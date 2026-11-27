import { FormEvent, useEffect, useRef, useState } from "react";

import { useApp } from "../../app/context";
import { ErrorState, Icon, Loading, Sheet } from "../../components/ui";
import { ApiError, api, newId, patch, post } from "../../lib/api";
import { PRIORITIES, STATUS_LABEL, deferOptions, dueLabel, isOpen, priorityLabel } from "../../lib/tasks";
import { addDays, durationLabel } from "../../lib/time";
import type { ChecklistItem, Entry, Goal, Milestone, Project, Roadmap, RoadmapNode, Task } from "../../lib/types";

export type TaskSheetMode = "view" | "edit";

type Draft = {
  title: string;
  description: string;
  area: string;
  roadmap: string;
  roadmap_item: string;
  priority: number;
  due_date: string;
  estimated_minutes: string;
  status: string;
  project: string;
  goal: string;
  milestone: string;
};

const EDITABLE_STATUSES = ["backlog", "todo", "in_progress", "in_review", "blocked", "done"];

function draftOf(task: Partial<Task> | null): Draft {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    area: task?.area ?? "",
    roadmap: "",
    roadmap_item: task?.roadmap_item ?? "",
    priority: task?.priority ?? 0,
    due_date: task?.due_date ?? "",
    estimated_minutes: task?.estimated_minutes ? String(task.estimated_minutes) : "",
    status: task?.status ?? "todo",
    project: task?.project ?? "",
    goal: task?.goal ?? "",
    milestone: task?.milestone ?? "",
  };
}

/** Create, view and act on one task. Every field but the title is optional. */
export function TaskSheet({
  taskId,
  defaults,
  initialMode,
  onClose,
}: {
  taskId: string | null;
  defaults?: Partial<Task>;
  initialMode: TaskSheetMode;
  onClose: () => void;
}) {
  const app = useApp();
  const [task, setTask] = useState<Task | null>(null);
  const [mode, setMode] = useState<TaskSheetMode>(taskId ? initialMode : "edit");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!taskId) return;
    api<Task>(`/tasks/${taskId}`)
      .then(setTask)
      .catch((err) => setLoadError(err.message));
  }, [taskId]);

  const title = !taskId ? "New task" : mode === "edit" ? "Edit task" : "Task";
  return (
    <Sheet title={title} onClose={onClose}>
      {loadError ? (
        <ErrorState message={loadError} />
      ) : taskId && !task ? (
        <Loading label="Loading task" />
      ) : mode === "edit" ? (
        <TaskForm
          task={task}
          defaults={defaults}
          onSaved={(saved) => {
            app.refresh();
            if (!taskId) {
              app.toast(`Added: ${saved.title}`, "success");
              onClose();
            } else {
              setTask(saved);
              setMode("view");
            }
          }}
          onCancel={() => (taskId ? setMode("view") : onClose())}
        />
      ) : (
        <TaskActions task={task!} onChange={setTask} onEdit={() => setMode("edit")} onClose={onClose} />
      )}
    </Sheet>
  );
}

