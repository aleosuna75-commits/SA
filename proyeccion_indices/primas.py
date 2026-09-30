# -*- coding: utf-8 -*-
"""
PRIMAS MENSUALES POR GRUPO DE RAMO (real, reforecast y presupuesto) para el factor de prima de las reservas.

Lee de entradas/ (todas opcionales; si falta alguna, la proyeccion de reservas sigue con su modelo sin primas):
  * BD_Real*.xlsx          real historico mensual por contrato (hoja BD, desde 201901).
  * BDReal26*.xlsx         real del ano en curso mes a mes (hoja BD; la fila 1 trae formulas, encabezados en la 2).
                           Para los meses que trae, sustituye a BD_Real.
  * BD_RFCST_26*.xlsx      hoja BD_RFCST26: reforecast del ano en curso por contrato, sin mes ni ramo (se usa
                           Primas 1226 - Primas 0726 = estimado ago-dic por LN); hoja Ppto2026: presupuesto del ano en
                           curso mes a mes por contrato con ramo (da la forma mensual y por ramo del reforecast).
  * PptoTecnico2027*.csv   presupuesto del ano siguiente (SAP BW): un renglon por mes x concepto x contrato x ano de
                           suscripcion; el ramo sale del centro de beneficio. Si existe la version _Ced (con PRCT_CED)
                           se prefiere.

Todo en USD. El resultado es la prima tomada (bruta) mensual por GRUPO de ramo de reserva: el real agrupa AP, GMM y
Salud en 30 y Terremoto e Hidro en 70, asi que las reservas 30, 34 y 37 comparten el grupo 30 y las 71 y 73 el 70.
Cada archivo leido deja sus controles (renglones, filtros, meses, prima por LN, siniestros/prima, comisiones/prima).

Se puede correr solo para ver los controles:  python primas.py
"""
from __future__ import annotations

import importlib.util
import math
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CARPETA = Path(__file__).resolve().parent
ENTRADAS = CARPETA / "entradas"
CACHE = CARPETA / "salidas" / "cache_primas"     # tablas ya agregadas, por archivo (nombre, tamano y fecha)

PATRON_REAL_HIST = "BD_Real*.xlsx"
PATRON_REAL_ANIO = "BDReal26*.xlsx"
PATRON_RFCST = "BD_RFCST_26*.xlsx"
PATRON_PPTO = "PptoTecnico2027*.csv"
ANIO_PPTO = 2027                  # 0FISCYEAR del presupuesto (trae tambien 2026 en 202606 y 2028-2035)
CUENTAS_PRIMA = ("6104010000", "6108010000", "6111090000")   # prima tomada (viene en negativo: se voltea)
PREFIJO_SINIESTRO, PREFIJO_COMISION = "54", "53"
MIN_COBERTURA_HISTORIA = 0.95     # el historico debe traer al menos 95 % de la prima de los meses que comparte con
                                  # el real del ano; con menos (p. ej. un fragmento) el grupo no se usa

# ramo de la fuente de primas -> grupo de reserva (None = no hay reserva de ese ramo en las BD)
GRUPO_DE_RAMO_PRIMA = {
    "10": "10", "20": None, "30": "30", "31": "30", "35": "30", "39": "30", "40": "40", "50": "50", "60": "60",
    "70": "70", "71": "70", "73": "70", "80": "80", "90": "90", "100": "100", "110": "110",
    "130": "130", "140": "140", "150": "150", "160": "160", "170": "170",
}
# ramo de las BD de reservas -> grupo de prima
GRUPO_DE_RAMO_RESERVA = {
    "10": "10", "30": "30", "34": "30", "37": "30", "40": "40", "50": "50", "60": "60", "71": "70", "73": "70",
    "80": "80", "90": "90", "100": "100", "110": "110",
    "130": "130", "140": "140", "150": "150", "160": "160", "170": "170",
}


