import { FormEvent, useState } from "react";

import { useApp } from "../../app/context";
import { Field, FormActions } from "../../components/forms";
import { useSubmit } from "../../lib/forms";
import { EmptyState, ErrorState, Icon, Loading, ScreenHead, Sheet } from "../../components/ui";
import { post } from "../../lib/api";
import { formatMinutes } from "../../lib/format";
import { formatDate, monthLabel } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { Goal, JournalKind, Journey, JourneyEntry } from "../../lib/types";

const ENTRY_META: Record<string, { label: string; icon: string; tone: string }> = {
  goal_completed: { label: "Goal completed", icon: "goal", tone: "gold" },
  milestone_completed: { label: "Milestone reached", icon: "flag", tone: "green" },
  project_completed: { label: "Project completed", icon: "project", tone: "gold" },
  vision_realised: { label: "Vision realised", icon: "vision", tone: "gold" },
  learning_completed: { label: "Learning completed", icon: "roadmaps", tone: "blue" },
  roadmap_completed: { label: "Roadmap completed", icon: "roadmaps", tone: "gold" },
  challenge_completed: { label: "Challenge completed", icon: "challenge", tone: "gold" },
  goal_carried_forward: { label: "Carried forward", icon: "chevronRight", tone: "muted" },
  achievement: { label: "Achievement", icon: "sparkle", tone: "green" },
  evidence: { label: "Evidence", icon: "link", tone: "muted" },
  weekly_review: { label: "Weekly review", icon: "insights", tone: "muted" },
  journal_reflection: { label: "Reflection", icon: "me", tone: "muted" },
  journal_decision: { label: "Decision", icon: "flag", tone: "blue" },
  journal_challenge: { label: "Challenge overcome", icon: "challenge", tone: "green" },
  journal_lesson: { label: "Lesson", icon: "sparkle", tone: "blue" },
  journal_moment: { label: "Moment", icon: "sparkle", tone: "muted" },
  journal_review: { label: "Review", icon: "insights", tone: "blue" },
};

const JOURNAL_KINDS: [JournalKind, string][] = [
  ["reflection", "Reflection"],
  ["decision", "Important decision"],
  ["challenge", "Challenge overcome"],
  ["lesson", "Lesson learned"],
  ["moment", "Moment worth keeping"],
  ["review", "Monthly or annual review"],
];

type Filter = "all" | "milestones" | "learning" | "journal" | "evidence";
const FILTER_TYPES: Record<Exclude<Filter, "all">, (type: string) => boolean> = {
  milestones: (type) => ["goal_completed", "milestone_completed", "project_completed", "vision_realised", "challenge_completed", "roadmap_completed", "achievement"].includes(type),
  learning: (type) => ["learning_completed", "roadmap_completed"].includes(type),
  journal: (type) => type.startsWith("journal_") || type === "weekly_review",
  evidence: (type) => type === "evidence",
};

