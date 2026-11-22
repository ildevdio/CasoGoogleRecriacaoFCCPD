"""policy-db: representa a tabela regional do Spanner que o Service Control le.
Capacidade limitada (DB_CAPACITY leituras simultaneas, DB_COST_MS cada).
Quem espera mais que DB_QUEUE_TIMEOUT_S recebe 503. O servidor NAO sabe se o
cliente ja desistiu, entao trabalho de requisicoes abandonadas ainda e executado
(isso e o que torna o retry sem backoff tao danoso)."""
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAP = int(os.getenv("DB_CAPACITY", "10"))
COST = float(os.getenv("DB_COST_MS", "80")) / 1000
QTO = float(os.getenv("DB_QUEUE_TIMEOUT_S", "2"))
LOG = os.getenv("LOG_FILE", "/logs/db.log")

sem = threading.Semaphore(CAP)
policy = {"version": 1, "quota": 100}
stats = {"ok": 0, "rej": 0, "waiting": 0}
lk = threading.Lock()


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.time():.3f} {msg}\n")


def reporter():
    while True:
        time.sleep(1)
        with lk:
            ok, rej, w = stats["ok"], stats["rej"], stats["waiting"]
            stats["ok"] = stats["rej"] = 0
        log(f"ok={ok} rej={rej} waiting={w}")


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
            pass  # cliente ja desistiu; o trabalho ja foi gasto

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if self.path == "/snapshot":
            with lk:
                stats["waiting"] += 1
            got = sem.acquire(timeout=QTO)
            with lk:
                stats["waiting"] -= 1
            if not got:
                with lk:
                    stats["rej"] += 1
                return self._send(503, {"error": "db overloaded"})
            try:
                time.sleep(COST)
            finally:
                sem.release()
            with lk:
                stats["ok"] += 1
            return self._send(200, dict(policy))
        self._send(404, {})

    def do_POST(self):
        if self.path == "/policy":
            n = int(self.headers.get("Content-Length", 0))
            new = json.loads(self.rfile.read(n) or b"{}")
            policy.clear()
            policy.update(new)
            log(f"event=policy_changed policy={json.dumps(new)}")
            return self._send(200, {"ok": True})
        self._send(404, {})


if __name__ == "__main__":
    threading.Thread(target=reporter, daemon=True).start()
    log("event=db_start")
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8000"))), H).serve_forever()
