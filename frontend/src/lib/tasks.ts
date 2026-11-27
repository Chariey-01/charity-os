import { addDays, daysBetween, formatDate, weekStart } from "./time";
import type { Task } from "./types";

export const OPEN_STATUSES = ["backlog", "todo", "in_progress", "in_review", "blocked"] as const;

export const STATUS_LABEL: Record<string, string> = {
  backlog: "Backlog",
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

/** Task.priority is a small integer; 0 means no priority was set. */
export const PRIORITIES = [
  { value: 0, label: "None" },
  { value: 1, label: "Low" },
  { value: 2, label: "Medium" },
  { value: 3, label: "High" },
] as const;

export function priorityLabel(priority: number | undefined) {
  return PRIORITIES.find((option) => option.value === priority)?.label ?? "None";
}

export function isOpen(task: Task) {
  return (OPEN_STATUSES as readonly string[]).includes(task.status) && !task.archived_at;
}

export type GroupKey = "overdue" | "today" | "upcoming" | "anytime" | "backlog";

export const GROUP_TITLE: Record<GroupKey, string> = {
  overdue: "Overdue",
  today: "Today",
  upcoming: "Upcoming",
  anytime: "No date",
  backlog: "Backlog",
};

/** Where an open task belongs on the task list. Due dates win over status. */
export function groupOf(task: Task, today: string): GroupKey {
  if (task.due_date && task.due_date < today) return "overdue";
  if (task.due_date === today || (!task.due_date && task.status === "in_progress")) return "today";
  if (task.due_date) return "upcoming";
  return task.status === "backlog" ? "backlog" : "anytime";
}

function compare(a: Task, b: Task) {
  return (
    (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999") ||
    (b.priority ?? 0) - (a.priority ?? 0) ||
    (a.created_at ?? "").localeCompare(b.created_at ?? "")
  );
}

/** Open, unarchived tasks in display groups; empty groups are left out. */
export function groupTasks(tasks: Task[], today: string) {
  const order: GroupKey[] = ["overdue", "today", "upcoming", "anytime", "backlog"];
  const groups = new Map<GroupKey, Task[]>(order.map((key) => [key, []]));
  for (const task of tasks) if (isOpen(task)) groups.get(groupOf(task, today))!.push(task);
  return order
    .map((key) => ({ key, title: GROUP_TITLE[key], tasks: [...groups.get(key)!].sort(compare) }))
    .filter((group) => group.tasks.length > 0);
}

/** "Today", "Tomorrow", "2 days overdue", "Mon 30 Nov". */
export function dueLabel(due: string, today: string) {
  const days = daysBetween(today, due);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  if (days < 0) return `${-days} days overdue`;
  return formatDate(due, { weekday: "short", day: "numeric", month: "short" });
}

/** Choices offered by "Defer": never a silent change, always the user's tap. */
export function deferOptions(today: string, startsOn = 1) {
  return [
    { label: "Tomorrow", date: addDays(today, 1) },
    { label: "Next week", date: addDays(weekStart(today, startsOn), 7) },
  ];
}
