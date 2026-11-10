# -*- coding: utf-8 -*-
"""
Líneas base de Cerebro Liga MX. Todas implementan arnes.Modelo.

  Frecuencias            proporciones históricas de local/empate/visita + Poisson con medias de liga.
  PoissonSimple          ataque y defensa por máxima verosimilitud con decaimiento exponencial
                         (vida media de 1 año), ventaja de local común, goles independientes.
  CerebroOriginal        el motor previo (cerebro_ligamx_2026.py) en su variante limpia para backtest:
                         mismo ajuste, sin priors ni capas escritas conociendo el futuro.
  CerebroOriginalExacto  el motor previo tal cual (priors, credibilidad y capas a mano). Sólo es
                         legítimo desde el 14-ago-2026, cuando el código quedó congelado.
  Mercado                probabilidades implícitas de los momios (cierre o apertura) sin margen, por
                         normalización proporcional, por el método de Shin o por el de potencia. Es
                         REFERENCIA: no sirve para simular rondas futuras.

Evaluar todas en DESARROLLO (desde ligamx/):  python3 -m modelo.base
"""
from __future__ import annotations

import contextlib
import io
import math
import sys

import numpy as np
import pandas as pd

from . import arnes, datos
from .arnes import Modelo


# ==================================================================================================
# (a) Frecuencias
# ==================================================================================================
class Frecuencias(Modelo):
    """
    El mismo pronóstico para todos los partidos: P(1X2) = proporciones históricas de local, empate y
    visita antes del corte; marcador = Poisson independientes con las medias de goles de local y de
    visita, reescalado para que su 1X2 coincida con las proporciones. `ventana_anios` limita la
    historia a los últimos años (None = toda).
    """
    familia = "base_frecuencias"

    def __init__(self, ventana_anios: float | None = None, nombre: str | None = None):
        self.ventana_anios = ventana_anios
        self.nombre = nombre or ("frecuencias" if ventana_anios is None else f"frecuencias_{ventana_anios:g}a")
        self.hiperparametros = {"ventana_anios": ventana_anios}
        self._pred = None

    def ajustar(self, hist, corte):
        ok = hist["evaluable"].to_numpy()
        if self.ventana_anios is not None:
            ok &= (hist["fecha_utc"] >= corte - pd.Timedelta(days=365.25 * self.ventana_anios)).to_numpy()
        if not ok.any():
            raise ValueError("Frecuencias: no hay historial antes del corte")
        res = hist["resultado"].to_numpy()[ok].astype(int)
        p = np.bincount(res, minlength=3) / len(res)
        lam_l = float(hist["gl"].to_numpy()[ok].mean())
        lam_v = float(hist["gv"].to_numpy()[ok].mean())
        M = arnes.ajustar_M_a_1x2(arnes.matriz_marcadores(lam_l, lam_v), p)
        self._pred = {"M": M, "lam_l": lam_l, "lam_v": lam_v}

    def predecir(self, partidos):
        return [self._pred] * len(partidos)


