---
name: codex-image-gen
description: >-
  画像を生成する。ChatGPT Images 2.0 / Codex、または Claude Code のネイティブ画像生成を使う。
  「画像を作って」「イラストを生成」「image generation」「アイコンを描いて」で必ず使う。
---

# codex-image-gen

Pi の `pi-codex-image-gen` 相当。画像をワークスペースに保存する。

## 手順

1. モデルに画像生成ツールがあるならそれを使う。
2. なければ `codex` CLI、または ChatGPT Images 2.0 で生成する。
3. プロンプトは被写体・構図・スタイル・文字・制約を具体的に書く。
4. 成果ファイルのパスを返し、未保存のプレビューだけで終わらない。

## やってはいけないこと

- 外部の不特定画像 API へ秘密を送ること
- 既存ファイルを上書きする前に確認しないこと
