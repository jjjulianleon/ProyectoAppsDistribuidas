import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spec  # noqa: E402


class TestSpec(unittest.TestCase):
    def test_like_mismo_usuario_cuenta_una_vez(self):
        s, _ = spec.apply(None, "like", {"cancion": "c1", "usuario": "ana"})
        s, _ = spec.apply(s, "like", {"cancion": "c1", "usuario": "ana"})
        self.assertEqual(spec.apply(s, "likes", {"cancion": "c1"})[1], 1)

    def test_saltar_coincide_con_cola(self):
        s, r = spec.apply(None, "agregar", {"cancion": "c1"})
        self.assertEqual(r, 0)
        s, r = spec.apply(s, "saltar", {"pos": 0})
        self.assertTrue(r)
        self.assertEqual(spec.apply(s, "ver_cola", {})[1], {"cola": ["c1"], "actual": 1})

    def test_claves(self):
        self.assertEqual(spec.key("like", {"cancion": "c1"}), "likes:c1")
        self.assertEqual(spec.key("saltar", {"pos": 0}), "cola")


if __name__ == "__main__":
    unittest.main()
