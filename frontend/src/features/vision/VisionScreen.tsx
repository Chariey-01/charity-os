import { FormEvent, useMemo, useState } from "react";

import { useApp } from "../../app/context";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { useSubmit } from "../../lib/forms";
import { EmptyState, ErrorState, Icon, Loading, ScreenHead, Sheet } from "../../components/ui";
import { patch, post } from "../../lib/api";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { Goal, Horizon, VisionItem, VisionKind, VisionRevision } from "../../lib/types";
import { GoalCard, GoalSheet } from "../goals/GoalsScreen";

const KIND_LABEL: Record<VisionKind, string> = {
  vision: "Vision",
  aspiration: "Aspiration",
  manifestation: "Manifestation",
  identity: "Who I am becoming",
};

const HORIZON_LABEL: Record<Horizon, string> = {
  short: "This year",
  medium: "1–3 years",
  long: "3–10 years",
  lifetime: "Lifetime",
};

type KindFilter = "all" | VisionKind | "realised" | "archived";

/** A stable, calm gradient per theme so cards without images still differ. */
function themeHue(theme: string) {
  let hash = 0;
  for (const char of theme || "vision") hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return hash;
}

export function VisionScreen() {
  const [filter, setFilter] = useState<KindFilter>("all");
  const [theme, setTheme] = useState("");
  const [editing, setEditing] = useState<VisionItem | "new" | null>(null);
  const [open, setOpen] = useState<VisionItem | null>(null);
  const { data, error, reload } = useResource<VisionItem[]>(filter === "archived" ? "/vision?archived=only" : "/vision");

  const items = useMemo(() => {
    const all = data ?? [];
    return all.filter((item) => {
      if (theme && item.theme !== theme) return false;
      if (filter === "archived") return true;
      if (filter === "realised") return item.status === "realised";
      if (filter === "all") return true;
      return item.kind === filter;
    });
  }, [data, filter, theme]);
  const themes = useMemo(() => Array.from(new Set((data ?? []).map((item) => item.theme).filter(Boolean))).sort(), [data]);
  const statement = (data ?? []).find((item) => item.kind === "vision" && item.status === "active" && !item.archived_at);

  return (
    <section className="screen vision" aria-labelledby="vision-title">
      <ScreenHead
        eyebrow="Plan · My Vision"
        title="Who you are becoming"
        lead="Aspirations are intentions, not achievements. They become real through goals, work and evidence."
        back={{ href: "#/plan", label: "Plan" }}
        action={
          <button type="button" className="button small" onClick={() => setEditing("new")}>
            <Icon name="plus" size={18} /> Add
          </button>
        }
      />
      {statement && filter === "all" && (
        <blockquote className="vision-statement">
          <p>{statement.statement || statement.title}</p>
          <button type="button" className="text-button" onClick={() => setOpen(statement)}>
            Open my vision statement
          </button>
        </blockquote>
      )}
      <div className="chip-scroll" role="tablist" aria-label="Show">
        {(
          [
            ["all", "All"],
            ["vision", "Vision"],
            ["aspiration", "Aspirations"],
            ["manifestation", "Manifestations"],
            ["identity", "Becoming"],
            ["realised", "Realised"],
            ["archived", "Archived"],
          ] as [KindFilter, string][]
        ).map(([value, label]) => (
          <button key={value} type="button" role="tab" aria-selected={filter === value} className="chip small" onClick={() => setFilter(value)}>
            {label}
          </button>
        ))}
      </div>
      {themes.length > 1 && (
        <div className="chip-scroll" aria-label="Themes">
          <button type="button" className="chip small" aria-pressed={!theme} onClick={() => setTheme("")}>
            Every theme
          </button>
          {themes.map((name) => (
            <button key={name} type="button" className="chip small" aria-pressed={theme === name} onClick={() => setTheme(name)}>
              {name}
            </button>
          ))}
        </div>
      )}
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <Loading label="Loading your vision" />
      ) : items.length === 0 ? (
        <EmptyState
          icon="vision"
          title={filter === "all" ? "Start with one sentence" : "Nothing here yet"}
          body={
            filter === "all"
              ? "Write the life you are building, then add the aspirations and the person you are becoming. Connect each one to goals when you are ready."
              : "Items you add or move here appear on this board."
          }
          action={
            filter === "all" ? (
              <button type="button" className="button" onClick={() => setEditing("new")}>
                Write my vision
              </button>
            ) : undefined
          }
        />
      ) : (
        <ul className="vision-board">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={`vision-card status-${item.status}`}
                style={{ ["--hue" as string]: themeHue(item.theme) }}
                onClick={() => setOpen(item)}
              >
                {item.image_url ? <img src={item.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="vision-art" aria-hidden="true" />}
                <span className="vision-card-body">
                  <span className="eyebrow">
                    {KIND_LABEL[item.kind]} · {HORIZON_LABEL[item.horizon]}
                  </span>
                  <b>{item.title}</b>
                  {item.statement && <span className="clamp-2">{item.statement}</span>}
                  <span className="vision-card-foot">
                    {item.theme && <span className="tag">{item.theme}</span>}
                    {item.status === "realised" && <span className="tag success">Realised</span>}
                    {item.status === "released" && <span className="tag">Let go</span>}
                    {item.goals_count > 0 && <span className="tag">{item.goals_count} goal{item.goals_count === 1 ? "" : "s"}</span>}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {editing && <VisionSheet item={editing === "new" ? null : editing} themes={themes} onClose={() => setEditing(null)} />}
      {open && (
        <VisionDetail
          item={(data ?? []).find((value) => value.id === open.id) ?? open}
          onEdit={() => {
            setEditing((data ?? []).find((value) => value.id === open.id) ?? open);
            setOpen(null);
          }}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  );
}

function VisionSheet({ item, themes, onClose }: { item: VisionItem | null; themes: string[]; onClose: () => void }) {
  const [draft, setDraft] = useState({
    kind: item?.kind ?? ("aspiration" as VisionKind),
    title: item?.title ?? "",
    statement: item?.statement ?? "",
    theme: item?.theme ?? "",
    horizon: item?.horizon ?? ("medium" as Horizon),
    success_looks_like: item?.success_looks_like ?? "",
    notes: item?.notes ?? "",
    image_url: item?.image_url ?? "",
    target_year: item?.target_year ? String(item.target_year) : "",
  });
  const form = useSubmit();
  const set = (key: keyof typeof draft, value: string) => setDraft((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      form.setFields({ title: "Give it a short title." });
      return;
    }
    if (draft.image_url && !draft.image_url.startsWith("https://")) {
      form.setFields({ image_url: "Use an https:// image link." });
      return;
    }
    const body = { ...draft, title: draft.title.trim(), target_year: draft.target_year ? Number(draft.target_year) : null };
    const saved = await form.run(
      (key) => (item ? patch(`/vision/${item.id}`, body) : post("/vision", body, { idempotencyKey: key })),
      item ? "Saved. The previous wording is kept in its history." : "Added to your vision",
    );
    if (saved) onClose();
  }

  return (
    <Sheet title={item ? "Revise" : "Add to my vision"} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <fieldset className="field">
          <legend>What is it?</legend>
          <div className="chip-row" role="radiogroup" aria-label="Kind">
            {(Object.keys(KIND_LABEL) as VisionKind[]).map((kind) => (
              <button key={kind} type="button" role="radio" aria-checked={draft.kind === kind} className="chip small" onClick={() => set("kind", kind)}>
                {KIND_LABEL[kind]}
              </button>
            ))}
          </div>
        </fieldset>
        <Field label="Title" error={form.fields.title}>
          <input value={draft.title} onChange={(e) => set("title", e.target.value)} maxLength={160} placeholder="e.g. I build AI products that matter" />
        </Field>
        <Field label={draft.kind === "vision" ? "Your vision, in your words" : "Describe it"} optional>
          <textarea rows={4} value={draft.statement} onChange={(e) => set("statement", e.target.value)} />
        </Field>
        <Field label="What success looks like" optional>
          <textarea rows={2} value={draft.success_looks_like} onChange={(e) => set("success_looks_like", e.target.value)} placeholder="How you will know it has come true" />
        </Field>
        <div className="field-row">
          <Field label="Theme" optional hint="Your own category: Career, Health, Faith…">
            <input value={draft.theme} onChange={(e) => set("theme", e.target.value)} list="vision-themes" maxLength={60} />
            <datalist id="vision-themes">
              {themes.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </Field>
          <Field label="Horizon">
            <select value={draft.horizon} onChange={(e) => set("horizon", e.target.value)}>
              {(Object.keys(HORIZON_LABEL) as Horizon[]).map((horizon) => (
                <option key={horizon} value={horizon}>
                  {HORIZON_LABEL[horizon]}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="field-row">
          <Field label="Target year" optional error={form.fields.target_year}>
            <input type="number" inputMode="numeric" min={1900} max={2200} value={draft.target_year} onChange={(e) => set("target_year", e.target.value)} />
          </Field>
          <Field label="Image link" optional error={form.fields.image_url}>
            <input type="url" inputMode="url" value={draft.image_url} onChange={(e) => set("image_url", e.target.value)} placeholder="https://…" />
          </Field>
        </div>
        <Field label="Notes" optional>
          <textarea rows={2} value={draft.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel={item ? "Save" : "Add"} onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function VisionDetail({ item, onEdit, onClose }: { item: VisionItem; onEdit: () => void; onClose: () => void }) {
  const app = useApp();
  const goals = useResource<Goal[]>(`/goals?vision=${item.id}`);
  const revisions = useResource<VisionRevision[]>(`/vision/${item.id}/revisions`);
  const [sheet, setSheet] = useState<null | "goal" | "realise" | "archive">(null);

  async function act(path: string, body: unknown, message: string) {
    try {
      await post(`/vision/${item.id}/${path}`, body);
      app.toast(message, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  if (sheet === "goal") return <GoalSheet goal={null} defaults={{ vision: item.id, title: "" }} onClose={() => setSheet(null)} />;
  if (sheet === "realise") return <RealiseSheet item={item} onClose={() => setSheet(null)} />;
  if (sheet === "archive")
    return (
      <ConfirmSheet
        title="Archive this from your board?"
        body={<p>It leaves your vision board. Its revisions and linked goals stay, and you can restore it.</p>}
        confirmLabel="Archive"
        onConfirm={() => act("archive", {}, "Archived")}
        onClose={() => setSheet(null)}
      />
    );

  return (
    <Sheet title={KIND_LABEL[item.kind]} onClose={onClose}>
      <div className="vision-detail">
        <h3>{item.title}</h3>
        {item.statement && <p className="prewrap">{item.statement}</p>}
        {item.success_looks_like && (
          <>
            <p className="eyebrow">Success looks like</p>
            <p className="prewrap">{item.success_looks_like}</p>
          </>
        )}
        {item.status === "realised" && (
          <p className="notice success-notice">
            Realised {item.realised_at ? formatDate(item.realised_at.slice(0, 10)) : ""}.
            {item.realised_note && <> {item.realised_note}</>}
            {item.realised_evidence_url && (
              <>
                {" "}
                <a href={item.realised_evidence_url} target="_blank" rel="noreferrer noopener">
                  Evidence
                </a>
              </>
            )}
          </p>
        )}
        {item.notes && <p className="muted prewrap">{item.notes}</p>}
        <p className="eyebrow">Goals that serve this</p>
        {goals.data && goals.data.length > 0 ? (
          <ul className="card-list compact">
            {goals.data.map((goal) => (
              <li key={goal.id} onClick={onClose}>
                <GoalCard goal={goal} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="inline-empty">No goals yet. A goal is how this starts to become real.</p>
        )}
        <div className="action-strip">
          {item.status === "active" && !item.archived_at && (
            <button type="button" className="button small" onClick={() => setSheet("goal")}>
              <Icon name="goal" size={18} /> Create a goal
            </button>
          )}
          <button type="button" className="button small secondary" onClick={onEdit}>
            <Icon name="edit" size={18} /> Revise
          </button>
          {item.status === "active" && (
            <button type="button" className="button small secondary" onClick={() => setSheet("realise")}>
              It came true
            </button>
          )}
          {item.status === "active" && (
            <button type="button" className="button small secondary" onClick={() => act("status", { status: "released" }, "Let go. It stays in your history.")}>
              Let go
            </button>
          )}
          {item.status !== "active" && (
            <button type="button" className="button small secondary" onClick={() => act("status", { status: "active" }, "Back on your board")}>
              Work towards it again
            </button>
          )}
          {item.archived_at ? (
            <button type="button" className="button small secondary" onClick={() => act("restore", {}, "Restored")}>
              Restore
            </button>
          ) : (
            <button type="button" className="button small secondary" onClick={() => setSheet("archive")}>
              <Icon name="archive" size={18} /> Archive
            </button>
          )}
        </div>
        {revisions.data && revisions.data.length > 0 && (
          <details className="collapsible">
            <summary>Earlier wording ({revisions.data.length})</summary>
            <ol className="history-list">
              {revisions.data.map((revision) => (
                <li key={revision.id}>
                  <b>Version {revision.version}</b>
                  <span>{formatDate(revision.created_at.slice(0, 10))}</span>
                  <p>{revision.title}</p>
                  {revision.statement && <p className="muted">{revision.statement}</p>}
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </Sheet>
  );
}

function RealiseSheet({ item, onClose }: { item: VisionItem; onClose: () => void }) {
  const app = useApp();
  const [evidence, setEvidence] = useState("");
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState(false);
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!evidence && !confirm) {
      form.setFields({ confirm: "Add a link as evidence, or tick the box to confirm it yourself." });
      return;
    }
    const done = await form.run(() => post(`/vision/${item.id}/realise`, { evidence_url: evidence, note, confirm }), "Recorded in My Journey");
    if (done) {
      app.celebrate(item.title, "It came true");
      onClose();
    }
  }
  return (
    <Sheet title="It came true" onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <p className="muted">CharityOS never marks an aspiration as achieved by itself. Record the evidence, or confirm it in your own words.</p>
        <Field label="Evidence link" optional error={form.fields.evidence_url}>
          <input type="url" inputMode="url" value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="https://…" />
        </Field>
        <Field label="What happened" optional>
          <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <label className="check-field">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          <span>I confirm this has come true.</span>
        </label>
        {form.fields.confirm && <p className="form-error">{form.fields.confirm}</p>}
        <FormActions busy={form.busy} error={form.error} submitLabel="Record it" onCancel={onClose} />
      </form>
    </Sheet>
  );
}
