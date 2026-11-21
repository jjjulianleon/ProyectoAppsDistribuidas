"""Revisa un historial de client.py contra spec.py.

    python3 check.py run/historial.jsonl
    python3 check.py run/historial.jsonl --spec mi_spec.py

Revisa:
- linearizability de las operaciones marcadas "linearizable" en spec.py,
  objeto por objeto (spec.key);
- convergencia de las operaciones "eventual": las lecturas finales
  (client.final) dan lo mismo en todas las réplicas, y ese valor sale de
  aplicar las escrituras del historial en algún orden (por ejemplo, el de
  LWW). Si tu diseño da un valor que una sola copia no puede dar (varios
  valores a la vez, como multi-value), define spec.converged_ok;
- líderes: nunca hay dos réplicas líderes en el mismo periodo (run/*/roles.log);
- costo: latencia por operación y el mayor tiempo sin respuestas ok.

Una operación sin respuesta ("ok": false) pudo pasar o no: el checker prueba
las dos posibilidades. Devuelve código 1 si encuentra una violación.
"""
import argparse
import importlib.util
import itertools
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

DEADLINE = 20.0  # segundos por objeto


def load_spec(path):
    s = importlib.util.spec_from_file_location("spec", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def frozen(x):
    return json.dumps(x, sort_keys=True)


def linearizable(ops, spec):
    """Busca un orden que respete el tiempo real y spec.apply.
    Devuelve True, False o None (no terminó a tiempo)."""
    inf = float("inf")
    ops = [o for o in ops if o["ok"] or o["op"] not in spec.READS]
    must = frozenset(i for i, o in enumerate(ops) if o["ok"])
    end = [o["complete"] if o["ok"] else inf for o in ops]
    seen, stop = set(), time.time() + DEADLINE
    sys.setrecursionlimit(max(10000, 4 * len(ops) + 100))

    def go(done, state):
        if must <= done:
            return True
        if time.time() > stop:
            raise TimeoutError
        k = (done, frozen(state))
        if k in seen:
            return False
        seen.add(k)
        horizon = min(end[i] for i in range(len(ops)) if i not in done)
        for i, o in enumerate(ops):
            if i in done or o["invoke"] > horizon:
                continue
            new, res = spec.apply(state, o["op"], o["args"])
            if o["ok"] and frozen(res) != frozen(o["result"]):
                continue
            if go(done | {i}, new):
                return True
        return False

    try:
        return go(frozenset(), spec.INITIAL)
    except (TimeoutError, RecursionError):
        return None


def converged(finals, updates, spec):
    """finals: lecturas finales de un objeto. updates: escrituras del objeto."""
    if not finals or not all(f["ok"] for f in finals):
        return False, "alguna réplica no respondió la lectura final"
    vals = {frozen(f["result"]) for f in finals}
    if len(vals) > 1:
        return False, "las réplicas terminaron distintas: " + ", ".join(
            f"{f['node']}={f['result']}" for f in finals)
    sure = [u for u in sorted(updates, key=lambda u: u["invoke"]) if u["ok"]]
    maybe = [u for u in updates if not u["ok"]][:12]
    f0 = finals[0]

    def gives(order):
        state = spec.INITIAL
        for u in order:
            state, _ = spec.apply(state, u["op"], u["args"])
        _, res = spec.apply(state, f0["op"], f0["args"])
        return frozen(res) == frozen(f0["result"])

    for r in range(len(maybe) + 1):
        for extra in itertools.combinations(maybe, r):
            applied = sorted(sure + list(extra), key=lambda u: u["invoke"])
            if hasattr(spec, "converged_ok"):
                if spec.converged_ok(applied, f0["result"]):
                    return True, f"todas las réplicas = {f0['result']} (spec.converged_ok)"
            elif gives(applied):
                return True, f"todas las réplicas = {f0['result']}"
    if not hasattr(spec, "converged_ok"):
        # Como en LWW: la marca, no la hora de inicio, decide qué escritura
        # queda al final. Probamos cada escritura como la última.
        for u in sure + maybe:
            if gives([v for v in sure if v is not u] + [u]):
                return True, f"todas las réplicas = {f0['result']} (con {u['op']} {u['args']} al final)"
    return False, f"todas dan {f0['result']}, pero eso no sale de las escrituras del historial"


def leaders(run_dir):
    by_term = defaultdict(set)
    logs = list(Path(run_dir).glob("*/roles.log"))
    if not logs:
        return None, {}
    for p in logs:
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r.get("role") == "leader":
                by_term[r.get("term")].add(r["node"])
    # Sin periodo (term None) no se puede saber si dos líderes fueron a la vez.
    bad = {t: sorted(n) for t, n in by_term.items() if t is not None and len(n) > 1}
    return by_term, bad


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("history")
    ap.add_argument("--spec", default=str(Path(__file__).with_name("spec.py")))
    ap.add_argument("--run", default=None, help="carpeta run/ con roles.log (por defecto, la del historial)")
    a = ap.parse_args()
    spec = load_spec(a.spec)
    hist = [json.loads(l) for l in Path(a.history).read_text().splitlines() if l.strip()]
    ops = [h for h in hist if not h.get("final")]
    finals = [h for h in hist if h.get("final")]
    failed = False

    print(f"Historial: {len(ops)} operaciones ({sum(o['ok'] for o in ops)} con respuesta ok), "
          f"{len(finals)} lecturas finales")
    unknown = sorted({o["op"] for o in ops} - set(spec.GUARANTEE))
    if unknown:
        print("  aviso: operaciones sin garantía en spec.py:", ", ".join(unknown))

    print("\nLinearizability")
    groups = defaultdict(list)
    for o in ops:
        if spec.GUARANTEE.get(o["op"]) == "linearizable":
            groups[frozen(spec.key(o["op"], o["args"]))].append(o)
    if not groups:
        print("  (ninguna operación linearizable)")
    for k, g in sorted(groups.items()):
        v = linearizable(g, spec)
        label = {True: "cumple", False: "NO CUMPLE", None: "no verificado (muy largo)"}[v]
        print(f"  objeto {json.loads(k)}: {len(g)} operaciones — {label}")
        failed |= v is False

    print("\nConvergencia")
    ev = defaultdict(lambda: {"finals": [], "updates": []})
    for o in ops:
        if spec.GUARANTEE.get(o["op"]) == "eventual" and o["op"] not in spec.READS:
            ev[frozen(spec.key(o["op"], o["args"]))]["updates"].append(o)
    for f in finals:
        if spec.GUARANTEE.get(f["op"]) == "eventual":
            ev[frozen(spec.key(f["op"], f["args"]))]["finals"].append(f)
    for o in ops:  # escrituras no eventuales del mismo objeto que una lectura eventual
        k = frozen(spec.key(o["op"], o["args"]))
        if k in ev and spec.GUARANTEE.get(o["op"]) != "eventual" and o["op"] not in spec.READS:
            ev[k]["updates"].append(o)
    if not ev:
        print("  (ninguna operación eventual)")
    for k, d in sorted(ev.items()):
        if not d["finals"]:
            print(f"  objeto {json.loads(k)}: sin lecturas finales (usa client.final después de heal)")
            continue
        ok, why = converged(d["finals"], d["updates"], spec)
        print(f"  objeto {json.loads(k)}: {'converge' if ok else 'NO CONVERGE'} — {why}")
        failed |= not ok

    print("\nLíderes")
    run_dir = a.run or Path(a.history).parent
    by_term, bad = leaders(run_dir)
    if by_term is None:
        print(f"  aviso: no hay roles.log en {run_dir}/NODO/; no se revisaron los líderes. "
              "Usa --run con la carpeta del escenario.")
    elif not by_term:
        print("  (ninguna réplica dijo ser líder)")
    elif bad:
        for t, ns in sorted(bad.items()):
            print(f"  periodo {t}: DOS LÍDERES {', '.join(ns)}")
        failed = True
    else:
        timed = {t: n for t, n in by_term.items() if t is not None}
        if timed:
            print("  un líder por periodo — cumple (" + ", ".join(
                f"periodo {t}: {next(iter(n))}" for t, n in sorted(timed.items())) + ")")
    if by_term and None in by_term:
        print(f"  líderes sin periodo: {', '.join(sorted(by_term[None]))}; check.py no sabe si "
              "fueron a la vez. Muéstralo con tu escenario.")

    print("\nCosto")
    for op in sorted({o["op"] for o in ops}):
        lat = [(o["complete"] - o["invoke"]) * 1000 for o in ops if o["op"] == op and o["ok"]]
        done = sorted(o["complete"] for o in ops if o["op"] == op and o["ok"])
        span = [o["invoke"] for o in ops if o["op"] == op]
        gaps = [b - a for a, b in zip(done, done[1:])]
        n_fail = sum(1 for o in ops if o["op"] == op and not o["ok"])
        if lat:
            print(f"  {op}: {len(lat)} ok, {n_fail} sin respuesta, latencia p50 {pct(lat, .5):.0f} ms, "
                  f"p95 {pct(lat, .95):.0f} ms, mayor tiempo sin respuestas ok {max(gaps, default=0):.1f} s")
        else:
            print(f"  {op}: 0 ok, {n_fail} sin respuesta")

    print("\nResultado:", "VIOLACIÓN" if failed else "sin violaciones")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
