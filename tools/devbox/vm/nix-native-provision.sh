#!/usr/bin/env bash
# Optional one-shot Lima system provision, not a host installer or Fly bootstrap.
# Append only after the operator approves native Nix validation in db-gate0.
set -euo pipefail
[[ $(uname -sm) == 'Linux x86_64' && $(id -u) == 0 ]] || exit 1
[[ -f /var/lib/devbox-lab-provisioned ]] || exit 1
state=/var/lib/devbox-nix-probe-v1
if [[ -e $state ]]; then
  echo 'Native Nix probe already attempted; inspect retained result. No retry.'
  [[ -f $state/result.txt && ! -L $state/result.txt &&
    $(cat "$state/result.txt") == $'stage=passed\nexit=0' ]] || exit 1
  exit 0
fi
umask 077
mkdir -m 755 "$state"
stage=prepare
record_result() {
  local code=$?
  printf 'stage=%s\nexit=%s\n' "$stage" "$code" >"$state/result.txt"
  chmod 644 "$state/result.txt"
}
trap record_result EXIT
exec >"$state/run.log" 2>&1
chmod 644 "$state/run.log"
# The VM contains no real credentials. Only minimal-environment public diagnostics
# are readable by devboxlab; neither host HOME nor VM keys are used or copied.
[[ ! -e /nix && ! -L /nix && ! -e /home/miyakishota && ! -L /home/miyakishota ]]
[[ ! -e /etc/nix && ! -e /opt/devbox-nix-probe ]]
if getent passwd 10001 || getent passwd miyakishota || getent group 10001; then
  echo 'Refuse an existing Nix user/group' >&2
  exit 1
fi
archive=/home/devboxlab/oci-gate1/infra/devbox/artifacts/nix.tar.xz
printf '%s  %s\n' \
  0c3960a9792331a22081c3c7a5d8465db9b17c50b3acdf18587fa4c6f2cb1158 \
  "$archive" | sha256sum -c -
groupadd --gid 10001 miyakishota
useradd --no-create-home --uid 10001 --gid 10001 \
  --home-dir /home/miyakishota --shell /bin/bash miyakishota
install -d -m 755 -o 10001 -g 10001 /nix
install -d -m 700 -o 10001 -g 10001 /home/miyakishota
install -d -m 755 /opt/devbox-nix-probe /etc/nix
# Public, hash-checked distribution: preserve traversal for the non-root user.
(
  umask 022
  tar -xJf "$archive" --no-same-owner --no-same-permissions \
    -C /opt/devbox-nix-probe --strip-components=1
)
install -m 644 /home/devboxlab/nix-native-input/sandbox-probe.nix /opt/devbox-nix-probe/
install -m 755 /home/devboxlab/nix-native-input/sandbox-probe.sh /opt/devbox-nix-probe/
printf '%s\n' 'experimental-features = nix-command flakes' \
  'build-users-group =' 'sandbox = true' 'sandbox-fallback = false' >/etc/nix/nix.conf
chmod 644 /etc/nix/nix.conf
stage=install
runuser -u miyakishota -- /usr/bin/env -i \
  HOME=/home/miyakishota USER=miyakishota LOGNAME=miyakishota \
  PATH=/usr/bin:/bin NIX_BECOME=/usr/bin/false \
  NIX_CONFIG=$'substitute = false\nbuilders =\n' \
  /usr/bin/timeout 240 /opt/devbox-nix-probe/install \
  --no-daemon --no-channel-add --no-modify-profile --yes
stage=sandbox-build
runuser -u miyakishota -- /usr/bin/env -i \
  HOME=/home/miyakishota USER=miyakishota LOGNAME=miyakishota PATH=/usr/bin:/bin \
  /usr/bin/timeout 180 /bin/bash /opt/devbox-nix-probe/sandbox-probe.sh \
  /opt/devbox-nix-probe/sandbox-probe.nix
stage=passed
