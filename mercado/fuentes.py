"""Fuentes adicionales: cada función agrega al panel jugador-año rasgos «como se sabían el 1 de julio de ese año».

Todas las tablas viven en datos_crudos/extra/ (las localizó y verificó el rastreo de fuentes; ver LEEME).
Regla común contra la fuga de información: un dato sólo cuenta para la foto del año Y si ya era conocible
el 1-jul de Y. Cuando una fuente no existe para un año, el rasgo queda vacío: nunca se rellena con ceros.
"""
from pathlib import Path

import numpy as np
import pandas as pd

# Tablas pequeñas ya procesadas que sí se versionan (cruces de identificadores y series por club o jugador-año).
DERIV = Path(__file__).resolve().parent / "derivados"

GRUPOS_EXTRA = {
    "Rendimiento en todas las competiciones": ["b_pj1", "b_pj2", "b_conv1", "b_tit1", "b_ga1", "b_goles1", "b_pj_carr", "b_ga_carr", "b_ncomp1", "b_gc1"],
    "Historial de traspasos": ["t_n", "t_ces", "t_cedido", "t_anios", "t_ult_fee", "t_ult_prima", "t_fee_max"],
    "Potencial y contrato (EA FC)": ["ea_ovr", "ea_pot", "ea_margen", "ea_d_ovr", "ea_d_pot", "ea_contrato", "ea_clausula", "ea_rep", "ea_lsal",
                                     "ea_val_tm", "ea_cedido", "ea_dias"],
    "Tabla y fuerza del club": ["tc_nivel", "tc_rango", "tc_ppg", "tc_asc", "elo", "elo_d1"],
}
RASGOS_EXTRA = [r for g in GRUPOS_EXTRA.values() for r in g]


def _fin_temporada(s):
    """'18/19' -> 2019 (termina el 30-jun); '2019' (año natural) -> 2020: sólo se conoce completa el 1-jul siguiente."""
    s = s.astype(str)
    partida = s.str.contains("/")
    dos = pd.to_numeric(s.str[-2:], errors="coerce")
    fin = np.where(dos >= 60, 1900 + dos, 2000 + dos)
    return pd.Series(np.where(partida, fin, pd.to_numeric(s, errors="coerce") + 1), index=s.index)


def rendimiento(X, corte):
    """Partidos, convocatorias, goles y asistencias por temporada en 1,643 competiciones (88 mil jugadores)."""
    c = ["player_id", "season_name", "competition_id", "nb_in_group", "nb_on_pitch", "goals", "assists", "subed_in", "goals_conceded"]
    d = pd.read_csv(X / "salimt_player_performances" / "player_performances.csv.gz", usecols=c, low_memory=False)
    d["anio"] = _fin_temporada(d.season_name)
    d = d[d.anio.notna() & (d.anio <= corte.year - 1)]       # la fuente se cortó en sep-2025: 25/26 y 2025 están incompletas
    d["anio"] = d.anio.astype(int)
    d["portero"] = d.goals.isna()
    d["goals"] = d.goals.fillna(0)
    d["gc"] = d.goals_conceded.where(d.portero)
    g = d.groupby(["player_id", "anio"]).agg(b_pj1=("nb_on_pitch", "sum"), b_conv1=("nb_in_group", "sum"), b_goles1=("goals", "sum"),
                                             asist=("assists", "sum"), entra=("subed_in", "sum"), b_ncomp1=("competition_id", "nunique"),
                                             gc=("gc", "sum"), portero=("portero", "max")).reset_index()
    g["b_tit1"] = np.where(g.b_pj1 > 0, (g.b_pj1 - g.entra) / g.b_pj1, np.nan)
    g["b_ga1"] = np.where(g.b_pj1 > 0, (g.b_goles1 + g.asist) / g.b_pj1, np.nan)
    g["b_gc1"] = np.where(g.portero & (g.b_pj1 > 0), g.gc / g.b_pj1, np.nan)
    g = g.sort_values(["player_id", "anio"])
    g["b_pj_carr"] = g.groupby("player_id").b_pj1.cumsum()
    g["b_ga_carr"] = (g.b_goles1 + g.asist).groupby(g.player_id).cumsum()
    previo = g[["player_id", "anio", "b_pj1"]].assign(anio=lambda t: t.anio + 1).rename(columns={"b_pj1": "b_pj2"})
    g = g.merge(previo, on=["player_id", "anio"], how="left")
    return g[["player_id", "anio", "b_pj1", "b_pj2", "b_conv1", "b_tit1", "b_ga1", "b_goles1", "b_pj_carr", "b_ga_carr", "b_ncomp1", "b_gc1"]]