export function JourneyScreen() {
  const app = useApp();
  const [year, setYear] = useState(() => Number(app.today.slice(0, 4)));
  const [filter, setFilter] = useState<Filter>("all");
  const [writing, setWriting] = useState(false);
  const [yearEnd, setYearEnd] = useState(false);
  const { data, error, reload } = useResource<Journey>(`/journey?year=${year}`);
  const thisYear = Number(app.today.slice(0, 4));
  const isDecember = app.today.slice(5, 7) === "12";

  return (
    <section className="screen journey" aria-labelledby="journey-title">
      <ScreenHead
        eyebrow="Me · My Journey"
        title="Your record of growth"
        lead="Everything you finish, learn and decide, kept year after year. Challenges come and go; this history does not reset."
        action={
          <button type="button" className="button small" onClick={() => setWriting(true)}>
            <Icon name="plus" size={18} /> Write
          </button>
        }
      />
      {data && (
        <div className="chip-scroll" role="tablist" aria-label="Year">
          {data.years.map((value) => (
            <button key={value} type="button" role="tab" aria-selected={year === value} className="chip small" onClick={() => setYear(value)}>
              {value === thisYear ? `${value} · this year` : value}
            </button>
          ))}
        </div>
      )}
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <Loading label="Loading your journey" />
      ) : (
        <>
          <section className="journey-summary" aria-label={`${year} in numbers`}>
            <Stat value={data.summary.goals_completed} label="goals completed" />
            <Stat value={data.summary.milestones_completed} label="milestones" />
            <Stat value={data.summary.learning_completed} label="learning items" />
            <Stat value={data.summary.projects_completed} label="projects finished" />
            <Stat value={data.summary.tasks_completed} label="tasks done" />
            <Stat value={formatMinutes(data.summary.focus_minutes)} label="focused" />
          </section>

          {(year < thisYear || (year === thisYear && isDecember)) && (
            <button type="button" className="notice-panel year-end" onClick={() => setYearEnd(true)}>
              <Icon name="flag" />
              <span>
                <b>Close {year} deliberately</b>
                <small>Choose which unfinished goals continue. Nothing is copied forward automatically.</small>
              </span>
              <Icon name="chevronRight" />
            </button>
          )}

          {data.chapters.length > 0 && (
            <section aria-labelledby="chapters-title">
              <h2 id="chapters-title" className="section-title">
                Chapters
              </h2>
              <ul className="chapter-list">
                {data.chapters.map((chapter) => (
                  <li key={chapter.id} className={`chapter status-${chapter.status}`}>
                    <b>{chapter.name}</b>
                    <small>
                      {formatDate(chapter.start_date)} – {formatDate(chapter.end_date)} · {chapter.total_days} days · {chapter.status}
                    </small>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="chip-scroll" role="tablist" aria-label="Show">
            {(
              [
                ["all", "Everything"],
                ["milestones", "Achievements"],
                ["learning", "Learning"],
                ["journal", "Reflections"],
                ["evidence", "Evidence"],
              ] as [Filter, string][]
            ).map(([value, label]) => (
              <button key={value} type="button" role="tab" aria-selected={filter === value} className="chip small" onClick={() => setFilter(value)}>
                {label}
              </button>
            ))}
          </div>

          <Timeline entries={data.entries.filter((entry) => filter === "all" || FILTER_TYPES[filter](entry.type))} months={data.months} />
          {data.truncated && <p className="muted small">Showing the most recent 400 entries for {year}.</p>}
        </>
      )}
      {writing && <JournalSheet onClose={() => setWriting(false)} />}
      {yearEnd && <YearEndSheet year={year} onClose={() => setYearEnd(false)} />}
    </section>
  );
}

function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="stat">
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

function Timeline({ entries, months }: { entries: JourneyEntry[]; months: Journey["months"] }) {
  if (!entries.length && !months.length)
    return (
      <EmptyState
        icon="journey"
        title="Your journey starts with the first thing you finish"
        body="Complete a milestone, finish a learning item, record an achievement or write down a decision. It will appear here, dated and kept."
      />
    );
  const byMonth = new Map<string, JourneyEntry[]>();
  for (const entry of entries) {
    const key = entry.date.slice(0, 7);
    byMonth.set(key, [...(byMonth.get(key) ?? []), entry]);
  }
  const keys = Array.from(new Set([...byMonth.keys(), ...months.map((m) => m.month)])).sort().reverse();
  return (
    <div className="journey-timeline">
      {keys.map((key) => {
        const month = months.find((m) => m.month === key);
        const items = byMonth.get(key) ?? [];
        return (
          <section key={key} aria-label={monthLabel(key)}>
            <header className="month-head">
              <h3>{monthLabel(key)}</h3>
              {month && (
                <small>
                  {month.tasks_completed} {month.tasks_completed === 1 ? "task" : "tasks"} done · {formatMinutes(month.focus_minutes)} focused
                  {month.top_areas.length > 0 && ` · mostly ${month.top_areas.map(([name]) => name).join(", ")}`}
                </small>
              )}
            </header>
            <ol className="timeline-entries">
              {items.map((entry) => {
                const meta = ENTRY_META[entry.type] ?? { label: entry.type, icon: "sparkle", tone: "muted" };
                const note = (entry.detail.note || entry.detail.body || entry.detail.description || entry.detail.wins) as string | undefined;
                const url = entry.detail.url || entry.detail.evidence_url;
                return (
                  <li key={entry.id} className={`timeline-entry tone-${meta.tone}`}>
                    <span className="timeline-icon" aria-hidden="true">
                      <Icon name={meta.icon} size={16} />
                    </span>
                    <div>
                      <small className="eyebrow">
                        {meta.label} · {formatDate(entry.date)}
                      </small>
                      <b>{entry.title}</b>
                      {typeof entry.detail.roadmap === "string" && <small className="muted">{entry.detail.roadmap}</small>}
                      {typeof entry.detail.goal === "string" && entry.type === "milestone_completed" && <small className="muted">Goal: {entry.detail.goal}</small>}
                      {typeof entry.detail.project === "string" && entry.type === "milestone_completed" && <small className="muted">Project: {entry.detail.project}</small>}
                      {note && <p className="clamp-3">{String(note)}</p>}
                      {typeof url === "string" && url && (
                        <a href={url} target="_blank" rel="noreferrer noopener" className="small">
                          Open evidence
                        </a>
                      )}
                      {entry.detail.edited === true && <small className="muted">Edited · earlier wording kept</small>}
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
    </div>
  );
}

function JournalSheet({ onClose }: { onClose: () => void }) {
  const app = useApp();
  const [draft, setDraft] = useState({ kind: "reflection" as JournalKind, title: "", body: "", local_date: app.today });
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      form.setFields({ title: "Give it a title." });
      return;
    }
    const saved = await form.run((key) => post("/journal", { ...draft, title: draft.title.trim() }, { idempotencyKey: key }), "Added to My Journey");
    if (saved) onClose();
  }
  return (
    <Sheet title="Write in My Journey" onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Kind">
          <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as JournalKind })}>
            {JOURNAL_KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Title" error={form.fields.title}>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={180} />
        </Field>
        <Field label="In your words" optional>
          <textarea rows={6} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
        </Field>
        <Field label="Date" error={form.fields.local_date}>
          <input type="date" value={draft.local_date} onChange={(e) => setDraft({ ...draft, local_date: e.target.value })} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel="Save" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function YearEndSheet({ year, onClose }: { year: number; onClose: () => void }) {
  const app = useApp();
  const { data, error } = useResource<{ year: number; goals: Goal[] }>(`/journey/year-end?year=${year}`);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const form = useSubmit();
  const nextDefault = `${year + 1}-12-31`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const entries = Object.entries(chosen);
    if (!entries.length) {
      form.setError("Choose at least one goal to continue, or close this.");
      return;
    }
    const done = await form.run(async () => {
      for (const [id, date] of entries) await post(`/goals/${id}/carry-forward`, { target_date: date, note: `Continued from ${year}` });
      return true;
    }, `${entries.length} goal${entries.length === 1 ? "" : "s"} continue into ${year + 1}`);
    if (done) onClose();
  }

  return (
    <Sheet title={`Close ${year}`} onClose={onClose}>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <Loading />
      ) : data.goals.length === 0 ? (
        <p className="inline-empty">No unfinished goals are due by the end of {year}.</p>
      ) : (
        <form className="form" onSubmit={submit}>
          <p className="muted">Tick the goals that should continue and give each a new target date. Unticked goals stay as they are, in {year}'s chapter.</p>
          <ul className="year-end-list">
            {data.goals.map((goal) => (
              <li key={goal.id}>
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={goal.id in chosen}
                    onChange={(e) =>
                      setChosen((current) => {
                        const next = { ...current };
                        if (e.target.checked) next[goal.id] = nextDefault;
                        else delete next[goal.id];
                        return next;
                      })
                    }
                  />
                  <span>
                    <b>{goal.title}</b>
                    <small>{goal.target_date ? `Was due ${formatDate(goal.target_date)}` : "No target date"}</small>
                  </span>
                </label>
                {goal.id in chosen && (
                  <input type="date" aria-label={`New target date for ${goal.title}`} min={app.today} value={chosen[goal.id]} onChange={(e) => setChosen({ ...chosen, [goal.id]: e.target.value })} />
                )}
              </li>
            ))}
          </ul>
          <FormActions busy={form.busy} error={form.error} submitLabel="Continue selected goals" onCancel={onClose} />
        </form>
      )}
    </Sheet>
  );
}