def ramo_de_centro(centro) -> str | None:
    """Centro de beneficio del presupuesto (/ERP/PROFTCTR, p. ej. A060000000) -> ramo (catalogo del area)."""
    m = re.match(r"^A(\d{3})\d{6}$", str(centro or "").strip().upper())
    if not m:
        return None
    t = m.group(1)
    if t in ("011", "012", "013", "600"):
        return "10"
    if t in ("021", "022", "023", "024", "025"):
        return "20"
    reglas = {"331": "31", "332": "35", "333": "39", "060": "60", "071": "71", "073": "73", "075": "73",
              "100": "100"}
    if t in reglas:
        return reglas[t]
    if t in ("041", "042", "043", "044"):
        return "40"
    if t in ("051", "052"):
        return "50"
    if t in ("081", "082", "083"):
        return "80"
    if t in ("091", "092", "093", "094", "095"):
        return "90"
    if t in ("111", "112"):
        return "110"
    if t[:2] in ("13", "14", "15", "16", "17"):      # fianzas: A13x -> 130, A14x -> 140, ..., A17x -> 170
        return t[:2] + "0"
    return None


# =============================================================================
# UTILERIAS
# =============================================================================
def _norm(t) -> str:
    t = str(t or "").replace("\xa0", " ").strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t)


def _col(df: pd.DataFrame, *nombres, obligatoria: bool = True):
    """Nombre real de la primera columna de df que coincide (sin acentos ni espacios extra) con alguno de nombres."""
    mapa = {}
    for c in df.columns:
        mapa.setdefault(_norm(c), c)
    for n in nombres:
        if _norm(n) in mapa:
            return mapa[_norm(n)]
    if obligatoria:
        raise ValueError(f"no se encontro la columna {nombres[0]!r}")
    return None


