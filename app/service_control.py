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
crash_count = [0] * N
crash_lock = threading.Lock()
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


def inc_crash(i):
    with crash_lock:
        crash_count[i] += 1
        return crash_count[i]


def get_crash(i):
    with crash_lock:
        return crash_count[i]


def reset_crash(i):
    with crash_lock:
        crash_count[i] = 0


class NullPointer(Exception):
    pass


def check(p):
    if not is_red() and p.get("quota") is None:
        raise NullPointer()


# Modos (variavel MITIGATION):
#   none   -> sem backoff: retry quase imediato e reinicio com RESTART fixo (como no incidente)
#   exp    -> backoff exponencial SEM jitter (todas as tarefas esperam o mesmo tempo)
#   jitter -> backoff exponencial COM jitter ("full jitter": uniforme entre 0 e o teto)
def wait_time(base, n):
    """Tempo de espera para a n-esima falha consecutiva, conforme o modo."""
    if MIT == "none":
        return base
    ceiling = min(CAPB, base * (2 ** n))
    if MIT == "jitter":
        return random.uniform(0, ceiling)
    return ceiling


def backoff(attempt):
    """Espera entre leituras falhas do banco durante o warmup."""
    if MIT == "none":
        time.sleep(0.01)
    else:
        time.sleep(wait_time(BASE, attempt))


def restart_delay(i):
    """Espera antes de reiniciar uma tarefa apos crash."""
    return wait_time(RESTART, get_crash(i))


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
            reset_crash(i)
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
            c = inc_crash(i)
            log(f"event=task_crash task={i} crashes={c}")
            delay = restart_delay(i)
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
            c = count_ready()
            return self._send(200 if c >= N else 503, {"ready": c, "n": N})
        if self.path == "/api":
            # Cada requisicao cai numa das N tarefas (como um balanceador).
            # Se a tarefa sorteada nao estiver pronta, a requisicao falha:
            # assim a % de erro mede a capacidade perdida, nao so "alguma tarefa viva".
            chosen = random.randrange(N)
            with ready_lock:
                ok = ready[chosen]
            if not ok:
                return self._send(503, {"error": "task not ready", "task": chosen})
            return self._send(200, {"ok": True, "task": chosen})
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
