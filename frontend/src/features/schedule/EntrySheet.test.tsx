import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { App } from "../../app/App";
import { day, entry, json, mockApi, TODAY } from "../../test/mockApi";
import type { Entry } from "../../lib/types";

/** Opens the entry sheet from the Today agenda. */
async function openSheet(title: string) {
  const buttons = await screen.findAllByRole("button", { name: new RegExp(title) });
  fireEvent.click(buttons.find((button) => button.classList.contains("entry-main"))!);
  return screen.findByRole("dialog");
}

function serve(initial: Entry) {
  let current = initial;
  const respond = (patch: Partial<Entry>) => () => {
    current = { ...current, ...patch, version: current.version + 1 };
    return current;
  };
  return {
    routes: {
      "/schedule/day": () => day([current]),
      [`/schedule-entries/${initial.id}`]: () => current,
      [`POST /schedule-entries/${initial.id}/start`]: respond({ status: "in_progress", actual_started_at: `${TODAY}T10:00:00Z`, actual_seconds: 0 }),
      [`POST /schedule-entries/${initial.id}/pause`]: respond({ status: "paused", paused_at: `${TODAY}T10:20:00Z`, actual_seconds: 1200 }),
      [`POST /schedule-entries/${initial.id}/resume`]: respond({ status: "in_progress", paused_at: null }),
      [`POST /schedule-entries/${initial.id}/skip`]: respond({ status: "skipped" }),
      [`POST /schedule-entries/${initial.id}/complete`]: (call: { body: Record<string, unknown> }) =>
        respond({
          status: call.body.partial ? "partially_completed" : "completed",
          outcome: String(call.body.outcome ?? ""),
          actual_seconds: call.body.actual_minutes !== undefined ? Number(call.body.actual_minutes) * 60 : null,
          actual_minutes: call.body.actual_minutes !== undefined ? Number(call.body.actual_minutes) : null,
        })(),
    },
    get current() {
      return current;
    },
  };
}

