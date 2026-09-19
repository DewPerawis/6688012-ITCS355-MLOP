from __future__ import annotations

from src import costs
from src.tune import SEARCH_SPACE, grid, select_candidate, trial_key


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
