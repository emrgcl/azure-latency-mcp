"""
Data models for Azure Latency MCP Server.

Defines dataclasses and Pydantic models for structured responses.
"""

from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Response Models (Dataclasses for internal use)
# =============================================================================

@dataclass
class LatencyResult:
    """Stores latency test results for a single region."""
    region: str
    endpoint: str
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    avg_ms: Optional[float] = None
    failed: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "region": self.region,
            "endpoint": self.endpoint,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "avg_ms": self.avg_ms,
            "failed": self.failed,
        }


@dataclass
class CreatedStorageAccount:
    """Tracks a temporarily created storage account."""
    region: str
    storage_account: str
    endpoint: str
    status: str = "Created"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "region": self.region,
            "storage_account": self.storage_account,
            "endpoint": self.endpoint,
            "status": self.status,
        }


@dataclass
class SubscriptionInfo:
    """Azure subscription information."""
    id: str
    name: str
    state: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
        }


# =============================================================================
# Pydantic Input Models (for MCP tool validation)
# =============================================================================

class TestLatencyInput(BaseModel):
    """Input parameters for the test_latency tool."""
    
    regions: list[str] = Field(
        ...,
        description="List of Azure region names to test (e.g., ['westeurope', 'eastus', 'southeastasia'])",
        min_length=1,
        max_length=50,
    )
    
    request_count: int = Field(
        default=10,
        description="Number of TCP connection attempts per region (3-20). Higher values give more accurate averages but take longer.",
        ge=3,
        le=20,
    )
    
    subscription_id: Optional[str] = Field(
        default=None,
        description="Azure subscription ID to use. If not provided, uses the first available subscription.",
    )
    
    log_file: Optional[str] = Field(
        default=None,
        description="Path to log file. Defaults to './azure-latency-test.log' in current working directory.",
    )

    @field_validator('regions')
    @classmethod
    def validate_regions(cls, v: list[str]) -> list[str]:
        """Validate and normalize region names."""
        if not v:
            raise ValueError("At least one region must be specified")
        # Normalize to lowercase and strip whitespace
        return [r.lower().strip() for r in v if r.strip()]


class ListSubscriptionsInput(BaseModel):
    """Input parameters for the list_subscriptions tool (no parameters needed)."""
    pass


# =============================================================================
# Response Builders
# =============================================================================

def build_latency_response(
    success: bool,
    results: list[LatencyResult],
    resource_group: str,
    subscription_id: str,
    created_accounts: list[str],
    deleted_accounts: list[str],
    failed_deletions: list[dict],
    warnings: list[str],
    duration_seconds: float,
    log_file: str,
    cancelled: bool = False,
) -> dict:
    """Build the two-part response structure for test_latency tool (Option E)."""
    
    # Determine best region from results
    best_region = results[0].region if results else None
    best_latency_ms = results[0].avg_ms if results else None
    
    # Determine infrastructure status
    if not created_accounts:
        infra_status = "No temporary resources needed - used existing endpoints"
    elif failed_deletions:
        infra_status = "Cleanup incomplete - manual action required"
    else:
        infra_status = "All resources cleaned up successfully"
    
    # Determine if action is required and build action message
    action_required = len(failed_deletions) > 0
    action_message = None
    if action_required:
        failed_names = [fd["account"] for fd in failed_deletions]
        if len(failed_names) == 1:
            action_message = f"Please manually delete storage account '{failed_names[0]}' in resource group '{resource_group}' or delete the entire resource group"
        else:
            action_message = f"Please manually delete storage accounts {failed_names} in resource group '{resource_group}' or delete the entire resource group"
    
    response = {
        # Top-level metadata
        "success": success,
        "cancelled": cancelled,
        "duration_seconds": round(duration_seconds, 2),
        "log_file": log_file,
        "warnings": warnings,
        
        # Latency results section
        "latency_results": {
            "best_region": best_region,
            "best_latency_ms": best_latency_ms,
            "regions_tested": len(results),
            "results": [r.to_dict() for r in results],
        },
        
        # Infrastructure operations section
        "infrastructure": {
            "status": infra_status,
            "subscription_id": subscription_id,
            "resource_group": resource_group,
            "created_accounts": created_accounts,
            "deleted_accounts": deleted_accounts,
            "failed_deletions": failed_deletions,
            "action_required": action_required,
            "action_message": action_message,
        },
    }
    
    return response


def build_subscriptions_response(
    subscriptions: list[SubscriptionInfo],
    current: Optional[str] = None,
) -> dict:
    """Build the response structure for list_subscriptions tool."""
    return {
        "subscriptions": [s.to_dict() for s in subscriptions],
        "current": current or (subscriptions[0].id if subscriptions else None),
    }