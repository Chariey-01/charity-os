import { useEffect, useState } from "react";

export type Route = { path: string[]; params: URLSearchParams };

export const TABS = ["today", "tasks", "schedule", "plan", "me"] as const;
export type Tab = (typeof TABS)[number];

/** Screens reached through a hub keep that hub's tab highlighted. */
const SECTION_TAB: Record<string, Tab> = {
  plan: "plan",
  vision: "plan",
  goals: "plan",
  projects: "plan",
  roadmaps: "plan",
  challenges: "plan",
  me: "me",
  journey: "me",
  insights: "me",
  profile: "me",
  partners: "me",
  feedback: "me",
  reminders: "me",
  beta: "me",
  account: "me",
};

export const SCREENS = ["today", "tasks", "schedule", ...Object.keys(SECTION_TAB)] as const;

export function screenOf(route: Route): string {
  const head = route.path[0];
  return (SCREENS as readonly string[]).includes(head) ? head : "today";
}

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [pathname, query = ""] = raw.split("?");
  const path = pathname.split("/").filter(Boolean);
  return { path: path.length ? path : ["today"], params: new URLSearchParams(query) };
}

/** Hash routing keeps deep links and the Android back button working in the PWA. */
export function useHashRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(hash: string) {
  const next = hash.startsWith("#") ? hash : `#${hash}`;
  if (window.location.hash !== next) window.location.hash = next;
}

export function tabOf(route: Route): Tab {
  const head = route.path[0];
  if (SECTION_TAB[head]) return SECTION_TAB[head];
  return TABS.includes(head as Tab) ? (head as Tab) : "today";
}
