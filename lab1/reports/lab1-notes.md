# Lab 1 Evidence Notes

## 2026-09-13 — Verified setup and data

- Cloud capability check: 11/11 passed
- Dataset seed: 20260101
- Dataset: 6,000 rows, 240 machines
- Positive rate: 0.117
- Data tests: 10 passed
- Portability audit: passed
- Full test suite: 32 passed, 1 Lab 4 latency test failed
- Latency repeats: 3/3 failed at approximately 63–65 ms against the temporary 50 ms threshold
- Dependency lock commit: 10fdacf

## 2026-09-13 — Reproducible container run

- DVC data version: `1c886b512c8a5c9bf723da1cd119fc80.dir`
- Data fingerprint: `422cccb9136e8140`
- Git commit: `dcbd69e06e48f38ee370b8aa13bfa81d0510c87e`
- Seed: `20260101`
- Validation ROC AUC: `0.8363728276105056`
- Validation PR AUC: `0.3963091530665979`
- Test ROC AUC: `0.8482378548603715`
- Test PR AUC: `0.4776221420444084`
- `make reproduce`: passed
- `make verify`: passed within tolerance
- MLflow named-volume artifact check: 10 files, passed
- Runtime: `linux/amd64`, non-root UID 10001
- The first two container attempts exposed write/metadata limitations on a Windows bind mount. The final run stores MLflow artifacts in Docker named volume `itcs355-lab1-mlflow`, while the tracking database and metrics remain under `reports/`.

## 2026-09-13 — Azure adapter

- Blob upload/download round trip: passed; SHA-256 `265b6fd6e69fd45e65b6e49efb32f0302c7847fe55e69e1a075f48200fe8e9b9`
- Blob object: `itcs355/itcs355/adapter-probes/roundtrip-6688012.txt`
- Adapter implementation commit/tag: `b4b1a18`
- The first ACR upload attempt received a transient HTTP 502 during a layer PUT. A health check/login and direct retry resumed the upload successfully.
- ACR repository/tag: `itcs355:b4b1a18`
- ACR digest: `sha256:14a7cce1ba697aaf9961a06dde8abb4f809e3ec5b5e8ca256d0c2abc5877698f`
- Adapter returned the same digest-pinned image reference; exit code 0.
