# ITCS355 Lab 1 — Reproducible Training

> **Course materials live in [`course/`](course/README.md)** — syllabus, slides, the faculty
> specification, all five lab handouts, and the project brief. Every document is Markdown and
> renders on GitHub, diagrams included. New to the repo? Start with the
> [portability reference](course/reference/cloud-portability-reference.md).
> Keep this block when you edit the rest of this file; it is not part of the Lab 1 deliverable.

Student ID: **6688012**

This project predicts whether a machine will fail within seven days from sensor readings. It
packages deterministic data generation and training in a pinned `linux/amd64` container so a
grader can reproduce the reported metric without my Python environment or Azure credentials.

---

## Reproduce

```bash
make reproduce
```

expected test_roc_auc: 0.846557 ± 0.020

Measured on WSL2 Ubuntu 24.04 with Docker Desktop: approximately 140–144 seconds when the final
image layers must be exported, and 36 seconds with a warm build cache. The command needs Git, GNU
Make, Docker with Buildx, and network access to Docker Hub on the first build. It does not require
host Python, DVC, Azure CLI, `cloud.env`, or cloud credentials.

Three fixed-seed repetitions produced exactly `0.84655741609384` (spread `0`). Five split seeds
produced `0.8379997`–`0.8661987`; the tolerance of `0.020` rounds up the largest observed absolute
difference from the fixed-seed claim (`0.0196413`). Only the fixed seed is used by `make reproduce`.

---

## The problem

The deterministic generator is `scripts/make_dataset.py`. Data seed `20260101` creates 6,000 rows:
240 machines, 25 readings per machine, six sensor features, and binary target
`failed_within_7d`, with positive rate `0.117`.

Machines have persistent characteristics — a hot-running machine reads hot in every row. So the
train/validation/test split is **grouped by `machine_id`**: every reading from one machine lands
in exactly one partition. Splitting row-wise instead lets the model memorise the machine and
reports a validation score that will never survive production. `tests/test_data.py` asserts this
property holds, and Lab 4 turns it into a CI gate.

The generated CSV has DVC version `1c886b512c8a5c9bf723da1cd119fc80.dir` and content fingerprint
`422cccb9136e8140`. `make reproduce` generates the byte-identical CSV inside the container, while
the DVC remote provides an independently versioned copy.

---

## Layout

```
src/          Layer 1 — provider-neutral. No SDKs, no bucket names, no absolute paths.
cloudlayer/   Layer 3 — the only place a provider SDK may be imported.
scripts/      Dataset generation, cloud check, portability audit, metric verification.
tests/        Data contract tests and split property tests.
```

`src/config.py` is the single point of environment knowledge. Everything else reads from it.
`make portability-audit` enforces the rule; it fails the build if a provider string appears in
`src/` or `tests/`.

---

## Model selection and experiment tracking

Five pre-declared MLflow runs varied one Random Forest parameter at a time while holding the data
and seed fixed. The selected `fewer-trees` configuration uses `n_estimators=100`, `max_depth=8`,
and `min_samples_leaf=5`. It had the best validation PR AUC (`0.406292`) and used half as many
trees as the baseline; test results were not used for selection.

Full run IDs, parameters, metrics, provenance, and limitations are in
[`reports/lab1-runs.md`](reports/lab1-runs.md). Every run logs the seed, Git SHA, DVC hash, data
fingerprint, split strategy, and trained model. Local MLflow artifacts persist in Docker volume
`itcs355-lab1-mlflow` for the experiment matrix. One-command reproduction uses the separate
`itcs355-lab1-reproduce` volume and copies only `metrics.json` back for verification. Generated
SQLite and JSON files are intentionally ignored by Git.

## Development checks

```bash
make setup
make data
make test
make portability-audit
make verify                         # run after make reproduce
```

`make test` runs the ten Lab 1 data-contract and group-leakage tests. The complete starter test
directory also includes later-lab gates; its Lab 4 latency placeholder is recorded separately and
does not define Lab 1 acceptance.

---

## Cloud artifacts and provenance

- Final fresh-clone-verified commit: `57a8c5ddb266cbf885145910c560d526ed17f69c`
- Azure Container Registry image: `itcs3556688012-fje5fmhpgmadcxdz.azurecr.io/itcs355@sha256:f8eaad5b655af10fc43e6155afa844dd397f850fe665b0a1aa94b9cd088b259a`
- DVC remote: `azure://itcs355/itcs355/dvc`, storage account `itcs3556688012`

The registry and DVC remote remain private. An instructor who needs direct access must receive an
Azure read role through the agreed course channel; no account key, token, or SAS URL is stored in
this repository. Direct cloud access is not part of the one-command reproduction path.

---

## Reproducibility trade-off

Under time pressure, I would drop dependency artifact hashes first while retaining exact package
versions. Seeds directly control the split and model, and the base-image digest fixes the OS and
Python foundation. Without hashes, a resolver could accept a different or republished wheel with
the same version, weakening supply-chain integrity and potentially changing behavior. Exact
versions still give partial reproducibility, but the build would no longer prove that it installed
the exact artifacts I tested.

---

## Notes for the grader

- The published image and local verification target `linux/amd64`; a second physical architecture
  was not available for direct testing.
- A clean image export took about 140–144 seconds; Docker layer caching reduced later runs to about
  36 seconds.
- The synthetic dataset is regenerated inside the container so reproduction needs no private DVC
  credentials. Its fingerprint and DVC pointer are checked in every run.
- MLflow uses Docker named volumes because bind-mount permissions and file metadata differ between
  Windows-backed WSL paths and native Linux paths. Training still runs as non-root UID 10001.

---

## Checklist before you submit

- [ ] Test the submitted Git URL from a fresh clone
- [ ] Run `make verify` after this README update
- [x] Ten Lab 1 tests pass
- [x] Portability audit passes
- [x] Image builds for `linux/amd64` and is pushed with a digest
- [x] DVC push completed and remote/cache synchronization was verified
- [x] Five meaningful MLflow runs include params, metrics, provenance, and model artifacts
- [x] No template instruction blocks remain
- [ ] `git log -p | grep -i -E "secret|password|AKIA|BEGIN PRIVATE"` returns nothing

That last check is not optional. A credential in Git history is an automatic deduction in this
course, and rotating it is your responsibility, not the grader's.
