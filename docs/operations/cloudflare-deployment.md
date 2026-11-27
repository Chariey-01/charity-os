# Cloudflare-first deployment ($0 a month)

Written 27 Nov 2026 for the owner. Prices and limits were read from the providers' own pages that day; recheck them before signing up.

**Status: prepared and proven locally, not deployed.** No account has been created, nothing has been bought, and nothing is public. Every "Passed" below was run on the laptop; nothing here has run on Cloudflare's, Vercel's or Neon's servers yet.

Related pages:
- [production runbook](production-runbook.md): the paid single-host alternative (Render, about USD 13.30 a month), already prepared.
- [backup and restore](backup-and-restore.md): the `ops/db` scripts used below.
- [migrations](../migrations.md): how each migration is reversed.

## 1. What runs where

```
Phone (Chrome, installed PWA)
   │ HTTPS, one origin: https://charityos.<your-subdomain>.workers.dev
   ▼
Cloudflare Worker "charityos"  (Workers Free; cloudflare/)
   ├─ /, /assets/*, /icons/*, sw.js, manifest  → the built PWA (static assets, free)
   └─ /api/*, /admin/*, /static/*              → forwarded over HTTPS, adding
        │                                        X-CharityOS-Edge-Secret and the
        │                                        visitor's address
        ▼
Django backend  (Vercel Hobby, Python 3.12; backend/)
   answers only requests carrying the secret (config/edge_proxy.py)
        │ TLS (verify-full + channel binding)
        ▼
PostgreSQL 16  (Neon Free, Frankfurt; pooled endpoint)
```

- **One origin.** The browser only ever talks to the Worker, so session cookies stay first-party, there is no CORS, and the service worker and CSRF protection work exactly as they do today.
- **Django is unchanged.** It runs on native CPython 3.12 with psycopg, the same as in the tests. Only two settings are new: `CHARITYOS_FRONTEND=external` and `CHARITYOS_EDGE_PROXY_SECRET`.
- **The backend can't be used around Cloudflare.** Vercel gives the backend a public address of its own. Without the shared secret it answers 403 to everything except the health probe. Cloudflare sets `CF-Connecting-IP` itself, and the Worker passes it on. That keeps per-visitor login lockouts and the security log accurate. Anything a visitor sends in those headers is thrown away.

## 2. Why not Django on Cloudflare Workers itself

That was the preferred design. It was tested and **failed on the Free plan**: CharityOS needs 10 to 150 times more CPU per request than the plan allows. The test ran the real CharityOS Django code inside Cloudflare's Python Workers runtime (`workerd` via `pywrangler dev`, Python 3.14.2 on Pyodide/WebAssembly), with production settings and a Hyperdrive binding to Postgres. The harness is in [`cloudflare/research/`](../../cloudflare/research/README.md).

Workers Free allows **10 ms of CPU per request** (Cloudflare limits page). Measured on this laptop (Intel i7-7600U, 2017), median of 5 runs:

| Operation | Python Worker CPU | Native Django CPU, new connection | Native Django CPU, kept connection |
|---|---:|---:|---:|
| 1. Health | 143 ms | 16 ms | 4 ms |
| 2. Sign in (password check) | **1,545 ms** | 1,000 ms | 973 ms |
| 3. Authenticated `GET /me` | 125 ms | 39 ms | 11 ms |
| 4. Create task | 113 ms | 73 ms | 48 ms |
| 5. Update task | 142 ms | 64 ms | 34 ms |
| 6. List workstreams | 182 ms | 53 ms | 29 ms |
| 7. Today's schedule | 208 ms | 125 ms | 122 ms |
| 8. Start / finish focus | 165 / 221 ms | 90 / 75 ms | 50 / 41 ms |
| 9. Weekly progress | 245 ms | 173 ms | 138 ms |
| 10. Weekly reviews list / save | 193 / 218 ms | 57 / 69 ms | 20 / 38 ms |

