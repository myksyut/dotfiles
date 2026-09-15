#!/usr/bin/env bash
# Merge Nix-managed Pi packages and startup keys into settings.json.
# Does not replace unmanaged keys. On jq/IO failure the original file is kept.
set -euo pipefail

settings_path="${1:?settings path is required}"

: "${AGENT_PI:?}"
: "${PI_HUNK:?}"
: "${PLANNOTATOR:?}"
: "${CONTEXT_VIEW:?}"
: "${WEB_ACCESS:?}"
: "${SESSION_RECALL:?}"
: "${PI_FFF:?}"
: "${PI_LENS:?}"
: "${RPIV_ASK_USER:?}"
: "${PI_BTW:?}"
: "${CODEX_IMAGE_GEN:?}"
: "${PI_VCC:?}"
: "${PI_LINEAR:?}"
: "${SKILL_CREATOR:?}"
: "${ISSUE_PR_WRITING:?}"
: "${REMOTE_CONTROL:?}"
: "${PI_GOAL:?}"
: "${CODEX_FAST:?}"

enable_remote_control="${ENABLE_REMOTE_CONTROL:-true}"
case "$enable_remote_control" in
true | false) ;;
*)
  printf '%s\n' 'ENABLE_REMOTE_CONTROL must be true or false' >&2
  exit 1
  ;;
esac

default_provider="${DEFAULT_PROVIDER:-openai-codex}"
default_model="${DEFAULT_MODEL:-gpt-6-astra}"
default_thinking_level="${DEFAULT_THINKING_LEVEL:-high}"

settings_dir="$(dirname "$settings_path")"
mkdir -p "$settings_dir"

if [ -L "$settings_path" ]; then
  printf '%s\n' "merge-pi-settings: refuse symlink: $settings_path" >&2
  exit 1
fi

if [ ! -e "$settings_path" ]; then
  printf '%s\n' '{}' >"$settings_path"
  chmod 600 "$settings_path"
elif [ ! -f "$settings_path" ]; then
  printf '%s\n' "merge-pi-settings: refuse non-regular file: $settings_path" >&2
  exit 1
fi

file_mode() {
  if stat -c '%a' "$1" >/dev/null 2>&1; then
    stat -c '%a' "$1"
  else
    python3 -c 'import os, sys; print(oct(os.stat(sys.argv[1]).st_mode)[-3:])' "$1"
  fi
}

mode="$(file_mode "$settings_path")"
tmp="$(mktemp "$settings_dir/.settings.json.XXXXXX")"

cleanup() {
  if [ -n "${tmp:-}" ] && [ -e "$tmp" ]; then
    rm -f "$tmp"
  fi
}
trap cleanup EXIT

jq -s -e \
  --arg agentPi "$AGENT_PI" \
  --arg piHunk "$PI_HUNK" \
  --arg plannotator "$PLANNOTATOR" \
  --arg contextView "$CONTEXT_VIEW" \
  --arg webAccess "$WEB_ACCESS" \
  --arg sessionRecall "$SESSION_RECALL" \
  --arg piFff "$PI_FFF" \
  --arg piLens "$PI_LENS" \
  --arg rpivAskUser "$RPIV_ASK_USER" \
  --arg piBtw "$PI_BTW" \
  --arg codexImageGen "$CODEX_IMAGE_GEN" \
  --arg piVcc "$PI_VCC" \
  --arg piLinear "$PI_LINEAR" \
  --arg skillCreator "$SKILL_CREATOR" \
  --arg issuePrWriting "$ISSUE_PR_WRITING" \
  --arg remoteControl "$REMOTE_CONTROL" \
  --argjson enableRemoteControl "$enable_remote_control" \
  --arg piGoal "$PI_GOAL" \
  --arg codexFast "$CODEX_FAST" \
  --arg defaultProvider "$default_provider" \
  --arg defaultModel "$default_model" \
  --arg defaultThinkingLevel "$default_thinking_level" \
  '
    def source:
      if type == "string" then .
      elif type == "object" then (.source // "")
      else ""
      end;
    def managed:
      (source | test("^(git:github.com/(ruizrica|myksyut)/agent-pi|npm:(pi-hunk|@plannotator/pi-extension|pi-context-view|pi-ask-user|pi-web-access|@ogulcancelik/pi-session-recall|@ff-labs/pi-fff|pi-lens|@juicesharp/rpiv-ask-user-question|pi-btw|pi-codex-image-gen|@sting8k/pi-vcc|@alasano/pi-linear|@tmustier/pi-skill-creator|pi-remote-control|@narumitw/pi-goal|@calesennett/pi-codex-fast|pi-claude-auth|@pankajudhas81/pi-claude-auth)(@.*)?$|(.*/)?nix/store/[a-z0-9]+-(agent-pi|pi-hunk|plannotator-pi-extension|pi-context-view|pi-web-access|pi-session-recall|pi-fff|pi-lens|rpiv-ask-user-question|pi-btw|pi-codex-image-gen|pi-vcc|pi-linear|pi-skill-creator|aipr-writing|issue-pr-writing|pi-remote-control|pi-goal|pi-codex-fast|pi-claude-auth)-)"));
    if length != 1 then error("expected exactly one JSON value") else .[0] end
    | if type != "object" then error("expected a JSON object") else . end
    | if has("packages") and (.packages | type != "array") then
        error("packages must be an array")
      else . end
    | .packages = (
      ((.packages // []) | map(select(managed | not)))
      + [
        { source: $agentPi, extensions: ["!extensions/user-question.ts"] },
        $piHunk,
        $plannotator,
        $contextView,
        $webAccess,
        $sessionRecall,
        $piFff,
        $piLens,
        $rpivAskUser,
        $piBtw,
        $codexImageGen,
        $piVcc,
        $piLinear,
        $skillCreator,
        $issuePrWriting,
        (if $enableRemoteControl then $remoteControl else empty end),
        $piGoal,
        { source: $codexFast, extensions: ["extensions/codex-fast.ts"] }
      ]
    )
    | .defaultProvider = $defaultProvider
    | .defaultModel = $defaultModel
    | .defaultThinkingLevel = $defaultThinkingLevel
  ' "$settings_path" >"$tmp"

chmod "$mode" "$tmp"
mv "$tmp" "$settings_path"
tmp=""
