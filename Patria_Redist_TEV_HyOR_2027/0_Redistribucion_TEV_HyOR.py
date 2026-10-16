# -*- coding: utf-8 -*-
"""
0_Redistribucion_TEV_HyOR.py  (versión 1.2)
============================================
Redistribución de primas (GL 61), comisiones (GL 53) y, opcionalmente, siniestros (GL 54)
entre los ramos 73 (Terremoto y Erupción Volcánica, TEV) y 71 (Hidrometeorológicos y Otros
Riesgos, HyOR) en el Presupuesto Técnico, ANTES de correr CtaMens.py.

Qué hace (resumen; el detalle está en Metodologia_Redistribucion_TEV_HyOR_2027.md y la operación en README_Script_Redistribucion.md):
  1. Lee Inputs/PptoTecnico{año}.csv exactamente como lo lee CtaMens.py (pd.read_csv, thousands=',').
  2. Construye la LLAVE de negocio = ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA (misma definición que en 2026)
     y el RAMO a partir de /ERP/PROFTCTR (vía Subramo.csv si existe; si no, dígitos 2-4: A071000000 -> 71, A073000000 -> 73).
  3. Obtiene los PESOS por ramo de cada LLAVE a partir de datos observables:
       a) histórico REAL por LLAVE y ramo (Hist_Real_LLAVE_Ramo.csv/xlsx, formato largo o ancho tipo Base_1), o
       b) una tabla de pesos ya calculada (Pesos_Ramo_TEV_HyOR.xlsx, hoja "Pesos"), o
       c) una TD con el formato 2026 (TD.xlsx, hoja "TD": LLAVE, Ramo, Monto Prima, Monto Comisiones, Monto Siniestros).
     Más un Layout opcional con decisiones documentadas (EXCLUIR / INCLUIR / FORZAR con justificación obligatoria).
  4. Decide el ALCANCE sobre el año fiscal que consume CtaMens (anio_decision) con reglas objetivas: AJUSTAR (negocio cargado
     en un solo ramo cuya historia creíble muestra ambos), REVISAR (casos que requieren confirmación del negocio), NO_AJUSTAR, SIN_PESO.
  5. Redistribuye FILA A FILA: agrupa las filas de la LLAVE por "firma" (todas las columnas excepto PROFTCTR y AMOUNT) y por signo,
     suma el monto de los ramos 71+73 ("pool") y lo reparte con los pesos. Si falta el ramo destino, clona la fila cambiando sólo
     PROFTCTR. El total de cada pool se conserva EXACTAMENTE; el residuo de redondeo se asigna a la fila de mayor monto del pool.
  6. Escribe el csv redistribuido con las MISMAS columnas y orden que el original (utf-8-sig), un libro de trazabilidad, el detalle
     fila a fila en csv y un log. Se detiene, sin escribir el csv, si algún control de cuadre falla.

Uso (rutas por defecto al estilo de CtaMens.py; todas se pueden sobreescribir por línea de comandos):
  python 0_Redistribucion_TEV_HyOR.py                      -> corre con los parámetros de abajo
  python 0_Redistribucion_TEV_HyOR.py --dry-run            -> sólo diagnóstico (alcance y pesos), no escribe el csv
  python 0_Redistribucion_TEV_HyOR.py --help               -> todas las opciones
"""

import argparse
import getpass
import hashlib
import logging
import os
import shutil
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

VERSION = "1.2"

# =============================================================================
# PARÁMETROS (editar aquí o pasar por línea de comandos)
# =============================================================================
zAño = 2027
usuario = getpass.getuser()
xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\{zAño}\5_Generacion"

DEFAULTS = {
    # --- Entradas ---
    "ppto":    fr"{xFolder}\Inputs\PptoTecnico{zAño}.csv",                           # mismo archivo que lee CtaMens.py
    "hist":    fr"{xFolder}\Inputs\Redistribucion\Hist_Real_LLAVE_Ramo.csv",          # histórico real (largo o ancho)
    "pesos":   fr"{xFolder}\Inputs\Redistribucion\Pesos_Ramo_TEV_HyOR.xlsx",          # alternativa: pesos ya calculados
    "td":      fr"{xFolder}\Inputs\Redistribucion\TD.xlsx",                           # alternativa: TD formato 2026
    "layout":  fr"{xFolder}\Inputs\Redistribucion\Layout_Redistribucion.xlsx",        # decisiones documentadas (opcional)
    "subramo": fr"{xFolder}\Inputs\Subramo.csv",                                      # CeBe -> Ramo, Ramo2 (recomendado)
    # --- Insumos de CtaMens para las verificaciones previas (opcionales: si el archivo existe se usa) ---
    "pais":        fr"{xFolder}\Inputs\Pais.csv",
    "cesion":      fr"{xFolder}\Inputs\Cesion.csv",
    "cesionpi":    fr"{xFolder}\Inputs\CesionPI.csv",
    "cesion_hist": fr"{xFolder}\Inputs\Porc_Cesión_Hist.xlsx",
    "matxl":       fr"{xFolder}\2_CostosXL\xMatCostoXL.xlsx",
    "dncostoxl":   fr"{xFolder}\2_CostosXL\xDnCostoXL.xlsx",
    "dnrecup":     fr"{xFolder}\2_CostosXL\xDnRecup.xlsx",
    "evcat":       fr"{xFolder}\3_EvCat\xDnEvCat.xlsx",
    "attritional": fr"{xFolder}\3_EvCat\xDnAttritional.xlsx",
    # --- Salidas ---
    "salida":  fr"{xFolder}\Inputs\PptoTecnico{zAño}_Red.csv",
    "out_dir": fr"{xFolder}\Outputs\Redistribucion_TEV_HyOR",
    # --- Metodología ---
    "ramos": [71, 73],              # ramos entre los que se redistribuye (bidireccional)
    "anio_decision": zAño,          # año fiscal sobre el que se decide el alcance (el que filtra CtaMens); el reparto aplica a anios_fiscales
    "anios_base": [2025, 2026],     # años del histórico real que alimentan los pesos (un año parcial se excluye si trae menos de min_meses_anio meses)
    "metodo_pesos": "ponderado",    # 'ponderado' (suma de |montos| de los años base válidos) | 'ultimo' (último año válido) | 'promedio_simple'
    "min_meses_anio": 8,            # si el histórico trae el mes: un año base con menos meses registrados se excluye (precedente 2026: INCOMPLETE_MONTHS < 8)
    "tolerancia": 0.05,             # 5 puntos porcentuales de diferencia entre participación presupuestada y de los pesos
    "modo_alcance": "auto",         # 'auto' (reglas + layout) | 'layout' (sólo LLAVEs del layout)
    "ajustar_split_explicito": False,   # False: una LLAVE que YA trae ambos ramos (partición explícita del cargador) queda en REVISAR
    "reclasificacion_total": "revisar", # 'revisar': histórico >= 1-tolerancia en un ramo vs presupuesto >= 1-tolerancia en el otro -> REVISAR | 'auto'
    "materialidad": 0.0,            # |prima 71+73| mínima (MXN) en el año de decisión para ajustar; 0 = sin filtro (precedente 2026: 100,000 MXN)
    "credibilidad_pct": 0.10,       # REVISAR si |prima histórica base| < credibilidad_pct x |prima presupuestada del año de decisión| (o < materialidad)
    "banda_ratio": [1 / 3.0, 3.0],  # REVISAR si |prima presupuestada| / |prima del último año real| queda fuera de la banda
    "revisar_sensibles": True,      # REVISAR si los tres métodos de peso difieren más que la tolerancia o hay cambio estructural entre años base
    "revisar_facultativos": True,   # ZTIPOREAS = 3 (la LLAVE agrupa varios contratos/corredores) -> REVISAR
    "excluir_funcarea": ["LN04004"],    # LN cuyo PROFTCTR reescribe CtaMens (CAT_LN4004): fuera de alcance
    "comisiones": "propio",         # 'propio' (pesos propios de GL 53; si no hay usa los de primas) | 'prima' | 'no'
    "siniestros": "prima",          # 'prima' (pesos de primas) | 'propio' | 'no' (no se tocan, como en 2026)
    "anios_fiscales": "todos",      # 'todos' | lista p.ej. [2027]
    "conservar_filas_cero": True,   # True: una fila cuyo ramo queda con peso 0 se escribe con monto 0 (CtaMens la ignora; el _ID se mantiene estable)
    "decimales": 2,                 # redondeo de montos nuevos; si el insumo trae más decimales se usa el máximo observado
    "max_filas_excel_detalle": 200000,  # Detalle_Filas se incluye en el xlsx sólo hasta este tamaño (siempre va en csv)
    "sobrescribir_input": False,    # True: respalda el original en Backups/ y escribe el redistribuido con el nombre original
    "aprobacion": "",               # corrida productiva: responsable y fecha que aprobaron parámetros y layout (queda en Resumen)
    "dry_run": False,
}

TIPO_POR_GL = {"61": "Primas", "53": "Comisiones", "54": "Siniestros"}
TIPOS = ["Primas", "Comisiones", "Siniestros"]
PESOS_COLS = ["LLAVE", "TIPO", "RAMO", "PESO", "MONTO_BASE", "FUENTE", "DETALLE", "ORIGEN_PESO", "VALIDO", "MOTIVO",
              "N_ANIOS_VALIDOS", "ULTIMO_ANIO", "MONTO_ULTIMO_ANIO", "CAMBIO_ESTRUCTURAL"]
METODOS = ["ponderado", "ultimo", "promedio_simple"]
DEC_PESO = 10  # decimales a los que se redondean los pesos (reproducibilidad)

# Nombres de columnas (con alias para tolerar el formato 2026 sin prefijos SAP)
ALIAS = {
    "PROF":  ["/ERP/PROFTCTR", "PROFTCTR", "CeBe"],
    "AMT":   ["/ERP/AMOUNT", "AMOUNT", "MONTO"],
    "AMT_T": ["/ERP/AMOUNT_T", "AMOUNT_T"],
    "GL":    ["/ERP/GL_ACCT", "GL_ACCT", "TY"],
    "FUNC":  ["/ERP/FUNCAREA", "FUNCAREA", "LN"],
    "FY":    ["0FISCYEAR", "FISCYEAR"],
    "MES":   ["0CALMONTH", "CALMONTH", "PERIODO"],
    "TIPOREA": ["ZTIPOREAS", "TipoRea"],
    "CED":   ["ZCEDENTE", "CiaTom"],
    "CTO":   ["ZCONTRATO", "CtoTom"],
    "REG":   ["ZREGIONRP"],
    "CORR":  ["ZCORREDOR"],
    "SUSC":  ["ZSUSCYEAR"],
}


class ErrorRedistribucion(Exception):
    """Error de negocio con mensaje claro para el analista."""


# =============================================================================
# UTILIDADES
# =============================================================================
def setup_logger(out_dir, ts):
    os.makedirs(out_dir, exist_ok=True)
    log = logging.getLogger("redist")
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        h.close()
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); log.addHandler(sh)
    fh = logging.FileHandler(os.path.join(out_dir, f"Log_Redistribucion_{ts}.txt"), encoding="utf-8")
    fh.setFormatter(fmt); log.addHandler(fh)
    return log


def logger_silencioso():
    q = logging.getLogger("redist.quiet"); q.propagate = False; q.handlers.clear(); q.addHandler(logging.NullHandler())
    return q


def col(df, key, obligatoria=True):
    """Devuelve el nombre real de la columna según sus alias."""
    for c in ALIAS[key]:
        if c in df.columns:
            return c
    if obligatoria:
        raise ErrorRedistribucion(f"No se encontró ninguna de las columnas {ALIAS[key]} en el archivo (columnas: {list(df.columns)[:12]}...).")
    return None


def leer_tabla(path, hoja=0, header=0):
    """Lee csv (thousands=',', utf-8 o latin-1) o Excel. Devuelve (df, descripcion)."""
    if not os.path.isfile(path):
        raise ErrorRedistribucion(f"No existe el archivo: {path}")
    low = path.lower()
    if low.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(path, sheet_name=hoja, header=header, engine="openpyxl"), "excel"
    try:
        df = pd.read_csv(path, thousands=",", header=header); enc = "utf-8"
    except UnicodeDecodeError:
        df = pd.read_csv(path, thousands=",", encoding="latin-1", header=header); enc = "latin-1"
    if df.shape[1] == 1 and ";" in str(df.columns[0]):
        raise ErrorRedistribucion(f"El archivo {path} parece usar ';' como separador; CtaMens y este script esperan ','.")
    return df, enc


def existe(p, k):
    return bool(p.get(k)) and os.path.isfile(p[k])


def a_num_estricto(serie, nombre, contexto, permitir_vacios=True):
    """pd.to_numeric que ABORTA si un valor no vacío no es numérico (p.ej. '-4,000' leído como texto)."""
    s = serie.copy()
    if s.dtype == object or str(s.dtype) in ("string", "str"):
        s = s.astype(str).str.strip().str.replace(",", "", regex=False)
        s = s.where(~s.isin(["", "nan", "None", "NaN", "<NA>"]), np.nan)
    num = pd.to_numeric(s, errors="coerce")
    malos = num.isna() & s.notna()
    if malos.any():
        ej = serie[malos].astype(str).head(5).tolist()
        raise ErrorRedistribucion(f"{contexto}: la columna {nombre} tiene {int(malos.sum())} valores no numéricos, p.ej. {ej}. Corrija el archivo (sin texto, sin símbolos).")
    if not permitir_vacios and num.isna().any():
        raise ErrorRedistribucion(f"{contexto}: la columna {nombre} tiene {int(num.isna().sum())} valores vacíos.")
    return num.astype("float64")


def a_int_str(s):
    """Serie numérica (posiblemente con NaN) -> texto entero; NaN -> '0' (misma regla que CtaMens.py)."""
    return pd.to_numeric(s, errors="coerce").fillna(0).round(0).astype("int64").astype(str)


def _tramo(t):
    t = str(t).strip()
    if t == "" or t.lower() in ("nan", "none"):
        return "0"  # contrato nulo: misma regla que CtaMens (2026, 3.1, lo escribía vacío)
    try:
        f = float(t)
        if f == int(f):
            return str(int(f))
        return t
    except ValueError:
        return t.upper()


def normalizar_llave(serie):
    """Texto 'TipoRea-Cedente-Contrato-LN' -> forma canónica ('1-4.0--ln04001 ' -> '1-4-0-LN04001')."""
    return serie.astype(str).str.strip().map(lambda s: "-".join(_tramo(x) for x in s.split("-")) if s and s.lower() != "nan" else "")


def construir_llave(df, c_tiporea, c_ced, c_cto, c_func):
    """LLAVE = ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA (definición 2026: 1.1 y 3.1)."""
    return (a_int_str(df[c_tiporea]) + "-" + a_int_str(df[c_ced]) + "-" + a_int_str(df[c_cto]) + "-"
            + df[c_func].astype(str).str.strip().str.upper())


