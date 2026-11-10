# -*- coding: utf-8 -*-
"""
Pruebas de las variables a la fecha (modelo/variables.py). Correr con:

    cd /home/user/SA/ligamx && python3 -m pytest modelo/pruebas/test_variables.py -q

Lo central es la NO FUGA: el valor de cada variable de un partido debe salir idéntico (igualdad exacta,
bit a bit) cuando se recalcula con un historial que termina justo antes de ese partido. Además se
comprueba que nada que no sea "_real" use datos del propio partido, que los pendientes tengan variables,
que los vacíos sean vacíos (no ceros) y que la actualización incremental dé lo mismo que reconstruir.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import variables as V  # noqa: E402

SEMILLA = 20261110
# Lo único del propio partido que se conoce antes de jugarlo (calendario, sede, árbitro y momios).
COLS_PREVIAS = ["id", "fecha_utc", "fecha_local", "anio", "torneo", "fase", "pierna", "estado", "local", "visitante",
                "estadio", "ciudad", "arbitro", "ml_l", "ml_e", "ml_v", "total_linea", "over", "under", "proveedor",
                "hora_local", "serie", "local_id", "visitante_id", "estadio_id", "ml_l_abre", "ml_e_abre",
                "ml_v_abre", "over_abre", "under_abre", "temporada_espn", "fase_espn"]


# ==================================================================================================
# Insumos compartidos
# ==================================================================================================
@pytest.fixture(scope="session")
def insumos():
    p = V.leer_partidos()
    return {"p": p, "tj": V.leer_tarjetas(), "al": V.leer_alineaciones(), "sd": V.leer_sedes(),
            "t": pd.to_datetime(p["fecha_utc"], utc=True)}


@pytest.fixture(scope="session")
def completa(insumos):
    return V.construir(insumos["p"], tarjetas=insumos["tj"], alineaciones=insumos["al"], sedes=insumos["sd"])


@pytest.fixture(scope="session")
def completa_bloque(insumos):
    return V.construir(insumos["p"], corte="bloque", tarjetas=insumos["tj"], alineaciones=insumos["al"],
                       sedes=insumos["sd"])


def _muestra(completa: pd.DataFrame, n: int, semilla: int) -> list[int]:
    """n partidos jugados al azar REPARTIDOS en el tiempo: uno por cada tramo cronológico de igual tamaño."""
    jug = completa[completa["estado"] == "jugado"].sort_values("fecha_utc")
    rng = np.random.default_rng(semilla)
    tramos = np.array_split(jug["id"].to_numpy(), n)
    return [int(rng.choice(t)) for t in tramos]


def _como_pendiente(fila: pd.DataFrame) -> pd.DataFrame:
    """Deja el partido como PROGRAMADO: borra todo lo que no se conoce antes de jugarlo."""
    f = fila.copy()
    for c in f.columns:
        if c not in COLS_PREVIAS:
            f[c] = ""
    f["estado"] = "programado"
    return f


def _truncar(insumos, pid: int, con_alineacion_propia: bool = False, antes_de=None, extra_pendientes=None):
    """
    Historial truncado FÍSICAMENTE: sólo los partidos que empezaron antes de `antes_de` (por omisión, antes
    del propio partido), más el partido (y `extra_pendientes`) como programado sin resultado ni estadísticas.
    Las tarjetas y alineaciones posteriores también se quitan.
    """
    p, t = insumos["p"], insumos["t"]
    propio = p[p["id"] == str(pid)]
    limite = pd.Timestamp(propio["fecha_utc"].iloc[0]) if antes_de is None else antes_de
    limite = limite.tz_localize("UTC") if limite.tzinfo is None else limite
    antes = p[t < limite]
    pend = [propio] if extra_pendientes is None else [extra_pendientes]
    pt = pd.concat([antes] + [_como_pendiente(x) for x in pend], ignore_index=True)
    ids = set(antes["id"])
    ids_al = ids | ({str(pid)} if con_alineacion_propia else set())
    return pt, insumos["tj"][insumos["tj"]["partido_id"].isin(ids)], insumos["al"][insumos["al"]["partido_id"].isin(ids_al)]


def _fila(df: pd.DataFrame, pid: int) -> pd.Series:
    r = df[df["id"] == pid]
    assert len(r) == 1, f"partido {pid}: {len(r)} filas"
    return r.iloc[0]


def _iguales(a: pd.Series, b: pd.Series, cols: list[str]) -> list[str]:
    """Columnas donde a y b NO son exactamente iguales (NaN == NaN cuenta como igual)."""
    x, y = a[cols].to_numpy(dtype="float64"), b[cols].to_numpy(dtype="float64")
    distinto = ~((x == y) | (np.isnan(x) & np.isnan(y)))
    return [c for c, d in zip(cols, distinto) if d]


COLS_TODAS = list(V.catalogo()["variable"])
COLS_NO_REAL = [c for c in COLS_TODAS if "_real" not in c]
COLS_REAL = [c for c in COLS_TODAS if "_real" in c]


# ==================================================================================================
# Catálogo
# ==================================================================================================
def test_catalogo_coincide_con_la_tabla(completa):
    cat = V.catalogo()
    assert not cat["variable"].duplicated().any()
    cols = [c for c in completa.columns if c not in V._IDENT]
    assert set(cols) == set(cat["variable"]), "toda columna debe estar documentada en el catálogo y viceversa"
    assert (completa[cols].dtypes == "float64").all()
    # las _real son exactamente las marcadas como no disponibles; las de mercado, las marcadas 'mercado'
    assert set(cat.loc[cat["disponible"] == "no", "variable"]) == set(COLS_REAL)
    assert set(cat.loc[cat["disponible"] == "mercado", "variable"]) == {c for c in cols if c.startswith("mercado_")}
    assert not set(V.columnas(completa)) & (set(COLS_REAL) | {c for c in cols if c.startswith("mercado_")})


def test_una_fila_por_partido(completa, insumos):
    p = insumos["p"]
    assert not completa["id"].duplicated().any()
    esperados = p[((p["estado"] == "jugado") & (p["fecha_utc"] >= V.DESDE)) | (p["estado"] == "programado")]
    assert set(completa["id"]) == set(esperados["id"].astype("int64"))


# ==================================================================================================
# NO FUGA
# ==================================================================================================
def test_no_fuga_60_partidos_historial_truncado(completa, insumos):
    """
    60 partidos al azar repartidos de 2010 a 2026: con el historial truncado justo antes del partido (y el
    propio partido sin resultado ni estadísticas) todas las variables no "_real" deben ser IDÉNTICAS a las
    de la tabla completa. 12 de ellos recalculan toda la tabla truncada; el resto sólo la fila del partido.
    """
    ids = _muestra(completa, 60, SEMILLA)
    fallas = {}
    for k, pid in enumerate(ids):
        pt, tj, al = _truncar(insumos, pid)
        t_m = V._a_epoca(insumos["p"].loc[insumos["p"]["id"] == str(pid), "fecha_utc"].iloc[0])
        rapido = None if k % 5 == 0 else t_m
        trunc = V.construir(pt, tarjetas=tj, alineaciones=al, sedes=insumos["sd"], _calcular_desde=rapido)
        dif = _iguales(_fila(trunc, pid), _fila(completa, pid), COLS_NO_REAL)
        if dif:
            fallas[pid] = dif
        # sin la alineación del propio partido, las _real quedan vacías
        assert _fila(trunc, pid)[COLS_REAL].isna().all()
    assert not fallas, f"variables que cambian al truncar el historial: {fallas}"


def test_hasta_equivale_a_truncar(completa, insumos):
    """El parámetro `hasta` (historial truncado sin tocar las tablas) da lo mismo que la tabla completa."""
    for pid in _muestra(completa, 8, SEMILLA + 1):
        fecha = insumos["p"].loc[insumos["p"]["id"] == str(pid), "fecha_utc"].iloc[0]
        trunc = V.construir(insumos["p"], hasta=fecha, tarjetas=insumos["tj"], alineaciones=insumos["al"],
                            sedes=insumos["sd"], _calcular_desde=V._a_epoca(fecha))
        fila = _fila(trunc, pid)
        assert fila["estado"] == "programado"
        assert not _iguales(fila, _fila(completa, pid), COLS_NO_REAL)
        assert fila[COLS_REAL].isna().all()


def test_real_solo_cambia_con_la_alineacion_propia(completa, insumos):
    """Con la alineación del propio partido (se publica ~1 h antes) las "_real" también coinciden."""
    for pid in _muestra(completa[completa["fecha_utc"] >= "2017-01-01"], 8, SEMILLA + 2):
        pt, tj, al = _truncar(insumos, pid, con_alineacion_propia=True)
        fecha = insumos["p"].loc[insumos["p"]["id"] == str(pid), "fecha_utc"].iloc[0]
        trunc = V.construir(pt, tarjetas=tj, alineaciones=al, sedes=insumos["sd"], _calcular_desde=V._a_epoca(fecha))
        assert not _iguales(_fila(trunc, pid), _fila(completa, pid), COLS_TODAS)


def test_nada_no_real_usa_datos_del_propio_partido(completa, insumos):
    """
    Se alteran el marcador, las estadísticas, las tarjetas y la alineación DEL PROPIO partido: ninguna
    variable no "_real" de ese partido puede cambiar (y las "_real" sí deben reaccionar a la alineación).
    """
    rng = np.random.default_rng(SEMILLA + 3)
    p, tj, al = insumos["p"], insumos["tj"], insumos["al"]
    reaccionaron = 0
    for pid in _muestra(completa[completa["fecha_utc"] >= "2013-01-01"], 15, SEMILLA + 3):
        s = str(pid)
        p2 = p.copy()
        i = p2.index[p2["id"] == s][0]
        for c in p2.columns:
            if c in COLS_PREVIAS or c in ("tiene_stats", "tiene_eventos", "tiene_alineaciones", "tiene_momios",
                                          "tiene_tarjetas", "ht_fuente", "estado_espn", "nota", "formacion_l",
                                          "formacion_v", "gl_et", "gv_et", "pen_l", "pen_v"):
                continue
            p2.loc[i, c] = str(int(rng.integers(0, 9)))   # marcador, tiros, tarjetas, asistencia... al azar
        p2.loc[i, "tiene_stats"] = "1"
        # tarjetas del propio partido: se expulsa a todos los que tuvieron tarjeta
        tj2 = tj.copy()
        tj2.loc[tj2["partido_id"] == s, "tipo"] = "roja"
        # alineación del propio partido: se intercambian titulares y suplentes del local
        al2 = al.copy()
        m = al2["partido_id"] == s
        fila_p = p[p["id"] == s].iloc[0]
        ml = m & (al2["equipo"] == fila_p["local"])
        if (al2.loc[ml, "titular"] == "0").sum() >= 3:
            idx_t = al2.index[ml & (al2["titular"] == "1")][:3]
            idx_s = al2.index[ml & (al2["titular"] == "0")][:3]
            al2.loc[idx_t, "titular"] = "0"
            al2.loc[idx_s, "titular"] = "1"
        alterada = V.construir(p2, tarjetas=tj2, alineaciones=al2, sedes=insumos["sd"],
                               _calcular_desde=V._a_epoca(fila_p["fecha_utc"]))
        dif = _iguales(_fila(alterada, pid), _fila(completa, pid), COLS_NO_REAL)
        assert not dif, f"partido {pid}: variables no _real que dependen del propio partido: {dif}"
        reaccionaron += bool(_iguales(_fila(alterada, pid), _fila(completa, pid), COLS_REAL))
    assert reaccionaron >= 10, "las variables _real deberían reaccionar a la alineación del propio partido"


def test_corte_bloque_no_usa_nada_del_bloque(completa_bloque, insumos):
    """
    corte='bloque': con sólo los partidos que EMPEZARON antes del corte de lunes/viernes 00:00 (CDMX) y todo
    el bloque del partido como programado, las variables salen idénticas: no se usa nada del propio bloque.
    """
    p, t = insumos["p"], insumos["t"]
    for pid in _muestra(completa_bloque, 12, SEMILLA + 4):
        corte = _fila(completa_bloque, pid)["corte_utc"]
        propio = p[p["id"] == str(pid)]
        t_m = pd.Timestamp(propio["fecha_utc"].iloc[0])
        assert corte <= t_m and (t_m - corte) < pd.Timedelta(days=4)
        loc = corte.tz_convert(V.ZONA)
        assert loc.hour == 0 and loc.minute == 0 and loc.dayofweek in (0, 4)
        del_bloque = p[(t >= corte) & (t <= t_m) & (p["estado"] == "jugado")]
        pt, tj, al = _truncar(insumos, pid, antes_de=corte, extra_pendientes=del_bloque)
        trunc = V.construir(pt, corte="bloque", tarjetas=tj, alineaciones=al, sedes=insumos["sd"],
                            _calcular_desde=V._a_epoca(corte))
        dif = _iguales(_fila(trunc, pid), _fila(completa_bloque, pid), COLS_NO_REAL)
        assert not dif, f"partido {pid} (bloque): {dif}"


def test_calculo_parcial_igual_al_completo(completa, insumos):
    """`_calcular_desde` (base de la actualización incremental) no cambia ningún valor."""
    desde = V._a_epoca("2025-07-01")
    parcial = V.construir(insumos["p"], tarjetas=insumos["tj"], alineaciones=insumos["al"], sedes=insumos["sd"],
                          _calcular_desde=desde)
    ref = completa[completa["fecha_utc"] >= "2025-07-01"].reset_index(drop=True)
    pd.testing.assert_frame_equal(parcial.reset_index(drop=True), ref, check_exact=True)


def test_determinista(completa, insumos):
    otra = V.construir(insumos["p"], tarjetas=insumos["tj"], alineaciones=insumos["al"], sedes=insumos["sd"])
    pd.testing.assert_frame_equal(otra, completa, check_exact=True)


# ==================================================================================================
# Actualización incremental (con copias de los datos en un directorio temporal)
# ==================================================================================================
def test_actualizacion_incremental_igual_a_reconstruir(completa, insumos, tmp_path, monkeypatch):
    p = insumos["p"]
    jug = p[p["estado"] == "jugado"]
    ultimos = jug.sort_values("fecha_utc")["id"].iloc[-12:]          # los 12 partidos más recientes "aún no se juegan"
    viejo = p.copy()
    m = viejo["id"].isin(set(ultimos))
    viejo.loc[m, :] = _como_pendiente(viejo[m])
    datos = tmp_path / "datos"
    datos.mkdir()
    for nombre in ("tarjetas.csv", "alineaciones.csv", "estadios_sedes.csv"):
        shutil.copy(V.DIR_DATOS / nombre, datos / nombre)
    monkeypatch.setattr(V, "RUTA_PARTIDOS", datos / "partidos.csv")
    monkeypatch.setattr(V, "RUTA_TARJETAS", datos / "tarjetas.csv")
    monkeypatch.setattr(V, "RUTA_ALINEACIONES", datos / "alineaciones.csv")
    monkeypatch.setattr(V, "RUTA_SEDES", datos / "estadios_sedes.csv")
    monkeypatch.setattr(V, "DIR_CACHE", tmp_path / "cache")

    viejo.to_csv(datos / "partidos.csv", index=False)
    antes = V.actualizar()                                            # sin caché: reconstrucción completa
    assert (antes["estado"] == "programado").sum() == (p["estado"] == "programado").sum() + 12
    p.to_csv(datos / "partidos.csv", index=False)                     # "se jugaron" esos 12 partidos
    despues = V.actualizar()                                          # incremental
    pd.testing.assert_frame_equal(despues.reset_index(drop=True), completa.reset_index(drop=True), check_exact=True)
    pd.testing.assert_frame_equal(V.cargar().reset_index(drop=True), completa.reset_index(drop=True), check_exact=True)
    # lo anterior al primer partido nuevo no se tocó
    corte = pd.to_datetime(p.loc[p["id"].isin(set(ultimos)), "fecha_utc"], utc=True).min()
    previas = antes[antes["fecha_utc"] < corte].reset_index(drop=True)
    pd.testing.assert_frame_equal(previas, completa[completa["fecha_utc"] < corte].reset_index(drop=True), check_exact=True)
    # sin cambios: devuelve la caché tal cual
    pd.testing.assert_frame_equal(V.actualizar().reset_index(drop=True), completa.reset_index(drop=True), check_exact=True)


# ==================================================================================================
# Pendientes y vacíos
# ==================================================================================================
def test_los_pendientes_tienen_variables(completa, insumos):
    pend = completa[completa["estado"] == "programado"]
    assert len(pend) == (insumos["p"]["estado"] == "programado").sum()
    if len(pend) == 0:
        pytest.skip("no hay partidos programados")
    clave = ["elo_dif", "forma5_ppp_l", "forma10_dg_v", "racha_inv_l", "tabla_pos_l", "tabla_pos_v", "descanso_l",
             "descanso_v", "sede_altitud", "sede_viaje_km_v", "sede_vl_l", "h2h_n", "juego10_xg_f_l", "susp_n_l",
             "once_previa_hab_l", "lig_series6_l", "n_prev_l", "hora_local", "liga_goles"]
    # Si el partido anterior de un equipo aún no se juega (pendientes_previos > 0) sus suspensiones no se pueden
    # deducir y quedan vacías; todo lo demás debe tener valor.
    al_dia = (pend["pendientes_previos_l"] == 0) & (pend["pendientes_previos_v"] == 0)
    assert al_dia.any()
    por_suspension = [f"{b}_{s}" for b in ("rojas_prev", "susp_n", "susp_imp", "susp_titulares", "aus_tit_previa")
                      for s in ("l", "v", "dif") if f"{b}_{s}" in COLS_TODAS]
    assert pend.loc[al_dia, clave].notna().all().all(), pend.loc[al_dia, clave].isna().sum()[lambda s: s > 0].to_dict()
    assert pend[[c for c in clave if c not in por_suspension]].notna().all().all()
    for s in ("l", "v"):
        atrasados = pend[pend[f"pendientes_previos_{s}"] > 0]
        assert atrasados[[f"susp_n_{s}", f"rojas_prev_{s}", f"aus_tit_previa_{s}"]].isna().all().all()
    # todas las variables disponibles (sin mercado ni árbitro) tienen valor en los pendientes de fase regular
    disp = [c for c in V.columnas(completa) if not c.startswith("arb_")]
    reg = pend[pend["fase"] == "regular"]
    liguilla = ["pierna", "global_gf_l", "global_gc_l", "global_dif_l", "sembrado_l", "sembrado_v", "sembrado_dif",
                "ventaja_serie_l", "h2h_lig_pts_l", "h2h_lig_dg_l", "h2h_final_dg_l", "asistencia5_l"]
    faltan = reg.loc[al_dia.reindex(reg.index), [c for c in disp if c not in liguilla]].isna().mean()
    assert (faltan == 0).all(), faltan[faltan > 0].to_dict()
    resto = reg[[c for c in disp if c not in liguilla and c not in por_suspension]].isna().mean()
    assert (resto == 0).all(), resto[resto > 0].to_dict()
    # sin alineación publicada no hay variables _real
    con_once = set(insumos["al"]["partido_id"])
    sin = pend[~pend["id"].astype(str).isin(con_once)]
    assert sin[COLS_REAL].isna().all().all()


def test_los_vacios_son_vacios_no_ceros(completa, insumos):
    p = insumos["p"].copy()
    p["id"] = p["id"].astype("int64")
    d = completa.merge(p[["id", "ml_l", "arbitro", "pierna"]].rename(columns={"pierna": "pierna_csv"}), on="id")
    # mercado: vacío exactamente donde no hay momios (o son dudosos)
    sin_momios = d["ml_l"] == ""
    assert d.loc[sin_momios, [c for c in COLS_TODAS if c.startswith("mercado_")]].isna().all().all()
    con = d[~sin_momios & (d["mercado_dudoso"] == 0)]
    assert con[["mercado_p_l", "mercado_p_e", "mercado_p_v"]].notna().all().all()
    assert np.allclose(con[["mercado_p_l", "mercado_p_e", "mercado_p_v"]].sum(axis=1), 1.0)
    dud = d[d["mercado_dudoso"] == 1]
    assert dud[["mercado_p_l", "mercado_linea", "mercado_p_over"]].isna().all().all()
    # árbitro: vacío si no hay árbitro
    assert d.loc[d["arbitro"] == "", ["arb_n", "arb_tarjetas", "arb_penales"]].isna().all().all()
    assert d.loc[d["arbitro"] != "", "arb_n"].notna().all()
    # fase regular: lo de liguilla queda vacío; en la ida no hay marcador global
    reg = d[d["fase"] == "regular"]
    assert reg[["pierna", "sembrado_l", "sembrado_v", "global_dif_l", "ventaja_serie_l"]].isna().all().all()
    assert d.loc[(d["fase"] != "regular") & (d["pierna_csv"] == "1"), ["global_gf_l", "global_dif_l"]].isna().all().all()
    vueltas = d[(d["fase"] != "regular") & (d["pierna_csv"] == "2") & (d["estado"] == "jugado")]
    assert vueltas["global_dif_l"].notna().mean() > 0.99
    # equipos sin historia: forma y rachas vacías (no cero)
    nuevos = completa[completa["n_prev_l"] == 0]
    assert len(nuevos) >= 3
    assert nuevos[["forma5_ppp_l", "forma10_gf_l", "formaexp_dg_l", "racha_vict_l", "racha_cero_l", "rojas_prev_l",
                   "susp_n_l", "descanso_l", "once_previa_hab_l", "juego10_tiros_f_l"]].isna().all().all()
    pocos = completa[completa["n_prev_v"] < 3]
    assert pocos[["forma5_ppp_v", "forma5_dg_v", "formaexp_ppp_v"]].isna().all().all()
    # primer partido del torneo: sin tabla (posición y puntos por partido vacíos, no cero)
    j1 = completa[completa["tabla_pj_l"] == 0]
    assert j1[["tabla_pos_l", "tabla_ppp_l", "tabla_dgpp_l", "torneo_ppp_l"]].isna().all().all()
    # juego: sin estadísticas no hay medias (la posesión de ESPN empieza a mediados de 2012)
    sin_stats = completa[completa["juego_n_l"] < 5]
    assert sin_stats[["juego10_tiros_f_l", "juego10_xg_f_l", "juego10_corners_c_l"]].isna().all().all()
    assert completa.loc[completa["fecha_utc"] < "2012-06-01", "juego10_posesion_l"].isna().all()
    assert completa.loc[completa["fecha_utc"] > "2014-01-01", "juego10_posesion_l"].notna().mean() > 0.95
    # ninguna media o proporción es exactamente 0 de forma masiva (señal de vacíos convertidos en ceros)
    for c in ["juego10_tiros_f_l", "juego10_posesion_l", "juego10_xg_f_l", "sede_altitud", "liga_goles",
              "mercado_p_l", "arb_tarjetas", "asistencia5_l", "elo_l", "descanso_l"]:
        assert (completa[c] == 0).mean() < 0.001, c


# ==================================================================================================
# Comprobaciones independientes de algunas definiciones (reimplementadas con pandas)
# ==================================================================================================
def _historial_equipo(p: pd.DataFrame, equipo: str, antes: pd.Timestamp) -> pd.DataFrame:
    """Partidos jugados del equipo anteriores a `antes`, con gf, gc y puntos (más reciente al final)."""
    t = pd.to_datetime(p["fecha_utc"], utc=True)
    m = (p["estado"] == "jugado") & (t < antes) & ((p["local"] == equipo) | (p["visitante"] == equipo))
    h = p[m].assign(t=t[m]).sort_values("t")
    loc = h["local"] == equipo
    gf = np.where(loc, h["gl"].astype(int), h["gv"].astype(int))
    gc = np.where(loc, h["gv"].astype(int), h["gl"].astype(int))
    return h.assign(es_local=loc, gf=gf, gc=gc, pts=np.where(gf > gc, 3, np.where(gf == gc, 1, 0)))


def test_definiciones_contra_calculo_independiente(completa, insumos):
    p = insumos["p"]
    for pid in _muestra(completa, 25, SEMILLA + 5):
        fila = _fila(completa, pid)
        t = fila["fecha_utc"]
        for lado, equipo in (("l", fila["local"]), ("v", fila["visitante"])):
            h = _historial_equipo(p, equipo, t)
            assert fila[f"n_prev_{lado}"] == len(h)
            u5 = h.tail(5)
            if len(h) >= 3:
                assert fila[f"forma5_ppp_{lado}"] == pytest.approx(u5["pts"].mean())
                assert fila[f"forma5_gf_{lado}"] == pytest.approx(u5["gf"].mean())
                assert fila[f"forma5_gc_{lado}"] == pytest.approx(u5["gc"].mean())
            cond = h[h["es_local"]] if lado == "l" else h[~h["es_local"]]
            if len(cond) >= 5:
                assert fila[f"forma10_cond_dg_{lado}"] == pytest.approx((cond.tail(10)["gf"] - cond.tail(10)["gc"]).mean())
            if len(h):
                racha = 0
                for pts in h["pts"].iloc[::-1]:
                    if pts < 1:
                        break
                    racha += 1
                assert fila[f"racha_inv_{lado}"] == min(racha, 60)
                dias = (t - h["t"].iloc[-1]).total_seconds() / 86400
                assert fila[f"descanso_{lado}"] == pytest.approx(min(dias, V.MAX_DESCANSO))
            reg = h[(h["torneo"] == fila["torneo"]) & (h["fase"] == "regular")]
            assert fila[f"tabla_pts_{lado}"] == reg["pts"].sum()
            assert fila[f"tabla_pj_{lado}"] == len(reg)


def test_tabla_de_los_pendientes_coincide_con_la_oficial(completa):
    """La posición y los puntos de los pendientes del torneo en curso = datos/tabla_<torneo>.csv (ESPN)."""
    pend = completa[(completa["estado"] == "programado") & (completa["fase"] == "regular")]
    if len(pend) == 0:
        pytest.skip("no hay pendientes de fase regular")
    torneo = pend["torneo"].iloc[0]
    tipo, anio = torneo.split()
    ruta = V.DIR_DATOS / f"tabla_{tipo.lower()}{anio}.csv"
    if not ruta.exists():
        pytest.skip(f"no existe {ruta.name}")
    tabla = pd.read_csv(ruta).set_index("equipo")
    for r in pend.itertuples():
        for lado, eq in (("l", r.local), ("v", r.visitante)):
            assert getattr(r, f"tabla_pts_{lado}") == tabla.loc[eq, "PTS"]
            assert getattr(r, f"tabla_pj_{lado}") == tabla.loc[eq, "PJ"]
            assert getattr(r, f"tabla_pos_{lado}") == tabla.loc[eq, "pos"]


def test_clasificado_y_eliminado_son_conservadores(completa, insumos):
    """Ningún equipo marcado como eliminado jugó la postemporada y todo marcado como clasificado sí la jugó."""
    p = insumos["p"]
    post = p[(p["fase"] != "regular") & (p["estado"] == "jugado")]
    juegan = post.groupby("torneo").apply(lambda d: set(d["local"]) | set(d["visitante"]), include_groups=False).to_dict()
    reg = completa[(completa["fase"] == "regular") & (completa["estado"] == "jugado")
                   & completa["torneo"].isin(juegan) & (completa["torneo"] != "Clausura 2020")]
    n_clas = n_elim = 0
    for lado, col in (("l", "local"), ("v", "visitante")):
        clas = reg[reg[f"tabla_clasificado_{lado}"] == 1]
        elim = reg[reg[f"tabla_eliminado_{lado}"] == 1]
        n_clas += len(clas)
        n_elim += len(elim)
        # excepción real: Querétaro (10.º del Clausura 2023) quedó fuera de la reclasificación por un adeudo
        assert all(e in juegan[t] or (t, e) == ("Clausura 2023", "Querétaro") for t, e in zip(clas["torneo"], clas[col]))
        assert not any(e in juegan[t] for t, e in zip(elim["torneo"], elim[col]))
    assert n_clas > 100 and n_elim > 50


# ==================================================================================================
# Reglas y sedes
# ==================================================================================================
def test_formato_de_torneos_contra_los_datos(insumos):
    p = insumos["p"]
    jug = p[p["estado"] == "jugado"]
    for torneo, d in jug.groupby("torneo"):
        if V.orden_torneo(torneo) < V.orden_torneo("Clausura 2010") or torneo == "Clausura 2020":
            continue
        fm = V.formato_torneo(torneo)
        reg = d[d["fase"] == "regular"]
        pj = pd.concat([reg["local"], reg["visitante"]]).value_counts()
        if (p[(p["torneo"] == torneo) & (p["fase"] == "regular")]["estado"] == "jugado").all():
            assert pj.max() == fm["partidos"], torneo
        post = d[d["fase"] != "regular"]
        if len(post) and (post["fase"] == "final").any():
            en_post = set(post["local"]) | set(post["visitante"])
            assert len(en_post) == fm["zona"], (torneo, len(en_post), fm)


def test_ganador_de_series_por_regla(insumos):
    """El ganador por regla (global, tiempos extra, penales, gol de visitante, tabla) es quien sigue vivo."""
    _, est = V.construir(insumos["p"], tarjetas=insumos["tj"], alineaciones=insumos["al"], sedes=insumos["sd"],
                         devolver_estado=True, _calcular_desde=V._a_epoca("2100-01-01"))
    jug = insumos["p"][insumos["p"]["estado"] == "jugado"]
    sig = {"cuartos": "semifinal", "semifinal": "final"}
    bien = mal = 0
    for (tor, fase, a, b), _ in est.series.items():
        if fase not in sig or (tor, fase, a, b) not in est.series_cerradas:
            continue
        nxt = jug[(jug["torneo"] == tor) & (jug["fase"] == sig[fase])]
        vivos = [e for e in (a, b) if e in set(nxt["local"]) | set(nxt["visitante"])]
        if len(vivos) != 1:
            continue
        gan = [g for (o, f, g) in est.series_h2h[(a, b)] if o == V.orden_torneo(tor) and f == fase][0]
        bien += gan == vivos[0]
        mal += gan != vivos[0]
    assert bien > 250 and mal == 0, (bien, mal)
    assert all(g is not None for v in est.series_h2h.values() for (_, f, g) in v if f == "final")


def test_sedes_cubre_todos_los_estadios(insumos):
    sd, p = insumos["sd"], insumos["p"]
    assert not sd["estadio_id"].duplicated().any()
    assert len(V.ids_sin_sede(p, sd)) == 0, "hay estadios de ESPN desde 2010 sin fila en estadios_sedes.csv"
    con = sd[sd["sede"] != ""]
    for c in ("lat", "lon", "altitud_m"):
        assert pd.to_numeric(con[c], errors="coerce").notna().all()
        assert con.groupby("sede")[c].nunique().max() == 1, f"{c} debe ser único por sede"
    assert pd.to_numeric(con["lat"]).between(14, 33).all() and pd.to_numeric(con["lon"]).between(-118, -86).all()
    assert pd.to_numeric(con["altitud_m"]).between(0, 2800).all()
    assert (con["fuente"] != "").all() and con["confianza"].isin(["alta", "media", "baja"]).all()


def test_sede_y_viaje_tienen_sentido(completa):
    d = completa[(completa["fecha_utc"] >= "2014-01-01") & (completa["estado"] == "jugado")]
    assert d["sede_habitual_l"].mean() > 0.95
    # América - Cruz Azul en casa compartida: el visitante no viaja
    comp = d[d["sede_tambien_v"] == 1]
    assert len(comp) > 10 and (comp["sede_viaje_km_v"] == 0).all()
    assert set(comp["local"]) | set(comp["visitante"]) <= {"América", "Cruz Azul", "Atlante", "Atlas", "Puebla",
                                                             "Lobos BUAP", "Leones Negros", "Pumas"}
    tij = d[(d["local"] == "Tijuana") & (d["sede_imputada"] == 0)]
    assert (tij["sede_sintetico"] == 1).all() and (tij["sede_altura"] == 0).all()
    assert tij["sede_viaje_km_v"].min() > 900                       # Tijuana queda a más de 900 km de todos (Juárez: 994)
    tol = d[(d["local"] == "Toluca") & (d["sede_habitual_l"] == 1)]
    assert (tol["sede_altitud"] > 2600).all()
    assert d["sede_viaje_km_v"].max() < 3400


def test_acepta_la_tabla_tipada_de_datos_py(completa):
    """Con la tabla ya tipada de modelo/datos.py (si existe) el resultado es el mismo que con el CSV en texto."""
    datos = pytest.importorskip("datos")
    try:
        tipada = datos.cargar(limpiar_momios=False)
    except Exception as e:                                           # el módulo vecino puede estar en obra
        pytest.skip(f"datos.cargar() no disponible: {e}")
    otra = V.construir(tipada, _calcular_desde=V._a_epoca("2026-07-01"))
    ref = completa[completa["fecha_utc"] >= "2026-07-01"].reset_index(drop=True)
    pd.testing.assert_frame_equal(otra.reset_index(drop=True), ref, check_exact=True)
