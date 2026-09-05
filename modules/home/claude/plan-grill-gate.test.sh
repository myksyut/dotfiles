#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
hook="$root/plan-grill-gate.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

chmod +x "$hook"

run_hook() {
  local tool_path="$1"
  python3 -c 'import json,sys; json.dump({"tool_name":"Write","cwd":sys.argv[1],"tool_input":{"file_path":sys.argv[2]}}, sys.stdout)' \
    "$tmp" "$tool_path" | "$hook" || true
}

mkdir -p "$tmp/.context"

# no todo.md -> allow (empty stdout)
out="$(run_hook "$tmp/src/main.rs")"
test -z "$out"

# todo without checkpoint -> deny
printf '%s\n' '# Plan' >"$tmp/.context/todo.md"
out="$(run_hook "$tmp/src/main.rs")"
printf '%s\n' "$out" | grep -q 'permissionDecision": "deny"'
printf '%s\n' "$out" | grep -q 'grill checkpoint'

# writing todo.md itself is allowed even without checkpoint
out="$(run_hook "$tmp/.context/todo.md")"
test -z "$out"

# checkpoint with open questions -> deny
cat >"$tmp/.context/todo.md" <<'EOF'
# Plan
## Grill checkpoint
- Open questions: still thinking
EOF
out="$(run_hook "$tmp/src/main.rs")"
printf '%s\n' "$out" | grep -q '未解決質問'

# checkpoint complete, no approval -> deny
cat >"$tmp/.context/todo.md" <<'EOF'
# Plan
## Grill checkpoint
- Open questions: none
EOF
out="$(run_hook "$tmp/src/main.rs")"
printf '%s\n' "$out" | grep -q '承認'

# Claude Code plan file lives outside the project; never gate it
outside="$(mktemp)"
out="$(run_hook "$outside")"
test -z "$out"
rm -f "$outside"

# approved hash matches -> allow
hash="$(python3 -c 'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$tmp/.context/todo.md")"
printf '{"approved": true, "planHash": "%s"}\n' "$hash" >"$tmp/.context/.grill-gate.json"
out="$(run_hook "$tmp/src/main.rs")"
test -z "$out"

# changed plan -> deny
printf '%s\n' 'changed' >>"$tmp/.context/todo.md"
out="$(run_hook "$tmp/src/main.rs")"
printf '%s\n' "$out" | grep -q '変わって'

printf 'plan-grill-gate.test.sh: ok\n'
