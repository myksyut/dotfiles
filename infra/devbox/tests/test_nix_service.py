"""Supervisor state machine: fake processes, real private control files."""

import contextlib
import importlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Process:
    pid = 42
    code = None
    signals = 0

    def poll(self):
        return self.code

    def terminate(self):
        self.signals += 1
        self.code = 0

    def wait(self, timeout):
        return self.code


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("nix.runtime")
        control = importlib.import_module("nix.control")
        self.tmp = tempfile.TemporaryDirectory(dir=Path("/tmp").resolve())
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        # Never consult the real root-private bootstrap on a running Linux devbox.
        bootstrap = patch.object(self.module, "BOOTSTRAP", self.path / "bootstrap.json")
        bootstrap.start()
        self.addCleanup(bootstrap.stop)
        self.now = 100.0
        self.channel = control.Channel(
            self.path / "control",
            owner=os.getuid(),
            boot="test-boot",
            clock=lambda: self.now,
        )
        self.record = {"generation_digest": "a" * 64}
        self.process = Process()
        self.starts = 0
        self.fence_state = "open"
        self.workers = []
        self.proof = False
        self.runtime = self.module.NixRuntime(
            channel=self.channel,
            lease_path=self.path / "lease.json",
            state_reader=lambda: self.record,
            starter=self.start,
            probe=lambda process, start: process.poll() is None,
            pid_identity=lambda pid: {"start": "123", "pgid": 42, "sid": 42},
            fence=self.fence,
            process_scan=lambda **kwargs: self.workers,
            drain_probe=lambda request: self.proof,
        )

    def start(self):
        self.starts += 1
        return self.process

    @contextlib.contextmanager
    def fence(self, *, exclusive=False, require_open=True):
        if require_open and self.fence_state != "open":
            raise ValueError("closed")
        yield io.StringIO('{"state":"' + self.fence_state + '"}')

    def start_request(self):
        assert self.record is not None
        return self.channel.publish("start", self.record["generation_digest"])

    def stop_request(self):
        assert self.record is not None
        self.fence_state = "draining"
        return self.channel.publish(
            "quiesce-stop",
            self.record["generation_digest"],
            drain_id="b" * 32,
            daemon_pid=42,
            daemon_start="123",
        )

    def test_start_replay_spawns_once(self):
        request = self.start_request()
        self.assertEqual(self.runtime.tick()["state"], "available")
        self.assertEqual(self.channel.read_ack(request)["phase"], "ready")
        self.runtime.tick()
        self.assertEqual(self.starts, 1)

    def test_normal_boot_uses_same_dispatcher(self):
        self.assertEqual(self.runtime.tick()["state"], "available")
        self.assertEqual(self.starts, 1)

    def test_unknown_drain_never_signals(self):
        self.runtime.tick()
        stop = self.stop_request()
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.channel.read_ack(stop)["phase"], "failed")
        self.assertEqual(self.process.signals, 0)

    def test_verified_fixture_can_ack_before_final_vm_approval(self):
        self.runtime.tick()
        self.proof = True
        stop = self.stop_request()
        self.assertEqual(self.runtime.tick()["state"], "stopped")
        self.assertEqual(self.channel.read_ack(stop)["phase"], "stopped")
        self.assertEqual(self.process.signals, 1)
        self.assertFalse((self.path / "stop-approved.json").exists())

    def test_build_worker_blocks_even_with_fixture_proof(self):
        self.runtime.tick()
        self.proof = True
        self.workers = [99]
        self.stop_request()
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.process.signals, 0)

    def test_exited_daemon_is_not_restarted(self):
        self.runtime.tick()
        self.process.code = 1
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.runtime.tick()
        self.assertEqual(self.starts, 1)

    def test_expired_request_does_not_spawn(self):
        self.start_request()
        self.now = 146
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.starts, 0)

    def test_new_request_same_generation_reuses_process(self):
        request = self.start_request()
        self.runtime.tick()
        request = {**request, "request_id": "d" * 32}
        fs = importlib.import_module("nix.boundary")
        fs.atomic_json(self.channel.path / "request.json", request, owner=os.getuid())
        self.assertEqual(self.runtime.tick()["state"], "available")
        self.assertEqual(self.channel.read_ack(request)["phase"], "ready")
        self.assertEqual(self.starts, 1)

    def test_pending_start_is_nonblocking_and_deadline_does_not_kill(self):
        self.runtime.probe = lambda *_: False
        self.start_request()
        self.assertEqual(self.runtime.tick()["state"], "starting")
        self.now = 131
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.process.signals, 0)
        self.assertEqual(self.starts, 1)

    def test_draining_does_not_open_new_probe_connections(self):
        self.runtime.tick()
        self.fence_state = "draining"

        def reject_probe(*_):
            self.fail("New IPC during drain")

        self.runtime.probe = reject_probe
        self.assertEqual(self.runtime.tick()["state"], "draining")
        self.assertFalse(self.runtime.available)

    def test_prior_lease_identity_is_preserved_on_refusal(self):
        fs = importlib.import_module("nix.boundary")
        old = {
            "schema": 1,
            "phase": "running",
            "generation_digest": "a" * 64,
            "daemon_pid": 999,
            "daemon_start": "777",
        }
        fs.atomic_json(self.runtime.lease_path, old, owner=os.getuid())
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(fs.read_json(self.runtime.lease_path, owner=os.getuid()), old)
        self.assertTrue(self.runtime.failure_path.exists())
        self.assertEqual(self.starts, 0)

    def test_residual_worker_after_daemon_exit_is_not_stopped(self):
        self.runtime.tick()
        self.proof = True
        stop = self.stop_request()

        def terminate():
            self.process.code = 0
            self.process.signals += 1
            self.workers = [99]

        self.process.terminate = terminate
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.channel.read_ack(stop)["phase"], "failed")
        self.assertEqual(self.process.signals, 1)

    def test_slow_stop_proof_cannot_signal_after_request_expiry(self):
        self.runtime.tick()
        request = self.stop_request()

        def slow_proof(_):
            self.now = request["deadline"] + 1
            return True

        self.runtime.drain_probe = slow_proof
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.process.signals, 0)
        self.assertTrue(self.runtime.failure_path.exists())

    def test_daemon_exit_during_proof_is_not_supervised_clean_stop(self):
        self.runtime.tick()
        self.stop_request()

        def exited(_):
            self.process.code = 0
            return True

        self.runtime.drain_probe = exited
        self.assertEqual(self.runtime.tick()["state"], "needs-review")
        self.assertEqual(self.process.signals, 0)

    def test_no_store_waits_without_installing(self):
        self.record = None
        self.assertEqual(self.runtime.tick()["state"], "not-provisioned")
        self.assertEqual(self.starts, 0)


if __name__ == "__main__":
    unittest.main()
