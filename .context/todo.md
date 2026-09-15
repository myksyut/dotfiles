# Plan: 追加 omp — Nix管理でpiと併用し全ソースをpush

## Context

`flake.nix`（417行）はMac `miyagishoutanoMacBook-Pro`、WSL、standalone Devboxへ共通Home Manager設定を渡している。`modules/home/default.nix`（1179行）の`home.packages`には`pi-coding-agent`があり、ompは未導入。固定中のnixpkgsには`oh-my-pi`属性がないが、公式`can1357/oh-my-pi`は`packages.<system>.omp`を公開している。公式flakeの依存・ビルド定義を利用し、独自パッケージ化やnpmグローバル導入はしない。

`main`は`origin/main`より1コミット先行し、8件のstaged変更とDevbox関連ソース・文書などの未追跡ファイルがある。ユーザーは既存分を含む全pushを承認した。`.context`内の文書は保持するが、DB・セッション状態・`.pi`監査ログ・Pythonキャッシュは公開対象から除外する。秘密情報が見つかればpushを止める。

`CONTEXT.md`と`docs/adr/0001-devbox-multi-user-nix.md`はDevboxの用語・保護方針を記録している。今回の追加でその契約やFly実機の状態は変更しない。既存のClaude修復計画は`.context/todo.before-omp.md`へ保全済み。既存switch appはsudoを実行するため本セッションから起動できない。ユーザーはビルド・pushを先行し、switchを後で手動実行することを選択した。

---

## Phase 1: 公式ompのNix統合

**Why:** 既存piを壊さず、再現可能な依存固定で全Home Manager構成へ追加する。

**Test first** → `flake.nix` / `modules/home/default.nix`

- 追加前はomp input・home packageがないことを確認済み。
- 追加後にMac・WSL・Devboxのhome.packagesを評価し、ompとpi-coding-agentが共存することを検証する。

**Modify** → `flake.nix`

- `inputs.omp.url = "github:can1357/oh-my-pi"`を追加しoutputsへ受け取る。
- 共通Home Managerとstandalone Devboxの`extraSpecialArgs`へompを渡す。
- 両systemの`packages.omp`を公式packageへ接続し、個別ビルド・検証可能にする。
- 公式側のnixpkgsやRust/Bun要件を不用意に既存nixpkgsへfollowsさせない。既存inputは更新しない。

**Modify** → `flake.lock`

- ompと必要な推移依存だけを固定。既存inputの変更がないことをdiff確認。

**Modify** → `modules/home/default.nix`

- 引数ompを受け取り、`home.packages`へ`omp.packages.${pkgs.stdenv.hostPlatform.system}.omp`を追加。
- pi本体・拡張・設定・認証・シェルaliasはそのまま残す。

**Modify** → `README.md`

- ompコマンド、piとの併用、Nix更新手順、設定/認証移行を行わないことを記載。

---

## Phase 2: Integration Test + Polish

**Why:** 実際のMac構成のビルドとCLI起動を確認し、既存差分も含む公開前チェックを行う。

**Modify** → `.gitignore`

- `.pi/`、Pythonキャッシュ、`.context`のDB・DB sidecar・session-state・承認ゲート等のローカル状態を限定的に除外。文書は除外しない。削除はしない。

**Reference** → `modules/home/merge-pi-settings.test.sh`, `infra/devbox/tests/`, `infra/devbox-launcher/worker.test.mjs`

- 既存差分に対応するオフラインテストを実行。Fly・VM・課金対象は起動しない。
- 既存不具合を発見し今回の範囲で直せなければ、勝手に広範囲を改修せず報告して止める。

**Verification targets** → `.#omp`, `.#darwinConfigurations.miyagishoutanoMacBook-Pro.system`

- 編集Nixファイルを診断・整形し、個別ompビルドとMac全体ビルドを行う。
- 一時HOMEでompの`--version`・`--help`・`--smoke-test`を実行し、実認証やLLM呼び出しは行わない。
- キャッシュ設定やsandbox、秘密保護を緩和しない。公式flakeが失敗した場合は別導入方式へ無断で切り替えない。

---

## Phase 3: 全ソースのcommit・pushと手動switch引継ぎ

**Why:** ユーザー指定の全差分を安全に公開し、権限が必要な適用操作を明確に分離する。

**Reference** → 全staged差分・未追跡ソース/文書・`origin/main..HEAD`

