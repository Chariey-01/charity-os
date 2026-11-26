import { useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { ApiError, newId, post } from "../../lib/api";
import { spanWithin } from "../../lib/time";
import type { Entry } from "../../lib/types";

const HIDDEN_IN_GRID = new Set(["cancelled", "rescheduled"]);

/** Live actual seconds: the server value plus time since it was fetched. */
export function useLiveSeconds(entry: Entry | null) {
  // Re-anchor whenever a fresh server copy arrives (start, pause, resume).
  const [anchor, setAnchor] = useState(() => ({ entry, at: Date.now() }));
  if (anchor.entry !== entry) setAnchor({ entry, at: Date.now() });
  const fetchedAt = anchor.at;
  const [now, setNow] = useState(() => Date.now());
  const running = entry?.status === "in_progress";
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  if (!entry || entry.actual_seconds === null) return null;
  return running ? entry.actual_seconds + Math.max(0, Math.floor((now - fetchedAt) / 1000)) : entry.actual_seconds;
}

/** Runs a one-tap lifecycle command from a list row. */
export function useEntryCommand() {
  const app = useApp();
  const [busyId, setBusyId] = useState<string | null>(null);
  async function run(entry: Entry, name: "start" | "pause" | "resume") {
    setBusyId(entry.id);
    try {
      const body: Record<string, unknown> = { expected_version: entry.version };
      if (name === "start" && entry.tracking === "focus") body.session_id = newId();
      if (name === "pause") body.pause_id = newId();
      await post<Entry>(`/schedule-entries/${entry.id}/${name}`, body);
      app.refresh();
    } catch (err) {
      app.toast(err instanceof ApiError ? err.message : "Could not update the activity", "error");
    } finally {
      setBusyId(null);
    }
  }
  return { run, busyId };
}

export type Placed = { entry: Entry; from: number; to: number; column: number; columns: number };

/** Assigns side-by-side columns to overlapping entries. */
export function layoutDay(entries: Entry[], date: string, timeZone: string): Placed[] {
  const spans = entries
    .filter((entry) => !HIDDEN_IN_GRID.has(entry.status))
    .map((entry) => ({ entry, ...spanWithin(entry.start_at, entry.end_at, date, timeZone) }))
    .filter((item) => item.to > item.from)
    .sort((a, b) => a.from - b.from || b.to - a.to);
  const placed: Placed[] = [];
  let cluster: Placed[] = [];
  let clusterEnd = -1;
  const flush = () => {
    const columns = Math.max(1, ...cluster.map((item) => item.column + 1));
    cluster.forEach((item) => (item.columns = columns));
    placed.push(...cluster);
    cluster = [];
  };
  for (const span of spans) {
    if (span.from >= clusterEnd && cluster.length) flush();
    const used = new Set(cluster.filter((item) => item.to > span.from).map((item) => item.column));
    let column = 0;
    while (used.has(column)) column += 1;
    cluster.push({ ...span, column, columns: 1 });
    clusterEnd = Math.max(clusterEnd, span.to);
  }
  if (cluster.length) flush();
  return placed;
}
