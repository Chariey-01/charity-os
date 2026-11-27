import { afterEach, expect, test } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "../app/App";
import { mockApi } from "../test/mockApi";

const progress = (overrides = {}) => ({
  ratio: null,
  basis: "none",
  latest_value: null,
  milestones_total: 0,
  milestones_done: 0,
  tasks_total: 0,
  tasks_done: 0,
  overdue: false,
  at_risk: false,
  days_left: null,
  ...overrides,
});

const goal = (overrides = {}) => ({
  id: "g1",
  title: "Become an AI engineer",
  description: "",
  why: "Build things that matter",
  area: null,
  vision: null,
  vision_title: null,
  kind: "qualitative",
  metric_unit: "",
  baseline_value: null,
  target_value: null,
  start_date: "2026-11-01",
  target_date: "2027-06-30",
  status: "active",
  completed_at: null,
  completion_note: "",
  archived_at: null,
  created_at: "2026-11-01T08:00:00Z",
  progress: progress(),
  ...overrides,
});

afterEach(() => {
  window.location.hash = "";
});

test("a goal without milestones or measurements says so instead of showing 0%", async () => {
  window.location.hash = "#/goals";
  mockApi({ "/goals": [goal()] });
  render(<App />);
  const card = await screen.findByRole("link", { name: /Become an AI engineer/ });
  expect(within(card).getByText("No measure yet")).toBeInTheDocument();
  expect(within(card).queryByText(/0%/)).not.toBeInTheDocument();
});

test("goal progress from milestones is shown with its basis", async () => {
  window.location.hash = "#/goals";
  mockApi({ "/goals": [goal({ progress: progress({ ratio: 0.5, basis: "milestones", milestones_total: 2, milestones_done: 1, overdue: true }) })] });
  render(<App />);
  const card = await screen.findByRole("link", { name: /Become an AI engineer/ });
  expect(within(card).getByText("50%")).toBeInTheDocument();
  expect(within(card).getByText("1/2 milestones")).toBeInTheDocument();
  expect(within(card).getByText("Overdue")).toBeInTheDocument();
});

test("creating a goal validates the title and sends one idempotent create", async () => {
  window.location.hash = "#/goals";
  const api = mockApi({ "/goals": [], "POST /goals": goal({ id: "new" }) });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Create your first goal" }));
  const dialog = await screen.findByRole("dialog", { name: "New goal" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Create goal" }));
  expect(await within(dialog).findByText("Name the goal.")).toBeInTheDocument();
  expect(api.writes()).toHaveLength(0);
  fireEvent.change(within(dialog).getByLabelText("Goal"), { target: { value: "Ship CharityOS" } });
  fireEvent.click(within(dialog).getByRole("radio", { name: "A number" }));
  fireEvent.change(within(dialog).getByLabelText("Target"), { target: { value: "10" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Create goal" }));
  await waitFor(() => expect(api.writes()).toHaveLength(1));
  const [write] = api.writes();
  expect(write.path).toBe("/goals");
  expect(write.body).toMatchObject({ title: "Ship CharityOS", kind: "measurable", target_value: "10" });
  const init = (api.spy.mock.calls.find(([, options]) => options?.method === "POST")?.[1] ?? {}) as RequestInit;
  expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
});

test("realising a vision needs evidence or an explicit confirmation", async () => {
  window.location.hash = "#/vision";
  const vision = {
    id: "v1",
    kind: "manifestation",
    title: "I lead an AI product team",
    statement: "",
    theme: "Career",
    horizon: "medium",
    success_looks_like: "",
    notes: "",
    image_url: "",
    target_year: 2028,
    status: "active",
    realised_at: null,
    realised_note: "",
    realised_evidence_url: "",
    position: 0,
    version: 1,
    goals_count: 0,
    archived_at: null,
    created_at: "",
    updated_at: "",
  };
  const api = mockApi({ "/vision": [vision], "/vision/v1/revisions": [], "/goals": [] });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /I lead an AI product team/ }));
  fireEvent.click(await screen.findByRole("button", { name: "It came true" }));
  const dialog = await screen.findByRole("dialog", { name: "It came true" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Record it" }));
  expect(await within(dialog).findByText(/Add a link as evidence, or tick the box/)).toBeInTheDocument();
  expect(api.writes()).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole("checkbox", { name: /I confirm this has come true/ }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Record it" }));
  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/vision/v1/realise"]));
  expect(api.writes()[0].body).toMatchObject({ confirm: true, evidence_url: "" });
});

test("My Journey shows chapters, snapshots and an honest empty state", async () => {
  window.location.hash = "#/journey";
  const year = new Date().getFullYear();
  mockApi({
    "/journey": {
      year,
      years: [year],
      summary: { goals_completed: 1, milestones_completed: 0, learning_completed: 0, projects_completed: 0, tasks_completed: 3, focus_minutes: 90 },
      months: [{ month: `${year}-11`, tasks_completed: 3, focus_minutes: 90, top_areas: [["Learning", 3]] }],
      chapters: [{ id: "c1", name: "Road to 2027", start_date: `${year}-09-01`, end_date: `${year}-12-05`, status: "active", archived: false, total_days: 96 }],
      entries: [{ id: "a1", type: "goal_completed", title: "Original title", date: `${year}-11-20`, occurred_at: `${year}-11-20T10:00:00Z`, detail: { note: "Done!" } }],
      truncated: false,
    },
  });
  render(<App />);
  expect(await screen.findByText("Road to 2027")).toBeInTheDocument();
  expect(screen.getByText("Original title")).toBeInTheDocument();
  expect(screen.getByText(/3 tasks done · 1h 30m focused/)).toBeInTheDocument();
});

test("the Plan hub links every part of the chain", async () => {
  window.location.hash = "#/plan";
  mockApi({ "/goals": [goal()], "/challenges/primary": null });
  render(<App />);
  for (const name of [/My Vision/, /Goals/, /Roadmaps/, /Projects/, /Challenges/]) {
    expect(await screen.findByRole("link", { name })).toBeInTheDocument();
  }
  const nav = screen.getByRole("navigation", { name: "Primary" });
  expect(within(nav).getByRole("link", { name: "Plan" })).toHaveAttribute("aria-current", "page");
});
