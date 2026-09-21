#!/usr/bin/env python3
"""Build self-contained host packages from a pinned public skills commit."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/vllnt/skills.git"
HOSTS = ("claude", "codex", "cursor")
PRINCIPLES = tuple(f"vllnt-{name}-principles" for name in ("thinking", "orchestration", "collaboration"))
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_MEMBERS = 5000
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class Invalid(ValueError):
    pass


def encoded(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def load_lock(root: Path) -> dict:
    lock = json.loads((root / "upstream.lock.json").read_text())
    if set(lock) != {"repository", "commit"} or lock["repository"] != UPSTREAM:
        raise Invalid("lock must select the trusted vllnt/skills repository")
    if not isinstance(lock["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]):
        raise Invalid("lock commit must be a full lowercase 40-character SHA")
    return lock


def local_archive(source: Path, commit: str) -> bytes:
    # Archive the committed objects, never the possibly dirty working tree.
    command = ["git", "-C", str(source), "archive", "--format=tar", commit,
               "LICENSE", "workflows", "mandatory"]
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as proc:
            chunks = []
            size = 0
            deadline = time.monotonic() + 60
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(proc.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise Invalid("git archive timed out")
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_ARCHIVE:
                            raise Invalid("archive exceeds size limit")
                        chunks.append(chunk)
                if proc.wait(timeout=max(1, deadline - time.monotonic())):
                    raise Invalid("git archive failed; check the source repository and pinned commit")
            except BaseException:
                proc.kill()
                proc.wait()
                raise
    return b"".join(chunks)


def download(commit: str) -> bytes:
    url = f"https://api.github.com/repos/vllnt/skills/tarball/{commit}"
    request = urllib.request.Request(url, headers={"User-Agent": "vstack-bundler"})
    chunks = []
    size = 0
    deadline = time.monotonic() + 120
    with urllib.request.urlopen(request, timeout=30) as response:
        while chunk := response.read(65536):
            size += len(chunk)
            if size > MAX_ARCHIVE or time.monotonic() > deadline:
                raise Invalid("download exceeds size or time limit")
            chunks.append(chunk)
    return b"".join(chunks)


def unpack(data: bytes, prefixed: bool = False) -> dict[str, bytes]:
    if len(data) > MAX_ARCHIVE:
        raise Invalid("archive exceeds size limit")
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            data = compressed.read(MAX_ARCHIVE + 1)
        if len(data) > MAX_ARCHIVE:
            raise Invalid("expanded archive exceeds size limit")
    files = {}
    seen = set()
    prefix = None
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for count, member in enumerate(archive, 1):
            if count > MAX_MEMBERS:
                raise Invalid("too many archive members")
            name = member.name.rstrip("/")
            parts = name.split("/")
            if not name or any(p in ("", ".", "..") for p in parts) or "\\" in name:
                raise Invalid(f"unsafe archive path: {name}")
            if name in seen:
                raise Invalid(f"duplicate archive path: {name}")
            seen.add(name)
            if not (member.isdir() or member.isfile()):
                raise Invalid(f"unsupported archive member: {name}")
            if member.size < 0 or member.size > MAX_FILE:
                raise Invalid(f"archive member exceeds size limit: {name}")
            total += member.size
            if total > MAX_TOTAL:
                raise Invalid("archive payload exceeds total limit")
            if prefixed:
                prefix = prefix or parts[0]
                if parts[0] != prefix:
                    raise Invalid("archive has multiple roots")
                parts = parts[1:]
            if member.isdir():
                continue
            if not parts:
                raise Invalid("archive root is not a directory")
            path = "/".join(parts)
            # Read every file, even excluded ones, under the same resource limits.
            stream = archive.extractfile(member)
            content = stream.read(MAX_FILE + 1)
            if len(content) != member.size:
                raise Invalid(f"archive member size mismatch: {name}")
            if path == "LICENSE" or parts[0] in ("workflows", "mandatory"):
                files[path] = content
    return files


def metadata(content: bytes) -> tuple[str, str, str]:
    text = content.decode("utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise Invalid("skill requires flat frontmatter")
    header, body = text[4:].split("\n---\n", 1)
    fields = {}
    for line in header.splitlines():
        match = re.fullmatch(r"(name|description|license|compatibility): (.+)", line)
        if not match or match[1] in fields:
            raise Invalid("unsupported or duplicate skill metadata")
        value = match[2]
        if value.startswith(('"', "'")) and value[-1:] == value[:1]:
            value = value[1:-1]
        fields[match[1]] = value
    name, description = fields.get("name", ""), fields.get("description", "")
    if not NAME.fullmatch(name) or len(description) < 20:
        raise Invalid("invalid skill name or description")
    return name, description, body


def payload(files: dict[str, bytes]) -> tuple[dict[str, bytes], bytes]:
    if "LICENSE" not in files or not files["LICENSE"].strip():
        raise Invalid("upstream LICENSE is required")
    skills = {}
    bodies = {}
    owners = {}
    for path, content in sorted(files.items()):
        parts = PurePosixPath(path).parts
        if len(parts) == 3 and parts[0] in ("workflows", "mandatory") and parts[2] == "SKILL.md":
            name, _, body = metadata(content)
            if name != parts[1] or name in owners:
                raise Invalid(f"duplicate or mismatched skill name: {path}")
            owners[name] = parts[0]
            bodies[name] = body
    if set(name for name, category in owners.items() if category == "mandatory") != set(PRINCIPLES):
        raise Invalid("mandatory principle inventory changed; review the adapter")
    if not any(category == "workflows" for category in owners.values()):
        raise Invalid("public workflows are missing")
    for path, content in sorted(files.items()):
        parts = PurePosixPath(path).parts
        if parts[0] not in ("workflows", "mandatory"):
            continue
        if len(parts) < 3 or owners.get(parts[1]) != parts[0]:
            raise Invalid(f"unowned public file: {path}")
        if parts[-1] == "SKILL.md" and len(parts) != 3:
            raise Invalid(f"nested skill is not public: {path}")
        skills["skills/" + "/".join(parts[1:])] = content
    # Validate local Markdown dependencies within each standalone skill folder.
    for path, content in skills.items():
        if not path.endswith(".md"):
            continue
        text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", content.decode("utf-8"))
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if not target or re.match(r"[a-zA-Z][\w+.-]*:", target):
                continue
            normalized = os.path.normpath(str(PurePosixPath(path).parent / target))
            if not normalized.startswith("/".join(path.split("/")[:2]) + "/") or normalized not in skills:
                raise Invalid(f"missing or nonportable link in {path}: {target}")
    rule = "---\ndescription: Apply Vstack thinking, orchestration, and collaboration principles.\nalwaysApply: true\n---\n\n"
    rule += "<!-- Generated from pinned vllnt/skills mandatory entries; do not edit. -->\n"
    for name in PRINCIPLES:
        body = bodies[name].strip()
        if not body.startswith("## Principles\n") or len(re.findall(r"(?m)^## ", body)) != 1:
            raise Invalid(f"unsupported principle structure: {name}")
        rule += f"\n<!-- Source: mandatory/{name}/SKILL.md -->\n\n{body}\n"
    return skills, rule.encode()


def build(files: dict[str, bytes], lock: dict, version: str) -> dict[str, bytes]:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version):
        raise Invalid("VERSION must contain a semantic version")
    skills, rule = payload(files)
    output = {}
    for host in HOSTS:
        manifest = {"name": "vstack", "version": version,
                    "description": "Vstack portable workflows and engineering principles.",
                    "author": {"name": "vllnt"}, "license": "MIT"}
        if host == "codex":
            manifest["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        manifest_path = {"claude": ".claude-plugin/plugin.json", "codex": "plugin.json",
                         "cursor": ".cursor-plugin/plugin.json"}[host]
        package = {**skills, "LICENSE": files["LICENSE"], manifest_path: encoded(manifest)}
        if host == "cursor":
            package["rules/vstack-principles.mdc"] = rule
        package["SOURCE.json"] = encoded({"upstream": lock, "files": {
            path: hashlib.sha256(content).hexdigest() for path, content in sorted(package.items())}})
        output.update({f"plugins/{host}/{path}": content for path, content in package.items()})
    for host in ("claude", "cursor"):
        output[f".{host}-plugin/marketplace.json"] = encoded({
            "name": "vllnt-stack", "owner": {"name": "vllnt"},
            "plugins": [{"name": "vstack", "source": f"./plugins/{host}"}]})
    output[".agents/plugins/marketplace.json"] = encoded({
        "name": "vllnt-stack", "interface": {"displayName": "Vstack"},
        "plugins": [{"name": "vstack", "source": {"source": "local", "path": "./plugins/codex"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                     "category": "Productivity"}]})
    return output


TARGETS = tuple(f"plugins/{host}" for host in HOSTS) + (
    ".claude-plugin/marketplace.json", ".cursor-plugin/marketplace.json", ".agents/plugins/marketplace.json")


def preflight(root: Path) -> None:
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise Invalid(f"symlink output ancestor: {parent}")
    for target in TARGETS:
        path = root
        for part in PurePosixPath(target).parts:
            path /= part
            if path.is_symlink():
                raise Invalid(f"symlink output: {path}")
            if path.exists() and path != root / target and not path.is_dir():
                raise Invalid(f"non-directory output ancestor: {path}")
        if path.exists():
            if target.startswith("plugins/") and not path.is_dir():
                raise Invalid(f"package output is not a directory: {path}")
            if not target.startswith("plugins/") and not path.is_file():
                raise Invalid(f"marketplace output is not a file: {path}")
            for item in path.rglob("*") if path.is_dir() else ():
                if item.is_symlink() or not (item.is_file() or item.is_dir()):
                    raise Invalid(f"unsupported existing output: {item}")


def actual(root: Path) -> dict[str, bytes]:
    preflight(root)
    files = {}
    for target in TARGETS:
        path = root / target
        for item in path.rglob("*") if path.is_dir() else (path,):
            if item.is_file():
                files[item.relative_to(root).as_posix()] = item.read_bytes()
    return files


def install(root: Path, expected: dict[str, bytes]) -> None:
    preflight(root)
    # Only exact generated targets are replaced. Backups survive until every swap succeeds.
    with tempfile.TemporaryDirectory(prefix=".vstack-stage-", dir=root) as temporary:
        stage = Path(temporary)
        for path, content in expected.items():
            destination = stage / "new" / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        moved = []
        written = []
        try:
            preflight(root)
            for index, target in enumerate(TARGETS):
                destination = root / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    backup = stage / f"backup-{index}"
                    os.replace(destination, backup)
                    moved.append((destination, backup))
                os.replace(stage / "new" / target, destination)
                written.append(destination)
        except BaseException:
            for path in reversed(written):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            for destination, backup in reversed(moved):
                os.replace(backup, destination)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without writing generated files")
    parser.add_argument("--source", type=Path, help="archive the pin from a local Git repository (offline)")
    args = parser.parse_args()
    try:
        preflight(ROOT)
        lock = load_lock(ROOT)
        archive = local_archive(args.source, lock["commit"]) if args.source else download(lock["commit"])
        files = unpack(archive, prefixed=args.source is None)
        expected = build(files, lock, (ROOT / "VERSION").read_text().strip())
        if args.check:
            current = actual(ROOT)
            changed = sorted(path for path in current.keys() | expected.keys() if current.get(path) != expected.get(path))
            if changed:
                raise Invalid("generated output differs; run sync.py:\n" + "\n".join(changed))
        else:
            install(ROOT, expected)
            if actual(ROOT) != expected:
                raise Invalid("read-back differs from generated output")
        print(f"{'Checked' if args.check else 'Built'} {len(expected)} files for {', '.join(HOSTS)} at {lock['commit']}")
        return 0
    except (Invalid, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
