# Azure Region Advisor

An AI-powered toolkit for making informed Azure region selection decisions by combining **network latency testing** and **pricing analysis**. Designed to work with GitHub Copilot (with Claude) and Claude Desktop through MCP (Model Context Protocol) and Claude Skills.

## Overview

Choosing the right Azure region involves balancing two key factors:

| Factor | Tool | Purpose |
|--------|------|---------|
| **Latency** | MCP Server | Measures actual TCP connection latency from your location to Azure regions |
| **Cost** | Claude Skill | Queries Azure Retail Prices API for VM pricing across regions |

When used together with an AI assistant, these tools provide comprehensive region recommendations that consider both performance and cost implications.

![Example Output](docs/example-output.png)

## Features

### 🌐 Latency Testing (MCP Server)
- Tests TCP connection latency to Azure blob storage endpoints
- Creates temporary storage accounts for regions without public endpoints
- Parallel execution for speed
- Automatic cleanup of temporary resources
- Supports cancellation with graceful resource cleanup

### 💰 Pricing Analysis (Claude Skill)
- Queries Azure Retail Prices API for any VM SKU
- Compares pricing across all Azure regions
- Shows consumption, spot, and reserved instance pricing
- Calculates annual costs and potential savings
- Supports multiple currencies (USD, EUR, GBP, TRY, etc.)

## Installation

### Prerequisites

