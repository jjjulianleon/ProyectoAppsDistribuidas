"""Provoca fallas en tus réplicas.

    python3 chaos.py kill NODO            # la réplica se cae (como apagarla)
    python3 chaos.py start NODO           # vuelve con su disco
    python3 chaos.py start NODO --empty   # vuelve sin estado: se borra su disco
    python3 chaos.py pause NODO           # se congela: no procesa nada
    python3 chaos.py partition n1 / n2 n3 # una partición separa n1 de n2 y n3
    python3 chaos.py delay NODO 300       # sus mensajes salen 300 ms tarde
    python3 chaos.py heal                 # quita partición, delay y pause
    python3 chaos.py leader               # dice qué réplica es líder ahora

En lugar de NODO puedes escribir `leader`: la réplica que dice ser líder con
el periodo más alto (según GET /status). Ejemplo: `chaos.py kill leader`.

Con Docker, kill, start y pause actúan sobre el contenedor. La partición y el
delay los aplica node.py en cada mensaje entre réplicas, igual en los dos
modos. El cliente llega a todas las réplicas aunque haya partición.
"""
import json
import sys
import time

import cluster


def faults():
    try:
        return json.loads((cluster.RUN / "faults.json").read_text())
    except (OSError, ValueError):
        return {}


def set_faults(f):
    (cluster.RUN / "faults.json").write_text(json.dumps(f))
    time.sleep(0.3)  # node.py relee el archivo cada 0.2 s


def leader(c):
    best = None
    for n, s in cluster.status(c).items():
        if s and s.get("role") == "leader":
            if best is None or (s.get("term") or 0) > (best[1] or 0):
                best = (n, s.get("term"))
    return best[0] if best else None


def resolve(c, name):
    if name == "leader":
        n = leader(c)
        if not n:
            sys.exit("No hay líder ahora.")
        return n
    if name not in c["names"]:
        sys.exit(f"No existe la réplica {name}.")
    return name


def main(argv):
    if not argv:
        sys.exit(__doc__)
    c = cluster.load()
    cmd, rest = argv[0], argv[1:]
    if cmd == "leader":
        print(leader(c) or "sin líder")
    elif cmd == "kill":
        n = resolve(c, rest[0])
        if c["mode"] == "docker":
            cluster.compose(c, "kill", n)
        else:
            cluster.stop_local(c, n)
            cluster.save(c)
        print("kill", n)
    elif cmd == "start":
        n = resolve(c, rest[0])
        if "--empty" in rest:
            (cluster.RUN / n / "disk.json").unlink(missing_ok=True)
        if c["mode"] == "docker":
            cluster.compose(c, "start", n)
        else:
            cluster.stop_local(c, n)
            cluster.start_local(c, n)
            cluster.save(c)
        cluster.wait_up(c, [n], 30)
        print("start", n, "(sin estado)" if "--empty" in rest else "")
    elif cmd == "pause":
        n = resolve(c, rest[0])
        if c["mode"] == "docker":
            cluster.compose(c, "pause", n)
        else:
            f = faults()
            f["paused"] = sorted(set(f.get("paused", [])) | {n})
            set_faults(f)
        print("pause", n)
    elif cmd == "partition":
        if "/" in rest:
            i = rest.index("/")
            groups = [[resolve(c, x) for x in rest[:i]], [resolve(c, x) for x in rest[i + 1:]]]
        else:  # un solo grupo: ese grupo contra el resto
            g = [resolve(c, x) for x in rest]
            groups = [g, [n for n in c["names"] if n not in g]]
        f = faults()
        f["partition"] = groups
        set_faults(f)
        print("partition", groups)
    elif cmd == "delay":
        n = resolve(c, rest[0])
        f = faults()
        f.setdefault("delay_ms", {})[n] = int(rest[1])
        set_faults(f)
        print("delay", n, rest[1], "ms")
    elif cmd == "heal":
        if c["mode"] == "docker":
            for n in c["names"]:
                cluster.compose(c, "unpause", n, check=False)
        set_faults({})
        print("heal")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