def _num(s: pd.Series) -> pd.Series:
    """Importes que pueden venir como texto con comas de miles y comillas ("-7,000.00")."""
    if s.dtype == object or str(s.dtype).startswith("str"):
        s = s.astype(str).str.replace(",", "", regex=False).str.replace('"', "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _ln(v) -> str:
    """4001 / 'LN04001' / '4008-Agro' -> 'LN04001' / 'LN04008-Agro'."""
    t = str(v).strip()
    if t.endswith(".0"):
        t = t[:-2]
    if t.upper().startswith("LN"):
        return "LN" + t[2:]
    return "LN0" + t if t[:2] == "40" else t


def _motor_excel() -> str:
    """calamine (mucho mas rapido) si esta instalado; si no, openpyxl."""
    return "calamine" if importlib.util.find_spec("python_calamine") else "openpyxl"


def _leer_hoja(ruta: Path, hoja: str, marcas: tuple) -> pd.DataFrame:
    """Lee una hoja buscando la fila de encabezados (la primera de las 10 primeras que trae todas las marcas)."""
    motor = _motor_excel()
    muestra = pd.read_excel(ruta, sheet_name=hoja, header=None, nrows=10, engine=motor)
    fila = next((i for i in range(len(muestra))
                 if all(any(_norm(m) == _norm(v) for v in muestra.iloc[i].tolist()) for m in marcas)), None)
    if fila is None:
        raise ValueError(f"{ruta.name} / {hoja}: no se encontraron los encabezados {marcas}")
    return pd.read_excel(ruta, sheet_name=hoja, header=fila, engine=motor)


def _buscar(patron: str) -> Path | None:
    """Archivo de entradas/ que cumple el patron; si hay varios, el mas reciente (y para el presupuesto, el _Ced)."""
    c = sorted(ENTRADAS.glob(patron), key=lambda p: (("_ced" in p.name.lower()), p.stat().st_mtime), reverse=True)
    c = [p for p in c if not p.name.startswith("~$")]
    return c[0] if c else None


def _con_cache(ruta: Path, clave: str, funcion):
    """Resultado de funcion(ruta) guardado en salidas/cache_primas; se recalcula si cambia el archivo."""
    st = ruta.stat()
    archivo = CACHE / f"{clave}_{re.sub(r'[^A-Za-z0-9]+', '_', ruta.stem)}_{st.st_size}_{int(st.st_mtime)}.pkl"
    if archivo.exists():
        try:
            with open(archivo, "rb") as f:
                return pickle.load(f)
        except Exception:  # noqa: BLE001  (cache danado: se recalcula)
            pass
    res = funcion(ruta)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        for viejo in CACHE.glob(f"{clave}_{re.sub(r'[^A-Za-z0-9]+', '_', ruta.stem)}_*.pkl"):
            viejo.unlink(missing_ok=True)
        with open(archivo, "wb") as f:
            pickle.dump(res, f)
    except OSError:
        pass
    return res


@dataclass
class Control:
    archivo: str
    renglones_leidos: int = 0
    renglones_usados: int = 0
    filtros: str = ""
    meses: str = ""
    prima: float = 0.0
    siniestros: float = 0.0
    comisiones: float = 0.0
    prima_por_ln: dict = field(default_factory=dict)
    notas: list = field(default_factory=list)

    def fila(self) -> dict:
        return {"Archivo": self.archivo, "Renglones leidos": self.renglones_leidos,
                "Renglones usados": self.renglones_usados, "Filtros": self.filtros, "Meses": self.meses,
                "Prima (M USD)": round(self.prima / 1e6, 2),
                "Siniestros / prima": round(self.siniestros / self.prima, 4) if self.prima else None,
                "Comisiones / prima": round(self.comisiones / self.prima, 4) if self.prima else None,
                "Prima por LN (M USD)": "; ".join(f"{k} {v / 1e6:,.1f}" for k, v in sorted(self.prima_por_ln.items())),
                "Notas": " | ".join(self.notas)}


def _rango_meses(periodos) -> str:
    p = sorted(set(int(x) for x in periodos))
    return f"{p[0]} a {p[-1]} ({len(p)} meses)" if p else "sin meses"


# =============================================================================
# LECTORES (cada uno regresa una tabla agregada y su control)
# =============================================================================
def _agregar_real(ruta: Path):
    df = _leer_hoja(ruta, "BD", ("Periodo", "Primas USD"))
    ctl = Control(ruta.name, renglones_leidos=len(df))
    c_per, c_ramo = _col(df, "Periodo"), _col(df, "Ramo2", "Ramo")
    c_ln = _col(df, "LN2", "LN")
    per = pd.to_numeric(df[c_per], errors="coerce")
    ok = per.between(190001, 299912)
    df = df[ok]
    t = pd.DataFrame({
        "periodo": per[ok].astype(int),
        "ramo": pd.to_numeric(df[c_ramo], errors="coerce").fillna(-1).astype(int).astype(str),
        "ln": df[c_ln].map(_ln),
        "prima": _num(df[_col(df, "Primas USD")]),
        "siniestros": _num(df[_col(df, "Siniestros USD")]),
        "comisiones": _num(df[_col(df, "Comisiones USD")]),
    })
    ctl.renglones_usados = len(t)
    ctl.filtros = f"Periodo valido; importes en USD (Primas/Siniestros/Comisiones USD); LN = {c_ln}"
    ctl.meses = _rango_meses(t["periodo"])
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("prima", "siniestros", "comisiones"))
    ctl.prima_por_ln = t.groupby("ln")["prima"].sum().to_dict()
    sin_grupo = t[~t["ramo"].isin([k for k, v in GRUPO_DE_RAMO_PRIMA.items() if v])]
    if len(sin_grupo):
        ctl.notas.append(f"ramos sin reserva o sin catalogo: {sorted(sin_grupo['ramo'].unique())} "
                         f"({sin_grupo['prima'].sum() / 1e6:,.1f} M, no se usan)")
    agg = t.groupby(["periodo", "ramo", "ln"], as_index=False)[["prima", "siniestros", "comisiones"]].sum()
    return agg, ctl


