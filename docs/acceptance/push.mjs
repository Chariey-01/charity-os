// Real Web Push: Chrome subscribes via its push service, the backend sends,
// the service worker shows the notification. Usage:
//   node push.mjs <base-url> <password-file> <shots-dir>
// Service workers need a secure context: http://localhost qualifies.
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright-core";

const [base, pwFile, shots] = process.argv.slice(2);
mkdirSync(shots, { recursive: true });
const password = readFileSync(pwFile, "utf8").trim();
// A fresh Chrome profile per run, inside the shots directory.
const userDataDir = `${shots}/profile-${Date.now()}`;
const context = await chromium.launchPersistentContext(userDataDir, {
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  viewport: { width: 390, height: 844 },
  permissions: ["notifications"],
  args: ["--enable-features=PushMessaging"],
});
const page = context.pages()[0] ?? (await context.newPage());
const results = [];
const log = (check, pass, detail = "") => results.push({ check, pass, detail });
page.on("console", (msg) => msg.type() === "error" && console.log("console:", msg.text()));

await page.goto(base);
await page.getByLabel("Email").fill("demo@example.com");
await page.getByLabel("Password").fill(password);
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByRole("navigation", { name: "Primary" }).waitFor();
await page.evaluate(() => (window.location.hash = "#/reminders"));
await page.getByRole("heading", { name: "Reminders" }).first().waitFor();

const turnOn = page.getByRole("button", { name: "Turn on notifications" });
await turnOn.waitFor({ timeout: 15000 }).catch(() => {});
if (!(await turnOn.isVisible())) {
  log("turn-on button visible", false, await page.locator("#notify-title").locator("..").innerText());
} else {
  await turnOn.click();
  let toast = [];
  for (let i = 0; i < 80 && !toast.length; i += 1) {
    await page.waitForTimeout(500);
    toast = await page.locator(".toast").allInnerTexts();
  }
  const ok = await page.getByText("On for this device.").waitFor({ timeout: 20000 }).then(() => true, () => false);
  const state = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.getRegistration();
    return {
      permission: Notification.permission,
      registered: Boolean(reg),
      installing: Boolean(reg?.installing),
      waiting: Boolean(reg?.waiting),
      active: reg?.active?.state ?? null,
      controller: Boolean(navigator.serviceWorker.controller),
    };
  });
  log("subscribe through Chrome's push service", ok, `${toast.join(" | ")} ${JSON.stringify(state)}`);
  const endpoint = await page.evaluate(async () => (await (await navigator.serviceWorker.ready).pushManager.getSubscription())?.endpoint ?? null);
  log("subscription endpoint host", Boolean(endpoint), endpoint ? new URL(endpoint).hostname : "none");
  if (ok) {
    await page.getByRole("button", { name: "Send a test" }).click();
    let shown = [];
    for (let i = 0; i < 30 && !shown.length; i += 1) {
      await page.waitForTimeout(1000);
      shown = await page.evaluate(async () => (await (await navigator.serviceWorker.ready).getNotifications()).map((n) => ({ title: n.title, body: n.body, actions: (n.actions || []).map((a) => a.action) })));
    }
    log("notification delivered and shown by the service worker", shown.length > 0, JSON.stringify(shown));
  }
}
await page.screenshot({ path: `${shots}/push-reminders-390.png`, fullPage: true });
console.log(JSON.stringify(results, null, 1));
await context.close();
