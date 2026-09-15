# Plan: Devboxをmulti-user Nixへ変更する — 新規store・daemon監督・停止境界

状態: **設計レビュー用。実装・VM作成・導入は未承認。**
今回の作業は計画・用語・ADRの文書化のみ。設計の承認だけでVM操作やコード実装を開始しない。Fly作成・課金・実認証・公開はさらに別の承認点。

## Grill checkpoint

Summary: Fly統合まで一括設計、限定bootstrap、新規root所有storeと非trusted利用者、保護維持、固定入力からのNix再構築を質問回答で確認した。

Decisions:

- 既存セッション計画は控えを保存して切替。リポジトリ内の別作業計画は保持。
- 用語とADRを記録し、起動/停止request-ack・lock順序・復旧方針の独立レビューはAPPROVED。
- namespace/drain等は実証gate。不明なら停止拒否し、成功扱いしない。
- 今回は設計文書のみ。実装・VM操作・課金・実認証は開始しない。

Open questions: none

## Context

現行`infra/devbox/Dockerfile`（45行）はUID10001と公式Nix 2.35.2のseedを持ち、`entrypoint.sh`（67行）がユーザー所有の`/data/nix`を`/nix`へbindする。`bootstrap.sh`（46行）はsingle-user installerを使い、`NIX_REMOTE=local`でHome Managerをbuild/activateする。sandbox/fallbackを厳密にしたローカルUbuntu VMでは、初期profile作成時点で必要なkernel namespaceが利用できず失敗した。Home Managerとmarker probeのLinux buildには未到達である。

現行`supervisor/supervisor.py`（320行）はTailscale/Orcaを監督し、`idle-controller/manual_stop.py`（167行）の`developer_processes()`はUID10001だけを検査する。multi-user化後のroot daemon・専用buildユーザー・待機要求はこの検査だけでは扱えない。公式配布物のsystemd unitも`KillMode=process`なので、親daemon終了をworker終了の証拠にはできない。

新構成はrootが管理するstoreとdaemon、非trustedの開発利用者、専用buildユーザーを分離する。ユーザー回答によりFly統合までを一括で設計し、公式固定配布物を使う限定bootstrapを選ぶ。内部の検証順序は分けるが、Nixだけ導入して停止境界を古いままにする変更を完成扱いしない。

### 確定した設計条件

| 項目 | 方針 |
| --- | --- |
| 範囲 | Fly用起動・bootstrap・状態・停止まで一括設計。Mac/WSL/Pi routingは変更しない |
| 旧検証環境 | `db-gate0`は停止・保全。途中storeをchownして信頼済みにしない |
| 次の検証環境 | 別名の新規VM、4 vCPU/8GiB/80GiB上限。旧VMと同時起動しない。作成は実装承認後 |
| 初期負荷 | `max-jobs = 1`、`cores = 2`。不足時は記録して相談し、自動拡張しない |
| 開発利用者 | `miyakishota`、UID/GID10001を維持。daemon利用は許可するがtrustedにはしない |
| build主体 | `nixbld` GID30000、`nixbld1..4` UID30001..30004。専用・非login。既存衝突は拒否 |
| daemon方針 | `trusted-users = root`、`allowed-users = miyakishota`、`build-users-group = nixbld`、`auto-allocate-uids = false` |
| sandbox | daemon側でtrue、fallback=false。クライアントからの無効化が拒否されることを実証する |
| 信頼・通信 | 固定seedのhash照合とNixのrequire-sigsを維持。seedの署名確認済みとは称さない。外部builder/TCP公開/root権限のsocket proxyなし |
| 停止 | 新規受付・既存接続・待機要求・実行中workerの安全を証明できなければ拒否。強制killで合格にしない |
| 災害復旧 | Nix store/DB/root profilesはbackup対象外。固定seed/lockから新規再構築。通常stopではVolumeを保持する |
| 既存境界 | 自動停止無効、Orca版固有hook未実証なら手動停止拒否、Tailscale identityの同時複製禁止 |

`trusted-users`追加は事実上rootアクセスを与えるという公式警告に従う。一般ユーザーのNix設定をroot daemonへ丸ごと取り込まない。単一ユーザーの開発環境でも、パッケージ管理主体を分離する意味でmulti-userと呼ぶ。

