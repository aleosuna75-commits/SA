# =====================================================
# VAL_RFCST26 - VALIDACION DEL REFORECAST 2026 (7+5)
# =====================================================
# Valida las cifras del RFCST que comparte Suscripcion
# (pestana BD_RFCST26) contra:
#
#   V1. Real acumulado a Julio 2026      (cols Q:S)
#   V2. Ppto Ago-Dic 2026 ajustado por
#       nivel de ejecucion Ene-Jul       (cols AC:AI)
#   V3. Reales 2025 (cierre y Ago-Dic)   (cols AK:AQ)
#   V4. Factores historicos y de Ppto    (cols AS:AY)
#   V5. Ppto 2026 ano completo           (cols Y:AA)
#   V6. Calidad de datos
#
# Output:
#   - Outputs/VAL_RFCST26.xlsx        (detalle + resumen)
#   - Outputs/Dashboard_RFCST26.html  (dashboard visual)
# =====================================================

import os
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

archivo = os.path.join(xInputs, "BD_RFCST_26_act.xlsx")

if not os.path.exists(archivo):
    candidatos = [
        os.path.join(carpeta, f)
        for carpeta in (xInputs, xFolder)
        if os.path.isdir(carpeta)
        for f in os.listdir(carpeta)
        if f.startswith("BD_RFCST") and f.endswith(".xlsx")
    ]
    if not candidatos:
        raise FileNotFoundError(
            f"No se encontro BD_RFCST*.xlsx en {xInputs} ni en {xFolder}"
        )
    archivo = candidatos[0]

HOJA = "BD_RFCST26"
FILA_ENCABEZADO = 4          # los encabezados estan en la fila 5 del Excel
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
PESO_INC = 0.30              # desviacion incremento Ago-Dic vs esperado
PESO_SIN = 0.30              # siniestralidad forecast
PESO_COS = 0.15              # costos forecast
PESO_V25 = 0.25              # desviacion crecimiento vs factor Ppto

# =====================================================
# CARGA
# =====================================================

print(f"Leyendo {archivo} ...")

df = pd.read_excel(archivo, sheet_name=HOJA, header=FILA_ENCABEZADO)

df = df[df["LN "].notna()].copy()
df = df.rename(columns={"LN ": "LN", "Compañía.1": "Num Compañía"})
df["LN"] = df["LN"].astype(str).str.strip()

# =====================================================
# LIMPIEZA
# =====================================================

columnas_numericas = [
    "Primas 0726", "Siniestros 0726", "Costos 0726",
    "Primas 1226", "Siniestros 1226", "Costos 1226",
    "Primas PPTO1226", "Siniestros PPTO1226", "Costos PPTO1226",
    "Primas PPTO08-1226", "Siniestros PPTO08-1226", "Costos PPTO08-1226",
    "Primas PPTO01-0726", "Siniestros PPTO01-0726", "Costos PPTO01-0726",
    "Primas 1225", "Siniestros 1225", "Costos 1225",
    "Primas 08-1225", "Siniestros 08-1225", "Costos 08-1225",
    "Incr. Primas Hist", "Ind. Sin. Hist", "Ind. Cos. Hist",
    "Incr. Primas Ppto", "Ind. Sin. Ppto", "Ind. Cos. Ppto",
]

for col in columnas_numericas:
    df[col] = pd.to_numeric(df[col], errors="coerce")

columnas_dim = [
    "Fuente/Hoja", "LN", "Tipo Reaseguro", "Compañía", "País",
    "Tipo Rea", "Corredor", "Num Compañía", "Num Contrato", "Año Susc.",
]

df = df[columnas_dim + columnas_numericas].copy()

# Las medidas monetarias se comparan con NaN tratado como 0
medidas = [c for c in columnas_numericas if not c.startswith(("Incr", "Ind"))]
df[medidas] = df[medidas].fillna(0)


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
# ser menor a lo ya registrado al corte de julio.

df["Inc_Primas_AgoDic"] = df["Primas 1226"] - df["Primas 0726"]
df["Inc_Siniestros_AgoDic"] = df["Siniestros 1226"] - df["Siniestros 0726"]
df["Inc_Costos_AgoDic"] = df["Costos 1226"] - df["Costos 0726"]

df["F_V1_Primas"] = df["Inc_Primas_AgoDic"] < -TOL
df["F_V1_Siniestros"] = df["Inc_Siniestros_AgoDic"] < -TOL
df["F_V1_Costos"] = df["Inc_Costos_AgoDic"] < -TOL

# =====================================================
# V2. INCREMENTO AGO-DIC vs PPTO AGO-DIC AJUSTADO
# =====================================================
# Si al corte de julio llevamos X% del ppto Ene-Jul, el
# incremento esperado Ago-Dic es el ppto Ago-Dic escalado
# por ese mismo nivel de ejecucion.

df["Ratio_Ejecucion"] = _ratio(df["Primas 0726"], df["Primas PPTO01-0726"])

