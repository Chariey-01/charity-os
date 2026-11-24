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
