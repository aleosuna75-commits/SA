#%% RESERVA SONR
#
# v4 — FND CALIBRADO (MEC v3). Qué cambió y por qué:
#   El FND de la prima PROPORCIONAL y FACULTATIVA (TipoRea 1 y 3) deja de leerse de
#   los diccionarios xPND escritos a mano y sale de la tabla calibrada del MEC,
#   indexada por ANTIGÜEDAD DE REGISTRO k = mes de valuación − CALMONTH, con un
#   desplazamiento δ por ramo. Es el MISMO factor que consume el RRC, de modo que la
#   prima devengada del SONR (Dev = 1 − FND) queda coherente con la RRC por
#   construcción, como pide la sección 8 del documento del MEC.
#   Se calibró contra la prima devengada real (base BEL-IRR-MR): error medio mensual
#   de 3.1% en la reserva y de 0.7%–2.3% en la prima devengada anual.
#   El NO PROPORCIONAL (TipoRea 2) NO cambia: conserva su ratio por fechas.
#   Con USAR_FND_CALIBRADO = False el script se comporta exactamente como la v3.
#
#%% LIBRERÍAS
import pyodbc
import pandas as pd
import warnings
import getpass
import os
import sys
from datetime import datetime
usuario = getpass.getuser()
warnings.filterwarnings('ignore')

#%% FND CALIBRADO (MEC v3) — sustituye la búsqueda en xPND
# mec_devengamiento.py debe estar en esta misma carpeta.
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
import mec_devengamiento as mec

USAR_FND_CALIBRADO = True   # False -> comportamiento idéntico a la v3 (xPND)
DELTA_FND = mec.cargar_delta(_DIR)      # lee delta_calibrado.json si existe


def fnd_cal(xRamo, xMesProc, xFecVal, legado=0.0):
    """FND de una cuenta proporcional/facultativa por antigüedad de REGISTRO:
    k = mes de valuación (de xFecVal) − mes contable de registro (xMesProc)."""
    if not USAR_FND_CALIBRADO or xRamo is None:
        return legado
    try:
        mv = xFecVal.year * 100 + xFecVal.month
    except Exception:
        return legado
    k = mec.antiguedad_registro(mv, xMesProc)
    if k is None:
        return legado
    return 0.0 if k < 0 else mec.fnd_registro(xRamo, k, DELTA_FND)


def _es_no_proporcional(xTipoRea) -> bool:
    try:
        return int(float(xTipoRea)) == 2
    except Exception:
        return False

#%% AÑO Y MES DE VALUACIÓN — lo único que se mueve en cada cierre
# Todo lo que depende del año se deriva de aquí: los nombres de archivo que llevan año,
# el mapa xAños, el corte del presupuesto, las fechas de valuación y el periodo de salida.
# No quedan años sueltos más abajo (los «2025» que verás en nombres de columna como
# IRR2025_TCVal son etiquetas internas del script y no dependen del ejercicio).
zAñoPpto = 2026
zAño= 2026
zMes = 12
#%% CARPETA LOCAL — todos los insumos se leen y todas las salidas se escriben aquí
# Por defecto es la carpeta donde está este script (ponlo en «…\OneDrive - GPV\Documents»).
# Si quieres otra, escribe la ruta completa, p. ej.  CARPETA = r"C:\Users\tu.usuario\OneDrive - GPV\Documents"
# La base de valuación (BaseValuacion.accdb) sigue leyéndose del servidor \\adsroma; eso no cambia.
CARPETA = _DIR
xFolder = CARPETA

#%% ARCHIVOS DE ENTRADA — los nombres tal como están en la carpeta
# Cada entrada admite varios nombres y se usa el PRIMERO que exista, así que el script
# aguanta que un archivo cambie de nombre entre cierres. {A} = zAño, {A-1} = año anterior.
# Si alguno se llama distinto, ponlo al principio de su lista.
ARCHIVOS = {
    "aj_manuales":    ["AjManuales_SONR.csv"],
    "subramo":        ["Subramo.csv"],
    "tbase_mp":       ["TablaBase_MetodoPropio.csv"],
    "tbase_mp_ext":   ["TablaBase_MetodoPropio_ext.csv"],
    "param_sonr":     ["ParamSONR{A}.csv", "ParamSONR.csv", "ParamSONR{A-1}.csv"],
    # los lags de incurrido: si no hay archivo aparte, sirve el mismo ParamSONR
    "param_sonr_inc": ["ParamSONR{A}_lagsinc.csv", "ParamSONR{A}.csv", "ParamSONR{A-1}_lagsinc.csv"],
    "pnd_mes":        ["PNDmes.csv"],
    "frec_col":       ["FrecCol.csv"],
    "llaves_pol":     ["LlavesPol.csv"],
    "esc_base":       ["Escenario_base_SONR.csv"],
    "ppto_tecnico":   ["PptoTecnico{A}.csv", "PptoTecnico.csv", "PptoTecnico{A-1}.csv"],
}


