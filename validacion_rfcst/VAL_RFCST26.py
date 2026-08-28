# =====================================================
# VAL_RFCST26 - VALIDACION DEL REFORECAST 2026 (7+5)
# =====================================================
# Valida las cifras del RFCST que comparte Suscripcion
# (pestana BD_RFCST26) contra:
#
#   V1. Real acumulado a Julio 2026 + cuadre interno
#       del incremento Ago-Dic
#   V2. Ppto Ago-Dic 2026 ajustado por nivel de
#       ejecucion Ene-Jul
#   V3. Reales 2025 (cierre y Ago-Dic)
#   V4. Factores historicos y de Ppto
#   V5. Ppto 2026 ano completo
#   V6. Calidad de datos
#
# Output:
#   - Outputs/VAL_RFCST26.xlsx        (detalle + resumen)
#   - Outputs/Dashboard_RFCST26.html  (dashboard PRISMA:
#       General / Linea de Negocio / Contrato / Cedente /
#       MGA con filtros interactivos)
# =====================================================

import os
import json
import math
import time
import getpass
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

# Verificacion temprana de dependencias: mejor avisar aqui
# que tronar despues de procesar toda la base
_faltantes = []

for _modulo, _paquete in (("openpyxl", "openpyxl"), ("xlsxwriter", "xlsxwriter")):
    try:
        __import__(_modulo)
    except ImportError:
        _faltantes.append(_paquete)

if _faltantes:
    raise SystemExit(
        "Faltan paquetes requeridos: " + ", ".join(_faltantes) + "\n"
        "Instalalos con:  pip install " + " ".join(_faltantes)
    )

# =====================================================
# CONFIGURACION
# =====================================================

warnings.filterwarnings("ignore")

inicio = time.perf_counter()

usuario = getpass.getuser()

# Por default trabaja en la carpeta donde vive el script.
# Para usar la ruta de OneDrive, descomentar y ajustar:
# xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\2026\4_Validacion"
xFolder = os.path.dirname(os.path.abspath(__file__))

xInputs = os.path.join(xFolder, "Inputs")
xOutputs = os.path.join(xFolder, "Outputs")

os.makedirs(xOutputs, exist_ok=True)

ARCHIVO_BASE = "BD_RFCST_26_act.xlsx"

# Seleccion del input, en este orden:
#   1. El nombre exacto de la base oficial, en Inputs o junto al script
#   2. Si no existe, la BD_RFCST*.xlsx mas reciente (por fecha de
#      modificacion), avisando cuales otras se ignoraron
archivo = None

for carpeta in (xInputs, xFolder):
    ruta = os.path.join(carpeta, ARCHIVO_BASE)
    if os.path.exists(ruta):
        archivo = ruta
        break

if archivo is None:
    candidatos = sorted(
        {
            os.path.join(carpeta, f)
            for carpeta in (xInputs, xFolder)
            if os.path.isdir(carpeta)
            for f in os.listdir(carpeta)
            if f.startswith("BD_RFCST") and f.endswith(".xlsx")
            and not f.startswith("~$")
        },
        key=os.path.getmtime,
        reverse=True,
    )
    if not candidatos:
        raise FileNotFoundError(
            f"No se encontro {ARCHIVO_BASE} ni BD_RFCST*.xlsx en {xInputs} ni en {xFolder}"
        )
    archivo = candidatos[0]
    if len(candidatos) > 1:
        print(f"AVISO: no se encontro {ARCHIVO_BASE} y hay varias bases BD_RFCST*.xlsx.")
        print("Se usa la mas reciente; elimina o renombra las viejas si no es la correcta:")
        for c in candidatos:
            marca = "->" if c == archivo else "  "
            fecha = datetime.fromtimestamp(os.path.getmtime(c)).strftime("%d/%m/%Y %H:%M")
            print(f"  {marca} {os.path.basename(c)}  (modificada {fecha})")

HOJA = "BD_RFCST26"
TOL = 1.0                    # tolerancia en USD para comparaciones
MATERIALIDAD = 10_000        # USD: contratos por debajo no escalan a ROJO

# Umbrales de semaforo (desviaciones relativas)
UMBRAL_AMARILLO = 0.20
UMBRAL_ROJO = 0.40

# Umbrales de indices tecnicos del forecast
IND_SIN_AMARILLO = 0.80      # siniestralidad
IND_SIN_ROJO = 1.00
IND_COS_AMARILLO = 0.35      # costo de adquisicion
IND_COS_ROJO = 0.50

# Ponderaciones del score de riesgo
PESO_INC = 0.30              # desviacion incremento Ago-Dic vs ppto
PESO_SIN = 0.30              # siniestralidad forecast
PESO_COS = 0.15              # costos forecast
PESO_V25 = 0.25              # desviacion crecimiento vs factor Ppto

# Hoja opcional con el presupuesto 2026 completo. La base
# BD_RFCST26 solo trae presupuesto de los contratos que ya
# registraron prima, por eso las CIFRAS GLOBALES toman el ppto
# de esta hoja (los contratos presupuestados sin prima aun se
# capturaron manualmente ahi). Las graficas por LN siguen
# usando el ppto de BD_RFCST26.
HOJA_PPTO = "Ppto2026"

# Nombres de columna en la hoja Ppto2026 (ajustar si cambian)
COL_PPTO = {
    "Primas": "PmasEmi",
    "Siniestros": "SinOcurr",
    "Costos": "CostosAdq",
}

# Columnas candidatas para acotar el presupuesto al ejercicio
# 2026 y para separar el periodo Ago-Dic
ANIO_PPTO = 2026
COLS_ANIO = ["0FISCYEAR", "FISCYEAR", "Ejercicio", "Año", "Anio", "Year", "AñoCont"]
COLS_PERIODO = ["0FISCPER", "FISCPER", "Periodo", "Período", "Mes", "Month", "PerCont"]
MESES_AGODIC = [8, 9, 10, 11, 12]
MESES_ENEJUL = [1, 2, 3, 4, 5, 6, 7]

# Medidas y sufijos de columnas de la base
MEDIDAS = ["Primas", "Siniestros", "Costos"]
SUFIJOS = ["0726", "1226", "08-1226", "PPTO1226",
           "PPTO08-1226", "PPTO01-0726", "1225", "08-1225"]

# =====================================================
# CARGA
# =====================================================

print(f"Leyendo {archivo} ...")

# La base original trae los encabezados en la fila 5 y otras
# versiones en la fila 2: se detecta buscando la celda "LN"
_crudo = pd.read_excel(archivo, sheet_name=HOJA, header=None, nrows=8)

fila_encabezado = None
for _i in range(len(_crudo)):
    if any(str(v).strip() == "LN" for v in _crudo.iloc[_i]):
        fila_encabezado = _i
        break

if fila_encabezado is None:
    raise ValueError(f"No se encontro la fila de encabezados (columna LN) en {HOJA}")

df = pd.read_excel(archivo, sheet_name=HOJA, header=fila_encabezado)

df.columns = [str(c).strip() for c in df.columns]

# Formato original: la primera 'Compañía' es el nombre de la
# cedente y 'Compañía.1' su numero
if "Compañía_Nombre" not in df.columns:
    df = df.rename(columns={"Compañía": "Compañía_Nombre", "Compañía.1": "Compañía"})

df = df[df["LN"].notna()].copy()
df["LN"] = df["LN"].astype(str).str.strip()

# La base original no trae el incremento Ago-Dic en columnas
# propias: se deriva como acumulado Dic menos acumulado Jul
for _m in MEDIDAS:
    if f"{_m} 08-1226" not in df.columns:
        df[f"{_m} 08-1226"] = (
            pd.to_numeric(df[f"{_m} 1226"], errors="coerce").fillna(0)
            - pd.to_numeric(df[f"{_m} 0726"], errors="coerce").fillna(0)
        )

# =====================================================
# LIMPIEZA
# =====================================================

columnas_numericas = [f"{m} {s}" for m in MEDIDAS for s in SUFIJOS] + [
    "Incr. Primas Hist", "Ind. Sin. Hist", "Ind. Cos. Hist",
    "Incr. Primas Ppto", "Ind. Sin. Ppto", "Ind. Cos. Ppto",
]

for col in columnas_numericas:
    df[col] = pd.to_numeric(df[col], errors="coerce")

columnas_dim = [
    "Fuente/Hoja", "LN", "Tipo Reaseguro", "Compañía_Nombre", "País",
    "Tipo Rea", "Binder Ppto", "Corredor", "Compañía", "Num Contrato",
    "Año Susc.",
]

df = df[columnas_dim + columnas_numericas].copy()

# Cardinalidad segun la fuente: Contrato / Cedente / MGA
df["Cardinalidad"] = np.select(
    [
        df["Fuente/Hoja"].str.contains("Contrato", na=False),
        df["Fuente/Hoja"].str.contains("Cedente", na=False),
        df["Fuente/Hoja"].str.contains("MGA", na=False),
    ],
    ["Contrato", "Cedente", "MGA"],
    default="Otro",
)

# Las medidas monetarias se comparan con NaN tratado como 0
medidas_cols = [f"{m} {s}" for m in MEDIDAS for s in SUFIJOS]
df[medidas_cols] = df[medidas_cols].fillna(0)


def _ratio(num, den, min_den=TOL):
    """Division protegida: NaN cuando el denominador es menor a min_den.
    Para crecimientos contra bases historicas usar min_den=MATERIALIDAD,
    de lo contrario una base minima produce porcentajes absurdos."""
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    return np.where(np.abs(den) > min_den, num / np.where(den == 0, np.nan, den), np.nan)


# =====================================================
# V1. FORECAST vs REAL ACUMULADO A JULIO 2026
# =====================================================
# El RFCST 1226 es acumulado a diciembre: nunca deberia
# ser menor a lo ya registrado al corte de julio. La base
# ya trae el incremento Ago-Dic en columnas propias
# (08-1226); se valida ademas su cuadre interno.

df["Inc_Primas_AgoDic"] = df["Primas 08-1226"]
df["Inc_Siniestros_AgoDic"] = df["Siniestros 08-1226"]
df["Inc_Costos_AgoDic"] = df["Costos 08-1226"]

df["F_V1_Primas"] = df["Inc_Primas_AgoDic"] < -TOL
df["F_V1_Siniestros"] = df["Inc_Siniestros_AgoDic"] < -TOL
df["F_V1_Costos"] = df["Inc_Costos_AgoDic"] < -TOL

# Cuadre interno: (1226 - 0726) debe ser igual a 08-1226
df["F_V1_Cuadre"] = (
    ((df["Primas 1226"] - df["Primas 0726"]) - df["Primas 08-1226"]).abs() > TOL
) | (
    ((df["Siniestros 1226"] - df["Siniestros 0726"]) - df["Siniestros 08-1226"]).abs() > TOL
) | (
    ((df["Costos 1226"] - df["Costos 0726"]) - df["Costos 08-1226"]).abs() > TOL
)

# =====================================================
# V2. INCREMENTO AGO-DIC vs PPTO AGO-DIC
# =====================================================
# El incremento que Suscripcion proyecta para Ago-Dic se
# compara contra lo presupuestado para ese mismo periodo.
# El ratio de ejecucion Ene-Jul se conserva como contexto.

df["Ratio_Ejecucion"] = _ratio(df["Primas 0726"], df["Primas PPTO01-0726"])

df["Desv_Inc_AgoDic"] = _ratio(
    df["Inc_Primas_AgoDic"], df["Primas PPTO08-1226"]
) - 1

# =====================================================
# V3. COHERENCIA vs REALES 2025
# =====================================================

df["Crec_vs_Real25"] = _ratio(df["Primas 1226"], df["Primas 1225"],
                              min_den=MATERIALIDAD) - 1