def ramo_desde_proftctr(serie, subramo_df=None, columna="Ramo"):
    """Ramo numérico a partir del centro de beneficio. Prioridad: Subramo.csv (CeBe->Ramo/Ramo2); si no, dígitos 2-4 ('A071000000' -> 71)."""
    s = serie.astype(str).str.strip()
    ramo = pd.Series(np.nan, index=serie.index, dtype="float64")
    if subramo_df is not None and {"CeBe", columna}.issubset(subramo_df.columns):
        m = (subramo_df.dropna(subset=["CeBe"]).drop_duplicates("CeBe").assign(CeBe=lambda d: d["CeBe"].astype(str).str.strip())
             .set_index("CeBe")[columna])
        ramo = s.map(pd.to_numeric(m, errors="coerce"))
    faltan = ramo.isna()
    if faltan.any():
        ramo.loc[faltan] = pd.to_numeric(s[faltan].str[1:4], errors="coerce")
    return ramo


def ramo_desde_texto(v):
    """'Terremoto'/'TEV' -> 73 ; 'HYORH'/'HyOR'/'Hidro...' -> 71 ; número -> número ; otro -> NaN"""
    if pd.isna(v):
        return np.nan
    s = str(v).strip().lower()
    if s.startswith("terr") or s == "tev":
        return 73
    if s.startswith("hyor") or s.startswith("hidro") or s.startswith("hyo"):
        return 71
    try:
        return float(s)
    except ValueError:
        return np.nan


def normalizar_tipo(v):
    """'61'/'53'/'54', '6108010000', 'Primas', 'PmaTom', etc. -> 'Primas'|'Comisiones'|'Siniestros'|None"""
    if pd.isna(v):
        return None
    s = str(v).strip().lower()
    if s.endswith(".0"):
        s = s[:-2]
    if s[:2] in TIPO_POR_GL:
        return TIPO_POR_GL[s[:2]]
    if s.startswith("prima") or s.startswith("pma"):
        return "Primas"
    if s.startswith("comi") or s.startswith("com") or s.startswith("cos"):
        return "Comisiones"
    if s.startswith("sini") or s.startswith("sin"):
        return "Siniestros"
    return None


def marco_pesos_vacio():
    base = {"LLAVE": str, "TIPO": str, "RAMO": int, "PESO": float, "MONTO_BASE": float, "FUENTE": str, "DETALLE": str, "ORIGEN_PESO": str,
            "VALIDO": bool, "MOTIVO": str, "N_ANIOS_VALIDOS": float, "ULTIMO_ANIO": float, "MONTO_ULTIMO_ANIO": float, "CAMBIO_ESTRUCTURAL": bool}
    return pd.DataFrame({k: pd.Series(dtype=v) for k, v in base.items()})


def completar_columnas_pesos(t):
    t = t.copy()
    for c in PESOS_COLS:
        if c not in t.columns:
            t[c] = np.nan if c in ("N_ANIOS_VALIDOS", "ULTIMO_ANIO", "MONTO_ULTIMO_ANIO", "MONTO_BASE", "PESO") else ("" if c in ("DETALLE", "MOTIVO") else (False if c == "CAMBIO_ESTRUCTURAL" else t.get(c)))
    return t[PESOS_COLS]


def redondear_pesos(pesos):
    """Redondea los pesos a DEC_PESO decimales y renormaliza: el ramo de mayor peso recibe 1 - suma(resto)."""
    if pesos.empty:
        return pesos
    p = pesos.copy()
    p["PESO"] = pd.to_numeric(p["PESO"], errors="coerce")
    val = p["VALIDO"].astype(bool)
    p.loc[val, "PESO"] = p.loc[val, "PESO"].round(DEC_PESO)
    idx_max = p[val].sort_values("PESO", ascending=False).drop_duplicates(["LLAVE", "TIPO"]).index
    suma = p[val].groupby(["LLAVE", "TIPO"])["PESO"].transform("sum")
    resto = (suma - p.loc[val, "PESO"])
    p.loc[idx_max, "PESO"] = (1.0 - resto.loc[idx_max]).round(DEC_PESO)
    return p


def sha256_archivo(path):
    hsh = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            hsh.update(chunk)
    return hsh.hexdigest()


def max_decimales(serie, tope=6):
    """Máximo número de decimales presente en una serie numérica (hasta `tope`)."""
    s = serie.dropna().abs()
    for d in range(0, tope + 1):
        if ((s * 10 ** d).round(6) % 1 == 0).all():
            return d
    return tope


# =============================================================================
# PESOS
# =============================================================================
def _detectar(up, candidatos):
    return next((up[k] for k in candidatos if k in up), None)


