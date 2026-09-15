# Requirements

## Context

agent-pi はロールごとにモデルを固定している。モードはプロンプトだけ変える。
メインは常に Grok 4.6。

欲しい動き:

- 普段は Grok 4.6
- 簡単なら gpt-5.6-luna
- 重い仕事・設計・アーキテクチャは Fable 5
- レビューは gpt-5.6-sol
- **誰が切替えるか**: エージェントが `set_model` を明示的に呼ぶ
- **判断基準**: criteria.md に固定し、プロンプトへそのまま載せる

## User Stories

### US1 — エージェントが set_model する

As a user, I want the agent to choose a tier/kind and call `set_model` before working, so I can see why the model changed.

**Acceptance**

- `set_model` ツールがある。引数は `tier`, 任意の `kind`, 必須の `reason`
- モデル ID は通常引数にない
- すでに同じ解決結果なら no-op で「already on …」と返す
- 切替成功で footer が変わり、notify に `model → provider/id (tier/kind) — reason` が出る
- 未知モデル / API キーなしは切替せず notify

### US2 — 判断基準がプロンプトに固定されている

As a user, I want the classification rules to be explicit, so the agent does not upgrade to Fable just because something “feels hard”.

**Acceptance**

- criteria.md の判定手順と例が mode prompt に入る
- easy は4条件をすべて満たすときだけ
- 迷ったら mid。default のままなら `set_model` しなくてよい
- PLAN/SPEC に入っただけでは fable にしない
- レビュー以外で sol にしない

### US3 — 途中で性質が変わったら呼び直す

As a user, I want a second `set_model` when the work changes type (investigate → design, implement → review).

**Acceptance**

- プロンプトが「性質が変わったら再度呼べ」と指示する
- 毎メッセージ呼ばない

### US4 — レビュアーは常に sol

As a user, I want reviewer agents to use gpt-5.6-sol.

**Acceptance**

- `name=reviewer` は `openai-codex/gpt-5.6-sol`
- 明示 override だけがこれを超える

### US5 — サブエージェントはロール優先、未指定は親を継承

As a user, I want dispatched agents to follow the same table without the parent re-picking a raw model ID.

**Acceptance**

- ロール → kind → tier → default
- `subagent_create` は optional `tier` / `kind` を受け、未指定なら親の直近 `set_model` を継承

### US6 — チェーン / パイプライン

As a user, I want YAML steps to declare tier/kind so the step agent starts on the right model.

**Acceptance**

- step に任意の `tier` / `kind`
- 未指定ならそのエージェントのロール、それもなければ default
- メインの自動切替はしない

### US7 — 設定は models.json

As a user, I want to change the mapping without editing code.

**Acceptance**

- 解決順: プロジェクト → `~/.pi/agents/models.json` → パッケージ
- `default` / `tiers` / `kinds` / `agents` を上書きできる

### US8 — 手動モデルは尊重する

As a user, I want Ctrl+L to win until I (or the agent) explicitly change again.

**Acceptance**

- 手動変更後、エージェントの `set_model` は「手動ロック中。解除する？」と返し、デフォルトでは上書きしない
- `set_model { force: true }` だけがロックを外す

## Non-goals

- タスク inprogress での自動切替
- モードとモデルの 1:1
- thinking level 連動
- ローカル qwen をこの対応に入れる
