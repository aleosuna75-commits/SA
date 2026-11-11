# -*- coding: utf-8 -*-
"""
Pruebas del motor en vivo: modelo en juego (produccion/en_juego.py), simulador con partidos en juego
y vivo.py (documento, eventos, observar, esperar, repetir).

    cd /home/user/SA/ligamx && python3 -m pytest produccion/pruebas/test_vivo.py -q

Sin red: las respuestas de ESPN están guardadas en produccion/pruebas/fixtures/ (scoreboard real del
7, 8, 10, 11 y 14 de noviembre de 2026; sólo se les quitó el bloque `leagues`). Los estados «en juego»
se CONSTRUYEN en memoria rebobinando un partido real ya terminado (se cortan sus jugadas en un minuto
y se recalcula el marcador): sirven para probar la mecánica y nada de eso se escribe en datos/ ni en
salidas/.
"""
from __future__ import annotations

import copy
import datetime as dt
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # .../ligamx

import vivo  # noqa: E402
from modelo import arnes, datos  # noqa: E402
from produccion import en_juego as EJ  # noqa: E402
from produccion import exportar as ex  # noqa: E402
from produccion import simulador as S  # noqa: E402
from produccion.pronosticador_provisional import Pronosticador  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
UTC = dt.timezone.utc
TORNEO = "Apertura 2026"
CORTE = "2026-11-10T00:00"                       # hora de CDMX (el mismo corte que test_simulador)
ID_PUMAS_AMERICA = 401876904                     # 2026-11-07 (03:10 UTC del 8): Pumas 2-2 América
ID_TOLUCA_MONTERREY = 401876905                  # 2026-11-07: Toluca 4-0 Monterrey, roja a Monterrey al 61'
ID_ATLAS_PACHUCA = 401876907                     # 2026-11-07: Atlas 1-4 Pachuca, autogol al 5'
ID_ATLAS_PUEBLA = 401876923                      # 2026-10-25: Atlas 4-3 Puebla, 7 goles y una roja al 78'
ID_QUERETARO_MONTERREY = 401876988               # 2026-11-14: el reprogramado que falta por jugar


# ==================================================================================================
# Utilidades de las pruebas
# ==================================================================================================
def fixture(dia: str) -> dict:
    return json.loads((FIXTURES / f"scoreboard_{dia}.json").read_text(encoding="utf-8"))


def rebobinar(evento: dict, minuto: int | None = None, estado: str = "in", nombre: str | None = None,
              reloj: str | None = None) -> dict:
    """Copia de un evento real de ESPN llevado a un momento anterior (jugadas cortadas en `minuto`)."""
    e = copy.deepcopy(evento)
    c = e["competitions"][0]
    if estado == "pre":
        det, st = [], {"clock": 0.0, "displayClock": "0'", "period": 0,
                       "type": {"name": "STATUS_SCHEDULED", "state": "pre", "completed": False}}
    else:
        det = [d for d in c["details"] if d["clock"]["value"] <= minuto * 60]
        periodo = 1 if minuto <= 45 else 2
        nombre = nombre or ("STATUS_FIRST_HALF" if periodo == 1 else "STATUS_SECOND_HALF")
        st = {"clock": minuto * 60.0 - 20.0, "displayClock": reloj or f"{minuto}'", "period": periodo,
              "type": {"name": nombre, "state": "in", "completed": False}}
    for x in c["competitors"]:
        x["score"] = str(sum(1 for d in det if d.get("scoringPlay") and d["team"]["id"] == x["team"]["id"]))
        x.pop("winner", None)
    c["details"], c["status"], e["status"] = det, st, st
    return e


def evento(dia: str, pid: int) -> dict:
    return next(e for e in fixture(dia)["events"] if int(e["id"]) == pid)


def servir(respuestas: dict):
    """`pedir` falso: responde por la fecha de la URL (dates=AAAAMMDD); un día sin respuesta viene vacío."""
    def pedir(url):
        dia = url.rsplit("dates=", 1)[-1]
        r = respuestas.get(dia, {"events": []})
        if isinstance(r, Exception):
            raise r
        return r
    return pedir


@pytest.fixture(scope="module")
def df():
    return datos.cargar()


@pytest.fixture(scope="module")
def pron(df):
    return Pronosticador(corte=CORTE, partidos=df)


@pytest.fixture(scope="module")
def par(df):
    """Parámetros del modelo en juego con lo jugado hasta el corte (sin escribir nada)."""
    return EJ.ajustar(df, corte=S.a_utc(CORTE), escribir=False)


@pytest.fixture(scope="module")
def pron_7nov(df):
    """Pronosticador con lo jugado antes de la tarde del 7 de noviembre (antes de los cuatro partidos)."""
    return Pronosticador(corte=pd.Timestamp("2026-11-07T22:00:00Z"), partidos=df)


def motor_7nov(df, pron_7nov, par, pedir=None, corte="2026-11-07T22:00:00Z", **kw):
    return vivo.Motor(n_sim=600, n_muestras=60, pron=pron_7nov, df=df, corte=vivo.de_iso(corte), sellos={},
                      parametros=par, pedir=pedir, **kw)


# ==================================================================================================
# Modelo en juego
# ==================================================================================================
def test_casillas_de_la_linea_de_tiempo():
    assert EJ.casilla(1, 1) == 0 and EJ.casilla(1, 45) == 44
    assert EJ.casilla(1, 45, 3) == 47 and EJ.casilla(1, 47) == 46            # 45'+3' y el viejo «47'» del primer tiempo
    assert EJ.casilla(2, 46) == EJ.INI_2T and EJ.casilla(2, 90) == EJ.INI_2T + 44
    assert EJ.casilla(2, 90, 5) == EJ.INI_2T + 49 and EJ.casilla(2, 93) == EJ.INI_2T + 47
    assert EJ.casilla(2, 90, 40) == EJ.N_CASILLAS - 1                         # el agregado larguísimo cae en la última
    assert EJ.casilla_de_minuto(45) == EJ.FIN_1T and EJ.casilla_de_minuto(0) == -1


def test_fraccion_restante_monotona(par):
    c = par.curva
    assert abs(c.w.sum() - 1.0) < 1e-9
    assert c.restante(0) == 1.0 and c.restante(None) == 1.0
    # secuencia completa de un partido, con el reloj en curso y con el minuto completo
    for en_curso in (True, False):
        sec = [c.restante(m, 1, en_curso=en_curso) for m in range(1, 46)]
        sec += [c.restante(45, 1, a, en_curso=en_curso) for a in range(1, EJ.A1 + 1)]
        sec += [c.restante(45, 1, descanso=True)]
        sec += [c.restante(m, 2, en_curso=en_curso) for m in range(46, 91)]
        sec += [c.restante(90, 2, a, en_curso=en_curso) for a in range(1, EJ.A2 + 1)]
        assert all(0.0 <= x <= 1.0 for x in sec)
        assert all(b <= a + 1e-12 for a, b in zip(sec, sec[1:])), "la fracción restante no puede subir"
        assert sec[0] > 0.97
    assert c.restante(90, 2, EJ.A2) == 0.0                                    # 90'+16' completo: no queda nada
    assert c.restante(90, 2, 10) < 0.01                                       # ~0 al 90+
    assert 0.0 < c.restante(90, 2, 12, en_curso=True) < 0.04                  # con el balón rodando queda un poco
    # hay más goles en el segundo tiempo que en el primero (cada uno con su agregado)
    assert c.parte_2t > 0.5 and 0.52 < c.restante(45, 1, descanso=True) < 0.60
    assert c.restante(45) > c.restante(45, 1, descanso=True) > c.restante(46, 2)


def test_probabilidades_en_juego_suman_uno_y_son_sensatas(par):
    for (gl, gv, m, per) in ((0, 0, 1, 1), (1, 0, 30, 1), (0, 2, 60, 2), (2, 2, 88, 2), (3, 1, 90, 2)):
        r = EJ.pronostico(par, 1.5, 1.2, gl, gv, m, per)
        assert abs(r["p_local"] + r["p_empate"] + r["p_visitante"] - 1.0) < 1e-9
        assert abs(r["M"].sum() - 1.0) < 1e-9
        assert r["M"][:gl, :].sum() == 0.0 and r["M"][:, :gv].sum() == 0.0   # nunca menos goles que el marcador actual
    r = EJ.pronostico(par, 1.5, 1.2, 2, 0, 80, 2)
    assert r["p_local"] > 0.95 and r["marcador_final"] == {"gl": 2, "gv": 0, "prob": r["marcador_final"]["prob"]}
    # al minuto 0 (sin empezar) es el pronóstico previo, con la misma rho
    r0 = EJ.pronostico(par, 1.5, 1.2, 0, 0, 0, 1, rho=-0.05)
    p0 = np.asarray(arnes.p1x2(arnes.matriz_marcadores(1.5, 1.2, -0.05))).ravel()
    assert np.allclose([r0["p_local"], r0["p_empate"], r0["p_visitante"]], p0, atol=1e-9)
    # con el tiempo, un empate se vuelve más probable de quedar en empate
    e30, e80 = EJ.pronostico(par, 1.5, 1.2, 1, 1, 30, 1), EJ.pronostico(par, 1.5, 1.2, 1, 1, 80, 2)
    assert e80["p_empate"] > e30["p_empate"] and e80["goles_restantes_l"] < e30["goles_restantes_l"]
    # terminado: el marcador es definitivo
    fin = EJ.pronostico(par, 1.5, 1.2, 1, 2, 90, 2, terminado=True)
    assert fin["p_visitante"] == pytest.approx(1.0) and fin["goles_restantes_l"] == 0.0
    # jugar con uno menos nunca ayuda (el multiplicador sólo se aplica si pasó de 2 errores estándar)
    con, sin = EJ.pronostico(par, 1.5, 1.2, 0, 0, 30, 1, rojas_l=1), EJ.pronostico(par, 1.5, 1.2, 0, 0, 30, 1)
    assert par.ef["con_menos"] <= 1.0 <= par.ef["con_mas"]
    assert con["p_local"] <= sin["p_local"] and con["goles_restantes_l"] <= sin["goles_restantes_l"]


