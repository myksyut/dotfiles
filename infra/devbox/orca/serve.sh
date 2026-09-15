#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $(id -u) == 10001 ]] || {
  echo 'Orca must run as devbox user' >&2
  exit 1
}
export HOME=/home/miyakishota USER=miyakishota LOGNAME=miyakishota
export XDG_RUNTIME_DIR=/run/user/10001
profile=
for candidate in "$HOME/.nix-profile" "$HOME/.local/state/nix/profiles/profile" \
  "$HOME/.local/state/nix/profiles/home-manager/home-path"; do
  if [[ -f $candidate/etc/profile.d/hm-session-vars.sh && -x $candidate/bin/zsh &&
    -x $candidate/bin/nix && -x $candidate/bin/pi ]]; then
    profile=$(readlink -f "$candidate")
    break
  fi
done
[[ $profile == /nix/store/* ]] || {
  echo 'Verified HM profile missing' >&2
  exit 1
}
export PATH="$profile/bin:$HOME/.local/bin:/usr/bin:/bin"
# This profile is sourced only as UID10001, never by root.
# Home Manager session variables may reference unset inherited variables.
set +u
# shellcheck disable=SC1091
source "$profile/etc/profile.d/hm-session-vars.sh"
set -u
export SHELL="$profile/bin/zsh" NIX_REMOTE=daemon NIX_BECOME=/usr/bin/false
cli=${ORCA_CLI:?set a verified absolute Orca CLI path}
[[ $cli = /* && -x $cli ]] || exit 1
# Packaging identity is checked at image build; CLI help checked before serving.
help=$("$cli" serve --help)
[[ $help == *--pairing-address* ]] || exit 1
address=$(/usr/bin/python3 -I /opt/devbox/supervisor/tailscale_state.py \
  --address "${DEVBOX_TAILSCALE_ADDRESS:?required private address}")
cd "$HOME"
exec "$cli" serve --port 6768 --pairing-address "$address" --mobile-pairing
