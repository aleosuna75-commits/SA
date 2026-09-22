# -*- coding: utf-8 -*-
"""ER vs vistas de ER: siete hojas con formulas referenciadas, insertadas en el libro original."""
import pickle, zipfile, struct
import xlsbw as W, empaquetar2 as E, estilos, fmla, dump
from biff import colrow, sheet_map

SRC, DST = 'FCST.xlsb', 'FCST_2027_Cesion.xlsb'
M = pickle.load(open('motor.pkl','rb'))
OUT, ERL, LINEAS, NOMBRE, ER_MAP, ER_NOM, MESES = (M[k] for k in ('OUT','ERL','LINEAS','NOMBRE','ER_MAP','ER_NOM','MESES'))
VD = pickle.load(open('valdim.pkl','rb'))
NM = 12; NOMMES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
F0, F1 = 3, 201233                     # CtaMens filas 4..201234 (0-based)

# ---- ixti ----
IX = dict(CtaMens=3, Param=4, ER_ln=6, ER_reg=7, ER_tre=8, Inicio=11, Gastos=14, CAT=15, ER_ram=28, Res=55, ER=56,
          ValDim=63, Val_Resumen=64, Val_Ramo=65, Val_LN=66, Val_Region=67, Val_TRea=68, Val_Origen=69, Val_ValDim=70)
XTI_EXTRA = [(0,12,12)] + [(0,t,t) for t in range(28,35)]
IX_HOJA = {'RAMO':IX['Val_Ramo'], 'LN':IX['Val_LN'], 'REGION':IX['Val_Region'], 'TREA':IX['Val_TRea']}
NOM_HOJA = {'RAMO':'Val_Ramo', 'LN':'Val_LN', 'REGION':'Val_Region', 'TREA':'Val_TRea'}
NOM_DIM = {'RAMO':'Ramo', 'LN':'Línea de Negocio', 'REGION':'Región', 'TREA':'Tipo de Reaseguro'}
COLD = {'RAMO':17, 'LN':2, 'REGION':4, 'TREA':11}       # columna criterio en CtaMens (0-based)
COLD_L = {'RAMO':'R', 'LN':'C', 'REGION':'E', 'TREA':'L'}
IX_VISTA = {'RAMO':IX['ER_ram'], 'LN':IX['ER_ln'], 'REGION':IX['ER_reg'], 'TREA':IX['ER_tre']}
NAME_XEVCAT = 92
CA, CB, CC, CD, CP, CQ = 0, 1, 2, 3, 15, 16            # columnas de la hoja

# ---- estilos ----
z = zipfile.ZipFile(SRC)
STYLES_NEW, X = estilos.paleta(z.read('xl/styles.bin'))
P = W.Cadenas(E.leer_sst(SRC))
def T(c, s, st):  return W.c_isst(c, P.add(s), st)
def N(c, v, st):  return W.c_num(c, v, st)
def B(c, st):     return W.c_blank(c, st)
def FN(c, v, g, st): return W.c_fmla_num(c, v, g, st)
def FS(c, v, g, st): return W.c_fmla_str(c, v, g, st)
def FB(c, v, g, st): return W.c_fmla_bool(c, v, g, st)

# ---- piezas de formula ----
def A3(col): return W.area3d(IX['CtaMens'], F0, F1, col, col)
def mesref(j): return W.ref(3, CD+j, crel=True)                    # D$4
def memref(r): return W.ref(r, CA, rrel=True)                      # $A{r}
def fx(dim, j): return W.ref3d(IX_VISTA[dim], 5, 4+j)              # ER_x!$E$6..$P$6
def sif(sumcol, cta, dim, r, j):
    return A3(sumcol) + A3(1) + W.num(cta) + A3(0) + mesref(j) + A3(COLD[dim]) + memref(r) + W.funcvar(7, W.IF_SUMIFS)
def sifn(sumcol, dim, r, j):
    return A3(sumcol) + A3(0) + mesref(j) + A3(COLD[dim]) + memref(r) + W.funcvar(5, W.IF_SUMIFS)
def prev(r, j): return (W.ref(r, CD+j-1, crel=True, rrel=True) + W.ADD) if j > 0 else b''
def celda(r, j): return W.ref(r, CD+j, crel=True, rrel=True)
def reserva(dim, filas, j):
    refs = [W.ref3d(IX['Res'], f, 22+j) for f in filas if f is not None]
    if len(refs) == 1: return refs[0]
    return refs[0] + refs[1] + W.ADD + W.PAREN
