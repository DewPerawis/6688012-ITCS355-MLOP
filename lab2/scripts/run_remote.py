"""Upload versioned data and run/resume the Lab 2 study on managed compute."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.azure import _blob_location
from cloudlayer.factory import get_adapter
from src import config, seeds
from src.train import dvc_data_version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--image-uri", required=True, help="digest-pinned ACR image reference")
    p.add_argument("--study-id", required=True, help="reuse this ID to resume a study")
    p.add_argument("--trials", type=int, default=12)
    p.add_argument("--budget-thb", type=float, default=150.0)
    p.add_argument("--seed-repeats", type=int, default=5)
    p.add_argument("--interrupt-after", type=int, default=0)
    p.add_argument("--experiment", default="itcs355-lab2")
    return p.parse_args()


def git_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def main() -> int:
    args = parse_args()
    cfg = config.load()
    adapter = get_adapter(cfg)
    raw_path = cfg.raw_path
    if not raw_path.is_file():
        raise FileNotFoundError(f"{raw_path} is absent; run `make data` or `dvc pull`")

    data_uri = adapter.upload(raw_path.as_posix(), "lab2/data/sensors.csv")
    _, _, prefix = _blob_location(cfg.blob_uri)
    output_parts = [part for part in (prefix, "lab2", "studies", args.study_id) if part]
    output_uri = "azureml://datastores/itcs355blob/paths/" + "/".join(output_parts)
    revision = git_revision(config.REPO_ROOT)
    data_version = dvc_data_version(cfg.data_dir / "raw.dvc")

    job_id = adapter.submit_training(
        args.image_uri,
        {
            "study_id": args.study_id,
            "experiment": args.experiment,
            "data_uri": data_uri,
            "output_uri": output_uri,
            "data_version": data_version,
            "git_commit": revision,
            "seed": seeds.DEFAULT_SEED,
            "trials": args.trials,
            "budget_thb": args.budget_thb,
            "seed_repeats": args.seed_repeats,
            "interrupt_after": args.interrupt_after,
        },
    )
    submitted_at = datetime.now(timezone.utc).isoformat()
    print(f"submitted Azure ML job {job_id}")
    result = adapter.wait_training(job_id)

    report_path = cfg.reports_dir / "lab2-jobs.json"
    history = json.loads(report_path.read_text()) if report_path.exists() else []
    history.append({
        "study_id": args.study_id,
        "job_id": job_id,
        "submitted_at": submitted_at,
        "interrupt_after": args.interrupt_after,
        "image_digest": args.image_uri.split("@", 1)[-1],
        "data_version": data_version,
        **result,
    })
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(history, indent=2, sort_keys=True))
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"wrote {report_path}")
    return 0 if result["status"] == "Completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
