#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
script="$root/modules/home/merge-pi-settings.sh"
pi_nix="$root/modules/home/pi.nix"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

require() {
  grep -Fq "$1" "$2" || fail "missing $1 in $2"
}

require 'merge-pi-settings.sh' "$pi_nix"
require "DEFAULT_PROVIDER='openai-codex'" "$pi_nix"
require "DEFAULT_MODEL='gpt-6-astra'" "$pi_nix"
require "DEFAULT_THINKING_LEVEL='high'" "$pi_nix"

export AGENT_PI='/nix/store/00000000000000000000000000000000-agent-pi-test/'
export PI_HUNK='npm:pi-hunk'
export PLANNOTATOR='npm:@plannotator/pi-extension'
export CONTEXT_VIEW='npm:pi-context-view'
export WEB_ACCESS='npm:pi-web-access'
export SESSION_RECALL='npm:@ogulcancelik/pi-session-recall'
export PI_FFF='npm:@ff-labs/pi-fff'
export PI_LENS='npm:pi-lens'
export RPIV_ASK_USER='npm:@juicesharp/rpiv-ask-user-question'
export PI_BTW='npm:pi-btw'
export CODEX_IMAGE_GEN='npm:pi-codex-image-gen'
export PI_VCC='npm:@sting8k/pi-vcc'
export PI_LINEAR='npm:@alasano/pi-linear'
export SKILL_CREATOR='npm:@tmustier/pi-skill-creator'
export ISSUE_PR_WRITING='/nix/store/00000000000000000000000000000001-issue-pr-writing-'
export REMOTE_CONTROL='npm:pi-remote-control'
export PI_GOAL='npm:@narumitw/pi-goal'
export CODEX_FAST='npm:@calesennett/pi-codex-fast'

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
settings="$workdir/settings.json"

assert_keys() {
  local file=$1
  python3 - "$file" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["defaultProvider"] == "openai-codex", data
assert data["defaultModel"] == "gpt-6-astra", data
assert data["defaultThinkingLevel"] == "high", data
assert isinstance(data.get("packages"), list) and data["packages"], data
PY
}

# Missing file: initialize and set keys.
bash "$script" "$settings"
assert_keys "$settings"
mode=$(python3 -c 'import os, sys; print(oct(os.stat(sys.argv[1]).st_mode)[-3:])' "$settings")
[ "$mode" = "600" ] || fail "missing-file mode was $mode"

# Preserve unmanaged settings and unmanaged packages.
python3 - "$settings" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
data["theme"] = "keep-me"
data["packages"].insert(0, "git:example.com/unmanaged")
json.dump(data, open(path, "w"))
PY
chmod 600 "$settings"
bash "$script" "$settings"
python3 - "$settings" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["theme"] == "keep-me", data
assert "git:example.com/unmanaged" in data["packages"], data
assert data["defaultProvider"] == "openai-codex"
assert data["defaultModel"] == "gpt-6-astra"
assert data["defaultThinkingLevel"] == "high"
PY

# Idempotent: second run keeps unmanaged keys and restores declared keys.
before=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True))' "$settings")
bash "$script" "$settings"
after=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True))' "$settings")
[ "$before" = "$after" ] || fail "second merge was not idempotent"

# Existing keys are overwritten to declared values.
python3 - "$settings" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
data["defaultProvider"] = "xai"
data["defaultModel"] = "grok-4.6"
data["defaultThinkingLevel"] = "low"
json.dump(data, open(path, "w"))
PY
bash "$script" "$settings"
assert_keys "$settings"

expect_fail_unchanged() {
  local label=$1
  cp "$settings" "$settings.bak"
  if bash "$script" "$settings" 2>/dev/null; then
    fail "$label should fail"
  fi
  cmp -s "$settings" "$settings.bak" || fail "$label mutated the original"
}

# Empty / multiple docs / non-object / bad packages: fail and keep bytes.
: > "$settings"
chmod 600 "$settings"
expect_fail_unchanged "empty JSON"

printf '%s\n' '{}' '{}' > "$settings"
expect_fail_unchanged "multiple JSON documents"

printf '%s\n' '[]' > "$settings"
expect_fail_unchanged "JSON array"

printf '%s\n' '1' > "$settings"
expect_fail_unchanged "JSON scalar"

printf '%s\n' '{"packages":null}' > "$settings"
expect_fail_unchanged "packages null"

printf '%s\n' '{"packages":{}}' > "$settings"
expect_fail_unchanged "packages object"

# Invalid JSON: original bytes preserved, non-zero exit.
printf '%s\n' '{not json' > "$settings"
chmod 640 "$settings"
expect_fail_unchanged "invalid JSON"
[ ! -e "$workdir/.settings.json."* ] || fail "temp file leaked after jq failure"
mode=$(python3 -c 'import os, sys; print(oct(os.stat(sys.argv[1]).st_mode)[-3:])' "$settings")
[ "$mode" = "640" ] || fail "invalid JSON changed mode to $mode"

# Unreadable file: stop without replacing.
python3 - "$settings" <<'PY'
import json, sys
json.dump({"theme": "secret-keep"}, open(sys.argv[1], "w"))
PY
chmod 000 "$settings"
if bash "$script" "$settings" 2>/dev/null; then
  chmod 600 "$settings" || true
  fail "unreadable settings should fail"
fi
chmod 600 "$settings"
python3 - "$settings" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data == {"theme": "secret-keep"}, data
PY

# Symlink / broken symlink / FIFO: refuse before read, leave original.
rm -f "$settings"
printf '%s\n' '{"theme":"via-link"}' > "$workdir/target.json"
cp "$workdir/target.json" "$workdir/target.json.bak"
ln -s target.json "$settings"
if bash "$script" "$settings" 2>/dev/null; then
  fail "symlink should fail"
fi
[ -L "$settings" ] || fail "symlink was replaced"
cmp -s "$workdir/target.json" "$workdir/target.json.bak" || fail "symlink target mutated"

rm -f "$settings"
ln -s missing-target.json "$settings"
if bash "$script" "$settings" 2>/dev/null; then
  fail "broken symlink should fail"
fi
[ -L "$settings" ] || fail "broken symlink was replaced"
[ ! -e "$workdir/missing-target.json" ] || fail "broken symlink created a target"

rm -f "$settings"
mkdir "$settings"
if bash "$script" "$settings" 2>/dev/null; then
  fail "directory should fail"
fi
[ -d "$settings" ] || fail "directory was replaced"
rmdir "$settings"

mkfifo "$settings"
if bash "$script" "$settings" 2>/dev/null; then
  fail "FIFO should fail"
fi
[ -p "$settings" ] || fail "FIFO was replaced"
rm -f "$settings"

printf '%s\n' 'merge-pi-settings: PASS'