- **Python 3.10+** [Download & Install Python](https://www.python.org/downloads/)
- **Azure CLI** - For authentication [Download and Installation Instructions](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?view=azure-cli-latest&pivots=winget)
- **VS Code Insider with GitHub Copilot** - For the integrated experience [Download here](https://code.visualstudio.com/insiders).
  > IMPORTANT NOTE: Please use only VS Code Insider as of January 2026 as the Agent Skills is only supported on Insiders edition as of Jan 2026.

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/azure-region-advisor.git
cd azure-region-advisor

# Install dependencies
pip install -r requirements.txt

# Authenticate with Azure
az login

# You are done! start the VSCODE insider, enable Github Copilot agent and start chatting:)
```

## Usage

Everything is preconfigured once you installed requirements and enabled copilot for VSCode Insider you are good to go!

### Recommended: AI-Assisted Region Selection

Ask your AI assistant questions like:

> "Help me choose an Azure region for deploying a Standard_D8as_v6 VM. I need good latency from Turkey and want to optimize costs."

The assistant will:
1. Discuss your requirements and confirm the VM SKU
2. Run latency tests to candidate regions using the MCP server
3. Query pricing data using the Claude skill
4. Combine results into a comprehensive recommendation

### Example Conversation

**You:** I need to deploy an 8-core VM with 32GB RAM for a web application serving users in Turkey. Help me choose the best region.

**Assistant:** For your requirements, I recommend the Standard_D8as_v6 SKU (AMD-based, 8 vCPU, 32GB RAM). Let me analyze the best regions...

*[Runs latency tests and pricing queries]*

**Output:**

| Bölge | Linux/Saat | Yıllık Maliyet | Latency |
|-------|------------|----------------|---------|
| uksouth 🏆 | $0.0506 | ~$443/yıl | 52.4 ms |
| swedencentral | $0.0717 | ~$628/yıl | 57.4 ms |
| germanywestcentral | $0.0811 | ~$710/yıl | 39.6 ms ⚡ |
| polandcentral | $0.0813 | ~$712/yıl | 45.2 ms |

**🎯 Recommendations:**
- **Option 1: Lowest Cost** - UK South ($1,918/yr total)
- **Option 2: Lowest Latency** - Germany West Central (39.6ms)
- **Option 3: Balanced** - Poland Central (good price/performance)

### Direct Tool Usage

#### Query VM Pricing

```bash
# Basic pricing query
python .claude/skills/azure-pricing/scripts/query_vm_pricing.py --sku Standard_D8as_v6

# With specific currency
python .claude/skills/azure-pricing/scripts/query_vm_pricing.py --sku Standard_D48as_v6 --currency EUR

# Filter to specific regions
python .claude/skills/azure-pricing/scripts/query_vm_pricing.py --sku Standard_D8as_v6 \
  --regions westeurope,northeurope,uksouth,germanywestcentral
```

#### Test Latency via MCP

Ask your AI assistant:
> "Test latency to westeurope, northeurope, uksouth, germanywestcentral, and polandcentral"

Or use the MCP Inspector:
```bash
npx @modelcontextprotocol/inspector python -m azure_latency_mcp.server
```

## Configuration

### VS Code + GitHub Copilot

The repository includes pre-configured VS Code settings. After cloning:

1. Open the repository folder in VS Code
2. The MCP server configuration is in `.vscode/mcp.json`
3. Copilot instructions are in `.github/copilot-instructions.md`
4. The Claude skill is automatically available in `.claude/skills/azure-pricing/`

**MCP Server Configuration** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "azure-latency": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "azure_latency_mcp.server"]
    }
  }
}
```

### Claude Desktop

Add to your Claude Desktop configuration:

**Linux/Mac:** `~/.config/claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

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

## MCP Tools Reference

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

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `regions` | `list[str]` | Yes | - | Azure region names (e.g., `["westeurope", "eastus"]`) |
| `request_count` | `int` | No | `10` | TCP connection attempts per region (3-20) |
| `subscription_id` | `str` | No | First available | Azure subscription ID to use |
| `log_file` | `str` | No | `./azure-latency-test.log` | Path to log file |

**Returns:**
```json
{
  "success": true,
  "latency_results": {
    "best_region": "germanywestcentral",
    "best_latency_ms": 39.6,
    "regions_tested": 5,
    "results": [
      {"region": "germanywestcentral", "avg_ms": 39.6, "min_ms": 38.2, "max_ms": 42.1},
      {"region": "polandcentral", "avg_ms": 45.2, "min_ms": 43.1, "max_ms": 48.3}
    ]
  },
  "infrastructure": {
    "status": "All resources cleaned up successfully",
    "created_accounts": [],
    "deleted_accounts": []
  }
}
```

## Claude Skill Reference

### Azure Pricing Skill

**Location:** `.claude/skills/azure-pricing/`

**Purpose:** Query Azure retail prices for VM SKUs across all regions.

**Script:** `scripts/query_vm_pricing.py`

| Option | Description |
|--------|-------------|
| `--sku` | VM SKU name (required, e.g., `Standard_D8as_v6`) |
| `--currency` | Currency code (default: USD) |
| `--regions` | Comma-separated list of regions (optional) |

**Output Sections:**
1. **Summary Table** - All regions sorted by Linux hourly price
2. **Cost Analysis** - Cheapest vs most expensive with annual savings

**Supported Price Types:**
- Linux consumption (pay-as-you-go)
- Windows consumption
- Windows with Azure Hybrid Benefit (same as Linux)
- Spot instances
- 1-year reserved instances
- 3-year reserved instances

## Project Structure

```
azure-region-advisor/
├── .claude/
│   └── skills/
│       └── azure-pricing/              # Claude skill for pricing
│           ├── SKILL.md                # Skill instructions
│           ├── scripts/
│           │   └── query_vm_pricing.py # Pricing query script
│           └── references/
│               └── service-mapping.md  # Service name mappings
├── .github/
│   └── copilot-instructions.md         # GitHub Copilot instructions
├── .vscode/
│   ├── mcp.json                        # MCP server configuration
│   └── settings.json                   # VS Code settings
├── src/
│   └── azure_latency_mcp/              # MCP server package
│       ├── __init__.py
│       ├── server.py                   # MCP server and tools
│       ├── latency_tester.py           # Core latency testing
│       └── models.py                   # Data models
├── pyproject.toml                      # Package configuration
├── requirements.txt                    # Python dependencies
├── LICENSE                             # MIT License
└── README.md                           # This file
```

## How It Works

### Latency Testing Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Phase 1: DNS   │────▶│ Phase 2: Create │────▶│ Phase 3: Test   │
│  Resolution     │     │ Storage Accounts│     │ TCP Latency     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │ Phase 4: Cleanup│
                                               │ Resources       │
                                               └─────────────────┘
```

1. **DNS Check** - Checks if `{region}.blob.core.windows.net` resolves
2. **Storage Creation** - Creates temporary accounts for unresolved regions
3. **Latency Test** - TCP connections to port 443, measures connection time
4. **Cleanup** - Deletes temporary storage accounts and resource groups

### Pricing Query Flow

1. **Parse SKU** - Normalizes name (e.g., `D8as_v6` → `Standard_D8as_v6`)
2. **API Query** - Fetches from Azure Retail Prices API with pagination
3. **Organize** - Groups by region and price type
4. **Output** - Summary table + cost analysis

## Regional Recommendations by Location

### Users in Turkey / Middle East
```
germanywestcentral, polandcentral, swedencentral, 
northeurope, westeurope, uksouth, francecentral, italynorth
```

### Users in Western Europe
```
westeurope, northeurope, uksouth, francecentral, 
germanywestcentral, swedencentral
```

### Users in North America
```
eastus, eastus2, centralus, westus2, westus3, canadacentral
```

### Users in Asia Pacific
```
southeastasia, eastasia, japaneast, australiaeast, koreacentral
```

## Troubleshooting

### "No Azure subscriptions found"

```bash
az login
```

### "Failed to create resource group"

Ensure your Azure account has permissions to create:
- Resource groups
- Storage accounts (Standard_LRS)

### Cleanup Failed

Check the response for `infrastructure.action_message`. Manual cleanup:

```bash
az group delete --name latency-test-mcp-YYYYMMDDHHMMSS --yes
```

### Pricing Script Returns No Data

- Verify the SKU name is correct (use `Standard_` prefix)
- Check if the SKU is available in Azure (newer SKUs may have limited regions)

### Slow Latency Tests

- Reduce `request_count` to 3-5 for faster tests
- Test fewer regions at once
- Check your network connection

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## License

MIT License - Copyright (c) 2026 Emre Guclu

See [LICENSE](LICENSE) for details.