CPU is the server thread's own time from `/proc/<pid>/task/*/schedstat`. It is not wall time, and it excludes database time. Wall time and the remainder ("waiting") are in the result files. Breakdown inside the Python Worker:
- runtime alone, without Django: 4–12 ms;
- Django's middleware with no database: 11–29 ms;
- opening the per-request database connection: 50–160 ms;
- the password hash alone: 1,380–1,545 ms.

**Conclusions:**
- **No optimisation fixes this within the rules.** Sign-in costs about 1 s of CPU even natively, because Django hashes passwords with PBKDF2-SHA256 at 1,000,000 iterations, on purpose. Lowering that would weaken password security, which is not allowed. Cloudflare's servers are faster than this laptop, but not 100× faster.
- **Five compatibility problems had to be worked around before it ran at all:**
  1. Hyperdrive's details can't be read at start-up.
  2. psycopg 3.2.10 has no WebAssembly build; Pyodide's 3.3.5 had to be used.
  3. Django refuses synchronous database calls in the async handler; requests have to be serialised with a lock.
  4. The runtime's `hashlib` has no `pbkdf2_hmac`, so Django's default password hasher fails. A same-format hasher using `cryptography` is needed.
  5. There's no time-zone database; `tzdata` had to be added.
- **With those fixes, all 10 operations worked locally.** The Python Worker used 62 MiB of WebAssembly memory, inside the 128 MB limit. It ran Python 3.14 and psycopg 3.3.5, not the 3.12 and 3.2.10 the test suite runs on.
- **On Workers Paid (USD 5 a month: 30 s of CPU per request, 30 million CPU-ms included) it would fit.** That is the "Cloudflare-only" fallback in section 4. It carries more risk, because the runtime differs from what the tests cover.

The Worker in the recommended design does far less work. Its own code costs **about 0.1 ms of CPU per request** (V8, measured with `cloudflare/research/bench/edge_cpu.mjs`), roughly 100× under the Free limit.

## 3. Compatibility and test results

| Check | Result | Evidence |
|---|---|---|
| Django 5.2 + DRF + django-axes in Python Workers (local workerd) | Passed, after 5 compatibility fixes (section 2) | `cloudflare/research/python-worker/` |
| Same, within Workers Free CPU (10 ms) | **Failed**: 110–250 ms per request, sign-in 1.5 s | section 2 |
| Psycopg through a local Hyperdrive binding; migrations through the Worker | Passed locally; real Hyperdrive pooling and caching **not tested** (local mode connects directly) | probe `__probe/migrate` |
| Worker: PWA files, SPA fallback, cache headers, CSP, manifest type | Passed (local workerd) | 17 unit tests, `curl` checks |
| Worker → Django: sign-in, CSRF, cookies, ownership, all daily operations | Passed: e2e **18/19** through the Worker. The one failure is the known incognito-only check, passed separately | `e2e-through-worker.txt` |
| PWA installability through the Worker (Chrome, normal profile) | Passed: 0 installability errors, 0 manifest errors | `chrome-installability-through-worker.txt` |
| Offline shell, reconnect, ended session, service-worker update | Passed | same e2e |
| CSP violations / console errors | 0 / 0 | same e2e |
| Direct request to the backend without the secret | Passed: 403 `edge_only`, logged as `edge_secret_rejected` | pytest, `curl` |
| Spoofed `X-CharityOS-*` / `X-Forwarded-For` through the Worker | Passed: replaced by the Worker; the log shows the visitor's /24 | pytest, unit tests, `curl` |
| Lockouts per visitor, not per Cloudflare address | Passed | `test_lockouts_count_per_visitor_not_per_cloudflare_address` |
| Postgres over TLS: `verify-full` + `sslrootcert=system` + `channel_binding=require` | Passed against a throwaway TLS-only server with its own CA; refused with an untrusted CA | `bench/tls_check.py` run |
| Migrations from the laptop over that TLS connection (`predeploy`) | Passed | — |
| Backup over TLS (`ops/db/backup.sh`) and verified restore into a new local database | Passed: 41 tables, 269 rows, fingerprints, schema, 60 migrations | `backup-over-tls.txt`, `restore-from-tls-backup.txt` |
| Real HTTPS on `workers.dev`, real Android install | **Blocked**: needs the Cloudflare account | — |
| Django on Vercel's Python runtime | **Not tested**: needs the Vercel account | — |
| Neon wake-up after scale-to-zero, Free limits in practice | **Not tested**: needs the Neon account (Neon documents "a few hundred milliseconds") | — |

