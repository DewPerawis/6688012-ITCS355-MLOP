"""Provider-neutral FastAPI inference service for Lab 3."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from service.schemas import BatchRequest, BatchResponse, PredictRequest, PredictResponse
from src.data import FEATURES

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("service")

STATE: dict[str, Any] = {
    "model": None,
    "version": os.environ.get("MODEL_VERSION", "unknown"),
    "load_count": 0,
}


def _load_model() -> Any:
    """Load the mounted MLflow sklearn model once during process startup."""
    raw_model_path = os.environ.get("MODEL_PATH")
    if not raw_model_path:
        raise RuntimeError("MODEL_PATH must point to a mounted versioned MLflow model")
    model_path = Path(raw_model_path)
    if not model_path.exists():
        raise RuntimeError("MODEL_PATH must point to a mounted versioned MLflow model")
    import mlflow.sklearn

    STATE["load_count"] += 1
    return mlflow.sklearn.load_model(str(model_path))


def _event(level: int, event: str, **fields: Any) -> None:
    log.log(level, json.dumps({"event": event, **fields}, separators=(",", ":")))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    STATE["version"] = os.environ.get("MODEL_VERSION", "unknown")
    try:
        STATE["model"] = _load_model()
        _event(logging.INFO, "model_loaded", model_version=STATE["version"])
    except Exception as exc:
        STATE["model"] = None
        _event(logging.ERROR, "model_load_failed", error_type=type(exc).__name__)
    yield
    STATE["model"] = None


app = FastAPI(title="ITCS355 inference", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000
        _event(
            logging.ERROR,
            "request",
            request_id=request_id,
            path=request.url.path,
            status=500,
            latency_ms=round(latency_ms, 3),
            model_version=str(STATE["version"]),
        )
        raise
    latency_ms = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    response.headers["x-model-version"] = str(STATE["version"])
    _event(
        logging.INFO,
        "request",
        request_id=request_id,
        path=request.url.path,
        status=response.status_code,
        latency_ms=round(latency_ms, 3),
        model_version=str(STATE["version"]),
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ready")
def ready():
    if STATE["model"] is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "model not loaded"},
        )
    return {"status": "ready", "model_version": str(STATE["version"])}


def _score(rows: list[PredictRequest]) -> list[float]:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    records = [row.model_dump(include=set(FEATURES)) for row in rows]
    frame = pd.DataFrame.from_records(records, columns=FEATURES)
    probabilities = STATE["model"].predict_proba(frame)[:, 1]
    return [float(value) for value in probabilities]


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest) -> PredictResponse:
    return PredictResponse(
        probability=_score([payload])[0],
        model_version=str(STATE["version"]),
    )


@app.post("/predict/batch", response_model=BatchResponse)
def predict_batch(payload: BatchRequest) -> BatchResponse:
    return BatchResponse(
        probabilities=_score(payload.rows),
        model_version=str(STATE["version"]),
    )


@app.post("/invoke", response_model=PredictResponse | BatchResponse)
def invoke(payload: PredictRequest | BatchRequest) -> PredictResponse | BatchResponse:
    """One scoring route for gateways that expose only a single public score URI.

    The required `/predict` and `/predict/batch` contracts remain unchanged. The cloud
    adapter maps its provider gateway to this neutral compatibility route.
    """
    if isinstance(payload, BatchRequest):
        return predict_batch(payload)
    return predict(payload)
