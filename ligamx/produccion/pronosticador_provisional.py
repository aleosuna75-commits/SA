# -*- coding: utf-8 -*-
"""
Pronosticador PROVISIONAL: cumple el contrato de modelo/pronostico.py con la línea base
`base.PoissonSimple` (ataque y defensa por equipo, ventaja de local común, rho = 0).

Sirve mientras no exista modelo/campeon.json; produccion.obtener_pronosticador() elige sola.

Incertidumbre de los parámetros: aproximación normal de la verosimilitud ponderada y penalizada,
theta ~ N(theta_hat, H^-1), con H la hessiana que usa el propio ajuste (X' diag(w·mu) X + ridge).
Como los pesos decaen con la antigüedad, H^-1 equivale a la posterior de una verosimilitud
descontada: es más ancha que la varianza muestral del estimador y absorbe, de forma aproximada,
que la fuerza de los equipos cambia con el tiempo.

Límites de la versión provisional (el modelo campeón puede quitarlos): la ventaja de local es la
misma para todos los equipos y sedes, y la fase "liguilla" no cambia nada (misma malla).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from modelo import base, datos

N_MUESTRAS_EE = 4000            # muestras para los errores estándar de fuerzas()
SEMILLA_EE = 20261110


def _a_utc(corte) -> pd.Timestamp:
    """Instante UTC; None = ahora; una fecha sin zona se toma como hora de la Ciudad de México."""
    if corte is None:
        return pd.Timestamp.now(tz="UTC")
    t = pd.Timestamp(corte)
    return (t.tz_localize(datos.ZONA) if t.tzinfo is None else t).tz_convert("UTC")


def _pct(mult: float) -> str:
    """'12% más' / '8% menos' a partir de un multiplicador."""
    d = (mult - 1.0) * 100.0
    return f"{abs(d):.0f}% {'más' if d >= 0 else 'menos'}"


class Pronosticador:
    """
    Contrato:
      equipos            los equipos del torneo en curso, en orden alfabético (el de `sorted`).
      partidos(df)       lambdas, rho y explicación de cada partido por jugar.
      malla(n, fase, s)  lambdas de todos contra todos; k = 0 puntual, k >= 1 muestras de parámetros.
      fuerzas()          ataque, defensa, rating y ventaja de local por equipo, con error estándar.
    """

    nombre = "provisional_poisson_simple"

    def __init__(self, corte=None, modelo=None, partidos: pd.DataFrame | None = None):
        df = datos.cargar() if partidos is None else partidos
        self.corte = _a_utc(corte)
        hist = df[(df["estado"] == "jugado") & (df["fecha_utc"] < self.corte)].reset_index(drop=True)
        if hist.empty:
            raise ValueError("Pronosticador: no hay partidos jugados antes del corte")
        self.modelo = modelo if modelo is not None else base.PoissonSimple()
        self.modelo.ajustar(hist, self.corte)
        self.n_historia = int(len(hist))
        self.rho = 0.0

        # torneo en curso: el del primer partido no anterior al corte; si no hay, el último jugado
        vivos = df[(df["fecha_utc"] >= self.corte) & df["estado"].isin(["programado", "jugado", "en_juego"])]
        self.torneo = str(vivos["torneo"].iloc[0]) if len(vivos) else str(hist["torneo"].iloc[-1])
        reg = df[(df["torneo"] == self.torneo) & (df["fase"] == "regular") & (df["estado"] != "cancelado")]
        self.equipos: list[str] = sorted(set(reg["local"]) | set(reg["visitante"]))

        self._covarianza(hist)

    # ---------------------------------------------------------------------------------------------
    def _covarianza(self, hist: pd.DataFrame) -> None:
        """Hessiana del ajuste en theta_hat (mismos partidos y pesos que PoissonSimple) y su inversa."""
        m = self.modelo
        edad = (self.corte - hist["fecha_utc"]).dt.total_seconds().to_numpy() / 86400.0
        ok = hist["evaluable"].to_numpy() & (edad <= m.ventana_dias)
        self._eq_modelo = list(m.atk.keys())                      # mismo orden que theta
        ix = {e: i for i, e in enumerate(self._eq_modelo)}
        ne = len(ix)
        il = np.fromiter((ix[e] for e in hist["local"].to_numpy()[ok]), int, int(ok.sum()))
        iv = np.fromiter((ix[e] for e in hist["visitante"].to_numpy()[ok]), int, int(ok.sum()))
        w = 0.5 ** (edad[ok] / m.vida_media_dias)
        n, p = len(il), 2 + 2 * ne
        r = np.arange(n)
        X = np.zeros((2 * n, p))
        X[:, 0] = 1.0
        X[:n, 1] = 1.0
        X[r, 2 + il] = 1.0
        X[r, 2 + ne + iv] = 1.0
        X[n + r, 2 + iv] = 1.0
        X[n + r, 2 + ne + il] = 1.0
        self.theta = np.r_[m.c, m.h, [m.atk[e] for e in self._eq_modelo], [m.dfn[e] for e in self._eq_modelo]]
        mu = np.exp(X @ self.theta)
        ww = np.concatenate([w, w])
        H = (X * (ww * mu)[:, None]).T @ X
        H[np.diag_indices(p)] += np.r_[0.0, 0.0, np.full(2 * ne, m.ridge)] + 1e-10
        self.cov = np.linalg.inv(H)
        self.cov = (self.cov + self.cov.T) / 2.0
        self._chol = np.linalg.cholesky(self.cov + 1e-12 * np.eye(p))
        self.n_efectivo = float(w.sum())
        # posiciones en theta de los equipos del torneo (-1 = equipo sin historia: promedio con prior)
        self._pos = np.array([ix.get(e, -1) for e in self.equipos])

    def _muestras(self, n: int, semilla: int) -> np.ndarray:
        """(n, p): fila 0 = theta_hat; filas 1.. = theta_hat + L z (aproximación normal). Semilla fija."""
        th = np.repeat(self.theta[None, :], max(int(n), 1), axis=0)
        if n > 1:
            rng = np.random.default_rng(semilla)
            th[1:] += rng.standard_normal((n - 1, len(self.theta))) @ self._chol.T
        return th

    def _atk_dfn(self, th: np.ndarray, semilla: int) -> tuple[np.ndarray, np.ndarray]:
        """Ataque y defensa (n, 18) de los equipos del torneo para cada muestra de theta."""
        ne = len(self._eq_modelo)
        pos = np.where(self._pos >= 0, self._pos, 0)
        atk, dfn = th[:, 2 + pos].copy(), th[:, 2 + ne + pos].copy()
        nuevos = self._pos < 0
        if nuevos.any():                                 # sin historia: prior N(0, 1/ridge), media 0
            rng = np.random.default_rng(semilla + 1)
            s = 1.0 / math.sqrt(self.modelo.ridge)
            z = rng.standard_normal((2, th.shape[0], int(nuevos.sum()))) * s
            z[:, 0, :] = 0.0
            atk[:, nuevos], dfn[:, nuevos] = z[0], z[1]
        return atk, dfn

    # ---------------------------------------------------------------------------------------------
    def partidos(self, df: pd.DataFrame) -> list[dict]:
        """Un dict por partido de `df` (mismo orden): id, lam_l, lam_v, rho, lam_base y explica."""
        m = self.modelo
        base_l = math.exp(m.c)
        out = []
        for pid, loc, vis in zip(df["id"], df["local"], df["visitante"]):
            ll, lv = m.lambdas(loc, vis)
            aL, dL = math.exp(m.atk.get(loc, 0.0)), math.exp(m.dfn.get(loc, 0.0))
            aV, dV = math.exp(m.atk.get(vis, 0.0)), math.exp(m.dfn.get(vis, 0.0))
            h = math.exp(m.h)
            explica = [
                {"factor": f"Ataque de {loc}", "detalle": f"anota {_pct(aL)} que un equipo promedio",
                 "efecto_l": aL, "efecto_v": 1.0},
                {"factor": f"Defensa de {vis}", "detalle": f"concede {_pct(dV)} que un equipo promedio",
                 "efecto_l": dV, "efecto_v": 1.0},
                {"factor": f"Ataque de {vis}", "detalle": f"anota {_pct(aV)} que un equipo promedio",
                 "efecto_l": 1.0, "efecto_v": aV},
                {"factor": f"Defensa de {loc}", "detalle": f"concede {_pct(dL)} que un equipo promedio",
                 "efecto_l": 1.0, "efecto_v": dL},
                {"factor": "Ventaja de local", "detalle": f"el local anota {_pct(h)} por jugar en casa "
                                                           "(misma para todos los equipos)",
                 "efecto_l": h, "efecto_v": 1.0},
            ]
            out.append({"id": int(pid), "lam_l": float(ll), "lam_v": float(lv), "rho": self.rho,
                        "lam_base": base_l, "explica": explica})
        return out

    def malla(self, n: int = 1, fase: str = "regular", semilla: int = 0) -> dict:
        """
        {"equipos", "lam_l" [n,18,18], "lam_v" [n,18,18], "rho"}; [k,i,j] = i recibe a j en su sede.
        k = 0 es la estimación puntual; k >= 1 son muestras de theta ~ N(theta_hat, H^-1).
        La diagonal (i = j) no es un partido: queda con un valor finito sin significado.
        `fase` ("regular" o "liguilla") no cambia nada en la versión provisional.
        """
        if fase not in ("regular", "liguilla"):
            raise ValueError("fase debe ser 'regular' o 'liguilla'")
        th = self._muestras(n, semilla)
        atk, dfn = self._atk_dfn(th, semilla)
        c, h = th[:, 0][:, None, None], th[:, 1][:, None, None]
        lam_l = np.exp(c + h + atk[:, :, None] + dfn[:, None, :])
        lam_v = np.exp(c + atk[:, None, :] + dfn[:, :, None])
        return {"equipos": list(self.equipos), "lam_l": lam_l, "lam_v": lam_v, "rho": self.rho}

    def fuerzas(self) -> pd.DataFrame:
        """
        Una fila por equipo (índice): ataque y defensa (multiplicadores respecto al promedio de los
        equipos del torneo; defensa < 1 = concede menos), gf_neutral y gc_neutral (goles esperados
        frente a un rival promedio en cancha neutral, con media ventaja de local para cada lado),
        rating = gf_neutral - gc_neutral, ventaja_local (multiplicador de los goles del local) y
        los errores estándar ee_* (desviación de 4,000 muestras de la aproximación normal).
        """
        th = self._muestras(N_MUESTRAS_EE + 1, SEMILLA_EE)
        atk, dfn = self._atk_dfn(th, SEMILLA_EE)
        atk_c = atk - atk.mean(axis=1, keepdims=True)
        dfn_c = dfn - dfn.mean(axis=1, keepdims=True)
        nivel = th[:, [0]] + 0.5 * th[:, [1]]            # cancha neutral: media ventaja de local
        gf = np.exp(nivel + atk + dfn.mean(axis=1, keepdims=True))
        gc = np.exp(nivel + dfn + atk.mean(axis=1, keepdims=True))
        rating = gf - gc
        vl = np.exp(th[:, 1])
        t = pd.DataFrame({
            "ataque": np.exp(atk_c[0]), "defensa": np.exp(dfn_c[0]),
            "gf_neutral": gf[0], "gc_neutral": gc[0], "rating": rating[0],
            "ventaja_local": vl[0],
            "ee_ataque": np.exp(atk_c[1:]).std(axis=0, ddof=1),
            "ee_defensa": np.exp(dfn_c[1:]).std(axis=0, ddof=1),
            "ee_rating": rating[1:].std(axis=0, ddof=1),
            "ee_ventaja_local": float(vl[1:].std(ddof=1)),
        }, index=pd.Index(self.equipos, name="equipo"))
        return t