---

## Phase 1: 新規storeと限定bootstrapを定義する（TDD）

**Why:** rootが初めてNixを実行する前に、入力・所有権・初期化履歴を保証する。失敗したsingle-user環境を変換しない。

**Test first** → `infra/devbox/tests/test_nix_runtime.py`（新規）

- 新規の空の`/data/nix`領域だけ初期化可能。Volume全体には既知のHOME/meta初期領域があってよい。旧schema、未完了、未知のNix内容、UID/GID衝突、symlink、誤所有者、hash不一致を拒否。
- root-owned runtime metadata、固定CLIパス、seedの必要closure、永続GC rootを検査。
- `/nix/store`の正当な1775と、開発利用者のgroup混入・不正な書込み権限を区別する。
- 途中失敗を次bootの成功にしない。bootはinstall/repair/chownを繰り返さない。

**New file** → `infra/devbox/nix/provision.py`

- root専用の明示one-shot。公式配布物のhashと登録情報を検証し、新規storeへseedをコピー・登録する。
- `--load-db`等の固定配布物と整合する手順だけを利用。公式installer全体を呼ばず、system profile/systemdを自動変更しない。
- 初期化開始前にroot-only状態を永続記録し、検証済み完了を原子的に記録する。秘密は記録しない。
- runtime packageはrootが用意した固定seedのものに限定し、root所有GC rootで保護。開発者のprofile/symlinkをrootの実行パスにしない。
- 単純なstore全体のroot:root・755化はしない。公式モデル通り、store本体はroot:nixbld・1775、DB/管理ディレクトリはroot所有で開発者書込禁止。
- コピー対象・archiveメンバー・link解決・同一FS上のrenameを検証する。既存storeを再帰chownする移行モードは作らない。

**Modify** → `infra/devbox/Dockerfile`, `infra/devbox/.dockerignore`

- 専用buildユーザーをimageで固定し、root所有Nix設定とseed manifestを追加。helperをallowlistへ追加。
- runtime binaryの根拠となるversion/hash/package pathを固定入力から生成。daemon/socketはimage build中に起動しない。
- rootが実行するNixは、新規root管理storeへ検証済みseedを配置したものだけ。seed検証前にユーザーstoreのバイナリを起動しない。

**Modify** → `infra/devbox/bootstrap_state.py`

- `schema`/`nix_mode`、seed digest、runtime path、build UID一覧、bootstrap stageを識別できる形に更新する。
- single-userの既存`home-ready`だけでは新構成をreadyにしない。旧状態の自動変換なし。

**Dependencies / risk:** 配布物のコピーだけで登録・GC root・証明書・profileが揃うとは限らない。fresh VMで実確認するまで限定bootstrapを合格にしない。

---

## Phase 2: 通常起動とdaemonの監督を統合する（TDD）

**Why:** Fly initの下でsystemd/socket activationに依存せず、二重起動・古いsocket・死んだdaemonを扱う必要がある。

**Test first** → `infra/devbox/tests/test_nix_runtime.py`, `infra/devbox/tests/test_startup.py`

- 新規・prepared・failed・旧single-user Volumeの状態遷移。
- 古いsocket、別processのlistener、daemon起動失敗/異常終了、boot ID不一致、監査情報欠落を拒否。
- readinessにタイムアウトを設け、PIDやsocketファイル存在だけで成功にしない。
- daemon障害時はOrcaを新たに起動しない。稼働中作業を強制終了せず劣化状態と要確認を保持し、自動再起動しない。
- bootstrap/start request/通常bootの同時実行、同ID replay、期限切れ・遅延ack、ack待ち中のstopが二重spawnやlock待ち循環を起こさない。

**New file** → `infra/devbox/nix/runtime.py`

- root所有metadataを検証して固定Nix daemonをforeground起動するための管理関数。
- ログはroot-only。最小環境、固定PATH、秘密を引き継がない。ユーザーHOMEのnix.confやprofileをrootでsourceしない。
- 公式seed内unitの`nix-daemon --daemon`を根拠に起動形を決め、実VMでforeground/子処理挙動を確認する。
- prepared記録後、daemon起動前に正規socket directoryをboot-local領域へbindする。未初期化storeに先行してsocket用の永続ディレクトリを作らず、初期化の空領域検査と矛盾させない。
- IPCによる応答・実効設定・専用buildユーザー構成をboundedに検証し、後述の実build合格とは別状態にする。

