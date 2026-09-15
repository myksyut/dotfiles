#!/usr/bin/env bash
# User-side marker check only; root bootstrap also observes the actual build UID.
set -euo pipefail
[[ $(uname -sm) == 'Linux x86_64' && $(id -u) == 10001 ]] || exit 1
[[ $HOME == /home/miyakishota && $# == 1 && $1 == /opt/devbox/nix/sandbox-probe.nix &&
  -f $1 && ! -L $1 ]] || exit 1
fixture_mode=$(stat -c '%u:%a' "$1")
[[ $fixture_mode == 0:644 || $fixture_mode == 0:444 ]] || exit 1
umask 077
export NIX_REMOTE=daemon NIX_BECOME=/usr/bin/false
export NIX_CONF_DIR=/etc/nix NIX_USER_CONF_FILES=/dev/null
unset NIX_CONFIG
nix_package=$(/usr/bin/python3 -I -c 'import sys; sys.path.insert(0,"/opt/devbox"); from nix.provision import RUNTIME; print(RUNTIME)')
nix_bin="$nix_package/bin/nix"
[[ $("$nix_bin" --version) == 'nix (Nix) 2.35.2' ]] || exit 1
flags=(--offline --store daemon --extra-experimental-features nix-command
  --option sandbox true --option sandbox-fallback false
  --option builders '' --option substitute false --option max-jobs 1 --option cores 2)
witness=$(mktemp -d /var/tmp/devbox-nix-visibility.XXXXXXXX)
chmod 755 "$witness"
marker="$witness/visible"
printf 'outside\n' >"$marker"
chmod 644 "$marker"
visible=$(DEVBOX_SANDBOX_MARKER="$marker" "$nix_bin" "${flags[@]}" eval --impure --raw \
  --expr 'builtins.readFile (builtins.getEnv "DEVBOX_SANDBOX_MARKER")')
[[ $visible == outside ]] || exit 1
build=("$nix_bin" "${flags[@]}" build --impure --file "$1"
  --argstr nixPackage "$nix_package" --argstr marker "$marker"
  --no-link --print-out-paths -L)
baseline=$("${build[@]}")
output=$("${build[@]}" --rebuild)
[[ $output == "$baseline" && $output == /nix/store/* && -f $output &&
  $(cat "$output") == marker-hidden ]] || exit 1
printf 'Marker rebuild passed; root outside-UID observation still required: %s\n' "$output"
