# 別のMacへデスクトップ設定を移す

対象は Apple Silicon Mac。Sky Copy 配色と、yabai／skhd の操作設定を共通化しています。
設定の入口は `modules/home/desktop` と `modules/darwin/desktop.nix` です。

## Nixが管理するもの

| 対象 | 管理内容 |
|---|---|
| yabai / skhd | BSP配置、除外ルール、46キー、補助スクリプト |
| SketchyBar / borders | バー、ウィンドウ枠、配色、透過、blur |
| 4サービス | Home ManagerのLaunchAgent。ログイン時起動、PATH、SHELL、ログ保存先 |
| Ghostty | 通常ウィンドウ、herdr自動起動なし、Cmd+W、Sky Copy配色 |
| Zed | Pywalテーマ、Sky Copy外観、フォントなど既存のZed設定 |
| Zen / Orca | 全初期化済みプロファイルの配色を、アプリの正常終了後に自動同期 |
| Python | pywal、ColorThief、Pillow、Zen用lz4。手動venvは不要 |
| macOS / Floaty | macOSの端ドラッグ等3項目を無効化。Floatyの自動起動・振ってピン留めを無効化 |
| アプリ導入 | Homebrewのyabai、skhd、borders、SketchyBar、blueutil、Zen、Orca。Ghostty/Zed/Raycastは既存のNix宣言を使用 |
| テーマ資材 | OrcaのYAML、Zen／Orcaの配色定義、Raycast正式JSON／URL、壁紙 |
| 壁紙 | 初回と配布画像の更新時に、接続中のディスプレイへ自動設定 |

ブラウザのログイン、Cookie、タブ、Orcaの作業データ、アプリのライセンスは移植しません。
Raycastの初回テーマ登録と選択、macOSの権限付与、アカウントへのログインは移行先で行います。
Homebrewはパッケージの一覧を管理し、バージョンの完全固定は行っていません。`flake.lock`は維持してください。

## 1. リポジトリを別のMacに用意

GitHubへpushした最新版を、別のMacでclone／pullします。

```sh
git clone https://github.com/myksyut/dotfiles ~/.config/nix-config
cd ~/.config/nix-config
```

NixとHomebrewを先に導入します（[SETUP.md](SETUP.md)）。
macOSのユーザー名が異なる場合は `flake.nix` の `username` をそのユーザー名へ変更します。
`darwinHostname` はflakeの構成名です。実機のホスト名が違っても、同じ構成名を明示して適用できます。
この構成は `aarch64-darwin` とARM版Raycastを前提にしています。

## 2. ビルドして適用

```sh
nix run .#build
```

初めてnix-darwinを導入するMac:

```sh
sudo nix --extra-experimental-features 'nix-command flakes' \
  run nix-darwin -- switch --flake .#miyagishoutanoMacBook-Pro
```

nix-darwin導入済み:

```sh
nix run .#switch
```

`darwinHostname`を編集した場合は上の構成名も合わせてください。
このリポジトリには開発ツールなど他の設定も含まれるため、適用前に差分を確認してください。

初回の切り替え時、Nix管理外のデスクトップ設定は `~/.local/state/yabai-config/backups`、
既存のサービス定義は `~/.local/state/yabai-config/launchagents-before-nix` に保存されます。
Home Manager管理の旧設定はNixの旧世代で保持します。

同じサービス名を引き継いでHome Managerが登録し直します。
移行後の起動管理はNixに統一し、`brew services start` や `yabai --start-service` で別の定義を作り直さないでください。

## 3. Macごとの権限と競合設定

「システム設定 → プライバシーとセキュリティ → アクセシビリティ」で
`/opt/homebrew/bin/yabai` と `/opt/homebrew/bin/skhd` を許可します。
SIPを解除する必要はありません。kanataを使う場合の入力監視はSETUP.mdの手順に従います。

許可後、サービスを再起動します。

```sh
launchctl kickstart -k "gui/$(id -u)/com.asmvik.yabai"
launchctl kickstart -k "gui/$(id -u)/com.koekeishiya.skhd"
launchctl kickstart -k "gui/$(id -u)/sh.brew.borders"
launchctl kickstart -k "gui/$(id -u)/sh.brew.sketchybar"
```

ログは `~/Library/Logs/yabai-config` にあります。

RaycastのSettings → Extensionsで、次の競合ホットキーが残っていれば解除します。

- Window ManagementのLeft／Right／Top／Bottom Halfにある `Control+Option+矢印`
- Todoistにある `Command+Shift+T`

Floatyがインストール済みの場合は、アプリとmacOSのログイン項目でも自動起動がオフか確認します。
アプリの設定値とmacOSのログイン登録は別管理です。

