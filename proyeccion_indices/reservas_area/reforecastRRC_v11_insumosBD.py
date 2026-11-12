# -*- coding: utf-8 -*-
#RESERVA RRC - version con los insumos de la BD proyectada (proyeccion_reservas.py)
#   Cambios respecto a reforecastRRC_v10_Esc1_ocl.py (marcados con "### INSUMOS BD"):
#   - IS Bel Media / 99.5% e Ind. Gasto por mes salen de la BD (HParametros Real + Proyección, IS (FA) en los ramos
#     indicados y el bloque FACTOR GTO); IS_Cat (71 y 73) de TEV e Hidro de HParametros; el TC USD de la columna TC
#     de la BD en los meses sin TC en la base; el escenario 0 de los montos reales de diciembre anterior de la BD y los
#     meses que el script no valua del escenario 3, de los saldos proyectados de la BD (config MESES_FALTANTES_ESC3).
#   - El ano y mes de valuacion se toman del ultimo mes real de la BD; las rutas, la base Access y los parametros del
#     margen de riesgo estan en config_local.py. La logica de valuacion (consultas, PORC_ND, cesion, MR) no cambia.
#Escenario 0 -> LISTO -> Año Base (diciembre del año anterior, real) 
#Escenario 1 -> LISTO -> Presupuesto (dls) usando tc real para los meses que ya se tienen y usar el tc ppto para el resto
#Escenario 2 -> Usar función real para los meses reales y hacer proceso mensualizados para los meses que no se tienen, para tc usar el estimado ####AGREGAR LA FUNCIÓN DE LOS MENSUALIZADOS PARA EL RESTO DE MESES
#Escenario 3 -> LISTO -> Usar función real para los meses reales y traer la info del ppto para los meses que no se tienen, para tc usar el estimado
#Escenario 4 -> LISTO -> Reforecast final del año, usando funciones ppto y real para obtener saldo al final del año en usd, usar tc real y estimado para pasar a mxn #####REVISAR MR MUY ALTO Y HACER EL CRUCE CON EL TC ESTIMADO


import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from insumos_bd import InsumosBD, importar_o_instalar, mes_mas, norm, verificar_arranque   ### INSUMOS BD
try:
    import config_local as cfg                               ### INSUMOS BD: rutas y parametros locales
except ImportError:
    raise SystemExit("Falta config_local.py junto al script: copia config_local.ejemplo.py como config_local.py y "
                     "pon tus rutas y parametros")
pyodbc = importar_o_instalar("pyodbc")                    ### INSUMOS BD: si falta, lo instala (como el modelo
                                                             # principal); si no se puede, verificar_arranque avisa
warnings.filterwarnings('ignore')
start_time = time.perf_counter()

RUTA_BD = verificar_arranque(cfg, "RRC", pyodbc, Path(__file__).resolve().parent)   ### INSUMOS BD: revisa
# pyodbc, el controlador de Access, la base, los archivos del area y la BD antes de empezar (la BD: RUTA_BD o, si no
# esta ahi, la mas reciente junto al script o en salidas/)
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

#%% INSUMOS DE LA BD PROYECTADA                              ### INSUMOS BD
print('Leyendo la BD proyectada ...')
INS = InsumosBD(RUTA_BD, getattr(cfg, "RUTA_DIAGNOSTICO", None), usar_is_fa=getattr(cfg, "USAR_IS_FA", True),
                ramos_is_fa=getattr(cfg, "RAMOS_IS_FA", None))
zAño = cfg.ANIO or INS.anio                                  # ano de valuacion = el del ultimo mes real de la BD
zMes = cfg.MES or INS.mes                                    # ultimo mes real
print(f'Valuacion {zAño}, meses reales 1 a {zMes}')

#%% TABLAS CSV (catalogos y auxiliares del area que la BD no trae)
xRamo = pd.read_excel(cfg.CATALOGOS, sheet_name="Valores", usecols="J:M", skiprows=1)
xPais = pd.read_excel(cfg.CATALOGOS, sheet_name="Valores", usecols="O:T", skiprows=1)

xFolder = str(cfg.CSV_AUXILIARES_RRC)
xLlavesPol = pd.read_csv(os.path.join(xFolder, "LlavesPol.csv"))
xAjManuales = pd.read_csv(os.path.join(xFolder, "AjManuales.csv")) 
xSubramo = pd.read_csv(os.path.join(xFolder, "Subramo.csv"))
xCesionPI = pd.read_csv(os.path.join(xFolder, "CesionPI.csv"))
zAFUN = pd.read_csv(os.path.join(xFolder, "AFUN.csv"))
zFrecuencias = pd.read_csv(os.path.join(xFolder, "zFrecuencias.csv"))
xTablaCesion = pd.read_csv(os.path.join(xFolder, "TablaCesion_Esc1.csv"))
Cesion_Esp = pd.read_csv(os.path.join(xFolder, "Cesion ID Esp.csv"))

### INSUMOS BD: indices de siniestralidad (media y 99.5%) e Ind. Gasto por mes de valuacion, de la BD; duracion y
### retencion del MR del CSV del area (la BD no las trae); IS_Cat de TEV e Hidro de la BD
xRRC = INS.parametros_rrc(zAño, csv_duracion=getattr(cfg, "CSV_DURACION_RRC", None))
xIS_CAT = INS.is_cat(csv_is_cat=getattr(cfg, "CSV_IS_CAT", None))
xRRC_PPTO = xRRC                                             # los meses no valuados usan los mismos indices (proyectados)
xIS_CAT_PPTO = xIS_CAT
xIS_BEL_MEDIA = xIS_CAT
### INSUMOS BD: escenario 0 (ano base) de la BD y, si existe el CSV, los renglones del escenario 1 (presupuesto)
xEsc_base = INS.escenario_base("RRC", zAño)
_ruta_esc = (getattr(cfg, "ESCENARIO_BASE_CSV", None) or {}).get("RRC")
if _ruta_esc and Path(_ruta_esc).exists():
    _csv = pd.read_csv(_ruta_esc)
    _faltan = [c for c in ("Reserva", "Escenario", "Tipo de Monto", "Ramo", "Periodo", "Monto_USD") if c not in _csv.columns]
    if _faltan:
        print(f'   AVISO: {Path(_ruta_esc).name} no trae las columnas {_faltan}: el escenario 1 (presupuesto) no se incluye')
    else:
        _csv = _csv[_csv["Escenario"] == 1].copy()
        _csv["Periodo"] = pd.to_numeric(_csv["Periodo"], errors="coerce")
        _csv = _csv[_csv["Periodo"].notna()]
        xEsc_base = pd.concat([xEsc_base, _csv], ignore_index=True)
        print(f'   Escenario 1 (presupuesto): {len(_csv)} renglones de {Path(_ruta_esc).name}')
else:
    print('   Sin Escenario_base_RRC.csv: el escenario 1 (presupuesto) no se incluye')

#%% DICCIONARIOS
xNoRamo = { 'Vida' : 10, "Acc Per." : 31, "GMM" : 35, "Salud" : 39, "Resp. Civil" : 40, 
          "MyT" : 50, "Incendio" : 60, "Terremoto": 71, "HyORH": 73, "Agropecuario": 80, "Autos" : 90, "Crédito" : 100, "Diversos" : 110}

