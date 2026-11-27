// Browser journey through the Life OS screens. Usage:
//   node life-os.mjs <base-url> <shots-dir> <password-file> [width]
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright-core";

const [base, shots, pwFile, widthArg] = process.argv.slice(2);
const width = Number(widthArg || 390);
const password = readFileSync(pwFile, "utf8").trim();
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true });
const context = await browser.newContext({ viewport: { width, height: 844 }, deviceScaleFactor: 1, isMobile: width < 700, hasTouch: width < 700, timezoneId: "Africa/Nairobi", locale: "en-GB" });
const page = await context.newPage();
const errors = [];
page.on("console", (msg) => msg.type() === "error" && errors.push(msg.text()));
page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
const results = [];
let step = 0;

async function shot(name) {
  step += 1;
  const file = `${shots}/${String(step).padStart(2, "0")}-${name}-${width}.png`;
  await page.screenshot({ path: file, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 0) results.push({ check: `no horizontal overflow on ${name}`, pass: false, detail: `${overflow}px` });
  return file;
}
async function check(name, fn) {
  try {
    await fn();
    results.push({ check: name, pass: true });
  } catch (err) {
    results.push({ check: name, pass: false, detail: String(err.message).split("\n")[0] });
    await shot(`FAIL-${name.replace(/\W+/g, "-").slice(0, 40)}`).catch(() => {});
    for (let i = 0; i < 3; i += 1) await page.keyboard.press("Escape").catch(() => {});
  }
}
const go = async (hash) => {
  await page.evaluate((h) => (window.location.hash = h), hash);
  await page.waitForTimeout(500);
};
const dialog = () => page.getByRole("dialog");

await page.goto(base);
await check("sign in", async () => {
  await page.getByLabel("Email").fill("demo@example.com");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Primary" }).waitFor();
});
await shot("today");

await check("plan hub", async () => {
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Plan" }).click();
  await page.getByRole("heading", { name: "From vision to today" }).waitFor();
});
await shot("plan-empty");

await check("vision: write statement and a manifestation", async () => {
  await go("#/vision");
  await page.getByRole("button", { name: "Write my vision" }).click();
  await dialog().getByRole("radio", { name: "Vision" }).click();
  await dialog().getByLabel("Title", { exact: true }).fill("A life of craft, service and freedom (demo)");
  await dialog().getByLabel("Your vision, in your words").fill("I build useful AI products, lead with integrity and keep learning every year.");
  await dialog().getByLabel(/^Theme/).fill("Life");
  await dialog().getByRole("button", { name: "Add", exact: true }).click();
  await dialog().waitFor({ state: "detached" });
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await dialog().getByRole("radio", { name: "Manifestation" }).click();
  await dialog().getByLabel("Title", { exact: true }).fill("I work as an AI engineer on a product team (demo)");
  await dialog().getByLabel(/^Theme/).fill("Career");
  await dialog().getByLabel("Horizon").selectOption("medium");
  await dialog().getByRole("button", { name: "Add", exact: true }).click();
  await dialog().waitFor({ state: "detached" });
  await page.getByText("I work as an AI engineer on a product team (demo)").waitFor();
});
await shot("vision-board");

await check("vision: realising requires evidence or confirmation", async () => {
  await page.getByRole("button", { name: /I work as an AI engineer/ }).click();
  await shot("vision-detail");
  await dialog().getByRole("button", { name: "It came true" }).click();
  await dialog().getByRole("button", { name: "Record it" }).click();
  await dialog().getByText(/Add a link as evidence, or tick the box/).waitFor();
  await dialog().getByRole("button", { name: "Cancel" }).click();
});

await check("goal: create measurable goal from vision", async () => {
  await go("#/goals");
  await page.getByRole("button", { name: "Create your first goal" }).click();
  await dialog().getByLabel("Goal", { exact: true }).fill("Complete the AI Engineering roadmap (demo)");
  await dialog().getByLabel("Why it matters").fill("It is the path to the work I want to do.");
  await dialog().getByLabel("Target date").fill("2027-06-30");
  await dialog().getByLabel("Part of my vision").selectOption({ label: "I work as an AI engineer on a product team (demo)" });
  await dialog().getByRole("button", { name: "Create goal" }).click();
  await page.getByRole("heading", { name: "Complete the AI Engineering roadmap (demo)" }).waitFor();
  await page.getByText(/does not guess/).waitFor();
});

await check("goal: milestones drive progress", async () => {
  for (const title of ["Finish stages 1–4 (demo)", "Ship a RAG portfolio project (demo)"]) {
    await page.getByLabel("New milestone").fill(title);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await page.getByText(title).waitFor();
  }
  await page.getByRole("checkbox", { name: "Complete Finish stages 1–4 (demo)" }).click();
  await page.getByText("1 of 2 milestones done.").waitFor();
  await page.getByText("50%").first().waitFor();
});
await page.waitForTimeout(2800);
await shot("goal-detail");

await check("goal: check-in note", async () => {
  await page.getByLabel("Progress note").fill("Finished NumPy and pandas basics.");
  await page.getByRole("button", { name: "Check in" }).click();
  await page.getByText("Finished NumPy and pandas basics.").first().waitFor();
});

await check("roadmap: AI Engineering template", async () => {
  await go("#/roadmaps");
  await page.getByRole("button", { name: "New roadmap" }).click();
  await dialog().getByText("Python foundations and software engineering").waitFor();
  await dialog().getByLabel("Serves goal").selectOption({ label: "Complete the AI Engineering roadmap (demo)" });
  await dialog().getByRole("button", { name: "Create roadmap" }).click();
  await page.getByRole("heading", { name: "AI Engineering" }).waitFor();
  await page.getByText("0 of 96 items complete.").waitFor();
});
await shot("roadmap-detail");

await check("roadmap: open stage, add resource, complete item", async () => {
  await page.getByRole("button", { name: /1\. Python foundations/ }).click();
  await page.getByText("Done when:").first().waitFor();
  await page.getByRole("button", { name: "Add resource" }).first().click();
  await dialog().getByLabel(/^Name/).fill("freeCodeCamp: Scientific Computing with Python");
  await dialog().getByLabel("Link", { exact: true }).fill("https://www.freecodecamp.org/learn");
  await dialog().getByRole("button", { name: "Add resource" }).click();
  await dialog().waitFor({ state: "detached" });
  await page.getByRole("link", { name: /freeCodeCamp: Scientific Computing/ }).waitFor();
  await page.getByRole("checkbox", { name: /Complete Learn: Data structures/ }).click();
  await page.getByText("1 of 96 items complete.").waitFor();
});
await shot("roadmap-stage");

await check("project: create and add task with checklist", async () => {
  await go("#/projects");
  await page.getByRole("button", { name: "Create a project" }).click();
  await dialog().getByLabel(/^Name/).fill("FundBridge (demo)");
  await dialog().getByLabel("What is it for?").fill("A demo startup workspace.");
  await dialog().getByRole("radio", { name: "High" }).click();
  await dialog().getByRole("button", { name: "Create project" }).click();
  await page.getByRole("heading", { name: "FundBridge (demo)" }).waitFor();
  await page.getByRole("button", { name: "Task", exact: true }).click();
  await dialog().getByLabel("Title", { exact: true }).fill("Draft the investor one-pager (demo)");
  await dialog().getByRole("button", { name: "Add task" }).click();
  await dialog().waitFor({ state: "detached" });
  await page.getByRole("button", { name: "Draft the investor one-pager (demo)" }).first().click();
  await dialog().getByLabel("New checklist item").fill("Outline the problem");
  await dialog().getByRole("button", { name: "Add", exact: true }).click();
  await dialog().getByText("Outline the problem").waitFor();
  await dialog().getByRole("checkbox", { name: "Outline the problem" }).check();
  await dialog().getByText("Checklist · 1/1").waitFor();
  await shot("task-sheet");
  await dialog().getByRole("button", { name: "Close" }).click();
});
await shot("project-board");

await check("challenges: list and pause/resume", async () => {
  await go("#/challenges");
  await page.getByText("96-day sprint (demo)").waitFor();
  await page.getByRole("button", { name: "Pause" }).first().click();
  await page.getByRole("button", { name: "Resume" }).first().waitFor();
  await page.getByRole("button", { name: "Resume" }).first().click();
  await page.getByRole("button", { name: "Pause" }).first().waitFor();
});
await shot("challenges");

await check("journey: shows the milestone and learning item", async () => {
  await go("#/journey");
  await page.getByText("Finish stages 1–4 (demo)").waitFor();
  await page.getByText("Learn: Data structures, functions and modules").waitFor();
  await page.getByRole("button", { name: "Write" }).click();
  await dialog().getByLabel("Kind", { exact: true }).selectOption("decision");
  await dialog().getByLabel("Title", { exact: true }).fill("Chose AI engineering as my direction (demo)");
  await dialog().getByRole("button", { name: "Save" }).click();
  await page.getByText("Chose AI engineering as my direction (demo)").waitFor();
});
await shot("journey");

await check("me hub and plan hub populated", async () => {
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Me" }).click();
  await page.getByRole("link", { name: /My Journey/ }).waitFor();
  await shot("me");
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Plan" }).click();
  await page.getByText("1 active").waitFor();
});
await shot("plan-filled");

await check("tasks, schedule, insights, profile still load", async () => {
  for (const [hash, locate] of [
    ["#/tasks", () => page.getByRole("heading").first()],
    ["#/schedule", () => page.getByRole("tablist", { name: "Calendar view" })],
    ["#/insights", () => page.getByRole("heading").first()],
    ["#/profile", () => page.getByRole("heading").first()],
  ]) {
    await go(hash);
    await locate().waitFor({ timeout: 8000 });
    await shot(hash.slice(2));
  }
});

await check("refresh keeps state", async () => {
  await go("#/goals");
  await page.reload();
  await page.getByText("Complete the AI Engineering roadmap (demo)").waitFor();
});

const meaningful = errors.filter((text) => !/403|401|Forbidden/.test(text));
results.push({ check: "no console errors", pass: meaningful.length === 0, detail: meaningful.slice(0, 5).join(" | ") });
console.log(JSON.stringify(results, null, 1));
console.log(`PASSED ${results.filter((r) => r.pass).length}/${results.length}`);
await browser.close();
