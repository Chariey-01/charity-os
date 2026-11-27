import { FormEvent, ReactNode, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import type { Route } from "../../app/router";
import { ConfirmSheet, Field, FormActions } from "../../components/forms";
import { nullable, useSubmit } from "../../lib/forms";
import { EmptyState, ErrorState, Icon, Loading, ProgressLine, ScreenHead, Sheet } from "../../components/ui";
import { newId, patch, post } from "../../lib/api";
import { formatDate } from "../../lib/when";
import { useResource } from "../../lib/useResource";
import type { Goal, Roadmap, RoadmapNode, RoadmapTemplate } from "../../lib/types";

type NextAction = { roadmap_id: string; roadmap_title: string; node_id: string; title: string; reason: string };
type Tree = { roadmap: Roadmap; nodes: RoadmapNode[] };
type Progress = { completed_eligible_items: number; eligible_items: number; skipped_items: number; progress_ratio: number };

const STATUS_LABEL: Record<string, string> = { active: "Active", paused: "Paused", completed: "Completed" };
const RESOURCE_KINDS: [string, string][] = [
  ["course", "Course"],
  ["docs", "Documentation"],
  ["video", "Video"],
  ["article", "Article"],
  ["book", "Book"],
  ["repo", "Repository"],
  ["exercise", "Exercise"],
  ["other", "Other"],
];

/** Old seeded roadmaps keep their guidance in the description as headed blocks. */
function lead(description: string) {
  const first = description.split("\n\n")[0] ?? "";
  const lines = first.split("\n");
  return lines.length > 1 && lines[0] === lines[0].toUpperCase() ? lines.slice(1).join(" ") : first;
}

export function RoadmapsScreen({ route }: { route?: Route }) {
  const app = useApp();
  const { data: roadmaps, error, reload } = useResource<Roadmap[]>("/roadmaps");
  const actions = useResource<NextAction[]>("/roadmaps/next-actions");
  const [selectedId, setSelectedId] = useState<string | null>(route?.params.get("open") ?? null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const open = route?.params.get("open");
    if (open) setSelectedId(open);
  }, [route]);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!roadmaps) return <Loading label="Loading roadmaps" />;
  if (selectedId) return <RoadmapDetail id={selectedId} onBack={() => (setSelectedId(null), app.navigate("#/roadmaps"))} />;

  return (
    <section className="screen roadmaps" aria-labelledby="roadmaps-title">
      <ScreenHead
        eyebrow="Plan · Roadmaps"
        title="Your learning paths"
        lead="Stages, items, resources and evidence. Pause and resume without losing progress; roadmaps continue across challenges."
        back={{ href: "#/plan", label: "Plan" }}
        action={
          <button type="button" className="button small" onClick={() => setCreating(true)}>
            <Icon name="plus" size={18} /> New roadmap
          </button>
        }
      />
      {(actions.data ?? []).length > 0 && (
        <section className="next-panel" aria-label="Next up">
          <p className="eyebrow">Next up</p>
          {(actions.data ?? []).slice(0, 5).map((action) => (
            <button type="button" key={action.node_id} onClick={() => setSelectedId(action.roadmap_id)}>
              <span>{action.roadmap_title}</span>
              <b>{action.title}</b>
              <small>{action.reason}</small>
            </button>
          ))}
        </section>
      )}
      {roadmaps.length === 0 ? (
        <EmptyState
          icon="roadmaps"
          title="No roadmaps yet"
          body="Start from the AI Engineering template or build your own path stage by stage."
          action={
            <button type="button" className="button" onClick={() => setCreating(true)}>
              Create a roadmap
            </button>
          }
        />
      ) : (
        <div className="roadmap-list">
          {roadmaps.map((roadmap) => (
            <button type="button" className="roadmap-card" key={roadmap.id} onClick={() => setSelectedId(roadmap.id)}>
              <div>
                <span className="eyebrow">
                  {STATUS_LABEL[roadmap.status] ?? roadmap.status}
                  {roadmap.target_date && ` · target ${formatDate(roadmap.target_date)}`}
                </span>
                <h2>{roadmap.title}</h2>
                <p>{roadmap.purpose || lead(roadmap.description)}</p>
              </div>
              <Icon name="chevronRight" />
            </button>
          ))}
        </div>
      )}
      <ArchivedRoadmaps />
      {creating && <NewRoadmapSheet onClose={() => setCreating(false)} onCreated={(id) => setSelectedId(id)} />}
    </section>
  );
}

