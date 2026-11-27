// Records a product demonstration of CharityOS with clearly labelled demo data.
//   node demo.mjs <base-url> <password-file> <out-dir>
import { mkdirSync, readFileSync, renameSync, readdirSync } from "node:fs";
import { chromium } from "playwright-core";

const [base, pwFile, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const password = readFileSync(pwFile, "utf8").trim();
const size = { width: 390, height: 844 };
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true });
const context = await browser.newContext({
  viewport: size,
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  timezoneId: "Africa/Nairobi",
  locale: "en-GB",
  recordVideo: { dir: `${out}/raw`, size },
});
const page = await context.newPage();
const log = [];
const pause = (ms) => page.waitForTimeout(ms);

async function caption(text, ms = 2600) {
  await page.evaluate((value) => {
    let bar = document.getElementById("demo-caption");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "demo-caption";
      bar.setAttribute("aria-hidden", "true");
      bar.style.cssText =
        "position:fixed;left:10px;right:10px;top:10px;z-index:9999;padding:10px 12px 10px 14px;border-radius:14px;background:rgba(20,35,28,.92);color:#fff;font:600 14px/1.35 Inter,system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25);pointer-events:none;transition:opacity .25s";
      document.body.appendChild(bar);
      const badge = document.createElement("div");
      badge.id = "demo-badge";
      badge.setAttribute("aria-hidden", "true");
      badge.textContent = "DEMO DATA";
      badge.style.cssText =
        "position:fixed;right:10px;bottom:76px;z-index:9999;padding:3px 8px;border-radius:999px;background:#f2cc79;color:#3a2a00;font:800 10px/1.4 Inter,system-ui,sans-serif;letter-spacing:.08em;pointer-events:none";
      document.body.appendChild(badge);
    }
    bar.textContent = value;
    bar.style.opacity = value ? "1" : "0";
  }, text);
  await pause(ms);
}
const go = async (hash) => {
  await page.evaluate((h) => (window.location.hash = h), hash);
  await pause(900);
};
const dialog = () => page.getByRole("dialog");
async function type(locator, text) {
  await locator.click();
  await locator.pressSequentially(text, { delay: 28 });
}
async function scene(name, fn) {
  try {
    await fn();
    log.push(`ok   ${name}`);
  } catch (err) {
    log.push(`FAIL ${name}: ${String(err.message).split("\n")[0]}`);
    await page.screenshot({ path: `${out}/fail-${name.replace(/\W+/g, "-")}.png` }).catch(() => {});
    for (let i = 0; i < 3; i += 1) await page.keyboard.press("Escape").catch(() => {});
  }
}

await page.goto(base);
await scene("intro", async () => {
  await caption("CharityOS: a personal operating system for turning a vision into daily action. (Demo account, sample data.)", 3800);
  await type(page.getByLabel("Email"), "demo@example.com");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Primary" }).waitFor();
  await caption("Today: the day at a glance. Up to three primary outcomes, with everything else around them.", 3200);
});

await scene("plan", async () => {
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Plan" }).click();
  await caption("Plan holds the chain: Vision → Goals → Roadmaps and Projects → Tasks.", 3000);
});

await scene("vision", async () => {
  await go("#/vision");
  await caption("My Vision: who you are becoming. Aspirations stay intentions until you record evidence or confirm them yourself.", 3400);
  await page.getByRole("button", { name: "Write my vision" }).click();
  await dialog().getByRole("radio", { name: "Vision" }).click();
  await type(dialog().getByLabel("Title", { exact: true }), "Build useful things and keep growing");
  await type(dialog().getByLabel("Your vision, in your words"), "I build AI products that help people, lead with integrity, and learn every year.");
  await dialog().getByRole("button", { name: "Add", exact: true }).click();
  await dialog().waitFor({ state: "detached" });
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await dialog().getByRole("radio", { name: "Manifestation" }).click();
  await type(dialog().getByLabel("Title", { exact: true }), "I work as an AI engineer on a product team");
  await dialog().getByLabel(/^Theme/).fill("Career");
  await dialog().getByRole("button", { name: "Add", exact: true }).click();
  await dialog().waitFor({ state: "detached" });
  await pause(1500);
});

await scene("goal", async () => {
  await caption("Goals turn an aspiration into a target with dates and milestones.", 2400);
  await page.getByRole("button", { name: /I work as an AI engineer/ }).click();
  await dialog().getByRole("button", { name: "Create a goal" }).click();
  await type(dialog().getByLabel("Goal", { exact: true }), "Complete the AI Engineering roadmap");
  await dialog().getByLabel("Why it matters").fill("It is the path to the work I want to do.");
  await dialog().getByLabel("Target date").fill("2027-06-30");
  await dialog().getByRole("button", { name: "Create goal" }).click();
  await page.getByRole("heading", { name: "Complete the AI Engineering roadmap" }).waitFor();
  await caption("Progress is never guessed: it comes from milestones or measurements.", 2800);
  for (const title of ["Finish stages 1–4", "Ship a RAG portfolio project"]) {
    await type(page.getByLabel("New milestone"), title);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await page.getByText(title).waitFor();
  }
  await page.getByRole("checkbox", { name: "Complete Finish stages 1–4" }).click();
  await caption("Completing a milestone moves the goal to 50%, and it is recorded permanently in My Journey.", 3400);
});

