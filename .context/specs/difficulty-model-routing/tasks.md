# Tasks

- [ ] 1. `~/src/agent-pi` に myksyut/agent-pi を clone する
- [ ] 2. `models.json` を `default` / `tiers` / `kinds` / `agents` に拡張する
- [ ] 3. `resolveExecutionModel()` と単体テスト
- [ ] 4. `set_model` ツール（tier / kind / reason / force）
- [ ] 5. 同じモデルなら no-op、未知モデルは notify + 据え置き
- [ ] 6. Ctrl+L 手動ロック。`force: true` だけ上書き
- [ ] 7. criteria.md を mode prompt に載せる
- [ ] 8. `subagent_create` が resolver を使い、未指定なら親の直近 set_model を継承
- [ ] 9. reviewer は必ず `openai-codex/gpt-5.6-sol`
- [ ] 10. chain / pipeline step に `tier` / `kind` を渡す（メインは自動切替しない）
- [ ] 11. 任意で task に difficulty/kind 表示（トリガーにはしない）
- [ ] 12. `~/.pi/agents/models.json`（または nix-config home）にユーザー対応を置く
- [ ] 13. agent-pi を push し、nix-config の flake.lock を更新する
