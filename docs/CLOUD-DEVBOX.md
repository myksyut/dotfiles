# Cloud Devbox — Orca Remote Server / Fly Machines

## 現在の運用状況（2026-09-06 更新）

Fly `myksyut-devbox`（東京、共有4 CPU・8GB RAM・50GB Volume）を構築し、Tailscale Serve経由のOrcaブラウザ接続とHome Manager環境の起動を確認済み。Macを中継せず、処理はFly上で動く。

自動停止は30秒ごとに観測し、**30分連続で接続も作業もない場合だけ停止**する実装を追加した。ブラウザ／モバイルの接続、開いたターミナル・Orcaブラウザタブ、Pi等の実行中コマンド、Orca予約タスク、`devbox hold`／登録作業、Nixビルドのいずれかがあれば停止しない。観測失敗時も停止せずアイドル時間をリセットする。終了前に接続受付を閉じて状態を再確認し、Orca・Nix・Tailscaleの順に終了して正常停止記録を保存する。

**自動停止を実機へ導入済み。** 初回切替での正常停止とNix再起動を確認した後、Flyの`config.files`へ修正済みコード4ファイル（32,287 bytes）を登録し、毎boot注入する構成にした。rootfsへの直接パッチはstop/startで消えることが判明したため、現構成では`config.files`の保持が必須。

実機でNix available・Orca起動・空のホスト判定を確認し、バックグラウンドの`sleep`実行中は停止しないことを実測した。1bootだけ待機を30秒へ縮めた動作試験では、2026-09-06 21:34:25 JSTにMachineが停止した。Flyの終了記録はexit code 0、OOMなし、外部の停止要求なしで、controller自身が正常終了して停止した。自動停止後に同じMachineを起動し、新bootで自動停止が有効・待機1800秒へ自動復帰したこと、Nix available・Orca running・Tailscale認証済み・空のホスト状態を確認した。HTTPS経由のOrca Webで「Orca Server / リモートサーバー / 接続済み」を実UIで確認し、検証用ブラウザは閉じて接続を解放した。オフライン検証は47件成功（新規18件、既存の停止保護22件とNix/supervisor7件）。

Orcaアプリが待機画面でも接続したままの場合や、ターミナルを開いたままの場合は停止しない。停止中はスマホのFly管理画面で既存MachineをStartし、Tailscaleを有効にしてOrcaへ戻る。Orcaへの接続による自動起動はない。OCIイメージの再作成と、未保存内容を含む完全な復元・backup/restoreの受入は未完了。

以下の実装状況と手順は初期構築時の記録を残している。Fly未作成・自動停止無効という記述は当時の状態であり、現在は上記更新を優先する。

## 初期実装時の状況と安全境界（履歴）

`cloud-devbox-plan-v3.md`を基準にした実装。**現在はGate 0の構築・検証用実装で、Phase 1（日常利用と安全な手動停止）は未合格。Flyインフラ未作成・Fly実機受入未実施であり、日常利用できる状態の実証はまだない。**

| 領域 | 状態 |
| --- | --- |
| standalone Home Manager / Nix | multi-user構成へ実装更新。3ホスト評価と149回帰テスト成功。Linux実測は[MULTI-USER-VALIDATION](CLOUD-DEVBOX-MULTI-USER-VALIDATION.md)参照 |
| 既存Mac/WSL/Pi | 既存switch・パッケージ・拡張・モデルルーティングを維持。devboxだけremote-control無効 |
| OCI / Fly | 旧imageでOCI build/CLI smoke成功。新multi-user imageの実build・server/Fly実機は未検証 |
| 状態adapter | 公式CLIのprivate診断収集。schema/host scope/clients/save/drainは未実証、常に停止禁止 |
| 自動停止 | **無効。実行経路自体を提供しない**。30分の純粋判定関数と異常系テストのみ |
| 手動停止 | root operator用の確認・停止プロトコル。**版固有の検証済みstop-hookがない限り拒否** |
| work protection | root所有の受付fenceとhold/runの永続登録。子PID開始識別・PGID/SIDを検査し、未知の範囲は停止禁止 |
| backup | quiesced後の暗号化Restic helperと復旧手順。保存先・鍵・restore試験は人が用意 |
| 起動ページ | optional Worker + Access JWT + Durable Object + offline tests。未デプロイ |

本作業ではMachine/Volume作成、deploy、有料builder、課金start、実token取得/登録、アカウント移行を実行していない。ソースのcommit/pushや既存Home Managerのactivationも実行していない。

開始時HEAD: `ce3fdbb05178ff552c7d9986f813c9509e3860a8`。
開始時`flake.lock` SHA-256: `3187930aede623520400776a30820a6781ef63a106747378d6f3841c7f7f6216`（変更しない）。
開始時に存在した`.envrc`、flakeのMacホストimport、Darwin設定/新ホスト、`.context/`、`.pi/`の変更は保全する。

## 計画からの設計判断