Evidence folder: `~/charityos-qa-evidence/20261127_cloudflare-prototype/` (local, not committed).

## 4. Cost

| Architecture | Monthly cost | Limitations | Suitability |
|---|---:|---|---|
| **Cloudflare-first, as briefed** (Django in a Python Worker on Workers Free + Hyperdrive + Neon Free) | $0 | CPU limit exceeded on every operation; sign-in 150× over | **Not suitable** |
| **Recommended: Cloudflare + alternative backend** (Worker on Workers Free + Django on Vercel Hobby + Neon Free) | **$0** | Three accounts. Vercel cold start after idle (seconds). Neon wakes in a few hundred ms after 5 min idle. 6-hour Neon restore window. Over a free limit means paused, not billed | **Recommended** |
| Cloudflare-only fallback (Python Worker on **Workers Paid** + Hyperdrive + Neon Free) | $5 (≈ KSh 650) | All operations worked locally after the 5 fixes. Runtime differs from tests (Python 3.14, Pyodide). Not tried on Cloudflare's network | Possible, higher risk |
| Lowest-cost reliable paid fallback (Render web + Postgres, prepared in `render.yaml`) | $13.30 (≈ KSh 1,730) | One provider, managed backups, 3-day point-in-time recovery | Reliable fallback |

Rejected free backends (details in the session report):
- **Koyeb Free:** 0.1 vCPU, so sign-in would take about 10 s. It sleeps after 1 hour.
- **Render Free:** sleeps after 15 minutes, takes about 1 minute to wake, and deletes its free database after 30 days.
- **Google Cloud Run:** generous, but needs a billing account with a card, and its budgets only alert.
- **Fly.io:** $1 starting credit, then needs a card.

Why Vercel and not just familiarity:
- it runs Django on native CPython 3.12, as the tests do;
- it gives each request a full vCPU, so sign-in takes about 1 s rather than 10;
- it detects Django itself;
- the Hobby plan is capped, not billed;
- it lets the function run in Frankfurt (`fra1`), next to the database.

Breakdown of the recommended $0, with the expected use (one person, a few hundred requests a day):

| Item | Provider allowance (free) | Expected use | Cost |
|---|---|---|---:|
| PWA files | Workers static assets: free, unlimited | — | $0 |
| Worker requests | 100,000 a day; 10 ms CPU each | under 1,000 a day; about 0.1 ms each | $0 |
| Backend | Vercel Hobby: 1,000,000 invocations, 4 active CPU-hours, 360 GB-hours memory, 100 GB transfer a month | about 15,000 requests a month; about 0.2–0.5 CPU-hours | $0 |
| Database | Neon Free: 100 CU-hours a project a month, 1 GB storage, 5 GB transfer, scale to zero after 5 min | about 20–30 CU-hours at 0.25 CU; a few MB | $0 |
| Hyperdrive | Free plan: 100,000 queries a day | not used (Vercel connects to Neon directly) | $0 |
| Domain | `workers.dev` subdomain | — | $0 |
| Backups | Neon 6-hour restore; `pg_dump` to the laptop | weekly by hand | $0 |
| **Total** | | | **$0** |

**Spending limits.**
- **Cloudflare Free and Neon Free need no card**, so nothing can be charged.
- **Vercel Hobby can't buy extra usage.** Over a limit, that feature pauses for up to 30 days.
- **Keep it at $0 by not adding a payment method to any of the three.**
- Free allowances can change. Cloudflare, Neon and Vercel all describe them as current plans, not trials, but none promises them forever.

