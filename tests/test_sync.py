import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("sync", Path(__file__).resolve().parents[1] / "scripts/sync.py")
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)
LOCK = {"repository": sync.UPSTREAM, "commit": "a" * 40}


def skill(name, body="## Goal\n\nComplete the synthetic test task.\n"):
    return f"---\nname: {name}\ndescription: A synthetic skill for packaging tests.\n---\n\n{body}".encode()


def source():
    files = {"LICENSE": b"Synthetic license\n", "workflows/test-work/SKILL.md": skill("test-work")}
    files.update({f"mandatory/{name}/SKILL.md": skill(name, "## Principles\n\n- Preserve evidence and scope.\n")
                  for name in sync.PRINCIPLES})
    return files


def archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return output.getvalue()


class BuildTests(unittest.TestCase):
    def test_deterministic_standalone_packages_and_provenance(self):
        files = source()
        files["workflows/test-work/references/test.md"] = b"Reference evidence.\n"
        files["workflows/test-work/SKILL.md"] += b"\nRead [reference](references/test.md).\n"
        first = sync.build(files, LOCK, "0.1.0-dev.1")
        self.assertEqual(first, sync.build(dict(reversed(list(files.items()))), LOCK, "0.1.0-dev.1"))
        for host in sync.HOSTS:
            prefix = f"plugins/{host}/"
            package = {p[len(prefix):]: b for p, b in first.items() if p.startswith(prefix)}
            provenance = json.loads(package.pop("SOURCE.json"))
            self.assertEqual(provenance["upstream"], LOCK)
            self.assertEqual(provenance["files"], {p: hashlib.sha256(b).hexdigest() for p, b in package.items()})
            self.assertEqual(package["skills/test-work/SKILL.md"], files["workflows/test-work/SKILL.md"])
            self.assertEqual("rules/vstack-principles.mdc" in package, host == "cursor")
            self.assertEqual(package["LICENSE"], files["LICENSE"])
            self.assertEqual(".claude-plugin/icon.svg" in package, host == "claude")
        self.assertIn(b"data:image/png;base64,", first["plugins/claude/.claude-plugin/icon.svg"])
        claude = json.loads(first[".claude-plugin/marketplace.json"])
        codex = json.loads(first[".agents/plugins/marketplace.json"])
        cursor = json.loads(first[".cursor-plugin/marketplace.json"])
        self.assertEqual(claude["plugins"][0]["source"], "./plugins/claude")
        self.assertEqual(codex["plugins"][0]["source"]["path"], "./plugins/codex")
        self.assertEqual(cursor["plugins"][0]["source"], "./plugins/cursor")
        self.assertIn("description", claude)
        self.assertNotIn("description", cursor)
        manifests = {host: json.loads(first[path]) for host, path in (
            ("claude", "plugins/claude/.claude-plugin/plugin.json"), ("codex", "plugins/codex/plugin.json"),
            ("cursor", "plugins/cursor/.cursor-plugin/plugin.json"))}
        self.assertEqual(manifests["claude"]["repository"], "https://github.com/vllnt/stack")
        self.assertEqual(manifests["claude"]["homepage"], "https://vllnt.com")
        self.assertNotIn("repository", manifests["codex"])
        self.assertNotIn("repository", manifests["cursor"])

    def test_claude_icon_requires_square_png(self):
        png = lambda w, h: b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", w, h)
        self.assertIn(b'viewBox="0 0 256 256"', sync.icon_svg(png(256, 256)))
        for bad in (png(256, 128), png(64, 64), b"<svg/>" + bytes(32)):
            with self.assertRaises(sync.Invalid):
                sync.icon_svg(bad)

    def test_added_and_removed_workflows(self):
        files = source()
        files["workflows/another-task/SKILL.md"] = skill("another-task")
        with_added = sync.build(files, LOCK, "0.1.0")
        del files["workflows/test-work/SKILL.md"]
        with_removed = sync.build(files, LOCK, "0.1.0")
        self.assertIn("plugins/codex/skills/another-task/SKILL.md", with_added)
        self.assertNotIn("plugins/codex/skills/test-work/SKILL.md", with_removed)

    def test_optional_upstream_license_metadata(self):
        body = skill("test-work").replace(b"\n---\n", b"\nlicense: MIT\n---\n", 1)
        self.assertEqual(sync.metadata(body)[0], "test-work")

    def test_invalid_public_sources(self):
        for label, change in [
            ("no license", lambda f: f.pop("LICENSE")),
            ("name mismatch", lambda f: f.update({"workflows/test-work/SKILL.md": skill("wrong-name")})),
            ("duplicate name", lambda f: f.update({"workflows/" + sync.PRINCIPLES[0] + "/SKILL.md": skill(sync.PRINCIPLES[0])})),
            ("hidden skill", lambda f: f.update({"workflows/test-work/references/SKILL.md": skill("hidden-skill")})),
            ("missing principle", lambda f: f.pop(f"mandatory/{sync.PRINCIPLES[0]}/SKILL.md")),
            ("internal metadata", lambda f: f.update({"workflows/test-work/SKILL.md": skill("test-work").replace(b"\n---\n", b"\nmetadata:\n  internal: true\n---\n", 1)})),
            ("missing link", lambda f: f.update({"workflows/test-work/SKILL.md": skill("test-work") + b"[missing](references/no.md)"})),
            ("escaping link", lambda f: f.update({"workflows/test-work/SKILL.md": skill("test-work") + b"[escape](../../LICENSE)"})),
            ("changed principle contract", lambda f: f.update({f"mandatory/{sync.PRINCIPLES[0]}/SKILL.md": skill(sync.PRINCIPLES[0], "## Workflow\nChanged") })),
        ]:
            with self.subTest(label=label):
                files = source()
                change(files)
                with self.assertRaises(sync.Invalid):
                    sync.build(files, LOCK, "0.1.0")

    def test_lock_rejects_moving_or_untrusted_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for lock in ({**LOCK, "commit": "main"}, {**LOCK, "repository": "https://example.invalid/source"}):
                (root / "upstream.lock.json").write_text(json.dumps(lock))
                with self.assertRaises(sync.Invalid):
                    sync.load_lock(root)


