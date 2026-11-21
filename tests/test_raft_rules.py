import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raft_rules import aceptar_append, concede_voto, log_al_dia, nuevo_commit  # noqa: E402


class TestRaftRules(unittest.TestCase):
    def test_no_vota_dos_veces(self):
        self.assertFalse(concede_voto(3, "n2", "n3", 3, True))
        self.assertTrue(concede_voto(3, "n3", "n3", 3, True))
        self.assertTrue(concede_voto(3, None, "n3", 3, True))
        self.assertFalse(concede_voto(3, None, "n3", 3, False))

    def test_log_al_dia(self):
        self.assertTrue(log_al_dia(2, 5, 3, 1))  # periodo mayor gana aunque sea más corto
        self.assertFalse(log_al_dia(3, 5, 3, 4))
        self.assertTrue(log_al_dia(3, 5, 3, 5))

    def test_no_commit_periodo_viejo(self):
        self.assertEqual(nuevo_commit(3, [1, 2], {"n2": 2, "n3": 0}, 0, 3), 0)
        self.assertEqual(nuevo_commit(3, [1, 2, 3], {"n2": 3, "n3": 0}, 0, 3), 3)

    def test_sin_mayoria_no_hay_commit(self):
        self.assertEqual(nuevo_commit(1, [1, 1], {"n2": 0, "n3": 0}, 0, 3), 0)

    def test_append_repara_conflicto(self):
        log = [{"term": 1}, {"term": 2}, {"term": 2}]
        ok, nuevo = aceptar_append(log, 1, 1, [{"term": 3}])
        self.assertTrue(ok)
        self.assertEqual([e["term"] for e in nuevo], [1, 3])

    def test_append_viejo_no_recorta(self):
        log = [{"term": 1}, {"term": 1}, {"term": 1}]
        ok, nuevo = aceptar_append(log, 0, 0, [{"term": 1}])
        self.assertTrue(ok)
        self.assertEqual(len(nuevo), 3)

    def test_append_hueco(self):
        self.assertFalse(aceptar_append([], 2, 1, [])[0])
        self.assertFalse(aceptar_append([{"term": 1}], 1, 2, [])[0])


if __name__ == "__main__":
    unittest.main()
