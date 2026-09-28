"""Delete only the configured Lab 3 endpoint after explicit name confirmation."""
from __future__ import annotations

import argparse

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-endpoint", required=True)
    args = parser.parse_args()
    cfg = config.load()
    if args.confirm_endpoint != cfg.online_endpoint:
        raise RuntimeError("confirmation does not exactly match ONLINE_ENDPOINT")
    affected = get_adapter(cfg).teardown(cfg.tags(3))
    for item in affected:
        print(item)
    if not affected:
        print("endpoint already absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