df["Inc_Esperado_AgoDic"] = df["Primas PPTO08-1226"] * df["Ratio_Ejecucion"]

df["Desv_Inc_AgoDic"] = _ratio(
    df["Inc_Primas_AgoDic"], df["Inc_Esperado_AgoDic"]
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
# RESUMEN POR LN
# =====================================================


def resumen_por(claves):

    r = (
        df.groupby(claves)
        .agg(
            Contratos=("LN", "size"),
            Primas_0726=("Primas 0726", "sum"),
            Siniestros_0726=("Siniestros 0726", "sum"),
            Costos_0726=("Costos 0726", "sum"),
            Primas_1226=("Primas 1226", "sum"),
            Siniestros_1226=("Siniestros 1226", "sum"),
            Costos_1226=("Costos 1226", "sum"),
            Primas_PPTO1226=("Primas PPTO1226", "sum"),
            Primas_PPTO_0812=("Primas PPTO08-1226", "sum"),
            Primas_PPTO_0107=("Primas PPTO01-0726", "sum"),
            Primas_1225=("Primas 1225", "sum"),
            Primas_0812_25=("Primas 08-1225", "sum"),
            Siniestros_1225=("Siniestros 1225", "sum"),
            Costos_1225=("Costos 1225", "sum"),
            Contratos_Alerta=("Tiene_Alerta", "sum"),
            Flags_V1=("F_V1_Primas", "sum"),
        )
        .reset_index()
    )

    # Indices y desviaciones recalculados sobre agregados
    # (no promedio de razones)
    r["Inc_AgoDic"] = r["Primas_1226"] - r["Primas_0726"]
    r["Ratio_Ejecucion"] = _ratio(r["Primas_0726"], r["Primas_PPTO_0107"])
    r["Inc_Esperado"] = r["Primas_PPTO_0812"] * r["Ratio_Ejecucion"]
    r["Desv_Inc_AgoDic"] = _ratio(r["Inc_AgoDic"], r["Inc_Esperado"]) - 1

    r["Cumplimiento_PPTO"] = _ratio(r["Primas_1226"], r["Primas_PPTO1226"])
    r["Var_Primas_PPTO"] = r["Cumplimiento_PPTO"] - 1
    r["Gap_Primas"] = r["Primas_1226"] - r["Primas_PPTO1226"]

    r["Crec_vs_Real25"] = _ratio(r["Primas_1226"], r["Primas_1225"],
                                 min_den=MATERIALIDAD) - 1
    r["Crec_AgoDic_vs_25"] = _ratio(r["Inc_AgoDic"], r["Primas_0812_25"],
                                    min_den=MATERIALIDAD) - 1

    r["Ind_Sin_FCST"] = _ratio(r["Siniestros_1226"], r["Primas_1226"])
    r["Ind_Cos_FCST"] = _ratio(r["Costos_1226"], r["Primas_1226"])
    r["Ind_Sin_Real25"] = _ratio(r["Siniestros_1225"], r["Primas_1225"])
    r["Ind_Cos_Real25"] = _ratio(r["Costos_1225"], r["Primas_1225"])

    r["Pct_Alerta"] = r["Contratos_Alerta"] / r["Contratos"]

    return r


resumen = resumen_por(["LN"])
resumen_tiporea = resumen_por(["LN", "Tipo Reaseguro"])
resumen_fuente = resumen_por(["Fuente/Hoja"])
resumen_pais = resumen_por(["País"]).sort_values("Primas_1226", ascending=False)

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


for tabla in (resumen, resumen_tiporea, resumen_fuente, resumen_pais):
    tabla["Semaforo_Inc"] = tabla["Desv_Inc_AgoDic"].apply(semaforo_desviacion)
    tabla["Semaforo_Sin"] = tabla["Ind_Sin_FCST"].apply(semaforo_sin)
    tabla["Semaforo_Costos"] = tabla["Ind_Cos_FCST"].apply(semaforo_costos)
    tabla["Semaforo_vs_25"] = tabla["Crec_AgoDic_vs_25"].apply(semaforo_desviacion)

df["Semaforo_Inc"] = df["Desv_Inc_AgoDic"].apply(semaforo_desviacion)
df["Semaforo_Sin"] = df["Ind_Sin_FCST"].apply(semaforo_sin)
df["Semaforo_Costos"] = df["Ind_Cos_FCST"].apply(semaforo_costos)

# Semaforo global por contrato:
#   ROJO     inconsistencia dura en contrato material
#   AMARILLO contrato material con alertas suaves
#   VERDE    limpio o por debajo de materialidad
inconsistencia_dura = (
    df["F_V1_Primas"]
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
# DASHBOARD (KPIs)
# =====================================================

total_fcst = df["Primas 1226"].sum()
total_ppto = df["Primas PPTO1226"].sum()
total_real25 = df["Primas 1225"].sum()
total_0726 = df["Primas 0726"].sum()
inc_agodic = total_fcst - total_0726
esperado_agodic = (
    df["Primas PPTO08-1226"].sum()
    * (total_0726 / df["Primas PPTO01-0726"].sum())
)
real_agodic_25 = df["Primas 08-1225"].sum()

sem_counts = df["Semaforo_Global"].value_counts()

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
        "Incremento implicito Ago-Dic",
        "Incremento esperado Ago-Dic (ppto ajustado)",
        "Desviacion incremento Ago-Dic",
        "Real Ago-Dic 2025 (referencia)",
        "Siniestralidad FCST",
        "Costos FCST",
        "Contratos VERDE",
        "Contratos AMARILLO",
        "Contratos ROJO",
        "Contratos FCST < Real Jul (V1)",
        "LN en riesgo ALTO/CRITICO",
    ],

    "Valor": [
        len(df),
        df["LN"].nunique(),
        total_fcst,
        total_0726,
        total_ppto,
        total_real25,
        total_fcst / total_ppto,
        total_fcst / total_real25 - 1,
        inc_agodic,
        esperado_agodic,
        inc_agodic / esperado_agodic - 1,
        real_agodic_25,
        df["Siniestros 1226"].sum() / total_fcst,
        df["Costos 1226"].sum() / total_fcst,
        int(sem_counts.get("VERDE", 0)),
        int(sem_counts.get("AMARILLO", 0)),
        int(sem_counts.get("ROJO", 0)),
        int(df["F_V1_Primas"].sum()),
        int((resumen["Nivel_Riesgo"].isin(["ALTO", "CRITICO"])).sum()),
    ],

})

