# Running CharityOS behind a reverse proxy

Sign-in lockouts and the security log need the address of the person signing in. Behind a reverse proxy, Django sees the proxy's address instead. This page explains how CharityOS finds the real address and how to configure it safely.

Nothing here has been deployed. The settings below are defaults and instructions; no production infrastructure was changed.

## What goes wrong without it

Lockouts are per email and IP address: the sixth failure locks that pair for 15 minutes. Each further attempt during the lock starts the 15 minutes again.

Behind a proxy without configuration, every request has the proxy's address. So:
- one person guessing passwords for an email locks that account **for everyone**;
- by retrying every few minutes, they can keep it locked indefinitely;
- the security log shows only the proxy's address.

## How CharityOS decides (`backend/config/proxies.py`)

| Situation | Address used |
|---|---|
| `CHARITYOS_TRUSTED_PROXIES` empty (the default) | `REMOTE_ADDR`. Forwarded headers are ignored completely. |
| The connection does not come from a listed proxy | `REMOTE_ADDR`. Its `X-Forwarded-For` is not believed. |
| The connection comes from a listed proxy | `X-Forwarded-For`, read from the right, skipping listed proxies. The first other address is the client. |
| That entry is not a plain IP address (for example `203.0.113.5:4433`) | The proxy's address. CharityOS never guesses. |
| The header is missing or empty | The proxy's address. |

Only `X-Forwarded-For` is read. `X-Real-IP`, `Forwarded` and other headers are ignored.

**Why read from the right.** A client can send its own `X-Forwarded-For`. A proxy appends the address it actually saw, so the right-most entries are written by proxies you run. Anything to the left of the first address your proxies did not add was written by the client, and can be forged.

Example, with the proxy at `10.0.0.2` listed:

```
REMOTE_ADDR      10.0.0.2                          (your proxy: trusted)
X-Forwarded-For  1.2.3.4, 203.0.113.66             (1.2.3.4 forged by the client)
                          ^ client = 203.0.113.66   (appended by your proxy)
```

The same resolver feeds both django-axes (`AXES_CLIENT_IP_CALLABLE = "config.proxies.axes_client_ip"`) and the security log. A lock and its log line always name the same address.

## Configuration

Set one environment variable: a comma-separated list of your proxies' addresses or networks.

```
CHARITYOS_TRUSTED_PROXIES=10.0.0.2
CHARITYOS_TRUSTED_PROXIES=10.0.0.0/24, fd00:1::/64
```

The value is checked at start-up, and the application refuses to start when:
- an entry is not an address or network;
- an entry has host bits set (`10.0.0.1/8`);
- an entry trusts everything (`0.0.0.0/0`, `::/0`).

**List each proxy exactly as Django sees it in `REMOTE_ADDR`.** If the application server listens on an IPv6 socket, an IPv4 proxy can arrive as `::ffff:10.0.0.2`, which does not match `10.0.0.2`; list `::ffff:10.0.0.2/128` or bind the server to IPv4. A proxy that does not match is not trusted: the result is safe (shared lockouts, no spoofing), and the check below shows it.

**List only addresses that are your proxies.** Anything listed can tell CharityOS which address a request came from. Never list a range that other customers of a hosting platform, or the public internet, can connect from.

### The proxy itself

The proxy must:
1. be the only way to reach Django: the application port must not be reachable directly;
2. **set or append** `X-Forwarded-For` with the address it saw;
3. **overwrite** `X-Forwarded-Proto`.

On point 3: production settings already trust `X-Forwarded-Proto: https` (`SECURE_PROXY_SSL_HEADER`). That setting predates this page and was not changed. It is safe only when requests reach Django exclusively through a proxy that overwrites the header.

nginx:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    # Replaces anything the client sent. Use $proxy_add_x_forwarded_for only
    # when another proxy you run sits in front of this one.
    proxy_set_header X-Forwarded-For   $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Host              $host;
}
```

Caddy 2: `reverse_proxy 127.0.0.1:8000`. By default, Caddy writes the address it saw and ignores client-sent forwarded headers unless `trusted_proxies` is configured. Confirm this with the check below.

**Managed hosting.** On a platform whose edge proxy addresses are not published, ask the provider which addresses its proxy connects from. Do not guess a private range such as `10.0.0.0/8`. Until you know, leave the variable empty. Lockouts then apply per email to everyone behind that proxy: a documented risk, but not a spoofable one.

## Checking a deployment

After deploying, from a machine outside the proxy:

1. Make a failed sign-in whose header claims a fake address:

   ```
   curl -s https://<host>/api/v1/auth/csrf -c jar -o /dev/null
   curl -s https://<host>/api/v1/auth/login -b jar \
     -H "X-CSRFToken: $(awk '/csrftoken/ {print $7}' jar)" \
     -H "Content-Type: application/json" \
     -H "X-Forwarded-For: 192.0.2.1" \
     -d '{"email":"nobody@example.com","password":"x"}'
   ```

2. Find the matching `event=login_failed` line in the application log:

   | The line shows | Meaning |
   |---|---|
   | `ip=` your own network's /24 | Correct |
   | `ip=192.0.2.0/24` | Forged headers are being believed: a misconfiguration; fix it before going live |
   | `ip=` the proxy's address | `CHARITYOS_TRUSTED_PROXIES` is empty, or does not match the proxy |

3. Remove the test lock if you made several attempts: `python manage.py axes_reset_username nobody@example.com`.

## Tests

`backend/tests/test_client_ip.py` covers:
- the default (headers ignored);
- forged first hops;
- chained proxies;
- IPv6;
- connections that bypass the proxy;
- malformed entries;
- strict parsing of the setting;
- lockout behind a proxy, where one attacker no longer locks out the owner;
- the logged address.
