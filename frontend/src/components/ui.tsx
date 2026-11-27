import { ReactNode, useEffect, useId, useRef } from "react";

import type { EntryStatus } from "../lib/types";

const ICONS: Record<string, ReactNode> = {
  today: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  schedule: <><rect x="3" y="4.5" width="18" height="16" rx="3" /><path d="M3 9.5h18M8 2.5v4M16 2.5v4" /></>,
  roadmaps: <><path d="M4 19c4 0 4-6 8-6s4-6 8-6" /><circle cx="4" cy="19" r="2" /><circle cx="20" cy="7" r="2" /></>,
  insights: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
  profile: <><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></>,
  tasks: <><rect x="3.5" y="3.5" width="17" height="17" rx="4" /><path d="M7.5 12l3 3 6-6.5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  play: <path d="M8 5.5v13l10-6.5z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  chevronLeft: <path d="M15 5l-7 7 7 7" />,
  chevronRight: <path d="M9 5l7 7-7 7" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  offline: <><path d="M2 8.5a15 15 0 0 1 20 0M5 12a10 10 0 0 1 14 0M8.5 15.5a5 5 0 0 1 7 0" /><path d="M3 3l18 18" /></>,
  sparkle: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
  bell: <><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" /><path d="M10 20a2 2 0 0 0 4 0" /></>,
  plan: <><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5l-2 5-5 2 2-5z" /></>,
  me: <><path d="M4 19.5V6a2 2 0 0 1 2-2h12v15.5H6a2 2 0 0 0-2 2" /><path d="M8 8h6M8 11.5h4" /></>,
  vision: <><path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z" /><circle cx="12" cy="12" r="3" /></>,
  goal: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.3" /></>,
  project: <><path d="M3 7.5a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></>,
  journey: <><path d="M5 21V4M5 4h11l-2 4 2 4H5" /></>,
  challenge: <><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z" /><path d="M7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3" /></>,
  archive: <><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
  people: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c1-3.5 3.5-5.5 6.5-5.5s5.5 2 6.5 5.5" /><circle cx="17" cy="9" r="2.5" /><path d="M16 14.5c2.5 0 4.5 1.5 5.5 4.5" /></>,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13.5 6.5l4 4" /></>,
  flag: <><path d="M5 21V4M5 4c5-2 9 2 14 0v9c-5 2-9-2-14 0" /></>,
};

export function Icon({ name, size = 22, label }: { name: keyof typeof ICONS | string; size?: number; label?: string }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      {ICONS[name]}
    </svg>
  );
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Bottom sheet on phones, centred dialog on wide screens. */
export function Sheet({
  title,
  onClose,
  children,
  labelledBy,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>("[autofocus], input, select, textarea") ??
      panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    first?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") closeRef.current();
      if (event.key !== "Tab" || !panel.current) return;
      const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!items.length) return;
      const [head, tail] = [items[0], items[items.length - 1]];
      if (event.shiftKey && document.activeElement === head) {
        event.preventDefault();
        tail.focus();
      } else if (!event.shiftKey && document.activeElement === tail) {
        event.preventDefault();
        head.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, []);

  return (
    <div className="sheet-layer">
      <div className="sheet-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={labelledBy ?? titleId} ref={panel}>
        <div className="sheet-grip" aria-hidden="true" />
        <header className="sheet-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </header>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-loading" role="status" aria-live="polite">
      <span className="skeleton wide" />
      <span className="skeleton" />
      <span className="skeleton short" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function EmptyState({ title, body, action, icon = "sparkle" }: { title: string; body?: string; action?: ReactNode; icon?: string }) {
  return (
    <div className="state-empty">
      <div className="state-art" aria-hidden="true"><Icon name={icon} size={26} /></div>
      <h3>{title}</h3>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-error" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="button secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="tablist" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          className={value === option.value ? "selected" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

const STATUS_LABEL: Record<EntryStatus, string> = {
  scheduled: "Scheduled",
  in_progress: "In progress",
  paused: "Paused",
  completed: "Done",
  partially_completed: "Partly done",
  skipped: "Skipped",
  cancelled: "Cancelled",
  rescheduled: "Rescheduled",
};

export function StatusBadge({ status }: { status: EntryStatus }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function CategoryDot({ color, label }: { color: string; label?: string }) {
  return <span className="category-dot" style={{ background: color }} aria-hidden={label ? undefined : true} title={label} />;
}

export function ProgressRing({ value, total, label }: { value: number; total: number; label: string }) {
  const ratio = total ? Math.min(1, value / total) : 0;
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  return (
    <svg className="progress-ring" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label={label}>
      <circle cx="32" cy="32" r={radius} className="ring-track" />
      <circle
        cx="32"
        cy="32"
        r={radius}
        className="ring-fill"
        strokeDasharray={`${circumference * ratio} ${circumference}`}
        transform="rotate(-90 32 32)"
      />
      <text x="32" y="37" textAnchor="middle" className="ring-text">
        {value}/{total}
      </text>
    </svg>
  );
}

export function Meter({ value, max, label, tone = "brand" }: { value: number; max: number; label: string; tone?: "brand" | "warn" }) {
  const ratio = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <div
      className={`meter meter-${tone}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      aria-label={label}
    >
      <i style={{ width: `${ratio * 100}%` }} />
    </div>
  );
}

/** Checkbox switch whose accessible name is the title; the hint is a description. */
export function Switch({
  checked,
  onChange,
  title,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  title: string;
  hint?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <label className="switch">
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        aria-labelledby={`${id}-t`}
        aria-describedby={hint ? `${id}-h` : undefined}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <b id={`${id}-t`}>{title}</b>
        {hint && <small id={`${id}-h`}>{hint}</small>}
      </span>
    </label>
  );
}

export function ScreenHead({ eyebrow, title, lead, action, back }: { eyebrow: string; title: string; lead?: string; action?: ReactNode; back?: { href: string; label: string } }) {
  return (
    <header className="screen-head">
      {back && (
        <a className="back-link" href={back.href}>
          <Icon name="chevronLeft" size={18} /> {back.label}
        </a>
      )}
      <div className="screen-head-row">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
        </div>
        {action}
      </div>
      {lead && <p className="muted">{lead}</p>}
    </header>
  );
}

/** A progress bar that admits when no measure exists instead of showing 0%. */
export function ProgressLine({ ratio, label }: { ratio: number | null; label: string }) {
  if (ratio === null) return <p className="no-measure">No measure yet</p>;
  const percent = Math.round(ratio * 100);
  return (
    <div className="progress-line">
      <Meter value={percent} max={100} label={`${label}: ${percent}%`} />
      <span>{percent}%</span>
    </div>
  );
}