def preparar_hist(hist, ramos, log):
    """
    Normaliza el histórico real: devuelve (h, meses) con
      h     = LLAVE, RAMO, TIPO, ANIO, MONTO (agregado por año; todos los años, sin filtrar por años base)
      meses = (LLAVE, TIPO, ANIO) -> número de meses distintos registrados (None si el histórico no trae mes)
    Acepta: LLAVE o sus 4 componentes; RAMO numérico, PROFTCTR/CeBe o DescRamo texto; ANIO/AñoCont o CALMONTH/PERIODO (AAAAMM);
    GL/TIPO/TY + MONTO, o formato ancho tipo Base_1 (PmaTom/CosTom/SinTom); columna Mes opcional.
    """
    h = hist.copy()
    h.columns = [str(c).strip() for c in h.columns]
    up = {c.upper(): c for c in h.columns}
    ctx = "Histórico"
    if "LLAVE" in up:
        h["LLAVE"] = normalizar_llave(h[up["LLAVE"]])
    else:
        alt = {"ZTIPOREAS": ["ZTIPOREAS", "TIPOREA"], "ZCEDENTE": ["ZCEDENTE", "CIATOM"], "ZCONTRATO": ["ZCONTRATO", "CTOTOM"],
               "FUNCAREA": ["FUNCAREA", "/ERP/FUNCAREA", "LN"]}
        got = {k: _detectar(up, v) for k, v in alt.items()}
        if any(v is None for v in got.values()):
            raise ErrorRedistribucion(f"{ctx}: necesita LLAVE o las 4 columnas ZTIPOREAS, ZCEDENTE, ZCONTRATO, FUNCAREA (encontradas: {got}).")
        for k in ["ZTIPOREAS", "ZCEDENTE", "ZCONTRATO"]:
            h[got[k]] = a_num_estricto(h[got[k]], got[k], ctx)
        h["LLAVE"] = construir_llave(h, got["ZTIPOREAS"], got["ZCEDENTE"], got["ZCONTRATO"], got["FUNCAREA"])
    if "RAMO" in up and pd.to_numeric(h[up["RAMO"]], errors="coerce").notna().any():
        h["RAMO"] = a_num_estricto(h[up["RAMO"]], "RAMO", ctx)
    else:
        cprof = _detectar(up, ["PROFTCTR", "/ERP/PROFTCTR", "CEBE"])
        ctxt = _detectar(up, ["DESCRAMO", "RAMON", "RAMO_DESC", "DESC_RAMO", "RAMO"])
        if cprof is not None:
            h["RAMO"] = ramo_desde_proftctr(h[cprof])
        elif ctxt is not None:
            h["RAMO"] = h[ctxt].map(ramo_desde_texto)
        else:
            raise ErrorRedistribucion(f"{ctx}: necesita RAMO, PROFTCTR/CeBe o DescRamo.")
    # periodo: año y, si existe, mes
    canio = _detectar(up, ["ANIO", "AÑO", "ANO", "YEAR", "0FISCYEAR", "FISCYEAR", "AÑOCONT", "ANIOCONT", "AÑO CONTABLE", "AÑO_CONT", "ANIO_CONT", "0CALYEAR", "CALYEAR"])
    if canio is None:
        canio = next((up[k] for k in up if k.startswith(("AÑO", "ANIO", "YEAR"))), None)
    cmes_full = _detectar(up, ["CALMONTH", "0CALMONTH", "PERIODO", "MES_CONTABLE"])
    cmes = _detectar(up, ["MES", "MONTH", "0CALMONTH2"])
    h["MES"] = np.nan
    if canio is not None:
        h["ANIO"] = a_num_estricto(h[canio], canio, ctx)
        if cmes is not None:
            h["MES"] = a_num_estricto(h[cmes], cmes, ctx)
        elif cmes_full is not None:
            per = a_num_estricto(h[cmes_full], cmes_full, ctx)
            h["MES"] = np.where(per > 9999, per % 100, np.nan)
    else:
        if cmes_full is None:
            raise ErrorRedistribucion(f"{ctx}: necesita ANIO (o CALMONTH/PERIODO numérico AAAAMM para derivarlo).")
        per = a_num_estricto(h[cmes_full], cmes_full, ctx)
        h["ANIO"] = np.where(per > 9999, per // 100, per)
        h["MES"] = np.where(per > 9999, per % 100, np.nan)
    # cuenta y monto (largo o ancho)
    if _detectar(up, ["TIPO", "GL", "GL_ACCT", "/ERP/GL_ACCT", "CUENTA", "TY", "GL2"]) is None:
        anchas = {}
        for k, tipo in [("PMATOM", "Primas"), ("PRIMAS", "Primas"), ("PRIMA", "Primas"), ("MONTO PRIMA", "Primas"),
                        ("COMTOM", "Comisiones"), ("COSTOM", "Comisiones"), ("COMISIONES", "Comisiones"), ("MONTO COMISIONES", "Comisiones"),
                        ("SINTOM", "Siniestros"), ("SINIESTROS", "Siniestros"), ("MONTO SINIESTROS", "Siniestros")]:
            if k in up and tipo not in anchas.values():
                anchas[up[k]] = tipo
        if not anchas:
            raise ErrorRedistribucion(f"{ctx}: necesita TIPO/GL (61/53/54 o Primas/Comisiones/Siniestros) o columnas anchas PmaTom/CosTom/SinTom.")
        for c in anchas:
            h[c] = a_num_estricto(h[c], c, ctx)
        ids = [c for c in h.columns if c not in anchas]
        h = h.melt(id_vars=ids, value_vars=list(anchas), var_name="TIPO", value_name="MONTO")
        h["TIPO"] = h["TIPO"].map(anchas)
        log.info("Histórico en formato ancho: columnas %s convertidas a largo", list(anchas))
    else:
        ctipo = _detectar(up, ["TIPO", "GL", "GL_ACCT", "/ERP/GL_ACCT", "CUENTA", "TY", "GL2"])
        h["TIPO"] = h[ctipo].map(normalizar_tipo)
        cmonto = _detectar(up, ["MONTO", "AMOUNT", "/ERP/AMOUNT", "IMPORTE", "MONTO_REAL"])
        if cmonto is None:
            raise ErrorRedistribucion(f"{ctx}: necesita MONTO.")
        h["MONTO"] = a_num_estricto(h[cmonto], cmonto, ctx)
    h["MONTO"] = pd.to_numeric(h["MONTO"], errors="coerce").fillna(0.0)
    presentes = {"años": sorted(h["ANIO"].dropna().astype(int).unique().tolist()), "ramos": sorted(h["RAMO"].dropna().unique().tolist()),
                 "tipos": sorted(h["TIPO"].dropna().unique().tolist())}
    h = h[h["RAMO"].isin(ramos) & h["TIPO"].notna() & h["ANIO"].notna() & (h["LLAVE"] != "")]
    if h.empty:
        raise ErrorRedistribucion(f"{ctx}: ninguna fila cae en ramos {ramos} con tipo de cuenta reconocido. Presentes en el archivo: {presentes}.")
    meses = None
    if h["MES"].notna().any():
        meses = (h[h["MONTO"] != 0].dropna(subset=["MES"]).groupby(["LLAVE", "TIPO", "ANIO"])["MES"].nunique().rename("N_MESES"))
        meses.index = meses.index.set_levels(meses.index.levels[2].astype(int), level=2)
    h = h.groupby(["LLAVE", "RAMO", "TIPO", "ANIO"], as_index=False)["MONTO"].sum()
    h["ANIO"] = h["ANIO"].astype(int)
    log.info("Histórico normalizado: %s filas LLAVE-ramo-tipo-año | LLAVEs: %s | años: %s | con detalle mensual: %s | suma MONTO por tipo y ramo:\n%s",
             len(h), h["LLAVE"].nunique(), sorted(h["ANIO"].unique().tolist()), meses is not None,
             h.pivot_table(index="TIPO", columns="RAMO", values="MONTO", aggfunc="sum").round(2).to_string())
    return h, meses


def _wide_hist(h, ramos):
    """(LLAVE, TIPO, ANIO) x ramo con validez por año: signos consistentes entre ramos y suma distinta de cero."""
    wide = (h.pivot_table(index=["LLAVE", "TIPO", "ANIO"], columns="RAMO", values="MONTO", aggfunc="sum").reindex(columns=ramos).fillna(0.0))
    signo_ok = (wide.min(axis=1) >= 0) | (wide.max(axis=1) <= 0)
    no_cero = wide.abs().sum(axis=1) > 0
    return wide, signo_ok, no_cero


def tolerancia_sugerida(h, ramos, log):
    """Diagnóstico: p90 del rango interanual de la participación del ramo mayor (Primas) en LLAVEs con >=3 años válidos y ambos ramos > 0."""
    wide, ok, nz = _wide_hist(h[h["TIPO"] == "Primas"], ramos)
    w = wide[ok & nz].abs()
    w = w[(w > 0).all(axis=1)]
    if w.empty:
        return None
    sh = (w[max(ramos)] / w.sum(axis=1)).rename("SHARE").reset_index()
    g = sh.groupby("LLAVE")["SHARE"].agg(["count", "max", "min"])
    g = g[g["count"] >= 3]
    if g.empty:
        return None
    p90 = float(np.percentile(g["max"] - g["min"], 90))
    log.info("Tolerancia sugerida por el dato (p90 del rango interanual de la participación %s en %s LLAVEs con >=3 años y ambos ramos): %.4f (piso 0.01)",
             max(ramos), len(g), max(p90, 0.01))
    return max(p90, 0.01)


def pesos_desde_hist(h, meses, ramos, anios_base, metodo, min_meses, log):
    """
    Pesos por LLAVE-tipo-ramo a partir del histórico normalizado, restringido a los años base.
    Un año cuenta sólo si (a) todos sus montos por ramo tienen el mismo signo, (b) no suman cero y (c) si hay detalle mensual, tiene
    al menos min_meses meses registrados. Los años excluidos quedan en MOTIVO. Sin año válido -> VALIDO=False.
    También reporta N_ANIOS_VALIDOS, ULTIMO_ANIO, MONTO_ULTIMO_ANIO y CAMBIO_ESTRUCTURAL (un año válido mono-ramo y otro bi-ramo).
    """
    ctx = "Histórico"
    presentes = sorted(h["ANIO"].unique().tolist())
    h = h[h["ANIO"].isin(anios_base)]
    if h.empty:
        raise ErrorRedistribucion(f"{ctx}: ningún registro en los años base {anios_base}; años presentes: {presentes}. Revise --anios-base.")
    wide, signo_ok, no_cero = _wide_hist(h, ramos)
    completo = pd.Series(True, index=wide.index)
    if meses is not None:
        nm = meses.reindex(wide.index)
        completo = nm.isna() | (nm >= min_meses)
    valido_anio = signo_ok & no_cero & completo
    excl = wide[~valido_anio].reset_index()[["LLAVE", "TIPO", "ANIO"]].copy()
    por = np.where(~signo_ok[~valido_anio].values, "signos opuestos entre ramos", np.where(~no_cero[~valido_anio].values, "suma cero", f"menos de {min_meses} meses registrados"))
    excl["POR"] = por
    motivos_excl = (excl.assign(txt=lambda d: "año " + d["ANIO"].astype(int).astype(str) + " excluido (" + d["POR"] + ")")
                        .groupby(["LLAVE", "TIPO"])["txt"].agg("; ".join)) if len(excl) else pd.Series(dtype=str)
    w = wide[valido_anio].abs()
    filas = []
    if not w.empty:
        g = w.reset_index().groupby(["LLAVE", "TIPO"])
        n_anios = g["ANIO"].nunique()
        ult = w.reset_index().sort_values("ANIO").drop_duplicates(["LLAVE", "TIPO"], keep="last").set_index(["LLAVE", "TIPO"])
        ultimo_anio = ult["ANIO"]; monto_ultimo = ult[ramos].sum(axis=1)
        mono = (w > 0).sum(axis=1) == 1
        bi = (w > 0).sum(axis=1) == len(ramos)
        cambio = (mono.groupby(level=["LLAVE", "TIPO"]).any() & bi.groupby(level=["LLAVE", "TIPO"]).any())
        if metodo == "ultimo":
            montos = ult[ramos]
            pesos = montos.div(montos.sum(axis=1), axis=0)
            detalle = "último año válido con datos: " + ult["ANIO"].astype(int).astype(str)
        elif metodo == "promedio_simple":
            shares = w.div(w.sum(axis=1), axis=0)
            pesos = shares.groupby(level=["LLAVE", "TIPO"]).mean()
            montos = w.groupby(level=["LLAVE", "TIPO"]).sum()
            anios = g["ANIO"].agg(lambda s: str(sorted(s.astype(int).tolist())))
            detalle = "promedio simple de participaciones anuales, años " + anios
        else:
            montos = w.groupby(level=["LLAVE", "TIPO"]).sum()
            pesos = montos.div(montos.sum(axis=1), axis=0)
            anios = g["ANIO"].agg(lambda s: str(sorted(s.astype(int).tolist())))
            detalle = "suma de |montos| de los años " + anios
            metodo = "ponderado"
        for r in ramos:
            idx = pesos.index
            filas.append(pd.DataFrame({"LLAVE": idx.get_level_values(0), "TIPO": idx.get_level_values(1), "RAMO": int(r),
                                       "PESO": pesos[r].values, "MONTO_BASE": montos[r].reindex(idx).values, "FUENTE": f"HIST_{metodo}",
                                       "DETALLE": detalle.reindex(idx).values, "ORIGEN_PESO": "propio", "VALIDO": True, "MOTIVO": "",
                                       "N_ANIOS_VALIDOS": n_anios.reindex(idx).values, "ULTIMO_ANIO": ultimo_anio.reindex(idx).values,
                                       "MONTO_ULTIMO_ANIO": monto_ultimo.reindex(idx).values, "CAMBIO_ESTRUCTURAL": cambio.reindex(idx).values}))
    out = pd.concat(filas, ignore_index=True) if filas else marco_pesos_vacio()
    sin_valido = set(motivos_excl.index) - set(zip(out["LLAVE"], out["TIPO"]))
    if sin_valido:
        inv = pd.DataFrame([{"LLAVE": l, "TIPO": t, "RAMO": int(r), "PESO": np.nan, "MONTO_BASE": np.nan, "FUENTE": f"HIST_{metodo}", "DETALLE": "",
                             "ORIGEN_PESO": "propio", "VALIDO": False, "MOTIVO": "sin año válido: " + motivos_excl.loc[(l, t)], "N_ANIOS_VALIDOS": 0,
                             "ULTIMO_ANIO": np.nan, "MONTO_ULTIMO_ANIO": np.nan, "CAMBIO_ESTRUCTURAL": False} for (l, t) in sin_valido for r in ramos])
        out = pd.concat([out, inv], ignore_index=True)
    if len(motivos_excl):
        key = list(zip(out["LLAVE"], out["TIPO"]))
        mot = pd.Series(key).map(lambda k: motivos_excl.get(k, "")).values
        out["MOTIVO"] = np.where(out["VALIDO"], mot, out["MOTIVO"])
    log.info("Pesos desde histórico (%s, años base %s): %s LLAVE-tipo válidas, %s inválidas, %s años excluidos (reversas/suma cero/meses incompletos), %s con cambio estructural",
             metodo, anios_base, int(out[out["VALIDO"]].groupby(["LLAVE", "TIPO"]).ngroups) if len(out) else 0, len(sin_valido), len(excl),
             int(out[out["VALIDO"] & out["CAMBIO_ESTRUCTURAL"].astype(bool)].groupby(["LLAVE", "TIPO"]).ngroups) if len(out) else 0)
    return completar_columnas_pesos(out)


def pesos_desde_td(td, ramos, log):
    """TD formato 2026 (LLAVE, Ramo, Monto Prima, Monto Comisiones, Monto Siniestros) -> pesos por tipo (|montos| con signo consistente)."""
    t = td.copy(); t.columns = [str(c).strip() for c in t.columns]
    for c in ["LLAVE", "Ramo"]:
        if c not in t.columns:
            raise ErrorRedistribucion(f"TD: falta la columna {c}.")
    t["LLAVE"] = normalizar_llave(t["LLAVE"])
    t["RAMO"] = a_num_estricto(t["Ramo"], "Ramo", "TD")
    t = t[t["RAMO"].isin(ramos)]
    mapa = {"Primas": "Monto Prima", "Comisiones": "Monto Comisiones", "Siniestros": "Monto Siniestros"}
    filas = []
    for tipo, c in mapa.items():
        if c not in t.columns:
            continue
        t[c] = a_num_estricto(t[c], c, "TD").fillna(0.0)
        m = t.pivot_table(index="LLAVE", columns="RAMO", values=c, aggfunc="sum").reindex(columns=ramos).fillna(0.0)
        m = m[m.abs().sum(axis=1) > 0]
        ok = (m.min(axis=1) >= 0) | (m.max(axis=1) <= 0)
        p = m.abs().div(m.abs().sum(axis=1), axis=0)
        for r in ramos:
            filas.append(pd.DataFrame({"LLAVE": m.index, "TIPO": tipo, "RAMO": int(r), "PESO": np.where(ok, p[r], np.nan), "MONTO_BASE": m[r].values,
                                       "FUENTE": "TD_2026", "DETALLE": "montos de TD.xlsx", "ORIGEN_PESO": "propio", "VALIDO": ok.values,
                                       "MOTIVO": np.where(ok, "", "signos opuestos entre ramos")}))
    out = pd.concat(filas, ignore_index=True) if filas else marco_pesos_vacio()
    if out.empty:
        raise ErrorRedistribucion("TD: no se obtuvo ningún peso (revise columnas 'Monto Prima'/'Monto Comisiones'/'Monto Siniestros' y los ramos).")
    return completar_columnas_pesos(out)


def pesos_desde_tabla(tab, ramos, log):
    """Tabla de pesos ya calculada (hoja 'Pesos'): LLAVE, RAMO, TIPO, PESO, [FUENTE, DETALLE, ORIGEN_PESO, ...]."""
    t = tab.copy(); t.columns = [str(c).strip() for c in t.columns]
    for c in ["LLAVE", "RAMO", "TIPO", "PESO"]:
        if c not in t.columns:
            raise ErrorRedistribucion(f"La tabla de pesos necesita la columna {c}.")
    t["LLAVE"] = normalizar_llave(t["LLAVE"])
    t["RAMO"] = a_num_estricto(t["RAMO"], "RAMO", "Tabla de pesos")
    t["TIPO"] = t["TIPO"].map(normalizar_tipo)
    t["PESO"] = a_num_estricto(t["PESO"], "PESO", "Tabla de pesos")
    t = t[t["RAMO"].isin(ramos) & t["TIPO"].notna() & (t["LLAVE"] != "")]
    if t.duplicated(["LLAVE", "TIPO", "RAMO"]).any():
        d = t[t.duplicated(["LLAVE", "TIPO", "RAMO"], keep=False)][["LLAVE", "TIPO", "RAMO"]].drop_duplicates().head(5)
        raise ErrorRedistribucion(f"Tabla de pesos: hay (LLAVE, TIPO, RAMO) repetidos, p.ej.\n{d.to_string(index=False)}")
    for c, v in [("FUENTE", "TABLA_PESOS"), ("DETALLE", ""), ("ORIGEN_PESO", "propio")]:
        if c not in t.columns:
            t[c] = v
        t[c] = t[c].fillna(v).astype(str)
    s = t.groupby(["LLAVE", "TIPO"])["PESO"].agg(["sum", "min"])
    bad = s[((s["sum"] - 1).abs() > 1e-6) | (s["min"] < 0)].index
    t["VALIDO"] = ~t.set_index(["LLAVE", "TIPO"]).index.isin(bad)
    t["MOTIVO"] = np.where(t["VALIDO"], "", "los pesos no suman 1 o hay negativos")
    t["RAMO"] = t["RAMO"].astype(int)
    if t.empty:
        raise ErrorRedistribucion("Tabla de pesos: no quedó ninguna fila útil (revise RAMO, TIPO y LLAVE).")
    return completar_columnas_pesos(t)


def completar_pesos(pesos, ramos):
    """Asegura que cada (LLAVE, TIPO) válida tenga una fila por ramo (ramo ausente -> peso 0) y redondea/renormaliza."""
    if pesos.empty:
        return marco_pesos_vacio()
    pesos = completar_columnas_pesos(pesos)
    pesos["VALIDO"] = pesos["VALIDO"].astype("boolean").fillna(False).astype(bool)
    pesos["PESO"] = pd.to_numeric(pesos["PESO"], errors="coerce")
    pesos["RAMO"] = pd.to_numeric(pesos["RAMO"], errors="coerce").astype(int)
    pesos["MOTIVO"] = pesos["MOTIVO"].fillna("").astype(str)
    base = pesos[pesos["VALIDO"]][["LLAVE", "TIPO"]].drop_duplicates()
    cross = base.merge(pd.DataFrame({"RAMO": ramos}), how="cross")
    out = cross.merge(pesos, on=["LLAVE", "TIPO", "RAMO"], how="left", validate="1:1")
    falt = out["PESO"].isna()
    out.loc[falt, "PESO"] = 0.0
    out.loc[falt, "VALIDO"] = True
    for c in ["FUENTE", "DETALLE", "ORIGEN_PESO", "MOTIVO", "N_ANIOS_VALIDOS", "ULTIMO_ANIO", "MONTO_ULTIMO_ANIO", "CAMBIO_ESTRUCTURAL"]:
        out[c] = out.groupby(["LLAVE", "TIPO"])[c].transform(lambda s: s.ffill().bfill())
    out.loc[falt, "MONTO_BASE"] = 0.0
    out["VALIDO"] = out["VALIDO"].astype(bool)
    inval = pesos[~pesos["VALIDO"]]
    out = pd.concat([out, inval], ignore_index=True) if len(inval) else out
    return redondear_pesos(out[PESOS_COLS])


def aplicar_layout(pesos, layout, ramos, log):
    """
    Layout (hoja 1): LLAVE, ACCION (EXCLUIR | INCLUIR | FORZAR), [RAMO, PESO_PRIMA, PESO_COMISION, PESO_SINIESTRO, METODO], FUENTE, JUSTIFICACION.
    - EXCLUIR: la LLAVE no se ajusta aunque haya histórico (JUSTIFICACION obligatoria).
    - INCLUIR: la LLAVE se ajusta con sus pesos históricos aunque esté en REVISAR o dentro de la tolerancia; METODO opcional
               (ponderado | ultimo | promedio_simple) para esa LLAVE.
    - FORZAR: usa los pesos del layout para TODOS los tipos (una fila por ramo; PESO_PRIMA obligatorio; PESO_COMISION/PESO_SINIESTRO opcionales,
              si faltan se usan los de primas forzados). FUENTE y JUSTIFICACION obligatorias. Sustituye por completo los pesos de la fuente para esa LLAVE.
    Devuelve (pesos_actualizados, decisiones: LLAVE -> (ACCION, JUSTIFICACION), metodos: LLAVE -> METODO).
    """
    lay = layout.copy(); lay.columns = [str(c).strip().upper() for c in lay.columns]
    lay["_FILA_EXCEL"] = lay.index + 2
    lay = lay.dropna(how="all", subset=[c for c in lay.columns if c != "_FILA_EXCEL"])
    if "LLAVE" not in lay.columns or "ACCION" not in lay.columns:
        raise ErrorRedistribucion("El layout necesita las columnas LLAVE y ACCION.")
    lay["LLAVE"] = normalizar_llave(lay["LLAVE"])
    n0 = len(lay); lay = lay[lay["LLAVE"] != ""]
    if n0 - len(lay):
        log.info("Layout: %s filas sin LLAVE descartadas", n0 - len(lay))
    lay["ACCION"] = lay["ACCION"].fillna("").astype(str).str.strip().str.upper()
    for c in ["JUSTIFICACION", "FUENTE", "METODO"]:
        if c not in lay.columns:
            lay[c] = ""
        lay[c] = lay[c].fillna("").astype(str).str.strip()
    cols_peso = [c for c in ["RAMO", "PESO_PRIMA", "PESO_COMISION", "PESO_SINIESTRO"] if c in lay.columns]
    decisiones, metodos, forzados = {}, {}, []
    for llave, g in lay.groupby("LLAVE"):
        filas_x = sorted(g["_FILA_EXCEL"].tolist())
        if g["ACCION"].nunique() > 1:
            raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): la LLAVE {llave} tiene más de una ACCION ({sorted(g['ACCION'].unique())}).")
        acc = g["ACCION"].iloc[0]
        just = " | ".join(x for x in g["JUSTIFICACION"].unique() if x)
        fuente = " | ".join(x for x in g["FUENTE"].unique() if x)
        if acc not in {"EXCLUIR", "INCLUIR", "FORZAR"}:
            raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): ACCION desconocida '{acc}' para LLAVE {llave}. Use EXCLUIR, INCLUIR o FORZAR.")
        if not just:
            raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): la LLAVE {llave} tiene ACCION={acc} sin JUSTIFICACION. Ninguna decisión del layout entra sin justificación documentada.")
        if acc == "FORZAR" and not fuente:
            raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): la LLAVE {llave} tiene ACCION=FORZAR sin FUENTE (documento que respalda el porcentaje).")
        if acc in {"EXCLUIR", "INCLUIR"} and cols_peso and g[cols_peso].notna().any().any():
            raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): la LLAVE {llave} tiene ACCION={acc} pero trae RAMO/PESO_*; para aplicar porcentajes propios use FORZAR.")
        met = [m for m in g["METODO"].str.lower().unique() if m]
        if met:
            if acc != "INCLUIR" or len(met) > 1 or met[0] not in METODOS:
                raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): METODO sólo aplica a INCLUIR y debe ser uno de {METODOS} (LLAVE {llave}: {met}).")
            metodos[llave] = met[0]
        decisiones[llave] = (acc, just)
        if acc == "FORZAR":
            if "RAMO" not in g.columns or "PESO_PRIMA" not in g.columns:
                raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): FORZAR requiere las columnas RAMO y PESO_PRIMA (LLAVE {llave}).")
            g2 = g.copy(); g2["RAMO"] = a_num_estricto(g2["RAMO"], "RAMO", "Layout")
            if g2["RAMO"].isna().any() or g2["RAMO"].duplicated().any() or set(g2["RAMO"].astype(int)) != set(ramos):
                raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): FORZAR en LLAVE {llave} necesita exactamente una fila por ramo {ramos} (tiene {g2['RAMO'].tolist()}).")
            for tipo, c in [("Primas", "PESO_PRIMA"), ("Comisiones", "PESO_COMISION"), ("Siniestros", "PESO_SINIESTRO")]:
                if c not in g2.columns:
                    continue
                wv = a_num_estricto(g2[c], c, "Layout")
                if wv.isna().all():
                    if tipo == "Primas":
                        raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): FORZAR en LLAVE {llave} requiere PESO_PRIMA para todos los ramos.")
                    continue
                if wv.isna().any():
                    raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): {c} parcial en LLAVE {llave}: indíquelo para todos los ramos o déjelo vacío.")
                if (wv < 0).any() or (wv > 1).any():
                    raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): {c} de la LLAVE {llave} tiene valores fuera de [0, 1]: {wv.tolist()}.")
                if abs(float(wv.sum()) - 1) > 1e-6:
                    raise ErrorRedistribucion(f"Layout (filas Excel {filas_x}): los pesos {c} de la LLAVE {llave} deben sumar 1 (suman {wv.sum():.6f}).")
                for r, pv in zip(g2["RAMO"].astype(int), wv):
                    forzados.append({"LLAVE": llave, "TIPO": tipo, "RAMO": int(r), "PESO": float(pv), "MONTO_BASE": np.nan,
                                     "FUENTE": "LAYOUT_FORZADO: " + fuente, "DETALLE": just, "ORIGEN_PESO": "layout", "VALIDO": True, "MOTIVO": ""})
    if forzados:
        f = completar_columnas_pesos(pd.DataFrame(forzados))
        llaves_f = set(f["LLAVE"])
        if not pesos.empty:
            pesos = pesos[~pesos["LLAVE"].isin(llaves_f)]  # FORZAR sustituye por completo la fuente para esa LLAVE (todos los tipos)
            pesos = pd.concat([pesos, f], ignore_index=True)
        else:
            pesos = f
        log.info("Layout: %s LLAVEs con pesos FORZADOS (justificados); sus pesos de la fuente se descartan para todos los tipos", len(llaves_f))
    log.info("Layout: %s decisiones (%s)%s", len(decisiones), ", ".join(f"{k}={sum(1 for v in decisiones.values() if v[0]==k)}" for k in ["EXCLUIR", "INCLUIR", "FORZAR"]),
             f" | métodos por LLAVE: {metodos}" if metodos else "")
    return pesos, decisiones, metodos


