import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "../../app/App";
import { entry, json, mockApi, TODAY } from "../../test/mockApi";

async function openQuickAdd() {
  fireEvent.click(await screen.findByRole("button", { name: "Quick add activity" }));
  return screen.findByRole("dialog", { name: "Quick add" });
}

test("quick add: title → category → date → start → end → save", async () => {
  const api = mockApi({ "POST /schedule-entries": (call: { body: Record<string, unknown> }) => json(entry({ title: String(call.body.title) }), 201) });
  render(<App />);
  const dialog = await openQuickAdd();

  fireEvent.change(within(dialog).getByLabelText("Title", { exact: true }), { target: { value: "Morning study" } });
  fireEvent.click(within(dialog).getByRole("radio", { name: /Learning/ }));
  fireEvent.change(within(dialog).getByLabelText("Date", { exact: true }), { target: { value: TODAY } });
  fireEvent.change(within(dialog).getByLabelText("Start", { exact: true }), { target: { value: "08:00" } });
  fireEvent.change(within(dialog).getByLabelText("End", { exact: true }), { target: { value: "09:30" } });
  expect(within(dialog).getByText("1h 30m", { selector: ".hint" })).toBeInTheDocument();
  // Learning defaults to the focus timer; it can be switched off.
  expect(within(dialog).getByRole("switch", { name: "Track with the focus timer" })).toBeChecked();
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => expect(api.writes()).toHaveLength(1));
  const [call] = api.writes();
  expect(call.path).toBe("/schedule-entries");
  expect(call.body).toMatchObject({
    title: "Morning study",
    area: "a-learn",
    tracking: "focus",
    start_local: `${TODAY}T08:00`,
    end_local: `${TODAY}T09:30`,
    timezone_name: "UTC",
    allow_overlap: false,
  });
  expect(call.body?.id).toEqual(expect.any(String));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(await screen.findByText(/Added “Morning study”/)).toBeInTheDocument();
});

test("duration chips set the end and an end before the start crosses midnight", async () => {
  mockApi();
  render(<App />);
  const dialog = await openQuickAdd();
  fireEvent.change(within(dialog).getByLabelText("Start", { exact: true }), { target: { value: "22:30" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "2h" }));
  expect(within(dialog).getByLabelText("End", { exact: true })).toHaveValue("00:30");
  expect(within(dialog).getByText(/ends the next day/)).toBeInTheDocument();
});

test("title is required before saving", async () => {
  const api = mockApi();
  render(<App />);
  const dialog = await openQuickAdd();
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Give the activity a title.");
  expect(api.writes()).toHaveLength(0);
});

test("overlap is flagged and saving again explicitly allows it with the same id", async () => {
  let attempts = 0;
  const api = mockApi({
    "POST /schedule-entries": () => {
      attempts += 1;
      return attempts === 1
        ? json({ detail: "This time overlaps with Lecture.", error: { code: "schedule_overlap", message: "overlap", conflicts: [{ id: "x", title: "Lecture", start_at: `${TODAY}T09:00:00Z`, end_at: `${TODAY}T10:00:00Z` }] } }, 409)
        : json(entry({ title: "Gym" }), 201);
    },
  });
  render(<App />);
  const dialog = await openQuickAdd();
  fireEvent.change(within(dialog).getByLabelText("Title", { exact: true }), { target: { value: "Gym" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(await within(dialog).findByText(/This overlaps/)).toBeInTheDocument();
  expect(within(dialog).getByText(/Lecture/)).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole("button", { name: "Keep both" }));
  await waitFor(() => expect(api.writes()).toHaveLength(2));
  const [first, second] = api.writes();
  expect(second.body).toMatchObject({ allow_overlap: true });
  expect(second.body?.id).toBe(first.body?.id);
});

