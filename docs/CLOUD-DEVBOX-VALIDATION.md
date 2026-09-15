# Cloud Devbox ローカル検証記録

実施日: 2026-09-05。環境: aarch64-darwin、Nix 2.35.1、Python 3.11.13、Node 22.23.2。
対象: `myksyut/dotfiles`のCloud Devbox追加差分。ローカルx86_64 VMでのOCI/CLI smokeを含む。Fly実機受入やPhase 1合格ではない。

## 結果

| 検証 | 結果 |
| --- | --- |
| Python unittest (`infra/devbox/tests`) | 前回74件に加え、今回Nix probe/失敗保持/bootstrap設定の**関連8件PASS**。全82件は下記Nix native checkで確認 |
| 既存`modules/home/merge-pi-settings.test.sh` | **PASS**。既存merge挙動の回帰なし |
| launcher `npm test` | **14件PASS**。ローカル生成署名鍵、issuer/aud/sub/期限/nbf/署名拒否、GET/CSRF/固定対象/同時start/rate/Fly障害 |
| devbox Home Manager activationPackage evaluation | **PASS** |
| 既存Mac system evaluation | **PASS**（開始時のMacホスト追加を保持） |
| 既存WSL toplevel evaluation | **PASS** |
| Darwin管理CLI package/app | **build・`--help`成功**。Nix固定Python/flyctl 0.4.79を使用。実status/startは実行せず |
| Pi routing/catalog/keybindings比較 | **3ホストでSHA-256一致**。remote-controlのenableはdevbox=false、Mac/WSL=true |
| Nix native `checks.aarch64-darwin.devbox-tests` build | **82件PASS**。Nix gateの8件を追加。activationは実行せず |
| ローカルVM | **起動成功・検証後に正常停止済み**。Lima 2.2.0 full/QEMU 11.0.3、Ubuntu 24.04 x86_64、4 vCPU/8GiB/80GiB |
| VM内Docker | **PASS**。Docker 29.1.3/Buildx 0.30.1、local socketのみ |
| OCI build / CLI smoke | **前回imageでPASS**。ALSA不足修正後にexit0。今回のsandbox-fallback/bootstrap変更後のOCI再buildは未実施 |
| smokeの制約 | **実inspectで確認**。UID10001、read-only、network none、CapDrop ALL、no-new-privileges、bind mountなし、exit0 |
| VM共有・forward | host HOME/SSH agentなし。修正後のguest loopback listenerは20秒間hostへ自動forwardされず |
| 一般user namespace probe | **DENIED**。Ubuntu VMのAppArmor設定1、uid_map書込拒否。Nix自体のsandbox成否ではない。保護を無効化せず |
| 固定配布物 | Orca 1.4.197/Nix 2.35.2/Tailscale 1.102.3を取得し公式SHA-256・サイズと一致。Ubuntu amd64 manifest/configのhashとarchitectureも確認 |
| Nix 2.35.2 single-user install | **FAIL**。Docker外のVM、UID10001、sandbox必須/fallback禁止で初期profile作成がnamespace不足によりexit1。保護は変更せず |
| x86_64-linux activationPackage build | **未到達**。Nix install失敗で停止。Home Manager build/activation未実施 |
| shellcheck 0.11.0 | **PASS**。既存対象に加えVM lab wrapper/build-smoke runnerも確認 |
| nixfmt `--check` / statix | **PASS**。既存Nix 4ファイルに加えVM host-tools.nixも確認 |
| LSP primary checks | 対象Nix/Python/Workerにblocking errorなし |
| `git diff --check` | **PASS** |
| flake.lock SHA-256 | 開始時と一致。`3187930aede623520400776a30820a6781ef63a106747378d6f3841c7f7f6216` |

Nix評価時、既存の`programs.zsh.initExtraBeforeCompInit`/`initExtra`についてdeprecation warningが出る。今回の移行で既存シェルの大規模整理を行わないため維持する。

## 再実行

