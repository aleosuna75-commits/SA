#RESERVA SONR - version con los insumos de la BD proyectada (proyeccion_reservas.py)
#   Cambios respecto a ReforecastSONR_v3.py (marcados con "### INSUMOS BD"):
#   - ParamSONR (Ind Sin SONR Media / 99.5%, LAG 1 a 10 y Factor_Ret por mes y ramo) sale de la BD: HParametros Real +
#     Proyección, IS (FA) en los ramos indicados en los meses proyectados y Factor_Ret = 1 - IRR / BEL de la BD.
#   - El TC USD de la columna TC de la BD en los meses sin TC en la base; el escenario 0 de los montos reales de
#     diciembre anterior de la BD; los meses que el script no valua del escenario 3, de los saldos proyectados de la BD
#     (config MESES_FALTANTES_ESC3).
#   - El ano y mes de valuacion se toman del ultimo mes real de la BD; rutas, base Access y parametros del margen de
#     riesgo en config_local.py. La logica de valuacion (consultas, FND, metodo propio) no cambia.
#%% LIBRERÍAS
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from insumos_bd import InsumosBD, mes_mas, RAMOS_SONR       ### INSUMOS BD
try:
    import config_local as cfg                               ### INSUMOS BD: rutas y parametros locales
except ImportError:
    raise SystemExit("Falta config_local.py junto al script: copia config_local.ejemplo.py como config_local.py y "
                     "pon tus rutas y parametros")
try:
    import pyodbc
except ImportError:                                          # (sin Access: el TC USD sale de la BD; las consultas fallan)
    pyodbc = None
warnings.filterwarnings('ignore')

CONN_STR = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + str(cfg.ACCESS_DBQ) + ';'   ### INSUMOS BD
Path(cfg.CARPETA_SALIDA).mkdir(parents=True, exist_ok=True)


def _guardar(df, nombre):                                    ### INSUMOS BD: consultas intermedias, solo si se pide
    if getattr(cfg, "GUARDAR_INTERMEDIOS", False):
        df.to_excel(Path(cfg.CARPETA_SALIDA) / nombre, index=False)


def _normalizar_ppto(df):                                    ### INSUMOS BD: el CSV del presupuesto puede traer los
    ren = {}                                                 # nombres de BW ("/ERP/GL_ACCT", "0CALMONTH", "/ERP/AMOUNT")
    for c in df.columns:
        base = str(c).strip()
        if base.startswith("/ERP/"):
            base = base[5:]
        elif base.startswith("0") and base[1:2].isalpha():
            base = base[1:]
        ren[c] = base
    return df.rename(columns=ren)


def _csv_opcional(ruta):                                     ### INSUMOS BD: CSV auxiliares que pueden no estar
    ruta = Path(ruta)
    return pd.read_csv(ruta) if ruta.exists() else None


#%% INSUMOS DE LA BD PROYECTADA                              ### INSUMOS BD
print('Leyendo la BD proyectada ...')
INS = InsumosBD(cfg.RUTA_BD, getattr(cfg, "RUTA_DIAGNOSTICO", None), usar_is_fa=getattr(cfg, "USAR_IS_FA", True),
                ramos_is_fa=getattr(cfg, "RAMOS_IS_FA", None))
zAño = cfg.ANIO or INS.anio                                  # ano de valuacion = el del ultimo mes real de la BD
zAñoPpto = zAño
zMes = cfg.MES or INS.mes                                    # ultimo mes real
print(f'Valuacion {zAño}, meses reales 1 a {zMes}')
_MR = cfg.MR_SONR
if any(v is None for v in _MR.values()):
    raise SystemExit("config_local.MR_SONR trae valores vacios: pon los parametros del margen de riesgo (BC y BC2)")

#%% INPUTS (archivos del area que la BD no trae)
xFolder = str(cfg.CSV_AUXILIARES_SONR)
xAjManuales = _csv_opcional(os.path.join(xFolder, "AjManuales_SONR.csv"))
if xAjManuales is None:
    xAjManuales = pd.DataFrame()
    print('   Sin AjManuales_SONR.csv: la consulta va sin ajustes manuales')

#### PPTO
xSubramo = pd.read_csv(os.path.join(xFolder, "Subramo.csv"))

####Mensual
Tbase_mp = _csv_opcional(os.path.join(xFolder, "TablaBase_MetodoPropio.csv"))
if Tbase_mp is None:                                         ### INSUMOS BD: la tabla base es ramo x LAG 1..10
    Tbase_mp = pd.DataFrame([{"Ramo": r, "NoLAG": k} for r in RAMOS_SONR for k in range(1, 11)])
    print('   Sin TablaBase_MetodoPropio.csv: se arma con los ramos de SONR de la BD y LAG 1 a 10')
ParamSONR = INS.param_sonr(csv_param_sonr=getattr(cfg, "CSV_PARAM_SONR", None),      ### INSUMOS BD: IS, LAGs y
                           ramos_factor_ret_csv=tuple(getattr(cfg, "RAMOS_FACTOR_RET_CSV", ()) or ()))  # Factor_Ret de la BD
### INSUMOS BD: escenario 0 (ano base) de la BD y, si existe el CSV, los renglones del escenario 1 (presupuesto)
xEsc_base = INS.escenario_base("SONR", zAño)
_ruta_esc = (getattr(cfg, "ESCENARIO_BASE_CSV", None) or {}).get("SONR")
if _ruta_esc and Path(_ruta_esc).exists():
    _csv = pd.read_csv(_ruta_esc)
    _csv = _csv[_csv["Escenario"] == 1] if "Escenario" in _csv.columns else _csv.iloc[0:0]
    xEsc_base = pd.concat([xEsc_base, _csv], ignore_index=True)
    print(f'   Escenario 1 (presupuesto): {len(_csv)} renglones de {Path(_ruta_esc).name}')
else:
    print('   Sin Escenario_base_SONR.csv: el escenario 1 (presupuesto) no se incluye')

#%% DICCIONARIOS
### INSUMOS BD: los meses hacia atras se calculan con mes_mas (antes, un diccionario fijo del ano de valuacion); el TC
### del escenario base sale de la BD (real hasta el ultimo mes y pronostico despues)
xTC_PPTO = INS.tc_dict()

xEscenario = {"BEL_RIESGO":["BEL", 2],
        "IRR":["IRR",2],
        f"IRR{zAño}_TCVal":["IRR",2],
        "MR":["MR",2],
        "BRUTO":["BRUTO",2],
        "NETO":["NETO",2]}


