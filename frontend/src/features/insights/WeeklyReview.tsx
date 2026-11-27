import { FormEvent, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { ErrorState, Icon, Loading } from "../../components/ui";
import { ApiError, api, patch, post } from "../../lib/api";
import { formatMinutes } from "../../lib/format";
import { addDays, formatDate } from "../../lib/time";
import type { ProgressTask, WeeklyReview as Review } from "../../lib/types";
import { WeekNav } from "./WeeklyProgress";
import { useProgress, weekRange } from "./progressData";

const PROMPTS = [
  { key: "wins", label: "What went well?", placeholder: "Wins, progress, things worth repeating" },
  { key: "lessons", label: "Obstacles and lessons", placeholder: "What got in the way, and what would you change?" },
  { key: "next_week", label: "Next week's priorities", placeholder: "The few things that matter most next week" },
] as const;

type Answers = Record<(typeof PROMPTS)[number]["key"], string>;

/**
 * The week's facts beside three prompts. Unfinished work is only ever moved by
 * an explicit tap: nothing is marked done or dropped automatically. Saved
 * answers keep every earlier version (the server's revision history).
 */
export function WeeklyReview({ week, onWeek }: { week: string | null; onWeek: (date: string) => void }) {
  const app = useApp();
  const { data, error, retry } = useProgress(week);
  const [review, setReview] = useState<Review | null | undefined>(undefined);
  const [answers, setAnswers] = useState<Answers>({ wins: "", lessons: "", next_week: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const start = data?.week.start;
  useEffect(() => {
    if (!start) return;
    setReview(undefined);
    api<Review[]>("/weekly-reviews")
      .then((rows) => {
        const found = (Array.isArray(rows) ? rows : []).find((row) => row.week_start_date === start && !row.archived_at) ?? null;
        setReview(found);
        setAnswers({ wins: found?.wins ?? "", lessons: found?.lessons ?? "", next_week: found?.next_week ?? "" });
      })
      .catch(() => setReview(null));
  }, [start]);

  if (error && !data) return <ErrorState message={error} onRetry={retry} />;
  if (!data || review === undefined) return <Loading label="Loading weekly review" />;

  const planned = data.tasks.planned;
  const completed = data.tasks.completed;
  const unfinished = planned.filter((task) => task.status !== "done");
  const nextWeek = addDays(data.week.start, 7) > data.today ? addDays(data.week.start, 7) : data.today;
  const topTime = [...data.workstreams.time].sort((a, b) => b.actual_minutes - a.actual_minutes);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const saved = review
        ? await patch<Review>(`/weekly-reviews/${review.id}`, { ...answers, expected_version: review.version })
        : await post<Review>("/weekly-reviews", {
            week_start_date: data!.week.start,
            week_end_date: data!.week.end,
            timezone_name: app.user.timezone,
            ...answers,
          });
      setReview(saved);
      setMessage("Saved. Earlier versions are kept.");
    } catch (err) {
      setMessage(
        err instanceof ApiError && (err.code === "version_conflict" || err.code === "already_exists")
          ? "This review changed on another device. Reload the page to see the latest version before saving."
          : err instanceof Error
            ? err.message
            : "Could not save the review",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="weekly-review">
      <button type="button" className="text-button" onClick={() => app.navigate(`#/insights?week=${data.week.start}`)}>
        <Icon name="chevronLeft" size={16} /> Weekly progress
      </button>
      <WeekNav data={data} onWeek={onWeek} label="Review week" />

      <section className="stat-grid" aria-label="The week in numbers">
        <article className="stat"><span>Planned</span><strong>{planned.length}</strong><small>tasks</small></article>
        <article className="stat"><span>Completed</span><strong>{completed.length}</strong><small>{data.weekly.unplanned_completed} unplanned</small></article>
        <article className="stat"><span>Not completed</span><strong>{unfinished.length}</strong><small>of the plan</small></article>
        <article className="stat"><span>Focus</span><strong>{formatMinutes(data.accomplishments.focus_minutes)}</strong><small>{data.accomplishments.focus_sessions} sessions</small></article>
      </section>

      <section className="panel" aria-labelledby="unfinished-title">
        <h2 id="unfinished-title" className="panel-title">What was not completed</h2>
        {unfinished.length === 0 ? (
          <p className="hint">{planned.length ? "Everything planned was completed." : "Nothing was planned for this week."}</p>
        ) : (
          <ul className="review-list">
            {unfinished.map((task) => (
              <CarryRow key={task.id} task={task} target={nextWeek} />
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="completed-title">
        <h2 id="completed-title" className="panel-title">What was completed</h2>
        {completed.length === 0 ? (
          <p className="hint">No tasks completed this week.</p>
        ) : (
          <ul className="done-list">
            {completed.map((task) => (
              <li key={task.id}>
                <span className="category-dot" style={{ background: task.color }} aria-hidden="true" />
                <span>{task.title}{!task.planned && <small> · unplanned</small>}</span>
                <small>{task.completed_on ? formatDate(task.completed_on, { weekday: "short" }) : ""}</small>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="attention-title">
        <h2 id="attention-title" className="panel-title">Where the time and attention went</h2>
        {topTime.length === 0 && data.workstreams.completed_tasks.length === 0 ? (
          <p className="hint">No tracked time or completed tasks this week.</p>
        ) : (
          <ul className="facts">
            {topTime.map((row) => (
              <li key={`t-${row.label}`}>
                <span className="category-dot" style={{ background: row.color }} aria-hidden="true" /> {row.label}: <b>{formatMinutes(row.actual_minutes)}</b> tracked
              </li>
            ))}
            {data.workstreams.completed_tasks.map((row) => (
              <li key={`c-${row.label}`}>
                <span className="category-dot" style={{ background: row.color }} aria-hidden="true" /> {row.label}: <b>{row.count}</b> task{row.count === 1 ? "" : "s"} done
              </li>
            ))}
          </ul>
        )}
      </section>

      <form className="panel form" onSubmit={save} aria-labelledby="reflect-title">
        <h2 id="reflect-title" className="panel-title">Reflect on {weekRange(data.week.start, data.week.end)}</h2>
        {PROMPTS.map((prompt) => (
          <label key={prompt.key} className="field">
            <span>{prompt.label}</span>
            <textarea
              rows={3}
              value={answers[prompt.key]}
              placeholder={prompt.placeholder}
              onChange={(event) => setAnswers((current) => ({ ...current, [prompt.key]: event.target.value }))}
            />
          </label>
        ))}
        {message && <p className="hint" role="status">{message}</p>}
        <button className="button" disabled={busy || !app.online}>{review ? "Save changes" : "Save review"}</button>
      </form>
    </div>
  );
}

function CarryRow({ task, target }: { task: ProgressTask; target: string }) {
  const app = useApp();
  const [state, setState] = useState<"idle" | "busy" | "moved">("idle");
  const stillOpen = !["done", "cancelled"].includes(task.status_now) && !task.archived_now;
  return (
    <li>
      <span className="category-dot" style={{ background: task.color }} aria-hidden="true" />
      <span className="review-title">
        {task.title}
        <small>{task.due_date ? `Was due ${formatDate(task.due_date, { weekday: "short", day: "numeric", month: "short" })}` : "Was scheduled this week"}</small>
      </span>
      {!stillOpen ? (
        <small className="muted">{task.status_now === "done" ? "Done since" : task.archived_now ? "Archived" : "Cancelled"}</small>
      ) : state === "moved" ? (
        <small className="muted">Due {formatDate(target, { weekday: "short", day: "numeric" })}</small>
      ) : (
        <button
          type="button"
          className="button secondary small"
          disabled={state === "busy" || !app.online}
          onClick={async () => {
            setState("busy");
            try {
              await patch(`/tasks/${task.id}`, { due_date: target });
              setState("moved");
              app.refresh();
            } catch (err) {
              setState("idle");
              app.toast(err instanceof Error ? err.message : "Could not move the task", "error");
            }
          }}
        >
          Carry to {formatDate(target, { weekday: "short", day: "numeric" })}
        </button>
      )}
    </li>
  );
}
