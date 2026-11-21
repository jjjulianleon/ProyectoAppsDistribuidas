"""Puente entre el navegador y las réplicas.

    python3 gateway.py        # http://localhost:8080  (?parlante=1 reproduce)

El navegador no puede hablar directo con las réplicas (node.py no permite
pedidos de otra página, CORS). Este servidor sirve web/ y reenvía cada acción
con client.py. Por eso todo lo que se hace en la demo queda en
run/web.jsonl, y check.py lo puede revisar igual que un escenario.

No replica nada: si el gateway se cae, las réplicas siguen bien.
"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import cluster
from client import Client

AQUI = Path(__file__).resolve().parent
WEB = AQUI / "web"
PUERTO = 8080
OPS = {"agregar", "saltar", "ver_cola", "ver_cola_rapida", "like", "likes"}


def ruta_estatica(path):
    """Archivo de web/ que corresponde a path, o None. Nunca sale de web/."""
    p = unquote(urlsplit(path).path).lstrip("/") or "index.html"
    f = (WEB / p).resolve()
    if not f.is_relative_to(WEB.resolve()) or not f.is_file():
        return None
    return f


def limpiar_args(args):
    """Quita las claves que chocarían con Client.call(op, node=...): los args
    vienen del navegador y no se confía en ellos."""
    return {k: v for k, v in args.items() if k not in ("op", "node")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _enviar(self, code, body, tipo="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            try:
                return self._enviar(200, cluster.status(cluster.load()))
            except OSError:
                return self._enviar(503, {"error": "no hay cluster: python3 cluster.py up --local"})
        f = ruta_estatica(self.path)
        if not f:
            return self._enviar(404, {"error": "no existe"})
        self._enviar(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    def do_POST(self):
        op = self.path.removeprefix("/api/")
        if op not in OPS:
            return self._enviar(404, {"error": f"operación desconocida: {op}"})
        try:
            args = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if not isinstance(args, dict):
                raise ValueError
        except ValueError:
            return self._enviar(400, {"error": "JSON inválido"})
        try:
            # Un Client por pedido: `cluster.py up` regenera run/ y los puertos.
            c = Client("web", str(AQUI / "run" / "web.jsonl"), run_dir=str(AQUI / "run"), timeout=5)
        except OSError:
            return self._enviar(503, {"ok": False, "error": "no hay cluster"})
        self._enviar(200, c.call(op, **limpiar_args(args)))


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else PUERTO
    print(f"JamQ en http://localhost:{puerto}  (parlante: http://localhost:{puerto}/?parlante=1)")
    ThreadingHTTPServer(("0.0.0.0", puerto), Handler).serve_forever()
