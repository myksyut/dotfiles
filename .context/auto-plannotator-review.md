# Plan: Hook work completion to `/plannotator-review`

## Decision

Hunk の after-run は使わない。**タスクが全部終わったタイミング**で Plannotator の code review を自動で開く。

毎ターン開くとブラウザがうるさい。agent-pi にはすでに「未完了タスクがあると `agent_end` で nudge」があるので、完了の定義はそれに合わせる。

```
write/edit があった
  → タスクが全部 done
  → agent_end
  → Plannotator code-review が開く
  → アノテは follow-up でエージェントに返る
```

## Trigger

`extensions/completion-report.ts` に hook を足す。新規ファイルは作らない。

**開く条件（全部満たす）**

- TUI
- `PI_SUBAGENT` ではない
- このセッションで `write` / `edit` が成功している
- `__piTaskList` があり `remaining === 0` かつ `total > 0`
- レビューがすでに進行中ではない
- 同じ完了サイクルで `show_report` をまだ開いていない

**開かない**

- タスクリストがない（手動で `/plannotator-review` か `show_report`）
- 未完了タスクがある（既存の nudge に任せる）
- subagent
- 読み取りだけ

## Behavior

`agent_end` は待たない。`void` で `codeReviewWithPlannotator` を走らせる。

終わったら `/plannotator-review` と同じく結果を返す:

- approved → notify
- feedback あり → `sendMessage` follow-up（`triggerTurn: true`）
- close / 失敗 → notify だけ

`show_report` が先にレビューを開いていたら hook はスキップ。二重起動しない。

## Out of scope

- Hunk の削除（`review: off` のまま）
- 毎ターン after-run
- Plannotator 本体の改造
- nix-config の変更

## Critical files

| File | Action |
|---|---|
| `~/src/agent-pi/extensions/completion-report.ts` | Modify — mutation 追跡 + agent_end hook |
| `~/src/agent-pi/extensions/lib/plannotator-client.ts` | Read-only |
| `~/src/agent-pi/extensions/tasks.ts` | Read-only（`__piTaskList`） |

## Verification

1. タスクを立ててファイルを編集し、全部 done にしてターン終了 → Plannotator review が開く
2. 未完了タスクがあるときは開かない
3. タスクリストなしでは開かない
4. `show_report` を呼んだ完了では二重に開かない
5. レビューのアノテがエージェントへの follow-up になる
