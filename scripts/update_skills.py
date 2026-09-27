#!/usr/bin/env python3
"""Trusted-main updater. Never execute content from upstream or an update branch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import sync

REPO = "vllnt/stack"
SOURCE = "vllnt/skills"
BRANCH = "automation/update-skills"
SHA = re.compile(r"[0-9a-f]{40}\Z")
MARKER = "vstack-skills-update-v1"


class Stop(RuntimeError):
    pass


def run(*args, cwd=None, data=None, env=None):
    result = subprocess.run(args, cwd=cwd, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=180)
    if result.returncode:
        # Do not echo commands, environment, or credential-bearing diagnostics.
        raise Stop(f"{args[0]} failed (exit {result.returncode})")
    return result.stdout


def git(*args, **kwargs):
    return run("git", *args, **kwargs)


def destination_git(*args):
    # Only private destination transport receives the scoped credential helper.
    return git("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential", *args)


def api(path, method="GET", body=None, token_env=None):
    args = ["gh", "api", f"repos/{REPO}/{path}", "--method", method]
    if body is not None:
        args += ["--input", "-"]
    env = None
    if token_env is not None:
        token = os.environ.get(token_env)
        if not token:
            raise Stop(f"{token_env} is required for the scoped API operation")
        env = dict(os.environ, GH_TOKEN=token)
    return json.loads(run(*args, data=json.dumps(body).encode() if body is not None else None, env=env))


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise Stop("invalid commit identity")
    return value


def upstream():
    value = run("gh", "api", f"repos/{SOURCE}/git/ref/heads/main")
    return sha(json.loads(value)["object"]["sha"])


def base_head():
    return sha(api("git/ref/heads/main")["object"]["sha"])


def bump(version):
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(dev|canary)\.(0|[1-9]\d*))?", version)
    if not match:
        raise Stop("VERSION needs human review")
    major, minor, patch, channel, number = match.groups()
    if channel is not None:
        return f"{major}.{minor}.{patch}-{channel}.{int(number)+1}"
    return f"{major}.{minor}.{int(patch)+1}"


def ordinary(path):
    parts = path.split("/")
    return (path in {"README.md", "CHANGELOG.md", "roadmap.md"} or
            (len(parts) >= 3 and parts[0] == "workflows" and path.endswith(".md")
             and not any(p.startswith(".") or p in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"} for p in parts)))


def classify(source, old, new):
    # A full local object comparison avoids API pagination/truncation and checks
    # both sides of renames as separate deletion/addition records.
    git("merge-base", "--is-ancestor", old, new, cwd=source)
    fields = git("diff", "--raw", "--no-renames", "-z", old, new, cwd=source).split(b"\0")
    sensitive = []
    while fields and fields[0]:
        header = fields.pop(0).decode("ascii").split()
        if len(header) != 5 or not fields:
            raise Stop("malformed diff")
        path = fields.pop(0).decode("utf-8", errors="strict")
        if header[4] not in {"A", "M", "D"} or any(mode not in {"000000", "100644"} for mode in (header[0][1:], header[1])) or not ordinary(path):
            sensitive.append(path)
    return sensitive


def blob(commit, path):
    return git("show", f"{commit}:{path}")


def lock_at(commit):
    lock = json.loads(blob(commit, "upstream.lock.json"))
    if set(lock) != {"repository", "commit"} or lock["repository"] != sync.UPSTREAM:
        raise Stop("untrusted lock")
    sha(lock["commit"])
    return lock


def owned(path):
    return path in {"VERSION", "CHANGELOG.md", "upstream.lock.json"} or any(path == t or path.startswith(t + "/") for t in sync.TARGETS)


def candidate(base, pin, source):
    old = lock_at(base)
    if old["commit"] == pin:
        raise Stop("candidate must change the pin")
    version = bump(blob(base, "VERSION").decode().strip())
    lock = {"repository": sync.UPSTREAM, "commit": pin}
    files = sync.unpack(sync.local_archive(source, pin))
    output = sync.build(files, lock, version)
    changelog = blob(base, "CHANGELOG.md").decode()
    if changelog.count("## Unreleased\n") != 1:
        raise Stop("unknown changelog structure")
    entry = f"\n- Update packaged skills from `{old['commit']}` to `{pin}` ({version}).\n"
    output.update({"VERSION": (version + "\n").encode(), "upstream.lock.json": sync.encoded(lock),
                   "CHANGELOG.md": changelog.replace("## Unreleased\n", "## Unreleased\n" + entry, 1).encode()})
    # Construct a complete tree from the trusted base without checking out or
    # running any update-branch files. Unowned paths are preserved exactly.
    with tempfile.TemporaryDirectory() as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"))
        git("read-tree", base, env=env)
        records = []
        for record in git("ls-tree", "-rz", base).split(b"\0"):
            if not record:
                continue
            _, path = record.split(b"\t", 1)
            if owned(path.decode()):
                records.append(b"0 " + b"0" * 40 + b"\t" + path + b"\0")
        for path, content in sorted(output.items()):
            digest = git("hash-object", "-w", "--stdin", data=content).strip()
            records.append(b"100644 " + digest + b"\t" + path.encode() + b"\0")
        git("update-index", "-z", "--index-info", data=b"".join(records), env=env)
        return git("write-tree", env=env).decode().strip()


def protection():
    rule = api("branches/main/protection")
    checks = rule.get("required_status_checks") or {}
    expected = {("validate", 15368)}
    actual = {(c.get("context"), c.get("app_id")) for c in checks.get("checks", [])}
    reviews = rule.get("required_pull_request_reviews") or {}
    if (checks.get("strict") is not True or actual != expected or
            rule.get("enforce_admins", {}).get("enabled") is not True or
            reviews.get("required_approving_review_count") != 0 or
            rule.get("allow_force_pushes", {}).get("enabled") is not False or
            rule.get("allow_deletions", {}).get("enabled") is not False):
        raise Stop("main protection differs from the reviewed merge contract")


def prs():
    # Explicit pagination: no default-page assumptions.
    result = []
    for page in range(1, 101):
        batch = api(f"pulls?state=all&head=vllnt:{BRANCH}&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise Stop("malformed PR response")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise Stop("PR inventory exceeded bound")


def verify_pr(pr, head):
    if (pr["head"]["sha"] != head or pr["head"]["ref"] != BRANCH or
            (pr["head"].get("repo") or {}).get("full_name") != REPO or
            pr["base"]["ref"] != "main" or pr.get("draft") or
            any(label["name"] == "manual-review" for label in pr.get("labels", [])) or
            "MANUAL HOLD" in (pr.get("body") or "")):
        raise Stop("existing PR is held or has an unexpected identity; leave untouched")


def load_resolutions():
    # Owned by reviewed main, never an event input or generated candidate.
    # main() verifies the clean checkout identity before this read.
    path = Path(__file__).resolve().parents[1] / ".github/skills-update-resolutions.json"
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise Stop("resolution acknowledgements must be a list")
    result = {}
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {"pr", "head"} or
                type(entry["pr"]) is not int or entry["pr"] < 1 or entry["pr"] in result):
            raise Stop("invalid or duplicate resolution acknowledgement")
        result[entry["pr"]] = sha(entry["head"])
    return result


def check_closed_holds(history, resolutions):
    closed = {p["number"]: p for p in history if p["state"] == "closed" and not p.get("merged_at")}
    for number, head in resolutions.items():
        pr = closed.get(number)
        if (pr is None or pr["head"]["sha"] != head or pr["head"]["ref"] != BRANCH or
                (pr["head"].get("repo") or {}).get("full_name") != REPO or pr["base"]["ref"] != "main"):
            raise Stop("resolution acknowledgement does not match an exact closed unmerged PR")
    if closed.keys() - resolutions.keys():
        raise Stop("closed unmerged automation PR requires reviewed acknowledgement")


def existing(source):
    refs = api("git/matching-refs/heads/automation/update-skills")
    exact = [r for r in refs if r["ref"] == f"refs/heads/{BRANCH}"]
    history = prs()
    opened = [p for p in history if p["state"] == "open"]
    # Acknowledgement releases historical holds only. It never authorizes
    # modifying a surviving held, unknown, or human-edited branch.
    check_closed_holds(history, load_resolutions())
    if not exact:
        if opened:
            raise Stop("PR exists without branch")
        return None, None
    if len(exact) != 1 or len(opened) > 1:
        raise Stop("unknown/orphaned branch; inspect uncertain prior writes")
    head = sha(exact[0]["object"]["sha"])
    matches = opened or [p for p in history if p.get("merged_at") and p["head"]["sha"] == head]
    if len(matches) != 1:
        raise Stop("unknown/orphaned branch; inspect uncertain prior writes")
    pr = api(f"pulls/{matches[0]['number']}")
    verify_pr(pr, head)
    destination_git("fetch", "--no-tags", "origin", head)
    parents = git("rev-list", "--parents", "-n", "1", head).decode().split()
    if len(parents) != 2:
        raise Stop("automation branch must be a single generated commit")
    parent = sha(parents[1])
    git("merge-base", "--is-ancestor", parent, "origin/main")
    pin = lock_at(head)["commit"]
    old = lock_at(parent)["commit"]
    if classify(source, old, pin):
        raise Stop("sensitive existing candidate is permanently held")
    message = git("show", "-s", "--format=%B", head).decode().strip()
    if message != f"{MARKER}\n\nbase {parent}\npin {pin}":
        raise Stop("unknown branch provenance")
    if git("rev-parse", f"{head}^{{tree}}").decode().strip() != candidate(parent, pin, source):
        raise Stop("human edits or unknown candidate; leave untouched")
    return head, pr if pr["state"] == "open" else None


def fence(base, pin):
    if base_head() != base or upstream() != pin:
        raise Stop("source or destination moved; rerun from current trusted main")


def checks_pass(head):
    # Checks read is provided by the workflow's short-lived installation token,
    # not requested from the operator's fine-grained personal access token.
    value = api(f"commits/{head}/check-runs?per_page=100", token_env="GITHUB_TOKEN")
    if value.get("total_count", 101) > 100:
        raise Stop("check inventory exceeds bound")
    checks = [c for c in value.get("check_runs", []) if c.get("name") == "validate" and (c.get("app") or {}).get("id") == 15368]
    return bool(checks) and all(c.get("head_sha") == head and c.get("status") == "completed" and c.get("conclusion") == "success" for c in checks)


def merge(pr, head, base, pin, previous_head=None):
    for attempt in range(20):
        fence(base, pin)
        current = api(f"pulls/{pr['number']}")
        observed = sha(current["head"]["sha"])
        # Holds and identity checks apply even while GitHub propagates our push.
        verify_pr(current, observed)
        if current.get("state") != "open":
            raise Stop("PR no longer open")
        if observed != head:
            if observed != previous_head:
                raise Stop("unexpected PR head; leave untouched")
            branch = sha(api(f"git/ref/heads/{BRANCH}")["object"]["sha"])
            if branch not in {head, previous_head}:
                raise Stop("unexpected branch head during propagation; leave untouched")
            print(f"Awaiting known PR head propagation from {previous_head} to {head}")
        elif checks_pass(head):
            protection()
            fence(base, pin)
            verify_pr(api(f"pulls/{pr['number']}"), head)
            result = api(f"pulls/{pr['number']}/merge", "PUT", {"sha": head, "merge_method": "squash"})
            if result.get("merged") is not True:
                raise Stop("normal protected merge did not complete")
            print(f"Merged update PR #{pr['number']} at {head}")
            return
        if attempt < 19:
            time.sleep(15)
    raise Stop("exact-head validate success missing; PR remains open")


def main():
    if not os.environ.get("GH_TOKEN"):
        raise Stop("STACK_UPDATE_TOKEN is required")
    if (os.environ.get("GITHUB_REPOSITORY") != REPO or os.environ.get("GITHUB_REF") != "refs/heads/main" or
            os.environ.get("GITHUB_EVENT_NAME") not in {"repository_dispatch", "schedule", "workflow_dispatch"}):
        raise Stop("updater only runs in a trusted-main workflow")
    if git("status", "--porcelain").strip():
        raise Stop("working tree must be clean")
    base = base_head()
    if git("rev-parse", "HEAD").decode().strip() != base:
        raise Stop("checkout is not current trusted main")
    pin = upstream()
    protection()
    destination_git("fetch", "--no-tags", "origin", "main")
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "source.git"
        # Public unauthenticated fetch; dispatch payload is never consulted.
        git("clone", "--bare", "--single-branch", "--branch", "main", sync.UPSTREAM, str(source))
        if git("rev-parse", "main", cwd=source).decode().strip() != pin:
            raise Stop("upstream moved during fetch")
        previous, pr = existing(source)
        old = lock_at(base)["commit"]
        if old == pin:
            print("No pin change; no version bump or remote write")
            return
        sensitive = classify(source, old, pin)
        if sensitive:
            # Do not publish a branch that could later be mistaken for ordinary.
            raise Stop("MANUAL HOLD: sensitive upstream paths: " + ", ".join(sensitive))
        tree = candidate(base, pin, source)
        if previous and git("rev-parse", f"{previous}^{{tree}}").decode().strip() == tree:
            head = previous
        else:
            env = dict(os.environ, GIT_AUTHOR_NAME="Vstack updater", GIT_AUTHOR_EMAIL="automation@users.noreply.github.com",
                       GIT_COMMITTER_NAME="Vstack updater", GIT_COMMITTER_EMAIL="automation@users.noreply.github.com")
            head = git("commit-tree", tree, "-p", base, data=f"{MARKER}\n\nbase {base}\npin {pin}\n".encode(), env=env).decode().strip()
        # Test the generated candidate in an isolated checkout. It contains only
        # trusted base code plus classified Markdown and generated artifacts.
        check = Path(temp) / "check"
        git("worktree", "add", "--detach", str(check), head)
        try:
            test_env = {k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN", "STACK_UPDATE_TOKEN"}}
            run("python3", "-m", "unittest", "discover", "-s", "tests", "-v", cwd=check, env=test_env)
            run("python3", "scripts/sync.py", "--check", "--source", str(source), cwd=check, env=test_env)
            git("diff", "--check", base, head, cwd=check)
        finally:
            git("worktree", "remove", "--force", str(check))
        fence(base, pin)
        # Re-read branch and PR immediately before any update. Lease also fences
        # branch changes after this read; PR metadata has no conditional API.
        now, current_pr = existing(source)
        if now != previous or (current_pr or {}).get("number") != (pr or {}).get("number"):
            raise Stop("automation branch or PR raced")
        if head != previous:
            # gh's credential helper is command-scoped; no credential persistence.
            destination_git("push",
                f"--force-with-lease=refs/heads/{BRANCH}:{previous or ''}",
                "origin", f"{head}:refs/heads/{BRANCH}")
        if pr is None:
            pr = api("pulls", "POST", {"title": "Update packaged Vstack skills", "head": BRANCH, "base": "main",
                 "body": f"Generated from trusted main `{base}` and upstream `{pin}`.\n\nAdd the `manual-review` label to stop automation.\n\n{MARKER}"})
        merge(pr, head, base, pin, previous_head=previous if head != previous else None)


if __name__ == "__main__":
    try:
        main()
    except (Stop, sync.Invalid, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Updater stopped: {exc}")
