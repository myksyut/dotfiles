#!/usr/bin/env bash
# tmux-session-gc.sh — 放置された tmux セッションを掃除する。
#
# 「tmux セッションが溜まって重い」の主因は worktree ごとに作ったセッションを消さないこと。
# セッション自体は軽い (~1MB) が、中で起動した Claude Code + MCP サーバーが生き続けて
# 積み上がる (1 セッション ≈ claude 100MB + MCP 60MB)。N 本溜めれば GB 級になる。
# そこで「一定時間 無活動(idle) かつ 開発プロセスが動いていない」セッションを掃除する。
#
# 判定軸は session_attached ではなく session_activity(最終 pane 出力) からの idle 時間。
# 理由: 各セッションを ghostty のタブで開きっぱなし = 常に attached のため、
#       「未 attach」では放置を捉えられない。「無活動時間」が放置を正しく表す。
#
# モード:
#   --interactive (既定)  候補を fzf で一覧し、選んだものを kill (prefix+X の popup 起動)
#   --auto                idle>閾値 かつ 保護プロセス無し を無確認で kill (launchd 定期実行)
#   --dry-run             kill せず対象だけ表示
#   --idle-hours N        idle 閾値 (既定: 環境変数 TMUX_GC_IDLE_HOURS or 12)

set -uo pipefail

IDLE_HOURS="${TMUX_GC_IDLE_HOURS:-12}"
MODE="interactive"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --auto)        MODE="auto" ;;
    --interactive) MODE="interactive" ;;
    --dry-run)     DRY_RUN=1 ;;
    --idle-hours)  shift; IDLE_HOURS="$1" ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

IDLE_SECS=$(( IDLE_HOURS * 3600 ))
NOW=$(date +%s)

# pane_pid から子孫 PID を再帰列挙
descendants() {
  local c
  for c in $(pgrep -P "$1" 2>/dev/null || true); do
    echo "$c"
    descendants "$c"
  done
}

# セッション配下で動作中の全プロセスの comm を改行区切りで返す
session_process_comms() {
  local session="$1" pid d
  for pid in $(tmux list-panes -t "=$session" -F '#{pane_pid}' 2>/dev/null || true); do
    for d in $pid $(descendants "$pid"); do
      ps -o comm= -p "$d" 2>/dev/null || true
    done
  done
}

# 保護判定: return 0 = 保護(消すな) / return 1 = 掃除してよい
is_protected_session() {
  local session="$1"
  local comms
  comms="$(session_process_comms "$session")"

  # claude(Claude Code 本体) と node(MCP サーバー・JS 系 dev server) を中核に、
  # 主要な常駐開発プロセスを保護する。comms は 1 行 1 プロセスなので行アンカー ^...$ で
  # 完全一致させ、node_exporter のような無関係プロセスの巻き込みを防ぐ。
  # grep -q の終了ステータスがそのまま関数の戻り値: マッチ=0(保護) / 非マッチ=1(掃除可)。
  printf '%s\n' "$comms" \
    | grep -qiE '^(claude|node|deno|bun|vite|next-server|python[0-9.]*|ruby|cargo|rustc|nvim|vim)$'
}

# 現在のセッション（popup 呼び出し元）。auto/launchd 経由なら空 → self 除外が無効化される。
CURRENT="$(tmux display-message -p '#{session_name}' 2>/dev/null || true)"

# 候補収集: tab 区切りで name / idle秒 / attached / protected / comms要約 を 1 行ずつ
collect() {
  local name act att idle prot summary
  while IFS=$'\t' read -r name act att; do
    [ -n "$name" ] || continue
    [ "$name" = "$CURRENT" ] && continue   # self は対象外（誤kill防止）
    idle=$(( NOW - act ))
    if is_protected_session "$name"; then prot="protected"; else prot="free"; fi
    summary="$(session_process_comms "$name" \
      | grep -viE '^(-?(zsh|bash|sh)|ps|pgrep|tmux|grep)$' | sort -u | paste -sd, - 2>/dev/null)"
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$idle" "$att" "$prot" "${summary:-（空シェル）}"
  done < <(tmux list-sessions -F '#{session_name}	#{session_activity}	#{session_attached}' 2>/dev/null || true)
}

fmt_idle() {  # 秒 → 人間可読
  local s="$1"
  if [ "$s" -ge 3600 ]; then echo "$(( s / 3600 ))h$(( (s % 3600) / 60 ))m"
  else echo "$(( s / 60 ))m"; fi
}

kill_session() {
  local name="$1"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] would kill: $name"
  else
    tmux kill-session -t "=$name" && echo "killed: $name"
  fi
}

# bash 3.2(macOS) も対象なので mapfile を避けて配列構築
ROWS=()
while IFS= read -r line; do
  [ -n "$line" ] && ROWS+=("$line")
done < <(collect)

if [ "${#ROWS[@]}" -eq 0 ]; then
  echo "掃除対象になりうるセッションがありません。"
  exit 0
fi

# --- auto: idle>閾値 かつ free を無確認 kill ---
if [ "$MODE" = "auto" ]; then
  killed=0
  for row in "${ROWS[@]}"; do
    IFS=$'\t' read -r name idle att prot summary <<<"$row"
    if [ "$idle" -ge "$IDLE_SECS" ] && [ "$prot" = "free" ]; then
      kill_session "$name"; killed=$(( killed + 1 ))
    fi
  done
  echo "auto-gc 完了: ${killed} セッション掃除（idle 閾値 ${IDLE_HOURS}h）"
  exit 0
fi

# --- interactive: fzf で選んで kill ---
menu() {
  local row name idle att prot summary mark
  for row in "${ROWS[@]}"; do
    IFS=$'\t' read -r name idle att prot summary <<<"$row"
    if [ "$prot" = "protected" ]; then mark="⚠ 動作中"; else mark="・放置"; fi
    printf '%s\t%-34s  idle %-7s  attached=%s  %s  %s\n' \
      "$name" "$name" "$(fmt_idle "$idle")" "$att" "$mark" "$summary"
  done
}

selected="$(menu | fzf --multi \
  --with-nth=2.. --delimiter=$'\t' \
  --header='Tab=複数選択 / Enter=kill / Esc=中止   ⚠=開発プロセス動作中(消すと失う)' \
  --prompt='掃除する tmux session> ' \
  | cut -f1)"

[ -n "$selected" ] || { echo "中止しました。"; exit 0; }

while IFS= read -r name; do
  [ -n "$name" ] && kill_session "$name"
done <<<"$selected"
