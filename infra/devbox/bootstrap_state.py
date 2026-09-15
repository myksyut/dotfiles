"""Root-side checkout validation and non-secret bootstrap progress records."""

import argparse
import os
import re
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "idle-controller"))
import safety  # type: ignore[import-not-found]  # noqa: E402, I001

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nix.boundary import atomic_json  # type: ignore[import-not-found]  # noqa: E402

STATE = Path("/data/meta/bootstrap-state.json")


def validate_checkout(raw, *, home=Path("/home/miyakishota"), owner=10001):
    lexical = Path(raw)
    if (
        not lexical.is_absolute()
        or ".." in lexical.parts
        or any(ord(ch) < 32 for ch in str(raw))
    ):
        raise ValueError("Checkout must be an absolute non-traversing path")
    home_info = home.lstat()
    if (
        not stat.S_ISDIR(home_info.st_mode)
        or home_info.st_uid != owner
        or home_info.st_mode & 0o022
    ):
        raise ValueError("Developer HOME must be a safe owned directory, not a symlink")
    base = home.resolve(strict=True)
    resolved = lexical.resolve(strict=True)
    if resolved == base or not resolved.is_relative_to(base):
        raise ValueError("Resolved checkout must remain below the developer HOME")
    # Reject symlink components even when they happen to resolve inside HOME.
    current = lexical
    while current != home:
        info = current.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != owner
            or info.st_mode & 0o022
        ):
            raise ValueError(
                "Checkout directories must be developer-owned, safe directories"
            )
        if current == current.parent:
            raise ValueError("Checkout is not lexically below HOME")
        current = current.parent
    for name in ("flake.nix", "flake.lock"):
        info = (resolved / name).lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != owner
            or info.st_mode & 0o022
            or info.st_nlink != 1
        ):
            raise ValueError(
                "Flake files must be regular developer-owned files, without writable groups or links"
            )
    return str(resolved)


def record(phase, stage, exit_code, *, path=STATE, nix_generation=None):
    if phase not in ("started", "failed", "home-ready") or stage not in (
        "initializing",
        "provisioning",
        "daemon-start",
        "sandbox",
        "hm-build",
        "hm-activate",
        "profile",
        "recording",
    ):
        raise ValueError("Invalid bootstrap phase/stage")
    if type(exit_code) is not int or exit_code < 0:
        raise ValueError("Invalid bootstrap exit code")
    if nix_generation is not None and (
        not isinstance(nix_generation, str)
        or re.fullmatch("[0-9a-f]{64}", nix_generation) is None
    ):
        raise ValueError("Invalid Nix generation")
    if phase == "home-ready" and (
        not nix_generation or exit_code != 0 or stage != "recording"
    ):
        raise ValueError("Home readiness requires a successful current Nix generation")
    atomic_json(
        path,
        {
            "schema": 2,
            "nix_mode": "multi-user",
            "phase": phase,
            "stage": stage,
            "exit_code": exit_code,
            "at": time.time(),
            "boot_id": safety.boot_id(),
            "nix_generation": nix_generation,
        },
        owner=safety.ROOT_UID,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout")
    parser.add_argument("--record", choices=["started", "failed", "home-ready"])
    parser.add_argument("--stage", default="initializing")
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--nix-generation")
    args = parser.parse_args()
    try:
        if os.getuid() != 0:
            raise ValueError("Bootstrap operations require the root operator console")
        if args.checkout and not args.record:
            print(validate_checkout(args.checkout))
        elif args.record and not args.checkout:
            record(
                args.record,
                args.stage,
                args.exit_code,
                nix_generation=args.nix_generation,
            )
        else:
            raise ValueError("Choose checkout validation or progress recording")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Bootstrap validation/state failed: {exc}") from exc
