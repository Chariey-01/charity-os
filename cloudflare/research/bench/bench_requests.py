"""Time real CharityOS API requests and the server's CPU per request.

Usage: python bench_requests.py BASE_URL SERVER_PID LABEL [ROUNDS]

The password for bench-owner@example.com is read from BENCH_PW. Requests are
sent one at a time. CPU is read from /proc/<pid>/task/*/schedstat
(nanoseconds on CPU) before and after each request, so it is the server's own
CPU time, not the client's or the database's:
  cpu_total  - every thread of the server process (includes GC/JIT helpers)
  cpu_thread - the one thread that used the most CPU (the request thread)
  wall       - client-side duration of the request
  waiting    - wall minus cpu_thread: time spent on the database and network
"""

import json
import os
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.cookies import SimpleCookie

BASE, PID, LABEL = sys.argv[1].rstrip("/"), int(sys.argv[2]), sys.argv[3]
ROUNDS = int(sys.argv[4]) if len(sys.argv) > 4 else 5
ORIGIN = os.environ.get("BENCH_ORIGIN", BASE)
EMAIL = "bench-owner@example.com"
PASSWORD = os.environ["BENCH_PW"]
# Local runs use a self-signed certificate; never point this at a real host.
TLS = ssl._create_unverified_context() if BASE.startswith("https://127.0.0.1") else None
if BASE.startswith("http://") and not BASE.startswith("http://127.0.0.1"):
    raise SystemExit("plain HTTP only on loopback")


def thread_cpu(pid):
    out = {}
    for tid in os.listdir(f"/proc/{pid}/task"):
        try:
            with open(f"/proc/{pid}/task/{tid}/schedstat") as f:
                out[tid] = int(f.read().split()[0])
        except FileNotFoundError:
            pass
    return out


