# ITCS355 Lab 1 — training image
#
# Pin by digest so a moving tag cannot silently change the build environment.
FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Dependencies first so this layer caches independently of your source.
COPY requirements.txt ./
# Reject packages whose artifacts do not match the committed lock file.
RUN pip install --require-hashes --prefix=/install -r requirements.txt


FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534 AS runtime

ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

# Non-root. A training container has no reason to run as root, and graders check.
RUN useradd --create-home --uid 10001 runner \
    && mkdir -p /app/reports/mlruns \
    && chown -R runner:runner /app/reports
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PYTHONHASHSEED=20260101 \
    GIT_COMMIT=${GIT_COMMIT} \
    GIT_PYTHON_REFRESH=quiet

COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=runner:runner src/ ./src/
COPY --chown=runner:runner cloudlayer/ ./cloudlayer/
COPY --chown=runner:runner scripts/ ./scripts/
COPY --chown=runner:runner data/raw.dvc ./data/raw.dvc

USER runner

# Credentials NEVER enter an image layer. They arrive at runtime from SECRET_STORE_PATH
# or from the platform's identity. If you find yourself adding an ARG for a key, stop.
ENTRYPOINT ["python", "-m", "src.train"]
CMD ["--n-estimators", "200", "--max-depth", "8"]
