# AIPR 用語集

Linear の文章で責務、環境、出荷段階を具体的に書くための用語を定義する。

## リポジトリと責務

| 呼称 | リポジトリ・サービス | 責務 | Issue で明記する観点 |
| --- | --- | --- | --- |
| Web | `ai_patent_rocket_web_mvp` | Django + React の画面、内部 API、agent module、検索式生成、SSE 配信、Patent DB への問い合わせ仲介 | 画面、内部 API、検索式、SSE のどこを変えるか |
| Core | `ai_patent_rocket_mvp` | AWS Batch で動く特許分析コア。Web の `containers/patent_analysis_core/ai_patent_rocket_mvp` に submodule として配置 | バッチの入力、分析処理、出力のどこを変えるか |
| Patent DB | `ai-patent-rocket-patent-db` | 別チームが管理する検索 API。API Gateway 経由で Expr を OpenSearch クエリへ変換し、件数・文書を返す | Expr、検索 API、検索件数、取得文書のどこを変えるか |

「システム側で修正する」と書かず、Web、Core、Patent DB のどの責務かを特定する。複数にまたがる場合は、境界で渡すデータと各側の変更を分けて書く。

## 環境と反映経路

| 表記 | 用途・反映経路 |
| --- | --- |
| dev | 開発環境。ローカル実行または Docker Compose で開発する |
| test | テスト環境。CI や Docker 内の自動テストで使う |
| Stg | `main` への push で `Deploy to STG` が自動実行される。URL は `https://stg.ai-patent-rocket.emuniinc.jp` |
| Prd | `release-*` ブランチへの push または `workflow_dispatch` で `Deploy to PRD` が実行される。job は GitHub environment `production` に紐づく |

反映先は「環境」とだけ書かず、Stg または Prd と書く。GitHub environment `production` との紐づけは確認できるが、それ以外の承認運用を意味するとは限らない。

## 出荷の段階

出荷状態は次の 5 段階で書く。

1. 未マージ
2. main マージ済み
3. Stg 反映済み（受入確認できる）
4. Prd 反映済み（顧客が使える）
5. 顧客告知済み

Linear のステータス名だけでは「顧客提供済み」か判断できない。コメントには上記の段階と確認根拠を書く。

出荷承認を述べる場合、確認できる事実は Prd の `workflow_dispatch` と GitHub environment `production` への紐づけまでである。誰が出荷承認するか、承認会議があるかはリポジトリから確認できないため、次のように残す。

> 確認事項: Prd 反映前の出荷承認者と承認手順を、運用責任者に確認する。

## 曖昧語の言い換え

| 避ける表現 | 書き換え方 |
| --- | --- |
| システム | Web / Core / Patent DB のどれか |
| デプロイした | Stg 反映済み / Prd 反映済み |
| 環境 | dev / test / Stg / Prd のどれか |
| 対応した | 誰が何をできる、何が表示される、何が返るなどの結果 |
| 一部 | 対象名と件数。未確認なら `?` または確認事項 |

## 表記の固定

| 概念 | 表記 |
| --- | --- |
| 特許分析 | 文章では「特許分析」、コード識別子は `patent_analysis` |
| 検索式 | 文章では「検索式」、Patent DB と受け渡す式木は Expr |
| パスワードレス認証 | マジックリンク |
| 組織単位 | テナント |
| 利用量に応じた課金 | クレジット課金 |
| Linear Issue | `AIPR-###`。タイトルには含めない |

## PR 本文で使う用語

| 表記 | 意味・使い方 |
| --- | --- |
| `Deploy to STG` | `main` への push で自動実行される GitHub Actions のジョブ名。成功をもって「Stg 反映済み」と書ける |
| `Deploy to PRD` | `release-*` ブランチへの push または `workflow_dispatch` で実行される GitHub Actions のジョブ名。成功をもって「Prd 反映済み」と書ける。実行前に「Prd 反映済み」「出荷済み」と書かない |
| `release-*` | Prd 反映のトリガーとなるブランチ名パターン。PR 本文で Prd 反映を主張する根拠として使えるのはこのブランチへの push または `workflow_dispatch` の実行結果のみ |
| Core submodule パス | Web リポジトリでは `containers/patent_analysis_core/ai_patent_rocket_mvp`。Core への変更を PR 本文で書くときはこのパスまたは Core の責務名で示す |
| 出荷承認の確認事項 | Prd 反映前の承認者・承認手順はリポジトリから確認できないため、断定せず「確認事項: Prd 反映前の出荷承認者と承認手順を、運用責任者に確認する」のように書く |
