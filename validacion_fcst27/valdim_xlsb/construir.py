# -*- coding: utf-8 -*-
"""Construye las hojas de validacion y las inserta en el libro original."""
import pickle, struct
import xlsbw as W, empaquetar
from biff import colrow

AN = pickle.load(open('analisis.pkl','rb'))
BLOQ, GLOBAL, MESES, NOMMES = AN['BLOQ'], AN['GLOBAL'], AN['MESES'], AN['NOMMES']
CPT = AN['CPT']
F0, F1 = AN['FILA_INI']-1, AN['FILA_FIN']-1          # 0-based: 3 .. 201233

# ---- ixti ----
IX_CTAMENS = 3; IX_ER = 56
IX_ER_DIM  = {'ER_ram':28, 'ER_ln':6, 'ER_reg':7, 'ER_tre':8}
IX_VALDIM  = 63
IX_RES, IX_RAMO, IX_LN, IX_REG, IX_TRE, IX_ORIG = 64, 65, 66, 67, 68, 69
XTI_EXTRA = [(0,12,12)] + [(0,t,t) for t in range(28, 34)]

# ---- estilos reutilizados del propio libro ----
S_TIT, S_TXT, S_NUM, S_TOT, S_SUB = 824, 725, 49, 87, 738

# ---- columnas del detalle CtaMens (0-based) ----
C_MES, C_CTA, C_MONTO = 0, 1, 16
C_DIM = {'RAMO':17, 'LN':2, 'REGION':4, 'TREA':11}

# ---- geometria de las hojas de dimension ----
B1, B2, B3 = 3, 16, 29          # primera columna de cada bloque (D, Q, AD)

P = W.Cadenas(empaquetar.leer_sst('FCST.xlsb'))
def T(col, s, st=S_TXT):  return W.c_isst(col, P.add(s), st)
def N(col, v, st=S_NUM):  return W.c_num(col, v, st)

def sumifs(dim_col, cta, r_cal, r_mem, j, negar):
    """-SUMIFS(CtaMens!Q, B,cta, A,<mes>, <dim>,<miembro>) tal como lo hace el libro."""
    g  = W.area3d(IX_CTAMENS, F0, F1, C_MONTO, C_MONTO)
    g += W.area3d(IX_CTAMENS, F0, F1, C_CTA,  C_CTA)  + W.num(cta)
    g += W.area3d(IX_CTAMENS, F0, F1, C_MES,  C_MES)  + W.ref(r_cal, B2+j, crel=True)
    g += W.area3d(IX_CTAMENS, F0, F1, dim_col, dim_col) + W.ref(r_mem, 0, rrel=True)
    g += W.funcvar(7, W.IF_SUMIFS)
    if negar: g += W.UMINUS
    return g

# ================= hojas por dimension =================
HOJAS = {}
ANCLAS = {}          # {key: {cpt: (fila_suma, fila_global, fila_dif)}}

