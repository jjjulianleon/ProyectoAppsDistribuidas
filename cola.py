"""Máquina de estados de la cola (M19).

Cada réplica aplica las entradas con commit del log de Raft, en el mismo
orden, con esta función. Como la función es determinista y todas parten de
estado_inicial(), todas las réplicas llegan al mismo estado.
"""


def estado_inicial():
    # aplicadas: request_id -> resultado. Si el cliente reintenta (por ejemplo,
    # porque cayó el líder), la misma operación puede quedar dos veces en el
    # log. Con este registro se aplica una sola vez y se devuelve el mismo
    # resultado (deduplicación, M05).
    return {"cola": [], "pos": 0, "aplicadas": {}}


def vista(estado):
    return {"cola": list(estado["cola"]), "actual": estado["pos"]}


def aplicar(estado, entrada):
    op, args, rid = entrada["op"], entrada["args"], entrada["id"]
    if op == "ver_cola":  # lectura: no cambia nada, no se deduplica
        return vista(estado)
    if rid in estado["aplicadas"]:
        return estado["aplicadas"][rid]
    if op == "agregar":
        estado["cola"].append(args["cancion"])
        res = len(estado["cola"]) - 1
    elif op == "saltar":
        # compare-and-swap: solo salta si quien pidió saltar estaba viendo la
        # misma posición. Si dos personas presionan "saltar" a la vez, las dos
        # mandan la misma pos; el log las ordena y solo la primera avanza.
        res = args["pos"] == estado["pos"] < len(estado["cola"])
        if res:
            estado["pos"] += 1
    else:
        raise ValueError(f"operación desconocida: {op}")
    estado["aplicadas"][rid] = res
    return res
