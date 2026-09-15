# 難易度ベースのモデル切替

メインエージェントが **`set_model` を明示的に呼んで** モデルを切り替える。
ランタイムはタスク開始では自動切替しない。

モードは手順、モデルは難易度。別物。

判断基準の本体は [criteria.md](./criteria.md)。

## 対応

| tier / kind | モデル |
|-------------|--------|
| mid / 未指定 | `xai/grok-4.6` |
| easy | `openai-codex/gpt-5.6-luna` |
| hard / design / architecture | `anthropic/claude-fable-5` |
| review / reviewer | `openai-codex/gpt-5.6-sol` |

## 誰がいつ

- **判断**: メインエージェント。依頼を読んだ直後、作業前。性質が変わったら再度。
- **実行**: `set_model { tier, kind?, reason }`。モデル名は直指定しない。
- **サブエージェント**: ロールが先（reviewer=sol）。未指定なら親の判定を継承。

## 解決順

1. 呼び出し側の明示 override（例外。通常使わない）
2. ロール（`reviewer` → sol）
3. kind（design / architecture / review）
4. tier（easy / mid / hard）
5. default（grok-4.6）

## 対象外

- タスク inprogress での自動切替
- モード連動
- モデル ID の直指定を通常経路にしない
- toolkit CLI ワーカー
- thinking level の連動
