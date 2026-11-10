# -*- coding: utf-8 -*-
"""
Pruebas del motor de mercados, la combinada, el contexto y el pronosticador provisional.

    cd /home/user/SA/ligamx && python3 -m pytest produccion/pruebas/test_mercados.py -q
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # .../ligamx

from modelo import arnes, datos  # noqa: E402
from produccion import combinada as cb  # noqa: E402
from produccion import mercados as mk  # noqa: E402
from produccion.contexto import Contexto  # noqa: E402
from produccion.pronosticador_provisional import Pronosticador  # noqa: E402

CASOS = [(1.83, 0.71, -0.08, 0.44, 0.45), (1.2, 1.5, 0.0, 0.456, 0.451), (3.0, 2.5, -0.05, 0.40, 0.48),
         (0.6, 0.5, 0.10, 0.45, 0.45), (1.35, 1.30, -0.12, 0.47, 0.43)]
FECHA = "2026-11-10"


def _q(lam_l, lam_v, rho, pl, pv):
    return mk.celdas(arnes.matriz_marcadores(lam_l, lam_v, rho), pl, pv)


# Definición INDEPENDIENTE de cada mercado combinable (x, y finales; h, a del primer tiempo), escrita
# aparte de las máscaras del catálogo: sirve para comprobarlas y para la simulación Monte Carlo.
def _s(v):
    return np.sign(v)


PRED = {
    "1": lambda x, y, h, a: x > y, "X": lambda x, y, h, a: x == y, "2": lambda x, y, h, a: x < y,
    "1X": lambda x, y, h, a: x >= y, "X2": lambda x, y, h, a: x <= y, "12": lambda x, y, h, a: x != y,
    "H_L-1.5": lambda x, y, h, a: x - y > 1.5, "H_V+1.5": lambda x, y, h, a: y + 1.5 > x,
    "H_V-1.5": lambda x, y, h, a: y - x > 1.5, "H_L+1.5": lambda x, y, h, a: x + 1.5 > y,
    "O15": lambda x, y, h, a: x + y > 1.5, "U15": lambda x, y, h, a: x + y < 1.5,
    "O25": lambda x, y, h, a: x + y > 2.5, "U25": lambda x, y, h, a: x + y < 2.5,
    "O35": lambda x, y, h, a: x + y > 3.5, "U35": lambda x, y, h, a: x + y < 3.5,
    "AA_SI": lambda x, y, h, a: np.minimum(x, y) > 0, "AA_NO": lambda x, y, h, a: np.minimum(x, y) == 0,
    "L_ANOTA": lambda x, y, h, a: x > 0, "L_2MAS": lambda x, y, h, a: x > 1, "L_U15": lambda x, y, h, a: x < 1.5,
    "PC_V": lambda x, y, h, a: x == 0,
    "V_ANOTA": lambda x, y, h, a: y > 0, "V_2MAS": lambda x, y, h, a: y > 1, "V_U15": lambda x, y, h, a: y < 1.5,
    "PC_L": lambda x, y, h, a: y == 0,
    "D_1": lambda x, y, h, a: h > a, "D_X": lambda x, y, h, a: h == a, "D_2": lambda x, y, h, a: h < a,
    "D_1X": lambda x, y, h, a: h >= a, "D_X2": lambda x, y, h, a: h <= a, "D_12": lambda x, y, h, a: h != a,
    "G1T_SI": lambda x, y, h, a: h + a > 0, "G1T_NO": lambda x, y, h, a: h + a == 0,
    "O15_1T": lambda x, y, h, a: h + a > 1.5, "U15_1T": lambda x, y, h, a: h + a < 1.5,
    "G2T_SI": lambda x, y, h, a: (x - h) + (y - a) > 0, "G2T_NO": lambda x, y, h, a: (x - h) + (y - a) == 0,
    "MAS_1T": lambda x, y, h, a: h + a > (x - h) + (y - a), "MAS_2T": lambda x, y, h, a: h + a < (x - h) + (y - a),
    "MIT_IGUAL": lambda x, y, h, a: h + a == (x - h) + (y - a),
    "GM_L": lambda x, y, h, a: (h > a) | ((x - h) > (y - a)), "GM_V": lambda x, y, h, a: (h < a) | ((x - h) < (y - a)),
}
for _a, _ca in ((1, "1"), (0, "X"), (-1, "2")):
    for _b, _cb in ((1, "1"), (0, "X"), (-1, "2")):
        PRED[f"DF_{_ca}/{_cb}"] = (lambda x, y, h, a, _a=_a, _b=_b: (_s(h - a) == _a) & (_s(x - y) == _b))


# ==================================================================================================
# 1. Conjunta por mitades
# ==================================================================================================
@pytest.mark.parametrize("caso", CASOS)
def test_J_suma_uno_y_marginal_coincide_con_M(caso):
    lam_l, lam_v, rho, pl, pv = caso
    J = mk.conjunta_mitades(lam_l, lam_v, rho, pl, pv)
    assert J.shape == (11, 11, 11, 11) and (J >= 0).all()
    assert abs(J.sum() - 1.0) < 1e-9
    M = arnes.matriz_marcadores(lam_l, lam_v, rho)
    Mj = np.zeros((11, 11))                               # marginal de tiempo completo, por fuerza bruta
    for h1, a1, h2, a2 in np.argwhere(J > 0):
        Mj[h1 + h2, a1 + a2] += J[h1, a1, h2, a2]
    assert np.abs(Mj - M).max() < 1e-4
    assert np.abs(mk.marginal_final(mk.celdas_de_tensor(J)) - M).max() < 1e-12
    # marginales por mitad: con rho = 0 el primer tiempo del local es (casi) Poisson(lam_l * pl)
    if rho == 0.0:
        from scipy.stats import poisson
        assert np.abs(J.sum(axis=(1, 2, 3))[:6] - poisson.pmf(np.arange(6), lam_l * pl)).max() < 1e-4


def test_celdas_vectorizado_igual_que_uno_por_uno():
    a = np.array(CASOS)
    M = arnes.matrices_marcadores(a[:, 0], a[:, 1], a[:, 2])
    Q = mk.celdas(M, a[:, 3], a[:, 4])
    assert Q.shape == (len(CASOS), mk.N_CELDAS)
    for i, c in enumerate(CASOS):
        assert np.allclose(Q[i], _q(*c), atol=1e-15)


# ==================================================================================================
# 2. Catálogo
# ==================================================================================================
def test_mascaras_coinciden_con_definicion_independiente():
    cat = {m.clave: m for m in mk.catalogo() if m.combinable}
    assert set(cat) == set(PRED)
    for clave, f in PRED.items():
        assert np.array_equal(cat[clave].mascara, np.asarray(f(mk.X, mk.Y, mk.H1, mk.A1), bool)), clave


@pytest.mark.parametrize("caso", CASOS)
def test_complementarios_suman_uno(caso):
    r = mk.mercados_partido(*caso)
    p = {m["clave"]: m["prob"] for m in r["mercados"]}
    pares = [("O15", "U15"), ("O25", "U25"), ("O35", "U35"), ("AA_SI", "AA_NO"), ("G1T_SI", "G1T_NO"),
             ("O15_1T", "U15_1T"), ("G2T_SI", "G2T_NO"), ("H_L-1.5", "H_V+1.5"), ("H_V-1.5", "H_L+1.5"),
             ("L_ANOTA", "PC_V"), ("V_ANOTA", "PC_L"), ("L_2MAS", "L_U15"), ("V_2MAS", "V_U15"),
             ("1X", "2"), ("X2", "1"), ("12", "X"), ("D_1X", "D_2"), ("D_X2", "D_1"), ("D_12", "D_X"),
             ("SE_1", "SE_2"), ("HA_L-1", "HA_V+1")]
    for a, b in pares:
        assert abs(p[a] + p[b] - 1.0) < 1e-9, (a, b)
    for trio in (("1", "X", "2"), ("D_1", "D_X", "D_2"), ("MAS_1T", "MAS_2T", "MIT_IGUAL")):
        assert abs(sum(p[c] for c in trio) - 1.0) < 1e-9, trio
    assert abs(sum(v for k, v in p.items() if k.startswith("DF_")) - 1.0) < 1e-9
    for res in ("1", "X", "2"):                           # descanso/final suma al resultado final
        assert abs(sum(p[f"DF_{d}/{res}"] for d in ("1", "X", "2")) - p[res]) < 1e-9


@pytest.mark.parametrize("caso", CASOS)
def test_coherente_con_arnes(caso):
    r = mk.mercados_partido(*caso)
    p = {m["clave"]: m["prob"] for m in r["mercados"]}
    M = r["M"]
    assert np.allclose([p["1"], p["X"], p["2"]], arnes.p1x2(M), atol=1e-12)
    for linea, c in ((1.5, "O15"), (2.5, "O25"), (3.5, "O35")):
        assert abs(p[c] - arnes.p_over(M, linea)) < 1e-12
    assert abs(p["AA_SI"] - arnes.p_ambos_anotan(M)) < 1e-12
    top = arnes.top_marcadores(M, 5)
    assert [(m["gl"], m["gv"]) for m in r["marcadores"]] == [(x, y) for x, y, _ in top]
    assert len(r["marcadores"]) == 5 and all(m["familia"] == "marcador" for m in r["marcadores"])
    assert abs(r["marcadores"][0]["prob"] - r["q"][mk.mascara_marcador(top[0][0], top[0][1])].sum()) < 1e-12
    # sin empate: P(gana | no empata)
    assert abs(p["SE_1"] - p["1"] / (1 - p["X"])) < 1e-12


def test_proporcion_1t_solo_usa_el_pasado():
    df = datos.cargar()
    corte = pd.Timestamp("2022-07-01", tz="UTC")
    pl, pv, n = mk.proporcion_1t(corte)
    j = df[df["evaluable"] & (df["tiene_eventos"] == 1) & (df["fecha_utc"] < corte) &
           (df["fecha_utc"] >= corte - pd.Timedelta(days=mk.ANIOS_P1 * 365.25))]
    g = datos.tabla("goles").merge(j[["id", "local", "visitante"]], left_on="partido_id", right_on="id")
    g = g[g["periodo"].isin([1, 2])]
    loc = g[g["equipo"] == g["local"]]
    vis = g[g["equipo"] == g["visitante"]]
    assert n == len(j)
    assert abs(pl - (loc["periodo"] == 1).mean()) < 1e-12 and abs(pv - (vis["periodo"] == 1).mean()) < 1e-12
    assert 0.35 < pl < 0.55 and 0.35 < pv < 0.55


# ==================================================================================================
# 3. Combinada del partido
# ==================================================================================================
def _simular(lam_l, lam_v, rho, pl, pv, n, semilla):
    """n partidos: marcador final de M (así entra la corrección Dixon-Coles) y goles del 1T por adelgazamiento."""
    rng = np.random.default_rng(semilla)
    M = arnes.matriz_marcadores(lam_l, lam_v, rho)
    k = rng.choice(121, size=n, p=M.ravel() / M.sum())
    x, y = k // 11, k % 11
    return x, y, rng.binomial(x, pl), rng.binomial(y, pv)


@pytest.mark.parametrize("caso,semilla", [(CASOS[0], 11), (CASOS[1], 12), (CASOS[4], 13)])
def test_conjunta_coincide_con_monte_carlo(caso, semilla):
    n = 400_000
    x, y, h, a = _simular(*caso, n, semilla)
    q = _q(*caso)
    for variante in cb.BANDAS:
        c = cb.combinada_partido(q, variante)
        assert c is not None and len(c["picks"]) == 4
        gana = np.ones(n, bool)
        for pk in c["picks"]:
            ok = np.asarray(PRED[pk["clave"]](x, y, h, a), bool)
            ee1 = np.sqrt(pk["prob"] * (1 - pk["prob"]) / n)
            assert abs(ok.mean() - pk["prob"]) <= 3 * ee1 + 1e-9, (variante, pk["clave"])      # marginal
            gana &= ok
        p = c["prob_conjunta"]
        ee = np.sqrt(p * (1 - p) / n)
        assert abs(gana.mean() - p) <= 3 * ee, (variante, gana.mean(), p, ee)
        assert abs(c["momio_justo"] - 1 / p) < 1e-9


def test_conjunta_con_mitades_poisson_independientes():
    """Con rho = 0: simulación directa de cuatro Poisson (una por equipo y mitad), sin pasar por M."""
    lam_l, lam_v, rho, pl, pv = CASOS[1]
    n = 400_000
    rng = np.random.default_rng(21)
    h, a = rng.poisson(lam_l * pl, n), rng.poisson(lam_v * pv, n)
    x, y = h + rng.poisson(lam_l * (1 - pl), n), a + rng.poisson(lam_v * (1 - pv), n)
    q = _q(lam_l, lam_v, rho, pl, pv)
    for variante in cb.BANDAS:
        c = cb.combinada_partido(q, variante)
        gana = np.ones(n, bool)
        for pk in c["picks"]:
            gana &= np.asarray(PRED[pk["clave"]](x, y, h, a), bool)
        p = c["prob_conjunta"]
        assert abs(gana.mean() - p) <= 3 * np.sqrt(p * (1 - p) / n) + 1e-4


def _lambdas_varias(n=40, semilla=5):
    rng = np.random.default_rng(semilla)
    return [(float(l), float(v), float(r), 0.456, 0.451) for l, v, r in
            zip(rng.uniform(0.6, 2.8, n), rng.uniform(0.5, 2.2, n), rng.uniform(-0.12, 0.05, n))]


def test_combinada_cumple_las_reglas():
    cat = {m.clave: m for m in mk.catalogo()}
    for caso in _lambdas_varias() + CASOS:
        q = _q(*caso)
        for variante, (lo, hi) in cb.BANDAS.items():
            c = cb.combinada_partido(q, variante)
            assert c is not None, (caso, variante)
            claves = [p["clave"] for p in c["picks"]]
            assert len(set(claves)) == 4
            assert len({cat[k].familia for k in claves}) == 4                     # familias distintas
            lo_, hi_ = c["banda"]
            if not c["banda_ampliada"]:
                assert (lo_, hi_) == (lo, hi)
            for p in c["picks"]:
                assert cat[p["clave"]].combinable
                assert abs(p["prob"] - q[cat[p["clave"]].mascara].sum()) < 1e-12
                assert lo_ - 1e-12 <= p["prob"] <= hi_ + 1e-12
            for a, b in itertools.combinations(claves, 2):
                pa, pb = q[cat[a].mascara].sum(), q[cat[b].mascara].sum()
                pab = q[cat[a].mascara & cat[b].mascara].sum()
                assert pab > 1e-12, (a, b, "se excluyen")
                assert abs(pab - pa) > 1e-9 and abs(pab - pb) > 1e-9, (a, b, "uno implica al otro")
                assert pab / pa <= cb.MAX_CONDICIONAL + 1e-12 and pab / pb <= cb.MAX_CONDICIONAL + 1e-12
                assert cb.relacion(a, b) == "libre"
            todos = np.ones(mk.N_CELDAS, bool)
            for k in claves:
                todos &= cat[k].mascara
            p4 = q[todos].sum()
            assert abs(p4 - c["prob_conjunta"]) < 1e-12 and abs(p4 - cb.prob_conjunta(q, claves)) < 1e-12
            for fuera in claves:                                                  # ninguno decidido por los otros tres
                otros = np.ones(mk.N_CELDAS, bool)
                for k in claves:
                    if k != fuera:
                        otros &= cat[k].mascara
                assert p4 / q[otros].sum() <= cb.MAX_CONDICIONAL + 1e-12, (claves, fuera)
            ingenua = float(np.prod([p["prob"] for p in c["picks"]]))
            assert abs(c["prob_ingenua"] - ingenua) < 1e-12 and abs(c["correlacion"] - p4 / ingenua) < 1e-9


def test_relaciones_logicas_conocidas():
    assert cb.relacion("1", "1X") == "implica" and cb.relacion("AA_SI", "L_ANOTA") == "implica"
    assert cb.relacion("DF_1/1", "D_1") == "implica" and cb.relacion("L_2MAS", "O15") == "implica"
    assert cb.relacion("1", "2") == "excluye" and cb.relacion("O25", "U15") == "excluye"
    assert cb.relacion("G1T_NO", "D_1") == "excluye" and cb.relacion("L_ANOTA", "PC_V") == "excluye"
    assert cb.relacion("1X", "12") == "misma_familia" and cb.relacion("1", "O25") == "libre"


@pytest.mark.parametrize("caso", [CASOS[0], CASOS[4]])
def test_busqueda_es_exacta_contra_fuerza_bruta(caso):
    """La búsqueda vectorizada encuentra el mismo óptimo que recorrer todas las cuartetas una por una."""
    q = _q(*caso)
    cat = [m for m in mk.catalogo() if m.combinable]
    for variante, (lo, hi) in cb.BANDAS.items():
        c = cb.combinada_partido(q, variante)
        assert not c["banda_ampliada"]
        cand = [m for m in cat if lo <= q[m.mascara].sum() <= hi]
        pr = {m.clave: q[m.mascara].sum() for m in cand}
        mejor, n_validas = -1.0, 0
        for cuatro in itertools.combinations(cand, 4):
            if len({m.familia for m in cuatro}) < 4:
                continue
            ok = True
            for a, b in itertools.combinations(cuatro, 2):
                pab = q[a.mascara & b.mascara].sum()
                if pab <= 0 or pab > cb.MAX_CONDICIONAL * min(pr[a.clave], pr[b.clave]) \
                        or (a.mascara & b.mascara).sum() in (a.mascara.sum(), b.mascara.sum()):
                    ok = False
                    break
            if not ok:
                continue
            m4 = cuatro[0].mascara & cuatro[1].mascara & cuatro[2].mascara & cuatro[3].mascara
            p4 = q[m4].sum()
            p3 = min(q[np.logical_and.reduce([m.mascara for m in cuatro if m is not f])].sum() for f in cuatro)
            if p4 > cb.MAX_CONDICIONAL * p3:
                continue
            n_validas += 1
            punt = p4 if variante != "equilibrada" else \
                p4 * min(1.0 / np.prod([pr[m.clave] for m in cuatro]), cb.TOPE_MOMIO_INGENUO)
            mejor = max(mejor, punt)
        mio = c["prob_conjunta"] if variante != "equilibrada" else \
            c["prob_conjunta"] * min(1.0 / c["prob_ingenua"], cb.TOPE_MOMIO_INGENUO)
        assert n_validas == c["n_evaluadas"]
        assert abs(mio - mejor) < 1e-12


def test_combinada_rapida():
    q = _q(*CASOS[1])
    cb.combinada_partido(q, "segura")                     # calienta las cachés
    t0 = time.perf_counter()
    for v in cb.BANDAS:
        cb.combinada_partido(q, v)
    assert time.perf_counter() - t0 < 2.0


def test_combinada_jornada():
    casos = _lambdas_varias(9, semilla=9)
    partidos = [{"id": i, "local": f"L{i}", "visitante": f"V{i}", "q": _q(*c)} for i, c in enumerate(casos)]
    j = cb.combinada_jornada(partidos)
    ids = [p["id"] for p in j["candidatos"]]
    assert len(ids) == len(set(ids)) and set(ids) | set(j["sin_pick"]) == set(range(9))
    assert all(cb.BANDA_JORNADA[0] <= p["prob"] <= cb.BANDA_JORNADA[1] for p in j["candidatos"])
    for v in ("segura", "equilibrada", "atrevida"):
        d = j[v]
        if d["n"]:
            assert abs(d["prob_conjunta"] - np.prod([p["prob"] for p in d["picks"]])) < 1e-12
    assert j["segura"]["n"] <= j["atrevida"]["n"]
    if j["segura"]["n"]:
        assert j["segura"]["prob_conjunta"] >= cb.PISOS_JORNADA["segura"]


# ==================================================================================================
# 4. Contexto: nada posterior a la fecha
# ==================================================================================================
@pytest.fixture(scope="module")
def ctx_real():
    return Contexto(FECHA)


def _fechas(o):
    """Todas las cadenas AAAA-MM-DD bajo claves 'fecha', 'previo' o 'desde' de una estructura anidada."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("fecha", "desde") and isinstance(v, str):
                yield k, v
            else:
                yield from _fechas(v)
    elif isinstance(o, list):
        for v in o:
            yield from _fechas(v)


