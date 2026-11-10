# -*- coding: utf-8 -*-
"""
Arnés de validación walk-forward de Cerebro Liga MX.

Todas las familias de modelos implementan la interfaz `Modelo` (ajustar + predecir) y se califican con
`evaluar`, que recorre los bloques en orden cronológico, entrega al modelo SÓLO los partidos jugados
antes del corte, le pide el pronóstico del bloque y guarda una fila por partido en
modelo/pred/<nombre>.parquet. `comparar` arma la tabla pareada (bootstrap de bloques) y `registrar`
lleva la cuenta de las variantes probadas en modelo/registro_variantes.jsonl.

Uso desde la carpeta ligamx/ (ver ARNES.md):
    python3 -m modelo.arnes evaluar modelo.base:PoissonSimple
    python3 -m modelo.arnes comparar poisson_simple cerebro_original_limpio --referencia mercado_cierre_shin
    python3 -m modelo.arnes resumen
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import importlib
import json
import os
import pickle
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import gammaln

from . import datos, metricas

try:                                              # los .parquet de pred/ necesitan pyarrow
    import pyarrow  # noqa: F401
except ImportError as e:                          # pragma: no cover
    raise ImportError("El arnés guarda las predicciones en parquet: instale pyarrow "
                      "(python3 -m pip install --user pyarrow)") from e

DIR_MODELO = Path(__file__).resolve().parent
DIR_PRED = DIR_MODELO / "pred"
DIR_CACHE = DIR_MODELO / "cache"
RUTA_REGISTRO = DIR_MODELO / "registro_variantes.jsonl"
NOMBRE_LOG_PRUEBA = "ACCESOS_PRUEBA.log"

MAX_GOLES = 10                                   # malla de marcadores 0..10 por lado (11 x 11)
_K = np.arange(MAX_GOLES + 1)
_LOGFACT = gammaln(_K + 1.0)
_X, _Y = np.meshgrid(_K, _K, indexing="ij")      # _X = goles del local, _Y = goles de la visita
_GANA_L, _EMPATE, _GANA_V = _X > _Y, _X == _Y, _X < _Y
_TOTAL = _X + _Y
_TOL = 1e-6                                      # tolerancia al validar que las probabilidades sumen 1


# ==================================================================================================
# Interfaz que implementan todas las familias
# ==================================================================================================
class Modelo:
    """
    Interfaz mínima de un modelo de pronóstico.

    nombre           identificador único de la variante (nombre del archivo de predicciones).
    familia          familia a la que pertenece (para contar variantes en el registro).
    hiperparametros  dict serializable con lo que define a la variante.

    ajustar(hist, corte): `hist` son TODOS los partidos jugados con fecha_utc < corte (DataFrame de
        datos.cargar(), en orden cronológico; incluye resultados de escritorio marcados en la columna
        `escritorio`); `corte` es un pd.Timestamp en UTC. Se llama cientos de veces: el modelo puede
        guardar estado para calentar el ajuste siguiente, y decidir no reajustar en cada llamada.
    predecir(partidos): `partidos` trae sólo columnas previas al partido (datos.COLS_PREPARTIDO).
        Devuelve una lista con un dict por partido, en el mismo orden:
          {"lam_l", "lam_v", "rho"}   medias de goles y correlación Dixon-Coles (rho opcional, 0 por
                                       omisión): el arnés arma la matriz 11x11 y renormaliza; o
          {"M": matriz 11x11}          M[x, y] = P(local x, visita y), suma 1 (lam_l/lam_v opcionales); o
          {"p1x2": [pl, pe, pv]}       sólo 1X2 (no entra en las métricas de marcador); o
          None                         sin pronóstico para ese partido (se omite la fila).
        Si vienen M o las lambdas, el 1X2 sale SIEMPRE de la matriz (un "p1x2" adicional se ignora): así
        el resultado, el marcador y los totales de un modelo son coherentes entre sí. Para dar matriz a
        un 1X2 que se calculó aparte, use ajustar_M_a_1x2.
        Claves extra que empiecen con "x_" y sean numéricas se guardan como columnas.
    """
    nombre: str = "sin_nombre"
    familia: str = "sin_familia"
    hiperparametros: dict = {}

    def ajustar(self, hist: pd.DataFrame, corte: pd.Timestamp) -> None:
        raise NotImplementedError

    def predecir(self, partidos: pd.DataFrame) -> list:
        raise NotImplementedError


# ==================================================================================================
# Matriz de marcadores y mercados derivados
# ==================================================================================================
def matrices_marcadores(lam_l, lam_v, rho=0.0) -> np.ndarray:
    """
    Matrices (n, 11, 11) de P(local x, visita y): Poisson independientes con la corrección de
    Dixon-Coles en los marcadores 0-0, 0-1, 1-0 y 1-1, truncadas en 10 goles y renormalizadas.
    tau(0,0) = 1 - lam_l*lam_v*rho; tau(0,1) = 1 + lam_l*rho; tau(1,0) = 1 + lam_v*rho; tau(1,1) = 1 - rho.
    """
    lam_l = np.atleast_1d(np.asarray(lam_l, float))
    lam_v = np.atleast_1d(np.asarray(lam_v, float))
    rho = np.broadcast_to(np.asarray(rho, float), lam_l.shape)
    if not (np.isfinite(lam_l).all() and np.isfinite(lam_v).all() and np.isfinite(rho).all()):
        raise ValueError("lam_l, lam_v y rho deben ser finitos")
    if (lam_l <= 0).any() or (lam_v <= 0).any():
        raise ValueError("lam_l y lam_v deben ser positivos")
    pl = np.exp(_K[None, :] * np.log(lam_l)[:, None] - lam_l[:, None] - _LOGFACT[None, :])
    pv = np.exp(_K[None, :] * np.log(lam_v)[:, None] - lam_v[:, None] - _LOGFACT[None, :])
    M = pl[:, :, None] * pv[:, None, :]
    M[:, 0, 0] *= np.clip(1.0 - lam_l * lam_v * rho, 1e-10, None)
    M[:, 0, 1] *= np.clip(1.0 + lam_l * rho, 1e-10, None)
    M[:, 1, 0] *= np.clip(1.0 + lam_v * rho, 1e-10, None)
    M[:, 1, 1] *= np.clip(1.0 - rho, 1e-10, None)
    return M / M.sum(axis=(1, 2), keepdims=True)


def matriz_marcadores(lam_l: float, lam_v: float, rho: float = 0.0) -> np.ndarray:
    """Matriz 11x11 de un partido (ver matrices_marcadores)."""
    return matrices_marcadores([lam_l], [lam_v], rho)[0]


def _lote(M) -> tuple[np.ndarray, bool]:
    M = np.asarray(M, float)
    return (M[None], True) if M.ndim == 2 else (M, False)


def p1x2(M) -> np.ndarray:
    """[P(gana local), P(empate), P(gana visita)] de una matriz (o de un lote (n, 11, 11))."""
    L, uno = _lote(M)
    P = np.stack([(L * _GANA_L).sum(axis=(1, 2)), (L * _EMPATE).sum(axis=(1, 2)), (L * _GANA_V).sum(axis=(1, 2))], axis=1)
    return P[0] if uno else P


def goles_esperados(M) -> np.ndarray:
    """[E(goles local), E(goles visita)] de una matriz o lote."""
    L, uno = _lote(M)
    E = np.stack([(L * _X).sum(axis=(1, 2)), (L * _Y).sum(axis=(1, 2))], axis=1)
    return E[0] if uno else E


def dist_total(M) -> np.ndarray:
    """Distribución del total de goles (0 a 20) de una matriz o lote."""
    L, uno = _lote(M)
    D = np.stack([(L * (_TOTAL == t)).sum(axis=(1, 2)) for t in range(2 * MAX_GOLES + 1)], axis=1)
    return D[0] if uno else D


def p_over(M, linea: float = 2.5):
    """P(total de goles > linea)."""
    L, uno = _lote(M)
    p = (L * (_TOTAL > linea)).sum(axis=(1, 2))
    return float(p[0]) if uno else p


def p_ambos_anotan(M):
    """P(los dos equipos anotan al menos un gol)."""
    L, uno = _lote(M)
    p = L[:, 1:, 1:].sum(axis=(1, 2))
    return float(p[0]) if uno else p


def top_marcadores(M, k: int = 5) -> list[tuple[int, int, float]]:
    """Los k marcadores más probables de UNA matriz: [(goles_local, goles_visita, probabilidad), ...]."""
    M = np.asarray(M, float)
    orden = np.argsort(-M, axis=None, kind="mergesort")[:k]
    return [(int(i // M.shape[1]), int(i % M.shape[1]), float(M.flat[i])) for i in orden]


def marcador_mas_probable(M) -> tuple[int, int, float]:
    """(goles_local, goles_visita, probabilidad) del marcador más probable de UNA matriz."""
    return top_marcadores(M, 1)[0]


def ajustar_M_a_1x2(M, p) -> np.ndarray:
    """
    Reescala las tres regiones de la matriz (gana local, empate, gana visita) para que su 1X2 sea
    exactamente `p`, conservando la forma dentro de cada región. Sirve para dar una matriz coherente a
    un modelo que sólo produce 1X2 (o a un ensamble de 1X2) a partir de una matriz base.
    """
    M = np.asarray(M, float)
    p = np.asarray(p, float)
    q = p1x2(M)
    if (q <= 0).any():
        raise ValueError("la matriz base tiene una región con probabilidad cero")
    R = M * (_GANA_L * (p[0] / q[0]) + _EMPATE * (p[1] / q[1]) + _GANA_V * (p[2] / q[2]))
    return R / R.sum()


def mercados(M) -> dict:
    """Mercados derivados de UNA matriz de marcadores (todo sale de la misma matriz: es coherente)."""
    M = np.asarray(M, float)
    pl, pe, pv = (float(x) for x in p1x2(M))
    el, ev = (float(x) for x in goles_esperados(M))
    x, y, pm = marcador_mas_probable(M)
    return {
        "p_l": pl, "p_e": pe, "p_v": pv,
        "p_local_o_empate": pl + pe, "p_empate_o_visita": pe + pv, "p_sin_empate": pl + pv,
        "goles_l": el, "goles_v": ev,
        "p_over15": p_over(M, 1.5), "p_over25": p_over(M, 2.5), "p_over35": p_over(M, 3.5),
        "p_ambos": p_ambos_anotan(M),
        "marcador_probable": f"{x}-{y}", "p_marcador_probable": pm,
        "top_marcadores": [(f"{a}-{b}", q) for a, b, q in top_marcadores(M, 5)],
    }


# ==================================================================================================
# Normalización de lo que devuelve un modelo
# ==================================================================================================
def _normalizar(pr) -> tuple[np.ndarray, np.ndarray | None, float, float, dict] | None:
    """Convierte el dict de un partido en (P 1X2, M o None, lam_l, lam_v, extras); None = sin pronóstico."""
    if pr is None:
        return None
    if not isinstance(pr, dict):
        raise TypeError("predecir debe devolver un dict por partido (o None)")
    extras = {k: float(v) for k, v in pr.items()
              if k.startswith("x_") and isinstance(v, (int, float, np.integer, np.floating))}
    M = None
    if pr.get("M") is not None:
        M = np.array(pr["M"], dtype=float)
        if M.shape != (MAX_GOLES + 1, MAX_GOLES + 1):
            raise ValueError(f"M debe ser {MAX_GOLES + 1}x{MAX_GOLES + 1}; llegó {M.shape}")
        if not np.isfinite(M).all() or M.min() < -1e-12 or abs(M.sum() - 1.0) > _TOL:
            raise ValueError(f"M debe ser finita, no negativa y sumar 1 (suma = {M.sum():.8f})")
        M = np.clip(M, 0.0, None)
        M = M / M.sum()
    elif pr.get("lam_l") is not None and pr.get("lam_v") is not None:
        M = matriz_marcadores(float(pr["lam_l"]), float(pr["lam_v"]), float(pr.get("rho") or 0.0))
    if M is not None:
        P = p1x2(M)
        E = goles_esperados(M)
        lam_l = float(pr["lam_l"]) if pr.get("lam_l") is not None else float(E[0])
        lam_v = float(pr["lam_v"]) if pr.get("lam_v") is not None else float(E[1])
        return P, M, lam_l, lam_v, extras
    if pr.get("p1x2") is not None:
        P = np.array(pr["p1x2"], dtype=float).ravel()
        if P.shape != (3,) or not np.isfinite(P).all() or P.min() < 0 or abs(P.sum() - 1.0) > _TOL:
            raise ValueError(f"p1x2 debe tener 3 probabilidades que sumen 1; llegó {P}")
        return P / P.sum(), None, np.nan, np.nan, extras
    raise ValueError("cada pronóstico necesita lam_l y lam_v, o M, o p1x2")


def _filas(previos: pd.DataFrame, preds: list, corte: pd.Timestamp) -> tuple[list[dict], list[np.ndarray]]:
    """Filas de salida (una por partido con pronóstico) y sus matrices (o None)."""
    if not isinstance(preds, (list, tuple)) or len(preds) != len(previos):
        raise ValueError(f"predecir devolvió {len(preds) if hasattr(preds, '__len__') else '?'} "
                         f"pronósticos para {len(previos)} partidos")
    filas, mats = [], []
    for (_, p), pr in zip(previos.iterrows(), preds):
        n = _normalizar(pr)
        if n is None:
            continue
        P, M, lam_l, lam_v, extras = n
        f = {"id": int(p["id"]), "fecha_utc": p["fecha_utc"], "torneo": p["torneo"], "fase": p["fase"],
             "pierna": p["pierna"], "local": p["local"], "visitante": p["visitante"],
             "bloque": p["bloque"], "dia": p["dia"], "corte": corte,
             "p_l": float(P[0]), "p_e": float(P[1]), "p_v": float(P[2]), "lam_l": lam_l, "lam_v": lam_v}
        if M is not None:
            x, y, pm = marcador_mas_probable(M)
            f.update({"p_over15": p_over(M, 1.5), "p_over25": p_over(M, 2.5), "p_over35": p_over(M, 3.5),
                      "p_ambos": p_ambos_anotan(M), "marcador_probable": f"{x}-{y}", "p_marcador_probable": pm})
        else:
            f.update({"p_over15": np.nan, "p_over25": np.nan, "p_over35": np.nan, "p_ambos": np.nan,
                      "marcador_probable": "", "p_marcador_probable": np.nan})
        f.update(extras)
        filas.append(f)
        mats.append(M)
    return filas, mats


# ==================================================================================================
# Archivos
# ==================================================================================================
def _nombre_valido(nombre: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", nombre or ""):
        raise ValueError(f"nombre de modelo inválido: {nombre!r} (use letras, números, '_', '-' o '.')")
    return nombre


def ruta_pred(nombre: str, periodo: str = "desarrollo", granularidad: str = "bloque",
              parcial: bool = False, dir_pred: str | Path | None = None) -> Path:
    """
    Ruta del archivo de predicciones: <nombre>.parquet para desarrollo por bloque; con sufijos
    __<periodo>, __dia y __parcial (evaluación sobre un subconjunto) en los demás casos.
    """
    suf = ("" if periodo == "desarrollo" else f"__{periodo}") + ("" if granularidad == "bloque" else f"__{granularidad}")
    suf += "__parcial" if parcial else ""
    return Path(dir_pred or DIR_PRED) / f"{_nombre_valido(nombre)}{suf}.parquet"


def leer_pred(nombre: str, periodo: str = "desarrollo", granularidad: str = "bloque",
              parcial: bool = False, dir_pred: str | Path | None = None) -> pd.DataFrame:
    """Lee las predicciones guardadas de un modelo (leer las de PRUEBA también queda en el registro de accesos)."""
    if periodo == "prueba":
        _acceso_prueba(dir_pred, "leer", nombre, granularidad=granularidad)
    return pd.read_parquet(ruta_pred(nombre, periodo, granularidad, parcial, dir_pred))


def leer_matrices(nombre: str, periodo: str = "desarrollo", granularidad: str = "bloque",
                  parcial: bool = False, dir_cache: str | Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(ids, matrices (n, 11, 11) en float64 renormalizadas) guardadas por evaluar; para ensambles."""
    r = Path(dir_cache or DIR_CACHE) / ("M_" + ruta_pred(nombre, periodo, granularidad, parcial).stem + ".npz")
    z = np.load(r)
    M = z["M"].astype(float)
    return z["id"], M / M.sum(axis=(1, 2), keepdims=True)


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    return str(o)


