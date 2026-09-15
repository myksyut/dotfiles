# Plan: Drop agent-pi built-in viewers, route everything through Plannotator

## Decision

前回の「show_plan / show_spec は残して bridge、board / chat / cleanup / report はそのまま」は中途半端。
**document / review 系の内臓 HTTP Viewer を消して、表示・承認は全部 Plannotator に寄せる。**

- 内臓ブラウザ GUI（`createServer` + `*-html.ts`）を捨てる
- Plannotator の event API を唯一のレビュー UI にする
- フォールバックで内臓 Viewer を開かない（Plannotator が無いなら明確に失敗）
- `AGENT_PI_PLAN_REVIEWER` スイッチは不要になる

## Mapping

| 今の tool / command | 寄せ先 | 備考 |
|---|---|---|
| `show_plan` plan | `plannotator:request` `plan-review` | 既存 `plannotator-client.ts` を拡張 |
| `/plan` | 同上の thin wrapper | `/plannotator-plan-mode` とは別。ファイルを開いて review するだけ |
| `show_plan` questions | `ask_user` | Plannotator に質問フォームは無い。pi-ask-user が既にある |
| `show_spec` / `/spec` | `annotate` + `folderPath` + `gate: true` | Approve / Annotate / Close |
| `show_file` / `/show-file` | markdown → `annotate`。それ以外は tool 削除 | コード閲覧は `read` |
| `show_report` / `/report` | `code-review` | 完了時の diff / annotate。rollback UI は捨てる |
| `show_reports` / `/reports` | `archive` | Plannotator の plan/decision browser |
| `close_viewer` | 削除 | Plannotator が自分のセッションを持つ |

## Keep (Plannotator に相当物が無い)

board / chat / cleanup / sounds / research / security-report は **今回触らない**。
Kanban・LAN chat・ディスク掃除・効果音はレビュー UI ではない。

後でそれも消すなら別タスク。

## After

```
計画を見せる     → show_plan / /plan
                 → Plannotator plan-review
                 → Approve / Deny with annotations
質問する         → ask_user
spec を見せる    → show_spec / /spec
                 → Plannotator annotate-folder (gate)
完了報告         → show_report
                 → Plannotator code-review
過去の計画       → /reports
                 → Plannotator archive
```

## Phase 1: Expand the Plannotator client

**Modify** → `~/src/agent-pi/extensions/lib/plannotator-client.ts`

今は `plan-review` + `review-status` だけ。全部載せる。

- `annotate({ filePath, markdown?, mode?, folderPath?, gate? })`
- `annotateLast({ markdown? })`
- `codeReview({ cwd?, defaultBranch?, diffType? })`
- `archive({ customPlanPath? })`
- 既存 `reviewPlanWithPlannotator` はそのまま

**Modify** → `~/src/agent-pi/extensions/__tests__/plannotator-client.test.ts`

新 action の request / error / timeout を足す。

## Phase 2: Replace document viewers with thin bridges

各 tool は残す（プロンプトと習慣を壊さない）。中身は HTTP サーバを捨てて client を呼ぶだけ。

**Rewrite**

- `extensions/plan-viewer.ts`
  - `runViewer` / `startViewerServer` / HTML を削除
  - plan は常に `reviewPlanWithPlannotator`
  - `mode: "questions"` は「`ask_user` を使え」と返して終わる
  - `/plan` は同じ bridge
  - env スイッチと内臓 fallback を削除
- `extensions/spec-viewer.ts`
  - folder を `annotate` (`mode: "annotate-folder"`, `gate: true`)
- `extensions/file-viewer.ts`
  - `.md` だけ `annotate`
  - それ以外はエラー（`read` を案内）
  - `close_viewer` / `/close-viewer` / `/show-file-help` 削除
- `extensions/completion-report.ts`
  - git 収集 + HTML + rollback を削除
  - `codeReview` を開く。summary があれば先に markdown を書いて `annotate`
- `extensions/reports-viewer.ts`
  - `archive` を開く

## Phase 3: Delete the GUI stack

**Delete**

- `extensions/lib/plan-viewer-html.ts`
- `extensions/lib/plan-viewer-editor.ts`
- `extensions/lib/plan-viewer-render.ts`
- `extensions/lib/spec-viewer-html.ts`
- `extensions/lib/file-viewer-html.ts`
- `extensions/lib/reports-viewer-html.ts`
- `extensions/lib/completion-report-html.ts`
- `extensions/lib/viewer-standalone-export.ts`

**Keep**

- `extensions/lib/viewer-session.ts` — board / chat / cleanup / sounds が使う
- `extensions/lib/report-index.ts` — 残すなら残す。bridge 化後に参照ゼロなら削除

**Cleanup**

- `docs/screenshots/plan-viewer.png` / `completion-report.png` は README から外す
- `install.sh` / `pi-doctor.sh` の Viewer 記述を直す

## Phase 4: Prompts, registry, nix-config

**Modify** → `extensions/lib/mode-prompts.ts`

- 「ALWAYS call show_plan」は残してよい。中身が Plannotator になる
- questions mode の指示を `ask_user` に書き換え
- `show_spec` は「Plannotator で annotate / approve」と書く
- `show_report` は rollback を案内しない

**Modify** → `extensions/tool-registry.ts`

- `show_file` を Interaction から外すか、markdown-only と注記

**Modify** → `~/src/agent-pi/README.md` / `CHANGELOG.md`

- 「optional Plannotator backend」を「Plannotator が唯一のレビュー UI」に
- `AGENT_PI_PLAN_REVIEWER` 節を削除

**Modify** → nix-config `modules/home/pi.nix`

- `AGENT_PI_PLAN_REVIEWER` wrap と sessionVariables を削除
- `plannotator.json` の `executionMode` は今回は触らない（モード廃止は別プラン）

## Out of scope

- PLAN / SPEC モード削除（`.context/todo.md` の別プラン）
- board / chat / cleanup / sounds / research / security-report
- Plannotator 本体の改造
- `executionMode: automatic` への切り替え

## Critical files

| File | Action |
|---|---|
| `~/src/agent-pi/extensions/lib/plannotator-client.ts` | Expand |
| `~/src/agent-pi/extensions/plan-viewer.ts` | Rewrite, no HTTP |
| `~/src/agent-pi/extensions/spec-viewer.ts` | Rewrite |
| `~/src/agent-pi/extensions/file-viewer.ts` | Rewrite / shrink |
| `~/src/agent-pi/extensions/completion-report.ts` | Rewrite |
| `~/src/agent-pi/extensions/reports-viewer.ts` | Rewrite |
| `~/src/agent-pi/extensions/lib/*-viewer-html.ts` | Delete |
| `~/src/agent-pi/extensions/lib/mode-prompts.ts` | Modify |
| `modules/home/pi.nix` | Drop env wrap |

## Verification

1. `show_plan` で内臓 Viewer が開かず、Plannotator の plan-review が開く
2. Approve / Deny with annotations が agent に返る
3. Plannotator 未起動なら内臓 fallback せずエラー
4. `show_plan mode=questions` は ask_user を案内して終わる
5. `show_spec` が annotate-folder + gate を開く
6. `show_file` の `.md` が annotate、それ以外はエラー
7. `show_report` が code-review を開く
8. `/reports` が archive を開く
9. `/plan` が Plannotator review を開く
10. board / chat / cleanup は今まで通り動く
11. `AGENT_PI_PLAN_REVIEWER` 無しでも plan-review に行く
