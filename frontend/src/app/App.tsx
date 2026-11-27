import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "../components/ui";
import { FocusBar } from "../features/focus/FocusBar";
import { ChallengesScreen } from "../features/challenges/ChallengesScreen";
import { GoalsScreen } from "../features/goals/GoalsScreen";
import { InsightsScreen } from "../features/insights/InsightsScreen";
import { JourneyScreen } from "../features/journey/JourneyScreen";
import { MeScreen } from "../features/me/MeScreen";
import { PlanScreen } from "../features/plan/PlanScreen";
import { ProjectsScreen } from "../features/projects/ProjectsScreen";
import { ProfileScreen } from "../features/profile/ProfileScreen";
import { RoadmapsScreen } from "../features/roadmaps/RoadmapsScreen";
import { EntrySheet } from "../features/schedule/EntrySheet";
import { QuickAddSheet } from "../features/schedule/QuickAddSheet";
import { ScheduleScreen } from "../features/schedule/ScheduleScreen";
import { TaskSheet, TaskSheetMode } from "../features/tasks/TaskSheet";
import { TasksScreen } from "../features/tasks/TasksScreen";
import { TodayScreen } from "../features/today/TodayScreen";
import { VisionScreen } from "../features/vision/VisionScreen";
import { ApiError, api, onSessionEnded, post } from "../lib/api";
import { useOnline } from "../lib/pwa";
import { useReminders } from "../lib/reminders";
import { addDays, todayIn } from "../lib/time";
import type { Area, Entry, Preferences, QuickAddDefaults, Session, Task, User } from "../lib/types";
import { AppContext, AppContextValue, EntrySheetMode, ToastKind } from "./context";
import { navigate, screenOf, tabOf, useHashRoute } from "./router";

// Kept exported so timestamp reconstruction stays independently testable.
// eslint-disable-next-line react-refresh/only-export-components
export { elapsedSeconds } from "../lib/time";

const DEFAULT_PREFS: Preferences = {
  reminders_enabled: false,
  reminder_lead_minutes: 10,
  start_reminders_enabled: true,
  daily_planning_reminder_enabled: false,
  daily_planning_time: "07:30:00",
  weekly_review_reminder_enabled: false,
  weekly_review_weekday: 7,
  weekly_review_time: "18:00:00",
  show_streaks: false,
  celebrations_enabled: true,
  default_today_view: "agenda",
};

const NAV = [
  { tab: "today", label: "Today", icon: "today" },
  { tab: "tasks", label: "Tasks", icon: "tasks" },
  { tab: "schedule", label: "Schedule", icon: "schedule" },
  { tab: "plan", label: "Plan", icon: "plan" },
  { tab: "me", label: "Me", icon: "me" },
] as const;

type Toast = { id: number; message: string; kind: ToastKind };

function Login({ onLogin, notice }: { onLogin: (user: User) => void; notice?: string }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api("/auth/csrf");
      onLogin(await post<User>("/auth/login", { email: form.get("email"), password: form.get("password") }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth">
      <section className="auth-card">
        <div className="brand-mark" aria-hidden="true">C</div>
        <p className="eyebrow">CharityOS</p>
        <h1>Plan the day. Live it. See what happened.</h1>
        <p className="muted">Your permanent personal scheduler for work, learning, health and life.</p>
        {notice && <p className="notice" role="status">{notice}</p>}
        <form onSubmit={submit} className="form">
          <label className="field">
            <span>Email</span>
            <input name="email" type="email" required autoComplete="email" inputMode="email" />
          </label>
          <label className="field">
            <span>Password</span>
            <input name="password" type="password" required autoComplete="current-password" />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button block" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </section>
    </main>
  );
}

export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [bootError, setBootError] = useState("");
  const [notice, setNotice] = useState("");
  const signedIn = useRef(false);
  signedIn.current = Boolean(user);

  // The server ended the session (expiry, sign-out elsewhere, erasure): drop
  // everything the signed-in shell held and ask for sign-in again. CSRF and
  // permission errors never come here (lib/api.ts).
  useEffect(() => {
    onSessionEnded(() => {
      if (!signedIn.current) return;
      setUser(null);
      setNotice("Your session has ended. Sign in again to carry on where you left off.");
    });
    return () => onSessionEnded(null);
  }, []);

  const boot = useCallback(async () => {
    setBootError("");
    try {
      setUser(await api<User>("/me"));
    } catch (err) {
      if (err instanceof ApiError && err.offline) setBootError(err.message);
      else setUser(null);
    }
  }, []);

  useEffect(() => {
    boot();
  }, [boot]);

  // Opened offline: try again by itself as soon as the connection is back.
  useEffect(() => {
    if (!bootError) return;
    window.addEventListener("online", boot);
    return () => window.removeEventListener("online", boot);
  }, [bootError, boot]);

  if (bootError) {
    return (
      <main className="loading" role="alert">
        <Icon name="offline" size={32} />
        <p>{bootError}</p>
        <button type="button" className="button" onClick={boot}>Try again</button>
      </main>
    );
  }
  if (user === undefined) return <main className="loading" role="status">Loading CharityOS…</main>;
  if (!user) {
    return (
      <Login
        notice={notice}
        onLogin={(value) => {
          setNotice("");
          setUser(value);
        }}
      />
    );
  }
  return <Shell user={user} setUser={setUser} />;
}

