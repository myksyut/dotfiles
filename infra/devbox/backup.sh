#!/usr/bin/env bash
# Only call after the validated stop hook fenced new work and saved/stopped services.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && -f /etc/devbox-host ]]
[[ ${1:-} == --quiesced ]] || {
  echo 'Requires the validated quiesced stop protocol' >&2
  exit 1
}
/usr/bin/jq -e '.verified == true' /data/meta/state-paths.json >/dev/null
# Root must not execute binaries in the user-writable single-user Nix store.
[[ -x /usr/bin/restic ]]
export RESTIC_REPOSITORY_FILE=/etc/devbox/secrets/restic-repository
export RESTIC_PASSWORD_FILE=/etc/devbox/secrets/restic-password
for path in /etc/devbox/secrets "$RESTIC_REPOSITORY_FILE" "$RESTIC_PASSWORD_FILE"; do
  [[ ! -L $path && $(stat -c %u "$path") == 0 ]]
  [[ $(stat -c %a "$path") == 600 || $(stat -c %a "$path") == 700 ]]
done
# Restic handles encryption. Never copy live SQLite files and claim consistency.
# DB dumps and Orca shutdown must already have succeeded in the site hook.
/usr/bin/restic backup --tag devbox-quiesced \
  --exclude '**/node_modules' --exclude '**/.cache' \
  /data/home /data/service-data /data/meta /data/tailscale
date -u +%FT%TZ >/data/meta/last-backup-success
