import { useEffect, useState } from "react";

export type Route = { path: string[]; params: URLSearchParams };

export const TABS = ["today", "schedule", "roadmaps", "insights", "profile"] as const;
export type Tab = (typeof TABS)[number];

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
  const head = route.path[0] as Tab;
  return TABS.includes(head) ? head : "today";
}
