import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import type { Progress, ProgressTask } from "../../lib/types";
import { day, mockApi, progress } from "../../test/mockApi";

const done = (title: string, label = "Learning and Education", color = "#1D4ED8"): ProgressTask => ({
  id: title,
  title,
  area: "a1",
  label,
  color,
  due_date: "2026-11-25",
  status: "done",
  status_now: "done",
  archived_now: false,
  planned: true,
  completed_on: "2026-11-24",
});
const open = (title: string): ProgressTask => ({
  ...done(title),
  id: title.toLowerCase().replace(/\s+/g, "-"),
  status: "todo",
  status_now: "todo",
  completed_on: null,
});

const week = (): Progress =>
  progress({
    overall: { completed: 9, remaining: 6, overdue: 2, due_today: 1, completion_percent: 60 },
    weekly: {
      planned: 4,
      completed: 3,
      outstanding: 1,
      completion_percent: 75,
      unplanned_completed: 1,
      completed_total: 4,
      previous: { planned: 5, completed: 3, outstanding: 2, completion_percent: 60, unplanned_completed: 0, completed_total: 3 },
    },
    workstreams: {
      completed_tasks: [
        { area: "a1", label: "Learning and Education", color: "#1D4ED8", count: 3 },
        { area: "a2", label: "Client Work and Income", color: "#A0522D", count: 1 },
      ],
      time: [{ area: "a2", label: "Client Work and Income", color: "#A0522D", actual_minutes: 150 }],
    },
    tasks: { planned: [done("Course"), done("Exercises"), done("Quiz"), open("Invoice client")], completed: [done("Course"), done("Exercises"), done("Quiz")] },
  });

test("this week: a percentage with its denominator, the comparison and both splits", async () => {
  mockApi({ "/progress": week() });
  window.location.hash = "#/insights";
  render(<App />);

  const planned = await screen.findByRole("region", { name: "Planned tasks this week" });
  expect(within(planned).getByText("75%")).toBeInTheDocument();
  expect(within(planned).getByText(/3 of 4 planned tasks done · 1 outstanding/)).toBeInTheDocument();
  expect(screen.getByText(/Also 1 unplanned task done \(not part of the percentage\)/)).toBeInTheDocument();
  expect(screen.getByText(/Up from 60% \(3 of 5\) the week before/)).toBeInTheDocument();

  const tasksChart = screen.getByRole("figure", { name: "Completed tasks by workstream" });
  expect(within(tasksChart).getByText("Learning and Education")).toBeInTheDocument();
  expect(within(tasksChart).getByText("75%")).toBeInTheDocument();
  const timeChart = screen.getByRole("figure", { name: "Tracked time by workstream" });
  const timeLegend = within(within(timeChart).getByRole("list")).getByText("Client Work and Income").closest("li")!;
  expect(within(timeLegend).getByText("2h 30m")).toBeInTheDocument();
  expect(within(timeLegend).getByText("100%")).toBeInTheDocument();

  fireEvent.click(within(tasksChart).getByRole("button", { name: "Table" }));
  expect(within(tasksChart).getByRole("table")).toBeInTheDocument();
});

test("an empty week says so instead of showing 0% or 100%", async () => {
  mockApi({ "/progress": progress() });
  window.location.hash = "#/insights";
  render(<App />);

  expect(await screen.findByText(/No tasks were planned for this week/)).toBeInTheDocument();
  expect(screen.queryByText("0%")).not.toBeInTheDocument();
  expect(screen.getByText("No tasks completed in this week yet.")).toBeInTheDocument();
  expect(screen.getByText("Nothing recorded for this week yet.")).toBeInTheDocument();
});

test("previous weeks are one tap away", async () => {
  const api = mockApi({ "/progress": week() });
  window.location.hash = "#/insights";
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Previous week" }));
  window.dispatchEvent(new HashChangeEvent("hashchange"));

  await waitFor(() => expect(api.calls.some((call) => call.path === "/progress" && call.search === "?week=2026-11-16")).toBe(true));
});

test("weekly review: unfinished work moves only when asked, and answers are saved with their version", async () => {
  const saved = { id: "r1", week_start_date: "2026-11-23", week_end_date: "2026-11-29", timezone_name: "UTC", wins: "Shipped", lessons: "", next_week: "", closed_at: null, archived_at: null, version: 1 };
  const api = mockApi({
    "/progress": week(),
    "/weekly-reviews": [],
    "POST /weekly-reviews": saved,
    "PATCH /weekly-reviews/r1": { ...saved, version: 2 },
    "PATCH /tasks/invoice-client": {},
  });
  window.location.hash = "#/insights/review?week=2026-11-23";
  render(<App />);

  const unfinished = await screen.findByRole("region", { name: "What was not completed" });
  expect(within(unfinished).getByText("Invoice client")).toBeInTheDocument();
  expect(api.writes()).toHaveLength(0);
  fireEvent.click(within(unfinished).getByRole("button", { name: /Carry to/ }));
  await waitFor(() => expect(api.writes()[0]).toMatchObject({ method: "PATCH", path: "/tasks/invoice-client", body: { due_date: "2026-11-30" } }));

  fireEvent.change(screen.getByLabelText("What went well?"), { target: { value: "Shipped" } });
  fireEvent.click(screen.getByRole("button", { name: "Save review" }));
  expect(await screen.findByText("Saved. Earlier versions are kept.")).toBeInTheDocument();
  expect(api.writes().at(-1)).toMatchObject({ path: "/weekly-reviews", body: { week_start_date: "2026-11-23", week_end_date: "2026-11-29", wins: "Shipped" } });

  fireEvent.change(screen.getByLabelText("Obstacles and lessons"), { target: { value: "Too many meetings" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(api.writes().at(-1)).toMatchObject({ method: "PATCH", path: "/weekly-reviews/r1", body: { expected_version: 1, lessons: "Too many meetings" } }));
});

test("Today answers what is due, what is overdue and how the week is going", async () => {
  const tasks = [
    { id: "x1", title: "Pay internet bill", status: "todo", due_date: "2026-11-20", is_deep_work_default: false, priority: 0, area: null },
    { id: "x2", title: "freeCodeCamp: JS module", status: "todo", due_date: "2026-11-24", is_deep_work_default: false, priority: 0, area: "a-learn" },
    { id: "x3", title: "Someday idea", status: "todo", due_date: null, is_deep_work_default: false, priority: 0, area: null },
  ];
  mockApi({ "/schedule/day": day(), "/tasks": tasks, "/progress": week() });
  render(<App />);

  const panel = await screen.findByRole("region", { name: "Tasks for today" });
  expect(await within(panel).findByText("Pay internet bill")).toBeInTheDocument();
  expect(within(panel).getByText("freeCodeCamp: JS module")).toBeInTheDocument();
  expect(within(panel).queryByText("Someday idea")).not.toBeInTheDocument();
  expect(within(panel).getByText("1 overdue")).toBeInTheDocument();
  expect(await screen.findByText(/75% · 3 of 4 planned done/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "New task" })).toBeInTheDocument();
});
