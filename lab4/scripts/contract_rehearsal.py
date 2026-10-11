"""Prove the named schema test fails locally, restoring the generated CSV afterwards."""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

if __name__ == "__main__":
    path = Path("data/raw/sensors.csv")
    original = path.read_bytes()
    try:
        pd.read_csv(path).drop(columns=["temp_c"]).to_csv(path, index=False)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q",
                                 "tests/test_data_contracts.py::test_training_schema_contract"],
                                capture_output=True, text=True)
        assert result.returncode == 1, "expected a test assertion failure"
        assert "training schema mismatch" in result.stdout
        Path("reports/local-contract-failure.json").write_text(json.dumps({
            "evidence_type": "local rehearsal; actual failing GitHub run is still required",
            "test": "test_training_schema_contract", "exit_code": result.returncode,
            "output": result.stdout}, indent=2), encoding="utf-8")
        print("PASS: deliberately missing temp_c was rejected by the named contract test")
    finally:
        path.write_bytes(original)
    assert path.read_bytes() == original
    print("Restored the generated CSV byte-for-byte")
