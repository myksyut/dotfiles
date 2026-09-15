"""Boot-bound private request/ack mailbox; locks are never held while waiting."""

import re
import secrets
import stat
import time
from pathlib import Path

from .boundary import (  # pyright: ignore[reportMissingImports]
    atomic_json,
    directory,
    locked,
    read_json,
)

RUN = Path("/run/devbox/nix-control")
ACTIONS = ("start", "quiesce-stop")
BINDING = ("request_id", "boot_id", "generation_digest", "action")


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def validate_request(value, boot, now, *, check_deadline=True):
    if (
        not isinstance(value, dict)
        or type(value.get("schema")) is not int
        or value["schema"] != 1
    ):
        raise ValueError("Unknown Nix request schema")
    if value.get("boot_id") != boot or not boot:
        raise ValueError("Stale Nix request boot")
    for field, size in (("request_id", 32), ("generation_digest", 64)):
        raw = value.get(field)
        if (
            not isinstance(raw, str)
            or re.fullmatch("[0-9a-f]{" + str(size) + "}", raw) is None
        ):
            raise ValueError("Malformed Nix request identity")
    if value.get("action") not in ACTIONS:
        raise ValueError("Unknown Nix action")
    expected_keys = {"schema", "deadline", *BINDING}
    if value["action"] == "quiesce-stop":
        expected_keys.update(("drain_id", "daemon_pid", "daemon_start"))
    if set(value) != expected_keys:
        raise ValueError("Unexpected Nix request fields")
    deadline = value.get("deadline")
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise ValueError("Invalid Nix request deadline")
    if not 0 <= deadline <= 1e12:
        raise ValueError("Invalid Nix request deadline")
    if check_deadline and not 0 <= deadline - now <= 45:
        raise ValueError("Expired or future Nix request")
    if value["action"] == "quiesce-stop" and (
        not isinstance(value.get("drain_id"), str)
        or re.fullmatch("[0-9a-f]{32}", value["drain_id"]) is None
        or type(value.get("daemon_pid")) is not int
        or value["daemon_pid"] <= 0
        or not isinstance(value.get("daemon_start"), str)
        or re.fullmatch("[0-9]{1,30}", value["daemon_start"]) is None
    ):
        raise ValueError("Incomplete Nix stop target")
    return value


class Channel:
    def __init__(self, path=RUN, *, owner=0, boot=None, clock=None):
        self.path = Path(path)
        self.owner = owner
        self.boot = boot or boot_id()
        self.clock = clock or time.monotonic
        directory(self.path.parent, owner=owner)
        self.path.mkdir(mode=0o700, exist_ok=True)
        info = self.path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != owner
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ValueError("Unsafe Nix control directory")

    def read_request(self, *, check_deadline=True):
        with locked(self.path / "control.lock", owner=self.owner):
            target = self.path / "request.json"
            if not target.exists() and not target.is_symlink():
                return None
            return validate_request(
                read_json(target, owner=self.owner),
                self.boot,
                self.clock(),
                check_deadline=check_deadline,
            )

    def publish(self, action, generation, **target):
        allowed = (
            {"drain_id", "daemon_pid", "daemon_start"}
            if action == "quiesce-stop"
            else set()
        )
        if set(target) != allowed:
            raise ValueError("Unexpected Nix request target fields")
        with locked(self.path / "control.lock", owner=self.owner):
            path = self.path / "request.json"
            if path.exists() or path.is_symlink():
                old = validate_request(
                    read_json(path, owner=self.owner),
                    self.boot,
                    self.clock(),
                    check_deadline=False,
                )
                if old["generation_digest"] != generation:
                    raise ValueError("Cannot replace a different Nix generation")
                if old["action"] == action:
                    validate_request(old, self.boot, self.clock())
                    if any(old.get(key) != val for key, val in target.items()):
                        raise ValueError("Conflicting repeated Nix request")
                    return old
                if old["action"] != "start" or action != "quiesce-stop":
                    raise ValueError("Nix cannot restart after stop request")
            request = {
                "schema": 1,
                "request_id": secrets.token_hex(16),
                "boot_id": self.boot,
                "generation_digest": generation,
                "action": action,
                "deadline": self.clock() + 45,
                **target,
            }
            validate_request(request, self.boot, self.clock())
            atomic_json(path, request, owner=self.owner)
            return request

    def acknowledge(self, request, phase, **details):
        if set(details) - {"daemon_pid", "daemon_start", "reason_code"}:
            raise ValueError("Unexpected Nix acknowledgement fields")
        if phase not in ("accepted", "ready", "failed", "stopped"):
            raise ValueError("Unknown Nix acknowledgement phase")
        if phase == "ready" and request["action"] != "start":
            raise ValueError("Stop cannot acknowledge readiness")
        if phase == "stopped" and request["action"] != "quiesce-stop":
            raise ValueError("Start cannot acknowledge stop")
        ack = {
            "schema": 1,
            **{key: request[key] for key in BINDING},
            **details,
            "phase": phase,
        }
        with locked(self.path / "control.lock", owner=self.owner):
            current = read_json(self.path / "request.json", owner=self.owner)
            if any(current.get(key) != request[key] for key in BINDING):
                raise ValueError("Nix request changed before acknowledgement")
            ack_path = self.path / "ack.json"
            if ack_path.exists() or ack_path.is_symlink():
                previous = read_json(ack_path, owner=self.owner)
                if all(
                    previous.get(key) == request[key] for key in BINDING
                ) and previous.get("phase") in ("ready", "failed", "stopped"):
                    if previous == ack:
                        return previous
                    raise ValueError("Cannot change a terminal Nix acknowledgement")
            atomic_json(ack_path, ack, owner=self.owner)
        return ack

    def read_ack(self, request):
        with locked(self.path / "control.lock", owner=self.owner):
            target = self.path / "ack.json"
            if not target.exists() and not target.is_symlink():
                return None
            value = read_json(target, owner=self.owner)
            if any(value.get(key) != request[key] for key in BINDING):
                return None
            if (
                type(value.get("schema")) is not int
                or value["schema"] != 1
                or value.get("phase")
                not in (
                    "accepted",
                    "ready",
                    "failed",
                    "stopped",
                )
            ):
                raise ValueError("Invalid Nix acknowledgement")
            return value


def await_channel_ack(channel, request, *, phase="ready", timeout=45):
    deadline = min(channel.clock() + timeout, request["deadline"])
    while channel.clock() <= deadline:
        try:
            ack = channel.read_ack(request)
        except BlockingIOError:
            ack = None
        if ack and ack["phase"] == "failed":
            raise ValueError("Nix lifecycle failed; operator review required")
        if ack and ack["phase"] == phase:
            return ack
        time.sleep(0.1)
    raise ValueError("Nix acknowledgement timed out; no automatic retry")
