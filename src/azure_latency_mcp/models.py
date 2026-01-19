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
class CleanupRequired:
    """Information about resources that need manual cleanup."""
    resource_group: str
    accounts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "resource_group": self.resource_group,
            "accounts": self.accounts,
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
    cleanup_required: Optional[CleanupRequired],
    duration_seconds: float,
    log_file: str,
    cancelled: bool = False,
) -> dict:
    """Build the flat response structure for test_latency tool."""
    
    best_region = results[0].region if results else None
    best_latency_ms = results[0].avg_ms if results else None
    
    response = {
        "success": success,
        "best_region": best_region,
        "best_latency_ms": best_latency_ms,
        "results": [r.to_dict() for r in results],
        "regions_tested": len(results),
        "resource_group": resource_group,
        "subscription_id": subscription_id,
        "created_accounts": created_accounts,
        "deleted_accounts": deleted_accounts,
        "failed_deletions": failed_deletions,
        "warnings": warnings,
        "cleanup_required": cleanup_required.to_dict() if cleanup_required else None,
        "duration_seconds": round(duration_seconds, 2),
        "log_file": log_file,
        "cancelled": cancelled,
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
