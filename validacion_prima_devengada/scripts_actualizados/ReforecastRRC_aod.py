#RESREVA RRC
import pyodbc
import pandas as pd
import time
import warnings
import openpyxl
import numpy as np
import getpass
import os 
import sys
usuario = "asunad"
warnings.filterwarnings('ignore')
start_time = time.perf_counter()

#%% FND CALIBRADO (MEC v3) — sustituye la búsqueda en xPND
# mec_devengamiento.py y delta_calibrado.json deben estar en esta misma carpeta.
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
import mec_devengamiento as mec

USAR_FND_CALIBRADO = True   # False -> comportamiento idéntico al script original (xPND)
DELTA_FND = mec.cargar_delta(_DIR)      # lee delta_calibrado.json si existe
MES_VALUACION = None                    # AAAAMM de la valuación; se fija en el ciclo


def fnd_cal(ramo, calmonth, valorfrec_legado=0.0):
    """FND de una cuenta proporcional/facultativa: tabla calibrada por antigüedad de
    REGISTRO respecto al mes de valuación. `valorfrec_legado` es el valor de xPND que
    se usaría hoy; se devuelve si el FND calibrado está desactivado o falta el mes."""
    if not USAR_FND_CALIBRADO or MES_VALUACION is None:
        return valorfrec_legado
    k = mec.antiguedad_registro(MES_VALUACION, calmonth)
    if k is None:
        return valorfrec_legado
    return 0.0 if k < 0 else mec.fnd_registro(ramo, k, DELTA_FND)

#%% CARPETA LOCAL — todos los insumos se leen y todas las salidas se escriben aquí
# Es la carpeta donde está este script (Documents). Si quieres otra, pon la ruta completa.
CARPETA = _DIR

#%% TABLAS CSV
xFolder = CARPETA

xFolder = CARPETA
xRamo = pd.read_excel(f"{xFolder}\\CentralizadoCatálogos_SIRECySAP.xlsx", sheet_name="Valores", usecols="J:M", skiprows=1)
xPais = pd.read_excel(f"{xFolder}\\CentralizadoCatálogos_SIRECySAP.xlsx", sheet_name="Valores", usecols="O:T", skiprows=1)

xFolder = CARPETA
xLlavesPol = pd.read_csv(f"{xFolder}\\LlavesPol.csv")
xRRC = pd.read_csv(f"{xFolder}\\ParametrosMensPPTO_3+9.csv")
xIS_CAT = pd.read_csv(f"{xFolder}\\IS_Cat.csv")
xAjManuales = pd.read_csv(f"{xFolder}\\AjManuales.csv") 
xRRC_PPTO = pd.read_csv(f"{xFolder}\\ParametrosMensPPTO_3+9.csv")
xIS_CAT_PPTO = pd.read_csv(f"{xFolder}\\IS_Cat_PPTO.csv")
xEsc_base = pd.read_csv(f"{xFolder}\\Escenario_base_RRC.csv")
xSubramo = pd.read_csv(f"{xFolder}\\Subramo.csv")
xIS_BEL_MEDIA = xIS_CAT_PPTO 
xCesionPI = pd.read_csv(f"{xFolder}\\CesionPI.csv")
zAFUN = pd.read_csv(f"{xFolder}\\AFUN.csv")
zFrecuencias = pd.read_csv(f"{xFolder}\\zFrecuencias.csv")
xTablaCesion = pd.read_csv(f"{xFolder}\\TablaCesion_Esc1.csv")
Cesion_Esp = pd.read_csv(f"{xFolder}\\Cesion ID Esp.csv")

#%% DICCIONARIOS
xNoRamo = { 'Vida' : 10, "Acc Per." : 31, "GMM" : 35, "Salud" : 39, "Resp. Civil" : 40, 
          "MyT" : 50, "Incendio" : 60, "Terremoto": 71, "HyORH": 73, "Agropecuario": 80, "Autos" : 90, "Crédito" : 100, "Diversos" : 110}