df["Crec_AgoDic_vs_25"] = _ratio(df["Inc_Primas_AgoDic"], df["Primas 08-1225"],
                                 min_den=MATERIALIDAD) - 1

# Desviacion del crecimiento forecast contra el factor de
# incremento que traia el Ppto (puntos porcentuales)
df["Desv_Crec_vs_Factor"] = df["Crec_vs_Real25"] - df["Incr. Primas Ppto"]

# =====================================================
# V4. INDICES TECNICOS DEL FORECAST vs FACTORES
# =====================================================

df["Ind_Sin_FCST"] = _ratio(df["Siniestros 1226"], df["Primas 1226"])
df["Ind_Cos_FCST"] = _ratio(df["Costos 1226"], df["Primas 1226"])

df["Desv_Sin_vs_Hist"] = df["Ind_Sin_FCST"] - df["Ind. Sin. Hist"]
df["Desv_Cos_vs_Hist"] = df["Ind_Cos_FCST"] - df["Ind. Cos. Hist"]

# =====================================================
# V5. FORECAST vs PPTO ANO COMPLETO
# =====================================================

df["Var_Primas_PPTO"] = _ratio(df["Primas 1226"], df["Primas PPTO1226"]) - 1
df["Gap_Primas_PPTO"] = df["Primas 1226"] - df["Primas PPTO1226"]
df["Cumplimiento_PPTO"] = _ratio(df["Primas 1226"], df["Primas PPTO1226"])

# =====================================================
# V6. CALIDAD DE DATOS
# =====================================================

df["F_V6_PrimaNegativa"] = df["Primas 1226"] < -TOL

df["F_V6_FcstCero"] = (df["Primas 1226"].abs() <= TOL) & (df["Primas 0726"] > TOL)

df["F_V6_SinPpto"] = (df["Primas PPTO1226"].abs() <= TOL) & (df["Primas 1226"] > TOL)

df["F_V6_SinFactores"] = df["Incr. Primas Ppto"].isna() & (df["Primas 1226"] > TOL)

df["F_V6_SinExcede100"] = df["Ind_Sin_FCST"] > 1.0

df["F_V6_SinNegativo"] = df["Siniestros 1226"] < -MATERIALIDAD

# Materialidad: contratos con prima relevante en el forecast
# o en el real a julio
df["Material"] = (
    (df["Primas 1226"].abs() > MATERIALIDAD)
    | (df["Primas 0726"].abs() > MATERIALIDAD)
)

# =====================================================
# FLAGS AGREGADOS POR CONTRATO
# =====================================================

flags = [c for c in df.columns if c.startswith("F_")]

df["Num_Flags"] = df[flags].sum(axis=1)

df["Tiene_Alerta"] = df["Num_Flags"] > 0

# =====================================================
# RESUMENES
# =====================================================


def resumen_por(claves):

    agg = {"Contratos": ("LN", "size"),
           "Contratos_Alerta": ("Tiene_Alerta", "sum"),
           "Flags_V1": ("F_V1_Primas", "sum")}

    for m, corto in zip(MEDIDAS, ["P", "S", "C"]):
        agg[f"{corto}_0726"] = (f"{m} 0726", "sum")
        agg[f"{corto}_1226"] = (f"{m} 1226", "sum")
        agg[f"{corto}_Inc"] = (f"{m} 08-1226", "sum")
        agg[f"{corto}_PPTO"] = (f"{m} PPTO1226", "sum")
        agg[f"{corto}_PPTO_0812"] = (f"{m} PPTO08-1226", "sum")
        agg[f"{corto}_PPTO_0107"] = (f"{m} PPTO01-0726", "sum")
        agg[f"{corto}_1225"] = (f"{m} 1225", "sum")
        agg[f"{corto}_0812_25"] = (f"{m} 08-1225", "sum")

    r = df.groupby(claves).agg(**agg).reset_index()

    # Indices y desviaciones recalculados sobre agregados
    # (no promedio de razones)
    r["Ratio_Ejecucion"] = _ratio(r["P_0726"], r["P_PPTO_0107"])
    r["Desv_Inc_AgoDic"] = _ratio(r["P_Inc"], r["P_PPTO_0812"]) - 1

    r["Cumplimiento_PPTO"] = _ratio(r["P_1226"], r["P_PPTO"])
    r["Var_Primas_PPTO"] = r["Cumplimiento_PPTO"] - 1
    r["Gap_Primas"] = r["P_1226"] - r["P_PPTO"]

    r["Crec_vs_Real25"] = _ratio(r["P_1226"], r["P_1225"],
                                 min_den=MATERIALIDAD) - 1
    r["Crec_AgoDic_vs_25"] = _ratio(r["P_Inc"], r["P_0812_25"],
                                    min_den=MATERIALIDAD) - 1

    r["Ind_Sin_FCST"] = _ratio(r["S_1226"], r["P_1226"])
    r["Ind_Cos_FCST"] = _ratio(r["C_1226"], r["P_1226"])
    r["Ind_Sin_Real25"] = _ratio(r["S_1225"], r["P_1225"])
    r["Ind_Cos_Real25"] = _ratio(r["C_1225"], r["P_1225"])

    r["Pct_Alerta"] = r["Contratos_Alerta"] / r["Contratos"]

    # Metricas estilo ANA_RFCST: variaciones y gaps de las tres
    # medidas, indices vs ppto, y P-S-C (resultado tecnico sin
    # reservas ni gastos, por eso el nombre neutro)
    r["Var_Siniestros_PPTO"] = _ratio(r["S_1226"], r["S_PPTO"]) - 1
    r["Var_Costos_PPTO"] = _ratio(r["C_1226"], r["C_PPTO"]) - 1
    r["Gap_Siniestros"] = r["S_1226"] - r["S_PPTO"]
    r["Gap_Costos"] = r["C_1226"] - r["C_PPTO"]

    r["Ind_Sin_PPTO"] = _ratio(r["S_PPTO"], r["P_PPTO"])
    r["Ind_Cos_PPTO"] = _ratio(r["C_PPTO"], r["P_PPTO"])
    r["Var_Ind_Sin"] = r["Ind_Sin_FCST"] - r["Ind_Sin_PPTO"]
    r["Var_Ind_Cos"] = r["Ind_Cos_FCST"] - r["Ind_Cos_PPTO"]

    r["P_S_C"] = r["P_1226"] - r["S_1226"] - r["C_1226"]
    r["Pct_P_S_C"] = _ratio(r["P_S_C"], r["P_1226"])
    r["P_S_C_PPTO"] = r["P_PPTO"] - r["S_PPTO"] - r["C_PPTO"]
    r["Pct_P_S_C_PPTO"] = _ratio(r["P_S_C_PPTO"], r["P_PPTO"])
    r["P_S_C_1225"] = r["P_1225"] - r["S_1225"] - r["C_1225"]
    r["Pct_P_S_C_1225"] = _ratio(r["P_S_C_1225"], r["P_1225"])

    return r


resumen = resumen_por(["LN"])
resumen_tiporea = resumen_por(["LN", "Tipo Reaseguro"])
resumen_fuente = resumen_por(["Fuente/Hoja"])
resumen_card = resumen_por(["Cardinalidad"])
resumen_pais = resumen_por(["País"]).sort_values("P_1226", ascending=False)

# =====================================================
# SEMAFOROS
# =====================================================


def semaforo_desviacion(x):

    if pd.isna(x):
        return "SIN DATO"

    if abs(x) > UMBRAL_ROJO:
        return "ROJO"

    elif abs(x) > UMBRAL_AMARILLO:
        return "AMARILLO"

    else:
        return "VERDE"


def semaforo_sin(x):

    if pd.isna(x):
        return "SIN DATO"

    if x > IND_SIN_ROJO:
        return "ROJO"

    elif x > IND_SIN_AMARILLO:
        return "AMARILLO"

    elif x < -0.05:
        # siniestros netos negativos: revisar recuperaciones
        return "AMARILLO"

    else:
        return "VERDE"


def semaforo_costos(x):

    if pd.isna(x):
        return "SIN DATO"

    if x > IND_COS_ROJO:
        return "ROJO"

    elif x > IND_COS_AMARILLO:
        return "AMARILLO"

    else:
        return "VERDE"


def aplicar_semaforos(tabla):
    tabla["Semaforo_Inc"] = tabla["Desv_Inc_AgoDic"].apply(semaforo_desviacion)
    tabla["Semaforo_Sin"] = tabla["Ind_Sin_FCST"].apply(semaforo_sin)
    tabla["Semaforo_Costos"] = tabla["Ind_Cos_FCST"].apply(semaforo_costos)
    tabla["Semaforo_vs_25"] = tabla["Crec_AgoDic_vs_25"].apply(semaforo_desviacion)
    return tabla


# Cortes adicionales estilo ANA_RFCST (por nivel de agrupacion)
resumen_ln_corredor = resumen_por(["LN", "Corredor"])
resumen_ln_compania = resumen_por(["LN", "Compañía_Nombre"])
resumen_ln_binder = resumen_por(["LN", "Binder Ppto"])
resumen_ln_contrato = resumen_por(["LN", "Num Contrato"])

for tabla in (resumen, resumen_tiporea, resumen_fuente, resumen_card, resumen_pais,
              resumen_ln_corredor, resumen_ln_compania, resumen_ln_binder,
              resumen_ln_contrato):
    aplicar_semaforos(tabla)

# Participacion de cada LN en la prima y en el gap (estilo ANA)
resumen["Participacion_Prima"] = resumen["P_1226"] / resumen["P_1226"].sum()
resumen["Participacion_Gap"] = (
    resumen["Gap_Primas"].abs() / resumen["Gap_Primas"].abs().sum()
)

# Pareto del gap vs ppto por LN y compania
pareto_gap = resumen_ln_compania.sort_values("Gap_Primas", ascending=False).copy()
pareto_gap["Gap_Acumulado"] = pareto_gap["Gap_Primas"].cumsum()
pareto_gap["Pct_Acum_Gap"] = pareto_gap["Gap_Acumulado"] / pareto_gap["Gap_Primas"].sum()

df["Semaforo_Inc"] = df["Desv_Inc_AgoDic"].apply(semaforo_desviacion)
df["Semaforo_Sin"] = df["Ind_Sin_FCST"].apply(semaforo_sin)
df["Semaforo_Costos"] = df["Ind_Cos_FCST"].apply(semaforo_costos)

# Semaforo global por contrato:
#   ROJO     inconsistencia dura en contrato material
#   AMARILLO contrato material con alertas suaves
#   VERDE    limpio o por debajo de materialidad
inconsistencia_dura = (
    df["F_V1_Primas"]
    | df["F_V1_Cuadre"]
    | df["F_V6_PrimaNegativa"]
    | df["F_V6_FcstCero"]
    | df["F_V6_SinExcede100"]
)

alerta_suave = (
    df["Tiene_Alerta"]
    | (df["Semaforo_Inc"] != "VERDE")
    | (df["Semaforo_Sin"] != "VERDE")
    | (df["Semaforo_Costos"] != "VERDE")
)

df["Semaforo_Global"] = np.select(
    [
        inconsistencia_dura & df["Material"],
        alerta_suave & df["Material"],
    ],
    ["ROJO", "AMARILLO"],
    default="VERDE",
)

# =====================================================
# SCORE DE RIESGO POR LN
# =====================================================


def _score(serie, tope=1.0):
    s = serie.abs().fillna(tope) / tope
    return np.minimum(s, 1.0) * 100