def _agregar_ppto_anio(ruta: Path):
    """Hoja Ppto2026: presupuesto del ano en curso mes a mes por LN y ramo."""
    df = _leer_hoja(ruta, "Ppto2026", ("AñoPpto", "MesPpto"))
    ctl = Control(f"{ruta.name} / Ppto2026", renglones_leidos=len(df))
    anio = pd.to_numeric(df[_col(df, "AñoPpto")], errors="coerce")
    mes = pd.to_numeric(df[_col(df, "MesPpto")], errors="coerce")
    ok = anio.notna() & mes.between(1, 12)
    df = df[ok]
    t = pd.DataFrame({
        "anio": anio[ok].astype(int), "mes": mes[ok].astype(int),
        "ramo": pd.to_numeric(df[_col(df, "Ramo")], errors="coerce").fillna(-1).astype(int).astype(str),
        "ln": df[_col(df, "LN2", "LíneaNegocio")].map(_ln),
        "prima": _num(df[_col(df, "PmasEmi")]),
        "siniestros": _num(df[_col(df, "SinOcurr")]),
        "comisiones": _num(df[_col(df, "CostosAdq")]),
    })
    ctl.renglones_usados = len(t)
    ctl.filtros = "renglones con AñoPpto y MesPpto 1-12; LN2; PmasEmi, SinOcurr, CostosAdq"
    ctl.meses = ", ".join(f"{a}: {len(set(g['mes']))} meses" for a, g in t.groupby("anio"))
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("prima", "siniestros", "comisiones"))
    ctl.prima_por_ln = t.groupby("ln")["prima"].sum().to_dict()
    agg = t.groupby(["anio", "mes", "ramo", "ln"], as_index=False)[["prima", "siniestros", "comisiones"]].sum()
    return agg, ctl


def _agregar_rfcst(ruta: Path):
    """Hoja BD_RFCST26: por LN, real ene-jul (0726) y reforecast del ano (1226); sin mes ni ramo."""
    df = _leer_hoja(ruta, "BD_RFCST26", ("Primas 0726", "Primas 1226"))
    ctl = Control(f"{ruta.name} / BD_RFCST26", renglones_leidos=len(df))
    c_ln = _col(df, "LN")
    df = df[df[c_ln].notna() & (df[c_ln].astype(str).str.strip() != "")]
    ln = df[c_ln].map(_ln)
    t = pd.DataFrame({"ln": ln})
    for base in ("0726", "1226", "PPTO1226", "1225"):
        for conc in ("Primas", "Siniestros", "Costos"):
            c = _col(df, f"{conc} {base}", obligatoria=False)
            t[f"{conc.lower()}_{base}"] = _num(df[c]) if c is not None else 0.0
    agro = t["ln"].str.contains("Agro", case=False)
    for c in [c for c in t.columns if c.startswith(("siniestros_", "costos_"))]:
        t.loc[agro, c] = -t.loc[agro, c]            # en 4008-Agro vienen con el signo invertido
    ctl.renglones_usados = len(t)
    ctl.filtros = "renglones con LN; 4008-Agro: siniestros y costos con el signo volteado"
    ctl.meses = "sin mes: 0726 = real ene-jul, 1226 = reforecast del ano"
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("primas_1226", "siniestros_1226",
                                                                              "costos_1226"))
    ctl.prima_por_ln = t.groupby("ln")["primas_1226"].sum().to_dict()
    ctl.notas.append("prima = reforecast 1226 (ano completo)")
    agg = t.groupby("ln", as_index=False).sum(numeric_only=True)
    return agg, ctl


