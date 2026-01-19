# Azure Latency MCP Server

An MCP (Model Context Protocol) server for testing Azure region latency. This server enables AI assistants like Claude Desktop and GitHub Copilot to measure network latency to Azure regions by pinging blob storage endpoints.

## Features

- **Test latency to any Azure region** - Measures TCP connection latency to Azure blob storage endpoints
- **Dynamic infrastructure** - Creates temporary storage accounts for regions without existing public endpoints, then cleans up
- **Parallel execution** - Tests multiple regions simultaneously for speed
- **Graceful cancellation** - Supports cancellation with proper cleanup of temporary resources
- **Queued execution** - Only one latency test runs at a time to avoid resource conflicts
- **Detailed logging** - Comprehensive log file with timestamps and phase information

## Tools

### `azure_list_subscriptions`

Lists all available Azure subscriptions accessible with current credentials.

**Parameters:** None

**Returns:**
```json
{
  "subscriptions": [
    {"id": "xxxx-xxxx-xxxx", "name": "My Subscription", "state": "Enabled"}
  ],
  "current": "xxxx-xxxx-xxxx"
}
```

### `azure_test_latency`

Tests network latency to specified Azure regions.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `regions` | `list[str]` | Yes | - | Azure region names to test (e.g., `["westeurope", "eastus"]`) |
| `request_count` | `int` | No | `10` | TCP connection attempts per region (3-20) |
| `subscription_id` | `str` | No | First available | Azure subscription ID to use |
| `log_file` | `str` | No | `./azure-latency-test.log` | Path to log file |

**Returns:**
```json
{
  "success": true,
  "best_region": "westeurope",
  "best_latency_ms": 42.5,
  "results": [
    {
      "region": "westeurope",
      "endpoint": "westeurope.blob.core.windows.net",
      "min_ms": 38.2,
      "max_ms": 52.1,
      "avg_ms": 42.5,
      "failed": 0
    }
  ],
  "regions_tested": 1,
  "resource_group": "latency-test-mcp-20250119143052",
  "subscription_id": "xxxx-xxxx-xxxx",
  "created_accounts": [],
  "deleted_accounts": [],
  "failed_deletions": [],
  "warnings": [],
  "cleanup_required": null,
  "duration_seconds": 15.3,
  "log_file": "./azure-latency-test.log",
  "cancelled": false
}
```

## Installation

### Prerequisites

1. **Python 3.10+** - Required for the MCP server
2. **Azure CLI** - For authentication (`az login`)
3. **uv** (recommended) or pip - For package management

### Install with uv (Recommended)

```bash
# Clone or download the repository
cd azure-latency-mcp

# Install with uv
uv pip install -e .
```

### Install with pip

```bash
cd azure-latency-mcp
pip install -e .
```

### Azure Authentication

The server uses `DefaultAzureCredential` which supports multiple authentication methods:

1. **Azure CLI** (recommended for local development):
   ```bash
   az login
   ```

2. **Environment variables**:
   ```bash
   export AZURE_CLIENT_ID="your-client-id"
   export AZURE_TENANT_ID="your-tenant-id"
   export AZURE_CLIENT_SECRET="your-client-secret"
   ```

3. **Managed Identity** (when running in Azure)

## Configuration

### Claude Desktop

Add to your Claude Desktop configuration (`~/.config/claude/claude_desktop_config.json` on Linux/Mac or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "azure-latency": {
      "command": "uv",
      "args": ["run", "--with", "azure-latency-mcp", "azure-latency-mcp"]
    }
  }
}
```

Or if installed globally:

```json
{
  "mcpServers": {
    "azure-latency": {
      "command": "azure-latency-mcp"
    }
  }
}
```

### GitHub Copilot

Add to your VS Code settings or Copilot configuration:

```json
{
  "github.copilot.chat.mcpServers": {
    "azure-latency": {
      "command": "azure-latency-mcp"
    }
  }
}
```

### Running Manually

For testing or development:

```bash
# Run with uv
uv run azure-latency-mcp

# Or if installed
azure-latency-mcp
```

### Using MCP Inspector

Test the server interactively:

```bash
npx @modelcontextprotocol/inspector azure-latency-mcp
```

## Usage Examples

### List Available Subscriptions

Ask Claude or Copilot:
> "List my Azure subscriptions"

### Test European Regions

> "Test latency to Azure regions in Europe: westeurope, northeurope, uksouth, francecentral, germanywestcentral"

### Find Best Region for a Workload

> "I need to deploy a service that serves users in the Middle East. Test latency to uaenorth, qatarcentral, and israelcentral to find the best region."

### Quick Test with Fewer Pings

> "Do a quick latency test (3 pings) to westeurope and eastus"

## How It Works

1. **DNS Check** - For each region, checks if `{region}.blob.core.windows.net` resolves
2. **Storage Account Creation** - For regions without existing endpoints, creates temporary storage accounts
3. **Latency Testing** - Opens TCP connections to port 443 and measures connection time
4. **Cleanup** - Deletes all temporary storage accounts and resource groups

### Resource Naming

- Resource groups: `latency-test-mcp-{yyyyMMddHHmmss}`
- Storage accounts: `lat{random16chars}`

All resources are automatically cleaned up after testing. If cleanup fails, the response includes `cleanup_required` with details.

## Troubleshooting

### "No Azure subscriptions found"

Run `az login` to authenticate with Azure CLI.

### "Failed to create resource group"

Ensure your Azure account has permissions to create resource groups and storage accounts.

### Cleanup Failed

If storage accounts weren't deleted, check the `cleanup_required` field in the response for the resource group name and account names. You can manually delete them:

```bash
az group delete --name latency-test-mcp-20250119143052 --yes
```

### Slow Performance

- Reduce `request_count` to 3-5 for faster tests
- Test fewer regions at once
- Check your network connection

## Development

### Project Structure

```
azure-latency-mcp/
├── src/
│   └── azure_latency_mcp/
│       ├── __init__.py        # Package exports
│       ├── server.py          # MCP server and tools
│       ├── latency_tester.py  # Core testing logic
│       └── models.py          # Data models
├── pyproject.toml             # Package configuration
└── README.md                  # This file
```

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest
```

### Building

```bash
uv build
```

## License

MIT

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