resumen["Score_Inc"] = _score(resumen["Desv_Inc_AgoDic"], tope=0.60)
resumen["Score_Sin"] = np.minimum(resumen["Ind_Sin_FCST"].fillna(1.0), 1.2) / 1.2 * 100
resumen["Score_Costos"] = np.minimum(resumen["Ind_Cos_FCST"].fillna(0.6), 0.6) / 0.6 * 100
resumen["Score_vs_25"] = _score(resumen["Crec_AgoDic_vs_25"], tope=1.0)

resumen["Score_Total"] = (
    resumen["Score_Inc"] * PESO_INC
    + resumen["Score_Sin"] * PESO_SIN
    + resumen["Score_Costos"] * PESO_COS
    + resumen["Score_vs_25"] * PESO_V25
)


def nivel_riesgo(x):

    if x >= 80:
        return "CRITICO"

    elif x >= 60:
        return "ALTO"

    elif x >= 40:
        return "MEDIO"

    else:
        return "BAJO"


resumen["Nivel_Riesgo"] = resumen["Score_Total"].apply(nivel_riesgo)

# =====================================================
# RANKING Y EXCEPCIONES
# =====================================================

ranking = (
    resumen.sort_values("Score_Total", ascending=False)
    .reset_index(drop=True)
)

ranking["Ranking"] = ranking.index + 1

excepciones = df[df["Semaforo_Global"] == "ROJO"].copy()

excepciones["Impacto"] = (
    excepciones["Inc_Primas_AgoDic"].where(
        excepciones["F_V1_Primas"], excepciones["Primas 1226"].abs()
    )
).abs()

excepciones = excepciones.sort_values("Impacto", ascending=False)

# =====================================================
# PRESUPUESTO 2026 COMPLETO (hoja Ppto2026)
# =====================================================
# Solo alimenta las cifras GLOBALES. Si la hoja no existe
# se avisa y se usa el ppto de BD_RFCST26.


def _buscar_columna(cols, candidatas):
    """Devuelve la primera columna cuyo nombre coincida (sin
    distinguir mayusculas ni acentos de mas) con las candidatas."""
    norm = {str(c).strip().upper(): c for c in cols}
    for cand in candidatas:
        if cand.strip().upper() in norm:
            return norm[cand.strip().upper()]
    return None


