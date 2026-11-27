import { useCallback, useEffect, useState } from "react";

import { useApp } from "../app/context";
import { api } from "./api";

/** Load JSON from the API; reloads on the app's data version and on demand. */
export function useResource<T>(path: string | null) {
  const app = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    setError("");
    api<T>(path)
      .then((value) => alive && setData(value))
      .catch((err) => alive && setError(err instanceof Error ? err.message : "Could not load"));
    return () => {
      alive = false;
    };
  }, [path, tick, app.dataVersion]);

  return { data, error, reload, setData };
}