for b in BLOQ:
    rows = {}; anclas = {}
    dim_col = C_DIM[b['key']]
    rows[0] = [T(0, f"VALIDACION DE LA VISTA POR {b['nom'].upper()} — PRESUPUESTO 2027", S_TIT)]
    rows[1] = [T(0, "Bloque izquierdo: lo que muestra ValDim.  Centro: el mismo concepto recalculado "
                    f"directo de CtaMens.  Derecha: la diferencia.", S_TXT)]
    rows[2] = [T(0, f"El recalculo usa la misma formula del libro: SUMIFS sobre CtaMens!Q "
                    f"(monto) filtrando B=cuenta, A=mes y {chr(65+dim_col) if dim_col<26 else '?'}={b['nom']}.", S_TXT)]
    base = 4
    for k, (cpt, cptnom, cta, sg) in enumerate(CPT):
        negar = (sg < 0)
        r_tit, r_cal, r_blq, r_hdr = base, base+1, base+2, base+3
        rows[r_tit] = [T(0, f"{cptnom.upper()}  (cifras acumuladas del año, USD)", S_TIT)]
        rows[r_cal] = [T(2, "CALMONTH que usa el SUMIFS →", S_TXT)] + \
                      [N(B2+j, MESES[j], S_NUM) for j in range(12)]
        rows[r_blq] = [T(B1, "LO QUE MUESTRA ValDim", S_TIT),
                       T(B2, "RECALCULO DIRECTO DE CtaMens", S_TIT),
                       T(B3, "DIFERENCIA  (ValDim − Recalculo)", S_TIT)]
        h = [T(0,"Miembro",S_TIT), T(1,"Renglones en CtaMens",S_TIT), T(2,"Origen de la cifra de ValDim",S_TIT)]
        for j in range(12):
            h += [T(B1+j, NOMMES[j], S_TIT), T(B2+j, NOMMES[j], S_TIT), T(B3+j, NOMMES[j], S_TIT)]
        rows[r_hdr] = h
        r = r_hdr + 1; r_m0 = r
        for m in b['miembros']:
            cs = []
            et = m['etiqueta']
            if b['key'] == 'TREA':
                cs.append(N(0, float(et), S_NUM))
            else:
                cs.append(T(0, str(et), S_TXT))
            cs.append(N(1, m['nfilas'], S_NUM))
            if not m['en_valdim']:
                org = "NO APARECE en ValDim, pero si existe en CtaMens"
            elif m['nfilas'] == 0:
                org = (f"ValDim!{m['vd'][cpt]['celdas'][11]} = valor pegado. "
                       f"Con ese nombre exacto CtaMens no tiene ni un renglon.")
            elif m['vd'][cpt]['viva']:
                org = f"ValDim!{m['vd'][cpt]['celdas'][11]} = formula viva → {b['er']}!{'P$9' if k==0 else 'P$19'}"
            else:
                org = f"ValDim!{m['vd'][cpt]['celdas'][11]} = valor pegado (constante)"
            cs.append(T(2, org, S_TXT))
            for j in range(12):
                # bloque 1: lo que dice ValDim
                if m['en_valdim']:
                    cel = m['vd'][cpt]['celdas'][j]
                    col0 = b['c_m1'] + j
                    fil0 = (m['fila_excel'] + (0 if k == 0 else 1))   # 0-based ya
                    cs.append(W.c_fmla_num(B1+j, m['vd'][cpt]['vals'][j] or 0.0,
                                           W.ref3d(IX_VALDIM, fil0, col0), S_NUM))
                # bloque 2: recalculo
                g = sumifs(dim_col, cta, r_cal, r, j, negar)
                if j > 0:
                    g = g + W.ref(r, B2+j-1, crel=True, rrel=True) + W.ADD
                cs.append(W.c_fmla_num(B2+j, m['real'][cpt][j], g, S_NUM))
                # bloque 3: diferencia
                cs.append(W.c_fmla_num(B3+j, (m['vd'][cpt]['vals'][j] or 0.0) - m['real'][cpt][j],
                                       W.ref(r,B1+j,crel=True,rrel=True) +
                                       W.ref(r,B2+j,crel=True,rrel=True) + W.SUB, S_NUM))
            rows[r] = cs
            r += 1
        r_sum, r_glo, r_dif = r, r+1, r+2
        nm = len(b['miembros'])
        s1 = [sum((m['vd'][cpt]['vals'][j] or 0) for m in b['miembros']) for j in range(12)]
        s2 = [sum(m['real'][cpt][j] for m in b['miembros']) for j in range(12)]
        cs = [T(0, "SUMA DE LOS MIEMBROS", S_TIT)]
        for j in range(12):
            for blk, cach in ((B1, s1[j]), (B2, s2[j]), (B3, s1[j]-s2[j])):
                cs.append(W.c_fmla_num(blk+j, cach,
                          W.area(r_m0, r_m0+nm-1, blk+j, blk+j) + W.funcvar(1, W.IF_SUM), S_TOT))
        rows[r_sum] = cs
        erow = 4 if k == 0 else 16
        cs = [T(0, "GLOBAL DEL PRESUPUESTO  (hoja ER)", S_TIT),
              T(2, f"ER!{'F' if k==0 else 'F'}${erow+1}:Q${erow+1} = -SUMIFS(CtaMens!Q; B;{cta}; A;mes)", S_TXT)]
        for j in range(12):
            for blk in (B1, B2):
                cs.append(W.c_fmla_num(blk+j, GLOBAL[cpt][j], W.ref3d(IX_ER, erow, 5+j), S_TOT))
            cs.append(W.c_fmla_num(B3+j, 0.0,
                      W.ref(r_glo,B1+j,crel=True,rrel=True) +
                      W.ref(r_glo,B2+j,crel=True,rrel=True) + W.SUB, S_TOT))
        rows[r_glo] = cs
        cs = [T(0, "DESCUADRE CONTRA EL GLOBAL", S_TIT),
              T(2, "Suma de los miembros menos el global", S_TXT)]
        for j in range(12):
            for blk, cach in ((B1, s1[j]-GLOBAL[cpt][j]), (B2, s2[j]-GLOBAL[cpt][j]), (B3, s1[j]-s2[j])):
                cs.append(W.c_fmla_num(blk+j, cach,
                          W.ref(r_sum,blk+j,crel=True,rrel=True) +
                          W.ref(r_glo,blk+j,crel=True,rrel=True) + W.SUB, S_SUB))
        rows[r_dif] = cs
        anclas[cpt] = (r_sum, r_glo, r_dif)
        base = r_dif + 3
    HOJAS[b['key']] = W.sheet_bin(rows, B3+12)
    ANCLAS[b['key']] = anclas

