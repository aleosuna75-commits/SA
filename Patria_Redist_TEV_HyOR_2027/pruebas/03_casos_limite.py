# -*- coding: utf-8 -*-
"""
Batería de casos límite para 0_Redistribucion_TEV_HyOR.py v1.1.
Uso: python 03_casos_limite.py <carpeta_test>   (carpeta generada por 01_generar_datos_prueba.py)
Cada caso imprime [OK] o [FALLO]; los casos marcados esperado_ok=False deben terminar con error y mensaje claro.
"""
import subprocess, sys, os, pandas as pd, numpy as np, shutil, glob
S = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "0_Redistribucion_TEV_HyOR.py")
os.chdir(sys.argv[1])
os.makedirs('edge', exist_ok=True)
def run(name, args, expect_ok=True, grep=None):
    out = f'edge/{name}'; os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, '-I', S, '--ppto', 'Inputs/PptoTecnico2027.csv', '--subramo', '/nonexistent', '--salida', f'{out}/Red.csv', '--out-dir', out] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = (r.returncode == 0)
    txt = r.stdout + r.stderr
    status = 'OK' if ok == expect_ok else 'FALLO'
    extra = ''
    if grep:
        found = any(g in txt for g in grep)
        if not found: status = 'FALLO(msg)'
        extra = ' | esperado: ' + ' / '.join(grep)
    key = [l for l in txt.splitlines() if any(k in l for k in ['Alcance:', 'Movimientos', 'Controles:', 'ERROR', 'Error', 'Firmas con', 'Tolerancia sugerida', 'Sensibilidad', 'tendencia', 'CONTROL FALLIDO'])]
    print(f'[{status}] {name} (rc={r.returncode}, esperado_ok={expect_ok}){extra}')
    for l in key[:8]: print('     ', l[9:][:220] if l[:2].isdigit() else l[:220])
    if status.startswith('FALLO'): print(txt[-1500:])
    return txt
