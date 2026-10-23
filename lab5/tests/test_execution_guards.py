"""Offline guards: no real Git, Azure calls or billable jobs."""
import subprocess
import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

from cloudlayer.execute import commit_source, owned, job_status, wait_job
from scripts.resume_normal import inspected_gate
from scripts.repair_serialization import verify_failure, repair_definition


class ExecutionGuardTests(unittest.TestCase):
    def test_serialization_retry_requires_the_specific_failure_before_release(self):
        import copy

        state = {"source_commit": "source", "jobs": {"normal": {"name": "normal"},
                 "degraded": {"expected_gate_failure_verified": True}}}
        report = {"job": "normal", "source_commit": "source", "status": "Failed",
                  "no_registration": True, "endpoint_exists": False,
                  "children": [{"step": step, "status": "Completed"} for step in ("ingest", "validate")]
                  + [{"step": "train", "status": "Failed", "user_log_excerpts": [{
                      "tail": "mlflow.sklearn.save_model Untrusted sklearn.tree._tree.Tree"}]}]}
        verify_failure(state, report)
        wrong_error = copy.deepcopy(report)
        wrong_error["children"][-1]["user_log_excerpts"][0]["tail"] = "out of memory"
        with self.assertRaises(ValueError):
            verify_failure(state, wrong_error)
        registered = copy.deepcopy(report)
        registered["no_registration"] = False
        with self.assertRaises(ValueError):
            verify_failure(state, registered)

    def test_repair_keeps_six_step_gate_and_revised_source_lineage(self):
        cfg = {"training_image": "example/image@sha256:abc", "ci_client_id": "release",
               "source_base_commit": "old", "data_version": "data", "tracking_uri": "tracking",
               "raw_uri": "raw", "incumbent_metric": .4}
        state = {"runtime": {**cfg, "source_base_commit": "fixed"}, "bundle": "new-bundle",
                 "serialization_repair": {"original": {"runtime": cfg, "bundle": "old-bundle"}}}
        doc = repair_definition(state, {"raw_sha256": "hash"})
        self.assertEqual(len(doc["jobs"]), 6)
        self.assertFalse(doc["settings"]["force_rerun"])
        self.assertFalse(doc["settings"]["continue_on_step_failure"])
        self.assertEqual(doc["jobs"]["ingest"]["environment_variables"]["LAB5_GIT_COMMIT"], "fixed")
        self.assertEqual(doc["jobs"]["train"]["environment_variables"]["LAB5_GIT_COMMIT"], "fixed")
        self.assertEqual(doc["jobs"]["train"]["inputs"]["validated"]["path"],
                         "${{parent.jobs.validate.outputs.validated}}")
        self.assertEqual(doc["jobs"]["register"]["inputs"]["gate"]["path"],
                         "${{parent.jobs.evaluate.outputs.gate}}")

    def test_only_an_inspected_measured_gate_failure_allows_continuation(self):
        import copy
        import json

        state = {"source_commit": "source", "jobs": {"degraded": {"name": "existing"}}}
        metric = {"passed": False, "deliberate_degradation": True, "measured_val_pr_auc": .1,
                  "evaluated_val_pr_auc": .1, "incumbent": .4, "floor": .4, "margin": .002}
        report = {"job": "existing", "source_commit": "source", "status": "Failed",
                  "no_registration": True, "endpoint_exists": False,
                  "children": [{"step": step, "status": "Completed"} for step in ("ingest", "validate", "train")]
                  + [{"step": "evaluate", "status": "Failed", "user_log_excerpts": [{"tail": json.dumps(metric)}]}]}
        self.assertEqual(inspected_gate(report, state), metric)
        broken = copy.deepcopy(report)
        broken["children"][2]["status"] = "Failed"
        with self.assertRaises(ValueError):
            inspected_gate(broken, state)
        missing_log = copy.deepcopy(report)
        missing_log["children"][-1]["user_log_excerpts"] = []
        with self.assertRaises(ValueError):
            inspected_gate(missing_log, state)

    def test_status_enum_and_wire_string_are_equivalent(self):
        class JobStatus(Enum):
            FAILED = "Failed"
            COMPLETED = "Completed"
        for status in (JobStatus.FAILED, "JobStatus.FAILED", "FAILED", "Failed"):
            self.assertEqual(job_status(status), "Failed")
        self.assertEqual(job_status(JobStatus.COMPLETED), "Completed")
        self.assertEqual(job_status("JobStatus.NOT_RESPONDING"), "NotResponding")

    def test_failed_job_returns_without_sleep_or_timeout(self):
        class JobStatus(Enum):
            FAILED = "Failed"
        job = SimpleNamespace(status=JobStatus.FAILED, studio_url="studio")
        jobs = SimpleNamespace(get=lambda _: job, list=lambda **_: [])
        record = {}
        with patch("cloudlayer.execute.save"), patch("cloudlayer.execute.progress"):
            with patch("cloudlayer.execute.time.sleep") as sleep:
                self.assertIs(wait_job(SimpleNamespace(jobs=jobs), "existing", {}, record), job)
                sleep.assert_not_called()
        self.assertEqual(record["status"], "Failed")

    def test_existing_staged_work_is_not_committed(self):
        existing = subprocess.CompletedProcess([], 0, stdout=b"unrelated/file.txt\n")
        with patch("cloudlayer.execute.git", return_value=existing) as call:
            with self.assertRaises(ValueError):
                commit_source()
            call.assert_called_once_with("diff", "--cached", "--name-only")

    def test_other_labs_resources_are_rejected(self):
        resource = SimpleNamespace(name="shared", tags={"course": "itcs355", "student": "6688012", "lab": "4"})
        with self.assertRaises(ValueError):
            owned(resource)


if __name__ == "__main__":
    unittest.main()
