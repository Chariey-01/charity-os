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
  goal?: string | null;
  milestone?: string | null;
  project?: string | null;
  checklist?: ChecklistItem[];
  notes?: string;
};

export type ChecklistItem = { id: string; text: string; done: boolean };

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

export type Roadmap = {
  id: string;
  title: string;
  description: string;
  status: string;
  area?: string | null;
  purpose?: string;
  notes?: string;
  start_date?: string | null;
  target_date?: string | null;
  goal?: string | null;
  archived_at?: string | null;
};

export type RoadmapNode = {
  id: string;
  title: string;
  description: string;
  node_type: string;
  state: string;
  completion_criteria?: string;
  notes?: string;
  completed_at?: string | null;
  position?: number;
  time_invested_seconds: number;
  linked_task_ids: string[];
  resources: { id: string; label: string; url: string; kind?: string; notes?: string }[];
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

export type VisionKind = "vision" | "aspiration" | "manifestation" | "identity";
export type Horizon = "short" | "medium" | "long" | "lifetime";

export type VisionItem = {
  id: string;
  kind: VisionKind;
  title: string;
  statement: string;
  theme: string;
  horizon: Horizon;
  success_looks_like: string;
  notes: string;
  image_url: string;
  target_year: number | null;
  status: "active" | "realised" | "released";
  realised_at: string | null;
  realised_note: string;
  realised_evidence_url: string;
  position: number;
  version: number;
  goals_count: number;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type VisionRevision = { id: string; version: number; title: string; statement: string; success_looks_like: string; created_at: string };

export type GoalProgress = {
  ratio: number | null;
  basis: "measure" | "milestones" | "none";
  latest_value: string | null;
  milestones_total: number;
  milestones_done: number;
  tasks_total: number;
  tasks_done: number;
  overdue: boolean;
  at_risk: boolean;
  days_left: number | null;
};

export type GoalStatus = "active" | "paused" | "completed" | "released";

export type Goal = {
  id: string;
  title: string;
  description: string;
  why: string;
  area: string | null;
  vision: string | null;
  vision_title: string | null;
  kind: "measurable" | "qualitative";
  metric_unit: string;
  baseline_value: string | null;
  target_value: string | null;
  start_date: string | null;
  target_date: string | null;
  status: GoalStatus;
  completed_at: string | null;
  completion_note: string;
  archived_at: string | null;
  progress: GoalProgress;
  created_at: string;
};

export type CheckIn = { id: string; goal: string; local_date: string; value: string | null; note: string; created_at: string };

export type Milestone = {
  id: string;
  goal: string | null;
  project: string | null;
  title: string;
  description: string;
  target_date: string | null;
  status: "open" | "done";
  completed_at: string | null;
  completion_note: string;
  position: number;
  archived_at: string | null;
  tasks_total: number;
  tasks_done: number;
  overdue: boolean;
};

export type ProjectStatus = "planning" | "active" | "on_hold" | "completed" | "cancelled";

export type Project = {
  id: string;
  name: string;
  description: string;
  notes: string;
  area: string | null;
  goal: string | null;
  goal_title: string | null;
  status: ProjectStatus;
  priority: number;
  start_date: string | null;
  deadline: string | null;
  color: string;
  completed_at: string | null;
  archived_at: string | null;
  counts: { tasks: number; open: number; done: number; overdue: number; milestones: number; milestones_done: number };
};

export type ActivityEvent = {
  id: string;
  subject_type: string;
  subject_id: string;
  kind: string;
  title: string;
  data: Record<string, unknown>;
  occurred_at: string;
};

export type JournalKind = "reflection" | "decision" | "challenge" | "lesson" | "moment" | "review";

export type JournalEntry = {
  id: string;
  kind: JournalKind;
  title: string;
  body: string;
  local_date: string;
  goal: string | null;
  project: string | null;
  revisions: { title: string; body: string; replaced_at: string }[];
  archived_at: string | null;
};

export type JourneyEntry = {
  id: string;
  type: string;
  title: string;
  date: string;
  occurred_at: string;
  subject_type?: string;
  subject_id?: string;
  detail: Record<string, unknown>;
};

export type Journey = {
  year: number;
  years: number[];
  summary: Record<string, number>;
  months: { month: string; tasks_completed: number; focus_minutes: number; top_areas: [string, number][] }[];
  chapters: { id: string; name: string; start_date: string; end_date: string; status: string; archived: boolean; total_days: number }[];
  entries: JourneyEntry[];
  truncated: boolean;
};

export type RoadmapTemplate = { key: string; title: string; summary: string; stages: string[] };
