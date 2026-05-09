# dotfiles

`myksyut` の macOS dotfiles。 **nix-darwin + home-manager + flakes** で宣言的に管理。

> 現状は `nix-config` (`~/.config/nix-config`) のみ。 ghostty/zed 等は今後追加予定。

## 使い方の早見表

| コマンド | 何をする |
|---|---|
| `nix run .#switch` | `sudo darwin-rebuild switch` + nom (進捗カラー化) |
| `nix run .#build` | ビルド計画を確認（適用しない） |
| `nix run .#update` | `flake.lock` を最新に更新 |
| `nix run .#fmt` / `nix fmt` | Nix ファイルを treefmt で整形 |
| `nix flake check` | formatter + pre-commit の検証 |
| `cd ~/.config/nix-config` | direnv が devShell を起動、`.git/hooks/pre-commit` を自動 install |

## ディレクトリ構造

```
~/.config/nix-config/
├── flake.nix              # inputs/outputs + apps/checks/devShell
├── flake.lock
├── modules/
│   ├── darwin/default.nix # システム設定
│   └── home/default.nix   # ユーザー設定 (home-manager)
├── .envrc                 # use flake (direnv 連携)
├── .gitignore
└── README.md
```

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

## 初期セットアップ（参考）

新しい Mac で復元する場合の手順メモ:

```bash
# 1. upstream Nix インストール
curl -sSfL https://artifacts.nixos.org/nix-installer | sh -s -- install --enable-flakes

# 2. このリポジトリを clone
git clone https://github.com/myksyut/dotfiles ~/.config/nix-config

# 3. ホスト名・ユーザー名を flake.nix の username/hostname に合わせて編集

# 4. 初回適用
cd ~/.config/nix-config
sudo nix run nix-darwin -- switch --flake .#$(hostname -s)
```
