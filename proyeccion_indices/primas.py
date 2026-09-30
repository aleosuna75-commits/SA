# -*- coding: utf-8 -*-
"""
PRIMAS MENSUALES POR GRUPO DE RAMO (real, reforecast y presupuesto) para el factor de prima de las reservas.

Lee de entradas/ (todas opcionales; si falta alguna, la proyeccion de reservas sigue con la recta):
  * BD_Real*.xlsx          real historico mensual por contrato (hoja BD, desde 201901).
  * BDReal26*.xlsx         real del ano en curso mes a mes (hoja BD; la fila 1 trae formulas, encabezados en la 2).
                           Para los meses que trae, sustituye a BD_Real.
  * BD_RFCST_26*.xlsx      hoja BD_RFCST26: reforecast del ano en curso por contrato, sin mes ni ramo (resto del ano
                           = Primas 1226 - Primas <corte>); hoja Ppto2026: presupuesto del ano en curso mes a mes con
                           ramo.
  * PptoTecnico2027*.csv   presupuesto del ano siguiente (SAP BW): un renglon por mes x concepto x contrato x ano de
                           suscripcion; el ramo sale del centro de beneficio.

Bases completas, nunca recortes: si hay varios archivos con el mismo patron (p. ej. un fragmento junto a la base
completa) se usa el MAS GRANDE y los demas se reportan como ignorados. Un archivo que parece recortado (renglones en un
limite tipico de extracto, LIMITES_TRUNCADO; un CSV del ano siguiente con menos de MIN_COBERTURA_PPTO de la prima de
referencia; o un historico que no cubre el real del ano o el real al corte del reforecast) NO se usa y NADA se completa
sobre el: la tabla "Archivos de primas" dice cual se uso y por que.

Todo en USD. El resultado es la prima tomada (bruta) mensual por GRUPO de ramo de reserva: el real agrupa AP, GMM y
Salud en 30 y Terremoto e Hidro en 70, asi que las reservas 30, 34 y 37 comparten el grupo 30 y las 71 y 73 el 70.

Resto del ano en curso (despues del ultimo mes real): el reforecast de cada contrato se reparte a grupos de ramo con
la mezcla del real del ano de la llave mas fina que exista (contrato, cedente, LN y tipo, LN) y a meses con el perfil
mensual que mejor explica el real del ano (parejo, forma del presupuesto, forma historica o mezcla). Las LN con prima
real que no vienen en el reforecast siguen al ritmo del ano.
Ano siguiente: presupuesto mes a mes; las LN que faltan en el CSV (menos de LN_INCOMPLETA de su referencia) se
completan con la cifra del dashboard del presupuesto (COMPLETAR_LN_PPTO). Todo queda en los controles y avisos.

Se puede correr solo para ver los controles:  python primas.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
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
CACHE_VERSION = 3

# =============================================================================
# CONFIGURACION
# =============================================================================
# Los nombres de archivo y de hoja llevan el ano. Se arman solos con el ano del ultimo mes real de reservas
# ({aa} = 26, {aaaa} = 2026, {sig} = 2027): BDReal26, BD_RFCST_26 con sus hojas BD_RFCST26 y Ppto2026, PptoTecnico2027.
# Si el area cambia la forma de nombrarlos, ajustalos aqui.
PATRON_REAL_HIST = "BD_Real*.xlsx"
PATRON_REAL_ANIO = "BDReal{aa}*.xlsx"
PATRON_RFCST = "BD_RFCST_{aa}*.xlsx"
HOJA_RFCST = "BD_RFCST{aa}"
HOJA_PPTO_ANIO = "Ppto{aaaa}"
PATRON_PPTO = "PptoTecnico{sig}*.csv"
CUENTAS_PRIMA = ("6104010000", "6108010000", "6111090000")   # prima tomada (viene en negativo: se voltea)
PREFIJO_SINIESTRO, PREFIJO_COMISION = "54", "53"
MIN_COBERTURA_HISTORIA = 0.95     # el historico debe traer al menos 95 % de la prima de los meses que comparte con
                                  # el real del ano; con menos (p. ej. un fragmento) el grupo no se usa
TOLERANCIA_TRASLAPE = 0.02        # aviso si historico y real del ano difieren mas de 2 % en un grupo y mes
TOLERANCIA_REAL_RFCST = 0.03      # aviso si la prima real acumulada del reforecast difiere del real mas de 3 %
UMBRAL_LN_MATERIAL = 0.01         # una LN pesa si trae al menos 1 % de la prima del ano
PERFIL_MENSUAL = "auto"           # reparto a meses: "auto" (el que mejor explica el real del ano), "parejo",
                                  # "presupuesto", "historico" o "mezcla" (50/50 presupuesto e historico)
COMPLETAR_LN_PPTO = "dashboard"   # LN ausentes o incompletas en el CSV del ano siguiente: "dashboard" (su cifra en
                                  # el dashboard del presupuesto), "plano" (su prima del ano en curso) o "no"
LN_INCOMPLETA = 0.50              # una LN del CSV esta incompleta si trae menos de 50 % de su referencia
MIN_COBERTURA_PPTO = 0.50         # el CSV del ano siguiente completo debe traer al menos 50 % de la prima de referencia
                                  # (dashboard o ano en curso); con menos parece recortado: no se usa ni se completa
RANGO_CRECIMIENTO_PRIMA = (-0.30, 0.50)   # aviso si la prima del ano siguiente de un grupo crece fuera de este rango
CREDIBILIDAD_PRESUPUESTO = 1.0    # 1 = el crecimiento del plan tal cual; 0.5 = la mitad del crecimiento; 0 = plano
ESCALA_MONEDA_CSV = ((0.5, 2.0), (8.0, 40.0))   # razon CSV / ano en curso: USD o MXN (se divide entre el TC)
LIMITES_TRUNCADO = (65535, 65536, 69999, 99999, 100000, 1048575, 1048576)

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
GRUPOS = sorted(set(GRUPO_DE_RAMO_RESERVA.values()), key=int)


# Catalogo de centros de beneficio del area (/ERP/PROFTCTR -> ramo). Un centro que no este en la lista va aparte como
# "sin ramo": no entra a ningun grupo y se reporta con su monto.
CATALOGO_CENTROS = {
    "10": ["A011000000", "A012000000", "A013000000", "A600000000"],
    "20": [f"A02{i}000000" for i in range(1, 6)],
    "31": ["A331003100", "A331003200", "A331003300"],
    "35": ["A332003400", "A332003500", "A332003600"],
    "39": ["A333003700", "A333003800", "A333003900"],
    "40": ["A041000000", "A042000000", "A043000000"] + [f"A04400000{i}" for i in range(5)],
    "50": [f"A05100000{i}" for i in range(3)] + ["A052000000"] + [f"A05200000{i}" for i in range(2, 7)],
    "60": ["A060000000", "A060000001"],
    "71": ["A071000000"],
    "73": ["A073000000", "A073000001", "A075000000"],
    "80": ["A081000000", "A082000000", "A083000000"],
    "90": [f"A09{i}000000" for i in range(1, 6)] + ["A094000001"],
    "100": ["A100000000", "A100000001", "A100000002"],
    "110": ["A111000000", "A111000008", "A111000009"] + [f"A11200000{i}" for i in range(6)] + ["A112000009"],
    "130": ([f"A13{i}000000" for i in range(1, 5)] + ["A141000000", "A142000000"]
            + [f"A15{i}000000" for i in range(1, 4)] + [f"A16{i}000000" for i in range(1, 6)] + ["A165000001"]
            + [f"A17{i}000000" for i in range(1, 5)]),
}
_RAMO_CENTRO = {c: r for r, cs in CATALOGO_CENTROS.items() for c in cs}


def ramo_de_centro(centro) -> str | None:
    """Centro de beneficio del presupuesto -> ramo segun CATALOGO_CENTROS (None = fuera del catalogo). Los de Fianzas
    (130 en el catalogo) se abren por su segundo y tercer digito en 130-170, como las columnas de la BD de RFV."""
    c = str(centro or "").strip().upper()
    r = _RAMO_CENTRO.get(c)
    return c[1:3] + "0" if r == "130" else r


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
    if not pd.api.types.is_numeric_dtype(s):
        s = s.astype(str).str.replace(",", "", regex=False).str.replace('"', "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _llave(v) -> str:
    """Llaves (compania, contrato, tipo): texto sin espacios, en mayusculas y sin '.0'."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    t = str(v).strip().upper()
    return t[:-2] if t.endswith(".0") else t


def _ln(v) -> str:
    """4001 / 'LN04001' / '4008-Agro' -> 'LN04001' / 'LN04008-Agro'."""
    t = str(v).strip()
    if t.endswith(".0"):
        t = t[:-2]
    t = re.sub(r"(?i)-agro$", "-Agro", t)
    if t.upper().startswith("LN"):
        return "LN" + t[2:]
    return "LN0" + t if t[:2] == "40" else t


def _motor_excel() -> str:
    """calamine (mucho mas rapido) si esta instalado; si no, openpyxl."""
    return "calamine" if importlib.util.find_spec("python_calamine") else "openpyxl"


def _fila_encabezado(filas: list, marcas: tuple) -> int | None:
    for i, fila in enumerate(filas):
        valores = {_norm(v) for v in fila if v is not None}
        if all(_norm(m) in valores for m in marcas):
            return i
    return None