# ==================================================================================================
# (b) Poisson simple
# ==================================================================================================
def ajustar_poisson(il, iv, gl, gv, w, n_eq: int, ridge: float = 1.0, theta0=None,
                    max_iter: int = 60, tol: float = 1e-9) -> tuple[np.ndarray, int]:
    """
    Máxima verosimilitud (ponderada y con penalización cuadrática) del modelo de goles independientes
        log lam_l = c + h + atk[local] + dfn[visita]        log lam_v = c + atk[visita] + dfn[local]
    por Newton con paso amortiguado. theta = [c, h, atk (n_eq), dfn (n_eq)]; dfn > 0 = concede más.
    La penalización (ridge/2)·(sum atk^2 + sum dfn^2) identifica el modelo (centra ataque y defensa) y
    mantiene finitos a los equipos con muy pocos partidos. Devuelve (theta, iteraciones).
    """
    n = len(il)
    p = 2 + 2 * n_eq
    r = np.arange(n)
    X = np.zeros((2 * n, p))
    X[:, 0] = 1.0
    X[:n, 1] = 1.0
    X[r, 2 + il] = 1.0
    X[r, 2 + n_eq + iv] = 1.0
    X[n + r, 2 + iv] = 1.0
    X[n + r, 2 + n_eq + il] = 1.0
    y = np.concatenate([gl, gv]).astype(float)
    ww = np.concatenate([w, w]).astype(float)
    pen = np.r_[0.0, 0.0, np.full(2 * n_eq, float(ridge))]

    def logv(th):
        eta = X @ th
        return float(ww @ (y * eta - np.exp(eta)) - 0.5 * pen @ (th * th)), eta

    if theta0 is None:
        theta = np.zeros(p)
        theta[0] = math.log(max(float(ww @ y) / float(ww.sum()), 1e-6))
    else:
        theta = np.asarray(theta0, float).copy()
    f, eta = logv(theta)
    it = 0
    for it in range(1, max_iter + 1):
        mu = np.exp(eta)
        g = X.T @ (ww * (y - mu)) - pen * theta
        H = (X * (ww * mu)[:, None]).T @ X
        H[np.diag_indices(p)] += pen + 1e-10
        paso = np.linalg.solve(H, g)
        t = 1.0
        while True:                                   # amortiguamiento: nunca empeorar la verosimilitud
            f2, eta2 = logv(theta + t * paso)
            if f2 >= f - 1e-12 or t < 1e-6:
                break
            t *= 0.5
        theta, f, eta = theta + t * paso, f2, eta2
        if np.max(np.abs(t * paso)) < tol:
            break
    return theta, it


class PoissonSimple(Modelo):
    """
    Ataque y defensa por equipo, ventaja de local común y goles independientes (rho = 0), ajustados por
    máxima verosimilitud con peso 0.5^(antigüedad / vida_media). Cada ajuste arranca del anterior.

    vida_media_dias  vida media del decaimiento (365 = 1 año).
    ridge            penalización cuadrática sobre ataque y defensa en escala logarítmica (equivale a
                     un prior N(0, 1/ridge)); con 1.0 casi no mueve a un equipo con historia y evita
                     que diverja uno con dos o tres partidos. Un equipo sin partidos previos = promedio.
    ventana_dias     se ignoran partidos más viejos (a 10 años el peso es 0.001).
    Los resultados de escritorio se excluyen del ajuste.
    """
    familia = "base_poisson"

    def __init__(self, vida_media_dias: float = 365.0, ridge: float = 1.0, ventana_dias: float = 3650.0,
                 nombre: str | None = None):
        self.vida_media_dias, self.ridge, self.ventana_dias = float(vida_media_dias), float(ridge), float(ventana_dias)
        self.nombre = nombre or "poisson_simple"
        self.hiperparametros = {"vida_media_dias": self.vida_media_dias, "ridge": self.ridge,
                                "ventana_dias": self.ventana_dias}
        self.c = self.h = None
        self.atk: dict[str, float] = {}
        self.dfn: dict[str, float] = {}
        self.iteraciones = 0

    def ajustar(self, hist, corte):
        edad = (corte - hist["fecha_utc"]).dt.total_seconds().to_numpy() / 86400.0
        ok = hist["evaluable"].to_numpy() & (edad <= self.ventana_dias)
        if not ok.any():
            raise ValueError("PoissonSimple: no hay historial antes del corte")
        loc, vis = hist["local"].to_numpy()[ok], hist["visitante"].to_numpy()[ok]
        equipos = sorted(set(loc) | set(vis))
        ix = {e: i for i, e in enumerate(equipos)}
        il = np.fromiter((ix[e] for e in loc), int, len(loc))
        iv = np.fromiter((ix[e] for e in vis), int, len(vis))
        w = 0.5 ** (edad[ok] / self.vida_media_dias)
        theta0 = None
        if self.c is not None:                         # arranque en caliente con el ajuste anterior
            theta0 = np.r_[self.c, self.h, [self.atk.get(e, 0.0) for e in equipos],
                           [self.dfn.get(e, 0.0) for e in equipos]]
        theta, self.iteraciones = ajustar_poisson(il, iv, hist["gl"].to_numpy()[ok], hist["gv"].to_numpy()[ok],
                                                  w, len(equipos), self.ridge, theta0)
        ne = len(equipos)
        self.c, self.h = float(theta[0]), float(theta[1])
        self.atk = dict(zip(equipos, theta[2:2 + ne].tolist()))
        self.dfn = dict(zip(equipos, theta[2 + ne:].tolist()))

    def lambdas(self, local: str, visitante: str) -> tuple[float, float]:
        """(goles esperados del local, de la visita); un equipo nunca visto vale el promedio (0, 0)."""
        a, d = self.atk, self.dfn
        return (math.exp(self.c + self.h + a.get(local, 0.0) + d.get(visitante, 0.0)),
                math.exp(self.c + a.get(visitante, 0.0) + d.get(local, 0.0)))

    def predecir(self, partidos):
        out = []
        for loc, vis in zip(partidos["local"], partidos["visitante"]):
            ll, lv = self.lambdas(loc, vis)
            out.append({"lam_l": ll, "lam_v": lv, "rho": 0.0})
        return out


