# Cloud Devbox — multi-user Nix実装・ローカル実証計画

状態: **show_planで実装・新規ローカルVM実証を承認済み。** 以下は承認時の計画を残したもの。実装の進捗・実測と未実証は[CLOUD-DEVBOX-MULTI-USER-VALIDATION.md](CLOUD-DEVBOX-MULTI-USER-VALIDATION.md)へ記録する。

作業リポジトリ: `/Users/miyakishota/.config/nix-config`。以下のコードパスはこのリポジトリ基準。
既に承認された詳細設計は `docs/CLOUD-DEVBOX-MULTI-USER-PLAN.md`、判断記録は `docs/adr/0001-devbox-multi-user-nix.md`。本計画はそのPhase 1〜5の実装許可と検証範囲を具体化する。技術条件を緩和しない。

## Grill checkpoint

Summary: 承認済みmulti-user Nix設計の実装と、新規ローカルVMでの実証まで進めることを確認した。

Decisions:

- 新規VMは4 vCPU・8GiB・80GiB上限、Nix buildは1job・2cores。旧VMと途中storeは保全し同時起動しない。
- 固定seed・root所有store・非trusted利用者・専用buildユーザー・sandbox必須を維持する。
- Fly作成・課金・実認証・公開・Mac/WSLへの設定適用・Pi設定変更は行わない。
- 不明なNix/Orca停止契約はunknownとして停止拒否する。保護を外して成功扱いしない。
- 起動・bootstrap・停止・配布を一括で実装し、実証できない条件は受入未完了として報告する。

Open questions: none

## 実装着手時に確認した現状（履歴）

- 旧VM `db-gate0` はStopped。現在4 vCPU・8GiB・80GiB。既存storeの信頼昇格や再利用はしない。
- `bootstrap.sh` はsingle-user installerとlocal storeを使用中。supervisorはNixをまだ監督していない。
- `safety.admission()` は既にnonblockingのshared/exclusive lockを実装済み。この仕組みを再利用し、不要な書換えをしない。
- 設計承認後の計画変更は `Decisions:` 後の空行だけ。元の承認時SHA-256へ復元照合済みで、設計変更はない。
- `flake.lock` SHA-256: `3187930aede623520400776a30820a6781ef63a106747378d6f3841c7f7f6216`。
- 既存stageのdiff SHA-256: `ea15a09a55278bbc8ea48076235f61be0df3fc3f475182b559bc78765bca0b2b`。stageを変更しない。
- 既存のPi関連・Darwin関連・その他の未コミット変更は保全する。commit/pushやstashも行わない。

## 実装順と対象

### 1. 固定seedからの新規store初期化

新規 `infra/devbox/nix/provision.py` と関連内部helper、`test_nix_runtime.py` を追加する。入力hash・archive/link・root所有・専用UID/GIDを検証してから公式seedをコピー・登録し、固定runtimeとroot GC rootを保護する。

`Dockerfile`、`.dockerignore`、`bootstrap_state.py` を変更する。開発利用者UID/GID10001、nixbld GID30000、build UID30001〜30004。storeはroot:nixbld・1775、管理領域は利用者書込禁止。既存内容・旧schema・途中失敗は拒否する。公式installer全体や既存storeへの再帰chownは使わない。

### 2. daemon監督とboot-bound request/ack

新規 `infra/devbox/nix/runtime.py` と起動テストを追加し、`entrypoint.sh`、`supervisor/supervisor.py` に統合する。

supervisorだけがdaemonをspawnする。準備完了後にboot-local socket領域をbindし、固定binary・IPC・PID開始識別・設定を確認する。世代/boot/request ID、replay、期限、二重spawn、異常終了を扱い、失敗から自動再起動しない。

lock順序はcontroller lock → admission → 短時間のcontrol lock。bootstrapと起動dispatcherはshared admissionを使用し、ack待ちにcontrol lockを保持しない。daemon応答30秒、controller待ち45秒。

### 3. sandbox gateと非trusted利用者のHM

`bootstrap.sh`、`bootstrap_state.py`、`orca/serve.sh`、`modules/home/hosts/devbox.nix` を変更する。固定Nix clientからdaemonを利用し、sandbox実build → HM build → VM内activate → profile確認 → 新schemaのhome-readyの順とする。