def _leer_hoja(ruta: Path, hoja: str, marcas: tuple) -> pd.DataFrame:
    """Lee una hoja chica buscando la fila de encabezados (la primera de las 10 primeras que trae todas las marcas)."""
    motor = _motor_excel()
    muestra = pd.read_excel(ruta, sheet_name=hoja, header=None, nrows=10, engine=motor)
    fila = _fila_encabezado([muestra.iloc[i].tolist() for i in range(len(muestra))], marcas)
    if fila is None:
        raise ValueError(f"{ruta.name} / {hoja}: no se encontraron los encabezados {marcas}")
    return pd.read_excel(ruta, sheet_name=hoja, header=fila, engine=motor)


def _leer_columnas(ruta: Path, hoja: str, marcas: tuple, columnas: dict) -> tuple[pd.DataFrame, int]:
    """Lee una hoja grande en streaming, solo con las columnas pedidas ({nombre de salida: (nombres posibles)}).
    Regresa (tabla, renglones de datos leidos)."""
    if _motor_excel() == "calamine":
        import python_calamine
        filas = python_calamine.CalamineWorkbook.from_path(str(ruta)).get_sheet_by_name(hoja).iter_rows()
        cierre = None
    else:
        import openpyxl
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        filas = wb[hoja].iter_rows(values_only=True)
        cierre = wb
    primeras = []
    for fila in filas:
        primeras.append(list(fila))
        if len(primeras) >= 10 or _fila_encabezado(primeras[-1:], marcas) is not None:
            break
    i = _fila_encabezado(primeras, marcas)
    if i is None:
        raise ValueError(f"{ruta.name} / {hoja}: no se encontraron los encabezados {marcas}")
    enc = [_norm(v) for v in primeras[i]]
    idx = {}
    for salida, nombres in columnas.items():
        pos = next((enc.index(_norm(n)) for n in nombres if _norm(n) in enc), None)
        if pos is not None:
            idx[salida] = pos
    datos = {k: [] for k in idx}
    leidos = 0
    for fila in primeras[i + 1:]:                    # renglones ya leidos despues del encabezado
        leidos += 1
        for k, p in idx.items():
            datos[k].append(fila[p] if p < len(fila) else None)
    for fila in filas:
        leidos += 1
        for k, p in idx.items():
            datos[k].append(fila[p] if p < len(fila) else None)
    if cierre is not None:
        cierre.close()
    return pd.DataFrame(datos), leidos


def _buscar(patron: str) -> tuple[Path | None, list]:
    """Archivo de entradas/ que cumple el patron. Si hay varios (p. ej. una copia recortada junto a la base completa),
    se usa el MAS GRANDE (la base completa); a igual tamano, el _Ced y luego el mas reciente. Regresa (elegido,
    candidatos)."""
    c = [p for p in ENTRADAS.glob(patron) if not p.name.startswith("~$") and p.is_file()]
    c.sort(key=lambda p: (p.stat().st_size, "_ced" in p.name.lower(), p.stat().st_mtime), reverse=True)
    return (c[0] if c else None), c


class _NoUsable(Exception):
    """Archivo que parece recortado o incompleto: no se usa (ni se completa con otras fuentes)."""


def _huella(funcion) -> str:
    """Huella de la configuracion de lectura (cuentas, prefijos, catalogo, codigo del lector): si cambia, la cache se
    recalcula."""
    partes = (CUENTAS_PRIMA, PREFIJO_SINIESTRO, PREFIJO_COMISION, sorted(GRUPO_DE_RAMO_PRIMA.items(), key=str),
              sorted(_RAMO_CENTRO.items()), LIMITES_TRUNCADO, inspect.getsource(funcion),
              inspect.getsource(ramo_de_centro), inspect.getsource(_leer_columnas))
    return hashlib.md5(repr(partes).encode()).hexdigest()[:8]


def _con_cache(ruta: Path, clave: str, funcion, *args):
    """Resultado de funcion(ruta, *args) guardado en salidas/cache_primas; se recalcula si cambia el archivo, la
    configuracion de lectura o CACHE_VERSION."""
    st = ruta.stat()
    base = f"{clave}_{re.sub(r'[^A-Za-z0-9]+', '_', ruta.stem)}"
    sufijo = "_".join(re.sub(r"[^A-Za-z0-9]+", "", str(a)) for a in args)
    archivo = CACHE / f"{base}_{st.st_size}_{int(st.st_mtime)}_{sufijo}_v{CACHE_VERSION}_{_huella(funcion)}.pkl"
    if archivo.exists():
        try:
            with open(archivo, "rb") as f:
                return pickle.load(f), True
        except Exception:  # noqa: BLE001  (cache danado: se recalcula)
            pass
    res = funcion(ruta, *args)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        for viejo in CACHE.glob(f"{base}_*.pkl"):
            viejo.unlink(missing_ok=True)
        with open(archivo, "wb") as f:
            pickle.dump(res, f)
    except OSError:
        pass
    return res, False


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


def _truncado(ctl: Control):
    if ctl.renglones_leidos in LIMITES_TRUNCADO:
        ctl.notas.append(f"{ctl.renglones_leidos:,} renglones: parece un extracto truncado (fragmento)")


def _a_grupo(tabla: pd.DataFrame, col: str = "ramo") -> pd.DataFrame:
    t = tabla.copy()
    t["grupo"] = t[col].astype(str).map(GRUPO_DE_RAMO_PRIMA)
    return t[t["grupo"].notna()]


def _mas(periodo: int, meses: int) -> int:
    i = (periodo // 100) * 12 + periodo % 100 - 1 + meses
    return (i // 12) * 100 + i % 12 + 1


def _rango(p0: int, p1: int) -> list[int]:
    out, p = [], p0
    while p <= p1:
        out.append(p)
        p = _mas(p, 1)
    return out


# =============================================================================
# LECTORES (cada uno regresa tablas agregadas y su control)
# =============================================================================
def _agregar_real(ruta: Path):
    cols = {"periodo": ("Periodo",), "ramo": ("Ramo2", "Ramo"), "ln": ("LN2", "LN"), "tipo": ("Tipo Rea",),
            "compania": ("Compañía", "Compania"), "contrato": ("Num Contrato",), "prima": ("Primas USD",),
            "siniestros": ("Siniestros USD",), "comisiones": ("Comisiones USD",)}
    df, leidos = _leer_columnas(ruta, "BD", ("Periodo", "Primas USD"), cols)
    ctl = Control(ruta.name, renglones_leidos=leidos)
    _truncado(ctl)
    for c in ("periodo", "ramo", "ln", "prima"):
        if c not in df:
            raise ValueError(f"{ruta.name}: falta la columna {cols[c][0]}")
    per = pd.to_numeric(df["periodo"], errors="coerce")
    ok = per.between(190001, 299912)
    df = df[ok].copy()
    t = pd.DataFrame({
        "periodo": per[ok].astype(int).to_numpy(),
        "ramo": pd.to_numeric(df["ramo"], errors="coerce").fillna(-1).astype(int).astype(str).to_numpy(),
        "ln": df["ln"].map(_ln).to_numpy(),
        "prima": _num(df["prima"]).to_numpy(),
        "siniestros": _num(df["siniestros"]).to_numpy() if "siniestros" in df else 0.0,
        "comisiones": _num(df["comisiones"]).to_numpy() if "comisiones" in df else 0.0,
        "tipo": df["tipo"].map(_llave).to_numpy() if "tipo" in df else "",
        "compania": df["compania"].map(_llave).to_numpy() if "compania" in df else "",
        "contrato": df["contrato"].map(_llave).to_numpy() if "contrato" in df else "",
    })
    ctl.renglones_usados = len(t)
    ctl.filtros = "Periodo valido; Primas/Siniestros/Comisiones USD; LN2 (o LN); Ramo2 (o Ramo)"
    ctl.meses = _rango_meses(t["periodo"])
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("prima", "siniestros", "comisiones"))
    ctl.prima_por_ln = t.groupby("ln")["prima"].sum().to_dict()
    sin_grupo = t[~t["ramo"].isin([k for k, v in GRUPO_DE_RAMO_PRIMA.items() if v])]
    if len(sin_grupo):
        ctl.notas.append(f"ramos sin reserva o sin catalogo: {sorted(sin_grupo['ramo'].unique())} "
                         f"({sin_grupo['prima'].sum() / 1e6:,.1f} M, no se usan)")
    agg = t.groupby(["periodo", "ramo", "ln"], as_index=False)[["prima", "siniestros", "comisiones"]].sum()
    llaves = t.groupby(["periodo", "ln", "tipo", "compania", "contrato", "ramo"], as_index=False)["prima"].sum()
    return agg, llaves, ctl


def _agregar_ppto_anio(ruta: Path, hoja: str):
    """Hoja del presupuesto del ano en curso (Ppto2026): mes a mes por LN y ramo."""
    df = _leer_hoja(ruta, hoja, ("AñoPpto", "MesPpto"))
    ctl = Control(f"{ruta.name} / {hoja}", renglones_leidos=len(df))
    _truncado(ctl)
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


def _agregar_rfcst(ruta: Path, hoja: str):
    """Hoja del reforecast (BD_RFCST26): por renglon (contrato, cedente o MGA), prima real al corte y reforecast."""
    df = _leer_hoja(ruta, hoja, ("Fuente/Hoja",))
    ctl = Control(f"{ruta.name} / {hoja}", renglones_leidos=len(df))
    _truncado(ctl)
    c_ln = _col(df, "LN")
    df = df[df[c_ln].notna() & (df[c_ln].astype(str).str.strip() != "")].copy()
    # corte (real al mes) y ano del reforecast desde los nombres "Primas MMYY"
    mmyy = [(int(m.group(1)), int(m.group(2)), c) for c in df.columns
            if (m := re.match(r"^\s*Primas\s+(\d{2})(\d{2})\s*$", str(c)))]
    if not mmyy:
        raise ValueError("no se encontraron columnas 'Primas MMYY'")
    yy = max(y for _, y, _ in mmyy)
    anual = next(c for m, y, c in mmyy if y == yy and m == 12)
    cortes = [(m, c) for m, y, c in mmyy if y == yy and m < 12]
    if not cortes:
        raise ValueError(f"no se encontro la columna de real al corte de 20{yy}")
    mes_corte, col_corte = max(cortes)
    ant = next((c for m, y, c in mmyy if y == yy - 1 and m == 12), None)
    # compania: la columna con codigos numericos (la otra trae nombres)
    comp = [c for c in df.columns if _norm(c).startswith("compan")]
    c_comp = next((c for c in comp if pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.8), None)
    c_tipo = _col(df, "Tipo Rea", obligatoria=False)
    c_ctto = _col(df, "Num Contrato", obligatoria=False)
    t = pd.DataFrame({
        "ln": df[c_ln].map(_ln),
        "tipo": df[c_tipo].map(_llave) if c_tipo else "",
        "compania": df[c_comp].map(_llave) if c_comp else "",
        "contrato": df[c_ctto].map(_llave) if c_ctto else "",
        "fuente": df[_col(df, "Fuente/Hoja")].astype(str),
        "prima_corte": _num(df[col_corte]), "prima_anual": _num(df[anual]),
        "prima_ant": _num(df[ant]) if ant else 0.0,
    })
    for conc in ("Siniestros", "Costos"):
        c = _col(df, f"{conc} 12{yy:02d}", obligatoria=False)
        t[f"{conc.lower()}_anual"] = _num(df[c]) if c else 0.0
    agro = t["ln"].str.contains("Agro", case=False)
    for c in ("siniestros_anual", "costos_anual"):
        t.loc[agro, c] = -t.loc[agro, c]            # en 4008-Agro vienen con el signo invertido
    ctl.renglones_usados = len(t)
    ctl.filtros = (f"renglones con LN; corte = {col_corte} (real a {mes_corte:02d}/20{yy}); ano = {anual}; "
                   "4008-Agro: siniestros y costos con el signo volteado")
    ctl.meses = f"sin mes: real ene-{mes_corte:02d} y reforecast del ano"
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("prima_anual", "siniestros_anual",
                                                                              "costos_anual"))
    ctl.prima_por_ln = t.groupby("ln")["prima_anual"].sum().to_dict()
    ctl.notas.append(f"prima = {anual} (ano completo)")
    if not c_comp:
        ctl.notas.append("no se encontro la columna de codigo de compania: el reparto usa LN y tipo")
    return {"tabla": t, "anio": 2000 + yy, "mes_corte": mes_corte}, ctl


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


