# -*- coding: utf-8 -*-
"""
Pruebas del simulador (tabla, liguilla, campeón), de los sellos y de la exportación.

    cd /home/user/SA/ligamx && python3 -m pytest produccion/pruebas/test_simulador.py -q

Los escenarios de liguilla se CONSTRUYEN en memoria (marcadores inventados sólo para probar la
mecánica); nada de eso se escribe en datos/ ni en salidas/.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # .../ligamx

from modelo import arnes, datos  # noqa: E402
from produccion import exportar as ex  # noqa: E402
from produccion import sellos  # noqa: E402
from produccion import simulador as S  # noqa: E402
from produccion.pronosticador_provisional import Pronosticador  # noqa: E402

TORNEO = "Apertura 2026"
CORTE = "2026-11-10T00:00"                       # hora de CDMX


@pytest.fixture(scope="module")
def df():
    return datos.cargar()


@pytest.fixture(scope="module")
def pron(df):
    return Pronosticador(corte=CORTE, partidos=df)


@pytest.fixture(scope="module")
def sim(df, pron):
    return S.simular(pron, df=df, n_sim=20000, semilla=7)


# ==================================================================================================
# Desempates
# ==================================================================================================
def test_desempates_a_mano():
    """Seis equipos empatados por pares en cada criterio: el orden sale del criterio siguiente."""
    #            A    B    C    D    E    F    G
    pts = np.array([30, 30, 30, 30, 30, 30, 31])
    dg = np.array([5, 5, 5, 5, 5, 4, -9])
    gf = np.array([20, 20, 20, 20, 19, 40, 1])
    gvis = np.array([9, 9, 9, 8, 30, 30, 0])
    fair = np.array([40, 40, 41, 10, 10, 10, 99])       # menos es mejor
    coc = np.array([1.5, 1.6, 9.9, 9.9, 9.9, 9.9, 0.1])
    azar = np.array([0.1, 0.9, 0.5, 0.5, 0.5, 0.5, 0.5])
    orden = S.ordenar(pts, dg, gf, gvis, fair, coc, azar)
    # G (más puntos); B sobre A por cociente; luego C (peor Fair Play), D (menos goles de visita),
    # E (menos goles a favor) y F (peor diferencia)
    assert orden.tolist() == [6, 1, 0, 2, 3, 4, 5]
    # el sorteo sólo decide cuando todo lo demás empata
    coc2 = coc.copy(); coc2[1] = 1.5
    assert S.ordenar(pts, dg, gf, gvis, fair, coc2, azar).tolist() == [6, 0, 1, 2, 3, 4, 5]
    azar2 = azar.copy(); azar2[0] = 0.95
    assert S.ordenar(pts, dg, gf, gvis, fair, coc2, azar2).tolist() == [6, 1, 0, 2, 3, 4, 5]


def test_desempates_por_simulacion():
    """La versión matricial ordena cada fila por separado."""
    rng = np.random.default_rng(1)
    pts = rng.integers(10, 14, size=(50, 18))
    dg = rng.integers(-2, 3, size=(50, 18))
    cero = np.zeros((50, 18))
    orden = S.ordenar(pts, dg, cero, cero, cero, cero, rng.random((50, 18)))
    for i in range(50):
        llave = pts[i, orden[i]] * 100 + dg[i, orden[i]]
        assert (np.diff(llave) <= 0).all()
        assert sorted(orden[i].tolist()) == list(range(18))


def test_fair_play_coincide_con_conteo_independiente(df):
    est = S.estado_torneo(df, TORNEO, CORTE)
    t = datos.tabla("tarjetas", est["jugados"])
    total = 0
    for _, g in t.groupby(["partido_id", "equipo", "jugador_id"], dropna=False):
        tipos = set(g["tipo"])
        if "segunda_amarilla" in tipos:
            total += 3
        elif "roja" in tipos:
            total += 4 if "amarilla" in tipos else 3
        else:
            total += 1
    assert est["fair"].sum() == total
    assert (est["fair"] > 0).all()


def test_goles_de_visitante_y_cociente(df):
    est = S.estado_torneo(df, TORNEO, CORTE)
    i = est["equipos"].index("América")
    jug = est["jugados"]
    vis = jug[jug["visitante"] == "América"].sort_values("fecha_utc")
    assert est["gvis"][i] == vis["gv"].head(S.VISITAS_CUENTAN).sum()
    assert (est["gvis"] <= est["gf_v"]).all()
    j = est["equipos"].index("Atlante")                 # recién llegado: su cociente sólo tiene este torneo
    assert est["coc_pj"][j] == est["pj"][j] and est["coc_pts"][j] == est["pts"][j]
    assert est["coc_pj"][i] == 4 * 17 + est["pj"][i]


# ==================================================================================================
# Tabla
# ==================================================================================================
def test_tabla_actual_coincide_con_csv(df):
    csv = pd.read_csv(datos.DIR_DATOS / "tabla_apertura2026.csv")
    tab = S.tabla_actual(S.estado_torneo(df, TORNEO, None))
    if int(csv["PJ"].sum()) != int(tab["PJ"].sum()):
        pytest.skip("tabla_apertura2026.csv no está al día con partidos.csv")
    cols = ["pos", "equipo", "PJ", "G", "E", "P", "GF", "GC", "DG", "PTS", "PJ_L", "PTS_L", "GF_L", "GC_L", "PJ_V", "PTS_V", "GF_V", "GC_V"]
    pd.testing.assert_frame_equal(tab[cols].reset_index(drop=True), csv[cols].reset_index(drop=True), check_dtype=False)


def test_sin_pendientes_la_tabla_simulada_es_la_real(df, pron):
    """Con todos los partidos jugados (se quitan los pendientes) la tabla simulada es la del CSV."""
    csv = pd.read_csv(datos.DIR_DATOS / "tabla_apertura2026.csv")
    jugado = df[~((df["torneo"] == TORNEO) & (df["estado"] != "jugado"))]
    if int(csv["PJ"].sum()) != 2 * int(((jugado["torneo"] == TORNEO) & (jugado["fase"] == "regular")).sum()):
        pytest.skip("tabla_apertura2026.csv no está al día con partidos.csv")
    r = S.simular(pron, corte="2026-12-31T00:00", df=jugado, n_sim=2000, n_muestras=200, torneo=TORNEO)
    assert r["meta"]["partidos_pendientes_regular"] == 0 and r["meta"]["regular_completa"]
    pos_csv = dict(zip(csv["equipo"], csv["pos"]))
    pts_csv = dict(zip(csv["equipo"], csv["PTS"]))
    for d in r["por_equipo"]:
        assert d["posicion"][pos_csv[d["equipo"]] - 1] == pytest.approx(1.0)
        assert d["puntos_esperados"] == pytest.approx(pts_csv[d["equipo"]])
        assert d["p_clasifica"] == (1.0 if pos_csv[d["equipo"]] <= 8 else 0.0)


# ==================================================================================================
# Simulación
# ==================================================================================================
def test_probabilidades_coherentes(sim):
    eq = sim["por_equipo"]
    assert len(eq) == 18
    assert sum(d["p_campeon"] for d in eq) == pytest.approx(1.0, abs=1e-9)
    assert sum(d["p_final"] for d in eq) == pytest.approx(2.0, abs=1e-9)
    assert sum(d["p_semifinal"] for d in eq) == pytest.approx(4.0, abs=1e-9)
    assert sum(d["p_clasifica"] for d in eq) == pytest.approx(8.0, abs=1e-9)
    for d in eq:
        assert sum(d["posicion"]) == pytest.approx(1.0, abs=1e-9)
        assert d["p_campeon"] <= d["p_final"] <= d["p_semifinal"] <= d["p_clasifica"] <= 1.0
        assert d["p_clasifica"] == pytest.approx(sum(d["posicion"][:8]), abs=1e-9)
        assert d["pts_min"] <= d["puntos_esperados"] <= d["pts_max"]
        assert d["pts_min"] >= d["pts_actual"]
        for k in ("p_campeon", "p_final", "p_semifinal", "p_clasifica"):
            assert 0.0 <= d["ee_" + k] < 0.02
    for c in sim["cruces_cuartos"]:
        assert sum(o["prob"] for o in c["opciones"]) <= 1.0 + 1e-9
        for o in c["opciones"]:
            assert o["p_avanza_mejor"] + o["p_avanza_peor"] == pytest.approx(1.0)
    assert sim["meta"]["segundos"] < 60


def test_reproducible_con_semilla(df, pron):
    a = S.simular(pron, df=df, n_sim=4000, n_muestras=400, semilla=11)
    b = S.simular(pron, df=df, n_sim=4000, n_muestras=400, semilla=11)
    c = S.simular(pron, df=df, n_sim=4000, n_muestras=400, semilla=12)
    assert [d["p_campeon"] for d in a["por_equipo"]] == [d["p_campeon"] for d in b["por_equipo"]]
    assert a["cruces_cuartos"] == b["cruces_cuartos"]
    assert [(d["equipo"], d["p_campeon"]) for d in a["por_equipo"]] != [(d["equipo"], d["p_campeon"]) for d in c["por_equipo"]]


def test_marcadores_con_y_sin_rho():
    rng = np.random.default_rng(3)
    n = 200000
    for rho in (0.0, -0.1):
        gl, gv = S.marcadores(rng, np.full(n, 1.4), np.full(n, 1.1), rho)
        M = arnes.matriz_marcadores(1.4, 1.1, rho)
        for x, y in ((0, 0), (1, 1), (2, 1)):
            f = float(((gl == x) & (gv == y)).mean())
            assert f == pytest.approx(M[x, y], abs=4 * math.sqrt(M[x, y] / n))


# ==================================================================================================
# Series
# ==================================================================================================
def test_prob_serie_contra_enumeracion():
    """Las tres reglas contra una enumeración directa de los cuatro marcadores."""
    M1 = arnes.matriz_marcadores(1.1, 1.3)            # ida: local = peor sembrado
    M2 = arnes.matriz_marcadores(1.7, 0.9)            # vuelta: local = mejor sembrado
    E = arnes.matriz_marcadores(1.7 / 3, 0.9 / 3)
    x, y = np.indices(E.shape)
    e_m, e_e = E[x > y].sum(), E[x == y].sum()
    pos = gv = fin = 0.0
    for a in range(11):                                # goles del peor en la ida
        for b in range(11):                            # goles del mejor en la ida (de visita)
            for c in range(11):                        # goles del mejor en la vuelta
                for d in range(11):                    # goles del peor en la vuelta (de visita)
                    p = M1[a, b] * M2[c, d]
                    gm, gp = b + c, a + d
                    if gm > gp:
                        pos += p; gv += p; fin += p
                    elif gm == gp:
                        pos += p
                        gv += p if b >= d else 0.0
                        fin += p * (e_m + 0.5 * e_e)
    assert S.prob_serie(M1, M2, regla="posicion")["p_mejor"] == pytest.approx(pos, abs=1e-10)
    assert S.prob_serie(M1, M2, regla="gol_visitante")["p_mejor"] == pytest.approx(gv, abs=1e-10)
    assert S.prob_serie(M1, M2, regla="final", lam_extra=(1.7 / 3, 0.9 / 3))["p_mejor"] == pytest.approx(fin, abs=1e-10)
    r = S.prob_serie(M1, M2)
    assert r["p_global_mejor"] + r["p_global_empate"] + r["p_global_peor"] == pytest.approx(1.0)
    assert r["G"].sum() == pytest.approx(1.0)


def test_prob_serie_casos_a_mano():
    ida, vta = S.matriz_fija(1, 0), S.matriz_fija(2, 1)      # 1-0 en casa del peor; 2-1 en casa del mejor: global 2-2
    assert S.prob_serie(ida, vta, regla="posicion")["p_mejor"] == 1.0
    assert S.prob_serie(ida, vta, regla="gol_visitante")["p_mejor"] == 0.0      # el peor anotó de visita
    assert S.prob_serie(S.matriz_fija(1, 1), S.matriz_fija(0, 0), regla="gol_visitante")["p_mejor"] == 1.0
    # ida ya jugada 3-0 para el peor: el mejor necesita ganar la vuelta por 3 o más
    M2 = arnes.matriz_marcadores(1.8, 0.8)
    x, y = np.indices(M2.shape)
    cond = S.prob_serie(S.matriz_fija(3, 0), M2, regla="posicion")["p_mejor"]
    assert cond == pytest.approx(M2[x - y >= 3].sum(), abs=1e-12)
    libre = S.prob_serie(arnes.matriz_marcadores(1.0, 1.4), M2, regla="posicion")["p_mejor"]
    assert cond < 0.2 < libre


def _con_liguilla(df, piernas):
    """
    Escenario CONSTRUIDO: la fase regular se da por terminada (los pendientes quedan 1-1) y se agregan
    las filas de liguilla de `piernas`: (fase, pierna, local, visitante, gl, gv, pen_l, pen_v, fecha).
    """
    d = df.copy()
    m = (d["torneo"] == TORNEO) & (d["estado"] != "jugado")
    d.loc[m, ["gl", "gv", "gl_ht", "gv_ht"]] = [1.0, 1.0, 0.0, 0.0]
    d.loc[m, "estado"] = "jugado"
    base = d[d["torneo"] == TORNEO].iloc[-1]
    filas = []
    for k, (fase, pierna, loc, vis, gl, gv, pl, pv, fecha) in enumerate(piernas):
        r = base.copy()
        t = pd.Timestamp(fecha, tz="UTC")
        r["id"], r["fecha_utc"], r["fecha_local"] = 990000000 + k, t, t.tz_localize(None).normalize()
        r["fase"], r["pierna"], r["local"], r["visitante"] = fase, float(pierna), loc, vis
        r["estado"] = "programado" if gl is None else "jugado"
        r["gl"], r["gv"] = (np.nan, np.nan) if gl is None else (float(gl), float(gv))
        r["gl_et"], r["gv_et"] = np.nan, np.nan
        r["pen_l"], r["pen_v"] = (np.nan, np.nan) if pl is None else (float(pl), float(pv))
        filas.append(r)
    return pd.concat([d, pd.DataFrame(filas)], ignore_index=True) if filas else d


def _siembra(df):
    d = _con_liguilla(df, [])
    tab = S.tabla_actual(S.estado_torneo(d, TORNEO, "2026-11-24T00:00"))
    assert int(tab["PJ"].min()) == 17
    return tab["equipo"].tolist()[:8]


def test_serie_real_con_ida_jugada_condiciona(df, pron):
    s = _siembra(df)
    piernas = [
        ("cuartos", 1, s[7], s[0], 4, 0, None, None, "2026-11-26T01:00"),      # el 8 golea al 1 en la ida
        ("cuartos", 2, s[0], s[7], None, None, None, None, "2026-11-29T01:00"),
        ("cuartos", 1, s[6], s[1], 0, 0, None, None, "2026-11-26T03:00"),
        ("cuartos", 2, s[1], s[6], None, None, None, None, "2026-11-29T03:00"),
        ("cuartos", 1, s[5], s[2], 1, 1, None, None, "2026-11-25T01:00"),      # serie decidida: global 1-1 -> pasa el 3
        ("cuartos", 2, s[2], s[5], 0, 0, None, None, "2026-11-27T01:00"),
        ("cuartos", 1, s[4], s[3], 2, 0, None, None, "2026-11-25T03:00"),      # serie decidida: pasa el 5 (2-1)
        ("cuartos", 2, s[3], s[4], 1, 0, None, None, "2026-11-27T03:00"),
    ]
    d = _con_liguilla(df, piernas)
    r = S.simular(pron, corte="2026-11-27T12:00", df=d, n_sim=40000, n_muestras=0, semilla=5, torneo=TORNEO)
    assert r["meta"]["regular_completa"]
    eq = {x["equipo"]: x for x in r["por_equipo"]}
    assert eq[s[2]]["p_semifinal"] == 1.0 and eq[s[5]]["p_semifinal"] == 0.0     # empate global: el mejor sembrado
    assert eq[s[4]]["p_semifinal"] == 1.0 and eq[s[3]]["p_semifinal"] == 0.0
    series = {(x["mejor"], x["peor"]): x for x in r["series_reales"]}
    assert len(series) == 4
    a = series[(s[0], s[7])]
    assert not a["decidida"] and a["piernas"][0]["jugado"] and not a["piernas"][1]["jugado"]
    # exacto: el 1 necesita ganar la vuelta por 4 o más (con empate global avanza el mejor sembrado)
    v = a["piernas"][1]
    M2 = arnes.matriz_marcadores(v["lam_l"], v["lam_v"])
    x, y = np.indices(M2.shape)
    assert a["p_avanza_mejor"] == pytest.approx(M2[x - y >= 4].sum(), abs=1e-9)
    ee = math.sqrt(a["p_avanza_mejor"] * (1 - a["p_avanza_mejor"]) / 40000)
    assert eq[s[0]]["p_semifinal"] == pytest.approx(a["p_avanza_mejor"], abs=5 * ee + 1e-4)
    assert a["p_avanza_mejor_sim"] == pytest.approx(eq[s[0]]["p_semifinal"], abs=1e-12)
    # sin la ida, el 1 sería claro favorito
    sin_ida = _con_liguilla(df, [p for p in piernas if p[1] == 2 or p[2] != s[7]])
    r0 = S.simular(pron, corte="2026-11-27T12:00", df=sin_ida, n_sim=40000, n_muestras=0, semilla=5, torneo=TORNEO)
    p0 = {x["equipo"]: x for x in r0["por_equipo"]}[s[0]]["p_semifinal"]
    assert p0 > 0.5 > 0.2 > eq[s[0]]["p_semifinal"]
    b = series[(s[1], s[6])]                                                    # ida 0-0: gana o empata la vuelta
    v = b["piernas"][1]
    M2 = arnes.matriz_marcadores(v["lam_l"], v["lam_v"])
    assert b["p_avanza_mejor"] == pytest.approx(M2[x >= y].sum(), abs=1e-9)
    assert sum(g["prob"] for g in b["globales"]) <= 1.0 + 1e-9
    assert sum(x["p_campeon"] for x in r["por_equipo"]) == pytest.approx(1.0)
    # antes del corte de la ida nada de la liguilla se da por jugado
    r_antes = S.simular(pron, corte="2026-11-24T12:00", df=d, n_sim=4000, n_muestras=0, semilla=5, torneo=TORNEO)
    assert all(not p["jugado"] for x in r_antes["series_reales"] for p in x["piernas"])


def test_cuadro_completo_con_final_en_penales(df, pron):
    s = _siembra(df)
    f = "2026-11-2"
    piernas = []
    for k, (m, p) in enumerate(((0, 7), (1, 6), (2, 5), (3, 4))):               # pasan 1, 2, 3 y 4
        piernas += [("cuartos", 1, s[p], s[m], 0, 0, None, None, f"{f}5T0{k}:00"),
                    ("cuartos", 2, s[m], s[p], 1, 0, None, None, f"{f}8T0{k}:00")]
    piernas += [("semifinal", 1, s[3], s[0], 2, 0, None, None, "2026-12-02T01:00"),     # resiembra: 1-4 y 2-3
                ("semifinal", 2, s[0], s[3], 0, 0, None, None, "2026-12-05T01:00"),     # pasa el 4
                ("semifinal", 1, s[2], s[1], 1, 1, None, None, "2026-12-02T03:00"),
                ("semifinal", 2, s[1], s[2], 2, 2, None, None, "2026-12-05T03:00"),     # 3-3: pasa el 2
                ("final", 1, s[3], s[1], 1, 0, None, None, "2026-12-10T01:00"),
                ("final", 2, s[1], s[3], 1, 0, 3, 5, "2026-12-13T01:00")]               # 1-1 global; penales 3-5: campeón el 4
    d = _con_liguilla(df, piernas)
    r = S.simular(pron, corte="2026-12-20T00:00", df=d, n_sim=2000, n_muestras=100, torneo=TORNEO)
    eq = {x["equipo"]: x for x in r["por_equipo"]}
    assert eq[s[3]]["p_campeon"] == 1.0 and eq[s[1]]["p_final"] == 1.0 and eq[s[1]]["p_campeon"] == 0.0
    assert all(x["decidida"] for x in r["series_reales"]) and len(r["series_reales"]) == 7
    # a media final (sólo la ida) el campeón no está decidido y el título se reparte entre los dos finalistas
    r2 = S.simular(pron, corte="2026-12-11T00:00", df=d, n_sim=20000, n_muestras=0, torneo=TORNEO)
    eq2 = {x["equipo"]: x for x in r2["por_equipo"]}
    assert eq2[s[3]]["p_campeon"] + eq2[s[1]]["p_campeon"] == pytest.approx(1.0)
    fin = [x for x in r2["series_reales"] if x["fase"] == "final"][0]
    p_exacta = fin["p_avanza_mejor"] if fin["mejor"] == s[1] else fin["p_avanza_peor"]
    assert eq2[s[1]]["p_campeon"] == pytest.approx(p_exacta, abs=0.015)
    assert 0.05 < eq2[s[1]]["p_campeon"] < 0.5                                   # va abajo 0-1 y cierra en casa


def test_regla_por_torneo():
    assert S._regla_de("Apertura 2019", "cuartos") == "gol_visitante"
    assert S._regla_de("Clausura 2021", "semifinal") == "gol_visitante"
    assert S._regla_de("Apertura 2021", "cuartos") == "posicion"
    assert S._regla_de("Apertura 2019", "final") == "final"


# ==================================================================================================
# Sellos
# ==================================================================================================
def test_sellar_y_calificar(df, pron, tmp_path):
    ruta, sal = tmp_path / "sellos.jsonl", tmp_path / "desempeno.json"
    ahora = pd.Timestamp("2026-11-10T12:00:00Z")
    nuevos = sellos.sellar(pron, df, ruta, ahora=ahora)
    pend = df[(df["estado"] == "programado") & (df["fecha_utc"] > ahora)]
    assert len(nuevos) == len(pend) > 0
    assert sellos.sellar(pron, df, ruta, ahora=ahora + pd.Timedelta(hours=1)) == []      # idéntico: no se repite
    s0 = nuevos[0]
    assert s0["p_l"] + s0["p_e"] + s0["p_v"] == pytest.approx(1.0, abs=1e-5)
    assert set(s0["combinadas"]) == {"segura", "equilibrada", "atrevida"}
    assert all(len(c["picks"]) == 4 for c in s0["combinadas"].values())
    assert sellos.calificar(df, ruta, sal)["n_calificados"] == 0
    with pytest.raises(ValueError):                                                      # no se sella hacia atrás
        sellos.sellar(pron, df, ruta, ahora=pd.Timestamp("2026-11-01T00:00:00Z"))
    # resultado inventado SÓLO para la prueba: el primer pendiente termina 2-1 (1-0 al descanso)
    d = df.copy()
    pid = int(s0["id"])
    m = d["id"] == pid
    d.loc[m, ["gl", "gv", "gl_ht", "gv_ht"]] = [2.0, 1.0, 1.0, 0.0]
    d.loc[m, "estado"] = "jugado"
    # un sello posterior al inicio no cuenta
    tarde = dict(s0, sellado_utc=(d.loc[m, "fecha_utc"].iloc[0] + pd.Timedelta(minutes=5)).isoformat(), p_l=0.99, p_e=0.005, p_v=0.005)
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(tarde, ensure_ascii=False) + "\n")
    r = sellos.calificar(d, ruta, sal)
    assert r["n_calificados"] == 1 and json.loads(sal.read_text(encoding="utf-8"))["n_calificados"] == 1
    p = r["partidos"][0]
    assert p["sellado_utc"] == s0["sellado_utc"] and p["resultado"] == "L"
    assert p["logloss"] == pytest.approx(-math.log(s0["p_l"]), abs=1e-5)
    assert p["brier"] == pytest.approx((s0["p_l"] - 1) ** 2 + s0["p_e"] ** 2 + s0["p_v"] ** 2, abs=1e-5)
    assert p["rps"] == pytest.approx(((s0["p_l"] - 1) ** 2 + (s0["p_l"] + s0["p_e"] - 1) ** 2) / 2, abs=1e-5)
    assert p["acierto_1x2"] == int(s0["pick"] == "L")
    assert p["marcador_exacto"] == int(s0["marcador"] == {"gl": 2, "gv": 1, "prob": s0["marcador"]["prob"]})
    for v, c in p["combinadas"].items():
        assert c["aciertos"] == sum(bool(x["acerto"]) for x in c["picks"]) and c["n_picks"] == 4
        assert c["completa"] == (c["aciertos"] == 4)
    assert r["acumulado"]["n"] == 1 and r["acumulado"]["logloss"] == pytest.approx(p["logloss"])


def test_calificar_picks_a_mano():
    claves = ["O15", "1", "X", "AA_SI", "D_1", "G2T_SI", "U25", "ME_2-1", "ME_0-0", "D_X", "L_2MAS", "PC_L"]
    assert sellos.calificar_picks(claves, 2, 1, 1, 0) == [True, True, False, True, True, True, False, True, False, False, True, False]
    sin = sellos.calificar_picks(claves, 2, 1, np.nan, np.nan)                   # sin marcador del descanso
    assert sin[:4] == [True, True, False, True] and sin[4] is None and sin[5] is None and sin[9] is None
    assert sin[6] is False and sin[7] is True


# ==================================================================================================
# Exportación
# ==================================================================================================
def test_etiquetas_de_jornada(df):
    reg = df[(df["torneo"] == TORNEO) & (df["fase"] == "regular") & (df["estado"] != "cancelado")]
    j = ex.etiquetas_jornada(reg)
    por = reg.assign(j=reg["id"].map(j))
    q = por[(por["local"] == "Querétaro") & (por["visitante"] == "Monterrey")]["j"].iloc[0]
    assert q == "Jornada 7 (reprogramado)"
    assert (por["j"] == "Jornada 17").sum() == 9
    assert (por["j"] == "Jornada 1").sum() == 9


def test_exportar_valida_su_json(df, pron, tmp_path):
    doc = ex.construir(n_sim=4000, sellar=False, ruta_sellos=tmp_path / "s.jsonl", ruta_desempeno=tmp_path / "d.json",
                       df=df, pron=pron)
    assert ex.validar(doc) == []
    for k in ex.OBLIGATORIOS:
        assert k in doc
    texto = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    assert len(texto.encode("utf-8")) < 600 * 1024
    assert json.loads(texto) == doc                                               # serializable sin pérdida
    assert len(doc["tabla"]) == 18 and len(doc["fuerzas"]) == 18
    for p in doc["pendientes"]:
        assert p["p_local"] + p["p_empate"] + p["p_visitante"] == pytest.approx(1.0, abs=2e-4)
        if not p["detalle"]:
            continue
        assert 0 <= p["marcador"]["prob"] <= 1 and len(p["top5"]) == 5
        assert all(0 <= m["prob"] <= 1 for m in p["mercados"])
        assert p["estadio"]["slug"]
        assert all(len(c["picks"]) == 4 and 0 < c["prob_conjunta"] <= 1 for c in p["combinadas"].values() if c)
        assert sum(sum(f) for f in p["matriz"]) + p["matriz_resto"] == pytest.approx(1.0, abs=5e-3)
    assert sum(d["prob"] for d in doc["proyeccion"]["campeon"]) == pytest.approx(1.0, abs=2e-3)
    # el validador detecta un documento estropeado
    malo = json.loads(texto)
    if malo["pendientes"]:
        malo["pendientes"][0]["p_local"] = 1.2
    malo["proyeccion"]["campeon"][0]["prob"] += 0.2
    del malo["avisos"]
    assert ex.validar(malo) == ["falta el campo 'avisos'"]
    malo["avisos"] = ["x"]
    err = ex.validar(malo)
    assert any("campeón" in e for e in err)
    if malo["pendientes"]:
        assert any("fuera de [0,1]" in e for e in err) and any("1X2 suma" in e for e in err)
    ruta, peso = ex.escribir(doc, tmp_path / "actual.json")
    assert ruta.exists() and peso < 600 * 1024 and len(list((tmp_path / "historial").glob("actual_*.json"))) == 1


def test_exportar_inicio_de_torneo_cabe_en_600_kb(df, tmp_path):
    """Corte retrospectivo con 100 o más partidos por jugar: sólo los primeros llevan ficha completa."""
    doc = ex.construir("2026-08-10T00:00", n_sim=2000, sellar=False, ruta_sellos=tmp_path / "s.jsonl",
                       ruta_desempeno=tmp_path / "d.json", df=df, pron=Pronosticador(corte="2026-08-10T00:00", partidos=df))
    assert ex.validar(doc) == []
    assert doc["meta"]["retrospectivo"] and len(doc["pendientes"]) > 100
    assert sum(p["detalle"] for p in doc["pendientes"]) == ex.MAX_DETALLE
    assert not (tmp_path / "s.jsonl").exists()                                    # una corrida retrospectiva no sella


def test_ultimos_resultados_usan_el_sello_oficial(df, pron, tmp_path):
    """Un partido sellado antes de su inicio y ya jugado aparece calificado con su sello."""
    ruta = tmp_path / "sellos.jsonl"
    nuevos = sellos.sellar(pron, df, ruta, ahora=pd.Timestamp("2026-11-10T12:00:00Z"))
    pid = int(nuevos[0]["id"])
    d = df.copy()                                         # resultado inventado SÓLO para la prueba
    m = d["id"] == pid
    d.loc[m, ["gl", "gv", "gl_ht", "gv_ht"]] = [0.0, 2.0, 0.0, 1.0]
    d.loc[m, "estado"] = "jugado"
    corte = (d.loc[m, "fecha_utc"].iloc[0] + pd.Timedelta(hours=6)).tz_convert("UTC")
    doc = ex.construir(corte, n_sim=2000, sellar=False, ruta_sellos=ruta, ruta_desempeno=tmp_path / "d.json", df=d,
                       pron=Pronosticador(corte=corte, partidos=d))
    assert ex.validar(doc) == []
    u = [x for x in doc["ultimos_resultados"] if x["id"] == pid][0]
    assert u["resultado"] == "V" and u["pronostico"]["origen"] == "sello"
    assert u["pronostico"]["logloss"] == pytest.approx(-math.log(nuevos[0]["p_v"]), abs=1e-3)
    assert doc["desempeno"]["n_calificados"] == 1 and doc["desempeno"]["acumulado"]["n"] == 1
    assert pid not in [p["id"] for p in doc["pendientes"]]
    assert doc["proyeccion"]["partidos_pendientes_regular"] == 9