# =====================================================
# PARAMETROS (documentacion de supuestos)
# =====================================================

parametros = pd.DataFrame({
    "Parametro": [
        "Archivo fuente", "Hoja", "Fecha de corte", "Tolerancia (USD)",
        "Materialidad (USD)",
        "Umbral amarillo desviaciones", "Umbral rojo desviaciones",
        "Siniestralidad amarilla", "Siniestralidad roja",
        "Costos amarillo", "Costos rojo",
        "Peso score: incremento Ago-Dic", "Peso score: siniestralidad",
        "Peso score: costos", "Peso score: vs Real 2025",
        "Generado por", "Fecha de ejecucion",
    ],
    "Valor": [
        os.path.basename(archivo), HOJA, "Julio 2026", TOL,
        MATERIALIDAD,
        UMBRAL_AMARILLO, UMBRAL_ROJO,
        IND_SIN_AMARILLO, IND_SIN_ROJO,
        IND_COS_AMARILLO, IND_COS_ROJO,
        PESO_INC, PESO_SIN, PESO_COS, PESO_V25,
        usuario, datetime.now().strftime("%Y-%m-%d %H:%M"),
    ],
    "Descripcion": [
        "Base compartida por Suscripcion", "Pestana con el detalle por contrato",
        "Real acumulado 7 meses (7+5)",
        "Diferencias menores a este monto no generan alerta",
        "Contratos con prima menor a este monto no escalan a ROJO",
        "Desviacion relativa que marca AMARILLO",
        "Desviacion relativa que marca ROJO",
        "Ind. siniestralidad FCST > umbral marca AMARILLO",
        "Ind. siniestralidad FCST > umbral marca ROJO",
        "Ind. costos FCST > umbral marca AMARILLO",
        "Ind. costos FCST > umbral marca ROJO",
        "V2: incremento vs ppto Ago-Dic ajustado por ejecucion",
        "V4: siniestralidad implicita del forecast",
        "V4: costos implicitos del forecast",
        "V3: incremento Ago-Dic vs mismo periodo 2025",
        "Usuario que ejecuto el script", "",
    ],
})

# =====================================================
# EXPORT EXCEL
# =====================================================

salida_xlsx = os.path.join(xOutputs, "VAL_RFCST26.xlsx")

cols_resumen = [
    "LN", "Contratos", "Primas_0726", "Primas_1226", "Primas_PPTO1226",
    "Primas_1225", "Inc_AgoDic", "Inc_Esperado", "Desv_Inc_AgoDic",
    "Semaforo_Inc", "Cumplimiento_PPTO", "Gap_Primas", "Crec_vs_Real25",
    "Crec_AgoDic_vs_25", "Ind_Sin_FCST", "Ind_Sin_Real25", "Semaforo_Sin",
    "Ind_Cos_FCST", "Ind_Cos_Real25", "Semaforo_Costos",
    "Contratos_Alerta", "Pct_Alerta", "Score_Total", "Nivel_Riesgo", "Ranking",
]

