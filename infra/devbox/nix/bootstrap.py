"""Explicit root controller; every checkout/build/activation runs as UID10001."""

import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bootstrap_state  # type: ignore[import-not-found]  # noqa: E402

from nix import provision as seed  # type: ignore[import-not-found]  # noqa: E402
from nix import runtime  # type: ignore[import-not-found]  # noqa: E402
from nix.boundary import (  # type: ignore[import-not-found]  # noqa: E402
    atomic_json,
    directory,
    locked,
)
from nix.daemon import worker_pids  # type: ignore[import-not-found]  # noqa: E402

safety = runtime.safety
HOME = "/home/miyakishota"
META = Path("/data/meta")
FIXTURE = Path("/opt/devbox/nix/sandbox-probe.nix")
FLAGS = [
    "--store",
    "daemon",
    "--option",
    "builders",
    "",
    "--option",
    "max-jobs",
    "1",
    "--option",
    "cores",
    "2",
]


def developer_environment():
    return {
        "HOME": HOME,
        "USER": "miyakishota",
        "LOGNAME": "miyakishota",
        "PATH": seed.RUNTIME + "/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "NIX_REMOTE": "daemon",
        "NIX_BECOME": "/usr/bin/false",
        "NIX_CONF_DIR": "/etc/nix",
        "NIX_USER_CONF_FILES": "/dev/null",
        "NIX_SSL_CERT_FILE": seed.CACERT + "/etc/ssl/certs/ca-bundle.crt",
    }


def validate_probe(value, observed):
    if value != "marker-hidden\n":
        raise ValueError("Sandbox marker is not proved hidden")
    if not observed or any(
        type(uid) is not int or uid not in seed.BUILD_UIDS for uid in observed
    ):
        raise ValueError("Missing or invalid outside build UID observation")
    return True


def require_true(value, label):
    if not isinstance(value, bool) or not value:
        raise ValueError(label + " not verified")


def execute_pipeline(checkout, actions):
    generation = None
    stage = "provisioning"

    def progress(name):
        nonlocal stage
        stage = name
        actions.record("started", stage, 0, generation)

    try:
        progress("provisioning")
        state = actions.provision()
        generation = state["generation_digest"]
        progress("daemon-start")
        request = actions.request_start()
        if request["generation_digest"] != generation:
            raise ValueError("Bootstrap daemon generation mismatch")
        ack = actions.await_ready(request)
        if ack.get("phase") != "ready":
            raise ValueError("Bootstrap daemon not ready")
        progress("sandbox")
        require_true(actions.sandbox(state), "Sandbox")
        progress("hm-build")
        activation = actions.build_home(checkout)
        progress("hm-activate")
        actions.activate_home(activation)
        progress("profile")
        require_true(actions.verify_profile(), "Home profile")
        progress("recording")
        actions.finish(state, checkout)
    except Exception:
        with contextlib.suppress(OSError, ValueError):
            actions.record("failed", stage, 1, generation)
        raise


