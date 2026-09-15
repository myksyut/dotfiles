#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || {
  echo 'entrypoint requires root' >&2
  exit 1
}
mountpoint -q /data || {
  echo '/data must be a mounted Volume' >&2
  exit 1
}
/usr/bin/python3 -I -c 'import sys; sys.path.insert(0,"/opt/devbox"); from nix.boundary import directory; directory("/data")'
[[ ! -L /nix && ! -L /home/miyakishota ]]
for name in home nix tailscale meta service-data; do
  [[ ! -L /data/$name ]] || {
    echo "refuse symlink /data/$name" >&2
    exit 1
  }
  if [[ ! -e /data/$name ]]; then
    if [[ $name == nix ]]; then mkdir -m 755 /data/nix; else mkdir -m 700 "/data/$name"; fi
    case "$name" in home | service-data) chown 10001:10001 "/data/$name" ;; esac
  fi
done
[[ -d /data/nix && $(stat -c %u:%g /data/nix) == 0:0 && $(stat -c %a /data/nix) == 755 ]] || {
  echo 'Refuse legacy/untrusted Nix directory; no ownership conversion on boot' >&2
  exit 1
}
for name in home service-data; do
  [[ -d /data/$name && $(stat -c %u:%g "/data/$name") == 10001:10001 && $(stat -c %a "/data/$name") == 700 ]] || {
    echo "Wrong ownership: /data/$name; repair explicitly, not recursively on boot" >&2
    exit 1
  }
done
for name in tailscale meta; do
  [[ -d /data/$name && $(stat -c %u:%g "/data/$name") == 0:0 && $(stat -c %a "/data/$name") == 700 ]] || {
    echo "Unsafe persistent directory: /data/$name; require root:root and mode 700" >&2
    exit 1
  }
done
# Nix store ancestors must not be symlinks. Seed lives outside /nix in the image.
mount --bind /data/nix /nix
mount --bind /data/home /home/miyakishota
# Fly can preserve rootfs across stop/start. Explicit tmpfs avoids stale sockets/requests.
mount -t tmpfs -o mode=755,nosuid,nodev tmpfs /run
install -d -m 700 /run/devbox /run/tailscale /run/devbox/logs
install -d -m 700 -o 10001 -g 10001 /run/user/10001
# Runtime objects are boot-local; never use a persisted ready/PID/socket as liveness.
cat /proc/sys/kernel/random/boot_id >/run/devbox/boot-id
/usr/bin/python3 -I /opt/devbox/idle-controller/safety.py
if [[ ! -e /data/meta/state-paths.json ]]; then
  install -m 600 /opt/devbox/state-paths.json /data/meta/state-paths.json
fi
if [[ -d /.fly ]]; then chmod 700 /.fly; fi
mkdir -p /dev/net
if [[ ! -c /dev/net/tun ]]; then mknod /dev/net/tun c 10 200; fi
chmod 600 /dev/net/tun
# Fail closed if Fly does not support kernel TUN or this firewall.
# No blanket privileged/userspace fallback.
nft -f /opt/devbox/firewall.nft
# Optional Fly init SSH recovery, restricted to the operator's verified 6PN /128.
# This is not an SSH daemon installed in this image and is never publicly exposed.
if [[ -n ${DEVBOX_ADMIN_IPV6:-} ]]; then
  admin_ip=$(/usr/bin/python3 -I -c '
import ipaddress, sys
address = ipaddress.IPv6Address(sys.argv[1])
if address not in ipaddress.IPv6Network("fdaa::/16"):
    raise SystemExit("admin address must be a verified Fly 6PN IPv6 address")
print(address)
' "$DEVBOX_ADMIN_IPV6")
  nft add rule inet devbox input ip6 saddr "$admin_ip" tcp dport 22 accept
fi
exec /usr/bin/python3 -I /opt/devbox/supervisor/supervisor.py
