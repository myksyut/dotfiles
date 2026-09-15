# Raycast を 2.3.1.0 に更新

## 確認済みの方針

- ユーザー指定: このMacだけでなく共通設定も更新する。
- 現在のアプリは1.104.25。macOSは26.6.2で、旧macOS向け固定は不要。
- Homebrewの配布情報で確認した最新版は2.3.1.0。管理方法はNixのまま維持する。

## 変更

1. `modules/darwin/default.nix` のRaycast共通固定を2.3.1.0、公式arm64配布URLと検証済みSHA-256へ変更する。
2. `modules/darwin/hosts/miyagishoutanoMacBook-Pro.nix` の旧版上書きを空のモジュールに置き換える。ファイル削除や他の既存変更の上書きはしない。
3. 対象ホストのRaycastをNixで評価・ビルドし、アプリのバージョンを確認する。
4. 適用経路を確認する。管理者権限が必要なシステム切替は実行せずユーザーにコマンドを案内し、適用未完了を明示する。

## 範囲外

- flake.lockの一括更新、Homebrewへの移行、Raycastの設定・ユーザーデータの削除。
- 既存の無関係な変更の修正やコミット。

## Grill checkpoint

Summary: Nix管理を維持し、共通固定を2.3.1.0に更新。旧OS用ホスト上書きを解除。

Decisions:

- 共通設定も更新。

Open questions: none

## 完了条件

共通設定とホスト上書きが整合し、Raycast 2.3.1.0のビルドを検証。インストール適用の結果または権限上の制約を報告する。
