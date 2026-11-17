#!/usr/bin/env python3
"""Edificios en 3D para toda la CDMX.

OpenStreetMap trae muy pocos edificios de la ciudad (unos 3 mil en las teselas z14), así que el 3D se veía vacío.
Este script junta:
  - las huellas de edificios de Microsoft (GlobalMLBuildingFootprints, detectadas con aprendizaje automático, ODbL),
  - los edificios de OpenStreetMap que ya vienen en las teselas (esos sí traen altura cuando alguien la capturó).
Si una huella de Microsoft cae dentro de un edificio de OSM, se queda la de OSM.

Altura: la de OSM cuando existe. Si no, una aproximada por el tamaño de la planta (casas chicas ~1-2 pisos,
naves y edificios grandes ~4-5 pisos), con una variación fija por edificio para que no se vea como maqueta plana.
La app lo dice en "Sobre los datos".

Salida: teselas vectoriales z14 (capa "b", propiedad "h" = altura en metros), empacadas de 4 en 4 por tesela z13
en <salida>/e/<x13>-<y13>.json, en base64, igual que el mapa base.

Uso: python3 -I edificios.py <carpeta con ms_*.csv.gz> <carpeta cache de teselas crudas> lugares.json <salida>
"""
import base64, collections, glob, gzip, json, math, os, sys, zlib
import mapbox_vector_tile as mvt

MS, CACHE, LUG, OUT = sys.argv[1:5]
Z = 14; EXT = 4096
lug = json.load(open(LUG, encoding='utf8'))

def lonlat_to_tile(lon, lat, z=Z):
    n = 2 ** z; x = (lon + 180) / 360 * n; y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n; return x, y

# --- dentro de la CDMX (polígonos de las alcaldías, con un margen chico) ---
polys = [p for a in lug['alcaldias'] for p in a['p']]
bb = [min(x for p in polys for x, _ in p[0]), min(y for p in polys for _, y in p[0]), max(x for p in polys for x, _ in p[0]), max(y for p in polys for _, y in p[0])]
def inside(pt, ring):
    c = False; j = len(ring) - 1
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[j]
        if (y1 > pt[1]) != (y2 > pt[1]) and pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1: c = not c
        j = i
    return c
# rejilla de 0.005° (~500 m) precalculada: 1 = dentro, 0 = fuera; las celdas del borde se cuentan dentro (margen)
G = 0.005; gx0, gy0 = bb[0] - G, bb[1] - G; gw, gh = int((bb[2] - bb[0]) / G) + 3, int((bb[3] - bb[1]) / G) + 3
grid = bytearray(gw * gh)
for i in range(gw):
    for j in range(gh):
        cx, cy = gx0 + (i + .5) * G, gy0 + (j + .5) * G
        pts = [(cx, cy)] + [(cx + dx * G * .5, cy + dy * G * .5) for dx in (-1, 1) for dy in (-1, 1)]
        if any(inside(p, poly[0]) and not any(inside(p, h) for h in poly[1:]) for p in pts for poly in polys): grid[i * gh + j] = 1
def en_cdmx(lon, lat):
    i, j = int((lon - gx0) / G), int((lat - gy0) / G)
    return 0 <= i < gw and 0 <= j < gh and grid[i * gh + j] == 1

# --- edificios de OSM de las teselas crudas (ya en coordenadas de tesela) ---
osm = collections.defaultdict(list)  # (x, y) -> [(ring, h)]
for f in glob.glob(os.path.join(CACHE, f'{Z}-*.pbf')):
    _, x, y = os.path.basename(f)[:-4].split('-'); x, y = int(x), int(y)
    d = mvt.decode(open(f, 'rb').read(), default_options={'y_coord_down': True})
    for ft in d.get('building', {}).get('features', []):
        g = ft['geometry']; h = ft['properties'].get('render_height') or 0
        rings = [g['coordinates'][0]] if g['type'] == 'Polygon' else [p[0] for p in g['coordinates']] if g['type'] == 'MultiPolygon' else []
        for r in rings:
            if len(r) >= 4: osm[(x, y)].append(([(int(a), int(b)) for a, b in r], float(h)))

def area_px(r):
    return sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1)) / 2
M_PX = 40075016.686 * math.cos(math.radians(19.4)) / (2 ** Z * EXT)  # metros por unidad de tesela a la latitud de la CDMX
def altura(area_m2, semilla):
    base = 4.5 if area_m2 < 60 else 6.5 if area_m2 < 150 else 9 if area_m2 < 400 else 12 if area_m2 < 1500 else 15
    return round(base * (0.85 + (semilla % 31) / 100), 1)  # ±15 % fijo por edificio

