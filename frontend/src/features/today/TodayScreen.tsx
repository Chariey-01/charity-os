import { useEffect, useRef, useState } from "react";

import { useApp } from "../../app/context";
import { EmptyState, ErrorState, Icon, Loading, Meter, ProgressRing, Segmented } from "../../components/ui";
import { api, post } from "../../lib/api";
import { formatMinutes } from "../../lib/format";
import { isOpen } from "../../lib/tasks";
import { clock, durationLabel, formatDate, formatTime, relativeMinutes, zoned } from "../../lib/time";
import type { DayPayload, Entry, Preferences, Progress, Task } from "../../lib/types";
import { useEntryCommand, useLiveSeconds } from "../schedule/hooks";
import { DayGrid, EntryList, TimelineList } from "../schedule/views";
import { QuickCapture, TaskRow } from "../tasks/TasksScreen";

type View = Preferences["default_today_view"];

const RUNNING = new Set(["in_progress", "paused"]);
const DONE = new Set(["completed", "partially_completed"]);

function greeting(minutes: number) {
  if (minutes < 12 * 60) return "Good morning";
  if (minutes < 17 * 60) return "Good afternoon";
  return "Good evening";
}

export function TodayScreen() {
  const app = useApp();
  const [data, setData] = useState<DayPayload | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>(app.prefs.default_today_view);
  const [retry, setRetry] = useState(0);
  const lastCompleted = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    api<DayPayload>("/schedule/day")
      .then((value) => {
        if (!alive) return;
        setData(value);
        setError("");
      })
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [app.dataVersion, retry]);

  // Gentle weekly milestone note when a completion crosses a target.
  useEffect(() => {
    if (!data) return;
    const previous = lastCompleted.current;
    lastCompleted.current = data.week.completed;
    if (previous === null || data.week.completed <= previous) return;
    const reached = data.week.milestones.find((item) => item.target > previous && item.target <= data.week.completed);
    if (reached && app.prefs.celebrations_enabled) app.toast(`Weekly milestone: ${reached.target} activities completed`, "success");
  }, [data, app]);

  if (error && !data) return <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />;
  if (!data) return <Loading label="Loading today" />;

  const tz = app.user.timezone;
  const nowZoned = zoned(Date.now(), tz);
  const nowMs = Date.now();
  const entries = data.entries.filter((entry) => entry.status !== "cancelled");
  const current = entries.filter((entry) => RUNNING.has(entry.status));
  const scheduled = entries.filter((entry) => entry.status === "scheduled");
  const upcoming = scheduled.filter((entry) => new Date(entry.end_at).getTime() >= nowMs);
  const unmarked = scheduled.filter((entry) => new Date(entry.end_at).getTime() < nowMs);
  const done = entries.filter((entry) => DONE.has(entry.status) || entry.status === "skipped");
  const next = upcoming[0];
  const { progress, capacity } = data;
  const doneCount = progress.completed + progress.partially_completed;

  return (
    <section className="screen today" aria-labelledby="today-title">
      <header className="screen-head">
        <p className="eyebrow">{greeting(nowZoned.minutes)}{app.user.display_name ? `, ${app.user.display_name}` : ""}</p>
        <h1 id="today-title">{formatDate(data.date, { weekday: "long", day: "numeric", month: "long" })}</h1>
        {data.challenge && (
          <p className="challenge-chip">
            <span>{data.challenge.name}</span>
            {data.challenge.phase === "active"
              ? ` · Day ${data.challenge.current_day} of ${data.challenge.total_days}`
              : data.challenge.phase === "upcoming"
                ? ` · starts ${formatDate(data.challenge.start_date, { day: "numeric", month: "short" })}`
                : " · complete"}
          </p>
        )}
      </header>

      <section className="summary-card" aria-label="Today's progress">
        <ProgressRing value={doneCount} total={progress.planned} label={`${doneCount} of ${progress.planned} activities done`} />
        <div className="summary-text">
          <b>{progress.planned ? `${doneCount} of ${progress.planned} done` : "Nothing planned yet"}</b>
          <small>
            {durationLabel(progress.actual_minutes)} tracked · {durationLabel(progress.planned_minutes)} planned
          </small>
          {capacity.available_minutes !== null ? (
            <>
              <Meter
                value={capacity.scheduled_minutes}
                max={capacity.available_minutes}
                tone={(capacity.remaining_minutes ?? 0) < 0 ? "warn" : "brand"}
                label="Scheduled time against available capacity"
              />
              <small>
                {(capacity.remaining_minutes ?? 0) >= 0
                  ? `${durationLabel(capacity.remaining_minutes)} free of ${durationLabel(capacity.available_minutes)}`
                  : `${durationLabel(-(capacity.remaining_minutes ?? 0))} over your ${durationLabel(capacity.available_minutes)} capacity`}
              </small>
            </>
          ) : (
            <CapacityPrompt date={data.date} />
          )}
        </div>
      </section>

      <QuickCapture />
      <TodayTasks />
      <TaskProgressCard />

      {current.map((entry) => (
        <CurrentCard key={entry.id} entry={entry} />
      ))}
      {!current.length && next && <NextCard entry={next} nowMs={nowMs} />}

      {entries.length === 0 ? (
        <EmptyState
          title="A clear day"
          body="Add what you want to do today: study, errands, exercise, rest. Anything with a time."
          action={
            <button type="button" className="button" onClick={() => app.openQuickAdd({ date: data.date })}>
              <Icon name="plus" size={18} /> Add an activity
            </button>
          }
        />
      ) : (
        <>
          <Segmented<View>
            label="Today view"
            value={view}
            onChange={setView}
            options={[
              { value: "agenda", label: "Agenda" },
              { value: "timeline", label: "Timeline" },
              { value: "day", label: "Day" },
            ]}
          />
          {view === "agenda" && (
            <div className="agenda">
              {unmarked.length > 0 && (
                <section className="group">
                  <h2 className="group-title">Earlier today</h2>
                  <p className="hint">Did these happen? Mark them done, move them, or skip. No pressure.</p>
                  <EntryList entries={unmarked} label="Earlier, not yet marked" />
                </section>
              )}
              <section className="group">
                <h2 className="group-title">Up next</h2>
                {upcoming.length ? (
                  <EntryList entries={upcoming} label="Upcoming activities" />
                ) : (
                  <p className="hint">Nothing else scheduled today.</p>
                )}
              </section>
            </div>
          )}
          {view === "timeline" && <TimelineList entries={entries} />}
          {view === "day" && <DayGrid date={data.date} entries={entries} compact />}
        </>
      )}

      {done.length > 0 && (
        <details className="group collapsible">
          <summary>
            <span className="group-title">Completed</span> <span className="count">{done.length}</span>
          </summary>
          <EntryList entries={done} label="Completed activities" />
        </details>
      )}

      {data.unscheduled_tasks.length > 0 && (
        <details className="group collapsible">
          <summary>
            <span className="group-title">Unscheduled tasks</span> <span className="count">{data.unscheduled_tasks.length}</span>
          </summary>
          <ul className="task-list">
            {data.unscheduled_tasks.map((task) => (
              <li key={task.id}>
                <span className="entry-color" style={{ background: task.color }} aria-hidden="true" />
                <span className="task-title">
                  {task.plan_kind === "primary" && <span className="primary-mark" aria-label="Primary outcome">✦ </span>}
                  {task.title}
                  {task.area_label && <small>{task.area_label}</small>}
                </span>
                <button
                  type="button"
                  className="button secondary small"
                  onClick={() =>
                    app.openQuickAdd({
                      title: task.title,
                      area: task.area,
                      task: task.id,
                      roadmap_node: task.roadmap_item,
                      date: data.date,
                      tracking: task.is_deep_work_default ? "focus" : undefined,
                    })
                  }
                >
                  Schedule
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <WeekStrip data={data} />
    </section>
  );
}

function CurrentCard({ entry }: { entry: Entry }) {
  const app = useApp();
  const live = useLiveSeconds(entry);
  const { run, busyId } = useEntryCommand();
  const busy = busyId === entry.id || !app.online;
  return (
    <section className={`current-card ${entry.status}`} aria-label="Current activity">
      <p className="eyebrow light">
        <span className="live-dot" aria-hidden="true" /> {entry.status === "paused" ? "Paused" : "Now"} · {entry.area_label || "Activity"}
      </p>
      <h2>{entry.title}</h2>
      <strong className="current-clock" data-testid="current-timer">{clock(live ?? 0)}</strong>
      <small>of {durationLabel(entry.planned_minutes)} planned{entry.tracking === "focus" ? " · focus timer" : ""}</small>
      <div className="button-row">
        {entry.status === "in_progress" ? (
          <button type="button" className="button ghost" disabled={busy} onClick={() => run(entry, "pause")}>
            <Icon name="pause" size={18} /> Pause
          </button>
        ) : (
          <button type="button" className="button ghost" disabled={busy} onClick={() => run(entry, "resume")}>
            <Icon name="play" size={18} /> Resume
          </button>
        )}
        <button type="button" className="button accent" disabled={!app.online} onClick={() => app.openEntry(entry, "finish")}>
          <Icon name="check" size={18} /> Finish
        </button>
      </div>
    </section>
  );
}

function NextCard({ entry, nowMs }: { entry: Entry; nowMs: number }) {
  const app = useApp();
  const { run, busyId } = useEntryCommand();
  const startsIn = Math.round((new Date(entry.start_at).getTime() - nowMs) / 60000);
  return (
    <section className="next-card" aria-label="Next activity">
      <span className="entry-color" style={{ background: entry.color }} aria-hidden="true" />
      <div>
        <p className="eyebrow">Up next · {startsIn > 0 ? relativeMinutes(startsIn) : "now"}</p>
        <h2>{entry.title}</h2>
        <small>
          {formatTime(entry.start_at, app.user.timezone)} – {formatTime(entry.end_at, app.user.timezone)}
        </small>
      </div>
      <button type="button" className="button" disabled={busyId === entry.id || !app.online} onClick={() => run(entry, "start")}>
        <Icon name="play" size={18} /> Start
      </button>
    </section>
  );
}

function CapacityPrompt({ date }: { date: string }) {
  const app = useApp();
  const [open, setOpen] = useState(false);
  const [hours, setHours] = useState(8);
  if (!open) {
    return (
      <button type="button" className="text-button" onClick={() => setOpen(true)}>
        Set today's available time
      </button>
    );
  }
  return (
    <form
      className="capacity-form"
      onSubmit={async (event) => {
        event.preventDefault();
        try {
          await post("/capacities", {
            local_date: date,
            timezone_name: app.user.timezone,
            available_minutes: Math.round(hours * 60),
            deep_work_minutes: Math.min(Math.round(hours * 60), 240),
          });
          app.refresh();
        } catch (err) {
          app.toast(err instanceof Error ? err.message : "Could not save capacity", "error");
        }
      }}
    >
      <label>
        Available hours
        <input type="number" min={0} max={24} step={0.5} value={hours} onChange={(event) => setHours(Number(event.target.value))} />
      </label>
      <button className="button small">Save</button>
    </form>
  );
}

function WeekStrip({ data }: { data: DayPayload }) {
  const { week } = data;
  return (
    <section className="week-strip" aria-label="This week">
      <div>
        <p className="eyebrow">Activities this week</p>
        <b>
          {week.completed} done · {week.active_days} active {week.active_days === 1 ? "day" : "days"}
        </b>
        <small>{week.next_milestone ? `Next milestone: ${week.next_milestone}` : "All weekly milestones reached. Rest counts too."}</small>
      </div>
      <ol className="milestones" aria-label="Weekly milestones">
        {week.milestones.map((milestone) => (
          <li key={milestone.target} className={milestone.reached ? "reached" : ""}>
            <span className="sr-only">{milestone.reached ? "Reached" : "Not yet"}:</span> {milestone.target}
          </li>
        ))}
      </ol>
      {week.streak_weeks !== null && week.streak_weeks > 0 && (
        <p className="streak">{week.streak_weeks}-week rhythm (3+ active days a week)</p>
      )}
    </section>
  );
}

/** What needs doing today: overdue, due today, in progress and high-priority tasks. */
function TodayTasks() {
  const app = useApp();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api<Task[]>("/tasks?status=open")
      .then((value) => {
        if (!alive) return;
        setTasks(Array.isArray(value) ? value : []);
        setFailed(false);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [app.dataVersion]);

  if (failed && !tasks) return <p className="hint">Tasks could not be loaded. Pull to refresh or open Tasks.</p>;
  if (!tasks) return null;
  const open = tasks.filter(isOpen);
  const rank = (task: Task) =>
    task.due_date && task.due_date < app.today ? 0 : task.due_date === app.today ? 1 : task.status === "in_progress" ? 2 : 3;
  const focus = open
    .filter((task) => rank(task) < 3 || (task.priority ?? 0) >= 3)
    .sort((a, b) => rank(a) - rank(b) || (b.priority ?? 0) - (a.priority ?? 0) || (a.due_date ?? "").localeCompare(b.due_date ?? ""));
  const overdue = open.filter((task) => task.due_date && task.due_date < app.today).length;
  const shown = focus.slice(0, 6);

  return (
    <section className="panel today-tasks" aria-labelledby="today-tasks-title">
      <div className="group-head">
        <h2 id="today-tasks-title" className="panel-title">Tasks for today</h2>
        <a className="text-button small" href="#/tasks">All tasks ({open.length})</a>
      </div>
      {overdue > 0 && <p className="hint overdue">{overdue} overdue</p>}
      {shown.length ? (
        <ul className="task-rows">
          {shown.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </ul>
      ) : (
        <p className="hint">
          {open.length ? "Nothing due today, overdue or in progress." : "No open tasks. Capture one above when something comes up."}
        </p>
      )}
      {focus.length > shown.length && <p className="hint">and {focus.length - shown.length} more on the Tasks tab.</p>}
    </section>
  );
}

/** This week's task progress in one line, with the figures behind it. */
function TaskProgressCard() {
  const app = useApp();
  const [data, setData] = useState<Progress | null>(null);

  useEffect(() => {
    let alive = true;
    api<Progress>("/progress")
      .then((value) => alive && setData(value && typeof value === "object" && "weekly" in value ? value : null))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [app.dataVersion]);

  if (!data) return null;
  const { weekly, accomplishments } = data;
  return (
    <a className="panel progress-card" href="#/insights" aria-label="Tasks this week. Open weekly progress.">
      <p className="eyebrow">Tasks this week</p>
      {weekly.planned ? (
        <>
          <b>
            {weekly.completion_percent}% · {weekly.completed} of {weekly.planned} planned done
          </b>
          <Meter value={weekly.completed} max={weekly.planned} label="Planned tasks completed this week" />
        </>
      ) : (
        <b>No tasks planned for this week yet</b>
      )}
      <small>
        {weekly.completed_total} completed · {formatMinutes(accomplishments.focus_minutes)} focus
        {data.overall.overdue ? ` · ${data.overall.overdue} overdue` : ""}
      </small>
    </a>
  );
}
