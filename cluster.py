"""Levanta y apaga tus réplicas.

    python3 cluster.py up            # 3 réplicas en contenedores (Docker)
    python3 cluster.py up -n 5       # 5 réplicas
    python3 cluster.py up --local    # las mismas réplicas como procesos locales, sin Docker
    python3 cluster.py status        # rol y periodo de cada réplica
    python3 cluster.py down          # apaga todo; guarda los historiales y borra run/

Antes de borrar run/ (en down o en un nuevo up), cluster.py copia cada
historial run/*.jsonl y cada run/NODO/roles.log a historiales/FECHA-HORA/.
Revisa esa copia con: python3 check.py historiales/FECHA-HORA/escenario.jsonl

Cada réplica guarda su disco en run/NODO/disk.json y su log en
run/NODO/node.log. Los dos modos corren el mismo node.py y tu mismo app.py.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "run"
PROJECT = "proyecto"
IMAGE = "python:3.12-slim"
BASE_PORT = 8001


def load():
    return json.loads((RUN / "cluster.json").read_text())


def save(c):
    (RUN / "cluster.json").write_text(json.dumps(c, indent=2))


def compose(c, *args, check=True):
    cmd = ["docker", "compose", "-f", str(RUN / "compose.yaml"), "-p", PROJECT, *args]
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def write_compose(names):
    inner = ",".join(f"{n}=http://{n}:8000" for n in names)
    lines = ["services:"]
    for i, n in enumerate(names):
        lines += [
            f"  {n}:",
            f"    image: {IMAGE}",
            "    working_dir: /app",
            f"    command: python -u node.py {n}",
            "    volumes:",
            f"      - {HERE.as_posix()}:/app",
            "    environment:",
            f"      NODE_ID: {n}",
            f"      NODES: \"{inner}\"",
            "      PORT: \"8000\"",
            "      RUN_DIR: /app/run",
            "    ports:",
            f"      - \"{BASE_PORT + i}:8000\"",
        ]
    (RUN / "compose.yaml").write_text("\n".join(lines) + "\n")


def start_local(c, n):
    env = {**os.environ, "NODE_ID": n, "NODES": c["local_nodes"], "RUN_DIR": str(RUN)}
    (RUN / n).mkdir(parents=True, exist_ok=True)
    out = open(RUN / n / "stdout.log", "a")
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    p = subprocess.Popen([sys.executable, "-u", str(HERE / "node.py"), n], env=env, stdout=out, stderr=out, cwd=HERE, **kw)
    c["pids"][n] = p.pid


def stop_local(c, n):
    pid = c["pids"].pop(n, None)
    if pid:
        try:
            os.kill(pid, signal.SIGKILL if os.name != "nt" else signal.SIGTERM)
        except OSError:
            pass


def status(c):
    out = {}
    for n, url in c["host_nodes"].items():
        try:
            with urllib.request.urlopen(url + "/status", timeout=1) as r:
                out[n] = json.loads(r.read())
        except Exception:
            out[n] = None
    return out


def wait_up(c, names, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        s = status(c)
        if all(s.get(n) for n in names):
            return True
        time.sleep(0.3)
    return False


def up(n, local):
    if RUN.exists():
        down(quiet=True)
    RUN.mkdir()
    names = [f"n{i + 1}" for i in range(n)]
    c = {"mode": "local" if local else "docker", "names": names, "pids": {},
         "host_nodes": {m: f"http://127.0.0.1:{BASE_PORT + i}" for i, m in enumerate(names)},
         "local_nodes": ",".join(f"{m}=http://127.0.0.1:{BASE_PORT + i}" for i, m in enumerate(names))}
    (RUN / "faults.json").write_text("{}")
    if local:
        for m in names:
            start_local(c, m)
    else:
        write_compose(names)
        compose(c, "up", "-d")
    save(c)
    if not wait_up(c, names):
        sys.exit("Las réplicas no respondieron. Revisa run/NODO/stdout.log o `docker compose logs`.")
    print(f"{n} réplicas listas ({c['mode']}):", ", ".join(f"{m} {u}" for m, u in c["host_nodes"].items()))


def keep_histories():
    """Copia los historiales y los roles.log de run/ a historiales/FECHA-HORA/."""
    files = list(RUN.glob("*.jsonl"))
    if not files:
        return None
    dest = HERE / "historiales" / time.strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dest / f.name)
    for roles in RUN.glob("*/roles.log"):
        (dest / roles.parent.name).mkdir(exist_ok=True)
        shutil.copy2(roles, dest / roles.parent.name / "roles.log")
    return dest


def down(quiet=False):
    if (RUN / "cluster.json").exists():
        c = load()
        if c["mode"] == "docker":
            compose(c, "down", "-t", "1", check=False)
        else:
            for m in list(c["pids"]):
                stop_local(c, m)
    kept = keep_histories() if RUN.exists() else None
    shutil.rmtree(RUN, ignore_errors=True)
    if kept:
        print("Historiales guardados en", kept.relative_to(HERE))
    if not quiet:
        print("Réplicas apagadas.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["up", "down", "status"])
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--local", action="store_true")
    a = ap.parse_args()
    if a.cmd == "up":
        if a.n < 3:
            sys.exit("Usa al menos 3 réplicas.")
        up(a.n, a.local)
    elif a.cmd == "down":
        down()
    else:
        for m, s in status(load()).items():
            print(m, s if s else "sin respuesta")
