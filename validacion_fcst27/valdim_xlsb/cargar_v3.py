# -*- coding: utf-8 -*-
"""Lee del libro de Cesion (v3) CtaMens completo y las celdas (valor y formula) de las hojas que se usan."""
import sys, pickle, time
sys.path.insert(0, '/home/user/SA/validacion_fcst27/valdim_xlsb')
import pandas as pd, fmla, dump
from biff import sheet_map
from pyxlsb import open_workbook
F = 'FCST.xlsb'; t0 = time.time()
KEEP = {0:'A_mes',1:'B_cta',2:'C_ln',4:'E_reg',11:'L_tre',16:'Q_monto',17:'R_ramo',
        22:'W_ced',26:'AA_xl',27:'AB_recu',28:'AC_evcat',29:'AD_attcat',30:'AE_sincatced',31:'AF_gtos'}
recs = []
with open_workbook(F).get_sheet('CtaMens') as sh:
    for i, row in enumerate(sh.rows()):
        if i < 3: continue
        d = {v: None for v in KEEP.values()}
        for c in row:
            n = KEEP.get(c.c)
            if n: d[n] = c.v
        d['_fila'] = i + 1; recs.append(d)
df = pd.DataFrame(recs).dropna(subset=['A_mes']).copy()
df['A_mes'] = df['A_mes'].astype(int); df['B_cta'] = df['B_cta'].astype(str)
for c in ['Q_monto','W_ced','AA_xl','AB_recu','AC_evcat','AD_attcat','AE_sincatced','AF_gtos','L_tre']:
    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
pickle.dump(df, open('ctamens_v3.pkl', 'wb'))
print('CtaMens', len(df), f'{time.time()-t0:.0f}s', flush=True)
ctx = fmla.Ctx(F); S = dump.sst(F); SM = {n: p for n, p in sheet_map(F)}
HOJAS = ['ER','ER_ln','ER_ram','ER_reg','ER_tre','2_Reservas','Parámetros','Inicio','CAT','Gastos','Anexo2_1225',
         'ER1225_Real','Valores','Val_LN','Val_Ramo','Val_Region','Val_TRea','Val_Resumen','Val_CAT','RIF']
CEL = {}
for h in HOJAS:
    CEL[h] = {(r, c): (v, f) for r, c, v, f in dump.cells(F, SM[h], ctx, S)}
    print(h, len(CEL[h]), f'{time.time()-t0:.0f}s', flush=True)
pickle.dump(CEL, open('celdas_v3.pkl', 'wb'))
print('listo')