cols_detalle = columnas_dim + [
    "Primas 0726", "Primas 1226", "Primas PPTO1226", "Primas PPTO08-1226",
    "Primas PPTO01-0726", "Primas 1225", "Primas 08-1225",
    "Inc_Primas_AgoDic", "Ratio_Ejecucion", "Inc_Esperado_AgoDic",
    "Desv_Inc_AgoDic", "Crec_vs_Real25", "Crec_AgoDic_vs_25",
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
                    for k in ("desv", "var", "crec", "pct", "cumplimiento",
                              "ind_", "ind.", "incr.", "ratio", "score")
                )
                ancho = 12
                ws.set_column(j, j, ancho, fmt_pct if es_pct else fmt_moneda)
            else:
                ws.set_column(j, j, 16, fmt_texto)

            if nombre_l.startswith("semaforo") or nombre_l == "nivel_riesgo":
                letra_ini = j
                n = len(tabla)
                for valor, fmt in (
                    ("ROJO", fmt_rojo), ("CRITICO", fmt_rojo),
                    ("AMARILLO", fmt_amarillo), ("ALTO", fmt_amarillo),
                    ("VERDE", fmt_verde), ("BAJO", fmt_verde),
                ):
                    ws.conditional_format(1, letra_ini, n, letra_ini, {
                        "type": "cell", "criteria": "==",
                        "value": f'"{valor}"', "format": fmt,
                    })

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(tabla), len(tabla.columns) - 1)

    exportar(dashboard, "Dashboard")
    exportar(ranking[cols_resumen], "Resumen_LN")
    exportar(resumen_tiporea, "Resumen_LN_TipoRea")
    exportar(resumen_fuente, "Resumen_Fuente")
    exportar(resumen_pais, "Resumen_Pais")
    exportar(excepciones[cols_detalle].head(500), "Excepciones")
    exportar(df[cols_detalle], "Detalle_Validaciones")
    exportar(parametros, "Parametros")

print(f"Excel generado: {salida_xlsx}")

# =====================================================
# GENERACION DEL DASHBOARD HTML
# =====================================================
# Produce un HTML autocontenido (sin dependencias
# externas ni internet) con tema oscuro: KPIs, barras
# por LN, dona de semaforos y tabla de excepciones.
# =====================================================

# Paleta (modo oscuro validado)
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
C_SIN_DATO = "#57565282"


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


def _nice_ticks(vmax, n=4):
    if vmax <= 0:
        return [0, 1]
    paso_bruto = vmax / n
    mag = 10 ** math.floor(math.log10(paso_bruto))
    for m in (1, 2, 2.5, 5, 10):
        if paso_bruto <= m * mag:
            paso = m * mag
            break
    ticks = []
    t = 0
    while t < vmax + paso * 0.999:
        ticks.append(t)
        t += paso
    return ticks


def _barra_redondeada(x, y, w, h, r=4):
    """Path de barra vertical con esquinas superiores redondeadas,
    anclada a la linea base."""
    if h <= 0.5:
        return ""
    r = min(r, w / 2, h)
    x2 = x + w
    yb = y + h
    return (
        f'M {x:.1f} {yb:.1f} L {x:.1f} {y + r:.1f} '
        f'Q {x:.1f} {y:.1f} {x + r:.1f} {y:.1f} '
        f'L {x2 - r:.1f} {y:.1f} '
        f'Q {x2:.1f} {y:.1f} {x2:.1f} {y + r:.1f} '
        f'L {x2:.1f} {yb:.1f} Z'
    )


def barras_agrupadas(categorias, series, width=980, height=320,
                     etiqueta_serie=0):
    """SVG de barras agrupadas.

    series: lista de dicts {nombre, color, valores}. Los valores NaN
    se dibujan como hueco. Solo la serie `etiqueta_serie` lleva
    etiqueta directa de valor (etiquetado selectivo).
    """
    mL, mR, mT, mB = 56, 12, 14, 46
    pw, ph = width - mL - mR, height - mT - mB

    vmax = 0
    for s in series:
        for v in s["valores"]:
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                vmax = max(vmax, v)
    ticks = _nice_ticks(vmax)
    vmax_t = ticks[-1]

    def ya(v):
        return mT + ph - (v / vmax_t) * ph

    nc, ns = len(categorias), len(series)
    grupo_w = pw / nc
    gap_barras = 2
    bw = min(34, (grupo_w * 0.72 - gap_barras * (ns - 1)) / ns)
    total_w = bw * ns + gap_barras * (ns - 1)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Barras por linea de negocio">']

    for t in ticks:
        y = ya(t)
        out.append(f'<line x1="{mL}" y1="{y:.1f}" x2="{width - mR}" '
                   f'y2="{y:.1f}" stroke="{C_GRID}" stroke-width="1"/>')
        out.append(f'<text x="{mL - 8}" y="{y + 3.5:.1f}" text-anchor="end" '
                   f'class="tick">{_fmt_m(t, 0)}</text>')

    for i, cat in enumerate(categorias):
        gx = mL + i * grupo_w + (grupo_w - total_w) / 2
        out.append(f'<text x="{mL + i * grupo_w + grupo_w / 2:.1f}" '
                   f'y="{height - mB + 18}" text-anchor="middle" '
                   f'class="cat">{cat}</text>')
        for k, s in enumerate(series):
            v = s["valores"][i]
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            x = gx + k * (bw + gap_barras)
            y = ya(max(v, 0))
            h = mT + ph - y
            path = _barra_redondeada(x, y, bw, h)
            if path:
                out.append(
                    f'<path d="{path}" fill="{s["color"]}" class="bar">'
                    f'<title>{cat} · {s["nombre"]}: {_fmt_m(v)}</title></path>'
                )
            if k == etiqueta_serie and vmax_t and v / vmax_t > 0.045:
                out.append(f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" '
                           f'text-anchor="middle" class="vlabel">'
                           f'{_fmt_m(v, 0)}</text>')

    out.append(f'<line x1="{mL}" y1="{mT + ph}" x2="{width - mR}" '
               f'y2="{mT + ph}" stroke="{C_BASE}" stroke-width="1"/>')
    out.append('</svg>')

    leyenda = ''.join(
        f'<span class="lg"><i style="background:{s["color"]}"></i>{s["nombre"]}</span>'
        for s in series
    )
    return f'<div class="legend">{leyenda}</div>{"".join(out)}'


