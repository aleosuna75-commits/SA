# -*- coding: utf-8 -*-
"""
Métricas de pronóstico y comparaciones pareadas con error estándar por bloques.

Convenciones (las mismas en todo el proyecto):
  * Resultado a 90 minutos, codificado 0 = gana local, 1 = empate, 2 = gana visita.
  * P es una matriz (n, 3) con columnas en ese orden; cada fila suma 1.
  * Log-loss con logaritmo natural (azar uniforme = ln 3 = 1.0986).
  * RPS con el orden local > empate > visita, dividido entre 2 (rango 0 a 1; azar uniforme = 0.222
    con resultados equiprobables).
  * Brier multicategoría: suma de (p - o)^2 sobre los 3 resultados (rango 0 a 2; azar uniforme 0.667).
  * Log-verosimilitud del marcador: ln M[gl, gv] sobre la malla 0-10 (un marcador con más de 10 goles
    de un lado se evalúa en la celda 10). MAYOR es mejor; las demás métricas, MENOR es mejor.
  * Las funciones `*_1x2` y `logv_marcador` devuelven el valor POR PARTIDO (para poder parear).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEMILLA = 20261110          # semilla fija del bootstrap
B_BOOTSTRAP = 2000
EPS = 1e-12                 # piso de probabilidad dentro de los logaritmos
MAX_GOLES = 10


# ==================================================================================================
# Métricas por partido
# ==================================================================================================
def resultado_1x2(gl, gv) -> np.ndarray:
    """0 = gana local, 1 = empate, 2 = gana visita (marcador a 90 minutos)."""
    gl, gv = np.asarray(gl, float), np.asarray(gv, float)
    return np.where(gl > gv, 0, np.where(gl == gv, 1, 2)).astype(int)


def _validar(P, y):
    P = np.asarray(P, float).reshape(-1, 3)
    y = np.asarray(y).astype(int).ravel()
    if len(P) != len(y):
        raise ValueError("P y y deben tener el mismo número de partidos")
    return P, y


def logloss_1x2(P, y) -> np.ndarray:
    """-ln de la probabilidad dada al resultado que ocurrió."""
    P, y = _validar(P, y)
    return -np.log(np.clip(P[np.arange(len(y)), y], EPS, None))


def rps_1x2(P, y) -> np.ndarray:
    """Ranked Probability Score: media de los cuadrados de las diferencias de acumuladas (2 umbrales)."""
    P, y = _validar(P, y)
    O = np.eye(3)[y]
    dif = np.cumsum(P, axis=1)[:, :2] - np.cumsum(O, axis=1)[:, :2]
    return (dif ** 2).sum(axis=1) / 2.0


def brier_1x2(P, y) -> np.ndarray:
    """Brier multicategoría: suma sobre los tres resultados de (p - o)^2."""
    P, y = _validar(P, y)
    return ((P - np.eye(3)[y]) ** 2).sum(axis=1)


def acierto_1x2(P, y) -> np.ndarray:
    """1 si el resultado más probable ocurrió (empates de probabilidad: local, luego empate)."""
    P, y = _validar(P, y)
    return (np.argmax(P, axis=1) == y).astype(float)


def logv_marcador(M, gl, gv) -> np.ndarray:
    """ln de la probabilidad del marcador exacto; M es (n, 11, 11) con M[i, x, y] = P(local x, visita y)."""
    M = np.asarray(M, float)
    if M.ndim == 2:
        M = M[None]
    x = np.clip(np.asarray(gl).astype(int).ravel(), 0, MAX_GOLES)
    y = np.clip(np.asarray(gv).astype(int).ravel(), 0, MAX_GOLES)
    return np.log(np.clip(M[np.arange(len(x)), x, y], EPS, None))


# ==================================================================================================
# Calibración
# ==================================================================================================
def calibracion_deciles(P, y, n_grupos: int = 10, por_clase: bool = False) -> pd.DataFrame:
    """
    Tabla de calibración: se ordenan las probabilidades pronosticadas, se parten en `n_grupos` grupos de
    igual tamaño (deciles) y se compara la probabilidad media con la frecuencia observada.

    por_clase=False junta las 3n parejas (probabilidad, ocurrió) de local, empate y visita;
    por_clase=True devuelve una tabla por resultado. Columnas: clase, grupo, n, p_media, frec_obs,
    dif (= frec_obs - p_media) y ee (error estándar binomial de la frecuencia bajo el pronóstico).
    """
    P, y = _validar(P, y)
    O = np.eye(3)[y]
    clases = [("local", P[:, 0], O[:, 0]), ("empate", P[:, 1], O[:, 1]), ("visita", P[:, 2], O[:, 2])]
    if not por_clase:
        clases = [("todas", P.ravel(), O.ravel())]
    filas = []
    for nombre, p, o in clases:
        orden = np.argsort(p, kind="mergesort")
        for g, idx in enumerate(np.array_split(orden, n_grupos), start=1):
            if len(idx) == 0:
                continue
            pm, fo = float(p[idx].mean()), float(o[idx].mean())
            filas.append({"clase": nombre, "grupo": g, "n": len(idx), "p_media": pm, "frec_obs": fo,
                          "dif": fo - pm, "ee": float(np.sqrt(max(pm * (1 - pm), 0.0) / len(idx)))})
    return pd.DataFrame(filas)


def error_calibracion(P, y, n_grupos: int = 10) -> float:
    """Error de calibración esperado: media ponderada de |frec_obs - p_media| sobre los deciles."""
    t = calibracion_deciles(P, y, n_grupos)
    return float((t["dif"].abs() * t["n"]).sum() / t["n"].sum())


def pendiente_calibracion(P, y) -> float:
    """
    Exponente t que minimiza el log-loss de P**t renormalizada (escala de temperatura inversa).
    t = 1: bien calibrado; t > 1: el pronóstico es tímido (convenía exagerarlo); t < 1: sobreconfiado.
    """
    from scipy.optimize import minimize_scalar
    P, y = _validar(P, y)
    L = np.log(np.clip(P, EPS, None))

    def perdida(t):
        Z = L * t
        Z = Z - Z.max(axis=1, keepdims=True)
        return float(-(Z[np.arange(len(y)), y] - np.log(np.exp(Z).sum(axis=1))).mean())

    return float(minimize_scalar(perdida, bounds=(0.2, 5.0), method="bounded").x)


# ==================================================================================================
# Bootstrap de bloques
# ==================================================================================================
def bootstrap_bloques(valores, bloques, B: int = B_BOOTSTRAP, semilla: int = SEMILLA) -> dict:
    """
    Media de `valores` con error estándar e intervalo de 95% por bootstrap de bloques.

    Se remuestrean BLOQUES completos con reemplazo (los partidos de una misma jornada comparten
    información y no son independientes) y en cada réplica se calcula suma/cuenta. Semilla fija.
    Devuelve media, ee, ic_inf, ic_sup (percentiles 2.5 y 97.5), n y n_bloques.
    """
    v = np.asarray(valores, float).ravel()
    ok = ~np.isnan(v)
    v = v[ok]
    cod, _ = pd.factorize(np.asarray(bloques).ravel()[ok], sort=True)
    if len(v) == 0:
        return {"media": np.nan, "ee": np.nan, "ic_inf": np.nan, "ic_sup": np.nan, "n": 0, "n_bloques": 0}
    nb = int(cod.max()) + 1
    suma = np.bincount(cod, weights=v, minlength=nb)
    cuenta = np.bincount(cod, minlength=nb).astype(float)
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, nb, size=(B, nb))
    rep = suma[idx].sum(axis=1) / cuenta[idx].sum(axis=1)
    return {"media": float(v.mean()), "ee": float(rep.std(ddof=1)) if nb > 1 else np.nan,
            "ic_inf": float(np.percentile(rep, 2.5)), "ic_sup": float(np.percentile(rep, 97.5)),
            "n": int(len(v)), "n_bloques": nb}


def diferencia_pareada(a, b, bloques, B: int = B_BOOTSTRAP, semilla: int = SEMILLA) -> dict:
    """
    Diferencia media a - b de una métrica por partido (mismos partidos, mismo orden) con error estándar
    e intervalo de 95% por bootstrap de bloques. `z` = dif / ee. Con log-loss, RPS y Brier, dif < 0
    significa que `a` es mejor; con la log-verosimilitud del marcador, dif > 0.
    """
    a, b = np.asarray(a, float).ravel(), np.asarray(b, float).ravel()
    if len(a) != len(b):
        raise ValueError("a y b deben venir pareados (misma longitud)")
    r = bootstrap_bloques(a - b, bloques, B, semilla)
    return {"dif": r["media"], "ee": r["ee"], "ic_inf": r["ic_inf"], "ic_sup": r["ic_sup"],
            "z": (r["media"] / r["ee"]) if r["ee"] and r["ee"] > 0 else np.nan,
            "n": r["n"], "n_bloques": r["n_bloques"]}


# ==================================================================================================
# Resumen de un archivo de predicciones
# ==================================================================================================
def metricas_por_partido(pred: pd.DataFrame) -> pd.DataFrame:
    """Añade a una tabla de predicciones del arnés las métricas por partido (ll, rps, brier, acierto)."""
    P = pred[["p_l", "p_e", "p_v"]].to_numpy(float)
    y = pred["resultado"].to_numpy(int)
    out = pred.copy()
    out["ll"], out["rps"], out["brier"], out["acierto"] = (
        logloss_1x2(P, y), rps_1x2(P, y), brier_1x2(P, y), acierto_1x2(P, y))
    return out


def resumen(pred: pd.DataFrame, con_ee: bool = False) -> dict:
    """
    Métricas agregadas de una tabla de predicciones del arnés: n, logloss, rps, brier, logv_marcador
    (media de logp_marcador; NaN si el modelo sólo da 1X2), acierto y n_marcador. Con con_ee=True añade
    el error estándar por bloques del log-loss.
    """
    if len(pred) == 0:
        return {"n": 0, "logloss": np.nan, "rps": np.nan, "brier": np.nan, "logv_marcador": np.nan,
                "acierto": np.nan, "n_marcador": 0}
    m = metricas_por_partido(pred)
    lm = m["logp_marcador"].to_numpy(float)
    r = {"n": int(len(m)), "logloss": float(m["ll"].mean()), "rps": float(m["rps"].mean()),
         "brier": float(m["brier"].mean()),
         "logv_marcador": float(np.nanmean(lm)) if np.isfinite(lm).any() else np.nan,
         "acierto": float(m["acierto"].mean()), "n_marcador": int(np.isfinite(lm).sum())}
    if con_ee:
        r["ee_logloss"] = bootstrap_bloques(m["ll"], m["bloque"])["ee"]
    return r
