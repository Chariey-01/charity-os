/**
 * Time helpers. Every display uses the user's IANA timezone, never the
 * device's, so a phone set to another zone still shows the planned day.
 * Local dates are plain "YYYY-MM-DD" strings; arithmetic happens in UTC.
 */

const partsCache = new Map<string, Intl.DateTimeFormat>();

function partsFormatter(timeZone: string) {
  let formatter = partsCache.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    partsCache.set(timeZone, formatter);
  }
  return formatter;
}

export type Zoned = { date: string; minutes: number; hhmm: string; seconds: number };

export function zoned(instant: string | number | Date, timeZone: string): Zoned {
  const parts = Object.fromEntries(
    partsFormatter(timeZone)
      .formatToParts(new Date(instant))
      .map((part) => [part.type, part.value]),
  );
  const hour = Number(parts.hour) % 24;
  const minute = Number(parts.minute);
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: hour * 60 + minute,
    hhmm: `${String(hour).padStart(2, "0")}:${parts.minute}`,
    seconds: Number(parts.second),
  };
}

export function todayIn(timeZone: string, now = Date.now()) {
  return zoned(now, timeZone).date;
}

function utcDate(date: string) {
  return new Date(`${date}T00:00:00Z`);
}

export function addDays(date: string, days: number) {
  const value = utcDate(date);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

export function daysBetween(start: string, end: string) {
  return Math.round((utcDate(end).getTime() - utcDate(start).getTime()) / 86_400_000);
}

/** ISO weekday 1 (Mon) … 7 (Sun). */
export function isoWeekday(date: string) {
  return ((utcDate(date).getUTCDay() + 6) % 7) + 1;
}

export function weekStart(date: string, startsOn = 1) {
  return addDays(date, -((isoWeekday(date) - startsOn + 7) % 7));
}

export function monthStart(date: string) {
  return `${date.slice(0, 7)}-01`;
}

export function addMonths(date: string, months: number) {
  const value = utcDate(monthStart(date));
  value.setUTCMonth(value.getUTCMonth() + months);
  return value.toISOString().slice(0, 10);
}

/** Six-week grid of dates covering the month of ``date``. */
export function monthGrid(date: string, startsOn = 1) {
  const first = weekStart(monthStart(date), startsOn);
  return Array.from({ length: 42 }, (_, index) => addDays(first, index));
}

export function formatDate(date: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(undefined, { timeZone: "UTC", ...options }).format(
    new Date(`${date}T12:00:00Z`),
  );
}

export function formatTime(instant: string, timeZone: string) {
  return new Intl.DateTimeFormat(undefined, { timeZone, hour: "numeric", minute: "2-digit" }).format(
    new Date(instant),
  );
}

export function hhmmLabel(hhmm: string) {
  const [hour, minute] = hhmm.split(":").map(Number);
  return new Intl.DateTimeFormat(undefined, { timeZone: "UTC", hour: "numeric", minute: "2-digit" }).format(
    new Date(Date.UTC(2000, 0, 1, hour, minute)),
  );
}

export function hourLabel(hour: number) {
  return new Intl.DateTimeFormat(undefined, { timeZone: "UTC", hour: "numeric" }).format(new Date(Date.UTC(2000, 0, 1, hour)));
}

/** Actual time for display: unknown, seconds under a minute, or minutes. */
export function actualLabel(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "not recorded";
  if (seconds < 60) return `${seconds}s`;
  return durationLabel(seconds / 60);
}

export function durationLabel(minutes: number | null | undefined) {
  if (minutes === null || minutes === undefined) return "—";
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded}m`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

export function clock(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(Math.floor(safe / 3600))}:${pad(Math.floor((safe % 3600) / 60))}:${pad(safe % 60)}`;
}

export function elapsedSeconds(startedAt: string, now = Date.now()) {
  return Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
}

export function minutesToHHMM(total: number) {
  const clamped = ((Math.round(total) % 1440) + 1440) % 1440;
  return `${String(Math.floor(clamped / 60)).padStart(2, "0")}:${String(clamped % 60).padStart(2, "0")}`;
}

export function hhmmToMinutes(hhmm: string) {
  const [hour, minute] = hhmm.split(":").map(Number);
  return hour * 60 + minute;
}

/** Builds local start/end strings; an end at or before the start is the next day. */
export function localRange(date: string, start: string, end: string) {
  const endDate = hhmmToMinutes(end) <= hhmmToMinutes(start) ? addDays(date, 1) : date;
  return { start_local: `${date}T${start}`, end_local: `${endDate}T${end}`, crossesMidnight: endDate !== date };
}

/** Minutes [start, end) an instant range occupies within local ``date``. */
export function spanWithin(startAt: string, endAt: string, date: string, timeZone: string) {
  const start = zoned(startAt, timeZone);
  const end = zoned(endAt, timeZone);
  const from = start.date < date ? 0 : start.date > date ? 1440 : start.minutes;
  const to = end.date > date ? 1440 : end.date < date ? 0 : end.minutes;
  return { from, to: Math.max(to, from) };
}

export function relativeMinutes(minutes: number) {
  if (minutes <= 0) return "now";
  if (minutes < 60) return `in ${minutes} min`;
  return `in ${durationLabel(minutes)}`;
}

export function deviceTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** UTC ISO instant for wall-clock ``hhmm`` on local ``date`` in ``timeZone``. */
export function instantFrom(date: string, hhmm: string, timeZone: string) {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = hhmm.split(":").map(Number);
  const target = Date.UTC(year, month - 1, day, hour, minute);
  let guess = target;
  for (let pass = 0; pass < 3; pass += 1) {
    const local = zoned(guess, timeZone);
    const [ly, lm, ld] = local.date.split("-").map(Number);
    const asUtc = Date.UTC(ly, lm - 1, ld, Math.floor(local.minutes / 60), local.minutes % 60);
    if (asUtc === target) break;
    guess += target - asUtc;
  }
  return new Date(guess).toISOString();
}
