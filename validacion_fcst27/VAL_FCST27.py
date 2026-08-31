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
#   V4. Coherencia por negocio (cedente / correlativo):
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
# El CSV trae dos defectos de origen que este script
# resuelve y documenta (hoja Mapeo_Columnas del Excel):
#
#   1. Los encabezados NO corresponden a las columnas de
#      datos (el export de BW escribio el catalogo de
#      campos en otro orden). El script lee POR POSICION
#      con el mapeo MAPEO_POSICIONAL de abajo, inferido y
#      verificado contra la estructura de los datos.
#
#   2. La columna del concepto (ZCONCEPTO) viene VACIA,
#      por lo que primas / siniestros / comisiones solo se
#      distinguen por la estructura del archivo: para cada
#      negocio los renglones vienen en corridas ordenadas
#      Primas (montos negativos: abono), luego Siniestros
#      y luego Comisiones (montos positivos: cargo). El
#      script reconstruye el concepto con esa regla y
#      reporta en Calidad_Datos lo que no pudo clasificar.
#
#   Si Suscripcion reexporta el archivo con ZCONCEPTO
#   lleno, ajustar COL_CONCEPTO_EXPLICITO para usarlo
#   directamente y desactivar la reconstruccion.
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
# xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\2027\4_Validacion"
xFolder = os.path.dirname(os.path.abspath(__file__))

xInputs = os.path.join(xFolder, "Inputs")
xOutputs = os.path.join(xFolder, "Outputs")

os.makedirs(xOutputs, exist_ok=True)

# ---- Base del FCST 2027 (CSV de Suscripcion) ----
ARCHIVO_FCST = "PptoTecnico2026_Completo.csv"
PREFIJO_FCST = "PptoTecnico"          # fallback: el .csv mas reciente

ANIO_FCST = 2027                      # ejercicio que se valida
MESES_TXT = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]

# ---- Base del RFCST 2026 (comparativo, opcional) ----
# Es la misma base que alimenta VAL_RFCST26 / el dashboard
# del RFCST. Si no se encuentra, el dashboard muestra s/d
# en las comparativas y el resto sigue funcionando.
ARCHIVO_RFCST = "BD_RFCST_26_act.xlsx"
PREFIJO_RFCST = "BD_RFCST"
HOJA_RFCST = "BD_RFCST26"

# ---- Catalogo de cedentes (numero -> nombre, opcional) ----
ARCHIVO_CATALOGO = "Catalogo"
HOJA_CATALOGO = "Valores"
COL_CAT_NUM = "Ced"
COL_CAT_NOMBRE = "CedenteRP"

# ---- Umbrales de validacion ----
TOL = 1.0                     # tolerancia en USD
MATERIALIDAD = 10_000         # USD: negocios por debajo no escalan a ROJO

UMBRAL_AMARILLO = 0.20        # desviacion vs RFCST que marca AMARILLO
UMBRAL_ROJO = 0.40            # desviacion vs RFCST que marca ROJO

IND_SIN_AMARILLO = 0.80       # siniestralidad implicita S/P
IND_SIN_ROJO = 1.00
IND_COS_AMARILLO = 0.35       # comisiones implicitas C/P
IND_COS_ROJO = 0.50

CONC_AMARILLO = 0.40          # un solo mes concentra > 40% del anio
CONC_ROJO = 0.60              # un solo mes concentra > 60% del anio

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

# ---- Concepto explicito ----
# Si un nuevo export trae la columna de concepto llena,
# indicar aqui su posicion (0-41) y el mapeo de claves, ej.
#   COL_CONCEPTO_EXPLICITO = (24, {"1": "P", "2": "S", "3": "C"})
COL_CONCEPTO_EXPLICITO = None