```bash
cd ~/.config/nix-config
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/devbox/tests -v
bash modules/home/merge-pi-settings.test.sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/devbox/check-nix.py
(cd infra/devbox-launcher && npm ci --ignore-scripts && npm test)
nixfmt --check flake.nix modules/home/pi.nix modules/home/hosts/devbox.nix pkgs/devbox/default.nix
statix check flake.nix
statix check modules/home/pi.nix
statix check modules/home/hosts/devbox.nix
statix check pkgs/devbox/default.nix
git diff --check
```

`check-nix.py`は必要コードだけのallowlist snapshotで評価するため、既存のstageを操作せず未追跡の追加コードも検証できる。`.pi/.context/.env/認証/artifacts/node_modules`はsnapshotへ含めない。snapshotは検査用にOSのtempディレクトリへ残す。全dotfilesのcheckoutをむやみに`path:.`で取り込まない。Linux実buildはx86_64-linux上で同scriptの`--build-home`を付けて実施する。

最終確認時のdevbox activation derivation:
`/nix/store/2ryn53mp7rygsvby0gfs5mdbqagfkg1f-home-manager-generation.drv`

最終native test derivation:
`/nix/store/2dz6yf4p8s1s4xyvywf47zwjzm0yz8bb-devbox-offline-tests.drv`

Darwin管理CLI build済みパス（この検証環境）:
`/nix/store/brpw6djinra9gpnbgpl98vbizd9qqbgd-devbox/bin/devbox`

## 遅延レビュー対応

REVIEWERは途中版を読んでいたため、指摘を最終版と照合した。実在した競合は修正し、未検証のOrca APIは追加していない。

| 指摘 | 対応 |
| --- | --- |
| stop-hookがなくPhase 1未達 | 合意。**Gate 0実装・Phase 1未合格**と明示。版固有hookは実証するまで提供しない |
| runと停止のrace | root所有の共有admission inodeをflock。登録〜spawnを共有lock、drain遷移と最終処理を排他lock。closed状態はhandoff後も維持 |
| registry readerが非同期 | writerと同じregistry.lockを使用。型/所有権/permissions/regular file/hardlink/symlinkも確認 |
| 子処理releaseが確認フラグのみ | child開始識別/PGID/SIDを記録・検査。旧boot/再利用/識別欠落/既知メンバー残存は拒否。setsidで範囲外へ逃げた子の証明は未解決で人の確認も残す |
| 終了最終処理失敗→restart | sync/metadata失敗をcatchしてsupervisor生存、fence維持。永続shutdown-stateで次bootも要確認ならOrca自動起動禁止 |
| Mac用CLIとflyctlの再現性 | Darwin package/appを追加、Python/flyctlをNix絶対パスへ固定。既存home profileは変更しない |
| bootstrap手順不足 | レビュー後に作成済みの運用ガイドへfresh checkout、Tailscale認証、開始失敗/復旧のoperator手順を記載 |
| apt依存がmutable | 完全再現buildとは称さず、OCI digestと`/opt/artifacts/dpkg-packages.txt`を記録。snapshot固定は今後の選択肢 |
| useraddとHOME symlink衝突 | HOMEは既にbind mountへ修正済み。さらに`--no-create-home`を明示 |

REVIEWER対応時は45件を確認。続くSCOUT遅延レビューで以下を追加し、最終60件・Nix評価/native tests build・Darwin package build/help・shellcheckを再確認した。起動ページとNix moduleロジックは今回未変更のため、前回14件とnixfmt/statixの結果を維持し、無関係な再実行はしていない。

