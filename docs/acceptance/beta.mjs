// Private beta journey with two real browser sessions. Usage:
//   node beta.mjs <base-url> <owner-password-file> <shots-dir>
import { randomBytes } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright-core";

const [base, pwFile, shots] = process.argv.slice(2);
mkdirSync(shots, { recursive: true });
const ownerPw = readFileSync(pwFile, "utf8").trim();
// Throwaway passwords for the accounts this run creates in a test database.
const friendPw = `Friend-${randomBytes(9).toString("base64url")}`;
const resetPw = `Reset-${randomBytes(9).toString("base64url")}`;
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true });
const ctx = () => browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, timezoneId: "Africa/Nairobi" });
const results = [];
let n = 0;
async function check(name, fn) {
  try {
    await fn();
    results.push({ check: name, pass: true });
  } catch (err) {
    results.push({ check: name, pass: false, detail: String(err.message).split("\n")[0] });
  }
}
const shot = (page, name) => page.screenshot({ path: `${shots}/${String(++n).padStart(2, "0")}-${name}.png`, fullPage: true });
const go = async (page, hash) => {
  await page.evaluate((h) => (window.location.hash = h), hash);
  await page.waitForTimeout(600);
};
async function signIn(page, email, password) {
  await page.goto(base);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Primary" }).waitFor();
}

const owner = await (await ctx()).newPage();
const friend = await (await ctx()).newPage();
let inviteUrl = "";

await check("owner signs in and creates an invite", async () => {
  await signIn(owner, "demo@example.com", ownerPw);
  await go(owner, "#/me");
  await owner.getByRole("link", { name: /Beta admin/ }).click();
  await owner.getByLabel(/^Who is it for/).fill("Friend (demo)");
  await owner.getByRole("button", { name: "Create invite" }).click();
  inviteUrl = await owner.getByLabel("Invite link").inputValue();
  if (!inviteUrl.includes("#/signup?code=")) throw new Error(`bad link ${inviteUrl}`);
  await shot(owner, "beta-admin-invite");
});

await check("friend signs up from the invite link", async () => {
  await friend.goto(inviteUrl.replace(/^https?:\/\/[^/]+/, base));
  await friend.getByRole("heading", { name: "Create your account" }).waitFor();
  await shot(friend, "signup");
  await friend.getByLabel(/^Your name/).fill("Demo Friend");
  await friend.getByLabel("Email").fill("friend@example.com");
  await friend.getByLabel("Password", { exact: true }).fill(friendPw);
  await friend.getByLabel("Repeat password").fill(friendPw);
  await friend.getByRole("checkbox").check();
  await friend.getByRole("button", { name: "Create account" }).click();
  await friend.getByRole("navigation", { name: "Primary" }).waitFor();
});

await check("the invite cannot be reused", async () => {
  const third = await (await ctx()).newPage();
  await third.goto(inviteUrl.replace(/^https?:\/\/[^/]+/, base));
  await third.getByLabel("Email").fill("third@example.com");
  await third.getByLabel("Password", { exact: true }).fill(friendPw);
  await third.getByLabel("Repeat password").fill(friendPw);
  await third.getByRole("checkbox").check();
  await third.getByRole("button", { name: "Create account" }).click();
  await third.getByText(/not valid or has been used/).waitFor();
  await third.context().close();
});

await check("owner creates a goal and invites the friend as partner", async () => {
  await go(owner, "#/goals");
  await owner.getByRole("button", { name: "Create your first goal" }).click();
  await owner.getByRole("dialog").getByLabel("Goal", { exact: true }).fill("Finish the RAG project (demo)");
  await owner.getByRole("dialog").getByRole("button", { name: "Create goal" }).click();
  await owner.getByRole("heading", { name: "Finish the RAG project (demo)" }).waitFor();
  await owner.getByLabel("New milestone").fill("Working prototype (demo)");
  await owner.getByRole("button", { name: "Add", exact: true }).click();
  await owner.getByText("Working prototype (demo)").waitFor();
  await go(owner, "#/partners");
  await owner.getByRole("button", { name: "Invite" }).click();
  await owner.getByRole("dialog").getByLabel(/^Their email/).fill("friend@example.com");
  await owner.getByRole("dialog").getByRole("button", { name: "Send invitation" }).click();
  await owner.getByText("Invited · waiting").waitFor();
});

await check("friend accepts", async () => {
  await go(friend, "#/partners");
  await friend.reload();
  await friend.getByRole("button", { name: "Accept" }).click();
  await friend.getByRole("link", { name: /Demo Learner/ }).waitFor();
});

await check("owner chooses the goal to share", async () => {
  await owner.reload();
  await owner.getByRole("button", { name: "Choose what to share" }).click();
  await owner.getByRole("dialog").getByRole("checkbox", { name: "Finish the RAG project (demo)" }).check();
  await owner.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await owner.getByText("1 goal").waitFor();
  await shot(owner, "partners-owner");
});

await check("friend sees only the shared goal, read-only, and cheers", async () => {
  await friend.getByRole("link", { name: /Demo Learner/ }).click();
  await friend.getByText("Finish the RAG project (demo)").waitFor();
  await friend.getByText("Working prototype (demo)").waitFor();
  await shot(friend, "partner-view");
  await friend.getByRole("button", { name: "Encourage" }).first().click();
  await friend.getByRole("dialog").getByLabel(/Message/).fill("Keep going (demo)");
  await friend.getByRole("dialog").getByRole("button", { name: "Send" }).click();
  await friend.getByRole("dialog").waitFor({ state: "detached" });
});

await check("friend's own goal list is empty (no data leaks)", async () => {
  await go(friend, "#/goals");
  await friend.getByText("No active goals yet").waitFor();
  const api = await friend.evaluate(async () => (await fetch("/api/v1/goals")).json());
  if (api.length !== 0) throw new Error(`friend sees ${api.length} goals`);
});

await check("owner sees the cheer", async () => {
  await owner.reload();
  await owner.getByText("Keep going (demo)").waitFor();
});

await check("friend sends feedback; owner reads it", async () => {
  await go(friend, "#/feedback");
  await friend.getByLabel(/What happened/).fill("The board tabs are hard to find on small phones (demo).");
  await friend.getByRole("button", { name: "Send feedback" }).click();
  await friend.getByText(/board tabs are hard to find/).nth(0).waitFor();
  await go(owner, "#/beta");
  await owner.reload();
  await owner.getByText(/board tabs are hard to find/).waitFor();
  await shot(owner, "beta-admin-feedback");
});

await check("password reset link from the owner works", async () => {
  const resetButtons = owner.getByRole("button", { name: "Reset link" });
  await resetButtons.nth(1).click();
  const link = await owner.getByLabel("Reset link").inputValue();
  const stranger = await (await ctx()).newPage();
  await stranger.goto(link.replace(/^https?:\/\/[^/]+/, base));
  await stranger.getByLabel("New password").fill(resetPw);
  await stranger.getByLabel("Repeat it").fill(resetPw);
  await stranger.getByRole("button", { name: "Save password" }).click();
  await stranger.getByRole("heading", { name: "Password changed" }).waitFor();
  await signIn(stranger, "friend@example.com", resetPw);
  await stranger.context().close();
});

console.log(JSON.stringify(results, null, 1));
console.log(`PASSED ${results.filter((r) => r.pass).length}/${results.length}`);
await browser.close();
