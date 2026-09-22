import pickle, pandas as pd, numpy as np
from biff import colrow

V = pickle.load(open('valdim.pkl','rb'))          # {(row0,col0):(valor, formula)}
df = pickle.load(open('ctamens_excelcols.pkl','rb'))
d = df.dropna(subset=['A_mes']).copy()
d['A_mes']  = d['A_mes'].astype(int)
d['B_cta']  = d['B_cta'].astype(str)
d['Q_monto']= pd.to_numeric(d['Q_monto'], errors='coerce').fillna(0.0)
d = d[(d['A_mes']>=202701)&(d['A_mes']<=202712)]

GLOB = {'P': -d.loc[d.B_cta=='61','Q_monto'].sum(),
        'C':  d.loc[d.B_cta=='53','Q_monto'].sum()}

# bloques de ValDim: (nombre, col etiqueta, col diciembre, columna de CtaMens, sheet ER)
BLOQ = [('RAMO',  1, 14, 'R_ramo', 'ER_ram'),
        ('LN',   16, 28, 'C_ln',   'ER_ln'),
        ('REGION',30,42, 'E_reg',  'ER_reg'),
        ('TREA', 44, 56, 'L_tre',  'ER_tre')]

def real(col, val, cta):
    m = (d.B_cta==str(cta)) & (d[col]==val)
    s = d.loc[m,'Q_monto'].sum()
    return -s if cta==61 else s

OUT = {}
for nom, ce, cd, ccol, ersh in BLOQ:
    filas = []
    r = 8                                    # fila excel 9 -> indice 8
    while (r, ce) in V:
        etiq = V[(r, ce)][0]
        vp, fp = V.get((r+1, cd), (None, None))
        vc, fc = V.get((r+2, cd), (None, None))
        clave = etiq
        rp = real(ccol, clave, 61); rc = real(ccol, clave, 53)
        n  = int(((d[ccol]==clave)).sum())
        filas.append(dict(fila=r+1, etiqueta=etiq, celda_p=colrow(r+1,cd), celda_c=colrow(r+2,cd),
                          viva=bool(fp), formula=fp or '', val_p=vp, val_c=vc,
                          real_p=rp, real_c=rc, dif_p=(vp or 0)-rp, dif_c=(vc or 0)-rc, nfilas=n))
        r += 3
    OUT[nom] = pd.DataFrame(filas)

for nom, ce, cd, ccol, ersh in BLOQ:
    t = OUT[nom]
    print('='*110)
    print(f'{nom}   (criterio CtaMens col {ccol})    hoja {ersh}')
    print('='*110)
    print(f"{'fila':>5} {'miembro':<14} {'celda':<6} {'viva':<5} {'ValDim prima':>18} {'real prima':>18} {'dif prima':>16}   {'ValDim comis':>16} {'real comis':>16} {'dif comis':>15}")
    for _,x in t.iterrows():
        print(f"{x.fila:>5} {str(x.etiqueta):<14} {x.celda_p:<6} {'SI' if x.viva else 'no':<5} "
              f"{(x.val_p or 0):>18,.2f} {x.real_p:>18,.2f} {x.dif_p:>16,.2f}   "
              f"{(x.val_c or 0):>16,.2f} {x.real_c:>16,.2f} {x.dif_c:>15,.2f}")
    sp, sc = t.val_p.fillna(0).sum(), t.val_c.fillna(0).sum()
    rp, rc = t.real_p.sum(), t.real_c.sum()
    print(f"{'':5} {'SUMA':<14} {'':6} {'':5} {sp:>18,.2f} {rp:>18,.2f} {sp-rp:>16,.2f}   {sc:>16,.2f} {rc:>16,.2f} {sc-rc:>15,.2f}")
    print(f"{'':5} {'GLOBAL':<14} {'':6} {'':5} {GLOB['P']:>18,.2f} {GLOB['P']:>18,.2f} {'':>16}   {GLOB['C']:>16,.2f} {GLOB['C']:>16,.2f}")
    print(f"{'':5} {'vs GLOBAL':<14} {'':6} {'':5} {sp-GLOB['P']:>18,.2f} {rp-GLOB['P']:>18,.2f} {'':>16}   {sc-GLOB['C']:>16,.2f} {rc-GLOB['C']:>16,.2f}")
    # miembros del detalle que ValDim no lista
    univ = set(d[ccol].dropna().unique()) - set(t.etiqueta)
    if univ:
        print(f'   MIEMBROS EN CtaMens QUE ValDim NO LISTA: {sorted(univ, key=str)}')
    print()
pickle.dump(OUT, open('comp.pkl','wb'))