1. **`fly.toml`ではなく`infra/devbox/machine.example.json`を正本にした。** Machines APIに直接対応する作成bodyで1台と既存Volumeを指定し、`fly deploy`のサービス追加・自動複製・再作成を日常経路へ入れない。管理CLIは固定IDのstatus/startだけ。
2. **multi-user Nix**へ更新した。[旧single-user検証](CLOUD-DEVBOX-NIX-VALIDATION.md)の失敗を受け、固定2.35.2 seedから新規root所有storeを限定的に初期化する。開発UID/GID10001は非trusted、nixbld GID30000・UID30001〜30004は非login。rootだけtrustedで、sandbox必須・fallback禁止・1job/2cores。root管理コードは固定seed由来runtimeだけを実行し、利用者profile/checkoutはUID10001で実行する。既存user所有storeのchownによる信頼昇格はしない。設計は[MULTI-USER-PLAN](CLOUD-DEVBOX-MULTI-USER-PLAN.md)。
3. `/data/nix`と`/data/home`は**bind mount**。Nix storeの親をsymlinkにせず、bootstrap素材はイメージの`/opt/artifacts/nix.tar.xz`に保持し、`nix/provision.py`で検証してから展開・登録する。通常起動はinstall/build/git pull/updateしない。rootfsへの直接修正はstop/startで失われることを実機確認済み。永続コードはイメージまたはFlyの`config.files`へ反映する。`/run`のtmpfsで古いsocket/PID/stop requestを持ち越さない。
4. Home Managerのgeneric Linuxが提供するGPU統合はdevboxだけ無効。CLI、Playwright、Neovimは維持する。
5. **観測不明・drain不明をsafeとしない。** CLIの空JSONやdoneだけでは停止許可を作らない。稼働中Pi全体をラップせず標準agent pickerを使い、子処理監視の実証まではholdする。
6. `devbox run`はdetach/double-fork子の完了を汎用PID列挙だけで証明できないため、親終了後も`completed-unverified`を残す。releaseは同boot・子PID開始識別・PGID/SIDの既知メンバー不在を検査し、さらに人の確認を要求する。旧boot/識別欠落/親異常終了/PID再利用は通常releaseで解除しない。cgroupによる完全な範囲監視・自動解放は、委譲とOrca連携の実証後の別変更。
7. `devbox stop`は任意コマンドやFly stopをエージェントへ渡さない。root-onlyの版固有hookで受付遮断・保存・終了・backupが実証されるまでは拒否する。既知でないOrca drain/sleep/quit APIは実装しない。
8. VOICEVOXのMCP設定だけdevboxで外す。Plannotator等のPi拡張は残し、外部ブラウザ連携は受入対象とする。GUIを動かすために公開ポートを増やさない。
9. Orcaは通常worktreeの主管理UI。devboxのgwq copy/setup自動処理とtmux worktree作成導線だけ止める。Mac/WSLの既存導線は変更しない。
10. supervisorはOCI entrypointから起動する主プロセスであり、Fly init下で必ずPID 1になるという仮定を置かない。private firewallが管理consoleも遮断しないよう、必要なら管理端末の確認済み6PN IPv6 `/128`だけFly init SSH(22)の復旧用例外にする。Tailscale側/インターネットにはSSHを公開しない。
11. 配布物の最新版やchecksumを推測しない。Ubuntu digest、公式Nix/Orca/TailscaleアーカイブとSHA-256を人が確認して与えるビルドゲートにした。apt依存はビルド時解決なので完全な再現ビルドとは称さず、完成OCI digestとビルド時自動記録`/opt/artifacts/dpkg-packages.txt`を保存する。
12. `run/hold/registry`とcontroller/supervisorがroot所有`/run/devbox-admission`の同じinodeをflockする。drain前に永続復旧意図を書き、閉鎖状態を記録する。最終処理失敗でも自動再開しない。ただしこのfenceは協調するCLI用であり、Orca/直接CLI/scheduler/新接続の遮断は依然としてsite hookの実証が必要。

## ファイルと責任分界

- `flake.nix`: `homeConfigurations."miyakishota@devbox"`、x86_64-linux専用`devbox-build`/`devbox-switch`、`checks.*.devbox-tests`、`checks.x86_64-linux.devbox-home`。
- `modules/home/hosts/devbox.nix`: HOME、headless差分、`~/.local/bin/devbox`。
- `pkgs/devbox`: Darwin向け`packages.aarch64-darwin.devbox`と`apps.aarch64-darwin.devbox`。Python/flyctlをNixの絶対パスへ固定。既存Mac/WSLのswitchやprofileを変更せず`nix run .#devbox`で利用できる。
- `modules/home/pi.nix`: `dotfiles.pi.remoteControl.{enable,bindAddress,advertisedBaseUrl}`。既存Mac/WSLの初期値は維持する。
- `merge-pi-settings.sh`: Nix所有のpackage/default起動キーだけ更新。Orcaの管理外package/extensions/hooks等は保持。devboxだけ既存の管理対象remote-control packageを取り除く。古い認証/configや実行中daemonを勝手に消さない（持ち込み時は人が確認）。
- `.pi/agent/settings.json`: writable、原子的merge。Orcaがこのファイルを書き込んでいる最中にNixを再適用しない。mergeは同時writerとの排他を保証しない。
- `.pi/agents/models.json`等の既存Nix-owned routing/keybindings: Orca側から置き換えない。Orcaが変更する必要のあるキーとの衝突が実証されたら限定的に分離する。
- `infra/devbox/`: private server/状態/停止定義。`infra/devbox-launcher/`: optional管理面。Fly tokenは後者または管理Macだけ。