function ArchivedRoadmaps() {
  const app = useApp();
  const { data } = useResource<Roadmap[]>("/roadmaps?archived=only");
  if (!data?.length) return null;
  return (
    <details className="collapsible">
      <summary>Archived ({data.length})</summary>
      <ul className="link-list">
        {data.map((roadmap) => (
          <li key={roadmap.id} className="link-row">
            <span>{roadmap.title}</span>
            <button
              type="button"
              className="text-button"
              onClick={() => post(`/roadmaps/${roadmap.id}/restore`).then(() => (app.toast("Roadmap restored", "success"), app.refresh()), (err) => app.toast(err.message, "error"))}
            >
              Restore
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}

function NewRoadmapSheet({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const app = useApp();
  const templates = useResource<RoadmapTemplate[]>("/roadmap-templates");
  const goals = useResource<Goal[]>("/goals");
  const [mode, setMode] = useState<"template" | "blank">("template");
  const [template, setTemplate] = useState("ai-engineering");
  const [draft, setDraft] = useState({ title: "", purpose: "", goal: "", area: "" });
  const form = useSubmit();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "blank" && !draft.title.trim()) {
      form.setFields({ title: "Name the roadmap." });
      return;
    }
    const saved = await form.run(
      (key) =>
        mode === "template"
          ? post<Roadmap>("/roadmaps/from-template", { template, title: draft.title.trim() || undefined, goal: nullable(draft.goal), area: nullable(draft.area) })
          : post<Roadmap>("/roadmaps", { title: draft.title.trim(), purpose: draft.purpose, goal: nullable(draft.goal), area: nullable(draft.area) }, { idempotencyKey: key }),
      "Roadmap created",
    );
    if (saved) {
      onClose();
      onCreated(saved.id);
    }
  }
  const chosen = templates.data?.find((item) => item.key === template);
  return (
    <Sheet title="New roadmap" onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <div className="chip-row" role="radiogroup" aria-label="Start from">
          <button type="button" role="radio" aria-checked={mode === "template"} className="chip small" onClick={() => setMode("template")}>
            From a template
          </button>
          <button type="button" role="radio" aria-checked={mode === "blank"} className="chip small" onClick={() => setMode("blank")}>
            Blank
          </button>
        </div>
        {mode === "template" && (
          <>
            <Field label="Template">
              <select value={template} onChange={(e) => setTemplate(e.target.value)}>
                {(templates.data ?? []).map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.title}
                  </option>
                ))}
              </select>
            </Field>
            {chosen && (
              <div className="template-preview">
                <p className="muted">{chosen.summary} Every stage is yours to edit, reorder or remove. Nothing is marked complete.</p>
                <ol>
                  {chosen.stages.map((stage) => (
                    <li key={stage}>{stage}</li>
                  ))}
                </ol>
              </div>
            )}
          </>
        )}
        <Field label={mode === "template" ? "Name" : "Name"} optional={mode === "template"} error={form.fields.title}>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={160} placeholder={mode === "template" ? chosen?.title : "e.g. Cloud engineering"} />
        </Field>
        {mode === "blank" && (
          <Field label="Purpose" optional>
            <textarea rows={2} value={draft.purpose} onChange={(e) => setDraft({ ...draft, purpose: e.target.value })} />
          </Field>
        )}
        <div className="field-row">
          <Field label="Serves goal" optional>
            <select value={draft.goal} onChange={(e) => setDraft({ ...draft, goal: e.target.value })}>
              <option value="">None</option>
              {(goals.data ?? []).map((goal) => (
                <option key={goal.id} value={goal.id}>
                  {goal.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Workstream" optional>
            <select value={draft.area} onChange={(e) => setDraft({ ...draft, area: e.target.value })}>
              <option value="">None</option>
              {app.areas.map((area) => (
                <option key={area.id} value={area.id}>
                  {area.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <FormActions busy={form.busy} error={form.error} submitLabel="Create roadmap" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function RoadmapDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const app = useApp();
  const { data, error, reload } = useResource<Tree>(`/roadmaps/${id}/tree`);
  const progress = useResource<Progress>(`/roadmaps/${id}/progress`);
  const [sheet, setSheet] = useState<null | { kind: "edit" } | { kind: "archive" } | { kind: "node"; node: RoadmapNode | null; parent: RoadmapNode | null } | { kind: "resource"; node: RoadmapNode }>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading roadmap" />;
  const { roadmap, nodes } = data;

  async function addToToday(node: RoadmapNode, focus = false) {
    try {
      const body: Record<string, unknown> = {};
      if (focus) {
        const area = roadmap.area ?? app.areas[0]?.id;
        if (!area) throw new Error("Create a category before starting focus.");
        Object.assign(body, { start_focus: true, session_id: newId(), area });
      }
      await post(`/roadmap-nodes/${node.id}/add-to-today`, body);
      app.toast(focus ? "Focus started" : "Added to Today", "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not add", "error");
    }
  }
  async function setState(node: RoadmapNode, state: string) {
    try {
      await patch(`/roadmap-nodes/${node.id}`, { state });
      if (state === "completed") app.toast(`Done: ${node.title}`, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }
  async function setStatus(status: string, message: string) {
    try {
      await patch(`/roadmaps/${roadmap.id}`, { status });
      if (status === "completed") app.celebrate(roadmap.title, "Roadmap completed");
      else app.toast(message, "success");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  function render(list: RoadmapNode[], depth = 0, parent: RoadmapNode | null = null): ReactNode {
    return list.map((node) => {
      const isSection = node.node_type !== "item";
      const expanded = open[node.id] ?? depth > 0;
      const items = node.children?.filter((child) => child.node_type === "item") ?? [];
      const done = items.filter((child) => child.state === "completed").length;
      if (isSection)
        return (
          <section key={node.id} className={`stage depth-${Math.min(depth, 2)}`}>
            <button type="button" className="stage-head" aria-expanded={expanded} onClick={() => setOpen({ ...open, [node.id]: !expanded })}>
              <span>
                <b>{node.title}</b>
                {items.length > 0 && (
                  <small>
                    {done}/{items.length} done{node.time_invested_seconds ? ` · ${Math.round(node.time_invested_seconds / 60)} min` : ""}
                  </small>
                )}
              </span>
              <Icon name={expanded ? "chevronLeft" : "chevronRight"} size={18} />
            </button>
            {expanded && (
              <div className="stage-body">
                {node.description && <p className="muted">{node.description}</p>}
                {node.completion_criteria && (
                  <p className="criteria">
                    <b>Done when:</b> {node.completion_criteria}
                  </p>
                )}
                <Resources node={node} onAdd={() => setSheet({ kind: "resource", node })} />
                {render(node.children ?? [], depth + 1, node)}
                <div className="stage-actions">
                  <button type="button" className="text-button" onClick={() => setSheet({ kind: "node", node: null, parent: node })}>
                    Add item
                  </button>
                  <button type="button" className="text-button" onClick={() => setSheet({ kind: "node", node, parent })}>
                    Edit stage
                  </button>
                </div>
              </div>
            )}
          </section>
        );
      return (
        <article className={`roadmap-node item state-${node.state}`} key={node.id}>
          <button
            type="button"
            className={`check ${node.state === "completed" ? "checked" : ""}`}
            role="checkbox"
            aria-checked={node.state === "completed"}
            aria-label={`${node.state === "completed" ? "Reopen" : "Complete"} ${node.title}`}
            onClick={() => setState(node, node.state === "completed" ? "planned" : "completed")}
          >
            <Icon name="check" size={16} />
          </button>
          <div>
            <b>{node.title}</b>
            {node.description && <p>{node.description.replace("Next action: ", "")}</p>}
            {node.notes && <p className="muted">Notes: {node.notes}</p>}
            <small>
              {node.state === "skipped" ? "Skipped · " : ""}
              {node.evidence_count} evidence · {Math.round(node.time_invested_seconds / 60)} min focused
            </small>
            <Resources node={node} />
            {node.state === "planned" && (
              <div className="item-actions">
                <button type="button" onClick={() => app.openQuickAdd({ title: node.title, roadmap_node: node.id, tracking: "focus" })}>
                  Schedule
                </button>
                <button type="button" onClick={() => addToToday(node)}>
                  Add to Today
                </button>
                <button type="button" onClick={() => addToToday(node, true)}>
                  Start focus
                </button>
              </div>
            )}
            <div className="stage-actions">
              <button type="button" className="text-button small" onClick={() => setSheet({ kind: "resource", node })}>
                Add resource
              </button>
              <button type="button" className="text-button small" onClick={() => setSheet({ kind: "node", node, parent })}>
                Edit
              </button>
            </div>
          </div>
        </article>
      );
    });
  }

  const p = progress.data && typeof progress.data.eligible_items === "number" ? progress.data : null;
  return (
    <section className="screen roadmaps" aria-labelledby="roadmap-title">
      <header className="screen-head">
        <button type="button" className="back-link" onClick={onBack}>
          <Icon name="chevronLeft" size={18} /> Roadmaps
        </button>
        <p className="eyebrow">
          {STATUS_LABEL[roadmap.status] ?? roadmap.status}
          {roadmap.start_date && ` · from ${formatDate(roadmap.start_date)}`}
          {roadmap.target_date && ` · target ${formatDate(roadmap.target_date)}`}
        </p>
        <h1 id="roadmap-title">{roadmap.title}</h1>
        {roadmap.purpose && <p className="lead-quote">{roadmap.purpose}</p>}
      </header>
      <section className="panel" aria-label="Progress">
        <ProgressLine ratio={p && p.eligible_items ? p.progress_ratio : null} label="Roadmap progress" />
        <p className="muted small">{p ? `${p.completed_eligible_items} of ${p.eligible_items} items complete${p.skipped_items ? `, ${p.skipped_items} skipped` : ""}.` : ""}</p>
      </section>
      <div className="action-strip" role="group" aria-label="Roadmap actions">
        <button type="button" className="button small" onClick={() => setSheet({ kind: "node", node: null, parent: null })}>
          <Icon name="plus" size={18} /> Stage
        </button>
        {roadmap.status === "active" && (
          <button type="button" className="button small secondary" onClick={() => setStatus("paused", "Roadmap paused. Your progress is kept.")}>
            Pause
          </button>
        )}
        {roadmap.status === "paused" && (
          <button type="button" className="button small" onClick={() => setStatus("active", "Roadmap resumed")}>
            Resume
          </button>
        )}
        {roadmap.status !== "completed" ? (
          <button type="button" className="button small secondary" onClick={() => setStatus("completed", "Roadmap completed")}>
            Complete
          </button>
        ) : (
          <button type="button" className="button small secondary" onClick={() => setStatus("active", "Roadmap reopened")}>
            Reopen
          </button>
        )}
        <button type="button" className="button small secondary" onClick={() => setSheet({ kind: "edit" })}>
          <Icon name="edit" size={18} /> Edit
        </button>
        <button type="button" className="button small secondary" onClick={() => setSheet({ kind: "archive" })}>
          <Icon name="archive" size={18} /> Archive
        </button>
      </div>
      {roadmap.description && !roadmap.purpose && (
        <details className="collapsible">
          <summary>Guidance</summary>
          <div className="guidance">
            {roadmap.description.split("\n\n").map((part) => {
              const [heading, ...body] = part.split("\n");
              return (
                <div key={heading}>
                  <b>{heading}</b>
                  <p>{body.join("\n")}</p>
                </div>
              );
            })}
          </div>
        </details>
      )}
      {nodes.length === 0 ? <p className="inline-empty">Add the first stage of this roadmap.</p> : <div className="stages">{render(nodes)}</div>}
      {roadmap.notes && (
        <section className="panel">
          <h2>Notes and reflections</h2>
          <p className="prewrap">{roadmap.notes}</p>
        </section>
      )}
      {sheet?.kind === "edit" && <RoadmapEditSheet roadmap={roadmap} onClose={() => setSheet(null)} />}
      {sheet?.kind === "node" && <NodeSheet roadmap={roadmap} node={sheet.node} parent={sheet.parent} siblings={(sheet.parent ? sheet.parent.children : nodes) ?? []} onClose={() => setSheet(null)} />}
      {sheet?.kind === "resource" && <ResourceSheet node={sheet.node} onClose={() => setSheet(null)} />}
      {sheet?.kind === "archive" && (
        <ConfirmSheet
          title="Archive this roadmap?"
          body={<p>It leaves your list. Stages, items, resources, evidence and focus time are kept, and you can restore it.</p>}
          confirmLabel="Archive"
          onConfirm={() => post(`/roadmaps/${roadmap.id}/archive`).then(() => (app.toast("Roadmap archived", "success"), onBack(), app.refresh()))}
          onClose={() => setSheet(null)}
        />
      )}
    </section>
  );
}

function Resources({ node, onAdd }: { node: RoadmapNode; onAdd?: () => void }) {
  if (!node.resources.length && !onAdd) return null;
  return (
    <ul className="resource-list">
      {node.resources.map((resource) => (
        <li key={resource.id}>
          <a href={resource.url} target="_blank" rel="noreferrer noopener">
            <Icon name="link" size={16} /> {resource.label}
          </a>
          {resource.kind && resource.kind !== "other" && <small>{RESOURCE_KINDS.find(([key]) => key === resource.kind)?.[1]}</small>}
        </li>
      ))}
      {onAdd && (
        <li>
          <button type="button" className="text-button" onClick={onAdd}>
            Add resource
          </button>
        </li>
      )}
    </ul>
  );
}

function RoadmapEditSheet({ roadmap, onClose }: { roadmap: Roadmap; onClose: () => void }) {
  const goals = useResource<Goal[]>("/goals");
  const [draft, setDraft] = useState({
    title: roadmap.title,
    purpose: roadmap.purpose ?? "",
    notes: roadmap.notes ?? "",
    start_date: roadmap.start_date ?? "",
    target_date: roadmap.target_date ?? "",
    goal: roadmap.goal ?? "",
  });
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      form.setFields({ title: "Name the roadmap." });
      return;
    }
    const saved = await form.run(
      () => patch(`/roadmaps/${roadmap.id}`, { ...draft, title: draft.title.trim(), start_date: nullable(draft.start_date), target_date: nullable(draft.target_date), goal: nullable(draft.goal) }),
      "Roadmap saved",
    );
    if (saved) onClose();
  }
  return (
    <Sheet title="Edit roadmap" onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Name" error={form.fields.title}>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={160} />
        </Field>
        <Field label="Purpose" optional>
          <textarea rows={2} value={draft.purpose} onChange={(e) => setDraft({ ...draft, purpose: e.target.value })} />
        </Field>
        <div className="field-row">
          <Field label="Start" optional>
            <input type="date" value={draft.start_date} onChange={(e) => setDraft({ ...draft, start_date: e.target.value })} />
          </Field>
          <Field label="Target" optional>
            <input type="date" value={draft.target_date} onChange={(e) => setDraft({ ...draft, target_date: e.target.value })} />
          </Field>
        </div>
        <Field label="Serves goal" optional>
          <select value={draft.goal} onChange={(e) => setDraft({ ...draft, goal: e.target.value })}>
            <option value="">None</option>
            {(goals.data ?? []).map((goal) => (
              <option key={goal.id} value={goal.id}>
                {goal.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Notes and reflections" optional>
          <textarea rows={4} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel="Save" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

function NodeSheet({ roadmap, node, parent, siblings, onClose }: { roadmap: Roadmap; node: RoadmapNode | null; parent: RoadmapNode | null; siblings: RoadmapNode[]; onClose: () => void }) {
  const app = useApp();
  const isStage = node ? node.node_type !== "item" : !parent;
  const [draft, setDraft] = useState({
    title: node?.title ?? "",
    description: node?.description ?? "",
    completion_criteria: node?.completion_criteria ?? "",
    notes: node?.notes ?? "",
  });
  const [confirm, setConfirm] = useState<"archive" | "skip" | null>(null);
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) {
      form.setFields({ title: "Give it a title." });
      return;
    }
    const body = { ...draft, title: draft.title.trim() };
    const saved = await form.run(
      (key) =>
        node
          ? patch(`/roadmap-nodes/${node.id}`, body)
          : post(
              "/roadmap-nodes",
              { ...body, roadmap: roadmap.id, parent: parent?.id ?? null, node_type: isStage ? "section" : "item", position: siblings.length },
              { idempotencyKey: key },
            ),
      node ? "Saved" : isStage ? "Stage added" : "Item added",
    );
    if (saved) onClose();
  }
  async function archiveNode() {
    if (!node) return;
    await post(`/roadmap-nodes/${node.id}/archive`).then(
      () => (app.toast("Archived. Its evidence and focus time are kept.", "success"), app.refresh(), onClose()),
      (err) => app.toast(err.message, "error"),
    );
  }
  async function skip() {
    if (!node) return;
    await patch(`/roadmap-nodes/${node.id}`, { state: "skipped" }).then(
      () => (app.toast("Skipped. It no longer counts towards progress.", "success"), app.refresh(), onClose()),
      (err) => app.toast(err.message, "error"),
    );
  }
  if (confirm === "archive")
    return (
      <ConfirmSheet title="Archive this?" body={<p>It leaves the roadmap. Its evidence, linked tasks and focus time are kept and it can be restored.</p>} confirmLabel="Archive" onConfirm={archiveNode} onClose={() => setConfirm(null)} />
    );
  if (confirm === "skip")
    return <ConfirmSheet title="Skip this item?" body={<p>Skipped items do not count towards progress either way.</p>} confirmLabel="Skip" onConfirm={skip} onClose={() => setConfirm(null)} />;
  return (
    <Sheet title={node ? (isStage ? "Edit stage" : "Edit item") : isStage ? "New stage" : `New item in ${parent?.title}`} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Title" error={form.fields.title}>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={180} placeholder={isStage ? "e.g. Retrieval-Augmented Generation" : "e.g. Build a RAG demo over my notes"} />
        </Field>
        <Field label={isStage ? "Purpose of this stage" : "Description"} optional>
          <textarea rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
        </Field>
        {isStage && (
          <Field label="Done when" optional hint="What you will be able to do or show at the end of this stage">
            <textarea rows={2} value={draft.completion_criteria} onChange={(e) => setDraft({ ...draft, completion_criteria: e.target.value })} />
          </Field>
        )}
        <Field label="Notes" optional>
          <textarea rows={2} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel={node ? "Save" : "Add"} onCancel={onClose} />
        {node && (
          <div className="button-row">
            {!isStage && node.state === "planned" && (
              <button type="button" className="button secondary small" onClick={() => setConfirm("skip")}>
                Skip item
              </button>
            )}
            <button type="button" className="button secondary small" onClick={() => setConfirm("archive")}>
              Archive
            </button>
          </div>
        )}
      </form>
    </Sheet>
  );
}

function ResourceSheet({ node, onClose }: { node: RoadmapNode; onClose: () => void }) {
  const [draft, setDraft] = useState({ label: "", url: "", kind: "course", notes: "" });
  const form = useSubmit();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.label.trim()) {
      form.setFields({ label: "Name the resource." });
      return;
    }
    if (!/^https?:\/\//.test(draft.url)) {
      form.setFields({ url: "Paste the full link, starting with https://" });
      return;
    }
    // Positions are unique per item, archived resources included; a time-based
    // value always sorts after the existing ones.
    const position = Math.floor(Date.now() / 1000) - 1_700_000_000;
    const saved = await form.run((key) => post("/roadmap-resources", { ...draft, label: draft.label.trim(), node: node.id, position }, { idempotencyKey: key }), "Resource added");
    if (saved) onClose();
  }
  return (
    <Sheet title={`Resource for ${node.title}`} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Name" error={form.fields.label}>
          <input value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} maxLength={120} placeholder="e.g. Udemy: LLM Engineering" />
        </Field>
        <Field label="Link" error={form.fields.url}>
          <input type="url" inputMode="url" value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} placeholder="https://…" />
        </Field>
        <Field label="Type">
          <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}>
            {RESOURCE_KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Notes" optional>
          <input value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
        </Field>
        <FormActions busy={form.busy} error={form.error} submitLabel="Add resource" onCancel={onClose} />
      </form>
    </Sheet>
  );
}

