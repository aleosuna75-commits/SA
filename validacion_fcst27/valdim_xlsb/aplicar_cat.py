# -*- coding: utf-8 -*-
"""Aplica el reparto de CAT y Gastos a CtaMens, agrega la hoja Val_CAT y recalcula los valores guardados."""
import zipfile, struct, re, os, shutil, subprocess, tempfile, pickle, collections, sys
import pandas as pd
import xlsbw as W
from biff import records, sheet_map, colrow
from reparar import records_raw, partir, rgce_de
import fmla, dump, evaluador2 as EV

import os as _os
SRC, TMP, DST = 'NUESTRO.xlsb', 'TMP_CAT.xlsb', _os.environ.get('DST_XLSB', 'FCST_2027_Cesion.xlsb')
R = pickle.load(open('reparto.pkl','rb')); FILAS, RESP, TASA = R['filas'], R['respaldo'], R['tasa']
ST = dict(TIT=1006, SUB=1007, NOTA=1008, BAR=1009, BAR_C=1010, HDR=1011, HDR_C=1012, TXT=1013, OBS=1014, NUM=1015,
          NUM_B=1016, NUM_G=1017, NUM_Y=1018, LBL_B=1019, LBL_G=1020, LBL_Y=1021, BOOL=1022, MES=1023, TXT_B=1024)
IX = dict(CtaMens=3, Inicio=11, Gastos=14, CAT=15, ER=56, Val_Resumen=68)
XTI_EXTRA = [(0, 28, 28)]                       # Val_Resumen
F0, F1 = 3, 201233
MESES = list(range(202701, 202713)); NOMMES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
H_VAL = ['Val_Resumen','Val_Ramo','Val_LN','Val_Region','Val_TRea','Val_CAT']

# ======================================================= CtaMens
def reescribir_ctamens(buf):
    tot = collections.defaultdict(float)
    for d in FILAS.values():
        for c, v in d.items(): tot[c] += v
    out = bytearray(); row = -1; vistos = set(); sub = {}
    for rid, pl, raw in records_raw(buf):
        if rid == 0:
            (row,) = struct.unpack_from('<I', pl, 0)
        elif rid in (1, 2, 5) and row >= 3:
            (col,) = struct.unpack_from('<I', pl, 0)
            if 28 <= col <= 31:
                d = FILAS.get(row + 1)
                if d is not None and col in d:
                    v = d[col]; v = 0.0 if v == 0 else v
                    out += W.rec(5, pl[:8] + struct.pack('<d', v)); vistos.add((row + 1, col)); continue
        elif rid == 9 and row == 1:
            (col,) = struct.unpack_from('<I', pl, 0)
            if 28 <= col <= 31:
                out += W.rec(9, pl[:8] + struct.pack('<d', tot[col]) + pl[16:]); sub[col] = tot[col]; continue
        out += raw
    esperado = {(f, c) for f, d in FILAS.items() for c in d}
    faltan = esperado - vistos
    if faltan: raise RuntimeError(f'{len(faltan)} celdas de CtaMens no encontradas, p.ej. {sorted(faltan)[:3]}')
    return bytes(out), len(vistos), sub

# ======================================================= Val_CAT
P = None
def T(c, s, st): return W.c_isst(c, P.add(s), ST[st])
def N(c, v, st): return W.c_num(c, v, ST[st])
def B(c, st):    return W.c_blank(c, ST[st])
def FN(c, g, st): return W.c_fmla_num(c, 0.0, g, ST[st])
def FS(c, g, st): return W.c_fmla_str(c, '', g, ST[st])
def FB(c, g, st): return W.c_fmla_bool(c, False, g, ST[st])
def A3(col): return W.area3d(IX['CtaMens'], F0, F1, col, col)
def sumifs(sumcol, pares):
    g = A3(sumcol)
    for c, v in pares: g += A3(c) + v
    return g + W.funcvar(1 + 2*len(pares), W.IF_SUMIFS)
