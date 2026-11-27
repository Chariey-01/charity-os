import { FormEvent, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { EmptyState, ErrorState, Icon, Loading, ProgressLine, ScreenHead, Sheet, Switch } from "../../components/ui";
import { patch, post } from "../../lib/api";
import { useSubmit } from "../../lib/forms";
import { formatMinutes } from "../../lib/format";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { Goal, WeeklyReview } from "../../lib/types";
import { PrivacyNotice } from "../account/AccountPages";

type CheerRow = { kind: string; message: string; about: string; created_at: string };
type Sharing = {
  id: string;
  invited_email: string;
  partner: string | null;
  status: "pending" | "active" | "ended";
  paused: boolean;
  share_summary: boolean;
  share_achievements: boolean;
  goals: string[];
  weekly_reviews: string[];
  cheers: CheerRow[];
};
type PartnersPayload = {
  sharing: Sharing[];
  ended: Sharing[];
  shared_with_me: { id: string; owner: string; paused: boolean }[];
  invitations: { id: string; owner: string; created_at: string }[];
};
type PartnerView = {
  id: string;
  owner: string;
  status: string;
  paused: boolean;
  goals?: { id: string; title: string; status: string; target_date: string | null; progress: number | null; basis: string; overdue: boolean; milestones: { title: string; status: string; target_date: string | null }[] }[];
  summary?: { week_start: string; tasks_completed: number; focus_minutes: number; milestones_completed: number };
  achievements?: { kind: string; title: string; date: string }[];
  weekly_reviews?: { week_start_date: string; wins: string; next_week: string }[];
  cheers?: CheerRow[];
};

const CHEER_LABEL: Record<string, string> = { cheer: "👏 Cheer", encourage: "💪 Encouragement", checkin: "❓ Check-in" };

export function PartnersScreen({ route }: { route: Route }) {
  const viewing = route.path[1];
  if (viewing) return <PartnerDetail id={viewing} />;
  return <PartnersHome />;
}

function PartnersHome() {
  const app = useApp();
  const { data, error, reload } = useResource<PartnersPayload>("/partners");
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState<Sharing | null>(null);
  const [ending, setEnding] = useState<{ id: string; label: string } | null>(null);

  async function act(path: string, message: string) {
    try {
      await post(path);
      app.toast(message, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  return (
    <section className="screen" aria-labelledby="partners-title">
      <ScreenHead
        eyebrow="Me · Accountability"
        title="Accountability partners"
        lead="Optional. Share chosen goals and progress with someone you trust. They can encourage you, never edit anything, and see nothing you did not choose."
        back={{ href: "#/me", label: "Me" }}
        action={
          <button type="button" className="button small" onClick={() => setInviting(true)}>
            <Icon name="plus" size={18} /> Invite
          </button>
        }
      />
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          {data.invitations.length > 0 && (
            <section className="panel" aria-labelledby="invites-title">
              <h2 id="invites-title" className="panel-title">Invitations for you</h2>
              {data.invitations.map((invite) => (
                <div key={invite.id} className="invite-row">
                  <p>
                    <b>{invite.owner}</b> wants you as their accountability partner. You will see only what they choose to share, and they will not see
                    anything of yours.
                  </p>
                  <div className="action-strip">
                    <button type="button" className="button small" onClick={() => act(`/partners/${invite.id}/accept`, "Accepted")}>Accept</button>
                    <button type="button" className="button small secondary" onClick={() => act(`/partners/${invite.id}/decline`, "Declined")}>Decline</button>
                  </div>
                </div>
              ))}
            </section>
          )}

          <section aria-labelledby="with-me-title">
            <h2 id="with-me-title" className="section-title">Shared with you</h2>
            {data.shared_with_me.length === 0 ? (
              <p className="inline-empty">Nobody is sharing with you yet.</p>
            ) : (
              <ul className="link-list">
                {data.shared_with_me.map((row) => (
                  <li key={row.id}>
                    <a className="link-row" href={`#/partners/${row.id}`}>
                      <Icon name="people" size={18} /> <span>{row.owner}</span> <small>{row.paused ? "Paused" : "Open"}</small>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="sharing-title">
            <h2 id="sharing-title" className="section-title">You share with</h2>
            {data.sharing.length === 0 ? (
              <EmptyState icon="people" title="You are not sharing with anyone" body="CharityOS works fully on your own. Invite a partner only if accountability would help you." />
            ) : (
              <ul className="card-list">
                {data.sharing.map((row) => (
                  <li key={row.id} className="entity-card static">
                    <div className="entity-card-top">
                      <span className="eyebrow">{row.status === "pending" ? "Invited · waiting" : row.paused ? "Paused" : "Sharing"}</span>
                    </div>
                    <h2>{row.partner ?? row.invited_email}</h2>
                    <p className="entity-meta">
                      <span>{row.goals.length} goal{row.goals.length === 1 ? "" : "s"}</span>
                      {row.share_summary && <span>weekly summary</span>}
                      {row.share_achievements && <span>achievements</span>}
                      {row.weekly_reviews.length > 0 && <span>{row.weekly_reviews.length} reviews</span>}
                    </p>
                    {row.status === "pending" && (
                      <p className="hint">
                        They will see the invitation under Me → Accountability when they sign in with {row.invited_email}. No account yet? They need a beta invite
                        first.
                      </p>
                    )}
                    {row.cheers.length > 0 && (
                      <ul className="cheer-list">
                        {row.cheers.slice(0, 3).map((cheer, index) => (
                          <li key={index}>
                            <b>{CHEER_LABEL[cheer.kind] ?? cheer.kind}</b> {cheer.message} <small>{formatDate(cheer.created_at.slice(0, 10))}</small>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="action-strip">
                      <button type="button" className="button small" onClick={() => setEditing(row)}>Choose what to share</button>
                      {row.status === "active" && (
                        <button type="button" className="button small secondary" onClick={() => patch(`/partners/${row.id}`, { paused: !row.paused }).then(() => (app.toast(row.paused ? "Sharing resumed" : "Sharing paused", "success"), app.refresh()))}>
                          {row.paused ? "Resume sharing" : "Pause sharing"}
                        </button>
                      )}
                      <button type="button" className="button small secondary" onClick={() => setEnding({ id: row.id, label: row.partner ?? row.invited_email })}>
                        {row.status === "pending" ? "Cancel invite" : "Stop sharing"}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
      {inviting && <InviteSheet onClose={() => setInviting(false)} />}
      {editing && <ShareSheet sharing={editing} onClose={() => setEditing(null)} />}
      {ending && (
        <ConfirmSheet
          title={`Stop sharing with ${ending.label}?`}
          body={<p>They lose access straight away. Your records are not affected.</p>}
          confirmLabel="Stop sharing"
          onConfirm={() => act(`/partners/${ending.id}/end`, "Sharing stopped")}
          onClose={() => setEnding(null)}
        />
      )}
    </section>
  );
}

function InviteSheet({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [summary, setSummary] = useState(true);
  const [achievements, setAchievements] = useState(false);
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!email.includes("@")) {
      form.setFields({ email: "Enter their email address." });
      return;
    }
    const saved = await form.run(() => post("/partners", { email, share_summary: summary, share_achievements: achievements }), "Invitation sent");
    if (saved) onClose();
  }
  return (
    <Sheet title="Invite an accountability partner" onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Their email" error={form.fields.email} hint="They accept from their own CharityOS account. Nothing is shared until they do.">
          <input type="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Switch checked={summary} onChange={setSummary} title="Weekly summary" hint="Numbers only: tasks done, focus time and milestones this week." />
        <Switch checked={achievements} onChange={setAchievements} title="Completed achievements" hint="Titles of goals, milestones, learning and projects you complete (last 30 days)." />
        <p className="hint">You choose specific goals and weekly reviews after they accept. Notes, reflections, journal entries and everything else stay private.</p>
        <FormActions busy={form.busy} error={form.error} submitLabel="Send invitation" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function ShareSheet({ sharing, onClose }: { sharing: Sharing; onClose: () => void }) {
  const goals = useResource<Goal[]>("/goals");
  const reviews = useResource<WeeklyReview[]>("/weekly-reviews");
  const [chosen, setChosen] = useState(new Set(sharing.goals));
  const [chosenReviews, setChosenReviews] = useState(new Set(sharing.weekly_reviews));
  const [summary, setSummary] = useState(sharing.share_summary);
  const [achievements, setAchievements] = useState(sharing.share_achievements);
  const form = useSubmit();
  const toggle = (set: Set<string>, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  };
  async function submit(event: FormEvent) {
    event.preventDefault();
    const saved = await form.run(
      () => patch(`/partners/${sharing.id}`, { goals: [...chosen], weekly_reviews: [...chosenReviews], share_summary: summary, share_achievements: achievements }),
      "Sharing updated",
    );
    if (saved) onClose();
  }
  return (
    <Sheet title={`Share with ${sharing.partner ?? sharing.invited_email}`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <Switch checked={summary} onChange={setSummary} title="Weekly summary" hint="Numbers only." />
        <Switch checked={achievements} onChange={setAchievements} title="Completed achievements" hint="Titles only, last 30 days." />
        <fieldset className="field">
          <legend>Goals (title, progress, milestones; never your notes or why)</legend>
          {(goals.data ?? []).length === 0 && <p className="inline-empty">No active goals.</p>}
          {(goals.data ?? []).map((goal) => (
            <label key={goal.id} className="check-field">
              <input type="checkbox" checked={chosen.has(goal.id)} onChange={() => setChosen(toggle(chosen, goal.id))} />
              <span>{goal.title}</span>
            </label>
          ))}
        </fieldset>
        <fieldset className="field">
          <legend>Weekly reviews (wins and next week only; never your lessons)</legend>
          {(reviews.data ?? []).length === 0 && <p className="inline-empty">No weekly reviews yet.</p>}
          {(reviews.data ?? []).slice(0, 8).map((review) => (
            <label key={review.id} className="check-field">
              <input type="checkbox" checked={chosenReviews.has(review.id)} onChange={() => setChosenReviews(toggle(chosenReviews, review.id))} />
              <span>Week of {formatDate(review.week_start_date)}</span>
            </label>
          ))}
        </fieldset>
        <FormActions busy={form.busy} error={form.error} submitLabel="Save" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function PartnerDetail({ id }: { id: string }) {
  const app = useApp();
  const { data, error, reload } = useResource<PartnerView>(`/partners/${id}/view`);
  const [cheer, setCheer] = useState<string | null>(null);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  return (
    <section className="screen" aria-labelledby="partner-title">
      <ScreenHead eyebrow="Shared with you · read only" title={data.owner} back={{ href: "#/partners", label: "Accountability" }} />
      {data.paused ? (
        <EmptyState icon="people" title="Sharing is paused" body={`${data.owner} has paused sharing for now.`} />
      ) : (
        <>
          {data.summary && (
            <section className="journey-summary" aria-label="This week">
              <div className="stat"><b>{data.summary.tasks_completed}</b><span>tasks done this week</span></div>
              <div className="stat"><b>{formatMinutes(data.summary.focus_minutes)}</b><span>focused</span></div>
              <div className="stat"><b>{data.summary.milestones_completed}</b><span>milestones</span></div>
            </section>
          )}
          {(data.goals ?? []).map((goal) => (
            <article key={goal.id} className="panel">
              <div className="group-head">
                <h2>{goal.title}</h2>
                {goal.overdue && <span className="tag danger">Overdue</span>}
              </div>
              <ProgressLine ratio={goal.progress} label={goal.title} />
              {goal.target_date && <p className="muted small">Target {formatDate(goal.target_date)}</p>}
              <ul className="milestone-mini">
                {goal.milestones.map((m, index) => (
                  <li key={index} className={m.status === "done" ? "done" : ""}>{m.title}</li>
                ))}
              </ul>
              <button type="button" className="button small secondary" onClick={() => setCheer(`goal:${goal.id}`)}>Encourage</button>
            </article>
          ))}
          {(data.achievements ?? []).length > 0 && (
            <section className="panel">
              <h2>Recent achievements</h2>
              <ul className="history-list">
                {data.achievements!.map((a, index) => (
                  <li key={index}><b>{a.title}</b><span>{a.kind.replace("_", " ")} · {formatDate(a.date)}</span></li>
                ))}
              </ul>
            </section>
          )}
          {(data.weekly_reviews ?? []).map((review) => (
            <section key={review.week_start_date} className="panel">
              <h2>Week of {formatDate(review.week_start_date)}</h2>
              {review.wins && <p className="prewrap"><b>Wins:</b> {review.wins}</p>}
              {review.next_week && <p className="prewrap"><b>Next:</b> {review.next_week}</p>}
            </section>
          ))}
          {!data.goals?.length && !data.summary && !data.achievements?.length && !data.weekly_reviews?.length && (
            <EmptyState icon="people" title="Nothing shared yet" body={`${data.owner} has not chosen anything to share yet.`} />
          )}
          <button type="button" className="button" onClick={() => setCheer("summary")}>Send encouragement</button>
        </>
      )}
      {cheer && <CheerSheet partnershipId={id} about={cheer} onClose={() => setCheer(null)} onSent={() => app.toast("Sent", "success")} />}
    </section>
  );
}

function CheerSheet({ partnershipId, about, onClose, onSent }: { partnershipId: string; about: string; onClose: () => void; onSent: () => void }) {
  const [kind, setKind] = useState("cheer");
  const [message, setMessage] = useState("");
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const sent = await form.run((key) => post(`/partners/${partnershipId}/cheer`, { kind, message, about }, { idempotencyKey: key }));
    if (sent) {
      onSent();
      onClose();
    }
  }
  return (
    <Sheet title="Encourage" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <div className="chip-row" role="radiogroup" aria-label="Kind">
          {Object.entries(CHEER_LABEL).map(([value, label]) => (
            <button key={value} type="button" role="radio" aria-checked={kind === value} className="chip small" onClick={() => setKind(value)}>{label}</button>
          ))}
        </div>
        <Field label="Message" optional>
          <textarea rows={3} maxLength={280} value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel="Send" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

export function FeedbackScreen() {
  const app = useApp();
  const mine = useResource<{ id: string; kind: string; message: string; status: string; created_at: string }[]>("/feedback");
  const [kind, setKind] = useState("bug");
  const [message, setMessage] = useState("");
  const [device, setDevice] = useState(true);
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (message.trim().length < 5) {
      form.setFields({ message: "Tell us a little more." });
      return;
    }
    const page = document.referrer ? "" : sessionStorage.getItem("charityos:lastScreen") ?? "";
    const saved = await form.run(
      (key) =>
        post("/feedback", { kind, message, page, device: device ? `${navigator.userAgent.slice(0, 250)} · ${window.innerWidth}×${window.innerHeight}` : "" }, { idempotencyKey: key }),
      "Thank you. Feedback sent.",
    );
    if (saved) setMessage("");
  }
  return (
    <section className="screen" aria-labelledby="feedback-title">
      <ScreenHead eyebrow="Me · Beta" title="Send feedback" lead="Something broken, confusing or great? It goes straight to the person running the beta." back={{ href: "#/me", label: "Me" }} />
      <form className="panel form" onSubmit={submit} noValidate>
        <div className="chip-row" role="radiogroup" aria-label="Kind">
          {[["bug", "Something is broken"], ["idea", "Idea"], ["question", "Question"], ["praise", "I like this"]].map(([value, label]) => (
            <button key={value} type="button" role="radio" aria-checked={kind === value} className="chip small" onClick={() => setKind(value)}>{label}</button>
          ))}
        </div>
        <Field label={kind === "bug" ? "What happened, and what did you expect?" : "Your message"} error={form.fields.message}>
          <textarea rows={6} maxLength={4000} value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        <label className="check-field">
          <input type="checkbox" checked={device} onChange={(e) => setDevice(e.target.checked)} />
          <span>Include my browser and screen size (helps fix bugs)</span>
        </label>
        {form.error && <p className="form-error" role="alert">{form.error}</p>}
        <button className="button" disabled={form.busy || !app.online}>{form.busy ? "Sending…" : "Send feedback"}</button>
      </form>
      {mine.data && mine.data.length > 0 && (
        <section aria-labelledby="sent-title">
          <h2 id="sent-title" className="section-title">You sent</h2>
          <ul className="history-list">
            {mine.data.map((row) => (
              <li key={row.id}><b>{row.message.slice(0, 120)}</b><span>{row.kind} · {row.status} · {formatDate(row.created_at.slice(0, 10))}</span></li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

type Invite = { id: string; email: string; note: string; uses: number; max_uses: number; expires_at: string; status: string; code?: string };
type BetaUser = { id: string; email: string; display_name: string; date_joined: string; last_login: string | null };
type FeedbackRow = { id: string; kind: string; message: string; page: string; device: string; status: string; created_at: string; from: string };

export function BetaAdminScreen() {
  const app = useApp();
  const invites = useResource<Invite[]>(app.user.is_beta_admin ? "/beta/invites" : null);
  const users = useResource<BetaUser[]>(app.user.is_beta_admin ? "/beta/users" : null);
  const feedback = useResource<FeedbackRow[]>(app.user.is_beta_admin ? "/beta/feedback" : null);
  const [created, setCreated] = useState<Invite | null>(null);
  const [note, setNote] = useState("");
  const [email, setEmail] = useState("");
  const [link, setLink] = useState<{ email: string; url: string } | null>(null);
  const form = useSubmit();
  if (!app.user.is_beta_admin) return <EmptyState title="Beta admins only" body="This screen is for the person running the beta." />;

  async function create(event: FormEvent) {
    event.preventDefault();
    const invite = await form.run(() => post<Invite>("/beta/invites", { note, email, days: 14, max_uses: 1 }), "Invite created");
    if (invite) {
      setCreated(invite);
      setNote("");
      setEmail("");
    }
  }
  const signupUrl = (code: string) => `${window.location.origin}/#/signup?code=${encodeURIComponent(code)}`;
  async function copy(text: string) {
    await navigator.clipboard.writeText(text).then(() => app.toast("Copied", "success"), () => app.toast("Select it and copy", "info"));
  }

  return (
    <section className="screen" aria-labelledby="beta-title">
      <ScreenHead eyebrow="Me · Beta admin" title="Private beta" lead="Invite friends, help them get back in, and read their feedback. You never see their records here." back={{ href: "#/me", label: "Me" }} />
      <form className="panel form" onSubmit={create} noValidate>
        <h2 className="panel-title">Invite a friend</h2>
        <Field label="Who is it for" optional hint="A note for yourself, e.g. their name.">
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={120} />
        </Field>
        <Field label="Only this email may use it" optional>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        {form.error && <p className="form-error">{form.error}</p>}
        <button className="button" disabled={form.busy}>Create invite</button>
        {created?.code && (
          <div className="notice-panel invite-created">
            <p><b>Send this link privately. It is shown only once</b> and works once, for 14 days.</p>
            <input readOnly value={signupUrl(created.code)} onFocus={(e) => e.currentTarget.select()} aria-label="Invite link" />
            <button type="button" className="button small" onClick={() => copy(signupUrl(created.code!))}>Copy link</button>
          </div>
        )}
      </form>
      <section className="panel">
        <h2 className="panel-title">Invites</h2>
        {(invites.data ?? []).length === 0 && <p className="inline-empty">None yet.</p>}
        <ul className="link-list">
          {(invites.data ?? []).map((invite) => (
            <li key={invite.id} className="link-row">
              <span>{invite.note || invite.email || "Invite"}</span>
              <small>{invite.status} · {invite.uses}/{invite.max_uses}</small>
              {invite.status === "open" && (
                <button type="button" className="text-button small" onClick={() => post(`/beta/invites/${invite.id}/revoke`).then(() => invites.reload())}>Revoke</button>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section className="panel">
        <h2 className="panel-title">People</h2>
        <ul className="link-list">
          {(users.data ?? []).map((user) => (
            <li key={user.id} className="link-row">
              <span>{user.display_name || user.email}<br /><small>{user.email} · joined {formatDate(user.date_joined.slice(0, 10))}{user.last_login ? ` · last seen ${formatDate(user.last_login.slice(0, 10))}` : ""}</small></span>
              <button type="button" className="text-button small" onClick={() => post<{ path: string }>(`/beta/users/${user.id}/reset-link`).then((r) => setLink({ email: user.email, url: `${window.location.origin}${r.path}` }))}>Reset link</button>
            </li>
          ))}
        </ul>
        {link && (
          <div className="notice-panel">
            <p>One-time password reset link for {link.email} (valid 1 day). Send it privately.</p>
            <input readOnly value={link.url} onFocus={(e) => e.currentTarget.select()} aria-label="Reset link" />
            <button type="button" className="button small" onClick={() => copy(link.url)}>Copy</button>
          </div>
        )}
      </section>
      <section className="panel">
        <h2 className="panel-title">Feedback</h2>
        {(feedback.data ?? []).length === 0 && <p className="inline-empty">No feedback yet.</p>}
        <ul className="history-list">
          {(feedback.data ?? []).map((row) => (
            <li key={row.id}>
              <b>{row.kind} · {row.from}</b>
              <p className="prewrap">{row.message}</p>
              <span>{formatDate(row.created_at.slice(0, 10))}{row.page && ` · ${row.page}`} · {row.status}</span>
              {row.device && <small>{row.device}</small>}
              {row.status !== "resolved" && (
                <button type="button" className="text-button small" onClick={() => post(`/beta/feedback/${row.id}/status`, { status: "resolved" }).then(() => feedback.reload())}>Mark resolved</button>
              )}
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}

export function AccountScreen() {
  const app = useApp();
  const form = useSubmit();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const ok = await form.run(() => post("/auth/password", { current_password: current, new_password: next }), "Password changed");
    if (ok) {
      setCurrent("");
      setNext("");
    }
  }
  return (
    <section className="screen" aria-labelledby="account-title">
      <ScreenHead eyebrow="Me · Account" title="Account and privacy" back={{ href: "#/me", label: "Me" }} />
      <form className="panel form" onSubmit={submit} noValidate>
        <h2 className="panel-title">Change password</h2>
        <Field label="Current password" error={form.fields.current_password}>
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password" error={form.fields.new_password} hint="At least 10 characters; not a common password.">
          <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        {form.error && !form.fields.current_password && <p className="form-error">{form.error}</p>}
        <button className="button" disabled={form.busy || !current || !next}>Change password</button>
      </form>
      <section className="panel">
        <PrivacyNotice />
      </section>
      <button type="button" className="button secondary" onClick={() => app.logout()}>Sign out</button>
    </section>
  );
}
