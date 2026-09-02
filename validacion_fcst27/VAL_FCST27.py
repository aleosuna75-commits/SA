# =====================================================
# VAL_FCST27 - VALIDACION DEL FCST 2027 (PPTO TECNICO)
# =====================================================
# Valida las cifras del FCST 2027 que comparte Suscripcion
# (PptoTecnico*.csv, export de SAP BW) contra:
#
#   V1. RFCST 2026 (base BD_RFCST*.xlsx del ejercicio 7+5):
#       niveles, crecimiento y participacion por LN
#   V2. Indices tecnicos implicitos del FCST 27
#       (siniestralidad S/P y comisiones C/P)
#   V3. Estacionalidad mensual de primas, siniestros y
#       comisiones (concentracion y meses sin registro)
#   V4. Coherencia por negocio (cedente / contrato):
#       siniestros sin prima, primas con signo invertido
#   V5. Calidad de datos del export (conceptos sin
#       clasificar, montos atipicos, anios fuera de rango)
#
# Output:
#   - Outputs/VAL_FCST27.xlsx        (detalle + resumen)
#   - Outputs/Dashboard_FCST27.html  (dashboard PRISMA:
#       General / Linea de Negocio / Negocios con vistas
#       tomado-retenido, estacionalidad y filtros)
#
# -----------------------------------------------------
# NOTA IMPORTANTE SOBRE EL EXPORT DE SUSCRIPCION
# -----------------------------------------------------
# El CSV trae un defecto de origen que este script resuelve y
# documenta (hoja Mapeo_Columnas del Excel): los encabezados NO
# corresponden a las columnas de datos (el export de BW escribio
# el catalogo de campos en otro orden), asi que el script lee POR
# POSICION con el layout de abajo, inferido y verificado contra
# la estructura de los datos.
#
# El concepto (primas / siniestros / comisiones) sale de la
# cuenta contable que trae el export de 45 columnas, segun el
# catalogo CUENTAS_CONCEPTO: las cuentas 61xx concentran la
# prima (en negativo, por ser abono), 5402 los siniestros y 5310
# las comisiones. El mapeo se verifico contra el RFCST 2026 y el
# real 2026: los indices implicitos que produce (S/P 44%, C/P
# 18%) empatan con los de esas bases.
#
# El export anterior, de 42 columnas, no traia esa cuenta y el
# concepto tenia que reconstruirse por la estructura del archivo
# (corridas Primas -> Siniestros -> Comisiones por negocio). Esa
# ruta se conserva como respaldo, pero NO separa siniestros de
# comisiones en los negocios con una sola corrida positiva, asi
# que las cifras de ese layout llevan esa salvedad.
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
import xlsxwriter

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
# xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\2027\4_Validacion"
xFolder = os.path.dirname(os.path.abspath(__file__))

xInputs = os.path.join(xFolder, "Inputs")
xOutputs = os.path.join(xFolder, "Outputs")

os.makedirs(xOutputs, exist_ok=True)

# ---- Base del FCST 2027 (CSV de Suscripcion) ----
ARCHIVO_FCST = "PptoTecnico2026.csv"
PREFIJO_FCST = "PptoTecnico"          # fallback: el .csv mas reciente

ANIO_FCST = 2027                      # ejercicio que se valida

ETIQ_FCST = f"FCST {ANIO_FCST}"

# Planeacion reporta el presupuesto 2026 como "FCST 2026"
# (fue el forecast con el que se cerro ese ejercicio): esta
# etiqueta se usa en el dashboard y en el Excel
ETIQ_PPTO26 = "FCST 2026"
MESES_TXT = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]

# Cortes del RFCST 2026: la base no esta mensualizada, solo
# separa el real acumulado a julio del incremento Ago-Dic
MESES_ENEJUL = [1, 2, 3, 4, 5, 6, 7]
MESES_AGODIC = [8, 9, 10, 11, 12]

# ---- Base del RFCST 2026 (comparativo, opcional) ----
# Es la misma base que alimenta VAL_RFCST26 / el dashboard
# del RFCST. Si no se encuentra, el dashboard muestra s/d
# en las comparativas y el resto sigue funcionando.
ARCHIVO_RFCST = "BD_RFCST_26_act.xlsx"
PREFIJO_RFCST = "BD_RFCST"
HOJA_RFCST = "BD_RFCST26"

# ---- Real 2026 mensual (opcional) ----
# Da la forma mensual observada Ene-Jul 2026, que es la que se
# usa para abrir el acumulado a julio del RFCST 2026
ARCHIVO_REAL26 = "BDReal26.xlsx"
PREFIJO_REAL26 = "BDReal26"
HOJA_REAL26 = "BD"
COL_REAL26 = {"P": "Primas USD", "S": "Siniestros USD", "C": "Comisiones USD"}
COL_REAL26_LN = ["LN2", "LN"]
ANIO_REAL26 = 2026

# ---- Presupuesto 2026 mensual (hoja del libro del RFCST) ----
# Trae los 12 meses del ejercicio, asi que la estacionalidad del
# FCST 2026 sale directa (no necesita ajuste)
HOJA_PPTO26 = "Ppto2026"
COL_PPTO26 = {"P": "PmasEmi", "S": "SinOcurr", "C": "CostosAdq"}
COL_PPTO26_LN = ["LN2", "LíneaNegocio", "LineaNegocio", "ClasificaciónLN"]
COL_PPTO26_ANIO = ["AñoPpto", "AnioPpto", "Año", "Anio"]
COL_PPTO26_MES = ["MesPpto", "Mes", "Periodo"]

# Los niveles del FCST 2026 salen de BD_RFCST26 (mismo universo de
# contratos que el comparativo). La hoja Ppto2026 trae el
# presupuesto completo de la compania, que es mayor porque incluye
# contratos sin prima registrada: ponerlo en True para reportar
# ese presupuesto completo en los niveles (la estacionalidad usa
# la hoja en ambos casos, porque es un perfil porcentual).
PPTO26_NIVEL_DESDE_HOJA = False

# ---- Catalogo de cedentes (numero -> nombre, opcional) ----
ARCHIVO_CATALOGO = "Catalogo"
HOJA_CATALOGO = "Valores"
COL_CAT_NUM = "Ced"
COL_CAT_NOMBRE = "CedenteRP"

# ---- Umbrales de validacion ----
TOL = 1.0                     # tolerancia en USD
MATERIALIDAD = 10_000         # USD: negocios por debajo no escalan a ROJO

# Impacto minimo en dolares para levantar una alerta de
# comparacion contra 2026: sin esto, un negocio de 30 k con la
# siniestralidad movida 30 pp pesa lo mismo que uno de 20 M y el
# reporte se llena de ruido que no es accionable
RELEVANCIA = 100_000

UMBRAL_AMARILLO = 0.20        # desviacion vs RFCST que marca AMARILLO
UMBRAL_ROJO = 0.40            # desviacion vs RFCST que marca ROJO

IND_SIN_AMARILLO = 0.80       # siniestralidad implicita S/P
IND_SIN_ROJO = 1.00
# Comisiones implicitas C/P. El portafolio corre en 18.5% (RFCST
# 20.2%) pero hay lineas que operan estructuralmente alto (LN 4003
# ronda 41%), asi que los umbrales van por encima de esa banda
IND_COS_AMARILLO = 0.45
IND_COS_ROJO = 0.65

# Concentracion mensual de la prima. A nivel LN es una senal util
# (una linea no deberia cargar el ano en un mes); a nivel contrato
# NO se alerta, porque la prima unica anual es la norma en
# reaseguro: el dato se reporta pero no levanta semaforo.
CONC_AMARILLO = 0.40
CONC_ROJO = 0.60

# Salto de un indice tecnico (siniestralidad o comisiones) del
# negocio contra su propio RFCST 2026, en puntos porcentuales.
# Solo alerta si ademas mueve mas de RELEVANCIA en dolares.
SALTO_IND = 0.30

MONTO_ATIPICO = 100e6         # renglones individuales mayores se reportan

# Ponderaciones del score de riesgo por LN
PESO_CREC = 0.35              # V1 crecimiento vs RFCST 2026
PESO_SIN = 0.30               # V2 siniestralidad implicita
PESO_COS = 0.15               # V2 comisiones implicitas
PESO_EST = 0.20               # V3 concentracion estacional

# ---- Vista RETENIDO ----
# La base actual NO trae una marca confiable de cesion /
# retencion: hay dos banderas binarias candidatas (ver hoja
# Retencion_Candidatas del Excel con la retencion implicita
# de cada una). Hasta que Suscripcion confirme cual es:
#
#   COL_VISTA_RETENIDO = None      -> retenido = tomado (con aviso)
#   COL_VISTA_RETENIDO = "Flag_A"  -> usa la bandera de la pos. 23
#   COL_VISTA_RETENIDO = "Flag_C"  -> usa la bandera de la pos. 33
#
# Alternativa: % de retencion por LN capturado a mano, ej.
#   RETENCION_LN = {"4001": 0.75, "4004": 0.60}
COL_VISTA_RETENIDO = None
VALOR_RETENIDO = 1            # valor de la bandera que marca lo retenido
RETENCION_LN = {}

# ---- Mapeo posicional del CSV ----
# Posicion -> campo, porque los encabezados del export vienen
# permutados respecto a las columnas de datos. Hay dos layouts
# segun el numero de columnas; se elige por el ancho del archivo.
#
#   45 columnas (export actual): trae la cuenta contable que
#      identifica el concepto, el numero de contrato y la columna
#      de Binder Ppto (hoy vacia).
#   42 columnas (export anterior): sin cuenta de concepto, el
#      concepto se reconstruye por la estructura del archivo.

MAPEO_45 = {
    1: "Cuenta_Concepto",  # cuenta contable: identifica P / S / C
    6: "LN",               # LN04001 ... LN04008-Agro
    7: "Pais_Cod",         # codigo numerico de pais / oficina
    11: "Moneda",          # moneda del contrato (el monto viene en USD)
    12: "Cuenta_LN",       # cuenta contable de la LN (redundante con LN)
    13: "Producto",        # cuenta tecnica / producto (A0xx...)
    14: "Contrato",        # numero de contrato dentro del cedente
    16: "Periodo",         # AAAA0PP fiscal (2027001..2027012 en el plan)
    18: "Anio",            # ejercicio fiscal del renglon
    21: "Mes",             # mes 1-12
    25: "Flag_A",          # bandera binaria (candidata retencion)
    27: "Flag_B",          # bandera 1/2/3 (uso por confirmar)
    28: "TipoRea_Cod",     # 1-4, tipo de reaseguro (por confirmar)
    32: "Anio_Susc",       # anio de suscripcion de la cohorte
    33: "Cedente",         # numero de cedente
    34: "Corredor",        # numero de corredor
    35: "Flag_C",          # bandera binaria (candidata retencion / MGA)
    39: "Monto",           # monto USD (primas en negativo, S y C en positivo)
    41: "Region",          # region R01-R06
    42: "Binder_Ppto",     # binder de presupuesto (hoy vacio en el export)
    44: "Archivo_Origen",  # archivo fuente por LN
}

MAPEO_42 = {
    4: "LN", 5: "Pais_Cod", 9: "Moneda", 10: "Cuenta_LN", 11: "Producto",
    12: "Contrato", 14: "Periodo", 16: "Anio", 19: "Mes", 23: "Flag_A",
    25: "Flag_B", 26: "TipoRea_Cod", 30: "Anio_Susc", 31: "Cedente",
    32: "Corredor", 33: "Flag_C", 37: "Monto", 39: "Region",
}

LAYOUTS = {45: MAPEO_45, 42: MAPEO_42}

# Columnas que varian dentro de un mismo negocio-concepto y por
# eso NO forman parte de la llave cuando hay que reconstruir el
# concepto por estructura (periodo, anio de proyeccion y cohorte)
POS_NO_LLAVE = {45: {16, 17, 18, 20, 21, 22, 32, 39},
                42: {14, 15, 16, 18, 19, 20, 30, 37}}

# ---- Concepto por cuenta contable (layout de 45 columnas) ----
# Verificado contra el RFCST 2026 y el real 2026: las cuentas 61xx
# concentran la prima (en negativo, por ser abono), 5402 los
# siniestros y 5310 las comisiones. Los indices implicitos que
# resultan (S/P 44%, C/P 18%) empatan con los del RFCST.
CUENTAS_CONCEPTO = {
    "6104010000": "P", "6108010000": "P", "6111090000": "P",
    "5402010000": "S", "5402030000": "S",
    "5310010000": "C",
}

# Respaldo por prefijo, para cuentas nuevas del mismo grupo
PREFIJOS_CONCEPTO = [("61", "P"), ("5402", "S"), ("5310", "C")]

MEDIDAS = ["Primas", "Siniestros", "Comisiones"]
CLAVE_MEDIDA = {"P": "Primas", "S": "Siniestros", "C": "Comisiones"}

# =====================================================
# LOCALIZACION DE ARCHIVOS
# =====================================================


def _buscar_archivo(nombre_exacto, prefijo, extension):
    """Nombre exacto en Inputs o junto al script; si no, el
    archivo prefijo*extension mas reciente (avisando)."""
    for carpeta in (xInputs, xFolder):
        ruta = os.path.join(carpeta, nombre_exacto)
        if os.path.exists(ruta):
            return ruta

    candidatos = sorted(
        {
            os.path.join(carpeta, f)
            for carpeta in (xInputs, xFolder)
            if os.path.isdir(carpeta)
            for f in os.listdir(carpeta)
            if f.startswith(prefijo) and f.endswith(extension)
            and not f.startswith("~$")
        },
        key=os.path.getmtime,
        reverse=True,
    )
    if not candidatos:
        return None
    if len(candidatos) > 1:
        print(f"AVISO: no se encontro {nombre_exacto} y hay varios "
              f"{prefijo}*{extension}. Se usa el mas reciente:")
        for c in candidatos:
            marca = "->" if c == candidatos[0] else "  "
            fecha = datetime.fromtimestamp(os.path.getmtime(c)).strftime("%d/%m/%Y %H:%M")
            print(f"  {marca} {os.path.basename(c)}  (modificado {fecha})")
    return candidatos[0]


archivo = _buscar_archivo(ARCHIVO_FCST, PREFIJO_FCST, ".csv")

if archivo is None:
    raise FileNotFoundError(
        f"No se encontro {ARCHIVO_FCST} ni {PREFIJO_FCST}*.csv en {xInputs} ni en {xFolder}"
    )

# =====================================================
# CARGA DEL CSV (POSICIONAL)
# =====================================================

print(f"Leyendo {archivo} ...")

df = pd.read_csv(archivo, encoding="utf-8-sig", low_memory=False)

ENCABEZADOS_ORIGINALES = [str(c).strip() for c in df.columns]

N_COLUMNAS_CSV = len(df.columns)

if N_COLUMNAS_CSV not in LAYOUTS:
    raise ValueError(
        f"El CSV trae {N_COLUMNAS_CSV} columnas y solo hay layout para "
        f"{sorted(LAYOUTS)}. Cambio el export: revisar MAPEO_45 / MAPEO_42."
    )

MAPEO_POSICIONAL = LAYOUTS[N_COLUMNAS_CSV]
_POS_NO_LLAVE = POS_NO_LLAVE[N_COLUMNAS_CSV]

df.columns = [MAPEO_POSICIONAL.get(i, f"pos{i:02d}") for i in range(N_COLUMNAS_CSV)]

if "Binder_Ppto" not in df.columns:
    df["Binder_Ppto"] = np.nan

df["Monto"] = pd.to_numeric(
    df["Monto"].astype(str).str.replace(",", "", regex=False), errors="coerce"
).fillna(0.0)

for col in ("Periodo", "Anio", "Mes", "Anio_Susc"):
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(np.int64)

df["LN"] = (df["LN"].astype(str).str.strip()
            .str.replace(r"^LN0*", "", regex=True))

for col in ("Cedente", "Contrato", "Corredor"):
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(np.int64)

# Los nulos se pasan a cadena vacia ANTES de astype(str): en
# pandas reciente astype(str) conserva el nulo y el groupby por
# binder se quedaria sin grupos
df["Binder_Ppto"] = (
    df["Binder_Ppto"].where(df["Binder_Ppto"].notna(), "")
    .astype(str).str.strip()
    .replace({"nan": "", "None": "", "0": "", "0.0": ""})
)

print(f"  {len(df):,} renglones ({N_COLUMNAS_CSV} columnas) · "
      f"LN: {df['LN'].nunique()} · cedentes: {df['Cedente'].nunique():,} · "
      f"contratos: {df['Contrato'].nunique():,} · "
      f"anios fiscales: {df['Anio'].min()}-{df['Anio'].max()}")

if df["Binder_Ppto"].eq("").all():
    print("  Binder Ppto: la columna viene vacia en el export "
          "(se incluye en el dashboard para cuando se llene).")

# Verificacion cruzada del mapeo: la cuenta contable de la
# LN (pos. 10) debe corresponder 1 a 1 con la LN (pos. 4);
# si no, el layout del export cambio y el mapeo ya no vale
_cruce = df.groupby("LN")["Cuenta_LN"].nunique()
_cruce2 = df.groupby("Cuenta_LN")["LN"].nunique()
if (_cruce > 1).any() or (_cruce2 > 1).any():
    print("AVISO: la cuenta de LN (pos. 10) no corresponde 1 a 1 con la LN "
          "(pos. 4). Revisar MAPEO_POSICIONAL: el layout del export pudo cambiar.")

# =====================================================
# RECONSTRUCCION DEL CONCEPTO (P / S / C)
# =====================================================
# Para cada negocio (todas las dimensiones estables iguales)
# el export escribe corridas contiguas de renglones, una por
# concepto y en este orden: Primas (negativos), Siniestros y
# Comisiones (positivos). Dentro de cada corrida los renglones
# van por cohorte de suscripcion y periodo ascendentes, asi
# que el limite entre conceptos es el punto donde el periodo
# retrocede sin que la cohorte avance.

def concepto_por_cuenta(serie):
    """P / S / C a partir de la cuenta contable, con respaldo por
    prefijo para cuentas nuevas del mismo grupo."""
    cta = serie.astype(str).str.strip()
    out = cta.map(CUENTAS_CONCEPTO)

    faltan = out.isna()
    if faltan.any():
        for pref, etiqueta in PREFIJOS_CONCEPTO:
            hit = faltan & cta.str.startswith(pref)
            out = out.mask(hit, etiqueta)
            faltan = out.isna()

    return out.fillna("X"), cta


CUENTAS_NUEVAS = {}

if "Cuenta_Concepto" in df.columns:
    df["Concepto"], _cta = concepto_por_cuenta(df["Cuenta_Concepto"])

    _no_cat = ~_cta.isin(CUENTAS_CONCEPTO)
    if _no_cat.any():
        CUENTAS_NUEVAS = (df.loc[_no_cat]
                          .groupby(_cta[_no_cat])
                          .agg(Renglones=("Monto", "size"),
                               Monto=("Monto", "sum"),
                               Concepto=("Concepto", "first"))
                          .to_dict("index"))
        print(f"AVISO: {len(CUENTAS_NUEVAS)} cuenta(s) fuera del catalogo "
              "CUENTAS_CONCEPTO; se clasificaron por prefijo (ver Calidad_Datos).")

    print("Concepto tomado de la cuenta contable del export.")
    METODO_CONCEPTO = "cuenta contable (columna del export)"