Q, Wc, AA, AB, AC, AD, AE, AF = 16, 22, 26, 27, 28, 29, 30, 31

def formula_linea(dim, ln, r, j, pos, filas_res):
    """rgce de la celda (fila r, mes j) para la linea ln; pos[ln] = fila del miembro en ese bloque."""
    xev = W.name(NAME_XEVCAT)
    if ln == 9:  return sif(Q,61,dim,r,j) + W.UMINUS + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 10: return sif(Wc,61,dim,r,j) + W.UMINUS + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 11: return celda(pos[9],j) + celda(pos[10],j) + W.SUB
    if ln in (12,13,18,25):
        if all(f is None for f in filas_res[ln]): return None
        return reserva(dim, filas_res[ln], j) + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 16: return celda(pos[9],j) + celda(pos[12],j) + W.SUB
    if ln == 17:
        return (sif(Q,54,dim,r,j) + sifn(AC,dim,r,j) + xev + W.MUL + W.ADD + sifn(AD,dim,r,j) + W.ADD + W.PAREN
                + fx(dim,j) + W.MUL + prev(r,j))
    if ln == 19: return sif(Q,53,dim,r,j) + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 20: return celda(pos[16],j) + celda(pos[17],j) + celda(pos[18],j) + W.ADD + celda(pos[19],j) + W.ADD + W.PAREN + W.SUB
    if ln == 23: return celda(pos[11],j) + celda(pos[13],j) + W.SUB
    if ln == 24:
        bruto = sif(Q,54,dim,r,j) + sifn(AC,dim,r,j) + xev + W.MUL + W.ADD + sifn(AD,dim,r,j) + W.ADD + W.PAREN
        cedido = sif(Wc,54,dim,r,j) + sifn(AE,dim,r,j) + W.ADD + sifn(AB,dim,r,j) + xev + W.MUL + W.PAREN + W.SUB + W.PAREN
        return bruto + cedido + W.SUB + W.PAREN + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 26: return sif(Q,53,dim,r,j) + sif(Wc,53,dim,r,j) + W.SUB + W.PAREN + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 27: return sif(AA,61,dim,r,j) + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 28: return (celda(pos[23],j) + celda(pos[24],j) + celda(pos[25],j) + W.ADD + celda(pos[26],j) + W.ADD
                         + celda(pos[27],j) + W.ADD + W.PAREN + W.SUB)
    if ln == 31: return sif(AF,61,dim,r,j) + fx(dim,j) + W.MUL + prev(r,j)
    if ln == 32: return celda(pos[10],j) + W.ref3d(IX['Param'], 9, 5+j) + W.MUL
    if ln == 33: return celda(pos[31],j) + celda(pos[32],j) + W.SUB
    if ln == 35: return celda(pos[28],j) + celda(pos[33],j) + W.SUB
    raise ValueError(ln)

def er_formula(ln, j):
    g = b''
    for k, (f, sg) in enumerate(ER_MAP[ln]):
        g += W.ref3d(IX['ER'], f-1, 5+j)
        if k: g += W.ADD if sg > 0 else W.SUB
    return g
def er_desc(ln):
    return ' − '.join(f"fila {f} · {ER_NOM[f]}" for f, _ in ER_MAP[ln]) if len(ER_MAP[ln]) > 1 else f"fila {ER_MAP[ln][0][0]} · {ER_NOM[ER_MAP[ln][0][0]]}"
def er_ref_txt(ln):
    return ' − '.join(f"ER!{colrow(f-1,5)[:-len(str(f))] if False else ''}F${f}:Q${f}" for f, _ in ER_MAP[ln])

def obs_linea(dim, ln, mb, info, filas_res, pos):
    n = info['n_ctamens']; L = COLD_L[dim]
    def cta(): return (f"Misma fórmula de la vista, con CtaMens!{L} = {mb!r} ({n:,} renglones)" if n
                       else f"Misma fórmula de la vista; CtaMens no tiene renglones con {L} = {mb!r} → 0")
    if ln in (9,10,17,19,24,26,27,31): return cta()
    if ln in (12,13,18,25):
        fr = [f for f in filas_res[ln] if f is not None]
        if not fr: return "No está en la tabla de 2_Reservas de esta dimensión (la vista daría #N/A) → se deja vacío"
        return "2_Reservas " + " + ".join(f"fila {f+1} (W:AH)" for f in fr) + " × tipo de cambio de la vista, acumulado"
    ref = {11:"= fila 9 − fila 10", 16:"= fila 9 − fila 12", 20:"= fila 16 − (17 + 18 + 19)", 23:"= fila 11 − fila 13",
           28:"= fila 23 − (24 + 25 + 26 + 27)", 32:"= fila 10 × 'Parámetros'!F10:Q10 (% contribución)",
           33:"= fila 31 − fila 32", 35:"= fila 28 − fila 33"}[ln]
    return ref + "  (de este mismo miembro, en esta hoja)"

