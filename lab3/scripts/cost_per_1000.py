"""Calculate serving cost from an explicit rate, throughput, and utilisation assumption."""
from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hourly-thb", type=float, required=True)
    parser.add_argument("--predictions-per-second", type=float, required=True)
    parser.add_argument("--utilisation", type=float, required=True)
    args = parser.parse_args()
    if args.hourly_thb <= 0 or args.predictions_per_second <= 0:
        raise ValueError("hourly rate and throughput must be positive")
    if not 0 < args.utilisation <= 1:
        raise ValueError("utilisation must be in (0, 1]")
    cost = (
        args.hourly_thb
        / (args.predictions_per_second * 3600 * args.utilisation)
        * 1000
    )
    print(
        json.dumps(
            {
                "hourly_thb": args.hourly_thb,
                "predictions_per_second": args.predictions_per_second,
                "utilisation": args.utilisation,
                "thb_per_1000_predictions": cost,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
