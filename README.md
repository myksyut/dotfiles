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

## 入っているもの

### Nix 開発支援
- **LSP / format / lint**: `nil`, `nixfmt`, `statix`, `deadnix`
- **進捗表示**: `nix-output-monitor` (nom)
- **コマンド逆引き**: `nix-index-database` + `comma` (`,foo` で一時実行)

### CLI essentials
- **検索**: `ripgrep` (rg), `fd`, `fzf`
- **整形・表示**: `bat`, `eza`, `jq`
- **ナビ・履歴・docs**: `zoxide` (z), `atuin` (Ctrl+R), `tealdeer` (tldr)

### Git 周り
- `gh`, `lazygit`, `delta`

### 開発ユーティリティ
- `just`, `watchexec`, `hyperfine`, `xh`
- `direnv` + `nix-direnv` (`use flake` で自動有効化)

### UNIX 代替 (Rust 製)
- `dust` (du), `duf` (df), `procs` (ps)

### Python
- `uv`, `ruff`, `pyright`, `mypy`, `pyenv`

### ランタイム / アプリ
- `tmux` (home-manager 管理、`~/.config/tmux/tmux.conf` 自動生成)
- `deno` (zeno.zsh の依存)
- `claude-code` (バイナリ名: `claude`)

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
