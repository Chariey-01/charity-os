import { KeyboardEvent, MouseEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useApp } from "../../app/context";
import { CategoryDot, Icon, StatusBadge } from "../../components/ui";
import {
  actualLabel,
  addDays,
  durationLabel,
  formatDate,
  formatTime,
  hhmmLabel,
  hourLabel,
  isoWeekday,
  minutesToHHMM,
  monthGrid,
  zoned,
} from "../../lib/time";
import type { Entry } from "../../lib/types";
import { layoutDay, useEntryCommand } from "./hooks";

const HIDDEN_IN_GRID = new Set(["cancelled", "rescheduled"]);

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

export function WeekGrid({ start, entries, onOpenDay }: { start: string; entries: Entry[]; onOpenDay: (date: string) => void }) {
  const app = useApp();
  const tz = app.user.timezone;
  const hourPx = 40;
  const now = useNowMinutes(tz);
  const days = Array.from({ length: 7 }, (_, index) => addDays(start, index));
  const scroller = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    scroller.current?.scrollTo?.({ top: 7 * hourPx });
  }, [start]);

  function addAt(date: string, event: MouseEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest(".event")) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const minutes = Math.floor(((event.clientY - rect.top) / hourPx) * 2) * 30;
    const startMin = Math.max(0, Math.min(23 * 60 + 30, minutes));
    app.openQuickAdd({ date, start: minutesToHHMM(startMin), end: minutesToHHMM(Math.min(startMin + 60, 1439)) });
  }

  return (
    <div className="week">
      <div className="week-head">
        <span />
        {days.map((day) => (
          <button
            type="button"
            key={day}
            className={`week-day ${day === now.date ? "today" : ""}`}
            onClick={() => onOpenDay(day)}
            aria-label={`Open ${formatDate(day, { weekday: "long", day: "numeric", month: "long" })}`}
          >
            <small>{formatDate(day, { weekday: "narrow" })}</small>
            <b>{Number(day.slice(8))}</b>
          </button>
        ))}
      </div>
      <div className="week-body" ref={scroller}>
        <div className="week-inner" style={{ height: hourPx * 24 }}>
          <div className="week-gutter">
            {HOURS.filter((hour) => hour % 3 === 0 && hour).map((hour) => (
              <span key={hour} style={{ top: hour * hourPx }}>
                {hour}
              </span>
            ))}
          </div>
          {days.map((day) => (
            <div key={day} className="week-col" onClick={(event) => addAt(day, event)} data-testid={`week-col-${day}`}>
              {day === now.date && <div className="now-line" style={{ top: (now.minutes / 60) * hourPx }} aria-hidden="true" />}
              {layoutDay(entries, day, tz).map(({ entry, from, to, column, columns }) => (
                <button
                  type="button"
                  key={entry.id}
                  className={`event mini status-${entry.status}`}
                  style={{
                    top: (from / 60) * hourPx,
                    height: Math.max(14, ((to - from) / 60) * hourPx - 1),
                    left: `${(column / columns) * 100}%`,
                    width: `${100 / columns}%`,
                    ["--event" as string]: entry.color,
                  }}
                  onClick={() => app.openEntry(entry)}
                  aria-label={`${entry.title}, ${formatDate(day, { weekday: "long" })} ${formatTime(entry.start_at, tz)}`}
                >
                  <b>{entry.title}</b>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function MonthGrid({
  month,
  selected,
  entries,
  onSelect,
}: {
  month: string;
  selected: string;
  entries: Entry[];
  onSelect: (date: string) => void;
}) {
  const app = useApp();
  const tz = app.user.timezone;
  const today = app.today;
  const cells = monthGrid(month);
  const byDay = useMemo(() => {
    const map = new Map<string, Entry[]>();
    for (const entry of entries) {
      if (HIDDEN_IN_GRID.has(entry.status)) continue;
      const day = zoned(entry.start_at, tz).date;
      map.set(day, [...(map.get(day) ?? []), entry]);
    }
    return map;
  }, [entries, tz]);

  function onKey(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    onSelect(addDays(selected, moves[event.key]));
  }

  return (
    <div className="month" role="grid" aria-label={formatDate(month, { month: "long", year: "numeric" })} onKeyDown={onKey}>
      <div className="month-weekdays" role="row">
        {cells.slice(0, 7).map((day) => (
          <span key={day} role="columnheader" aria-label={formatDate(day, { weekday: "long" })}>
            {formatDate(day, { weekday: "narrow" })}
          </span>
        ))}
      </div>
      {[0, 1, 2, 3, 4, 5].map((row) => (
        <div className="month-row" role="row" key={row}>
          {cells.slice(row * 7, row * 7 + 7).map((day) => {
            const items = byDay.get(day) ?? [];
            const inMonth = day.slice(0, 7) === month.slice(0, 7);
            const doneCount = items.filter((item) => item.status === "completed" || item.status === "partially_completed").length;
            return (
              <button
                type="button"
                role="gridcell"
                key={day}
                tabIndex={day === selected ? 0 : -1}
                aria-selected={day === selected}
                className={`month-cell ${inMonth ? "" : "outside"} ${day === today ? "today" : ""} ${day === selected ? "selected" : ""} ${isoWeekday(day) >= 6 ? "weekend" : ""}`}
                onClick={() => onSelect(day)}
                aria-label={`${formatDate(day, { weekday: "long", day: "numeric", month: "long" })}, ${items.length} activities${items.length ? `, ${doneCount} done` : ""}`}
              >
                <span className="month-num">{Number(day.slice(8))}</span>
                <span className="month-dots" aria-hidden="true">
                  {items.slice(0, 3).map((item) => (
                    <CategoryDot key={item.id} color={item.color} />
                  ))}
                  {items.length > 3 && <small>+{items.length - 3}</small>}
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
