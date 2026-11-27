# Deployment plan (private use)

**Status (27 Nov 2026): prepared, not deployed.** The code changes this plan called for are made on `feature/production-deploy`: Django serves the PWA through WhiteNoise, the platform's `DATABASE_URL` is accepted, and `render.yaml` plus `ops/deploy/` hold the deployment. The recommended host and the step-by-step procedure are in the [production runbook](production-runbook.md). Nothing has been deployed. No hosting has been bought, no domain registered, and no account created. The owner must approve, separately:
- the hosting choice and its cost;
- the domain;
- the deployment itself;
- any migration of the personal `charityos` database.

A $0 alternative was prepared afterwards on `feature/cloudflare-deploy`: Cloudflare serves the PWA and forwards the API to Django on Vercel Hobby, with PostgreSQL on Neon Free. It was proven locally, not deployed; see the [Cloudflare deployment guide](cloudflare-deployment.md). The requirements below apply to both layouts, except that there the Worker, not Django, serves the files in section 1.

This plan lists what the code on `integration/phase-0` needs. Related guides:
- [reverse proxy](reverse-proxy.md)
- [backup and restore](backup-and-restore.md)
- [migrations](../migrations.md)
- [PWA checklist](private-pwa-release-checklist.md)

## 1. Shape of the deployment

There is one HTTPS origin, for example `https://app.example.org`. Both the PWA and the session-cookie sign-in depend on it.

| Path | Served by |
|---|---|
| `/` (including `index.html`, `sw.js`, `manifest.webmanifest`, `/assets/`, `/icons/`) | the files from `frontend/dist` (`npm ci && npm run build`) |
| `/static/` | `backend/staticfiles` (`manage.py collectstatic --noinput`), for the admin |
| `/api/`, `/admin/` | Django through gunicorn: `gunicorn config.wsgi` from `backend/` |

**Django serves the frontend** with production settings (`config/frontend.py`): WhiteNoise serves `frontend/dist` at `/` and `/static/`. The app routes with the URL hash, so no catch-all route is needed. `index.html`, `sw.js` and the manifest are sent with `no-cache`, hashed assets as immutable, and `index.html` carries a Content-Security-Policy. This works the same on one PaaS web service and on a VPS behind Caddy or nginx.

## 2. Hosting requirements

| Need | Requirement |
|---|---|
| Runtime | Python 3.12. Node 24 at build time only. |
| Database | Managed or self-run PostgreSQL **16**, on persistent storage, reachable only from the application. With 17 or later, the backup host needs client tools of that version or newer, and CI should move to the same version. |
| TLS | A certificate for the chosen name, renewed automatically. |
| Process | One gunicorn service, restarted on failure. Its logs go to stdout and stderr. |
| Backups | Somewhere off the application host to hold encrypted backups (see section 7). |
| Shell access | Needed to run `ops/db/*.sh` and the management commands (`erase_user`, `axes_reset_username`, `check_data_integrity`). |

## 3. Environment variables and secrets

Set these in the platform's secret store, never in the repository. `.env.example` lists the names.

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `DJANGO_SECRET_KEY` | A new random value of 50 or more characters, used only here. Production refuses to start without it. |
| `DJANGO_ALLOWED_HOSTS` | The host name only, for example `app.example.org` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://app.example.org` |
| `DATABASE_URL` **or** `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | Production accepts a platform's `DATABASE_URL` (`postgres://`, optional `sslmode`), or all five `POSTGRES_*`, **never both**: it refuses to start when both are set (`config/database.py`). Development and tests read only `POSTGRES_*`, and the `ops/db` scripts refuse to run while `DATABASE_URL` is set. The defaults (`charityos` on `localhost`) are for development only. |
| `CHARITYOS_TRUSTED_PROXIES` | Empty until the proxy's address is known, then exactly that address (see [reverse-proxy.md](reverse-proxy.md)) |

The database password and secret key are owned by the operator. Use a database role that owns only the CharityOS database.

## 4. HTTPS

Production settings already redirect to HTTPS, set secure cookies, and send HSTS for one year with `includeSubDomains` and `preload`.
- Use a domain or subdomain that serves nothing else.
- Do not submit it for preloading while the setup may still change.
- `SECURE_PROXY_SSL_HEADER` trusts `X-Forwarded-Proto`. That is safe only when the proxy overwrites the header and the application port cannot be reached directly.

## 5. Reverse proxy and client addresses

