"""Offline regression tests for the lab's gate; not Linux sandbox acceptance."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VM = ROOT / "tools/devbox/vm"


class NixProbeTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="devbox-nix-state-test-"))
        source = (VM / "nix-native-provision.sh").read_text()
        start = source.index("if [[ -e $state ]]; then")
        end = source.index("\nfi", start) + len("\nfi")
        # Execute only the existing-state gate, never root provisioning/install.
        self.gate = "set -euo pipefail\nstate=$1\n" + source[start:end]

    def retained_result(self, text=None):
        if text is not None:
            (self.state / "result.txt").write_text(text)
        return subprocess.run(
            ["bash", "-c", self.gate, "gate", str(self.state)],
            capture_output=True,
            text=True,
            timeout=5,
        ).returncode

    def test_missing_result_is_not_success(self):
        self.assertNotEqual(self.retained_result(), 0)

    def test_failed_result_is_not_success(self):
        self.assertNotEqual(self.retained_result("stage=sandbox-build\nexit=1\n"), 0)

    def test_partial_result_is_not_success(self):
        self.assertNotEqual(self.retained_result("stage=passed\n"), 0)

    def test_passed_result_is_retained_without_retry(self):
        self.assertEqual(self.retained_result("stage=passed\nexit=0\n"), 0)

    def test_symlink_result_is_rejected(self):
        target = self.state / "target"
        target.write_text("stage=passed\nexit=0\n")
        (self.state / "result.txt").symlink_to(target)
        self.assertNotEqual(self.retained_result(), 0)

    def test_probe_requires_real_local_build_without_fallback(self):
        runner = (VM / "sandbox-probe.sh").read_text()
        for flag in [
            "--store daemon",
            "--option sandbox true",
            "--option sandbox-fallback false",
            "--option builders ''",
            "--option substitute false",
            "--rebuild",
        ]:
            self.assertIn(flag, runner)
        expression = (ROOT / "infra/devbox/nix/sandbox-probe.nix").read_text()
        self.assertIn('"--impure"', expression)
        self.assertIn("assert !(builtins.pathExists marker)", expression)
        self.assertIn("allowSubstitutes = false", expression)

    def test_bootstrap_is_isolated_and_has_no_single_user_installer(self):
        source = (ROOT / "infra/devbox/bootstrap.sh").read_text()
        self.assertIn("exec /usr/bin/python3 -I /opt/devbox/nix/bootstrap.py", source)
        self.assertNotIn("/opt/nix-bootstrap/install", source)
        self.assertNotIn("--no-daemon", source)
        policy = (ROOT / "infra/devbox/nix/provision.py").read_text()
        self.assertIn("sandbox = true\nsandbox-fallback = false\n", policy)
        self.assertIn("trusted-users = root\nallowed-users = miyakishota\n", policy)
        self.assertIn("build-users-group = nixbld", policy)

    def test_native_seed_matches_committed_pin(self):
        manifest = json.loads((ROOT / "infra/devbox/artifacts.lock.json").read_text())
        self.assertIn(
            manifest["nix"]["sha256"], (VM / "nix-native-provision.sh").read_text()
        )


if __name__ == "__main__":
    unittest.main()
