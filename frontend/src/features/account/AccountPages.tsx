import { FormEvent, ReactNode, useState } from "react";

import { Field } from "../../components/forms";
import { api, post } from "../../lib/api";
import { fieldErrors } from "../../lib/forms";
import { deviceTimezone } from "../../lib/time";
import type { User } from "../../lib/types";

/** Pre-sign-in pages: create an account with an invite, reset a password, privacy. */
function AuthCard({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <main className="auth">
      <section className="auth-card">
        <div className="brand-mark" aria-hidden="true">C</div>
        <p className="eyebrow">CharityOS · private beta</p>
        <h1>{title}</h1>
        {lead && <p className="muted">{lead}</p>}
        {children}
      </section>
    </main>
  );
}

export function SignupPage({ code, onSignedUp }: { code: string; onSignedUp: (user: User) => void }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!form.get("consent")) {
      setErrors({ consent: "Please read and accept the privacy notice." });
      return;
    }
    if (form.get("password") !== form.get("confirm")) {
      setErrors({ confirm: "The passwords do not match." });
      return;
    }
    setBusy(true);
    setError("");
    setErrors({});
    try {
      await api("/auth/csrf");
      onSignedUp(
        await post<User>("/auth/signup", {
          invite_code: String(form.get("invite_code") ?? "").trim(),
          email: form.get("email"),
          password: form.get("password"),
          display_name: form.get("display_name"),
          timezone: deviceTimezone() || "UTC",
        }),
      );
      window.location.hash = "#/today";
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(err instanceof Error ? err.message : "Could not create the account");
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthCard title="Create your account" lead="You need an invite code from the person who invited you to the beta.">
      <form onSubmit={submit} className="form" noValidate>
        <Field label="Invite code" error={errors.invite_code}>
          <input name="invite_code" defaultValue={code} required autoComplete="off" />
        </Field>
        <Field label="Your name" optional>
          <input name="display_name" autoComplete="name" maxLength={100} />
        </Field>
        <Field label="Email" error={errors.email}>
          <input name="email" type="email" required autoComplete="email" inputMode="email" />
        </Field>
        <Field label="Password" error={errors.password} hint="At least 10 characters; not a common password.">
          <input name="password" type="password" required autoComplete="new-password" minLength={10} />
        </Field>
        <Field label="Repeat password" error={errors.confirm}>
          <input name="confirm" type="password" required autoComplete="new-password" />
        </Field>
        <label className="check-field">
          <input type="checkbox" name="consent" value="yes" />
          <span>
            I have read the <a href="#/privacy">privacy notice and beta terms</a>.
          </span>
        </label>
        {errors.consent && <p className="form-error">{errors.consent}</p>}
        {error && !Object.keys(errors).length && <p className="form-error" role="alert">{error}</p>}
        <button className="button block" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <a className="text-button" href="#/">I already have an account</a>
      </form>
    </AuthCard>
  );
}

export function ResetPage({ uid, token }: { uid: string; token: string }) {
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("confirm")) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/auth/csrf");
      await post("/auth/password/reset", { uid, token, password: form.get("password") });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password");
    } finally {
      setBusy(false);
    }
  }
  if (done)
    return (
      <AuthCard title="Password changed" lead="Sign in with your new password.">
        <a className="button block" href="#/">Sign in</a>
      </AuthCard>
    );
  return (
    <AuthCard title="Choose a new password">
      <form onSubmit={submit} className="form">
        <label className="field">
          <span>New password</span>
          <input name="password" type="password" required minLength={10} autoComplete="new-password" />
        </label>
        <label className="field">
          <span>Repeat it</span>
          <input name="confirm" type="password" required autoComplete="new-password" />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button block" disabled={busy || !uid || !token}>{busy ? "Saving…" : "Save password"}</button>
      </form>
    </AuthCard>
  );
}

export function PrivacyNotice() {
  return (
    <article className="privacy prose">
      <h2>Privacy notice and beta terms</h2>
      <p>
        <b>Who runs it.</b> CharityOS is a personal project run by its founder for a small, invited private beta. It is not a company product and has no
        advertising.
      </p>
      <p>
        <b>What is stored.</b> Your email, name, password (as a one-way hash), timezone, and everything you enter: vision, goals, tasks, schedule, focus
        sessions, reflections, evidence links, reminders and feedback. Sign-in attempts are logged with a masked email for security.
      </p>
      <p>
        <b>Who can see it.</b> Only you. Other beta users cannot see your records. If you invite an accountability partner, they see only what you choose
        to share, and you can pause or end sharing at any time. The beta admin can see your email, name, sign-up date and the feedback you send, but not
        your records. The admin has database access to operate the service and will not read your records except to fix a problem you report, with your
        permission.
      </p>
      <p>
        <b>Where it lives.</b> The app is served by Cloudflare; the server runs on Vercel and the database on Neon, both in Frankfurt (EU). Push
        notifications pass through your browser's push service (Google, Mozilla or Apple) in encrypted form. A calendar link you create can be read by
        anyone who has it.
      </p>
      <p>
        <b>Deleting your data.</b> Ask the beta admin and your account and all its records will be erased permanently. Backups expire within about 8
        weeks.
      </p>
      <p>
        <b>Beta limitations.</b> This is early software. Expect bugs, changes and occasional downtime. Keep anything critical somewhere else too.
        Notifications can be delayed by your phone and are not alarm clocks. There is no email: if you forget your password, ask the person who
        invited you for a reset link.
      </p>
    </article>
  );
}

export function PrivacyPage() {
  return (
    <AuthCard title="Privacy and beta terms">
      <PrivacyNotice />
      <button type="button" className="button block secondary" onClick={() => window.history.back()}>
        Back
      </button>
    </AuthCard>
  );
}
