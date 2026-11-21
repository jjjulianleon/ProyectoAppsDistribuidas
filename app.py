"""JamQ: una réplica de la cola musical compartida.

Dos mecanismos, uno por tipo de operación:

1. Raft (M20) para agregar, saltar, pausar, reanudar y ver_cola (linearizable). Un líder elegido
   por mayoría numera las operaciones en un log. Una entrada tiene commit
   cuando la tiene una mayoría, y cada réplica aplica las entradas con commit,
   en orden, a la máquina de estados de cola.py (M19).
2. Un G-set con gossip (M11, M14, M17) para los likes (eventual). Cualquier
   réplica acepta un like y lo guarda; cada 0.5 s le manda su set a otra
   réplica al azar, que hace la unión. La unión es conmutativa, asociativa e
   idempotente: no importa el orden ni si un mensaje llega dos veces.

node.py llama a este código en un solo hilo: no hacen falta locks.
"""
import random

from cola import aplicar, estado_inicial, vista
from node import Node
from raft_rules import aceptar_append, concede_voto, log_al_dia, nuevo_commit

ELECCION = (1.5, 3.0)  # timeout de elección aleatorio, para que no empaten todos
HEARTBEAT = 0.3        # el líder avisa que sigue vivo (append vacío)
GOSSIP = 0.5           # cada cuánto se mandan los likes
MAX_ENTRADAS = 100     # entradas por mensaje de append, para no armar mensajes enormes

RAFT = {"agregar", "saltar", "pausar", "reanudar", "ver_cola"}


