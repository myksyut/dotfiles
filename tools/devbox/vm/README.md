# Local Cloud Devbox lab (Apple Silicon)

使い捨てx86_64 Linux VM用。Fly/課金/本番認証/既存Mac・WSLのswitchは行わない。
VMの作成・ローカル資源使用は2026-09-05に承認済み。

**現行構成はmulti-user Nix。以下の`db-gate0`コマンドは旧検証の記録であり、失敗storeを再利用・再起動しない。** 新規`db-mu1`の実証は末尾の手順と[MULTI-USER-VALIDATION](../../../docs/CLOUD-DEVBOX-MULTI-USER-VALIDATION.md)を参照する。

## 固定値と境界

- `host-tools.nix`: nixpkgs `044bfe75bfe4c7bbe043dc17b5e42ea823b84a09`、Lima **2.2.0 full**、QEMU **11.0.3**。
- `lima.yaml`: Ubuntu 24.04 minimal `release-20260716`、amd64、公式SHA-256を確認。mutable fallbackなし。
- 4 vCPU、8GiB RAM、80GiB sparse disk。QEMU TCGによるx86_64 VMであり、ネイティブ速度ではない。
- host HOME/SSH agent/既存公開鍵/proxy環境を取り込まず、mountなし。
- 通信はQEMU user-mode NAT。SSHはホストloopbackのみ。サービス自動forwardは禁止。
- NATは完全なネットワーク隔離ではない。公開package取得は可能で、任意の未信頼コード用sandboxとは称さない。
- VM管理用の新しい鍵はLimaが専用state内で生成する。鍵を表示・repoへコピーしない。
- 専用state: `~/.local/share/devbox-lima`。既存`~/.lima`/`~/.ssh`へ設定を追加しない。

## 初回作成

既存out-link/VMがある場合は上書き・再作成せず、まず確認する。

```bash
cd ~/.config/nix-config
nix build --builders '' --file tools/devbox/vm/host-tools.nix \
  --out-link "$HOME/.local/share/devbox-vm-tools"
tools/devbox/vm/lab validate tools/devbox/vm/lima.yaml
tools/devbox/vm/lab start --tty=false --mount-none --name=db-gate0 \
  --timeout=20m tools/devbox/vm/lima.yaml
```

`lab`は最小環境と専用LIMA_HOMEでlimactlを呼ぶ補助wrapper。任意operatorに対するsecurity sandboxではない。共有を追加する`--mount`/`--sync`、`--preserve-env`は使わない。

## 起動・状態・停止

```bash
tools/devbox/vm/lab list
tools/devbox/vm/lab start --tty=false db-gate0
tools/devbox/vm/lab shell --workdir /home/devboxlab db-gate0 uname -sm
# 検証処理がすべて終わった後だけ、正常停止:
tools/devbox/vm/lab stop db-gate0
```

停止はQMP power buttonによるguest正常shutdownを使い、disk/ログを削除しない。通常のVM操作をFly Machine操作と混同しない。docker groupに追加した直後の古いSSH接続ではsocket権限が反映されないことがある。その場合は設定を緩めず、次で接続し直す。

```bash
tools/devbox/vm/lab shell --reconnect --workdir /home/devboxlab db-gate0 id
```

## 許可ファイルだけの転送とbuild/smoke

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/devbox/vm/bundle.py
# 出力されたsource.tarのパスをBUNDLEに手動で指定する。
# この出力をevalしない。初回の空directoryにだけ展開する。
tools/devbox/vm/lab shell --workdir /home/devboxlab db-gate0 \
  mkdir -m 700 /home/devboxlab/oci-gate0
tools/devbox/vm/lab copy --backend=scp "$BUNDLE" \
  db-gate0:/home/devboxlab/oci-gate0/source.tar
tools/devbox/vm/lab shell --workdir /home/devboxlab/oci-gate0 db-gate0 \
  tar --no-same-owner -xf source.tar
tools/devbox/vm/lab shell --workdir /home/devboxlab/oci-gate0 db-gate0 \
  bash tools/devbox/vm/build-smoke.sh /home/devboxlab/oci-gate0
