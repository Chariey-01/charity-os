import { useEffect, useRef } from "react";

import { instantFrom, isoWeekday } from "./time";
import type { Entry, Preferences } from "./types";

/**
 * Foreground reminders.
 *
 * Without Web Push a PWA cannot wake itself, so reminders are checked by a
 * ticker that runs only while CharityOS is open (or briefly backgrounded).
 * When notification permission is granted they are shown through the service
 * worker as system notifications; otherwise they appear as in-app toasts.
 */

export type PermissionState = NotificationPermission | "unsupported";

export function canNotify() {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notificationPermission(): PermissionState {
  return canNotify() ? Notification.permission : "unsupported";
}

export async function requestNotificationPermission(): Promise<PermissionState> {
  if (!canNotify()) return "unsupported";
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

export type Reminder = { key: string; at: number; title: string; body: string; url: string };

export function buildReminders(entries: Entry[], prefs: Preferences, today: string, timeZone: string): Reminder[] {
  if (!prefs.reminders_enabled) return [];
  const reminders: Reminder[] = [];
  for (const entry of entries) {
    if (entry.status !== "scheduled") continue;
    const start = new Date(entry.start_at).getTime();
    if (prefs.reminder_lead_minutes > 0) {
      reminders.push({
        key: `lead:${entry.id}:${entry.start_at}`,
        at: start - prefs.reminder_lead_minutes * 60_000,
        title: `${entry.title} in ${prefs.reminder_lead_minutes} min`,
        body: entry.area_label || "Coming up next",
        url: "#/today",
      });
    }
    if (prefs.start_reminders_enabled) {
      reminders.push({ key: `start:${entry.id}:${entry.start_at}`, at: start, title: `Time for ${entry.title}`, body: "Tap to start it", url: "#/today" });
    }
  }
  if (prefs.daily_planning_reminder_enabled) {
    reminders.push({
      key: `plan:${today}`,
      at: new Date(instantFrom(today, prefs.daily_planning_time.slice(0, 5), timeZone)).getTime(),
      title: "Plan your day",
      body: "A few minutes now makes the day clearer.",
      url: "#/today",
    });
  }
  if (prefs.weekly_review_reminder_enabled && isoWeekday(today) === prefs.weekly_review_weekday) {
    reminders.push({
      key: `review:${today}`,
      at: new Date(instantFrom(today, prefs.weekly_review_time.slice(0, 5), timeZone)).getTime(),
      title: "Weekly review",
      body: "Look back on what you did this week.",
      url: "#/profile/reflect",
    });
  }
  return reminders;
}

/** Reminders that became due within ``windowMs`` and have not fired. */
export function dueReminders(reminders: Reminder[], now: number, fired: Set<string>, windowMs = 10 * 60_000) {
  return reminders.filter((reminder) => reminder.at <= now && reminder.at > now - windowMs && !fired.has(reminder.key));
}

const FIRED_KEY = "charityos:fired-reminders";

function loadFired(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(FIRED_KEY) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

function saveFired(fired: Set<string>) {
  try {
    localStorage.setItem(FIRED_KEY, JSON.stringify(Array.from(fired).slice(-200)));
  } catch {
    // Storage can be unavailable in private mode; duplicates are harmless.
  }
}

async function showSystemNotification(reminder: Reminder) {
  if (notificationPermission() !== "granted") return false;
  try {
    const registration = await navigator.serviceWorker?.getRegistration?.();
    if (registration) {
      await registration.showNotification(reminder.title, {
        body: reminder.body,
        tag: reminder.key,
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        data: { url: reminder.url },
      });
      return true;
    }
    new Notification(reminder.title, { body: reminder.body, tag: reminder.key });
    return true;
  } catch {
    return false;
  }
}

export function useReminders(
  entries: Entry[],
  prefs: Preferences,
  today: string,
  timeZone: string,
  onInApp: (reminder: Reminder) => void,
) {
  const callback = useRef(onInApp);
  callback.current = onInApp;
  useEffect(() => {
    if (!prefs.reminders_enabled) return;
    const reminders = buildReminders(entries, prefs, today, timeZone);
    const fired = loadFired();
    async function tick() {
      for (const reminder of dueReminders(reminders, Date.now(), fired)) {
        fired.add(reminder.key);
        saveFired(fired);
        const shown = document.visibilityState === "hidden" ? await showSystemNotification(reminder) : false;
        if (!shown) callback.current(reminder);
      }
    }
    tick();
    const timer = window.setInterval(tick, 20_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [entries, prefs, today, timeZone]);
}
