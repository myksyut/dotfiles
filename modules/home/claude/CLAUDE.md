- 自分で「設計・複数ファイル・方針が割れる」と判断したとき、ユーザーが `/plan` しなくても計画へ入る

## 分類

- 小さい修正・調査・単発の質問 → そのまま実行（auto）
- 設計・複数ファイル・方針が割れる作業 → 計画。実装しない

## Plan が必要なとき

1. skill `grill-with-docs` を読む
2. ラウンド制で前提・用語・意思決定を詰める（`AskUserQuestion` または ❓/➡️）
3. `.context/todo.md` に計画と `## Grill checkpoint`（要約・決定・Open questions: none）を書く
4. 計画ができたら Plan mode を抜ける（`ExitPlanMode`）。ここで Plannotator がブラウザで開く
5. 承認後、`.context/.grill-gate.json` に todo.md の SHA-256 を書いてから実装する

Plannotator は Plan に入った瞬間ではなく、計画を承認に出すとき開く。使えないときだけチャット承認へ fallback する。
grill 未完了のまま実装しない。PreToolUse hook が未承認の `Write`/`Edit` を拒否する。

## 永続ドキュメント

- 確定した用語 → `CONTEXT.md`
- 戻しにくい意思決定 → `docs/adr/`
- 計画は `.context/todo.md`（タスク単位、承認用）
