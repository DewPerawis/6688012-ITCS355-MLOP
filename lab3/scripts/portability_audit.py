"""Fail when provider-specific implementation leaks outside cloudlayer/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("src", "service", "tests")
FORBIDDEN = (
    (r"\bfrom azure\b|\bimport azure\b", "Azure SDK"),
    (r"azurecr\.io|blob\.core\.windows\.net", "Azure hostname"),
    (r"\bimport boto3\b|amazonaws\.com", "AWS detail"),
    (r"\bfrom google\.cloud\b|googleapis\.com", "GCP detail"),
    (r"[A-Za-z]:\\Users\\|/home/[^/]+/", "developer path"),
)


def main() -> int:
    hits: list[str] = []
    for folder in SCANNED:
        for path in (ROOT / folder).rglob("*.py"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                for pattern, label in FORBIDDEN:
                    if re.search(pattern, line):
                        hits.append(f"{path.relative_to(ROOT)}:{line_number}: {label}")
    if hits:
        print("PORTABILITY AUDIT FAILED")
        print("\n".join(hits))
        return 1
    print("PORTABILITY AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
