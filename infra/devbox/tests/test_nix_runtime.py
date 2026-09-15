"""Unprivileged tests for the root-managed Nix boundary (no actual daemon)."""

import hashlib
import importlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fs = importlib.import_module("nix.boundary")
        self.provision = importlib.import_module("nix.provision")
        self.tmp = tempfile.TemporaryDirectory(dir=Path("/tmp").resolve())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.owner = os.getuid()

    def test_json_exact_permissions_bounded_and_duplicate_keys(self):
        path = self.root / "state.json"
        self.fs.atomic_json(path, {"phase": "prepared"}, owner=self.owner)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.fs.read_json(path, owner=self.owner)["phase"], "prepared")
        for text in (
            '{"a":1,"a":2}',
            '{"a":NaN}',
            '{"a":1e999}',
            '{"a":' * 1100 + "0" + "}" * 1100,
            '{"a":' * 40 + "0" + "}" * 40,
            '{"a":' + "[" * 40 + "0" + "]" * 40 + "}",
            "[]",
            "x" * 16385,
        ):
            path.write_text(text)
            with self.assertRaises(ValueError):
                self.fs.read_json(path, owner=self.owner)
        path.write_text("{}")
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.fs.read_json(path, owner=self.owner)

    def test_symlink_and_hardlink_control_files_refused(self):
        target = self.root / "target"
        target.write_text("{}")
        target.chmod(0o600)
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            self.fs.atomic_json(link, {}, owner=self.owner)
        hard = self.root / "hard"
        os.link(target, hard)
        with self.assertRaises(ValueError):
            self.fs.read_json(hard, owner=self.owner)
        with self.assertRaises(ValueError):
            self.fs.atomic_json(target, {}, owner=self.owner)

    def test_writable_or_link_parent_refused(self):
        parent = self.root / "parent"
        parent.mkdir(mode=0o700)
        link = self.root / "parent-link"
        link.symlink_to(parent)
        with self.assertRaises(ValueError):
            self.fs.atomic_json(link / "state", {}, owner=self.owner)
        parent.chmod(0o777)
        with self.assertRaises(ValueError):
            self.fs.atomic_json(parent / "state", {}, owner=self.owner)

    def archive(self, entries):
        path = self.root / "seed.tar.xz"
        with tarfile.open(path, "w:xz") as archive:
            for name, kind, value in entries:
                item = tarfile.TarInfo("seed/" + name)
                item.mode = 0o755 if kind == "dir" else 0o644
                if kind == "link":
                    item.type = tarfile.SYMTYPE
                    item.linkname = value
                    archive.addfile(item)
                elif kind == "dir":
                    item.type = tarfile.DIRTYPE
                    archive.addfile(item)
                else:
                    data = value.encode()
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
        path.chmod(0o600)
        return path

    def test_seed_hash_checked_before_archive_read(self):
        path = self.archive([("store/pkg/file", "file", "data")])
        with self.assertRaisesRegex(ValueError, "digest"):
            self.provision.inspect_archive(path, "0" * 64, owner=self.owner)

    def test_archive_escape_and_link_parent_refused(self):
        cases = [
            [("../escape", "file", "bad")],
            [("store/pkg/link", "link", "/etc/passwd")],
            [("store/pkg/link", "link", "../../../outside")],
            [("store/pkg/dir", "link", "other"), ("store/pkg/dir/file", "file", "bad")],
            [("store/pkg/file", "file", "a"), ("store/pkg/file", "file", "b")],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                path = self.archive(entries)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    self.provision.inspect_archive(path, digest, owner=self.owner)

    def test_fresh_store_and_failed_state_are_distinct(self):
        store = self.root / "nix"
        store.mkdir(mode=0o755)
        store.chmod(0o755)  # Explicit fixture mode, independent of caller umask.
        state = self.root / "nix-state.json"
        self.provision.require_fresh(store, state, owner=self.owner)
        self.fs.atomic_json(state, {"phase": "failed"}, owner=self.owner)
        with self.assertRaises(ValueError):
            self.provision.require_fresh(store, state, owner=self.owner)
        other = self.root / "other-state.json"
        (store / "unknown").write_text("not trusted")
        with self.assertRaises(ValueError):
            self.provision.require_fresh(store, other, owner=self.owner)

    def test_valid_closure_links_are_not_confused_with_escapes(self):
        path = self.archive(
            [
                ("store", "dir", ""),
                ("store/pkg", "dir", ""),
                ("store/pkg/file", "file", "data"),
                ("store/pkg/relative", "link", "file"),
                ("store/pkg/absolute", "link", "/nix/store/pkg/file"),
            ]
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        names = self.provision.inspect_archive(path, digest, owner=self.owner)
        self.assertIn("store/pkg/absolute", names)

    def test_management_directories_remain_traversable_with_private_umask(self):
        store = self.root / "nix"
        store.mkdir()
        before = os.umask(0o077)
        try:
            self.provision._management_directories(store)
        finally:
            os.umask(before)
        for directory in store.rglob("*"):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)

    def test_seed_copy_preserves_links_and_readonly_contents(self):
        path = self.archive(
            [
                ("store", "dir", ""),
                ("store/pkg", "dir", ""),
                ("store/pkg/file", "file", "data"),
                ("store/pkg/relative", "link", "file"),
                ("store/pkg/absolute", "link", "/nix/store/pkg/file"),
            ]
        )
        destination = self.root / "destination"
        (destination / "store").mkdir(parents=True)
        sentinel = self.root / "outside"
        sentinel.write_text("unchanged")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.provision.verified_archive(path, digest, owner=self.owner) as (
            archive,
            members,
        ):
            self.provision._copy_seed(archive, members, destination)
        package = destination / "store/pkg"
        self.assertEqual((package / "file").read_text(), "data")
        self.assertEqual((package / "file").stat().st_mode & 0o777, 0o444)
        self.assertEqual(package.stat().st_mode & 0o777, 0o555)
        self.assertEqual((package / "file").stat().st_uid, self.owner)
        self.assertEqual((package / "relative").read_text(), "data")
        self.assertEqual(str((package / "absolute").readlink()), "/nix/store/pkg/file")
        self.assertEqual(sentinel.read_text(), "unchanged")

    def test_archive_member_and_total_size_budgets(self):
        many = (tarfile.TarInfo(f"seed/file{i}") for i in range(10001))
        with self.assertRaisesRegex(ValueError, "budget"):
            self.provision._members(many)
        large = [tarfile.TarInfo(f"seed/file{i}") for i in range(3)]
        for item in large:
            item.size = 400 * 1024 * 1024
        with self.assertRaisesRegex(ValueError, "budget"):
            self.provision._members(large)

    def test_configuration_keeps_developer_untrusted(self):
        settings = self.provision.CONFIG
        self.assertIn("trusted-users = root\n", settings)
        self.assertIn("allowed-users = miyakishota\n", settings)
        self.assertIn("sandbox = true\n", settings)
        self.assertIn("sandbox-fallback = false\n", settings)
        self.assertIn("build-users-group = nixbld\n", settings)
        self.assertIn("auto-allocate-uids = false\n", settings)
        self.assertIn("require-sigs = true\n", settings)
        self.assertIn("max-jobs = 1\ncores = 2\n", settings)


if __name__ == "__main__":
    unittest.main()