# ==================================================================================================
# (c) Cerebro original
# ==================================================================================================
RAIZ_PREVIO = datos.RAIZ.parent                        # raíz del repo: cerebro_ligamx_2026.py y generar.py
INICIO_HISTORIA_ORIGINAL = pd.Timestamp("2010-07-23")  # primer partido del CSV con que se calibraba
CONGELADO = pd.Timestamp("2026-08-14", tz=datos.ZONA)  # desde aquí el motor exacto es fuera de muestra
_motor_cache = None


def motor_original():
    """Importa (una vez) cerebro_ligamx_2026 y generar del repo previo sin dejar __pycache__ en la raíz."""
    global _motor_cache
    if _motor_cache is None:
        previo, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        sys.path.insert(0, str(RAIZ_PREVIO))
        try:
            import cerebro_ligamx_2026 as C
            import generar as G
        finally:
            sys.path.remove(str(RAIZ_PREVIO))
            sys.dont_write_bytecode = previo
        _motor_cache = (C, G)
    return _motor_cache


def partidos_formato_original(hist: pd.DataFrame) -> list[dict]:
    """
    Historial en el formato del motor previo: dicts {fecha (date local), local, visitante, gl, gv, fase}
    desde el 23-jul-2010, con fase 'regular' o 'liguilla' (repechaje, cuartos, semifinal y final). El
    marcador es el de 90 minutos de ESPN (el CSV previo traía 120 minutos y algunas tandas de penales).
    """
    h = hist[hist["fecha_local"] >= INICIO_HISTORIA_ORIGINAL]
    fechas = h["fecha_local"].dt.date.to_numpy()
    fase = np.where(h["fase"].to_numpy() == "regular", "regular", "liguilla")
    return [{"fecha": f, "local": l, "visitante": v, "gl": int(a), "gv": int(b), "fase": s}
            for f, l, v, a, b, s in zip(fechas, h["local"].to_numpy(), h["visitante"].to_numpy(),
                                        h["gl"].to_numpy(), h["gv"].to_numpy(), fase)]


def ajuste_original(entrena: list[dict], corte_d) -> tuple[dict, tuple[float, float], dict]:
    """
    Núcleo del motor previo sobre partidos anteriores a `corte_d` (date): bases = media sin ponderar de
    goles de local y visita en fase regular; ratings crudos = C.fit_dixon_coles(entrena, hoy=corte_d);
    pesos = G.pesos. Devuelve (ratings crudos, bases, pesos por equipo).
    """
    C, G = motor_original()
    reg = [p for p in entrena if p["fase"] == "regular"]
    bases = (sum(p["gl"] for p in reg) / len(reg), sum(p["gv"] for p in reg) / len(reg))
    C.BASE_HOME_GOALS, C.BASE_AWAY_GOALS = bases
    with contextlib.redirect_stdout(io.StringIO()):     # fit_dixon_coles imprime
        crudos = C.fit_dixon_coles(entrena, hoy=corte_d)
    return crudos, bases, G.pesos(entrena, corte_d)


