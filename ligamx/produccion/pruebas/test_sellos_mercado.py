# -*- coding: utf-8 -*-
"""
Pruebas del mercado en los sellos y de la comparación pareada modelo contra mercado.

    cd /home/user/SA/ligamx && python3 -m pytest produccion/pruebas/test_sellos_mercado.py -q

Los partidos, momios y marcadores de casi todas las pruebas son INVENTADOS en memoria (sólo para probar
la mecánica): nada se escribe en datos/ ni en salidas/. El caso «a mano» trae las cuentas escritas.
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

from modelo import base, datos  # noqa: E402
from produccion import exportar as ex  # noqa: E402
from produccion import sellos  # noqa: E402

NAN = float("nan")
INICIO = {1: "2026-11-21T01:00:00Z", 2: "2026-11-21T03:00:00Z"}
AHORA = pd.Timestamp("2026-11-18T12:00:00Z")


class _Pron:
    """Pronosticador mínimo: sellar() sólo le pide nombre y corte cuando recibe el paquete ya armado."""
    nombre, corte = "de_prueba", None


def _partidos(momios: dict | None = None, estado: str = "programado") -> pd.DataFrame:
    """Dos partidos por jugar; `momios` = {id: (ml_l, ml_e, ml_v, total_linea, over, under, proveedor)}."""
    filas = []
    for pid, (loc, vis) in {1: ("Puebla", "Atlas"), 2: ("Tijuana", "León")}.items():
        m = (momios or {}).get(pid) or (NAN,) * 6 + ("",)
        filas.append({"id": pid, "estado": estado, "fecha_utc": pd.Timestamp(INICIO[pid]), "torneo": "Apertura 2026",
                      "fase": "regular", "pierna": NAN, "local": loc, "visitante": vis, "gl": NAN, "gv": NAN,
                      "gl_ht": NAN, "gv_ht": NAN, **dict(zip(sellos.COLS_MERCADO, m[:6])), "proveedor": m[6]})
    return pd.DataFrame(filas)


def _paquete(lam: dict | None = None) -> dict:
    lam = lam or {1: (1.4, 1.1), 2: (1.7, 0.9)}
    return {"p1_l": 0.45, "p1_v": 0.45,
            "partidos": [{"id": pid, "lam_l": a, "lam_v": b, "rho": 0.0, "combinadas": {}} for pid, (a, b) in lam.items()]}


def _sellar(df, ruta, ahora=AHORA, lam=None):
    return sellos.sellar(_Pron(), df, ruta, paquete=_paquete(lam), ahora=ahora)


MOMIOS_1 = (2.45, 3.40, 2.65, 2.5, 1.645, 2.10, "DraftKings")


# ==================================================================================================
# El campo `mercado` del sello
# ==================================================================================================
def test_sello_con_y_sin_momios(tmp_path):
    ruta = tmp_path / "sellos.jsonl"
    nuevos = {s["id"]: s for s in _sellar(_partidos({1: MOMIOS_1}), ruta)}
    assert set(nuevos) == {1, 2}
    m = nuevos[1]["mercado"]
    assert [m[k] for k in sellos.COLS_MERCADO] == list(MOMIOS_1[:6]) and m["proveedor"] == "DraftKings"      # tal como estaban
    P = base.prob_shin([MOMIOS_1[:3]])[0][0]
    assert [m["p_l"], m["p_e"], m["p_v"]] == pytest.approx(list(P), abs=1e-6) and m["metodo"] == "shin"
    assert m["p_l"] + m["p_e"] + m["p_v"] == pytest.approx(1.0, abs=2e-6)
    assert m["margen"] == pytest.approx(1 / 2.45 + 1 / 3.40 + 1 / 2.65 - 1, abs=1e-6)
    # Shin le quita más margen al momio alto que el reparto proporcional: el favorito queda por encima
    assert m["p_l"] > (1 / 2.45) / (1 / 2.45 + 1 / 3.40 + 1 / 2.65)
    assert nuevos[2]["mercado"] is None                                         # sin momios: null, no se inventa
    en_disco = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()]
    assert len(en_disco) == 2 and all("mercado" in s for s in en_disco)
    assert {s["id"]: s["mercado"] for s in en_disco} == {1: m, 2: None}
    # el pronóstico del sello no depende de que haya momios
    sin = {s["id"]: s for s in _sellar(_partidos(), tmp_path / "otro.jsonl")}
    for k in ("lam_l", "lam_v", "p_l", "p_e", "p_v", "pick", "marcador", "top5"):
        assert sin[1][k] == nuevos[1][k]


def test_mercado_de_guarda_la_linea_de_goles_completa_o_nada():
    f = {"ml_l": 2.0, "ml_e": 3.3, "ml_v": 3.9, "total_linea": 2.5, "over": NAN, "under": 2.1, "proveedor": ""}
    m = sellos.mercado_de(f)
    assert (m["total_linea"], m["over"], m["under"], m["proveedor"]) == (None, None, None, None)
    assert (m["ml_l"], m["ml_e"], m["ml_v"]) == (2.0, 3.3, 3.9) and m["p_l"] > m["p_e"] > m["p_v"]
    m = sellos.mercado_de(dict(f, total_linea=3.5, over=1.05, under=9.0))       # sólo la línea de 2.5 delata un partido en juego
    assert (m["total_linea"], m["over"], m["under"]) == (3.5, 1.05, 9.0)


@pytest.mark.parametrize("cambio, motivo", [
    ({"ml_e": NAN}, "falta un momio"),
    ({"ml_l": None}, "falta un momio"),
    ({"ml_v": 1.0}, "momio que no paga"),
    ({"ml_l": 0.0}, "momio imposible"),
    ({"ml_l": -150.0}, "momio americano sin convertir"),
    ({"ml_e": "3.40"}, "texto en lugar de número"),
    ({"ml_l": float("inf")}, "infinito"),
    ({"ml_l": 1.05, "ml_e": 9.0, "ml_v": 21.0}, "en vivo: favorito por debajo de 1.08"),
    ({"ml_l": 6.0, "ml_e": 1.6, "ml_v": 6.5}, "en vivo: empate por debajo de 2.0"),
    ({"ml_l": 1.15, "ml_e": 13.0, "ml_v": 17.0}, "en vivo: empate por encima de 12"),
    ({"over": 1.10, "under": 6.0}, "en vivo: un lado de la línea de 2.5 por debajo de 1.15"),
    ({"momios_dudosos": True}, "la fila ya viene marcada como dudosa"),
])
def test_momios_invalidos_o_en_vivo_se_descartan(cambio, motivo):
    f = {**dict(zip(sellos.COLS_MERCADO, MOMIOS_1[:6])), "proveedor": "DraftKings"}
    assert sellos.mercado_de(f) is not None
    assert sellos.mercado_de({**f, **cambio}) is None, motivo


def test_descarta_lo_mismo_que_datos():
    """La regla es la de modelo/datos.py: los momios históricos marcados «en vivo» tampoco entrarían a un sello."""
    crudo = datos.cargar(limpiar_momios=False)
    dud = crudo[crudo["momios_dudosos"]]
    assert len(dud) >= 6                                                         # los de Bet365 de abril de 2024
    quita = lambda f: f.drop("momios_dudosos").to_dict()                         # noqa: E731  (que decida la regla, no la marca)
    assert all(sellos.mercado_de(quita(f)) is None for _, f in dud.iterrows())
    assert all(sellos.mercado_de(f) is None for _, f in dud.iterrows())
    con = crudo[(crudo["tiene_momios"] == 1) & ~crudo["momios_dudosos"] & crudo[["ml_l", "ml_e", "ml_v"]].notna().all(axis=1)].tail(300)
    ok = (con[["ml_l", "ml_e", "ml_v"]] > 1.0).all(axis=1)
    assert ok.sum() > 250 and all((sellos.mercado_de(quita(f)) is not None) == bool(v) for (_, f), v in zip(con.iterrows(), ok))
    # y coincide con la referencia de mercado del arnés (mercado_cierre_shin)
    ref = base.Mercado("cierre", "shin").predecir(con[ok].tail(1))[0]["p1x2"]
    m = sellos.mercado_de(con[ok].iloc[-1])
    assert [m["p_l"], m["p_e"], m["p_v"]] == pytest.approx(list(ref), abs=1e-6)


# ==================================================================================================
# Regla que omite sellos idénticos
# ==================================================================================================
def test_un_cambio_de_momios_si_produce_sello_y_la_misma_corrida_no(tmp_path):
    ruta = tmp_path / "sellos.jsonl"
    h = lambda n: AHORA + pd.Timedelta(hours=n)                                  # noqa: E731
    assert len(_sellar(_partidos({1: MOMIOS_1}), ruta, h(0))) == 2
    for n in (1, 2, 3):                                                          # nada cambió: ni un sello más
        assert _sellar(_partidos({1: MOMIOS_1}), ruta, h(n)) == []
    movido = (2.30, 3.40, 2.85) + MOMIOS_1[3:]
    nuevos = _sellar(_partidos({1: movido}), ruta, h(4))                         # se movió el 1X2 del partido 1
    assert [s["id"] for s in nuevos] == [1] and nuevos[0]["mercado"]["ml_l"] == 2.30
    assert _sellar(_partidos({1: movido}), ruta, h(5)) == []
    linea = movido[:3] + (2.5, 1.70, 2.05, "DraftKings")
    assert [s["id"] for s in _sellar(_partidos({1: linea}), ruta, h(6))] == [1]  # también cuenta la línea de goles
    aparece = {1: linea, 2: (1.60, 4.2, 4.7, NAN, NAN, NAN, "")}
    nuevos = _sellar(_partidos(aparece), ruta, h(7))                             # aparecen momios donde no había
    assert [s["id"] for s in nuevos] == [2] and nuevos[0]["mercado"]["total_linea"] is None
    assert _sellar(_partidos(aparece), ruta, h(8)) == []
    # los momios desaparecen y el pronóstico es el mismo: no se escribe nada y el último sello los conserva
    assert _sellar(_partidos({2: aparece[2]}), ruta, h(9)) == []
    of = sellos.sellos_oficiales(_partidos(), ruta)
    assert of[1]["mercado"]["ml_l"] == 2.30 and of[1]["mercado"]["over"] == 1.70 and of[1]["sellado_utc"] == h(6).isoformat()
    # cambia el pronóstico sin momios a la vista: sello nuevo, y dice la verdad (mercado null)
    nuevos = _sellar(_partidos({2: aparece[2]}), ruta, h(10), lam={1: (1.5, 1.1), 2: (1.7, 0.9)})
    assert [s["id"] for s in nuevos] == [1] and nuevos[0]["mercado"] is None
    assert sellos.sellos_oficiales(_partidos(), ruta)[1]["mercado"] is None
    assert len(sellos.leer_sellos(ruta)) == 6


def test_no_se_sellan_momios_de_un_partido_que_ya_empezo(tmp_path):
    """Sin fugas: después del silbatazo los momios pueden moverse lo que quieran, el sello oficial no cambia."""
    ruta = tmp_path / "sellos.jsonl"
    _sellar(_partidos({1: MOMIOS_1, 2: MOMIOS_1}), ruta)
    tarde = pd.Timestamp(INICIO[1]) + pd.Timedelta(minutes=20)                   # el partido 1 ya se juega; el 2 todavía no
    movido = (1.20, 6.0, 15.0) + MOMIOS_1[3:]
    nuevos = _sellar(_partidos({1: movido, 2: movido}), ruta, tarde)
    assert [s["id"] for s in nuevos] == [2]
    of = sellos.sellos_oficiales(_partidos(), ruta)
    assert of[1]["mercado"]["ml_l"] == 2.45 and of[2]["mercado"]["ml_l"] == 1.20
    # y un sello escrito a mano con hora posterior al inicio no cuenta, traiga los momios que traiga
    falso = dict(of[1], sellado_utc=tarde.isoformat(), mercado=dict(of[1]["mercado"], p_l=0.98, p_e=0.01, p_v=0.01))
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(falso) + "\n")
    assert sellos.sellos_oficiales(_partidos(), ruta)[1]["mercado"]["p_l"] == of[1]["mercado"]["p_l"]


# ==================================================================================================
# Sellos viejos (sin el campo)
# ==================================================================================================
def test_sello_viejo_sin_el_campo_se_lee_y_califica_igual(tmp_path):
    ruta, viejo_ruta = tmp_path / "sellos.jsonl", tmp_path / "viejo.jsonl"
    s = _sellar(_partidos({1: MOMIOS_1}), ruta)[0]
    viejo = {k: v for k, v in s.items() if k != "mercado"}                       # como los escritos antes del 16-nov-2026
    viejo_ruta.write_text(json.dumps(viejo, ensure_ascii=False) + "\n", encoding="utf-8")
    assert sellos.leer_sellos(viejo_ruta) == [viejo]
    jug = _partidos(estado="jugado")
    jug.loc[jug["id"] == 1, ["gl", "gv", "gl_ht", "gv_ht"]] = [2.0, 0.0, 1.0, 0.0]
    jug = jug[jug["id"] == 1]
    r_viejo, r_nuevo = (sellos.calificar(jug, x, escribir=False) for x in (viejo_ruta, ruta))
    p = r_viejo["partidos"][0]
    assert p["mercado"] is None and p["logloss"] == pytest.approx(-math.log(s["p_l"]), abs=1e-5)
    assert {k: v for k, v in p.items() if k != "mercado"} == {k: v for k, v in r_nuevo["partidos"][0].items() if k != "mercado"}
    assert r_viejo["acumulado"] == r_nuevo["acumulado"] and r_viejo["por_modelo"] == r_nuevo["por_modelo"]
    cm = r_viejo["contra_mercado"]
    assert (cm["n"], cm["n_sin_mercado"], cm["n_sellados_con_mercado"], cm["desde_local"], cm["lectura"]) == (0, 1, 0, None, "sin_partidos")
    assert cm["mercado"] is None and cm["modelo"] is None and cm["dif_logloss"] is None and cm["ee_dif_logloss"] is None
    assert r_nuevo["contra_mercado"]["n"] == 1 and r_nuevo["contra_mercado"]["desde_local"] == "2026-11-18"
    # frente a un sello viejo: sin momios no se repite; con momios sí se escribe uno nuevo
    assert [x["id"] for x in _sellar(_partidos(), viejo_ruta, AHORA + pd.Timedelta(hours=1))] == [2]      # el partido 2 no tenía sello
    assert _sellar(_partidos(), viejo_ruta, AHORA + pd.Timedelta(hours=2)) == []
    nuevos = _sellar(_partidos({1: MOMIOS_1}), viejo_ruta, AHORA + pd.Timedelta(hours=3))
    assert [x["id"] for x in nuevos] == [1] and nuevos[0]["mercado"]["ml_e"] == 3.40


def test_los_sellos_reales_anteriores_califican_como_antes():
    """El único partido calificado al 16-nov-2026 (Querétaro 0-1 Monterrey) se selló sin momios: 0.8473 de log-loss."""
    df = datos.cargar()
    r = sellos.calificar(df, escribir=False)
    p = [x for x in r["partidos"] if x["id"] == 401876988]
    assert len(p) == 1 and p[0]["mercado"] is None and p[0]["logloss"] == pytest.approx(0.8472941937, abs=1e-9)
    cm = r["contra_mercado"]
    assert cm["n"] + cm["n_sin_mercado"] == r["n_calificados"] and cm["n_sin_mercado"] >= 1
    viejos = [s for s in sellos.leer_sellos() if "mercado" not in s]
    assert len(viejos) == 49 and all(sellos.calificar_mercado(s, 0) is None for s in viejos)


# ==================================================================================================
# Calificación pareada
# ==================================================================================================
def _sello_a_mano(pid, modelo_p, mercado_p, sellado="2026-11-18T12:00:00+00:00"):
    k = int(np.argmax(modelo_p))
    s = {"id": pid, "sellado_utc": sellado, "modelo": "de_prueba", "lam_l": 1.3, "lam_v": 1.1,
         "p_l": modelo_p[0], "p_e": modelo_p[1], "p_v": modelo_p[2], "pick": "LEV"[k],
         "marcador": {"gl": 1, "gv": 1, "prob": 0.12}, "combinadas": {}}
    if mercado_p is not None:
        s["mercado"] = {"proveedor": "Casa", "ml_l": 2.4, "ml_e": 3.3, "ml_v": 3.0, "total_linea": None, "over": None,
                        "under": None, "metodo": "shin", "p_l": mercado_p[0], "p_e": mercado_p[1], "p_v": mercado_p[2], "margen": 0.05}
    return s


def _jugados(marcadores: dict) -> pd.DataFrame:
    return pd.DataFrame([{"id": pid, "estado": "jugado", "fecha_utc": pd.Timestamp("2026-11-21T01:00:00Z") + pd.Timedelta(hours=pid),
                          "torneo": "Apertura 2026", "fase": "regular", "local": f"L{pid}", "visitante": f"V{pid}",
                          "gl": float(gl), "gv": float(gv), "gl_ht": NAN, "gv_ht": NAN} for pid, (gl, gv) in marcadores.items()])


def _escribir(ruta, lista):
    ruta.write_text("".join(json.dumps(s) + "\n" for s in lista), encoding="utf-8")
    return ruta


def test_calificacion_pareada_a_mano(tmp_path):
    """
    Cuatro partidos; tres con mercado en su sello y uno sin él (queda fuera de la comparación).

      partido  resultado  modelo (L, E, V)     mercado (L, E, V)    -ln modelo   -ln mercado   diferencia
      A        L (2-0)    0.50, 0.30, 0.20     0.40, 0.30, 0.30     0.693147     0.916291      -0.223144
      B        E (1-1)    0.20, 0.30, 0.50     0.25, 0.25, 0.50     1.203973     1.386294      -0.182322
      C        V (0-1)    0.60, 0.25, 0.15     0.50, 0.30, 0.20     1.897120     1.609438      +0.287682
      D        L (1-0)    0.40, 0.30, 0.30     (sin mercado)        0.916291

    Media de las tres diferencias: -0.117784 / 3 = -0.039261. Desviaciones respecto a la media: -0.183883,
    -0.143061 y +0.326943; suma de cuadrados 0.161171; entre n-1 = 2 da 0.080586; raíz 0.283876; entre raíz
    de 3 = 0.163896 (error estándar). Brier del mercado: 0.54, 0.875 y 0.98 (media 0.798333). RPS del
    mercado: 0.225, 0.15625 y 0.445 (media 0.275417). Favorito del mercado: L, V y L: acierta 1 de 3.
    """
    ruta = _escribir(tmp_path / "s.jsonl", [
        _sello_a_mano(1, (0.50, 0.30, 0.20), (0.40, 0.30, 0.30)), _sello_a_mano(2, (0.20, 0.30, 0.50), (0.25, 0.25, 0.50)),
        _sello_a_mano(3, (0.60, 0.25, 0.15), (0.50, 0.30, 0.20)), _sello_a_mano(4, (0.40, 0.30, 0.30), None)])
    r = sellos.calificar(_jugados({1: (2, 0), 2: (1, 1), 3: (0, 1), 4: (1, 0)}), ruta, tmp_path / "d.json")
    assert json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))["contra_mercado"] == r["contra_mercado"]
    por = {p["id"]: p for p in r["partidos"]}
    assert [por[i]["mercado"]["logloss"] for i in (1, 2, 3)] == pytest.approx([0.916291, 1.386294, 1.609438], abs=1e-6)
    assert [por[i]["mercado"]["dif_logloss"] for i in (1, 2, 3)] == pytest.approx([-0.223144, -0.182322, 0.287682], abs=1e-6)
    assert [por[i]["mercado"]["pick"] for i in (1, 2, 3)] == ["L", "V", "L"]
    assert [por[i]["mercado"]["acierto_1x2"] for i in (1, 2, 3)] == [1, 0, 0]
    assert [por[i]["mercado"]["prob_resultado"] for i in (1, 2, 3)] == pytest.approx([0.40, 0.25, 0.20])
    assert por[1]["mercado"]["ml_l"] == 2.4 and por[1]["mercado"]["proveedor"] == "Casa"
    assert por[4]["mercado"] is None
    cm = r["contra_mercado"]
    assert (cm["n"], cm["n_sin_mercado"], cm["n_sellados_con_mercado"], cm["n_minimo"]) == (3, 1, 3, 30)
    assert cm["modelo"]["n"] == cm["mercado"]["n"] == 3
    assert cm["modelo"]["logloss"] == pytest.approx(3.794240 / 3, abs=1e-6)
    assert cm["mercado"]["logloss"] == pytest.approx(3.912023 / 3, abs=1e-6)
    assert cm["dif_logloss"] == pytest.approx(-0.039261, abs=1e-6)
    assert cm["dif_logloss"] == pytest.approx(math.log(0.4 * 0.25 * 0.2 / (0.5 * 0.3 * 0.15)) / 3, abs=1e-12)
    assert cm["ee_dif_logloss"] == pytest.approx(0.163896, abs=1e-6)
    assert cm["mercado"]["brier"] == pytest.approx(0.798333, abs=1e-6) and cm["mercado"]["rps"] == pytest.approx(0.275417, abs=1e-6)
    assert (cm["mercado"]["aciertos_favorito"], cm["modelo"]["aciertos_1x2"]) == (1, 1)
    assert cm["mercado"]["acierto_favorito"] == pytest.approx(1 / 3)
    assert cm["lectura"] == "pocos_partidos" and cm["desde_local"] == "2026-11-18"
    # lo que ya existía no cambia: el acumulado sigue contando los cuatro partidos
    assert r["n_calificados"] == r["acumulado"]["n"] == 4
    assert r["acumulado"]["logloss"] == pytest.approx((3.794240 + 0.916291) / 4, abs=1e-6)
    assert r["acumulado"]["aciertos_1x2"] == 2


def test_un_solo_partido_no_tiene_error_estandar_y_el_empate_de_favoritos_va_al_local(tmp_path):
    ruta = _escribir(tmp_path / "s.jsonl", [_sello_a_mano(1, (0.30, 0.30, 0.40), (0.37, 0.26, 0.37))])
    r = sellos.calificar(_jugados({1: (0, 2)}), ruta, escribir=False)
    cm, m = r["contra_mercado"], r["partidos"][0]["mercado"]
    assert cm["n"] == 1 and cm["ee_dif_logloss"] is None and cm["mercado"]["ee_logloss"] is None and cm["lectura"] == "pocos_partidos"
    assert cm["dif_logloss"] == pytest.approx(math.log(0.37 / 0.40))
    assert m["pick"] == "L" and m["acierto_1x2"] == 0                            # 0.37 y 0.37: el primero en el orden L, E, V


def test_el_mercado_sellado_despues_del_inicio_no_entra(tmp_path):
    """El sello oficial (sin mercado) manda: un sello posterior al silbatazo con momios no mete al partido en la comparación."""
    tarde = "2026-11-21T02:30:00+00:00"                                          # el partido 1 empieza 02:00 UTC
    ruta = _escribir(tmp_path / "s.jsonl", [_sello_a_mano(1, (0.5, 0.3, 0.2), None),
                                            _sello_a_mano(1, (0.5, 0.3, 0.2), (0.9, 0.05, 0.05), sellado=tarde)])
    r = sellos.calificar(_jugados({1: (3, 0)}), ruta, escribir=False)
    assert r["partidos"][0]["mercado"] is None and r["contra_mercado"]["n"] == 0
    assert r["contra_mercado"]["n_sellados_con_mercado"] == 0


@pytest.mark.parametrize("modelo_p, mercados, lectura", [
    ((0.40, 0.30, 0.30), [(0.50, 0.25, 0.25), (0.46, 0.27, 0.27)], "mercado_mejor"),
    ((0.50, 0.25, 0.25), [(0.40, 0.30, 0.30), (0.44, 0.28, 0.28)], "modelo_mejor"),
    ((0.40, 0.30, 0.30), [(0.40, 0.30, 0.30)], "sin_diferencia_clara"),
    ((0.40, 0.30, 0.30), [(0.80, 0.10, 0.10), (0.18, 0.41, 0.41)], "sin_diferencia_clara"),
])
def test_lectura_con_treinta_partidos(tmp_path, modelo_p, mercados, lectura):
    """Todos terminan en victoria local: con 30 partidos la lectura sale de comparar la diferencia con 2 errores estándar."""
    n = 30
    ruta = _escribir(tmp_path / "s.jsonl", [_sello_a_mano(i, modelo_p, mercados[i % len(mercados)]) for i in range(1, n + 1)])
    df = _jugados({i: (1, 0) for i in range(1, n + 1)})
    cm = sellos.calificar(df, ruta, escribir=False)["contra_mercado"]
    assert cm["n"] == n and cm["lectura"] == lectura and cm["ee_dif_logloss"] is not None
    if lectura in ("mercado_mejor", "modelo_mejor"):
        assert abs(cm["dif_logloss"]) >= 2 * cm["ee_dif_logloss"] and (cm["dif_logloss"] > 0) == (lectura == "mercado_mejor")
    else:
        assert abs(cm["dif_logloss"]) < 2 * cm["ee_dif_logloss"] or cm["dif_logloss"] == 0
    # con un partido menos ya no se lee nada
    cm29 = sellos.calificar(df[df["id"] < n], ruta, escribir=False)["contra_mercado"]
    assert cm29["n"] == n - 1 and cm29["lectura"] == "pocos_partidos"


# ==================================================================================================
# Exportación: últimos resultados y validador
# ==================================================================================================
def _doc_minimo(tmp_path):
    ruta = _escribir(tmp_path / "s.jsonl", [_sello_a_mano(1, (0.50, 0.30, 0.20), (0.40, 0.30, 0.30)),
                                            _sello_a_mano(2, (0.20, 0.30, 0.50), (0.25, 0.25, 0.50)), _sello_a_mano(3, (0.4, 0.3, 0.3), None)])
    df = _jugados({1: (2, 0), 2: (1, 1), 3: (0, 0)})
    des = sellos.calificar(df, ruta, escribir=False)
    of = sellos.sellos_oficiales(df, ruta)
    df = df.assign(fecha_local=df["fecha_utc"].dt.tz_convert(datos.ZONA).dt.tz_localize(None).dt.normalize(), pierna=NAN)
    ult = ex._ultimos(df, pd.Timestamp("2026-11-23T00:00:00Z"), {}, of, "de_prueba")
    return ex.redondear({"desempeno": {k: des[k] for k in ("n_calificados", "contra_mercado")}, "ultimos_resultados": ult})


def test_ultimos_resultados_y_validador(tmp_path):
    doc = _doc_minimo(tmp_path)
    assert ex._validar_mercado(doc) == []
    por = {u["id"]: u["pronostico"] for u in doc["ultimos_resultados"]}
    m = por[1]["mercado"]
    assert (m["p_local"], m["p_empate"], m["p_visitante"], m["pick"], m["acierto_1x2"]) == (0.4, 0.3, 0.3, "L", True)
    assert m["logloss"] == pytest.approx(0.9163, abs=1e-4) and m["dif_logloss"] == pytest.approx(-0.2231, abs=1e-4)
    assert m["prob_del_resultado"] == 0.4 and (m["ml_local"], m["ml_empate"], m["ml_visitante"], m["proveedor"]) == (2.4, 3.3, 3.0, "Casa")
    assert por[3]["mercado"] is None and por[3]["origen"] == "sello"
    # lo que ya traía el pronóstico sigue igual
    assert por[1]["logloss"] == pytest.approx(0.6931, abs=1e-4) and por[1]["p_local"] == 0.5 and por[1]["acierto_1x2"] is True

    def roto(fn):
        d = json.loads(json.dumps(doc))
        fn(d)
        return ex._validar_mercado(d)

    cm = lambda d: d["desempeno"]["contra_mercado"]                              # noqa: E731
    con_mercado = lambda d: [u for u in d["ultimos_resultados"] if u["id"] == 1][0]["pronostico"]      # noqa: E731
    assert roto(lambda d: d["desempeno"].pop("contra_mercado")) == ["desempeno.contra_mercado falta"]
    assert any("falta" in e for e in roto(lambda d: cm(d).pop("lectura")))
    assert any("dif_logloss no es" in e for e in roto(lambda d: cm(d).update(dif_logloss=0.5)))
    assert any("ee_dif_logloss" in e for e in roto(lambda d: cm(d).update(ee_dif_logloss=None)))
    assert any("lectura no corresponde" in e for e in roto(lambda d: cm(d).update(lectura="mercado_mejor")))
    assert any("lectura desconocida" in e for e in roto(lambda d: cm(d).update(lectura="gana el modelo")))
    assert any("n_calificados" in e for e in roto(lambda d: cm(d).update(n_sin_mercado=0)))
    assert any("mismos partidos" in e for e in roto(lambda d: cm(d)["mercado"].update(n=1)))
    assert any("no debe traer cifras" in e for e in roto(lambda d: cm(d).update(n=0, n_sin_mercado=3)))
    assert any("mercado sellado inválido" in e for e in roto(lambda d: con_mercado(d)["mercado"].update(p_local=0.9)))
    assert any("no viene de un sello" in e for e in roto(lambda d: con_mercado(d).update(origen="modelo/pred (walk-forward, no sellado)")))
    assert any("no cuadran" in e for e in roto(lambda d: cm(d).update(desde_local=None)))             # partidos con mercado y sin fecha
    assert any("no cuadran" in e for e in roto(lambda d: cm(d).update(n_sellados_con_mercado=1)))     # menos sellados que comparados
    # fecha sin partidos sí puede pasar (un sello con momios de un partido que ya no está en los datos): es válido
    vacio = dict(n=0, n_sin_mercado=3, n_sellados_con_mercado=0, mercado=None, modelo=None, dif_logloss=None,
                 ee_dif_logloss=None, lectura="sin_partidos")
    assert roto(lambda d: (cm(d).update(vacio), [u["pronostico"].update(mercado=None) for u in d["ultimos_resultados"]])) == []


def test_el_documento_exportado_trae_la_comparacion():
    """salidas/actual.json (lo que lee la página) pasa el validador, y los sellos reales con mercado están bien formados."""
    doc = json.loads((datos.RAIZ / "salidas" / "actual.json").read_text(encoding="utf-8"))
    assert ex._validar_mercado(doc) == []
    cm = doc["desempeno"]["contra_mercado"]
    assert cm["n"] + cm["n_sin_mercado"] == doc["desempeno"]["n_calificados"]
    if len(doc["desempeno"]["partidos"]) == doc["desempeno"]["n_calificados"]:              # caben todos (son los últimos 40)
        assert sum(p["logloss_mercado"] is not None for p in doc["desempeno"]["partidos"]) == cm["n"]
    # los sellos con mercado guardan momios mayores que 1 y su 1X2 por Shin; ninguno se selló después de su partido
    con = [s for s in sellos.leer_sellos() if s.get("mercado")]
    assert len(con) >= 9 and cm["desde_local"] is not None                                    # los 9 de la Jornada 17, del 16-nov-2026
    assert min(s["sellado_utc"] for s in con) >= "2026-11-16"
    for s in con:
        m = s["mercado"]
        assert min(m["ml_l"], m["ml_e"], m["ml_v"]) > 1.0 and m["p_l"] + m["p_e"] + m["p_v"] == pytest.approx(1.0, abs=2e-6)
        assert pd.Timestamp(s["sellado_utc"]) < pd.Timestamp(s["fecha_utc"])
        assert [m["p_l"], m["p_e"], m["p_v"]] == pytest.approx(list(base.prob_shin([[m["ml_l"], m["ml_e"], m["ml_v"]]])[0][0]), abs=1e-6)
