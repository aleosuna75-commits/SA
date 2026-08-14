# -*- coding: utf-8 -*-
"""
Arma una vista previa de UN SOLO ARCHIVO a partir del sitio real.

El sitio de docs/ es lo que se publica: index.html + estilos.css + app.js que
piden datos/jXX.json. Para compartir la página como Artifact hace falta un solo
HTML autocontenido, así que aquí se inlinea todo desde las MISMAS fuentes: no
hay una segunda copia del diseño que se pueda desincronizar.
"""
import json
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent


def main():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    css = (DOCS / "estilos.css").read_text(encoding="utf-8")
    js = ((DOCS / "equipos.js").read_text(encoding="utf-8") + "\n"
          + (DOCS / "app.js").read_text(encoding="utf-8"))
    idx = json.loads((DOCS / "datos" / "indice.json").read_text(encoding="utf-8"))
    jornadas = {str(j["jornada"]):
                json.loads((DOCS / "datos" / j["archivo"]).read_text(encoding="utf-8"))
                for j in idx["jornadas"] if j.get("archivo")}
    proy_f = DOCS / "datos" / "proyeccion.json"
    datos = {"indice": idx, "jornadas": jornadas,
             "proyeccion": json.loads(proy_f.read_text(encoding="utf-8"))
                           if proy_f.is_file() else None}

    cuerpo = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    cuerpo = re.sub(r'\s*<script src="(app|equipos)\.js"></script>', "", cuerpo)
    titulo = re.search(r"<title>(.*?)</title>", html, re.S).group(1)

    salida = (
        f"<title>{titulo}</title>\n"
        f"<style>\n{css}\n</style>\n"
        f"{cuerpo}\n"
        f"<script>\nconst DATOS = {json.dumps(datos, ensure_ascii=False)};\n{js}\n</script>\n"
    )
    destino = DOCS / "vista_previa.html"
    destino.write_text(salida, encoding="utf-8")
    print(f"{destino}  ({destino.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
