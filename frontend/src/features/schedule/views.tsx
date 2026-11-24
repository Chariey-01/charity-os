import { MouseEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useApp } from "../../app/context";
import { Icon, StatusBadge } from "../../components/ui";
import { actualLabel, durationLabel, formatDate, formatTime, hhmmLabel, hourLabel, minutesToHHMM, zoned } from "../../lib/time";
import type { Entry } from "../../lib/types";
import { layoutDay, useEntryCommand } from "./hooks";

export function EntryRow({ entry, showDate = false }: { entry: Entry; showDate?: boolean }) {
  const app = useApp();
  const { run, busyId } = useEntryCommand();
  const tz = app.user.timezone;
  const done = entry.status === "completed" || entry.status === "partially_completed";
  const busy = busyId === entry.id || !app.online;
  return (
    <li className={`entry-row status-${entry.status}`}>
      <span className="entry-color" style={{ background: entry.color }} aria-hidden="true" />
      <button type="button" className="entry-main" onClick={() => app.openEntry(entry)}>
        <span className="entry-time">
          {showDate && `${formatDate(entry.local_date, { weekday: "short", day: "numeric" })} · `}
          {formatTime(entry.start_at, tz)} – {formatTime(entry.end_at, tz)}
        </span>
        <span className="entry-title">{entry.title}</span>
        <span className="entry-sub">
          {entry.area_label || "No category"}
          {done && ` · ${entry.actual_seconds !== null ? actualLabel(entry.actual_seconds) : "time not recorded"}`}
          {!done && ` · ${durationLabel(entry.planned_minutes)}`}
          {entry.tracking === "focus" && " · focus"}
        </span>
      </button>
      <span className="entry-side">
        {entry.status === "scheduled" && (
          <button type="button" className="round-action" disabled={busy} aria-label={`Start ${entry.title}`} onClick={() => run(entry, "start")}>
            <Icon name="play" size={18} />
          </button>
        )}
        {entry.status === "in_progress" && (
          <button type="button" className="round-action live" disabled={busy} aria-label={`Pause ${entry.title}`} onClick={() => run(entry, "pause")}>
            <Icon name="pause" size={18} />
          </button>
        )}
        {entry.status === "paused" && (
          <button type="button" className="round-action" disabled={busy} aria-label={`Resume ${entry.title}`} onClick={() => run(entry, "resume")}>
            <Icon name="play" size={18} />
          </button>
        )}
        {entry.status !== "scheduled" && entry.status !== "in_progress" && entry.status !== "paused" && <StatusBadge status={entry.status} />}
      </span>
    </li>
  );
}

export function EntryList({ entries, showDate = false, label }: { entries: Entry[]; showDate?: boolean; label: string }) {
  return (
    <ul className="entry-list" aria-label={label}>
      {entries.map((entry) => (
        <EntryRow key={entry.id} entry={entry} showDate={showDate} />
      ))}
    </ul>
  );
}

export function TimelineList({ entries }: { entries: Entry[] }) {
  const app = useApp();
  const tz = app.user.timezone;
  const nowMs = Date.now();
  return (
    <ol className="timeline" aria-label="Timeline">
      {entries.map((entry) => {
        const past = new Date(entry.end_at).getTime() < nowMs;
        return (
          <li key={entry.id} className={`timeline-item status-${entry.status} ${past ? "past" : ""}`}>
            <span className="timeline-time">{formatTime(entry.start_at, tz)}</span>
            <span className="timeline-dot" style={{ borderColor: entry.color }} aria-hidden="true">
              {(entry.status === "completed" || entry.status === "partially_completed") && <Icon name="check" size={12} />}
            </span>
            <button type="button" className="timeline-card" onClick={() => app.openEntry(entry)}>
              <b>{entry.title}</b>
              <small>
                {durationLabel(entry.planned_minutes)} · {entry.area_label || "No category"}
              </small>
              {entry.status !== "scheduled" && <StatusBadge status={entry.status} />}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function useNowMinutes(timeZone: string) {
  const [now, setNow] = useState(() => zoned(Date.now(), timeZone));
  useEffect(() => {
    const timer = window.setInterval(() => setNow(zoned(Date.now(), timeZone)), 60_000);
    return () => window.clearInterval(timer);
  }, [timeZone]);
  return now;
}

export function DayGrid({ date, entries, compact = false }: { date: string; entries: Entry[]; compact?: boolean }) {
  const app = useApp();
  const tz = app.user.timezone;
  const hourPx = compact ? 52 : 60;
  const scroller = useRef<HTMLDivElement>(null);
  const now = useNowMinutes(tz);
  const placed = useMemo(() => layoutDay(entries, date, tz), [entries, date, tz]);
  const isToday = now.date === date;

  useLayoutEffect(() => {
    const first = placed[0]?.from ?? 7 * 60;
    const target = isToday ? now.minutes - 60 : Math.min(first, 7 * 60);
    scroller.current?.scrollTo?.({ top: Math.max(0, (target / 60) * hourPx) });
    // Only on day change; later updates must not yank the scroll position.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  function addAt(hour: number, event: MouseEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const half = rect.height && event.clientY ? (event.clientY - rect.top > rect.height / 2 ? 30 : 0) : 0;
    const start = hour * 60 + half;
    app.openQuickAdd({ date, start: minutesToHHMM(start), end: minutesToHHMM(Math.min(start + 60, 1439)) });
  }

  return (
    <div className="day-grid" ref={scroller} style={{ ["--hour" as string]: `${hourPx}px` }}>
      <div className="day-grid-inner" style={{ height: hourPx * 24 }}>
        {HOURS.map((hour) => (
          <div key={hour} className="hour-row" style={{ top: hour * hourPx }}>
            <span className="hour-label">{hour === 0 ? "" : hourLabel(hour)}</span>
            <button
              type="button"
              className="hour-slot"
              aria-label={`Add activity at ${hhmmLabel(`${String(hour).padStart(2, "0")}:00`)}`}
              onClick={(event) => addAt(hour, event)}
            />
          </div>
        ))}
        {isToday && (
          <div className="now-line" style={{ top: (now.minutes / 60) * hourPx }} aria-hidden="true">
            <span />
          </div>
        )}
        <div className="day-events">
          {placed.map(({ entry, from, to, column, columns }) => {
            const height = Math.max(22, ((to - from) / 60) * hourPx - 2);
            return (
              <button
                type="button"
                key={entry.id}
                className={`event status-${entry.status} ${height < 40 ? "tiny" : ""}`}
                style={{
                  top: (from / 60) * hourPx + 1,
                  height,
                  left: `calc(${(column / columns) * 100}% + 2px)`,
                  width: `calc(${100 / columns}% - 4px)`,
                  ["--event" as string]: entry.color,
                }}
                onClick={() => app.openEntry(entry)}
                aria-label={`${entry.title}, ${formatTime(entry.start_at, tz)} to ${formatTime(entry.end_at, tz)}, ${entry.status.replace("_", " ")}`}
              >
                <b>{entry.title}</b>
                {height >= 40 && (
                  <small>
                    {formatTime(entry.start_at, tz)} – {formatTime(entry.end_at, tz)}
                  </small>
                )}
                {(entry.status === "completed" || entry.status === "partially_completed") && (
                  <span className="event-check"><Icon name="check" size={12} /></span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
