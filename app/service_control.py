import json, os, random, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

N = int(os.getenv("N_TASKS", "100"))
POLL = float(os.getenv("POLL_S", "2"))
DB = os.getenv("DB_URL", "http://policy-db:8000")
MIT = os.getenv("MITIGATION", "none")
WARM = int(os.getenv("WARMUP_READS", "5"))
RESTART = float(os.getenv("RESTART_DELAY_S", "0.5"))
RTO = float(os.getenv("READ_TIMEOUT_S", "0.5"))
BASE = float(os.getenv("BACKOFF_BASE_S", "0.1"))
CAPB = float(os.getenv("BACKOFF_CAP_S", "5"))
BOOT = float(os.getenv("BOOT_STAGGER_S", "15"))
LOG = os.getenv("LOG_FILE", "/logs/sc.log")

ready = [False] * N
ready_lock = threading.Lock()
red = {"on": False}
red_lock = threading.Lock()


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.time():.3f} {msg}\n")


def fetch():
    with urllib.request.urlopen(DB + "/snapshot", timeout=RTO) as r:
        return json.loads(r.read())


def is_red():
    with red_lock:
        return red["on"]


def set_red(value):
    with red_lock:
        red["on"] = value


def set_ready(i, value):
    with ready_lock:
        ready[i] = value


def count_ready():
    with ready_lock:
        return sum(ready)


class NullPointer(Exception):
    pass


def check(p):
    if not is_red() and p.get("quota") is None:
        raise NullPointer()


def backoff(attempt):
    if MIT == "jitter":
        time.sleep(random.uniform(0, min(CAPB, BASE * 2 ** attempt)))
    else:
        time.sleep(0.01)


def task(i):
    time.sleep(random.uniform(0, BOOT))
    while True:
        try:
            good = 0
            attempt = 0
            while good < WARM:
                try:
                    check(fetch())
                    good += 1
                    attempt = 0
                except NullPointer:
                    raise
                except Exception:
                    attempt += 1
                    backoff(attempt)
            set_ready(i, True)
            log(f"event=task_ready task={i}")
            while True:
                time.sleep(POLL * random.uniform(0.5, 1.5))
                try:
                    check(fetch())
                except NullPointer:
                    raise
                except Exception:
                    pass
        except NullPointer:
            set_ready(i, False)
            log(f"event=task_crash task={i}")
            delay = random.uniform(0, RESTART * 2) if MIT == "jitter" else RESTART
            time.sleep(delay)


def reporter():
    while True:
        time.sleep(1)
        log(f"ready_count={count_ready()}")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        try:
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if self.path == "/ready":
            return self._send(200 if count_ready() >= N else 503, {"ready": count_ready()})
        if self.path == "/api":
            if count_ready() > 0:
                return self._send(200, {"ok": True})
            return self._send(503, {"error": "no ready task"})
        self._send(404, {})

    def do_POST(self):
        if self.path == "/redbutton":
            set_red(True)
            log("event=redbutton")
            return self._send(200, {"ok": True})
        self._send(404, {})


if __name__ == "__main__":
    log(f"event=sc_start mitigation={MIT} n_tasks={N}")
    threading.Thread(target=reporter, daemon=True).start()
    for i in range(N):
        threading.Thread(target=task, args=(i,), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()
