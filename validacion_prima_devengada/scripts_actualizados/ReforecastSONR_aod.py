#%% LIBRERÍAS
import pyodbc
import pandas as pd
import warnings
import getpass
from datetime import datetime
import os
import sys
usuario = "asunad"
warnings.filterwarnings('ignore')

#%% FND CALIBRADO (MEC v3) — sustituye la búsqueda en xPND
# mec_devengamiento.py y delta_calibrado.json se leen de la carpeta de Documents.
CARPETA_FND = fr"C:\Users\{usuario}\OneDrive - GPV\Documents"
if CARPETA_FND not in sys.path:
    sys.path.insert(0, CARPETA_FND)
import mec_devengamiento as mec

USAR_FND_CALIBRADO = True   # False -> comportamiento idéntico al script original (xPND)
DELTA_FND = mec.cargar_delta(CARPETA_FND)   # lee delta_calibrado.json de Documents si existe


# XPND_K traduce cada CLAVE de xPND a la antigüedad de registro k que representa.
# Se rearma junto a xPND en cada mes del ciclo (xPND[xAños[Meses - j]] vale NT(j)).
XPND_K = {}


def fnd_modelo(xRamo, clave, legado):
    """FND del modelo EN EL LUGAR EXACTO donde el script leía la tabla xPND.

    Sustituye el VALOR de la tabla, no la lógica: la clave (xMesProc o el xVal
    desplazado que calcula el propio script) ya viene resuelta por el código
    original, y aquí sólo se traduce a la antigüedad k con el mismo mapa con el
    que se arma xPND. Así el modelo no se salta ninguna rama —ni la de
    xIniVig == xFinVig, ni la del no proporcional, ni el corte de 12 meses— y
    con USAR_FND_CALIBRADO = False el script es idéntico al original.

    Si la clave no está en la escalera de 12 meses (las entradas fijas 202606,
    202706, 202806 y 202906 que el original mete aparte), se respeta el legado.
    """
    if not USAR_FND_CALIBRADO or xRamo is None:
        return legado
    k = XPND_K.get(clave)
    if k is None:
        return legado
    return mec.fnd_registro(xRamo, k, DELTA_FND)


def _es_no_proporcional(xTipoRea) -> bool:
    try:
        return int(float(xTipoRea)) == 2
    except Exception:
        return False

#%% INPUTS
zAñoPpto = 2026
zAño= 2026
zMes = 12
xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Archivos de Maria Osmara Camacho Lopez - Inputs"
#xAjManuales = pd.read_csv(f"{xFolder}\\AjManuales_SONR.csv")

#### PPTO
xSubramo = pd.read_csv(f"{xFolder}\\Subramo.csv")

####Mensual
Tbase_mp = pd.read_csv(f"{xFolder}\\TablaBase_MetodoPropio.csv")
Tbase_mp_ext = pd.read_csv(f"{xFolder}\\TablaBase_MetodoPropio_ext.csv")
ParamSONR_ARCHIVO = "ParamSONR2026_3+9.csv"
ParamSONR = pd.read_csv(f"{xFolder}\\{ParamSONR_ARCHIVO}")
ParamSONR_inc = pd.read_csv(f"{xFolder}\\ParamSONR2026_3+9.csv")
xPNDmes = pd.read_csv(f"{xFolder}\\PNDmes.csv")
xFrecCol = pd.read_csv(f"{xFolder}\\FrecCol.csv")
xLlavesPol = pd.read_csv(f"{xFolder}\\LlavesPol.csv")
xEsc_base = pd.read_csv(f"{xFolder}\\Escenario_base_SONR.csv")

#%% DICCIONARIOS
xAños ={202612:202612, 202611:202611, 202610:202610, 202609:202609, 202608:202608, 202607:202607, 202606:202606, 202605:202605, 202604:202604, 202603:202603, 202602:202602, 202601:202601,
        202600:202512, 202599:202511, 202598:202510, 202597:202509, 202596:202508, 202595:202507, 202594:202506, 202593:202505, 202592:202504, 202591:202503, 202590:202502, 202589:202501}

