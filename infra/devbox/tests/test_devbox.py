"""Offline tests. No Fly calls, credentials, mounts or service shutdowns."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infra/devbox"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


cli = load("devbox_cli", ROOT / "tools/devbox/devbox")
policy = load("policy", INFRA / "idle-controller/policy.py")
stop = load("manual_stop", INFRA / "idle-controller/manual_stop.py")
adapter = load("observe", INFRA / "orca-state-adapter/observe.py")
supervisor = load("supervisor", INFRA / "supervisor/supervisor.py")
CONFIG = {"app": "test-devbox", "machine": "0123456789abcd"}


class SafetyFixture(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="devbox-fence-test-")).resolve()
        self.home = self.directory / "home"
        self.home.mkdir(mode=0o700)
        self.safety = stop.safety
        for name, value in {
            "ADMISSION": self.directory / "admission",
            "RECOVERY": self.directory / "shutdown-state.json",
            "DEVELOPER_HOME": self.home,
            "ROOT_UID": os.getuid(),
            "DEVELOPER_UID": os.getuid(),
            "boot_id": lambda: "test-boot",
        }.items():
            patcher = patch.object(self.safety, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(cli, "safety", return_value=self.safety)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.safety.initialize_admission()


class SupervisorTests(SafetyFixture):
    def test_only_fresh_manual_approval_with_no_processes(self):
        approval = {
            "at": 100,
            "boot_id": "boot",
            "mode": "manual-validated-hook",
            "nix_stop_request_id": "c" * 32,
        }

        def valid(value, exited=True, pids=()):
            return supervisor.approval_valid(
                value, "boot", 100, orca_exited=exited, developer_pids=pids
            )

        self.assertTrue(valid(approval))
        self.assertFalse(valid(approval, exited=False))
        self.assertFalse(valid(approval, pids=["123"]))
        for field, bad in [
            ("at", 0),
            ("at", 101),
            ("at", "100"),
            ("at", True),
            ("at", float("nan")),
            ("boot_id", "old"),
            ("mode", "auto"),
            ("nix_stop_request_id", None),
            ("nix_stop_request_id", "stale"),
        ]:
            self.assertFalse(valid(dict(approval, **{field: bad})))
        for bad in [None, [], {}, {"at": 100}]:
            self.assertFalse(valid(bad))

    def test_provider_signal_is_not_clean_exit(self):
        with self.assertRaises(SystemExit) as raised:
            supervisor.terminate_requested()
        self.assertEqual(raised.exception.code, 1)

    def test_tailscale_timeout_does_not_mean_ready(self):
        with patch.object(
            supervisor.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("ts", 10),
        ):
            self.assertIsNone(supervisor.private_address())


class PolicyTests(unittest.TestCase):
    def safe(self):
        return dict(
            schema=1,
            boot_id="boot",
            runtime_id="runtime",
            observed_at=100,
            errors=[],
            **dict.fromkeys(policy.SAFE_FLAGS, True),
        )

    def check(self, snapshot):
        return policy.blockers(snapshot, boot_id="boot", runtime_id="runtime", now=100)

    def test_safe(self):
        self.assertEqual(self.check(self.safe()), [])

    def test_every_missing_or_false_flag_blocks(self):
        for key in policy.SAFE_FLAGS:
            for bad in [None, False, "true", 1, [], "waiting", "working", "done"]:
                with self.subTest(key=key, bad=bad):
                    snapshot = self.safe()
                    snapshot[key] = bad
                    self.assertTrue(self.check(snapshot))
            snapshot = self.safe()
            del snapshot[key]
            self.assertTrue(self.check(snapshot))

    def test_bad_observation(self):
        for key, values in {
            "schema": [None, 2],
            "boot_id": [None, "old"],
            "runtime_id": [None, "old"],
            "errors": [None, ["failed"]],
            "observed_at": [None, "100", True, 0, 101, float("nan"), float("inf")],
        }.items():
            for value in values:
                snapshot = self.safe()
                snapshot[key] = value
                self.assertTrue(self.check(snapshot), (key, value))
        self.assertTrue(self.check(None))

    def test_30_minutes_continuous_and_reset(self):
        window = policy.IdleWindow()
        for t in range(0, 1800, 10):
            self.assertFalse(window.observe(True, "runtime", t))
        self.assertTrue(window.observe(True, "runtime", 1800))
        self.assertFalse(window.observe(False, "runtime", 1801))
        self.assertFalse(window.observe(True, "runtime", 1810))

    def test_gap_identity_and_clock_reset(self):
        for identity, t in [("new", 10), ("same", 100), ("same", -1)]:
            window = policy.IdleWindow(seconds=10)
            window.observe(True, "same", 0)
            self.assertFalse(window.observe(True, identity, t))


class StopTests(SafetyFixture):
    def test_order(self):
        phases = []
        stop.stop_protocol(
            phases.append,
            lambda: None,
            list,
            begin_fence=lambda: None,
            nix_stop=lambda _: "c" * 32,
        )
        self.assertEqual(
            phases,
            [
                "validate",
                "drain",
                "verify-quiescent",
                "save-and-stop",
                "backup",
                "verify-stopped",
            ],
        )

    def test_any_phase_failure_blocks(self):
        for failure in [
            "validate",
            "drain",
            "verify-quiescent",
            "save-and-stop",
            "backup",
            "verify-stopped",
        ]:
            phases = []

            def hook(name, phases=phases, failure=failure):
                phases.append(name)
                if name == failure:
                    raise ValueError("mock failure")

            with self.subTest(failure=failure), self.assertRaises(ValueError):
                stop.stop_protocol(
                    hook,
                    lambda: None,
                    list,
                    begin_fence=lambda: None,
                    nix_stop=lambda _: "c" * 32,
                )
            if failure != "validate":
                self.assertEqual(phases[-1], "abort")

    def test_new_hold_after_drain_blocks(self):
        checks = iter([None, ValueError("new hold")])

        def check():
            value = next(checks)
            if value:
                raise value

        with self.assertRaises(ValueError):
            stop.stop_protocol(
                lambda _: None,
                check,
                list,
                begin_fence=lambda: None,
                nix_stop=lambda _: "c" * 32,
            )

    def test_child_and_stale_hold_block(self):
        with self.assertRaises(ValueError):
            stop.stop_protocol(
                lambda _: None,
                lambda: None,
                lambda: ["123"],
                begin_fence=lambda: None,
                nix_stop=lambda _: "c" * 32,
            )
        with self.safety.registry_file(self.home, owner=os.getuid(), write=True):
            pass
        path = self.home / ".local/state/devbox/registry.json"
        for value in [
            {},
            {"schema": 1, "records": {"x": {"state": "running", "boot_id": "old"}}},
        ]:
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                stop.check_registry()
        path.write_text("{bad json")
        with self.assertRaises(ValueError):
            stop.check_registry()

    def test_no_site_hook(self):
        with self.assertRaises((ValueError, OSError)):
            stop.check_hook(Path("/nonexistent-devbox-site-hook"))


class ManagerTests(SafetyFixture):
    def runner(self, states):
        remaining = iter(states)
        calls = []

        def run(argv, **_):
            calls.append(argv)
            if "status" in argv:
                output = {"id": CONFIG["machine"], "state": next(remaining)}
                return subprocess.CompletedProcess(argv, 0, json.dumps(output), "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        return run, calls

    def test_start_exactly_once_and_never_restart(self):
        run, calls = self.runner(["stopped", "starting", "started"])
        result = cli.start_machine(CONFIG, run, lambda _: None)
        self.assertEqual(result["machine"], "started")
        self.assertEqual(sum("start" in c for c in calls), 1)
        self.assertFalse(
            any("restart" in c or "create" in c or "stop" in c for c in calls)
        )

    def test_started_is_noop(self):
        run, calls = self.runner(["started"])
        cli.start_machine(CONFIG, run)
        self.assertEqual(len(calls), 1)

    def test_stopping_waits(self):
        run, calls = self.runner(["stopping", "stopped", "started"])
        cli.start_machine(CONFIG, run, lambda _: None)
        self.assertEqual(sum("start" in c for c in calls), 1)

    def test_bad_state_and_response_refused(self):
        for state in ["destroyed", "suspended", "replacing", "unknown"]:
            run, calls = self.runner([state])
            with self.assertRaises(ValueError):
                cli.start_machine(CONFIG, run)
            self.assertEqual(len(calls), 1)

        def wrong(argv, **_):
            return subprocess.CompletedProcess(
                argv, 0, '{"id":"other","state":"started"}', ""
            )

        with self.assertRaises(ValueError):
            cli.machine_state(CONFIG, wrong)

    def test_start_timeout_no_retry(self):
        run, calls = self.runner(["stopped", "stopped"])
        times = iter([0, 0, 10, 181])
        with self.assertRaises(ValueError):
            cli.start_machine(CONFIG, run, lambda _: None, lambda: next(times))
        self.assertEqual(sum("start" in c for c in calls), 1)

    def test_registry_retains_unknown_and_owner_protection(self):
        home = self.home
        with patch.object(Path, "home", return_value=home):
            with cli.registry() as data:
                data["records"]["job"] = {
                    "owner": os.getuid(),
                    "kind": "job",
                    "state": "completed-unverified",
                }
                data["records"]["other"] = {
                    "owner": os.getuid() + 1,
                    "kind": "hold",
                    "state": "held",
                }
            with self.assertRaises(ValueError):
                cli.release("job", False)
            with self.assertRaises(ValueError):
                cli.release("other", True)
            with patch.object(self.safety, "verify_job_absent") as verify:
                cli.release("job", True)
                verify.assert_called_once()
            with cli.registry() as data:
                self.assertEqual(cli.blockers(data), ["other"])

    def test_command_crash_keeps_registration(self):
        home = self.home
        with (
            patch.object(Path, "home", return_value=home),
            patch.object(cli, "boot_id", return_value="boot"),
            patch.object(cli, "proc_start", return_value="123"),
            patch.object(
                cli.subprocess, "Popen", side_effect=OSError("mock spawn failure")
            ),
        ):
            with self.assertRaises((OSError, ValueError)):
                cli.run_work(["mock-command"])
            with cli.registry() as data:
                self.assertEqual(len(cli.blockers(data)), 1)


class AdapterTests(unittest.TestCase):
    def test_even_empty_success_is_unknown(self):
        output = Path(tempfile.mkdtemp(prefix="devbox-evidence-")) / "capture"

        def fake(argv, **_):
            return subprocess.CompletedProcess(argv, 0, b"{}", b"")

        with patch.object(adapter.subprocess, "run", side_effect=fake):
            snapshot = adapter.observe("/verified/orca-ide", output)
        self.assertFalse(snapshot["auto_stop"])
        self.assertIsNone(snapshot["runtime_id"])
        self.assertTrue(snapshot["errors"])
        self.assertEqual((output / "status.json").stat().st_mode & 0o777, 0o600)

    def test_timeout_is_unknown(self):
        output = Path(tempfile.mkdtemp(prefix="devbox-evidence-")) / "capture"
        with patch.object(
            adapter.subprocess, "run", side_effect=subprocess.TimeoutExpired("orca", 15)
        ):
            snapshot = adapter.observe("/verified/orca-ide", output)
        self.assertEqual(len(snapshot["errors"]), 5)


if __name__ == "__main__":
    unittest.main()
