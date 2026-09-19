"""Cost model for Lab 2.

Rates are explicit measured inputs, not hidden constants. The Azure rate used by this
submission was checked against the Azure Retail Prices API in THB on 2026-09-19 for
Central India. It is the Linux on-demand rate selected after the Azure for Students
subscription reported zero low-priority quota in nearby regions. Retail prices and billed
cost can change, so the report must retain the check date and compare the estimate with
Cost Management after the job settles.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriceEvidence:
    provider: str
    region: str
    instance: str
    hourly_thb: float
    meter: str
    checked_on: str
    source: str


VERIFIED_PRICE = PriceEvidence(
    provider="azure",
    region="centralindia",
    instance="Standard_DS2_v2-dedicated",
    hourly_thb=5.558,
    meter="DS2 v2 (Linux Consumption)",
    checked_on="2026-09-19",
    source="Azure Retail Prices API",
)


PRICE_TABLE: dict[str, dict[str, float]] = {
    "local": {"local": 0.0},
    "azure": {
        VERIFIED_PRICE.instance: VERIFIED_PRICE.hourly_thb,
    },
}


def hourly_rate(provider: str, instance: str) -> float:
    table = PRICE_TABLE.get(provider.lower())
    if table is None:
        raise KeyError(f"No price table for provider {provider!r}.")
    if instance not in table:
        raise KeyError(
            f"No verified rate for {instance!r} on {provider}. Known: {sorted(table)}. "
            "Verify the exact meter and region; do not silently substitute a similar SKU."
        )
    return table[instance]
