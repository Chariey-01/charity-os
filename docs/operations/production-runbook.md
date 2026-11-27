# Production runbook

How CharityOS runs in production, how to deploy it, and how to recover it.
Written 27 Nov 2026 for the owner. Prices were checked that day; recheck them before buying.

Related pages:
- [deployment plan](deployment-plan.md): requirements and the go-live gate.
- [backup and restore](backup-and-restore.md): the `ops/db` scripts.
- [reverse proxy](reverse-proxy.md): client addresses behind a proxy.
- [migrations](../migrations.md): the order in which migrations are reversed.

## 1. What runs where

```
Phone / laptop browser ──HTTPS──▶ Render edge (TLS, HTTP→HTTPS) ──▶ web service "charityos"
                                                                    gunicorn + Django
                                                                    ├─ /            the PWA (frontend/dist, WhiteNoise)
                                                                    ├─ /api/v1/     the API (session cookie + CSRF)
                                                                    ├─ /admin/      Django admin
                                                                    └─ /static/     admin files
                                                                          │ private network only
                                                                          ▼
                                                                    Postgres 16 "charityos-db"
                                                                    (no internet access: ipAllowList [])
```

- **One origin** serves everything. The PWA and the session-cookie sign-in both depend on that.
- **Frankfurt region.** It is Render's closest region to Nairobi.
- **`render.yaml`** defines both resources. **`ops/deploy/build.sh`** builds them, **`ops/deploy/start.sh`** starts them, and **`python manage.py predeploy`** runs before every release (section 5).

| Item | Plan | USD / month | KSh / month (at 130) |
|---|---|---|---|
| Web service `charityos` | 0.5 CPU, 512 MB (`0.5c-512mb`) | 7.00 | 910 |
| Postgres `charityos-db` | 0.1 CPU, 256 MB (`0.1c-256mb`) | 6.00 | 780 |
| Database storage | 1 GB at $0.30/GB | 0.30 | 39 |
| Hobby workspace | | 0.00 | 0 |
| **Total** | | **13.30** | **≈ 1,730** |

Included in that price:
- HTTPS on `<name>.onrender.com` (a domain is optional);
- 3 days of point-in-time recovery for the database;
- logical exports, kept 7 days;
- 5 GB of bandwidth a month.

## 2. First deployment (owner actions)

Before you start:
- `render.yaml` and this branch must be on GitHub;
- the Render GitHub app is already installed on `charity-os`.

The Blueprint deploys branch `main` once its CI checks pass (`autoDeployTrigger: checksPass`).