xTC_PPTO = {202512:18.008,202601:19.0333,202602:19.0667,
            202603:19.1,202604:19.1333,202605:19.1667,
            202606:19.2,202607:19.2333,202608:19.2667,
            202609:19.3,202610:19.3333,202611:19.3667,
            202612:19.4}

xEscenario = {"BEL_RIESGO":["BEL", 2],
        "IRR":["IRR",2],
        "IRR2026_TCVal":["IRR",2],
        "MR":["MR",2],
        "BRUTO":["BRUTO",2],
        "NETO":["NETO",2]}


#%% FUNCIÓN FND REAL.
def zFND(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia, xRamo=None):
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
                if xFinVig == 45930: #### AJUSTE HECHO PARA LOS AJUSTES MANUALES QUE REGRESAN VALORES QUE GENERAN ERROR PARA SACAR EL RATIO
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
                return fnd_modelo(xRamo, xMesProc, result)

#%% FUNCIÓN FND PPTO
def zFND_PPTO(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia, xRamo=None):
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
                    xVal = xAños.get(int(xMesProc) - xFecVal.month,0)
                else:
                    xVal = xAños.get(int(xMesProc) - xFecVal.month + 12 ,0)
            if xVal < 202601:
                #result = 1
                result = xPND.get(xVal,0).get(str(xFrecuencia), 0)
            else:
                result = xPND.get(xVal,0).get(str(xFrecuencia), 0)
            return fnd_modelo(xRamo, xVal, result)
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
                return fnd_modelo(xRamo, xVal, result)

#%% zFND REAL REFORECAST
def zFND2(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia, xRamo=None):
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
                if xFinVig == 45930: #### AJUSTE HECHO PARA LOS AJUSTES MANUALES QUE REGRESAN VALORES NO USABLES PARA SACAR EL RATIO
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
                return fnd_modelo(xRamo, xVal, result)
#%% FUNCIÓN CONSULTA TC USD.
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

ConsultaTC_usd = ConsultaMoneda_usd()
TC_USD = ConsultaMoneda_usd()
xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Archivos de Maria Osmara Camacho Lopez - Inputs"
fileName = f"{xFolder}\\TablaTCSONR.xlsx"
TC_USD.to_excel(fileName, index=False)


#%% FUNCIÓN CONSULTA MONEDA.
def ConsultaMoneda():
    zAño = 2026
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




