# Cloud Devbox infrastructure

正本の手順・承認点・受入試験は [CLOUD-DEVBOX.md](../../docs/CLOUD-DEVBOX.md)。

2026-09-06 更新: Fly `myksyut-devbox` にデプロイし、Tailscale経由のブラウザ接続まで確認済み。30秒ごとに観測し、30分連続で接続・実行中コマンド・ターミナル・ブラウザタブ・予約タスク・hold・Nixビルドがない場合だけ停止する実装を追加した。**自動停止を実機へ導入済み。** Flyの`config.files`でコード4ファイルを毎boot注入し、Nix・Orcaの再起動、空のホスト判定、バックグラウンド作業中の停止抑止を確認した。1bootだけ待機を30秒にした動作試験では、controller自身の正常終了によるMachine停止（exit 0、OOMなし、外部停止要求なし）を確認済み。自動停止後の再起動で通常30分設定へ自動復帰し、Nix・Orca・TailscaleとHTTPS経由のOrca接続復旧を確認済み。検証用ブラウザ接続は閉じた。rootfsへの直接パッチはstop/startで消えるため、現構成では`config.files`の保持が必須。Orcaアプリが待機画面でも接続したままの場合、ターミナルを開いたままの場合、予約タスクが残る場合は停止しない。停止後はスマホのFly管理画面から既存MachineをStartする。Orcaへ接続するだけでは起動しない。

- `machine.example.json`: Machines API作成body。単一Machine/Volume、public servicesなし。`fly deploy`は使わない。
- `Dockerfile`: Ubuntu amd64、公式のローカル配布物とSHA-256・Orca版を必須とする。contextはこのディレクトリのみ。
- `artifacts.lock.json`: 公開metadataと取得物を照合した固定URL/hash/サイズ。`tools/devbox/check-artifacts.py`で再確認する。`verified_cli`はローカル非root version/help smokeだけで、server readyではない。
- `entrypoint.sh`: Volume確認、UID/GID検証、永続HOME/Nix/Tailscaleとboot-local runtime、private firewall。
- `bootstrap.sh`: 明示実行だけのsingle-user Nix + standalone Home Manager初期構築。
- `backup.sh`: 検証済みquiesced後だけの暗号化Restic backup。rootはユーザー管理Nixバイナリを実行しない。
- `supervisor/`: rootの主プロセス（Fly init下のPID番号は仮定しない）。Orcaは非root、秘密を含み得るログはroot-only。障害時にOrcaを自動再起動しない。
- `orca-state-adapter/`: 公式CLIの診断収集だけ。未確認JSONをsafeに変換しない。
- `idle-controller/`: 30分の連続アイドル判定、Orca 1.4.197向けのプロセス・接続・CLI状態観測、自動停止controller。観測できない場合は時間をリセットして停止しない。手動停止の既存経路は検証済みsite hookを要求する。
- `state-paths.json`: 実機で埋める保存先一覧。未確認を明示。

配布物固定とローカルbuild/smoke手順は[Linux検証準備](../../docs/CLOUD-DEVBOX-LINUX-VALIDATION.md)。OCI build/CLI smokeは成功し、ALSA依存不足を修正済み。使い捨てVMの手順は[VM lab](../../tools/devbox/vm/README.md)。

**初期実装時の記録（上記更新前）: まだデプロイ可能性の実証はしていません。** Orca起動・TUN/nft・Nix sandbox・PTY終了と保存をGate 0で確認し、実証できなければOrcaを残して基盤を変更します。
