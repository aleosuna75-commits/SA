# -*- coding: utf-8 -*-
"""
Auditoría · PRODUCCIÓN (no es pytest; ~2 minutos):

    cd /home/user/SA/ligamx && python3 -m modelo.pruebas.auditoria_produccion

Arma el JSON de la página en una carpeta temporal (sin sellar y sin tocar salidas/) y revisa:

  a. probabilidades: 1X2, matriz, mercados complementarios y distribuciones que suman 1; sin NaN ni nulos;
  b. 1X2, más de 2.5, ambos anotan y marcador más probable de 3 partidos recalculados "a mano" con
     Poisson + Dixon-Coles a partir de las lambdas y rho exportadas (fórmulas escritas aquí);
  c. la probabilidad conjunta de 3 combinadas por simulación (marcador final sorteado de la matriz y goles
     repartidos entre mitades con una binomial), con predicados escritos aquí;
  d. la tabla actual contra datos/tabla_apertura2026.csv y contra un recuento propio de partidos.csv;
  e. proyección: campeón suma 1, finalistas 2, semifinalistas 4, clasificados 8, monotonía por equipo;
  f. desempates: orden de criterios de la tabla y reglas de series contra config/torneo.json;
  g. un simulador PROPIO del resto del torneo (escrito aquí, con las lambdas puntuales) contra el del
     proyecto con n_muestras = 0, y contra lo exportado (que añade la incertidumbre de parámetros);
  h. robustez: equipo sin historial, equipo sin estadísticas ni alineaciones recientes, caché de
     variables desactualizada (¿avisa el Pronosticador?) y caché ausente;
  i. cuánto cambia P(campeón) si se usa ensamble, dc o elo en vez del campeón (modelos indistinguibles).

Resultado: modelo/pruebas/auditoria_resultados/produccion.json.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import warnings
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("AGENTE", "auditoria")

import numpy as np
import pandas as pd
from scipy.special import gammaln

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from modelo import datos, variables as V                      # noqa: E402
from modelo.familias import candidatos as C                   # noqa: E402
from modelo.pronostico import Pronosticador                   # noqa: E402
from produccion import exportar, simulador                    # noqa: E402
from produccion import mercados as mk                         # noqa: E402

DIR_SAL = Path(__file__).resolve().parent / "auditoria_resultados"
TOL = 2e-4                                                    # el JSON redondea a 4 decimales


# ==================================================================================================
# Fórmulas propias
# ==================================================================================================
def matriz(lam_l, lam_v, rho, n=10):
    k = np.arange(n + 1)
    pl = np.exp(-lam_l + k * math.log(lam_l) - gammaln(k + 1))
    pv = np.exp(-lam_v + k * math.log(lam_v) - gammaln(k + 1))
    M = np.outer(pl, pv)
    M[0, 0] *= 1 - lam_l * lam_v * rho
    M[0, 1] *= 1 + lam_l * rho
    M[1, 0] *= 1 + lam_v * rho
    M[1, 1] *= 1 - rho
    return M / M.sum()


def predicado(clave, x, y, h, a):
    """Mercado -> vector booleano, a partir del marcador final (x, y) y del descanso (h, a). None = no cubierto."""
    D, T, D1, T1 = x - y, x + y, h - a, h + a
    D2, T2 = (x - h) - (y - a), (x - h) + (y - a)
    t = {"1": D > 0, "X": D == 0, "2": D < 0, "1X": D >= 0, "X2": D <= 0, "12": D != 0,
         "H_L-1.5": D >= 2, "H_V+1.5": D <= 1, "H_V-1.5": D <= -2, "H_L+1.5": D >= -1,
         "O15": T >= 2, "U15": T <= 1, "O25": T >= 3, "U25": T <= 2, "O35": T >= 4, "U35": T <= 3,
         "AA_SI": (x > 0) & (y > 0), "AA_NO": (x == 0) | (y == 0),
         "L_ANOTA": x >= 1, "L_2MAS": x >= 2, "L_U15": x <= 1, "PC_V": x == 0,
         "V_ANOTA": y >= 1, "V_2MAS": y >= 2, "V_U15": y <= 1, "PC_L": y == 0,
         "D_1": D1 > 0, "D_X": D1 == 0, "D_2": D1 < 0, "D_1X": D1 >= 0, "D_X2": D1 <= 0, "D_12": D1 != 0,
         "G1T_SI": T1 >= 1, "G1T_NO": T1 == 0, "O15_1T": T1 >= 2, "U15_1T": T1 <= 1, "G2T_SI": T2 >= 1, "G2T_NO": T2 == 0,
         "MAS_1T": T1 > T2, "MAS_2T": T2 > T1, "MIT_IGUAL": T1 == T2,
         "GM_L": (D1 > 0) | (D2 > 0), "GM_V": (D1 < 0) | (D2 < 0)}
    return t.get(clave)


def sortear(rng, M, n):
    j = rng.choice(M.size, size=n, p=M.ravel() / M.sum())
    return j // M.shape[1], j % M.shape[1]


def caminar(o, ruta=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from caminar(v, f"{ruta}.{k}" if ruta else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from caminar(v, f"{ruta}[{i}]")
    else:
        yield ruta, o


# ==================================================================================================
def revisar_documento(doc: dict, pron, res: dict):
    pend = doc["pendientes"]
    # ---- a. sumas y nulos
    a = {"pendientes": len(pend), "max_abs_1x2_menos_1": 0.0, "max_abs_matriz_menos_1": 0.0, "pares_complementarios_malos": [],
         "prob_fuera_de_0_1": [], "nulos_en_campos_numericos": [], "nan_o_inf": []}
    for p in pend:
        a["max_abs_1x2_menos_1"] = max(a["max_abs_1x2_menos_1"], abs(p["p_local"] + p["p_empate"] + p["p_visitante"] - 1))
        if p.get("matriz") is not None:
            s = float(np.sum(p["matriz"])) + float(p.get("matriz_resto") or 0.0)
            a["max_abs_matriz_menos_1"] = max(a["max_abs_matriz_menos_1"], abs(s - 1))
        mk_ = {m["clave"]: m["prob"] for m in (p.get("mercados") or [])}
        for x, y in (("O25", "U25"), ("AA_SI", "AA_NO"), ("O15", "U15"), ("O35", "U35"), ("G1T_SI", "G1T_NO"), ("L_ANOTA", "PC_V"),
                     ("V_ANOTA", "PC_L")):
            if x in mk_ and y in mk_ and abs(mk_[x] + mk_[y] - 1) > 2 * TOL:
                a["pares_complementarios_malos"].append([p["id"], x, y, mk_[x] + mk_[y]])
        if {"1", "X", "2"} <= set(mk_):
            for k, v in (("1", p["p_local"]), ("X", p["p_empate"]), ("2", p["p_visitante"])):
                if abs(mk_[k] - v) > TOL:
                    a["pares_complementarios_malos"].append([p["id"], k, "p_1x2", mk_[k] - v])
    for ruta, v in caminar({k: doc[k] for k in ("pendientes", "proyeccion", "tabla", "combinada_jornada", "fuerzas")}):
        hoja = ruta.rsplit(".", 1)[-1].split("[")[0]
        if isinstance(v, float) and not math.isfinite(v):
            a["nan_o_inf"].append(ruta)
        if v is None and (hoja.startswith(("p_", "prob", "lam_", "ee", "pts", "puntos")) or hoja in ("rho", "PTS", "DG")):
            a["nulos_en_campos_numericos"].append(ruta)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and (hoja.startswith(("p_", "prob")) or hoja == "prob"):
            if not (-1e-9 <= v <= 1 + 1e-9):
                a["prob_fuera_de_0_1"].append([ruta, v])
    for k in ("nulos_en_campos_numericos", "nan_o_inf", "prob_fuera_de_0_1"):
        a[f"n_{k}"] = len(a[k])
        a[k] = a[k][:8]
    res["a_sumas"] = a

    # ---- b. tres partidos a mano
    b = []
    for p in pend[:3]:
        M = matriz(p["lam_l"], p["lam_v"], p["rho"])
        x, y = np.indices(M.shape)
        mano = {"p_local": float(M[x > y].sum()), "p_empate": float(M[x == y].sum()), "p_visitante": float(M[x < y].sum()),
                "O25": float(M[x + y >= 3].sum()), "AA_SI": float(M[(x > 0) & (y > 0)].sum())}
        i, j = np.unravel_index(np.argmax(M), M.shape)
        mk_ = {m["clave"]: m["prob"] for m in p["mercados"]}
        exp = {"p_local": p["p_local"], "p_empate": p["p_empate"], "p_visitante": p["p_visitante"], "O25": mk_.get("O25"),
               "AA_SI": mk_.get("AA_SI")}
        dif = max(abs(mano[k] - exp[k]) for k in mano if exp[k] is not None)
        dif_m = float(np.abs(np.array(p["matriz"]) - M[:7, :7]).max())
        b.append({"partido": f"{p['local']} vs {p['visitante']}", "lam_l": p["lam_l"], "lam_v": p["lam_v"], "rho": p["rho"],
                  "a_mano": {k: round(v, 4) for k, v in mano.items()}, "exportado": exp, "max_dif": dif, "max_dif_matriz": dif_m,
                  "marcador_a_mano": [int(i), int(j), round(float(M[i, j]), 4)], "marcador_exportado": p["marcador"]})
    res["b_a_mano"] = b

    # ---- c. tres combinadas por simulación
    p1_l, p1_v = mk.proporcion_1t(pron.corte)[:2]
    rng = np.random.default_rng(123)
    n = 2_000_000
    c = []
    for p, variante in zip(pend[:3], ("segura", "equilibrada", "atrevida")):
        comb = (p.get("combinadas") or {}).get(variante)
        if not comb:
            c.append({"partido": p["id"], "variante": variante, "nota": "sin combinada"})
            continue
        x, y = sortear(rng, matriz(p["lam_l"], p["lam_v"], p["rho"]), n)
        h, a_ = rng.binomial(x, p1_l), rng.binomial(y, p1_v)
        ok = np.ones(n, bool)
        marg, cubierto = [], True
        for pick in comb["picks"]:
            m = predicado(pick["clave"], x, y, h, a_)
            if m is None:
                cubierto = False
                break
            marg.append([pick["clave"], pick["prob"], round(float(m.mean()), 4)])
            ok &= m
        if not cubierto:
            c.append({"partido": p["id"], "variante": variante, "nota": f"mercado no cubierto: {pick['clave']}"})
            continue
        sim = float(ok.mean())
        ee = math.sqrt(sim * (1 - sim) / n)
        c.append({"partido": f"{p['local']} vs {p['visitante']}", "variante": variante, "picks_exportado_simulado": marg,
                  "prob_conjunta_exportada": comb["prob_conjunta"], "simulada": round(sim, 5), "ee_mc": round(ee, 5),
                  "dif": sim - comb["prob_conjunta"], "coincide": bool(abs(sim - comb["prob_conjunta"]) < 4 * ee + TOL),
                  "producto_ingenuo": comb.get("prob_ingenua")})
    res["c_combinadas"] = c
    res["c_proporcion_1t"] = [p1_l, p1_v]
    cj = doc.get("combinada_jornada") or {}
    res["c_combinada_jornada"] = {k: (v if not isinstance(v, (list, dict)) else f"<{type(v).__name__} {len(v)}>") for k, v in cj.items()}
    for nombre in ("segura", "atrevida", "combinada"):
        s = cj.get(nombre)
        if isinstance(s, dict) and "picks" in s and "prob_conjunta" in s:
            prod = float(np.prod([q["prob"] for q in s["picks"]]))
            res["c_combinada_jornada"][nombre] = {"prob_conjunta": s["prob_conjunta"], "producto_de_picks": round(prod, 4),
                                                 "partidos_distintos": len({q["id"] for q in s["picks"]}) == len(s["picks"])}

    # ---- d. tabla
    of = pd.read_csv(RAIZ / "datos" / "tabla_apertura2026.csv")
    tj = pd.DataFrame(doc["tabla"])
    cols = ["pos", "equipo", "PJ", "G", "E", "P", "GF", "GC", "DG", "PTS"]
    u = of[cols].merge(tj[cols], on="equipo", suffixes=("_csv", "_json"))
    dist = int(sum((u[f"{k}_csv"] != u[f"{k}_json"]).sum() for k in cols if k != "equipo"))
    p = pd.read_csv(RAIZ / "datos" / "partidos.csv", dtype=str, keep_default_na=False)
    r = p[(p["torneo"] == doc["meta"]["torneo"]) & (p["fase"] == "regular") & (p["estado"] == "jugado")]
    mio = {}
    for f in r.itertuples():
        gl, gv = int(f.gl), int(f.gv)
        for eq, gf, gc in ((f.local, gl, gv), (f.visitante, gv, gl)):
            m = mio.setdefault(eq, {"PJ": 0, "PTS": 0, "GF": 0, "GC": 0})
            m["PJ"] += 1; m["GF"] += gf; m["GC"] += gc; m["PTS"] += 3 if gf > gc else (1 if gf == gc else 0)
    dist2 = sum(int(mio[e][k] != v) for e, fila in tj.set_index("equipo").iterrows() for k, v in fila[["PJ", "PTS", "GF", "GC"]].items())
    res["d_tabla"] = {"equipos": int(len(u)), "celdas_distintas_vs_tabla_csv": dist, "celdas_distintas_vs_recuento_propio": int(dist2),
                      "coincide_espn_en_el_csv": int(of["coincide_espn"].sum())}

    # ---- e. proyección
    pr = doc["proyeccion"]
    camp = pd.DataFrame(pr["campeon"])
    tf = pd.DataFrame(pr["tabla_final"])
    pos = np.array(tf["posicion"].tolist())
    e = {"suma_campeon": float(camp["prob"].sum()), "suma_final": float(camp["p_final"].sum()),
         "suma_semifinal": float(camp["p_semifinal"].sum()), "suma_clasifica": float(camp["p_clasifica"].sum()),
         "monotonia_violada": int(((camp["prob"] > camp["p_final"] + TOL) | (camp["p_final"] > camp["p_semifinal"] + TOL)
                                   | (camp["p_semifinal"] > camp["p_clasifica"] + TOL)).sum()),
         "max_abs_fila_posicion_menos_1": float(np.abs(pos.sum(axis=1) - 1).max()),
         "max_abs_columna_posicion_menos_1": float(np.abs(pos.sum(axis=0) - 1).max()),
         "max_abs_p_clasifica_menos_suma_top8": float(np.abs(pos[:, :8].sum(axis=1) - tf["p_clasifica"]).max()),
         "campeon_tabla_final_vs_lista": float(np.abs(tf.set_index("equipo")["p_campeon"].reindex(camp["equipo"]).to_numpy() - camp["prob"]).max()),
         "cruces_suma_por_llave": {c["llave"]: round(sum(o["prob"] for o in c["opciones"]), 4) for c in pr["cruces_cuartos"]},
         "n_sim": pr["n_sim"], "n_muestras": pr["n_muestras"]}
    res["e_proyeccion"] = e


def revisar_desempates(res: dict):
    reglas = simulador.cargar_reglas()
    f = {"criterios_config": reglas["desempate_tabla"]}
    # orden de criterios: cada caso empata en todo lo anterior y difiere sólo en el criterio probado
    base = dict(pts=[30, 30], dg=[5, 5], gf=[20, 20], gvis=[9, 9], fair=[30, 30], coc=[1.5, 1.5], azar=[0.2, 0.1])
    casos = {"puntos": ("pts", [31, 30]), "diferencia_de_goles": ("dg", [6, 5]), "goles_a_favor": ("gf", [21, 20]),
             "goles_de_visitante": ("gvis", [10, 9]), "menos_puntos_fair_play": ("fair", [29, 30]),
             "tabla_de_cociente": ("coc", [1.6, 1.5])}
    orden_ok = {}
    nombres = list(casos)
    for i, (nombre, (k, val)) in enumerate(casos.items()):
        d = {kk: np.array(v, float) for kk, v in base.items()}
        d[k] = np.array(val, float)
        # el criterio SIGUIENTE favorece al otro equipo: si el orden de criterios fuera otro, ganaría el 1
        if i + 1 < len(nombres):
            k2, v2 = casos[nombres[i + 1]]
            d[k2] = np.array(v2[::-1], float)
        orden_ok[nombre] = bool(simulador.ordenar(**d)[0] == 0)
    d = {kk: np.array(v, float) for kk, v in base.items()}
    orden_ok["sorteo"] = bool(simulador.ordenar(**d)[0] == 1)            # azar menor primero
    f["orden_de_criterios_respetado"] = orden_ok
    f["orden_config_esperado"] = reglas["desempate_tabla"][:7] == ["puntos", "diferencia_de_goles", "goles_a_favor",
                                                                  "goles_de_visitante_con_el_mismo_numero_de_visitas",
                                                                  "menos_puntos_fair_play", "tabla_de_cociente", "sorteo"]
    # series: global empatado
    lig = reglas["liguilla"]
    M11, M00 = simulador.matriz_fija(1, 1), simulador.matriz_fija(0, 0)
    s = simulador.prob_serie(M11, M00, False, True, simulador._regla_de(reglas["torneo"], "cuartos"))
    f["cuartos_global_empatado_avanza_mejor"] = s["p_mejor"]
    s = simulador.prob_serie(simulador.matriz_fija(2, 1), simulador.matriz_fija(1, 0), False, True,
                             simulador._regla_de(reglas["torneo"], "semifinal"))       # peor gana 2-1 la ida, mejor 1-0 la vuelta
    f["semifinal_2a2_con_gol_de_visita_del_mejor_avanza_mejor"] = s["p_mejor"]
    s = simulador.prob_serie(simulador.matriz_fija(1, 2), simulador.matriz_fija(0, 1), False, True,
                             simulador._regla_de(reglas["torneo"], "cuartos"))         # mejor gana 2-1 fuera, peor gana 1-0 fuera
    f["cuartos_2a2_con_mas_goles_de_visita_del_peor_avanza_mejor"] = s["p_mejor"]
    s = simulador.prob_serie(M11, M00, False, True, simulador._regla_de(reglas["torneo"], "final"), lam_extra=(1e-9, 1e-9))
    f["final_empatada_sin_goles_en_extra_es_moneda"] = s["p_mejor"]
    s = simulador.prob_serie(M11, M00, False, True, "final", lam_extra=(0.5, 0.4))
    E = matriz(0.5, 0.4, 0.0)
    x, y = np.indices(E.shape)
    f["final_empatada_con_extra_formula"] = [s["p_mejor"], float(E[x > y].sum() + 0.5 * E[x == y].sum())]
    f["reglas_config"] = {k: lig[k] for k in ("cruces_cuartos", "gol_visitante", "resiembra_semifinal", "empate_global_cuartos_semis",
                                              "final_empate")}
    f["constantes_codigo"] = {"FRACCION_EXTRA": simulador.FRACCION_EXTRA, "P_PENALES": simulador.P_PENALES,
                              "VISITAS_CUENTAN": simulador.VISITAS_CUENTAN, "TORNEO_COCIENTE": simulador.TORNEO_COCIENTE,
                              "clasifican": reglas["clasifican_directo"]}
    res["f_desempates"] = f


def simulador_propio(doc: dict, pron, n: int = 60000, semilla: int = 99) -> pd.Series:
    """Resto del torneo con reglas de config/torneo.json escritas aquí; lambdas puntuales. Devuelve P(campeón)."""
    eq = list(pron.equipos)
    ix = {e: i for i, e in enumerate(eq)}
    ne = len(eq)
    p = pd.read_csv(RAIZ / "datos" / "partidos.csv", dtype=str, keep_default_na=False)
    tor = doc["meta"]["torneo"]
    reg = p[(p["torneo"] == tor) & (p["fase"] == "regular")].sort_values(["fecha_utc", "id"])
    pts, gf, gc, gvis, nvis = (np.zeros(ne) for _ in range(5))
    for f in reg[reg["estado"] == "jugado"].itertuples():
        a, b, gl, gv = ix[f.local], ix[f.visitante], int(f.gl), int(f.gv)
        pts[a] += 3 * (gl > gv) + (gl == gv); pts[b] += 3 * (gv > gl) + (gl == gv)
        gf[a] += gl; gc[a] += gv; gf[b] += gv; gc[b] += gl
    # goles de visitante: sólo las primeras 8 visitas de cada equipo, por orden cronológico del calendario
    vivos = reg[reg["estado"].isin(["jugado", "programado", "pospuesto", "en_juego"])]
    cuenta_vis = {}
    for f in vivos.itertuples():
        b = ix[f.visitante]
        nvis[b] += 1
        cuenta_vis[f.id] = nvis[b] <= 8
        if f.estado == "jugado" and cuenta_vis[f.id]:
            gvis[b] += int(f.gv)
    # cociente: puntos / partidos de fase regular desde el Apertura 2024
    def ord_t(t):
        tipo, an = t.rsplit(" ", 1)
        return 2 * int(an) + (0 if tipo.startswith("Clausura") else 1)
    cq = p[(p["fase"] == "regular") & (p["estado"] == "jugado") & (p["torneo"].map(ord_t) >= ord_t("Apertura 2024"))
           & (p["torneo"].map(ord_t) <= ord_t(tor))]
    cpts, cpj = np.zeros(ne), np.zeros(ne)
    for f in cq.itertuples():
        gl, gv = int(f.gl), int(f.gv)
        for e, x, y in ((f.local, gl, gv), (f.visitante, gv, gl)):
            if e in ix:
                cpts[ix[e]] += 3 * (x > y) + (x == y); cpj[ix[e]] += 1
    fair = np.array([next(t["fair_play"] for t in doc["tabla"] if t["equipo"] == e) for e in eq], float)   # insumo tomado del JSON
    rng = np.random.default_rng(semilla)
    P, GF, GC, GV = (np.repeat(v[None], n, axis=0) for v in (pts, gf, gc, gvis))
    CP, CJ = np.repeat(cpts[None], n, axis=0), cpj.copy()
    for d in doc["pendientes"]:
        if d["fase"] != "regular":
            continue
        a, b = ix[d["local"]], ix[d["visitante"]]
        x, y = sortear(rng, matriz(d["lam_l"], d["lam_v"], d["rho"]), n)
        pa, pb = 3 * (x > y) + (x == y), 3 * (y > x) + (x == y)
        P[:, a] += pa; P[:, b] += pb; CP[:, a] += pa; CP[:, b] += pb; CJ[a] += 1; CJ[b] += 1
        GF[:, a] += x; GC[:, a] += y; GF[:, b] += y; GC[:, b] += x
        if cuenta_vis.get(str(d["id"]), False):
            GV[:, b] += y
    coc = CP / np.maximum(CJ, 1)[None]
    orden = np.lexsort(np.stack([rng.random((n, ne)), -coc, np.repeat(fair[None], n, axis=0), -GV, -GF, -(GF - GC), -P]), axis=-1)
    ml = pron.malla(n=1, fase="liguilla")
    LL, LV, rho = ml["lam_l"][0], ml["lam_v"][0], float(ml["rho"])
    lugar = np.empty_like(orden)
    lugar[np.arange(n)[:, None], orden] = np.arange(ne)[None]

    def serie(mejor, peor, final=False):
        gm, gp = np.zeros(n, int), np.zeros(n, int)
        for loc, vis, mejor_local in ((peor, mejor, False), (mejor, peor, True)):        # ida en casa del peor
            gl, gv = np.zeros(n, int), np.zeros(n, int)
            llave = loc * ne + vis
            for k in np.unique(llave):
                m = llave == k
                gl[m], gv[m] = sortear(rng, matriz(LL[k // ne, k % ne], LV[k // ne, k % ne], rho), int(m.sum()))
            gm += gl if mejor_local else gv
            gp += gv if mejor_local else gl
        if not final:
            return gm >= gp                                                             # global empatado: avanza el mejor
        em, ep = rng.poisson(LL[mejor, peor] / 3.0), rng.poisson(LV[mejor, peor] / 3.0)  # tiempos extra en casa del mejor
        return (gm > gp) | ((gm == gp) & ((em > ep) | ((em == ep) & (rng.random(n) < 0.5))))

    vivos4 = []
    for s1, s2 in ((1, 8), (2, 7), (3, 6), (4, 5)):
        m_, p_ = orden[:, s1 - 1], orden[:, s2 - 1]
        g = serie(m_, p_)
        vivos4.append(np.where(g, m_, p_))
    V4 = np.stack(vivos4, axis=1)
    V4 = np.take_along_axis(V4, np.argsort(np.take_along_axis(lugar, V4, axis=1), axis=1), axis=1)   # resiembra por lugar
    f1 = np.where(serie(V4[:, 0], V4[:, 3]), V4[:, 0], V4[:, 3])
    f2 = np.where(serie(V4[:, 1], V4[:, 2]), V4[:, 1], V4[:, 2])
    l1, l2 = lugar[np.arange(n), f1], lugar[np.arange(n), f2]
    mejor, peor = np.where(l1 < l2, f1, f2), np.where(l1 < l2, f2, f1)
    camp = np.where(serie(mejor, peor, final=True), mejor, peor)
    return pd.Series(np.bincount(camp, minlength=ne) / n, index=eq)


def revisar_simulador(doc: dict, pron, res: dict):
    n = 60000
    mio = simulador_propio(doc, pron, n)
    suyo = simulador.simular(pron, n_sim=n, n_muestras=0, semilla=5)
    por = pd.DataFrame(suyo["por_equipo"]).set_index("equipo")
    col = "p_campeon" if "p_campeon" in por.columns else [c for c in por.columns if "campe" in c][0]
    exp = pd.DataFrame(doc["proyeccion"]["campeon"]).set_index("equipo")["prob"]
    t = pd.DataFrame({"propio": mio, "proyecto_puntual": por[col].reindex(mio.index), "exportado_con_incertidumbre": exp.reindex(mio.index)})
    ee = np.sqrt((t["propio"] * (1 - t["propio"]) + t["proyecto_puntual"] * (1 - t["proyecto_puntual"])) / n)
    z = ((t["propio"] - t["proyecto_puntual"]) / ee.replace(0, np.nan)).abs()
    res["g_simulador"] = {"n": n, "max_abs_dif_propio_vs_proyecto": float((t["propio"] - t["proyecto_puntual"]).abs().max()),
                          "max_z": float(z.max()), "suma_propio": float(mio.sum()),
                          "max_abs_dif_puntual_vs_exportado": float((t["proyecto_puntual"] - t["exportado_con_incertidumbre"]).abs().max()),
                          "tabla": t[t["propio"] > 0.002].sort_values("propio", ascending=False).round(4).reset_index().to_dict("records")}


def revisar_robustez(pron, res: dict):
    h = {}
    df = datos.cargar()
    pend = datos.pendientes(df)
    base = {int(d["id"]): d for d in pron.partidos(pend)}
    # 1. equipo sin historial y sede desconocida
    try:
        d = pron.partidos(pd.DataFrame([{"id": 999000001, "fecha_utc": "2026-11-21T01:00Z", "local": "Equipo Fantasma", "visitante": "América"},
                                        {"id": 999000002, "fecha_utc": "2026-11-21T03:00Z", "local": "Toluca", "visitante": "Equipo Fantasma"}]))
        h["equipo_sin_historial"] = [{"lam_l": x["lam_l"], "lam_v": x["lam_v"],
                                      "finito": bool(np.isfinite([x["lam_l"], x["lam_v"]]).all())} for x in d]
    except Exception as e:                                               # noqa: BLE001
        h["equipo_sin_historial"] = f"ERROR {type(e).__name__}: {e}"
    # 2. un equipo sin estadísticas ni alineaciones en sus últimos 25 partidos (datos nuevos incompletos)
    original_p, original_a = V.leer_partidos, V.leer_alineaciones
    try:
        eq = str(pend["visitante"].iloc[-1])
        pt = original_p()
        ult = pt[((pt["local"] == eq) | (pt["visitante"] == eq)) & (pt["estado"] == "jugado")].sort_values("fecha_utc").tail(25)["id"]
        pt = pt.copy()
        m = pt["id"].isin(ult)
        for c in pt.columns:
            if c.startswith(("tiros", "corners", "faltas", "posesion", "amarillas", "rojas")):
                pt.loc[m, c] = ""
        pt.loc[m, "tiene_stats"] = "0"
        al = original_a()
        al = al[~al["partido_id"].isin(ult)]
        V.leer_partidos = lambda ruta=None: pt.copy()
        V.leer_alineaciones = lambda ruta=None: al.copy()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            p2 = Pronosticador(corte=pron.corte)
            d2 = {int(d["id"]): d for d in p2.partidos(pend)}
        fila = pend[pend["visitante"] == eq].iloc[-1]
        i = int(fila["id"])
        h["equipo_sin_estadisticas_recientes"] = {
            "equipo": eq, "partido": f"{fila['local']} vs {fila['visitante']}", "todas_finitas": bool(all(np.isfinite([d["lam_l"], d["lam_v"]]).all() for d in d2.values())),
            "lam_con_datos": [base[i]["lam_l"], base[i]["lam_v"]], "lam_sin_datos": [d2[i]["lam_l"], d2[i]["lam_v"]],
            "avisos": [str(x.message)[:200] for x in w][:3]}
    except Exception as e:                                               # noqa: BLE001
        h["equipo_sin_estadisticas_recientes"] = f"ERROR {type(e).__name__}: {e}"
    finally:
        V.leer_partidos, V.leer_alineaciones = original_p, original_a
    # 3. caché de variables desactualizada (le faltan los partidos desde marzo de 2026) y caché ausente
    rutas = dict(C.RUTA_VARIABLES)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            vieja = V.cargar("bloque")
            vieja = vieja[vieja["fecha_utc"] < "2026-03-01"]
            ruta = Path(tmp) / "variables_bloque.parquet"
            vieja.to_parquet(ruta, index=False)
            C.RUTA_VARIABLES["bloque"] = ruta
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                p3 = Pronosticador(corte=pron.corte)
                d3 = {int(d["id"]): d for d in p3.partidos(pend)}
            dif = max(max(abs(d3[i]["lam_l"] - base[i]["lam_l"]), abs(d3[i]["lam_v"] - base[i]["lam_v"])) for i in base)
            h["cache_desactualizada"] = {"filas_faltantes": int(len(V.cargar("bloque")) - len(vieja)), "avisa": bool(len(w) > 0),
                                         "avisos": [str(x.message)[:300] for x in w][:2], "max_dif_lambda": float(dif),
                                         "atributo_avisos": list(getattr(p3, "avisos", []))[:2]}
            # filas presentes pero firmas viejas (un partido de febrero de 2026 "cambió" después de generar la caché)
            dir_real = V.DIR_CACHE
            try:
                import shutil
                for r in V._rutas("bloque"):
                    shutil.copy(r, Path(tmp) / r.name)
                V.DIR_CACHE = Path(tmp)
                C.RUTA_VARIABLES["bloque"] = V._rutas("bloque")[0]
                fir = pd.read_parquet(V._rutas("bloque")[1])
                k = fir.index[(fir["t"] > pd.Timestamp("2026-02-01", tz="UTC").timestamp()) & (fir["estado"] == "jugado")][0]
                fir.loc[k, "firma"] = "0"
                fir.to_parquet(V._rutas("bloque")[1], index=False)
                C._tablas_variables.clear()
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")
                    p4 = Pronosticador(corte=pron.corte)
                h["cache_con_firmas_viejas"] = {"avisa": bool(len(w) > 0), "avisos": [str(x.message)[:300] for x in w][:1],
                                                "atributo_avisos": len(getattr(p4, "avisos", []))}
            finally:
                V.DIR_CACHE = dir_real
            h["cache_al_dia_no_avisa"] = len(getattr(pron, "avisos", [])) == 0
            C.RUTA_VARIABLES["bloque"] = Path(tmp) / "no_existe.parquet"
            try:
                Pronosticador(corte=pron.corte)
                h["cache_ausente"] = "NO FALLA (mal: usaría coeficientes sin datos)"
            except Exception as e:                                       # noqa: BLE001
                h["cache_ausente"] = f"falla con {type(e).__name__}: {str(e)[:160]}"
    finally:
        C.RUTA_VARIABLES.update(rutas)
        C._tablas_variables.clear()
    res["h_robustez"] = h


def revisar_sensibilidad_modelo(res: dict, n_sim: int = 20000):
    """P(campeón) con cada modelo que la validación no distingue: la diferencia entre ellos es incertidumbre real."""
    out = {}
    for m in ("ajuste", "ensamble", "dc", "elo"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = simulador.simular(Pronosticador(modelo=m), n_sim=n_sim)
        out[m] = pd.DataFrame(s["por_equipo"]).set_index("equipo")["p_campeon"]
    t = pd.DataFrame(out).sort_values("ajuste", ascending=False)
    t["rango"] = t.max(axis=1) - t.min(axis=1)
    res["i_campeon_por_modelo"] = {"n_sim": n_sim, "max_rango": float(t["rango"].max()),
                                   "tabla": t.head(8).round(4).reset_index().to_dict("records")}


def main():
    DIR_SAL.mkdir(exist_ok=True)
    res: dict = {}
    pron = Pronosticador()
    with tempfile.TemporaryDirectory() as tmp:
        doc = exportar.construir(sellar=False, ruta_desempeno=Path(tmp) / "desempeno.json", pron=pron)
        res["validar_del_proyecto"] = exportar.validar(doc)[:10]
        ruta, peso = exportar.escribir(doc, Path(tmp) / "auditoria_actual.json", historial=False)
        doc = json.loads(Path(ruta).read_text(encoding="utf-8"))
        res["peso_kb"] = round(peso / 1024, 1)
    res["meta"] = {k: doc["meta"][k] for k in ("corte_utc", "torneo")} | {"modelo": doc["meta"]["modelo"]["nombre"]}
    for nombre, fn in (("documento", lambda: revisar_documento(doc, pron, res)), ("desempates", lambda: revisar_desempates(res)),
                       ("simulador", lambda: revisar_simulador(doc, pron, res)), ("robustez", lambda: revisar_robustez(pron, res)),
                       ("sensibilidad", lambda: revisar_sensibilidad_modelo(res))):
        try:
            fn()
        except Exception as e:                                           # noqa: BLE001
            import traceback
            res[f"ERROR_{nombre}"] = traceback.format_exc()[-1500:]
        (DIR_SAL / "produccion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str)[:9000])


if __name__ == "__main__":
    main()
