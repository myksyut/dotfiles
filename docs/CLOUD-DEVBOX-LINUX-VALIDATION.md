# Cloud Devbox — 固定配布物とLinux検証準備

## 現在地（2026-09-05）

**配布物照合・使い捨てx86_64 Linux VM・OCI build・非root CLI smokeまで成功。VMは正常停止済み。Phase 1受入は未完了。**
Darwin arm64上に専用Lima/QEMUをNixで用意し、既存ホスト設定はswitchしていない。後続の[Nix実検証](CLOUD-DEVBOX-NIX-VALIDATION.md)ではsandbox必須のsingle-user installが初期profile作成で失敗した。Home Managerには未到達。fallback禁止修正後のOCI再buildも未実施。次はmulti-user構成の比較・設計が判断点。

| 配布物 | 固定版・確認内容 |
| --- | --- |
| Ubuntu | 24.04、linux/amd64 manifest digest。registryのmanifestとconfigをハッシュ照合しarchitectureを確認 |
| Nix | 2.35.2、x86_64-linux、27,131,728 bytes。公式.sha256と取得物が一致 |
| Orca | 1.4.197、amd64 deb、162,285,876 bytes。公式GitHub release asset digestと取得物が一致 |
| Tailscale | 1.102.3、amd64、38,693,297 bytes。公式.sha256と取得物が一致 |

正本は[`infra/devbox/artifacts.lock.json`](../infra/devbox/artifacts.lock.json)。URL・SHA-256・サイズ・照合元を記録した。
`latest`は候補の発見だけに使い、取得/buildの入力は固定URLとhashとする。GitHub releaseはimmutableではないため、将来同じURLの内容が変わってもhash不一致で拒否する。署名や独立した真正性の検証済みとは称さない。

Orca debを**実行・展開installせず**読んだ結果:

- Package=`orca-ide`、Version=`1.4.197`、Architecture=`amd64`。
- CLI wrapperは`/opt/Orca/resources/bin/orca-ide`。postinstは`/usr/bin/orca-ide`をこのwrapperへリンクするコードを持つ。
- wrapperは同梱Electronを`ELECTRON_RUN_AS_NODE=1`で使い、CLI用のJSを起動する。
- `xvfb`等の依存宣言を確認。後続VM検証で`libasound.so.2`不足が判明し、`libasound2t64`追加後に`--version`/`serve --help`が成功した。

取得物はGit/Docker context全体に混ぜず、`infra/devbox/artifacts/`へ置く。同directoryはGit ignore、Dockerは3ファイルだけをallowlistする。lockには秘密・pairing URL・認証情報を入れない。

## 1. 検証先（作成・起動確認済み）

承認後、**使い捨てのx86_64 Linux VM `db-gate0`**を作成した。既存Mac/WSLへactivationしていない。

- Lima 2.2.0 full / QEMU 11.0.3。固定Ubuntu 24.04 minimal imageで`Linux x86_64`を確認。
- 4 vCPU / 8GiB RAM / 80GiB sparse disk。Docker 29.1.3 / Buildx 0.30.1が稼働。QEMU TCGのため実速度はnativeとは異なる。
- host共有mount・SSH agent転送なしをguest内で確認。guest loopback listenerの自動forwardも否定試験済み。
- 再現手順・停止・copy/build runnerは[`tools/devbox/vm/README.md`](../tools/devbox/vm/README.md)。専用LIMA_HOMEと空Docker client configを使う。
- HOME、Docker socket、既存Nix store、実Tailscale state、認証ディレクトリを検証コンテナへmountしない。実identityを複製しない。
- Fly、有料/外部builder、push/deployはこの検証には不要。

## 2. 配布物のoffline gate

```bash
cd ~/.config/nix-config
python3 tools/devbox/check-artifacts.py

# 別の検証機へ秘密なしのsourceを用意した場合:
python3 tools/devbox/check-artifacts.py --print-downloads
# 表示されたコマンドを読んでから人が実行する。eval/自動pipe実行はしない。
# 既存ファイルはskip。失敗/古い取得物は人が確認し、無断で削除・上書きしない。
python3 tools/devbox/check-artifacts.py
```