Follow [reverse-proxy.md](reverse-proxy.md). **Deployment stays blocked until its "Checking a deployment" test passes on the real host**: the security log must show the client's own network, not the proxy and not a forged address. No nginx or Caddy configuration has been run against this code yet. The configuration in that guide comes from documentation and must be verified there.

## 6. Logging and monitoring

- **Security events.** Logger `charityos.security` writes one line each to stderr: `login_succeeded`, `login_failed`, `login_locked_out`, `logout`, `csrf_rejected`, `erasure_dry_run`, `user_erased`. Emails are masked and IP addresses truncated. Keep these logs for at least 30 days.
- **Alerts:**
  - any `login_locked_out` you did not cause;
  - repeated `csrf_rejected`;
  - HTTP 5xx responses;
  - the process restarting.
- **Uptime.** Check `GET /api/v1/health` every few minutes. It is anonymous, runs `SELECT 1` on the database, and answers 200 or 503 with no details. It is answered before host and HTTPS checks, so a platform's internal probe works too (`config/health_probe.py`).
- **Django errors (L1, fixed on `feature/daily-operations`).** Unhandled exceptions and `django.security` errors are written to stderr, one redacted line plus the traceback each (`config/error_logging.py`): emails masked, password, token, secret, session, CSRF and Authorization values replaced, and the path without its query string. Gunicorn writes its own access and error lines to stderr as well (`--access-logfile - --error-logfile -`). Collect stderr. Without `DEBUG`, nothing else writes these errors.

## 7. Backups and retention

- Use `ops/db/backup.sh` from a host that can reach the database. It keeps 14 daily and 8 weekly backups, each with a checksum and row-count manifest, and verifies every backup.
- Copies kept off the machine must be **encrypted**. The current encrypted copy sits on the development machine's own disk, so an off-machine location is still an owner decision.
- If the platform has its own database backups, keep them on as well, but they do not replace a restore drill.
- The systemd timer in `backup-and-restore.md` is installed only after a manual backup and restore have passed on the real host, and only with owner approval.

## 8. Restore testing

1. **Before any real data goes in:** take a backup of the new production database, then run `ops/db/restore-drill.sh` into a **new** database. It refuses existing ones and protected names.
2. Repeat monthly, and before every release that contains migrations.
3. Keep the drill reports.

## 9. Running migrations

- Never run `manage.py migrate` directly against a database that holds real records. Run `ops/db/migrate-with-backup.sh --database NAME` instead. It takes a verified pre-migration backup, checks that Django will reach that same database, and only then migrates.
- **A new, empty production database** migrates from zero. CI and the local fresh-database check do exactly that on every change.
- **The personal `charityos` database** (34 migrations, applied on 24 Nov) moves 25 migrations forward to this release. The restore drill exercises that path on `charityos_acceptance`, which has the same 34: forward, back with every row identical, then forward again. Migrating `charityos` needs separate owner approval and a drill of `charityos` itself first.

## 10. Rollback

| Situation | Action |
|---|---|
| A code problem, schema unchanged | Redeploy the previous commit. |
| A release whose migrations must be undone | Stop the app, then reverse with `manage.py migrate <app> <previous>` in the order given in [migrations.md](../migrations.md), then redeploy the previous code. Every Phase 0 migration has a reverse, but some refuse to run when reversing would lose data: the four `*.0002_archived_at` migrations while archived rows exist, and `reflections.0003` while revisions exist. In those cases use the backup row below. `api.0001` drops only replay records, which expire after 24 hours anyway. |
| Data damaged, or a migration half-applied | Restore the pre-migration backup into a **new** database with `ops/db/restore.sh`, check it with `check_data_integrity`, point `POSTGRES_DB` at it, and redeploy. Never restore over the damaged database; keep it for investigation. |

## 11. Go-live gate

All of these must be true before real data goes into a deployment:

- [x] Deployment configuration prepared and verified locally under production settings (`feature/production-deploy`)
- [ ] Hosting, domain and cost approved by the owner
- [ ] HTTPS working; `manage.py check --deploy` clean on the host
- [ ] Proxy check from `reverse-proxy.md` passed, with `CHARITYOS_TRUSTED_PROXIES` set
- [x] Error logging fixed (L1) and tested
- [ ] Logs collected and alerts set (section 6)
- [ ] Backup taken, and a restore drill passed, on the host (section 8)
- [ ] An encrypted off-machine backup location chosen
- [x] PWA fixes SW1 and AU1 done (`feature/daily-operations`)
- [ ] Install tests 4.1–4.5 passed on the deployed site
- [ ] CI green on the deployed commit
