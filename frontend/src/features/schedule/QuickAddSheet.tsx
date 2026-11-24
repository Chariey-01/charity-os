import { FormEvent, useMemo, useState } from "react";

import { areaById, defaultsToFocus, useApp } from "../../app/context";
import { CategoryDot, Sheet, Switch } from "../../components/ui";
import { ApiError, newId, post } from "../../lib/api";
import { durationLabel, formatTime, hhmmToMinutes, localRange, minutesToHHMM, zoned } from "../../lib/time";
import type { Entry, QuickAddDefaults } from "../../lib/types";

const DURATIONS = [15, 30, 45, 60, 90, 120];

function nextHalfHour(timeZone: string) {
  const minutes = zoned(Date.now(), timeZone).minutes;
  return minutesToHHMM(Math.min(23 * 60 + 30, Math.ceil((minutes + 1) / 30) * 30));
}

export function QuickAddSheet({ defaults, onClose }: { defaults: QuickAddDefaults; onClose: () => void }) {
  const app = useApp();
  const [id] = useState(newId);
  const initialStart = defaults.start ?? nextHalfHour(app.user.timezone);
  const [title, setTitle] = useState(defaults.title ?? "");
  const [area, setArea] = useState<string | null>(defaults.area ?? null);
  const [date, setDate] = useState(defaults.date ?? app.today);
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(defaults.end ?? minutesToHHMM(hhmmToMinutes(initialStart) + 60));
  const [tracking, setTracking] = useState<"manual" | "focus">(
    defaults.tracking ?? (defaultsToFocus(areaById(app.areas, defaults.area)) ? "focus" : "manual"),
  );
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [overlap, setOverlap] = useState<ApiError | null>(null);

  const range = useMemo(() => localRange(date, start, end), [date, start, end]);
  const duration = (hhmmToMinutes(end) - hhmmToMinutes(start) + 1440) % 1440 || 1440;

  function chooseArea(next: string | null) {
    setArea(next);
    if (!defaults.tracking) setTracking(defaultsToFocus(areaById(app.areas, next)) ? "focus" : "manual");
  }

  async function save(allowOverlap = false) {
    setBusy(true);
    setError("");
    try {
      const entry = await post<Entry>("/schedule-entries", {
        id,
        title,
        area,
        tracking,
        notes,
        task: defaults.task ?? null,
        roadmap_node: defaults.roadmap_node ?? null,
        start_local: range.start_local,
        end_local: range.end_local,
        timezone_name: app.user.timezone,
        allow_overlap: allowOverlap,
      });
      app.toast(`Added “${entry.title}” at ${formatTime(entry.start_at, app.user.timezone)}`, "success");
      app.refresh();
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === "schedule_overlap") setOverlap(err);
      else setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      setError("Give the activity a title.");
      return;
    }
    save(false);
  }

  return (
    <Sheet title="Quick add" onClose={onClose}>
      <form className="quick-add" onSubmit={submit} noValidate>
        <label className="field">
          <span>Title</span>
          <input
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Study session, groceries, gym…"
            maxLength={200}
            required
            enterKeyHint="next"
          />
        </label>

        <fieldset className="field">
          <legend>Category</legend>
          <div className="chip-scroll" role="radiogroup" aria-label="Category">
            <button type="button" role="radio" aria-checked={area === null} className="chip" onClick={() => chooseArea(null)}>
              None
            </button>
            {app.areas.map((item) => (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={area === item.id}
                className="chip"
                onClick={() => chooseArea(item.id)}
              >
                <CategoryDot color={item.color} />
                {item.name}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="field-row three">
          <label className="field">
            <span>Date</span>
            <input type="date" value={date} onChange={(event) => setDate(event.target.value)} required />
          </label>
          <label className="field">
            <span>Start</span>
            <input
              type="time"
              value={start}
              step={300}
              onChange={(event) => {
                const next = event.target.value;
                setEnd(minutesToHHMM(hhmmToMinutes(next) + duration));
                setStart(next);
              }}
              required
            />
          </label>
          <label className="field">
            <span>End</span>
            <input type="time" value={end} step={300} onChange={(event) => setEnd(event.target.value)} required />
          </label>
        </div>
        <div className="chip-row" aria-label="Duration">
          {DURATIONS.map((minutes) => (
            <button
              key={minutes}
              type="button"
              className={`chip small ${duration === minutes ? "active" : ""}`}
              aria-pressed={duration === minutes}
              onClick={() => setEnd(minutesToHHMM(hhmmToMinutes(start) + minutes))}
            >
              {durationLabel(minutes)}
            </button>
          ))}
        </div>
        <p className="hint" aria-live="polite">
          {durationLabel(duration)}
          {range.crossesMidnight ? " · ends the next day" : ""}
        </p>

        <Switch checked={tracking === "focus"} onChange={(value) => setTracking(value ? "focus" : "manual")} title="Track with the focus timer" hint={tracking === "focus" ? "Starting it opens a server-timed focus session." : "Record actual time when you finish."} />

        <details className="more">
          <summary>More options</summary>
          <label className="field">
            <span>Notes</span>
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} />
          </label>
        </details>

        {error && <p className="form-error" role="alert">{error}</p>}
        {overlap && (
          <div className="overlap" role="alert">
            <p>
              <b>This overlaps</b> {overlap.conflicts.map((item) => `${item.title} (${formatTime(item.start_at, app.user.timezone)}–${formatTime(item.end_at, app.user.timezone)})`).join(", ")}.
            </p>
            <div className="button-row">
              <button type="button" className="button secondary" onClick={() => setOverlap(null)}>
                Change time
              </button>
              <button type="button" className="button" disabled={busy} onClick={() => save(true)}>
                Keep both
              </button>
            </div>
          </div>
        )}
        {!overlap && (
          <button className="button block" disabled={busy || !app.online}>
            {busy ? "Saving…" : app.online ? "Save" : "Offline — connect to save"}
          </button>
        )}
      </form>
    </Sheet>
  );
}
