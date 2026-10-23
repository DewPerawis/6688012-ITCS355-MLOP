"""Offline guards: no real Git, Azure calls or billable jobs."""
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cloudlayer.execute import commit_source, owned


class ExecutionGuardTests(unittest.TestCase):
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
