"""Real flock/fixture-files, fake services. Never touches /run or /data."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from test_devbox import SafetyFixture, cli, stop, supervisor


class FenceTests(SafetyFixture):
    def test_drain_rejects_run_hold_at_every_stop_phase(self):
        attempted = []

        def hook(phase):
            if phase == "validate":
                return
            attempted.append(phase)
            with self.assertRaises(ValueError):
                cli.hold("must not start")
            with self.assertRaises(ValueError):
                cli.run_work(["must-not-execute"])

        with (
            patch.object(Path, "home", return_value=self.home),
            patch.object(cli.subprocess, "Popen") as spawn,
        ):
            stop.stop_protocol(hook, process_check=list, nix_stop=lambda _: "c" * 32)
            spawn.assert_not_called()
        self.assertEqual(
            attempted,
            ["drain", "verify-quiescent", "save-and-stop", "backup", "verify-stopped"],
        )
        self.assertTrue(self.safety.recovery_required())

    def test_registration_holds_fence_through_spawn_and_identity(self):
        def spawn(*_, **__):
            with self.assertRaises(ValueError):
                self.safety.begin_drain()
            return Mock(pid=999999, wait=lambda: 0)

        with (
            patch.object(Path, "home", return_value=self.home),
            patch.object(cli, "boot_id", return_value="test-boot"),
            patch.object(cli, "proc_start", return_value="123"),
            patch.object(cli.subprocess, "Popen", side_effect=spawn),
            patch.object(
                self.safety,
                "proc_info",
                return_value={"start": "456", "pgid": 999999, "sid": 999999},
            ),
        ):
            self.assertEqual(cli.run_work(["mock-command"]), 0)
            with cli.registry(read_only=True) as data:
                item = next(iter(data["records"].values()))
                self.assertEqual(item["child_start"], "456")
                self.assertEqual(item["state"], "completed-unverified")

    def test_missing_or_stale_fence_is_never_open(self):
        with (
            patch.object(self.safety, "ADMISSION", self.directory / "missing"),
            self.assertRaises(ValueError),
            self.safety.admission(),
        ):
            self.fail("Missing fence was accepted")
        with (
            patch.object(self.safety, "boot_id", return_value="next-boot"),
            self.assertRaises(ValueError),
            self.safety.admission(),
        ):
            self.fail("Stale fence was accepted")

    def test_exclusive_fence_blocks_another_process(self):
        code = """import fcntl,sys
with open(sys.argv[1]) as stream:
    try:
        fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(23)
