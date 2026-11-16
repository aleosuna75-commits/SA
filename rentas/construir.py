#!/usr/bin/env python3
"""Arma el artefacto de Busca Nido: une src/app.html con el CSS de MapLibre, los íconos y las plataformas,
y deja todo lo que se publica en una carpeta (por defecto ./publicar)."""
import json, shutil, sys
from pathlib import Path
A = Path(__file__).resolve().parent; SRC = A / 'src'
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else A / 'publicar'
page = (SRC / 'app.html').read_text(encoding='utf8')
page = page.replace('/*MAPLIBRE_CSS*/', (SRC / 'maplibre-4.7.1.css').read_text(encoding='utf8'))
page = page.replace('/*ICONOS*/{}', (SRC / 'iconos.json').read_text(encoding='utf8'))
page = page.replace('/*PLATAFORMAS*/', (SRC / 'plataformas.js').read_text(encoding='utf8'))
assert '/*' not in page.split('<script>', 2)[-1][:0]
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'index.html').write_text(page, encoding='utf8')
for d in ['data']:
    (OUT / d).mkdir(exist_ok=True)
    for f in (A / 'datos' / 'publicar').glob('*.json'):
        if not f.name.startswith('.'): shutil.copy(f, OUT / d / f.name)
print('index.html', len(page) // 1024, 'KB ->', OUT)
