# -*- coding: utf-8 -*-
"""
Utilidades comunes de la medicion de mercados con el modelo de produccion (ensamble).
Solo DESARROLLO (modelo/pred/<modelo>.parquet, por bloque). No lee PRUEBA. No toca produccion.

rho: modelo/pred/ensamble.parquet NO guarda la columna x_rho, asi que los comandos existentes
(`python3 -m produccion.mercados validar ensamble`) caen en rho = 0. Aqui el rho de cada partido se
recupera de la matriz guardada por el arnes (modelo/cache/M_<modelo>.npz):
    M[1,1] / Pois(1,1) = (1 - rho) / Z   y   M[2,2] / Pois(2,2) = 1 / Z   =>   rho = 1 - cociente
y se verifica reconstruyendo la matriz con arnes.matrices_marcadores (diferencia < 1e-7).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy.stats import poisson

sys.path.insert(0, "/home/user/SA/ligamx")
from modelo import arnes, datos, metricas          # noqa: E402
from produccion import mercados as mk              # noqa: E402

SAL = "/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/mercados"


def rho_guardado(nombre: str, pred: pd.DataFrame) -> np.ndarray:
    ids, M = arnes.leer_matrices(nombre)
    M = pd.Series(list(M), index=ids).reindex(pred["id"].to_numpy())
    M = np.stack(M.to_numpy())
    ll, lv = pred["lam_l"].to_numpy(float), pred["lam_v"].to_numpy(float)
    p11 = poisson.pmf(1, ll) * poisson.pmf(1, lv)
    p22 = poisson.pmf(2, ll) * poisson.pmf(2, lv)
    rho = 1.0 - (M[:, 1, 1] / p11) / (M[:, 2, 2] / p22)
    M2 = arnes.matrices_marcadores(ll, lv, rho)
    err = float(np.abs(M - M2).max())
    if err > 1e-6:
        raise AssertionError(f"no se pudo recuperar rho de {nombre}: {err}")
    return rho


def preparar(nombre: str, rho: str = "modelo", lam=None) -> dict:
    """
    pred de DESARROLLO + medio tiempo, proporcion del 1T solo con el pasado de cada corte (igual que
    produccion.mercados.validar_desarrollo), celdas Q, probabilidades P (n, 56) y celda observada.
    rho = "modelo" (el de la matriz guardada) o "cero". lam = (lam_l, lam_v) alternativos (diagnostico).
    """
    pred = arnes.leer_pred(nombre)                       # desarrollo, por bloque
    df = datos.cargar()
    pred = pred.merge(df[["id", "gl_ht", "gv_ht"]], on="id", how="left")
    r = rho_guardado(nombre, pred) if rho == "modelo" else np.zeros(len(pred))
    pred["rho"] = r
    pred = pred[pred["lam_l"].notna() & pred["gl_ht"].notna()].reset_index(drop=True)
    p1 = mk.proporciones_1t_cortes(pred["corte"], mk.ANIOS_P1, df)
    ll = pred["lam_l"].to_numpy(float) if lam is None else np.asarray(lam[0], float)
    lv = pred["lam_v"].to_numpy(float) if lam is None else np.asarray(lam[1], float)
    M = arnes.matrices_marcadores(ll, lv, pred["rho"].to_numpy(float))
    Q = mk.celdas(M, p1["p1_l"].to_numpy(), p1["p1_v"].to_numpy())
    P = mk.probabilidades(Q)
    obs = mk.resultado_en_celdas(pred["gl"], pred["gv"], pred["gl_ht"], pred["gv_ht"])
    ok = obs >= 0
    return {"pred": pred, "p1": p1, "M": M, "Q": Q, "P": P, "obs": obs, "ok": ok,
            "bloques": pred["bloque"].to_numpy(), "lam_l": ll, "lam_v": lv}


def tabla_mercados(d: dict, con_ee_pendiente: bool = True, B: int = 300) -> pd.DataFrame:
    """Una fila por mercado del catalogo (56). En los 4 con devolucion: solo partidos sin devolucion."""
    G, Z = mk._matrices()
    cat = mk.catalogo()
    ok, obs, P, bl = d["ok"], d["obs"], d["P"], d["bloques"]
    filas = []
    for k, m in enumerate(cat):
        sel = ok.copy()
        if not m.combinable:
            sel &= np.where(ok, Z[k, np.where(ok, obs, 0)] == 0, False)
        y = G[k, obs[sel]]
        p = P[sel, k]
        r = mk.resumen_binario(p, y, bl[sel])
        fila = {"clave": m.clave, "mercado": mk.etiqueta(m), "familia": m.familia, "combinable": m.combinable, **r}
        if con_ee_pendiente:
            fila["ee_pendiente"] = ee_pendiente(p, y, bl[sel], B)
        filas.append(fila)
    return pd.DataFrame(filas).set_index("clave")


def ee_pendiente(p, y, bloques, B: int = 300, semilla: int = 20261115) -> float:
    """Error estandar de la pendiente de recalibracion por bootstrap de bloques."""
    cod, _ = pd.factorize(np.asarray(bloques), sort=True)
    nb = cod.max() + 1
    grupos = [np.flatnonzero(cod == b) for b in range(nb)]
    rng = np.random.default_rng(semilla)
    out = []
    for _ in range(B):
        ix = np.concatenate([grupos[b] for b in rng.integers(0, nb, nb)])
        try:
            out.append(mk._pendiente_logit(p[ix], y[ix]))
        except Exception:
            pass
    return float(np.std(out, ddof=1))


def logloss_vec(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def pareada_mercados(da: dict, db: dict) -> pd.DataFrame:
    """Log-loss de a menos log-loss de b por mercado combinable (mismos partidos), ee por bloques."""
    G, _ = mk._matrices()
    cat = mk.catalogo()
    assert (da["pred"]["id"].to_numpy() == db["pred"]["id"].to_numpy()).all()
    ok, obs, bl = da["ok"], da["obs"], da["bloques"]
    filas = []
    for k, m in enumerate(cat):
        if not m.combinable:
            continue
        y = G[k, obs[ok]]
        r = metricas.diferencia_pareada(logloss_vec(da["P"][ok, k], y), logloss_vec(db["P"][ok, k], y), bl[ok])
        filas.append({"clave": m.clave, "d_ll": r["dif"], "ee": r["ee"], "z": r["z"]})
    return pd.DataFrame(filas).set_index("clave")