def _meses_de(serie):
    """Deriva el mes (1-12) de una columna de periodo, aceptando
    1-12, AAAAMM y fechas."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie.dt.month

    num = pd.to_numeric(serie, errors="coerce")

    if num.notna().sum() == 0:
        return None

    maximo = num.max()

    if maximo <= 12:
        return num
    if maximo >= 100_000:          # AAAAMM
        return num % 100
    if maximo <= 12_12:            # AAMM u otro compacto
        return num % 100

    return None


def cargar_ppto2026(ruta):

    try:
        crudo = pd.read_excel(ruta, sheet_name=HOJA_PPTO, header=None, nrows=12)
    except ValueError:
        print(f"AVISO: el libro no tiene la hoja '{HOJA_PPTO}'.")
        print("       Las cifras globales usaran el ppto de BD_RFCST26,")
        print("       que solo cubre contratos con prima registrada.")
        return None

    col_primas = COL_PPTO["Primas"]

    fila = None
    for i in range(len(crudo)):
        if any(str(v).strip() == col_primas for v in crudo.iloc[i]):
            fila = i
            break

    if fila is None:
        print(f"AVISO: en la hoja '{HOJA_PPTO}' no se encontro la columna "
              f"'{col_primas}'; se usa el ppto de BD_RFCST26.")
        return None

    p = pd.read_excel(ruta, sheet_name=HOJA_PPTO, header=fila)
    p.columns = [str(c).strip() for c in p.columns]

    faltantes = [c for c in COL_PPTO.values() if c not in p.columns]
    if faltantes:
        print(f"AVISO: a la hoja '{HOJA_PPTO}' le faltan columnas {faltantes}; "
              "se usa el ppto de BD_RFCST26.")
        return None

    filas_totales = len(p)

    # Acotar al ejercicio presupuestado
    col_anio = _buscar_columna(p.columns, COLS_ANIO)
    if col_anio is not None:
        anios = pd.to_numeric(p[col_anio], errors="coerce")
        p = p[anios == ANIO_PPTO]
        print(f"  {HOJA_PPTO}: filtrado {col_anio} = {ANIO_PPTO} "
              f"({len(p):,} de {filas_totales:,} filas)")
    else:
        print(f"  AVISO: en '{HOJA_PPTO}' no se encontro columna de ejercicio "
              f"{COLS_ANIO}; se suman las {filas_totales:,} filas de la hoja.")
        print("         Verifica que la hoja solo contenga el presupuesto 2026.")

    # Separar Ago-Dic
    col_periodo = _buscar_columna(p.columns, COLS_PERIODO)
    meses = _meses_de(p[col_periodo]) if col_periodo is not None else None

    if meses is None and col_periodo is not None:
        print(f"  AVISO: no se pudo interpretar el periodo de '{col_periodo}'.")

    ppto = {}

    for medida, col in COL_PPTO.items():
        vals = pd.to_numeric(p[col], errors="coerce").fillna(0)
        d = {"anual": float(vals.sum())}
        if meses is not None:
            d["agodic"] = float(vals[meses.isin(MESES_AGODIC)].sum())
            d["enejul"] = float(vals[meses.isin(MESES_ENEJUL)].sum())
        ppto[medida] = d

    if meses is not None:
        print(f"  {HOJA_PPTO}: periodo tomado de '{col_periodo}' "
              "(Ago-Dic y Ene-Jul disponibles)")
    else:
        print(f"  AVISO: sin columna de periodo en '{HOJA_PPTO}'; el ppto "
              "Ago-Dic global se toma de BD_RFCST26.")

    for medida, d in ppto.items():
        detalle = f"anual {d['anual'] / 1e6:,.1f} M"
        if "agodic" in d:
            detalle += f" · Ago-Dic {d['agodic'] / 1e6:,.1f} M"
        print(f"  {HOJA_PPTO} · {medida}: {detalle}")

    return ppto


print("Presupuesto 2026 completo:")
PPTO2026 = cargar_ppto2026(archivo)

FUENTE_PPTO = (
    f"hoja {HOJA_PPTO} (presupuesto completo)" if PPTO2026
    else "BD_RFCST26 (solo contratos con prima)"
)

# =====================================================
# GLOBALES POR MEDIDA (P / S / C y P-S-C)
# =====================================================


def global_medida(sub, m):
    g = {
        "a0726": sub[f"{m} 0726"].sum(),
        "fcst": sub[f"{m} 1226"].sum(),
        "inc": sub[f"{m} 08-1226"].sum(),
        "ppto": sub[f"{m} PPTO1226"].sum(),
        "ppto0812": sub[f"{m} PPTO08-1226"].sum(),
        "ppto0107": sub[f"{m} PPTO01-0726"].sum(),
        "real25": sub[f"{m} 1225"].sum(),
        "real0812": sub[f"{m} 08-1225"].sum(),
    }
    # El presupuesto global sale de la hoja Ppto2026 cuando esta
    # disponible: BD_RFCST26 solo trae ppto de contratos que ya
    # registraron prima y subestima el presupuesto real
    if PPTO2026 and m in PPTO2026:
        g["ppto"] = PPTO2026[m]["anual"]
        if "agodic" in PPTO2026[m]:
            g["ppto0812"] = PPTO2026[m]["agodic"]
            g["ppto0107"] = PPTO2026[m]["enejul"]

    g["var_ppto"] = g["fcst"] / g["ppto"] - 1 if abs(g["ppto"]) > TOL else float("nan")
    g["crec25"] = g["fcst"] / g["real25"] - 1 if abs(g["real25"]) > TOL else float("nan")

    # El incremento Ago-Dic se compara contra lo presupuestado
    # para ese mismo periodo
    g["desv_inc"] = (g["inc"] / g["ppto0812"] - 1
                     if abs(g["ppto0812"]) > TOL else float("nan"))
    return g


GLOB = {m: global_medida(df, m) for m in MEDIDAS}

PSC = {k: GLOB["Primas"][k] - GLOB["Siniestros"][k] - GLOB["Costos"][k]
       for k in ("a0726", "fcst", "inc", "ppto", "ppto0812", "real25", "real0812")}
PSC["var_ppto"] = PSC["fcst"] / PSC["ppto"] - 1 if abs(PSC["ppto"]) > TOL else float("nan")
PSC["crec25"] = PSC["fcst"] / PSC["real25"] - 1 if abs(PSC["real25"]) > TOL else float("nan")

PCT_PSC = {
    "fcst": PSC["fcst"] / GLOB["Primas"]["fcst"],
    "ppto": PSC["ppto"] / GLOB["Primas"]["ppto"],
    "real25": PSC["real25"] / GLOB["Primas"]["real25"],
}

sem_counts = df["Semaforo_Global"].value_counts()
n_verde = int(sem_counts.get("VERDE", 0))
n_amarillo = int(sem_counts.get("AMARILLO", 0))
n_rojo = int(sem_counts.get("ROJO", 0))
n_v1 = int(df["F_V1_Primas"].sum())

# =====================================================
# DASHBOARD (KPIs para Excel)
# =====================================================

gp = GLOB["Primas"]

dashboard = pd.DataFrame({

    "Indicador": [
        "Contratos analizados",
        "Lineas de negocio",
        "Prima Forecast 2026",
        "Prima Real corte Jul 2026",
        "Prima PPTO 2026",
        "Prima Real 2025",
        "Cumplimiento FCST vs PPTO",
        "Crecimiento FCST vs Real 2025",
        "Incremento Ago-Dic",
        "Ppto Ago-Dic 2026",
        "Desviacion incremento Ago-Dic",
        "Real Ago-Dic 2025 (referencia)",
        "Siniestralidad FCST",
        "Costos FCST",
        "P-S-C Forecast 2026",
        "%P-S-C Forecast 2026",
        "Contratos VERDE",
        "Contratos AMARILLO",
        "Contratos ROJO",
        "Contratos FCST < Real Jul (V1)",
        "LN en riesgo ALTO/CRITICO",
    ],

    "Valor": [
        len(df),
        df["LN"].nunique(),
        gp["fcst"],
        gp["a0726"],
        gp["ppto"],
        gp["real25"],
        gp["fcst"] / gp["ppto"],
        gp["crec25"],
        gp["inc"],
        gp["ppto0812"],
        gp["desv_inc"],
        gp["real0812"],
        GLOB["Siniestros"]["fcst"] / gp["fcst"],
        GLOB["Costos"]["fcst"] / gp["fcst"],
        PSC["fcst"],
        PCT_PSC["fcst"],
        n_verde,
        n_amarillo,
        n_rojo,
        n_v1,
        int((resumen["Nivel_Riesgo"].isin(["ALTO", "CRITICO"])).sum()),
    ],

})

# =====================================================
# RESUMEN GLOBAL P/S/C (para el correo del reporte)
# =====================================================

filas_global = []

for nombre, g in [("Primas", GLOB["Primas"]), ("Siniestros", GLOB["Siniestros"]),
                  ("Costos", GLOB["Costos"]), ("P-S-C *", PSC)]:
    filas_global.append({
        "Concepto": nombre,
        "FCST Dic26": g["fcst"],
        "PPTO 2026": g["ppto"],
        "Var $ vs PPTO": g["fcst"] - g["ppto"],
        "Var % vs PPTO": g["var_ppto"],
        "Real 2025": g["real25"],
        "Var $ vs Real25": g["fcst"] - g["real25"],
        "Var % vs Real25": g["crec25"],
        "Inc. Ago-Dic": g["inc"],
        "Ppto Ago-Dic": g.get("ppto0812", float("nan")),
        "Real Ago-Dic 25": g["real0812"],
    })

filas_global.append({
    "Concepto": "%P-S-C *",
    "FCST Dic26": PCT_PSC["fcst"],
    "PPTO 2026": PCT_PSC["ppto"],
    "Var $ vs PPTO": float("nan"),
    "Var % vs PPTO": PCT_PSC["fcst"] - PCT_PSC["ppto"],
    "Real 2025": PCT_PSC["real25"],
    "Var $ vs Real25": float("nan"),
    "Var % vs Real25": PCT_PSC["fcst"] - PCT_PSC["real25"],
    "Inc. Ago-Dic": float("nan"),
    "Ppto Ago-Dic": float("nan"),
    "Real Ago-Dic 25": float("nan"),
})

resumen_global = pd.DataFrame(filas_global)

# =====================================================
# PARAMETROS (documentacion de supuestos)
# =====================================================

parametros = pd.DataFrame({
    "Parametro": [
        "Archivo fuente", "Hoja", "Fuente ppto global", "Fecha de corte",
        "Tolerancia (USD)",
        "Materialidad (USD)",
        "Umbral amarillo desviaciones", "Umbral rojo desviaciones",
        "Siniestralidad amarilla", "Siniestralidad roja",
        "Costos amarillo", "Costos rojo",
        "Peso score: incremento Ago-Dic", "Peso score: siniestralidad",
        "Peso score: costos", "Peso score: vs Real 2025",
        "Nota P-S-C",
        "Generado por", "Fecha de ejecucion",
    ],
    "Valor": [
        os.path.basename(archivo), HOJA, FUENTE_PPTO, "Julio 2026", TOL,
        MATERIALIDAD,
        UMBRAL_AMARILLO, UMBRAL_ROJO,
        IND_SIN_AMARILLO, IND_SIN_ROJO,
        IND_COS_AMARILLO, IND_COS_ROJO,
        PESO_INC, PESO_SIN, PESO_COS, PESO_V25,
        "* Falta el incremento a la reserva y los costos de cobertura",
        usuario, datetime.now().strftime("%Y-%m-%d %H:%M"),
    ],
    "Descripcion": [
        "Base compartida por Suscripcion", "Pestana con el detalle por contrato",
        "De donde salen las cifras globales de presupuesto",
        "Real acumulado 7 meses (7+5)",
        "Diferencias menores a este monto no generan alerta",
        "Contratos con prima menor a este monto no escalan a ROJO",
        "Desviacion relativa que marca AMARILLO",
        "Desviacion relativa que marca ROJO",
        "Ind. siniestralidad FCST > umbral marca AMARILLO",
        "Ind. siniestralidad FCST > umbral marca ROJO",
        "Ind. costos FCST > umbral marca AMARILLO",
        "Ind. costos FCST > umbral marca ROJO",
        "V2: incremento Ago-Dic vs lo presupuestado en ese periodo",
        "V4: siniestralidad implicita del forecast",
        "V4: costos implicitos del forecast",
        "V3: incremento Ago-Dic vs mismo periodo 2025",
        "P-S-C no es resultado tecnico: no incluye reservas ni gastos",
        "Usuario que ejecuto el script", "",
    ],
})

# =====================================================
# EXPORT EXCEL
# =====================================================

salida_xlsx = os.path.join(xOutputs, "VAL_RFCST26.xlsx")

cols_resumen = [
    "LN", "Contratos", "P_0726", "P_1226", "P_PPTO", "P_1225",
    "P_Inc", "P_PPTO_0812", "Desv_Inc_AgoDic", "Semaforo_Inc",
    "Cumplimiento_PPTO", "Gap_Primas", "Crec_vs_Real25", "Crec_AgoDic_vs_25",
    "Ind_Sin_FCST", "Ind_Sin_Real25", "Semaforo_Sin",
    "Ind_Cos_FCST", "Ind_Cos_Real25", "Semaforo_Costos",
    "Var_Siniestros_PPTO", "Var_Costos_PPTO", "Gap_Siniestros", "Gap_Costos",
    "Var_Ind_Sin", "Var_Ind_Cos", "P_S_C", "Pct_P_S_C",
    "Pct_P_S_C_PPTO", "Pct_P_S_C_1225",
    "Participacion_Prima", "Participacion_Gap",
    "Contratos_Alerta", "Pct_Alerta", "Score_Total", "Nivel_Riesgo", "Ranking",
]

cols_detalle = ["Cardinalidad"] + columnas_dim + [
    "Primas 0726", "Primas 1226", "Primas 08-1226", "Primas PPTO1226",
    "Primas PPTO08-1226", "Primas PPTO01-0726", "Primas 1225", "Primas 08-1225",
    "Siniestros 1226", "Costos 1226",
    "Ratio_Ejecucion", "Desv_Inc_AgoDic", "Crec_vs_Real25", "Crec_AgoDic_vs_25",
    "Ind_Sin_FCST", "Ind_Cos_FCST", "Var_Primas_PPTO",
] + flags + ["Num_Flags", "Semaforo_Inc", "Semaforo_Sin", "Semaforo_Costos", "Semaforo_Global"]

with pd.ExcelWriter(salida_xlsx, engine="xlsxwriter") as writer:

    wb = writer.book

    fmt_header = wb.add_format({
        "bold": True, "font_name": "Arial", "font_size": 9,
        "font_color": "#FFFFFF", "bg_color": "#1F3864",
        "border": 1, "text_wrap": True, "valign": "vcenter",
    })
    fmt_texto = wb.add_format({"font_name": "Arial", "font_size": 9})
    fmt_moneda = wb.add_format({"font_name": "Arial", "font_size": 9, "num_format": "#,##0;(#,##0);-"})
    fmt_pct = wb.add_format({"font_name": "Arial", "font_size": 9, "num_format": "0.0%;(0.0%);-"})
    fmt_rojo = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
    fmt_amarillo = wb.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})
    fmt_verde = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})

    def exportar(tabla, nombre):

        tabla.to_excel(writer, sheet_name=nombre, index=False, startrow=1, header=False)

        ws = writer.sheets[nombre]

        for j, col in enumerate(tabla.columns):
            ws.write(0, j, col, fmt_header)

            serie = tabla[col]
            nombre_l = str(col).lower()

            if serie.dtype.kind in "fi":
                es_pct = any(
                    k in nombre_l
                    for k in ("desv", "var %", "var_", "crec", "pct", "cumplimiento",
                              "ind_", "ind.", "incr.", "ratio", "score", "%p-s-c",
                              "participacion")
                )
                ws.set_column(j, j, 12, fmt_pct if es_pct else fmt_moneda)
            else:
                ws.set_column(j, j, 16, fmt_texto)

            if nombre_l.startswith("semaforo") or nombre_l == "nivel_riesgo":
                n = len(tabla)
                for valor, fmt in (
                    ("ROJO", fmt_rojo), ("CRITICO", fmt_rojo),
                    ("AMARILLO", fmt_amarillo), ("ALTO", fmt_amarillo),
                    ("VERDE", fmt_verde), ("BAJO", fmt_verde),
                ):
                    ws.conditional_format(1, j, n, j, {
                        "type": "cell", "criteria": "==",
                        "value": f'"{valor}"', "format": fmt,
                    })

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(tabla), len(tabla.columns) - 1)

    exportar(dashboard, "Dashboard")
    exportar(resumen_global, "Resumen_Global")
    exportar(ranking[cols_resumen], "Resumen_LN")
    exportar(resumen_card, "Resumen_Cardinalidad")
    exportar(resumen_tiporea, "Resumen_LN_TipoRea")
    exportar(resumen_fuente, "Resumen_Fuente")
    exportar(resumen_pais, "Resumen_Pais")
    exportar(resumen_ln_corredor, "Resumen_LN_Corredor")
    exportar(resumen_ln_compania, "Resumen_LN_Compania")
    exportar(resumen_ln_binder, "Resumen_LN_Binder")
    exportar(resumen_ln_contrato, "Resumen_LN_Contrato")

    cols_pareto = [
        "LN", "Compañía_Nombre", "Contratos", "P_1226", "P_PPTO",
        "Gap_Primas", "Gap_Acumulado", "Pct_Acum_Gap", "Var_Primas_PPTO",
        "P_S_C", "Pct_P_S_C", "Semaforo_Inc", "Semaforo_Sin",
    ]
    exportar(pareto_gap[cols_pareto], "Pareto_Gap")
    exportar(excepciones[cols_detalle].head(500), "Excepciones")
    exportar(df[cols_detalle], "Detalle_Validaciones")
    exportar(parametros, "Parametros")

print(f"Excel generado: {salida_xlsx}")

# =====================================================
# DASHBOARD HTML - PALETA Y FORMATOS
# =====================================================

C_SURFACE = "#1a1a19"
C_PAGE = "#0d0d0d"
C_INK = "#ffffff"
C_INK2 = "#c3c2b7"
C_MUTED = "#898781"
C_GRID = "#2c2c2a"
C_BASE = "#383835"
C_BORDER = "rgba(255,255,255,0.10)"

S1 = "#3987e5"   # azul    - Forecast
S2 = "#d95926"   # naranja - Presupuesto
S3 = "#199e70"   # aqua    - Real 2025

C_VERDE = "#0ca30c"
C_AMARILLO = "#fab219"
C_ROJO = "#d03b3b"


def _fmt_m(v, dec=1):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    return f"{v / 1e6:,.{dec}f} M"


def _fmt_pct(v, dec=1, signo=False):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    if v > 9.99:
        return "&gt;999%"
    if v < -9.99:
        return "&lt;-999%"
    s = "+" if (signo and v > 0) else ""
    return f"{s}{v * 100:,.{dec}f}%"


def _badge(v, bueno_arriba=True, texto=""):
    """Pastilla de variacion: verde si la direccion es favorable
    para la medida (primas arriba = bien; siniestros/costos
    arriba = mal)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return f'<b class="neu">s/d</b> {texto}'
    favorable = (v >= 0) == bueno_arriba
    cls = "up" if favorable else "down"
    return f'<b class="{cls}">{_fmt_pct(v, signo=True)}</b> {texto}'


def _kpi(icono, titulo, valor, linea2, linea3=""):
    l3 = f'<div class="d">{linea3}</div>' if linea3 else ""
    return (
        f'<div class="card kpi"><div class="t"><i>{icono}</i>{titulo}</div>'
        f'<div class="v">{valor}</div><div class="d">{linea2}</div>{l3}</div>'
    )


# =====================================================
# SECCION 1 - GENERAL (P / S / C y P-S-C)
# =====================================================

INFO_MEDIDAS = [
    ("Primas", "P", "&#128181;", True),
    ("Siniestros", "S", "&#9888;", False),
    ("Costos", "C", "&#129534;", False),
]

sec1_bloques = []

for medida, corto, icono, bueno_arriba in INFO_MEDIDAS:
    g = GLOB[medida]
    bloque = f"""
  <h3 class="med">{medida} · {corto}</h3>
  <div class="grid kpis">
    {_kpi(icono, f"{medida} Forecast 2026", _fmt_m(g['fcst']),
          _badge(g['var_ppto'], bueno_arriba, f"vs Ppto 2026 ({_fmt_m(g['ppto'])})"),
          f"Real a Jul 26: {_fmt_m(g['a0726'])}")}
    {_kpi("&#128200;", "Crecimiento vs Real 2025", _fmt_pct(g['crec25'], signo=True),
          f"FCST Dic 26 ({_fmt_m(g['fcst'])}) vs cierre Real 2025 ({_fmt_m(g['real25'])})")}
    {_kpi("&#9202;", "Incremento Ago-Dic", _fmt_m(g['inc']),
          _badge(g['desv_inc'], bueno_arriba,
                 f"vs Ppto Ago-Dic ({_fmt_m(g['ppto0812'])})"),
          f"Real Ago-Dic 2025: {_fmt_m(g['real0812'])}")}
  </div>"""
    sec1_bloques.append(bloque)