def _anexar(ruta: Path, linea: str) -> None:
    """Agrega una línea a un archivo con candado (varios agentes escriben a la vez)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(linea.rstrip("\n") + "\n")
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)


def _ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==================================================================================================
# Registro de variantes
# ==================================================================================================
def registrar(nombre: str, familia: str, hiperparametros: dict, metricas_: dict,
              ruta: str | Path | None = None, **extra) -> dict:
    """
    Anota una variante probada en modelo/registro_variantes.jsonl (una línea JSON por evaluación).
    Elegir entre muchas variantes mirando el mismo periodo sesga a favor de la elegida: este registro
    permite decir cuántas se probaron. `evaluar` lo llama solo; úsese a mano si una variante se
    califica por otra vía.
    """
    reg = {"fecha": _ahora(), "nombre": nombre, "familia": familia,
           "hiperparametros": hiperparametros or {}, "metricas": metricas_ or {}, **extra}
    _anexar(Path(ruta or RUTA_REGISTRO), json.dumps(reg, ensure_ascii=False, default=_json, sort_keys=True))
    return reg


def leer_registro(ruta: str | Path | None = None) -> pd.DataFrame:
    """Registro de variantes como tabla (una fila por evaluación registrada)."""
    ruta = Path(ruta or RUTA_REGISTRO)
    if not ruta.is_file():
        return pd.DataFrame()
    with open(ruta, encoding="utf-8") as f:
        regs = [json.loads(l) for l in f if l.strip()]
    t = pd.json_normalize(regs, max_level=1)
    return t


# ==================================================================================================
# Evaluación walk-forward
# ==================================================================================================
def cortes(periodo: str = "desarrollo", granularidad: str = "bloque", df: pd.DataFrame | None = None,
           torneos: list[str] | None = None, desde=None, hasta=None) -> pd.DataFrame:
    """
    Partidos evaluables del periodo con su corte (columna `corte`), en orden. No da acceso a nada que
    `evaluar` no dé; sirve para que una familia sepa de antemano cuántos cortes hay.
    """
    df = datos.cargar() if df is None else df
    jug = datos.jugados(df)
    m = (jug["periodo"] == periodo) & jug["evaluable"]
    if torneos is not None:
        m &= jug["torneo"].isin(list(torneos))
    if desde is not None:
        m &= jug["fecha_utc"] >= pd.Timestamp(desde, tz="UTC")
    if hasta is not None:
        m &= jug["fecha_utc"] < pd.Timestamp(hasta, tz="UTC")
    obj = jug[m].copy()
    obj["corte"] = obj[datos.columna_corte(granularidad)]
    return obj


def _candado(hist: pd.DataFrame, corte: pd.Timestamp, bloque: pd.DataFrame) -> None:
    """
    Candado contra fugas, en tiempo de ejecución: el historial sólo trae partidos jugados con fecha_utc
    anterior al corte, y ningún partido a pronosticar es anterior al corte ni está en el historial.
    """
    if len(hist) and not (hist["fecha_utc"].iloc[-1] < corte and hist["fecha_utc"].max() < corte):
        raise AssertionError(f"fuga: el historial contiene partidos del {hist['fecha_utc'].max()} (corte {corte})")
    if len(hist) and not (hist["estado"] == "jugado").all():
        raise AssertionError("fuga: el historial contiene partidos no jugados")
    if not (bloque["fecha_utc"] >= corte).all():
        raise AssertionError(f"fuga: hay partidos a pronosticar anteriores al corte {corte}")
    if len(hist) and np.isin(bloque["id"].to_numpy(), hist["id"].to_numpy()).any():
        raise AssertionError("fuga: un partido a pronosticar está en el historial")


def _acceso_prueba(dir_pred, accion: str, nombre: str, quien: str | None = None, **datos_extra) -> None:
    """Deja constancia en pred/ACCESOS_PRUEBA.log de quién miró la PRUEBA, cuándo y con qué modelo."""
    quien = quien or os.environ.get("AGENTE") or os.environ.get("USER") or "desconocido"
    extra = "".join(f"\t{k}={v}" for k, v in datos_extra.items())
    _anexar(Path(dir_pred or DIR_PRED) / NOMBRE_LOG_PRUEBA,
            f"{_ahora()}\taccion={accion}\tquien={quien}\tmodelo={nombre}{extra}\tpid={os.getpid()}"
            f"\targv={' '.join(sys.argv)}")


def evaluar(modelo: Modelo, periodo: str = "desarrollo", granularidad: str = "bloque", *,
            permitir_prueba: bool = False, torneos: list[str] | None = None, desde=None, hasta=None,
            guardar: bool = True, guardar_matrices: bool = True, registrar_variante: bool = True,
            dir_pred: str | Path | None = None, dir_cache: str | Path | None = None,
            ruta_registro: str | Path | None = None, quien: str | None = None,
            reanudar: bool = False, cada: int = 20,
            df: pd.DataFrame | None = None, verbose: bool = True) -> pd.DataFrame:
    """
    Recorre el periodo en orden cronológico: para cada corte ajusta el modelo con los partidos jugados
    ANTES del corte, pronostica los partidos del bloque y los califica contra el resultado a 90 minutos.

    periodo        'desarrollo' (por omisión), 'calentamiento' o 'prueba'. La PRUEBA exige
                   permitir_prueba=True y deja constancia en pred/ACCESOS_PRUEBA.log.
    granularidad   'bloque' (cortes lunes y viernes 00:00 CDMX) o 'dia' (corte al inicio de cada día).
    torneos, desde, hasta   subconjunto para iterar rápido (el archivo se guarda con sufijo __parcial).
    reanudar, cada          para modelos lentos: guarda un punto de control en cache/ cada `cada` cortes y,
                   si la corrida se interrumpe, la siguiente llamada idéntica retoma donde se quedó. Supone
                   que el resultado de `ajustar` no depende de las llamadas anteriores (el estado guardado
                   sólo sirve para arrancar más rápido); el punto de control se invalida si cambian el
                   nombre, los hiperparámetros, los partidos a evaluar o los datos.
    Devuelve (y guarda en modelo/pred/) una fila por partido: id, fecha_utc, torneo, fase, pierna, local,
    visitante, bloque, dia, corte, p_l, p_e, p_v, lam_l, lam_v, p_over15, p_over25, p_over35, p_ambos,
    marcador_probable, p_marcador_probable, gl, gv, resultado, logp_marcador. Las matrices 11x11 quedan
    en modelo/cache/M_<archivo>.npz (leer_matrices). Cada corrida se anota en el registro de variantes.
    """
    if periodo not in datos.PERIODOS:
        raise ValueError(f"periodo debe ser uno de {datos.PERIODOS}")
    nombre = _nombre_valido(getattr(modelo, "nombre", ""))
    dir_pred = Path(dir_pred or DIR_PRED)
    df = datos.cargar() if df is None else df
    jug = datos.jugados(df)
    obj = cortes(periodo, granularidad, df, torneos, desde, hasta)
    parcial = torneos is not None or desde is not None or hasta is not None

    if (obj["periodo"] == "prueba").any() or periodo == "prueba":
        if not permitir_prueba:
            raise PermissionError(
                "La PRUEBA (Apertura 2025 en adelante) sólo la mira el agente de selección, una vez y con "
                "candidatos declarados de antemano. Si es el caso, llame con permitir_prueba=True.")
        _acceso_prueba(dir_pred, "evaluar", nombre, quien, periodo=periodo, granularidad=granularidad,
                       partidos=len(obj), parcial=parcial)

    f_ns = jug["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
    filas, mats = [], []
    t_aj = t_pr = 0.0
    t0 = time.time()
    grupos = list(obj.groupby("corte", sort=True))

    # --- punto de control para modelos lentos: se retoma donde se quedó una corrida interrumpida ---
    control = Path(dir_cache or DIR_CACHE) / f"reanudar_{ruta_pred(nombre, periodo, granularidad, parcial).stem}.pkl"
    firma = json.dumps({"nombre": nombre, "hiper": getattr(modelo, "hiperparametros", {}), "periodo": periodo,
                        "granularidad": granularidad, "ids": obj["id"].tolist(),
                        "datos": int(jug["gl"].sum() * 1000 + jug["gv"].sum())}, default=_json, sort_keys=True)
    hechos = 0
    if reanudar and control.is_file():
        with open(control, "rb") as fh:
            guardado = pickle.load(fh)
        if guardado.get("firma") == firma:
            filas, mats, hechos = guardado["filas"], guardado["mats"], guardado["hechos"]
            t_aj, t_pr = guardado["t_aj"], guardado["t_pr"]
            if verbose:
                print(f"  [{nombre}] se retoma en el corte {hechos + 1}/{len(grupos)}", flush=True)

    for i, (corte, g) in enumerate(grupos, start=1):
        if i <= hechos:
            continue
        k = int(np.searchsorted(f_ns, corte.value, side="left"))        # partidos con fecha_utc < corte
        hist = jug.iloc[:k]
        _candado(hist, corte, g)
        t = time.time()
        modelo.ajustar(hist, corte)
        t_aj += time.time() - t
        previos = g[datos.COLS_PREPARTIDO].reset_index(drop=True)
        t = time.time()
        preds = modelo.predecir(previos)
        t_pr += time.time() - t
        fb, mb = _filas(previos, preds, corte)
        filas += fb
        mats += mb
        if verbose and (i % 100 == 0 or i == len(grupos)):
            print(f"  [{nombre}] corte {i}/{len(grupos)}  {corte:%Y-%m-%d}  {time.time() - t0:6.1f} s", flush=True)
        if reanudar and (i % max(int(cada), 1) == 0) and i < len(grupos):
            control.parent.mkdir(parents=True, exist_ok=True)
            temporal = control.with_name(f".{control.name}.{os.getpid()}.tmp")
            with open(temporal, "wb") as fh:
                pickle.dump({"firma": firma, "filas": filas, "mats": mats, "hechos": i, "t_aj": t_aj, "t_pr": t_pr}, fh)
            os.replace(temporal, control)
    if reanudar and control.is_file():
        control.unlink()                                                 # corrida completa: ya no hace falta

    pred = pd.DataFrame(filas)
    if len(pred):
        real = obj.set_index("id")[["gl", "gv", "resultado"]]
        pred["gl"] = real["gl"].reindex(pred["id"]).to_numpy().astype("int64")
        pred["gv"] = real["gv"].reindex(pred["id"]).to_numpy().astype("int64")
        pred["resultado"] = real["resultado"].reindex(pred["id"]).to_numpy().astype("int64")
        con_m = np.array([m is not None for m in mats])
        logp = np.full(len(pred), np.nan)
        if con_m.any():
            lote = np.stack([m for m in mats if m is not None])
            logp[con_m] = metricas.logv_marcador(lote, pred["gl"].to_numpy()[con_m], pred["gv"].to_numpy()[con_m])
        pred["logp_marcador"] = logp
        orden = np.lexsort((pred["id"].to_numpy(), pred["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")))
        pred = pred.iloc[orden].reset_index(drop=True)
        mats = [mats[j] for j in orden]

    res = metricas.resumen(pred, con_ee=True)
    res.update({"n_cortes": len(grupos), "n_sin_pronostico": int(len(obj) - len(pred)),
                "seg_ajustar": round(t_aj, 2), "seg_predecir": round(t_pr, 2)})
    if guardar and len(pred) == 0:
        print(f"  [{nombre}] sin pronósticos en {periodo}: no se guarda archivo", flush=True)
    elif guardar:
        dir_pred.mkdir(parents=True, exist_ok=True)
        destino = ruta_pred(nombre, periodo, granularidad, parcial, dir_pred)
        temporal = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
        pred.to_parquet(temporal, index=False)          # escritura atómica: otro agente nunca lee un archivo a medias
        os.replace(temporal, destino)
        if guardar_matrices and any(m is not None for m in mats):
            dc = Path(dir_cache or DIR_CACHE)
            dc.mkdir(parents=True, exist_ok=True)
            con = [j for j, m in enumerate(mats) if m is not None]
            np.savez_compressed(dc / f"M_{destino.stem}.npz", id=pred["id"].to_numpy()[con],
                                M=np.stack([mats[j] for j in con]).astype(np.float32))
    if registrar_variante:
        registrar(nombre, getattr(modelo, "familia", "sin_familia"), getattr(modelo, "hiperparametros", {}),
                  res, ruta=ruta_registro, periodo=periodo, granularidad=granularidad, parcial=parcial,
                  torneos=list(torneos) if torneos is not None else None,
                  desde=str(desde) if desde is not None else None, hasta=str(hasta) if hasta is not None else None)
    if verbose and len(pred):
        print(f"  [{nombre}] {periodo}/{granularidad}: n={res['n']}  log-loss={res['logloss']:.4f}  "
              f"RPS={res['rps']:.4f}  Brier={res['brier']:.4f}  logv marcador={res['logv_marcador']:.4f}  "
              f"acierto={res['acierto']:.3f}  ({t_aj:.1f} s ajustar, {t_pr:.1f} s predecir)", flush=True)
    pred.attrs["resumen"] = res
    return pred


def pronosticar(modelo: Modelo, partidos: pd.DataFrame | None = None, granularidad: str = "dia",
                df: pd.DataFrame | None = None) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Pronóstico de partidos POR JUGAR (por omisión, todos los pendientes): para cada corte ajusta con
    todo lo jugado antes y predice. Devuelve (tabla como la de evaluar pero sin resultado, matrices
    (n, 11, 11) con NaN donde el modelo sólo da 1X2). No califica nada ni toca el registro.
    """
    df = datos.cargar() if df is None else df
    jug = datos.jugados(df)
    partidos = datos.pendientes(df) if partidos is None else partidos
    col = datos.columna_corte(granularidad)
    f_ns = jug["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
    filas, mats = [], []
    for corte, g in partidos.groupby(col, sort=True):
        k = int(np.searchsorted(f_ns, corte.value, side="left"))
        hist = jug.iloc[:k]
        _candado(hist, corte, g)
        modelo.ajustar(hist, corte)
        previos = g[datos.COLS_PREPARTIDO].reset_index(drop=True)
        fb, mb = _filas(previos, modelo.predecir(previos), corte)
        filas += fb
        mats += mb
    vacia = np.full((MAX_GOLES + 1, MAX_GOLES + 1), np.nan)
    return pd.DataFrame(filas), (np.stack([vacia if m is None else m for m in mats]) if mats else np.empty((0, 11, 11)))


# ==================================================================================================
# Comparación pareada y resumen
# ==================================================================================================
def _tabla(x, periodo, granularidad, dir_pred) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else leer_pred(x, periodo, granularidad, dir_pred=dir_pred)


def comparar(nombres, referencia=None, periodo: str = "desarrollo", granularidad: str = "bloque",
             dir_pred: str | Path | None = None, B: int = metricas.B_BOOTSTRAP,
             semilla: int = metricas.SEMILLA) -> pd.DataFrame:
    """
    Tabla pareada de cada modelo contra la referencia (por omisión, el primero de la lista), sólo sobre
    los partidos que ambos pronosticaron. `nombres` es una lista de nombres guardados en pred/ o un dict
    {nombre: tabla de predicciones}. Diferencias = modelo - referencia: en log-loss, RPS y Brier,
    negativo = el modelo es mejor; en logv (log-verosimilitud del marcador), positivo = mejor.
    ee_* es el error estándar por bootstrap de bloques (semilla fija); ic95_* el intervalo de 95% del
    log-loss; z_ll = d_ll / ee_ll.
    """
    tablas = dict(nombres) if isinstance(nombres, dict) else {n: n for n in nombres}
    if referencia is None:
        referencia = next(iter(tablas))
    elif referencia not in tablas:
        tablas[referencia] = referencia
    ref = metricas.metricas_por_partido(_tabla(tablas[referencia], periodo, granularidad, dir_pred)).set_index("id")
    filas = []
    for nombre, x in tablas.items():
        if nombre == referencia:
            continue
        mod = metricas.metricas_por_partido(_tabla(x, periodo, granularidad, dir_pred)).set_index("id")
        ids = mod.index.intersection(ref.index)
        a, b = mod.loc[ids], ref.loc[ids]
        fila = {"modelo": nombre, "referencia": referencia, "n": len(ids)}
        if len(ids):
            bl = a["bloque"].to_numpy()
            d = metricas.diferencia_pareada(a["ll"], b["ll"], bl, B, semilla)
            fila.update({"ll_modelo": a["ll"].mean(), "ll_ref": b["ll"].mean(), "d_ll": d["dif"], "ee_ll": d["ee"],
                         "ic95_inf": d["ic_inf"], "ic95_sup": d["ic_sup"], "z_ll": d["z"]})
            for met in ("rps", "brier"):
                d = metricas.diferencia_pareada(a[met], b[met], bl, B, semilla)
                fila.update({f"d_{met}": d["dif"], f"ee_{met}": d["ee"]})
            ok = (np.isfinite(a["logp_marcador"]) & np.isfinite(b["logp_marcador"])).to_numpy()
            fila["n_marcador"] = int(ok.sum())
            if ok.any():
                d = metricas.diferencia_pareada(a["logp_marcador"][ok], b["logp_marcador"][ok], bl[ok], B, semilla)
                fila.update({"d_logv": d["dif"], "ee_logv": d["ee"]})
            fila.update({"acierto_modelo": a["acierto"].mean(), "acierto_ref": b["acierto"].mean()})
        filas.append(fila)
    return pd.DataFrame(filas)


def resumen(periodo: str = "desarrollo", granularidad: str = "bloque", dir_pred: str | Path | None = None,
            nombres: list[str] | None = None) -> pd.DataFrame:
    """
    Métricas de cada modelo guardado en pred/ sobre SUS partidos (n puede diferir entre modelos: para
    comparar use `comparar`). Columnas: modelo, n, logloss, ee_logloss, rps, brier, logv_marcador, acierto.
    """
    dir_pred = Path(dir_pred or DIR_PRED)
    if nombres is None:
        suf = ruta_pred("x", periodo, granularidad).stem[1:]
        nombres = []
        for r in sorted(dir_pred.glob("*.parquet")):
            base = r.stem
            if suf:
                if base.endswith(suf):
                    nombres.append(base[: -len(suf)])
            elif "__" not in base:
                nombres.append(base)
    filas = []
    for n in nombres:
        r = metricas.resumen(leer_pred(n, periodo, granularidad, dir_pred=dir_pred), con_ee=True)
        filas.append({"modelo": n, **{k: r.get(k) for k in ("n", "logloss", "ee_logloss", "rps", "brier",
                                                              "logv_marcador", "acierto")}})
    t = pd.DataFrame(filas)
    return t.sort_values("logloss").reset_index(drop=True) if len(t) else t


def desglose(nombre: str, por: str = "torneo", periodo: str = "desarrollo", granularidad: str = "bloque",
             dir_pred: str | Path | None = None) -> pd.DataFrame:
    """
    Métricas de un modelo guardado partidas por `por`: 'torneo', 'fase', 'anio' o cualquier columna de la
    tabla de predicciones. Sirve para ver si una mejora es pareja o viene de un solo tramo.
    """
    m = metricas.metricas_por_partido(leer_pred(nombre, periodo, granularidad, dir_pred=dir_pred))
    if por == "anio":
        m["anio"] = m["fecha_utc"].dt.tz_convert(datos.ZONA).dt.year
    t = m.groupby(por, sort=False).agg(n=("ll", "size"), logloss=("ll", "mean"), rps=("rps", "mean"),
                                       brier=("brier", "mean"), logv_marcador=("logp_marcador", "mean"),
                                       acierto=("acierto", "mean")).reset_index()
    return t


def calibracion(nombre: str, periodo: str = "desarrollo", granularidad: str = "bloque",
                por_clase: bool = False, dir_pred: str | Path | None = None) -> pd.DataFrame:
    """Tabla de calibración por deciles de un modelo guardado."""
    p = leer_pred(nombre, periodo, granularidad, dir_pred=dir_pred)
    return metricas.calibracion_deciles(p[["p_l", "p_e", "p_v"]].to_numpy(), p["resultado"].to_numpy(), por_clase=por_clase)


# ==================================================================================================
# Línea de comandos
# ==================================================================================================
def instanciar(espec: str, kw: dict | None = None) -> Modelo:
    """Crea un modelo desde 'paquete.modulo:Clase' y un dict de argumentos del constructor."""
    if ":" not in espec:
        raise ValueError("el modelo se indica como modulo:Clase, p. ej. modelo.base:PoissonSimple")
    mod, clase = espec.split(":", 1)
    return getattr(importlib.import_module(mod), clase)(**(kw or {}))


def _imprimir(t: pd.DataFrame) -> None:
    with pd.option_context("display.width", 250, "display.max_columns", 40, "display.float_format", "{:.4f}".format):
        print(t.to_string(index=False) if len(t) else "(sin filas)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m modelo.arnes", description="Arnés de validación walk-forward")
    sub = ap.add_subparsers(dest="orden", required=True)

    def comunes(p):
        p.add_argument("--periodo", default="desarrollo", choices=datos.PERIODOS)
        p.add_argument("--granularidad", default="bloque", choices=("bloque", "dia"))

    e = sub.add_parser("evaluar", help="recorre el periodo con un modelo y guarda sus predicciones")
    e.add_argument("modelo", help="modulo:Clase, p. ej. modelo.base:PoissonSimple")
    comunes(e)
    e.add_argument("--kw", default="{}", help="JSON con los argumentos del constructor")
    e.add_argument("--torneos", default=None, help="lista separada por comas (evaluación parcial)")
    e.add_argument("--desde", default=None, help="fecha UTC inicial (evaluación parcial)")
    e.add_argument("--hasta", default=None, help="fecha UTC final, excluida (evaluación parcial)")
    e.add_argument("--permitir-prueba", action="store_true", help="sólo el agente de selección")
    e.add_argument("--quien", default=None, help="quién pide la PRUEBA (queda en ACCESOS_PRUEBA.log)")
    e.add_argument("--no-guardar", action="store_true")
    e.add_argument("--reanudar", action="store_true", help="retoma una corrida interrumpida (modelos lentos)")

    c = sub.add_parser("comparar", help="tabla pareada contra una referencia")
    c.add_argument("nombres", nargs="+")
    c.add_argument("--referencia", default=None)
    comunes(c)

    r = sub.add_parser("resumen", help="métricas de todos los modelos guardados")
    comunes(r)

    k = sub.add_parser("calibracion", help="calibración por deciles de un modelo guardado")
    k.add_argument("nombre")
    k.add_argument("--por-clase", action="store_true")
    comunes(k)

    g = sub.add_parser("desglose", help="métricas de un modelo por torneo, fase o año")
    g.add_argument("nombre")
    g.add_argument("--por", default="torneo")
    comunes(g)

    sub.add_parser("registro", help="cuántas variantes se han probado, por familia")

    a = ap.parse_args(argv)
    if a.orden == "evaluar":
        modelo = instanciar(a.modelo, json.loads(a.kw))
        evaluar(modelo, a.periodo, a.granularidad, permitir_prueba=a.permitir_prueba,
                torneos=[t.strip() for t in a.torneos.split(",")] if a.torneos else None,
                desde=a.desde, hasta=a.hasta, guardar=not a.no_guardar, quien=a.quien, reanudar=a.reanudar)
    elif a.orden == "comparar":
        _imprimir(comparar(a.nombres, a.referencia, a.periodo, a.granularidad))
    elif a.orden == "resumen":
        _imprimir(resumen(a.periodo, a.granularidad))
    elif a.orden == "calibracion":
        _imprimir(calibracion(a.nombre, a.periodo, a.granularidad, a.por_clase))
    elif a.orden == "desglose":
        _imprimir(desglose(a.nombre, a.por, a.periodo, a.granularidad))
    elif a.orden == "registro":
        t = leer_registro()
        if len(t):
            print(f"evaluaciones registradas: {len(t)}  ·  variantes distintas: {t['nombre'].nunique()}")
            _imprimir(t.groupby("familia").agg(evaluaciones=("nombre", "size"), variantes=("nombre", "nunique")).reset_index())
        else:
            print("registro vacío")
    return 0


if __name__ == "__main__":
    sys.exit(main())