## 4. 配色の反映とRaycastの初回設定

テーマファイルは `~/.config/desktop-theme/assets` に配置されます。
詳細は [テーマの手順](modules/home/desktop/themes/README.md) を参照してください。

- **Ghostty:** 起動済みなら `⌘⇧,` で再読み込み。
- **Zen／Orca:** switch時とログイン時、その後60秒ごとに配色を確認します。起動中のアプリは閉じず、変更が必要なら正常終了後の確認で反映します。新しいMacでは各アプリを一度起動し、通常の終了操作で閉じてください。全初期化済みプロファイルが対象です。
- **Orca:** ターミナルはSky Copy、サイドバーは「ターミナルに合わせる」、分割線は `#3c565b` へ自動同期します。内蔵エディタは標準のダーク／ライト配色です。
- **Raycast:** `desktop-raycast-theme` を実行し、**Install Theme（インポート）**、続けてSky Copyを右クリックして **Set as Current (forced)** を選びます。この初回の2操作は必要です。公開APIでの無人選択には対応していません。正式な書き出しファイル `Raycast-Sky-Copy.json` と `.url` も同梱しています。
- **壁紙:** 初回とNix内の画像データ更新時に、接続中のディスプレイへ自動設定します。同じ画像データでの再switchは、後から手動変更した壁紙を保持します。配布画像が更新された場合は、新しい画像に切り替わります。

この構成を作成したMacでは、Zenの13ワークスペースとOrcaがすでにSky Copyと一致していることを確認済みです。差分がなければプロファイルを書き換えません。

配色の確認だけを行う場合:

```sh
desktop-app-themes --app all
```

すぐに再確認・同期する場合:

```sh
desktop-app-themes --app all --apply --defer-running
```

Zen／Orcaのタブ・ログイン・作業データは保持します。変更前のバックアップは
`~/.local/state/desktop-theme/backups/zen` または `orca` に保存されます。
正常な絶対パスの `XDG_STATE_HOME` を指定している場合は、その下の `desktop-theme/backups` を使います。
バックアップはこのMacのセッション情報を含むため、Gitへ追加しないでください。

## 5. 操作・再調整

| 操作 | キー |
|---|---|
| 隣のウィンドウへ移動 | Option＋矢印／H J K L |
| ウィンドウを入れ替え | Shift＋Option＋矢印／H J K L |
| サイズ変更 | Control＋Option＋矢印／H J K L |
| Finder | Control＋Enter |
| Ghostty / Zen / Zed | Option＋Q / B / C |
| 一時ターミナル | Command＋Shift＋T |

Sky Copyは、新しいMacでパレットとZedテーマが未作成の場合に初期配置します。
既存の手動配色は保持します。Sky Copyに明示的に揃える場合:

```sh
reload-theme --reset-palette
```

パレットを保ったままバー・枠・Zedテーマを再読み込み:

```sh
reload-theme
```

壁紙の画像から新しく色を抽出:

```sh
reload-theme "$HOME/Pictures/好きな画像.heic"
```

色抽出コマンドは壁紙自体を変更しません。Ghostty・Zen・Orca・Raycastにも自動連動しません。
ZedのSky Copy外観overrideは固定値なので、別の配色へ全面変更する場合は
`themes/zed-overrides.json` も編集してNixを再適用します。

Zen／Orcaで手動変更した配色は、アプリの正常終了後にNixの配色へ戻ります。
別の配色を継続利用する場合は `themes/zen-workspaces.json` または `themes/orca-theme.json` を編集して再適用してください。

配布している壁紙へ明示的に戻す場合:

```sh
desktop-wallpaper --force
```

GUIセッションや接続中のディスプレイがない場合、壁紙設定は次回switchへ延期します。
未接続のディスプレイや非表示のSpaceまでの反映は保証しません。

## 検証・出典

設定のNix評価、Python／シェルの構文、隔離したHOMEでの初期配置・バックアップ・46キーの一致を確認しています。
Zen／Orcaの適用処理は合成データによる19件のテストで、テーマ以外の保持、再実行、起動中の延期、競合拒否、バックアップと復元、重複実行の排他を確認しています。
別の実機でのアクセシビリティ許可とウィンドウ操作の確認は、移行先で行ってください。

- [yabai-configの移植元](modules/home/desktop/runtime/UPSTREAM.md)
- [Orca公式インストール方法](https://www.onorca.dev/docs/install)
- [HomebrewのZen cask](https://formulae.brew.sh/cask/zen)
- [Raycastテーマのエクスポート](https://manual.raycast.com/themes)