## 1. ローカル検証（課金なし）

追加ファイルが未追跡のままではGit flakeの評価に含まれない。既存のstageを巻き戻さず、レビュー後に必要な追加ファイルを個別にstage/commitするか、**必要なコードだけをallowlistコピーした一時source**で検証する。HOME、`.pi/`、`.context/`、`.env*`、artifact、認証ファイルを`path:.`で丸ごとNix storeへ入れない。

```bash
cd ~/.config/nix-config
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/devbox/tests -v
# 未追跡の追加ファイルも含むallowlist snapshotで3ホスト評価/Pi比較/ネイティブtests build:
PYTHONDONTWRITEBYTECODE=1 python3 tools/devbox/check-nix.py
(cd infra/devbox-launcher && npm ci --ignore-scripts && npm test)

# 追加ファイルをGitに含めた、秘密情報のないcheckoutで実施:
nix eval --no-write-lock-file '.#homeConfigurations.miyakishota@devbox.activationPackage.drvPath'
nix build --no-write-lock-file --no-link '.#checks.aarch64-darwin.devbox-tests'
nix shell --inputs-from . nixpkgs#shellcheck --command shellcheck \
  infra/devbox/*.sh infra/devbox/orca/*.sh modules/home/merge-pi-settings.sh

# 実際のactivationPackage buildはx86_64-linux builderで:
PYTHONDONTWRITEBYTECODE=1 python3 tools/devbox/check-nix.py --build-home
```

Apple Silicon macOSではLinux activationPackageを評価できても直接buildできない。外部builderは今回設定しない。`nix flake update`やホストの`switch`は不要。検証結果は[CLOUD-DEVBOX-VALIDATION.md](CLOUD-DEVBOX-VALIDATION.md)を参照。

## 2. OCI imageの準備（人が確認、ローカルbuild）

固定入力は`infra/devbox/artifacts.lock.json`。2026-09-05にOrca 1.4.197/Nix 2.35.2/Tailscale 1.102.3の公式配布物を取得して公開SHA-256と照合し、Ubuntu 24.04 amd64 manifest digestを固定した。これはLinux動作確認や人の運用受入ではない。

1. [Linux検証準備](CLOUD-DEVBOX-LINUX-VALIDATION.md)に従って使い捨て検証先を選ぶ。既存Mac/WSLをswitchしない。
2. `infra/devbox/artifacts/{nix.tar.xz,orca.deb,tailscale.tgz}`へ固定配布物を置く。別環境向けdownloadコマンドは`check-artifacts.py --print-downloads`で表示できる。秘密情報を同じ場所へ置かない。
3. offline gateでサイズ/hashを再検証する。配布物とUbuntu digestを変更するときは公式出典を再照合し、lockをレビューする。`artifacts.example.json`のplaceholderをbuild入力にしない。
4. 空Docker client config・明示local Unix socket・default builderのbuildコマンドをレビューして人が実行する。課金/remote builder/pushは行わない。

```bash
python3 tools/devbox/check-artifacts.py
# ファイル照合後、固定hash/ORCA_VERSION込みのコマンドを表示するだけ:
python3 tools/devbox/check-artifacts.py --print-build \
  --docker-host unix:///var/run/docker.sock
```

固定deb内でもPackage=`orca-ide`、Version=`1.4.197`、Architecture=`amd64`、`xvfb`依存、CLI wrapperを確認済み。Dockerfileでもpackage/version/architecture/CLIリンクを検査する。ローカルx86_64 VMでOCI buildと非rootのCLI version/helpは成功済み。deb依存に不足していた`libasound2t64`を追加した。server起動やNix sandboxは未検証。

実イメージで`orca-ide --version`、`serve --help`を非rootで確認し、正しい絶対パスをMachine envの`ORCA_CLI`に反映する。同梱CLIのファイル配置が例と違えばそこで修正し、GNOME Orcaへのfallbackを作らない。`--no-sandbox`の追加で回避しない。OCI digest、Orca版、Nix版、Tailscale版、`dpkg-query -W`を運用記録へ残す。

## 3. Fly作成（別途明示承認が必要・本作業では未実行）

作成直前にnrt在庫/単価、4 shared vCPU/8GB、50GB Volume、rootfs/snapshot/通信、バックアップとTailscale業務利用条件を確認する。50GBや月$25は承認済み予算ではない。停止中もVolume等は課金される。予算アラートはhard capでも強制停止装置でもない。

承認後、管理Macで次の順に**人が**実行する。