Warning signs that would mean upgrading:
- Workers error 1027 (daily request limit);
- Vercel usage emails;
- Neon compute suspended with SQLSTATE 53000.

## 5. Security

- **Unchanged:**
  - Django session sign-in;
  - CSRF checks, now against the Worker's origin in `DJANGO_CSRF_TRUSTED_ORIGINS`;
  - secure, HttpOnly cookies;
  - HSTS and the SSL redirect;
  - ownership checks on every object;
  - django-axes lockouts;
  - the security event log with masked emails and IPs;
  - error redaction.
- **New:**
  - The edge secret gates the backend, compared in constant time and never logged.
  - The Worker refuses a non-https backend, and a secret shorter than 32 characters.
  - Production settings refuse to start in external mode without the secret or a trusted origin.
  - The database URL accepts only `sslmode`, `channel_binding` and `sslrootcert=system`. A file path for the certificate is refused.
- **Database access:**
  - Neon only accepts TLS. Use `sslmode=verify-full&sslrootcert=system&channel_binding=require`. Channel binding stops a man-in-the-middle from completing sign-in even if certificate checking were ever lost.
  - The password lives only in Vercel's environment and on the laptop, never in the repository.
- **Secrets never in the frontend:** the PWA is static files; the edge secret is a Worker secret (`wrangler secret put`), not a variable in `wrangler.jsonc`.
- **Residual risks:**
  - `workers.dev` is a shared Cloudflare domain; a custom domain can come later.
  - Vercel Hobby keeps runtime logs for only 1 hour.
  - Neon Free has no IP allow-list (that's a paid feature). Its protection is TLS plus a strong generated password.

## 6. Backups and recovery

| Layer | What | Status |
|---|---|---|
| 1. Neon instant restore | Any moment in the last **6 hours** (Free), into a branch | Automatic once the project exists |
| 2. Logical backup to the laptop | `ops/db/backup.sh` over TLS from Neon's **direct** (not `-pooler`) host: checksummed, row counts, fingerprints | Proven against a TLS-only rehearsal server; manual |
| 3. Encrypted off-machine copy | Layer 2 encrypted with the existing off-site key ([backup-and-restore.md](backup-and-restore.md#off-machine-copies)) | **Awaiting owner decision**: destination, schedule, retention, key holder. Nothing is scheduled |

Neon Free has no scheduled backups. Layer 2 is the real backup: take one weekly, and before every migration.

```bash
# On the laptop, from the repository root. The DIRECT connection details come
# from Neon's dashboard (Connect, pooling off). pg_dump 16 needs a Postgres 16 project.
# PGHOST and PGUSER: the host (without "-pooler") and role from that string.
read -rsp 'Neon password: ' PGPASSWORD && export PGPASSWORD && echo
env -u DATABASE_URL PGHOST=ep-XXXX.eu-central-1.aws.neon.tech PGPORT=5432 PGUSER=<neon-role> \
  PGSSLMODE=verify-full PGSSLROOTCERT=system PGCHANNELBINDING=require \
  ops/db/backup.sh --database charityos --label neon-weekly
unset PGPASSWORD
```

Restore drill (monthly), into a new database on the private local cluster. `restore.sh` checks rows, fingerprints, schema and migrations:

```bash
env PGHOST=/home/user/postgres-charityos/socket PGPORT=5433 PGUSER=user \
  ops/db/restore.sh --backup ~/charityos-backups/charityos/<stamp>_neon-weekly \
  --target charityos_restore_drill_neon_$(date -u +%Y%m%d)
```

Drop the drill database afterwards. Never restore over the production database; restore into a new Neon branch or database and switch `DATABASE_URL` once it checks out.

## 7. Account setup (owner actions, about 45 minutes)

Before starting:
- Vercel deploys from GitHub. The code is on the branch `feature/cloudflare-deploy` (pushed 27 Nov 2026). It stacks on PR #5 and the Render work. Until PR #5 can be merged, deploy that branch (step D). Once everything is merged, switch Vercel's production branch back to `main`.
- Generate two secrets on the laptop and keep them in your password manager:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'   # DJANGO_SECRET_KEY
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'   # EDGE_PROXY_SECRET
```

### A. Cloudflare: pick the address (5 min)
1. Sign up at [dash.cloudflare.com](https://dash.cloudflare.com/sign-up) (Free; no card).
2. Open **Workers & Pages** and choose your `workers.dev` subdomain. Your address will be `https://charityos.<subdomain>.workers.dev`.

### B. Neon: the database (10 min)
1. Sign up at [neon.com](https://neon.com) (Free; no card).
2. Create a project:
   - name `charityos`;
   - **Postgres 16** (matches the laptop's `pg_dump`);
   - region **AWS Europe (Frankfurt)**;
   - database `charityos`.
3. In the compute settings, set the maximum to **0.25 CU**. It's plenty for one person and keeps you far inside 100 CU-hours.
4. Under **Connect**, copy two strings:
   - **pooled** (host contains `-pooler`): for Vercel;
   - **direct** (pooling off): for migrations and backups.
5. Change each string's ending to `?sslmode=verify-full&sslrootcert=system&channel_binding=require`.

### C. Migrate and create your account from the laptop (10 min)
```bash
cd backend
read -rsp 'Neon DIRECT connection string: ' DATABASE_URL && export DATABASE_URL && echo
export DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_SECRET_KEY='<the generated key>' \
  DJANGO_ALLOWED_HOSTS=localhost CHARITYOS_FRONTEND=external \
  CHARITYOS_EDGE_PROXY_SECRET='<the generated edge secret>' \
  DJANGO_CSRF_TRUSTED_ORIGINS=https://charityos.<subdomain>.workers.dev
# Empty, not unset: otherwise the checkout's .env fills them in, and production
# refuses to run with both DATABASE_URL and POSTGRES_* (config/database.py).
export POSTGRES_DB= POSTGRES_USER= POSTGRES_PASSWORD= POSTGRES_HOST= POSTGRES_PORT=
../.venv/bin/python manage.py predeploy            # empty database: applies every migration
../.venv/bin/python manage.py bootstrap_charityos --email YOUR-EMAIL --display-name "Charity" \
  --timezone Africa/Nairobi --challenge-name "My 96-Day Challenge" --with-workstreams
unset DATABASE_URL DJANGO_SECRET_KEY CHARITYOS_EDGE_PROXY_SECRET
```
`bootstrap_charityos` asks for your password without showing it. It creates categories and workstreams, and no tasks or history.

### D. Vercel: the backend (10 min)
1. Sign up at [vercel.com](https://vercel.com/signup) on the **Hobby** plan with your GitHub account. Do not add a card.
2. Choose **Add New → Project**, then import `charity-os`. Set:
   - **Root Directory: `backend`**;
   - until the merges: Settings → Git → **Production Branch** `feature/cloudflare-deploy`;
   - framework: Django (detected from `manage.py`).
3. Add these Environment Variables (Production):

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `DJANGO_SECRET_KEY` | the generated key |
| `DJANGO_ALLOWED_HOSTS` | `<project>.vercel.app` (the project's production address) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://charityos.<subdomain>.workers.dev` |
| `DATABASE_URL` | Neon's **pooled** string with the `verify-full` ending |
| `CHARITYOS_FRONTEND` | `external` |
| `CHARITYOS_EDGE_PROXY_SECRET` | the generated edge secret |

4. Deploy. `backend/vercel.json` runs the function in Frankfurt (`fra1`), and Python comes from `backend/.python-version` (3.12).
5. Check it. The health probe should answer `{"status": "ok", "database": "ok"}`, and anything else should be refused with `edge_only`:

```bash
curl https://<project>.vercel.app/api/v1/health
curl https://<project>.vercel.app/api/v1/me
```

6. If the database check fails with `certificate verify failed`, the platform's CA store wasn't found. Add the variable `SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt` and redeploy. Never drop below `sslmode=require&channel_binding=require`.

### E. Cloudflare: the Worker (10 min)
```bash
cd cloudflare
npm ci
npx wrangler login                                   # opens the browser once
# Put the backend's address in wrangler.jsonc: "BACKEND_ORIGIN": "https://<project>.vercel.app"
npx wrangler secret put EDGE_PROXY_SECRET            # paste the generated edge secret
npm test                                             # 17 unit tests
npm run deploy                                       # builds frontend/dist, then deploys
```

### F. Check the live site (10 min)
| Check | How | Expected |
|---|---|---|
| Health through Cloudflare | `curl https://charityos.<subdomain>.workers.dev/api/v1/health` | `{"status": "ok", "database": "ok"}` |
| HTTPS only | `curl -sI http://charityos.<subdomain>.workers.dev/` | redirect to `https://` |
| Headers | `curl -sI https://charityos.<subdomain>.workers.dev/` | `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options: DENY`, `Cache-Control: no-cache` |
| Backend not usable directly | `curl https://<project>.vercel.app/api/v1/me` | 403 `edge_only` |
| Sign in and out | Chrome on the phone | Today screen; sign-out returns to sign-in |
| Install | Chrome → ⋮ → **Install app** | opens without the browser bar |
| Offline | airplane mode, open the app | the shell opens; it reconnects by itself |

Then take the first backup (section 6).

## 8. Releases, migrations and rollback

- **Code change, no migration:** merge to `main`. Vercel deploys the backend by itself; run `npm run deploy` in `cloudflare/` if the frontend or Worker changed.
- **New migrations:**
  1. Take a backup.
  2. Run `manage.py predeploy` from the laptop with the **direct** string, as in step C. With your account in the database it stops, lists the migrations and prints an approval code. Read them, set `CHARITYOS_APPROVE_MIGRATIONS=<code>` and run it again. Note the recovery time it prints.
  3. Then deploy the code.
  4. Migrations never run inside Vercel.
- **Roll back:**
  - **Worker:** run `npx wrangler rollback`, or use the dashboard → the Worker → **Deployments**.
  - **Backend:** Vercel dashboard → **Deployments** → promote the previous one.
  - **Data:** Neon → **Restore** to a time within the last 6 hours (it keeps a backup branch of the current state). For anything older, restore the latest layer-2 backup into a new Neon database.
  - **Migrations that must be reversed:** follow [migrations.md](../migrations.md).

## 9. Incidents

| Symptom | First steps |
|---|---|
| App says it can't reach the server (503 `backend_unavailable`) | Vercel deployment status, then Neon project status. In Vercel's logs, an `ImproperlyConfigured` names the bad variable |
| 403 `edge_only` inside the app | `EDGE_PROXY_SECRET` (Cloudflare) and `CHARITYOS_EDGE_PROXY_SECRET` (Vercel) differ. Set both to the same new value |
| Locked out after failed sign-ins | Wait 15 minutes, or run `manage.py axes_reset_username YOUR-EMAIL` from the laptop with the direct string |
| Phone lost | Run `manage.py changepassword YOUR-EMAIL`, then delete all sessions (runbook section 8), from the laptop |
| Secret leaked | Generate new values; update Vercel and `wrangler secret put`; rotate the Neon password from its dashboard |

## 10. Never

- Never add a payment method to keep a free service running without deciding to; that is a decision for the owner.
- Never put the database URL, the Django key or the edge secret in `wrangler.jsonc`, `vercel.json`, the repository or a pull request. The repository is public.
- Never connect to Neon without TLS, or with `sslmode` weaker than `require` plus `channel_binding=require`.
- Never run migrations through the pooled (`-pooler`) host; use the direct one.
- Never restore over the production database.
