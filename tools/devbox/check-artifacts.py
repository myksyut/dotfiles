#!/usr/bin/env python3
"""Offline artifact gate. Print commands only; never download, install, or run Docker."""

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
from pathlib import Path

INFRA = Path(__file__).resolve().parents[2] / "infra/devbox"
FILES = {"nix": "nix.tar.xz", "orca": "orca.deb", "tailscale": "tailscale.tgz"}


def validate_manifest(manifest: dict) -> None:
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema")) is not int
        or manifest["schema"] != 1
    ):
        raise ValueError("Expected artifact manifest schema 1")
    if manifest.get("platform") != "linux/amd64":
        raise ValueError("Only linux/amd64 is supported")
    if not re.fullmatch(
        r"ubuntu:24\.04@sha256:[0-9a-f]{64}", str(manifest.get("ubuntu_image"))
    ):
        raise ValueError("Ubuntu must be pinned by digest")
    for name, filename in FILES.items():
        item = manifest.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"Missing {name} record")
        version = item.get("version")
        if not isinstance(version, str) or not re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+", version
        ):
            raise ValueError(f"Invalid fixed {name} version")
        urls = {
            "nix": f"https://releases.nixos.org/nix/nix-{version}/nix-{version}-x86_64-linux.tar.xz",
            "orca": f"https://github.com/stablyai/orca/releases/download/v{version}/orca-ide_{version}_amd64.deb",
            "tailscale": f"https://pkgs.tailscale.com/stable/tailscale_{version}_amd64.tgz",
        }
        if (
            item.get("url") != urls[name]
            or item.get("local_file") != f"artifacts/{filename}"
        ):
            raise ValueError(f"Invalid official URL or local path for {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256"))):
            raise ValueError(f"Missing {name} SHA-256")
        size = item.get("size_bytes")
        if type(size) is not int or not 0 < size <= 512 * 1024 * 1024:
            raise ValueError(f"Invalid {name} size")


def verify_files(manifest: dict, infra: Path = INFRA) -> None:
    validate_manifest(manifest)
    directory = infra / "artifacts"
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise ValueError("artifacts must be a regular directory, not a symlink")
    for name, filename in FILES.items():
        item = manifest[name]
        fd = os.open(directory / filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size != item["size_bytes"]
            ):
                raise ValueError(f"Invalid {name} file type/link count/size")
            digest = hashlib.sha256()
            total = 0
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > item["size_bytes"]:
                    raise ValueError(f"{name} grew during verification")
                digest.update(chunk)
            if total != item["size_bytes"] or digest.hexdigest() != item["sha256"]:
                raise ValueError(f"{name} SHA-256 mismatch; retained for manual review")


def build_command(manifest: dict, infra: Path, docker_host: str) -> str:
    validate_manifest(manifest)
    if (
        not re.fullmatch(r"unix:///[^\s]+", docker_host)
        or ".." in Path(docker_host[7:]).parts
    ):
        raise ValueError(
            "Use an explicit local unix:///absolute/socket Docker endpoint"
        )
    args = [
        "--host",
        docker_host,
        "buildx",
        "build",
        "--builder",
        "default",
        "--load",
        "--platform",
        "linux/amd64",
        "--build-arg",
        f"UBUNTU_IMAGE={manifest['ubuntu_image']}",
    ]
    for name in FILES:
        args.extend(
            ["--build-arg", f"{name.upper()}_SHA256={manifest[name]['sha256']}"]
        )
    args.extend(
        [
            "--build-arg",
            f"ORCA_VERSION={manifest['orca']['version']}",
            "-t",
            "cloud-devbox:gate0",
            str(infra),
        ]
    )
    # An empty client config and explicit default builder avoid inherited auth/remote contexts.
    return (
        "docker_config=$(mktemp -d -t devbox-docker.XXXXXXXX) || exit 1\n"
        "env -u DOCKER_CONTEXT -u DOCKER_HOST -u BUILDX_BUILDER -u DOCKER_TLS_VERIFY "
        '-u DOCKER_CERT_PATH DOCKER_CONFIG="$docker_config" DOCKER_BUILDKIT=1 '
        'docker --config "$docker_config" ' + shlex.join(args)
    )


def download_commands(manifest: dict, infra: Path) -> str:
    validate_manifest(manifest)
    directory = infra / "artifacts"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("Refuse an unsafe artifacts directory")
    target = shlex.quote(str(directory))
    lines = [
        "# Existing files are skipped, not replaced. Run the offline gate afterward.",
        "# Do not run downloads concurrently; --no-clobber is an additional safeguard.",
        f"if [ -L {target} ] || {{ [ -e {target} ] && [ ! -d {target} ]; }}; then",
        "  echo 'Unsafe artifacts directory' >&2; exit 1; fi",
        shlex.join(["mkdir", "-p", str(directory)]) + " || exit 1",
    ]
    for name in FILES:
        item = manifest[name]
        path = shlex.quote(str(infra / item["local_file"]))
        command = shlex.join(
            [
                "curl",
                "--fail",
                "--location",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--max-time",
                "300",
                "--no-clobber",
                "--output",
                str(infra / item["local_file"]),
                item["url"],
            ]
        )
        lines.extend(
            [
                f"if [ -e {path} ] || [ -L {path} ]; then",
                f"  echo 'Existing {name} file: verify or review manually' >&2",
                "else",
                f"  {command} || exit 1",
                "fi",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=INFRA / "artifacts.lock.json")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--print-downloads",
        action="store_true",
        help="Print fixed URLs; skip local file checks",
    )
    modes.add_argument(
        "--print-build",
        action="store_true",
        help="Verify files, then print a local-only build command",
    )
    parser.add_argument("--docker-host", default="unix:///var/run/docker.sock")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        validate_manifest(manifest)
        if args.print_downloads:
            print(download_commands(manifest, INFRA))
        else:
            verify_files(manifest)
            if args.print_build:
                print(build_command(manifest, INFRA, args.docker_host))
            else:
                for name in FILES:
                    print(f"{name} {manifest[name]['version']}: SHA-256 and size match")
                print("Offline checks only. OCI/Linux/Orca execution not verified.")
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f"Artifact gate refused: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
