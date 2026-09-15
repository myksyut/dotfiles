#!/usr/bin/env bash
# One-shot db-mu1 system provision only. Embed a host-reviewed manifest SHA in
# DEVBOX_INPUT_SHA256 in the Lima system script BEFORE this script's contents.
# No host install, old-store conversion, authentication, or protection fallback.
set -euo pipefail
[[ $(uname -sm) == 'Linux x86_64' && $(id -u) == 0 && $(hostname -s) == lima-db-mu1 ]] || exit 1
[[ -f /var/lib/devbox-lab-provisioned && ${DEVBOX_INPUT_SHA256:-} =~ ^[0-9a-f]{64}$ ]] || exit 1
state=/var/lib/devbox-nix-multi-v1
[[ ! -e $state && ! -L $state ]] || { echo 'Already attempted; inspect retained evidence. No retry.'; exit 1; }
for path in /nix /data /home/miyakishota /etc/nix /opt/devbox /opt/artifacts /opt/devbox-lab /var/lib/devbox-multi-data; do
  [[ ! -e $path && ! -L $path ]] || { echo "Refuse existing path: $path"; exit 1; }
done
# Package preflight is recorded by Lima, before consuming the Nix attempt.
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends zsh procps util-linux
umask 077
mkdir -m 755 "$state"
stage=verify-input
record_result() {
  local code=$?
  printf 'stage=%s\nexit=%s\n' "$stage" "$code" >"$state/provision-result.txt"
  chmod 644 "$state/provision-result.txt"
}
trap record_result EXIT
exec >"$state/provision.log" 2>&1
chmod 644 "$state/provision.log"
# The fixture VM has no real authentication. Only this setup log/status is public;
# production bootstrap/daemon logs remain private and are not chmodded.
/usr/bin/python3 -I - <<'PY'
import hashlib, json, os, shutil, stat
from pathlib import Path, PurePosixPath
source = Path('/home/devboxlab/multi-user-input')
staging = Path('/var/lib/devbox-nix-multi-v1/input')
staging.mkdir(mode=0o700)
# Anchor is embedded by the operator in root's system-provision script, NOT read
# from the developer-writable input tree. Copy+hash through the same file handle.
fd = os.open(source / 'input-manifest.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as stream:
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        raise ValueError('Manifest must be regular')
    raw = stream.read(262145)
if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != os.environ['DEVBOX_INPUT_SHA256']:
    raise ValueError('Input manifest does not match root anchor')
manifest = json.loads(raw)
if manifest['schema'] != 1 or not 1 <= len(manifest['files']) <= 1000:
    raise ValueError('Invalid input manifest')
for name, expected in manifest['files'].items():
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('Invalid input path')
    if not (name.startswith('infra/devbox/') or name.startswith('home-config/') or
            name in ('tools/devbox/vm/nix-lab-driver.py', 'tools/devbox/vm/nix-multi-user-provision.sh')):
        raise ValueError('Input path outside lab allowlist')
    if not 0 <= expected['size'] <= 512 * 1024 * 1024:
        raise ValueError('Input size out of bounds')
    destination = staging / name
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(source / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as src, destination.open('xb') as dst:
        info = os.fstat(src.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != expected['size']:
            raise ValueError('Input is not the expected regular file')
        digest = hashlib.sha256()
        remaining = expected['size']
        while remaining:
            data = src.read(min(1024 * 1024, remaining))
            if not data:
                raise ValueError('Short input')
            dst.write(data)
            digest.update(data)
            remaining -= len(data)
        if src.read(1) or digest.hexdigest() != expected['sha256']:
            raise ValueError('Input bytes changed or failed hash verification')
# All bytes are now verified in private root-owned staging; no guest source is
# executed or copied again. Destination directories are new, not existing stores.
for name in manifest['files']:
    if name.startswith('home-config/'):
        continue
    if name == 'infra/devbox/artifacts/nix.tar.xz':
        target = Path('/opt/artifacts/nix.tar.xz')
    elif name.startswith('infra/devbox/'):
        target = Path('/opt/devbox') / name.removeprefix('infra/devbox/')
    else:
        target = Path('/opt/devbox-lab') / Path(name).name
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    shutil.copyfile(staging / name, target)
    target.chmod(0o755 if target.suffix == '.sh' else 0o644)
# mkdir(parents=True) obeys umask; make only these NEW code ancestors traversable.
for root in ('/opt/devbox', '/opt/artifacts', '/opt/devbox-lab'):
    for directory, _, _ in os.walk(root):
        Path(directory).chmod(0o755)
PY
stage=accounts-mounts
# Account collisions fail; never reuse an existing UID/GID or mutate memberships.
groupadd --gid 10001 miyakishota
useradd --no-create-home --uid 10001 --gid 10001 --home-dir /home/miyakishota --shell /bin/zsh miyakishota
groupadd --gid 30000 nixbld
for i in 1 2 3 4; do
  useradd --no-create-home --uid "$((30000 + i))" --gid nixbld --groups nixbld --home-dir /var/empty --shell /usr/sbin/nologin "nixbld$i"
done
install -d -m 755 /var/lib/devbox-multi-data /data /nix /home/miyakishota /etc/nix
mount --bind /var/lib/devbox-multi-data /data
install -d -m 755 /data/nix
install -d -m 700 /data/meta /data/tailscale
install -d -m 700 -o 10001 -g 10001 /data/home /data/service-data
mount --bind /data/nix /nix
mount --bind /data/home /home/miyakishota
install -d -m 700 /run/devbox /run/devbox/logs
install -d -m 700 -o 10001 -g 10001 /run/user/10001
/usr/bin/python3 -I - <<'PY'
import os, shutil, sys
from pathlib import Path
sys.path.insert(0, '/opt/devbox')
from nix.provision import CONFIG, validate_accounts
validate_accounts()
Path('/etc/nix/nix.conf').write_text(CONFIG)
Path('/etc/nix/nix.conf').chmod(0o644)
Path('/etc/devbox-host').touch(mode=0o644)
# This is an empty new HOME. Only the verified allowlisted source is copied.
source = Path('/var/lib/devbox-nix-multi-v1/input/home-config')
target = Path('/home/miyakishota/source')
shutil.copytree(source, target)
for directory, _, files in os.walk(target):
    os.chown(directory, 10001, 10001)
    Path(directory).chmod(0o700)
    for name in files:
        path = Path(directory) / name
        os.chown(path, 10001, 10001)
        path.chmod(0o600)
PY
cat /proc/sys/kernel/random/boot_id >/run/devbox/boot-id
/usr/bin/python3 -I /opt/devbox/idle-controller/safety.py
stage=launch
# This lab supervises the SAME runtime; not a systemd-specific Nix daemon.
# No automatic restart/retry. Background jobs survive the provisioning shell.
setsid /usr/bin/env -i HOME=/root USER=root LOGNAME=root PATH=/usr/bin:/bin \
  /usr/bin/python3 -I /opt/devbox-lab/nix-lab-driver.py supervise \
  >"$state/supervisor.log" 2>&1 </dev/null &
setsid /usr/bin/env -i HOME=/root USER=root LOGNAME=root PATH=/usr/bin:/bin DEVBOX_MODE=maintenance \
  /usr/bin/python3 -I /opt/devbox-lab/nix-lab-driver.py bootstrap \
  >"$state/bootstrap.log" 2>&1 </dev/null &
stage=launched-not-verified