# ================= hojas por dimension =================
HOJAS = {}; POS = {}; ANC = {}
for dim in ('RAMO','LN','REGION','TREA'):
    D = OUT[dim]; vista = D['vista']; miembros = D['miembros']; nombre = NOM_DIM[dim]
    rows = {}; pos = {ln:{} for ln in LINEAS}; anc = {}
    rows[0] = [T(CA, f"ER vs VISTA {vista.upper()} — PRESUPUESTO 2027 POR {nombre.upper()}  (USD, acumulado por mes)", X['TIT'])]
    rows[1] = [T(CA, f"Cada renglón de {vista} evaluado con su propia fórmula para cada {nombre.lower()} "
                     f"(como si el selector A6 se pusiera en cada miembro). La suma de los miembros se compara contra el renglón equivalente de ER.", X['SUB'])]
    sel = {'RAMO':'Vida','LN':'LN04001','REGION':'R06','TREA':3.0}[dim]
    rows[2] = [T(CA, "Selector actual de la vista", X['TXT_B']),
               (FN(CB, sel, W.ref3d(IX_VISTA[dim], 5, 0), X['SUB']) if isinstance(sel, float) else FS(CB, sel, W.ref3d(IX_VISTA[dim], 5, 0), X['SUB'])),
               T(CD, f"← {vista}!A6. Ese miembro es el único que hoy se ve en la vista; sus cifras aquí son idénticas a las de la vista.", X['NOTA'])]
    rows[3] = [T(CA, "Mes (CALMONTH)", X['TXT_B'])] + [N(CD+j, MESES[j], X['MES']) for j in range(NM)]
    r = 5
    for ln in LINEAS:
        r0 = r
        bar = [T(CA, f"{ln} · {NOMBRE[ln]}", X['BAR']),
               T(CB, f"Vista {vista}, fila {ln}  (selector A6 = cada miembro)   ↔   ER {er_desc(ln)}", X['BAR']),
               B(CC, X['BAR']), B(CP, X['BAR']), T(CQ, "", X['BAR'])]
        bar += [B(CD+j, X['BAR']) for j in range(NM)]
        rows[r0] = bar
        hdr = [T(CA, "Miembro", X['HDR']), T(CB, "Cómo se obtiene la cifra", X['HDR']), T(CQ, "¿Cuadra dic.?", X['HDR_C'])]
        hdr += [T(CD+j, NOMMES[j], X['HDR_C']) for j in range(NM)]
        rows[r0+1] = hdr
        r = r0 + 2; r_m0 = r
        for mb in miembros:
            info = D['res'][mb]; pos[ln][mb] = r
            vals = info['lineas'][ln]; fr = info['filas_reserva']
            cs = [N(CA, mb, X['TXT']) if isinstance(mb, float) else T(CA, str(mb), X['TXT']),
                  T(CB, obs_linea(dim, ln, mb, info, fr, {k: pos[k].get(mb) for k in LINEAS}), X['OBS'])]
            pm = {k: pos[k].get(mb) for k in LINEAS}
            for j in range(NM):
                g = formula_linea(dim, ln, r, j, pm, fr)
                if g is None: cs.append(B(CD+j, X['NUM'])); continue
                cs.append(FN(CD+j, vals[j] if vals is not None else 0.0, g, X['NUM']))
            rows[r] = cs; r += 1
        r_sum, r_er, r_dif = r, r+1, r+2
        suma = [sum((D['res'][mb]['lineas'][ln] or [0]*NM)[j] for mb in miembros) for j in range(NM)]
        cs = [T(CA, "Suma de los miembros", X['LBL_B']), T(CB, f"= SUM de las {len(miembros)} filas de arriba", X['LBL_B'])]
        cs += [FN(CD+j, suma[j], W.area(r_m0, r-1, CD+j, CD+j) + W.funcvar(1, W.IF_SUM), X['NUM_B']) for j in range(NM)]
        rows[r_sum] = cs
        cs = [T(CA, "ER (global)", X['LBL_G']), T(CB, "= " + er_ref_txt(ln) + "   " + er_desc(ln), X['LBL_G'])]
        cs += [FN(CD+j, ERL[ln][j], er_formula(ln, j), X['NUM_G']) for j in range(NM)]
        rows[r_er] = cs
        cs = [T(CA, "Diferencia (suma − ER)", X['LBL_Y']), T(CB, "Cero significa que la vista, sumada sobre todos sus miembros, reproduce ER.", X['LBL_Y'])]
        cs += [FN(CD+j, suma[j]-ERL[ln][j], celda(r_sum,j) + celda(r_er,j) + W.SUB, X['NUM_Y']) for j in range(NM)]
        cs.append(FB(CQ, abs(suma[11]-ERL[ln][11]) < 0.005,
                     W.ref(r_dif, CD+11, crel=True, rrel=True) + W.func_fix(24) + W.num(0.005) + W.LT, X['BOOL']))
        rows[r_dif] = cs
        anc[ln] = (r_sum, r_er, r_dif, suma[11])
        r = r_dif + 2
    HOJAS[dim] = W.sheet_bin(rows, CQ+1, cols=[(CA,CA,20),(CB,CB,62),(CC,CC,1.5),(CD,CD+11,15),(CP,CP,1.5),(CQ,CQ,13)], freeze=(2,4))
    POS[dim] = pos; ANC[dim] = anc

