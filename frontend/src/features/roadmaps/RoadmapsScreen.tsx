import { ReactNode, useEffect, useState } from "react";

import { useApp } from "../../app/context";
import { EmptyState, ErrorState, Icon, Loading } from "../../components/ui";
import { api, newId, patch, post } from "../../lib/api";
import type { Roadmap, RoadmapNode } from "../../lib/types";

type NextAction = { roadmap_id: string; roadmap_title: string; node_id: string; title: string; reason: string };

export function RoadmapsScreen() {
  const app = useApp();
  const [roadmaps, setRoadmaps] = useState<Roadmap[] | null>(null);
  const [actions, setActions] = useState<NextAction[]>([]);
  const [selected, setSelected] = useState<{ roadmap: Roadmap; nodes: RoadmapNode[] } | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let alive = true;
    Promise.all([api<Roadmap[]>("/roadmaps"), api<NextAction[]>("/roadmaps/next-actions")])
      .then(([maps, next]) => {
        if (!alive) return;
        setRoadmaps(maps);
        setActions(next);
      })
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [app.dataVersion]);

  async function open(roadmap: Roadmap) {
    try {
      setSelected(await api<{ roadmap: Roadmap; nodes: RoadmapNode[] }>(`/roadmaps/${roadmap.id}/tree`));
      setMessage("");
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not open roadmap", "error");
    }
  }

  // One request, one server transaction: the task, today's plan item and (for
  // Start focus) the session are all created, or none of them is.
  async function addToToday(node: RoadmapNode, focus = false) {
    try {
      const body: Record<string, unknown> = {};
      if (focus) {
        const area = selected?.roadmap.area ?? app.areas[0]?.id;
        if (!area) throw new Error("Create a category before starting focus.");
        Object.assign(body, { start_focus: true, session_id: newId(), area });
      }
      await post(`/roadmap-nodes/${node.id}/add-to-today`, body);
      setMessage(focus ? "Focus started" : "Added to Today's unscheduled tasks");
      app.refresh();
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not add", "error");
    }
  }

  async function complete(node: RoadmapNode) {
    try {
      await patch(`/roadmap-nodes/${node.id}`, { state: "completed" });
      setMessage("Marked complete");
      if (selected) open(selected.roadmap);
    } catch (err) {
      app.toast(err instanceof Error ? err.message : "Could not update", "error");
    }
  }

  function render(nodes: RoadmapNode[], depth = 0): ReactNode[] {
    return nodes.flatMap((node) => {
      const actionable = node.node_type === "item" && node.state === "planned";
      return [
        <article className={`roadmap-node depth-${Math.min(depth, 3)}`} key={node.id}>
          <div>
            <span className={`node-state ${node.state}`} aria-label={node.state} />
            <b>{node.title}</b>
            {node.description && <p>{node.description.replace("Next action: ", "")}</p>}
            <small>
              {node.node_type} · {node.evidence_count} evidence · {Math.round(node.time_invested_seconds / 60)} min focused
            </small>
          </div>
          {actionable && (
            <div className="item-actions">
              <button type="button" onClick={() => app.openQuickAdd({ title: node.title, roadmap_node: node.id, tracking: "focus" })}>Schedule</button>
              <button type="button" onClick={() => addToToday(node)}>Add to Today</button>
              <button type="button" onClick={() => addToToday(node, true)}>Start focus</button>
              <button type="button" onClick={() => complete(node)}>Done</button>
            </div>
          )}
        </article>,
        ...(node.children ? render(node.children, depth + 1) : []),
      ];
    });
  }

  if (error) return <ErrorState message={error} />;
  if (!roadmaps) return <Loading label="Loading roadmaps" />;

  return (
    <section className="screen roadmaps" aria-labelledby="roadmaps-title">
      <header className="screen-head">
        <p className="eyebrow">Roadmaps</p>
        <h1 id="roadmaps-title">Your long-lived paths.</h1>
        <p className="muted">Challenges have dates. Your roadmaps and evidence continue across them.</p>
      </header>
      {actions.length > 0 && (
        <section className="next-panel" aria-label="Next up">
          <p className="eyebrow">Next up</p>
          {actions.slice(0, 5).map((action) => (
            <button
              type="button"
              key={action.node_id}
              onClick={() => {
                const roadmap = roadmaps.find((item) => item.id === action.roadmap_id);
                if (roadmap) open(roadmap);
              }}
            >
              <span>{action.roadmap_title}</span>
              <b>{action.title}</b>
              <small>{action.reason}</small>
            </button>
          ))}
        </section>
      )}
      {roadmaps.length === 0 && <EmptyState title="No roadmaps yet" body="Seed your personal roadmaps from the command line to start." />}
      <div className="roadmap-list">
        {roadmaps.map((roadmap) => (
          <button
            type="button"
            className={`roadmap-card ${selected?.roadmap.id === roadmap.id ? "selected" : ""}`}
            key={roadmap.id}
            onClick={() => open(roadmap)}
            aria-expanded={selected?.roadmap.id === roadmap.id}
          >
            <div>
              <span className="eyebrow">{roadmap.status}</span>
              <h2>{roadmap.title}</h2>
              <p>{roadmap.description.split("\n\n")[0]?.split("\n")[1]}</p>
            </div>
            <Icon name="chevronRight" />
          </button>
        ))}
      </div>
      {selected && (
        <section className="panel roadmap-detail" aria-label={selected.roadmap.title}>
          <div className="group-head">
            <h2>{selected.roadmap.title}</h2>
            <button type="button" className="text-button" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <div className="guidance">
            {selected.roadmap.description.split("\n\n").map((part) => {
              const [heading, ...body] = part.split("\n");
              return (
                <div key={heading}>
                  <b>{heading}</b>
                  <p>{body.join("\n")}</p>
                </div>
              );
            })}
          </div>
          <h3>Nested work</h3>
          {render(selected.nodes)}
          {message && <p className="success" role="status">{message}</p>}
        </section>
      )}
    </section>
  );
}
