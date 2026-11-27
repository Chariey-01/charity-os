/** public/sw.js push and notification-click handlers, executed for real. */
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(`${process.cwd()}/public/sw.js`, "utf8");
const ORIGIN = "https://app.test";
type Listener = (event: Record<string, unknown>) => void;

function load(windows: { url: string; focus: () => Promise<void>; navigate: (url: string) => Promise<void> }[] = []) {
  const listeners: Record<string, Listener> = {};
  const shown: { title: string; options: Record<string, unknown> }[] = [];
  const fetched: { url: string; init: RequestInit }[] = [];
  const opened: string[] = [];
  const self = {
    addEventListener: (type: string, listener: Listener) => (listeners[type] = listener),
    location: { origin: ORIGIN },
    registration: { showNotification: async (title: string, options: Record<string, unknown>) => void shown.push({ title, options }) },
    clients: { matchAll: async () => windows, openWindow: async (url: string) => void opened.push(url), claim: async () => undefined },
  };
  const network = async (url: string, init: RequestInit) => {
    fetched.push({ url, init });
    return new Response("{}");
  };
  new Function("self", "caches", "fetch", SOURCE)(self, {}, network);
  async function fire(type: string, event: Record<string, unknown>) {
    const waits: Promise<unknown>[] = [];
    listeners[type]({ ...event, waitUntil: (promise: Promise<unknown>) => waits.push(promise) });
    await Promise.all(waits);
  }
  return { fire, shown, fetched, opened };
}

describe("service worker notifications", () => {
  it("shows the server's reminder with Open and Snooze actions", async () => {
    const sw = load();
    const payload = { title: "Study RAG", body: "Starts at 09:00", url: "/#/schedule", tag: "entry:1", snooze: "tok" };
    await sw.fire("push", { data: { json: () => payload, text: () => JSON.stringify(payload) } });
    expect(sw.shown).toHaveLength(1);
    expect(sw.shown[0].title).toBe("Study RAG");
    expect(sw.shown[0].options).toMatchObject({ body: "Starts at 09:00", tag: "entry:1", data: { url: "/#/schedule", snooze: "tok" } });
    expect((sw.shown[0].options.actions as { action: string }[]).map((a) => a.action)).toEqual(["open", "snooze"]);
  });

  it("still shows something for a plain-text push", async () => {
    const sw = load();
    await sw.fire("push", { data: { json: () => { throw new Error("not json"); }, text: () => "Hello" } });
    expect(sw.shown[0]).toMatchObject({ title: "CharityOS", options: { body: "Hello" } });
  });

  it("snooze posts the signed token without cookies and opens nothing", async () => {
    const sw = load();
    let closed = false;
    await sw.fire("notificationclick", { action: "snooze", notification: { data: { url: "/#/today", snooze: "tok" }, close: () => (closed = true) } });
    expect(closed).toBe(true);
    expect(sw.fetched).toHaveLength(1);
    expect(sw.fetched[0].url).toBe("/api/v1/push/snooze");
    expect(sw.fetched[0].init.credentials).toBe("omit");
    expect(JSON.parse(String(sw.fetched[0].init.body))).toEqual({ token: "tok", minutes: 10 });
    expect(sw.opened).toEqual([]);
  });

  it("a tap focuses an open CharityOS window and navigates it, or opens one", async () => {
    const navigated: string[] = [];
    let focused = false;
    const sw = load([{ url: `${ORIGIN}/#/today`, focus: async () => void (focused = true), navigate: async (url) => void navigated.push(url) }]);
    await sw.fire("notificationclick", { action: "", notification: { data: { url: "/#/goals/1" }, close: () => undefined } });
    expect(focused).toBe(true);
    expect(navigated).toEqual([`${ORIGIN}/#/goals/1`]);
    const fresh = load();
    await fresh.fire("notificationclick", { action: "", notification: { data: { url: "/#/goals/1" }, close: () => undefined } });
    expect(fresh.opened).toEqual([`${ORIGIN}/#/goals/1`]);
  });
});