def mes(col): return W.ref(3, col, crel=True)
def cat(r1, j): return W.ref3d(IX['CAT'], r1-1, 7+j)
def er_mes(fila, j):
    g = W.ref3d(IX['ER'], fila-1, 5+j)
    return g if j == 0 else g + W.ref3d(IX['ER'], fila-1, 4+j) + W.SUB
def cuadra(r, c1, c2):
    a = W.area(r, r, c1, c2)
    return a + W.funcvar(1, 7) + W.func_fix(24) + a + W.funcvar(1, 6) + W.func_fix(24) + W.ADD + W.num(0.005) + W.LT

C1, C2, C3 = 2, 15, 28            # bloques de meses: C..N, P..AA, AC..AN
QC = 40                           # columna AO: ¿Cuadra?

def hoja_val_cat():
    global CATV
    _ctx = fmla.Ctx(SRC); _S = dump.sst(SRC); _SM = {n:p for n,p in sheet_map(SRC)}
    CATV = {(rr,cc): v for rr,cc,v,f in dump.cells(SRC, _SM['CAT'], _ctx, _S)}
    rows = {}; r = 0
    def fila(cs):
        nonlocal r; rows[r] = cs; r += 1
    def barra(txt, ultima=13):
        fila([T(0, txt, 'BAR')] + [B(c, 'BAR') for c in range(1, ultima+1)])
    fila([T(0, "CAT Y GASTOS GENERALES: DE DÓNDE ENTRAN AL ER Y CÓMO QUEDAN REPARTIDOS EN CtaMens — FCST 2027 (USD, importes del mes)", 'TIT')])
    fila([T(0, "Misma regla que Integración2026_Dim_10: cada importe mensual de la hoja CAT (Cebe × territorio) se reparte entre los renglones de prima (B=61) de CtaMens de ese Cebe, territorio y mes, en proporción a su MONTO. Gastos: por mes, entre todos los renglones de prima.", 'SUB')])
    fila([T(0, "Toda cifra de esta hoja es fórmula sobre ER, CAT, Gastos y CtaMens.", 'SUB')])
    fila([T(0, "Mes (CALMONTH)", 'TXT_B')] + [N(C1+j, MESES[j], 'MES') for j in range(12)]
         + [N(C2+j, MESES[j], 'MES') for j in range(12)] + [N(C3+j, MESES[j], 'MES') for j in range(12)])
    r += 1
    def hdr(extra=None):
        cs = [T(0, "Concepto", 'HDR'), T(1, "Fuente", 'HDR')] + [T(C1+j, NOMMES[j], 'HDR_C') for j in range(12)]
        if extra: cs += extra
        fila(cs)
    # ---------- 1) donde entra hoy el CAT al ER
    barra("1) EL ER TOMA EL CAT Y LOS GASTOS DIRECTO DE LAS HOJAS CAT Y Gastos, NO DE CtaMens", 14)
    hdr([T(14, "¿Cuadra?", 'HDR_C')])
    def bloque1(lineas, resto_txt):
        r0 = r
        for i, (con, fue, gen, st) in enumerate(lineas):
            fila([T(0, con, 'TXT' if st == 'NUM' else 'LBL_G'), T(1, fue, 'OBS')] + [FN(C1+j, gen(j), st) for j in range(12)])
        cs = [T(0, resto_txt, 'LBL_Y'), T(1, "Debe dar 0 en todos los meses", 'LBL_Y')]
        for j in range(12):
            g = W.ref(r0, C1+j, crel=True, rrel=True)
            for k in range(1, len(lineas)): g += W.ref(r0+k, C1+j, crel=True, rrel=True) + W.SUB
            cs.append(FN(C1+j, g, 'NUM_Y'))
        cs.append(FB(14, cuadra(r, C1, C1+11), 'BOOL'))
        fila(cs); fila([])
    bloque1([("Siniestros tomados en ER (fila 13)", "ER!F13:Q13, importe del mes", lambda j: er_mes(13, j), 'NUM_G'),
             ("Siniestros de la base", "SUMIFS(CtaMens!Q; B=54; mes)", lambda j: sumifs(16, [(1, W.num(54)), (0, mes(C1+j))]), 'NUM'),
             ("CAT attritional bruto", "CAT!H27:S27", lambda j: cat(27, j), 'NUM'),
             ("Eventos CAT × xEvCat", "CAT!H83:S83", lambda j: cat(83, j), 'NUM')],
            "ER − base − CAT")
    bloque1([("Siniestros recuperados en ER (fila 24)", "ER!F24:Q24, importe del mes", lambda j: er_mes(24, j), 'NUM_G'),
             ("Recuperados de la base", "SUMIFS(CtaMens!W; B=54; mes)", lambda j: sumifs(22, [(1, W.num(54)), (0, mes(C1+j))]), 'NUM'),
             ("CAT cedido (attritional)", "CAT!H41:S41", lambda j: cat(41, j), 'NUM'),
             ("Recuperación eventos × xEvCat", "CAT!H84:S84", lambda j: cat(84, j), 'NUM')],
            "ER − base − CAT")
    bloque1([("Gastos Generales en ER (fila 46)", "ER!F46:Q46, importe del mes", lambda j: er_mes(46, j), 'NUM_G'),
             ("Gastos Generales", "Gastos!C12:N12", lambda j: W.ref3d(IX['Gastos'], 11, 2+j), 'NUM')],
            "ER − Gastos")
    # ---------- 2) repartido en CtaMens
    barra("2) EL MISMO IMPORTE, AHORA REPARTIDO EN LOS RENGLONES DE CtaMens (lo que leen las vistas ER_ram, ER_ln, ER_reg, ER_tre)", 14)
    hdr([T(14, "¿Cuadra?", 'HDR_C')])
    def bloque2(con, fue, gen_ct, fue2, gen_ref):
        r0 = r
        fila([T(0, con, 'TXT'), T(1, fue, 'OBS')] + [FN(C1+j, gen_ct(j), 'NUM') for j in range(12)])
        fila([T(0, "Importe de origen", 'LBL_G'), T(1, fue2, 'OBS')] + [FN(C1+j, gen_ref(j), 'NUM_G') for j in range(12)])
        fila([T(0, "Diferencia", 'LBL_Y'), T(1, "CtaMens − origen", 'LBL_Y')]
             + [FN(C1+j, W.ref(r0, C1+j, crel=True, rrel=True) + W.ref(r0+1, C1+j, crel=True, rrel=True) + W.SUB, 'NUM_Y') for j in range(12)]
             + [FB(14, cuadra(r0+2, C1, C1+11), 'BOOL')])
        fila([])
    bloque2("CtaMens!AD  AttritionalCat", "SUMIFS(CtaMens!AD; mes)", lambda j: sumifs(29, [(0, mes(C1+j))]), "CAT!H27:S27", lambda j: cat(27, j))
    bloque2("CtaMens!AE  SiniestrosCatCedidos", "SUMIFS(CtaMens!AE; mes)", lambda j: sumifs(30, [(0, mes(C1+j))]), "CAT!H41:S41", lambda j: cat(41, j))
    bloque2("CtaMens!AC  EventosCat (entra × xEvCat)", "SUMIFS(CtaMens!AC; mes)", lambda j: sumifs(28, [(0, mes(C1+j))]), "CAT!H68:S68", lambda j: cat(68, j))
    bloque2("CtaMens!AF  GastosGenerales", "SUMIFS(CtaMens!AF; B=61; mes)", lambda j: sumifs(31, [(1, W.num(61)), (0, mes(C1+j))]), "Gastos!C12:N12", lambda j: W.ref3d(IX['Gastos'], 11, 2+j))
    # ---------- 3) y 4) por Cebe x territorio
    def bloque_ct(titulo, r1, r2, scol, nombre_col):
        barra(titulo, QC)
        fila([T(0, "Cebe", 'HDR'), T(1, "Territorio", 'HDR')] + [T(C1+j, NOMMES[j], 'HDR_C') for j in range(12)]
             + [T(C2+j, NOMMES[j], 'HDR_C') for j in range(12)] + [T(C3+j, NOMMES[j], 'HDR_C') for j in range(12)] + [T(QC, "¿Cuadra?", 'HDR_C')])
        fila([T(0, "", 'SUB'), T(1, "", 'SUB'), T(C1, "Hoja CAT", 'TXT_B'), T(C2, f"CtaMens!{nombre_col} (SUMIFS por Cebe, territorio y mes)", 'TXT_B'),
              T(C3, "Diferencia (CtaMens − CAT)", 'TXT_B')])
        for rc in range(r1, r2+1):
            rr = r
            cs = [FS(0, W.ref3d(IX['CAT'], rc-1, 2), 'TXT'), FS(1, W.ref3d(IX['CAT'], rc-1, 4), 'TXT')]
            cs += [FN(C1+j, cat(rc, j), 'NUM') for j in range(12)]
            cs += [FN(C2+j, sumifs(scol, [(3, W.ref(rr, 0, rrel=True)), (4, W.ref(rr, 1, rrel=True)), (0, mes(C2+j))]), 'NUM') for j in range(12)]
            cs += [FN(C3+j, W.ref(rr, C2+j, crel=True, rrel=True) + W.ref(rr, C1+j, crel=True, rrel=True) + W.SUB, 'NUM_Y') for j in range(12)]
            cs.append(FB(QC, cuadra(rr, C3, C3+11), 'BOOL'))
            fila(cs)
        cebes = []
        for rc in range(r1, r2+1):
            ce = CATV.get((rc-1, 2))
            if ce and ce not in [c for c, _, _ in cebes]: cebes.append((ce, rc, rc))
            elif ce: cebes = [(c, a, (rc if c == ce else b)) for c, a, b in cebes]
        for ce, a, b in cebes:
            rr = r
            cs = [T(0, ce, 'LBL_B'), T(1, "Total del Cebe", 'LBL_B')]
            cs += [FN(C1+j, W.area3d(IX['CAT'], a-1, b-1, 7+j, 7+j) + W.funcvar(1, W.IF_SUM), 'NUM_B') for j in range(12)]
            cs += [FN(C2+j, sumifs(scol, [(3, W.ref(rr, 0, rrel=True)), (0, mes(C2+j))]), 'NUM_B') for j in range(12)]
            cs += [FN(C3+j, W.ref(rr, C2+j, crel=True, rrel=True) + W.ref(rr, C1+j, crel=True, rrel=True) + W.SUB, 'NUM_Y') for j in range(12)]
            cs.append(FB(QC, cuadra(rr, C3, C3+11), 'BOOL'))
            fila(cs)
        fila([T(0, "Una fila de territorio en FALSO solo puede venir de los casos sin prima en el mes (sección 5): ese importe va a otros territorios del mismo Cebe y mes. Los totales por Cebe cuadran todos los meses.", 'NOTA')])
        fila([])
    bloque_ct("3) ATTRITIONAL CAT POR CEBE × TERRITORIO: hoja CAT (filas 14 a 25) contra CtaMens!AD", 14, 25, 29, 'AD')
    bloque_ct("4) EVENTOS CAT POR CEBE × TERRITORIO: hoja CAT (filas 49 a 66) contra CtaMens!AC", 49, 66, 28, 'AC')
    # ---------- 5) casos sin prima
    barra("5) CASOS EN QUE LA HOJA CAT TRAE IMPORTE PERO CtaMens NO TIENE PRIMA DE ESE CEBE Y TERRITORIO EN EL MES", 8)
    fila([T(0, "Bloque", 'HDR'), T(1, "Cebe · territorio", 'HDR'), T(2, "Mes", 'HDR_C'), T(3, "Importe (hoja CAT)", 'HDR_C'), T(4, "Se repartió en", 'HDR')])
    for x in RESP:
        j = MESES.index(x['mes'])
        fila([T(0, f"{'Attritional' if x['bloque']=='attritional' else 'Eventos'} (CAT fila {x['fila_cat']})", 'TXT'),
              T(1, f"{x['cebe']} · {x['territorio']}", 'TXT'), N(2, x['mes'], 'MES'), FN(3, cat(x['fila_cat'], j), 'NUM'),
              T(4, "mismo Cebe y mes, territorios " + ", ".join(x['repartido_en']) + " (misma clase de cesión), en proporción a la prima", 'OBS')])
    fila([T(0, "En Integración2026_Dim_10 no hay casos así: sus 144 importes de attritional y 216 de eventos tienen prima en su mes. Aquí se conserva el mes, el Cebe y el % de cesión; solo cambia la región a la que se atribuye.", 'NOTA')])
    fila([])
    # ---------- 6) evidencia de la regla
    barra("6) LA REGLA, COMPROBADA EN Integración2026_Dim_10 (cifras de ese archivo)", 8)
    fila([T(0, "Columna de CtaMens", 'HDR'), T(1, "Contra", 'HDR'), T(2, "Suma en su CtaMens", 'HDR_C'), T(3, "Importe de su hoja", 'HDR_C'), T(4, "Al reaplicar la regla a sus 293,186 renglones", 'HDR')])
    for a, b, v1, v2, t in [("AD AttritionalCat", "CAT!T27", 47000529.41, 47000530.11, "diferencia máxima 0.05 por renglón (su CtaMens se generó con 0.70 menos que su hoja CAT)"),
                            ("AE SiniestrosCatCedidos", "CAT!T41", 21423365.37, 21423365.54, "AE = AD × %cesión (0.25 Ultramar, 0.86 Terremoto, 0.30 Hidro), exacto por renglón"),
                            ("AC EventosCat", "CAT!T68", 45000000.00, 45000000.00, "exacto en todos los renglones"),
                            ("AF GastosGenerales", "Gastos!C12:N12", 36275790.11, 36275790.11, "exacto en todos los renglones")]:
        fila([T(0, a, 'TXT'), T(1, b, 'TXT'), N(2, v1, 'NUM'), N(3, v2, 'NUM'), T(4, t, 'OBS')])
    fila([])
    # ---------- 7) efecto
    barra("7) RESULTADO EN Val_Resumen (diferencia de diciembre, vistas contra ER)", 8)
    fila([T(0, "Renglón", 'HDR'), T(1, "", 'HDR'), T(2, "Ramo", 'HDR_C'), T(3, "Línea de negocio", 'HDR_C'), T(4, "Región", 'HDR_C'), T(5, "Tipo de reaseguro", 'HDR_C')])
    for fr, nom in [(13, "17 · Siniestros Ocurridos"), (16, "20 · Resultado técnico total"), (18, "24 · Siniestros Netos Ocurridos"),
                    (22, "28 · Resultado técnico a retención"), (23, "31 · Gastos Generales"), (25, "33 · Total costos de operación"), (26, "35 · Resultado de operación")]:
        fila([T(0, nom, 'TXT'), T(1, f"Val_Resumen fila {fr}", 'OBS')] + [FN(2+k, W.ref3d(IX['Val_Resumen'], fr-1, c), 'NUM_Y') for k, c in enumerate((3, 7, 11, 15))])
    cols = [(0,0,40),(1,1,34)] + [(C1+j, C1+j, 12.5) for j in range(12)] + [(14,14,10)] + [(C2+j, C2+j, 12.5) for j in range(12)] + [(27,27,1.5)] + [(C3+j, C3+j, 12.5) for j in range(12)] + [(QC, QC, 10)]
    return W.sheet_bin(rows, QC+1, cols=cols, freeze=(2, 4))