# ---- Mapeo posicional del CSV (42 columnas) ----
# Posicion -> campo. Inferido de la estructura de los datos
# porque los encabezados del export vienen permutados. Las
# posiciones no listadas se conservan pero no se usan.
MAPEO_POSICIONAL = {
    4: "LN",              # LN04001 ... LN04008-Agro
    5: "Pais_Cod",        # codigo numerico de pais / oficina
    9: "Moneda",          # moneda del contrato (el monto viene en USD)
    10: "Cuenta_LN",      # cuenta contable de la LN (redundante con LN)
    11: "Producto",       # cuenta tecnica / producto (A0xx...)
    12: "Correlativo",    # correlativo del negocio dentro del cedente
    14: "Periodo",        # AAAA0PP fiscal (2027001..2027012 en el plan)
    16: "Anio",           # ejercicio fiscal del renglon
    19: "Mes",            # mes 1-12
    23: "Flag_A",         # bandera binaria (candidata retencion)
    25: "Flag_B",         # bandera 1/2/3 (uso por confirmar)
    26: "TipoRea_Cod",    # 1-4, tipo de reaseguro (por confirmar)
    30: "Anio_Susc",      # anio de suscripcion de la cohorte
    31: "Cedente",        # numero de cedente
    32: "Corredor",       # numero de corredor
    33: "Flag_C",         # bandera binaria (candidata retencion / MGA)
    37: "Monto",          # monto USD (primas en negativo, S y C en positivo)
    39: "Region",         # region R01-R06
}

N_COLUMNAS_CSV = 42

# Columnas que varian dentro de un mismo negocio-concepto y
# por eso NO forman parte de la llave para reconstruir el
# concepto (periodo/anio de proyeccion y cohorte)
_POS_NO_LLAVE = {14, 15, 16, 18, 19, 20, 30, 37}

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

if len(df.columns) != N_COLUMNAS_CSV:
    raise ValueError(
        f"El CSV trae {len(df.columns)} columnas y se esperaban {N_COLUMNAS_CSV}. "
        "Cambio el layout del export: revisar MAPEO_POSICIONAL."
    )

df.columns = [MAPEO_POSICIONAL.get(i, f"pos{i:02d}") for i in range(len(df.columns))]

df["Monto"] = pd.to_numeric(
    df["Monto"].astype(str).str.replace(",", "", regex=False), errors="coerce"
).fillna(0.0)

for col in ("Periodo", "Anio", "Mes", "Anio_Susc"):
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(np.int64)

df["LN"] = (df["LN"].astype(str).str.strip()
            .str.replace(r"^LN0*", "", regex=True))

df["Cedente"] = pd.to_numeric(df["Cedente"], errors="coerce").fillna(0).astype(np.int64)
df["Correlativo"] = pd.to_numeric(df["Correlativo"], errors="coerce").fillna(0).astype(np.int64)
df["Corredor"] = pd.to_numeric(df["Corredor"], errors="coerce").fillna(0).astype(np.int64)

print(f"  {len(df):,} renglones · LN: {df['LN'].nunique()} · "
      f"cedentes: {df['Cedente'].nunique():,} · "
      f"anios fiscales: {df['Anio'].min()}-{df['Anio'].max()}")

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

if COL_CONCEPTO_EXPLICITO is not None:
    _pos, _claves = COL_CONCEPTO_EXPLICITO
    _col = MAPEO_POSICIONAL.get(_pos, f"pos{_pos:02d}")
    df["Concepto"] = (df[_col].astype(str).str.strip()
                      .map(_claves).fillna("X"))
    print(f"Concepto tomado de la columna explicita (pos. {_pos}).")
else:
    print("Reconstruyendo el concepto por estructura del archivo ...")

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

_chk("ZCONCEPTO vacia",
     "El concepto P/S/C se reconstruyo por la estructura del archivo "
     "(corridas Primas -> Siniestros -> Comisiones por negocio)."
     if COL_CONCEPTO_EXPLICITO is None else
     "Se uso la columna de concepto explicita configurada.",
     0, 0)

_x = d[d["Concepto"] == "X"]
_chk("Bloques sin clasificar (X)",
     f"Corridas positivas de mas alla de la segunda por negocio en {ANIO_FCST}; "
     "excluidas de P/S/C. Revisar con Suscripcion.",
     len(_x), _x["Monto"].sum())

_n = d[d["Concepto"] == "N"]
_chk("Bloques neutros (suma cero)",
     "Corridas cuya suma es cero: no afectan cifras.",
     len(_n), 0)

_pp = d[(d["Concepto"] == "P") & (d["Monto"] > TOL)]
_chk("Primas con signo invertido",
     f"Renglones positivos dentro de bloques de prima en {ANIO_FCST} "
     "(ajustes o devoluciones); restan prima.",
     len(_pp), _pp["Monto"].sum())

