#!/usr/bin/env python3
"""Genera la version de un solo archivo para publicar como pagina.

Toma index.html, css/app.css, js/data.js y js/app.js y los une. Quita lo que
no aplica fuera del hosting propio: el service worker y la descarga de
respaldo, que el visor de artifacts no permite.
"""
import re, pathlib, sys

d = pathlib.Path(__file__).parent
html = (d / 'index.html').read_text()
css  = (d / 'css/app.css').read_text()
data = (d / 'js/data.js').read_text()
app  = (d / 'js/app.js').read_text()

# El artifact envuelve en doctype/head/body: solo va el contenido.
body = html.split('<body>', 1)[1].split('</body>', 1)[0].strip()

# Sin sw.js que registrar fuera del hosting propio.
app, n = re.subn(r"\nif \('serviceWorker' in navigator\) \{.*?\n\}\n", "\n", app, flags=re.S)
assert n == 1 and 'serviceWorker' not in app, 'no se quito el registro del service worker'

# El visor no permite descargas: fuera el boton de respaldo y su manejador.
body, n = re.subn(r'\s*<button class="btn ghost" id="btnExport">[^<]*</button>', '', body)
assert n == 1, 'no se quito el boton de exportar'
app, n = re.subn(r"\n  if \(t\.id === 'btnExport'\) \{.*?\n  \}\n", "\n", app, flags=re.S)
assert n == 1 and 'btnExport' not in app, 'no se quito el manejador de exportar'
body = body.replace(
    'Tus listas y gastos se guardan sólo en este dispositivo. Si borras los datos del navegador se pierden.',
    'Tus listas y gastos se guardan sólo en este dispositivo y en este navegador. '
    'Si borras los datos del navegador se pierden.')

out = f"<title>Viaje SoCal 2026</title>\n<style>\n{css}</style>\n\n{body}\n\n<script>\n{data}</script>\n<script>\n{app}</script>\n"
dest = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else d / 'viaje-socal.html')
dest.write_text(out)
print(f'{dest}: {len(out):,} bytes')