def test_contexto_no_usa_partidos_posteriores():
    df = datos.cargar()
    fecha = pd.Timestamp("2026-04-20", tz=datos.ZONA)     # a media temporada: hay futuro ya jugado
    futuros = (df["fecha_utc"] >= fecha.tz_convert("UTC")) & (df["estado"] == "jugado")
    assert futuros.sum() > 50
    a = Contexto(fecha, partidos=df)
    alterado = df.copy()                                  # mismo calendario, pero el futuro aún no se juega
    cols = [c for c in df.columns if c not in datos.COLS_PREPARTIDO]
    alterado.loc[futuros, "estado"] = "programado"
    for c in ("gl", "gv", "gl_ht", "gv_ht", "resultado", "tiene_tarjetas", "tiene_eventos"):
        if c in cols:
            alterado.loc[futuros, c] = np.nan
    b = Contexto(fecha, partidos=alterado)
    assert a.hist["fecha_utc"].max() < fecha.tz_convert("UTC") and len(a.hist) == len(b.hist)
    assert a.tabla().equals(b.tabla())
    prox = a.agenda.head(6)
    assert len(prox) == 6 and (prox["fecha_utc"] >= fecha.tz_convert("UTC")).all()
    limite = fecha.strftime("%Y-%m-%d")
    for fila in prox.to_dict("records"):
        ra, rb = a.partido(fila), b.partido(fila)
        assert json.dumps(ra, sort_keys=True, default=str) == json.dumps(rb, sort_keys=True, default=str)
        dia_partido = ra["fecha"]
        for clave, f in _fechas({k: v for k, v in ra.items() if k != "fecha"}):
            assert f <= limite, (clave, f)
        assert dia_partido >= limite
    assert json.dumps(a.dominios_liguilla(), sort_keys=True) == json.dumps(b.dominios_liguilla(), sort_keys=True)
    assert (a.series()["fecha"] < fecha.tz_convert("UTC")).all()
    # las tarjetas que lee son sólo de partidos anteriores
    assert set(a._tarjetas()["partido_id"]) <= set(a.hist["id"])


