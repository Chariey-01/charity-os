// Mobile acceptance scenario for CharityOS (see docs/acceptance/README.md).
// Usage: node acceptance.mjs <screenshot-dir> <password-file>
// Env: BASE_URL (default http://127.0.0.1:4173), CHROME_PATH, ACCEPT_EMAIL.
import { chromium } from "playwright-core";
import fs from "node:fs";

const [,, shots, pwFile] = process.argv;
const password = fs.readFileSync(pwFile, "utf8").trim();
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:4173";
const EMAIL = process.env.ACCEPT_EMAIL ?? "acceptance@example.com";
const log = (...args) => console.log("•", ...args);
const assert = (cond, msg) => { if (!cond) throw new Error(`ASSERTION FAILED: ${msg}`); log("ok:", msg); };

// Pick a zone where it is currently morning so the scenario is real.
const ZONES = ["Pacific/Honolulu","America/Anchorage","America/Los_Angeles","America/Denver","America/Chicago","America/New_York","America/Halifax","America/Sao_Paulo","Atlantic/South_Georgia","Atlantic/Azores","Europe/London","Europe/Paris","Africa/Cairo","Africa/Nairobi","Asia/Dubai","Asia/Karachi","Asia/Dhaka","Asia/Bangkok","Asia/Singapore","Asia/Tokyo","Australia/Brisbane","Pacific/Noumea","Pacific/Auckland"];
const hourIn = (tz) => Number(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", hourCycle: "h23" }).format(new Date()));
const tz = ZONES.find((zone) => { const h = hourIn(zone); return h >= 7 && h < 9; }) ?? "Africa/Nairobi";
log("timezone", tz, "local hour", hourIn(tz));

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, timezoneId: tz, locale: "en-GB" });
const page = await ctx.newPage();
const problems = [];
page.on("console", (m) => { if (m.type() === "error") problems.push(`${m.type()}: ${m.text()}`); });
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
let n = 0;
const shot = async (name) => { n += 1; const file = `${shots}/${String(n).padStart(2, "0")}-${name}.png`; await page.waitForTimeout(350); await page.screenshot({ path: file }); };
const api = async (path) => (await page.request.get(`${BASE}/api/v1${path}`)).json();
const nav = (name) => page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name });
const sheet = () => page.getByRole("dialog");

// 1. Install / open
await page.goto(`${BASE}/`);
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Password").fill(password);
await page.getByRole("button", { name: "Sign in" }).click();
await page.locator("#today-title").waitFor();
const manifest = await (await page.request.get(`${BASE}/manifest.webmanifest`)).json();
assert(manifest.display === "standalone" && manifest.icons.some((i) => i.sizes === "512x512" && i.purpose === "maskable"), "manifest is installable (standalone, 192/512 + maskable icons)");
const sw = await page.evaluate(async () => { const reg = await navigator.serviceWorker.ready; return { scope: reg.scope, active: Boolean(reg.active) }; });
assert(sw.active, `service worker active (scope ${sw.scope})`);

