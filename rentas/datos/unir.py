#!/usr/bin/env python3
"""Une los anuncios ya publicados con los nuevos (salidas de ubicar.py) en datos/publicar/anuncios.json.
Quita repetidos: misma URL, o el mismo inmueble en dos portales (mismo precio, colonia, recámaras y m²).
Los anuncios que ya estaban conservan su fecha "visto".

Uso: python3 -I unir.py salida.json "fecha legible" base.json nuevo1.json [nuevo2.json ...]
"""
import json, sys, re, unicodedata, urllib.parse, collections

OUT, FECHA, *SRC = sys.argv[1:]
def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', str(s or '').lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', s)).strip()
def url_key(u):
    p = urllib.parse.urlparse(u.strip()); return (p.hostname or '').replace('www.', '') + p.path.rstrip('/').lower()

out, urls, firmas = [], set(), set()
quitados = collections.Counter()
for f in SRC:
    for a in json.load(open(f, encoding='utf8'))['anuncios']:
        k = url_key(a['url'])
        if k in urls: quitados['misma url'] += 1; continue
        firma = (round(a['precio'], -1), norm(a.get('colonia')), a.get('recamaras'), a.get('m2'))
        if a.get('m2') and firma in firmas: quitados['mismo inmueble en otro portal'] += 1; continue
        urls.add(k); firmas.add(firma); out.append(a)
json.dump({'meta': {'fecha': FECHA, 'total': len(out)}, 'anuncios': out}, open(OUT, 'w', encoding='utf8'), ensure_ascii=False, separators=(',', ':'))
print('total', len(out), dict(quitados))
print(collections.Counter(a['fuente'] for a in out).most_common())
print(collections.Counter(a['alcaldia'] for a in out).most_common())
print(collections.Counter(a['prec'] for a in out))