def _agregar_ppto_sig(ruta: Path, anio_sig: int):
    """Presupuesto del ano siguiente (CSV de SAP BW), leido por bloques."""
    avisos = []
    muestra = pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, nrows=20000)
    cols = {
        "gl": _columna_por_contenido(muestra, "/ERP/GL_ACCT", lambda s: s.str.match(r"^[56]\d{9}$"), avisos),
        "ln": _columna_por_contenido(muestra, "/ERP/FUNCAREA", lambda s: s.str.startswith("LN040"), avisos),
        "cc": _columna_por_contenido(muestra, "/ERP/PROFTCTR", lambda s: s.str.match(r"^A\d{9}$"), avisos),
        # ano y mes salen del periodo fiscal AAAA0MM: es la unica columna con ese contenido (el ano fiscal suelto se
        # confunde con ZPLANYEAR, 0CALYEAR o ZSUSCYEAR si los encabezados vienen corridos)
        "per": _columna_por_contenido(muestra, "0FISCPER", lambda s: s.str.match(r"^20\d{2}0(0[1-9]|1[0-2])$"), avisos),
        # importe: numerico, no constante y con negativos (la prima viene en negativo); descarta MANDT, _ID, PRCT_CED
        "imp": _columna_por_contenido(
            muestra, "/ERP/AMOUNT",
            lambda s: (lambda x: x.notna() & (x.nunique() > 1) & bool((x < 0).any()))(
                pd.to_numeric(s.str.replace(",", "", regex=False).str.replace('"', "", regex=False), errors="coerce")),
            avisos),
    }
    for extra, nombre in (("ced", "PRCT_CED"), ("cohorte", "ZSUSCYEAR"), ("moneda", "0CURRENCY")):
        c = _col(muestra, nombre, obligatoria=False)
        if c is not None:
            cols[extra] = c
    leidos, bloques, anios = 0, [], {}
    for ch in pd.read_csv(ruta, encoding="utf-8-sig", dtype=str, usecols=list(set(cols.values())), chunksize=500_000):
        leidos += len(ch)
        t = pd.DataFrame({k: ch[v] for k, v in cols.items()})
        t["per"] = t["per"].astype(str).str.strip()
        t["anio"] = pd.to_numeric(t["per"].str[:4], errors="coerce")
        t["mes"] = t["per"].str[-2:]
        for a, n in t["anio"].value_counts().items():
            anios[int(a)] = anios.get(int(a), 0) + int(n)
        t = t[t["anio"] == anio_sig].copy()
        t["imp"] = _num(t["imp"])
        t["gl"] = t["gl"].astype(str).str.strip()
        t["mes"] = pd.to_numeric(t["mes"], errors="coerce")
        ced = pd.to_numeric(t["ced"], errors="coerce").fillna(0.0) if "ced" in t else pd.Series(0.0, index=t.index)
        t["ced"] = np.where(ced > 1, ced / 100, ced)
        t["cohorte"] = pd.to_numeric(t["cohorte"], errors="coerce") if "cohorte" in t else np.nan
        bloques.append(t)
    t = pd.concat(bloques, ignore_index=True) if bloques else pd.DataFrame(columns=list(cols) + ["ced"])
    ctl = Control(ruta.name, renglones_leidos=leidos)
    _truncado(ctl)
    es_prima = t["gl"].isin(CUENTAS_PRIMA)
    otras_61 = sorted(t.loc[t["gl"].str.startswith("61") & ~es_prima, "gl"].unique())
    t["prima"] = np.where(es_prima, -t["imp"], 0.0)
    t["siniestros"] = np.where(t["gl"].str.startswith(PREFIJO_SINIESTRO), t["imp"], 0.0)
    t["comisiones"] = np.where(t["gl"].str.startswith(PREFIJO_COMISION), t["imp"], 0.0)
    t["retenida"] = t["prima"] * (1 - t["ced"])
    t["anterior"] = np.where(t["cohorte"] < anio_sig, t["prima"], 0.0)
    t["ln"] = t["ln"].map(_ln)
    t["ramo"] = t["cc"].map(ramo_de_centro)
    ctl.renglones_usados = len(t)
    ctl.filtros = (f"0FISCYEAR = {anio_sig} (se descartan "
                   f"{', '.join(f'{a}: {n:,}' for a, n in sorted(anios.items()) if a != anio_sig) or 'nada'}); "
                   f"prima = cuentas {', '.join(CUENTAS_PRIMA)} con el signo volteado; siniestros {PREFIJO_SINIESTRO}*, "
                   f"comisiones {PREFIJO_COMISION}*; importe = /ERP/AMOUNT sin comas")
    ctl.meses = _rango_meses(anio_sig * 100 + t["mes"].dropna().astype(int)) if len(t) else "sin meses"
    ctl.prima, ctl.siniestros, ctl.comisiones = (float(t[c].sum()) for c in ("prima", "siniestros", "comisiones"))
    ctl.prima_por_ln = t.groupby("ln")["prima"].sum().to_dict()
    ctl.notas += avisos
    if avisos:
        ctl.notas.append("columnas localizadas por su contenido: revisa que el export no venga con encabezados corridos")
    if otras_61:
        ctl.notas.append(f"otras cuentas 61 no sumadas como prima: {otras_61[:5]}")
    if "moneda" in cols:
        ctl.notas.append(f"0CURRENCY = {sorted(t['moneda'].dropna().unique())[:3]} (se toma USD; ver escala)")
    sin_ramo = t[t["ramo"].isna() & (t["prima"] != 0)]
    if len(sin_ramo):
        ctl.notas.append(f"centros fuera del catalogo: {sorted(sin_ramo['cc'].astype(str).unique())[:8]} "
                         f"({sin_ramo['prima'].sum() / 1e6:,.1f} M de prima; van aparte como 'sin ramo')")
    if "ced" not in cols:
        ctl.notas.append("sin PRCT_CED: prima retenida = tomada")
    if ctl.prima:
        ctl.notas.append(f"retenida / tomada = {t['retenida'].sum() / ctl.prima:.1%}; prima de anos de suscripcion "
                         f"anteriores = {t['anterior'].sum() / ctl.prima:.1%}")
    t["ramo"] = t["ramo"].fillna("sin ramo")
    agg = t.groupby(["mes", "ramo", "ln"], as_index=False)[["prima", "retenida", "siniestros", "comisiones",
                                                           "anterior"]].sum()
    return {"tabla": agg, "anios": anios}, ctl


