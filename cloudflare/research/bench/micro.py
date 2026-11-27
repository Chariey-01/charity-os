import os, ssl, statistics, sys, time, urllib.request
BASE, PID, N = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
TLS = ssl._create_unverified_context()
def cpu():
    out = {}
    for t in os.listdir(f"/proc/{PID}/task"):
        try: out[t] = int(open(f"/proc/{PID}/task/{t}/schedstat").read().split()[0])
        except FileNotFoundError: pass
    return out
for path in sys.argv[4:]:
    rows = []
    for _ in range(N):
        b = cpu(); s = time.perf_counter()
        r = urllib.request.urlopen(urllib.request.Request(BASE + path, headers={"X-Forwarded-Proto": "https"}), context=TLS, timeout=120); r.read()
        w = (time.perf_counter() - s) * 1000; time.sleep(0.05); a = cpu()
        rows.append((max(a[t] - b.get(t, 0) for t in a) / 1e6, w))
    c = [r[0] for r in rows]; ws = [r[1] for r in rows]
    print(f"{path:22} n={N} cpu_thread median {statistics.median(c):7.1f} ms (min {min(c):6.1f}, max {max(c):6.1f})  wall median {statistics.median(ws):7.1f} ms")
