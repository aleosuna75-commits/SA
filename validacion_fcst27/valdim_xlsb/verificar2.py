# -*- coding: utf-8 -*-
"""Auditoria del libro generado: integridad, estructura, estilos y reevaluacion de TODAS las formulas nuevas."""
import zipfile, hashlib, re, struct, pickle, collections
import pandas as pd, xml.dom.minidom as MD
import fmla, dump
from biff import records, sheet_map, colrow

F, SRC = 'FCST_2027_Cesion.xlsb', 'FCST.xlsb'
NUEVAS = ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea','Val_Origen','Val_ValDim']
za, zb = zipfile.ZipFile(SRC), zipfile.ZipFile(F)
print('0) zip testzip ->', zb.testzip(), '| primera entrada:', zb.namelist()[0])

# 1) partes originales intactas (incluido calcChain)
cambiadas = {'xl/workbook.bin','xl/_rels/workbook.bin.rels','[Content_Types].xml','xl/sharedStrings.bin','xl/styles.bin'}
orig = [n for n in za.namelist() if n not in cambiadas]
malos = [n for n in orig if n not in zb.namelist() or hashlib.md5(za.read(n)).digest() != hashlib.md5(zb.read(n)).digest()]
raw_igual = sum(1 for n in orig if za.getinfo(n).compress_size == zb.getinfo(n).compress_size and za.getinfo(n).CRC == zb.getinfo(n).CRC)
print(f'1) partes originales intactas: {len(orig)-len(malos)}/{len(orig)} (mismos bytes comprimidos: {raw_igual}); calcChain presente: {"xl/calcChain.bin" in zb.namelist()}' + (f'  DIFERENTES: {malos}' if malos else ''))
for p in ['[Content_Types].xml','xl/_rels/workbook.bin.rels']: MD.parseString(zb.read(p))
ct = zb.read('[Content_Types].xml').decode(); rl = zb.read('xl/_rels/workbook.bin.rels').decode()
print('   XML ok; overrides hojas nuevas:', sum(1 for i in range(29,36) if f'sheet{i}.bin' in ct), '/7; rels:', sum(1 for i in range(29,36) if f'sheet{i}.bin' in rl), '/7; calcChain sigue en rels y content types:', 'calcChain' in rl and 'calcChain' in ct)

# 2) estilos: contadores y referencias
def st_parse(buf):
    cnt = {}; lists = collections.defaultdict(list); sec = None
    for rid, pl in records(buf):
        if rid in (611,603,613,617): cnt[rid] = struct.unpack_from('<I',pl,0)[0]; sec = rid
        elif rid in (612,604,614,618): sec = None
        elif sec and rid in (43,45,46,47): lists[sec].append(pl)
    return cnt, lists
cnt, lists = st_parse(zb.read('xl/styles.bin')); cnt0, _ = st_parse(za.read('xl/styles.bin'))
ok = all(cnt[k] == len(lists[k]) for k in cnt)
print(f'2) styles.bin: fuentes {cnt0[611]}->{cnt[611]}, rellenos {cnt0[603]}->{cnt[603]}, bordes {cnt0[613]}->{cnt[613]}, cellXfs {cnt0[617]}->{cnt[617]}; contadores = registros reales: {ok}')
xfs = lists[617]; bad = 0
for i in range(cnt0[617], cnt[617]):
    p, fmt, fo, fi, bo, trot, ind, flags, attr = struct.unpack_from('<HHHHHBBHH', xfs[i], 0)
    if fo >= cnt[611] or fi >= cnt[603] or bo >= cnt[613] or len(xfs[i]) != 16: bad += 1
lens = {43: {len(x) for x in lists[611][cnt0[611]:]}, 45: {len(x) for x in lists[603][cnt0[603]:]}, 46: {len(x) for x in lists[613][cnt0[613]:]}}
print(f'   xfs nuevos con referencias invalidas: {bad}; longitudes nuevas font/fill/border: {lens}')