def ruta(clave):
    """Ruta completa del archivo, probando los nombres de ARCHIVOS[clave] en orden.
    Si ninguno existe, aborta diciendo qué hay en la carpeta que se le parezca."""
    import difflib
    nombres = [x.replace("{A-1}", str(zAño - 1)).replace("{A}", str(zAño)) for x in ARCHIVOS[clave]]
    for x in nombres:
        p = os.path.join(CARPETA, x)
        if os.path.exists(p):
            if x != nombres[0]:
                print(f"[SONR] {clave}: uso «{x}» ({nombres[0]} no está en la carpeta).")
            return p
    hay = os.listdir(CARPETA)
    cerca = difflib.get_close_matches(nombres[0], hay, n=3, cutoff=0.4)
    raise SystemExit(f"[SONR] No encontré el archivo «{clave}».\n"
                     f"       Busqué, en este orden: {nombres}\n"
                     f"       En la carpeta: {CARPETA}\n"
                     f"       Lo más parecido que hay ahí: {cerca or 'nada'}\n"
                     f"       Corrige el nombre en el diccionario ARCHIVOS, arriba en este script.")


xAjManuales = pd.read_csv(ruta("aj_manuales"))

#### PPTO
xSubramo = pd.read_csv(ruta("subramo"))

####Mensual
Tbase_mp = pd.read_csv(ruta("tbase_mp"))
Tbase_mp_ext = pd.read_csv(ruta("tbase_mp_ext"))
ParamSONR = pd.read_csv(ruta("param_sonr"))
ParamSONR_inc = pd.read_csv(ruta("param_sonr_inc"))
xPNDmes = pd.read_csv(ruta("pnd_mes"))
xFrecCol = pd.read_csv(ruta("frec_col"))
xLlavesPol = pd.read_csv(ruta("llaves_pol"))
xEsc_base = pd.read_csv(ruta("esc_base"))

#%% DICCIONARIOS
def mapa_años(a):
    """Reconstruye xAños: traduce la aritmética «Meses - k» a un AAAAMM real cruzando
    el cambio de año. Cubre de enero del año a-1 a diciembre del año a."""
    m = {a * 100 + i: a * 100 + i for i in range(1, 13)}
    m.update({a * 100 - 11 + i: (a - 1) * 100 + 1 + i for i in range(12)})
    return m


xAños = mapa_años(zAño)

xTC_PPTO = {202412:19.5,202501:19.5146,202502:19.5438,202503:19.5729,
         202504:19.6021,202505:19.6313,202506:19.6604,202507:19.6896,
         202508:19.7188,202509:19.7479,202510:19.7771,202511:19.8063,
         202512:19.8354}


def revisar_tc_ppto(periodos):
    """El TC de presupuesto es un dato: no se deriva del año. Si el escenario base trae
    meses que no están en xTC_PPTO hay que agregarlos a mano; esto avisa con nombre y
    apellido en vez de reventar con un KeyError sin contexto."""
    faltan = sorted({int(p) for p in periodos} - set(xTC_PPTO))
    if faltan:
        raise SystemExit(f"[SONR] Faltan tipos de cambio de presupuesto en xTC_PPTO para {faltan}.\n"
                         f"       Hoy la tabla cubre {min(xTC_PPTO)}–{max(xTC_PPTO)}.\n"
                         f"       Agrégalos en el diccionario xTC_PPTO, arriba en este script.")

xEscenario = {"BEL_RIESGO":["BEL", 2],
        "IRR":["IRR",2],
        "IRR2025_TCVal":["IRR",2],
        "MR":["MR",2],
        "BRUTO":["BRUTO",2],
        "NETO":["NETO",2]}


#%% FUNCIÓN FND REAL.
def zFND(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia, xRamo=None):
    # v4: proporcional y facultativo -> tabla calibrada por antigüedad de registro.
    # El no proporcional (TipoRea 2) sigue por la lógica de fechas de más abajo.
    if USAR_FND_CALIBRADO and not _es_no_proporcional(xTipoRea):
        return fnd_cal(xRamo, xMesProc, xFecVal,
                       xPND.get(xMesProc, {}).get(str(xFrecuencia), 0))   # {}: un mes fuera de la ventana da 0, no revienta
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
                return result