**Modify** → `infra/devbox/entrypoint.sh`

- `/data/nix`はroot管理となり、現行のUID10001所有検査から分離する。HOME/service-dataはUID10001、meta/Tailscaleはrootのまま。
- `/nix`のbind mountを維持。通常bootは所有権/schemaの検査だけで、新規installはしない。
- `/run`のtmpfsを維持。daemon socketはseed prepared後のruntime処理で、`/nix/var/nix/daemon-socket`へ`/run`配下のdirectoryをbindする候補を検証する。store祖先はsymlinkにしない。
- 生存が不明なsocketを削除して復旧しない。永続socketが混入した旧配置は明示的に拒否する。

**Modify** → `infra/devbox/supervisor/supervisor.py`

- Nixも監督対象へ追加。maintenanceではprepared storeがあるときだけdaemonを起動し、未初期化なら診断可能な待機状態にする。
- 明示provision後は、root所有のrequest/stateを介して未起動→起動へ一度だけ進める。bootstrapとsupervisorの両方から同じdaemonをspawnしない。
- serve条件にNix応答/設定検査と新schemaのHome Manager完了を追加。ただしOrca readinessは引き続きunknown。
- `nix-not-provisioned / starting / available / failed / needs-review`等の非秘密状態を公開する。availableはsandbox試験や全体受入の合格とは別。

**Dependencies / risk:** `/run`のbindとdaemonのlisten pathはFly kernelで別途受入。native VMの成功をそのままFly成功としない。

---

### 起動のrequest/ackと状態機械

永続状態は`/data/meta/nix-state.json`（root:root・600）。`uninitialized → preparing → prepared`のみ正常遷移とし、途中失敗は`failed`へ記録する。`prepared`にはseed/config digest・runtime path・UID構成を含める。boot-local状態は`/run/devbox/nix-control/`（root:root・700）の`request.json`/`ack.json`（600）で分離する。

| 遷移 | 所有する主体・処理 |
| --- | --- |
| 未初期化 → preparing/prepared | 明示bootstrapがbootstrap.lockを取得し、admissionのshared/openを保持してprovision helperを呼ぶ。helperが永続状態を原子的に記録 |
| prepared → start要求 | bootstrapがroot所有のstart requestを原子的にpublish。その後は短いcontrol lockを解放してackを待つ |
| start要求 → starting | supervisorがadmission shared/openの下でrequest/seedを検証し、acceptedをpublish。spawnはこの主体だけ |
| starting → available | supervisorがIPC/設定/PID開始識別を検証し、同じrequest IDのready ackをpublish |
| available → HM処理 | bootstrapが同boot/generationのready ackと生存を確認し、UID10001のHM処理へ進む |
| 通常bootのprepared | supervisorが同じdispatcherへboot起動要求を投入。bootstrapのstartと重複しても同generationの生存daemonへ応答し、二重spawnしない |
| failed / needs-review | 自動再要求・再spawnなし。store初期化失敗やbootstrap失敗をreadyで上書きしない |

requestの固定schemaは`action`、128-bitランダム`request_id`、`boot_id`、`generation_digest`、monotonic期限。ackは同じ識別子と`accepted/ready/failed`、非秘密reason code、daemonのPID/開始識別を持つ。pathや任意argvをrequestから実行しない。regular file・root所有・mode600・single link・bounded JSONを検証する。

同じrequest IDには同じ終端結果を返す。別IDで同generationのstart要求が来ても既存processを再利用する。異なるboot、期限切れ、世代不一致、改変された識別子は拒否する。daemon応答の上限30秒、bootstrapのack待ちは45秒。timeoutではbootstrapをfailedにし、遅れたreadyでHMへ進まない。既にspawnされたprocessは監督下に残して要確認とし、勝手にkill/retryしない。

**Lock順序:** bootstrap.lockまたはstop.lock（別のcontroller排他）→ admission → control.lock。control.lockはpublish/readの短い区間だけ。ack待ち中はcontrol.lockを持たない。bootstrapはadmission sharedを保持してよいが、supervisorのstart側もsharedとし、bootstrap.lockは取得しない。stop側のadmission取得はnonblockingで、bootstrap中ならbusyを返す。これらの順序とtimeoutを競合テストする。

