"""Escenario replica: cae un follower y después vuelve con su disco.

Muestra que la réplica que vuelve se pone al día: el líder le reenvía las
entradas que le faltan (reparación del log) y ella las aplica antes de
mostrarlas. Las operaciones linearizables siempre las responde el líder.
"""
import time

from comun import chaos, esperar_lider, nuevo_cliente, paso

lider = esperar_lider()
caida = next(n for n in ("n1", "n2", "n3") if n != lider)
c = nuevo_cliente("c1", "replica")
c.call("agregar", cancion="c1")

paso(f"kill {caida} (follower); el líder es {lider}")
chaos.main(["kill", caida])
for cancion in ["c2", "c3", "c4", "c5", "c6"]:
    print("agregar", cancion, "->", c.call("agregar", cancion=cancion).get("result"))
print("ver_cola ->", c.call("ver_cola").get("result"))

paso(f"start {caida} (vuelve con su disco)")
chaos.main(["start", caida])
time.sleep(3)
print(f"ver_cola pedida a {caida} (redirige al líder) ->", c.call("ver_cola", node=caida).get("result"))
r = c.call("ver_cola_rapida", node=caida).get("result")
print(f"ver_cola_rapida en {caida} ->", r)
print("¿se puso al día?", "sí" if r and len(r["cola"]) == 6 else "NO")