def pesos_efectivos(pesos, ramos, politica_com, politica_sin):
    """
    Tabla de pesos que realmente se aplica por TIPO:
      Primas      -> pesos de Primas
      Comisiones  -> 'propio': pesos de Comisiones si existen y son válidos, si no los de Primas | 'prima' | 'no'
      Siniestros  -> igual, con la política de siniestros
    Un peso capturado en el layout (ORIGEN_PESO='layout') prevalece sobre la política global. ORIGEN_PESO documenta el origen.
    """
    v = pesos[pesos["VALIDO"]].copy()
    inv = pesos[~pesos["VALIDO"]].drop_duplicates(["LLAVE", "TIPO"]).set_index(["LLAVE", "TIPO"])["MOTIVO"]
    prim = v[v["TIPO"] == "Primas"].copy()
    out = [prim]
    for tipo, pol in [("Comisiones", politica_com), ("Siniestros", politica_sin)]:
        if pol == "no":
            continue
        propio = v[v["TIPO"] == tipo].copy()
        desde_prima = prim.copy(); desde_prima["TIPO"] = tipo
        motivo_inv = desde_prima["LLAVE"].map(lambda l: inv.get((l, tipo), None))
        desde_prima["ORIGEN_PESO"] = np.where(desde_prima["ORIGEN_PESO"] == "layout", "layout (primas forzadas)",
                                              np.where(motivo_inv.notna(), "prima (propio inválido: " + motivo_inv.fillna("").astype(str) + ")", "prima"))
        if pol == "propio":
            out.append(propio)
            out.append(desde_prima[~desde_prima["LLAVE"].isin(set(propio["LLAVE"]))])
        else:  # 'prima': sólo se respetan los pesos de ese tipo capturados en el layout
            lay = propio[propio["ORIGEN_PESO"] == "layout"]
            out.append(lay)
            out.append(desde_prima[~desde_prima["LLAVE"].isin(set(lay["LLAVE"]))])
    ef = pd.concat(out, ignore_index=True) if out else marco_pesos_vacio()
    ef = ef[["LLAVE", "TIPO", "RAMO", "PESO", "FUENTE", "DETALLE", "ORIGEN_PESO"]]
    if ef.duplicated(["LLAVE", "TIPO", "RAMO"]).any():
        d = ef[ef.duplicated(["LLAVE", "TIPO", "RAMO"], keep=False)].head(6)
        raise ErrorRedistribucion(f"Pesos duplicados por (LLAVE, TIPO, RAMO):\n{d.to_string(index=False)}")
    return ef


def sensibilidad_pesos(h, meses, ramos, anios_base, min_meses, tolerancia):
    """Peso del ramo mayor bajo los tres métodos por LLAVE-tipo; SENSIBLE si la diferencia entre métodos supera la tolerancia."""
    quiet = logger_silencioso()
    r = max(ramos); tabs = []
    for m in METODOS:
        try:
            t = pesos_desde_hist(h, meses, ramos, anios_base, m, min_meses, quiet)
        except ErrorRedistribucion:
            continue
        t = t[t["VALIDO"] & (t["RAMO"] == r)][["LLAVE", "TIPO", "PESO"]].rename(columns={"PESO": f"W{r}_{m}"})
        tabs.append(t)
    if not tabs:
        return pd.DataFrame()
    out = tabs[0]
    for t in tabs[1:]:
        out = out.merge(t, on=["LLAVE", "TIPO"], how="outer")
    wc = [c for c in out.columns if c.startswith(f"W{r}_")]
    out["DIF_MAX_ENTRE_METODOS"] = out[wc].max(axis=1) - out[wc].min(axis=1)
    out["SENSIBLE"] = out["DIF_MAX_ENTRE_METODOS"] > tolerancia
    return out.sort_values("DIF_MAX_ENTRE_METODOS", ascending=False)


def validacion_tendencia(h, df, c_amt, c_fy, anio_ppto, ramos, log):
    """
    Validación tipo 2026 (banderas de tendencia): último año real con datos vs presupuesto del año de decisión (Primas, |montos|) por LLAVE y ramo.
    SPLIT_SHIFT: un ramo sube >= +60% y el otro cae <= -40% mientras la suma 71+73 se mueve dentro de (-40%, +60%).
    """
    hp = h[h["TIPO"] == "Primas"]
    if hp.empty:
        return pd.DataFrame()
    ult = hp.groupby("LLAVE")["ANIO"].max().rename("ANIO_REAL")
    real = (hp.merge(ult, on="LLAVE").query("ANIO == ANIO_REAL").pivot_table(index="LLAVE", columns="RAMO", values="MONTO", aggfunc="sum")
              .reindex(columns=ramos).fillna(0.0).abs())
    pp = df[(df["TIPO"] == "Primas") & (df[c_fy] == anio_ppto) & df["RAMO"].isin(ramos)]
    ppto = pp.pivot_table(index="LLAVE", columns="RAMO", values=c_amt, aggfunc="sum").reindex(columns=ramos).fillna(0.0).abs()
    t = real.add_suffix("_REAL").join(ppto.add_suffix("_PPTO"), how="inner").join(ult)
    if t.empty:
        return pd.DataFrame()
    def d(a, b):
        return np.where(a > 0, (b - a) / a, np.nan)
    for r in ramos:
        t[f"DELTA_{r}"] = d(t[f"{r}_REAL"], t[f"{r}_PPTO"])
    t["TOTAL_REAL"] = sum(t[f"{r}_REAL"] for r in ramos); t["TOTAL_PPTO"] = sum(t[f"{r}_PPTO"] for r in ramos)
    t["DELTA_TOTAL"] = d(t["TOTAL_REAL"], t["TOTAL_PPTO"])
    r1, r2 = ramos[0], ramos[1]
    dentro = (t["DELTA_TOTAL"] > -0.40) & (t["DELTA_TOTAL"] < 0.60)
    t["SPLIT_SHIFT"] = dentro & (((t[f"DELTA_{r1}"] >= 0.60) & (t[f"DELTA_{r2}"] <= -0.40)) | ((t[f"DELTA_{r2}"] >= 0.60) & (t[f"DELTA_{r1}"] <= -0.40)))
    t["RAMO_DESAPARECE"] = ((t[f"{r1}_REAL"] > 0) & (t[f"{r1}_PPTO"] == 0)) | ((t[f"{r2}_REAL"] > 0) & (t[f"{r2}_PPTO"] == 0))
    t["RAMO_APARECE"] = ((t[f"{r1}_REAL"] == 0) & (t[f"{r1}_PPTO"] > 0)) | ((t[f"{r2}_REAL"] == 0) & (t[f"{r2}_PPTO"] > 0))
    log.info("Validación de tendencia (último real vs ppto %s, %s LLAVEs): SPLIT_SHIFT=%s | ramo desaparece=%s | ramo aparece=%s",
             anio_ppto, len(t), int(t["SPLIT_SHIFT"].sum()), int(t["RAMO_DESAPARECE"].sum()), int(t["RAMO_APARECE"].sum()))
    return t.reset_index()


# =============================================================================
# ALCANCE
# =============================================================================
def tabla_alcance(df, c_amt, c_fy, pesos, pesos_ef, sens, decisiones, ramos, p, log):
    """
    Una fila por LLAVE con ramo 71/73 en el presupuesto. La decisión se toma sobre el año fiscal anio_decision (el que consume CtaMens)
    y AMOUNT != 0. DECISION: AJUSTAR | NO_AJUSTAR | SIN_PESO | REVISAR (requiere confirmación del negocio vía layout INCLUIR/EXCLUIR).
    """
    r_ref = max(ramos); tol, modo, anio = p["tolerancia"], p["modo_alcance"], p["anio_decision"]
    cat_all = df[df["RAMO"].isin(ramos)]
    cat = cat_all[(cat_all[c_fy] == anio) & (cat_all[c_amt] != 0)]
    por = cat.pivot_table(index="LLAVE", columns=["TIPO", "RAMO"], values=c_amt, aggfunc="sum").fillna(0.0)
    atrib = cat_all.groupby("LLAVE")[["ZTIPOREAS_LL", "ZCEDENTE_LL", "ZCONTRATO_LL", "FUNCAREA_LL"]].first()
    # estructura de ramos (con prima) en otros años fiscales
    est = (cat_all[cat_all["TIPO"] == "Primas"].groupby(["LLAVE", c_fy])["RAMO"].agg(lambda s: tuple(sorted(set(s)))).reset_index())
    est_dec = est[est[c_fy] == anio].set_index("LLAVE")["RAMO"]
    est_otros = est[est[c_fy] != anio].groupby("LLAVE")["RAMO"].agg(lambda s: len(set(s)) > 1 or (len(s) and list(s)[0] != est_dec.get(s.name, None)))
    pw = pesos_ef.pivot_table(index=["LLAVE", "TIPO"], columns="RAMO", values="PESO", aggfunc="first")
    pcalc = pesos[pesos["VALIDO"] & (pesos["TIPO"] == "Primas")].drop_duplicates(["LLAVE", "TIPO"]).set_index("LLAVE")
    mb = pesos[pesos["VALIDO"] & (pesos["TIPO"] == "Primas")].groupby("LLAVE")["MONTO_BASE"].sum()
    fuente = pesos_ef[pesos_ef["TIPO"] == "Primas"].groupby("LLAVE")["FUENTE"].first()
    origen = pesos_ef[pesos_ef["TIPO"] == "Primas"].groupby("LLAVE")["ORIGEN_PESO"].first()
    tipos_peso = pesos_ef.groupby("LLAVE")["TIPO"].agg(lambda s: ",".join(sorted(set(s))))
    sensible = sens[sens["TIPO"] == "Primas"].set_index("LLAVE")["SENSIBLE"] if len(sens) else pd.Series(dtype=bool)
    sens_det = sens[sens["TIPO"] == "Primas"].set_index("LLAVE") if len(sens) else None
    filas = []
    for llave in sorted(set(cat_all["LLAVE"])):
        acc, just = decisiones.get(llave, (None, ""))
        en_anio = llave in por.index
        fp = por.loc[llave] if en_anio else pd.Series(dtype=float)
        tot = {t: float(sum(fp.get((t, r), 0.0) for r in ramos)) for t in TIPOS}
        tipo_ref = "Primas" if tot["Primas"] != 0 else next((t for t in TIPOS if tot[t] != 0), None)
        share_ppto = float(fp.get((tipo_ref, r_ref), 0.0) / tot[tipo_ref]) if tipo_ref else np.nan
        share_hist = float(pw.loc[(llave, tipo_ref), r_ref]) if (tipo_ref and (llave, tipo_ref) in pw.index) else np.nan
        tiene_peso = (llave, "Primas") in pw.index
        es_layout = origen.get(llave, "") == "layout"
        diff = share_ppto - share_hist if (pd.notna(share_ppto) and pd.notna(share_hist)) else np.nan
        tiene_ambos = all(float(fp.get(("Primas", r), 0.0)) != 0 for r in ramos)
        recl_total = (pd.notna(diff) and ((share_hist >= 1 - tol and share_ppto <= tol) or (share_hist <= tol and share_ppto >= 1 - tol)))
        monto_hist = float(mb.get(llave, np.nan))
        monto_ult = float(pcalc.loc[llave, "MONTO_ULTIMO_ANIO"]) if llave in pcalc.index else np.nan
        n_anios = float(pcalc.loc[llave, "N_ANIOS_VALIDOS"]) if llave in pcalc.index else np.nan
        cambio = bool(pcalc.loc[llave, "CAMBIO_ESTRUCTURAL"]) if llave in pcalc.index and pd.notna(pcalc.loc[llave, "CAMBIO_ESTRUCTURAL"]) else False
        es_sensible = bool(sensible.get(llave, False))
        ppto_abs = abs(tot["Primas"])
        ratio = (ppto_abs / monto_ult) if (pd.notna(monto_ult) and monto_ult > 0) else np.nan
        cred_min = max(p["materialidad"], p["credibilidad_pct"] * ppto_abs)
        funcarea = str(atrib.loc[llave, "FUNCAREA_LL"]); facultativo = str(atrib.loc[llave, "ZTIPOREAS_LL"]) == "3"
        if acc == "EXCLUIR":
            dec, mot = "NO_AJUSTAR", f"Layout EXCLUIR: {just}"
        elif not tiene_peso:
            dec, mot = "SIN_PESO", "sin histórico/pesos válidos de primas para esta LLAVE (requiere información del negocio: layout FORZAR o histórico)"
        elif not en_anio:
            dec, mot = "NO_AJUSTAR", f"sin filas de ramos {ramos} con monto en el año de decisión {anio}"
        elif modo == "layout" and acc is None:
            dec, mot = "NO_AJUSTAR", "modo 'layout': la LLAVE no está en el layout"
        elif acc in {"INCLUIR", "FORZAR"}:
            dec, mot = "AJUSTAR", f"Layout {acc}: {just}"
        elif funcarea in [x.upper() for x in p["excluir_funcarea"]]:
            dec, mot = "NO_AJUSTAR", f"LN {funcarea} excluida (CtaMens reescribe su PROFTCTR con CAT_LN4004)"
        elif tipo_ref != "Primas":
            dec, mot = "REVISAR", f"sin primas de referencia en ramos {ramos} (sólo {tipo_ref}); confirmar con INCLUIR si procede"
        elif pd.isna(diff):
            dec, mot = "NO_AJUSTAR", "no se pudo calcular la participación"
        elif abs(diff) <= tol:
            dec, mot = "NO_AJUSTAR", f"dentro de tolerancia (diferencia {abs(diff):.1%})"
        elif p["materialidad"] > 0 and ppto_abs < p["materialidad"]:
            dec, mot = "NO_AJUSTAR", f"inmaterial: |prima 71+73 {anio}| = {ppto_abs:,.0f} < materialidad {p['materialidad']:,.0f}"
        elif recl_total and p["reclasificacion_total"] != "auto":
            dec, mot = "REVISAR", f"reclasificación total (histórico {abs(share_hist):.1%} en {r_ref} vs presupuesto {abs(share_ppto):.1%}, umbral 1-tolerancia): confirmar con INCLUIR"
        elif not es_layout and pd.notna(monto_hist) and monto_hist < cred_min:
            dec, mot = "REVISAR", f"histórico poco creíble: |prima histórica base| = {monto_hist:,.0f} < {cred_min:,.0f} ({p['credibilidad_pct']:.0%} del presupuesto {anio} o materialidad)"
        elif not es_layout and pd.notna(ratio) and not (p["banda_ratio"][0] <= ratio <= p["banda_ratio"][1]):
            dec, mot = "REVISAR", f"presupuesto {anio} / último real anual = {ratio:.2f} fuera de la banda [{p['banda_ratio'][0]:.2f}, {p['banda_ratio'][1]:.2f}]"
        elif not es_layout and p["revisar_sensibles"] and (cambio or es_sensible):
            det = ""
            if sens_det is not None and llave in sens_det.index:
                det = " | " + ", ".join(f"{c.replace('W' + str(r_ref) + '_', '')}={sens_det.loc[llave, c]:.3f}" for c in sens_det.columns if c.startswith(f"W{r_ref}_"))
            dec, mot = "REVISAR", ("cambio estructural entre años base (un año mono-ramo y otro bi-ramo)" if cambio else "pesos sensibles al método") + f": confirmar con INCLUIR (opcionalmente METODO){det}"
        elif str(atrib.loc[llave, "ZCONTRATO_LL"]) == "0" and not facultativo:
            dec, mot = "REVISAR", "contrato nulo en negocio no facultativo: la LLAVE agrupa varios contratos distintos; pedir el número de contrato a la LN y confirmar con INCLUIR o FORZAR"
        elif facultativo and p["revisar_facultativos"]:
            dec, mot = "REVISAR", "facultativo: la LLAVE agrupa varios contratos/corredores de la cedente; confirmar con INCLUIR o aportar el slip (FORZAR)"
        elif tiene_ambos and not p["ajustar_split_explicito"]:
            dec, mot = "REVISAR", f"la LLAVE ya trae ambos ramos (partición explícita del cargador, participación {share_ppto:.1%} vs histórica {share_hist:.1%}): confirmar con INCLUIR"
        else:
            dec, mot = "AJUSTAR", f"cargada en un solo ramo; |participación ppto - histórica| = {abs(diff):.1%} > tolerancia {tol:.1%}"
        fila = {"LLAVE": llave, "ZTIPOREAS": atrib.loc[llave, "ZTIPOREAS_LL"], "ZCEDENTE": atrib.loc[llave, "ZCEDENTE_LL"],
                "ZCONTRATO": atrib.loc[llave, "ZCONTRATO_LL"], "FUNCAREA": funcarea, "ANIO_DECISION": anio, "TIPO_REFERENCIA": tipo_ref,
                "PPTO_TOTAL_REF_7173": tot[tipo_ref] if tipo_ref else 0.0, f"SHARE_{r_ref}_PPTO": share_ppto, f"SHARE_{r_ref}_PESO": share_hist,
                "DIFERENCIA": diff, "TIENE_AMBOS_RAMOS": tiene_ambos, "PRIMA_HIST_BASE": monto_hist, "PRIMA_ULTIMO_REAL": monto_ult,
                "RATIO_PPTO_ULTIMO_REAL": ratio, "N_ANIOS_VALIDOS": n_anios, "CAMBIO_ESTRUCTURAL": cambio, "SENSIBLE_METODO": es_sensible,
                "RAMOS_OTROS_FY_DIFIEREN": bool(est_otros.get(llave, False)), "FUENTE_PESO": fuente.get(llave, ""), "ORIGEN_PESO": origen.get(llave, ""),
                "TIPOS_CON_PESO": tipos_peso.get(llave, ""), "DECISION": dec, "MOTIVO": mot}
        for t in TIPOS:
            for r in ramos:
                fila[f"PPTO_{t}_{r}"] = float(fp.get((t, r), 0.0))
        filas.append(fila)
    al = pd.DataFrame(filas)
    log.info("Alcance (año de decisión %s): %s LLAVEs con ramos %s | AJUSTAR=%s | REVISAR=%s | NO_AJUSTAR=%s | SIN_PESO=%s", anio, len(al), ramos,
             int((al["DECISION"] == "AJUSTAR").sum()), int((al["DECISION"] == "REVISAR").sum()), int((al["DECISION"] == "NO_AJUSTAR").sum()),
             int((al["DECISION"] == "SIN_PESO").sum()))
    if (al["DECISION"] == "REVISAR").any():
        log.info("Motivos de REVISAR: %s", al[al["DECISION"] == "REVISAR"]["MOTIVO"].str.split(":").str[0].str.split("(").str[0].str.strip().value_counts().to_dict())
    return al


