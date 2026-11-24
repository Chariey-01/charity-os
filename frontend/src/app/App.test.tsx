import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { json, mockApi } from "../test/mockApi";
import { App } from "./App";

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
