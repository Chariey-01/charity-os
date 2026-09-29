import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { App, elapsedSeconds } from "./App";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => { vi.restoreAllMocks(); });

test("renders the authenticated dashboard", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/me")) return json({ id:"1", email:"owner@example.com", display_name:"Owner", timezone:"UTC" });
    if (path.endsWith("/sessions/active")) return json(null);
    if (path.endsWith("/tasks")) return json([{id:"t1",title:"Ship the MVP",status:"planned",is_deep_work_default:true}]);
    if (path.endsWith("/areas")) return json([{id:"a1",name:"Engineering",color:"#173f31"}]);
    return json({total_focused_minutes:45,deep_work_minutes:30,planned_completion_rate:.5});
  });
  render(<App/>);
  expect(await screen.findByRole("heading", {name:"Good day."})).toBeInTheDocument();
  expect(screen.getByText("Ship the MVP")).toBeInTheDocument();
  expect(screen.getByText("45", {exact:false})).toBeInTheDocument();
});

test("reconstructs elapsed time from the server timestamp", async () => {
  const start = new Date(Date.now() - 125_000).toISOString();
  expect(elapsedSeconds(start)).toBeGreaterThanOrEqual(124);
  expect(elapsedSeconds(start)).toBeLessThanOrEqual(126);
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path=String(input);
    if(path.endsWith("/me")) return json({id:"1",email:"x@y.com",display_name:"",timezone:"UTC"});
    if(path.endsWith("/sessions/active")) return json({id:"s1",title:"Deep build",status:"active",started_at:start,version:1});
    if(path.endsWith("/tasks")||path.endsWith("/areas")) return json([]);
    return json({total_focused_minutes:0,deep_work_minutes:0,planned_completion_rate:0});
  });
  render(<App/>);
  expect(await screen.findByText("Deep build")).toBeInTheDocument();
  expect(screen.getByTestId("elapsed-timer")).toHaveTextContent("00:02:05");
});

test("shows login when the session is unauthenticated", async () => {
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"Authentication credentials were not provided."},403));
  render(<App/>);
  expect(await screen.findByRole("button",{name:"Sign in"})).toBeInTheDocument();
});

test("renders roadmap guidance, progress, and next action detail", async () => {
  const roadmap = { id: "r1", title: "TypeScript", description: "PURPOSE\nBuild typed apps\n\nOUTCOME\nExplain a React app", status: "active" };
  const item = { id: "n1", title: "Union types", description: "Next action: practise and explain.", node_type: "item", state: "planned", time_invested_seconds: 1200, linked_task_ids: [], resources: [], evidence_count: 1, prerequisite_ids: [], children: [] };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/me")) return json({ id:"1", email:"x@y.com", display_name:"", timezone:"UTC" });
    if (path.endsWith("/sessions/active")) return json(null);
    if (path.endsWith("/tasks") || path.endsWith("/areas")) return json([]);
    if (path.endsWith("/analytics/metrics")) return json({ total_focused_minutes:0, deep_work_minutes:0, planned_completion_rate:0 });
    if (path.endsWith("/roadmaps")) return json([roadmap]);
    if (path.endsWith("/roadmaps/next-actions")) return json([{ roadmap_id:"r1", roadmap_title:"TypeScript", node_id:"n1", title:"Union types", description:"", reason:"prerequisite-ready item" }]);
    if (path.endsWith("/roadmaps/r1/tree")) return json({ roadmap, nodes: [item] });
    if (path.endsWith("/roadmaps/r1/progress")) return json({ progress_ratio:0 });
    return json({});
  });
  render(<App/>);
  fireEvent.click(await screen.findByRole("button", { name: /Roadmap/ }));
  expect(await screen.findByRole("heading", { name: "Your paths." })).toBeInTheDocument();
  expect((await screen.findAllByText("Union types")).length).toBe(2);
  expect((screen.getAllByText("Build typed apps")).length).toBe(2);
});