1. 固定アプリを作成し、local build済みOCIをregistryへpush。アプリ名・image digestを記録。
2. nrtにVolumeを1本だけ作成し、IDを記録。例: `flyctl volumes create devbox_data --app "$APP" --region nrt --size 50`（課金）。
3. `machine.example.json`を`machine.local.json`へコピーし、image digest・Volume ID・確認済みCLIを記入。最初は`DEVBOX_MODE=maintenance`。Servicesは空配列のまま。
4. 対話root consoleが必要なら、Fly WireGuard管理端末の実際の6PN送信元IPv6を確認し、`config.env.DEVBOX_ADMIN_IPV6`へその単一アドレスを追加する（鍵は記録しない）。`fdaa::/16`内のIPv6だけ受け付け、TCP22だけ許可。未指定時はSSH閉鎖、Fly管理APIのexec経路等で復旧する。Machine作成後に必ず到達性/認証/拒否元を確認し、広いallow-allへ変更しない。
5. 管理端末の認証済みMachines APIクライアントから `POST https://api.machines.dev/v1/apps/<APP>/machines` にそのJSONを送る。**この作成POSTの自動retryはしない**。タイムアウト時はlistして二重作成を防ぐ。作成は起動/課金を伴い得る。
6. 戻ったMachine IDを`~/.config/devbox/manager.json`に記録（`tools/devbox/manager.example.json`参照）。ユーザー本人所有の通常ファイル・mode 600、親directoryは本人/root所有・group/world書込禁止とする。symlink/FIFO/hardlinkや別ownerは拒否する。既存設定を上書きせず、tokenを書かない。`flyctl machine list --app "$APP"`とVolume一覧で1台/1本を確認。public IP/service/SSH daemon/Proxy auto-startは追加しない。
7. consoleによる復旧経路を確保する。復旧アクセス例はインストールしたflyctlの`ssh console --help`で固定Machine選択を確認する。これは管理Macだけで使用する。

APIの`restart: {policy: on-failure, max_retries: 3}`と`auto_destroy: false`を再確認。supervisor主プロセスの検証済みexit 0でMachineがstoppedになることは実機で確認する。Orcaだけの終了やcontroller終了では停止完了とはしない。

## 4. 初回bootstrapとTailscale

entrypointはVolume必須・既存所有権を検査し、bind mountと`/run` tmpfs、nftablesを準備する。`/data/tailscale`と`/data/meta`は通常directory・root:root・700を必須とし、不一致をchmodで隠して進まず起動を拒否する。既存データを再帰chown/削除しない。TUN/nftが使えなければfail closed。userspace転送を追加する場合はOrcaへの到達性を別途設計/受入し、無断でポートを開けない。

maintenance modeはOrcaを起動しない。tailscaledとNix request処理を監督し、Nixは準備済み世代とboot-bound要求が揃った場合だけ起動する。以下の実認証は別途承認されたroot operator作業であり、ローカル検証では行わない。

```bash
# 同じ永続stateを使って手動認証。auth URLは秘密として扱う。
/opt/tailscale/tailscale --socket=/run/tailscale/tailscaled.sock up \
  --hostname=devbox --advertise-tags=tag:devbox --accept-dns=false
```

auth keyをイメージ/環境変数/起動scriptへ埋め込まない。非ephemeral identityを維持する。`tailscale-grants.example.json`の本人/タグ/6768許可をtailnet policyへ統合する。**既存allow-all ACL/grantは加算されるため、この例を追加するだけで制限済みとはならない。** Unauthorized端末から否定試験を行う。

認証後、管理者がTailscale管理画面の対象デバイスと`status --json`の`Self.ID`を照合し、期待するNode IDだけをroot所有600の`/data/meta/tailscale-node.json`へ`{"node_id":"確認済みID"}`として記録する。これは秘密鍵ではなく固定identityの照合値。初回出力を無条件に自動採用したり、毎boot書き換えたりしない。再登録でIDが変わったら明示的に再検証する。

Orca起動前に`BackendState=Running`、`Self.Online`、kernel TUN、`tailscale0`、固定Node ID、top-level/Selfの一致した単一IPv4（`100.64.0.0/10`）を検査する。欠落/失効/複数IP/不正IP/別identityでは起動しない。採用するTailscale固定版のJSONをGate 0で照合する。これはローカルの接続状態検査であり、grantsやクライアントからの実到達性の証明ではない。statusは`machine`、`network`、`orca`、`reason_code`、boot IDを分離し、最終`ready`はunknownのまま実機試験に委ねる。

secret-free dotfilesのレビュー済みcommitを`/home/miyakishota/src/dotfiles`へ開発ユーザーとして配置する。最初は公開repoのcloneでよいが、この実装差分を含むcommitを選ぶ。既存HOMEを丸ごと移さない。rootでユーザーrepo内コードを実行しない。

```bash
# root operator console: 固定seed初期化のみroot。sandbox/HM build/activationはUID10001。
/opt/devbox/bootstrap.sh /home/miyakishota/src/dotfiles
```