def test_contexto_contenido(ctx_real):
    c = ctx_real
    t = c.tabla()
    assert len(t) == 18 and list(t["pos"]) == list(range(1, 19))
    assert (t["PJ"] == t["G"] + t["E"] + t["P"]).all() and (t["PTS"] == 3 * t["G"] + t["E"]).all()
    assert t["GF"].sum() == t["GC"].sum() and t["PTS"].is_monotonic_decreasing
    pend = datos.pendientes()
    r = c.partido(pend.iloc[-1].to_dict())
    json.dumps(r, default=str)                            # serializable
    assert len(r["equipo_local"]["forma"]) == 5 and r["equipo_local"]["posicion"] in range(1, 19)
    bl, bv, bt = (r["equipo_local"][k] for k in ("balance_local", "balance_visita", "balance"))
    assert bl["pj"] + bv["pj"] == bt["pj"] and bl["gf"] + bv["gf"] == bt["gf"]
    assert r["sede"]["altitud_m"] is not None and r["sede"]["aforo"] is not None
    assert r["viaje_visitante_km"] is not None and r["viaje_visitante_km"] > 0
    assert r["descanso_local"]["dias"] > 0
    h = r["historial"]
    assert h["ultimos"]["balance"]["pj"] == len(h["ultimos"]["partidos"]) <= 10
    assert h["series"]["gana_local"] + h["series"]["gana_visitante"] <= h["series"]["n"]


