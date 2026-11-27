import { FormEvent, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { EmptyState, ErrorState, Icon, Loading, ScreenHead, Sheet, Switch } from "../../components/ui";
import { api, patch, post } from "../../lib/api";
import { useSubmit } from "../../lib/forms";
import { PushConfig, PushState, disablePush, enablePush, loadPushConfig, pushState } from "../../lib/push";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";

type Reminder = {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string;
  target_id: string | null;
  repeat: "once" | "daily" | "weekly";
  local_date: string | null;
  local_time: string;
  weekdays: number[];
  timezone_name: string;
  enabled: boolean;
  next_fire_at: string | null;
  last_fired_at: string | null;
  archived_at: string | null;
};
type Device = { id: string; device_label: string; created_at: string; last_success_at: string | null; active: boolean };
type Delivery = { id: string; title: string; due_at: string; status: string; devices: number };

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DELIVERY_LABEL: Record<string, string> = { sent: "Delivered to the push service", no_device: "No device subscribed", failed: "Could not send", skipped: "Skipped: too late" };

function when(reminder: Reminder) {
  const time = reminder.local_time.slice(0, 5);
  if (reminder.repeat === "daily") return `Every day at ${time}`;
  if (reminder.repeat === "weekly") return `${reminder.weekdays.map((day) => DAYS[day - 1]).join(", ")} at ${time}`;
  return `${reminder.local_date ? formatDate(reminder.local_date) : ""} at ${time}`;
}

function nextLabel(iso: string | null, timeZone: string) {
  if (!iso) return "Not scheduled";
  return `Next: ${new Intl.DateTimeFormat(undefined, { timeZone, weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso))}`;
}

export function RemindersScreen({ route }: { route: Route }) {
  const app = useApp();
  const reminders = useResource<Reminder[]>("/reminders");
  const [editing, setEditing] = useState<Reminder | "new" | null>(() => (route.params.get("new") === "1" ? "new" : null));
  const [archive, setArchive] = useState<Reminder | null>(null);
  const prefill = {
    title: route.params.get("title") ?? "",
    link: route.params.get("link") ?? "",
    kind: route.params.get("kind") ?? "custom",
    target_id: route.params.get("target") ?? null,
  };

  async function toggle(reminder: Reminder, enabled: boolean) {
    try {
      await patch(`/reminders/${reminder.id}`, { enabled, ...(enabled && reminder.repeat === "once" && reminder.local_date && reminder.local_date < app.today ? { local_date: app.today } : {}) });
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  return (
    <section className="screen" aria-labelledby="reminders-title">
      <ScreenHead
        eyebrow="Me · Reminders"
        title="Reminders"
        lead="Sent by the server, so they reach your phone even when CharityOS is closed."
        back={{ href: "#/me", label: "Me" }}
        action={
          <button type="button" className="button small" onClick={() => setEditing("new")}>
            <Icon name="plus" size={18} /> New
          </button>
        }
      />
      <NotificationsPanel />
      <section aria-labelledby="list-title">
        <h2 id="list-title" className="section-title">Your reminders</h2>
        {reminders.error ? (
          <ErrorState message={reminders.error} onRetry={reminders.reload} />
        ) : !reminders.data ? (
          <Loading />
        ) : reminders.data.length === 0 ? (
          <EmptyState icon="bell" title="No reminders yet" body="Remind yourself to study, review the week, or check on a goal. Activities you schedule can also remind you before they start (Settings → Reminders)." />
        ) : (
          <ul className="card-list">
            {reminders.data.map((reminder) => (
              <li key={reminder.id} className="entity-card static reminder-card">
                <div className="entity-card-top">
                  <span className="eyebrow">{when(reminder)}</span>
                  <span className="tag">{reminder.enabled ? nextLabel(reminder.next_fire_at, reminder.timezone_name) : "Off"}</span>
                </div>
                <h2>{reminder.title}</h2>
                {reminder.body && <p className="muted">{reminder.body}</p>}
                <Switch checked={reminder.enabled} onChange={(value) => toggle(reminder, value)} title={reminder.enabled ? "On" : "Off"} />
                <div className="action-strip">
                  {reminder.link && <a className="button small secondary" href={reminder.link}>Open</a>}
                  <button type="button" className="button small secondary" onClick={() => setEditing(reminder)}>Edit</button>
                  <button type="button" className="button small secondary" onClick={() => setArchive(reminder)}>Archive</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <CalendarPanel />
      <Deliveries />
      {editing && <ReminderSheet reminder={editing === "new" ? null : editing} prefill={prefill} onClose={() => (setEditing(null), route.params.get("new") && app.navigate("#/reminders"))} />}
      {archive && (
        <ConfirmSheet
          title="Archive this reminder?"
          body={<p>It stops and leaves the list. You can restore it later.</p>}
          confirmLabel="Archive"
          onConfirm={() => post(`/reminders/${archive.id}/archive`).then(() => (app.toast("Reminder archived", "success"), app.refresh()))}
          onClose={() => setArchive(null)}
        />
      )}
    </section>
  );
}

function NotificationsPanel() {
  const app = useApp();
  const [config, setConfig] = useState<PushConfig | null>(null);
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const devices = useResource<Device[]>("/push/subscriptions");

  useEffect(() => {
    loadPushConfig().then(setConfig).catch(() => setConfig({ configured: false, public_key: null }));
    pushState().then(setState).catch(() => setState("unsupported"));
  }, [app.dataVersion]);

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    try {
      await action();
      app.toast(message, "success");
      setState(await pushState());
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Something went wrong", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="notify-title">
      <h2 id="notify-title" className="panel-title">
        <Icon name="bell" size={20} /> Phone notifications
      </h2>
      {config && !config.configured ? (
        <p className="notice">Notifications are not switched on for this server yet. Reminders are saved and will be sent once the server is configured.</p>
      ) : state === "unsupported" ? (
        <p className="notice">This browser cannot receive notifications. On Android, install CharityOS from Chrome (menu → Install app) and open it from the home screen.</p>
      ) : state === "denied" ? (
        <p className="notice">Notifications are blocked for CharityOS. Allow them in your phone's settings (Apps → CharityOS or Chrome → Notifications), then come back.</p>
      ) : state === "on" ? (
        <p className="success">On for this device.</p>
      ) : (
        <p>Turn on notifications on this device to receive reminders.</p>
      )}
      <div className="action-strip">
        {state === "off" && config?.configured && config.public_key && (
          <button type="button" className="button small" disabled={busy || !app.online} onClick={() => run(() => enablePush(config.public_key!), "Notifications on for this device")}>
            Turn on notifications
          </button>
        )}
        {state === "on" && (
          <>
            <button type="button" className="button small" disabled={busy || !app.online} onClick={() => run(() => post("/push/test"), "Test sent. It should arrive within a minute.")}>
              Send a test
            </button>
            <button type="button" className="button small secondary" disabled={busy} onClick={() => run(disablePush, "Notifications off for this device")}>
              Turn off here
            </button>
          </>
        )}
      </div>
      {devices.data && devices.data.length > 0 && (
        <ul className="link-list">
          {devices.data.map((device) => (
            <li key={device.id} className="link-row">
              <span>
                {device.device_label || "Device"}
                {!device.active && " · no longer reachable"}
              </span>
              <button type="button" className="text-button small" onClick={() => run(() => post("/push/unsubscribe", { id: device.id }), "Device removed")}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <details className="collapsible">
        <summary>How reliable are reminders?</summary>
        <p className="muted small">
          CharityOS's server sends each reminder at its time, through your browser's push service. Your phone shows it when it has a connection. Android may delay notifications in battery-saver or Doze mode, and you can mute them in system settings. A
          notification is not an alarm clock: for something you must not miss, also set an alarm in your phone's Clock app.
        </p>
      </details>
    </section>
  );
}

function CalendarPanel() {
  const app = useApp();
  const feed = useResource<{ active: boolean }>("/calendar/feed");
  const [url, setUrl] = useState("");
  const [confirm, setConfirm] = useState<"rotate" | "revoke" | null>(null);

  async function issue() {
    try {
      const result = await post<{ path: string }>("/calendar/feed");
      setUrl(`${window.location.origin}${result.path}`);
      feed.reload();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not create the link", "error");
    }
  }
  async function revoke() {
    await api("/calendar/feed", { method: "DELETE" });
    setUrl("");
    feed.reload();
    app.toast("Calendar link turned off", "success");
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      app.toast("Link copied", "success");
    } catch {
      app.toast("Select the link and copy it", "info");
    }
  }

  return (
    <section className="panel" aria-labelledby="calendar-title">
      <h2 id="calendar-title" className="panel-title">
        <Icon name="schedule" size={20} /> See your plan in Google Calendar
      </h2>
      <p className="muted small">A private, read-only calendar of your scheduled activities, due dates, milestones and goal targets. No Google permission is needed: your calendar app fetches the link itself, about every few hours.</p>
      {url ? (
        <>
          <label className="field">
            <span>Your private calendar link</span>
            <input readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
          </label>
          <div className="action-strip">
            <button type="button" className="button small" onClick={copy}>Copy link</button>
          </div>
          <ol className="steps small">
            <li>On a computer, open Google Calendar → Other calendars → + → From URL.</li>
            <li>Paste the link and choose Add calendar. It then appears on your Android phone too.</li>
            <li>Keep the link private. Anyone with it can read the titles in your plan.</li>
          </ol>
        </>
      ) : feed.data?.active ? (
        <p className="small">A calendar link is active. For safety it is shown only once; make a new one if you need it again (the old one stops working).</p>
      ) : null}
      <div className="action-strip">
        {!url && (
          <button type="button" className="button small secondary" onClick={() => (feed.data?.active ? setConfirm("rotate") : issue())}>
            {feed.data?.active ? "Make a new link" : "Create calendar link"}
          </button>
        )}
        {feed.data?.active && (
          <button type="button" className="button small secondary" onClick={() => setConfirm("revoke")}>
            Turn off link
          </button>
        )}
      </div>
      {confirm && (
        <ConfirmSheet
          title={confirm === "rotate" ? "Make a new calendar link?" : "Turn off the calendar link?"}
          body={<p>{confirm === "rotate" ? "The current link stops working. Calendars subscribed to it need the new one." : "Calendars subscribed to it stop updating."}</p>}
          confirmLabel={confirm === "rotate" ? "Make new link" : "Turn off"}
          onConfirm={confirm === "rotate" ? issue : revoke}
          onClose={() => setConfirm(null)}
        />
      )}
    </section>
  );
}

function Deliveries() {
  const { data } = useResource<Delivery[]>("/reminders/deliveries");
  if (!data?.length) return null;
  return (
    <details className="collapsible">
      <summary>Recently sent ({data.length})</summary>
      <ul className="history-list">
        {data.map((row) => (
          <li key={row.id}>
            <b>{row.title}</b>
            <span>
              {new Date(row.due_at).toLocaleString()} · {DELIVERY_LABEL[row.status] ?? row.status}
              {row.status === "sent" && row.devices > 1 && ` (${row.devices} devices)`}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function ReminderSheet({ reminder, prefill, onClose }: { reminder: Reminder | null; prefill: { title: string; link: string; kind: string; target_id: string | null }; onClose: () => void }) {
  const app = useApp();
  const [draft, setDraft] = useState({
    title: reminder?.title ?? prefill.title,
    body: reminder?.body ?? "",
    repeat: reminder?.repeat ?? ("once" as Reminder["repeat"]),
    local_date: reminder?.local_date ?? app.today,
    local_time: (reminder?.local_time ?? "08:00").slice(0, 5),
    weekdays: reminder?.weekdays ?? [1, 2, 3, 4, 5],
    link: reminder?.link ?? prefill.link,
  });
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      form.setFields({ title: "What should the reminder say?" });
      return;
    }
    if (draft.repeat === "weekly" && !draft.weekdays.length) {
      form.setFields({ weekdays: "Choose at least one day." });
      return;
    }
    const body = {
      ...draft,
      title: draft.title.trim(),
      local_date: draft.repeat === "once" ? draft.local_date : null,
      weekdays: draft.repeat === "weekly" ? draft.weekdays : [],
      ...(reminder ? {} : { kind: prefill.kind, target_id: prefill.target_id, timezone_name: app.user.timezone }),
    };
    const saved = await form.run((key) => (reminder ? patch(`/reminders/${reminder.id}`, body) : post("/reminders", body, { idempotencyKey: key })), reminder ? "Reminder saved" : "Reminder set");
    if (saved) onClose();
  }
  return (
    <Sheet title={reminder ? "Edit reminder" : "New reminder"} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Remind me to" error={form.fields.title}>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={120} placeholder="e.g. Study transformers for 45 minutes" />
        </Field>
        <Field label="Note" optional>
          <input value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} maxLength={240} />
        </Field>
        <fieldset className="field">
          <legend>Repeat</legend>
          <div className="chip-row" role="radiogroup" aria-label="Repeat">
            {(["once", "daily", "weekly"] as const).map((value) => (
              <button key={value} type="button" role="radio" aria-checked={draft.repeat === value} className="chip small" onClick={() => setDraft({ ...draft, repeat: value })}>
                {value === "once" ? "Once" : value === "daily" ? "Every day" : "Some days"}
              </button>
            ))}
          </div>
        </fieldset>
        {draft.repeat === "weekly" && (
          <fieldset className="field">
            <legend>Days</legend>
            <div className="chip-row">
              {DAYS.map((label, index) => (
                <button
                  key={label}
                  type="button"
                  className="chip small"
                  aria-pressed={draft.weekdays.includes(index + 1)}
                  onClick={() => setDraft({ ...draft, weekdays: draft.weekdays.includes(index + 1) ? draft.weekdays.filter((day) => day !== index + 1) : [...draft.weekdays, index + 1].sort() })}
                >
                  {label}
                </button>
              ))}
            </div>
            {form.fields.weekdays && <small className="form-error">{form.fields.weekdays}</small>}
          </fieldset>
        )}
        <div className="field-row">
          {draft.repeat === "once" && (
            <Field label="Day" error={form.fields.local_date}>
              <input type="date" min={app.today} value={draft.local_date} onChange={(e) => setDraft({ ...draft, local_date: e.target.value })} />
            </Field>
          )}
          <Field label="Time" error={form.fields.local_time}>
            <input type="time" value={draft.local_time} onChange={(e) => setDraft({ ...draft, local_time: e.target.value })} />
          </Field>
        </div>
        <p className="hint">Times are in {app.user.timezone}.</p>
        <FormActions busy={form.busy} error={form.error} submitLabel={reminder ? "Save" : "Set reminder"} onCancel={onClose} />
      </form>
    </Sheet>
  );
}
