"""Pi/Orca coexistence without touching the real HOME or provider credentials."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "modules/home/merge-pi-settings.sh"
PACKAGES = {
    "AGENT_PI": "/nix/store/00000000000000000000000000000000-agent-pi-test/",
    "PI_HUNK": "npm:pi-hunk",
    "PLANNOTATOR": "npm:@plannotator/pi-extension",
    "CONTEXT_VIEW": "npm:pi-context-view",
    "WEB_ACCESS": "npm:pi-web-access",
    "SESSION_RECALL": "npm:@ogulcancelik/pi-session-recall",
    "PI_FFF": "npm:@ff-labs/pi-fff",
    "PI_LENS": "npm:pi-lens",
    "RPIV_ASK_USER": "npm:@juicesharp/rpiv-ask-user-question",
    "PI_BTW": "npm:pi-btw",
    "CODEX_IMAGE_GEN": "npm:pi-codex-image-gen",
    "PI_VCC": "npm:@sting8k/pi-vcc",
    "PI_LINEAR": "npm:@alasano/pi-linear",
    "SKILL_CREATOR": "npm:@tmustier/pi-skill-creator",
    "ISSUE_PR_WRITING": "/nix/store/00000000000000000000000000000001-issue-pr-writing-test",
    "REMOTE_CONTROL": "npm:pi-remote-control",
    "PI_GOAL": "npm:@narumitw/pi-goal",
    "CODEX_FAST": "npm:@calesennett/pi-codex-fast",
}


class PiMergeTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="devbox-pi-test-"))
        self.path = self.directory / "settings.json"
        self.environment = dict(
            os.environ,
            **PACKAGES,
            DEFAULT_PROVIDER="openai-codex",
            DEFAULT_MODEL="gpt-6-astra",
            DEFAULT_THINKING_LEVEL="high",
            ENABLE_REMOTE_CONTROL="false",
        )

    def merge(self):
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.path)],
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_orca_unmanaged_keys_and_hooks_survive_twice(self):
        # Synthetic unmanaged keys, not claims about Orca's real hook schema.
        hooks = {
            "extensions": ["/opt/orca/managed-pi-hook.ts"],
            "orca": {"hooks": {"enabled": True, "host": "server"}},
        }
        self.path.write_text(
            json.dumps(
                dict(
                    hooks,
                    packages=[
                        {
                            "source": "/opt/orca/managed-pi-package",
                            "extensions": ["hook.ts"],
                        },
                        "npm:pi-remote-control@1.0.4",
                        "/nix/store/00000000000000000000000000000002-pi-remote-control-1.0.5",
                        "npm:unmanaged-extension",
                    ],
                    theme="keep",
                )
            )
        )
        self.path.chmod(0o600)
        self.assertEqual(self.merge().returncode, 0)
        before = self.path.read_bytes()
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)
        result = json.loads(before)
        for key, value in hooks.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result["theme"], "keep")
        self.assertNotIn("pi-remote-control", json.dumps(result["packages"]))
        self.assertIn("npm:unmanaged-extension", result["packages"])
        self.assertEqual(result["defaultModel"], "gpt-6-astra")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            result["packages"][0],
            {"source": "/opt/orca/managed-pi-package", "extensions": ["hook.ts"]},
        )

    def test_mac_wsl_default_remote_is_preserved(self):
        self.environment.pop("ENABLE_REMOTE_CONTROL")
        self.assertEqual(self.merge().returncode, 0)
        self.assertIn(
            "npm:pi-remote-control", json.loads(self.path.read_text())["packages"]
        )

    def test_invalid_original_unchanged(self):
        for value in ["{bad", "", "{}\n{}", "[]", '{"packages":null}']:
            self.path.write_text(value)
            self.assertNotEqual(self.merge().returncode, 0)
            self.assertEqual(self.path.read_text(), value)

    def test_invalid_option_does_not_create_file(self):
        self.environment["ENABLE_REMOTE_CONTROL"] = "maybe"
        self.assertNotEqual(self.merge().returncode, 0)
        self.assertFalse(self.path.exists())

    def test_refuses_symlink(self):
        target = self.directory / "real.json"
        target.write_text("{}")
        self.path.symlink_to(target)
        self.assertNotEqual(self.merge().returncode, 0)
        self.assertEqual(target.read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
