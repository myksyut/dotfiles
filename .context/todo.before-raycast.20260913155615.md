# Plan: Drop agent-pi modes, let Plannotator own planning

## Decision

前回プランは「モードは残して UI だけ差し替え」。却下。
**agent-pi のモードを消して、計画フローは Plannotator に任せる。**

- PLAN / SPEC モード、`set_mode`、Shift+Tab サイクルを削除
- 計画は `/plannotator-plan-mode` / `Ctrl+Alt+P` / `pi --plan`
- 承認後の実行は Plannotator（`executionMode: automatic`）
- TEAM / CHAIN / PIPELINE はモードではなく、今ある slash command で起動

## After

```
通常作業     → 普通の Pi（agent-pi 拡張はそのまま）
計画が必要   → Ctrl+Alt+P
             → 計画ファイルを書く
             → plannotator_submit_plan
             → ブラウザで Approve / Annotate
             → Plannotator が実行
チーム作業   → /agents-team（モードバーなし）
```

## Phase 1: Tear out the mode switcher

**Remove / gut** → `~/src/agent-pi/extensions/mode-cycler.ts`

- `set_mode` tool 削除
- `/mode` 削除
- Shift+Tab バインド削除
- PLAN_PROMPT / SPEC_PROMPT の注入削除
- `__piCurrentMode` を書かない

**Modify** → `~/src/agent-pi/extensions/lib/mode-prompts.ts`

- PLAN / SPEC プロンプトを削除、または未使用にする
- NORMAL プロンプトから「set_mode で PLAN/SPEC に入れ」を消す
- 計画が必要なら `/plannotator-plan-mode` を案内する一文だけ残す

**Modify** → nix-config `modules/home/pi.nix`

- thinking を Shift+Tab に戻してよい（mode に譲る理由が消える）
- `executionMode` を `"automatic"` に変更
- `AGENT_PI_PLAN_REVIEWER` は不要になる（plan-review bridge に頼らない）

## Phase 2: Ungate TEAM / CHAIN / PIPELINE

今は `__piCurrentMode === "TEAM"` のときだけプロンプトが乗る。

**Modify**

- `extensions/agent-team.ts`
- `extensions/agent-chain.ts`
- `extensions/pipeline-team.ts`

モード値ではなく、各自の slash command が立てる active フラグでゲートする。
コマンドを叩いていないときはプロンプトを出さない。

## Phase 3: Viewers

PLAN モードが無いので `show_plan` を必須ゲートにしない。

- `show_plan` / `show_spec` は残すが、呼ばれたら Plannotator annotate / plan-review に流す（前回の bridge を流用）
- プロンプトはこれらを「必ず呼べ」とは書かない
- board / chat / cleanup / report はそのまま

## Phase 4: Keybinds & docs

- `Ctrl+Alt+P` = Plannotator plan mode（既存）
- Shift+Tab = thinking cycle に戻す
- agent-pi README のモード表を削除し、Plannotator 計画フローに書き換え

## Critical files

| File | Action |
|---|---|
| `~/src/agent-pi/extensions/mode-cycler.ts` | Gut / delete |
| `~/src/agent-pi/extensions/lib/mode-prompts.ts` | Modify |
| `~/src/agent-pi/extensions/lib/mode-cycler-logic.ts` | Delete if unused |
| `~/src/agent-pi/extensions/agent-team.ts` | Modify (ungate) |
| `~/src/agent-pi/extensions/agent-chain.ts` | Modify (ungate) |
| `~/src/agent-pi/extensions/pipeline-team.ts` | Modify (ungate) |
| `~/src/agent-pi/extensions/plan-viewer.ts` | Keep, optional bridge |
| `modules/home/pi.nix` | `executionMode: automatic`, thinking key |
| `modules/home/default.nix` | 既存の pi wrap と整合 |

## Verification

1. 起動直後に PLAN バーが出ない
2. Shift+Tab でモードが変わらない
3. `Ctrl+Alt+P` で Plannotator 計画に入る
4. 承認後、同じセッションで実行に入る
5. `/agents-team` だけ TEAM 相当のプロンプトが乗る
6. `set_mode` ツールがカタログに無い
