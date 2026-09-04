#RESREVA RRC
#Escenario 0 -> LISTO -> Año Base (202412 real) 
#Escenario 1 -> LISTO -> Presupuesto (dls) usando tc real para los meses que ya se tienen y usar el tc ppto para el resto
#Escenario 2 -> Usar función real para los meses reales y hacer proceso mensualizados para los meses que no se tienen, para tc usar el estimado ####AGREGAR LA FUNCIÓN DE LOS MENSUALIZADOS PARA EL RESTO DE MESES
#Escenario 3 -> LISTO -> Usar función real para los meses reales y traer la info del ppto para los meses que no se tienen, para tc usar el estimado
#Escenario 4 -> LISTO -> Reforecast final del año, usando funciones ppto y real para obtener saldo al final del año en usd, usar tc real y estimado para pasar a mxn #####REVISAR MR MUY ALTO Y HACER EL CRUCE CON EL TC ESTIMADO


import pyodbc
import pandas as pd
import time
import warnings
import openpyxl
import numpy as np
import getpass
import os 
usuario = getpass.getuser()
warnings.filterwarnings('ignore')
start_time = time.perf_counter()

#%% TABLAS CSV
xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos"

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Planeación Financiera RPAT - Documents\Financieros"
xRamo = pd.read_excel(f"{xFolder}\\CentralizadoCatálogos_SIRECySAP.xlsx", sheet_name="Valores", usecols="J:M", skiprows=1)
xPais = pd.read_excel(f"{xFolder}\\CentralizadoCatálogos_SIRECySAP.xlsx", sheet_name="Valores", usecols="O:T", skiprows=1)

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Planeación Financiera RPAT - Documents\Forecasts\2025\CSV Auxiliares"
xLlavesPol = pd.read_csv(f"{xFolder}\\LlavesPol.csv")
xRRC = pd.read_csv(f"{xFolder}\\ParametrosMens2025.csv")
xIS_CAT = pd.read_csv(f"{xFolder}\\IS_Cat.csv")
xAjManuales = pd.read_csv(f"{xFolder}\\AjManuales.csv") 
xRRC_PPTO = pd.read_csv(f"{xFolder}\\ParametrosMensPPTO2025.csv")
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

xEscenario = {"BELRIESGO2025_TCVal":["BEL", 2],
        "BELGASTO2025_TCVal":["BELG",2],
        "IRR2025_TCVal":["IRR",2],
        "MR2025_TCVal":["MR",2],
        "BRUTO_TCVal":["BRUTO",2],
        "NETO_TCVal":["NETO",2],
        "BELRIESGO2025_TCAñoAnt":["BEL",5],
        "BELGASTO2025_TCAñoAnt":["BELG",5],
        "IRR2025_TCAñoAnt":["IRR",5],
        "MR2025_TCAñoAnt":["MR",5],
        "BRUTO_TCAñoAnt":["BRUTO",5],
        "NETO_TCAñoAnt":["NETO",5],
        "BELRIESGO2025":["BEL", 4],
        "BELGASTO2025":["BELG",4],
        "IRR2025":["IRR",4],
        "MR2025":["MR",4],
        "BRUTO2025":["BRUTO",4],
        "NETO2025":["NETO",4]}

xTC_PPTO = {202412:19.5,202501:19.5146,202502:19.5438,202503:19.5729,
         202504:19.6021,202505:19.6313,202506:19.6604,202507:19.6896,
         202508:19.7188,202509:19.7479,202510:19.7771,202511:19.8063,
         202512:19.8354}
	


#%% VARIABLES INPUT
zMes = 9
zAño = 2025
Nomeses = [1,12]

