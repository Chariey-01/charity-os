import { FormEvent, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { nullable, useSubmit } from "../../lib/forms";
import { CategoryDot, EmptyState, ErrorState, Icon, Loading, ProgressLine, ScreenHead, Segmented, Sheet } from "../../components/ui";
import { patch, post } from "../../lib/api";
import { STATUS_LABEL } from "../../lib/tasks";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { ActivityEvent, CheckIn, Goal, GoalStatus, Milestone, Project, Roadmap, Task, VisionItem } from "../../lib/types";

const FILTERS = [
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Done" },
  { value: "archived", label: "Archived" },
] as const;
type Filter = (typeof FILTERS)[number]["value"];

const GOAL_STATUS_LABEL: Record<GoalStatus, string> = {
  active: "Active",
  paused: "Paused",
  completed: "Completed",
  released: "Let go",
};

export function GoalsScreen({ route }: { route: Route }) {
  const id = route.path[1];
  if (id) return <GoalDetail id={id} />;
  return <GoalList />;
}

function GoalList() {
  const [filter, setFilter] = useState<Filter>("active");
  const [editing, setEditing] = useState(false);
  const query = filter === "archived" ? "/goals?archived=only" : `/goals?status=${filter}`;
  const { data, error, reload } = useResource<Goal[]>(query);
  const released = useResource<Goal[]>(filter === "completed" ? "/goals?status=released" : null);
  const goals = [...(data ?? []), ...(filter === "completed" ? released.data ?? [] : [])];

  return (
    <section className="screen" aria-labelledby="goals-title">
      <ScreenHead
        eyebrow="Plan · Goals"
        title="Goals"
        lead="Turn what you want into targets with dates, milestones and evidence."
        back={{ href: "#/plan", label: "Plan" }}
        action={
          <button type="button" className="button small" onClick={() => setEditing(true)}>
            <Icon name="plus" size={18} /> New goal
          </button>
        }
      />
      <Segmented label="Goal status" value={filter} options={[...FILTERS]} onChange={setFilter} />
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <Loading label="Loading goals" />
      ) : goals.length === 0 ? (
        <EmptyState
          icon="goal"
          title={filter === "active" ? "No active goals yet" : "Nothing here"}
          body={
            filter === "active"
              ? "A goal turns an aspiration into something you can plan, measure and finish."
              : "Goals you move here will appear in this list."
          }
          action={
            filter === "active" ? (
              <button type="button" className="button" onClick={() => setEditing(true)}>
                Create your first goal
              </button>
            ) : undefined
          }
        />
      ) : (
        <ul className="card-list">
          {goals.map((goal) => (
            <li key={goal.id}>
              <GoalCard goal={goal} />
            </li>
          ))}
        </ul>
      )}
      {editing && <GoalSheet goal={null} onClose={() => setEditing(false)} />}
    </section>
  );
}

export function GoalCard({ goal }: { goal: Goal }) {
  const app = useApp();
  const area = app.allAreas.find((item) => item.id === goal.area);
  const p = goal.progress;
  return (
    <a className="entity-card" href={`#/goals/${goal.id}`}>
      <div className="entity-card-top">
        <span className="eyebrow">
          {area && <CategoryDot color={area.color} />} {goal.vision_title ?? (goal.kind === "measurable" ? "Measurable" : "Growth")}
        </span>
        <RiskBadges goal={goal} />
      </div>
      <h2>{goal.title}</h2>
      <ProgressLine ratio={p.ratio} label={goal.title} />
      <p className="entity-meta">
        {p.basis === "measure" && p.latest_value !== null && (
          <span>
            {p.latest_value} / {goal.target_value} {goal.metric_unit}
          </span>
        )}
        {p.milestones_total > 0 && (
          <span>
            {p.milestones_done}/{p.milestones_total} milestones
          </span>
        )}
        {p.tasks_total > 0 && (
          <span>
            {p.tasks_done}/{p.tasks_total} tasks
          </span>
        )}
        {goal.target_date && <span>Target {formatDate(goal.target_date)}</span>}
        {goal.status !== "active" && <span>{GOAL_STATUS_LABEL[goal.status]}</span>}
      </p>
    </a>
  );
}

