import { render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { App } from "../../app/App";
import { mockApi } from "../../test/mockApi";

afterEach(() => {
  window.location.hash = "";
});

test("direction shows quiet goals and what keeps slipping", async () => {
  window.location.hash = "#/insights?view=direction";
  mockApi({
    "/insights/direction": {
      goals: [{ id: "g1", title: "Ship portfolio", status: "active", ratio: null, basis: "none", overdue: false, at_risk: false, days_left: null, activity_30d: 0 }],
      roadmaps: [],
      projects: [],
      postponed: [{ id: "t1", title: "Write case study", times: 3, status: "todo" }],
    },
  });
  render(<App />);
  expect(await screen.findByText("Ship portfolio")).toBeInTheDocument();
  expect(screen.getByText("No measure yet")).toBeInTheDocument();
  expect(screen.getByText(/One active goal has had no activity for 30 days/)).toBeInTheDocument();
  expect(screen.getByText("moved 3×")).toBeInTheDocument();
});

test("direction has an honest empty state", async () => {
  window.location.hash = "#/insights?view=direction";
  mockApi({ "/insights/direction": { goals: [], roadmaps: [], projects: [], postponed: [] } });
  render(<App />);
  expect(await screen.findByText("Nothing to measure yet")).toBeInTheDocument();
});
