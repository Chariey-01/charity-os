import { useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/time";
import type { Progress } from "../../lib/types";

export function weekRange(start: string, end: string) {
  const sameMonth = start.slice(0, 7) === end.slice(0, 7);
  return sameMonth
    ? `${Number(start.slice(8))}–${formatDate(end, { day: "numeric", month: "short" })}`
    : `${formatDate(start, { day: "numeric", month: "short" })} – ${formatDate(end, { day: "numeric", month: "short" })}`;
}

export function useProgress(week: string | null) {
  const app = useApp();
  const [data, setData] = useState<Progress | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    api<Progress>(`/progress${week ? `?week=${week}` : ""}`)
      .then((value) => {
        if (!alive) return;
        if (!value || typeof value !== "object" || !("weekly" in value)) throw new Error("Progress is unavailable right now.");
        setData(value);
        setError("");
      })
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [week, app.dataVersion, retry]);
  return { data, error, retry: () => setRetry((value) => value + 1) };
}
