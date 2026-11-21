"""Escenario normal: todas las operaciones, sin fallas.

    python3 cluster.py up --local
    python3 scenarios/normal.py
    python3 check.py run/normal.jsonl

Incluye el doble salto (dos clientes saltan a la vez sobre la misma canción:
solo uno salta) y la doble pausa (dos clientes pausan a la vez: queda
pausado, porque pausar fija el estado en vez de alternarlo).
"""
import threading
import time

from comun import esperar_lider, nuevo_cliente, paso

esperar_lider()
c = nuevo_cliente("c1", "normal")

paso("agregar 4 canciones")
for cancion in ["c1", "c2", "c3", "c4"]:
    print("agregar", cancion, "->", c.call("agregar", cancion=cancion).get("result"))
print("ver_cola ->", c.call("ver_cola").get("result"))

paso("doble salto: dos clientes saltan pos=0 a la vez")
resultados = {}


def saltar(nombre):
    resultados[nombre] = nuevo_cliente(nombre, "normal").call("saltar", pos=0).get("result")


hilos = [threading.Thread(target=saltar, args=(n,)) for n in ("c2", "c3")]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
print("saltar ->", resultados, "(solo uno debe ser True)")
print("ver_cola ->", c.call("ver_cola").get("result"))

paso("doble pausa: dos clientes pausan a la vez, después uno reanuda")
pausas = {}


def pausar(nombre):
    pausas[nombre] = nuevo_cliente(nombre, "normal").call("pausar").get("result")


hilos = [threading.Thread(target=pausar, args=(n,)) for n in ("c2", "c3")]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
print("pausar ->", pausas, "(los dos True: pausar fija el estado, no lo alterna)")
print("ver_cola ->", c.call("ver_cola").get("result"))
print("reanudar ->", c.call("reanudar").get("result"))

paso("likes en réplicas distintas (ana repite)")
for nodo, usuario in [("n1", "ana"), ("n2", "beto"), ("n3", "ana"), ("n3", "caro")]:
    c.call("like", node=nodo, cancion="c2", usuario=usuario)
print("ver_cola_rapida ->", c.call("ver_cola_rapida").get("result"))
print("likes c2 (puede estar atrasado) ->", c.call("likes", cancion="c2").get("result"))

paso("esperar gossip y leer likes en cada réplica")
time.sleep(2)
for n, r in c.final("likes", cancion="c2").items():
    print(n, "likes c2 =", r.get("result"))
