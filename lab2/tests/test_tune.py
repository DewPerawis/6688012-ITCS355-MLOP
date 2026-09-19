from __future__ import annotations

from pathlib import Path

import mlflow

from src import costs
from src.tune import (
    MODEL_PIP_REQUIREMENTS,
    SEARCH_SPACE,
    _log_model_run_artifact,
    grid,
    select_candidate,
    trial_key,
)


def test_search_space_has_twelve_unique_three_parameter_configurations() -> None:
    candidates = grid(SEARCH_SPACE)
    assert len(candidates) == 12
    assert len({trial_key("study", candidate, 20260101) for candidate in candidates}) == 12
    assert set(SEARCH_SPACE) == {"n_estimators", "max_depth", "min_samples_leaf"}
    assert all(len(values) >= 2 for values in SEARCH_SPACE.values())


def test_selection_prefers_cheapest_candidate_inside_near_best_band() -> None:
    results = [
        {
            "val_pr_auc": 0.410,
            "cost_thb": 0.08,
            "params": {"n_estimators": 240, "max_depth": 8, "min_samples_leaf": 2},
        },
        {
            "val_pr_auc": 0.407,
            "cost_thb": 0.03,
            "params": {"n_estimators": 80, "max_depth": 8, "min_samples_leaf": 2},
        },
        {
            "val_pr_auc": 0.390,
            "cost_thb": 0.01,
            "params": {"n_estimators": 80, "max_depth": 4, "min_samples_leaf": 8},
        },
    ]
    selected = select_candidate(results, tolerance=0.005)
    assert selected["val_pr_auc"] == 0.407


def test_verified_azure_price_is_used_exactly() -> None:
    assert costs.hourly_rate("azure", "Standard_DS2_v2-dedicated") == 5.558


def test_model_is_uploaded_as_run_artifact_without_logged_model_api(monkeypatch) -> None:
    saved: dict[str, object] = {}
    uploaded: dict[str, object] = {}
    sentinel_model = object()

    def fake_save_model(model, *, path, serialization_format, pip_requirements):
        model_dir = Path(path)
        model_dir.mkdir(parents=True)
        (model_dir / "MLmodel").write_text("flavors: {}", encoding="utf-8")
        saved.update(
            model=model,
            path=model_dir,
            serialization_format=serialization_format,
            pip_requirements=pip_requirements,
        )

    def fake_log_artifacts(local_dir, *, artifact_path):
        model_dir = Path(local_dir)
        uploaded.update(
            has_mlmodel=(model_dir / "MLmodel").is_file(),
            artifact_path=artifact_path,
        )

    monkeypatch.setattr(mlflow.sklearn, "save_model", fake_save_model)
    monkeypatch.setattr(mlflow, "log_artifacts", fake_log_artifacts)

    _log_model_run_artifact(sentinel_model)

    assert saved["model"] is sentinel_model
    assert saved["serialization_format"] == "cloudpickle"
    assert saved["pip_requirements"] == MODEL_PIP_REQUIREMENTS
    assert uploaded == {"has_mlmodel": True, "artifact_path": "model"}
