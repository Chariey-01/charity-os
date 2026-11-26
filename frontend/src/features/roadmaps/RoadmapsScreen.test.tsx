import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { mockApi } from "../../test/mockApi";

test("Add to Today is one atomic request for the roadmap item", async () => {
  const roadmap = { id: "r1", title: "TypeScript", description: "PURPOSE\nBuild typed apps", status: "active", area: "a-learn" };
  const item = { id: "n1", title: "Union types", description: "", node_type: "item", state: "planned", time_invested_seconds: 0, linked_task_ids: [], resources: [], evidence_count: 0, children: [] };
  window.location.hash = "#/roadmaps";
  const api = mockApi({
    "/roadmaps": [roadmap],
    "/roadmaps/r1/tree": { roadmap, nodes: [item] },
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /TypeScript/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Add to Today" }));
  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/roadmap-nodes/n1/add-to-today"]));
  expect(api.writes()[0].body).toEqual({});
});

test("Start focus sends the roadmap's category and a client session id in the same request", async () => {
  const roadmap = { id: "r1", title: "TypeScript", description: "", status: "active", area: "a-learn" };
  const item = { id: "n1", title: "Union types", description: "", node_type: "item", state: "planned", time_invested_seconds: 0, linked_task_ids: [], resources: [], evidence_count: 0, children: [] };
  window.location.hash = "#/roadmaps";
  const api = mockApi({ "/roadmaps": [roadmap], "/roadmaps/r1/tree": { roadmap, nodes: [item] } });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /TypeScript/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Start focus" }));
  await waitFor(() => expect(api.writes()).toHaveLength(1));
  expect(api.writes()[0].path).toBe("/roadmap-nodes/n1/add-to-today");
  expect(api.writes()[0].body).toMatchObject({ start_focus: true, area: "a-learn" });
  expect(typeof api.writes()[0].body?.session_id).toBe("string");
});
