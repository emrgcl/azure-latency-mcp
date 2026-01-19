"""
Azure Region Latency Tester with Cancellation Support.

Tests latency to Azure regions by pinging blob storage endpoints.
Creates temporary storage accounts for regions without existing endpoints.
"""

import socket
import time
import uuid
import logging
import asyncio
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Optional, Callable, Any
from collections.abc import Sequence

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import (
    StorageAccountCreateParameters,
    Sku,
    Kind,
)
from azure.mgmt.subscription import SubscriptionClient
from azure.core.exceptions import AzureError

from .models import (
    LatencyResult,
    CreatedStorageAccount,
    SubscriptionInfo,
)


# Type alias for progress callback
# callback(phase: int, total_phases: int, message: str, percentage: float)
ProgressCallback = Callable[[int, int, str, float], Any]


class CancellationToken:
    """Thread-safe cancellation token for graceful shutdown."""
    
    def __init__(self):
        self._cancelled = threading.Event()
    
    def cancel(self):
        """Signal cancellation."""
        self._cancelled.set()
    
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled.is_set()
    
    def reset(self):
        """Reset the cancellation state."""
        self._cancelled.clear()


class AzureLatencyTester:
    """Main class for Azure region latency testing with cancellation support."""

    def __init__(
        self,
        request_count: int = 10,
        throttle_limit: int = 10,
        resource_group_prefix: str = "latency-test-mcp",
        log_file: str = "./azure-latency-test.log",
        regions: Sequence[str] | None = None,
        subscription_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ):
        self.request_count = request_count
        self.throttle_limit = throttle_limit
        self.resource_group_prefix = resource_group_prefix
        self.log_file = log_file
        self.regions = list(regions) if regions else []
        self.target_subscription_id = subscription_id
        self.progress_callback = progress_callback
        self.cancellation_token = cancellation_token or CancellationToken()

        # Generate unique resource group name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.resource_group_name = f"{self.resource_group_prefix}-{timestamp}"

        # Thread-safe data structures
        self.endpoint_map: dict[str, str] = {}
        self.created_accounts: list[CreatedStorageAccount] = []
        self.deleted_accounts: list[str] = []
        self.failed_deletions: list[dict] = []
        self.results: list[LatencyResult] = []
        self.warnings: list[str] = []

        # Azure clients (initialized on connect)
        self.credential: Optional[DefaultAzureCredential] = None
        self.subscription_id: Optional[str] = None
        self.resource_client: Optional[ResourceManagementClient] = None
        self.storage_client: Optional[StorageManagementClient] = None

        # Setup logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging to file."""
        self.logger = logging.getLogger(f"AzureLatencyTest-{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # File handler
        try:
            file_handler = logging.FileHandler(self.log_file, mode="w")
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
        except (IOError, OSError) as e:
            # If we can't write to log file, use a null handler
            self.logger.addHandler(logging.NullHandler())
            self.warnings.append(f"Could not create log file: {e}")

        self.logger.info("Azure Latency Test Started")
        self.logger.info(f"Resource group name: {self.resource_group_name}")

    def _report_progress(self, phase: int, total_phases: int, message: str, percentage: float) -> None:
        """Report progress via callback if available."""
        self.logger.info(f"Progress: Phase {phase}/{total_phases} - {message} ({percentage:.0f}%)")
        if self.progress_callback:
            try:
                self.progress_callback(phase, total_phases, message, percentage)
            except Exception as e:
                self.logger.warning(f"Progress callback failed: {e}")

    def _check_cancelled(self) -> bool:
        """Check if cancellation was requested and log if so."""
        if self.cancellation_token.is_cancelled():
            self.logger.warning("Cancellation requested")
            return True
        return False

    def connect_to_azure(self) -> bool:
        """Connect to Azure using DefaultAzureCredential."""
        self.logger.info("Connecting to Azure...")
        try:
            self.credential = DefaultAzureCredential()

            # Get subscriptions
            sub_client = SubscriptionClient(self.credential)
            subscriptions = list(sub_client.subscriptions.list())

            if not subscriptions:
                self.logger.error("No Azure subscriptions found")
                raise RuntimeError("No Azure subscriptions found. Ensure you are logged in with 'az login'.")

            # Use target subscription if provided, otherwise first available
            if self.target_subscription_id:
                matching = [s for s in subscriptions if s.subscription_id == self.target_subscription_id]
                if not matching:
                    available = [s.subscription_id for s in subscriptions]
                    raise RuntimeError(
                        f"Subscription '{self.target_subscription_id}' not found. "
                        f"Available: {available}"
                    )
                self.subscription_id = matching[0].subscription_id
                sub_name = matching[0].display_name
            else:
                self.subscription_id = subscriptions[0].subscription_id
                sub_name = subscriptions[0].display_name

            self.logger.info(f"Connected to Azure subscription: {sub_name} ({self.subscription_id})")

            # Initialize management clients
            self.resource_client = ResourceManagementClient(
                self.credential, self.subscription_id
            )
            self.storage_client = StorageManagementClient(
                self.credential, self.subscription_id
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Azure: {e}")
            raise

    def _check_dns(self, region: str) -> tuple[str, Optional[str]]:
        """Check if DNS resolves for a region's blob endpoint."""
        endpoint = f"{region}.blob.core.windows.net"
        try:
            socket.gethostbyname(endpoint)
            return region, endpoint
        except socket.gaierror:
            return region, None

    def phase1_check_dns(self) -> tuple[list[str], list[str]]:
        """Phase 1: Check DNS resolution for all regions."""
        self._report_progress(1, 4, f"Checking DNS resolution for {len(self.regions)} regions", 10)
        
        if self._check_cancelled():
            return [], []

        self.logger.info("Phase 1: Checking DNS resolution for all regions")

        regions_needing_storage: list[str] = []

        with ThreadPoolExecutor(max_workers=self.throttle_limit) as executor:
            futures = {
                executor.submit(self._check_dns, region): region
                for region in self.regions
            }

            for future in as_completed(futures):
                if self._check_cancelled():
                    break
                region, endpoint = future.result()
                if endpoint:
                    self.endpoint_map[region] = endpoint
                else:
                    regions_needing_storage.append(region)

        resolved = sorted(self.endpoint_map.keys())
        to_create = sorted(regions_needing_storage)

        self.logger.info(f"DNS resolved: {', '.join(resolved) if resolved else 'None'}")
        self.logger.info(f"Need storage accounts: {', '.join(to_create) if to_create else 'None'}")

        return resolved, to_create

    def _create_storage_account(self, region: str) -> Optional[CreatedStorageAccount]:
        """Create a temporary storage account in a region."""
        if self._check_cancelled():
            return None

        # Generate unique storage account name (3-24 chars, lowercase alphanumeric only)
        guid = uuid.uuid4().hex[:16]
        storage_account_name = f"lat{guid}"

        try:
            # Create storage account
            params = StorageAccountCreateParameters(
                sku=Sku(name="Standard_LRS"),
                kind=Kind.STORAGE_V2,
                location=region,
                minimum_tls_version="TLS1_2",
                allow_blob_public_access=True,
            )

            poller = self.storage_client.storage_accounts.begin_create(
                self.resource_group_name, storage_account_name, params
            )
            poller.result()  # Wait for completion

            endpoint = f"{storage_account_name}.blob.core.windows.net"
            self.endpoint_map[region] = endpoint

            account = CreatedStorageAccount(
                region=region,
                storage_account=storage_account_name,
                endpoint=endpoint,
                status="Created",
            )
            self.created_accounts.append(account)
            self.logger.info(f"Created storage account: {storage_account_name} in {region}")
            return account

        except AzureError as e:
            self.logger.error(f"Failed to create storage account in {region}: {e}")
            self.warnings.append(f"Failed to create storage account in {region}: {str(e)}")
            return None

    def phase2_create_storage_accounts(self, regions_to_create: list[str]) -> None:
        """Phase 2: Create temporary storage accounts for unresolved regions."""
        if not regions_to_create:
            self._report_progress(2, 4, "No storage accounts needed", 30)
            return

        if self._check_cancelled():
            return

        self._report_progress(2, 4, f"Creating storage accounts for {len(regions_to_create)} regions", 20)
        self.logger.info("Phase 2: Creating temporary storage accounts")

        # Ensure resource group exists
        rg_location = regions_to_create[0]
        try:
            self.resource_client.resource_groups.get(self.resource_group_name)
            self.logger.info(f"Resource group '{self.resource_group_name}' already exists")
        except AzureError:
            self.logger.info(f"Creating resource group '{self.resource_group_name}' in '{rg_location}'")
            try:
                self.resource_client.resource_groups.create_or_update(
                    self.resource_group_name, {"location": rg_location}
                )
                self.logger.info(f"Resource group created: {self.resource_group_name}")
            except AzureError as e:
                self.logger.error(f"Failed to create resource group: {e}")
                raise RuntimeError(f"Failed to create resource group: {e}")

        if self._check_cancelled():
            return

        # Create storage accounts in parallel
        with ThreadPoolExecutor(max_workers=self.throttle_limit) as executor:
            futures = {
                executor.submit(self._create_storage_account, region): region
                for region in regions_to_create
            }

            for future in as_completed(futures):
                if self._check_cancelled():
                    break
                future.result()  # Process results (logging happens in worker)

        self._report_progress(2, 4, f"Created {len(self.created_accounts)} storage accounts", 30)
        self.logger.info(f"Storage account creation complete. Created: {len(self.created_accounts)}")

    def _test_latency(self, region: str, endpoint: str) -> LatencyResult:
        """Test TCP latency to an endpoint."""
        latencies: list[float] = []

        for i in range(self.request_count):
            if self._check_cancelled():
                break

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)

                start = time.perf_counter()
                sock.connect((endpoint, 443))
                elapsed = (time.perf_counter() - start) * 1000  # Convert to ms

                sock.close()
                latencies.append(elapsed)

            except (socket.error, socket.timeout):
                latencies.append(-1)

            time.sleep(0.1)  # 100ms delay between requests

        # Calculate statistics
        valid = [lat for lat in latencies if lat >= 0]
        failed = len([lat for lat in latencies if lat < 0])

        result = LatencyResult(
            region=region,
            endpoint=endpoint,
            min_ms=round(min(valid), 1) if valid else None,
            max_ms=round(max(valid), 1) if valid else None,
            avg_ms=round(sum(valid) / len(valid), 1) if valid else None,
            failed=failed,
        )

        return result

    def phase3_run_latency_tests(self) -> list[LatencyResult]:
        """Phase 3: Run latency tests against all endpoints."""
        self._report_progress(3, 4, f"Running latency tests for {len(self.endpoint_map)} regions", 50)
        
        if self._check_cancelled():
            return []

        self.logger.info("Phase 3: Starting latency tests")

        for region, endpoint in self.endpoint_map.items():
            self.logger.info(f"Testing: {region} -> {endpoint}")

        results: list[LatencyResult] = []
        total_regions = len(self.endpoint_map)
        completed = 0

        with ThreadPoolExecutor(max_workers=self.throttle_limit) as executor:
            futures: dict[Future, str] = {
                executor.submit(self._test_latency, region, endpoint): region
                for region, endpoint in self.endpoint_map.items()
            }

            for future in as_completed(futures):
                if self._check_cancelled():
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    self.warnings.append(
                        f"Operation cancelled after {completed} of {total_regions} regions tested"
                    )
                    break

                result = future.result()
                results.append(result)
                completed += 1
                
                # Report incremental progress (50-90%)
                progress = 50 + (completed / total_regions) * 40
                self._report_progress(3, 4, f"Tested {completed}/{total_regions} regions", progress)
                
                self.logger.info(
                    f"Result: {result.region} - Avg: {result.avg_ms}ms, "
                    f"Min: {result.min_ms}ms, Max: {result.max_ms}ms, "
                    f"Failed: {result.failed}"
                )

        # Sort by average latency (N/A goes to end)
        self.results = sorted(
            results, key=lambda r: r.avg_ms if r.avg_ms is not None else float("inf")
        )

        self.logger.info("Phase 3 Complete: Latency test results")
        return self.results

    def _delete_storage_account(self, account: CreatedStorageAccount) -> tuple[str, str, str]:
        """Delete a storage account."""
        try:
            self.storage_client.storage_accounts.delete(
                self.resource_group_name, account.storage_account
            )
            self.logger.info(f"Deleted storage account: {account.storage_account}")
            return account.storage_account, account.region, "Deleted"
        except AzureError as e:
            self.logger.error(f"Failed to delete {account.storage_account}: {e}")
            return account.storage_account, account.region, f"FAILED: {e}"

    def phase4_cleanup(self) -> None:
        """Phase 4: Cleanup - Delete created storage accounts."""
        if not self.created_accounts:
            self._report_progress(4, 4, "No cleanup needed", 100)
            return

        self._report_progress(4, 4, f"Cleaning up {len(self.created_accounts)} storage accounts", 95)
        self.logger.info("Phase 4: Cleaning up temporary storage accounts")

        # Always attempt cleanup, even if cancelled
        with ThreadPoolExecutor(max_workers=self.throttle_limit) as executor:
            futures = {
                executor.submit(self._delete_storage_account, account): account
                for account in self.created_accounts
            }

            for future in as_completed(futures):
                account_name, region, status = future.result()
                if status == "Deleted":
                    self.deleted_accounts.append(account_name)
                else:
                    self.failed_deletions.append({
                        "account": account_name,
                        "region": region,
                        "error": status,
                    })

        self.logger.info(
            f"Cleanup complete. Deleted: {len(self.deleted_accounts)}, "
            f"Failed: {len(self.failed_deletions)}"
        )

        # Try to remove resource group if all accounts deleted
        if not self.failed_deletions:
            try:
                accounts = list(
                    self.storage_client.storage_accounts.list_by_resource_group(
                        self.resource_group_name
                    )
                )
                if not accounts:
                    self.logger.info(f"Removing empty resource group: {self.resource_group_name}")
                    self.resource_client.resource_groups.begin_delete(self.resource_group_name)
                    self.logger.info(f"Resource group removal initiated: {self.resource_group_name}")
            except AzureError as e:
                self.logger.warning(f"Could not remove resource group: {e}")
        else:
            # Add warnings for failed deletions
            for fd in self.failed_deletions:
                self.warnings.append(
                    f"Failed to delete storage account '{fd['account']}' in {fd['region']}: {fd['error']}"
                )

        self._report_progress(4, 4, "Cleanup complete", 100)

    def run(self) -> list[LatencyResult]:
        """Execute the full latency test workflow."""
        start_time = time.time()

        # Connect to Azure
        self.connect_to_azure()

        # Phase 1: Check DNS
        _, regions_to_create = self.phase1_check_dns()

        if self._check_cancelled():
            self.phase4_cleanup()
            return self.results

        # Phase 2: Create storage accounts
        self.phase2_create_storage_accounts(regions_to_create)

        if self._check_cancelled():
            self.phase4_cleanup()
            return self.results

        # Phase 3: Run latency tests
        self.phase3_run_latency_tests()

        # Phase 4: Cleanup (always run, even if cancelled)
        self.phase4_cleanup()

        self.logger.info("Azure Latency Test Completed")
        self.logger.info(f"Total duration: {time.time() - start_time:.2f} seconds")

        return self.results


def list_azure_subscriptions() -> list[SubscriptionInfo]:
    """List all available Azure subscriptions."""
    try:
        credential = DefaultAzureCredential()
        sub_client = SubscriptionClient(credential)
        subscriptions = list(sub_client.subscriptions.list())

        result = []
        for s in subscriptions:
            # Handle state - could be enum, string, or None
            if s.state is None:
                state = "Unknown"
            elif isinstance(s.state, str):
                state = s.state
            else:
                # It's an enum, get the value
                state = s.state.value if hasattr(s.state, 'value') else str(s.state)
            
            result.append(SubscriptionInfo(
                id=s.subscription_id,
                name=s.display_name,
                state=state,
            ))
        
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to list Azure subscriptions: {e}")