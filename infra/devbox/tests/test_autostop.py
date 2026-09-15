"""Inventory rejection and elapsed-idle behavior; no real processes or writes."""

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "idle-controller" / "autostop.py"
spec = importlib.util.spec_from_file_location("autostop_test_target", SOURCE)
autostop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(autostop)


EMPTY = {
    "terminal": {
        "terminals": [], "totalCount": 0, "truncated": False,
        "hostScope": {"hostIds": ["local"], "omittedHostIds": []},
    },
    "automations": {"automations": [], "items": [], "orphanCount": 0},
    "tab": {"tabs": []},
}


class InventoryTests(unittest.TestCase):
    def query(self, data):
        return lambda args: data[args[0]]

    def test_complete_empty_inventory(self):
        autostop.empty_host(self.query(EMPTY))

    def test_missing_fields_reject(self):
        for category, fields in EMPTY.items():
            for field in fields:
                with self.subTest(category=category, field=field):
                    data = deepcopy(EMPTY)
                    del data[category][field]
                    with self.assertRaises(ValueError):
                        autostop.empty_host(self.query(data))
        for field in ("hostIds", "omittedHostIds"):
            with self.subTest(scope=field):
                data = deepcopy(EMPTY)
                del data["terminal"]["hostScope"][field]
                with self.assertRaises(ValueError):
                    autostop.empty_host(self.query(data))

    def test_any_open_or_incomplete_inventory_rejects(self):
        cases = (
            ("terminal", "terminals", [{"id": "working"}]),
            ("terminal", "totalCount", 1),
            ("terminal", "truncated", True),
            ("terminal", "hostScope", {"hostIds": ["local", "remote"], "omittedHostIds": []}),
            ("terminal", "hostScope", {"hostIds": ["local"], "omittedHostIds": ["remote"]}),
            ("automations", "automations", [{"id": "scheduled"}]),
            ("automations", "items", [{"id": "scheduled"}]),
            ("automations", "orphanCount", 1),
            ("tab", "tabs", [{"id": "browser"}]),
        )
        for category, field, value in cases:
            with self.subTest(category=category, field=field):
                data = deepcopy(EMPTY)
                data[category][field] = value
                with self.assertRaises(ValueError):
                    autostop.empty_host(self.query(data))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.controller = autostop.Controller()
        self.nix = SimpleNamespace(available=True, process=SimpleNamespace(pid=123))
        self.tailscale = Mock()
        self.orca = Mock(poll=Mock(return_value=None))
        self.inventory = Mock(return_value={"idle": True, "services": []})
        self.stop = Mock(return_value=True)
        self.writer = Mock()
        self.config = Mock(return_value=(True, 1800))
        patches = (
            patch.object(autostop.time, "monotonic", side_effect=lambda: self.now),
            patch.object(autostop.safety, "boot_id", return_value="test-boot"),
            patch.object(autostop, "configuration", self.config),
            patch.object(autostop, "check", self.inventory),
            patch.object(autostop, "stop", self.stop),
            patch.object(autostop, "atomic_json", self.writer),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def tick(self, now):
        self.now = now
        return self.controller.tick(self.nix, self.tailscale, self.orca)

    def test_stops_only_after_thirty_minutes(self):
        for now in range(0, 1800, 30):
            self.assertFalse(self.tick(now))
        self.stop.assert_not_called()
        self.assertTrue(self.tick(1800))
        self.stop.assert_called_once_with(self.nix.process, self.tailscale, self.orca)

    def test_connection_resets_full_idle_window(self):
        for now in range(0, 900, 30):
            self.assertFalse(self.tick(now))
        self.inventory.side_effect = ValueError("Client connected")
        self.assertFalse(self.tick(900))
        self.assertEqual(self.controller.state["idle_for"], 0)
        self.inventory.side_effect = None
        for now in range(930, 2730, 30):
            self.assertFalse(self.tick(now))
        self.stop.assert_not_called()
        self.assertTrue(self.tick(2730))

    def test_disabled_skips_inventory_and_stop(self):
        self.config.return_value = (False, 1800)
        self.assertFalse(self.tick(0))
        self.assertFalse(self.tick(1800))
        self.inventory.assert_not_called()
        self.stop.assert_not_called()
        self.assertFalse(self.controller.state["enabled"])

    def test_observation_gap_restarts_window(self):
        self.assertFalse(self.tick(0))
        self.assertFalse(self.tick(1800))
        self.stop.assert_not_called()
        self.assertEqual(self.controller.state["idle_for"], 0)

    def test_status_write_failure_does_not_escape(self):
        self.writer.side_effect = OSError("fixture status write failure")
        self.assertFalse(self.tick(0))
        self.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
