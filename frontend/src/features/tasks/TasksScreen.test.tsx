import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { App } from "../../app/App";
import { TODAY, entry, json, mockApi } from "../../test/mockApi";
import type { Task } from "../../lib/types";

function task(overrides: Partial<Task>): Task {
  return {
    id: overrides.title ?? "t",
    title: "t",
    description: "",
    status: "todo",
    area: null,
    roadmap_item: null,
    priority: 0,
    due_date: null,
    estimated_minutes: null,
    completed_at: null,
    archived_at: null,
    created_at: "2026-11-20T08:00:00Z",
    is_deep_work_default: false,
    ...overrides,
  };
}

const overdue = task({ id: "t-over", title: "Send invoice", due_date: "2026-11-20", area: "a-personal", priority: 3 });
const dueToday = task({ id: "t-today", title: "Udemy: section 4", due_date: TODAY, area: "a-learn" });
const later = task({ id: "t-later", title: "Update CV", due_date: "2026-11-30" });
const someday = task({ id: "t-any", title: "Read chapter 2" });
const parked = task({ id: "t-back", title: "Explore partnerships", status: "backlog" });

function tasksRoute(open: Task[], done: Task[] = []) {
  return ({ search }: { search: string }) => (search.includes("status=done") ? done : search.includes("archived=only") ? [] : open);
}

async function openTasksTab() {
  window.location.hash = "#/tasks";
  render(<App />);
  return screen.findByRole("heading", { name: "What needs doing" });
}

test("tasks are grouped by when they are due, with workstream, due label and priority", async () => {
  mockApi({ "/tasks": tasksRoute([later, someday, dueToday, overdue, parked]) });
  await openTasksTab();

  const titles = await screen.findAllByRole("heading", { level: 2 });
  expect(titles.map((heading) => heading.textContent?.replace(/\d+$/, "").trim())).toEqual([
    "Overdue",
    "Today",
    "Upcoming",
    "No date",
    "Backlog",
  ]);
  const overdueGroup = screen.getByRole("region", { name: /Overdue/ });
  expect(within(overdueGroup).getByText("Send invoice")).toBeInTheDocument();
  expect(within(overdueGroup).getByText("4 days overdue")).toBeInTheDocument();
  expect(within(overdueGroup).getByText("High")).toBeInTheDocument();
  expect(within(overdueGroup).getByText("Personal")).toBeInTheDocument();
  expect(screen.getByText(/5 open · 1 overdue/)).toBeInTheDocument();
});

test("filtering by workstream keeps the groups honest", async () => {
  mockApi({ "/tasks": tasksRoute([overdue, dueToday, later]) });
  await openTasksTab();
  fireEvent.click(await screen.findByRole("radio", { name: "Learning" }));
  window.dispatchEvent(new HashChangeEvent("hashchange"));

  await waitFor(() => expect(screen.queryByText("Send invoice")).not.toBeInTheDocument());
  expect(screen.getByText("Udemy: section 4")).toBeInTheDocument();
});

test("quick capture needs only a title and sends one idempotency key per capture", async () => {
  const api = mockApi({ "/tasks": tasksRoute([]), "POST /tasks": (call: { body: { title: string } }) => task({ title: call.body.title }) });
  await openTasksTab();
  expect(await screen.findByText("Nothing on your list")).toBeInTheDocument();

  const input = screen.getByRole("textbox", { name: "New task" });
  fireEvent.change(input, { target: { value: "Microsoft Learn: finish module" } });
  fireEvent.submit(input.closest("form")!);
  await waitFor(() => expect(api.writes()).toHaveLength(1));
  fireEvent.change(input, { target: { value: "Call client about deliverable" } });
  fireEvent.submit(input.closest("form")!);
  await waitFor(() => expect(api.writes()).toHaveLength(2));

  const [first, second] = api.writes();
  expect(first.body).toEqual({ title: "Microsoft Learn: finish module" });
  expect(second.body).toEqual({ title: "Call client about deliverable" });
  const keys = api.spy.mock.calls
    .filter(([, init]) => init?.method === "POST")
    .map(([, init]) => (init!.headers as Record<string, string>)["Idempotency-Key"]);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).not.toBe(keys[1]);
});

