import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gateway  # noqa: E402


class TestGateway(unittest.TestCase):
    def test_no_sale_de_web(self):
        self.assertIsNone(gateway.ruta_estatica("/musica/../../app.py"))
        self.assertIsNone(gateway.ruta_estatica("/../node.py"))
        self.assertIsNone(gateway.ruta_estatica("/%2e%2e/node.py"))

    def test_sirve_index(self):
        self.assertEqual(gateway.ruta_estatica("/").name, "index.html")

    def test_sirve_catalogo(self):
        self.assertEqual(gateway.ruta_estatica("/catalogo.json?x=1").name, "catalogo.json")

    def test_args_no_pisan_parametros_del_cliente(self):
        self.assertEqual(gateway.limpiar_args({"op": "x", "node": "n1", "cancion": "c1"}), {"cancion": "c1"})

    def test_no_existe(self):
        self.assertIsNone(gateway.ruta_estatica("/nada.txt"))


if __name__ == "__main__":
    unittest.main()
