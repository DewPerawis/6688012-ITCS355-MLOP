"""Download actual Azure ML pipeline/child artifacts and locate drift evidence."""
import argparse
import json
from pathlib import Path

from cloudlayer.factory import get_adapter
from src import config

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, help="pipeline run name from Azure ML Studio")
    args = parser.parse_args()
    client = get_adapter(config.load())._ml_client()
    job = client.jobs.get(args.job)
    children = list(client.jobs.list(parent_job_name=args.job))
    jobs = children or [job]
    destination = Path("reports/cloud-jobs") / args.job
    destination.mkdir(parents=True, exist_ok=True)
    for item in jobs:
        print(f"job={item.name} status={item.status}", flush=True)
        client.jobs.download(item.name, download_path=str(destination / item.name), all=True)
    files = list(destination.rglob("drift.json"))
    print(json.dumps({"pipeline": args.job, "status": job.status,
                      "drift_files": [str(file) for file in files]}, indent=2))
    if not files:
        raise SystemExit("No drift output yet; inspect the child job logs and verify it completed")
