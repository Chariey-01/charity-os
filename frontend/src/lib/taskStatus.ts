/**
 * Task status helpers.
 *
 * Tasks are moving from planned/completed/skipped to the workflow
 * backlog/todo/in_progress/in_review/blocked/done/cancelled
 * (docs/project-workspaces-design.md §13). The client accepts both so it
 * keeps working across the migration and with cached legacy data.
 */
export const OPEN_TASK_STATUSES: ReadonlySet<string> = new Set([
  "planned",
  "backlog",
  "todo",
  "in_progress",
  "in_review",
  "blocked",
]);

export function isTaskOpen(status: string | null | undefined) {
  return Boolean(status && OPEN_TASK_STATUSES.has(status));
}

export function isTaskDone(status: string | null | undefined) {
  return status === "done" || status === "completed";
}
