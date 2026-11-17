#!/usr/bin/env python3
"""Revisión mecánica de lo que traen los agentes, antes de ubicarlo en el mapa.

Un anuncio pasa solo si:
  - su URL es la ficha individual de un portal conocido (no una página de resultados),
  - el precio aparece en la evidencia citada (en cualquier formato: $18,500 · 18.500 · 18500 MXN),
  - la colonia aparece en la evidencia, el título o la URL,
  - la evidencia no dice que ya no está publicado o que se rentó,
  - el lote del agente no reprobó la muestra revisada en sus fichas (2 de 3 o más mal: se descarta el lote entero).

Uso: python3 -I verificar.py salida.json entrada1.json [entrada2.json ...]
Las entradas pueden ser {"zonas": [...]} (búsquedas) o {"lotes": [...]} (resultado de un workflow con muestra).
"""
import json, re, sys, unicodedata, collections

OUT, *SRC = sys.argv[1:]

def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', str(s or '').lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', s)).strip()

INDIVIDUAL = [
    r'inmuebles24\.com/propiedades/.*\d{7,}\.html',
    r'vivanuncios\.com\.mx/a-[^/]+/[^/]+/[^/]+/\d{6,}',
    r'propiedades\.com/inmuebles/.+-\d{6,}',
    r'(departamento|casa|inmueble|articulo|loft)\.mercadolibre\.com\.mx/MLM-?\d{6,}',
    r'lamudi\.com\.mx/(en/)?(property|detalle|propiedad)/',
    r'pincali\.com/(en/)?(home|inmueble|propiedad)/',
    r'easybroker\.com/.*(listings|inmueble|propiedad|property)',
    r'icasas\.mx/propiedad/',
    r'homie\.mx/detalle/',
    r'casasyterrenos\.com/.*propiedad',
    r'metroscubicos\.com/MLM-?\d{6,}',
    r'century21mexico\.com/(propiedad|p)/',
    r'remax\.com\.mx/(propiedades|listings)/',
    r'segundamano\.mx/.+/\d{6,}',
    r'dadaroom\.com/.+\d', r'compartodepa\.com\.mx/.+\d', r'roomgo\.com\.mx/.+\d',
]
MUERTO = re.compile(r'ya no est[aá] (publicado|disponible)|finalizado|\brentad[oa]\b|no disponible|fuera del mercado|vendid[oa]', re.I)
STOP = {'col', 'colonia', 'de', 'del', 'la', 'las', 'los', 'el', 'y', 'cdmx', 'seccion', 'secc', 'sur', 'norte', 'oriente', 'poniente', 'centro', 'i', 'ii', 'iii', 'iv', 'v'}

def a_int(t):
    t = t.replace(' ', ',')
    m = re.fullmatch(r'(\d{1,3}(?:[.,]\d{3})+)(?:[.,](\d{1,2}))?', t)
    if m: return int(re.sub(r'[.,]', '', m.group(1)))
    m = re.fullmatch(r'(\d+)(?:[.,]\d{1,2})?', t)
    return int(m.group(1)) if m else None
def precio_en(precio, texto):
    nums = {n for n in (a_int(m.group(0)) for m in re.finditer(r'\d{1,3}(?:[ .,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?', texto)) if n is not None}
    p = int(round(precio))
    if any(abs(n - p) <= 1 for n in nums): return True
    # "18.5k", "18 mil"
    for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(k|mil)\b', texto, re.I):
        if abs(float(m.group(1).replace(',', '.')) * 1000 - p) <= 50: return True
    return False

def colonia_en(col, texto):
    w = [x for x in norm(col).split() if x not in STOP and len(x) > 2]
    if not w: w = [x for x in norm(col).split() if len(x) > 1]
    t = ' ' + norm(texto) + ' '
    return bool(w) and all(' ' + x + ' ' in t or (len(x) > 5 and x[:-1] in t) for x in w)

lotes = []
for f in SRC:
    d = json.load(open(f, encoding='utf8'))
    if 'zonas' in d: lotes += [{'key': z.get('zona'), 'anuncios': z.get('confirmados', []), 'muestra': None} for z in d['zonas']]
    if 'lotes' in d: lotes += [{'key': l.get('key'), 'anuncios': (l.get('r') or {}).get('anuncios', []), 'muestra': l.get('muestra')} for l in d['lotes']]

ok, motivos, por_lote = [], collections.Counter(), []
for l in lotes:
    m = [x for x in ((l['muestra'] or {}).get('revisados') or []) if '403' not in str(x.get('nota') or '')]  # 403: el portal no deja abrirla; no cuenta
    malos = sum(1 for x in m if not x.get('abre', x.get('encontrado', True)) or x.get('coincide_precio') is False or x.get('vigente', x.get('vigente_segun_buscador')) == 'no')
    if m and malos >= 2 and malos >= len(m) * .6:
        por_lote.append((l['key'], len(l['anuncios']), 0, f'lote descartado: muestra {malos}/{len(m)} mal')); motivos['lote reprobado'] += len(l['anuncios']); continue
    muertos = {x['url'] for x in m if x.get('vigente', x.get('vigente_segun_buscador')) == 'no'}
    n0 = len(ok)
    for a in l['anuncios']:
        url, ev = str(a.get('url') or '').strip(), str(a.get('evidencia') or '')
        if not any(re.search(p, url) for p in INDIVIDUAL): motivos['url no individual'] += 1; continue
        if url in muertos or MUERTO.search(ev): motivos['ya no publicado'] += 1; continue
        if not isinstance(a.get('precio'), (int, float)) or not (1500 <= a['precio'] <= 400000): motivos['precio fuera de rango'] += 1; continue
        if not precio_en(a['precio'], ev): motivos['precio no está en la evidencia'] += 1; continue
        if not a.get('colonia') or not colonia_en(a['colonia'], ev + ' ' + str(a.get('titulo') or '') + ' ' + url.replace('-', ' ')): motivos['colonia no está en la evidencia'] += 1; continue
        ok.append(a)
    por_lote.append((l['key'], len(l['anuncios']), len(ok) - n0, ''))

json.dump({'zonas': [{'zona': 'verificados', 'confirmados': ok}]}, open(OUT, 'w', encoding='utf8'), ensure_ascii=False)
for k, n, v, nota in por_lote: print(f'  {k}: {v}/{n} {nota}')
print('pasan', len(ok), 'de', sum(len(l['anuncios']) for l in lotes), dict(motivos))