#%% FUNCIÓN FND REAL.
def zFND(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia):
    mes_proc_str = str(xMesProc)
    right_3 = mes_proc_str[-3:] if len(mes_proc_str) >= 3 else mes_proc_str

    def safe_yyyymm_to_date(yyyymm):
        if isinstance(yyyymm, (datetime, pd.Timestamp)):
            return yyyymm
        try:
            if isinstance(yyyymm, (int, float)):
                yyyymm = int(yyyymm)
                year = yyyymm // 100
                month = yyyymm % 100
                if 1 <= month <= 12:
                    return datetime(year=year, month=month, day=1)
            return None  
        except:
            return None
   
    #xIniVig = safe_yyyymm_to_date(xIniVig)
    #xFinVig = safe_yyyymm_to_date(xFinVig) 
    
    if xIniVig == xFinVig: 
        current_ym = xFecVal.year * 100 + xFecVal.month
        if xMesProc < current_ym:
            return 0
        else:
            return 1
    else:
        if xTipoRea == 2: 
            current_ym = xFecVal.year * 100 + xFecVal.month
            if xAñoMes == current_ym:
                return 0
            else:
                if xFinVig == cfg.FINVIG_AJUSTE_MANUAL: #### AJUSTE HECHO PARA LOS AJUSTES MANUALES QUE REGRESAN VALORES QUE GENERAN ERROR PARA SACAR EL RATIO
                    return 0
                else:
                    ratio = (xFinVig - xFecVal) / (xFinVig - xIniVig)
                    return max(min(ratio, 1), 0)
        else:
            prev_year_ym = (xFecVal.year - 1) * 100 + xFecVal.month
            if xMesProc <= prev_year_ym:
                return 0
            else:
                result = xPND.get(xMesProc,0).get(str(xFrecuencia), 0) 
                return result

#%% FUNCIÓN FND PPTO
def zFND_PPTO(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia):
    fecha = datetime(zAño, 12, 31)
    #print(xMesProc)
    #print(xFecVal)
    
    if xIniVig == xFinVig: 
        if xMesProc <= (xFecVal.year -1) * 100 + xFecVal.month:
            return 0
        elif xMesProc >= (xFecVal.year) * 100 + xFecVal.month:
            return 1
        else:
            if fecha <= xFecVal:
                xVal = int(xMesProc)
            else:
                nMes = int(xMesProc) - (zAño * 100)
                if xFecVal.month < nMes:
                    xVal = mes_mas(int(xMesProc), -xFecVal.month)            ### INSUMOS BD (antes, diccionario fijo)
                else:
                    xVal = mes_mas(int(xMesProc), -xFecVal.month + 12)
            result = xPND.get(xVal,0).get(str(xFrecuencia), 0) 
            return result
    else:
        if xTipoRea == 2: 
            if xAñoMes == (xFecVal.year) * 100 + xFecVal.month:
                return 0
            else:
                ratio = (xFinVig - xFecVal) / (xFinVig - xIniVig)
                return max(min(ratio, 1), 0)
        else:
            if xMesProc <= (xFecVal.year) * 100 + xFecVal.month:
                return 0
            else:
                if fecha <= xFecVal:
                    xVal = int(xMesProc)
                else:
                    nMes = int(xMesProc)
                    if xFecVal.month < nMes:
                        xVal = int(xMesProc) - xFecVal.month
                    else:
                        xVal = int(xMesProc) - xFecVal.month + 12
                result = xPND.get(xVal,0).get(str(xFrecuencia), 0) 
                return result

#%% zFND REAL REFORECAST
def zFND2(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia):
    mes_proc_str = str(int(xMesProc))
    if xIniVig == xFinVig: 
        current_ym = xFecVal.year * 100 + xFecVal.month
        if xMesProc < current_ym:
            return 0
        else:
            return 1
    else:
        if xTipoRea == 2: 
            current_ym = xFecVal.year * 100 + xFecVal.month
            if xAñoMes == current_ym:
                return 0
            else:
                if xFinVig == cfg.FINVIG_AJUSTE_MANUAL: #### AJUSTE HECHO PARA LOS AJUSTES MANUALES QUE REGRESAN VALORES NO USABLES PARA SACAR EL RATIO
                    return 0
                else:
                    ratio = (xFinVig - xFecVal) / (xFinVig - xIniVig)
                    return max(min(ratio, 1), 0)
        else:
            prev_year_ym = (xFecVal.year - 1) * 100 + xFecVal.month
            if xMesProc <= prev_year_ym:
                return 0
            else:
                zFechaPpto = pd.Timestamp(f'31/12/{zAñoPpto}')
                if zFechaPpto <= xFecVal:
                    xVal = int(xMesProc)
                else:
                    der_2 = mes_proc_str[-2:]
                    izq_4 = mes_proc_str[:4]
                    nMes = int(der_2)
                    nAño = int(izq_4)
                    if nAño < zAñoPpto:
                        if xFecVal.month < nMes:
                            xVal = int(xMesProc) - xFecVal.month + 100
                        else:
                            xVal = int(xMesProc) - xFecVal.month + 112
                    else:
                        if xFecVal.month < nMes:
                            xVal = int(xMesProc) - xFecVal.month
                        else:
                            xVal = xVal = int(xMesProc) - xFecVal.month + 12
                #print(xFecVal)
                #print(xAñoMes)
                #print(xMesProc)
                #print(xVal)
                #print(xPND)
                result = xPND.get(xVal,0).get(str(xFrecuencia), 0) 
                return result
#%% FUNCIÓN CONSULTA TC USD.
def ConsultaMoneda_usd():
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()

    xSelect = " Select cTCAD_FecAMD, cTCAD_Mnt "
    xTabla = " From dbo_aMOT_MovTipCambio "
    xWhere = " Where cMON_Id = 31"
    xGroup = ""
    xOrder = ""

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xOrder])

    ConsultaTC_USD = pd.read_sql(xSQL, conn)
    conn.close()


    return(ConsultaTC_USD)

### INSUMOS BD: el TC USD de la base hasta el ultimo mes real; los meses siguientes (hasta el fin de la proyeccion) con
### el TC de la BD (pronostico)
if pyodbc is not None:
    TC_USD = ConsultaMoneda_usd()
    TC_USD = TC_USD[TC_USD['cTCAD_FecAMD'] <= zAño * 100 + zMes]
else:
    TC_USD = INS.tc_tabla().iloc[0:0]
_ult_tc = int(TC_USD['cTCAD_FecAMD'].max()) if len(TC_USD) else 0
_tc_bd = INS.tc_tabla()
TC_USD = pd.concat([TC_USD, _tc_bd[_tc_bd['cTCAD_FecAMD'] > _ult_tc]], ignore_index=True)
TC_USD = TC_USD.sort_values('cTCAD_FecAMD').reset_index(drop=True)
ConsultaTC_usd = TC_USD
print(f'   TC USD: base hasta {_ult_tc}; de la BD, {int((_tc_bd["cTCAD_FecAMD"] > _ult_tc).sum())} meses')
_guardar(TC_USD, "TablaTCSONR.xlsx")