```

OCI bundleは`bundle.py`の`RUNTIME`とchecker/runnerの明示allowlist（現在30通常ファイル）。infraのコード・3配布物・lock・checker・runnerだけで、.pi/.context/.env/認証/machine.local.json/VM stateは入れない。事前にartifact gateを通し、VM側でも再照合する。全repoやHOMEをtar/copyしない。

runnerは次を実施する:

1. offline artifact gate。
2. 空Docker client config、local socket、default builderでamd64 imageをbuild。
3. image IDを`image-id.txt`へ保存し、そのIDで非rootのCLI smokeを実行。
4. networkなし、read-only rootfs、capabilitiesなし、no-new-privileges、空HOME/tmpfs。host/VMディレクトリのbind mountなし。
5. Tailscale版、Orca version/help、deb版を確認。`job.exit`へ終了コードを記録。

`image-id.txt`はDockerが返したローカルimage handleで、registryへpush済みの参照ではない（Docker 29ではmanifest/index digestの場合もある）。container名はbundle directory名から生成し、`container-name.txt`へ記録する。修正後の再検証は`oci-gate1`等の別directoryを使い、以前の証跡を消さない。`job.exit`がない場合は成功扱いしない。失敗時のimage/container/ログは残し、原因を確認する。勝手な再実行や削除、`--no-sandbox`/privilegedでの回避はしない。Nix install/activation、Orca server、実認証、保存/drain/backupはこのrunnerでは行わない。

## Nixのnative検証（別の明示承認で実施済み）

Docker外の専用UID10001でNix 2.35.2を試したが、sandbox必須/fallback禁止では初期profile作成がnamespace不足で失敗した。Home Managerとmarker probeのbuildには未到達。詳細・証跡・次の構成判断は[Nix検証記録](../../../docs/CLOUD-DEVBOX-NIX-VALIDATION.md)。

- `nix-native-provision.sh`: 旧single-user用の記録。再実行しない。通常の`lima.yaml`には追加していない。現在の`sandbox-probe.sh`はmulti-user daemon向けで、旧harnessとの組合せは非対応。
- 実行時は既存の検証用アーカイブを再照合し、`sandbox-probe.sh`と`sandbox-probe.nix`だけをguestの`/home/devboxlab/nix-native-input/`へコピーした。
- VMを正常停止してから、専用stateのLima YAMLにprovision本文を追加・validateし、再開した。変更前YAMLは`lima.before-nix-probe.yaml`へ保全。
- `/var/lib/devbox-nix-probe-v1/result.txt`は`stage=install / exit=1`。LimaのREADYはprobe成功を意味しない。既存失敗/未完了stateでは非zeroを返し、再インストールしない。
- 証跡回収後にVMを正常停止済み。次回起動時にも失敗記録が残るため、そのままHome Managerへ進めない。multi-user等の比較は新しい検証storeと別の設計で行う。

## 実動作で判明した注意点

- OCI buildとOrca/Tailscale CLI smokeは成功済み。初回はOrcaのdebにALSA依存が足りずexit127となり、`libasound2t64`追加後に別runでexit0を確認した。検証後、VMは正常停止済み。

- 通常のNix `lima` packageにはhost archのguest agentしかない。x86_64 VMには`withAdditionalGuestAgents = true`が必要。
- Lima 2.2.0は`guestIP: 0.0.0.0`だけだと`guestIPMustBeZero=true`を補完する。これではguest loopback serviceがfallback ruleでhostへforwardされるため、**falseを明示**した。
- 修正前にguest内loopbackポートの自動forwardを観測した。LAN公開はなく、VM正常停止後に修正・再起動した。修正後はguest loopbackの一時listenerが20秒間hostへforwardされないことを確認した。
- 最初のSSH ControlMasterはdocker group追加前に作られたため、`--reconnect`でgroupを反映した。socketの権限変更や特権による回避はしていない。
- VMでは`apparmor_restrict_unprivileged_userns=1`で、一般ユーザーの`unshare --user --map-root-user true`はuid_map書込時に拒否された。Nix sandboxの成否そのものを検証した結果ではないが、次の確認点。sysctl/AppArmor/sandboxは無効化していない。Fly VMのkernel制約とは別に扱う。

## 現行multi-user検証（db-mu1、一回限り）

設計/実装と新VMの4CPU・8GiB・80GiB以内の実証を2026-09-06に承認。旧VM/途中storeは保全し同時起動しない。`nix-multi-user-provision.sh`と`nix-lab-driver.py`は認証なしfixture専用で、Flyや実HOMEに配備しない。

1. `python3 tools/devbox/vm/bundle.py --native`で固定runtime/seedとallowlisted flake sourceをまとめる。出力はtarパスと`manifest-sha256=...`。出力をevalしない。作成時のmember snapshotも同じ一時directoryへ保全される。
2. `db-mu1`が新規・既存Nixなし・旧VM停止・ホスト共有なしであることを確認する。tarだけをguestの空の`/home/devboxlab/multi-user-input`へcopyし、通常ユーザーとして展開する。
3. manifest hashをホスト側の値と照合する。稼働jobがないbase VMを正常停止後、instance YAMLを保全し、レビュー済みprovision本文と**ホスト側の固定SHAを設定する`DEVBOX_INPUT_SHA256`**をsystem provisionに埋込む。guest入力からanchorを自動採用しない。validate後にこのVMだけ起動する。
4. rootはprivate stagingへcopyしながらhashを照合し、その保存済みbytesだけを配置する。既存のstore/利用者/状態を変換しない。APT前提を確認した後に一回限りの記録を作る。
5. VM disk上の専用directoryを`/data`へbindし、`/data/nix`を`/nix`へbind。production `nix.provision`と`NixRuntime`を再利用し、固定seed → daemon → sandbox → HMを実行する。通常Lima起動テンプレートにはこの処理を追加しない。
6. `/var/lib/devbox-nix-multi-v1/{provision-result.txt,runtime.json,result.json}`を確認する。`launched-not-verified`やLima READYだけは成功ではない。bootstrapとdaemonの詳細ログ、`/data/meta`はroot-onlyで保全する。
7. 失敗時は自動再試行せず、timeout後にclient/workerが残る場合も強制killしない。全検証job終了後だけ正常停止する。再起動を修復手段にしない。追加VM・資源拡張・保護解除はこの手順では許可しない。

このnative harnessはOrca/Tailscaleサービスを起動せず、Nixの安全停止契約を偽装しない。VMの通常shutdownはcredential-free fixtureの管理操作であり、本番`devbox stop`の合格証拠ではない。結果は[MULTI-USER-VALIDATION](../../../docs/CLOUD-DEVBOX-MULTI-USER-VALIDATION.md)へ分けて記録する。
