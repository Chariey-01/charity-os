export type User = { id: string; email: string; display_name: string; timezone: string };

export type Area = {
  id: string;
  name: string;
  slug: string;
  color: string;
  health_kind: "" | "exercise" | "sleep";
  sort_order: number;
  archived_at: string | null;
};

export type EntryStatus =
  | "scheduled"
  | "in_progress"
  | "paused"
  | "completed"
  | "partially_completed"
  | "skipped"
  | "cancelled"
  | "rescheduled";

export type Entry = {
  id: string;
  title: string;
  description: string;
  notes: string;
  outcome: string;
  area: string | null;
  area_label: string;
  color: string;
  health_kind: string;
  start_at: string;
  end_at: string;
  start_local: string;
  end_local: string;
  timezone_name: string;
  local_date: string;
  planned_minutes: number;
  status: EntryStatus;
  tracking: "manual" | "focus";
  task: string | null;
  task_title: string;
  task_status: string | null;
  roadmap_node: string | null;
  roadmap_node_title: string;
  focus_session: string | null;
  focus_session_status: string | null;
  focus_session_version: number | null;
  actual_started_at: string | null;
  actual_ended_at: string | null;
  actual_seconds: number | null;
  actual_minutes: number | null;
  paused_at: string | null;
  closed_at: string | null;
  rescheduled_from: string | null;
  rescheduled_to: string | null;
  version: number;
};

export type ChallengeProgress = {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  phase: "upcoming" | "active" | "completed";
  current_day: number;
  total_days: number;
  days_remaining: number;
  progress_percent: number;
  completed_activities: number;
  focus_minutes: number;
  active_days: number;
};

export type Badge = { key: string; title: string; description: string; earned: boolean };

export type WeekSummary = {
  week_start: string;
  week_end: string;
  completed: number;
  planned: number;
  active_days: number;
  milestones: { target: number; reached: boolean }[];
  next_milestone: number | null;
  badges: Badge[];
  streak_weeks: number | null;
};

export type UnscheduledTask = {
  id: string;
  title: string;
  area: string | null;
  area_label: string;
  color: string;
  estimated_minutes: number | null;
  roadmap_item: string | null;
  plan_kind: "primary" | "secondary" | null;
  is_deep_work_default: boolean;
};

export type DayPayload = {
  date: string;
  today: string;
  timezone: string;
  challenge: ChallengeProgress | null;
  entries: Entry[];
  progress: {
    planned: number;
    completed: number;
    partially_completed: number;
    skipped: number;
    in_progress: number;
    remaining: number;
    planned_minutes: number;
    actual_minutes: number;
  };
  capacity: {
    available_minutes: number | null;
    deep_work_minutes: number | null;
    scheduled_minutes: number;
    remaining_minutes: number | null;
  };
  unscheduled_tasks: UnscheduledTask[];
  active_session_entry: string | null;
  week: WeekSummary;
};

export type Session = {
  id: string;
  title: string;
  status: "active" | "paused" | "completed" | "cancelled";
  started_at: string;
  version: number;
  elapsed_seconds: number;
  task?: string | null;
  roadmap_item?: string | null;
  area: string;
};

export type Preferences = {
  reminders_enabled: boolean;
  reminder_lead_minutes: number;
  start_reminders_enabled: boolean;
  daily_planning_reminder_enabled: boolean;
  daily_planning_time: string;
  weekly_review_reminder_enabled: boolean;
  weekly_review_weekday: number;
  weekly_review_time: string;
  show_streaks: boolean;
  celebrations_enabled: boolean;
  default_today_view: "agenda" | "timeline" | "day";
};

export type Challenge = {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  is_primary: boolean;
  total_days: number;
  current_day: number;
  days_remaining: number;
  progress_percent: number;
  phase: string;
};

export type TaskStatus = "backlog" | "todo" | "in_progress" | "in_review" | "blocked" | "done" | "cancelled";

export type Task = {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus | string;
  area?: string | null;
  roadmap_item?: string | null;
  priority?: number;
  due_date?: string | null;
  estimated_minutes?: number | null;
  completed_at?: string | null;
  archived_at?: string | null;
  created_at?: string;
  is_deep_work_default: boolean;
};

export type ProgressTask = {
  id: string;
  title: string;
  area: string | null;
  label: string;
  color: string;
  due_date: string | null;
  status: string;
  status_now: string;
  archived_now: boolean;
  planned: boolean;
  completed_on: string | null;
};

export type WeeklyNumbers = {
  planned: number;
  completed: number;
  outstanding: number;
  completion_percent: number | null;
  unplanned_completed: number;
  completed_total: number;
};

export type Progress = {
  today: string;
  week: { start: string; end: string; is_current: boolean; is_future: boolean; as_of: string };
  overall: { completed: number; remaining: number; overdue: number; due_today: number; completion_percent: number | null };
  weekly: WeeklyNumbers & { previous: WeeklyNumbers };
  workstreams: {
    completed_tasks: { area: string | null; label: string; color: string; count: number }[];
    time: { area: string | null; label: string; color: string; actual_minutes: number }[];
  };
  tasks: { planned: ProgressTask[]; completed: ProgressTask[] };
  accomplishments: {
    completed_tasks: ProgressTask[];
    milestones: { id: string; title: string; kind: string; roadmap: string; completed_on: string }[];
    focus_minutes: number;
    focus_sessions: number;
    roadmaps_advanced: string[];
    learning: { roadmap_items_completed: number; roadmap_tasks_completed: number };
    evidence_recorded: number;
    accomplishments: { id: string; title: string; local_date: string }[];
  };
};

export type WeeklyReview = {
  id: string;
  week_start_date: string;
  week_end_date: string;
  timezone_name: string;
  wins: string;
  lessons: string;
  next_week: string;
  closed_at: string | null;
  archived_at: string | null;
  version: number;
};

export type DayStats = {
  date: string;
  planned: number;
  completed: number;
  partially_completed: number;
  skipped: number;
  cancelled: number;
  rescheduled: number;
  open: number;
};

export type Insights = {
  period: { label: string; start: string; end: string; days: number };
  totals: {
    planned: number;
    completed: number;
    partially_completed: number;
    skipped: number;
    rescheduled: number;
    cancelled: number;
    focus_minutes: number;
    tracked_minutes: number;
    active_days: number;
  };
  schedule_daily: DayStats[];
  schedule_weekly: {
    week_start: string;
    planned: number;
    completed: number;
    focus_minutes: number;
    active_days: number;
    days_in_range: number;
  }[];
  category_time: {
    area: string | null;
    label: string;
    color: string;
    planned_minutes: number;
    actual_minutes: number;
    activities: number;
  }[];
  focus_daily: { date: string; minutes: number }[];
  health: {
    exercise_daily: { date: string; minutes: number }[];
    sleep_daily: { date: string; hours: number }[];
    activities_from_schedule: { exercise: number; sleep: number };
  };
  challenge: ChallengeProgress | null;
  week: WeekSummary;
};

export type Roadmap = { id: string; title: string; description: string; status: string; area?: string | null };

export type RoadmapNode = {
  id: string;
  title: string;
  description: string;
  node_type: string;
  state: string;
  time_invested_seconds: number;
  linked_task_ids: string[];
  resources: { id: string; label: string; url: string }[];
  evidence_count: number;
  children: RoadmapNode[];
};

export type QuickAddDefaults = {
  title?: string;
  date?: string;
  start?: string;
  end?: string;
  area?: string | null;
  task?: string | null;
  roadmap_node?: string | null;
  tracking?: "manual" | "focus";
};