sys.exit(0)
"""
        with self.safety.admission(exclusive=True):
            result = subprocess.run(
                [sys.executable, "-c", code, str(self.safety.ADMISSION)], check=False
            )
            self.assertEqual(result.returncode, 23)

    def test_hold_committed_before_drain_still_blocks_stop(self):
        with (
            patch.object(Path, "home", return_value=self.home),
            patch.object(cli, "boot_id", return_value="test-boot"),
            patch.object(cli, "proc_start", return_value="123"),
        ):
            cli.hold("before drain")
        self.safety.begin_drain()
        with self.assertRaises(ValueError):
            self.safety.check_registry()

    def test_registry_reader_rejects_malformed_records_and_unsafe_modes(self):
        with self.safety.registry_file(self.home, owner=os.getuid(), write=True):
            pass
        path = self.home / ".local/state/devbox/registry.json"
        for record in [
            None,
            [],
            1,
            {"state": "released"},
            {"kind": "job", "state": "released", "owner": "root"},
        ]:
            path.write_text(json.dumps({"schema": 1, "records": {"bad": record}}))
            with self.assertRaises(ValueError):
                self.safety.check_registry()
        path.write_text('{"schema":1,"records":{}}')
        path.chmod(0o666)
        with self.assertRaises(ValueError):
            self.safety.check_registry()

    def test_stop_reader_uses_the_writers_lock(self):
        with self.safety.registry_file(self.home, owner=os.getuid(), write=True):
            pass
        with (
            self.safety.registry_file(self.home, owner=os.getuid(), write=True),
            self.assertRaises(ValueError),
        ):
            self.safety.check_registry()

    def test_symlink_registry_is_not_trusted(self):
        root = self.home / ".local/state/devbox"
        root.mkdir(parents=True, mode=0o700)
        (root / "registry.lock").write_text("")
        (root / "registry.lock").chmod(0o600)
        target = self.directory / "other.json"
        target.write_text('{"schema":1,"records":{}}')
        (root / "registry.json").symlink_to(target)
        with self.assertRaises(ValueError):
            self.safety.check_registry()

    def test_fifo_does_not_block_the_reader(self):
        root = self.home / ".local/state/devbox"
        root.mkdir(parents=True, mode=0o700)
        (root / "registry.lock").write_text("")
        (root / "registry.lock").chmod(0o600)
        os.mkfifo(root / "registry.json", 0o600)
        with self.assertRaises(ValueError):
            self.safety.check_registry()


class FinalizationTests(SafetyFixture):
    def begin(self):
        self.safety.begin_drain()
        return Mock(wait=Mock(return_value=0))

    def test_no_registration_between_final_checks_and_exit(self):
        service = self.begin()
        checks = []

        def probe():
            checks.append("probe")
            with self.assertRaises(ValueError):
                cli.run_work(["must-not-spawn"])
            return []

        with (
            patch.object(Path, "home", return_value=self.home),
            patch.object(cli.subprocess, "Popen") as spawn,
        ):
            self.assertTrue(
                supervisor.finalize_stop(
                    {},
                    service,
                    process_check=probe,
                    sync=lambda: None,
                    nix_check=lambda: True,
                )
            )
            spawn.assert_not_called()
        self.assertEqual(len(checks), 2)
        self.assertFalse(self.safety.recovery_required())
        # Even after finalization returns, admission remains closed until a new boot.
        with self.assertRaises(ValueError), self.safety.admission():
            self.fail("Reopened before exit")

    def test_new_process_after_tailscale_exit_aborts(self):
        service = self.begin()
        checks = iter([[], ["123"]])
        self.assertFalse(
            supervisor.finalize_stop(
                {},
                service,
                process_check=lambda: next(checks),
                sync=lambda: None,
                nix_check=lambda: True,
            )
        )
        self.assertTrue(self.safety.recovery_required())

    def test_sync_failure_retains_recovery_across_boot(self):
        service = self.begin()

        def fail():
            raise OSError("mock sync failure")

        self.assertFalse(
            supervisor.finalize_stop(
                {}, service, process_check=list, sync=fail, nix_check=lambda: True
            )
        )
        self.assertTrue(self.safety.recovery_required())
        with patch.object(self.safety, "boot_id", return_value="next-boot"):
            self.safety.initialize_admission()
            with self.assertRaises(ValueError), self.safety.admission():
                self.fail("Failure reopened admission on next boot")

    def test_metadata_write_failure_retains_recovery(self):
        service = self.begin()

        def fail(*_):
            raise OSError("mock disk full")

        self.assertFalse(
            supervisor.finalize_stop(
                {},
                service,
                process_check=list,
                sync=lambda: None,
                write_state=fail,
                nix_check=lambda: True,
            )
        )
        self.assertTrue(self.safety.recovery_required())

    def test_tailscale_failure_is_not_clean_exit(self):
        service = self.begin()
        service.wait.return_value = 1
        self.assertFalse(
            supervisor.finalize_stop(
                {},
                service,
                process_check=list,
                sync=lambda: None,
                nix_check=lambda: True,
            )
        )
        self.assertTrue(self.safety.recovery_required())


class JobIdentityTests(SafetyFixture):
    def job(self):
        return {
            "state": "completed-unverified",
            "boot_id": "test-boot",
            "child_pid": 123,
            "child_start": "1000",
            "pgid": 123,
            "sid": 123,
        }

    def proc(self, pid, *, start="1000", pgid=123, sid=123):
        root = self.directory / "proc"
        entry = root / str(pid)
        entry.mkdir(parents=True, exist_ok=True)
        fields = ["S", "1", str(pgid), str(sid)] + ["0"] * 15 + [start]
        (entry / "stat").write_text(f"{pid} (process with spaces) " + " ".join(fields))
        return root

    def test_live_child_or_pid_reuse_cannot_release(self):
        for start in ["1000", "different"]:
            proc = self.proc(123, start=start)
            with self.assertRaises(ValueError):
                self.safety.verify_job_absent(self.job(), proc)

    def test_orphaned_session_member_cannot_release(self):
        proc = self.proc(456)
        with self.assertRaises(ValueError):
            self.safety.verify_job_absent(self.job(), proc)

    def test_unknown_identity_or_old_boot_requires_operator(self):
        for change in [
            {"boot_id": "old"},
            {"child_start": None},
            {"pgid": None},
            {"state": "running"},
        ]:
            with self.assertRaises(ValueError):
                self.safety.verify_job_absent(dict(self.job(), **change))

    def test_no_known_members_still_requires_cli_confirmation(self):
        proc = self.directory / "proc"
        proc.mkdir()
        self.safety.verify_job_absent(self.job(), proc)
        with patch.object(Path, "home", return_value=self.home):
            with cli.registry() as data:
                data["records"]["job"] = dict(self.job(), owner=os.getuid(), kind="job")
            with self.assertRaises(ValueError):
                cli.release("job", False)
