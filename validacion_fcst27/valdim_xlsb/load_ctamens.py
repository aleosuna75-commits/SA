from pyxlsb import open_workbook
import pandas as pd, pickle, time
# Excel cols used by the ER formulas (0-based): A=0 mes, B=1 cuenta, C=2 LN,
# E=4 region, L=11 tipo rea, Q=16 monto, R=17 ramo
KEEP = {0:'A_mes', 1:'B_cta', 2:'C_ln', 4:'E_reg', 11:'L_tre', 16:'Q_monto', 17:'R_ramo'}
t0=time.time(); recs=[]
wb = open_workbook('FCST.xlsb')
with wb.get_sheet('CtaMens') as sh:
    for i, row in enumerate(sh.rows()):
        if i < 3:            # fila 1 encabezado tecnico, fila 2 totales, fila 3 encabezado
            continue
        d = {v: None for v in KEEP.values()}
        for c in row:
            n = KEEP.get(c.c)
            if n: d[n] = c.v
        d['_fila'] = i+1
        recs.append(d)
df = pd.DataFrame(recs)
print('filas', len(df), f'{time.time()-t0:.0f}s')
print(df.dtypes)
pickle.dump(df, open('ctamens_excelcols.pkl','wb'))
print(df.head(3).to_string())
print('ultimas filas'); print(df.tail(3).to_string())