# ================= Val_Resumen =================
rows = {}
rows[0] = [T(0, "RESUMEN — ¿CUADRAN LAS VISTAS DE ER CONTRA ER?  Presupuesto 2027, diciembre acumulado (USD)", X['TIT'])]
rows[1] = [T(0, "Para cada renglón del estado de resultados: suma de todos los miembros de la vista (evaluada con la fórmula de la propia vista) contra el renglón equivalente de ER.", X['SUB'])]
rows[2] = [T(0, "Detalle mes a mes y miembro por miembro en Val_Ramo, Val_LN, Val_Region y Val_TRea. Fórmulas y fuentes de cada renglón en Val_Origen. Por qué ValDim muestra descuadres: Val_ValDim.", X['SUB'])]
DIMS = ['RAMO','LN','REGION','TREA']
g0 = 2
bar = [T(0, "Renglón de la vista", X['BAR']), T(1, "Renglón equivalente de ER", X['BAR'])]
hdr = [T(0, "", X['HDR']), T(1, "", X['HDR'])]
for k, dim in enumerate(DIMS):
    c = g0 + 4*k
    bar += [T(c, f"{NOM_DIM[dim].upper()}  ({OUT[dim]['vista']})", X['BAR_C']), B(c+1, X['BAR']), B(c+2, X['BAR']), B(c+3, X['BAR'])]
    hdr += [T(c, "Suma de miembros", X['HDR_C']), T(c+1, "ER", X['HDR_C']), T(c+2, "Diferencia", X['HDR_C']), T(c+3, "¿Cuadra?", X['HDR_C'])]
rows[4] = bar; rows[5] = hdr
r = 6; RESROW = {}
for ln in LINEAS:
    cs = [T(0, f"{ln} · {NOMBRE[ln]}", X['TXT']), T(1, er_desc(ln), X['OBS'])]
    for k, dim in enumerate(DIMS):
        c = g0 + 4*k; r_sum, r_er, r_dif, s11 = ANC[dim][ln]; ix = IX_HOJA[dim]
        cs += [FN(c,   s11,             W.ref3d(ix, r_sum, CD+11), X['NUM']),
               FN(c+1, ERL[ln][11],     W.ref3d(ix, r_er,  CD+11), X['NUM_G']),
               FN(c+2, s11-ERL[ln][11], W.ref3d(ix, r_dif, CD+11), X['NUM_Y']),
               FB(c+3, abs(s11-ERL[ln][11]) < 0.005, W.ref3d(ix, r_dif, CQ), X['BOOL'])]
    rows[r] = cs; RESROW[ln] = r; r += 1
