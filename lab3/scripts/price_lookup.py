"""Capture current Azure Linux VM retail rates for reproducible cost estimates."""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

API_URL = "https://prices.azure.com/api/retail/prices"


def _lookup(sku: str, region: str, currency: str) -> dict[str, Any]:
    query = (
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
        f"and armSkuName eq '{sku}' and priceType eq 'Consumption'"
    )
    params = urllib.parse.urlencode({"currencyCode": f"'{currency}'", "$filter": query})
    with urllib.request.urlopen(f"{API_URL}?{params}", timeout=30) as response:
        payload = json.load(response)
    candidates = [
        item
        for item in payload.get("Items", [])
        if "windows" not in item.get("productName", "").lower()
        and "spot" not in item.get("meterName", "").lower()
        and "low priority" not in item.get("meterName", "").lower()
        and item.get("type") == "Consumption"
        and float(item.get("retailPrice", 0)) > 0
    ]
    if len(candidates) != 1:
        names = [f"{item.get('meterName')}:{item.get('retailPrice')}" for item in candidates]
        raise RuntimeError(f"expected one Linux consumption meter for {sku}, found {names}")
    item = candidates[0]
    return {
        "sku": sku,
        "region": region,
        "currency": item["currencyCode"],
        "hourly_retail_price": item["retailPrice"],
        "unit": item["unitOfMeasure"],
        "meter": item["meterName"],
        "product": item["productName"],
        "effective_start": item["effectiveStartDate"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skus", nargs="+")
    parser.add_argument("--region", default="centralindia")
    parser.add_argument("--currency", default="THB")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = {
        "lookup_at": datetime.now(UTC).isoformat(),
        "source": API_URL,
        "prices": [_lookup(sku, args.region, args.currency) for sku in args.skus],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print("AZURE RETAIL PRICE SUMMARY")
    for price in evidence["prices"]:
        print(
            f"{price['sku']} {price['hourly_retail_price']} {price['currency']}/hour "
            f"meter={price['meter']} effective={price['effective_start']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
