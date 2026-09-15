---
status: accepted
---

# DevboxのNix管理主体を開発利用者から分離する

sandbox必須・fallback禁止のsingle-user Nix 2.35.2は、検証用Ubuntu VMで初期profile作成に失敗した。保護を無効化せず、**新規のroot所有store、非trustedのDevbox利用者、専用buildユーザー、監督対象のdaemon**を持つ構成を設計する。これは全Linuxでsingle-userが不可能という判断ではなく、候補構成を切り替えて実証するための設計判断である。

本セッションの質問回答で、Fly統合までの一括設計と、公式固定配布物からの限定的なbootstrapを選択した。2026-09-06のPlannotatorレビューで設計を承認済み。当時は実装・導入が未承認であり、この設計承認だけでは着手しなかった。その後、別の[実装・新規ローカルVM実証計画](../CLOUD-DEVBOX-MULTI-USER-IMPLEMENTATION.md)をPlannotatorで承認し、実装に着手した。Fly導入・実認証は引き続き未承認。結果は[検証記録](../CLOUD-DEVBOX-MULTI-USER-VALIDATION.md)へ分離する。

設計承認時のセッション計画（後続実装計画に更新する前）: `/Users/miyakishota/.context/todo.md`。SHA-256: `4e83e9e12cea6939490c6037567d976df6efd87a9b6f7f326b67ba5109ae929f`。以前の別作業計画は同directoryの`todo.before-devbox-multi-user-20260905.md`へ保全した。

## Considered Options

- sandbox/AppArmorを無効化する回避: 要件に反するため採用しない。
- ユーザー書込み可能だったstoreをchownして再利用: 内容の信頼は所有権変更だけでは回復しないため採用しない。
- 公式multi-user installerをそのまま実行: systemd/profile等の広い自動変更をFlyの通常起動に持ち込まないため、今回は限定bootstrapを設計する。ただし固定配布物・登録情報・公式のstore権限モデルは利用する。

## Consequences

rootがNixを実行する前にstoreの由来と所有権を保証する必要がある。既存のUID10001だけの停止検査では専用buildユーザーを見落とすため、daemonの接続・待機要求・workerを含む停止契約も変更する。安全を証明できない場合は停止拒否を維持する。

復旧方針も質問回答で確定した。通常stop/startはVolumeを維持する一方、災害復旧backupではNix storeを除外し、固定seed/flake.lockから再構築する。利用者profileとroot GC rootは再作成し、復元されたready metadataは現行承認にしない。入力を再取得できない場合は復旧未完了として扱う。

詳細: [実装計画案](../CLOUD-DEVBOX-MULTI-USER-PLAN.md)。
