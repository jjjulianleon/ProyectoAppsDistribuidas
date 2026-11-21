"""Escenario lider: cae el líder mientras 3 clientes agregan a la vez.

Muestra que se elige otro líder con un periodo mayor, que ninguna canción
confirmada se pierde (check.py: linearizability) y que nunca hay dos líderes
en el mismo periodo (check.py: líderes).
"""
import threading
import time

from comun import chaos, cluster, esperar_lider, nuevo_cliente, paso

lider = esperar_lider()
confirmadas = []


def cliente(nombre):
    c = nuevo_cliente(nombre, "lider")
    for i in range(6):
        r = c.call("agregar", cancion=f"{nombre}-{i}")
        if r.get("ok"):
            confirmadas.append(f"{nombre}-{i}")
        time.sleep(0.3)


paso(f"3 clientes agregando; el líder es {lider}")
hilos = [threading.Thread(target=cliente, args=(n,)) for n in ("c1", "c2", "c3")]
for h in hilos:
    h.start()
time.sleep(1.5)
paso(f"kill leader ({lider})")
chaos.main(["kill", "leader"])
for h in hilos:
    h.join()
nuevo = esperar_lider()
print("nuevo líder:", nuevo, cluster.status(cluster.load())[nuevo])

paso(f"start {lider} (vuelve como follower)")
chaos.main(["start", lider])
time.sleep(2)
cola = nuevo_cliente("c1", "lider").call("ver_cola").get("result")["cola"]
perdidas = [s for s in confirmadas if s not in cola]
print(f"confirmadas: {len(confirmadas)}, en la cola: {len(cola)}, perdidas: {perdidas or 'ninguna'}")
for n, s in cluster.status(cluster.load()).items():
    print(n, s)
