#!/usr/bin/env bash
# Deny Write/Edit when a plan file exists but is not grill-complete and approved.
set -euo pipefail

payload="$(mktemp)"
trap 'rm -f "$payload"' EXIT
cat >"$payload"

python3 - "$payload" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

def allow():
    sys.exit(0)

def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    sys.exit(0)

try:
    raw = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else ""
    inp = json.loads(raw) if raw.strip() else {}
except (json.JSONDecodeError, OSError):
    allow()

tool = str(inp.get("tool_name") or inp.get("tool") or "")
if tool not in {"Write", "Edit", "NotebookEdit"}:
    allow()

cwd = Path(str(inp.get("cwd") or os.getcwd())).expanduser().resolve()
todo = cwd / ".context" / "todo.md"
if not todo.is_file():
    allow()

tool_input = inp.get("tool_input") if isinstance(inp.get("tool_input"), dict) else {}
file_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
target = Path(file_path).expanduser()
if not target.is_absolute():
    target = cwd / target
try:
    target = target.resolve()
except OSError:
    pass

# Claude Code writes the native plan to ~/.claude/plans/*.md before
# ExitPlanMode. Blocking that leaves planExists=false and Plannotator
# never gets a document to open.
try:
    target.relative_to(cwd)
except ValueError:
    allow()

allowed = {
    (cwd / ".context" / "todo.md").resolve(),
    (cwd / ".context" / ".grill-gate.json").resolve(),
}
if target in allowed:
    allow()

text = todo.read_text(encoding="utf-8", errors="replace")
if "## Grill checkpoint" not in text:
    deny(
        "grill checkpoint がありません。grill-with-docs を完了し "
        ".context/todo.md に ## Grill checkpoint を書いてください。"
    )

lower = text.lower()
has_open_none = (
    "open questions: none" in lower
    or "open_questions: []" in lower
    or "未解決質問0" in text
    or "未解決質問なし" in text
    or "- open questions: none" in lower
)
if not has_open_none:
    deny("grill に未解決質問が残っています。Open questions: none になるまで実装しません。")

gate = cwd / ".context" / ".grill-gate.json"
if not gate.is_file():
    deny(
        "grill 済みですが Plannotator（またはチャット）承認がありません。"
        "承認後に .context/.grill-gate.json へ planHash を書いてください。"
    )

try:
    gate_data = json.loads(gate.read_text(encoding="utf-8"))
except json.JSONDecodeError:
    deny(".context/.grill-gate.json が壊れています。承認マーカーを書き直してください。")

plan_hash = hashlib.sha256(todo.read_bytes()).hexdigest()
if not gate_data.get("approved") or str(gate_data.get("planHash") or "") != plan_hash:
    deny("計画が承認時から変わっています。再 grill と再承認が必要です。")

allow()
PY
