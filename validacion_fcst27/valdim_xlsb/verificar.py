# -*- coding: utf-8 -*-
"""Audita el archivo generado: relee cada formula, la evalua contra CtaMens y la compara."""
import pickle, re, zipfile, hashlib, sys
import pandas as pd
import fmla, dump
from biff import colrow, sheet_map

F = 'FCST_2027_Cesion.xlsb'; SRC = 'FCST.xlsb'
ctx = fmla.Ctx(F); S = dump.sst(F); SM = {n:p for n,p in sheet_map(F)}

# ---------- 1. las 28 hojas originales no se tocaron ----------
za, zb = zipfile.ZipFile(SRC), zipfile.ZipFile(F)
orig = [n for n in za.namelist() if n not in
        ('xl/workbook.bin','xl/_rels/workbook.bin.rels','[Content_Types].xml',
         'xl/calcChain.bin','xl/sharedStrings.bin')]
malos = [n for n in orig if hashlib.md5(za.read(n)).digest() != hashlib.md5(zb.read(n)).digest()]
falta = [n for n in orig if n not in zb.namelist()]
print(f'1) Partes originales intactas: {len(orig)-len(malos)-len(falta)}/{len(orig)}'
      + (f'  DIFERENTES: {malos}' if malos else '') + (f'  FALTAN: {falta}' if falta else ''))

# ---------- 2. ninguna formula quedo mal codificada ----------
NUEVAS = ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea','Val_Origen']
celdas = {}
rotas = 0; nf = 0
for h in NUEVAS:
    celdas[h] = {}
    for r,c,v,f in dump.cells(F, SM[h], ctx, S):
        celdas[h][colrow(r,c)] = (v,f)
        if f:
            nf += 1
            if '<?' in f or '#REF' in f or 'FUNC' in f: rotas += 1; print('   ROTA', h, colrow(r,c), f)
print(f'2) Formulas escritas: {nf}   mal codificadas: {rotas}')

# ---------- 3. evaluar cada SUMIFS contra CtaMens ----------
df = pickle.load(open('ctamens_excelcols.pkl','rb'))
d = df.dropna(subset=['A_mes']).copy()
d['A_mes']=d['A_mes'].astype(int); d['B_cta']=d['B_cta'].astype(str)
d['Q_monto']=pd.to_numeric(d['Q_monto'],errors='coerce').fillna(0.0)
d=d[(d.A_mes>=202701)&(d.A_mes<=202712)]
XL2PD = {'R':'R_ramo','C':'C_ln','E':'E_reg','L':'L_tre','A':'A_mes','B':'B_cta','Q':'Q_monto'}

RX = re.compile(
 r'^(-?)SUMIFS\(CtaMens!\$Q\$4:\$Q\$201234,CtaMens!\$B\$4:\$B\$201234,(\d+),'
 r'CtaMens!\$A\$4:\$A\$201234,([A-Z]+)\$(\d+),'
 r'CtaMens!\$([A-Z])\$4:\$\1?[A-Z]*\$?201234,\$([A-Z]+)(\d+)\)(?:\+([A-Z]+)(\d+))?$')
RX2 = re.compile(
 r'^(-?)SUMIFS\(CtaMens!\$Q\$4:\$Q\$201234,CtaMens!\$B\$4:\$B\$201234,(\d+),'
 r'CtaMens!\$A\$4:\$A\$201234,([A-Z]+)\$(\d+),'
 r'CtaMens!\$([A-Z])\$4:\$[A-Z]+\$201234,\$([A-Z]+)(\d+)\)(?:\+([A-Z]+)(\d+))?$')

def val(h, a):
    return celdas[h].get(a, (None,None))[0]

probadas = 0; fallas = 0; peor = 0.0
for h in ['Val_Ramo','Val_LN','Val_Region','Val_TRea']:
    for a,(v,f) in celdas[h].items():
        if not f or 'SUMIFS' not in f: continue
        m = RX2.match(f)
        if not m:
            print('   NO PARSEADA', h, a, f); fallas += 1; continue
        neg, cta, mcol, mrow, dcol, mem_c, mem_r, pcol, prow = m.groups()
        mes = val(h, f'{mcol}{mrow}')
        miembro = val(h, f'{mem_c}{mem_r}')
        col = XL2PD[dcol]
        sel = d[(d.B_cta == cta) & (d[col] == miembro) & (d.A_mes == int(mes))]
        r = sel.Q_monto.sum() * (-1 if neg else 1)
        if pcol: r += val(h, f'{pcol}{prow}')
        dif = abs(r - v)
        peor = max(peor, dif)
        probadas += 1
        if dif > 0.005:
            fallas += 1
            if fallas < 6: print(f'   DESCUADRE {h}!{a}: archivo={v:,.2f} evaluado={r:,.2f}')
print(f'3) SUMIFS reevaluados contra CtaMens: {probadas}   descuadres: {fallas}   peor desviacion: {peor:.6f}')

# ---------- 4. referencias a ValDim y a ER apuntan al valor correcto ----------
VD = pickle.load(open('valdim.pkl','rb'))
def leer(hoja_ix_nombre, a):
    m = re.match(r'^([A-Z]+)\$?(\d+)$', a)
    col = 0
    for ch in m.group(1): col = col*26 + (ord(ch)-64)
    return (int(m.group(2))-1, col-1)
ok = mal = 0
for h in ['Val_Ramo','Val_LN','Val_Region','Val_TRea']:
    for a,(v,f) in celdas[h].items():
        if not f or not f.startswith('ValDim!'): continue
        r0,c0 = leer(None, f.split('!')[1].replace('$',''))
        esp = VD.get((r0,c0),(None,None))[0]
        if esp is None or abs(esp - v) > 0.005: mal += 1; print('   MAL', h, a, f, v, esp)
        else: ok += 1
print(f'4) Referencias =ValDim!... correctas: {ok}   incorrectas: {mal}')

# ---------- 5. SUM y restas ----------
def evalsimple(h, f, v):
    m = re.match(r'^SUM\(\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)\)$', f)
    if m:
        c,a1,_,a2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        s = sum(val(h, f'{c}{i}') or 0 for i in range(a1, a2+1))
        return s
    m = re.match(r'^([A-Z]+)(\d+)-([A-Z]+)(\d+)$', f)
    if m:
        a = val(h, m.group(1)+m.group(2)) or 0; b = val(h, m.group(3)+m.group(4)) or 0
        return a-b
    return None
ok = mal = 0
for h in NUEVAS:
    for a,(v,f) in celdas[h].items():
        if not f: continue
        r = evalsimple(h, f, v)
        if r is None: continue
        if abs(r - v) > 0.005: mal += 1; print('   MAL', h, a, f, v, r)
        else: ok += 1
print(f'5) SUM y restas internas correctas: {ok}   incorrectas: {mal}')

# ---------- 6. lectura completa con pyxlsb ----------
from pyxlsb import open_workbook
wb = open_workbook(F)
print(f'6) pyxlsb abre el libro: {len(wb.sheets)} hojas; ultimas -> {wb.sheets[-6:]}')
for h in NUEVAS:
    with wb.get_sheet(h) as sh:
        n = sum(1 for row in sh.rows() for c in row if c.v is not None)
    print(f'     {h}: {n} celdas con valor')
