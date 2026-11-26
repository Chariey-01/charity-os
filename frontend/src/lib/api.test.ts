import { afterEach, describe, expect, it, vi } from "vitest";

import { post } from "./api";

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