class App(Node):
    # ---------------------------------------------------------------- arranque
    def start(self):
        # En disco (sobrevive a kill): periodo, voto, log y likes. El voto y el
        # periodo van al disco para no votar dos veces en un periodo.
        d = self.disk
        d.setdefault("term", 0)
        d.setdefault("voted_for", None)
        d.setdefault("log", [])
        d.setdefault("likes", {})  # cancion -> lista de usuarios (G-set)
        # Volátil: se reconstruye. commit empieza en 0 y la cola se vuelve a
        # armar a medida que el líder avisa hasta dónde hay commit.
        self.role = "follower"
        self.lider = None
        self.commit = 0
        self.aplicado = 0
        self.estado = estado_inicial()
        self.pendientes = {}  # largo del log al agregar la entrada -> request_id
        self.votos = set()
        self.match, self.next_len = {}, {}
        self.proximo_hb = 0.0
        self.proximo_gossip = self.now() + GOSSIP
        self._reiniciar_eleccion()

    def status(self):
        return {"role": self.role, "term": self.disk["term"]}

    # ---------------------------------------------------------------- helpers
    @property
    def log_(self):
        return self.disk["log"]

    def _ultimo_term(self):
        return self.log_[-1]["term"] if self.log_ else 0

    def _reiniciar_eleccion(self):
        self.deadline = self.now() + random.uniform(*ELECCION)

    def _mayoria(self):
        return len(self.nodes) // 2 + 1

    def _fallar_pendientes(self, motivo):
        # Si dejo de ser líder, mis entradas pendientes pueden no tener commit
        # nunca (otro líder puede borrarlas). Nunca respondo "ok" sin commit:
        # respondo que no pude y el cliente reintenta (con el mismo id).
        for rid in self.pendientes.values():
            self.reply(rid, {"ok": False, "error": motivo})
        self.pendientes.clear()

    def _ser_follower(self, term):
        if term > self.disk["term"]:
            self.disk["term"], self.disk["voted_for"] = term, None
            self.save()
        if self.role == "leader":
            self._fallar_pendientes("ya no soy líder")
        self.role = "follower"
        self._reiniciar_eleccion()

    # ---------------------------------------------------------------- ticks
    def on_tick(self):
        ahora = self.now()
        if self.role == "leader":
            if ahora >= self.proximo_hb:
                self._replicar()
        elif ahora >= self.deadline:
            self._empezar_eleccion()
        if ahora >= self.proximo_gossip and self.peers:
            self.proximo_gossip = ahora + GOSSIP
            self.send(random.choice(self.peers), {"t": "gossip", "likes": self.disk["likes"]})

    def _empezar_eleccion(self):
        # No supe del líder a tiempo: subo de periodo, voto por mí y pido votos.
        self.disk["term"] += 1
        self.disk["voted_for"] = self.id
        self.save()
        self.role, self.lider, self.votos = "candidate", None, {self.id}
        self._reiniciar_eleccion()
        self.log("elección, periodo", self.disk["term"])
        self.broadcast({"t": "pedir_voto", "term": self.disk["term"],
                        "last_term": self._ultimo_term(), "len": len(self.log_)})

    def _ser_lider(self):
        self.role, self.lider = "leader", self.id
        self.log("soy líder, periodo", self.disk["term"])
        self.match = {p: 0 for p in self.peers}
        self.next_len = {p: len(self.log_) for p in self.peers}
        # Entrada vacía del periodo nuevo (Raft §8): las entradas de periodos
        # anteriores solo tienen commit cuando hay commit de una del periodo
        # actual. Sin esto, quedarían esperando al próximo pedido.
        self.log_.append({"term": self.disk["term"], "id": f"noop-{self.id}-{self.disk['term']}",
                          "op": "noop", "args": {}})
        self.save()
        self._replicar()

    def _replicar(self):
        self.proximo_hb = self.now() + HEARTBEAT
        for p in self.peers:
            self._append_a(p)

    def _append_a(self, p):
        prev = self.next_len[p]
        self.send(p, {"t": "append", "term": self.disk["term"], "prev_len": prev,
                      "prev_term": self.log_[prev - 1]["term"] if prev else 0,
                      "entradas": self.log_[prev:prev + MAX_ENTRADAS], "commit": self.commit})

    def _aplicar_commit(self):
        # Aplica en orden las entradas con commit. Si soy líder y alguien
        # espera esa entrada, le respondo ahora: ya es segura.
        while self.aplicado < self.commit:
            e = self.log_[self.aplicado]
            self.aplicado += 1
            res = None if e["op"] == "noop" else aplicar(self.estado, e)
            rid = self.pendientes.pop(self.aplicado, None)
            if rid is not None:
                self.reply(rid, {"ok": True, "result": res})

    # ---------------------------------------------------------------- mensajes
    def on_message(self, src, msg):
        t = msg["t"]
        if t == "gossip":
            return self._unir_likes(msg["likes"])
        term = msg["term"]
        if term > self.disk["term"]:
            self._ser_follower(term)
            self.lider = None
        if t == "pedir_voto":
            al_dia = log_al_dia(self._ultimo_term(), len(self.log_), msg["last_term"], msg["len"])
            ok = concede_voto(self.disk["term"], self.disk["voted_for"], src, term, al_dia)
            if ok:
                self.disk["voted_for"] = src
                self.save()  # el voto va al disco ANTES de responder
                self._reiniciar_eleccion()
            self.send(src, {"t": "voto", "term": self.disk["term"], "ok": ok})
        elif t == "voto":
            if self.role == "candidate" and term == self.disk["term"] and msg["ok"]:
                self.votos.add(src)
                if len(self.votos) >= self._mayoria():
                    self._ser_lider()
        elif t == "append":
            self._recibir_append(src, msg)
        elif t == "append_resp":
            self._recibir_resp(src, msg)

    def _recibir_append(self, src, msg):
        if msg["term"] < self.disk["term"]:
            # Mensaje de un líder de un periodo viejo: lo ignoro y le digo mi
            # periodo, para que se entere de que ya no es líder.
            return self.send(src, {"t": "append_resp", "term": self.disk["term"], "ok": False, "len": 0})
        if self.role != "follower":
            self._ser_follower(msg["term"])
        self.lider = src
        self._reiniciar_eleccion()
        ok, nuevo = aceptar_append(self.log_, msg["prev_len"], msg["prev_term"], msg["entradas"])
        largo = msg["prev_len"] + len(msg["entradas"]) if ok else len(self.log_)
        if ok:
            if nuevo != self.log_:
                self.disk["log"] = nuevo
                self.save()  # al disco antes de confirmar: el líder cuenta esta copia
            self.commit = max(self.commit, min(msg["commit"], largo))
            self._aplicar_commit()
        self.send(src, {"t": "append_resp", "term": self.disk["term"], "ok": ok, "len": largo})

    def _recibir_resp(self, src, msg):
        if self.role != "leader" or msg["term"] != self.disk["term"]:
            return
        if msg["ok"]:
            self.match[src] = max(self.match[src], msg["len"])
            self.next_len[src] = self.match[src]
            nuevo = nuevo_commit(self.disk["term"], [e["term"] for e in self.log_],
                                 self.match, self.commit, len(self.nodes))
            if nuevo > self.commit:
                self.commit = nuevo
                self._aplicar_commit()
            if self.next_len[src] < len(self.log_):
                self._append_a(src)
        else:
            # Reparación: el follower no tiene la entrada anterior. Retrocedo
            # (como mucho hasta su largo) y reenvío. Así una réplica que vuelve
            # sin estado recibe el log completo.
            self.next_len[src] = max(0, min(self.next_len[src] - 1, msg["len"]))
            self._append_a(src)

    def _unir_likes(self, otros):
        cambio = False
        for cancion, usuarios in otros.items():
            mios = self.disk["likes"].setdefault(cancion, [])
            nuevos = set(usuarios) - set(mios)
            if nuevos:
                mios.extend(sorted(nuevos))
                cambio = True
        if cambio:
            self.save()

    # ---------------------------------------------------------------- clientes
    def on_request(self, req):
        op, a = req.op, req.args
        if op == "like":
            if not isinstance(a.get("cancion"), str) or not isinstance(a.get("usuario"), str):
                return {"ok": False, "error": "like necesita cancion y usuario"}
            self._unir_likes({a["cancion"]: [a["usuario"]]})
            return {"ok": True, "result": "ok"}
        if op == "likes":
            return {"ok": True, "result": len(self.disk["likes"].get(a.get("cancion"), []))}
        if op == "ver_cola_rapida" or (op == "ver_cola" and a.get("local")):
            return {"ok": True, "result": vista(self.estado)}
        if op not in RAFT:
            return {"ok": False, "error": f"operación desconocida: {op}"}
        if op == "agregar" and not isinstance(a.get("cancion"), str):
            return {"ok": False, "error": "agregar necesita cancion"}
        if op == "saltar" and not isinstance(a.get("pos"), int):
            return {"ok": False, "error": "saltar necesita pos"}
        if self.role != "leader":
            if self.lider and self.lider != self.id:
                return {"redirect": self.lider}
            return {"ok": False, "error": "sin líder"}
        if req.id in self.estado["aplicadas"]:  # reintento de algo ya aplicado
            return {"ok": True, "result": self.estado["aplicadas"][req.id]}
        self.log_.append({"term": self.disk["term"], "id": req.id, "op": op, "args": a})
        self.save()
        self.pendientes[len(self.log_)] = req.id
        self._replicar()  # no espero al próximo heartbeat: menos latencia
        return None  # respondo en _aplicar_commit, cuando tenga commit
