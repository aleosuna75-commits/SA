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
import time
import getpass
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

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
# EXPORT DASHBOARD HTML
# =====================================================

from dashboard_html import generar_dashboard_html

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
