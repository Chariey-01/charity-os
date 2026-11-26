import { useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { navigate, Route } from "../../app/router";
import { EmptyState, ErrorState, Icon, Loading, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { addDays, addMonths, formatDate, monthGrid, monthStart, weekStart, zoned } from "../../lib/time";
import type { Entry } from "../../lib/types";
import { DayGrid, EntryList, MonthGrid, WeekGrid } from "./views";

type View = "day" | "week" | "month";

function rangeFor(view: View, date: string): [string, string] {
  if (view === "day") return [date, date];
  if (view === "week") {
    const start = weekStart(date);
    return [start, addDays(start, 6)];
  }
  const cells = monthGrid(date);
  return [cells[0], cells[cells.length - 1]];
}

function heading(view: View, date: string) {
  if (view === "day") return formatDate(date, { weekday: "long", day: "numeric", month: "long" });
  if (view === "week") {
    const start = weekStart(date);
    const end = addDays(start, 6);
    const sameMonth = start.slice(0, 7) === end.slice(0, 7);
    return `${formatDate(start, { day: "numeric", month: sameMonth ? undefined : "short" })} – ${formatDate(end, { day: "numeric", month: "short" })}`;
  }
  return formatDate(monthStart(date), { month: "long", year: "numeric" });
}

export function ScheduleScreen({ route }: { route: Route }) {
  const app = useApp();
  const view = (["day", "week", "month"].includes(route.params.get("view") ?? "") ? route.params.get("view") : "day") as View;
  const date = route.params.get("date") ?? app.today;
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [start, end] = rangeFor(view, date);

  useEffect(() => {
    let alive = true;
    setError("");
    api<Entry[]>(`/schedule-entries?start=${start}&end=${end}`)
      .then((value) => alive && setEntries(value))
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [start, end, app.dataVersion, retry]);

  const go = (nextView: View, nextDate: string) => navigate(`#/schedule?view=${nextView}&date=${nextDate}`);
  const step = (direction: number) => {
    if (view === "day") go(view, addDays(date, direction));
    else if (view === "week") go(view, addDays(date, 7 * direction));
    else go(view, addMonths(date, direction));
  };
  const dayEntries = (entries ?? []).filter(
    (entry) => zoned(entry.start_at, app.user.timezone).date === date && entry.status !== "rescheduled",
  );

  return (
    <section className="screen schedule" aria-labelledby="schedule-title">
      <header className="screen-head row">
        <div>
          <p className="eyebrow">Schedule</p>
          <h1 id="schedule-title">{heading(view, date)}</h1>
        </div>
        <div className="date-nav">
          <button type="button" className="icon-button" onClick={() => step(-1)} aria-label={`Previous ${view}`}>
            <Icon name="chevronLeft" />
          </button>
          <button type="button" className="button secondary small" onClick={() => go(view, app.today)} disabled={date === app.today}>
            Today
          </button>
          <button type="button" className="icon-button" onClick={() => step(1)} aria-label={`Next ${view}`}>
            <Icon name="chevronRight" />
          </button>
        </div>
      </header>
      <Segmented<View>
        label="Calendar view"
        value={view}
        onChange={(next) => go(next, date)}
        options={[
          { value: "day", label: "Day" },
          { value: "week", label: "Week" },
          { value: "month", label: "Month" },
        ]}
      />
      {error && <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />}
      {!error && entries === null && <Loading label="Loading schedule" />}
      {!error && entries !== null && (
        <div className={entries === null ? "refetching" : ""}>
          {view === "day" && (
            <>
              {dayEntries.length === 0 && (
                <p className="hint inline-empty">Nothing scheduled. Tap a time to add something.</p>
              )}
              <DayGrid date={date} entries={entries} />
            </>
          )}
          {view === "week" && <WeekGrid start={start} entries={entries} onOpenDay={(day) => go("day", day)} />}
          {view === "month" && (
            <>
              <MonthGrid month={date} selected={date} entries={entries} onSelect={(day) => go("month", day)} />
              <section className="group">
                <div className="group-head">
                  <h2 className="group-title">{formatDate(date, { weekday: "long", day: "numeric", month: "long" })}</h2>
                  <button type="button" className="text-button" onClick={() => go("day", date)}>
                    Open day
                  </button>
                </div>
                {dayEntries.length ? (
                  <EntryList entries={dayEntries} label="Activities on the selected day" />
                ) : (
                  <EmptyState
                    title="Nothing planned"
                    action={
                      <button type="button" className="button secondary" onClick={() => app.openQuickAdd({ date })}>
                        <Icon name="plus" size={18} /> Add to this day
                      </button>
                    }
                  />
                )}
              </section>
            </>
          )}
        </div>
      )}
    </section>
  );
}