else:
    METODO_CONCEPTO = ("estructura del archivo (el export no trae la cuenta "
                       "que identifica el concepto)")
    print("Reconstruyendo el concepto por estructura del archivo ...")
    print("  AVISO: sin la cuenta contable no se pueden separar siniestros de")
    print("         comisiones en los negocios con un solo bloque positivo.")

    llave_cols = [MAPEO_POSICIONAL.get(i, f"pos{i:02d}")
                  for i in range(N_COLUMNAS_CSV) if i not in _POS_NO_LLAVE]

    negocio_id = df.groupby(llave_cols, sort=False, dropna=False).ngroup().to_numpy()

    per = df["Periodo"].to_numpy()
    coh = df["Anio_Susc"].to_numpy()

    cambio_negocio = np.empty(len(df), dtype=bool)
    cambio_negocio[0] = True
    cambio_negocio[1:] = negocio_id[1:] != negocio_id[:-1]

    corte_concepto = np.zeros(len(df), dtype=bool)
    corte_concepto[1:] = (per[1:] < per[:-1]) & (coh[1:] <= coh[:-1])

    bloque_id = np.cumsum(cambio_negocio | corte_concepto) - 1

    df["_bloque"] = bloque_id

    blq = df.groupby("_bloque", sort=True).agg(suma=("Monto", "sum"))
    blq["negocio"] = pd.Series(negocio_id).groupby(bloque_id).first().to_numpy()
    blq["inicio"] = pd.Series(np.arange(len(df))).groupby(bloque_id).first().to_numpy()

    conceptos_blq = np.empty(len(blq), dtype="U1")

    orden = blq.sort_values("inicio").index.to_numpy()
    negocios_ord = blq.loc[orden, "negocio"].to_numpy()
    sumas_ord = blq.loc[orden, "suma"].to_numpy()

    neg_prev = -1
    positivos = 0
    for j in range(len(orden)):
        if negocios_ord[j] != neg_prev:
            neg_prev = negocios_ord[j]
            positivos = 0
        s = sumas_ord[j]
        if s < -TOL:
            etiqueta = "P"
        elif s > TOL:
            positivos += 1
            etiqueta = "S" if positivos == 1 else ("C" if positivos == 2 else "X")
        else:
            etiqueta = "N"          # bloque neutro: no consume turno
        conceptos_blq[orden[j]] = etiqueta

    mapa_concepto = pd.Series(conceptos_blq, index=blq.index)
    df["Concepto"] = mapa_concepto.reindex(df["_bloque"]).to_numpy()

    df.drop(columns="_bloque", inplace=True)

# Valor con signo economico: primas positivas, siniestros y
# comisiones positivos como gasto (P-S-C resta directamente)
df["Valor"] = np.where(df["Concepto"] == "P", -df["Monto"], df["Monto"])

_conteo = df["Concepto"].value_counts()
print("  Bloques clasificados:",
      " · ".join(f"{k}: {int(v):,}" for k, v in _conteo.items()))

# =====================================================
# BASE DEL EJERCICIO (ANIO_FCST)
# =====================================================

d = df[df["Anio"] == ANIO_FCST].copy()

if d.empty:
    raise ValueError(f"El CSV no trae renglones del ejercicio {ANIO_FCST}.")

meses_plan = sorted(d["Mes"].unique())
if meses_plan != list(range(1, 13)):
    print(f"AVISO: el ejercicio {ANIO_FCST} no trae los 12 meses: {meses_plan}")

d_ok = d[d["Concepto"].isin(["P", "S", "C"])].copy()

# =====================================================
# CALIDAD DE DATOS (V5)
# =====================================================

calidad = []


def _chk(check, detalle, n, monto):
    calidad.append({"Check": check, "Detalle": detalle,
                    "Renglones": int(n), "Monto USD": float(monto)})


_chk("Encabezados permutados",
     "El CSV trae los nombres de columna en otro orden que los datos; "
     "se leyo con el mapeo posicional de la hoja Mapeo_Columnas.",
     0, 0)

_chk("Origen del concepto P/S/C",
     f"Concepto tomado de: {METODO_CONCEPTO}."
     + ("" if "cuenta" in METODO_CONCEPTO else
        " Sin la cuenta contable, los negocios con un solo bloque positivo "
        "no permiten separar siniestros de comisiones."), 0, 0)

for _cta_nueva, _info in CUENTAS_NUEVAS.items():
    _chk("Cuenta fuera del catalogo",
         f"La cuenta {_cta_nueva} no esta en CUENTAS_CONCEPTO; se clasifico "
         f"como '{_info['Concepto']}' por prefijo. Confirmar con Suscripcion.",
         _info["Renglones"], _info["Monto"])

_x = d[d["Concepto"] == "X"]
_chk("Renglones sin clasificar (X)",
     f"Renglones de {ANIO_FCST} que no se pudieron asignar a P/S/C; "
     "excluidos de las cifras. Revisar con Suscripcion.",
     len(_x), _x["Monto"].sum())

_n = d[d["Concepto"] == "N"]
if len(_n):
    _chk("Bloques neutros (suma cero)",
         "Corridas cuya suma es cero: no afectan cifras.", len(_n), 0)

_pp = d[(d["Concepto"] == "P") & (d["Monto"] > TOL)]
_chk("Primas con signo invertido",
     f"Renglones positivos en cuentas de prima en {ANIO_FCST} "
     "(ajustes o devoluciones); restan prima.",
     len(_pp), _pp["Monto"].sum())

_sn = d[(d["Concepto"].isin(["S", "C"])) & (d["Monto"] < -TOL)]
_chk("Siniestros/comisiones negativos",
     f"Renglones negativos en cuentas de siniestros o comisiones en "
     f"{ANIO_FCST} (recuperos o ajustes); restan gasto.",
     len(_sn), _sn["Monto"].sum())

_at = df[df["Monto"].abs() > MONTO_ATIPICO]
_chk("Montos atipicos (> {:,.0f} M)".format(MONTO_ATIPICO / 1e6),
     "Renglones individuales gigantes; anios: "
     + ", ".join(str(a) for a in sorted(_at["Anio"].unique())) if len(_at) else
     "Sin renglones por encima del umbral.",
     len(_at), _at["Monto"].sum())

_fa = df[~df["Anio"].between(ANIO_FCST - 1, ANIO_FCST + 8)]
_chk("Anios fuera de rango",
     f"Renglones con ejercicio fiscal fuera de {ANIO_FCST - 1}-{ANIO_FCST + 8}.",
     len(_fa), _fa["Monto"].sum())

# Negocios con siniestros o comisiones pero sin prima
_por_neg = d_ok.pivot_table(index=["LN", "Cedente", "Contrato"],
                            columns="Concepto", values="Valor",
                            aggfunc="sum").fillna(0)
for c in ("P", "S", "C"):
    if c not in _por_neg.columns:
        _por_neg[c] = 0.0
_sin_prima = _por_neg[(_por_neg["P"].abs() <= TOL)
                      & ((_por_neg["S"].abs() > TOL) | (_por_neg["C"].abs() > TOL))]
_chk("Negocios con S/C sin prima",
     f"Negocios de {ANIO_FCST} con siniestros o comisiones y prima cero.",
     len(_sin_prima), (_sin_prima["S"] + _sin_prima["C"]).sum())

# =====================================================
# COMPARATIVO RFCST 2026 (opcional)
# =====================================================


def _norm_ln(v):
    """Normaliza la LN a la clave corta: LN04001 / 4001 / 4001.0 -> '4001'."""
    if pd.isna(v):
        return ""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.replace("LN0", "").lstrip("0") or s


def cargar_rfcst26():
    """Agrega la base BD_RFCST26 por LN y por cedente para el
    comparativo. Devuelve None si no esta disponible."""
    ruta = _buscar_archivo(ARCHIVO_RFCST, PREFIJO_RFCST, ".xlsx")

    if ruta is None:
        print(f"AVISO: no se encontro {ARCHIVO_RFCST} ni {PREFIJO_RFCST}*.xlsx;")
        print("       las comparativas vs RFCST 2026 apareceran como s/d.")
        return None

    try:
        crudo = pd.read_excel(ruta, sheet_name=HOJA_RFCST, header=None, nrows=8)
    except ValueError:
        print(f"AVISO: {os.path.basename(ruta)} no tiene la hoja '{HOJA_RFCST}'; "
              "comparativas vs RFCST como s/d.")
        return None

    fila = None
    for i in range(len(crudo)):
        if any(str(v).strip() == "LN" for v in crudo.iloc[i]):
            fila = i
            break
    if fila is None:
        print(f"AVISO: no se encontro la fila de encabezados (LN) en {HOJA_RFCST}.")
        return None

    b = pd.read_excel(ruta, sheet_name=HOJA_RFCST, header=fila)
    b.columns = [str(c).strip() for c in b.columns]

    if "Compañía_Nombre" not in b.columns and "Compañía.1" in b.columns:
        b = b.rename(columns={"Compañía": "Compañía_Nombre", "Compañía.1": "Compañía"})

    b = b[b["LN"].notna()].copy()
    b["_LN"] = b["LN"].map(_norm_ln)

    # RFCST usa "Costos"; aqui el concepto equivalente son
    # las comisiones (costos de adquisicion)
    cols_map = {"Primas": "P", "Siniestros": "S", "Costos": "C"}

    # 1226 / PPTO1226 / 1225 alimentan los niveles; los cortes
    # 0726 y 08-1226 (y sus equivalentes de presupuesto) dan el
    # unico perfil de estacionalidad que trae la base: la base del
    # RFCST no esta mensualizada, solo separa Ene-Jul y Ago-Dic
    sufijos = ["1226", "PPTO1226", "1225",
               "0726", "08-1226", "PPTO01-0726", "PPTO08-1226"]

    # La base original no siempre trae el incremento Ago-Dic en
    # columnas propias: se deriva como acumulado Dic menos Jul
    for medida in cols_map:
        if f"{medida} 08-1226" not in b.columns and f"{medida} 0726" in b.columns:
            b[f"{medida} 08-1226"] = (
                pd.to_numeric(b[f"{medida} 1226"], errors="coerce").fillna(0)
                - pd.to_numeric(b[f"{medida} 0726"], errors="coerce").fillna(0)
            )

    datos = {}
    for medida, corto in cols_map.items():
        for suf in sufijos:
            col = f"{medida} {suf}"
            if col in b.columns:
                datos[f"{corto}_{suf}"] = pd.to_numeric(b[col], errors="coerce").fillna(0)
            else:
                datos[f"{corto}_{suf}"] = pd.Series(0.0, index=b.index)

    t = pd.DataFrame(datos)
    t["_LN"] = b["_LN"]

    por_ln = t.groupby("_LN").sum()

    # Agregados por negocio (LN, cedente, contrato) para comparar
    # cada negocio del FCST 2027 contra su equivalente 2026
    por_negocio = {}
    if "Num Contrato" in b.columns and "Compañía" in b.columns:
        _ced = pd.to_numeric(b["Compañía"], errors="coerce")
        _cto = pd.to_numeric(b["Num Contrato"], errors="coerce")
        _ok = _ced.notna() & _cto.notna()

        _bloques = {"rfcst": "1226", "ppto": "PPTO1226", "real25": "1225"}
        _tmp = pd.DataFrame({
            "_ln": b.loc[_ok, "_LN"],
            "_ced": _ced[_ok].astype(np.int64),
            "_cto": _cto[_ok].astype(np.int64),
        })
        for _blq, _suf in _bloques.items():
            for _cpt in ("P", "S", "C"):
                _tmp[f"{_blq}_{_cpt}"] = datos[f"{_cpt}_{_suf}"].loc[_ok].to_numpy()

        _agg = _tmp.groupby(["_ln", "_ced", "_cto"]).sum()
        for _llave, _fila in _agg.iterrows():
            por_negocio[_llave] = {
                blq: {cpt: float(_fila[f"{blq}_{cpt}"]) for cpt in ("P", "S", "C")}
                for blq in _bloques
            }
        print(f"  negocios con llave LN/cedente/contrato: {len(por_negocio):,}")

    # Nombre de cedente que trae la propia base del RFCST
    nombres_ced = {}
    if "Compañía_Nombre" in b.columns and "Compañía" in b.columns:
        _n = pd.to_numeric(b["Compañía"], errors="coerce")
        for _num, _nom in zip(_n, b["Compañía_Nombre"]):
            if pd.notna(_num) and pd.notna(_nom):
                nombres_ced.setdefault(str(int(_num)), str(_nom).strip())

    por_ced = {}
    if "Compañía" in b.columns:
        nums = pd.to_numeric(b["Compañía"], errors="coerce")
        sub = pd.DataFrame({"ced": nums, "p": datos["P_1226"]})
        sub = sub[sub["ced"].notna()]
        por_ced = (sub.groupby(sub["ced"].astype(np.int64))["p"].sum()).to_dict()
        por_ced = {int(k): float(v) for k, v in por_ced.items()}

    print(f"RFCST 2026 cargado de {os.path.basename(ruta)}: "
          f"{len(b):,} registros · {por_ln.index.nunique()} LN · "
          f"{len(por_ced):,} cedentes")
    print(f"  Prima RFCST Dic26 {por_ln['P_1226'].sum() / 1e6:,.1f} M · "
          f"{ETIQ_PPTO26} {por_ln['P_PPTO1226'].sum() / 1e6:,.1f} M · "
          f"Real25 {por_ln['P_1225'].sum() / 1e6:,.1f} M")

    return {"por_ln": por_ln, "por_ced": por_ced,
            "por_negocio": por_negocio, "nombres_ced": nombres_ced,
            "archivo": os.path.basename(ruta)}


def _buscar_columna(cols, candidatas):
    """Primera columna cuyo nombre coincida con las candidatas."""
    norm = {str(c).strip().upper(): c for c in cols}
    for cand in candidatas:
        if cand.strip().upper() in norm:
            return norm[cand.strip().upper()]
    return None


def _mensual_por_ln(b, col_ln, meses, cols_medida, etiqueta):
    """{LN: {concepto: [12 montos]}} mas el total, a partir de una
    base con una fila por movimiento y su mes."""
    ln = b[col_ln].map(_norm_ln)

    out = {}
    for cpt, col in cols_medida.items():
        if col not in b.columns:
            print(f"AVISO: a {etiqueta} le falta la columna '{col}'.")
            continue
        vals = pd.to_numeric(b[col], errors="coerce").fillna(0)
        tabla = (pd.DataFrame({"_ln": ln, "_mes": meses, "_v": vals})
                 .pivot_table(index="_ln", columns="_mes", values="_v",
                              aggfunc="sum", fill_value=0.0))
        for m in range(1, 13):
            if m not in tabla.columns:
                tabla[m] = 0.0
        tabla = tabla[[m for m in range(1, 13)]]

        for clave, fila in tabla.iterrows():
            out.setdefault(clave, {})[cpt] = [float(v) for v in fila]
        out.setdefault("_tot", {})[cpt] = [float(v) for v in tabla.sum()]

    return out


