#!/usr/bin/env python3
"""Evaluate from an allowlisted source snapshot, without staging user changes.
No HOME/.pi/.context/.env files, artifacts or credentials enter this Nix source.
Does not activate configurations, update inputs or configure external builders.
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def snapshot():
    output = Path(tempfile.mkdtemp(prefix="devbox-verification-"))
    names = (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "-z",
                "--",
                "flake.nix",
                "flake.lock",
                "modules",
                "pkgs",
            ]
        )
        .decode()
        .split("\0")
    )
    files = {Path(name) for name in names if name}
    files.update(
        [
            Path("modules/home/hosts/devbox.nix"),
            Path("tools/devbox/devbox"),
            Path("pkgs/devbox/default.nix"),
            Path("infra/devbox/bootstrap_state.py"),
            Path("infra/devbox/bootstrap.sh"),
            Path("infra/devbox/Dockerfile"),
            Path("infra/devbox/.dockerignore"),
            Path("infra/devbox/entrypoint.sh"),
            Path("infra/devbox/state-paths.json"),
            Path("infra/devbox/machine.example.json"),
            Path("infra/devbox/orca/serve.sh"),
            Path("tools/devbox/check-artifacts.py"),
            Path("infra/devbox/artifacts.lock.json"),
            Path("tools/devbox/vm/bundle.py"),
            Path("tools/devbox/vm/build-smoke.sh"),
            Path("tools/devbox/vm/lima.yaml"),
            Path("tools/devbox/vm/nix-native-provision.sh"),
            Path("tools/devbox/vm/sandbox-probe.sh"),
            Path("tools/devbox/vm/sandbox-probe.nix"),
            Path("tools/devbox/vm/nix-multi-user-provision.sh"),
            Path("tools/devbox/vm/nix-lab-driver.py"),
            Path("tools/devbox/check-nix.py"),
        ]
    )
    for name in (
        "__init__.py",
        "boundary.py",
        "provision.py",
        "policy.py",
        "control.py",
        "daemon.py",
        "runtime.py",
        "bootstrap.py",
        "sandbox-probe.nix",
    ):
        files.add(Path("infra/devbox/nix") / name)
    # Only these tests and policy modules are needed by checks.*.devbox-tests.
    for directory in ["tests", "idle-controller", "orca-state-adapter", "supervisor"]:
        files.update(
            p.relative_to(ROOT)
            for p in (ROOT / "infra/devbox" / directory).glob("*.py")
        )
    for relative in files:
        original = ROOT / relative
        if original.is_symlink() or not original.is_file():
            raise ValueError(f"Refuse non-regular source: {relative}")
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
    return output


def nix(command, ref, *args):
    return subprocess.check_output(
        ["nix", command, "--no-write-lock-file", ref, *args], text=True
    ).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-home",
        action="store_true",
        help="Also build Linux activationPackage locally (never activate)",
    )
    args = parser.parse_args()
    source = snapshot()
    print(f"Allowlisted source (retained for inspection): {source}", flush=True)
    base = f"path:{source}"
    for selector in [
        "homeConfigurations.miyakishota@devbox.activationPackage.drvPath",
        "darwinConfigurations.miyagishoutanoMacBook-Pro.system.drvPath",
        "nixosConfigurations.miyaki-wsl.config.system.build.toplevel.drvPath",
        "apps.aarch64-darwin.devbox.program",
    ]:
        print(selector, nix("eval", f"{base}#{selector}", "--raw"), flush=True)
    selections = [
        "homeConfigurations.miyakishota@devbox.config",
        "darwinConfigurations.miyagishoutanoMacBook-Pro.config.home-manager.users.miyakishota",
        "nixosConfigurations.miyaki-wsl.config.home-manager.users.miyakishota",
    ]
    expression = """c: {
      routing = builtins.hashString "sha256" c.home.file.".pi/agents/models.json".text;
      models = builtins.hashString "sha256" c.home.file.".pi/agent/models.json".text;
      keys = builtins.hashString "sha256" c.home.file.".pi/agent/keybindings.json".text;
      remote = c.dotfiles.pi.remoteControl.enable;
    }"""
    try:
        results = [
            json.loads(nix("eval", f"{base}#{s}", "--json", "--apply", expression))
            for s in selections
        ]
    except ValueError as exc:
        raise ValueError(
            "Invalid Nix evaluation JSON; host comparison not verified"
        ) from exc
    for key in ["routing", "models", "keys"]:
        if len({value[key] for value in results}) != 1:
            raise ValueError(f"Host-specific Pi {key} drift")
    if [value["remote"] for value in results] != [False, True, True]:
        raise ValueError("Remote-control host defaults changed")
    print(
        "Pi routing/catalog/keybindings identical across all hosts; remote-control only disabled on devbox.",
        flush=True,
    )
    system = nix("eval", "--impure", "--raw", "--expr", "builtins.currentSystem")
    subprocess.run(
        [
            "nix",
            "build",
            "--no-write-lock-file",
            "--no-link",
            "--builders",
            "",
            f"{base}#checks.{system}.devbox-tests",
            "-L",
        ],
        check=True,
    )
    if args.build_home:
        if system != "x86_64-linux":
            raise ValueError(
                "Linux activation build needs a local x86_64-linux builder"
            )
        subprocess.run(
            [
                "nix",
                "build",
                "--no-write-lock-file",
                "--no-link",
                "--builders",
                "",
                f"{base}#homeConfigurations.miyakishota@devbox.activationPackage",
            ],
            check=True,
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"check-nix failed: {exc}") from exc
