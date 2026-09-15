#!/usr/bin/env python3
"""Create an allowlisted OCI lab tarball locally. Never copies HOME or uploads."""

import argparse
import hashlib
import importlib.util
import io
import json
import os
import stat
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = (
    ".dockerignore",
    "Dockerfile",
    "entrypoint.sh",
    "bootstrap.sh",
    "bootstrap_state.py",
    "backup.sh",
    "firewall.nft",
    "state-paths.json",
    "artifacts.lock.json",
    "nix/__init__.py",
    "nix/boundary.py",
    "nix/provision.py",
    "nix/policy.py",
    "nix/control.py",
    "nix/daemon.py",
    "nix/runtime.py",
    "nix/bootstrap.py",
    "nix/sandbox-probe.nix",
    "supervisor/supervisor.py",
    "supervisor/tailscale_state.py",
    "orca/serve.sh",
    "idle-controller/manual_stop.py",
    "idle-controller/policy.py",
    "idle-controller/safety.py",
    "orca-state-adapter/observe.py",
    "artifacts/nix.tar.xz",
    "artifacts/orca.deb",
    "artifacts/tailscale.tgz",
)


def native_files(snapshot):
    files = {
        f"infra/devbox/{name}": ROOT / "infra/devbox" / name
        for name in RUNTIME
        if name not in ("artifacts/orca.deb", "artifacts/tailscale.tgz")
    }
    for name in ("nix-multi-user-provision.sh", "nix-lab-driver.py"):
        files[f"tools/devbox/vm/{name}"] = ROOT / "tools/devbox/vm" / name
    for path in snapshot.rglob("*"):
        if path.is_file() or path.is_symlink():
            files["home-config/" + path.relative_to(snapshot).as_posix()] = path
    return files


def create_archive(files, output, *, manifest=False):
    records = {}
    retained = output.with_suffix(".members")
    retained.mkdir(mode=0o700)
    with tarfile.open(output, "x") as archive:
        for index, (name, path) in enumerate(sorted(files.items())):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Refuse non-regular source: {name}")
            digest = hashlib.sha256()
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with (
                os.fdopen(descriptor, "rb") as stream,
                (retained / str(index)).open("xb+") as saved,
            ):
                before = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_size > 512 * 1024 * 1024
                ):
                    raise ValueError(f"Invalid or oversized source: {name}")
                remaining = before.st_size
                while remaining:
                    block = stream.read(min(remaining, 1024 * 1024))
                    if not block:
                        raise ValueError(f"Short source: {name}")
                    saved.write(block)
                    digest.update(block)
                    remaining -= len(block)
                after = os.fstat(stream.fileno())
                attributes = (
                    "st_dev",
                    "st_ino",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
                if stream.read(1) or any(
                    getattr(before, key) != getattr(after, key)
                    or getattr(before, key) != getattr(path.lstat(), key)
                    for key in attributes
                ):
                    raise ValueError(f"Source changed while snapshotting: {name}")
                saved.flush()
                saved.seek(0)
                info = tarfile.TarInfo(name)
                info.size = before.st_size
                info.mode = 0o755 if before.st_mode & 0o111 else 0o644
                archive.addfile(info, saved)
            records[name] = {"sha256": digest.hexdigest(), "size": before.st_size}
        if manifest:
            raw = (
                json.dumps({"schema": 1, "files": records}, sort_keys=True) + "\n"
            ).encode()
            info = tarfile.TarInfo("input-manifest.json")
            info.size, info.mode = len(raw), 0o600
            archive.addfile(info, io.BytesIO(raw))
            return hashlib.sha256(raw).hexdigest()
    return None


def main(*, native=False) -> None:
    checker = ROOT / "tools/devbox/check-artifacts.py"
    spec = importlib.util.spec_from_file_location("artifact_gate", checker)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the offline artifact gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        manifest = json.loads((ROOT / "infra/devbox/artifacts.lock.json").read_text())
        module.verify_files(manifest)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Artifact gate refused: {error}") from error
    files = [ROOT / "infra/devbox" / name for name in RUNTIME] + [
        checker,
        ROOT / "tools/devbox/vm/build-smoke.sh",
    ]
    selected = {path.relative_to(ROOT).as_posix(): path for path in files}
    if native:
        spec = importlib.util.spec_from_file_location(
            "nix_snapshot", ROOT / "tools/devbox/check-nix.py"
        )
        if spec is None or spec.loader is None:
            raise ValueError("Cannot load source snapshotter")
        snapshotter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(snapshotter)
        selected = native_files(snapshotter.snapshot())
    output = Path(tempfile.mkdtemp(prefix="devbox-oci-bundle-")) / "source.tar"
    digest = create_archive(selected, output, manifest=native)
    print(output)
    if digest:
        print("manifest-sha256=" + digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native",
        action="store_true",
        help="Fresh db-mu1 payload and root manifest anchor",
    )
    main(native=parser.parse_args().native)
