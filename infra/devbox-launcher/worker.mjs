import { createRemoteJWKSet, jwtVerify } from "jose";

function urlOf(value) {
  try {
    return new URL(value);
  } catch {
    throw new Error("Invalid URL");
  }
}

const headers = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy":
    "default-src 'none'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
};
const json = (value, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { ...headers, "Content-Type": "application/json" },
  });

export async function authenticate(request, env, keys) {
  if (
    !/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/.test(
      env.ACCESS_ISSUER ?? "",
    ) ||
    !env.ACCESS_AUD ||
    !env.ALLOWED_SUB
  )
    throw new Error("Invalid Access configuration");
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token || token.length > 16384)
    throw new Error("Missing Access assertion");
  const keySet =
    keys ??
    createRemoteJWKSet(urlOf(`${env.ACCESS_ISSUER}/cdn-cgi/access/certs`));
  const { payload } = await jwtVerify(token, keySet, {
    issuer: env.ACCESS_ISSUER,
    audience: env.ACCESS_AUD,
    subject: env.ALLOWED_SUB,
    algorithms: ["RS256"],
    requiredClaims: ["exp", "iat", "iss", "aud", "sub"],
  });
  if (typeof payload.iat !== "number" || payload.iat > Date.now() / 1000 + 30) {
    throw new Error("Invalid issue time");
  }
}

const page = `<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Devbox</title><h1>Cloud Devbox</h1>
<p>Machine起動とOrca接続可能は別です。起動後は保存済みRemote Serverを選んでください。</p>
<button id="status">状態確認</button> <button id="start">起動（課金開始）</button>
<pre id="result" role="status"></pre><script src="/app.js"></script></html>`;
const script = `async function call(path, method) {
  const result = document.getElementById('result');
  try {
    const response = await fetch(path, {method, headers: method === 'POST' ?
      {'Content-Type':'application/json','X-Devbox-Start':'1'} : {},
      body: method === 'POST' ? '{}' : undefined});
    result.textContent = await response.text();
  } catch { result.textContent = 'Request failed; check status before retrying.'; }
}
document.getElementById('status').onclick = () => call('/status', 'GET');
document.getElementById('start').onclick = () => {
  if (confirm('固定Machineを起動します。稼働料金が発生します。')) call('/start', 'POST');
};`;

export async function handle(request, env, auth = authenticate) {
  const url = urlOf(request.url);
  if (
    !env.PUBLIC_ORIGIN?.startsWith("https://") ||
    url.origin !== env.PUBLIC_ORIGIN ||
    url.search
  ) {
    return json({ error: "Invalid origin or query" }, 400);
  }
  const expected = {
    "/": "GET",
    "/app.js": "GET",
    "/status": "GET",
    "/start": "POST",
  }[url.pathname];
  if (!expected || request.method !== expected)
    return json({ error: "Method/path not allowed" }, 405);
  try {
    await auth(request, env);
  } catch {
    return json({ error: "Unauthorized" }, 401);
  }
  if (url.pathname === "/")
    return new Response(page, {
      headers: { ...headers, "Content-Type": "text/html; charset=utf-8" },
    });
  if (url.pathname === "/app.js")
    return new Response(script, {
      headers: { ...headers, "Content-Type": "text/javascript; charset=utf-8" },
    });
  if (request.method === "POST") {
    if (
      request.headers.get("Origin") !== env.PUBLIC_ORIGIN ||
      request.headers.get("Content-Type") !== "application/json" ||
      request.headers.get("X-Devbox-Start") !== "1"
    )
      return json({ error: "CSRF check failed" }, 403);
    // Read a bounded body; no caller-specified app, Machine, command or token.
    if (
      request.headers.get("Content-Length") !== null &&
      Number(request.headers.get("Content-Length")) > 2
    ) {
      return json({ error: "Unexpected body" }, 400);
    }
    const reader = request.body?.getReader();
    if (!reader) return json({ error: "Missing body" }, 400);
    let body = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      body += new TextDecoder().decode(value);
      if (body.length > 2) {
        await reader.cancel();
        return json({ error: "Unexpected body" }, 400);
      }
    }
    if (body !== "{}") return json({ error: "Unexpected body" }, 400);
  }
  try {
    const instance = env.MACHINE.get(env.MACHINE.idFromName("only-devbox"));
    return await instance.fetch(
      new Request(`https://internal${url.pathname}`, { method: expected }),
    );
  } catch {
    return json({ error: "Management unavailable; inspect status" }, 503);
  }
}

export default {
  fetch(request, env) {
    return handle(request, env);
  },
};

export class MachineGate {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }
  async fetch(request) {
    // Serialize status/start across Worker instances; rate state survives eviction.
    return this.ctx.blockConcurrencyWhile(async () => {
      const path = urlOf(request.url).pathname;
      if (
        !(
          (path === "/status" && request.method === "GET") ||
          (path === "/start" && request.method === "POST")
        )
      )
        return json({ error: "Denied" }, 405);
      const env = this.env;
      if (
        !/^[a-z0-9][a-z0-9-]{0,62}$/.test(env.FLY_APP ?? "") ||
        !/^[a-f0-9]{14}$/.test(env.FLY_MACHINE_ID ?? "") ||
        !env.FLY_API_TOKEN
      ) {
        return json({ error: "Management not configured" }, 503);
      }
      const now = Date.now();
      const rateKey = path === "/start" ? "nextStart" : "nextStatus";
      const next = (await this.ctx.storage.get(rateKey)) ?? 0;
      if (now < next)
        return json({ error: "Rate limited; wait before retrying" }, 429);
      await this.ctx.storage.put(
        rateKey,
        now + (path === "/start" ? 60000 : 2000),
      );
      const base = `https://api.machines.dev/v1/apps/${env.FLY_APP}/machines/${env.FLY_MACHINE_ID}`;
      const options = {
        headers: { Authorization: `Bearer ${env.FLY_API_TOKEN}` },
        redirect: "error",
        signal: AbortSignal.timeout(10000),
      };
      try {
        const response = await fetch(base, options);
        if (!response.ok) return json({ error: "Fly status failed" }, 502);
        const machine = await response.json();
        if (
          machine.id !== env.FLY_MACHINE_ID ||
          typeof machine.state !== "string"
        )
          throw new Error("Bad schema");
        if (path === "/start" && machine.state === "stopped") {
          const started = await fetch(`${base}/start`, {
            ...options,
            method: "POST",
            signal: AbortSignal.timeout(10000),
          });
          if (!started.ok)
            return json(
              { error: "Start failed or raced; inspect status" },
              502,
            );
          return json({ machine: "starting", ready: "unknown" }, 202);
        }
        if (
          path === "/start" &&
          !["started", "starting"].includes(machine.state)
        ) {
          return json(
            {
              error: "Machine transitioning or unsafe to start; inspect status",
            },
            409,
          );
        }
        return json({ machine: machine.state, ready: "unknown" });
      } catch {
        return json({ error: "Fly unavailable; no automatic retry" }, 502);
      }
    });
  }
}
