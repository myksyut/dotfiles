# Optional authenticated launcher (Phase 4)

未デプロイ。Cloudflareの利用条件・料金、Access保護domain、単一Machine、最小権限/期限のFly tokenを人が確定してから使用する。`workers.dev`とpreview URLは無効。

`worker.mjs`はJOSEでAccess JWTのRS256署名・issuer・audience・exp・nbf・subjectを検証する。固定本人以外を許可しない。GETは起動せず、POST /startはsame-origin + JSON + custom header + 固定bodyを要求。Durable Objectがstartを直列化し60秒制限、statusは2秒制限。起動済みはno-op、未知/遷移中は停止・restart・createせず拒否する。Fly応答全体やtokenは返さない。

```bash
cd infra/devbox-launcher
npm ci --ignore-scripts
npm test
```

人が行う公開準備（この実装作業では実行しない）:

1. `wrangler.example.toml`をローカル`wrangler.toml`へコピーし非secret値を入力。Accessアプリを同じdomainへ配置し本人のみallow、bypass policyなし。
2. Worker secretとして`FLY_API_TOKEN`を登録。app限定tokenもstart-only権限とは限らない。TTL・失効方法を記録。
3. レビューしたWrangler版を使い、明示承認後のみdeploy。Worker/DO/domainの課金を確認。
4. 実JWT、不正署名/issuer/audience/期限/subject、Originなし/別Origin、GET /start、連打・同時POST、直接Worker URL、Fly障害を受入試験。すべての不正要求でMachineを起動しない。
5. Tailscale上のOrcaへWorkerが到達する構成ではない。`ready: unknown`は意図した表示。pairing URLは保存しない。

テストはローカル生成鍵と偽Fly transportだけを使い、実認証を取得しない。公開環境のJWT転送、Access policy、Durable Objectの排他動作は別途実機確認が必要。