r += 1
rows[r] = [T(0, "POR QUÉ NO CUADRAN LOS RENGLONES 17, 24 y 31 (y los resultados que los arrastran: 20, 28, 33 y 35)", X['BAR'])] + [B(c, X['BAR']) for c in range(1, g0+16)]
r += 1
rows[r] = [T(0, "Concepto", X['HDR']), T(1, "De dónde sale", X['HDR']), T(2, "Importe", X['HDR_C']), T(3, "Comprobación", X['HDR_C']), T(4, "¿Cero?", X['HDR_C'])]
r += 1
cat27 = W.area3d(IX['CAT'], 26, 26, 7, 18) + W.funcvar(1, W.IF_SUM) + W.area3d(IX['CAT'], 82, 82, 7, 18) + W.funcvar(1, W.IF_SUM) + W.ADD
cat41 = W.area3d(IX['CAT'], 40, 40, 7, 18) + W.funcvar(1, W.IF_SUM) + W.area3d(IX['CAT'], 83, 83, 7, 18) + W.funcvar(1, W.IF_SUM) + W.ADD
gas   = W.area3d(IX['Gastos'], 11, 11, 2, 13) + W.funcvar(1, W.IF_SUM)
V27, V41, VG = 41811767.85, 14392567.04, 38249042.87
d17 = ANC['RAMO'][17][3] - ERL[17][11]; d24 = ANC['RAMO'][24][3] - ERL[24][11]; d31 = ANC['RAMO'][31][3] - ERL[31][11]
ixr = IX['Val_Resumen']
def dref(ln, k=0): return W.ref3d(ixr, RESROW[ln], g0 + 4*k + 2)         # diferencia de esa linea (Ramo)
EXPL = [
 ("Eventos CAT brutos que ER suma en siniestros", "ER fila 13 agrega CAT!H27:S27 + CAT!H83:S83 cada mes; la vista solo toma lo que CtaMens reparte por miembro (columnas AC y AD, hoy en cero).",
  cat27, V27, dref(17) + W.ref(r+0, 2, rrel=True) + W.ADD, d17 + V27, "Diferencia fila 17 + este importe"),
 ("Recuperados CAT que ER resta en siniestros netos", "ER fila 24 agrega CAT!H41:S41 + CAT!H84:S84; la vista resta CtaMens!AE − AB×xEvCat, que viene en cero.",
  cat41, V41, dref(24) + W.ref(r+0, 2, rrel=True) + W.ADD + W.ref(r+1, 2, rrel=True) + W.SUB, d24 + V27 - V41, "Diferencia fila 24 + CAT brutos − CAT recuperados"),
 ("Gastos Generales que ER toma de la hoja Gastos", "ER fila 46 = Gastos!C12:N12; la vista fila 31 = CtaMens!AF, que viene en cero para todos los miembros.",
  gas, VG, dref(31) + W.ref(r+2, 2, rrel=True) + W.ADD, d31 + VG, "Diferencia fila 31 + este importe"),
]
for i, (con, de, g, v, gchk, vchk, txt) in enumerate(EXPL):
    rows[r] = [T(0, con, X['TXT']), T(1, de, X['OBS']), FN(2, v, g, X['NUM']),
               FN(3, vchk, gchk, X['NUM_Y']), FB(4, abs(vchk) < 0.005, W.ref(r, 3, rrel=True) + W.func_fix(24) + W.num(0.005) + W.LT, X['BOOL'])]
    r += 1
rows[r] = [T(0, "Los renglones 20, 28, 33 y 35 son resultados: solo arrastran las tres diferencias anteriores. Los otros 13 renglones cuadran a 0.00 en las cuatro dimensiones.", X['NOTA'])]
r += 2
rows[r] = [T(0, "Cómo leer: cada cifra es una fórmula. Las de 'Suma de miembros' apuntan a la hoja de su dimensión, donde cada miembro se calcula con la fórmula de la vista; las de 'ER' apuntan a la hoja ER.", X['NOTA'])]
HOJA_RES = W.sheet_bin(rows, g0+16, cols=[(0,0,44),(1,1,58)] + [(g0+4*k+i, g0+4*k+i, 17 if i<3 else 10) for k in range(4) for i in range(4)], freeze=(2,6))

# ================= Val_Origen =================
ctx = fmla.Ctx(SRC); S = dump.sst(SRC); SM = {n:p for n,p in sheet_map(SRC)}
FV = {}; FE = {}
for rr, cc, v, f in dump.cells(SRC, SM['ER_ram'], ctx, S):
    if cc == 15 and (rr+1) in LINEAS: FV[rr+1] = f or '(constante)'
for rr, cc, v, f in dump.cells(SRC, SM['ER'], ctx, S):
    if cc == 16 and (rr+1) in ER_NOM: FE[rr+1] = f or '(constante)'
rows = {}; r = 0
def linea(cs):
    global r; rows[r] = cs; r += 1