#%% FUNCIÓN CONSULTA PARA SONR REAL
def ConsultaReal(MES, FECVAL, AÑOMES):
    zInicio = (zAño - 10) * 100 + MES
    zFin = zAño * 100 + MES
    #print(FECVAL)
    #print(zInicio)
    #print(zFin)
    
    # Conexión y consulta BD Gonz
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
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
    
    #ConsultaR = pd.concat([tMovGG,xAjManuales]) 
    ConsultaR = tMovGG

    ConsultaR['AñoMes'] = ConsultaR.apply(lambda row: row['Susc'] * 100 + int(str(int(row['CALMONTH']))[-2:]), axis=1) 
    
    ConsultaR['Frecuencia'] = ConsultaR.apply(lambda row: row['Periodo'] if (row['TipoRea'] == 1 and row['Ramo_filt'] != 70 and row['Ramo_filt'] != 100) else ('NA' if pd.notna(row['Periodo']) else 'DEF'), axis=1)
    ConsultaR[['IniVig', 'FinVig']] = ConsultaR[['IniVig', 'FinVig']].fillna(0)
    ConsultaR[f'FND_{AÑOMES}'] = ConsultaR.apply(lambda y: zFND(y['IniVig'], y['FinVig'], y['TipoRea'], y['AñoMes'], FECVAL, y['CALMONTH'], y['Frecuencia'], y['Ramo_filt']), axis=1)
    
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
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            r'DBQ=\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb;')

    conn = pyodbc.connect(conn_str)
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
        ConsultaR[f'FND_{zAño + mes}12'] = ConsultaR.apply(lambda y: zFND2(y['IniVig'], y['FinVig'], y['TipoRea'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia'], y['Ramo_filt']), axis=1)
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
        ConsultaR[f'FND_{zAño}{AuxMes}{mes_calculo}'] = ConsultaR.apply(lambda y: zFND2(y['IniVig'], y['FinVig'], y['TipoRea'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia'], y['Ramo_filt']), axis=1)
        ConsultaR[f'Dev_{zAño}{AuxMes}{mes_calculo}'] = ConsultaR.apply(lambda row: 1 - row[f'FND_{zAño}{AuxMes}{mes_calculo}'] , axis=1)
        ConsultaR[f'PrimaDev_{zAño}{AuxMes}{mes_calculo}_Val'] = ConsultaR.apply(lambda row: row['PmaTomOri'] * row['TC_USD'] * row[f'Dev_{zAño}{AuxMes}{mes_calculo}'], axis=1)

    return(ConsultaR)


#%% FUNCIÓN MÉTODO PROPIO
def Metodo_propio():
    global Tbase_mp, ConsultaR
    BC = -3910064857 #TEMPORAL
    BC2 = 84398596 #TEMPORAL
    Tbase_mp_ = Tbase_mp.copy()   # .copy(): sin esto cada vuelta del ciclo muta el global
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

#%% FUNCIÓN MÉTODO PROPIO REFORECAST
def Metodo_propio_reforecast():
    global Tbase_mp, ConsultaR, Tbase_mp_ext
    BC = -3910064857 #TEMPORAL
    BC2 = 84398596 #TEMPORAL
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
    global Tbase_mp, ConsultaR, Tbase_mp_ext
    BC = -3910064857 #TEMPORAL
    BC2 = 84398596 #TEMPORAL
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

xEsc_base['TC'] =  xEsc_base.apply(lambda row: xTC_PPTO[row['Periodo']],axis=1)
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
    xAños[Meses]: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
    202606: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    202706: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    202806: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    202906: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717}}

    # Antigüedad k que representa cada clave de la escalera de 12 meses. Las cuatro
    # entradas fijas de arriba (202606, 202706, 202806, 202906) NO entran: el original
    # las sobrescribe con un valor propio, así que ahí se respeta el legado.
    XPND_K.clear()
    for _j in range(12):
        XPND_K[xAños[Meses - _j]] = _j
    for _fijo in (202606, 202706, 202806, 202906):
        XPND_K.pop(_fijo, None)

    
    

    ConsultaR = ConsultaReal(mes_calculo, zFechaValuacion, Meses)

    print(ConsultaR)
    df_Real_IS_Real = Metodo_propio()

    # ---- DIAGNÓSTICO: por qué un ramo se queda sin filas -------------------------
    # df_SONR_dim.set_index([...]).stack() DESCARTA los NaN. Si BEL_RIESGO, IRR y MR
    # son NaN para un ramo, ese ramo desaparece de la salida SIN AVISO. El NaN viene
    # casi siempre del merge con ParamSONR: si no hay fila con Llave '<AñoMes>-<Ramo>',
    # 'Ind Sin SONR Media' y 'Factor_Ret' llegan vacíos y todo lo que cuelga de ellos
    # también. Esto lo reporta en claro en vez de perderlo.
    try:
        _d = df_Real_IS_Real
        _falta_param = sorted(set(_d.loc[_d['Ind Sin SONR Media'].isna(), 'Ramo'].tolist()))
        _falta_ret = sorted(set(_d.loc[_d['Factor_Ret'].isna(), 'Ramo'].tolist()))
        _sin_bel = _d.groupby('Ramo')['BEL_RIESGO'].apply(lambda x: x.isna().all())
        _mudos = sorted(_sin_bel[_sin_bel].index.tolist())
    except Exception as _e:
        # el diagnóstico NUNCA debe tumbar la corrida
        print(f"[SONR][{Meses}] no pude revisar los ramos: {_e}")
        _falta_param = _falta_ret = _mudos = []
    if _falta_param or _falta_ret or _mudos:
        print(f"[SONR][{Meses}] AVISO — ramos que se van a perder en la salida:")
        if _falta_param:
            print(f"    sin 'Ind Sin SONR Media' (falta Llave '{Meses}-<ramo>' en ParamSONR): {_falta_param}")
        if _falta_ret:
            print(f"    sin 'Factor_Ret' en ParamSONR: {_falta_ret}")
        if _mudos:
            print(f"    BEL_RIESGO todo NaN -> NO saldrán en Base SONR: {_mudos}")
        print(f"    Revisa que {ParamSONR_ARCHIVO} tenga una fila por cada '{Meses}-<ramo>'.")
    else:
        print(f"[SONR][{Meses}] ok — {df_Real_IS_Real['Ramo'].nunique()} ramos con BEL_RIESGO calculado")
    # -----------------------------------------------------------------------------
    print(df_Real_IS_Real)
    xColumnas = ['Ramo', 'BEL_RIESGO', 'IRR', 'MR']
    df_SONR_dim = df_Real_IS_Real.reindex(columns=xColumnas)
    print(df_SONR_dim)
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
    Meses_falt_3 = xEsc_base[xEsc_base["Periodo"] > Mesesppto]
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
    df.append(auxSONR_sum)
    
    xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documents\Outputs"
    fileName = f"{xFolder}\\auxSONR_sum.xlsx"
    auxSONR_sum.to_excel(fileName, index=False)



df_concatenado = pd.concat(df, ignore_index=True)
#df_concatenado = df_concatenado.drop(["cTCAD_FecAMD","cTCAD_Mnt"], axis=1)
df_concatenado = df_concatenado.drop_duplicates()

#Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'TC', 'Monto_USD']
Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'Monto_USD']
df_concatenado = df_concatenado[Columnas]

# ---- RESUMEN DE COBERTURA -------------------------------------------------------
# La corrida de septiembre con el FND del modelo perdió 8 de 11 ramos desde 202604 y
# nadie se enteró hasta comparar los Excel: la salida simplemente traía menos filas.
# Esto lo dice antes de escribir el archivo.
try:
    _esc = df_concatenado[df_concatenado["Escenario"] == 2]
    _ramos = sorted(_esc["Ramo"].dropna().unique())
    _pers = sorted(_esc["Periodo"].dropna().unique())
    _hay = set(zip(_esc["Ramo"], _esc["Periodo"]))
    _faltan = [(r, p) for r in _ramos for p in _pers if (r, p) not in _hay]
    print(f"[SONR] cobertura escenario 2: {len(_ramos)} ramos x {len(_pers)} periodos"
          f" = {len(_ramos)*len(_pers)} esperados, {len(_hay)} presentes")
    if _faltan:
        print(f"[SONR] !! FALTAN {len(_faltan)} combinaciones ramo x periodo. La salida está INCOMPLETA.")
        import collections as _c
        _pr = _c.defaultdict(list)
        for r, pp in _faltan:
            _pr[r].append(int(pp))
        for r in sorted(_pr):
            print(f"       ramo {r}: {sorted(_pr[r])}")
        print("[SONR]    Causa habitual: falta la Llave '<AAAAMM>-<ramo>' en " + ParamSONR_ARCHIVO + ",")
        print("[SONR]    lo que deja 'Ind Sin SONR Media' vacío y .stack() borra la fila en silencio.")
    else:
        print("[SONR] cobertura completa: no falta ninguna combinación ramo x periodo.")
    _dup = df_concatenado.duplicated(subset=["Escenario","Tipo de Monto","Ramo","Periodo"]).sum()
    if _dup:
        print(f"[SONR] !! {_dup} filas duplicadas por (Escenario, Tipo, Ramo, Periodo).")
except Exception as _e:
    print(f"[SONR] no pude resumir la cobertura: {_e}")
# ---------------------------------------------------------------------------------

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documents\Outputs"
fileName = f"{xFolder}\\SONR_esc.xlsx"
df_concatenado.to_excel(fileName, index=False)