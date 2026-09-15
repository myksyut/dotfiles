"""Offline artifact gate tests: synthetic payloads, no downloads or Docker calls."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_devbox import INFRA, ROOT, load

artifacts = load("check_artifacts", ROOT / "tools/devbox/check-artifacts.py")


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((INFRA / "artifacts.lock.json").read_text())
        self.directory = Path(
            tempfile.mkdtemp(prefix="devbox-artifact-test-")
        ).resolve()
        (self.directory / "artifacts").mkdir()

    def payloads(self, skip=None):
        for name, filename in artifacts.FILES.items():
            payload = name.encode()
            self.manifest[name]["sha256"] = hashlib.sha256(payload).hexdigest()
            self.manifest[name]["size_bytes"] = len(payload)
            if name != skip:
                (self.directory / "artifacts" / filename).write_bytes(payload)

    def test_committed_pins_have_valid_shape(self):
        artifacts.validate_manifest(self.manifest)
        self.assertEqual(
            self.manifest["orca"]["verified_cli"],
            self.manifest["orca"]["installed_cli"],
        )
        self.assertIn(
            "Not server readiness", self.manifest["orca"]["cli_verification_scope"]
        )
        self.assertIsNone(self.manifest["oci_digest"])

    def test_exact_local_payloads_pass(self):
        self.payloads()
        artifacts.verify_files(self.manifest, self.directory)

    def test_same_size_wrong_hash_refused(self):
        self.payloads()
        (self.directory / "artifacts/nix.tar.xz").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            artifacts.verify_files(self.manifest, self.directory)

    def test_truncated_payload_refused(self):
        self.payloads()
        (self.directory / "artifacts/nix.tar.xz").write_bytes(b"n")
        with self.assertRaises(ValueError):
            artifacts.verify_files(self.manifest, self.directory)

    def test_missing_file_refused(self):
        self.payloads(skip="nix")
        with self.assertRaises(FileNotFoundError):
            artifacts.verify_files(self.manifest, self.directory)

    def test_symlink_and_fifo_refused(self):
        self.payloads(skip="nix")
        path = self.directory / "artifacts/nix.tar.xz"
        path.symlink_to(self.directory / "artifacts/orca.deb")
        with self.assertRaises(OSError):
            artifacts.verify_files(self.manifest, self.directory)
        other = self.directory / "other"
        (other / "artifacts").mkdir(parents=True)
        os.mkfifo(other / "artifacts/nix.tar.xz")
        with self.assertRaises(ValueError):
            artifacts.verify_files(self.manifest, other)

    def test_directory_symlink_refused(self):
        other = self.directory / "other"
        other.mkdir()
        (other / "artifacts").symlink_to(
            self.directory / "artifacts", target_is_directory=True
        )
        with self.assertRaises(ValueError):
            artifacts.verify_files(self.manifest, other)

    def test_mutable_urls_traversal_and_invalid_metadata_refused(self):
        for key, value in [
            (
                "url",
                "https://github.com/stablyai/orca/releases/latest/download/orca.deb",
            ),
            ("url", "https://example.org/orca.deb"),
            ("version", "latest"),
            ("local_file", "../../private"),
            ("sha256", "REPLACE"),
            ("size_bytes", True),
            ("size_bytes", -1),
        ]:
            bad = copy.deepcopy(self.manifest)
            bad["orca"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                artifacts.validate_manifest(bad)
        for key, value in [
            ("schema", True),
            ("platform", "linux/arm64"),
            ("ubuntu_image", "ubuntu:24.04"),
        ]:
            with self.assertRaises(ValueError):
                artifacts.validate_manifest(dict(self.manifest, **{key: value}))

    def run_download_script(self, script):
        fake_bin = self.directory / "fake-bin"
        fake_bin.mkdir()
        curl = fake_bin / "curl"
        curl.write_text("#!/bin/sh\nexit 99\n")
        curl.chmod(0o700)
        bash = shutil.which("bash")
        assert bash is not None
        return subprocess.run(
            [bash, "-c", script],
            env={"PATH": f"{fake_bin}:{os.environ.get('PATH', os.defpath)}"},
            capture_output=True,
            text=True,
        )

    def test_download_script_skips_existing_files_without_curl(self):
        self.payloads()
        result = self.run_download_script(
            artifacts.download_commands(self.manifest, self.directory)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("Existing"), 3)
        artifacts.verify_files(self.manifest, self.directory)

    def test_download_script_refuses_directory_symlink_before_print_and_execution(self):
        other = self.directory / "other"
        other.mkdir()
        script = artifacts.download_commands(self.manifest, other)
        (other / "artifacts").symlink_to(
            self.directory / "artifacts", target_is_directory=True
        )
        with self.assertRaises(ValueError):
            artifacts.download_commands(self.manifest, other)
        result = self.run_download_script(script)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unsafe artifacts directory", result.stderr)
        self.assertEqual(list((self.directory / "artifacts").iterdir()), [])

    def test_build_prints_only_local_default_builder_and_pinned_arguments(self):
        command = artifacts.build_command(
            self.manifest, self.directory, "unix:///var/run/docker.sock"
        )
        for text in [
            "--host unix:///var/run/docker.sock",
            "--builder default",
            "--load",
            "--platform linux/amd64",
            '--config "$docker_config"',
            "-u DOCKER_CONTEXT",
            "-u BUILDX_BUILDER",
            f"ORCA_VERSION={self.manifest['orca']['version']}",
            self.manifest["ubuntu_image"],
        ]:
            self.assertIn(text, command)
        for endpoint in [
            "ssh://builder",
            "tcp://127.0.0.1:2375",
            "unix://relative",
            "unix:///tmp/../socket",
        ]:
            with self.assertRaises(ValueError):
                artifacts.build_command(self.manifest, self.directory, endpoint)