- 公開対象の全ファイル名・差分概要を確認し、秘密情報スキャナをredact付きで使用。検出値は表示しない。
- `.envrc`等も検査する。スキャナ未提供なら固定nixpkgsのgitleaksを一時利用する。
- 未push履歴も含めて検査する。真の秘密情報があれば履歴改変やpushをせず判断を仰ぐ。
- 既存変更は維持し、既存分とomp追加を可能な範囲で意味のあるcommitへ分離。commit hookを無効化しない。
- `git diff --cached --check`、関連テスト、ビルド成功後、`git push origin main`。force push・自動merge/rebaseはしない。
- リモート先行や認証失敗時は停止して報告する。完了後にリモートHEADとの一致と残存ファイルを確認。

**Modify** → `.context/todo.md`

- 各phaseの結果と未適用状態を記録し、完了レビューを提示。
- 手動コマンド`nix run .#switch`を案内。これは内部でsudoを使うためこちらからは実行しない。ユーザー側で`command -v omp`と`omp --version`を確認してもらう。

## Critical Files

| File | Action |
| --- | --- |
| `flake.nix` | Modify（omp input、引数、package出力） |
| `flake.lock` | Modify（omp依存固定） |
| `modules/home/default.nix` | Modify（omp package追加） |
| `README.md` | Modify（併用案内） |
| `.gitignore` | Modify（ローカル生成物除外） |
| `.context/todo.md` | Modify（計画・結果） |
| `.context/todo.before-omp.md` | New（旧計画保全済み） |
| 既存staged 8ファイル・未追跡ソース/文書 | Preserve / commit・push対象 |
| `modules/home/pi.nix` | Reference（既存差分を保持） |
| `CONTEXT.md`, `docs/adr/0001-devbox-multi-user-nix.md` | Reference / 既存未追跡分をpush |

## Reusable Components (no changes needed)

- **公式omp flake** — 対応systemのpackageとinstallCheckをそのまま利用。
- **共通Home Manager構成** — 既存の全環境配線を利用。
- **darwin switch app** — ユーザー手動適用に再利用。
- **既存pi設定・認証** — 移行も初期化もしない。

## Verification

1. `nix eval`でMac/WSL/Devbox home.packagesのompとpiの共存を確認。
2. `nix build .#omp --no-link --print-out-paths`が成功し、隔離HOMEでCLI smoke testが成功。
3. `nix build .#darwinConfigurations.miyagishoutanoMacBook-Pro.system --no-link`が成功。新規ソースはflakeが参照できるよう安全確認後stageする。
4. `bash modules/home/merge-pi-settings.test.sh`、`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/devbox/tests -v`、`node --test infra/devbox-launcher/worker.test.mjs`が成功。
5. 変更Nixファイルのnixfmt/statix/deadnix、`git diff --cached --check`、redact付き秘密検査が合格。
6. `git push origin main`成功後、`git ls-remote origin refs/heads/main`がローカルHEADと一致。
7. switchは未実施として報告し、ユーザーへ手動適用を引き継ぐ。

## 実行結果

- Phase 1: 完了。公式omp 18.2.0（commit `5663497617194e7c06310c18bf6ee31f68dc7725`）を固定。既存inputの固定内容は変更なし（lock内部の一部node名のみ採番変更）。
- Phase 2: 完了。Mac・WSL・Devboxの評価でpi-coding-agent 0.84.1とomp 18.2.0が共存。
- ompのビルドと隔離HOMEでのversion/help/smoke-testが成功。初回ビルドのツール時間制限後に再実行して完了。
- Mac全体ビルド成功: `/nix/store/9wssnw7gih5334miznfykbhkwypw7d6l-darwin-system-26.11.15abb8c`。
- Piマージテスト、Python 167件、Worker 14件が成功。変更Nixファイルの診断・nixfmt・statix・deadnixは合格。
- gitleaksによる作業ツリー全体と未pushの既存1コミットの検査で検出なし。ログ・DB・Pythonキャッシュ等はgitignoreにより保持したまま除外。
- 既存zshのinitExtra系非推奨警告あり。今回変更せず、ビルド成功を確認。
- Phase 3: commit・push待ち。switchは未実施で、push後にユーザーが`nix run .#switch`を手動実行する。

## Grill checkpoint

Summary: oh-my-piを公式Nix flakeで既存piと併用導入し、既存分を含む全ソース・文書を検査後にorigin/mainへpushする。switchはpush後にユーザーが手動実行する。

Decisions:

- ompはoh-my-piを指す。共通Home Managerへ追加しMac・WSL・Devboxで利用可能にする。
- 既存piは残し、設定・認証・拡張の移行は行わない。
- 既存変更と未pushコミットを含む全ソース・文書をpushする。秘密情報・ログ・DB・キャッシュ・ローカル状態は除外する。
- ビルド・検証・pushを先行し、sudo必須のswitchはユーザーが後で手動実行する。

Open questions: none
