# -*- coding: utf-8 -*-
"""
0a_Actualizar_Base1.py  (versión 1.1)
=====================================
Actualiza la Base_1 (histórico REAL por LLAVE, DescRamo, AñoCont y MesCont con PmaTom, CosTom, SinTom, ...)
con la información real del año en curso, para que 0_Redistribucion_TEV_HyOR.py calcule los pesos por ramo
con historia completa y para que Base1_global.py (dashboard y banderas) trabaje con la base al día.

Qué hace:
  1. Lee la Base_1 PREVIA (la del año pasado; nunca se modifica).
  2. Lee la información NUEVA (uno o varios archivos, o una carpeta). Reconoce dos formatos:
       a) formato Base_1 (mismas columnas: LLAVE, DescRamo, AñoCont, MesCont, PmaTom, ...), o
       b) extracto SAP BW de reales (columnas /ERP/GL_ACCT, /ERP/AMOUNT, /ERP/PROFTCTR, /ERP/FUNCAREA, ZTIPOREAS,
          ZCEDENTE, ZCONTRATO, 0CALMONTH o 0FISCPER, ...), que convierte al formato Base_1:
            - LLAVE = ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA (contrato nulo = 0; misma regla que CtaMens y la redistribución)
            - AñoCont / MesCont desde 0CALMONTH (o 0FISCPER, variante K4 = calendario)
            - DescRamo desde /ERP/PROFTCTR: primero con lo que ya dice la Base_1 previa (si trae CeBe/PROFTCTR),
              después con Subramo.csv, y siempre traducido a la ortografía de la Base_1 previa
            - Territorio desde ZREGIONRP con Pais.csv (como CtaMens)
            - Métricas por prefijo de cuenta: 61 -> PmaTom, 53 -> CosTom, 54 -> SinTom (signo SAP corregido)
            - Las demás columnas de la Base_1 se llenan sólo si se pueden derivar del dato (directas o aprendidas
              de la Base_1 previa de forma unívoca); si no, quedan vacías y se reporta.
  3. Une: los periodos (AñoCont, MesCont) que trae la información nueva REEMPLAZAN completos a los mismos periodos
     de la Base_1 previa (no se suman, para no duplicar); los demás periodos de la previa quedan intactos.
  4. VALIDA contra la previa en los meses de traslape (meses que están en ambas): por métrica y por ramo, la
     información nueva debe reproducir la previa (tolerancia 1 %). Así se comprueba, con datos y no con supuestos,
     que la consulta nueva tiene la misma definición que la Base_1 (cuentas, signo, LLAVE, ramo). Si no cuadra, NO
     escribe la base y deja el detalle en el libro de control.
  5. Escribe la Base_1 actualizada (csv, que es el insumo por defecto de la redistribución, y xlsx si cabe), un libro
     de control y un log.

Uso:
  python 0a_Actualizar_Base1.py                                   -> rutas por defecto (abajo)
  python 0a_Actualizar_Base1.py --dry-run                         -> sólo valida y genera el libro de control
  python 0a_Actualizar_Base1.py --previa "...\\Base_1.xlsx" --nueva "...\\Real_2026.csv"
  python 0a_Actualizar_Base1.py --help
"""

import argparse
import getpass
import logging
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd

VERSION = "1.1"

# =============================================================================
# PARÁMETROS (editar aquí o pasar por línea de comandos)
# =============================================================================
zAño = 2027
_aqui = os.path.dirname(os.path.abspath(__file__))
_ctamens = fr"C:\Users\{getpass.getuser()}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\{zAño}\5_Generacion"
# La carpeta de trabajo es donde vive este script (5_Generacion); si ahí no hay carpeta Inputs, se usa la ruta estilo CtaMens.
xFolder = _aqui if os.path.isdir(os.path.join(_aqui, "Inputs")) else _ctamens
# La carpeta se acepta con o sin acento ("Redistribución" / "Redistribucion")
xRed = next((os.path.join(xFolder, "Inputs", n) for n in ("Redistribucion", "Redistribución") if os.path.isdir(os.path.join(xFolder, "Inputs", n))),
            os.path.join(xFolder, "Inputs", "Redistribucion"))

DEFAULTS = {
    "previa": os.path.join(xRed, "Base_1.xlsx"),                    # Base_1 del año pasado (no se modifica)
    "nueva": [os.path.join(xRed, "Base1_Nueva")],                   # archivo(s) o carpeta con la información real nueva
    "subramo": os.path.join(xFolder, "Inputs", "Subramo.csv"),      # CeBe -> ramo (sólo para formato SAP)
    "pais": os.path.join(xFolder, "Inputs", "Pais.csv"),            # TerrSAP -> Territorio (sólo para formato SAP)
    "mapa_descramo": "",                                            # opcional: CeBe -> DescRamo (prevalece sobre Subramo)
    "mapa_gl": "",                                                  # opcional: GL (prefijo) -> METRICA, SIGNO
    "salida_csv": os.path.join(xRed, "Hist_Real_LLAVE_Ramo.csv"),   # insumo por defecto de 0_Redistribucion_TEV_HyOR.py
    "salida_xlsx": os.path.join(xRed, "Base_1_Actualizada.xlsx"),   # para Base1_global.py (si cabe en Excel)
    "out_dir": os.path.join(xFolder, "Outputs", "Actualizacion_Base1"),
    "filtros": [],                                                  # p.ej. ["/ERP/CATEGORY=REAL01"]
    "tolerancia_traslape": 0.01,                                    # 1 % por métrica y por ramo en los meses de traslape
    "materialidad_traslape": 1000.0,                                # |monto| mínimo de la previa para evaluar un ramo
    "signos": {},                                                   # p.ej. {"PmaTom": -1}; vacío = defecto + verificación por traslape
    "aceptar_traslape": "",                                         # justificación para escribir aunque el traslape no cuadre
    "sin_traslape": "",                                             # justificación para escribir sin meses de traslape (formato SAP)
    "permitir_descramo_nuevo": False,
    "especiales_a_diciembre": False,                                # periodos 13-16 de 0FISCPER -> mes 12
    "escribir_xlsx": True,
    "conservar_posteriores": False,                                 # conservar periodos de la previa posteriores a la fecha del archivo
    "dry_run": False,
}

# Cuenta SAP (prefijo) -> métrica de la Base_1 y signo para pasar de convención SAP a convención Base_1.
# En SAP las primas (61) vienen negativas y la Base_1 las guarda positivas. El signo se verifica con el traslape.
MAPA_GL_DEFECTO = [("61", "PmaTom", -1.0), ("53", "CosTom", 1.0), ("54", "SinTom", 1.0)]
METRICAS_CONOCIDAS = ["PmaTom", "PmaRet", "SinTom", "SinRet", "CosTom", "CosRet", "ComTom", "ComRet"]
FILAS_MAX_EXCEL = 1_048_575


class ErrorBase1(Exception):
    """Error de negocio con mensaje claro para el analista."""


