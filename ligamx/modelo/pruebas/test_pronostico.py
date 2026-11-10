# -*- coding: utf-8 -*-
"""
Pruebas de la API de pronóstico de producción (pytest). Desde ligamx/:

    python3 -m pytest modelo/pruebas/test_pronostico.py -q

Ninguna prueba toca el periodo de PRUEBA ni escribe en modelo/pred: sólo leen datos, la caché de variables
y las predicciones de DESARROLLO ya guardadas.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # .../ligamx

from modelo import arnes, datos  # noqa: E402
from modelo import pronostico as P  # noqa: E402
from modelo.familias import candidatos as C  # noqa: E402

CLAVES_PARTIDO = {"id", "lam_l", "lam_v", "rho", "explica"}
CLAVES_FACTOR = {"factor", "detalle", "efecto_l", "efecto_v"}
COLS_FUERZAS = ["equipo", "ataque", "defensa", "rating", "ventaja_local",
                "ee_ataque", "ee_defensa", "ee_rating", "ee_ventaja_local"]


@pytest.fixture(scope="module")
def df():
    return datos.cargar()


@pytest.fixture(scope="module")
def pro(df):
    """El campeón ajustado con todo lo jugado (una sola vez para todo el módulo)."""
    return P.Pronosticador(df=df)


@pytest.fixture(scope="module")
def pendientes(df):
    return datos.pendientes(df)


def _prox_bloque(df, pro):
    """Partidos del torneo en curso que aún no se juegan; si no hay, se arma un cruce hipotético."""
    pend = datos.pendientes(df)
    if len(pend):
        return pend
    a, b = pro.equipos[0], pro.equipos[1]
    return pd.DataFrame({"id": [8_000_000_001], "fecha_utc": [pro.corte + pd.Timedelta(days=3)],
                         "local": [a], "visitante": [b]})


# --------------------------------------------------------------------------------------------------
# Contrato de formas
# --------------------------------------------------------------------------------------------------
def test_equipos_18_en_orden(pro):
    assert len(pro.equipos) == 18
    assert pro.equipos == sorted(pro.equipos)
    assert len(set(pro.equipos)) == 18


def test_campeon_por_omision_es_el_de_campeon_json(pro):
    esperado = P.leer_campeon().get("modelo", P.CAMPEON_POR_OMISION)
    assert pro.nombre == esperado


def test_partidos_contrato(pro, df):
    prox = _prox_bloque(df, pro)
    res = pro.partidos(prox)
    assert isinstance(res, list) and len(res) == len(prox)
    assert [r["id"] for r in res] == [int(i) for i in prox["id"]]
    for r in res:
        assert CLAVES_PARTIDO <= set(r)
        assert r["lam_l"] > 0 and r["lam_v"] > 0 and np.isfinite([r["lam_l"], r["lam_v"]]).all()
        assert -C.RHO_MAX <= r["rho"] <= C.RHO_MAX
        assert isinstance(r["explica"], list) and len(r["explica"]) >= 1
        for f in r["explica"]:
            assert set(f) == CLAVES_FACTOR
            assert isinstance(f["factor"], str) and isinstance(f["detalle"], str)
            assert f["efecto_l"] > 0 and f["efecto_v"] > 0


def test_explica_empieza_por_fuerza_base_y_su_producto_es_la_lambda(pro, df):
    for r in pro.partidos(_prox_bloque(df, pro)):
        factores = [f["factor"] for f in r["explica"]]
        if isinstance(pro.modelo, (C.DixonColes, C.Ajuste)):
            assert factores[0] == "media de la liga"
            assert factores[1] == f"ataque de {r['local']}" and factores[2] == f"defensa de {r['visitante']}"
            assert factores[3] == f"ataque de {r['visitante']}" and factores[4] == f"defensa de {r['local']}"
            assert factores[5] == "ventaja de local"
        assert np.prod([f["efecto_l"] for f in r["explica"]]) == pytest.approx(r["lam_l"], rel=1e-10)
        assert np.prod([f["efecto_v"] for f in r["explica"]]) == pytest.approx(r["lam_v"], rel=1e-10)


def test_malla_contrato_y_lambdas_positivas(pro):
    n = 40
    for fase in ("regular", "liguilla"):
        m = pro.malla(n, fase=fase, semilla=3)
        assert set(m) == {"equipos", "lam_l", "lam_v", "rho"}
        assert m["equipos"] == pro.equipos
        assert isinstance(m["rho"], float)
        fuera = ~np.eye(18, dtype=bool)
        for k in ("lam_l", "lam_v"):
            x = m[k]
            assert x.shape == (n, 18, 18) and x.dtype == np.float64
            assert np.isnan(x[:, ~fuera]).all()                      # nadie juega contra sí mismo
            assert np.isfinite(x[:, fuera]).all() and (x[:, fuera] > 0).all()
            assert x[:, fuera].max() < 8                             # goles esperados verosímiles
    with pytest.raises(ValueError):
        pro.malla(1, fase="repechaje")
    with pytest.raises(ValueError):
        pro.malla(0)


def test_malla_n1_es_solo_la_puntual(pro):
    a, b = pro.malla(), pro.malla(5, semilla=9)
    assert a["lam_l"].shape == (1, 18, 18)
    np.testing.assert_array_equal(a["lam_l"][0], b["lam_l"][0])
    np.testing.assert_array_equal(a["lam_v"][0], b["lam_v"][0])


def test_fuerzas_contrato(pro):
    f = pro.fuerzas(n=200, semilla=1)
    assert list(f.columns) == COLS_FUERZAS
    assert sorted(f["equipo"]) == pro.equipos
    assert f["rating"].is_monotonic_decreasing
    np.testing.assert_allclose(f["rating"], f["ataque"] - f["defensa"], atol=1e-12)
    assert (f[["ataque", "defensa", "ventaja_local"]] > 0).all().all()
    assert (f[[c for c in f.columns if c.startswith("ee_")]] > 0).all().all()
    # la media de ataque y la de defensa son la misma cantidad (goles en cancha neutral)
    assert f["ataque"].mean() == pytest.approx(f["defensa"].mean(), rel=0.02)


# --------------------------------------------------------------------------------------------------
# Coherencia entre malla y partidos
# --------------------------------------------------------------------------------------------------
def test_k0_de_la_malla_coincide_con_partidos(pro, df):
    """Un partido real en la sede habitual del local debe dar lo mismo que su casilla [0, i, j]."""
    prox = _prox_bloque(df, pro)
    m = pro.malla(1)
    pos = {e: i for i, e in enumerate(pro.equipos)}
    comparados = 0
    dm = pro._malla_base()[0].set_index(["local", "visitante"])
    reales = pro._con_variables(pro._normalizar(prox)).set_index("id")
    for r in pro.partidos(prox):
        i, j = pos[r["local"]], pos[r["visitante"]]
        km_real = reales.loc[r["id"], "sede_viaje_km_v"]
        km_malla = dm.loc[(r["local"], r["visitante"]), "sede_viaje_km_v"]
        if not np.isclose(km_real, km_malla, equal_nan=True):
            continue                                                 # se juega fuera de la sede habitual
        assert m["lam_l"][0, i, j] == pytest.approx(r["lam_l"], rel=1e-10)
        assert m["lam_v"][0, i, j] == pytest.approx(r["lam_v"], rel=1e-10)
        assert m["rho"] == pytest.approx(r["rho"], abs=1e-12)
        comparados += 1
    assert comparados >= 1


def test_reproducible_con_semilla(pro):
    a, b, c = pro.malla(30, semilla=11), pro.malla(30, semilla=11), pro.malla(30, semilla=12)
    np.testing.assert_array_equal(a["lam_l"], b["lam_l"])
    np.testing.assert_array_equal(a["lam_v"], b["lam_v"])
    fuera = ~np.eye(18, dtype=bool)
    assert not np.allclose(a["lam_l"][1:][:, fuera], c["lam_l"][1:][:, fuera])
    np.testing.assert_array_equal(a["lam_l"][0], c["lam_l"][0])     # la puntual no depende de la semilla
    f1, f2 = pro.fuerzas(n=100, semilla=4), pro.fuerzas(n=100, semilla=4)
    pd.testing.assert_frame_equal(f1, f2)


# --------------------------------------------------------------------------------------------------
# Incertidumbre de parámetros
# --------------------------------------------------------------------------------------------------
def test_laplace_en_el_optimo(pro):
    """La hessiana se evalúa donde el gradiente de la verosimilitud penalizada es cero y es definida positiva."""
    lap = pro._laplace()
    assert np.abs(lap["grad"]).max() < 1e-6
    assert np.linalg.eigvalsh(lap["H"]).min() > 0


def test_ancho_de_la_incertidumbre_razonable(pro):
    """
    El error estándar del logaritmo de una lambda debe ser del orden de 1/raíz(goles efectivos por equipo):
    ni despreciable ni mayor que la dispersión real entre equipos. Y las muestras deben centrarse en la puntual.
    """
    m = pro.malla(801, semilla=5)
    fuera = ~np.eye(18, dtype=bool)
    for k in ("lam_l", "lam_v"):
        lg = np.log(m[k][:, fuera])
        ee = lg[1:].std(axis=0, ddof=1)
        assert 0.05 < np.median(ee) < 0.30
        assert ee.max() < 0.60
        sesgo = lg[1:].mean(axis=0) - lg[0]
        assert np.abs(sesgo).max() < 4 * ee.max() / np.sqrt(800) + 1e-9
    f = pro.fuerzas(n=400, semilla=2)
    assert f["ee_rating"].median() < f["rating"].std()              # la señal entre equipos supera al ruido


def test_incertidumbre_prestada_para_modelos_sin_verosimilitud(df):
    p = P.Pronosticador(modelo="elo", df=df)
    assert p.incertidumbre == "prestada de dc"
    m = p.malla(20, semilla=1)
    fuera = ~np.eye(18, dtype=bool)
    assert np.isfinite(m["lam_l"][:, fuera]).all() and (m["lam_l"][:, fuera] > 0).all()
    assert P.Pronosticador(modelo="dc", df=df).incertidumbre == "propia"


# --------------------------------------------------------------------------------------------------
# Corte en el pasado: sin fuga y reproduce el walk-forward guardado
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre,bloque", [(None, "2024-03-01"), (None, "2019-08-02"), ("dc", "2022-02-18"),
                                            ("elo", "2025-01-10"), ("ensamble", "2023-10-06")])
def test_corte_pasado_reproduce_pred_guardada(df, nombre, bloque):
    """
    Un Pronosticador con corte en el corte de un bloque de DESARROLLO da las mismas lambdas que el
    walk-forward guardado en modelo/pred/<modelo>.parquet para los partidos de ese bloque.
    """
    nombre = nombre or P.leer_campeon().get("modelo", P.CAMPEON_POR_OMISION)
    if not arnes.ruta_pred(nombre).is_file():
        pytest.skip(f"no hay predicciones guardadas de {nombre}")
    pred = arnes.leer_pred(nombre)
    g = pred[pred["bloque"] == bloque]
    assert len(g) > 0
    corte = g["corte"].iloc[0]
    p = P.Pronosticador(corte=corte, modelo=nombre, df=df)
    assert p._hist["fecha_utc"].max() < corte                        # nada posterior al corte en el historial
    res = pd.DataFrame(p.partidos(df[df["id"].isin(g["id"])])).set_index("id").loc[g["id"].to_numpy()]
    np.testing.assert_allclose(res["lam_l"].to_numpy(), g["lam_l"].to_numpy(), rtol=1e-8)
    np.testing.assert_allclose(res["lam_v"].to_numpy(), g["lam_v"].to_numpy(), rtol=1e-8)
    M = arnes.matrices_marcadores(res["lam_l"].to_numpy(), res["lam_v"].to_numpy(), res["rho"].to_numpy())
    np.testing.assert_allclose(arnes.p1x2(M), g[["p_l", "p_e", "p_v"]].to_numpy(), atol=1e-8)


def test_no_pronostica_hacia_atras(df):
    p = P.Pronosticador(corte="2024-03-01", modelo="dc", df=df)      # viernes 1-mar-2024, 00:00 CDMX
    assert p.corte == pd.Timestamp("2024-03-01 06:00", tz="UTC")
    antes = df[(df["fecha_utc"] < p.corte) & (df["estado"] == "jugado")].tail(2)
    with pytest.raises(ValueError):
        p.partidos(antes)


def test_el_futuro_no_cambia_el_pronostico(df):
    """Borrar físicamente todo lo posterior al bloque pronosticado no cambia las lambdas (modelo dc)."""
    corte = pd.Timestamp("2024-03-01 06:00", tz="UTC")
    bloque = df[(df["corte_bloque"] == corte) & (df["estado"] == "jugado")]
    a = P.Pronosticador(corte=corte, modelo="dc", df=df).partidos(bloque)
    recortado = df[df["fecha_utc"] <= bloque["fecha_utc"].max()].copy()
    oculto = recortado["fecha_utc"] >= corte                         # el propio bloque, sin resultado
    recortado.loc[oculto, ["gl", "gv", "resultado"]] = np.nan
    recortado.loc[oculto, "estado"] = "programado"
    b = P.Pronosticador(corte=corte, modelo="dc", df=recortado).partidos(recortado[oculto])
    assert [x["id"] for x in a] == [x["id"] for x in b]
    np.testing.assert_allclose([x["lam_l"] for x in a], [x["lam_l"] for x in b], rtol=1e-12)
    np.testing.assert_allclose([x["lam_v"] for x in a], [x["lam_v"] for x in b], rtol=1e-12)


# --------------------------------------------------------------------------------------------------
# Retadores, cruces hipotéticos y tabla de salida
# --------------------------------------------------------------------------------------------------
def test_modelo_por_nombre_y_por_instancia(df):
    ahora = pd.Timestamp.now(tz="UTC")                                # mismo corte: el peso depende de la antigüedad
    a = P.Pronosticador(corte=ahora, modelo="dc", df=df)
    b = P.Pronosticador(corte=ahora, modelo=C.DixonColes(vida_media=365, ridge=4, nombre="dc"), df=df)
    np.testing.assert_allclose(a.malla()["lam_l"], b.malla()["lam_l"], rtol=1e-12, equal_nan=True)
    with pytest.raises(ValueError):
        P.Pronosticador(modelo="no_existe", df=df)


def test_cruce_hipotetico_de_liguilla(pro):
    """Un cruce sin id en partidos.csv (serie de liguilla por simular) se pronostica como en la malla."""
    a, b = pro.equipos[3], pro.equipos[10]
    cruce = pd.DataFrame({"id": [8_000_000_123], "fecha_utc": [pro.corte + pd.Timedelta(days=20)],
                          "fase": ["cuartos"], "pierna": [1], "local": [a], "visitante": [b]})
    r = pro.partidos(cruce)[0]
    m = pro.malla(1, fase="liguilla")
    i, j = pro.equipos.index(a), pro.equipos.index(b)
    assert r["lam_l"] == pytest.approx(m["lam_l"][0, i, j], rel=1e-10)
    assert r["lam_v"] == pytest.approx(m["lam_v"][0, i, j], rel=1e-10)


def test_tabla_pronosticos(pro, df):
    t = P.tabla_pronosticos(pro, _prox_bloque(df, pro))
    assert {"lam_l", "lam_v", "p_l", "p_e", "p_v", "marcador", "p_marcador"} <= set(t.columns)
    np.testing.assert_allclose(t[["p_l", "p_e", "p_v"]].sum(axis=1), 1.0, atol=1e-9)
    assert t["marcador"].str.fullmatch(r"\d+-\d+").all()


# --------------------------------------------------------------------------------------------------
# Caché de variables desactualizada (añadido en la auditoría del 2026-11-10)
# --------------------------------------------------------------------------------------------------
def test_cache_de_variables_al_dia_no_avisa(pro):
    assert pro.avisos == []


def test_avisa_si_a_la_cache_de_variables_le_faltan_partidos(df, tmp_path, monkeypatch):
    """Una caché a la que le faltan partidos anteriores al corte de coeficientes debe avisar, no callar."""
    from modelo import variables as V
    vieja = V.cargar("bloque")
    vieja = vieja[vieja["fecha_utc"] < "2026-03-01"]
    ruta = tmp_path / "variables_bloque.parquet"
    vieja.to_parquet(ruta, index=False)
    monkeypatch.setitem(C.RUTA_VARIABLES, "bloque", ruta)
    C._tablas_variables.clear()
    try:
        with pytest.warns(RuntimeWarning, match="faltan"):
            p = P.Pronosticador(corte="2026-11-10", df=df)
        assert len(p.avisos) == 1 and "variables.actualizar" in p.avisos[0]
        # un modelo que no usa la caché (dc) no tiene por qué avisar
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert P.Pronosticador(corte="2026-11-10", modelo="dc", df=df).avisos == []
    finally:
        C._tablas_variables.clear()


def test_estado_cache_detecta_un_partido_modificado(tmp_path, monkeypatch):
    """variables.estado_cache compara firmas sin reconstruir: una firma distinta = caché desactualizada."""
    import shutil
    from modelo import variables as V
    assert V.estado_cache("bloque")["al_dia"]
    for r in V._rutas("bloque"):
        shutil.copy(r, tmp_path / r.name)
    monkeypatch.setattr(V, "DIR_CACHE", tmp_path)
    fir = pd.read_parquet(V._rutas("bloque")[1])
    k = fir.index[(fir["estado"] == "jugado") & (fir["t"] > pd.Timestamp("2026-02-01", tz="UTC").timestamp())][0]
    fir.loc[k, "firma"] = "0"
    fir.to_parquet(V._rutas("bloque")[1], index=False)
    est = V.estado_cache("bloque")
    assert not est["al_dia"] and est["cambiados"] == 1 and est["primer_cambio_utc"].startswith("2026-02")
    assert V.estado_cache("bloque", hasta="2026-01-01")["al_dia"]          # lo anterior al cambio sigue sirviendo