def dona(conteos, width=230, height=230):
    """SVG tipo dona para la distribucion de semaforos.
    conteos: lista de (etiqueta, valor, color)."""
    total = sum(v for _, v, _ in conteos)
    cx, cy, r, grosor = width / 2, height / 2, width / 2 - 12, 30

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Distribucion de semaforos">']

    ang = -90.0
    for etiqueta, v, color in conteos:
        if total == 0 or v == 0:
            continue
        frac = v / total
        barrido = frac * 360
        # brecha de 2px convertida a grados sobre el radio medio
        gap_deg = min(2.5, barrido * 0.15)
        a0 = math.radians(ang + gap_deg / 2)
        a1 = math.radians(ang + barrido - gap_deg / 2)
        rm = r - grosor / 2
        x0, y0 = cx + rm * math.cos(a0), cy + rm * math.sin(a0)
        x1, y1 = cx + rm * math.cos(a1), cy + rm * math.sin(a1)
        grande = 1 if (a1 - a0) > math.pi else 0
        out.append(
            f'<path d="M {x0:.2f} {y0:.2f} A {rm:.2f} {rm:.2f} 0 {grande} 1 '
            f'{x1:.2f} {y1:.2f}" fill="none" stroke="{color}" '
            f'stroke-width="{grosor}" stroke-linecap="butt" class="bar">'
            f'<title>{etiqueta}: {v:,} ({frac:.1%})</title></path>'
        )
        ang += barrido

    out.append(f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
               f'class="donut-n">{total:,}</text>')
    out.append(f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" '
               f'class="donut-l">contratos</text>')
    out.append('</svg>')
    return ''.join(out)


def _chip(valor):
    clase = {"ROJO": "rojo", "AMARILLO": "amarillo", "VERDE": "verde"}.get(valor, "gris")
    icono = {"rojo": "&#9650;", "amarillo": "&#9679;", "verde": "&#10003;"}.get(clase, "–")
    return f'<span class="chip {clase}">{icono} {valor}</span>'


