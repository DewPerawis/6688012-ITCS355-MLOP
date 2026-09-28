"""Validated request and response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    temp_c: float = Field(..., ge=-10, le=140)
    vibration_mm_s: float = Field(..., ge=0, le=60)
    pressure_kpa: float = Field(..., ge=0, le=600)
    hours_since_service: float = Field(..., ge=0, le=20000)
    load_pct: float = Field(..., ge=0, le=100)
    ambient_humidity: float = Field(..., ge=0, le=100)
    request_context: str | None = Field(default=None, max_length=100_000)

    model_config = {"extra": "forbid"}


class PredictResponse(BaseModel):
    probability: float
    model_version: str


class BatchRequest(BaseModel):
    rows: list[PredictRequest] = Field(..., min_length=1, max_length=100)


class BatchResponse(BaseModel):
    probabilities: list[float]
    model_version: str