# =============================================================================
# UTILIDADES
# =============================================================================
def norm(s):
    """Nombre de columna normalizado: mayúsculas, sin acentos, sin espacios, '_', '/', '.' ni '-'. 'AñoCont' -> 'ANOCONT'."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\s_/\.\-]", "", s).upper()


def norm_txt(s):
    """Valor de texto normalizado para comparar ('HyORH ' == 'HYORH', 'Hidrometeorológicos' == 'HIDROMETEOROLOGICOS')."""
    if pd.isna(s):
        return ""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").strip().upper()


def buscar(df, candidatos):
    """Nombre real de la primera columna de df cuyo nombre normalizado está en candidatos."""
    m = {norm(c): c for c in df.columns}
    return next((m[norm(k)] for k in candidatos if norm(k) in m), None)


def tramo(v):
    """Segmento de LLAVE: número entero como texto; vacío/NaN -> '0'; texto -> mayúsculas (regla de CtaMens)."""
    if pd.isna(v):
        return "0"
    t = str(v).strip()
    if t == "" or t.lower() in ("nan", "none"):
        return "0"
    try:
        f = float(t.replace(",", ""))
        return str(int(f)) if f == int(f) else t
    except ValueError:
        return t.upper()


def llave_canonica(serie):
    """'1-40.0-16-ln04001 ' -> '1-40-16-LN04001' (sólo para comparar; la Base_1 previa se escribe tal cual)."""
    return serie.astype(str).str.strip().map(lambda s: "-".join(tramo(x) for x in s.split("-")) if s and s.lower() != "nan" else "")


def a_num(serie, nombre, contexto):
    """Numérico estricto: aborta si hay texto no numérico (p.ej. '1,234' mal leído o '#N/A')."""
    s = serie
    if s.dtype == object or str(s.dtype) in ("string", "str"):
        s = s.astype(str).str.strip().str.replace(",", "", regex=False)
        s = s.where(~s.isin(["", "nan", "None", "NaN", "<NA>"]), np.nan)
    num = pd.to_numeric(s, errors="coerce")
    malos = num.isna() & s.notna()
    if malos.any():
        raise ErrorBase1(f"{contexto}: la columna {nombre} tiene {int(malos.sum())} valores no numéricos, p.ej. {serie[malos].astype(str).head(5).tolist()}.")
    return num.astype("float64")


def leer(path):
    """csv (coma, miles con ',', utf-8 o latin-1) o Excel (primera hoja)."""
    low = path.lower()
    if low.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(path, sheet_name=0, engine="openpyxl")
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(path, thousands=",", encoding=enc, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
    if df.shape[1] == 1 and ";" in str(df.columns[0]):
        df = pd.read_csv(path, sep=";", encoding=enc, low_memory=False)
    return df


def archivos_nuevos(rutas):
    out = []
    for r in rutas:
        if os.path.isdir(r):
            for f in sorted(os.listdir(r)):
                if f.lower().endswith((".csv", ".xlsx", ".xlsm", ".xls", ".txt")) and not f.startswith("~$"):
                    out.append(os.path.join(r, f))
        elif os.path.isfile(r):
            out.append(r)
        else:
            raise ErrorBase1(f"No existe la ruta de información nueva: {r}\n"
                             "Cree esa carpeta y deje ahí el extracto REAL del año en curso (csv o xlsx, formato Base_1 o extracto SAP BW de reales), "
                             "incluyendo 2 o 3 meses que ya estén en la Base_1 previa para validar el traslape. O indique el archivo con --nueva \"ruta\".")
    if not out:
        raise ErrorBase1(f"No se encontró ningún archivo de información nueva en {rutas}. Deje ahí el extracto real del año (csv o xlsx).")
    return out


def setup_logger(out_dir, ts):
    os.makedirs(out_dir, exist_ok=True)
    log = logging.getLogger("base1")
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        h.close()
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); log.addHandler(sh)
    fh = logging.FileHandler(os.path.join(out_dir, f"Log_Actualizacion_Base1_{ts}.txt"), encoding="utf-8")
    fh.setFormatter(fmt); log.addHandler(fh)
    return log


# =============================================================================
# BASE_1 PREVIA
# =============================================================================
def esquema_previa(prev):
    """Identifica en la previa las columnas clave, las métricas y las dimensiones."""
    c = {k: buscar(prev, v) for k, v in {
        "LLAVE": ["LLAVE"], "DESC": ["DescRamo"], "ANIO": ["AñoCont", "AnioCont"], "MES": ["MesCont"]}.items()}
    falt = [k for k, v in c.items() if v is None]
    if falt:
        raise ErrorBase1(f"Base_1 previa: faltan columnas {falt}. Se esperan al menos LLAVE, DescRamo, AñoCont, MesCont y PmaTom. Columnas encontradas: {list(prev.columns)}")
    metricas = [col for col in prev.columns if norm(col) in {norm(m) for m in METRICAS_CONOCIDAS}]
    if not any(norm(m) == "PMATOM" for m in metricas):
        raise ErrorBase1("Base_1 previa: no trae la columna PmaTom.")
    dims = [col for col in prev.columns if col not in metricas]
    return c, metricas, dims


def preparar_previa(prev, c, metricas):
    prev = prev.copy()
    prev.columns = [str(x).strip() for x in prev.columns]
    for m in metricas:
        prev[m] = a_num(prev[m], m, "Base_1 previa")
    prev[c["ANIO"]] = a_num(prev[c["ANIO"]], c["ANIO"], "Base_1 previa").astype("Int64")
    prev[c["MES"]] = a_num(prev[c["MES"]], c["MES"], "Base_1 previa").astype("Int64")
    if prev[c["ANIO"]].isna().any() or prev[c["MES"]].isna().any():
        raise ErrorBase1(f"Base_1 previa: {int(prev[c['ANIO']].isna().sum() + prev[c['MES']].isna().sum())} filas sin AñoCont o MesCont.")
    return prev


# =============================================================================
# INFORMACIÓN NUEVA
# =============================================================================
def detectar_formato(df):
    if all(buscar(df, [k]) is not None for k in ["LLAVE", "DescRamo", "MesCont", "PmaTom"]) and buscar(df, ["AñoCont", "AnioCont"]) is not None:
        return "BASE1"
    if all(buscar(df, v) is not None for v in [["/ERP/GL_ACCT", "GL_ACCT"], ["/ERP/AMOUNT", "AMOUNT"], ["/ERP/PROFTCTR", "PROFTCTR", "CeBe"]]):
        return "SAP"
    return None


def nueva_formato_base1(df, prev_cols, metricas, c, log):
    """Alinea un archivo en formato Base_1 con las columnas de la previa (por nombre normalizado)."""
    mapa = {}
    for pc in prev_cols:
        real = buscar(df, [pc])
        if real is not None:
            mapa[pc] = real
    sobran = [x for x in df.columns if x not in mapa.values()]
    faltan = [pc for pc in prev_cols if pc not in mapa]
    out = pd.DataFrame({pc: (df[mapa[pc]] if pc in mapa else np.nan) for pc in prev_cols})
    for m in metricas:
        out[m] = a_num(out[m], m, "Información nueva (formato Base_1)") if m in mapa else np.nan
    out[c["ANIO"]] = a_num(out[c["ANIO"]], c["ANIO"], "Información nueva").astype("Int64")
    out[c["MES"]] = a_num(out[c["MES"]], c["MES"], "Información nueva").astype("Int64")
    if sobran:
        log.info("  columnas del archivo nuevo que no existen en la Base_1 previa (se ignoran): %s", sobran)
    llenado = [{"COLUMNA": pc, "METODO": "DIRECTA (formato Base_1)" if pc in mapa else "VACIA (no viene en el archivo)"} for pc in prev_cols]
    return out, faltan, llenado


def periodo_sap(df, p, log):
    """(año, mes) desde 0CALMONTH (AAAAMM, MM.AAAA) o 0FISCPER (AAAAPPP, PPP.AAAA) o 0FISCYEAR+0FISCPER3. Aborta si no se puede leer."""
    ccal = buscar(df, ["0CALMONTH", "CALMONTH"])
    cfp = buscar(df, ["0FISCPER", "FISCPER"])
    cfy, cp3 = buscar(df, ["0FISCYEAR", "FISCYEAR"]), buscar(df, ["0FISCPER3", "FISCPER3"])
    cvar = buscar(df, ["0FISCVARNT", "FISCVARNT"])
    if cvar is not None:
        var = df[cvar].dropna().astype(str).str.strip().unique().tolist()
        if any(v not in ("K4",) for v in var) and ccal is None:
            raise ErrorBase1(f"Variante de ejercicio {var}: sólo K4 (ejercicio = año calendario) permite usar 0FISCPER como mes; incluya 0CALMONTH en el extracto.")
    def limpia(s):
        return s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    if ccal is not None:
        s = limpia(df[ccal])
        a = pd.Series(np.nan, index=df.index); m = pd.Series(np.nan, index=df.index)
        r1 = s.str.fullmatch(r"\d{6}")
        a[r1] = s[r1].str[:4].astype(float); m[r1] = s[r1].str[4:].astype(float)
        r2 = s.str.fullmatch(r"\d{1,2}[./-]\d{4}")
        a[r2] = s[r2].str[-4:].astype(float); m[r2] = s[r2].str.split(r"[./-]", regex=True).str[0].astype(float)
        r3 = s.str.fullmatch(r"\d{4}[./-]\d{1,2}")
        a[r3] = s[r3].str[:4].astype(float); m[r3] = s[r3].str.split(r"[./-]", regex=True).str[1].astype(float)
        fuente = ccal
    elif cfp is not None or (cfy is not None and cp3 is not None):
        if cfp is not None:
            s = limpia(df[cfp])
            a = pd.Series(np.nan, index=df.index); m = pd.Series(np.nan, index=df.index)
            r1 = s.str.fullmatch(r"\d{7}")
            a[r1] = s[r1].str[:4].astype(float); m[r1] = s[r1].str[4:].astype(float)
            r2 = s.str.fullmatch(r"\d{1,3}[./]\d{4}")
            a[r2] = s[r2].str[-4:].astype(float); m[r2] = s[r2].str.split(r"[./]", regex=True).str[0].astype(float)
            fuente = cfp
        else:
            a = a_num(df[cfy], cfy, "Extracto SAP"); m = a_num(df[cp3], cp3, "Extracto SAP"); fuente = f"{cfy}+{cp3}"
        esp = m > 12
        if esp.any():
            if not p["especiales_a_diciembre"]:
                raise ErrorBase1(f"El extracto trae {int(esp.sum())} filas en periodos especiales (13-16) de {fuente}. Incluya 0CALMONTH en el extracto, "
                                 "o use --especiales-a-diciembre para asignarlos al mes 12 (cierre del ejercicio) dejando constancia.")
            log.warning("  %s filas en periodos especiales 13-16 asignadas al mes 12 (--especiales-a-diciembre)", int(esp.sum()))
            m = m.where(~esp, 12.0)
    else:
        raise ErrorBase1("El extracto SAP no trae periodo: se necesita 0CALMONTH, 0FISCPER o 0FISCYEAR + 0FISCPER3.")
    malos = a.isna() | m.isna() | (m < 1) | (m > 12)
    if malos.any():
        raise ErrorBase1(f"Periodo ilegible en {int(malos.sum())} filas (columna {fuente}), p.ej. {df.loc[malos, fuente if fuente in df.columns else df.columns[0]].astype(str).head(5).tolist()}.")
    return a.astype("Int64"), m.astype("Int64"), fuente


def leer_mapa_gl(p):
    if not p["mapa_gl"]:
        return [(g, m, s) for g, m, s in MAPA_GL_DEFECTO]
    t = leer(p["mapa_gl"])
    cg, cm, cs = buscar(t, ["GL", "GL_PREFIJO", "CUENTA"]), buscar(t, ["METRICA"]), buscar(t, ["SIGNO"])
    if cg is None or cm is None:
        raise ErrorBase1("mapa_gl: necesita columnas GL (prefijo de cuenta) y METRICA; SIGNO opcional (1 o -1).")
    return [(tramo(r[cg]), str(r[cm]).strip(), float(r[cs]) if cs is not None and pd.notna(r[cs]) else 1.0) for _, r in t.iterrows()]


def mapa_cebe_descramo(prev, c, p, log):
    """CeBe -> DescRamo con la ortografía de la Base_1 previa. Devuelve (dict, fuente, conflictos)."""
    valores_prev = prev[c["DESC"]].dropna().astype(str).str.strip().unique().tolist()
    por_norm = {}
    for v in valores_prev:
        por_norm.setdefault(norm_txt(v), v)
    mapa, fuente = {}, {}
    conflictos = []
    # 1) mapa explícito del usuario
    if p["mapa_descramo"]:
        t = leer(p["mapa_descramo"])
        cc, cd = buscar(t, ["CeBe", "PROFTCTR", "/ERP/PROFTCTR"]), buscar(t, ["DescRamo"])
        if cc is None or cd is None:
            raise ErrorBase1("mapa_descramo: necesita columnas CeBe (o PROFTCTR) y DescRamo.")
        for _, r in t.dropna(subset=[cc, cd]).iterrows():
            mapa[str(r[cc]).strip()] = str(r[cd]).strip(); fuente[str(r[cc]).strip()] = "mapa_descramo"
    # 2) lo que ya dice la Base_1 previa, si trae el CeBe
    cprev = buscar(prev, ["CeBe", "PROFTCTR", "/ERP/PROFTCTR"])
    if cprev is not None:
        g = prev.dropna(subset=[cprev, c["DESC"]]).groupby(prev[cprev].astype(str).str.strip())[c["DESC"]].agg(lambda s: sorted(s.astype(str).str.strip().unique()))
        for cebe, vals in g.items():
            if cebe in mapa:
                continue
            if len(vals) == 1:
                mapa[cebe] = vals[0]; fuente[cebe] = "Base_1 previa"
            else:
                conflictos.append({"CeBe": cebe, "DescRamo_en_previa": " | ".join(vals)})
    # 3) Subramo.csv: se elige la columna cuyo texto mejor coincide con los DescRamo de la previa
    if p["subramo"] and os.path.isfile(p["subramo"]):
        sr = leer(p["subramo"])
        cc = buscar(sr, ["CeBe"])
        if cc is not None:
            mejor, score = None, -1.0
            for cand in ["DescRamo", "RamoN", "Ramo2", "Ramo", "Descripcion", "DescRamo2"]:
                cr = buscar(sr, [cand])
                if cr is None:
                    continue
                vals = sr[cr].dropna().map(norm_txt)
                sc = vals.isin(por_norm.keys()).mean() if len(vals) else 0
                if sc > score:
                    mejor, score = cr, sc
            if mejor is not None:
                log.info("  Subramo.csv: columna '%s' para DescRamo (%.0f%% de sus valores existen en la Base_1 previa)", mejor, 100 * score)
                for _, r in sr.dropna(subset=[cc, mejor]).drop_duplicates(cc).iterrows():
                    k = str(r[cc]).strip()
                    if k not in mapa:
                        mapa[k] = str(r[mejor]).strip(); fuente[k] = f"Subramo.csv[{mejor}]"
    # ortografía de la previa
    for k, v in list(mapa.items()):
        if norm_txt(v) in por_norm:
            mapa[k] = por_norm[norm_txt(v)]
    return mapa, fuente, conflictos, set(valores_prev)


def aprender_columna(prev, col_dest, clave_prev):
    """Mapa clave -> valor de col_dest si en la previa la relación es unívoca (cada clave con un solo valor)."""
    d = pd.DataFrame({"K": clave_prev, "V": prev[col_dest]}).dropna()
    if d.empty:
        return None
    n = d.groupby("K")["V"].nunique()
    if (n > 1).any():
        return None
    return d.drop_duplicates("K").set_index("K")["V"]


def nueva_formato_sap(df, prev, prev_cols, metricas, c, p, log, nombre):
    """Convierte un extracto SAP de reales al formato de la Base_1 previa."""
    ctx = f"Extracto SAP {nombre}"
    df = df.copy()
    df.columns = [str(x).strip() for x in df.columns]
    # filtros explícitos
    for f in p["filtros"]:
        if "=" not in f:
            raise ErrorBase1(f"Filtro inválido '{f}': use COLUMNA=VALOR.")
        k, v = f.split("=", 1)
        ck = buscar(df, [k.strip()])
        if ck is None:
            raise ErrorBase1(f"Filtro '{f}': la columna {k} no existe en {nombre}.")
        antes = len(df)
        df = df[df[ck].astype(str).str.strip() == v.strip()]
        log.info("  filtro %s: %s -> %s filas", f, antes, len(df))
    # guardas: no mezclar categorías (real/presupuesto), monedas ni sociedades
    for nombre_col, cand in [("categoría", ["/ERP/CATEGORY", "CATEGORY"]), ("moneda", ["0CURRENCY", "CURRENCY"]), ("sociedad", ["/ERP/COMPCODE", "COMPCODE"])]:
        cc = buscar(df, cand)
        if cc is not None:
            vals = sorted(df[cc].dropna().astype(str).str.strip().unique().tolist())
            if len(vals) > 1:
                raise ErrorBase1(f"{ctx}: trae más de una {nombre_col} en {cc}: {vals}. Filtre con --filtro {cc}=<valor> (p.ej. sólo la categoría de reales).")
            if nombre_col == "categoría" and vals and vals[0].upper().startswith("PRES"):
                raise ErrorBase1(f"{ctx}: la categoría es {vals[0]} (presupuesto). La Base_1 es histórico REAL; use el extracto de reales.")
            log.info("  %s: %s", nombre_col, vals)
    cgl = buscar(df, ["/ERP/GL_ACCT", "GL_ACCT"]); camt = buscar(df, ["/ERP/AMOUNT", "AMOUNT"])
    cprof = buscar(df, ["/ERP/PROFTCTR", "PROFTCTR", "CeBe"]); cfunc = buscar(df, ["/ERP/FUNCAREA", "FUNCAREA"])
    ctr, cced, ccto = buscar(df, ["ZTIPOREAS"]), buscar(df, ["ZCEDENTE"]), buscar(df, ["ZCONTRATO"])
    falt = [n for n, v in [("FUNCAREA", cfunc), ("ZTIPOREAS", ctr), ("ZCEDENTE", cced), ("ZCONTRATO", ccto)] if v is None]
    if falt:
        raise ErrorBase1(f"{ctx}: faltan columnas para construir la LLAVE: {falt}.")
    df["_AMT"] = a_num(df[camt], camt, ctx).fillna(0.0)
    # métricas por prefijo de cuenta (prefijo más largo gana)
    reglas = sorted(leer_mapa_gl(p), key=lambda r: -len(r[0]))
    gl = df[cgl].map(tramo)
    df["_MET"] = None; df["_SIG"] = np.nan
    for pref, met, sig in reglas:
        sel = df["_MET"].isna() & gl.str.startswith(pref)
        df.loc[sel, "_MET"] = met; df.loc[sel, "_SIG"] = sig
    sel_nm = df["_MET"].isna()
    resumen_gl = (df[sel_nm].groupby(gl[sel_nm].str[:2].rename("GL_2"))["_AMT"].agg(FILAS="count", MONTO="sum").reset_index()
                  if sel_nm.any() else pd.DataFrame(columns=["GL_2", "FILAS", "MONTO"]))
    df = df[df["_MET"].notna()].copy()
    if df.empty:
        raise ErrorBase1(f"{ctx}: ninguna cuenta cae en el mapa de métricas {[r[:2] for r in reglas]}.")
    mets_prev = {norm(m): m for m in metricas}
    sin_col = sorted({m for m in df["_MET"].unique() if norm(m) not in mets_prev})
    if sin_col:
        raise ErrorBase1(f"{ctx}: las métricas {sin_col} del mapa de cuentas no existen como columnas en la Base_1 previa ({metricas}).")
    df["_MET"] = df["_MET"].map(lambda m: mets_prev[norm(m)])
    # signo: el del usuario prevalece
    for met, s in p["signos"].items():
        if norm(met) in mets_prev:
            df.loc[df["_MET"] == mets_prev[norm(met)], "_SIG"] = float(s)
    df["_VAL"] = df["_AMT"] * df["_SIG"]
    # periodo
    anio, mes, fuente_per = periodo_sap(df, p, log)
    df["_ANIO"], df["_MES"] = anio.values, mes.values
    # LLAVE y DescRamo
    df["_LLAVE"] = (df[ctr].map(tramo) + "-" + df[cced].map(tramo) + "-" + df[ccto].map(tramo) + "-" + df[cfunc].astype(str).str.strip().str.upper())
    mapa_desc, fuente_desc, conflictos, desc_prev = mapa_cebe_descramo(prev, c, p, log)
    cebe = df[cprof].astype(str).str.strip()
    df["_DESC"] = cebe.map(mapa_desc)
    sin_ramo = df[df["_DESC"].isna()]
    if not sin_ramo.empty:
        t = sin_ramo.groupby(cebe[sin_ramo.index])["_VAL"].agg(["count", "sum"]).sort_values("sum", key=abs, ascending=False)
        raise ErrorBase1(f"{ctx}: {len(t)} centros de beneficio sin DescRamo (ni en la Base_1 previa, ni en Subramo.csv, ni en mapa_descramo). "
                         f"Agréguelos a un mapa CeBe -> DescRamo (--mapa-descramo). Principales:\n{t.head(15).to_string()}")
    nuevos_desc = sorted(set(df["_DESC"].unique()) - desc_prev)
    if nuevos_desc and not p["permitir_descramo_nuevo"]:
        raise ErrorBase1(f"{ctx}: los ramos {nuevos_desc} no existen en la Base_1 previa ({sorted(desc_prev)}). Un nombre distinto partiría la historia del ramo en dos. "
                         "Corrija el mapa (--mapa-descramo) o, si de verdad es un ramo nuevo, use --permitir-descramo-nuevo.")
    # columnas de la previa: directas, aprendidas o vacías
    directas = {"LLAVE": "_LLAVE", c["LLAVE"]: "_LLAVE", c["DESC"]: "_DESC", c["ANIO"]: "_ANIO", c["MES"]: "_MES"}
    equivalentes = {
        "ZTIPOREAS": ctr, "TIPOREA": ctr, "TIPOREAS": ctr, "CIATOM": cced, "ZCEDENTE": cced, "CEDENTE": cced,
        "CTOTOM": ccto, "ZCONTRATO": ccto, "CONTRATO": ccto, "FUNCAREA": cfunc, "LN": cfunc, "CEBE": cprof, "PROFTCTR": cprof,
        "ZSUSCYEAR": buscar(df, ["ZSUSCYEAR"]), "SUSC": buscar(df, ["ZSUSCYEAR"]), "ANOSUSC": buscar(df, ["ZSUSCYEAR"]),
        "ZCORREDOR": buscar(df, ["ZCORREDOR"]), "CORREDOR": buscar(df, ["ZCORREDOR"]), "ZREGIONRP": buscar(df, ["ZREGIONRP"]),
        "REGION": buscar(df, ["ZREGIONRP"]), "TERRSAP": buscar(df, ["ZREGIONRP"]),
    }
    llenado, salida = [], pd.DataFrame(index=df.index)
    func_prev = llave_canonica(prev[c["LLAVE"]]).str.split("-").str[-1]
    llave_prev = llave_canonica(prev[c["LLAVE"]])
    func_new = df[cfunc].astype(str).str.strip().str.upper()
    for pc in prev_cols:
        if pc in metricas:
            continue
        n = norm(pc)
        if pc in directas:
            salida[pc] = df[directas[pc]]; metodo = "DIRECTA"
        elif n in equivalentes and equivalentes[n] is not None:
            src = equivalentes[n]
            salida[pc] = df[src].map(tramo) if n not in ("FUNCAREA", "LN", "CEBE", "PROFTCTR", "ZREGIONRP", "REGION", "TERRSAP") else df[src].astype(str).str.strip()
            metodo = f"DIRECTA ({src})"
        elif n == "TERRITORIO" and buscar(df, ["ZREGIONRP"]) is not None and p["pais"] and os.path.isfile(p["pais"]):
            pa = leer(p["pais"]); ct, cv = buscar(pa, ["TerrSAP"]), buscar(pa, ["Territorio"])
            if ct is None or cv is None:
                salida[pc] = np.nan; metodo = "VACIA (Pais.csv sin TerrSAP/Territorio)"
            else:
                m = pa.dropna(subset=[ct]).drop_duplicates(ct).assign(**{ct: lambda d: d[ct].astype(str).str.strip()}).set_index(ct)[cv]
                salida[pc] = df[buscar(df, ["ZREGIONRP"])].astype(str).str.strip().map(m); metodo = "Pais.csv (ZREGIONRP -> TerrSAP -> Territorio)"
        else:
            salida[pc] = np.nan; metodo = "VACIA (no derivable del extracto sin inventar)"
            for nombre_k, k_prev, k_new in [("FUNCAREA", func_prev.values, func_new),
                                            ("DescRamo", prev[c["DESC"]].astype(str).str.strip().values, df["_DESC"]),
                                            ("LLAVE; LLAVEs nuevas quedan vacías", llave_prev.values, df["_LLAVE"])]:
                m = aprender_columna(prev, pc, k_prev)
                if m is not None:
                    salida[pc] = k_new.map(m); metodo = f"APRENDIDA de la previa (unívoca por {nombre_k})"
                    break
        llenado.append({"COLUMNA": pc, "METODO": metodo, "PCT_FILAS_CON_DATO": float(salida[pc].notna().mean()) if len(salida) else 0.0})
    # agregación al grano de la Base_1: dimensiones + periodo, métricas en columnas
    dims = [pc for pc in prev_cols if pc not in metricas]
    salida["_MET"] = df["_MET"]; salida["_VAL"] = df["_VAL"]
    llaves_grupo = dims + ["_MET"]
    tmp = salida.copy()
    for d in dims:
        tmp[d] = tmp[d].astype(object).where(tmp[d].notna(), "§NA§")
    g = tmp.groupby(llaves_grupo, dropna=False)["_VAL"].sum().unstack("_MET").reset_index()
    for d in dims:
        g[d] = g[d].where(g[d] != "§NA§", np.nan)
    for m in metricas:
        if m not in g.columns:
            g[m] = np.nan  # métrica no derivable del extracto (p.ej. retenidas): vacía, no cero
    g.columns.name = None
    g = g[prev_cols]
    g[c["ANIO"]] = pd.to_numeric(g[c["ANIO"]]).astype("Int64"); g[c["MES"]] = pd.to_numeric(g[c["MES"]]).astype("Int64")
    info = {"fuente_periodo": fuente_per, "gl_no_mapeadas": resumen_gl, "conflictos_descramo": pd.DataFrame(conflictos),
            "fuente_descramo": pd.DataFrame([{"CeBe": k, "DescRamo": mapa_desc[k], "FUENTE": fuente_desc.get(k, "")} for k in sorted(set(cebe))
                                            if k in mapa_desc]),
            "signos": {m: float(df.loc[df["_MET"] == m, "_SIG"].iloc[0]) for m in df["_MET"].unique()}}
    return g, llenado, info


# =============================================================================
# CONTROLES
# =============================================================================
def comparar_traslape(prev, nueva, c, metricas, per_tras):
    """Totales por métrica y DescRamo en los periodos de traslape: previa vs nueva."""
    codigos = {a * 100 + m for a, m in per_tras}
    def tot(df):
        d = df[(df[c["ANIO"]].astype(int) * 100 + df[c["MES"]].astype(int)).isin(codigos)]
        return d.groupby(d[c["DESC"]].astype(str).str.strip())[metricas].sum(min_count=1)
    a, b = tot(prev), tot(nueva)
    filas = []
    for m in metricas:
        for desc in sorted(set(a.index) | set(b.index)):
            va = a[m].get(desc, np.nan) if m in a else np.nan
            vb = b[m].get(desc, np.nan) if m in b else np.nan
            filas.append({"METRICA": m, "DescRamo": desc, "PREVIA": va, "NUEVA": vb})
    t = pd.DataFrame(filas)
    t["DIF"] = t["NUEVA"] - t["PREVIA"]
    t["DIF_PCT"] = np.where(t["PREVIA"].abs() > 0, t["DIF"] / t["PREVIA"].abs(), np.nan)
    return t


def evaluar_traslape(t, tol, mat):
    """Por métrica (total) y por ramo material: |dif| <= tol * |previa|. Devuelve (ok, fallas, ratio_total por métrica)."""
    fallas, ratios = [], {}
    for m, g in t.groupby("METRICA"):
        if g["NUEVA"].isna().all() or g["PREVIA"].abs().sum() == 0:
            continue  # métrica sin dato en la nueva (p.ej. retenidas) o sin monto previo: no evaluable
        sp, sn = g["PREVIA"].fillna(0).sum(), g["NUEVA"].fillna(0).sum()
        ratios[m] = sn / sp if sp else np.nan
        if abs(sn - sp) > tol * abs(sp):
            fallas.append(f"{m} total: previa {sp:,.2f} vs nueva {sn:,.2f} ({(sn - sp) / abs(sp):+.2%})")
        for _, r in g[g["PREVIA"].abs() >= mat].iterrows():
            if pd.isna(r["NUEVA"]) or abs(r["NUEVA"] - r["PREVIA"]) > tol * abs(r["PREVIA"]):
                fallas.append(f"{m} / {r['DescRamo']}: previa {r['PREVIA']:,.2f} vs nueva {r['NUEVA'] if pd.notna(r['NUEVA']) else 0:,.2f}")
    return (not fallas), fallas, ratios


def participacion_tev_hyor(base, c, cpma):
    d = base[[c["DESC"], c["ANIO"], cpma]].copy()
    t = d[c["DESC"]].map(norm_txt)
    d["RAMO"] = np.where(t.str.startswith("TERR") | (t == "TEV"), "Terremoto (73)", np.where(t.str.startswith(("HYO", "HIDRO")), "HyOR (71)", None))
    d = d[d["RAMO"].notna()]
    if d.empty:
        return pd.DataFrame()
    p = d.pivot_table(index=c["ANIO"], columns="RAMO", values=cpma, aggfunc="sum").fillna(0.0)
    tot = p.sum(axis=1)
    if "Terremoto (73)" in p:
        p["PCT_TERREMOTO"] = np.where(tot != 0, p["Terremoto (73)"] / tot, np.nan)
    return p.reset_index()


# =============================================================================
# PRINCIPAL
# =============================================================================
def main(p):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = setup_logger(p["out_dir"], ts)
    log.info("=== Actualización Base_1 | script v%s | pandas %s ===", VERSION, pd.__version__)
    log.info("Previa: %s | Nueva: %s | Salida: %s", p["previa"], p["nueva"], p["salida_csv"])
    if not os.path.isfile(p["previa"]):
        cands = [os.path.join(xFolder, "Inputs", n, "Base_1.xlsx") for n in ("Redistribucion", "Redistribución")] + [os.path.join(xFolder, "Inputs", "Base_1.xlsx")]
        alterno = next((x for x in cands if os.path.isfile(x)), cands[-1])
        if os.path.isfile(alterno) and os.path.abspath(alterno) != os.path.abspath(p["salida_xlsx"]):
            log.warning("No existe %s; se usa como Base_1 previa %s", p["previa"], alterno)
            p["previa"] = alterno
        else:
            raise ErrorBase1(f"No existe la Base_1 previa: {p['previa']} (tampoco {alterno}).")
    for k in ("salida_csv", "salida_xlsx"):
        if p[k] and os.path.abspath(p[k]) == os.path.abspath(p["previa"]):
            raise ErrorBase1("La salida no puede ser el mismo archivo que la Base_1 previa (la previa nunca se sobreescribe).")

    prev_raw = leer(p["previa"])
    prev_raw.columns = [str(x).strip() for x in prev_raw.columns]
    c, metricas, dims = esquema_previa(prev_raw)
    prev = preparar_previa(prev_raw, c, metricas)
    # Periodos posteriores a la fecha del archivo no pueden ser reales (p.ej. 2026 en una Base_1 guardada en dic-2025: presupuesto o proyección)
    mt = datetime.fromtimestamp(os.path.getmtime(p["previa"]))
    cod_mt = mt.year * 100 + mt.month
    cod_prev = prev[c["ANIO"]].astype(int) * 100 + prev[c["MES"]].astype(int)
    futuros = cod_prev > cod_mt
    excluida = pd.DataFrame()
    if futuros.any():
        excluida = prev[futuros].groupby([c["ANIO"], c["MES"]])[metricas].sum(min_count=1).reset_index()
        excluida.insert(2, "FILAS", prev[futuros].groupby([c["ANIO"], c["MES"]]).size().values)
        if p["conservar_posteriores"]:
            log.warning("La Base_1 previa (guardada el %s) trae %s filas de periodos posteriores (%s a %s); se CONSERVAN por --conservar-posteriores.",
                        mt.strftime("%d/%m/%Y"), int(futuros.sum()), cod_prev[futuros].min(), cod_prev[futuros].max())
            excluida = pd.DataFrame()
        else:
            log.warning("La Base_1 previa fue guardada el %s pero trae %s filas de periodos posteriores (%s a %s). Esos meses no pueden ser reales "
                        "(probablemente presupuesto o proyección) y se EXCLUYEN de la historia; detalle en la hoja Previa_Excluida. "
                        "El real de esos meses debe venir en la información nueva.", mt.strftime("%d/%m/%Y"), int(futuros.sum()),
                        cod_prev[futuros].min(), cod_prev[futuros].max())
            prev = prev[~futuros].reset_index(drop=True)
    prev_cols = list(prev.columns)
    cpma = next(m for m in metricas if norm(m) == "PMATOM")
    per_prev = set(zip(prev[c["ANIO"]].astype(int), prev[c["MES"]].astype(int)))
    log.info("Base_1 previa: %s filas | %s LLAVEs | periodos %s-%02d a %s-%02d | métricas %s",
             len(prev), prev[c["LLAVE"]].nunique(), *min(per_prev), *max(per_prev), metricas)

    # --- información nueva ---
    partes, llenados, infos, origen = [], [], [], []
    for f in archivos_nuevos(p["nueva"]):
        df = leer(f)
        df.columns = [str(x).strip() for x in df.columns]
        fmt = detectar_formato(df)
        nombre = os.path.basename(f)
        if fmt is None:
            raise ErrorBase1(f"{nombre}: no se reconoce el formato. Debe ser formato Base_1 (LLAVE, DescRamo, AñoCont, MesCont, PmaTom...) o extracto SAP "
                             f"(/ERP/GL_ACCT, /ERP/AMOUNT, /ERP/PROFTCTR, ...). Columnas: {list(df.columns)[:20]}")
        log.info("Archivo nuevo %s: formato %s, %s filas", nombre, fmt, len(df))
        if fmt == "BASE1":
            g, faltan, llen = nueva_formato_base1(df, prev_cols, metricas, c, log)
            info = {"signos": {}, "fuente_periodo": "AñoCont/MesCont"}
        else:
            g, llen, info = nueva_formato_sap(df, prev, prev_cols, metricas, c, p, log, nombre)
        if g[c["ANIO"]].isna().any() or g[c["MES"]].isna().any():
            raise ErrorBase1(f"{nombre}: hay filas sin AñoCont o MesCont.")
        per = set(zip(g[c["ANIO"]].astype(int), g[c["MES"]].astype(int)))
        for (o_nombre, o_per) in origen:
            dup = per & o_per
            if dup:
                raise ErrorBase1(f"Los archivos {o_nombre} y {nombre} traen los mismos periodos {sorted(dup)[:6]}: se duplicaría la información. Deje sólo uno por periodo.")
        origen.append((nombre, per))
        partes.append(g); llenados.append(pd.DataFrame(llen).assign(ARCHIVO=nombre)); infos.append((nombre, fmt, info))
    nueva = pd.concat(partes, ignore_index=True)
    per_new = set(zip(nueva[c["ANIO"]].astype(int), nueva[c["MES"]].astype(int)))
    per_tras = per_prev & per_new
    hay_sap = any(fmt == "SAP" for _, fmt, _ in infos)
    log.info("Información nueva: %s filas | periodos %s-%02d a %s-%02d (%s meses) | traslape con la previa: %s meses %s",
             len(nueva), *min(per_new), *max(per_new), len(per_new), len(per_tras), sorted(per_tras))

    # --- traslape: misma definición que la previa ---
    ajustes_signo = {}
    traslape_ok, fallas, tabla_tras = True, [], pd.DataFrame()
    if per_tras:
        tabla_tras = comparar_traslape(prev, nueva, c, metricas, per_tras)
        traslape_ok, fallas, ratios = evaluar_traslape(tabla_tras, p["tolerancia_traslape"], p["materialidad_traslape"])
        # signo invertido en un extracto SAP sin signo explícito del usuario: se corrige y se documenta
        if hay_sap:
            for m, r in ratios.items():
                if norm(m) in {norm(k) for k in p["signos"]}:
                    continue
                if pd.notna(r) and abs(r + 1) <= p["tolerancia_traslape"]:
                    nueva[m] = -nueva[m]; ajustes_signo[m] = "invertido: el traslape mostró la nueva = -1 x previa"
                    log.warning("Signo de %s invertido por evidencia del traslape (razón nueva/previa = %.4f)", m, r)
            if ajustes_signo:
                tabla_tras = comparar_traslape(prev, nueva, c, metricas, per_tras)
                traslape_ok, fallas, ratios = evaluar_traslape(tabla_tras, p["tolerancia_traslape"], p["materialidad_traslape"])
        log.info("Traslape (razón nueva/previa por métrica): %s", {k: round(v, 6) for k, v in ratios.items()})
        if not traslape_ok:
            log.error("El traslape NO cuadra (tolerancia %.2f%%):\n  %s", 100 * p["tolerancia_traslape"], "\n  ".join(fallas[:30]))
    else:
        msg = ("No hay meses de traslape entre la previa y la información nueva: no se puede comprobar con datos que la consulta nueva "
               "tenga la misma definición (cuentas, signo, LLAVE, ramo). Recomendación: extraiga también los últimos 2-3 meses que ya están en la Base_1 previa.")
        if hay_sap and not p["sin_traslape"]:
            traslape_ok = False; fallas = [msg + " Para continuar sin validar, use --sin-traslape \"justificación\"."]
            log.error(msg)
        else:
            log.warning(msg + (f" Continuar sin traslape: {p['sin_traslape']}" if p["sin_traslape"] else ""))

    # --- unión: los periodos nuevos reemplazan completos a los de la previa ---
    reemplazar = (prev[c["ANIO"]].astype(int) * 100 + prev[c["MES"]].astype(int)).isin({a * 100 + m for a, m in per_new})
    prev_keep, prev_out = prev[~reemplazar], prev[reemplazar]
    final = pd.concat([prev_keep, nueva[prev_cols]], ignore_index=True)
    final = final.sort_values([c["ANIO"], c["MES"]], kind="stable").reset_index(drop=True)

    # --- controles de cuadre ---
    cuadre = []
    for m in metricas:
        esperado = prev[m].sum() - prev_out[m].sum() + nueva[m].sum()
        cuadre.append({"METRICA": m, "PREVIA": prev[m].sum(), "PREVIA_REEMPLAZADA": prev_out[m].sum(), "NUEVA": nueva[m].sum(),
                       "FINAL": final[m].sum(), "DIF": final[m].sum() - esperado})
    cuadre = pd.DataFrame(cuadre)
    filas_ok = len(final) == len(prev_keep) + len(nueva)
    cuadre_ok = bool((cuadre["DIF"].abs() <= 1e-6 * max(1.0, cuadre["PREVIA"].abs().max())).all()) and filas_ok

    periodos = final.groupby([c["ANIO"], c["MES"]])[metricas].sum(min_count=1).reset_index()
    periodos["FUENTE"] = [("NUEVA (reemplaza a la previa)" if (a, m) in per_tras else "NUEVA") if (a, m) in per_new else "PREVIA"
                          for a, m in zip(periodos[c["ANIO"]].astype(int), periodos[c["MES"]].astype(int))]
    meses_anio = final.groupby(c["ANIO"])[c["MES"]].nunique().rename("MESES_DISTINTOS").reset_index()
    meses_anio["COMPLETO"] = meses_anio["MESES_DISTINTOS"] >= 12
    todos = sorted(per_prev | per_new)
    huecos = []
    a0, m0 = todos[0]
    a1, m1 = todos[-1]
    a, m = a0, m0
    while (a, m) <= (a1, m1):
        if (a, m) not in per_prev and (a, m) not in per_new:
            huecos.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    if huecos:
        log.warning("Meses sin información entre %s-%02d y %s-%02d: %s", a0, m0, a1, m1, huecos)
    lk_prev = set(llave_canonica(prev[c["LLAVE"]]))
    nueva_lk = nueva.assign(_LK=llave_canonica(nueva[c["LLAVE"]]))
    llaves_nuevas = (nueva_lk[~nueva_lk["_LK"].isin(lk_prev)].groupby(["_LK", c["DESC"]])[cpma].sum().reset_index()
                     .rename(columns={"_LK": "LLAVE"}).sort_values(cpma, key=abs, ascending=False))
    pct_llave_conocida = (1 - llaves_nuevas[cpma].abs().sum() / nueva[cpma].abs().sum()) if nueva[cpma].abs().sum() else np.nan
    log.info("LLAVEs de la información nueva que ya existen en la previa: %.1f%% de la |PmaTom| nueva (%s LLAVEs nuevas)",
             100 * pct_llave_conocida if pd.notna(pct_llave_conocida) else float("nan"), llaves_nuevas["LLAVE"].nunique())
    if pd.notna(pct_llave_conocida) and pct_llave_conocida < 0.5:
        log.warning("Menos de la mitad de la prima nueva cae en LLAVEs conocidas: revise que la LLAVE se construya igual que en la Base_1 previa.")
    part = participacion_tev_hyor(final, c, cpma)
    if not part.empty:
        log.info("Participación Terremoto vs HyOR en la base actualizada (PmaTom):\n%s", part.round(4).to_string(index=False))
    log.info("Cuadre: %s | filas %s = %s previa intacta + %s nueva", "OK" if cuadre_ok else "FALLA", len(final), len(prev_keep), len(nueva))

    # --- libro de control ---
    resumen = [
        ("version_script", VERSION), ("fecha", ts), ("previa", p["previa"]), ("archivos_nuevos", ", ".join(n for n, _ in origen)),
        ("previa_fecha_archivo", mt.strftime("%d/%m/%Y")), ("previa_filas_excluidas_posteriores", int(excluida["FILAS"].sum()) if not excluida.empty else 0),
        ("filas_previa", len(prev)), ("filas_previa_reemplazadas", len(prev_out)), ("filas_nuevas", len(nueva)), ("filas_final", len(final)),
        ("periodos_nuevos", f"{min(per_new)[0]}-{min(per_new)[1]:02d} a {max(per_new)[0]}-{max(per_new)[1]:02d} ({len(per_new)})"),
        ("meses_traslape", len(per_tras)), ("traslape", "OK" if traslape_ok else "NO CUADRA"),
        ("aceptar_traslape", p["aceptar_traslape"]), ("sin_traslape", p["sin_traslape"]),
        ("ajustes_de_signo", str(ajustes_signo) if ajustes_signo else ""),
        ("signos_aplicados", "; ".join(f"{n}: {i.get('signos')}" for n, f, i in infos if f == "SAP")),
        ("periodo_desde", "; ".join(f"{n}: {i.get('fuente_periodo')}" for n, _, i in infos)),
        ("cuadre", "OK" if cuadre_ok else "FALLA"), ("meses_sin_informacion", ", ".join(huecos)),
        ("pct_prima_nueva_en_llaves_conocidas", pct_llave_conocida),
    ]
    escribir = cuadre_ok and (traslape_ok or bool(p["aceptar_traslape"])) and not p["dry_run"]
    estado = "DRY-RUN (no se escribió la base)" if p["dry_run"] else ("ESCRITA" if escribir else "NO ESCRITA: " + ("cuadre" if not cuadre_ok else "traslape"))
    resumen.append(("resultado", estado))
    sufijo = "" if (cuadre_ok and (traslape_ok or p["aceptar_traslape"])) else "_CONTROL_FALLIDO"
    ctrl_path = os.path.join(p["out_dir"], f"Control_Actualizacion_Base1_{ts}{sufijo}.xlsx")
    with pd.ExcelWriter(ctrl_path, engine="openpyxl") as w:
        pd.DataFrame(resumen, columns=["CONCEPTO", "VALOR"]).to_excel(w, sheet_name="Resumen", index=False)
        pd.DataFrame({"FALLAS_TRASLAPE": fallas}).to_excel(w, sheet_name="Fallas", index=False)
        if not excluida.empty:
            excluida.to_excel(w, sheet_name="Previa_Excluida", index=False)
        cuadre.to_excel(w, sheet_name="Cuadre", index=False)
        (tabla_tras if not tabla_tras.empty else pd.DataFrame({"NOTA": ["Sin meses de traslape"]})).to_excel(w, sheet_name="Traslape", index=False)
        periodos.to_excel(w, sheet_name="Periodos", index=False)
        meses_anio.to_excel(w, sheet_name="Meses_por_Anio", index=False)
        (part if not part.empty else pd.DataFrame({"NOTA": ["Sin ramos Terremoto/HyOR reconocidos"]})).to_excel(w, sheet_name="Particip_TEV_HyOR", index=False)
        pd.concat(llenados, ignore_index=True).to_excel(w, sheet_name="Llenado_Columnas", index=False)
        llaves_nuevas.head(100000).to_excel(w, sheet_name="LLAVEs_Nuevas", index=False)
        for n, f, i in infos:
            if f != "SAP":
                continue
            corto = re.sub(r"[^A-Za-z0-9]", "", os.path.splitext(n)[0])[:12]
            i["gl_no_mapeadas"].to_excel(w, sheet_name=f"GL_NoMap_{corto}"[:31], index=False)
            i["fuente_descramo"].to_excel(w, sheet_name=f"DescRamo_{corto}"[:31], index=False)
            if not i["conflictos_descramo"].empty:
                i["conflictos_descramo"].to_excel(w, sheet_name=f"ConflictoRamo_{corto}"[:31], index=False)
    log.info("Libro de control: %s", ctrl_path)

    if not cuadre_ok:
        raise ErrorBase1("El cuadre de montos o de filas falló; no se escribió la base. Revise la hoja Cuadre.")
    if not traslape_ok and not p["aceptar_traslape"]:
        raise ErrorBase1("La información nueva no reproduce a la Base_1 previa en los meses de traslape (o no hay traslape); no se escribió la base. "
                         "Revise las hojas Fallas y Traslape. Si la diferencia está explicada, documente con --aceptar-traslape \"justificación\".")
    if p["dry_run"]:
        log.info("DRY-RUN: validaciones completas; no se escribió la base.")
        return final

    # --- escritura (la previa nunca se toca; un archivo de salida existente se respalda) ---
    def respaldar(path):
        if path and os.path.isfile(path):
            bdir = os.path.join(p["out_dir"], "Backups"); os.makedirs(bdir, exist_ok=True)
            base, ext = os.path.splitext(os.path.basename(path))
            shutil.copy2(path, os.path.join(bdir, f"{base}_{ts}{ext}"))
    os.makedirs(os.path.dirname(os.path.abspath(p["salida_csv"])) or ".", exist_ok=True)
    respaldar(p["salida_csv"])
    tmp = p["salida_csv"] + ".tmp"
    final.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, p["salida_csv"])
    log.info("Base_1 actualizada (csv): %s", p["salida_csv"])
    if p["escribir_xlsx"] and p["salida_xlsx"]:
        if len(final) > FILAS_MAX_EXCEL:
            log.warning("La base tiene %s filas: no cabe en Excel; sólo se escribió el csv.", len(final))
        else:
            respaldar(p["salida_xlsx"])
            tmpx = p["salida_xlsx"] + ".tmp.xlsx"
            final.to_excel(tmpx, index=False, engine="openpyxl")
            os.replace(tmpx, p["salida_xlsx"])
            log.info("Base_1 actualizada (xlsx): %s", p["salida_xlsx"])
    return final


def parse_args(argv=None):
    d = DEFAULTS
    ap = argparse.ArgumentParser(description="Actualiza la Base_1 (histórico real) con la información del año en curso.")
    ap.add_argument("--previa", default=d["previa"])
    ap.add_argument("--nueva", nargs="+", default=d["nueva"], help="archivo(s) o carpeta(s) con la información nueva")
    ap.add_argument("--subramo", default=d["subramo"])
    ap.add_argument("--pais", default=d["pais"])
    ap.add_argument("--mapa-descramo", default=d["mapa_descramo"])
    ap.add_argument("--mapa-gl", default=d["mapa_gl"])
    ap.add_argument("--salida-csv", default=d["salida_csv"])
    ap.add_argument("--salida-xlsx", default=d["salida_xlsx"])
    ap.add_argument("--out-dir", default=d["out_dir"])
    ap.add_argument("--filtro", action="append", default=list(d["filtros"]), help="COLUMNA=VALOR (repetible), p.ej. /ERP/CATEGORY=REAL01")
    ap.add_argument("--tolerancia-traslape", type=float, default=d["tolerancia_traslape"])
    ap.add_argument("--materialidad-traslape", type=float, default=d["materialidad_traslape"])
    ap.add_argument("--signo", action="append", default=[], help="METRICA=1|-1 (repetible), p.ej. PmaTom=-1")
    ap.add_argument("--aceptar-traslape", default=d["aceptar_traslape"], help="justificación documentada para escribir aunque el traslape no cuadre")
    ap.add_argument("--sin-traslape", default=d["sin_traslape"], help="justificación documentada para escribir sin meses de traslape")
    ap.add_argument("--permitir-descramo-nuevo", action="store_true", default=d["permitir_descramo_nuevo"])
    ap.add_argument("--especiales-a-diciembre", action="store_true", default=d["especiales_a_diciembre"])
    ap.add_argument("--sin-xlsx", action="store_true")
    ap.add_argument("--conservar-posteriores", action="store_true", help="no excluir periodos de la previa posteriores a la fecha del archivo")
    ap.add_argument("--dry-run", action="store_true", default=d["dry_run"])
    a = ap.parse_args(argv)
    p = dict(d)
    p.update({"previa": a.previa, "nueva": a.nueva, "subramo": a.subramo, "pais": a.pais, "mapa_descramo": a.mapa_descramo,
              "mapa_gl": a.mapa_gl, "salida_csv": a.salida_csv, "salida_xlsx": a.salida_xlsx, "out_dir": a.out_dir, "filtros": a.filtro,
              "tolerancia_traslape": a.tolerancia_traslape, "materialidad_traslape": a.materialidad_traslape,
              "aceptar_traslape": a.aceptar_traslape.strip(), "sin_traslape": a.sin_traslape.strip(),
              "permitir_descramo_nuevo": a.permitir_descramo_nuevo, "especiales_a_diciembre": a.especiales_a_diciembre,
              "escribir_xlsx": d["escribir_xlsx"] and not a.sin_xlsx, "dry_run": a.dry_run,
              "conservar_posteriores": a.conservar_posteriores})
    signos = dict(d["signos"])
    for s in a.signo:
        if "=" not in s:
            raise SystemExit(f"--signo inválido '{s}': use METRICA=1 o METRICA=-1")
        k, v = s.split("=", 1)
        if v.strip() not in ("1", "-1", "+1"):
            raise SystemExit(f"--signo inválido '{s}': el signo debe ser 1 o -1")
        signos[k.strip()] = float(v)
    p["signos"] = signos
    return p


if __name__ == "__main__":
    _p = parse_args()
    _ok = False
    try:
        main(_p)
        _ok = True
    except Exception as e:
        _log = logging.getLogger("base1")
        if _log.handlers:
            _log.exception("LA ACTUALIZACIÓN SE DETUVO: %s", e)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        try:
            os.makedirs(_p["out_dir"], exist_ok=True)
            with open(os.path.join(_p["out_dir"], f"ERROR_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"{type(e).__name__}: {e}\n")
        except Exception:
            pass
    finally:
        for h in list(logging.getLogger("base1").handlers):
            h.close()
    if os.name == "nt" and sys.stdout.isatty():
        try:
            input("Presione Enter para cerrar...")
        except Exception:
            pass
    sys.exit(0 if _ok else 1)