def test_los_ajustes_solo_entran_si_pasan_de_dos_errores_estandar():
    celdas = {("empata", "igual"): [1000.0, 1000.0], ("pierde", "igual"): [600.0, 500.0],
              ("gana_1", "igual"): [505.0, 500.0], ("gana_2", "igual"): [200.0, 205.0]}
    r = EJ.ajustar_efectos(celdas)
    assert r["detalle"]["aplicados"] == ["pierde"]
    assert r["ef"]["pierde"] == pytest.approx(1.2, abs=0.03)
    assert r["ef"]["gana_1"] == 1.0 and r["ef"]["base"] == 1.0 and r["ef"]["con_menos"] == 1.0
    # con pocos datos nada pasa del umbral
    pocas = {("empata", "igual"): [20.0, 21.0], ("pierde", "igual"): [9.0, 7.0], ("empata", "con_menos"): [2.0, 3.5]}
    assert EJ.ajustar_efectos(pocas)["ef"] == EJ.SIN_EFECTOS
    assert EJ.multiplicador(r["ef"], -1) == r["ef"]["pierde"] and EJ.multiplicador(r["ef"], 0) == 1.0


def test_la_curva_solo_usa_el_pasado(df):
    prep = EJ.preparar(df)
    corte = pd.Timestamp("2019-07-01T00:00:00Z")
    c = EJ.curva_al_corte(prep, corte)
    assert pd.Timestamp(c.meta["hasta"]) < corte.tz_localize(None) and c.meta["torneos"] == EJ.VENTANA_TORNEOS
    assert c.meta["goles"] > EJ.MIN_GOLES_CURVA
    # un partido: los tramos reparten toda la lambda y todos los goles
    pid = int(prep["partidos"]["id"].iloc[-1])
    t = EJ.tabla_tramos(prep["ev"][pid], 1.4, 1.1, c)
    fila = prep["partidos"].iloc[-1]
    assert sum(v[0] for v in t.values()) == fila["gl"] + fila["gv"]
    assert sum(v[1] for v in t.values()) == pytest.approx(2.5, abs=1e-9)


def test_matriz_final_coincide_con_la_version_por_lotes():
    for (a, b, x, y, r) in ((0, 0, 1.3, 1.1, -0.05), (2, 1, 0.4, 0.9, 0.0), (10, 3, 0.5, 0.5, -0.05), (4, 9, 2.0, 2.5, 0.0),
                            (1, 0, 0.0, 0.0, 0.0)):
        assert np.allclose(S.matrices_en_juego(a, b, [x], [y], r)[0], EJ.matriz_final(a, b, x, y, r))
    assert EJ.matriz_final(1, 0, 0.0, 0.0)[1, 0] == pytest.approx(1.0)


def test_prob_avanza_con_la_vuelta_en_juego(par):
    """Ida 1-0 para el peor sembrado; vuelta en casa del mejor, 1-0 al 70': global 1-1."""
    ida = S.matriz_fija(1, 0)                                   # local = peor sembrado
    r70 = EJ.pronostico(par, 1.6, 1.0, 1, 0, 70, 2)
    cuartos = EJ.prob_avanza("cuartos", ida, r70["M"], False, True)
    final = EJ.prob_avanza("final", ida, r70["M"], False, True, (1.6, 1.0))
    # en cuartos el empate global es del mejor sembrado: avanza salvo que el rival anote más de lo que él anote
    assert cuartos["p_avanza_mejor"] == pytest.approx(cuartos["p_global_mejor"] + cuartos["p_global_empate"])
    assert cuartos["p_avanza_mejor"] > 0.7
    # en la final el empate global va a tiempos extra y penales: menos que en cuartos, más que sólo ganar el global
    assert final["p_global_mejor"] < final["p_avanza_mejor"] < cuartos["p_avanza_mejor"]
    assert final["p_avanza_mejor"] + final["p_avanza_peor"] == pytest.approx(1.0)
    # coincide con el cálculo directo del simulador
    directo = S.prob_serie(ida, r70["M"], False, True, "final", (1.6 / 3, 1.0 / 3))
    assert final["p_avanza_mejor"] == pytest.approx(directo["p_mejor"])
    # con la vuelta ya terminada 1-0 en cuartos avanza el mejor con certeza
    fin = EJ.pronostico(par, 1.6, 1.0, 1, 0, 90, 2, terminado=True)
    assert EJ.prob_avanza("cuartos", ida, fin["M"], False, True)["p_avanza_mejor"] == pytest.approx(1.0)
    # tiempos extra: ganando 1-0 el local casi lo tiene; en penales, moneda al aire
    assert EJ.prob_tiempos_extra(1, 0, 0.1, 0.1) > 0.9 and EJ.prob_tiempos_extra(0, 0, 0.0, 0.0) == pytest.approx(0.5)
    assert EJ.prob_tiempos_extra(0, 0, 0.3, 0.2, penales=True) == 0.5


# ==================================================================================================
# Simulador con partidos en juego
# ==================================================================================================
def test_acoplar_en_juego_respeta_el_marcador_y_la_distribucion():
    rng = np.random.default_rng(1)
    n = 60000
    lam_l, lam_v = 1.4 * np.exp(rng.normal(0, 0.1, n)), 1.1 * np.exp(rng.normal(0, 0.1, n))
    g0, h0 = S.marcadores(np.random.default_rng(2), lam_l, lam_v, -0.05)
    v = {"gl": 1, "gv": 0, "lam_rest_l": 0.5, "lam_rest_v": 0.7}
    a, b = S.acoplar_en_juego(np.random.default_rng(3), g0, h0, lam_l, lam_v, 0.0, v)
    assert a.min() >= 1 and b.min() >= 0
    assert (a - 1).mean() == pytest.approx(0.5, abs=0.015) and b.mean() == pytest.approx(0.7, abs=0.015)
    assert ((a == 1) & (b == 0)).mean() == pytest.approx(np.exp(-1.2), abs=0.01)
    assert ((a == g0) & (b == h0)).mean() > 0.3                  # conserva el sorteo normal lo más posible
    # al minuto 0 (lo que falta = todo) no cambia ni un marcador
    v0 = {"gl": 0, "gv": 0, "lam_rest_l": 1.4, "lam_rest_v": 1.1, "lam_l": 1.4, "lam_v": 1.1}
    a, b = S.acoplar_en_juego(np.random.default_rng(3), g0, h0, lam_l, lam_v, -0.05, v0)
    assert (a == g0).all() and (b == h0).all()
    # terminado: todas las simulaciones quedan en el marcador final
    a, b = S.acoplar_en_juego(np.random.default_rng(3), g0, h0, lam_l, lam_v, -0.05, {"gl": 2, "gv": 2, "lam_rest_l": 0, "lam_rest_v": 0})
    assert (a == 2).all() and (b == 2).all()


