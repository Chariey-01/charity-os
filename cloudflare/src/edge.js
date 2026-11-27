/**
 * CharityOS's front door on Cloudflare (Workers Free plan). The Worker entry
 * point is src/worker.js; everything it does lives here so it can be tested.
 *
 * One HTTPS origin, as the PWA and the session-cookie sign-in need:
 *   /api/*, /admin/*, /static/*  -> forwarded to the Django backend
 *   everything else              -> the built PWA (frontend/dist, static assets)
 *
 * The backend has a public address of its own, so it only answers requests
 * carrying EDGE_PROXY_SECRET (backend/config/edge_proxy.py). This Worker adds
 * that secret and the visitor's address (CF-Connecting-IP), after removing any
 * copies a visitor sent. Cookies, CSRF headers and bodies pass through
 * unchanged; Django still does all authentication, CSRF and rate limiting.
 *
 * Headers for the app shell mirror backend/config/frontend.py, which serves
 * the same files when Django hosts the PWA itself (tests keep them equal).
 * See docs/operations/cloudflare-deployment.md.
 */

export const PROXIED_PREFIXES = ["/api/", "/admin/", "/static/"];
export const EDGE_SECRET_HEADER = "X-CharityOS-Edge-Secret";
export const CLIENT_IP_HEADER = "X-CharityOS-Client-IP";

// Mirrors CONTENT_SECURITY_POLICY in backend/config/frontend.py.
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "manifest-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const NO_CACHE = new Set(["/", "/index.html", "/sw.js", "/manifest.webmanifest"]);
// Vite names hashed files like /assets/index-BSiiNENh.js (frontend.py's regex).
const HASHED_ASSET = /^\/assets\/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$/;
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
]);
// Never let a visitor supply these: the backend believes only what this Worker sets.
const STRIPPED_PREFIXES = ["x-charityos-", "x-forwarded-", "cf-", "x-real-ip", "forwarded"];
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function isProxied(pathname) {
  return pathname === "/admin" || PROXIED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

/** The backend origin, refusing anything but https (plain http only on loopback). */
export function backendOrigin(env) {
  let origin;
  try {
    origin = new URL(env.BACKEND_ORIGIN);
  } catch {
    throw new Error("BACKEND_ORIGIN is not set to a URL");
  }
  if (origin.protocol !== "https:" && !(origin.protocol === "http:" && LOCAL_HOSTS.has(origin.hostname))) {
    throw new Error("BACKEND_ORIGIN must be https://");
  }
  if (origin.pathname !== "/" || origin.search || origin.username) {
    throw new Error("BACKEND_ORIGIN must be an origin only, e.g. https://api.example.org");
  }
  return origin;
}

function edgeSecret(env) {
  const secret = env.EDGE_PROXY_SECRET || "";
  if (secret.length < 32) throw new Error("EDGE_PROXY_SECRET is missing or too short");
  return secret;
}

/** The request to send to Django for a visitor's /api, /admin or /static request. */
export function upstreamRequest(request, env) {
  const url = new URL(request.url);
  const target = new URL(url.pathname + url.search, backendOrigin(env));
  const headers = new Headers();
  for (const [name, value] of request.headers) {
    const lower = name.toLowerCase();
    if (HOP_BY_HOP.has(lower) || STRIPPED_PREFIXES.some((prefix) => lower.startsWith(prefix))) continue;
    headers.append(name, value);
  }
  headers.set("X-Forwarded-Proto", "https");
  headers.set(EDGE_SECRET_HEADER, edgeSecret(env));
  const visitor = request.headers.get("CF-Connecting-IP");
  if (visitor) headers.set(CLIENT_IP_HEADER, visitor);
  const hasBody = !["GET", "HEAD"].includes(request.method);
  return new Request(target, {
    method: request.method,
    headers,
    redirect: "manual",
    ...(hasBody ? { body: request.body, duplex: "half" } : {}),
  });
}

/** Django's response for the visitor; a redirect to the backend's own host points back here. */
export function visitorResponse(response, publicOrigin, env) {
  const headers = new Headers(response.headers);
  const location = headers.get("Location");
  // Relative redirects already stay on the site; only absolute ones can leak
  // the backend's address.
  if (location && /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(location)) {
    const backend = backendOrigin(env);
    const target = new URL(location, backend);
    if (target.origin === backend.origin) {
      headers.set("Location", publicOrigin + target.pathname + target.search + target.hash);
    }
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

/** Cache and security headers for the PWA's files (see frontend.py's docstring). */
export function assetHeaders(pathname, headers) {
  const out = new Headers(headers);
  if (NO_CACHE.has(pathname)) {
    out.set("Cache-Control", "no-cache");
  } else if (HASHED_ASSET.test(pathname)) {
    out.set("Cache-Control", "public, max-age=31536000, immutable");
  } else if (!out.has("Cache-Control")) {
    out.set("Cache-Control", "public, max-age=60");
  }
  if (pathname.endsWith(".webmanifest")) out.set("Content-Type", "application/manifest+json");
  const contentType = out.get("Content-Type") || "";
  if (contentType.startsWith("text/html")) {
    out.set("Content-Security-Policy", CONTENT_SECURITY_POLICY);
    out.set("X-Frame-Options", "DENY");
  }
  out.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  out.set("X-Content-Type-Options", "nosniff");
  out.set("Referrer-Policy", "same-origin");
  out.set("Cross-Origin-Opener-Policy", "same-origin");
  return out;
}

function unavailable() {
  // The PWA treats this like being offline and retries by itself.
  const message = "CharityOS's server cannot be reached right now. Try again in a moment.";
  return Response.json(
    { detail: message, error: { code: "backend_unavailable", message } },
    { status: 503, headers: { "Cache-Control": "no-store", "Retry-After": "5" } },
  );
}

/**
 * Digital Asset Links for the Android app (a Trusted Web Activity built with
 * Bubblewrap, docs/android-app.md). Android checks this file to confirm the
 * app and the site belong together; then the app opens without a browser bar.
 * The certificate fingerprint is public by design.
 */
export function assetLinks(env) {
  const packageName = env.ANDROID_PACKAGE || "";
  const fingerprints = String(env.ANDROID_CERT_SHA256 || "")
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter((value) => /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/.test(value));
  if (!packageName || !fingerprints.length) return [];
  return [
    {
      relation: ["delegate_permission/common.handle_all_urls"],
      target: { namespace: "android_app", package_name: packageName, sha256_cert_fingerprints: fingerprints },
    },
  ];
}

export async function handleRequest(request, env) {
  const url = new URL(request.url);
  if (url.protocol === "http:" && !LOCAL_HOSTS.has(url.hostname)) {
    url.protocol = "https:";
    return Response.redirect(url.toString(), 301);
  }
  if (url.pathname === "/.well-known/assetlinks.json") {
    return Response.json(assetLinks(env), {
      headers: { "Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff" },
    });
  }
  if (isProxied(url.pathname)) {
    let upstream;
    try {
      upstream = upstreamRequest(request, env);
    } catch (error) {
      console.error(`charityos-edge misconfigured: ${error.message}`);
      return unavailable();
    }
    try {
      const response = await fetch(upstream);
      return visitorResponse(response, url.origin, env);
    } catch (error) {
      console.error(`charityos-edge backend unreachable: ${error.name}`);
      return unavailable();
    }
  }
  const asset = await env.ASSETS.fetch(request);
  return new Response(asset.body, {
    status: asset.status,
    statusText: asset.statusText,
    headers: assetHeaders(url.pathname, asset.headers),
  });
}
