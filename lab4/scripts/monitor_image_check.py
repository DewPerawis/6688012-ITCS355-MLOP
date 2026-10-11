"""Check the actual monitor image's dependency integrity and Azure MLflow registration."""
import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    docker = os.getenv("DOCKER", "docker")
    code = ("import os, json, importlib.metadata as m; "
            "import numpy, pandas, mlflow, azure.identity, azureml.mlflow; "
            "entries=[e for e in m.entry_points(group='mlflow.tracking_store') if e.name=='azureml']; "
            "assert entries; entries[0].load(); "
            "assert os.getuid() == 10001; "
            "print(json.dumps({'uid':os.getuid(),'mlflow':m.version('mlflow'),"
            "'azureml_mlflow':m.version('azureml-mlflow'),'azureml_tracking_registered':True}))")
    subprocess.run([docker, "run", "--rm", args.image, "python", "-m", "pip", "check"], check=True)
    result = subprocess.check_output([docker, "run", "--rm", args.image, "python", "-c", code], text=True)
    evidence = {"image": args.image, "status": "passed", "checked_at": datetime.now(UTC).isoformat(),
                "runtime": json.loads(result), "scope": "local dependency/runtime check; no cloud job submitted"}
    Path("reports/monitor-image-check.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