def test_simular_con_en_juego_respeta_el_marcador_minimo(df, pron):
    est = S.estado_torneo(df, TORNEO, CORTE, list(pron.equipos))
    pend = est["pendientes"]
    fila = pend[pend["id"] == ID_QUERETARO_MONTERREY].iloc[0]
    loc, vis = fila["local"], fila["visitante"]
    otros_vis = int(((pend["local"] == vis) | (pend["visitante"] == vis)).sum()) - 1
    kw = dict(df=df, corte=CORTE, n_sim=4000, n_muestras=200, semilla=5)
    base = S.simular(pron, **kw)
    d = {x["lam_l"]: x for x in pron.partidos(pend[pend["id"] == ID_QUERETARO_MONTERREY])}
    prev = next(iter(d.values()))
    # 3-0 definitivo: el local suma 3 puntos en todas las simulaciones y el visitante ninguno en ese partido
    r = S.simular(pron, en_juego={ID_QUERETARO_MONTERREY: {"gl": 3, "gv": 0, "lam_rest_l": 0.0, "lam_rest_v": 0.0}}, **kw)
    assert r["meta"]["en_juego"] == [ID_QUERETARO_MONTERREY]
    pe = {x["equipo"]: x for x in r["por_equipo"]}
    assert pe[loc]["pts_min"] >= pe[loc]["pts_actual"] + 3
    assert pe[vis]["pts_max"] <= pe[vis]["pts_actual"] + 3 * otros_vis
    # 0-2 al 80': el visitante gana o empata casi siempre; nunca baja de los puntos de un empate... ni el local sube de 1
    r = S.simular(pron, en_juego={ID_QUERETARO_MONTERREY: {"gl": 0, "gv": 2, "lam_rest_l": 0.2, "lam_rest_v": 0.2}}, **kw)
    pe2 = {x["equipo"]: x for x in r["por_equipo"]}
    b = {x["equipo"]: x for x in base["por_equipo"]}
    assert pe2[vis]["puntos_esperados"] > b[vis]["puntos_esperados"] + 1.0
    assert pe2[loc]["puntos_esperados"] < b[loc]["puntos_esperados"] - 0.5
    # al minuto 0 con las lambdas previas del partido la simulación es idéntica a la de base (mismos sorteos)
    r0 = S.simular(pron, en_juego={ID_QUERETARO_MONTERREY: {"gl": 0, "gv": 0, "lam_rest_l": prev["lam_l"], "lam_rest_v": prev["lam_v"],
                                                            "lam_l": prev["lam_l"], "lam_v": prev["lam_v"]}}, **kw)
    assert [(x["equipo"], x["p_clasifica"], x["p_campeon"]) for x in r0["por_equipo"]] == \
           [(x["equipo"], x["p_clasifica"], x["p_campeon"]) for x in base["por_equipo"]]
    # sin en_juego nada cambia respecto a no pasar el parámetro
    assert S.simular(pron, en_juego={}, **kw)["por_equipo"] == base["por_equipo"]
    assert base["meta"]["en_juego"] == []


def test_simular_con_la_vuelta_de_la_final_en_juego(df, pron):
    """Escenario CONSTRUIDO (como en test_simulador): final con la ida 1-0 para el peor sembrado y la vuelta en juego."""
    from test_simulador import _con_liguilla, _siembra
    s = _siembra(df)
    piernas = []
    for k, (m, p) in enumerate(((0, 7), (1, 6), (2, 5), (3, 4))):               # pasan 1, 2, 3 y 4
        piernas += [("cuartos", 1, s[p], s[m], 0, 0, None, None, f"2026-11-25T0{k}:00"),
                    ("cuartos", 2, s[m], s[p], 1, 0, None, None, f"2026-11-28T0{k}:00")]
    piernas += [("semifinal", 1, s[3], s[0], 2, 0, None, None, "2026-12-02T01:00"), ("semifinal", 2, s[0], s[3], 0, 0, None, None, "2026-12-05T01:00"),
                ("semifinal", 1, s[2], s[1], 1, 1, None, None, "2026-12-02T03:00"), ("semifinal", 2, s[1], s[2], 2, 2, None, None, "2026-12-05T03:00"),
                ("final", 1, s[3], s[1], 1, 0, None, None, "2026-12-10T01:00"),
                ("final", 2, s[1], s[3], None, None, None, None, "2026-12-13T01:00")]   # la vuelta: en casa del 2, sin jugar
    d = _con_liguilla(df, piernas)
    vuelta = 990000000 + len(piernas) - 1
    kw = dict(corte="2026-12-13T02:30:00Z", df=d, n_sim=20000, n_muestras=0, semilla=3, torneo=TORNEO)

    def campeon(en_juego):
        r = S.simular(pron, en_juego=en_juego, **kw)
        fin = next(x for x in r["series_reales"] if x["fase"] == "final")
        return {x["equipo"]: x["p_campeon"] for x in r["por_equipo"]}, fin, r

    # 1-0 al 80' de la vuelta: global 1-1; quedan pocos goles
    c, fin, r = campeon({vuelta: {"gl": 1, "gv": 0, "lam_rest_l": 0.2, "lam_rest_v": 0.12}})
    assert r["meta"]["en_juego"] == [vuelta] and fin["mejor"] == s[1] and not fin["decidida"]
    v = fin["piernas"][1]
    assert v["en_juego"] is True and (v["gl_vivo"], v["gv_vivo"]) == (1, 0) and not v["jugado"]
    assert c[s[1]] + c[s[3]] == pytest.approx(1.0)
    assert c[s[1]] == pytest.approx(fin["p_avanza_mejor"], abs=0.015)              # la simulación coincide con el cálculo exacto
    exacto = EJ.prob_avanza("final", S.matriz_fija(1, 0), EJ.matriz_final(1, 0, 0.2, 0.12), False, True, (v["lam_l"], v["lam_v"]))
    assert fin["p_avanza_mejor"] == pytest.approx(exacto["p_avanza_mejor"], abs=1e-9)
    assert 0.45 < fin["p_avanza_mejor"] < 0.75                                    # empatado el global, cerrando en casa y con poco tiempo
    # sin nada en juego (antes de la vuelta) el 2 va abajo 0-1: vale menos que con el 1-0 a favor
    c0, fin0, _ = campeon(None)
    assert c0[s[1]] < c[s[1]] and "en_juego" not in fin0["piernas"][1]
    # ya en tiempos extra, el local gana 1-0 el tiempo extra y no queda tiempo: campeón el local
    c, fin, _ = campeon({vuelta: {"gl": 1, "gv": 0, "lam_rest_l": 0.0, "lam_rest_v": 0.0,
                                  "extra": {"gl": 1, "gv": 0, "lam_rest_l": 0.0, "lam_rest_v": 0.0}}})
    assert c[s[1]] == pytest.approx(1.0) and fin["p_avanza_mejor"] == pytest.approx(1.0)
    # en penales: moneda al aire
    c, fin, _ = campeon({vuelta: {"gl": 1, "gv": 0, "lam_rest_l": 0.0, "lam_rest_v": 0.0,
                                  "extra": {"gl": 0, "gv": 0, "lam_rest_l": 0.0, "lam_rest_v": 0.0, "penales": True}}})
    assert fin["p_avanza_mejor"] == pytest.approx(0.5) and c[s[1]] == pytest.approx(0.5, abs=0.02)
    # ESPN ya dio al campeón (ganó el visitante en penales) y partidos.csv aún no lo sabe
    c, fin, _ = campeon({vuelta: {"gl": 1, "gv": 0, "lam_rest_l": 0.0, "lam_rest_v": 0.0, "avanza": s[3]}})
    assert c[s[3]] == 1.0 and fin["decidida"] and fin["ganador"] == s[3]


# ==================================================================================================
# ESPN -> forma interna
# ==================================================================================================
def test_normalizar_evento_real_y_estados():
    fin = vivo.normalizar_evento(evento("20261107", ID_ATLAS_PACHUCA))
    assert (fin["local"], fin["visitante"], fin["gl"], fin["gv"], fin["estado"]) == ("Atlas", "Pachuca", 1, 4, "final")
    assert (fin["minuto"], fin["anadido"], fin["periodo"]) == (90, 10, 2)
    goles = [j for j in fin["jugadas"] if j["clase"] == "gol"]
    assert [j["tipo"] for j in goles] == ["autogol", "gol", "gol", "penal", "gol"]
    assert goles[0]["lado"] == 1 and goles[0]["jugador"] == "Manuel Capasso"   # el autogol le cuenta a Pachuca
    assert (goles[-1]["min"], goles[-1]["anadido"]) == (90, 2)
    assert sum(1 for j in fin["jugadas"] if j["clase"] == "roja") == 1
    # nombres canónicos aunque ESPN diga «Tigres UANL» o «Pumas UNAM»
    assert vivo.normalizar_evento(evento("20261107", 401876906))["local"] == "Tigres"
    assert vivo.normalizar_evento(evento("20261107", ID_PUMAS_AMERICA))["local"] == "Pumas"
    pre = vivo.normalizar_evento(evento("20261114", ID_QUERETARO_MONTERREY))
    assert pre["estado"] == "programado" and pre["inicio"] == dt.datetime(2026, 11, 14, 23, 0, tzinfo=UTC)
    ev = evento("20261107", ID_PUMAS_AMERICA)
    juego = vivo.normalizar_evento(rebobinar(ev, 57))
    assert (juego["estado"], juego["periodo"], juego["minuto"], juego["gl"], juego["gv"]) == ("en_juego", 2, 57, 1, 1)
    agregado = vivo.normalizar_evento(rebobinar(ev, 45, reloj="45'+3'"))
    assert (agregado["estado"], agregado["minuto"], agregado["anadido"]) == ("en_juego", 45, 3)
    descanso = vivo.normalizar_evento(rebobinar(ev, 45, nombre="STATUS_HALFTIME", reloj="HT"))
    assert descanso["estado"] == "descanso" and descanso["minuto"] == 45
    pos = rebobinar(ev, estado="pre")
    pos["status"]["type"].update(name="STATUS_POSTPONED", state="post")
    assert vivo.normalizar_evento(pos)["estado"] == "pospuesto"
    assert vivo.normalizar_evento({"id": "1"}) is None            # un evento ilegible no tumba nada
    assert vivo._minuto("90'+4'", None) == (90, 4) and vivo._minuto("57'", None) == (57, None)
    assert vivo._minuto("HT", 2700.0) == (45, None) and vivo._minuto(None, None) == (None, None)


