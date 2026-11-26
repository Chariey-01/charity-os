import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { entry, mockApi, TODAY } from "../../test/mockApi";

const items = [
  entry({ id: "a", title: "Lecture", start_local: `${TODAY}T09:00`, end_local: `${TODAY}T10:30` }),
  entry({ id: "b", title: "Podcast walk", start_local: `${TODAY}T09:30`, end_local: `${TODAY}T10:00`, color: "#C2410C" }),
  entry({ id: "c", title: "Sleep", start_local: `${TODAY}T22:30`, end_local: "2026-11-25T06:30", planned_minutes: 480 }),
  entry({ id: "d", title: "Old plan", status: "cancelled", start_local: `${TODAY}T12:00`, end_local: `${TODAY}T13:00` }),
];

test("day view places overlapping activities side by side and hides cancelled ones", async () => {
  window.location.hash = `#/schedule?view=day&date=${TODAY}`;
  const api = mockApi({ "/schedule-entries": items });
  render(<App />);
  const lecture = await screen.findByRole("button", { name: /^Lecture,/ });
  const podcast = screen.getByRole("button", { name: /^Podcast walk,/ });
  expect(lecture.style.width).toBe("calc(50% - 4px)");
  expect(podcast.style.left).toBe("calc(50% + 2px)");
  expect(screen.queryByRole("button", { name: /^Old plan,/ })).not.toBeInTheDocument();
  expect(api.calls.find((call) => call.path === "/schedule-entries")?.search).toBe(`?start=${TODAY}&end=${TODAY}`);
});

test("week view requests the Monday–Sunday range and opens a day from its header", async () => {
  window.location.hash = `#/schedule?view=week&date=${TODAY}`;
  const api = mockApi({ "/schedule-entries": items });
  render(<App />);
  expect(await screen.findByRole("heading", { name: /23.*29/ })).toBeInTheDocument();
  await waitFor(() => expect(api.calls.some((call) => call.search === "?start=2026-11-23&end=2026-11-29")).toBe(true));
  // The overnight sleep block appears on both Tuesday and Wednesday.
  expect(within(screen.getByTestId(`week-col-${TODAY}`)).getByRole("button", { name: /^Sleep/ })).toBeInTheDocument();
  expect(within(screen.getByTestId("week-col-2026-11-25")).getByRole("button", { name: /^Sleep/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Open Wednesday/ }));
  await waitFor(() => expect(window.location.hash).toBe("#/schedule?view=day&date=2026-11-25"));
});

test("month view shows activity dots and lists the selected day", async () => {
  window.location.hash = `#/schedule?view=month&date=${TODAY}`;
  const api = mockApi({ "/schedule-entries": items });
  render(<App />);
  const cell = await screen.findByRole("gridcell", { name: /24.*, 3 activities/ });
  expect(cell).toHaveAttribute("aria-selected", "true");
  expect(api.calls.some((call) => call.search === "?start=2026-10-26&end=2026-12-06")).toBe(true);
  const list = screen.getByRole("list", { name: "Activities on the selected day" });
  expect(within(list).getByText("Lecture")).toBeInTheDocument();
  fireEvent.keyDown(cell, { key: "ArrowRight" });
  await waitFor(() => expect(window.location.hash).toBe("#/schedule?view=month&date=2026-11-25"));
});

test("date navigation steps by the current view", async () => {
  window.location.hash = `#/schedule?view=day&date=${TODAY}`;
  mockApi();
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Next day" }));
  await waitFor(() => expect(window.location.hash).toBe("#/schedule?view=day&date=2026-11-25"));
});
