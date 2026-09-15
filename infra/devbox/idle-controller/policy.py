"""Pure, fail-closed policy for future validated observations. NOT a stop actuator.
The schema is internal, NOT Orca's JSON. Production adapter never declares safe.
"""

import math

SAFE_FLAGS = (
    "host_complete",
    "clients_absent",
    "agents_safe",
    "children_absent",
    "external_work_absent",
    "saved",
    "services_safe",
    "no_holds",
    "drain_verified",
)


def blockers(snapshot, *, boot_id, runtime_id, now, max_age=15):
    if not isinstance(snapshot, dict):
        return ["invalid observation"]
    reasons = []
    if snapshot.get("schema") != 1:
        reasons.append("unknown schema")
    if not boot_id or snapshot.get("boot_id") != boot_id:
        reasons.append("wrong boot")
    if not runtime_id or snapshot.get("runtime_id") != runtime_id:
        reasons.append("wrong/unknown runtime")
    observed = snapshot.get("observed_at")
    if (
        not isinstance(observed, (int, float))
        or isinstance(observed, bool)
        or not math.isfinite(observed)
        or not 0 <= now - observed <= max_age
    ):
        reasons.append("stale/future/invalid observation")
    for name in SAFE_FLAGS:
        value = snapshot.get(name)
        if not isinstance(value, bool) or not value:
            reasons.append(name + " not verified")
    if snapshot.get("errors") != []:
        reasons.append("observation errors or missing error status")
    return reasons


class IdleWindow:
    """Use monotonic time; reset on unknown, gaps, runtime change or clock rollback."""

    def __init__(self, seconds=1800, max_gap=15):
        self.seconds = seconds
        self.max_gap = max_gap
        self.since = None
        self.last = None
        self.identity = None

    def observe(self, safe, identity, monotonic):
        discontinuity = (
            self.last is None
            or self.identity != identity
            or not 0 <= monotonic - self.last <= self.max_gap
        )
        self.last, self.identity = monotonic, identity
        if not isinstance(safe, bool) or not safe or not identity:
            self.since = None
            return False
        if discontinuity or self.since is None:
            self.since = monotonic
        return monotonic - self.since >= self.seconds
