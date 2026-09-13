# ITCS355 Lab 1
# `make reproduce` is the one command a grader runs. Keep it working.

SHELL := /bin/bash
IMAGE ?= itcs355-lab1
TAG   ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
PLATFORM ?= linux/amd64
SEED ?= 20260101
DATA_SEED ?= 20260101
GIT_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
MLFLOW_VOLUME ?= itcs355-lab1-mlflow
REPRODUCE_VOLUME ?= itcs355-lab1-reproduce
N_ESTIMATORS ?= 100
MAX_DEPTH ?= 8
MIN_SAMPLES_LEAF ?= 5

.PHONY: help setup cloud-check data test portability-audit train image image-push reproduce experiments verify clean teardown \
        tune compare reload-check serve serve-image loadtest drift inject-drift pipeline cost swap-check llm-eval llm-gate

help:
	@grep -E "^[a-zA-Z_-]+:.*?## .*$$" $(MAKEFILE_LIST) | awk -F":.*?## " "{printf \"  %-20s %s\\n\", \$$1, \$$2}"

setup: ## Install dependencies and print environment status
	python -m pip install --upgrade pip
	python -m pip install --require-hashes -r requirements.txt
	@echo "environment ok"

cloud-check: ## Resolve the eight capability slots
	python scripts/cloud_check.py

data: ## Generate the default dataset (deterministic)
	python scripts/make_dataset.py --seed $(DATA_SEED)

test: ## Run data contract and split property tests
	pytest -q tests/test_data.py

portability-audit: ## Fail if provider strings leak into src/
	python scripts/portability_audit.py

train: ## Train locally, outside the container
	PYTHONHASHSEED=$(SEED) GIT_COMMIT=$(GIT_COMMIT) python -m src.train \
	  --n-estimators $(N_ESTIMATORS) --max-depth $(MAX_DEPTH) \
	  --min-samples-leaf $(MIN_SAMPLES_LEAF) --seed $(SEED) \
	  --metrics-out reports/metrics.json

image: ## Build the training image for linux/amd64
	docker buildx build --progress=plain --platform $(PLATFORM) \
	  --build-arg GIT_COMMIT=$(GIT_COMMIT) -t $(IMAGE):$(TAG) --load .

image-push: image ## Push to CONTAINER_REGISTRY via your adapter
	python -c "from src import config; from cloudlayer.factory import get_adapter; \
	print(get_adapter(config.load()).push_image(\"$(IMAGE):$(TAG)\"))"

reproduce: image ## THE ONE COMMAND. Grader runs this.
	mkdir -p reports
	docker run --rm \
	  -w /app/reports \
	  -v "$(REPRODUCE_VOLUME):/app/reports" \
	  -e GIT_COMMIT=$(GIT_COMMIT) \
	  -e PYTHONHASHSEED=$(SEED) \
	  -e MLFLOW_TRACKING_URI=sqlite:////app/reports/mlflow.db \
	  --entrypoint /bin/sh $(IMAGE):$(TAG) -c '\
	  python /app/scripts/make_dataset.py --seed $(DATA_SEED) \
	    --out /app/data/raw/sensors.csv && \
	  python -m src.train --n-estimators $(N_ESTIMATORS) --max-depth $(MAX_DEPTH) \
	    --min-samples-leaf $(MIN_SAMPLES_LEAF) --seed $(SEED) \
	    --run-name reproduce-fewer-trees --metrics-out /app/reports/metrics.json'
	docker run --rm \
	  -v "$(REPRODUCE_VOLUME):/app/reports:ro" \
	  --entrypoint /bin/cat $(IMAGE):$(TAG) \
	  /app/reports/metrics.json > reports/metrics.json

experiments: image ## Run the declared five-run Lab 1 MLflow matrix
	IMAGE_REF="$(IMAGE):$(TAG)" GIT_COMMIT="$(GIT_COMMIT)" SEED="$(SEED)" \
	  MLFLOW_VOLUME="$(MLFLOW_VOLUME)" bash scripts/run_experiments.sh

verify: ## Check the produced metric against the README claim
	python scripts/verify_metric.py

teardown: ## Delete every resource tagged course=itcs355 for this lab
	python -c "from src import config; from cloudlayer.factory import get_adapter; \
	cfg=config.load(); print(get_adapter(cfg).teardown(cfg.tags(1)))"

clean: ## Remove local artifacts
	rm -rf mlruns mlartifacts mlflow.db reports/metrics.json .pytest_cache

# --- Lab 2 -------------------------------------------------------------------
tune: ## Budgeted hyperparameter study (>=12 trials)
	python -m src.tune --trials 12 --budget-thb 150

compare: ## Rank runs by metric and by cost per point
	python scripts/compare_runs.py --experiment itcs355-lab2

reload-check: ## Load the registered model by version and score rows
	python scripts/reload_check.py --name $(MODEL_REGISTRY_NAME) --version $(VERSION)

# --- Lab 3 -------------------------------------------------------------------
serve: ## Run the inference service locally on :8080
	python scripts/export_model.py --out reports/model.joblib
	MODEL_PATH=reports/model.joblib MODEL_VERSION=local uvicorn service.app:app --port 8080

serve-image: ## Build the serving image
	docker buildx build --platform $(PLATFORM) -f service/Dockerfile.serve -t itcs355-serve:$(TAG) --load .

loadtest: ## Load test at three concurrency levels
	@for vus in 1 10 50; do \
	  echo "=== $$vus VUs ==="; \
	  k6 run -e TARGET=$(TARGET) -e VUS=$$vus loadtest/k6.js || true; \
	done

# --- Lab 4 -------------------------------------------------------------------
inject-drift: ## Shift a feature's distribution on purpose
	python scripts/inject_drift.py --feature temp_c --mode shift --magnitude 6

drift: ## Score drift against the reference window
	python -m monitoring.drift --current data/current.csv

# --- Lab 5 -------------------------------------------------------------------
pipeline: ## Compile pipeline/pipeline.yaml for your provider
	python -c "from cloudlayer.pipelines import compile_for; from src import config; \
	compile_for(config.load().provider)"

llm-eval: ## Run the LLM golden set against recorded responses (offline, free)
	python scripts/llm_eval.py --out reports/llm_eval-baseline.json

llm-gate: ## Prove the gate fails on a degraded set — expected to exit non-zero
	python scripts/llm_eval.py --out reports/llm_eval-baseline.json >/dev/null
	python scripts/llm_eval.py --responses evals/fixtures/triage-regressed.jsonl \
	  --out reports/llm_eval.json --baseline reports/llm_eval-baseline.json

cost: ## Build the cost report
	python scripts/cost_report.py --estimate $(EST) --actual $(ACT) --rps $(RPS) --instance $(INSTANCE)

swap-check: ## Prove the portability seam against a second provider
	python scripts/portability_swap_check.py --second-provider $(SECOND)
