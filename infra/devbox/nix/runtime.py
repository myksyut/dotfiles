"""Single-owner daemon supervisor and root bootstrap/stop controller API."""

import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "idle-controller"))
import safety  # type: ignore[import-not-found]  # noqa: E402, I001

from .boundary import atomic_json, locked, read_json  # pyright: ignore[reportMissingImports]  # noqa: E402
from .control import Channel, await_channel_ack, boot_id, validate_request  # pyright: ignore[reportMissingImports]  # noqa: E402
from .daemon import identity, probe_daemon, start_daemon, worker_pids  # pyright: ignore[reportMissingImports]  # noqa: E402
from .policy import prepared_state  # pyright: ignore[reportMissingImports]  # noqa: E402
from .provision import STATE  # pyright: ignore[reportMissingImports]  # noqa: E402

LEASE = Path("/data/meta/nix-runtime-state.json")
BOOTSTRAP = Path("/data/meta/bootstrap-state.json")


def require_no_failure():
    failure = LEASE.with_name(LEASE.stem + "-failure.json")
    if failure.exists() or failure.is_symlink():
        raise ValueError("Nix runtime failure requires operator review")


def optional_prepared():
    if not STATE.exists() and not STATE.is_symlink():
        return None
    value = read_json(STATE)
    if value.get("phase") == "preparing":
        progress = read_json(BOOTSTRAP)
        if (
            value.get("boot_id") != boot_id()
            or progress.get("boot_id") != boot_id()
            or progress.get("phase") != "started"
        ):
            raise ValueError("Unfinished Nix initialization requires review")
        try:
            with locked(Path("/run/devbox/bootstrap.lock")):
                pass
        except BlockingIOError:
            return None
        raise ValueError("No active bootstrap owns preparing state")
    return prepared_state()


def stop_contract_verified():
    """No production adapter has passed connection/queue/worker containment yet."""
    return False


def observe_drain(request):
    """No validated fixed-version admission/queue containment adapter exists yet."""
    recovery = read_json(safety.RECOVERY)
    if (
        recovery.get("boot_id") != request["boot_id"]
        or recovery.get("drain_id") != request["drain_id"]
        or recovery.get("phase") != "draining"
    ):
        raise ValueError("Nix stop does not match current drain intent")
    # Empty worker lists, socket chmod and a live PID cannot prove drained IPC.
    return False


def ensure_start_request():
    if os.getuid() != 0:
        raise ValueError("Root bootstrap console required")
    deadline = time.monotonic() + 2
    while True:
        try:
            with safety.admission():
                require_no_failure()
                state = prepared_state()
                return Channel().publish("start", state["generation_digest"])
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise ValueError("Nix controller busy") from None
            time.sleep(0.05)


def await_ack(request, *, phase="ready", timeout=45):
    if os.getuid() != 0:
        raise ValueError("Root controller required")
    channel = Channel()
    ack = await_channel_ack(channel, request, phase=phase, timeout=timeout)
    require_no_failure()
    state = prepared_state()
    if state["generation_digest"] != request["generation_digest"]:
        raise ValueError("Nix generation changed while waiting")
    if phase == "ready":
        lease = read_json(LEASE)
        if (
            lease.get("phase") != "running"
            or lease.get("boot_id") != channel.boot
            or lease.get("generation_digest") != state["generation_digest"]
            or lease.get("daemon_pid") != ack.get("daemon_pid")
            or lease.get("daemon_start") != ack.get("daemon_start")
        ):
            raise ValueError("Nix readiness lease is no longer current")
        pid, start = ack.get("daemon_pid"), ack.get("daemon_start")
        if type(pid) is not int or pid <= 0 or not isinstance(start, str):
            raise ValueError("Missing Nix daemon identity")
        process = SimpleNamespace(pid=pid, poll=lambda: None)
        if not probe_daemon(process, start):
            raise ValueError("Nix readiness acknowledgement is no longer live")
    return ack


def request_stop(drain_id):
    if os.getuid() != 0:
        raise ValueError("Root stop controller required")
    require_no_failure()
    state = prepared_state()
    lease = read_json(LEASE)
    if (
        lease.get("phase") != "running"
        or lease.get("boot_id") != boot_id()
        or lease.get("generation_digest") != state["generation_digest"]
    ):
        raise ValueError("No current running Nix lease")
    return Channel().publish(
        "quiesce-stop",
        state["generation_digest"],
        drain_id=drain_id,
        daemon_pid=lease["daemon_pid"],
        daemon_start=lease["daemon_start"],
    )


