import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { areas, day, entry, mockApi, prefs, TODAY } from "../../test/mockApi";

test("categories: add one with a unique slug and colour, or restore missing defaults", async () => {
  window.location.hash = "#/profile/categories";
  const api = mockApi({ "POST /areas/ensure-defaults": { created: 2, areas } });
  render(<App />);
  expect(await screen.findByText("Learning")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Learning" } });
  fireEvent.click(screen.getByRole("radio", { name: "#C2410C" }));
  fireEvent.click(screen.getByRole("button", { name: "Add category" }));
  await waitFor(() => expect(api.writes().some((call) => call.path === "/areas")).toBe(true));
  const created = api.writes().find((call) => call.path === "/areas")!;
  // "learning" is taken, so the slug gets a suffix instead of colliding.
  expect(created.body).toMatchObject({ name: "Learning", slug: "learning-2", color: "#C2410C" });

  fireEvent.click(screen.getByRole("button", { name: "Restore any missing default categories" }));
  await waitFor(() => expect(api.writes().some((call) => call.path === "/areas/ensure-defaults")).toBe(true));
});

test("categories: archive and restore through the archive actions, never by editing archived_at", async () => {
  window.location.hash = "#/profile/categories";
  const old = { ...areas[1], id: "a-old", name: "Old hobby", slug: "old-hobby", archived_at: "2026-11-01T10:00:00Z" };
  const api = mockApi({ "/areas": [...areas, old] });
  render(<App />);
  expect(await screen.findByText("Learning")).toBeInTheDocument();
  expect(api.calls.find((call) => call.method === "GET" && call.path === "/areas")?.search).toBe("?archived=include");

  fireEvent.click(screen.getByText("Archived"));
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(api.writes().map((call) => `${call.method} ${call.path}`)).toContain("POST /areas/a-old/restore"));

  fireEvent.click(within(screen.getByText("Learning").closest("li")!).getByRole("button", { name: "Edit" }));
  fireEvent.click(screen.getByRole("button", { name: "Archive" }));
  await waitFor(() => expect(api.writes().map((call) => `${call.method} ${call.path}`)).toContain("POST /areas/a-learn/archive"));
  expect(api.writes().some((call) => call.body && "archived_at" in call.body)).toBe(false);
});

test("reflection: an existing day is edited with its version, never posted twice", async () => {
  window.location.hash = "#/profile/reflect";
  const existing = { id: "r1", version: 3, local_date: TODAY, went_well: "Old words", learned: "L", improve: "I" };
  const api = mockApi({
    "/daily-reflections": [existing],
    "PATCH /daily-reflections/r1": (call: { body: Record<string, unknown> }) => ({ ...existing, ...call.body, version: 4 }),
  });
  render(<App />);
  expect(await screen.findByDisplayValue("Old words")).toBeInTheDocument();
  expect(screen.getByText(/keeps your earlier wording/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("What went well?"), { target: { value: "New words" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(api.writes()).toHaveLength(1));
  expect(api.writes()[0]).toMatchObject({ method: "PATCH", path: "/daily-reflections/r1", body: { went_well: "New words", expected_version: 3 } });
  expect(await screen.findByText(/earlier wording is kept/)).toBeInTheDocument();
});

test("reflection: a new day is created once", async () => {
  window.location.hash = "#/profile/reflect";
  const api = mockApi({ "/daily-reflections": [], "POST /daily-reflections": { id: "r9", version: 1, local_date: TODAY, went_well: "A", learned: "B", improve: "C" } });
  render(<App />);
  fireEvent.change(await screen.findByLabelText("What went well?"), { target: { value: "A" } });
  fireEvent.change(screen.getByLabelText("What did you learn?"), { target: { value: "B" } });
  fireEvent.change(screen.getByLabelText("What will you improve?"), { target: { value: "C" } });
  fireEvent.click(screen.getByRole("button", { name: "Save reflection" }));
  await waitFor(() => expect(api.writes().map((call) => `${call.method} ${call.path}`)).toEqual(["POST /daily-reflections"]));
  expect(api.writes()[0].body).toMatchObject({ local_date: TODAY, went_well: "A" });
});

test("reminder settings save preferences and state that reminders need the app open", async () => {
  window.location.hash = "#/profile/reminders";
  const api = mockApi({ "PATCH /preferences": (call: { body: Record<string, unknown> }) => ({ ...prefs, ...call.body }) });
  render(<App />);
  expect(await screen.findByText(/while CharityOS is open/)).toBeInTheDocument();
  expect(screen.getByText(/not supported on this device/)).toBeInTheDocument();
  expect(screen.getByLabelText("Remind me before")).toBeDisabled();

  fireEvent.click(screen.getByRole("switch", { name: "Activity reminders" }));
  await waitFor(() => expect(api.writes()[0]).toMatchObject({ method: "PATCH", path: "/preferences", body: { reminders_enabled: true } }));
  expect(await screen.findByLabelText("Remind me before")).toBeEnabled();
});

test("a due reminder is shown in the app when system notifications are unavailable", async () => {
  // 10:00 UTC now; the activity starts at 10:05 and the lead time is 10 minutes.
  const soon = entry({ id: "soon", start_local: `${TODAY}T10:05`, end_local: `${TODAY}T11:00` });
  mockApi({
    "/preferences": { ...prefs, reminders_enabled: true },
    "/schedule/day": day([soon]),
    "/schedule-entries": [soon],
  });
  render(<App />);
  const status = await screen.findByText(/Grocery shopping in 10 min/);
  expect(within(status.closest(".toasts")!).getByText(/Personal/)).toBeInTheDocument();
});
