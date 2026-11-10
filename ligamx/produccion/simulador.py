# -*- coding: utf-8 -*-
"""
Simulador de la tabla, la liguilla y el campeón de la Liga MX (Monte Carlo vectorizado con numpy).

Consume sólo el contrato del `Pronosticador` (`equipos`, `partidos(df)`, `malla(n, fase, semilla)`):
  * fase regular: tabla real hasta el corte + partidos pendientes simulados; orden con los criterios
    oficiales de config/torneo.json (puntos, diferencia, goles a favor, goles de visitante, Fair Play,
    cociente, sorteo);
  * liguilla: cuartos 1-8, 2-7, 3-6, 4-5 a ida y vuelta, resiembra en semifinales, final con tiempos
    extra y penales; se respeta lo ya jugado de las series reales;
  * la incertidumbre de los parámetros se propaga repartiendo las simulaciones entre las muestras
    k >= 1 de `malla(n)`; el error de Monte Carlo se calcula entre muestras (conglomerados);
  * `prob_serie` da la probabilidad EXACTA de una serie (sin simular) y `calibrar_series` la contrasta
    con las liguillas de DESARROLLO.

Uso:  python3 -m produccion.simulador [--corte AAAA-MM-DDTHH:MM] [--n-sim 20000] [--calibrar]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import convolve2d

from modelo import arnes, datos, metricas

RAIZ = datos.RAIZ
RUTA_REGLAS = RAIZ / "config" / "torneo.json"
DIR_SALIDAS = RAIZ / "salidas"
MAXG = arnes.MAX_GOLES                       # 10: tope de goles por equipo y partido
N_SIM = 20000
N_MUESTRAS = 2000                            # muestras de parámetros entre las que se reparten las simulaciones
SEMILLA = 20261110
FASES_LIGUILLA = ("cuartos", "semifinal", "final")
TORNEO_COCIENTE = "Apertura 2024"            # art. 34: puntos entre partidos desde este torneo
VISITAS_CUENTAN = 8                          # goles de visitante: sólo las primeras 8 visitas de cada equipo
FRACCION_EXTRA = 1.0 / 3.0                   # tiempos extra: 30 de 90 minutos
P_PENALES = 0.5                              # tanda de penales: moneda al aire
ESTADOS_PENDIENTES = ("programado", "en_juego", "pospuesto")


# ==================================================================================================
# Utilidades
# ==================================================================================================
def cargar_reglas(ruta: str | Path | None = None) -> dict:
    """Reglas del torneo (config/torneo.json)."""
    with open(ruta or RUTA_REGLAS, encoding="utf-8") as f:
        return json.load(f)


def a_utc(corte) -> pd.Timestamp:
    """Corte como Timestamp en UTC (None = ahora; sin zona se interpreta como hora de CDMX)."""
    if corte is None:
        return pd.Timestamp.now(tz="UTC")
    t = pd.Timestamp(corte)
    return t.tz_localize(datos.ZONA).tz_convert("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def orden_torneo(torneo: str) -> int:
    """Ordinal cronológico del torneo: año * 2 + (1 si es Apertura)."""
    tipo, anio = torneo.rsplit(" ", 1)
    return int(anio) * 2 + (1 if tipo.startswith("Apertura") else 0)


def marcadores(rng: np.random.Generator, lam_l, lam_v, rho: float = 0.0):
    """
    Marcadores simulados (enteros de 0 a 10) para arreglos de lambdas de cualquier forma.
    Con rho = 0 son dos Poisson independientes recortadas en 10 (la masa por encima es < 1e-5); con
    rho != 0 se sortea de la matriz de Dixon-Coles de `arnes.matrices_marcadores`.
    """
    lam_l, lam_v = np.asarray(lam_l, float), np.asarray(lam_v, float)
    if rho == 0.0:
        return np.minimum(rng.poisson(lam_l), MAXG), np.minimum(rng.poisson(lam_v), MAXG)
    forma = lam_l.shape
    a, b = lam_l.ravel(), lam_v.ravel()
    u = rng.random(len(a))
    j = np.empty(len(a), dtype=np.int64)
    for i in range(0, len(a), 40000):
        s = slice(i, i + 40000)
        c = np.cumsum(arnes.matrices_marcadores(a[s], b[s], rho).reshape(-1, (MAXG + 1) ** 2), axis=1)
        j[s] = np.minimum((c < u[s, None]).sum(axis=1), (MAXG + 1) ** 2 - 1)
    return (j // (MAXG + 1)).reshape(forma), (j % (MAXG + 1)).reshape(forma)


def ordenar(pts, dg, gf, gvis, fair, coc, azar) -> np.ndarray:
    """
    Orden de la tabla con los criterios oficiales, de más a menos importante: puntos, diferencia de
    goles, goles a favor, goles de visitante (más es mejor), puntos de Fair Play (MENOS es mejor),
    cociente (más es mejor) y sorteo (`azar`, menor primero). Acepta vectores (18,) o matrices
    (n_sim, 18); devuelve los índices de los equipos del primer al último lugar (misma forma).
    """
    llaves = [np.asarray(x, float) for x in (azar, -np.asarray(coc, float), fair, -np.asarray(gvis, float),
                                             -np.asarray(gf, float), -np.asarray(dg, float),
                                             -np.asarray(pts, float))]
    return np.lexsort(np.stack(llaves), axis=-1)


# ==================================================================================================
# Estado real del torneo a un corte
# ==================================================================================================
def puntos_fair_play(jugados: pd.DataFrame, equipos: list[str]) -> np.ndarray:
    """
    Puntos de Fair Play por equipo en los partidos de `jugados` (tarjetas.csv), por jugador y partido:
    sólo amarilla 1; segunda amarilla (expulsado por doble amarilla) 3; roja directa 3; amarilla más
    roja directa 4. Menos es mejor. tarjetas.csv no distingue al cuerpo técnico ni trae las sanciones
    de la Comisión Disciplinaria, que el reglamento también cuenta: es una aproximación.
    """
    out = np.zeros(len(equipos))
    if jugados.empty:
        return out
    t = datos.tabla("tarjetas", jugados)
    if t.empty:
        return out
    t = t.assign(a=(t["tipo"] == "amarilla").astype(int), s=(t["tipo"] == "segunda_amarilla").astype(int),
                 r=(t["tipo"] == "roja").astype(int))
    g = t.groupby(["partido_id", "equipo", "jugador_id"], dropna=False)[["a", "s", "r"]].sum()
    p = np.where(g["s"] > 0, 3, np.where(g["r"] > 0, np.where(g["a"] > 0, 4, 3), np.minimum(g["a"], 1)))
    por_eq = pd.Series(p, index=g.index).groupby(level="equipo").sum()
    ix = {e: i for i, e in enumerate(equipos)}
    for e, v in por_eq.items():
        if e in ix:
            out[ix[e]] = float(v)
    return out


def estado_torneo(df: pd.DataFrame, torneo: str, corte, equipos: list[str] | None = None) -> dict:
    """
    Lo que se sabe de la fase regular de `torneo` antes de `corte`: tabla (pj, g, e, p, gf, gc, pts,
    desglose de local y visita), goles de visitante en las primeras 8 visitas, puntos de Fair Play,
    base del cociente (puntos y partidos de fase regular desde el Apertura 2024, torneo en curso
    incluido) y los partidos pendientes con el número de visita que le toca al visitante.
    """
    corte = a_utc(corte)
    reg = df[(df["torneo"] == torneo) & (df["fase"] == "regular") & (df["estado"] != "cancelado")]
    reg = reg.sort_values(["fecha_utc", "id"])
    if equipos is None:
        equipos = sorted(set(reg["local"]) | set(reg["visitante"]))
    ix = {e: i for i, e in enumerate(equipos)}
    n = len(equipos)
    hecho = (reg["estado"] == "jugado") & (reg["fecha_utc"] < corte) & reg["gl"].notna()
    jug = reg[hecho]
    pend = reg[~hecho & (reg["estado"].isin(ESTADOS_PENDIENTES) | (reg["estado"] == "jugado"))]
    # un 'pospuesto' con su reposición ya en el calendario no se cuenta dos veces
    llave = pend["local"] + "|" + pend["visitante"]
    ya = set(jug["local"] + "|" + jug["visitante"]) | set(llave[pend["estado"] != "pospuesto"])
    pend = pend[~((pend["estado"] == "pospuesto") & llave.isin(ya))]

    c = {k: np.zeros(n) for k in ("pj", "g", "e", "p", "gf", "gc", "pts", "pj_l", "pts_l", "gf_l", "gc_l",
                                  "pj_v", "pts_v", "gf_v", "gc_v", "gvis", "n_vis")}
    il = jug["local"].map(ix).to_numpy()
    iv = jug["visitante"].map(ix).to_numpy()
    gl, gv = jug["gl"].to_numpy(float), jug["gv"].to_numpy(float)
    for a, b, x, y in zip(il, iv, gl, gv):
        pl, pv = (3, 0) if x > y else ((1, 1) if x == y else (0, 3))
        for i, gf, gc, pt, lado in ((a, x, y, pl, "l"), (b, y, x, pv, "v")):
            c["pj"][i] += 1; c["gf"][i] += gf; c["gc"][i] += gc; c["pts"][i] += pt
            c["g"][i] += pt == 3; c["e"][i] += pt == 1; c["p"][i] += pt == 0
            c["pj_" + lado][i] += 1; c["pts_" + lado][i] += pt
            c["gf_" + lado][i] += gf; c["gc_" + lado][i] += gc
    # número de visita de cada partido (jugados y pendientes, en orden cronológico)
    visitas = reg[reg["id"].isin(jug["id"]) | reg["id"].isin(pend["id"])]
    ordinal = visitas.groupby("visitante").cumcount() + 1
    ord_de = dict(zip(visitas["id"], ordinal))
    for pid, b, y in zip(jug["id"], iv, gv):
        c["n_vis"][b] += 1
        if ord_de[pid] <= VISITAS_CUENTAN:
            c["gvis"][b] += y
    # cociente: fase regular desde el Apertura 2024, antes del corte (incluye el torneo en curso)
    o0 = orden_torneo(TORNEO_COCIENTE)
    hist = df[(df["fase"] == "regular") & (df["estado"] == "jugado") & (df["fecha_utc"] < corte)
              & df["gl"].notna() & (df["torneo"].map(orden_torneo) >= o0)
              & (df["torneo"].map(orden_torneo) <= orden_torneo(torneo))]
    coc_pts, coc_pj = np.zeros(n), np.zeros(n)
    for loc, vis, x, y in zip(hist["local"], hist["visitante"], hist["gl"], hist["gv"]):
        pl, pv = (3, 0) if x > y else ((1, 1) if x == y else (0, 3))
        if loc in ix:
            coc_pts[ix[loc]] += pl; coc_pj[ix[loc]] += 1
        if vis in ix:
            coc_pts[ix[vis]] += pv; coc_pj[ix[vis]] += 1
    est = {"torneo": torneo, "corte": corte, "equipos": list(equipos), **c,
           "fair": puntos_fair_play(jug, list(equipos)), "coc_pts": coc_pts, "coc_pj": coc_pj,
           "jugados": jug, "pendientes": pend.reset_index(drop=True),
           "pend_il": pend["local"].map(ix).to_numpy(dtype=int), "pend_iv": pend["visitante"].map(ix).to_numpy(dtype=int),
           "pend_cuenta_vis": np.array([ord_de[i] <= VISITAS_CUENTAN for i in pend["id"]], dtype=bool)}
    est["dg"] = est["gf"] - est["gc"]
    est["cociente"] = np.divide(coc_pts, coc_pj, out=np.zeros(n), where=coc_pj > 0)
    return est


def tabla_actual(est: dict) -> pd.DataFrame:
    """Tabla general real (una fila por equipo, ordenada con los criterios oficiales; sorteo = alfabético)."""
    eq = est["equipos"]
    orden = ordenar(est["pts"], est["dg"], est["gf"], est["gvis"], est["fair"], est["cociente"],
                    np.arange(len(eq)))
    t = pd.DataFrame({"equipo": eq, "PJ": est["pj"], "G": est["g"], "E": est["e"], "P": est["p"],
                      "GF": est["gf"], "GC": est["gc"], "DG": est["dg"], "PTS": est["pts"],
                      "PJ_L": est["pj_l"], "PTS_L": est["pts_l"], "GF_L": est["gf_l"], "GC_L": est["gc_l"],
                      "PJ_V": est["pj_v"], "PTS_V": est["pts_v"], "GF_V": est["gf_v"], "GC_V": est["gc_v"],
                      "goles_visita_8": est["gvis"], "fair_play": est["fair"]}).astype(
        {k: int for k in ("PJ", "G", "E", "P", "GF", "GC", "DG", "PTS", "PJ_L", "PTS_L", "GF_L", "GC_L", "PJ_V",
                          "PTS_V", "GF_V", "GC_V", "goles_visita_8", "fair_play")})
    t["cociente"] = np.round(est["cociente"], 4)
    t = t.iloc[orden].reset_index(drop=True)
    t.insert(0, "pos", np.arange(1, len(t) + 1))
    return t


# ==================================================================================================
# Probabilidad exacta de una serie a ida y vuelta
# ==================================================================================================
def prob_serie(M1, M2, mejor_local_1: bool = False, mejor_local_2: bool = True, regla: str = "posicion",
               lam_extra: tuple[float, float] | None = None) -> dict:
    """
    Probabilidad exacta de que avance el MEJOR sembrado en una serie a dos partidos.

    M1, M2: matrices [goles del local, goles del visitante] de la ida y la vuelta (una pierna ya jugada
    se pasa como matriz con toda la masa en su marcador: `matriz_fija`). `mejor_local_k` dice si el
    mejor sembrado es local en la pierna k. Reglas con el global empatado:
      "posicion"       avanza el mejor sembrado (cuartos y semifinales desde el Apertura 2021);
      "gol_visitante"  más goles de visitante y, si siguen iguales, el mejor sembrado (Ap. 2012-Cl. 2021);
      "final"          tiempos extra con lambdas `lam_extra` = (local, visitante) de la vuelta ya
                       multiplicadas por 1/3 y, si persiste, penales 50/50.
    Devuelve p_mejor, p_peor, p_global_mejor / p_global_empate / p_global_peor y `G`[goles globales del
    mejor, del peor].
    """
    A1 = np.asarray(M1, float) if mejor_local_1 else np.asarray(M1, float).T      # [goles mejor, goles peor]
    A2 = np.asarray(M2, float) if mejor_local_2 else np.asarray(M2, float).T
    G = convolve2d(A1, A2)
    n = G.shape[0]
    i, j = np.indices((n, n))
    p_gana, p_emp = float(G[i > j].sum()), float(G[i == j].sum())
    if regla == "posicion":
        p = p_gana + p_emp
    elif regla == "final":
        if lam_extra is None:
            raise ValueError("regla 'final' necesita lam_extra")
        E = arnes.matriz_marcadores(max(lam_extra[0], 1e-9), max(lam_extra[1], 1e-9), 0.0)
        x, y = np.indices(E.shape)
        e_loc, e_emp = float(E[x > y].sum()), float(E[x == y].sum())
        e_mejor = e_loc if mejor_local_2 else 1.0 - e_loc - e_emp
        p = p_gana + p_emp * (e_mejor + e_emp * P_PENALES)
    elif regla == "gol_visitante":
        T = A1[:, :, None, None] * A2[None, None, :, :]                            # [m1, p1, m2, p2]
        m1, p1, m2, p2 = np.indices(T.shape)
        emp = (m1 + m2) == (p1 + p2)
        vis_m = np.where(mejor_local_1, 0, m1) + np.where(mejor_local_2, 0, m2)   # goles de visita del mejor
        vis_p = np.where(mejor_local_1, p1, 0) + np.where(mejor_local_2, p2, 0)
        p = p_gana + float(T[emp & (vis_m >= vis_p)].sum())
    else:
        raise ValueError("regla debe ser 'posicion', 'gol_visitante' o 'final'")
    return {"p_mejor": float(p), "p_peor": float(1.0 - p), "p_global_mejor": p_gana, "p_global_empate": p_emp,
            "p_global_peor": float(1.0 - p_gana - p_emp), "G": G}


def matriz_fija(gl, gv) -> np.ndarray:
    """Matriz 11x11 con toda la masa en el marcador ya jugado (recortado en 10)."""
    M = np.zeros((MAXG + 1, MAXG + 1))
    M[int(min(gl, MAXG)), int(min(gv, MAXG))] = 1.0
    return M


# ==================================================================================================
# Series reales de la liguilla en curso
# ==================================================================================================
def series_reales(df: pd.DataFrame, torneo: str, corte, equipos: list[str], pos: dict[str, int]) -> dict:
    """
    Series de liguilla de `torneo` que ya están en partidos.csv, por fase. Cada una: a, b (índices; a es
    el mejor sembrado según `pos`), piernas {1, 2} con local, visitante, si ya se jugó antes del corte
    y su marcador, y `ganador` (índice) si la serie ya está decidida con los datos.
    """
    corte = a_utc(corte)
    ix = {e: i for i, e in enumerate(equipos)}
    lg = df[(df["torneo"] == torneo) & df["fase"].isin(FASES_LIGUILLA) & (df["estado"] != "cancelado")]
    out: dict[str, list] = {f: [] for f in FASES_LIGUILLA}
    if lg.empty:
        return out
    lg = lg.assign(_a=np.minimum(lg["local"], lg["visitante"]), _b=np.maximum(lg["local"], lg["visitante"]))
    for (fase, ea, eb), g in lg.groupby(["fase", "_a", "_b"], sort=False):
        if ea not in ix or eb not in ix:
            continue
        g = g.sort_values("fecha_utc")
        mejor, peor = (ea, eb) if pos.get(ea, 99) < pos.get(eb, 99) else (eb, ea)
        piernas = {}
        for k, r in enumerate(g.itertuples(index=False), start=1):
            num = int(r.pierna) if pd.notna(r.pierna) else k
            jugado = (r.estado == "jugado") and (r.fecha_utc < corte) and pd.notna(r.gl)
            piernas[num] = {"id": int(r.id), "fecha_utc": r.fecha_utc, "local": ix[r.local], "visitante": ix[r.visitante],
                            "jugado": bool(jugado), "gl": int(r.gl) if jugado else None,
                            "gv": int(r.gv) if jugado else None,
                            "gl_et": r.gl_et if jugado else np.nan, "gv_et": r.gv_et if jugado else np.nan,
                            "pen_l": r.pen_l if jugado else np.nan, "pen_v": r.pen_v if jugado else np.nan,
                            "mult_l": 1.0, "mult_v": 1.0}
        s = {"fase": fase, "a": ix[mejor], "b": ix[peor], "piernas": piernas, "ganador": None}
        if len(piernas) >= 2 and all(p["jugado"] for p in piernas.values()):
            ga = sum(p["gl"] if p["local"] == s["a"] else p["gv"] for p in piernas.values())
            gb = sum(p["gl"] if p["local"] == s["b"] else p["gv"] for p in piernas.values())
            ult = piernas[max(piernas)]
            if ga != gb:
                s["ganador"] = s["a"] if ga > gb else s["b"]
            elif fase != "final":
                s["ganador"] = s["a"]                     # global empatado: avanza el mejor sembrado
            elif pd.notna(ult["gl_et"]) and pd.notna(ult["gv_et"]) and ult["gl_et"] != ult["gv_et"]:
                s["ganador"] = ult["local"] if ult["gl_et"] > ult["gv_et"] else ult["visitante"]
            elif pd.notna(ult["pen_l"]) and pd.notna(ult["pen_v"]) and ult["pen_l"] != ult["pen_v"]:
                s["ganador"] = ult["local"] if ult["pen_l"] > ult["pen_v"] else ult["visitante"]
        out[fase].append(s)
    return out


def _jugar_serie(rng, mejor, peor, k, LL, LV, rho, fase: str, reales: dict):
    """
    Simula una serie por simulación (vectores de índices `mejor`, `peor` y de muestra de parámetros
    `k`). Ida en casa del peor sembrado y vuelta en casa del mejor, salvo que una serie real diga otra
    cosa; lo ya jugado se respeta. Devuelve un vector booleano: avanza el mejor sembrado.
    """
    n = len(mejor)
    loc = [peor.copy(), mejor.copy()]
    vis = [mejor.copy(), peor.copy()]
    fijo_l = [np.full(n, -1), np.full(n, -1)]
    fijo_v = [np.full(n, -1), np.full(n, -1)]
    mult_l = [np.ones(n), np.ones(n)]
    mult_v = [np.ones(n), np.ones(n)]
    forzado = np.full(n, -1)
    for s in reales.get(fase, []):
        m = ((mejor == s["a"]) & (peor == s["b"])) | ((mejor == s["b"]) & (peor == s["a"]))
        if not m.any():
            continue
        for num, p in s["piernas"].items():
            if num not in (1, 2):
                continue
            j = num - 1
            loc[j][m], vis[j][m] = p["local"], p["visitante"]
            if p["jugado"]:
                fijo_l[j][m], fijo_v[j][m] = min(p["gl"], MAXG), min(p["gv"], MAXG)
            else:
                mult_l[j][m], mult_v[j][m] = p["mult_l"], p["mult_v"]
        if s["ganador"] is not None:
            forzado[m] = s["ganador"]
    goles_m, goles_p = np.zeros(n, dtype=np.int64), np.zeros(n, dtype=np.int64)
    lam2 = None
    for j in (0, 1):
        ll = LL[k, loc[j], vis[j]] * mult_l[j]
        lv = LV[k, loc[j], vis[j]] * mult_v[j]
        gl, gv = marcadores(rng, ll, lv, rho)
        gl = np.where(fijo_l[j] >= 0, fijo_l[j], gl)
        gv = np.where(fijo_v[j] >= 0, fijo_v[j], gv)
        es_m = loc[j] == mejor
        goles_m += np.where(es_m, gl, gv)
        goles_p += np.where(es_m, gv, gl)
        lam2 = (ll, lv)
    if fase != "final":
        gana = goles_m >= goles_p
    else:
        el, ev = marcadores(rng, lam2[0] * FRACCION_EXTRA, lam2[1] * FRACCION_EXTRA, 0.0)
        es_m = loc[1] == mejor
        em, ep = np.where(es_m, el, ev), np.where(es_m, ev, el)
        moneda = rng.random(n) < P_PENALES
        gana = (goles_m > goles_p) | ((goles_m == goles_p) & ((em > ep) | ((em == ep) & moneda)))
    return np.where(forzado >= 0, forzado == mejor, gana)


# ==================================================================================================
# Simulación completa
# ==================================================================================================
def _ee(x: np.ndarray, n_k: int) -> np.ndarray:
    """Error de Monte Carlo de la media de `x` (n_sim, ...) con las simulaciones agrupadas por muestra."""
    m = x.reshape(n_k, -1, *x.shape[1:]).mean(axis=1)
    return m.std(axis=0, ddof=1) / math.sqrt(n_k) if n_k > 1 else np.zeros(x.shape[1:])


def _pares(mejor, peor, gana, n_eq: int, eq: list[str], n_sim: int, minimo: float, tope: int) -> list[dict]:
    """Cruces más frecuentes (mejor sembrado, peor sembrado) con P(avanza cada uno | se cruzan)."""
    cod = mejor * n_eq + peor
    cuenta = np.bincount(cod, minlength=n_eq * n_eq)
    victorias = np.bincount(cod, weights=gana.astype(float), minlength=n_eq * n_eq)
    out = []
    for c in np.argsort(-cuenta, kind="mergesort")[:tope]:
        if cuenta[c] < max(minimo * n_sim, 1):
            break
        p = cuenta[c] / n_sim
        pa = victorias[c] / cuenta[c]
        out.append({"mejor": eq[c // n_eq], "peor": eq[c % n_eq], "prob": float(p),
                    "ee": float(math.sqrt(p * (1 - p) / n_sim)), "p_avanza_mejor": float(pa),
                    "p_avanza_peor": float(1 - pa), "ee_avanza": float(math.sqrt(max(pa * (1 - pa), 0) / cuenta[c])),
                    "n": int(cuenta[c])})
    return out


def simular(pron=None, corte=None, df: pd.DataFrame | None = None, n_sim: int = N_SIM,
            n_muestras: int = N_MUESTRAS, semilla: int = SEMILLA, reglas: dict | None = None,
            torneo: str | None = None) -> dict:
    """
    Simula lo que falta del torneo y devuelve un dict serializable a JSON:
      meta, tabla_actual, por_equipo (puntos esperados, distribución del lugar final, P(clasificar),
      P(semifinal), P(final), P(campeón) con su error de Monte Carlo), cruces_cuartos (por llave),
      series_posibles (por fase), cuadro_mas_probable y series_reales (con el pronóstico exacto de cada
      serie que ya está en el calendario).
    Las `n_sim` simulaciones se reparten entre `n_muestras` muestras de parámetros (k >= 1 de la malla);
    con n_muestras = 0 se usa sólo la estimación puntual (k = 0).
    `pron` cumple el contrato del Pronosticador; si es None se usa `obtener_pronosticador(corte)`.
    """
    t0 = time.time()
    df = datos.cargar() if df is None else df
    if pron is None:
        from . import obtener_pronosticador
        pron = obtener_pronosticador(a_utc(corte) if corte is not None else None)
    corte = a_utc(corte if corte is not None else getattr(pron, "corte", None))
    reglas = reglas or cargar_reglas()
    torneo = torneo or getattr(pron, "torneo", None) or reglas["torneo"]
    eq = list(pron.equipos)
    n_eq = len(eq)
    n_clas = int(reglas.get("clasifican_directo", 8))
    cruces = [tuple(c) for c in reglas.get("liguilla", {}).get("cruces_cuartos", [[1, 8], [2, 7], [3, 6], [4, 5]])]
    est = estado_torneo(df, torneo, corte, eq)
    pend = est["pendientes"]
    n_p = len(pend)

    # n_muestras <= 0: sólo la estimación puntual (k = 0), sin incertidumbre de parámetros
    puntual = int(n_muestras) <= 0
    K = min(100, int(n_sim)) if puntual else max(1, min(int(n_muestras), int(n_sim)))   # grupos para el error de MC
    por_k = max(1, int(n_sim) // K)
    N = K * por_k
    mr = pron.malla(n=1 if puntual else K + 1, fase="regular", semilla=semilla)
    ml = pron.malla(n=1 if puntual else K + 1, fase="liguilla", semilla=semilla)
    if list(mr["equipos"]) != eq:
        raise ValueError("malla: el orden de los equipos no coincide con pron.equipos")
    rho_r, rho_l = float(mr.get("rho", 0.0)), float(ml.get("rho", 0.0))
    LLr, LVr = np.asarray(mr["lam_l"], float), np.asarray(mr["lam_v"], float)
    LLl, LVl = np.asarray(ml["lam_l"], float), np.asarray(ml["lam_v"], float)
    kidx = np.repeat(np.zeros(K, dtype=int) if puntual else np.arange(1, K + 1), por_k)
    rng = np.random.default_rng(semilla)
    filas = np.arange(N)

    # ---------------- fase regular ----------------
    pts = np.repeat(est["pts"][None, :], N, axis=0)
    gf = np.repeat(est["gf"][None, :], N, axis=0)
    gc = np.repeat(est["gc"][None, :], N, axis=0)
    gvis = np.repeat(est["gvis"][None, :], N, axis=0)
    pj_final = est["pj"].copy()
    pron_pend = []
    if n_p:
        il, iv = est["pend_il"], est["pend_iv"]
        pron_pend = pron.partidos(pend)
        # las lambdas del partido (con su contexto) centran la muestra de la malla (sede habitual)
        aj_l = np.array([d["lam_l"] for d in pron_pend]) / LLr[0, il, iv]
        aj_v = np.array([d["lam_v"] for d in pron_pend]) / LVr[0, il, iv]
        lam_l = LLr[kidx[:, None], il[None, :], iv[None, :]] * aj_l[None, :]
        lam_v = LVr[kidx[:, None], il[None, :], iv[None, :]] * aj_v[None, :]
        gl, gv = marcadores(rng, lam_l, lam_v, rho_r)
        pl = 3 * (gl > gv) + (gl == gv)
        pv = 3 * (gv > gl) + (gl == gv)
        for j in range(n_p):
            a, b = il[j], iv[j]
            pts[:, a] += pl[:, j]; pts[:, b] += pv[:, j]
            gf[:, a] += gl[:, j]; gc[:, a] += gv[:, j]
            gf[:, b] += gv[:, j]; gc[:, b] += gl[:, j]
            if est["pend_cuenta_vis"][j]:
                gvis[:, b] += gv[:, j]
            pj_final[a] += 1; pj_final[b] += 1
    coc_pj = est["coc_pj"] + (pj_final - est["pj"])
    coc = np.divide(est["coc_pts"][None, :] + (pts - est["pts"][None, :]), coc_pj[None, :],
                    out=np.zeros_like(pts), where=coc_pj[None, :] > 0)
    orden = ordenar(pts, gf - gc, gf, gvis, np.repeat(est["fair"][None, :], N, axis=0), coc, rng.random((N, n_eq)))
    pos = np.empty_like(orden)
    pos[filas[:, None], orden] = np.arange(n_eq)[None, :]

    # ---------------- liguilla ----------------
    tab = tabla_actual(est)
    pos_real = dict(zip(tab["equipo"], tab["pos"]))
    regular_completa = n_p == 0
    reales = series_reales(df, torneo, corte, eq, pos_real) if regular_completa else {f: [] for f in FASES_LIGUILLA}
    # lambdas propias de las piernas reales pendientes (contexto del partido) como multiplicador de la malla
    por_id = {}
    for f in FASES_LIGUILLA:
        for s in reales[f]:
            for p in s["piernas"].values():
                if not p["jugado"]:
                    por_id[p["id"]] = p
    if por_id:
        filas_df = df[df["id"].isin(list(por_id))]
        for d in pron.partidos(filas_df):
            p = por_id[int(d["id"])]
            p["lam_l"], p["lam_v"], p["rho"] = float(d["lam_l"]), float(d["lam_v"]), float(d.get("rho", rho_l))
            p["mult_l"] = p["lam_l"] / LLl[0, p["local"], p["visitante"]]
            p["mult_v"] = p["lam_v"] / LVl[0, p["local"], p["visitante"]]

    semilla_de = pos                                         # (N, 18): lugar 0-based de cada equipo
    sem = orden[:, :n_clas]                                  # (N, 8): equipo en cada siembra
    stats = {}
    gan_q = []
    cruces_llave = []
    for (s1, s2) in cruces:
        m_, p_ = sem[:, s1 - 1], sem[:, s2 - 1]
        g_ = _jugar_serie(rng, m_, p_, kidx, LLl, LVl, rho_l, "cuartos", reales)
        gan_q.append(np.where(g_, m_, p_))
        cruces_llave.append((f"{s1}-{s2}", m_, p_, g_))
    Wq = np.stack(gan_q, axis=1)                             # (N, 4) equipos que pasan a semifinales
    sq = np.sort(semilla_de[filas[:, None], Wq], axis=1)     # sus siembras, de mejor a peor (resiembra)
    eq_de_sem = orden                                        # orden[fila, siembra] = equipo
    semis = []
    gan_s = []
    for a_, b_ in ((0, 3), (1, 2)):
        m_, p_ = eq_de_sem[filas, sq[:, a_]], eq_de_sem[filas, sq[:, b_]]
        g_ = _jugar_serie(rng, m_, p_, kidx, LLl, LVl, rho_l, "semifinal", reales)
        gan_s.append(np.where(g_, m_, p_))
        semis.append((m_, p_, g_))
    Ws = np.stack(gan_s, axis=1)
    sf = np.sort(semilla_de[filas[:, None], Ws], axis=1)
    fm, fp = eq_de_sem[filas, sf[:, 0]], eq_de_sem[filas, sf[:, 1]]
    gfin = _jugar_serie(rng, fm, fp, kidx, LLl, LVl, rho_l, "final", reales)
    campeon = np.where(gfin, fm, fp)

    # ---------------- resúmenes ----------------
    def ind(equipos_por_sim: np.ndarray) -> np.ndarray:
        """(N, n_eq) indicadores de pertenencia a las columnas de `equipos_por_sim` (N, m)."""
        z = np.zeros((N, n_eq))
        z[filas[:, None], equipos_por_sim] = 1.0
        return z

    I_clas, I_semi, I_final, I_camp = ind(sem), ind(Wq), ind(Ws), ind(campeon[:, None])
    I_top4, I_lider = ind(orden[:, :4]), ind(orden[:, :1])
    dist = np.zeros((n_eq, n_eq))
    np.add.at(dist, (np.repeat(np.arange(n_eq)[None, :], N, axis=0).ravel(), pos.ravel()), 1.0)
    dist /= N
    resumen = {"puntos_esperados": (pts.mean(axis=0), _ee(pts, K)), "p_clasifica": (I_clas.mean(axis=0), _ee(I_clas, K)),
               "p_top4": (I_top4.mean(axis=0), _ee(I_top4, K)), "p_lider": (I_lider.mean(axis=0), _ee(I_lider, K)),
               "p_semifinal": (I_semi.mean(axis=0), _ee(I_semi, K)), "p_final": (I_final.mean(axis=0), _ee(I_final, K)),
               "p_campeon": (I_camp.mean(axis=0), _ee(I_camp, K))}
    pos_esp = (pos + 1).mean(axis=0)
    por_equipo = []
    for i in np.argsort(-resumen["p_campeon"][0] - 1e-6 * resumen["p_clasifica"][0] - 1e-9 * resumen["puntos_esperados"][0],
                        kind="mergesort"):
        d = {"equipo": eq[i], "pos_actual": int(pos_real[eq[i]]), "pts_actual": int(est["pts"][i]),
             "pj_actual": int(est["pj"][i]), "pos_esperada": float(pos_esp[i]),
             "pos_mas_probable": int(np.argmax(dist[i]) + 1), "posicion": [float(x) for x in dist[i]],
             "pts_min": int(pts[:, i].min()), "pts_max": int(pts[:, i].max())}
        for kx, (v, e) in resumen.items():
            d[kx] = float(v[i])
            d["ee_" + kx] = float(e[i])
        por_equipo.append(d)

    cruces_out = []
    for llave, m_, p_, g_ in cruces_llave:
        cruces_out.append({"llave": llave, "opciones": _pares(m_, p_, g_, n_eq, eq, N, 0.01, 8)})
    todos_q = (np.concatenate([c[1] for c in cruces_llave]), np.concatenate([c[2] for c in cruces_llave]),
               np.concatenate([c[3] for c in cruces_llave]))
    todos_s = (np.concatenate([c[0] for c in semis]), np.concatenate([c[1] for c in semis]),
               np.concatenate([c[2] for c in semis]))
    series_pos = {"cuartos": _pares(*todos_q, n_eq, eq, N, 0.01, 30),
                  "semifinal": _pares(*todos_s, n_eq, eq, N, 0.01, 15),
                  "final": _pares(fm, fp, gfin, n_eq, eq, N, 0.01, 15)}
    # cuadro de cuartos más probable (los ocho clasificados en su orden exacto)
    cod = (sem * (n_eq ** np.arange(n_clas))[None, :]).sum(axis=1)
    val, cnt = np.unique(cod, return_counts=True)
    c0 = int(val[np.argmax(cnt)])
    orden0 = [eq[(c0 // n_eq ** j) % n_eq] for j in range(n_clas)]
    cuadro = {"prob": float(cnt.max() / N), "siembra": orden0,
              "cruces": [{"llave": f"{a}-{b}", "mejor": orden0[a - 1], "peor": orden0[b - 1]} for a, b in cruces]}

    # series reales: pronóstico exacto con las lambdas puntuales + frecuencia de la simulación
    reales_out = []
    for f in FASES_LIGUILLA:
        for s in reales[f]:
            d = detalle_serie(s, eq, pos_real, LLl[0], LVl[0], rho_l)
            if f == "cuartos":
                m = np.zeros(N, dtype=bool); g = np.zeros(N, dtype=bool)
                for _, m_, p_, g_ in cruces_llave:
                    mm = (m_ == s["a"]) & (p_ == s["b"])
                    m |= mm; g |= mm & g_
            elif f == "semifinal":
                m = np.zeros(N, dtype=bool); g = np.zeros(N, dtype=bool)
                for m_, p_, g_ in semis:
                    mm = ((m_ == s["a"]) & (p_ == s["b"])) | ((m_ == s["b"]) & (p_ == s["a"]))
                    m |= mm; g |= mm & (np.where(g_, m_, p_) == s["a"])
            else:
                m = ((fm == s["a"]) & (fp == s["b"])) | ((fm == s["b"]) & (fp == s["a"]))
                g = m & (campeon == s["a"])
            d["p_avanza_mejor_sim"] = float(g.sum() / m.sum()) if m.any() else None
            d["n_sim_cruce"] = int(m.sum())
            reales_out.append(d)

    return {
        "meta": {"torneo": torneo, "corte_utc": corte.isoformat(), "n_sim": int(N), "n_muestras": 0 if puntual else int(K),
                 "sim_por_muestra": int(N) if puntual else int(por_k), "semilla": int(semilla), "modelo": getattr(pron, "nombre", type(pron).__name__),
                 "partidos_pendientes_regular": int(n_p), "regular_completa": bool(regular_completa),
                 "clasifican": n_clas, "segundos": round(time.time() - t0, 2)},
        "equipos": eq,
        "tabla_actual": json.loads(tab.to_json(orient="records", force_ascii=False)),
        "por_equipo": por_equipo,
        "cruces_cuartos": cruces_out,
        "cuadro_mas_probable": cuadro,
        "series_posibles": series_pos,
        "series_reales": reales_out,
    }


def _top_matriz(M: np.ndarray, k: int = 5) -> list[dict]:
    return [{"gl": int(x), "gv": int(y), "prob": float(p)} for x, y, p in arnes.top_marcadores(M, k)]


def detalle_serie(s: dict, eq: list[str], pos: dict[str, int], LL0: np.ndarray, LV0: np.ndarray,
                  rho: float = 0.0) -> dict:
    """
    Ficha de una serie real: piernas (resultado o pronóstico con 1X2 y marcadores), distribución del
    marcador global y P(avanza) de cada equipo CONDICIONADA a lo ya jugado (cálculo exacto con las
    lambdas puntuales; `mejor` es el mejor sembrado). Una serie que aún no tiene su vuelta en el
    calendario la completa con la localía de la regla (cierra en casa el mejor sembrado).
    """
    a, b, fase = s["a"], s["b"], s["fase"]
    piernas = dict(s["piernas"])
    for num, (loc, vis) in ((1, (b, a)), (2, (a, b))):
        if num not in piernas:
            piernas[num] = {"id": None, "fecha_utc": None, "local": loc, "visitante": vis, "jugado": False,
                            "gl": None, "gv": None, "mult_l": 1.0, "mult_v": 1.0}
    Ms, legs = {}, []
    for num in (1, 2):
        p = piernas[num]
        d = {"pierna": num, "id": p["id"], "fecha_utc": p["fecha_utc"].isoformat() if p.get("fecha_utc") is not None else None,
             "local": eq[p["local"]], "visitante": eq[p["visitante"]], "jugado": p["jugado"]}
        if p["jugado"]:
            Ms[num] = matriz_fija(p["gl"], p["gv"])
            d.update({"gl": p["gl"], "gv": p["gv"]})
        else:
            ll = p.get("lam_l", LL0[p["local"], p["visitante"]] * p.get("mult_l", 1.0))
            lv = p.get("lam_v", LV0[p["local"], p["visitante"]] * p.get("mult_v", 1.0))
            Ms[num] = arnes.matriz_marcadores(ll, lv, p.get("rho", rho))
            pr = arnes.p1x2(Ms[num])
            pr = np.asarray(pr, float).ravel()
            d.update({"lam_l": float(ll), "lam_v": float(lv), "p_local": float(pr[0]), "p_empate": float(pr[1]),
                      "p_visitante": float(pr[2]), "marcadores": _top_matriz(Ms[num], 5)})
        legs.append(d)
    p2 = piernas[2]
    extra = None
    if fase == "final":
        ll2 = p2.get("lam_l", LL0[p2["local"], p2["visitante"]] * p2.get("mult_l", 1.0))
        lv2 = p2.get("lam_v", LV0[p2["local"], p2["visitante"]] * p2.get("mult_v", 1.0))
        extra = (ll2 * FRACCION_EXTRA, lv2 * FRACCION_EXTRA)
    r = prob_serie(Ms[1], Ms[2], piernas[1]["local"] == a, p2["local"] == a,
                   "final" if fase == "final" else "posicion", extra)
    if s.get("ganador") is not None:
        r["p_mejor"], r["p_peor"] = (1.0, 0.0) if s["ganador"] == a else (0.0, 1.0)
    G = r["G"]
    orden = np.argsort(-G, axis=None, kind="mergesort")[:8]
    globales = [{"mejor": int(i // G.shape[1]), "peor": int(i % G.shape[1]), "prob": float(G.flat[i])}
                for i in orden if G.flat[i] > 1e-6]
    return {"fase": fase, "mejor": eq[a], "peor": eq[b], "siembra_mejor": int(pos.get(eq[a], 0)),
            "siembra_peor": int(pos.get(eq[b], 0)), "piernas": legs,
            "decidida": s.get("ganador") is not None,
            "ganador": eq[s["ganador"]] if s.get("ganador") is not None else None,
            "p_avanza_mejor": float(r["p_mejor"]), "p_avanza_peor": float(r["p_peor"]),
            "p_global_mejor": r["p_global_mejor"], "p_global_empate": r["p_global_empate"],
            "p_global_peor": r["p_global_peor"], "globales": globales,
            "regla_empate": ("tiempos extra y penales" if fase == "final" else "avanza el mejor sembrado")}


# ==================================================================================================
# Calibración histórica del simulador de series (DESARROLLO, sin fuga)
# ==================================================================================================
def _regla_de(torneo: str, fase: str) -> str:
    """Regla de desempate de la serie vigente en ese torneo."""
    if fase == "final":
        return "final"
    o = orden_torneo(torneo)
    return "gol_visitante" if orden_torneo("Apertura 2012") <= o <= orden_torneo("Clausura 2021") else "posicion"


def tabla_series_historicas(df: pd.DataFrame | None = None, hasta: str = "2025-07-01") -> pd.DataFrame:
    """
    Series a ida y vuelta (cuartos, semifinal, final) desde el Apertura 2012 y jugadas antes de `hasta`
    (por omisión el fin del DESARROLLO): torneo, fase, mejor y peor sembrado (posición en la tabla
    general de ese torneo), ids de ida y vuelta, si la vuelta fue en casa del mejor y si avanzó el mejor.
    """
    from .contexto import Contexto
    df = datos.cargar() if df is None else df
    fin = pd.Timestamp(hasta, tz="UTC")
    ctx = Contexto(fin, df)
    ser = ctx.series()
    ser = ser[ser["fase"].isin(FASES_LIGUILLA) & (ser["torneo"].map(orden_torneo) >= orden_torneo("Apertura 2012"))]
    lg = df[df["fase"].isin(FASES_LIGUILLA) & (df["estado"] == "jugado") & (df["fecha_utc"] < fin)]
    filas = []
    for r in ser.itertuples(index=False):
        g = lg[(lg["torneo"] == r.torneo) & (lg["fase"] == r.fase)
               & (np.minimum(lg["local"], lg["visitante"]) == r.a) & (np.maximum(lg["local"], lg["visitante"]) == r.b)]
        g = g.sort_values("fecha_utc")
        if len(g) != 2 or r.ganador is None:
            continue
        pos = ctx.tabla(r.torneo).set_index("equipo")["pos"]
        if r.a not in pos.index or r.b not in pos.index:
            continue
        mejor, peor = (r.a, r.b) if pos[r.a] < pos[r.b] else (r.b, r.a)
        ida, vta = g.iloc[0], g.iloc[1]
        gm = (ida.gl if ida.local == mejor else ida.gv) + (vta.gl if vta.local == mejor else vta.gv)
        gp = (ida.gl + ida.gv + vta.gl + vta.gv) - gm
        filas.append({"torneo": r.torneo, "orden": orden_torneo(r.torneo), "fase": r.fase, "mejor": mejor, "peor": peor,
                      "pos_mejor": int(pos[mejor]), "pos_peor": int(pos[peor]), "id_ida": int(ida.id), "id_vta": int(vta.id),
                      "ida_local": ida.local, "vta_local": vta.local, "ida_gl": int(ida.gl), "ida_gv": int(ida.gv),
                      "vta_gl": int(vta.gl), "vta_gv": int(vta.gv), "global_mejor": int(gm), "global_peor": int(gp),
                      "vuelta_en_casa_del_mejor": bool(vta.local == mejor), "avanza_mejor": int(r.ganador == mejor),
                      "regla": _regla_de(r.torneo, r.fase), "periodo": datos.periodo_de(r.torneo)})
    return pd.DataFrame(filas).sort_values(["orden", "fase"]).reset_index(drop=True)


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def calibrar_series(nombre: str = "poisson_simple", estricto: bool | None = None, rho: float = 0.0) -> dict:
    """
    Contrasta la P(avanza el mejor sembrado) del cálculo de series con lo ocurrido en las liguillas de
    DESARROLLO (Apertura 2016 a Clausura 2025), con las lambdas fuera de muestra guardadas de `nombre`
    y la regla de desempate vigente en cada torneo. Referencias: frecuencia histórica previa (series
    desde el Apertura 2012 anteriores al torneo) y 50/50. Errores por bootstrap de torneos completos.
    `estricto` añade la variante que reajusta PoissonSimple en el corte de la ida y usa esas lambdas
    para las dos piernas (la vuelta guardada se pronosticó ya conociendo la ida); sólo existe para
    poisson_simple. `rho` es la correlación de Dixon-Coles con la que se arman las matrices (los
    archivos de predicciones no la guardan). También mide si en liguilla hay menos goles o distinta
    ventaja de local que lo que esperan las lambdas.
    """
    estricto = (nombre == "poisson_simple") if estricto is None else (estricto and nombre == "poisson_simple")
    df = datos.cargar()
    pred = arnes.leer_pred(nombre).set_index("id")
    S = tabla_series_historicas(df)
    D = S[(S["periodo"] == "desarrollo") & S["id_ida"].isin(pred.index) & S["id_vta"].isin(pred.index)].reset_index(drop=True)
    y = D["avanza_mejor"].to_numpy(float)
    p_pre, p_cond, p_est, frec = [], [], [], []
    if estricto:
        from .pronosticador_provisional import Pronosticador as Provisional
    dif_ida = []
    for r in D.itertuples(index=False):
        a, b = pred.loc[r.id_ida], pred.loc[r.id_vta]
        M1 = arnes.matriz_marcadores(a.lam_l, a.lam_v, rho)
        M2 = arnes.matriz_marcadores(b.lam_l, b.lam_v, rho)
        ml1, ml2 = r.ida_local == r.mejor, r.vta_local == r.mejor
        extra = (b.lam_l * FRACCION_EXTRA, b.lam_v * FRACCION_EXTRA)
        p_pre.append(prob_serie(M1, M2, ml1, ml2, r.regla, extra)["p_mejor"])
        p_cond.append(prob_serie(matriz_fija(r.ida_gl, r.ida_gv), M2, ml1, ml2, r.regla, extra)["p_mejor"])
        previas = S[S["orden"] < r.orden]
        frec.append(previas["avanza_mejor"].mean())
        if estricto:
            pr = Provisional(corte=pd.Timestamp(a.corte), partidos=df)
            l1 = pr.modelo.lambdas(r.ida_local, r.peor if ml1 else r.mejor)
            l2 = pr.modelo.lambdas(r.vta_local, r.peor if ml2 else r.mejor)
            dif_ida.append(abs(l1[0] - a.lam_l) + abs(l1[1] - a.lam_v))
            p_est.append(prob_serie(arnes.matriz_marcadores(*l1), arnes.matriz_marcadores(*l2), ml1, ml2, r.regla,
                                    (l2[0] * FRACCION_EXTRA, l2[1] * FRACCION_EXTRA))["p_mejor"])
    P = {"simulador": np.array(p_pre), "frecuencia_previa": np.array(frec), "mitad": np.full(len(y), 0.5),
         "simulador_tras_ida": np.array(p_cond)}
    if estricto:
        P["simulador_estricto"] = np.array(p_est)
    bl = D["torneo"].to_numpy()

    def medida(p):
        return {"brier": metricas.bootstrap_bloques((p - y) ** 2, bl), "logloss": metricas.bootstrap_bloques(_ll(p, y), bl)}

    def contra(pa, pb):
        return {"brier": metricas.diferencia_pareada((pa - y) ** 2, (pb - y) ** 2, bl),
                "logloss": metricas.diferencia_pareada(_ll(pa, y), _ll(pb, y), bl)}

    out = {"modelo": nombre, "rho": float(rho), "n_series": int(len(D)), "n_torneos": int(D["torneo"].nunique()),
           "avanza_mejor_observado": metricas.bootstrap_bloques(y, bl),
           "media_pronosticada": {k: float(v.mean()) for k, v in P.items()},
           "sesgo_observado_menos_pronosticado": {k: metricas.bootstrap_bloques(y - v, bl) for k, v in P.items()},
           "metricas": {k: medida(v) for k, v in P.items()},
           "diferencias": {"simulador_vs_frecuencia_previa": contra(P["simulador"], P["frecuencia_previa"]),
                           "simulador_vs_mitad": contra(P["simulador"], P["mitad"]),
                           "tras_ida_vs_simulador": contra(P["simulador_tras_ida"], P["simulador"]),
                           "tras_ida_vs_frecuencia_previa": contra(P["simulador_tras_ida"], P["frecuencia_previa"])},
           "vuelta_en_casa_del_mejor": float(D["vuelta_en_casa_del_mejor"].mean()),
           "global_empatado": int((D["global_mejor"] == D["global_peor"]).sum())}
    if estricto:
        out["diferencias"]["estricto_vs_simulador"] = contra(P["simulador_estricto"], P["simulador"])
        out["diferencias"]["estricto_vs_frecuencia_previa"] = contra(P["simulador_estricto"], P["frecuencia_previa"])
        out["comprobacion_lambdas_ida"] = float(np.max(dif_ida)) if dif_ida else None
    # tabla de calibración (cuartiles de la probabilidad pronosticada) y por fase
    q = pd.qcut(P["simulador"], 4, labels=False, duplicates="drop")
    cal = pd.DataFrame({"g": q, "p": P["simulador"], "y": y}).groupby("g").agg(n=("y", "size"), p_media=("p", "mean"),
                                                                               p_min=("p", "min"), p_max=("p", "max"),
                                                                               observado=("y", "mean"))
    cal["ee_observado"] = np.sqrt(cal["observado"] * (1 - cal["observado"]) / cal["n"])
    out["calibracion"] = json.loads(cal.reset_index(drop=True).to_json(orient="records"))
    fases = pd.DataFrame({"fase": D["fase"], "p": P["simulador"], "p_tras_ida": P["simulador_tras_ida"], "y": y}) \
        .groupby("fase").agg(n=("y", "size"), pronosticado=("p", "mean"), observado=("y", "mean"))
    out["por_fase"] = json.loads(fases.reset_index().to_json(orient="records"))
    out["por_regla"] = json.loads(pd.DataFrame({"regla": D["regla"], "p": P["simulador"], "y": y}).groupby("regla")
                                  .agg(n=("y", "size"), pronosticado=("p", "mean"), observado=("y", "mean"))
                                  .reset_index().to_json(orient="records"))
    # pendiente de calibración (regresión logística de y sobre el logit de p)
    out["pendiente_calibracion"] = _pendiente(P["simulador"], y)

    # ---- goles y localía en liguilla frente a lo que esperan las lambdas (partidos de DESARROLLO) ----
    pr = pred.reset_index()
    pr = pr[pr["gl"].notna()]
    grupos = {"regular": pr["fase"] == "regular",
              "liguilla": pr["fase"].isin(FASES_LIGUILLA),
              "liguilla_ida": pr["fase"].isin(FASES_LIGUILLA) & (pr["pierna"] == 1),
              "liguilla_vuelta": pr["fase"].isin(FASES_LIGUILLA) & (pr["pierna"] == 2),
              "cuartos": pr["fase"] == "cuartos", "semifinal": pr["fase"] == "semifinal", "final": pr["fase"] == "final"}
    gol = {}
    for kx, m in grupos.items():
        t = pr[m]
        b = t["bloque"].to_numpy()
        tot_o, tot_e = t["gl"] + t["gv"], t["lam_l"] + t["lam_v"]
        gol[kx] = {"n": int(len(t)),
                   "goles_observados": metricas.bootstrap_bloques(tot_o, b),
                   "goles_esperados": float(tot_e.mean()),
                   "residuo_total": metricas.bootstrap_bloques(tot_o - tot_e, b),
                   "residuo_local": metricas.bootstrap_bloques(t["gl"] - t["lam_l"], b),
                   "residuo_visita": metricas.bootstrap_bloques(t["gv"] - t["lam_v"], b),
                   "ventaja_local_observada": metricas.bootstrap_bloques(t["gl"] - t["gv"], b),
                   "ventaja_local_esperada": float((t["lam_l"] - t["lam_v"]).mean()),
                   "residuo_ventaja_local": metricas.bootstrap_bloques((t["gl"] - t["gv"]) - (t["lam_l"] - t["lam_v"]), b),
                   "empates_observados": float((t["gl"] == t["gv"]).mean()), "empates_esperados": float(t["p_e"].mean())}
    out["goles_y_localia"] = gol
    return out


def _pendiente(p, y) -> dict:
    """Pendiente e intercepto de la regresión logística de y sobre logit(p) (1 y 0 = bien calibrado)."""
    from sklearn.linear_model import LogisticRegression
    x = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1))
    m = LogisticRegression(C=1e6, max_iter=1000).fit(x.reshape(-1, 1), y.astype(int))
    return {"pendiente": float(m.coef_[0, 0]), "intercepto": float(m.intercept_[0])}


# ==================================================================================================
def _limpio(o):
    """Convierte tipos de numpy/pandas a tipos de JSON."""
    if isinstance(o, dict):
        return {str(k): _limpio(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_limpio(v) for v in o]
    if isinstance(o, np.ndarray):
        return _limpio(o.tolist())
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Simulador de tabla, liguilla y campeón de la Liga MX")
    ap.add_argument("--corte", default=None, help="AAAA-MM-DDTHH:MM (hora de CDMX); por omisión, ahora")
    ap.add_argument("--n-sim", type=int, default=N_SIM)
    ap.add_argument("--n-muestras", type=int, default=N_MUESTRAS)
    ap.add_argument("--semilla", type=int, default=SEMILLA)
    ap.add_argument("--calibrar", action="store_true", help="calibración histórica de series (DESARROLLO)")
    ap.add_argument("--modelo", default="poisson_simple", help="predicciones de modelo/pred para --calibrar")
    ap.add_argument("--rho", type=float, default=0.0, help="rho de Dixon-Coles para --calibrar")
    a = ap.parse_args(argv)
    DIR_SALIDAS.mkdir(exist_ok=True)
    if a.calibrar:
        r = _limpio(calibrar_series(a.modelo, rho=a.rho))
        nombre = "calibracion_series.json" if a.modelo == "poisson_simple" else f"calibracion_series_{a.modelo}.json"
        (DIR_SALIDAS / nombre).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: r[k] for k in ("n_series", "media_pronosticada", "pendiente_calibracion")}, ensure_ascii=False))
        return 0
    r = simular(corte=a.corte, n_sim=a.n_sim, n_muestras=a.n_muestras, semilla=a.semilla)
    print(json.dumps(r["meta"], ensure_ascii=False))
    for d in r["por_equipo"]:
        print(f"{d['equipo']:<20s} pts {d['puntos_esperados']:5.1f}  clasifica {d['p_clasifica']:.3f}  "
              f"semi {d['p_semifinal']:.3f}  final {d['p_final']:.3f}  campeón {d['p_campeon']:.4f} (±{d['ee_p_campeon']:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