# =============================================================================
# REDISTRIBUCIÓN FILA A FILA
# =============================================================================
def redistribuir(df, cols_orig, c_prof, c_amt, c_amt_t, c_fy, pesos_ef, llaves, ramos, anios_fiscales, conservar_cero, decimales, log):
    """
    Devuelve (df_salida con cols_orig + _ID_ORIGEN, detalle_fila_a_fila, n_omitidas).
    Mecánica: pool por (FIRMA, SIGNO) -> target por ramo = pool x peso -> filas existentes reparten el target del ramo según
    |monto original| -> ramos faltantes se clonan desde la fila mayor del pool -> redondeo + residuo a la fila mayor (conservación exacta).
    """
    tipos = sorted(set(pesos_ef["TIPO"]))
    mask = df["LLAVE"].isin(llaves) & df["RAMO"].isin(ramos) & df["TIPO"].isin(tipos)
    if anios_fiscales != "todos":
        mask &= df[c_fy].isin(list(anios_fiscales))
    work = df[mask].copy()
    log.info("Filas en alcance (LLAVEs AJUSTAR x ramos %s x tipos %s x años %s): %s", ramos, tipos, anios_fiscales, len(work))
    cols_firma = [c for c in cols_orig if c not in {c_prof, c_amt, c_amt_t}]
    if work.empty:
        return df[cols_orig + ["_ID_ORIGEN"]].copy(), pd.DataFrame(), 0
    dec_obs = max_decimales(work[c_amt])
    if decimales is not None and dec_obs > decimales:
        log.warning("Los montos en alcance traen hasta %s decimales; se usa ese redondeo en lugar de %s para conservar los totales exactamente", dec_obs, decimales)
        decimales = dec_obs

    work["FIRMA"] = work.groupby(cols_firma, dropna=False, sort=False).ngroup()
    work["AMOUNT_ORIG"] = work[c_amt].astype(float)
    work["SIGNO"] = np.where(work["AMOUNT_ORIG"] < 0, -1, 1)
    work["POOL_ID"] = work.groupby(["FIRMA", "SIGNO"], sort=False).ngroup()
    pool = work.groupby("POOL_ID")["AMOUNT_ORIG"].sum().rename("POOL")
    n_mixtas = int(work.groupby("FIRMA")["SIGNO"].nunique().gt(1).sum())
    if n_mixtas:
        log.info("Firmas con montos de signo mixto (se reparten por separado el sub-pool positivo y el negativo): %s", n_mixtas)

    pools = work[["POOL_ID", "FIRMA", "LLAVE", "TIPO"]].drop_duplicates("POOL_ID")
    cross = pools.merge(pd.DataFrame({"RAMO": ramos}), how="cross")
    cross = cross.merge(pesos_ef[["LLAVE", "TIPO", "RAMO", "PESO", "FUENTE", "ORIGEN_PESO"]], on=["LLAVE", "TIPO", "RAMO"], how="left", validate="m:1")
    sin_peso = cross["PESO"].isna()
    if sin_peso.any():
        pools_sin = cross.loc[sin_peso, "POOL_ID"].unique()
        log.warning("Pools sin peso para algún ramo (se dejan intactos): %s", len(pools_sin))
        work = work[~work["POOL_ID"].isin(pools_sin)]
        cross = cross[~cross["POOL_ID"].isin(pools_sin)]
        pool = pool[~pool.index.isin(pools_sin)]
    cross = cross.join(pool, on="POOL_ID")
    cross["TARGET"] = cross["POOL"] * cross["PESO"]

    work["_ABS"] = work["AMOUNT_ORIG"].abs()
    sum_abs = work.groupby(["POOL_ID", "RAMO"])["_ABS"].transform("sum")
    n_rows = work.groupby(["POOL_ID", "RAMO"])["_ABS"].transform("size")
    work["SHARE_INTRA"] = np.where(sum_abs > 0, work["_ABS"] / sum_abs.where(sum_abs > 0, 1), 1.0 / n_rows)
    work = work.merge(cross[["POOL_ID", "RAMO", "TARGET", "PESO", "FUENTE", "ORIGEN_PESO"]], on=["POOL_ID", "RAMO"], how="left", validate="m:1")
    work["AMOUNT_NUEVO"] = work["TARGET"] * work["SHARE_INTRA"]
    work["MOVIMIENTO"] = "RECALCULADA"
    work["RAMO_ORIGEN"] = work["RAMO"]
    work["_ID_CLON_DE"] = np.nan

    existentes = work[["POOL_ID", "RAMO"]].drop_duplicates()
    falt = cross.merge(existentes.assign(_e=1), on=["POOL_ID", "RAMO"], how="left")
    falt = falt[falt["_e"].isna()]
    umbral = 0.5 * 10 ** (-(decimales if decimales is not None else 10))
    n_clon_cero = int((falt["TARGET"].abs() < umbral).sum())
    falt = falt[falt["TARGET"].abs() >= umbral]  # un clon cuyo monto redondea a 0 no se crea; el residuo queda en la fila existente
    code_llave = df[df["RAMO"].isin(ramos)].groupby(["LLAVE", "RAMO"])[c_prof].agg(lambda s: s.value_counts().index[0])
    code_global = df[df["RAMO"].isin(ramos)].groupby("RAMO")[c_prof].agg(lambda s: s.value_counts().index[0])

    def codigo(llave, r):
        if (llave, r) in code_llave.index:
            return code_llave.loc[(llave, r)]
        if r in code_global.index:
            return code_global.loc[r]
        return f"A{int(r):03d}000000"

    clones = pd.DataFrame()
    if not falt.empty:
        rep = work.sort_values("_ABS", ascending=False).drop_duplicates("POOL_ID").set_index("POOL_ID")
        clones = rep.loc[falt["POOL_ID"].values].reset_index()
        clones["_ID_CLON_DE"] = clones["_ID_ORIGEN"]
        clones["RAMO_ORIGEN"] = clones["RAMO"]
        clones["RAMO"] = falt["RAMO"].values
        clones[c_prof] = [codigo(l, r) for l, r in zip(clones["LLAVE"], clones["RAMO"])]
        clones["AMOUNT_ORIG"] = 0.0
        clones["SHARE_INTRA"] = 1.0
        clones["TARGET"] = falt["TARGET"].values
        clones["PESO"] = falt["PESO"].values
        clones["FUENTE"] = falt["FUENTE"].values
        clones["ORIGEN_PESO"] = falt["ORIGEN_PESO"].values
        clones["AMOUNT_NUEVO"] = clones["TARGET"]
        clones["MOVIMIENTO"] = "CLON"
        clones["_ID_ORIGEN"] = np.nan
    todo = pd.concat([work, clones], ignore_index=True) if len(clones) else work

    pool_r = pool.round(decimales) if decimales is not None else pool
    if decimales is not None:
        todo["AMOUNT_NUEVO"] = todo["AMOUNT_NUEVO"].round(decimales)
    suma = todo.groupby("POOL_ID")["AMOUNT_NUEVO"].transform("sum")
    todo["_RES"] = todo["POOL_ID"].map(pool_r) - suma
    if decimales is not None:
        todo["_RES"] = todo["_RES"].round(decimales)
    idx_max = todo.assign(_a=todo["AMOUNT_NUEVO"].abs()).sort_values(["POOL_ID", "_a"], ascending=[True, False]).drop_duplicates("POOL_ID").index
    es_max = todo.index.isin(idx_max)
    todo.loc[es_max, "AMOUNT_NUEVO"] = todo.loc[es_max, "AMOUNT_NUEVO"] + todo.loc[es_max, "_RES"]
    if decimales is not None:
        todo["AMOUNT_NUEVO"] = todo["AMOUNT_NUEVO"].round(decimales)
    todo["RESIDUO_ASIGNADO"] = np.where(es_max, todo["_RES"], 0.0)

    cambia = (todo["AMOUNT_NUEVO"] - todo["AMOUNT_ORIG"]).abs() > 1e-9
    todo.loc[(todo["MOVIMIENTO"] == "RECALCULADA") & ~cambia, "MOVIMIENTO"] = "SIN_CAMBIO"
    todo.loc[(todo["MOVIMIENTO"] == "RECALCULADA") & (todo["AMOUNT_NUEVO"].abs() < 1e-9), "MOVIMIENTO"] = "A_CERO"
    todo[c_amt] = todo["AMOUNT_NUEVO"]
    if c_amt_t is not None and df[c_amt_t].notna().any():
        src_t = todo[c_amt_t].astype(float)
        src_a = np.where(todo["MOVIMIENTO"] == "CLON", todo["_ID_CLON_DE"].map(df.set_index("_ID_ORIGEN")[c_amt]), todo["AMOUNT_ORIG"])
        ratio = np.where(pd.notna(src_a) & (np.abs(src_a) > 0), todo["AMOUNT_NUEVO"] / np.where(src_a == 0, 1, src_a), np.nan)
        todo[c_amt_t] = np.where(pd.notna(src_t), (src_t * ratio).round(decimales if decimales is not None else 10), np.nan)

    chk = todo.groupby("POOL_ID")[c_amt].sum() - pool_r
    if (chk.abs() > 1e-6).any():
        raise AssertionError(f"Conservación por pool violada en {int((chk.abs() > 1e-6).sum())} pools (máx {chk.abs().max()}).")

    recalc = todo[todo["MOVIMIENTO"] != "CLON"].copy()
    if not conservar_cero:
        recalc = recalc[recalc["MOVIMIENTO"] != "A_CERO"]  # sólo se omiten las filas que la redistribución dejó en cero
    n_omitidas = int((todo["MOVIMIENTO"] != "CLON").sum() - len(recalc))
    cols_out = cols_orig + ["_ID_ORIGEN"]
    salida = df.set_index("_ID_ORIGEN", drop=False)
    salida = salida.drop(index=work["_ID_ORIGEN"].unique())[cols_out]
    salida = pd.concat([salida, recalc.set_index("_ID_ORIGEN", drop=False)[cols_out]]).sort_index()
    cl = todo[todo["MOVIMIENTO"] == "CLON"]
    salida = pd.concat([salida.reset_index(drop=True), cl[cols_out].reset_index(drop=True)], ignore_index=True) if len(cl) else salida.reset_index(drop=True)

    c_mes = col(df, "MES")
    det_cols = ["_ID_ORIGEN", "_ID_CLON_DE", "LLAVE", "FIRMA", "POOL_ID", "SIGNO", "TIPO", c_fy, c_mes, "ZSUSCYEAR", "RAMO_ORIGEN", "RAMO", c_prof,
                "AMOUNT_ORIG", "PESO", "ORIGEN_PESO", "FUENTE", "SHARE_INTRA", "TARGET", "AMOUNT_NUEVO", "RESIDUO_ASIGNADO", "MOVIMIENTO"]
    det_cols = [c for c in det_cols if c in todo.columns]
    detalle = todo[det_cols].rename(columns={"RAMO": "RAMO_NUEVO", c_prof: "PROFTCTR_NUEVO"}).sort_values(["LLAVE", "FIRMA", "SIGNO", "RAMO_NUEVO"])
    log.info("Movimientos: %s | clones no creados por monto 0: %s | filas en cero omitidas del csv: %s | decimales: %s",
             detalle["MOVIMIENTO"].value_counts().to_dict(), n_clon_cero, n_omitidas, decimales)
    return salida, detalle, n_omitidas