bootstrapはcheckoutを実パスへ解決し、HOME配下であること、`..`/symlinkの不在、directoryとflake.nix/flake.lockの型・owner・書込権限を検査する。固定seedの初期化とdaemon監督だけrootで行う。sandbox実buildとrebuildの専用UID観測後にHM build/activation/profile確認をUID10001で行い、実行中にrepoを変更しない。

開始マーカーと排他lockに加え、`/data/meta/bootstrap-state.json`へstarted/failed/home-ready、stage、終了コード、時刻、boot IDを記録する。コマンド本文や秘密情報は記録しない。通常例外はcontrollerがfailedを残し、SIGKILL等ではstartedが残る。schema2はmulti-user modeとNix世代を要求する。状態記録の失敗も未完了として扱い、二回目を自動実行しない。supervisorは通常のhome-readyマーカーと構造化成功記録の両方を要求する。**これはOrca readyではない。**

復旧はroot operatorがprivateログ、bootstrap-state/bootstrap-started、Nix store/DB/profile、activationの途中状態を確認し、元の記録を保全して対応する。既存Nixの上へinstallerを再実行して直そうとしない。失敗/途中状態から自動修復・再試行しない。修復または新規環境での再構築は別途レビュー・承認する。ready記録を手動で書き換えて成功扱いしない。

Gate 0の準備後、保存済み状態がない初回だけ`DEVBOX_MODE=serve`へ設定変更する。既存Machineの更新は課金/再起動を伴うため人が承認して実施。通常のstop/startではこの設定を変更しない。supervisorは永続identityと認証状態を確認してOrcaを1回だけ起動し、障害時に二重runtimeを作る再試行をしない。各serviceは専用process groupで起動し、通常停止では開発UID全体に加え既知service groupのroot子も残っていないことを確認する。未確認のgroup killは行わず、離脱したdaemon等の網羅性はsite hookの実機試験で確認する。

## 5. Orcaの初回設定・日常操作

Orcaのstdout/stderrは`/run/devbox/logs/orca.log`へroot-onlyで保存する。起動時のpairing URLをFly共有ログへ出さない。管理者が必要なリンクだけを端末へ渡し、チケット/このドキュメントへ貼らない。`/run`は再起動で消えるため、障害ログが必要なら秘密を除いた要約のみ別途記録する。

1. Mac A/B: Settings → Remote Orca Servers → Add Serverでペアリング。通常は保存済みServerを選ぶ。Advanced → Active Serverが対象Remote Serverであることを確認。
2. **Agent PermissionsをManualへ変更**。custom launch argumentsに確認省略引数が残っていないか各CLIで確認する。推測した設定JSONをNixから書かない。
3. agent pickerのPi/Claude/CodexはNixの実体へ合わせる。Orca自動setupとCLI自動更新で別版を重複installしない。サーバー/クライアントの互換版を固定。
4. GitHub/AIの認証はserver側で人が実施。Orca管理アカウントとPi auth storeは別。会社権限の持ち込みは会社の規則に従い、本番DB/広域cloud admin権限を置かない。
5. Orcaから開いたterminalで次を確認する（SSHでの成功だけでは不十分）。

```bash
whoami
printf '%s\n' "$HOME" "$SHELL"
command -v pi claude codex node python3 uv git nvim
pi --version
node --version
python3 --version
```

Piモデルルーティング/既存拡張が読み込まれ、Orca管理hookがNix適用後も残ることを確認する。Neovim/Orca未保存バッファ、Plannotatorやagent-piのbrowser opener、GUI通知、Playwrightは別途試験する。Plannotatorが`0.0.0.0`等へ独自serverを出しても公開ルールを追加せず、まずOrca remote browserで可否を調べる。reviewの主管理はOrcaのdiff。

管理Macでは追加ファイルを含むレビュー済みGit checkoutでNix appを使う。`flyctl`はflake.lockのNix store絶対パスに固定され、ambient PATHから探さない。実認証設定と課金起動の承認は別途必要。

```bash
nix run .#devbox -- --help      # ローカルhelpだけ。管理APIへ接続しない
nix run .#devbox -- status      # 固定Machine状態だけ。readyはunknown
nix run .#devbox -- start       # 課金操作。stoppedだけstart
nix run .#devbox -- open        # start後にOrcaを開く
```

ソースを直接使う場合は`python3 tools/devbox/devbox --flyctl /verified/absolute/path/to/flyctl status`のように、確認済み実行ファイルを明示する。環境変数やrepo configから実行パスを自動取得しない。Nix packageを人がPATHへインストールした場合は従来の`devbox status/start/open`表記でもよい。

`starting/stopping`は最大180秒待ち、未知/suspended等は拒否。タイムアウトでrestart/createしない。`open`は非公開deep linkを使わない。初期readyは人による接続試験で判定し、単なるPID/listenやFly startedをreadyと呼ばない。

devbox内:

