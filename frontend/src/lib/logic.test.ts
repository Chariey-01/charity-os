import { expect, test } from "vitest";

import { layoutDay } from "../features/schedule/hooks";
import { entry, TODAY } from "../test/mockApi";
import { buildReminders, dueReminders } from "./reminders";
import { addDays, instantFrom, localRange, monthGrid, spanWithin, weekStart, zoned } from "./time";
import { niceTicks } from "./format";
import { prefs } from "../test/mockApi";

test("zoned formats instants in the user's timezone, not the device's", () => {
  expect(zoned("2026-11-24T22:30:00Z", "Africa/Nairobi")).toMatchObject({ date: "2026-11-25", hhmm: "01:30" });
  expect(zoned("2026-11-24T22:30:00Z", "America/New_York")).toMatchObject({ date: "2026-11-24", hhmm: "17:30" });
});

test("instantFrom converts local wall-clock times including across DST", () => {
  expect(instantFrom("2026-11-24", "09:00", "Africa/Nairobi")).toBe("2026-11-24T06:00:00.000Z");
  expect(instantFrom("2026-07-01", "09:00", "America/New_York")).toBe("2026-07-01T13:00:00.000Z");
  expect(instantFrom("2026-12-01", "09:00", "America/New_York")).toBe("2026-12-01T14:00:00.000Z");
});

test("local ranges ending before they start continue into the next day", () => {
  expect(localRange(TODAY, "22:30", "06:30")).toEqual({ start_local: `${TODAY}T22:30`, end_local: "2026-11-25T06:30", crossesMidnight: true });
  expect(localRange(TODAY, "08:00", "09:30").crossesMidnight).toBe(false);
});

test("date helpers for week and month grids", () => {
  expect(weekStart(TODAY)).toBe("2026-11-23");
  expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  const grid = monthGrid(TODAY);
  expect(grid).toHaveLength(42);
  expect(grid[0]).toBe("2026-10-26");
});

test("spans are clipped to the requested day", () => {
  expect(spanWithin(`${TODAY}T22:30:00Z`, "2026-11-25T06:30:00Z", TODAY, "UTC")).toEqual({ from: 1350, to: 1440 });
  expect(spanWithin(`${TODAY}T22:30:00Z`, "2026-11-25T06:30:00Z", "2026-11-25", "UTC")).toEqual({ from: 0, to: 390 });
});

test("overlapping entries share columns; separate clusters reset", () => {
  const placed = layoutDay(
    [
      entry({ id: "a", start_local: `${TODAY}T09:00`, end_local: `${TODAY}T11:00` }),
      entry({ id: "b", start_local: `${TODAY}T09:30`, end_local: `${TODAY}T10:00` }),
      entry({ id: "c", start_local: `${TODAY}T10:00`, end_local: `${TODAY}T10:30` }),
      entry({ id: "d", start_local: `${TODAY}T12:00`, end_local: `${TODAY}T13:00` }),
    ],
    TODAY,
    "UTC",
  );
  const byId = Object.fromEntries(placed.map((item) => [item.entry.id, item]));
  expect(byId.a).toMatchObject({ column: 0, columns: 2 });
  expect(byId.b).toMatchObject({ column: 1, columns: 2 });
  expect(byId.c).toMatchObject({ column: 1, columns: 2 });
  expect(byId.d).toMatchObject({ column: 0, columns: 1 });
});

test("reminders: lead and start times for scheduled entries, deduplicated once fired", () => {
  const items = [entry({ id: "x", start_local: `${TODAY}T14:00`, end_local: `${TODAY}T15:00` }), entry({ id: "y", status: "completed" })];
  const reminders = buildReminders(items, { ...prefs, reminders_enabled: true, reminder_lead_minutes: 15, daily_planning_reminder_enabled: true }, TODAY, "UTC");
  expect(reminders.map((item) => item.key)).toEqual([`lead:x:${TODAY}T14:00:00Z`, `start:x:${TODAY}T14:00:00Z`, `plan:${TODAY}`]);
  const lead = Date.parse(`${TODAY}T13:45:00Z`);
  expect(dueReminders(reminders, lead + 1000, new Set()).map((item) => item.title)).toEqual(["Grocery shopping in 15 min"]);
  expect(dueReminders(reminders, lead + 1000, new Set([`lead:x:${TODAY}T14:00:00Z`]))).toEqual([]);
  expect(dueReminders(reminders, lead + 11 * 60_000, new Set())).toEqual([]);
  expect(buildReminders(items, prefs, TODAY, "UTC")).toEqual([]);
});

test("chart ticks are rounded", () => {
  expect(niceTicks(95)).toEqual([0, 50, 100]);
  expect(niceTicks(3)).toEqual([0, 1, 2, 3]);
});