def historial_traspasos(t, anios):
    """Movimientos anteriores al 1-jul de cada año: cuántos, cesiones, antigüedad en el club, último precio pagado."""
    t = t[t.tipo.isin(["Transfer", "Loan", "Return from loan"])].sort_values(["player_id", "fecha"])
    partes = []
    for y in anios:
        ref = pd.Timestamp(y, 7, 1)
        e = t[t.fecha < ref]
        g = e.groupby("player_id")
        ult = g.tail(1).set_index("player_id")
        pag = e[(e.pagado > 0)]
        up = pag.groupby("player_id").tail(1).set_index("player_id")
        r = pd.DataFrame({"t_n": e[e.tipo == "Transfer"].groupby("player_id").size(), "t_ces": e[e.tipo == "Loan"].groupby("player_id").size()})
        r = r.reindex(ult.index).fillna(0)
        r["t_cedido"] = (ult.tipo == "Loan").astype(float)
        r["t_anios"] = (ref - ult.fecha).dt.days / 365.25
        r["club_b"] = ult.a_id
        r["t_ult_fee"] = np.log(up.pagado).reindex(r.index)
        r["t_ult_prima"] = np.log(up.pagado / up.valor_t.where(up.valor_t > 0)).reindex(r.index)
        r["t_fee_max"] = np.log(pag.groupby("player_id").pagado.max()).reindex(r.index)
        partes.append(r.reset_index().assign(anio=y))
    return pd.concat(partes)


def _ea_tabla(X):
    """Todas las ediciones y actualizaciones de EA FC / FIFA disponibles, con fecha, llevadas a id de Transfermarkt."""
    c = ["player_id", "overall", "potential", "value_eur", "wage_eur", "release_clause_eur", "club_contract_valid_until_year",
         "international_reputation", "club_loaned_from"]
    a = pd.read_csv(X / "eafc_hf_jsulz" / "male_players_all_updates_slim.csv.gz", usecols=c + ["fifa_update_date"], low_memory=False).rename(columns={"fifa_update_date": "fecha"})
    b = pd.read_csv(X / "eafc24_hf_belkin7" / "male_players.csv.gz", usecols=c + ["update_as_of", "fifa_version"], low_memory=False).rename(columns={"update_as_of": "fecha"})
    b = b[b.fifa_version >= 24].drop(columns="fifa_version")
    d = pd.read_csv(X / "eafc26_gh_jawadk05" / "FC26_20250921.csv.gz", usecols=c + ["fifa_update_date"], low_memory=False).rename(columns={"fifa_update_date": "fecha"})
    # FC 25: el archivo no trae fecha. Sus datos incluyen fichajes de sep-2024; se fecha en el lanzamiento (27-sep-2024).
    e = pd.read_csv(X / "eafc25_hf_jmacd867" / "all_fifa_players.csv.gz", low_memory=False)
    dinero = lambda s: pd.to_numeric(s.astype(str).str.replace("€", "").str.replace("K", "e3").str.replace("M", "e6"), errors="coerce")
    e = pd.DataFrame({"player_id": e["Player ID"], "overall": pd.to_numeric(e["Overall Score"], errors="coerce"),
                      "potential": pd.to_numeric(e["Potential Score"], errors="coerce"), "value_eur": dinero(e["Value"]), "wage_eur": dinero(e["Wage"]),
                      "release_clause_eur": dinero(e["Release Clause"]), "club_contract_valid_until_year": pd.to_numeric(e["Contract End"], errors="coerce"),
                      "international_reputation": np.nan, "club_loaned_from": np.where(e["Loan End"].notna(), "x", None), "fecha": "2024-09-27"})
    t = pd.concat([a, b, e, d], ignore_index=True)
    t["fecha"] = pd.to_datetime(t.fecha, errors="coerce")
    xw = pd.read_csv(DERIV / "sofifa_tm_xwalk.csv.gz")
    xw = xw[xw.tier.isin(["1_exact", "2_subset", "3_short"]) | xw.nat_ok]          # el tramo dudoso sólo si la nacionalidad coincide
    t = t.merge(xw[["sofifa_id", "tm_id"]], left_on="player_id", right_on="sofifa_id").drop(columns=["player_id", "sofifa_id"])
    return t[t.fecha.notna()].rename(columns={"tm_id": "player_id"}).sort_values("fecha")


