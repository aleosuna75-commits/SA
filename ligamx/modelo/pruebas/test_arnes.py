# -*- coding: utf-8 -*-
"""
Pruebas del arnés de validación (pytest). Desde ligamx/:

    python3 -m pytest modelo/pruebas/test_arnes.py -q

Ninguna prueba toca el periodo de PRUEBA real ni escribe en modelo/pred: todo va a carpetas temporales.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # .../ligamx

from modelo import arnes, base, datos, metricas  # noqa: E402

RESULTADOS = ["gl", "gv", "resultado", "gl_ht", "gv_ht", "gl_et", "gv_et", "pen_l", "pen_v", "tiros_l",
              "tiros_v", "corners_l", "posesion_l", "rojas_l", "amarillas_v", "asistencia", "evaluable", "nota"]


@pytest.fixture(scope="module")
def df():
    return datos.cargar()


def _aislado(tmp_path):
    """Argumentos para que evaluar no escriba fuera de la carpeta temporal."""
    return dict(dir_pred=tmp_path / "pred", dir_cache=tmp_path / "cache",
                ruta_registro=tmp_path / "registro.jsonl", verbose=False)


# ==================================================================================================
# Datos: tipos, periodos y bloques
# ==================================================================================================
def test_tipos_y_orden(df):
    assert df["id"].is_unique
    assert df["fecha_utc"].is_monotonic_increasing
    assert str(df["fecha_utc"].dtype) == "datetime64[ns, UTC]"
    assert str(df["inicio_local"].dtype) == f"datetime64[ns, {datos.ZONA}]"
    assert df["gl"].dtype == float and df["tiros_l"].dtype == float
    jug = datos.jugados(df)
    assert jug[["gl", "gv", "resultado"]].notna().all().all()
    # los vacíos del CSV son NaN, nunca cero: en 2001 no hay tiros ni momios
    viejo = jug[jug["torneo"] == "Apertura 2001"]
    assert viejo["tiros_l"].isna().all() and viejo["ml_l"].isna().all()
    pend = datos.pendientes(df)
    assert not set(pend.columns) & {"gl", "gv", "resultado"}
    assert (df.loc[df["estado"] != "jugado", "resultado"].isna()).all()


def test_periodos(df):
    assert datos.periodo_de("Clausura 2016") == "calentamiento"
    assert datos.periodo_de("Apertura 2016") == "desarrollo"
    assert datos.periodo_de("Clausura 2025") == "desarrollo"
    assert datos.periodo_de("Apertura 2025") == "prueba"
    assert datos.periodo_de("Apertura 2026") == "prueba"
    assert datos.clave_torneo("Clausura 2020") < datos.clave_torneo("Apertura 2020")
    des = datos.torneos_de("desarrollo", df)
    assert len(des) == 18 and des[0] == "Apertura 2016" and des[-1] == "Clausura 2025"
    assert datos.torneos_de("prueba", df) == ["Apertura 2025", "Clausura 2026", "Apertura 2026"]


def test_escritorio_fuera_de_la_evaluacion_pero_en_el_historial(df):
    jug = datos.jugados(df)
    esc = jug[jug["escritorio"]]
    assert set(esc["id"]) == {590969, 623106}
    assert not esc["evaluable"].any()
    obj = arnes.cortes("desarrollo", "bloque", df)
    assert not set(obj["id"]) & {590969, 623106}
    assert len(obj) == int(((jug["periodo"] == "desarrollo") & jug["evaluable"]).sum())


def test_tablas_auxiliares_restringidas_al_historial(df):
    jug = datos.jugados(df)
    corte = pd.Timestamp("2018-03-02 06:00", tz="UTC")
    hist = jug[jug["fecha_utc"] < corte]
    for nombre in ("goles", "tarjetas", "alineaciones"):
        t = datos.tabla(nombre, hist)
        assert len(t) and set(t["partido_id"]) <= set(hist["id"])
        assert len(t) < len(datos.tabla(nombre))
    # los goles con minuto suman el marcador donde ESPN los trae completos
    g = datos.tabla("goles", hist)
    ok = hist[hist["tiene_eventos"] == 1].set_index("id")
    cuenta = g[g["periodo"] <= 2].groupby("partido_id").size().reindex(ok.index).fillna(0)
    assert (cuenta == ok["gl"] + ok["gv"]).mean() > 0.99


def test_bloques_limites_sinteticos():
    """Cortes lunes 00:00 y viernes 00:00 CDMX; en invierno CDMX = UTC-6."""
    loc = ["2024-03-07 23:59",   # jueves por la noche   -> bloque del lunes 4
           "2024-03-08 00:00",   # viernes 00:00         -> bloque del viernes 8
           "2024-03-10 23:00",   # domingo 23:00 (ya es lunes en UTC) -> bloque del viernes 8
           "2024-03-11 00:00",   # lunes 00:00           -> bloque del lunes 11
           "2024-03-06 19:00"]   # miércoles             -> bloque del lunes 4
    utc = pd.DatetimeIndex(loc).tz_localize(datos.ZONA).tz_convert("UTC")
    b = datos.asignar_bloques(pd.Series(utc))
    assert b["bloque"].tolist() == ["2024-03-04", "2024-03-08", "2024-03-08", "2024-03-11", "2024-03-04"]
    assert b["dia"].tolist() == ["2024-03-07", "2024-03-08", "2024-03-10", "2024-03-11", "2024-03-06"]
    assert b["corte_bloque"].iloc[1] == pd.Timestamp("2024-03-08 06:00", tz="UTC")
    assert b["corte_dia"].iloc[2] == pd.Timestamp("2024-03-10 06:00", tz="UTC")
    assert (b["corte_bloque"] <= pd.Series(utc)).all() and (b["corte_dia"] <= pd.Series(utc)).all()
    # con horario de verano (hasta 2022) la medianoche local es 05:00 UTC
    v = datos.asignar_bloques(pd.Series(pd.DatetimeIndex(["2019-07-20 02:00"], tz="UTC")))   # viernes 19, 21:00 local
    assert v["bloque"].iloc[0] == "2019-07-19" and v["corte_bloque"].iloc[0] == pd.Timestamp("2019-07-19 05:00", tz="UTC")


def test_bloques_semana_con_jornada_doble(df):
    """Semana del 26-feb-2024: jornada de media semana (martes y miércoles) y jornada de fin de semana."""
    jug = datos.jugados(df)
    sem = jug[(jug["dia"] >= "2024-02-26") & (jug["dia"] <= "2024-03-03")]
    assert sorted(sem["bloque"].unique()) == ["2024-02-26", "2024-03-01"]
    media, fin = sem[sem["bloque"] == "2024-02-26"], sem[sem["bloque"] == "2024-03-01"]
    assert set(media["inicio_local"].dt.dayofweek) <= {0, 1, 2, 3} and len(media) == 3
    assert set(fin["inicio_local"].dt.dayofweek) <= {4, 5, 6} and len(fin) == 9
    # ningún equipo juega dos veces dentro del mismo bloque
    for _, g in sem.groupby("bloque"):
        equipos = pd.concat([g["local"], g["visitante"]])
        assert equipos.is_unique
    # todo partido cae en el bloque cuyo corte es el último lunes o viernes 00:00 local
    dias = (jug["inicio_local"].dt.tz_localize(None) - pd.to_datetime(jug["bloque"])).dt.total_seconds() / 86400
    assert (dias >= 0).all() and (dias < 4).all()
    assert set(pd.to_datetime(jug["bloque"]).dt.dayofweek.unique()) == {0, 4}


# ==================================================================================================
# Matriz de marcadores
# ==================================================================================================
def test_matriz_suma_uno_y_derivados():
    lam_l = np.array([0.3, 1.2, 1.6, 2.9, 4.5])
    lam_v = np.array([0.4, 1.1, 0.7, 2.2, 0.2])
    for rho in (0.0, -0.11, 0.08):
        M = arnes.matrices_marcadores(lam_l, lam_v, rho)
        assert M.shape == (5, 11, 11) and (M >= 0).all()
        assert np.allclose(M.sum(axis=(1, 2)), 1.0, atol=1e-12)
        P = arnes.p1x2(M)
        assert np.allclose(P.sum(axis=1), 1.0, atol=1e-12)
        assert np.allclose(arnes.dist_total(M).sum(axis=1), 1.0, atol=1e-12)
        assert np.allclose(arnes.p_over(M, 2.5), arnes.dist_total(M)[:, 3:].sum(axis=1))
    # rho = 0: producto de Poisson independientes (truncado y renormalizado)
    M = arnes.matriz_marcadores(1.6, 0.7, 0.0)
    pl = np.array([math.exp(-1.6) * 1.6 ** k / math.factorial(k) for k in range(11)])
    pv = np.array([math.exp(-0.7) * 0.7 ** k / math.factorial(k) for k in range(11)])
    esperado = np.outer(pl, pv) / np.outer(pl, pv).sum()
    assert np.allclose(M, esperado, atol=1e-14)
    assert math.isclose(arnes.p_ambos_anotan(M), esperado[1:, 1:].sum())
    assert math.isclose(arnes.p1x2(M)[0], np.tril(esperado, -1).sum()) and math.isclose(arnes.p1x2(M)[2], np.triu(esperado, 1).sum())
    # Dixon-Coles a mano: sólo cambian las cuatro celdas bajas
    rho = -0.11
    D = np.outer(pl, pv)
    D[0, 0] *= 1 - 1.6 * 0.7 * rho
    D[0, 1] *= 1 + 1.6 * rho
    D[1, 0] *= 1 + 0.7 * rho
    D[1, 1] *= 1 - rho
    assert np.allclose(arnes.matriz_marcadores(1.6, 0.7, rho), D / D.sum(), atol=1e-14)
    x, y, p = arnes.marcador_mas_probable(M)
    assert (x, y) == (1, 0) and math.isclose(p, M.max())
    top = arnes.top_marcadores(M, 3)
    assert [t[2] for t in top] == sorted(M.ravel(), reverse=True)[:3]
    merc = arnes.mercados(M)
    assert math.isclose(merc["p_l"] + merc["p_e"] + merc["p_v"], 1.0) and merc["marcador_probable"] == "1-0"


def test_ajustar_M_a_1x2():
    M = arnes.matriz_marcadores(1.4, 1.1)
    p = np.array([0.5, 0.2, 0.3])
    R = arnes.ajustar_M_a_1x2(M, p)
    assert math.isclose(R.sum(), 1.0) and np.allclose(arnes.p1x2(R), p, atol=1e-12)
    assert math.isclose(R[2, 0] / R[1, 0], M[2, 0] / M[1, 0])        # la forma dentro de la región no cambia


def test_matriz_igual_a_la_del_motor_original():
    if not (base.RAIZ_PREVIO / "cerebro_ligamx_2026.py").is_file():
        pytest.skip("no está el repo previo")
    C, _ = base.motor_original()
    for ll, lv in ((1.83, 0.71), (0.9, 1.4), (3.0, 2.5)):
        assert np.allclose(arnes.matriz_marcadores(ll, lv, C.RHO_DC), C.matriz_marcadores(ll, lv), atol=1e-14)


# ==================================================================================================
# Métricas contra cálculos a mano
# ==================================================================================================
def test_metricas_a_mano():
    P = np.array([[0.5, 0.3, 0.2],      # gana local
                  [0.2, 0.5, 0.3],      # gana visita
                  [0.6, 0.3, 0.1]])     # empate
    y = metricas.resultado_1x2([2, 0, 1], [1, 3, 1])
    assert y.tolist() == [0, 2, 1]
    # log-loss: -ln 0.5, -ln 0.3, -ln 0.3
    assert np.allclose(metricas.logloss_1x2(P, y), [0.6931471806, 1.2039728043, 1.2039728043])
    # RPS = [(F1-O1)^2 + (F2-O2)^2] / 2 con acumuladas en el orden local, empate, visita
    #   partido 1: F = (0.5, 0.8), O = (1, 1) -> (0.25 + 0.04) / 2 = 0.145
    #   partido 2: F = (0.2, 0.7), O = (0, 0) -> (0.04 + 0.49) / 2 = 0.265
    #   partido 3: F = (0.6, 0.9), O = (0, 1) -> (0.36 + 0.01) / 2 = 0.185
    assert np.allclose(metricas.rps_1x2(P, y), [0.145, 0.265, 0.185])
    # Brier multicategoría: 0.25+0.09+0.04 = 0.38; 0.04+0.25+0.49 = 0.78; 0.36+0.49+0.01 = 0.86
    assert np.allclose(metricas.brier_1x2(P, y), [0.38, 0.78, 0.86])
    assert metricas.acierto_1x2(P, y).tolist() == [1.0, 0.0, 0.0]
    # azar uniforme: log-loss ln 3 y Brier 2/3
    U = np.full((3, 3), 1 / 3)
    assert np.allclose(metricas.logloss_1x2(U, y), math.log(3)) and np.allclose(metricas.brier_1x2(U, y), 2 / 3)
    assert math.isclose(metricas.rps_1x2(U, [0, 1, 2]).mean(), 2 / 9)
    # log-verosimilitud del marcador: ln M[gl, gv]; 12 goles se evalúan en la celda 10
    M = arnes.matrices_marcadores([1.5, 1.5], [1.0, 1.0])
    lv = metricas.logv_marcador(M, [2, 12], [1, 0])
    assert math.isclose(lv[0], math.log(M[0, 2, 1])) and math.isclose(lv[1], math.log(M[1, 10, 0]))
    # resumen de una tabla como la del arnés
    t = pd.DataFrame({"p_l": P[:, 0], "p_e": P[:, 1], "p_v": P[:, 2], "resultado": y,
                      "logp_marcador": [-2.0, -3.0, np.nan], "bloque": ["a", "a", "b"]})
    r = metricas.resumen(t)
    assert r["n"] == 3 and r["n_marcador"] == 2
    assert math.isclose(r["logloss"], (0.6931471806 + 2 * 1.2039728043) / 3, rel_tol=1e-9)
    assert math.isclose(r["rps"], 0.595 / 3) and math.isclose(r["brier"], 2.02 / 3)
    assert math.isclose(r["logv_marcador"], -2.5) and math.isclose(r["acierto"], 1 / 3)


def test_calibracion_deciles():
    rng = np.random.default_rng(1)
    n = 6000
    p_l = rng.uniform(0.2, 0.6, n)
    p_e = (1 - p_l) * 0.45
    P = np.column_stack([p_l, p_e, 1 - p_l - p_e])
    y = np.array([rng.choice(3, p=p) for p in P])
    t = metricas.calibracion_deciles(P, y)
    assert len(t) == 10 and t["n"].sum() == 3 * n and t["p_media"].is_monotonic_increasing
    assert math.isclose((t["p_media"] * t["n"]).sum() / t["n"].sum(), 1 / 3)       # cada fila suma 1
    assert (t["dif"].abs() < 4 * t["ee"] + 1e-9).all()                              # datos bien calibrados
    assert len(metricas.calibracion_deciles(P, y, por_clase=True)) == 30
    assert metricas.error_calibracion(P, y) < 0.02
    assert 0.9 < metricas.pendiente_calibracion(P, y) < 1.1
    assert metricas.pendiente_calibracion(P ** 0.5 / (P ** 0.5).sum(axis=1, keepdims=True), y) > 1.5   # tímido


def test_bootstrap_de_bloques():
    rng = np.random.default_rng(7)
    v = rng.normal(0.1, 1.0, 900)
    bloques = np.repeat(np.arange(100), 9)
    r1, r2 = metricas.bootstrap_bloques(v, bloques), metricas.bootstrap_bloques(v, bloques)
    assert r1 == r2                                                   # semilla fija: mismo resultado
    assert math.isclose(r1["media"], v.mean()) and r1["n"] == 900 and r1["n_bloques"] == 100
    assert abs(r1["ee"] - v.std(ddof=1) / math.sqrt(900)) < 0.15 * r1["ee"]   # datos independientes
    assert r1["ic_inf"] < r1["media"] < r1["ic_sup"]
    # con efecto común por bloque el error por bloques crece respecto al ingenuo
    w = v + np.repeat(rng.normal(0, 1.0, 100), 9)
    assert metricas.bootstrap_bloques(w, bloques)["ee"] > 2 * w.std(ddof=1) / math.sqrt(900)
    d = metricas.diferencia_pareada(v + 0.05, v, bloques)
    assert math.isclose(d["dif"], 0.05) and d["ee"] < 1e-12            # diferencia constante: sin error
    assert metricas.diferencia_pareada(v, v, bloques)["dif"] == 0.0


# ==================================================================================================
# El arnés no deja ver el futuro
# ==================================================================================================
class Espia(arnes.Modelo):
    """Registra todo lo que el arnés le enseña y pronostica una constante."""
    nombre = "espia"
    familia = "prueba"

    def __init__(self, jug):
        self.fechas = jug["fecha_utc"].to_numpy(dtype="datetime64[ns]").astype("int64")
        self.cortes, self.max_hist, self.n_hist, self.vistos, self.predichos = [], [], [], set(), []
        self.corte = None

    def ajustar(self, hist, corte):
        assert isinstance(corte, pd.Timestamp) and str(corte.tz) == "UTC"
        assert (hist["estado"] == "jugado").all() and hist["fecha_utc"].is_monotonic_increasing
        self.corte = corte
        self.cortes.append(corte)
        self.max_hist.append(hist["fecha_utc"].max())
        self.n_hist.append(len(hist))
        self.vistos = set(hist["id"])
        # el historial es TODO lo jugado antes del corte, ni más ni menos
        assert len(hist) == int((self.fechas < corte.value).sum())

    def predecir(self, partidos):
        assert not set(partidos["id"]) & self.vistos, "el bloque está en el historial"
        assert (partidos["fecha_utc"] >= self.corte).all()
        assert not set(partidos.columns) & set(RESULTADOS), "el arnés entregó columnas del resultado"
        self.predichos += partidos["id"].tolist()
        return [{"p1x2": [0.45, 0.27, 0.28]}] * len(partidos)


@pytest.mark.parametrize("granularidad", ["bloque", "dia"])
def test_no_hay_fuga(df, tmp_path, granularidad):
    jug = datos.jugados(df)
    espia = Espia(jug)
    torneos = ["Clausura 2020", "Apertura 2020", "Clausura 2024"]
    pred = arnes.evaluar(espia, "desarrollo", granularidad, torneos=torneos, guardar=False,
                         registrar_variante=False, **_aislado(tmp_path))
    assert len(espia.cortes) > 60
    # el espía nunca vio nada con fecha igual o posterior al corte
    assert all(m < c for m, c in zip(espia.max_hist, espia.cortes))
    assert espia.cortes == sorted(espia.cortes) and espia.n_hist == sorted(espia.n_hist)
    # se pronosticó exactamente lo evaluable de esos torneos, una vez cada partido
    esperado = jug[jug["torneo"].isin(torneos) & jug["evaluable"]]
    assert sorted(espia.predichos) == sorted(esperado["id"]) == sorted(pred["id"])
    # cada partido se predijo con el corte de SU bloque (o de su día)
    col = datos.columna_corte(granularidad)
    assert (pred.set_index("id")["corte"] == esperado.set_index("id")[col].reindex(pred["id"])).all()
    assert (pred["corte"] <= pred["fecha_utc"]).all()
    if granularidad == "bloque":
        assert pred.groupby("bloque")["corte"].nunique().max() == 1
    # los resultados reales que califica el arnés son los del CSV
    real = esperado.set_index("id").loc[pred["id"]]
    assert (pred["gl"].to_numpy() == real["gl"].to_numpy()).all() and (pred["resultado"].to_numpy() == real["resultado"].to_numpy()).all()


def test_el_candado_detecta_una_fuga(df):
    jug = datos.jugados(df)
    bloque = jug[jug["bloque"] == "2024-03-01"]
    corte = bloque["corte_bloque"].iloc[0]
    limpio = jug[jug["fecha_utc"] < corte]
    arnes._candado(limpio, corte, bloque)                                # sin fuga: no pasa nada
    with pytest.raises(AssertionError):                                  # el historial incluye el bloque
        arnes._candado(jug[jug["fecha_utc"] <= bloque["fecha_utc"].max()], corte, bloque)
    with pytest.raises(AssertionError):                                  # se pide pronosticar algo ya jugado
        arnes._candado(limpio, corte, pd.concat([limpio.tail(1), bloque]))
    with pytest.raises(AssertionError):                                  # un partido sin jugar en el historial
        arnes._candado(df[df["fecha_utc"] < corte], corte, bloque)


def test_la_prueba_exige_permiso_y_deja_constancia(df, tmp_path):
    aislado = _aislado(tmp_path)
    with pytest.raises(PermissionError):
        arnes.evaluar(Espia(datos.jugados(df)), "prueba", guardar=False, registrar_variante=False, **aislado)
    assert not (tmp_path / "pred" / arnes.NOMBRE_LOG_PRUEBA).exists()
    # Constancia: se simula una "prueba" re-etiquetando un torneo del calentamiento (no se toca la real)
    falso = df[df["orden_torneo"] <= df.loc[df["torneo"] == "Clausura 2010", "orden_torneo"].iloc[0]].copy()
    falso.loc[falso["torneo"] == "Clausura 2010", "periodo"] = "prueba"
    pred = arnes.evaluar(Espia(datos.jugados(falso)), "prueba", permitir_prueba=True, quien="pytest", df=falso,
                         guardar=True, registrar_variante=False, **aislado)
    assert len(pred) == 167
    log = (tmp_path / "pred" / arnes.NOMBRE_LOG_PRUEBA).read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 1 and "quien=pytest" in log[0] and "modelo=espia" in log[0] and "periodo=prueba" in log[0]
    assert (tmp_path / "pred" / "espia__prueba.parquet").is_file()


# ==================================================================================================
# Formatos de salida de un modelo
# ==================================================================================================
class Formatos(arnes.Modelo):
    """Alterna las cuatro formas válidas de responder."""
    nombre = "formatos"

    def ajustar(self, hist, corte):
        pass

    def predecir(self, partidos):
        out = []
        for i in range(len(partidos)):
            out.append([{"lam_l": 1.5, "lam_v": 1.1, "rho": -0.05, "x_extra": 7.0},
                        {"M": arnes.matriz_marcadores(1.2, 1.3)},
                        {"p1x2": [0.5, 0.25, 0.25]},
                        None][i % 4])
        return out


def test_formatos_de_salida(df, tmp_path):
    pred = arnes.evaluar(Formatos(), torneos=["Clausura 2017"], registrar_variante=False, **_aislado(tmp_path))
    n = int((datos.jugados(df)["torneo"] == "Clausura 2017").sum())
    assert 0 < len(pred) < n                                             # los None se omiten
    assert np.allclose(pred[["p_l", "p_e", "p_v"]].sum(axis=1), 1.0)
    solo = pred[pred["lam_l"].isna()]                                    # los que sólo dieron 1X2
    assert len(solo) and solo["logp_marcador"].isna().all() and solo["p_over25"].isna().all()
    con = pred[pred["lam_l"].notna()]
    assert con["logp_marcador"].notna().all() and (con["logp_marcador"] < 0).all()
    fila = con[np.isclose(con["lam_l"], 1.5)].iloc[0]
    M = arnes.matriz_marcadores(1.5, 1.1, -0.05)
    assert math.isclose(fila["p_l"], arnes.p1x2(M)[0]) and math.isclose(fila["p_over25"], arnes.p_over(M, 2.5))
    assert math.isclose(fila["logp_marcador"], math.log(M[int(fila["gl"]), int(fila["gv"])]))
    assert fila["x_extra"] == 7.0
    # lo guardado es lo devuelto, y las matrices quedan en la caché
    guardado = arnes.leer_pred("formatos", parcial=True, dir_pred=tmp_path / "pred")
    pd.testing.assert_frame_equal(guardado, pred, check_dtype=False)
    ids, mats = arnes.leer_matrices("formatos", parcial=True, dir_cache=tmp_path / "cache")
    assert len(ids) == len(con) and np.allclose(mats.sum(axis=(1, 2)), 1.0)
    assert np.allclose(arnes.p1x2(mats), con[["p_l", "p_e", "p_v"]].to_numpy(), atol=1e-6)


@pytest.mark.parametrize("malo", [{"M": np.full((11, 11), 0.01)}, {"M": np.ones((6, 6)) / 36},
                                  {"p1x2": [0.5, 0.3, 0.3]}, {"lam_l": -1.0, "lam_v": 1.0}, {"otra": 1}])
def test_pronosticos_invalidos_se_rechazan(tmp_path, malo):
    class Malo(arnes.Modelo):
        nombre = "malo"

        def ajustar(self, hist, corte):
            pass

        def predecir(self, partidos):
            return [malo] * len(partidos)

    with pytest.raises(ValueError):
        arnes.evaluar(Malo(), torneos=["Clausura 2017"], guardar=False, registrar_variante=False, **_aislado(tmp_path))


# ==================================================================================================
# Determinismo, comparación y registro
# ==================================================================================================
def test_evaluar_es_determinista_y_registra(tmp_path):
    aislado = _aislado(tmp_path)
    torneos = ["Apertura 2018", "Clausura 2019"]
    a = arnes.evaluar(base.PoissonSimple(), torneos=torneos, **aislado)
    b = arnes.evaluar(base.PoissonSimple(), torneos=torneos, **aislado)
    pd.testing.assert_frame_equal(a, b)                                  # idéntico bit a bit
    assert len(a) == 334 and a["id"].is_unique and a["fecha_utc"].is_monotonic_increasing
    assert np.allclose(a[["p_l", "p_e", "p_v"]].sum(axis=1), 1.0)
    assert 0.95 < metricas.resumen(a)["logloss"] < 1.10                  # mejor que el azar (1.0986)
    reg = arnes.leer_registro(aislado["ruta_registro"])
    assert len(reg) == 2 and (reg["nombre"] == "poisson_simple").all() and (reg["familia"] == "base_poisson").all()
    assert reg["hiperparametros.vida_media_dias"].iloc[0] == 365.0 and bool(reg["parcial"].iloc[0])
    assert math.isclose(reg["metricas.logloss"].iloc[0], metricas.resumen(a)["logloss"])
    # comparación pareada: contra sí mismo no hay diferencia; contra las frecuencias coincide con la resta
    f = arnes.evaluar(base.Frecuencias(), torneos=torneos, **aislado)
    c = arnes.comparar({"poisson": a, "copia": b, "frecuencias": f}, referencia="frecuencias")
    fila = c.set_index("modelo").loc["poisson"]
    assert fila["n"] == 334 and math.isclose(fila["d_ll"], metricas.resumen(a)["logloss"] - metricas.resumen(f)["logloss"])
    assert fila["ic95_inf"] < fila["d_ll"] < fila["ic95_sup"] and fila["ee_ll"] > 0
    assert math.isclose(fila["d_logv"], a["logp_marcador"].mean() - f["logp_marcador"].mean())
    c2 = arnes.comparar({"poisson": a, "copia": b})
    assert c2["d_ll"].iloc[0] == 0.0 and c2["d_rps"].iloc[0] == 0.0
    # las frecuencias dan a todos los partidos de un bloque el mismo pronóstico, y su 1X2 suma 1
    assert f.groupby("bloque")["p_l"].nunique().max() == 1


def test_reanudar_una_corrida_interrumpida(tmp_path):
    """Un modelo que truena a media corrida se retoma y da exactamente lo mismo que sin interrupción."""
    class Fragil(base.Frecuencias):
        def __init__(self, falla_en=None):
            super().__init__()
            self.falla_en, self.llamadas = falla_en, 0

        def ajustar(self, hist, corte):
            self.llamadas += 1
            if self.falla_en and self.llamadas == self.falla_en:
                raise KeyboardInterrupt("corte de luz")
            super().ajustar(hist, corte)

    aislado = dict(_aislado(tmp_path), registrar_variante=False, torneos=["Clausura 2019"])
    completo = arnes.evaluar(Fragil(), **aislado)
    with pytest.raises(KeyboardInterrupt):
        arnes.evaluar(Fragil(falla_en=18), reanudar=True, cada=5, **aislado)
    control = list((tmp_path / "cache").glob("reanudar_*.pkl"))
    assert len(control) == 1
    segundo = Fragil()
    retomado = arnes.evaluar(segundo, reanudar=True, cada=5, **aislado)
    pd.testing.assert_frame_equal(retomado, completo)
    assert segundo.llamadas == completo["corte"].nunique() - 15          # sólo rehízo desde el corte 16
    assert not list((tmp_path / "cache").glob("reanudar_*.pkl"))         # al terminar se borra el punto de control


def test_registrar_a_mano(tmp_path):
    ruta = tmp_path / "r.jsonl"
    arnes.registrar("v1", "familia_x", {"a": 1, "b": np.float64(0.5)}, {"logloss": 1.01}, ruta=ruta, periodo="desarrollo")
    arnes.registrar("v2", "familia_x", {"a": 2}, {"logloss": 1.02}, ruta=ruta, periodo="desarrollo")
    t = arnes.leer_registro(ruta)
    assert t["nombre"].tolist() == ["v1", "v2"] and t["metricas.logloss"].tolist() == [1.01, 1.02]


# ==================================================================================================
# Líneas base
# ==================================================================================================
def test_poisson_coincide_con_un_optimizador_independiente():
    from scipy.optimize import minimize
    rng = np.random.default_rng(3)
    ne, n = 6, 400
    il = rng.integers(0, ne, n)
    iv = (il + rng.integers(1, ne, n)) % ne
    atk, dfn = rng.normal(0, 0.3, ne), rng.normal(0, 0.3, ne)
    gl = rng.poisson(np.exp(0.2 + 0.25 + atk[il] + dfn[iv]))
    gv = rng.poisson(np.exp(0.2 + atk[iv] + dfn[il]))
    w = rng.uniform(0.1, 1.0, n)
    theta, it = base.ajustar_poisson(il, iv, gl, gv, w, ne, ridge=1.0)

    def menos_logv(th):
        c, h, a, d = th[0], th[1], th[2:2 + ne], th[2 + ne:]
        el, ev = c + h + a[il] + d[iv], c + a[iv] + d[il]
        return -(w @ (gl * el - np.exp(el) + gv * ev - np.exp(ev))) + 0.5 * (a @ a + d @ d)

    ref = minimize(menos_logv, np.zeros(2 + 2 * ne), method="BFGS", options={"gtol": 1e-9})
    assert np.allclose(theta, ref.x, atol=1e-5) and it < 15
    # arrancar en caliente desde otra solución llega al mismo óptimo
    theta2, _ = base.ajustar_poisson(il, iv, gl, gv, w, ne, ridge=1.0, theta0=theta + 0.3)
    assert np.allclose(theta, theta2, atol=1e-8)


def test_mercado_sin_margen():
    momios = np.array([[2.0, 3.4, 3.9], [1.25, 6.0, 11.0], [3.0, 3.0, 3.0]])
    P = base.prob_proporcional(momios)
    inv = 1 / momios[0]
    assert np.allclose(P[0], inv / inv.sum()) and np.allclose(P.sum(axis=1), 1.0)
    S, z = base.prob_shin(momios)
    assert np.allclose(S.sum(axis=1), 1.0) and (z > 0).all() and (z < 0.1).all()
    assert np.allclose(S[2], 1 / 3)                                    # momios iguales: 1/3 cada uno
    # Shin quita más margen al desvalido: favorito más probable, desvalido menos que el proporcional
    assert S[1, 0] > P[1, 0] and S[1, 2] < P[1, 2]
    # la definición de Shin se cumple: sum sqrt(z^2 + 4(1-z) pi^2 / B) = 2 - z
    pi, B = 1 / momios, (1 / momios).sum(axis=1)
    assert np.allclose(np.sqrt(z[:, None] ** 2 + 4 * (1 - z[:, None]) * pi ** 2 / B[:, None]).sum(axis=1), 2 + z, atol=1e-9)
    # potencia: sum pi^k = 1 con k > 1, y quita aún más margen al desvalido que Shin
    W, k = base.prob_potencia(momios)
    assert np.allclose(((1 / momios) ** k[:, None]).sum(axis=1), 1.0, atol=1e-9) and (k[:2] > 1).all()
    assert np.allclose(W.sum(axis=1), 1.0) and W[1, 2] < S[1, 2] < P[1, 2] and np.allclose(W[2], 1 / 3)
    # el modelo sólo pronostica donde hay momios completos
    partidos = pd.DataFrame({"ml_l": [2.0, np.nan], "ml_e": [3.4, 3.2], "ml_v": [3.9, 2.9]})
    out = base.Mercado("cierre", "proporcional").predecir(partidos)
    assert out[1] is None and np.allclose(out[0]["p1x2"], P[0])


def test_marcador_implicito_del_mercado():
    """De una matriz conocida a sus cuotas (1X2 y más/menos) y de regreso a (lam_l, lam_v, rho)."""
    ll, lv = np.array([1.6, 0.9, 2.4, 1.2]), np.array([1.0, 1.5, 0.8, 1.2])
    rho, linea = np.array([-0.10, 0.05, -0.15, 0.0]), np.array([2.5, 2.5, 3.5, 4.5])
    M = arnes.matrices_marcadores(ll, lv, rho)
    P, po = arnes.p1x2(M), np.array([arnes.p_over(M[i], linea[i]) for i in range(4)])
    a, b, r, res = base.marcador_de_mercado(P, linea, po)
    assert np.allclose(a, ll, atol=1e-8) and np.allclose(b, lv, atol=1e-8) and np.allclose(r, rho, atol=1e-8)
    assert res.max() < 1e-10
    a, b, r, res = base.marcador_de_mercado(P)                         # sin línea de goles: rho = 0
    assert (r == 0).all() and res.max() < 1e-10
    assert np.allclose(arnes.p1x2(arnes.matrices_marcadores(a, b, 0.0)), P, atol=1e-9)
    # el modelo de referencia entrega una matriz cuyo 1X2 es el del mercado sin margen (Shin)
    partidos = pd.DataFrame({"ml_l": [2.0, 1.5], "ml_e": [3.4, 4.2], "ml_v": [3.9, 6.5],
                             "total_linea": [2.5, np.nan], "over": [1.9, np.nan], "under": [1.9, np.nan]})
    out = base.MercadoMarcador().predecir(partidos)
    shin = base.prob_shin(partidos[["ml_l", "ml_e", "ml_v"]].to_numpy())[0]
    for o, s in zip(out, shin):
        assert math.isclose(o["M"].sum(), 1.0) and np.allclose(arnes.p1x2(o["M"]), s, atol=1e-10)
    assert math.isclose(arnes.p_over(out[0]["M"], 2.5), 0.5, abs_tol=1e-6) and out[1]["x_rho"] == 0.0


def test_momios_en_vivo_se_vacian(df):
    crudo = datos.cargar(limpiar_momios=False)
    dud = crudo[crudo["momios_dudosos"] & (crudo["periodo"] == "desarrollo")]
    assert set(dud["id"]) == {692368, 692377, 692383, 692385, 692386, 692388}
    assert dud["ml_l"].notna().all()
    limpio = df[df["id"].isin(dud["id"])]
    assert limpio["ml_l"].isna().all() and (limpio["tiene_momios"] == 0).all()


def test_cerebro_exacto_se_niega_antes_de_agosto_2026(df):
    jug = datos.jugados(df)
    corte = pd.Timestamp("2024-03-01 06:00", tz="UTC")
    with pytest.raises(ValueError):
        base.CerebroOriginalExacto().ajustar(jug[jug["fecha_utc"] < corte], corte)