def test_dia_de_juego_y_dias_consultados():
    # un partido que arranca a las 21:10 de México sigue siendo «de hoy» a la 1 de la mañana
    assert vivo.dia_de_juego(dt.datetime(2026, 11, 8, 7, 0, tzinfo=UTC)) == dt.date(2026, 11, 7)
    assert vivo.dia_de_juego(dt.datetime(2026, 11, 8, 11, 0, tzinfo=UTC)) == dt.date(2026, 11, 8)
    pedidos = []

    def pedir(url):
        pedidos.append(url.rsplit("=", 1)[-1])
        return servir({"20261107": fixture("20261107"), "20261108": fixture("20261108")})(url)

    crudas, avisos = vivo.leer_hoy(dt.datetime(2026, 11, 8, 2, 0, tzinfo=UTC), pedir)
    assert pedidos == ["20261107", "20261108"] and avisos == []
    assert [c["id"] for c in crudas] == [ID_ATLAS_PACHUCA, ID_TOLUCA_MONTERREY, 401876906, ID_PUMAS_AMERICA] or \
        sorted(c["id"] for c in crudas) == sorted([ID_ATLAS_PACHUCA, ID_TOLUCA_MONTERREY, 401876906, ID_PUMAS_AMERICA])
    # si ESPN no responde el día principal es ErrorRed; si falla sólo el siguiente, se avisa y se sigue
    with pytest.raises(vivo.ErrorRed):
        vivo.leer_hoy(dt.datetime(2026, 11, 8, 2, 0, tzinfo=UTC), servir({"20261107": vivo.ErrorRed("sin red")}))
    crudas, avisos = vivo.leer_hoy(dt.datetime(2026, 11, 8, 2, 0, tzinfo=UTC),
                                   servir({"20261107": fixture("20261107"), "20261108": vivo.ErrorRed("sin red")}))
    assert len(crudas) == 4 and len(avisos) == 1


# ==================================================================================================
# Documento
# ==================================================================================================
def test_documento_cumple_el_contrato_y_pesa_poco(df, pron_7nov, par, tmp_path):
    f = fixture("20261107")
    f["events"] = [e if int(e["id"]) == ID_ATLAS_PACHUCA else
                   rebobinar(e, estado="pre") if int(e["id"]) == ID_PUMAS_AMERICA else rebobinar(e, 62)
                   for e in f["events"]]
    m = motor_7nov(df, pron_7nov, par, servir({"20261107": f}))
    doc = vivo.una_vez(m, ahora=dt.datetime(2026, 11, 8, 2, 2, tzinfo=UTC), salida=tmp_path / "vivo.json",
                       bitacora=vivo.Bitacora(tmp_path / "eventos.jsonl"))
    assert vivo.validar_documento(doc) == []
    peso = (tmp_path / "vivo.json").stat().st_size
    assert peso < 40 * 1024 and json.loads((tmp_path / "vivo.json").read_text(encoding="utf-8")) == doc
    # mismas llaves que el ejemplo del contrato (salidas/vivo_ejemplo.json)
    ej = json.loads((datos.RAIZ / "salidas" / "vivo_ejemplo.json").read_text(encoding="utf-8"))
    assert set(ej) - {"ejemplo"} <= set(doc)
    assert set(ej["partidos"][0]) <= set(doc["partidos"][0])
    assert set(ej["tabla"][0]) == set(doc["tabla"][0])
    assert set(ej["proyeccion"]) <= set(doc["proyeccion"])
    assert set(ej["proyeccion"]["campeon"][0]) == set(doc["proyeccion"]["campeon"][0])
    assert set(ej["siguiente"]) == set(doc["siguiente"])
    por_id = {p["id"]: p for p in doc["partidos"]}
    assert doc["estado"] == "en_juego" and doc["dia"] == "2026-11-07" and len(doc["partidos"]) == 4
    assert [p["inicio_utc"] for p in doc["partidos"]] == sorted(p["inicio_utc"] for p in doc["partidos"])
    # terminado: marcador real, eventos con su parcial, sin pronóstico al momento
    fin = por_id[ID_ATLAS_PACHUCA]
    assert (fin["estado"], fin["gl"], fin["gv"], fin["minuto"], fin["anadido"], fin["vivo"]) == ("final", 1, 4, 90, 10, None)
    assert [e["tipo"] for e in fin["eventos"]] == ["autogol", "gol", "gol", "penal", "roja", "gol"]
    assert fin["eventos"][0] == {"min": 5, "anadido": None, "tipo": "autogol", "equipo": "Pachuca", "jugador": "Manuel Capasso", "marcador": "0-1"}
    assert fin["eventos"][-1]["marcador"] == "1-4" and fin["eventos"][-1]["anadido"] == 2 and fin["rojas_l"] == 1
    # en juego con expulsión del visitante al 61': Toluca 3-0 Monterrey al 62'
    tm = por_id[ID_TOLUCA_MONTERREY]
    assert (tm["estado"], tm["periodo"], tm["minuto"], tm["gl"], tm["gv"], tm["rojas_l"], tm["rojas_v"]) == ("en_juego", 2, 62, 3, 0, 0, 1)
    assert set(ej["partidos"][0]["vivo"]) == set(tm["vivo"]) and set(ej["partidos"][0]["previo"]) <= set(tm["previo"])
    assert tm["vivo"]["p_local"] > 0.97 and abs(sum(tm["vivo"][k] for k in ("p_local", "p_empate", "p_visitante")) - 1) < 3e-4
    assert tm["vivo"]["marcador_final"]["gl"] >= 3 and tm["reloj_utc"] is not None
    assert tm["vivo"]["goles_restantes_l"] > tm["vivo"]["goles_restantes_v"]
    assert abs(sum(tm["previo"][k] for k in ("p_local", "p_empate", "p_visitante")) - 1) < 3e-4
    # sin empezar
    pa = por_id[ID_PUMAS_AMERICA]
    assert (pa["estado"], pa["gl"], pa["gv"], pa["minuto"], pa["vivo"], pa["eventos"]) == ("programado", None, None, None, None, [])
    assert pa["previo"] is not None and doc["siguiente"]["id"] == ID_PUMAS_AMERICA
    # tabla al momento: 18 equipos, los que juegan marcados y con un partido más que antes del día
    assert [f_["pos"] for f_ in doc["tabla"]] == list(range(1, 19))
    jugando = {f_["equipo"] for f_ in doc["tabla"] if f_["en_juego"]}
    assert jugando == {"Toluca", "Monterrey", "Tigres", "Cruz Azul"}
    antes = S.tabla_actual(S.estado_torneo(df, TORNEO, pd.Timestamp("2026-11-07T22:00:00Z"))).set_index("equipo")
    ahora = {f_["equipo"]: f_ for f_ in doc["tabla"]}
    for e in ("Toluca", "Monterrey", "Tigres", "Cruz Azul", "Atlas", "Pachuca"):
        assert ahora[e]["PJ"] == antes.loc[e, "PJ"] + 1
    assert ahora["Toluca"]["PTS"] == antes.loc["Toluca", "PTS"] + 3 and ahora["Monterrey"]["PTS"] == antes.loc["Monterrey", "PTS"]
    assert ahora["Pachuca"]["PTS"] == antes.loc["Pachuca", "PTS"] + 3 and ahora["Pumas"]["PJ"] == antes.loc["Pumas", "PJ"]
    assert sum(f_["cambio"] for f_ in doc["tabla"]) == 0
    assert "en juego" in doc["tabla_nota"]
    # proyección al momento con los tres partidos tocados
    pr = doc["proyeccion"]
    assert sorted(pr["partidos_considerados"]) == sorted([ID_ATLAS_PACHUCA, ID_TOLUCA_MONTERREY, 401876906])
    assert pr["n_sim"] == 600 and pr["campeon"] and all(0 <= d["p"] <= 1 for d in pr["campeon"] + pr["clasifica"])
    assert abs(sum(d["p"] for d in pr["campeon"]) - 1.0) < 0.02
    cl = {d["equipo"]: d for d in pr["clasifica"]}
    if "Monterrey" in cl:                                       # perdiendo 3-0 con uno menos no puede mejorar
        assert cl["Monterrey"]["delta"] <= 0.02
    assert doc["series"] == [] and all(p["serie"] is None for p in doc["partidos"])


