# Cloud Devbox multi-user Nix — 検証記録

2026-09-06。承認済み実装計画のローカル実証。**日常利用・Fly受入は未合格**。実認証・公開・課金・既存Mac/WSL activation・commit/pushは行っていない。

## 追加検証 2026-09-06 16:13 JST

PiセッションからCodexへ継続し、ユーザーの再開承認後に同じdb-mu1で検証を完了した。以下の稼働中/未到達記録は再開前の履歴として保持する。

- HM buildはexit0。初回activationでZenoのコピー先親ディレクトリがなく失敗したため、`modules/home/default.nix` の `copyZenoZsh` に `run mkdir -p "$HOME/.local/share"` を1行追加。再build・VM内activationはexit0。
- 確認スクリプトのaggregate user profileとHM home-pathの誤比較を修正し、HM世代リンクがbuild結果と一致することを確認。Nix2.34.8、Zsh5.9.2、Pi0.84.1のversionコマンドはexit0。daemonの固定seedは従来の2.35.2のまま。
- 新multi-user OCI buildとnetwork-none/read-only/UID10001のCLI smokeはexit0。Orca1.4.197のversion/serve help、Tailscale1.102.3のversionを確認。ローカルimage ID: `sha256:557d2ecb5aa0840a2cbd31fa4f904e7554098807b69e7ca7162288aff1aa8dc1`。
- native結果はVMの `/var/lib/devbox-native-recovery-20260906-v2/verified-result.json`、OCI結果は `/home/devboxlab/oci-multi1/job.exit` と `image-id.txt`。旧hm-build timeoutとv1/v2の途中記録は保持した。
- 残存build/CLIがないことを確認後、16:12 JSTにdb-mu1を通常停止。旧db-gate0も停止のまま。ディスク・ログを保持した。
- flake.lock/既存stageのSHAは下記baselineと一致、git diff --check成功。今回の1行修正はVMで直接検証し、無関係な追加テストや全suite再実行はしていない。

今回の成功は手動での検証VM内HM/CLIとOCI smoke。production home-readyと元のfailed記録は変更していない。Orca実接続、Fly実機、通常運用のNix/Orca drainと実backup/restoreは未実証で、`oci_digest`未設定・`verified=false`を維持する。

## 実装と静的検証

- 固定Nix 2.35.2 seedの検証/限定初期化、root daemon監督、boot/世代/request-bound制御、非trusted UID10001、専用UID30001〜30004を実装。
- sandbox実build/rebuild・外側UID観測 → HM build → VM内activation → profile → schema2 home-readyの順を実装。失敗から自動再試行せず、timeoutでもclient/buildを強制killしない。
- root Pythonは`-I`、実行元はroot管理の`/opt/devbox`。Nix drainは未実証のためunknown、通常停止は拒否。`restart.policy=no`。
- `python3 -m unittest discover -s infra/devbox/tests`: **149 tests成功**。
- `tools/devbox/check-nix.py`: **3ホスト評価・Pi routing/catalog/keybindings比較・Nix内149 tests成功**。既存zshオプションのdeprecation warningあり。
- shellcheck、対象Python LSP、`git diff --check`成功。
- 独立レビューで指摘されたbundleのhash/archive競合、APT前提を修正。不要なimage内seed二重展開を廃止。再レビューはAPPROVED、対象範囲の新規指摘なし。
- Linux VMでも**149 tests成功**。初回はservice単体fixtureが実機のroot-private bootstrapを参照して7件失敗したため、fixture内の`BOOTSTRAP`を仮想pathへ隔離。別の`/home/devboxlab/unit-v2`へテストだけ反映して再実行した。稼働中のproduction runtime・元の入力・storeは変更していない。
- Docker lintのAPT版固定/リスト容量は既知の制約として残す。APT依存はdpkg inventoryで記録し、完全な再現imageとは称さない。削除操作は追加していない。
- 統合試験で見つけたumask依存のfixtureを修正。JSON深さ拒否をPython実装の再帰制限に依存させず明示32階層に制限。

保全確認:

| 対象 | SHA-256 |
| --- | --- |
| flake.lock | `3187930aede623520400776a30820a6781ef63a106747378d6f3841c7f7f6216` |
| 既存stageのbinary diff | `ea15a09a55278bbc8ea48076235f61be0df3fc3f475182b559bc78765bca0b2b` |

## 新規VMの範囲

`db-mu1` / Ubuntu 24.04 amd64、4 vCPU・8GiB・80GiB、build 1job/2cores。旧`db-gate0`は停止したまま。host mount/agent/key/proxy/実HOME/認証/既存storeは持ち込まない。Lima管理鍵は専用state内だけに保持する。

`bundle.py --native`は固定runtime・seed・allowlisted flake source・lab helperを転送する。root system provisionへmanifest SHAを明示埋込みし、guest利用者が変更できる入力とは独立したanchorとする。同一FDから取得した保存済みbytesをhashとtarの両方に使用。guestはprivate root stagingへcopy+hash後にだけ配置/実行する。

- 入力manifest SHA-256: `3c6d06b21d42ac5f90d36e621cdd3b1de25e9c1aabd814f80933d40f6e4d917e`。
- `/var/lib/devbox-multi-data` → `/data` → `/nix`へVM disk上のbind mount。
- 本番と同じ`NixRuntime`をlab driverから監督。systemd別実装・通常起動時installer・自動repairを追加しない。
- 14:08時点: one-shot setup終了、runtimeが`NIX_AVAILABLE`を報告。世代`7e297e91dfcded51681668a40677f250f1b636decd63653761d3ad416e26eef6`。
- **15:10:27: bootstrapは`phase=failed / exit=1 / bootstrap_stage=hm-build`。** 3600秒のcommand deadlineで終了。`Bootstrap command timed out; process may remain, no retry`を記録した。
- sandbox gateを通過してHM buildへ到達したが、HM build完了・activation・profile/home-readyは未到達。TerraformのGo build/testコンパイルが時間を要した。失敗を保護解除で隠していない。
- 15:11時点: UID10001のNix client PID2063、UID30001のGo/compilerが継続中。メモリ/ディスクの不足ではなく、disk約16GiB使用/62GiB空き。**VMは稼働を保全。強制停止・再bootstrap・追加VM作成はしていない。** 再開方針の判断が必要。
- 新OCI用payloadは`/home/devboxlab/oci-multi1`へ転送済みで3配布物のoffline hash/size検証に成功。新layoutにCLI smokeを修正済みだが、native jobとの同時buildを避け実build/smokeは未実行。

証跡はVMの`/var/lib/devbox-nix-multi-v1/`と`/data/meta/`。setup/statusは認証なしfixture用の限定公開診断、production bootstrap/daemon logsはroot-onlyのまま。新VM上でOrca/Tailscaleの実サービス・認証を開始しない。

## 未実証・停止条件

- HM buildはcontroller timeoutにより受入未完了。実client設定拒否・store直接書込拒否も未実測。稼働中buildを保全したまま、長時間buildと失敗段階からの再開を別途計画/承認する必要がある。
- queued request/既存接続/離脱workerを閉じた範囲で観測できるNix drain契約、Orca版固有save/drain hook、実backup/restoreは未実証。
- 新multi-user OCI build/smoke、Fly kernel/TUN/firewall/到達性、Orca実接続は未実証。旧imageの成功を流用せず`oci_digest`未設定・`verified=false`を維持する。
- 失敗storeは保全し、同じone-shotを再実行しない。VM増設・資源拡張・保護解除・実認証・新しい修復方針には別の判断/承認が必要。