test("a full task: workstream, priority, due date, estimate and status, saved once", async () => {
  const api = mockApi({ "/tasks": tasksRoute([]), "POST /tasks": (call: { body: Partial<Task> }) => task({ ...call.body, id: "new" }) });
  await openTasksTab();
  fireEvent.click(await screen.findByRole("button", { name: "Add a task" }));

  const sheet = await screen.findByRole("dialog", { name: "New task" });
  fireEvent.change(within(sheet).getByLabelText("Title"), { target: { value: "QUAHAXTON customer interviews" } });
  fireEvent.change(within(sheet).getByLabelText(/Workstream/), { target: { value: "a-learn" } });
  fireEvent.click(within(sheet).getByRole("radio", { name: "High" }));
  fireEvent.click(within(sheet).getByRole("button", { name: "Tomorrow" }));
  fireEvent.change(within(sheet).getByLabelText(/Estimate/), { target: { value: "90" } });
  fireEvent.change(within(sheet).getByLabelText("Status"), { target: { value: "backlog" } });
  fireEvent.click(within(sheet).getByRole("button", { name: "Add task" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(api.writes()).toHaveLength(1);
  expect(api.writes()[0].body).toMatchObject({
    title: "QUAHAXTON customer interviews",
    area: "a-learn",
    priority: 3,
    due_date: "2026-11-25",
    estimated_minutes: 90,
    status: "backlog",
    roadmap_item: null,
  });
});

test("a task without a title is not sent", async () => {
  const api = mockApi({ "/tasks": tasksRoute([]) });
  await openTasksTab();
  fireEvent.click(await screen.findByRole("button", { name: "Add a task" }));
  fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Add task" }));

  expect(await screen.findByText("Give the task a title.")).toBeInTheDocument();
  expect(api.writes()).toHaveLength(0);
});

test("ticking a task completes it on the server", async () => {
  const api = mockApi({ "/tasks": tasksRoute([dueToday]), "POST /tasks/t-today/complete": { ...dueToday, status: "done" } });
  await openTasksTab();
  fireEvent.click(await screen.findByRole("button", { name: "Mark Udemy: section 4 done" }));

  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/tasks/t-today/complete"]));
});

test("from a task: defer, start focus and archive", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const api = mockApi({
    "/tasks": tasksRoute([dueToday]),
    "/tasks/t-today": dueToday,
    "PATCH /tasks/t-today": (call: { body: Partial<Task> }) => ({ ...dueToday, ...call.body }),
    "POST /sessions/start": { id: "s1", status: "active" },
    "POST /tasks/t-today/transition": { ...dueToday, status: "in_progress" },
    "POST /tasks/t-today/archive": { ...dueToday, archived_at: "2026-11-24T10:00:00Z" },
  });
  await openTasksTab();

  fireEvent.click(await screen.findByRole("button", { name: /^Udemy: section 4/ }));
  let sheet = await screen.findByRole("dialog", { name: "Task" });
  fireEvent.click(await within(sheet).findByRole("button", { name: "Tomorrow" }));
  await waitFor(() => expect(api.writes().at(-1)).toMatchObject({ method: "PATCH", body: { due_date: "2026-11-25" } }));

  fireEvent.click(within(sheet).getByRole("button", { name: "Start focus" }));
  await waitFor(() => expect(api.writes().map((call) => call.path)).toContain("/tasks/t-today/transition"));
  const start = api.writes().find((call) => call.path === "/sessions/start")!;
  expect(start.body).toMatchObject({ title: "Udemy: section 4", area: "a-learn", task: "t-today" });
  expect(typeof start.body!.id).toBe("string");

  fireEvent.click(await screen.findByRole("button", { name: /^Udemy: section 4/ }));
  sheet = await screen.findByRole("dialog", { name: "Task" });
  fireEvent.click(await within(sheet).findByRole("button", { name: "Archive" }));
  await waitFor(() => expect(api.writes().at(-1)!.path).toBe("/tasks/t-today/archive"));
});

test("a task without a workstream asks where to track the time before focusing", async () => {
  mockApi({ "/tasks": tasksRoute([someday]), "/tasks/t-any": someday });
  await openTasksTab();
  fireEvent.click(await screen.findByRole("button", { name: /^Read chapter 2/ }));
  const sheet = await screen.findByRole("dialog", { name: "Task" });

  const start = await within(sheet).findByRole("button", { name: "Start focus" });
  expect(start).toBeDisabled();
  fireEvent.change(within(sheet).getByLabelText("Track the time under"), { target: { value: "a-learn" } });
  expect(start).toBeEnabled();
});

test("an expired session returns to sign-in with an explanation, without a reload", async () => {
  let signedIn = true;
  mockApi({
    "/tasks": ({ search }: { search: string }) =>
      signedIn ? (search.includes("status=open") ? [dueToday] : []) : json({ detail: "x", error: { code: "not_authenticated", message: "x" } }, 403),
  });
  await openTasksTab();
  expect(await screen.findByText("Udemy: section 4")).toBeInTheDocument();

  signedIn = false;
  document.dispatchEvent(new Event("visibilitychange"));
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  document.dispatchEvent(new Event("visibilitychange"));

  expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Your session has ended");
  expect(screen.queryByText("Udemy: section 4")).not.toBeInTheDocument();
});

test("starting focus on a task that is scheduled today starts that activity", async () => {
  const planned = entry({ id: "e-udemy", title: "Udemy: section 4", task: "t-today", status: "scheduled", tracking: "focus", version: 3 });
  const api = mockApi({
    "/tasks": tasksRoute([dueToday]),
    "/tasks/t-today": dueToday,
    "/schedule-entries": [planned],
    "POST /schedule-entries/e-udemy/start": { ...planned, status: "in_progress" },
    "POST /tasks/t-today/transition": { ...dueToday, status: "in_progress" },
  });
  await openTasksTab();
  fireEvent.click(await screen.findByRole("button", { name: /^Udemy: section 4/ }));
  fireEvent.click(await within(await screen.findByRole("dialog", { name: "Task" })).findByRole("button", { name: "Start focus" }));

  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/schedule-entries/e-udemy/start", "/tasks/t-today/transition"]));
  expect(api.writes()[0].body).toMatchObject({ expected_version: 3 });
  expect(typeof api.writes()[0].body!.session_id).toBe("string");
});