xEscenario = {f"BELRIESGO{zAño}_TCVal":["BEL", 2],
        f"BELGASTO{zAño}_TCVal":["BELG",2],
        f"IRR{zAño}_TCVal":["IRR",2],
        f"MR{zAño}_TCVal":["MR",2],
        "BRUTO_TCVal":["BRUTO",2],
        "NETO_TCVal":["NETO",2],
        f"BELRIESGO{zAño}_TCAñoAnt":["BEL",5],
        f"BELGASTO{zAño}_TCAñoAnt":["BELG",5],
        f"IRR{zAño}_TCAñoAnt":["IRR",5],
        f"MR{zAño}_TCAñoAnt":["MR",5],
        "BRUTO_TCAñoAnt":["BRUTO",5],
        "NETO_TCAñoAnt":["NETO",5],
        f"BELRIESGO{zAño}":["BEL", 4],
        f"BELGASTO{zAño}":["BELG",4],
        f"IRR{zAño}":["IRR",4],
        f"MR{zAño}":["MR",4],
        f"BRUTO{zAño}":["BRUTO",4],
        f"NETO{zAño}":["NETO",4]}

xTC_PPTO = INS.tc_dict()                                     ### INSUMOS BD: TC real hasta el ultimo mes y pronostico despues
	


#%% VARIABLES INPUT                                          ### INSUMOS BD: parametros del margen de riesgo en config_local
Nomeses = [1,12]
_MR = cfg.MR_RRC
MR_DESDE_BD = str(getattr(cfg, "MR_DESDE", "BD")).upper() == "BD"   ### INSUMOS BD: MR = PND del contrato x FACTOR MR de la BD
if not MR_DESDE_BD:
    for _k, _d in _MR.items():
        if isinstance(_d, dict) and any(v is None for v in _d.values()):
            raise SystemExit(f"config_local.MR_RRC['{_k}'] trae valores vacios: pon los parametros del margen de riesgo")
print('   MR del RRC: ' + ('PND x FACTOR MR de la BD' if MR_DESDE_BD else 'formula de capital del area (RCS, COC, duracion, BC)'))
if not MR_DESDE_BD and xRRC[["Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret"]].isna().all().all():
    raise SystemExit("MR_DESDE = 'AREA' necesita la duracion y retencion del CSV del area (CSV_DURACION_RRC): sin ellas el "
                     "MR del RRC saldria en 0")
_COLUMNAS_AJUSTE = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 'CiaTom', 'CtoTom', 'Susc', 'Período',
                    'CALMONTH', 'IniVig', 'FinVig', 'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal',
                    'PmaTom_sERNal', 'PrimaCedidaNal', 'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION',
                    'BELMEDIA', 'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'PORC_ND', 'CEDIDA',
                    'TC_Valuación', 'TC_CierreAnterior', f'PMADEV_{zAño}', f'DESVIACION{zAño}', f'BELRIESGO{zAño}_TCVal',
                    f'BELGASTO{zAño}_TCVal', f'IRR{zAño}_TCVal', f'MR{zAño}_TCVal', f'BELRIESGO{zAño}_TCAñoAnt',
                    f'BELGASTO{zAño}_TCAñoAnt', f'IRR{zAño}_TCAñoAnt', f'MR{zAño}_TCAñoAnt']
_ajenas = [c for c in xAjManuales.columns if c not in set(_COLUMNAS_AJUSTE)]
if len(xAjManuales) and _ajenas:                             ### INSUMOS BD: columnas con otro ano se perderian en el concat
    print(f'   AVISO: AjManuales.csv trae {len(_ajenas)} columna(s) que el script no usa este ano ({", ".join(map(str, _ajenas[:6]))}'
          f'{"..." if len(_ajenas) > 6 else ""}): revisa que los montos del ajuste lleven el ano {zAño} en el nombre')
BC_SONR = _MR.get("BC_SONR", 0) or 0


#%% PROYECCIÓN TC USD A FINAL DE AÑO
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
### el TC de la BD (pronostico), en lugar del promedio de los ultimos dos meses
if pyodbc is not None:
    TC_USD = ConsultaMoneda_usd()
    TC_USD = TC_USD[TC_USD['cTCAD_FecAMD'] <= zAño * 100 + zMes]
else:
    TC_USD = INS.tc_tabla().iloc[0:0]
_ult_tc = int(TC_USD['cTCAD_FecAMD'].max()) if len(TC_USD) else 0
_tc_bd = INS.tc_tabla()
TC_USD = pd.concat([TC_USD, _tc_bd[_tc_bd['cTCAD_FecAMD'] > _ult_tc]], ignore_index=True)
TC_USD = TC_USD.sort_values('cTCAD_FecAMD').reset_index(drop=True)
print(f'   TC USD: base hasta {_ult_tc}; de la BD, {int((_tc_bd["cTCAD_FecAMD"] > _ult_tc).sum())} meses')


def zPorcCesion(xCesion, zTablaCesion, zCesionPI, xSusc, xPorCed, xPorCedEsp, xTipoRea):
    AñoRef = zAño
    xPI = 1

    if xSusc >= 2023:
        xAUX_PI = xPI * zCesionPI 
    else: 
        xAUX_PI = 0
   
    if xCesion == 1:
        zCed = zTablaCesion
    elif xCesion == 2: 
        if xTipoRea == 3: 
            zCed = xPorCed 
        elif xPorCedEsp != None:
            zCed = zTablaCesion
        else:
            zCed = zTablaCesion
    elif xCesion == 3:
        zCed = 1
    elif xCesion == 4:
        zCed = 0

    zCed = max(zCed, 0)
    zRet = 1 - zCed
    return zCed + (zRet*xAUX_PI)

