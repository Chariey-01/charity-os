import { useEffect, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { ErrorState, Icon, Loading, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/time";
import type { Insights } from "../../lib/types";
import { formatMinutes } from "../../lib/format";
import { CategoryBars, ColumnChart, Point } from "./Chart";
import { Direction } from "./Direction";
import { WeeklyProgress } from "./WeeklyProgress";
import { WeeklyReview } from "./WeeklyReview";

const PERIODS = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "90d", label: "90 days" },
  { value: "180d", label: "6 months" },
  { value: "challenge", label: "Challenge" },
  { value: "year", label: "This year" },
  { value: "all", label: "All time" },
];

type RoadmapProgress = { id: string; title: string; completed_eligible_items: number; eligible_items: number; progress_ratio: number };

const short = (date: string) => formatDate(date, { day: "numeric", month: "short" });
/** Compact axis tick: the day number, or the month name on the 1st. Full dates live in the tooltip and table. */
const tick = (date: string) => (date.endsWith("-01") ? formatDate(date, { month: "short" }) : String(Number(date.slice(8))));

type View = "week" | "direction" | "trends";

/**
 * Insights has two views: this week's task progress (the default, with the
 * weekly review under #/insights/review) and the longer-range trends.
 */
export function InsightsScreen({ route }: { route: Route }) {
  const app = useApp();
  const week = route.params.get("week");
  if (route.path[1] === "review") {
    return (
      <section className="screen insights" aria-labelledby="review-title">
        <header className="screen-head">
          <p className="eyebrow">Insights</p>
          <h1 id="review-title">Weekly review</h1>
          <p className="muted">What was planned, what happened, what comes next.</p>
        </header>
        <WeeklyReview week={week} onWeek={(date) => app.navigate(`#/insights/review?week=${date}`)} />
      </section>
    );
  }
  const requested = route.params.get("view");
  const view: View = requested === "trends" || requested === "direction" ? requested : "week";
  return (
    <section className="screen insights" aria-labelledby="insights-title">
      <header className="screen-head">
        <p className="eyebrow">Insights</p>
        <h1 id="insights-title">What actually happened</h1>
        <p className="muted">From your real records. No composite score.</p>
      </header>
      <Segmented<View>
        label="Insights view"
        value={view}
        onChange={(next) => app.navigate(next === "week" ? "#/insights" : `#/insights?view=${next}`)}
        options={[
          { value: "week", label: "This week" },
          { value: "direction", label: "Direction" },
          { value: "trends", label: "Trends" },
        ]}
      />
      {view === "week" ? (
        <WeeklyProgress week={week} onWeek={(date) => app.navigate(`#/insights?week=${date}`)} />
      ) : view === "direction" ? (
        <Direction />
      ) : (
        <Trends />
      )}
    </section>
  );
}

