"""service-control: N_TASKS tarefas que (1) carregam a politica do policy-db ao
subir (WARMUP_READS leituras), (2) fazem polling periodico e (3) servem /api.
Politica com campo em branco => 'null pointer' => a tarefa cai e e reiniciada
(crash loop). POST /redbutton desliga o caminho de codigo defeituoso.
MITIGATION=jitter => backoff exponencial com jitter nas leituras e no restart."""
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
LOG = os.getenv("LOG_FILE", "/logs/sc.log")

ready = [False] * N
red = {"on": False}
lk = threading.Lock()


class NullPointer(Exception):
    pass


def log(msg):
    with lk:
        with open(LOG, "a") as f:
            f.write(f"{time.time():.3f} {msg}\n")


def fetch():
    with urllib.request.urlopen(DB + "/snapshot", timeout=RTO) as r:
        return json.loads(r.read())


def check(p):
    # caminho de codigo novo (cota): sem tratamento de erro e sem feature flag
    if not red["on"] and p.get("quota") is None:
        raise NullPointer()


def backoff(attempt):
    if MIT == "jitter":
        time.sleep(random.uniform(0, min(CAPB, BASE * 2 ** attempt)))  # full jitter
    else:
        time.sleep(0.01)  # retry imediato (so evita girar 100% de CPU)


BOOT = float(os.getenv("BOOT_STAGGER_S", "15"))


def task(i):
    time.sleep(random.uniform(0, BOOT))  # implantacao inicial escalonada
    while True:
        try:
            good = attempt = 0
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
            ready[i] = True
            log(f"event=task_ready task={i}")
            while True:
                time.sleep(POLL * random.uniform(0.5, 1.5))
                try:
                    check(fetch())
                except NullPointer:
                    raise
                except Exception:
                    pass  # mantem politica em cache
        except NullPointer:
            ready[i] = False
            log(f"event=task_crash task={i}")
            time.sleep(random.uniform(0, RESTART * 2) if MIT == "jitter" else RESTART)


def reporter():
    while True:
        time.sleep(1)
        log(f"ready_count={sum(ready)}")


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
            return self._send(200 if sum(ready) >= N else 503, {"ready": sum(ready)})
        if self.path == "/api":
            if any(ready):
                return self._send(200, {"ok": True})
            return self._send(503, {"error": "no ready task"})
        self._send(404, {})

    def do_POST(self):
        if self.path == "/redbutton":
            red["on"] = True
            log("event=redbutton")
            return self._send(200, {"ok": True})
        self._send(404, {})


if __name__ == "__main__":
    log(f"event=sc_start mitigation={MIT} n_tasks={N}")
    threading.Thread(target=reporter, daemon=True).start()
    for i in range(N):
        threading.Thread(target=task, args=(i,), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()