def ea(X, anios):
    """Media, potencial, contrato y cláusula según EA: la fila más reciente anterior al 1-jul, de no más de 400 días.

    Los archivos originales pesan gigas; el resultado por jugador-año se guarda en derivados/ y se reutiliza.
    """
    cache = DERIV / "ea_por_anio.csv.gz"
    if cache.exists():
        return pd.read_csv(cache)
    t = _ea_tabla(X)
    partes = []
    for y in anios:
        ref = pd.Timestamp(y, 7, 1)
        s = t[(t.fecha <= ref) & (t.fecha > ref - pd.Timedelta(days=400))].groupby("player_id").tail(1)
        if not len(s):
            continue
        r = pd.DataFrame({"player_id": s.player_id, "anio": y, "ea_ovr": s.overall, "ea_pot": s.potential, "ea_margen": s.potential - s.overall,
                          "ea_contrato": (s.club_contract_valid_until_year - y).clip(-1, 8), "ea_rep": s.international_reputation,
                          "ea_clausula": np.log(s.release_clause_eur.where(s.release_clause_eur > 0) / s.value_eur.where(s.value_eur > 0)),
                          "ea_lsal": np.log1p(s.wage_eur), "ea_lval": np.log(s.value_eur.where(s.value_eur > 0)),
                          "ea_cedido": s.club_loaned_from.notna().astype(float), "ea_dias": (ref - s.fecha).dt.days})
        partes.append(r)
    r = pd.concat(partes).sort_values(["player_id", "anio"])
    previo = r[["player_id", "anio", "ea_ovr", "ea_pot"]].assign(anio=lambda d: d.anio + 1).rename(columns={"ea_ovr": "o0", "ea_pot": "p0"})
    r = r.merge(previo, on=["player_id", "anio"], how="left")
    r["ea_d_ovr"], r["ea_d_pot"] = r.ea_ovr - r.o0, r.ea_pot - r.p0
    r = r.drop(columns=["o0", "p0"]).round(4)
    r.to_csv(cache, index=False)
    return r


def tabla_club():
    """Nivel de la liga, puesto y puntos por partido del club en su última temporada completa conocida."""
    d = pd.read_csv(DERIV / "club_season_asof.csv.gz")
    d = d[~d.partial & (d.season_total_matches >= 10)].copy()
    d["tc_nivel"] = d.season_league_level_level_number
    d["tc_rango"] = d.season_rank / d.groupby(["competition_id", "season_id"]).season_rank.transform("max")
    d["tc_ppg"] = (3 * d.season_wins + d.season_draws) / d.season_total_matches
    d = d.sort_values(["club_id", "known_year"])
    ant = d.groupby("club_id")[["known_year", "tc_nivel"]].shift(1)
    d["tc_asc"] = np.where(ant.known_year == d.known_year - 1, ant.tc_nivel - d.tc_nivel, np.nan)     # +1 ascendió, -1 descendió
    return d.rename(columns={"club_id": "club_ref", "known_year": "anio"})[["club_ref", "anio", "tc_nivel", "tc_rango", "tc_ppg", "tc_asc"]].drop_duplicates(["club_ref", "anio"])