class Actions:
    def __init__(self):
        self.logs = META / "bootstrap-logs"
        directory(META)
        self.logs.mkdir(mode=0o700)
        self.logs.chmod(0o700)
        self.number = 0
        self.active_child = None

    def record(self, phase, stage, code, generation):
        bootstrap_state.record(phase, stage, code, nix_generation=generation)

    def provision(self):
        return seed.provision()

    def request_start(self):
        return runtime.ensure_start_request()

    def await_ready(self, request):
        return runtime.await_ack(request)

    def run_user(self, argv, *, timeout=3600, observe=False, result=True):
        self.number += 1
        output_path = self.logs / f"{self.number:02d}.stdout"
        error_path = self.logs / f"{self.number:02d}.stderr"
        observed = set()
        with output_path.open("xb") as output, error_path.open("xb") as error:
            process = subprocess.Popen(
                ["/usr/sbin/runuser", "-u", "miyakishota", "--", *argv],
                env=developer_environment(),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=error,
                start_new_session=True,
            )
            self.active_child = process
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if observe:
                    for pid in worker_pids():
                        try:
                            with Path("/proc", str(pid), "status").open() as status:
                                lines = status.read(65536).splitlines()
                            uid_line = next(
                                line for line in lines if line.startswith("Uid:")
                            )
                            observed.update(
                                int(value)
                                for value in uid_line.split()[1:]
                                if int(value) in seed.BUILD_UIDS
                            )
                        except FileNotFoundError:
                            continue
                if time.monotonic() >= deadline:
                    # Do not kill a client/build on timeout. Preserve identity/logs.
                    atomic_json(
                        self.logs / "pending-client.json",
                        {"pid": process.pid, "stage_log": output_path.name},
                    )
                    raise ValueError(
                        "Bootstrap command timed out; process may remain, no retry"
                    )
                time.sleep(0.02 if observe else 0.2)
            self.active_child = None
            if process.returncode != 0:
                raise ValueError(
                    "Developer command failed; inspect private bootstrap logs"
                )
        if not result:
            return "", observed
        with output_path.open("rb") as stream:
            content = stream.read(16385)
        if len(content) > 16384:
            raise ValueError("Bootstrap result exceeds bound")
        return content.decode(), observed

    def sandbox(self, _state):
        directory(FIXTURE.parent)
        info = FIXTURE.lstat()
        if (
            not FIXTURE.is_file()
            or FIXTURE.is_symlink()
            or info.st_uid != 0
            or info.st_mode & 0o022
        ):
            raise ValueError("Sandbox fixture must be immutable root input")
        witness = Path(
            tempfile.mkdtemp(prefix="devbox-nix-visibility.", dir="/var/tmp")
        )
        witness.chmod(0o755)
        marker = witness / "visible"
        marker.write_text("outside\n")
        marker.chmod(0o644)
        # Verify readability for every dedicated UID OUTSIDE the sandbox first.
        for index in range(1, 5):
            check = subprocess.run(
                [
                    "/usr/sbin/runuser",
                    "-u",
                    f"nixbld{index}",
                    "--",
                    "/usr/bin/cat",
                    str(marker),
                ],
                env=seed.root_environment(),
                capture_output=True,
                timeout=10,
                check=True,
            )
            if check.stdout != b"outside\n":
                raise ValueError("Public marker not readable outside sandbox")
        command = [
            seed.RUNTIME + "/bin/nix",
            *FLAGS,
            "--offline",
            "--option",
            "substitute",
            "false",
            "build",
            "--impure",
            "--file",
            str(FIXTURE),
            "--argstr",
            "nixPackage",
            seed.RUNTIME,
            "--argstr",
            "marker",
            str(marker),
            "--no-link",
            "--print-out-paths",
            "-L",
        ]
        observations = []
        outputs = []
        # Fresh baseline, then a checked rebuild; both must really execute a builder.
        for extra in ([], ["--rebuild"]):
            if worker_pids():
                raise ValueError("Unrelated build work present before isolated probe")
            output, observed = self.run_user(
                [*command, *extra], timeout=240, observe=True
            )
            path = store_output(output)
            with path.open() as stream:
                data = stream.read(128)
            validate_probe(data, observed)
            observations.append(sorted(observed))
            outputs.append(str(path))
        if outputs[0] != outputs[1]:
            raise ValueError("Sandbox rebuild changed output identity")
        atomic_json(
            META / "sandbox-gate.json",
            {
                "schema": 1,
                "boot_id": safety.boot_id(),
                "nix_generation": _state["generation_digest"],
                "observed_build_uids": observations,
                "output": outputs[0],
            },
        )
        return True

    def build_home(self, checkout):
        output, _ = self.run_user(
            [
                seed.RUNTIME + "/bin/nix",
                *FLAGS,
                "build",
                "--no-write-lock-file",
                "--no-link",
                "--print-out-paths",
                f"path:{checkout}#homeConfigurations.miyakishota@devbox.activationPackage",
            ],
            timeout=10800,
        )
        return str(store_output(output))

    def activate_home(self, activation):
        self.run_user([activation + "/activate"], result=False)

    def verify_profile(self):
        output, _ = self.run_user(["/usr/bin/python3", "-I", "-c", PROFILE_CHECK])
        profile = store_output(output)
        atomic_json(META / "home-profile.json", {"schema": 1, "profile": str(profile)})
        return True

    def finish(self, state, checkout):
        output, _ = self.run_user(["/usr/bin/sha256sum", checkout + "/flake.lock"])
        digest = output.split()[0]
        if re.fullmatch("[0-9a-f]{64}", digest) is None:
            raise ValueError("Invalid flake lock hash")
        atomic_json(
            META / "bootstrap-inputs.json",
            {
                "schema": 1,
                "flake_lock_sha256": digest,
                "checkout": checkout,
                "source": "reviewed-snapshot",
            },
        )
        self.record("home-ready", "recording", 0, state["generation_digest"])
        atomic_json(
            META / "home-ready",
            {"schema": 2, "generation_digest": state["generation_digest"]},
        )


PROFILE_CHECK = """from pathlib import Path
home=Path('/home/miyakishota')
for relative in ('.nix-profile', '.local/state/nix/profiles/profile', '.local/state/nix/profiles/home-manager/home-path'):
    try:
        profile=(home/relative).resolve(strict=True)
        if profile.is_relative_to('/nix/store') and all((profile/name).is_file() for name in ('bin/nix','bin/zsh','bin/pi','etc/profile.d/hm-session-vars.sh')):
            print(profile)
            break
    except OSError:
        continue
else:
    raise SystemExit('No complete activated Home Manager profile')
"""


def store_output(text):
    value = text.strip()
    if re.fullmatch("/nix/store/[a-z0-9]{32}-[^/\\s]+", value) is None:
        raise ValueError("Expected one Nix store output path")
    return Path(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout")
    args = parser.parse_args()
    if (
        os.getuid() != 0
        or os.environ.get("DEVBOX_MODE", "maintenance") != "maintenance"
    ):
        raise ValueError("Root maintenance console required")
    if not Path("/etc/devbox-host").is_file():
        raise ValueError("Devbox host marker missing")
    os.umask(0o077)
    checkout = bootstrap_state.validate_checkout(args.checkout)
    with locked(Path("/run/devbox/bootstrap.lock")), safety.admission():
        for name in (
            "bootstrap-started",
            "bootstrap-state.json",
            "home-ready",
            "nix-state.json",
            "bootstrap-logs",
        ):
            path = META / name
            if path.exists() or path.is_symlink():
                raise ValueError(
                    "Bootstrap already attempted; preserve evidence and review"
                )
        actions = Actions()
        execute_pipeline(checkout, actions)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Bootstrap refused/failed: {exc}") from exc
