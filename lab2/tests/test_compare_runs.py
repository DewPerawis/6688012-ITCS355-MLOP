from __future__ import annotations

import json

import pandas as pd

from scripts.compare_runs import _job_ids_for_study, _markdown_table, _runs_for_jobs


def test_comparison_filters_runs_to_requested_study(tmp_path) -> None:
    history_path = tmp_path / "lab2-jobs.json"
    history_path.write_text(
        json.dumps(
            [
                {"study_id": "study-old", "job_id": "job-old"},
                {"study_id": "study-current", "job_id": "job-interrupt"},
                {"study_id": "study-current", "job_id": "job-resume"},
            ]
        ),
        encoding="utf-8",
    )
    runs = pd.DataFrame(
        {
            "run_id": ["old-run", "interrupted-run", "resumed-run"],
            "tags.training_job_id": ["job-old", "job-interrupt", "job-resume"],
        }
    )

    job_ids = _job_ids_for_study(history_path, "study-current")
    selected = _runs_for_jobs(runs, job_ids)

    assert job_ids == {"job-interrupt", "job-resume"}
    assert selected["run_id"].tolist() == ["interrupted-run", "resumed-run"]


def test_markdown_table_has_no_optional_dependency() -> None:
    frame = pd.DataFrame(
        {
            "run_id": ["abc123", "def456"],
            "note": ["selected", "pipe | escaped"],
        }
    )

    rendered = _markdown_table(frame)

    assert rendered.splitlines() == [
        "| run_id | note |",
        "| --- | --- |",
        "| abc123 | selected |",
        r"| def456 | pipe \| escaped |",
    ]
