import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { day, entry, json, mockApi } from "../test/mockApi";
import { App, elapsedSeconds } from "./App";

test("shows login when unauthenticated", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: "Authentication credentials were not provided." }, 403));
  render(<App />);
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
});

test("a locked-out sign-in shows the server's message, after fetching a CSRF token", async () => {
  const locked = { detail: "Too many failed sign-in attempts. Wait 15 minutes, then try again.", error: { code: "too_many_attempts", message: "Too many failed sign-in attempts. Wait 15 minutes, then try again." } };
  const api = mockApi({
    "/me": json({ detail: "Authentication credentials were not provided." }, 403),
    "/auth/csrf": { csrf_token: "t" },
    "POST /auth/login": json(locked, 429),
  });
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "owner@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByText(/Too many failed sign-in attempts/)).toBeInTheDocument();
  const paths = api.calls.map((call) => `${call.method} ${call.path}`);
  expect(paths.indexOf("GET /auth/csrf")).toBeLessThan(paths.indexOf("POST /auth/login"));
});

test("an app opened offline retries by itself when the connection returns", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/offline/i);

  fetchMock.mockResolvedValue(json({ detail: "x", error: { code: "not_authenticated", message: "x" } }, 403));
  window.dispatchEvent(new Event("online"));

  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
});

test("shows an offline state instead of the login form when the server is unreachable", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/offline/i);
  expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
});

test("mobile navigation exposes the five primary sections", async () => {
  mockApi({ "/schedule/day": day([entry()]) });
  render(<App />);
  const nav = await screen.findByRole("navigation", { name: "Primary" });
  const links = within(nav).getAllByRole("link");
  expect(links.map((link) => link.textContent)).toEqual(["Today", "Tasks", "Schedule", "Plan", "Me"]);
  expect(within(nav).getByRole("link", { name: "Today" })).toHaveAttribute("aria-current", "page");

  fireEvent.click(within(nav).getByRole("link", { name: "Schedule" }));
  window.location.hash = "#/schedule";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  expect(await screen.findByRole("tablist", { name: "Calendar view" })).toBeInTheDocument();
  await waitFor(() => expect(within(nav).getByRole("link", { name: "Schedule" })).toHaveAttribute("aria-current", "page"));
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
  expect(await screen.findByRole("heading", { name: "Your learning paths" })).toBeInTheDocument();
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