function Shell({ user, setUser }: { user: User; setUser: (user: User | null) => void }) {
  const route = useHashRoute();
  const tab = tabOf(route);
  const screenName = screenOf(route);
  const online = useOnline();
  const [allAreas, setAllAreas] = useState<Area[]>([]);
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [session, setSession] = useState<AppContextValue["session"]>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [quickAdd, setQuickAdd] = useState<QuickAddDefaults | null>(null);
  const [entrySheet, setEntrySheet] = useState<{ id: string; mode: EntrySheetMode; key: number } | null>(null);
  const [taskSheet, setTaskSheet] = useState<{ id: string | null; defaults?: Partial<Task>; mode: TaskSheetMode; key: number } | null>(null);
  const [celebration, setCelebration] = useState<{ title: string; detail?: string; key: number } | null>(null);
  const [reminderEntries, setReminderEntries] = useState<Entry[]>([]);
  const [today, setToday] = useState(() => todayIn(user.timezone));
  const toastId = useRef(0);

  useEffect(() => {
    setToday(todayIn(user.timezone));
    const timer = window.setInterval(() => setToday(todayIn(user.timezone)), 60_000);
    return () => window.clearInterval(timer);
  }, [user.timezone]);

  const toast = useCallback((message: string, kind: ToastKind = "info") => {
    toastId.current += 1;
    const id = toastId.current;
    setToasts([{ id, message, kind }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), kind === "error" ? 6000 : 2800);
  }, []);

  const reloadAreas = useCallback(async () => {
    // Archived categories are included so Profile can list and restore them.
    setAllAreas(await api<Area[]>("/areas?archived=include"));
  }, []);

  useEffect(() => {
    reloadAreas().catch(() => toast("Could not load categories", "error"));
    api<Preferences>("/preferences").then(setPrefs).catch(() => undefined);
  }, [reloadAreas, toast]);

  useEffect(() => {
    api<Session & { schedule_entry?: string | null }>("/sessions/active")
      .then((value) => setSession(value ?? null))
      .catch(() => undefined);
  }, [dataVersion]);

  useEffect(() => {
    if (!prefs.reminders_enabled) return;
    api<Entry[]>(`/schedule-entries?start=${today}&end=${addDays(today, 1)}`)
      .then(setReminderEntries)
      .catch(() => undefined);
  }, [prefs.reminders_enabled, today, dataVersion]);

  useReminders(reminderEntries, prefs, today, user.timezone, (reminder) => toast(`${reminder.title}. ${reminder.body}`));

  // Refresh when the app returns to the foreground; the server may have moved on.
  useEffect(() => {
    const onVisible = () => document.visibilityState === "visible" && setDataVersion((value) => value + 1);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
  }, []);

  // Shortcut from the manifest: /#/today?add=1 opens quick add.
  useEffect(() => {
    if (route.params.get("add") === "1") {
      setQuickAdd({});
      navigate(`#/${route.path.join("/")}`);
    }
  }, [route]);

  const areas = useMemo(() => allAreas.filter((area) => !area.archived_at), [allAreas]);

  const value: AppContextValue = useMemo(
    () => ({
      user,
      areas,
      allAreas,
      prefs,
      session,
      dataVersion,
      online,
      today,
      refresh: () => setDataVersion((value) => value + 1),
      reloadAreas,
      setPrefs,
      setUser,
      toast,
      celebrate: (title, detail) => {
        if (!prefs.celebrations_enabled) {
          toast(`Done: ${title}`, "success");
          return;
        }
        setCelebration({ title, detail, key: Date.now() });
        window.setTimeout(() => setCelebration(null), 2600);
      },
      openQuickAdd: (defaults = {}) => setQuickAdd(defaults),
      openEntry: (entry, mode = "view") =>
        setEntrySheet({ id: typeof entry === "string" ? entry : entry.id, mode, key: Date.now() }),
      openTask: (task, defaults) => setTaskSheet({ id: task, defaults, mode: task ? "view" : "edit", key: Date.now() }),
      navigate,
      logout: async () => {
        await post("/auth/logout").catch(() => undefined);
        setUser(null);
      },
    }),
    [user, areas, allAreas, prefs, session, dataVersion, online, today, reloadAreas, setUser, toast],
  );

  const screens: Record<string, () => ReactNode> = {
    tasks: () => <TasksScreen route={route} />,
    schedule: () => <ScheduleScreen route={route} />,
    plan: () => <PlanScreen />,
    vision: () => <VisionScreen />,
    goals: () => <GoalsScreen route={route} />,
    projects: () => <ProjectsScreen route={route} />,
    roadmaps: () => <RoadmapsScreen route={route} />,
    challenges: () => <ChallengesScreen />,
    me: () => <MeScreen />,
    journey: () => <JourneyScreen />,
    insights: () => <InsightsScreen route={route} />,
    profile: () => <ProfileScreen route={route} />,
  };
  const screen = (screens[screenName] ?? (() => <TodayScreen key={prefs.default_today_view} />))();

  return (
    <AppContext.Provider value={value}>
      <div className={`app-shell ${session && !(tab === "today" && session.schedule_entry) ? "has-focus" : ""}`}>
        <a className="skip-link" href="#main">Skip to content</a>
        {!online && (
          <div className="offline-banner" role="status">
            <Icon name="offline" size={18} /> Offline. You can look around; changes need a connection.
          </div>
        )}
        <main id="main" className="content" tabIndex={-1}>
          {screen}
        </main>
        {!(tab === "today" && session?.schedule_entry) && <FocusBar />}
        <button
          type="button"
          className="fab"
          onClick={() =>
            tab === "tasks" || tab === "plan"
              ? setTaskSheet({ id: null, mode: "edit", key: Date.now() })
              : setQuickAdd({ date: tab === "schedule" ? route.params.get("date") ?? today : today })
          }
          aria-label={tab === "tasks" || tab === "plan" ? "Add a task" : "Quick add activity"}
        >
          <Icon name="plus" size={26} />
        </button>
        <nav className="bottom-nav" aria-label="Primary">
          {NAV.map((item) => (
            <a key={item.tab} href={`#/${item.tab}`} className={tab === item.tab ? "active" : ""} aria-current={tab === item.tab && screenName === item.tab ? "page" : undefined}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </a>
          ))}
        </nav>
        <div className="toasts" aria-live="polite" aria-atomic="false">
          {toasts.map((item) => (
            <p key={item.id} className={`toast ${item.kind}`} role={item.kind === "error" ? "alert" : undefined}>
              {item.message}
            </p>
          ))}
        </div>
        {celebration && (
          <div className="celebration" key={celebration.key} role="status" aria-live="polite">
            <div className="celebration-card">
              <span className="celebration-mark" aria-hidden="true"><Icon name="check" size={30} /></span>
              <b>Nice work</b>
              <span>{celebration.title}</span>
              {celebration.detail && <small>{celebration.detail}</small>}
            </div>
          </div>
        )}
        {quickAdd && <QuickAddSheet defaults={quickAdd} onClose={() => setQuickAdd(null)} />}
        {taskSheet && (
          <TaskSheet
            key={taskSheet.key}
            taskId={taskSheet.id}
            defaults={taskSheet.defaults}
            initialMode={taskSheet.mode}
            onClose={() => setTaskSheet(null)}
          />
        )}
        {entrySheet && (
          <EntrySheet key={entrySheet.key} entryId={entrySheet.id} initialMode={entrySheet.mode} onClose={() => setEntrySheet(null)} />
        )}
      </div>
    </AppContext.Provider>
  );
}
