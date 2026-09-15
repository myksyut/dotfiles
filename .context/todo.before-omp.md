# Plan: 修復 Claude Desktop — 設定を維持した公式版更新

## Context

`/Applications/Claude.app` は1.1.4498で、macOS 26.6.2上の起動時に失敗している。`~/Library/Logs/Claude/launch-failure.err` はNodeの`formatProperty`から`TypeError: Cannot read properties of undefined (reading 'value')`を記録し、`main.log`にも同様の起動失敗がある。署名検証は正常。根本原因は未確定であり、設定破損と断定しない。Homebrewの配布メタデータで確認した公式版1.52386.4への本体更新を最小の修復として試す。ClaudeはHomebrew管理ではなく、Nix設定も変更しない。CONTEXT.mdとdocs/adr/0001-devbox-multi-user-nix.mdはDevbox関連で、本修復には適用対象がない。

---

## Phase 1: 公式配布物の検証と退避（完了）

**Why:** 検証した配布物だけを使用し、旧アプリとローカルデータを復旧可能にする。

**Reference** → Homebrew cask `claude` のメタデータ

- URL: `https://downloads.claude.ai/releases/darwin/universal/1.52386.4/Claude-5078b3dcabffbffb717315a5f9a0e552c9ca54d6.zip`
- SHA-256: `7f400621323f71c1a3c9c149563cfcf75e710a50d635aecada8b2510f0140648`

**New file / directory** → `~/Library/Caches/claude-repair-<timestamp>/`

- ZIPをダウンロード・SHA-256検証後に展開する。署名、Bundle ID、Team ID `Q6L2SF6YDW`を旧アプリと照合し、Gatekeeper評価を確認する。
- Claudeを通常終了する。停止できなければユーザーへ終了を依頼し、強制終了しない。

**New file / directory** → `~/Library/Application Support/Claude-repair-backup-<timestamp>/`

- 終了後に既存の`Claude`データディレクトリ（約366MB）と存在するClaudeのplistをローカル退避する。内容や認証情報は出力しない。
- 旧アプリはこの退避先へ移動する。削除はしない。

---

## Phase 2: 本体置換・起動確認（完了）

**Why:** 設定リセットを避けた更新だけで修復できるか、実際の起動で確認する。

**Modify** → `/Applications/Claude.app`

- 検証済みアプリを`ditto`で配置し、配置後にも署名とバージョンを確認する。
- Claudeを起動し、プロセスの継続、起動後の限定したログ、ユーザーの画面確認で結果を判定する。古いエラーログと新しいエラーを区別する。
- 失敗が続く場合は初期化やセキュリティ保護無効化をせず、追加調査の判断をユーザーに確認する。
- 権限不足の場合は停止して手動操作を案内する。sudoは使用しない。

## Critical Files

| File | Action |
| --- | --- |
| `/Applications/Claude.app` | 退避後に更新 |
| `~/Library/Caches/claude-repair-<timestamp>/` | New（配布物・展開先） |
| `~/Library/Application Support/Claude-repair-backup-<timestamp>/` | New（旧本体・データ退避） |
| `~/Library/Application Support/Claude/` | バックアップ元、削除・初期化しない |
| `~/Library/Logs/Claude/main.log` | Reference（起動確認） |
| `~/Library/Logs/Claude/launch-failure.err` | Reference（障害時刻の確認） |

## Reusable Components (no changes needed)

- **ditto / codesign / spctl** — macOS標準のコピーと署名・実行許可検証。
- **Claude既存設定** — 再設定せず維持する。更新後のアプリによる通常のデータ移行はあり得る。

## Verification

1. `shasum -a 256`が公開メタデータと一致する。
2. `codesign --verify --deep --strict`と`spctl --assess --type execute`が成功する。
3. Info.plistのバージョン、Bundle ID、署名Team IDを確認する。
4. 起動後30秒程度待ち、プロセス・新規ログ・ユーザーの画面確認で起動失敗の解消を確認する。
5. データ退避の存在を確認し、設定初期化やNix設定変更がないことを確認する。

## 実行結果

- 公式版1.52386.4のSHA-256、署名、Team ID、Gatekeeper評価に合格。
- 通常終了できなかった旧プロセスは、ユーザーが手動で終了。
- 退避先: `~/Library/Application Support/Claude-repair-backup-20260913185305.k1mJ7G/`（旧アプリと366MBのデータ）。
- `/Applications/Claude.app`を更新し、30秒後も稼働。旧launch-failure.errは更新されず、ログイン処理まで進行。
- ユーザーから「正常に開いた」と確認済み。設定初期化・Nix設定変更なし。

## Grill checkpoint

Summary: Claude Desktopの起動失敗に対し、設定を削除せず公式の新しい版へ本体更新して起動を検証する。

Decisions:

- ユーザーは本体を更新する方針を選択した。
- 旧アプリとローカルデータを退避し、Nix設定は変更しない。
- 設定初期化、強制終了、セキュリティ保護の無効化、sudoは行わない。

Open questions: none