# ======================================================= empaquetado
def empaquetar(src, dst, partes, borrar):
    shutil.copyfile(src, dst)
    if borrar:
        r = subprocess.run(['zip', '-d', '-q', os.path.abspath(dst)] + borrar, capture_output=True, text=True)
        if r.returncode: raise RuntimeError(r.stderr)
    with tempfile.TemporaryDirectory() as td:
        for nombre, data in partes.items():
            p = os.path.join(td, nombre); os.makedirs(os.path.dirname(p), exist_ok=True); open(p,'wb').write(data)
        r = subprocess.run(['zip', '-X', '-D', '-q', os.path.abspath(dst)] + list(partes), cwd=td, capture_output=True, text=True)
        if r.returncode: raise RuntimeError(r.stderr)

def fase_a():
    global P
    z = zipfile.ZipFile(SRC); SM = {n:p for n,p in sheet_map(SRC)}
    import empaquetar2 as E2
    P = W.Cadenas(E2.leer_sst(SRC))
    partes = {}
    # CtaMens
    cm, n_rep, sub = reescribir_ctamens(z.read(SM['CtaMens']))
    partes[SM['CtaMens']] = cm
    rels_cm = SM['CtaMens'].replace('worksheets/', 'worksheets/_rels/') + '.rels'
    rtxt = z.read(rels_cm).decode('utf-8')
    rtxt2 = re.sub(r'<Relationship [^>]*xlBinaryIndex[^>]*/>', '', rtxt); assert rtxt2 != rtxt
    partes[rels_cm] = rtxt2.encode('utf-8')
    bidx = 'xl/worksheets/binaryIndex23.bin'; assert bidx in z.namelist()
    # hoja nueva
    val_cat = hoja_val_cat()
    usados = {int(m) for m in re.findall(r'worksheets/sheet(\d+)\.bin', ' '.join(z.namelist()))}
    parte_nueva = f'xl/worksheets/sheet{max(usados)+1}.bin'
    wb = z.read('xl/workbook.bin'); rels = z.read('xl/_rels/workbook.bin.rels').decode('utf-8'); cts = z.read('[Content_Types].xml').decode('utf-8')
    _n = max(int(m) for m in re.findall(r'Id="rId(\d+)"', rels)) + 1
    rid_nuevo = 'rId%d' % _n
    max_tab = max(struct.unpack_from('<I', pl, 4)[0] for rid, pl in records(wb) if rid == 156)
    out = bytearray()
    for rid, pl, raw in records_raw(wb):
        if rid == 144:
            out += W.rec(156, struct.pack('<II', 0, max_tab+1) + W.wstr(rid_nuevo) + W.wstr('Val_CAT'))
        if rid == 362:
            (cn,) = struct.unpack_from('<I', pl, 0); assert cn == 68, cn
            cuerpo = pl[4:4+12*cn] + b''.join(struct.pack('<Iii', *x) for x in XTI_EXTRA)
            out += W.rec(362, struct.pack('<I', cn + len(XTI_EXTRA)) + cuerpo); continue
        if rid == 157:
            (fl,) = struct.unpack_from('<H', pl, len(pl)-2)
            out += W.rec(157, pl[:-2] + struct.pack('<H', fl | 0x0001)); continue      # fFullCalcOnLoad
        out += raw
    partes['xl/workbook.bin'] = bytes(out)
    rels = rels.replace('</Relationships>', f'<Relationship Id="{rid_nuevo}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{parte_nueva.replace("xl/","")}"/></Relationships>')
    partes['xl/_rels/workbook.bin.rels'] = rels.encode('utf-8')
    cts2 = re.sub(r'<Override PartName="/xl/worksheets/binaryIndex23\.bin"[^>]*/>', '', cts); assert cts2 != cts
    cts2 = cts2.replace('</Types>', f'<Override PartName="/{parte_nueva}" ContentType="application/vnd.ms-excel.worksheet"/></Types>')
    partes['[Content_Types].xml'] = cts2.encode('utf-8')
    o = bytearray()
    for rid, pl, raw in records_raw(z.read('xl/sharedStrings.bin')):
        if rid == 159:
            tot, uni = struct.unpack_from('<II', pl, 0)
            o += W.rec(159, struct.pack('<II', tot + len(P.nuevas), uni + len(P.nuevas)) + pl[8:]); continue
        if rid == 160:
            for s in P.nuevas: o += W.rec(19, b'\x00' + W.wstr(s))
        o += raw
    partes['xl/sharedStrings.bin'] = bytes(o)
    partes[parte_nueva] = val_cat
    z.close()
    empaquetar(SRC, TMP, partes, [bidx])
    return dict(n_rep=n_rep, sub=sub, parte_nueva=parte_nueva, cadenas=len(P.nuevas))

