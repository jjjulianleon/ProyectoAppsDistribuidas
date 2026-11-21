"""Escenario de falla (FUERA del modelo): una réplica vuelve sin estado.

n3 queda aislada, recibe un like y lo confirma. Antes de que el gossip lo
pase a otra réplica, n3 se cae y vuelve con el disco borrado (--empty). Ese
like solo existía en n3: se pierde.

Supuesto que rompe: el modelo es crash-recovery CON disco. Volver sin estado
está fuera del modelo. Por la misma razón, Raft tampoco es seguro así: n3
olvida su voto y podría votar dos veces en un periodo.

Resultado esperado de check.py: NO CONVERGE (un like con "ok" que no está).
"""
import time

from comun import chaos, esperar_lider, nuevo_cliente, paso

esperar_lider()
c = nuevo_cliente("c1", "falla")

paso("partition n3 / n1 n2")
chaos.main(["partition", "n3", "/", "n1", "n2"])
print("like en n3 ->", c.call("like", node="n3", cancion="c9", usuario="solo_n3").get("result"))

paso("kill n3 antes del gossip, heal y start n3 --empty")
chaos.main(["kill", "n3"])
chaos.main(["heal"])
chaos.main(["start", "n3", "--empty"])
time.sleep(3)
for n, r in c.final("likes", cancion="c9").items():
    print(n, "likes c9 =", r.get("result"))
print("El like confirmado se perdió: estaba solo en el disco de n3.")