def _columna_por_contenido(df: pd.DataFrame, nombre: str, prueba, avisos: list) -> str:
    """Encabezados corridos en algunos exports: si la columna que dice ser 'nombre' no pasa la prueba de contenido,
    se busca la que si la pasa."""
    def pasa(c):
        s = df[c].dropna().astype(str).str.strip()
        s = s[s != ""]
        return len(s) > 0 and prueba(s).mean() > 0.95
    c = _col(df, nombre, obligatoria=False)
    if c is not None and pasa(c):
        return c
    for otra in df.columns:
        if otra != c and pasa(otra):
            avisos.append(f"la columna {nombre} esta en '{otra}' (encabezados corridos)")
            return otra
    raise ValueError(f"no se encontro una columna con el contenido de {nombre}")


def _agregar_ppto_sig(ruta: Path):
    """Presupuesto del ano siguiente (CSV de SAP BW), leido por bloques."""
    avisos = []
    muestra = pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, nrows=20000)
    es_num = lambda s: pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce").notna()  # noqa: E731
    cols = {
        "gl": _columna_por_contenido(muestra, "/ERP/GL_ACCT", lambda s: s.str.match(r"^[56]\d{9}$"), avisos),
        "ln": _columna_por_contenido(muestra, "/ERP/FUNCAREA", lambda s: s.str.startswith("LN040"), avisos),
        "cc": _columna_por_contenido(muestra, "/ERP/PROFTCTR", lambda s: s.str.match(r"^A\d{9}$"), avisos),
        "anio": _columna_por_contenido(muestra, "0FISCYEAR", lambda s: s.str.match(r"^20\d{2}$"), avisos),
        "mes": _columna_por_contenido(muestra, "0CALMONTH2", lambda s: s.str.match(r"^(0?[1-9]|1[0-2])$"), avisos),
        "imp": _col(muestra, "/ERP/AMOUNT"),
    }
    if not es_num(muestra[cols["imp"]].dropna().astype(str)).mean() > 0.95:
        raise ValueError("la columna /ERP/AMOUNT no trae importes")
    for extra, nombre in (("ced", "PRCT_CED"), ("cohorte", "ZSUSCYEAR"), ("region", "ZREGIONRP"),
                          ("tipo", "ZTIPOREAS")):
        c = _col(muestra, nombre, obligatoria=False)
        if c is not None:
            cols[extra] = c
    leidos, bloques = 0, []
    for ch in pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, usecols=list(set(cols.values())), chunksize=500_000):
        leidos += len(ch)
        t = pd.DataFrame({k: ch[v] for k, v in cols.items()})
        t["imp"] = _num(t["imp"])
        t["gl"] = t["gl"].astype(str).str.strip()
        t["anio"] = pd.to_numeric(t["anio"], errors="coerce")
        t["mes"] = pd.to_numeric(t["mes"], errors="coerce")
        if "ced" in t:
            ced = pd.to_numeric(t["ced"], errors="coerce").fillna(0.0)
            t["ced"] = np.where(ced > 1, ced / 100, ced)
        else:
            t["ced"] = 0.0
        bloques.append(t)
    t = pd.concat(bloques, ignore_index=True) if bloques else pd.DataFrame()
    ctl = Control(ruta.name, renglones_leidos=leidos)
    anios = t["anio"].value_counts().sort_index()
    t = t[t["anio"] == ANIO_PPTO]
    es_prima = t["gl"].isin(CUENTAS_PRIMA)
    otras_61 = t[t["gl"].str.startswith("61") & ~es_prima]
    t["prima"] = np.where(es_prima, -t["imp"], 0.0)
    t["siniestros"] = np.where(t["gl"].str.startswith(PREFIJO_SINIESTRO), t["imp"], 0.0)
    t["comisiones"] = np.where(t["gl"].str.startswith(PREFIJO_COMISION), t["imp"], 0.0)
    t["retenida"] = t["prima"] * (1 - t["ced"])
    t["ln"] = t["ln"].map(_ln)
    t["ramo"] = t["cc"].map(ramo_de_centro)
    ctl.renglones_usados = len(t)
    ctl.filtros = (f"0FISCYEAR = {ANIO_PPTO} (se descartan {', '.join(f'{int(a)}: {n:,}' for a, n in anios.items() if a != ANIO_PPTO)}); "
                   f"prima = cuentas {', '.join(CUENTAS_PRIMA)} con el signo volteado; siniestros {PREFIJO_SINIESTRO}*, "
                   f"comisiones {PREFIJO_COMISION}*")
    ctl.meses = _rango_meses(ANIO_PPTO * 100 + t["mes"].dropna().astype(int))
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("prima", "siniestros", "comisiones"))
    ctl.prima_por_ln = t.groupby("ln")["prima"].sum().to_dict()
    ctl.notas += avisos
    if len(otras_61):
        ctl.notas.append(f"otras cuentas 61 no sumadas como prima: {sorted(otras_61['gl'].unique())[:5]}")
    sin_ramo = t[t["ramo"].isna() & (t["prima"] != 0)]
    if len(sin_ramo):
        ctl.notas.append(f"centros sin ramo en el catalogo: {sorted(sin_ramo['cc'].astype(str).unique())[:8]} "
                         f"({sin_ramo['prima'].sum() / 1e6:,.1f} M de prima)")
    if "ced" not in cols:
        ctl.notas.append("sin PRCT_CED: prima retenida = tomada")
    t["ramo"] = t["ramo"].fillna("sin ramo")
    agg = t.groupby(["mes", "ramo", "ln"], as_index=False)[["prima", "retenida", "siniestros", "comisiones"]].sum()
    return agg, ctl