def test_documento_de_un_dia_terminado_y_de_un_dia_sin_partidos(df, pron_7nov, par):
    m = motor_7nov(df, pron_7nov, par, servir({"20261107": fixture("20261107"), "20261108": fixture("20261108")}))
    doc = vivo.una_vez(m, ahora=dt.datetime(2026, 11, 8, 8, 0, tzinfo=UTC), salida=None)
    assert vivo.validar_documento(doc) == []
    assert doc["estado"] == "terminado_hoy" and len(doc["partidos"]) == 4 and all(p["vivo"] is None for p in doc["partidos"])
    assert {(p["local"], p["gl"], p["gv"], p["visitante"]) for p in doc["partidos"]} == {
        ("Atlas", 1, 4, "Pachuca"), ("Tigres", 2, 3, "Cruz Azul"), ("Toluca", 4, 0, "Monterrey"), ("Pumas", 2, 2, "América")}
    for p in doc["partidos"]:
        goles = [e for e in p["eventos"] if e["tipo"] != "roja"]
        assert goles[-1]["marcador"] == f"{p['gl']}-{p['gv']}"
    # hoy (10-nov) no hay partidos: sin_partidos y el siguiente sale del calendario previo
    actual = {"meta": {"torneo": TORNEO, "corte_utc": "2026-11-10T21:49:09+00:00"},
              "tabla": [{"pos": 1, "equipo": "Cruz Azul", "PJ": 16, "PTS": 32, "DG": 11, "GF": 37}],
              "proyeccion": {"n_sim": 20000, "regular_completa": False,
                             "tabla_final": [{"equipo": "Cruz Azul", "p_clasifica": 1.0}, {"equipo": "Pachuca", "p_clasifica": 0.42}],
                             "campeon": [{"equipo": "Cruz Azul", "prob": 0.26}, {"equipo": "Pachuca", "prob": 0.02}]},
              "pendientes": [{"id": 401877054, "fecha_utc": "2026-11-21T01:00:00+00:00", "local": "Puebla", "visitante": "Atlético San Luis",
                              "fase": "regular", "etiqueta": "Jornada 17", "pierna": None, "lam_l": 1.33, "lam_v": 1.37, "rho": -0.05,
                              "p_local": 0.355, "p_empate": 0.271, "p_visitante": 0.374, "marcador": {"gl": 1, "gv": 1, "prob": 0.13}},
                             {"id": ID_QUERETARO_MONTERREY, "fecha_utc": "2026-11-14T23:00:00+00:00", "local": "Querétaro",
                              "visitante": "Monterrey", "fase": "regular", "etiqueta": "Jornada 7 (reprogramado)", "pierna": None,
                              "lam_l": 1.22, "lam_v": 1.49, "rho": -0.05, "p_local": 0.304, "p_empate": 0.268, "p_visitante": 0.428,
                              "marcador": {"gl": 1, "gv": 1, "prob": 0.13}}],
              "liguilla": {"torneo": None}}
    m = vivo.Motor(actual=actual, sellos={}, parametros=par, proyectar=False,
                   pedir=servir({"20261110": fixture("20261110"), "20261111": fixture("20261111")}))
    doc = vivo.una_vez(m, ahora=dt.datetime(2026, 11, 10, 22, 0, tzinfo=UTC), salida=None)
    assert vivo.validar_documento(doc) == []
    assert doc["estado"] == "sin_partidos" and doc["partidos"] == [] and doc["series"] == []
    assert doc["siguiente"] == {"id": ID_QUERETARO_MONTERREY, "inicio_utc": "2026-11-14T23:00:00Z", "local": "Querétaro",
                                "visitante": "Monterrey"}
    assert doc["tabla"] == [{"pos": 1, "equipo": "Cruz Azul", "PJ": 16, "PTS": 32, "DG": 11, "GF": 37, "cambio": 0, "en_juego": False}]
    assert doc["proyeccion"]["campeon"][0] == {"equipo": "Cruz Azul", "p": 0.26, "delta": 0.0}
    assert doc["proyeccion"]["clasifica"] == [{"equipo": "Pachuca", "p": 0.42, "delta": 0.0}]
    # el día del partido, antes de empezar: «previo» con su pronóstico sellado
    m = vivo.Motor(actual=actual, parametros=par, proyectar=False, pedir=servir({"20261114": fixture("20261114")}),
                   sellos={ID_QUERETARO_MONTERREY: {"id": ID_QUERETARO_MONTERREY, "sellado_utc": "2026-11-14T07:20:00+00:00", "fase": "regular",
                                                    "pierna": None, "lam_l": 1.25, "lam_v": 1.45, "rho": -0.05, "p_l": 0.31, "p_e": 0.27,
                                                    "p_v": 0.42, "marcador": {"gl": 1, "gv": 1, "prob": 0.13}}})
    doc = vivo.una_vez(m, ahora=dt.datetime(2026, 11, 14, 22, 50, tzinfo=UTC), salida=None)
    assert doc["estado"] == "previo" and doc["siguiente"]["id"] == ID_QUERETARO_MONTERREY
    p = doc["partidos"][0]
    assert p["etiqueta"] == "Jornada 7 (reprogramado)" and p["previo"]["lam_l"] == 1.25 and "origen" not in p["previo"]   # manda el sello


def _serie(fase="cuartos", ida_jugada=True):
    return {"llave": "C1" if fase == "cuartos" else "F", "fase": fase, "real": True, "viene_de": None,
            "mejor": {"equipo": "Cruz Azul", "siembra": 1}, "peor": {"equipo": "Tijuana", "siembra": 8},
            "piernas": [
                {"pierna": 1, "nombre": "Ida", "id": 9001, "local": "Tijuana", "visitante": "Cruz Azul", "jugado": ida_jugada,
                 "gl": 1 if ida_jugada else None, "gv": 0 if ida_jugada else None, "lam_l": 1.4, "lam_v": 1.5},
                {"pierna": 2, "nombre": "Vuelta", "id": 9002, "local": "Cruz Azul", "visitante": "Tijuana", "jugado": False,
                 "gl": None, "gv": None, "lam_l": 2.0, "lam_v": 0.9}],
            "p_avanza_mejor": 0.62, "p_avanza_peor": 0.38, "favorito": "Cruz Azul", "p_favorito": 0.62, "decidida": False,
            "ganador": None}


def _cruda(pid, local, visitante, estado, minuto, gl, gv, periodo=2, inicio="2026-11-29T01:00:00Z", gana=None):
    jug = [{"clase": "gol", "tipo": "gol", "lado": 0, "min": 20 + k, "anadido": None, "seg": (20 + k) * 60.0, "jugador": f"L{k}", "jid": ""}
           for k in range(gl or 0)] + \
          [{"clase": "gol", "tipo": "gol", "lado": 1, "min": 30 + k, "anadido": None, "seg": (30 + k) * 60.0, "jugador": f"V{k}", "jid": ""}
           for k in range(gv or 0)]
    return {"id": pid, "inicio": vivo.de_iso(inicio), "local": local, "visitante": visitante, "estado": estado, "estado_espn": "",
            "periodo": periodo, "minuto": minuto, "anadido": None, "segundos": (minuto or 0) * 60.0 - 20, "gl": gl, "gv": gv,
            "tanda_l": None, "tanda_v": None, "gana": gana, "pierna": 2, "slug": None, "jugadas": sorted(jug, key=lambda j: j["seg"])}