sec1_psc = f"""
  <h3 class="med">P-S-C / %P-S-C <span class="ast-mark">*</span></h3>
  <div class="grid kpis">
    {_kpi("&#128176;", "P-S-C Forecast 2026", _fmt_m(PSC['fcst']),
          _badge(PSC['var_ppto'], True, f"vs Ppto 2026 ({_fmt_m(PSC['ppto'])})"),
          f"Real 2025: {_fmt_m(PSC['real25'])}")}
    {_kpi("&#128200;", "Crecimiento P-S-C vs Real 2025", _fmt_pct(PSC['crec25'], signo=True),
          f"P-S-C FCST ({_fmt_m(PSC['fcst'])}) vs Real 2025 ({_fmt_m(PSC['real25'])})")}
    {_kpi("&#128202;", "%P-S-C Forecast 2026", _fmt_pct(PCT_PSC['fcst']),
          _badge(PCT_PSC['fcst'] - PCT_PSC['ppto'], True, "pts vs Ppto"),
          f"Ppto 2026: {_fmt_pct(PCT_PSC['ppto'])} · Real 2025: {_fmt_pct(PCT_PSC['real25'])}")}
  </div>
  <div class="ast">* Falta el incremento a la reserva y los costos de cobertura.</div>"""

insight = (
    f"El RFCST 2026 proyecta <b>{_fmt_m(gp['fcst'])}</b> de prima, "
    f"<b>{_fmt_pct(gp['var_ppto'], signo=True)}</b> sobre el presupuesto anual y "
    f"<b>{_fmt_pct(gp['crec25'], signo=True)}</b> contra el cierre real 2025. "
    f"El incremento Ago-Dic ({_fmt_m(gp['inc'])}) esta "
    f"<b>{_fmt_pct(gp['desv_inc'], signo=True)}</b> contra lo presupuestado para "
    f"ese periodo ({_fmt_m(gp['ppto0812'])}), y equivale a "
    f"{gp['inc'] / gp['real0812']:,.1f}x el real del mismo periodo 2025 "
    f"({_fmt_m(gp['real0812'])}). La siniestralidad del forecast es "
    f"<b>{_fmt_pct(GLOB['Siniestros']['fcst'] / gp['fcst'])}</b> y el P-S-C queda en "
    f"<b>{_fmt_m(PSC['fcst'])}</b> ({_fmt_pct(PCT_PSC['fcst'])} de la prima). "
    f"<b>{n_v1:,}</b> contratos reportan forecast menor al real de julio (V1)."
)

# =====================================================
# SECCION 2 - CONFIGS DE GRAFICAS POR LN
# =====================================================

r_ln = resumen.sort_values("LN").reset_index(drop=True)
LNS = r_ln["LN"].tolist()


def _vals(serie):
    out = []
    for v in serie:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            out.append(None)
        else:
            out.append(round(float(v)))
    return out


charts_cfg = []

for medida, corto, _, _ in INFO_MEDIDAS:
    charts_cfg.append({
        "el": f"ch_{corto}_niv", "fmt": "m",
        "cats": LNS,
        "series": [
            {"n": "Forecast 2026", "c": S1, "v": _vals(r_ln[f"{corto}_1226"])},
            {"n": "Ppto 2026", "c": S2, "v": _vals(r_ln[f"{corto}_PPTO"])},
            {"n": "Real 2025", "c": S3, "v": _vals(r_ln[f"{corto}_1225"])},
        ],
    })
    charts_cfg.append({
        "el": f"ch_{corto}_inc", "fmt": "m",
        "cats": LNS,
        "series": [
            {"n": "Incremento FCST Ago-Dic", "c": S1, "v": _vals(r_ln[f"{corto}_Inc"])},
            {"n": "Ppto Ago-Dic 2026", "c": S2, "v": _vals(r_ln[f"{corto}_PPTO_0812"])},
            {"n": "Real Ago-Dic 2025", "c": S3, "v": _vals(r_ln[f"{corto}_0812_25"])},
        ],
    })

psc_ln = {}
for k, suf in (("fcst", "_1226"), ("ppto", "_PPTO"), ("real25", "_1225")):
    psc_ln[k] = (r_ln["P" + suf] - r_ln["S" + suf] - r_ln["C" + suf])

charts_cfg.append({
    "el": "ch_PSC_niv", "fmt": "m",
    "cats": LNS,
    "series": [
        {"n": "Forecast 2026", "c": S1, "v": _vals(psc_ln["fcst"])},
        {"n": "Ppto 2026", "c": S2, "v": _vals(psc_ln["ppto"])},
        {"n": "Real 2025", "c": S3, "v": _vals(psc_ln["real25"])},
    ],
})


def _pct_vals(psc, primas):
    out = []
    for a, b in zip(psc, primas):
        if b is None or abs(b) < MATERIALIDAD:
            out.append(None)
        else:
            out.append(round(a / b, 4))
    return out


charts_cfg.append({
    "el": "ch_PSC_pct", "fmt": "pct",
    "cats": LNS,
    "series": [
        {"n": "Forecast 2026", "c": S1, "v": _pct_vals(psc_ln["fcst"], r_ln["P_1226"])},
        {"n": "Ppto 2026", "c": S2, "v": _pct_vals(psc_ln["ppto"], r_ln["P_PPTO"])},
        {"n": "Real 2025", "c": S3, "v": _pct_vals(psc_ln["real25"], r_ln["P_1225"])},
    ],
})

TITULOS_S2 = []
for medida, corto, _, _ in INFO_MEDIDAS:
    TITULOS_S2.append((corto, medida,
                       f"{medida} por línea de negocio",
                       "Incremento Ago-Dic por línea de negocio"))

sec2_bloques = []
for corto, medida, t_niv, t_inc in TITULOS_S2:
    sec2_bloques.append(f"""
  <h3 class="med">{medida} · {corto}</h3>
  <div class="grid dos2">
    <div class="card">
      <h2>{t_niv}</h2>
      <div class="nota">Forecast acumulado a Dic 2026 vs presupuesto anual y cierre real 2025 (USD)</div>
      <div id="ch_{corto}_niv"></div>
    </div>
    <div class="card">
      <h2>{t_inc}</h2>
      <div class="nota">Incremento que proyecta el forecast para Ago-Dic 2026 vs lo presupuestado para ese mismo periodo. Referencia: real Ago-Dic 2025.</div>
      <div id="ch_{corto}_inc"></div>
    </div>
  </div>""")

sec2_bloques.append("""
  <h3 class="med">P-S-C / %P-S-C <span class="ast-mark">*</span></h3>
  <div class="grid dos2">
    <div class="card">
      <h2>P-S-C por línea de negocio</h2>
      <div class="nota">Primas − Siniestros − Costos (USD)</div>
      <div id="ch_PSC_niv"></div>
    </div>
    <div class="card">
      <h2>%P-S-C por línea de negocio</h2>
      <div class="nota">P-S-C como % de la prima del mismo periodo. LN con prima menor a la materialidad no se grafican.</div>
      <div id="ch_PSC_pct"></div>
    </div>
  </div>
  <div class="ast">* Falta el incremento a la reserva y los costos de cobertura.</div>""")

# =====================================================
# SECCION 3 - DATOS POR CONTRATO PARA FILTROS
# =====================================================

CARD_IDX = {"Contrato": 0, "Cedente": 1, "MGA": 2}
SEM_IDX = {"VERDE": 0, "AMARILLO": 1, "ROJO": 2}


def _txt(v):
    if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def _motivos(row):
    m = []
    if row["F_V1_Primas"]:
        m.append("FCST < Real Jul")
    if row["F_V1_Cuadre"]:
        m.append("Descuadre Ago-Dic")
    if row["F_V6_PrimaNegativa"]:
        m.append("Prima negativa")
    if row["F_V6_FcstCero"]:
        m.append("FCST en cero")
    if row["F_V6_SinExcede100"]:
        m.append("Siniestralidad > 100%")
    if row["Semaforo_Inc"] == "ROJO":
        m.append("Desv. incremento")
    return " · ".join(m)


rows_js = []

for _, row in df.iterrows():
    card = CARD_IDX.get(row["Cardinalidad"])
    if card is None:
        continue
    sem = SEM_IDX[row["Semaforo_Global"]]
    imp = abs(row["Inc_Primas_AgoDic"]) if row["F_V1_Primas"] else abs(row["Primas 1226"])
    medidas_arr = []
    for m in MEDIDAS:
        medidas_arr.append([
            round(row[f"{m} 0726"]), round(row[f"{m} 1226"]),
            round(row[f"{m} 08-1226"]), round(row[f"{m} PPTO1226"]),
            round(row[f"{m} PPTO08-1226"]), round(row[f"{m} PPTO01-0726"]),
            round(row[f"{m} 1225"]), round(row[f"{m} 08-1225"]),
        ])
    rows_js.append([
        card, _txt(row["LN"]), _txt(row["Tipo Reaseguro"]), _txt(row["País"]),
        _txt(row["Corredor"]), _txt(row["Compañía_Nombre"]),
        _txt(row["Num Contrato"]), _txt(row["Binder Ppto"]),
        sem, _motivos(row) if sem == 2 else "", round(imp),
        medidas_arr[0], medidas_arr[1], medidas_arr[2],
    ])

DATA_JS = {
    "rows": rows_js,
    "charts": charts_cfg,
    "cfg": {
        "umbralAmarillo": UMBRAL_AMARILLO,
        "umbralRojo": UMBRAL_ROJO,
        "sinAmarillo": IND_SIN_AMARILLO,
        "sinRojo": IND_SIN_ROJO,
        "minDen": TOL,
        "materialidad": MATERIALIDAD,
    },
}

sec3_defs = [
    (0, "Contrato", "sec-contrato",
     "Contratos suscritos directamente (LN 4001, 4004 y 4005). Filtra y las gráficas, semáforos y tablas se actualizan.",
     "Contratos con alerta"),
    (1, "Cedente", "sec-cedente",
     "Negocio por cedente (LN 4002, 4003, 4004, 4008 y 4008-Agro).",
     "Cedentes con alerta"),
    (2, "MGA", "sec-mga",
     "Negocio por agencia / binder (LN 4006).",
     "Binders con alerta"),
]

sec3_bloques = []
for idx, nombre, sec_id, desc, t_alerta in sec3_defs:
    sec3_bloques.append(f"""
<section id="{sec_id}" class="cardinal">
  <div class="sec-head"><h2 class="sec-title">{nombre}</h2>
    <span class="sub">{desc}</span></div>
  <div class="card filtros" id="flt_{idx}"></div>
  <div class="grid kpis" id="kpi_{idx}"></div>
  <div class="grid dos">
    <div class="card">
      <div class="chart-head">
        <h2>FCST 2026 vs Ppto 2026 vs Real 2025</h2>
        <div class="toggle" id="tgl_{idx}">
          <button data-m="0" class="on">Primas</button>
          <button data-m="1">Siniestros</button>
          <button data-m="2">Costos</button>
        </div>
      </div>
      <div class="nota">Con los filtros aplicados, por línea de negocio (USD)</div>
      <div id="ch3_{idx}"></div>
    </div>
    <div class="card donut-wrap">
      <h2>Semáforo</h2>
      <div id="dn_{idx}"></div>
      <div class="dl" id="dl_{idx}"></div>
    </div>
  </div>
  <div class="card scroll">
    <h2>{t_alerta}</h2>
    <div class="nota">Entidades con contratos en rojo o amarillo, ordenadas por severidad e impacto.</div>
    <div id="al_{idx}"></div>
  </div>
  <div class="card scroll">
    <h2>Resumen por línea de negocio</h2>
    <div class="nota">Calculado sobre los registros filtrados. Índices sobre agregados.</div>
    <div id="rs_{idx}"></div>
  </div>
  <div class="card scroll">
    <h2>Top excepciones (semáforo rojo)</h2>
    <div class="nota">Con los filtros aplicados. Detalle completo en VAL_RFCST26.xlsx → Excepciones.</div>
    <div id="ex_{idx}"></div>
  </div>
</section>""")