# =============================================================================
# CONTROLES (independientes del cálculo; detienen la escritura si fallan)
# =============================================================================
def controles(df, salida, detalle, n_omitidas, pesos_ef, cols_orig, c_prof, c_amt, c_amt_t, c_fy, c_mes, ramos, llaves_aj, tol_share, anios_fiscales, subramo_df, log):
    res, fallas = {}, []
    cols_firma = [c for c in cols_orig if c not in {c_prof, c_amt, c_amt_t}]
    ids_tocados = set(detalle["_ID_ORIGEN"].dropna().astype(int)) if len(detalle) else set()
    n_clones = int((detalle["MOVIMIENTO"] == "CLON").sum()) if len(detalle) else 0

    # 1) filas no tocadas: idénticas en todas las columnas
    orig_int = df[~df["_ID_ORIGEN"].isin(ids_tocados)].set_index("_ID_ORIGEN")[cols_orig].sort_index()
    sal_int = salida[salida["_ID_ORIGEN"].notna() & ~salida["_ID_ORIGEN"].isin(ids_tocados)].set_index("_ID_ORIGEN")[cols_orig].sort_index()
    sal_int.index = sal_int.index.astype(orig_int.index.dtype)
    identicas = len(orig_int) == len(sal_int) and orig_int.index.equals(sal_int.index) and orig_int.fillna("<NA>").astype(str).equals(sal_int.fillna("<NA>").astype(str))
    res["filas_intactas"] = len(orig_int)
    if not identicas:
        fallas.append("Las filas fuera del alcance NO son idénticas al original.")

    # 2) conservación por firma completa en todo el archivo
    def por_firma(d):
        return d.groupby(cols_firma, dropna=False, sort=False)[c_amt].sum()
    a, b = por_firma(df[cols_orig]), por_firma(salida[cols_orig])
    cmpf = pd.concat([a.rename("ANTES"), b.rename("DESPUES")], axis=1).fillna(0.0)
    cmpf["DIF"] = cmpf["DESPUES"] - cmpf["ANTES"]
    res["max_dif_firma"] = float(cmpf["DIF"].abs().max()) if len(cmpf) else 0.0
    if res["max_dif_firma"] > 0.005:
        fallas.append(f"Conservación por firma violada (máx dif {res['max_dif_firma']}).")

    # 3) cuadre por LLAVE-tipo-año-mes y global
    def prep(d):
        d = d.copy()
        d["TIPO"] = d[col(d, "GL")].astype(str).str[:2].map(TIPO_POR_GL)
        d["RAMO"] = ramo_desde_proftctr(d[c_prof], subramo_df)
        d["LLAVE"] = construir_llave(d, col(d, "TIPOREA"), col(d, "CED"), col(d, "CTO"), col(d, "FUNC"))
        return d
    a2, b2 = prep(df[cols_orig]), prep(salida[cols_orig])
    g0 = a2.groupby(["LLAVE", "TIPO", c_fy, c_mes], dropna=False)[c_amt].sum()
    g1 = b2.groupby(["LLAVE", "TIPO", c_fy, c_mes], dropna=False)[c_amt].sum()
    cmp = pd.concat([g0.rename("ANTES"), g1.rename("DESPUES")], axis=1).fillna(0.0)
    cmp["DIF"] = (cmp["DESPUES"] - cmp["ANTES"]).round(6)
    res["cuadre_llave_tipo_anio_mes"] = cmp.reset_index()
    res["max_dif_llave_tipo_anio_mes"] = float(cmp["DIF"].abs().max()) if len(cmp) else 0.0
    res["dif_global"] = float(round(b2[c_amt].sum() - a2[c_amt].sum(), 6))
    tg0 = a2.groupby(["TIPO", c_fy])[c_amt].sum().rename("ANTES"); tg1 = b2.groupby(["TIPO", c_fy])[c_amt].sum().rename("DESPUES")
    res["cuadre_tipo_anio"] = pd.concat([tg0, tg1], axis=1).fillna(0.0).assign(DIF=lambda d: (d["DESPUES"] - d["ANTES"]).round(6)).reset_index()
    if abs(res["dif_global"]) > 0.01 or res["max_dif_llave_tipo_anio_mes"] > 0.01:
        fallas.append("Cuadre global o por LLAVE-tipo-año-mes fuera de tolerancia.")

    # 4) participación resultante == peso (LLAVEs ajustadas); sin cambio (no ajustadas)
    r_ref = max(ramos)
    def shares(d):
        c = d[d["RAMO"].isin(ramos)]
        if anios_fiscales != "todos":
            c = c[c[c_fy].isin(list(anios_fiscales))]
        pv = c.pivot_table(index=["LLAVE", "TIPO"], columns="RAMO", values=c_amt, aggfunc="sum").reindex(columns=ramos).fillna(0.0)
        tot = pv.sum(axis=1)
        return (pv[r_ref] / tot.where(tot != 0)).rename("SHARE")
    s0, s1 = shares(a2), shares(b2)
    pw = pesos_ef.set_index(["LLAVE", "TIPO"]); pw = pw[pw["RAMO"] == r_ref]["PESO"]
    chk = pd.concat([s0.rename("SHARE_ANTES"), s1.rename("SHARE_DESPUES"), pw.rename("PESO")], axis=1)
    chk = chk[chk.index.get_level_values(0).isin(set(a2.loc[a2["RAMO"].isin(ramos), "LLAVE"]))]
    aj = chk[chk.index.get_level_values(0).isin(llaves_aj) & chk["PESO"].notna() & chk["SHARE_DESPUES"].notna()]
    aj_dev = (aj["SHARE_DESPUES"] - aj["PESO"]).abs()
    res["max_desv_share_vs_peso"] = float(aj_dev.max()) if len(aj_dev) else 0.0
    if res["max_desv_share_vs_peso"] > tol_share:
        fallas.append(f"La participación resultante difiere del peso aplicado en alguna LLAVE ajustada (máx {res['max_desv_share_vs_peso']:.6f}).")
    no = chk[~chk.index.get_level_values(0).isin(llaves_aj)]
    if ((no["SHARE_DESPUES"].fillna(-9) - no["SHARE_ANTES"].fillna(-9)).abs() > 1e-9).any():
        fallas.append("Cambió la participación de alguna LLAVE NO ajustada.")
    res["participacion_llave"] = chk.reset_index()

    # 5) conteo de filas
    res["filas_antes"], res["filas_despues"], res["clones"], res["filas_cero_omitidas"] = len(df), len(salida), n_clones, n_omitidas
    if len(salida) != len(df) - n_omitidas + n_clones:
        fallas.append(f"Conteo de filas inesperado: {len(df)} -> {len(salida)} (clones {n_clones}, ceros omitidos {n_omitidas}).")

    # 6) participación agregada (informativa)
    def participacion(d, by):
        c = d[d["RAMO"].isin(ramos)]
        pv = c.pivot_table(index=by, columns="RAMO", values=c_amt, aggfunc="sum").reindex(columns=ramos).fillna(0.0)
        pv["TOTAL"] = pv.sum(axis=1)
        pv[f"SHARE_{r_ref}"] = np.where(pv["TOTAL"] != 0, pv[r_ref] / pv["TOTAL"], np.nan)
        return pv
    tabs = []
    c_reg, c_func = col(a2, "REG", obligatoria=False), col(a2, "FUNC")
    niveles = [("GLOBAL", ["TIPO", c_fy]), ("LN", ["TIPO", c_fy, c_func])] + ([("REGION", ["TIPO", c_fy, c_reg])] if c_reg else [])
    for nombre, by in niveles:
        t = participacion(a2, by).add_suffix("_ANTES").join(participacion(b2, by).add_suffix("_DESPUES"), how="outer").reset_index()
        t.insert(0, "NIVEL", nombre); tabs.append(t)
    res["participacion"] = pd.concat(tabs, ignore_index=True)

    # 7) combinaciones que aparecen y que desaparecen (filas GL61 con monto) por llaves que usa CtaMens
    nuevos, desap = {}, {}
    c_tr, c_ced, c_cto = col(a2, "TIPOREA"), col(a2, "CED"), col(a2, "CTO")
    c_corr, c_susc = col(a2, "CORR", obligatoria=False), col(a2, "SUSC", obligatoria=False)
    claves = {"EVCAT (PROFTCTR-Region)": [c_prof] + ([c_reg] if c_reg else []),
              "LN-Ramo-Region-TipoRea": [c_func, "RAMO"] + ([c_reg] if c_reg else []) + [c_tr],
              "CESION_HIST (TipoRea-Corredor-Cedente-Contrato-Susc-Region-Ramo)": [x for x in [c_tr, c_corr, c_ced, c_cto, c_susc, c_reg, "RAMO"] if x]}
    for nombre, k in claves.items():
        antes = a2[a2["RAMO"].isin(ramos) & (a2["TIPO"] == "Primas") & (a2[c_amt] != 0)].groupby(k, dropna=False)[c_amt].sum()
        despues = b2[b2["RAMO"].isin(ramos) & (b2["TIPO"] == "Primas") & (b2[c_amt] != 0)].groupby(k, dropna=False)[c_amt].sum()
        nuevos[nombre] = despues[~despues.index.isin(antes.index)].rename("MONTO_PRIMA").reset_index()
        desap[nombre] = antes[~antes.index.isin(despues.index)].rename("MONTO_PRIMA_ANTES").reset_index()
    res["combos_nuevos"], res["combos_desaparecen"] = nuevos, desap
    res["fallas"] = fallas
    log.info("Controles: intactas=%s | max dif firma=%s | dif global=%s | max dif LLAVE-tipo-año-mes=%s | max desv share vs peso=%s | filas %s -> %s (clones %s, ceros omitidos %s) | combos nuevos: %s | desaparecen: %s",
             res["filas_intactas"], res["max_dif_firma"], res["dif_global"], res["max_dif_llave_tipo_anio_mes"], round(res["max_desv_share_vs_peso"], 6),
             len(df), len(salida), n_clones, n_omitidas, {k.split(" ")[0]: len(v) for k, v in nuevos.items()}, {k.split(" ")[0]: len(v) for k, v in desap.items()})
    return res, b2


