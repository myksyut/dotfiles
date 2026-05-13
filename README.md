# dotfiles

`myksyut` の macOS / Windows(WSL) dotfiles。 **nix-darwin + NixOS-WSL + home-manager + flakes** で宣言的に管理。

> 共通の `modules/home` を両プラットフォームで共有し、`pkgs.stdenv.isDarwin` で macOS 専用 (terminal-notifier / ghostty / zed-editor 等) を切り分ける。

## 使い方の早見表

`nix run .#switch` 等は **実行中の OS の system 用 app を自動で解決** する (macOS なら aarch64-darwin、WSL なら x86_64-linux)。

| コマンド | macOS での動作 | WSL での動作 |
|---|---|---|
| `nix run .#switch` | `sudo darwin-rebuild switch` + nom | `sudo nixos-rebuild switch` + nom |
| `nix run .#build`  | darwin configuration をビルド（適用しない） | nixos configuration をビルド（適用しない） |
| `nix run .#update` | `flake.lock` を最新に更新 | 同左 |
| `nix run .#fmt` / `nix fmt` | Nix ファイルを treefmt で整形 | 同左 |
| `nix flake check` | formatter + pre-commit の検証 | 同左 |
| `cd ~/.config/nix-config` | direnv が devShell を起動、`.git/hooks/pre-commit` を自動 install | 同左 |

## ディレクトリ構造

```
~/.config/nix-config/
├── flake.nix              # inputs/outputs + apps/checks/devShell (darwin + wsl)
├── flake.lock
├── modules/
│   ├── darwin/default.nix # macOS システム設定 (nix-darwin)
│   ├── nixos/default.nix  # WSL システム設定 (NixOS-WSL)
│   └── home/default.nix   # ユーザー設定 (home-manager, 両 OS 共通)
├── pkgs/                  # `callPackage` 用のローカル derivation
├── .envrc                 # use flake (direnv 連携)
├── .gitignore
└── README.md
```

### Windows (WSL2 / NixOS-WSL) 対応

`darwinConfigurations.<hostname>` と並列に `nixosConfigurations.<hostname>` を提供する。

| 概念 | macOS | Windows (WSL) |
|---|---|---|
| system | `aarch64-darwin` | `x86_64-linux` |
| 既定 hostname | `miyakinoMacBook-Air` | `miyaki-wsl` |
| 外部 input | `nix-darwin` | `nixos-wsl` (NixOS-WSL) |
| switch コマンド | `darwin-rebuild` | `nixos-rebuild` |

> 新規マシンでの 0 → 動く までの完走チェックリストは **[SETUP.md](SETUP.md)** にある。

## 導入ツール解説

### Nix 開発支援

| パッケージ | 解説 |
|---|---|
| **nil** | Nix の LSP。Zed/VSCode/Helix で `.nix` を開くと補完・参照ジャンプ・ホバーが動く |
| **nixfmt** | Nix 公式フォーマッタ (RFC style)。treefmt 経由・単体どちらでも使用可 |
| **statix** | Nix のリンター。anti-pattern を検出（例: `programs.x = ...; programs.y = ...;` の繰り返し → `programs = { x = ...; y = ...; }` を提案） |
| **deadnix** | デッドコード検出。未使用の `let` バインディングや関数引数を発見 |
| **nix-output-monitor (nom)** | `nix build` の進捗を DAG 形式でカラフル可視化。`nix run .#switch` 内部で `|& nom` を使用 |
| **nix-index-database** | nixpkgs の binary→package 逆引きインデックス（週次更新キャッシュ）。未インストールコマンドを叩くと提案が出る |
| **comma (`,`)** | `, foo` で foo を一時的に `nix shell nixpkgs#foo` で実行（インストール不要） |

### CLI essentials

| パッケージ | 解説 |
|---|---|
| **ripgrep (rg)** | `grep` の Rust 代替。`.gitignore` を尊重、桁違いに高速。`rg pattern` |
| **fd** | `find` の代替。`fd pattern dir` のシンプル構文、カラー出力 |
| **fzf** | 汎用 fuzzy finder。Ctrl+T (file), Ctrl+R (history), Alt+C (cd) |
| **bat** | `cat` の代替。シンタックスハイライト + `git diff` 表示 + ページャ |
| **eza** | `ls` の代替。アイコン・色・ツリー表示・git status integration |
| **jq** | JSON 処理の標準。`curl ... \| jq '.data[0]'` |
| **zoxide (z)** | `cd` の学習版。一度行った場所に `z foo` の部分文字列でジャンプ可 |
| **atuin** | shell history を sqlite で管理。Ctrl+R が fuzzy 検索、デバイス間同期も任意 |
| **tealdeer (tldr)** | 実用例ベースの簡易 man。`tldr tar` で要点だけ |