# ================= hoja resumen =================
IXH = {'RAMO':IX_RAMO, 'LN':IX_LN, 'REGION':IX_REG, 'TREA':IX_TRE}
DIC1, DIC2, DIC3 = B1+11, B2+11, B3+11

rows = {}
rows[0] = [T(0, "RESUMEN — ¿CUADRAN LAS VISTAS POR DIMENSION CONTRA EL GLOBAL? (FCST 2027, diciembre acumulado)", S_TIT)]
txt = [
 "Cada vista de ValDim compara la suma de sus miembros contra el global del presupuesto.",
 "Columna C: la suma que ValDim trae hoy.   Columna F: la misma suma recalculada directo de CtaMens con la formula del propio libro.",
 "Si el recalculo cuadra en 0.00 y ValDim no, el descuadre no esta en los datos: esta en las cifras que ValDim trae capturadas.",
 "Detalle mes a mes y miembro por miembro en las hojas Val_Ramo, Val_LN, Val_Region y Val_TRea. El rastreo de cada formula, en Val_Origen.",
]
for i, t in enumerate(txt): rows[1+i] = [T(0, t, S_TXT)]
rows[6] = [T(0,"Dimension",S_TIT), T(1,"Concepto",S_TIT),
           T(2,"Suma de miembros segun ValDim",S_TIT), T(3,"Global (ER)",S_TIT),
           T(4,"Descuadre que muestra ValDim",S_TIT),
           T(5,"Suma de miembros recalculada de CtaMens",S_TIT), T(6,"Global (ER)",S_TIT),
           T(7,"Descuadre real",S_TIT), T(8,"Lectura",S_TIT)]
r = 7
for b in BLOQ:
    ix = IXH[b['key']]
    for k,(cpt,cptnom,cta,sg) in enumerate(CPT):
        r_sum, r_glo, r_dif = ANCLAS[b['key']][cpt]
        sv = sum((m['vd'][cpt]['vals'][11] or 0) for m in b['miembros'])
        sr = sum(m['real'][cpt][11] for m in b['miembros'])
        g  = GLOBAL[cpt][11]
        lect = ("La vista cuadra en los datos; lo que ValDim muestra viene de cifras capturadas."
                if abs(sr-g) < 0.01 else "Revisar: el recalculo tampoco cuadra.")
        rows[r] = [T(0, b['nom'], S_TXT), T(1, cptnom, S_TXT),
          W.c_fmla_num(2, sv, W.ref3d(ix, r_sum, DIC1), S_TOT),
          W.c_fmla_num(3, g,  W.ref3d(ix, r_glo, DIC1), S_TOT),
          W.c_fmla_num(4, sv-g, W.ref3d(ix, r_dif, DIC1), S_TOT),
          W.c_fmla_num(5, sr, W.ref3d(ix, r_sum, DIC2), S_TOT),
          W.c_fmla_num(6, g,  W.ref3d(ix, r_glo, DIC2), S_TOT),
          W.c_fmla_num(7, sr-g, W.ref3d(ix, r_dif, DIC2), S_TOT),
          T(8, lect, S_TXT)]
        r += 1
