"""Offline lab packaging regressions. No VM operations, downloads or real secrets."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_devbox import ROOT, load

bundle = load("vm_bundle", ROOT / "tools/devbox/vm/bundle.py")


class VMToolsTests(unittest.TestCase):
    def fixture(self, skip=None):
        root = Path(tempfile.mkdtemp(prefix="devbox-bundle-test-"))
        for name in bundle.RUNTIME:
            if name == skip:
                continue
            path = root / "infra/devbox" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        for name in (
            "tools/devbox/check-artifacts.py",
            "tools/devbox/vm/build-smoke.sh",
        ):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((ROOT / name).read_text())
        manifest = json.loads((ROOT / "infra/devbox/artifacts.lock.json").read_text())
        for name in ("nix", "orca", "tailscale"):
            manifest[name]["size_bytes"] = 7
            manifest[name]["sha256"] = hashlib.sha256(b"fixture").hexdigest()
        (root / "infra/devbox/artifacts.lock.json").write_text(json.dumps(manifest))
        return root

    def test_bundle_excludes_unlisted_data(self):
        import tarfile

        root = self.fixture()
        (root / ".pi").mkdir()
        (root / ".pi/auth.json").write_text("synthetic-not-a-secret")
        (root / "infra/devbox/machine.local.json").write_text("synthetic-local-config")
        output = io.StringIO()
        with patch.object(bundle, "ROOT", root), contextlib.redirect_stdout(output):
            bundle.main()
        with tarfile.open(output.getvalue().strip()) as archive:
            members = archive.getmembers()
        expected = {f"infra/devbox/{name}" for name in bundle.RUNTIME}
        expected.update(
            {"tools/devbox/check-artifacts.py", "tools/devbox/vm/build-smoke.sh"}
        )
        self.assertEqual({item.name for item in members}, expected)
        self.assertTrue(all(item.isfile() for item in members))

    def test_runtime_symlink_refused(self):
        root = self.fixture(skip="Dockerfile")
        (root / "infra/devbox/Dockerfile").symlink_to(
            root / "infra/devbox/entrypoint.sh"
        )
        with (
            patch.object(bundle, "ROOT", root),
            self.assertRaisesRegex(ValueError, "non-regular"),
        ):
            bundle.main()

    def test_native_manifest_anchors_exact_regular_members(self):
        import tarfile

        source = Path(tempfile.mkdtemp(prefix="devbox-native-test-"))
        fixture = source / "flake.lock"
        fixture.write_text("public fixture")
        output = source / "payload.tar"
        digest = bundle.create_archive(
            {"home-config/flake.lock": fixture}, output, manifest=True
        )
        with tarfile.open(output) as archive:
            self.assertTrue(all(item.isfile() for item in archive.getmembers()))
            stream = archive.extractfile("input-manifest.json")
            if stream is None:
                self.fail("Regular manifest member missing")
            raw = stream.read()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            record = json.loads(raw)["files"]["home-config/flake.lock"]
            self.assertEqual(record["size"], fixture.stat().st_size)
            self.assertEqual(
                record["sha256"], hashlib.sha256(fixture.read_bytes()).hexdigest()
            )

    def test_archive_uses_hashed_snapshot_not_reopened_source(self):
        import tarfile

        source = Path(tempfile.mkdtemp(prefix="devbox-native-race-test-"))
        fixture = source / "flake.lock"
        fixture.write_bytes(b"before")
        original = tarfile.TarFile.addfile

        def mutate(archive, info, fileobj=None):
            fixture.write_bytes(b"after-edit")
            return original(archive, info, fileobj)

        output = source / "payload.tar"
        with patch.object(tarfile.TarFile, "addfile", mutate):
            bundle.create_archive(
                {"home-config/flake.lock": fixture}, output, manifest=True
            )
        with tarfile.open(output) as archive:
            member = archive.extractfile("home-config/flake.lock")
            manifest = archive.extractfile("input-manifest.json")
            if member is None or manifest is None:
                self.fail("Missing regular members")
            self.assertEqual(member.read(), b"before")
            record = json.load(manifest)["files"]["home-config/flake.lock"]
            self.assertEqual(record["sha256"], hashlib.sha256(b"before").hexdigest())

    def test_native_harness_is_one_shot_and_uses_production_runtime(self):
        shell = (ROOT / "tools/devbox/vm/nix-multi-user-provision.sh").read_text()
        driver = (ROOT / "tools/devbox/vm/nix-lab-driver.py").read_text()
        for item in (
            "lima-db-mu1",
            "DEVBOX_INPUT_SHA256",
            "os.O_NOFOLLOW",
            "No retry.",
        ):
            self.assertIn(item, shell)
        self.assertLess(
            shell.index("apt-get update"), shell.index('mkdir -m 755 "$state"')
        )
        self.assertIn("from nix.runtime import NixRuntime", driver)
        self.assertNotIn("--no-daemon", shell)
        self.assertNotIn("--privileged", shell)
        self.assertNotIn("nix-native-provision.sh", shell)

    def test_lima_no_sharing_and_wildcard_ignore_regression(self):
        # Text regression, in addition to real limactl validate/runtime mount checks.
        text = (ROOT / "tools/devbox/vm/lima.yaml").read_text()
        for value in [
            "mounts: []",
            "loadDotSSHPubKeys: false",
            "forwardAgent: false",
            "propagateProxyEnv: false",
            "guestIPMustBeZero: false",
            "ignore: true",
        ]:
            self.assertIn(value, text)
        self.assertNotIn("\nbase:", text)