def verificar_insumos_ctamens(df_antes_prep, salida_prep, detalle, p, subramo_df, c_prof, c_amt, c_fy, ramos, log):
    """
    Verificaciones previas contra los insumos de CtaMens que existan en disco, reproduciendo sus llaves exactas:
      - Subramo.csv: el CeBe de los clones debe existir (si no, CtaMens convierte Ramo2 a decimal para toda la base) -> bloqueante.
      - Cesion.csv + Pais.csv + Subramo.csv: LLAVE1 = FUNCAREA-Ramo2-Territorio-ZTIPOREAS de las filas clonadas, con columna del ZSUSCYEAR.
      - CesionPI.csv: fila para el Ramo de ambos ramos.
      - Porc_Cesión_Hist.xlsx: LLAVE_CESION_HIST = ZTIPOREAS-ZCORREDOR-ZCEDENTE-ZCONTRATO-ZSUSCYEAR-ZREGIONRP-Ramo2 de las filas clonadas.
      - xDnEvCat / xDnAttritional: PROFTCTR+ZREGIONRP de las filas clonadas.
      - xMatCostoXL + xDnCostoXL / xDnRecup: firma ContratosXL de las filas clonadas (GL 61), como la construye CtaMens.
    Devuelve una tabla larga (INSUMO, LLAVE, EXISTE, MONTO) para la hoja Verif_Insumos_CtaMens.
    """
    if not len(detalle):
        return pd.DataFrame()
    cl = salida_prep[salida_prep["_ID_ORIGEN"].isna()].copy() if "_ID_ORIGEN" in salida_prep.columns else pd.DataFrame()
    cl = cl[cl["TIPO"] == "Primas"] if len(cl) else cl
    out = []
    c_reg, c_func, c_tr = col(salida_prep, "REG", obligatoria=False), col(salida_prep, "FUNC"), col(salida_prep, "TIPOREA")
    c_corr, c_ced, c_cto, c_susc = col(salida_prep, "CORR", obligatoria=False), col(salida_prep, "CED"), col(salida_prep, "CTO"), col(salida_prep, "SUSC", obligatoria=False)
    # Subramo (bloqueante)
    if subramo_df is not None and "CeBe" in subramo_df.columns and len(cl):
        cebes = set(subramo_df["CeBe"].astype(str).str.strip())
        falt = sorted(set(cl[c_prof].astype(str)) - cebes)
        if falt:
            raise ErrorRedistribucion(f"Los centros de beneficio de los clones {falt} no existen en Subramo.csv: CtaMens convertiría Ramo2 a decimal para toda la base. Agregue el CeBe a Subramo.csv antes de continuar.")
        log.info("Verificación Subramo.csv: todos los centros de beneficio de los clones existen (%s)", sorted(set(cl[c_prof].astype(str))))
        cl["Ramo2"] = ramo_desde_proftctr(cl[c_prof], subramo_df, "Ramo2" if "Ramo2" in subramo_df.columns else "Ramo")
    elif len(cl):
        cl["Ramo2"] = cl["RAMO"]
        log.warning("Sin Subramo.csv: las verificaciones de cesión usan el ramo derivado del centro de beneficio en lugar de Ramo2")
    if not len(cl):
        return pd.DataFrame()
    def agrega(nombre, llave_series, existe_series):
        t = pd.DataFrame({"INSUMO": nombre, "LLAVE": llave_series.values, "EXISTE": existe_series.values, "MONTO": cl[c_amt].values})
        t = t.groupby(["INSUMO", "LLAVE", "EXISTE"], as_index=False)["MONTO"].sum()
        out.append(t)
        log.info("Verificación %s: %s llaves de clones, %s sin entrada (monto %s)", nombre, t["LLAVE"].nunique(), int((~t["EXISTE"]).sum()), round(float(t.loc[~t["EXISTE"], "MONTO"].sum()), 2))
    # Cesion.csv (LLAVE1 exacta) requiere Pais.csv
    if existe(p, "cesion") and existe(p, "pais") and c_reg:
        try:
            pais, _ = leer_tabla(p["pais"]); ces, _ = leer_tabla(p["cesion"])
            terr = pais.drop_duplicates("TerrSAP").set_index("TerrSAP")["Territorio"]
            llave1 = (cl[c_func].astype(str) + "-" + cl["Ramo2"].fillna(0).astype(int).astype(str) + "-" + cl[c_reg].map(terr).fillna("").astype(str) + "-" + a_int_str(cl[c_tr]))
            keys = set(ces["Llave"].astype(str).str.strip())
            agrega("Cesion.csv (LLAVE1)", llave1, llave1.isin(keys))
        except Exception as ex:
            log.warning("No se pudo verificar Cesion.csv: %s", ex)
    if existe(p, "cesionpi"):
        try:
            pi, _ = leer_tabla(p["cesionpi"])
            keys = set(pd.to_numeric(pi["Ramo"], errors="coerce").dropna().astype(int))
            s = cl["Ramo2"].fillna(0).astype(int)
            agrega("CesionPI.csv (Ramo)", s.astype(str), s.isin(keys))
        except Exception as ex:
            log.warning("No se pudo verificar CesionPI.csv: %s", ex)
    if existe(p, "cesion_hist") and c_corr and c_susc and c_reg:
        try:
            m = pd.read_excel(p["cesion_hist"], sheet_name=0, engine="openpyxl")
            keys = set(m["LlaveCesión"].astype(str).str.strip())
            susc = pd.to_numeric(cl[c_susc], errors="coerce").fillna(2026).astype(int).astype(str)  # CtaMens: ZSUSCYEAR nulo -> '2026'
            tr = pd.to_numeric(cl[c_tr], errors="coerce").map(lambda v: "" if pd.isna(v) else str(int(v)))  # CtaMens: ZTIPOREAS nulo -> ''
            lch = (tr + "-" + a_int_str(cl[c_corr]) + "-" + a_int_str(cl[c_ced]) + "-" + a_int_str(cl[c_cto]) + "-" + susc + "-"
                   + cl[c_reg].fillna("").astype(str) + "-" + cl["Ramo2"].fillna(0).astype(int).astype(str))
            agrega("Porc_Cesión_Hist (LLAVE_CESION_HIST)", lch, lch.isin(keys))
        except Exception as ex:
            log.warning("No se pudo verificar Porc_Cesión_Hist: %s", ex)
    for nombre, k in [("xDnEvCat", "evcat"), ("xDnAttritional", "attritional")]:
        if existe(p, k) and c_reg:
            try:
                m = pd.read_excel(p[k], sheet_name=0, engine="openpyxl")
                keys = set(m["PROFTCTR"].astype(str) + m["ZREGIONRP"].astype(str))
                le = cl[c_prof].astype(str) + cl[c_reg].astype(str)
                agrega(f"{nombre} (PROFTCTR+Region)", le, le.isin(keys))
            except Exception as ex:
                log.warning("No se pudo verificar %s: %s", nombre, ex)
    if existe(p, "matxl") and c_reg:
        try:
            mat = pd.read_excel(p["matxl"], sheet_name=0, header=None, engine="openpyxl")
            headers = mat.iloc[0].dropna().tolist()
            cols = [((cl["Ramo2"].fillna(0).astype(int).astype(str) == str(h)) | (cl[c_func].astype(str) == str(h)) | (a_int_str(cl[c_tr]) == str(h)) | (cl[c_reg].astype(str) == str(h))).astype(int).astype(str) for h in headers]
            firma = pd.concat(cols, axis=1).agg(".".join, axis=1)
            for nombre, k in [("xDnCostoXL", "dncostoxl"), ("xDnRecup", "dnrecup")]:
                if existe(p, k):
                    dn = pd.read_excel(p[k], sheet_name=0, header=None, engine="openpyxl")
                    keys = set(dn.iloc[1:, 0].astype(str).str.strip())
                    agrega(f"{nombre} (firma ContratosXL)", firma, firma.isin(keys))
        except Exception as ex:
            log.warning("No se pudo verificar la firma ContratosXL: %s", ex)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# =============================================================================
# MAIN
# =============================================================================
def validar_entradas(p):
    if not os.path.isfile(p["ppto"]):
        raise ErrorRedistribucion(f"No existe el presupuesto: {p['ppto']}")
    if not any(existe(p, k) for k in ("hist", "pesos", "td")) and not existe(p, "layout"):
        raise ErrorRedistribucion("No se encontró ningún insumo de pesos (histórico, tabla de pesos o TD) ni layout. Revise las rutas en DEFAULTS o los argumentos.")
    os.makedirs(p["out_dir"], exist_ok=True)
    if not p["dry_run"]:
        os.makedirs(os.path.dirname(os.path.abspath(p["salida"])) or ".", exist_ok=True)
        if os.path.abspath(p["salida"]) == os.path.abspath(p["ppto"]) and not p["sobrescribir_input"]:
            raise ErrorRedistribucion("La salida es el mismo archivo que el presupuesto de entrada; use --sobrescribir-input para que el original se respalde antes de escribir.")
    if p["metodo_pesos"] not in METODOS:
        raise ErrorRedistribucion(f"metodo_pesos inválido: {p['metodo_pesos']}")
    if p["comisiones"] not in ("propio", "prima", "no") or p["siniestros"] not in ("prima", "propio", "no"):
        raise ErrorRedistribucion("Políticas de comisiones/siniestros inválidas.")


