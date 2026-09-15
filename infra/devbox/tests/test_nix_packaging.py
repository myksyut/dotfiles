"""Packaging boundaries; real image/VM acceptance is recorded separately."""

import json
import unittest

from test_devbox import ROOT, load


class PackagingTests(unittest.TestCase):
    def test_all_nix_helpers_are_allowlisted(self):
        bundle = load("nix_bundle_test", ROOT / "tools/devbox/vm/bundle.py")
        for name in (
            "__init__.py",
            "boundary.py",
            "provision.py",
            "policy.py",
            "control.py",
            "daemon.py",
            "runtime.py",
            "bootstrap.py",
            "sandbox-probe.nix",
        ):
            self.assertIn("nix/" + name, bundle.RUNTIME)
        ignore = (ROOT / "infra/devbox/.dockerignore").read_text()
        self.assertTrue(ignore.startswith("**\n"))
        self.assertIn("!nix/", ignore)
        self.assertNotIn("!artifacts/*", ignore)

    def test_image_has_fixed_build_users_and_root_python(self):
        source = (ROOT / "infra/devbox/Dockerfile").read_text()
        self.assertIn("groupadd --gid 30000 nixbld", source)
        self.assertIn("COPY nix/", source)
        self.assertIn("from nix.provision import CONFIG", source)
        self.assertIn("HOME=/root USER=root LOGNAME=root", source)
        self.assertNotIn("nix-daemon --daemon", source)
        self.assertNotIn("/opt/nix-bootstrap", source)
        smoke = (ROOT / "tools/devbox/vm/build-smoke.sh").read_text()
        self.assertNotIn("test -f /opt/nix-bootstrap/install", smoke)
        self.assertIn("test -f /opt/devbox/nix/provision.py", smoke)
        entry = (ROOT / "infra/devbox/entrypoint.sh").read_text()
        self.assertIn("/usr/bin/python3 -I /opt/devbox/supervisor/supervisor.py", entry)
        self.assertIn("stat -c %u:%g /data/nix", entry)
        self.assertNotIn("home | nix | service-data", entry)

    def test_machine_remains_unpublished_and_does_not_auto_restart(self):
        value = json.loads((ROOT / "infra/devbox/machine.example.json").read_text())
        self.assertEqual(value["config"]["restart"]["policy"], "no")
        self.assertEqual(value["config"]["services"], [])
        self.assertIn("REPLACE_DIGEST", value["config"]["image"])
        manifest = json.loads((ROOT / "infra/devbox/artifacts.lock.json").read_text())
        self.assertIsNone(manifest["oci_digest"])

    def test_store_not_backed_up_socket_is_volatile(self):
        value = json.loads((ROOT / "infra/devbox/state-paths.json").read_text())
        self.assertFalse(value["verified"])
        store = next(item for item in value["paths"] if item["path"] == "/nix")
        self.assertFalse(store["backup"])
        self.assertIn("/nix/var/nix/daemon-socket", value["volatile"])
