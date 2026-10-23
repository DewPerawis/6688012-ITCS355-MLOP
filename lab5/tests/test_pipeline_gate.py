"""Small offline checks for the registration boundary and non-finite metrics."""
import unittest

from cloudlayer.pipelines import definition
from src.pipeline_steps import decision


class PipelineGateTests(unittest.TestCase):
    def test_gate_blocks_unchanged_and_invalid_scores(self):
        incumbent = 0.40004728306048276
        self.assertTrue(decision(incumbent + .01, incumbent))
        self.assertFalse(decision(incumbent, incumbent))
        self.assertFalse(decision(.1, incumbent))
        with self.assertRaises(ValueError):
            decision(float("nan"), incumbent)

    def test_release_has_required_gate_dependency_in_both_variants(self):
        cfg = {"training_image": "example/image@sha256:abc", "train_identity_id": "training",
               "ci_client_id": "release", "source_base_commit": "commit", "data_version": "data",
               "tracking_uri": "tracking", "raw_uri": "raw", "incumbent_metric": .4}
        for degraded in (True, False):
            doc = definition(cfg, ".", "datahash", degraded)
            self.assertFalse(doc["settings"]["continue_on_step_failure"])
            jobs = doc["jobs"]
            for step in ("ingest", "validate", "train", "evaluate"):
                self.assertEqual(jobs[step]["identity"], {"type": "managed"})
            for step in ("register", "deploy_staging"):
                self.assertEqual(jobs[step]["identity"], {"type": "managed", "client_id": "release"})
            self.assertEqual(jobs["register"]["inputs"]["gate"]["path"],
                             "${{parent.jobs.evaluate.outputs.gate}}")
            self.assertEqual(jobs["deploy_staging"]["inputs"]["registered"]["path"],
                             "${{parent.jobs.register.outputs.registered}}")
            self.assertNotEqual(jobs["train"]["compute"], jobs["register"]["compute"])


if __name__ == "__main__":
    unittest.main()
