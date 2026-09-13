# Lab 1 MLflow Runs

Recorded: 2026-09-14

## Experiment controls

- Experiment: `itcs355-lab1`
- Git commit: `3d99e1cc077f1bd0f366408aed66b25c7c96ecc6`
- DVC data version: `1c886b512c8a5c9bf723da1cd119fc80.dir`
- Data fingerprint: `422cccb9136e8140`
- Dataset seed and training seed: `20260101`
- Split strategy: group by `machine_id`
- Fixed controls: the same dataset, split, seed, features and container image were used for all runs.

## Results

| Run | Full MLflow run ID | Trees | Depth | Min leaf | Val ROC AUC | Val PR AUC | Test ROC AUC | Test PR AUC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | `4ea1a4ac8245474982bb6bcd1bbb7204` | 200 | 8 | 5 | 0.836373 | 0.396309 | 0.848238 | 0.477622 |
| fewer-trees | `14366694d7bc417fac0f6fda8d1c69fc` | 100 | 8 | 5 | 0.839697 | **0.406292** | 0.846557 | 0.467457 |
| more-trees | `c5c6ec5c635645eabde10a64b127088f` | 300 | 8 | 5 | 0.837698 | 0.395445 | 0.849052 | 0.477963 |
| shallow | `9dc0a10ecb5d46a89d527faf4676793a` | 200 | 4 | 5 | 0.840455 | 0.386668 | 0.854311 | **0.499588** |
| larger-leaf | `12b1e42020934c278d1ad099281cdc41` | 200 | 8 | 10 | **0.841734** | 0.399945 | 0.849105 | 0.476465 |

Test metrics are reported for completeness and were not used to choose the candidate.

## Selected candidate

Selected run: `fewer-trees` (`14366694d7bc417fac0f6fda8d1c69fc`).

The dataset has an 11.7% positive rate, so validation PR AUC is useful for comparing minority-class ranking. `fewer-trees` has the best validation PR AUC, while its validation ROC AUC is only 0.002037 below the best run. It also uses half as many trees as the baseline. This suggests a better quality/capacity trade-off, but latency and cost improvements remain hypotheses until measured. The held-out test metrics are ROC AUC 0.846557 and PR AUC 0.467457.

## Limitations

- This matrix changes one hyperparameter factor at a time and uses one fixed seed.
- Runtime, latency and monetary cost were not measured per run, so no performance or cost reduction is claimed.
- Testing was performed on `linux/amd64` through WSL2 and Docker Desktop; another physical architecture was not available.

## Repeatability and seed sensitivity

The selected configuration was repeated three times at commit `8d6fae82bf9b3a98f85ca1f0e10c40b512f1b34f` with identical data, config and seed. All three runs produced test ROC AUC `0.84655741609384` (spread `0`). Measured end-to-end times were 144, 36 and 36 seconds; the first run built/exported the new image and later runs used Docker cache.

Changing only the training/split seed produced:

| Seed | Test ROC AUC |
|---:|---:|
| 20260101 | 0.846557416093840 |
| 20260102 | 0.866198650244004 |
| 20260103 | 0.837999698674166 |
| 20260104 | 0.855363349607217 |
| 20260105 | 0.850513724685910 |

Mean was `0.851326567861028`, full spread `0.028198951569838`, and population standard deviation `0.009364671977191`. This is a split-sensitivity study and is kept separate from the fixed-seed repeatability claim.

The final Docker-only reproduction at commit `ef75b24da8baa1d6af985f02d49ec7005eed7e4c` regenerated the same dataset inside the container and reproduced test ROC AUC `0.84655741609384` with matching DVC hash and fingerprint.