def cargar_real26():
    """Real 2026 mensual (Ene-Jul) por LN y concepto. Da la forma
    con la que se abre el acumulado a julio del RFCST 2026."""

    ruta = _buscar_archivo(ARCHIVO_REAL26, PREFIJO_REAL26, ".xlsx")

    if ruta is None:
        print(f"AVISO: no se encontro {ARCHIVO_REAL26}; la estacionalidad del")
        print("       RFCST 2026 usara un perfil plano Ene-Jul / Ago-Dic.")
        return None

    try:
        crudo = pd.read_excel(ruta, sheet_name=HOJA_REAL26, header=None, nrows=8)
    except ValueError:
        print(f"AVISO: {os.path.basename(ruta)} no tiene la hoja '{HOJA_REAL26}'.")
        return None

    fila = None
    for i in range(len(crudo)):
        if any(str(v).strip() == "Periodo" for v in crudo.iloc[i]):
            fila = i
            break
    if fila is None:
        print(f"AVISO: no se encontro la columna 'Periodo' en {HOJA_REAL26}.")
        return None

    b = pd.read_excel(ruta, sheet_name=HOJA_REAL26, header=fila)
    b.columns = [str(c).strip() for c in b.columns]

    col_ln = _buscar_columna(b.columns, COL_REAL26_LN)
    if col_ln is None:
        print(f"AVISO: no se encontro la columna de LN {COL_REAL26_LN} en {HOJA_REAL26}.")
        return None

    per = pd.to_numeric(b["Periodo"], errors="coerce")
    b = b[(per // 100) == ANIO_REAL26].copy()
    meses = (per % 100).loc[b.index]

    datos = _mensual_por_ln(b, col_ln, meses, COL_REAL26,
                            f"{os.path.basename(ruta)} · {HOJA_REAL26}")

    # Acumulado por negocio, para el reporte de alertas
    por_negocio = {}
    if "Num Contrato" in b.columns and "Compañía" in b.columns:
        _ced = pd.to_numeric(b["Compañía"], errors="coerce")
        _cto = pd.to_numeric(b["Num Contrato"], errors="coerce")
        _ok = _ced.notna() & _cto.notna()
        _tmp = pd.DataFrame({
            "_ln": b.loc[_ok, col_ln].map(_norm_ln),
            "_ced": _ced[_ok].astype(np.int64),
            "_cto": _cto[_ok].astype(np.int64),
        })
        for _cpt, _col in COL_REAL26.items():
            _tmp[_cpt] = pd.to_numeric(b.loc[_ok, _col], errors="coerce").fillna(0).to_numpy()
        _agg = _tmp.groupby(["_ln", "_ced", "_cto"]).sum()
        por_negocio = {k: {c: float(v[c]) for c in ("P", "S", "C")}
                       for k, v in _agg.iterrows()}

    obs = sorted({int(m) for m in meses.dropna().unique()})
    tot = datos.get("_tot", {}).get("P", [0] * 12)
    print(f"Real {ANIO_REAL26} mensual ({os.path.basename(ruta)}): "
          f"meses {obs[0]}-{obs[-1]} · primas {sum(tot) / 1e6:,.1f} M")

    return {"por_ln": datos, "meses": obs, "por_negocio": por_negocio,
            "archivo": os.path.basename(ruta)}


def cargar_ppto26():
    """Presupuesto 2026 mensual (hoja Ppto2026 del libro del RFCST):
    12 meses abiertos, asi que la estacionalidad del FCST 2026 sale
    directa, sin ajustes."""

    ruta = _buscar_archivo(ARCHIVO_RFCST, PREFIJO_RFCST, ".xlsx")

    if ruta is None:
        return None

    try:
        crudo = pd.read_excel(ruta, sheet_name=HOJA_PPTO26, header=None, nrows=12)
    except ValueError:
        print(f"AVISO: el libro del RFCST no tiene la hoja '{HOJA_PPTO26}'; la")
        print("       estacionalidad del FCST 2026 usara un perfil plano.")
        return None

    fila = None
    for i in range(len(crudo)):
        if any(str(v).strip() == COL_PPTO26["P"] for v in crudo.iloc[i]):
            fila = i
            break
    if fila is None:
        print(f"AVISO: no se encontro '{COL_PPTO26['P']}' en la hoja {HOJA_PPTO26}.")
        return None

    b = pd.read_excel(ruta, sheet_name=HOJA_PPTO26, header=fila)
    b.columns = [str(c).strip() for c in b.columns]

    col_ln = _buscar_columna(b.columns, COL_PPTO26_LN)
    col_anio = _buscar_columna(b.columns, COL_PPTO26_ANIO)
    col_mes = _buscar_columna(b.columns, COL_PPTO26_MES)

    if col_ln is None or col_mes is None:
        print(f"AVISO: a la hoja {HOJA_PPTO26} le falta la columna de LN o de mes.")
        return None

    if col_anio is not None:
        anios = pd.to_numeric(b[col_anio], errors="coerce")
        b = b[anios == ANIO_REAL26].copy()

    mes = pd.to_numeric(b[col_mes], errors="coerce")
    if mes.max() and mes.max() > 12:          # viene como AAAAMM
        mes = mes % 100

    datos = _mensual_por_ln(b, col_ln, mes, COL_PPTO26,
                            f"{os.path.basename(ruta)} · {HOJA_PPTO26}")

    tot = datos.get("_tot", {}).get("P", [0] * 12)
    print(f"Ppto {ANIO_REAL26} mensual (hoja {HOJA_PPTO26}): "
          f"12 meses · primas {sum(tot) / 1e6:,.1f} M")

    return {"por_ln": datos, "archivo": f"{os.path.basename(ruta)} · {HOJA_PPTO26}"}


RFCST = cargar_rfcst26()

REAL26 = cargar_real26()

PPTO26 = cargar_ppto26() if RFCST is not None else None

FUENTE_RFCST = RFCST["archivo"] if RFCST else "no disponible (s/d)"


def cargar_catalogo_cedentes():
    """Diccionario numero de cedente -> nombre. Vacio si el
    catalogo no esta disponible (el dashboard muestra el numero)."""
    ruta = _buscar_archivo(ARCHIVO_CATALOGO + ".xlsx", ARCHIVO_CATALOGO, ".xlsx")

    if ruta is None:
        print("AVISO: sin catalogo de cedentes; el dashboard muestra numeros.")
        return {}

    try:
        crudo = pd.read_excel(ruta, sheet_name=HOJA_CATALOGO, header=None, nrows=6)
        fila = None
        for i in range(len(crudo)):
            if any(str(x).strip() == COL_CAT_NUM for x in crudo.iloc[i]):
                fila = i
                break
        if fila is None:
            print(f"AVISO: no se pudo leer el catalogo de {os.path.basename(ruta)}.")
            return {}
        c = pd.read_excel(ruta, sheet_name=HOJA_CATALOGO, header=fila)
        c.columns = [str(x).strip() for x in c.columns]
        if COL_CAT_NUM not in c.columns or COL_CAT_NOMBRE not in c.columns:
            return {}
        num = pd.to_numeric(c[COL_CAT_NUM], errors="coerce")
        ok = num.notna() & c[COL_CAT_NOMBRE].notna()
        cat = {str(int(k)): str(v).strip()
               for k, v in zip(num[ok], c.loc[ok, COL_CAT_NOMBRE])}
        print(f"Catalogo de cedentes: {len(cat):,} numeros ({os.path.basename(ruta)})")
        return cat
    except Exception as e:
        print(f"AVISO: error leyendo el catalogo ({e}).")
        return {}


CATALOGO_CED = cargar_catalogo_cedentes()

# =====================================================
# VISTA RETENIDO
# =====================================================

if COL_VISTA_RETENIDO in ("Flag_A", "Flag_C"):
    _flag = pd.to_numeric(d_ok[COL_VISTA_RETENIDO], errors="coerce")
    d_ok["_ret"] = np.where(_flag == VALOR_RETENIDO, 1.0, 0.0)
    RETENIDO_MODO = f"bandera {COL_VISTA_RETENIDO} == {VALOR_RETENIDO}"
    RETENIDO_REAL = True
elif RETENCION_LN:
    d_ok["_ret"] = d_ok["LN"].map(RETENCION_LN).fillna(1.0)
    RETENIDO_MODO = "% de retencion capturado por LN (RETENCION_LN)"
    RETENIDO_REAL = True
else:
    d_ok["_ret"] = 1.0
    RETENIDO_MODO = ("sin marca de retencion en la base: retenido = tomado "
                     "(configurar COL_VISTA_RETENIDO o RETENCION_LN)")
    RETENIDO_REAL = False

d_ok["Valor_Ret"] = d_ok["Valor"] * d_ok["_ret"]

print(f"Vista retenido: {RETENIDO_MODO}")

# Retencion implicita de las banderas candidatas (documentacion)
ret_candidatas = []
for flag in ("Flag_A", "Flag_C"):
    fv = pd.to_numeric(d_ok[flag], errors="coerce")
    for cpt in ("P", "S", "C"):
        sub = d_ok[d_ok["Concepto"] == cpt]
        tot = sub["Valor"].sum()
        ret = sub.loc[fv.reindex(sub.index) == VALOR_RETENIDO, "Valor"].sum()
        ret_candidatas.append({
            "Bandera": flag, "Concepto": CLAVE_MEDIDA[cpt],
            f"Total {ANIO_FCST}": tot, f"Con bandera={VALOR_RETENIDO}": ret,
            "Retencion implicita": ret / tot if abs(tot) > TOL else np.nan,
        })
ret_candidatas = pd.DataFrame(ret_candidatas)

# =====================================================
# AGREGADOS: GLOBAL Y ESTACIONALIDAD
# =====================================================


def _ratio(num, den, min_den=TOL):
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    return np.where(np.abs(den) > min_den, num / np.where(den == 0, np.nan, den), np.nan)


def _rat(num, den, min_den=TOL):
    if den is None or num is None:
        return float("nan")
    return num / den if abs(den) > min_den else float("nan")


def agregado(sub, col_valor):
    """Anual y por mes (1-12) por concepto P/S/C sobre col_valor."""
    out = {}
    for cpt in ("P", "S", "C"):
        s = sub[sub["Concepto"] == cpt]
        anual = float(s[col_valor].sum())
        por_mes = s.groupby("Mes")[col_valor].sum()
        meses = [float(por_mes.get(m, 0.0)) for m in range(1, 13)]
        out[cpt] = {"anual": anual, "meses": meses}
    out["PSC"] = {
        "anual": out["P"]["anual"] - out["S"]["anual"] - out["C"]["anual"],
        "meses": [out["P"]["meses"][i] - out["S"]["meses"][i] - out["C"]["meses"][i]
                  for i in range(12)],
    }
    return out


GLOB_T = agregado(d_ok, "Valor")
GLOB_R = agregado(d_ok, "Valor_Ret")

# Comparativo global RFCST
if RFCST is not None:
    t = RFCST["por_ln"]
    RF_GLOB = {c: {"fcst": float(t[f"{c}_1226"].sum()),
                   "ppto": float(t[f"{c}_PPTO1226"].sum()),
                   "real25": float(t[f"{c}_1225"].sum())}
               for c in ("P", "S", "C")}
    RF_GLOB["PSC"] = {k: RF_GLOB["P"][k] - RF_GLOB["S"][k] - RF_GLOB["C"][k]
                      for k in ("fcst", "ppto", "real25")}
else:
    RF_GLOB = None

# =====================================================
# AGREGADOS POR LN
# =====================================================

LNS = sorted(d_ok["LN"].unique(), key=lambda v: (len(v), v))


def resumen_ln():
    filas = []
    for ln in LNS:
        sub = d_ok[d_ok["LN"] == ln]
        g = agregado(sub, "Valor")
        gr = agregado(sub, "Valor_Ret")
        fila = {"LN": ln,
                "Primas": g["P"]["anual"], "Siniestros": g["S"]["anual"],
                "Comisiones": g["C"]["anual"], "P_S_C": g["PSC"]["anual"],
                "Primas_Ret": gr["P"]["anual"], "Siniestros_Ret": gr["S"]["anual"],
                "Comisiones_Ret": gr["C"]["anual"], "P_S_C_Ret": gr["PSC"]["anual"]}
        fila["Ind_Sin"] = _rat(fila["Siniestros"], fila["Primas"])
        fila["Ind_Cos"] = _rat(fila["Comisiones"], fila["Primas"])
        fila["Pct_P_S_C"] = _rat(fila["P_S_C"], fila["Primas"])

        # estacionalidad de la prima: mes pico y concentracion
        mm = g["P"]["meses"]
        tot = sum(mm)
        if abs(tot) > TOL:
            shares = [m / tot for m in mm]
            pico = int(np.argmax(shares))
            fila["Mes_Pico"] = MESES_TXT[pico]
            fila["Pct_Mes_Pico"] = shares[pico]
            fila["Meses_Sin_Prima"] = sum(1 for s in shares if abs(s) < 1e-6)
        else:
            fila["Mes_Pico"] = ""
            fila["Pct_Mes_Pico"] = np.nan
            fila["Meses_Sin_Prima"] = 12

        if RFCST is not None and ln in RFCST["por_ln"].index:
            r = RFCST["por_ln"].loc[ln]
            fila["Primas_RFCST26"] = r["P_1226"]
            fila["Siniestros_RFCST26"] = r["S_1226"]
            fila["Comisiones_RFCST26"] = r["C_1226"]
            fila["Primas_FCST26"] = r["P_PPTO1226"]
            fila["Siniestros_FCST26"] = r["S_PPTO1226"]
            fila["Comisiones_FCST26"] = r["C_PPTO1226"]
            fila["Primas_Real25"] = r["P_1225"]
            fila["Siniestros_Real25"] = r["S_1225"]
            fila["Comisiones_Real25"] = r["C_1225"]
        else:
            for c in ("Primas_RFCST26", "Siniestros_RFCST26", "Comisiones_RFCST26",
                      "Primas_FCST26", "Siniestros_FCST26", "Comisiones_FCST26",
                      "Primas_Real25", "Siniestros_Real25", "Comisiones_Real25"):
                fila[c] = np.nan

        fila["P_S_C_RFCST26"] = (fila["Primas_RFCST26"] - fila["Siniestros_RFCST26"]
                                 - fila["Comisiones_RFCST26"])
        fila["Crec_vs_RFCST"] = _rat(fila["Primas"], fila["Primas_RFCST26"],
                                     MATERIALIDAD) - 1 \
            if pd.notna(fila["Primas_RFCST26"]) else np.nan
        fila["Ind_Sin_RFCST"] = _rat(fila["Siniestros_RFCST26"], fila["Primas_RFCST26"])
        fila["Ind_Cos_RFCST"] = _rat(fila["Comisiones_RFCST26"], fila["Primas_RFCST26"])
        fila["Pct_P_S_C_RFCST"] = _rat(fila["P_S_C_RFCST26"], fila["Primas_RFCST26"])

        filas.append(fila)
    return pd.DataFrame(filas)


r_ln = resumen_ln()

r_ln["Participacion_FCST27"] = r_ln["Primas"] / r_ln["Primas"].sum()
if RFCST is not None:
    _tot_rf = r_ln["Primas_RFCST26"].sum()
    r_ln["Participacion_RFCST26"] = r_ln["Primas_RFCST26"] / _tot_rf if _tot_rf else np.nan
else:
    r_ln["Participacion_RFCST26"] = np.nan

# =====================================================
# SEMAFOROS Y SCORE POR LN
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


def semaforo_concentracion(x):
    if pd.isna(x):
        return "SIN DATO"
    if x > CONC_ROJO:
        return "ROJO"
    elif x > CONC_AMARILLO:
        return "AMARILLO"
    else:
        return "VERDE"


r_ln["Semaforo_Crec"] = r_ln["Crec_vs_RFCST"].apply(semaforo_desviacion)
r_ln["Semaforo_Sin"] = r_ln["Ind_Sin"].apply(semaforo_sin)
r_ln["Semaforo_Cos"] = r_ln["Ind_Cos"].apply(semaforo_costos)
r_ln["Semaforo_Est"] = r_ln["Pct_Mes_Pico"].apply(semaforo_concentracion)


def _score(serie, tope):
    s = serie.abs().fillna(tope) / tope
    return np.minimum(s, 1.0) * 100


# Sin base RFCST el crecimiento no se puede evaluar: no se
# castiga a todas las LN con score maximo por dato faltante
if RFCST is None:
    r_ln["Score_Crec"] = 0.0
else:
    r_ln["Score_Crec"] = _score(r_ln["Crec_vs_RFCST"], tope=0.60)
r_ln["Score_Sin"] = np.minimum(r_ln["Ind_Sin"].fillna(1.0).clip(lower=0), 1.2) / 1.2 * 100
r_ln["Score_Cos"] = np.minimum(r_ln["Ind_Cos"].fillna(0.6).clip(lower=0), 0.6) / 0.6 * 100
r_ln["Score_Est"] = _score(r_ln["Pct_Mes_Pico"], tope=0.80)

r_ln["Score_Total"] = (
    r_ln["Score_Crec"] * PESO_CREC
    + r_ln["Score_Sin"] * PESO_SIN
    + r_ln["Score_Cos"] * PESO_COS
    + r_ln["Score_Est"] * PESO_EST
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


r_ln["Nivel_Riesgo"] = r_ln["Score_Total"].apply(nivel_riesgo)

ranking = r_ln.sort_values("Score_Total", ascending=False).reset_index(drop=True)
ranking["Ranking"] = ranking.index + 1

# =====================================================
# ESTACIONALIDAD POR LN (para dashboard y Excel)
# =====================================================


def estacionalidad(sub):
    """% del anio por mes para P, S y C (None si no hay base)."""
    out = {}
    for cpt in ("P", "S", "C"):
        s = sub[sub["Concepto"] == cpt]
        por_mes = s.groupby("Mes")["Valor"].sum()
        vals = np.array([float(por_mes.get(m, 0.0)) for m in range(1, 13)])
        tot = vals.sum()
        out[cpt] = list(np.round(vals / tot, 4)) if abs(tot) > TOL else None
    return out


SEASON = {"_tot": estacionalidad(d_ok)}
for ln in LNS:
    SEASON[ln] = estacionalidad(d_ok[d_ok["LN"] == ln])

est_filas = []
for ln in ["_tot"] + LNS:
    for cpt in ("P", "S", "C"):
        v = SEASON[ln][cpt]
        fila = {"LN": "Total" if ln == "_tot" else ln,
                "Concepto": CLAVE_MEDIDA[cpt]}
        for i, mes in enumerate(MESES_TXT):
            fila[mes] = v[i] if v else np.nan
        est_filas.append(fila)
est_ln = pd.DataFrame(est_filas)

# =====================================================
# ESTACIONALIDAD 2026 (RFCST 2026 y FCST 2026)
# =====================================================
# FCST 2026: la hoja Ppto2026 trae los 12 meses abiertos, asi que
#   su estacionalidad es directa.
# RFCST 2026: la base no esta mensualizada. Ene-Jul se abre con la
#   forma del real 2026 (escalada al acumulado a julio del propio
#   RFCST, para que el perfil sume su total) y Ago-Dic se reparte
#   con la mensualizacion que Suscripcion le dio al FCST 2027.
#   Ese ajuste se declara al pie de la grafica.


def _forma(vals):
    """Reparte una lista de valores como shares que suman 1.
    Sirve tanto para montos como para perfiles ya porcentuales, asi
    que la tolerancia es relativa (TOL esta en dolares y aqui la
    suma puede ser una fraccion). Devuelve None cuando el total se
    cancela y el reparto seria ruido."""
    if not vals:
        return None
    tot = sum(vals)
    escala = max(abs(v) for v in vals)
    if not math.isfinite(tot) or abs(tot) <= 1e-12 or abs(tot) < 1e-6 * escala:
        return None
    return [v / tot for v in vals]


def _meses_de(fuente, ln, cpt):
    """Montos mensuales de una base cargada, con caida al total."""
    if fuente is None:
        return None
    por_ln = fuente["por_ln"]
    fila = por_ln.get(ln)
    if not fila or cpt not in fila:
        return None
    return fila[cpt]


IDX_ENEJUL = [m - 1 for m in MESES_ENEJUL]
IDX_AGODIC = [m - 1 for m in MESES_AGODIC]


def perfil_rfcst26(ln, cpt, fila_rf):
    """Perfil mensual del RFCST 2026 para una LN y concepto."""

    ini = float(fila_rf.get(f"{cpt}_0726", 0.0))          # acumulado a julio
    fin = float(fila_rf.get(f"{cpt}_08-1226", 0.0))       # incremento Ago-Dic
    if abs(ini + fin) <= TOL:
        return None

    # Ene-Jul: forma del real 2026 observado; si no hay, plana
    real = _meses_de(REAL26, ln, cpt) or _meses_de(REAL26, "_tot", cpt)
    forma_ini = _forma([real[i] for i in IDX_ENEJUL]) if real else None
    if forma_ini is None:
        forma_ini = [1 / len(IDX_ENEJUL)] * len(IDX_ENEJUL)

    # Ago-Dic: mensualizacion que trae el propio FCST 2027
    f27 = SEASON.get(ln, {}).get(cpt) or SEASON["_tot"].get(cpt)
    forma_fin = _forma([f27[i] for i in IDX_AGODIC]) if f27 else None
    if forma_fin is None:
        forma_fin = [1 / len(IDX_AGODIC)] * len(IDX_AGODIC)

    meses = [0.0] * 12
    for k, i in enumerate(IDX_ENEJUL):
        meses[i] = ini * forma_ini[k]
    for k, i in enumerate(IDX_AGODIC):
        meses[i] = fin * forma_fin[k]

    forma = _forma(meses)
    return [round(v, 4) for v in forma] if forma else None


def perfil_ppto26(ln, cpt, fila_rf):
    """Perfil mensual del FCST 2026 (hoja Ppto2026, 12 meses)."""

    meses = _meses_de(PPTO26, ln, cpt)
    forma = _forma(meses) if meses else None

    if forma is None:
        # Sin la hoja mensual: perfil plano por bloques del ppto
        ini = float(fila_rf.get(f"{cpt}_PPTO01-0726", 0.0))
        fin = float(fila_rf.get(f"{cpt}_PPTO08-1226", 0.0))
        if abs(ini + fin) <= TOL:
            return None
        meses = ([ini / len(IDX_ENEJUL)] * len(IDX_ENEJUL)
                 + [fin / len(IDX_AGODIC)] * len(IDX_AGODIC))
        forma = _forma(meses)

    return [round(v, 4) for v in forma] if forma else None


SEASON26 = {}

if RFCST is not None:
    _rf_ln = RFCST["por_ln"]
    for _ln in list(_rf_ln.index) + ["_tot"]:
        _fila = _rf_ln.sum() if _ln == "_tot" else _rf_ln.loc[_ln]
        SEASON26[_ln] = {
            cpt: {"rfcst": perfil_rfcst26(_ln, cpt, _fila),
                  "ppto": perfil_ppto26(_ln, cpt, _fila)}
            for cpt in ("P", "S", "C")
        }

# El ajuste Ago-Dic solo aplica al RFCST: el FCST 2026 sale
# mensualizado de la hoja Ppto2026
AJUSTE_AGODIC = REAL26 is not None or PPTO26 is not None

FUENTE_EST26 = " · ".join(filter(None, [
    f"Ene-Jul con la forma del real 2026 ({REAL26['archivo']})" if REAL26 else None,
    f"FCST 2026 mensual de {PPTO26['archivo']}" if PPTO26 else None,
])) or "perfil plano Ene-Jul / Ago-Dic (sin bases mensuales)"

# =====================================================
# AGREGADOS POR NEGOCIO Y CEDENTE
# =====================================================

grp_neg = d_ok.groupby(["LN", "Cedente", "Contrato", "Binder_Ppto"],
                       sort=False, dropna=False)

# ---- Contrapartes 2026 / 2025 por negocio ----
RF_NEG = RFCST["por_negocio"] if RFCST else {}
RL_NEG = REAL26["por_negocio"] if REAL26 else {}
NOMBRE_CED = dict(RFCST["nombres_ced"]) if RFCST else {}
NOMBRE_CED.update(CATALOGO_CED)          # el catalogo manda si existe

VACIO = {"P": 0.0, "S": 0.0, "C": 0.0}


def _fmt_corto(v):
    """Monto compacto para los textos de motivo: 4.43 M / 544.4 k."""
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:,.2f} M"
    if a >= 1e3:
        return f"{v / 1e3:,.1f} k"
    return f"{v:,.0f}"


def _fmt_pc(v, dec=0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    return f"{v * 100:,.{dec}f}%"


def evaluar_alertas(f, rf, ppto, r25, r26, conc, mes_pico):
    """Reglas de alerta de un negocio.

    Devuelve (semaforo, motivos, celdas) donde:
      semaforo  0 verde · 1 amarillo · 2 rojo
      motivos   textos que citan los montos comparados
      celdas    columnas del reporte que se marcan en amarillo

    ROJO se reserva a inconsistencias duras en negocios materiales;
    AMARILLO a indices altos y desviaciones fuertes contra 2026.
    """

    P, S, C = f["P"], f["S"], f["C"]
    material = abs(P) > MATERIALIDAD

    motivos, celdas = [], []
    sem = 0

    def marca(nivel, texto, cols):
        nonlocal sem
        motivos.append(texto)
        celdas.extend(cols)
        sem = max(sem, nivel)

    ind_sin = _rat(S, P)
    ind_cos = _rat(C, P)

    # --- Inconsistencias duras ---
    if P < -TOL:
        marca(2 if material else 1,
              f"Prima FCST negativa ({_fmt_corto(P)})", ["P_F"])

    if abs(P) <= TOL and (abs(S) > TOL or abs(C) > TOL):
        marca(2 if (abs(S) + abs(C)) > MATERIALIDAD else 1,
              f"Siniestros/comisiones sin prima (S {_fmt_corto(S)} · "
              f"C {_fmt_corto(C)} · P {_fmt_corto(P)})",
              ["P_F", "S_F", "C_F"])

    # --- Indices tecnicos del propio forecast ---
    if not math.isnan(ind_sin):
        if ind_sin > IND_SIN_ROJO:
            marca(2 if material else 1,
                  f"Siniestralidad {_fmt_pc(ind_sin)} > {IND_SIN_ROJO:.0%} "
                  f"(S {_fmt_corto(S)} / P {_fmt_corto(P)})",
                  ["P_F", "S_F", "IND_SIN"])
        elif ind_sin > IND_SIN_AMARILLO:
            marca(1, f"Siniestralidad {_fmt_pc(ind_sin)} > {IND_SIN_AMARILLO:.0%} "
                     f"(S {_fmt_corto(S)} / P {_fmt_corto(P)})",
                  ["P_F", "S_F", "IND_SIN"])
        elif ind_sin < -0.05:
            marca(1, f"Siniestralidad negativa {_fmt_pc(ind_sin)} "
                     f"(S {_fmt_corto(S)} / P {_fmt_corto(P)})",
                  ["S_F", "IND_SIN"])

    if not math.isnan(ind_cos):
        if ind_cos > IND_COS_ROJO:
            marca(2 if material else 1,
                  f"Comisiones {_fmt_pc(ind_cos)} > {IND_COS_ROJO:.0%} "
                  f"(C {_fmt_corto(C)} / P {_fmt_corto(P)})",
                  ["P_F", "C_F", "IND_COS"])
        elif ind_cos > IND_COS_AMARILLO:
            marca(1, f"Comisiones {_fmt_pc(ind_cos)} > {IND_COS_AMARILLO:.0%} "
                     f"(C {_fmt_corto(C)} / P {_fmt_corto(P)})",
                  ["P_F", "C_F", "IND_COS"])

    if S < -RELEVANCIA:
        marca(1, f"Siniestros FCST negativos ({_fmt_corto(S)}): revisar recuperaciones",
              ["S_F"])

    # --- Contra el RFCST 2026 del mismo negocio ---
    tiene_rf = rf is not None and abs(rf["P"]) > TOL

    if tiene_rf and material:
        var_p = _rat(P, rf["P"], MATERIALIDAD) - 1
        if (not math.isnan(var_p) and abs(var_p) > UMBRAL_ROJO
                and abs(P - rf["P"]) > RELEVANCIA):
            marca(1, f"Prima {_fmt_pc(var_p)} vs RFCST 2026 "
                     f"(FCST {_fmt_corto(P)} vs RFCST {_fmt_corto(rf['P'])})",
                  ["P_F", "P_R", "VAR_P"])

        ind_sin_rf = _rat(rf["S"], rf["P"])
        if not math.isnan(ind_sin) and not math.isnan(ind_sin_rf):
            salto = ind_sin - ind_sin_rf
            # el salto tiene que mover dinero, no solo el indice
            if abs(salto) > SALTO_IND and abs(salto * P) > RELEVANCIA:
                marca(1, f"Siniestralidad {_fmt_pc(ind_sin)} vs {_fmt_pc(ind_sin_rf)} "
                         f"del RFCST 2026 ({salto * 100:+,.0f} pp · "
                         f"S {_fmt_corto(S)} vs {_fmt_corto(rf['S'])})",
                      ["S_F", "S_R", "IND_SIN", "IND_SIN_R"])

        ind_cos_rf = _rat(rf["C"], rf["P"])
        if not math.isnan(ind_cos) and not math.isnan(ind_cos_rf):
            salto = ind_cos - ind_cos_rf
            if abs(salto) > SALTO_IND and abs(salto * P) > RELEVANCIA:
                marca(1, f"Comisiones {_fmt_pc(ind_cos)} vs {_fmt_pc(ind_cos_rf)} "
                         f"del RFCST 2026 ({salto * 100:+,.0f} pp · "
                         f"C {_fmt_corto(C)} vs {_fmt_corto(rf['C'])})",
                      ["C_F", "C_R", "IND_COS", "IND_COS_R"])

    # La concentracion mensual NO levanta semaforo a nivel negocio
    # (la prima unica anual es lo normal en reaseguro); queda como
    # dato en el reporte y como senal a nivel linea de negocio

    # Nota informativa: no escala el semaforo, solo explica que el
    # negocio no tiene contra que compararse
    nota = ""
    if not tiene_rf and material:
        nota = ("Sin contraparte en el RFCST 2026 (negocio nuevo o con otra "
                "llave LN/cedente/contrato): no hay comparativo 2026")

    return sem, motivos, celdas, nota


negocios = []

for (ln, ced, cto, binder), sub in grp_neg:

    g = {}
    for cpt in ("P", "S", "C"):
        s_cpt = sub[sub["Concepto"] == cpt]
        por_mes = s_cpt.groupby("Mes")["Valor"].sum()
        g[cpt] = [round(float(por_mes.get(m, 0.0))) for m in range(1, 13)]

    f = {cpt: float(sum(g[cpt])) for cpt in ("P", "S", "C")}

    llave = (ln, int(ced), int(cto))
    rf = RF_NEG.get(llave, {}).get("rfcst") if llave in RF_NEG else None
    ppto = RF_NEG.get(llave, {}).get("ppto") if llave in RF_NEG else None
    r25 = RF_NEG.get(llave, {}).get("real25") if llave in RF_NEG else None
    r26 = RL_NEG.get(llave)

    tot_p = sum(abs(v) for v in g["P"])
    if tot_p > TOL:
        _idx = int(np.argmax([abs(v) for v in g["P"]]))
        conc = abs(g["P"][_idx]) / tot_p
        mes_pico = MESES_TXT[_idx]
    else:
        conc, mes_pico = float("nan"), ""

    sem, motivos, celdas, nota = evaluar_alertas(f, rf, ppto, r25, r26, conc, mes_pico)

    regiones = sorted(set(sub["Region"].dropna().astype(str)))
    paises = sorted(set(pd.to_numeric(sub["Pais_Cod"], errors="coerce")
                        .dropna().astype(int).astype(str)))
    corredores = sorted(set(sub["Corredor"].astype(int).astype(str)))
    monedas = sorted(set(sub["Moneda"].dropna().astype(str)))

    negocios.append({
        "LN": ln, "Cedente": int(ced), "Contrato": int(cto),
        "Binder": str(binder or "").strip(),
        "Region": "/".join(regiones), "Paises": "/".join(paises[:3]),
        "Corredores": "/".join(corredores[:3]), "Monedas": "/".join(monedas[:4]),
        "f": f, "rf": rf, "ppto": ppto, "r25": r25, "r26": r26,
        "meses": g, "conc": conc, "mes_pico": mes_pico,
        "sem": sem, "motivos": motivos, "celdas": sorted(set(celdas)),
        "nota": nota,
    })

neg_rows = [[
    n["LN"], str(n["Cedente"]), str(n["Contrato"]),
    n["Region"], n["Paises"], n["Corredores"], n["Monedas"],
    round(n["f"]["P"]), round(n["f"]["S"]), round(n["f"]["C"]),
    n["meses"]["P"], n["meses"]["S"], n["meses"]["C"],
    n["sem"], " · ".join(n["motivos"]) + ((" · " if n["motivos"] else "") + n["nota"]
                                          if n["nota"] else ""),
    n["Binder"],
] for n in negocios]

print(f"Negocios {ANIO_FCST}: {len(neg_rows):,} · "
      f"con alerta: {sum(1 for r in neg_rows if r[13] > 0):,}")

# Resumen por cedente (Excel)
ced_filas = []
for ced, sub in d_ok.groupby("Cedente"):
    g = agregado(sub, "Valor")
    P, S, C = g["P"]["anual"], g["S"]["anual"], g["C"]["anual"]
    fila = {"Cedente": int(ced),
            "Nombre": CATALOGO_CED.get(str(int(ced)), ""),
            "LNs": ", ".join(sorted(set(sub["LN"]))),
            "Negocios": sub.groupby(["LN", "Contrato"]).ngroups,
            "Primas": P, "Siniestros": S, "Comisiones": C,
            "P_S_C": P - S - C,
            "Ind_Sin": _rat(S, P), "Ind_Cos": _rat(C, P)}
    if RFCST is not None:
        rp = RFCST["por_ced"].get(int(ced))
        fila["Primas_RFCST26"] = rp if rp is not None else np.nan
        fila["Crec_vs_RFCST"] = (_rat(P, rp, MATERIALIDAD) - 1
                                 if rp is not None else np.nan)
    else:
        fila["Primas_RFCST26"] = np.nan
        fila["Crec_vs_RFCST"] = np.nan
    ced_filas.append(fila)

r_ced = (pd.DataFrame(ced_filas)
         .sort_values("Primas", ascending=False)
         .reset_index(drop=True))
r_ced["Semaforo_Crec"] = r_ced["Crec_vs_RFCST"].apply(semaforo_desviacion)
r_ced["Semaforo_Sin"] = r_ced["Ind_Sin"].apply(semaforo_sin)

# =====================================================
# RESUMEN GLOBAL (Excel / correo)
# =====================================================


def _fila_global(nombre, gt, gr, rf):
    fcst = gt["anual"]
    ret = gr["anual"]
    rfc = rf["fcst"] if rf else float("nan")
    ppt = rf["ppto"] if rf else float("nan")
    r25 = rf["real25"] if rf else float("nan")
    return {
        "Concepto": nombre,
        f"FCST Dic{str(ANIO_FCST)[2:]} Tomado": fcst,
        f"FCST Dic{str(ANIO_FCST)[2:]} Retenido": ret,
        "RFCST Dic26": rfc,
        "Var $ vs RFCST": fcst - rfc,
        "Var % vs RFCST": _rat(fcst, rfc) - 1 if not math.isnan(rfc) else float("nan"),
        ETIQ_PPTO26: ppt,
        f"Var % vs {ETIQ_PPTO26}": _rat(fcst, ppt) - 1 if not math.isnan(ppt) else float("nan"),
        "Real 2025": r25,
    }


filas_global = []
for cpt in ("P", "S", "C", "PSC"):
    nombre = CLAVE_MEDIDA.get(cpt, "P-S-C *")
    filas_global.append(_fila_global(
        nombre, GLOB_T[cpt], GLOB_R[cpt],
        RF_GLOB[cpt] if RF_GLOB else None))

pct_psc_fcst = _rat(GLOB_T["PSC"]["anual"], GLOB_T["P"]["anual"])
pct_psc_ret = _rat(GLOB_R["PSC"]["anual"], GLOB_R["P"]["anual"])
pct_psc_rf = (_rat(RF_GLOB["PSC"]["fcst"], RF_GLOB["P"]["fcst"])
              if RF_GLOB else float("nan"))
pct_psc_ppto = (_rat(RF_GLOB["PSC"]["ppto"], RF_GLOB["P"]["ppto"])
                if RF_GLOB else float("nan"))

filas_global.append({
    "Concepto": "%P-S-C *",
    f"FCST Dic{str(ANIO_FCST)[2:]} Tomado": pct_psc_fcst,
    f"FCST Dic{str(ANIO_FCST)[2:]} Retenido": pct_psc_ret,
    "RFCST Dic26": pct_psc_rf,
    "Var $ vs RFCST": float("nan"),
    "Var % vs RFCST": pct_psc_fcst - pct_psc_rf,
    ETIQ_PPTO26: pct_psc_ppto,
    f"Var % vs {ETIQ_PPTO26}": pct_psc_fcst - pct_psc_ppto,
    "Real 2025": float("nan"),
})

resumen_global = pd.DataFrame(filas_global)

# =====================================================
# DASHBOARD (KPIs para Excel)
# =====================================================

n_rojo = sum(1 for r in neg_rows if r[13] == 2)
n_amarillo = sum(1 for r in neg_rows if r[13] == 1)
n_verde = len(neg_rows) - n_rojo - n_amarillo

gp = GLOB_T["P"]["anual"]
_rf_p = RF_GLOB["P"]["fcst"] if RF_GLOB else float("nan")

dashboard = pd.DataFrame({
    "Indicador": [
        "Negocios analizados",
        "Lineas de negocio",
        "Cedentes",
        f"Prima FCST {ANIO_FCST} (tomado)",
        f"Prima FCST {ANIO_FCST} (retenido)",
        "Prima RFCST Dic 2026",
        "Crecimiento vs RFCST 2026",
        f"Siniestros FCST {ANIO_FCST}",
        f"Comisiones FCST {ANIO_FCST}",
        "Siniestralidad implicita",
        "Comisiones implicitas",
        f"P-S-C FCST {ANIO_FCST} *",
        "%P-S-C *",
        "Mes pico de prima",
        "Negocios VERDE",
        "Negocios AMARILLO",
        "Negocios ROJO",
        "LN en riesgo ALTO/CRITICO",
    ],
    "Valor": [
        len(neg_rows),
        len(LNS),
        d_ok["Cedente"].nunique(),
        gp,
        GLOB_R["P"]["anual"],
        _rf_p,
        _rat(gp, _rf_p) - 1 if not math.isnan(_rf_p) else float("nan"),
        GLOB_T["S"]["anual"],
        GLOB_T["C"]["anual"],
        _rat(GLOB_T["S"]["anual"], gp),
        _rat(GLOB_T["C"]["anual"], gp),
        GLOB_T["PSC"]["anual"],
        pct_psc_fcst,
        MESES_TXT[int(np.argmax(GLOB_T["P"]["meses"]))],
        n_verde,
        n_amarillo,
        n_rojo,
        int((r_ln["Nivel_Riesgo"].isin(["ALTO", "CRITICO"])).sum()),
    ],
})

# =====================================================
# PARAMETROS (documentacion de supuestos)
# =====================================================

parametros = pd.DataFrame({
    "Parametro": [
        "Archivo fuente", "Ejercicio validado", "Fuente RFCST 2026",
        "Vista retenido", "Tolerancia (USD)", "Materialidad (USD)",
        "Umbral amarillo desviaciones", "Umbral rojo desviaciones",
        "Siniestralidad amarilla", "Siniestralidad roja",
        "Comisiones amarillo", "Comisiones rojo",
        "Concentracion mensual amarilla", "Concentracion mensual roja",
        "Monto atipico (USD)",
        "Peso score: crecimiento vs RFCST", "Peso score: siniestralidad",
        "Peso score: comisiones", "Peso score: estacionalidad",
        "Nota P-S-C",
        "Nota conceptos",
        "Generado por", "Fecha de ejecucion",
    ],
    "Valor": [
        os.path.basename(archivo), ANIO_FCST, FUENTE_RFCST,
        RETENIDO_MODO, TOL, MATERIALIDAD,
        UMBRAL_AMARILLO, UMBRAL_ROJO,
        IND_SIN_AMARILLO, IND_SIN_ROJO,
        IND_COS_AMARILLO, IND_COS_ROJO,
        CONC_AMARILLO, CONC_ROJO,
        MONTO_ATIPICO,
        PESO_CREC, PESO_SIN, PESO_COS, PESO_EST,
        "* Falta el incremento a la reserva y los costos de cobertura",
        METODO_CONCEPTO,
        usuario, datetime.now().strftime("%Y-%m-%d %H:%M"),
    ],
    "Descripcion": [
        "CSV compartido por Suscripcion", "Anio del plan que se valida",
        "Base del RFCST 2026 para comparativas",
        "Como se calcula la vista retenido del dashboard",
        "Diferencias menores a este monto no generan alerta",
        "Negocios con prima menor a este monto no escalan a ROJO",
        "Desviacion relativa que marca AMARILLO",
        "Desviacion relativa que marca ROJO",
        "S/P del FCST > umbral marca AMARILLO",
        "S/P del FCST > umbral marca ROJO",
        "C/P del FCST > umbral marca AMARILLO",
        "C/P del FCST > umbral marca ROJO",
        "Un mes con mas de este % de la prima anual marca AMARILLO",
        "Un mes con mas de este % de la prima anual marca ROJO",
        "Renglones individuales mayores se listan en Calidad_Datos",
        "V1: crecimiento de prima vs RFCST 2026",
        "V2: siniestralidad implicita del FCST",
        "V2: comisiones implicitas del FCST",
        "V3: concentracion de la prima en el mes pico",
        "P-S-C no es resultado tecnico: no incluye reservas ni costos de cobertura",
        "Ver hoja Mapeo_Columnas y Calidad_Datos",
        "Usuario que ejecuto el script", "",
    ],
})

mapeo_doc = pd.DataFrame({
    "Posicion": list(range(N_COLUMNAS_CSV)),
    "Encabezado CSV (permutado)": ENCABEZADOS_ORIGINALES,
    "Campo asignado": [MAPEO_POSICIONAL.get(i, "(no usado)")
                       for i in range(N_COLUMNAS_CSV)],
})

calidad_df = pd.DataFrame(calidad)

# Catalogo de cuentas usado para clasificar el concepto, con lo
# que aporta cada una al ejercicio validado
if "Cuenta_Concepto" in d.columns:
    _cta_res = (d.groupby([d["Cuenta_Concepto"].astype(str), "Concepto"])["Monto"]
                .agg(["size", "sum"]).reset_index())
    _cta_res.columns = ["Cuenta", "Concepto", "Renglones", f"Monto {ANIO_FCST}"]
    _cta_res["Concepto"] = _cta_res["Concepto"].map(
        {**CLAVE_MEDIDA, "X": "SIN CLASIFICAR"})
    _cta_res["En catalogo"] = np.where(
        _cta_res["Cuenta"].isin(CUENTAS_CONCEPTO), "Si", "No (por prefijo)")
    cuentas_df = _cta_res.sort_values(f"Monto {ANIO_FCST}", key=abs, ascending=False)
else:
    cuentas_df = pd.DataFrame(
        {"Nota": ["El export de 42 columnas no trae la cuenta del concepto."]})

# =====================================================
# EXPORT EXCEL
# =====================================================

salida_xlsx = os.path.join(xOutputs, "VAL_FCST27.xlsx")

cols_ln = [
    "LN", "Primas", "Primas_RFCST26", "Crec_vs_RFCST", "Semaforo_Crec",
    "Primas_FCST26", "Primas_Real25", "Primas_Ret",
    "Siniestros", "Siniestros_RFCST26", "Ind_Sin", "Ind_Sin_RFCST", "Semaforo_Sin",
    "Comisiones", "Comisiones_RFCST26", "Ind_Cos", "Ind_Cos_RFCST", "Semaforo_Cos",
    "P_S_C", "Pct_P_S_C", "P_S_C_RFCST26", "Pct_P_S_C_RFCST",
    "Participacion_FCST27", "Participacion_RFCST26",
    "Mes_Pico", "Pct_Mes_Pico", "Meses_Sin_Prima", "Semaforo_Est",
    "Score_Total", "Nivel_Riesgo", "Ranking",
]

neg_export = pd.DataFrame(
    [r[:3] + [r[15]] + r[3:10] + [r[13], r[14]] for r in neg_rows],
    columns=["LN", "Cedente", "Contrato", "Binder Ppto", "Region", "Paises",
             "Corredores", "Monedas", "Primas", "Siniestros", "Comisiones",
             "Semaforo", "Motivos"],
)
neg_export["Nombre Cedente"] = neg_export["Cedente"].map(
    lambda c: CATALOGO_CED.get(c, ""))
neg_export["P_S_C"] = (neg_export["Primas"] - neg_export["Siniestros"]
                       - neg_export["Comisiones"])
neg_export["Ind_Sin"] = _ratio(neg_export["Siniestros"], neg_export["Primas"])
neg_export["Ind_Cos"] = _ratio(neg_export["Comisiones"], neg_export["Primas"])
neg_export["Semaforo"] = neg_export["Semaforo"].map(
    {0: "VERDE", 1: "AMARILLO", 2: "ROJO"})
neg_export = neg_export.sort_values("Primas", ascending=False)

excepciones = neg_export[neg_export["Semaforo"].isin(["ROJO", "AMARILLO"])].copy()
excepciones = excepciones.sort_values(
    ["Semaforo", "Primas"], ascending=[True, False])

with pd.ExcelWriter(salida_xlsx, engine="xlsxwriter") as writer:

    wb = writer.book

    fmt_header = wb.add_format({
        "bold": True, "font_name": "Arial", "font_size": 9,
        "font_color": "#FFFFFF", "bg_color": "#1F3864",
        "border": 1, "text_wrap": True, "valign": "vcenter",
    })
    fmt_texto = wb.add_format({"font_name": "Arial", "font_size": 9})
    fmt_moneda = wb.add_format({"font_name": "Arial", "font_size": 9,
                                "num_format": "#,##0;(#,##0);-"})
    fmt_pct = wb.add_format({"font_name": "Arial", "font_size": 9,
                             "num_format": "0.0%;(0.0%);-"})
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
                    for k in ("var %", "crec", "pct", "ind_", "retencion",
                              "participacion", "score", "%p-s-c")
                ) or nombre_l in MESES_TXT
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
        if len(tabla):
            ws.autofilter(0, 0, len(tabla), len(tabla.columns) - 1)

    exportar(dashboard, "Dashboard")
    exportar(resumen_global, "Resumen_Global")
    exportar(ranking[cols_ln], "Resumen_LN")
    exportar(est_ln, "Estacionalidad_LN")
    exportar(r_ced, "Resumen_Cedente")
    exportar(neg_export, "Resumen_Negocio")
    exportar(excepciones.head(500), "Excepciones")
    exportar(calidad_df, "Calidad_Datos")
    exportar(cuentas_df, "Cuentas_Concepto")
    exportar(ret_candidatas, "Retencion_Candidatas")
    exportar(mapeo_doc, "Mapeo_Columnas")
    exportar(parametros, "Parametros")

print(f"Excel generado: {salida_xlsx}")

# =====================================================
# REPORTE DE ALERTAS (formato del reporte del RFCST 26)
# =====================================================
# Una hoja por negocio en ROJO o AMARILLO con: identificacion,
# las cifras del FCST 2027, aquello contra lo que se compara
# (RFCST 2026, FCST 2026, real 2026 a julio y real 2025), los
# indices y desviaciones como formulas de Excel, los semaforos
# y el motivo con los montos. Las celdas que dispararon cada
# alerta van marcadas en amarillo.

salida_alertas = os.path.join(xOutputs, "Reporte_Alertas_FCST27.xlsx")

# columna logica -> (letra, indice 0-based)
COLS_REP = [
    # Identificacion
    ("LN", "Identificación"), ("N° Cedente", None), ("Cedente", None),
    ("País (cód.)", None), ("Región", None), ("Corredor", None),
    ("Num Contrato", None), ("Binder Ppto", None),
    # Cifras
    ("Primas", f"{ETIQ_FCST} · Dic {ANIO_FCST}"), ("Siniestros", None), ("Comisiones", None),
    ("Primas", "RFCST 2026 · Dic 2026"), ("Siniestros", None), ("Comisiones", None),
    ("Primas", f"{ETIQ_PPTO26} · Dic 2026"), ("Siniestros", None), ("Comisiones", None),
    ("Primas", "Real 2026 · Corte a Julio"), ("Siniestros", None), ("Comisiones", None),
    ("Primas", "Real 2025 · Dic 2025"), ("Siniestros", None), ("Comisiones", None),
    # Indices
    (f"% Sin {ETIQ_FCST}", "Índices"), (f"% Com {ETIQ_FCST}", None),
    ("% Sin RFCST 26", None), ("% Com RFCST 26", None),
    (f"%P-S-C {ETIQ_FCST}", None), ("%P-S-C RFCST 26", None),
    # Desviaciones
    ("Var Primas vs RFCST 26", "Desviaciones"), ("Var Siniestros vs RFCST 26", None),
    ("Var Comisiones vs RFCST 26", None), (f"Var Primas vs {ETIQ_PPTO26}", None),
    ("Crec. vs Real 2025", None), ("% prima en el mes pico", None),
    # Semaforos
    ("Semáforo Sin.", "Semáforos"), ("Semáforo Com.", None),
    ("Semáforo vs RFCST", None), ("Semáforo Global", None),
    # Motivo
    ("Motivo de la alerta", "Motivo"),
]

# Posiciones (0-based) de las columnas que se marcan en amarillo
MARCA_COL = {
    "P_F": 8, "S_F": 9, "C_F": 10,
    "P_R": 11, "S_R": 12, "C_R": 13,
    "IND_SIN": 23, "IND_COS": 24, "IND_SIN_R": 25, "IND_COS_R": 26,
    "VAR_P": 29, "CONC": 35,
}

REGLAS_LEYENDA = [
    ("ROJO", "Prima del FCST negativa", "< 0",
     f"{ETIQ_FCST} Primas"),
    ("ROJO", "Siniestros o comisiones sin prima", "prima = 0 y S o C ≠ 0",
     f"{ETIQ_FCST} Primas · Siniestros · Comisiones"),
    ("ROJO", "Siniestralidad implícita del forecast por encima del 100%",
     f"> {IND_SIN_ROJO:.0%}", f"{ETIQ_FCST} Primas · Siniestros · % Sin"),
    ("ROJO", "Comisiones implícitas muy por encima de la banda del portafolio",
     f"> {IND_COS_ROJO:.0%}", f"{ETIQ_FCST} Primas · Comisiones · % Com"),
    ("AMARILLO", "Siniestralidad implícita alta", f"> {IND_SIN_AMARILLO:.0%}",
     f"{ETIQ_FCST} Primas · Siniestros · % Sin"),
    ("AMARILLO", "Siniestralidad implícita negativa (revisar recuperaciones)",
     "< -5%", f"{ETIQ_FCST} Siniestros · % Sin"),
    ("AMARILLO", "Comisiones implícitas altas", f"> {IND_COS_AMARILLO:.0%}",
     f"{ETIQ_FCST} Primas · Comisiones · % Com"),
    ("AMARILLO", "Siniestros del forecast negativos",
     f"< -{RELEVANCIA:,.0f} USD", f"{ETIQ_FCST} Siniestros"),
    ("AMARILLO", "Prima muy desviada contra el mismo negocio en el RFCST 2026",
     f"|var| > {UMBRAL_ROJO:.0%} y diferencia > {RELEVANCIA:,.0f} USD",
     f"{ETIQ_FCST} Primas · RFCST Primas · Var Primas vs RFCST"),
    ("AMARILLO", "Salto de la siniestralidad contra la del mismo negocio en el RFCST 2026",
     f"> {SALTO_IND:.0%} pp y con impacto > {RELEVANCIA:,.0f} USD",
     f"{ETIQ_FCST} Siniestros · RFCST Siniestros · % Sin (ambos)"),
    ("AMARILLO", "Salto de las comisiones contra las del mismo negocio en el RFCST 2026",
     f"> {SALTO_IND:.0%} pp y con impacto > {RELEVANCIA:,.0f} USD",
     f"{ETIQ_FCST} Comisiones · RFCST Comisiones · % Com (ambos)"),
]


def _v(bloque, cpt):
    """Monto del bloque comparativo, o None si no hay contraparte."""
    if not bloque:
        return None
    v = bloque.get(cpt)
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return float(v)


def generar_reporte_alertas(ruta, filas):

    wb = xlsxwriter.Workbook(ruta, {"nan_inf_to_errors": True})
    ws = wb.add_worksheet("Alertas")

    base = {"font_name": "Arial", "font_size": 9}
    f_grupo = {c: wb.add_format({**base, "bold": True, "font_color": "#FFFFFF",
                                 "bg_color": c, "align": "center", "border": 1})
               for c in ("#5B3C8A", "#1F3864", "#2E5E4E", "#3C3C3C")}
    f_head = wb.add_format({**base, "bold": True, "bg_color": "#D9E1F2",
                            "border": 1, "text_wrap": True, "valign": "vcenter",
                            "align": "center"})
    f_txt = wb.add_format(base)
    f_num = wb.add_format({**base, "num_format": "#,##0;(#,##0);-"})
    f_pct = wb.add_format({**base, "num_format": "0.0%;(0.0%);-"})
    f_num_m = wb.add_format({**base, "num_format": "#,##0;(#,##0);-",
                             "bg_color": "#FFEB9C", "bold": True})
    f_pct_m = wb.add_format({**base, "num_format": "0.0%;(0.0%);-",
                             "bg_color": "#FFEB9C", "bold": True})
    f_motivo = wb.add_format({**base, "text_wrap": True, "valign": "top"})

    # Color del grupo por tramo de columnas
    color_grupo = ["#5B3C8A"] * 8 + ["#1F3864"] * 15 + ["#2E5E4E"] * 12 \
        + ["#3C3C3C"] * 4 + ["#1F3864"]

    # Fila 1: encabezados de grupo (combinados)
    ini = 0
    for i, (_, grupo) in enumerate(COLS_REP):
        if grupo is None and i > 0:
            continue
        fin = i
        while fin + 1 < len(COLS_REP) and COLS_REP[fin + 1][1] is None:
            fin += 1
        if fin > ini or True:
            texto = grupo or ""
            if fin > i:
                ws.merge_range(0, i, 0, fin, texto, f_grupo[color_grupo[i]])
            else:
                ws.write(0, i, texto, f_grupo[color_grupo[i]])
        ini = fin + 1

    # Fila 2: encabezados de columna
    for i, (nombre, _) in enumerate(COLS_REP):
        ws.write(1, i, nombre, f_head)

    es_pct = set(range(23, 36))          # indices y desviaciones

    for j, n in enumerate(filas):
        r = j + 2                        # fila 0-based en la hoja
        e = r + 1                        # fila 1-based para las formulas
        marcadas = {MARCA_COL[c] for c in n["celdas"] if c in MARCA_COL}

        def fmt(col):
            if col in marcadas:
                return f_pct_m if col in es_pct else f_num_m
            return f_pct if col in es_pct else f_num

        ident = [n["LN"], n["Cedente"], NOMBRE_CED.get(str(n["Cedente"]), ""),
                 n["Paises"], n["Region"], n["Corredores"], n["Contrato"],
                 n["Binder"]]
        for i, v in enumerate(ident):
            ws.write(r, i, v, f_txt)

        bloques = [n["f"], n["rf"], n["ppto"], n["r26"], n["r25"]]
        col = 8
        for bl in bloques:
            for cpt in ("P", "S", "C"):
                v = _v(bl, cpt)
                if v is None:
                    ws.write_blank(r, col, None, fmt(col))
                else:
                    ws.write_number(r, col, v, fmt(col))
                col += 1

        # Indices y desviaciones como formulas
        formulas = [
            f'=IF(ABS(I{e})>1,J{e}/I{e},"")',
            f'=IF(ABS(I{e})>1,K{e}/I{e},"")',
            f'=IF(ABS(L{e})>1,M{e}/L{e},"")',
            f'=IF(ABS(L{e})>1,N{e}/L{e},"")',
            f'=IF(ABS(I{e})>1,(I{e}-J{e}-K{e})/I{e},"")',
            f'=IF(ABS(L{e})>1,(L{e}-M{e}-N{e})/L{e},"")',
            f'=IF(ABS(L{e})>1,I{e}/L{e}-1,"")',
            f'=IF(ABS(M{e})>1,J{e}/M{e}-1,"")',
            f'=IF(ABS(N{e})>1,K{e}/N{e}-1,"")',
            f'=IF(ABS(O{e})>1,I{e}/O{e}-1,"")',
            f'=IF(ABS(U{e})>1,I{e}/U{e}-1,"")',
        ]
        for k, f_ in enumerate(formulas):
            ws.write_formula(r, 23 + k, f_, fmt(23 + k))

        conc = n["conc"]
        if conc is None or math.isnan(conc):
            ws.write_blank(r, 35, None, fmt(35))
        else:
            ws.write_number(r, 35, conc, fmt(35))

        for k, v in enumerate(n["semaforos"]):
            ws.write(r, 36 + k, v, f_txt)

        ws.write(r, 40 - 0, " · ".join(n["motivos"]) +
                 ((" · " if n["motivos"] else "") + n["nota"] if n["nota"] else ""),
                 f_motivo)

    nfilas = len(filas) + 2

    # Semaforos con formato condicional, igual que el reporte del RFCST
    for col in range(36, 40):
        for valor, bg, fg in (("ROJO", "#FFC7CE", "#9C0006"),
                              ("AMARILLO", "#FFEB9C", "#9C6500"),
                              ("VERDE", "#C6EFCE", "#006100"),
                              ("SIN DATO", "#EDEDED", "#7F7F7F")):
            ws.conditional_format(2, col, max(nfilas - 1, 2), col, {
                "type": "cell", "criteria": "==", "value": f'"{valor}"',
                "format": wb.add_format({"bg_color": bg, "font_color": fg,
                                         **base}),
            })

    ws.freeze_panes(2, 3)
    ws.autofilter(1, 0, max(nfilas - 1, 2), len(COLS_REP) - 1)

    ws.set_column(0, 0, 8)          # LN
    ws.set_column(1, 1, 10)         # N° cedente
    ws.set_column(2, 2, 34)         # nombre
    ws.set_column(3, 7, 12)
    ws.set_column(8, 22, 14)
    ws.set_column(23, 35, 13)
    ws.set_column(36, 39, 14)
    ws.set_column(40, 40, 90)       # motivo

    # ---- Leyenda ----
    lg = wb.add_worksheet("Leyenda")
    f_t = wb.add_format({**base, "bold": True, "font_size": 12})
    f_b = wb.add_format({**base, "bold": True, "bg_color": "#D9E1F2", "border": 1})
    f_w = wb.add_format({**base, "text_wrap": True, "valign": "top"})

    n_rojo_r = sum(1 for n in filas if n["sem"] == 2)
    n_ama_r = len(filas) - n_rojo_r

    lg.write(0, 0, f"Reporte de alertas del {ETIQ_FCST} · PPTO Técnico", f_t)
    lg.write(1, 0, f"Generado {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
                   f"{len(filas):,} negocios en ROJO o AMARILLO "
                   f"({n_rojo_r:,} rojos · {n_ama_r:,} amarillos) de "
                   f"{len(negocios):,} · cifras en dólares · materialidad "
                   f"{MATERIALIDAD:,.0f} USD (negocios por debajo no escalan a ROJO) · "
                   f"relevancia {RELEVANCIA:,.0f} USD (impacto mínimo para alertar "
                   f"una desviación contra 2026)", f_w)
    lg.write(2, 0, "Las celdas en amarillo dentro de la hoja Alertas son las cifras "
                   "que se compararon para levantar cada alerta; el Motivo repite "
                   "esos montos.", f_w)
    lg.write(3, 0, "El negocio es la combinación de línea, cedente y número de "
                   "contrato; contra esa misma llave se busca su equivalente en el "
                   "RFCST 2026, en el presupuesto 2026 y en los reales.", f_w)

    for i, t in enumerate(("Semáforo", "Regla", "Umbral",
                           "Celdas marcadas en amarillo")):
        lg.write(5, i, t, f_b)
    for i, fila in enumerate(REGLAS_LEYENDA):
        for k, v in enumerate(fila):
            lg.write(6 + i, k, v, f_w)

    r0 = 6 + len(REGLAS_LEYENDA) + 1
    lg.write(r0, 0, "Semáforo Global: ROJO si hay al menos una regla roja en un "
                    "negocio material; AMARILLO si solo hay reglas amarillas; VERDE "
                    "si no hay alertas o el negocio está por debajo de la "
                    "materialidad.", f_w)
    lg.write(r0 + 1, 0, "La concentración mensual de la prima se reporta como dato "
                        "(% en el mes pico) pero no levanta semáforo a nivel "
                        "negocio: la prima única anual es lo normal en reaseguro.", f_w)
    lg.write(r0 + 2, 0, "Los negocios sin contraparte en el RFCST 2026 se señalan en "
                        "el motivo, pero eso por sí solo no levanta semáforo.", f_w)

    lg.set_column(0, 0, 22)
    lg.set_column(1, 1, 62)
    lg.set_column(2, 2, 34)
    lg.set_column(3, 3, 52)

    wb.close()


# Semaforos por dimension para el reporte
for _n in negocios:
    _f = _n["f"]
    _is = _rat(_f["S"], _f["P"])
    _ic = _rat(_f["C"], _f["P"])
    _vp = (_rat(_f["P"], _n["rf"]["P"], MATERIALIDAD) - 1
           if _n["rf"] and abs(_n["rf"]["P"]) > TOL else float("nan"))
    _n["semaforos"] = [semaforo_sin(_is), semaforo_costos(_ic),
                       semaforo_desviacion(_vp),
                       ["VERDE", "AMARILLO", "ROJO"][_n["sem"]]]

alertas_rep = sorted([n for n in negocios if n["sem"] > 0],
                     key=lambda n: (-n["sem"], -abs(n["f"]["P"])))

generar_reporte_alertas(salida_alertas, alertas_rep)

print(f"Reporte de alertas generado: {salida_alertas} "
      f"({len(alertas_rep):,} negocios)")

# =====================================================
# DASHBOARD HTML - PALETA Y FORMATOS
# =====================================================

S1 = "#3987e5"   # azul    - FCST 2027
S2 = "#d95926"   # naranja - RFCST 2026
S3 = "#199e70"   # aqua    - presupuesto 2026 (FCST 2026)


def _fmt_m(v, dec=1):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    return f"{v / 1e6:,.{dec}f} M"


def _fmt_pct(v, dec=1, signo=False):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "s/d"
    if v > 9.99:
        return f"&times;{v + 1:,.0f}" if v + 1 >= 100 else f"&times;{v + 1:,.1f}"
    if v < -9.99:
        return "&lt;-999%"
    s = "+" if (signo and v > 0) else ""
    return f"{s}{v * 100:,.{dec}f}%"


def _badge(v, bueno_arriba=True, texto=""):
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
# SECCION 1 - GENERAL (tomado / retenido por concepto)
# =====================================================

INFO_MEDIDAS = [
    ("Primas", "P", "&#128181;", True),
    ("Siniestros", "S", "&#9888;", False),
    ("Comisiones", "C", "&#129534;", False),
]

AVISO_RET = ("" if RETENIDO_REAL else
             '<div class="aviso-ret">&#9432; La base del FCST no trae la marca de '
             'retencion: la vista retenido es igual a la tomada. Configura '
             '<b>COL_VISTA_RETENIDO</b> o <b>RETENCION_LN</b> en el script cuando '
             'Suscripcion confirme la marca.</div>')


def _kpis_concepto(cpt, medida, icono, bueno_arriba, glob):
    g = glob[cpt]
    rf = RF_GLOB[cpt] if RF_GLOB else None
    fcst = g["anual"]
    var_rf = _rat(fcst, rf["fcst"]) - 1 if rf else float("nan")
    var_pp = _rat(fcst, rf["ppto"]) - 1 if rf else float("nan")
    meses = g["meses"]
    tot = sum(meses)
    if abs(tot) > TOL:
        shares = [m / tot for m in meses]
        pico = int(np.argmax(np.abs(shares)))
        txt_pico = f"{MESES_TXT[pico]} ({_fmt_pct(shares[pico])})"
    else:
        txt_pico = "s/d"
    prom = tot / 12 if abs(tot) > TOL else float("nan")

    k1 = _kpi(icono, f"{medida} {ETIQ_FCST}", _fmt_m(fcst),
              _badge(var_rf, bueno_arriba,
                     f"vs RFCST Dic26 ({_fmt_m(rf['fcst']) if rf else 's/d'})"),
              f"{ETIQ_PPTO26}: {_fmt_m(rf['ppto']) if rf else 's/d'} · "
              f"Real 2025: {_fmt_m(rf['real25']) if rf else 's/d'}")
    k2 = _kpi("&#128200;", "Crecimiento vs RFCST 2026",
              _fmt_pct(var_rf, signo=True),
              f"{ETIQ_FCST} ({_fmt_m(fcst)}) vs RFCST Dic26 "
              f"({_fmt_m(rf['fcst']) if rf else 's/d'})",
              _badge(var_pp, bueno_arriba, f"vs {ETIQ_PPTO26}"))
    k3 = _kpi("&#128197;", "Estacionalidad", txt_pico,
              f"mes pico del anio · promedio mensual {_fmt_m(prom)}",
              f"total {ANIO_FCST}: {_fmt_m(tot)}")
    return f'<div class="grid kpis">{k1}{k2}{k3}</div>'


sec1_bloques = []

for medida, cpt, icono, bueno_arriba in INFO_MEDIDAS:
    bloque = f"""
  <div class="med-head"><h3 class="med">{medida} · {cpt}</h3>
    <div class="toggle tgl-vista" data-cpt="{cpt}">
      <button data-v="T" class="on">Tomado</button>
      <button data-v="R">Retenido</button>
    </div></div>
  <div class="vista" id="v_{cpt}_T">{_kpis_concepto(cpt, medida, icono, bueno_arriba, GLOB_T)}</div>
  <div class="vista oculto" id="v_{cpt}_R">{AVISO_RET}{_kpis_concepto(cpt, medida, icono, bueno_arriba, GLOB_R)}</div>"""
    sec1_bloques.append(bloque)


def _kpis_psc(glob, pct):
    rf = RF_GLOB["PSC"] if RF_GLOB else None
    fcst = glob["PSC"]["anual"]
    var_rf = _rat(fcst, rf["fcst"]) - 1 if rf else float("nan")
    k1 = _kpi("&#128176;", f"P-S-C {ETIQ_FCST}", _fmt_m(fcst),
              _badge(var_rf, True,
                     f"vs RFCST Dic26 ({_fmt_m(rf['fcst']) if rf else 's/d'})"),
              f"{ETIQ_PPTO26}: {_fmt_m(rf['ppto']) if rf else 's/d'}")
    k2 = _kpi("&#128202;", f"%P-S-C {ETIQ_FCST}", _fmt_pct(pct),
              _badge(pct - pct_psc_rf if not math.isnan(pct_psc_rf) else None,
                     True, "pts vs RFCST Dic26"),
              f"RFCST Dic26: {_fmt_pct(pct_psc_rf)} · {ETIQ_PPTO26}: {_fmt_pct(pct_psc_ppto)}")
    k3 = _kpi("&#9888;", "Composicion",
              f"{_fmt_pct(_rat(glob['S']['anual'], glob['P']['anual']))} S/P",
              f"Comisiones: {_fmt_pct(_rat(glob['C']['anual'], glob['P']['anual']))} de la prima",
              f"S: {_fmt_m(glob['S']['anual'])} · C: {_fmt_m(glob['C']['anual'])}")
    return f'<div class="grid kpis">{k1}{k2}{k3}</div>'


sec1_psc = f"""
  <div class="med-head"><h3 class="med">P-S-C / %P-S-C <span class="ast-mark">*</span></h3>
    <div class="toggle tgl-vista" data-cpt="PSC">
      <button data-v="T" class="on">Tomado</button>
      <button data-v="R">Retenido</button>
    </div></div>
  <div class="vista" id="v_PSC_T">{_kpis_psc(GLOB_T, pct_psc_fcst)}</div>
  <div class="vista oculto" id="v_PSC_R">{AVISO_RET}{_kpis_psc(GLOB_R, pct_psc_ret)}</div>
  <div class="ast">* Falta el incremento a la reserva y los costos de cobertura.</div>"""

sec1_graficas = f"""
  <div class="grid dos2 dos-donut">
    <div class="card donut-doble">
      <h2>Participación por línea de negocio · {ETIQ_FCST} vs RFCST 2026</h2>
      <div class="nota">Participación de cada LN en la prima. Anillo interior =
        PPTO/{ETIQ_FCST} · anillo exterior = RFCST 2026.</div>
      <div id="ch_part"></div>
    </div>
    <div class="card donut-doble">
      <h2>Estacionalidad {ETIQ_FCST} · primas, siniestros y comisiones</h2>
      <div class="nota">Distribución mensual esperada. Anillo interior = primas ·
        medio = siniestros · exterior = comisiones.</div>
      <div id="ch_est_glob"></div>
    </div>
  </div>
  <div class="ast">* Falta el incremento a la reserva y los costos de cobertura.</div>"""

var_rf_p = _rat(gp, _rf_p) - 1 if not math.isnan(_rf_p) else float("nan")
_mes_pico_g = int(np.argmax(GLOB_T["P"]["meses"]))

insight = (
    f"El {ETIQ_FCST} de Suscripcion proyecta <b>{_fmt_m(gp)}</b> de prima tomada"
    + (f", <b>{_fmt_pct(var_rf_p, signo=True)}</b> contra el RFCST Dic 2026 "
       f"({_fmt_m(_rf_p)})" if not math.isnan(var_rf_p) else
       " (sin base RFCST 2026 para comparar)")
    + f". La siniestralidad implicita es "
      f"<b>{_fmt_pct(_rat(GLOB_T['S']['anual'], gp))}</b> y las comisiones "
      f"<b>{_fmt_pct(_rat(GLOB_T['C']['anual'], gp))}</b>, con lo que el P-S-C "
      f"queda en <b>{_fmt_m(GLOB_T['PSC']['anual'])}</b> "
      f"({_fmt_pct(pct_psc_fcst)} de la prima). "
      f"El mes pico de prima es <b>{MESES_TXT[_mes_pico_g]}</b> "
      f"({_fmt_pct(GLOB_T['P']['meses'][_mes_pico_g] / gp if abs(gp) > TOL else None)} del anio). "
      f"<b>{n_rojo}</b> negocios en rojo y <b>{n_amarillo}</b> en amarillo; "
      f"la LN con mayor score de riesgo es "
      f"<b>LN {ranking.iloc[0]['LN']}</b> ({ranking.iloc[0]['Nivel_Riesgo']}, "
      f"score {ranking.iloc[0]['Score_Total']:.0f})."
)

# =====================================================
# SECCION 2 - LINEA DE NEGOCIO
# =====================================================


def _vals(serie):
    out = []
    for v in serie:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            out.append(None)
        else:
            out.append(round(float(v)))
    return out


def _vals_pct(serie):
    out = []
    for v in serie:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            out.append(None)
        else:
            out.append(round(float(v), 4))
    return out


LNS_LBL = [f"LN {ln}" for ln in LNS]

charts_cfg = []

_col_fcst = {"P": "Primas", "S": "Siniestros", "C": "Comisiones"}
_col_rf = {"P": "Primas_RFCST26", "S": "Siniestros_RFCST26", "C": "Comisiones_RFCST26"}
_col_pp = {"P": "Primas_FCST26", "S": "Siniestros_FCST26", "C": "Comisiones_FCST26"}

for medida, cpt, _, bueno in INFO_MEDIDAS:
    charts_cfg.append({
        "el": f"ch_{cpt}_niv", "fmt": "m",
        "cats": LNS_LBL,
        "series": [
            {"n": ETIQ_FCST, "c": S1, "v": _vals(r_ln[_col_fcst[cpt]])},
            {"n": "RFCST 2026", "c": S2, "v": _vals(r_ln[_col_rf[cpt]])},
            {"n": ETIQ_PPTO26, "c": S3, "v": _vals(r_ln[_col_pp[cpt]])},
        ],
    })
    var = _ratio(r_ln[_col_fcst[cpt]], r_ln[_col_rf[cpt]], MATERIALIDAD) - 1
    charts_cfg.append({
        "el": f"ch_{cpt}_var", "fmt": "pct",
        "cats": LNS_LBL,
        "series": [
            {"n": f"Var % {ETIQ_FCST} vs RFCST 2026", "c": S1,
             "v": _vals_pct(var)},
        ],
    })

charts_cfg.append({
    "el": "ch_PSC_niv", "fmt": "m",
    "cats": LNS_LBL,
    "series": [
        {"n": ETIQ_FCST, "c": S1, "v": _vals(r_ln["P_S_C"])},
        {"n": "RFCST 2026", "c": S2, "v": _vals(r_ln["P_S_C_RFCST26"])},
    ],
})

charts_cfg.append({
    "el": "ch_PSC_pct", "fmt": "pct",
    "cats": LNS_LBL,
    "series": [
        {"n": ETIQ_FCST, "c": S1, "v": _vals_pct(r_ln["Pct_P_S_C"])},
        {"n": "RFCST 2026", "c": S2, "v": _vals_pct(r_ln["Pct_P_S_C_RFCST"])},
    ],
})

# Pie de pagina de las graficas de estacionalidad: declara el
# ajuste Ago-Dic, que aplica unicamente al RFCST 2026
if REAL26 is not None or PPTO26 is not None:
    PIE_EST = (
        "* RFCST 2026: Ene-Jul se abre con la forma del real 2026 y Ago-Dic no viene "
        "mensualizado en esa base, por lo que su incremento se reparte con la "
        f"mensualización que Suscripción dio al {ETIQ_FCST} (tramo punteado). El ajuste "
        f"aplica solo al RFCST 2026: el {ETIQ_PPTO26} viene mensualizado en la hoja "
        f"{HOJA_PPTO26} y se grafica sin ajuste."
    )
else:
    PIE_EST = (
        "* Sin las bases mensuales de 2026, el perfil del RFCST 2026 y del "
        f"{ETIQ_PPTO26} es plano dentro de cada bloque (Ene-Jul / Ago-Dic)."
    )

# KPIs de la seccion por LN: mismos cuadros que en General pero
# recalculados a la linea que elija el area de suscripcion
sec2_kpis = f"""
  <div class="card filtros" id="flt_ln">
    <div class="flt"><label>Línea de negocio</label>
      <select id="sel_kpi_ln"></select></div>
    <div class="flt nota-kpi">Los cuadros de primas, siniestros y comisiones se
      recalculan a la LN seleccionada; las gráficas de abajo siguen mostrando
      todas las líneas.</div>
  </div>
  <div class="grid kpis" id="kpi_ln"></div>"""

sec2_bloques = []
for medida, cpt, _, _b in INFO_MEDIDAS:
    sec2_bloques.append(f"""
  <h3 class="med">{medida} · {cpt}</h3>
  <div class="grid dos2">
    <div class="card">
      <h2>{medida} por línea de negocio</h2>
      <div class="nota">{ETIQ_FCST} vs RFCST acumulado a Dic 2026 y {ETIQ_PPTO26} (USD)</div>
      <div id="ch_{cpt}_niv"></div>
    </div>
    <div class="card">
      <h2>Variación vs RFCST 2026 por línea de negocio</h2>
      <div class="nota">Crecimiento implícito del {ETIQ_FCST} contra el RFCST Dic 2026.
        LN sin base comparable no se grafican.</div>
      <div id="ch_{cpt}_var"></div>
    </div>
  </div>
  <div class="grid uno">
    <div class="card">
      <div class="chart-head">
        <h2>Estacionalidad mensual · {medida.lower()}</h2>
        <select class="sel-ln" id="sel_line_{cpt}"></select>
      </div>
      <div class="nota">% del año {ANIO_FCST} que aporta cada mes. Con el filtro en
        (Todas) se dibujan todas las LN; elige una para comparar su estacionalidad
        contra la del RFCST 2026 y la del {ETIQ_PPTO26}.</div>
      <div id="ch_line_{cpt}"></div>
      <div class="ast">{PIE_EST}</div>
    </div>
  </div>""")

sec2_bloques.append(f"""
  <h3 class="med">P-S-C / %P-S-C <span class="ast-mark">*</span></h3>
  <div class="grid dos2">
    <div class="card">
      <h2>P-S-C por línea de negocio</h2>
      <div class="nota">Primas − Siniestros − Comisiones (USD)</div>
      <div id="ch_PSC_niv"></div>
    </div>
    <div class="card">
      <h2>%P-S-C por línea de negocio</h2>
      <div class="nota">P-S-C como % de la prima. LN con prima menor a la
        materialidad no se grafican.</div>
      <div id="ch_PSC_pct"></div>
    </div>
  </div>
  <div class="ast">* Falta el incremento a la reserva y los costos de cobertura.</div>""")

sec2_bloques.append(f"""
  <h3 class="med">Mensualización P · S · C</h3>
  <div class="grid uno">
    <div class="card donut-doble">
      <div class="chart-head">
        <h2>Mensualización de la estacionalidad {ETIQ_FCST}</h2>
        <select class="sel-ln" id="sel_ring_LN"></select>
      </div>
      <div class="nota">Anillo interior = primas · medio = siniestros · exterior =
        comisiones. Cada segmento es el % del año que aporta ese mes. Filtra la LN
        a gusto del área de suscripción.</div>
      <div id="ch_ring_LN"></div>
    </div>
  </div>""")

# =====================================================
# SECCION 3 - NEGOCIOS (cedente / negocio)
# =====================================================

sec3 = f"""
<section id="sec-negocios" class="cardinal">
  <div class="sec-head"><h2 class="sec-title">Negocios</h2>
    <span class="sub">Análisis a nivel cedente, contrato y binder de presupuesto.
      Cada negocio es la combinación de cedente y número de contrato dentro de
      su línea.</span></div>
  <div class="card filtros" id="flt_neg"></div>
  <div class="grid kpis" id="kpi_neg"></div>
  <div class="grid dos">
    <div class="card">
      <div class="chart-head">
        <h2>{ETIQ_FCST} por línea de negocio</h2>
        <div class="toggle" id="tgl_neg">
          <button data-m="0" class="on">Primas</button>
          <button data-m="1">Siniestros</button>
          <button data-m="2">Comisiones</button>
        </div>
      </div>
      <div class="nota">Con los filtros aplicados (USD)</div>
      <div id="ch3_neg"></div>
    </div>
    <div class="card donut-wrap">
      <h2>Semáforo</h2>
      <div id="dn_neg"></div>
      <div class="dl" id="dl_neg"></div>
    </div>
  </div>
  <div class="card scroll">
    <h2>Resumen por entidad</h2>
    <div class="nota">Top por prima {ETIQ_FCST} con los filtros aplicados. Índices
      sobre agregados. El semáforo de la entidad es el peor de sus negocios: las
      columnas Rojos y Amarillos dicen cuántos lo provocaron, y el detalle con el
      motivo y los montos está en el reporte de alertas del final.</div>
    <div id="rs_neg"></div>
  </div>
  <div class="grid dos2">
    <div class="card">
      <div class="chart-head">
        <h2>Estacionalidad del negocio</h2>
        <select class="sel-ln" id="sel_negocio"></select>
      </div>
      <div class="nota">Distribución mensual de primas, siniestros y comisiones del
        negocio seleccionado (% del año).</div>
      <div id="tb_negocio"></div>
    </div>
    <div class="card">
      <h2>Mensualización P · S · C del negocio</h2>
      <div class="nota">Anillo interior = primas · medio = siniestros · exterior =
        comisiones.</div>
      <div id="ch_ring_negocio"></div>
    </div>
  </div>
  <div class="card scroll">
    <div class="chart-head">
      <h2>Top excepciones</h2>
      <div class="toggle" id="tglx_neg">
        <button data-s="2" class="on">&#9650; Rojo</button>
        <button data-s="1">&#9679; Amarillo</button>
      </div>
    </div>
    <div class="nota">Con los filtros aplicados, ordenadas por prima. El motivo
      explica el semáforo. Detalle completo en VAL_FCST27.xlsx → Excepciones.</div>
    <div id="ex_neg"></div>
  </div>
</section>"""

# =====================================================
# DATOS PARA EL DASHBOARD (JSON)
# =====================================================


def _sea_js(dic):
    return {k: {c: (v[c] if v[c] else None) for c in ("P", "S", "C")}
            for k, v in dic.items()}


# Cuadros de primas / siniestros / comisiones por LN: los mismos
# de la seccion General, recalculados a la linea seleccionada
_COLS_KPI = {
    "P": ("Primas", "Primas_RFCST26", "Primas_FCST26", "Primas_Real25"),
    "S": ("Siniestros", "Siniestros_RFCST26", "Siniestros_FCST26", "Siniestros_Real25"),
    "C": ("Comisiones", "Comisiones_RFCST26", "Comisiones_FCST26", "Comisiones_Real25"),
}


def _num(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v))


kpi_ln = {}

for _, _fila in r_ln.iterrows():
    kpi_ln[_fila["LN"]] = {
        cpt: {"f": _num(_fila[c0]), "r": _num(_fila[c1]),
              "p": _num(_fila[c2]), "r25": _num(_fila[c3])}
        for cpt, (c0, c1, c2, c3) in _COLS_KPI.items()
    }

# El total replica los globales de la seccion General (incluye las
# LN presupuestadas que aun no traen forecast 2027)
kpi_ln["_tot"] = {
    cpt: {"f": _num(GLOB_T[cpt]["anual"]),
          "r": _num(RF_GLOB[cpt]["fcst"]) if RF_GLOB else None,
          "p": _num(RF_GLOB[cpt]["ppto"]) if RF_GLOB else None,
          "r25": _num(RF_GLOB[cpt]["real25"]) if RF_GLOB else None}
    for cpt in ("P", "S", "C")
}

DATA_JS = {
    "lns": LNS,
    "lnKpi": kpi_ln,
    "meses": MESES_TXT,
    "charts": charts_cfg,
    "season": {k: {c: (SEASON[k][c] if SEASON[k][c] else None)
                   for c in ("P", "S", "C")} for k in SEASON},
    # Estacionalidad 2026 (RFCST y FCST 2026) para comparar
    # contra la mensualizacion del FCST 2027
    "season26": SEASON26,
    "part": {
        "lns": LNS,
        "fcst": _vals(r_ln["Primas"]),
        "rfcst": (_vals(r_ln["Primas_RFCST26"]) if RFCST is not None else None),
    },
    "neg": neg_rows,
    "cat": CATALOGO_CED,
    "rfcstCed": ({str(k): round(v) for k, v in RFCST["por_ced"].items()}
                 if RFCST is not None else {}),
    "cfg": {
        "umbralAmarillo": UMBRAL_AMARILLO,
        "umbralRojo": UMBRAL_ROJO,
        "sinAmarillo": IND_SIN_AMARILLO,
        "sinRojo": IND_SIN_ROJO,
        "minDen": TOL,
        "materialidad": MATERIALIDAD,
        "anio": ANIO_FCST,
        "hayRfcst": RFCST is not None,
        "etiqFcst": ETIQ_FCST,
        "etiqPpto26": ETIQ_PPTO26,
        # A partir de agosto el RFCST 2026 va ajustado: se dibuja
        # punteado de ese mes en adelante
        "ajusteDesde": len(MESES_ENEJUL),
    },
}

# =====================================================
# PLANTILLA HTML DEL DASHBOARD
# =====================================================

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validación FCST __ANIO__</title>
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
  .med-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .med-head h3.med { margin: 18px 0 10px; }
  .ast-mark { color: #fab219; }
  .ast { color: #898781; font-size: 12px; margin: 8px 2px 0; font-style: italic; }
  .aviso-ret { grid-column: 1/-1; color: #fab219; font-size: 12px;
    background: rgba(250,178,25,.08); border: 1px solid rgba(250,178,25,.25);
    border-radius: 10px; padding: 9px 13px; margin-bottom: 10px; }
  .aviso-ret b { color: #ffd97a; }
  .vista.oculto { display: none; }
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
  .dos2 { grid-template-columns: 1fr 1fr; align-items: stretch; margin-top: 14px; }
  .uno { grid-template-columns: 1fr; margin-top: 14px; }
  @media (max-width: 950px) { .dos, .dos2 { grid-template-columns: 1fr; } }
  svg { width: 100%; height: auto; display: block; }
  .tick { fill: #898781; font-size: 10.5px; font-family: system-ui, sans-serif;
    font-variant-numeric: tabular-nums; }
  .cat { fill: #c3c2b7; font-size: 11px; font-family: system-ui, sans-serif; }
  .vlabel { fill: #c3c2b7; font-size: 10px; font-family: system-ui, sans-serif;
    font-variant-numeric: tabular-nums; }
  .donut-n { fill: #ffffff; font-size: 22px; font-weight: 650;
    font-family: system-ui, sans-serif; }
  .donut-l { fill: #898781; font-size: 10.5px; font-family: system-ui, sans-serif; }
  .bar { transition: opacity .12s; }
  svg:hover .bar { opacity: .45; }
  svg .bar:hover { opacity: 1; }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; margin: 4px 0 10px; }
  .lg { color: #c3c2b7; font-size: 11.5px; display: inline-flex; align-items: center;
    gap: 6px; }
  .lg i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  .donut-wrap { display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .donut-wrap > div:first-of-type { width: 100%; max-width: 210px; }
  .donut-doble > div:last-child { max-width: 460px; margin: 0 auto; }
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
  .flt.nota-kpi { font-size: 11.5px; color: #898781; flex: 2; min-width: 240px;
    justify-content: center; line-height: 1.45; }
  .chart-head { display: flex; justify-content: space-between; align-items: center;
    gap: 10px; flex-wrap: wrap; }
  .toggle { display: inline-flex; background: #0d0d0d; border: 1px solid #383835;
    border-radius: 999px; padding: 2px; }
  .toggle button { background: none; border: none; color: #898781; font-size: 11.5px;
    padding: 5px 12px; border-radius: 999px; cursor: pointer; font-family: inherit; }
  .toggle button.on { background: rgba(57,135,229,.2); color: #9ec5f4; }
  .sel-ln { background: #0d0d0d; color: #ffffff; border: 1px solid #383835;
    border-radius: 8px; padding: 5px 9px; font-size: 12px; font-family: inherit;
    max-width: 340px; }
  .sel-ln:focus { outline: none; border-color: rgba(57,135,229,.6); }
  .vacio { color: #898781; font-size: 12.5px; padding: 18px 4px; }
  .cardinal { border-top: 1px solid #2c2c2a; padding-top: 20px; margin-top: 30px; }
  .acciones { display: flex; justify-content: center; margin-top: 28px; gap: 12px;
    flex-wrap: wrap; }
  a.btn-print { text-decoration: none; }
  .pie-acciones { max-width: 780px; margin: 10px auto 0; text-align: center; }
  .btn-print { background: rgba(57,135,229,.16); color: #9ec5f4;
    border: 1px solid rgba(57,135,229,.35); border-radius: 10px; padding: 11px 20px;
    font-size: 13px; font-family: inherit; cursor: pointer; display: inline-flex;
    align-items: center; gap: 9px; }
  .btn-print:hover { background: rgba(57,135,229,.26); color: #ffffff; }

  /* Impresion: solo la seccion Linea de Negocio, tema oscuro
     conservado (como una captura) */
  @media print {
    @page { size: A4 landscape; margin: 0; }
    * { -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important; }
    html, body.print-ln { background: #0d0d0d !important; }
    body.print-ln { padding: 9mm 9mm 6mm !important; }
    body.print-ln > *:not(#sec-ln):not(header) { display: none !important; }
    body.print-ln header.top { position: static !important; padding: 0 0 10px !important;
      margin-bottom: 14px !important; background: none !important; }
    body.print-ln nav.secs { display: none !important; }
    body.print-ln #sec-ln { display: block !important; margin: 0 !important; }
    body.print-ln .card { break-inside: avoid; page-break-inside: avoid; }
    body.print-ln h3.med { break-after: avoid; page-break-after: avoid; }
    body.print-ln .dos2 { grid-template-columns: 1fr 1fr !important; }
  }
</style>
</head>
<body>

<header class="top">
  <h1>Validación FCST __ANIO__ · PPTO Técnico</h1>
  <span class="sub">__ARCHIVO__ · RFCST 2026: __FUENTE_RFCST__ · generado __GENERADO__</span>
  <nav class="secs">
    <a href="#sec-general">General</a>
    <a href="#sec-ln">Línea de Negocio</a>
    <a href="#sec-negocios">Negocios</a>
  </nav>
</header>

<section id="sec-general" class="bloque">
  <div class="sec-head"><h2 class="sec-title">General</h2>
    <span class="sub">Totalidad de las líneas de negocio · cifras en dólares ·
      comparativo contra __FUENTE_RFCST__</span></div>
__SEC1__
__SEC1PSC__
__SEC1GRAF__
  <div class="insight">&#128161; __INSIGHT__</div>
</section>

<section id="sec-ln" class="bloque">
  <div class="sec-head"><h2 class="sec-title">Línea de Negocio</h2>
    <span class="sub">Mismas vistas, por LN · cifras en dólares · estacionalidad
      mensual del FCST __ANIO__</span></div>
__SEC2KPI__
__SEC2__
</section>

__SEC3__

<div class="acciones">
  <a class="btn-print" href="Reporte_Alertas_FCST27.xlsx" download>
    &#128229; Descargar reporte de alertas (__N_ALERTAS__ negocios)
  </a>
  <button type="button" class="btn-print" id="btn-print-ln">
    &#128424; Imprimir PDF (Línea de Negocio)
  </button>
</div>
<div class="ast pie-acciones">El reporte trae, por cada negocio en rojo o
  amarillo, sus cifras del __ETIQ_FCST__ junto a aquello contra lo que se comparó
  (RFCST 2026, __ETIQ_PPTO26__, real 2026 a julio y real 2025), los índices y
  desviaciones como fórmulas, los semáforos y el motivo con los montos. Las
  celdas que dispararon cada alerta van marcadas en amarillo. Debe estar en la
  misma carpeta que este dashboard.</div>

<script>
const DATA = __DATA__;
const S = ['#3987e5', '#d95926', '#199e70'];
const SEMC = ['#0ca30c', '#fab219', '#d03b3b'];
const SEMN = ['Verde — sin alertas', 'Amarillo — revisar', 'Rojo — inconsistencia'];
const MEDN = ['Primas', 'Siniestros', 'Comisiones'];
const MESES = DATA.meses;
const LNC = ['#3987e5', '#d95926', '#199e70', '#8f6fe8', '#d34f8f', '#c9a227',
             '#4fb3c9', '#7a9e57', '#b06b4c'];
const MESC = ['#2c5f8a', '#e07b39', '#2e7d52', '#3fa7c4', '#9c5fb5', '#7ab648',
              '#1f4e5f', '#b5541c', '#3d6b35', '#4589b0', '#6a3d75', '#245c31'];

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
  // Una variacion de varios miles por ciento no dice nada: se lee
  // mejor como el multiplo que representa
  if (v > 9.99) return '\u00d7' + (v + 1).toLocaleString('en-US',
    {maximumFractionDigits: (v + 1) >= 100 ? 0 : 1});
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
  const y = yV;
  if (v >= 0)
    return 'M ' + x + ' ' + y0 + ' L ' + x + ' ' + (y + r) +
      ' Q ' + x + ' ' + y + ' ' + (x + r) + ' ' + y +
      ' L ' + (x2 - r) + ' ' + y + ' Q ' + x2 + ' ' + y + ' ' + x2 + ' ' + (y + r) +
      ' L ' + x2 + ' ' + y0 + ' Z';
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
  const fmtVal = fmt === 'pct' ? v => fmtPct(v, true) : v => fmtM(v);
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

// Grafica de lineas: estacionalidad mensual (% del anio)
function lineChart(elId, series) {
  const el = document.getElementById(elId);
  if (!el) return;
  const vals = [];
  series.forEach(s => s.v.forEach(v => { if (v !== null && isFinite(v)) vals.push(v); }));
  if (!vals.length) {
    el.innerHTML = '<div class="vacio">Sin datos para esta selección.</div>';
    return;
  }
  const W = 980, H = 300, mL = 52, mR = 14, mT = 14, mB = 40;
  const pw = W - mL - mR, ph = H - mT - mB;
  let vmin = Math.min(0, ...vals), vmax = Math.max(...vals);
  if (vmax === vmin) vmax = vmin + 0.01;
  const ticks = ticksFor(vmin, vmax);
  const tmin = ticks[0], tmax = ticks[ticks.length - 1];
  const x = i => mL + (i + 0.5) * pw / 12;
  const y = v => mT + ph - ((v - tmin) / (tmax - tmin)) * ph;
  let out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">';
  ticks.forEach(t => {
    out += '<line x1="' + mL + '" y1="' + y(t) + '" x2="' + (W - mR) + '" y2="' + y(t) +
      '" stroke="#2c2c2a"/>' +
      '<text x="' + (mL - 8) + '" y="' + (y(t) + 3.5) + '" text-anchor="end" class="tick">' +
      Math.round(t * 100) + '%</text>';
  });
  MESES.forEach((m, i) => {
    out += '<text x="' + x(i) + '" y="' + (H - mB + 18) +
      '" text-anchor="middle" class="cat">' + m + '</text>';
  });
  series.forEach(s => {
    // dashFrom permite dibujar una serie solida hasta cierto mes y
    // punteada de ahi en adelante (el tramo ajustado del RFCST)
    const cortes = (s.dashFrom === undefined)
      ? [[0, s.v.length - 1, !!s.dash]]
      : [[0, s.dashFrom, false], [s.dashFrom, s.v.length - 1, true]];
    cortes.forEach(([ini, fin, punteado]) => {
      let d = '';
      for (let i = ini; i <= fin; i++) {
        const v = s.v[i];
        if (v === null || v === undefined || !isFinite(v)) continue;
        d += (d ? ' L ' : 'M ') + x(i) + ' ' + y(v);
      }
      if (!d) return;
      out += '<path d="' + d + '" fill="none" stroke="' + s.c +
        '" stroke-width="2"' + (punteado ? ' stroke-dasharray="6 4"' : '') +
        ' class="bar"/>';
    });
    {
    s.v.forEach((v, i) => {
      if (v === null || !isFinite(v)) return;
      out += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="3" fill="' + s.c +
        '" class="bar"><title>' + esc(s.n) + ' · ' + MESES[i] + ': ' +
        fmtPct(v) + '</title></circle>';
    });
    }
  });
  out += '</svg>';
  const leyenda = '<div class="legend">' + series.map(s =>
    '<span class="lg">' + ((s.dash && s.dashFrom === undefined)
      ? '<i style="height:0;border-radius:0;border-top:2px dashed ' + s.c + '"></i>'
      : '<i style="background:' + s.c + '"></i>') + esc(s.n) + '</span>'
  ).join('') + '</div>';
  el.innerHTML = leyenda + out;
}

// Dona de anillos concentricos (cada anillo una serie; cada
// segmento un mes o una LN, proporcional a su participacion)
function ringDonut(elId, rings, segLabels, segColors, centro, centroSub) {
  const el = document.getElementById(elId);
  if (!el) return;
  const activos = rings.filter(r => r.v && r.v.some(v => v > 0));
  if (!activos.length) {
    el.innerHTML = '<div class="vacio">Sin datos para esta selección.</div>';
    return;
  }
  const W = 340, cx = W / 2, cy = W / 2;
  const rInt = 62, grosor = Math.min(34, (W / 2 - 14 - rInt) / rings.length);
  let out = '<svg viewBox="0 0 ' + W + ' ' + W + '" role="img">';
  rings.forEach((ring, k) => {
    if (!ring.v) return;
    const total = ring.v.reduce((a, b) => a + Math.max(b, 0), 0);
    if (total <= 0) return;
    const rm = rInt + grosor * k + grosor / 2;
    let ang = -90;
    ring.v.forEach((v, i) => {
      const vv = Math.max(v, 0);
      if (!vv) return;
      const barra = vv / total * 360;
      const gapD = Math.min(1.6, barra * 0.2);
      const a0 = (ang + gapD / 2) * Math.PI / 180;
      const a1 = (ang + barra - gapD / 2) * Math.PI / 180;
      if (a1 > a0) {
        const x0 = cx + rm * Math.cos(a0), y0 = cy + rm * Math.sin(a0);
        const x1 = cx + rm * Math.cos(a1), y1 = cy + rm * Math.sin(a1);
        out += '<path d="M ' + x0 + ' ' + y0 + ' A ' + rm + ' ' + rm + ' 0 ' +
          ((a1 - a0) > Math.PI ? 1 : 0) + ' 1 ' + x1 + ' ' + y1 +
          '" fill="none" stroke="' + segColors[i % segColors.length] +
          '" stroke-width="' + (grosor - 3) + '" class="bar"><title>' +
          esc(ring.n) + ' · ' + esc(segLabels[i]) + ': ' + fmtPct(vv / total) +
          '</title></path>';
      }
      ang += barra;
    });
  });
  out += '<text x="' + cx + '" y="' + (cy - 2) + '" text-anchor="middle" class="donut-n">' +
    esc(centro) + '</text>' +
    '<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" class="donut-l">' +
    esc(centroSub) + '</text></svg>';
  const leyendaSeg = '<div class="legend">' + segLabels.map((l, i) =>
    '<span class="lg"><i style="background:' + segColors[i % segColors.length] +
    '"></i>' + esc(l) + '</span>').join('') + '</div>';
  const leyendaAn = '<div class="legend" style="margin-top:2px">' + rings.map((r, k) =>
    '<span class="lg">' + (k === 0 ? '&#9678; interior: ' :
      (k === rings.length - 1 ? '&#9673; exterior: ' : '&#9673; medio: ')) +
    esc(r.n) + '</span>').join('') + '</div>';
  el.innerHTML = out + leyendaSeg + leyendaAn;
}

function donut(elId, listId, counts) {
  const el = document.getElementById(elId), dl = document.getElementById(listId);
  const total = counts.reduce((a, b) => a + b, 0);
  if (!total) { el.innerHTML = '<div class="vacio">Sin datos.</div>'; dl.innerHTML = ''; return; }
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
    '<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" class="donut-l">negocios</text></svg>';
  el.innerHTML = out;
  dl.innerHTML = counts.map((v, i) =>
    '<div><span><i style="background:' + SEMC[i] + '"></i>' + SEMN[i] +
    '</span><span class="n">' + v.toLocaleString('en-US') + '</span></div>').join('');
}

function chip(txt, cls) { return '<span class="chip ' + cls + '">' + txt + '</span>'; }

function chipSem(s) {
  return s === 2 ? chip('&#9650; ROJO', 'rojo')
    : s === 1 ? chip('&#9679; AMARILLO', 'amarillo') : chip('&#10003; VERDE', 'verde');
}

function ratio(a, b) { return Math.abs(b) > DATA.cfg.minDen ? a / b : null; }

// ------- Seccion 1: toggles tomado / retenido -------
document.querySelectorAll('.tgl-vista').forEach(tgl => {
  const cpt = tgl.dataset.cpt;
  tgl.querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', () => {
      tgl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === btn));
      document.getElementById('v_' + cpt + '_T').classList.toggle('oculto', btn.dataset.v !== 'T');
      document.getElementById('v_' + cpt + '_R').classList.toggle('oculto', btn.dataset.v !== 'R');
    });
  });
});

// ------- Seccion 1: dona de participacion por LN -------
(function () {
  const p = DATA.part;
  const rings = [{n: 'PPTO/FCST ' + DATA.cfg.anio, v: p.fcst.map(v => v === null ? 0 : Math.max(v, 0))}];
  if (p.rfcst) rings.push({n: 'RFCST 2026', v: p.rfcst.map(v => v === null ? 0 : Math.max(v, 0))});
  const tot = p.fcst.reduce((a, b) => a + (b || 0), 0);
  ringDonut('ch_part', rings, p.lns.map(l => 'LN ' + l), LNC,
    fmtM(tot, 0), 'prima FCST ' + DATA.cfg.anio);
})();

// ------- Seccion 1: dona de estacionalidad global -------
function ringsEstacion(lnKey) {
  const s = DATA.season[lnKey];
  if (!s) return [];
  return [
    {n: 'Primas', v: s.P},
    {n: 'Siniestros', v: s.S},
    {n: 'Comisiones', v: s.C},
  ];
}

ringDonut('ch_est_glob', ringsEstacion('_tot'), MESES, MESC,
  DATA.cfg.anio, 'estacionalidad');

// ------- Seccion 2: graficas por LN -------
DATA.charts.forEach(c => groupedBars(c.el, c.cats, c.series, c.fmt));

function selLN(sel, cb) {
  sel.innerHTML = '<option value="">(Todas las LN)</option>' + DATA.lns.map(l =>
    '<option value="' + esc(l) + '">LN ' + esc(l) + '</option>').join('');
  sel.addEventListener('change', () => cb(sel.value));
}

// Cuadros de primas / siniestros / comisiones por LN: mismos
// datos que la seccion General, recalculados al filtro
(function () {
  const sel = document.getElementById('sel_kpi_ln');
  const cont = document.getElementById('kpi_ln');
  if (!sel || !cont) return;
  const ICO = {P: '&#128181;', S: '&#9888;', C: '&#129534;'};
  const BUENO = {P: true, S: false, C: false};

  function pinta(lnSel) {
    const d = DATA.lnKpi[lnSel || '_tot'] || {};
    const suf = lnSel ? ' · LN ' + lnSel : '';
    cont.innerHTML = ['P', 'S', 'C'].map((cpt, i) => {
      const o = d[cpt] || {};
      const varRf = (o.r !== null && o.r !== undefined &&
                     Math.abs(o.r) > DATA.cfg.minDen) ? o.f / o.r - 1 : null;
      return '<div class="card kpi"><div class="t"><i>' + ICO[cpt] + '</i>' +
        MEDN[i] + ' ' + DATA.cfg.etiqFcst + suf + '</div>' +
        '<div class="v">' + fmtM(o.f) + '</div>' +
        '<div class="d">' + badge(varRf, BUENO[cpt],
          'vs RFCST Dic26 (' + fmtM(o.r) + ')') + '</div>' +
        '<div class="d">' + DATA.cfg.etiqPpto26 + ': ' + fmtM(o.p) +
        ' · Real 2025: ' + fmtM(o.r25) + '</div></div>';
    }).join('');
  }

  selLN(sel, pinta);
  pinta('');
})();

['P', 'S', 'C'].forEach(cpt => {
  const selL = document.getElementById('sel_line_' + cpt);

  function pintaLinea(lnSel) {
    let series;
    if (lnSel) {
      // Una sola LN: se compara su mensualizacion contra el
      // perfil 2026. Las series 2026 van punteadas porque esa
      // base solo separa Ene-Jul de Ago-Dic (perfil por bloques)
      const v = DATA.season[lnSel] ? DATA.season[lnSel][cpt] : null;
      series = [{n: 'LN ' + lnSel + ' · ' + DATA.cfg.etiqFcst, c: S[0], v: v || []}];
      const s26 = DATA.season26[lnSel];
      if (s26 && s26[cpt]) {
        // El RFCST va solido hasta julio (forma del real 2026) y
        // punteado de agosto en adelante (tramo ajustado)
        if (s26[cpt].rfcst)
          series.push({n: 'RFCST 2026', c: S[1], v: s26[cpt].rfcst,
                       dashFrom: DATA.cfg.ajusteDesde - 1});
        if (s26[cpt].ppto)
          series.push({n: DATA.cfg.etiqPpto26, c: S[2], v: s26[cpt].ppto});
      }
      if (series.length === 1) {
        // Sin base 2026 comparable: al menos el total como referencia
        const t = DATA.season._tot[cpt];
        if (t) series.push({n: 'Total ' + DATA.cfg.etiqFcst, c: '#898781', v: t, dash: '3 3'});
      }
    } else {
      series = DATA.lns.map((ln, i) => ({
        n: 'LN ' + ln, c: LNC[i % LNC.length],
        v: (DATA.season[ln] && DATA.season[ln][cpt]) || [],
      })).filter(s => s.v && s.v.length);
    }
    lineChart('ch_line_' + cpt, series);
  }

  if (selL) { selLN(selL, pintaLinea); pintaLinea(''); }
});

// Mensualizacion P·S·C: una sola dona al final de la seccion
// (antes se repetia identica en los tres conceptos)
(function () {
  const sel = document.getElementById('sel_ring_LN');
  if (!sel) return;
  function pintaDona(lnSel) {
    ringDonut('ch_ring_LN', ringsEstacion(lnSel || '_tot'), MESES, MESC,
      lnSel ? 'LN ' + lnSel : DATA.cfg.anio, 'P · S · C');
  }
  selLN(sel, pintaDona);
  pintaDona('');
})();

// ------- Seccion 3: negocios -------
// Fila: [0 ln, 1 cedente, 2 contrato, 3 region, 4 paises, 5 corredores,
//        6 monedas, 7 P, 8 S, 9 C, 10 Pm[12], 11 Sm[12], 12 Cm[12],
//        13 semaforo, 14 motivos, 15 binder ppto]
const stateNeg = {nivel: 'ced', m: 0, exc: 2, f: {}};

const FDEF_NEG = [[0, 'LN'], [3, 'Región'], [4, 'País (cód.)'], [1, 'Cedente'],
                  [2, 'Contrato'], [15, 'Binder Ppto']];

function nombreCed(c) {
  const n = DATA.cat[c];
  return n ? c + ' · ' + n : c;
}

function rowsNeg(skip) {
  return DATA.neg.filter(r => {
    for (const k in stateNeg.f) {
      if (+k === skip) continue;
      const v = stateNeg.f[k];
      if (v !== null && v !== undefined && String(r[k]) !== v) return false;
    }
    return true;
  });
}

function buildFiltersNeg() {
  const cont = document.getElementById('flt_neg');
  let html = '<div class="flt"><label>Nivel</label>' +
    '<select id="sel_nivel">' +
    '<option value="ced"' + (stateNeg.nivel === 'ced' ? ' selected' : '') + '>Cedente</option>' +
    '<option value="neg"' + (stateNeg.nivel === 'neg' ? ' selected' : '') + '>Contrato</option>' +
    '<option value="bin"' + (stateNeg.nivel === 'bin' ? ' selected' : '') + '>Binder Ppto</option>' +
    '</select></div>';
  FDEF_NEG.forEach(([k, label]) => {
    const opts = [...new Set(rowsNeg(k).map(r => String(r[k])).filter(v => v !== ''))]
      .sort((a, b) => a.localeCompare(b, 'es', {numeric: true}));
    const cur = stateNeg.f[k] || '';
    const rot = k === 1 ? nombreCed : (o => o);
    const vacio = opts.length ? '(Todos)' : '(sin dato en el export)';
    html += '<div class="flt"><label>' + label + '</label>' +
      '<select data-k="' + k + '"><option value="">' + vacio + '</option>' +
      opts.map(o => '<option value="' + esc(o) + '"' + (o === cur ? ' selected' : '') + '>' +
        esc(rot(o)) + '</option>').join('') + '</select></div>';
  });
  html += '<button class="flt-reset" type="button">Limpiar filtros</button>';
  cont.innerHTML = html;
  cont.querySelector('#sel_nivel').addEventListener('change', e => {
    stateNeg.nivel = e.target.value;
    renderNeg();
  });
  cont.querySelectorAll('select[data-k]').forEach(sel => {
    sel.addEventListener('change', () => {
      const k = +sel.dataset.k;
      if (sel.value === '') delete stateNeg.f[k];
      else stateNeg.f[k] = sel.value;
      renderNeg();
    });
  });
  cont.querySelector('.flt-reset').addEventListener('click', () => {
    stateNeg.f = {};
    renderNeg();
  });
}

function entLabel(r) {
  const ced = nombreCed(r[1]);
  if (stateNeg.nivel === 'ced') return ced;
  if (stateNeg.nivel === 'bin') return r[15] || '(sin binder)';
  return ced + ' · cto ' + r[2] + ' · LN ' + r[0];
}

function entKeyNeg(r) {
  if (stateNeg.nivel === 'ced') return r[1];
  if (stateNeg.nivel === 'bin') return r[15] || '';
  return r[1] + '|' + r[2] + '|' + r[0];
}

function agrupaEntidades(rows) {
  const ents = {};
  rows.forEach(r => {
    const k = entKeyNeg(r);
    if (!ents[k]) ents[k] = {label: entLabel(r), ced: r[1], n: 0, P: 0, S: 0, C: 0,
      Pm: Array(12).fill(0), Sm: Array(12).fill(0), Cm: Array(12).fill(0),
      sem: 0, rojos: 0, amas: 0, motivos: new Set(), lns: new Set(), reg: new Set()};
    const e = ents[k];
    e.n++; e.P += r[7]; e.S += r[8]; e.C += r[9];
    for (let i = 0; i < 12; i++) { e.Pm[i] += r[10][i]; e.Sm[i] += r[11][i]; e.Cm[i] += r[12][i]; }
    // el semaforo de la entidad es el peor de sus negocios: las
    // columnas de conteo dicen cuantos lo provocaron
    e.sem = Math.max(e.sem, r[13]);
    if (r[13] === 2) e.rojos++; else if (r[13] === 1) e.amas++;
    if (r[14]) e.motivos.add(r[14]);
    e.lns.add(r[0]); if (r[3]) e.reg.add(r[3]);
  });
  return ents;
}

function renderNeg() {
  buildFiltersNeg();
  const rows = rowsNeg(null);
  const ents = agrupaEntidades(rows);
  const lista = Object.values(ents).sort((a, b) => b.P - a.P);

  // KPIs
  const P = rows.reduce((a, r) => a + r[7], 0);
  const Sv = rows.reduce((a, r) => a + r[8], 0);
  const Cv = rows.reduce((a, r) => a + r[9], 0);
  const nR = rows.filter(r => r[13] === 2).length;
  const nA = rows.filter(r => r[13] === 1).length;

  // crecimiento vs RFCST por cedentes con base comparable
  let pF = 0, pR = 0;
  if (DATA.cfg.hayRfcst) {
    const porCed = {};
    rows.forEach(r => { porCed[r[1]] = (porCed[r[1]] || 0) + r[7]; });
    for (const c in porCed) {
      const rf = DATA.rfcstCed[c];
      if (rf !== undefined && Math.abs(rf) > DATA.cfg.materialidad) {
        pF += porCed[c]; pR += rf;
      }
    }
  }
  const crec = (pR !== 0) ? pF / pR - 1 : null;

  document.getElementById('kpi_neg').innerHTML =
    '<div class="card kpi"><div class="t"><i>&#128181;</i>Prima FCST ' + DATA.cfg.anio +
    '</div><div class="v">' + fmtM(P) + '</div><div class="d">' +
    lista.length.toLocaleString('en-US') + ' entidades · ' +
    rows.length.toLocaleString('en-US') + ' negocios</div></div>' +
    '<div class="card kpi"><div class="t"><i>&#128200;</i>Crecimiento vs RFCST 2026</div>' +
    '<div class="v">' + fmtPct(crec, true) + '</div>' +
    '<div class="d">' + (DATA.cfg.hayRfcst
      ? 'solo cedentes presentes en ambas bases: FCST ' + fmtM(pF) + ' vs RFCST ' + fmtM(pR)
      : 'sin base RFCST 2026 disponible') + '</div></div>' +
    '<div class="card kpi"><div class="t"><i>&#9888;</i>Índices implícitos</div>' +
    '<div class="v">' + fmtPct(ratio(Sv, P)) + '</div>' +
    '<div class="d">siniestralidad S/P · comisiones ' + fmtPct(ratio(Cv, P)) + '</div></div>' +
    '<div class="card kpi"><div class="t"><i>&#128680;</i>Negocios con alerta</div>' +
    '<div class="v">' + (nR + nA).toLocaleString('en-US') + '</div>' +
    '<div class="d"><b class="down">' + nR.toLocaleString('en-US') + ' rojos</b> · ' +
    nA.toLocaleString('en-US') + ' amarillos · de ' +
    rows.length.toLocaleString('en-US') + '</div></div>';

  // Barras por LN
  const mi = stateNeg.m;
  const lns = [...new Set(rows.map(r => r[0]))].sort((a, b) =>
    a.localeCompare(b, 'es', {numeric: true}));
  const serie = lns.map(ln => rows.filter(r => r[0] === ln)
    .reduce((a, r) => a + r[7 + mi], 0));
  groupedBars('ch3_neg', lns.map(l => 'LN ' + l),
    [{n: MEDN[mi] + ' FCST ' + DATA.cfg.anio, c: S[0], v: serie}], 'm');

  // Donut semaforo
  donut('dn_neg', 'dl_neg', [rows.length - nR - nA, nA, nR]);

  // Resumen por entidad
  const top = lista.slice(0, 15);
  document.getElementById('rs_neg').innerHTML = top.length ?
    '<table><thead><tr><th>Entidad</th><th>LN</th><th>Región</th>' +
    '<th class="num">Negocios</th><th class="num">Primas</th>' +
    '<th class="num">vs RFCST 26</th>' +
    '<th class="num">Siniestros</th><th class="num">Comisiones</th>' +
    '<th class="num">S/P</th><th class="num">C/P</th><th class="num">%P-S-C</th>' +
    '<th class="num">Rojos</th><th class="num">Amarillos</th>' +
    '<th>Semáforo</th></tr></thead><tbody>' +
    top.map(e => {
      const rf = DATA.cfg.hayRfcst && stateNeg.nivel === 'ced'
        ? DATA.rfcstCed[e.ced] : undefined;
      const cr = rf !== undefined && Math.abs(rf) > DATA.cfg.materialidad
        ? e.P / rf - 1 : null;
      return '<tr><td>' + esc(e.label) + '</td><td>' + esc([...e.lns].join(', ')) +
        '</td><td>' + esc([...e.reg].join(', ')) + '</td>' +
        '<td class="num">' + e.n + '</td><td class="num">' + fmtM(e.P) + '</td>' +
        '<td class="num">' + fmtPct(cr, true) + '</td>' +
        '<td class="num">' + fmtM(e.S) + '</td><td class="num">' + fmtM(e.C) + '</td>' +
        '<td class="num">' + fmtPct(ratio(e.S, e.P)) + '</td>' +
        '<td class="num">' + fmtPct(ratio(e.C, e.P)) + '</td>' +
        '<td class="num">' + fmtPct(ratio(e.P - e.S - e.C, e.P)) + '</td>' +
        '<td class="num">' + (e.rojos ? chip(e.rojos, 'rojo') : '–') + '</td>' +
        '<td class="num">' + (e.amas ? chip(e.amas, 'amarillo') : '–') + '</td>' +
        '<td>' + chipSem(e.sem) + '</td></tr>';
    }).join('') + '</tbody></table>' :
    '<div class="vacio">Sin datos con los filtros aplicados.</div>';

  // Selector de negocio para estacionalidad
  const sel = document.getElementById('sel_negocio');
  const prev = sel.value;
  sel.innerHTML = lista.slice(0, 60).map((e, i) =>
    '<option value="' + i + '">' + esc(e.label) + ' (' + fmtM(e.P) + ')</option>').join('');
  if (prev && +prev < Math.min(lista.length, 60)) sel.value = prev;
  pintaNegocio(lista);

  // Top excepciones
  const sev = stateNeg.exc;
  const exc = rows.filter(r => r[13] === sev).sort((a, b) => b[7] - a[7]).slice(0, 10);
  document.getElementById('ex_neg').innerHTML = exc.length ?
    '<table><thead><tr><th>LN</th><th>Cedente</th><th class="num">Contrato</th>' +
    '<th>Binder Ppto</th><th>Región</th><th class="num">Primas</th>' +
    '<th class="num">Siniestros</th>' +
    '<th class="num">Comisiones</th><th>Motivo</th></tr></thead><tbody>' +
    exc.map(r => '<tr><td>LN ' + esc(r[0]) + '</td><td>' + esc(nombreCed(r[1])) + '</td>' +
      '<td class="num">' + esc(r[2]) + '</td><td>' + esc(r[15] || '–') + '</td>' +
      '<td>' + esc(r[3]) + '</td>' +
      '<td class="num">' + fmtM(r[7]) + '</td><td class="num">' + fmtM(r[8]) + '</td>' +
      '<td class="num">' + fmtM(r[9]) + '</td>' +
      '<td class="motivo">' + esc(r[14] || 'Revisión') + '</td></tr>').join('') +
    '</tbody></table>' :
    '<div class="vacio">Sin excepciones ' + (sev === 2 ? 'rojas' : 'amarillas') +
    ' con los filtros aplicados.</div>';
}

function pintaNegocio(lista) {
  const sel = document.getElementById('sel_negocio');
  const e = lista[+sel.value || 0];
  const tb = document.getElementById('tb_negocio');
  if (!e) {
    tb.innerHTML = '<div class="vacio">Sin datos.</div>';
    ringDonut('ch_ring_negocio', [], MESES, MESC, '', '');
    return;
  }
  const tot = {P: e.Pm.reduce((a, b) => a + b, 0), S: e.Sm.reduce((a, b) => a + b, 0),
               C: e.Cm.reduce((a, b) => a + b, 0)};
  const pct = (v, t) => Math.abs(t) > DATA.cfg.minDen ? v / t : null;
  tb.innerHTML =
    '<table><thead><tr><th>Mes</th><th class="num">Primas</th><th class="num">%</th>' +
    '<th class="num">Siniestros</th><th class="num">%</th>' +
    '<th class="num">Comisiones</th><th class="num">%</th></tr></thead><tbody>' +
    MESES.map((m, i) =>
      '<tr><td>' + m + '</td>' +
      '<td class="num">' + fmtM(e.Pm[i]) + '</td>' +
      '<td class="num">' + fmtPct(pct(e.Pm[i], tot.P)) + '</td>' +
      '<td class="num">' + fmtM(e.Sm[i]) + '</td>' +
      '<td class="num">' + fmtPct(pct(e.Sm[i], tot.S)) + '</td>' +
      '<td class="num">' + fmtM(e.Cm[i]) + '</td>' +
      '<td class="num">' + fmtPct(pct(e.Cm[i], tot.C)) + '</td></tr>').join('') +
    '</tbody></table>';
  ringDonut('ch_ring_negocio', [
    {n: 'Primas', v: tot.P > 0 ? e.Pm.map(v => Math.max(v, 0)) : null},
    {n: 'Siniestros', v: tot.S > 0 ? e.Sm.map(v => Math.max(v, 0)) : null},
    {n: 'Comisiones', v: tot.C > 0 ? e.Cm.map(v => Math.max(v, 0)) : null},
  ], MESES, MESC, '', '');
}

document.getElementById('sel_negocio').addEventListener('change', () => {
  const rows = rowsNeg(null);
  const lista = Object.values(agrupaEntidades(rows)).sort((a, b) => b.P - a.P);
  pintaNegocio(lista);
});

document.querySelectorAll('#tgl_neg button').forEach(btn => {
  btn.addEventListener('click', () => {
    stateNeg.m = +btn.dataset.m;
    document.querySelectorAll('#tgl_neg button')
      .forEach(b => b.classList.toggle('on', b === btn));
    renderNeg();
  });
});
document.querySelectorAll('#tglx_neg button').forEach(btn => {
  btn.addEventListener('click', () => {
    stateNeg.exc = +btn.dataset.s;
    document.querySelectorAll('#tglx_neg button')
      .forEach(b => b.classList.toggle('on', b === btn));
    renderNeg();
  });
});

renderNeg();

// Imprimir solo la seccion Linea de Negocio
const btnPrint = document.getElementById('btn-print-ln');
function finPrint() { document.body.classList.remove('print-ln'); }
btnPrint.addEventListener('click', () => {
  document.body.classList.add('print-ln');
  window.addEventListener('afterprint', finPrint, {once: true});
  window.print();
  setTimeout(finPrint, 1500);
});

// Resalta la seccion activa en la navegacion
const secciones = ['sec-general', 'sec-ln', 'sec-negocios'];
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

salida_html = os.path.join(xOutputs, "Dashboard_FCST27.html")

html = (
    PLANTILLA
    .replace("__ANIO__", str(ANIO_FCST))
    .replace("__ARCHIVO__", os.path.basename(archivo))
    .replace("__FUENTE_RFCST__", FUENTE_RFCST)
    .replace("__GENERADO__", datetime.now().strftime("%d/%m/%Y %H:%M"))
    .replace("__SEC1PSC__", sec1_psc)
    .replace("__SEC1GRAF__", sec1_graficas)
    .replace("__SEC1__", "".join(sec1_bloques))
    .replace("__N_ALERTAS__", f"{len(alertas_rep):,}")
    .replace("__ETIQ_PPTO26__", ETIQ_PPTO26)
    .replace("__ETIQ_FCST__", ETIQ_FCST)
    .replace("__SEC2KPI__", sec2_kpis)
    .replace("__SEC2__", "".join(sec2_bloques))
    .replace("__SEC3__", sec3)
    .replace("__INSIGHT__", insight)
    .replace("__DATA__", json.dumps(DATA_JS, separators=(",", ":"), ensure_ascii=False))
)

with open(salida_html, "w", encoding="utf-8") as fh:
    fh.write(html)

print(f"Dashboard generado: {salida_html}")

print(f"Listo en {time.perf_counter() - inicio:.1f} s")
