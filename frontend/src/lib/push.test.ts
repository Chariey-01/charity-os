import { expect, test } from "vitest";

import { withTimeout } from "./push";

test("a stalled push subscription fails with a helpful message instead of hanging", async () => {
  const stalled = new Promise<never>(() => undefined);
  await expect(withTimeout(stalled, 20, "Your browser's push service did not answer in time.")).rejects.toThrow(/did not answer in time/);
});

test("a prompt answer passes straight through", async () => {
  await expect(withTimeout(Promise.resolve("ok"), 1000, "late")).resolves.toBe("ok");
});