def assert_stopped(request_id):
    require_no_failure()
    channel = Channel()
    request = channel.read_request(check_deadline=False)
    if (
        request is None
        or request["request_id"] != request_id
        or request["action"] != "quiesce-stop"
    ):
        raise ValueError("Missing intermediate Nix stop request")
    ack = channel.read_ack(request)
    lease = read_json(LEASE)
    state = prepared_state()
    if (
        not ack
        or ack["phase"] != "stopped"
        or lease.get("phase") != "stopped"
        or lease.get("boot_id") != channel.boot
        or lease.get("request_id") != request_id
        or lease.get("generation_digest") != state["generation_digest"]
        or request["generation_digest"] != state["generation_digest"]
    ):
        raise ValueError("Nix stop acknowledgement is stale or incomplete")
    if Path("/proc", str(request["daemon_pid"])).exists():
        raise ValueError("Daemon PID present or reused after stop")
    if worker_pids(group=request["daemon_pid"]):
        raise ValueError("Nix workers remain after stop")
    recovery = read_json(safety.RECOVERY)
    if (
        recovery.get("phase") != "draining"
        or recovery.get("drain_id") != request["drain_id"]
        or recovery.get("boot_id") != channel.boot
    ):
        raise ValueError("Nix stop fence changed")
    return True


