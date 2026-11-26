# Private PWA release checklist

CharityOS is installed on a phone as a Progressive Web App: from Chrome, over HTTPS. There is no APK.

**Status (26 Nov 2026): not installable yet.** Nothing is deployed. An install works only from an HTTPS address, so the app cannot be installed until a deployment is approved, completed, and passes the tests in section 4. Do not tell anyone it can be downloaded before then.

Sections 1–3 come from reading the code on `integration/phase-0`. Section 4 must be run on a real Android phone against the deployed site.

## 1. What is already in place (verified in code)

| Area | Where | State |
|---|---|---|
| Web app manifest | `frontend/public/manifest.webmanifest`, linked from `index.html` | Present. Fields: `id: /`, name and short name `CharityOS`, `start_url: /#/today`, `scope: /`, `display: standalone`, theme `#173f31`, background `#f4f3ee`. It has two shortcuts, Quick add and Schedule. |
| Icons | `frontend/public/icons/` | Present: 192 and 512 PNG (`any`), 512 PNG (`maskable`), SVG, and a 180 Apple touch icon. These cover Chrome's install requirements. |
| Service worker | `frontend/public/sw.js`, registered by `src/lib/pwa.ts` | Registered at `/sw.js` with scope `/`, in production builds only. |
| Offline app shell | `sw.js` | Pages load network-first, falling back to the cached `/` when offline. Hashed `/assets/` and `/icons/` load cache-first. |
| Offline behaviour | `src/lib/api.ts:55` | API calls made offline say "You appear to be offline. Changes need a connection." Nothing is queued or written offline. |
| API caching safety | `sw.js:24-25` | The worker never handles `/api/`, `/admin/`, non-GET requests or other origins. Personal data is never stored in the service-worker cache. |
| Install prompt | `src/lib/pwa.ts`, Profile | It shows Chrome's install prompt when the browser offers one. On iOS, use Share → Add to Home Screen. |
| Viewport | `index.html`, `src/index.css` | `width=device-width, initial-scale=1, viewport-fit=cover`. Safe-area insets are used for the top and bottom bars. Acceptance screenshots at 360–430 px wide and in dark mode are in `docs/acceptance/screenshots/`. |
| HTTPS | `config/settings/production.py` | HTTPS redirect, secure session and CSRF cookies, HSTS for 1 year with subdomains and preload |
| Sessions | `config/settings/base.py` | Cookie session, `HttpOnly`, `SameSite=Lax`, `Secure` in production. Django's default lifetime is 2 weeks. |
| Reminders | README "Reminders and installation" | Foreground only. A PWA cannot wake itself without Web Push, and Web Push is not implemented. |

## 2. Fix before the install test

| ID | Severity | Finding | Fix |
|---|---|---|---|
| SW1 | Medium | The page handler in `sw.js` stores **every** page response as the offline shell, without checking `response.ok`. A 502 from the proxy during a redeploy, or a 404 page, would replace the offline shell, and the app would then open offline to an error page. | Cache only when `response.ok` is true. This is a one-line change; test it with an offline launch after a deliberate 502. |
| AU1 | Low (for personal use) | When a session expires while the app is open, API calls return 403 and each screen shows an error toast. The app returns to sign-in only after a reload. | Handle 401 and 403 "not authenticated" in one place in `src/lib/api.ts`, and switch to the sign-in screen. |

## 3. Worth doing; not blocking a personal install

| ID | Finding | Suggestion |
|---|---|---|
| SW2 | The cache name `charityos-shell-v1` never changes, so old hashed assets pile up across deploys. | Delete `/assets/` entries the current `index.html` no longer references, or include the build hash in the cache name. |
| SW3 | On the very first visit, the page's assets load before the worker takes control, so they are not cached. Offline works from the second launch. | Accept this, or pre-cache the build's asset list. Test step 4.3 accounts for it. |
| HD1 | The server's headers decide how quickly updates reach the phone. | Serve `index.html`, `sw.js` and `manifest.webmanifest` with `Cache-Control: no-cache`, `/assets/*` with `Cache-Control: public, max-age=31536000, immutable`, and `sw.js` as `text/javascript`. |
| HS1 | `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` are hard to undo. | Use a dedicated domain or subdomain. Do not submit the domain to the browser preload list until the setup is stable. |

## 4. Install test on Android (run after deployment)

Use Chrome on a real Android phone, against the HTTPS address. Record the phone model, Android and Chrome versions, the deployed commit, and pass or fail for each step.

| # | Step | Pass when |
|---|---|---|
| 4.1 | Open the HTTPS address in Chrome | The app loads with no certificate warning. DevTools (via `chrome://inspect`) → Application → Manifest shows no errors, and the service worker is "activated and running". |
| 4.2 | Chrome menu → **Install app** (or **Add to Home screen** → Install), or Profile → Install | The icon appears on the home screen and in the app drawer. It is not a browser shortcut and has no Chrome badge. |
| 4.3 | Open it from the icon, use it, close it, then open it once more | It opens standalone, with no address bar, on Today. The status bar uses the theme colour. |
| 4.4 | Turn on aeroplane mode and open the app | The shell opens and the offline message is shown. No crash, no Chrome "dinosaur" page. |
| 4.5 | Sign out, then sign in | Sign-in works over HTTPS. After signing out, no personal data is visible, including after reopening the app offline. |
| 4.6 | Expire the session (delete it in the admin, or wait), then use the app | With AU1 fixed: the app returns to sign-in. Without it: error toasts, then sign-in after a reload. |
| 4.7 | Deploy a visible change, then reopen the installed app | The change appears on the next launch, or after at most one more. |
| 4.8 | Allow notifications and set a reminder; keep the app open | The reminder appears. Expected limitation: none appear while the app is closed. |
| 4.9 | Long-press the icon | The Quick add and Schedule shortcuts open the right screens. |
| 4.10 | Rotate the phone and use the narrowest common width (360 px) | Nothing overlaps the bottom bar or the notch area. |
| 4.11 | Uninstall | It uninstalls cleanly. Data stays on the server. |

**The app is "downloadable" only after 4.1–4.5 pass on a deployed HTTPS site.**
