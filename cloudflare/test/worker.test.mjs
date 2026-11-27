// Unit tests for the Cloudflare front door (src/worker.js). Run: npm test
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import worker from "../src/worker.js";
import {
  CONTENT_SECURITY_POLICY,
  assetHeaders,
  backendOrigin,
  isProxied,
  upstreamRequest,
  visitorResponse,
} from "../src/edge.js";

const SECRET = "s".repeat(10) + "0123456789abcdefghijKLMNOPQRstuv";
const ENV = { BACKEND_ORIGIN: "https://charityos-api.example.app", EDGE_PROXY_SECRET: SECRET };
const SITE = "https://charityos.example.workers.dev";

describe("routing", () => {
  it("forwards the API, the admin and the admin's static files only", () => {
    for (const path of ["/api/v1/me", "/admin/", "/admin", "/static/admin/css/base.css"]) {
      assert.equal(isProxied(path), true, path);
    }
    for (const path of ["/", "/index.html", "/sw.js", "/assets/index-abc12345.js", "/apiary", "/administrator"]) {
      assert.equal(isProxied(path), false, path);
    }
  });
});

describe("backend origin", () => {
  it("accepts https, and plain http on loopback for local runs", () => {
    assert.equal(backendOrigin(ENV).origin, "https://charityos-api.example.app");
    assert.equal(backendOrigin({ BACKEND_ORIGIN: "http://127.0.0.1:8001" }).origin, "http://127.0.0.1:8001");
  });

  it("refuses plain http elsewhere, paths, credentials and nonsense", () => {
    for (const value of [
      "http://charityos-api.example.app",
      "https://charityos-api.example.app/api",
      "https://user:pw@charityos-api.example.app",
      "not a url",
      undefined,
    ]) {
      assert.throws(() => backendOrigin({ BACKEND_ORIGIN: value }), undefined, String(value));
    }
  });
});

describe("the request sent to Django", () => {
  const visitorRequest = (headers = {}, init = {}) =>
    new Request(`${SITE}/api/v1/tasks?archived=include`, { headers, ...init });

  it("keeps the visitor's cookies, CSRF token, origin and body", async () => {
    const upstream = upstreamRequest(
      visitorRequest(
        {
          Cookie: "sessionid=abc; csrftoken=xyz",
          "X-CSRFToken": "xyz",
          Origin: SITE,
          "Content-Type": "application/json",
          "Idempotency-Key": "k-1",
        },
        { method: "POST", body: JSON.stringify({ title: "Read" }) },
      ),
      ENV,
    );
    assert.equal(upstream.url, "https://charityos-api.example.app/api/v1/tasks?archived=include");
    assert.equal(upstream.method, "POST");
    assert.equal(upstream.redirect, "manual");
    assert.equal(upstream.headers.get("Cookie"), "sessionid=abc; csrftoken=xyz");
    assert.equal(upstream.headers.get("X-CSRFToken"), "xyz");
    assert.equal(upstream.headers.get("Origin"), SITE);
    assert.equal(upstream.headers.get("Idempotency-Key"), "k-1");
    assert.deepEqual(JSON.parse(await upstream.text()), { title: "Read" });
  });

  it("adds the secret, the visitor's address and https, and drops anything the visitor claimed", () => {
    const upstream = upstreamRequest(
      visitorRequest({
        "CF-Connecting-IP": "196.201.214.7",
        "X-CharityOS-Edge-Secret": "guess",
        "X-CharityOS-Client-IP": "203.0.113.9",
        "X-Forwarded-For": "203.0.113.9",
        "X-Forwarded-Proto": "http",
        "X-Real-IP": "203.0.113.9",
        Forwarded: "for=203.0.113.9",
        "CF-Worker": "elsewhere",
      }),
      ENV,
    );
    assert.equal(upstream.headers.get("X-CharityOS-Edge-Secret"), SECRET);
    assert.equal(upstream.headers.get("X-CharityOS-Client-IP"), "196.201.214.7");
    assert.equal(upstream.headers.get("X-Forwarded-Proto"), "https");
    for (const name of ["X-Forwarded-For", "X-Real-IP", "Forwarded", "CF-Connecting-IP", "CF-Worker"]) {
      assert.equal(upstream.headers.get(name), null, name);
    }
  });

  it("sends no client address rather than a made-up one", () => {
    const upstream = upstreamRequest(visitorRequest({ "X-CharityOS-Client-IP": "203.0.113.9" }), ENV);
    assert.equal(upstream.headers.get("X-CharityOS-Client-IP"), null);
  });

  it("refuses to forward without a strong secret", () => {
    assert.throws(() => upstreamRequest(visitorRequest(), { ...ENV, EDGE_PROXY_SECRET: "" }));
    assert.throws(() => upstreamRequest(visitorRequest(), { ...ENV, EDGE_PROXY_SECRET: "short" }));
  });
});

