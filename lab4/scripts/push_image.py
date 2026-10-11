"""Push one SHA-tagged image and expose only its digest to subsequent CI steps."""
import argparse
import json
from dataclasses import replace
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--monitor", action="store_true", help="use a separate monitor image repository")
    args = parser.parse_args()
    cfg = config.load()
    if args.monitor:
        cfg = replace(cfg, container_registry=cfg.container_registry + "-monitor")
    digest = get_adapter(cfg).push_image(args.tag)
    Path("reports").mkdir(exist_ok=True)
    report = "monitor-image-push.json" if args.monitor else "image-push.json"
    Path("reports", report).write_text(json.dumps({"tag": args.tag, "digest": digest},
                                                       indent=2), encoding="utf-8")
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as handle:
            key = "MONITOR_IMAGE_URI" if args.monitor else "SERVING_IMAGE_URI"
            handle.write(f"{key}={digest}\n")
    print(digest)