```bash
devbox status
devbox hold 'Pi + agent-piの子処理が全終了するまで保持'  # 表示IDを控える
devbox run -- pnpm test
# 子/daemon/Dispatchが本当に全終了したことを確認してから:
devbox release <JOB_ID> --confirm-no-descendants
devbox release <HOLD_ID>
```

runの引数やsecretはregistryへ記録しない。boot ID、wrapper PID/start、child PID/start/PGID/SID、owner、時刻、状態を保持し、TTLや新bootで勝手に解放しない。wrapper crash/spawn失敗/子の識別取得前の終了でも阻止が残る。通常releaseは旧boot・PID再利用・既知子/セッションメンバー残存・識別欠落を拒否する。`setsid`で逃げた子までは保証できないため、人の`--confirm-no-descendants`は依然必要。

異常/旧bootレコードは別のoperator reconciliation扱い。人がroot consoleで全開発プロセス・履歴・保存・backupを確認し、registryの原本をprivateに保全してから該当IDだけを明示的に修正する。一般CLIにforce-releaseは追加しない。修正後もJSON schema、owner、600権限と親ディレクトリ所有権を維持する。通常releaseを通すためにboot IDやPIDを偽装しない。

registryは同じ`registry.lock`でwriter/stop readerを同期し、regular file、owner、permissions、hardlink/symlink、record型を検証する。受付fenceの欠落/旧boot/閉鎖中は新規run/hold/変更を拒否し、statusだけは読み取り可能。これはユーザー自身の誤停止防止であり、同一UIDの悪意あるエージェントを隔離するsecurity boundaryではない。root停止hookで独立に全仕事を確認する。

## 6. 手動停止を実用化するゲート

**初期の`devbox stop`は、検証済みhook未導入なら安全に拒否する。まだ「コマンドだけで安全に止められる」とは扱わない。**

管理者は対象Orca版の保存/終了/PTY挙動をテストrepoで確認し、root所有・group/world書込禁止の`/etc/devbox/stop-hook`を導入する。親ディレクトリも同じ条件。開発HOME/Nix storeからのhook symlinkは禁止。hookの全phaseは最大300秒、非zeroなら停止中止。

| phase引数 | 実証して実装する内容 |
| --- | --- |
| `validate` | Orca/client/CLI版、保存先inventory、以下の試験証拠が現在版と一致すること |
| `drain` | 新接続/既存接続からの新作業、CLI/local scheduler、Orca Automationsを含む新受付を遮断する。検証済みのnetwork fenceとruntime受付制御。既存の接続数取得を推測しない |
| `verify-quiescent` | 全client不在、working/waiting/Dispatch/agent-pi子/backup/Nix更新/未保存なしを人の保存確認と実測から再確認 |
| `save-and-stop` | DBを整合的に保存して停止、Orca/session/PTYを対象版で実証した手順で正常終了。未確認SIGTERMやkillを保存APIと同一視しない |
| `backup` | 保存後の`/opt/devbox/backup.sh --quiesced`等。成功記録必須。失敗で中止 |
| `verify-stopped` | 保存とbackup、Orca/PTY/サービスの終了、新しい仕事/holdなしをもう一度確認。orphan/zombie処理も確認 |
| `abort` | エラーと復旧手順をroot-onlyで記録し、受付のfenceを維持する。勝手にruntimeを再起動したり、受付を戻したりしない |

単なる`exit 0`のhook、JSONを手でsafeにしたhook、CPU/pgrepだけで合格するhookは不可。公式に存在しないdrain/sleep APIを創作しない。実装を決められない場合は自動停止も安全停止も未合格のまま、Gate 0用の使い捨てテストデータだけで運用する。

通常操作は、保存/全client切断/hold解放後、**管理用root consoleから**`/usr/bin/python3 -I /opt/devbox/idle-controller/manual_stop.py`。TTYと確認文字列が必要。Orca terminal内の非root`devbox stop`はroot権限を自動取得しない。

停止lock → validate＋Nix停止契約確認 → 永続復旧意図記録＋受付fence閉鎖 → drain/save/Orca終了hook → registry/開発UID・build UID再確認 → Nix中間stop request/ack（接続・待機・worker・固定daemon正常終了） → backup/verify-stopped → root-only最終承認 → supervisorが受付fenceを排他保持 → registry/プロセス/Nix停止再確認 → tailscaled正常終了 → 再確認 → sync/正常停止記録 → 完了状態 → exit 0。排他を解放しても閉鎖状態は次の正常bootまで維持する。最後に管理Macのstatusで`stopped`を確認する。

**現在のNix停止契約はunknown固定のため、validate後・停止作用前に拒否する。** 単なるプロセス不在やhook成功で上書きできない。契約実証後のdrain開始以降にhook/backup/sync/最終metadata書込が失敗した場合はVM稼働と閉鎖fenceを維持し、最終停止を自動retryしない。すでにOrcaやTailscaleが正常終了済みの場合がある。`/data/meta/shutdown-state.json`がdraining/needs-review/不正JSONなら、次回bootでもOrcaを自動起動せず受付を閉鎖する。正常stopのstopped状態だけが通常再開を許す。