# =============================================================================
# EXPOSICIONES (drivers de prima de cada reserva)
# =============================================================================
PESOS_PND = (23 - 2 * np.arange(12)) / 24         # prima no devengada en 24avos: el mes t aporta 23/24, t-11 1/24


def _convolucion(x: np.ndarray, pesos: np.ndarray) -> np.ndarray:
    """out[t] = sum_j pesos[j] * x[t-j]; NaN mientras no haya len(pesos) meses."""
    out = np.convolve(np.nan_to_num(x, nan=np.nan), pesos, mode="full")[:len(x)]
    out[:len(pesos) - 1] = np.nan
    return out


def exposicion(p: pd.Series, nombre: str, v=None) -> pd.Series:
    """Driver de prima a partir de la prima mensual p (indice AAAAMM continuo):
       PND12 = prima no devengada en 24avos; P12 = suma de 12 meses; P24 = promedio anual de 24 meses (1/2 x suma);
       P36 = promedio anual de 36 meses; PD12 = prima devengada de 12 meses; PDP = prima devengada pendiente de
       reportar: sum_a v[a] x PD12(t - 12(a-1)), v[a] = 1 - LAG a (patron anual de HParametros)."""
    x = p.to_numpy(dtype=float)
    if nombre == "P12":
        out = _convolucion(x, np.ones(12))
    elif nombre == "P24":
        out = _convolucion(x, np.full(24, 0.5))
    elif nombre == "P36":
        out = _convolucion(x, np.full(36, 1 / 3))
    elif nombre == "PND12":
        out = _convolucion(x, PESOS_PND)
    elif nombre in ("PD12", "PDP"):
        pnd = _convolucion(x, PESOS_PND)
        ep = x - np.r_[np.nan, np.diff(pnd)]                          # devengada del mes = suscrita - aumento de PND
        pd12 = _convolucion(ep, np.ones(12))
        if nombre == "PD12":
            out = pd12
        else:
            v = list(v if v is not None else (1.0,))
            out = np.zeros(len(x))
            for a, va in enumerate(v):
                desfase = np.r_[np.full(12 * a, np.nan), pd12[:len(x) - 12 * a]] if a else pd12
                out = out + va * desfase
    else:
        raise ValueError(f"exposicion desconocida: {nombre}")
    return pd.Series(out, index=p.index)


def fraccion_estimada(p: pd.Series, es_estimado: pd.Series, nombre: str, v=None) -> pd.Series:
    """Parte del driver que viene de meses estimados (reforecast o presupuesto), en [0, 1]. Exacta porque los
    drivers son lineales en la prima."""
    total = exposicion(p, nombre, v)
    est = exposicion(p.where(es_estimado.reindex(p.index).fillna(False).astype(bool), 0.0), nombre, v)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = (est / total).clip(0.0, 1.0)
    return f.where(total.abs() > 0, 0.0)


# =============================================================================
# SERIE MENSUAL POR GRUPO
# =============================================================================
@dataclass
class Primas:
    mensual: pd.DataFrame            # periodo x grupo: prima tomada USD (del primer mes real al ultimo proyectado)
    fuente: pd.DataFrame             # periodo x grupo: real / reforecast / reforecast (ritmo) / presupuesto / ...
    ppto_curso: pd.DataFrame | None  # periodo x grupo: presupuesto del ano en curso repartido con el perfil elegido
    sigma_plan: dict                 # grupo -> error tipico del plan (|ln real / presupuesto| del ano en curso)
    cobertura: dict                  # grupo -> cobertura del historico (0-1) o None si no se pudo medir
    ultimo_real: int                 # ultimo mes con prima real
    perfil: dict                     # {"elegido": ..., "errores": {candidato: error}}
    tablas: dict                     # nombre -> DataFrame para la hoja Primas_Controles
    controles: list                  # filas de control por archivo
    avisos: list                     # avisos para consola y Alertas
    tiene_siguiente: bool            # hay prima del ano siguiente (presupuesto)
    retenida: pd.DataFrame | None    # periodo x grupo del presupuesto del ano siguiente (tomada x (1 - cesion))
    anio_sig: int = 0

    def es_estimado(self, grupo: str) -> pd.Series:
        return self.fuente[grupo] != "real"

    def grupos_utiles(self) -> list:
        return [g for g, c in self.cobertura.items() if c is not None and c >= MIN_COBERTURA_HISTORIA]


def _perfiles(real_anio: pd.DataFrame, ppto_anio: pd.DataFrame | None, historia: pd.DataFrame, anio: int,
              mes_ult: int, grupos_hist: list) -> tuple[dict, dict]:
    """Participacion mensual (12 valores) por grupo de cada candidato y su error al explicar la forma de los meses
    1..mes_ult del real del ano."""
    cand = {"parejo": {g: np.full(12, 1 / 12) for g in GRUPOS}}
    if ppto_anio is not None and len(ppto_anio):
        pa = _a_grupo(ppto_anio[ppto_anio["anio"] == anio]).groupby(["grupo", "mes"])["prima"].sum().clip(lower=0)
        forma = {}
        for g in GRUPOS:
            v = np.array([pa.get((g, m), 0.0) for m in range(1, 13)])
            forma[g] = v / v.sum() if v.sum() > 0 else np.full(12, 1 / 12)
        cand["presupuesto"] = forma
    anios_h = [a for a in (anio - 3, anio - 2, anio - 1)
               if all(a * 100 + m in historia.index for m in range(1, 13))]
    if anios_h and grupos_hist:
        forma = {}
        for g in GRUPOS:
            partes = []
            for a in anios_h:
                v = np.array([max(0.0, historia.at[a * 100 + m, g]) if g in historia.columns else 0.0
                              for m in range(1, 13)])
                if v.sum() > 0:
                    partes.append(v / v.sum())
            forma[g] = np.mean(partes, axis=0) if partes else np.full(12, 1 / 12)
        cand["historico"] = forma
        if "presupuesto" in cand:
            cand["mezcla"] = {g: 0.5 * cand["presupuesto"][g] + 0.5 * forma[g] for g in GRUPOS}
    ra = real_anio.groupby(["grupo", "mes"])["prima"].sum()
    errores = {}
    for nombre, forma in cand.items():
        num = den = 0.0
        for g in GRUPOS:
            if nombre in ("historico", "mezcla") and g not in grupos_hist:
                continue
            r = np.array([max(0.0, ra.get((g, m), 0.0)) for m in range(1, mes_ult + 1)])
            if r.sum() < 1e6:
                continue
            s = forma[g][:mes_ult]
            s = s / s.sum() if s.sum() > 0 else np.full(mes_ult, 1 / mes_ult)
            num += r.sum() * float(np.abs(s - r / r.sum()).sum())
            den += r.sum()
        errores[nombre] = num / den if den else math.nan
    return cand, errores


