# Nix単一ユーザー構成の実検証 — Gate 0未合格

実施日: 2026-09-05。対象は承認済みのローカルLima VM `db-gate0`だけ。
**Nix 2.35.2のsandbox必須インストールが初期profile作成で失敗した。Home Manager build/activationには進んでいない。**

## 実行したこと

- Dockerのseccompと混同しないため、Ubuntu 24.04 x86_64 VM内で直接検証した。
- VMの一般userでAppArmor設定`apparmor_restrict_unprivileged_userns=1`、`Seccomp: 0`、`NoNewPrivs: 0`、profile `unconfined`を確認。以前の一般user namespace probeもuid_map書込を拒否された。
- 同VMに未使用UID/GID 10001、専用HOME、ユーザー所有`/nix`を作成。Mac/WSLにはユーザー・Nix・profileを追加していない。
- 既存の公式Nix 2.35.2アーカイブを再度SHA-256照合して使用。Limaの追加system provisionで準備し、installerは非root、最小環境、channel追加なし、shell profile変更なし、substitute/remote builderなしで実行した。
- `/etc/nix/nix.conf`に`sandbox = true`と`sandbox-fallback = false`を明示。保護の無効化やprivileged containerでの回避はしていない。

結果:

```text
stage=install
exit=1
installing 'nix-2.35.2'
error: this system does not support the kernel namespaces that are required for sandboxing
/opt/devbox-nix-probe/install: unable to install Nix into your default profile
```

Nixのコピー・登録後、初期profile作成で失敗した。**インストール成功とは扱わない。** エラーに表示されるsandbox無効化オプションには従っていない。

これは当該Ubuntu VMでの結果であり、Fly kernelでの失敗や、全Linux環境でsingle-user構成が不可能であることを証明しない。AppArmor制約と整合するが、個別拒否syscallのauditまで取得して原因を断定したわけではない。

## 検証用コードと限界

- `tools/devbox/vm/nix-native-provision.sh`: 任意追加の一回限りのVM準備。既存Nix/userを上書きしない。失敗・途中状態を次回成功扱いせず、自動retryしない。通常のVM templateには組み込んでいない。
- `sandbox-probe.sh` / `sandbox-probe.nix`: 外側では読める公開markerがsandbox内では見えないことを検査する、小さなローカルbuild。Nix自身の登録済みclosureを使い、nixpkgs取得を必要としない。
- probeはfallback/substitute/remote builderを禁止し、毎回異なるmarkerと`--rebuild`を使用。内側もimpure evaluatorにして、pure evaluation制限やUIDの読取権限をsandboxと誤認しない。
- **今回はinstallerで止まったため、このprobeのLinux build段階には未到達。** Macで式の陽性・陰性controlだけを確認した。これはsandboxの合格結果ではない。
- 追加offline回帰8件PASS。DarwinのNix native check全82件PASS。3ホスト評価/Pi routing比較も一致。これらもLinux Home Manager実buildの代わりではない。

## 見つかった設定不備の修正

Nix 2.35の[`sandbox-fallback`](https://nix.dev/manual/nix/2.35/command-ref/conf-file#conf-sandbox-fallback)は既定値が`true`で、kernelが許可しない場合にsandboxを無効化できる。**`sandbox = true`だけでは必須条件を保証できなかった。**

- Dockerfileに`sandbox-fallback = false`を追加。
- bootstrapでもinstallerより前にsandbox/fallbackを強制し、local store、外部builderなし、権限昇格なしを明示。
- 初期化の失敗・未完了・symlink結果の拒否と、bootstrapの設定上書きを回帰テスト化。

この修正後のOCI再buildは未実施。以前のOCI/Orca CLI smoke成功は以前のimageに対する記録として維持する。Gate 0未合格・自動停止無効は変わらない。

## 証跡と終了状態

- VM内: `/var/lib/devbox-nix-probe-v1/{run.log,result.txt}`。
- hostのGit ignore内: `infra/devbox/build-evidence/20260905-nix-native/`。directory 700、コピーしたログ600。秘密・VM鍵・HOMEのコピーなし。
- 実行したprovision SHA-256: `18f359d82289ed95586f9b07cd93441479684e53c8ae39abd143e62811d87be6`。
- probe shell: `20d0b43fa3be8177071b26f965315699ea19755b4dca73d3f43f448afe45d05e`。
- probe Nix: `07f2bb6d3f562e40866e6dbbf34e3b35a1e10ede10d756d2928ea57e32332743`。
- 実VMのLima YAMLにprovision本文を追加して実行。変更前は同state directoryの`lima.before-nix-probe.yaml`へ保全。既存のmount/SSH/port-forward制約は保持。
- 23:34 JST、UID10001の処理とrunning containerがないことを確認してVMを正常停止。diskと途中のNix storeは保全した。
- **次回起動でも失敗記録は残り、当該provisionは非zeroを返す。** LimaのREADYだけでは合格扱いしない。再試験は別途設計・承認し、失敗stateを削除して再実行しない。

## 次の判断

**推奨: 別の新規検証storeでmulti-user Nixを設計・検証する。** root daemonがnamespaceを準備し、実buildは専用の非root build usersで行う構成を比較する。OSのAppArmor/sysctlやsandboxを無効化しない。まだmulti-user installer/daemonは導入していない。

- ユーザー書込み可能だった今回のstoreを、所有権変更だけでrootの信頼済みstoreへ昇格させない。
- daemonの監督・終了順、root所有store、build users、Volume配置、既存bootstrapからの変更を先に設計する。
- 新構成で小さなsandbox buildが成功してからHome Managerの実build・検証VMだけでのactivationへ進む。
- その後にOrca server、保存/drain/停止/backupを検証する。Fly作成・課金・実認証は別承認。
- 旧Machineとreplacementを同じTailscale identityで同時稼働させない。
