/* CharityOS service worker.
 *
 * Caches only the application shell so the app opens offline. API responses
 * are private and server-authoritative, so /api/, /admin/ and /static/ are
 * never cached or intercepted.
 *
 * The last known-good shell is never replaced by something broken:
 * - only successful (2xx, same-origin) responses are ever cached;
 * - a new index.html replaces the cached one only after every /assets/ file it
 *   references has been fetched successfully, so a half-finished deployment
 *   or a proxy error page cannot become the offline app;
 * - when a page load fails or returns an error, the cached shell is served;
 * - assets the current shell no longer references are pruned.
 */
const VERSION = "charityos-shell-v2";
const ICONS = ["/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon.svg"];
const ASSET = /(?:src|href)="(\/assets\/[^"?#]+)"/g;
const PRIVATE = ["/api/", "/admin/", "/static/"];

function pathOf(request) {
  return new URL(typeof request === "string" ? request : request.url, self.location.origin).pathname;
}

function usable(response) {
  return Boolean(response && response.ok && (response.type === "basic" || response.type === "default"));
}

function assetsOf(html) {
  return [...new Set([...html.matchAll(ASSET)].map((match) => match[1]))];
}

/** Store ``html`` as the shell only if all of its assets load; returns true when it did. */
async function adoptShell(html, headers) {
  const assets = assetsOf(html);
  const fetched = await Promise.all(
    assets.map((path) =>
      fetch(path, { cache: "no-cache" })
        .then((response) => (usable(response) ? response : null))
        .catch(() => null),
    ),
  );
  if (fetched.some((response) => response === null)) return false; // incomplete: keep the old shell
  const cache = await caches.open(VERSION);
  await Promise.all(assets.map((path, index) => cache.put(path, fetched[index])));
  await cache.put("/", new Response(html, { status: 200, headers }));
  const keep = new Set(assets);
  for (const request of await cache.keys()) {
    const path = pathOf(request);
    if (path.startsWith("/assets/") && !keep.has(path)) await cache.delete(request);
  }
  return true;
}

async function refreshShell(response) {
  if (!usable(response) || !(response.headers.get("Content-Type") || "").includes("text/html")) return false;
  const html = await response.text();
  // Unchanged deployment with every asset still cached: nothing to download.
  const cache = await caches.open(VERSION);
  const current = await cache.match("/");
  if (current && (await current.text()) === html) {
    const cached = await Promise.all(assetsOf(html).map((path) => cache.match(path)));
    if (cached.every(Boolean)) return true;
  }
  return adoptShell(html, response.headers);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(VERSION);
      await cache.addAll(ICONS); // rejects on any error response: the old worker stays
      const shell = await fetch("/", { cache: "no-cache" });
      if (!(await refreshShell(shell))) throw new Error("The app shell is incomplete; not installing.");
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

async function cachedShell() {
  const cache = await caches.open(VERSION);
  return cache.match("/");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (PRIVATE.some((prefix) => url.pathname.startsWith(prefix))) return;

  if (request.mode === "navigate") {
    // Network first so deployments show up immediately; the last good shell
    // when offline or when the server answers with an error.
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);
          if (usable(response)) {
            event.waitUntil(refreshShell(response.clone()).catch(() => false));
            return response;
          }
          return (await cachedShell()) || response;
        } catch (error) {
          const shell = await cachedShell();
          if (shell) return shell;
          throw error;
        }
      })(),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/") || url.pathname === "/manifest.webmanifest") {
    // Hashed build assets never change: cache first, and cache only successes.
    event.respondWith(
      (async () => {
        const cache = await caches.open(VERSION);
        const cached = await cache.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (usable(response)) event.waitUntil(cache.put(request, response.clone()));
        return response;
      })(),
    );
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "#/today";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate ? client.navigate(`/${target}`) : null;
          return client.focus();
        }
      }
      return self.clients.openWindow(`/${target}`);
    }),
  );
});

/* ---- Reminders (Web Push). The server decides when; this only shows them. ---- */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "CharityOS", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "CharityOS";
  const options = {
    body: data.body || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: data.tag || undefined,
    renotify: Boolean(data.tag),
    data: { url: data.url || "/#/today", snooze: data.snooze || null },
    actions: data.snooze ? [{ action: "open", title: "Open" }, { action: "snooze", title: "Snooze 10 min" }] : [],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  const { url, snooze } = event.notification.data || {};
  event.notification.close();
  if (event.action === "snooze" && snooze) {
    // The signed token is the only credential; no cookie or CSRF is needed.
    event.waitUntil(
      fetch("/api/v1/push/snooze", {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: snooze, minutes: 10 }),
      }).catch(() => undefined),
    );
    return;
  }
  const target = new URL(url || "/#/today", self.location.origin).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of windows) {
        if (new URL(client.url).origin === self.location.origin) {
          await client.focus();
          if ("navigate" in client) return client.navigate(target).catch(() => undefined);
          return undefined;
        }
      }
      return self.clients.openWindow(target);
    })(),
  );
});
