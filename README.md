# nix-config

macOS (aarch64-darwin) の開発環境を **nix-darwin + home-manager + flakes** で宣言的に管理。

## 適用

```bash
sudo darwin-rebuild switch --flake ~/.config/nix-config#miyakinoMacBook-Air
```

## 構造

```
~/.config/nix-config/
├── flake.nix       # nix-darwin + home-manager のエントリーポイント
└── flake.lock      # 入力の固定バージョン (git管理する)
```

## ヒント / Tips

- **ipython を一時的に使う**: `uvx ipython` で隔離環境内に ipython をインストールして起動（global を汚さない）
- **uv で Python venv**: `uv venv && uv add foo` でプロジェクトごとの venv 管理
- **direnv で flake devShell 自動適用**: プロジェクト直下に `.envrc` (`use flake`) と `flake.nix` を置く

## 今後の追加予定

### システム / ユーザーパッケージ
- [ ] claude-code
- [ ] ghostty (`programs.ghostty` で設定管理)
- [ ] zed (`programs.zed-editor` で設定管理)
- [ ] direnv (`programs.direnv.enable` + `nix-direnv`)
- [ ] 各種 CLI (ripgrep, fd, fzf, bat, eza, jq など)

### シェル環境の再宣言化
- [ ] zeno.zsh を home-manager 経由で再導入
  - 現状: `~/.zshrc` の bindkey 3行を一時的にコメントアウト中
- [ ] pyenv の代替を検討（python3 / uv / pyenv のいずれかを home-manager 管理）
  - 現状: `~/.zshrc:108` `~/.zprofile:1` で `command not found: pyenv` エラー

### プロジェクトごとの devShell 運用
- 各プロジェクトに `flake.nix` を置いて言語別環境を定義
- `direnv` (`use flake`) で `cd` 時に自動有効化
- 例: `nix develop` で入る or direnv で透過的に
