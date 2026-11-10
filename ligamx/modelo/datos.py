# -*- coding: utf-8 -*-
"""
Carga de partidos de Liga MX (ESPN) y partición temporal para el arnés de validación.

Todo lo que define QUÉ sabe un modelo y CUÁNDO vive aquí:

  * cargar()      -> todos los partidos con tipos correctos, fechas en UTC y en hora de la Ciudad de
                     México, bloque walk-forward, día, periodo y banderas de calidad.
  * jugados()     -> sólo los partidos con resultado (historial).
  * pendientes()  -> los programados que faltan por jugar.
  * asignar_bloques() -> corte de lunes/viernes 00:00 (hora de la Ciudad de México) de cada partido.

Convenciones de tipos: numérico con faltantes = float64 con NaN (los vacíos del CSV NUNCA se vuelven
cero); numérico sin faltantes = int64; texto faltante = cadena vacía.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent          # .../ligamx
DIR_DATOS = RAIZ / "datos"
RUTA_PARTIDOS = DIR_DATOS / "partidos.csv"
ZONA = "America/Mexico_City"

# --- Protocolo de validación (por torneo) ---------------------------------------------------------
PRIMER_TORNEO_DESARROLLO = "Apertura 2016"
ULTIMO_TORNEO_DESARROLLO = "Clausura 2025"
PERIODOS = ("calentamiento", "desarrollo", "prueba")

# --- Columnas -------------------------------------------------------------------------------------
_COLS_TEXTO = [
    "torneo", "fase", "estado", "local", "visitante", "estadio", "ciudad", "arbitro", "proveedor",
    "hora_local", "serie", "formacion_l", "formacion_v", "ht_fuente", "fase_espn", "estado_espn", "nota",
]
_COLS_ENTERAS = ["id", "anio", "local_id", "visitante_id", "temporada_espn",
                 "tiene_stats", "tiene_eventos", "tiene_alineaciones", "tiene_momios", "tiene_tarjetas"]
_COLS_FECHA = ["fecha_utc", "fecha_local"]
COLS_MOMIOS = ["ml_l", "ml_e", "ml_v", "total_linea", "over", "under",
               "ml_l_abre", "ml_e_abre", "ml_v_abre", "over_abre", "under_abre"]

# Lo ÚNICO que se conoce de un partido antes de jugarse. El arnés entrega a `predecir` sólo estas
# columnas: así ninguna familia puede usar por accidente el resultado o las estadísticas del propio
# partido. Los momios están aquí porque existen antes del silbatazo, pero son posteriores al corte del
# bloque (el cierre se fija al inicio del partido): sólo los modelos de referencia "Mercado" deben
# usarlos; una familia que los use como variable debe declararlo y no sirve para simular rondas futuras.
# `arbitro` se designa días antes, pero ESPN lo publica con el partido: úsese con esa reserva.
COLS_PREPARTIDO = [
    "id", "fecha_utc", "inicio_local", "fecha_local", "hora_local", "dia", "bloque", "corte_bloque",
    "corte_dia", "anio", "torneo", "orden_torneo", "periodo", "fase", "pierna", "serie",
    "local", "visitante", "local_id", "visitante_id", "estadio", "ciudad", "estadio_id", "arbitro",
    *COLS_MOMIOS, "proveedor", "tiene_momios", "momios_dudosos",
]

_cache: dict = {}


# ==================================================================================================
# Torneos y periodos
# ==================================================================================================
def clave_torneo(torneo: str) -> tuple[int, int]:
    """Clave de orden cronológico: (año, 0 = Clausura [ene-may], 1 = Apertura [jul-dic])."""
    tipo, anio = torneo.rsplit(" ", 1)
    return int(anio), (0 if tipo.startswith("Clausura") else 1)


def periodo_de(torneo: str) -> str:
    """calentamiento (hasta Clausura 2016) | desarrollo (Apertura 2016 a Clausura 2025) | prueba."""
    k = clave_torneo(torneo)
    if k < clave_torneo(PRIMER_TORNEO_DESARROLLO):
        return "calentamiento"
    if k <= clave_torneo(ULTIMO_TORNEO_DESARROLLO):
        return "desarrollo"
    return "prueba"


# ==================================================================================================
# Bloques walk-forward
# ==================================================================================================
def asignar_bloques(fecha_utc) -> pd.DataFrame:
    """
    Corte de cada partido en las dos granularidades del protocolo.

    Bloque: los cortes son cada lunes 00:00 y cada viernes 00:00, hora de la Ciudad de México. El bloque
    de un partido es el último corte <= su hora local de inicio (lunes a jueves = jornada de media
    semana; viernes a domingo = jornada de fin de semana). Día: corte a las 00:00 locales del día.

    Devuelve un DataFrame alineado con la entrada: inicio_local (con zona), fecha_local y dia (fecha
    local), bloque (fecha local del corte, 'AAAA-MM-DD'), corte_bloque y corte_dia (instantes en UTC).
    """
    f = pd.DatetimeIndex(pd.to_datetime(fecha_utc, utc=True)).as_unit("ns")
    local = f.tz_convert(ZONA)
    ingenuo = local.tz_localize(None)                   # reloj de pared en CDMX
    dia = ingenuo.normalize()
    ds = np.asarray(ingenuo.dayofweek)                  # lunes = 0 ... domingo = 6
    atras = np.where(ds <= 3, ds, ds - 4)               # días desde el último lunes o viernes
    corte_local = dia - pd.to_timedelta(atras, unit="D")

    def a_utc(ix):
        # La medianoche siempre existe en CDMX (el horario de verano cambiaba a las 02:00).
        return ix.tz_localize(ZONA, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")

    return pd.DataFrame({
        "inicio_local": local,
        "fecha_local": dia,
        "dia": dia.strftime("%Y-%m-%d"),
        "bloque": corte_local.strftime("%Y-%m-%d"),
        "corte_bloque": a_utc(corte_local),
        "corte_dia": a_utc(dia),
    }, index=getattr(fecha_utc, "index", None))


# ==================================================================================================
# Momios capturados en vivo
# ==================================================================================================
def momios_en_vivo(df: pd.DataFrame) -> pd.Series:
    """
    Marca momios de "cierre" que en realidad se capturaron con el partido en juego.

    La regla usa SÓLO los momios (nunca el resultado): favorito por debajo de 1.08, empate por debajo
    de 2.0 o por encima de 12, o en la línea de 2.5 goles un lado por debajo de 1.15. Ningún partido de
    Liga MX abre así antes del silbatazo. En DESARROLLO marca 6 partidos (Bet365, abril de 2024: ids
    692368, 692377, 692383, 692385, 692386 y 692388), p. ej. empate a 1.04 en un 1-1 o local a 151.
    No detecta capturas tempranas con momios todavía verosímiles (ver ARNES.md).
    """
    ml = df[["ml_l", "ml_e", "ml_v"]]
    hay = ml.notna().all(axis=1)
    extremo = (ml.min(axis=1) < 1.08) | (df["ml_e"] < 2.0) | (df["ml_e"] > 12)
    ou = (df["total_linea"] == 2.5) & ((df["over"] < 1.15) | (df["under"] < 1.15))
    return hay & (extremo | ou)


# ==================================================================================================
# Carga
# ==================================================================================================
def cargar(ruta: str | Path | None = None, limpiar_momios: bool = True) -> pd.DataFrame:
    """
    Todos los partidos (jugados, programados, pospuestos y cancelados), ordenados por fecha_utc e id.

    Columnas añadidas a las del CSV (ver datos/COBERTURA.md para el diccionario original):
      fecha_utc (instante UTC), inicio_local (con zona CDMX), fecha_local (fecha local, sin hora),
      dia, bloque, corte_bloque, corte_dia (ver asignar_bloques), orden_torneo (0 = Apertura 2001),
      periodo, resultado (0 gana local, 1 empate, 2 gana visita, a 90 min; NaN si no se jugó),
      escritorio (resultado de escritorio o partido abandonado: queda en el historial marcado),
      evaluable (jugado y no de escritorio: los únicos que califica el arnés),
      momios_dudosos (momios capturados en vivo; con limpiar_momios=True sus momios se vacían).

    Se guarda en memoria por (ruta, fecha de modificación); siempre devuelve una copia.
    """
    ruta = Path(ruta) if ruta else RUTA_PARTIDOS
    llave = (str(ruta), ruta.stat().st_mtime_ns, limpiar_momios)
    if llave in _cache:
        return _cache[llave].copy()

    crudo = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8")
    df = pd.DataFrame(index=crudo.index)
    for c in crudo.columns:
        if c in _COLS_FECHA:
            continue
        if c in _COLS_TEXTO:
            df[c] = crudo[c].astype(str)
        elif c in _COLS_ENTERAS:
            df[c] = crudo[c].astype("int64")
        else:                                           # numérico con faltantes: vacío -> NaN
            df[c] = pd.to_numeric(crudo[c].where(crudo[c] != "", np.nan), errors="raise").astype("float64")

    df["fecha_utc"] = pd.to_datetime(crudo["fecha_utc"], utc=True, format="%Y-%m-%dT%H:%MZ").dt.as_unit("ns")
    df = pd.concat([df, asignar_bloques(df["fecha_utc"])], axis=1)
    distintas = df["dia"] != crudo["fecha_local"]
    if distintas.any():
        raise ValueError(f"fecha_local del CSV no coincide con fecha_utc en {int(distintas.sum())} partidos")

    torneos = sorted(df["torneo"].unique(), key=clave_torneo)
    df["orden_torneo"] = df["torneo"].map({t: i for i, t in enumerate(torneos)}).astype("int64")
    df["periodo"] = df["torneo"].map({t: periodo_de(t) for t in torneos})

    jugado = df["estado"] == "jugado"
    if df.loc[jugado, ["gl", "gv"]].isna().any().any():
        raise ValueError("hay partidos 'jugado' sin marcador")
    df["resultado"] = np.where(jugado, np.where(df["gl"] > df["gv"], 0.0, np.where(df["gl"] == df["gv"], 1.0, 2.0)), np.nan)
    df["escritorio"] = jugado & df["nota"].str.contains("escritorio|abandonado", case=False, regex=True)
    df["evaluable"] = jugado & ~df["escritorio"]

    df["momios_dudosos"] = momios_en_vivo(df)
    if limpiar_momios:
        df.loc[df["momios_dudosos"], COLS_MOMIOS] = np.nan
        df.loc[df["momios_dudosos"], "tiene_momios"] = 0

    df = df.sort_values(["fecha_utc", "id"], kind="mergesort").reset_index(drop=True)
    primero = ["id", "fecha_utc", "inicio_local", "fecha_local", "hora_local", "dia", "bloque", "corte_bloque",
               "corte_dia", "anio", "torneo", "orden_torneo", "periodo", "fase", "pierna", "estado",
               "local", "visitante", "gl", "gv", "resultado", "evaluable", "escritorio"]
    df = df[primero + [c for c in df.columns if c not in primero]]
    _cache.clear()
    _cache[llave] = df
    return df.copy()


def jugados(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Partidos con resultado, en orden cronológico (incluye los de escritorio, marcados)."""
    df = cargar() if df is None else df
    return df[df["estado"] == "jugado"].reset_index(drop=True)


