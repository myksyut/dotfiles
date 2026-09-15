"""Startup/input boundary tests. Synthetic node IDs and temporary checkouts only."""

import json
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_devbox import INFRA, SafetyFixture, cli, load, supervisor

network = load("test_tailscale_state", INFRA / "supervisor/tailscale_state.py")
bootstrap = load("test_bootstrap_state", INFRA / "bootstrap_state.py")


class NetworkTests(unittest.TestCase):
    def status(self):
        ips = ["100.64.0.2", "fd7a:115c:a1e0::1"]
        return {
            "BackendState": "Running",
            "TUN": True,
            "TailscaleIPs": ips,
            "Self": {"ID": "nfixture", "Online": True, "TailscaleIPs": list(ips)},
        }

    def test_strict_single_cgnat_ipv4(self):
        self.assertEqual(network.tailscale_ipv4("100.64.0.2"), "100.64.0.2")
        for value in [
            "100.1.2.3",
            "100.128.0.1",
            "100.64.256.1",
            "100.064.0.1",
            "100.64.0.1\n100.64.0.2",
            " 100.64.0.1",
            "100.64.0.1\n",
            "::1",
            None,
            123,
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                network.tailscale_ipv4(value)

    def test_authenticated_node_and_exact_identity_required(self):
        good = self.status()
        result = network.startup_state(good, "nfixture")
        self.assertEqual(result["address"], "100.64.0.2")
        self.assertEqual(result["network"], "authenticated-local")
        for identity in [None, "", "other-node"]:
            self.assertIsNone(network.startup_state(good, identity)["address"])
        for state in ["NeedsLogin", "Stopped", "Starting", "NoState"]:
            self.assertIsNone(
                network.startup_state(dict(good, BackendState=state), "nfixture")[
                    "address"
                ]
            )

    def test_online_tun_and_expiry_are_checked(self):
        for key, value in [
            ("Online", False),
            ("Online", "true"),
            ("Online", 1),
            ("Expired", True),
            ("Expired", "false"),
        ]:
            status = self.status()
            status["Self"][key] = value
            self.assertIsNone(network.startup_state(status, "nfixture")["address"])
        for value in [False, 1, None, "true"]:
            self.assertIsNone(
                network.startup_state(dict(self.status(), TUN=value), "nfixture")[
                    "address"
                ]
            )

    def test_multiple_missing_or_inconsistent_addresses_block(self):
        for ips in [
            [],
            ["::1"],
            ["100.64.0.1", "100.64.0.2"],
            ["100.64.0.1\n100.64.0.2"],
            [1],
        ]:
            status = self.status()
            status["TailscaleIPs"] = ips
            self.assertIsNone(network.startup_state(status, "nfixture")["address"])
        status = self.status()
        status["Self"]["TailscaleIPs"] = ["100.64.0.3"]
        self.assertIsNone(network.startup_state(status, "nfixture")["address"])

    def test_probe_requires_interface_and_keeps_global_readiness_unknown(self):
        def runner(argv, **_):
            self.assertEqual(argv[-2:], ["status", "--json"])
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.status()), "")

        ready = supervisor.probe_network(
            "nfixture", runner=runner, interface_present=lambda: True
        )
        self.assertEqual(ready["address"], "100.64.0.2")
        self.assertEqual(ready["reason_code"], "ORCA_READINESS_UNVERIFIED")
        missing = supervisor.probe_network(
            "nfixture", runner=runner, interface_present=lambda: False
        )
        self.assertIsNone(missing["address"])
        self.assertEqual(missing["reason_code"], "TAILSCALE_TUN_MISSING")

    def test_probe_timeout_and_invalid_json_do_not_start_orca(self):
        def timeout(*_, **__):
            raise subprocess.TimeoutExpired("fixture", 10)

        def invalid(argv, **_):
            return subprocess.CompletedProcess(argv, 0, "{bad", "")

        for runner in [timeout, invalid]:
            self.assertIsNone(
                supervisor.probe_network(
                    "nfixture", runner=runner, interface_present=lambda: True
                )["address"]
            )