#%% TC PARA CÁLCULO RESERVAS (Del periodo y del cierre año anterior)

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

    ConsultaTC['Anio_ant'] = (zAño-1)*100+12
    ConsultaTC['Llave_ant'] = ConsultaTC[['Anio_ant', 'cMON_Id']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    ConsultaTC = ConsultaTC.merge(ConsultaTC_Temporal[["Llave","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Llave_ant", right_on="Llave")
    ConsultaTC = ConsultaTC.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="cTCAD_FecAMD", right_on="cTCAD_FecAMD")
    ConsultaTC['TC_USD'] = ConsultaTC.apply(lambda row: (row['cTCAD_Mnt_x'] /  row['cTCAD_Mnt']) if row['cTCAD_Mnt'] != 0 else 0, axis = 1)
    return(ConsultaTC)

ConsultaTC = ConsultaMoneda()

#%% FUNCION LN

def zLN(xRamo, xTerritorio, xTR, xSusc, xOfiRep):

    if xRamo == 80:
        return "Daños Facultativos Sur y Agropecuario" #LN4008
    elif xRamo == 10 or (xRamo<= 39 and xRamo >= 30):
        return "Vida, Accidentes y Enfermedades" #LN4004
    elif xRamo<= 170 and xRamo >= 100:
        return "Fianzas y Crédito" #LN04003
    elif xTerritorio == "R05":
        if xSusc >= 2022:
            return "Daños Ultramar Londres"  #LN04009
        elif xSusc == 2021 and xOfiRep == 1:
            return "Daños Ultramar Londres"  #LN04009
        else: return "Daños Líneas Especiales"  #LN04006
    elif xTerritorio == "R03" or xTerritorio == "R04":
        if xTR < 3:
            return "Daños Contratos Sur"  #LN04005
        else: return "Daños Facultativos Sur y Agropecuario"  #LN04008
    elif xTR < 3:
        return "Daños Contratos Norte"  #LN04001
    elif xTR == 3:
        return "Daños Facultativos Norte"  #LN04002

    return None  # Si no coincide con ningún caso

#%% FUNCIÓN RRC REAL USD
def ConsultaReal_USD(IS,IS_CAT, MES):

    global ConsultaTC, zMes, zFechaValuacion, xLlavesPol, xRamo
    
    # Conexión y consulta a la base de valuación
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    zLlavesPol = "','".join(list(xLlavesPol["Llave"].values)) 

    
    xSelect = "Select SRamo, Pais, TipoRea, OfiRepPt, MonedaOri, CorrTom, CiaTom, CtoTom, Susc, Período, aPog_MesProc AS CALMONTH, IniVig, FinVig, " \
              "CSng(Sum(Val(PriTomOri5)+Val(PriTomEnCOri5)+Val(PriTomReCOri5))) as PrimaTomadaOri, " \
              "CSng(Sum(Val(PriTomOri5))) as PmaTom_sEROri, CSng(Sum(Val(PriCedOri5))) as PrimaCedidaOri, " \
              "CSng(Sum(Val(PriTomNal5)+Val(PriTomEnCNal5)+Val(PriTomReCNal5))) as PrimaTomadaNal, " \
              "CSng(Sum(Val(PriTomNal5))) as PmaTom_sERNal, CSng(Sum(Val(PriCedNal5))) as PrimaCedidaNal "
    
    xTabla = "From dbo_aMOG_MovGonzalo "

    xWhere = f" Where ((Val(aPog_MesProc) > {AuxMesI} and Val(aPog_MesProc) <= {AuxMesF})  or ( FinVig > {zFechaValuacion} and IniVig < {zFechaValuacion}))" \
            f" and Tipo=5 and Ramo < 130 and Período <> 9  " \
                f"  and ((Val(PriTomOri5)+Val(PriTomEnCOri5)+Val(PriTomReCOri5) < 0) or (Val(left(aPog_MesProc,4)) <= Susc) ) " \
                    f"and (aPOG_MesProc & '-' & cNAT_IdTPol & '-' & TipoRea & '-' & aPOG_Num not in ('{zLlavesPol}') ) "


    xGroup = " Group By SRamo, Pais, TipoRea, OfiRepPt, MonedaOri, CorrTom, CiaTom, CtoTom, Susc, Período, aPog_MesProc, IniVig, FinVig"
    xOrder = ""

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xOrder])

    tMovGG = pd.read_sql(xSQL, conn)
    conn.close()

    ConsultaR = tMovGG


    #####AGREGAR COLUMNAS REAL
    ConsultaR= ConsultaR.merge(xPais[["País","TerrSAP"]].drop_duplicates(),
                             how="left", left_on="Pais", right_on="País")
    
    ConsultaR= ConsultaR.rename(columns={
                            "TerrSAP":"REGION"
                            })

    ConsultaR = ConsultaR.merge(xRamo[["SR","Ramo"]].drop_duplicates(),
                             how="left", left_on="SRamo", right_on="SR")
    
    ConsultaR['LLAVE_TC'] = f'{Meses}-' + ConsultaR['MonedaOri'].astype('str')
    ConsultaR = ConsultaR.merge(ConsultaTC[["Llave_x","cTCAD_Mnt_x","cTCAD_Mnt_y","TC_USD"]].drop_duplicates(),
                             how="left", left_on="LLAVE_TC", right_on="Llave_x")
    ConsultaR = ConsultaR.drop('SR', axis=1)
    ConsultaR['Ramo'] = ConsultaR['Ramo'].apply(lambda x: xNoRamo[x])

    ConsultaR['LLAVE'] = ConsultaR[['CorrTom', 'CiaTom', 'Susc', 'TipoRea']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    ConsultaR['LN2'] = ConsultaR.apply(lambda y: zLN(y['Ramo'], y['REGION'], y['TipoRea'], y['Susc'], y['OfiRepPt']), axis=1)
    ConsultaR['FRECUENCIA'] = ConsultaR.apply(lambda row: row['Período'] if row['TipoRea'] == 1 and row['Ramo'] != 71 and row['Ramo'] != 73 and row['Ramo'] != 100 else 'NA', axis = 1)
    

    ConsultaR['MONTO_PI'] = ConsultaR.apply(lambda row: (row['PmaTom_sEROri'] if row['TipoRea'] == 2 and row['Ramo'] != 71 and row['Ramo'] != 73 else row['PrimaTomadaOri']) * row["TC_USD"], axis = 1)
    
    ##Cruce xRRC e IS BEL MEDIA (CAT)
    ConsultaR= ConsultaR.merge(IS[["Ramo","Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto-12", "FACTOR MR-12", f"IS Bel Media-12", f"IS Bel 99.5%-12"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "FACTOR MR-12":"FACTORMR",                  ### INSUMOS BD: MR / PND de la BD (diciembre)
                            "Ind. Gasto-12":"BELGASTO",                 ### INSUMOS BD: gasto del mes de valuacion (diciembre)
                            f"IS Bel 99.5%-12":"BEL99",
                            }),
                             how="left", left_on="Ramo", right_on="Ramo")
    ConsultaR = ConsultaR.merge(IS_CAT[["IS Bel Media","71", "73"]].drop_duplicates(),
                             how="left", left_on="CALMONTH", right_on="IS Bel Media")

    ##Cruce xRRC e IS BEL MEDIA (CAT)

    ConsultaR['CESION'] = ConsultaR.apply(lambda row: -1*(row['PrimaCedidaOri']* row["TC_USD"])/row['MONTO_PI'] if row['MONTO_PI'] != 0 else 0, axis = 1)
    ConsultaR['BELMEDIA'] = ConsultaR.apply(lambda row: row['71'] if row['Ramo'] == 71 else (row['73'] if row['Ramo'] == 73 else row[f'IS Bel Media-12']), axis = 1)
    ConsultaR = ConsultaR.drop(['71','73', f'IS Bel Media-12', 'IS Bel Media'], axis=1)
    
    ConsultaR['VALORFREC'] =  ConsultaR.apply(
    lambda row: xPND.get(row['CALMONTH'], 0).get(str(row['FRECUENCIA']), 0),
    axis=1)

    ConsultaR['PORC_ND'] = ConsultaR.apply(
    lambda row: (
        row['VALORFREC']  # Si el Ramo es 71 o 73
        if row['Ramo'] in [71, 73] 
        else (
            0  # Si TipoRea es 2 y las fechas de inicio y fin son iguales
            if row['TipoRea'] == 2 and row['IniVig'] == row['FinVig'] 
            else (
                np.maximum(np.minimum(
                    (row['FinVig'] - pd.Timestamp(zFechaValuacion)).days / 
                    (row['FinVig'] - row['IniVig']).days, 1), 0)
                # Si TipoRea es 2 y las fechas de inicio y fin son diferentes
                if row['TipoRea'] == 2 and row['IniVig'] != row['FinVig']
                else row['VALORFREC']  # En cualquier otro caso
            )
        )
    ), axis=1)

    #ConsultaR = ConsultaR.drop('VALORFREC', axis=1)

    ConsultaR['CEDIDA'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['CESION'], axis = 1)
    ConsultaR['TC_Valuación'] =  ConsultaR['cTCAD_Mnt_x']
    ConsultaR['TC_CierreAnterior'] = ConsultaR['cTCAD_Mnt_y']
    ConsultaR[f'BELRIESGO{zAño}_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR[f'BELGASTO{zAño}_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR[f'IRR{zAño}_TCVal'] = ConsultaR.apply(lambda row: row[f'BELRIESGO{zAño}_TCVal']*row['CESION'], axis = 1)
    
    
    ConsultaR[f'DESVIACION{zAño}'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    BC_RRC = ConsultaR[f'DESVIACION{zAño}'].sum()
    BC_TOTAL = BC_RRC + BC_SONR
    RCS = _MR["REAL_USD"].get("RCS") or 0                      ### INSUMOS BD: parametros del MR de config_local (solo MR_DESDE = "AREA")
    COC = _MR["REAL_USD"].get("COC") or 0
    ConsultaR[f'MR{zAño}_TCVal'] = ConsultaR.apply(lambda row: (row['MONTO_PI']*row['PORC_ND']*row['FACTORMR']) if MR_DESDE_BD else -1*row[f'DESVIACION{zAño}']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_TOTAL), axis = 1)   ### INSUMOS BD
    
    
    ConsultaR[f'PMADEV_{zAño}'] = ConsultaR.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    ConsultaR[f'BELRIESGO{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR[f'BELGASTO{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR[f'IRR{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: row[f'BELRIESGO{zAño}_TCAñoAnt']*row['CESION'], axis = 1)																											
    ConsultaR[f'MR{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: (row['MONTO_PI']*row['PORC_ND']*row['FACTORMR']) if MR_DESDE_BD else -1*row[f'DESVIACION{zAño}']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_TOTAL), axis = 1)   ### INSUMOS BD
    

    xColumnas = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 
             'CiaTom', 'CtoTom', 'Susc', 'Período', 'CALMONTH', 'IniVig', 'FinVig', 
             'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal','PmaTom_sERNal', 'PrimaCedidaNal',
             'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION','BELMEDIA', 
             'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'VALORFREC', 'PORC_ND', 'CEDIDA', 
             'TC_Valuación', 'TC_CierreAnterior', f'PMADEV_{zAño}', f'DESVIACION{zAño}', f'BELRIESGO{zAño}_TCVal', f'BELGASTO{zAño}_TCVal',
             f'IRR{zAño}_TCVal', f'MR{zAño}_TCVal', f'BELRIESGO{zAño}_TCAñoAnt', f'BELGASTO{zAño}_TCAñoAnt', f'IRR{zAño}_TCAñoAnt', f'MR{zAño}_TCAñoAnt']

    ConsultaR = ConsultaR.reindex(columns=xColumnas, fill_value='')
    #ConsultaR = pd.concat([ConsultaR,xAjManuales],axis=0) 

    #fileName = os.path.join(xFolder, "ConsultaR_RRC_{MES}.xlsx")
    #ConsultaR.to_excel(fileName, index=False)

    return ConsultaR

#%% FUNCIÓN RRC PPTO

def ConsultaPPTO(MES):
    global xPais, xSubramo, ConsultaTC, xRRC, xIS_BEL_MEDIA, BC, RCS, COC, tc_CIERRE, zMes, zAFUN, xCesionPI, xTablaCesion, zFrecuencias, xPND2, Cesion_Esp
    
    ConsultaP = _normalizar_ppto(pd.read_csv(cfg.PPTO_TECNICO_RRC, thousands=','))     ### INSUMOS BD: ruta en config_local
    ConsultaPPTO = ConsultaP[(ConsultaP["GL_ACCT"] > 6101000000) & (ConsultaP["GL_ACCT"] < 6108999999) & (ConsultaP["CALMONTH"] <= zAño*100 + 12) & (ConsultaP["CALMONTH"] >= (zAño*100 + MES + 1))]

    Columnas = [
    'PROFTCTR', 'ZREGIONRP', 'ZTIPOREAS', 'ZOFICN_RP', 'FUNCAREA', 'ZMGA', 
    'TWAERS', 'ZTIPOCES', 'PRODUCT', 'ZCORREDOR', 'ZCEDENTE', 'ZCONTRATO', 
    'ZSUSCYEAR', 'CALMONTH', 'AMOUNT']

    ConsultaPPTO = ConsultaPPTO[Columnas]

    ConsultaPPTO= ConsultaPPTO.merge(xSubramo[["CeBe","Ramo", "Ramo2"]].drop_duplicates(),
                             how="left", left_on="PROFTCTR", right_on="CeBe")
    
    ConsultaPPTO['Ramo'] = ConsultaPPTO.apply(lambda row: 10 if row['Ramo'] == 20 else row['Ramo'], axis = 1)

    ConsultaPPTO = ConsultaPPTO.drop('CeBe', axis=1)
    

    ConsultaPPTO= ConsultaPPTO.merge(xRRC[["Ramo", "Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto-12", "FACTOR MR-12", f"IS Bel Media-12", f"IS Bel 99.5%-12"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "FACTOR MR-12":"FACTORMR",                  ### INSUMOS BD: MR / PND de la BD (diciembre)
                            "Ind. Gasto-12":"BELGASTO",                 ### INSUMOS BD
                            f"IS Bel 99.5%-12":"BEL99",
                            f"IS Bel Media-12":"BELMEDIA"
                            }),
                             how="left", left_on="Ramo", right_on="Ramo")
    ConsultaPPTO = ConsultaPPTO.merge(xIS_BEL_MEDIA[["IS Bel Media","71", "73"]].drop_duplicates(),
                             how="left", left_on="CALMONTH", right_on="IS Bel Media")
    ConsultaPPTO = ConsultaPPTO.drop('IS Bel Media', axis=1)

                            
    
    ConsultaPPTO = ConsultaPPTO.merge(xCesionPI[["Ramo", "2020", "2021", "2022", "2023","2024", "2025", "2026", "2027", "2028", "2029"]].drop_duplicates()
                            .rename(columns={
                            "2020":"202000",
                            "2021":"202100",
                            "2022":"202200",
                            "2023":"202300",
                            "2024":"202400",
                            "2025":"202500",
                            "2026":"202600",
                            "2027":"202700",
                            "2028":"202800",
                            "2029":"202900"
                            }),
                             how="left", left_on="Ramo", right_on="Ramo")
    
    ConsultaPPTO = ConsultaPPTO.merge(zAFUN[["AFUN","Linea de Negocio"]].drop_duplicates(),
                             how="left", left_on="FUNCAREA", right_on="AFUN")
    ConsultaPPTO = ConsultaPPTO.drop('AFUN', axis=1)
    

    ConsultaPPTO['LLAVE'] = ConsultaPPTO[['ZCORREDOR', 'ZCEDENTE', 'ZCONTRATO', 'ZTIPOREAS']].apply(lambda x: '-'.join(x.fillna(0).astype('int').astype('str')), axis=1)

    ConsultaPPTO['LLAVE1'] = ConsultaPPTO[['ZCORREDOR', 'ZCEDENTE', 'ZCONTRATO', 'ZSUSCYEAR', 'ZTIPOREAS']].apply(
    lambda x: '-'.join([
        str(int(x['ZCORREDOR']) if pd.notna(x['ZCORREDOR']) else 0), 
        str(int(x['ZCEDENTE']) if pd.notna(x['ZCEDENTE']) else 0), 
        str(int(x['ZCONTRATO']) if pd.notna(x['ZCONTRATO']) else 0),  
        str(min(int(x['ZSUSCYEAR']) if pd.notna(x['ZSUSCYEAR']) else zAño - 1, zAño - 1)), 
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else '')  
    ]), axis=1)
        
    
    ConsultaPPTO['LLAVE2'] = ConsultaPPTO[['PROFTCTR', 'CALMONTH', 'TWAERS']].apply(lambda x: '|'.join(x.astype('str')), axis=1)


    ConsultaPPTO = ConsultaPPTO.merge(zFrecuencias[["Llave","Periodo"]].drop_duplicates(),
                             how="left", left_on="LLAVE", right_on="Llave")

    ConsultaPPTO['FRECUENCIA'] = ConsultaPPTO.apply(lambda row: row['Periodo'] if row['ZTIPOREAS'] == 1 and row['Ramo'] != 71 and row['Ramo'] != 73 and row['Ramo'] != 100 else 'NA', axis = 1)
    ConsultaPPTO['FRECUENCIA'] = ConsultaPPTO['FRECUENCIA'].fillna('DEF')
    ConsultaPPTO = ConsultaPPTO.drop('Periodo', axis=1)

    ConsultaPPTO['MONTO_PI'] = ConsultaPPTO['AMOUNT']

    ConsultaPPTO['LLAVE3'] = ConsultaPPTO[['Ramo2', 'ZREGIONRP', 'ZTIPOREAS']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    ConsultaPPTO = ConsultaPPTO.merge(xTablaCesion[["Llave","2020","2021","2022","2023","2024", "2025", "2026", "2027", "2028", "2029"]].drop_duplicates(),
                             how="left", left_on="LLAVE3", right_on="Llave")
    ConsultaPPTO = ConsultaPPTO.drop('Llave_y', axis=1)

    ConsultaPPTO = ConsultaPPTO.merge(Cesion_Esp[["Llave","Porcentaje Cedido"]].drop_duplicates(),
                             how="left", left_on="LLAVE1", right_on="Llave")
    
    ConsultaPPTO['CESION'] = ConsultaPPTO.apply(lambda y:zPorcCesion(y['ZTIPOCES'], y[str(y['ZSUSCYEAR'])], y[str(y['ZSUSCYEAR'] * 100)], y['ZSUSCYEAR'], float(y['PRODUCT']), float(y['Porcentaje Cedido']), y['ZTIPOREAS']), axis=1)
    ConsultaPPTO = ConsultaPPTO.drop(["71","73","2020","2021","2022","2023","2024", "2025", "2026", "2027", "2028", "2029", "202000","202100","202200","202300","202400","202500","202600","202700", "202800","202900", "Llave"], axis=1)
   
    ConsultaPPTO['PORC_ND'] =  ConsultaPPTO.apply(
    lambda row: xPND2.get(row['CALMONTH'], 0).get(row['FRECUENCIA'], 2),axis=1)



    ConsultaPPTO['CEDIDA'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['CESION'], axis = 1)

    ConsultaPPTO[f'BELRIESGO{zAño}'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaPPTO[f'BELGASTO{zAño}'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaPPTO[f'IRR{zAño}'] = ConsultaPPTO.apply(lambda row: row[f'BELRIESGO{zAño}']*row['CESION'], axis = 1)
    ConsultaPPTO[f'DESVIACION{zAño}'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['TWAERS'] == "MXN" else row['RETOTR']), axis = 1)
    BC_RRC = ConsultaPPTO[f'DESVIACION{zAño}'].sum()
    BC_TOTAL = BC_RRC + BC_SONR
    BC = _MR["PPTO"].get("BC") or 1                            ### INSUMOS BD: parametros del MR de config_local (solo MR_DESDE = "AREA")
    RCS = _MR["PPTO"].get("RCS") or 0
    COC = _MR["PPTO"].get("COC") or 0

    
    ConsultaPPTO[f'MR{zAño}'] = ConsultaPPTO.apply(lambda row: (row['MONTO_PI']*row['PORC_ND']*row['FACTORMR']) if MR_DESDE_BD else -1*row[f'DESVIACION{zAño}']*RCS*COC*(row['DURMXN'] if row['TWAERS'] == "MXN" else (row['DUROTR']))*(1/BC), axis = 1)   ### INSUMOS BD
    
    ConsultaPPTO[f'PMADEV_{zAño}'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    _guardar(ConsultaPPTO, f"ConsultaPPTO_RRC_{MES}.xlsx")

    return ConsultaPPTO

#%% FUNCION RRC REAL

def ConsultaReal(IS,IS_CAT, MES):

    global ConsultaTC, zMes, zFechaValuacion, xLlavesPol, xRamo
    
    # Conexión y consulta a la base de valuación
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    
    zLlavesPol = "','".join(list(xLlavesPol["Llave"].values)) 

    
    xSelect = "Select SRamo, Pais, TipoRea, OfiRepPt, MonedaOri, CorrTom, CiaTom, CtoTom, Susc, Período, aPog_MesProc AS CALMONTH, IniVig, FinVig, " \
              "CSng(Sum(Val(PriTomOri5)+Val(PriTomEnCOri5)+Val(PriTomReCOri5))) as PrimaTomadaOri, " \
              "CSng(Sum(Val(PriTomOri5))) as PmaTom_sEROri, CSng(Sum(Val(PriCedOri5))) as PrimaCedidaOri, " \
              "CSng(Sum(Val(PriTomNal5)+Val(PriTomEnCNal5)+Val(PriTomReCNal5))) as PrimaTomadaNal, " \
              "CSng(Sum(Val(PriTomNal5))) as PmaTom_sERNal, CSng(Sum(Val(PriCedNal5))) as PrimaCedidaNal "
    
    xTabla = "From dbo_aMOG_MovGonzalo "

    xWhere = f" Where ((Val(aPog_MesProc) > {AuxMesI} and Val(aPog_MesProc) <= {AuxMesF})  or ( FinVig > {zFechaValuacion} and IniVig < {zFechaValuacion}))" \
            f" and Tipo=5 and Ramo < 130 and Período <> 9  " \
                f"  and ((Val(PriTomOri5)+Val(PriTomEnCOri5)+Val(PriTomReCOri5) < 0) or (Val(left(aPog_MesProc,4)) <= Susc) ) " \
                    f"and (aPOG_MesProc & '-' & cNAT_IdTPol & '-' & TipoRea & '-' & aPOG_Num not in ('{zLlavesPol}') ) "


    xGroup = " Group By SRamo, Pais, TipoRea, OfiRepPt, MonedaOri, CorrTom, CiaTom, CtoTom, Susc, Período, aPog_MesProc, IniVig, FinVig"
    xOrder = ""

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xOrder])

    tMovGG = pd.read_sql(xSQL, conn)
    conn.close()

    ConsultaR = tMovGG


    #####AGREGAR COLUMNAS REAL
    ConsultaR= ConsultaR.merge(xPais[["País","TerrSAP"]].drop_duplicates(),
                             how="left", left_on="Pais", right_on="País")
    
    ConsultaR= ConsultaR.rename(columns={
                            "TerrSAP":"REGION"
                            })

    ConsultaR = ConsultaR.merge(xRamo[["SR","Ramo"]].drop_duplicates(),
                             how="left", left_on="SRamo", right_on="SR")
    
    ConsultaR['LLAVE_TC'] = f'{Meses}-' + ConsultaR['MonedaOri'].astype('str')
    ConsultaR = ConsultaR.merge(ConsultaTC[["Llave_x","cTCAD_Mnt_x","cTCAD_Mnt_y"]].drop_duplicates(),
                             how="left", left_on="LLAVE_TC", right_on="Llave_x")
    ConsultaR = ConsultaR.drop('SR', axis=1)
    ConsultaR['Ramo'] = ConsultaR['Ramo'].apply(lambda x: xNoRamo[x])

    ConsultaR['LLAVE'] = ConsultaR[['CorrTom', 'CiaTom', 'Susc', 'TipoRea']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    ConsultaR['LN2'] = ConsultaR.apply(lambda y: zLN(y['Ramo'], y['REGION'], y['TipoRea'], y['Susc'], y['OfiRepPt']), axis=1)
    ConsultaR['FRECUENCIA'] = ConsultaR.apply(lambda row: row['Período'] if row['TipoRea'] == 1 and row['Ramo'] != 71 and row['Ramo'] != 73 and row['Ramo'] != 100 else 'NA', axis = 1)
    

    ConsultaR['MONTO_PI'] = ConsultaR.apply(lambda row: row['PmaTom_sEROri'] if row['TipoRea'] == 2 and row['Ramo'] != 71 and row['Ramo'] != 73 else row['PrimaTomadaOri'], axis = 1)
    
    ##Cruce xRRC e IS BEL MEDIA (CAT)
    ConsultaR= ConsultaR.merge(IS[["Ramo","Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", f"Ind. Gasto-{MES}", f"FACTOR MR-{MES}", f"IS Bel Media-{MES}", f"IS Bel 99.5%-{MES}"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            f"FACTOR MR-{MES}":"FACTORMR",              ### INSUMOS BD: MR / PND de la BD del mes de valuacion
                            f"Ind. Gasto-{MES}":"BELGASTO",             ### INSUMOS BD: gasto del mes de valuacion
                            f"IS Bel 99.5%-{MES}":"BEL99",
                            }),
                             how="left", left_on="Ramo", right_on="Ramo")
    ConsultaR = ConsultaR.merge(IS_CAT[["IS Bel Media","71", "73"]].drop_duplicates(),
                             how="left", left_on="CALMONTH", right_on="IS Bel Media")

    ##Cruce xRRC e IS BEL MEDIA (CAT)

    ConsultaR['CESION'] = ConsultaR.apply(lambda row: -1*row['PrimaCedidaOri']/row['MONTO_PI'] if row['MONTO_PI'] != 0 else 0, axis = 1)
    ConsultaR['BELMEDIA'] = ConsultaR.apply(lambda row: row['71'] if row['Ramo'] == 71 else (row['73'] if row['Ramo'] == 73 else row[f'IS Bel Media-{MES}']), axis = 1)
    ConsultaR = ConsultaR.drop(['71','73', f'IS Bel Media-{MES}', 'IS Bel Media'], axis=1)
    
    ConsultaR['VALORFREC'] =  ConsultaR.apply(
    lambda row: xPND.get(row['CALMONTH'], 0).get(str(row['FRECUENCIA']), 0),
    axis=1)

    ConsultaR['PORC_ND'] = ConsultaR.apply(
    lambda row: (
        row['VALORFREC']  # Si el Ramo es 71 o 73
        if row['Ramo'] in [71, 73] 
        else (
            0  # Si TipoRea es 2 y las fechas de inicio y fin son iguales
            if row['TipoRea'] == 2 and row['IniVig'] == row['FinVig'] 
            else (
                np.maximum(np.minimum(
                    (row['FinVig'] - pd.Timestamp(zFechaValuacion)).days / 
                    (row['FinVig'] - row['IniVig']).days, 1), 0)
                # Si TipoRea es 2 y las fechas de inicio y fin son diferentes
                if row['TipoRea'] == 2 and row['IniVig'] != row['FinVig']
                else row['VALORFREC']  # En cualquier otro caso
            )
        )
    ), axis=1)

    ConsultaR['PORC_ND'] = ConsultaR['PORC_ND'].fillna(0)
    ConsultaR['BELMEDIA'] = ConsultaR['BELMEDIA'].fillna(0)
    ConsultaR = ConsultaR.drop('VALORFREC', axis=1)

    ConsultaR['CEDIDA'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['CESION'], axis = 1)
    ConsultaR['TC_Valuación'] =  ConsultaR['cTCAD_Mnt_x']
    ConsultaR['TC_CierreAnterior'] = ConsultaR['cTCAD_Mnt_y']
    ConsultaR['BELMEDIA'] = pd.to_numeric(ConsultaR['BELMEDIA'], errors='coerce')
    _guardar(ConsultaR, f"ConsultaR_RRC_{MES}.xlsx")
    ConsultaR[f'BELRIESGO{zAño}_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA']*row['TC_Valuación'], axis = 1)
    ConsultaR[f'BELGASTO{zAño}_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO']*row['TC_Valuación'], axis = 1)
    ConsultaR[f'IRR{zAño}_TCVal'] = ConsultaR.apply(lambda row: row[f'BELRIESGO{zAño}_TCVal']*row['CESION'], axis = 1)
    
    ConsultaR[f'DESVIACION{zAño}'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*row['TC_Valuación']*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    BC_RRC = ConsultaR[f'DESVIACION{zAño}'].sum()
    BC_TOTAL = BC_RRC + BC_SONR
    COC = _MR["REAL"].get("COC") or 0                          ### INSUMOS BD: parametros del MR de config_local (solo MR_DESDE = "AREA")
    RCS = _MR["REAL"].get("RCS") or 0
    ConsultaR[f'MR{zAño}_TCVal'] = ConsultaR.apply(lambda row: (row['MONTO_PI']*row['PORC_ND']*row['FACTORMR']*row['TC_Valuación']) if MR_DESDE_BD else -1*row[f'DESVIACION{zAño}']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_TOTAL), axis = 1)   ### INSUMOS BD
    ConsultaR[f'PMADEV_{zAño}'] = ConsultaR.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    ConsultaR[f'BELRIESGO{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA']*row['TC_CierreAnterior'], axis = 1)
    ConsultaR[f'BELGASTO{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO']*row['TC_CierreAnterior'], axis = 1)
    ConsultaR[f'IRR{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: row[f'BELRIESGO{zAño}_TCAñoAnt']*row['CESION'], axis = 1)																											
    ConsultaR[f'MR{zAño}_TCAñoAnt'] = ConsultaR.apply(lambda row: (row['MONTO_PI']*row['PORC_ND']*row['FACTORMR']*row['TC_CierreAnterior']) if MR_DESDE_BD else -1*row[f'DESVIACION{zAño}']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_TOTAL), axis = 1)   ### INSUMOS BD

    xColumnas = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 
             'CiaTom', 'CtoTom', 'Susc', 'Período', 'CALMONTH', 'IniVig', 'FinVig', 
             'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal','PmaTom_sERNal', 'PrimaCedidaNal',
             'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION','BELMEDIA', 
             'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'PORC_ND', 'CEDIDA', 
             'TC_Valuación', 'TC_CierreAnterior', f'PMADEV_{zAño}', f'DESVIACION{zAño}', f'BELRIESGO{zAño}_TCVal', f'BELGASTO{zAño}_TCVal',
             f'IRR{zAño}_TCVal', f'MR{zAño}_TCVal', f'BELRIESGO{zAño}_TCAñoAnt', f'BELGASTO{zAño}_TCAñoAnt', f'IRR{zAño}_TCAñoAnt', f'MR{zAño}_TCAñoAnt']
    
    ConsultaR = ConsultaR.reindex(columns=xColumnas, fill_value='')
    ConsultaR = pd.concat([ConsultaR,xAjManuales],axis=0) 
    return ConsultaR


#%% FUNCION RRC MENSUALIZADOS

#%% ESCENARIO 0 Y 1
print('Inicio cálculo escenario 0 y 1')
columnas_finales = ['Reserva', 'Escenario', 'Tipo de Monto','Ramo', 'Periodo', 'Monto_MXN', 'Monto_USD', 'TC']
xEsc_base = xEsc_base[columnas_finales]

#xEsc_base= xEsc_base.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
#                             how="left", left_on="Periodo", right_on="cTCAD_FecAMD")
#xEsc_base['TC'] = xEsc_base['cTCAD_Mnt']
xEsc_base['TC'] =  xEsc_base.apply(lambda row: INS.tc_de(int(row['Periodo'])),axis=1)   ### INSUMOS BD: TC de la BD
xEsc_base['Monto_MXN'] = xEsc_base.apply(lambda row: row['Monto_USD'] * row['TC'], axis = 1)
print('Fin cálculo escenario 0 y 1')


df = []
#%% ESCENARIO 2 - INICIO CICLO FOR

for mes in range(zMes):
#for mes in [4]:
    
    mes_calculo = mes + 1

    ##Meses real escenario 2
    zAñoRef = zAño - 1
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
    AuxMesI =  zAñoRef * 100 + mes_calculo
    AuxMesF = AuxMesI + 100

    Meses = zAño*100 + mes_calculo 
    Mesesppto = zAño*100 + zMes

    print(f'Inicio cálculo escenario 2 para {Meses}')

    ### INSUMOS BD: los meses hacia atras se calculan con mes_mas (antes, un diccionario fijo del ano de valuacion)
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
        Meses: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329}}

    df_Real_IS_Real = ConsultaReal(xRRC,xIS_CAT,mes_calculo)   ### INSUMOS BD: indices de la BD del mes de valuacion

    ##Meses ppto escenario 2
    


    xColumnas = ['Ramo', f'BELRIESGO{zAño}_TCVal', f'BELGASTO{zAño}_TCVal', f'IRR{zAño}_TCVal', f'MR{zAño}_TCVal',
                f'BELRIESGO{zAño}_TCAñoAnt', f'BELGASTO{zAño}_TCAñoAnt', f'IRR{zAño}_TCAñoAnt', f'MR{zAño}_TCAñoAnt']

    df_RRC_dim = df_Real_IS_Real.reindex(columns=xColumnas)
    df_RRC_dim['BRUTO_TCVal'] = df_RRC_dim.apply(lambda row: -row[f'BELRIESGO{zAño}_TCVal'] - row[f'BELGASTO{zAño}_TCVal'] - row[f'MR{zAño}_TCVal'], axis = 1)
    df_RRC_dim['NETO_TCVal'] = df_RRC_dim.apply(lambda row: row['BRUTO_TCVal'] + row[f'IRR{zAño}_TCVal'], axis = 1)
    df_RRC_dim['BRUTO_TCAñoAnt'] = df_RRC_dim.apply(lambda row: -row[f'BELRIESGO{zAño}_TCAñoAnt'] - row[f'BELGASTO{zAño}_TCAñoAnt'] - row[f'MR{zAño}_TCAñoAnt'], axis = 1)
    df_RRC_dim['NETO_TCAñoAnt'] = df_RRC_dim.apply(lambda row: row['BRUTO_TCAñoAnt'] + row[f'IRR{zAño}_TCAñoAnt'], axis = 1)
    df_RRC_dim['Reserva'] = 'RRC'
    df_RRC_dim['Periodo'] = f'{zAño}{AuxMes}{mes_calculo}'


    auxRRC = df_RRC_dim.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxRRC = auxRRC.reset_index()
    auxRRC.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    auxRRC_sum = auxRRC.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxRRC_sum['Tipo de Monto'] = auxRRC_sum['Origen'].apply(lambda x: xEscenario[x][0])
    auxRRC_sum['Escenario'] = auxRRC_sum['Origen'].apply(lambda x: xEscenario[x][1])
    auxRRC_sum['Periodo'] = auxRRC_sum['Periodo'].astype(int)

    auxRRC_sum= auxRRC_sum.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo", right_on="cTCAD_FecAMD")
    
    auxRRC_sum['Monto_MXN'] = auxRRC_sum['Monto']
    auxRRC_sum['Monto_USD'] = auxRRC_sum.apply(lambda row: row['Monto_MXN'] / row['cTCAD_Mnt'], axis = 1)

    xColumnas = ['Reserva', 'Ramo', 'Periodo', 'Tipo de Monto', 'Escenario',
                'Monto_MXN', 'Monto_USD']

    auxRRC_sum = auxRRC_sum.reindex(columns=xColumnas)
    print(f'Fin cálculo escenario 2 para {Meses}')
