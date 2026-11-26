/**
 * public/sw.js, executed for real against in-memory caches and a scripted
 * network: offline launch, server errors, interrupted deployments and
 * version changes must never leave the installed app without a working shell.
 */
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

// Vitest runs from frontend/ (npm test, CI); the file is served as-is from public/.
const SOURCE = readFileSync(`${process.cwd()}/public/sw.js`, "utf8");
const ORIGIN = "https://app.test";
const CACHE = "charityos-shell-v2";

type Handler = () => Response | Promise<Response>;
type Listener = (event: Record<string, unknown>) => void;

const page = (...assets: string[]) =>
  `<!doctype html><html><head>${assets.map((asset) => (asset.endsWith(".css") ? `<link rel="stylesheet" href="${asset}">` : `<script type="module" src="${asset}"></script>`)).join("")}</head><body><div id="root"></div></body></html>`;
const html = (body: string, status = 200) => new Response(body, { status, headers: { "Content-Type": "text/html; charset=utf-8" } });
const ok = (body = "x") => new Response(body, { status: 200 });

function worker() {
  const routes: Record<string, Handler> = {};
  let offline = false;
  const store = new Map<string, Map<string, Response>>();
  const path = (request: unknown) =>
    new URL(typeof request === "string" ? request : (request as { url: string }).url, ORIGIN).pathname;
  const network = async (request: unknown) => {
    if (offline) throw new TypeError("Failed to fetch");
    const handler = routes[path(request)];
    return handler ? handler() : new Response("Not found", { status: 404 });
  };
  const cache = (name: string) => {
    if (!store.has(name)) store.set(name, new Map());
    const entries = store.get(name)!;
    return {
      match: async (request: unknown) => entries.get(path(request))?.clone(),
      put: async (request: unknown, response: Response) => void entries.set(path(request), response.clone()),
      addAll: async (requests: string[]) => {
        const responses = await Promise.all(requests.map(network));
        if (responses.some((response) => !response.ok)) throw new TypeError("addAll: a response was not ok");
        requests.forEach((request, index) => entries.set(path(request), responses[index]));
      },
      keys: async () => [...entries.keys()].map((key) => ({ url: ORIGIN + key })),
      delete: async (request: unknown) => entries.delete(path(request)),
    };
  };
  const caches = { open: async (name: string) => cache(name), keys: async () => [...store.keys()], delete: async (name: string) => store.delete(name) };
  const listeners: Record<string, Listener> = {};
  const self = {
    addEventListener: (type: string, listener: Listener) => (listeners[type] = listener),
    location: { origin: ORIGIN },
    skipWaiting: async () => undefined,
    clients: { claim: async () => undefined },
  };
  new Function("self", "caches", "fetch", SOURCE)(self, caches, network);

  return {
    routes,
    store,
    goOffline: () => (offline = true),
    async lifecycle(type: "install" | "activate") {
      const waits: Promise<unknown>[] = [];
      listeners[type]({ waitUntil: (promise: Promise<unknown>) => waits.push(promise) });
      await Promise.all(waits);
    },
    async request(pathname: string, mode = "no-cors", method = "GET") {
      const waits: Promise<unknown>[] = [];
      let responded: Promise<Response> | undefined;
      listeners.fetch({
        request: { url: ORIGIN + pathname, method, mode },
        respondWith: (promise: Promise<Response>) => (responded = promise),
        waitUntil: (promise: Promise<unknown>) => waits.push(promise),
      });
      const response = responded ? await responded : undefined;
      await Promise.all(waits);
      return response;
    },
    async shell() {
      return (await store.get(CACHE)?.get("/")?.clone().text()) ?? null;
    },
    cached: (pathname: string) => store.get(CACHE)?.has(pathname) ?? false,
  };
}

function deployed(sw: ReturnType<typeof worker>, build: string) {
  const js = `/assets/index-${build}.js`;
  const css = `/assets/index-${build}.css`;
  sw.routes["/"] = () => html(page(js, css));
  sw.routes[js] = () => ok(`js ${build}`);
  sw.routes[css] = () => ok(`css ${build}`);
  return { js, css };
}