def leer_primas(ultimo_reservas: int, periodo_fin: int, lineas_dashboard: dict | None = None,
                tc_proy: dict | None = None, verbose: bool = True) -> Primas | None:
    """Arma la prima mensual por grupo con lo que haya en entradas/. None si no hay prima real.
    lineas_dashboard = {LN: prima del ano siguiente en el dashboard del presupuesto}; tc_proy = TC por mes."""
    a_res = ultimo_reservas // 100
    nombres = {"aa": f"{a_res % 100:02d}", "aaaa": str(a_res), "sig": str(a_res + 1)}
    pat = {"hist": PATRON_REAL_HIST.format(**nombres), "anio": PATRON_REAL_ANIO.format(**nombres),
           "rfcst": PATRON_RFCST.format(**nombres), "ppto": PATRON_PPTO.format(**nombres)}
    hoja_rfcst, hoja_ppto_anio = HOJA_RFCST.format(**nombres), HOJA_PPTO_ANIO.format(**nombres)
    encontrados = {k: _buscar(v) for k, v in pat.items()}
    rutas = {k: v[0] for k, v in encontrados.items()}
    if rutas["hist"] is None and rutas["anio"] is None:
        return None
    controles, avisos, tablas = [], [], {}

    def log(msg):
        if verbose:
            print(f"   {msg}", flush=True)

    # archivos encontrados: de cada patron se toma el mas grande; su estado final se llena al terminar
    archivos, estado = [], {}
    for k, (elegido, cands) in encontrados.items():
        for c in cands:
            st = c.stat()
            archivos.append({"Base": {"hist": "real historico", "anio": "real del ano", "rfcst": "reforecast y "
                                      "presupuesto del ano", "ppto": "presupuesto del ano siguiente"}[k],
                             "Patron": pat[k], "Archivo": c.name, "Tamano (MB)": round(st.st_size / 2**20, 1),
                             "Fecha": pd.Timestamp(st.st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"), "_k": k,
                             "_elegido": c == elegido})
        if elegido is not None:
            estado[k] = "se usa"
        if len(cands) > 1:
            avisos.append(f"Primas: hay {len(cands)} archivos que cumplen {pat[k]}: se usa el mas grande ({elegido.name}, "
                          f"{elegido.stat().st_size / 2**20:,.1f} MB); se ignoran {', '.join(c.name for c in cands[1:])}")
    nombre_archivos = "Archivos de primas (de cada patron se toma el mas grande)"
    tablas[nombre_archivos] = None                  # (se llena al final, con el estado de cada archivo)
    reales, llaves = {}, {}
    recortados = []
    for k in ("hist", "anio"):
        if rutas[k] is not None:
            (agg, ll, ctl), cache = _con_cache(rutas[k], "real", _agregar_real)
            log(f"Primas: {rutas[k].name} ({'cache' if cache else 'leido'}; {ctl.renglones_leidos:,} renglones, "
                f"{ctl.meses})")
            reales[k], llaves[k] = agg, ll
            controles.append(ctl.fila())
            if any("truncado" in n for n in ctl.notas):
                recortados.append((k, ctl.renglones_leidos))
    # una base recortada se deja fuera; si todas lo estan solo sirven de diagnostico (el factor no se aplica)
    solo_diagnostico = bool(recortados) and len(recortados) == len(reales)
    for k, n in recortados:
        if solo_diagnostico:
            estado[k] = "recortado: solo diagnostico (el factor no se aplica)"
            avisos.append(f"Primas: {rutas[k].name} parece recortado ({n:,} renglones): solo se muestra como "
                          "diagnostico, el factor no se aplica (ni se completa con otras fuentes); copia la base "
                          "completa en entradas/")
        else:
            estado[k] = "recortado: no se usa"
            avisos.append(f"Primas: {rutas[k].name} parece recortado ({n:,} renglones): no se usa (ni se completa con "
                          "otras fuentes); copia la base completa en entradas/")
            reales.pop(k, None)
            llaves.pop(k, None)
    hist, anio_df = reales.get("hist"), reales.get("anio")
    meses_anio = set(anio_df["periodo"]) if anio_df is not None else set()
    partes = []
    if hist is not None:
        partes.append(hist[~hist["periodo"].isin(meses_anio)])
    if anio_df is not None:
        partes.append(anio_df)
    real = _a_grupo(pd.concat(partes, ignore_index=True))
    ultimo_real = int(real["periodo"].max())
    anio, mes_ult = divmod(ultimo_real, 100)
    real["mes"] = real["periodo"] % 100
    real_anio = real[real["periodo"] // 100 == anio]
    llaves_anio = _a_grupo(llaves.get("anio", llaves.get("hist")))
    llaves_anio = llaves_anio[llaves_anio["periodo"] // 100 == anio]

    # cobertura del historico: en los meses que comparte con el real del ano debe traer (casi) la misma prima
    cobertura, cobertura_supuesta = {}, False
    comunes = sorted(meses_anio & set(hist["periodo"])) if hist is not None else []
    if comunes:
        h = _a_grupo(hist[hist["periodo"].isin(comunes)])
        a = _a_grupo(anio_df[anio_df["periodo"].isin(comunes)])
        hg, ag = h.groupby("grupo")["prima"].sum(), a.groupby("grupo")["prima"].sum()
        for g in GRUPOS:
            base = float(ag.get(g, 0.0))
            cobertura[g] = float(hg.get(g, 0.0)) / base if base > 0 else None
        hm = h.groupby(["grupo", "periodo"])["prima"].sum()
        am = a.groupby(["grupo", "periodo"])["prima"].sum()
        filas = [{"Grupo": g, "Periodo": p, "Historico (M USD)": hm.get((g, p), 0.0) / 1e6,
                  "Real del ano (M USD)": am.get((g, p), 0.0) / 1e6} for g in GRUPOS for p in comunes]
        tablas["Historico contra real del ano (meses comunes)"] = pd.DataFrame(filas)
        difieren = [f"{f['Grupo']} {f['Periodo']}" for f in filas if f["Real del ano (M USD)"] > 0.5
                    and abs(f["Historico (M USD)"] / f["Real del ano (M USD)"] - 1) > TOLERANCIA_TRASLAPE]
        if difieren and all((c or 0) >= MIN_COBERTURA_HISTORIA for c in cobertura.values() if c is not None):
            avisos.append(f"Primas: historico y real del ano difieren mas de {TOLERANCIA_TRASLAPE:.0%} en "
                          f"{len(difieren)} grupo-mes ({', '.join(difieren[:6])}...)")
    elif hist is not None:
        truncado = any("truncado" in c.get("Notas", "") for c in controles if c["Archivo"] == rutas["hist"].name)
        if truncado:                        # (ya avisado arriba como recortado)
            cobertura = {g: None for g in GRUPOS}
        else:                               # se mide abajo contra el real al corte del reforecast, si lo hay
            cobertura = {g: 1.0 for g in GRUPOS}
            cobertura_supuesta = True
    else:
        avisos.append(f"Primas: sin {pat['hist']} completo solo hay {len(meses_anio)} meses de prima real: no alcanza "
                      "para estimar la relacion reserva / prima")
        cobertura = {g: None for g in GRUPOS}
    if solo_diagnostico:                    # solo hay bases de real recortadas: no se usa ningun grupo
        cobertura = {g: None for g in GRUPOS}
    incompletos = [f"{g} ({c:.0%})" for g, c in cobertura.items() if c is not None and c < MIN_COBERTURA_HISTORIA]
    if incompletos:
        avisos.append(f"Primas: el historico trae menos de {MIN_COBERTURA_HISTORIA:.0%} de la prima del real del ano "
                      f"en los grupos {', '.join(incompletos)} (fragmento o base incompleta): esos grupos se "
                      "proyectan con la recta")
    tablas["Cobertura del historico por grupo"] = pd.DataFrame(
        [{"Grupo": g, "Cobertura": c, "Se usa": bool(c is not None and c >= MIN_COBERTURA_HISTORIA)}
         for g, c in cobertura.items()])
    # continuidad del historico: un ano con menos de la mitad de la prima del anterior en un grupo material
    anual = real.groupby([real["periodo"] // 100, "grupo"])["prima"].sum().unstack(fill_value=0.0)
    for g in anual.columns:
        s = anual[g]
        for a in s.index[1:]:
            if a < anio and s.get(a - 1, 0) > 5e6 and s[a] < 0.5 * s[a - 1]:
                avisos.append(f"Primas: el grupo {g} trae en {a} menos de la mitad de la prima de {a - 1} "
                              "(posible hueco en el historico)")
    tablas["Prima real por ano y grupo (M USD)"] = (anual / 1e6).reset_index().rename(columns={"periodo": "Ano"})

    mensual = real.pivot_table(index="periodo", columns="grupo", values="prima", aggfunc="sum")
    mensual = mensual.reindex(_rango(int(mensual.index.min()), ultimo_real)).fillna(0.0)
    for g in GRUPOS:
        if g not in mensual.columns:
            mensual[g] = 0.0
    mensual = mensual[GRUPOS]
    fuente = pd.DataFrame("real", index=mensual.index, columns=GRUPOS)

    # presupuesto y reforecast del ano en curso
    ppto_anio = rfcst = None
    if rutas["rfcst"] is not None:
        try:
            (rfcst, ctl), cache = _con_cache(rutas["rfcst"], "rfcst", _agregar_rfcst, hoja_rfcst)
            controles.append(ctl.fila())
            (ppto_anio, ctl2), _ = _con_cache(rutas["rfcst"], "pptoanio", _agregar_ppto_anio, hoja_ppto_anio)
            controles.append(ctl2.fila())
            log(f"Primas: {rutas['rfcst'].name} ({'cache' if cache else 'leido'}; reforecast y presupuesto del ano)")
            for c_, nombre in ((ctl, "rfcst"), (ctl2, "ppto_anio")):
                if any("truncado" in n for n in c_.notas):
                    avisos.append(f"Primas: {c_.archivo} parece recortado ({c_.renglones_leidos:,} renglones): no se usa "
                                  "(ni se completa con otras fuentes); copia la base completa en entradas/")
                    if nombre == "rfcst":
                        rfcst = None
                    else:
                        ppto_anio = None
                    estado["rfcst"] = ("recortado: no se usa" if rfcst is None and ppto_anio is None else
                                       f"se usa sin la hoja {c_.archivo.split(' / ')[-1]} (recortada)")
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Primas: no se pudo leer {rutas['rfcst'].name} ({e}); el resto del ano va sin reforecast")
            rfcst = ppto_anio = None
            estado["rfcst"] = "no se pudo leer: no se usa"

    # sin real del ano: la cobertura del historico se mide con el real al corte del reforecast (total, sin ramo)
    if cobertura_supuesta:
        if rfcst is not None and rfcst["anio"] == anio and rfcst["mes_corte"] <= mes_ult:
            # todas las cuentas del historico (con y sin ramo de reserva), en las LN que trae el reforecast
            lns = set(rfcst["tabla"]["ln"])
            h = hist[(hist["periodo"] // 100 == anio) & (hist["periodo"] % 100 <= rfcst["mes_corte"])
                     & hist["ln"].isin(lns)]
            ref, h_ = float(rfcst["tabla"]["prima_corte"].sum()), float(h["prima"].sum())
            c_ = h_ / ref if ref > 0 else None
            tablas["Historico contra real al corte del reforecast"] = pd.DataFrame(
                [{"Historico (M USD)": h_ / 1e6, "Reforecast al corte (M USD)": ref / 1e6, "Cobertura": c_}])
            if c_ is None or c_ < MIN_COBERTURA_HISTORIA:
                avisos.append(f"Primas: sin {pat['anio']} completo, {rutas['hist'].name} trae "
                              f"{h_ / 1e6:,.1f} M de ene a {rfcst['mes_corte']:02d}/{anio} contra {ref / 1e6:,.1f} M "
                              "del real al corte del reforecast: parece incompleto; no se usa para el factor")
                cobertura = {g: None for g in GRUPOS}
            else:
                avisos.append(f"Primas: sin {pat['anio']} completo, la cobertura de {rutas['hist'].name} se mide contra "
                              f"el real al corte del reforecast ({c_:.1%})")
        else:
            avisos.append(f"Primas: sin {pat['anio']} completo ni reforecast no se puede medir la cobertura de "
                          f"{rutas['hist'].name}; se toma como completa")
        tablas["Cobertura del historico por grupo"] = pd.DataFrame(
            [{"Grupo": g, "Cobertura": c, "Se usa": bool(c is not None and c >= MIN_COBERTURA_HISTORIA)}
             for g, c in cobertura.items()])

    # perfil mensual: el candidato que mejor explica la forma de los meses reales del ano
    grupos_hist = [g for g, c in cobertura.items() if c is not None and c >= MIN_COBERTURA_HISTORIA]
    formas, errores = _perfiles(real_anio, ppto_anio, mensual, anio, mes_ult, grupos_hist)
    if PERFIL_MENSUAL != "auto" and PERFIL_MENSUAL in formas:
        elegido = PERFIL_MENSUAL
    else:
        validos = {k: e for k, e in errores.items() if np.isfinite(e)}
        elegido = min(validos, key=validos.get) if validos else "parejo"
    forma = formas[elegido]
    perfil = {"elegido": elegido, "errores": errores}
    tablas["Perfil mensual (error al explicar la forma del real del ano)"] = pd.DataFrame(
        [{"Candidato": k, "Error": e, "Elegido": k == elegido} for k, e in errores.items()])

    # sigma del plan y presupuesto del ano en curso repartido con el perfil (para el backtest ex ante)
    sigma, ppto_curso = {}, None
    if ppto_anio is not None:
        pa = _a_grupo(ppto_anio[ppto_anio["anio"] == anio])
        acum_p = pa[pa["mes"] <= mes_ult].groupby("grupo")["prima"].sum()
        acum_r = real_anio.groupby("grupo")["prima"].sum()
        filas = []
        for g in GRUPOS:
            rp, rr = float(acum_p.get(g, 0.0)), float(acum_r.get(g, 0.0))
            sigma[g] = float(np.clip(abs(math.log(rr / rp)), 0.05, 0.50)) if rp > 0 and rr > 0 else 0.15
            filas.append({"Grupo": g, "Real acumulado (M USD)": rr / 1e6, "Presupuesto acumulado (M USD)": rp / 1e6,
                          "Sigma del plan": sigma[g]})
        tablas["Presupuesto del ano en curso contra real (acumulado)"] = pd.DataFrame(filas)
        # presupuesto del ano en curso con sus propios meses (para el backtest ex ante: sin informacion posterior al
        # corte, a diferencia del perfil, que se elige con el real del ano)
        ppto_curso = pa.groupby(["mes", "grupo"])["prima"].sum().unstack(fill_value=0.0)
        ppto_curso = ppto_curso.reindex(index=range(1, 13), columns=GRUPOS, fill_value=0.0)
        ppto_curso.index = [anio * 100 + m for m in ppto_curso.index]
    else:
        sigma = {g: 0.15 for g in GRUPOS}

    # resto del ano en curso
    meses_rest = list(range(mes_ult + 1, 13))
    resto_ln = {}                          # resto del ano estimado por LN (el mismo que va a la prima mensual)
    if meses_rest and rfcst is not None:
        t = rfcst["tabla"].copy()
        escala = (12 - mes_ult) / (12 - rfcst["mes_corte"]) if rfcst["mes_corte"] < 12 else 1.0
        if rfcst["anio"] != anio:
            avisos.append(f"Primas: el reforecast es de {rfcst['anio']} y el real llega a {ultimo_real}; no se usa")
            t = t.iloc[0:0]
        elif escala != 1:
            avisos.append(f"Primas: el reforecast tiene corte a {rfcst['mes_corte']:02d} y el real llega a "
                          f"{mes_ult:02d}: el resto del reforecast se escala por {escala:.2f}")
        t["resto"] = (t["prima_anual"] - t["prima_corte"]) * escala
        resto_ln = t.groupby("ln")["resto"].sum().to_dict()
        # control: real al corte del reforecast contra el real por LN
        rc = t.groupby("ln")["prima_corte"].sum()
        rr = real_anio[real_anio["mes"] <= rfcst["mes_corte"]].groupby("ln")["prima"].sum()
        filas = []
        for ln in sorted(set(rc.index) | set(rr.index)):
            a_, b_ = float(rc.get(ln, 0.0)), float(rr.get(ln, 0.0))
            filas.append({"LN": ln, "Reforecast al corte (M USD)": a_ / 1e6, "Real (M USD)": b_ / 1e6,
                          "Diferencia": (a_ / b_ - 1) if b_ else None})
            if ln in rc.index and b_ > 1e6 and abs(a_ / b_ - 1) > TOLERANCIA_REAL_RFCST:   # (las LN que no vienen
                # en el reforecast se avisan aparte)
                avisos.append(f"Primas: en {ln} el real al corte del reforecast ({a_ / 1e6:,.1f} M) difiere del real "
                              f"({b_ / 1e6:,.1f} M) en {a_ / b_ - 1:+.1%}")
        tablas["Reforecast al corte contra real por LN"] = pd.DataFrame(filas)
        # reparto a grupos por jerarquia de llaves con la mezcla del real del ano
        ll = llaves_anio.copy()
        niveles = [("contrato", ["tipo", "compania", "contrato"]), ("cedente", ["ln", "tipo", "compania"]),
                   ("LN y tipo", ["ln", "tipo"]), ("LN", ["ln"])]
        mezclas = []
        for nombre, llave in niveles:
            m = ll.groupby(llave + ["grupo"])["prima"].sum().clip(lower=0)
            tot = m.groupby(level=list(range(len(llave)))).sum()
            mezclas.append((nombre, llave, m, tot[tot > 0]))
        if ppto_anio is not None:
            pa = _a_grupo(ppto_anio[ppto_anio["anio"] == anio]).groupby(["ln", "grupo"])["prima"].sum().clip(lower=0)
            mezclas.append(("presupuesto del ano", ["ln"], pa, pa.groupby(level=0).sum().loc[lambda s: s > 0]))
        asignado = {g: 0.0 for g in GRUPOS}
        por_nivel = {n: 0.0 for n, *_ in mezclas}
        por_nivel["sin asignar"] = 0.0
        for fila in t.itertuples():
            if abs(fila.resto) < 1:
                continue
            for nombre, llave, m, tot in mezclas:
                k = tuple(getattr(fila, c) for c in llave)
                k = k[0] if len(k) == 1 else k
                if k in tot.index:
                    for g, w in (m.loc[k] / tot.loc[k]).items():
                        asignado[g] += fila.resto * w
                    por_nivel[nombre] += fila.resto
                    break
            else:
                por_nivel["sin asignar"] += fila.resto
        total_resto = sum(por_nivel.values())
        tablas["Reparto del reforecast a ramos (por nivel de llave)"] = pd.DataFrame(
            [{"Nivel": n, "Resto del ano (M USD)": v / 1e6, "%": v / total_resto if total_resto else None}
             for n, v in por_nivel.items()])
        if abs(por_nivel["sin asignar"]) > 1e5:
            avisos.append(f"Primas: {por_nivel['sin asignar'] / 1e6:,.1f} M del reforecast no se pudieron asignar a "
                          "un ramo (ninguna llave coincide)")
        # LN con prima real en el ano que no vienen en el reforecast: al ritmo del ano
        total_anio = float(real_anio["prima"].sum())
        imputadas = []
        for ln, acum in real_anio.groupby("ln")["prima"].sum().items():
            if ln in set(t["ln"]) or total_anio <= 0 or acum < UMBRAL_LN_MATERIAL * total_anio:
                continue
            resto = acum * (12 - mes_ult) / mes_ult
            resto_ln[ln] = resto_ln.get(ln, 0.0) + resto
            mezcla = real_anio[real_anio["ln"] == ln].groupby("grupo")["prima"].sum().clip(lower=0)
            for g, w in (mezcla / mezcla.sum()).items():
                asignado[g] += resto * w
            imputadas.append({"LN": ln, "Real acumulado (M USD)": acum / 1e6, "Resto imputado (M USD)": resto / 1e6})
            avisos.append(f"Primas: {ln} trae {acum / 1e6:,.1f} M de prima real en {anio} pero no viene en el "
                          f"reforecast: el resto del ano se estima al ritmo del ano ({resto / 1e6:,.1f} M)")
        if imputadas:
            tablas["LN sin reforecast (al ritmo del ano)"] = pd.DataFrame(imputadas)
        filas = {}
        for g in GRUPOS:
            s = forma[g][mes_ult:]
            s = s / s.sum() if s.sum() > 0 else np.full(len(meses_rest), 1 / len(meses_rest))
            for m, w in zip(meses_rest, s):
                filas.setdefault(anio * 100 + m, {})[g] = asignado[g] * w
        rest = pd.DataFrame.from_dict(filas, orient="index")[GRUPOS]
        if (rest < 0).any().any():
            avisos.append("Primas: el reforecast deja prima negativa en algun grupo y mes; se acota a 0")
            rest = rest.clip(lower=0)
        mensual = pd.concat([mensual, rest])
        fuente = pd.concat([fuente, pd.DataFrame("reforecast", index=rest.index, columns=GRUPOS)])
    elif meses_rest:
        # sin reforecast: mismo mes del ano anterior por el crecimiento del ano
        filas = {}
        for g in GRUPOS:
            prev = [mensual.at[(anio - 1) * 100 + m, g] for m in range(1, mes_ult + 1)
                    if (anio - 1) * 100 + m in mensual.index]
            acum = float(mensual.loc[[anio * 100 + m for m in range(1, mes_ult + 1)], g].sum())
            crec = float(np.clip(acum / sum(prev), 0.5, 2.0)) if prev and sum(prev) > 0 else 1.0
            for m in meses_rest:
                p_ant = (anio - 1) * 100 + m
                filas.setdefault(anio * 100 + m, {})[g] = (mensual.at[p_ant, g] if p_ant in mensual.index else 0) * crec
        rest = pd.DataFrame.from_dict(filas, orient="index")[GRUPOS]
        k_ = float(rest.to_numpy().sum()) / max(float(real_anio["prima"].sum()), 1.0)
        resto_ln = {ln: v * k_ for ln, v in real_anio.groupby("ln")["prima"].sum().items()}
        mensual = pd.concat([mensual, rest])
        fuente = pd.concat([fuente, pd.DataFrame("ano anterior x crecimiento", index=rest.index, columns=GRUPOS)])
        avisos.append(f"Primas: sin {pat['rfcst']} utilizable: el resto de {anio} se estima con el mismo mes del ano "
                      "anterior por el crecimiento del ano")

    # presupuesto del ano siguiente
    anio_sig = anio + 1
    retenida, tiene_sig = None, False
    if rutas["ppto"] is not None:
        try:
            (pp, ctl), cache = _con_cache(rutas["ppto"], "ppto", _agregar_ppto_sig, anio_sig)
            controles.append(ctl.fila())
            log(f"Primas: {rutas['ppto'].name} ({'cache' if cache else 'leido'}; {ctl.renglones_leidos:,} renglones)")
            if any("truncado" in n for n in ctl.notas):
                raise _NoUsable(f"parece recortado ({ctl.renglones_leidos:,} renglones); no se completa con el "
                                "dashboard: copia la base completa en entradas/")
            p = pp["tabla"].copy()
            tablas["Presupuesto del ano siguiente: renglones por ano fiscal"] = pd.DataFrame(
                [{"Ano fiscal": a, "Renglones": n, "Se usa": a == anio_sig} for a, n in sorted(pp["anios"].items())])
            # centros fuera del catalogo: van aparte como "sin ramo" (no entran a ningun grupo) y se reportan
            sin = p[(p["ramo"] == "sin ramo") & (p["prima"] != 0)]
            if len(sin):
                avisos.append(f"Primas: {sin['prima'].sum() / 1e6:,.1f} M del presupuesto {anio_sig} en centros de "
                              "beneficio fuera del catalogo (van aparte como 'sin ramo' y no entran al factor; ver "
                              "notas del control)")
            csv_ln_todo = p.groupby("ln")["prima"].sum()        # toda la LN, como en el dashboard
            sin_reserva = float(p[p["ramo"].map(lambda r: GRUPO_DE_RAMO_PRIMA.get(str(r)) is None)]["prima"].sum())
            p = _a_grupo(p[p["ramo"] != "sin ramo"])
            # ano en curso por LN: real + el mismo resto del ano que va a la prima mensual
            real_ln = real_anio.groupby("ln")["prima"].sum()
            curso = {ln: float(real_ln.get(ln, 0.0)) + float(resto_ln.get(ln, 0.0))
                     for ln in set(real_ln.index) | set(resto_ln)}
            # escala de moneda contra el ano en curso (solo si el ano en curso esta completo)
            razones = [csv_ln_todo[ln] / curso[ln] for ln in csv_ln_todo.index
                       if curso.get(ln, 0) > 1e6 and csv_ln_todo[ln] > 0]
            if razones and resto_ln:
                med = float(np.median(razones))
                (u0, u1), (m0, m1) = ESCALA_MONEDA_CSV
                if m0 <= med <= m1 and tc_proy:
                    tc_m = float(np.mean([v for k, v in tc_proy.items() if k // 100 == anio_sig] or [1.0]))
                    p[["prima", "retenida"]] = p[["prima", "retenida"]] / tc_m
                    csv_ln_todo = csv_ln_todo / tc_m
                    avisos.append(f"Primas: el presupuesto {anio_sig} parece venir en pesos (razon {med:.1f} contra "
                                  f"{anio}); se divide entre el TC promedio {tc_m:.2f}")
                elif not (u0 <= med <= u1):
                    avisos.append(f"Primas: la escala del presupuesto {anio_sig} contra {anio} es {med:.2f}: revisa la "
                                  "moneda o el alcance del CSV")
            # perimetro por LN: completar las LN ausentes o incompletas (misma base: toda la LN)
            referencia = {ln: float(v) for ln, v in (lineas_dashboard or {}).items() if v}
            fuente_ref = "dashboard" if referencia else "ano en curso"
            if not referencia:
                referencia = curso
            total_curso = sum(curso.values()) or 1.0
            # antes de completar nada: la base del CSV debe estar completa (no un recorte)
            tot_csv, tot_ref = float(csv_ln_todo.sum()), float(sum(referencia.values()))
            if tot_ref and tot_csv < MIN_COBERTURA_PPTO * tot_ref:
                raise _NoUsable(f"trae {tot_csv / 1e6:,.1f} M contra {tot_ref / 1e6:,.1f} M de referencia ({fuente_ref}), "
                                f"menos de {MIN_COBERTURA_PPTO:.0%}: parece recortado o incompleto; no se completa con "
                                "otras fuentes: revisa que en entradas/ este la base completa")
            filas, completar, origen = [], {}, {}
            for ln in sorted(set(referencia) | set(csv_ln_todo.index)):
                c_ = float(csv_ln_todo.get(ln, 0.0))
                ref = float(referencia.get(ln, 0.0))
                material = curso.get(ln, 0.0) >= UMBRAL_LN_MATERIAL * total_curso or ref >= UMBRAL_LN_MATERIAL * total_curso
                accion = "se usa tal cual"
                if ref == 0 and c_ > 0 and fuente_ref == "dashboard":
                    accion = "LN del CSV que no esta en la referencia (se usa tal cual)"
                    avisos.append(f"Primas: {ln} viene en el presupuesto {anio_sig} ({c_ / 1e6:,.1f} M) pero no en el "
                                  "dashboard: revisa la etiqueta de la LN")
                elif ref > 0 and c_ < LN_INCOMPLETA * ref and material and COMPLETAR_LN_PPTO != "no":
                    if COMPLETAR_LN_PPTO == "plano" and ln in curso:
                        meta, org = curso[ln], "ano en curso"
                    else:
                        meta, org = ref, fuente_ref
                    if meta > c_:
                        completar[ln], origen[ln] = meta - c_, org
                        accion = f"se completa con {meta / 1e6:,.1f} M ({org})"
                elif ref > 0 and abs(c_ / ref - 1) > 0.05:
                    accion = "diferencia senalada (no se ajusta)"
                filas.append({"LN": ln, "CSV (M USD)": c_ / 1e6, f"Referencia {fuente_ref} (M USD)": ref / 1e6,
                              f"Ano {anio} real + resto estimado (M USD)": curso.get(ln, 0.0) / 1e6,
                              "CSV / referencia": (c_ / ref) if ref else None, "Accion": accion,
                              "Completado (M USD)": completar.get(ln, 0.0) / 1e6})
            # conciliacion: lo completado no puede llevar el total por arriba de la referencia
            if completar and tot_ref and tot_csv + sum(completar.values()) > 1.05 * tot_ref:
                avisos.append(f"Primas: completar {', '.join(completar)} llevaria el presupuesto {anio_sig} a "
                              f"{(tot_csv + sum(completar.values())) / 1e6:,.1f} M contra {tot_ref / 1e6:,.1f} M de "
                              "referencia (probables etiquetas de LN distintas): no se completa")
                for f in filas:
                    if f["LN"] in completar:
                        f["Accion"], f["Completado (M USD)"] = "no se completa (el total pasaria la referencia)", 0.0
                completar = {}
            tablas[f"Presupuesto {anio_sig}: perimetro por LN"] = pd.DataFrame(filas)
            if sin_reserva:
                avisos.append(f"Primas: {sin_reserva / 1e6:,.1f} M del presupuesto {anio_sig} son de ramos sin reserva "
                              "en las BD (p. ej. ramo 20): no entran al factor")
            if tot_ref and abs(tot_csv / tot_ref - 1) > 0.05:
                avisos.append(f"Primas: el presupuesto {anio_sig} del CSV suma {tot_csv / 1e6:,.1f} M contra "
                              f"{tot_ref / 1e6:,.1f} M de referencia ({fuente_ref})"
                              + (f"; se completan {', '.join(completar)} ({sum(completar.values()) / 1e6:,.1f} M)"
                                 if completar else ""))
            # prima mensual por grupo (y lo completado con la mezcla del ano en curso de la LN)
            if elegido == "presupuesto":
                sig = p.groupby(["mes", "grupo"])["prima"].sum().unstack(fill_value=0.0)
                sig = sig.reindex(range(1, 13), fill_value=0.0)
            else:
                tot_g = p.groupby("grupo")["prima"].sum()
                sig = pd.DataFrame({g: float(tot_g.get(g, 0.0)) * forma[g] for g in GRUPOS}, index=range(1, 13))
            extra = pd.DataFrame(0.0, index=range(1, 13), columns=GRUPOS)
            for ln, monto in completar.items():
                mezcla = real_anio[real_anio["ln"] == ln].groupby("grupo")["prima"].sum().clip(lower=0)
                if mezcla.sum() <= 0 and ppto_anio is not None:
                    mezcla = _a_grupo(ppto_anio[(ppto_anio["anio"] == anio) & (ppto_anio["ln"] == ln)]) \
                        .groupby("grupo")["prima"].sum().clip(lower=0)
                if mezcla.sum() <= 0:
                    avisos.append(f"Primas: {ln} no tiene mezcla de ramos para completar su presupuesto; no se completa")
                    continue
                for g, w in (mezcla / mezcla.sum()).items():
                    extra[g] += monto * w * forma[g]
            sig = sig.reindex(columns=GRUPOS, fill_value=0.0) + extra
            # credibilidad del plan: atempera el crecimiento contra el ano en curso
            curso_g = mensual.loc[[x for x in mensual.index if x // 100 == anio]].sum()
            filas = []
            for g in GRUPOS:
                s, c_ = float(sig[g].sum()), float(curso_g.get(g, 0.0))
                crec = s / c_ - 1 if c_ > 0 else None
                if CREDIBILIDAD_PRESUPUESTO != 1 and c_ > 0 and s > 0:
                    G = s / c_
                    sig[g] *= (1 + CREDIBILIDAD_PRESUPUESTO * (G - 1)) / G
                filas.append({"Grupo": g, f"{anio} real + reforecast (M USD)": c_ / 1e6,
                              f"{anio_sig} presupuesto (M USD)": s / 1e6, "Crecimiento": crec,
                              "Completado (M USD)": float(extra[g].sum()) / 1e6})
                if crec is not None and c_ > 5e6 and not (RANGO_CRECIMIENTO_PRIMA[0] <= crec <= RANGO_CRECIMIENTO_PRIMA[1]):
                    avisos.append(f"Primas: el grupo {g} crece {crec:+.0%} en {anio_sig} contra {anio} "
                                  f"({c_ / 1e6:,.1f} -> {s / 1e6:,.1f} M): revisa el presupuesto")
            tablas[f"Presupuesto {anio_sig} contra {anio} por grupo"] = pd.DataFrame(filas)
            # siniestros y comisiones / prima por LN contra el real de los ultimos 12 meses
            ult12 = real[real["periodo"] > _mas(ultimo_real, -12)]
            pr12 = ult12.groupby("ln")[["prima", "siniestros", "comisiones"]].sum()
            ps = pp["tabla"].groupby("ln")[["prima", "siniestros", "comisiones"]].sum()
            filas = []
            for ln in sorted(ps.index):
                a_ = ps.loc[ln]
                b_ = pr12.loc[ln] if ln in pr12.index else None
                fila = {"LN": ln, f"S/P {anio_sig}": a_["siniestros"] / a_["prima"] if a_["prima"] else None,
                        f"C/P {anio_sig}": a_["comisiones"] / a_["prima"] if a_["prima"] else None,
                        "S/P real 12 meses": (b_["siniestros"] / b_["prima"]) if b_ is not None and b_["prima"] else None,
                        "C/P real 12 meses": (b_["comisiones"] / b_["prima"]) if b_ is not None and b_["prima"] else None}
                filas.append(fila)
                if fila[f"S/P {anio_sig}"] is not None and fila["S/P real 12 meses"] is not None \
                        and a_["prima"] > 5e6 and abs(fila[f"S/P {anio_sig}"] - fila["S/P real 12 meses"]) > 0.10:
                    avisos.append(f"Primas: en {ln} la siniestralidad del presupuesto ({fila[f'S/P {anio_sig}']:.0%}) "
                                  f"difiere mas de 10 pts de la real de 12 meses ({fila['S/P real 12 meses']:.0%})")
            tablas[f"Siniestros y comisiones / prima: presupuesto {anio_sig} contra real"] = pd.DataFrame(filas)
            sig.index = [anio_sig * 100 + m for m in sig.index]
            mensual = pd.concat([mensual, sig[GRUPOS]])
            f_sig = pd.DataFrame("presupuesto", index=sig.index, columns=GRUPOS)
            for g in GRUPOS:
                if extra[g].sum() > 0.5 * max(1.0, float(sig[g].sum())):
                    f_sig[g] = "presupuesto completado"
            fuente = pd.concat([fuente, f_sig])
            retenida = p.pivot_table(index="mes", columns="grupo", values="retenida", aggfunc="sum").fillna(0.0)
            retenida.index = [anio_sig * 100 + m for m in retenida.index]
            tiene_sig = True
        except _NoUsable as e:
            avisos.append(f"Primas: {rutas['ppto'].name} no se usa: {e}. Sin prima del ano siguiente el factor no se "
                          "aplica")
            estado["ppto"] = "recortado o incompleto: no se usa"
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Primas: no se pudo usar {rutas['ppto'].name} ({type(e).__name__}: {e})")
            estado["ppto"] = "no se pudo leer: no se usa"
    else:
        avisos.append(f"Primas: sin {pat['ppto']} no hay prima del ano siguiente: el factor de prima no se aplica")

    # meses posteriores al ultimo ano con plan: mismo mes del ano anterior
    ultimo_prima = int(mensual.index.max())
    if tiene_sig and ultimo_prima < periodo_fin:
        extra_meses = _rango(_mas(ultimo_prima, 1), periodo_fin)
        filas = pd.DataFrame([mensual.loc[_mas(p, -12)].to_numpy() for p in extra_meses], index=extra_meses,
                             columns=GRUPOS)
        mensual = pd.concat([mensual, filas])
        fuente = pd.concat([fuente, pd.DataFrame("plan del ano anterior", index=extra_meses, columns=GRUPOS)])
        avisos.append(f"Primas: de {extra_meses[0]} a {periodo_fin} se repite la prima del ano anterior")

    tablas[nombre_archivos] = pd.DataFrame(
        [{**{c: v for c, v in a.items() if not c.startswith("_")},
          "Estado": estado.get(a["_k"], "") if a["_elegido"] else "se ignora (hay uno mas grande)"} for a in archivos])
    mensual = mensual.groupby(level=0).sum().sort_index()
    fuente = fuente[~fuente.index.duplicated(keep="last")].sort_index()
    mensual.index = mensual.index.astype(int)
    fuente.index = fuente.index.astype(int)
    return Primas(mensual=mensual[GRUPOS], fuente=fuente.reindex(mensual.index).fillna("real"),
                  ppto_curso=ppto_curso, sigma_plan=sigma, cobertura=cobertura, ultimo_real=ultimo_real,
                  perfil=perfil, tablas=tablas, controles=controles, avisos=avisos, tiene_siguiente=tiene_sig,
                  retenida=retenida, anio_sig=anio_sig)


def lineas_del_dashboard(ppto: dict | None) -> dict:
    """{LN: prima del ano siguiente} del dashboard del presupuesto (leer_presupuesto de proyeccion_reservas)."""
    return {_ln(ln): v for ln, v in ((ppto or {}).get("prima_ln_siguiente") or {}).items()}


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    lineas = {}
    try:                                   # la misma referencia del dashboard del presupuesto que usa la corrida
        import proyeccion_reservas as _prr
        lineas = lineas_del_dashboard(_prr.leer_presupuesto())
        ultimo_, fin_ = _prr.periodo_ultimo_real(_prr.rango_periodos(_prr.PERIODO_INICIO, _prr.PERIODO_FIN)), _prr.PERIODO_FIN
    except Exception:  # noqa: BLE001
        ultimo_, fin_ = 202608, 202712
    pr = leer_primas(ultimo_, fin_, lineas)
    if pr is None:
        print("No hay archivos de prima real en entradas/.")
    else:
        print("\nCONTROLES POR ARCHIVO")
        for c in pr.controles:
            print(" ", {k: v for k, v in c.items() if v not in ("", None)})
        for nombre, tabla in pr.tablas.items():
            print(f"\n{nombre}")
            print(tabla.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
        print("\nPerfil mensual elegido:", pr.perfil)
        for a in pr.avisos:
            print("AVISO", a)
        print("\nPrima mensual por grupo (M USD), ultimos 24 meses con fuente:")
        m = (pr.mensual / 1e6).round(2)
        m["fuente"] = pr.fuente.apply(lambda f: ", ".join(sorted(set(f))), axis=1)
        print(m.tail(24).to_string())