### Git 周り

| パッケージ | 解説 |
|---|---|
| **gh** | GitHub CLI。`gh repo create`, `gh pr create`, `gh issue list` 等 |
| **lazygit** | TUI Git クライアント。rebase/cherry-pick/stage を h/j/k/l でサクサク |
| **delta** | `git diff` のページャ。シンタックスハイライト + サイドバイサイド表示 |
| **gwq** | Git worktree マネージャ（fuzzy finder 連携）。`gwq add <branch>` で `~/worktrees/<host>/<owner>/<repo>/<branch>` に worktree を作成。詳細は[Worktree 並列開発](#worktree-並列開発) |

### 開発ユーティリティ

| パッケージ | 解説 |
|---|---|
| **just** | Makefile 代替の軽量タスクランナー。シンプル構文、引数渡しが楽 |
| **watchexec** | ファイル変更で再実行。`watchexec -e py pytest` で .py 変更時に pytest |
| **hyperfine** | コマンドベンチマーカー。warmup/runs 指定で統計的に valid な計測 |
| **xh** | HTTP クライアント (HTTPie の Rust 版)。`xh post api/foo name=bar` |
| **direnv** | ディレクトリごとの env 管理。`.envrc` を `cd` で自動 source |
| **nix-direnv** | direnv の Nix 拡張。`use flake` をキャッシュで高速化 |

### UNIX 代替 (Rust 製)

| パッケージ | 解説 |
|---|---|
| **dust** | `du -sh` の代替。ディレクトリサイズを縦棒グラフで可視化 |
| **duf** | `df` の代替。マウントポイントを色付きテーブル表示 |
| **procs** | `ps` の代替。色付き・ツリー表示・検索・TCP統合 |

### Python

| パッケージ | 解説 |
|---|---|
| **uv** | パッケージ + venv + バージョン管理の統合 (Rust 製、爆速)。`uv add foo`, `uv python install 3.13` |
| **ruff** | linter + formatter。black/isort/flake8 を統合、100倍高速 |
| **pyright** | 型 LSP (Microsoft 製)。Zed/VSCode で型チェック・補完 |
| **mypy** | 厳密な型チェッカ。CI で使うことが多い |
| **pyenv** | 古典的なバージョンマネージャ。`~/.pyenv/versions/*` 互換維持用、新規は uv 推奨 |

### ランタイム / アプリ

| パッケージ | 解説 |
|---|---|
| **tmux** | ターミナル多重化。home-manager 管理で `~/.config/tmux/tmux.conf` 自動生成 |
| **deno** | TypeScript ランタイム (Rust 製)。zeno.zsh の必須依存 |
| **claude-code** | Anthropic Claude Code CLI（バイナリ名: `claude`） |

## 動作確認サンプル

```bash
# 未インストールコマンドを叩くと提案が出る
cowsay
# => The program 'cowsay' is currently not installed. It is provided by ...

# , (comma) で一時的にバイナリ実行 (パッケージは入れない)
, hello
# => Hello, world!

# zoxide で頻出ディレクトリへジャンプ
z config
# => ~/.config/nix-config

# uvx で隔離環境で Python ツール起動
uvx ipython
```

## Worktree 並列開発

複数ブランチを別ディレクトリで同時に開発するための設定。 **gwq** + **tmux popup** + **fzf** で「ブランチ選択 → worktree 作成 → 専用 tmux セッションへ移動」がワンキーで完結する。

### 構成要素

| 要素 | 場所 | 役割 |
|---|---|---|
| `gwq` バイナリ | `pkgs/gwq/default.nix` (`buildGoModule`) | worktree の作成・列挙・削除 |
| 切替スクリプト | `~/.config/tmux/worktree-switcher.sh` (Nix 管理) | fzf UI + tmux セッション制御 |
| tmux キーバインド | `programs.tmux.extraConfig` の `bind-key w` | popup でスクリプトを呼び出す |
| gwq グローバル設定 | `~/.config/gwq/config.toml` (Nix 管理) | `repository = "**"` で全 repo 共通の copy_files / setup_commands |

### 操作フロー (`prefix + w`)

1. tmux 内で `prefix` (デフォルト `C-b`) → `w` を押すと、現在ペインの `pwd` を作業ディレクトリにした popup が開く
2. fzf に以下が混在表示される（カテゴリプレフィクスで識別）
   - `[wt]   <branch>` — 既存 worktree（gwq 管理下）
   - `[local]  <branch>` — ローカルブランチ（worktree 未作成）
   - `[remote] <branch>` — リモートブランチ（worktree 未作成、ローカル追跡なし）
3. 選択後の挙動
   - `[wt]` を選択 → そのパス向けの tmux セッションへ `switch-client`（無ければ `new-session -d`）
   - `[local]/[remote]` を選択 → `gwq add <branch>` で worktree を作成し、続けて tmux セッションへ移動
4. tmux セッション名は `<repo>__<branch>`（`/`, `:`, `.` は `_` にサニタイズ）。`session-color.sh` フックでセッション色も自動付与

### worktree の保存先と命名

```
~/worktrees/
└── github.com/
    └── <owner>/
        └── <repo>/
            ├── feature-x/   # gwq add feature-x
            └── bugfix-y/    # gwq add bugfix-y
```

命名は `naming.template = "{{.Host}}/{{.Owner}}/{{.Repository}}/{{.Branch}}"` で制御（gwq デフォルト）。`worktree.basedir = "~/worktrees"` も同じく gwq デフォルト。

### untracked ファイルの自動コピー

worktree は git tracked ファイルしか持っていかないので、`.env` 等は新 worktree に存在しない。これを補うため、`~/.config/gwq/config.toml` に **全リポジトリ共通の catch-all** を入れている。

```toml
[[repository_settings]]
repository = "**"
copy_files = [
  ".env", ".env.*",
  ".envrc", ".envrc.local",
  ".tool-versions", ".python-version", ".node-version",
  ".claude/settings.local.json",
]
setup_commands = [
  "if [ -f .envrc ]; then direnv allow .; fi",
]
```

- `gwq add` 時にメイン worktree から該当ファイルを **存在するものだけ** 新 worktree にコピー
- 続いて `setup_commands` を `sh -c` で順に実行（`.envrc` があれば `direnv allow`）
- パターン:
  - `**` は doublestar グロブの全マッチ。
  - `findRepoSetting` は **先頭一致** で返すため、特定 repo 用の override を入れる場合は `**` より上に並べる。
  - 個別 repo の `<repo>/.gwq.toml` に `repository = "**"` を書くと、その repo に限り global の `**` を完全置換できる（初回 trust prompt が出る）。

### よく使う gwq コマンド

| コマンド | 役割 |
|---|---|
| `gwq add <branch>` | 既存ブランチの worktree を作成 |
| `gwq add -b <branch>` | 新規ブランチを作って worktree を作成 |
| `gwq list` / `gwq ls` | 現在 repo の worktree を一覧 |
| `gwq list -g` | 全 repo の worktree を一覧（base dir 配下） |
| `gwq get <pattern>` | worktree のパスを取得（`cd $(gwq get foo)` で移動） |
| `gwq remove <pattern>` | worktree を削除（インタラクティブ選択も可） |
| `gwq status` | 全 worktree の git status をまとめて表示 |
| `gwq exec <pattern> -- <cmd>` | 指定 worktree でコマンド実行（`gwq exec feature -- pnpm test`） |

### tmux セッション周り

- セッション一覧: `prefix + s`（tmux 標準）
- 別セッションへ移動: 上記のリスト or `tmux switch-client -t <name>`
- セッション削除: `tmux kill-session -t <name>` （worktree 自体は残る、消すなら `gwq remove`）
- popup を閉じるだけ: `Esc` または `q`

### トラブルシューティング

- **popup が出ない / `prefix + w` が無反応** → `tmux source-file ~/.config/tmux/tmux.conf` で再読込。`tmux list-keys | grep popup` で `bind-key w` が登録されているか確認。
- **`gwq not found in PATH`** → `which gwq` を確認。新規 tmux セッションだと PATH が反映されてないことがあるので、`tmux kill-server` で全セッション切ってから再起動。
- **`gwq add <branch>` が失敗** → 既に同名 worktree がある場合は `-f` で上書き、または `gwq remove` で消してから。リモートブランチ名は `origin/` を除いた形で渡す（スクリプトは自動で剥がす）。
- **tmux セッションが残り続ける** → 終わった worktree のセッションは `tmux kill-session -t <session>` で個別 kill。一括するなら `tmux ls -F '#S' | xargs -n1 tmux kill-session -t`。

## キーボード統一 (kanata)

NuPhy Air75 V3 を **Mac モードのまま macOS / Windows 両方で使い回す** 前提で、kanata に
両 OS の差分を吸収させて Cmd ファーストの体験を統一する。

### 設計

- `modules/kanata/mac.kbd` — Mac はネイティブで Cmd ファースト。CapsLock → Esc/Ctrl だけ。
- `modules/kanata/win.kbd` — Windows 側で `LMeta ↔ LCtrl` を swap し、物理 Cmd 位置が
  `Ctrl+C` を送るようにして Mac と同じ親指コピペ感覚にする。CapsLock も Mac と同期。

| 物理ラベル (Mac mode) | scancode | macOS 送出 | Windows 送出 (kanata 経由) |
|---|---|---|---|
| Ctrl (左下) | `lctl` | Ctrl | **Win** (start menu 等) |
| Opt | `lalt` | Opt | Alt |
| Cmd (左親指) | `lmet` | Cmd | **Ctrl** ← copy/paste の主役 |
| Cmd (右親指) | `rmet` | Cmd | **Ctrl** |
| Opt (右) | `ralt` | Opt | Alt |
| Caps | `caps` | tap=Esc / hold=Ctrl | 同左 |

### Nix 管理範囲

| 担当 | macOS | Windows ホスト |
|---|---|---|
| kanata 本体 install | `modules/darwin/default.nix` の `environment.systemPackages` | `winget install jtroo.kanata` (手動) |
| HID driver | `homebrew.casks = [ "karabiner-elements" ]` (DriverKit のみ流用) | Interception driver (手動 install + 再起動) |
| 自動起動 | `launchd.daemons.kanata` (root) | タスクスケジューラ (管理者権限) |
| kbd ファイル | `environment.etc."kanata/mac.kbd"` 経由で `/etc/kanata/mac.kbd` | `cp .../win.kbd /mnt/c/Users/<you>/kanata.kbd` (手動) |
| 初回権限承認 | 入力監視許可 + driver activation (手動) | UAC + driver install 時 (手動) |

初回権限付与・install 手順は **[SETUP.md](SETUP.md)** のセクション A-6 / B-5 を参照。

### reload / 編集ワークフロー

`.kbd` を編集したら:

- Mac: `sudo launchctl kickstart -k system/org.nixos.kanata` (Nix 経由で `/etc/kanata/mac.kbd` は自動更新)
- Windows: タスクマネージャで `kanata.exe` を kill して再起動 (win.kbd は手動コピー必要)

ログ: `tail -f /var/log/kanata.log` (Mac)

## 開発ワークフロー

1. `cd ~/.config/nix-config` (direnv が devShell 起動)
2. `flake.nix` / `modules/*` を編集
3. `nix run .#fmt` で整形
4. `nix run .#build` でビルド計画確認
5. `nix run .#switch` で適用
6. `git commit` (pre-commit が自動で treefmt/statix/deadnix を実行)

## ヒント / Tips

- **`ipython` を一時的に使う**: `uvx ipython` で隔離環境内に ipython をインストールして起動（global を汚さない）
- **`uv` で Python venv**: `uv venv && uv add foo` でプロジェクトごとの venv 管理
- **direnv で flake devShell 自動適用**: プロジェクト直下に `.envrc` (`use flake`) と `flake.nix` を置く
- **command-not-found index 更新**: 週次ビルドのインデックスは `nix run .#update && nix run .#switch` で更新

## 今後の追加予定

### システム / ユーザーパッケージ
- [ ] ghostty (`programs.ghostty` で設定管理)
- [ ] zed (`programs.zed-editor` で設定管理)

### シェル環境の整理
- [ ] `~/.zshrc` の home-manager 管理化を検討
- [ ] zeno.zsh / pyenv 設定を home-manager で再宣言

### プロジェクトごとの devShell 運用
- 各プロジェクトに `flake.nix` を置いて言語別環境を定義
- `direnv` (`use flake`) で `cd` 時に自動有効化

## 初期セットアップ

新規マシン (Mac / Windows-WSL 双方) に 0 から導入する完走チェックリスト・初回権限付与・
トラブルシューティングは **[SETUP.md](SETUP.md)** にまとめてある。
