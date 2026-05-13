# SETUP

新しい Mac / Windows(WSL) に **このリポジトリをそのまま適用して動かす** ためのチェックリスト。
原則として上から順に潰せば完走できる構成にしてある。README は機能解説、SETUP.md は手順
書、と棲み分けて二重メンテにならないようにする。

---

## 0. 前提

- GitHub にアクセスできる
- 管理者権限 (Mac: `sudo` / Windows: 管理者 PowerShell) が叩ける
- 既存ホスト名・ユーザー名:

  | scope | 値 | flake.nix の変数 |
  |---|---|---|
  | macOS host | `miyakinoMacBook-Air` | `darwinHostname` |
  | WSL host | `miyaki-wsl` | `wslHostname` |
  | ユーザー | `miyakishota` | `username` |

  異なる環境では `flake.nix` 冒頭の `let` ブロックを書き換えてから switch する。

---

## A. macOS — 新規 / 復元

### A-1. Nix 本体の install

```bash
curl -sSfL https://artifacts.nixos.org/nix-installer | sh -s -- install --enable-flakes
# 新規ターミナルを開き直して PATH 反映を確認
nix --version
```

### A-2. リポジトリを clone

```bash
git clone https://github.com/myksyut/dotfiles ~/.config/nix-config
cd ~/.config/nix-config
```

### A-3. (必要なら) hostname / username を編集

`scutil --get LocalHostName` で hostname を確認し、`flake.nix` の `darwinHostname` と
合わなければ書き換える。

### A-4. 初回適用

`nix-darwin` 本体が未 install のため、初回だけ `nix run nix-darwin -- switch` で bootstrap する。

```bash
sudo nix --extra-experimental-features 'nix-command flakes' \
  run nix-darwin -- switch --flake .#$(scutil --get LocalHostName)
```

以後は `nix run .#switch` でも `darwin-rebuild switch --flake .` でも OK。

### A-5. Homebrew が未 install の場合

`homebrew.enable = true` は管理だけ宣言するので、Homebrew 自体は別途入れる:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

入れ直したら `nix run .#switch` をもう一度。ghostty / karabiner-elements の cask が install される。

### A-6. kanata の初回権限付与 (重要)

`launchd.daemons.kanata` は登録済みだが、macOS の権限承認は手動。以下を **順番に** やる。

1. **Karabiner-DriverKit-VirtualHIDDevice を activate**
   - `/Applications/Karabiner-Elements.app` を起動
   - ダイアログに従って「システム拡張を有効化」を許可 (要再起動の場合あり)
   - driver が動き始めたら Karabiner-Elements の `Settings > General > Karabiner-Elements` の **"Launch at login" / "Background services"** を **OFF** にする (kanata と HID 取り合いになるため)

2. **kanata に入力監視を許可**
   - システム設定 > プライバシーとセキュリティ > 入力監視
   - `+` ボタン → `Cmd+Shift+G` → `/run/current-system/sw/bin/kanata` を選択 → チェックを入れる

3. **daemon を再起動して反映**
   ```bash
   sudo launchctl kickstart -k system/org.nixos.kanata
   tail -f /var/log/kanata.log    # "entering the processing loop" が出れば成功
   ```

### A-7. 動作確認

```bash
# CapsLock を押して Esc が送られるか
# (terminal で `cat` を起動して Caps を押すと何も表示されないが、tap を hold に変えると Ctrl になる)

# flake check が通るか
nix flake check
```

---

## B. Windows — 新規 (WSL2 + NixOS-WSL)

WSL 内の Linux 環境を Nix で宣言的に管理する。GUI / キーボードイベントは **Windows ホストが
握っている** ので、kanata は WSL 内ではなく Windows 側に別途常駐させる (B-5)。

### B-1. WSL2 自体を有効化 (Windows 10 21H2+ / Windows 11)

PowerShell (管理者) で:

```powershell
wsl --install --no-distribution
# 再起動を促されたら従う
wsl --set-default-version 2
wsl --version    # 2.x になっていることを確認
```

### B-2. NixOS-WSL distro を install

```powershell
# 最新 release から nixos-wsl.wsl をダウンロード
#   https://github.com/nix-community/NixOS-WSL/releases
wsl --install --from-file .\nixos-wsl.wsl
```

起動すると `nixos@<hostname>` の shell に入る。デフォルトユーザーは `nixos`。

### B-3. ユーザーを `miyakishota` に合わせる