def main(p):
    t0 = time.perf_counter()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = setup_logger(p["out_dir"], ts)
    log.info("=== Redistribución TEV/HyOR %s | script v%s | pandas %s === parámetros: %s", zAño, VERSION, pd.__version__, {k: v for k, v in p.items() if k != "out_dir"})
    validar_entradas(p)

    # ---- 0. Anti doble aplicación ----
    registro = os.path.join(p["out_dir"], "registro_salidas.txt")
    h_in = sha256_archivo(p["ppto"])
    if os.path.isfile(registro):
        previas = [l.split("\t") for l in open(registro, encoding="utf-8").read().splitlines() if "\t" in l]
        hit = [l for l in previas if len(l) >= 2 and l[1] == h_in]
        if hit:
            raise ErrorRedistribucion(f"El presupuesto de entrada es idéntico (sha256) a una salida previa de este script ({hit[0][0]}, {hit[0][-1]}). "
                                      "Corra siempre desde el presupuesto original para no aplicar la redistribución dos veces.")
    log.info("sha256 del presupuesto de entrada: %s", h_in)

    # ---- 1. Presupuesto (idéntico a CtaMens.py) ----
    df, enc = leer_tabla(p["ppto"])
    cols_orig = list(df.columns)
    if len(cols_orig) < 10:
        raise ErrorRedistribucion(f"El presupuesto sólo tiene {len(cols_orig)} columnas; se esperaban las 45 del extracto SAP. ¿Separador o archivo equivocado?")
    df["_ID_ORIGEN"] = df.index
    c_prof, c_amt, c_gl, c_fy, c_mes = col(df, "PROF"), col(df, "AMT"), col(df, "GL"), col(df, "FY"), col(df, "MES")
    c_amt_t = col(df, "AMT_T", obligatoria=False)
    for k in ("TIPOREA", "CED", "CTO", "FUNC"):
        col(df, k)
    df[c_amt] = a_num_estricto(df[c_amt], c_amt, "Presupuesto")
    if df[c_amt].isna().any():
        raise ErrorRedistribucion(f"Presupuesto: {int(df[c_amt].isna().sum())} filas con {c_amt} vacío; corrija el insumo antes de redistribuir.")
    if c_amt_t is not None and df[c_amt_t].notna().any():
        df[c_amt_t] = a_num_estricto(df[c_amt_t], c_amt_t, "Presupuesto")
    log.info("Presupuesto: %s filas x %s columnas (lectura %s) | total %s = %s", len(df), len(cols_orig), enc, c_amt, round(df[c_amt].sum(), 2))

    subramo_df = None
    if existe(p, "subramo"):
        subramo_df, _ = leer_tabla(p["subramo"]); log.info("Subramo.csv: %s filas (columnas %s)", len(subramo_df), list(subramo_df.columns)[:6])
    else:
        log.info("Sin Subramo.csv: el ramo se deriva de los dígitos 2-4 de %s", c_prof)

    df["TIPO"] = df[c_gl].astype(str).str[:2].map(TIPO_POR_GL)
    col_ramo_sub = "Ramo2" if (subramo_df is not None and "Ramo2" in subramo_df.columns) else "Ramo"  # CtaMens arma LLAVE1/cesión/XL con Ramo2
    df["RAMO"] = ramo_desde_proftctr(df[c_prof], subramo_df, col_ramo_sub)
    if subramo_df is not None:
        digitos = pd.to_numeric(df[c_prof].astype(str).str[1:4], errors="coerce")
        disc = df.loc[(df["RAMO"] != digitos) & (digitos.isin(p["ramos"]) | df["RAMO"].isin(p["ramos"])), c_prof].astype(str).unique()
        if len(disc):
            log.warning("Subramo.csv (%s) asigna a %s un ramo distinto de los dígitos del centro de beneficio; se usa Subramo (así lo hace CtaMens)", col_ramo_sub, sorted(disc)[:10])
    df["ZTIPOREAS_LL"], df["ZCEDENTE_LL"], df["ZCONTRATO_LL"] = a_int_str(df[col(df, "TIPOREA")]), a_int_str(df[col(df, "CED")]), a_int_str(df[col(df, "CTO")])
    df["FUNCAREA_LL"] = df[col(df, "FUNC")].astype(str).str.strip().str.upper()
    df["LLAVE"] = df["ZTIPOREAS_LL"] + "-" + df["ZCEDENTE_LL"] + "-" + df["ZCONTRATO_LL"] + "-" + df["FUNCAREA_LL"]
    cat = df[df["RAMO"].isin(p["ramos"])]
    if cat.empty:
        raise ErrorRedistribucion(f"El presupuesto no tiene filas de los ramos {p['ramos']} (PROFTCTR observados: {sorted(df[c_prof].astype(str).unique())[:20]}).")
    universo = set(cat["LLAVE"])
    log.info("Ramos %s en el presupuesto: %s filas | %s LLAVEs | códigos %s", p["ramos"], len(cat), len(universo),
             {int(k): sorted(map(str, v)) for k, v in cat.groupby("RAMO")[c_prof].unique().to_dict().items()})
    log.info("Montos por tipo y ramo (todos los años fiscales):\n%s", cat.pivot_table(index="TIPO", columns="RAMO", values=c_amt, aggfunc="sum").round(2).to_string())

    # ---- 2. Pesos ----
    fuentes, hnorm, meses, tol_sug, sens, tend = [], None, None, None, pd.DataFrame(), pd.DataFrame()
    if existe(p, "hist"):
        hist, _ = leer_tabla(p["hist"])
        hnorm, meses = preparar_hist(hist, p["ramos"], log)
        pesos = pesos_desde_hist(hnorm, meses, p["ramos"], p["anios_base"], p["metodo_pesos"], p["min_meses_anio"], log); fuentes.append(f"hist={p['hist']}")
        tol_sug = tolerancia_sugerida(hnorm, p["ramos"], log)
        sens = sensibilidad_pesos(hnorm, meses, p["ramos"], p["anios_base"], p["min_meses_anio"], p["tolerancia"])
        if len(sens):
            log.info("Sensibilidad entre métodos de peso: %s LLAVE-tipo SENSIBLES (dif > %s) de %s", int(sens["SENSIBLE"].sum()), p["tolerancia"], len(sens))
        tend = validacion_tendencia(hnorm, df, c_amt, c_fy, p["anio_decision"], p["ramos"], log)
    elif existe(p, "pesos"):
        pesos = pesos_desde_tabla(pd.read_excel(p["pesos"], sheet_name="Pesos", engine="openpyxl"), p["ramos"], log); fuentes.append(f"pesos={p['pesos']}")
    elif existe(p, "td"):
        pesos = pesos_desde_td(pd.read_excel(p["td"], sheet_name="TD", engine="openpyxl"), p["ramos"], log); fuentes.append(f"td={p['td']}")
    else:
        pesos = marco_pesos_vacio()
        log.warning("No se encontró histórico, tabla de pesos ni TD: sólo se aplicará el layout (FORZAR).")
    decisiones, metodos = {}, {}
    if existe(p, "layout"):
        pesos, decisiones, metodos = aplicar_layout(pesos, pd.read_excel(p["layout"], sheet_name=0, engine="openpyxl"), p["ramos"], log); fuentes.append(f"layout={p['layout']}")
    if metodos:
        if hnorm is None:
            raise ErrorRedistribucion("El layout indica METODO por LLAVE pero no hay histórico; METODO sólo aplica con histórico real.")
        for m in set(metodos.values()):
            alt = pesos_desde_hist(hnorm, meses, p["ramos"], p["anios_base"], m, p["min_meses_anio"], logger_silencioso())
            ll = [l for l, mm in metodos.items() if mm == m]
            pesos = pd.concat([pesos[~pesos["LLAVE"].isin(ll)], alt[alt["LLAVE"].isin(ll)]], ignore_index=True)
        log.info("Pesos con método propio por LLAVE (layout INCLUIR+METODO): %s", metodos)
    pesos = completar_pesos(pesos, p["ramos"])
    no_cruzan = sorted(set(pesos["LLAVE"]) - universo)
    if no_cruzan:
        log.warning("LLAVEs con pesos que NO existen en el presupuesto con ramos %s (se listan en LLAVEs_No_Cruzan): %s, p.ej. %s", p["ramos"], len(no_cruzan), no_cruzan[:5])
    lay_no = sorted(set(decisiones) - universo)
    if lay_no:
        raise ErrorRedistribucion(f"El layout contiene decisiones para LLAVEs que no existen en el presupuesto con ramos {p['ramos']}: {lay_no[:10]}. Corrija la LLAVE (formato TipoRea-Cedente-Contrato-LN) o elimine la fila.")
    n_val = pesos[pesos["VALIDO"] & (pesos["TIPO"] == "Primas")]["LLAVE"].nunique() if len(pesos) else 0
    n_inv = pesos[~pesos["VALIDO"]][["LLAVE", "TIPO"]].drop_duplicates().shape[0] if len(pesos) else 0
    log.info("Pesos: %s LLAVEs con pesos válidos de Primas | LLAVE-tipo inválidas: %s | LLAVEs de pesos que no cruzan: %s", n_val, n_inv, len(no_cruzan))
    pesos_ef = pesos_efectivos(pesos if len(pesos) else marco_pesos_vacio(), p["ramos"], p["comisiones"], p["siniestros"])

    # ---- 3. Alcance ----
    alcance = tabla_alcance(df, c_amt, c_fy, pesos, pesos_ef, sens, decisiones, p["ramos"], p, log)
    llaves_aj = alcance.loc[alcance["DECISION"] == "AJUSTAR", "LLAVE"].tolist()
    # diagnósticos de cobertura: % de la prima del año de decisión con pesos, y firmas huérfanas en LLAVEs con ambos ramos
    dec_rows = cat[(cat[c_fy] == p["anio_decision"]) & (cat["TIPO"] == "Primas") & (cat[c_amt] != 0)]
    prima_dec = dec_rows.groupby("LLAVE")[c_amt].sum().abs()
    con_peso = set(pesos_ef.loc[pesos_ef["TIPO"] == "Primas", "LLAVE"])
    cobertura = float(prima_dec[prima_dec.index.isin(con_peso)].sum() / prima_dec.sum()) if prima_dec.sum() > 0 else np.nan
    cols_firma_diag = [c for c in cols_orig if c not in {c_prof, c_amt, c_amt_t}]
    biramo = set(alcance.loc[alcance["TIENE_AMBOS_RAMOS"], "LLAVE"])
    huerfanas = 0
    if biramo:
        fr = dec_rows[dec_rows["LLAVE"].isin(biramo)].groupby(cols_firma_diag, dropna=False)["RAMO"].nunique()
        huerfanas = int((fr < len(p["ramos"])).sum())
    log.info("Cobertura: %.1f%% de la prima %s de los ramos %s pertenece a LLAVEs con pesos | firmas con un solo ramo en LLAVEs bi-ramo: %s (si son muchas, alguna columna de la firma difiere entre ramos)",
             (cobertura or 0) * 100, p["anio_decision"], p["ramos"], huerfanas)
    if pd.notna(cobertura) and cobertura < 0.5:
        log.warning("Menos del 50%% de la prima del año de decisión tiene pesos: revise la codificación del histórico (LLAVE, ramo, cuenta) antes de usar el resultado")

    # ---- 4. Redistribución + controles ----
    salida, detalle, ctrl, verif, n_omit = None, pd.DataFrame(), None, pd.DataFrame(), 0
    if p["dry_run"]:
        log.info("DRY-RUN: no se redistribuye ni se escribe el csv.")
    else:
        salida, detalle, n_omit = redistribuir(df, cols_orig, c_prof, c_amt, c_amt_t, c_fy, pesos_ef, llaves_aj, p["ramos"], p["anios_fiscales"],
                                               p["conservar_filas_cero"], p["decimales"], log)
        ctrl, salida_prep = controles(df, salida, detalle, n_omit, pesos_ef, cols_orig, c_prof, c_amt, c_amt_t, c_fy, c_mes, p["ramos"], llaves_aj, 1e-3,
                                      p["anios_fiscales"], subramo_df, log)
        salida_prep["_ID_ORIGEN"] = salida["_ID_ORIGEN"].values
        verif = verificar_insumos_ctamens(None, salida_prep, detalle, p, subramo_df, c_prof, c_amt, c_fy, p["ramos"], log)
    fallas = ctrl["fallas"] if ctrl else []
    for f in fallas:
        log.error("CONTROL FALLIDO: %s", f)
    if salida is not None and not fallas:
        destino = p["salida"]
        if p["sobrescribir_input"]:
            bdir = os.path.join(os.path.dirname(os.path.abspath(p["ppto"])), "Backups"); os.makedirs(bdir, exist_ok=True)
            respaldo = os.path.join(bdir, os.path.basename(p["ppto"]).replace(".csv", f"_PreRedist_{ts}.csv"))
            if os.path.exists(respaldo):
                raise ErrorRedistribucion(f"Ya existe el respaldo {respaldo}; no se sobrescribe.")
            shutil.copy2(p["ppto"], respaldo); destino = p["ppto"]
            log.info("Original respaldado en %s", respaldo)
        tmp = destino + ".tmp"
        salida[cols_orig].to_csv(tmp, index=False, encoding="utf-8-sig")
        os.replace(tmp, destino)
        h_out = sha256_archivo(destino)
        with open(registro, "a", encoding="utf-8") as fh:
            fh.write(f"{ts}\t{h_out}\t{os.path.abspath(destino)}\n")
        log.info("CSV redistribuido escrito: %s (%s filas) | sha256 %s", destino, len(salida), h_out)

    # ---- 5. Trazabilidad (también cuando un control falla, para poder diagnosticar) ----
    sufijo = "_CONTROL_FALLIDO" if fallas else ""
    resumen = {
        "version_script": VERSION, "fecha": ts, "aprobacion": p.get("aprobacion", ""), "controles": ("FALLIDOS: " + " | ".join(fallas)) if fallas else ("OK" if ctrl else "dry-run"),
        "ppto": p["ppto"], "sha256_entrada": h_in, "fuentes_pesos": " ; ".join(fuentes) or "ninguna",
        "cobertura_prima_con_pesos": cobertura, "firmas_huerfanas_llaves_biramo": huerfanas,
        "ramos": str(p["ramos"]), "anio_decision": p["anio_decision"], "anios_base": str(p["anios_base"]), "metodo_pesos": p["metodo_pesos"],
        "min_meses_anio": p["min_meses_anio"], "tolerancia": p["tolerancia"], "tolerancia_sugerida_por_dato_p90": tol_sug, "modo_alcance": p["modo_alcance"],
        "ajustar_split_explicito": p["ajustar_split_explicito"], "reclasificacion_total": p["reclasificacion_total"], "materialidad": p["materialidad"],
        "credibilidad_pct": p["credibilidad_pct"], "banda_ratio": str(p["banda_ratio"]), "revisar_sensibles": p["revisar_sensibles"],
        "revisar_facultativos": p["revisar_facultativos"], "excluir_funcarea": str(p["excluir_funcarea"]), "politica_comisiones": p["comisiones"],
        "politica_siniestros": p["siniestros"], "anios_fiscales": str(p["anios_fiscales"]), "decimales": p["decimales"],
        "conservar_filas_cero": p["conservar_filas_cero"], "llaves_7173_en_ppto": int(len(alcance)), "llaves_ajustadas": len(llaves_aj),
        "llaves_revisar": int((alcance["DECISION"] == "REVISAR").sum()) if len(alcance) else 0,
        "llaves_sin_peso": int((alcance["DECISION"] == "SIN_PESO").sum()) if len(alcance) else 0, "llaves_pesos_no_cruzan": len(no_cruzan),
        "filas_antes": len(df), "filas_despues": (len(salida) if salida is not None else None),
        "dif_total_global": (ctrl["dif_global"] if ctrl else None), "max_dif_firma": (ctrl["max_dif_firma"] if ctrl else None),
        "max_dif_llave_tipo_anio_mes": (ctrl["max_dif_llave_tipo_anio_mes"] if ctrl else None),
        "max_desv_share_vs_peso": (ctrl["max_desv_share_vs_peso"] if ctrl else None),
        "movimientos": (detalle["MOVIMIENTO"].value_counts().to_dict() if len(detalle) else {}), "dry_run": p["dry_run"],
        "nota": "Las filas fuera del alcance son idénticas en valor y tipo al leer con pd.read_csv(thousands=','); el texto del csv se reserializa.",
    }
    traza = os.path.join(p["out_dir"], f"Trazabilidad_Redistribucion_TEV_HyOR_{ts}{sufijo}.xlsx")
    det_csv = os.path.join(p["out_dir"], f"Detalle_Filas_{ts}{sufijo}.csv")
    with pd.ExcelWriter(traza, engine="openpyxl") as w:
        pd.DataFrame([{"PARAMETRO": k, "VALOR": str(v)} for k, v in resumen.items()]).to_excel(w, sheet_name="Resumen", index=False)
        alcance.to_excel(w, sheet_name="Alcance_LLAVEs", index=False)
        if len(alcance):
            alcance[alcance["DECISION"] == "REVISAR"].to_excel(w, sheet_name="LLAVEs_Revisar", index=False)
            alcance[alcance["DECISION"] == "SIN_PESO"].to_excel(w, sheet_name="LLAVEs_Sin_Peso", index=False)
        pesos.to_excel(w, sheet_name="Pesos_Calculados", index=False)
        pesos_ef.to_excel(w, sheet_name="Pesos_Aplicados", index=False)
        if len(sens):
            sens.to_excel(w, sheet_name="Sensibilidad_Metodos", index=False)
        if len(tend):
            tend.to_excel(w, sheet_name="Validacion_Tendencia", index=False)
        if len(detalle):
            detalle.to_csv(det_csv, index=False, encoding="utf-8-sig")
            if len(detalle) <= p["max_filas_excel_detalle"]:
                detalle.to_excel(w, sheet_name="Detalle_Filas", index=False)
            else:
                pd.DataFrame([{"NOTA": f"Detalle_Filas tiene {len(detalle)} filas; se escribió en {det_csv}"}]).to_excel(w, sheet_name="Detalle_Filas", index=False)
        if ctrl:
            ctrl["participacion"].to_excel(w, sheet_name="Control_Participacion", index=False)
            ctrl["participacion_llave"].to_excel(w, sheet_name="Control_Share_LLAVE", index=False)
            ctrl["cuadre_tipo_anio"].to_excel(w, sheet_name="Control_Tipo_Anio", index=False)
            c = ctrl["cuadre_llave_tipo_anio_mes"]; c = c[c["LLAVE"].isin(llaves_aj)]
            c.head(p["max_filas_excel_detalle"]).to_excel(w, sheet_name="Control_LLAVE_Mes", index=False)
            cn = pd.concat([v.assign(NIVEL=k) for k, v in ctrl["combos_nuevos"].items()], ignore_index=True) if ctrl["combos_nuevos"] else pd.DataFrame()
            cn.to_excel(w, sheet_name="Combos_Nuevos", index=False)
            cd = pd.concat([v.assign(NIVEL=k) for k, v in ctrl["combos_desaparecen"].items()], ignore_index=True) if ctrl["combos_desaparecen"] else pd.DataFrame()
            cd.to_excel(w, sheet_name="Combos_Desaparecen", index=False)
            if len(verif):
                verif.to_excel(w, sheet_name="Verif_Insumos_CtaMens", index=False)
        pd.DataFrame({"LLAVE_SIN_CRUCE": no_cruzan}).to_excel(w, sheet_name="LLAVEs_No_Cruzan", index=False)
    log.info("Trazabilidad escrita: %s%s", traza, f" | detalle fila a fila: {det_csv}" if len(detalle) else "")
    log.info("Resumen: %s", resumen)
    log.info("Tiempo: %.1f s", time.perf_counter() - t0)
    if fallas:
        raise AssertionError("Los controles de cuadre fallaron; no se escribió el csv. Vea el log y la trazabilidad con sufijo _CONTROL_FALLIDO.")
    return resumen


def parse_args():
    ap = argparse.ArgumentParser(description="Redistribución TEV (73) / HyOR (71) previa a CtaMens.py")
    for k in ["ppto", "hist", "pesos", "td", "layout", "subramo", "salida", "pais", "cesion", "cesionpi", "matxl", "dncostoxl", "dnrecup", "evcat", "attritional"]:
        ap.add_argument(f"--{k}")
    ap.add_argument("--out-dir", dest="out_dir"); ap.add_argument("--cesion-hist", dest="cesion_hist")
    ap.add_argument("--ramos", help="p.ej. 71,73"); ap.add_argument("--anio-decision", dest="anio_decision", type=int)
    ap.add_argument("--anios-base", dest="anios_base", help="p.ej. 2025,2026"); ap.add_argument("--metodo-pesos", dest="metodo_pesos", choices=METODOS)
    ap.add_argument("--min-meses-anio", dest="min_meses_anio", type=int); ap.add_argument("--tolerancia", type=float)
    ap.add_argument("--modo-alcance", dest="modo_alcance", choices=["auto", "layout"])
    ap.add_argument("--ajustar-split-explicito", dest="ajustar_split_explicito", action="store_true", help="ajusta también LLAVEs que ya traen ambos ramos")
    ap.add_argument("--reclasificacion-total", dest="reclasificacion_total", choices=["revisar", "auto"])
    ap.add_argument("--materialidad", type=float, help="|prima 71+73| mínima en el año de decisión para ajustar (MXN)")
    ap.add_argument("--credibilidad-pct", dest="credibilidad_pct", type=float); ap.add_argument("--banda-ratio", dest="banda_ratio", help="p.ej. 0.33,3")
    ap.add_argument("--no-revisar-sensibles", dest="no_revisar_sensibles", action="store_true"); ap.add_argument("--no-revisar-facultativos", dest="no_revisar_facultativos", action="store_true")
    ap.add_argument("--excluir-funcarea", dest="excluir_funcarea", help="LN separadas por coma; '' para ninguna")
    ap.add_argument("--comisiones", choices=["propio", "prima", "no"]); ap.add_argument("--siniestros", choices=["prima", "propio", "no"])
    ap.add_argument("--anios-fiscales", dest="anios_fiscales", help="'todos' o p.ej. 2027")
    ap.add_argument("--decimales", type=int); ap.add_argument("--no-conservar-cero", dest="no_conservar_cero", action="store_true", help="omite del csv las filas que la redistribución deja en 0")
    ap.add_argument("--sobrescribir-input", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--aprobacion", help="responsable y fecha de aprobación de parámetros y layout (corrida productiva)")
    a = ap.parse_args()
    p = dict(DEFAULTS)
    for k in ["ppto", "hist", "pesos", "td", "layout", "subramo", "salida", "out_dir", "pais", "cesion", "cesionpi", "cesion_hist", "matxl", "dncostoxl", "dnrecup",
              "evcat", "attritional", "anio_decision", "metodo_pesos", "min_meses_anio", "tolerancia", "comisiones", "siniestros", "decimales", "modo_alcance",
              "reclasificacion_total", "materialidad", "credibilidad_pct", "aprobacion"]:
        v = getattr(a, k)
        if v is not None:
            p[k] = v
    if a.ramos: p["ramos"] = [int(x) for x in a.ramos.split(",")]
    if a.anios_base: p["anios_base"] = [int(x) for x in a.anios_base.split(",")]
    if a.banda_ratio: p["banda_ratio"] = [float(x) for x in a.banda_ratio.split(",")]
    if a.excluir_funcarea is not None: p["excluir_funcarea"] = [x.strip() for x in a.excluir_funcarea.split(",") if x.strip()]
    if a.anios_fiscales: p["anios_fiscales"] = "todos" if a.anios_fiscales == "todos" else [int(x) for x in a.anios_fiscales.split(",")]
    if a.ajustar_split_explicito: p["ajustar_split_explicito"] = True
    if a.no_revisar_sensibles: p["revisar_sensibles"] = False
    if a.no_revisar_facultativos: p["revisar_facultativos"] = False
    if a.no_conservar_cero: p["conservar_filas_cero"] = False
    if a.sobrescribir_input: p["sobrescribir_input"] = True
    if a.dry_run: p["dry_run"] = True
    return p


if __name__ == "__main__":
    _p = parse_args()
    try:
        main(_p)
        _ok = True
    except Exception as e:  # el error queda en el log y en un archivo visible en la carpeta de salida
        _ok = False
        _log = logging.getLogger("redist")
        if _log.handlers:
            _log.exception("LA REDISTRIBUCIÓN SE DETUVO CON ERROR: %s", e)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        try:
            os.makedirs(_p["out_dir"], exist_ok=True)
            with open(os.path.join(_p["out_dir"], f"ERROR_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"{type(e).__name__}: {e}\n")
        except Exception:
            pass
    finally:
        for h in list(logging.getLogger("redist").handlers):
            h.close()
    if os.name == "nt" and sys.stdout.isatty():
        try:
            input("Presione Enter para cerrar...")
        except Exception:
            pass
    sys.exit(0 if _ok else 1)