H = 'Inputs/Redistribucion/Hist_Real_LLAVE_Ramo.csv'; L = 'Inputs/Redistribucion/Layout_Redistribucion.xlsx'
# 1) base con split explícito NO ajustado por defecto -> 1-5-20 y 1-264-19(INCLUIR) : 1-5-20 debe quedar REVISAR
run('t01_base_default', ['--hist', H, '--layout', L])
# 2) histórico con separador de miles -> debe correr igual (thousands) o abortar con mensaje claro, nunca ceros silenciosos
h = pd.read_csv(H); h2 = h.copy(); h2['MONTO'] = h2['MONTO'].map(lambda v: f'{v:,.0f}'); h2.to_csv('edge/hist_miles.csv', index=False, quoting=1)
run('t02_hist_miles', ['--hist', 'edge/hist_miles.csv', '--layout', L, '--ajustar-split-explicito'])
# 3) histórico sin filas en años base -> error claro
run('t03_hist_anios_vacios', ['--hist', H, '--layout', L, '--anios-base', '2019'], expect_ok=False, grep=['años base', 'anios'])
# 4) layout con filas en blanco y LLAVE '4.0' y minúsculas
lay = pd.read_excel(L); blank = pd.DataFrame([{c: np.nan for c in lay.columns}]); lay2 = pd.concat([lay.iloc[:1], blank, lay.iloc[1:], blank], ignore_index=True)
lay2.loc[lay2['LLAVE']=='2-85-4-LN04001', 'LLAVE'] = '2-85-4.0-ln04001'; lay2.to_excel('edge/layout_blancos.xlsx', index=False)
run('t04_layout_blancos_40', ['--hist', H, '--layout', 'edge/layout_blancos.xlsx'])
# 5) FORZAR sin PESO_PRIMA -> error
pd.DataFrame([dict(LLAVE='2-85-4-LN04001', ACCION='FORZAR', RAMO=71, FUENTE='slip', JUSTIFICACION='x'), dict(LLAVE='2-85-4-LN04001', ACCION='FORZAR', RAMO=73, FUENTE='slip', JUSTIFICACION='x')]).to_excel('edge/layout_sinpeso.xlsx', index=False)
run('t05_forzar_sin_peso', ['--hist', H, '--layout', 'edge/layout_sinpeso.xlsx'], expect_ok=False, grep=['PESO_PRIMA'])
# 6) layout con LLAVE inexistente en ppto -> error
pd.DataFrame([dict(LLAVE='7-7777-7-LN04001', ACCION='EXCLUIR', JUSTIFICACION='x')]).to_excel('edge/layout_inexistente.xlsx', index=False)
run('t06_layout_llave_inexistente', ['--hist', H, '--layout', 'edge/layout_inexistente.xlsx'], expect_ok=False, grep=['no existen en el presupuesto'])
# 7) firmas con signos mixtos: inyectar reversos en 1-40-16 ramo 71 (fila positiva) y correr
b = pd.read_csv('Inputs/PptoTecnico2027.csv', thousands=','); m = (b['ZCEDENTE']==40)&(b['ZCONTRATO']==16)&(b['/ERP/PROFTCTR']=='A071000000')&(b['/ERP/GL_ACCT']==6108010000)&(b['0FISCYEAR']==2027)
rev = b[m].head(3).copy(); rev['/ERP/AMOUNT'] = [500.0, 1200.5, 77.25]; b2 = pd.concat([b, rev], ignore_index=True); b2.to_csv('edge/ppto_reversos.csv', index=False)
t = run('t07_signos_mixtos', ['--ppto', 'edge/ppto_reversos.csv', '--hist', H, '--layout', L])
d = pd.read_csv(sorted(glob.glob('edge/t07_signos_mixtos/Detalle_Filas_*.csv'))[-1])
x = d[(d['LLAVE']=='1-40-16-LN04001')&(d['SIGNO']==1)]
print('      reversos repartidos (signo +):', x[['POOL_ID','RAMO_NUEVO','AMOUNT_ORIG','AMOUNT_NUEVO','MOVIMIENTO']].to_string(index=False).replace('\n','\n      '))
# 8) histórico con año de reversa (signos opuestos en 2026) -> año excluido, peso del año válido
h3 = h.copy(); h3 = pd.concat([h3, pd.DataFrame([dict(ZTIPOREAS=1, ZCEDENTE=296, ZCONTRATO=6, FUNCAREA='LN04001', RAMO=71, ANIO=2026, GL=61, MONTO=+2000000), dict(ZTIPOREAS=1, ZCEDENTE=296, ZCONTRATO=6, FUNCAREA='LN04001', RAMO=73, ANIO=2026, GL=61, MONTO=-1000000)])], ignore_index=True)
h3.to_csv('edge/hist_reversa.csv', index=False)
run('t08_hist_anio_reversa', ['--hist', 'edge/hist_reversa.csv', '--layout', L])
pc = pd.read_excel(sorted(glob.glob('edge/t08_hist_anio_reversa/Trazabilidad_*.xlsx'))[-1], sheet_name='Pesos_Calculados')
print('      1-296-6:', pc[pc['LLAVE']=='1-296-6-LN04001'][['TIPO','RAMO','PESO','DETALLE','MOTIVO']].to_string(index=False).replace('\n','\n      '))
# 9) AMOUNT NaN -> error
b3 = b.copy(); b3.loc[5, '/ERP/AMOUNT'] = np.nan; b3.to_csv('edge/ppto_nan.csv', index=False)
run('t09_amount_nan', ['--ppto', 'edge/ppto_nan.csv', '--hist', H, '--layout', L], expect_ok=False, grep=['vacío'])
# 10) doble aplicación: usar la salida de t01 como entrada -> error por hash (mismo out-dir)
run('t10_doble_aplicacion', ['--ppto', 'edge/t01_base_default/Red.csv', '--hist', H, '--layout', L, '--out-dir', 'edge/t01_base_default'], expect_ok=False, grep=['idéntico (sha256)'])
# 11) reclasificación total: 1-32-71 (solo 71) con hist 100% 73 -> REVISAR por defecto, AJUSTAR con --reclasificacion-total auto
h4 = h[~((h['ZCEDENTE']==32)&(h['ZCONTRATO']==71))].copy(); esc32 = abs(float(b[(b['ZCEDENTE']==32)&(b['ZCONTRATO']==71)&(b['0FISCYEAR']==2027)&(b['/ERP/GL_ACCT']==6108010000)&(b['/ERP/PROFTCTR'].isin(['A071000000','A073000000']))]['/ERP/AMOUNT'].sum()))
h4 = pd.concat([h4, pd.DataFrame([dict(ZTIPOREAS=1, ZCEDENTE=32, ZCONTRATO=71, FUNCAREA='LN04001', RAMO=73, ANIO=2025, GL=61, MONTO=-round(esc32*0.9,2))])], ignore_index=True); h4.to_csv('edge/hist_recl.csv', index=False)
run('t11_recl_total_revisar', ['--hist', 'edge/hist_recl.csv', '--layout', L])
al = pd.read_excel(sorted(glob.glob('edge/t11_recl_total_revisar/Trazabilidad_*.xlsx'))[-1], sheet_name='Alcance_LLAVEs'); print('      1-32-71:', al[al['LLAVE']=='1-32-71-LN04001'][['DECISION','MOTIVO']].to_string(index=False))
run('t12_recl_total_auto', ['--hist', 'edge/hist_recl.csv', '--layout', L, '--reclasificacion-total', 'auto', '--no-revisar-sensibles'])
al = pd.read_excel(sorted(glob.glob('edge/t12_recl_total_auto/Trazabilidad_*.xlsx'))[-1], sheet_name='Alcance_LLAVEs'); print('      1-32-71:', al[al['LLAVE']=='1-32-71-LN04001'][['DECISION','MOTIVO']].to_string(index=False))
# 13) materialidad 1e9 -> nada se ajusta salvo layout
run('t13_materialidad', ['--hist', H, '--layout', L, '--materialidad', '1000000000'])
# 14) tabla de pesos con duplicados -> error
pa = pd.read_excel(sorted(glob.glob('edge/t01_base_default/Trazabilidad_*.xlsx'))[-1], sheet_name='Pesos_Aplicados')
dup = pd.concat([pa, pa.iloc[:1]]); 
with pd.ExcelWriter('edge/pesos_dup.xlsx', engine='openpyxl') as w: dup.to_excel(w, sheet_name='Pesos', index=False)
run('t14_pesos_duplicados', ['--hist', '/nonexistent', '--td', '/nonexistent', '--pesos', 'edge/pesos_dup.xlsx', '--layout', '/nonexistent'], expect_ok=False, grep=['repetidos'])
# 15) tabla de pesos congelada (ORIGEN_PESO respetado) -> mismo csv que t02? comparar shares
with pd.ExcelWriter('edge/pesos_ok.xlsx', engine='openpyxl') as w: pa.to_excel(w, sheet_name='Pesos', index=False)
run('t15_pesos_tabla', ['--hist', '/nonexistent', '--td', '/nonexistent', '--pesos', 'edge/pesos_ok.xlsx', '--layout', '/nonexistent'])
pa2 = pd.read_excel(sorted(glob.glob('edge/t15_pesos_tabla/Trazabilidad_*.xlsx'))[-1], sheet_name='Pesos_Aplicados'); print('      ORIGEN_PESO en tabla congelada:', pa2['ORIGEN_PESO'].value_counts().to_dict())
# 16) sobrescribir input con respaldo (copia del csv) y segunda corrida bloqueada por hash
shutil.copy('Inputs/PptoTecnico2027.csv', 'edge/ppto_sobre.csv')
run('t16_sobrescribir', ['--ppto', 'edge/ppto_sobre.csv', '--hist', H, '--layout', L, '--sobrescribir-input'])
print('      respaldo existe:', os.path.exists('edge/Backups') and sorted(os.listdir('edge/Backups')))
run('t16b_sobrescribir_2da', ['--ppto', 'edge/ppto_sobre.csv', '--hist', H, '--layout', L, '--sobrescribir-input', '--out-dir', 'edge/t16_sobrescribir'], expect_ok=False, grep=['idéntico (sha256)'])
# 17) conservar ceros + solo FY 2027 + comisiones prima + siniestros no + metodo ultimo
run('t17_variantes', ['--hist', H, '--layout', L, '--no-conservar-cero', '--anios-fiscales', '2027', '--comisiones', 'prima', '--siniestros', 'no', '--metodo-pesos', 'ultimo', '--ajustar-split-explicito'])
# 18) sin ZREGIONRP (columna eliminada) -> debe correr (región opcional en controles)
b4 = b.drop(columns=['ZREGIONRP']); b4.to_csv('edge/ppto_sinreg.csv', index=False)
run('t18_sin_zregionrp', ['--ppto', 'edge/ppto_sinreg.csv', '--hist', H, '--layout', L])
# 19) dry-run
run('t19_dry_run', ['--hist', H, '--layout', L, '--dry-run'])

