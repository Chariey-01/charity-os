import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

beforeEach(() => {
  vi.restoreAllMocks();
});

test("renders the shell and reports backend health", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "ok", database: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<App />);

  expect(screen.getByRole("heading", { name: "CharityOS" })).toBeInTheDocument();
  expect(await screen.findByText("Backend: ready")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/health",
    expect.objectContaining({ credentials: "same-origin" }),
  );
});

