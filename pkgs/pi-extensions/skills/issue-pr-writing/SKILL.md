---
name: issue-pr-writing
description: Linear の Issue・Project・コメント・ステータス更新と GitHub PR 本文を作成・編集・レビューする。プロジェクト固有の用語と固定スキーマに沿って文章を整える。「Linear の文章を書いて」「Issue を作成・整えて」「Project description を作って」「コメントを直して」「PR の本文を書いて」「プルリクの説明文を作って」「PR 本文をレビューして」と言われたとき、または issue-pr-writing と明示されたときに使う。
---

# issue-pr-writing

AIPR の Linear 向け文章と GitHub PR 本文を作成、編集、レビューするときに使う。

## 手順

1. 依頼を Issue、Project、コメント・ステータス更新、PR 本文のいずれかに分類する。
2. `GUIDE.md` を最初に全文読む。
3. `templates.md` の該当スキーマを選び、必要に応じて `aipr-glossary.md` と `examples.md` を読む。
4. 固定見出し・順序を保ち、確認済みの事実、推論、未確認事項を分けて文章を書く。
5. 空欄、プレースホルダー、根拠のない数値・担当・環境・完了状態を残さず、未確認の内容は `?` または確認事項として示す。
6. 完成した本文だけを返す。依頼に明示されていない Linear や GitHub への書き込みは行わない。

## 固定ルール

- AIPR 用語集に従い、Web、Core、Patent DB、dev、test、Stg、Prd を具体的に書く。
- Issue の完了条件は、観測できる結果と確認手段で書く。
- PR 本文は `templates.md` の8見出しを省略・改名・並べ替えしない。
- PR 本文の変更内容・検証・影響範囲は git diff、実行結果、関連 Issue、または依頼者が与えた context に接地させる。
- PR タイトルは作成・変更しない。
- Linear API、GitHub CLI、その他の連携ツールは、文章作成のために自動実行しない。
