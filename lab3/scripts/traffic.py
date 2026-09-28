"""Apply a traffic split and append timestamped rollback evidence."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config


def _allocation(value: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for part in value.split(","):
        name, separator, percent = part.partition("=")
        if not separator:
            raise argparse.ArgumentTypeError("use deployment=percent,deployment=percent")
        try:
            result[name.strip()] = int(percent)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("traffic percentages must be integers") from exc
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allocation", type=_allocation, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/lab3-traffic.json"))
    args = parser.parse_args()
    cfg = config.load()
    observed = get_adapter(cfg).set_traffic(cfg.online_endpoint, args.allocation)
    record = {
        "observed_at": datetime.now(UTC).isoformat(),
        "endpoint": cfg.online_endpoint,
        "traffic": observed,
    }
    history: list[dict] = []
    if args.out.exists():
        history = json.loads(args.out.read_text(encoding="utf-8"))
    history.append(record)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