function RiskBadges({ goal }: { goal: Goal }) {
  if (goal.archived_at) return <span className="tag">Archived</span>;
  if (goal.progress.overdue) return <span className="tag danger">Overdue</span>;
  if (goal.progress.at_risk) return <span className="tag warn">At risk</span>;
  if (goal.status === "completed") return <span className="tag success">Done</span>;
  if (goal.progress.days_left !== null && goal.progress.days_left <= 14 && goal.status === "active")
    return <span className="tag">{goal.progress.days_left} days left</span>;
  return null;
}

export function GoalSheet({ goal, defaults, onClose }: { goal: Goal | null; defaults?: Partial<Goal>; onClose: () => void }) {
  const app = useApp();
  const visions = useResource<VisionItem[]>("/vision");
  const seed = goal ?? defaults ?? {};
  const [draft, setDraft] = useState({
    title: seed.title ?? "",
    why: seed.why ?? "",
    description: seed.description ?? "",
    kind: seed.kind ?? "qualitative",
    metric_unit: seed.metric_unit ?? "",
    baseline_value: seed.baseline_value ?? "",
    target_value: seed.target_value ?? "",
    start_date: seed.start_date ?? app.today,
    target_date: seed.target_date ?? "",
    area: seed.area ?? "",
    vision: seed.vision ?? "",
  });
  const form = useSubmit();
  const set = (key: keyof typeof draft, value: string) => setDraft((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      form.setFields({ title: "Name the goal." });
      return;
    }
    const body = {
      ...draft,
      title: draft.title.trim(),
      baseline_value: draft.kind === "measurable" ? nullable(String(draft.baseline_value)) : null,
      target_value: draft.kind === "measurable" ? nullable(String(draft.target_value)) : null,
      start_date: nullable(draft.start_date),
      target_date: nullable(draft.target_date),
      area: nullable(draft.area),
      vision: nullable(draft.vision),
    };
    const saved = await form.run(
      (key) => (goal ? patch<Goal>(`/goals/${goal.id}`, body) : post<Goal>("/goals", body, { idempotencyKey: key })),
      goal ? "Goal saved" : "Goal created",
    );
    if (saved) {
      onClose();
      if (!goal) app.navigate(`#/goals/${saved.id}`);
    }
  }

  return (
    <Sheet title={goal ? "Edit goal" : "New goal"} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Goal" error={form.fields.title}>
          <input value={draft.title} onChange={(e) => set("title", e.target.value)} maxLength={160} autoFocus placeholder="e.g. Land my first AI engineering role" />
        </Field>
        <Field label="Why it matters" optional>
          <textarea rows={2} value={draft.why} onChange={(e) => set("why", e.target.value)} placeholder="The reason you will come back to on hard days" />
        </Field>
        <fieldset className="field">
          <legend>How will you know you are making progress?</legend>
          <div className="chip-row" role="radiogroup" aria-label="Goal type">
            {(["qualitative", "measurable"] as const).map((kind) => (
              <button key={kind} type="button" role="radio" aria-checked={draft.kind === kind} className="chip small" onClick={() => set("kind", kind)}>
                {kind === "qualitative" ? "Milestones" : "A number"}
              </button>
            ))}
          </div>
        </fieldset>
        {draft.kind === "measurable" && (
          <div className="field-row three">
            <Field label="Unit" optional>
              <input value={draft.metric_unit} onChange={(e) => set("metric_unit", e.target.value)} placeholder="km, KSh, projects" maxLength={40} />
            </Field>
            <Field label="Starting at" optional error={form.fields.baseline_value}>
              <input type="number" inputMode="decimal" value={draft.baseline_value} onChange={(e) => set("baseline_value", e.target.value)} />
            </Field>
            <Field label="Target" error={form.fields.target_value}>
              <input type="number" inputMode="decimal" value={draft.target_value} onChange={(e) => set("target_value", e.target.value)} />
            </Field>
          </div>
        )}
        <div className="field-row">
          <Field label="Start" optional>
            <input type="date" value={draft.start_date} onChange={(e) => set("start_date", e.target.value)} />
          </Field>
          <Field label="Target date" optional error={form.fields.target_date}>
            <input type="date" value={draft.target_date} onChange={(e) => set("target_date", e.target.value)} />
          </Field>
        </div>
        <div className="field-row">
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
          <Field label="Part of my vision" optional>
            <select value={draft.vision} onChange={(e) => set("vision", e.target.value)}>
              <option value="">Not linked</option>
              {(visions.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Details" optional>
          <textarea rows={3} value={draft.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel={goal ? "Save" : "Create goal"} onCancel={onClose} />
      </form>
    </Sheet>
  );
}

type Overview = {
  goal: Goal;
  milestones: Milestone[];
  tasks: Task[];
  roadmaps: Roadmap[];
  projects: Project[];
  checkins: CheckIn[];
  history: ActivityEvent[];
};

function GoalDetail({ id }: { id: string }) {
  const app = useApp();
  const { data, error, reload } = useResource<Overview>(`/goals/${id}/overview`);
  const [sheet, setSheet] = useState<null | "edit" | "complete" | "release" | "archive">(null);
  const [note, setNote] = useState("");

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading goal" />;
  const { goal } = data;

  async function setStatus(status: GoalStatus, message: string, extra: Record<string, string> = {}) {
    try {
      await post(`/goals/${goal.id}/status`, { status, ...extra });
      app.toast(message, "success");
      if (status === "completed") app.celebrate(goal.title, "Goal completed");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  async function archive(restore = false) {
    try {
      await post(`/goals/${goal.id}/${restore ? "restore" : "archive"}`);
      app.toast(restore ? "Goal restored" : "Goal archived. Its history is kept.", "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  return (
    <section className="screen" aria-labelledby="goal-title">
      <header className="screen-head">
        <a className="back-link" href="#/goals">
          <Icon name="chevronLeft" size={18} /> Goals
        </a>
        <p className="eyebrow">
          {GOAL_STATUS_LABEL[goal.status]}
          {goal.vision_title && <> · {goal.vision_title}</>}
          {goal.archived_at && " · Archived"}
        </p>
        <h1 id="goal-title">{goal.title}</h1>
        {goal.why && <p className="lead-quote">{goal.why}</p>}
      </header>

      <section className="panel goal-progress" aria-label="Progress">
        <div className="group-head">
          <h2>Progress</h2>
          <RiskBadges goal={goal} />
        </div>
        <ProgressLine ratio={goal.progress.ratio} label="Goal progress" />
        <p className="muted small">
          {goal.progress.basis === "measure"
            ? `Latest measurement: ${goal.progress.latest_value} of ${goal.target_value} ${goal.metric_unit}.`
            : goal.progress.basis === "milestones"
              ? `${goal.progress.milestones_done} of ${goal.progress.milestones_total} milestones done.`
              : goal.kind === "measurable"
                ? "Record your first measurement to see progress."
                : "Add milestones to measure progress. Until then CharityOS does not guess."}
          {goal.target_date && ` Target ${formatDate(goal.target_date)}.`}
        </p>
        {goal.status === "active" && !goal.archived_at && <CheckInForm goal={goal} />}
      </section>

      <div className="action-strip" role="group" aria-label="Goal actions">
        {goal.status === "active" && (
          <button type="button" className="button small" onClick={() => setSheet("complete")}>
            <Icon name="check" size={18} /> Complete
          </button>
        )}
        {goal.status === "active" && (
          <button type="button" className="button small secondary" onClick={() => setStatus("paused", "Goal paused")}>
            Pause
          </button>
        )}
        {goal.status === "paused" && (
          <button type="button" className="button small" onClick={() => setStatus("active", "Goal resumed")}>
            Resume
          </button>
        )}
        {(goal.status === "completed" || goal.status === "released") && (
          <button type="button" className="button small secondary" onClick={() => setStatus("active", "Goal reopened")}>
            Reopen
          </button>
        )}
        <button type="button" className="button small secondary" onClick={() => setSheet("edit")}>
          <Icon name="edit" size={18} /> Edit
        </button>
        {goal.status === "active" && (
          <a className="button small secondary" href={`#/reminders?new=1&kind=goal&target=${goal.id}&title=${encodeURIComponent(`Check in on: ${goal.title}`)}&link=${encodeURIComponent(`#/goals/${goal.id}`)}`}>
            <Icon name="bell" size={18} /> Remind me
          </a>
        )}
        {goal.status !== "released" && goal.status !== "completed" && (
          <button type="button" className="button small secondary" onClick={() => setSheet("release")}>
            Let go
          </button>
        )}
        {goal.archived_at ? (
          <button type="button" className="button small secondary" onClick={() => archive(true)}>
            Restore
          </button>
        ) : (
          <button type="button" className="button small secondary" onClick={() => setSheet("archive")}>
            <Icon name="archive" size={18} /> Archive
          </button>
        )}
      </div>

      <MilestonesPanel parent={{ goal: goal.id }} milestones={data.milestones} />

      <section className="panel" aria-labelledby="goal-tasks">
        <div className="group-head">
          <h2 id="goal-tasks">Tasks</h2>
          <button type="button" className="text-button" onClick={() => app.openTask(null, { goal: goal.id, area: goal.area })}>
            Add task
          </button>
        </div>
        {data.tasks.length === 0 ? (
          <p className="inline-empty">No tasks yet. Break the next milestone into a first step.</p>
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

      {(data.roadmaps.length > 0 || data.projects.length > 0) && (
        <section className="panel" aria-label="Linked roadmaps and projects">
          <h2>Roadmaps and projects</h2>
          <ul className="link-list">
            {data.roadmaps.map((roadmap) => (
              <li key={roadmap.id}>
                <a className="link-row" href={`#/roadmaps?open=${roadmap.id}`}>
                  <Icon name="roadmaps" size={18} /> <span>{roadmap.title}</span> <small>Roadmap</small>
                </a>
              </li>
            ))}
            {data.projects.map((project) => (
              <li key={project.id}>
                <a className="link-row" href={`#/projects/${project.id}`}>
                  <Icon name="project" size={18} /> <span>{project.name}</span> <small>Project</small>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {goal.description && (
        <section className="panel">
          <h2>Details</h2>
          <p className="prewrap">{goal.description}</p>
        </section>
      )}

      {data.checkins.length > 0 && (
        <section className="panel" aria-labelledby="goal-checkins">
          <h2 id="goal-checkins">Check-ins</h2>
          <ul className="history-list">
            {data.checkins.map((checkin) => (
              <li key={checkin.id}>
                <b>{formatDate(checkin.local_date)}</b>
                {checkin.value !== null && (
                  <span>
                    {checkin.value} {goal.metric_unit}
                  </span>
                )}
                {checkin.note && <p>{checkin.note}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <HistoryPanel events={data.history} />

      {sheet === "edit" && <GoalSheet goal={goal} onClose={() => setSheet(null)} />}
      {sheet === "complete" && (
        <ConfirmSheet
          title="Complete this goal?"
          body={<p>It moves to My Journey with today's date. You can reopen it later; the record of completing it stays.</p>}
          confirmLabel="Mark complete"
          onConfirm={() => setStatus("completed", "Goal completed", { note })}
          onClose={() => setSheet(null)}
        >
          <Field label="What did you achieve?" optional>
            <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </ConfirmSheet>
      )}
      {sheet === "release" && (
        <ConfirmSheet
          title="Let this goal go?"
          body={<p>Letting go is a decision, not a failure. The goal and its history stay in your records.</p>}
          confirmLabel="Let it go"
          onConfirm={() => setStatus("released", "Goal let go", { note })}
          onClose={() => setSheet(null)}
        >
          <Field label="Why" optional>
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </ConfirmSheet>
      )}
      {sheet === "archive" && (
        <ConfirmSheet
          title="Archive this goal?"
          body={<p>It leaves your working lists. Milestones, tasks, check-ins and history are kept, and you can restore it at any time.</p>}
          confirmLabel="Archive"
          onConfirm={() => archive()}
          onClose={() => setSheet(null)}
        />
      )}
    </section>
  );
}

function CheckInForm({ goal }: { goal: Goal }) {
  const app = useApp();
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (goal.kind === "measurable" && value === "") {
      form.setFields({ value: "Enter the value you measured." });
      return;
    }
    if (goal.kind === "qualitative" && !note.trim()) {
      form.setFields({ note: "Write a short note about your progress." });
      return;
    }
    const done = await form.run(
      (key) => post(`/goals/${goal.id}/checkins`, { value: value || null, note, local_date: app.today }, { idempotencyKey: key }),
      "Check-in recorded",
    );
    if (done !== null) {
      setValue("");
      setNote("");
    }
  }
  return (
    <form className="checkin-form" onSubmit={submit} noValidate>
      {goal.kind === "measurable" && (
        <Field label={`Today's value${goal.metric_unit ? ` (${goal.metric_unit})` : ""}`} error={form.fields.value}>
          <input type="number" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
      )}
      <Field label="Progress note" optional={goal.kind === "measurable"} error={form.fields.note}>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What moved forward?" />
      </Field>
      {form.error && <p className="form-error" role="alert">{form.error}</p>}
      <button className="button small" disabled={form.busy || !app.online}>
        {form.busy ? "Saving…" : "Check in"}
      </button>
    </form>
  );
}

export function MilestonesPanel({ parent, milestones }: { parent: { goal?: string; project?: string }; milestones: Milestone[] }) {
  const app = useApp();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [confirm, setConfirm] = useState<Milestone | null>(null);
  const form = useSubmit();

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      form.setFields({ title: "Name the milestone." });
      return;
    }
    const saved = await form.run(
      (key) => post("/milestones", { ...parent, title: title.trim(), target_date: nullable(date), position: milestones.length }, { idempotencyKey: key }),
      "Milestone added",
    );
    if (saved) {
      setTitle("");
      setDate("");
    }
  }

  async function toggle(milestone: Milestone) {
    try {
      const next = milestone.status === "done" ? "open" : "done";
      await post(`/milestones/${milestone.id}/status`, { status: next });
      if (next === "done") app.celebrate(milestone.title, "Milestone reached");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  async function archive(milestone: Milestone) {
    await post(`/milestones/${milestone.id}/archive`).catch((err) => app.toast(err.message, "error"));
    app.toast("Milestone archived", "success");
    app.refresh();
  }

  return (
    <section className="panel" aria-labelledby="milestones-title">
      <h2 id="milestones-title">Milestones</h2>
      {milestones.length === 0 && <p className="inline-empty">Milestones are the checkpoints between today and the finish line.</p>}
      <ol className="milestone-list">
        {milestones.map((milestone) => (
          <li key={milestone.id} className={milestone.status === "done" ? "done" : ""}>
            <button
              type="button"
              className={`check ${milestone.status === "done" ? "checked" : ""}`}
              role="checkbox"
              aria-checked={milestone.status === "done"}
              aria-label={`${milestone.status === "done" ? "Reopen" : "Complete"} ${milestone.title}`}
              onClick={() => toggle(milestone)}
            >
              <Icon name="check" size={16} />
            </button>
            <div>
              <b>{milestone.title}</b>
              <small>
                {milestone.target_date ? `Target ${formatDate(milestone.target_date)}` : "No target date"}
                {milestone.tasks_total > 0 && ` · ${milestone.tasks_done}/${milestone.tasks_total} tasks`}
                {milestone.overdue && " · overdue"}
              </small>
            </div>
            <button type="button" className="icon-button" aria-label={`Archive ${milestone.title}`} onClick={() => setConfirm(milestone)}>
              <Icon name="archive" size={18} />
            </button>
          </li>
        ))}
      </ol>
      <form className="inline-form" onSubmit={add} noValidate>
        <input aria-label="New milestone" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a milestone" maxLength={160} />
        <input aria-label="Milestone target date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <button className="button small" disabled={form.busy || !app.online}>
          Add
        </button>
      </form>
      {(form.fields.title || form.error) && <p className="form-error" role="alert">{form.fields.title || form.error}</p>}
      {confirm && (
        <ConfirmSheet
          title="Archive this milestone?"
          body={<p>It leaves this list. Linked tasks and its history stay.</p>}
          confirmLabel="Archive"
          onConfirm={() => archive(confirm)}
          onClose={() => setConfirm(null)}
        />
      )}
    </section>
  );
}

const EVENT_LABEL: Record<string, string> = {
  created: "Created",
  completed: "Completed",
  reopened: "Reopened",
  status_changed: "Status changed",
  checkin: "Check-in",
  realised: "Realised",
  revised: "Revised",
  carried_forward: "Carried forward",
};

export function HistoryPanel({ events }: { events: ActivityEvent[] }) {
  if (!events.length) return null;
  return (
    <section className="panel" aria-labelledby="history-title">
      <h2 id="history-title">History</h2>
      <ol className="history-list">
        {events.map((event) => (
          <li key={event.id}>
            <b>{EVENT_LABEL[event.kind] ?? event.kind}</b>
            <span>{formatDate(event.occurred_at.slice(0, 10))}</span>
            {typeof event.data.note === "string" && event.data.note && <p>{event.data.note}</p>}
            {typeof event.data.to === "string" && event.kind === "status_changed" && <p>Now {String(event.data.to).replace("_", " ")}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

