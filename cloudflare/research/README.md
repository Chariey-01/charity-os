# Research: can CharityOS's Django run on Cloudflare Workers?

**Not a deployment.** This folder reproduces the measurements in
[docs/operations/cloudflare-deployment.md](../../docs/operations/cloudflare-deployment.md#2-why-not-django-on-cloudflare-workers-itself).
Use only throwaway databases and throwaway accounts with it.

## `python-worker/`: the real Django app in a Python Worker

`sync-backend.sh` copies the Django apps from `backend/` into `src/` (git-ignored). `src/entry.py` then serves them through the Workers SDK's WSGI adapter, with production settings and a Hyperdrive binding. It needed five changes before it ran at all, each marked in the code:

1. Hyperdrive's connection details can't be read at start-up ("Disallowed operation called within global scope"). Django starts with a placeholder and gets the real details on the first request.
2. psycopg 3.2.10 (the version `backend/requirements.txt` pins) has no WebAssembly libpq. Pyodide ships `psycopg[binary]==3.3.5`.
3. Django refuses synchronous database calls inside the async handler (`SynchronousOnlyOperation`). Requests are serialised with an `asyncio.Lock`, as Cloudflare's Hyperdrive guide advises, and only then is `DJANGO_ALLOW_ASYNC_UNSAFE` set.
4. The runtime's `hashlib` has no `pbkdf2_hmac`, so Django's password hasher fails. `cfprobe_hashers.py` computes the same PBKDF2-SHA256, with the same 1,000,000 iterations and the same format, using `cryptography`.
5. There is no time-zone database, so `tzdata` is a dependency.

Run it (needs `uv` and Node; a throwaway database and account):

```bash
cd cloudflare/research/python-worker
./sync-backend.sh
printf 'DJANGO_SECRET_KEY="%s"\nDJANGO_ALLOWED_HOSTS="127.0.0.1"\nDJANGO_CSRF_TRUSTED_ORIGINS="https://127.0.0.1:8790"\n' \
  "$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" > .dev.vars
export CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE='postgresql://USER:PASSWORD@127.0.0.1:5433/THROWAWAY_DB'
uv run pywrangler dev --port 8790 --ip 127.0.0.1 --local-protocol https
curl -k https://127.0.0.1:8790/__probe/migrate     # migrations through the Worker
```

The `__probe/*` routes (`noop`, `connect`, `connect2q`, `pbkdf2`, `mem`, `migrate`) exist only here, to separate the runtime's own costs from Django's.

## `bench/`

- `bench_requests.py BASE_URL SERVER_PID LABEL [ROUNDS]`: the ten operations in the brief (health, sign-in, `/me`, create and update a task, workstreams, today's schedule, focus start and finish, weekly progress, weekly reviews).
  - It reports the server's CPU from `/proc/<pid>/task/*/schedstat`, separately from wall time.
  - Its account is `bench-owner@example.com`, with the password in `BENCH_PW`.
  - Plain HTTP is allowed only on loopback.
- `micro.py BASE_URL SERVER_PID N PATH...`: CPU per request for single paths.
- `edge_cpu.mjs`: CPU of the Cloudflare Worker's own code per request, on V8, with the network mocked.