def test_series_de_liguilla_al_momento(par):
    def motor(fase):
        actual = {"meta": {"torneo": TORNEO}, "tabla": [], "pendientes": [],
                  "proyeccion": {"n_sim": 20000, "regular_completa": True, "tabla_final": [], "campeon": [{"equipo": "Cruz Azul", "prob": 0.3}]},
                  "liguilla": {"torneo": {"rondas": [{"fase": fase, "series": [_serie(fase)]}]}}}
        sello = {9002: {"id": 9002, "sellado_utc": "2026-11-28T07:20:00+00:00", "fecha_utc": "2026-11-29T01:00:00+00:00", "fase": fase,
                        "pierna": 2, "lam_l": 2.0, "lam_v": 0.9, "rho": 0.0, "p_l": 0.64, "p_e": 0.2, "p_v": 0.16,
                        "marcador": {"gl": 2, "gv": 0, "prob": 0.1}}}
        return vivo.Motor(actual=actual, sellos=sello, parametros=par, proyectar=False)

    ahora = dt.datetime(2026, 11, 29, 2, 30, tzinfo=UTC)
    # cuartos: ida 1-0 Tijuana; vuelta 1-0 Cruz Azul al 70' -> global 1-1, el empate es del mejor sembrado
    doc = motor("cuartos").documento([_cruda(9002, "Cruz Azul", "Tijuana", "en_juego", 70, 1, 0)], ahora)
    assert vivo.validar_documento(doc) == []
    s = doc["series"][0]
    assert (s["llave"], s["global_mejor"], s["global_peor"], s["al_momento"], s["decidida"]) == ("C1", 1, 1, True, False)
    assert [(p["pierna"], p["estado"], p["gl"], p["gv"]) for p in s["piernas"]] == [(1, "final", 1, 0), (2, "en_juego", 1, 0)]
    r70 = EJ.pronostico(par, 2.0, 0.9, 1, 0, 70, 2, en_curso=True)
    esperado = EJ.prob_avanza("cuartos", S.matriz_fija(1, 0), r70["M"], False, True)["p_avanza_mejor"]
    assert s["p_avanza_mejor"] == pytest.approx(esperado, abs=1e-4) and s["p_avanza_mejor"] > 0.8
    assert s["delta_avanza_mejor"] == pytest.approx(s["p_avanza_mejor"] - 0.62, abs=1e-4)
    p = doc["partidos"][0]
    assert p["fase"] == "cuartos" and p["etiqueta"] == "Cuartos de final, vuelta"
    assert p["serie"] == {"llave": "C1", "mejor": "Cruz Azul", "peor": "Tijuana", "global_mejor": 1, "global_peor": 1,
                          "p_avanza_mejor": s["p_avanza_mejor"], "p_avanza_peor": s["p_avanza_peor"]}
    # el mismo estado en una final vale menos: hay tiempos extra y penales
    sf = motor("final").documento([_cruda(9002, "Cruz Azul", "Tijuana", "en_juego", 70, 1, 0)], ahora)["series"][0]
    assert sf["p_avanza_mejor"] < s["p_avanza_mejor"]
    # si Tijuana empata 1-1 la vuelta (global 1-2) las cosas se voltean
    s2 = motor("cuartos").documento([_cruda(9002, "Cruz Azul", "Tijuana", "en_juego", 85, 1, 1)], ahora)["series"][0]
    assert s2["p_avanza_mejor"] < 0.3 and s2["favorito"] == "Tijuana" and (s2["global_mejor"], s2["global_peor"]) == (1, 2)
    # terminada 1-0 la vuelta: global 1-1, avanza el mejor sembrado (cuartos)
    s3 = motor("cuartos").documento([_cruda(9002, "Cruz Azul", "Tijuana", "final", 90, 1, 0)], ahora)["series"][0]
    assert (s3["decidida"], s3["ganador"], s3["p_avanza_mejor"]) == (True, "Cruz Azul", 1.0)
    # en la final un 1-1 global no se decide hasta que ESPN diga quién ganó el tiempo extra o los penales
    s4 = motor("final").documento([_cruda(9002, "Cruz Azul", "Tijuana", "final", 90, 1, 0)], ahora)["series"][0]
    assert s4["decidida"] is False and 0.3 < s4["p_avanza_mejor"] < 0.7
    s5 = motor("final").documento([_cruda(9002, "Cruz Azul", "Tijuana", "final", 120, 1, 0, gana="visitante")], ahora)["series"][0]
    assert (s5["decidida"], s5["ganador"], s5["p_avanza_mejor"]) == (True, "Tijuana", 0.0)
    # sin partido de la serie hoy se repite lo que ya decía actual.json
    s6 = motor("cuartos").documento([], ahora)["series"][0]
    assert (s6["al_momento"], s6["p_avanza_mejor"], s6["delta_avanza_mejor"], s6["global_mejor"], s6["global_peor"]) == (False, 0.62, 0.0, 0, 1)


def test_descanso_pausas_y_fin_del_tiempo_regular(par):
    sello = {9002: {"id": 9002, "sellado_utc": "2026-11-28T07:20:00+00:00", "fecha_utc": "2026-11-29T01:00:00+00:00", "fase": "regular",
                    "pierna": None, "lam_l": 2.0, "lam_v": 0.9, "rho": 0.0, "p_l": 0.64, "p_e": 0.2, "p_v": 0.16,
                    "marcador": {"gl": 2, "gv": 0, "prob": 0.1}}}
    actual = {"meta": {"torneo": TORNEO}, "tabla": [], "pendientes": [], "proyeccion": {}, "liguilla": {}}
    ahora = dt.datetime(2026, 11, 29, 2, 0, tzinfo=UTC)

    def partido(**kw):
        c = _cruda(9002, "Cruz Azul", "Tijuana", "descanso", kw.pop("minuto"), 1, 1, periodo=kw.pop("periodo"))
        c.update(kw)
        m = vivo.Motor(actual=actual, sellos=sello, parametros=par, proyectar=False)
        return m.documento([c], ahora)["partidos"][0]

    # medio tiempo: ESPN puede decir periodo 1 o 2; el documento siempre dice periodo 1, minuto 45
    for per in (1, 2):
        p = partido(minuto=45, periodo=per, medio_tiempo=True)
        assert (p["estado"], p["periodo"], p["minuto"], p["anadido"]) == ("descanso", 1, 45, None) and p["reloj_utc"] is not None
        assert p["vivo"]["goles_restantes_l"] == pytest.approx(2.0 * par.curva.parte_2t, abs=0.006)
    # pausa a media cancha (lluvia) al 30': no es el descanso, falta lo que falta desde el 30'
    p = partido(minuto=30, periodo=1, medio_tiempo=False)
    assert (p["periodo"], p["minuto"]) == (1, 30)
    assert p["vivo"]["goles_restantes_l"] == pytest.approx(2.0 * par.curva.restante(30, 1, en_curso=True), abs=0.006)
    # pausa tras los 90 minutos (antes de un tiempo extra): el resultado a 90 minutos ya es definitivo
    p = partido(minuto=90, periodo=2, medio_tiempo=False)
    assert p["vivo"]["p_empate"] == 1.0 and p["vivo"]["goles_restantes_l"] == 0.0
    # sólo en la final esa pausa anuncia tiempos extra
    antes = dict(p, estado="en_juego", minuto=88)
    assert [e["tipo"] for e in vivo.detectar_eventos({9002: antes}, [p])] == []
    assert [e["tipo"] for e in vivo.detectar_eventos({9002: dict(antes, fase="final")}, [dict(p, fase="final")])] == ["tiempos_extra"]
    # tiempos extra en juego: el marcador a 90' (1-1) queda fijo aunque ESPN ya sume el gol del tiempo extra
    c = _cruda(9002, "Cruz Azul", "Tijuana", "en_juego", 100, 1, 1, periodo=3)
    c["jugadas"].append({"clase": "gol", "tipo": "gol", "lado": 0, "min": 98, "anadido": None, "seg": 98 * 60.0, "jugador": "X", "jid": ""})
    c["gl"] = 2
    p = vivo.Motor(actual=actual, sellos=sello, parametros=par, proyectar=False).documento([c], ahora)["partidos"][0]
    assert (p["gl"], p["gv"], p["periodo"]) == (2, 1, 3) and p["vivo"]["p_empate"] == 1.0


# ==================================================================================================
# Eventos, repetir, esperar, observar
# ==================================================================================================
def _p(estado, gl=None, gv=None, periodo=None, minuto=None, eventos=(), rl=0, rv=0):
    return {"id": 7, "local": "Pumas", "visitante": "América", "estado": estado, "gl": gl, "gv": gv, "periodo": periodo,
            "minuto": minuto, "rojas_l": rl, "rojas_v": rv, "eventos": list(eventos)}