class BootstrapTests(SafetyFixture):
    def checkout(self, *, lock=True):
        checkout = self.home / "src/dotfiles"
        checkout.mkdir(parents=True, mode=0o700)
        (checkout / "flake.nix").write_text("{}")
        if lock:
            (checkout / "flake.lock").write_text("{}")
        return checkout

    def validate(self, path):
        return bootstrap.validate_checkout(str(path), home=self.home, owner=os.getuid())

    def test_regular_owned_checkout_accepted(self):
        checkout = self.checkout()
        self.assertEqual(self.validate(checkout), str(checkout))

    def test_traversal_outside_and_directory_symlink_rejected(self):
        checkout = self.checkout()
        alias = self.home / "alias"
        alias.symlink_to(checkout, target_is_directory=True)
        for path in [checkout / "../dotfiles", self.directory, alias]:
            with self.assertRaises(ValueError):
                self.validate(path)

    def test_flake_symlink_rejected(self):
        checkout = self.checkout(lock=False)
        (checkout / "flake.lock").symlink_to(checkout / "flake.nix")
        with self.assertRaises(ValueError):
            self.validate(checkout)

    def test_writable_checkout_rejected(self):
        checkout = self.checkout()
        checkout.chmod(0o777)
        with self.assertRaises(ValueError):
            self.validate(checkout)

    def test_structured_failure_and_success_records(self):
        path = self.directory / "bootstrap-state.json"
        for phase, code in [("started", 0), ("failed", 7), ("home-ready", 0)]:
            stage = "recording" if phase == "home-ready" else "hm-build"
            bootstrap.record(phase, stage, code, path=path, nix_generation="a" * 64)
            data = json.loads(path.read_text())
            self.assertEqual(data["phase"], phase)
            self.assertEqual(data["schema"], 2)
            self.assertEqual(data["nix_mode"], "multi-user")
            self.assertEqual(data["nix_generation"], "a" * 64)
            self.assertEqual(data["exit_code"], code)
            self.assertEqual(data["boot_id"], "test-boot")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ManagerConfigTests(SafetyFixture):
    def config(self):
        path = self.directory / "manager.json"
        path.write_text('{"app":"fixture-app","machine":"0123456789abcd"}')
        path.chmod(0o600)
        return path

    def test_regular_owner_only_config_accepted(self):
        self.assertEqual(cli.manager_config(self.config())["machine"], "0123456789abcd")

    def test_symlink_and_fifo_refused(self):
        alias = self.directory / "alias.json"
        alias.symlink_to(self.config())
        with self.assertRaises((OSError, ValueError)):
            cli.manager_config(alias)
        fifo = self.directory / "fifo.json"
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(ValueError):
            cli.manager_config(fifo)

    def test_permissions_owner_and_schema_refused(self):
        path = self.config()
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            cli.manager_config(path)
        path.chmod(0o600)
        info = path.stat()
        foreign = SimpleNamespace(
            st_mode=info.st_mode, st_uid=os.getuid() + 1, st_nlink=1
        )
        with (
            patch.object(cli.os, "fstat", return_value=foreign),
            self.assertRaises(ValueError),
        ):
            cli.manager_config(path)
        for data in [
            [],
            {"app": "x", "machine": "0123456789abcd", "token": "fixture"},
            {"app": 1, "machine": "0123456789abcd"},
        ]:
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                cli.manager_config(path)

    def test_known_root_service_group_member_blocks_finalization(self):
        proc = self.directory / "proc"
        (proc / "321").mkdir(parents=True)
        fields = ["S", "1", "123", "123"] + ["0"] * 15 + ["999"]
        (proc / "321/stat").write_text("321 (root helper) " + " ".join(fields))
        self.assertEqual(supervisor.service_group_members((123,), proc), ["321"])
        self.assertEqual(supervisor.service_group_members((456,), proc), [])
        self.safety.begin_drain()
        service = SimpleNamespace(terminate=lambda: None, wait=lambda **_: 0)
        with patch.object(supervisor, "service_group_members", return_value=["321"]):
            self.assertFalse(
                supervisor.finalize_stop(
                    {},
                    service,
                    process_check=list,
                    sync=lambda: None,
                    service_groups=(123,),
                    nix_check=lambda: True,
                )
            )
