#!/usr/bin/env bash
# Local-only preparation and checks. Does not create cloud resources or publish Git.
set -euo pipefail
cd "$(dirname "$0")"
if [[ -z "${LAB4_PYTHON:-}" ]]; then
  if [[ -f "$HOME/yes/etc/profile.d/conda.sh" ]]; then
    source "$HOME/yes/etc/profile.d/conda.sh"
    conda activate itcs355-lab3
  fi
  LAB4_PYTHON=python
fi
if ! command -v docker >/dev/null 2>&1 && command -v docker.exe >/dev/null 2>&1; then
  export DOCKER=docker.exe
fi
echo '1/6: read-only prerequisites'
"$LAB4_PYTHON" -m scripts.preflight
echo '2/6: generate deterministic local fixtures'
"$LAB4_PYTHON" -m scripts.prepare
echo '3/6: lint and provider boundary'
"$LAB4_PYTHON" -m ruff check src service monitoring cloudlayer scripts tests
"$LAB4_PYTHON" -m scripts.portability_audit
echo '4/6: unit, data, model, service and monitoring tests'
"$LAB4_PYTHON" -m pytest -q tests
echo '5/6: deliberate local data-contract failure and exact restoration'
"$LAB4_PYTHON" -m scripts.contract_rehearsal
echo '6/6: baseline versus injected drift rehearsal'
"$LAB4_PYTHON" -m scripts.local_drift
echo 'Local checks completed. Next read START_HERE_TH.md for GitHub/Azure evidence.'
