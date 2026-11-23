import json, os, threading, time, urllib.request, urllib.error

SC = os.getenv("SC_URL", "http://service-control:8080")
DB = os.getenv("DB_URL", "http://policy-db:8000")
RATE = float(os.getenv("RATE", "50"))
WORKERS = int(os.getenv("WORKERS", "10"))
POISON_AT = float(os.getenv("POISON_AT_S", "20"))
RED_AT = float(os.getenv("REDBUTTON_AT_S", "35"))
STABLE = float(os.getenv("STABLE_S", "20"))
READY_FRAC = float(os.getenv("READY_FRAC", "0.9"))
MAX_S = float(os.getenv("MAX_S", "240"))
# A execucao so termina depois de cobrir a janela fixa de erro do
# analyze.py (poison + WINDOW_S), com 1 s de folga.
WINDOW = float(os.getenv("WINDOW_S", "60"))
OUT = os.getenv("OUT_DIR", "/logs")

rows = []
lk = threading.Lock()
stop = threading.Event()


def ready_status():
    """Le {"ready": x, "n": N} de /ready (responde 503 enquanto x < N)."""
    try:
        r = urllib.request.urlopen(SC + "/ready", timeout=1)
    except urllib.error.HTTPError as e:
        r = e
    except Exception:
        return None
    try:
        return json.loads(r.read())
    except Exception:
        return None


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
    stable_since = None
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

        # Criterio de parada: pelo menos READY_FRAC das tarefas prontas,
        # sem interrupcao, por STABLE segundos (MAX_S e o teto da execucao).
        if red:
            st = ready_status()
            if st and st["ready"] >= READY_FRAC * st["n"]:
                if stable_since is None:
                    stable_since = time.time()
                elif (time.time() - stable_since >= STABLE
                      and time.time() >= ev["poison_injected"] + WINDOW + 1):
                    ev["stable_reached"] = time.time()
                    break
            else:
                stable_since = None

        if int(el * 4) % 20 == 0:
            flush(ev)

    stop.set()
    time.sleep(0.5)
    ev["end"] = time.time()
    flush(ev)
    print("client finished", ev)