flake.nix が `username = "miyakishota"` 前提なので、初回だけ手動でユーザーを作って
切り替えるか、flake.nix の `username` を `nixos` 等に書き換える。前者を推奨:

```bash
# nixos ユーザーで実行
sudo useradd -m -G wheel miyakishota
sudo passwd miyakishota
# 一度 WSL を抜けて default user を切り替え:
exit
```

```powershell
# Windows PowerShell から
wsl -d NixOS -u miyakishota
```

### B-4. リポジトリを clone して switch

```bash
# WSL の miyakishota shell 内で
git clone https://github.com/myksyut/dotfiles ~/.config/nix-config
cd ~/.config/nix-config

# wslHostname が `miyaki-wsl` 以外なら flake.nix を編集

# 初回適用 (まだ nix flake 拡張が off の可能性があるので明示)
nix --extra-experimental-features 'nix-command flakes' \
  run .#switch
```

完了すると default shell が zsh になり、`gwq` や `nix run .#switch` 等が使えるようになる。

### B-5. Windows ホスト側に kanata を install (キーボード統一)

WSL 内では Linux の HID は触れないので、Windows ホスト側で常駐させる。

```powershell
# 1. kanata 本体
winget install jtroo.kanata
#   または scoop install kanata

# 2. Interception driver を install (要再起動)
#   https://www.interception.cc/ から interception.zip を取得
cd <展開先>
.\install-interception.exe /install
#   reboot
```

```bash
# 3. WSL から win.kbd を Windows 側にコピー
cp ~/.config/nix-config/modules/kanata/win.kbd /mnt/c/Users/<you>/kanata.kbd
```

```powershell
# 4. テスト起動 (管理者 PowerShell)
kanata.exe --cfg C:\Users\<you>\kanata.kbd
# Ctrl+C で停止。
# Cmd 位置 (LMeta) を押した状態で C を押して clipboard コピーが効けば成功。
```

### B-6. Windows kanata の自動起動

タスクスケジューラに登録するのが手軽:

1. `taskschd.msc` を開く
2. タスク作成 → トリガー: 「ログオン時」 → 操作: `kanata.exe --cfg C:\Users\<you>\kanata.kbd`
3. 全般タブで **「最上位の特権で実行する」** にチェック (interception driver には管理者権限が要る)
4. 「ユーザーがログオンしているかどうかにかかわらず実行する」は OFF (ログオン後で OK)

### B-7. 動作確認

```bash
# WSL 内で
nix flake check    # 両 system 通れば設定として OK
which gwq          # ~/.nix-profile/bin/gwq 等が返ること
```

---

## C. 更新ワークフロー (両 OS 共通)

```bash
cd ~/.config/nix-config
git pull
nix run .#update    # flake.lock を更新
nix run .#switch    # 反映
```

kbd を編集した直後の reload:

- Mac: `sudo launchctl kickstart -k system/org.nixos.kanata`
- Windows: タスクマネージャで `kanata.exe` を kill → タスクスケジューラから再起動 (or 再ログオン)

---

## D. トラブルシューティング

| 症状 | 対処 |
|---|---|
| `darwin-rebuild: command not found` | A-4 の bootstrap が未実施。`sudo nix run nix-darwin -- switch --flake .#$(scutil --get LocalHostName)` を実行 |
| `nix run .#switch` が `sudo` で詰まる | `modules/{darwin,nixos}/default.nix` の sudoers ルールがまだ反映されていない。初回は素の `sudo` パスワードを入力すれば次回以降は不要 |
| kanata daemon が起動しない (Mac) | `tail /var/log/kanata.log` を確認。"IOHIDDevice open failed" は **入力監視未許可**、"VirtualHIDDevice not running" は **Karabiner driver 未承認** が多い |
| Cmd+C 等が効かない (Windows) | kanata.exe が管理者権限で動いていない可能性。タスクスケジューラの「最上位の特権で実行」を確認 |
| NixOS-WSL で `nixos-rebuild` がパスワードを要求 | `security.sudo.extraRules` 反映前なので、初回は普通に sudo パスワードを入力 |
| flake check で `wslu has been removed` | nixpkgs 上の retirement。`modules/nixos/default.nix` の `environment.systemPackages` から消す (元から外してある) |
| stash@{0} が残っている | merge 前に退避した WIP。HEAD に吸収済みなので `git stash drop` で安全に削除 |

---

## E. クリーンアップ

不要になった worktree やブランチを片付ける:

```bash
git worktree list
git worktree remove <path>
git branch -d <branch>
```