class NixRuntime:
    def __init__(
        self,
        *,
        channel=None,
        lease_path=LEASE,
        state_reader=None,
        starter=None,
        probe=None,
        pid_identity=None,
        fence=None,
        process_scan=None,
        drain_probe=None,
    ):
        self.channel = channel or Channel()
        self.lease_path = lease_path
        self.failure_path = lease_path.with_name(lease_path.stem + "-failure.json")
        self.state_reader = state_reader or optional_prepared
        self.starter = starter or start_daemon
        self.probe = probe or probe_daemon
        self.identity = pid_identity or identity
        self.fence = fence or safety.admission
        self.scan = process_scan or worker_pids
        self.drain_probe = drain_probe or observe_drain
        self.process = None
        self.start = ""
        self.generation = None
        self.phase = "not-provisioned"
        self.reason = "NIX_NOT_PROVISIONED"
        self.attempted = False
        self.handled = None
        self.start_deadline = 0.0

    @property
    def available(self):
        return (
            self.phase == "available"
            and self.process is not None
            and self.process.poll() is None
        )

    def _lease(self, phase, request):
        value = {
            "schema": 1,
            "phase": phase,
            "boot_id": self.channel.boot,
            "generation_digest": self.generation,
            "request_id": request["request_id"] if request else None,
            "daemon_pid": self.process.pid if self.process else None,
            "daemon_start": self.start,
        }
        atomic_json(self.lease_path, value, owner=self.channel.owner)

    def _fail(self, request):
        self.phase, self.reason = "needs-review", "NIX_LIFECYCLE_UNVERIFIED"
        # Preserve the previous process/lease identity as failure evidence.
        # Starting/running leases still veto next boot if failure-record IO fails.
        if not self.failure_path.exists() and not self.failure_path.is_symlink():
            with contextlib.suppress(OSError, ValueError):
                atomic_json(
                    self.failure_path,
                    {
                        "schema": 1,
                        "boot_id": self.channel.boot,
                        "generation_digest": self.generation,
                        "reason_code": self.reason,
                        "request_id": request["request_id"] if request else None,
                        "daemon_pid": self.process.pid if self.process else None,
                        "daemon_start": self.start,
                    },
                    owner=self.channel.owner,
                )
        if request is not None:
            with contextlib.suppress(OSError, ValueError):
                self.channel.acknowledge(request, "failed", reason_code=self.reason)

    def _current(self, request):
        current = self.channel.read_request()
        state = self.state_reader()
        if (
            current != request
            or state is None
            or state["generation_digest"] != request["generation_digest"]
        ):
            raise ValueError("Nix state/request changed")
        validate_request(request, self.channel.boot, self.channel.clock())

    def _start(self, request):
        with self.fence():
            self._current(request)
            if self.process is not None or self.attempted:
                raise ValueError("Nix spawn already attempted")
            if self.lease_path.exists() or self.lease_path.is_symlink():
                previous = read_json(self.lease_path, owner=self.channel.owner)
                if (
                    previous.get("schema") != 1
                    or previous.get("phase") != "stopped"
                    or previous.get("generation_digest") != self.generation
                ):
                    raise ValueError("Unclean or incompatible previous Nix lease")
            self.channel.acknowledge(request, "accepted")
            self._lease("starting", request)
            self.attempted = True
            self.phase, self.reason = "starting", "NIX_STARTING"
            self.process = self.starter()
            self.start = self.identity(self.process.pid)["start"]
            self._lease("starting", request)
            self.start_deadline = min(self.channel.clock() + 30, request["deadline"])
            self._finish_start(request)

    def _publish_ready(self, request):
        if self.process is None:
            raise ValueError("Nix process missing")
        self._current(request)
        self._lease("running", request)
        self.channel.acknowledge(
            request, "ready", daemon_pid=self.process.pid, daemon_start=self.start
        )
        self.handled = request["request_id"]
        self.phase, self.reason = "available", "NIX_AVAILABLE"

    def _finish_start(self, request):
        if self.process is None or self.process.poll() is not None:
            raise ValueError("Nix exited during startup")
        if self.channel.clock() >= self.start_deadline:
            raise ValueError("Nix startup deadline elapsed")
        try:
            ready = self.probe(self.process, self.start)
        except (FileNotFoundError, ConnectionRefusedError, subprocess.TimeoutExpired):
            ready = False
        if self.channel.clock() >= self.start_deadline:
            raise ValueError("Nix startup deadline elapsed")
        if ready:
            if BOOTSTRAP.exists():
                progress = read_json(BOOTSTRAP)
                if (
                    progress.get("boot_id") == self.channel.boot
                    and progress.get("phase") == "failed"
                ):
                    raise ValueError("Bootstrap failed before readiness")
            self._publish_ready(request)

    def _running(self, request):
        if self.process is None or self.process.poll() is not None:
            raise ValueError("Nix process exited")
        with self.fence(require_open=False) as stream:
            if safety.load_object(stream).get("state") == "draining":
                if self.identity(self.process.pid)["start"] != self.start:
                    raise ValueError("Nix drain target changed")
                # A validated drain may intentionally reject new IPC probes.
                self.phase, self.reason = "draining", "NIX_AWAITING_DRAIN_PROOF"
                return
            if self.phase == "draining":
                raise ValueError("Nix admission reopened without reconciliation")
            if not self.probe(self.process, self.start):
                raise ValueError("Nix readiness lost")
            if request["request_id"] != self.handled:
                self._publish_ready(request)

    def _stop_target(self, request):
        if (
            self.process is None
            or self.process.poll() is not None
            or request["daemon_pid"] != self.process.pid
            or request["daemon_start"] != self.start
            or self.identity(self.process.pid)["start"] != self.start
        ):
            raise ValueError("Nix stop target changed")
        return self.process

    def _stop(self, request):
        with self.fence(exclusive=True, require_open=False) as stream:
            self._current(request)
            if safety.load_object(stream).get("state") != "draining":
                raise ValueError("Nix stop requires closed admission")
            process = self._stop_target(request)
            proof = self.drain_probe(request)
            if not isinstance(proof, bool) or not proof:
                raise ValueError("Nix connection/queue containment remains unverified")
            self._current(request)  # proof collection may have exhausted its lease
            if self.scan(group=process.pid, exclude=(process.pid,)):
                raise ValueError("Nix worker remains")
            self._current(request)
            self._stop_target(request)
            self._lease("stopping", request)
            self.channel.acknowledge(request, "accepted")
            self._current(request)
            self._stop_target(request)
            process.terminate()
            if process.wait(timeout=30) != 0 or self.scan(group=process.pid):
                raise ValueError("Nix did not stop cleanly or workers remain")
            self._lease("stopped", request)
            self.channel.acknowledge(
                request, "stopped", daemon_pid=process.pid, daemon_start=self.start
            )
            self.handled = request["request_id"]
            self.phase, self.reason = "stopped", "NIX_STOPPED"

    def tick(self):
        request = None
        if self.phase in ("needs-review", "stopped"):
            return self.status()
        try:
            if self.failure_path.exists() or self.failure_path.is_symlink():
                raise ValueError("Prior Nix failure requires operator review")
            state = self.state_reader()
            if state is None:
                if self.attempted:
                    raise ValueError("Prepared store disappeared")
                return self.status()
            generation = state["generation_digest"]
            if self.generation is not None and generation != self.generation:
                raise ValueError("Nix generation changed during supervision")
            self.generation = generation
            request = self.channel.read_request(check_deadline=False)
            if request is None:
                with self.fence():
                    request = self.channel.publish("start", generation)
            if request["generation_digest"] != generation:
                raise ValueError("Nix request generation does not match the store")
            # Intermediate stop is independent of final VM stop-approved.json.
            if (
                request["action"] == "quiesce-stop"
                and request["request_id"] != self.handled
            ):
                self._stop(request)
            elif self.process is not None:
                if self.phase == "starting":
                    with self.fence():
                        self._current(request)
                        self._finish_start(request)
                else:
                    self._running(request)
            elif request["request_id"] != self.handled:
                self._start(request)
        except BlockingIOError:
            pass  # short control/admission contention; retry within request deadline
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            self._fail(request)
        return self.status()

    def status(self):
        return {
            "state": self.phase,
            "reason_code": self.reason,
            "generation_digest": self.generation,
        }