## Phase 3: 非trusted利用者でHome Managerを構築する（TDD）

**Why:** 現在の`NIX_REMOTE=local`とsingle-user profile依存を除き、開発利用者がroot管理storeへ直接書かずdaemon経由で構築する。

**Test first** → `infra/devbox/tests/test_nix_probe.py`, `infra/devbox/tests/test_startup.py`

- bootstrapがsingle-user installer/local storeへ戻らないこと。
- daemon不足・sandbox未合格・profile生成失敗ではactivation/home-readyへ進まない。
- runtime用root GC rootと利用者のHM profileを混同しない。
- CLI設定や環境からsandbox/fallback・trusted設定を緩めようとしてもdaemonが許可しないことを実VMで検査する。

**Modify** → `infra/devbox/bootstrap.sh`, `infra/devbox/bootstrap_state.py`

- 手順はseed prepared → supervisorによるdaemon ready → 小さなsandbox gate → HM build → HM activate → profile検証 → home-ready。
- rootは所有権・metadataと進行を管理。checkout参照・Nix client・HM activationはUID10001で実行する。
- root所有の固定Nix clientを使い`NIX_REMOTE=daemon`を明示。初回は利用者の`.nix-profile/bin/nix`の存在を前提にしない。
- stageごとの失敗を記録し、失敗を自動retryしない。入力はレビュー済みallowlist source、固定flake.lock。外部builder/実認証を持ち込まない。

**Modify** → `infra/devbox/orca/serve.sh`, `modules/home/hosts/devbox.nix`

- devboxだけdaemon接続をsessionへ渡す。Mac/WSLの既定値は触らない。
- HM適用後の実profileと`hm-session-vars.sh`・Nix CLI・zshのパスを検査する。古いsingle-user installerが作ったprofileを前提にしない。
- Pi packages/models/keybindings/routing、Orca管理外キーのmerge方針は維持する。

**New file** → `infra/devbox/nix/sandbox-probe.nix`

- 既存VM probeを元に、登録済みNix closureで最小buildを行う共通fixture。公開markerが外側で読め、内側では見えないことを確認する。

**Modify** → `tools/devbox/vm/sandbox-probe.sh`

- single-user/local store専用条件をmulti-user daemon検証へ更新。PID/UIDの外側観測も取り、専用buildユーザーの実行を確認。
- 毎回異なるmarker、substitute禁止、再build、impure内側評価、UIDに依存しないmarker読取権限を維持する。

**Dependencies / risk:** daemon応答成功やcache取得だけではsandbox合格ではない。任意のクライアント設定変更がdaemonでどう扱われるかは固定版の実験を必須にする。

---

## Phase 4: Nix作業も含む停止拒否・正常停止を統合する（TDD）

**Why:** root daemonを止めてもbuild workerが残る可能性があり、UID10001のみの列挙や既存PGIDだけでは検出できない。

**Test first** → `infra/devbox/tests/test_nix_stop.py`（新規）, `infra/devbox/tests/test_fence.py`

- 専用build UIDの処理が残る場合、root worker・別PGID/SIDの子、古いPID、観測エラーでは停止拒否。
- 新規接続、既存IPC接続からの追加要求、待機job、client切断後のworker、同時bootstrap/GCが停止と競合する場合を検証。
- Nix daemon終了後にもworkerが残る、異常exit、timeout、記録/sync失敗ではfenceを維持してneeds-review。
- Nix設定を変えてbuildユーザーを検査対象外へ逃がすことを許可しない。プロセス名whitelistは使わない。
- 最終stop-approved発行前に中間Nix stop ackを返せること、controllerが待つ間にsupervisorが必要lockを取得できること、backup失敗後に古いackから再開しないこと。

**Modify** → `infra/devbox/idle-controller/manual_stop.py`, `infra/devbox/idle-controller/safety.py`

- 既存admission fenceを維持し、root管理Nixの実行主体・bootstrap中状態・drain観測を別途検査する。
- 現行UID10001検査は残し、全専用build UIDと監督対象root workerを追加。これだけを停止の十分条件にはしない。
- Unix socketのchmodは既存接続を無効化しないため、それだけでdrain成功にしない。root権限のIPC proxyも作らない。
- `verify-quiescent`で実行中/待機中仕事が解決したことを確認し、`save-and-stop`後にも受付・接続・workerを再検査する。

