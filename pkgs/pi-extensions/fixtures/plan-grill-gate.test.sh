#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/../../.." && pwd)
patch="$repo_root/pkgs/pi-extensions/patches/agent-pi-plan-grill-gate.patch"
agent_pi="$repo_root/pkgs/pi-extensions/agent-pi.nix"
skill="$HOME/.pi/agent/skills/grill-with-docs/SKILL.md"

require() {
  local needle=$1
  local file=$2
  grep -Fq "$needle" "$file" || {
    printf 'missing %s in %s\n' "$needle" "$file" >&2
    exit 1
  }
}

require 'agent-pi-plan-grill-gate.patch' "$agent_pi"
require '+++ b/extensions/plan-grill-gate.ts' "$patch"
require 'name: "grill_with_docs"' "$patch"
require '__piPlanGrillComplete' "$patch"
require 'plan_grill_required' "$patch"
require 'plan_grill_section_required' "$patch"
require '## Mandatory grill-with-docs gate' "$patch"
require '## Grill checkpoint' "$patch"
require '__piResetPlanGrill' "$patch"
require '## PLANモードの必須チェックポイント' "$skill"

python3 - "$patch" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
mandatory = text.index("## Mandatory grill-with-docs gate")
workflow = text.index("## Workflow", mandatory)
bridge = text.index("plan_grill_required")
if not mandatory < workflow:
    raise SystemExit("mandatory grill instructions must precede the PLAN workflow")
if not mandatory < bridge:
    raise SystemExit("the PLAN prompt must be present before the bridge gate")
PY

printf '%s\n' 'plan-grill-gate fixture: PASS'