class CerebroOriginal(Modelo):
    """
    Motor previo en su variante LIMPIA para backtest: el mismo ajuste (C.fit_dixon_coles: xi = 0.0038,
    liguilla x1.25, rho = -0.11 fijo, historia desde 2010), las mismas bases y la misma matriz, pero
    SIN lo que se escribió en julio de 2026 conociendo el pasado: ni priors por equipo, ni localía por
    estadio, ni escudo, ni H2H. La credibilidad conserva su fórmula (Z = w^p / (w^p + k^p), k = 4,
    p = 3) pero encoge hacia el equipo promedio (1, 1) y se aplica a todos los equipos.
    `credibilidad=False` deja los ratings crudos. Un equipo sin partidos previos vale (1, 1).
    """
    familia = "base_cerebro_original"

    def __init__(self, credibilidad: bool = True, k: float = 4.0, p: float = 3.0, nombre: str | None = None):
        self.credibilidad, self.k, self.p = bool(credibilidad), float(k), float(p)
        self.nombre = nombre or ("cerebro_original_limpio" if credibilidad else "cerebro_original_crudo")
        self.hiperparametros = {"credibilidad": self.credibilidad, "k": self.k, "p": self.p,
                                "xi": 0.0038, "rho": -0.11, "peso_liguilla": 1.25, "capas": "ninguna",
                                "prior": "equipo promedio (1, 1)"}
        self.ratings, self.bases = {}, (np.nan, np.nan)

    def ajustar(self, hist, corte):
        corte_d = corte.tz_convert(datos.ZONA).date()
        crudos, self.bases, w = ajuste_original(partidos_formato_original(hist), corte_d)
        if self.credibilidad:
            ratings = {}
            for e, (a, d) in crudos.items():
                wi = w.get(e, 0.0)
                z = wi ** self.p / (wi ** self.p + self.k ** self.p) if wi > 0 else 0.0
                ratings[e] = (math.exp(z * math.log(a)), math.exp(z * math.log(d)))
            crudos = ratings
        self.ratings = crudos

    def predecir(self, partidos):
        C, _ = motor_original()
        out = []
        for loc, vis in zip(partidos["local"], partidos["visitante"]):
            atk_l, def_l = self.ratings.get(loc, (1.0, 1.0))
            atk_v, def_v = self.ratings.get(vis, (1.0, 1.0))
            lam_l, lam_v = self.bases[0] * atk_l * def_v, self.bases[1] * atk_v * def_l
            out.append({"M": C.matriz_marcadores(lam_l, lam_v), "lam_l": lam_l, "lam_v": lam_v})
        return out


