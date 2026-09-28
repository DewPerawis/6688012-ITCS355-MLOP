# ITCS355 Lab 3 — run from WSL/Bash, one PLAN.md step at a time.
SHELL := /bin/bash
DOCKER ?= docker.exe
IMAGE ?= itcs355-lab3-serve
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
GIT_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
PLATFORM ?= linux/amd64
K6_IMAGE ?= grafana/k6:1.7.1@sha256:4fd3a694926b064d3491d9b02b01cde886583c4931f1223816e3d9a7bdfa7e0f
TARGET ?=
VUS ?= 10
DURATION ?= 60s
WARMUP ?= 15s
MODE ?= single
BATCH_SIZE ?= 100
PADDING_BYTES ?= 0
K6_OUT ?=
CANARY_VERSION ?=
CANARY_INSTANCE ?= Standard_DS1_v2
ENDPOINT_CONFIRM ?=
MODEL_VERSION ?= 1

.PHONY: help lock setup data test lint portability-audit cloud-check download-model \
        serve image run-container image-push deploy smoke register-canary deploy-canary loadtest \
        k6-version load-summary payload100-and-summary instance-experiment canary-probe traffic-canary \
        canary-local-check canary-experiment rollback cost teardown clean

help:
	@grep -E "^[a-zA-Z_-]+:.*?## .*$$" $(MAKEFILE_LIST) | awk -F":.*?## " '{printf "  %-20s %s\n", $$1, $$2}'

lock: ## Compile the hashed dependency lock (run once in the Lab 3 environment)
	env -u PIP_NO_INDEX -u PIP_EXTRA_INDEX_URL PIP_CONFIG_FILE=/dev/null \
	  CUSTOM_COMPILE_COMMAND="make lock" \
	  PIP_INDEX_URL=https://pypi.org/simple \
	  pip-compile --no-config --verbose --index-url https://pypi.org/simple \
	  --emit-index-url --generate-hashes requirements.in -o requirements.txt
	env -u PIP_NO_INDEX -u PIP_EXTRA_INDEX_URL PIP_CONFIG_FILE=/dev/null \
	  CUSTOM_COMPILE_COMMAND="make lock" \
	  PIP_INDEX_URL=https://pypi.org/simple \
	  pip-compile --no-config --verbose --index-url https://pypi.org/simple \
	  --emit-index-url --generate-hashes requirements-serve.in -o requirements-serve.txt

setup: ## Install only artifacts matching the committed hashes
	test -f requirements.txt -a -f requirements-serve.txt || (echo "run make lock first" && exit 2)
	env -u PIP_NO_INDEX -u PIP_EXTRA_INDEX_URL PIP_CONFIG_FILE=/dev/null \
	  python -m pip install --progress-bar on --index-url https://pypi.org/simple \
	  --require-hashes -r requirements.txt
	python -m pip check

data: ## Regenerate the deterministic Lab 2 dataset locally
	python -m scripts.make_dataset

test: ## Run Lab 3 unit and contract tests
	pytest -q tests

lint: ## Check source quality
	python -m ruff check src service cloudlayer scripts tests
	python -m compileall -q src service cloudlayer scripts tests

portability-audit: ## Ensure provider code stays in cloudlayer
	python -m scripts.portability_audit

cloud-check: ## Verify non-secret local/cloud prerequisites
	python -m scripts.cloud_check

download-model: ## Download exact registered MODEL_VERSION for local smoke only
	python -m scripts.download_model

serve: ## Run locally; set MODEL_PATH to the downloaded MLflow model directory
	test -n "$(MODEL_PATH)" || (echo "set MODEL_PATH=<downloaded model path>" && exit 2)
	MODEL_PATH="$(MODEL_PATH)" MODEL_VERSION="$(MODEL_VERSION)" \
	  uvicorn service.app:app --host 127.0.0.1 --port 8080

image: ## Build a non-root linux/amd64 serving image
	$(DOCKER) buildx build --progress=plain --platform $(PLATFORM) \
	  --build-arg GIT_COMMIT=$(GIT_COMMIT) -f service/Dockerfile.serve \
	  -t $(IMAGE):$(TAG) --load .

