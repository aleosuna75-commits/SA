# Importar Librerías
import pyodbc
import pandas as pd
import time
import warnings
from datetime import datetime
import numpy as np
warnings.filterwarnings('ignore')
start_time = time.perf_counter()


#Parametros iniciales
zMes = 12
zAñoReal = 2026
zAñoPpto = 2027

Meses = zAñoReal*100 + zMes + 1 
zAñoMesPPTO = zAñoPpto*100 + zMes
AnioPiv_1 = zAñoPpto - 10
AnioPiv_2 = zAñoPpto - 3

if zMes < 10:
    AuxMes = 0
else:
    AuxMes= ""

if zMes == 2:
    dia = 28
elif zMes in [1,3,5,7,8,10,12]:
    dia = 31
else:
    dia = 30

zFechaValuacion = f'{dia}/{AuxMes}{zMes}/2026'
zFechaValuacion2 = f'31/03/2026'
zFechaValuacion = pd.Timestamp(zFechaValuacion)

BC_SONR_2025 = -284975100.558635
BC_SONR_2026 = -518556955.380801
BC_SONR_2027 = -610659192.37917
BC_SONR_2028 = -779172209.924872
BC_SONR_2029 = -636838690.917713
RCS = 113000000
COC = 0.1


BC = -1007920806 #-1139984032.15
RCS = 113000000 #105000000
COC = 0.1

tc_CIERRE={202502:19.5,202503:19.5,202504:19.5,202505:19.5,202506:19.5,202507:19.5,202508:19.5, 202509:19.5 , 202510:19.5 , 202511:19.5 ,
        202512:19.5,202601:19.0333,202602:19.0667,202603:19.1000,
        202604:19.1333,202605:19.1667,202606:19.2000,202607:19.2333,
        202608:19.2667,202609:19.3000,202610:19.3333,202611:19.3667,
        202612:19.4000,202712:20.2899189189189,202812:21.0000660810811,202912:21.7350683939189,203012:22.4957957877061
         }

xAños ={202502:202502, 202503:202503, 202504:202504, 202505:202505, 202506:202506, 202507:202507, 202508:202508, 202509:202509, 202510:202510, 202511:202511, 202512:202512, 
        202513:202601, 202514:202602, 202515:202603, 202516:202604, 202517:202605, 202518:202606, 202519:202607, 202520:202608, 202521:202609, 202522:202610, 202523:202611, 202524:202612}

