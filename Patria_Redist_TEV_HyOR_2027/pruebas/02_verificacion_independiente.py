# -*- coding: utf-8 -*-
"""
Verificación INDEPENDIENTE del script (no reutiliza su código): lee original y redistribuido como lo hace CtaMens.py.
Uso: python 02_verificacion_independiente.py <carpeta_test>   (la carpeta generada por 01_generar_datos_prueba.py, tras correr el script
     con --ajustar-split-explicito --no-revisar-sensibles y --salida <carpeta_test>/Inputs/PptoTecnico2027_Red.csv)
"""
import pandas as pd, numpy as np, sys, os
os.chdir(sys.argv[1])
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
o = pd.read_csv('Inputs/PptoTecnico2027.csv', thousands=',')
r = pd.read_csv('Inputs/PptoTecnico2027_Red.csv', thousands=',')
print("cols iguales y mismo orden:", list(o.columns)==list(r.columns))
print("dtypes iguales:", (o.dtypes.astype(str)==r.dtypes.astype(str)).all(), "| diffs:", {c:(str(o[c].dtype),str(r[c].dtype)) for c in o.columns if str(o[c].dtype)!=str(r[c].dtype)})
def prep(d):
    d = d.copy(); d['GL2']=d['/ERP/GL_ACCT'].astype(str).str[:2]; d['RAMO']=d['/ERP/PROFTCTR'].str[1:4].astype(int)
    d['LLAVE']=d['ZTIPOREAS'].fillna(0).astype(int).astype(str)+'-'+d['ZCEDENTE'].fillna(0).astype(int).astype(str)+'-'+d['ZCONTRATO'].fillna(0).astype(int).astype(str)+'-'+d['/ERP/FUNCAREA']
    return d
o, r = prep(o), prep(r)
hist = pd.read_csv('Inputs/Redistribucion/Hist_Real_LLAVE_Ramo.csv')
hist['LLAVE']=hist['ZTIPOREAS'].astype(str)+'-'+hist['ZCEDENTE'].astype(str)+'-'+hist['ZCONTRATO'].astype(str)+'-'+hist['FUNCAREA']
# 1) totales por LLAVE-GL-mes-año (todas las LLAVEs) idénticos
k=['LLAVE','GL2','0FISCYEAR','0CALMONTH']
a=o.groupby(k)['/ERP/AMOUNT'].sum(); b=r.groupby(k)['/ERP/AMOUNT'].sum()
d=(pd.concat([a.rename('a'),b.rename('b')],axis=1).fillna(0)); d['dif']=d['b']-d['a']
print("1) max |dif| LLAVE-GL-FY-mes:", d['dif'].abs().max(), "| total global dif:", round(r['/ERP/AMOUNT'].sum()-o['/ERP/AMOUNT'].sum(),6))
# 2) filas fuera del alcance: idénticas (comparación exacta fila a fila por posición en las primeras 70001 filas, salvo montos modificados)
ajust = {'1-5-20-LN04001','1-40-16-LN04001','1-181-1-LN04001','1-296-6-LN04001','1-32-71-LN04001','2-85-4-LN04001','1-264-19-LN04001'}
o0 = o.iloc[:len(o)]; r0 = r.iloc[:len(o)]
cols_cmp = [c for c in o.columns if c not in ('/ERP/AMOUNT','GL2','RAMO','LLAVE')]
same_attr = (o0[cols_cmp].fillna('NA').astype(str).values == r0[cols_cmp].fillna('NA').astype(str).values).all()
print("2) atributos (todo salvo AMOUNT) idénticos en las primeras", len(o), "filas:", same_attr)
mask_fuera = ~(o0['LLAVE'].isin(ajust) & o0['RAMO'].isin([71,73]))
print("   montos idénticos fuera del alcance:", np.allclose(o0.loc[mask_fuera,'/ERP/AMOUNT'], r0.loc[mask_fuera,'/ERP/AMOUNT']), "| filas fuera alcance:", mask_fuera.sum())
# 3) clones: atributos idénticos a alguna fila original de la misma firma, PROFTCTR correcto
cl = r.iloc[len(o):]
print("3) clones:", len(cl), "| PROFTCTR:", cl['/ERP/PROFTCTR'].value_counts().to_dict(), "| LLAVEs:", sorted(cl['LLAVE'].unique()))
firma = [c for c in o.columns if c not in ('/ERP/PROFTCTR','/ERP/AMOUNT','/ERP/AMOUNT_T','GL2','RAMO','LLAVE')]
ofirmas = set(map(tuple, o[firma].fillna('NA').astype(str).values.tolist()))
cfirmas = list(map(tuple, cl[firma].fillna('NA').astype(str).values.tolist()))
print("   todas las firmas de los clones existen en el original:", all(f in ofirmas for f in cfirmas))
# 4) participación 73 por LLAVE ajustada (Primas y Comisiones) vs pesos esperados
def share(d, llave, gl):
    s = d[(d['LLAVE']==llave)&(d['GL2']==gl)&(d['RAMO'].isin([71,73]))].groupby('RAMO')['/ERP/AMOUNT'].sum().reindex([71,73]).fillna(0)
    return (s[73]/s.sum()) if s.sum()!=0 else np.nan