def pendientes(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Partidos programados que faltan por jugar (sólo columnas previas al partido)."""
    df = cargar() if df is None else df
    return df.loc[df["estado"] == "programado", COLS_PREPARTIDO].reset_index(drop=True)


def torneos_de(periodo: str, df: pd.DataFrame | None = None) -> list[str]:
    """Torneos de un periodo, en orden cronológico."""
    df = cargar() if df is None else df
    return sorted(df.loc[df["periodo"] == periodo, "torneo"].unique(), key=clave_torneo)


def columna_corte(granularidad: str) -> str:
    """Nombre de la columna con el corte de cada partido según la granularidad ('bloque' o 'dia')."""
    if granularidad not in ("bloque", "dia"):
        raise ValueError("granularidad debe ser 'bloque' o 'dia'")
    return "corte_bloque" if granularidad == "bloque" else "corte_dia"


if __name__ == "__main__":
    d = cargar()
    j = jugados(d)
    print(f"partidos: {len(d)}  jugados: {len(j)}  pendientes: {len(pendientes(d))}")
    print(j.groupby("periodo").agg(partidos=("id", "size"), evaluables=("evaluable", "sum"),
                                   bloques=("bloque", "nunique"), dias=("dia", "nunique"),
                                   torneos=("torneo", "nunique")).loc[list(PERIODOS[:2])].to_string())