class CerebroOriginalExacto(Modelo):
    """
    Motor previo EXACTO (receta de notas/mapa_repo_previo.md §1.6): MLE + credibilidad hacia
    PRIORS_ILUSTRATIVOS (k = 4, p = 3) + localía por estadio + escudo + H2H, sin ajustes de jornada.
    Los priors y las capas se escribieron en julio de 2026: antes del 14-ago-2026 ve el futuro, así que
    `ajustar` se niega a correr con cortes anteriores (salvo forzar=True, sólo para reproducir lo
    publicado). Se alimenta con ESPN (sin el hueco de 2025-26 que tenía el CSV de agosto).
    """
    familia = "base_cerebro_original"
    CRED = {"activa": True, "k": 4, "p": 3}

    def __init__(self, forzar: bool = False, nombre: str | None = None):
        self.forzar = bool(forzar)
        self.nombre = nombre or "cerebro_original_exacto"
        self.hiperparametros = {"credibilidad": self.CRED, "capas": "localia_estadio, escudo, h2h",
                                "valido_desde": "2026-08-14"}
        self.ratings, self.bases = {}, (np.nan, np.nan)

    def ajustar_dicts(self, entrena: list[dict], corte_d) -> None:
        """Ajuste con partidos ya en el formato original (para reproducir pronósticos publicados)."""
        C, G = motor_original()
        crudos, self.bases, w = ajuste_original(entrena, corte_d)
        for e in C.EQUIPOS:
            crudos.setdefault(e, C.PRIORS_ILUSTRATIVOS[e])
        self.ratings, _ = G.aplicar_credibilidad(crudos, w, self.CRED)

    def ajustar(self, hist, corte):
        if corte < CONGELADO and not self.forzar:
            raise ValueError("CerebroOriginalExacto sólo es válido desde el 14-ago-2026: antes, sus priors "
                             "y capas (escritos en julio de 2026) ven el futuro. Use CerebroOriginal.")
        self.ajustar_dicts(partidos_formato_original(hist), corte.tz_convert(datos.ZONA).date())

    def predecir_uno(self, local: str, visitante: str) -> dict:
        C, _ = motor_original()
        C.BASE_HOME_GOALS, C.BASE_AWAY_GOALS = self.bases           # estado global del módulo: fijarlo siempre
        lam_l, lam_v, _ = C.lambdas_partido(local, visitante, self.ratings, jornada_actual=False)
        return {"M": C.matriz_marcadores(lam_l, lam_v), "lam_l": lam_l, "lam_v": lam_v}

    def predecir(self, partidos):
        return [self.predecir_uno(l, v) for l, v in zip(partidos["local"], partidos["visitante"])]


# ==================================================================================================
# (d) Mercado
# ==================================================================================================
def prob_proporcional(momios) -> np.ndarray:
    """Probabilidades implícitas sin margen: 1/momio dividido entre la suma (n, 3)."""
    inv = 1.0 / np.asarray(momios, float).reshape(-1, 3)
    return inv / inv.sum(axis=1, keepdims=True)


def prob_shin(momios, iteraciones: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """
    Probabilidades implícitas por el método de Shin (1993): el margen se atribuye a una fracción z de
    apostadores informados, lo que quita más margen a los momios altos (corrige el sesgo
    favorito-desvalido). p_i = [sqrt(z^2 + 4(1-z)·pi_i^2/B) - z] / (2(1-z)), con pi_i = 1/momio_i,
    B = sum pi_i y z tal que sum p_i = 1 (bisección vectorizada). Devuelve (P (n, 3), z (n,)).
    """
    pi = 1.0 / np.asarray(momios, float).reshape(-1, 3)
    B = pi.sum(axis=1, keepdims=True)

    def probs(z):
        z = z[:, None]
        return (np.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / B) - z) / (2.0 * (1.0 - z))

    lo, hi = np.zeros(len(pi)), np.full(len(pi), 0.5)
    for _ in range(iteraciones):                        # sum p_i(z) decrece con z
        mid = 0.5 * (lo + hi)
        mayor = probs(mid).sum(axis=1) > 1.0
        lo, hi = np.where(mayor, mid, lo), np.where(mayor, hi, mid)
    z = 0.5 * (lo + hi)
    P = probs(z)
    return P / P.sum(axis=1, keepdims=True), z


