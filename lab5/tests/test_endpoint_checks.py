"""Offline regression checks for the endpoint's account-level role requirement."""
import unittest
import copy

from cloudlayer.endpoint_checks import role_evidence
from scripts.repair_deployment import deployment_definition, verified_candidate, registered_reference


class EndpointRoleTests(unittest.TestCase):
    account = "/subscriptions/sub/resourceGroups/course/providers/Microsoft.Storage/storageAccounts/lab"

    def assignment(self, scope, role="Storage Blob Data Reader", principal="serve", condition=None):
        return {"principalId": principal, "roleDefinitionName": role, "scope": scope, "condition": condition}

    def check_roles(self, assignments):
        return role_evidence(assignments, "serve", self.account, {"Storage Blob Data Reader"})

    def test_container_reader_does_not_satisfy_account_startup_check(self):
        grants = [self.assignment(self.account + "/blobServices/default/containers/model")]
        self.assertFalse(self.check_roles(grants)["verified_unconditional_role"])
        grants.append(self.assignment(self.account))
        self.assertTrue(self.check_roles(grants)["verified_unconditional_role"])

    def test_inherited_roles_apply_but_other_principals_and_sibling_accounts_do_not(self):
        for grant in (self.assignment(self.account, principal="train"), self.assignment(self.account + "2"),
                      self.assignment(self.account, role="Owner")):
            self.assertFalse(self.check_roles([grant])["verified_unconditional_role"])
        inherited = self.assignment("/SUBSCRIPTIONS/sub/resourceGroups/COURSE")
        self.assertTrue(self.check_roles([inherited])["verified_unconditional_role"])

    def test_conditional_role_remains_unverified(self):
        result = self.check_roles([self.assignment(self.account, condition="container == model")])
        self.assertFalse(result["verified_unconditional_role"])
        self.assertEqual(len(result["matching_assignments"]), 1)


class DeploymentContinuationTests(unittest.TestCase):
    def test_registration_child_without_outputs_builds_audited_reference(self):
        from types import SimpleNamespace

        job = SimpleNamespace(name="registered-child", status="Completed")
        self.assertFalse(hasattr(job, "outputs"))
        candidate = {"name": "model", "version": "3", "lineage": {"git_commit": "verified"}}
        self.assertEqual(registered_reference(job, "registered-child", candidate)["version"], "3")
        with self.assertRaises(ValueError):
            registered_reference(job, "another-child", candidate)
        job.status = "Failed"
        with self.assertRaises(ValueError):
            registered_reference(job, "registered-child", candidate)

    def test_continuation_uses_only_release_under_ci_and_local_reference(self):
        runtime = {"training_image": "image@sha256:abc", "ci_client_id": "ci-client",
                   "source_base_commit": "commit", "data_version": "data", "tracking_uri": "tracking",
                   "raw_uri": "raw", "incumbent_metric": .4}
        doc = deployment_definition({"runtime": runtime, "bundle": "bundle"}, {"raw_sha256": "sha"},
                                    "/offline/deployment-bundle")
        self.assertEqual(set(doc["jobs"]), {"deploy_staging"})
        node = doc["jobs"]["deploy_staging"]
        self.assertEqual(node["identity"], {"type": "managed", "client_id": "ci-client"})
        self.assertEqual(node["compute"], "azureml:lab5release")
        self.assertEqual(node["inputs"], {})
        self.assertIn("release deploy ", node["command"])
        self.assertIn("--registered ./registered", node["command"])
        self.assertNotIn("${{inputs.", node["command"])

    def test_only_the_audited_model_and_passing_gate_can_be_deployed(self):
        state = {"jobs": {"normal-repair": {"name": "original", "source_commit": "commit"}},
                 "runtime": {"model_name": "model", "incumbent_metric": .4}, "estimate_commit": "estimate"}
        audit = {"job": "original", "source_commit": "commit",
                 "steps": [{"step": step, "name": step, "status": "Completed"}
                           for step in ("ingest", "validate", "train", "evaluate", "register")]
                          + [{"step": "deploy_staging", "name": "deploy", "status": "Failed"}],
                 "registered_model": {"name": "model", "version": "3", "lineage": {
                     "git_commit": "commit", "training_job_id": "train", "estimate_commit": "estimate", "metric_val": ".41"}},
                 "deployment": {"model_version": "3", "image_matches_pinned": True},
                 "endpoint": {"expected_identity_attached": True},
                 "permission_checks": {"registry_pull": {"verified_unconditional_role": True},
                                       "workspace_storage_reader": {"status": "ok"}}}
        self.assertEqual(verified_candidate(audit, state)[1], "register")
        wrong_version = copy.deepcopy(audit)
        wrong_version["deployment"]["model_version"] = "1"
        with self.assertRaises(ValueError):
            verified_candidate(wrong_version, state)
        no_gain = copy.deepcopy(audit)
        no_gain["registered_model"]["lineage"]["metric_val"] = ".4"
        with self.assertRaises(ValueError):
            verified_candidate(no_gain, state)


if __name__ == "__main__":
    unittest.main()
