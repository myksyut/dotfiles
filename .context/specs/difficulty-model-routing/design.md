# Design

実装先は **myksyut/agent-pi**。nix-config はそれを flake input で食う。

```bash
git clone git@github.com:myksyut/agent-pi.git ~/src/agent-pi
nix run .#switch -- --override-input agent-pi path:$HOME/src/agent-pi
```

## Config

`models.json` を拡張。既存の `default` / `agents` は残す。

```json
{
  "default": { "provider": "xai", "model": "grok-4.6" },
  "tiers": {
    "easy": { "provider": "openai-codex", "model": "gpt-5.6-luna" },
    "mid":  { "provider": "xai", "model": "grok-4.6" },
    "hard": { "provider": "anthropic", "model": "claude-fable-5" }
  },
  "kinds": {
    "design":       { "provider": "anthropic", "model": "claude-fable-5" },
    "architecture": { "provider": "anthropic", "model": "claude-fable-5" },
    "review":       { "provider": "openai-codex", "model": "gpt-5.6-sol" }
  },
  "agents": {
    "reviewer": { "provider": "openai-codex", "model": "gpt-5.6-sol" }
  }
}
```

解決順: プロジェクト → `~/.pi/agents/models.json` → パッケージ同梱。

## Resolver

`extensions/lib/agent-defs.ts` に純関数。

```ts
resolveExecutionModel({ override?, agentName?, kind?, difficulty?, config })
```

優先: override → ロール → kind → tier → default。

## set_model ツール

`extensions/mode-cycler.ts` か新しい `extensions/model-router.ts` に置く。

```
set_model
  tier: "easy" | "mid" | "hard"     // mid は明示リセット用
  kind?: "design" | "architecture" | "review"
  reason: string                    // 必須
  force?: boolean                   // 手動ロック解除
```

流れ:

1. resolver で provider/model を決める
2. 今と同じなら no-op
3. 手動ロック中かつ `force` でないなら拒否
4. レジストリから `Model` を引いて `pi.setModel`
5. `__piCurrentModelTier` / `__piCurrentModelKind` を保存（サブエージェント継承用）
6. notify

手動ロック: `model_select` イベントで `__piManualModelLock = true`。
`set_model { force: true }` かユーザーの次の手動変更で外す。

タスク inprogress では呼ばない。

## Prompts

criteria.md の判定手順・禁止事項・例を `mode-prompts.ts` に短い形で埋め込む。

必須ルール:

- 作業前に判定する
- mid なら呼ばなくてよい
- easy は4条件すべて
- 迷ったら mid
- モードだけでは上げない
- 性質が変わったときだけ再呼び出し

## Subagents / chains

`subagent_create` に optional `tier` / `kind`。未指定なら `__piCurrentModelTier/Kind`。
`name=reviewer` は常に sol。

YAML step も同じフィールド。ステップ開始時にそのワーカーへ渡すだけで、メインは触らない。

## Tasks

`difficulty` / `kind` は任意メタデータ（表示と記録用）。切替のトリガーにはしない。

## Thinking

変えない。
