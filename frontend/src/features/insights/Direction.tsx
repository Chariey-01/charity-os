import { EmptyState, ErrorState, Loading, ProgressLine } from "../../components/ui";
import { useResource } from "../../lib/useResource";

type DirectionData = {
  goals: { id: string; title: string; status: string; ratio: number | null; basis: string; overdue: boolean; at_risk: boolean; days_left: number | null; activity_30d: number }[];
  roadmaps: { id: string; title: string; status: string; done: number; total: number; ratio: number | null; completed_30d: number }[];
  projects: { id: string; name: string; status: string; open: number; done: number; done_30d: number; overdue: number }[];
  postponed: { id: string; title: string; times: number; status: string }[];
};

/** Is the long-term work moving? Goals, roadmaps, projects, and what keeps slipping. */
export function Direction() {
  const { data, error, reload } = useResource<DirectionData>("/insights/direction");
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading direction" />;
  const empty = !data.goals.length && !data.roadmaps.length && !data.projects.length;
  if (empty)
    return <EmptyState icon="plan" title="Nothing to measure yet" body="Create a goal, roadmap or project under Plan. This view then shows which ones are moving and which have gone quiet." />;
  const quiet = data.goals.filter((goal) => goal.status === "active" && goal.activity_30d === 0);
  return (
    <div className="insights-body">
      <section className="panel" aria-labelledby="dir-goals">
        <h2 id="dir-goals" className="panel-title">Goals</h2>
        <p className="muted small">Progress comes from your milestones or measurements. "Activity" counts check-ins, milestones and linked tasks finished in the last 30 days.</p>
        <ul className="direction-list">
          {data.goals.map((goal) => (
            <li key={goal.id}>
              <a href={`#/goals/${goal.id}`}>
                <span className="direction-title">
                  {goal.title}
                  {goal.overdue ? <span className="tag danger">Overdue</span> : goal.at_risk ? <span className="tag warn">At risk</span> : null}
                </span>
                <ProgressLine ratio={goal.ratio} label={goal.title} />
                <small>{goal.activity_30d ? `${goal.activity_30d} ${goal.activity_30d === 1 ? "step" : "steps"} forward in 30 days` : "No activity in 30 days"}{goal.status === "paused" ? " · paused" : ""}</small>
              </a>
            </li>
          ))}
        </ul>
        {quiet.length > 0 && <p className="notice">{quiet.length === 1 ? "One active goal has" : `${quiet.length} active goals have`} had no activity for 30 days. Pause, let go, or plan a first step.</p>}
      </section>
      {data.roadmaps.length > 0 && (
        <section className="panel" aria-labelledby="dir-roadmaps">
          <h2 id="dir-roadmaps" className="panel-title">Learning</h2>
          <ul className="direction-list">
            {data.roadmaps.map((roadmap) => (
              <li key={roadmap.id}>
                <a href={`#/roadmaps?open=${roadmap.id}`}>
                  <span className="direction-title">{roadmap.title}{roadmap.status === "paused" && <span className="tag">Paused</span>}</span>
                  <ProgressLine ratio={roadmap.ratio} label={roadmap.title} />
                  <small>{roadmap.done} of {roadmap.total} items · {roadmap.completed_30d} completed in 30 days</small>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
      {data.projects.length > 0 && (
        <section className="panel" aria-labelledby="dir-projects">
          <h2 id="dir-projects" className="panel-title">Projects</h2>
          <ul className="direction-list">
            {data.projects.map((project) => (
              <li key={project.id}>
                <a href={`#/projects/${project.id}`}>
                  <span className="direction-title">{project.name}{project.overdue > 0 && <span className="tag danger">{project.overdue} overdue</span>}</span>
                  <small>{project.open} open · {project.done} done · {project.done_30d} finished in 30 days</small>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="panel" aria-labelledby="dir-postponed">
        <h2 id="dir-postponed" className="panel-title">What keeps slipping</h2>
        <p className="muted small">Tasks whose due date moved later, that were carried over or rescheduled at least twice in 90 days.</p>
        {data.postponed.length === 0 ? (
          <p className="inline-empty">Nothing has slipped repeatedly. 👏</p>
        ) : (
          <ul className="link-list">
            {data.postponed.map((task) => (
              <li key={task.id} className="link-row">
                <span>{task.title}</span>
                <small>moved {task.times}×</small>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