_sn = d[(d["Concepto"].isin(["S", "C"])) & (d["Monto"] < -TOL)]
_chk("Siniestros/comisiones negativos",
     f"Renglones negativos dentro de bloques S o C en {ANIO_FCST} "
     "(recuperos o ajustes); restan gasto.",
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
_por_neg = d_ok.pivot_table(index=["LN", "Cedente", "Correlativo"],
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
    sufijos = ["1226", "PPTO1226", "1225"]

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
          f"Ppto26 {por_ln['P_PPTO1226'].sum() / 1e6:,.1f} M · "
          f"Real25 {por_ln['P_1225'].sum() / 1e6:,.1f} M")

    return {"por_ln": por_ln, "por_ced": por_ced,
            "archivo": os.path.basename(ruta)}


RFCST = cargar_rfcst26()

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
            fila["Primas_PPTO26"] = r["P_PPTO1226"]
            fila["Siniestros_PPTO26"] = r["S_PPTO1226"]
            fila["Comisiones_PPTO26"] = r["C_PPTO1226"]
            fila["Primas_Real25"] = r["P_1225"]
        else:
            for c in ("Primas_RFCST26", "Siniestros_RFCST26", "Comisiones_RFCST26",
                      "Primas_PPTO26", "Siniestros_PPTO26", "Comisiones_PPTO26",
                      "Primas_Real25"):
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
# AGREGADOS POR NEGOCIO Y CEDENTE
# =====================================================

grp_neg = d_ok.groupby(["LN", "Cedente", "Correlativo"], sort=False)

neg_rows = []
for (ln, ced, corr), sub in grp_neg:
    g = {}
    for cpt in ("P", "S", "C"):
        s = sub[sub["Concepto"] == cpt]
        por_mes = s.groupby("Mes")["Valor"].sum()
        g[cpt] = [round(float(por_mes.get(m, 0.0))) for m in range(1, 13)]
    P = sum(g["P"]); S = sum(g["S"]); C = sum(g["C"])

    ind_sin = _rat(S, P)
    ind_cos = _rat(C, P)
    tot_p = sum(abs(v) for v in g["P"])
    conc = max(abs(v) for v in g["P"]) / tot_p if tot_p > TOL else float("nan")

    motivos = []
    sem = 0
    material = abs(P) > MATERIALIDAD
    if P < -TOL:
        motivos.append("Prima negativa")
        sem = 2 if material else 1
    if abs(P) <= TOL and (abs(S) > TOL or abs(C) > TOL):
        motivos.append("S/C sin prima")
        sem = max(sem, 2 if (abs(S) + abs(C)) > MATERIALIDAD else 1)
    if not math.isnan(ind_sin) and ind_sin > IND_SIN_ROJO:
        motivos.append("Siniestralidad > 100%")
        sem = max(sem, 2 if material else 1)
    elif not math.isnan(ind_sin) and ind_sin > IND_SIN_AMARILLO:
        motivos.append(f"Siniestralidad > {IND_SIN_AMARILLO:.0%}")
        sem = max(sem, 1)
    if not math.isnan(ind_cos) and ind_cos > IND_COS_ROJO:
        motivos.append(f"Comisiones > {IND_COS_ROJO:.0%}")
        sem = max(sem, 2 if material else 1)
    elif not math.isnan(ind_cos) and ind_cos > IND_COS_AMARILLO:
        motivos.append(f"Comisiones > {IND_COS_AMARILLO:.0%}")
        sem = max(sem, 1)
    if not math.isnan(conc) and conc > CONC_ROJO and material:
        motivos.append(f"{conc:.0%} de la prima en un mes")
        sem = max(sem, 1)

    regiones = sorted(set(sub["Region"].dropna().astype(str)))
    paises = sorted(set(pd.to_numeric(sub["Pais_Cod"], errors="coerce")
                        .dropna().astype(int).astype(str)))
    corredores = sorted(set(sub["Corredor"].astype(int).astype(str)))
    monedas = sorted(set(sub["Moneda"].dropna().astype(str)))

    neg_rows.append([
        ln, str(int(ced)), str(int(corr)),
        "/".join(regiones), "/".join(paises[:3]), "/".join(corredores[:3]),
        "/".join(monedas[:4]),
        round(P), round(S), round(C),
        g["P"], g["S"], g["C"],
        sem, " · ".join(motivos),
    ])

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
            "Negocios": sub.groupby(["LN", "Correlativo"]).ngroups,
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
        "Ppto 2026": ppt,
        "Var % vs Ppto26": _rat(fcst, ppt) - 1 if not math.isnan(ppt) else float("nan"),
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
    "Ppto 2026": pct_psc_ppto,
    "Var % vs Ppto26": pct_psc_fcst - pct_psc_ppto,
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
        "P/S/C reconstruidos por estructura del export (ZCONCEPTO vacia)"
        if COL_CONCEPTO_EXPLICITO is None else "Concepto de columna explicita",
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

# =====================================================
# EXPORT EXCEL
# =====================================================

salida_xlsx = os.path.join(xOutputs, "VAL_FCST27.xlsx")

cols_ln = [
    "LN", "Primas", "Primas_RFCST26", "Crec_vs_RFCST", "Semaforo_Crec",
    "Primas_PPTO26", "Primas_Real25", "Primas_Ret",
    "Siniestros", "Siniestros_RFCST26", "Ind_Sin", "Ind_Sin_RFCST", "Semaforo_Sin",
    "Comisiones", "Comisiones_RFCST26", "Ind_Cos", "Ind_Cos_RFCST", "Semaforo_Cos",
    "P_S_C", "Pct_P_S_C", "P_S_C_RFCST26", "Pct_P_S_C_RFCST",
    "Participacion_FCST27", "Participacion_RFCST26",
    "Mes_Pico", "Pct_Mes_Pico", "Meses_Sin_Prima", "Semaforo_Est",
    "Score_Total", "Nivel_Riesgo", "Ranking",
]

neg_export = pd.DataFrame(
    [r[:10] + [r[13], r[14]] for r in neg_rows],
    columns=["LN", "Cedente", "Correlativo", "Region", "Paises", "Corredores",
             "Monedas", "Primas", "Siniestros", "Comisiones", "Semaforo",
             "Motivos"],
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
    exportar(ret_candidatas, "Retencion_Candidatas")
    exportar(mapeo_doc, "Mapeo_Columnas")
    exportar(parametros, "Parametros")

print(f"Excel generado: {salida_xlsx}")

# =====================================================
# DASHBOARD HTML - PALETA Y FORMATOS
# =====================================================

S1 = "#3987e5"   # azul    - FCST 2027
S2 = "#d95926"   # naranja - RFCST 2026
S3 = "#199e70"   # aqua    - Ppto 2026


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


A2 = str(ANIO_FCST)[2:]          # "27"
ETIQ_FCST = f"FCST {ANIO_FCST}"

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
              f"Ppto 2026: {_fmt_m(rf['ppto']) if rf else 's/d'} · "
              f"Real 2025: {_fmt_m(rf['real25']) if rf else 's/d'}")
    k2 = _kpi("&#128200;", "Crecimiento vs RFCST 2026",
              _fmt_pct(var_rf, signo=True),
              f"{ETIQ_FCST} ({_fmt_m(fcst)}) vs RFCST Dic26 "
              f"({_fmt_m(rf['fcst']) if rf else 's/d'})",
              _badge(var_pp, bueno_arriba, "vs Ppto 2026"))
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
              f"Ppto 2026: {_fmt_m(rf['ppto']) if rf else 's/d'}")
    k2 = _kpi("&#128202;", f"%P-S-C {ETIQ_FCST}", _fmt_pct(pct),
              _badge(pct - pct_psc_rf if not math.isnan(pct_psc_rf) else None,
                     True, "pts vs RFCST Dic26"),
              f"RFCST Dic26: {_fmt_pct(pct_psc_rf)} · Ppto 2026: {_fmt_pct(pct_psc_ppto)}")
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
_col_pp = {"P": "Primas_PPTO26", "S": "Siniestros_PPTO26", "C": "Comisiones_PPTO26"}

