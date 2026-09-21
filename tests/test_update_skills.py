"""Offline updater tests: real Git trees and mocked remote boundaries."""
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_skills as u
from test_sync import source

A, B = "a" * 40, "b" * 40


def pr(head=A):
    return {"number": 1, "state": "open", "head": {"sha": head, "ref": u.BRANCH, "repo": {"full_name": u.REPO}},
            "base": {"ref": "main"}, "draft": False, "labels": [], "body": ""}


def protected():
    return {"required_status_checks": {"strict": True, "checks": [{"context": "validate", "app_id": 15368}]},
            "enforce_admins": {"enabled": True}, "required_pull_request_reviews": {"required_approving_review_count": 0},
            "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}


@contextlib.contextmanager
def repository():
    with tempfile.TemporaryDirectory() as temp:
        old = Path.cwd()
        os.chdir(temp)
        try:
            u.git("init", "-q")
            u.git("config", "user.email", "test@example.invalid")
            u.git("config", "user.name", "Test")
            yield Path(temp)
        finally:
            os.chdir(old)


def commit(files):
    for name, content in files.items():
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    u.git("add", "-A")
    u.git("commit", "-qm", "fixture")
    return u.git("rev-parse", "HEAD").decode().strip()


class GitTests(unittest.TestCase):
    def test_full_diff_rename_modes_and_ancestry(self):
        with repository() as repo:
            old = commit({"README.md": b"one\n", "workflows/x/SKILL.md": b"test\n"})
            new = commit({"README.md": b"two\n"})
            self.assertEqual(u.classify(repo, old, new), [])
            u.git("mv", "workflows/x/SKILL.md", "AGENTS.md")
            renamed = commit({"README.md": b"three\n"})
            self.assertIn("AGENTS.md", u.classify(repo, new, renamed))
            with self.assertRaises(u.Stop):
                u.classify(repo, renamed, old)
            os.chmod("README.md", 0o755)
            executable = commit({"README.md": b"four\n"})
            self.assertIn("README.md", u.classify(repo, renamed, executable))

    def test_more_than_300_files_never_truncated(self):
        with repository() as repo:
            old = commit({"README.md": b"base"})
            files = {f"workflows/x/{i}.md": b"safe" for i in range(350)}
            files["scripts/unsafe.py"] = b"not executed"
            new = commit(files)
            self.assertEqual(u.classify(repo, old, new), ["scripts/unsafe.py"])

    def test_candidate_reproducible_preserves_unowned_and_detects_edits(self):
        with repository() as repo:
            old = commit(source())
            new = commit({"workflows/test-work/extra.md": b"Additional evidence\n"})
            base = commit({"VERSION": b"0.1.0-dev.1\n", "CHANGELOG.md": b"# Changelog\n\n## Unreleased\n",
                           "upstream.lock.json": u.sync.encoded({"repository": u.sync.UPSTREAM, "commit": old}),
                           "unowned.txt": b"preserve me\n"})
            first = u.candidate(base, new, repo)
            self.assertEqual(first, u.candidate(base, new, repo))
            self.assertEqual(u.blob(first, "unowned.txt"), b"preserve me\n")
            self.assertEqual(u.blob(first, "VERSION"), b"0.1.0-dev.2\n")
            self.assertIn(new.encode(), u.blob(first, "CHANGELOG.md"))
            self.assertNotEqual(first, u.git("rev-parse", f"{base}^{{tree}}").decode().strip())
            with self.assertRaises(u.Stop):
                u.candidate(base, old, repo)


    def test_existing_candidate_rerun_edits_and_sensitive_hold(self):
        with repository() as repo:
            old = commit(source())
            new = commit({"workflows/test-work/extra.md": b"ordinary\n"})
            base = commit({"VERSION": b"1.0.0\n", "CHANGELOG.md": b"## Unreleased\n",
                           "upstream.lock.json": u.sync.encoded({"repository": u.sync.UPSTREAM, "commit": old})})
            u.git("update-ref", "refs/remotes/origin/main", base)
            tree = u.candidate(base, new, repo)
            head = u.git("commit-tree", tree, "-p", base, data=f"{u.MARKER}\n\nbase {base}\npin {new}\n".encode()).decode().strip()
            original_git = u.git
            def local_git(*args, **kwargs):
                return b"" if "fetch" in args else original_git(*args, **kwargs)
            def remote(path, *args):
                return [{"ref": f"refs/heads/{u.BRANCH}", "object": {"sha": head}}] if path.startswith("git/") else pr(head)
            acknowledged = dict(pr(), number=7, state="closed", merged_at=None)
            with patch.object(u, "git", side_effect=local_git), patch.object(u, "api", side_effect=remote), patch.object(u, "prs", return_value=[pr(head), acknowledged]), patch.object(u, "load_resolutions", return_value={7: A}):
                self.assertEqual(u.existing(repo), (head, pr(head)))
                with patch.object(u, "candidate", return_value=B), self.assertRaises(u.Stop):
                    u.existing(repo)
                with patch.object(u, "classify", return_value=["mandatory/x/SKILL.md"]), self.assertRaises(u.Stop):
                    u.existing(repo)


class BoundaryTests(unittest.TestCase):
    def test_versions_and_sensitive_paths(self):
        self.assertEqual(u.bump("1.2.3"), "1.2.4")
        self.assertEqual(u.bump("0.1.0-dev.9"), "0.1.0-dev.10")
        for version in ("1.2.3-rc.1", "01.2.3", "v1.2.3", "1.2"):
            with self.assertRaises(u.Stop):
                u.bump(version)
        for path in ("mandatory/x/SKILL.md", "LICENSE", "AGENTS.md", "workflows/x/AGENTS.md",
                     "workflows/x/.github/x.md", "scripts/x.md", "workflows/x/run.py"):
            self.assertFalse(u.ordinary(path), path)
        self.assertTrue(u.ordinary("workflows/x/SKILL.md"))

    def test_missing_credentials_and_wrong_ref(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(u.Stop):
            u.main()
        with patch.dict(os.environ, {"GH_TOKEN": "synthetic", "GITHUB_REPOSITORY": u.REPO,
                                    "GITHUB_REF": "refs/heads/other", "GITHUB_EVENT_NAME": "workflow_dispatch"}), self.assertRaises(u.Stop):
            u.main()

    def test_manual_hold_fork_and_head_fences(self):
        for change in ({"draft": True}, {"labels": [{"name": "manual-review"}]}, {"body": "MANUAL HOLD"},
                       {"head": {"sha": B, "ref": u.BRANCH, "repo": {"full_name": u.REPO}}},
                       {"head": {"sha": A, "ref": u.BRANCH, "repo": {"full_name": "someone/stack"}}}):
            with self.assertRaises(u.Stop):
                u.verify_pr(dict(pr(), **change), A)

    def test_source_and_destination_races(self):
        for base, pin in ((B, A), (A, B)):
            with patch.object(u, "base_head", return_value=base), patch.object(u, "upstream", return_value=pin), self.assertRaises(u.Stop):
                u.fence(A, A)

    def test_missing_failed_skipped_cancelled_wrong_app_checks(self):
        for conclusion in (None, "failure", "skipped", "cancelled", "timed_out"):
            check = {"name": "validate", "app": {"id": 15368}, "head_sha": A, "status": "completed", "conclusion": conclusion}
            with patch.object(u, "api", return_value={"total_count": 1, "check_runs": [check]}):
                self.assertFalse(u.checks_pass(A))
        for checks in ([], [{"name": "validate", "app": {"id": 1}, "head_sha": A, "status": "completed", "conclusion": "success"}]):
            with patch.object(u, "api", return_value={"total_count": len(checks), "check_runs": checks}):
                self.assertFalse(u.checks_pass(A))
        with patch.object(u, "api", return_value={"total_count": 101}), self.assertRaises(u.Stop):
            u.checks_pass(A)

    def test_protection_requires_reviewed_contract(self):
        with patch.object(u, "api", return_value=protected()):
            u.protection()
        for key in protected():
            value = protected()
            del value[key]
            with patch.object(u, "api", return_value=value), self.assertRaises(u.Stop):
                u.protection()

    def test_merge_positive_and_uncertain_failure_no_retry(self):
        for merged in (True, False):
            def api(path, method="GET", body=None):
                if method == "PUT":
                    self.assertEqual(body, {"sha": A, "merge_method": "squash"})
                    return {"merged": merged}
                return pr()
            with patch.object(u, "api", side_effect=api) as remote, patch.object(u, "fence"), patch.object(u, "protection"), patch.object(u, "checks_pass", return_value=True):
                if merged:
                    u.merge(pr(), A, B, B)
                else:
                    with self.assertRaises(u.Stop):
                        u.merge(pr(), A, B, B)
                self.assertEqual(sum(c.args[1:2] == ("PUT",) for c in remote.call_args_list), 1)

    def test_bounded_missing_ci_never_merges(self):
        with patch.object(u, "api", return_value=pr()) as remote, patch.object(u, "fence"), patch.object(u, "checks_pass", return_value=False), patch.object(u.time, "sleep"), self.assertRaises(u.Stop):
            u.merge(pr(), A, B, B)
        self.assertEqual(remote.call_count, 20)
        self.assertTrue(all(len(c.args) == 1 for c in remote.call_args_list))

    def test_unknown_branch_and_closed_pr_preserved(self):
        for history in ([], [dict(pr(), state="closed", merged_at=None)]):
            with patch.object(u, "api", return_value=[{"ref": f"refs/heads/{u.BRANCH}", "object": {"sha": A}}]), patch.object(u, "prs", return_value=history), self.assertRaises(u.Stop):
                u.existing(Path("unused"))

    def test_main_publish_and_rerun_orchestration(self):
        environment = {"GH_TOKEN": "synthetic", "GITHUB_REPOSITORY": u.REPO,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch"}
        tree, head = "c" * 40, "d" * 40
        for previous in (None, head):
            def git(*args, **kwargs):
                if args[0] == "status":
                    return b""
                if args[0] == "rev-parse":
                    return (B if "cwd" in kwargs else tree if args[1].endswith("^{tree}") else A).encode()
                if args[0] == "commit-tree":
                    return head.encode()
                return b""
            existing_pr = pr(head) if previous else None
            with patch.dict(os.environ, environment), patch.object(u, "git", side_effect=git) as commands, patch.object(u, "run", return_value=b"") as processes, patch.object(u, "base_head", return_value=A), patch.object(u, "upstream", return_value=B), patch.object(u, "protection"), patch.object(u, "existing", return_value=(previous, existing_pr)), patch.object(u, "lock_at", return_value={"commit": A}), patch.object(u, "classify", return_value=[]), patch.object(u, "candidate", return_value=tree), patch.object(u, "fence"), patch.object(u, "api", return_value=pr(head)) as remote, patch.object(u, "merge") as merge:
                u.main()
                merge.assert_called_once_with(pr(head), head, A, B)
                pushes = [c for c in commands.call_args_list if "push" in c.args]
                self.assertEqual(len(pushes), 0 if previous else 1)
                if pushes:
                    self.assertIn(f"--force-with-lease=refs/heads/{u.BRANCH}:", pushes[0].args)
                self.assertEqual(remote.call_count, 0 if previous else 1)
                self.assertEqual(processes.call_count, 2)
                for process in processes.call_args_list:
                    self.assertNotIn("GH_TOKEN", process.kwargs["env"])

    def test_main_noop_and_sensitive_never_write(self):
        environment = {"GH_TOKEN": "synthetic", "GITHUB_REPOSITORY": u.REPO,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "repository_dispatch"}
        for pin, sensitive in ((A, []), (B, ["LICENSE"])):
            def git(*args, **kwargs):
                if args[0] == "status":
                    return b""
                if args[0] == "rev-parse":
                    return (pin if "cwd" in kwargs else A).encode()
                return b""
            with patch.dict(os.environ, environment), patch.object(u, "git", side_effect=git) as commands, patch.object(u, "base_head", return_value=A), patch.object(u, "upstream", return_value=pin), patch.object(u, "protection"), patch.object(u, "existing", return_value=(None, None)), patch.object(u, "lock_at", return_value={"commit": A}), patch.object(u, "classify", return_value=sensitive), patch.object(u, "api") as remote:
                if sensitive:
                    with self.assertRaisesRegex(u.Stop, "MANUAL HOLD"):
                        u.main()
                else:
                    u.main()
                remote.assert_not_called()
                self.assertFalse(any("push" in c.args for c in commands.call_args_list))

    def test_closed_hold_exact_reviewed_recovery(self):
        closed = dict(pr(), state="closed", merged_at=None)
        # Deletion alone cannot reset a human hold.
        with patch.object(u, "api", return_value=[]), patch.object(u, "prs", return_value=[closed]), patch.object(u, "load_resolutions", return_value={}):
            with self.assertRaisesRegex(u.Stop, "reviewed acknowledgement"):
                u.existing(Path("unused"))
        # Reviewed exact identity + separately deleted branch permits a fresh
        # candidate; the acknowledgement never deletes or overwrites a branch.
        with patch.object(u, "api", return_value=[]), patch.object(u, "prs", return_value=[closed]), patch.object(u, "load_resolutions", return_value={1: A}):
            self.assertEqual(u.existing(Path("unused")), (None, None))
        for acknowledgement in ({1: B}, {2: A}):
            with self.assertRaisesRegex(u.Stop, "does not match"):
                u.check_closed_holds([closed], acknowledgement)
        other = dict(closed, number=2)
        with self.assertRaisesRegex(u.Stop, "reviewed acknowledgement"):
            u.check_closed_holds([closed, other], {1: A})
        # Even acknowledged closed branches are not adopted as writable state.
        with patch.object(u, "api", return_value=[{"ref": f"refs/heads/{u.BRANCH}", "object": {"sha": A}}]), patch.object(u, "prs", return_value=[closed]), patch.object(u, "load_resolutions", return_value={1: A}):
            with self.assertRaisesRegex(u.Stop, "unknown/orphaned"):
                u.existing(Path("unused"))

    def test_acknowledged_history_allows_later_ordinary_update(self):
        head = "d" * 40
        environment = {"GH_TOKEN": "synthetic", "GITHUB_REPOSITORY": u.REPO,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch"}
        closed = dict(pr(), state="closed", merged_at=None)
        def git(*args, **kwargs):
            if args[0] == "rev-parse":
                return (B if "cwd" in kwargs else A).encode()
            return head.encode() if args[0] == "commit-tree" else b""
        def remote(path, method="GET", body=None):
            return [] if path.startswith("git/matching-refs/") else pr(head)
        with patch.dict(os.environ, environment), patch.object(u, "git", side_effect=git) as commands, patch.object(u, "run", return_value=b""), patch.object(u, "base_head", return_value=A), patch.object(u, "upstream", return_value=B), patch.object(u, "protection"), patch.object(u, "prs", return_value=[closed]), patch.object(u, "load_resolutions", return_value={1: A}), patch.object(u, "lock_at", return_value={"commit": A}), patch.object(u, "classify", return_value=[]), patch.object(u, "candidate", return_value="c" * 40), patch.object(u, "fence"), patch.object(u, "api", side_effect=remote) as api, patch.object(u, "merge") as merge:
            u.main()
            self.assertEqual(sum("push" in c.args for c in commands.call_args_list), 1)
            self.assertEqual(sum(c.args[1:2] == ("POST",) for c in api.call_args_list), 1)
            merge.assert_called_once_with(pr(head), head, A, B)

    def test_resolution_schema_and_identity_fail_closed(self):
        import json
        invalid = ({}, [True], [{"pr": True, "head": A}], [{"pr": 0, "head": A}],
                   [{"pr": 1, "head": "main"}], [{"pr": 1, "head": A, "all": True}],
                   [{"pr": 1, "head": A}, {"pr": 1, "head": A}])
        for entries in invalid:
            with patch.object(Path, "read_text", return_value=json.dumps(entries)), self.assertRaises(u.Stop):
                u.load_resolutions()
        with patch.object(Path, "read_text", return_value=json.dumps([{"pr": 1, "head": A}])):
            self.assertEqual(u.load_resolutions(), {1: A})
        closed = dict(pr(), state="closed", merged_at=None)
        for change in ({"state": "open"}, {"merged_at": "synthetic-date"}, {"base": {"ref": "other"}},
                       {"head": {"sha": A, "ref": u.BRANCH, "repo": {"full_name": "other/stack"}}}):
            with self.assertRaises(u.Stop):
                u.check_closed_holds([dict(closed, **change)], {1: A})

    def test_api_error_visible(self):
        with patch.object(u, "run", side_effect=u.Stop("API unavailable")), self.assertRaises(u.Stop):
            u.api("pulls")


if __name__ == "__main__":
    unittest.main()
