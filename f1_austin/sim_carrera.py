"""Simulador Monte Carlo de carrera (GP EE.UU. 2026).

Cada piloto: posición de salida (grid) + ventaja de ritmo (tanda larga, qualy, forma) que se
convierte en posiciones según la facilidad de rebase del circuito; ruido heterocedástico
(primera vuelta / incidentes, depende de la posición de salida y del circuito) y abandono
(logística sobre fiabilidad del equipo/piloto y tasa de DNF del circuito). Todo se ajusta sólo
con carreras pasadas. Pronóstico = posición media simulada.

Variante usada en producción: MC_VAR = {"is26": False, "gn_inter": True}
(walk-forward 2024-2026: NDCG@10 0.8886 vs 0.8794 del orden de qualy; mejor en los tres años).
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LogisticRegression

FIN = {"Finished", "Lapped"}


def prep(df):
    """Variables por carrera en escala de posiciones (todas conocidas antes de la salida)."""
    d = df.copy()
    g = d.groupby("meeting_key")
    d["n"] = g.driver_number.transform("size")
    d["g"] = d.grid.fillna(d.n)
    d["qp"] = d.q_pos.fillna(d.g)
    # ritmo de tanda larga -> rango 1..n (faltantes: rango de prácticas global)
    lr = d.long_rank_all.copy()
    lr = lr.fillna(d.fp_rank_all).fillna(d.qp)
    d["pace_r"] = d.assign(_x=lr).groupby("meeting_key")._x.rank(method="average")
    # gap de ritmo (s) recortado; faltantes -> percentil 75 de la carrera
    lg = d.long_gap_all.clip(upper=4.0)
    d["lg"] = lg.fillna(d.assign(_x=lg).groupby("meeting_key")._x.transform(lambda s: s.quantile(.75))).fillna(2.0)
    d["qg"] = d.q_gap.clip(upper=3.0).fillna(d.assign(_x=d.q_gap.clip(upper=3)).groupby("meeting_key")._x.transform("max")).fillna(2.0)
    d["form"] = d.r_mean10.fillna(d.team_r_mean5).fillna(d.g)
    d["tform"] = d.team_r_mean5.fillna(d.form)
    d["sp"] = (d.sprint_pos - d.g).fillna(0.0)
    d["has_sp"] = d.sprint_pos.notna().astype(float)
    d["cga"] = d.circ_gain_abs.fillna(3.3)
    d["cgc"] = d.circ_grid_corr.fillna(0.62)
    d["cdnf"] = d.circ_dnf_rate.fillna(0.155)
    d["tfin"] = d.team_finish_rate5.fillna(0.86)
    d["rfin"] = d.r_finish_rate10.fillna(0.86)
    d["gn"] = (d.g - 1) / (d.n - 1)
    return d


def X_media(d, var, como_df=False):
    """Diseño para el cambio de posición esperado (y - grid)."""
    mob = (d.cga - 3.3)            # facilidad de rebase del circuito (centrada)
    cols = {
        "gc": d.g - (d.n + 1) / 2,                 # regresión a la media por estar delante/detrás
        "pace": d.pace_r - d.g,                    # ritmo de carrera vs salida
        "pace_mob": (d.pace_r - d.g) * mob,
        "lg": d.lg, "qg": d.qg,
        "form": d.form - d.g,
        "tform": d.tform - d.g,
        "qpen": d.qp - d.g,                        # sanción / salida fuera de su sitio
        "sp": d.sp,
    }
    if var.get("grid_mob", True):
        cols["gc_mob"] = (d.g - (d.n + 1) / 2) * mob
        cols["form_mob"] = (d.form - d.g) * mob
    if var.get("corr", False):
        cols["pace_corr"] = (d.pace_r - d.g) * (d.cgc - 0.62)
    if var.get("is26", True):
        cols["pace26"] = (d.pace_r - d.g) * (d.year >= 2026)
        cols["form26"] = (d.form - d.g) * (d.year >= 2026)
    if var.get("front", False):
        f3 = (d.g <= 3).astype(float)
        cols["pole"] = (d.g == 1).astype(float)
        cols["front3"] = f3
        cols["form_f3"] = (d.form - d.g) * f3
        cols["pace_f3"] = (d.pace_r - d.g) * f3
    if var.get("gn_inter", False):
        cols["form_gn"] = (d.form - d.g) * d.gn
        cols["pace_gn"] = (d.pace_r - d.g) * d.gn
    if var.get("gn_mob", False):
        cols["form_gn_mob"] = (d.form - d.g) * d.gn * mob
        cols["pace_gn_mob"] = (d.pace_r - d.g) * d.gn * mob
    if var.get("gn_all", False):
        cols["tform_gn"] = (d.tform - d.g) * d.gn
        cols["qpen_gn"] = (d.qp - d.g) * d.gn
        cols["sp_gn"] = d.sp * d.gn
    if var.get("racecraft", False):
        cols["rgain"] = d.r_gain_mean10.fillna(0).clip(-6, 6)
        cols["rgain_gn"] = d.r_gain_mean10.fillna(0).clip(-6, 6) * d.gn
        cols["rcgain"] = d.r_circ_gain.fillna(0).clip(-8, 8)
    if var.get("teamlong", False):
        cols["ltb"] = d.long_team_best.clip(upper=4).fillna(d.lg)
    if var.get("form3", False):
        cols["form3"] = (d.r_mean3.fillna(d.form) - d.g)
        cols["form3_gn"] = (d.r_mean3.fillna(d.form) - d.g) * d.gn
    if var.get("pole", False):
        cols["pole"] = (d.g == 1).astype(float)
    for c in var.get("drop", []):
        cols.pop(c, None)
    X = pd.DataFrame(cols).astype(float)
    return X if como_df else X.values


def X_sigma(d):
    return np.c_[d.gn, d.gn ** 2, d.cga - 3.3]


def X_dnf(d):
    return np.c_[d.tfin, d.rfin, d.cdnf, d.gn, (d.year >= 2026).astype(float)]


class Simulador:
    def __init__(self, var=None):
        self.var = var or {}

    def fit(self, train):
        v = self.var
        d = prep(train)
        w = np.where(d.year >= 2026, v.get("w26", 3.0), np.where(d.year == 2025, 1.5, 1.0))
        dnf = (~d.status.isin(FIN)).astype(int).values
        fin = dnf == 0
        # 1) media: regresión del cambio de posición contra diferencia de ritmo (sólo terminados,
        #    objetivo = puesto entre los que terminan, re-escalado al tamaño de parrilla)
        df_ = d[fin].copy()
        df_["nfin"] = df_.groupby("meeting_key").driver_number.transform("size")
        df_["yfin"] = df_.groupby("meeting_key").race_pos.rank(method="first")
        y = (df_.yfin - 1) * (df_.n - 1) / (df_.nfin - 1).clip(lower=1) + 1 - df_.g
        Xm = X_media(df_, v)
        self.rm = Ridge(alpha=v.get("alpha", 1.0)).fit(Xm, y.values, sample_weight=w[fin])
        res = y.values - self.rm.predict(Xm)
        # 2) ruido heterocedástico (primera vuelta + carrera): |resid| ~ salida, circuito
        self.rs = Ridge(alpha=1.0).fit(X_sigma(df_), np.abs(res), sample_weight=w[fin])
        self.sig_floor = 0.5
        # 3) abandono
        self.rd = LogisticRegression(C=1.0, max_iter=500).fit(X_dnf(d), dnf, sample_weight=w)
        return self

    def simular(self, test, n_sims=20000, seed=0):
        v = self.var
        d = prep(test)
        mu = d.g.values + self.rm.predict(X_media(d, v))
        sig = np.maximum(self.rs.predict(X_sigma(d)) * np.sqrt(np.pi / 2), self.sig_floor) * v.get("sig_k", 1.0)
        p_dnf = self.rd.predict_proba(X_dnf(d))[:, 1] * v.get("dnf_k", 1.0)
        rng = np.random.default_rng(seed)
        n = len(d)
        nu = v.get("df", 0)
        eps = rng.standard_t(nu, size=(n_sims, n)) if nu else rng.standard_normal((n_sims, n))
        lat = mu[None, :] + sig[None, :] * eps
        out = rng.random((n_sims, n)) < p_dnf[None, :]
        lat = lat + out * 1000.0           # los abandonos van detrás de todos los que terminan
        pos = lat.argsort(axis=1).argsort(axis=1) + 1
        return pos.mean(axis=0), mu, sig, p_dnf, pos

    def predict(self, test):
        m, mu, sig, pd_, pos = self.simular(test)
        r = self.var.get("resumen", "mean")
        if r == "gain":
            return -np.clip(11 - pos, 0, None).mean(axis=0)
        if r == "median":
            return np.median(pos, axis=0) + 1e-3 * m
        return m

