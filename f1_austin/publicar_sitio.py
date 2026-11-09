"""Arma la carpeta del sitio estático para Netlify (../sitio_f1) a partir de los reportes generados.

Estructura publicada:
    sitio_f1/index.html            -> página única de todos los GP (web/plantilla.html vía construir_web.py): muestra el GP
                                      actual de gps/meta.json, cambia de GP con el menú o con el hash (#brasil2026) y lleva
                                      incrustados meta.json y los JSON de todos los gps/<slug>/
    sitio_f1/img/<tema>/           -> fotos de cada tema (web/img/)
    sitio_f1/<slug>/qualy.html     -> páginas de archivo (reportes anteriores: Austin, México)
    sitio_f1/<slug>/carrera.html   -> pronóstico de carrera de archivo (si existe)

Cada página recibe una barra de navegación común. Despliegue: arrastrar la carpeta sitio_f1 a Netlify
(app.netlify.com/drop) o conectar el repo (netlify.toml en la raíz ya apunta a sitio_f1). Ver PUBLICAR_NETLIFY.md.

Uso:  python3 publicar_sitio.py                       # -> ../sitio_f1 con los datos de gps/
      python3 publicar_sitio.py --sitio /tmp/prueba --gps /ruta/a/gps   # otra salida u otros datos (pruebas)
"""
import argparse
import shutil
from pathlib import Path

BASE = Path(__file__).parent
SITIO = BASE.parent / "sitio_f1"

# Portada: página única multi-GP (web/, la misma que se publica como Artifact). Se construye con doctype
# (construir_web.py --documento) y se copian sus imágenes; no recibe barra: trae su propio menú con todos los GP.
# La página vieja de México (web_mexico/ + construir_web_mexico.py) sigue intacta y reproducible, pero ya no es la portada.
WEB = BASE / "web"
GPS_DIR = BASE / "gps"

# (slug, etiqueta, archivo qualy, archivo carrera) — páginas de archivo con barra común
PAGINAS = [
    ("mexico", "México 2026", "reporte_qualy_mexico_2026.html", None),
    ("austin", "Austin 2026", "reporte_qualy_austin_2026.html", "reporte_carrera_austin_2026.html"),
]

NAV_CSS = """
<style>
.f1nav{position:relative;z-index:50;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;justify-content:center;
padding:8px 16px;background:#0b0b0f;border-bottom:1px solid rgba(255,255,255,.12);font:600 13px/1.3 "Titillium Web",system-ui,sans-serif}
.f1nav b{color:#fff;letter-spacing:2px;text-transform:uppercase;font-size:12px;margin-right:6px}
.f1nav a{color:#d9d4cc;text-decoration:none;padding:3px 8px;border-radius:3px}
.f1nav a:hover{background:rgba(255,255,255,.1);color:#fff}
.f1nav a.on{background:#e10600;color:#fff}
</style>"""


def nav(actual, prefijo):
    links = [f'<a href="{prefijo}index.html">Inicio · Todos los GP</a>']
    for i, (slug, etiqueta, q, c) in enumerate(PAGINAS):
        href_q = f"{prefijo}{slug}/qualy.html"
        links.append(f'<a class="{"on" if actual == (slug, "qualy") else ""}" href="{href_q}">{etiqueta} · Qualy</a>')
        if c:
            links.append(f'<a class="{"on" if actual == (slug, "carrera") else ""}" href="{prefijo}{slug}/carrera.html">'
                         f'{etiqueta} · Carrera</a>')
    return f'{NAV_CSS}<nav class="f1nav"><b>Pronósticos F1</b>{"".join(links)}</nav>'


def inyectar(html, barra):
    i = html.find("<body")
    j = html.find(">", i) + 1
    return html[:j] + barra + html[j:]


def main():
    global SITIO, GPS_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitio", default=str(SITIO), help="carpeta de salida (se borra y se rehace)")
    ap.add_argument("--gps", default=str(GPS_DIR), help="carpeta con meta.json y <slug>/*.json")
    a = ap.parse_args()
    SITIO, GPS_DIR = Path(a.sitio), Path(a.gps)
    if SITIO.exists():
        shutil.rmtree(SITIO)
    SITIO.mkdir()
    import subprocess, sys
    cmd = [sys.executable, str(BASE / "construir_web.py"), "--salida", str(SITIO / "index.html"), "--documento",
           "--gps", str(GPS_DIR)]
    subprocess.run(cmd, check=True)
    shutil.copytree(WEB / "img", SITIO / "img")
    print("->", (SITIO / "index.html").relative_to(SITIO.parent), "(página de todos los GP) + img/<tema>/")
    for i, (slug, etiqueta, q, c) in enumerate(PAGINAS):
        for tipo, archivo in (("qualy", q), ("carrera", c)):
            if not archivo or not (BASE / archivo).exists():
                continue
            html = (BASE / archivo).read_text(encoding="utf-8")
            destino, prefijo = SITIO / slug / f"{tipo}.html", "../"
            destino.parent.mkdir(exist_ok=True)
            destino.write_text(inyectar(html, nav((slug, tipo), prefijo)), encoding="utf-8")
            print("->", destino.relative_to(SITIO.parent))
    (SITIO / "404.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>No encontrado</title><body style="margin:0;background:#0b0b0f;color:#fff;font-family:system-ui;'
        'display:grid;place-items:center;min-height:100vh;text-align:center"><div><h1>Bandera roja 🚩</h1>'
        '<p>Esta página no existe.</p><a style="color:#ff8c00" href="/">Volver a los pronósticos</a></div>', encoding="utf-8")


if __name__ == "__main__":
    main()