xEscenario = {"BELRIESGO2026_TCVal":["BEL", 2],
        "BELGASTO2026_TCVal":["BELG",2],
        "IRR2026_TCVal":["IRR",2],
        "MR2026_TCVal":["MR",2],
        "BRUTO_TCVal":["BRUTO",2],
        "NETO_TCVal":["NETO",2],
        "BELRIESGO2026_TCAñoAnt":["BEL",5],
        "BELGASTO2026_TCAñoAnt":["BELG",5],
        "IRR2026_TCAñoAnt":["IRR",5],
        "MR2026_TCAñoAnt":["MR",5],
        "BRUTO_TCAñoAnt":["BRUTO",5],
        "NETO_TCAñoAnt":["NETO",5],
        "BELRIESGO2026":["BEL", 4],
        "BELGASTO2026":["BELG",4],
        "IRR2026":["IRR",4],
        "MR2026":["MR",4],
        "BRUTO2026":["BRUTO",4],
        "NETO2026":["NETO",4]}

xTC_PPTO = {202512:18.008,202601:19.0333,202602:19.0667,
            202603:19.1,202604:19.1333,202605:19.1667,
            202606:19.2,202607:19.2333,202608:19.2667,
            202609:19.3,202610:19.3333,202611:19.3667,
            202612:19.4}

#%% VARIABLES INPUT
zMes = 12
zAño = 2026
Nomeses = [1,12]

COC = 0.1
BC_SONR_2026 = 0
RCS = 2227189146.47
BC = -1007920806


#%% PROYECCIÓN TC USD A FINAL DE AÑO
def ConsultaMoneda_usd():
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
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

TC_USD = ConsultaMoneda_usd()

xFolder = CARPETA
fileName = f"{xFolder}\\TablaTCRRC.xlsx"

TC_USD.to_excel(fileName, index=False)

# Función para obtener el siguiente mes en formato AAAAMM
def siguiente_mes(fecha):
    anio = fecha // 100
    mes = fecha % 100
    if mes == 12:
        return (anio + 1) * 100 + 1
    else:
        return anio * 100 + (mes + 1)

num_proyecciones = 12 - zMes
# Generar pryección
for i in range(num_proyecciones):
    ultimos_dos = TC_USD['cTCAD_Mnt'].iloc[-2:].mean()
    nueva_fecha = siguiente_mes(TC_USD['cTCAD_FecAMD'].iloc[-1])
    TC_USD = pd.concat([TC_USD, pd.DataFrame({'cTCAD_FecAMD': [nueva_fecha], 'cTCAD_Mnt': [ultimos_dos]})], ignore_index=True)