1. Sign in at [dashboard.render.com](https://dashboard.render.com) with the account the GitHub app belongs to.
2. Add a payment method. This is the step that commits money; nothing is charged before it.
3. Choose **New → Blueprint**, select the `charity-os` repository, and select the branch to deploy.
4. Render lists two resources: **web service `charityos`** and **database `charityos-db`**. Check the plans and the Frankfurt region, then apply.
5. Render creates the database and generates `DJANGO_SECRET_KEY`. It then builds (`ops/deploy/build.sh`), runs `predeploy` and starts the service.
   - On a fresh database, `predeploy` applies every migration.
   - The deploy log ends with the health check passing at `/api/v1/health`.
6. The service page shows its URL: `https://charityos.onrender.com`, or a variant with a suffix if that name is taken. That is the address you will use.

### Create your account (once)

There is no public sign-up. Open the service's **Shell** tab (paid instances have one) and run:

```bash
cd backend
python manage.py bootstrap_charityos --email YOUR-EMAIL --display-name "Charity" \
  --timezone Africa/Nairobi --challenge-name "My 96-Day Challenge" --with-workstreams
```

The command:
- asks for the password without showing it;
- creates the default categories and the six workstreams;
- **creates no tasks, sessions or records.** History starts empty.

### Check the deployment (about 10 minutes)

| Check | How | Expected |
|---|---|---|
| Health | `curl https://<host>/api/v1/health` | `{"status": "ok", "database": "ok"}` |
| HTTPS only | `curl -sI http://<host>/` | a redirect to `https://` |
| Security headers | `curl -sI https://<host>/` | `Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options: DENY`, `Cache-Control: no-cache` |
| Django deploy checks | in the Shell: `cd backend && python manage.py check --deploy` | no issues |
| Database not public | Render database page, **Networking** | no allowed IP ranges |
| Client address | the test in [reverse-proxy.md](reverse-proxy.md#checking-a-deployment) | `ip=` your own /24 in the log, not `192.0.2.0/24` |
| Sign in and out | the site in Chrome | Today screen; sign-out returns to sign-in |

## 3. Installing on Android

1. Open the URL in **Chrome** on the phone and sign in.
2. Chrome offers **Install app**. You can also use the ⋮ menu → **Install app** (older versions call it **Add to Home screen**).
3. Confirm. CharityOS appears in the launcher with its own icon and opens without the browser bar.
4. Open it once while online. After that, the app shell opens offline. Changes still need a connection, and the app reconnects by itself.

If Chrome does not offer to install:
- check that the address starts with `https://`;
- reload once, so the service worker can take control of the page.

## 4. Logs and what to watch

Find them in the Render service's **Logs** tab: gunicorn access lines, application errors and security events, all on stdout/stderr.

- **Security events** (`charityos.security`): `login_succeeded`, `login_failed`, `login_locked_out`, `logout`, `csrf_rejected`. Emails are masked and IPs truncated to a /24.
- **Errors**: one redacted line plus the traceback. Passwords, tokens, cookies and emails are masked (`config/error_logging.py`).
- **Health**: Render polls `/api/v1/health` and restarts the service if it fails. `health check: database unavailable (…)` means the database could not be reached.

Investigate:
- a `login_locked_out` you did not cause;
- repeated `csrf_rejected`;
- any 5xx response;
- unexpected restarts.

## 5. Releasing changes

1. Merge to `main` through a pull request whose checks pass. Render deploys the commit after its checks pass.
2. `predeploy` runs before the new release takes traffic. If it fails, **the previous release keeps serving** and nothing changes.
   - No new migrations: it only runs `check --deploy`.
   - New migrations, and the database holds accounts: **it stops**. It lists the migrations and prints an approval code.

### Approving migrations over real data

1. Read the listed migrations and their notes in [migrations.md](../migrations.md). Know how each one would be undone.
2. Take a backup (section 6, "Before a migration").
3. In the service's **Environment**, set `CHARITYOS_APPROVE_MIGRATIONS` to the printed code. Then choose **Manual Deploy → Deploy latest commit**.
4. The log prints the approved list and a **recovery point** (a UTC time) before it migrates. Note that time down.
5. **Remove `CHARITYOS_APPROVE_MIGRATIONS` afterwards.** The code approves only that exact set of migrations, so a later release with different ones stops again.

## 6. Backups and recovery

| Layer | What | Cost | Status |
|---|---|---|---|
| 1. Point-in-time recovery | Render restores the database to any moment in the last **3 days**, into a new database | included | automatic once the database exists |
| 2. Logical export | Render database **Recovery** page → export. A compressed `pg_dump` directory, kept **7 days** on Render | included | manual |
| 3. Encrypted off-machine copy | The export, encrypted with the existing off-site key (`gpg` AES-256, [backup-and-restore.md](backup-and-restore.md#off-machine-copies)) and stored away from both Render and the laptop | depends on destination | **awaiting owner decision** |

Layers 1 and 2 both live at Render. Layer 3 protects against losing the Render account, or against an error noticed after more than 3 days.

**Proposed layer 3.** Not built and not scheduled. Your decision is needed on:
- **Destination:** your Google Drive, or another storage account.
- **Schedule:** weekly by hand, or an automated job that encrypts on Render with a public key and uploads.
- **Retention:** 8 weekly copies.
- **Who holds the key.**

No timer or job is installed until you approve all four.

### Restore drill (before real data goes in, then monthly)

1. On the database's **Recovery** page, create a logical export and download it to the laptop.
2. Restore it into a **new** local database on the private cluster. Never use `charityos` or any protected name.

   ```bash
   mkdir -p ~/charityos-drill && tar -xzf <export>.dir.tar.gz -C ~/charityos-drill
   createdb -h /home/user/postgres-charityos/socket -p 5433 charityos_restore_drill_render_<date>
   pg_restore -h /home/user/postgres-charityos/socket -p 5433 --no-owner --no-acl \
     -d charityos_restore_drill_render_<date> ~/charityos-drill/<export-dir>
   ```

3. Check the restored copy with `POSTGRES_DB=charityos_restore_drill_render_<date> python manage.py check_data_integrity`. Then compare its row counts with the production counts (`manage.py shell` on Render).
4. Drop the drill database. Keep the drill note.

### Before a migration

Create a logical export (layer 2) and download it. The recovery point that `predeploy` prints is a second safety net, through layer 1.

## 7. Rollback

| Situation | Action |
|---|---|
| A release misbehaves, no migration in it | In the service's **Events**, choose **Rollback** on the previous deploy. Render serves the earlier build. |
| A release with migrations misbehaves, data intact | Roll back the code only if the old code works with the new schema. Otherwise reverse the migrations in the Shell, in the order given in [migrations.md](../migrations.md), then roll back. Some reverses refuse while data would be lost. In that case, use the next row. |
| Data damaged, or a migration half-applied | Use point-in-time recovery to the recovery point, which creates a **new** database. Check it with `check_data_integrity`. Then point the service's `DATABASE_URL` at the new database and redeploy. Keep the damaged database until the cause is understood. |

## 8. Incidents

| Symptom | First steps |
|---|---|
| Site down, health failing | Read the Logs. A database error means checking the database page's status. A start-up `ImproperlyConfigured` names the missing or bad variable. |
| Locked out after failed sign-ins | Wait 15 minutes, or in the Shell: `cd backend && python manage.py axes_reset_username YOUR-EMAIL` |
| Forgot password | Shell: `cd backend && python manage.py changepassword YOUR-EMAIL` |
| Phone lost or stolen | Change the password (above). Then end every session: `python manage.py shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"`. Every device has to sign in again. |
| Suspected leak of the secret key or the database password | Generate a new `DJANGO_SECRET_KEY` in Environment, which signs everyone out. Rotate the database password from the database page. Redeploy. Read the security log for the period. |
| A bad release | Section 7 |

## 9. Environment variables

These live in Render's Environment and are never committed.

| Variable | Set by | Value |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Blueprint | `config.settings.production`. `start.sh` refuses anything else. |
| `DJANGO_SECRET_KEY` | Render (generated) | 256 random bits. Production refuses short or placeholder keys. |
| `DJANGO_ALLOWED_HOSTS` | Blueprint | The service's `onrender.com` host. Add a custom domain here, comma-separated. |
| `DATABASE_URL` | Render (from the database) | Internal URL. **Do not also set `POSTGRES_*`**: production refuses to start with both. |
| `CHARITYOS_TRUSTED_PROXIES` | Blueprint | Empty. Render's proxy addresses are not published ([reverse-proxy.md](reverse-proxy.md)). |
| `CHARITYOS_APPROVE_MIGRATIONS` | Owner, per release | Only while approving migrations (section 5). |
| `CHARITYOS_DB_CONN_MAX_AGE` | optional | Seconds a database connection is reused. Default 60. |

## 10. Never

- Never allow internet access to the database (`ipAllowList`) to make a backup easier. Use the export instead.
- Never restore over a damaged database. Always restore into a new one.
- Never put secrets in `render.yaml`, the repository or a pull request. The repository is public.
- Never set `DEBUG`, or use development settings, on Render.