test("start, pause, resume and finish with outcome and actual minutes", async () => {
  const shop = entry({ id: "e1", start_local: `${TODAY}T10:00`, end_local: `${TODAY}T11:00` });
  const server = serve(shop);
  const api = mockApi(server.routes);
  render(<App />);
  let dialog = await openSheet("Grocery shopping");

  fireEvent.click(within(dialog).getByRole("button", { name: "Start" }));
  expect(await within(dialog).findByText("In progress")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Pause" }));
  expect(await within(dialog).findByText(/time is not counting/)).toBeInTheDocument();
  expect(within(dialog).getByTestId("entry-timer")).toHaveTextContent("00:20:00");
  fireEvent.click(within(dialog).getByRole("button", { name: "Resume" }));
  // Actions are disabled while a command is in flight; wait for the resumed state.
  await within(dialog).findByRole("button", { name: "Pause" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Finish" }));

  dialog = await screen.findByRole("dialog", { name: "Finish activity" });
  expect(within(dialog).getByLabelText("Actual minutes")).toHaveValue(20);
  fireEvent.change(within(dialog).getByLabelText("Actual minutes"), { target: { value: "25" } });
  fireEvent.change(within(dialog).getByLabelText("Outcome"), { target: { value: "Bought everything" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Complete" }));

  expect(await screen.findByText("Nice work")).toBeInTheDocument();
  const paths = api.writes().map((call) => call.path.split("/").pop());
  expect(paths).toEqual(["start", "pause", "resume", "complete"]);
  const versions = api.writes().map((call) => call.body?.expected_version);
  expect(versions).toEqual([1, 2, 3, 4]);
  expect(api.writes()[3].body).toMatchObject({ actual_minutes: 25, outcome: "Bought everything", partial: false });
});

test("mark an unstarted activity done without inventing time, or record it explicitly", async () => {
  const server = serve(entry({ id: "e2", title: "Evening cycling", start_local: `${TODAY}T18:00`, end_local: `${TODAY}T19:00` }));
  const api = mockApi(server.routes);
  render(<App />);
  const dialog = await openSheet("Evening cycling");
  fireEvent.click(within(dialog).getByRole("button", { name: "Mark done" }));
  const form = await screen.findByRole("dialog", { name: "Finish activity" });
  expect(within(form).getByLabelText(/How long did it take/)).toHaveValue(null);
  expect(within(form).getByText(/blank means the actual time stays unknown/)).toBeInTheDocument();
  fireEvent.click(within(form).getByRole("button", { name: /As planned/ }));
  expect(within(form).getByLabelText(/How long did it take/)).toHaveValue(60);
  fireEvent.change(within(form).getByLabelText(/How long did it take/), { target: { value: "45" } });
  fireEvent.click(within(form).getByRole("checkbox", { name: "Only partly done" }));
  fireEvent.click(within(form).getByRole("button", { name: "Save as partly done" }));
  await waitFor(() => expect(api.writes()).toHaveLength(1));
  expect(api.writes()[0].body).toMatchObject({ actual_minutes: 45, partial: true });
});

test("recording actual start and end converts the user's local times to instants", async () => {
  const server = serve(entry({ id: "e3", title: "Errand" }));
  const api = mockApi(server.routes);
  render(<App />);
  const dialog = await openSheet("Errand");
  fireEvent.click(within(dialog).getByRole("button", { name: "Mark done" }));
  const form = await screen.findByRole("dialog", { name: "Finish activity" });
  fireEvent.click(within(form).getByRole("button", { name: "I know the start and end" }));
  fireEvent.change(within(form).getByLabelText("Actual start"), { target: { value: "14:10" } });
  fireEvent.change(within(form).getByLabelText("Actual end"), { target: { value: "14:55" } });
  fireEvent.click(within(form).getByRole("button", { name: "Complete" }));
  await waitFor(() => expect(api.writes()).toHaveLength(1));
  expect(api.writes()[0].body).toMatchObject({ actual_started_at: `${TODAY}T14:10:00.000Z`, actual_ended_at: `${TODAY}T14:55:00.000Z` });
  expect(api.writes()[0].body).not.toHaveProperty("actual_minutes");
});

test("future scheduled activity is moved; a past one is rescheduled keeping history", async () => {
  const future = entry({ id: "future", title: "Lunch", start_local: `${TODAY}T12:00`, end_local: `${TODAY}T13:00` });
  const past = entry({ id: "past", title: "Morning run", start_local: `${TODAY}T06:00`, end_local: `${TODAY}T06:30` });
  const api = mockApi({
    "/schedule/day": day([past, future]),
    "/schedule-entries/future": future,
    "/schedule-entries/past": past,
    "PATCH /schedule-entries/future": { ...future, start_local: `${TODAY}T12:30`, version: 2 },
    "POST /schedule-entries/past/reschedule": { original: { ...past, status: "rescheduled" }, entry: { ...past, id: "new", start_local: "2026-11-25T06:00" } },
  });
  render(<App />);

  let dialog = await openSheet("Lunch");
  fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));
  dialog = await screen.findByRole("dialog", { name: "Move or reschedule" });
  expect(within(dialog).getByText(/moving it simply changes the plan/)).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "+30 min" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));
  await waitFor(() => expect(api.writes()).toHaveLength(1));
  expect(api.writes()[0]).toMatchObject({ method: "PATCH", body: { start_local: `${TODAY}T12:30`, end_local: `${TODAY}T13:30`, expected_version: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Close" }));

  dialog = await openSheet("Morning run");
  fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));
  dialog = await screen.findByRole("dialog", { name: "Move or reschedule" });
  expect(within(dialog).getByText(/keeps the original in your history/)).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Tomorrow" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Reschedule" }));
  await waitFor(() => expect(api.writes()).toHaveLength(2));
  expect(api.writes()[1]).toMatchObject({ method: "POST", path: "/schedule-entries/past/reschedule", body: { start_local: "2026-11-25T06:00", end_local: "2026-11-25T06:30" } });
});

test("skip and cancel are available; cancel asks for confirmation", async () => {
  const server = serve(entry({ id: "e4", title: "Call mum", start_local: `${TODAY}T16:00`, end_local: `${TODAY}T16:30` }));
  const api = mockApi({ ...server.routes, "POST /schedule-entries/e4/cancel": { ...server.current, status: "cancelled" } });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<App />);
  const dialog = await openSheet("Call mum");
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel activity" }));
  expect(confirm).toHaveBeenCalled();
  expect(api.writes()).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole("button", { name: "Skip" }));
  expect(await within(dialog).findByText("Skipped")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Reschedule" })).toBeInTheDocument();
});

test("a version conflict reloads the activity and explains why", async () => {
  const shop = entry({ id: "e5" });
  mockApi({
    "/schedule/day": day([shop]),
    "/schedule-entries/e5": { ...shop, version: 3, title: "Grocery shopping (edited elsewhere)" },
    "POST /schedule-entries/e5/start": json({ detail: "This activity changed on another device. Refresh and try again.", error: { code: "version_conflict", message: "changed" } }, 409),
  });
  render(<App />);
  const dialog = await openSheet("Grocery shopping");
  fireEvent.click(within(dialog).getByRole("button", { name: "Start" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(/another device/);
});