linea([T(0, "DE DÓNDE SALE CADA CIFRA QUE SE COMPARA", X['TIT'])])
linea([T(0, "Fórmulas tal como están en el libro (columna de diciembre). Las hojas Val_* replican la fórmula de la vista cambiando solo el selector A6 por cada miembro.", X['SUB'])])
r += 1
linea([T(0, "1) RENGLÓN POR RENGLÓN: VISTA ↔ ER", X['BAR'])] + [B(c, X['BAR']) for c in range(1,7)])
linea([T(0,"Fila vista",X['HDR_C']), T(1,"Concepto",X['HDR']), T(2,"Fórmula en la vista (ER_ram!P, las otras vistas cambian la columna del criterio)",X['HDR']),
       T(3,"Fila(s) ER",X['HDR_C']), T(4,"Fórmula en ER (columna Q)",X['HDR']), T(5,"¿Misma fuente?",X['HDR_C']), T(6,"Nota",X['HDR'])])
NOTA = {17:"ER agrega CAT!H27:S27 y H83:S83 (eventos CAT globales); la vista usa CtaMens!AC×xEvCat + AD, en cero.",
        24:"ER: siniestros tomados (con CAT) − recuperados (con CAT!H41:S41 + H84:S84) − no proporcional (AB×xEvCat). Vista: CtaMens!AE − AB×xEvCat, en cero.",
        31:"ER toma Gastos!C12:N12; la vista suma CtaMens!AF, en cero. Ojo: Gastos!C5:N5 rotula los meses como 202601..202612; conviene confirmar que la fila 12 es el presupuesto 2027.",
        20:"Arrastra la fila 17.", 28:"Arrastra la fila 24.", 33:"Arrastra la fila 31.", 35:"Arrastra 28 y 33.",
        12:"ER usa el TOTAL de la tabla por ramo (2_Reservas!W81:AH81); las vistas leen la fila del miembro en la tabla de su dimensión. Todas las tablas suman lo mismo.",
        13:"ER usa 2_Reservas!W100:AH100 (total).",
        18:"ER usa 2_Reservas!W118:AH118 (total). Ese total (fila 118 = SUM(104:116)) deja fuera la fila 117, Fianzas, que hoy está en cero.",
        25:"ER usa 2_Reservas!W136:AH136 (total). Igual que la 18: la fila 136 = SUM(122:134) deja fuera la 135, Fianzas, hoy en cero.",
        32:"La vista multiplica el acumulado por la tasa; ER acumula incrementos × tasa. Iguales mientras la tasa (0.048) no cambie de mes."}
MISMA = {ln: (ln not in (17,24,31,20,28,33,35)) for ln in LINEAS}
for ln in LINEAS:
    fe = ' ; '.join(f"Q{f}: {FE.get(f,'')}" for f,_ in ER_MAP[ln])
    linea([N(0, ln, X['TXT_C']), T(1, NOMBRE[ln], X['TXT']), T(2, FV.get(ln,''), X['OBS']),
           T(3, ' − '.join(f"fila {f}" for f,_ in ER_MAP[ln]), X['TXT_C']), T(4, fe, X['OBS']),
           T(5, "Sí" if MISMA[ln] else "NO", X['TXT_C']), T(6, NOTA.get(ln, ""), X['OBS'])])
r += 1
linea([T(0, "2) COLUMNAS DE CtaMens QUE USAN LAS FÓRMULAS  (encabezado en la fila 3; datos de la fila 4 a la 201,234)", X['BAR'])] + [B(c, X['BAR']) for c in range(1,7)])
linea([T(0,"Columna",X['HDR_C']), T(1,"Encabezado",X['HDR']), T(2,"Uso",X['HDR'])])
for col, enc, uso in [("A","CALMONTH / PERIODO","Mes 202701..202712 (criterio de mes)"),("B","GL_ACCT / TY","Familia de cuenta: 61 prima, 53 comisiones, 54 siniestros"),
    ("C","FUNCAREA","Línea de negocio — criterio de ER_ln"),("E","ZREGIONRP","Región — criterio de ER_reg"),("L","ZTIPOREAS","Tipo de reaseguro — criterio de ER_tre"),
    ("Q","AMOUNT / MONTO","Importe tomado"),("R","RamoN / RAMO","Ramo — criterio de ER_ram"),("W","CEDIDA","Importe cedido (prima retrocedida, siniestros recuperados, comisiones cedidas)"),
    ("AA","CostosXL","Costos de protecciones XL (en cero)"),("AB","Recuperaciones","Recuperaciones no proporcionales (en cero)"),("AC","EventosCat","Siniestros por eventos CAT (en cero)"),
    ("AD","AttritionalCat","Siniestros atricionales CAT (en cero)"),("AE","SiniestrosCatCedidos","Siniestros CAT cedidos (en cero)"),("AF","GastosGenerales","Gastos generales por renglón (en cero)")]:
    linea([T(0,col,X['TXT_C']), T(1,enc,X['TXT']), T(2,uso,X['OBS'])])
