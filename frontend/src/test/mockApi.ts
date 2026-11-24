import { vi } from "vitest";

import type { Area, DayPayload, Entry, Preferences, User } from "../lib/types";

export const NOW = new Date("2026-11-24T10:00:00Z");
export const TODAY = "2026-11-24";

export const json = (body: unknown, status = 200) =>
  new Response(body === undefined ? "" : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export const user: User = { id: "u1", email: "owner@example.com", display_name: "Charity", timezone: "UTC" };

export const areas: Area[] = [
  { id: "a-learn", name: "Learning", slug: "learning", color: "#1D4ED8", health_kind: "", sort_order: 0, archived_at: null },
  { id: "a-personal", name: "Personal", slug: "personal", color: "#B4536A", health_kind: "", sort_order: 1, archived_at: null },
  { id: "a-ex", name: "Exercise", slug: "exercise", color: "#C2410C", health_kind: "exercise", sort_order: 2, archived_at: null },
];

export const prefs: Preferences = {
  reminders_enabled: false,
  reminder_lead_minutes: 10,
  start_reminders_enabled: true,
  daily_planning_reminder_enabled: false,
  daily_planning_time: "07:30:00",
  weekly_review_reminder_enabled: false,
  weekly_review_weekday: 7,
  weekly_review_time: "18:00:00",
  show_streaks: false,
  celebrations_enabled: true,
  default_today_view: "agenda",
};

export function entry(overrides: Partial<Entry> = {}): Entry {
  const start = overrides.start_local ?? `${TODAY}T14:00`;
  const end = overrides.end_local ?? `${TODAY}T15:00`;
  return {
    id: "e1",
    title: "Grocery shopping",
    description: "",
    notes: "",
    outcome: "",
    area: "a-personal",
    area_label: "Personal",
    color: "#B4536A",
    health_kind: "",
    start_at: `${start}:00Z`,
    end_at: `${end}:00Z`,
    start_local: start,
    end_local: end,
    timezone_name: "UTC",
    local_date: start.slice(0, 10),
    planned_minutes: 60,
    status: "scheduled",
    tracking: "manual",
    task: null,
    task_title: "",
    task_status: null,
    roadmap_node: null,
    roadmap_node_title: "",
    focus_session: null,
    focus_session_status: null,
    focus_session_version: null,
    actual_started_at: null,
    actual_ended_at: null,
    actual_seconds: null,
    actual_minutes: null,
    paused_at: null,
    closed_at: null,
    rescheduled_from: null,
    rescheduled_to: null,
    version: 1,
    ...overrides,
  };
}

export function day(entries: Entry[] = [], overrides: Partial<DayPayload> = {}): DayPayload {
  const done = entries.filter((item) => item.status === "completed").length;
  return {
    date: TODAY,
    today: TODAY,
    timezone: "UTC",
    challenge: {
      id: "c1",
      name: "Road to 2027",
      start_date: "2026-09-27",
      end_date: "2026-12-31",
      phase: "active",
      current_day: 59,
      total_days: 96,
      days_remaining: 37,
      progress_percent: 61.5,
      completed_activities: done,
      focus_minutes: 0,
      active_days: 1,
    },
    entries,
    progress: {
      planned: entries.length,
      completed: done,
      partially_completed: 0,
      skipped: 0,
      in_progress: 0,
      remaining: entries.length - done,
      planned_minutes: entries.reduce((sum, item) => sum + item.planned_minutes, 0),
      actual_minutes: 0,
    },
    capacity: { available_minutes: 480, deep_work_minutes: 240, scheduled_minutes: 120, remaining_minutes: 360 },
    unscheduled_tasks: [],
    active_session_entry: null,
    week: {
      week_start: "2026-11-23",
      week_end: "2026-11-29",
      completed: done,
      planned: entries.length,
      active_days: done ? 1 : 0,
      milestones: [
        { target: 3, reached: done >= 3 },
        { target: 7, reached: false },
        { target: 12, reached: false },
      ],
      next_milestone: done >= 3 ? 7 : 3,
      badges: [],
      streak_weeks: null,
    },
    ...overrides,
  };
}

type Call = { method: string; path: string; search: string; body: Record<string, unknown> | undefined };
type Handler = unknown | ((call: Call) => unknown);

/**
 * Routes "METHOD /path" (or "/path" for GET) to fixed bodies, functions or
 * Responses. Unknown GETs return [] and unknown writes return {}.
 */
export function mockApi(routes: Record<string, Handler> = {}) {
  const calls: Call[] = [];
  const table: Record<string, Handler> = {
    "/me": user,
    "/areas": areas,
    "/preferences": prefs,
    "/sessions/active": undefined,
    "/schedule/day": day(),
    ...routes,
  };
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const call: Call = {
      method,
      path: url.pathname.replace(/^\/api\/v1/, ""),
      search: url.search,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const key = `${method} ${call.path}`;
    const handler = key in table ? table[key] : method === "GET" && call.path in table ? table[call.path] : method === "GET" ? [] : {};
    const result = typeof handler === "function" ? await (handler as (call: Call) => unknown)(call) : handler;
    return result instanceof Response ? result : json(result);
  });
  return { spy, calls, writes: () => calls.filter((call) => call.method !== "GET") };
}
