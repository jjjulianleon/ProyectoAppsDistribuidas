"""Baja la portada de cada canción del catálogo (API pública de búsqueda de Deezer).

    python3 web/bajar_portadas.py

Guarda web/portadas/<id>.jpg (500x500). Las portadas son de terceros: no van
en el repo ni en el zip (ver .gitignore). Sin portada, la página usa el color
del catálogo.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

WEB = Path(__file__).resolve().parent
DESTINO = WEB / "portadas"


def elegir(resultados, artista):
    """El primer resultado cuyo artista comparte una palabra con el del catálogo
    y que no es remix ni instrumental. Evita covers de otros artistas
    ("Piano Dreamers") y versiones que no son la original."""
    palabras = [w for w in artista.lower().replace(",", " ").split() if len(w) >= 4]
    for r in resultados:
        nombre = (r["title"] + " " + r["album"]["title"]).lower()
        if any(w in nombre for w in ("remix", "instrumental")):
            continue
        if any(w in r["artist"]["name"].lower() for w in palabras):
            return r
    return None


def main():
    DESTINO.mkdir(exist_ok=True)
    for c in json.loads((WEB / "catalogo.json").read_text()):
        q = urllib.parse.urlencode({"q": f"{c['artista'].split(' ft.')[0]} {c['titulo']}", "limit": 10})
        with urllib.request.urlopen(f"https://api.deezer.com/search?{q}", timeout=10) as r:
            hit = elegir(json.load(r).get("data", []), c["artista"])
        if not hit:
            print(f"{c['id']}: sin resultado para {c['titulo']}")
            continue
        with urllib.request.urlopen(hit["album"]["cover_big"], timeout=10) as r:
            (DESTINO / f"{c['id']}.jpg").write_bytes(r.read())
        print(f"{c['id']}: {hit['artist']['name']} — {hit['title']} ({hit['album']['title']})")


if __name__ == "__main__":
    main()
