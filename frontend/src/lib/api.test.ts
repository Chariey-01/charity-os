import { afterEach, describe, expect, it, vi } from "vitest";

import { api, onSessionEnded, post } from "./api";

function lastHeaders(fetchMock: ReturnType<typeof vi.fn>) {
  const [, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return init.headers as Record<string, string>;
}

describe("post", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends an Idempotency-Key only when one is given", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await post("/evidence", { kind: "note" }, { idempotencyKey: "action-1" });
    expect(lastHeaders(fetchMock)["Idempotency-Key"]).toBe("action-1");
    expect(lastHeaders(fetchMock)["Content-Type"]).toBe("application/json");

    await post("/evidence", { kind: "note" });
    expect(lastHeaders(fetchMock)).not.toHaveProperty("Idempotency-Key");
  });
});

describe("session and CSRF failures", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    onSessionEnded(null);
  });

  const envelope = (code: string, status: number) =>
    new Response(JSON.stringify({ detail: code, error: { code, message: code } }), { status });

  it("reports an ended session, and only that", async () => {
    const ended = vi.fn();
    onSessionEnded(ended);
    vi.stubGlobal("fetch", vi.fn(async () => envelope("not_authenticated", 403)));

    await expect(api("/tasks")).rejects.toMatchObject({ status: 403, code: "not_authenticated" });
    expect(ended).toHaveBeenCalledTimes(1);

    vi.stubGlobal("fetch", vi.fn(async () => envelope("not_found", 404)));
    await expect(api("/tasks/x")).rejects.toMatchObject({ code: "not_found" });
    expect(ended).toHaveBeenCalledTimes(1);
  });

  it("does not report sign-in failures as an ended session", async () => {
    const ended = vi.fn();
    onSessionEnded(ended);
    vi.stubGlobal("fetch", vi.fn(async () => envelope("not_authenticated", 403)));

    await expect(post("/auth/login", {})).rejects.toBeTruthy();
    expect(ended).not.toHaveBeenCalled();
  });

  it("refreshes a rejected CSRF token and retries the same request once", async () => {
    const ended = vi.fn();
    onSessionEnded(ended);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(envelope("csrf_failed", 403))
      .mockResolvedValueOnce(new Response('{"csrf_token":"t"}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"id":"1"}', { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(post("/tasks", { title: "x" }, { idempotencyKey: "k1" })).resolves.toEqual({ id: "1" });
    const urls = fetchMock.mock.calls.map(([url]) => url);
    expect(urls).toEqual(["/api/v1/tasks", "/api/v1/auth/csrf", "/api/v1/tasks"]);
    expect(lastHeaders(fetchMock)["Idempotency-Key"]).toBe("k1");
    expect(ended).not.toHaveBeenCalled();
  });

  it("gives up after one CSRF retry", async () => {
    const fetchMock = vi.fn(async (url: string) => (url.endsWith("/auth/csrf") ? new Response("{}") : envelope("csrf_failed", 403)));
    vi.stubGlobal("fetch", fetchMock);

    await expect(post("/tasks", {})).rejects.toMatchObject({ code: "csrf_failed" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
