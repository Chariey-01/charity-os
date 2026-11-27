import { describe, expect, it } from "vitest";

import { deferOptions, dueLabel, groupOf, groupTasks, isOpen } from "./tasks";
import type { Task } from "./types";

const TODAY = "2026-11-26"; // a Thursday

function task(overrides: Partial<Task>): Task {
  return { id: overrides.title ?? "t", title: "t", status: "todo", is_deep_work_default: false, ...overrides };
}

describe("task groups", () => {
  it("puts due dates first, then status", () => {
    expect(groupOf(task({ due_date: "2026-11-20" }), TODAY)).toBe("overdue");
    expect(groupOf(task({ due_date: TODAY }), TODAY)).toBe("today");
    expect(groupOf(task({ status: "in_progress" }), TODAY)).toBe("today");
    expect(groupOf(task({ due_date: "2026-11-30" }), TODAY)).toBe("upcoming");
    expect(groupOf(task({ status: "backlog" }), TODAY)).toBe("backlog");
    expect(groupOf(task({ status: "backlog", due_date: "2026-11-20" }), TODAY)).toBe("overdue");
    expect(groupOf(task({}), TODAY)).toBe("anytime");
  });

  it("leaves out finished and archived tasks and empty groups, and sorts by date then priority", () => {
    const groups = groupTasks(
      [
        task({ title: "low", due_date: "2026-11-30", priority: 1 }),
        task({ title: "high", due_date: "2026-11-30", priority: 3 }),
        task({ title: "sooner", due_date: "2026-11-28" }),
        task({ title: "done", status: "done", due_date: "2026-11-20" }),
        task({ title: "archived", archived_at: "2026-11-25T10:00:00Z" }),
      ],
      TODAY,
    );
    expect(groups.map((group) => group.key)).toEqual(["upcoming"]);
    expect(groups[0].tasks.map((item) => item.title)).toEqual(["sooner", "high", "low"]);
  });

  it("knows which tasks are open", () => {
    expect(isOpen(task({ status: "blocked" }))).toBe(true);
    expect(isOpen(task({ status: "cancelled" }))).toBe(false);
  });
});

describe("dates", () => {
  it("labels due dates relative to today", () => {
    expect(dueLabel(TODAY, TODAY)).toBe("Today");
    expect(dueLabel("2026-11-27", TODAY)).toBe("Tomorrow");
    expect(dueLabel("2026-11-25", TODAY)).toBe("Yesterday");
    expect(dueLabel("2026-11-21", TODAY)).toBe("5 days overdue");
    expect(dueLabel("2026-12-03", TODAY)).toMatch(/3/);
  });

  it("offers tomorrow and the start of next week", () => {
    expect(deferOptions(TODAY)).toEqual([
      { label: "Tomorrow", date: "2026-11-27" },
      { label: "Next week", date: "2026-11-30" },
    ]);
  });
});