linea([T(0, "Las vistas usan columnas completas ($Q$1:$Q$1048576); las hojas Val_* usan $Q$4:$Q$201234, todo el rango con datos. El resultado es idéntico y el cálculo más ligero.", X['NOTA'])])
r += 1
linea([T(0, "3) TABLAS DE 2_Reservas QUE LEE CADA VISTA (llave en la columna U para ramo y V para las demás; meses en W:AH)", X['BAR'])] + [B(c, X['BAR']) for c in range(1,7)])
linea([T(0,"Vista",X['HDR']), T(1,"Fila 12 · Var. Rva s/Tomada",X['HDR']), T(2,"Fila 13 · Var. Rva s/Retenida",X['HDR']), T(3,"Fila 18 · IBNR",X['HDR']), T(4,"Fila 25 · IBNR neto",X['HDR'])])
def rng(bl): return ' + '.join(f"filas {a+1}:{b+1}" for a,b in bl)
for dim in DIMS:
    D = OUT[dim]
    linea([T(0, D['vista'], X['TXT']), T(1, rng(D['t12']), X['OBS']), T(2, rng(D['t13']), X['OBS']), T(3, rng(D['t18']), X['OBS']), T(4, rng(D['t25']), X['OBS'])])
linea([T(0, "ER (global)", X['TXT']), T(1, "fila 81 (total)", X['OBS']), T(2, "fila 100 (total)", X['OBS']), T(3, "fila 118 (total)", X['OBS']), T(4, "fila 136 (total)", X['OBS'])])
r += 1
linea([T(0, "4) MIEMBROS DE CADA DIMENSIÓN", X['BAR'])] + [B(c, X['BAR']) for c in range(1,7)])
linea([T(0,"Vista",X['HDR']), T(1,"Miembros (tabla de reservas + etiquetas de CtaMens)",X['HDR']), T(2,"Observación",X['HDR'])])
OBSM = {'RAMO':"'Crédito' (con acento) está en 2_Reservas y 'Credito' (sin acento) en CtaMens: son dos filas distintas. GMM y Crédito no tienen renglones en CtaMens pero sí reservas: hay que incluirlos para que la vista sume lo mismo que ER.",
        'LN':"'LN04008-Agro' está en CtaMens y en Valores!BB20, pero no en la tabla de reservas; 'LN04008' y 'LN04009' están en reservas y no tienen renglones en CtaMens.",
        'REGION':"Coinciden.", 'TREA':"Coinciden."}
for dim in DIMS:
    linea([T(0, OUT[dim]['vista'], X['TXT']), T(1, ', '.join(str(int(m)) if isinstance(m,float) else m for m in OUT[dim]['miembros']), X['OBS']), T(2, OBSM[dim], X['OBS'])])
r += 1
linea([T(0, "5) SELECTOR ACTUAL DE CADA VISTA (vivo)", X['BAR'])] + [B(c, X['BAR']) for c in range(1,7)])
linea([T(0,"Vista",X['HDR']), T(1,"Celda",X['HDR']), T(2,"Miembro seleccionado",X['HDR_C'])])
for dim, sel in [('RAMO','Vida'),('LN','LN04001'),('REGION','R06'),('TREA',3.0)]:
    cel = (FN(2, sel, W.ref3d(IX_VISTA[dim], 5, 0), X['TXT_C']) if isinstance(sel, float) else FS(2, sel, W.ref3d(IX_VISTA[dim], 5, 0), X['TXT_C']))
    linea([T(0, OUT[dim]['vista'], X['TXT']), T(1, f"{OUT[dim]['vista']}!A6", X['TXT']), cel])
r += 1
linea([T(0, "6) CÁLCULO", X['BAR'])] + [B(c, X['BAR']) for c in range(1,7)])
linea([T(0, "El libro está en cálculo manual. Las hojas Val_* se guardaron ya calculadas; al pulsar F9 se recalculan con las fórmulas que contienen. xEvCat = Inicio!C13 = 0 y el tipo de cambio de las vistas (E6:P6) es 1.00 en USD.", X['NOTA'])])
HOJA_ORIG = W.sheet_bin(rows, 7, cols=[(0,0,14),(1,1,48),(2,2,95),(3,3,12),(4,4,95),(5,5,14),(6,6,80)])

