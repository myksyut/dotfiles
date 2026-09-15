#!/usr/bin/env bash
# Run only inside the disposable VM against the explicitly supplied OCI bundle.
set -euo pipefail
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || exit 1
[[ $(id -un) == devboxlab && $# == 1 && $1 == /* ]] || exit 1
cd "$1"
run_id=$(basename "$PWD")
[[ $run_id =~ ^[a-z0-9][a-z0-9_.-]{0,47}$ ]] || exit 1
container_name="devbox-${run_id}-smoke"
umask 077
[[ ! -e job.exit && ! -e image-id.txt && ! -e container-name.txt ]] || {
  echo 'Existing run evidence: review before a separate explicit run' >&2
  exit 1
}
trap 'printf "%s\n" "$?" > job.exit' EXIT
python3 tools/devbox/check-artifacts.py
lock=infra/devbox/artifacts.lock.json
docker_config=$(mktemp -d -t devbox-docker.XXXXXXXX)
export DOCKER_CONFIG="$docker_config" DOCKER_BUILDKIT=1
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH BUILDX_BUILDER
local_docker() {
  docker --config "$docker_config" --host unix:///var/run/docker.sock "$@"
}
local_docker buildx build --builder default --load --platform linux/amd64 \
  --build-arg "UBUNTU_IMAGE=$(jq -r .ubuntu_image "$lock")" \
  --build-arg "NIX_SHA256=$(jq -r .nix.sha256 "$lock")" \
  --build-arg "ORCA_SHA256=$(jq -r .orca.sha256 "$lock")" \
  --build-arg "TAILSCALE_SHA256=$(jq -r .tailscale.sha256 "$lock")" \
  --build-arg "ORCA_VERSION=$(jq -r .orca.version "$lock")" \
  --iidfile image-id.txt -t cloud-devbox:gate0 infra/devbox
image=$(cat image-id.txt)
[[ $image =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1
printf '%s\n' "$container_name" >container-name.txt
# The single-quoted script expands variables inside the isolated container.
# shellcheck disable=SC2016
local_docker run --name "$container_name" --pull=never \
  --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --user 10001:10001 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  --env HOME=/tmp/devbox-smoke --entrypoint /bin/bash "$image" -euc '
    umask 077
    mkdir "$HOME"
    test "$(id -u)" = 10001
    test -f /opt/artifacts/nix.tar.xz
    test -f /opt/devbox/nix/provision.py
    test ! -e /opt/nix-bootstrap
    /usr/bin/python3 -I -c '\''import sys; from pathlib import Path; sys.path.insert(0, "/opt/devbox"); from nix.provision import CONFIG, validate_accounts; validate_accounts(); assert Path("/etc/nix/nix.conf").read_text() == CONFIG'\''
    actual=$(/opt/tailscale/tailscale version)
    test "$(printf "%s\n" "$actual" | head -n 1)" = "$1"
    /usr/bin/orca-ide --version
    test "$(dpkg-query -W -f="\${Version}" orca-ide)" = "$2"
    help=$(/usr/bin/orca-ide serve --help)
    printf "%s\n" "$help"
    grep -q -- --pairing-address <<< "$help"
    cat /opt/artifacts/dpkg-packages.txt
  ' smoke "$(jq -r .tailscale.version "$lock")" "$(jq -r .orca.version "$lock")"
printf 'OCI build and network-isolated CLI smoke passed; serve/Nix/stop still unverified.\n'
