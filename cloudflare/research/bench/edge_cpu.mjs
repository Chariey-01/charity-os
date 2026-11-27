// CPU of the Worker's own code per request, on V8 (Node 24), network mocked.
import { handleRequest } from "../../src/edge.js";
const html = "<!doctype html>" + "x".repeat(1100);
const env = {
  BACKEND_ORIGIN: "https://charityos-api.example.app",
  EDGE_PROXY_SECRET: "Yb7Kq2Lm9Nv4Rx8Tz1Wc6Pd3Hf5Js0Ga-Ue_Io7By2",
  ASSETS: { fetch: async () => new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } }) },
};
globalThis.fetch = async () => Response.json({ status: "ok", items: Array.from({ length: 30 }, (_, i) => ({ id: i, title: "task " + i })) });
const site = "https://charityos.example.workers.dev";
const cases = {
  "app shell (asset)": () => new Request(`${site}/`),
  "API GET (proxied)": () => new Request(`${site}/api/v1/tasks`, { headers: { Cookie: "sessionid=abc; csrftoken=xyz", "CF-Connecting-IP": "196.201.214.7" } }),
  "API POST with body (proxied)": () => new Request(`${site}/api/v1/tasks`, { method: "POST", body: JSON.stringify({ title: "Read chapter 4", estimated_minutes: 30 }), headers: { "Content-Type": "application/json", Cookie: "sessionid=abc; csrftoken=xyz", "X-CSRFToken": "xyz", "CF-Connecting-IP": "196.201.214.7" } }),
};
for (const [label, make] of Object.entries(cases)) {
  const first = process.cpuUsage();
  await (await handleRequest(make(), env)).arrayBuffer();
  const cold = process.cpuUsage(first);
  for (let i = 0; i < 200; i++) await (await handleRequest(make(), env)).arrayBuffer();
  const n = 2000, start = process.cpuUsage();
  for (let i = 0; i < n; i++) await (await handleRequest(make(), env)).arrayBuffer();
  const used = process.cpuUsage(start);
  console.log(`${label.padEnd(30)} first call ${((cold.user + cold.system) / 1000).toFixed(2)} ms CPU; warm mean ${((used.user + used.system) / 1000 / n).toFixed(3)} ms CPU (includes building the test request and mocks)`);
}
