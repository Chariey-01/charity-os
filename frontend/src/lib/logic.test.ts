import { expect, test } from "vitest";

import { TODAY } from "../test/mockApi";
import { addDays, instantFrom, localRange, monthGrid, spanWithin, weekStart, zoned } from "./time";
import { niceTicks } from "./format";

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

test("chart ticks are rounded", () => {
  expect(niceTicks(95)).toEqual([0, 50, 100]);
  expect(niceTicks(3)).toEqual([0, 1, 2, 3]);
});
