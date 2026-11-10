# -*- coding: utf-8 -*-
"""
Auditoría · RÉPLICA independiente de las cifras de RESULTADOS.md (no es pytest):

    cd /home/user/SA/ligamx && python3 -m modelo.pruebas.auditoria_replica

No importa nada del proyecto (ni arnes, ni metricas, ni datos): lee datos/partidos.csv y los parquet de
modelo/pred/ y recalcula con fórmulas escritas aquí:

  1. Integridad de cada archivo de predicciones: ids = partidos evaluables del periodo, resultado igual
     al del CSV, probabilidades que suman 1, corte anterior al inicio e igual al recalculado con zoneinfo.
  2. Log-loss, RPS y Brier del campeón, dc, poisson_simple, elo, ensamble y el mercado.
  3. El mercado desde los momios crudos: método de Shin propio y filtro de momios en vivo.
  4. Comparaciones pareadas sobre exactamente los mismos partidos, con error estándar por bootstrap de
     bloques propio (otra semilla), por semana, por mes y con la fórmula analítica de conglomerados.
  5. Indicios de momios de "cierre" capturados con el partido en juego (apertura contra cierre).
  6. Diferencia ajuste - dc por torneo (para valorar su estabilidad).

Deja constancia de la lectura de la PRUEBA en modelo/pred/ACCESOS_PRUEBA.log (quien=auditoria).
Resultado: modelo/pruebas/auditoria_resultados/replica.json.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
DIR_PRED = RAIZ / "modelo" / "pred"
DIR_SAL = Path(__file__).resolve().parent / "auditoria_resultados"
ZONA = ZoneInfo("America/Mexico_City")

REPORTADO = {   # RESULTADOS.md y ARNES.md
    "desarrollo": {"ajuste": 1.0225, "dc": 1.0297, "poisson_simple": 1.0309, "mercado_cierre_shin": 1.0028,
                   "ensamble": 1.0254, "elo": 1.0316},
    "prueba": {"elo": 1.0221, "ensamble": 1.0225, "dc": 1.0264, "ajuste": 1.0272, "poisson_simple": 1.0276,
               "cerebro_original_limpio": 1.0325, "mercado_cierre_shin": 1.0030},
    "pareadas": {("desarrollo", "ajuste", "mercado_cierre_shin"): (0.0095, 0.0043),
                 ("desarrollo", "ajuste", "dc"): (-0.0072, 0.0013),
                 ("desarrollo", "ajuste", "ensamble"): (-0.0029, 0.0010),
                 ("desarrollo", "poisson_simple", "mercado_cierre_shin"): (0.0185, 0.0046),
                 ("prueba", "ajuste", "mercado_cierre_shin"): (0.0237, 0.0080),
                 ("prueba", "ajuste", "dc"): (0.0008, 0.0045),
                 ("prueba", "ensamble", "ajuste"): (-0.0047, 0.0028),
                 ("prueba", "elo", "mercado_cierre_shin"): (0.0185, 0.0075),
                 ("prueba", "ajuste", "poisson_simple"): (-0.0004, 0.0042)},
}


# ==================================================================================================
# Fórmulas propias
# ==================================================================================================
def periodo(torneo: str) -> str:
    tipo, anio = torneo.rsplit(" ", 1)
    k = (int(anio), 0 if tipo.startswith("Clausura") else 1)
    return "calentamiento" if k < (2016, 1) else ("desarrollo" if k <= (2025, 0) else "prueba")


def cortes(txt: str):
    loc = datetime.strptime(txt, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(ZONA)
    dia = loc.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    ds = dia.weekday()
    lunes_o_viernes = dia - timedelta(days=ds if ds <= 3 else ds - 4)
    return (lunes_o_viernes.strftime("%Y-%m-%d"), pd.Timestamp(lunes_o_viernes.replace(tzinfo=ZONA)).tz_convert("UTC"),
            pd.Timestamp(dia.replace(tzinfo=ZONA)).tz_convert("UTC"), loc)


def metricas(P: np.ndarray, y: np.ndarray):
    """(log-loss, RPS, Brier) por partido. y: 0 local, 1 empate, 2 visita."""
    n = len(y)
    O = np.zeros((n, 3))
    O[np.arange(n), y] = 1.0
    ll = -np.log(P[np.arange(n), y])
    ca, co = np.cumsum(P, axis=1), np.cumsum(O, axis=1)
    rps = ((ca[:, :2] - co[:, :2]) ** 2).sum(axis=1) / 2.0
    brier = ((P - O) ** 2).sum(axis=1)
    return ll, rps, brier


def shin(o: np.ndarray) -> np.ndarray:
    """Probabilidades sin margen por el método de Shin (bisección sobre z). o: momios decimales (3,)."""
    pi = 1.0 / o
    S = pi.sum()

    def p(z):
        return (np.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / S) - z) / (2.0 * (1.0 - z))

    lo, hi = 0.0, 0.4
    for _ in range(200):
        z = (lo + hi) / 2
        if p(z).sum() > 1.0:
            lo = z
        else:
            hi = z
    q = p((lo + hi) / 2)
    return q / q.sum()


def ee_bootstrap(v: np.ndarray, grupos: np.ndarray, B: int = 4000, semilla: int = 7) -> tuple[float, float, float]:
    """Error estándar e IC 95% de la media remuestreando grupos enteros (estimador de razón)."""
    cod, _ = pd.factorize(grupos)
    nb = cod.max() + 1
    s = np.bincount(cod, weights=v, minlength=nb)
    c = np.bincount(cod, minlength=nb).astype(float)
    rng = np.random.default_rng(semilla)
    ix = rng.integers(0, nb, size=(B, nb))
    rep = s[ix].sum(axis=1) / c[ix].sum(axis=1)
    return float(rep.std(ddof=1)), float(np.percentile(rep, 2.5)), float(np.percentile(rep, 97.5))


def ee_analitico(v: np.ndarray, grupos: np.ndarray) -> float:
    """Error estándar robusto a conglomerados de la media (linealización del estimador de razón)."""
    cod, _ = pd.factorize(grupos)
    nb = cod.max() + 1
    m = v.mean()
    r = np.bincount(cod, weights=v - m, minlength=nb)
    return float(math.sqrt(nb / (nb - 1) * (r ** 2).sum()) / len(v))


# ==================================================================================================
def main():
    DIR_SAL.mkdir(exist_ok=True)
    with open(DIR_PRED / "ACCESOS_PRUEBA.log", "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}\taccion=leer\tquien=auditoria\tmodelo=todos\t"
                 f"granularidad=dia\tpid={os.getpid()}\targv={' '.join(sys.argv)}\t"
                 "nota=replica independiente de las cifras ya reportadas; no se evalua ningun modelo nuevo\n")
    p = pd.read_csv(RAIZ / "datos" / "partidos.csv", dtype=str, keep_default_na=False, encoding="utf-8")
    p["periodo"] = p["torneo"].map(periodo)
    jug = p[(p["estado"] == "jugado")].copy()
    jug["escritorio"] = jug["nota"].str.contains("escritorio|abandonado", case=False, regex=True)
    ev = jug[~jug["escritorio"]].copy()
    ev["gl"], ev["gv"] = ev["gl"].astype(int), ev["gv"].astype(int)
    ev["y"] = np.where(ev["gl"] > ev["gv"], 0, np.where(ev["gl"] == ev["gv"], 1, 2))
    cc = [cortes(x) for x in ev["fecha_utc"]]
    ev["bloque"], ev["cb"], ev["cd"] = [c[0] for c in cc], [c[1] for c in cc], [c[2] for c in cc]
    ev["semana"] = [f"{c[3].isocalendar()[0]}-{c[3].isocalendar()[1]:02d}" for c in cc]
    ev["mes"] = [c[3].strftime("%Y-%m") for c in cc]
    ev["id"] = ev["id"].astype("int64")
    ev = ev.set_index("id")
    res: dict = {"integridad": {}, "metricas": {}, "pareadas": [], "mercado": {}, "por_torneo": {}}
    print(f"evaluables: desarrollo {int((ev.periodo == 'desarrollo').sum())}, prueba {int((ev.periodo == 'prueba').sum())}")

    # ---------------------------------------------------------------- 1 y 2: archivos y métricas
    modelos = {"desarrollo": ["ajuste", "dc", "poisson_simple", "mercado_cierre_shin", "ensamble", "elo", "dc2", "tiros",
                              "frecuencias"],
               "prueba": ["ajuste", "dc", "poisson_simple", "mercado_cierre_shin", "ensamble", "elo", "dc2", "tiros",
                          "cerebro_original_limpio", "frecuencias"]}
    porp: dict = {}
    for per, lista in modelos.items():
        suf = "" if per == "desarrollo" else "__prueba__dia"
        col_corte = "cb" if per == "desarrollo" else "cd"
        esperados = set(ev.index[ev["periodo"] == per])
        for m in lista:
            d = pd.read_parquet(DIR_PRED / f"{m}{suf}.parquet").set_index("id")
            P = d[["p_l", "p_e", "p_v"]].to_numpy(float)
            real = ev.loc[d.index]
            integ = {"n": int(len(d)), "ids_fuera_del_periodo": int(len(set(d.index) - esperados)),
                     "evaluables_sin_pronostico": int(len(esperados - set(d.index))),
                     "duplicados": int(d.index.duplicated().sum()),
                     "resultado_distinto_al_csv": int((d["resultado"].to_numpy() != real["y"].to_numpy()).sum()),
                     "max_abs_suma_menos_1": float(np.abs(P.sum(axis=1) - 1).max()),
                     "prob_fuera_de_0_1": int(((P <= 0) | (P >= 1)).sum()),
                     "corte_no_anterior_al_inicio": int((pd.to_datetime(d["corte"], utc=True) >= pd.to_datetime(d["fecha_utc"], utc=True)).sum()),
                     "corte_distinto_al_recalculado": int((pd.to_datetime(d["corte"], utc=True).to_numpy() != pd.DatetimeIndex(real[col_corte]).to_numpy()).sum())}
            res["integridad"][f"{per}/{m}"] = integ
            ll, rps, br = metricas(P, real["y"].to_numpy())
            porp[(per, m)] = pd.DataFrame({"ll": ll, "rps": rps, "brier": br}, index=d.index)
            ee, _, _ = ee_bootstrap(ll, real["bloque"].to_numpy())
            rep = REPORTADO[per].get(m)
            res["metricas"][f"{per}/{m}"] = {"n": int(len(d)), "logloss": float(ll.mean()), "ee": ee, "rps": float(rps.mean()),
                                             "brier": float(br.mean()), "reportado": rep,
                                             "coincide_a_4_decimales": None if rep is None else bool(abs(round(float(ll.mean()), 4) - rep) < 1e-9)}
            print(f"{per:10s} {m:26s} n={len(d):5d}  ll={ll.mean():.4f} (ee {ee:.4f})  rps={rps.mean():.4f}  brier={br.mean():.4f}"
                  f"  reportado={rep}")
    malos = {k: v for k, v in res["integridad"].items()
             if any(v[c] for c in v if c not in ("n", "max_abs_suma_menos_1", "evaluables_sin_pronostico")) or v["max_abs_suma_menos_1"] > 1e-9}
    print("archivos con problemas de integridad:", malos or "ninguno")

    # ---------------------------------------------------------------- 3: el mercado desde los momios crudos
    for per in ("desarrollo", "prueba"):
        sub = ev[ev["periodo"] == per]
        o = sub[["ml_l", "ml_e", "ml_v"]].apply(pd.to_numeric, errors="coerce")
        hay = o.notna().all(axis=1)
        tl = pd.to_numeric(sub["total_linea"], errors="coerce")
        ov, un = pd.to_numeric(sub["over"], errors="coerce"), pd.to_numeric(sub["under"], errors="coerce")
        vivo = hay & ((o.min(axis=1) < 1.08) | (o["ml_e"] < 2.0) | (o["ml_e"] > 12) | ((tl == 2.5) & ((ov < 1.15) | (un < 1.15))))
        usa = hay & ~vivo
        Q = np.array([shin(r) for r in o[usa].to_numpy(float)])
        ll, rps, br = metricas(Q, sub.loc[usa, "y"].to_numpy())
        suf = "" if per == "desarrollo" else "__prueba__dia"
        g = pd.read_parquet(DIR_PRED / f"mercado_cierre_shin{suf}.parquet").set_index("id")
        mismos = set(g.index) == set(sub.index[usa])
        dif = float(np.abs(g.loc[sub.index[usa], ["p_l", "p_e", "p_v"]].to_numpy(float) - Q).max()) if mismos else None
        Qv = np.array([shin(r) for r in o[hay].to_numpy(float)])
        llv, _, _ = metricas(Qv, sub.loc[hay, "y"].to_numpy())
        margen = (1.0 / o[usa]).sum(axis=1) - 1
        res["mercado"][per] = {"evaluables": int(len(sub)), "con_momios": int(hay.sum()), "marcados_en_vivo": int(vivo.sum()),
                               "ids_en_vivo": [int(i) for i in sub.index[vivo]], "usados": int(usa.sum()),
                               "mismos_partidos_que_el_archivo": bool(mismos), "max_dif_prob_shin_propio_vs_archivo": dif,
                               "logloss_shin_propio": float(ll.mean()), "rps": float(rps.mean()), "brier": float(br.mean()),
                               "logloss_si_no_se_filtrara_en_vivo": float(llv.mean()), "margen_medio": float(margen.mean()),
                               "proveedores": sub.loc[usa, "proveedor"].value_counts().to_dict()}
        print(f"mercado {per}: {res['mercado'][per]}")

    # ---------------------------------------------------------------- 4: pareadas
    for (per, a, b), (d_rep, ee_rep) in REPORTADO["pareadas"].items():
        A, Bm = porp[(per, a)], porp[(per, b)]
        com = A.index.intersection(Bm.index)
        v = (A.loc[com, "ll"] - Bm.loc[com, "ll"]).to_numpy()
        e = ev.loc[com]
        ee_b, lo, hi = ee_bootstrap(v, e["bloque"].to_numpy())
        fila = {"periodo": per, "a": a, "b": b, "n": int(len(com)), "n_a": int(len(A)), "n_b": int(len(Bm)),
                "dif": float(v.mean()), "dif_reportada": d_rep, "ee_bloque": ee_b, "ee_reportado": ee_rep,
                "ic95": [lo, hi], "ee_partido": float(v.std(ddof=1) / math.sqrt(len(v))),
                "ee_semana": ee_bootstrap(v, e["semana"].to_numpy())[0], "ee_mes": ee_bootstrap(v, e["mes"].to_numpy())[0],
                "ee_analitico_bloque": ee_analitico(v, e["bloque"].to_numpy()),
                "d_rps": float((A.loc[com, "rps"] - Bm.loc[com, "rps"]).mean()),
                "d_brier": float((A.loc[com, "brier"] - Bm.loc[com, "brier"]).mean())}
        res["pareadas"].append(fila)
        print(f"{per:10s} {a} - {b}: n={fila['n']} dif={fila['dif']:+.4f} (rep {d_rep:+.4f})  ee bloque={ee_b:.4f} (rep {ee_rep:.4f})"
              f"  partido={fila['ee_partido']:.4f} semana={fila['ee_semana']:.4f} mes={fila['ee_mes']:.4f} analitico={fila['ee_analitico_bloque']:.4f}")
    # todo el periodo: ajuste - dc (desarrollo por bloque + prueba por día), reportado -0.0061 (0.0013)
    v = pd.concat([porp[("desarrollo", "ajuste")]["ll"] - porp[("desarrollo", "dc")]["ll"],
                   porp[("prueba", "ajuste")]["ll"] - porp[("prueba", "dc")]["ll"]])
    ee_b, lo, hi = ee_bootstrap(v.to_numpy(), ev.loc[v.index, "bloque"].to_numpy())
    res["ajuste_menos_dc_todo"] = {"n": int(len(v)), "dif": float(v.mean()), "ee": ee_b, "reportado": [-0.0061, 0.0013]}
    print("ajuste - dc en todo:", res["ajuste_menos_dc_todo"])

    # regla pre-registrada: ¿algún candidato supera a `ajuste` en la PRUEBA por más de 2 ee pareados?
    res["regla_prueba"] = []
    for c in ("ensamble", "elo", "dc2", "dc", "tiros"):
        v = (porp[("prueba", c)]["ll"] - porp[("prueba", "ajuste")]["ll"])
        ee_b, lo, hi = ee_bootstrap(v.to_numpy(), ev.loc[v.index, "bloque"].to_numpy())
        res["regla_prueba"].append({"candidato": c, "dif_vs_ajuste": float(v.mean()), "ee": ee_b, "z": float(v.mean() / ee_b)})
        print(f"regla PRUEBA: {c} - ajuste = {v.mean():+.4f} (ee {ee_b:.4f}, z {v.mean() / ee_b:+.2f})")
    # ¿y en DESARROLLO? cada candidato contra `ajuste` (para la discusión del sesgo de selección)
    for c in ("ensamble", "elo", "dc2", "dc", "tiros", "poisson_simple"):
        v = (porp[("desarrollo", c)]["ll"] - porp[("desarrollo", "ajuste")]["ll"])
        ee_b, _, _ = ee_bootstrap(v.to_numpy(), ev.loc[v.index, "bloque"].to_numpy())
        print(f"DESARROLLO: {c} - ajuste = {v.mean():+.4f} (ee {ee_b:.4f}, z {v.mean() / ee_b:+.2f})")

    # ---------------------------------------------------------------- 5: ¿cierres capturados en juego?
    sub = ev[ev["periodo"] == "prueba"]
    oc = sub[["ml_l", "ml_e", "ml_v"]].apply(pd.to_numeric, errors="coerce")
    oa = sub[["ml_l_abre", "ml_e_abre", "ml_v_abre"]].apply(pd.to_numeric, errors="coerce")
    amb = oc.notna().all(axis=1) & oa.notna().all(axis=1)
    Qc = np.array([shin(r) for r in oc[amb].to_numpy(float)])
    Qa = np.array([shin(r) for r in oa[amb].to_numpy(float)])
    y = sub.loc[amb, "y"].to_numpy()
    k = np.arange(len(y))
    mov_real = Qc[k, y] - Qa[k, y]                       # cuánto subió la probabilidad de lo que acabó pasando
    mov_max = np.abs(Qc - Qa).max(axis=1)
    grande = mov_max > 0.10
    llc, lla = -np.log(Qc[k, y]), -np.log(Qa[k, y])
    res["apertura_vs_cierre_prueba"] = {
        "n": int(amb.sum()), "logloss_apertura": float(lla.mean()), "logloss_cierre": float(llc.mean()),
        "movimiento_abs_max_mediana": float(np.median(mov_max)), "movimiento_abs_max_p90": float(np.percentile(mov_max, 90)),
        "partidos_con_movimiento_mayor_a_0.10": int(grande.sum()),
        "de_esos_hacia_el_resultado_real": int((mov_real[grande] > 0).sum()),
        "ganancia_logloss_del_cierre_en_esos": float((lla - llc)[grande].sum() / len(y)),
        "ganancia_logloss_del_cierre_en_el_resto": float((lla - llc)[~grande].sum() / len(y)),
        "proveedores": sub.loc[amb, "proveedor"].value_counts().to_dict()}
    print("apertura contra cierre (PRUEBA):", res["apertura_vs_cierre_prueba"])

    # ---------------------------------------------------------------- 6: ajuste - dc por torneo
    filas = []
    for per in ("desarrollo", "prueba"):
        v = porp[(per, "ajuste")]["ll"] - porp[(per, "dc")]["ll"]
        t = ev.loc[v.index, "torneo"]
        for tor, g in v.groupby(t.to_numpy()):
            filas.append({"periodo": per, "torneo": tor, "n": int(len(g)), "ajuste_menos_dc": float(g.mean())})
    orden = lambda s: (int(s.rsplit(" ", 1)[1]), 0 if s.startswith("Clausura") else 1)
    filas.sort(key=lambda f: orden(f["torneo"]))
    res["por_torneo"] = filas
    des = [f["ajuste_menos_dc"] for f in filas if f["periodo"] == "desarrollo"]
    print("ajuste - dc por torneo:", " ".join(f"{f['torneo'][:1]}{f['torneo'][-2:]}:{f['ajuste_menos_dc']:+.4f}" for f in filas))
    print(f"desarrollo: ajuste gana en {sum(x < 0 for x in des)} de {len(des)} torneos; media de torneos {np.mean(des):+.4f}, "
          f"desviación entre torneos {np.std(des, ddof=1):.4f}")
    res["torneos_desarrollo_ganados_por_ajuste"] = [int(sum(x < 0 for x in des)), len(des)]
    (DIR_SAL / "replica.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