def test_dominios_incluye_america_cruz_azul(ctx_real):
    d = ctx_real.dominios_liguilla(top=10)
    par = [x for x in d if (x["a"], x["b"]) == ("América", "Cruz Azul")]
    assert par, [(x["a"], x["b"]) for x in d]
    x = par[0]
    assert x["series"] >= 5 and x["gana_a"] + x["gana_b"] + x["sin_decidir"] == x["series"]
    assert x["finales"] >= 3 and x["finales_a"] + x["finales_b"] <= x["finales"]
    be = ctx_real.balance_estadios()
    assert len(be) == 18 and all(b["historico"] is None or b["historico"]["pj"] >= b["ultimos_3_anios"]["pj"] for b in be)


# ==================================================================================================
# 5. Pronosticador provisional: contrato
# ==================================================================================================
@pytest.fixture(scope="module")
def pron():
    return Pronosticador(corte=FECHA)


def test_contrato_pronosticador(pron):
    assert len(pron.equipos) == 18 and pron.equipos == sorted(pron.equipos)
    pend = datos.pendientes()
    ps = pron.partidos(pend)
    assert [d["id"] for d in ps] == [int(i) for i in pend["id"]]
    ma = pron.malla(n=30, fase="regular", semilla=3)
    assert ma["equipos"] == pron.equipos and ma["lam_l"].shape == ma["lam_v"].shape == (30, 18, 18)
    assert np.isfinite(ma["lam_l"]).all() and (ma["lam_l"] > 0).all() and (ma["lam_v"] > 0).all()
    ix = {e: i for i, e in enumerate(pron.equipos)}
    for d, loc, vis in zip(ps, pend["local"], pend["visitante"]):
        assert abs(ma["lam_l"][0, ix[loc], ix[vis]] - d["lam_l"]) < 1e-12
        assert abs(ma["lam_v"][0, ix[loc], ix[vis]] - d["lam_v"]) < 1e-12
        assert set(d) >= {"id", "lam_l", "lam_v", "rho", "explica"}
        el = d["lam_base"] * np.prod([f["efecto_l"] for f in d["explica"]])
        ev = d["lam_base"] * np.prod([f["efecto_v"] for f in d["explica"]])
        assert abs(el - d["lam_l"]) < 1e-9 and abs(ev - d["lam_v"]) < 1e-9
        assert all(set(f) == {"factor", "detalle", "efecto_l", "efecto_v"} for f in d["explica"])
    # muestras: misma semilla = mismas muestras; centradas en la estimación puntual
    assert np.array_equal(ma["lam_l"], pron.malla(n=30, semilla=3)["lam_l"])
    assert not np.array_equal(ma["lam_l"][1:], pron.malla(n=30, semilla=4)["lam_l"][1:])
    g = pron.malla(n=2001, semilla=7)
    i, j = ix[pend["local"].iloc[0]], ix[pend["visitante"].iloc[0]]
    z = np.log(g["lam_l"][1:, i, j])
    assert abs(z.mean() - np.log(g["lam_l"][0, i, j])) < 4 * z.std() / np.sqrt(2000)
    assert 0.02 < z.std() < 0.5
    assert np.array_equal(pron.malla(n=1, fase="liguilla")["lam_l"].shape, (1, 18, 18))
    f = pron.fuerzas()
    assert list(f.index) == pron.equipos
    assert {"ataque", "defensa", "rating", "ventaja_local", "ee_rating", "ee_ataque", "ee_defensa"} <= set(f.columns)
    assert (f["ee_rating"] > 0).all() and abs(np.log(f["ataque"]).mean()) < 1e-9


