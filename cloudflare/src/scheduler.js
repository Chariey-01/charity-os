/**
 * Server-side reminders (backend/notifications). A cron trigger runs this
 * every minute; it asks Django to send due reminders only when something is
 * due, so the free-tier database is not woken every minute for nothing.
 *
 * Workers KV (binding REMINDERS_KV, optional) remembers when the backend said
 * the next reminder is due. Any change that can move that time (a reminder, a
 * schedule entry, preferences, a push subscription) clears it, so the next
 * tick asks the backend again. Without the binding, every tick dispatches.
 */
import { EDGE_SECRET_HEADER, backendOrigin } from "./edge.js";

export const CRON_SECRET_HEADER = "X-CharityOS-Cron-Secret";
export const NEXT_DUE_KEY = "reminders:next_due";
export const DISPATCH_PATH = "/api/v1/internal/reminders/dispatch";
// Writes to these may change when the next reminder is due.
const INVALIDATING = ["/api/v1/reminders", "/api/v1/schedule-entries", "/api/v1/preferences", "/api/v1/push/"];
// Ask the backend at least this often even if nothing seems due.
const MAX_SLEEP_MS = 6 * 60 * 60 * 1000;

export function invalidates(request) {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return false;
  const path = new URL(request.url).pathname;
  return INVALIDATING.some((prefix) => path.startsWith(prefix));
}

export async function forgetNextDue(env) {
  if (env.REMINDERS_KV) await env.REMINDERS_KV.delete(NEXT_DUE_KEY);
}

/** True when the backend should be asked to dispatch now. */
export async function dispatchIsDue(env, now) {
  if (!env.REMINDERS_KV) return true;
  const stored = await env.REMINDERS_KV.get(NEXT_DUE_KEY);
  if (!stored) return true;
  const due = Date.parse(stored);
  // A minute early: KV is eventually consistent and cron ticks are coarse.
  return Number.isNaN(due) || now >= due - 60_000 || due - now > MAX_SLEEP_MS;
}

export async function runScheduled(env, now = Date.now(), fetcher = fetch) {
  const secret = env.CRON_SECRET || "";
  if (secret.length < 32) {
    console.error("charityos-cron: CRON_SECRET is missing or too short; reminders are not sent");
    return { called: false, reason: "not_configured" };
  }
  if (!(await dispatchIsDue(env, now))) return { called: false, reason: "not_due" };
  const target = new URL(DISPATCH_PATH, backendOrigin(env));
  const response = await fetcher(
    new Request(target, {
      method: "POST",
      headers: {
        [EDGE_SECRET_HEADER]: env.EDGE_PROXY_SECRET || "",
        [CRON_SECRET_HEADER]: secret,
        "X-Forwarded-Proto": "https",
        "Content-Type": "application/json",
      },
      body: "{}",
    }),
  );
  if (!response.ok) {
    console.error(`charityos-cron: dispatch answered ${response.status}`);
    return { called: true, ok: false, status: response.status };
  }
  const result = await response.json();
  if (env.REMINDERS_KV && result.next_due_at) {
    await env.REMINDERS_KV.put(NEXT_DUE_KEY, result.next_due_at);
  }
  return { called: true, ok: true, sent: result.sent, next_due_at: result.next_due_at };
}