# ======================================================= fase B: valores guardados
def fase_b():
    N0 = pickle.load(open('nuestro_ctamens_limpio.pkl','rb'))
    df = N0[['_fila','A','B','C','D','E','L','Q','R','W']].copy()
    for c in ['Q','W','L']: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    for c in ['C','D','E','R']: df[c] = df[c].astype(str)
    for c in ['AA','AB']: df[c] = 0.0
    for c, col in (('AC',28),('AD',29),('AE',30),('AF',31)):
        df[c] = df['_fila'].map(lambda f, col=col: FILAS.get(f, {}).get(col, 0.0))
    base = EV.Base(df)
    hojas = EV.Hojas(TMP, ['ER','CAT','Gastos','Inicio','Parámetros','2_Reservas','ER_ram','ER_ln','ER_reg','ER_tre'])
    ctx = fmla.Ctx(TMP); S = dump.sst(TMP); SM = {n:p for n,p in sheet_map(TMP)}
    CEL = {}; FORM = {}
    for h in H_VAL:
        CEL[h] = {}; FORM[h] = {}
        for r,c,v,f in dump.cells(TMP, SM[h], ctx, S):
            if f: FORM[h][(r,c)] = f; CEL[h][(r,c)] = (None, f)
            else: CEL[h][(r,c)] = (v, None)
    malas = [(h, colrow(*k), f) for h in H_VAL for k, f in FORM[h].items() if any(t in f for t in ('<?','FUNC','#REF','SINGLE'))]
    if malas: raise RuntimeError(f'formulas mal decodificadas: {malas[:4]}')
    ev = EV.Evaluador(base, hojas, CEL)
    for it in range(80):
        cambios = 0
        for h in H_VAL:
            for k, f in FORM[h].items():
                m = re.fullmatch(r"'?([^'!]+)'?!(\$?[A-Z]+\$?\d+)", f)
                try:
                    if m:
                        v = ev.r3(m.group(1), m.group(2))
                        if v is None: v = 0.0          # celda vacia = 0, como en Excel
                    else:
                        v = ev.evaluar(h, f)
                except (ValueError, TypeError):
                    v = None
                if isinstance(v, int) and not isinstance(v, bool): v = float(v)
                old = CEL[h][k][0]
                if not (old == v or (isinstance(old,float) and isinstance(v,float) and abs(old-v) < 1e-9)): cambios += 1
                CEL[h][k] = (v, f)
        if cambios == 0: break
    pend = [(h, colrow(*k), FORM[h][k][:80]) for h in H_VAL for k in FORM[h] if CEL[h][k][0] is None]
    if pend: raise RuntimeError(f'{len(pend)} formulas sin valor: {pend[:4]}')
    norm = lambda v: 0.0 if (isinstance(v, float) and v == 0.0) else v
    valores = {h: {k: norm(CEL[h][k][0]) for k in FORM[h]} for h in H_VAL}
    # escribir
    z = zipfile.ZipFile(TMP); partes = {}
    for h in H_VAL:
        out = bytearray(); row = 0
        for rid, pl, raw in records_raw(z.read(SM[h])):
            if rid == 0: (row,) = struct.unpack_from('<I', pl, 0)
            if rid in (8,9,10,11):
                (col,) = struct.unpack_from('<I', pl, 0); v = valores[h].get((row, col))
                hdr, grbit, tail = partir(rid, pl)
                if isinstance(v, bool): nrid, val = 10, bytes([1 if v else 0])
                elif isinstance(v, float): nrid, val = 9, struct.pack('<d', v)
                elif isinstance(v, str): nrid, val = 8, W.wstr(v)
                else: raise TypeError((h, row, col, v))
                out += W.rec(nrid, hdr + val + grbit + tail); continue
            out += raw
        partes[SM[h]] = bytes(out)
    z.close()
    empaquetar(TMP, DST, partes, [])
    pickle.dump(dict(CEL=CEL, FORM=FORM), open('aplicado.pkl','wb'))
    return it + 1, sum(len(FORM[h]) for h in H_VAL)

if __name__ == '__main__':
    a = fase_a(); print('fase A:', a)
    n, nf = fase_b(); print(f'fase B: {nf} formulas recalculadas en {n} pasadas')
    os.remove(TMP)