def test_pronosticador_no_ve_el_futuro():
    df = datos.cargar()
    corte = pd.Timestamp("2026-04-20", tz=datos.ZONA)
    a = Pronosticador(corte=corte, partidos=df)
    recortado = df[(df["fecha_utc"] < corte.tz_convert("UTC")) | (df["torneo"] == a.torneo)].copy()
    fut = recortado["fecha_utc"] >= corte.tz_convert("UTC")
    recortado.loc[fut, ["gl", "gv"]] = np.nan
    recortado.loc[fut, "estado"] = "programado"
    recortado.loc[fut, "evaluable"] = False
    b = Pronosticador(corte=corte, partidos=recortado)
    assert a.equipos == b.equipos and np.allclose(a.theta, b.theta, atol=1e-12)


def test_paquete_partidos_solo_con_el_contrato(pron):
    pend = datos.pendientes()
    r = cb.paquete_partidos(pron, pend)
    json.dumps(r)                                          # serializable
    assert len(r["partidos"]) == len(pend) and 0.35 < r["p1_l"] < 0.55
    for d in r["partidos"]:
        assert abs(np.sum(d["matriz"]) - 1.0) < 1e-4 and len(d["marcadores"]) == 5
        assert set(d["combinadas"]) == set(cb.BANDAS)
        assert all(c is None or len(c["picks"]) == 4 for c in d["combinadas"].values())
        assert d["combinadas"]["segura"]["prob_conjunta"] > d["combinadas"]["atrevida"]["prob_conjunta"]
    assert len(r["jornada"]["candidatos"]) + len(r["jornada"]["sin_pick"]) == len(pend)