# 20) fila original con monto 0 dentro de una LLAVE AJUSTAR -> debe correr y conservar la fila
b5 = b.copy(); z = b5[(b5['ZCEDENTE']==181)&(b5['ZCONTRATO']==1)&(b5['/ERP/PROFTCTR']=='A071000000')&(b5['/ERP/GL_ACCT']==6108010000)&(b5['0FISCYEAR']==2027)].head(1).copy()
z['/ERP/AMOUNT'] = 0.0; z['0CALMONTH'] = 202701; b5 = pd.concat([b5, z], ignore_index=True); b5.to_csv('edge/ppto_cero.csv', index=False)
run('t20_fila_cero_en_alcance', ['--ppto', 'edge/ppto_cero.csv', '--hist', H, '--layout', L])
# 21) --salida igual al insumo sin --sobrescribir-input -> error
run('t21_salida_igual_ppto', ['--ppto', 'edge/ppto_cero.csv', '--hist', H, '--layout', L, '--salida', 'edge/ppto_cero.csv'], expect_ok=False, grep=['sobrescribir-input'])
# 22) INCLUIR sin justificación -> error
pd.DataFrame([dict(LLAVE='1-264-19-LN04001', ACCION='INCLUIR', JUSTIFICACION='')]).to_excel('edge/layout_incluir_sinjust.xlsx', index=False)
run('t22_incluir_sin_justificacion', ['--hist', H, '--layout', 'edge/layout_incluir_sinjust.xlsx'], expect_ok=False, grep=['JUSTIFICACION'])
# 23) Subramo sintético con Ramo2 y CeBe faltante para el clon -> error bloqueante
pd.DataFrame([dict(CeBe='A071000000', Ramo=71, Ramo2=71, RamoN='HyORH'), dict(CeBe='A060000000', Ramo=60, Ramo2=60, RamoN='Incendio')]).to_csv('edge/subramo_sin73.csv', index=False)
run('t23_subramo_sin_cebe_clon', ['--hist', H, '--layout', L, '--subramo', 'edge/subramo_sin73.csv'], expect_ok=False, grep=['no existen en Subramo.csv'])
pd.DataFrame([dict(CeBe='A071000000', Ramo=71, Ramo2=71, RamoN='HyORH'), dict(CeBe='A073000000', Ramo=73, Ramo2=73, RamoN='Terremoto'), dict(CeBe='A060000000', Ramo=60, Ramo2=60, RamoN='Incendio')]).to_csv('edge/subramo_ok.csv', index=False)
run('t24_subramo_ok', ['--hist', H, '--layout', L, '--subramo', 'edge/subramo_ok.csv'])