run-container: ## Run the built image locally with the downloaded model mounted read-only
	test -n "$(MODEL_PATH)" || (echo "set MODEL_PATH=<downloaded model path>" && exit 2)
	test -d "$(MODEL_PATH)" || (echo "MODEL_PATH is not a directory: $(MODEL_PATH)" && exit 2)
	MODEL_HOST_PATH="$$(wslpath -w "$(MODEL_PATH)")"; \
	  $(DOCKER) run --rm --name itcs355-lab3-local -p 8080:8080 \
	  --mount "type=bind,source=$$MODEL_HOST_PATH,target=/model,readonly" \
	  -e MODEL_PATH=/model -e MODEL_VERSION=$(MODEL_VERSION) \
	  $(IMAGE):$(TAG)

image-push: image ## Push the serving image and print an immutable digest reference
	DOCKER=$(DOCKER) python -c 'from src import config; from cloudlayer.factory import get_adapter; cfg=config.load(); print(get_adapter(cfg).push_image("$(IMAGE):$(TAG)"))'

deploy: ## BILLABLE: deploy MODEL_VERSION as DEPLOYMENT_NAME
	python -m scripts.deploy

smoke: ## Invoke three known rows through the managed endpoint
	python -m scripts.smoke

register-canary: ## Register the prechecked weaker Lab 2 run as another exact version
	python -m scripts.register_canary

deploy-canary: ## BILLABLE: deploy CANARY_VERSION as green with zero initial traffic
	test -n "$(CANARY_VERSION)" || (echo "set CANARY_VERSION=<registered version>" && exit 2)
	DEPLOYMENT_NAME=green MODEL_VERSION=$(CANARY_VERSION) python -m scripts.deploy --model-version $(CANARY_VERSION)

k6-version: ## Show the pinned k6 version using the official Docker image
	$(DOCKER) run --rm $(K6_IMAGE) version

loadtest: ## Run one measured k6 scenario in Docker; secrets stay in shell env
	test -n "$(TARGET)" || (echo "set TARGET=<endpoint scoring URI>" && exit 2)
	test -n "$$ENDPOINT_KEY" || (echo "export ENDPOINT_KEY in this shell" && exit 2)
	@WORKSPACE_HOST="$$(wslpath -w "$$(pwd)")"; \
	  $(DOCKER) run --rm \
	  --mount "type=bind,source=$$WORKSPACE_HOST,target=/work" -w /work \
	  -e TARGET="$(TARGET)" -e ENDPOINT_KEY="$$ENDPOINT_KEY" \
	  -e VUS=$(VUS) -e DURATION=$(DURATION) \
	  -e WARMUP=$(WARMUP) -e MODE=$(MODE) -e BATCH_SIZE=$(BATCH_SIZE) \
	  -e PADDING_BYTES=$(PADDING_BYTES) $(K6_IMAGE) run \
	  $(if $(K6_OUT),--summary-export "/work/$(K6_OUT)",) /work/loadtest/k6.js

load-summary: ## Print one compact table from all completed 60-second load tests
	python -m scripts.summarize_loadtests

payload100-and-summary: ## Run the 100 KB payload test, then summarize all load evidence
	@set +e; \
	  $(MAKE) loadtest TARGET="$(TARGET)" VUS=1 WARMUP=15s DURATION=60s \
	    MODE=single PADDING_BYTES=100000 K6_OUT=reports/k6-payload-100kb.json; \
	  test_rc=$$?; \
	  $(MAKE) load-summary; summary_rc=$$?; \
	  if [ $$summary_rc -ne 0 ]; then exit $$summary_rc; fi; \
	  exit $$test_rc

