# -*- coding: utf-8 -*-
"""
Auditoria independiente de las correcciones de mercados (MERCADOS_ENSAMBLE.md secciones 8 y 9).
Implementacion PROPIA: no importa nada de produccion/ ni de modelo/ ni de los guiones de quien corrigio.
Lee solo archivos (parquet de predicciones, npz de matrices, CSV de datos).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln
from scipy.stats import binom, poisson

RAIZ = "/home/user/SA/ligamx"
AUD = "/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/mercados/auditoria"
NG = 11
KK = np.arange(NG)
LOGF = gammaln(KK + 1.0)
N0 = 300.0
SEIS = int(6.0 * 365.25 * 86400 * 1e9)

# ---------------------------------------------------------------- celdas (x, y, h1, a1) y predicados propios
CEL = np.array([(x, y, h, a) for x in range(NG) for y in range(NG) for h in range(x + 1) for a in range(y + 1)])
CX, CY, CH1, CA1 = CEL.T


def predicados(x, y, h1, a1) -> dict:
    """52 mercados binarios, escritos desde la etiqueta en lenguaje llano (no desde las mascaras del catalogo)."""
    x, y, h1, a1 = (np.asarray(v) for v in (x, y, h1, a1))
    h2, a2 = x - h1, y - a1
    d, t, d1, t1, d2, t2 = x - y, x + y, h1 - a1, h1 + a1, h2 - a2, h2 + a2
    ambos = (x >= 1) & (y >= 1)
    P = {"1": d > 0, "X": d == 0, "2": d < 0, "1X": d >= 0, "X2": d <= 0, "12": d != 0,
         "H_L-1.5": d >= 2, "H_V+1.5": d < 2, "H_V-1.5": d <= -2, "H_L+1.5": d > -2,
         "O15": t >= 2, "U15": t <= 1, "O25": t >= 3, "U25": t <= 2, "O35": t >= 4, "U35": t <= 3,
         "AA_SI": ambos, "AA_NO": ~ambos,
         "L_ANOTA": x >= 1, "L_2MAS": x >= 2, "L_U15": x <= 1, "PC_V": x == 0,
         "V_ANOTA": y >= 1, "V_2MAS": y >= 2, "V_U15": y <= 1, "PC_L": y == 0,
         "D_1": d1 > 0, "D_X": d1 == 0, "D_2": d1 < 0, "D_1X": d1 >= 0, "D_X2": d1 <= 0, "D_12": d1 != 0,
         "G1T_SI": t1 >= 1, "G1T_NO": t1 == 0, "O15_1T": t1 >= 2, "U15_1T": t1 <= 1,
         "G2T_SI": t2 >= 1, "G2T_NO": t2 == 0,
         "MAS_1T": t1 > t2, "MAS_2T": t2 > t1, "MIT_IGUAL": t1 == t2,
         "GM_L": (d1 > 0) | (d2 > 0), "GM_V": (d1 < 0) | (d2 < 0)}
    nom = {1: "1", 0: "X", -1: "2"}
    for a in (1, 0, -1):
        for b in (1, 0, -1):
            P[f"DF_{nom[a]}/{nom[b]}"] = (np.sign(d1) == a) & (np.sign(d) == b)
    return P


MASC = predicados(CX, CY, CH1, CA1)
CLAVES = list(MASC)
GM = np.stack([MASC[c] for c in CLAVES]).astype(float)          # (52, 4356)
IDX = {c: i for i, c in enumerate(CLAVES)}
FAMILIA = {}
for c in CLAVES:
    FAMILIA[c] = ("resultado" if c in ("1", "X", "2", "1X", "X2", "12") or c.startswith("H_") else
                  "total" if c[0] in "OU" and not c.endswith("1T") else "ambos" if c.startswith("AA") else
                  "goles_local" if c in ("L_ANOTA", "L_2MAS", "L_U15", "PC_V") else
                  "goles_visita" if c in ("V_ANOTA", "V_2MAS", "V_U15", "PC_L") else
                  "descanso_final" if c.startswith("DF_") else "descanso" if c.startswith("D_") else
                  "mitades" if c.startswith("MAS") or c == "MIT_IGUAL" else
                  "goles_1t" if c.endswith("1T") or c.startswith("G1T") else "goles_2t" if c.startswith("G2T") else "gana_mitad")
COMPL = {}
for c in CLAVES:
    for e in CLAVES:
        if np.array_equal(MASC[c], ~MASC[e]):
            COMPL[c] = e


# ---------------------------------------------------------------- matrices
def mat_dc(ll, lv, rho) -> np.ndarray:
    """Poisson x Poisson con tau de Dixon-Coles, truncada en 10 y renormalizada (formula escrita aparte)."""
    ll, lv, rho = (np.atleast_1d(np.asarray(v, float)) for v in (ll, lv, rho))
    M = poisson.pmf(KK[None, :], ll[:, None])[:, :, None] * poisson.pmf(KK[None, :], lv[:, None])[:, None, :]
    M[:, 0, 0] *= 1.0 - ll * lv * rho
    M[:, 0, 1] *= 1.0 + ll * rho
    M[:, 1, 0] *= 1.0 + lv * rho
    M[:, 1, 1] *= 1.0 - rho
    return M / M.sum(axis=(1, 2), keepdims=True)


def cmp_media(lam, nu) -> np.ndarray:
    """Conway-Maxwell-Poisson en 0..10 con la media de la Poisson truncada: P(k) ~ exp(k t - nu ln k!). Biseccion en t."""
    lam = np.atleast_1d(np.asarray(lam, float))
    nu = np.broadcast_to(np.asarray(nu, float), lam.shape)
    pt = poisson.pmf(KK[None, :], lam[:, None])
    m = (pt * KK).sum(axis=1) / pt.sum(axis=1)

    def dist(t):
        a = KK[None, :] * t[:, None] - nu[:, None] * LOGF[None, :]
        a = np.exp(a - a.max(axis=1, keepdims=True))
        return a / a.sum(axis=1, keepdims=True)

    t = nu * np.log(lam)                                     # Newton (rapido); si no converge, biseccion
    for _ in range(12):
        f = dist(t)
        mu = (f * KK).sum(axis=1)
        var = (f * KK * KK).sum(axis=1) - mu * mu
        t = t + np.clip((m - mu) / np.maximum(var, 1e-10), -2.0, 2.0)
    f = dist(t)
    if np.abs((f * KK).sum(axis=1) - m).max() > 1e-9:
        lo, hi = np.full(lam.shape, -30.0), np.full(lam.shape, 30.0)
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            mu = (dist(mid) * KK).sum(axis=1)
            lo = np.where(mu < m, mid, lo)
            hi = np.where(mu < m, hi, mid)
        f = dist(0.5 * (lo + hi))
    assert np.abs((f * KK).sum(axis=1) - m).max() < 1e-8
    return f


_XX, _YY = np.meshgrid(KK, KK, indexing="ij")
REG = np.stack([_XX > _YY, _XX == _YY, _XX < _YY]).astype(float)        # (3, 11, 11)


def p1x2(M) -> np.ndarray:
    return np.einsum("nxy,rxy->nr", M, REG)


def mat_forma(ll, lv, rho, nu=1.0, kappa=0.0) -> np.ndarray:
    """Marginales CMP (misma media), tau de Dixon-Coles, factor de dependencia y 1X2 fijado al de mat_dc."""
    ll, lv, rho = (np.atleast_1d(np.asarray(v, float)) for v in (ll, lv, rho))
    nu = np.broadcast_to(np.asarray(nu, float), ll.shape)
    kappa = np.broadcast_to(np.asarray(kappa, float), ll.shape)
    M = cmp_media(ll, nu)[:, :, None] * cmp_media(lv, nu)[:, None, :]
    M[:, 0, 0] *= 1.0 - ll * lv * rho
    M[:, 0, 1] *= 1.0 + ll * rho
    M[:, 1, 0] *= 1.0 + lv * rho
    M[:, 1, 1] *= 1.0 - rho
    dep = (KK[None, :, None] - ll[:, None, None]) * (KK[None, None, :] - lv[:, None, None]) / np.sqrt(ll * lv)[:, None, None]
    M = M * np.exp(kappa[:, None, None] * dep)
    M /= M.sum(axis=(1, 2), keepdims=True)
    objetivo = p1x2(mat_dc(ll, lv, rho))
    fac = objetivo / p1x2(M)
    M = M * np.einsum("nr,rxy->nxy", fac, REG)
    return M / M.sum(axis=(1, 2), keepdims=True)


# ---------------------------------------------------------------- celdas y mercados
def celdas(M, pl, pv) -> np.ndarray:
    """q (n, 4356). pl, pv: (n,) o (n, 4356) (proporcion del 1T por celda, para mitades_total)."""
    pl, pv = np.asarray(pl, float), np.asarray(pv, float)
    pl = pl[:, None] if pl.ndim == 1 else pl
    pv = pv[:, None] if pv.ndim == 1 else pv
    return M[:, CX, CY] * binom.pmf(CH1[None, :], CX[None, :], pl) * binom.pmf(CA1[None, :], CY[None, :], pv)


def prob_mercados(q) -> np.ndarray:
    return q @ GM.T                                             # (n, 52)


def observado(gl, gv, hl, hv) -> np.ndarray:
    """(n, 52) con lo que ocurrio, evaluando los predicados en el marcador real (sin pasar por celdas)."""
    P = predicados(np.minimum(gl, 10), np.minimum(gv, 10), hl, hv)
    return np.stack([P[c] for c in CLAVES], axis=1).astype(float)


def ll_bin(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


# ---------------------------------------------------------------- errores estandar por bloques (propios)
def ee_bloques(v, bloques, B=2000, semilla=4242) -> tuple[float, float, float]:
    """(media, ee bootstrap de bloques, ee analitico de conglomerados)."""
    v = np.asarray(v, float)
    cod, _ = pd.factorize(np.asarray(bloques))
    nb = cod.max() + 1
    S = np.bincount(cod, weights=v, minlength=nb)
    C = np.bincount(cod, minlength=nb).astype(float)
    rng = np.random.default_rng(semilla)
    ix = rng.integers(0, nb, size=(B, nb))
    medias = S[ix].sum(axis=1) / C[ix].sum(axis=1)
    m = v.mean()
    ana = np.sqrt(nb / (nb - 1.0) * ((S - m * C) ** 2).sum()) / len(v)
    return float(m), float(medias.std(ddof=1)), float(ana)


# ---------------------------------------------------------------- datos
def leer_partidos() -> pd.DataFrame:
    p = pd.read_csv(f"{RAIZ}/datos/partidos.csv", low_memory=False)
    p["f_ns"] = pd.to_datetime(p["fecha_utc"], utc=True, format="%Y-%m-%dT%H:%MZ").astype("datetime64[ns, UTC]").astype("int64")
    return p


def rho_de_matriz(M, ll, lv) -> np.ndarray:
    """rho de la matriz guardada, por dos caminos (celdas 1-1 y 0-1 contra 2-2); se exige que coincidan."""
    P = poisson.pmf(KK[None, :], ll[:, None])[:, :, None] * poisson.pmf(KK[None, :], lv[:, None])[:, None, :]
    base = M[:, 2, 2] / P[:, 2, 2]
    r11 = 1.0 - (M[:, 1, 1] / P[:, 1, 1]) / base
    r01 = ((M[:, 0, 1] / P[:, 0, 1]) / base - 1.0) / ll
    r10 = ((M[:, 1, 0] / P[:, 1, 0]) / base - 1.0) / lv
    assert np.abs(r11 - r01).max() < 2e-4 and np.abs(r11 - r10).max() < 2e-4, (np.abs(r11 - r01).max(), np.abs(r11 - r10).max())
    return (r11 + r01 + r10) / 3.0


def preparar(pred: pd.DataFrame, ruta_npz: str, partidos: pd.DataFrame) -> dict:
    z = np.load(ruta_npz)
    Mg = pd.Series(list(z["M"].astype(float)), index=z["id"]).reindex(pred["id"].to_numpy())
    Mg = np.stack(Mg.to_numpy())
    Mg /= Mg.sum(axis=(1, 2), keepdims=True)
    ll, lv = pred["lam_l"].to_numpy(float), pred["lam_v"].to_numpy(float)
    rho = rho_de_matriz(Mg, ll, lv)
    err = float(np.abs(mat_dc(ll, lv, rho) - Mg).max())
    ht = partidos.set_index("id").reindex(pred["id"].to_numpy())
    d = {"id": pred["id"].to_numpy(), "f": pred["fecha_utc"].astype("datetime64[ns, UTC]").astype("int64").to_numpy(),
         "c": pd.to_datetime(pred["corte"], utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy(),
         "bloque": pred["bloque"].to_numpy(), "ll": ll, "lv": lv, "rho": rho,
         "gl": pred["gl"].to_numpy(int), "gv": pred["gv"].to_numpy(int),
         "hl": ht["gl_ht"].to_numpy(float), "hv": ht["gv_ht"].to_numpy(float),
         "p3": pred[["p_l", "p_e", "p_v"]].to_numpy(float), "err_matriz": err,
         "torneo": pred["torneo"].to_numpy()}
    assert (ht["gl"].to_numpy() == d["gl"]).all() and (ht["gv"].to_numpy() == d["gv"]).all()
    return d


def subconjunto(d: dict, sel) -> dict:
    return {k: (v[sel] if isinstance(v, np.ndarray) else v) for k, v in d.items()}


def unir(a: dict, b: dict) -> dict:
    return {k: (np.concatenate([a[k], b[k]]) if isinstance(a[k], np.ndarray) else a[k]) for k in a}


# ---------------------------------------------------------------- proporcion del 1T (de goles.csv, solo pasado)
def conteos_mitades(partidos: pd.DataFrame) -> pd.DataFrame:
    j = partidos[(partidos["estado"] == "jugado") & (partidos["tiene_eventos"] == 1)
                 & ~partidos["nota"].fillna("").str.contains("escritorio|abandonado", case=False)]
    g = pd.read_csv(f"{RAIZ}/datos/goles.csv", low_memory=False)
    g = g[g["periodo"].isin([1, 2])].merge(j[["id", "local", "visitante"]], left_on="partido_id", right_on="id")
    g["l"] = (g["equipo"] == g["local"]).astype(float)
    g["v"] = (g["equipo"] == g["visitante"]).astype(float)
    g["l1"] = g["l"] * (g["periodo"] == 1)
    g["v1"] = g["v"] * (g["periodo"] == 1)
    s = g.groupby("id")[["l1", "l", "v1", "v"]].sum()
    t = j[["id", "f_ns"]].set_index("id").join(s).fillna(0.0).sort_values("f_ns", kind="mergesort")
    return t


def p1_cortes(t: pd.DataFrame, cortes: np.ndarray, por_total: bool = False) -> dict:
    """Para cada corte, con los partidos de [corte - 6 anios, corte). Recorre corte por corte (sin sumas acumuladas)."""
    f = t["f_ns"].to_numpy()
    A = t[["l1", "l", "v1", "v"]].to_numpy(float)
    tot = A[:, 1] + A[:, 3]
    out = {}
    for c in np.unique(cortes):
        w = (f < c) & (f >= c - SEIS)
        if por_total:
            lo, hi = A[w & (tot <= 2)].sum(axis=0), A[w & (tot >= 3)].sum(axis=0)
            out[c] = (lo[0] / lo[1], lo[2] / lo[3], hi[0] / hi[1], hi[2] / hi[3])
        else:
            s = A[w].sum(axis=0)
            out[c] = (s[0] / s[1], s[2] / s[3])
    return out


# ---------------------------------------------------------------- estimacion de parametros SOLO con el pasado
def logv_forma(nu, kappa, P) -> float:
    M = mat_forma(P["ll"], P["lv"], P["rho"], nu, kappa)
    return float(np.log(M[np.arange(len(P["ll"])), np.minimum(P["gl"], 10), np.minimum(P["gv"], 10)]).sum())


def estimar_nu(P) -> float:
    r = minimize_scalar(lambda nu: -logv_forma(nu, 0.0, P), bounds=(0.5, 2.0), method="bounded", options={"xatol": 1e-5})
    return float(r.x)


def estimar_nu_kappa(P, x0=(1.0, 0.0)) -> tuple[float, float]:
    r = minimize(lambda th: -logv_forma(th[0], th[1], P), x0=np.array(x0), method="L-BFGS-B",
                 bounds=[(0.5, 2.0), (-0.1, 0.2)], options={"ftol": 1e-12, "gtol": 1e-7})
    return float(r.x[0]), float(r.x[1])


def estimar_intercepto(p, y) -> float:
    lg = np.log(p / (1 - p))
    r = minimize_scalar(lambda a: ll_bin(1.0 / (1.0 + np.exp(-(lg + a))), y).sum(), bounds=(-0.8, 0.8), method="bounded",
                        options={"xatol": 1e-6})
    return float(r.x)