// Align the profile timezone with the device via the UI.
await nav("Profile").click();
const tzButton = page.getByRole("button", { name: /Use this device's timezone/ });
if (await tzButton.count()) { await tzButton.click(); await page.getByText(`Timezone set to ${tz}`).waitFor(); }
assert((await api("/me")).timezone === tz, `user timezone is ${tz}`);
await nav("Today").click();
await page.locator("#today-title").waitFor();
await shot("today-empty");

const today = (await api("/schedule/day")).date;
async function quickAdd({ title, category, start, end, focus }) {
  await page.getByRole("button", { name: "Quick add activity" }).click();
  const dialog = sheet();
  await dialog.getByLabel("Title", { exact: true }).fill(title);
  await dialog.getByRole("radio", { name: category }).click();
  await dialog.getByLabel("Date", { exact: true }).fill(today);
  await dialog.getByLabel("Start", { exact: true }).fill(start);
  await dialog.getByLabel("End", { exact: true }).fill(end);
  const toggle = dialog.getByRole("switch", { name: "Track with the focus timer" });
  if ((await toggle.isChecked()) !== focus) await toggle.click();
  return dialog;
}

// 2. Study session in the morning (focus-tracked)
let dialog = await quickAdd({ title: "Study: dynamic programming", category: "Learning", start: "08:00", end: "09:30", focus: true });
await shot("quick-add-study");
await dialog.getByRole("button", { name: "Save" }).click();
await page.getByText(/Added “Study: dynamic programming”/).waitFor();
// 3. Shopping in the afternoon
dialog = await quickAdd({ title: "Grocery shopping", category: "Personal", start: "14:00", end: "15:00", focus: false });
await dialog.getByRole("button", { name: "Save" }).click();
await page.getByText(/Added “Grocery shopping”/).waitFor();
// 4. Exercise in the evening
dialog = await quickAdd({ title: "Evening cycling", category: "Exercise", start: "18:00", end: "19:00", focus: false });
await dialog.getByRole("button", { name: "Save" }).click();
await page.getByText(/Added “Evening cycling”/).waitFor();

// Overlap protection: a clashing entry is flagged, then cancelled.
dialog = await quickAdd({ title: "Team call", category: "Career", start: "18:30", end: "19:00", focus: false });
await dialog.getByRole("button", { name: "Save" }).click();
await dialog.getByText(/This overlaps/).waitFor();
await shot("overlap-warning");
await dialog.getByRole("button", { name: "Close" }).click();
let day = await api("/schedule/day");
assert(day.entries.length === 3, "three activities scheduled; the overlapping one was not saved");
await shot("today-planned");

// 5. Start the study activity
await page.getByRole("button", { name: "Start Study: dynamic programming" }).click();
await page.locator(".current-card").waitFor();
await page.waitForTimeout(2500);
await shot("study-in-progress");
// The timer stays one tap away on every other screen.
await nav("Schedule").click();
const bar = page.getByRole("region", { name: "Focus session" });
await bar.waitFor();
assert((await bar.textContent()).includes("Study: dynamic programming"), "focus bar with live timer is shown on other tabs");
await shot("focus-bar-on-schedule");
await nav("Today").click();
await page.locator(".current-card").waitFor();
day = await api("/schedule/day");
const study = day.entries.find((e) => e.title.startsWith("Study"));
assert(study.status === "in_progress" && study.focus_session, "study is in progress with a linked server focus session");

// 6. Pause and resume
await page.locator(".current-card").getByRole("button", { name: "Pause" }).click();
await page.locator(".current-card.paused").waitFor();
const pausedClock = await page.getByTestId("current-timer").textContent();
await page.waitForTimeout(2500);
assert((await page.getByTestId("current-timer").textContent()) === pausedClock, `paused timer stays at ${pausedClock}`);
await shot("study-paused");
await page.locator(".current-card").getByRole("button", { name: "Resume" }).click();
await page.locator(".current-card.in_progress").waitFor();
await page.waitForTimeout(3000);
await shot("study-resumed");

// 7. Finish and record the outcome
await page.locator(".current-card").getByRole("button", { name: "Finish" }).click();
dialog = sheet();
await dialog.getByLabel("Outcome").fill("Solved 4 knapsack variants; wrote notes on memoisation vs tabulation.");
await dialog.getByLabel("What did you learn?").fill("Bottom-up tables avoid recursion limits.");
await shot("study-finish-form");
await dialog.getByRole("button", { name: "Complete" }).click();
await page.locator(".celebration").waitFor();
await shot("celebration");
await page.locator(".celebration").waitFor({ state: "detached", timeout: 5000 });

// 8. Mark shopping completed (as planned)
await page.getByRole("button", { name: /Grocery shopping/ }).first().click();
dialog = sheet();
await dialog.getByRole("button", { name: "Mark done" }).click();
await dialog.getByRole("button", { name: /As planned/ }).click();
await dialog.getByLabel("Outcome").fill("Got everything on the list.");
await shot("shopping-mark-done");
await dialog.getByRole("button", { name: "Complete" }).click();
await page.locator(".celebration").waitFor();
await page.locator(".celebration").waitFor({ state: "detached", timeout: 5000 });

// 9. Record the actual exercise duration
await page.getByRole("button", { name: /Evening cycling/ }).first().click();
dialog = sheet();
await dialog.getByRole("button", { name: "Mark done" }).click();
await dialog.getByLabel(/How long did it take/).fill("45");
await dialog.getByLabel("Outcome").fill("Easy recovery ride, 15 km.");
await shot("exercise-duration");
await dialog.getByRole("button", { name: "Complete" }).click();
await page.locator(".celebration").waitFor();
await page.locator(".celebration").waitFor({ state: "detached", timeout: 5000 });

// 10. Review the day's progress
await page.locator(".summary-card").getByText("3 of 3 done").waitFor();
await shot("today-progress");
await page.getByRole("tab", { name: "Timeline" }).click();
await shot("today-timeline");
await page.getByRole("tab", { name: "Day" }).click();
await shot("today-dayview");
const completedToggle = page.locator("details").filter({ hasText: "Completed" }).locator("summary");
await page.getByRole("tab", { name: "Agenda" }).click();
await completedToggle.click();
await shot("today-completed-list");

// 11. Weekly and monthly schedule views
await nav("Schedule").click();
await page.getByRole("tab", { name: "Week" }).click();
await page.locator(".week").waitFor();
await shot("schedule-week");
await page.getByRole("tab", { name: "Month" }).click();
await page.locator(".month").waitFor();
await shot("schedule-month");
await page.getByRole("tab", { name: "Day" }).click();
await page.locator(".day-grid").waitFor();
await shot("schedule-day");

// 12. Refresh and confirm persistence
await page.reload();
await nav("Today").click();
await page.locator(".summary-card").getByText("3 of 3 done").waitFor();
await shot("after-reload");

// 13. History and analytics accuracy
day = await api("/schedule/day");
const byTitle = Object.fromEntries(day.entries.map((e) => [e.title, e]));
const studyDone = byTitle["Study: dynamic programming"];
const session = (await api("/sessions")).find((s) => s.id === studyDone.focus_session);
assert(studyDone.status === "completed" && studyDone.outcome.startsWith("Solved"), "study completed with outcome persisted");
assert(session.status === "completed" && session.duration_seconds === studyDone.actual_seconds, `study actual (${studyDone.actual_seconds}s) equals the server focus session duration`);
assert(byTitle["Grocery shopping"].status === "completed" && byTitle["Grocery shopping"].actual_minutes === 60, "shopping completed, 60 minutes as explicitly confirmed");
assert(byTitle["Evening cycling"].actual_minutes === 45, "exercise actual duration is 45 minutes");
assert(day.progress.completed === 3 && day.progress.planned === 3, "day progress 3/3");
const insights = await api("/insights?period=7d");
const todayRow = insights.schedule_daily.find((d) => d.date === today);
assert(todayRow.planned === 3 && todayRow.completed === 3, "insights planned vs completed for today = 3/3");
const exerciseToday = insights.health.exercise_daily.find((d) => d.date === today).minutes;
assert(exerciseToday === 45, "health exercise history shows 45 minutes today");
const tracked = insights.category_time.reduce((sum, row) => sum + row.actual_minutes, 0);
const expected = Math.round(session.duration_seconds / 60) + 60 + 45;
assert(tracked === expected, `time by category counts each minute once (${tracked} = ${expected})`);
assert(insights.week.completed >= 3 && insights.week.milestones[0].reached, "weekly milestone of 3 reached");

await nav("Insights").click();
await page.locator(".stat-grid").waitFor();
await page.getByRole("radio", { name: "7 days" }).click();
await page.waitForTimeout(800);
await shot("insights-top");
await page.locator(".chart").first().scrollIntoViewIfNeeded();
await shot("insights-charts");
await page.locator(".health-section").scrollIntoViewIfNeeded();
await shot("insights-health");
await nav("Profile").click();
await page.getByRole("link", { name: "History" }).click();
await page.getByText("Solved 4 knapsack", { exact: false }).first().waitFor();
await shot("history");

console.log(JSON.stringify({ tz, today, problems }, null, 1));
await browser.close();
