"""Start the built container, check the real HTTP contract, then stop it."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VALID = {"temp_c": 78.4, "vibration_mm_s": 3.1, "pressure_kpa": 315.2,
         "hours_since_service": 4200, "load_pct": 68, "ambient_humidity": 55}


def request(base: str, route: str, payload: dict | None = None) -> tuple[int, dict]:
    req = Request(base + route, data=json.dumps(payload).encode() if payload else None,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--port", type=int, default=18084)
    parser.add_argument("--out", type=Path, default=Path("reports/container-integration.json"))
    args = parser.parse_args()
    if not (args.model_path / "MLmodel").is_file():
        parser.error("--model-path must contain MLmodel")
    docker = os.environ.get("DOCKER", "docker")
    name = "itcs355-lab4-check-" + uuid.uuid4().hex[:8]
    mount = str(args.model_path.resolve())
    if docker.endswith(".exe") and os.name != "nt":
        mount = subprocess.check_output(["wslpath", "-w", mount], text=True).strip()
    base = f"http://127.0.0.1:{args.port}"
    passed = []
    try:
        subprocess.run([docker, "run", "-d", "--rm", "--name", name,
                        "-p", f"127.0.0.1:{args.port}:8080", "--mount",
                        f"type=bind,source={mount},target=/model,readonly",
                        "-e", "MODEL_PATH=/model", "-e", f"MODEL_VERSION={args.version}",
                        args.image], check=True)
        for _ in range(90):
            try:
                status, ready = request(base, "/ready")
                if status == 200:
                    assert ready["model_version"] == args.version
                    break
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError("container did not become ready within 180 seconds")
        passed.append("ready and exact model version")
        status, prediction = request(base, "/predict", VALID)
        assert status == 200 and set(prediction) == {"probability", "model_version"}
        assert 0 <= prediction["probability"] <= 1
        assert prediction["model_version"] == args.version
        passed.append("single prediction schema, probability, version")
        status, batch = request(base, "/predict/batch", {"rows": [VALID] * 3})
        assert status == 200 and len(batch["probabilities"]) == 3
        assert batch["model_version"] == args.version
        passed.append("batch prediction")
        assert request(base, "/predict", {**VALID, "temp_c": 999})[0] == 422
        assert request(base, "/predict/batch", {"rows": [VALID] * 101})[0] == 422
        passed.append("422 data contract and batch limit")
        state = request(base, "/observability")[1]
        assert state["request_count"] == 4 and state["4xx_fraction"] == 0.5
        assert state["latency_ms"]["p95"] > 0 and state["feature_rows"] == 4
        passed.append("actual rolling request/error/latency/feature signals")
        user = subprocess.check_output([docker, "exec", name, "id", "-u"], text=True).strip()
        assert user == "10001"
        passed.append("non-root uid 10001")
        from datetime import UTC, datetime

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"status": "passed", "image": args.image,
            "model_version": args.version, "checks": passed, "observability": state,
            "checked_at": datetime.now(UTC).isoformat()}, indent=2), encoding="utf-8")
        print(f"PASS {len(passed)} container checks; evidence={args.out}")
    finally:
        subprocess.run([docker, "logs", "--tail", "10", name], check=False)
        subprocess.run([docker, "stop", name], check=False)


if __name__ == "__main__":
    main()