COC = 0.1
BC_SONR_2025 = 0
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
    ConsultaR['BELRIESGO2025_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR['BELGASTO2025_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR['IRR2025_TCVal'] = ConsultaR.apply(lambda row: row['BELRIESGO2025_TCVal']*row['CESION'], axis = 1)
    
    
    ConsultaR['DESVIACION2025'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    BC_RRC_2025 = ConsultaR[f'DESVIACION2025'].sum()
    BC_2025 = BC_RRC_2025 + BC_SONR_2025
    BC = -1139984032.15/20 #-1007920806 -1139984032.15
    RCS = 105000000/20 #113000000 105000000
    COC = 0.1
    ConsultaR['MR2025_TCVal'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2025']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2025), axis = 1)
    
    
    ConsultaR['PMADEV_2025'] = ConsultaR.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    ConsultaR['BELRIESGO2025_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaR['BELGASTO2025_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaR['IRR2025_TCAñoAnt'] = ConsultaR.apply(lambda row: row['BELRIESGO2025_TCAñoAnt']*row['CESION'], axis = 1)																											
    ConsultaR['MR2025_TCAñoAnt'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2025']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2025), axis = 1)
    

    xColumnas = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 
             'CiaTom', 'CtoTom', 'Susc', 'Período', 'CALMONTH', 'IniVig', 'FinVig', 
             'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal','PmaTom_sERNal', 'PrimaCedidaNal',
             'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION','BELMEDIA', 
             'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'VALORFREC', 'PORC_ND', 'CEDIDA', 
             'TC_Valuación', 'TC_CierreAnterior', 'PMADEV_2025', 'DESVIACION2025', 'BELRIESGO2025_TCVal', 'BELGASTO2025_TCVal',
             'IRR2025_TCVal', 'MR2025_TCVal', 'BELRIESGO2025_TCAñoAnt', 'BELGASTO2025_TCAñoAnt', 'IRR2025_TCAñoAnt', 'MR2025_TCAñoAnt']

    ConsultaR = ConsultaR.reindex(columns=xColumnas, fill_value='')
    #ConsultaR = pd.concat([ConsultaR,xAjManuales],axis=0) 

    #xFolder = r"C:\Users\mocamachol\OneDrive - GPV\Documentos"
    #fileName = f"{xFolder}\\ConsultaR_RRC_{MES}.xlsx"
    #ConsultaR.to_excel(fileName, index=False)

    return ConsultaR

#%% FUNCIÓN RRC PPTO

def ConsultaPPTO2025(MES):
    global xPais, xSubramo, ConsultaTC, xRRC, xIS_BEL_MEDIA, BC, RCS, COC, tc_CIERRE, zMes, zAFUN, xCesionPI, xTablaCesion, zFrecuencias, xPND2, Cesion_Esp
    
    xFolder = fr"C:\Users\mocamachol\OneDrive - GPV\Planeación Financiera RPAT - Documents\Presupuestos\2025\02 Técnico\BD_PptoTécnico_2025"
    xFile = fr"{xFolder}\PptoTecnico2025.csv"
    ConsultaP = pd.read_csv(xFile, thousands=',')
    ConsultaPPTO = ConsultaP[(ConsultaP["GL_ACCT"] > 6101000000) & (ConsultaP["GL_ACCT"] < 6108999999) & (ConsultaP["CALMONTH"] <= 202512) & (ConsultaP["CALMONTH"] >= (zAño*100 + MES + 1))]

    Columnas = [
    'PROFTCTR', 'ZREGIONRP', 'ZTIPOREAS', 'ZOFICN_RP', 'FUNCAREA', 'ZMGA', 
    'TWAERS', 'ZTIPOCES', 'PRODUCT', 'ZCORREDOR', 'ZCEDENTE', 'ZCONTRATO', 
    'ZSUSCYEAR', 'CALMONTH', 'AMOUNT']

    ConsultaPPTO = ConsultaPPTO[Columnas]

    ConsultaPPTO= ConsultaPPTO.merge(xSubramo[["CeBe","Ramo", "Ramo2"]].drop_duplicates(),
                             how="left", left_on="PROFTCTR", right_on="CeBe")
    
    ConsultaPPTO['Ramo'] = ConsultaPPTO.apply(lambda row: 10 if row['Ramo'] == 20 else row['Ramo'], axis = 1)

    ConsultaPPTO = ConsultaPPTO.drop('CeBe', axis=1)
    

    ConsultaPPTO= ConsultaPPTO.merge(xRRC[["Ramo", "Pesos_dur", "Resto Monedas_dur", "Pesos_ret", "Resto Monedas_ret", "Ind. Gasto", f"IS Bel Media-12", f"IS Bel 99.5%-12"]].drop_duplicates()
                            .rename(columns={
                            "Pesos_dur":"DURMXN",
                            "Resto Monedas_dur":"DUROTR",
                            "Pesos_ret":"RETMXN",
                            "Resto Monedas_ret":"RETOTR",
                            "Ind. Gasto":"BELGASTO",
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

    ConsultaPPTO['BELRIESGO2025'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA'], axis = 1)
    ConsultaPPTO['BELGASTO2025'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO'], axis = 1)
    ConsultaPPTO['IRR2025'] = ConsultaPPTO.apply(lambda row: row['BELRIESGO2025']*row['CESION'], axis = 1)
    ConsultaPPTO['DESVIACION2025'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*(row['RETMXN'] if row['TWAERS'] == "MXN" else row['RETOTR']), axis = 1)
    BC_RRC_2025 = ConsultaPPTO[f'DESVIACION2025'].sum()
    BC_2025 = BC_RRC_2025 + BC_SONR_2025
    BC = -1139984032.15 #-1007920806 -1139984032.15
    RCS = 105000000 #113000000 105000000
    COC = 0.1

    
    ConsultaPPTO['MR2025'] = ConsultaPPTO.apply(lambda row: -1*row['DESVIACION2025']*RCS*COC*(row['DURMXN'] if row['TWAERS'] == "MXN" else (row['DUROTR']))*(1/BC), axis = 1)
    
    ConsultaPPTO['PMADEV_2025'] = ConsultaPPTO.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    #xFolder = r"C:\Users\mocamachol\OneDrive - GPV\Documentos"
    #fileName = f"{xFolder}\\ConsultaPPTO_RRC_{MES}.xlsx"
    #ConsultaPPTO.to_excel(fileName, index=False)

    return ConsultaPPTO

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
    xFolder1 = r"C:\Users\mocamachol\OneDrive - GPV\Documentos"
    fileName = f"{xFolder1}\\ConsultaR.xlsx"
    ConsultaR.to_excel(fileName, index=False)
    ConsultaR['BELRIESGO2025_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA']*row['TC_Valuación'], axis = 1)
    ConsultaR['BELGASTO2025_TCVal'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO']*row['TC_Valuación'], axis = 1)
    ConsultaR['IRR2025_TCVal'] = ConsultaR.apply(lambda row: row['BELRIESGO2025_TCVal']*row['CESION'], axis = 1)
    
    ConsultaR['DESVIACION2025'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*(row['BEL99']-row['BELMEDIA'])*row['TC_Valuación']*(row['RETMXN'] if row['MonedaOri'] == 1 else row['RETOTR']), axis = 1)
    BC_RRC_2025 = ConsultaR[f'DESVIACION2025'].sum()
    BC_2025 = BC_RRC_2025 + BC_SONR_2025
    COC = 0.1
    RCS = 2227189146.47
    BC = -1007920806
    ConsultaR['MR2025_TCVal'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2025']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2025), axis = 1)
    ConsultaR['PMADEV_2025'] = ConsultaR.apply(lambda row: row['MONTO_PI']*(1-row['PORC_ND']), axis = 1)

    ConsultaR['BELRIESGO2025_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELMEDIA']*row['TC_CierreAnterior'], axis = 1)
    ConsultaR['BELGASTO2025_TCAñoAnt'] = ConsultaR.apply(lambda row: row['MONTO_PI']*row['PORC_ND']*row['BELGASTO']*row['TC_CierreAnterior'], axis = 1)
    ConsultaR['IRR2025_TCAñoAnt'] = ConsultaR.apply(lambda row: row['BELRIESGO2025_TCAñoAnt']*row['CESION'], axis = 1)																											
    ConsultaR['MR2025_TCAñoAnt'] = ConsultaR.apply(lambda row: -1*row['DESVIACION2025']*RCS*COC*(row['DURMXN'] if row['MonedaOri'] == 1 else (row['DUROTR']))*(1/BC_2025), axis = 1)

    xColumnas = ['SRamo', 'Pais', 'TipoRea', 'OfiRepPt', 'MonedaOri', 'CorrTom', 
             'CiaTom', 'CtoTom', 'Susc', 'Período', 'CALMONTH', 'IniVig', 'FinVig', 
             'PrimaTomadaOri', 'PmaTom_sEROri', 'PrimaCedidaOri', 'PrimaTomadaNal','PmaTom_sERNal', 'PrimaCedidaNal',
             'REGION', 'Ramo', 'LLAVE', 'LN2', 'FRECUENCIA', 'MONTO_PI', 'CESION','BELMEDIA', 
             'BELGASTO', 'BEL99', 'DURMXN', 'DUROTR', 'RETMXN', 'RETOTR', 'PORC_ND', 'CEDIDA', 
             'TC_Valuación', 'TC_CierreAnterior', 'PMADEV_2025', 'DESVIACION2025', 'BELRIESGO2025_TCVal', 'BELGASTO2025_TCVal',
             'IRR2025_TCVal', 'MR2025_TCVal', 'BELRIESGO2025_TCAñoAnt', 'BELGASTO2025_TCAñoAnt', 'IRR2025_TCAñoAnt', 'MR2025_TCAñoAnt']
    
    xFolder = r"C:\Users\mocamachol\OneDrive - GPV\Documentos"
    fileName = f"{xFolder}\\ConsultaPPTO_RRC_{MES}_tradicional.xlsx"
    ConsultaR.to_excel(fileName, index=False)

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

    zFechaValuacion = f'{dia}/{AuxMes}{mes_calculo}/2025'
    AuxMesI =  zAñoRef * 100 + mes_calculo
    AuxMesF = AuxMesI + 100

    Meses = zAño*100 + mes_calculo 
    Mesesppto = zAño*100 + zMes

    print(f'Inicio cálculo escenario 2 para {Meses}')

    xAños ={202512:202512, 202511:202511, 202510:202510, 202509:202509, 202508:202508, 202507:202507, 202506:202506, 202505:202505, 202504:202504, 202503:202503, 202502:202502, 202501:202501,
            202500:202412, 202499:202411, 202498:202410, 202497:202409, 202496:202408, 202495:202407, 202494:202406, 202493:202405, 202492:202404, 202491:202403, 202490:202402, 202489:202401}
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
    


    xColumnas = ['Ramo', 'BELRIESGO2025_TCVal', 'BELGASTO2025_TCVal', 'IRR2025_TCVal', 'MR2025_TCVal',
                'BELRIESGO2025_TCAñoAnt', 'BELGASTO2025_TCAñoAnt', 'IRR2025_TCAñoAnt', 'MR2025_TCAñoAnt']

    df_RRC_dim = df_Real_IS_Real.reindex(columns=xColumnas)
    df_RRC_dim['BRUTO_TCVal'] = df_RRC_dim.apply(lambda row: -row['BELRIESGO2025_TCVal'] - row['BELGASTO2025_TCVal'] - row['MR2025_TCVal'], axis = 1)
    df_RRC_dim['NETO_TCVal'] = df_RRC_dim.apply(lambda row: row['BRUTO_TCVal'] + row['IRR2025_TCVal'], axis = 1)
    df_RRC_dim['BRUTO_TCAñoAnt'] = df_RRC_dim.apply(lambda row: -row['BELRIESGO2025_TCAñoAnt'] - row['BELGASTO2025_TCAñoAnt'] - row['MR2025_TCAñoAnt'], axis = 1)
    df_RRC_dim['NETO_TCAñoAnt'] = df_RRC_dim.apply(lambda row: row['BRUTO_TCAñoAnt'] + row['IRR2025_TCAñoAnt'], axis = 1)
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

    xColumnas = ['Ramo', 'BELRIESGO2025_TCVal', 'BELGASTO2025_TCVal', 'IRR2025_TCVal', 'MR2025_TCVal']

    df_RRC_dim_3 = df_Real_IS_Real.reindex(columns=xColumnas)
    df_RRC_dim_3['BRUTO_TCVal'] = df_RRC_dim_3.apply(lambda row: -row['BELRIESGO2025_TCVal'] - row['BELGASTO2025_TCVal'] - row['MR2025_TCVal'], axis = 1)
    df_RRC_dim_3['NETO_TCVal'] = df_RRC_dim_3.apply(lambda row: row['BRUTO_TCVal'] + row['IRR2025_TCVal'], axis = 1)
    #df_RRC_dim_3['BRUTO_TCAñoAnt'] = df_RRC_dim_3.apply(lambda row: -row['BELRIESGO2025_TCAñoAnt'] - row['BELGASTO2025_TCAñoAnt'] - row['MR2025_TCAñoAnt'], axis = 1)
    #df_RRC_dim_3['NETO_TCAñoAnt'] = df_RRC_dim_3.apply(lambda row: row['BRUTO_TCAñoAnt'] + row['IRR2025_TCAñoAnt'], axis = 1)
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
#%%Escenario 4
    Mesesp = zAño * 100 + 12
    xPND = {
        xAños[Mesesp - 11]: {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
        xAños[Mesesp - 10]: {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
        xAños[Mesesp - 9]: {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
        xAños[Mesesp - 8]: {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
        xAños[Mesesp - 7]: {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
        xAños[Mesesp - 6]: {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
        xAños[Mesesp - 5]: {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
        xAños[Mesesp - 4]: {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
        xAños[Mesesp - 3]: {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
        xAños[Mesesp - 2]: {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
        xAños[Mesesp - 1]: {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
        xAños[Mesesp]: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329}}
    xPND2 = {
    xAños[Mesesp - 11]: {'NA': 0.043835616, 1: 0.043835616, 2: 0, 3: 0, 6: 0, 0: 0, 'DEF': 0},
    xAños[Mesesp - 10]: {'NA': 0.126027397, 1: 0.126027397, 2: 0.083333333, 3: 0.043835616, 6: 0, 0: 0, 'DEF': 0.043835616},
    xAños[Mesesp - 9]: {'NA': 0.210958904, 1: 0.210958904, 2: 0.166666667, 3: 0.128767123, 6: 0.005479452, 0: 0, 'DEF': 0.128767123},
    xAños[Mesesp - 8]: {'NA': 0.295890411, 1: 0.295890411, 2: 0.25, 3: 0.21369863, 6: 0.08630137, 0: 0, 'DEF': 0.21369863},
    xAños[Mesesp - 7]: {'NA': 0.37260274, 1: 0.37260274, 2: 0.333333333, 3: 0.290410959, 6: 0.167123288, 0: 0, 'DEF': 0.290410959},
    xAños[Mesesp - 6]: {'NA': 0.457534247, 1: 0.457534247, 2: 0.416666667, 3: 0.375342466, 6: 0.252054795, 0: 0, 'DEF': 0.375342466},
    xAños[Mesesp - 5]: {'NA': 0.539726027, 1: 0.539726027, 2: 0.5, 3: 0.457534247, 6: 0.334246575, 0: 0.087671233, 'DEF': 0.457534247},
    xAños[Mesesp - 4]: {'NA': 0.624657534, 1: 0.624657534, 2: 0.583333333, 3: 0.542465753, 6: 0.419178082, 0: 0.17260274, 'DEF': 0.542465753},
    xAños[Mesesp - 3]: {'NA': 0.706849315, 1: 0.706849315, 2: 0.666666667, 3: 0.624657534, 6:  0.501369863, 0: 0.254794521, 'DEF': 0.624657534},
    xAños[Mesesp - 2]: {'NA': 0.791780822, 1: 0.791780822, 2: 0.75, 3: 0.709589041, 6: 0.58630137, 0: 0.339726027, 'DEF': 0.709589041},
    xAños[Mesesp - 1]: {'NA': 0.876712329, 1: 0.876712329, 2: 0.833333333, 3: 0.794520548, 6: 0.671232877, 0: 0.424657534, 'DEF': 0.794520548},
    xAños[Mesesp]: {'NA': 0.95890411, 1: 0.95890411, 2: 0.916666667, 3: 0.876712329, 6: 0.753424658, 0: 0.506849315, 'DEF': 0.876712329}}

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

    zFechaValuacion = f'{dia}/{AuxMes}{mes_calculo}/2025'
    AuxMesI =  zAñoRef * 100
    AuxMesF = zAñoRef * 100 + mes_calculo
    print(f'Inicio cálculo escenario 4 para {Meses}')
    xReforecast_Real = ConsultaReal_USD(xRRC,xIS_CAT,mes_calculo)
   
    
    df_PPTO = ConsultaPPTO2025(mes_calculo)

    xColumnas = ['Ramo', 'BELRIESGO2025_TCVal', 'BELGASTO2025_TCVal', 'IRR2025_TCVal', 'MR2025_TCVal']
    df_reforecast_real = xReforecast_Real.reindex(columns=xColumnas)
    df_reforecast_real= df_reforecast_real.rename(columns={
                            "BELRIESGO2025_TCVal":"BELRIESGO2025",
                            "BELGASTO2025_TCVal":"BELGASTO2025",
                            "IRR2025_TCVal":"IRR2025",
                            "MR2025_TCVal":"MR2025"})

    xColumnas = ['Ramo', 'BELRIESGO2025', 'BELGASTO2025', 'IRR2025', 'MR2025']
    df_reforecast_ppto = df_PPTO.reindex(columns=xColumnas)
    xReforecast = pd.concat([df_reforecast_real,df_reforecast_ppto],axis=0)

    xReforecast['BRUTO2025'] = xReforecast.apply(lambda row: -row['BELRIESGO2025'] - row['BELGASTO2025'] - row['MR2025'], axis = 1)
    xReforecast['NETO2025'] = xReforecast.apply(lambda row: row['BRUTO2025'] + row['IRR2025'], axis = 1)
    xReforecast['Reserva'] = 'RRC'
    xReforecast['Periodo'] = f'{zAño}12-{mes_calculo}'


    auxReforecast = xReforecast.set_index(["Reserva", "Ramo", "Periodo"]).stack()
    auxReforecast = auxReforecast.reset_index()
    auxReforecast.columns = ['Reserva', 'Ramo', 'Periodo', 'Origen', 'Monto'] 

    auxReforecast_sum = auxReforecast.groupby(['Reserva', 'Ramo', 'Periodo', 'Origen']).agg({'Monto': 'sum'}).reset_index()
    auxReforecast_sum['Tipo de Monto'] = auxReforecast_sum['Origen'].apply(lambda x: xEscenario[x][0])
    auxReforecast_sum['Escenario'] = auxReforecast_sum['Origen'].apply(lambda x: xEscenario[x][1])
    auxReforecast_sum['Monto_USD'] = auxReforecast_sum['Monto']
    auxReforecast_sum['Periodo2'] = 202512

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
xFolder = r"C:\Users\mocamachol\OneDrive - GPV\Documentos"
fileName = f"{xFolder}\\RRC_esc.xlsx"
xRRC_saldos.to_excel(fileName, index=False)

end_time = time.perf_counter()
elapsed_time = end_time - start_time
print("Elapsed time: ", elapsed_time)