#%% FUNCIÓN CONSULTA MONEDA.
def ConsultaMoneda():
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()

    xSelect = "Select *, (cTCAD_FecAMD & '-' & cMON_Id) as Llave "
    xTabla = "From dbo_aMOT_MovTipCambio "
    xWhere = ""
    xGroup = ""
    xOrder = ""

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xOrder])

    ConsultaTC = pd.read_sql(xSQL, conn)
    ConsultaTC_Temporal = ConsultaTC
    conn.close()

    
    #ConsultaTC['Anio_ant'] = ConsultaTC.apply(lambda row: row['cTCAD_FecAMD'] - 100, axis = 1)
    ConsultaTC['Anio_ant'] = (zAño-1)*100+12
    ConsultaTC['Llave_ant'] = ConsultaTC[['Anio_ant', 'cMON_Id']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    ConsultaTC = ConsultaTC.merge(ConsultaTC_Temporal[["Llave","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Llave_ant", right_on="Llave")
    ConsultaTC = ConsultaTC.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="cTCAD_FecAMD", right_on="cTCAD_FecAMD")
    ConsultaTC['TC_USD'] = ConsultaTC.apply(lambda row: (row['cTCAD_Mnt_x'] /  row['cTCAD_Mnt']) if row['cTCAD_Mnt'] != 0 else 0, axis = 1)
    return(ConsultaTC)

ConsultaTC = ConsultaMoneda()

#%% FUNCIÓN SUMARSI
def calcular_tbase_mp(row, df_consulta):
    # Filtramos el dataframe de consulta según las condiciones
    mask = (
        (ConsultaR['AñoMes'] > row['Fecha Inicio']) &
        (ConsultaR['AñoMes'] <= row['Fecha Fin']) &
        (ConsultaR['Ramo_filt'] == row['Ramo'])  
    )
    
    # Sumamos los valores de la columna T que cumplen las condiciones
    suma = df_consulta.loc[mask, f'PrimaDev_{Meses}_Val'].sum()
    
    
    return suma

def calcular_tbase_mp_rf_real(row, df_consulta):
    # Filtramos el dataframe de consulta según las condiciones
    mask = (
        (ConsultaR_USD['AñoMes'] > row['Fecha Inicio']) & 
        (ConsultaR_USD['AñoMes'] <= row['Fecha Fin']) &  
        (ConsultaR_USD['Ramo_filt'] == row['Ramo'])   
    )
    añomes = row['AñoMes']
    # Sumamos los valores de la columna T que cumplen las condiciones
    suma = df_consulta.loc[mask, f'PrimaDev_{añomes}_Val'].sum()

    return suma

def calcular_tbase_mp_rf_ppto(row, df_consulta):
    # Filtramos el dataframe de consulta según las condiciones
    mask = (
        (ConsultaPPTO['AñoMes'] > row['Fecha Inicio']) &
        (ConsultaPPTO['AñoMes'] <= row['Fecha Fin']) & 
        (ConsultaPPTO['Ramo'] == row['Ramo'])    
    )
    añomes = row['AñoMes']
    # Sumamos los valores de la columna T que cumplen las condiciones
    suma = df_consulta.loc[mask, f'PrimaDev_{añomes}_Val'].sum()
    return suma
#%% FUNCIÓN CONSULTA PARA SONR REAL
def ConsultaReal(MES, FECVAL, AÑOMES):
    zInicio = (zAño - 10) * 100 + MES
    zFin = zAño * 100 + MES
    #print(FECVAL)
    #print(zInicio)
    #print(zFin)
    
    # Conexión y consulta BD Gonz
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    xSelect = "Select Val(aPog_MesProc) AS CALMONTH, iif(Sramo in (30,31,32,33), 31, iif(Sramo in (34,35,36), 35, iif(Sramo in (37,38,39), 39, Ramo))) As Ramo_filt, Pais, TipoRea, CorrTom, CiaTom, CtoTom, Susc, MonedaOri, IniVig, FinVig, " \
              "Período as Periodo, -Sum(Val(PriTomOri5) + Val(PriTomEnCOri5) + Val(PriTomReCOri5)) As PmaTomOri, " \
              "-Sum(Val(PriTomNal5) + Val(PriTomEnCNal5) + Val(PriTomReCNal5)) As PmaTomNal "
    
    xTabla = "From dbo_aMOG_MovGonzalo "

    xWhere = f" Where Tipo = 5 and Ramo <> 70 and Período <> 9 And Val(aPog_MesProc) >= {zInicio} And Val(aPog_MesProc) <= {zFin} " #\
               # f"and (aPOG_MesProc & '-' & cNAT_IdTPol & '-' & TipoRea & '-' & aPOG_Num not in ('{zLlavesPol}') ) "

    xGroup = " Group By Val(aPog_MesProc), iif(Sramo in (30,31,32,33), 31, iif(Sramo in (34,35,36), 35, iif(Sramo in (37,38,39), 39, Ramo))), Pais, TipoRea, CorrTom, CiaTom, CtoTom, Susc, MonedaOri, IniVig, FinVig, Período "
    xHaving = " Having -Sum(Val(PriTomOri5) + Val(PriTomEnCOri5) + Val(PriTomReCOri5)) <> 0 or  -Sum(Val(PriTomNal5) + Val(PriTomEnCNal5) + Val(PriTomReCNal5)) <> 0 "
    xOrder = " Order By Val(aPog_MesProc), iif(Sramo in (30,31,32,33), 31, iif(Sramo in (34,35,36), 35, iif(Sramo in (37,38,39), 39, Ramo))), Pais, TipoRea, Susc, MonedaOri "

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xHaving, xOrder])

    tMovGG = pd.read_sql(xSQL, conn)
    conn.close()
    
    ConsultaR = pd.concat([tMovGG,xAjManuales]) 
    #ConsultaR = tMovGG

    ConsultaR['AñoMes'] = ConsultaR.apply(lambda row: row['Susc'] * 100 + int(str(int(row['CALMONTH']))[-2:]), axis=1) 
    
    ConsultaR['Frecuencia'] = ConsultaR.apply(lambda row: row['Periodo'] if (row['TipoRea'] == 1 and row['Ramo_filt'] != 70 and row['Ramo_filt'] != 100) else ('NA' if pd.notna(row['Periodo']) else 'DEF'), axis=1)
    ConsultaR[['IniVig', 'FinVig']] = ConsultaR[['IniVig', 'FinVig']].fillna(0)
    ConsultaR[f'FND_{AÑOMES}'] = ConsultaR.apply(lambda y: zFND(y['IniVig'], y['FinVig'], y['TipoRea'], y['AñoMes'], FECVAL, y['CALMONTH'], y['Frecuencia']), axis=1)
    
    #ConsultaR[f'FND_{Meses}'] = ConsultaR.apply(lambda y: zFNDmes(y['IniVig'], y['FinVig'], y['TipoRea'], y['Susc'], zFechaValuacion, y['CALMONTH'], y['Frecuencia'], xPNDmes, xFrecCol), axis=1)
    ConsultaR[f'Dev_{AÑOMES}'] = ConsultaR.apply(lambda row: 1 - row[f'FND_{AÑOMES}'] , axis=1)
    #MERGE PARA TC
    ConsultaR['LLAVE_TC'] = f'{AÑOMES}-' + ConsultaR['MonedaOri'].astype('str')
    ConsultaR = ConsultaR.merge(ConsultaTC[["Llave_x","cTCAD_Mnt_x","cTCAD_Mnt_y"]].drop_duplicates(),
                             how="left", left_on="LLAVE_TC", right_on="Llave_x")        
    ConsultaR[f'PrimaDev_{AÑOMES}_Val'] = ConsultaR.apply(lambda row: row['PmaTomOri'] * row['cTCAD_Mnt_x'] * row[f'Dev_{AÑOMES}'], axis=1)
    ConsultaR[f'PrimaDev_{AÑOMES}_AñoAnt'] = ConsultaR.apply(lambda row: row['PmaTomOri'] * row['cTCAD_Mnt_y'] * row[f'Dev_{AÑOMES}'], axis=1)
    

    return(ConsultaR)