class ArchiveTests(unittest.TestCase):
    def test_git_and_github_layouts(self):
        self.assertEqual(sync.unpack(archive(source())), source())
        remote = {"upstream-root/" + p: b for p, b in source().items()}
        remote["upstream-root/.agents/skills/manage-skill/SKILL.md"] = skill("manage-skill")
        self.assertEqual(sync.unpack(gzip.compress(archive(remote)), True), source())

    def test_invalid_paths(self):
        for path in ("/absolute", "../escape", "a/../b", "a//b", "a\\b", "./relative"):
            with self.subTest(path=path), self.assertRaises(sync.Invalid):
                sync.unpack(archive({path: b"x"}))

    def test_links_and_duplicate_members(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as tar:
                info = tarfile.TarInfo("workflows/test-work/link")
                info.type = kind
                info.linkname = "/outside"
                tar.addfile(info)
            with self.assertRaises(sync.Invalid):
                sync.unpack(output.getvalue())
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as tar:
            for _ in range(2):
                tar.addfile(tarfile.TarInfo("LICENSE"), io.BytesIO())
        with self.assertRaises(sync.Invalid):
            sync.unpack(output.getvalue())

    def test_all_resource_limits(self):
        data = archive(source())
        for setting, limit in (("MAX_ARCHIVE", 10), ("MAX_FILE", 5), ("MAX_TOTAL", 10), ("MAX_MEMBERS", 1)):
            with self.subTest(setting=setting), patch.object(sync, setting, limit), self.assertRaises(sync.Invalid):
                sync.unpack(data)
        compressed = gzip.compress(data)
        with patch.object(sync, "MAX_ARCHIVE", len(compressed) + 1), self.assertRaisesRegex(sync.Invalid, "expanded"):
            sync.unpack(compressed)


class OutputTests(unittest.TestCase):
    def test_replace_removes_stale_files_and_preserves_unowned_work(self):
        expected = sync.build(source(), LOCK, "0.1.0")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sync.install(root, expected)
            self.assertEqual(sync.actual(root), expected)
            (root / "plugins/codex/stale.txt").write_text("stale")
            (root / "plugins/unrelated").mkdir()
            (root / "plugins/unrelated/keep.txt").write_text("keep")
            self.assertNotEqual(sync.actual(root), expected)
            sync.install(root, expected)
            self.assertEqual(sync.actual(root), expected)
            self.assertEqual((root / "plugins/unrelated/keep.txt").read_text(), "keep")

    def test_symlink_targets_and_ancestors_rejected_without_external_change(self):
        expected = sync.build(source(), LOCK, "0.1.0")
        for target in ("plugins", "plugins/codex", ".agents", "plugins/cursor/skills/escape"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                base = Path(directory).resolve()
                root, outside = base / "repo", base / "outside"
                root.mkdir(); outside.mkdir()
                (outside / "keep").write_text("safe")
                destination = root / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(sync.Invalid):
                    sync.install(root, expected)
                self.assertEqual(list(outside.iterdir()), [outside / "keep"])
                self.assertEqual((outside / "keep").read_text(), "safe")

    def test_mid_install_error_rolls_back_all_packages(self):
        expected = sync.build(source(), LOCK, "0.1.0")
        updated = sync.build(source(), LOCK, "0.2.0")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sync.install(root, expected)
            replace = sync.os.replace
            calls = 0
            def fail_once(a, b):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("synthetic rename failure")
                return replace(a, b)
            with patch.object(sync.os, "replace", fail_once), self.assertRaises(OSError):
                sync.install(root, updated)
            self.assertEqual(sync.actual(root), expected)

    def test_committed_pin_ignores_dirty_source_and_cli_check_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            upstream = base / "upstream"
            upstream.mkdir()
            for path, data in source().items():
                file = upstream / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(upstream), *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
            commit = git("rev-parse", "HEAD")
            (upstream / "LICENSE").write_text("dirty source should not be bundled")
            self.assertEqual(sync.unpack(sync.local_archive(upstream, commit)), source())
            root = base / "distribution"
            root.mkdir()
            (root / "upstream.lock.json").write_text(json.dumps({**LOCK, "commit": commit}))
            (root / "VERSION").write_text("0.1.0")
            def run(check=False):
                argv = ["sync.py", "--source", str(upstream)] + (["--check"] if check else [])
                with patch.object(sync, "ROOT", root), patch("sys.argv", argv):
                    return sync.main()
            self.assertEqual(run(), 0)
            self.assertEqual(run(True), 0)
            target = root / "plugins/codex/skills/test-work/SKILL.md"
            target.write_text("tampered")
            before = sync.actual(root)
            self.assertEqual(run(True), 1)
            self.assertEqual(sync.actual(root), before)
            self.assertEqual(run(), 0)
            self.assertEqual(run(True), 0)
            (root / "upstream.lock.json").write_text(json.dumps({**LOCK, "commit": "f" * 40}))
            before = sync.actual(root)
            self.assertEqual(run(), 1)
            self.assertEqual(sync.actual(root), before)


if __name__ == "__main__":
    unittest.main()
