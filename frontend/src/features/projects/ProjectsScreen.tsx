import { FormEvent, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { nullable, useSubmit } from "../../lib/forms";
import { EmptyState, ErrorState, Icon, Loading, ScreenHead, Segmented, Sheet } from "../../components/ui";
import { patch, post } from "../../lib/api";
import { STATUS_LABEL, priorityLabel } from "../../lib/tasks";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { Goal, Milestone, Project, ProjectStatus, Task } from "../../lib/types";
import { MilestonesPanel } from "../goals/GoalsScreen";

const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = {
  planning: "Planning",
  active: "Active",
  on_hold: "On hold",
  completed: "Completed",
  cancelled: "Cancelled",
};
const PRIORITY = ["Low", "Normal", "High", "Critical"];
const BOARD_COLUMNS = ["backlog", "todo", "in_progress", "blocked", "done"] as const;

export function ProjectsScreen({ route }: { route: Route }) {
  const id = route.path[1];
  return id ? <ProjectDetail id={id} /> : <ProjectList />;
}

type ListFilter = "current" | "completed" | "archived";

function ProjectList() {
  const [filter, setFilter] = useState<ListFilter>("current");
  const [editing, setEditing] = useState(false);
  const { data, error, reload } = useResource<Project[]>(filter === "archived" ? "/projects?archived=only" : "/projects");
  const projects = (data ?? []).filter((project) =>
    filter === "archived" ? true : filter === "completed" ? ["completed", "cancelled"].includes(project.status) : !["completed", "cancelled"].includes(project.status),
  );
  return (
    <section className="screen" aria-labelledby="projects-title">
      <ScreenHead
        eyebrow="Plan · Projects"
        title="Projects"
        lead="Each project is its own workspace: its tasks, milestones, notes and history stay separate."
        back={{ href: "#/plan", label: "Plan" }}
        action={
          <button type="button" className="button small" onClick={() => setEditing(true)}>
            <Icon name="plus" size={18} /> New project
          </button>
        }
      />
      <Segmented
        label="Projects shown"
        value={filter}
        onChange={setFilter}
        options={[
          { value: "current", label: "Current" },
          { value: "completed", label: "Finished" },
          { value: "archived", label: "Archived" },
        ]}
      />
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <Loading label="Loading projects" />
      ) : projects.length === 0 ? (
        <EmptyState
          icon="project"
          title={filter === "current" ? "No projects yet" : "Nothing here"}
          body={filter === "current" ? "Create a workspace for a startup, a client, portfolio work or anything with its own deadline." : undefined}
          action={
            filter === "current" ? (
              <button type="button" className="button" onClick={() => setEditing(true)}>
                Create a project
              </button>
            ) : undefined
          }
        />
      ) : (
        <ul className="card-list">
          {projects.map((project) => (
            <li key={project.id}>
              <ProjectCard project={project} />
            </li>
          ))}
        </ul>
      )}
      {editing && <ProjectSheet project={null} onClose={() => setEditing(false)} />}
    </section>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const { counts } = project;
  const ratio = counts.tasks ? counts.done / counts.tasks : null;
  return (
    <a className="entity-card" href={`#/projects/${project.id}`} style={{ ["--accent-line" as string]: project.color }}>
      <div className="entity-card-top">
        <span className="eyebrow">
          {PROJECT_STATUS_LABEL[project.status]} · {PRIORITY[project.priority]} priority
        </span>
        {counts.overdue > 0 && <span className="tag danger">{counts.overdue} overdue</span>}
      </div>
      <h2>{project.name}</h2>
      {project.description && <p className="clamp-2 muted">{project.description}</p>}
      {ratio !== null ? (
        <div className="progress-line">
          <span className="meter">
            <i style={{ width: `${Math.round(ratio * 100)}%` }} />
          </span>
          <span>
            {counts.done}/{counts.tasks} tasks
          </span>
        </div>
      ) : (
        <p className="no-measure">No tasks yet</p>
      )}
      <p className="entity-meta">
        {counts.milestones > 0 && (
          <span>
            {counts.milestones_done}/{counts.milestones} milestones
          </span>
        )}
        {project.deadline && <span>Deadline {formatDate(project.deadline)}</span>}
        {project.goal_title && <span>Goal: {project.goal_title}</span>}
      </p>
    </a>
  );
}

