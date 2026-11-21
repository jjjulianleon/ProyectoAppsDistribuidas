import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cola import aplicar, estado_inicial, vista  # noqa: E402


def agregar(i, c):
    return {"id": i, "op": "agregar", "args": {"cancion": c}}


class TestCola(unittest.TestCase):
    def test_agregar_devuelve_indice(self):
        e = estado_inicial()
        self.assertEqual(aplicar(e, agregar("a", "c1")), 0)
        self.assertEqual(aplicar(e, agregar("b", "c1")), 1)
        self.assertEqual(vista(e), {"cola": ["c1", "c1"], "actual": 0, "pausado": False})

    def test_saltar_cas(self):  # dos clientes con la misma pos: solo uno salta
        e = estado_inicial()
        aplicar(e, agregar("a", "c1"))
        aplicar(e, agregar("b", "c2"))
        self.assertTrue(aplicar(e, {"id": "s1", "op": "saltar", "args": {"pos": 0}}))
        self.assertFalse(aplicar(e, {"id": "s2", "op": "saltar", "args": {"pos": 0}}))
        self.assertEqual(vista(e)["actual"], 1)

    def test_saltar_al_final(self):
        e = estado_inicial()
        self.assertFalse(aplicar(e, {"id": "s", "op": "saltar", "args": {"pos": 0}}))

    def test_pausar_dos_veces_queda_pausado(self):  # fija el estado, no lo alterna
        e = estado_inicial()
        self.assertTrue(aplicar(e, {"id": "p1", "op": "pausar", "args": {}}))
        self.assertTrue(aplicar(e, {"id": "p2", "op": "pausar", "args": {}}))
        self.assertTrue(vista(e)["pausado"])
        self.assertFalse(aplicar(e, {"id": "r1", "op": "reanudar", "args": {}}))
        self.assertFalse(vista(e)["pausado"])

    def test_saltar_reanuda(self):
        e = estado_inicial()
        aplicar(e, agregar("a", "c1"))
        aplicar(e, {"id": "p", "op": "pausar", "args": {}})
        aplicar(e, {"id": "s", "op": "saltar", "args": {"pos": 0}})
        self.assertFalse(vista(e)["pausado"])

    def test_mismo_id_se_aplica_una_vez(self):
        e = estado_inicial()
        x = agregar("a", "c1")
        self.assertEqual(aplicar(e, x), 0)
        self.assertEqual(aplicar(e, dict(x)), 0)
        self.assertEqual(vista(e)["cola"], ["c1"])


if __name__ == "__main__":
    unittest.main()
