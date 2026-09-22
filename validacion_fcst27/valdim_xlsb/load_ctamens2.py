from pyxlsb import open_workbook
import pandas as pd, pickle, time
KEEP = {0:'A_mes',1:'B_cta',2:'C_ln',4:'E_reg',11:'L_tre',16:'Q_monto',17:'R_ramo',
        22:'W_ced',26:'AA_xl',27:'AB_recu',28:'AC_evcat',29:'AD_attcat',30:'AE_sincatced',31:'AF_gtos'}
t0=time.time(); recs=[]
with open_workbook('FCST.xlsb').get_sheet('CtaMens') as sh:
    for i,row in enumerate(sh.rows()):
        if i<3: continue
        d={v:None for v in KEEP.values()}
        for c in row:
            n=KEEP.get(c.c)
            if n: d[n]=c.v
        d['_fila']=i+1; recs.append(d)
df=pd.DataFrame(recs)
df=df.dropna(subset=['A_mes']).copy()
df['A_mes']=df['A_mes'].astype(int); df['B_cta']=df['B_cta'].astype(str)
for c in ['Q_monto','W_ced','AA_xl','AB_recu','AC_evcat','AD_attcat','AE_sincatced','AF_gtos','L_tre']:
    df[c]=pd.to_numeric(df[c],errors='coerce').fillna(0.0)
pickle.dump(df, open('ctamens_full.pkl','wb'))
print('filas',len(df),f'{time.time()-t0:.0f}s'); print(df.describe().T[['count','mean']].to_string())
