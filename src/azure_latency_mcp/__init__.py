"""
Azure Latency MCP Server.

An MCP server for testing Azure region latency and managing Azure subscriptions.
"""

__version__ = "1.0.0"

__all__ = [
    # Models
    "LatencyResult",
    "CreatedStorageAccount",
    "CleanupRequired",
    "SubscriptionInfo",
    "TestLatencyInput",
    # Tester
    "AzureLatencyTester",
    "CancellationToken",
    "list_azure_subscriptions",
    # Server
    "mcp",
]


def __getattr__(name: str):
    """Lazy import to avoid circular imports when running as __main__."""
    if name in ("LatencyResult", "CreatedStorageAccount", "CleanupRequired", 
                "SubscriptionInfo", "TestLatencyInput"):
        from . import models
        return getattr(models, name)
    elif name in ("AzureLatencyTester", "CancellationToken", "list_azure_subscriptions"):
        from . import latency_tester
        return getattr(latency_tester, name)
    elif name == "mcp":
        from . import server
        return server.mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