**Modify** → `infra/devbox/nix/runtime.py`, `infra/devbox/supervisor/supervisor.py`

- 停止順の契約: admission閉鎖 → 検証済みhookでOrca/Nix新規仕事を遮断 → 既存作業完了・保存 → Orca終了 → Nix接続/待機要求/worker確認 → daemon正常終了・残存確認 → backup → Tailscale終了 → sync/完了記録。
- backup前にNix側の正常停止確認が終わるよう、現行hook/supervisor間の責任分界を変更する。supervisorを唯一のdaemon spawn/終了実行主体とし、boot-bound request/ackでoperator側と同期する。
- 初期化・GC・root保守操作も同じ停止fenceに参加させる。完了前のSIGTERMを「安全停止」と扱わない。
- 自動停止は追加しない。一般のNixコマンドすべてを勝手にPiラッパーへ置換しない。

### 中間停止request/ack（最終stop-approvedとは別）

1. `manual_stop.py`がstop.lockを保持して処理を直列化する。admissionを短時間exclusiveで閉鎖・永続記録し、**そのflockを解放してから**hook/ack待ちへ進む。閉鎖状態自体は保持される。
2. 検証済みhookで受付遮断・既存仕事解決・保存・Orca終了を確認後、同じcontrol directoryへ`action=quiesce-stop`をpublishする。`drain_id`と対象daemonのgeneration/PID開始識別を要求へ追加する。
3. supervisorは最終`stop-approved.json`の有無に関係なく、loopの独立したNix control処理でこの要求を読む。閉鎖fence・drain_id・同boot・生きたdrain観測を再確認する。証明不足ならfailed ackで拒否し、signalを送らない。
4. 契約の確認後にsupervisorだけが正常終了を要求する。exit codeと専用UID/root workerの残存を検査して、同IDの`stopped`または`failed` ackをpublishする。上限30秒、強制kill/再起動なし。
5. manual_stopはcontrol/admissionのlockを持たず、stop.lockだけを保持して最大45秒待つ。supervisorはstop.lockを取得しない。stopped ackと現状態を検証してからbackup/verify-stoppedを実施し、最後に従来の最終`stop-approved.json`を発行する。
6. 最終承認には対応するNix stop request IDを含める。supervisorは同bootのstopped ack・閉鎖fence・残存なしを再検査し、初めてTailscale終了・sync・最終記録へ進む。中間ackだけでVM全体を停止しない。

途中crash/timeout/ack書込失敗はneeds-reviewとして停止を拒否する。後から届いたackだけではcontrollerを自動再開しない。最終承認の短い期限はbackup後の発行時点から計測し、古い中間ackを最終承認として流用しない。正常な中間ackの保持中も、fence再開・世代変更・不明なprocessがあれば無効とする。

**未実証部分の扱い:** Nixに未確認の`drain`/job一覧APIを仮定しない。固定版sourceとローカル結合試験で、既存接続・accept待ち・workerを閉じた観測範囲として扱える手段を実証する。root管理cgroupを使う場合もFlyの委譲可否と逃走拒否を先に検証する。実証できなければNix drainはunknownを返し、手動停止は拒否したまま。この分岐をPhase 1合格と報告しない。

**Dependencies / risk:** Orca版固有の保存/受付遮断hookも引き続き必須。Nixの導入が成功しても、この契約が未合格なら日常利用・安全停止の受入は未完了。

---

## Phase 5: 検証VM・配布・運用記録を更新する

**Why:** 古い検証結果やimage digestで新しい構成が検証済みと見えることを防ぐ。

**Test first** → `infra/devbox/tests/test_vm_tools.py`, `infra/devbox/tests/test_nix_probe.py`

- bundle/snapshotに新helperとfixtureだけを追加。HOME/.pi/.context/認証/既存stateは引き続き除外。
- fixed seedとUID一覧、失敗証跡の保全、新旧VMの取り違え拒否。
- storeなしのrestore、danglingな利用者profile、古いprepared/home-ready、入力取得不能で復旧を成功扱いしない。再構築後だけ新しいreadyを発行する。

