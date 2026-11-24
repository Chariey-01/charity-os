import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { day, mockApi } from "../../test/mockApi";
import type { Insights } from "../../lib/types";

const dates = ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24"];

function insights(label = "7d"): Insights {
  return {
    period: { label, start: dates[0], end: dates[6], days: 7 },
    totals: { planned: 5, completed: 3, partially_completed: 1, skipped: 1, rescheduled: 1, cancelled: 0, focus_minutes: 95, tracked_minutes: 200, active_days: 3 },
    schedule_daily: dates.map((date, index) => ({ date, planned: index > 3 ? 2 : 0, completed: index > 4 ? 2 : 0, partially_completed: 0, skipped: 0, cancelled: 0, rescheduled: 0, open: 0 })),
    schedule_weekly: [
      { week_start: "2026-11-16", planned: 1, completed: 0, focus_minutes: 0, active_days: 0, days_in_range: 5 },
      { week_start: "2026-11-23", planned: 4, completed: 4, focus_minutes: 95, active_days: 2, days_in_range: 2 },
    ],
    category_time: [
      { area: "a-learn", label: "Learning", color: "#1D4ED8", planned_minutes: 120, actual_minutes: 95, activities: 2 },
      { area: "a-ex", label: "Exercise", color: "#C2410C", planned_minutes: 60, actual_minutes: 45, activities: 1 },
    ],
    focus_daily: dates.map((date, index) => ({ date, minutes: index === 6 ? 95 : 0 })),
    health: {
      exercise_daily: dates.map((date, index) => ({ date, minutes: index === 6 ? 45 : 0 })),
      sleep_daily: dates.map((date) => ({ date, hours: 0 })),
      activities_from_schedule: { exercise: 1, sleep: 0 },
    },
    challenge: { ...day().challenge!, completed_activities: 4, focus_minutes: 95, active_days: 3 },
    week: { ...day().week, completed: 4, active_days: 2, badges: [{ key: "first_step", title: "First step", description: "Completed your first scheduled activity.", earned: true }, { key: "rested", title: "Well rested", description: "Five nights.", earned: false }] },
  };
}

test("insights show totals, charts, categories and a separate health section", async () => {
  window.location.hash = "#/insights";
  mockApi({ "/insights": insights() });
  render(<App />);
  const totals = await screen.findByRole("region", { name: "Totals" });
  expect(within(totals).getByText("4")).toBeInTheDocument();
  expect(within(totals).getByText("of 5 planned")).toBeInTheDocument();
  expect(within(totals).getByText("1h 35m")).toBeInTheDocument();
  expect(screen.getByText(/1 rescheduled and 1 skipped/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Planned vs completed\. 7 periods/ })).toBeInTheDocument();
  expect(screen.getByText("Learning")).toBeInTheDocument();
  const health = screen.getByRole("region", { name: "Health" });
  expect(within(health).getByText("Exercise minutes")).toBeInTheDocument();
  expect(within(health).getByText("No sleep recorded in this range.")).toBeInTheDocument();
  expect(screen.getByText(/No composite score/)).toBeInTheDocument();
});

test("charts expose a keyboard tooltip and a table view", async () => {
  window.location.hash = "#/insights";
  mockApi({ "/insights": insights() });
  render(<App />);
  const plot = await screen.findByRole("img", { name: /Focus minutes per day/ });
  fireEvent.keyDown(plot, { key: "ArrowLeft" });
  expect(within(plot.parentElement!).getByRole("status")).toHaveTextContent("95 min");
  const figure = plot.closest("figure")!;
  fireEvent.click(within(figure).getByRole("button", { name: "Table" }));
  const table = within(figure).getByRole("table");
  expect(within(table).getAllByRole("row")).toHaveLength(8);
});

test("changing the range refetches with the selected period", async () => {
  window.location.hash = "#/insights";
  const api = mockApi({ "/insights": (call: { search: string }) => insights(new URLSearchParams(call.search).get("period") ?? "30d") });
  render(<App />);
  await screen.findByRole("region", { name: "Totals" });
  for (const [label, period] of [["7 days", "7d"], ["90 days", "90d"], ["Challenge", "challenge"], ["This year", "year"], ["All time", "all"]]) {
    fireEvent.click(screen.getByRole("radio", { name: label }));
    await waitFor(() => expect(api.calls.some((call) => call.path === "/insights" && call.search === `?period=${period}`)).toBe(true));
  }
  expect(screen.getByRole("radio", { name: "All time" })).toHaveAttribute("aria-checked", "true");
});

test("badges are collapsed and milestones are listed", async () => {
  window.location.hash = "#/insights";
  mockApi({ "/insights": insights() });
  render(<App />);
  const week = await screen.findByRole("region", { name: "This week" });
  expect(within(week).getByText("1 of 2")).toBeInTheDocument();
  expect(within(week).getByRole("list", { name: "Weekly milestones" }).children).toHaveLength(3);
});