class Client:
    def __init__(self):
        self.cookies = {}

    def call(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method)
        # The server sits behind TLS in production; the probe is plain HTTP on
        # loopback, so it gets the header the edge proxy would add.
        req.add_header("X-Forwarded-Proto", "https")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if method not in ("GET", "HEAD"):
            req.add_header("Origin", ORIGIN)
            req.add_header("Referer", ORIGIN + "/")
            if "csrftoken" in self.cookies:
                req.add_header("X-CSRFToken", self.cookies["csrftoken"])
        if self.cookies:
            req.add_header(
                "Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            )
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        before = thread_cpu(PID)
        start = time.perf_counter()
        try:
            resp = urllib.request.urlopen(req, timeout=120, context=TLS)
            status, raw, hdrs = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as err:
            status, raw, hdrs = err.code, err.read(), err.headers
        wall = (time.perf_counter() - start) * 1000
        time.sleep(0.05)  # let background threads settle before reading CPU
        after = thread_cpu(PID)
        deltas = [after[t] - before.get(t, 0) for t in after]
        for line in hdrs.get_all("Set-Cookie") or []:
            for k, morsel in SimpleCookie(line).items():
                self.cookies[k] = morsel.value
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw[:200]
        return status, payload, wall, sum(deltas) / 1e6, max(deltas) / 1e6


results = {}


def record(name, client, method, path, body=None, headers=None, expect=(200, 201)):
    status, payload, wall, cpu_total, cpu_thread = client.call(
        method, path, body, headers
    )
    ok = status in expect
    results.setdefault(name, []).append(
        {
            "status": status,
            "ok": ok,
            "wall_ms": wall,
            "cpu_total_ms": cpu_total,
            "cpu_thread_ms": cpu_thread,
        }
    )
    if not ok:
        print(f"  ! {name}: HTTP {status} {str(payload)[:300]}", file=sys.stderr)
    return payload


def main():
    anon = Client()
    record("01 health (cold: first request)", anon, "GET", "/api/v1/health")
    for _ in range(ROUNDS):
        record("01 health", anon, "GET", "/api/v1/health")

    client = None
    for _ in range(ROUNDS):
        client = Client()
        record("02a csrf cookie", client, "GET", "/api/v1/auth/csrf")
        record(
            "02b login (password check)",
            client,
            "POST",
            "/api/v1/auth/login",
            {"email": EMAIL, "password": PASSWORD},
        )

    areas = []
    for _ in range(ROUNDS):
        record("03 authenticated GET /me", client, "GET", "/api/v1/me")
        areas = record("06 workstream list", client, "GET", "/api/v1/areas") or []
    if isinstance(areas, dict):
        areas = areas.get("results", [])
    area = areas[0]["id"]

    task_ids = []
    for i in range(ROUNDS):
        task = record(
            "04 task create",
            client,
            "POST",
            "/api/v1/tasks",
            {
                "title": f"Benchmark task {i}",
                "description": "",
                "area": area,
                "priority": 2,
                "due_date": None,
                "estimated_minutes": 30,
                "status": "todo",
            },
            {"Idempotency-Key": str(uuid.uuid4())},
        )
        task_ids.append(task["id"])
        record(
            "05 task update",
            client,
            "PATCH",
            f"/api/v1/tasks/{task['id']}",
            {"title": f"Benchmark task {i} (renamed)", "estimated_minutes": 45},
        )
        record("07 schedule for today", client, "GET", "/api/v1/schedule/day")

    for task_id in task_ids:
        session_id = str(uuid.uuid4())
        session = record(
            "08a focus start",
            client,
            "POST",
            "/api/v1/sessions/start",
            {
                "id": session_id,
                "title": "Benchmark focus",
                "area": area,
                "is_deep_work": False,
                "task": task_id,
                "roadmap_item": None,
            },
        )
        record(
            "08b focus finish",
            client,
            "POST",
            f"/api/v1/sessions/{session_id}/finish",
            {
                "expected_version": (session or {}).get("version", 1),
                "outcome": "",
                "learning": "",
            },
        )

    progress = {}
    for _ in range(ROUNDS):
        progress = record("09 weekly progress", client, "GET", "/api/v1/progress")
    week = (progress or {}).get("week") or {}
    existing = record("10a weekly reviews list", client, "GET", "/api/v1/weekly-reviews")
    if isinstance(existing, dict):
        existing = existing.get("results", [])
    review = next(
        (r for r in existing or [] if r.get("week_start_date") == week.get("start")),
        None,
    )
    for i in range(ROUNDS):
        record("10a weekly reviews list", client, "GET", "/api/v1/weekly-reviews")
        if review is None:
            review = record(
                "10b weekly review save",
                client,
                "POST",
                "/api/v1/weekly-reviews",
                {
                    "week_start_date": week.get("start"),
                    "week_end_date": week.get("end"),
                    "timezone_name": "Africa/Nairobi",
                    "wins": "benchmark",
                    "lessons": "",
                    "next_week": "",
                },
            )
        else:
            review = record(
                "10b weekly review save",
                client,
                "PATCH",
                f"/api/v1/weekly-reviews/{review['id']}",
                {"wins": f"benchmark {i}", "expected_version": review["version"]},
            )

    summary = {}
    print(f"\n{LABEL}: median (max) over runs; ms")
    print(
        f"{'operation':34} {'n':>2} {'ok':>3} {'cpu_thread':>17} {'cpu_total':>17}"
        f" {'wall':>17} {'waiting':>9}"
    )
    for name, runs in results.items():
        def m(key):
            vals = [r[key] for r in runs]
            return statistics.median(vals), max(vals)

        ct, tt, wl = m("cpu_thread_ms"), m("cpu_total_ms"), m("wall_ms")
        ok = sum(r["ok"] for r in runs)
        print(
            f"{name:34} {len(runs):>2} {ok:>3} {ct[0]:8.1f} ({ct[1]:6.1f})"
            f" {tt[0]:8.1f} ({tt[1]:6.1f}) {wl[0]:8.1f} ({wl[1]:6.1f})"
            f" {max(wl[0] - ct[0], 0):9.1f}"
        )
        summary[name] = {"runs": runs}
    with open(f"results-{LABEL}.json", "w") as f:
        json.dump(summary, f, indent=1)


main()
