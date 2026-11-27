import { Icon, ProgressLine, ScreenHead } from "../../components/ui";
import { useResource } from "../../lib/useResource";
import type { Challenge, Goal, Project, Roadmap, VisionItem } from "../../lib/types";

const Pending = () => <span className="skeleton inline" aria-label="Loading" />;

/** The planning chain at a glance: Vision → Goals → Roadmaps and Projects. */
export function PlanScreen() {
  const vision = useResource<VisionItem[]>("/vision");
  const goals = useResource<Goal[]>("/goals?status=active");
  const projects = useResource<Project[]>("/projects");
  const roadmaps = useResource<Roadmap[]>("/roadmaps");
  const primary = useResource<Challenge | null>("/challenges/primary");

  const statement = vision.data?.find((item) => item.kind === "vision" && item.status === "active");
  const activeProjects = (projects.data ?? []).filter((p) => ["active", "planning", "on_hold"].includes(p.status));
  const activeRoadmaps = (roadmaps.data ?? []).filter((r) => r.status !== "completed");
  const atRisk = (goals.data ?? []).filter((g) => g.progress.overdue || g.progress.at_risk);

  return (
    <section className="screen plan" aria-labelledby="plan-title">
      <ScreenHead eyebrow="Plan" title="From vision to today" lead="Vision gives direction. Goals make it concrete. Roadmaps and projects organise the work that Today and Schedule turn into action." />

      <a className="chain-card vision-chain" href="#/vision">
        <span className="chain-step">
          <Icon name="vision" /> My Vision
        </span>
        <b>{statement ? statement.title : "Write who you are becoming"}</b>
        <small>{vision.data ? `${vision.data.filter((v) => v.status === "active").length} on your vision board` : <Pending />}</small>
      </a>

      <a className="chain-card" href="#/goals">
        <span className="chain-step">
          <Icon name="goal" /> Goals
        </span>
        <b>{goals.data ? `${goals.data.length} active` : <Pending />}</b>
        <small>{atRisk.length ? `${atRisk.length} need attention` : "Milestones, check-ins and evidence"}</small>
        {goals.data?.slice(0, 3).map((goal) => (
          <span key={goal.id} className="chain-row">
            <span>{goal.title}</span>
            <ProgressLine ratio={goal.progress.ratio} label={goal.title} />
          </span>
        ))}
      </a>

      <div className="chain-pair">
        <a className="chain-card" href="#/roadmaps">
          <span className="chain-step">
            <Icon name="roadmaps" /> Roadmaps
          </span>
          <b>{roadmaps.data ? `${activeRoadmaps.length} in progress` : <Pending />}</b>
          <small>Learning paths</small>
        </a>
        <a className="chain-card" href="#/projects">
          <span className="chain-step">
            <Icon name="project" /> Projects
          </span>
          <b>{projects.data ? `${activeProjects.length} open` : <Pending />}</b>
          <small>Separate workspaces</small>
        </a>
      </div>

      <a className="chain-card" href="#/challenges">
        <span className="chain-step">
          <Icon name="challenge" /> Challenges
        </span>
        <b>{primary.data ? primary.data.name : "No primary challenge"}</b>
        <small>
          {primary.data
            ? primary.data.phase === "active"
              ? `Day ${primary.data.current_day} of ${primary.data.total_days}`
              : primary.data.phase
            : "30, 90, 96 days or a year"}
        </small>
      </a>

      <div className="chain-foot">
        <a href="#/tasks" className="chip small">
          <Icon name="tasks" size={16} /> Tasks and backlog
        </a>
        <a href="#/schedule" className="chip small">
          <Icon name="schedule" size={16} /> Schedule
        </a>
        <a href="#/journey" className="chip small">
          <Icon name="journey" size={16} /> My Journey
        </a>
      </div>
    </section>
  );
}