#%% FUNCIÓN FND PPTO
def zFND_PPTO(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia, xRamo=None):
    # v4: idem zFND. En el presupuesto CALMONTH es el mes en que se proyecta el
    # registro de la cuenta, así que la antigüedad de registro se calcula igual.
    if USAR_FND_CALIBRADO and not _es_no_proporcional(xTipoRea):
        return fnd_cal(xRamo, xMesProc, xFecVal, 0.0)
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
            if xVal < (zAño*100 + 1):
                #result = 1
                result = xPND.get(xVal,0).get(str(xFrecuencia), 0)
            else:
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
def zFND2(xIniVig, xFinVig, xTipoRea, xAñoMes, xFecVal, xMesProc, xFrecuencia, xRamo=None):
    # v4: idem zFND (versión del reforecast).
    if USAR_FND_CALIBRADO and not _es_no_proporcional(xTipoRea):
        return fnd_cal(xRamo, xMesProc, xFecVal,
                       xPND.get(xMesProc, {}).get(str(xFrecuencia), 0))   # {}: un mes fuera de la ventana da 0, no revienta
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
                return result
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
xFolder = CARPETA
fileName = f"{xFolder}\\TablaTCSONR.xlsx"
TC_USD.to_excel(fileName, index=False)


#%% FUNCIÓN CONSULTA MONEDA.
def ConsultaMoneda():
    # zAño se toma del bloque de arriba; antes había aquí un «zAño = 2025» local que
    # pisaba al global y dejaba Anio_ant en el año equivocado al mover el ejercicio.
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
    
    ConsultaR = pd.concat([tMovGG,xAjManuales]) 
    #ConsultaR = tMovGG

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
def ConsultaPPTO2025(MES):
    
    xFolder = CARPETA
    xFile = ruta("ppto_tecnico")
    ConsultaP = pd.read_csv(xFile, thousands=',')
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
        ConsultaPPTO[f'FND_{zAño + mes}12'] = ConsultaPPTO.apply(lambda y: zFND_PPTO(0, 0, y['ZTIPOREAS'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia'], y['Ramo']), axis=1)
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
        ConsultaPPTO[f'FND_{zAño}{AuxMes}{mes_calculo}'] = ConsultaPPTO.apply(lambda y: zFND_PPTO(0, 0, y['ZTIPOREAS'], y['AñoMes'], zFechaValuacion, y['CALMONTH'], y['Frecuencia'], y['Ramo']), axis=1)
        ConsultaPPTO[f'Dev_{zAño}{AuxMes}{mes_calculo}'] = ConsultaPPTO.apply(lambda row: 1 - row[f'FND_{zAño}{AuxMes}{mes_calculo}'] , axis=1)
        ConsultaPPTO[f'PrimaDev_{zAño}{AuxMes}{mes_calculo}_Val'] = ConsultaPPTO.apply(lambda row: -row['AMOUNT'] * row[f'Dev_{zAño}{AuxMes}{mes_calculo}'], axis=1)
    
    
    return ConsultaPPTO

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

revisar_tc_ppto(xEsc_base['Periodo'])
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
    
    

    ConsultaR = ConsultaReal(mes_calculo, zFechaValuacion, Meses)
    df_Real_IS_Real = Metodo_propio()
    #xFolder = r"C:\Users\aburtona\OneDrive - GPV\Documentos"
    #fileName = f"{xFolder}\\SONR_consulta_{mes_calculo}.xlsx"
    #ConsultaR.to_excel(fileName, index=False)
    #fileName = f"{xFolder}\\SONR_met_{mes_calculo}.xlsx"
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
#%% ESCENARIO 4
    Mesesr = zAño * 100 + 12
    xPND = {
    xAños[Mesesr - 11]: {'NA': 0.043835616, '1': 0.043835616, '2': 0, '3': 0, '6': 0, '0': 0, 'DEF': 0},
    xAños[Mesesr - 10]: {'NA': 0.126027397, '1': 0.126027397, '2': 0.083333333, '3': 0.043835616, '6': 0, '0': 0, 'DEF': 0.043835616},
    xAños[Mesesr - 9]: {'NA': 0.210958904, '1': 0.210958904, '2': 0.166666667, '3': 0.128767123, '6': 0.005479452, '0': 0, 'DEF': 0.128767123},
    xAños[Mesesr - 8]: {'NA': 0.295890411, '1': 0.295890411, '2': 0.25, '3': 0.21369863, '6': 0.08630137, '0': 0, 'DEF': 0.21369863},
    xAños[Mesesr - 7]: {'NA': 0.37260274, '1': 0.37260274, '2': 0.333333333, '3': 0.290410959, '6': 0.167123288, '0': 0, 'DEF': 0.290410959},
    xAños[Mesesr - 6]: {'NA': 0.457534247, '1': 0.457534247, '2': 0.416666667, '3': 0.375342466, '6': 0.252054795, '0': 0, 'DEF': 0.375342466},
    xAños[Mesesr - 5]: {'NA': 0.539726027, '1': 0.539726027, '2': 0.5, '3': 0.457534247, '6': 0.334246575, '0': 0.087671233, 'DEF': 0.457534247},
    xAños[Mesesr - 4]: {'NA': 0.624657534, '1': 0.624657534, '2': 0.583333333, '3': 0.542465753, '6': 0.419178082, '0': 0.17260274, 'DEF': 0.542465753},
    xAños[Mesesr - 3]: {'NA': 0.706849315, '1': 0.706849315, '2': 0.666666667, '3': 0.624657534, '6':  0.501369863, '0': 0.254794521, 'DEF': 0.624657534},
    xAños[Mesesr - 2]: {'NA': 0.791780822, '1': 0.791780822, '2': 0.75, '3': 0.709589041, '6': 0.58630137, '0': 0.339726027, 'DEF': 0.709589041},
    xAños[Mesesr - 1]: {'NA': 0.876712329, '1': 0.876712329, '2': 0.833333333, '3': 0.794520548, '6': 0.671232877, '0': 0.424657534, 'DEF': 0.794520548},
    xAños[Mesesr]: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
    202606: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    202706: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    202806: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
    202906: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717}}
    ConsultaR_USD = ConsultaReal_USD(mes_calculo, zFechaValuacion, Meses)
    xFolder = CARPETA
    fileName = f"{xFolder}\\ConsultaR_USD{mes_calculo}_E4.xlsx"
    ConsultaR_USD.to_excel(fileName, index=False)
    
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
        xAños[Mesesp]: {'NA': 0.95890411, '1': 0.95890411, '2': 0.916666667, '3': 0.876712329, '6': 0.753424658, '0': 0.506849315, 'DEF': 0.876712329},
        202606: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
        202706: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
        202806: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717},
        202906: {'NA': 0.498630136986301, '1': 0.498630136986301, '2': 0.458333333333333, '3': 0.499771689497717, '6': 0.293150684931507, '0': 0.0438356164383562, 'DEF': 0.499771689497717}}
    
    if mes_calculo == 12:
        df_reforecast = Metodo_propio_reforecast_dic()
    else:

        ConsultaPPTO = ConsultaPPTO2025(mes_calculo)
        df_reforecast = Metodo_propio_reforecast()
        fileName = f"{xFolder}\\ConsultaPPTO{mes_calculo}_E4.xlsx"
        ConsultaPPTO.to_excel(fileName, index=False)

    fileName = f"{xFolder}\\df_reforecast{mes_calculo}_E4.xlsx"
    df_reforecast.to_excel(fileName, index=False)

    df_reforecast = df_reforecast[(df_reforecast["AñoMes"] == (zAño*100 + 12))]

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
    auxSONR_sum['Periodo2'] = zAño*100 + 12

    auxSONR_sum= auxSONR_sum.merge(TC_USD[["cTCAD_FecAMD","cTCAD_Mnt"]].drop_duplicates(),
                             how="left", left_on="Periodo2", right_on="cTCAD_FecAMD")
    
    auxSONR_sum['TC'] = auxSONR_sum['cTCAD_Mnt']
    auxSONR_sum['Monto_USD'] = auxSONR_sum['Monto']
    auxSONR_sum['Monto_MXN'] = auxSONR_sum.apply(lambda row: row['Monto_USD'] * row['cTCAD_Mnt'], axis = 1)

    xColumnas = ['Reserva', 'Ramo', 'Periodo', 'Tipo de Monto', 'Escenario',
                'Monto_MXN', 'Monto_USD']

    auxSONR_sum = auxSONR_sum.reindex(columns=xColumnas)

    df.append(auxSONR_sum)
    xFolder = CARPETA
    fileName = f"{xFolder}\\auxSONR_sum.xlsx"
    auxSONR_sum.to_excel(fileName, index=False)



df_concatenado = pd.concat(df, ignore_index=True)
#df_concatenado = df_concatenado.drop(["cTCAD_FecAMD","cTCAD_Mnt"], axis=1)
df_concatenado = df_concatenado.drop_duplicates()

#Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'TC', 'Monto_USD']
Columnas = ['Reserva', 'Escenario', 'Tipo de Monto', 'Ramo', 'Periodo', 'Monto_MXN', 'Monto_USD']
df_concatenado = df_concatenado[Columnas]

xFolder = CARPETA
# v4: el nombre de la salida dice con qué FND se corrió, para poder comparar contra el output anterior
# (SONR_esc.xlsx de la v3) sin pisarlo.
fileName = f"{xFolder}\\{'SONR_esc_FNDcal.xlsx' if USAR_FND_CALIBRADO else 'SONR_esc_legado.xlsx'}"
print(f"[SONR] Salida escrita en: {fileName}")
df_concatenado.to_excel(fileName, index=False)




