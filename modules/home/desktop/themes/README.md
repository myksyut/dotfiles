# Sky Copy アプリ配色

このディレクトリには配色・壁紙を置きます。ログイン、Cookie、タブ、プロファイル、アプリのデータベースはGitへ保存しません。

## 自動配置

- Ghostty: macOSの `config.ghostty` をNixで配置。開いているウィンドウは `⌘⇧,` で再読み込み。
- Zed: Nixでテーマ選択と外観overrideを設定。`zed-pywal.json` は書き換え可能なテーマの初期値としてコピーします。
- 共通: `~/.config/desktop-theme/assets` に配色ファイルを配布。
- Zen／Orca: switch時・ログイン時・その後60秒ごとに、全初期化済みプロファイルの配色だけを同期。
- 壁紙: 初回と配布画像の更新時に、接続中のディスプレイへ設定。

## Zen／Orcaの自動同期

新しいMacではアプリを一度起動して初期設定を済ませ、通常の終了操作で閉じます。次の同期で配色が反映されます。未作成のプロファイルは作成せずスキップし、後で初期化されたプロファイルも自動的に対象にします。

起動中のアプリは閉じません。配色がすでに一致する場合は変更せず、差分がある場合は正常終了後まで延期します。この構成を作成したMacでは、Zenの13ワークスペースとOrcaがすでに配色定義と一致しています。

確認だけを行う場合:

```sh
desktop-app-themes --app all
```

すぐに同期する場合:

```sh
desktop-app-themes --app all --apply --defer-running
```

結果は `unchanged`（一致）、`preview`（未適用の差分あり）、`applied`（変更）、`deferred`（起動中などのため延期）、`skipped`（未初期化など）、`error` のいずれかです。定期処理は `--quiet` を使い、実際の変更とエラーだけを出力します。

1つのプロファイルだけを確認・適用したい場合は、アプリとディレクトリを指定します。

```sh
desktop-app-themes --app zen --profile "$HOME/Library/Application Support/zen/Profiles/選んだプロファイル"
desktop-app-themes --app orca --profile "$HOME/Library/Application Support/orca/profiles/選んだプロファイル" --apply --defer-running
```

`--app`を省略するとZenを対象にします。`--app zen`／`orca`で複数プロファイルが見つかった場合は、`--profile`の指定を求めて停止します。定期同期で使用する `--app all` は全プロファイルを対象にします。

### 変更する内容

- **Zen:** ワークスペースのテーマと `zen.view.window.scheme`。タブ・フォルダ・コンテナなどを維持し、プライベート・非同期・閉じたウィンドウは変更しません。
- **Orca:** ダーク外観、Sky Copyターミナルテーマ、サイドバーの「ターミナルに合わせる」、分割線 `#3c565b`。既存のSky CopyがあればIDとメタデータを再利用し、重複登録しません。その他のテーマ、ライトテーマ、作業データ、ログイン情報を維持します。

Orcaの背景は単色です。内蔵エディタの独立した配色選択は、この構成で確認したアプリでは利用できません。

Zen／Orcaで手動変更した配色も、正常終了後にNixの配色へ戻ります。別の配色を継続利用する場合は `zen-workspaces.json`／`orca-theme.json` を編集してNixを再適用します。

### バックアップと競合対策

変更が必要な場合だけ、アプリの終了状態と対象ファイルの未変更を確認し、バックアップ後に同じディレクトリ内の一時ファイルから置換します。activationと定期同期は排他ロックで重複実行を防ぎます。アプリの内部形式が不明な場合は書き換えません。

バックアップは `${XDG_STATE_HOME:-$HOME/.local/state}/desktop-theme/backups/zen` または `orca` に保存します。`XDG_STATE_HOME` が空や相対パスなら `~/.local/state` を使います。ディレクトリは0700、ファイルは0600です。バックアップはタブや作業状態を含むため、Gitへ追加しないでください。

復元する場合は該当アプリを終了し、バックアップ内の同名ファイルを元のプロファイルへ戻します。以前の配色を継続利用したい場合は、先にNixの配色定義も変更してください。

Zen／Orcaの合成データによる21件のテストで、配色以外の保持、再適用、延期、バックアップと復元、競合拒否、排他処理などを検証しています。

## Raycastの初回設定

Raycastから正式に書き出した `Raycast-Sky-Copy.json` と `Raycast-Sky-Copy.url` を同梱しています。移行先で次を実行します。

```sh
desktop-raycast-theme
```

1. 表示された画面で **Install Theme（インポート）** を押す。
2. Sky Copyを右クリックし、**Set as Current (forced)** を選ぶ。

この初回の2操作は必要です。公開APIではテーマの無人選択に対応していません。Raycastへのログインやライセンスの確認は移行先で行ってください。

## 壁紙

`~/.local/share/desktop-theme/wallpapers/loupe-mono-dark.heic` を配布し、初回とNix内の画像データ更新時に設定します。同じ画像データで再switchしても、後から手動変更した壁紙は保持します。配布画像が更新された場合は、新しい画像に切り替えます。

配布壁紙へ明示的に戻す場合:

```sh
desktop-wallpaper --force
```

GUIセッションや接続中のディスプレイがない場合は、次回switchへ延期します。未接続のディスプレイや非表示のSpaceまでの反映は保証しません。
