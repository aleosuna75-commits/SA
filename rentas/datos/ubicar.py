#!/usr/bin/env python3
"""Convierte los anuncios verificados (salida de la búsqueda) en datos/publicar/anuncios.json:
normaliza la plataforma, quita duplicados y ubica cada anuncio en el mapa.

Ubicación: si el anuncio trae calle, se busca la calle dentro de su colonia con Nominatim (OpenStreetMap,
una consulta por segundo como pide su política de uso) y solo se acepta si cae cerca de la colonia.
Si no, el pin va al centro de la colonia con un pequeño desplazamiento fijo para que no se encimen.

Uso: python3 ubicar.py resultado_busqueda.json lugares.json salida.json "16 de noviembre de 2026"
"""
import json, sys, time, math, re, unicodedata, urllib.parse, urllib.request, hashlib, os

SRC, LUG, OUT, FECHA = sys.argv[1:5]
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.nominatim_cache.json')
UA = {'User-Agent': 'BuscaNido/1.0 (mapa personal de rentas en la CDMX)'}

def norm(s):
    s = str(s or '').lower().replace('ñ', '\x01')
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').replace('\x01', 'ñ')
    s = re.sub(r'[^a-z0-9ñ ]', ' ', s)
    s = re.sub(r'\b(col|colonia|cdmx|ciudad de mexico|alcaldia|del|de la|de los)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def hav(a, b):
    r = math.pi / 180; dl = (b[1] - a[1]) * r; dn = (b[0] - a[0]) * r
    h = math.sin(dl / 2) ** 2 + math.cos(a[1] * r) * math.cos(b[1] * r) * math.sin(dn / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))

FUENTES = {'inmuebles24': 'inmuebles24.com', 'vivanuncios': 'vivanuncios.com.mx', 'lamudi': 'lamudi.com.mx', 'propiedades': 'propiedades.com',
           'mercadolibre': 'mercadolibre.com.mx', 'pincali': 'pincali.com', 'trovit': 'trovit.com.mx', 'mitula': 'mitula.mx', 'easybroker': 'easybroker.com',
           'icasas': 'icasas.mx', 'homie': 'homie.mx', 'casasyterrenos': 'casasyterrenos.com', 'metroscubicos': 'metroscubicos.com', 'century21': 'century21mexico.com',
           'remax': 'remax.com.mx', 'segundamano': 'segundamano.mx', 'dadaroom': 'dadaroom.com', 'compartodepa': 'compartodepa.com.mx', 'roomgo': 'roomgo.com.mx'}
def fuente(url, txt):
    try: h = urllib.parse.urlparse(url).hostname or ''
    except Exception: h = ''
    for k, d in FUENTES.items():
        if h.endswith(d): return k
    return h.replace('www.', '') or norm(txt)

def inside(pt, ring):
    c = False; j = len(ring) - 1
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[j]
        if (y1 > pt[1]) != (y2 > pt[1]) and pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1: c = not c
        j = i
    return c

lug = json.load(open(LUG, encoding='utf8'))
def alcaldia_de(lon, lat):
    for a in lug['alcaldias']:
        for poly in a['p']:
            if inside((lon, lat), poly[0]) and not any(inside((lon, lat), h) for h in poly[1:]): return a['n']
    return None
ALC = {norm(a['n']): a['n'] for a in lug['alcaldias']}
ALC.update({'cuajimalpa morelos': 'Cuajimalpa', 'la magdalena contreras': 'Magdalena Contreras', 'magdalena contreras': 'Magdalena Contreras', 'gam': 'Gustavo A. Madero', 'gustavo a madero': 'Gustavo A. Madero'})
def alc_norm(s):
    n = norm(s)
    for k, v in ALC.items():
        if k and (n == k or k in n): return v
    return None

COL = {}
for c in lug['colonias']: COL.setdefault(norm(c['n']), []).append(c)
def colonia(nombre, alc):
    n = re.sub(r'\b(i|ii|iii|iv|v|1a|2a|3a|1|2|3|primera|segunda|tercera)\b( seccion| secc)?$|\bseccion\b|\bsecc\b', '', norm(nombre)).strip() if norm(nombre) not in COL else norm(nombre)
    if not n: return None
    cands = COL.get(n, [])
    if not cands:  # variantes: "narvarte" → "narvarte poniente"; "del valle centro" → "del valle"
        cands = [c for k, v in COL.items() for c in v if k.startswith(n + ' ') or n.startswith(k + ' ') and len(k) > 5]
    if alc: cands = [c for c in cands if c['a'] == alc]  # nunca un homónimo de otra alcaldía
    return cands[0] if cands else None

cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
last = [0.0]
def nominatim(q):
    if q in cache: return cache[q]
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({'q': q, 'format': 'jsonv2', 'limit': 3, 'countrycodes': 'mx', 'viewbox': '-99.37,19.60,-98.94,19.04', 'bounded': 1})
    r = None
    for intento in range(3):
        wait = 1.6 - (time.time() - last[0])
        if wait > 0: time.sleep(wait)
        try: r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40)); break
        except Exception as e:
            last[0] = time.time(); print('  nominatim falló', q, e)
            if '429' in str(e): time.sleep(30)
    if r is None: last[0] = time.time(); return []  # no se guarda en caché: se reintenta en la próxima corrida
    last[0] = time.time(); cache[q] = r; json.dump(cache, open(CACHE, 'w'))
    return r

raw = json.load(open(SRC, encoding='utf8'))
zonas = raw['zonas'] if isinstance(raw, dict) and 'zonas' in raw else raw
items = [a for z in zonas for a in z.get('confirmados', [])]
print('verificados', len(items))

def url_key(u):
    try:
        p = urllib.parse.urlparse(u.strip()); return (p.hostname or '').replace('www.', '') + p.path.rstrip('/').lower()
    except Exception: return u

out, seen, sig = [], set(), set()
for a in items:
    url = (a.get('url') or '').strip()
    if not url.startswith('http') or not a.get('precio') or a['precio'] < 1500 or a['precio'] > 400000: continue
    k = url_key(url)
    if k in seen: continue
    seen.add(k)
    al = alc_norm(a.get('alcaldia')) or None
    c = colonia(a.get('colonia'), al)
    s = (round(a['precio'], -1), norm(a.get('colonia')), a.get('recamaras'), a.get('m2'))
    if s in sig and a.get('m2'): continue  # mismo inmueble en dos portales
    sig.add(s)
    lon = lat = None; prec = 'colonia'
    if a.get('calle') and c:
        r = nominatim(f"{a['calle']}, {c['n']}, {c['a']}, Ciudad de México")
        for x in r:
            p = (float(x['lon']), float(x['lat']))
            if hav(p, (c['lon'], c['lat'])) < 2500: lon, lat, prec = p[0], p[1], 'calle'; break
    if lon is None and c:
        h = int(hashlib.md5(url.encode()).hexdigest(), 16)
        ang = (h % 360) * math.pi / 180; dist = 60 + (h >> 9) % 190  # 60–250 m del centro de la colonia
        lat = c['lat'] + dist * math.cos(ang) / 111320; lon = c['lon'] + dist * math.sin(ang) / (111320 * math.cos(math.radians(c['lat'])))
    if lon is None:
        r = nominatim(f"{a.get('colonia')}, {al or a.get('alcaldia') or ''}, Ciudad de México")
        for x in r:  # solo si de verdad cae en la alcaldía que dice el anuncio
            p = (float(x['lon']), float(x['lat']))
            if not al or alcaldia_de(*p) == al:
                h = int(hashlib.md5(url.encode()).hexdigest(), 16)
                lon, lat = p[0] + (((h >> 10) % 300) - 150) / 105000, p[1] + ((h % 300) - 150) / 111320; break
    if lon is None: print('  sin ubicar:', a.get('colonia'), a.get('alcaldia'), url[:80]); continue
    alc = alcaldia_de(lon, lat) or al
    if al and alc != al: print('  quedó en otra alcaldía, se descarta:', a.get('colonia'), al, '→', alc, url[:70]); continue
    if not alc: print('  fuera de la CDMX:', a.get('colonia'), url[:80]); continue
    o = {k2: a.get(k2) for k2 in ['titulo', 'tipo', 'precio', 'mantenimiento', 'mantenimiento_incluido', 'calle', 'recamaras', 'banos', 'm2', 'estacionamientos', 'amueblado', 'mascotas', 'mascotas_detalle', 'anunciante', 'fecha_publicacion', 'requisitos', 'amenidades']}
    o.update({'id': 'w-' + hashlib.md5(k.encode()).hexdigest()[:10], 'url': url, 'fuente': fuente(url, a.get('fuente')), 'colonia': c['n'] if c else a.get('colonia'),
              'alcaldia': alc, 'lat': round(lat, 6), 'lon': round(lon, 6), 'prec': prec, 'visto': FECHA})
    out.append({k2: v for k2, v in o.items() if v not in (None, '')})

json.dump({'meta': {'fecha': FECHA, 'total': len(out)}, 'anuncios': out}, open(OUT, 'w', encoding='utf8'), ensure_ascii=False, separators=(',', ':'))
from collections import Counter
print('publicados', len(out), Counter(o['fuente'] for o in out).most_common(), Counter(o['alcaldia'] for o in out).most_common(), Counter(o['prec'] for o in out))
