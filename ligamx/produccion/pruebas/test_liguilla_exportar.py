# -*- coding: utf-8 -*-
"""
Pruebas de lo que exporta la liguilla (liguilla.torneo, la serie de cada pendiente, la combinada de la ronda,
los avisos y la tabla final) y de la validación de la página. Cada prueba corresponde a un defecto encontrado en
el ensayo de la liguilla con el Clausura 2026 (workflow 10, encargo E; el id va en el nombre o en el docstring).

    cd /home/user/SA/ligamx && python3 -m pytest produccion/pruebas/test_liguilla_exportar.py -q

Los escenarios se CONSTRUYEN en memoria sobre los datos al 10-nov-2026 (marcadores inventados sólo para probar
la mecánica); nada se escribe en datos/ ni en salidas/.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))                                           # .../ligamx

from modelo import datos  # noqa: E402
from produccion import combinada as cb  # noqa: E402
from produccion import exportar as ex  # noqa: E402
from produccion.contexto import Contexto  # noqa: E402
from produccion.pronosticador_provisional import Pronosticador  # noqa: E402
from produccion.pruebas.al_corte import al_corte  # noqa: E402
from produccion.pruebas.test_simulador import CORTE, TORNEO, _con_liguilla, _siembra  # noqa: E402

CIUDAD_DEPORTES = (1252.0, "Estadio Ciudad de los Deportes (Azul)")     # estadio_id y nombre de ESPN


@pytest.fixture(scope="module")
def df():
    return al_corte(datos.cargar(), CORTE, TORNEO)


@pytest.fixture(scope="module")
def pron(df):
    return Pronosticador(corte=CORTE, partidos=df)


def _escenario(df, idas_jugadas: int, sede_rara: bool = True):
    """Cuartos en el calendario; las primeras `idas_jugadas` idas ya jugadas. La vuelta de C1 en otra sede."""
    s = _siembra(df)
    piernas = []
    marc = [(0, 1), (1, 1), (2, 0), (0, 0)]
    idas = ["2026-11-26T01:00", "2026-11-26T03:00", "2026-11-27T01:00", "2026-11-27T03:00"]       # miércoles y jueves, 19 y 21 h
    vueltas = ["2026-11-29T01:00", "2026-11-29T03:00", "2026-11-30T01:00", "2026-11-30T03:00"]    # sábado y domingo
    for k, (m, p) in enumerate(((0, 7), (1, 6), (2, 5), (3, 4))):
        gl, gv = marc[k] if k < idas_jugadas else (None, None)
        piernas += [("cuartos", 1, s[p], s[m], gl, gv, None, None, idas[k]),
                    ("cuartos", 2, s[m], s[p], None, None, None, None, vueltas[k])]
    d = _con_liguilla(df, piernas)
    if sede_rara:                                   # la vuelta de C1 (en casa del 1.º) se juega en otro estadio
        i = d.index[(d["fase"] == "cuartos") & (d["pierna"] == 2.0) & (d["local"] == s[0])]
        d.loc[i, "estadio_id"], d.loc[i, "estadio"] = CIUDAD_DEPORTES
    return s, d


def _doc(d, corte, tmp_path, pron):
    return ex.construir(corte, n_sim=2000, sellar=False, ruta_sellos=tmp_path / "s.jsonl",
                        ruta_desempeno=tmp_path / "d.json", df=d, pron=pron)


def _series(doc):
    return [s for r in doc["liguilla"]["torneo"]["rondas"] for s in r["series"]]


@pytest.fixture(scope="module")
def doc_entre(df, pron, tmp_path_factory):
    """Jueves 26-nov a mediodía: dos idas jugadas, dos por jugar ese mismo día y las cuatro vueltas calendarizadas."""
    s, d = _escenario(df, idas_jugadas=2)
    return s, d, _doc(d, "2026-11-26T12:00", tmp_path_factory.mktemp("entre"), pron)


@pytest.fixture(scope="module")
def doc_publicado(df, pron, tmp_path_factory):
    """Lunes 23-nov: ESPN ya lista los cuartos y no se ha jugado nada."""
    s, d = _escenario(df, idas_jugadas=0)
    return s, d, _doc(d, "2026-11-24T12:00", tmp_path_factory.mktemp("publicado"), pron)


def test_h1_estadio_de_la_pierna_es_el_del_calendario(doc_entre):
    s, d, doc = doc_entre
    pend = {p["id"]: p for p in doc["pendientes"]}
    con_id = [l for x in _series(doc) for l in x["piernas"] if l["id"] is not None]
    assert con_id
    for l in con_id:
        fila = d[d["id"] == l["id"]].iloc[0]
        if l["id"] in pend and pend[l["id"]]["detalle"]:
            assert l["estadio"]["nombre"] == pend[l["id"]]["estadio"]["nombre"]          # cuadro = «Próximos partidos»
        assert l["estadio"]["origen"] in ("calendario", "habitual")
        if int(fila["estadio_id"]) == int(CIUDAD_DEPORTES[0]):
            assert l["estadio"]["nombre"] != "Estadio Banorte" and "Ciudad de los Deportes" in l["estadio"]["nombre"]
            assert l["estadio"]["origen"] == "calendario"
    assert any("Ciudad de los Deportes" in l["estadio"]["nombre"] for l in con_id)


def test_h1_sin_calendario_la_sede_dice_de_donde_sale(doc_publicado):
    """Semifinales y final sin calendario: sede de la prensa (config) o la habitual, con su origen."""
    _, _, doc = doc_publicado
    sin_id = [l for x in _series(doc) for l in x["piernas"] if l["id"] is None]
    assert sin_id and all(l["estadio"] and l["estadio"]["origen"] in ("prensa", "habitual") for l in sin_id)


def test_h6_cuartos_publicados_sin_jugar_no_es_en_curso(doc_publicado, doc_entre):
    assert doc_publicado[2]["liguilla"]["torneo"]["estado"] == "definido"
    assert doc_entre[2]["liguilla"]["torneo"]["estado"] == "en_curso"


def test_h7_combinada_de_la_ronda_mas_proxima(doc_entre):
    _, _, doc = doc_entre
    cj = doc["combinada_jornada"]
    assert doc["pendientes"][0]["etiqueta"] == "Cuartos de final, ida"
    assert cj is not None and cj["etiqueta"] == "Cuartos de final, ida" and cj["n_partidos"] == 2


def test_h8_boletos_repetidos_se_marcan():
    q = [{"id": i, "local": f"L{i}", "visitante": f"V{i}", "lam_l": 1.4, "lam_v": 1.0, "rho": 0.0, "p1_l": 0.45, "p1_v": 0.45}
         for i in range(2)]
    j = cb.combinada_jornada(q)
    ns = [j[k]["n"] for k in ("segura", "equilibrada", "atrevida")]
    vistos = {}
    for k in ("segura", "equilibrada", "atrevida"):
        n = j[k]["n"]
        assert j[k]["igual_a"] == (vistos.get(n) if n else None)
        vistos.setdefault(n, k)
    assert len(set(ns)) < 3 and any(j[k]["igual_a"] for k in ("equilibrada", "atrevida"))


def test_h2_vuelta_trae_la_serie_y_lo_que_necesita_cada_uno(doc_entre):
    s, _, doc = doc_entre
    vueltas = [p for p in doc["pendientes"] if p["fase"] == "cuartos" and p["pierna"] == 2]
    assert len(vueltas) == 4
    por_llave = {x["llave"]: x for x in _series(doc)}
    for p in vueltas:
        se = p["serie"]
        x = por_llave[se["llave"]]
        assert se["p_avanza_mejor"] == x["p_avanza_mejor"] and se["mejor"] == x["mejor"]["equipo"]
        assert isinstance(se["texto"], str) and se["texto"]
    # C1: en la ida el 1.º ganó 1-0 de visita (marc[0] = (0, 1): el 8.º, local, 0; el 1.º, 1): va 1-0 en el global
    c1 = [p for p in vueltas if p["local"] == s[0]][0]["serie"]
    assert c1["ida"] == {"local": s[7], "visitante": s[0], "gl": 0, "gv": 1}
    assert c1["global_antes"] == {"mejor": 1, "peor": 0}
    assert c1["necesita"]["mejor"] == f"{s[0]} avanza aun si pierde por 1"
    assert c1["necesita"]["peor"] == f"{s[7]} necesita ganar por 2 o más"
    # C2: 1-1 en la ida: al 2.º le basta el empate y el 7.º necesita ganar
    c2 = [p for p in vueltas if p["local"] == s[1]][0]["serie"]
    assert c2["necesita"] == {"mejor": f"a {s[1]} le basta el empate", "peor": f"{s[6]} necesita ganar"}
    # C3 y C4: la ida todavía no se juega (es ese mismo día): sin ida
    assert all(p["serie"]["ida"] is None for p in vueltas if p["local"] in (s[2], s[3]))
    ida = [p for p in doc["pendientes"] if p["fase"] == "cuartos" and p["pierna"] == 1][0]["serie"]
    assert ida["pierna"] == 1 and "mejor sembrado" in ida["texto"]
    # V1-3: `necesita` es null en la ida y en la vuelta cuya ida no tiene resultado (como dice el contrato)
    assert ida["necesita"] is None
    assert all(p["serie"]["necesita"] is None for p in vueltas if p["local"] in (s[2], s[3]))


def test_v2_6_cada_pierna_sin_jugar_trae_su_pronostico(doc_publicado):
    """La tarjeta compacta de una pierna sin día ni hora dice quién gana (antes sólo el tablero «1·1» y la barra)."""
    _, _, doc = doc_publicado
    sin_jugar = [l for x in _series(doc) for l in x["piernas"] if not l["jugado"]]
    assert sin_jugar
    for l in sin_jugar:
        tres = {"L": l["p_local"], "E": l["p_empate"], "V": l["p_visitante"]}
        pk = l["pick"]
        assert pk["resultado"] == max(tres, key=tres.get) and pk["prob"] == pytest.approx(max(tres.values()), abs=1e-4)
        assert pk["equipo"] == {"L": l["local"], "E": "Empate", "V": l["visitante"]}[pk["resultado"]]


def test_v3_4_aviso_de_la_final_recorrida_sale_de_la_config():
    from produccion import simulador
    a = ex._aviso_final_recorrida(simulador.cargar_reglas())
    assert "si Toluca llega a la final de liga" in a and "24 y 27 de diciembre" in a and "no lo ha precisado" in a
    assert "avanza en la Copa Intercontinental" not in a
    assert ex._dias_mes(["2026-11-30", "2026-12-03"]) == "30 de noviembre y 3 de diciembre"


def test_v2_7_tras_la_final_sigue_el_torneo_terminado(tmp_path):
    """
    25-may-2026 (día siguiente a la final del Clausura 2026): partidos.csv ya trae el Apertura 2026 (empieza el 16-jul).
    El documento sigue con el Clausura 2026 (campeón decidido, sin pendientes) hasta 7 días antes del torneo nuevo; ya
    con el torneo nuevo, «pendientes» sólo trae sus dos primeras jornadas (antes, los 153 partidos).
    """
    d = datos.cargar()
    corte = "2026-05-25T12:00"
    d2, sig = ex.sin_torneo_siguiente(d, corte)
    assert sig == "Apertura 2026" and not (d2["torneo"] == "Apertura 2026").any()
    doc = ex.construir(corte, n_sim=2000, sellar=False, ruta_sellos=tmp_path / "s.jsonl", ruta_desempeno=tmp_path / "d.json",
                       df=d, pron=Pronosticador(corte=corte, partidos=d2))
    assert ex.validar(doc) == []
    t = doc["liguilla"]["torneo"]
    assert doc["meta"]["torneo"] == "Clausura 2026" and doc["pendientes"] == []
    assert t["estado"] == "terminado" and t["campeon_decidido"] and doc["ultimos_resultados"][0]["etiqueta"] == "Final, vuelta"
    assert "sigue con el Clausura 2026" in doc["avisos"][-1]
    assert ex.sin_torneo_siguiente(d, "2026-05-22T12:00")[1] is None             # entre la ida y la vuelta de la final, no
    primero = d.loc[d["torneo"] == "Apertura 2026", "fecha_utc"].min()
    pegado = (primero - pd.Timedelta(days=5)).tz_convert("America/Mexico_City").strftime("%Y-%m-%dT%H:%M")
    assert ex.sin_torneo_siguiente(d, pegado)[1] is None                          # a 5 días del torneo nuevo, ya es ése
    doc = ex.construir(pegado, n_sim=2000, sellar=False, ruta_sellos=tmp_path / "s2.jsonl", ruta_desempeno=tmp_path / "d2.json",
                       df=d, pron=Pronosticador(corte=pegado, partidos=d))
    limpias = list(dict.fromkeys(p["etiqueta"] for p in doc["pendientes"] if "eprogramado" not in p["etiqueta"]))
    assert doc["meta"]["torneo"] == "Apertura 2026" and limpias == ["Jornada 1", "Jornada 2"]
    assert sum(p["etiqueta"] == "Jornada 2" for p in doc["pendientes"]) >= 7 and len(doc["pendientes"]) <= 22


def test_h2_frases_de_la_final():
    assert ex._frase("Pumas", 0, True) == "a Pumas le basta el empate para ser campeón"
    assert ex._frase("Pumas", 2, True).startswith("Pumas necesita ganar por 2 o más")
    assert ex._frase("Pumas", -1) == "Pumas avanza aun si pierde por 1"


def test_h14_h15_fechas_de_la_ronda_y_formato(doc_entre):
    _, d, doc = doc_entre
    cu = doc["liguilla"]["torneo"]["rondas"][0]
    reales = sorted({l["fecha_local"] for x in cu["series"] for l in x["piernas"] if l["pierna"] == 1})
    assert cu["fechas"]["ida"] == reales
    for x in _series(doc):
        for l in x["piernas"]:
            assert l["fecha_local"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", l["fecha_local"])


def test_e1_piernas_sin_jugar_traen_rho(doc_entre):
    for x in _series(doc_entre[2]):
        for l in x["piernas"]:
            if not l["jugado"]:
                assert isinstance(l.get("rho"), float)


def test_h17_h18_en_liguilla_sin_avisos_de_tabla_y_forma_de_fase_regular(doc_entre):
    _, _, doc = doc_entre
    assert not any(a.startswith("Desempates de la tabla") for a in doc["avisos"])
    assert not any("config/torneo.json" in a for a in doc["avisos"])
    for f in doc["tabla"]:
        assert all(x["fase"] == "regular" for x in f["forma_detalle"])


def test_h4_campeon_decidido(df, pron, tmp_path):
    s = _siembra(df)
    piernas = []
    for k, (m, p) in enumerate(((0, 7), (1, 6), (2, 5), (3, 4))):
        piernas += [("cuartos", 1, s[p], s[m], 0, 0, None, None, f"2026-11-25T0{k}:00"),
                    ("cuartos", 2, s[m], s[p], 1, 0, None, None, f"2026-11-28T0{k}:00")]
    piernas += [("semifinal", 1, s[3], s[0], 2, 0, None, None, "2026-12-02T01:00"),
                ("semifinal", 2, s[0], s[3], 0, 0, None, None, "2026-12-05T01:00"),
                ("semifinal", 1, s[2], s[1], 1, 1, None, None, "2026-12-02T03:00"),
                ("semifinal", 2, s[1], s[2], 2, 2, None, None, "2026-12-05T03:00"),
                ("final", 1, s[3], s[1], 1, 0, None, None, "2026-12-10T01:00"),
                ("final", 2, s[1], s[3], 3, 0, None, None, "2026-12-13T01:00")]
    doc = _doc(_con_liguilla(df, piernas), "2026-12-14T12:00", tmp_path, pron)
    t = doc["liguilla"]["torneo"]
    assert t["estado"] == "terminado" and t["campeon_decidido"] and t["campeon_ruta"] == s[1]
    assert t["subcampeon"] == s[3] and "campeón" in t["nota"]


def test_a6_formato_sin_fechas_de_otro_torneo(df, tmp_path):
    corte = "2026-05-04T12:00"                     # Clausura 2026: config/torneo.json es del Apertura 2026
    d = datos.cargar()
    d = d[d["fecha_utc"] < pd.Timestamp("2026-06-30", tz="UTC")]
    doc = ex.construir(corte, n_sim=2000, sellar=False, ruta_sellos=tmp_path / "s.jsonl", ruta_desempeno=tmp_path / "d.json",
                       df=d, pron=Pronosticador(corte=corte, partidos=d))
    assert doc["meta"]["torneo"] == "Clausura 2026"
    assert doc["liguilla"]["formato"]["fechas"] is None
    assert not any(str(f).startswith("2026-11") for r in doc["liguilla"]["torneo"]["rondas"] for f in (r["fechas"]["ida"] or []))


def test_c5_en_liguilla_nadie_llega_apercibido():
    # datos AL CORTE (V1-1 del workflow 10): con los datos del día, en cuanto partidos.csv trae la ida de cuartos
    # de Monterrey (agendada antes del 26-nov 21:00, o ya jugada) suspendidos() da conocido=False y la prueba fallaba
    c = Contexto("2026-11-23", partidos=al_corte(datos.cargar(), "2026-11-23T00:00", TORNEO))
    reg = c.suspendidos("Monterrey", "2026-11-26 21:00", "regular")
    lig = c.suspendidos("Monterrey", "2026-11-26 21:00", "cuartos")
    assert reg["apercibidos"] and lig["apercibidos"] == []
    assert [x["jugador"] for x in lig["suspendidos"]] == [x["jugador"] for x in reg["suspendidos"]]   # las ganadas se cumplen
    assert "art. 15" in lig["nota"]


def _construir():
    spec = importlib.util.spec_from_file_location("construir_web", RAIZ / "web" / "construir.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_h9_pendiente_ligero_sin_estadio_no_tumba_la_pagina():
    c = _construir()
    d = json.loads((RAIZ / "salidas" / "actual.json").read_text(encoding="utf-8"))
    base = {"id": 1, "detalle": False, "fecha_utc": "2027-01-10T01:00:00+00:00", "fecha_local": "2027-01-09", "hora_local": "19:00",
            "etiqueta": "Jornada 1", "local": "Chivas", "visitante": "Pachuca", "p_local": 0.5, "p_empate": 0.3,
            "p_visitante": 0.2, "pick": {"resultado": "L", "equipo": "Chivas", "prob": 0.5}, "marcador": {"gl": 1, "gv": 0}}
    d["pendientes"] = [dict(base)]
    c.validar(d)                                   # ligero sin estadio: válido
    d["pendientes"] = [dict(base, detalle=True)]
    with pytest.raises(c.ErrorDatos):              # con ficha completa el estadio sigue siendo obligatorio
        c.validar(d)


def test_h10_otros_datos_no_reescriben_index(tmp_path):
    c = _construir()
    web = RAIZ / "web"
    huella = {n: hashlib.md5((web / n).read_bytes()).hexdigest() for n in ("index.html", "archivos_publicados.json", "capacidades.json")
              if (web / n).exists()}
    otro = tmp_path / "otro.json"
    shutil.copy(RAIZ / "salidas" / "actual.json", otro)
    assert c.main(["--datos", str(otro), "--documento", "--salida", str(tmp_path / "sitio")]) == 0
    assert (tmp_path / "sitio" / "index.html").exists()
    assert huella == {n: hashlib.md5((web / n).read_bytes()).hexdigest() for n in huella}


# ==================================================================================================
# Horarios de la prensa (24-nov-2026): la liga anunció día y hora de los cuartos, pero ESPN todavía no los lista.
# exportar los toma de config/torneo.json → liguilla.horarios_<fase> (horario_origen = "prensa"); ESPN manda en cuanto
# lista la pierna ("calendario"); un corte de otro torneo no los toma. Equipos y horarios CONSTRUIDOS sobre la siembra
# del escenario (no son los reales).
# ==================================================================================================
def _reglas_con_horarios(s, **cambios) -> dict:
    """config/torneo.json con horarios de prensa para tres piernas de cuartos (ida en casa del peor sembrado)."""
    import copy
    from produccion import simulador
    r = copy.deepcopy(simulador.cargar_reglas())
    r["torneo"] = TORNEO
    lig = r.setdefault("liguilla", {})
    lig["sedes_cuartos"] = []
    lig["horarios_cuartos"] = [
        {"llave": "C4", "pierna": 1, "local": s[4], "visitante": s[3], "fecha_local": "2026-11-25", "hora_local": "19:00",
         "estadio": "Estadio de Prueba", "fuente": "prueba"},
        {"llave": "C1", "pierna": 2, "local": s[0], "visitante": s[7], "fecha_local": "2026-11-29", "hora_local": "19:07",
         "fuente": "prueba"},
        {"llave": "C2", "pierna": 1, "local": s[6], "visitante": s[1], "fecha_local": "2026-11-26", "hora_local": None,
         "fuente": "prueba: sin hora todavía, no se inventa"},
    ]
    r.update(cambios)
    return r


def _piernas(lt) -> dict:
    return {(x["llave"], l["pierna"]): l for r in lt["rondas"] for x in r["series"] for l in x["piernas"]}


@pytest.fixture(scope="module")
def sin_calendario(df, pron):
    """Lunes 23-nov por la noche: fase regular terminada y ESPN sin ningún partido de liguilla."""
    from produccion import simulador
    s, d = _siembra(df), _con_liguilla(df, [])
    reglas = _reglas_con_horarios(s)
    sim = simulador.simular(pron, "2026-11-23T21:15", d, n_sim=2000, reglas=reglas, torneo=TORNEO)
    return s, d, sim, reglas


def test_horario_de_prensa_llena_dia_hora_y_utc(sin_calendario, pron):
    s, d, sim, reglas = sin_calendario
    lt = ex.torneo_liguilla(pron, sim, reglas, s, d)
    p = _piernas(lt)
    ida = p[("C4", 1)]
    assert (ida["local"], ida["visitante"]) == (s[4], s[3]) and ida["id"] is None
    assert (ida["fecha_local"], ida["hora_local"]) == ("2026-11-25", "19:00")
    assert ida["fecha_utc"] == "2026-11-26T01:00:00+00:00"                    # 19:00 del centro de México = 01:00 UTC
    assert ida["horario_origen"] == "prensa"
    assert ida["estadio"] == {"slug": ida["estadio"]["slug"], "nombre": "Estadio de Prueba", "origen": "prensa"}  # sede de horarios_<fase>
    vu = p[("C1", 2)]
    assert (vu["fecha_local"], vu["hora_local"], vu["fecha_utc"], vu["horario_origen"]) == \
        ("2026-11-29", "19:07", "2026-11-30T01:07:00+00:00", "prensa")
    # sin hora completa (C2 ida) o sin horario (las demás) no se inventa nada
    for k, l in p.items():
        if k not in (("C4", 1), ("C1", 2)):
            assert (l["fecha_local"], l["hora_local"], l["fecha_utc"], l["horario_origen"]) == (None, None, None, None), k
    # la ronda: con piernas sin día, las fechas siguen completándose con las ventanas de la configuración
    assert lt["rondas"][0]["fechas"] == {"ida": ["2026-11-25", "2026-11-26"], "vuelta": ["2026-11-28", "2026-11-29"]}


def test_horario_de_prensa_en_el_documento_completo(sin_calendario, pron, tmp_path, monkeypatch):
    """construir() de punta a punta: el documento valida, la ronda toma los días de sus piernas y los avisos no dicen «sin día»."""
    s, d, _, reglas = sin_calendario
    todos = []
    for (m, q), (fi, hi), (fv, hv) in zip(((0, 7), (1, 6), (2, 5), (3, 4)),
                                          (("2026-11-26", "19:00"), ("2026-11-26", "21:10"), ("2026-11-25", "21:10"), ("2026-11-25", "19:00")),
                                          (("2026-11-29", "19:07"), ("2026-11-29", "21:00"), ("2026-11-28", "21:10"), ("2026-11-28", "19:00"))):
        todos += [{"pierna": 1, "local": s[q], "visitante": s[m], "fecha_local": fi, "hora_local": hi},
                  {"pierna": 2, "local": s[m], "visitante": s[q], "fecha_local": fv, "hora_local": hv}]
    reglas = dict(reglas, liguilla=dict(reglas["liguilla"], horarios_cuartos=todos))
    monkeypatch.setattr(ex.simulador, "cargar_reglas", lambda *a, **k: reglas)
    doc = _doc(d, "2026-11-23T21:15", tmp_path, pron)
    assert ex.validar(doc) == [] and doc["pendientes"] == []
    cu = doc["liguilla"]["torneo"]["rondas"][0]
    assert all(l["horario_origen"] == "prensa" and l["id"] is None for x in cu["series"] for l in x["piernas"])
    assert cu["fechas"] == {"ida": ["2026-11-25", "2026-11-26"], "vuelta": ["2026-11-28", "2026-11-29"]}
    primera = min((l for x in cu["series"] for l in x["piernas"]), key=lambda l: l["fecha_utc"])
    assert (primera["local"], primera["fecha_utc"]) == (s[4], "2026-11-26T01:00:00+00:00")
    semis = [l for r in doc["liguilla"]["torneo"]["rondas"][1:] for x in r["series"] for l in x["piernas"]]
    assert all(l["horario_origen"] is None and l["fecha_local"] is None for l in semis)
    assert not any("ya tiene día y hora en el calendario" in a or "mientras la liga no lo publica" in a for a in doc["avisos"])


def test_espn_gana_sobre_la_prensa(df, pron):
    """ESPN lista las cuatro idas (C4 a otra hora que la prensa): su dato manda; la vuelta de C1, sin ESPN, sale de la prensa."""
    from produccion import simulador
    s = _siembra(df)
    idas = ["2026-11-26T01:00", "2026-11-26T03:00", "2026-11-27T01:00", "2026-11-27T03:00"]
    d = _con_liguilla(df, [("cuartos", 1, s[q], s[m], None, None, None, None, idas[k])
                           for k, (m, q) in enumerate(((0, 7), (1, 6), (2, 5), (3, 4)))])
    cu = d["fase"] == "cuartos"                          # como en partidos.csv: día y hora del centro de México
    loc = d.loc[cu, "fecha_utc"].dt.tz_convert(datos.ZONA)
    d.loc[cu, "fecha_local"], d.loc[cu, "hora_local"] = loc.dt.tz_localize(None).dt.normalize(), loc.dt.strftime("%H:%M")
    reglas = _reglas_con_horarios(s)
    sim = simulador.simular(pron, "2026-11-24T12:00", d, n_sim=2000, reglas=reglas, torneo=TORNEO)
    p = _piernas(ex.torneo_liguilla(pron, sim, reglas, s, d))
    ida = p[("C4", 1)]                                   # ESPN: 27-nov 03:00 UTC = jueves 26, 21:00 (la prensa decía mié 25, 19:00)
    fila = d[d["id"] == ida["id"]].iloc[0]
    assert ida["id"] is not None and ida["horario_origen"] == "calendario"
    assert (ida["fecha_local"], ida["hora_local"]) == ("2026-11-26", "21:00") and str(fila["hora_local"]) == "21:00"
    assert pd.Timestamp(ida["fecha_utc"]) == pd.Timestamp("2026-11-27T03:00", tz="UTC")
    assert ida["estadio"]["origen"] in ("calendario", "habitual")                       # la sede también es la de ESPN
    assert p[("C2", 1)]["horario_origen"] == "calendario"                                # en ESPN aunque la prensa no tenga hora
    vu = p[("C1", 2)]
    assert vu["id"] is None and (vu["fecha_local"], vu["hora_local"], vu["horario_origen"]) == ("2026-11-29", "19:07", "prensa")
    assert all(l["horario_origen"] is None for k, l in p.items() if k[1] == 2 and k[0] != "C1")


def test_corte_de_otro_torneo_no_toma_los_horarios(sin_calendario, pron):
    """Un corte retrospectivo de otro torneo (config/torneo.json es de otro): ni horarios ni sedes ni ventanas de la prensa."""
    s, d, sim, reglas = sin_calendario
    otro = dict(reglas, torneo="Clausura 2027")
    lt = ex.torneo_liguilla(pron, sim, otro, s, d)
    for l in _piernas(lt).values():
        assert (l["fecha_local"], l["hora_local"], l["fecha_utc"], l["horario_origen"]) == (None, None, None, None)
        assert l["estadio"] is None or l["estadio"]["origen"] == "habitual"
    assert all(r["fechas"] == {"ida": None, "vuelta": None} for r in lt["rondas"])


def test_v1_1_con_la_localia_invertida_la_vuelta_no_toma_el_dia_de_la_ida(df, pron):
    """
    Workflow 11, V1-1: la liga pone la ida de C4 en casa del MEJOR sembrado y ESPN lista sólo esa ida. La vuelta que
    completa el simulador invierte la localía de la ida y toma de la prensa su propio día (pierna 2); nunca el de la
    ida (antes salía con el mismo local, visitante, día y hora que la ida, y la ronda decía que había vuelta el 25).
    """
    from produccion import simulador
    s = _siembra(df)
    d = _con_liguilla(df, [("cuartos", 1, s[3], s[4], None, None, None, None, "2026-11-26T01:00")])
    cu = d["fase"] == "cuartos"
    loc = d.loc[cu, "fecha_utc"].dt.tz_convert(datos.ZONA)
    d.loc[cu, "fecha_local"], d.loc[cu, "hora_local"] = loc.dt.tz_localize(None).dt.normalize(), loc.dt.strftime("%H:%M")
    reglas = _reglas_con_horarios(s)
    reglas["liguilla"]["horarios_cuartos"] = [
        {"llave": "C4", "pierna": 1, "local": s[3], "visitante": s[4], "fecha_local": "2026-11-25", "hora_local": "19:00"},
        {"llave": "C4", "pierna": 2, "local": s[4], "visitante": s[3], "fecha_local": "2026-11-28", "hora_local": "19:00"}]
    sim = simulador.simular(pron, "2026-11-24T12:00", d, n_sim=2000, reglas=reglas, torneo=TORNEO)
    lt = ex.torneo_liguilla(pron, sim, reglas, s, d)
    p = _piernas(lt)
    ida, vu = p[("C4", 1)], p[("C4", 2)]
    assert (ida["local"], ida["horario_origen"], ida["fecha_local"]) == (s[3], "calendario", "2026-11-25")
    assert (vu["local"], vu["visitante"], vu["id"]) == (s[4], s[3], None)
    assert (vu["fecha_local"], vu["hora_local"], vu["fecha_utc"], vu["horario_origen"]) == \
        ("2026-11-28", "19:00", "2026-11-29T01:00:00+00:00", "prensa")
    assert "2026-11-25" not in lt["rondas"][0]["fechas"]["vuelta"]


def test_v1_1_la_prensa_se_empareja_tambien_por_pierna(sin_calendario, pron):
    """
    Workflow 11, V1-1: una entrada de horarios_<fase> (o sedes_<fase>) con `pierna` sólo vale para esa pierna. Aquí la
    prensa trae la ida de C1 en casa del mejor sembrado y ESPN no lista nada: la vuelta proyectada (mismo local y
    visitante, pierna 2) no toma ni el día ni la sede de esa ida; queda sin día (no se inventa nada).
    """
    s, d, sim, reglas = sin_calendario
    r = dict(reglas, liguilla=dict(reglas["liguilla"], horarios_cuartos=[
        {"llave": "C1", "pierna": 1, "local": s[0], "visitante": s[7], "fecha_local": "2026-11-26", "hora_local": "19:00",
         "estadio": "Estadio de la Ida"}],
        sedes_cuartos=[{"llave": "C1", "pierna": 1, "local": s[0], "visitante": s[7], "estadio": "Estadio de la Ida"}]))
    vu = _piernas(ex.torneo_liguilla(pron, sim, r, s, d))[("C1", 2)]
    assert (vu["local"], vu["visitante"]) == (s[0], s[7])
    assert (vu["fecha_local"], vu["hora_local"], vu["fecha_utc"], vu["horario_origen"]) == (None, None, None, None)
    assert vu["estadio"] is None or vu["estadio"]["origen"] == "habitual"
    # sin `pierna` en la entrada (configuraciones viejas) se sigue emparejando por local y visitante
    r2 = dict(r, liguilla=dict(r["liguilla"], horarios_cuartos=[{k: v for k, v in r["liguilla"]["horarios_cuartos"][0].items() if k != "pierna"}]))
    assert _piernas(ex.torneo_liguilla(pron, sim, r2, s, d))[("C1", 2)]["horario_origen"] == "prensa"


def test_v1_6_entrada_de_prensa_ilegible_avisa_en_stderr(sin_calendario, pron, capsys):
    """Workflow 11, V1-6: una entrada de esta pierna con la hora mal escrita no se usa, pero se avisa (una vez) en stderr."""
    s, d, sim, reglas = sin_calendario
    r = dict(reglas, liguilla=dict(reglas["liguilla"], horarios_cuartos=list(reglas["liguilla"]["horarios_cuartos"]) + [
        {"llave": "C3", "pierna": 2, "local": s[2], "visitante": s[5], "fecha_local": "2026-11-28", "hora_local": "7:00 pm"}]))
    capsys.readouterr()
    p = _piernas(ex.torneo_liguilla(pron, sim, r, s, d))
    err = capsys.readouterr().err
    assert p[("C3", 2)]["horario_origen"] is None and p[("C3", 2)]["fecha_utc"] is None
    assert err.count(f"aviso: config/torneo.json → liguilla.horarios_cuartos: {s[2]}–{s[5]} (vuelta) no tiene día y hora legibles") == 1
    assert "'7:00 pm'" in err
    assert err.count(f"{s[6]}–{s[1]} (ida) no tiene día y hora legibles") == 1      # la de C2 sin hora (del escenario base)
    assert err.count("aviso:") == 2                                                 # las legibles no avisan
