# -*- coding: utf-8 -*-
import zipfile, struct, re, pickle, collections, hashlib
import xml.dom.minidom as MD
import pandas as pd, numpy as np
import fmla, dump
from biff import records, sheet_map, colrow
from reparar import records_raw
SRC, DST = 'NUESTRO.xlsb', 'FCST_2027_Cesion.xlsb'
za, zb = zipfile.ZipFile(SRC), zipfile.ZipFile(DST)
SMa = {n:p for n,p in sheet_map(SRC)}; SMb = {n:p for n,p in sheet_map(DST)}
print('0) testzip:', zb.testzip())
cambio_esperado = {SMa['CtaMens'], 'xl/worksheets/_rels/sheet23.bin.rels', 'xl/workbook.bin', 'xl/_rels/workbook.bin.rels',
                   '[Content_Types].xml', 'xl/sharedStrings.bin'} | {SMa[h] for h in ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea']}
na, nb = set(za.namelist()), set(zb.namelist())
print('   solo en original:', sorted(na-nb), '| solo en nuevo:', sorted(nb-na))
iguales = [n for n in na & nb if n not in cambio_esperado]
mal = [n for n in iguales if za.getinfo(n).CRC != zb.getinfo(n).CRC or za.read(n) != zb.read(n)]
print(f'1) partes que no debian cambiar: {len(iguales)-len(mal)}/{len(iguales)} identicas', mal[:5])
for p in ['[Content_Types].xml','xl/_rels/workbook.bin.rels','xl/worksheets/_rels/sheet23.bin.rels']: MD.parseString(zb.read(p))
ct = zb.read('[Content_Types].xml').decode(); rl = zb.read('xl/worksheets/_rels/sheet23.bin.rels').decode()
print('   XML ok | binaryIndex23 en CT:', 'binaryIndex23' in ct, '| en rels de CtaMens:', 'BinaryIndex' in rl, '| sheet34 en CT:', 'sheet34.bin' in ct)
# 2) workbook.bin
ra = list(records(za.read('xl/workbook.bin'))); rb = list(records(zb.read('xl/workbook.bin')))
dif = collections.Counter()
ia = collections.Counter(rid for rid,_ in ra); ib = collections.Counter(rid for rid,_ in rb)
print('2) workbook.bin: registros por tipo que cambian en cantidad:', {k:(ia[k],ib[k]) for k in set(ia)|set(ib) if ia[k]!=ib[k]})
cp_a = [pl for rid,pl in ra if rid==157][0]; cp_b = [pl for rid,pl in rb if rid==157][0]
print('   BrtCalcProp:', cp_a.hex(), '->', cp_b.hex(), '| solo cambia el bit fFullCalcOnLoad:', cp_a[:-2]==cp_b[:-2] and (struct.unpack('<H',cp_b[-2:])[0] ^ struct.unpack('<H',cp_a[-2:])[0]) == 1)
xa = [pl for rid,pl in ra if rid==362][0]; xb = [pl for rid,pl in rb if rid==362][0]
print('   Xti:', struct.unpack_from('<I',xa,0)[0], '->', struct.unpack_from('<I',xb,0)[0], '| tabla previa intacta:', xb[4:4+len(xa)-4]==xa[4:])
otros_a = [(rid,pl) for rid,pl in ra if rid not in (156,157,362)]; otros_b = [(rid,pl) for rid,pl in rb if rid not in (156,157,362)]
print('   resto de registros identicos:', otros_a == otros_b)
# 3) CtaMens por registros
FILAS = pickle.load(open('reparto.pkl','rb'))['filas']
A = list(records_raw(za.read(SMa['CtaMens']))); Bq = list(records_raw(zb.read(SMb['CtaMens'])))
print(f'3) CtaMens: registros {len(A)} -> {len(Bq)} (mismo numero: {len(A)==len(Bq)})')
row = -1; distintos = 0; ok_val = 0; mal_val = []; estilo_mal = 0; tipos = collections.Counter()
for (rida, pla, rawa), (ridb, plb, rawb) in zip(A, Bq):
    if rida == 0: (row,) = struct.unpack_from('<I', pla, 0)
    if rawa == rawb: continue
    distintos += 1
    (col,) = struct.unpack_from('<I', pla, 0)
    if pla[4:8] != plb[4:8]: estilo_mal += 1
    if row == 1: tipos['subtotal fila 2'] += 1; continue
    tipos[(rida, ridb, col)] += 1
    v = struct.unpack_from('<d', plb, 8)[0]; esp = FILAS.get(row+1, {}).get(col)
    if esp is not None and abs(v - esp) < 1e-9: ok_val += 1
    else: mal_val.append((row+1, col, v, esp))
print(f'   registros distintos: {distintos} | valores correctos {ok_val} | incorrectos {len(mal_val)} | estilo alterado {estilo_mal}')
print('   tipos de cambio:', {str(k): v for k, v in tipos.items()})
# 4) formulas de las hojas Val
ctx = fmla.Ctx(DST); S = dump.sst(DST)
H = ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea','Val_CAT']
nf = 0; malas = []; errores = []
for h in H:
    for r,c,v,f in dump.cells(DST, SMb[h], ctx, S):
        if f:
            nf += 1
            if any(t in f for t in ('<?','FUNC','#REF','SINGLE')): malas.append((h, colrow(r,c), f))
            if isinstance(v,str) and v.startswith('#'): errores.append((h, colrow(r,c), v))
print(f'4) formulas en hojas Val: {nf} | mal decodificadas {len(malas)} | con error guardado {len(errores)}')
# 5) lectura con pyxlsb de CtaMens nueva
from pyxlsb import open_workbook
NOM = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z','AA','AB','AC','AD','AE','AF','AG','AH']
def leer(F):
    recs = []
    with open_workbook(F).get_sheet('CtaMens') as sh:
        for i, rw in enumerate(sh.rows()):
            if i < 3: continue
            d = {NOM[c.c]: c.v for c in rw if c.c < len(NOM) and c.v is not None}
            if d: d['_fila'] = i+1; recs.append(d)
    return pd.DataFrame(recs).set_index('_fila')
a = leer(SRC); b = leer(DST)
cols = [c for c in a.columns if c not in ('AC','AD','AE','AF')]
dif_otros = int(((a[cols].fillna('∅').astype(str)) != (b[cols].fillna('∅').astype(str))).sum().sum())
print(f'5) CtaMens releida: {len(b)} renglones | celdas distintas fuera de AC:AF: {dif_otros}')
b2 = b.copy()
for c in ['Q','AC','AD','AE','AF']: b2[c] = pd.to_numeric(b2[c], errors='coerce').fillna(0.0)
b2['A'] = pd.to_numeric(b2['A'], errors='coerce'); b2['B'] = b2['B'].astype(str).str.replace('.0','',regex=False)
print('   totales AC %.2f AD %.2f AE %.2f AF %.2f' % tuple(b2[c].sum() for c in ['AC','AD','AE','AF']))
nz = b2[(b2[['AC','AD','AE','AF']] != 0).any(axis=1)]
print('   renglones con importe:', len(nz), '| todos con B=61:', bool((nz['B']=='61').all()))
ad = b2[b2['AD'] != 0]; ratio = (ad['AE']/ad['AD']).round(10)
print('   AE/AD por (Cebe, territorio R05 o no):', ad.assign(r=ratio, u=ad['E']=='R05').groupby(['D','u'])['r'].agg(['min','max']).to_dict('index'))
print('6) pyxlsb abre el libro:', len(open_workbook(DST).sheets), 'hojas; ultimas:', open_workbook(DST).sheets[-6:])
