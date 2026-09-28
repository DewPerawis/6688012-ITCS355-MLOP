# ITCS355 Lab 3 — Serving, Load Testing, and Rollback

Student ID: **6688012** · Provider: **Azure** · Region: **Central India**

This lab serves the versioned model produced by Lab 2 through a provider-neutral FastAPI
application, deploys the same digest-pinned container to an Azure ML managed online
endpoint, measures latency under load, and demonstrates a timestamped canary rollback.

## Evidence status

The production model `itcs355-6688012` version `1` was served from a digest-pinned image on
Azure ML. Service tests, smoke tests, concurrency/batch/payload/instance experiments, and a
timestamped 90/10 canary rollback have been completed. Raw JSON evidence and the measured
analysis are stored under `reports/`. The production endpoint and canary deployment were
deleted after evidence capture, and the automated absence check is recorded in the report.

## Predeclared service objective

Before any endpoint load measurement, the warm-service objective is:

- concurrency: **10 virtual users**
- p95 client-observed end-to-end request latency: **below 250 ms**
- HTTP error rate: **below 1%**
- measurement window: **60 seconds after a 15-second warm-up**

This is a target, not a reported result. Cold-start latency, if observed, is reported
separately and is not removed from the raw evidence.

## API contract

| Route | Contract |
|---|---|
| `POST /predict` | One row; returns probability and model version |
| `POST /predict/batch` | 1–100 rows; returns probabilities and model version |
| `GET /health` | Process liveness only |
| `GET /ready` | 200 only after the versioned model is loaded |

Malformed, missing, out-of-range, or unknown fields are rejected with HTTP 422. The model
is loaded once during application startup. Every response carries `x-request-id` and
`x-model-version`; structured logs include request ID, route, status, latency, and version.

## Intended workflow

Use WSL/Bash from this folder and follow `PLAN.md` one numbered step at a time. Local
tests and the serving-image smoke test come before any billable deployment. The Azure
endpoint is deleted immediately after all evidence is captured, and deletion is checked
again in Azure Portal.

The controller uses the Azure ML SDK only inside `cloudlayer/`. The service itself knows
nothing about Azure: the adapter binds an exact registered model version into the custom
container and provides its mounted path through runtime configuration.

## Submission artifacts

- `service/` — provider-neutral API and pinned serving image
- `cloudlayer/` — Azure deploy, invoke, traffic, and scoped teardown operations
- `loadtest/k6.js` — reproducible single, batch, and payload-size scenarios
- `tests/` — service contract and adapter unit tests
- `reports/lab3-load.md` — predeclared target and measured evidence table

`cloud.env`, credentials, endpoint keys, raw data, local caches, and generated raw logs
must not be committed.