復旧はroot operatorが保存・registry・停止済みサービス・backupを点検し、現在のshutdown-stateをprivateに保全する。安全な再開を承認した場合だけ、このファイルを日時付きの監査用名へ退避し、受付を直接書き換えず管理経路から明示的に再起動する。通常bootstrapを再実行して直そうとしない。自動rollback起動は行わない。意図しないFly/provider stopは緊急操作であり、通常経路には提供しない。停止による未保存/実行中タスク消失のリスクを人が引き受ける別承認が必要。

## 7. 自動停止の後続ゲート

`orca-state-adapter/observe.py --cli <absolute-cli> --output <new-private-directory>`をOrcaユーザーで実行すると、`status/worktree ps/terminal list/agent hooks status --json`を収集する。JSONにはprivate情報が含まれ得るため、共有せず必要なら手でredactする。hook JSONの実フィールドは決め打ちしていない。

`policy.py`は内部schemaの全flagがstrict boolean true、errors空、観測15秒以内、boot/runtime一致、連続1800秒、poll gap/時刻逆行なしだけを候補とする。しかし**実adapterはsafe flagを生成しないし、policyは停止を実行しない**。

A06/A08〜A14を実機で通し、host scope/client presence/save/drainの版別contract、cgroup等の子処理観測、新規仕事とのrace解消を実装・reviewした後にだけactuator追加を検討する。Orca hibernationとVM停止は別機能、待ち時間も別。前景worktreeが休止しない時は人が終了する。開きっぱなしclientは停止を妨げ得る。節約のために状態を偽装しない。

## 8. worktree移行

移行前に`git status`、`git worktree list --porcelain`、未push branch、stash、untrackedとGit common directoryを棚卸し。既存作業は削除しない。Orcaに登録するworktreeは作成/移動/削除をgwqと二重管理しない。Pi内部子worktreeは所有範囲を別に記録。

Orca `.worktreeinclude`はliteral path。gwqの`.env.*`globをそのまま貼らず、repoごとに必要な`.env.local`等を**値を含めず**明示する。共有パス/copy/hookの一つへ寄せる。`node_modules`はbranch別lockfileを優先して個別install。`.envrc`/setup hookを確認してからそのrepoだけ人が`direnv allow`。Orca UIからbranchごと削除する操作は未push/未merge確認後だけ。

## 9. backup・復旧・更新

`/data/meta/state-paths.json`の`verified`は初期false。実機でOrca userData、runtime config、pairing grants、managed accounts/keyring、worktrees、layout、session IDs、hooks、HOME外データの**実パス**を調べて記録する。HOME配下なら一括保護されるが、HOME外はVolume/backup対象へ明示的に追加する。snapshotは単一Volumeの外部backupの代替ではない。

Restic repoと復号鍵は人が用意し、VM外にも安全に保管。root-onlyの`/etc/devbox/secrets/restic-repository`と`restic-password`（600、親700）を手動供給する。初期化も人が行う。cloud用認証が必要なら最小権限のbackup専用credentialだけをroot側に置く。devbox/PiへFly tokenを置かない。

`backup.sh`はOrca/DB停止後のみ使用。`/data/home`（Git履歴/未push/untracked/stash/worktreeメタデータ/AI履歴/認証を含む）、`service-data`、`meta`、Tailscale identityを暗号化する。`node_modules`と`.cache`、Nix storeは再構築対象。SQLite稼働中の単純copyは合格にしない。鍵をNix/Docker/Gitへ含めない。バックアップ失敗で容量拡張/古いデータ削除/強制停止しない。

復元は別の承認済み使い捨て環境で行い、原本へ上書きしない。暗号化snapshotを復元してUID/GID、元と同じHOMEパス、Git worktree `.git`参照/common dir/branch/untracked/stash、Orca grants/session再開と認証を確認する。Nixは固定lock/bootstrapから再構築。**同じTailscale identityの新旧VMを同時起動しない。** 失効/再登録手順も試す。復元先VM作成も別承認。

更新はholdして作業を止め、backup後に実施。Orca client/server互換版とOCI digest、Nix/flake.lock/Pi版を記録。通常bootでは更新しない。devboxでのみ`nix run .#devbox-switch`を使う（user/HOME/host markerでguard）。runtimeとNix mergeの同時writerを避ける。image rollbackでVolumeの新しいDB形式まで戻るとは考えない。最後のpromptを起動scriptから再送しない。

## 10. 受入試験（すべて実環境では未実施）

最初はテストrepo/低権限アカウントのみ。各試験に日付・Orca client/server版・OCI digest・lock hash・担当者・結果・secretを除いた証拠を記録。作成/課金/認証登録の事前承認が必要。

