import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { json, mockApi } from "../test/mockApi";
import { App, elapsedSeconds } from "./App";

test("shows login when unauthenticated", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: "Authentication credentials were not provided." }, 403));
  render(<App />);
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
});

test("shows an offline state instead of the login form when the server is unreachable", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/offline/i);
  expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
});

test("paused focus session uses the backend elapsed duration", async () => {
  const start = new Date(Date.now() - 125_000).toISOString();
  expect(elapsedSeconds(start)).toBeGreaterThanOrEqual(124);
  window.location.hash = "#/schedule";
  mockApi({
    "/sessions/active": { id: "s1", title: "Deep build", status: "paused", started_at: start, version: 2, elapsed_seconds: 42, area: "a-learn", schedule_entry: null },
  });
  render(<App />);
  const bar = await screen.findByRole("region", { name: "Focus session" });
  expect(within(bar).getByText("Deep build")).toBeInTheDocument();
  expect(screen.getByTestId("elapsed-timer")).toHaveTextContent("00:00:42");
  expect(within(bar).getByRole("button", { name: "Resume focus" })).toBeInTheDocument();
});

test("an empty /sessions/active body means no session (DRF renders None as empty)", async () => {
  window.location.hash = "#/schedule";
  mockApi();
  render(<App />);
  await screen.findByRole("tablist", { name: "Calendar view" });
  expect(screen.queryByRole("region", { name: "Focus session" })).not.toBeInTheDocument();
});

test("renders nested roadmap and next actions", async () => {
  const roadmap = { id: "r1", title: "TypeScript", description: "PURPOSE\nBuild typed apps\n\nOUTCOME\nExplain a React app", status: "active" };
  const item = { id: "n1", title: "Union types", description: "Next action: practise and explain.", node_type: "item", state: "planned", time_invested_seconds: 1200, linked_task_ids: [], resources: [], evidence_count: 1, children: [] };
  window.location.hash = "#/roadmaps";
  mockApi({
    "/roadmaps": [roadmap],
    "/roadmaps/next-actions": [{ roadmap_id: "r1", roadmap_title: "TypeScript", node_id: "n1", title: "Union types", reason: "prerequisite-ready item" }],
    "/roadmaps/r1/tree": { roadmap, nodes: [item] },
  });
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Your long-lived paths." })).toBeInTheDocument();
  expect((await screen.findAllByText("Union types")).length).toBeGreaterThan(0);
  fireEvent.click(screen.getAllByRole("button", { name: /TypeScript/ }).at(-1)!);
  expect((await screen.findAllByText("Build typed apps")).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "Schedule" }));
  const dialog = await screen.findByRole("dialog", { name: "Quick add" });
  expect(within(dialog).getByLabelText("Title", { exact: true })).toHaveValue("Union types");
});

test("offline banner appears and saving is disabled", async () => {
  Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
  mockApi();
  render(<App />);
  expect(await screen.findByText(/Offline\. You can look around/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Quick add activity" }));
  const dialog = await screen.findByRole("dialog", { name: "Quick add" });
  expect(within(dialog).getByRole("button", { name: /Offline/ })).toBeDisabled();
});