describe("Django's response", () => {
  it("points redirects to the backend's own host back at the site", () => {
    const response = visitorResponse(
      new Response(null, {
        status: 302,
        headers: { Location: "https://charityos-api.example.app/admin/login/?next=/admin/" },
      }),
      SITE,
      ENV,
    );
    assert.equal(response.headers.get("Location"), `${SITE}/admin/login/?next=/admin/`);
  });

  it("leaves relative and other sites' redirects, cookies and status alone", () => {
    const headers = new Headers({ Location: "/admin/login/" });
    headers.append("Set-Cookie", "sessionid=abc; Secure; HttpOnly; SameSite=Lax; Path=/");
    const relative = visitorResponse(new Response(null, { status: 302, headers }), SITE, ENV);
    assert.equal(relative.headers.get("Location"), "/admin/login/");
    assert.match(relative.headers.get("Set-Cookie"), /sessionid=abc; Secure; HttpOnly/);
    const other = visitorResponse(
      new Response(null, { status: 302, headers: { Location: "https://elsewhere.example/" } }),
      SITE,
      ENV,
    );
    assert.equal(other.headers.get("Location"), "https://elsewhere.example/");
  });
});

describe("headers on the app's files", () => {
  it("revalidates the shell, the service worker and the manifest", () => {
    const shell = assetHeaders("/", { "Content-Type": "text/html; charset=utf-8" });
    assert.equal(shell.get("Cache-Control"), "no-cache");
    assert.equal(shell.get("Content-Security-Policy"), CONTENT_SECURITY_POLICY);
    assert.equal(shell.get("X-Frame-Options"), "DENY");
    assert.equal(assetHeaders("/sw.js", { "Content-Type": "text/javascript" }).get("Cache-Control"), "no-cache");
    const manifest = assetHeaders("/manifest.webmanifest", { "Content-Type": "application/octet-stream" });
    assert.equal(manifest.get("Cache-Control"), "no-cache");
    assert.equal(manifest.get("Content-Type"), "application/manifest+json");
  });

  it("caches content-hashed files for a year, other files briefly", () => {
    assert.equal(
      assetHeaders("/assets/index-BSiiNENh.js", {}).get("Cache-Control"),
      "public, max-age=31536000, immutable",
    );
    assert.equal(assetHeaders("/icons/icon-192.png", {}).get("Cache-Control"), "public, max-age=60");
  });

  it("sends the browser security headers on every file", () => {
    const headers = assetHeaders("/icons/icon-192.png", { "Content-Type": "image/png" });
    assert.equal(headers.get("Strict-Transport-Security"), "max-age=31536000; includeSubDomains");
    assert.equal(headers.get("X-Content-Type-Options"), "nosniff");
    assert.equal(headers.get("Referrer-Policy"), "same-origin");
    assert.equal(headers.get("Content-Security-Policy"), null); // only HTML pages need it
  });
});

describe("fetch handler", () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });
  const assets = {
    async fetch(request) {
      return new Response("<!doctype html>", {
        headers: { "Content-Type": "text/html; charset=utf-8", "X-Asset-Path": new URL(request.url).pathname },
      });
    },
  };

  it("redirects plain http to https", async () => {
    const response = await worker.fetch(new Request("http://charityos.example.workers.dev/api/v1/me"), ENV);
    assert.equal(response.status, 301);
    assert.equal(response.headers.get("Location"), "https://charityos.example.workers.dev/api/v1/me");
  });

  it("forwards API requests and returns Django's answer", async () => {
    let seen;
    globalThis.fetch = async (request) => {
      seen = request;
      return Response.json({ ok: true }, { status: 201 });
    };
    const response = await worker.fetch(new Request(`${SITE}/api/v1/me`), ENV);
    assert.equal(response.status, 201);
    assert.equal(seen.url, "https://charityos-api.example.app/api/v1/me");
    assert.equal(seen.headers.get("X-CharityOS-Edge-Secret"), SECRET);
  });

  it("answers 503 (which the app treats as offline) when the backend is unreachable", async () => {
    globalThis.fetch = async () => {
      throw new TypeError("network down");
    };
    const response = await worker.fetch(new Request(`${SITE}/api/v1/me`), ENV);
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error.code, "backend_unavailable");
  });

  it("answers 503 without contacting anything when misconfigured", async () => {
    globalThis.fetch = async () => assert.fail("must not fetch");
    const response = await worker.fetch(new Request(`${SITE}/api/v1/me`), { ...ENV, EDGE_PROXY_SECRET: "" });
    assert.equal(response.status, 503);
  });

  it("serves the app's files from static assets with their headers", async () => {
    globalThis.fetch = async () => assert.fail("must not reach the backend");
    const response = await worker.fetch(new Request(`${SITE}/`), { ...ENV, ASSETS: assets });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("X-Asset-Path"), "/");
    assert.equal(response.headers.get("Content-Security-Policy"), CONTENT_SECURITY_POLICY);
  });
});