await scene("roadmap", async () => {
  await go("#/roadmaps");
  await caption("Roadmaps: start from the AI Engineering template (16 editable stages) or build your own.", 2600);
  await page.getByRole("button", { name: "New roadmap" }).click();
  await pause(1500);
  await dialog().getByLabel("Serves goal").selectOption({ label: "Complete the AI Engineering roadmap" });
  await dialog().getByRole("button", { name: "Create roadmap" }).click();
  await page.getByRole("heading", { name: "AI Engineering" }).waitFor();
  await page.getByRole("button", { name: /1\. Python foundations/ }).click();
  await caption("Each stage has a purpose, completion criteria, resources, practice and a build project.", 3200);
  await page.mouse.wheel(0, 380);
  await pause(800);
  await page.getByRole("checkbox", { name: /Complete Learn: Data structures/ }).click();
  await pause(1500);
});

await scene("project and task", async () => {
  await go("#/projects");
  await caption("Projects are separate workspaces with their own board, milestones, notes and history.", 2600);
  await page.getByRole("button", { name: "Create a project" }).click();
  await type(dialog().getByLabel(/^Name/), "FundBridge");
  await dialog().getByLabel("What is it for?").fill("Startup workspace: product, pitch and partners.");
  await dialog().getByRole("radio", { name: "High" }).click();
  await dialog().getByRole("button", { name: "Create project" }).click();
  await page.getByRole("heading", { name: "FundBridge" }).waitFor();
  await pause(1200);
  await caption("Tasks carry checklists, due dates, priorities and links to a project, goal or milestone.", 1800);
  await page.getByRole("button", { name: "Task", exact: true }).click();
  await type(dialog().getByLabel("Title", { exact: true }), "Draft the investor one-pager");
  await dialog().getByRole("button", { name: "Add task" }).click();
  await dialog().waitFor({ state: "detached" });
  await page.getByRole("button", { name: "Draft the investor one-pager" }).first().click();
  for (const step of ["Outline the problem", "Add traction numbers"]) {
    await type(dialog().getByLabel("New checklist item"), step);
    await dialog().getByRole("button", { name: "Add", exact: true }).click();
    await dialog().getByText(step).waitFor();
  }
  await dialog().getByRole("checkbox", { name: "Outline the problem" }).check();
  await pause(1500);
});

await scene("focus", async () => {
  const track = dialog().getByLabel(/Track the time under/);
  const options = (await track.locator("option").allTextContents()).slice(1);
  const work = options.find((label) => /^(work|business|startup|career)/i.test(label)) ?? options[0];
  await track.selectOption({ label: work });
  await dialog().getByRole("button", { name: "Start focus" }).click();
  await page.getByRole("region", { name: "Focus session" }).waitFor();
  await caption("Focus sessions record what you actually worked on. The server keeps the time, even across refreshes.", 3600);
  await page.getByRole("button", { name: "Pause focus" }).click();
  await caption("Pause and resume without losing time.", 2000);
  await page.getByRole("button", { name: "Resume focus" }).click();
  await pause(2500);
  await page.getByRole("button", { name: "Finish focus" }).click();
  await type(dialog().getByLabel("Outcome"), "First draft of the one-pager done.");
  await dialog().getByLabel("Learning").fill("Lead with the problem, not the product.");
  await dialog().getByLabel(/Evidence note/).fill("https://github.com/example/fundbridge-pitch");
  await dialog().getByRole("checkbox").check();
  await dialog().getByRole("button", { name: "Save and finish" }).click();
  await caption("Outcome, learning and evidence are saved with the session.", 3000);
});

await scene("journey", async () => {
  await go("#/journey");
  await caption("My Journey: a permanent, dated record of what you finish, learn and decide, year after year.", 4000);
  await page.mouse.wheel(0, 500);
  await pause(1800);
});

await scene("insights", async () => {
  await go("#/insights?view=direction");
  await caption("Insights: which goals, roadmaps and projects are moving, and what keeps slipping. No made-up scores.", 4000);
});

await scene("reminders", async () => {
  await go("#/reminders");
  await caption("Reminders arrive as phone notifications even when the app is closed. Plans can also appear in Google Calendar.", 3800);
  await page.getByRole("button", { name: "New", exact: true }).click();
  await type(dialog().getByLabel("Remind me to"), "Study AI engineering for 45 minutes");
  await dialog().getByRole("radio", { name: "Some days" }).click();
  await dialog().getByLabel("Time").fill("06:30");
  await dialog().getByRole("button", { name: "Set reminder" }).click();
  await dialog().waitFor({ state: "detached" });
  await pause(1500);
});

await scene("partners", async () => {
  await go("#/partners");
  await caption("Optional accountability: share chosen goals with someone you trust. They can encourage you, never edit.", 3800);
});

await scene("outro", async () => {
  await go("#/plan");
  await caption("CharityOS: vision → goals → plans → execution → evidence → growth. Private beta.", 4000);
});

await context.close();
await browser.close();
const raw = readdirSync(`${out}/raw`).find((name) => name.endsWith(".webm"));
if (raw) renameSync(`${out}/raw/${raw}`, `${out}/charityos-demo.webm`);
console.log(log.join("\n"));
