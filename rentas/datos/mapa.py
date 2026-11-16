#!/usr/bin/env python3
"""Descarga el mapa base de la CDMX (OpenFreeMap, datos de OpenStreetMap), lo adelgaza y lo empaca en JSON
para servirlo desde el propio artefacto. También extrae colonias y estaciones de metro/metrobús/tren."""
import base64, json, math, os, sys, time, concurrent.futures as cf, urllib.request, gzip, collections
from mapbox_vector_tile.Mapbox import vector_tile_pb2 as vt
import mapbox_vector_tile as mvt
OUT = sys.argv[1]; os.makedirs(OUT + '/t', exist_ok=True); os.makedirs('cache', exist_ok=True)
BASE = 'https://tiles.openfreemap.org/planet/20261101_080013_pt'
W, N, E, S = -99.37, 19.60, -98.94, 19.04
UA = {'User-Agent': 'NuestroNido-Rentas/1.0 (mapa personal; descarga unica)', 'Accept-Encoding': 'gzip'}
def tile(lon, lat, z):
    n = 2 ** z; x = int((lon + 180) / 360 * n); y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n); return x, y
def lonlat(z, x, y, px, py, ext=4096):
    n = 2 ** z; lon = (x + px / ext) / n * 360 - 180; lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / ext) / n)))); return lon, lat
tiles = []
for z in range(0, 15):
    x0, y0 = tile(W, N, z); x1, y1 = tile(E, S, z)
    tiles += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
def get(t):
    z, x, y = t; f = f'cache/{z}-{x}-{y}.pbf'
    if os.path.exists(f): return t, open(f, 'rb').read()
    for i in range(5):
        try:
            r = urllib.request.urlopen(urllib.request.Request(f'{BASE}/{z}/{x}/{y}.pbf', headers=UA), timeout=60); b = r.read()
            if r.headers.get('Content-Encoding') == 'gzip' or b[:2] == b'\x1f\x8b': b = gzip.decompress(b)
            open(f, 'wb').write(b); return t, b
        except Exception as e:
            time.sleep(2 * (i + 1)); err = e
    raise err
KEEP_NAMES = {'name', 'name:es'}
def slim(b):
    tl = vt.tile(); tl.ParseFromString(b); out = vt.tile()
    for L in tl.layers:
        if L.name in ('housenumber',): continue  # números de casa: pesan mucho y no se usan
        keep = [i for i, k in enumerate(L.keys) if not ((k.startswith('name') and k not in KEEP_NAMES) or k in ('name_int', 'name_de', 'name_en'))]
        kmap = {old: new for new, old in enumerate(keep)}; used = collections.OrderedDict()
        NL = out.layers.add(); NL.version = L.version; NL.name = L.name; NL.extent = L.extent; NL.keys.extend([L.keys[i] for i in keep])
        feats = []
        for F in L.features:
            tags = []
            for j in range(0, len(F.tags), 2):
                k, v = F.tags[j], F.tags[j + 1]
                if k in kmap:
                    if v not in used: used[v] = len(used)
                    tags += [kmap[k], used[v]]
            feats.append((F, tags))
        for old in used: NL.values.add().CopyFrom(L.values[old])
        for F, tags in feats:
            NF = NL.features.add()
            if F.HasField('id'): NF.id = F.id
            NF.type = F.type; NF.geometry.extend(F.geometry); NF.tags.extend(tags)
    return out.SerializeToString()
data = {}; raw = slimmed = 0
with cf.ThreadPoolExecutor(6) as ex:
    for i, (t, b) in enumerate(ex.map(get, tiles)):
        s = slim(b); data[t] = s; raw += len(b); slimmed += len(s)
        if i % 100 == 0: print(i, len(tiles), flush=True)
print('teselas', len(data), 'MB crudo', round(raw / 1e6, 1), 'MB adelgazado', round(slimmed / 1e6, 1), flush=True)
# paquetes: z<=11 en uno; z12+z13 por tesela z12; z14 por tesela z13
packs = collections.defaultdict(dict)
for (z, x, y), b in data.items():
    key = 'low' if z <= 11 else f'a-{x >> (z - 12)}-{y >> (z - 12)}' if z <= 13 else f'b-{x >> 1}-{y >> 1}'
    packs[key][f'{z}/{x}/{y}'] = base64.b64encode(b).decode()
sizes = []
for k, d in packs.items():
    s = json.dumps(d, separators=(',', ':')); open(f'{OUT}/t/{k}.json', 'w').write(s); sizes.append(len(s))
print('paquetes', len(packs), 'MB', round(sum(sizes) / 1e6, 1), 'max KB', max(sizes) // 1000, flush=True)
# colonias y estaciones (de las teselas z14, que traen todo)
places, stations = {}, {}
for (z, x, y), b in data.items():
    if z != 14: continue
    d = mvt.decode(b, default_options={'y_coord_down': True})
    for f in d.get('place', {}).get('features', []):
        p = f['properties']; g = f['geometry']
        if g['type'] != 'Point' or p.get('class') not in ('suburb', 'neighbourhood', 'quarter', 'village', 'town', 'hamlet', 'city', 'isolated_dwelling'): continue
        lon, lat = lonlat(z, x, y, *g['coordinates']); nm = p.get('name:es') or p.get('name')
        if nm: places[(nm, round(lon, 3), round(lat, 3))] = {'n': nm, 'c': p.get('class'), 'lon': round(lon, 5), 'lat': round(lat, 5)}
    for f in d.get('poi', {}).get('features', []):
        p = f['properties']; g = f['geometry']
        if g['type'] != 'Point': continue
        cl, sc = p.get('class'), p.get('subclass')
        if cl in ('railway',) or sc in ('subway', 'station', 'halt', 'tram_stop', 'bus_station') or (cl == 'bus' and sc == 'bus_station'):
            lon, lat = lonlat(z, x, y, *g['coordinates']); nm = p.get('name:es') or p.get('name')
            if nm: stations[(nm, round(lon, 3), round(lat, 3))] = {'n': nm, 'c': cl, 's': sc, 'lon': round(lon, 5), 'lat': round(lat, 5)}
json.dump({'colonias': sorted(places.values(), key=lambda r: r['n']), 'estaciones': sorted(stations.values(), key=lambda r: r['n'])}, open(f'{OUT}/lugares_crudo.json', 'w'), ensure_ascii=False)
print('lugares', len(places), 'estaciones', len(stations), collections.Counter((s['c'], s['s']) for s in stations.values()).most_common(12), flush=True)
