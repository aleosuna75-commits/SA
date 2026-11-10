# -*- coding: utf-8 -*-
"""
Candidatos de Cerebro Liga MX. Todos implementan arnes.Modelo y devuelven lam_l, lam_v y rho.

  DixonColes  (C1 "dc", C2 "dc2", C4 "tiros")  ataque y defensa por equipo por máxima verosimilitud
              penalizada con decaimiento exponencial; rho por verosimilitud perfilada. Opciones: ventaja
              de local por equipo encogida, efecto de fase (liguilla), peso de liguilla, olvido al
              cambiar de torneo y mezcla de goles con goles esperados aproximados por tiros.
  Elo         (C3 "elo")  Elo con margen de goles y ventaja de local, regresión a la media entre
              torneos y conversión a goles por regresión de Poisson reajustada al inicio de cada torneo.
  Ajuste      (C5 "ajuste")  corrección log-lineal pequeña (ridge fuerte) de las lambdas de un modelo
              base con pocas variables escogidas de antemano; coeficientes reajustados sólo con el
              pasado al inicio de cada torneo.
  Ensamble    (C6 "ensamble")  promedio de lambdas o de probabilidades de varios modelos.

finalistas() devuelve las instancias con los hiperparámetros elegidos en DESARROLLO (Apertura 2016 a
Clausura 2025); DESCRIPCION las explica en lenguaje llano. Resultados: modelo/informes/candidatos.md.

Evaluar uno (desde ligamx/):
    python3 -m modelo.arnes evaluar modelo.familias.candidatos:DixonColes --kw '{"vida_media": 730, "ridge": 4}'
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import sparse

from .. import arnes, datos
from ..arnes import Modelo

RHO_MAX = 0.25                       # cota de seguridad para la correlación Dixon-Coles
RUTA_VARIABLES = {"bloque": arnes.DIR_CACHE / "variables_bloque.parquet",
                  "partido": arnes.DIR_CACHE / "variables.parquet"}


# ==================================================================================================
# Utilidades comunes
# ==================================================================================================
def orden_calendario(anio, mes, dia):
    """
    Ordinal de torneo deducido sólo del calendario: 2*año + 1 si es Apertura (del 20 de junio en
    adelante) y 2*año si es Clausura. No depende de la etiqueta `torneo` (que trae un partido de julio
    de 2016 rotulado "Clausura 2017"). Sirve para saber, en un corte, a qué torneo pertenece lo que viene.
    """
    return 2 * anio + ((mes >= 7) | ((mes == 6) & (dia >= 20))).astype(int)


def orden_de_fechas(fecha_local: pd.Series) -> np.ndarray:
    """Ordinal de torneo (ver orden_calendario) de una serie de fechas locales."""
    f = fecha_local.dt
    return orden_calendario(f.year.to_numpy(), f.month.to_numpy(), f.day.to_numpy())


def orden_de_corte(corte: pd.Timestamp) -> int:
    """Ordinal del torneo en curso en el instante `corte` (UTC)."""
    c = corte.tz_convert(datos.ZONA)
    return int(orden_calendario(np.array(c.year), np.array(c.month), np.array(c.day)))


def newton_poisson(X, y, w, pen, theta0, max_iter: int = 60, tol: float = 1e-9):
    """
    Máximo de la verosimilitud de Poisson ponderada y penalizada
        sum_i w_i (y_i eta_i - exp(eta_i)) - 0.5 * sum_j pen_j theta_j^2,   eta = X theta (+ 0),
    por Newton con paso amortiguado (el mismo algoritmo de base.ajustar_poisson, con una matriz de
    diseño cualquiera, rala o densa). `y` puede no ser entero (cuasi-verosimilitud). Devuelve (theta, iteraciones).
    """
    ralo = sparse.issparse(X)
    Xt = X.T.tocsr() if ralo else X.T
    p = X.shape[1]

    def logv(th):
        eta = X @ th
        return float(w @ (y * eta - np.exp(eta)) - 0.5 * pen @ (th * th)), eta

    theta = np.asarray(theta0, float).copy()
    f, eta = logv(theta)
    it = 0
    for it in range(1, max_iter + 1):
        mu = np.exp(eta)
        g = Xt @ (w * (y - mu)) - pen * theta
        d = w * mu
        H = (Xt.multiply(d) @ X).toarray() if ralo else (Xt * d) @ X
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


def estimar_rho(lam, mu, gl, gv, w, rho0: float = 0.0, max_iter: int = 30) -> float:
    """
    Correlación Dixon-Coles por verosimilitud perfilada: dadas las medias (lam, mu) de cada partido,
    maximiza sum w log tau(gl, gv; rho), con tau = 1 - lam*mu*rho (0-0), 1 + lam*rho (0-1),
    1 + mu*rho (1-0) y 1 - rho (1-1). Es cóncava en rho: Newton con paso acotado al dominio.
    """
    gl, gv = np.asarray(gl), np.asarray(gv)
    a = np.zeros(len(gl))
    m00, m01, m10, m11 = (gl == 0) & (gv == 0), (gl == 0) & (gv == 1), (gl == 1) & (gv == 0), (gl == 1) & (gv == 1)
    a[m00], a[m01], a[m10], a[m11] = -(lam * mu)[m00], lam[m01], mu[m10], -1.0
    sel = a != 0
    a, ww = a[sel], np.asarray(w, float)[sel]
    if len(a) < 20:
        return 0.0
    lo = max(-RHO_MAX, float(np.max(-1.0 / a[a > 0])) + 1e-6) if (a > 0).any() else -RHO_MAX
    hi = min(RHO_MAX, float(np.min(-1.0 / a[a < 0])) - 1e-6) if (a < 0).any() else RHO_MAX
    rho = float(np.clip(rho0, lo, hi))
    for _ in range(max_iter):
        tau = 1.0 + a * rho
        g = float(ww @ (a / tau))
        h = -float(ww @ ((a / tau) ** 2))
        if h >= 0:
            break
        nuevo = float(np.clip(rho - g / h, lo, hi))
        if abs(nuevo - rho) < 1e-9:
            rho = nuevo
            break
        rho = nuevo
    return rho


# ==================================================================================================
# C1 / C2 / C4: Dixon-Coles penalizado
# ==================================================================================================
class DixonColes(Modelo):
    """
    log lam_l = c + h + atk[local] + dfn[visita] (+ hl[local]) (+ f_tot + f_loc si es liguilla)
    log lam_v = c     + atk[visita] + dfn[local]                (+ f_tot si es liguilla)
    Ataque y defensa con prior normal hacia la media (ridge), ventaja de local común `h`, peso
    0.5^(antigüedad / vida_media). Dos etapas: (1) verosimilitud de Poisson penalizada por Newton
    (arranca del ajuste anterior); (2) rho por verosimilitud perfilada dadas las medias.

    vida_media      vida media del decaimiento, en días.
    ridge           penalización de ataque y defensa (prior N(0, 1/ridge) en escala logarítmica).
    ridge_local     None = sólo ventaja de local común; número = además un desvío por equipo `hl`
                    encogido hacia cero con esa penalización (efecto aleatorio).
    fase            True = dos efectos de liguilla (todo lo que no es fase regular): sobre el total de
                    goles (f_tot) y sobre la ventaja de local (f_loc), con penalización ridge_fase.
    peso_liguilla   factor del peso de los partidos de liguilla (1 = igual que los demás).
    olvido_torneo   factor adicional del peso por cada cambio de torneo entre el partido y el corte
                    (1 = sin olvido extra; los planteles cambian en cada receso).
    w_goles         el "resultado" de cada partido es w*goles + (1-w)*xg aproximado por tiros (regresión
                    lineal ponderada de goles sobre tiros fuera de puerta y tiros a puerta, sólo con el
                    historial); donde no hay estadísticas se usan los goles. 1 = sólo goles.
    ventana_dias    se ignoran partidos más viejos (por omisión 10 vidas medias: peso < 0.001).
    Un equipo sin partidos previos vale el promedio. Los resultados de escritorio se excluyen.
    """
    familia = "dc"

    def __init__(self, vida_media: float = 730.0, ridge: float = 4.0, ridge_local: float | None = None,
                 fase: bool = False, ridge_fase: float = 50.0, peso_liguilla: float = 1.0,
                 olvido_torneo: float = 1.0, w_goles: float = 1.0, ventana_dias: float | None = None,
                 nombre: str | None = None, familia: str | None = None):
        self.vida_media, self.ridge = float(vida_media), float(ridge)
        self.ridge_local = None if ridge_local is None else float(ridge_local)
        self.fase, self.ridge_fase = bool(fase), float(ridge_fase)
        self.peso_liguilla, self.olvido_torneo, self.w_goles = float(peso_liguilla), float(olvido_torneo), float(w_goles)
        self.ventana_dias = float(ventana_dias) if ventana_dias is not None else 10.0 * self.vida_media
        if familia:
            self.familia = familia
        self.nombre = nombre or f"dc_vm{self.vida_media:g}_r{self.ridge:g}"
        self.hiperparametros = {
            "vida_media": self.vida_media, "ridge": self.ridge, "ridge_local": self.ridge_local,
            "fase": self.fase, "ridge_fase": self.ridge_fase if self.fase else None,
            "peso_liguilla": self.peso_liguilla, "olvido_torneo": self.olvido_torneo,
            "w_goles": self.w_goles, "ventana_dias": self.ventana_dias, "rho": "perfilada"}
        self.c = self.h = None
        self.atk: dict[str, float] = {}
        self.dfn: dict[str, float] = {}
        self.hl: dict[str, float] = {}
        self.f_tot = self.f_loc = 0.0
        self.rho = 0.0
        self.xg_coef = None
        self.iteraciones = 0

    # ------------------------------------------------------------------------------------------
    def _objetivo(self, hist, ok, w):
        """Goles o mezcla de goles y xg aproximado (sólo historial) de los partidos `ok`."""
        gl = hist["gl"].to_numpy(float)[ok]
        gv = hist["gv"].to_numpy(float)[ok]
        if self.w_goles >= 1.0:
            return gl, gv, gl, gv
        tl, tv = hist["tiros_l"].to_numpy(float)[ok], hist["tiros_v"].to_numpy(float)[ok]
        pl, pv = hist["tiros_puerta_l"].to_numpy(float)[ok], hist["tiros_puerta_v"].to_numpy(float)[ok]
        con = np.isfinite(tl) & np.isfinite(tv) & np.isfinite(pl) & np.isfinite(pv)
        yl, yv = gl.copy(), gv.copy()
        if con.sum() >= 150:
            fuera = np.r_[np.clip(tl - pl, 0, None)[con], np.clip(tv - pv, 0, None)[con]]
            puerta = np.r_[pl[con], pv[con]]
            goles = np.r_[gl[con], gv[con]]
            rw = np.sqrt(np.r_[w[con], w[con]])
            A = np.column_stack([np.ones(len(goles)), fuera, puerta])
            coef, *_ = np.linalg.lstsq(A * rw[:, None], goles * rw, rcond=None)
            self.xg_coef = tuple(float(x) for x in coef)
            xl = np.clip(coef[0] + coef[1] * np.clip(tl - pl, 0, None) + coef[2] * pl, 0.05, None)
            xv = np.clip(coef[0] + coef[1] * np.clip(tv - pv, 0, None) + coef[2] * pv, 0.05, None)
            yl[con] = self.w_goles * gl[con] + (1 - self.w_goles) * xl[con]
            yv[con] = self.w_goles * gv[con] + (1 - self.w_goles) * xv[con]
        return yl, yv, gl, gv

    def ajustar(self, hist, corte):
        f_ns = hist["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
        edad = (corte.value - f_ns) / 86400e9
        ok = hist["evaluable"].to_numpy() & (edad <= self.ventana_dias)
        if not ok.any():
            raise ValueError("DixonColes: no hay historial antes del corte")
        loc, vis = hist["local"].to_numpy()[ok], hist["visitante"].to_numpy()[ok]
        n = len(loc)
        cod, equipos = pd.factorize(np.concatenate([loc, vis]))
        il, iv, ne = cod[:n], cod[n:], len(equipos)
        lig = (hist["fase"].to_numpy()[ok] != "regular").astype(float)
        w = 0.5 ** (edad[ok] / self.vida_media)
        if self.peso_liguilla != 1.0:
            w = w * np.where(lig > 0, self.peso_liguilla, 1.0)
        if self.olvido_torneo != 1.0:
            cambios = orden_de_corte(corte) - orden_de_fechas(hist["fecha_local"])[ok]
            w = w * self.olvido_torneo ** np.clip(cambios, 0, None)
        yl, yv, gl, gv = self._objetivo(hist, ok, w)

        # --- matriz de diseño rala: filas 0..n-1 = goles del local; n..2n-1 = goles de la visita ---
        r = np.arange(n)
        o_hl = 2 + 2 * ne
        o_f = o_hl + (ne if self.ridge_local is not None else 0)
        p = o_f + (2 if self.fase else 0)
        fil = [r, r, r, r, n + r, n + r, n + r]
        col = [np.zeros(n, int), np.ones(n, int), 2 + il, 2 + ne + iv, np.zeros(n, int), 2 + iv, 2 + ne + il]
        val = [np.ones(n)] * 7
        if self.ridge_local is not None:
            fil.append(r), col.append(o_hl + il), val.append(np.ones(n))
        if self.fase:
            fil += [r, r, n + r]
            col += [np.full(n, o_f), np.full(n, o_f + 1), np.full(n, o_f)]
            val += [lig, lig, lig]
        X = sparse.csr_matrix((np.concatenate(val), (np.concatenate(fil), np.concatenate(col))), shape=(2 * n, p))
        pen = np.zeros(p)
        pen[2:2 + 2 * ne] = self.ridge
        if self.ridge_local is not None:
            pen[o_hl:o_hl + ne] = self.ridge_local
        if self.fase:
            pen[o_f:o_f + 2] = self.ridge_fase
        y, ww = np.concatenate([yl, yv]), np.concatenate([w, w])

        theta0 = np.zeros(p)
        if self.c is None:
            theta0[0] = math.log(max(float(ww @ y) / float(ww.sum()), 1e-6))
        else:                                              # arranque en caliente con el ajuste anterior
            theta0[0], theta0[1] = self.c, self.h
            theta0[2:2 + ne] = [self.atk.get(e, 0.0) for e in equipos]
            theta0[2 + ne:2 + 2 * ne] = [self.dfn.get(e, 0.0) for e in equipos]
            if self.ridge_local is not None:
                theta0[o_hl:o_hl + ne] = [self.hl.get(e, 0.0) for e in equipos]
            if self.fase:
                theta0[o_f], theta0[o_f + 1] = self.f_tot, self.f_loc
        theta, self.iteraciones = newton_poisson(X, y, ww, pen, theta0)

        self.c, self.h = float(theta[0]), float(theta[1])
        self.atk = dict(zip(equipos, theta[2:2 + ne].tolist()))
        self.dfn = dict(zip(equipos, theta[2 + ne:2 + 2 * ne].tolist()))
        self.hl = dict(zip(equipos, theta[o_hl:o_hl + ne].tolist())) if self.ridge_local is not None else {}
        self.f_tot, self.f_loc = (float(theta[o_f]), float(theta[o_f + 1])) if self.fase else (0.0, 0.0)
        eta = X @ theta
        self.rho = estimar_rho(np.exp(eta[:n]), np.exp(eta[n:]), gl, gv, w, self.rho)

    def lambdas(self, local: str, visitante: str, liguilla: bool = False) -> tuple[float, float]:
        """(goles esperados del local, de la visita); un equipo nunca visto vale el promedio."""
        a, d = self.atk, self.dfn
        ft = self.f_tot if liguilla else 0.0
        fl = self.f_loc if liguilla else 0.0
        return (math.exp(self.c + self.h + a.get(local, 0.0) + d.get(visitante, 0.0) + self.hl.get(local, 0.0) + ft + fl),
                math.exp(self.c + a.get(visitante, 0.0) + d.get(local, 0.0) + ft))

    def predecir(self, partidos):
        out = []
        for loc, vis, fase in zip(partidos["local"], partidos["visitante"], partidos["fase"]):
            ll, lv = self.lambdas(loc, vis, fase != "regular")
            out.append({"lam_l": ll, "lam_v": lv, "rho": self.rho})
        return out


# ==================================================================================================
# C3: Elo con margen de goles
# ==================================================================================================
class Elo(Modelo):
    """
    Elo de clubes: tras cada partido R_local += K*G*(S - E), R_visita -= lo mismo, con
    E = 1 / (1 + 10^(-(R_local + H - R_visita)/400)), S = 1 / 0.5 / 0 y G el multiplicador por margen
    de goles del Elo mundial (1 hasta un gol de diferencia, 1.5 con dos, (11 + dif)/8 con tres o más).
    La ventaja de local H (en puntos Elo) se actualiza despacio con el mismo residuo. Al cambiar de
    torneo, los equipos activos regresan una fracción `regresion` hacia su media. Un equipo nuevo
    arranca `castigo_nuevo` puntos bajo la media de los activos.
    Conversión a goles: dos regresiones de Poisson, log lam_l = a_l + b_l*x y log lam_v = a_v + b_v*x con
    x = (R_local - R_visita)/400 ANTES de cada partido pasado; se reajustan al inicio de cada torneo
    sólo con el pasado (ventana `ventana_dias`, sin los primeros `quemado` torneos), y con ellas rho.
    El estado se actualiza de forma incremental (sólo los partidos nuevos del historial).
    """
    familia = "elo"

    def __init__(self, k: float = 20.0, regresion: float = 0.15, margen: bool = True,
                 ventaja_inicial: float = 60.0, k_ventaja: float = 1.0, castigo_nuevo: float = 50.0,
                 ventana_dias: float = 3650.0, quemado: int = 6, nombre: str | None = None):
        self.k, self.regresion, self.margen = float(k), float(regresion), bool(margen)
        self.ventaja_inicial, self.k_ventaja, self.castigo_nuevo = float(ventaja_inicial), float(k_ventaja), float(castigo_nuevo)
        self.ventana_dias, self.quemado = float(ventana_dias), int(quemado)
        self.nombre = nombre or f"elo_k{self.k:g}_reg{self.regresion:g}"
        self.hiperparametros = {"k": self.k, "regresion": self.regresion, "margen": self.margen,
                                "ventaja_inicial": self.ventaja_inicial, "k_ventaja": self.k_ventaja,
                                "castigo_nuevo": self.castigo_nuevo, "ventana_dias": self.ventana_dias,
                                "quemado": self.quemado}
        self._reiniciar()

    def _reiniciar(self):
        self.R: dict[str, float] = {}
        self.ultimo: dict[str, int] = {}          # último ordinal de torneo en que jugó cada equipo
        self.H = self.ventaja_inicial
        self.n_proc, self.ultimo_id, self.ord_estado, self.ord_inicial = 0, None, None, None
        self.x, self.gl, self.gv, self.f_ns, self.ord = [], [], [], [], []
        self.coef, self.rho, self.ord_coef = None, 0.0, None

    def _media_activos(self, orden_previo):
        vals = [r for e, r in self.R.items() if self.ultimo.get(e, -1) >= orden_previo]
        return float(np.mean(vals)) if vals else 1500.0

    def _cambio_torneo(self, nuevo: int):
        """Regresión a la media de los equipos que jugaron el torneo anterior."""
        if self.ord_estado is not None and self.regresion > 0:
            m = self._media_activos(self.ord_estado)
            for e in self.R:
                if self.ultimo.get(e, -1) >= self.ord_estado:
                    self.R[e] = m + (1.0 - self.regresion) * (self.R[e] - m)
        self.ord_estado = nuevo

    def _procesar(self, hist):
        nuevos = hist.iloc[self.n_proc:]
        if not len(nuevos):
            return
        ordenes = orden_de_fechas(nuevos["fecha_local"])
        f_ns = nuevos["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
        for loc, vis, gl, gv, ev, o, f in zip(nuevos["local"].to_numpy(), nuevos["visitante"].to_numpy(),
                                               nuevos["gl"].to_numpy(), nuevos["gv"].to_numpy(),
                                               nuevos["evaluable"].to_numpy(), ordenes, f_ns):
            if not ev:
                continue
            if self.ord_inicial is None:
                self.ord_inicial = int(o)
            if self.ord_estado is None or o > self.ord_estado:
                self._cambio_torneo(int(o))
            for e in (loc, vis):
                if e not in self.R:                        # en el primer torneo del historial todos valen 1500
                    self.R[e] = (1500.0 if o == self.ord_inicial
                                 else self._media_activos(self.ord_estado - 1) - self.castigo_nuevo)
                self.ultimo[e] = int(o)
            d = self.R[loc] - self.R[vis]
            self.x.append(d / 400.0), self.gl.append(gl), self.gv.append(gv), self.f_ns.append(f), self.ord.append(o)
            E = 1.0 / (1.0 + 10.0 ** (-(d + self.H) / 400.0))
            S = 1.0 if gl > gv else (0.5 if gl == gv else 0.0)
            dif = abs(gl - gv)
            G = 1.0 if (not self.margen or dif <= 1) else (1.5 if dif == 2 else (11.0 + dif) / 8.0)
            delta = self.k * G * (S - E)
            self.R[loc] += delta
            self.R[vis] -= delta
            self.H += self.k_ventaja * (S - E)
        self.n_proc = len(hist)
        self.ultimo_id = int(hist["id"].iloc[-1])

    def _reajustar_conversion(self, corte):
        x, gl, gv = np.array(self.x), np.array(self.gl, float), np.array(self.gv, float)
        f_ns, o = np.array(self.f_ns), np.array(self.ord)
        sel = ((corte.value - f_ns) / 86400e9 <= self.ventana_dias) & (o >= o.min() + self.quemado)
        if sel.sum() < 300:
            sel = np.ones(len(x), bool)
        X = np.column_stack([np.ones(sel.sum()), x[sel]])
        w, pen = np.ones(sel.sum()), np.zeros(2)
        cl, _ = newton_poisson(X, gl[sel], w, pen, np.array([math.log(max(gl[sel].mean(), 1e-6)), 0.0]))
        cv, _ = newton_poisson(X, gv[sel], w, pen, np.array([math.log(max(gv[sel].mean(), 1e-6)), 0.0]))
        self.coef = (float(cl[0]), float(cl[1]), float(cv[0]), float(cv[1]))
        self.rho = estimar_rho(np.exp(X @ cl), np.exp(X @ cv), gl[sel], gv[sel], w, self.rho)

    def ajustar(self, hist, corte):
        if self.n_proc and (len(hist) < self.n_proc or int(hist["id"].iloc[self.n_proc - 1]) != self.ultimo_id):
            self._reiniciar()                              # el historial no continúa el anterior: desde cero
        self._procesar(hist)
        actual = orden_de_corte(corte)
        if self.coef is None or actual != self.ord_coef:
            self._reajustar_conversion(corte)
            self.ord_coef = actual
        self._ord_corte = actual

    def predecir(self, partidos):
        # copia de trabajo: si el corte abre un torneo nuevo, la regresión a la media se aplica ya
        R = self.R
        if self.ord_estado is not None and self._ord_corte > self.ord_estado and self.regresion > 0:
            m = self._media_activos(self.ord_estado)
            R = {e: (m + (1.0 - self.regresion) * (r - m)) if self.ultimo.get(e, -1) >= self.ord_estado else r
                 for e, r in self.R.items()}
        nuevo = (self._media_activos(self.ord_estado) if self.ord_estado is not None else 1500.0) - self.castigo_nuevo
        al, bl, av, bv = self.coef
        out = []
        for loc, vis in zip(partidos["local"], partidos["visitante"]):
            x = (R.get(loc, nuevo) - R.get(vis, nuevo)) / 400.0
            out.append({"lam_l": math.exp(al + bl * x), "lam_v": math.exp(av + bv * x), "rho": self.rho, "x_elo_dif": 400.0 * x})
        return out


# ==================================================================================================
# C5: corrección log-lineal con pocas variables
# ==================================================================================================
GRUPOS_AJUSTE = {                       # escogidas de antemano por lo que ya se sabe (VARIABLES.md §5.1)
    "viaje": ["sede_viaje_km_v"],                                   # km que viaja el visitante
    "rotacion": ["once_previa_cambios_v"],                          # cambios en el once previo del visitante
    "tiros": ["juego10_tiros_f_l", "juego10_tiros_c_l",             # tiros a favor y concedidos, últimos 10
              "juego10_tiros_f_v", "juego10_tiros_c_v"],
    "suspension": ["susp_imp_l", "susp_imp_v"],                     # ausencias por suspensión (con importancia)
    "altitud": ["sede_alt_dif_v"],                                  # diferencia de altitud que sufre el visitante
}
_tablas_variables: dict = {}


def tabla_variables(corte: str = "bloque") -> pd.DataFrame:
    """Tabla de variables a la fecha (modelo/variables.py), indexada por id; se lee una sola vez."""
    if corte not in _tablas_variables:
        cols = ["id"] + [c for g in GRUPOS_AJUSTE.values() for c in g]
        _tablas_variables[corte] = pd.read_parquet(RUTA_VARIABLES[corte], columns=cols).set_index("id")
    return _tablas_variables[corte]


class Ajuste(Modelo):
    """
    Toma las lambdas de un modelo base y las corrige con pocas variables estandarizadas z:
        lam_l' = lam_l * exp(b0_l + z·b_l)        lam_v' = lam_v * exp(b0_v + z·b_v)
    Los coeficientes salen de dos regresiones de Poisson (goles del local y de la visita) con las lambdas
    base como compensación (offset) y penalización ridge fuerte sobre b (no sobre b0). Se reajustan al
    inicio de cada torneo sólo con partidos pasados, usando para cada uno la lambda base que se habría
    pronosticado en su propio bloque (recorrido interno del modelo base desde `inicio`; nada posterior).
    Medias y desviaciones para estandarizar salen de la misma muestra pasada; un dato faltante vale 0
    (la media). Las variables vienen de la tabla a la fecha por bloque (sin fuga por construcción).

    base     modelo que da lam_l, lam_v, rho (por omisión DixonColes()).
    ridge    penalización de cada coeficiente estandarizado (prior N(0, 1/ridge)).
    grupos   grupos de GRUPOS_AJUSTE que entran (por omisión todos).
    """
    familia = "ajuste"

    def __init__(self, base: Modelo | None = None, ridge: float = 1000.0, grupos: list[str] | None = None,
                 inicio: str = "2011-07-01", tabla: str = "bloque", nombre: str | None = None):
        self.base = base if base is not None else DixonColes()
        self.ridge = float(ridge)
        self.grupos = list(grupos) if grupos is not None else list(GRUPOS_AJUSTE)
        self.columnas = [c for g in self.grupos for c in GRUPOS_AJUSTE[g]]
        self.inicio = pd.Timestamp(inicio, tz="UTC")
        self.tabla = tabla
        self.nombre = nombre or f"ajuste_r{self.ridge:g}"
        self.hiperparametros = {"base": self.base.nombre, "base_hiper": self.base.hiperparametros,
                                "ridge": self.ridge, "grupos": self.grupos, "columnas": self.columnas,
                                "inicio": str(self.inicio.date()), "tabla": tabla}
        self._lam: dict[int, tuple[float, float]] = {}       # id -> lambdas base pronosticadas en su bloque
        self._ord_coef = None
        self.media = self.desv = self.b_l = self.b_v = None
        self.bitacora: list[dict] = []                       # coeficientes de cada reajuste

    def _recorrer_base(self, hist):
        """Lambdas base, bloque por bloque, de los partidos del historial que aún no las tienen."""
        ids = hist["id"].to_numpy()
        f = hist["fecha_utc"]
        falta = (f >= self.inicio).to_numpy() & hist["evaluable"].to_numpy() & ~np.isin(ids, list(self._lam))
        if not falta.any():
            return
        f_ns = f.to_numpy(dtype="datetime64[ns]").astype("int64")
        for corte_b, g in hist[falta].groupby("corte_bloque", sort=True):
            k = int(np.searchsorted(f_ns, corte_b.value, side="left"))
            self.base.ajustar(hist.iloc[:k], corte_b)
            for i, pr in zip(g["id"].to_numpy(), self.base.predecir(g[datos.COLS_PREPARTIDO].reset_index(drop=True))):
                self._lam[int(i)] = (float(pr["lam_l"]), float(pr["lam_v"]))

    def _z(self, ids, directas: pd.DataFrame | None = None):
        """
        Variables estandarizadas de los partidos `ids` (de la tabla a la fecha). Si `directas` trae alguna
        de las columnas (p. ej. un cruce hipotético de liguilla armado por el simulador, sin id en la
        tabla), esos valores tienen prioridad. Lo que falte vale 0 (la media): sin corrección.
        """
        Z = tabla_variables(self.tabla).reindex(ids)[self.columnas].to_numpy(float)
        if directas is not None:
            for j, c in enumerate(self.columnas):
                if c in directas.columns:
                    Z[:, j] = directas[c].to_numpy(float)
        z = (Z - self.media) / self.desv
        return np.where(np.isfinite(z), z, 0.0)

    def _reajustar(self, hist, corte):
        h = hist[hist["evaluable"].to_numpy() & np.isin(hist["id"].to_numpy(), list(self._lam))]
        ids = h["id"].to_numpy()
        Z = tabla_variables(self.tabla).reindex(ids)[self.columnas].to_numpy(float)
        self.media = np.nanmean(Z, axis=0)
        self.desv = np.nanstd(Z, axis=0)
        self.desv = np.where(self.desv > 0, self.desv, 1.0)
        z = self._z(ids)
        lam = np.array([self._lam[int(i)] for i in ids])
        X = np.column_stack([np.ones(len(ids)), z])
        pen = np.r_[0.0, np.full(z.shape[1], self.ridge)]
        coefs = []
        for j, y in ((0, h["gl"].to_numpy(float)), (1, h["gv"].to_numpy(float))):
            # offset: se resuelve con pesos w = lam (y/lam como respuesta) -> misma verosimilitud
            b, _ = newton_poisson(X, y / lam[:, j], lam[:, j], pen, np.zeros(X.shape[1]))
            coefs.append(b)
        self.b_l, self.b_v = coefs
        self.bitacora.append({"corte": str(corte.date()), "n": int(len(ids)),
                              "b0_l": float(self.b_l[0]), "b0_v": float(self.b_v[0]),
                              **{f"l__{c}": float(v) for c, v in zip(self.columnas, self.b_l[1:])},
                              **{f"v__{c}": float(v) for c, v in zip(self.columnas, self.b_v[1:])}})

    def ajustar(self, hist, corte):
        self._recorrer_base(hist)
        actual = orden_de_corte(corte)
        if self.b_l is None or actual != self._ord_coef:
            self._reajustar(hist, corte)
            self._ord_coef = actual
        self.base.ajustar(hist, corte)

    def predecir(self, partidos):
        base = self.base.predecir(partidos)
        z = self._z(partidos["id"].to_numpy(), partidos)
        fl = np.exp(self.b_l[0] + z @ self.b_l[1:])
        fv = np.exp(self.b_v[0] + z @ self.b_v[1:])
        return [{"lam_l": pr["lam_l"] * a, "lam_v": pr["lam_v"] * b, "rho": pr.get("rho", 0.0),
                 "x_factor_l": float(a), "x_factor_v": float(b)} for pr, a, b in zip(base, fl, fv)]


# ==================================================================================================
# C6: ensamble
# ==================================================================================================
class Ensamble(Modelo):
    """
    Promedio simple de varios modelos. modo="lambdas": media aritmética de lam_l, lam_v y rho (una sola
    matriz Dixon-Coles); modo="prob": media de las matrices de marcadores (y por tanto del 1X2).
    """
    familia = "ensamble"

    def __init__(self, modelos: list[Modelo], modo: str = "lambdas", nombre: str | None = None):
        if modo not in ("lambdas", "prob"):
            raise ValueError("modo debe ser 'lambdas' o 'prob'")
        self.modelos, self.modo = list(modelos), modo
        self.nombre = nombre or f"ens_{modo}_" + "+".join(m.nombre for m in self.modelos)
        self.hiperparametros = {"modo": modo, "modelos": [m.nombre for m in self.modelos],
                                "hiper": {m.nombre: m.hiperparametros for m in self.modelos}}

    def ajustar(self, hist, corte):
        for m in self.modelos:
            m.ajustar(hist, corte)

    def predecir(self, partidos):
        preds = [m.predecir(partidos) for m in self.modelos]
        out = []
        for fila in zip(*preds):
            ll = float(np.mean([p["lam_l"] for p in fila]))
            lv = float(np.mean([p["lam_v"] for p in fila]))
            if self.modo == "lambdas":
                out.append({"lam_l": ll, "lam_v": lv, "rho": float(np.mean([p.get("rho", 0.0) for p in fila]))})
            else:
                M = np.mean([arnes.matriz_marcadores(p["lam_l"], p["lam_v"], p.get("rho", 0.0)) for p in fila], axis=0)
                out.append({"M": M / M.sum(), "lam_l": ll, "lam_v": lv})
        return out


# ==================================================================================================
# Finalistas (hiperparámetros fijos, elegidos en DESARROLLO; ver informes/candidatos.md)
# ==================================================================================================
GRUPOS_FINALES = ["viaje", "rotacion", "tiros"]      # suspensión y altitud no aportaron en la ablación


def _dc() -> DixonColes:
    return DixonColes(vida_media=365, ridge=4, nombre="dc")


def _elo() -> Elo:
    return Elo(k=8, regresion=0.15, nombre="elo")


def _ajuste() -> "Ajuste":
    return Ajuste(_dc(), ridge=1000, grupos=GRUPOS_FINALES, nombre="ajuste")


def finalistas() -> dict[str, Modelo]:
    """
    El mejor de cada candidato C1 a C6 con sus hiperparámetros fijos, como {nombre: instancia nueva}. El
    nombre es el del archivo en modelo/pred/. ESTADO dice cuáles se recomiendan: "dc2" y "tiros" quedan
    como referencia (no superaron a "dc" por más de 2 errores estándar; "tiros" es peor).
    """
    return {
        "dc": _dc(),
        "dc2": DixonColes(vida_media=365, ridge=4, ridge_local=30, nombre="dc2", familia="dc2"),
        "elo": _elo(),
        "tiros": DixonColes(vida_media=365, ridge=4, w_goles=0.7, nombre="tiros", familia="tiros"),
        "ajuste": _ajuste(),
        "ensamble": Ensamble([_ajuste(), _elo()], modo="lambdas", nombre="ensamble"),
    }


ESTADO: dict[str, str] = {
    "dc": "finalista",
    "dc2": "referencia: la mejora sobre dc no pasa de 2 errores estándar",
    "elo": "finalista (componente del ensamble)",
    "tiros": "descartado: peor que dc",
    "ajuste": "finalista: el mejor en resultado (1X2)",
    "ensamble": "finalista: el mejor en marcador exacto; en 1X2 queda detrás de ajuste",
}

DESCRIPCION: dict[str, str] = {
    "dc": ("Cada equipo tiene una fuerza de ataque y una de defensa que se estiman con sus goles; los partidos "
           "recientes pesan más (uno de hace un año cuenta la mitad).\nSe suma una ventaja de local igual para "
           "todos y un ajuste a los marcadores bajos (0-0, 1-0, 0-1, 1-1), que en el futbol salen más de lo que diría el azar."),
    "dc2": ("Lo mismo que dc, pero cada equipo tiene además su propia ventaja de local (su cancha puede pesar más o "
            "menos que el promedio), estimada con cautela.\nEn el historial casi no cambió los pronósticos: la "
            "diferencia frente a dc cabe dentro del ruido."),
    "elo": ("Cada equipo tiene una calificación que sube cuando gana y baja cuando pierde, más si es por goleada o "
            "contra un rival fuerte; en cada receso se acerca un poco al promedio.\nLa diferencia de calificaciones "
            "se traduce en goles esperados con una regla aprendida sólo de partidos pasados."),
    "tiros": ("Como dc, pero la fuerza de cada equipo se mide con una mezcla de 70% sus goles y 30% los goles que "
              "'merecía' según sus tiros.\nEn el historial pronosticó peor que usar sólo los goles: los tiros sirven "
              "más como señal aparte (ver ajuste) que como sustituto del marcador."),
    "ajuste": ("Parte de los goles esperados de dc y los corrige un poco con tres datos previos al partido: cuántos "
               "tiros genera y concede cada equipo en sus últimos 10 juegos, cuántos kilómetros viaja el visitante y "
               "cuánto viene cambiando su alineación.\nEl tamaño de cada corrección se aprende sólo con partidos "
               "anteriores y se revisa al inicio de cada torneo."),
    "ensamble": ("Promedia los goles esperados de dos modelos que miran distinto: ajuste (fuerza reciente más tiros, "
                 "viaje y rotación) y elo (calificación de largo plazo).\nEs un poco más prudente: acierta algo "
                 "mejor el marcador exacto, pero pronostica el ganador algo peor que ajuste solo."),
}
