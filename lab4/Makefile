SHELL := /bin/bash
DOCKER ?= docker
TAG ?= $(shell git rev-parse HEAD)
IMAGE ?= itcs355-lab4-serve
MONITOR_IMAGE ?= itcs355-lab4-monitor
MODEL_PATH ?=
MODEL_VERSION ?= 1
ENDPOINT_CONFIRM ?=

.PHONY: prepare test lint integration image monitor-image local-drift cloud-check inject-drift baseline drift schedule disable-schedule dashboard cleanup-plan teardown cost-report
prepare:
	python -m scripts.prepare
test:
	python -m pytest -q tests
lint:
	python -m ruff check src service monitoring cloudlayer scripts tests
	python -m scripts.portability_audit
image:
	$(DOCKER) buildx build --progress=plain --platform linux/amd64 --build-arg GIT_COMMIT=$(TAG) -f service/Dockerfile.serve -t $(IMAGE):$(TAG) --load .
monitor-image:
	$(DOCKER) buildx build --progress=plain --platform linux/amd64 -f monitoring/Dockerfile.monitor -t $(MONITOR_IMAGE):$(TAG) --load .
integration:
	test -n "$(MODEL_PATH)"
	DOCKER=$(DOCKER) python -m scripts.integration --image $(IMAGE):$(TAG) --model-path "$(MODEL_PATH)" --version $(MODEL_VERSION)
local-drift:
	python -m scripts.local_drift
cloud-check:
	python -m scripts.cloud_ops inspect
dashboard:
	python -m scripts.workbook
baseline:
	python -m scripts.replay --cloud --rows 600
inject-drift:
	python -m scripts.replay --cloud --shift 12 --rows 600
drift:
	python -m scripts.cloud_ops run
schedule:
	python -m scripts.cloud_ops schedule --hours 2
disable-schedule:
	python -m scripts.cloud_ops disable
cleanup-plan:
	python -m scripts.cloud_ops cleanup-plan
teardown:
	test -n "$(ENDPOINT_CONFIRM)"
	python -m scripts.cloud_ops cleanup --confirm-endpoint "$(ENDPOINT_CONFIRM)"
cost-report:
	python -m scripts.cost_report $(ARGS)
