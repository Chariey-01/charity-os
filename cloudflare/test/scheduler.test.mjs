// Run: npm test
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import worker from "../src/worker.js";
import { CRON_SECRET_HEADER, NEXT_DUE_KEY, dispatchIsDue, invalidates, runScheduled } from "../src/scheduler.js";

const SECRET = "c".repeat(40);
const EDGE = "e".repeat(40);
const BASE = { BACKEND_ORIGIN: "https://api.example.app", EDGE_PROXY_SECRET: EDGE, CRON_SECRET: SECRET };

function kv(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    store,
    get: async (key) => store.get(key) ?? null,
    put: async (key, value) => void store.set(key, value),
    delete: async (key) => void store.delete(key),
  };
}

describe("scheduled reminders", () => {
  it("calls the backend with both secrets and remembers the next due time", async () => {
    const env = { ...BASE, REMINDERS_KV: kv() };
    const seen = [];
    const result = await runScheduled(env, Date.parse("2026-11-28T04:00:00Z"), async (request) => {
      seen.push(request);
      return Response.json({ sent: 1, next_due_at: "2026-11-28T04:30:00+00:00" });
    });
    assert.equal(result.sent, 1);
    assert.equal(seen.length, 1);
    assert.equal(new URL(seen[0].url).pathname, "/api/v1/internal/reminders/dispatch");
    assert.equal(seen[0].headers.get(CRON_SECRET_HEADER), SECRET);
    assert.equal(seen[0].headers.get("X-CharityOS-Edge-Secret"), EDGE);
    assert.equal(env.REMINDERS_KV.store.get(NEXT_DUE_KEY), "2026-11-28T04:30:00+00:00");
  });

  it("skips the backend until the next reminder is close", async () => {
    const env = { ...BASE, REMINDERS_KV: kv({ [NEXT_DUE_KEY]: "2026-11-28T04:30:00Z" }) };
    assert.equal(await dispatchIsDue(env, Date.parse("2026-11-28T04:00:00Z")), false);
    assert.equal(await dispatchIsDue(env, Date.parse("2026-11-28T04:29:30Z")), true);
    let calls = 0;
    const result = await runScheduled(env, Date.parse("2026-11-28T04:00:00Z"), async () => {
      calls += 1;
      return Response.json({});
    });
    assert.equal(result.reason, "not_due");
    assert.equal(calls, 0);
  });

  it("dispatches every tick without KV, and never without a strong secret", async () => {
    assert.equal(await dispatchIsDue({ ...BASE }, Date.now()), true);
    const result = await runScheduled({ ...BASE, CRON_SECRET: "short" }, Date.now(), async () => {
      throw new Error("must not call");
    });
    assert.equal(result.reason, "not_configured");
  });

  it("forgets the cached time after writes that can change it", async () => {
    const site = "https://charityos.example.workers.dev";
    assert.equal(invalidates(new Request(`${site}/api/v1/reminders`, { method: "POST" })), true);
    assert.equal(invalidates(new Request(`${site}/api/v1/schedule-entries/1/start`, { method: "POST" })), true);
    assert.equal(invalidates(new Request(`${site}/api/v1/reminders`)), false);
    assert.equal(invalidates(new Request(`${site}/api/v1/tasks`, { method: "POST" })), false);
  });

  it("the cron entry point hands the run to waitUntil", async () => {
    const pending = [];
    await worker.scheduled({ scheduledTime: Date.now() }, { ...BASE, CRON_SECRET: "x" }, { waitUntil: (p) => pending.push(p) });
    assert.equal(pending.length, 1);
    assert.equal((await pending[0]).reason, "not_configured");
  });
});

describe("Android asset links", async () => {
  const { assetLinks, handleRequest } = await import("../src/edge.js");
  const FP = "EA:17:55:77:32:CC:A0:4B:15:DD:0A:AC:FF:AE:C9:EA:F7:DD:61:0F:F9:0F:3B:0D:FD:76:54:3D:73:D6:AD:0C";

  it("serves the package and fingerprint for Trusted Web Activity verification", async () => {
    const env = { ...BASE, ANDROID_PACKAGE: "dev.workers.charity_jk.charityos.twa", ANDROID_CERT_SHA256: FP };
    const response = await handleRequest(new Request("https://charityos.example.workers.dev/.well-known/assetlinks.json"), env);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body[0].target.package_name, "dev.workers.charity_jk.charityos.twa");
    assert.deepEqual(body[0].target.sha256_cert_fingerprints, [FP]);
    assert.deepEqual(body[0].relation, ["delegate_permission/common.handle_all_urls"]);
  });

  it("serves an empty list when unconfigured or malformed", () => {
    assert.deepEqual(assetLinks({}), []);
    assert.deepEqual(assetLinks({ ANDROID_PACKAGE: "x", ANDROID_CERT_SHA256: "not-a-fingerprint" }), []);
  });
});