#%%Escenario 3
    df.append(auxRRC_sum)
    print(f'Inicio cálculo escenario 3 para {Meses}')

    xColumnas = ['Ramo', f'BELRIESGO{zAño}_TCVal', f'BELGASTO{zAño}_TCVal', f'IRR{zAño}_TCVal', f'MR{zAño}_TCVal']

    df_RRC_dim_3 = df_Real_IS_Real.reindex(columns=xColumnas)
    df_RRC_dim_3['BRUTO_TCVal'] = df_RRC_dim_3.apply(lambda row: -row[f'BELRIESGO{zAño}_TCVal'] - row[f'BELGASTO{zAño}_TCVal'] - row[f'MR{zAño}_TCVal'], axis = 1)
    df_RRC_dim_3['NETO_TCVal'] = df_RRC_dim_3.apply(lambda row: row['BRUTO_TCVal'] + row[f'IRR{zAño}_TCVal'], axis = 1)
    #df_RRC_dim_3['BRUTO_TCAñoAnt'] = df_RRC_dim_3.apply(lambda row: -row[f'BELRIESGO{zAño}_TCAñoAnt'] - row[f'BELGASTO{zAño}_TCAñoAnt'] - row[f'MR{zAño}_TCAñoAnt'], axis = 1)
    #df_RRC_dim_3['NETO_TCAñoAnt'] = df_RRC_dim_3.apply(lambda row: row['BRUTO_TCAñoAnt'] + row[f'IRR{zAño}_TCAñoAnt'], axis = 1)
    df_RRC_dim_3['Reserva'] = 'RRC'
    df_RRC_dim_3['Periodo'] = f'{zAño}{AuxMes}{mes_calculo}'


    auxRRC_3 = df_RRC_dim_3.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxRRC_3 = auxRRC_3.reset_index()
    auxRRC_3.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    auxRRC_sum_3 = auxRRC_3.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxRRC_sum_3['Tipo de Monto'] = auxRRC_sum_3['Origen'].apply(lambda x: xEscenario[x][0])
    
    ### INSUMOS BD: los meses que el script no valua (despues del ultimo real) salen de los saldos proyectados de la
    ### BD (MESES_FALTANTES_ESC3 = "BD") o del presupuesto del CSV (escenario 1), como antes
    if str(getattr(cfg, "MESES_FALTANTES_ESC3", "BD")).upper() == "BD":
        Meses_falt_3 = INS.saldos_proyectados("RRC", mes_mas(Mesesppto, 1), zAño * 100 + 12, escenario=3)
    else:
        Meses_falt_3 = xEsc_base[(xEsc_base["Periodo"] > Mesesppto) & (xEsc_base["Escenario"] == 1)]
    auxRRC_sum_3 = pd.concat([auxRRC_sum_3,Meses_falt_3],axis=0)

    auxRRC_sum_3['Escenario'] = 3
    auxRRC_sum_3['Periodo'] = auxRRC_sum_3['Periodo'].astype(int)

    auxRRC_sum_3= auxRRC_sum_3.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo", right_on="cTCAD_FecAMD")
    
    #auxRRC_sum_3['Monto_MXN'] = auxRRC_sum_3['Monto']
    #auxRRC_sum_3['Monto_USD'] = auxRRC_sum_3.apply(lambda row: row['Monto_MXN'] / row['cTCAD_Mnt'], axis = 1)
    auxRRC_sum_3['TC'] = auxRRC_sum_3['cTCAD_Mnt']
    auxRRC_sum_3['Monto_MXN'] = auxRRC_sum_3.apply(lambda row: row['Monto_USD'] * row['TC'] if row['Periodo'] > AuxMesF else row['Monto'], axis = 1)
    auxRRC_sum_3['Monto_USD'] = auxRRC_sum_3.apply(lambda row: row['Monto_USD'] if row['Periodo'] > AuxMesF else row['Monto_MXN'] / row['TC'], axis = 1)
    
    

    xColumnas = ['Reserva', 'Ramo', 'Periodo', 'Tipo de Monto', 'Escenario',
                'Monto_MXN', 'Monto_USD', 'TC']

    auxRRC_sum_3 = auxRRC_sum_3.reindex(columns=xColumnas)
    df.append(auxRRC_sum_3)
    print(f'Fin cálculo escenario 3 para {Meses}')