# ================= Val_ValDim =================
rows = {}; r = 0
linea([T(0, "POR QUÉ ValDim MUESTRA DESCUADRES: lo que ValDim trae capturado contra la vista evaluada para cada miembro (diciembre)", X['TIT'])])
linea([T(0, "En ValDim solo la primera fila de miembro de cada vista tiene fórmula (=ER_x!P$9 / P$19); las demás son valores pegados en otro momento. Y esa primera fila muestra el miembro que tenga el selector, no el de su rótulo.", X['SUB'])])
r += 1
BLQ = [('RAMO',1,14,'Ramo'),('LN',16,28,'Línea de Negocio'),('REGION',30,42,'Región'),('TREA',44,56,'Tipo de Reaseguro')]
for dim, c_et, c_dic, nombre in BLQ:
    for ln, cpt, off in ((9,'Prima Tomada',1),(19,'Comisiones (Costos de Adquisición)',2)):
        linea([T(0, f"{nombre.upper()} · {cpt.upper()}", X['BAR']), B(1,X['BAR']), B(2,X['BAR']), B(3,X['BAR']), B(4,X['BAR']), B(5,X['BAR'])])
        linea([T(0,"Miembro (rótulo en ValDim)",X['HDR']), T(1,"Celda ValDim",X['HDR_C']), T(2,"ValDim dice",X['HDR_C']), T(3,"Vista evaluada (hoja Val_*)",X['HDR_C']), T(4,"Diferencia",X['HDR_C']), T(5,"Origen de la cifra de ValDim",X['HDR'])])
        rr = 8
        while (rr, c_et) in VD:
            et = VD[(rr, c_et)][0]; fil = rr + off; cel = (fil, c_dic)
            vval, vf = VD.get(cel, (None,None)); vval = vval or 0.0
            mb = float(et) if dim == 'TREA' else str(et)
            prow = POS[dim][ln].get(mb)
            vista_v = (OUT[dim]['res'][mb]['lineas'][ln] or [0]*NM)[11] if mb in OUT[dim]['res'] else 0.0
            org = (f"Fórmula viva = {OUT[dim]['vista']}!P${9 if ln==9 else 19}: muestra el miembro del selector, no necesariamente '{et}'" if vf
                   else "Valor pegado (constante), sin fórmula")
            cs = [N(0, mb, X['TXT']) if isinstance(mb,float) else T(0, str(et), X['TXT']),
                  T(1, f"ValDim!{colrow(*cel)}", X['TXT_C']),
                  FN(2, vval, W.ref3d(IX['ValDim'], cel[0], cel[1]), X['NUM'])]
            if prow is not None:
                cs += [FN(3, vista_v, W.ref3d(IX_HOJA[dim], prow, CD+11), X['NUM']),
                       FN(4, vval - vista_v, W.ref(r,2,rrel=True) + W.ref(r,3,rrel=True) + W.SUB, X['NUM_Y'])]
            else:
                cs += [B(3, X['NUM']), B(4, X['NUM_Y'])]
            cs.append(T(5, org, X['OBS']))
            linea(cs); rr += 3
        r += 1
linea([T(0, "'Credito' (sin acento) y 'LN04008-Agro' no aparecen en ValDim; están en las hojas Val_Ramo y Val_LN.", X['NOTA'])])
HOJA_VD = W.sheet_bin(rows, 6, cols=[(0,0,28),(1,1,14),(2,2,18),(3,3,24),(4,4,18),(5,5,80)])

# ================= insertar =================
HS = [('Val_Resumen', HOJA_RES), ('Val_Ramo', HOJAS['RAMO']), ('Val_LN', HOJAS['LN']), ('Val_Region', HOJAS['REGION']),
      ('Val_TRea', HOJAS['TREA']), ('Val_Origen', HOJA_ORIG), ('Val_ValDim', HOJA_VD)]
n = E.insertar(SRC, DST, HS, xti_extra=XTI_EXTRA, cadenas=P, styles_bin=STYLES_NEW)
for x in n: print(x)
print('cadenas nuevas:', len(P.nuevas), '| xfs nuevos desde', min(X.values()))
pickle.dump(dict(POS=POS, ANC=ANC, RESROW=RESROW, X=X), open('construccion.pkl','wb'))