esperado = {'1-5-20-LN04001':{'61':0.6,'53':0.6}, '1-40-16-LN04001':{'61':0.6,'53':0.7,'54':0.6}, '1-181-1-LN04001':{'61':0.75,'53':0.75},
            '1-296-6-LN04001':{'61':0.65,'53':0.65}, '1-32-71-LN04001':{'61':0.5,'53':0.5}, '2-85-4-LN04001':{'61':0.5,'53':0.5}, '1-264-19-LN04001':{'61':0.27,'53':0.272}}
print("4) participación 73 por LLAVE ajustada (antes -> después | esperado):")
ok=True
for l,exp in esperado.items():
    for gl,e in exp.items():
        s0, s1 = share(o,l,gl), share(r,l,gl)
        flag = '' if (pd.isna(s1) or abs(s1-e)<0.005) else '  <-- REVISAR'
        if flag: ok=False
        print(f"   {l} GL{gl}: {s0:.4f} -> {s1:.4f} | esperado {e:.4f}{flag}")
# 5) filas por firma: cada firma de una LLAVE ajustada tiene exactamente una fila por ramo (71 y 73) salvo targets 0
sub = r[r['LLAVE'].isin(ajust)&r['RAMO'].isin([71,73])]
cnt = sub.groupby(firma, dropna=False)['RAMO'].nunique()
print("5) firmas en LLAVEs ajustadas:", len(cnt), "| con 2 ramos:", (cnt==2).sum(), "| con 1 ramo:", (cnt==1).sum())
# 6) no ajustadas: 1-181-4 (EXCLUIR), 1-486-1, 1-124-3 (inválido) sin cambios
for l in ['1-181-4-LN04001','1-486-1-LN04001','1-124-3-LN04001']:
    print(f"6) {l}: share73 antes {share(o,l,'61'):.4f} -> después {share(r,l,'61'):.4f}")
# 7) simular inicio de CtaMens.py sobre el redistribuido
rr = r.copy(); rr['_ID']=rr.index
cp = rr[(rr['0FISCYEAR']<=2027)&(rr['0FISCYEAR']>2026)&(rr['/ERP/AMOUNT']!=0)].copy()
cp['/ERP/GL_ACCT']=cp['/ERP/GL_ACCT'].astype(str).str[:2]
cp['LLAVE_LN4004']=(cp['ZCORREDOR'].fillna(0).astype(int).astype(str)+'-'+cp['ZCEDENTE'].fillna(0).astype(int).astype(str)+'-'+cp['ZCONTRATO'].fillna(0).astype(int).astype(str)+'-'+cp['ZTIPOREAS'].fillna(0).astype(int).astype(str)+'-'+cp['ZREGIONRP'].fillna('').astype(str))
print("7) CtaMens-like filtro 2027 & !=0:", len(cp), "filas; _ID duplicados:", cp['_ID'].duplicated().sum(), "; GL:", cp['/ERP/GL_ACCT'].unique().tolist())
print("VERIFICACION OK" if ok and same_attr else "VERIFICACION CON OBSERVACIONES")
