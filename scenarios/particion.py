"""Escenario particion: el líder queda solo contra las otras dos réplicas.

Lo que dice la tabla:
- agregar (Raft): el lado con menos réplicas no puede tener commit y no
  confirma; el lado con mayoría elige un líder nuevo y sigue.
- like (G-set): los dos lados aceptan; al unirse la red, el gossip junta los
  likes y todas las réplicas terminan iguales.
"""
import time

from comun import chaos, esperar_lider, nuevo_cliente, paso

viejo = esperar_lider()
otros = [n for n in ("n1", "n2", "n3") if n != viejo]
c = nuevo_cliente("c1", "particion")
c.call("agregar", cancion="c1")

paso(f"partition {viejo} / {' '.join(otros)}")
chaos.main(["partition", viejo, "/", *otros])
time.sleep(4)
print("líder del lado mayoritario:", esperar_lider())

paso(f"agregar en {viejo} (lado minoritario): debe fallar")
corto = nuevo_cliente("c2", "particion", timeout=6)
print("->", corto.call("agregar", node=viejo, cancion="c2"))
paso(f"agregar en {otros[0]} (lado mayoritario): debe funcionar")
print("->", c.call("agregar", node=otros[0], cancion="c3"))

paso("likes en los dos lados")
print("like en", viejo, "->", c.call("like", node=viejo, cancion="c1", usuario="minoria").get("result"))
print("like en", otros[0], "->", c.call("like", node=otros[0], cancion="c1", usuario="mayoria").get("result"))
print("likes c1 en", viejo, "->", c.call("likes", node=viejo, cancion="c1").get("result"))

paso("heal")
chaos.main(["heal"])
time.sleep(3)
for n, r in c.final("likes", cancion="c1").items():
    print(n, "likes c1 =", r.get("result"))
print("ver_cola ->", c.call("ver_cola").get("result"))