xPND = {
    xAños[Meses]: {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
    xAños[Meses + 1]: {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
    xAños[Meses + 2]: {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
    xAños[Meses + 3]: {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
    xAños[Meses + 4]: {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
    xAños[Meses + 5]: {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
    xAños[Meses + 6]: {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
    xAños[Meses + 7]: {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
    xAños[Meses + 8]: {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
    xAños[Meses + 9]: {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
    xAños[Meses + 10]: {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
    xAños[Meses + 11]: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
}

xPND2 = {
    xAños[Meses]: {'NA': 0.043835616, 1: 0.043835616, 2: 0, 3: 0, 6: 0, 0: 0, 'DEF': 0},
    xAños[Meses + 1]: {'NA': 0.126027397, 1: 0.126027397, 2: 0.083333333, 3: 0.043835616, 6: 0, 0: 0, 'DEF': 0.043835616},
    xAños[Meses + 2]: {'NA': 0.210958904, 1: 0.210958904, 2: 0.166666667, 3: 0.128767123, 6: 0.005479452, 0: 0, 'DEF': 0.128767123},
    xAños[Meses + 3]: {'NA': 0.295890411, 1: 0.295890411, 2: 0.25, 3: 0.21369863, 6: 0.08630137, 0: 0, 'DEF': 0.21369863},
    xAños[Meses + 4]: {'NA': 0.37260274, 1: 0.37260274, 2: 0.333333333, 3: 0.290410959, 6: 0.167123288, 0: 0, 'DEF': 0.290410959},
    xAños[Meses + 5]: {'NA': 0.457534247, 1: 0.457534247, 2: 0.416666667, 3: 0.375342466, 6: 0.252054795, 0: 0, 'DEF': 0.375342466},
    xAños[Meses + 6]: {'NA': 0.539726027, 1: 0.539726027, 2: 0.5, 3: 0.457534247, 6: 0.334246575, 0: 0.087671233, 'DEF': 0.457534247},
    xAños[Meses + 7]: {'NA': 0.624657534, 1: 0.624657534, 2: 0.583333333, 3: 0.542465753, 6: 0.419178082, 0: 0.17260274, 'DEF': 0.542465753},
    xAños[Meses + 8]: {'NA': 0.706849315, 1: 0.706849315, 2: 0.666666667, 3: 0.624657534, 6:  0.501369863, 0: 0.254794521, 'DEF': 0.624657534},
    xAños[Meses + 9]: {'NA': 0.791780822, 1: 0.791780822, 2: 0.75, 3: 0.709589041, 6: 0.58630137, 0: 0.339726027, 'DEF': 0.709589041},
    xAños[Meses + 10]: {'NA': 0.876712329, 1: 0.876712329, 2: 0.833333333, 3: 0.794520548, 6: 0.671232877, 0: 0.424657534, 'DEF': 0.794520548},
    xAños[Meses + 11]: {'NA': 0.95890411, 1: 0.95890411, 2: 0.916666667, 3: 0.876712329, 6: 0.753424658, 0: 0.506849315, 'DEF': 0.876712329},
}


xCesionPI = {
    10: {'2023': 0.0095, '2024': 0.0078, '2025': 0.006, '2026': 0.0014, '2027': 0.0013, '2028': 0.0013},
    31: {'2023': 0.0095, '2024': 0.0078, '2025': 0.006, '2026': 0.0014, '2027': 0.0013, '2028': 0.0013},
    35: {'2023': 0.0095, '2024': 0.0078, '2025': 0.006, '2026': 0.0014, '2027': 0.0013, '2028': 0.0013},
    39: {'2023': 0.0095, '2024': 0.0078, '2025': 0.006, '2026': 0.0014, '2027': 0.0013, '2028': 0.0013},
    40: {'2023': 0.009, '2024': 0.0146, '2025': 0.011, '2026': 0.0025, '2027': 0.0024, '2028': 0.0023},
    50: {'2023': 0.0117, '2024': 0.013, '2025': 0.0082, '2026': 0.002, '2027': 0.0019, '2028': 0.0019},
    60: {'2023': 0.0139, '2024': 0.035558719, '2025': 0.0085, '2026': 0.002, '2027': 0.0019, '2028': 0.0018},
    71: {'2023': 0.0139, '2024': 0.035558719, '2025': 0.0355, '2026': 0.0088, '2027': 0.009, '2028': 0.0091},
    73: {'2023': 0.0139, '2024': 0.035558719, '2025': 0.0355, '2026': 0.0088, '2027':  0.009, '2028': 0.0091},
    80: {'2023': 0.0108, '2024': 0.0076, '2025': 0.0092, '2026': 0.0022, '2027': 0.0021, '2028': 0.002},
    90: {'2023': 0.0139, '2024': 0.0191, '2025': 0.0555, '2026': 0.014, '2027': 0.0147, '2028': 0.0152},
    100: {'2023': 0.0286, '2024': 0.0241, '2025': 0.0148, '2026': 0.0034, '2027': 0.0033, '2028': 0.0032},
    110: {'2023': 0.0038, '2024': 0.035558719, '2025': 0.0058, '2026': 0.0014, '2027': 0.0015, '2028': 0.0015},
}


#Archivos Tablas Aux

import getpass
usuario = getpass.getuser()

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2026"
xRRC = pd.read_csv(f"{xFolder}\\6_Recalibración\\0_Integración\Inputs\ParametrosMens2026.csv")
xTablaCesion = pd.read_csv(f"{xFolder}\\4_Generacion\\03 Reservas\Inputs scripts\TablaCesion.csv")
xPais = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\Pais.csv")
xSubramo = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\Subramo.csv")
xFrecCol = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\FrecCol.csv")
xIS_BEL_MEDIA = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\IS_Cat.csv") #ACTUALIZAR
zAFUN = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\AFUN.csv")
xCesionPI = pd.read_csv(f"{xFolder}\\4_Generacion\\03 Reservas\Inputs scripts\CesionPI.csv") #AÑO PASADO
zFrecuencias = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\zFrecuencias.csv") #ACTUALIZAR
Cesion_Esp = pd.read_csv(f"{xFolder}\\4_Generacion\\0_Integración\Inputs scripts\Cesion ID Esp.csv") #ACTUALIZAR

# Conexión y consulta BD Gonz
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

tMovGG = pd.read_sql(xSQL, conn)
conn.close()


ConsultaTC = pd.DataFrame(tMovGG)

ConsultaTC_Temporal = pd.DataFrame(tMovGG)
ConsultaTC['Vacio'] = ''
ConsultaTC_Temporal['LlaveTC_Temporal'] = ConsultaTC[['cTCAD_FecAMD', 'Vacio']].apply(lambda x: '-31'.join(x.astype('str')), axis=1)
ConsultaTC_Temporal = ConsultaTC_Temporal.merge(ConsultaTC[["Llave","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="LlaveTC_Temporal", right_on="Llave")

ConsultaTC = ConsultaTC_Temporal
ConsultaTC['TC_USD'] = ConsultaTC.apply(lambda row: row['cTCAD_Mnt_x']/row['cTCAD_Mnt_y'], axis = 1)

def zLN(xRamo, xTerritorio, xTR, xSusc, xOfiRep):

    if xRamo == 80:
        return 'LN04008' #"Daños Facultativos Sur y Agropecuario" #LN4008
    elif xRamo == 10 or (xRamo<= 39 and xRamo >= 30):
        return 'LN04004' #"Vida, Accidentes y Enfermedades" #LN4004
    elif xRamo<= 170 and xRamo >= 100:
        return 'LN04003' #"Fianzas y Crédito" #LN04003
    elif xTerritorio == "R05":
        if xSusc >= 2022:
            return 'LN04009' #"Daños Ultramar Londres"  #LN04009
        elif xSusc == 2021 and xOfiRep == 1:
            return 'LN04009' #"Daños Ultramar Londres"  #LN04009
        else: return 'LN04006' #"Daños Líneas Especiales"  #LN04006
    elif xTerritorio == "R03" or xTerritorio == "R04":
        if xTR < 3:
            return 'LN04005' #"Daños Contratos Sur"  #LN04005
        else: return 'LN04008' #"Daños Facultativos Sur y Agropecuario"  #LN04008
    elif xTR < 3:
        return 'LN04001' #"Daños Contratos Norte"  #LN04001
    elif xTR == 3:
        return 'LN04002' #"Daños Facultativos Norte"  #LN04002

    return None  # Si no coincide con ningún caso

def zCesionPI(xRow):
    if xRow["ZSUSCYEAR"] >= 2023:
        xAUX_PI = xCesionPI.loc[xCesionPI["Ramo"]==xRow["Ramo"],xRow["ZSUSCYEAR"]]
    else:
        xAUX_PI = 0    
    return(xAUX_PI)    

def zPorcCesion_v3(xRow): #xCesion, xTipoRea, xLlave, xSusc, xLlaveCto): str(y['ZSUSCYEAR'])
    if xRow["ZTIPOCES"] ==1 :
        zCed = max(xTablaCesion.loc[xTablaCesion["Llave"]==xRow["LLAVE3"],str(xRow["ZSUSCYEAR"])],default=0)
    elif xRow["ZTIPOCES"] ==2:
        if xRow["ZTIPOREAS"] == 3:
            zCed = float(xRow["PRODUCT"])
        elif xRow["LLAVE2"] in Cesion_Esp["Llave"].values:
            zCed = max(Cesion_Esp.loc[Cesion_Esp["Llave"]==xRow["LLAVE1"],"Porcentaje Cedido"])
        else:
            zCed = max(xTablaCesion.loc[xTablaCesion["Llave"]==xRow["LLAVE3"],str(xRow["ZSUSCYEAR"])],default=0)
    elif xRow["ZTIPOCES"] == 3 :
        zCed = 1
    else:
        zCed = 0
    xPorcCesion = max(zCed ,0)
    return(xPorcCesion)


#zPorcCesion(y['ZTIPOCES'], y[str(y['ZSUSCYEAR'])], y[str(y['ZSUSCYEAR'] * 100)], y['ZSUSCYEAR'], y['PRODUCT'], y['Porcentaje Cedido'])
def zPorcCesion(xCesion, zTablaCesion, zCesionPI, xSusc, xPorCed, xPorCedEsp, xTipoRea):
    AñoRef = 2025
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
            zCed = xPorCedEsp
        else:
            zCed = zTablaCesion
    elif xCesion == 3:
        zCed = 1
    elif xCesion == 4:
        zCed = 0

    zCed = max(zCed, 0)
    zRet = 1 - zCed
    return zCed + (zRet*xAUX_PI)

def ConsultaReal():

    global xPais, xSubramo, ConsultaTC, xRRC, xIS_BEL_MEDIA, BC, RCS, COC, tc_CIERRE, zAñoMesPPTO, zMes, xPND, zFechaValuacion
    
    # Conexión y consulta BD Gonz
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    #zLlavesPol = "','".join(list(xLlavesPol["Llave"].values)) 

    xSelect = "Select SRamo, Pais, TipoRea, OfiRepPt, MonedaOri, CorrTom, CiaTom, CtoTom, Susc, Período, aPog_MesProc AS CALMONTH, IniVig, FinVig, " \
              "CDbl(Sum(Val(PriTomOri5)+Val(PriTomEnCOri5)+Val(PriTomReCOri5))) as PrimaTomadaOri, " \
              "CDbl(Sum(Val(PriTomOri5))) as PmaTom_sEROri, CDbl(Sum(Val(PriCedOri5))) as PrimaCedidaOri " 
    
    xTabla = "From dbo_aMOG_MovGonzalo "

    xWhere = f" Where ((Val(aPog_MesProc) > {zAñoReal}{AuxMes}{zMes} and Val(aPog_MesProc) <= 202512)  or ( FinVig > {zFechaValuacion2} and IniVig < {zFechaValuacion2}))" \
            f" and Tipo=5 and Ramo < 130 and Período <> 9  " \
                f"  and ((Val(PriTomOri5)+Val(PriTomEnCOri5)+Val(PriTomReCOri5) < 0) or (Val(left(aPog_MesProc,4)) <= Susc) ) " #\
                    #f"and (aPOG_MesProc & '-' & cNAT_IdTPol & '-' & TipoRea & '-' & aPOG_Num not in ('{zLlavesPol}') ) "
    
    xGroup = " Group By SRamo, Pais, TipoRea, OfiRepPt, MonedaOri, CorrTom, CiaTom, CtoTom, Susc, Período, aPog_MesProc, IniVig, FinVig"
    xOrder = ""

    xSQL = " ".join([xSelect, xTabla, xWhere, xGroup, xOrder])

    tMovGG = pd.read_sql(xSQL, conn)
    conn.close()


    ConsultaR = pd.DataFrame(tMovGG)

    #####AGREGAR COLUMNAS REAL
    ConsultaR= ConsultaR.merge(xPais[["Pais","TerrSAP"]].drop_duplicates(),
                             how="left", left_on="Pais", right_on="Pais")
    ConsultaR = ConsultaR.merge(xSubramo[["SR","Ramo"]].drop_duplicates(),
                             how="left", left_on="SRamo", right_on="SR")
    ConsultaR = ConsultaR.drop('SR', axis=1)
    
    ConsultaR['LLAVE'] = ConsultaR[['CorrTom', 'CiaTom', 'Susc', 'TipoRea']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    ConsultaR['LN2'] = ConsultaR.apply(lambda y: zLN(y['Ramo'], y['TerrSAP'], y['TipoRea'], y['Susc'], y['OfiRepPt']), axis=1)
    ConsultaR['FRECUENCIA'] = ConsultaR.apply(lambda row: row['Período'] if row['TipoRea'] == 1 and row['Ramo'] != 71 and row['Ramo'] != 73 and row['Ramo'] != 100 else 'NA', axis = 1)
    
    ##Cruce TC_USD
    ConsultaR['LlaveTC_Temporal'] = ConsultaR[['CALMONTH', 'MonedaOri']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
    
    ConsultaR = ConsultaR.merge(ConsultaTC[["Llave_x","TC_USD"]].drop_duplicates(),
                             how="left", left_on="LlaveTC_Temporal", right_on="Llave_x")
    ConsultaR = ConsultaR.drop(['LlaveTC_Temporal','Llave_x' ], axis=1)
    ##Cruce TC_USD

    ConsultaR['MONTO_PI_USD'] = ConsultaR.apply(lambda row: row['PmaTom_sEROri']*row['TC_USD'] if row['TipoRea'] == 2 and row['Ramo'] != 71 and row['Ramo'] != 73 else row['PrimaTomadaOri']*row['TC_USD'], axis = 1)
   
    ##Cruce xRRC e IS BEL MEDIA (CAT)
    ConsultaR= ConsultaR.merge(xRRC[["Ramo","Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto", f"IS Bel Media-{zMes}", f"IS Bel 99.5%-{zMes}"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "Ind. Gasto":"BELGASTO",
                            f"IS Bel 99.5%-{zMes}":"BEL99",
                            }),
                             how="left", left_on="Ramo", right_on="Ramo")
    ConsultaR = ConsultaR.merge(xIS_BEL_MEDIA[["IS Bel Media","71", "73"]].drop_duplicates(),
                             how="left", left_on="CALMONTH", right_on="IS Bel Media")

    ##Cruce xRRC e IS BEL MEDIA (CAT)

    ConsultaR['CESION'] = ConsultaR.apply(lambda row: -1*row['PrimaCedidaOri']*row['TC_USD']/row['MONTO_PI_USD'] if row['MONTO_PI_USD'] != 0 else 0, axis = 1)
    ConsultaR['BELMEDIA'] = ConsultaR.apply(lambda row: row['71'] if row['Ramo'] == 71 else (row['73'] if row['Ramo'] == 73 else row[f'IS Bel Media-{zMes}']), axis = 1)
    ConsultaR = ConsultaR.drop(['71','73', f'IS Bel Media-{zMes}', 'IS Bel Media', 'TC_USD'], axis=1)
    

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

    ConsultaR = ConsultaR.drop('VALORFREC', axis=1)

    ConsultaR['CEDIDA'] = ConsultaR.apply(lambda row: row['MONTO_PI_USD']*row['CESION'], axis = 1)
    ConsultaR['TC_Valuación'] =  ConsultaR.apply(lambda row: tc_CIERRE[row['CALMONTH']],axis=1)

    ConsultaR['TC_CierreAnterior'] = ''
    ConsultaR['BELRIESGO2026_r'] = ConsultaR.apply(lambda row: row['MONTO_PI_USD']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR['BELGASTO2026_r'] = ConsultaR.apply(lambda row: row['MONTO_PI_USD']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR['IRR2026_r'] = ConsultaR.apply(lambda row: row['BELRIESGO2026_r']*row['CESION'], axis = 1)
    ConsultaR['DESVIACION2026'] = ConsultaR.apply(lambda row: row['MONTO_PI_USD']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    ConsultaR['MR2026_r'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2026']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC), axis = 1)
    ConsultaR['PMADEV_2025'] = ConsultaR.apply(lambda row: row['MONTO_PI_USD']*(1-row['PORC_ND']), axis = 1)
    ConsultaR['PMANDEV_2026'] = ConsultaR.apply(lambda row: row['MONTO_PI_USD']*(row['PORC_ND']), axis = 1)


    return ConsultaR

def ConsultaPPTO2026():
    global xPais, xSubramo, ConsultaTC, xRRC, xIS_BEL_MEDIA, BC, RCS, COC, tc_CIERRE, zAñoMesPPTO, zMes, zAFUN, AnioPiv_1, AnioPiv_2, xCesionPI, xTablaCesion, zFrecuencias, xPND2, Cesion_Esp
    
    xFolder = fr"C:\Users\mocamachol\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2026\6_Recalibración\xls"
    xFile = fr"{xFolder}\\BD_CtaMens_reservas_0526.xlsx"
    
    ConsultaP = pd.read_excel(xFile, thousands=',')
    ConsultaPPTO = ConsultaP[(ConsultaP["TY"] == 61) & (ConsultaP["PERIODO"] <= zAñoMesPPTO) & (ConsultaP["PERIODO"] > zAñoPpto*100)]

    ConsultaPPTO= ConsultaPPTO.rename(columns={
                            "PERIODO":"CALMONTH",
                            "TY":"GL_ACCT",
                            "MONTO":"AMOUNT",
                            "TERRITORIO":"TWAERS"
                            })

    Columnas = [
    'PROFTCTR', 'ZREGIONRP', 'ZTIPOREAS', 'ZOFICN_RP', 'FUNCAREA', 'ZMGA', 
    'TWAERS', 'ZTIPOCES', 'PORCED', 'ZCORREDOR', 'ZCEDENTE', 'ZCONTRATO', 
    'ZSUSCYEAR', 'CALMONTH', 'AMOUNT','PORC_CESION']

    ConsultaPPTO = ConsultaPPTO[Columnas]


    ConsultaPPTO= ConsultaPPTO.merge(xSubramo[["CeBe","Ramo", "Ramo2"]].drop_duplicates(),
                             how="left", left_on="PROFTCTR", right_on="CeBe")
    
    ConsultaPPTO['Ramo'] = ConsultaPPTO.apply(lambda row: 10 if row['Ramo'] == 20 else row['Ramo'], axis = 1)

    ConsultaPPTO = ConsultaPPTO.drop('CeBe', axis=1)
    

    ConsultaPPTO= ConsultaPPTO.merge(xRRC[["Ramo", "Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto", f"IS Bel Media-{zMes}", f"IS Bel 99.5%-{zMes}"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "Ind. Gasto":"BELGASTO",
                            f"IS Bel 99.5%-{zMes}":"BEL99",
                            f"IS Bel Media-{zMes}":"BELMEDIA"
                            }),
                             how="left", left_on="Ramo", right_on="Ramo")
    ConsultaPPTO = ConsultaPPTO.merge(xIS_BEL_MEDIA[["IS Bel Media","71", "73"]].drop_duplicates(),
                             how="left", left_on="CALMONTH", right_on="IS Bel Media")
    ConsultaPPTO = ConsultaPPTO.drop('IS Bel Media', axis=1)

                            
    
    ConsultaPPTO = ConsultaPPTO.merge(xCesionPI[["Ramo", "2020", "2021", "2022", "2023", "2024","2025", "2026", "2027", "2028", "2029", "2030"]].drop_duplicates()
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
                            "2029":"202900",
                            "2030":"203000"
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
        str(min(int(x['ZSUSCYEAR']) if pd.notna(x['ZSUSCYEAR']) else 2024, 2024)), 
        str(int(x['ZTIPOREAS']) if pd.notna(x['ZTIPOREAS']) else '')  
    ]), axis=1)
        
    
    ConsultaPPTO['LLAVE2'] = ConsultaPPTO[['PROFTCTR', 'CALMONTH', 'TWAERS']].apply(lambda x: '|'.join(x.astype('str')), axis=1)


    ConsultaPPTO = ConsultaPPTO.merge(zFrecuencias[["Llave","Periodo"]].drop_duplicates(),
                             how="left", left_on="LLAVE", right_on="Llave")

    ConsultaPPTO['FRECUENCIA'] = ConsultaPPTO.apply(lambda row: row['Periodo'] if row['ZTIPOREAS'] == 1 and row['Ramo'] != 71 and row['Ramo'] != 73 and row['Ramo'] != 100 else 'NA', axis = 1)
    ConsultaPPTO['FRECUENCIA'] = ConsultaPPTO['FRECUENCIA'].fillna('DEF')
    ConsultaPPTO = ConsultaPPTO.drop('Periodo', axis=1)

    ConsultaPPTO['MONTO_PI'] = ConsultaPPTO['AMOUNT']

    #ConsultaPPTO['LLAVE3'] = ConsultaPPTO[['FUNCAREA','Ramo2', 'ZREGIONRP', 'ZTIPOREAS']].apply(lambda x: '-'.join(x.astype('str')), axis=1)
        
    ConsultaPPTO['LLAVE3'] = (
        ConsultaPPTO[['FUNCAREA', 'Ramo2', 'ZREGIONRP', 'ZTIPOREAS']]
        .fillna('')                       # Evita floats NaN
        .astype(str)                      # Convierte todo a string seguro
        .agg('-'.join, axis=1)            # Concatena sin problemas
    )

    ConsultaPPTO = ConsultaPPTO.merge(xTablaCesion[["Llave", "2020", "2021","2022","2023","2024", "2025", "2026", "2027", "2028", "2029", "2030"]].drop_duplicates(),
                             how="left", left_on="LLAVE3", right_on="Llave")
    
    ConsultaPPTO = ConsultaPPTO.drop('Llave_y', axis=1)

    ConsultaPPTO = ConsultaPPTO.merge(Cesion_Esp[["Llave","Porcentaje Cedido"]].drop_duplicates(),
                             how="left", left_on="LLAVE1", right_on="Llave")
    
    #ConsultaPPTO['CESION'] = ConsultaPPTO.apply(lambda y:zPorcCesion(y['ZTIPOCES'], y[str(y['ZSUSCYEAR'])], y[str(y['ZSUSCYEAR'] * 100)], y['ZSUSCYEAR'], float(y['PORCED']), float(y['Porcentaje Cedido']), y['ZTIPOREAS']), axis=1)
    ConsultaPPTO = ConsultaPPTO.drop(["71","73","2021","2022","2023","2024", "2025", "2026", "2027", "2028", "2029", "2030","202100","202200","202300","202400","202500","202600","202700", "202800","202900","203000", "Llave"], axis=1)
    
    ConsultaPPTO['PORC_ND'] =  ConsultaPPTO.apply(
    lambda row: xPND2.get(row['CALMONTH'], 0).get(row['FRECUENCIA'], 2),axis=1)



    ConsultaPPTO['CEDIDA'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_CESION'], axis = 1)
    ConsultaPPTO['TC_Valuación'] =  ConsultaPPTO.apply(lambda row: tc_CIERRE[row['CALMONTH']],axis=1)
    ConsultaPPTO['TC_CierreAnterior'] = ''
    ConsultaPPTO['BELRIESGO2026_p'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaPPTO['BELGASTO2026_p'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaPPTO['IRR2026_p'] = ConsultaPPTO.apply(lambda row: row['BELRIESGO2026_p']*row['PORC_CESION'], axis = 1)
    ConsultaPPTO['DESVIACION2026'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['TWAERS'] == "México" else row['RETOTR']), axis = 1)
    ConsultaPPTO['MR2026_p'] = ConsultaPPTO.apply(lambda row: -1*row['DESVIACION2026']*RCS*COC*(row['DURMXN'] if row['TWAERS'] == "México" else (row['DUROTR']))*(1/BC), axis = 1)
    ConsultaPPTO['PMADEV_2026'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)
    ConsultaPPTO['PMANDEV_2026'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND'], axis = 1)

    print(ConsultaPPTO)

    return ConsultaPPTO





if zMes == 12:
    df_PPTO = ConsultaPPTO2026()
    df_ppto_real = pd.DataFrame()
else:
    df_Real = ConsultaReal()
    df_PPTO = ConsultaPPTO2026()

    xColumnas = ['Ramo', 'TipoRea' , 'LN2', 'TerrSAP', 'BELRIESGO2026_r', 'BELGASTO2026_r', 'IRR2026_r', 'MR2026_r', 'PMANDEV_2026']
    df_ppto_real = df_Real.reindex(columns=xColumnas)
    df_ppto_real= df_ppto_real.rename(columns={
                            "BELRIESGO2026_r":"BELRIESGO2026",
                            "BELGASTO2026_r":"BELGASTO2026",
                            "IRR2026_r":"IRR2026",
                            "MR2026_r":"MR2026",
                            "LN2":"LN",
                            "TerrSAP":"Terr"})

xColumnas = ['Ramo', 'ZREGIONRP', 'ZTIPOREAS', 'FUNCAREA', 'BELRIESGO2026_p', 'BELGASTO2026_p', 'IRR2026_p', 'MR2026_p', 'PMANDEV_2026']
df_ppto_ppto = df_PPTO.reindex(columns=xColumnas)
df_ppto_ppto= df_ppto_ppto.rename(columns={
                            "BELRIESGO2026_p":"BELRIESGO2026",
                            "BELGASTO2026_p":"BELGASTO2026",
                            "IRR2026_p":"IRR2026",
                            "MR2026_p":"MR2026",
                            "ZTIPOREAS":"TipoRea",
                            "FUNCAREA":"LN",
                            "ZREGIONRP":"Terr"})

xPPTO = pd.concat([df_ppto_real,df_ppto_ppto],axis=0)

xPPTO['BRUTO2026'] = xPPTO.apply(lambda row: -row['BELRIESGO2026'] - row['BELGASTO2026'] - row['MR2026'], axis = 1)
xPPTO['NETO2026'] = xPPTO.apply(lambda row: row['BRUTO2026'] + row['IRR2026'], axis = 1)
xPPTO['Reserva'] = 'RRC'
xPPTO['Periodo'] = f'2026-{AuxMes}{zMes}'

auxPPTO = xPPTO.set_index(["Reserva", "Ramo", 'TipoRea', 'LN', 'Terr', "Periodo"]).stack()
auxPPTO = auxPPTO.reset_index()
auxPPTO.columns = ['Reserva', 'Ramo', 'TipoRea', 'LN', 'Terr', 'Periodo', 'Origen', 'Monto'] 

auxPPTO_sum = auxPPTO.groupby(['Reserva', 'Ramo', 'TipoRea', 'LN', 'Terr', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
auxPPTO_sum['Tipo de Monto'] = auxPPTO_sum['Origen']
auxPPTO_sum['Escenario'] = 'PPTO'
auxPPTO_sum['Monto_USD'] = auxPPTO_sum['Monto']

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2026\6_Recalibración\03_Reservas\Outputs scripts\RRC"
fileName = f"{xFolder}\\auxPPTO_sum_{zMes}.xlsx"
auxPPTO_sum.to_excel(fileName, index=False)

end_time = time.perf_counter()
elapsed_time = end_time - start_time
print("Elapsed time: ", elapsed_time)