function TaskForm({
  task,
  defaults,
  onSaved,
  onCancel,
}: {
  task: Task | null;
  defaults?: Partial<Task>;
  onSaved: (task: Task) => void;
  onCancel: () => void;
}) {
  const app = useApp();
  const [draft, setDraft] = useState<Draft>(() => draftOf(task ?? defaults ?? null));
  // One form submission, one key: a resent create replays instead of duplicating.
  const [createKey] = useState(newId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const [startsOn] = useState(1);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      setFields({ title: "Give the task a title." });
      return;
    }
    setBusy(true);
    setError("");
    setFields({});
    const body = {
      title: draft.title.trim(),
      description: draft.description,
      area: draft.area || null,
      roadmap_item: draft.roadmap_item || null,
      priority: draft.priority,
      due_date: draft.due_date || null,
      estimated_minutes: draft.estimated_minutes ? Number(draft.estimated_minutes) : null,
      status: draft.status,
      project: draft.project || null,
      goal: draft.goal || null,
      milestone: draft.milestone || null,
    };
    try {
      const saved = task
        ? await patch<Task>(`/tasks/${task.id}`, body)
        : await post<Task>("/tasks", body, { idempotencyKey: createKey });
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setFields(
          Object.fromEntries(Object.entries(err.fields).map(([key, value]) => [key, Array.isArray(value) ? value[0] : String(value)])),
        );
      }
      setError(
        err instanceof ApiError && err.code === "idempotency_key_reused"
          ? "This task may already have been saved before the connection dropped. Close this form and check your list before adding it again."
          : err instanceof Error
            ? err.message
            : "Could not save the task",
      );
    } finally {
      setBusy(false);
    }
  }

  const quickDates = [{ label: "Today", date: app.today }, ...deferOptions(app.today, startsOn)];
  return (
    <form className="form task-form" onSubmit={submit} noValidate>
      <label className="field">
        <span>Title</span>
        <input
          value={draft.title}
          onChange={(event) => set("title", event.target.value)}
          maxLength={200}
          required
          autoFocus
          aria-invalid={Boolean(fields.title)}
          placeholder="e.g. Finish freeCodeCamp JavaScript module"
        />
        {fields.title && <small className="form-error">{fields.title}</small>}
      </label>
      <label className="field">
        <span>Workstream <small className="optional">optional</small></span>
        <select value={draft.area} onChange={(event) => set("area", event.target.value)}>
          <option value="">No workstream</option>
          {app.areas.map((area) => (
            <option key={area.id} value={area.id}>{area.name}</option>
          ))}
        </select>
      </label>
      <fieldset className="field">
        <legend>Priority</legend>
        <div className="chip-row" role="radiogroup" aria-label="Priority">
          {PRIORITIES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={draft.priority === option.value}
              className="chip small"
              onClick={() => set("priority", option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset className="field">
        <legend>Due date <small className="optional">optional</small></legend>
        <div className="chip-row">
          {quickDates.map((option) => (
            <button
              key={option.label}
              type="button"
              className="chip small"
              aria-pressed={draft.due_date === option.date}
              onClick={() => set("due_date", option.date)}
            >
              {option.label}
            </button>
          ))}
          {draft.due_date && (
            <button type="button" className="chip small" onClick={() => set("due_date", "")}>No date</button>
          )}
        </div>
        <input type="date" aria-label="Due date" value={draft.due_date} onChange={(event) => set("due_date", event.target.value)} />
        {fields.due_date && <small className="form-error">{fields.due_date}</small>}
      </fieldset>
      <div className="field-row">
        <label className="field">
          <span>Estimate (minutes)</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            step={5}
            value={draft.estimated_minutes}
            onChange={(event) => set("estimated_minutes", event.target.value)}
            placeholder="e.g. 45"
          />
        </label>
        <label className="field">
          <span>Status</span>
          <select value={draft.status} onChange={(event) => set("status", event.target.value)}>
            {EDITABLE_STATUSES.map((status) => (
              <option key={status} value={status}>{STATUS_LABEL[status]}</option>
            ))}
          </select>
        </label>
      </div>
      <LinkPicker draft={draft} set={(key, value) => set(key, value)} />
      {fields.milestone && <small className="form-error">{fields.milestone}</small>}
      <RoadmapItemPicker value={draft.roadmap_item} onChange={(value) => set("roadmap_item", value)} />
      <label className="field">
        <span>Notes <small className="optional">optional</small></span>
        <textarea rows={3} value={draft.description} onChange={(event) => set("description", event.target.value)} />
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button secondary" onClick={onCancel}>Cancel</button>
        <button className="button" disabled={busy || !app.online}>{busy ? "Saving…" : task ? "Save" : "Add task"}</button>
      </div>
    </form>
  );
}

/** Project, goal and milestone. A milestone sets its own goal or project. */
function LinkPicker({ draft, set }: { draft: Draft; set: (key: "project" | "goal" | "milestone", value: string) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  useEffect(() => {
    api<Project[]>("/projects").then(setProjects).catch(() => undefined);
    api<Goal[]>("/goals").then(setGoals).catch(() => undefined);
  }, []);
  useEffect(() => {
    const parent = draft.project ? `project=${draft.project}` : draft.goal ? `goal=${draft.goal}` : "";
    if (!parent) {
      setMilestones([]);
      return;
    }
    api<Milestone[]>(`/milestones?${parent}`).then(setMilestones).catch(() => setMilestones([]));
  }, [draft.project, draft.goal]);
  const openProjects = projects.filter((p) => !["completed", "cancelled"].includes(p.status) || p.id === draft.project);
  if (!openProjects.length && !goals.length) return null;
  return (
    <div className="field-row">
      {openProjects.length > 0 && (
        <label className="field">
          <span>Project <small className="optional">optional</small></span>
          <select value={draft.project} onChange={(event) => (set("project", event.target.value), set("milestone", ""))}>
            <option value="">No project</option>
            {openProjects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
        </label>
      )}
      {goals.length > 0 && (
        <label className="field">
          <span>Goal <small className="optional">optional</small></span>
          <select value={draft.goal} onChange={(event) => (set("goal", event.target.value), !draft.project && set("milestone", ""))}>
            <option value="">No goal</option>
            {goals.map((goal) => (
              <option key={goal.id} value={goal.id}>{goal.title}</option>
            ))}
          </select>
        </label>
      )}
      {milestones.length > 0 && (
        <label className="field">
          <span>Milestone <small className="optional">optional</small></span>
          <select value={draft.milestone} onChange={(event) => set("milestone", event.target.value)}>
            <option value="">None</option>
            {milestones.filter((m) => m.status === "open" || m.id === draft.milestone).map((milestone) => (
              <option key={milestone.id} value={milestone.id}>{milestone.title}</option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

/** Subtasks as a checklist; each change saves straight away. */
function Checklist({ task, onChange }: { task: Task; onChange: (task: Task) => void }) {
  const app = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  // Shown straight away; put back if the server refuses the change.
  const [pending, setPending] = useState<ChecklistItem[] | null>(null);
  // Saves can overlap (tick an item while the previous change is in flight);
  // only the latest one decides what is shown.
  const latest = useRef(0);
  const items = pending ?? task.checklist ?? [];
  async function save(next: ChecklistItem[]) {
    const request = ++latest.current;
    setBusy(true);
    setPending(next);
    try {
      const saved = await patch<Task>(`/tasks/${task.id}`, { checklist: next });
      if (request === latest.current) onChange(saved);
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not save the checklist", "error");
    } finally {
      if (request === latest.current) {
        setPending(null);
        setBusy(false);
      }
    }
  }
  return (
    <section className="checklist" aria-label="Checklist">
      <p className="eyebrow">
        Checklist {items.length > 0 && `· ${items.filter((item) => item.done).length}/${items.length}`}
      </p>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <label className="check-field">
              <input
                type="checkbox"
                checked={item.done}
                disabled={Boolean(task.archived_at)}
                aria-busy={busy}
                onChange={() => save(items.map((value) => (value.id === item.id ? { ...value, done: !value.done } : value)))}
              />
              <span className={item.done ? "done-text" : ""}>{item.text}</span>
            </label>
            {!task.archived_at && (
              <button type="button" className="icon-button" aria-label={`Remove ${item.text}`} disabled={busy} onClick={() => save(items.filter((value) => value.id !== item.id))}>
                <Icon name="close" size={16} />
              </button>
            )}
          </li>
        ))}
      </ul>
      {!task.archived_at && (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!text.trim()) return;
            save([...items, { id: newId().slice(0, 8), text: text.trim(), done: false }]).then(() => setText(""));
          }}
        >
          <input aria-label="New checklist item" value={text} onChange={(event) => setText(event.target.value)} maxLength={200} placeholder="Add a step" />
          <button className="button small secondary" disabled={busy || !text.trim()}>Add</button>
        </form>
      )}
    </section>
  );
}

function TaskLinks({ task }: { task: Task }) {
  const [names, setNames] = useState<{ project?: string; goal?: string }>({});
  useEffect(() => {
    if (task.project) api<Project>(`/projects/${task.project}`).then((p) => setNames((n) => ({ ...n, project: p.name }))).catch(() => undefined);
    if (task.goal) api<Goal>(`/goals/${task.goal}`).then((g) => setNames((n) => ({ ...n, goal: g.title }))).catch(() => undefined);
  }, [task.project, task.goal]);
  if (!task.project && !task.goal) return null;
  return (
    <p className="chip-row">
      {task.project && (
        <a className="chip small" href={`#/projects/${task.project}`}>
          <Icon name="project" size={16} /> {names.project ?? "Project"}
        </a>
      )}
      {task.goal && (
        <a className="chip small" href={`#/goals/${task.goal}`}>
          <Icon name="goal" size={16} /> {names.goal ?? "Goal"}
        </a>
      )}
    </p>
  );
}

type ItemOption = { id: string; label: string };

function flattenItems(nodes: RoadmapNode[], trail: string[] = []): ItemOption[] {
  return nodes.flatMap((node) => [
    ...(node.node_type === "item" ? [{ id: node.id, label: [...trail, node.title].join(" › ") }] : []),
    ...flattenItems(node.children ?? [], node.node_type === "item" ? trail : [...trail, node.title]),
  ]);
}

/** Optional link to a roadmap milestone item: pick a roadmap, then one of its items. */
function RoadmapItemPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [roadmaps, setRoadmaps] = useState<Roadmap[] | null>(null);
  const [roadmap, setRoadmap] = useState("");
  const [items, setItems] = useState<ItemOption[]>([]);
  const [open, setOpen] = useState(Boolean(value));

  useEffect(() => {
    if (!open || roadmaps) return;
    api<Roadmap[]>("/roadmaps").then(setRoadmaps).catch(() => setRoadmaps([]));
    if (value) {
      api<{ roadmap: string }>(`/roadmap-nodes/${value}`)
        .then((node) => setRoadmap(node.roadmap))
        .catch(() => undefined);
    }
  }, [open, roadmaps, value]);

  useEffect(() => {
    if (!roadmap) return setItems([]);
    api<{ nodes: RoadmapNode[] }>(`/roadmaps/${roadmap}/tree`)
      .then((tree) => setItems(flattenItems(tree.nodes)))
      .catch(() => setItems([]));
  }, [roadmap]);

  if (!open) {
    return (
      <button type="button" className="text-button" onClick={() => setOpen(true)}>
        Link to a roadmap milestone
      </button>
    );
  }
  return (
    <div className="field-row">
      <label className="field">
        <span>Roadmap</span>
        <select
          value={roadmap}
          onChange={(event) => {
            setRoadmap(event.target.value);
            onChange("");
          }}
        >
          <option value="">{roadmaps ? "None" : "Loading…"}</option>
          {(roadmaps ?? []).map((item) => (
            <option key={item.id} value={item.id}>{item.title}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Milestone item</span>
        <select value={value} onChange={(event) => onChange(event.target.value)} disabled={!roadmap}>
          <option value="">None</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>{item.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

function TaskActions({
  task,
  onChange,
  onEdit,
  onClose,
}: {
  task: Task;
  onChange: (task: Task) => void;
  onEdit: () => void;
  onClose: () => void;
}) {
  const app = useApp();
  const [busy, setBusy] = useState(false);
  const [pickDate, setPickDate] = useState(false);
  const [focusArea, setFocusArea] = useState(task.area ?? "");
  const [sessionId] = useState(newId);
  const area = app.allAreas.find((item) => item.id === task.area);
  const open = isOpen(task);
  const archived = Boolean(task.archived_at);

  async function act(label: string, run: () => Promise<Task | void>, done?: string) {
    setBusy(true);
    try {
      const updated = await run();
      if (updated) onChange(updated);
      app.refresh();
      if (done) app.toast(done, "success");
    } catch (err) {
      app.toast(err instanceof Error ? err.message : `Could not ${label}`, "error");
    } finally {
      setBusy(false);
    }
  }

  const setDue = (date: string | null, status?: string) =>
    act("defer", () => patch<Task>(`/tasks/${task.id}`, status ? { due_date: date, status } : { due_date: date }), date ? `Due ${dueLabel(date, app.today)}` : "Moved to backlog");

  async function startFocus() {
    await act(
      "start focus",
      async () => {
        // If the task is scheduled today and not started, start that activity:
        // the time then belongs to the plan and finishing it can close the task.
        const today = await api<Entry[]>(`/schedule-entries?start=${app.today}&end=${addDays(app.today, 1)}`).catch(() => []);
        const planned = (Array.isArray(today) ? today : []).find((entry) => entry.task === task.id && entry.status === "scheduled");
        if (planned) {
          await post(`/schedule-entries/${planned.id}/start`, {
            expected_version: planned.version,
            ...(planned.tracking === "focus" ? { session_id: sessionId } : {}),
          });
        } else {
          if (!focusArea) throw new Error("Choose a workstream to track the time under.");
          await post("/sessions/start", {
          id: sessionId,
          title: task.title,
          area: focusArea,
          is_deep_work: task.is_deep_work_default,
          task: task.id,
          roadmap_item: task.roadmap_item ?? null,
          });
        }
        if (task.status === "todo" || task.status === "backlog") {
          return post<Task>(`/tasks/${task.id}/transition`, { status: "in_progress" });
        }
      },
      "Focus started",
    );
    onClose();
  }

  const meta = [
    STATUS_LABEL[task.status] ?? task.status,
    area ? area.name : "No workstream",
    task.due_date ? `Due ${dueLabel(task.due_date, app.today)}` : null,
    task.priority ? `${priorityLabel(task.priority)} priority` : null,
    task.estimated_minutes ? `~${durationLabel(task.estimated_minutes)}` : null,
  ].filter(Boolean);

  return (
    <div className="task-actions">
      <div>
        <h3 className="task-sheet-title">
          {area && <span className="category-dot" style={{ background: area.color }} aria-hidden="true" />} {task.title}
        </h3>
        <p className="muted">{meta.join(" · ")}</p>
        {archived && <p className="hint">Archived. It stays in your history and can be restored.</p>}
        {task.description && <p className="task-notes">{task.description}</p>}
        {task.roadmap_item && <p className="hint">Linked to a roadmap item.</p>}
        <TaskLinks task={task} />
      </div>
      <Checklist task={task} onChange={onChange} />

      {!archived && (
        <>
          <div className="button-row">
            {open ? (
              <button
                type="button"
                className="button"
                disabled={busy || !app.online}
                onClick={() =>
                  act("complete", async () => {
                    const done = await post<Task>(`/tasks/${task.id}/complete`);
                    app.celebrate(task.title);
                    return done;
                  })
                }
              >
                <Icon name="check" size={18} /> Mark done
              </button>
            ) : (
              <button type="button" className="button secondary" disabled={busy || !app.online} onClick={() => act("reopen", () => post<Task>(`/tasks/${task.id}/reopen`), "Reopened")}>
                Reopen
              </button>
            )}
            <button type="button" className="button secondary" onClick={onEdit}>Edit</button>
          </div>

          {open && (
            <>
              <section className="action-group" aria-label="Focus">
                <h4 className="group-title">Work on it now</h4>
                {!task.area && (
                  <label className="field">
                    <span>Track the time under</span>
                    <select value={focusArea} onChange={(event) => setFocusArea(event.target.value)}>
                      <option value="">Choose a workstream</option>
                      {app.areas.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                )}
                <div className="button-row">
                  <button
                    type="button"
                    className="button accent"
                    disabled={busy || !focusArea || Boolean(app.session) || !app.online}
                    onClick={startFocus}
                  >
                    <Icon name="play" size={18} /> Start focus
                  </button>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => {
                      app.openQuickAdd({
                        title: task.title,
                        area: task.area ?? null,
                        task: task.id,
                        roadmap_node: task.roadmap_item ?? null,
                        date: task.due_date && task.due_date >= app.today ? task.due_date : app.today,
                        tracking: task.is_deep_work_default ? "focus" : undefined,
                      });
                      onClose();
                    }}
                  >
                    <Icon name="schedule" size={18} /> Schedule
                  </button>
                </div>
                {app.session && <p className="hint">A focus session is already running. Finish it first.</p>}
              </section>

              <section className="action-group" aria-label="Defer">
                <h4 className="group-title">Not now</h4>
                <div className="chip-row">
                  {deferOptions(app.today).map((option) => (
                    <button key={option.label} type="button" className="chip small" disabled={busy} onClick={() => setDue(option.date)}>
                      {option.label}
                    </button>
                  ))}
                  <button type="button" className="chip small" aria-pressed={pickDate} onClick={() => setPickDate(!pickDate)}>
                    Pick a date
                  </button>
                  {task.status !== "backlog" && (
                    <button type="button" className="chip small" disabled={busy} onClick={() => setDue(null, "backlog")}>
                      Backlog
                    </button>
                  )}
                </div>
                {pickDate && (
                  <input
                    type="date"
                    aria-label="New due date"
                    min={addDays(app.today, 0)}
                    onChange={(event) => event.target.value && setDue(event.target.value)}
                  />
                )}
              </section>
            </>
          )}
        </>
      )}

      <div className="button-row">
        {archived ? (
          <button type="button" className="button secondary" disabled={busy} onClick={() => act("restore", () => post<Task>(`/tasks/${task.id}/restore`), "Restored")}>
            Restore
          </button>
        ) : (
          <button
            type="button"
            className="button secondary danger-text"
            disabled={busy}
            onClick={() => {
              if (window.confirm(`Archive "${task.title}"? It leaves your lists but stays in your history.`)) {
                act("archive", () => post<Task>(`/tasks/${task.id}/archive`), "Archived");
              }
            }}
          >
            Archive
          </button>
        )}
      </div>
    </div>
  );
}