共通 `infra/devbox/nix/sandbox-probe.nix` とVM側probeを整える。外側で読める公開markerを内側から隠し、cacheを使わないbuildと専用build UIDを確認する。クライアントのsandbox無効化要求や直接store書込みを拒否できることを検証する。rootは利用者profileやcheckout内の実行コードを直接実行しない。

### 4. Nixを含む停止境界

`idle-controller/manual_stop.py`、`safety.py`、runtime/supervisorを統合し、`test_nix_stop.py`、起動/停止/fence回帰を追加する。

停止順は受付閉鎖 → 検証済みhookによる受付遮断/保存/Orca終了 → Nix接続・待機・worker確認 → daemon正常終了・残存確認 → backup → 最終承認 → Tailscale終了・sync。

中間Nix stop request/ackは最終stop-approvedなしで処理できる独立経路とする。待機中controllerはadmission/control lockを保持せず、supervisorはstop.lockを取得しない。worker残存、古いPID、観測不明、timeout、backup失敗はfenceを維持して停止拒否する。

未確認のdrain APIを創作しない。固定版sourceと結合試験で閉じた観測範囲を実証できなければ、Nix drainはunknownのままにする。Orca版固有hook未実証時の停止拒否・自動停止無効を維持する。

### 5. VM harness・配布・復旧手順

新規 `tools/devbox/vm/nix-multi-user-provision.sh` はproduction helperを共用する。`bundle.py`、`check-nix.py`、VM tests、`state-paths.json`、`machine.example.json`、関連README/validation docsを更新する。必要ファイルは明示allowlistで配布し、HOME・認証・.pi・.context・実stateは含めない。

新VM候補名は `db-mu1`。作成直前に同名不在と旧VM停止を再確認する。既存のLima隔離設定・ホスト共有なし・認証持込みなしを継承する。追加VMの増殖や資源の自動拡張はしない。

災害backupではNix storeを除外し固定seed/lockから再構築する。復元metaを現行readyの根拠にせず、danglingな利用者profileを保全して再作成する。入力取得不能なら復旧未完了。通常stop/startのVolume保持と、同一Tailscale identityの同時稼働禁止を維持する。

## 検証と完了条件

1. 変更ごとに関連Python unit testsを先に追加・実行し、起動/停止/fence/bundleの回帰を確認する。無関係な全suiteを毎回実行しない。
2. 対象Python診断、shellcheck、Nix整形、`git diff --check`を実行する。
3. 統合時に既存 `tools/devbox/check-nix.py` の3ホスト評価・Pi比較・native testsを再利用する。既存ホストへのactivateはしない。
4. 新規VMでroot daemon/sandbox/build UID/設定制限/固定HMの実build・VM内activate・profileを確認する。public pinned inputの取得は許可範囲。秘密・Fly token・実Tailscale identityを持ち込まない。
5. bootstrap中、build中、待機job、既存接続、別SID worker、daemon異常、同時stop、途中失敗後bootの拒否を結合試験する。証明不足なら通常運用の受入は未完了とする。
6. 可能な範囲で新OCIの非root/network-none/read-only CLI smokeを再検証する。Docker/seccomp/Fly kernel差は記録し、保護解除で代替しない。未実測digestやverified=trueを記入しない。
7. 固定seedと失敗記録を保全し、関連検証を終えた新VMは通常の停止操作で停止する。作業が残る場合は停止を強制せず、未完了として状況を報告する。
8. flake.lock・既存stage・Pi/Darwin/WSLの変更保全を比較確認し、独立レビューの指摘を修正する。完了レポートには実装済み・実測済み・未実証を分けて記載する。

## 許可しない操作・停止条件

- Flyリソース作成/課金/start、公開、実認証、秘密の閲覧や持込み、commit/push、既存VM/storeの削除・再利用は行わない。
- security guard、sandbox、AppArmor、seccomp等の保護を無効化しない。
- 固定入力、資源上限、権限/停止モデルの変更が必要になったら停止して判断を求める。
- 新規VMの成功をFly本番の受入成功と同一視しない。