**New file** → `tools/devbox/vm/nix-multi-user-provision.sh`

- 新規VM専用の限定bootstrapとNix lifecycle検証harness。productionと同じhelperを使い、systemdがあるVMだけで成功する別実装にしない。
- VMのサービス管理をharnessとして使う場合も、実際のforeground daemon/子処理監督コードは共通にする。

**Modify** → `tools/devbox/vm/bundle.py`, `tools/devbox/check-nix.py`

- 必要な新規ファイルを明示allowlistへ追加し、artifact/credentialsをNix評価sourceへ混ぜない。
- 新規VM名・ログ・root所有store状態を分離。旧`nix-native-provision.sh`と失敗結果は履歴として保存し、再実行しない。

**Modify** → `infra/devbox/state-paths.json`, `infra/devbox/machine.example.json`

- store/DB/profiles/GC rootsとvolatile socketの責任を更新。既存data/Nixを共有して新旧同時稼働させない。
- 現時点で`verified`や`oci_digest`を成功値にしない。Machine作成は別承認。

**Modify** → `docs/CLOUD-DEVBOX.md`, `docs/CLOUD-DEVBOX-VALIDATION.md`, `docs/CLOUD-DEVBOX-LINUX-VALIDATION.md`, `tools/devbox/vm/README.md`

- 新規storeへの移行、正常停止/失敗復旧、Nixをbackup対象外として再構築する復元手順を更新。
- rootのResticはUbuntuの固定経路を維持。store全体を盲目的にrestoreして信頼済みにしない。
- 新しいOCIを再buildして正確なimageを記録し、そのimageでCLI/Nix/lifecycleを再検証する。

### 確定した復旧契約

- 通常stop/startでは`/data/nix`を含むVolumeを保持する。災害復旧backupではNix store/DB/root profiles/GC rootsを保存対象外とし、HOME・作業データ・meta・Tailscaleの既存暗号化backupを維持する。
- 復旧は別の空のroot管理storeへ固定seedを検証して初期化し、記録したflake.lock・ソースからHMを再buildする。取得物が失われた場合は復旧未完了として止める。最新版への自動置換なし。
- restoreされたmetaは**過去の証跡**であり、prepared/home-ready/clean-stopの現行承認にしない。新しいgenerationで再検証する。
- HOME内の`.nix-profile`やHM profile/GC-root symlinkは、消失したstoreを指す可能性がある。UID10001で既存linkを調べ、復旧作業専用の控えへrenameして保全後にHM profileを再作成する。未知の通常ファイル・symlink traversal・衝突は拒否し、rootで追跡/実行しない。
- 失われたstoreへ参照するprofileが残らないことと、Orca/CLI/Piの読込を確認してから新しいhome-readyを発行する。root runtimeのGC rootは新storeの固定seedから作る。
- 元のMachineが動いていれば、同じTailscale identityを持つ復旧先を起動しない。旧identityを再利用する操作は別のoperator確認点。

---

## Critical Files

| File | Action |
| --- | --- |
| `infra/devbox/nix/provision.py` | New: 新規root管理storeの限定初期化 |
| `infra/devbox/nix/runtime.py` | New: daemon起動・状態・停止契約 |
| `infra/devbox/nix/sandbox-probe.nix` | New: 共通sandbox実build fixture |
| `infra/devbox/Dockerfile`, `.dockerignore` | Modify: build users/設定/配布 |
| `infra/devbox/entrypoint.sh` | Modify: store所有権・boot-local socket |
| `infra/devbox/bootstrap.sh`, `bootstrap_state.py` | Modify: daemon経由・stage/schema |
| `infra/devbox/supervisor/supervisor.py` | Modify: 唯一のdaemon監督主体 |
| `infra/devbox/idle-controller/manual_stop.py`, `safety.py` | Modify: Nix作業・停止fence |
| `infra/devbox/orca/serve.sh` | Modify: client環境/profile確認 |
| `modules/home/hosts/devbox.nix` | Modify: devboxだけdaemon環境 |
| `infra/devbox/tests/test_nix_runtime.py`, `test_nix_stop.py` | New |
| `infra/devbox/tests/test_startup.py`, `test_nix_probe.py`, `test_fence.py`, `test_vm_tools.py` | Modify |
| `tools/devbox/vm/nix-multi-user-provision.sh` | New |
| `tools/devbox/vm/sandbox-probe.sh`, `bundle.py`, `tools/devbox/check-nix.py` | Modify |
| `infra/devbox/state-paths.json`, `machine.example.json` | Modify: 保存領域・未検証状態 |
| `docs/CLOUD-DEVBOX*.md`, `tools/devbox/vm/README.md` | Modify: 手順・実行結果・未合格事項 |
| `CONTEXT.md`, `docs/adr/0001-devbox-multi-user-nix.md` | 今回は設計文書のみ作成 |

