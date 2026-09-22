# -*- coding: utf-8 -*-
"""Render HTML de hojas del .xlsb usando los estilos reales de styles.bin."""
import zipfile, struct, html, sys
from biff import records, sheet_map, colrow, rd_xlwstr
import fmla, dump
F = sys.argv[1] if len(sys.argv) > 1 else 'FCST_2027_Cesion.xlsb'
z = zipfile.ZipFile(F)
fonts, fills, xfs, fmts = [], [], [], {}
sec = None
for rid, pl in records(z.read('xl/styles.bin')):
    if rid == 611: sec = 'font'
    elif rid == 603: sec = 'fill'
    elif rid == 617: sec = 'xf'
    elif rid in (612, 604, 618, 613, 614): sec = None if rid != 613 else 'border'
    elif rid == 44: (i,) = struct.unpack_from('<H', pl, 0); fmts[i] = rd_xlwstr(pl, 2)[0]
    elif rid == 43 and sec == 'font': fonts.append(pl)
    elif rid == 45 and sec == 'fill': fills.append(pl)
    elif rid == 47 and sec == 'xf': xfs.append(pl)
def color(c8, default):
    t = c8[0] >> 1
    if t == 2: return '#%02x%02x%02x' % (c8[4], c8[5], c8[6])
    return default
def estilo(ix):
    if ix >= len(xfs): return '', 0, False
    p, fmt, fo, fi, bo, trot, ind, flags = struct.unpack_from('<HHHHHBBH', xfs[ix], 0)
    css = ''
    if fo < len(fonts):
        f = fonts[fo]; h, g, bls = struct.unpack_from('<HHH', f, 0)
        css += f'font-size:{h/20*1.33:.1f}px;' + ('font-weight:700;' if bls >= 700 else '') + ('font-style:italic;' if g & 2 else '')
        css += f'color:{color(f[12:20], "#000")};'
    if fi < len(fills):
        fl = fills[fi]; (fls,) = struct.unpack_from('<I', fl, 0)
        if fls == 1: css += f'background:{color(fl[4:12], "#fff")};'
    alc = flags & 7
    if alc == 2: css += 'text-align:center;'
    elif alc == 3: css += 'text-align:right;'
    return css, fmt, bo > 0
ctx = fmla.Ctx(F); S = dump.sst(F); SM = {n:p for n,p in sheet_map(F)}
def leer(h):
    sty = {}; row = None
    for rid, pl in records(z.read(SM[h])):
        if rid == 0: (row,) = struct.unpack_from('<I', pl, 0)
        elif rid in (1,2,4,5,6,7,8,9,10,11):
            (c,) = struct.unpack_from('<I', pl, 0); (s,) = struct.unpack_from('<I', pl, 4); sty[(row, c)] = s & 0xFFFFFF
    val = {(r, c): v for r, c, v, f in dump.cells(F, SM[h], ctx, S)}
    return val, sty
def tabla(h, filas, cols, anchos, titulo):
    val, sty = leer(h)
    th = ''.join(f'<th class=cs style="width:{w}px">{colrow(0,c)[:-1]}</th>' for c, w in zip(cols, anchos))
    trs = []
    for r in filas:
        tds = []
        for c in cols:
            v = val.get((r, c)); css, fmt, borde = estilo(sty.get((r, c), 0))
            bd = 'border:1px solid #d4d4d4;' if borde else 'border:1px solid #f0f0f0;'
            if v is None: tds.append(f'<td style="{css}{bd}"></td>'); continue
            if isinstance(v, bool): txt = 'VERDADERO' if v else 'FALSO'; css += 'text-align:center;'
            elif isinstance(v, float):
                txt = (f'{v:,.2f}' if fmt not in (0,) else (f'{v:,.2f}' if abs(v) >= 1000 or v != int(v) else f'{int(v)}'))
                if abs(v) < 0.005: txt = '0.00' if fmt else txt
                css += 'text-align:right;'
            else: txt = html.escape(str(v))
            if isinstance(v, str) and v.startswith('#ERR'): css += 'color:#c00;font-weight:700;'
            tds.append(f'<td style="{css}{bd}overflow:hidden;white-space:nowrap;">{txt}</td>')
        trs.append(f'<tr><th class=rh>{r+1}</th>{"".join(tds)}</tr>')
    return f'<div class=wrap><div class=tab>{titulo}</div><table><tr><th class=cs style="width:28px"></th>{th}</tr>{"".join(trs)}</table></div>'
partes = [
 tabla('Val_Resumen', list(range(4, 26)), list(range(0, 17)), [230] + [98, 98, 90, 72]*4, 'Val_Resumen'),
 tabla('Val_Ramo', list(range(5, 25)), list(range(0, 14)), [120, 8] + [92]*12, 'Val_Ramo · bloque 9 Prima Tomada'),
]
HTML = f'''<html><head><meta charset=utf-8><style>
body{{font-family:Arial,Helvetica,sans-serif;background:#f3f3f3;margin:0;padding:14px}}
.wrap{{background:#fff;border:1px solid #cfcfcf;margin-bottom:18px;padding:0 0 8px 0;display:inline-block}}
.tab{{display:inline-block;background:#1a5632;color:#fff;font-weight:700;padding:4px 14px;border-radius:0 0 6px 0;margin-bottom:6px;font-size:13px}}
table{{border-collapse:collapse;table-layout:fixed;margin:0 8px;font-size:12px}}
th,td{{padding:2px 5px;height:17px}}
.cs,.rh{{background:#e8e8e8;color:#444;font-weight:600;text-align:center;font-size:11px;border:1px solid #cfcfcf}}
td{{font-variant-numeric:tabular-nums}}
</style></head><body>{"<br>".join(partes)}</body></html>'''
open(sys.argv[2] if len(sys.argv) > 2 else 'vista.html', 'w').write(HTML)
