# 難易度ベースのモデル切替

いまの agent-pi は **役割ごと** にモデルを固定している。難易度では切り替わらない。

## いまの割り当て

| 対象 | モデル |
|------|--------|
| メインセッション | `xai/grok-4.6` + thinking high |
| scout | `x-ai/grok-4.1-fast` |
| builder | `anthropic/claude-haiku-4-5` |
| planner / tester | `openai-codex/gpt-5.4` |
| reviewer / paladin / warden | `anthropic/claude-opus-4-6` |

モード切替（Shift+Tab / `set_mode`）はプロンプトだけ変える。`pi.setModel()` は呼ばない。
タスクにも difficulty フィールドはない。

使える候補: grok-4.6 / grok-build-0.1 / haiku / sonnet / opus / gpt-5.4 / gpt-5.4-mini / ローカル qwen3.8:27b など。

---

## Q1. 何を切り替えたい？
Default: メインセッション + サブエージェント両方

## Q2. 難易度は誰が決める？
Default: エージェントがタスク作成時に判定し、必要ならユーザーが上書き

## Q3. トリガーはどれ？
Default: タスク / チェーンステップの難易度。モード連動はしない

- タスクごとに切替（inprogress になったタスクの難易度）
- チェーン / パイプラインのステップごと
- モード連動（NORMAL=軽、PLAN/SPEC=重）
- 全部

## Q4. ティアはどう分ける？
Default: easy / mid / hard の3段階

## Q5. モデル対応は？
Default: easy=haiku or grok-build / mid=grok-4.6 or sonnet / hard=opus or gpt-5.4

希望の対応を書いてください。thinking も一緒に下げる？

## Q6. どこに実装する？
Default: agent-pi 本体に機能追加 + ユーザーの models.json で上書き
