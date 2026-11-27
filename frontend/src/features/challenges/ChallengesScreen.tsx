import { FormEvent, useState } from "react";

import { useApp } from "../../app/context";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { useSubmit } from "../../lib/forms";
import { EmptyState, ErrorState, Icon, Loading, Meter, ScreenHead, Sheet } from "../../components/ui";
import { patch, post } from "../../lib/api";
import { addDays } from "../../lib/time";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { Challenge } from "../../lib/types";

const PRESETS = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 96, label: "96 days" },
  { days: 365, label: "A year" },
  { days: 0, label: "Custom" },
];

const STATUS_LABEL: Record<string, string> = {
  draft: "Not started",
  active: "Active",
  paused: "Paused",
  completed: "Completed",
  cancelled: "Stopped",
};

export function ChallengesScreen() {
  const app = useApp();
  const current = useResource<(Challenge & { description: string })[]>("/challenges");
  const archived = useResource<(Challenge & { description: string })[]>("/challenges?archived=only");
  const [editing, setEditing] = useState<Challenge | "new" | null>(null);
  const [confirm, setConfirm] = useState<{ challenge: Challenge; action: "completed" | "cancelled" | "archive" } | null>(null);

  async function update(challenge: Challenge, body: Record<string, unknown>, message: string) {
    try {
      await patch(`/challenges/${challenge.id}`, body);
      if (body.status === "completed") app.celebrate(challenge.name, "Challenge completed");
      else app.toast(message, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }
  async function act(challenge: Challenge, path: string, message: string) {
    try {
      await post(`/challenges/${challenge.id}/${path}`);
      app.toast(message, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  const list = current.data ?? [];
  const groups = [
    { title: "Now", items: list.filter((c) => ["active", "paused"].includes(c.status) && c.phase !== "upcoming") },
    { title: "Upcoming", items: list.filter((c) => c.status === "draft" || (c.phase === "upcoming" && !["completed", "cancelled"].includes(c.status))) },
    { title: "Finished", items: list.filter((c) => ["completed", "cancelled"].includes(c.status) || (c.phase === "completed" && c.status === "active")) },
  ];

  return (
    <section className="screen" aria-labelledby="challenges-title">
      <ScreenHead
        eyebrow="Plan · Challenges"
        title="Challenges"
        lead="Time-boxed pushes: 30, 90 or 96 days, a year, or your own length. Your history continues across all of them."
        back={{ href: "#/plan", label: "Plan" }}
        action={
          <button type="button" className="button small" onClick={() => setEditing("new")}>
            <Icon name="plus" size={18} /> New
          </button>
        }
      />
      {current.error ? (
        <ErrorState message={current.error} onRetry={current.reload} />
      ) : !current.data ? (
        <Loading label="Loading challenges" />
      ) : list.length === 0 ? (
        <EmptyState icon="challenge" title="No challenges yet" body="Start a 96-day challenge, an annual plan for next year, or any length you choose." action={<button type="button" className="button" onClick={() => setEditing("new")}>Start a challenge</button>} />
      ) : (
        groups
          .filter((group) => group.items.length)
          .map((group) => (
            <section key={group.title} aria-label={group.title}>
              <h2 className="section-title">{group.title}</h2>
              <ul className="card-list">
                {group.items.map((challenge) => (
                  <li key={challenge.id} className="entity-card static">
                    <div className="entity-card-top">
                      <span className="eyebrow">
                        {STATUS_LABEL[challenge.status] ?? challenge.status}
                        {challenge.is_primary && " · Primary"}
                      </span>
                      <span className="tag">{challenge.total_days} days</span>
                    </div>
                    <h2>{challenge.name}</h2>
                    <p className="muted small">
                      {formatDate(challenge.start_date)} – {formatDate(challenge.end_date)}
                      {challenge.phase === "active" && ` · day ${challenge.current_day} of ${challenge.total_days}, ${challenge.days_remaining} left`}
                    </p>
                    {challenge.phase === "active" && <Meter value={challenge.current_day} max={challenge.total_days} label={`${challenge.name}: day ${challenge.current_day} of ${challenge.total_days}`} />}
                    <div className="action-strip">
                      {challenge.status === "draft" && <button type="button" className="button small" onClick={() => update(challenge, { status: "active" }, "Challenge started")}>Start</button>}
                      {challenge.status === "active" && <button type="button" className="button small secondary" onClick={() => update(challenge, { status: "paused" }, "Paused")}>Pause</button>}
                      {challenge.status === "paused" && <button type="button" className="button small" onClick={() => update(challenge, { status: "active" }, "Resumed")}>Resume</button>}
                      {["active", "paused"].includes(challenge.status) && <button type="button" className="button small secondary" onClick={() => setConfirm({ challenge, action: "completed" })}>Complete</button>}
                      {!challenge.is_primary && !["completed", "cancelled"].includes(challenge.status) && <button type="button" className="button small secondary" onClick={() => act(challenge, "set-primary", "Now your primary challenge")}>Make primary</button>}
                      <button type="button" className="button small secondary" onClick={() => setEditing(challenge)}>Edit</button>
                      <button type="button" className="button small secondary" onClick={() => setConfirm({ challenge, action: "archive" })}>Archive</button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
      )}
      {archived.data && archived.data.length > 0 && (
        <details className="collapsible">
          <summary>Archived ({archived.data.length})</summary>
          <ul className="link-list">
            {archived.data.map((challenge) => (
              <li key={challenge.id} className="link-row">
                <span>{challenge.name}</span>
                <button type="button" className="text-button" onClick={() => act(challenge, "restore", "Restored")}>Restore</button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {editing && <ChallengeSheet challenge={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {confirm && (
        <ConfirmSheet
          title={confirm.action === "archive" ? "Archive this challenge?" : "Complete this challenge?"}
          body={
            <p>
              {confirm.action === "archive"
                ? "It leaves your list. Its dates, daily plans and everything done during it stay in your history."
                : "It is recorded in My Journey as a finished chapter."}
            </p>
          }
          confirmLabel={confirm.action === "archive" ? "Archive" : "Complete"}
          onConfirm={() => (confirm.action === "archive" ? act(confirm.challenge, "archive", "Archived") : update(confirm.challenge, { status: confirm.action }, "Completed"))}
          onClose={() => setConfirm(null)}
        />
      )}
    </section>
  );
}

function ChallengeSheet({ challenge, onClose }: { challenge: Challenge | null; onClose: () => void }) {
  const app = useApp();
  const [preset, setPreset] = useState(challenge ? 0 : 96);
  const [draft, setDraft] = useState({
    name: challenge?.name ?? "",
    description: (challenge as Challenge & { description?: string })?.description ?? "",
    start_date: challenge?.start_date ?? app.today,
    end_date: challenge?.end_date ?? addDays(app.today, 95),
  });
  const form = useSubmit();
  function choose(days: number) {
    setPreset(days);
    if (days) setDraft((current) => ({ ...current, end_date: addDays(current.start_date, days - 1) }));
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) {
      form.setFields({ name: "Name the challenge." });
      return;
    }
    if (draft.end_date < draft.start_date) {
      form.setFields({ end_date: "The end date cannot be before the start." });
      return;
    }
    const body = { ...draft, name: draft.name.trim(), ...(challenge ? {} : { status: draft.start_date <= app.today ? "active" : "draft" }) };
    const saved = await form.run((key) => (challenge ? patch(`/challenges/${challenge.id}`, body) : post("/challenges", body, { idempotencyKey: key })), challenge ? "Saved" : "Challenge created");
    if (saved) onClose();
  }
  return (
    <Sheet title={challenge ? "Edit challenge" : "New challenge"} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Name" error={form.fields.name}>
          <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} maxLength={120} placeholder="e.g. Road to 2027" />
        </Field>
        <fieldset className="field">
          <legend>Length</legend>
          <div className="chip-row" role="radiogroup" aria-label="Length">
            {PRESETS.map((option) => (
              <button key={option.label} type="button" role="radio" aria-checked={preset === option.days} className="chip small" onClick={() => choose(option.days)}>
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="field-row">
          <Field label="Starts">
            <input
              type="date"
              value={draft.start_date}
              onChange={(e) => setDraft((current) => ({ ...current, start_date: e.target.value, end_date: preset ? addDays(e.target.value, preset - 1) : current.end_date }))}
            />
          </Field>
          <Field label="Ends" error={form.fields.end_date}>
            <input type="date" value={draft.end_date} onChange={(e) => (setPreset(0), setDraft({ ...draft, end_date: e.target.value }))} />
          </Field>
        </div>
        <Field label="Intention" optional>
          <textarea rows={3} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel={challenge ? "Save" : "Create"} onCancel={onClose} />
      </form>
    </Sheet>
  );
}
