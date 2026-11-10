# -*- coding: utf-8 -*-
"""
Auditoría de FUGAS (no es pytest; se corre a mano y tarda varios minutos):

    cd /home/user/SA/ligamx && python3 -m modelo.pruebas.auditoria_fugas [--n 40] [--procesos 3]

Qué hace, sin usar el arnés ni las cachés de variables o de predicciones:

  A. Zona horaria y cortes: recalcula con zoneinfo (sin pandas) el día local, el corte de bloque y el
     corte de día de cada partido y los compara con datos.cargar(); cuenta partidos nocturnos que caen
     en el día UTC siguiente y partidos que EMPIEZAN antes de un corte pero TERMINAN después.
  B. Reajuste del campeón DESDE CERO para n partidos al azar de PRUEBA (corte por día) y n de
     DESARROLLO (corte por bloque):
       etapa 1 (coeficientes): se escriben CSV truncados físicamente en el primer corte del torneo
               (ninguna fila posterior existe), se construyen las variables con ese historial y se
               ajusta un `Ajuste` nuevo; la regresión se repite con un optimizador propio (scipy).
       etapa 2 (partido): CSV truncados físicamente en el corte del partido (más la fila del partido
               sin marcador, sin estadísticas y sin alineación), variables recalculadas, y un
               Dixon-Coles PROPIO (Newton denso escrito aquí, rho por minimize_scalar).
     Las lambdas y el 1X2 se comparan con modelo/pred/ajuste*.parquet y dc*.parquet.
  C. Tablas de variables: las cachés contra una reconstrucción completa; tabla "partido" contra corte
     "dia" y contra "bloque" en las 6 columnas del campeón.
  D. Cálculo independiente (desde los CSV, sin variables.py) de tiros de los últimos 10 y de cambios
     entre los dos últimos onces, para TODOS los partidos, contra la tabla por bloque.

Resultado: modelo/pruebas/auditoria_resultados/fugas.json y un resumen en pantalla.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from scipy import optimize
from scipy.special import gammaln

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from modelo import datos, variables as V            # noqa: E402
from modelo.familias import candidatos as C         # noqa: E402

DIR_PRED = RAIZ / "modelo" / "pred"
DIR_SAL = Path(__file__).resolve().parent / "auditoria_resultados"
SEMILLA = 20261110
ZONA = ZoneInfo("America/Mexico_City")
COLS6 = ["sede_viaje_km_v", "once_previa_cambios_v", "juego10_tiros_f_l", "juego10_tiros_c_l",
         "juego10_tiros_f_v", "juego10_tiros_c_v"]
PREVIAS = ["id", "fecha_utc", "fecha_local", "anio", "torneo", "fase", "pierna", "estado", "local", "visitante",
           "estadio", "ciudad", "hora_local", "serie", "local_id", "visitante_id", "estadio_id", "temporada_espn",
           "fase_espn"]
ENTERAS_CERO = ["tiene_stats", "tiene_eventos", "tiene_alineaciones", "tiene_momios", "tiene_tarjetas"]


# ==================================================================================================
# Utilidades propias (no usan datos.py ni arnes.py)
# ==================================================================================================
def a_dt(txt: str) -> datetime:
    return datetime.strptime(txt, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def cortes_propios(txt: str) -> tuple[str, datetime, datetime]:
    """(día local, corte de bloque UTC, corte de día UTC) con zoneinfo: lunes o viernes 00:00 CDMX."""
    loc = a_dt(txt).astimezone(ZONA)
    dia = loc.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    ds = dia.weekday()
    atras = ds if ds <= 3 else ds - 4
    cb = (dia - timedelta(days=atras)).replace(tzinfo=ZONA).astimezone(timezone.utc)
    cd = dia.replace(tzinfo=ZONA).astimezone(timezone.utc)
    return dia.strftime("%Y-%m-%d"), cb, cd


def periodo(torneo: str) -> str:
    tipo, anio = torneo.rsplit(" ", 1)
    k = (int(anio), 0 if tipo.startswith("Clausura") else 1)
    return "calentamiento" if k < (2016, 1) else ("desarrollo" if k <= (2025, 0) else "prueba")


def orden_cal(c: datetime) -> int:
    """Ordinal de torneo por calendario (Apertura desde el 20 de junio), como declara el modelo."""
    loc = c.astimezone(ZONA)
    return 2 * loc.year + int(loc.month >= 7 or (loc.month == 6 and loc.day >= 20))


def fmt(c: datetime) -> str:
    return c.strftime("%Y-%m-%dT%H:%MZ")


def matriz(lam_l, lam_v, rho, n=10):
    """Matriz 11x11 Poisson + Dixon-Coles renormalizada, escrita aparte de arnes.matriz_marcadores."""
    k = np.arange(n + 1)
    pl = np.exp(-lam_l + k * math.log(lam_l) - gammaln(k + 1))
    pv = np.exp(-lam_v + k * math.log(lam_v) - gammaln(k + 1))
    M = np.outer(pl, pv)
    M[0, 0] *= 1 - lam_l * lam_v * rho
    M[0, 1] *= 1 + lam_l * rho
    M[1, 0] *= 1 + lam_v * rho
    M[1, 1] *= 1 - rho
    return M / M.sum()


def p1x2(M):
    return float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())


def dc_propio(h: pd.DataFrame, corte: datetime, vida_media=365.0, ridge=4.0, ventana=3650.0):
    """
    Dixon-Coles penalizado, implementación independiente: Newton denso sobre la verosimilitud de Poisson
    ponderada (peso 0.5^(edad/vida_media)), ridge sobre ataque y defensa, y rho por máxima verosimilitud
    perfilada con minimize_scalar. `h`: partidos jugados evaluables anteriores al corte (texto del CSV).
    """
    t = np.array([(corte - a_dt(x)).total_seconds() / 86400.0 for x in h["fecha_utc"]])
    ok = t <= ventana
    h, t = h[ok], t[ok]
    gl, gv = h["gl"].astype(float).to_numpy(), h["gv"].astype(float).to_numpy()
    eq = sorted(set(h["local"]) | set(h["visitante"]))
    ix = {e: i for i, e in enumerate(eq)}
    il = h["local"].map(ix).to_numpy()
    iv = h["visitante"].map(ix).to_numpy()
    n, ne = len(h), len(eq)
    p = 2 + 2 * ne
    X = np.zeros((2 * n, p))
    r = np.arange(n)
    X[r, 0] = 1; X[r, 1] = 1; X[r, 2 + il] = 1; X[r, 2 + ne + iv] = 1
    X[n + r, 0] = 1; X[n + r, 2 + iv] = 1; X[n + r, 2 + ne + il] = 1
    w = 0.5 ** (t / vida_media)
    ww, y = np.r_[w, w], np.r_[gl, gv]
    pen = np.r_[0.0, 0.0, np.full(2 * ne, ridge)]
    th = np.zeros(p)
    th[0] = math.log((ww @ y) / ww.sum())
    for _ in range(100):
        mu = np.exp(X @ th)
        g = X.T @ (ww * (y - mu)) - pen * th
        H = (X.T * (ww * mu)) @ X + np.diag(pen + 1e-12)
        paso = np.linalg.solve(H, g)
        th = th + paso
        if np.max(np.abs(paso)) < 1e-12:
            break
    lam, mu = np.exp(X[:n] @ th), np.exp(X[n:] @ th)

    def menos_logv(rho):
        tau = np.ones(n)
        m = (gl == 0) & (gv == 0); tau[m] = 1 - lam[m] * mu[m] * rho
        m = (gl == 0) & (gv == 1); tau[m] = 1 + lam[m] * rho
        m = (gl == 1) & (gv == 0); tau[m] = 1 + mu[m] * rho
        m = (gl == 1) & (gv == 1); tau[m] = 1 - rho
        if (tau <= 0).any():
            return 1e12
        return -float(w @ np.log(tau))

    rho = float(optimize.minimize_scalar(menos_logv, bounds=(-0.25, 0.25), method="bounded",
                                         options={"xatol": 1e-12}).x)
    return {"c": th[0], "h": th[1], "atk": dict(zip(eq, th[2:2 + ne])), "dfn": dict(zip(eq, th[2 + ne:])), "rho": rho}


def lam_dc(par, loc, vis):
    a, d = par["atk"], par["dfn"]
    return (math.exp(par["c"] + par["h"] + a.get(loc, 0.0) + d.get(vis, 0.0)),
            math.exp(par["c"] + a.get(vis, 0.0) + d.get(loc, 0.0)))


# ==================================================================================================
# Truncado físico
# ==================================================================================================
_crudo: dict = {}


def crudo():
    if not _crudo:
        p = pd.read_csv(RAIZ / "datos" / "partidos.csv", dtype=str, keep_default_na=False, encoding="utf-8")
        _crudo["p"] = p
        _crudo["tj"] = V.leer_tarjetas()
        _crudo["al"] = V.leer_alineaciones()
        _crudo["sd"] = V.leer_sedes()
    return _crudo["p"], _crudo["tj"], _crudo["al"], _crudo["sd"]


def truncar(corte: datetime, objetivo: str | None = None):
    """
    Tablas con SÓLO lo anterior al corte (las fechas ISO ordenan como texto). Si se pide un objetivo, su
    fila se agrega como 'programado' y sin nada posterior al silbatazo (ni marcador, ni estadísticas, ni
    momios, ni árbitro); sus alineaciones y tarjetas no existen en las tablas auxiliares.
    """
    p, tj, al, sd = crudo()
    antes = p[p["fecha_utc"] < fmt(corte)]
    ids = set(antes["id"])
    partes = [antes]
    if objetivo is not None:
        f = p[p["id"] == objetivo].copy()
        assert len(f) == 1 and f["fecha_utc"].iloc[0] >= fmt(corte)
        for c in f.columns:
            if c not in PREVIAS:
                f[c] = "0" if c in ENTERAS_CERO else ""
        f["estado"] = "programado"
        partes.append(f)
    pt = pd.concat(partes, ignore_index=True)
    return pt, tj[tj["partido_id"].isin(ids)], al[al["partido_id"].isin(ids)], sd


# ==================================================================================================
# B. Reajuste desde cero
# ==================================================================================================
def etapa1(arg):
    """Coeficientes de la corrección con todo truncado físicamente en c0. arg = (c0 ISO, modo de tabla)."""
    c0_txt, modo = arg
    c0 = a_dt(c0_txt)
    pt, tj, al, sd = truncar(c0)
    tab = V.construir(pt, corte=modo, tarjetas=tj, alineaciones=al, sedes=sd)
    C._tablas_variables.clear()
    C._tablas_variables[modo] = tab.set_index("id")[[c for g in C.GRUPOS_AJUSTE.values() for c in g]]
    with tempfile.TemporaryDirectory() as d:
        ruta = Path(d) / "partidos.csv"
        pt.to_csv(ruta, index=False, encoding="utf-8")
        h0 = datos.jugados(datos.cargar(ruta))
    assert (h0["fecha_utc"] < pd.Timestamp(c0)).all()
    m = C.Ajuste(C._dc(), ridge=1000, grupos=C.GRUPOS_FINALES, tabla=modo, nombre="ajuste")
    m.ajustar(h0, pd.Timestamp(c0))
    # regresión con optimizador propio: Poisson con offset log(lambda base) y ridge 1000 sobre z
    ids = np.array(sorted(m._lam))
    hh = h0.set_index("id").loc[ids]
    Z = tab.set_index("id").loc[ids, COLS6].to_numpy(float)
    media, desv = np.nanmean(Z, axis=0), np.nanstd(Z, axis=0)
    z = np.where(np.isfinite(Z), (Z - media) / desv, 0.0)
    lam = np.array([m._lam[int(i)] for i in ids])
    propio = []
    for j, y in ((0, hh["gl"].to_numpy(float)), (1, hh["gv"].to_numpy(float))):
        def f(b, y=y, j=j):
            eta = b[0] + z @ b[1:]
            mu = lam[:, j] * np.exp(eta)
            val = -(y * eta - mu).sum() + 500.0 * (b[1:] ** 2).sum()
            g = np.r_[-(y - mu).sum(), -(z.T @ (y - mu)) + 1000.0 * b[1:]]
            return val, g
        r = optimize.minimize(f, np.zeros(7), jac=True, method="L-BFGS-B", options={"ftol": 1e-15, "gtol": 1e-10})
        propio.append(r.x)
    dif = max(float(np.max(np.abs(propio[0] - m.b_l))), float(np.max(np.abs(propio[1] - m.b_v))))
    return {"c0": c0_txt, "modo": modo, "n": int(len(ids)), "media": media.tolist(), "desv": desv.tolist(),
            "b_l": propio[0].tolist(), "b_v": propio[1].tolist(), "dif_clase_vs_propio": dif,
            "b_l_clase": m.b_l.tolist(), "b_v_clase": m.b_v.tolist()}


def etapa2(arg):
    """Pronóstico de un partido con todo truncado físicamente en su corte. arg = (id, corte ISO, modo, coef)."""
    pid, c_txt, modo, coef = arg
    c = a_dt(c_txt)
    pt, tj, al, sd = truncar(c, pid)
    tab = V.construir(pt, corte=modo, tarjetas=tj, alineaciones=al, sedes=sd).set_index("id")
    x = tab.loc[int(pid), COLS6].to_numpy(float)
    fila = pt[pt["id"] == pid].iloc[0]
    h = pt[(pt["estado"] == "jugado") & (pt["id"] != pid)]
    h = h[~h["nota"].str.contains("escritorio|abandonado", case=False, regex=True)]
    par = dc_propio(h, c)
    bl, bv = lam_dc(par, fila["local"], fila["visitante"])
    z = (x - np.array(coef["media"])) / np.array(coef["desv"])
    z = np.where(np.isfinite(z), z, 0.0)
    fl = math.exp(coef["b_l"][0] + float(z @ np.array(coef["b_l"][1:])))
    fv = math.exp(coef["b_v"][0] + float(z @ np.array(coef["b_v"][1:])))
    pl, pe, pv = p1x2(matriz(bl * fl, bv * fv, par["rho"]))
    return {"id": int(pid), "base_l": bl, "base_v": bv, "rho": par["rho"], "f_l": fl, "f_v": fv,
            "lam_l": bl * fl, "lam_v": bv * fv, "p_l": pl, "p_e": pe, "p_v": pv,
            "vars": [None if not np.isfinite(v) else float(v) for v in x]}


def reajuste_desde_cero(n: int, procesos: int) -> dict:
    p, *_ = crudo()
    jug = p[(p["estado"] == "jugado")].copy()
    jug["periodo"] = jug["torneo"].map(periodo)
    cc = [cortes_propios(x) for x in jug["fecha_utc"]]
    jug["cb"], jug["cd"] = [x[1] for x in cc], [x[2] for x in cc]
    rng = np.random.default_rng(SEMILLA)
    casos = []                                   # (periodo, archivo ajuste, archivo dc, columna de corte, modo de tabla)
    for per, arch, arch_dc, col, modo in (("prueba", "ajuste__prueba__dia", "dc__prueba__dia", "cd", "partido"),
                                          ("desarrollo", "ajuste", "dc", "cb", "bloque")):
        guard = pd.read_parquet(DIR_PRED / f"{arch}.parquet")
        guard_dc = pd.read_parquet(DIR_PRED / f"{arch_dc}.parquet").set_index("id")
        ids = rng.choice(guard["id"].to_numpy(), size=min(n, len(guard)), replace=False)
        sub = jug[jug["periodo"] == per]
        cortes = sorted(set(sub[col]))
        primero = {}                             # ordinal de calendario -> primer corte del recorrido con ese ordinal
        for c in cortes:
            primero.setdefault(orden_cal(c), c)
        for i in ids:
            f = sub[sub["id"] == str(i)].iloc[0]
            c = f[col]
            g = guard[guard["id"] == i].iloc[0]
            assert pd.Timestamp(g["corte"]) == pd.Timestamp(c), "el corte guardado no coincide con el recalculado"
            casos.append({"id": str(i), "periodo": per, "modo": modo, "c": fmt(c), "c0": fmt(primero[orden_cal(c)]),
                          "g": {k: float(g[k]) for k in ("lam_l", "lam_v", "p_l", "p_e", "p_v", "x_factor_l", "x_factor_v")},
                          "g_dc": {k: float(guard_dc.loc[i, k]) for k in ("lam_l", "lam_v")}})
    claves = sorted({(k["c0"], k["modo"]) for k in casos})
    print(f"[B] {len(casos)} partidos, {len(claves)} ajustes de coeficientes desde cero...", flush=True)
    t0 = time.time()
    with Pool(procesos) as pool:
        e1 = {(r["c0"], r["modo"]): r for r in pool.imap_unordered(etapa1, claves)}
        print(f"[B] etapa 1 lista en {time.time() - t0:.0f} s", flush=True)
        e2 = pool.map(etapa2, [(k["id"], k["c"], k["modo"], e1[(k["c0"], k["modo"])]) for k in casos])
    filas = []
    for k, r in zip(casos, e2):
        g, gd = k["g"], k["g_dc"]
        filas.append({"id": r["id"], "periodo": k["periodo"], "corte": k["c"], "c0": k["c0"],
                      "d_base": max(abs(r["base_l"] - gd["lam_l"]), abs(r["base_v"] - gd["lam_v"])),
                      "d_factor": max(abs(r["f_l"] - g["x_factor_l"]), abs(r["f_v"] - g["x_factor_v"])),
                      "d_lam": max(abs(r["lam_l"] - g["lam_l"]), abs(r["lam_v"] - g["lam_v"])),
                      "d_p": max(abs(r["p_l"] - g["p_l"]), abs(r["p_e"] - g["p_e"]), abs(r["p_v"] - g["p_v"])),
                      "lam_l": r["lam_l"], "lam_l_guardada": g["lam_l"], "lam_v": r["lam_v"], "lam_v_guardada": g["lam_v"],
                      "vars_nan": int(sum(v is None for v in r["vars"]))})
    t = pd.DataFrame(filas)
    res = {"n": int(len(t)), "segundos": round(time.time() - t0, 1),
           "max_dif_coef_clase_vs_optimizador_propio": max(r["dif_clase_vs_propio"] for r in e1.values()),
           "por_periodo": {}}
    for per, g in t.groupby("periodo"):
        res["por_periodo"][per] = {"n": int(len(g)), "max_d_base_dc": float(g["d_base"].max()),
                                   "max_d_factor": float(g["d_factor"].max()), "max_d_lambda": float(g["d_lam"].max()),
                                   "max_d_prob_1x2": float(g["d_p"].max()),
                                   "peores": g.nlargest(3, "d_lam")[["id", "corte", "d_base", "d_factor", "d_lam", "d_p"]].to_dict("records")}
    res["coeficientes"] = [{k: v for k, v in r.items() if k in ("c0", "modo", "n", "b_l", "b_v")} for r in e1.values()]
    print(t.groupby("periodo")[["d_base", "d_factor", "d_lam", "d_p"]].max().to_string(), flush=True)
    return res


# ==================================================================================================
# A. Zona horaria y cortes
# ==================================================================================================
def zona_y_cortes() -> dict:
    p, *_ = crudo()
    d = datos.cargar().set_index("id")
    mal_dia = mal_cb = mal_cd = 0
    utc_sig = 0
    tarde = {"desarrollo": {"bloque": 0, "dia": 0}, "prueba": {"bloque": 0, "dia": 0}}
    min_gap = {"bloque": 1e9, "dia": 1e9}
    jug = p[p["estado"] == "jugado"]
    ini = {i: a_dt(x) for i, x in zip(jug["id"], jug["fecha_utc"])}
    todos_cb, todos_cd = set(), set()
    for i, x, tor in zip(jug["id"], jug["fecha_utc"], jug["torneo"]):
        dia, cb, cd = cortes_propios(x)
        f = d.loc[int(i)]
        mal_dia += dia != f["dia"]
        mal_cb += pd.Timestamp(cb) != f["corte_bloque"]
        mal_cd += pd.Timestamp(cd) != f["corte_dia"]
        utc_sig += x[:10] != dia
        if periodo(tor) in tarde:
            todos_cb.add(cb); todos_cd.add(cd)
            min_gap["bloque"] = min(min_gap["bloque"], (ini[i] - cb).total_seconds() / 3600)
            min_gap["dia"] = min(min_gap["dia"], (ini[i] - cd).total_seconds() / 3600)
    # partidos que empiezan antes de un corte y terminan (inicio + 2 h) después: están en `hist` de ese corte
    cb_s, cd_s = sorted(todos_cb), sorted(todos_cd)
    import bisect
    for i, x, tor in zip(jug["id"], jug["fecha_utc"], jug["torneo"]):
        per = periodo(tor)
        if per not in tarde:
            continue
        t0, t1 = ini[i], ini[i] + timedelta(hours=2)
        for nombre, lista in (("bloque", cb_s), ("dia", cd_s)):
            j = bisect.bisect_right(lista, t0)
            if j < len(lista) and lista[j] < t1:
                tarde[per][nombre] += 1
    return {"partidos_jugados": int(len(jug)), "dia_local_distinto": int(mal_dia), "corte_bloque_distinto": int(mal_cb),
            "corte_dia_distinto": int(mal_cd), "jugados_cuyo_dia_utc_no_es_el_local": int(utc_sig),
            "terminan_despues_de_un_corte_usado": tarde,
            "horas_minimas_del_corte_al_inicio": {k: round(v, 2) for k, v in min_gap.items()}}


# ==================================================================================================
# C. Tablas de variables
# ==================================================================================================
def tablas() -> dict:
    p, tj, al, sd = crudo()
    pv = V.leer_partidos()
    res = {}
    nuevas = {}
    for modo in ("partido", "bloque", "dia"):
        nuevas[modo] = V.construir(pv, corte=modo, tarjetas=tj, alineaciones=al, sedes=sd).set_index("id")
    for modo in ("partido", "bloque"):
        cache = V.cargar(modo).set_index("id")
        n = nuevas[modo]
        comunes = cache.index.intersection(n.index)
        a, b = cache.loc[comunes, COLS6].to_numpy(float), n.loc[comunes, COLS6].to_numpy(float)
        dist = ~((a == b) | (np.isnan(a) & np.isnan(b)))
        res[f"cache_{modo}"] = {"filas_cache": int(len(cache)), "filas_reconstruidas": int(len(n)),
                                "ids_sin_fila_en_cache": int(len(n.index.difference(cache.index))),
                                "celdas_distintas_6_columnas": int(dist.sum())}
    per = nuevas["partido"]["periodo"]
    for a_, b_ in (("partido", "dia"), ("partido", "bloque")):
        A, B = nuevas[a_], nuevas[b_].reindex(nuevas[a_].index)
        fila = {}
        for nombre in ("desarrollo", "prueba"):
            m = (per == nombre).to_numpy() & (A["estado"] == "jugado").to_numpy()
            x, y = A.loc[m, COLS6].to_numpy(float), B.loc[m, COLS6].to_numpy(float)
            dist = ~((x == y) | (np.isnan(x) & np.isnan(y)))
            fila[nombre] = {"partidos": int(m.sum()), "partidos_con_alguna_diferencia": int(dist.any(axis=1).sum()),
                            "por_columna": dict(zip(COLS6, dist.sum(axis=0).astype(int).tolist()))}
        res[f"{a_}_vs_{b_}"] = fila
    return res


# ==================================================================================================
# D. Cálculo independiente de tiros y rotación
# ==================================================================================================
def independiente() -> dict:
    p, tj, al, sd = crudo()
    jug = p[(p["estado"] == "jugado") & (p["gl"] != "") & (p["gv"] != "")].copy()
    jug["t"] = [a_dt(x) for x in jug["fecha_utc"]]
    jug = jug.sort_values(["t", "id"])
    # historial por equipo: (inicio, tiros a favor, tiros en contra, once o None)
    tit = al[al["titular"] == "1"].groupby(["partido_id", "equipo"])["jugador_id"].apply(list)
    onces = {k: frozenset(v) for k, v in tit.items() if len(v) == 11 and len(set(v)) == 11}
    hist: dict[str, list] = {}
    for r in jug.itertuples():
        con = r.tiene_stats == "1" and r.tiros_l != "" and r.tiros_v != ""
        tl, tv = (float(r.tiros_l), float(r.tiros_v)) if con else (None, None)
        hist.setdefault(r.local, []).append((r.t, tl, tv, onces.get((r.id, r.local))))
        hist.setdefault(r.visitante, []).append((r.t, tv, tl, onces.get((r.id, r.visitante))))
    cache = V.cargar("bloque").set_index("id")
    cache = cache[(cache["estado"] == "jugado") & (cache["fecha_utc"] >= "2016-07-01")]
    crud = p.set_index("id")
    n = dif_t = dif_c = 0
    ejemplos = []
    for pid, f in cache.iterrows():
        _, cb, _ = cortes_propios(crud.loc[str(pid), "fecha_utc"])
        esperado = {}
        for lado, eq in (("l", f["local"]), ("v", f["visitante"])):
            previos = [h for h in hist.get(eq, []) if h[0] < cb][-20:]
            con = [h for h in reversed(previos) if h[1] is not None][:10]
            if len(con) >= 5:
                esperado[f"juego10_tiros_f_{lado}"] = sum(h[1] for h in con) / len(con)
                esperado[f"juego10_tiros_c_{lado}"] = sum(h[2] for h in con) / len(con)
            else:
                esperado[f"juego10_tiros_f_{lado}"] = esperado[f"juego10_tiros_c_{lado}"] = float("nan")
            if lado == "v":
                xs = [h[3] for h in hist.get(eq, []) if h[0] < cb and h[3] is not None][-2:]
                esperado["once_previa_cambios_v"] = float(11 - len(xs[0] & xs[1])) if len(xs) == 2 else float("nan")
        n += 1
        for k, v in esperado.items():
            g = float(f[k])
            if not ((math.isnan(v) and math.isnan(g)) or abs(v - g) < 1e-9):
                if k.startswith("juego10"):
                    dif_t += 1
                else:
                    dif_c += 1
                if len(ejemplos) < 6:
                    ejemplos.append({"id": int(pid), "variable": k, "tabla": g, "independiente": v})
    return {"partidos_comparados": n, "celdas_de_tiros_distintas": dif_t, "celdas_de_rotacion_distintas": dif_c,
            "ejemplos": ejemplos}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--procesos", type=int, default=3)
    ap.add_argument("--solo", default="A,C,D,B")
    a = ap.parse_args()
    DIR_SAL.mkdir(exist_ok=True)
    ruta = DIR_SAL / "fugas.json"
    res = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    for parte, fn in (("A", zona_y_cortes), ("C", tablas), ("D", independiente),
                      ("B", lambda: reajuste_desde_cero(a.n, a.procesos))):
        if parte not in a.solo.split(","):
            continue
        t0 = time.time()
        res[parte] = fn()
        ruta.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"== {parte} ({time.time() - t0:.0f} s) ==")
        print(json.dumps({k: v for k, v in res[parte].items() if k != "coeficientes"}, ensure_ascii=False, indent=1,
                         default=str)[:3000], flush=True)


if __name__ == "__main__":
    main()
