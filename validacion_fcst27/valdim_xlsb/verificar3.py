# -*- coding: utf-8 -*-
import zipfile, hashlib, re, pickle, struct, collections
import fmla, dump, evaluador
from biff import sheet_map, colrow, records
DST, USR, MIO = 'FCST_2027_Cesion.xlsb', 'USR.xlsb', 'MIO.xlsb'
H = ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea']
zu, zd = zipfile.ZipFile(USR), zipfile.ZipFile(DST)
SMu = {n:p for n,p in sheet_map(USR)}; hojas_mod = {SMu[h] for h in H}
print('0) testzip:', zd.testzip(), '| mismas entradas:', sorted(zu.namelist()) == sorted(zd.namelist()), '| orden igual:', zu.namelist() == zd.namelist())
otras = [n for n in zu.namelist() if n not in hojas_mod]
dif = [n for n in otras if zu.read(n) != zd.read(n)]
raw = sum(1 for n in otras if zu.getinfo(n).CRC == zd.getinfo(n).CRC and zu.getinfo(n).compress_size == zd.getinfo(n).compress_size)
print(f'1) partes de tu archivo intactas: {len(otras)-len(dif)}/{len(otras)} (mismos bytes comprimidos: {raw}) {dif if dif else ""}')

# registros no-formula de las hojas modificadas, identicos
from reparar import records_raw
for h in H:
    a = [(rid, raw) for rid, pl, raw in records_raw(zu.read(SMu[h])) if rid not in (8,9,10,11)]
    b = [(rid, raw) for rid, pl, raw in records_raw(zd.read(SMu[h])) if rid not in (8,9,10,11)]
    na = sum(1 for rid,pl,raw in records_raw(zu.read(SMu[h])) if rid in (8,9,10,11))
    nb = sum(1 for rid,pl,raw in records_raw(zd.read(SMu[h])) if rid in (8,9,10,11))
    print(f'   {h:<12} registros no-formula identicos: {a == b} ({len(a)}) | celdas con formula {na} -> {nb}')

# 2) relectura
ctx = fmla.Ctx(DST); S = dump.sst(DST); SM = {n:p for n,p in sheet_map(DST)}
CEL = {}; nf = 0; rotas = []; errores = []; tipos = collections.Counter()
for h in H:
    CEL[h] = {}
    for r,c,v,f in dump.cells(DST, SM[h], ctx, S):
        CEL[h][(r,c)] = (v, f)
        if f:
            nf += 1; tipos[type(v).__name__] += 1
            if any(t in f for t in ('SINGLE','#REF','<?','FUNC')): rotas.append((h, colrow(r,c), f))
            if isinstance(v, str) and v.startswith('#'): errores.append((h, colrow(r,c), v))
print(f'2) formulas: {nf} | rotas: {len(rotas)} | valores de error guardados: {len(errores)} | tipos de resultado: {dict(tipos)}')
for x in (rotas + errores)[:5]: print('   ', x)

# 3) reevaluacion independiente contra CtaMens y hojas fuente
F = evaluador.Fuentes(DST, '../v3/ctamens_full.pkl', '../v3/celdas_ref.pkl')
E = evaluador.Evaluador(F, CEL)
mal = 0; peor = 0.0; n = 0; nsif = 0
for h in H:
    for k, (v, f) in CEL[h].items():
        if not f: continue
        e = E.evaluar(h, f); n += 1; nsif += f.count('SUMIFS(')
        if isinstance(v, bool) or isinstance(e, bool):
            if bool(v) != bool(e) or type(v) != type(e): mal += 1; print('   BOOL', h, colrow(*k), v, e)
        else:
            d = abs(float(e) - float(v)); peor = max(peor, d)
            if d > 0.005: mal += 1; print('   DESCUADRE', h, colrow(*k), v, e, f[:80])
print(f'3) reevaluadas {n} formulas ({nsif} SUMIFS) contra CtaMens/ER/2_Reservas/CAT/Gastos: descuadres {mal}, peor desviacion {peor:.6f}')

# 4) contra la version validada, trasladando columnas borradas
def mapa(h):
    if h == 'Val_TRea': return lambda c: c
    if h == 'Val_Ramo': return lambda c: (0 if c == 0 else (c-1 if 2 <= c <= 14 else None))
    return lambda c: (0 if c == 0 else (c-1 if c >= 2 else None))
def L(c): return colrow(0, c)[:-1]
def trad_formula(f, hoja):
    """Traduce una formula de MIO a coordenadas de USR."""
    def sust(m):
        pre, dc, col, dr, row = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        h = pre[:-1].strip("'") if pre else hoja
        if h in H:
            c = evaluador.col0(col); nc = mapa(h)(c)
            if nc is None: return (pre or '') + '#BORRADA'
            col = L(nc)
        return f'{pre or ""}{dc}{col}{dr}{row}'
    def una(pre, dc, col, dr, row, h):
        if h in H:
            nc = mapa(h)(evaluador.col0(col))
            if nc is None: return '#BORRADA'
            col = L(nc)
        return f'{dc}{col}{dr}{row}'
    def sust2(m):
        pre = m.group(1) or ''
        h = pre[:-1].strip("'") if pre else hoja
        a = una(pre, m.group(2), m.group(3), m.group(4), m.group(5), h)
        if m.group(6):
            b = una(pre, m.group(7), m.group(8), m.group(9), m.group(10), h)
            return f'{pre}{a}:{b}'
        return f'{pre}{a}'
    return re.sub(r"((?:'[^']+'|[A-Za-z0-9_]+)!)?(\$?)([A-Z]{1,3})(\$?)(\d+)(:(\$?)([A-Z]{1,3})(\$?)(\d+))?(?![\d(])", sust2, f)
MV = pickle.load(open('MIO_val.pkl','rb'))
ok = 0; bad = 0; fok = 0; fbad = []; esperadas = 0
for h in H:
    mp = mapa(h)
    for (r, c), (vm, fm) in MV[h].items():
        nc = mp(c)
        if nc is None: continue
        vd, fd = CEL[h].get((r, nc), (None, None))
        if fm:
            if h == 'Val_Resumen' and nc == 4 and 6 <= r <= 25:
                esperadas += 1       # antes Val_Ramo!$Q$..; ahora ABS(D..)<0.005
                if vd == vm: ok += 1
                else: bad += 1; print('   CUADRA DISTINTO', h, colrow(r,nc), vm, vd)
                continue
            ft = trad_formula(fm, h)
            if ft.replace('+-','-') == (fd or '').replace('+-','-'): fok += 1
            else: fbad.append((h, colrow(r,nc), ft[:90], (fd or '')[:90]))
            if isinstance(vm, bool) or isinstance(vd, bool):
                if vm == vd: ok += 1
                else: bad += 1; print('   VALOR', h, colrow(r,nc), vm, vd)
            else:
                if vd is not None and abs(float(vm) - float(vd)) < 0.005: ok += 1
                else: bad += 1; print('   VALOR', h, colrow(r,nc), vm, vd)
print(f'4) vs version validada (columnas trasladadas): valores iguales {ok}, distintos {bad}; formulas identicas tras traslado {fok}, distintas {len(fbad)}; ¿Cuadra? de Ramo reescritas {esperadas}')
cat = collections.Counter('borrada por ti' if not x[3] else 'otra' for x in fbad)
print('   formulas distintas por tipo:', dict(cat))
for x in [y for y in fbad if y[3]][:8]: print('   F', x)

from pyxlsb import open_workbook
wb = open_workbook(DST); print(f'5) pyxlsb abre: {len(wb.sheets)} hojas; {wb.sheets[-5:]}')