def prob_potencia(momios, iteraciones: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """
    Probabilidades implícitas por el método de potencia: p_i = pi_i^k con pi_i = 1/momio_i y k >= 1 tal
    que sum p_i = 1 (bisección vectorizada). Quita todavía más margen a los momios altos que Shin.
    Devuelve (P (n, 3), k (n,)).
    """
    pi = 1.0 / np.asarray(momios, float).reshape(-1, 3)
    lo, hi = np.ones(len(pi)), np.full(len(pi), 3.0)
    for _ in range(iteraciones):                        # sum pi_i^k decrece con k (pi_i < 1)
        mid = 0.5 * (lo + hi)
        mayor = (pi ** mid[:, None]).sum(axis=1) > 1.0
        lo, hi = np.where(mayor, mid, lo), np.where(mayor, hi, mid)
    k = 0.5 * (lo + hi)
    P = pi ** k[:, None]
    return P / P.sum(axis=1, keepdims=True), k


_METODOS_MERCADO = {"proporcional": "prop", "shin": "shin", "potencia": "pot"}


class Mercado(Modelo):
    """
    Referencia de mercado: 1X2 implícito en los momios, sin margen. tipo = 'cierre' (ml_l, ml_e, ml_v)
    o 'apertura' (ml_*_abre); metodo = 'proporcional', 'shin' o 'potencia'. Sólo pronostica donde hay
    momios completos (y no marcados como capturados en vivo); no produce matriz de marcadores.
    """
    familia = "referencia_mercado"

    def __init__(self, tipo: str = "cierre", metodo: str = "shin", nombre: str | None = None):
        if tipo not in ("cierre", "apertura") or metodo not in _METODOS_MERCADO:
            raise ValueError("tipo: 'cierre' o 'apertura'; metodo: 'proporcional', 'shin' o 'potencia'")
        self.tipo, self.metodo = tipo, metodo
        self.cols = ["ml_l", "ml_e", "ml_v"] if tipo == "cierre" else ["ml_l_abre", "ml_e_abre", "ml_v_abre"]
        self.nombre = nombre or f"mercado_{'cierre' if tipo == 'cierre' else 'abre'}_{_METODOS_MERCADO[metodo]}"
        self.hiperparametros = {"tipo": tipo, "metodo": metodo}

    def ajustar(self, hist, corte):
        pass                                             # el mercado no se ajusta

    def predecir(self, partidos):
        mom = partidos[self.cols].to_numpy(float)
        ok = np.isfinite(mom).all(axis=1) & (mom > 1.0).all(axis=1)
        out: list = [None] * len(partidos)
        if ok.any():
            P = {"shin": lambda m: prob_shin(m)[0], "potencia": lambda m: prob_potencia(m)[0],
                 "proporcional": prob_proporcional}[self.metodo](mom[ok])
            for i, p in zip(np.flatnonzero(ok), P):
                out[i] = {"p1x2": p}
        return out


LINEAS_OU = (1.5, 2.5, 3.5, 4.5)                        # líneas de goles sin devolución (medio gol)


def marcador_de_mercado(p1x2, linea=None, p_over=None, iteraciones: int = 60) -> tuple[np.ndarray, ...]:
    """
    Parámetros (lam_l, lam_v, rho) de la matriz Dixon-Coles que reproduce lo que cotiza el mercado:
    P(gana local) y P(gana visita) del 1X2 y, donde hay línea de goles, P(total > línea). Son tres
    ecuaciones con tres incógnitas, resueltas por Newton amortiguado y vectorizado (jacobiano numérico).
    Sin línea de goles utilizable se fija rho = 0 y se resuelven sólo las dos del 1X2.
    rho se limita a [-0.3, 0.3]: si el mercado pide más, queda un residuo. Devuelve
    (lam_l, lam_v, rho, residuo), donde residuo es el máximo error absoluto de las ecuaciones.
    """
    p = np.asarray(p1x2, float).reshape(-1, 3)
    n = len(p)
    linea = np.full(n, np.nan) if linea is None else np.asarray(linea, float).ravel()
    p_over = np.full(n, np.nan) if p_over is None else np.asarray(p_over, float).ravel()
    con_ou = np.isin(linea, LINEAS_OU) & np.isfinite(p_over) & (p_over > 0.01) & (p_over < 0.99)
    mas = (arnes._TOTAL[None, :, :] > np.where(con_ou, linea, 2.5)[:, None, None])

    def F(th):
        M = arnes.matrices_marcadores(np.exp(th[:, 0]), np.exp(th[:, 1]), th[:, 2])
        q = arnes.p1x2(M)
        tercero = np.where(con_ou, (M * mas).sum(axis=(1, 2)) - np.where(con_ou, p_over, 0.0), th[:, 2])
        return np.column_stack([q[:, 0] - p[:, 0], q[:, 2] - p[:, 2], tercero])

    th = np.column_stack([np.full(n, math.log(1.45)), np.full(n, math.log(1.15)), np.zeros(n)])
    h = 1e-5
    for _ in range(iteraciones):
        f0 = F(th)
        J = np.empty((n, 3, 3))
        for j in range(3):
            d = th.copy()
            d[:, j] += h
            J[:, :, j] = (F(d) - f0) / h
        paso = np.linalg.solve(J + 1e-9 * np.eye(3)[None], -f0[:, :, None])[:, :, 0]
        paso[:, :2] = np.clip(paso[:, :2], -0.5, 0.5)
        paso[:, 2] = np.clip(paso[:, 2], -0.1, 0.1)
        th = th + paso
        th[:, :2] = np.clip(th[:, :2], math.log(0.05), math.log(6.0))
        th[:, 2] = np.clip(th[:, 2], -0.3, 0.3)
        if np.abs(paso).max() < 1e-10:
            break
    return np.exp(th[:, 0]), np.exp(th[:, 1]), th[:, 2], np.abs(F(th)).max(axis=1)


class MercadoMarcador(Modelo):
    """
    Referencia de mercado para el MARCADOR: la matriz Dixon-Coles implícita en los momios de cierre
    (1X2 sin margen por Shin + línea de goles sin margen por normalización proporcional; ver
    marcador_de_mercado). Su 1X2 se reescala al del mercado, así que coincide con mercado_cierre_shin.
    Sólo donde hay momios 1X2; sin línea de goles utilizable usa rho = 0. Es REFERENCIA, como Mercado.
    """
    familia = "referencia_mercado"

    def __init__(self, nombre: str | None = None):
        self.nombre = nombre or "mercado_cierre_marcador"
        self.hiperparametros = {"tipo": "cierre", "metodo_1x2": "shin", "metodo_goles": "proporcional",
                                "matriz": "Dixon-Coles con lam_l, lam_v y rho implícitos"}

    def ajustar(self, hist, corte):
        pass

    def predecir(self, partidos):
        mom = partidos[["ml_l", "ml_e", "ml_v"]].to_numpy(float)
        ok = np.isfinite(mom).all(axis=1) & (mom > 1.0).all(axis=1)
        out: list = [None] * len(partidos)
        if ok.any():
            P = prob_shin(mom[ok])[0]
            ou = partidos[["over", "under"]].to_numpy(float)[ok]
            p_over = (1.0 / ou[:, 0]) / (1.0 / ou[:, 0] + 1.0 / ou[:, 1])
            ll, lv, rho, res = marcador_de_mercado(P, partidos["total_linea"].to_numpy(float)[ok], p_over)
            for i, p, a, b, r, e in zip(np.flatnonzero(ok), P, ll, lv, rho, res):
                M = arnes.ajustar_M_a_1x2(arnes.matriz_marcadores(a, b, r), p)
                out[i] = {"M": M, "lam_l": a, "lam_v": b, "x_rho": r, "x_residuo": e}
        return out


# ==================================================================================================
# Corrida de todas las líneas base en DESARROLLO
# ==================================================================================================
def lineas_base(con_original: bool = True) -> list[Modelo]:
    """Las líneas base que se evalúan en DESARROLLO (el Cerebro original tarda decenas de minutos)."""
    m: list[Modelo] = [Frecuencias(), PoissonSimple(),
                       Mercado("cierre", "proporcional"), Mercado("cierre", "shin"), Mercado("cierre", "potencia"),
                       Mercado("apertura", "proporcional"), Mercado("apertura", "shin"), MercadoMarcador()]
    if con_original:
        m.append(CerebroOriginal())
    return m


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Evalúa las líneas base en DESARROLLO")
    ap.add_argument("--sin-original", action="store_true", help="omite el Cerebro original (lento)")
    ap.add_argument("--solo-original", action="store_true")
    a = ap.parse_args()
    for mod in lineas_base(con_original=not a.sin_original):
        if a.solo_original and not isinstance(mod, CerebroOriginal):
            continue
        arnes.evaluar(mod)