# =====================================================
# PLANTILLA HTML DEL DASHBOARD
# =====================================================

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validación RFCST 2026</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { background: #0d0d0d; color: #ffffff;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 0 30px 40px; }
  header.top { position: sticky; top: 0; z-index: 20; background: rgba(13,13,13,.94);
    backdrop-filter: blur(4px); display: flex; align-items: center; gap: 14px;
    flex-wrap: wrap; padding: 16px 0 12px; border-bottom: 1px solid #2c2c2a;
    margin-bottom: 18px; }
  h1 { font-size: 20px; font-weight: 650; }
  .sub { color: #898781; font-size: 12.5px; }
  nav.secs { display: flex; gap: 4px; margin-left: auto; flex-wrap: wrap; }
  nav.secs a { color: #c3c2b7; text-decoration: none; font-size: 12.5px;
    padding: 5px 11px; border-radius: 999px; border: 1px solid transparent; }
  nav.secs a:hover { background: rgba(255,255,255,.06); }
  nav.secs a.on { background: rgba(57,135,229,.16); color: #9ec5f4;
    border-color: rgba(57,135,229,.3); }
  section.bloque { margin-top: 26px; }
  section.bloque, section.cardinal { scroll-margin-top: 74px; }
  .sec-head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
    margin-bottom: 12px; }
  .sec-title { font-size: 17px; font-weight: 650; }
  h3.med { font-size: 13px; font-weight: 650; color: #9ec5f4; letter-spacing: .06em;
    text-transform: uppercase; margin: 18px 0 10px; }
  .ast-mark { color: #fab219; }
  .ast { color: #898781; font-size: 12px; margin: 8px 2px 0; font-style: italic; }
  .grid { display: grid; gap: 14px; }
  .kpis { grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); }
  .card { background: #1a1a19; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px; padding: 16px 18px; }
  .kpi .t { color: #c3c2b7; font-size: 12px; margin-bottom: 8px; display: flex;
    align-items: center; gap: 7px; }
  .kpi .t i { width: 22px; height: 22px; border-radius: 6px; display: inline-flex;
    align-items: center; justify-content: center; font-style: normal; font-size: 12px;
    background: rgba(57,135,229,.16); }
  .kpi .v { font-size: 25px; font-weight: 650; letter-spacing: -0.02em; }
  .kpi .d { font-size: 12px; margin-top: 7px; color: #c3c2b7; }
  b.up, b.down, b.warn, b.neu { font-weight: 600; padding: 2px 7px;
    border-radius: 999px; font-size: 11.5px; }
  .up   { color: #7dd87d; background: rgba(12,163,12,.14); }
  .down { color: #f09a9a; background: rgba(208,59,59,.16); }
  .warn { color: #fab219; background: rgba(250,178,25,.13); }
  .neu  { color: #898781; background: rgba(137,135,129,.15); }
  .card h2 { font-size: 13.5px; font-weight: 600; color: #c3c2b7; margin-bottom: 4px; }
  .card .nota { font-size: 11.5px; color: #898781; margin-bottom: 10px; }
  .dos { grid-template-columns: 2.1fr 1fr; align-items: stretch; }
  .dos2 { grid-template-columns: 1fr 1fr; align-items: stretch; }
  @media (max-width: 950px) { .dos, .dos2 { grid-template-columns: 1fr; } }
  svg { width: 100%; height: auto; display: block; }
  .tick { fill: #898781; font-size: 10.5px; font-family: system-ui, sans-serif;
    font-variant-numeric: tabular-nums; }
  .cat { fill: #c3c2b7; font-size: 11px; font-family: system-ui, sans-serif; }
  .vlabel { fill: #c3c2b7; font-size: 10px; font-family: system-ui, sans-serif;
    font-variant-numeric: tabular-nums; }
  .donut-n { fill: #ffffff; font-size: 26px; font-weight: 650;
    font-family: system-ui, sans-serif; }
  .donut-l { fill: #898781; font-size: 10.5px; font-family: system-ui, sans-serif; }
  .bar { transition: opacity .12s; }
  svg:hover .bar { opacity: .45; }
  svg .bar:hover { opacity: 1; }
  .legend { display: flex; gap: 16px; flex-wrap: wrap; margin: 4px 0 10px; }
  .lg { color: #c3c2b7; font-size: 11.5px; display: inline-flex; align-items: center;
    gap: 6px; }
  .lg i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  .donut-wrap { display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .donut-wrap > div:first-of-type { width: 100%; max-width: 210px; }
  .dl { width: 100%; font-size: 12px; color: #c3c2b7; }
  .dl div { display: flex; justify-content: space-between; padding: 5px 2px;
    border-bottom: 1px solid #2c2c2a; }
  .dl div:last-child { border-bottom: none; }
  .dl i { width: 10px; height: 10px; border-radius: 3px; display: inline-block;
    margin-right: 7px; }
  .dl .n { font-variant-numeric: tabular-nums; color: #ffffff; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; color: #898781; font-weight: 500; font-size: 11px;
    padding: 7px 10px; border-bottom: 1px solid #383835; white-space: nowrap; }
  td { padding: 7.5px 10px; border-bottom: 1px solid #2c2c2a; white-space: nowrap; }
  tr:last-child td { border-bottom: none; }
  tbody tr:hover { background: rgba(255,255,255,.03); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  th.num { text-align: right; }
  .motivo { color: #c3c2b7; white-space: normal; max-width: 260px; }
  .chip { font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px; }
  .chip.rojo { color: #f09a9a; background: rgba(208,59,59,.16); }
  .chip.amarillo { color: #fab219; background: rgba(250,178,25,.13); }
  .chip.verde { color: #7dd87d; background: rgba(12,163,12,.14); }
  .chip.gris { color: #898781; background: rgba(137,135,129,.15); }
  .insight { background: linear-gradient(90deg, rgba(57,135,229,.10),
    rgba(57,135,229,.03)); border: 1px solid rgba(57,135,229,.25);
    border-radius: 12px; padding: 14px 18px; font-size: 13px; line-height: 1.55;
    color: #c3c2b7; margin-top: 16px; }
  .insight b { color: #ffffff; }
  .scroll { overflow-x: auto; margin-top: 14px; }
  .filtros { display: flex; gap: 12px; flex-wrap: wrap; padding: 13px 16px;
    margin-bottom: 14px; position: relative; z-index: 5; }
  .flt { display: flex; flex-direction: column; gap: 4px; min-width: 150px; flex: 1; }
  .flt label { font-size: 10.5px; color: #898781; letter-spacing: .04em;
    text-transform: uppercase; }
  .flt select { background: #0d0d0d; color: #ffffff; border: 1px solid #383835;
    border-radius: 8px; padding: 7px 9px; font-size: 12.5px; font-family: inherit;
    max-width: 300px; }
  .flt select:focus { outline: none; border-color: rgba(57,135,229,.6); }
  .flt-reset { align-self: flex-end; background: none; border: 1px solid #383835;
    color: #c3c2b7; border-radius: 8px; padding: 7px 12px; font-size: 12px;
    cursor: pointer; font-family: inherit; }
  .flt-reset:hover { border-color: rgba(57,135,229,.6); color: #ffffff; }
  .chart-head { display: flex; justify-content: space-between; align-items: center;
    gap: 10px; flex-wrap: wrap; }
  .toggle { display: inline-flex; background: #0d0d0d; border: 1px solid #383835;
    border-radius: 999px; padding: 2px; }
  .toggle button { background: none; border: none; color: #898781; font-size: 11.5px;
    padding: 5px 12px; border-radius: 999px; cursor: pointer; font-family: inherit; }
  .toggle button.on { background: rgba(57,135,229,.2); color: #9ec5f4; }
  .vacio { color: #898781; font-size: 12.5px; padding: 18px 4px; }
  footer { margin-top: 22px; color: #898781; font-size: 11px; line-height: 1.6; }
  .cardinal { border-top: 1px solid #2c2c2a; padding-top: 20px; margin-top: 30px; }
  .print-head { display: none; }
  .acciones { display: flex; justify-content: center; margin-top: 28px; }
  .btn-print { background: rgba(57,135,229,.16); color: #9ec5f4;
    border: 1px solid rgba(57,135,229,.35); border-radius: 10px; padding: 11px 20px;
    font-size: 13px; font-family: inherit; cursor: pointer; display: inline-flex;
    align-items: center; gap: 9px; }
  .btn-print:hover { background: rgba(57,135,229,.26); color: #ffffff; }

  /* Impresion: solo la seccion Linea de Negocio, en claro */
  @media print {
    @page { size: A4 landscape; margin: 10mm; }
    /* el lienzo hereda color-scheme: dark y pintaria los margenes en negro */
    :root { color-scheme: light !important; }
    html { background: #ffffff !important; }
    body.print-ln { background: #ffffff !important; color: #111111 !important;
      padding: 0 !important; }
    body.print-ln > *:not(#sec-ln) { display: none !important; }
    body.print-ln #sec-ln { display: block !important; margin: 0 !important; }
    body.print-ln .sec-head { display: none !important; }
    body.print-ln .print-head { display: block; margin-bottom: 12px; }
    body.print-ln .print-head h2 { font-size: 15px; font-weight: 650; color: #111111; }
    body.print-ln .print-head span { font-size: 10.5px; color: #555555; }
    body.print-ln .card { background: #ffffff !important; border: 1px solid #cccccc !important;
      break-inside: avoid; page-break-inside: avoid; }
    body.print-ln h3.med { color: #1a5eb0 !important; break-after: avoid;
      page-break-after: avoid; margin-top: 12px; }
    body.print-ln .card h2 { color: #111111 !important; }
    body.print-ln .card .nota, body.print-ln .lg, body.print-ln .ast { color: #444444 !important; }
    body.print-ln .tick { fill: #555555 !important; }
    body.print-ln .cat, body.print-ln .vlabel { fill: #222222 !important; }
    body.print-ln .dos2 { grid-template-columns: 1fr 1fr !important; }
    * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  }
</style>
</head>
<body>

<header class="top">
  <h1>Validación RFCST 2026 · 7+5</h1>
  <span class="sub">Corte Julio 2026 · __ARCHIVO__ · generado __GENERADO__</span>
  <nav class="secs">
    <a href="#sec-general">General</a>
    <a href="#sec-ln">Línea de Negocio</a>
    <a href="#sec-contrato">Contrato</a>
    <a href="#sec-cedente">Cedente</a>
    <a href="#sec-mga">MGA</a>
  </nav>
</header>

<section id="sec-general" class="bloque">
  <div class="sec-head"><h2 class="sec-title">General</h2>
    <span class="sub">Totalidad de las líneas de negocio · cifras en dólares ·
      presupuesto de __FUENTE_PPTO__</span></div>
__SEC1__
__SEC1PSC__
  <div class="insight">&#128161; __INSIGHT__</div>
</section>

<section id="sec-ln" class="bloque">
  <div class="print-head">
    <h2>Validación RFCST 2026 · 7+5 — Línea de Negocio</h2>
    <span>Corte Julio 2026 · __ARCHIVO__ · generado __GENERADO__ · cifras en dólares</span>
  </div>
  <div class="sec-head"><h2 class="sec-title">Línea de Negocio</h2>
    <span class="sub">Mismas vistas, por LN · cifras en dólares</span></div>
__SEC2__
</section>

__SEC3__

<div class="acciones">
  <button type="button" class="btn-print" id="btn-print-ln">
    &#128424; Imprimir sección Línea de Negocio en PDF
  </button>
</div>

<footer>Validación automática VAL_RFCST26.py · Planeación Financiera · cifras en dólares ·
V1: consistencia acumulada y cuadre Ago-Dic · V2: incremento vs ppto ajustado ·
V3: coherencia vs 2025 · V4: índices vs factores · V5: vs ppto anual · V6: calidad de datos ·
* P-S-C = Primas − Siniestros − Costos: falta el incremento a la reserva y los costos de cobertura.</footer>

<script>
const DATA = __DATA__;
const S = ['#3987e5', '#d95926', '#199e70'];
const SEMC = ['#0ca30c', '#fab219', '#d03b3b'];
const SEMN = ['Verde — sin alertas', 'Amarillo — revisar', 'Rojo — inconsistencia'];
const MEDN = ['Primas', 'Siniestros', 'Costos'];

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtM(v, dec) {
  if (v === null || v === undefined || !isFinite(v)) return 's/d';
  const a = Math.abs(v);
  if (a >= 1e6 || a === 0)
    return (v / 1e6).toLocaleString('en-US',
      {minimumFractionDigits: dec === undefined ? (a >= 1e8 || a === 0 ? 1 : 2) : dec,
       maximumFractionDigits: dec === undefined ? (a >= 1e8 || a === 0 ? 1 : 2) : dec}) + ' M';
  if (a >= 1e3) return (v / 1e3).toLocaleString('en-US', {maximumFractionDigits: 1}) + ' k';
  return v.toLocaleString('en-US', {maximumFractionDigits: 0});
}

function fmtPct(v, signo) {
  if (v === null || v === undefined || !isFinite(v)) return 's/d';
  if (v > 9.99) return '>999%';
  if (v < -9.99) return '<-999%';
  return (signo && v > 0 ? '+' : '') + (v * 100).toLocaleString('en-US',
    {minimumFractionDigits: 1, maximumFractionDigits: 1}) + '%';
}

function badge(v, buenoArriba, texto) {
  if (v === null || !isFinite(v)) return '<b class="neu">s/d</b> ' + texto;
  const cls = ((v >= 0) === buenoArriba) ? 'up' : 'down';
  return '<b class="' + cls + '">' + fmtPct(v, true) + '</b> ' + texto;
}

function niceStep(x) {
  if (x <= 0 || !isFinite(x)) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(x)));
  for (const m of [1, 2, 2.5, 5, 10]) if (x <= m * mag) return m * mag;
  return 10 * mag;
}

function ticksFor(vmin, vmax) {
  const step = niceStep((vmax - vmin) / 4 || 1);
  const t0 = Math.floor(vmin / step) * step;
  const ticks = [];
  for (let t = t0; t < vmax + step * 0.999; t += step) ticks.push(t);
  return ticks;
}

function barPath(x, y0, w, v, yV) {
  const r = Math.min(4, w / 2, Math.abs(yV - y0));
  if (Math.abs(yV - y0) < 0.5) return '';
  const x2 = x + w;
  if (v >= 0) {
    const y = yV;
    return 'M ' + x + ' ' + y0 + ' L ' + x + ' ' + (y + r) +
      ' Q ' + x + ' ' + y + ' ' + (x + r) + ' ' + y +
      ' L ' + (x2 - r) + ' ' + y + ' Q ' + x2 + ' ' + y + ' ' + x2 + ' ' + (y + r) +
      ' L ' + x2 + ' ' + y0 + ' Z';
  }
  const y = yV;
  return 'M ' + x + ' ' + y0 + ' L ' + x + ' ' + (y - r) +
    ' Q ' + x + ' ' + y + ' ' + (x + r) + ' ' + y +
    ' L ' + (x2 - r) + ' ' + y + ' Q ' + x2 + ' ' + y + ' ' + x2 + ' ' + (y - r) +
    ' L ' + x2 + ' ' + y0 + ' Z';
}

function groupedBars(elId, cats, series, fmt) {
  const el = document.getElementById(elId);
  if (!el) return;
  const vals = [];
  series.forEach(s => s.v.forEach(v => { if (v !== null && isFinite(v)) vals.push(v); }));
  if (!vals.length || !cats.length) {
    el.innerHTML = '<div class="vacio">Sin datos con los filtros aplicados.</div>';
    return;
  }
  const W = 980, H = 320, mL = 62, mR = 12, mT = 14, mB = 46;
  const pw = W - mL - mR, ph = H - mT - mB;
  let vmin = Math.min(0, ...vals), vmax = Math.max(0, ...vals);
  if (vmin === vmax) vmax = vmin + 1;
  const ticks = ticksFor(vmin, vmax);
  const tmin = ticks[0], tmax = ticks[ticks.length - 1];
  const y = v => mT + ph - ((v - tmin) / (tmax - tmin)) * ph;
  const y0 = y(0);
  const fmtTick = fmt === 'pct'
    ? v => Math.round(v * 100) + '%'
    : v => fmtM(v, Math.abs(tmax - tmin) < 4e6 ? 1 : 0);
  const fmtVal = fmt === 'pct' ? v => fmtPct(v) : v => fmtM(v);
  const nc = cats.length, ns = series.length;
  const gw = pw / nc, gap = 2;
  const bw = Math.min(34, (gw * 0.72 - gap * (ns - 1)) / ns);
  const tw = bw * ns + gap * (ns - 1);
  let out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">';
  ticks.forEach(t => {
    out += '<line x1="' + mL + '" y1="' + y(t) + '" x2="' + (W - mR) + '" y2="' + y(t) +
      '" stroke="#2c2c2a" stroke-width="1"/>' +
      '<text x="' + (mL - 8) + '" y="' + (y(t) + 3.5) + '" text-anchor="end" class="tick">' +
      fmtTick(t) + '</text>';
  });
  cats.forEach((cat, i) => {
    const gx = mL + i * gw + (gw - tw) / 2;
    out += '<text x="' + (mL + i * gw + gw / 2) + '" y="' + (H - mB + 18) +
      '" text-anchor="middle" class="cat">' + esc(cat) + '</text>';
    series.forEach((s, k) => {
      const v = s.v[i];
      if (v === null || v === undefined || !isFinite(v)) return;
      const x = gx + k * (bw + gap);
      const p = barPath(x, y0, bw, v, y(v));
      if (p) out += '<path d="' + p + '" fill="' + s.c + '" class="bar"><title>' +
        esc(cat) + ' · ' + esc(s.n) + ': ' + fmtVal(v) + '</title></path>';
      if (k === 0 && gw >= 56 && Math.abs(y(v) - y0) / ph > 0.045)
        out += '<text x="' + (x + bw / 2) + '" y="' + (v >= 0 ? y(v) - 5 : y(v) + 12) +
          '" text-anchor="middle" class="vlabel">' + fmtVal(v) + '</text>';
    });
  });
  out += '<line x1="' + mL + '" y1="' + y0 + '" x2="' + (W - mR) + '" y2="' + y0 +
    '" stroke="#383835" stroke-width="1"/></svg>';
  const leyenda = '<div class="legend">' + series.map(s =>
    '<span class="lg"><i style="background:' + s.c + '"></i>' + esc(s.n) + '</span>'
  ).join('') + '</div>';
  el.innerHTML = leyenda + out;
}

function donut(elId, listId, counts) {
  const el = document.getElementById(elId), dl = document.getElementById(listId);
  const total = counts.reduce((a, b) => a + b, 0);
  const W = 230, cx = W / 2, cy = W / 2, r = W / 2 - 12, gr = 30, rm = r - gr / 2;
  let out = '<svg viewBox="0 0 ' + W + ' ' + W + '" role="img">';
  let ang = -90;
  counts.forEach((v, i) => {
    if (!v) return;
    const bar = v / total * 360;
    const gapD = Math.min(2.5, bar * 0.15);
    const a0 = (ang + gapD / 2) * Math.PI / 180, a1 = (ang + bar - gapD / 2) * Math.PI / 180;
    const x0 = cx + rm * Math.cos(a0), y0 = cy + rm * Math.sin(a0);
    const x1 = cx + rm * Math.cos(a1), y1 = cy + rm * Math.sin(a1);
    out += '<path d="M ' + x0 + ' ' + y0 + ' A ' + rm + ' ' + rm + ' 0 ' +
      ((a1 - a0) > Math.PI ? 1 : 0) + ' 1 ' + x1 + ' ' + y1 +
      '" fill="none" stroke="' + SEMC[i] + '" stroke-width="' + gr +
      '" class="bar"><title>' + SEMN[i] + ': ' + v.toLocaleString('en-US') + '</title></path>';
    ang += bar;
  });
  out += '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" class="donut-n">' +
    total.toLocaleString('en-US') + '</text>' +
    '<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" class="donut-l">registros</text></svg>';
  el.innerHTML = out;
  dl.innerHTML = counts.map((v, i) =>
    '<div><span><i style="background:' + SEMC[i] + '"></i>' + SEMN[i] +
    '</span><span class="n">' + v.toLocaleString('en-US') + '</span></div>').join('');
}

function chip(txt, cls) { return '<span class="chip ' + cls + '">' + txt + '</span>'; }

function chipDesv(v) {
  if (v === null || !isFinite(v)) return chip('– SIN DATO', 'gris');
  const a = Math.abs(v);
  if (a > DATA.cfg.umbralRojo) return chip('&#9650; ROJO', 'rojo');
  if (a > DATA.cfg.umbralAmarillo) return chip('&#9679; AMARILLO', 'amarillo');
  return chip('&#10003; VERDE', 'verde');
}

// ------- Seccion 2: graficas estaticas -------
DATA.charts.forEach(c => groupedBars(c.el, c.cats, c.series, c.fmt));

// ------- Seccion 3: filtros interactivos -------
const FDEF = {
  0: [[1, 'LN'], [2, 'Tipo Reaseguro'], [3, 'País'], [4, 'Corredor'],
      [5, 'Compañía'], [6, 'Contrato']],
  1: [[1, 'LN'], [2, 'Tipo Reaseguro'], [3, 'País'], [5, 'Cedente']],
  2: [[1, 'LN'], [2, 'Tipo Reaseguro'], [3, 'País'], [5, 'Compañía (MGA)'], [7, 'Binder']],
};
const state = {0: {m: 0, f: {}}, 1: {m: 0, f: {}}, 2: {m: 0, f: {}}};

function rowsFor(card, skip) {
  return DATA.rows.filter(r => {
    if (r[0] !== card) return false;
    for (const k in state[card].f) {
      if (+k === skip) continue;
      const v = state[card].f[k];
      if (v !== null && v !== undefined && String(r[k]) !== v) return false;
    }
    return true;
  });
}

function buildFilters(card) {
  const cont = document.getElementById('flt_' + card);
  let html = '';
  FDEF[card].forEach(([k, label]) => {
    const opts = [...new Set(rowsFor(card, k).map(r => String(r[k])).filter(v => v !== ''))]
      .sort((a, b) => a.localeCompare(b, 'es', {numeric: true}));
    const cur = state[card].f[k] || '';
    html += '<div class="flt"><label>' + label + '</label>' +
      '<select data-k="' + k + '"><option value="">(Todos)</option>' +
      opts.map(o => '<option value="' + esc(o) + '"' + (o === cur ? ' selected' : '') + '>' +
        esc(o) + '</option>').join('') + '</select></div>';
  });
  html += '<button class="flt-reset" type="button">Limpiar filtros</button>';
  cont.innerHTML = html;
  cont.querySelectorAll('select').forEach(sel => {
    sel.addEventListener('change', () => {
      const k = +sel.dataset.k;
      if (sel.value === '') delete state[card].f[k];
      else state[card].f[k] = sel.value;
      renderCard(card);
    });
  });
  cont.querySelector('.flt-reset').addEventListener('click', () => {
    state[card].f = {};
    renderCard(card);
  });
}

function sums(rows, mi) {
  const o = {a0726: 0, fcst: 0, inc: 0, ppto: 0, p0812: 0, p0107: 0, r25: 0, r0812: 0};
  const kk = ['a0726', 'fcst', 'inc', 'ppto', 'p0812', 'p0107', 'r25', 'r0812'];
  rows.forEach(r => { const a = r[11 + mi]; kk.forEach((k, i) => o[k] += a[i]); });
  return o;
}

function ratio(a, b) { return Math.abs(b) > DATA.cfg.minDen ? a / b : null; }

function entKey(card, r) {
  if (card === 0) return r[5] + (r[6] !== '' ? ' · #' + r[6] : '');
  if (card === 1) return r[5];
  return r[7] !== '' ? r[7] : r[5];
}

function renderCard(card) {
  buildFilters(card);
  const rows = rowsFor(card, null);

  // KPIs
  const p = sums(rows, 0), s = sums(rows, 1);
  const varPpto = ratio(p.fcst, p.ppto), crec = ratio(p.fcst, p.r25);
  const desvInc = ratio(p.inc, p.p0812);
  const nR = rows.filter(r => r[8] === 2).length;
  const nA = rows.filter(r => r[8] === 1).length;
  document.getElementById('kpi_' + card).innerHTML =
    '<div class="card kpi"><div class="t"><i>&#128181;</i>Prima Forecast 2026</div>' +
    '<div class="v">' + fmtM(p.fcst) + '</div><div class="d">' +
    badge(varPpto === null ? null : varPpto - 1, true, 'vs Ppto (' + fmtM(p.ppto) + ')') + '</div>' +
    '<div class="d">Real a Jul 26: ' + fmtM(p.a0726) + '</div></div>' +
    '<div class="card kpi"><div class="t"><i>&#128200;</i>Crecimiento vs Real 2025</div>' +
    '<div class="v">' + fmtPct(crec === null ? null : crec - 1, true) + '</div>' +
    '<div class="d">FCST (' + fmtM(p.fcst) + ') vs Real 2025 (' + fmtM(p.r25) + ')</div></div>' +
    '<div class="card kpi"><div class="t"><i>&#9202;</i>Incremento Ago-Dic</div>' +
    '<div class="v">' + fmtM(p.inc) + '</div><div class="d">' +
    badge(desvInc === null ? null : desvInc - 1, true,
      'vs Ppto Ago-Dic (' + fmtM(p.p0812) + ')') + '</div></div>' +
    '<div class="card kpi"><div class="t"><i>&#9888;</i>Registros con alerta</div>' +
    '<div class="v">' + (nR + nA).toLocaleString('en-US') + '</div>' +
    '<div class="d"><b class="down">' + nR.toLocaleString('en-US') + ' rojos</b> · ' +
    nA.toLocaleString('en-US') + ' amarillos · de ' + rows.length.toLocaleString('en-US') +
    ' registros</div></div>';

  // Grafica FCST vs Ppto vs Real por LN
  const mi = state[card].m;
  const lns = [...new Set(rows.map(r => r[1]))].sort((a, b) =>
    a.localeCompare(b, 'es', {numeric: true}));
  const serFcst = [], serPpto = [], serR25 = [];
  lns.forEach(ln => {
    const sub = rows.filter(r => r[1] === ln);
    const o = sums(sub, mi);
    serFcst.push(o.fcst); serPpto.push(o.ppto); serR25.push(o.r25);
  });
  groupedBars('ch3_' + card, lns, [
    {n: MEDN[mi] + ' FCST 2026', c: S[0], v: serFcst},
    {n: 'Ppto 2026', c: S[1], v: serPpto},
    {n: 'Real 2025', c: S[2], v: serR25},
  ], 'm');

  // Donut
  donut('dn_' + card, 'dl_' + card,
    [rows.filter(r => r[8] === 0).length, nA, nR]);

  // Entidades con alerta
  const ents = {};
  rows.forEach(r => {
    const k = entKey(card, r);
    if (!ents[k]) ents[k] = {n: 0, rojo: 0, ama: 0, fcst: 0, paises: new Set(), ln: new Set()};
    const e = ents[k];
    e.n++; e.fcst += r[11][1]; if (r[3] !== '') e.paises.add(r[3]); e.ln.add(r[1]);
    if (r[8] === 2) e.rojo++; else if (r[8] === 1) e.ama++;
  });
  const conAlerta = Object.entries(ents).filter(([, e]) => e.rojo + e.ama > 0)
    .sort((a, b) => (b[1].rojo - a[1].rojo) || (b[1].ama - a[1].ama) ||
      (Math.abs(b[1].fcst) - Math.abs(a[1].fcst)))
    .slice(0, 12);
  document.getElementById('al_' + card).innerHTML = conAlerta.length ?
    '<table><thead><tr><th>Entidad</th><th>LN</th><th>País</th>' +
    '<th class="num">Registros</th><th class="num">Prima FCST</th>' +
    '<th class="num">Rojos</th><th class="num">Amarillos</th></tr></thead><tbody>' +
    conAlerta.map(([k, e]) => '<tr><td>' + esc(k) + '</td><td>' +
      esc([...e.ln].join(', ')) + '</td><td>' + esc(e.paises.size > 1 ? 'Varios' : ([...e.paises][0] || '')) + '</td>' +
      '<td class="num">' + e.n + '</td><td class="num">' + fmtM(e.fcst) + '</td>' +
      '<td class="num">' + (e.rojo ? chip(e.rojo, 'rojo') : '–') + '</td>' +
      '<td class="num">' + (e.ama ? chip(e.ama, 'amarillo') : '–') + '</td></tr>').join('') +
    '</tbody></table>' :
    '<div class="vacio">Sin alertas con los filtros aplicados.</div>';

  // Resumen por LN
  document.getElementById('rs_' + card).innerHTML = lns.length ?
    '<table><thead><tr><th>LN</th><th class="num">Registros</th>' +
    '<th class="num">Prima FCST</th><th class="num">vs Ppto</th>' +
    '<th class="num">vs Real 25</th><th class="num">Desv. inc. Ago-Dic</th><th>Semáforo</th>' +
    '<th class="num">% Sin FCST</th><th class="num">%P-S-C</th><th class="num">Alertas</th></tr></thead><tbody>' +
    lns.map(ln => {
      const sub = rows.filter(r => r[1] === ln);
      const o = sums(sub, 0), so = sums(sub, 1), co = sums(sub, 2);
      const vp = ratio(o.fcst, o.ppto), cr = o.r25 && Math.abs(o.r25) > DATA.cfg.materialidad
        ? o.fcst / o.r25 - 1 : null;
      const di = ratio(o.inc, o.p0812);
      const al = sub.filter(r => r[8] > 0).length;
      return '<tr><td>LN ' + esc(ln) + '</td><td class="num">' + sub.length + '</td>' +
        '<td class="num">' + fmtM(o.fcst) + '</td>' +
        '<td class="num">' + fmtPct(vp === null ? null : vp - 1, true) + '</td>' +
        '<td class="num">' + fmtPct(cr, true) + '</td>' +
        '<td class="num">' + fmtPct(di === null ? null : di - 1, true) + '</td>' +
        '<td>' + chipDesv(di === null ? null : di - 1) + '</td>' +
        '<td class="num">' + fmtPct(ratio(so.fcst, o.fcst)) + '</td>' +
        '<td class="num">' + fmtPct(ratio(o.fcst - so.fcst - co.fcst, o.fcst)) + '</td>' +
        '<td class="num">' + al + ' / ' + sub.length + '</td></tr>';
    }).join('') + '</tbody></table>' :
    '<div class="vacio">Sin datos con los filtros aplicados.</div>';

  // Top excepciones
  const exc = rows.filter(r => r[8] === 2).sort((a, b) => b[10] - a[10]).slice(0, 10);
  document.getElementById('ex_' + card).innerHTML = exc.length ?
    '<table><thead><tr><th>LN</th><th>Entidad</th><th>País</th><th>Tipo</th>' +
    '<th class="num">Real Jul 26</th><th class="num">FCST Dic 26</th>' +
    '<th class="num">Inc. Ago-Dic</th><th>Motivo</th></tr></thead><tbody>' +
    exc.map(r => '<tr><td>LN ' + esc(r[1]) + '</td><td>' + esc(entKey(card, r)) + '</td>' +
      '<td>' + esc(r[3]) + '</td><td>' + esc(r[2]) + '</td>' +
      '<td class="num">' + fmtM(r[11][0]) + '</td><td class="num">' + fmtM(r[11][1]) + '</td>' +
      '<td class="num">' + fmtM(r[11][2]) + '</td>' +
      '<td class="motivo">' + esc(r[9] || 'Revisión') + '</td></tr>').join('') +
    '</tbody></table>' :
    '<div class="vacio">Sin excepciones rojas con los filtros aplicados.</div>';
}

[0, 1, 2].forEach(card => {
  document.querySelectorAll('#tgl_' + card + ' button').forEach(btn => {
    btn.addEventListener('click', () => {
      state[card].m = +btn.dataset.m;
      document.querySelectorAll('#tgl_' + card + ' button')
        .forEach(b => b.classList.toggle('on', b === btn));
      renderCard(card);
    });
  });
  renderCard(card);
});

// Imprimir solo la seccion Linea de Negocio
const btnPrint = document.getElementById('btn-print-ln');
function finPrint() { document.body.classList.remove('print-ln'); }
btnPrint.addEventListener('click', () => {
  document.body.classList.add('print-ln');
  window.addEventListener('afterprint', finPrint, {once: true});
  window.print();
  // Respaldo por si el navegador no dispara afterprint
  setTimeout(finPrint, 1500);
});

// Resalta la seccion activa en la navegacion
const secciones = ['sec-general', 'sec-ln', 'sec-contrato', 'sec-cedente', 'sec-mga'];
const links = document.querySelectorAll('nav.secs a');
const obs = new IntersectionObserver(es => {
  es.forEach(e => {
    if (e.isIntersecting) links.forEach(l =>
      l.classList.toggle('on', l.getAttribute('href') === '#' + e.target.id));
  });
}, {rootMargin: '-20% 0px -70% 0px'});
secciones.forEach(id => { const el = document.getElementById(id); if (el) obs.observe(el); });
</script>

</body>
</html>"""

# =====================================================
# EXPORT DASHBOARD HTML
# =====================================================

salida_html = os.path.join(xOutputs, "Dashboard_RFCST26.html")

html = (
    PLANTILLA
    .replace("__ARCHIVO__", os.path.basename(archivo))
    .replace("__FUENTE_PPTO__", FUENTE_PPTO)
    .replace("__GENERADO__", datetime.now().strftime("%d/%m/%Y %H:%M"))
    .replace("__SEC1PSC__", sec1_psc)
    .replace("__SEC1__", "".join(sec1_bloques))
    .replace("__SEC2__", "".join(sec2_bloques))
    .replace("__SEC3__", "".join(sec3_bloques))
    .replace("__INSIGHT__", insight)
    .replace("__DATA__", json.dumps(DATA_JS, separators=(",", ":"), ensure_ascii=False))
)

with open(salida_html, "w", encoding="utf-8") as fh:
    fh.write(html)

print(f"Dashboard generado: {salida_html}")

print(f"Listo en {time.perf_counter() - inicio:.1f} s")