# 3) hojas nuevas: estructura + celdas
ctx = fmla.Ctx(F); S = dump.sst(F); SM = {n:p for n,p in sheet_map(F)}
CEL = {}; nf = 0; rotas = 0; orden_mal = 0; estilos_mal = 0
for h in NUEVAS:
    CEL[h] = {}
    buf = zb.read(SM[h]); row = None; ult = -1; ids = [rid for rid,_ in records(buf)]
    for rid, pl in records(buf):
        if rid == 0: (row,) = struct.unpack_from('<I',pl,0); ult = -1
        elif rid in (1,2,4,5,6,7,8,9,10,11):
            (c,) = struct.unpack_from('<I',pl,0); (sty,) = struct.unpack_from('<I',pl,4)
            if c <= ult: orden_mal += 1
            ult = c
            if (sty & 0xFFFFFF) >= cnt[617]: estilos_mal += 1
    assert ids[0]==129 and ids[-1]==130 and ids.count(145)==1 and ids.count(146)==1
    for r,c,v,f in dump.cells(F, SM[h], ctx, S):
        CEL[h][(r,c)] = (v,f)
        if f:
            nf += 1
            if '<?' in f or '#REF' in f or 'FUNC' in f: rotas += 1; print('   ROTA', h, colrow(r,c), f[:120])
print(f'3) hojas nuevas: {len(NUEVAS)}; formulas: {nf}; mal codificadas: {rotas}; celdas fuera de orden: {orden_mal}; estilos invalidos: {estilos_mal}')

# 4) reevaluacion de todas las formulas
d = pickle.load(open('ctamens_full.pkl','rb')); REF = pickle.load(open('celdas_ref.pkl','rb')); VD = pickle.load(open('valdim.pkl','rb'))
COLS = {'A':'A_mes','B':'B_cta','C':'C_ln','E':'E_reg','L':'L_tre','Q':'Q_monto','R':'R_ramo','W':'W_ced','AA':'AA_xl','AB':'AB_recu','AC':'AC_evcat','AD':'AD_attcat','AE':'AE_sincatced','AF':'AF_gtos'}
AMT = ['Q_monto','W_ced','AA_xl','AB_recu','AC_evcat','AD_attcat','AE_sincatced','AF_gtos']
G1 = {}; G2 = {}
for dc in ['R_ramo','C_ln','E_reg','L_tre']:
    G1[dc] = d.groupby([dc,'B_cta','A_mes'])[AMT].sum().to_dict('index')
    G2[dc] = d.groupby([dc,'A_mes'])[AMT].sum().to_dict('index')
def col0(letters):
    n = 0
    for ch in letters: n = n*26 + ord(ch)-64
    return n-1
def a1(ref):
    m = re.match(r'^\$?([A-Z]+)\$?(\d+)$', ref); return int(m.group(2))-1, col0(m.group(1))
XEV = 0.0
CAT = {}; GAS = {}
for r,c,v,f in dump.cells(SRC, SM['CAT'], ctx, S):
    if (r+1) in (27,41,83,84): CAT[(r,c)] = float(v) if isinstance(v,(int,float)) else 0.0
for r,c,v,f in dump.cells(SRC, SM['Gastos'], ctx, S):
    if (r+1) == 12: GAS[(r,c)] = float(v) if isinstance(v,(int,float)) else 0.0
def r3(hoja, ref):
    r, c = a1(ref)
    if hoja == 'CtaMens': raise ValueError
    if hoja in ('ER','Parametros','Parámetros','Inicio'):
        v = REF['Parametros' if hoja.startswith('Par') else hoja].get((r,c))
    elif hoja == '2_Reservas': v = REF['2_Reservas'].get((r,c),(None,None))[0]
    elif hoja in ('ER_ram','ER_ln','ER_reg','ER_tre'): v = REF[hoja].get((r,c))
    elif hoja == 'CAT': v = CAT.get((r,c), 0.0)
    elif hoja == 'Gastos': v = GAS.get((r,c), 0.0)
    elif hoja == 'ValDim': v = VD.get((r,c),(None,None))[0]
    elif hoja in CEL: v = CEL[hoja].get((r,c),(None,None))[0]
    else: raise KeyError(hoja)
    return v if v is not None else 0.0
def rango3(hoja, rng):
    a, b = rng.split(':'); (r1,c1), (r2,c2) = a1(a), a1(b)
    return sum((r3(hoja, colrow(r,c)) or 0.0) for r in range(r1,r2+1) for c in range(c1,c2+1) if isinstance(r3(hoja, colrow(r,c)), (int,float)))
