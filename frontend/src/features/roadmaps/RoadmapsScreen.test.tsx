import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { mockApi } from "../../test/mockApi";

test("Add to Today creates a task with the server's default status and plans it", async () => {
  const roadmap = { id: "r1", title: "TypeScript", description: "PURPOSE\nBuild typed apps", status: "active" };
  const item = { id: "n1", title: "Union types", description: "", node_type: "item", state: "planned", time_invested_seconds: 0, linked_task_ids: [], resources: [], evidence_count: 0, children: [] };
  window.location.hash = "#/roadmaps";
  const api = mockApi({
    "/roadmaps": [roadmap],
    "/roadmaps/r1/tree": { roadmap, nodes: [item] },
    "POST /tasks": { id: "t9", title: "Union types", status: "todo", is_deep_work_default: true },
    "/daily-plans/today": { plan: { id: "p1" } },
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /TypeScript/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Add to Today" }));
  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/tasks", "/daily-plan-items"]));
  expect(api.writes()[0].body).toEqual({ title: "Union types", roadmap_item: "n1", is_deep_work_default: true });
  expect(api.writes()[1].body).toMatchObject({ plan: "p1", task: "t9", kind: "secondary" });
});
