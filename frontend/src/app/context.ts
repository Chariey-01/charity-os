import { createContext, useContext } from "react";

import type { Area, Entry, Preferences, QuickAddDefaults, Session, User } from "../lib/types";

export type ToastKind = "info" | "success" | "error";

export type AppContextValue = {
  user: User;
  areas: Area[];
  allAreas: Area[];
  prefs: Preferences;
  session: (Session & { schedule_entry?: string | null }) | null;
  dataVersion: number;
  online: boolean;
  today: string;
  refresh: () => void;
  reloadAreas: () => Promise<void>;
  setPrefs: (prefs: Preferences) => void;
  setUser: (user: User) => void;
  toast: (message: string, kind?: ToastKind) => void;
  celebrate: (title: string, detail?: string) => void;
  openQuickAdd: (defaults?: QuickAddDefaults) => void;
  openEntry: (entry: Entry | string, mode?: EntrySheetMode) => void;
  navigate: (hash: string) => void;
  logout: () => Promise<void>;
};

export type EntrySheetMode = "view" | "finish" | "move" | "edit";

export const AppContext = createContext<AppContextValue | null>(null);

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside AppContext");
  return value;
}

export function areaById(areas: Area[], id: string | null | undefined) {
  return areas.find((area) => area.id === id);
}

/** Categories that default to the focus timer when chosen in quick add. */
const FOCUS_SLUGS = new Set([
  "software-engineering",
  "computer-science",
  "learning",
  "projects",
  "freelancing",
  "career",
  "ai",
  "reading",
]);

export function defaultsToFocus(area: Area | undefined) {
  return Boolean(area && FOCUS_SLUGS.has(area.slug));
}