# =============================================================================
# SERIE MENSUAL POR GRUPO
# =============================================================================
@dataclass
class Primas:
    mensual: pd.DataFrame            # periodo x grupo: prima tomada USD
    fuente: dict                     # periodo -> "real" / "reforecast" / "presupuesto"
    retenida: pd.DataFrame | None    # periodo x grupo del presupuesto del ano siguiente (tomada x (1 - cesion))
    controles: list                  # filas de control por archivo
    cobertura: dict                  # grupo -> cobertura del historico (0-1) o None si no se pudo medir
    avisos: list                     # avisos para consola y Alertas
    ultimo_real: int | None          # ultimo mes con prima real

    def grupos_utiles(self) -> list:
        return [g for g, c in self.cobertura.items() if c is not None and c >= MIN_COBERTURA_HISTORIA]


def _a_grupo(tabla: pd.DataFrame) -> pd.DataFrame:
    t = tabla.copy()
    t["grupo"] = t["ramo"].astype(str).map(GRUPO_DE_RAMO_PRIMA)
    return t[t["grupo"].notna()]


def leer_primas(verbose: bool = True) -> Primas | None:
    """Arma la prima mensual por grupo con lo que haya en entradas/. None si no hay real (no hay con que estimar)."""
    rutas = {k: _buscar(p) for k, p in (("hist", PATRON_REAL_HIST), ("anio", PATRON_REAL_ANIO),
                                         ("rfcst", PATRON_RFCST), ("ppto", PATRON_PPTO))}
    if rutas["hist"] is None and rutas["anio"] is None:
        return None
    controles, avisos = [], []

    def log(msg):
        if verbose:
            print(f"   {msg}", flush=True)

    reales = {}
    for k in ("hist", "anio"):
        if rutas[k] is not None:
            log(f"Primas: leyendo {rutas[k].name} ...")
            reales[k], ctl = _con_cache(rutas[k], "real", _agregar_real)
            controles.append(ctl.fila())
    hist, anio = reales.get("hist"), reales.get("anio")
    meses_anio = set(anio["periodo"]) if anio is not None else set()
    partes = []
    if hist is not None:
        partes.append(hist[~hist["periodo"].isin(meses_anio)])
    if anio is not None:
        partes.append(anio)
    real = _a_grupo(pd.concat(partes, ignore_index=True))
    ultimo_real = int(real["periodo"].max())

    # cobertura del historico: en los meses que comparte con el real del ano debe traer (casi) la misma prima
    cobertura = {}
    grupos = sorted(set(GRUPO_DE_RAMO_RESERVA.values()), key=int)
    if hist is not None and anio is not None and meses_anio & set(hist["periodo"]):
        h = _a_grupo(hist[hist["periodo"].isin(meses_anio)]).groupby("grupo")["prima"].sum()
        a = _a_grupo(anio[anio["periodo"].isin(set(hist["periodo"]))]).groupby("grupo")["prima"].sum()
        for g in grupos:
            base = float(a.get(g, 0.0))
            cobertura[g] = float(h.get(g, 0.0)) / base if base > 0 else None
    elif hist is not None:
        avisos.append(f"Primas: sin {PATRON_REAL_ANIO} no se puede medir la cobertura de {rutas['hist'].name}; "
                      "se toma como completa")
        cobertura = {g: 1.0 for g in grupos}
    else:
        avisos.append(f"Primas: sin {PATRON_REAL_HIST} solo hay {len(meses_anio)} meses de prima real: no alcanza "
                      "para estimar la relacion reserva / prima")
        cobertura = {g: None for g in grupos}
    incompletos = [f"{g} ({c:.0%})" for g, c in cobertura.items() if c is not None and c < MIN_COBERTURA_HISTORIA]
    if incompletos:
        avisos.append(f"Primas: el historico ({rutas['hist'].name}) trae menos de {MIN_COBERTURA_HISTORIA:.0%} de la "
                      f"prima del real del ano en los grupos {', '.join(incompletos)} (fragmento o base incompleta): "
                      "esos grupos se proyectan sin factor de prima")

    mensual = real.pivot_table(index="periodo", columns="grupo", values="prima", aggfunc="sum").fillna(0.0)
    fuente = {int(p): "real" for p in mensual.index}

    # reforecast del ano en curso: meses posteriores al ultimo real, repartidos con la forma del presupuesto del ano
    ppto_anio, rfcst = None, None
    if rutas["rfcst"] is not None:
        log(f"Primas: leyendo {rutas['rfcst'].name} (reforecast y presupuesto del ano) ...")
        try:
            rfcst, ctl = _con_cache(rutas["rfcst"], "rfcst", _agregar_rfcst)
            controles.append(ctl.fila())
            ppto_anio, ctl = _con_cache(rutas["rfcst"], "pptoanio", _agregar_ppto_anio)
            controles.append(ctl.fila())
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Primas: no se pudo leer {rutas['rfcst'].name} ({e}); el resto del ano va sin reforecast")
    anio_curso, mes_ult = divmod(ultimo_real, 100)
    meses_rest = list(range(mes_ult + 1, 13))
    if meses_rest and rfcst is not None and ppto_anio is not None:
        filas, notas = [], []
        ppto_rest = _a_grupo(ppto_anio[(ppto_anio["anio"] == anio_curso) & ppto_anio["mes"].isin(meses_rest)])
        real_anio = real[real["periodo"] // 100 == anio_curso]
        estimado = {r.ln: r.primas_1226 - r.primas_0726 for r in rfcst.itertuples()}
        # LN con prima real en el ano que el reforecast no trae: se usa su presupuesto del resto del ano
        for ln in sorted(set(real_anio["ln"]) - set(estimado)):
            p = float(ppto_rest[ppto_rest["ln"] == ln]["prima"].sum())
            if p > 0:
                estimado[ln] = p
                notas.append(f"{ln} no viene en el reforecast: se usa su presupuesto {anio_curso} del resto del ano "
                             f"({p / 1e6:,.1f} M)")
        for ln, total in estimado.items():
            if abs(total) < 1:
                continue
            forma = ppto_rest[ppto_rest["ln"] == ln].groupby(["grupo", "mes"])["prima"].sum().clip(lower=0)
            if forma.sum() <= 0:            # sin presupuesto del resto del ano: mezcla de ramos del real, meses parejos
                mezcla = real_anio[real_anio["ln"] == ln].groupby("grupo")["prima"].sum().clip(lower=0)
                if mezcla.sum() <= 0:
                    notas.append(f"{ln}: reforecast de {total / 1e6:,.1f} M sin ramo conocido (no se reparte)")
                    continue
                forma = pd.Series({(g, m): v for g, v in mezcla.items() for m in meses_rest})
                notas.append(f"{ln}: sin presupuesto del resto del ano; se reparte con la mezcla de ramos del real "
                             "y meses parejos")
            for (g, m), w in (forma / forma.sum()).items():
                filas.append((anio_curso * 100 + int(m), g, total * w))
        if filas:
            t = pd.DataFrame(filas, columns=["periodo", "grupo", "prima"]).pivot_table(
                index="periodo", columns="grupo", values="prima", aggfunc="sum")
            mensual = pd.concat([mensual, t]).fillna(0.0)
            fuente.update({int(p): "reforecast" for p in t.index})
        avisos += [f"Primas (reforecast): {n}" for n in notas]
    elif meses_rest:
        avisos.append(f"Primas: sin {PATRON_RFCST} no hay estimado de {anio_curso}{meses_rest[0]:02d} a "
                      f"{anio_curso}12")

    # presupuesto del ano siguiente, mes a mes
    retenida = None
    if rutas["ppto"] is not None:
        log(f"Primas: leyendo {rutas['ppto'].name} (presupuesto {ANIO_PPTO}; la primera vez tarda) ...")
        try:
            ppto, ctl = _con_cache(rutas["ppto"], "ppto", _agregar_ppto_sig)
            controles.append(ctl.fila())
            p = _a_grupo(ppto[ppto["ramo"] != "sin ramo"])
            p["periodo"] = ANIO_PPTO * 100 + p["mes"].astype(int)
            t = p.pivot_table(index="periodo", columns="grupo", values="prima", aggfunc="sum")
            mensual = pd.concat([mensual, t]).fillna(0.0)
            fuente.update({int(x): "presupuesto" for x in t.index})
            retenida = p.pivot_table(index="periodo", columns="grupo", values="retenida", aggfunc="sum").fillna(0.0)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Primas: no se pudo leer {rutas['ppto'].name} ({e})")
    mensual = mensual.groupby(level=0).sum().sort_index()
    mensual.index = mensual.index.astype(int)
    for g in grupos:
        if g not in mensual.columns:
            mensual[g] = 0.0
    return Primas(mensual=mensual[grupos], fuente=fuente, retenida=retenida, controles=controles,
                  cobertura=cobertura, avisos=avisos, ultimo_real=ultimo_real)


def rodante(serie: pd.Series, meses: int = 12) -> pd.Series:
    """Suma movil de 'meses' meses (flujo -> acumulado de los ultimos 12 meses); NaN si falta algun mes."""
    idx = pd.PeriodIndex([pd.Period(year=p // 100, month=p % 100, freq="M") for p in serie.index])
    s = pd.Series(serie.to_numpy(dtype=float), index=idx).asfreq("M")
    r = s.rolling(meses, min_periods=meses).sum()
    return pd.Series(r.to_numpy(), index=[p.year * 100 + p.month for p in r.index])


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pr = leer_primas()
    if pr is None:
        print("No hay archivos de prima real en entradas/.")
    else:
        print("\nCONTROLES")
        for c in pr.controles:
            print(" ", {k: v for k, v in c.items() if v not in ("", None)})
        print("\nCobertura del historico por grupo:", {g: (None if c is None else round(c, 3)) for g, c in pr.cobertura.items()})
        for a in pr.avisos:
            print("AVISO", a)
        print("\nPrima mensual por grupo (M USD), ultimos 24 meses con fuente:")
        m = (pr.mensual / 1e6).round(2)
        m["fuente"] = [pr.fuente.get(int(p)) for p in m.index]
        print(m.tail(24).to_string())
