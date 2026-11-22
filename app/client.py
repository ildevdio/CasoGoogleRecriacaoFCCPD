import os, threading, time, urllib.request, urllib.error

SC = os.getenv("SC_URL", "http://service-control:8080")
DB = os.getenv("DB_URL", "http://policy-db:8000")
RATE = float(os.getenv("RATE", "50"))
WORKERS = int(os.getenv("WORKERS", "10"))
POISON_AT = float(os.getenv("POISON_AT_S", "20"))
RED_AT = float(os.getenv("REDBUTTON_AT_S", "35"))
STABLE = float(os.getenv("STABLE_S", "20"))
MAX_S = float(os.getenv("MAX_S", "240"))
OUT = os.getenv("OUT_DIR", "/logs")

rows = []
lk = threading.Lock()
last_err = {"t": 0.0}
stop = threading.Event()


def wait(url, timeout=1):
    while True:
        try:
            urllib.request.urlopen(url + "/health", timeout=timeout)
            return
        except Exception:
            time.sleep(0.5)


def post(url, data=b"{}"):
    req = urllib.request.Request(url, data=data, method="POST")
    urllib.request.urlopen(req, timeout=2).read()


def worker():
    period = WORKERS / RATE
    while not stop.is_set():
        t = time.time()
        try:
            code = urllib.request.urlopen(SC + "/api", timeout=1).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception:
            code = 0
        lat = (time.time() - t) * 1000
        with lk:
            rows.append((t, code, lat))
            if code != 200:
                last_err["t"] = t
        time.sleep(max(0, period - (time.time() - t)))


def flush(ev):
    with lk:
        data = list(rows)
    with open(f"{OUT}/client.csv", "w") as f:
        f.write("epoch,status,latency_ms\n")
        f.writelines(f"{a:.3f},{b},{c:.1f}\n" for a, b, c in data)
    with open(f"{OUT}/client_events.log", "w") as f:
        for k, v in ev.items():
            f.write(f"{k}={v:.3f}\n")


if __name__ == "__main__":
    wait(SC)
    wait(DB)

    while True:
        try:
            urllib.request.urlopen(SC + "/ready", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    ev = {}
    t0 = time.time()
    ev["t0"] = t0

    for _ in range(WORKERS):
        threading.Thread(target=worker, daemon=True).start()

    poisoned = False
    red = False
    while time.time() - t0 < MAX_S:
        time.sleep(0.25)
        el = time.time() - t0

        if not poisoned and el >= POISON_AT:
            post(DB + "/policy", b'{"version": 2, "quota": null}')
            ev["poison_injected"] = time.time()
            poisoned = True

        if not red and el >= RED_AT:
            post(SC + "/redbutton")
            ev["redbutton_pressed"] = time.time()
            red = True

        if red and time.time() - max(last_err["t"], ev["redbutton_pressed"]) >= STABLE:
            ev["stable_reached"] = time.time()
            break

        if int(el * 4) % 20 == 0:
            flush(ev)

    stop.set()
    time.sleep(0.5)
    ev["end"] = time.time()
    flush(ev)
    print("client finished", ev)