## Reusable Components (no changes needed)

- Pi設定mergeと既存routing/catalog/keybindings — 既存の管理境界を維持。差分検証を再利用する。
- Tailscale startup検証とprivate firewall — 今回のNix変更で弱めない。
- `tools/devbox/devbox`の既存管理CLI/hold/run — 受付fenceを再利用し、全Piプロセスの新しいラップを追加しない。
- `tools/devbox/check-artifacts.py` — seedのhash/size検証を再利用する。
- `infra/devbox/backup.sh`のUbuntu Restic実行 — 呼出順は見直すが、root実行バイナリをユーザーprofileへ切り替えない。
- optional起動Worker — 今回未変更、課金startを検証のために実行しない。

## Verification

実装承認後に、変更した範囲から実行する。以下は**予定コマンド・合格条件**であり、今回実行した記録ではない。

1. `python3 -m unittest discover -s infra/devbox/tests -p 'test_nix*.py' -v` — 新規store/daemon/停止・設定の関連テスト成功。
2. `python3 -m unittest discover -s infra/devbox/tests -p 'test_startup.py' -v` と `-p 'test_fence.py'` — 起動/停止変更に対応する回帰成功。
3. `shellcheck infra/devbox/bootstrap.sh infra/devbox/entrypoint.sh infra/devbox/orca/serve.sh tools/devbox/vm/sandbox-probe.sh tools/devbox/vm/nix-multi-user-provision.sh`、新規Nix fixtureの`nixfmt --check`、対象Python診断。
4. `PYTHONDONTWRITEBYTECODE=1 python3 tools/devbox/check-nix.py` — 統合時に3ホスト評価/Pi比較とnative testsを確認。各小修正ごとの全suite再実行はしない。
5. 新規VMでsandbox必須build・build UID・公開marker隠蔽を確認。clientによるsandbox無効化要求、local store直接書込み、許可外ユーザーのdaemon利用を拒否。cached outputやIPC応答だけで合格にしない。
6. 固定flake.lockのHM実build、検証VM内だけでactivation、profile/CLI/Pi管理設定の比較。秘密や実認証を用意しない。
7. 新OCIで非root/network-none/read-only CLI smokeを再確認。Dockerのseccomp不足がある場合、保護を外さずnative VMでproduction helperを検証し、その差を記録。
8. bootstrap中・長時間build・待機build・既存接続・別SID worker・daemon異常終了・同時stop・失敗後bootを結合試験。処理が残るケースで停止しないことを必須にする。
9. shutdown全体の合格はNix/Orca両方の受付・保存・残存process・復旧契約を実証してから。未実証ならunknown/needs-reviewを維持する。
10. `git diff --check`、flake.lock hashと既存stage保全、証跡のignore/permissions、新VMの正常停止を確認。VM/workerが稼働中なら完了と言わない。

## References / 残る実証事項

- [実測したsingle-user失敗](CLOUD-DEVBOX-NIX-VALIDATION.md)
- [Nix 2.35設定仕様](https://nix.dev/manual/nix/2.35/command-ref/conf-file): sandbox/fallback、trusted-users、allowed-users、build-users-group、store 1775、auto-allocate-uids。
- 公式固定2.35.2配布物の`install-multi-user`、`install-systemd-multi-user.sh`とdaemon service/socket unitを読んだ。実行はしていない。
- **実証待ち:** root daemonのnamespace成立、クライアント設定の制限、socket配置、接続/待機jobを含むdrain、Fly kernel/cgroup/終了挙動、HM実profile、Orca保存hook。
- **未決の利用者判断:** なし。上の実証が失敗した場合は変更を拡張せず、その時点で次の判断を求める。