| SCOUT指摘 | 最終対応 |
| --- | --- |
| HOME symlink破損 | 途中版への指摘。bind mountとno-create-homeへ既に変更済み |
| Tailscale ipだけで起動、100.*判定 | `status --json`のRunning/Online/TUN、期待Node ID、単一canonical IPv4(100.64/10)、Self/top-level一致、tailscale0を検査。最終readyはunknown |
| bootstrapパスのtraversal/symlink | 実パスHOME制限、lexical ..とsymlink拒否、directory/flakeファイルのtype/owner/permissionsを検査 |
| bootstrap失敗情報不足 | root-only構造化状態started/failed/home-ready、stage/exit code/時刻/bootを記録。失敗を自動retryせずoperator復旧 |
| tailscale/meta所有権 | root:root・700の通常directoryを必須にして明示的に起動拒否 |
| root service子が未確認 | serviceを専用groupで起動し、停止後は既知groupのroot子も検査。未検証の強制group killは追加しない |
| management configの信頼 | regular file、本人owner、600、単一link、安全な親directoryを必須。symlink/FIFO/異常schemaを拒否 |
| registryをroot所有/暗号化せよ | registryを同一UIDに対するsecurity sandboxとは扱わない。root所有fence/制御状態と独立した停止前process検査を維持し、Orca/site hookの網羅性は実機受入必須 |
| startページのreadyがunknown | 意図した設計。WorkerからTailscaleへの到達確認を捏造しない |

Tailscale状態のfixtureは実node認証ではない。Node ID pinの手動照合、採用固定版JSON、grants、private接続、groupから離脱するdaemonの観測範囲は未検証の受入項目として残す。

## 配布物固定・Linux検証準備（VM作成前の記録）

以下はVM作成前の段階。後続の承認・実行結果は次節を参照。

- `infra/devbox/artifacts.lock.json`へ公式固定URL・hash・サイズ・出典を記録。取得物はGit ignore内に保存し、バイナリ実行やinstaller実行はしていない。
- `tools/devbox/check-artifacts.py`を追加。offline検証とdownload/buildコマンドの表示のみ。default local builderと空client configを要求し、既存認証/remote contextを持ち込まない。
- Dockerfileへamd64、Orca版、CLIリンクの検証を追加。OCI build自体は未実施。
- reviewerが指摘したdownload先symlinkとcurlの既存file処理を修正。pre-print/runtime両方のdirectory拒否と既存file skipをテストし、追レビューはAPPROVED。
- 今回は関連11件、Nix native全71件、3ホスト評価/Pi比較、配布物実hash、LSP、diffを確認。CLI packageやWorker等の無関係なbuild/testsは再実行していない。flake.lockは一致、既存stageは操作していない。
- Linux/VMがないため実buildへは進めない。[検証先の選択・準備手順](CLOUD-DEVBOX-LINUX-VALIDATION.md)を追加。VM方式/install/資源割当は未決定で、勝手に導入しない。

## 承認後のローカルVM検証

- 専用LIMA_HOME `~/.local/share/devbox-lima`に`db-gate0`を作成。既存Mac/WSL、既存~/.lima/認証を共有・switchしていない。
- 初回はNix limaにx86_64 guest agentが不足。公式の`withAdditionalGuestAgents=true`で解決。Limaの通常port rule補完でもloopback forwardが残ることが判明し、`guestIPMustBeZero=false`を明示して正常再起動・否定試験した。
- Docker group追加前のSSH接続は`--reconnect`で更新。socket chmodや権限回避を行わず、Docker probeが成功した。
- 初回OCI buildは成功したが、Orca CLIが`libasound.so.2`不足でexit127。`ldd`でも不足を確認し、Ubuntuの`libasound2t64`をDockerfileへ追加。最終dpkg inventoryも更新する。
- 失敗した`oci-gate0`を保全し、修正した別directory `oci-gate1`でbuild/smokeを実施。Tailscale 1.102.3、Orca 1.4.197のversion/help、`--pairing-address`を確認。実行時制約をdocker inspectで再確認し、job.exit=0。
- 同じartifactの`verified_cli`はこのCLI smokeだけを指す。server readiness、Nix activation、運用承認は意味しない。
- 成功時のDockerローカルimage handle: `sha256:5b9c06ec561f6b96d6436c9956e062e4d80327281b61d1b5af05f93b23c52d9d`。registryへのpush/deployはしていない。
- 実行したDockerfile SHA-256: `86194913b43c8560fd3d676b1f0c11cad18c4e3b64afe450bbb4d38861b12258`。runner: `99f210410563fae9cc80fee486a1e4aeea0a9d7858d7dd9c565ed377baaa317c`。hostとVMの一致を確認。
- ローカル証跡はGit ignore内の`infra/devbox/build-evidence/20260905-{failed,passed}/`に保全。VMの鍵/stateはコピーしていない。buildログの`InvalidDefaultArgInFrom`警告は、Ubuntu digestを必須build argにしてdefaultを持たせない設計による。
- running containerがないことを確認後、22:48 JSTにVMを正常停止。disk/image/container/ログは削除していない。