#%% FUNCIÓN CONSULTA PARA SONR REAL USD
def ConsultaReal_USD(MES, FECVAL, AÑOMES):
    zInicio = (zAño - 10) * 100 + MES + 1
    zFin = zAño * 100 + MES
    
    # Conexión y consulta BD Gonz
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    xSelect = "Select Val(aPog_MesProc) AS CALMONTH, iif(Sramo in (30,31,32,33), 31, iif(Sramo in (34,35,36), 35, iif(Sramo in (37,38,39), 39, Ramo))) As Ramo_filt, Pais, TipoRea, CorrTom, CiaTom, CtoTom, Susc, MonedaOri, IniVig, FinVig, " \
              "Período as Periodo, -Sum(Val(PriTomOri5) + Val(PriTomEnCOri5) + Val(PriTomReCOri5)) As PmaTomOri, " \
              "-Sum(Val(PriTomNal5) + Val(PriTomEnCNal5) + Val(PriTomReCNal5)) As PmaTomNal "
    
    xTabla = "From dbo_aMOG_MovGonzalo "

    xWhere = f" Where Tipo = 5 and Ramo <> 70 and Período <> 9 And Val(aPog_MesProc) >= {zInicio} And Val(aPog_MesProc) <= {zFin} " 

    xGroup = " Group By Val(aPog_MesProc), iif(Sramo in (30,31,32,33), 31, iif(Sramo in (34,35,36), 35, iif(Sramo in (37,38,39), 39, Ramo))), Pais, TipoRea, CorrTom, CiaTom, CtoTom, Susc, MonedaOri, IniVig, FinVig, Período "
    xHaving = " Having -Sum(Val(PriTomOri5) + Val(PriTomEnCOri5) + Val(PriTomReCOri5)) <> 0 or  -Sum(Val(PriTomNal5) + Val(PriTomEnCNal5) + Val(PriTomReCNal5)) <> 0 "
    xOrder = " Order By Val(aPog_MesProc), iif(Sramo in (30,31,32,33), 31, iif(Sramo in (34,35,36), 35, iif(Sramo in (37,38,39), 39, Ramo))), Pais, TipoRea, Susc, MonedaOri "

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xHaving, xOrder])

    tMovGG = pd.read_sql(xSQL, conn)
    conn.close()
    
    ConsultaR = tMovGG
    
    ConsultaR['AñoMes'] = ConsultaR.apply(lambda row: row['Susc'] * 100 + int(str(int(row['CALMONTH']))[-2:]), axis=1) 
    
    ConsultaR['Frecuencia'] = ConsultaR.apply(lambda row: row['Periodo'] if (row['TipoRea'] == 1 and row['Ramo_filt'] != 70 and row['Ramo_filt'] != 100) else ('NA' if pd.notna(row['Periodo']) else 'DEF'), axis=1)
    ConsultaR[['IniVig', 'FinVig']] = ConsultaR[['IniVig', 'FinVig']].fillna(0)

    ConsultaR['LLAVE_TC'] = f'{AÑOMES}-' + ConsultaR['MonedaOri'].astype('str')
    ConsultaR = ConsultaR.merge(ConsultaTC[["Llave_x", "cTCAD_Mnt_x", "cTCAD_Mnt_y", "TC_USD"]].drop_duplicates(),
                             how="left", left_on="LLAVE_TC", right_on="Llave_x")      
    ConsultaR[f'PmaTomUSD'] = ConsultaR.apply(lambda row: row['PmaTomOri'] * row['TC_USD'], axis=1)

    for mes in range(5):
  
        zFechaValuacion = f'31/12/{zAño + mes}'
        zFechaValuacion = pd.Timestamp(zFechaValuacion)
        ConsultaR[f'FND_{zAño + mes}12'] = ConsultaR.apply(lambda y: zFND2(y['IniVig'], y['FinVig'], y['TipoRea'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia']), axis=1)
        ConsultaR[f'Dev_{zAño + mes}12'] = ConsultaR.apply(lambda row: 1 - row[f'FND_{zAño + mes}12'] , axis=1)
        ConsultaR[f'PrimaDev_{zAño + mes}12_Val'] = ConsultaR.apply(lambda row: row['PmaTomUSD'] * row[f'Dev_{zAño + mes}12'], axis=1)


    for mes in range(11):
        mes_calculo = mes + 1
        if mes_calculo < 10:
            AuxMes = 0
        else:
            AuxMes= ""

        if mes_calculo == 2:
            dia = 28
        elif mes_calculo in [1,3,5,7,8,10,12]:
            dia = 31
        else:
            dia = 30
        
        zFechaValuacion = f'{dia}/{AuxMes}{mes_calculo}/{zAño}'
        zFechaValuacion = pd.Timestamp(zFechaValuacion)
        ConsultaR[f'FND_{zAño}{AuxMes}{mes_calculo}'] = ConsultaR.apply(lambda y: zFND2(y['IniVig'], y['FinVig'], y['TipoRea'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia']), axis=1)
        ConsultaR[f'Dev_{zAño}{AuxMes}{mes_calculo}'] = ConsultaR.apply(lambda row: 1 - row[f'FND_{zAño}{AuxMes}{mes_calculo}'] , axis=1)
        ConsultaR[f'PrimaDev_{zAño}{AuxMes}{mes_calculo}_Val'] = ConsultaR.apply(lambda row: row['PmaTomOri'] * row['TC_USD'] * row[f'Dev_{zAño}{AuxMes}{mes_calculo}'], axis=1)

    return(ConsultaR)


#%% FUNCIÓN MÉTODO PROPIO
def Metodo_propio():
    global Tbase_mp, ConsultaR
    BC = _MR["BC"]                                           ### INSUMOS BD: parametros del MR de config_local
    BC2 = _MR["BC2"]
    Tbase_mp_ = Tbase_mp
    Tbase_mp_['Año'] = zAño
    Tbase_mp_['AñoMes'] = Meses
    Tbase_mp_['AñoSusc'] = Tbase_mp_.apply(lambda row: row['Año'] + 1 - row['NoLAG'], axis=1) 
    Tbase_mp_['Fecha Inicio'] = Tbase_mp_.apply(lambda row: (row['Año']-row['NoLAG'])*100 + mes_calculo, axis=1)
    Tbase_mp_['Fecha Fin'] = Tbase_mp_.apply(lambda row: row['Fecha Inicio'] + 100, axis=1)
    Tbase_mp_['Llave'] = Tbase_mp_[['AñoMes', 'Ramo']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    Tbase_mp_ = Tbase_mp_.merge(ParamSONR[["Llave","Factor_Ret","Ind Sin SONR Media","Ind Sin SONR 99.5%", "LAG 1", "LAG 2", "LAG 3", "LAG 4", "LAG 5", "LAG 6", "LAG 7", "LAG 8", "LAG 9", "LAG 10"]].drop_duplicates(),
                             how="left", left_on="Llave", right_on="Llave")
    Tbase_mp_['Llave_lag'] = f'LAG ' + Tbase_mp_['NoLAG'].astype('str')
    Tbase_mp_['LAG'] = Tbase_mp_.apply(lambda row: 1 - row[str(row['Llave_lag'])], axis=1) 
    #Tbase_mp_['LAG'] = Tbase_mp_.apply(lambda row: 0 if row['LAG'] < 0 else row['LAG'], axis=1) 
    Tbase_mp_['Prima Dev'] = Tbase_mp_.apply(calcular_tbase_mp, args=(ConsultaR,), axis=1)
    Tbase_mp_['BEL_RIESGO'] = Tbase_mp_.apply(lambda row: row['Prima Dev'] * row['LAG'] * row['Ind Sin SONR Media'], axis=1)
    Tbase_mp_['IRR'] = Tbase_mp_.apply(lambda row: row['BEL_RIESGO'] * (1-row['Factor_Ret']), axis=1)
    Tbase_mp_['Desviacion'] = Tbase_mp_.apply(lambda row: row['Prima Dev'] * row['LAG'] * (row['Ind Sin SONR 99.5%']-row['Ind Sin SONR Media']), axis=1)
    ####MERGE BASE DE CAPITAL (Archivo MR y desviaciones para RRC y SONR)
    Tbase_mp_['MR'] = Tbase_mp_.apply(lambda row: (row['Desviacion'] / -BC) * BC2, axis=1)

    

    return Tbase_mp_

#%% FUNCIÓN CONSULTA PARA SONR PPTO
def ConsultaPresupuesto(MES):                                ### INSUMOS BD: (antes ConsultaPPTO<ano>; ConsultaPPTO es el DataFrame)
    
    ConsultaP = _normalizar_ppto(pd.read_csv(cfg.PPTO_TECNICO_SONR, thousands=','))    ### INSUMOS BD: ruta en config_local
    ConsultaPPTO = ConsultaP[(ConsultaP["GL_ACCT"] > 6101000000) & (ConsultaP["GL_ACCT"] < 6108999999) & (ConsultaP["CALMONTH"] >= (zAño*100 + MES + 1))]

    Columnas = ['CALMONTH', 'PROFTCTR', 'ZTIPOREAS', 'ZSUSCYEAR', 'AMOUNT']

    ConsultaPPTO = ConsultaPPTO[Columnas]
    ConsultaPPTO = ConsultaPPTO.groupby(['CALMONTH', 'PROFTCTR', 'ZTIPOREAS', 'ZSUSCYEAR'])['AMOUNT'].sum().reset_index()

    ConsultaPPTO= ConsultaPPTO.merge(xSubramo[["CeBe","Ramo", "Ramo2"]].drop_duplicates(),
                             how="left", left_on="PROFTCTR", right_on="CeBe")
    
    ConsultaPPTO['Periodo'] = 3
    ConsultaPPTO['AñoMes'] = ConsultaPPTO.apply(lambda row: row['ZSUSCYEAR'] * 100 + int(str(int(row['CALMONTH']))[-2:]), axis=1)
    ConsultaPPTO['Frecuencia'] = ConsultaPPTO.apply(lambda row: row['Periodo'] if (row['ZTIPOREAS'] == 1 or row['ZTIPOREAS'] == 3) and row['Ramo'] != 71 and row['Ramo'] != 73 and row['Ramo'] != 100 else 'NA', axis = 1)
    ConsultaPPTO['Frecuencia'] = ConsultaPPTO['Frecuencia'].fillna('DEF')

    #DICIEMRE AÑO PPTO Y CIERRE DE LOS SIG 4 AÑOS
    for mes in range(5):
  
        zFechaValuacion = f'31/12/{zAño + mes}'
        zFechaValuacion = pd.Timestamp(zFechaValuacion)
        ConsultaPPTO[f'FND_{zAño + mes}12'] = ConsultaPPTO.apply(lambda y: zFND_PPTO(0, 0, y['ZTIPOREAS'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia']), axis=1)
        ConsultaPPTO[f'Dev_{zAño + mes}12'] = ConsultaPPTO.apply(lambda row: 1 - row[f'FND_{zAño + mes}12'] , axis=1)
        ConsultaPPTO[f'PrimaDev_{zAño + mes}12_Val'] = ConsultaPPTO.apply(lambda row: -row['AMOUNT'] * row[f'Dev_{zAño + mes}12'], axis=1)

    #ENERO-NOVIEMBRE AÑO PPTO
    for mes in range(11):
        mes_calculo = mes + 1 
        if mes_calculo < 10:
            AuxMes = 0
        else:
            AuxMes= ""

        if mes_calculo == 2:
            dia = 28
        elif mes_calculo in [1,3,5,7,8,10,12]:
            dia = 31
        else:
            dia = 30
        
        zFechaValuacion = f'{dia}/{AuxMes}{mes_calculo}/{zAño}'
        zFechaValuacion = pd.Timestamp(zFechaValuacion)
        ConsultaPPTO[f'FND_{zAño}{AuxMes}{mes_calculo}'] = ConsultaPPTO.apply(lambda y: zFND_PPTO(0, 0, y['ZTIPOREAS'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia']), axis=1)
        ConsultaPPTO[f'Dev_{zAño}{AuxMes}{mes_calculo}'] = ConsultaPPTO.apply(lambda row: 1 - row[f'FND_{zAño}{AuxMes}{mes_calculo}'] , axis=1)
        ConsultaPPTO[f'PrimaDev_{zAño}{AuxMes}{mes_calculo}_Val'] = ConsultaPPTO.apply(lambda row: -row['AMOUNT'] * row[f'Dev_{zAño}{AuxMes}{mes_calculo}'], axis=1)
    
    
    return ConsultaPPTO

#%% FUNCIÓN MÉTODO PROPIO REFORECAST
def Metodo_propio_reforecast():
    global Tbase_mp, ConsultaR
    BC = _MR["BC"]                                           ### INSUMOS BD: parametros del MR de config_local
    BC2 = _MR["BC2"]
    Tbase_mp_0 = []
    for mes in range(12):
        Tbase_mp_ = Tbase_mp.copy()
        Tbase_mp_['Año'] = zAño  
        Tbase_mp_['AñoMes'] = zAño * 100 + mes + 1
        Tbase_mp_0.append(Tbase_mp_)

    Tbase_mp_f = pd.concat(Tbase_mp_0, ignore_index=True)
    #Tbase_mp_ext = Tbase_mp_ext.rename(columns={'Anio': 'Año', 'AnioMes': 'AñoMes'})
    #Tbase_mp_f = pd.concat([Tbase_mp_, Tbase_mp_ext], ignore_index=True)
    Tbase_mp_f['AñoSusc'] = Tbase_mp_f.apply(lambda row: row['Año'] + 1 - row['NoLAG'], axis=1) 
    Tbase_mp_f['Fecha Inicio'] = Tbase_mp_f.apply(lambda row: (row['Año']-row['NoLAG'])*100 + (row['AñoMes'] - zAño * 100), axis=1)
    Tbase_mp_f['Fecha Fin'] = Tbase_mp_f.apply(lambda row: row['Fecha Inicio'] + 100, axis=1)
    Tbase_mp_f['Llave'] = Tbase_mp_f[['AñoMes', 'Ramo']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    Tbase_mp_f = Tbase_mp_f.merge(ParamSONR[["Llave","Factor_Ret","Ind Sin SONR Media","Ind Sin SONR 99.5%", "LAG 1", "LAG 2", "LAG 3", "LAG 4", "LAG 5", "LAG 6", "LAG 7", "LAG 8", "LAG 9", "LAG 10"]].drop_duplicates(),
                             how="left", left_on="Llave", right_on="Llave")
    Tbase_mp_f['Llave_lag'] = f'LAG ' + Tbase_mp_f['NoLAG'].astype('str')
    Tbase_mp_f['LAG'] = Tbase_mp_f.apply(lambda row: 1 - row[str(row['Llave_lag'])], axis=1) 
    Tbase_mp_f['Prima Dev Real'] = Tbase_mp_f.apply(calcular_tbase_mp_rf_real, args=(ConsultaR_USD,), axis=1)
    Tbase_mp_f['Prima Dev PPTO'] = Tbase_mp_f.apply(calcular_tbase_mp_rf_ppto, args=(ConsultaPPTO,), axis=1)
    Tbase_mp_f['Prima Dev'] = Tbase_mp_f.apply(lambda row: row['Prima Dev Real'] + row['Prima Dev PPTO'], axis=1)
    Tbase_mp_f['BEL_RIESGO'] = Tbase_mp_f.apply(lambda row: row['Prima Dev'] * row['LAG'] * row['Ind Sin SONR Media'], axis=1)
    Tbase_mp_f['IRR'] = Tbase_mp_f.apply(lambda row: row['BEL_RIESGO'] * (1-row['Factor_Ret']), axis=1)
    Tbase_mp_f['Desviacion'] = Tbase_mp_f.apply(lambda row: row['Prima Dev'] * row['LAG'] * (row['Ind Sin SONR 99.5%']-row['Ind Sin SONR Media']), axis=1)
    ####MERGE BASE DE CAPITAL (Archivo MR y desviaciones para RRC y SONR)
    Tbase_mp_f['MR'] = Tbase_mp_f.apply(lambda row: (row['Desviacion'] / -BC) * BC2, axis=1)
    return Tbase_mp_f

def Metodo_propio_reforecast_dic():
    global Tbase_mp, ConsultaR
    BC = _MR["BC"]                                           ### INSUMOS BD: parametros del MR de config_local
    BC2 = _MR["BC2"]
    Tbase_mp_0 = []
    for mes in range(12):
        Tbase_mp_ = Tbase_mp.copy()
        Tbase_mp_['Año'] = zAño  
        Tbase_mp_['AñoMes'] = zAño * 100 + mes + 1
        Tbase_mp_0.append(Tbase_mp_)

    Tbase_mp_f = pd.concat(Tbase_mp_0, ignore_index=True)
    #Tbase_mp_ext = Tbase_mp_ext.rename(columns={'Anio': 'Año', 'AnioMes': 'AñoMes'})
    #Tbase_mp_f = pd.concat([Tbase_mp_, Tbase_mp_ext], ignore_index=True)
    Tbase_mp_f['AñoSusc'] = Tbase_mp_f.apply(lambda row: row['Año'] + 1 - row['NoLAG'], axis=1) 
    Tbase_mp_f['Fecha Inicio'] = Tbase_mp_f.apply(lambda row: (row['Año']-row['NoLAG'])*100 + (row['AñoMes'] - zAño * 100), axis=1)
    Tbase_mp_f['Fecha Fin'] = Tbase_mp_f.apply(lambda row: row['Fecha Inicio'] + 100, axis=1)
    Tbase_mp_f['Llave'] = Tbase_mp_f[['AñoMes', 'Ramo']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    Tbase_mp_f = Tbase_mp_f.merge(ParamSONR[["Llave","Factor_Ret","Ind Sin SONR Media","Ind Sin SONR 99.5%", "LAG 1", "LAG 2", "LAG 3", "LAG 4", "LAG 5", "LAG 6", "LAG 7", "LAG 8", "LAG 9", "LAG 10"]].drop_duplicates(),
                             how="left", left_on="Llave", right_on="Llave")
    Tbase_mp_f['Llave_lag'] = f'LAG ' + Tbase_mp_f['NoLAG'].astype('str')
    Tbase_mp_f['LAG'] = Tbase_mp_f.apply(lambda row: 1 - row[str(row['Llave_lag'])], axis=1) 
    Tbase_mp_f['Prima Dev Real'] = Tbase_mp_f.apply(calcular_tbase_mp_rf_real, args=(ConsultaR_USD,), axis=1)
    Tbase_mp_f['Prima Dev'] = Tbase_mp_f.apply(lambda row: row['Prima Dev Real'], axis=1)
    Tbase_mp_f['BEL_RIESGO'] = Tbase_mp_f.apply(lambda row: row['Prima Dev'] * row['LAG'] * row['Ind Sin SONR Media'], axis=1)
    Tbase_mp_f['IRR'] = Tbase_mp_f.apply(lambda row: row['BEL_RIESGO'] * (1-row['Factor_Ret']), axis=1)
    Tbase_mp_f['Desviacion'] = Tbase_mp_f.apply(lambda row: row['Prima Dev'] * row['LAG'] * (row['Ind Sin SONR 99.5%']-row['Ind Sin SONR Media']), axis=1)
    ####MERGE BASE DE CAPITAL (Archivo MR y desviaciones para RRC y SONR)
    Tbase_mp_f['MR'] = Tbase_mp_f.apply(lambda row: (row['Desviacion'] / -BC) * BC2, axis=1)
    return Tbase_mp_f


#%% ESCENARIO 0 Y 1
df = []
columnas_finales = ['Reserva', 'Escenario', 'Tipo de Monto','Ramo', 'Periodo', 'Monto_MXN', 'Monto_USD', 'TC']
xEsc_base = xEsc_base[columnas_finales]

xEsc_base['TC'] =  xEsc_base.apply(lambda row: INS.tc_de(int(row['Periodo'])),axis=1)   ### INSUMOS BD: TC de la BD
xEsc_base['Monto_MXN'] = xEsc_base.apply(lambda row: row['Monto_USD'] * row['TC'], axis = 1)
df.append(xEsc_base)
#%% ESCENARIO 2
#for mes in range(zMes):
for mes in range(zMes):
    mes_calculo = mes + 1
    if mes_calculo < 10:
        AuxMes = 0
    else:
        AuxMes= ""
    
    if mes_calculo == 2:
        dia = 28
    elif mes_calculo in [1,3,5,7,8,10,12]:
        dia = 31
    else:
        dia = 30

    zFechaValuacion = f'{dia}/{AuxMes}{mes_calculo}/{zAño}'
    zFechaValuacion = pd.Timestamp(zFechaValuacion)
    
    Meses = zAño * 100 + mes_calculo
    xPND = {
    mes_mas(Meses, -11): {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
    mes_mas(Meses, -10): {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
    mes_mas(Meses, -9): {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
    mes_mas(Meses, -8): {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
    mes_mas(Meses, -7): {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
    mes_mas(Meses, -6): {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
    mes_mas(Meses, -5): {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
    mes_mas(Meses, -4): {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
    mes_mas(Meses, -3): {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
    mes_mas(Meses, -2): {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
    mes_mas(Meses, -1): {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
    Meses: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
    (zAño + 1) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    (zAño + 2) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    (zAño + 3) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    (zAño + 4) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717}}
    
    

    ConsultaR = ConsultaReal(mes_calculo, zFechaValuacion, Meses)
    df_Real_IS_Real = Metodo_propio()
    #fileName = os.path.join(xFolder, "SONR_consulta_{mes_calculo}.xlsx")
    #ConsultaR.to_excel(fileName, index=False)
    #fileName = os.path.join(xFolder, "SONR_met_{mes_calculo}.xlsx")
    #df_Real_IS_Real.to_excel(fileName, index=False)
    #print(df_Real_IS_Real)
    #print(ConsultaR)
    xColumnas = ['Ramo', 'BEL_RIESGO', 'IRR', 'MR']
    df_SONR_dim = df_Real_IS_Real.reindex(columns=xColumnas)
    #print(df_SONR_dim)
    df_SONR_dim['BRUTO'] = df_SONR_dim.apply(lambda row: row['BEL_RIESGO'] + row['MR'], axis = 1)
    df_SONR_dim['NETO'] = df_SONR_dim.apply(lambda row: row['BRUTO'] - row['IRR'], axis = 1)

    df_SONR_dim['Reserva'] = 'SONR'
    df_SONR_dim['Periodo'] = f'{zAño}{AuxMes}{mes_calculo}'

    auxSONR = df_SONR_dim.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxSONR = auxSONR.reset_index()
    auxSONR.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    #######
    auxSONR_sum = auxSONR.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxSONR_sum['Tipo de Monto'] = auxSONR_sum['Origen'].apply(lambda x: xEscenario[x][0])
    auxSONR_sum['Escenario'] = auxSONR_sum['Origen'].apply(lambda x: xEscenario[x][1])
    auxSONR_sum['Periodo'] = auxSONR_sum['Periodo'].astype(int)

    auxSONR_sum= auxSONR_sum.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo", right_on="cTCAD_FecAMD")
    
    auxSONR_sum['Monto_MXN'] = auxSONR_sum['Monto']
    auxSONR_sum['Monto_USD'] = auxSONR_sum.apply(lambda row: row['Monto_MXN'] / row['cTCAD_Mnt'], axis = 1)

    xColumnas = ['Reserva', 'Ramo', 'Periodo', 'Tipo de Monto', 'Escenario',
                'Monto_MXN', 'Monto_USD']

    auxSONR_sum = auxSONR_sum.reindex(columns=xColumnas)
    df.append(auxSONR_sum)

#%% ESCENARIO 3
    xColumnas = ['Ramo', 'BEL_RIESGO', 'IRR', 'MR']
    df_SONR_dim_3 = df_Real_IS_Real.reindex(columns=xColumnas)
    df_SONR_dim_3['BRUTO'] = df_SONR_dim_3.apply(lambda row: row['BEL_RIESGO'] + row['MR'], axis = 1)
    df_SONR_dim_3['NETO'] = df_SONR_dim_3.apply(lambda row: row['BRUTO'] - row['IRR'], axis = 1)

    df_SONR_dim_3['Reserva'] = 'SONR'
    df_SONR_dim_3['Periodo'] = f'{zAño}{AuxMes}{mes_calculo}'

    auxSONR_3 = df_SONR_dim_3.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxSONR_3 = auxSONR_3.reset_index()
    auxSONR_3.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    #######
    auxSONR_sum_3 = auxSONR_3.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxSONR_sum_3['Tipo de Monto'] = auxSONR_sum_3['Origen'].apply(lambda x: xEscenario[x][0])

    ##### CONCATENACIÓN CON EL RESTO DEL AÑO
    Mesesppto = zAño*100 + zMes
    ### INSUMOS BD: los meses que el script no valua (despues del ultimo real) salen de los saldos proyectados de la
    ### BD (MESES_FALTANTES_ESC3 = "BD") o del presupuesto del CSV (escenario 1), como antes
    if str(getattr(cfg, "MESES_FALTANTES_ESC3", "BD")).upper() == "BD":
        Meses_falt_3 = INS.saldos_proyectados("SONR", mes_mas(Mesesppto, 1), zAño * 100 + 12, escenario=3)
    else:
        Meses_falt_3 = xEsc_base[(xEsc_base["Periodo"] > Mesesppto) & (xEsc_base["Escenario"] == 1)]
    auxSONR_sum_3 = pd.concat([auxSONR_sum_3,Meses_falt_3],axis=0)

    auxSONR_sum_3['Escenario'] = 3
    auxSONR_sum_3['Periodo'] = auxSONR_sum_3['Periodo'].astype(int)

    auxSONR_sum_3= auxSONR_sum_3.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo", right_on="cTCAD_FecAMD")

    AuxMesF = zAño * 100 + mes_calculo
    auxSONR_sum_3['TC'] = auxSONR_sum_3['cTCAD_Mnt']
    
    auxSONR_sum_3['Monto_MXN'] = auxSONR_sum_3.apply(lambda row: row['Monto_USD'] * row['TC'] if row['Periodo'] > AuxMesF else row['Monto'], axis = 1)
    auxSONR_sum_3['Monto_USD'] = auxSONR_sum_3.apply(lambda row: row['Monto_USD'] if row['Periodo'] > AuxMesF else row['Monto_MXN'] / row['TC'], axis = 1)
    

    xColumnas = ['Reserva', 'Ramo', 'Periodo', 'Tipo de Monto', 'Escenario',
                'Monto_MXN', 'Monto_USD', 'TC']

    auxSONR_sum_3 = auxSONR_sum_3.reindex(columns=xColumnas)
    df.append(auxSONR_sum_3)
#%% ESCENARIO 4
    Mesesr = zAño * 100 + 12
    xPND = {
    mes_mas(Mesesr, -11): {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
    mes_mas(Mesesr, -10): {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
    mes_mas(Mesesr, -9): {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
    mes_mas(Mesesr, -8): {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
    mes_mas(Mesesr, -7): {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
    mes_mas(Mesesr, -6): {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
    mes_mas(Mesesr, -5): {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
    mes_mas(Mesesr, -4): {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
    mes_mas(Mesesr, -3): {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
    mes_mas(Mesesr, -2): {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
    mes_mas(Mesesr, -1): {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
    Mesesr: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
    (zAño + 1) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    (zAño + 2) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    (zAño + 3) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    (zAño + 4) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717}}
    ConsultaR_USD = ConsultaReal_USD(mes_calculo, zFechaValuacion, Meses)
    _guardar(ConsultaR_USD, f"ConsultaR_USD{mes_calculo}_E4.xlsx")
    
    Mesesp = zAño * 100 + 12
    xPND = {
        mes_mas(Mesesp, -11): {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
        mes_mas(Mesesp, -10): {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
        mes_mas(Mesesp, -9): {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
        mes_mas(Mesesp, -8): {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
        mes_mas(Mesesp, -7): {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
        mes_mas(Mesesp, -6): {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
        mes_mas(Mesesp, -5): {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
        mes_mas(Mesesp, -4): {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
        mes_mas(Mesesp, -3): {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
        mes_mas(Mesesp, -2): {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
        mes_mas(Mesesp, -1): {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
        Mesesp: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
        (zAño + 1) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
        (zAño + 2) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
        (zAño + 3) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
        (zAño + 4) * 100 + 6: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717}}
    
    if mes_calculo == 12:
        df_reforecast = Metodo_propio_reforecast_dic()
    else:

        ConsultaPPTO = ConsultaPresupuesto(mes_calculo)
        df_reforecast = Metodo_propio_reforecast()
        _guardar(ConsultaPPTO, f"ConsultaPPTO{mes_calculo}_E4.xlsx")

    _guardar(df_reforecast, f"df_reforecast{mes_calculo}_E4.xlsx")

    df_reforecast = df_reforecast[(df_reforecast["AñoMes"] == zAño * 100 + 12)]

    xColumnas = ['Ramo', 'BEL_RIESGO', 'IRR', 'MR']
    df_SONR_dim = df_reforecast.reindex(columns=xColumnas)

    df_SONR_dim['BRUTO'] = df_SONR_dim.apply(lambda row: row['BEL_RIESGO'] + row['MR'], axis = 1)
    df_SONR_dim['NETO'] = df_SONR_dim.apply(lambda row: row['BRUTO'] - row['IRR'], axis = 1)

    df_SONR_dim['Reserva'] = 'SONR'
    df_SONR_dim['Periodo'] = f'{zAño}12-{mes_calculo}'


    auxSONR = df_SONR_dim.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxSONR = auxSONR.reset_index()
    auxSONR.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 
    
    #######
    auxSONR_sum = auxSONR.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxSONR_sum['Tipo de Monto'] = auxSONR_sum['Origen'].apply(lambda x: xEscenario[x][0])
    auxSONR_sum['Escenario'] = 4
    auxSONR_sum['Periodo2'] = zAño * 100 + 12

    auxSONR_sum= auxSONR_sum.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo2", right_on="cTCAD_FecAMD")
    
    auxSONR_sum['TC'] = auxSONR_sum['cTCAD_Mnt']
    auxSONR_sum['Monto_USD'] = auxSONR_sum['Monto']
    auxSONR_sum['Monto_MXN'] = auxSONR_sum.apply(lambda row: row['Monto_USD'] * row['cTCAD_Mnt'], axis = 1)

    xColumnas = ['Reserva', 'Ramo', 'Periodo', 'Tipo de Monto', 'Escenario',
                'Monto_MXN', 'Monto_USD']

    auxSONR_sum = auxSONR_sum.reindex(columns=xColumnas)

    df.append(auxSONR_sum)
    _guardar(auxSONR_sum, f"auxSONR_sum{mes_calculo}_E4.xlsx")



df_concatenado = pd.concat(df, ignore_index=True)
#df_concatenado = df_concatenado.drop(["cTCAD_FecAMD","cTCAD_Mnt"], axis=1)
df_concatenado = df_concatenado.drop_duplicates()

#Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'TC', 'Monto_USD']
Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'Monto_USD']
df_concatenado = df_concatenado[Columnas]

fileName = Path(cfg.CARPETA_SALIDA) / "SONR_esc.xlsx"              ### INSUMOS BD: salida en la carpeta local
df_concatenado.to_excel(fileName, index=False)
INS.exportar(Path(cfg.CARPETA_SALIDA) / "Parametros_usados_SONR.xlsx", zAño,
             csv_param_sonr=getattr(cfg, "CSV_PARAM_SONR", None),
             ramos_factor_ret_csv=tuple(getattr(cfg, "RAMOS_FACTOR_RET_CSV", ()) or ()))
print(f'Saldos en {fileName}; insumos usados en Parametros_usados_SONR.xlsx')
for _a in INS.avisos_texto():
    print('   AVISO:', _a)