def test_detectar_eventos():
    g1 = {"min": 3, "anadido": None, "tipo": "gol", "equipo": "América", "jugador": "Zendejas", "marcador": "0-1"}
    g2 = {"min": 45, "anadido": 2, "tipo": "penal", "equipo": "Pumas", "jugador": "Huerta", "marcador": "1-1"}
    r1 = {"min": 40, "anadido": None, "tipo": "roja", "equipo": "América", "jugador": "Bueno", "marcador": "0-1"}
    pre, j1 = _p("programado"), _p("en_juego", 0, 0, 1, 1)
    assert vivo.detectar_eventos({}, [j1]) == []                                  # sin foto anterior no se anuncia nada
    assert [e["tipo"] for e in vivo.detectar_eventos({7: pre}, [pre])] == []
    evs = vivo.detectar_eventos({7: pre}, [j1])
    assert [(e["tipo"], e["texto"]) for e in evs] == [("inicio", "Arranca Pumas vs América")]
    # gol, roja y gol entre dos consultas: salen en el orden de las jugadas, con su texto
    j2 = _p("en_juego", 1, 1, 1, 45, [g1, r1, g2], rv=1)
    evs = vivo.detectar_eventos({7: j1}, [j2])
    assert [e["tipo"] for e in evs] == ["gol", "roja", "gol"]
    assert evs[0]["texto"] == "Gol de América (3'): Zendejas. Pumas 0-1 América"
    assert evs[1]["texto"] == "Expulsión en América (40'): Bueno. Pumas 1-1 América"
    assert evs[2]["texto"] == "Gol de Pumas de penal (45'+2'): Huerta. Pumas 1-1 América" and evs[2]["marcador"] == "1-1"
    # ESPN movió el marcador antes de publicar la jugada
    assert vivo.detectar_eventos({7: j1}, [_p("en_juego", 1, 0, 1, 9)])[0]["texto"] == "Gol de Pumas. Pumas 1-0 América"
    # gol anulado o marcador corregido
    evs = vivo.detectar_eventos({7: j2}, [_p("en_juego", 0, 1, 2, 50, [g1, r1], rv=1)])
    assert [e["tipo"] for e in evs] == ["gol_anulado", "segundo_tiempo"] and "antes 1-1" in evs[0]["texto"]
    # descanso, segundo tiempo, final (si se pierde el descanso por un fallo de red sólo avisa del segundo tiempo)
    d = _p("descanso", 1, 1, 1, 45, [g1, r1, g2], rv=1)
    s = _p("en_juego", 1, 1, 2, 46, [g1, r1, g2], rv=1)
    fin = _p("final", 1, 1, 2, 90, [g1, r1, g2], rv=1)
    assert [e["tipo"] for e in vivo.detectar_eventos({7: j2}, [d])] == ["descanso"]
    assert [e["tipo"] for e in vivo.detectar_eventos({7: d}, [s])] == ["segundo_tiempo"]
    assert [e["tipo"] for e in vivo.detectar_eventos({7: j2}, [s])] == ["segundo_tiempo"]
    assert [(e["tipo"], e["texto"]) for e in vivo.detectar_eventos({7: s}, [fin])] == [("final", "Final: Pumas 1-1 América")]
    assert vivo.detectar_eventos({7: fin}, [fin]) == []
    # final de la liguilla: tiempos extra y penales
    te = _p("en_juego", 1, 1, 3, 95, [g1, r1, g2], rv=1)
    pen = _p("en_juego", 1, 1, 5, 120, [g1, r1, g2], rv=1)
    assert [e["tipo"] for e in vivo.detectar_eventos({7: s}, [te])] == ["tiempos_extra"]
    assert [e["tipo"] for e in vivo.detectar_eventos({7: te}, [pen])] == ["penales"]
    fin_pen = dict(fin, periodo=5, minuto=120, penales={"l": 4, "v": 3})
    assert vivo.detectar_eventos({7: pen}, [fin_pen])[0]["texto"] == "Final: Pumas 1-1 América (penales 4-3)"
    assert [e["tipo"] for e in vivo.detectar_eventos({7: pre}, [_p("pospuesto")])] == ["pospuesto"]
    # todo de golpe (se cayó la red dos horas): inicio, goles, roja y final
    assert [e["tipo"] for e in vivo.detectar_eventos({7: pre}, [fin])] == ["inicio", "gol", "roja", "gol", "final"]


def test_repetir_genera_los_eventos_de_un_partido_conocido(df, tmp_path):
    """Atlas 4-3 Puebla (25-oct-2026): goles al 1', 20', 60' (autogol), 63', 68', 79' y 84'; roja al 78'."""
    fila = df[df["id"] == ID_ATLAS_PUEBLA].iloc[0]
    assert (fila["local"], int(fila["gl"]), int(fila["gv"]), fila["visitante"]) == ("Atlas", 4, 3, "Puebla")
    corte = fila["fecha_utc"] - pd.Timedelta(minutes=1)
    salida = tmp_path / "rep.json"
    docs = []
    original = vivo.escribir_json

    def espia(doc, ruta):
        docs.append(copy.deepcopy(doc))
        return original(doc, ruta)

    vivo.escribir_json = espia
    try:
        r = vivo.repetir(ID_ATLAS_PUEBLA, velocidad=0, salida=salida, n_sim=400, pron=Pronosticador(corte=corte, partidos=df), df=df)
    finally:
        vivo.escribir_json = original
    evs = vivo.leer_eventos(tmp_path / "rep_eventos.jsonl")
    assert [e["n"] for e in evs] == list(range(1, len(evs) + 1)) and r["eventos"] == len(evs) == 12
    assert [e["tipo"] for e in evs] == ["inicio", "gol", "gol", "descanso", "segundo_tiempo", "gol", "gol", "gol", "roja", "gol", "gol", "final"]
    assert [e["marcador"] for e in evs if e["tipo"] == "gol"] == ["1-0", "1-1", "1-2", "2-2", "3-2", "4-2", "4-3"]
    assert evs[1]["texto"] == "Gol de Atlas (1'): Florián Monzón. Atlas 1-0 Puebla"
    assert "(autogol)" in evs[5]["texto"] and evs[8]["texto"].startswith("Expulsión en Puebla (78')")
    assert evs[-1]["texto"] == "Final: Atlas 4-3 Puebla"
    # documentos: todos válidos, de prueba, con el minuto que avanza y el pronóstico al momento
    assert len(docs) == r["documentos"] >= 25 and all(d.get("prueba") is True for d in docs)
    assert all(vivo.validar_documento(d) == [] for d in docs)
    assert [d["estado"] for d in docs][0] == "previo" and docs[-1]["estado"] == "terminado_hoy"
    assert "descanso" in [d["estado"] for d in docs]
    juego = [d["partidos"][0] for d in docs if d["partidos"][0]["estado"] == "en_juego"]
    minutos = [(p["periodo"], p["minuto"], p["anadido"] or 0) for p in juego]
    assert minutos == sorted(minutos) and all(p["vivo"] is not None for p in juego)
    ultimo = json.loads(salida.read_text(encoding="utf-8"))
    p = ultimo["partidos"][0]
    assert (p["estado"], p["gl"], p["gv"], p["rojas_v"], p["vivo"]) == ("final", 4, 3, 1, None)
    assert ultimo["ultimo_evento"]["tipo"] == "final" and ultimo["ultimo_evento"]["n"] == 12
    assert p["previo"]["origen"] == "modelo al corte (no sellado)"            # ese partido no tiene sello
    # con el 4-2 al 80' y uno menos, Puebla casi no tiene cómo ganar; la tabla al momento le da los 3 a Atlas
    al80 = next(d for d in docs if d["partidos"][0]["estado"] == "en_juego" and d["partidos"][0]["minuto"] == 80)
    assert al80["partidos"][0]["vivo"]["p_local"] > 0.9 and al80["proyeccion"]["partidos_considerados"] == [ID_ATLAS_PUEBLA]
    atlas = next(f for f in al80["tabla"] if f["equipo"] == "Atlas")
    antes = S.tabla_actual(S.estado_torneo(df, TORNEO, corte)).set_index("equipo")
    assert atlas["en_juego"] and atlas["PTS"] == antes.loc["Atlas", "PTS"] + 3
    with pytest.raises(ValueError):
        vivo.repetir(ID_QUERETARO_MONTERREY if df[df["id"] == ID_QUERETARO_MONTERREY]["estado"].iloc[0] != "jugado" else 1, velocidad=0,
                     salida=tmp_path / "x.json", df=df)


def test_esperar_devuelve_el_evento_correcto(tmp_path):
    ruta, candado = tmp_path / "eventos.jsonl", tmp_path / "observar.lock"
    bit = vivo.Bitacora(ruta)
    ahora = dt.datetime(2026, 11, 22, 1, 0, tzinfo=UTC)
    bit.anotar([{"tipo": "inicio", "partido_id": 1, "texto": "Arranca A vs B"}, {"tipo": "gol", "partido_id": 1, "texto": "Gol de A"},
                {"tipo": "refresco", "partido_id": None, "texto": "Refresco"}], ahora)
    assert vivo.Bitacora(ruta).n == 3                              # la numeración sigue al último del archivo
    assert bit.ultimo_del_dia(vivo.dia_de_juego(ahora))["tipo"] == "gol"         # el refresco no cuenta como último evento
    assert bit.ultimo_del_dia(dt.date(2026, 11, 30)) is None
    f = vivo._candado(candado)                                     # hace de `observar` corriendo
    assert f is not None and vivo._candado(candado) is None and vivo.observador_activo(candado)
    try:
        out = io.StringIO()
        assert vivo.esperar(1, 5, ruta, candado, pausa=0.05, salida=out) == 0
        lineas = out.getvalue().strip().splitlines()
        assert len(lineas) == 1                                    # UNA línea
        d = json.loads(lineas[0])
        assert (d["n"], d["tipo"], d["texto"], d["pendientes"], d["ultimo_n"]) == (2, "gol", "Gol de A", 1, 3)
        out = io.StringIO()
        assert vivo.esperar(0, 5, ruta, candado, pausa=0.05, salida=out) == 0 and json.loads(out.getvalue())["n"] == 1
        out = io.StringIO()
        assert vivo.esperar(3, 0.3, ruta, candado, pausa=0.05, salida=out) == 4       # nada nuevo y `observar` sigue: se agota
        assert json.loads(out.getvalue())["agotado"] is True
    finally:
        f.close()
    assert not vivo.observador_activo(candado)
    out = io.StringIO()
    assert vivo.esperar(3, 5, ruta, candado, pausa=0.05, salida=out) == 3             # `observar` ya terminó y no hay más
    assert json.loads(out.getvalue()) == {"terminado": True, "desde": 3, "ultimo_n": 3}
    out = io.StringIO()
    assert vivo.esperar(2, 5, ruta, candado, pausa=0.05, salida=out) == 0             # aunque ya terminó, entrega lo pendiente
    assert json.loads(out.getvalue())["n"] == 3


