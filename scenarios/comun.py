"""Ayudas compartidas por los escenarios."""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import chaos  # noqa: E402
import cluster  # noqa: E402
from client import Client  # noqa: E402


def esperar_lider(timeout=15):
    """Espera a que alguna réplica diga ser líder y devuelve su nombre."""
    fin = time.time() + timeout
    while time.time() < fin:
        n = chaos.leader(cluster.load())
        if n:
            return n
        time.sleep(0.3)
    sys.exit("No hubo líder a tiempo.")


def nuevo_cliente(nombre, escenario, timeout=10.0):
    return Client(nombre, str(RAIZ / "run" / f"{escenario}.jsonl"), run_dir=str(RAIZ / "run"), timeout=timeout)


def paso(texto):
    print(f"\n== {texto}", flush=True)