# --- huellas de Microsoft ---
tiles = collections.defaultdict(list)
n_ms = n_fuera = n_dup = n_chico = 0
osm_bbox = {k: [(min(a for a, _ in r), min(b for _, b in r), max(a for a, _ in r), max(b for _, b in r), r, i) for i, (r, _) in enumerate(v)] for k, v in osm.items()}
dentro = collections.defaultdict(list)  # (tesela, i de OSM) -> huellas de Microsoft que caen dentro
for f in sorted(glob.glob(os.path.join(MS, 'ms_*.csv.gz'))):
    for line in gzip.open(f, 'rt'):
        try: g = json.loads(line)['geometry']
        except Exception: continue
        if g['type'] != 'Polygon': continue
        ring = g['coordinates'][0]
        cx = sum(p[0] for p in ring[:-1]) / (len(ring) - 1); cy = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
        n_ms += 1
        if not (bb[0] - .01 < cx < bb[2] + .01 and bb[1] - .01 < cy < bb[3] + .01) or not en_cdmx(cx, cy): n_fuera += 1; continue
        tx, ty = lonlat_to_tile(cx, cy); key = (int(tx), int(ty))
        pts = []
        for lon, lat in ring:
            px, py = lonlat_to_tile(lon, lat)
            q = (round((px - key[0]) * EXT), round((py - key[1]) * EXT))
            if not pts or q != pts[-1]: pts.append(q)
        if len(pts) < 4: n_chico += 1; continue
        if pts[0] != pts[-1]: pts.append(pts[0])
        a = area_px(pts)
        if abs(a) * M_PX * M_PX < 12: n_chico += 1; continue  # menos de 12 m²: ruido
        c = ((tx - key[0]) * EXT, (ty - key[1]) * EXT)
        item = (pts, altura(abs(a) * M_PX * M_PX, hash((pts[0], len(pts))) & 0xffff)); dup = None
        for x0, y0, x1, y1, r, i in osm_bbox.get(key, ()):
            if x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and inside(c, r): dup = i; break
        if dup is not None: dentro[(key, dup)].append(item); continue
        tiles[key].append(item)
# un edificio de OSM que cubre varias huellas (una manzana o una unidad entera dibujada como un solo edificio) se cambia por ellas;
# si no, se queda el de OSM (trae forma y a veces altura capturadas a mano)
n_osm_cambiado = 0
for k, v in osm.items():
    for i, (r, h) in enumerate(v):
        a = abs(area_px(r)) * M_PX * M_PX; hijos = dentro.get((k, i), [])
        if len(hijos) >= 3 and a > 3000: tiles[k].extend(hijos); n_osm_cambiado += 1; continue
        n_dup += len(hijos)
        tiles[k].append((r, h if h > 0 else altura(a, hash((r[0], len(r))) & 0xffff)))
print('edificios de OSM cambiados por sus huellas', n_osm_cambiado)
print(f'Microsoft: {n_ms} huellas; fuera de la CDMX {n_fuera}; repetidas con OSM {n_dup}; muy chicas {n_chico}', flush=True)
print('edificios en teselas', sum(len(v) for v in tiles.values()), 'teselas', len(tiles), flush=True)

# --- codificación MVT mínima (una capa, polígonos, una propiedad) ---
def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: out.append(b | 0x80)
        else: out.append(b); return bytes(out)
def key_(field, wt): return varint((field << 3) | wt)
def ld(field, payload): return key_(field, 2) + varint(len(payload)) + payload
zz = lambda n: (n << 1) ^ (n >> 31)
def geom(r):
    if area_px(r) < 0: r = r[::-1]  # anillo exterior en sentido horario (área positiva en coordenadas de tesela)
    r = r[:-1]; cmds = [(1 & 7) | (1 << 3)]; x = y = 0
    dx, dy = r[0][0] - x, r[0][1] - y; cmds += [zz(dx), zz(dy)]; x, y = r[0]
    cmds.append((2 & 7) | ((len(r) - 1) << 3))
    for px, py in r[1:]: cmds += [zz(px - x), zz(py - y)]; x, y = px, py
    cmds.append((7 & 7) | (1 << 3))
    return b''.join(varint(c) for c in cmds)
def encode(feats):
    vals = {}; fb = bytearray()
    for r, h in feats:
        hv = int(round(h))
        if hv not in vals: vals[hv] = len(vals)
        f = key_(2, 2) + varint(len(varint(0) + varint(vals[hv]))) + varint(0) + varint(vals[hv])  # tags packed
        f += key_(3, 0) + varint(3)  # POLYGON
        g = geom(r); f += ld(4, g)
        fb += ld(2, f)
    layer = key_(15, 0) + varint(2) + ld(1, b'b') + bytes(fb) + ld(3, b'h')
    for hv in vals: layer += ld(4, key_(5, 0) + varint(hv))  # uint_value
    layer += key_(5, 0) + varint(EXT)
    return ld(3, layer)

packs = collections.defaultdict(dict); raw = 0
for (x, y), feats in tiles.items():
    b = encode(feats); raw += len(b)
    packs[(x >> 1, y >> 1)][f'{Z}/{x}/{y}'] = base64.b64encode(b).decode()
os.makedirs(os.path.join(OUT, 'e'), exist_ok=True)
tot = 0
for (x, y), d in packs.items():
    s = json.dumps(d, separators=(',', ':')); tot += len(s)
    open(os.path.join(OUT, 'e', f'{x}-{y}.json'), 'w').write(s)
print('paquetes', len(packs), 'MB pbf', round(raw / 1e6, 1), 'MB json', round(tot / 1e6, 1), 'gz aprox', round(sum(len(zlib.compress(open(os.path.join(OUT, 'e', f'{x}-{y}.json'), 'rb').read(), 6)) for x, y in list(packs)[:20]) / max(1, min(20, len(packs))) * len(packs) / 1e6, 1))