HOJA_RES = W.sheet_bin(rows, 9)

# ================= hoja de rastreo =================
rows = {}; r = 0
def linea(cs):
    global r
    rows[r] = cs; r += 1
def sec(t):
    global r
    r += 1; rows[r] = [T(0, t, S_TIT)]; r += 1

linea([T(0, "DE DONDE SALE CADA CIFRA QUE SE ESTA COMPARANDO", S_TIT)])
linea([T(0, "La columna Valor trae una formula viva apuntando a la celda original, para que se pueda auditar sin salir del libro.", S_TXT)])

sec("1) LA CADENA COMPLETA")
linea([T(0,"Celda",S_TIT), T(1,"Que contiene",S_TIT), T(2,"Formula tal cual esta en el libro",S_TIT), T(3,"Valor",S_TIT)])
VAL = {"ValDim!O3":1221468789.5700004, "ER!Q5":1221468789.5700004,
       "ValDim!O4":253227062.79999977, "ER!Q17":253227062.79999977,
       "ValDim!O10":242188696.82999998, "ER_ram!P9":242188696.82999998,
       "ValDim!AC10":238262208.88000005, "ValDim!AQ10":89356450.04999998,
       "ValDim!BE10":256914040.65999997, "ValDim!O13":13462965.82,
       "ValDim!O6":165162122.33}
CAD = [
 ("ValDim!O3",   "Global prima tomada, diciembre acumulado", "=ER!Q$5", IX_ER, 4, 16),
 ("ER!Q5",       "Global prima: suma de CtaMens sin filtrar dimension",
                 "=-SUMIFS(CtaMens!$Q:$Q; CtaMens!$B:$B;61; CtaMens!$A:$A;Q$4)*Q$3+P5", IX_ER, 4, 16),
 ("ValDim!O4",   "Global comisiones, diciembre acumulado", "=ER!Q$17", IX_ER, 16, 16),
 ("ER!Q17",      "Global comisiones",
                 "=SUMIFS(CtaMens!$Q:$Q; CtaMens!$B:$B;53; CtaMens!$A:$A;Q$4)*Q$3+P17", IX_ER, 16, 16),
 ("ValDim!O10",  "Primer miembro de la vista Ramo (fila rotulada Vida)", "=ER_ram!P$9", IX_VALDIM, 9, 14),
 ("ER_ram!P9",   "Prima del ramo que este seleccionado en ER_ram!A6",
                 "=-SUMIFS(CtaMens!$Q:$Q; CtaMens!$B:$B;61; CtaMens!$A:$A;P$7; CtaMens!$R:$R;$A$6)*P$6+O9",
                 IX_ER_DIM['ER_ram'], 8, 15),
 ("ValDim!AC10", "Primer miembro de la vista LN",     "=ER_ln!P$9",  IX_VALDIM, 9, 28),
 ("ValDim!AQ10", "Primer miembro de la vista Region", "=ER_reg!P$9", IX_VALDIM, 9, 42),
 ("ValDim!BE10", "Primer miembro de la vista Tipo Rea","=ER_tre!P$9",IX_VALDIM, 9, 56),
 ("ValDim!O13",  "Segundo miembro de la vista Ramo (Acc Per.)", "Constante capturada, sin formula", IX_VALDIM, 12, 14),
 ("ValDim!O6",   "Descuadre de la vista Ramo", "=(O10+O13+...+O49)-O3", IX_VALDIM, 5, 14),
]
for cel, que, f, ix, rr, cc in CAD:
    linea([T(0,cel,S_TXT), T(1,que,S_TXT), T(2,f,S_TXT),
           W.c_fmla_num(3, VAL.get(cel, 0.0), W.ref3d(ix, rr, cc), S_NUM)])

sec("2) QUE COLUMNA DE CtaMens USA CADA FILTRO")
linea([T(0,"Columna",S_TIT), T(1,"Encabezado (fila 3 de CtaMens)",S_TIT), T(2,"Para que se usa",S_TIT)])
for col, enc, uso in [
 ("A","CALMONTH / PERIODO","Mes del presupuesto (202701 a 202712)"),
 ("B","GL_ACCT / TY","Familia de cuenta: 61 prima, 53 comisiones, 54 siniestros"),
 ("C","FUNCAREA","Linea de negocio — filtro de la vista ER_ln"),
 ("E","ZREGIONRP","Region — filtro de la vista ER_reg"),
 ("L","ZTIPOREAS","Tipo de reaseguro — filtro de la vista ER_tre"),
 ("Q","AMOUNT / MONTO","Importe que se suma"),
 ("R","RamoN / RAMO","Ramo — filtro de la vista ER_ram")]:
    linea([T(0,col,S_TXT), T(1,enc,S_TXT), T(2,uso,S_TXT)])