#%%Escenario 4
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
        Mesesp: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329}}
    xPND2 = {
    mes_mas(Mesesp, -11): {'NA': 0.043835616, 1: 0.043835616, 2: 0, 3: 0, 6: 0, 0: 0, 'DEF': 0},
    mes_mas(Mesesp, -10): {'NA': 0.126027397, 1: 0.126027397, 2: 0.083333333, 3: 0.043835616, 6: 0, 0: 0, 'DEF': 0.043835616},
    mes_mas(Mesesp, -9): {'NA': 0.210958904, 1: 0.210958904, 2: 0.166666667, 3: 0.128767123, 6: 0.005479452, 0: 0, 'DEF': 0.128767123},
    mes_mas(Mesesp, -8): {'NA': 0.295890411, 1: 0.295890411, 2: 0.25, 3: 0.21369863, 6: 0.08630137, 0: 0, 'DEF': 0.21369863},
    mes_mas(Mesesp, -7): {'NA': 0.37260274, 1: 0.37260274, 2: 0.333333333, 3: 0.290410959, 6: 0.167123288, 0: 0, 'DEF': 0.290410959},
    mes_mas(Mesesp, -6): {'NA': 0.457534247, 1: 0.457534247, 2: 0.416666667, 3: 0.375342466, 6: 0.252054795, 0: 0, 'DEF': 0.375342466},
    mes_mas(Mesesp, -5): {'NA': 0.539726027, 1: 0.539726027, 2: 0.5, 3: 0.457534247, 6: 0.334246575, 0: 0.087671233, 'DEF': 0.457534247},
    mes_mas(Mesesp, -4): {'NA': 0.624657534, 1: 0.624657534, 2: 0.583333333, 3: 0.542465753, 6: 0.419178082, 0: 0.17260274, 'DEF': 0.542465753},
    mes_mas(Mesesp, -3): {'NA': 0.706849315, 1: 0.706849315, 2: 0.666666667, 3: 0.624657534, 6:  0.501369863, 0: 0.254794521, 'DEF': 0.624657534},
    mes_mas(Mesesp, -2): {'NA': 0.791780822, 1: 0.791780822, 2: 0.75, 3: 0.709589041, 6: 0.58630137, 0: 0.339726027, 'DEF': 0.709589041},
    mes_mas(Mesesp, -1): {'NA': 0.876712329, 1: 0.876712329, 2: 0.833333333, 3: 0.794520548, 6: 0.671232877, 0: 0.424657534, 'DEF': 0.794520548},
    Mesesp: {'NA': 0.95890411, 1: 0.95890411, 2: 0.916666667, 3: 0.876712329, 6: 0.753424658, 0: 0.506849315, 'DEF': 0.876712329}}

    mes_calculo = mes + 1
    zAñoRef = zAño 
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
    AuxMesI =  zAñoRef * 100
    AuxMesF = zAñoRef * 100 + mes_calculo
    print(f'Inicio cálculo escenario 4 para {Meses}')
    xReforecast_Real = ConsultaReal_USD(xRRC,xIS_CAT,mes_calculo)
   
    
    df_PPTO = ConsultaPPTO(mes_calculo)

    xColumnas = ['Ramo', f'BELRIESGO{zAño}_TCVal', f'BELGASTO{zAño}_TCVal', f'IRR{zAño}_TCVal', f'MR{zAño}_TCVal']
    df_reforecast_real = xReforecast_Real.reindex(columns=xColumnas)
    df_reforecast_real= df_reforecast_real.rename(columns={
                            f"BELRIESGO{zAño}_TCVal":f"BELRIESGO{zAño}",
                            f"BELGASTO{zAño}_TCVal":f"BELGASTO{zAño}",
                            f"IRR{zAño}_TCVal":f"IRR{zAño}",
                            f"MR{zAño}_TCVal":f"MR{zAño}"})

    xColumnas = ['Ramo', f'BELRIESGO{zAño}', f'BELGASTO{zAño}', f'IRR{zAño}', f'MR{zAño}']
    df_reforecast_ppto = df_PPTO.reindex(columns=xColumnas)
    xReforecast = pd.concat([df_reforecast_real,df_reforecast_ppto],axis=0)

    xReforecast[f'BRUTO{zAño}'] = xReforecast.apply(lambda row: -row[f'BELRIESGO{zAño}'] - row[f'BELGASTO{zAño}'] - row[f'MR{zAño}'], axis = 1)
    xReforecast[f'NETO{zAño}'] = xReforecast.apply(lambda row: row[f'BRUTO{zAño}'] + row[f'IRR{zAño}'], axis = 1)
    xReforecast['Reserva'] = 'RRC'
    xReforecast['Periodo'] = f'{zAño}12-{mes_calculo}'


    auxReforecast = xReforecast.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxReforecast = auxReforecast.reset_index()
    auxReforecast.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    auxReforecast_sum = auxReforecast.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxReforecast_sum['Tipo de Monto'] = auxReforecast_sum['Origen'].apply(lambda x: xEscenario[x][0])
    auxReforecast_sum['Escenario'] = auxReforecast_sum['Origen'].apply(lambda x: xEscenario[x][1])
    auxReforecast_sum['Monto_USD'] = auxReforecast_sum['Monto']
    auxReforecast_sum['Periodo2'] = zAño * 100 + 12

    auxReforecast_sum= auxReforecast_sum.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo2", right_on="cTCAD_FecAMD")
    auxReforecast_sum['TC'] = auxReforecast_sum['cTCAD_Mnt']
    auxReforecast_sum['Monto_MXN'] = auxReforecast_sum.apply(lambda row: row['Monto_USD'] * row['TC'], axis = 1)
    
    df_final_reforecast = auxReforecast_sum.drop(['Origen', 'Monto','Periodo2'], axis=1)
    df.append(df_final_reforecast)
    print(f'Fin cálculo escenario 4 para {Meses}')
    


