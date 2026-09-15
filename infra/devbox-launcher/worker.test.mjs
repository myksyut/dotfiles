import assert from "node:assert/strict";
import { test } from "node:test";
import { generateKeyPair, SignJWT } from "jose";
import worker, { authenticate, handle, MachineGate } from "./worker.mjs";

const env = {
  PUBLIC_ORIGIN: "https://devbox.example.com",
  ACCESS_ISSUER: "https://owner.cloudflareaccess.com",
  ACCESS_AUD: "test-audience",
  ALLOWED_SUB: "test-owner",
  FLY_APP: "test-app",
  FLY_MACHINE_ID: "0123456789abcd",
  FLY_API_TOKEN: "fixture-not-a-real-token",
};
const pair = await generateKeyPair("RS256");
const other = await generateKeyPair("RS256");
async function token(claims = {}, key = pair.privateKey) {
  return new SignJWT({
    iss: env.ACCESS_ISSUER,
    aud: env.ACCESS_AUD,
    sub: env.ALLOWED_SUB,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 60,
    ...claims,
  })
    .setProtectedHeader({ alg: "RS256", kid: "test" })
    .sign(key);
}
function request(path, method = "GET", extra = {}) {
  return new Request(`${env.PUBLIC_ORIGIN}${path}`, { method, ...extra });
}
function post(extra = {}) {
  return request("/start", "POST", {
    body: "{}",
    headers: {
      Origin: env.PUBLIC_ORIGIN,
      "Content-Type": "application/json",
      "X-Devbox-Start": "1",
      ...extra,
    },
  });
}
function binding() {
  const calls = [];
  return {
    calls,
    MACHINE: {
      idFromName: (name) => name,
      get: () => ({
        fetch: async (req) => {
          calls.push(req);
          return Response.json({ machine: "starting", ready: "unknown" });
        },
      }),
    },
  };
}

test("valid Access assertion is verified with a real signature", async () => {
  const jwt = await token();
  await authenticate(
    request("/status", "GET", { headers: { "Cf-Access-Jwt-Assertion": jwt } }),
    env,
    pair.publicKey,
  );
});
for (const [name, claims] of Object.entries({
  issuer: { iss: "https://wrong.cloudflareaccess.com" },
  audience: { aud: "wrong" },
  subject: { sub: "wrong" },
  expired: { exp: 1 },
  notBefore: { nbf: Math.floor(Date.now() / 1000) + 3600 },
  futureIssue: { iat: Math.floor(Date.now() / 1000) + 3600 },
})) {
  test(`reject ${name}`, async () => {
    await assert.rejects(
      authenticate(
        request("/status", "GET", {
          headers: { "Cf-Access-Jwt-Assertion": await token(claims) },
        }),
        env,
        pair.publicKey,
      ),
    );
  });
}
test("bad signature and missing header rejected", async () => {
  await assert.rejects(authenticate(request("/status"), env, pair.publicKey));
  await assert.rejects(
    authenticate(
      request("/status", "GET", {
        headers: {
          "Cf-Access-Jwt-Assertion": await token({}, other.privateKey),
        },
      }),
      env,
      pair.publicKey,
    ),
  );
});
test("GET/link preview/unauthorized requests never reach Machine binding", async () => {
  const b = binding();
  const config = { ...env, ...b };
  assert.equal((await handle(request("/start"), config)).status, 405);
  assert.equal(
    (await worker.fetch(request("/status"), config, {})).status,
    401,
  );
  assert.equal(
    (await handle(request("/"), config, async () => {})).status,
    200,
  );
  assert.equal(b.calls.length, 0);
});
test("CSRF, caller target and origin are rejected", async () => {
  const b = binding();
  const config = { ...env, ...b };
  assert.equal(
    (
      await handle(
        post({ Origin: "https://evil.example" }),
        config,
        async () => {},
      )
    ).status,
    403,
  );
  assert.equal(
    (
      await handle(
        request("/start", "POST", { body: "{}" }),
        config,
        async () => {},
      )
    ).status,
    403,
  );
  assert.equal(
    (await handle(request("/status?machine=other"), config, async () => {}))
      .status,
    400,
  );
  assert.equal(b.calls.length, 0);
});
test("valid POST and status only forward fixed paths", async () => {
  const b = binding();
  const config = { ...env, ...b };
  assert.equal((await handle(post(), config, async () => {})).status, 200);
  await handle(request("/status"), config, async () => {});
  assert.deepEqual(
    b.calls.map((r) => [r.url, r.method]),
    [
      ["https://internal/start", "POST"],
      ["https://internal/status", "GET"],
    ],
  );
});
function gateContext() {
  const values = new Map();
  let queue = Promise.resolve();
  return {
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => values.set(key, value),
    },
    blockConcurrencyWhile(fn) {
      const result = queue.then(fn);
      queue = result.catch(() => {});
      return result;
    },
  };
}
test("concurrent starts serialized/rate limited; no second Machine or restart", async () => {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push([url, options.method ?? "GET"]);
    return Response.json(
      url.endsWith("/start")
        ? {}
        : { id: env.FLY_MACHINE_ID, state: "stopped" },
    );
  };
  try {
    const gate = new MachineGate(gateContext(), env);
    const results = await Promise.all([gate.fetch(post()), gate.fetch(post())]);
    assert.deepEqual(
      results.map((r) => r.status),
      [202, 429],
    );
    assert.equal(calls.length, 2);
    assert.equal(
      calls[1][0],
      `https://api.machines.dev/v1/apps/test-app/machines/${env.FLY_MACHINE_ID}/start`,
    );
  } finally {
    globalThis.fetch = original;
  }
});
test("already started is no-op, unknown state refuses start", async () => {
  const original = globalThis.fetch;
  try {
    for (const state of ["started", "starting", "stopping", "destroyed"]) {
      const calls = [];
      globalThis.fetch = async (url) => {
        calls.push(url);
        return Response.json({ id: env.FLY_MACHINE_ID, state });
      };
      const gate = new MachineGate(gateContext(), env);
      assert.equal(
        (await gate.fetch(post())).status,
        ["started", "starting"].includes(state) ? 200 : 409,
      );
      assert.equal(calls.length, 1);
    }
  } finally {
    globalThis.fetch = original;
  }
});
test("Fly outage produces no retry and no raw response leakage", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    throw new Error("fixture-secret-response");
  };
  try {
    const response = await new MachineGate(gateContext(), env).fetch(post());
    assert.equal(response.status, 502);
    assert.equal(calls, 1);
    assert.doesNotMatch(await response.text(), /fixture-secret-response/);
  } finally {
    globalThis.fetch = original;
  }
});
