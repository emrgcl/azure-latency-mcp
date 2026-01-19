#!/usr/bin/env python3
"""
Azure VM Pricing Query Script

Queries Azure Retail Prices API and produces:
1. Summary table of all regions sorted by Linux price
2. Cost analysis comparing cheapest vs most expensive regions
"""

import argparse
import json
import requests
import sys
from typing import Dict, List, Optional, Any
from collections import defaultdict


HOURS_PER_YEAR = 8760


def query_azure_prices(
    sku: str,
    currency: str = "USD",
    regions: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Query Azure Retail Prices API for a specific VM SKU.
    Fetches all price types: Consumption, Reservation, Spot
    """
    base_url = "https://prices.azure.com/api/retail/prices"
    all_items = []
    
    # Build filter - get all prices for this SKU
    filter_str = f"serviceName eq 'Virtual Machines' and armSkuName eq '{sku}'"
    
    url = f"{base_url}?$filter={filter_str}&currencyCode={currency}"
    
    while url:
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("Items", [])
            all_items.extend(items)
            
            url = data.get("NextPageLink")
            
        except requests.exceptions.RequestException as e:
            print(f"Error querying API: {e}", file=sys.stderr)
            break
    
    # Filter by regions if specified
    if regions:
        regions_lower = [r.lower() for r in regions]
        all_items = [i for i in all_items if i.get("armRegionName", "").lower() in regions_lower]
    
    return all_items


def is_windows_price(item: Dict[str, Any]) -> bool:
    """Check if this is a Windows pricing (has Windows in product name)."""
    product_name = item.get("productName", "").lower()
    return "windows" in product_name


def is_spot_price(item: Dict[str, Any]) -> bool:
    """Check if this is a Spot pricing."""
    return item.get("type", "").lower() == "spot"


def is_reservation_price(item: Dict[str, Any]) -> bool:
    """Check if this is a Reservation pricing."""
    return item.get("type", "").lower() == "reservation"


def get_reservation_term(item: Dict[str, Any]) -> Optional[str]:
    """Get reservation term (1 Year or 3 Years)."""
    return item.get("reservationTerm")


def organize_prices(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Organize prices by region with all price types.
    
    Returns:
        {
            "eastus": {
                "linux_consumption": 2.304,
                "windows_consumption": 3.120,
                "spot": 0.461,
                "reserved_1yr": 1.456,
                "reserved_3yr": 0.982
            },
            ...
        }
    """
    regions = defaultdict(lambda: {
        "linux_consumption": None,
        "windows_consumption": None,
        "spot": None,
        "reserved_1yr": None,
        "reserved_3yr": None,
        "location": None
    })
    
    for item in items:
        region = item.get("armRegionName")
        if not region:
            continue
        
        price = item.get("retailPrice", 0)
        regions[region]["location"] = item.get("location", region)
        
        is_windows = is_windows_price(item)
        is_spot = is_spot_price(item)
        is_reservation = is_reservation_price(item)
        
        if is_spot:
            # Spot pricing (usually Linux-based)
            if not is_windows and (regions[region]["spot"] is None or price < regions[region]["spot"]):
                regions[region]["spot"] = price
        elif is_reservation:
            term = get_reservation_term(item)
            # Only use Linux reservations (Windows reservations are separate)
            if not is_windows:
                if term == "1 Year" and (regions[region]["reserved_1yr"] is None or price < regions[region]["reserved_1yr"]):
                    regions[region]["reserved_1yr"] = price
                elif term == "3 Years" and (regions[region]["reserved_3yr"] is None or price < regions[region]["reserved_3yr"]):
                    regions[region]["reserved_3yr"] = price
        else:
            # Consumption pricing
            if is_windows:
                if regions[region]["windows_consumption"] is None or price < regions[region]["windows_consumption"]:
                    regions[region]["windows_consumption"] = price
            else:
                if regions[region]["linux_consumption"] is None or price < regions[region]["linux_consumption"]:
                    regions[region]["linux_consumption"] = price
    
    return dict(regions)


def format_price(price: Optional[float], currency: str = "$") -> str:
    """Format price for display."""
    if price is None:
        return "N/A"
    return f"{currency}{price:.4f}"


def format_annual(price: Optional[float], currency: str = "$") -> str:
    """Format annual cost for display."""
    if price is None:
        return "N/A"
    annual = price * HOURS_PER_YEAR
    return f"{currency}{annual:,.0f}"


def print_summary_table(regions: Dict[str, Dict], sku: str, currency_symbol: str = "$"):
    """Print the summary table sorted by Linux price."""
    
    # Filter out regions with no Linux price and sort
    valid_regions = [(r, p) for r, p in regions.items() if p["linux_consumption"] is not None]
    sorted_regions = sorted(valid_regions, key=lambda x: x[1]["linux_consumption"])
    
    if not sorted_regions:
        print("No pricing data found for this SKU.")
        return None, None
    
    print(f"\n## Azure VM Pricing: {sku}")
    print(f"\n**All Regions** (sorted by Linux hourly price, ascending)\n")
    
    # Header
    print("| Region | Linux (Win+AHB)/hr | Windows/hr | Spot/hr | 1yr Reserved | 3yr Reserved |")
    print("|--------|-------------------|------------|---------|--------------|--------------|")
    
    for region, prices in sorted_regions:
        linux = format_price(prices["linux_consumption"], currency_symbol)
        windows = format_price(prices["windows_consumption"], currency_symbol)
        spot = format_price(prices["spot"], currency_symbol)
        res_1yr = format_price(prices["reserved_1yr"], currency_symbol)
        res_3yr = format_price(prices["reserved_3yr"], currency_symbol)
        
        print(f"| {region} | {linux} | {windows} | {spot} | {res_1yr} | {res_3yr} |")
    
    print("\n> *Linux and Windows with Azure Hybrid Benefit (AHB) share the same compute price*")
    print("> *Spot prices vary based on demand and VMs can be evicted with 30s notice*")
    
    # Return cheapest and most expensive
    cheapest = sorted_regions[0]
    most_expensive = sorted_regions[-1]
    
    return cheapest, most_expensive


def print_cost_analysis(cheapest: tuple, most_expensive: tuple, currency_symbol: str = "$"):
    """Print the cost analysis section."""
    
    cheapest_region, cheapest_prices = cheapest
    expensive_region, expensive_prices = most_expensive
    
    print(f"\n---\n")
    print(f"## Cost Analysis ({HOURS_PER_YEAR:,} hours/year)\n")
    
    # Cheapest region table
    print(f"### Cheapest Region: {cheapest_region}\n")
    print("| Price Type | Hourly | Annual |")
    print("|------------|--------|--------|")
    
    price_types = [
        ("Linux (Win+AHB)", "linux_consumption"),
        ("Windows", "windows_consumption"),
        ("Spot", "spot"),
        ("1yr Reserved", "reserved_1yr"),
        ("3yr Reserved", "reserved_3yr")
    ]
    
    for label, key in price_types:
        hourly = format_price(cheapest_prices[key], currency_symbol)
        annual = format_annual(cheapest_prices[key], currency_symbol)
        print(f"| {label} | {hourly} | {annual} |")
    
    # Most expensive region table
    print(f"\n### Most Expensive Region: {expensive_region}\n")
    print("| Price Type | Hourly | Annual |")
    print("|------------|--------|--------|")
    
    for label, key in price_types:
        hourly = format_price(expensive_prices[key], currency_symbol)
        annual = format_annual(expensive_prices[key], currency_symbol)
        print(f"| {label} | {hourly} | {annual} |")
    
    # Savings table
    print(f"\n### Annual Savings (Cheapest vs Most Expensive)\n")
    print("| Price Type | Cheapest Annual | Expensive Annual | Savings | % Saved |")
    print("|------------|-----------------|------------------|---------|---------|")
    
    for label, key in price_types:
        cheap_price = cheapest_prices[key]
        exp_price = expensive_prices[key]
        
        if cheap_price is not None and exp_price is not None:
            cheap_annual = cheap_price * HOURS_PER_YEAR
            exp_annual = exp_price * HOURS_PER_YEAR
            savings = exp_annual - cheap_annual
            pct = (savings / exp_annual) * 100 if exp_annual > 0 else 0
            
            print(f"| {label} | {currency_symbol}{cheap_annual:,.0f} | {currency_symbol}{exp_annual:,.0f} | {currency_symbol}{savings:,.0f} | {pct:.1f}% |")
        else:
            print(f"| {label} | N/A | N/A | N/A | N/A |")


def main():
    parser = argparse.ArgumentParser(
        description="Query Azure VM pricing with regional comparison"
    )
    
    parser.add_argument(
        "--sku", "-s",
        required=True,
        help="VM SKU name (e.g., Standard_D48as_v6)"
    )
    parser.add_argument(
        "--currency", "-c",
        default="USD",
        help="Currency code (default: USD)"
    )
    parser.add_argument(
        "--regions", "-r",
        help="Comma-separated list of regions to filter (optional)"
    )
    
    args = parser.parse_args()
    
    # Normalize SKU name
    sku = args.sku
    if not sku.startswith("Standard_"):
        sku = f"Standard_{sku}"
    
    # Parse regions if provided
    regions = None
    if args.regions:
        regions = [r.strip() for r in args.regions.split(",")]
    
    # Currency symbol
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "AUD": "A$",
        "CAD": "C$",
        "CHF": "CHF ",
        "INR": "₹",
        "TRY": "₺"
    }
    currency_symbol = currency_symbols.get(args.currency.upper(), "$")
    
    # Query API
    print(f"Querying Azure pricing for {sku}...", file=sys.stderr)
    items = query_azure_prices(sku, args.currency, regions)
    
    if not items:
        print(f"No pricing data found for SKU: {sku}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(items)} price records", file=sys.stderr)
    
    # Organize by region
    organized = organize_prices(items)
    
    # Print summary table
    result = print_summary_table(organized, sku, currency_symbol)
    
    if result[0] is not None:
        # Print cost analysis
        print_cost_analysis(result[0], result[1], currency_symbol)


if __name__ == "__main__":
    main()
