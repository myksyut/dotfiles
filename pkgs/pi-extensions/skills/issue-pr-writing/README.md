# issue-pr-writing

Linear 向け文章と GitHub PR 本文を作成・編集・レビューする Pi Agent Skill です。AI Patent Rocket（AIPR）のように、プロジェクト固有の用語集と運用ルールにも対応します。

## 対象

- Linear Issue のタイトル・description
- Project summary・description
- コメント・ステータス更新
- GitHub PR 本文

Web、Core、Patent DB、dev、test、Stg、Prd の責務・環境を区別し、固定スキーマと検証可能な完了条件で文章を作ります。

## 動作範囲

文章本文を返すスキルです。依頼に明示されていない限り、Linear や GitHub への書き込みは行いません。PR タイトルの生成は対象外です。

## 参照ファイル

- `GUIDE.md`: 文章規範と自己点検チェックリスト
- `templates.md`: 文書種別ごとの固定スキーマ
- `aipr-glossary.md`: AIPR の責務・環境・出荷段階・表記
- `examples.md`: 匿名化した良い例・悪い例

## Installation

このスキルはNix設定からPiパッケージとして管理されます。Nix設定を反映した後、Piで`/reload`を実行してください。