helper自身は通信/ダウンロード/install/Docker実行をしない。型・version付き公式URL・サイズ・SHA-256・ファイルのregular/single-linkを検査する。symlink/FIFO/不一致は拒否する。印刷したdownloadコマンドにもdirectoryのsymlink拒否と既存fileのskipを入れている。同時downloadは行わない。

## 3. ローカルOCI build（Docker Engine + Buildxが必要）

```bash
python3 tools/devbox/check-artifacts.py --print-build \
  --docker-host unix:///var/run/docker.sock
# 表示されたコマンドをレビューし、用意したLinux検証機で人が実行する。
```

出力は空の一時Docker client config、明示local Unix socket、default builder、linux/amd64、hash/version build args、`--load`を指定する。既存client認証やremote context/builderを引き継がない。実際のlocal socketが異なる場合だけ明示指定し、ssh/tcp endpointは使わない。Buildx pluginは空configでも発見できるsystem pluginとして必要。

Dockerfileはamd64、deb package/version/architecture、CLI wrapperへのリンクをbuild中にも照合する。hash検査を外して通さない。build contextは**infra/devboxのみ**。

Ubuntu baseと3配布物は固定だが、apt依存はbuild時のrepositoryから解決するため**完全再現buildではない**。生成image ID、registryへ将来pushしたときのOCI digest（別承認）、`/opt/artifacts/dpkg-packages.txt`、buildログを記録する。一時Docker configとimage/containerは自動削除しない。

## 4. ネットワークなしのCLI smoke（build成功後のみ）

同じ検証用Linux機で以下をレビューして実行する。まだTailscale daemon/Orca server/entrypointを起動しない。既存container名があれば上書きせず確認する。

```bash
docker_config=$(mktemp -d -t devbox-docker.XXXXXXXX) || exit 1
env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  DOCKER_CONFIG="$docker_config" docker --config "$docker_config" \
  --host unix:///var/run/docker.sock run \
  --name devbox-gate0-smoke --pull=never --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges:true --user 10001:10001 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  --env HOME=/tmp/devbox-smoke --entrypoint /bin/bash cloud-devbox:gate0 -euc '
    umask 077
    mkdir "$HOME"
    test "$(id -u)" = 10001
    test -f /opt/nix-bootstrap/install
    /opt/tailscale/tailscale version
    /usr/bin/orca-ide --version
    help=$(/usr/bin/orca-ide serve --help)
    printf "%s\n" "$help"
    grep -q -- --pairing-address <<< "$help"
  '
```

出力のTailscale/Orca版をlockと比較し、CLI成功を記録する。失敗したら原因を調べ、`--no-sandbox`/公開ポート/privilegedで回避しない。これはversion/helpの検査だけで、Nix install/buildやOrca serveの成功を意味しない。

## 5. 次の実機ゲート（未実施）

1. x86_64 Linuxで`tools/devbox/check-nix.py --build-home`。必要コードだけのallowlist snapshotで実buildし、既存ホストはswitchしない。
2. 独立したVM/空のデータ領域でmount、UID/GID、Nix single-user sandbox、bootstrap失敗/復旧と再bootを確認する。Docker制約とFly VM制約の差は別に検証する。
3. 別承認後にTailscale認証・Node ID照合、grants否定試験、Macからのprivate到達を実証する。
4. Orca保存・drain・terminal/agent子処理・終了・backup restoreの版固有contractを実証し、初めてstop-hookを実装する。

`verified_cli`は今回成功したversion/help smokeのパスだけを記録し、server readyとは扱わない。registryへ未公開のため`oci_digest`はnull。上記受入が終わるまで自動停止は無効、Phase 1未合格を維持する。旧Machineとreplacementを同一Tailscale identityで同時に動かさない。