後続の[Nix実検証](CLOUD-DEVBOX-NIX-VALIDATION.md)では、sandbox必須のsingle-user installが初期profile作成で失敗した。fallbackの既定値trueも判明し、Dockerfile/bootstrapでfalseを明示した。次はmulti-user構成の設計・比較を推奨。Ubuntu VMとFly kernelを同一視せず、保護を無効化して合格扱いにしない。検証後23:34 JSTにVMを再び正常停止。

再現・再開・停止は[`tools/devbox/vm/README.md`](../tools/devbox/vm/README.md)。

## 仕様照合とreviewで修正した点

- Orca公式docsでRemote Serverがサーバー上のworktrees/terminals/agent sessionsを所有すること、serveがforeground、pairing-addressが待受制限ではないことを確認。
- Linux CLIは`orca-ide`。公式packaging定義に加え、固定1.4.197のdeb内でもPackage/Version/Architecture/Xvfb依存/CLI wrapper/postinstリンク定義を確認。Docker内のinstallとCLI version/helpも確認済み。server本体は未検証。
- CLI referenceにhost selectorとterminal `executionHostId`/`hostScope`の説明があるが、client不在・保存完了・drainを証明するcontractは確認できず。adapterからの自動停止許可は実装しない。
- root supervisorが必ずPID 1という仮定を除去。Fly init下の主プロセスとして終了コードを渡す設計へ修正。
- Nix store親symlinkを避けてbind mountへ修正。rootfs保持時のstale `/run`をtmpfsで分離。
- rootのstop-hookは固定PATH/最小環境、rootのbackupはUbuntu側Resticを使用。Orca childへservice環境を丸ごと引き継がない。
- private firewallによる管理console閉鎖を避けるため、必要時だけ管理端末の確認済み6PN IPv6 /128へFly init SSHを許可する手順/設定を追加。public/任意tailnetには開けない。
- standalone generic LinuxのGPU統合をheadless hostだけ無効化。
- bootstrapのrootによるuser-owned Git checkout参照をrunuserへ修正。
- supervisorは古い承認/誤boot/Orca生存/新しい子処理/異常なTailscale終了で正常stopしない。

## 実行していないこと・未検証

- flyctlの実Machine API操作/認証参照は未実施。ローカルOCI/CLI smokeは成功したが、Fly上の動作は未検証。
- Fly Machine/Volume/registry push/deploy/課金start、Tailscale/Orca/AIの実認証登録、Worker公開は一切未実施。
- Nix activation、既存Mac/WSL switch、devbox entrypointのmount/firewall/stop-hook/Restic helperは実行していない。
- Nix単一ユーザーsandboxは当該VMで失敗。Orca server起動、Fly TUN/nft/管理console、Orca/Pi実hooks、Mac間引継ぎ、session/grants復元、preview/Compose/Mobile、暗号化backup restore、実請求は未検証。
- 自動停止actuatorは未実装。手動stop-hookの具体的なOrca保存/終了/受付遮断も、対象版で実証できるまで未提供。既定stopは拒否する。
- launcher testsはDO/Fly transportをmockしており、Cloudflare Access実policy・JWT転送・DO実環境の排他/課金を検証したものではない。
- Pi共存テストのOrca keysは管理外設定を模したfixture。実際のOrca hook schemaの保証ではない。mergeとOrcaの同時writeも未保証で、停止/idle時に適用する。

A01〜A24の実機手順・合格条件と次の承認点は[CLOUD-DEVBOX.md](CLOUD-DEVBOX.md)に記載。テストrepoでGate 0を通す前に重要データを移さない。
