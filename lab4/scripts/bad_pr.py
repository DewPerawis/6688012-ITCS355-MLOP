"""Create a deliberate contract-breaking PR and capture its failure; user runs explicitly."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--close", type=int, help="close the failed PR without merging")
    args = parser.parse_args()
    root = Path(output("git", "rev-parse", "--show-toplevel"))
    branch = "codex/lab4-bad-contract"
    worktree = root / "lab4/_worktrees/bad-contract"
    repo = output("gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    if args.close:
        if not args.execute:
            raise SystemExit("Preview: would close the specified PR without merging; add --execute")
        pr = json.loads(output("gh", "pr", "view", str(args.close), "--repo", repo, "--json",
                               "headRefName,state,mergedAt,url"))
        if pr["headRefName"] != branch or pr["mergedAt"]:
            raise RuntimeError("specified PR is not the unmerged Lab 4 bad-contract exercise")
        subprocess.run(["gh", "pr", "close", str(args.close), "--repo", repo], check=True)
        pr = json.loads(output("gh", "pr", "view", str(args.close), "--repo", repo, "--json",
                               "state,mergedAt,url"))
        if pr["state"] != "CLOSED" or pr["mergedAt"]:
            raise RuntimeError("PR closure was not confirmed")
        Path("reports/blocked-pr-closure.json").write_text(json.dumps(pr, indent=2), encoding="utf-8")
        print("PR closed without merging; evidence captured")
        return
    print(f"Plan: create {branch} from origin/main in {worktree}; drop temp_c from the generated CSV;")
    print("commit only lab4/scripts/prepare.py, push the new branch, and open a PR. Main is unchanged.")
    if not args.execute:
        return
    if output("git", "diff", "--name-only") or output("git", "diff", "--cached", "--name-only"):
        raise RuntimeError("commit the finished Lab 4 preparation before starting the PR exercise")
    subprocess.run(["git", "fetch", "origin", "main"], check=True)
    # This is intentionally not repeated if the branch or worktree already exists.
    subprocess.run(["git", "worktree", "add", "-b", branch, str(worktree), "origin/main"], check=True)
    target = worktree / "lab4/scripts/prepare.py"
    text = target.read_text(encoding="utf-8")
    before = 'frame.to_csv("data/raw/sensors.csv", index=False)'
    after = 'frame.drop(columns=["temp_c"]).to_csv("data/raw/sensors.csv", index=False)'
    if text.count(before) != 1:
        raise RuntimeError("unexpected source; no bad commit created")
    target.write_text(text.replace(before, after), encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "lab4/scripts/prepare.py"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-m",
                    "test: deliberately break Lab 4 temperature data contract"], check=True)
    subprocess.run(["git", "-C", str(worktree), "push", "-u", "origin", branch], check=True)
    body = Path("reports/bad-pr-body.md")
    body.write_text("Controlled Lab 4 failure exercise: generated training CSV omits temp_c. "
                    "The data schema contract must block CI before build and deployment. "
                    "This PR will be closed without merging after the failing test is captured.\n",
                    encoding="utf-8")
    url = output("gh", "pr", "create", "--repo", repo, "--base", "main", "--head", branch,
                 "--title", "Lab 4: prove the temperature data contract blocks a bad commit",
                 "--body-file", str(body))
    Path("reports/blocked-pr.json").write_text(json.dumps({"url": url, "branch": branch,
        "expected_failing_test": "test_training_schema_contract", "status": "awaiting actual CI"}, indent=2),
        encoding="utf-8")
    print(f"Opened {url}. Capture the actual CI failure before closing this PR.")


if __name__ == "__main__":
    main()