def generar_dashboard_html(ruta, df, resumen, dashboard, excepciones, parametros):

    d = dict(zip(dashboard["Indicador"], dashboard["Valor"]))

    total_fcst = d["Prima Forecast 2026"]
    total_ppto = d["Prima PPTO 2026"]
    total_real25 = d["Prima Real 2025"]
    total_0726 = d["Prima Real corte Jul 2026"]
    inc_agodic = d["Incremento implicito Ago-Dic"]
    esperado = d["Incremento esperado Ago-Dic (ppto ajustado)"]
    desv_inc = d["Desviacion incremento Ago-Dic"]
    real_agodic25 = d["Real Ago-Dic 2025 (referencia)"]
    n_rojo = int(d["Contratos ROJO"])
    n_amarillo = int(d["Contratos AMARILLO"])
    n_verde = int(d["Contratos VERDE"])
    n_v1 = int(d["Contratos FCST < Real Jul (V1)"])

    r = resumen.sort_values("LN").reset_index(drop=True)
    categorias = r["LN"].tolist()

    chart_primas = barras_agrupadas(
        categorias,
        [
            {"nombre": "Forecast 2026", "color": S1,
             "valores": r["Primas_1226"].tolist()},
            {"nombre": "Ppto 2026", "color": S2,
             "valores": r["Primas_PPTO1226"].tolist()},
            {"nombre": "Real 2025", "color": S3,
             "valores": r["Primas_1225"].tolist()},
        ],
    )

    chart_inc = barras_agrupadas(
        categorias,
        [
            {"nombre": "Incremento FCST Ago-Dic", "color": S1,
             "valores": r["Inc_AgoDic"].tolist()},
            {"nombre": "Esperado (Ppto Ago-Dic × ejecucion)", "color": S2,
             "valores": r["Inc_Esperado"].tolist()},
            {"nombre": "Real Ago-Dic 2025", "color": S3,
             "valores": r["Primas_0812_25"].tolist()},
        ],
        height=300,
    )

    grafica_dona = dona([
        ("Verde", n_verde, C_VERDE),
        ("Amarillo", n_amarillo, C_AMARILLO),
        ("Rojo", n_rojo, C_ROJO),
    ])

    # ----- tabla resumen por LN -----
    filas_ln = []
    for _, row in resumen.sort_values("Score_Total", ascending=False).iterrows():
        filas_ln.append(
            "<tr>"
            f"<td>LN {row['LN']}</td>"
            f"<td class='num'>{_fmt_m(row['Primas_1226'])}</td>"
            f"<td class='num'>{_fmt_pct(row['Cumplimiento_PPTO'] - 1, signo=True)}</td>"
            f"<td class='num'>{_fmt_pct(row['Crec_vs_Real25'], signo=True)}</td>"
            f"<td class='num'>{_fmt_pct(row['Desv_Inc_AgoDic'], signo=True)}</td>"
            f"<td>{_chip(row['Semaforo_Inc'])}</td>"
            f"<td class='num'>{_fmt_pct(row['Ind_Sin_FCST'])}</td>"
            f"<td>{_chip(row['Semaforo_Sin'])}</td>"
            f"<td class='num'>{int(row['Contratos_Alerta'])} / {int(row['Contratos'])}</td>"
            f"<td class='num'>{row['Score_Total']:.0f}</td>"
            f"<td><span class='nivel {row['Nivel_Riesgo'].lower()}'>{row['Nivel_Riesgo']}</span></td>"
            "</tr>"
        )

    # ----- tabla top excepciones -----
    filas_exc = []
    for _, row in excepciones.head(12).iterrows():
        motivos = []
        if row.get("F_V1_Primas"):
            motivos.append("FCST &lt; Real Jul")
        if row.get("F_V6_PrimaNegativa"):
            motivos.append("Prima negativa")
        if row.get("F_V6_FcstCero"):
            motivos.append("FCST en cero")
        if row.get("Semaforo_Sin") == "ROJO":
            motivos.append("Siniestralidad &gt; 100%")
        if row.get("Semaforo_Inc") == "ROJO":
            motivos.append("Desv. incremento")
        comp = str(row.get("Compañía", ""))[:38]
        filas_exc.append(
            "<tr>"
            f"<td>LN {row['LN']}</td>"
            f"<td>{comp}</td>"
            f"<td>{row.get('País', '')}</td>"
            f"<td>{row.get('Tipo Reaseguro', '')}</td>"
            f"<td class='num'>{_fmt_m(row['Primas 0726'], 2)}</td>"
            f"<td class='num'>{_fmt_m(row['Primas 1226'], 2)}</td>"
            f"<td class='num'>{_fmt_m(row['Inc_Primas_AgoDic'], 2)}</td>"
            f"<td class='motivo'>{' · '.join(motivos) if motivos else 'Revision'}</td>"
            "</tr>"
        )

    # ----- insight automatico -----
    peor = resumen.sort_values("Score_Total", ascending=False).iloc[0]
    cumpl = total_fcst / total_ppto - 1
    crec25 = total_fcst / total_real25 - 1
    insight = (
        f"El RFCST 2026 proyecta <b>{_fmt_m(total_fcst)}</b> de prima, "
        f"<b>{_fmt_pct(cumpl, signo=True)}</b> sobre el presupuesto anual y "
        f"<b>{_fmt_pct(crec25, signo=True)}</b> contra el cierre real 2025. "
        f"El incremento implicito Ago-Dic ({_fmt_m(inc_agodic)}) esta "
        f"<b>{_fmt_pct(desv_inc, signo=True)}</b> respecto al esperado ajustando "
        f"el ppto Ago-Dic por el nivel de ejecucion a julio ({_fmt_m(esperado)}), "
        f"y equivale a {inc_agodic / real_agodic25:,.1f}x el real del mismo "
        f"periodo 2025 ({_fmt_m(real_agodic25)}). "
        f"<b>{n_v1:,}</b> contratos reportan forecast menor al real de julio (V1) "
        f"y la LN con mayor score de riesgo es <b>LN {peor['LN']}</b> "
        f"({peor['Nivel_Riesgo']}, score {peor['Score_Total']:.0f})."
    )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validación RFCST 2026</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{
    background: {C_PAGE}; color: {C_INK};
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 26px 30px 40px;
  }}
  header {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
            margin-bottom: 20px; }}
  h1 {{ font-size: 21px; font-weight: 650; }}
  header .sub {{ color: {C_MUTED}; font-size: 12.5px; }}
  .grid {{ display: grid; gap: 14px; }}
  .kpis {{ grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }}
  .card {{
    background: {C_SURFACE}; border: 1px solid {C_BORDER};
    border-radius: 12px; padding: 16px 18px;
  }}
  .kpi .t {{ color: {C_INK2}; font-size: 12px; margin-bottom: 8px;
             display: flex; align-items: center; gap: 7px; }}
  .kpi .t i {{ width: 22px; height: 22px; border-radius: 6px; display: inline-flex;
               align-items: center; justify-content: center; font-style: normal;
               font-size: 12px; background: rgba(57,135,229,.16); }}
  .kpi .v {{ font-size: 26px; font-weight: 650; letter-spacing: -0.02em; }}
  .kpi .d {{ font-size: 12px; margin-top: 7px; color: {C_INK2}; }}
  .kpi .d b {{ font-weight: 600; padding: 2px 7px; border-radius: 999px;
               font-size: 11.5px; }}
  .up   {{ color: #7dd87d; background: rgba(12,163,12,.14); }}
  .down {{ color: #f09a9a; background: rgba(208,59,59,.16); }}
  .warn {{ color: {C_AMARILLO}; background: rgba(250,178,25,.13); }}
  section {{ margin-top: 14px; }}
  .card h2 {{ font-size: 13.5px; font-weight: 600; color: {C_INK2};
              margin-bottom: 4px; }}
  .card .nota {{ font-size: 11.5px; color: {C_MUTED}; margin-bottom: 10px; }}
  .dos {{ grid-template-columns: 2.1fr 1fr; align-items: stretch; }}
  @media (max-width: 900px) {{ .dos {{ grid-template-columns: 1fr; }} }}
  svg {{ width: 100%; height: auto; display: block; }}
  .tick, .donut-l {{ fill: {C_MUTED}; font-size: 10.5px;
    font-family: system-ui, sans-serif; font-variant-numeric: tabular-nums; }}
  .cat {{ fill: {C_INK2}; font-size: 11px; font-family: system-ui, sans-serif; }}
  .vlabel {{ fill: {C_INK2}; font-size: 10px; font-family: system-ui, sans-serif;
             font-variant-numeric: tabular-nums; }}
  .donut-n {{ fill: {C_INK}; font-size: 26px; font-weight: 650;
              font-family: system-ui, sans-serif; }}
  .bar {{ transition: opacity .12s; }}
  svg:hover .bar {{ opacity: .45; }}
  svg .bar:hover {{ opacity: 1; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 4px 0 10px; }}
  .lg {{ color: {C_INK2}; font-size: 11.5px; display: inline-flex;
         align-items: center; gap: 6px; }}
  .lg i {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}
  .donut-wrap {{ display: flex; flex-direction: column; align-items: center;
                 gap: 6px; }}
  .donut-wrap svg {{ max-width: 210px; }}
  .dl {{ width: 100%; font-size: 12px; color: {C_INK2}; }}
  .dl div {{ display: flex; justify-content: space-between; padding: 5px 2px;
             border-bottom: 1px solid {C_GRID}; }}
  .dl div:last-child {{ border-bottom: none; }}
  .dl i {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block;
           margin-right: 7px; }}
  .dl .n {{ font-variant-numeric: tabular-nums; color: {C_INK}; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: {C_MUTED}; font-weight: 500; font-size: 11px;
        padding: 7px 10px; border-bottom: 1px solid {C_BASE};
        white-space: nowrap; }}
  td {{ padding: 7.5px 10px; border-bottom: 1px solid {C_GRID};
        white-space: nowrap; }}
  tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(255,255,255,.03); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  th.num {{ text-align: right; }}
  .motivo {{ color: {C_INK2}; white-space: normal; max-width: 260px; }}
  .chip {{ font-size: 10.5px; font-weight: 600; padding: 2px 8px;
           border-radius: 999px; }}
  .chip.rojo {{ color: #f09a9a; background: rgba(208,59,59,.16); }}
  .chip.amarillo {{ color: {C_AMARILLO}; background: rgba(250,178,25,.13); }}
  .chip.verde {{ color: #7dd87d; background: rgba(12,163,12,.14); }}
  .chip.gris {{ color: {C_MUTED}; background: rgba(137,135,129,.15); }}
  .nivel {{ font-size: 10.5px; font-weight: 700; padding: 2px 8px;
            border-radius: 5px; }}
  .nivel.critico {{ color: #f09a9a; background: rgba(208,59,59,.18); }}
  .nivel.alto {{ color: {C_AMARILLO}; background: rgba(250,178,25,.14); }}
  .nivel.medio {{ color: #9ec5f4; background: rgba(57,135,229,.14); }}
  .nivel.bajo {{ color: #7dd87d; background: rgba(12,163,12,.14); }}
  .insight {{ background: linear-gradient(90deg, rgba(57,135,229,.10),
              rgba(57,135,229,.03)); border: 1px solid rgba(57,135,229,.25);
              border-radius: 12px; padding: 14px 18px; font-size: 13px;
              line-height: 1.55; color: {C_INK2}; }}
  .insight b {{ color: {C_INK}; }}
  .scroll {{ overflow-x: auto; }}
  footer {{ margin-top: 18px; color: {C_MUTED}; font-size: 11px; }}
</style>
</head>
<body>

<header>
  <h1>Validación RFCST 2026 · 7+5</h1>
  <span class="sub">Corte Julio 2026 · {parametros['archivo']} ·
    generado {parametros['generado']}</span>
</header>

<div class="grid kpis">
  <div class="card kpi">
    <div class="t"><i>&#128181;</i>Prima Forecast 2026</div>
    <div class="v">{_fmt_m(total_fcst)}</div>
    <div class="d"><b class="{'up' if cumpl >= 0 else 'down'}">{_fmt_pct(cumpl, signo=True)}</b>
      vs Ppto 2026 ({_fmt_m(total_ppto)})</div>
  </div>
  <div class="card kpi">
    <div class="t"><i>&#128200;</i>Crecimiento vs Real 2025</div>
    <div class="v">{_fmt_pct(crec25, signo=True)}</div>
    <div class="d">Real 2025: {_fmt_m(total_real25)} · Real Jul 26: {_fmt_m(total_0726)}</div>
  </div>
  <div class="card kpi">
    <div class="t"><i>&#9202;</i>Incremento Ago-Dic implícito</div>
    <div class="v">{_fmt_m(inc_agodic)}</div>
    <div class="d"><b class="{'warn' if abs(desv_inc) > 0.2 else 'up'}">{_fmt_pct(desv_inc, signo=True)}</b>
      vs esperado ({_fmt_m(esperado)})</div>
  </div>
  <div class="card kpi">
    <div class="t"><i>&#9888;</i>Contratos con alerta</div>
    <div class="v">{n_rojo + n_amarillo:,}</div>
    <div class="d"><b class="down">{n_rojo:,} rojos</b> · {n_amarillo:,} amarillos ·
      {n_v1:,} con FCST &lt; Real Jul</div>
  </div>
</div>

<section class="grid dos">
  <div class="card">
    <h2>Primas por línea de negocio</h2>
    <div class="nota">Forecast acumulado a Dic 2026 vs presupuesto anual y cierre real 2025 (USD)</div>
    {chart_primas}
  </div>
  <div class="card donut-wrap">
    <h2>Semáforo de contratos</h2>
    {grafica_dona}
    <div class="dl">
      <div><span><i style="background:{C_VERDE}"></i>&#10003; Verde — sin alertas</span><span class="n">{n_verde:,}</span></div>
      <div><span><i style="background:{C_AMARILLO}"></i>&#9679; Amarillo — revisar</span><span class="n">{n_amarillo:,}</span></div>
      <div><span><i style="background:{C_ROJO}"></i>&#9650; Rojo — inconsistencia</span><span class="n">{n_rojo:,}</span></div>
    </div>
  </div>
</section>

<section class="card">
  <h2>Incremento Ago-Dic 2026: forecast vs esperado</h2>
  <div class="nota">Esperado = Ppto Ago-Dic 2026 × nivel de ejecución Ene-Jul
    (Real Jul / Ppto Ene-Jul). Referencia: real del mismo periodo 2025. LN 4004
    no tiene ppto Ene-Jul, por lo que no se calcula esperado.</div>
  {chart_inc}
</section>

<section class="card scroll">
  <h2>Resumen por línea de negocio</h2>
  <div class="nota">Ordenado por score de riesgo (0-100). Índices calculados sobre agregados.</div>
  <table>
    <thead><tr>
      <th>LN</th><th class="num">Prima FCST</th><th class="num">vs Ppto</th>
      <th class="num">vs Real 25</th><th class="num">Desv. inc. Ago-Dic</th><th>Semáforo</th>
      <th class="num">% Sin FCST</th><th>Semáforo</th>
      <th class="num">Alertas</th><th class="num">Score</th><th>Riesgo</th>
    </tr></thead>
    <tbody>{''.join(filas_ln)}</tbody>
  </table>
</section>

<section class="card scroll">
  <h2>Top excepciones (semáforo rojo)</h2>
  <div class="nota">Contratos con mayor impacto en prima. Detalle completo en VAL_RFCST26.xlsx → Excepciones.</div>
  <table>
    <thead><tr>
      <th>LN</th><th>Compañía</th><th>País</th><th>Tipo</th>
      <th class="num">Real Jul 26</th><th class="num">FCST Dic 26</th>
      <th class="num">Inc. Ago-Dic</th><th>Motivo</th>
    </tr></thead>
    <tbody>{''.join(filas_exc)}</tbody>
  </table>
</section>

<section class="insight">&#128161; {insight}</section>

<footer>Validación automática VAL_RFCST26.py · Planeación Financiera ·
  cifras en dólares · V1: consistencia acumulada · V2: incremento vs ppto ajustado ·
  V3: coherencia vs 2025 · V4: índices vs factores · V5: vs ppto anual · V6: calidad de datos</footer>

</body>
</html>"""

    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)


# =====================================================
# EXPORT DASHBOARD HTML
# =====================================================

salida_html = os.path.join(xOutputs, "Dashboard_RFCST26.html")

generar_dashboard_html(
    ruta=salida_html,
    df=df,
    resumen=ranking,
    dashboard=dashboard,
    excepciones=excepciones,
    parametros={
        "corte": "Julio 2026",
        "archivo": os.path.basename(archivo),
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
    },
)

print(f"Dashboard generado: {salida_html}")

print(f"Listo en {time.perf_counter() - inicio:.1f} s")