class Ev:
    def __init__(self, hoja): self.h = hoja
    def RL(self, ref):
        v = CEL[self.h].get(a1(ref),(None,None))[0]; return v if v is not None else 0.0
    def SUMR(self, rng): return rango3(self.h, rng)
    def SIF(self, args):
        toks = [t.strip() for t in args.split(',')]
        sc = re.match(r"^CtaMens!\$([A-Z]+)\$4:\$[A-Z]+\$201234$", toks[0]).group(1)
        crit = {}
        for k in range(1, len(toks), 2):
            cc = re.match(r"^CtaMens!\$([A-Z]+)\$4:\$[A-Z]+\$201234$", toks[k]).group(1)
            cv = toks[k+1]
            crit[cc] = float(cv) if re.match(r'^-?\d+(\.\d+)?$', cv) else self.RL(cv)
        dimcol = [c for c in crit if c in ('R','C','E','L')][0]; dc = COLS[dimcol]
        mes = int(crit['A']); mb = crit[dimcol]
        if dc == 'L_tre': mb = float(mb)
        if 'B' in crit:
            row = G1[dc].get((mb, str(int(crit['B'])), mes))
        else:
            row = G2[dc].get((mb, mes))
        return float(row[COLS[sc]]) if row else 0.0
def evaluar(hoja, f):
    ev = Ev(hoja); s = f
    hold = []
    def keep(txt):
        hold.append(txt); return f'__H{len(hold)-1}__'
    s = re.sub(r'SUMIFS\(([^()]*)\)', lambda m: keep(f'ev.SIF("{m.group(1)}")'), s)
    s = re.sub(r"SUM\('?([A-Za-z0-9_]+)'?!(\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)", lambda m: keep(f'rango3("{m.group(1)}","{m.group(2)}")'), s)
    s = re.sub(r'SUM\((\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+)\)', lambda m: keep(f'ev.SUMR("{m.group(1)}")'), s)
    s = s.replace('ABS(', 'abs(').replace('xEvCat', 'XEV')
    s = re.sub(r"'([^']+)'!(\$?[A-Z]+\$?\d+)", lambda m: keep(f'r3("{m.group(1)}","{m.group(2)}")'), s)
    s = re.sub(r"([A-Za-z0-9_]+)!(\$?[A-Z]+\$?\d+)", lambda m: keep(f'r3("{m.group(1)}","{m.group(2)}")'), s)
    s = re.sub(r'(?<![A-Za-z0-9_"])(\$?[A-Z]{1,2}\$?\d+)(?![\d"])', lambda m: f'ev.RL("{m.group(1)}")', s)
    for i, t in enumerate(hold): s = s.replace(f'__H{i}__', t)
    return eval(s, {'ev':ev,'r3':r3,'rango3':rango3,'abs':abs,'XEV':XEV})
tot = 0; mal = 0; peor = 0.0; nsif = 0; porhoja = collections.Counter()
for h in NUEVAS:
    for (r,c),(v,f) in CEL[h].items():
        if not f: continue
        try: e = evaluar(h, f)
        except Exception as ex:
            mal += 1; print('   NO EVALUADA', h, colrow(r,c), f[:100], '->', ex); continue
        tot += 1; porhoja[h] += 1; nsif += f.count('SUMIFS(')
        if isinstance(v, bool) or isinstance(e, bool):
            if bool(v) != bool(e): mal += 1; print('   BOOL MAL', h, colrow(r,c), f, v, e)
        elif isinstance(v, str) or isinstance(e, str):
            if str(v) != str(e): mal += 1; print('   TEXTO MAL', h, colrow(r,c), f, v, e)
        else:
            dif = abs(float(e) - float(v)); peor = max(peor, dif)
            if dif > 0.005: mal += 1; 
            if dif > 0.005 and mal < 8: print(f'   DESCUADRE {h}!{colrow(r,c)}: archivo={v:,.2f} evaluado={e:,.2f}  {f[:90]}')
print(f'4) formulas reevaluadas: {tot} (SUMIFS dentro: {nsif}); descuadres: {mal}; peor desviacion: {peor:.6f}')
print('   por hoja:', dict(porhoja))

# 5) lectura completa con pyxlsb
from pyxlsb import open_workbook
wb = open_workbook(F); print(f'5) pyxlsb: {len(wb.sheets)} hojas; ultimas: {wb.sheets[-7:]}')
for h in NUEVAS:
    with wb.get_sheet(h) as sh: n = sum(1 for row in sh.rows() for c in row if c.v is not None)
    print(f'     {h}: {n} celdas con valor')
