"""Runtime de una réplica. No lo edites: tu código va en app.py.

Cada réplica corre este archivo. Atiende tres rutas HTTP:

  POST /msg     mensajes entre réplicas
  POST /client  operaciones de un cliente
  GET  /status  rol y periodo de la réplica (lo usan chaos.py y client.py)

Todo tu código corre en un solo hilo, en orden: un mensaje, un pedido o un
tick a la vez. No necesitas locks. Las réplicas no comparten memoria ni
archivos: solo saben lo que reciben en mensajes.
"""
import json
import os
import queue
import random
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TICK = 0.05          # segundos entre llamadas a on_tick
CLIENT_WAIT = 5.0    # segundos que un cliente espera una respuesta


def parse_nodes(text):
    """"n1=http://h:8001,n2=..." -> {"n1": "http://h:8001", ...}"""
    out = {}
    for part in text.split(","):
        name, url = part.split("=", 1)
        out[name.strip()] = url.strip().rstrip("/")
    return out


class Faults:
    """Lee run/faults.json, que escribe chaos.py. Se relee cada 0.2 s."""

    def __init__(self, path):
        self.path, self.data, self.read_at = path, {}, 0.0

    def get(self):
        if time.time() - self.read_at > 0.2:
            try:
                self.data = json.loads(self.path.read_text())
            except (OSError, ValueError):
                self.data = {}
            self.read_at = time.time()
        return self.data

    def blocked(self, a, b):
        groups = self.get().get("partition") or []
        side = {n: i for i, g in enumerate(groups) for n in g}
        return a in side and b in side and side[a] != side[b]

    def delay(self, a):
        return self.get().get("delay_ms", {}).get(a, 0) / 1000

    def paused(self, a):
        return a in (self.get().get("paused") or [])


class Request:
    def __init__(self, rid, op, args, client):
        self.id, self.op, self.args, self.client = rid, op, args, client


class Node:
    """Base de tu réplica. Sobrescribe start, on_message, on_request,
    on_tick y status en app.py."""

    def __init__(self, me, nodes, run_dir):
        self.id = me
        self.nodes = nodes
        self.peers = [n for n in nodes if n != me]
        self.run_dir = run_dir
        self.faults = Faults(run_dir / "faults.json")
        self._disk_path = run_dir / me / "disk.json"
        self._disk_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.disk = json.loads(self._disk_path.read_text())
        except (OSError, ValueError):
            self.disk = {}
        self._inbox = queue.Queue()
        self._waiting = {}
        self._out = queue.Queue()
        self._log = open(run_dir / me / "node.log", "a", buffering=1)

    # ---- lo que tu App puede usar ------------------------------------
    def send(self, dst, msg):
        """Envía msg (un dict) a la réplica dst. Puede perderse, demorarse o
        no llegar si hay partición o la réplica está caída."""
        self._out.put((dst, msg))

    def broadcast(self, msg):
        for p in self.peers:
            self.send(p, msg)

    def save(self):
        """Guarda self.disk en el disco de esta réplica. Sobrevive a kill y
        restart; se borra con `chaos.py start NODO --empty`. Escribe el
        archivo completo: guarda antes de responder si tu garantía lo pide."""
        tmp = self._disk_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.disk, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._disk_path)

    def reply(self, req_id, response):
        """Responde un pedido que dejaste pendiente (on_request devolvió None)."""
        w = self._waiting.pop(req_id, None)
        if w:
            w[1].update(response)
            w[0].set()

    def now(self):
        return time.monotonic()

    def log(self, *parts):
        self._log.write(f"{time.time():.3f} {self.id} " + " ".join(map(str, parts)) + "\n")

    # ---- para sobrescribir -------------------------------------------
    def start(self):
        pass

    def on_message(self, src, msg):
        pass

    def on_request(self, req):
        return {"ok": False, "error": "no implementado"}

    def on_tick(self):
        pass

    def status(self):
        return {"role": "replica", "term": None}

    # ---- runtime -----------------------------------------------------
    def _sender(self):
        while True:
            dst, msg = self._out.get()
            threading.Thread(target=self._deliver, args=(dst, msg), daemon=True).start()

    def _deliver(self, dst, msg):
        if self.faults.paused(self.id) or self.faults.blocked(self.id, dst):
            return
        d = self.faults.delay(self.id)
        if d:
            time.sleep(d * random.uniform(0.8, 1.2))
        body = json.dumps({"src": self.id, "msg": msg}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(
                self.nodes[dst] + "/msg", body, {"Content-Type": "application/json"}), timeout=2).read()
        except Exception:
            pass  # la red no avisa: el mensaje simplemente no llegó

    def _record_role(self):
        # roles.log guarda cada cambio de rol o periodo; check.py lo usa para
        # revisar que nunca haya dos líderes en el mismo periodo.
        try:
            s = self.status()
            now = (s.get("role"), s.get("term"))
        except Exception:
            return
        if now != getattr(self, "_last_role", None):
            self._last_role = now
            with open(self.run_dir / self.id / "roles.log", "a") as f:
                f.write(json.dumps({"t": time.time(), "node": self.id, "role": now[0], "term": now[1]}) + "\n")

    def _loop(self):
        self.start()
        self._record_role()
        next_tick = time.monotonic()
        while True:
            timeout = max(0.0, next_tick - time.monotonic())
            try:
                item = self._inbox.get(timeout=timeout)
            except queue.Empty:
                item = ("tick",)
            if self.faults.paused(self.id):
                if item[0] == "tick":
                    next_tick = time.monotonic() + TICK
                if item[0] == "client":
                    self.reply(item[1].id, {"ok": False, "error": "timeout"})
                continue
            try:
                if item[0] == "tick":
                    next_tick = time.monotonic() + TICK
                    self.on_tick()
                elif item[0] == "msg":
                    self.on_message(item[1], item[2])
                elif item[0] == "client":
                    r = self.on_request(item[1])
                    if r is not None:
                        self.reply(item[1].id, r)
                self._record_role()
            except Exception as e:  # un error en tu código no tumba la réplica
                self.log("ERROR", type(e).__name__, e)
                if item[0] == "client":
                    self.reply(item[1].id, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def serve(self, port):
        node = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, data):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/status":
                    if node.faults.paused(node.id):
                        time.sleep(CLIENT_WAIT)
                        return self._json(503, {})
                    self._json(200, {"id": node.id, **node.status()})
                else:
                    self._json(404, {})

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/msg":
                    if not node.faults.blocked(data["src"], node.id):
                        node._inbox.put(("msg", data["src"], data["msg"]))
                    self._json(200, {})
                elif self.path == "/client":
                    req = Request(data["id"], data["op"], data.get("args", {}), data.get("client"))
                    done, resp = threading.Event(), {}
                    node._waiting[req.id] = (done, resp)
                    node._inbox.put(("client", req))
                    if not done.wait(CLIENT_WAIT):
                        node._waiting.pop(req.id, None)
                        resp = {"ok": False, "error": "timeout"}
                    self._json(200, resp)
                else:
                    self._json(404, {})

        threading.Thread(target=self._sender, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()
        ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


def main():
    me = os.environ.get("NODE_ID") or sys.argv[1]
    nodes = parse_nodes(os.environ["NODES"])
    port = int(os.environ.get("PORT") or nodes[me].rsplit(":", 1)[1])
    run_dir = Path(os.environ.get("RUN_DIR", "run"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app import App
    App(me, nodes, run_dir).serve(port)


if __name__ == "__main__":
    main()
