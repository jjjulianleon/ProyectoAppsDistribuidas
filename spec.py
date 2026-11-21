"""JamQ como si hubiera una sola copia. check.py lo usa para revisar historiales.

Está escrito aparte de cola.py a propósito: es la referencia de "una sola
copia". Si la app tuviera un bug en cola.py, usar el mismo código aquí lo
escondería.

Garantías (ver la tabla de operaciones del reporte):
- agregar, saltar, ver_cola: linearizable. Pasan por el log de Raft: todos ven
  la cola en el mismo orden y saltar es un compare-and-swap.
- ver_cola_rapida: eventual. Lee el estado local de una réplica, sin el líder;
  puede estar atrasada.
- like, likes: eventual (strong eventual consistency). Cada réplica guarda un
  G-set de usuarios por canción y se lo pasan por gossip.
"""

GUARANTEE = {
    "agregar": "linearizable",
    "saltar": "linearizable",
    "ver_cola": "linearizable",
    "ver_cola_rapida": "eventual",
    "like": "eventual",
    "likes": "eventual",
}

READS = {"ver_cola", "ver_cola_rapida", "likes"}

INITIAL = None


def key(op, args):
    """La cola es un solo objeto; cada canción tiene su propio set de likes."""
    if op in ("like", "likes"):
        return "likes:" + args["cancion"]
    return "cola"


def apply(state, op, args):
    if op in ("like", "likes"):
        usuarios = state or []  # lista ordenada: un set no se guarda en JSON
        if op == "like":
            return sorted(set(usuarios) | {args["usuario"]}), "ok"
        return usuarios, len(usuarios)
    s = state or {"cola": [], "pos": 0}
    if op == "agregar":
        cola = s["cola"] + [args["cancion"]]
        return {"cola": cola, "pos": s["pos"]}, len(cola) - 1
    if op == "saltar":
        if args["pos"] == s["pos"] < len(s["cola"]):
            return {"cola": s["cola"], "pos": s["pos"] + 1}, True
        return s, False
    if op in ("ver_cola", "ver_cola_rapida"):
        return s, {"cola": s["cola"], "actual": s["pos"]}
    raise ValueError(f"operación desconocida: {op}")
