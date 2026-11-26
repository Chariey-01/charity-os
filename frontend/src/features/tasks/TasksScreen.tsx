import { FormEvent, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { EmptyState, ErrorState, Icon, Loading } from "../../components/ui";
import { api, newId, post } from "../../lib/api";
import { dueLabel, groupTasks, isOpen, priorityLabel } from "../../lib/tasks";
import { addDays, durationLabel } from "../../lib/time";
import type { Task } from "../../lib/types";

/** Type a title, press Enter: the fastest way to capture a responsibility. */
export function QuickCapture({ dueToday = false }: { dueToday?: boolean }) {
  const app = useApp();
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  // A new key per capture; a resend of the same capture is replayed by the server.
  const [key, setKey] = useState(newId);

  async function capture(event: FormEvent) {
    event.preventDefault();
    const text = title.trim();
    if (!text) return;
    setBusy(true);
    try {
      await post<Task>("/tasks", { title: text, ...(dueToday ? { due_date: app.today } : {}) }, { idempotencyKey: key });
      setTitle("");
      setKey(newId());
      app.toast(`Added: ${text}`, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not add the task", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="quick-capture" onSubmit={capture} aria-label="Capture a task">
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder={dueToday ? "Add a task for today…" : "Add a task…"}
        aria-label={dueToday ? "New task for today" : "New task"}
        maxLength={200}
        enterKeyHint="done"
      />
      <button className="button small" disabled={busy || !title.trim() || !app.online}>Add</button>
      <button
        type="button"
        className="button secondary small"
        onClick={() => {
          app.openTask(null, { title: title.trim(), ...(dueToday ? { due_date: app.today } : {}) });
          setTitle("");
        }}
      >
        Details
      </button>
    </form>
  );
}

export function TaskRow({ task }: { task: Task }) {
  const app = useApp();
  const [busy, setBusy] = useState(false);
  const area = app.allAreas.find((item) => item.id === task.area);
  const open = isOpen(task);
  const overdue = Boolean(open && task.due_date && task.due_date < app.today);

  async function toggle() {
    setBusy(true);
    try {
      await post(`/tasks/${task.id}/${open ? "complete" : "reopen"}`);
      if (open) app.celebrate(task.title);
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update the task", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`task-row ${open ? "" : "done"}`}>
      <button
        type="button"
        className={`check ${open ? "" : "checked"}`}
        aria-label={open ? `Mark ${task.title} done` : `Reopen ${task.title}`}
        aria-pressed={!open}
        disabled={busy || !app.online}
        onClick={toggle}
      >
        <Icon name="check" size={16} />
      </button>
      <button type="button" className="task-main" onClick={() => app.openTask(task.id)}>
        <span className="task-title">{task.title}</span>
        <span className="task-meta">
          {area && (
            <span>
              <span className="category-dot" style={{ background: area.color }} aria-hidden="true" /> {area.name}
            </span>
          )}
          {task.due_date && open && <span className={overdue ? "overdue" : ""}>{dueLabel(task.due_date, app.today)}</span>}
          {task.status === "in_progress" && <span>In progress</span>}
          {task.status === "blocked" && <span className="overdue">Blocked</span>}
          {(task.priority ?? 0) >= 2 && <span className="priority">{priorityLabel(task.priority)}</span>}
          {task.estimated_minutes ? <span>~{durationLabel(task.estimated_minutes)}</span> : null}
        </span>
      </button>
    </li>
  );
}

export function TasksScreen({ route }: { route: Route }) {
  const app = useApp();
  const [open, setOpen] = useState<Task[] | null>(null);
  const [done, setDone] = useState<Task[]>([]);
  const [archived, setArchived] = useState<Task[] | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const filter = route.params.get("area") ?? "all";

  useEffect(() => {
    let alive = true;
    Promise.all([
      api<Task[]>("/tasks?status=open"),
      api<Task[]>(`/tasks?status=done&completed_since=${addDays(app.today, -7)}`),
    ])
      .then(([openTasks, doneTasks]) => {
        if (!alive) return;
        setOpen(openTasks);
        setDone([...doneTasks].sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? "")));
        setError("");
      })
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [app.dataVersion, app.today, retry]);

  useEffect(() => {
    if (archived === null) return;
    api<Task[]>("/tasks?archived=only").then(setArchived).catch(() => setArchived([]));
    // Reload the archive list whenever data changes while it is shown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.dataVersion]);

  if (error && !open) return <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />;
  if (!open) return <Loading label="Loading tasks" />;

  const matches = (task: Task) => filter === "all" || (filter === "none" ? !task.area : task.area === filter);
  const visible = open.filter(matches);
  const groups = groupTasks(visible, app.today);
  const usedAreas = app.areas.filter((area) => open.some((task) => task.area === area.id));
  const overdue = open.filter((task) => task.due_date && task.due_date < app.today).length;

  return (
    <section className="screen tasks" aria-labelledby="tasks-title">
      <header className="screen-head">
        <p className="eyebrow">Tasks</p>
        <h1 id="tasks-title">What needs doing</h1>
        <p className="muted">
          {open.length} open{overdue ? ` · ${overdue} overdue` : ""} · {done.length} done in the last 7 days
        </p>
      </header>

      <QuickCapture />

      {usedAreas.length > 0 && (
        <div className="chip-scroll filter-row" role="radiogroup" aria-label="Workstream">
          {[{ id: "all", name: "All" }, ...usedAreas, ...(open.some((task) => !task.area) ? [{ id: "none", name: "No workstream" }] : [])].map((area) => (
            <button
              key={area.id}
              type="button"
              role="radio"
              aria-checked={filter === area.id}
              className="chip"
              onClick={() => app.navigate(area.id === "all" ? "#/tasks" : `#/tasks?area=${area.id}`)}
            >
              {area.name}
            </button>
          ))}
        </div>
      )}

      {groups.length === 0 ? (
        <EmptyState
          title={open.length ? "Nothing in this workstream" : "Nothing on your list"}
          body="Capture responsibilities as they come up: courses, client work, applications, errands. Only a title is needed."
          action={
            <button type="button" className="button" onClick={() => app.openTask(null)}>
              <Icon name="plus" size={18} /> New task
            </button>
          }
        />
      ) : (
        groups.map((group) => (
          <section key={group.key} className="group" aria-labelledby={`group-${group.key}`}>
            <h2 id={`group-${group.key}`} className={`group-title ${group.key === "overdue" ? "overdue" : ""}`}>
              {group.title} <span className="count">{group.tasks.length}</span>
            </h2>
            <ul className="task-rows">
              {group.tasks.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </ul>
          </section>
        ))
      )}

      {done.filter(matches).length > 0 && (
        <details className="group collapsible">
          <summary>
            <span className="group-title">Done in the last 7 days</span> <span className="count">{done.filter(matches).length}</span>
          </summary>
          <ul className="task-rows">
            {done.filter(matches).map((task) => (
              <TaskRow key={task.id} task={task} />
            ))}
          </ul>
        </details>
      )}

      <details
        className="group collapsible"
        onToggle={(event) => {
          if ((event.target as HTMLDetailsElement).open && archived === null) {
            setArchived([]);
            api<Task[]>("/tasks?archived=only").then(setArchived).catch(() => setArchived([]));
          }
        }}
      >
        <summary>
          <span className="group-title">Archived</span>
        </summary>
        {archived === null || archived.length === 0 ? (
          <p className="hint">{archived === null ? "Loading…" : "Nothing archived."}</p>
        ) : (
          <ul className="task-rows">
            {archived.map((task) => (
              <li key={task.id} className="task-row done">
                <button type="button" className="task-main" onClick={() => app.openTask(task.id)}>
                  <span className="task-title">{task.title}</span>
                  <span className="task-meta">Archived · tap to restore</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
