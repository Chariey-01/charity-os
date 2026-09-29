import { render, screen } from "@testing-library/react";
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
