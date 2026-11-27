import { Children, FormEvent, ReactElement, ReactNode, cloneElement, isValidElement, useId, useState } from "react";

import { useApp } from "../app/context";
import { Sheet } from "./ui";



/**
 * A labelled control. The hint and the error are linked to the control with
 * aria-describedby, so the control's accessible name stays the label alone.
 */
export function Field({
  label,
  optional,
  error,
  hint,
  children,
}: {
  label: string;
  optional?: boolean;
  error?: string;
  hint?: string;
  children: ReactElement<Record<string, unknown>> | (ReactElement<Record<string, unknown>> | false | null | undefined)[];
}) {
  const id = useId();
  const items = Children.toArray(children).filter(isValidElement) as ReactElement<Record<string, unknown>>[];
  const described = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>
        <span>{label}</span> {optional && <small className="optional">optional</small>}
      </label>
      {items.map((child, index) =>
        index === 0 ? cloneElement(child, { key: "control", id, "aria-describedby": described, "aria-invalid": error ? true : undefined }) : child,
      )}
      {hint && (
        <small className="hint" id={`${id}-hint`}>
          {hint}
        </small>
      )}
      {error && (
        <small className="form-error" id={`${id}-error`}>
          {error}
        </small>
      )}
    </div>
  );
}

export function FormActions({
  busy,
  error,
  submitLabel,
  onCancel,
}: {
  busy: boolean;
  error?: string;
  submitLabel: string;
  onCancel: () => void;
}) {
  const app = useApp();
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="button-row">
        <button type="button" className="button secondary" onClick={onCancel}>
          Cancel
        </button>
        <button className="button" disabled={busy || !app.online}>
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </>
  );
}

/** Confirmation for actions that hide or change history. */
export function ConfirmSheet({
  title,
  body,
  confirmLabel,
  tone = "normal",
  onConfirm,
  onClose,
  children,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  tone?: "normal" | "danger";
  onConfirm: () => Promise<unknown> | void;
  onClose: () => void;
  children?: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await onConfirm();
      onClose();
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet title={title} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <div className="confirm-body">{body}</div>
        {children}
        <div className="button-row">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className={`button ${tone === "danger" ? "danger" : ""}`} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

