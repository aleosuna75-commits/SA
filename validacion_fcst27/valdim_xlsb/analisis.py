import pickle, pandas as pd, numpy as np
from biff import colrow

MESES = list(range(202701, 202713))
NOMMES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

V  = pickle.load(open('valdim.pkl','rb'))
df = pickle.load(open('ctamens_excelcols.pkl','rb'))
d  = df.dropna(subset=['A_mes']).copy()
d['A_mes']   = d['A_mes'].astype(int)
d['B_cta']   = d['B_cta'].astype(str)
d['Q_monto'] = pd.to_numeric(d['Q_monto'], errors='coerce').fillna(0.0)
d = d[(d.A_mes >= 202701) & (d.A_mes <= 202712)]
FILA_INI, FILA_FIN = 4, 201234

# bloque: nombre, col0 etiqueta, col0 primer mes, col CtaMens, hoja ER, ixti ER, col excel criterio
BLOQ = [
 dict(key='RAMO',   nom='Ramo',              c_et=1,  c_m1=3,  col='R_ramo', er='ER_ram', xls_col='R', xls_i=17, tipo='texto'),
 dict(key='LN',     nom='Linea de Negocio',  c_et=16, c_m1=17, col='C_ln',   er='ER_ln',  xls_col='C', xls_i=2,  tipo='texto'),
 dict(key='REGION', nom='Region',            c_et=30, c_m1=31, col='E_reg',  er='ER_reg', xls_col='E', xls_i=4,  tipo='texto'),
 dict(key='TREA',   nom='Tipo de Reaseguro', c_et=44, c_m1=45, col='L_tre',  er='ER_tre', xls_col='L', xls_i=11, tipo='numero'),
]
CPT = [('P','Prima Tomada',61,-1.0), ('C','Comisiones Directos y Tomados',53,1.0)]

def acum(col, val, cta, signo):
    sub = d[(d.B_cta == str(cta)) & (d[col] == val)]
    g = sub.groupby('A_mes')['Q_monto'].sum()
    out, ac = [], 0.0
    for m in MESES:
        ac += float(g.get(m, 0.0)) * signo
        out.append(ac)
    return out

def acum_global(cta, signo):
    sub = d[d.B_cta == str(cta)]
    g = sub.groupby('A_mes')['Q_monto'].sum()
    out, ac = [], 0.0
    for m in MESES:
        ac += float(g.get(m, 0.0)) * signo
        out.append(ac)
    return out

RES = {}
for b in BLOQ:
    # miembros tal como los lista ValDim (fila excel 9, 12, 15, ...)
    miembros, r = [], 8
    while (r, b['c_et']) in V:
        et = V[(r, b['c_et'])][0]
        fila_p, fila_c = r + 1, r + 2      # 0-based
        vd = {}
        for k, (cpt, _, cta, sg) in enumerate(CPT):
            vals, viva, celdas = [], None, []
            for j in range(12):
                cell = (fila_p if k == 0 else fila_c, b['c_m1'] + j)
                val, f = V.get(cell, (None, None))
                vals.append(val); celdas.append(colrow(*cell))
                if viva is None: viva = bool(f)
            vd[cpt] = dict(vals=vals, celdas=celdas, viva=viva)
        miembros.append(dict(etiqueta=et, fila_excel=r + 1, vd=vd, en_valdim=True))
        r += 3
    # miembros que SI existen en CtaMens pero ValDim no lista
    reales = sorted(d[b['col']].dropna().unique(), key=str)
    faltan = [x for x in reales if x not in [m['etiqueta'] for m in miembros]]
    for x in faltan:
        miembros.append(dict(etiqueta=x, fila_excel=None,
                             vd={c: dict(vals=[None]*12, celdas=['']*12, viva=False) for c,_,_,_ in CPT},
                             en_valdim=False))
    # recalculo
    for m in miembros:
        m['real'] = {c: acum(b['col'], m['etiqueta'], cta, sg) for c, _, cta, sg in CPT}
        m['nfilas'] = int((d[b['col']] == m['etiqueta']).sum())
    b['miembros'] = miembros
    b['reales_univ'] = reales
    RES[b['key']] = b

GLOBAL = {c: acum_global(cta, sg) for c, _, cta, sg in CPT}
pickle.dump(dict(BLOQ=BLOQ, GLOBAL=GLOBAL, MESES=MESES, NOMMES=NOMMES,
                 FILA_INI=FILA_INI, FILA_FIN=FILA_FIN, CPT=CPT),
            open('analisis.pkl','wb'))

# ---- resumen en pantalla ----
for b in BLOQ:
    print('='*118)
    print(f"{b['nom']}  (criterio: CtaMens col {b['xls_col']}, hoja {b['er']})")
    for c, cn, cta, sg in CPT:
        sv = sum((m['vd'][c]['vals'][11] or 0) for m in b['miembros'])
        sr = sum(m['real'][c][11] for m in b['miembros'])
        g  = GLOBAL[c][11]
        print(f"  {cn:<32}  ValDim suma={sv:>18,.2f} vs global -> {sv-g:>16,.2f}   |   "
              f"Recalculo suma={sr:>18,.2f} vs global -> {sr-g:>14,.2f}")
    for m in b['miembros']:
        dp = (m['vd']['P']['vals'][11] or 0) - m['real']['P'][11]
        if abs(dp) > 0.005 or not m['en_valdim']:
            marca = 'NO ESTA EN ValDim' if not m['en_valdim'] else ('VIVA' if m['vd']['P']['viva'] else 'pegada')
            print(f"      {str(m['etiqueta']):<14} {marca:<18} ValDim={(m['vd']['P']['vals'][11] or 0):>18,.2f}  real={m['real']['P'][11]:>18,.2f}  dif={dp:>16,.2f}  filas={m['nfilas']:,}")
print('='*118)
print(f"GLOBAL dic  prima={GLOBAL['P'][11]:,.2f}   comisiones={GLOBAL['C'][11]:,.2f}")
