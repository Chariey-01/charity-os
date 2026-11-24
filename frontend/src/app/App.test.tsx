import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { App, elapsedSeconds } from "./App";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const challenge = { id: "c1", name: "2027", start_date: "2027-01-01", end_date: "2027-12-31", status: "active", is_primary: true, total_days: 365, current_day: 20, days_remaining: 345, progress_percent: 5.5, phase: "active" };
const task = { id: "t1", title: "Ship the MVP", status: "planned", area: "a1", is_deep_work_default: true };
const metrics = { total_focused_minutes: 45, deep_work_minutes: 30, planned_appearances: 1, completed_planned_appearances: 0, planned_completion_rate: 0, challenge, roadmaps: [], focus_trend: [], deep_work_trend: [], planned_vs_completed: [], area_distribution: [], exercise_trend: [], sleep_trend: [] };

function mockApp(active: unknown = null) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/me")) return json({ id: "1", email: "owner@example.com", display_name: "Owner", timezone: "UTC" });
    if (path.endsWith("/sessions/active")) return json(active);
    if (path.endsWith("/daily-plans/today")) return json({ plan: { id: "p1", local_date: "2027-01-20" }, challenge, capacity: null, items: [{ id: "i1", task: "t1", kind: "primary", position: 0, title_snapshot: task.title, area_label_snapshot: "Engineering" }], tasks: [task] });
    if (path.endsWith("/areas")) return json([{ id: "a1", name: "Engineering", color: "#173f31" }]);
    if (path.endsWith("/roadmaps") || path.endsWith("/challenges")) return json([]);
    if (path.includes("/analytics/metrics")) return json(metrics);
    return json([]);
  });
}

beforeEach(() => { vi.restoreAllMocks(); });

test("renders real daily plan and dynamic challenge", async () => {
  mockApp(); render(<App />);
  expect(await screen.findByRole("heading", { name: "Good day." })).toBeInTheDocument();
  expect(screen.getAllByText("Ship the MVP").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/DAY 20 OF 365/).length).toBeGreaterThan(0);
  expect(screen.getByText("1/3 selected")).toBeInTheDocument();
});

test("paused timer uses backend elapsed duration", async () => {
  const start = new Date(Date.now() - 125_000).toISOString();
  expect(elapsedSeconds(start)).toBeGreaterThanOrEqual(124);
  mockApp({ id: "s1", title: "Deep build", status: "paused", started_at: start, version: 2, elapsed_seconds: 42, area: "a1" });
  render(<App />);
  expect(await screen.findByText("Deep build")).toBeInTheDocument();
  expect(screen.getByTestId("elapsed-timer")).toHaveTextContent("00:00:42");
});

test("shows login when unauthenticated", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: "Authentication credentials were not provided." }, 403));
  render(<App />);
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
});

test("renders nested roadmap and next actions", async () => {
  const roadmap = { id: "r1", title: "TypeScript", description: "PURPOSE\nBuild typed apps\n\nOUTCOME\nExplain a React app", status: "active" };
  const item = { id: "n1", title: "Union types", description: "Next action: practise and explain.", node_type: "item", state: "planned", time_invested_seconds: 1200, linked_task_ids: [], resources: [], evidence_count: 1, children: [] };
  mockApp().mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/me")) return json({ id: "1", email: "x@y.com", display_name: "", timezone: "UTC" });
    if (path.endsWith("/sessions/active")) return json(null);
    if (path.endsWith("/daily-plans/today")) return json({ plan: { id: "p1", local_date: "2027-01-20" }, challenge, capacity: null, items: [], tasks: [] });
    if (path.endsWith("/areas")) return json([]);
    if (path.endsWith("/challenges")) return json([challenge]);
    if (path.endsWith("/roadmaps")) return json([roadmap]);
    if (path.endsWith("/roadmaps/next-actions")) return json([{ roadmap_id: "r1", roadmap_title: "TypeScript", node_id: "n1", title: "Union types", reason: "prerequisite-ready item" }]);
    if (path.endsWith("/roadmaps/r1/tree")) return json({ roadmap, nodes: [item] });
    if (path.includes("/analytics/metrics")) return json(metrics);
    return json([]);
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Roadmap/ }));
  expect(await screen.findByRole("heading", { name: "Your long-lived paths." })).toBeInTheDocument();
  expect((await screen.findAllByText("Union types")).length).toBeGreaterThan(0);
  fireEvent.click(screen.getAllByRole("button", { name: /TypeScript/ }).at(-1)!);
  expect((await screen.findAllByText("Build typed apps")).length).toBeGreaterThan(0);
});
