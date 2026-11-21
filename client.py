"""Cliente que guarda un historial. Úsalo en tus escenarios.

    from client import Client
    c = Client("c1", "run/historial.jsonl")
    c.call("reservar", asiento="A1")         # va a cualquier réplica
    c.call("likes", node="n2", banda="x")    # a una réplica en particular
    c.final("likes", banda="x")              # lee en cada réplica (convergencia)

Cada operación queda en el historial con su id, cliente, argumentos, hora de
inicio, hora de fin, resultado y error. Si nunca recibe respuesta, queda con
"ok": false y check.py la trata como "pudo pasar o no".

"ok": false significa "esta réplica no pudo atender el pedido", y el cliente
reintenta. Una respuesta de tu app, aunque sea una negativa ("asiento
ocupado", "sin stock"), va con "ok": true y la negativa en "result".

Si una réplica responde {"redirect": "n2"}, el cliente reintenta en n2.
Si no hay respuesta, reintenta en otra réplica con el mismo request_id,
hasta `timeout` segundos. Tu App puede usar ese id para no aplicar dos veces
la misma operación (M05).
"""
import json
import random
import threading
import time
import urllib.request
import uuid
from pathlib import Path

_lock = threading.Lock()


def cluster(run_dir="run"):
    return json.loads((Path(run_dir) / "cluster.json").read_text())


def _post(url, data, wait):
    req = urllib.request.Request(url + "/client", json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=wait) as r:
        return json.loads(r.read())


class Client:
    def __init__(self, name, history, run_dir="run", timeout=10.0):
        self.name, self.timeout = name, timeout
        self.history = Path(history)
        self.history.parent.mkdir(parents=True, exist_ok=True)
        self.nodes = cluster(run_dir)["host_nodes"]

    def _record(self, entry):
        with _lock, open(self.history, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def call(self, op, node=None, **args):
        """Hace una operación y la guarda en el historial. Devuelve la
        respuesta de la réplica (un dict), o {"ok": False, ...}."""
        oid = f"{self.name}-{uuid.uuid4().hex[:8]}"
        start, deadline = time.time(), time.time() + self.timeout
        target = node or random.choice(list(self.nodes))
        resp, served = {"ok": False, "error": "sin respuesta"}, None
        while time.time() < deadline:
            try:
                resp = _post(self.nodes[target], {"id": oid, "op": op, "args": args, "client": self.name},
                             wait=max(0.5, min(6.0, deadline - time.time())))
            except Exception as e:
                resp = {"ok": False, "error": type(e).__name__}
            served = target
            if resp.get("redirect") in self.nodes:
                target = resp["redirect"]
                continue
            if resp.get("ok"):
                break
            if node:  # pediste una réplica en particular: no cambia
                time.sleep(0.2)
                continue
            target = random.choice([n for n in self.nodes if n != target] or [target])
            time.sleep(0.2)
        self._record({"id": oid, "client": self.name, "op": op, "args": args,
                      "invoke": start, "complete": time.time() if resp.get("ok") else None,
                      "ok": bool(resp.get("ok")), "result": resp.get("result"),
                      "error": resp.get("error"), "node": served})
        return resp

    def final(self, op, **args):
        """Lee en cada réplica por separado, sin reintentar en otra. Úsalo al
        final de un escenario, después de `chaos.py heal`, para revisar
        convergencia."""
        out = {}
        for n, url in self.nodes.items():
            t = time.time()
            try:
                resp = _post(url, {"id": f"{self.name}-final-{uuid.uuid4().hex[:6]}", "op": op,
                                   "args": {**args, "local": True}, "client": self.name}, wait=6)
            except Exception as e:
                resp = {"ok": False, "error": type(e).__name__}
            self._record({"id": f"final-{n}", "client": self.name, "op": op, "args": args, "final": True,
                          "node": n, "invoke": t, "complete": time.time(), "ok": bool(resp.get("ok")),
                          "result": resp.get("result")})
            out[n] = resp
        return out
