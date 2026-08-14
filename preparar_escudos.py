# -*- coding: utf-8 -*-
"""
================================================================================
  PREPARAR ESCUDOS — Cerebro Liga MX 2026
================================================================================
Deja listos los escudos reales para que la web los use en lugar de las
insignias de uniforme.

POR QUÉ ESTE SCRIPT Y NO LOS ARCHIVOS YA PUESTOS
------------------------------------------------
Los escudos de los clubes de Liga MX no están disponibles con licencia libre
(no existen en Wikimedia Commons; en Wikipedia son archivos de uso legítimo, no
redistribuibles). Así que el repositorio no los trae. Si tú los consigues por
una vía en la que tengas derecho a usarlos, este script los normaliza, los
renombra y enciende el interruptor en la web. La decisión y los archivos quedan
de tu lado.

USO
---
1. Junta las imágenes en una carpeta (PNG, JPG, WEBP o SVG). Da igual cómo se
   llamen: el script las empareja por nombre con los equipos.

2. Corre:
       python preparar_escudos.py --origen "C:\\Users\\asunad\\Downloads\\escudos"

   Lo que hace:
     * empareja cada archivo con su equipo (acepta "america.png", "Club
       América.png", "AME.png", "aguilas.png"...)
     * lo convierte a PNG cuadrado de 128 px con fondo transparente
     * lo guarda en docs/escudos/<slug>.png
     * actualiza la lista ESCUDOS de docs/equipos.js

3. Publica: git add . && git commit -m "escudos" && git push

Los equipos sin archivo siguen mostrando su insignia de uniforme, así que
puedes ir agregándolos de a poco.

    python preparar_escudos.py --listar     # ver qué falta
    python preparar_escudos.py --quitar     # volver a las insignias
================================================================================
"""
import argparse
import re
import shutil
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ / "docs" / "escudos"
EQUIPOS_JS = RAIZ / "docs" / "equipos.js"
TAM = 128

# slug -> nombres con los que puede venir el archivo
ALIAS = {
    "ame": ["america", "club america", "aguilas", "ame", "cf america"],
    "ats": ["atlas", "ats", "rojinegros", "atlas fc"],
    "ate": ["atlante", "ate", "potros", "atlante fc"],
    "asl": ["atletico san luis", "san luis", "asl", "atl san luis"],
    "caz": ["cruz azul", "caz", "cementeros", "maquina"],
    "chi": ["chivas", "guadalajara", "chi", "cd guadalajara", "rebano"],
    "jua": ["juarez", "fc juarez", "jua", "bravos"],
    "leo": ["leon", "club leon", "leo", "la fiera"],
    "mty": ["monterrey", "rayados", "mty", "cf monterrey"],
    "nec": ["necaxa", "nec", "rayos", "club necaxa"],
    "pac": ["pachuca", "pac", "tuzos", "cf pachuca"],
    "pue": ["puebla", "pue", "camoteros", "club puebla"],
    "pum": ["pumas", "unam", "pum", "universidad nacional"],
    "qro": ["queretaro", "qro", "gallos", "gallos blancos"],
    "san": ["santos", "santos laguna", "san", "guerreros"],
    "tig": ["tigres", "uanl", "tig", "tigres uanl"],
    "tij": ["tijuana", "xolos", "tij", "xol", "club tijuana"],
    "tol": ["toluca", "tol", "diablos", "diablos rojos"],
}
NOMBRE = {"ame": "América", "ats": "Atlas", "ate": "Atlante", "asl": "Atlético San Luis",
          "caz": "Cruz Azul", "chi": "Chivas", "jua": "Juárez", "leo": "León",
          "mty": "Monterrey", "nec": "Necaxa", "pac": "Pachuca", "pue": "Puebla",
          "pum": "Pumas", "qro": "Querétaro", "san": "Santos", "tig": "Tigres",
          "tij": "Tijuana", "tol": "Toluca"}


def normaliza(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def empareja(nombre_archivo):
    base = normaliza(Path(nombre_archivo).stem)
    mejor, largo = None, 0
    for slug, alias in ALIAS.items():
        for a in alias:
            if a in base and len(a) > largo:
                mejor, largo = slug, len(a)
    return mejor


def convierte(origen, destino):
    """A PNG cuadrado con transparencia. Usa Pillow si está; si no, copia tal cual."""
    try:
        from PIL import Image
    except ImportError:
        shutil.copy(origen, destino)
        return "copiado sin redimensionar (instala Pillow para normalizar)"
    if origen.suffix.lower() == ".svg":
        shutil.copy(origen, destino.with_suffix(".svg"))
        return "SVG copiado tal cual"
    im = Image.open(origen).convert("RGBA")
    im.thumbnail((TAM, TAM), Image.LANCZOS)
    lienzo = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    lienzo.paste(im, ((TAM - im.width) // 2, (TAM - im.height) // 2), im)
    lienzo.save(destino, "PNG", optimize=True)
    return f"{TAM}×{TAM} px"


def escribe_lista(slugs):
    """Actualiza `const ESCUDOS = [...]` dentro de docs/equipos.js."""
    txt = EQUIPOS_JS.read_text(encoding="utf-8")
    lista = ", ".join(f'"{s}"' for s in sorted(slugs))
    nuevo, n = re.subn(r"const ESCUDOS = \[[^\]]*\];",
                       f"const ESCUDOS = [{lista}];", txt, count=1)
    if not n:
        raise SystemExit("No encontré 'const ESCUDOS = [...]' en docs/equipos.js")
    EQUIPOS_JS.write_text(nuevo, encoding="utf-8")


def disponibles():
    return sorted(p.stem for p in DESTINO.glob("*.png")) if DESTINO.is_dir() else []


def main():
    ap = argparse.ArgumentParser(description="Prepara los escudos para la web")
    ap.add_argument("--origen", help="Carpeta con las imágenes de los escudos")
    ap.add_argument("--listar", action="store_true", help="Muestra qué hay y qué falta")
    ap.add_argument("--quitar", action="store_true", help="Vuelve a las insignias de uniforme")
    args = ap.parse_args()

    DESTINO.mkdir(parents=True, exist_ok=True)

    if args.quitar:
        escribe_lista([])
        print("Listo: la web vuelve a las insignias de uniforme.")
        print("(Los archivos siguen en docs/escudos/; bórralos si quieres.)")
        return

    if args.origen:
        origen = Path(args.origen).expanduser()
        if not origen.is_dir():
            raise SystemExit(f"No existe la carpeta: {origen}")
        vistos, sin_match = {}, []
        for f in sorted(origen.iterdir()):
            if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                continue
            slug = empareja(f.name)
            if not slug:
                sin_match.append(f.name)
                continue
            detalle = convierte(f, DESTINO / f"{slug}.png")
            vistos[slug] = f.name
            print(f"  {NOMBRE[slug]:20s} <- {f.name}   ({detalle})")
        if sin_match:
            print("\n  Sin emparejar (renómbralos con el nombre del equipo):")
            for s in sin_match:
                print(f"    {s}")

    listos = disponibles()
    escribe_lista(listos)

    print(f"\nEscudos activos: {len(listos)}/18")
    faltan = [NOMBRE[s] for s in NOMBRE if s not in listos]
    if faltan:
        print("Siguen con insignia de uniforme: " + ", ".join(sorted(faltan)))
    print("\nSiguiente paso:  python docs/construir_vista_previa.py  y publica.")


if __name__ == "__main__":
    main()