def elo():
    """Elo del club el 1-jul (ClubElo vía espejo abierto); sólo valores vivos, no arrastrados."""
    d = pd.read_csv(DERIV / "tm_club_elo_jul1.csv.gz")
    d = d[d.fresh & d.tm_club_id.notna()].drop_duplicates(["anio", "tm_club_id"])
    d = d.rename(columns={"tm_club_id": "club_ref"})[["club_ref", "anio", "elo"]]
    ant = d.assign(anio=d.anio + 1).rename(columns={"elo": "e0"})
    d = d.merge(ant, on=["club_ref", "anio"], how="left")
    d["elo_d1"] = d.elo - d.e0
    return d.drop(columns="e0")


def agregar(f, crudos, traspasos, corte):
    """Pega todos los rasgos adicionales al panel. `traspasos` es la tabla unificada de precio.tabla_traspasos."""
    X = crudos / "extra"
    anios = range(int(f.anio.min()), int(f.anio.max()) + 1)
    f = f.merge(rendimiento(X, corte), on=["player_id", "anio"], how="left")
    f = f.merge(historial_traspasos(traspasos, anios), on=["player_id", "anio"], how="left")
    e = ea(X, range(2015, int(f.anio.max()) + 1))
    f = f.merge(e, on=["player_id", "anio"], how="left")
    f["ea_val_tm"] = f.ea_lval - np.log(f.valor)
    f["club_ref"] = f.club_t.fillna(f.club_b)                # club en la fecha: fuente A; si no, el del último traspaso
    f = f.merge(tabla_club(), on=["club_ref", "anio"], how="left").merge(elo(), on=["club_ref", "anio"], how="left")
    # La fuente de rendimiento y la de tablas se cortaron en sep-2025: en la foto más reciente no existen. Para los
    # jugadores de ligas con partidos fechados (fuente A) se reconstruyen con esos partidos, que sí llegan al corte;
    # sin esto el modelo leería "sin datos" (típico de jugadores desconocidos) justo en los jugadores más importantes.
    u = (f.anio == corte.year) & f.comp_t.notna() & f.b_pj1.isna()
    previa = f[["player_id", "anio", "b_pj1", "b_pj_carr", "b_ga_carr"]].assign(anio=lambda d: d.anio + 1).set_index(["player_id", "anio"])
    ix = pd.MultiIndex.from_frame(f.loc[u, ["player_id", "anio"]])
    ga = (f.goles + f.asist)[u]
    f.loc[u, "b_pj1"] = f.pj12[u]
    f.loc[u, "b_conv1"] = f.conv12[u]
    f.loc[u, "b_tit1"] = f.cuota_tit[u] * f.conv12[u] / f.pj12[u].where(f.pj12[u] > 0)
    f.loc[u, "b_goles1"] = f.goles[u]
    f.loc[u, "b_ga1"] = ga / f.pj12[u].where(f.pj12[u] > 0)
    f.loc[u, "b_pj2"] = previa.b_pj1.reindex(ix).to_numpy()
    f.loc[u, "b_pj_carr"] = previa.b_pj_carr.reindex(ix).fillna(0).to_numpy() + f.pj12[u].fillna(0)
    f.loc[u, "b_ga_carr"] = previa.b_ga_carr.reindex(ix).fillna(0).to_numpy() + ga.fillna(0)
    f.loc[u, "b_ncomp1"] = 2.0
    v = (f.anio == corte.year) & f.comp_t.notna() & f.tc_ppg.isna()
    f.loc[v, "tc_ppg"] = f.club_ppg[v]
    f.loc[v, "tc_nivel"] = 1.0
    return f