function ProjectSheet({ project, onClose }: { project: Project | null; onClose: () => void }) {
  const app = useApp();
  const goals = useResource<Goal[]>("/goals");
  const [draft, setDraft] = useState({
    name: project?.name ?? "",
    description: project?.description ?? "",
    priority: project?.priority ?? 1,
    start_date: project?.start_date ?? "",
    deadline: project?.deadline ?? "",
    area: project?.area ?? "",
    goal: project?.goal ?? "",
    color: project?.color ?? "#1F5A44",
  });
  const form = useSubmit();
  const set = (key: keyof typeof draft, value: string | number) => setDraft((current) => ({ ...current, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) {
      form.setFields({ name: "Name the project." });
      return;
    }
    const body = { ...draft, name: draft.name.trim(), start_date: nullable(draft.start_date), deadline: nullable(draft.deadline), area: nullable(draft.area), goal: nullable(draft.goal) };
    const saved = await form.run(
      (key) => (project ? patch<Project>(`/projects/${project.id}`, body) : post<Project>("/projects", body, { idempotencyKey: key })),
      project ? "Project saved" : "Project created",
    );
    if (saved) {
      onClose();
      if (!project) app.navigate(`#/projects/${saved.id}`);
    }
  }
  return (
    <Sheet title={project ? "Edit project" : "New project"} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Name" error={form.fields.name}>
          <input value={draft.name} onChange={(e) => set("name", e.target.value)} maxLength={160} placeholder="e.g. FundBridge" />
        </Field>
        <Field label="What is it for?" optional>
          <textarea rows={3} value={draft.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <fieldset className="field">
          <legend>Priority</legend>
          <div className="chip-row" role="radiogroup" aria-label="Priority">
            {PRIORITY.map((label, value) => (
              <button key={label} type="button" role="radio" aria-checked={draft.priority === value} className="chip small" onClick={() => set("priority", value)}>
                {label}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="field-row">
          <Field label="Start" optional>
            <input type="date" value={draft.start_date} onChange={(e) => set("start_date", e.target.value)} />
          </Field>
          <Field label="Deadline" optional error={form.fields.deadline}>
            <input type="date" value={draft.deadline} onChange={(e) => set("deadline", e.target.value)} />
          </Field>
        </div>
        <div className="field-row">
          <Field label="Serves goal" optional>
            <select value={draft.goal} onChange={(e) => set("goal", e.target.value)}>
              <option value="">None</option>
              {(goals.data ?? []).map((goal) => (
                <option key={goal.id} value={goal.id}>
                  {goal.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Workstream" optional>
            <select value={draft.area} onChange={(e) => set("area", e.target.value)}>
              <option value="">None</option>
              {app.areas.map((area) => (
                <option key={area.id} value={area.id}>
                  {area.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Colour" optional>
          <input type="color" value={draft.color} onChange={(e) => set("color", e.target.value.toUpperCase())} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel={project ? "Save" : "Create project"} onCancel={onClose} />
      </form>
    </Sheet>
  );
}

type Overview = {
  project: Project;
  tasks: Task[];
  milestones: Milestone[];
  activity: { id: string; kind: string; title: string; detail: Record<string, string>; occurred_at: string; source: string }[];
};

function ProjectDetail({ id }: { id: string }) {
  const app = useApp();
  const { data, error, reload } = useResource<Overview>(`/projects/${id}/overview`);
  const [view, setView] = useState<"board" | "list">("board");
  const [sheet, setSheet] = useState<null | "edit" | "complete" | "archive">(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [column, setColumn] = useState<(typeof BOARD_COLUMNS)[number]>("todo");

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading project" />;
  const { project } = data;

  async function setStatus(status: ProjectStatus, message: string) {
    try {
      await post(`/projects/${project.id}/status`, { status });
      if (status === "completed") app.celebrate(project.name, "Project completed");
      else app.toast(message, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }
  async function move(task: Task, status: string) {
    try {
      await patch(`/tasks/${task.id}`, { status });
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not move the task", "error");
    }
  }
  async function saveNotes() {
    if (notes === null) return;
    try {
      await patch(`/projects/${project.id}`, { notes });
      app.toast("Notes saved", "success");
      setNotes(null);
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not save notes", "error");
    }
  }

  const byStatus = (status: string) => data.tasks.filter((task) => (status === "todo" ? ["todo", "in_review"].includes(task.status) : task.status === status));
  const finished = project.status === "completed" || project.status === "cancelled";

  return (
    <section className="screen" aria-labelledby="project-title" style={{ ["--accent-line" as string]: project.color }}>
      <header className="screen-head project-head">
        <a className="back-link" href="#/projects">
          <Icon name="chevronLeft" size={18} /> Projects
        </a>
        <p className="eyebrow">
          {PROJECT_STATUS_LABEL[project.status]} · {PRIORITY[project.priority]} priority
          {project.deadline && <> · Deadline {formatDate(project.deadline)}</>}
          {project.archived_at && " · Archived"}
        </p>
        <h1 id="project-title">{project.name}</h1>
        {project.description && <p className="muted">{project.description}</p>}
        {project.goal && (
          <a className="chip small" href={`#/goals/${project.goal}`}>
            <Icon name="goal" size={16} /> {project.goal_title}
          </a>
        )}
      </header>

      <div className="action-strip" role="group" aria-label="Project actions">
        <button type="button" className="button small" onClick={() => app.openTask(null, { project: project.id, area: project.area, status: "todo" })}>
          <Icon name="plus" size={18} /> Task
        </button>
        {project.status === "planning" && (
          <button type="button" className="button small secondary" onClick={() => setStatus("active", "Project started")}>
            Start
          </button>
        )}
        {project.status === "active" && (
          <button type="button" className="button small secondary" onClick={() => setStatus("on_hold", "Project on hold")}>
            Put on hold
          </button>
        )}
        {project.status === "on_hold" && (
          <button type="button" className="button small secondary" onClick={() => setStatus("active", "Project resumed")}>
            Resume
          </button>
        )}
        {!finished && (
          <button type="button" className="button small secondary" onClick={() => setSheet("complete")}>
            <Icon name="check" size={18} /> Complete
          </button>
        )}
        {finished && (
          <button type="button" className="button small secondary" onClick={() => setStatus("active", "Project reopened")}>
            Reopen
          </button>
        )}
        <button type="button" className="button small secondary" onClick={() => setSheet("edit")}>
          <Icon name="edit" size={18} /> Edit
        </button>
        {project.archived_at ? (
          <button
            type="button"
            className="button small secondary"
            onClick={() => post(`/projects/${project.id}/restore`).then(() => (app.toast("Project restored", "success"), app.refresh()), (err) => app.toast(err.message, "error"))}
          >
            Restore
          </button>
        ) : (
          <button type="button" className="button small secondary" onClick={() => setSheet("archive")}>
            <Icon name="archive" size={18} /> Archive
          </button>
        )}
      </div>

      <section className="panel" aria-labelledby="board-title">
        <div className="group-head">
          <h2 id="board-title">Work</h2>
          <Segmented label="View" value={view} onChange={setView} options={[{ value: "board", label: "Board" }, { value: "list", label: "List" }]} />
        </div>
        {data.tasks.length === 0 ? (
          <p className="inline-empty">No tasks in this project yet. Add the first concrete step.</p>
        ) : view === "board" ? (
          <>
            <div className="board-tabs chip-scroll" role="tablist" aria-label="Board column">
              {BOARD_COLUMNS.map((status) => (
                <button key={status} type="button" role="tab" aria-selected={column === status} className="chip small" onClick={() => setColumn(status)}>
                  {STATUS_LABEL[status]} <span className="count">{byStatus(status).length}</span>
                </button>
              ))}
            </div>
            <div className="board">
              {BOARD_COLUMNS.map((status) => (
                <section key={status} className={`board-col ${column === status ? "current" : ""}`} aria-label={STATUS_LABEL[status]}>
                  <h3>
                    {STATUS_LABEL[status]} <span className="count">{byStatus(status).length}</span>
                  </h3>
                  {byStatus(status).map((task) => (
                    <article key={task.id} className="board-card">
                      <button type="button" className="board-card-title" onClick={() => app.openTask(task.id)}>
                        {task.title}
                      </button>
                      {(Boolean(task.priority) || task.due_date) && (
                        <small>{[task.priority ? `${priorityLabel(task.priority)} priority` : "", task.due_date ? `Due ${formatDate(task.due_date)}` : ""].filter(Boolean).join(" · ")}</small>
                      )}
                      <label className="sr-only" htmlFor={`move-${task.id}`}>
                        Move {task.title}
                      </label>
                      <select id={`move-${task.id}`} value={task.status} onChange={(e) => move(task, e.target.value)}>
                        {["backlog", "todo", "in_progress", "in_review", "blocked", "done"].map((value) => (
                          <option key={value} value={value}>
                            {STATUS_LABEL[value]}
                          </option>
                        ))}
                      </select>
                    </article>
                  ))}
                  {byStatus(status).length === 0 && <p className="board-empty">Nothing here</p>}
                </section>
              ))}
            </div>
          </>
        ) : (
          <ul className="link-list">
            {data.tasks.map((task) => (
              <li key={task.id}>
                <button type="button" className="link-row" onClick={() => app.openTask(task.id)}>
                  <span className={`dot status-${task.status}`} aria-hidden="true" />
                  <span>{task.title}</span>
                  <small>{STATUS_LABEL[task.status] ?? task.status}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <MilestonesPanel parent={{ project: project.id }} milestones={data.milestones} />

      <section className="panel" aria-labelledby="notes-title">
        <div className="group-head">
          <h2 id="notes-title">Notes</h2>
          {notes === null ? (
            <button type="button" className="text-button" onClick={() => setNotes(project.notes)}>
              Edit
            </button>
          ) : (
            <button type="button" className="text-button" onClick={saveNotes}>
              Save
            </button>
          )}
        </div>
        {notes === null ? (
          project.notes ? <p className="prewrap">{project.notes}</p> : <p className="inline-empty">Decisions, links and context for this project.</p>
        ) : (
          <textarea className="notes-editor" aria-label="Project notes" rows={6} value={notes} onChange={(e) => setNotes(e.target.value)} />
        )}
      </section>

      {data.activity.length > 0 && (
        <section className="panel" aria-labelledby="activity-title">
          <h2 id="activity-title">Activity</h2>
          <ol className="history-list">
            {data.activity.slice(0, 20).map((row) => (
              <li key={row.id}>
                <b>{row.title || project.name}</b>
                <span>
                  {row.kind.replace("_", " ")}
                  {row.detail.to && ` → ${STATUS_LABEL[row.detail.to] ?? PROJECT_STATUS_LABEL[row.detail.to as ProjectStatus] ?? row.detail.to}`} · {formatDate(row.occurred_at.slice(0, 10))}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {sheet === "edit" && <ProjectSheet project={project} onClose={() => setSheet(null)} />}
      {sheet === "complete" && (
        <ConfirmSheet
          title="Complete this project?"
          body={<p>It is recorded in My Journey. Open tasks stay as they are; you can reopen the project later.</p>}
          confirmLabel="Complete project"
          onConfirm={() => setStatus("completed", "Project completed")}
          onClose={() => setSheet(null)}
        />
      )}
      {sheet === "archive" && (
        <ConfirmSheet
          title="Archive this project?"
          body={<p>It leaves your project list. Tasks, milestones, notes and history are kept and it can be restored.</p>}
          confirmLabel="Archive"
          onConfirm={() => post(`/projects/${project.id}/archive`).then(() => (app.toast("Project archived", "success"), app.refresh()))}
          onClose={() => setSheet(null)}
        />
      )}
    </section>
  );
}