df_concatenado = pd.concat(df, ignore_index=True)
xRRC_saldos = pd.concat([df_concatenado,xEsc_base],axis=0)
xRRC_saldos = xRRC_saldos.drop(["cTCAD_FecAMD","cTCAD_Mnt"], axis=1)
xRRC_saldos = xRRC_saldos.drop_duplicates()

Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'TC', 'Monto_USD']
xRRC_saldos = xRRC_saldos[Columnas]

print(f'Fin concatenación df')
print(f'Inicio creación xlsx')
fileName = Path(cfg.CARPETA_SALIDA) / "RRC_esc.xlsx"              ### INSUMOS BD: salida en la carpeta local
xRRC_saldos.to_excel(fileName, index=False)
INS.exportar(Path(cfg.CARPETA_SALIDA) / "Parametros_usados_RRC.xlsx", zAño,
             csv_duracion=getattr(cfg, "CSV_DURACION_RRC", None), csv_is_cat=getattr(cfg, "CSV_IS_CAT", None))
print(f'Saldos en {fileName}; insumos usados en Parametros_usados_RRC.xlsx')
for _a in INS.avisos_texto():
    print('   AVISO:', _a)

end_time = time.perf_counter()
elapsed_time = end_time - start_time
print("Elapsed time: ", elapsed_time)
