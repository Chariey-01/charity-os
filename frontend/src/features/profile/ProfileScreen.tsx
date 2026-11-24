import { FormEvent, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { navigate, Route } from "../../app/router";
import { CategoryDot, EmptyState, ErrorState, Icon, Loading, Switch } from "../../components/ui";
import { api, patch, post } from "../../lib/api";
import { canNotify, notificationPermission, requestNotificationPermission } from "../../lib/reminders";
import { actualLabel, addDays, deviceTimezone, durationLabel, instantFrom, weekStart } from "../../lib/time";
import type { Area, Challenge, Preferences, Task, User } from "../../lib/types";
import { useInstallPrompt } from "../../lib/pwa";

const SUBPAGES: Record<string, string> = {
  categories: "Categories",
  reminders: "Reminders",
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
        {sub === "categories" && <Categories />}
        {sub === "reminders" && <Reminders />}
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

const PALETTE = ["#2F6B55", "#3D5A80", "#8C5E2A", "#A0522D", "#6A4C93", "#C2410C", "#65A30D", "#0E7490", "#4338CA", "#B4536A", "#D97706", "#1D4ED8", "#57534E"];

function slugify(value: string) {
  return value.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "category";
}

function Categories() {
  const app = useApp();
  const [name, setName] = useState("");
  const [color, setColor] = useState(PALETTE[0]);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await app.reloadAreas();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  const archived = app.allAreas.filter((area) => area.archived_at);
  return (
    <>
      {app.areas.length === 0 && (
        <EmptyState
          title="No categories yet"
          body="Categories colour your schedule and group your insights."
          action={<button type="button" className="button" onClick={() => run(() => post("/areas/ensure-defaults"))}>Add default categories</button>}
        />
      )}
      <ul className="category-list">
        {app.areas.map((area) => (
          <li key={area.id}>
            {editing === area.id ? (
              <CategoryEditor area={area} onDone={() => setEditing(null)} run={run} />
            ) : (
              <>
                <CategoryDot color={area.color} />
                <span className="grow">
                  {area.name}
                  {area.health_kind && <small> · feeds {area.health_kind} history</small>}
                </span>
                <button type="button" className="text-button" onClick={() => setEditing(area.id)}>Edit</button>
              </>
            )}
          </li>
        ))}
      </ul>
      <form
        className="panel form"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          const base = slugify(name);
          const taken = new Set(app.allAreas.map((area) => area.slug));
          let slug = base;
          for (let index = 2; taken.has(slug); index += 1) slug = `${base}-${index}`;
          run(() =>
            post("/areas", { name: name.trim(), slug, color, sort_order: app.allAreas.length }).then(() => setName("")),
          );
        }}
      >
        <h2 className="panel-title">New category</h2>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} />
        </label>
        <ColorPicker value={color} onChange={setColor} />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button" disabled={!name.trim() || !app.online}>Add category</button>
      </form>
      <button type="button" className="text-button" onClick={() => run(() => post("/areas/ensure-defaults"))}>
        Restore any missing default categories
      </button>
      {archived.length > 0 && (
        <details className="group collapsible">
          <summary><span className="group-title">Archived</span> <span className="count">{archived.length}</span></summary>
          <ul className="category-list">
            {archived.map((area) => (
              <li key={area.id}>
                <CategoryDot color={area.color} />
                <span className="grow">{area.name}</span>
                <button type="button" className="text-button" onClick={() => run(() => patch(`/areas/${area.id}`, { archived_at: null }))}>Restore</button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function ColorPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <fieldset className="field">
      <legend>Colour</legend>
      <div className="swatches" role="radiogroup" aria-label="Colour">
        {PALETTE.map((swatch) => (
          <button
            key={swatch}
            type="button"
            role="radio"
            aria-checked={value.toUpperCase() === swatch.toUpperCase()}
            aria-label={swatch}
            className="swatch"
            style={{ background: swatch }}
            onClick={() => onChange(swatch)}
          />
        ))}
      </div>
    </fieldset>
  );
}

function CategoryEditor({ area, onDone, run }: { area: Area; onDone: () => void; run: (action: () => Promise<unknown>) => Promise<void> }) {
  const [name, setName] = useState(area.name);
  const [color, setColor] = useState(area.color);
  const [health, setHealth] = useState(area.health_kind);
  return (
    <form
      className="category-editor"
      onSubmit={(event) => {
        event.preventDefault();
        run(() => patch(`/areas/${area.id}`, { name, color, health_kind: health })).then(onDone);
      }}
    >
      <label className="field">
        <span>Name</span>
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <ColorPicker value={color} onChange={setColor} />
      <label className="field">
        <span>Counts towards health history</span>
        <select value={health} onChange={(event) => setHealth(event.target.value as Area["health_kind"])}>
          <option value="">No</option>
          <option value="exercise">Exercise</option>
          <option value="sleep">Sleep</option>
        </select>
      </label>
      <div className="button-row">
        <button type="button" className="button secondary" onClick={() => run(() => patch(`/areas/${area.id}`, { archived_at: new Date().toISOString() })).then(onDone)}>
          Archive
        </button>
        <button className="button">Save</button>
      </div>
    </form>
  );
}

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function Reminders() {
  const app = useApp();
  const [permission, setPermission] = useState(notificationPermission());
  const prefs = app.prefs;

  async function save(changes: Partial<Preferences>) {
    try {
      app.setPrefs(await patch<Preferences>("/preferences", changes));
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not save", "error");
    }
  }

  async function enable(checked: boolean) {
    if (checked && canNotify() && notificationPermission() === "default") {
      setPermission(await requestNotificationPermission());
    }
    save({ reminders_enabled: checked });
  }

  return (
    <>
      <section className="panel notice-panel">
        <h2 className="panel-title"><Icon name="bell" size={18} /> How reminders work</h2>
        <p>
          Reminders fire <b>while CharityOS is open</b>, including when it is installed and running in the background
          for a short time. Phones may pause background apps, so a closed app cannot remind you. Background push
          notifications are not available yet.
        </p>
        <p className="muted">
          System notifications: {permission === "granted" ? "allowed" : permission === "denied" ? "blocked in browser settings — in-app reminders will be used" : permission === "unsupported" ? "not supported on this device — in-app reminders will be used" : "not yet allowed"}
        </p>
      </section>
      <section className="panel form">
        <Switch checked={prefs.reminders_enabled} onChange={(value) => enable(value)} title="Activity reminders" hint="Before activities start." />
        <label className="field">
          <span>Remind me before</span>
          <select value={prefs.reminder_lead_minutes} disabled={!prefs.reminders_enabled} onChange={(event) => save({ reminder_lead_minutes: Number(event.target.value) })}>
            {[0, 5, 10, 15, 30, 60].map((minutes) => (
              <option key={minutes} value={minutes}>{minutes ? `${durationLabel(minutes)} before` : "At start only"}</option>
            ))}
          </select>
        </label>
        <Switch checked={prefs.start_reminders_enabled} disabled={!prefs.reminders_enabled} onChange={(value) => save({ start_reminders_enabled: value })} title="At start time" hint="“It's time for …”" />
        <Switch checked={prefs.daily_planning_reminder_enabled} disabled={!prefs.reminders_enabled} onChange={(value) => save({ daily_planning_reminder_enabled: value })} title="Daily planning" hint="A nudge to plan the day." />
        <label className="field">
          <span>Planning time</span>
          <input type="time" value={prefs.daily_planning_time.slice(0, 5)} disabled={!prefs.daily_planning_reminder_enabled || !prefs.reminders_enabled} onChange={(event) => save({ daily_planning_time: event.target.value })} />
        </label>
        <Switch checked={prefs.weekly_review_reminder_enabled} disabled={!prefs.reminders_enabled} onChange={(value) => save({ weekly_review_reminder_enabled: value })} title="Weekly review" hint="Look back on the week." />
        <div className="field-row">
          <label className="field">
            <span>Review day</span>
            <select value={prefs.weekly_review_weekday} disabled={!prefs.weekly_review_reminder_enabled || !prefs.reminders_enabled} onChange={(event) => save({ weekly_review_weekday: Number(event.target.value) })}>
              {WEEKDAYS.map((day, index) => <option key={day} value={index + 1}>{day}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Time</span>
            <input type="time" value={prefs.weekly_review_time.slice(0, 5)} disabled={!prefs.weekly_review_reminder_enabled || !prefs.reminders_enabled} onChange={(event) => save({ weekly_review_time: event.target.value })} />
          </label>
        </div>
      </section>
    </>
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
