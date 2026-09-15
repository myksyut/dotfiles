"""Nix-aware readiness/finalization cannot accept legacy or unknown evidence."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_devbox import SafetyFixture, stop, supervisor


class NixSupervisorTests(SafetyFixture):
    def test_finalization_requires_positive_nix_evidence_before_tailscale(self):
        self.safety.begin_drain()
        service = Mock(wait=Mock(return_value=0))
        self.assertFalse(
            supervisor.finalize_stop(
                {},
                service,
                process_check=list,
                sync=lambda: None,
                nix_check=lambda: False,
            )
        )
        service.terminate.assert_not_called()
        self.assertTrue(self.safety.recovery_required())

    def test_missing_intermediate_ack_blocks_default_finalization(self):
        self.safety.begin_drain()
        service = Mock(wait=Mock(return_value=0))
        with patch.object(
            supervisor.nix_runtime, "assert_stopped", side_effect=ValueError("missing")
        ):
            self.assertFalse(
                supervisor.finalize_stop(
                    {}, service, process_check=list, sync=lambda: None
                )
            )
        service.terminate.assert_not_called()

    def test_home_ready_requires_new_schema_and_matching_generation(self):
        generation = "a" * 64
        marker = {"schema": 2, "generation_digest": generation}
        state = {
            "schema": 2,
            "nix_mode": "multi-user",
            "phase": "home-ready",
            "nix_generation": generation,
            "exit_code": 0,
        }
        with patch.object(supervisor, "read_json", side_effect=[marker, state]):
            self.assertTrue(supervisor.home_ready(generation))
        for change in (
            {"schema": 1},
            {"nix_generation": "b" * 64},
            {"phase": "failed"},
            {"exit_code": 1},
        ):
            with (
                self.subTest(change=change),
                patch.object(
                    supervisor, "read_json", side_effect=[marker, {**state, **change}]
                ),
            ):
                self.assertFalse(supervisor.home_ready(generation))
        self.assertFalse(supervisor.home_ready())

    def test_reaper_never_consumes_tracked_popen_exit_status(self):
        parent = self.directory / "7/task/7"
        parent.mkdir(parents=True)
        (parent / "children").write_text("42 43 44")
        waiter = Mock(return_value=(44, 0))
        supervisor.reap_untracked(
            [SimpleNamespace(pid=42), SimpleNamespace(pid=43)],
            proc=self.directory,
            parent=7,
            waitpid=waiter,
        )
        self.assertEqual(waiter.call_count, 1)
        self.assertEqual(waiter.call_args.args[0], 44)

    def test_real_saved_and_build_uids_detected_without_proc_owner_assumption(self):
        daemon = importlib.import_module("nix.daemon")
        proc = self.directory / "proc"
        for pid, uids in ((50, "0 10001 0 0"), (51, "0 0 30001 0"), (52, "0 0 0 0")):
            root = proc / str(pid)
            root.mkdir(parents=True)
            (root / "status").write_text("Uid:\t" + uids + "\n")
            fields = (
                ["S", "1", "99" if pid == 52 else "42", "42"] + ["0"] * 15 + ["123"]
            )
            (root / "stat").write_text(str(pid) + " (fixture) " + " ".join(fields))
        self.assertEqual(daemon.worker_pids(proc=proc), [51])
        self.assertEqual(set(stop.developer_processes(proc)), {"50", "51"})
        self.assertEqual(set(daemon.worker_pids(proc=proc, group=42)), {50, 51, 52})

    def test_service_session_is_checked_even_after_setpgid(self):
        proc = self.directory / "proc"
        root = proc / "99"
        root.mkdir(parents=True)
        fields = ["S", "1", "99", "42"] + ["0"] * 15 + ["123"]
        (root / "stat").write_text("99 (fixture) " + " ".join(fields))
        self.assertEqual(supervisor.service_group_members((42,), proc), ["99"])

    def test_orca_spawn_requires_live_nix_and_shared_admission(self):
        with patch.object(supervisor, "spawn") as spawn:
            with self.assertRaises(ValueError):
                supervisor.admitted_orca_spawn(SimpleNamespace(available=False), [], {})
            spawn.assert_not_called()

        def spawn(*_, **__):
            with self.assertRaises(ValueError):
                self.safety.begin_drain()
            return "child"

        with patch.object(supervisor, "spawn", side_effect=spawn):
            self.assertEqual(
                supervisor.admitted_orca_spawn(SimpleNamespace(available=True), [], {}),
                "child",
            )
        self.safety.begin_drain()
        with patch.object(supervisor, "spawn") as spawn:
            with self.assertRaises(ValueError):
                supervisor.admitted_orca_spawn(SimpleNamespace(available=True), [], {})
            spawn.assert_not_called()
