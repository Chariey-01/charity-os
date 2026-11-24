import { FormEvent, useEffect, useState } from "react";

import { EntrySheetMode, useApp } from "../../app/context";
import { CategoryDot, Icon, Sheet, StatusBadge, Switch } from "../../components/ui";
import { ApiError, api, newId, patch, post } from "../../lib/api";
import {
  actualLabel,
  addDays,
  clock,
  durationLabel,
  formatDate,
  formatTime,
  hhmmToMinutes,
  instantFrom,
  localRange,
  minutesToHHMM,
} from "../../lib/time";
import type { Entry } from "../../lib/types";
import { useLiveSeconds } from "./hooks";

const RUNNING = new Set(["in_progress", "paused"]);
const CLOSED = new Set(["completed", "partially_completed", "skipped", "cancelled", "rescheduled"]);

export function EntrySheet({ entryId, initialMode, onClose }: { entryId: string; initialMode: EntrySheetMode; onClose: () => void }) {
  const app = useApp();
  const [entry, setEntry] = useState<Entry | null>(null);
  const [mode, setMode] = useState<EntrySheetMode>(initialMode);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api<Entry>(`/schedule-entries/${entryId}`)
      .then((value) => alive && setEntry(value))
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [entryId]);

  async function command(name: string, body: Record<string, unknown> = {}) {
    if (!entry) return;
    setBusy(true);
    setError("");
    try {
      const next = await post<Entry>(`/schedule-entries/${entry.id}/${name}`, { expected_version: entry.version, ...body });
      setEntry(next);
      app.refresh();
      return next;
    } catch (err) {
      if (err instanceof ApiError && err.code === "version_conflict") {
        setEntry(await api<Entry>(`/schedule-entries/${entry.id}`));
      }
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const title = entry?.title ?? "Activity";
  return (
    <Sheet title={mode === "finish" ? "Finish activity" : mode === "move" ? "Move or reschedule" : mode === "edit" ? "Edit activity" : title} onClose={onClose}>
      {!entry && !error && <p className="muted" role="status">Loading…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {entry && mode === "view" && <EntryDetail entry={entry} busy={busy} command={command} setMode={setMode} />}
      {entry && mode === "finish" && (
        <FinishForm
          entry={entry}
          busy={busy}
          onCancel={() => setMode("view")}
          onSubmit={async (body) => {
            const done = await command("complete", body);
            if (done) {
              app.celebrate(done.title, done.actual_seconds !== null ? `${actualLabel(done.actual_seconds)} recorded` : undefined);
              onClose();
            }
          }}
        />
      )}
      {entry && mode === "move" && <MoveForm entry={entry} onDone={(next) => { setEntry(next); setMode("view"); }} onCancel={() => setMode("view")} />}
      {entry && mode === "edit" && <EditForm entry={entry} onDone={(next) => { setEntry(next); setMode("view"); }} onCancel={() => setMode("view")} />}
    </Sheet>
  );
}

function EntryDetail({
  entry,
  busy,
  command,
  setMode,
}: {
  entry: Entry;
  busy: boolean;
  command: (name: string, body?: Record<string, unknown>) => Promise<Entry | undefined>;
  setMode: (mode: EntrySheetMode) => void;
}) {
  const app = useApp();
  const live = useLiveSeconds(entry);
  const tz = app.user.timezone;
  const disabled = busy || !app.online;
  return (
    <div className="entry-detail">
      <div className="entry-meta">
        <StatusBadge status={entry.status} />
        {entry.area_label && (
          <span className="tag">
            <CategoryDot color={entry.color} /> {entry.area_label}
          </span>
        )}
        {entry.tracking === "focus" && <span className="tag">Focus timer</span>}
      </div>
      <p className="entry-when">
        {formatDate(entry.local_date, { weekday: "long", day: "numeric", month: "long" })}
        <br />
        <b>
          {formatTime(entry.start_at, tz)} – {formatTime(entry.end_at, tz)}
        </b>{" "}
        · {durationLabel(entry.planned_minutes)} planned
      </p>
      {RUNNING.has(entry.status) && (
        <div className={`live-timer ${entry.status}`}>
          <span className="live-dot" aria-hidden="true" />
          <strong data-testid="entry-timer">{clock(live ?? 0)}</strong>
          <small>{entry.status === "paused" ? "Paused — time is not counting" : "Counting"}</small>
        </div>
      )}
      {CLOSED.has(entry.status) && entry.status !== "rescheduled" && entry.status !== "skipped" && (
        <p className="actual-line">
          Actual: <b>{actualLabel(entry.actual_seconds)}</b>
          {entry.actual_seconds !== null && ` of ${durationLabel(entry.planned_minutes)} planned`}
        </p>
      )}
      {entry.task_title && <p className="linked">Task: {entry.task_title}{entry.task_status === "completed" ? " ✓" : ""}</p>}
      {entry.roadmap_node_title && <p className="linked">Roadmap: {entry.roadmap_node_title}</p>}
      {entry.outcome && <p className="note"><b>Outcome</b> {entry.outcome}</p>}
      {entry.notes && <p className="note"><b>Notes</b> {entry.notes}</p>}

      <div className="action-grid">
        {entry.status === "scheduled" && (
          <>
            <button className="button" disabled={disabled} onClick={() => command("start", entry.tracking === "focus" ? { session_id: newId() } : {})}>
              <Icon name="play" size={18} /> Start
            </button>
            <button className="button secondary" disabled={disabled} onClick={() => setMode("finish")}>
              <Icon name="check" size={18} /> Mark done
            </button>
            <button className="button secondary" disabled={disabled} onClick={() => setMode("move")}>Move</button>
            <button className="button secondary" disabled={disabled} onClick={() => command("skip")}>Skip</button>
          </>
        )}
        {entry.status === "in_progress" && (
          <>
            <button className="button secondary" disabled={disabled} onClick={() => command("pause", { pause_id: newId() })}>
              <Icon name="pause" size={18} /> Pause
            </button>
            <button className="button" disabled={disabled} onClick={() => setMode("finish")}>
              <Icon name="check" size={18} /> Finish
            </button>
          </>
        )}
        {entry.status === "paused" && (
          <>
            <button className="button" disabled={disabled} onClick={() => command("resume")}>
              <Icon name="play" size={18} /> Resume
            </button>
            <button className="button secondary" disabled={disabled} onClick={() => setMode("finish")}>
              <Icon name="check" size={18} /> Finish
            </button>
          </>
        )}
        {(entry.status === "skipped" || entry.status === "cancelled") && (
          <button className="button" disabled={disabled} onClick={() => setMode("move")}>Reschedule</button>
        )}
        {entry.status === "rescheduled" && entry.rescheduled_to && (
          <button className="button secondary" onClick={() => app.openEntry(entry.rescheduled_to!)}>View new time</button>
        )}
      </div>
      <div className="link-row">
        {entry.status !== "rescheduled" && (
          <button className="text-button" disabled={disabled} onClick={() => setMode("edit")}>
            {CLOSED.has(entry.status) ? "Edit notes" : "Edit details"}
          </button>
        )}
        {(entry.status === "scheduled" || RUNNING.has(entry.status)) && (
          <button
            className="text-button danger"
            disabled={disabled}
            onClick={() => {
              if (window.confirm("Cancel this activity? It stays in your history as cancelled.")) command("cancel");
            }}
          >
            Cancel activity
          </button>
        )}
      </div>
    </div>
  );
}

function FinishForm({
  entry,
  busy,
  onSubmit,
  onCancel,
}: {
  entry: Entry;
  busy: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const app = useApp();
  const live = useLiveSeconds(entry);
  const focusLinked = Boolean(entry.focus_session);
  const timed = RUNNING.has(entry.status);
  const [outcome, setOutcome] = useState(entry.outcome);
  const [learning, setLearning] = useState("");
  const [partial, setPartial] = useState(false);
  const [completeTask, setCompleteTask] = useState(false);
  const [minutes, setMinutes] = useState<string>(timed && !focusLinked && live !== null ? String(Math.max(1, Math.round(live / 60))) : "");
  const [knowsTimes, setKnowsTimes] = useState(false);
  const [actualStart, setActualStart] = useState(entry.start_local.slice(11, 16));
  const [actualEnd, setActualEnd] = useState(entry.end_local.slice(11, 16));

  function submit(event: FormEvent) {
    event.preventDefault();
    const body: Record<string, unknown> = { outcome, partial, complete_task: completeTask };
    if (focusLinked) body.learning = learning;
    else if (knowsTimes && !timed) {
      const range = localRange(entry.local_date, actualStart, actualEnd);
      body.actual_started_at = instantFrom(range.start_local.slice(0, 10), actualStart, app.user.timezone);
      body.actual_ended_at = instantFrom(range.end_local.slice(0, 10), actualEnd, app.user.timezone);
    } else if (minutes !== "") body.actual_minutes = Number(minutes);
    onSubmit(body);
  }

  return (
    <form className="finish-form" onSubmit={submit}>
      <p className="muted">{entry.title}</p>
      {focusLinked ? (
        <p className="hint">Focus time is measured by the server timer: <b>{clock(live ?? 0)}</b>.</p>
      ) : timed ? (
        <div className="field">
          <label className="field">
            <span>Actual minutes</span>
            <input type="number" inputMode="numeric" min={0} max={1440} value={minutes} aria-describedby="measured-hint" onChange={(event) => setMinutes(event.target.value)} />
          </label>
          <small className="hint" id="measured-hint">Measured {actualLabel(live ?? 0)} excluding pauses. Adjust if needed.</small>
        </div>
      ) : (
        <>
          {!knowsTimes && (
            <label className="field">
              <span>How long did it take? (minutes)</span>
              <input type="number" inputMode="numeric" min={0} max={1440} value={minutes} placeholder="Leave blank if unsure" onChange={(event) => setMinutes(event.target.value)} />
            </label>
          )}
          <div className="chip-row">
            {!knowsTimes && (
              <button type="button" className="chip small" onClick={() => setMinutes(String(entry.planned_minutes))}>
                As planned · {durationLabel(entry.planned_minutes)}
              </button>
            )}
            <button type="button" className="chip small" aria-pressed={knowsTimes} onClick={() => setKnowsTimes(!knowsTimes)}>
              {knowsTimes ? "Enter minutes instead" : "I know the start and end"}
            </button>
          </div>
          {knowsTimes && (
            <div className="field-row">
              <label className="field">
                <span>Actual start</span>
                <input type="time" value={actualStart} onChange={(event) => setActualStart(event.target.value)} />
              </label>
              <label className="field">
                <span>Actual end</span>
                <input type="time" value={actualEnd} onChange={(event) => setActualEnd(event.target.value)} />
              </label>
            </div>
          )}
          <small className="hint">Nothing is assumed: blank means the actual time stays unknown.</small>
        </>
      )}
      <label className="field">
        <span>Outcome</span>
        <textarea rows={3} value={outcome} onChange={(event) => setOutcome(event.target.value)} placeholder="What happened? What did you get done?" />
      </label>
      {focusLinked && (
        <label className="field">
          <span>What did you learn?</span>
          <textarea rows={2} value={learning} onChange={(event) => setLearning(event.target.value)} />
        </label>
      )}
      <label className="check-row">
        <input type="checkbox" checked={partial} onChange={(event) => setPartial(event.target.checked)} />
        Only partly done
      </label>
      {entry.task && entry.task_status === "planned" && (
        <label className="check-row">
          <input type="checkbox" checked={completeTask} onChange={(event) => setCompleteTask(event.target.checked)} />
          Also mark the task “{entry.task_title}” complete
        </label>
      )}
      <div className="button-row">
        <button type="button" className="button secondary" onClick={onCancel}>Back</button>
        <button className="button" disabled={busy || !app.online}>{busy ? "Saving…" : partial ? "Save as partly done" : "Complete"}</button>
      </div>
    </form>
  );
}

function MoveForm({ entry, onDone, onCancel }: { entry: Entry; onDone: (entry: Entry) => void; onCancel: () => void }) {
  const app = useApp();
  const [date, setDate] = useState(entry.start_local.slice(0, 10));
  const [start, setStart] = useState(entry.start_local.slice(11, 16));
  const [end, setEnd] = useState(entry.end_local.slice(11, 16));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [overlap, setOverlap] = useState<ApiError | null>(null);
  const [newEntryId] = useState(newId);
  // A scheduled entry still in the future is only a plan: moving it rewrites
  // the time. Anything past, skipped or cancelled keeps its original record.
  const keepHistory = entry.status !== "scheduled" || new Date(entry.start_at).getTime() < Date.now();
  const duration = hhmmToMinutes(end) - hhmmToMinutes(start);

  function nudge(minutes: number, days = 0) {
    const length = (duration + 1440) % 1440 || 60;
    const startMinutes = hhmmToMinutes(start) + minutes;
    const dayShift = days + Math.floor(startMinutes / 1440);
    setDate(addDays(date, dayShift));
    setStart(minutesToHHMM(startMinutes));
    setEnd(minutesToHHMM(startMinutes + length));
  }

  async function save(allowOverlap = false) {
    setBusy(true);
    setError("");
    const range = localRange(date, start, end);
    try {
      if (keepHistory) {
        const result = await post<{ entry: Entry }>(`/schedule-entries/${entry.id}/reschedule`, {
          id: newEntryId,
          start_local: range.start_local,
          end_local: range.end_local,
          allow_overlap: allowOverlap,
          expected_version: entry.version,
        });
        app.toast("Rescheduled. The original stays in your history.", "success");
        onDone(result.entry);
      } else {
        const next = await patch<Entry>(`/schedule-entries/${entry.id}`, {
          start_local: range.start_local,
          end_local: range.end_local,
          allow_overlap: allowOverlap,
          expected_version: entry.version,
        });
        app.toast("Moved", "success");
        onDone(next);
      }
      app.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.code === "schedule_overlap") setOverlap(err);
      else setError(err instanceof Error ? err.message : "Could not move");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="move-form"
      onSubmit={(event) => {
        event.preventDefault();
        save(false);
      }}
    >
      <p className="hint">
        {keepHistory
          ? "Rescheduling creates a new time and keeps the original in your history."
          : "This activity has not started yet, so moving it simply changes the plan."}
      </p>
      <div className="chip-row">
        <button type="button" className="chip small" onClick={() => nudge(30)}>+30 min</button>
        <button type="button" className="chip small" onClick={() => nudge(60)}>+1 hour</button>
        <button type="button" className="chip small" onClick={() => nudge(0, 1)}>Tomorrow</button>
        <button type="button" className="chip small" onClick={() => nudge(0, 7)}>Next week</button>
      </div>
      <div className="field-row three">
        <label className="field">
          <span>Date</span>
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="field">
          <span>Start</span>
          <input type="time" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="field">
          <span>End</span>
          <input type="time" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {overlap ? (
        <div className="overlap" role="alert">
          <p><b>This overlaps</b> {overlap.conflicts.map((item) => item.title).join(", ")}.</p>
          <div className="button-row">
            <button type="button" className="button secondary" onClick={() => setOverlap(null)}>Change time</button>
            <button type="button" className="button" disabled={busy} onClick={() => save(true)}>Keep both</button>
          </div>
        </div>
      ) : (
        <div className="button-row">
          <button type="button" className="button secondary" onClick={onCancel}>Back</button>
          <button className="button" disabled={busy || !app.online}>{keepHistory ? "Reschedule" : "Move"}</button>
        </div>
      )}
    </form>
  );
}

function EditForm({ entry, onDone, onCancel }: { entry: Entry; onDone: (entry: Entry) => void; onCancel: () => void }) {
  const app = useApp();
  const closed = CLOSED.has(entry.status);
  const [title, setTitle] = useState(entry.title);
  const [area, setArea] = useState<string | null>(entry.area);
  const [notes, setNotes] = useState(entry.notes);
  const [outcome, setOutcome] = useState(entry.outcome);
  const [tracking, setTracking] = useState(entry.tracking);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body: Record<string, unknown> = { notes, outcome, expected_version: entry.version };
    if (!closed) Object.assign(body, { title, area });
    if (entry.status === "scheduled") body.tracking = tracking;
    try {
      const next = await patch<Entry>(`/schedule-entries/${entry.id}`, body);
      app.refresh();
      onDone(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="edit-form" onSubmit={submit}>
      {!closed && (
        <>
          <label className="field">
            <span>Title</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} />
          </label>
          <label className="field">
            <span>Category</span>
            <select value={area ?? ""} onChange={(event) => setArea(event.target.value || null)}>
              <option value="">None</option>
              {app.areas.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
        </>
      )}
      {entry.status === "scheduled" && (
        <Switch checked={tracking === "focus"} onChange={(value) => setTracking(value ? "focus" : "manual")} title="Track with the focus timer" />
      )}
      <label className="field">
        <span>Notes</span>
        <textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
      </label>
      {closed && (
        <label className="field">
          <span>Outcome</span>
          <textarea rows={3} value={outcome} onChange={(event) => setOutcome(event.target.value)} />
        </label>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button secondary" onClick={onCancel}>Back</button>
        <button className="button" disabled={busy || !app.online}>Save</button>
      </div>
    </form>
  );
}
