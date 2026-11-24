import { FormEvent, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { navigate, Route } from "../../app/router";
import { EmptyState, ErrorState, Icon, Loading, Switch } from "../../components/ui";
import { api, patch, post } from "../../lib/api";
import { actualLabel, addDays, deviceTimezone, instantFrom, weekStart } from "../../lib/time";
import type { Challenge, Preferences, Task, User } from "../../lib/types";
import { useInstallPrompt } from "../../lib/pwa";

const SUBPAGES: Record<string, string> = {
  challenges: "Challenges",
  health: "Health log",
  reflect: "Reflection",
  history: "History",
};

export function ProfileScreen({ route }: { route: Route }) {
  const sub = route.path[1];
  if (sub && SUBPAGES[sub]) {
    return (
      <section className="screen profile-sub" aria-labelledby="sub-title">
        <header className="screen-head">
          <button type="button" className="back-link" onClick={() => navigate("#/profile")}>
            <Icon name="chevronLeft" size={18} /> Profile
          </button>
          <h1 id="sub-title">{SUBPAGES[sub]}</h1>
        </header>
        {sub === "challenges" && <Challenges />}
        {sub === "health" && <HealthLog />}
        {sub === "reflect" && <Reflect />}
        {sub === "history" && <History />}
      </section>
    );
  }
  return <ProfileHome />;
}

function ProfileHome() {
  const app = useApp();
  const install = useInstallPrompt();
  const device = deviceTimezone();
  const [busy, setBusy] = useState(false);

  async function savePrefs(changes: Partial<Preferences>) {
    try {
      app.setPrefs(await patch<Preferences>("/preferences", changes));
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not save", "error");
    }
  }

  async function useDeviceZone() {
    setBusy(true);
    try {
      app.setUser(await patch<User>("/me", { timezone: device }));
      app.toast(`Timezone set to ${device}`, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update timezone", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="screen profile" aria-labelledby="profile-title">
      <header className="screen-head">
        <p className="eyebrow">Profile</p>
        <h1 id="profile-title">{app.user.display_name || "Your CharityOS"}</h1>
        <p className="muted">{app.user.email}</p>
      </header>

      <section className="panel">
        <h2 className="panel-title">Timezone</h2>
        <p>
          Days, reminders and history use <b>{app.user.timezone}</b>.
        </p>
        {device && device !== app.user.timezone && (
          <button type="button" className="button secondary small" disabled={busy} onClick={useDeviceZone}>
            Use this device's timezone ({device})
          </button>
        )}
      </section>

      <nav className="menu" aria-label="Profile sections">
        {Object.entries(SUBPAGES).map(([key, label]) => (
          <a key={key} href={`#/profile/${key}`} className="menu-row">
            <span>{label}</span>
            <Icon name="chevronRight" size={18} />
          </a>
        ))}
      </nav>

      <section className="panel">
        <h2 className="panel-title">Motivation</h2>
        <Switch checked={app.prefs.celebrations_enabled} onChange={(value) => savePrefs({ celebrations_enabled: value })} title="Completion celebrations" hint="A small moment when you finish something." />
        <Switch checked={app.prefs.show_streaks} onChange={(value) => savePrefs({ show_streaks: value })} title="Weekly rhythm streak" hint="Counts weeks with 3+ active days. A missed day never resets it." />
        <label className="field">
          <span>Today opens in</span>
          <select value={app.prefs.default_today_view} onChange={(event) => savePrefs({ default_today_view: event.target.value as Preferences["default_today_view"] })}>
            <option value="agenda">Agenda</option>
            <option value="timeline">Timeline</option>
            <option value="day">Day view</option>
          </select>
        </label>
      </section>

      {install.available && (
        <section className="panel">
          <h2 className="panel-title">Install CharityOS</h2>
          <p className="muted">Add it to your home screen for a full-screen app.</p>
          <button type="button" className="button" onClick={install.prompt}>Install app</button>
        </section>
      )}

      <button type="button" className="button secondary block" onClick={app.logout}>
        Log out
      </button>
    </section>
  );
}

function Challenges() {
  const app = useApp();
  const [challenges, setChallenges] = useState<Challenge[] | null>(null);
  const [name, setName] = useState("");
  const [start, setStart] = useState(app.today);
  const [end, setEnd] = useState(addDays(app.today, 95));
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    api<Challenge[]>("/challenges").then(setChallenges).catch((err) => setError(err.message));
  }, [version]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      setVersion((value) => value + 1);
      app.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  if (!challenges) return error ? <ErrorState message={error} /> : <Loading />;
  return (
    <>
      <p className="muted">CharityOS is permanent. Challenges are dated containers inside it.</p>
      <ul className="category-list">
        {challenges.map((challenge) => (
          <li key={challenge.id}>
            <span className="grow">
              <b>{challenge.name}</b>
              <small>
                {challenge.start_date} → {challenge.end_date} · {challenge.phase}
                {challenge.phase === "active" ? ` · day ${challenge.current_day}/${challenge.total_days}` : ""}
              </small>
            </span>
            {challenge.is_primary ? (
              <span className="status-badge status-completed">Primary</span>
            ) : (
              <>
                <button type="button" className="text-button" onClick={() => run(() => post(`/challenges/${challenge.id}/set-primary`))}>Use</button>
                <button type="button" className="text-button" onClick={() => run(() => post(`/challenges/${challenge.id}/archive`))}>Archive</button>
              </>
            )}
          </li>
        ))}
      </ul>
      <form
        className="panel form"
        onSubmit={(event) => {
          event.preventDefault();
          run(() => post("/challenges", { name, start_date: start, end_date: end, status: "active", is_primary: challenges.length === 0 }).then(() => setName("")));
        }}
      >
        <h2 className="panel-title">New challenge</h2>
        <label className="field"><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} required placeholder="Road to 2027" /></label>
        <div className="field-row">
          <label className="field"><span>Start</span><input type="date" value={start} onChange={(event) => setStart(event.target.value)} required /></label>
          <label className="field"><span>End</span><input type="date" value={end} onChange={(event) => setEnd(event.target.value)} required /></label>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button">Create challenge</button>
      </form>
    </>
  );
}

function HealthLog() {
  const app = useApp();
  const tz = app.user.timezone;
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [exercise, setExercise] = useState({ activity: "", start: "07:00", minutes: 30 });
  const [sleep, setSleep] = useState({ started: "22:30", woke: "06:30", quality: 4 });
  const [water, setWater] = useState(2000);
  const [meal, setMeal] = useState({ type: "Breakfast", description: "" });
  const [nutrition, setNutrition] = useState(4);

  async function save(kind: string, action: () => Promise<unknown>) {
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(`${kind} saved to your health history`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  return (
    <>
      <p className="muted">Health history stays separate from productivity. Exercise and sleep activities you complete on your schedule also appear in health insights.</p>
      <form className="panel form" onSubmit={(event) => {
        event.preventDefault();
        const started = instantFrom(app.today, exercise.start, tz);
        const ended = new Date(new Date(started).getTime() + exercise.minutes * 60000).toISOString();
        save("Exercise", () => post("/exercise-logs", { activity: exercise.activity, started_at: started, ended_at: ended }));
      }}>
        <h2 className="panel-title">Exercise</h2>
        <label className="field"><span>Activity</span><input value={exercise.activity} onChange={(event) => setExercise({ ...exercise, activity: event.target.value })} required /></label>
        <div className="field-row">
          <label className="field"><span>Started</span><input type="time" value={exercise.start} onChange={(event) => setExercise({ ...exercise, start: event.target.value })} /></label>
          <label className="field"><span>Minutes</span><input type="number" min={1} value={exercise.minutes} onChange={(event) => setExercise({ ...exercise, minutes: Number(event.target.value) })} /></label>
        </div>
        <button className="button">Save exercise</button>
      </form>
      <form className="panel form" onSubmit={(event) => {
        event.preventDefault();
        const wokeDate = app.today;
        const startDate = sleep.started > sleep.woke ? addDays(app.today, -1) : app.today;
        save("Sleep", () => post("/sleep-logs", { started_at: instantFrom(startDate, sleep.started, tz), woke_at: instantFrom(wokeDate, sleep.woke, tz), timezone_name: tz, quality: sleep.quality }));
      }}>
        <h2 className="panel-title">Last night's sleep</h2>
        <div className="field-row three">
          <label className="field"><span>Slept</span><input type="time" value={sleep.started} onChange={(event) => setSleep({ ...sleep, started: event.target.value })} /></label>
          <label className="field"><span>Woke</span><input type="time" value={sleep.woke} onChange={(event) => setSleep({ ...sleep, woke: event.target.value })} /></label>
          <label className="field"><span>Quality 1–5</span><input type="number" min={1} max={5} value={sleep.quality} onChange={(event) => setSleep({ ...sleep, quality: Number(event.target.value) })} /></label>
        </div>
        <button className="button">Save sleep</button>
      </form>
      <form className="panel form" onSubmit={(event) => {
        event.preventDefault();
        save("Water", () => post("/water", { local_date: app.today, timezone_name: tz, total_ml: water }));
      }}>
        <h2 className="panel-title">Water today</h2>
        <label className="field"><span>Total ml</span><input type="number" min={0} step={250} value={water} onChange={(event) => setWater(Number(event.target.value))} /></label>
        <button className="button">Save water</button>
      </form>
      <form className="panel form" onSubmit={(event) => {
        event.preventDefault();
        save("Meal", () => post("/meal-logs", { local_date: app.today, timezone_name: tz, meal_type: meal.type, description: meal.description }));
      }}>
        <h2 className="panel-title">Meal</h2>
        <label className="field"><span>Meal</span><select value={meal.type} onChange={(event) => setMeal({ ...meal, type: event.target.value })}><option>Breakfast</option><option>Lunch</option><option>Dinner</option><option>Snack</option></select></label>
        <label className="field"><span>Description</span><textarea rows={2} value={meal.description} onChange={(event) => setMeal({ ...meal, description: event.target.value })} required /></label>
        <button className="button">Save meal</button>
      </form>
      <form className="panel form" onSubmit={(event) => {
        event.preventDefault();
        save("Nutrition rating", () => post("/nutrition", { local_date: app.today, timezone_name: tz, rating: nutrition }));
      }}>
        <h2 className="panel-title">Nutrition today</h2>
        <label className="field"><span>Rating 1–5</span><input type="number" min={1} max={5} value={nutrition} onChange={(event) => setNutrition(Number(event.target.value))} /></label>
        <button className="button">Save rating</button>
      </form>
      <div aria-live="polite">
        {message && <p className="success">{message}</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
    </>
  );
}

function Reflect() {
  const app = useApp();
  const [weekly, setWeekly] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const tz = app.user.timezone;
    setError("");
    try {
      if (weekly) {
        const start = weekStart(app.today);
        await post("/weekly-reviews", { week_start_date: start, week_end_date: addDays(start, 6), timezone_name: tz, wins: data.get("a"), lessons: data.get("b"), next_week: data.get("c"), closed_at: new Date().toISOString() });
      } else {
        await post("/daily-reflections", { local_date: app.today, timezone_name: tz, went_well: data.get("a"), learned: data.get("b"), improve: data.get("c"), closed_at: new Date().toISOString() });
      }
      setMessage(weekly ? "Weekly review saved" : "Day closed");
      event.currentTarget?.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  return (
    <>
      <div className="segmented" role="tablist" aria-label="Reflection type">
        <button type="button" role="tab" aria-selected={!weekly} className={!weekly ? "selected" : ""} onClick={() => setWeekly(false)}>Daily</button>
        <button type="button" role="tab" aria-selected={weekly} className={weekly ? "selected" : ""} onClick={() => setWeekly(true)}>Weekly review</button>
      </div>
      <form className="panel form" onSubmit={submit}>
        <label className="field"><span>{weekly ? "Wins" : "What went well?"}</span><textarea name="a" rows={3} required /></label>
        <label className="field"><span>{weekly ? "Lessons" : "What did you learn?"}</span><textarea name="b" rows={3} required /></label>
        <label className="field"><span>{weekly ? "Next week" : "What will you improve?"}</span><textarea name="c" rows={3} required /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button">Save reflection</button>
        {message && <p className="success" role="status">{message}</p>}
      </form>
    </>
  );
}

type HistoryItem = { kind: string; title: string; detail: string };

function History() {
  const [entries, setEntries] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api<Task[]>("/tasks"),
      api<{ title: string; duration_seconds: number | null; outcome: string; status: string }[]>("/sessions"),
      api<{ kind: string; text: string; url: string }[]>("/evidence"),
      api<{ title: string; local_date: string }[]>("/accomplishments"),
      api<{ local_date: string; went_well: string }[]>("/daily-reflections"),
    ])
      .then(([tasks, sessions, evidence, wins, reflections]) =>
        setEntries([
          ...tasks.filter((task) => task.status === "completed").map((task) => ({ kind: "Completed task", title: task.title, detail: "" })),
          ...sessions
            .filter((session) => session.status === "completed")
            .map((session) => ({ kind: "Focus", title: session.title, detail: `${actualLabel(session.duration_seconds ?? 0)}${session.outcome ? ` · ${session.outcome}` : ""}` })),
          ...evidence.map((item) => ({ kind: "Evidence", title: item.text || item.url, detail: item.kind })),
          ...wins.map((win) => ({ kind: "Accomplishment", title: win.title, detail: win.local_date })),
          ...reflections.map((reflection) => ({ kind: "Reflection", title: reflection.went_well, detail: reflection.local_date })),
        ]),
      )
      .catch((err) => setError(err.message));
  }, []);
  if (error) return <ErrorState message={error} />;
  if (!entries) return <Loading />;
  if (!entries.length) return <EmptyState title="Nothing recorded yet" body="Completed tasks, focus, evidence and reflections will appear here." />;
  return (
    <ul className="history-list">
      {entries.map((entry, index) => (
        <li key={`${entry.kind}-${index}`}>
          <small>{entry.kind}</small>
          <b>{entry.title || "Untitled entry"}</b>
          {entry.detail && <span className="muted">{entry.detail}</span>}
        </li>
      ))}
    </ul>
  );
}