let sw: ReturnType<typeof worker>;

beforeEach(async () => {
  sw = worker();
  for (const icon of ["/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon.svg"]) sw.routes[icon] = () => ok();
});

describe("service worker", () => {
  it("installs the shell with every asset it needs, so the first offline launch works", async () => {
    const v1 = deployed(sw, "v1");
    await sw.lifecycle("install");

    expect(await sw.shell()).toContain(v1.js);
    expect(sw.cached(v1.js) && sw.cached(v1.css)).toBe(true);

    sw.goOffline();
    const response = await sw.request("/", "navigate");
    expect(response!.status).toBe(200);
    expect(await response!.text()).toContain(v1.js);
    expect(await (await sw.request(v1.js))!.text()).toBe("js v1");
  });

  it("refuses to install from an incomplete deployment", async () => {
    sw.routes["/"] = () => html(page("/assets/missing.js"));

    await expect(sw.lifecycle("install")).rejects.toThrow(/incomplete/);
    expect(await sw.shell()).toBeNull();
  });

  it("serves the last good shell when the server answers with an error, and never caches the error", async () => {
    const v1 = deployed(sw, "v1");
    await sw.lifecycle("install");
    sw.routes["/"] = () => html("<h1>502 Bad Gateway</h1>", 502);

    const response = await sw.request("/", "navigate");

    expect(response!.status).toBe(200);
    expect(await response!.text()).toContain(v1.js);
    expect(await sw.shell()).toContain(v1.js);
  });

  it("keeps the last good shell when a deployment is only half finished", async () => {
    const v1 = deployed(sw, "v1");
    await sw.lifecycle("install");
    sw.routes["/"] = () => html(page("/assets/index-v2.js")); // index is new, its asset is not there yet

    const fresh = await sw.request("/", "navigate");
    expect(await fresh!.text()).toContain("index-v2.js"); // the page sees the network as it is
    expect(await sw.shell()).toContain(v1.js); // but the offline shell is untouched

    sw.goOffline();
    expect(await (await sw.request("/", "navigate"))!.text()).toContain(v1.js);
  });

  it("adopts a complete new deployment and prunes the old build's assets", async () => {
    const v1 = deployed(sw, "v1");
    await sw.lifecycle("install");
    const v2 = deployed(sw, "v2");

    await sw.request("/", "navigate");

    expect(await sw.shell()).toContain(v2.js);
    expect(sw.cached(v2.js) && sw.cached(v2.css)).toBe(true);
    expect(sw.cached(v1.js) || sw.cached(v1.css)).toBe(false);
  });

  it("does not cache failed asset responses", async () => {
    deployed(sw, "v1");
    await sw.lifecycle("install");
    sw.routes["/assets/late.js"] = () => new Response("boom", { status: 500 });

    expect((await sw.request("/assets/late.js"))!.status).toBe(500);
    expect(sw.cached("/assets/late.js")).toBe(false);

    sw.routes["/assets/late.js"] = () => ok("late");
    expect(await (await sw.request("/assets/late.js"))!.text()).toBe("late");
    expect(sw.cached("/assets/late.js")).toBe(true);
  });

  it("never touches the API, the admin, static files or writes", async () => {
    deployed(sw, "v1");
    await sw.lifecycle("install");

    expect(await sw.request("/api/v1/tasks", "cors")).toBeUndefined();
    expect(await sw.request("/admin/", "navigate")).toBeUndefined();
    expect(await sw.request("/static/admin/css/base.css")).toBeUndefined();
    expect(await sw.request("/", "navigate", "POST")).toBeUndefined();
    expect([...sw.store.get(CACHE)!.keys()].some((key) => key.startsWith("/api/"))).toBe(false);
  });

  it("removes the caches of older versions when it activates", async () => {
    sw.store.set("charityos-shell-v2", new Map([["/", html("old")]]));
    deployed(sw, "v2");
    await sw.lifecycle("install");
    await sw.lifecycle("activate");

    expect([...sw.store.keys()]).toEqual([CACHE]);
  });
});
