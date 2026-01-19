"""
Azure Latency MCP Server.

Provides tools for testing Azure region latency and listing subscriptions.
"""

import asyncio
import json
import time
import threading
from typing import Optional
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP, Context
from pydantic import Field

from .models import (
    TestLatencyInput,
    build_latency_response,
    build_subscriptions_response,
)
from .latency_tester import (
    AzureLatencyTester,
    CancellationToken,
    list_azure_subscriptions,
)


# =============================================================================
# Server Configuration
# =============================================================================

# Queue lock for ensuring only one latency test runs at a time
_test_lock = asyncio.Lock()

# Track active cancellation tokens for cleanup
_active_tokens: dict[str, CancellationToken] = {}


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage server lifecycle."""
    yield {}


# Initialize MCP server
mcp = FastMCP(
    "azure_latency_mcp",
    lifespan=lifespan,
)


# =============================================================================
# Tools
# =============================================================================

@mcp.tool(
    name="azure_list_subscriptions",
    annotations={
        "title": "List Azure Subscriptions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def azure_list_subscriptions() -> str:
    """List all available Azure subscriptions.

    Returns a list of Azure subscriptions accessible with the current credentials.
    Uses DefaultAzureCredential which supports Azure CLI, environment variables,
    managed identity, and other authentication methods.

    Returns:
        JSON object containing:
        - subscriptions: List of subscription objects with id, name, and state
        - current: The subscription ID that will be used by default

    Raises:
        McpError: If authentication fails or no subscriptions are found.

    Example:
        >>> result = await azure_list_subscriptions()
        >>> # Returns: {"subscriptions": [{"id": "xxx", "name": "My Sub", "state": "Enabled"}], "current": "xxx"}
    """
    try:
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        subscriptions = await loop.run_in_executor(None, list_azure_subscriptions)

        if not subscriptions:
            raise RuntimeError("No Azure subscriptions found. Please ensure you are logged in with 'az login'.")

        response = build_subscriptions_response(subscriptions)
        return json.dumps(response, indent=2)

    except Exception as e:
        raise RuntimeError(f"Failed to list Azure subscriptions: {str(e)}")


@mcp.tool(
    name="azure_test_latency",
    annotations={
        "title": "Test Azure Region Latency",
        "readOnlyHint": False,  # Creates temporary storage accounts
        "destructiveHint": False,  # Cleans up after itself
        "idempotentHint": True,  # Same inputs produce same type of output
        "openWorldHint": True,  # Interacts with Azure
    }
)
async def azure_test_latency(
    regions: list[str] = Field(
        ...,
        description="List of Azure region names to test (e.g., ['westeurope', 'eastus', 'southeastasia'])",
    ),
    request_count: int = Field(
        default=10,
        description="Number of TCP connection attempts per region (3-20). Higher values give more accurate averages but take longer.",
        ge=3,
        le=20,
    ),
    subscription_id: Optional[str] = Field(
        default=None,
        description="Azure subscription ID to use. If not provided, uses the first available subscription.",
    ),
    log_file: Optional[str] = Field(
        default=None,
        description="Path to log file. Defaults to './azure-latency-test.log' in current working directory.",
    ),
    ctx: Context = None,
) -> str:
    """Test network latency to Azure regions by pinging blob storage endpoints.

    This tool tests TCP connection latency to Azure blob storage endpoints in the
    specified regions. For regions without existing public endpoints, it creates
    temporary storage accounts, runs the tests, and cleans up afterward.

    The test measures raw TCP socket connection time to port 443, providing clean
    network latency measurements without HTTP overhead.

    Args:
        regions: List of Azure region names to test (e.g., ['westeurope', 'eastus']).
                 At least one region is required.
        request_count: Number of TCP connection attempts per region (3-20).
                       Default is 10. Higher values provide more accurate averages.
        subscription_id: Optional Azure subscription ID. Uses first available if not specified.
        log_file: Optional path to log file. Defaults to './azure-latency-test.log'.
        ctx: MCP context for progress reporting.

    Returns:
        JSON object containing:
        - success: Boolean indicating if tests completed successfully
        - best_region: Region with lowest average latency
        - best_latency_ms: Lowest average latency in milliseconds
        - results: Array of results per region (sorted by avg_ms):
            - region: Region name
            - endpoint: Blob storage endpoint used
            - min_ms, max_ms, avg_ms: Latency statistics
            - failed: Number of failed connection attempts
        - regions_tested: Number of regions successfully tested
        - resource_group: Name of the temporary resource group used
        - subscription_id: Azure subscription ID used
        - created_accounts: List of storage accounts that were created
        - deleted_accounts: List of storage accounts that were deleted
        - failed_deletions: List of storage accounts that failed to delete
        - warnings: Any warnings or issues encountered
        - cleanup_required: If cleanup failed, details of resources needing manual cleanup
        - duration_seconds: Total execution time
        - log_file: Path to detailed log file
        - cancelled: Whether the operation was cancelled

    Example:
        >>> result = await azure_test_latency(
        ...     regions=["westeurope", "eastus", "southeastasia"],
        ...     request_count=5
        ... )
        >>> # Returns results sorted by latency with best_region indicated
    """
    # Validate input
    if not regions:
        raise ValueError("At least one region must be specified")

    # Normalize regions
    regions = [r.lower().strip() for r in regions if r.strip()]
    if not regions:
        raise ValueError("No valid regions provided after normalization")

    # Use default log file if not specified
    actual_log_file = log_file or "./azure-latency-test.log"

    # Acquire lock to ensure only one test runs at a time
    async with _test_lock:
        start_time = time.time()
        
        # Create cancellation token
        cancel_token = CancellationToken()
        test_id = str(time.time())
        _active_tokens[test_id] = cancel_token

        try:
            # Progress callback that reports to MCP context
            def progress_callback(phase: int, total_phases: int, message: str, percentage: float):
                if ctx:
                    try:
                        # Use asyncio to report progress from sync context
                        asyncio.get_event_loop().call_soon_threadsafe(
                            lambda: None  # Progress reporting placeholder
                        )
                    except Exception:
                        pass  # Ignore progress errors

            # Create tester instance
            tester = AzureLatencyTester(
                request_count=request_count,
                throttle_limit=10,
                log_file=actual_log_file,
                regions=regions,
                subscription_id=subscription_id,
                progress_callback=progress_callback,
                cancellation_token=cancel_token,
            )

            # Run the test in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, tester.run)

            # Build response
            duration = time.time() - start_time

            response = build_latency_response(
                success=True,
                results=results,
                resource_group=tester.resource_group_name,
                subscription_id=tester.subscription_id or "",
                created_accounts=[a.storage_account for a in tester.created_accounts],
                deleted_accounts=tester.deleted_accounts,
                failed_deletions=tester.failed_deletions,
                warnings=tester.warnings,
                duration_seconds=duration,
                log_file=actual_log_file,
                cancelled=cancel_token.is_cancelled(),
            )

            return json.dumps(response, indent=2)

        except Exception as e:
            # Return error as MCP exception
            raise RuntimeError(f"Latency test failed: {str(e)}")

        finally:
            # Clean up cancellation token
            _active_tokens.pop(test_id, None)


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()