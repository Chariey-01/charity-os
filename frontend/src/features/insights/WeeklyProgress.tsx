import { useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { ErrorState, Icon, Loading, Meter } from "../../components/ui";
import { api } from "../../lib/api";
import { formatMinutes } from "../../lib/format";
import { addDays, formatDate } from "../../lib/time";
import type { Progress } from "../../lib/types";
import { DonutChart } from "./Chart";
import { useProgress, weekRange } from "./progressData";

type RoadmapProgress = { id: string; title: string; completed_eligible_items: number; eligible_items: number; progress_ratio: number };

const day = (date: string) => formatDate(date, { weekday: "short", day: "numeric", month: "short" });

export function WeekNav({ data, onWeek, label }: { data: Progress; onWeek: (date: string) => void; label?: string }) {
  const { week } = data;
  const relation = week.is_current ? "This week" : week.is_future ? "Next week" : addDays(week.end, 7) >= data.today ? "Last week" : "Earlier week";
  return (
    <nav className="week-nav" aria-label={label ?? "Choose a week"}>
      <button type="button" className="icon-button" aria-label="Previous week" onClick={() => onWeek(addDays(week.start, -7))}>
        <Icon name="chevronLeft" />
      </button>
      <div>
        <b>{weekRange(week.start, week.end)}</b>
        <small>{relation}</small>
      </div>
      <button type="button" className="icon-button" aria-label="Next week" disabled={week.is_future} onClick={() => onWeek(addDays(week.start, 7))}>
        <Icon name="chevronRight" />
      </button>
    </nav>
  );
}

function comparison(current: number | null, previous: Progress["weekly"]["previous"]) {
  if (previous.planned === 0 || previous.completion_percent === null) return "No planned tasks the week before to compare with.";
  const last = `${previous.completion_percent}% (${previous.completed} of ${previous.planned})`;
  if (current === null) return `Last week: ${last}.`;
  if (current > previous.completion_percent) return `Up from ${last} the week before.`;
  if (current < previous.completion_percent) return `Down from ${last} the week before.`;
  return `Same as the week before: ${last}.`;
}

export function WeeklyProgress({ week, onWeek }: { week: string | null; onWeek: (date: string) => void }) {
  const app = useApp();
  const { data, error, retry } = useProgress(week);
  const [roadmaps, setRoadmaps] = useState<RoadmapProgress[]>([]);

  useEffect(() => {
    api<{ roadmaps: RoadmapProgress[] }>("/analytics/metrics?period=7d")
      .then((value) => setRoadmaps(value?.roadmaps ?? []))
      .catch(() => setRoadmaps([]));
  }, [app.dataVersion]);

  if (error && !data) return <ErrorState message={error} onRetry={retry} />;
  if (!data) return <Loading label="Loading weekly progress" />;

  const { overall, weekly, workstreams, accomplishments: done } = data;
  const nothingDone =
    done.completed_tasks.length + done.milestones.length + done.accomplishments.length + done.evidence_recorded === 0 && done.focus_minutes === 0;

  return (
    <div className="weekly-progress">
      <WeekNav data={data} onWeek={onWeek} />

      <section className="panel" aria-labelledby="week-title">
        <h2 id="week-title" className="panel-title">Planned tasks this week</h2>
        {weekly.planned === 0 ? (
          <p className="hint">
            No tasks were planned for this week: none were due, scheduled or on a daily plan.
            {weekly.completed_total > 0 && ` ${weekly.completed_total} task${weekly.completed_total === 1 ? " was" : "s were"} still completed.`}
          </p>
        ) : (
          <>
            <p className="hero-figure">
              <strong>{weekly.completion_percent}%</strong>
              <span>
                {weekly.completed} of {weekly.planned} planned tasks done · {weekly.outstanding} outstanding
              </span>
            </p>
            <Meter value={weekly.completed} max={weekly.planned} label="Planned tasks completed this week" />
          </>
        )}
        {weekly.unplanned_completed > 0 && (
          <p className="hint">
            Also {weekly.unplanned_completed} unplanned task{weekly.unplanned_completed === 1 ? "" : "s"} done (not part of the percentage).
          </p>
        )}
        <p className="hint">{comparison(weekly.completion_percent, weekly.previous)}</p>
        <details className="definitions">
          <summary>How this is counted</summary>
          <p>
            A task belongs to a week's plan when it was due that week, scheduled that week, or on a daily plan that week, and was not
            cancelled, archived or already done before the week began. Each task counts once. Past weeks are shown as they stood at the
            end of the week: finishing, deferring or archiving something later does not change them.
          </p>
        </details>
      </section>

      <section className="stat-grid" aria-label="All active tasks">
        <Stat label="Done" value={`${overall.completed}`} detail="tasks, all time" />
        <Stat label="Remaining" value={`${overall.remaining}`} detail="open tasks" />
        <Stat label="Overdue" value={`${overall.overdue}`} detail={`${overall.due_today} due today`} tone={overall.overdue ? "warn" : undefined} />
        <Stat
          label="Overall"
          value={overall.completion_percent === null ? "—" : `${overall.completion_percent}%`}
          detail={`done of ${overall.completed + overall.remaining} active tasks`}
        />
      </section>

      <DonutChart
        title="Completed tasks by workstream"
        unit="tasks"
        rows={workstreams.completed_tasks.map((row) => ({ key: row.area ?? "none", label: row.label, color: row.color, value: row.count }))}
        empty="No tasks completed in this week yet."
      />
      <DonutChart
        title="Tracked time by workstream"
        unit="tracked"
        format={formatMinutes}
        rows={workstreams.time.map((row) => ({ key: row.area ?? row.label, label: row.label, color: row.color, value: row.actual_minutes }))}
        empty="No focus sessions or completed activities with tracked time this week."
      />

      {roadmaps.length > 0 && (
        <section className="panel">
          <h2 className="panel-title">Roadmap progress</h2>
          <p className="hint">Completed milestone items of each roadmap, all time.</p>
          <ul className="roadmap-progress">
            {roadmaps.map((roadmap) => (
              <li key={roadmap.id}>
                <span>{roadmap.title}</span>
                <Meter value={roadmap.completed_eligible_items} max={roadmap.eligible_items} label={`${roadmap.title} progress`} />
                <small>
                  {roadmap.eligible_items ? `${Math.round(roadmap.progress_ratio * 100)}% · ` : ""}
                  {roadmap.completed_eligible_items}/{roadmap.eligible_items}
                </small>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel" aria-labelledby="accomplished-title">
        <h2 id="accomplished-title" className="panel-title">Accomplished · {weekRange(data.week.start, data.week.end)}</h2>
        {nothingDone ? (
          <p className="hint">Nothing recorded for this week yet.</p>
        ) : (
          <>
            <ul className="facts">
              <li><b>{done.completed_tasks.length}</b> {plural(done.completed_tasks.length, "task")} completed</li>
              <li><b>{done.milestones.length}</b> roadmap {plural(done.milestones.length, "milestone")} reached</li>
              <li><b>{formatMinutes(done.focus_minutes)}</b> focus time ({done.focus_sessions} {plural(done.focus_sessions, "session")})</li>
              <li><b>{done.learning.roadmap_items_completed}</b> learning {plural(done.learning.roadmap_items_completed, "item")} completed · <b>{done.learning.roadmap_tasks_completed}</b> roadmap-linked {plural(done.learning.roadmap_tasks_completed, "task")} done</li>
              <li><b>{done.evidence_recorded}</b> {plural(done.evidence_recorded, "piece")} of evidence · <b>{done.accomplishments.length}</b> {plural(done.accomplishments.length, "achievement")} recorded</li>
            </ul>
            {done.roadmaps_advanced.length > 0 && <p className="hint">Roadmaps advanced: {done.roadmaps_advanced.join(", ")}</p>}
            {done.completed_tasks.length > 0 && (
              <ul className="done-list" aria-label="Completed tasks">
                {done.completed_tasks.map((task) => (
                  <li key={task.id}>
                    <span className="category-dot" style={{ background: task.color }} aria-hidden="true" />
                    <span>{task.title}</span>
                    <small>{task.completed_on ? day(task.completed_on) : ""}</small>
                  </li>
                ))}
              </ul>
            )}
            {done.milestones.length > 0 && (
              <ul className="done-list" aria-label="Milestones reached">
                {done.milestones.map((node) => (
                  <li key={node.id}>
                    <Icon name="sparkle" size={14} />
                    <span>{node.title} <small>· {node.roadmap}</small></span>
                    <small>{day(node.completed_on)}</small>
                  </li>
                ))}
              </ul>
            )}
            {done.accomplishments.length > 0 && (
              <ul className="done-list" aria-label="Achievements">
                {done.accomplishments.map((item) => (
                  <li key={item.id}>
                    <Icon name="check" size={14} />
                    <span>{item.title}</span>
                    <small>{day(item.local_date)}</small>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <button type="button" className="button block" onClick={() => app.navigate(`#/insights/review?week=${data.week.start}`)}>
        Review this week
      </button>
    </div>
  );
}

function plural(count: number, word: string) {
  return count === 1 ? word : `${word}s`;
}

function Stat({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: "warn" }) {
  return (
    <article className={`stat ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