# ==================================================================================================
# 6. Córners y tarjetas (modelos simples, fuera del catálogo)
# ==================================================================================================
@pytest.mark.parametrize("que", ["corners", "tarjetas"])
def test_modelo_conteo_coherente_y_sin_futuro(que):
    df = datos.cargar()
    corte = pd.Timestamp("2024-07-01", tz="UTC")
    a = mk.ModeloConteo(que).ingerir_historia(df[(df["estado"] == "jugado") & (df["fecha_utc"] < corte)])
    pr = a.predecir("América", "Cruz Azul")
    assert pr is not None and abs(pr["p_mas"] + pr["p_menos"] - 1.0) < 1e-12
    assert 0.05 < pr["p_mas"] < 0.95 and 0.2 < pr["p_mas_liga"] < 0.8 and pr["mu"] > 0
    assert len(a.liga) == mk.N_LIGA and all(len(d) <= mk.N_EQUIPO for d in a.eq.values())
    nuevo = a.predecir("Equipo Nuevo", "Otro Nuevo")       # sin historia: medias de liga
    L = np.array(a.liga, float)
    assert abs(nuevo["mu"] - L.sum(axis=1).mean()) < 1e-9
    assert not {m.familia for m in mk.catalogo()} & {"corners", "tarjetas"}     # no pasaron la validación
