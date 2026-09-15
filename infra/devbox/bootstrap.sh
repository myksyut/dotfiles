#!/usr/bin/env bash
# Explicit fresh multi-user bootstrap. No install/repair on ordinary boot.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && ${DEVBOX_MODE:-maintenance} == maintenance ]]
mountpoint -q /data
# Isolated Python must not load developer-writable user-site/.pth files as root.
exec /usr/bin/python3 -I /opt/devbox/nix/bootstrap.py "${1:?usage: bootstrap.sh /home/miyakishota/src/dotfiles}"
