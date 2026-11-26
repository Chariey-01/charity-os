import { FormEvent, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { Icon, Sheet } from "../../components/ui";
import { ApiError, newId, post } from "../../lib/api";
import { clock } from "../../lib/time";
import type { Session } from "../../lib/types";

/** Elapsed seconds from the server value, advanced locally only while active. */
function useSessionSeconds(session: Session | null) {
  const [anchor, setAnchor] = useState(() => ({ session, at: Date.now() }));
  if (anchor.session !== session) setAnchor({ session, at: Date.now() });
  const [now, setNow] = useState(() => Date.now());
  const active = session?.status === "active";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  if (!session) return 0;
  return active ? session.elapsed_seconds + Math.max(0, Math.floor((now - anchor.at) / 1000)) : session.elapsed_seconds;
}

export function FocusBar() {
  const app = useApp();
  const session = app.session;
  const seconds = useSessionSeconds(session);
  const [busy, setBusy] = useState(false);
  const [finishing, setFinishing] = useState(false);
  if (!session) return null;
  const linked = session.schedule_entry ?? null;

  async function toggle() {
    if (!session) return;
    setBusy(true);
    try {
      const pausing = session.status === "active";
      if (linked) {
        await post(`/schedule-entries/${linked}/${pausing ? "pause" : "resume"}`, pausing ? { pause_id: newId() } : {});
      } else {
        await post(
          `/sessions/${session.id}/${pausing ? "pause" : "resume"}`,
          pausing ? { id: newId(), expected_version: session.version } : { expected_version: session.version },
        );
      }
      app.refresh();
    } catch (err) {
      app.toast(err instanceof ApiError ? err.message : "Could not update the timer", "error");
      app.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className={`focus-bar ${session.status}`} role="region" aria-label="Focus session">
        <button type="button" className="focus-main" onClick={() => (linked ? app.openEntry(linked) : setFinishing(true))}>
          <span className="live-dot" aria-hidden="true" />
          <span className="focus-text">
            <small>{session.status === "paused" ? "Paused — not counting" : "Focus in progress"}</small>
            <b>{session.title}</b>
          </span>
          <strong data-testid="elapsed-timer">{clock(seconds)}</strong>
        </button>
        <button
          type="button"
          className="round-action light"
          disabled={busy || !app.online}
          onClick={toggle}
          aria-label={session.status === "active" ? "Pause focus" : "Resume focus"}
        >
          <Icon name={session.status === "active" ? "pause" : "play"} size={18} />
        </button>
        <button
          type="button"
          className="round-action accent"
          disabled={!app.online}
          onClick={() => (linked ? app.openEntry(linked, "finish") : setFinishing(true))}
          aria-label="Finish focus"
        >
          <Icon name="check" size={18} />
        </button>
      </div>
      {finishing && !linked && <SessionFinishSheet session={session} seconds={seconds} onClose={() => setFinishing(false)} />}
    </>
  );
}

function SessionFinishSheet({ session, seconds, onClose }: { session: Session; seconds: number; onClose: () => void }) {
  const app = useApp();
  const [outcome, setOutcome] = useState("");
  const [learning, setLearning] = useState("");
  const [evidence, setEvidence] = useState("");
  // One finish action, one key: a resend of this evidence cannot store it twice.
  const [evidenceKey] = useState(newId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function finish(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await post(`/sessions/${session.id}/finish`, { expected_version: session.version, outcome, learning });
      const text = evidence.trim();
      if (text) {
        const isUrl = text.startsWith("https://");
        await post("/evidence", {
          kind: text.startsWith("https://github.com/") ? "github" : isUrl ? "url" : "note",
          text: isUrl ? "" : text,
          url: isUrl ? text : "",
          session: session.id,
        }, { idempotencyKey: evidenceKey });
      }
      app.celebrate(session.title, `${Math.round(seconds / 60)} min of focus`);
      app.refresh();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet title="Finish focus session" onClose={onClose}>
      <form className="finish-form" onSubmit={finish}>
        <p className="muted">
          {session.title} · <b>{clock(seconds)}</b>
        </p>
        <label className="field">
          <span>Outcome</span>
          <textarea rows={3} value={outcome} onChange={(event) => setOutcome(event.target.value)} placeholder="What did I accomplish?" />
        </label>
        <label className="field">
          <span>Learning</span>
          <textarea rows={2} value={learning} onChange={(event) => setLearning(event.target.value)} placeholder="What did I learn?" />
        </label>
        <label className="field">
          <span>Evidence note or HTTPS/GitHub URL</span>
          <input value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="A note or https://…" />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="button-row">
          <button type="button" className="button secondary" onClick={onClose}>Keep going</button>
          <button className="button" disabled={busy || !app.online}>Save and finish</button>
        </div>
      </form>
    </Sheet>
  );
}
