import { useState } from "react";

import { useApp } from "../app/context";
import { ApiError, newId } from "./api";

export type FieldErrors = Record<string, string>;

export function fieldErrors(err: unknown): FieldErrors {
  if (!(err instanceof ApiError)) return {};
  return Object.fromEntries(
    Object.entries(err.fields).map(([key, value]) => [key, Array.isArray(value) ? String(value[0]) : String(value)]),
  );
}

/**
 * Submit state for a form: one idempotency key per form, field errors from
 * the server, and a message that says what to do next.
 */
export function useSubmit() {
  const app = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<FieldErrors>({});
  // One key per submission attempt: a retry after a failure reuses it (so the
  // server replays instead of duplicating); a success starts a new one, so a
  // form that stays open (add milestone, check in) can save again.
  const [key, setKey] = useState(newId);

  async function run<T>(action: (key: string) => Promise<T>, success?: string): Promise<T | null> {
    if (!app.online) {
      setError("You are offline. Reconnect to save.");
      return null;
    }
    setBusy(true);
    setError("");
    setFields({});
    try {
      const result = await action(key);
      setKey(newId());
      if (success) app.toast(success, "success");
      app.refresh();
      return result;
    } catch (err) {
      setFields(fieldErrors(err));
      setError(
        err instanceof ApiError && err.code === "idempotency_key_reused"
          ? "This may already have been saved before the connection dropped. Close the form and check before trying again."
          : err instanceof Error
            ? err.message
            : "Could not save",
      );
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, fields, setFields, setError, run };
}

export function nullable(value: string) {
  return value.trim() === "" ? null : value;
}
