import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { day, entry, json, mockApi, TODAY } from "../../test/mockApi";

const study = entry({ id: "study", title: "Study algorithms", area: "a-learn", area_label: "Learning", color: "#1D4ED8", start_local: `${TODAY}T08:00`, end_local: `${TODAY}T09:30`, planned_minutes: 90, tracking: "focus" });
const shop = entry({ id: "shop", title: "Grocery shopping", start_local: `${TODAY}T14:00`, end_local: `${TODAY}T15:00` });
const gym = entry({ id: "gym", title: "Evening cycling", area: "a-ex", area_label: "Exercise", start_local: `${TODAY}T18:00`, end_local: `${TODAY}T19:00`, status: "completed", actual_seconds: 2700, actual_minutes: 45 });

test("daily schedule shows date, challenge, progress, capacity and grouped activities", async () => {
  mockApi({ "/schedule/day": day([study, shop, gym]) });
  render(<App />);

  expect(await screen.findByRole("heading", { level: 1, name: /24 November|November 24/ })).toBeInTheDocument();
  expect(screen.getByText(/Day 59 of 96/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "1 of 3 activities done" })).toBeInTheDocument();
  expect(screen.getByText("1 of 3 done")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: /capacity/ })).toHaveAttribute("aria-valuenow", "120");
  expect(screen.getByText(/6h free of 8h/)).toBeInTheDocument();

  // 10:00 UTC: the morning study is unmarked, shopping is next.
  const earlier = screen.getByRole("list", { name: "Earlier, not yet marked" });
  expect(within(earlier).getByText("Study algorithms")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Next activity" })).toHaveTextContent("Grocery shopping");
  const completed = screen.getByText("Completed").closest("details")!;
  expect(within(completed).getByText("Evening cycling")).toBeInTheDocument();
  expect(within(completed).getByText(/45m/)).toBeInTheDocument();
});

test("switches between agenda, timeline and day views", async () => {
  mockApi({ "/schedule/day": day([study, shop]) });
  render(<App />);
  await screen.findByText("Up next");

  fireEvent.click(screen.getByRole("tab", { name: "Timeline" }));
  expect(screen.getByRole("list", { name: "Timeline" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Day" }));
  expect(screen.getByRole("button", { name: /Study algorithms, .* to .*scheduled/ })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /^Add activity at/ })).toHaveLength(24);
});

test("empty day offers quick add", async () => {
  mockApi({ "/schedule/day": day([]) });
  render(<App />);
  expect(await screen.findByText("A clear day")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add an activity" }));
  expect(await screen.findByRole("dialog", { name: "Quick add" })).toBeInTheDocument();
});

test("error state retries", async () => {
  let fail = true;
  mockApi({ "/schedule/day": () => (fail ? json({ detail: "Server unavailable" }, 503) : day([shop])) });
  render(<App />);
  expect(await screen.findByText("Server unavailable")).toBeInTheDocument();
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Grocery shopping", { selector: ".entry-title" })).toBeInTheDocument();
});

test("current activity shows a live timer with pause and finish", async () => {
  const running = { ...study, status: "in_progress" as const, focus_session: "s1", focus_session_status: "active", actual_seconds: 125 };
  const api = mockApi({
    "/schedule/day": day([running, shop]),
    "/sessions/active": { id: "s1", title: running.title, status: "active", started_at: "2026-11-24T09:57:55Z", version: 1, elapsed_seconds: 125, area: "a-learn", schedule_entry: "study" },
    "POST /schedule-entries/study/pause": { ...running, status: "paused" },
  });
  render(<App />);
  const card = await screen.findByRole("region", { name: "Current activity" });
  expect(within(card).getByTestId("current-timer")).toHaveTextContent("00:02:05");
  // The Today card replaces the global focus bar for an entry-linked session.
  expect(screen.queryByRole("region", { name: "Focus session" })).not.toBeInTheDocument();

  fireEvent.click(within(card).getByRole("button", { name: "Pause" }));
  await waitFor(() => expect(api.writes().map((call) => call.path)).toContain("/schedule-entries/study/pause"));
  expect(api.writes()[0].body).toMatchObject({ expected_version: 1 });
  expect(api.writes()[0].body?.pause_id).toEqual(expect.any(String));
});

test("unscheduled tasks can be scheduled with the task linked", async () => {
  mockApi({
    "/schedule/day": day([shop], {
      unscheduled_tasks: [{ id: "t1", title: "Write essay", area: "a-learn", area_label: "Learning", color: "#1D4ED8", estimated_minutes: null, roadmap_item: null, plan_kind: "primary", is_deep_work_default: true }],
    }),
  });
  render(<App />);
  const section = (await screen.findByText("Unscheduled tasks")).closest("details")!;
  fireEvent.click(within(section).getByText("Unscheduled tasks"));
  expect(within(section).getByLabelText("Primary outcome")).toBeInTheDocument();
  fireEvent.click(within(section).getByRole("button", { name: "Schedule" }));
  const dialog = await screen.findByRole("dialog", { name: "Quick add" });
  expect(within(dialog).getByLabelText("Title", { exact: true })).toHaveValue("Write essay");
  expect(within(dialog).getByRole("radio", { name: /Learning/ })).toHaveAttribute("aria-checked", "true");
  expect(within(dialog).getByRole("switch", { name: "Track with the focus timer" })).toBeChecked();
});

test("weekly milestones are shown without penalty language", async () => {
  mockApi({ "/schedule/day": day([{ ...shop, status: "completed" }]) });
  render(<App />);
  const strip = await screen.findByRole("region", { name: "This week" });
  expect(within(strip).getByText(/Next milestone: 3/)).toBeInTheDocument();
  expect(strip.textContent).not.toMatch(/missed|failed|broke/i);
});