instance-experiment: ## BILLABLE: compare DS3 at 10 VUs, always restoring DS2 afterward
	@set -eu; \
	  test -n "$(TARGET)" || (echo "set TARGET=<endpoint scoring URI>" && exit 2); \
	  test -n "$$ENDPOINT_KEY" || (echo "export ENDPOINT_KEY in this shell" && exit 2); \
	  python -m scripts.price_lookup --currency THB \
	    --out reports/azure-vm-prices.json Standard_DS2_v2 Standard_DS3_v2; \
	  restore_needed=1; \
	  restore() { \
	    if [ $$restore_needed -eq 1 ]; then \
	      echo "RESTORE: returning deployment to Standard_DS2_v2"; \
	      python -m scripts.deploy --instance Standard_DS2_v2 \
	        --out reports/lab3-deployment-restored.json || true; \
	    fi; \
	  }; \
	  trap restore EXIT; trap 'exit 130' INT TERM; \
	  python -m scripts.deploy --instance Standard_DS3_v2 \
	    --out reports/lab3-deployment-ds3.json; \
	  python -m scripts.smoke; \
	  load_rc=0; \
	  $(MAKE) loadtest TARGET="$(TARGET)" VUS=10 WARMUP=15s DURATION=60s \
	    MODE=single PADDING_BYTES=0 K6_OUT=reports/k6-vus10-ds3.json || load_rc=$$?; \
	  python -m scripts.deploy --instance Standard_DS2_v2 \
	    --out reports/lab3-deployment-restored.json; \
	  restore_needed=0; trap - EXIT INT TERM; \
	  python -m scripts.smoke; \
	  $(MAKE) load-summary; \
	  exit $$load_rc

traffic-canary: ## Set verified 90/10 live traffic
	python -m scripts.traffic --allocation blue=90,green=10

canary-probe: ## Replay validation rows through live traffic until degradation is detected
	python -m scripts.canary_probe

rollback: ## Return all traffic to blue and record the observed timestamp
	python -m scripts.traffic --allocation blue=100,green=0

canary-local-check: ## Read-only: download and load the registered canary locally
	python -m scripts.verify_canary_local

canary-experiment: ## BILLABLE: run canary detection, always rollback and delete green
	@set -eu; rollback_needed=0; cleanup_needed=0; \
	  $(MAKE) test; $(MAKE) lint; $(MAKE) portability-audit; \
	  safeguard() { \
	    if [ $$rollback_needed -eq 1 ]; then \
	      echo "SAFEGUARD: rolling traffic back to blue=100"; \
	      python -m scripts.traffic --allocation blue=100,green=0 || true; \
	    fi; \
	    if [ $$cleanup_needed -eq 1 ]; then \
	      echo "SAFEGUARD: deleting green deployment"; \
	      python -m scripts.cleanup_canary || true; \
	    fi; \
	  }; \
	  trap safeguard EXIT; trap 'exit 130' INT TERM; \
	  if [ -f reports/lab3-canary-model.json ]; then \
	    echo "REUSE: previously registered canary model evidence"; \
	  else \
	    python -m scripts.register_canary; \
	  fi; \
	  canary_version="$$(python -c 'import json; print(json.load(open("reports/lab3-canary-model.json"))["version"])')"; \
	  test -n "$$canary_version"; cleanup_needed=1; \
	  DEPLOYMENT_NAME=green MODEL_VERSION="$$canary_version" \
	    python -m scripts.deploy --model-version "$$canary_version" \
	    --instance "$(CANARY_INSTANCE)" \
	    --out reports/lab3-deployment-green.json; \
	  python -m scripts.traffic --allocation blue=100,green=0; \
	  DEPLOYMENT_NAME=green MODEL_VERSION="$$canary_version" \
	    python -m scripts.smoke --deployment green; \
	  python -m scripts.traffic --allocation blue=90,green=10; rollback_needed=1; \
	  probe_rc=0; python -m scripts.canary_probe || probe_rc=$$?; \
	  python -m scripts.traffic --allocation blue=100,green=0; rollback_needed=0; \
	  python -m scripts.cleanup_canary; cleanup_needed=0; \
	  trap - EXIT INT TERM; \
	  python -m scripts.summarize_canary --probe-exit "$$probe_rc"

cost: ## Calculate THB/1,000; pass ARGS with measured values
	python -m scripts.cost_per_1000 $(ARGS)

teardown: ## DESTRUCTIVE: delete exact Lab 3 endpoint after name confirmation
	test -n "$(ENDPOINT_CONFIRM)" || (echo "set ENDPOINT_CONFIRM=<exact endpoint>" && exit 2)
	python -m scripts.teardown --confirm-endpoint "$(ENDPOINT_CONFIRM)"

clean: ## Remove only local caches; preserves reports and cloud resources
	rm -rf .pytest_cache .ruff_cache **/__pycache__
