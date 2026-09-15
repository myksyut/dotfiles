"""Nix stop integration must finish BEFORE backup and final VM approval."""

import unittest

from test_devbox import SafetyFixture, stop


class NixStopTests(SafetyFixture):
    def test_intermediate_nix_stop_precedes_backup(self):
        events = []

        def nix_stop(drain_id):
            self.assertEqual(len(drain_id), 32)
            # begin_drain released the admission lock before any handshake wait.
            with self.safety.admission(exclusive=True, require_open=False):
                events.append("nix-stopped")
            return "c" * 32

        result = stop.stop_protocol(
            events.append, lambda: None, list, nix_stop=nix_stop
        )
        self.assertEqual(result, "c" * 32)
        self.assertLess(events.index("save-and-stop"), events.index("nix-stopped"))
        self.assertLess(events.index("nix-stopped"), events.index("backup"))

    def test_nix_stop_failure_never_backs_up_or_reopens(self):
        events = []

        def fail(_):
            raise ValueError("unverified")

        with self.assertRaises(ValueError):
            stop.stop_protocol(events.append, lambda: None, list, nix_stop=fail)
        self.assertNotIn("backup", events)
        self.assertEqual(events[-1], "abort")
        with self.assertRaises(ValueError), self.safety.admission():
            pass

    def test_default_unverified_contract_refuses_before_fencing_or_saving(self):
        events = []
        with self.assertRaises(ValueError):
            stop.stop_protocol(events.append, lambda: None, list)
        self.assertEqual(events, ["validate"])
        with self.safety.admission():
            pass

    def test_backup_failure_never_returns_approval(self):
        def hook(name):
            if name == "backup":
                raise ValueError("failed")

        with self.assertRaises(ValueError):
            stop.stop_protocol(hook, lambda: None, list, nix_stop=lambda _: "c" * 32)


if __name__ == "__main__":
    unittest.main()
