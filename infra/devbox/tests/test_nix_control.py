"""Control protocol tests run without root, daemon, mounts, or network."""

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("nix.control")
        self.fs = importlib.import_module("nix.boundary")
        self.tmp = tempfile.TemporaryDirectory(dir=Path("/tmp").resolve())
        self.addCleanup(self.tmp.cleanup)
        self.now = 100.0
        self.channel = self.module.Channel(
            Path(self.tmp.name) / "control",
            owner=os.getuid(),
            boot="test-boot",
            clock=lambda: self.now,
        )
        self.generation = "a" * 64

    def request(self):
        return self.channel.publish("start", self.generation)

    def test_same_start_is_idempotent(self):
        first = self.request()
        self.assertEqual(first, self.request())
        self.assertEqual(first, self.channel.read_request())

    def test_ready_ack_binding_and_late_ack_rejected(self):
        request = self.request()
        self.channel.acknowledge(request, "ready", daemon_pid=42, daemon_start="123")
        self.assertEqual(
            self.module.await_channel_ack(self.channel, request)["phase"], "ready"
        )
        self.now = 146
        with self.assertRaises(ValueError):
            self.module.await_channel_ack(self.channel, request)
        with self.assertRaises(ValueError):
            self.request()

    def test_stale_boot_generation_and_malformed_deadlines(self):
        request = self.request()
        for change in (
            {"boot_id": "other"},
            {"generation_digest": "bad"},
            {"deadline": True},
            {"deadline": float("inf")},
            {"deadline": float("nan")},
            {"deadline": 10**400},
            {"deadline": 99},
            {"deadline": 146},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.module.validate_request({**request, **change}, "test-boot", 100)

    def test_stop_is_separate_from_final_vm_approval(self):
        start = self.request()
        self.channel.acknowledge(start, "ready", daemon_pid=42, daemon_start="123")
        self.now = 200
        stop = self.channel.publish(
            "quiesce-stop",
            self.generation,
            drain_id="b" * 32,
            daemon_pid=42,
            daemon_start="123",
        )
        self.assertIsNone(self.channel.read_ack(stop))
        self.channel.acknowledge(stop, "stopped", daemon_pid=42, daemon_start="123")
        self.assertEqual(
            self.module.await_channel_ack(self.channel, stop, phase="stopped")["phase"],
            "stopped",
        )
        self.assertFalse((self.channel.path.parent / "stop-approved.json").exists())
        with self.assertRaises(ValueError):
            self.request()

    def test_failed_ack_is_terminal(self):
        request = self.request()
        self.channel.acknowledge(request, "failed", reason_code="TEST_FAILURE")
        with self.assertRaises(ValueError):
            self.module.await_channel_ack(self.channel, request)
        with self.assertRaises(ValueError):
            self.channel.acknowledge(request, "ready")

    def test_unknown_fields_and_binding_override_refused(self):
        with self.assertRaises(ValueError):
            self.channel.publish("start", self.generation, request_id="c" * 32)
        request = self.request()
        with self.assertRaises(ValueError):
            self.module.validate_request(
                {**request, "argv": ["evil"]}, "test-boot", 100
            )
        with self.assertRaises(ValueError):
            self.channel.acknowledge(request, "ready", boot_id="other")

    def test_control_lock_released_between_calls(self):
        request = self.request()
        with (
            self.fs.locked(self.channel.path / "control.lock", owner=os.getuid()),
            self.assertRaises(BlockingIOError),
        ):
            self.channel.read_ack(request)
        self.channel.acknowledge(request, "accepted")
        self.assertEqual(self.channel.read_ack(request)["phase"], "accepted")


if __name__ == "__main__":
    unittest.main()
