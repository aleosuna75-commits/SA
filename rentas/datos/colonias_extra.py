#!/usr/bin/env python3
"""Agrega a lugares.json las colonias que usan los anuncios y que OpenStreetMap no trae con ese nombre
(p. ej. "Del Valle Centro", "San Rafael" de Cuauhtémoc, "Tacuba"). Sin ellas, la búsqueda no las sugiere
y "Agregar" no puede ubicar un anuncio de esas colonias.

El centro sale de Nominatim (una consulta cada 1.6 s, con la misma caché que ubicar.py) y solo se acepta
si cae dentro de la alcaldía del anuncio; si no, se usa el promedio de los anuncios de esa colonia.

Uso: python3 colonias_extra.py lugares.json anuncios.json
"""
import json, sys, os, re, time, unicodedata, urllib.parse, urllib.request
from collections import defaultdict

LUG, ANU = sys.argv[1:3]
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.nominatim_cache.json')
UA = {'User-Agent': 'BuscaNido/1.0 (mapa personal de rentas en la CDMX)'}

def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', str(s or '').lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()

def inside(pt, ring):
    c = False; j = len(ring) - 1
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[j]
        if (y1 > pt[1]) != (y2 > pt[1]) and pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1: c = not c
        j = i
    return c

lug = json.load(open(LUG, encoding='utf8'))
anu = json.load(open(ANU, encoding='utf8'))['anuncios']
def alcaldia_de(lon, lat):
    for a in lug['alcaldias']:
        for poly in a['p']:
            if inside((lon, lat), poly[0]) and not any(inside((lon, lat), h) for h in poly[1:]): return a['n']
    return None

cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
last = [0.0]
def nominatim(q):
    if q in cache: return cache[q]
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({'q': q, 'format': 'jsonv2', 'limit': 3, 'countrycodes': 'mx', 'viewbox': '-99.37,19.60,-98.94,19.04', 'bounded': 1})
    wait = 1.6 - (time.time() - last[0])
    if wait > 0: time.sleep(wait)
    try: r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40))
    except Exception as e: print('  nominatim falló', q, e); last[0] = time.time(); return []
    last[0] = time.time(); cache[q] = r; json.dump(cache, open(CACHE, 'w'))
    return r

lug['colonias'] = [c for c in lug['colonias'] if c.get('c') != 'anuncios']  # se recalculan cada vez
hay = {(norm(c['n']), c['a']) for c in lug['colonias']}
grupos = defaultdict(list)
for a in anu:
    if (norm(a['colonia']), a['alcaldia']) not in hay: grupos[(a['colonia'], a['alcaldia'])].append(a)

nuevas = []
for (col, alc), xs in sorted(grupos.items()):
    pt = None
    for x in nominatim(f'{col}, {alc}, Ciudad de México'):
        p = (float(x['lon']), float(x['lat']))
        if alcaldia_de(*p) == alc: pt = p; break
    origen = 'nominatim'
    if not pt:
        pt = (sum(a['lon'] for a in xs) / len(xs), sum(a['lat'] for a in xs) / len(xs)); origen = 'promedio de anuncios'
    nuevas.append({'n': col, 'a': alc, 'lon': round(pt[0], 5), 'lat': round(pt[1], 5), 'c': 'anuncios'})
    print(f'  {col} ({alc}): {origen}')
lug['colonias'] += nuevas
json.dump(lug, open(LUG, 'w', encoding='utf8'), ensure_ascii=False, separators=(',', ':'))
print('colonias agregadas', len(nuevas), '· total', len(lug['colonias']))