class Guion:
    """Reloj, pausas y respuestas de ESPN falsos para correr `observar` de corrido."""

    def __init__(self, pasos):
        self.pasos, self.i, self.pedidos = pasos, 0, 0

    def reloj(self):
        return vivo.de_iso(self.pasos[min(self.i, len(self.pasos) - 1)][0])

    def dormir(self, _seg):
        self.i += 1

    def pedir(self, url):
        self.pedidos += 1
        r = self.pasos[min(self.i, len(self.pasos) - 1)][1]
        if isinstance(r, Exception):
            raise r
        return {"events": [r]} if url.endswith("20261107") else {"events": []}


def test_observar_de_corrido(df, par, tmp_path):
    """Pumas 2-2 América (7-nov) visto por `observar`: antes, primer tiempo, un fallo de red, descanso, segundo tiempo y final."""
    ev = evento("20261107", ID_PUMAS_AMERICA)
    pasos = [("2026-11-08T03:00:00Z", rebobinar(ev, estado="pre")),
             ("2026-11-08T03:13:30Z", rebobinar(ev, 3)),                        # 0-1 (Zendejas 3')
             ("2026-11-08T03:16:00Z", vivo.ErrorRed("sin red (prueba)")),
             ("2026-11-08T03:40:00Z", rebobinar(ev, 30)),                       # 1-1 (Huerta 4')
             ("2026-11-08T04:00:00Z", rebobinar(ev, 45, nombre="STATUS_HALFTIME", reloj="HT")),
             ("2026-11-08T04:17:00Z", rebobinar(ev, 50)),
             ("2026-11-08T04:42:00Z", rebobinar(ev, 75)),                       # 1-2 (penal al 72')
             ("2026-11-08T05:10:00Z", ev),                                      # final 2-2 (penal al 77')
             ("2026-11-08T05:16:00Z", ev),
             ("2026-11-08T05:21:00Z", ev)]                                      # 11 minutos después del final: termina
    g = Guion(pasos)
    corte = pd.Timestamp("2026-11-08T03:00:00Z")
    motor = vivo.Motor(n_sim=400, n_muestras=40, pron=Pronosticador(corte=corte, partidos=df), df=df, corte=corte.to_pydatetime(),
                       sellos={}, parametros=par, pedir=g.pedir)
    salida, ruta, candado = tmp_path / "vivo.json", tmp_path / "eventos.jsonl", tmp_path / "observar.lock"
    # con el candado tomado no arranca un segundo observador
    f = vivo._candado(candado)
    assert vivo.observar(None, motor, salida, ruta, candado, dormir=g.dormir, reloj=g.reloj) == 2 and g.pedidos == 0
    f.close()
    cod = vivo.observar(None, motor, salida, ruta, candado, dormir=g.dormir, reloj=g.reloj, max_ciclos=40)
    assert cod == 0 and g.i == len(pasos) - 1                      # terminó solo, 10 minutos después del final
    assert not vivo.observador_activo(candado)
    evs = vivo.leer_eventos(ruta)
    assert [e["tipo"] for e in evs] == ["inicio", "gol", "gol", "descanso", "segundo_tiempo", "gol", "gol", "final"]
    assert [e["n"] for e in evs] == list(range(1, 9))
    assert evs[1]["texto"] == "Gol de América (3'): Alejandro Zendejas. Pumas 0-1 América"
    assert evs[5]["texto"] == "Gol de América de penal (72'): Henry Martín. Pumas 1-2 América"
    doc = json.loads(salida.read_text(encoding="utf-8"))
    assert vivo.validar_documento(doc) == [] and doc["estado"] == "terminado_hoy"
    assert doc["ultimo_evento"]["tipo"] == "final" and doc["ultimo_evento"]["n"] == 8
    assert doc["partidos"][0]["gl"] == 2 and doc["partidos"][0]["gv"] == 2
    latido = json.loads(candado.read_text(encoding="utf-8"))
    assert latido["ultimo_evento_n"] == 8 and latido["estado"] == "terminado_hoy"
    # al terminar `observar`, `esperar` entrega lo pendiente y luego avisa que ya no hay más (código 3)
    out = io.StringIO()
    assert vivo.esperar(7, 5, ruta, candado, pausa=0.05, salida=out) == 0 and json.loads(out.getvalue())["tipo"] == "final"
    assert vivo.esperar(8, 5, ruta, candado, pausa=0.05, salida=io.StringIO()) == 3
    # un día sin partidos: `observar` termina de inmediato y no anota nada
    g2 = Guion([("2026-11-10T22:00:00Z", None)])
    g2.pedir = lambda url: {"events": []}
    m2 = vivo.Motor(actual={"meta": {"torneo": TORNEO}, "tabla": [], "pendientes": [], "proyeccion": {}, "liguilla": {}}, sellos={},
                    parametros=par, proyectar=False, pedir=g2.pedir)
    assert vivo.observar(None, m2, tmp_path / "v2.json", tmp_path / "e2.jsonl", tmp_path / "c2.lock", dormir=g2.dormir, reloj=g2.reloj) == 0
    assert vivo.leer_eventos(tmp_path / "e2.jsonl") == []
    assert json.loads((tmp_path / "v2.json").read_text(encoding="utf-8"))["estado"] == "sin_partidos"


def test_guion_de_partido_es_coherente(df):
    fila = df[df["id"] == ID_ATLAS_PUEBLA].iloc[0]
    g = datos.tabla("goles"); g = g[g["partido_id"] == ID_ATLAS_PUEBLA]
    t = datos.tabla("tarjetas"); t = t[t["partido_id"] == ID_ATLAS_PUEBLA]
    fotos = vivo.guion_de_partido(fila, g, t)
    tiempos = [s for s, _ in fotos]
    assert tiempos == sorted(tiempos) and fotos[0][1]["estado"] == "programado" and fotos[-1][1]["estado"] == "final"
    assert (fotos[-1][1]["gl"], fotos[-1][1]["gv"]) == (4, 3)
    totales = [c["gl"] + c["gv"] for _, c in fotos if c["gl"] is not None]
    assert totales == sorted(totales)                              # el marcador nunca baja
    assert sum(1 for _, c in fotos if c["estado"] == "descanso") == 1


# ==================================================================================================
# Exportación
# ==================================================================================================
def test_exportar_incrusta_el_documento_en_vivo(tmp_path):
    ahora = pd.Timestamp("2026-11-22T03:00:00Z")
    ruta = tmp_path / "vivo.json"
    assert ex.leer_vivo(ruta, ahora) is None                       # no existe
    doc = {"version": 1, "generado_utc": "2026-11-22T02:59:00Z", "estado": "en_juego", "partidos": []}
    ruta.write_text(json.dumps(doc), encoding="utf-8")
    assert ex.leer_vivo(ruta, ahora) == doc
    assert ex.leer_vivo(ruta, ahora + pd.Timedelta(hours=35)) == doc
    assert ex.leer_vivo(ruta, ahora + pd.Timedelta(hours=37)) is None            # más de 36 horas: ya no se incrusta
    ruta.write_text(json.dumps(dict(doc, prueba=True)), encoding="utf-8")
    assert ex.leer_vivo(ruta, ahora) is None                       # una repetición de prueba nunca se incrusta
    ruta.write_text("{roto", encoding="utf-8")
    assert ex.leer_vivo(ruta, ahora) is None
    # incrustar_vivo sólo toca el campo "vivo" de actual.json
    actual = tmp_path / "actual.json"
    actual.write_text(json.dumps({"meta": {"corte_utc": "2026-11-22T02:00:00+00:00"}, "tabla": [1, 2]}), encoding="utf-8")
    reciente = dict(doc, generado_utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    ruta.write_text(json.dumps(reciente), encoding="utf-8")
    assert ex.incrustar_vivo(actual, ruta) is True
    d = json.loads(actual.read_text(encoding="utf-8"))
    assert d["vivo"] == reciente and d["tabla"] == [1, 2]
    assert ex.incrustar_vivo(actual, ruta) is False                # sin cambios no reescribe
    ruta.unlink()
    assert ex.incrustar_vivo(actual, ruta) is True and json.loads(actual.read_text(encoding="utf-8"))["vivo"] is None
    assert not (tmp_path / "historial").exists()