def zPorcCesion(xCesion, zTablaCesion, zCesionPI, xSusc, xPorCed, xPorCedEsp, xTipoRea):
    AñoRef = 2026
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
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
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
    
    # Conexión y consulta BD Gonz
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
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
    ConsultaR= ConsultaR.merge(IS[["Ramo","Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto", f"IS Bel Media-12", f"IS Bel 99.5%-12"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "Ind. Gasto":"BELGASTO",
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
    lambda row: fnd_cal(row['Ramo'], row['CALMONTH'],
                        xPND.get(row['CALMONTH'], 0).get(str(row['FRECUENCIA']), 0)),
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
    ConsultaR['BELRIESGO2026_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR['BELGASTO2026_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR['IRR2026_TCVal'] = ConsultaR.apply(lambda row: row['BELRIESGO2026_TCVal']*row['CESION'], axis = 1)
    
    
    ConsultaR['DESVIACION2026'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    BC_RRC_2026 = ConsultaR[f'DESVIACION2026'].sum()
    BC_2026 = BC_RRC_2026 + BC_SONR_2026
    
    BC = -1139984032.15/20 
    RCS = 105000000/20 
    COC = 0.1
    
    ConsultaR['MR2026_TCVal'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2026']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2026), axis = 1)
    
    
    ConsultaR['PMADEV_2026'] = ConsultaR.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    ConsultaR['BELRIESGO2026_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR['BELGASTO2026_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR['IRR2026_TCAñoAnt'] = ConsultaR.apply(lambda row: row['BELRIESGO2026_TCAñoAnt']*row['CESION'], axis = 1)																											
    ConsultaR['MR2026_TCAñoAnt'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2026']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2026), axis = 1)
    

    xColumnas = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 
             'CiaTom', 'CtoTom', 'Susc', 'Período', 'CALMONTH', 'IniVig', 'FinVig', 
             'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal','PmaTom_sERNal', 'PrimaCedidaNal',
             'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION','BELMEDIA', 
             'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'VALORFREC', 'PORC_ND', 'CEDIDA', 
             'TC_Valuación', 'TC_CierreAnterior', 'PMADEV_2026', 'DESVIACION2026', 'BELRIESGO2026_TCVal', 'BELGASTO2026_TCVal',
             'IRR2026_TCVal', 'MR2026_TCVal', 'BELRIESGO2026_TCAñoAnt', 'BELGASTO2026_TCAñoAnt', 'IRR2026_TCAñoAnt', 'MR2026_TCAñoAnt']

    ConsultaR = ConsultaR.reindex(columns=xColumnas, fill_value='')
    #ConsultaR = pd.concat([ConsultaR,xAjManuales],axis=0) 
   
    xFolder = CARPETA
    fileName = f"{xFolder}\\ConsultaR_RRC_{MES}.xlsx"
    ConsultaR.to_excel(fileName, index=False)

    return ConsultaR

#%% FUNCION RRC REAL

def ConsultaReal(IS,IS_CAT, MES):

    global ConsultaTC, zMes, zFechaValuacion, xLlavesPol, xRamo
    
    # Conexión y consulta BD Gonz
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
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
    ConsultaR= ConsultaR.merge(IS[["Ramo","Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto", f"IS Bel Media-{MES}", f"IS Bel 99.5%-{MES}"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "Ind. Gasto":"BELGASTO",
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
    lambda row: fnd_cal(row['Ramo'], row['CALMONTH'],
                        xPND.get(row['CALMONTH'], 0).get(str(row['FRECUENCIA']), 0)),
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

    #xFolder1 = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Forecasts\2026\Programas\Outputs"
    #fileName = f"{xFolder1}\\ConsultaR.xlsx"
    #ConsultaR.to_excel(fileName, index=False)
    
    ConsultaR['BELRIESGO2026_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA']*row['TC_Valuación'], axis = 1)
    ConsultaR['BELGASTO2026_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO']*row['TC_Valuación'], axis = 1)
    ConsultaR['IRR2026_TCVal'] = ConsultaR.apply(lambda row: row['BELRIESGO2026_TCVal']*row['CESION'], axis = 1)
    ConsultaR['DESVIACION2026'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*row['TC_Valuación']*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    BC_RRC_2026 = ConsultaR[f'DESVIACION2026'].sum()
    BC_2026 = BC_RRC_2026 + BC_SONR_2026
    
    #COC = 0.1
    #RCS = 2227189146.47
    #BC = -1007920806
    
    ConsultaR['MR2026_TCVal'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2026']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2026), axis = 1)
    ConsultaR['PMADEV_2026'] = ConsultaR.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    ConsultaR['BELRIESGO2026_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA']*row['TC_CierreAnterior'], axis = 1)
    ConsultaR['BELGASTO2026_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO']*row['TC_CierreAnterior'], axis = 1)
    ConsultaR['IRR2026_TCAñoAnt'] = ConsultaR.apply(lambda row: row['BELRIESGO2026_TCAñoAnt']*row['CESION'], axis = 1)																											
    ConsultaR['MR2026_TCAñoAnt'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2026']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2026), axis = 1)

    xColumnas = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 
             'CiaTom', 'CtoTom', 'Susc', 'Período', 'CALMONTH', 'IniVig', 'FinVig', 
             'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal','PmaTom_sERNal', 'PrimaCedidaNal',
             'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION','BELMEDIA', 
             'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'PORC_ND', 'CEDIDA', 
             'TC_Valuación', 'TC_CierreAnterior', 'PMADEV_2026', 'DESVIACION2026', 'BELRIESGO2026_TCVal', 'BELGASTO2026_TCVal',
             'IRR2026_TCVal', 'MR2026_TCVal', 'BELRIESGO2026_TCAñoAnt', 'BELGASTO2026_TCAñoAnt', 'IRR2026_TCAñoAnt', 'MR2026_TCAñoAnt']
    
    xFolder = CARPETA
    fileName = f"{xFolder}\\ConsultaPPTO_RRC_{MES}_tradicional.xlsx"
    ConsultaR.to_excel(fileName, index=False)

    ConsultaR = ConsultaR.reindex(columns=xColumnas, fill_value='')
    #ConsultaR = pd.concat([ConsultaR,xAjManuales],axis=0) 
    return ConsultaR


#%% FUNCION RRC MENSUALIZADOS

#%% ESCENARIO 0 Y 1
print('Inicio cálculo escenario 0 y 1')
columnas_finales = ['Reserva', 'Escenario', 'Tipo de Monto','Ramo', 'Periodo', 'Monto_MXN', 'Monto_USD', 'TC']
xEsc_base = xEsc_base[columnas_finales]

#xEsc_base= xEsc_base.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
#                             how="left", left_on="Periodo", right_on="cTCAD_FecAMD")
#xEsc_base['TC'] = xEsc_base['cTCAD_Mnt']
xEsc_base['TC'] =  xEsc_base.apply(lambda row: xTC_PPTO[row['Periodo']],axis=1)
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

    zFechaValuacion = f'{dia}/{AuxMes}{mes_calculo}/2026'
    AuxMesI =  zAñoRef * 100 + mes_calculo
    AuxMesF = AuxMesI + 100

    Meses = zAño*100 + mes_calculo 
    Mesesppto = zAño*100 + zMes
    MES_VALUACION = Meses          # el FND se corta en el mes de VALUACIÓN

    print(f'Inicio cálculo escenario 2 para {Meses}')

    xAños ={202612:202612, 202611:202611, 202610:202610, 202609:202609, 202608:202608, 202607:202607, 202606:202606, 202605:202605, 202604:202604, 202603:202603, 202602:202602, 202601:202601,
            202600:202512, 202599:202511, 202598:202510, 202597:202509, 202596:202508, 202595:202507, 202594:202506, 202593:202505, 202592:202504, 202591:202503, 202590:202502, 202589:202501}
    
    xPND = {
        xAños[Meses - 11]: {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
        xAños[Meses - 10]: {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
        xAños[Meses - 9]: {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
        xAños[Meses - 8]: {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
        xAños[Meses - 7]: {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
        xAños[Meses - 6]: {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
        xAños[Meses - 5]: {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
        xAños[Meses - 4]: {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
        xAños[Meses - 3]: {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
        xAños[Meses - 2]: {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
        xAños[Meses - 1]: {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
        xAños[Meses]: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329}}

    df_Real_IS_Real = ConsultaReal(xRRC,xIS_CAT,mes_calculo)

    ##Meses ppto escenario 2
    xColumnas = ['Ramo', 'BELRIESGO2026_TCVal', 'BELGASTO2026_TCVal', 'IRR2026_TCVal', 'MR2026_TCVal',
                'BELRIESGO2026_TCAñoAnt', 'BELGASTO2026_TCAñoAnt', 'IRR2026_TCAñoAnt', 'MR2026_TCAñoAnt']

    df_RRC_dim = df_Real_IS_Real.reindex(columns=xColumnas)
    df_RRC_dim['BRUTO_TCVal'] = df_RRC_dim.apply(lambda row: -row['BELRIESGO2026_TCVal'] - row['BELGASTO2026_TCVal'] - row['MR2026_TCVal'], axis = 1)
    df_RRC_dim['NETO_TCVal'] = df_RRC_dim.apply(lambda row: row['BRUTO_TCVal'] + row['IRR2026_TCVal'], axis = 1)
    df_RRC_dim['BRUTO_TCAñoAnt'] = df_RRC_dim.apply(lambda row: -row['BELRIESGO2026_TCAñoAnt'] - row['BELGASTO2026_TCAñoAnt'] - row['MR2026_TCAñoAnt'], axis = 1)
    df_RRC_dim['NETO_TCAñoAnt'] = df_RRC_dim.apply(lambda row: row['BRUTO_TCAñoAnt'] + row['IRR2026_TCAñoAnt'], axis = 1)
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

    xColumnas = ['Ramo', 'BELRIESGO2026_TCVal', 'BELGASTO2026_TCVal', 'IRR2026_TCVal', 'MR2026_TCVal']

    df_RRC_dim_3 = df_Real_IS_Real.reindex(columns=xColumnas)
    df_RRC_dim_3['BRUTO_TCVal'] = df_RRC_dim_3.apply(lambda row: -row['BELRIESGO2026_TCVal'] - row['BELGASTO2026_TCVal'] - row['MR2026_TCVal'], axis = 1)
    df_RRC_dim_3['NETO_TCVal'] = df_RRC_dim_3.apply(lambda row: row['BRUTO_TCVal'] + row['IRR2026_TCVal'], axis = 1)
    #df_RRC_dim_3['BRUTO_TCAñoAnt'] = df_RRC_dim_3.apply(lambda row: -row['BELRIESGO2026_TCAñoAnt'] - row['BELGASTO2026_TCAñoAnt'] - row['MR2026_TCAñoAnt'], axis = 1)
    #df_RRC_dim_3['NETO_TCAñoAnt'] = df_RRC_dim_3.apply(lambda row: row['BRUTO_TCAñoAnt'] + row['IRR2026_TCAñoAnt'], axis = 1)
    df_RRC_dim_3['Reserva'] = 'RRC'
    df_RRC_dim_3['Periodo'] = f'{zAño}{AuxMes}{mes_calculo}'


    auxRRC_3 = df_RRC_dim_3.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxRRC_3 = auxRRC_3.reset_index()
    auxRRC_3.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    auxRRC_sum_3 = auxRRC_3.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxRRC_sum_3['Tipo de Monto'] = auxRRC_sum_3['Origen'].apply(lambda x: xEscenario[x][0])
    
    Meses_falt_3 = xEsc_base[xEsc_base["Periodo"] > Mesesppto]
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
    


df_concatenado = pd.concat(df, ignore_index=True)
xRRC_saldos = pd.concat([df_concatenado,xEsc_base],axis=0)
xRRC_saldos = xRRC_saldos.drop_duplicates()

Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'TC', 'Monto_USD']
xRRC_saldos = xRRC_saldos[Columnas]

print(f'Fin concatenación df')
print(f'Inicio creación xlsx')

xFolder = CARPETA
# el nombre de la salida dice con qué FND se corrió, para compararla contra RRC_esc.xlsx sin pisarlo
fileName = f"{xFolder}\\{'RRC_esc_FNDcal.xlsx' if USAR_FND_CALIBRADO else 'RRC_esc_legado.xlsx'}"
print(f"[RRC] Salida escrita en: {fileName}")

xRRC_saldos.to_excel(fileName, index=False)

end_time = time.perf_counter()
elapsed_time = end_time - start_time
print("Elapsed time: ", elapsed_time)