for medida, cpt, _, bueno in INFO_MEDIDAS:
    charts_cfg.append({
        "el": f"ch_{cpt}_niv", "fmt": "m",
        "cats": LNS_LBL,
        "series": [
            {"n": ETIQ_FCST, "c": S1, "v": _vals(r_ln[_col_fcst[cpt]])},
            {"n": "RFCST 2026", "c": S2, "v": _vals(r_ln[_col_rf[cpt]])},
            {"n": "Ppto 2026", "c": S3, "v": _vals(r_ln[_col_pp[cpt]])},
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

sec2_bloques = []
for medida, cpt, _, _b in INFO_MEDIDAS:
    sec2_bloques.append(f"""
  <h3 class="med">{medida} · {cpt}</h3>
  <div class="grid dos2">
    <div class="card">
      <h2>{medida} por línea de negocio</h2>
      <div class="nota">{ETIQ_FCST} vs RFCST acumulado a Dic 2026 y Ppto 2026 (USD)</div>
      <div id="ch_{cpt}_niv"></div>
    </div>
    <div class="card">
      <h2>Variación vs RFCST 2026 por línea de negocio</h2>
      <div class="nota">Crecimiento implícito del {ETIQ_FCST} contra el RFCST Dic 2026.
        LN sin base comparable no se grafican.</div>
      <div id="ch_{cpt}_var"></div>
    </div>
  </div>
  <div class="grid dos2">
    <div class="card">
      <div class="chart-head">
        <h2>Estacionalidad mensual · {medida.lower()}</h2>
        <select class="sel-ln" id="sel_line_{cpt}"></select>
      </div>
      <div class="nota">% del año {ANIO_FCST} que aporta cada mes. Con el filtro en
        (Todas) se dibujan todas las LN; elige una para verla sola.</div>
      <div id="ch_line_{cpt}"></div>
    </div>
    <div class="card">
      <div class="chart-head">
        <h2>Mensualización P · S · C</h2>
        <select class="sel-ln" id="sel_ring_{cpt}"></select>
      </div>
      <div class="nota">Anillo interior = primas · medio = siniestros · exterior =
        comisiones. Filtra la LN a gusto del área de suscripción.</div>
      <div id="ch_ring_{cpt}"></div>
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

# =====================================================
# SECCION 3 - NEGOCIOS (cedente / negocio)
# =====================================================

sec3 = f"""
<section id="sec-negocios" class="cardinal">
  <div class="sec-head"><h2 class="sec-title">Negocios</h2>
    <span class="sub">Análisis a nivel cedente / negocio (correlativo del sistema).
      La base del FCST {ANIO_FCST} no trae número de contrato ni marca de MGA:
      el correlativo identifica cada negocio dentro del cedente.</span></div>
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
      sobre agregados; el crecimiento vs RFCST 2026 se calcula por cedente cuando
      la base del RFCST está disponible.</div>
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


DATA_JS = {
    "lns": LNS,
    "meses": MESES_TXT,
    "charts": charts_cfg,
    "season": {k: {c: (SEASON[k][c] if SEASON[k][c] else None)
                   for c in ("P", "S", "C")} for k in SEASON},
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
  .acciones { display: flex; justify-content: center; margin-top: 28px; }
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
__SEC2__
</section>

__SEC3__

<div class="acciones">
  <button type="button" class="btn-print" id="btn-print-ln">
    &#128424; Imprimir PDF (Línea de Negocio)
  </button>
</div>

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
    let d = '';
    s.v.forEach((v, i) => {
      if (v === null || !isFinite(v)) return;
      d += (d ? ' L ' : 'M ') + x(i) + ' ' + y(v);
    });
    if (!d) return;
    out += '<path d="' + d + '" fill="none" stroke="' + s.c +
      '" stroke-width="2" class="bar"/>';
    s.v.forEach((v, i) => {
      if (v === null || !isFinite(v)) return;
      out += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="3" fill="' + s.c +
        '" class="bar"><title>' + esc(s.n) + ' · ' + MESES[i] + ': ' +
        fmtPct(v) + '</title></circle>';
    });
  });
  out += '</svg>';
  const leyenda = '<div class="legend">' + series.map(s =>
    '<span class="lg"><i style="background:' + s.c + '"></i>' + esc(s.n) + '</span>'
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

['P', 'S', 'C'].forEach(cpt => {
  const selL = document.getElementById('sel_line_' + cpt);
  const selR = document.getElementById('sel_ring_' + cpt);

  function pintaLinea(lnSel) {
    let series;
    if (lnSel) {
      const v = DATA.season[lnSel] ? DATA.season[lnSel][cpt] : null;
      series = [{n: 'LN ' + lnSel, c: LNC[DATA.lns.indexOf(lnSel) % LNC.length], v: v || []}];
      const t = DATA.season._tot[cpt];
      if (t) series.push({n: 'Total', c: '#898781', v: t});
    } else {
      series = DATA.lns.map((ln, i) => ({
        n: 'LN ' + ln, c: LNC[i % LNC.length],
        v: (DATA.season[ln] && DATA.season[ln][cpt]) || [],
      })).filter(s => s.v && s.v.length);
    }
    lineChart('ch_line_' + cpt, series);
  }

  function pintaDona(lnSel) {
    const key = lnSel || '_tot';
    ringDonut('ch_ring_' + cpt, ringsEstacion(key), MESES, MESC,
      lnSel ? 'LN ' + lnSel : DATA.cfg.anio, 'P · S · C');
  }

  if (selL) { selLN(selL, pintaLinea); pintaLinea(''); }
  if (selR) { selLN(selR, pintaDona); pintaDona(''); }
});

// ------- Seccion 3: negocios -------
// Fila: [0 ln, 1 cedente, 2 correlativo, 3 region, 4 paises, 5 corredores,
//        6 monedas, 7 P, 8 S, 9 C, 10 Pm[12], 11 Sm[12], 12 Cm[12],
//        13 semaforo, 14 motivos]
const stateNeg = {nivel: 'ced', m: 0, exc: 2, f: {}};

const FDEF_NEG = [[0, 'LN'], [3, 'Región'], [4, 'País (cód.)'], [1, 'Cedente']];

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
    '<option value="neg"' + (stateNeg.nivel === 'neg' ? ' selected' : '') + '>Negocio (correlativo)</option>' +
    '</select></div>';
  FDEF_NEG.forEach(([k, label]) => {
    const opts = [...new Set(rowsNeg(k).map(r => String(r[k])).filter(v => v !== ''))]
      .sort((a, b) => a.localeCompare(b, 'es', {numeric: true}));
    const cur = stateNeg.f[k] || '';
    const rot = k === 1 ? nombreCed : (o => o);
    html += '<div class="flt"><label>' + label + '</label>' +
      '<select data-k="' + k + '"><option value="">(Todos)</option>' +
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
  return stateNeg.nivel === 'ced' ? ced : ced + ' · #' + r[2] + ' · LN ' + r[0];
}

function entKeyNeg(r) {
  return stateNeg.nivel === 'ced' ? r[1] : r[1] + '|' + r[2] + '|' + r[0];
}

function agrupaEntidades(rows) {
  const ents = {};
  rows.forEach(r => {
    const k = entKeyNeg(r);
    if (!ents[k]) ents[k] = {label: entLabel(r), ced: r[1], n: 0, P: 0, S: 0, C: 0,
      Pm: Array(12).fill(0), Sm: Array(12).fill(0), Cm: Array(12).fill(0),
      sem: 0, motivos: new Set(), lns: new Set(), reg: new Set()};
    const e = ents[k];
    e.n++; e.P += r[7]; e.S += r[8]; e.C += r[9];
    for (let i = 0; i < 12; i++) { e.Pm[i] += r[10][i]; e.Sm[i] += r[11][i]; e.Cm[i] += r[12][i]; }
    e.sem = Math.max(e.sem, r[13]);
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
    '<table><thead><tr><th>LN</th><th>Cedente</th><th class="num">Correlativo</th>' +
    '<th>Región</th><th class="num">Primas</th><th class="num">Siniestros</th>' +
    '<th class="num">Comisiones</th><th>Motivo</th></tr></thead><tbody>' +
    exc.map(r => '<tr><td>LN ' + esc(r[0]) + '</td><td>' + esc(nombreCed(r[1])) + '</td>' +
      '<td class="num">' + esc(r[2]) + '</td><td>' + esc(r[3]) + '</td>' +
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
    .replace("__SEC2__", "".join(sec2_bloques))
    .replace("__SEC3__", sec3)
    .replace("__INSIGHT__", insight)
    .replace("__DATA__", json.dumps(DATA_JS, separators=(",", ":"), ensure_ascii=False))
)

with open(salida_html, "w", encoding="utf-8") as fh:
    fh.write(html)

print(f"Dashboard generado: {salida_html}")

print(f"Listo en {time.perf_counter() - inicio:.1f} s")
