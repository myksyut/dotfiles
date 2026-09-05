#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/../../.." && pwd)
patches="$repo_root/pkgs/pi-extensions/patches"
agent_src="${AGENT_PI_SRC:-$HOME/src/agent-pi}"
work="${PLAN_GRILL_WORK:-$HOME/.cache/pi-a2-agent-pi-patched-$$}"

mkdir -p "$work"
rsync -a --exclude /.git --exclude /extensions/node_modules --exclude /node_modules "$agent_src/" "$work/"

patch -d "$work" -p1 < "$patches/agent-pi-tool-caller-security.patch"
patch -d "$work" -p1 < "$patches/agent-pi-shortcuts.patch"
patch -d "$work" -p1 < "$patches/agent-pi-runtime-paths.patch"
patch -d "$work" -p1 < "$patches/agent-pi-plan-grill-gate.patch"

test -f "$work/extensions/plan-grill-gate.ts"
test ! -f "$work/extensions/plannotator-bridge.ts"
grep -Fq 'QA_AUTOMATION_ROOT' "$work/skills/qa-automation/README.md"
grep -Fq 'NANO_BANANA_SKILL_DIR' "$work/skills/nano-banana/SKILL.md"
grep -Fq '__piResetPlanGrill' "$work/extensions/mode-cycler.ts"
grep -Fq '__piAssertPlanGrillReady' "$work/extensions/lib/plannotator-client.ts"
grep -Fq 'resolvePlanFile' "$work/extensions/plan-viewer.ts"
grep -Fq '## Mandatory grill-with-docs gate' "$work/extensions/lib/mode-prompts.ts"
if grep -Fq 'plannotator-bridge' "$patches/agent-pi-runtime-paths.patch"; then echo 'runtime-paths still patches missing bridge' >&2; exit 1; fi

if [ -d "$agent_src/extensions/node_modules" ]; then
  mkdir -p "$work/extensions"
  rsync -a "$agent_src/extensions/node_modules/" "$work/extensions/node_modules/"
fi

cp "$repo_root/pkgs/pi-extensions/fixtures/plan-grill-gate.runtime.test.ts" \
  "$work/extensions/__tests__/plan-grill-gate.runtime.test.ts"

fake_home="$work/.fake-home"
mkdir -p "$fake_home"
export HOME="$fake_home"

(
  cd "$work/extensions"
  npx --no-install vitest run --config __tests__/vitest.config.ts
)

printf '%s\n' "apply-agent-pi-patches-and-test: PASS"
printf '%s\n' "work tree: $work"