| ID | 操作 | 合格条件 |
| --- | --- | --- |
| A01 | 非rootでCLI/serve help、実起動、`ss -lntp`、root-only log権限確認 | 正しいOrca、1 runtime、pairing情報非公開 |
| A02 | Orca terminalで上記HOME/PATH/version確認、Nix build | UID10001、Nix CLI/拡張/認証が利用可能 |
| A03 | Mac Aで長いtest/Pi開始→切断→B接続 | 同じ実行/作業へ戻り、二重指示/プロセスなし |
| A04 | A/B同時接続→片方grant失効 | 失効端末だけ即時切断、既存grantはboot後維持 |
| A05 | Orca管理hookを有効にし、idle時にdevbox-switchを2回 | hooks/独自設定/ルーティング維持、二重登録なし |
| A06 | agent-piの子だけ動く状態と未完了Dispatchを作る | 親doneでもhold/停止阻止が残る |
| A07 | Pi/Claude/Codexを個別に休止・再開 | cwd/session/args/認証/拡張を保つ。agent-pi別検証 |
| A08 | LLM待ち、承認待ち、無出力の長時間処理 | CPUに関係なく止まらない |
| A09 | 全仕事終了/client不在から連続30分 | 現実装は自動停止しない。将来actuator実装後のみ正常停止を合格にする |
| A10 | CLI失敗/JSON欠落/別host/unverified scope | unknown・具体的阻止理由。空JSONをsafeにしない |
| A11 | adapter/controller停止、古い観測、runtime再起動 | 過去のdone/bootを使わず停止禁止 |
| A12 | drain直前/直後/backup中に接続・タスク投入 | 受付済み仕事を落とさず、未受付は拒否。手動hookも必須 |
| A13 | `devbox run`でbuild/test/Nix更新、親exit後の子/daemon | 全範囲終了まで阻止。wrapper kill/PID再利用/旧bootも自動解放なし |
| A14 | Orca/Neovimに未保存編集を残す | 保存確認失敗でstop拒否 |
| A15 | 正常stop/start、その後承認済みrootfs再作成 | Nix DB/profile/gcroots、Orca/Git/認証がVolumeから復元 |
| A16 | 保存済みagentをVM停止後にresume | 新プロセスとして同session/cwdへ。指示の自動再送なし |
| A17 | remote previewでlocalhost/HMR/WS/upload/login、日本語編集 | 対象projectで動く。Playwrightは別にbuild/test |
| A18 | `.worktreeinclude`でローカル設定とbranch別依存 | glob誤移植/秘密commit/共有node_modules破損なし |
| A19 | public/6PN/許可外tailnet/本人端末からport確認 | tailnetは本人6768のみ。管理6PN /128だけ必要時にFly init SSHを許可、それ以外のSSH/DB/previewは拒否。/.fly/api非root拒否 |
| A20 | launcherの不正JWT/issuer/aud/exp/sub、GET、Origin違い、同時POST | 不正起動なし、固定1台、status/start以外なし、rate limit |
| A21 | MacをオフにしてMobile起動ページ→Orca Mobile | mobile-scoped pairing、応答/承認/日本語/再接続。Desktop同等IDEとはしない |
| A22 | 別環境へ暗号化backup restore | Git参照/untracked/stash/session/grants/認証の復旧と失効が可能 |
| A23 | backup失敗/容量不足/hook失敗を注入 | stop中止、VM生存、データ削除なし、fence/復旧理由が残る |
| A24 | 管理面stoppedと請求/usage確認 | compute停止、Volume/rootfs/snapshot等の残費用を説明 |

Mobile pairingは同じuserDataで二つ目の`serve`を起動して作らない。対象版の`--mobile-pairing`での初期起動または正規UIの発行方法を検証して運用へ反映する。Composeが必要なら通常受付/停止/DB保存/port非公開の別試験を追加する。Docker daemonやprivileged権限を未検証のまま開発ユーザーへ渡さない。

## 11. 次にすること

1. ローカルtestsと差分レビュー（課金なし）。
2. x86_64-linuxでactivationPackage build、固定配布物を使ったOCI buildとheadless起動試験。
3. 人が費用・契約・認証・1台/1本の作成を承認してGate 0を開始。
4. 保存先inventory、Orca/Pi/Mac間引継ぎ、版固有stop-hookとbackup restoreを合格させてPhase 1を開放。
5. hibernation/観測/raceの実証後にのみ自動停止actuatorを追加。最後にoptional launcherを公開。

## 参照

- [Orca Remote Servers](https://www.onorca.dev/docs/remote-servers): Remote runtime所有、serve foreground、pairing-addressは通知先。
- [Orca Install](https://www.onorca.dev/docs/install) / [CLI reference](https://www.onorca.dev/docs/cli/reference): Linux CLI/対象版flagsを再確認。
- [Orca hibernation](https://www.onorca.dev/docs/agents/hibernation) / [Session restore](https://www.onorca.dev/docs/model/session-restore): RAM保存と同一視しない。
- [Fly Machines API](https://fly.io/docs/machines/api/machines-resource/) / [restart](https://fly.io/docs/machines/guides-examples/machine-restart-policy/): JSON正本と正常exitの受入。
- [Tailscale on Fly](https://tailscale.com/docs/install/cloud/flydotio): state永続化、TUN/接続の実証。
- [Access JWT](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/): ヘッダー存在だけで認証しない。
