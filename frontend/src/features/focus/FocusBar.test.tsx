import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { NOW, mockApi } from "../../test/mockApi";

const session = {
  id: "s1",
  title: "Udemy: section 4",
  status: "active",
  started_at: new Date(NOW.getTime() - 25 * 60_000).toISOString(),
  version: 1,
  elapsed_seconds: 1500,
  task: "t1",
  area: "a-learn",
  schedule_entry: null,
};

test("finishing focus on a task can also mark the task done, only when asked", async () => {
  const api = mockApi({ "/sessions/active": session, "POST /sessions/s1/finish": { ...session, status: "completed" }, "POST /tasks/t1/complete": {} });
  window.location.hash = "#/tasks";
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Finish focus" }));
  const sheet = await screen.findByRole("dialog", { name: "Finish focus session" });
  fireEvent.click(within(sheet).getByLabelText(/mark it complete/));
  fireEvent.click(within(sheet).getByRole("button", { name: "Save and finish" }));

  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/sessions/s1/finish", "/tasks/t1/complete"]));
});

test("without the tick the task stays open", async () => {
  const api = mockApi({ "/sessions/active": session, "POST /sessions/s1/finish": { ...session, status: "completed" } });
  window.location.hash = "#/tasks";
  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Finish focus" }));
  fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Save and finish" }));

  await waitFor(() => expect(api.writes().map((call) => call.path)).toEqual(["/sessions/s1/finish"]));
});
