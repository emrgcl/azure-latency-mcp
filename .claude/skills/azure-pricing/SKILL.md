---
name: azure-pricing
description: Query Azure retail prices using the Azure Retail Prices API. Use when users ask about Azure service pricing, costs, or rates. Handles natural language queries like "how much does a VM cost" or "what's the price of Standard_D48as_v6" by mapping user intent to correct API serviceName values. Supports filtering by region, SKU, price type (consumption/reservation/spot), and currency. Provides comparison tables across all regions with annual cost analysis.
---

# Azure Pricing Skill

Query Azure retail prices via https://prices.azure.com/api/retail/prices

Scripts are located under `scripts` folder

## Workflow

1. **Parse user query** - Extract SKU name
2. **Run the Python script** - MANDATORY, do not use curl
3. **Display the FULL output** - Both tables must be shown

## CRITICAL: Always Use the Python Script

**DO NOT use curl or manual API calls. ALWAYS run this command:**

On Linux/Mac:
```bash
python3 scripts/query_vm_pricing.py --sku Standard_D48as_v6
```
On Windows:
```cmd
python scripts\query_vm_pricing.py --sku Standard_D48as_v6
```

The script outputs TWO sections - **you must display BOTH**:
1. Summary table (all regions)
2. Cost analysis (cheapest vs most expensive with savings)

Options:
- `--sku` - VM SKU name (required, e.g., Standard_D48as_v6)
- `--currency` - Currency code (default: USD)  
- `--regions` - Comma-separated list of specific regions (optional)

## Required Output Format

The script produces TWO sections that MUST both be displayed:

### Section 1: Summary Table (All Regions)
Sorted by Linux hourly price (ascending):

| Region | Linux (Win+AHB)/hr | Windows/hr | Spot/hr | 1yr Reserved | 3yr Reserved |
|--------|-------------------|------------|---------|--------------|--------------|
| eastus | $2.304 | $3.120 | $0.461 | $1.456 | $0.982 |
| ... | | | | | |

Notes:
- *Linux and Windows with Azure Hybrid Benefit share the same compute price*
- *Spot prices vary based on demand and can be evicted*

### Section 2: Cost Analysis (8,760 hrs/year)

**Cheapest Region: {region}**
| Price Type | Hourly | Annual |
|------------|--------|--------|

**Most Expensive Region: {region}**
| Price Type | Hourly | Annual |
|------------|--------|--------|

**Annual Savings (Cheapest vs Most Expensive)**
| Price Type | Cheapest Annual | Expensive Annual | Savings | % Saved |
|------------|-----------------|------------------|---------|---------|

**IMPORTANT: Always show BOTH sections. Do not truncate or summarize.**

## API Reference

**Base URL**: `https://prices.azure.com/api/retail/prices`

**Key Filters**:
- `serviceName eq 'Virtual Machines'`
- `armSkuName eq 'Standard_D48as_v6'`
- `priceType eq 'Consumption'` or `'Reservation'` or `'Spot'`

**Product Name Patterns**:
- Linux: `Virtual Machines Dasv6 Series` (no "Windows" in name)
- Windows: `Virtual Machines Dasv6 Series Windows`
- Spot: `priceType eq 'Spot'` filter

## Service Name Mapping

For non-VM queries, see `references/service-mapping.md` for mapping common terms to API serviceName values.

Common mappings:
- vm, virtual machine → `Virtual Machines`
- storage, blob, disk → `Storage`
- sql, database → `SQL Database`
- aks, kubernetes → `Azure Kubernetes Service`