linea([T(0,"Renglones con datos: de la fila 4 a la 201,234. El recalculo usa exactamente ese rango.",S_TXT)])

sec("3) QUE CELDAS DE ValDim ESTAN VIVAS Y CUALES ESTAN CAPTURADAS")
linea([T(0,"Filas de ValDim",S_TIT), T(1,"Contenido",S_TIT), T(2,"Celdas con formula",S_TIT), T(3,"Celdas capturadas",S_TIT)])
CENSO = [("3 y 4","Global de prima y comisiones",96,0),
         ("6 y 7","Descuadre de cada vista",96,0),
         ("10 y 11","Primer miembro de cada vista",96,0),
         ("13 en adelante","Todos los demas miembros de las cuatro vistas",0,552)]
for a,bb,cf,cc in CENSO:
    linea([T(0,a,S_TXT), T(1,bb,S_TXT), N(2,cf), N(3,cc)])
linea([T(0,"Solo la primera fila de miembro de cada vista se recalcula sola. Las demas quedaron como valor.",S_TXT)])

sec("4) EN QUE MIEMBRO ESTA PARADO HOY CADA SELECTOR")
linea([T(0,"Vista",S_TIT), T(1,"Celda del selector",S_TIT), T(2,"Miembro seleccionado hoy",S_TIT),
       T(3,"Rotulo de la primera fila de ValDim",S_TIT), T(4,"Coinciden?",S_TIT)])
SEL = [("Ramo","ER_ram!A6",IX_ER_DIM['ER_ram'],5,0,"Vida",  IX_VALDIM,8,1, "Vida"),
       ("Linea de negocio","ER_ln!A6",IX_ER_DIM['ER_ln'],5,0,"LN04001", IX_VALDIM,8,16,"LN04001"),
       ("Region","ER_reg!A6",IX_ER_DIM['ER_reg'],5,0,"R06", IX_VALDIM,8,30,"R01"),
       ("Tipo de reaseguro","ER_tre!A6",IX_ER_DIM['ER_tre'],5,0,3.0, IX_VALDIM,8,44,1.0)]
for nom, cel, ix, rr, cc, vsel, ixv, rv, cv, vrot in SEL:
    fsel = (W.c_fmla_num(2, vsel, W.ref3d(ix, rr, cc), S_NUM) if isinstance(vsel,float)
            else W.c_fmla_str(2, vsel, W.ref3d(ix, rr, cc), S_TXT))
    frot = (W.c_fmla_num(3, vrot, W.ref3d(ixv, rv, cv), S_NUM) if isinstance(vrot,float)
            else W.c_fmla_str(3, vrot, W.ref3d(ixv, rv, cv), S_TXT))
    ok = "Si" if vsel == vrot else "NO — la primera fila muestra otro miembro del que dice el rotulo"
    linea([T(0,nom,S_TXT), T(1,cel,S_TXT), fsel, frot, T(4, ok, S_TXT)])
linea([T(0,"Si el selector no esta parado en el miembro que rotula la primera fila, esa fila muestra otro miembro.",S_TXT)])
HOJA_ORIG = W.sheet_bin(rows, 5)

# ================= insertar =================
HS = [('Val_Resumen', HOJA_RES),
      ('Val_Ramo',    HOJAS['RAMO']),
      ('Val_LN',      HOJAS['LN']),
      ('Val_Region',  HOJAS['REGION']),
      ('Val_TRea',    HOJAS['TREA']),
      ('Val_Origen',  HOJA_ORIG)]
n = empaquetar.insertar('FCST.xlsb', 'FCST_2027_Cesion.xlsb', HS,
                        xti_extra=XTI_EXTRA, cadenas=P)
for x in n: print(x)
print('cadenas nuevas:', len(P.nuevas))
