import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "../app/App";
import { json, mockApi } from "../test/mockApi";

afterEach(() => {
  window.location.hash = "";
});

test("signed out, an invite link opens sign-up with the code filled in and requires consent", async () => {
  window.location.hash = "#/signup?code=abc-123";
  const api = mockApi({ "/me": () => json({ error: { code: "not_authenticated", message: "No" } }, 403), "/auth/csrf": { csrf_token: "t" } });
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Create your account" })).toBeInTheDocument();
  expect(screen.getByLabelText("Invite code")).toHaveValue("abc-123");
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "amina@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-Long-phrase-123" } });
  fireEvent.change(screen.getByLabelText("Repeat password"), { target: { value: "a-Long-phrase-123" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(await screen.findByText(/read and accept the privacy notice/)).toBeInTheDocument();
  expect(api.writes()).toHaveLength(0);
});

test("the sign-in page links to sign-up and privacy", async () => {
  mockApi({ "/me": () => json({ error: { code: "not_authenticated", message: "No" } }, 403) });
  render(<App />);
  expect(await screen.findByRole("link", { name: /Have an invite/ })).toHaveAttribute("href", "#/signup");
  expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "#/privacy");
});

test("a partner's view is read only and shows only what was shared", async () => {
  window.location.hash = "#/partners/p1";
  const api = mockApi({
    "/partners/p1/view": {
      id: "p1",
      owner: "Charity",
      status: "active",
      paused: false,
      goals: [{ id: "g1", title: "Ship CharityOS", status: "active", target_date: null, progress: 0.5, basis: "milestones", overdue: false, milestones: [{ title: "Beta", status: "done", target_date: null }] }],
      summary: { week_start: "2026-11-23", tasks_completed: 4, focus_minutes: 120, milestones_completed: 1 },
      weekly_reviews: [],
      cheers: [],
    },
    "POST /partners/p1/cheer": { id: "c1", kind: "cheer" },
  });
  render(<App />);
  expect(await screen.findByText("Ship CharityOS")).toBeInTheDocument();
  expect(screen.getByText("Shared with you · read only")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Edit|Archive|Complete/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Encourage" }));
  const dialog = await screen.findByRole("dialog", { name: "Encourage" });
  fireEvent.change(within(dialog).getByLabelText(/Message/), { target: { value: "Go!" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Send" }));
  await waitFor(() => expect(api.writes().map((w) => w.body)).toEqual([{ kind: "cheer", message: "Go!", about: "goal:g1" }]));
});

test("the beta admin screen is hidden from ordinary users", async () => {
  window.location.hash = "#/beta";
  const api = mockApi();
  render(<App />);
  expect(await screen.findByText("Beta admins only")).toBeInTheDocument();
  expect(api.calls.some((call) => call.path.startsWith("/beta/"))).toBe(false);
  vi.restoreAllMocks();
});