function Trends() {
  const app = useApp();
  const [period, setPeriod] = useState("30d");
  const [data, setData] = useState<Insights | null>(null);
  const [roadmaps, setRoadmaps] = useState<RoadmapProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      api<Insights>(`/insights?period=${period}`),
      api<{ roadmaps: RoadmapProgress[] }>(`/analytics/metrics?period=${period === "all" ? "year" : period}`).catch(() => ({ roadmaps: [] })),
    ])
      .then(([value, metrics]) => {
        if (!alive) return;
        setData(value);
        setRoadmaps(metrics.roadmaps ?? []);
        setError("");
      })
      .catch((err) => alive && setError(err.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [period, app.dataVersion, retry]);

  return (
    <>
      {data && <WeekCard data={data} />}
      <div className="chip-scroll filter-row" role="radiogroup" aria-label="Time range">
        {PERIODS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={period === option.value}
            className="chip"
            onClick={() => setPeriod(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {error && !data && <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />}
      {!data && !error && <Loading label="Loading insights" />}
      {data && <InsightsBody data={data} roadmaps={roadmaps} refetching={loading} />}
    </>
  );
}

function InsightsBody({ data, roadmaps, refetching }: { data: Insights; roadmaps: RoadmapProgress[]; refetching: boolean }) {
  const weekly = data.period.days > 31;
  const { totals } = data;
  const doneTotal = totals.completed + totals.partially_completed;
  const schedulePoints: Point[] = weekly
    ? data.schedule_weekly.map((week) => ({ label: short(week.week_start), value: week.completed, track: week.planned, detail: `Week of ${short(week.week_start)}` }))
    : data.schedule_daily.map((day) => ({ label: short(day.date), tick: tick(day.date), value: day.completed + day.partially_completed, track: day.planned, detail: formatDate(day.date, { weekday: "long", day: "numeric", month: "short" }) }));
  const focusPoints: Point[] = weekly
    ? data.schedule_weekly.map((week) => ({ label: short(week.week_start), value: week.focus_minutes, detail: `Week of ${short(week.week_start)}` }))
    : data.focus_daily.map((day) => ({ label: short(day.date), tick: tick(day.date), value: day.minutes }));
  const consistency: Point[] = data.schedule_weekly.map((week) => ({
    label: short(week.week_start),
    value: week.active_days,
    detail: `Week of ${short(week.week_start)} · ${week.active_days} of ${week.days_in_range} days`,
  }));
  const exercise = data.health.exercise_daily;
  const sleep = data.health.sleep_daily;
  const exercisePoints: Point[] = weekly ? bucketWeeks(exercise.map((day) => ({ date: day.date, value: day.minutes })), data.schedule_weekly.map((w) => w.week_start)) : exercise.map((day) => ({ label: short(day.date), tick: tick(day.date), value: day.minutes }));
  const sleepNights = sleep.filter((day) => day.hours > 0);
  const sleepPoints: Point[] = weekly
    ? bucketWeeks(sleep.map((day) => ({ date: day.date, value: day.hours })), data.schedule_weekly.map((w) => w.week_start), true)
    : sleep.map((day) => ({ label: short(day.date), tick: tick(day.date), value: day.hours }));
  const categoryRows = data.category_time
    .filter((row) => row.actual_minutes > 0 || row.planned_minutes > 0)
    .map((row) => ({ key: row.area ?? row.label, label: row.label, color: row.color, actual: row.actual_minutes, planned: row.planned_minutes }));

  return (
    <div className={`insights-body ${refetching ? "refetching" : ""}`} aria-busy={refetching}>

      <section className="stat-grid" aria-label="Totals">
        <Stat label="Activities done" value={`${doneTotal}`} detail={`of ${totals.planned} planned`} />
        <Stat label="Focus time" value={formatMinutes(totals.focus_minutes)} detail="completed sessions" />
        <Stat label="Tracked time" value={formatMinutes(totals.tracked_minutes)} detail="recorded actuals" />
        <Stat label="Active days" value={`${totals.active_days}`} detail={`of ${data.period.days}`} />
      </section>
      {(totals.skipped > 0 || totals.rescheduled > 0) && (
        <p className="hint">
          Also {totals.rescheduled} rescheduled and {totals.skipped} skipped. Plans change; that's normal.
        </p>
      )}

      {data.challenge && (
        <section className="panel challenge-panel">
          <p className="eyebrow">Challenge</p>
          <h2 className="panel-title">{data.challenge.name}</h2>
          <p>
            {data.challenge.phase === "active"
              ? `Day ${data.challenge.current_day} of ${data.challenge.total_days} · ${data.challenge.days_remaining} days left`
              : data.challenge.phase === "upcoming"
                ? `Starts ${short(data.challenge.start_date)}`
                : "Completed"}
          </p>
          <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={data.challenge.progress_percent} aria-label="Challenge time elapsed">
            <i style={{ width: `${data.challenge.progress_percent}%` }} />
          </div>
          <small>
            {plural(data.challenge.completed_activities, "activity", "activities")} · {formatMinutes(data.challenge.focus_minutes)} focus · {plural(data.challenge.active_days, "active day")}
          </small>
        </section>
      )}

      <ColumnChart
        title={weekly ? "Planned vs completed, by week" : "Planned vs completed"}
        points={schedulePoints}
        unit="done"
        valueLabel="Completed"
        trackLabel="Planned"
      />

      <section className="panel">
        <h2 className="panel-title">Time by category</h2>
        {categoryRows.length ? (
          <>
            <div className="legend" aria-hidden="true">
              <span><i className="key value" /> Actual</span>
              <span><i className="key track" /> Planned</span>
            </div>
            <CategoryBars rows={categoryRows} />
          </>
        ) : (
          <p className="hint">No activities in this range yet.</p>
        )}
      </section>

      <ColumnChart title={weekly ? "Focus minutes, by week" : "Focus minutes per day"} points={focusPoints} unit="min" />
      {consistency.length > 1 && <ColumnChart title="Weekly consistency (active days)" points={consistency} unit="days" />}

      {roadmaps.length > 0 && (
        <section className="panel">
          <h2 className="panel-title">Roadmap progress</h2>
          <ul className="roadmap-progress">
            {roadmaps.map((roadmap) => (
              <li key={roadmap.id}>
                <span>{roadmap.title}</span>
                <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={roadmap.eligible_items} aria-valuenow={roadmap.completed_eligible_items} aria-label={`${roadmap.title} progress`}>
                  <i style={{ width: `${roadmap.progress_ratio * 100}%` }} />
                </div>
                <small>{roadmap.completed_eligible_items}/{roadmap.eligible_items}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="health-section" aria-labelledby="health-title">
        <h2 id="health-title" className="section-title">Health</h2>
        <p className="hint">Kept separate from productivity. Logged exercise and sleep, plus completed exercise and sleep activities (counted once).</p>
        {exercise.some((day) => day.minutes > 0) ? (
          <ColumnChart title={weekly ? "Exercise minutes, by week" : "Exercise minutes"} points={exercisePoints} unit="min" tone="health" />
        ) : (
          <p className="hint">No exercise recorded in this range.</p>
        )}
        {sleepNights.length > 0 ? (
          <ColumnChart title={weekly ? "Average sleep per logged night, by week" : "Sleep hours"} points={sleepPoints} unit="h" tone="health" format={(value) => `${Math.round(value * 10) / 10}`} />
        ) : (
          <p className="hint">No sleep recorded in this range.</p>
        )}
      </section>
    </div>
  );
}

function bucketWeeks(days: { date: string; value: number }[], weekStarts: string[], average = false): Point[] {
  return weekStarts.map((start, index) => {
    const end = weekStarts[index + 1] ?? "9999-12-31";
    const inWeek = days.filter((day) => day.date >= start && day.date < end);
    const sum = inWeek.reduce((total, day) => total + day.value, 0);
    const counted = inWeek.filter((day) => day.value > 0).length;
    return {
      label: short(start),
      value: average ? (counted ? Math.round((sum / counted) * 10) / 10 : 0) : Math.round(sum),
      detail: `Week of ${short(start)}`,
    };
  });
}

function plural(count: number, one: string, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function WeekCard({ data }: { data: Insights }) {
  const { week } = data;
  return (
    <section className="panel week-card" aria-label="This week">
      <div className="group-head">
        <div>
          <p className="eyebrow">This week</p>
          <h2 className="panel-title">{week.completed} completed · {plural(week.active_days, "active day")}</h2>
        </div>
        {week.streak_weeks !== null && week.streak_weeks > 0 && <span className="tag">{week.streak_weeks}-week rhythm</span>}
      </div>
      <ol className="milestones large" aria-label="Weekly milestones">
        {week.milestones.map((milestone) => (
          <li key={milestone.target} className={milestone.reached ? "reached" : ""}>
            <span className="sr-only">{milestone.reached ? "Reached" : "Not yet"}:</span> {milestone.target}
          </li>
        ))}
      </ol>
      <details className="collapsible badges-toggle">
        <summary>
          <span className="group-title">Badges</span>
          <span className="count">{week.badges.filter((badge) => badge.earned).length} of {week.badges.length}</span>
        </summary>
      <ul className="badges" aria-label="Badges">
        {week.badges.map((badge) => (
          <li key={badge.key} className={badge.earned ? "earned" : ""}>
            <Icon name={badge.earned ? "sparkle" : "clock"} size={18} />
            <span>
              <b>{badge.title}</b>
              <small>{badge.description}</small>
            </span>
            <span className="sr-only">{badge.earned ? "Earned" : "Not yet earned"}</span>
          </li>
        ))}
      </ul>
      </details>
    </section>
  );
}
