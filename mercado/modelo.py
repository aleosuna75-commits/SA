"""Modelo de precisión: gradient boosting por cuantiles sobre rasgos del jugador y su contexto.

Sustituye la proyección central de la curva por celdas (pipeline.py) cuando hay señal individual.
Cada fila es un jugador en una foto anual (1-jul); los objetivos son el cambio de valor a h años.

Se trabaja en euros corrientes. Se probó deflactar con el índice de los 500 y de los 5,000 jugadores más
caros: la precisión fue prácticamente la misma (algo peor a 1 y 3 años) y el valor máximo quedó peor
calibrado, porque la élite se infló mucho más que el resto en 2017-2019. Sin deflactor hay un supuesto
menos: el modelo aprende el cambio nominal típico de cada tipo de jugador.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb

H_MODELO = [1, 3, 5, 8]          # los validados en la prueba retrospectiva (1, 3, 5) más 8; el resto se interpola
CUANTILES = [0.1, 0.5, 0.9]
COMP_EUROPA = ["CL", "EL", "UCOL"]
RASGOS = [
    "edad_f", "pi", "sub", "altura", "pie", "x",
    "mom6", "mom1", "mom2", "mom3", "dd", "anios_max", "exp", "edad_debut", "nval12", "meses_val",
    "les12", "les24",
    "comp", "club_x", "club_n", "rango", "cuota", "liga_med", "cambio_club", "d_liga", "estuvo",
    "club_ppg", "club_dg", "club_asist",
    "tit12", "cuota_tit", "cap12", "tit_sel12", "conv_sel12", "sale12", "entra12", "tarjetas12",
    "min12", "pj12", "ga90", "g90", "min_eu", "min_prev", "min_sel", "cuota_min", "min_carrera", "min_eu_carrera", "ga_carrera",
    "fichado12", "log_fee", "fee_x",
]
CATEGORICAS = ["pi", "sub", "pie", "comp"]
GRUPOS = {
    "Edad, posición y nivel de valor": ["edad_f", "pi", "sub", "altura", "pie", "x", "exp", "edad_debut"],
    "Trayectoria de su valor": ["mom6", "mom1", "mom2", "mom3", "dd", "anios_max", "nval12", "meses_val"],
    "Club y liga": ["comp", "club_x", "club_n", "rango", "cuota", "liga_med", "cambio_club", "d_liga", "estuvo", "fichado12", "log_fee", "fee_x",
                    "club_ppg", "club_dg", "club_asist"],
    "Minutos y producción": ["min12", "pj12", "ga90", "g90", "min_eu", "min_prev", "min_sel", "cuota_min", "min_carrera", "min_eu_carrera", "ga_carrera",
                             "tit12", "cuota_tit", "cap12", "tit_sel12", "conv_sel12", "sale12", "entra12", "tarjetas12"],
    "Lesiones": ["les12", "les24"],
}


def sin_deflactor(fotos):
    return fotos.groupby("anio").valor.apply(lambda s: 0.0)


def cargar_partidos(crudos):
    """Alineaciones, eventos y resultados de la fuente A (desde 2013): titularidades, capitanías, cambios, equipo."""
    leer = lambda t, **kw: pd.read_csv(crudos / f"{t}.csv.gz", low_memory=False, **kw)
    juegos = leer("games", usecols=["game_id", "date", "competition_type", "home_club_id", "attendance"], parse_dates=["date"])
    return {
        "juegos": juegos,
        "alineaciones": leer("game_lineups", usecols=["date", "game_id", "player_id", "type", "team_captain"], parse_dates=["date"]),
        "eventos": leer("game_events", usecols=["date", "type", "player_id", "player_in_id"], parse_dates=["date"]),
        "club_juegos": leer("club_games", usecols=["game_id", "club_id", "own_goals", "opponent_goals"]),
    }


def _foto(fecha):
    """Año de la foto (1-jul) a la que pertenece un hecho: todo lo ocurrido hasta el 30-jun cuenta para ese año."""
    return fecha.dt.year + (fecha.dt.month > 6)


def rasgos_partidos(f, partidos):
    """Agrega al panel los rasgos de alineaciones, eventos y resultados del club (12 meses previos a la foto)."""
    nuevos = ["club_ppg", "club_dg", "club_asist", "tit12", "cuota_tit", "cap12", "tit_sel12", "conv_sel12", "sale12", "entra12", "tarjetas12"]
    if partidos is None:
        return f.assign(**{c: np.nan for c in nuevos})
    J = partidos["juegos"]
    sel = J.set_index("game_id").competition_type.eq("national_team_competition")
    a = partidos["alineaciones"].assign(anio=lambda d: _foto(d.date))
    a["es_sel"] = a.game_id.map(sel).fillna(False).astype(bool)
    a["tit"] = a.type.eq("starting_lineup")
    club = a[~a.es_sel].groupby(["player_id", "anio"]).agg(tit12=("tit", "sum"), conv12=("tit", "size"), cap12=("team_captain", "sum")).reset_index()
    nac = a[a.es_sel].groupby(["player_id", "anio"]).agg(tit_sel12=("tit", "sum"), conv_sel12=("tit", "size")).reset_index()
    e = partidos["eventos"].assign(anio=lambda d: _foto(d.date))
    sale = e[e.type == "Substitutions"].groupby(["player_id", "anio"]).size().rename("sale12").reset_index()
    entra = e[e.type == "Substitutions"].dropna(subset=["player_in_id"]).groupby(["player_in_id", "anio"]).size().rename("entra12").reset_index().rename(columns={"player_in_id": "player_id"})
    tarj = e[e.type == "Cards"].groupby(["player_id", "anio"]).size().rename("tarjetas12").reset_index()
    for t in (club, nac, sale, entra, tarj):
        f = f.merge(t, on=["player_id", "anio"], how="left")
    hay = f.anio >= 2014                                     # las alineaciones empiezan en jul-2013
    en_liga = f.comp_t.notna() & hay
    for c in ["tit12", "conv12", "cap12", "tit_sel12", "conv_sel12", "sale12", "entra12", "tarjetas12"]:
        f[c] = np.where(en_liga, f[c].fillna(0), f[c].where(hay))
    f["cuota_tit"] = np.where(f.conv12 > 0, f.tit12 / f.conv12, np.nan)
    # resultados del club en liga doméstica
    cj = partidos["club_juegos"].merge(J[["game_id", "date", "competition_type", "home_club_id", "attendance"]], on="game_id")
    cj = cj[cj.competition_type == "domestic_league"].assign(anio=lambda d: _foto(d.date))
    cj["pts"] = np.where(cj.own_goals > cj.opponent_goals, 3, np.where(cj.own_goals == cj.opponent_goals, 1, 0))
    cj["dg"] = cj.own_goals - cj.opponent_goals
    cj["asist_local"] = cj.attendance.where((cj.home_club_id == cj.club_id) & (cj.attendance > 0))
    cg = cj.groupby(["club_id", "anio"]).agg(club_ppg=("pts", "mean"), club_dg=("dg", "mean"), club_asist=("asist_local", "mean"), n=("pts", "size")).reset_index()
    cg = cg[cg.n >= 10].drop(columns="n").rename(columns={"club_id": "club_t"})
    cg["club_asist"] = np.log(cg.club_asist)
    return f.merge(cg, on=["club_t", "anio"], how="left")


def construir(val, jug, les, apar, fich, corte, log_idx_de=sin_deflactor, partidos=None):
    """Panel jugador-año con rasgos. `log_idx_de(fotos)` devuelve el log-índice del mercado por año."""
    val = val.sort_values(["player_id", "date"]).copy()
    # La fuente B no trae club por fecha: se arrastra el último club conocido de A (hasta 400 días).
    conocido = val.date.where(val.club_t.notna()).groupby(val.player_id).ffill()
    fresco = (val.date - conocido).dt.days <= 400
    for c in ("club_t", "comp_t"):
        val[c] = val.groupby("player_id")[c].ffill().where(fresco)
    partes = []
    for anio in range(2005, corte.year + 1):
        ref = pd.Timestamp(anio, 7, 1)
        v = val[(val.date > ref - pd.Timedelta(days=365)) & (val.date <= ref)]
        g = v.groupby("player_id")
        u = g.tail(1)[["player_id", "market_value_in_eur", "date", "club_t", "comp_t"]].copy()
        u["nval12"] = u.player_id.map(g.size())
        # valor de hace ~6 meses: última valuación anterior a ref-150 días (dentro de 18 meses)
        v6 = val[(val.date > ref - pd.Timedelta(days=540)) & (val.date <= ref - pd.Timedelta(days=150))].groupby("player_id").market_value_in_eur.last()
        u["v6"] = u.player_id.map(v6)
        u["anio"] = anio
        u["meses_val"] = (ref - u.date).dt.days / 30.4
        partes.append(u)
    f = pd.concat(partes).rename(columns={"market_value_in_eur": "valor"})
    cod = {s: i for i, s in enumerate(sorted(jug.subpos.dropna().astype(str).unique()))}
    j = jug.assign(sub=jug.subpos.astype(str).map(cod), pie_c=jug.pie.map({"right": 0, "left": 1, "both": 2}),
                   pi=jug.pos.map({"Goalkeeper": 0, "Defender": 1, "Midfield": 2, "Attack": 3}))
    f = f.merge(j[["player_id", "pi", "sub", "pie_c", "altura", "nac"]], on="player_id").rename(columns={"pie_c": "pie"})
    ref = pd.to_datetime(f.anio.astype(str) + "-07-01")
    f["edad_f"] = (ref - f.nac).dt.days / 365.25
    f["edad"] = f.edad_f.astype(int)
    f = f[(f.edad >= 15) & (f.edad <= 48)].drop(columns="nac")
    f.loc[~(f.altura > 100), "altura"] = np.nan

    li = log_idx_de(f)
    f = f.sort_values(["player_id", "anio"]).reset_index(drop=True)
    f["li"] = f.anio.map(li)
    f["x"] = np.log(f.valor) - f.li + li.iloc[-1]                 # euros reales del último año
    g = f.groupby("player_id")
    for k in (1, 2, 3):
        prev = g[["anio", "x"]].shift(k)
        f[f"mom{k}"] = np.where(prev.anio == f.anio - k, f.x - prev.x, np.nan)
    f["mom6"] = np.log(f.valor / f.v6)
    cm = g.x.cummax()
    f["dd"] = f.x - cm
    f["es_max"] = f.x >= cm - 1e-9
    f["anio_max"] = f.anio.where(f.es_max).groupby(f.player_id).ffill()
    f["anios_max"] = f.anio - f.anio_max
    primero = g.anio.transform("min")
    f["exp"] = f.anio - primero
    f["edad_debut"] = f.edad_f - f.exp

    # lesiones: días de baja en los 12 y 24 meses previos
    le = les.assign(anio=les.from_date.dt.year + (les.from_date.dt.month > 6))
    dias = le.groupby(["player_id", "anio"]).days_missed.sum().rename("les12").reset_index()
    f = f.merge(dias, on=["player_id", "anio"], how="left")
    f["les12"] = f.les12.fillna(0)
    f["les24"] = f.les12 + f.groupby("player_id").les12.shift(1).fillna(0)

    # club y liga en la fecha de la foto (sólo fuente A)
    f["comp"] = f.comp_t.astype("category").cat.codes.replace(-1, np.nan)
    cl = f[f.club_t.notna()].groupby(["club_t", "anio"]).agg(club_v=("valor", "sum"), club_n=("valor", "size")).reset_index()
    f = f.merge(cl, on=["club_t", "anio"], how="left")
    f["club_x"] = np.log(f.club_v) - f.li + li.iloc[-1]
    f["cuota"] = np.log(f.valor / f.club_v)
    f["rango"] = f.groupby(["club_t", "anio"]).valor.rank(ascending=False, pct=True).where(f.club_t.notna())
    f["liga_med"] = f.groupby(["comp_t", "anio"]).x.transform("median").where(f.comp_t.notna())
    prev = f.groupby("player_id")[["club_t", "liga_med", "anio"]].shift(1)
    seguido = prev.anio == f.anio - 1
    f["cambio_club"] = np.where(seguido & f.club_t.notna() & prev.club_t.notna(), (f.club_t != prev.club_t).astype(float), np.nan)
    f["d_liga"] = np.where(seguido, f.liga_med - prev.liga_med, np.nan)

    # partidos: 12 meses previos a la foto
    a = apar.assign(anio=apar.date.dt.year + (apar.date.dt.month > 6))
    a["eu"] = a.competition_id.isin(COMP_EUROPA) * a.minutes_played
    a["sel"] = a.competition_id.isin(["FIWC", "EURO", "COPA", "AFCN", "AFAC"]) * a.minutes_played
    ag = a.groupby(["player_id", "anio"]).agg(min12=("minutes_played", "sum"), pj12=("game_id", "count"), goles=("goals", "sum"),
                                              asist=("assists", "sum"), min_eu=("eu", "sum"), min_sel=("sel", "sum")).reset_index()
    f = f.merge(ag, on=["player_id", "anio"], how="left")
    hay = f.anio >= 2013                                      # la tabla de partidos empieza en jul-2012
    en_liga = f.comp_t.notna() & hay
    for c in ["min12", "pj12", "goles", "asist", "min_eu", "min_sel"]:
        f[c] = np.where(en_liga, f[c].fillna(0), f[c].where(hay))
    f["ga90"] = np.where(f.min12 >= 450, (f.goles + f.asist) / f.min12 * 90, np.nan)
    f["g90"] = np.where(f.min12 >= 450, f.goles / f.min12 * 90, np.nan)
    f["min_prev"] = np.where(f.groupby("player_id").anio.shift(1) == f.anio - 1, f.groupby("player_id").min12.shift(1), np.nan)
    gj = f.groupby("player_id")
    f["min_carrera"] = gj.min12.cumsum().where(hay)          # acumulado en competiciones cubiertas hasta la foto
    f["min_eu_carrera"] = gj.min_eu.cumsum().where(hay)
    f["ga_carrera"] = (f.goles + f.asist).groupby(f.player_id).cumsum().where(hay)
    f["cuota_min"] = f.min12 / f.groupby(["club_t", "anio"]).min12.transform("max").where(f.club_t.notna())

    f = rasgos_partidos(f, partidos)

    # fichajes en los 12 meses previos
    t = fich[fich.transfer_date.notna()].assign(anio=lambda d: d.transfer_date.dt.year + (d.transfer_date.dt.month > 6))
    t = t[t.transfer_date <= pd.to_datetime(t.anio.astype(str) + "-07-01")]
    tg = t.sort_values("transfer_date").groupby(["player_id", "anio"]).agg(fee=("transfer_fee", "max")).reset_index()
    tg["fichado12"] = 1.0
    f = f.merge(tg, on=["player_id", "anio"], how="left")
    f["fichado12"] = f.fichado12.fillna(0)
    f["log_fee"] = np.where(f.fee > 0, np.log(f.fee.clip(lower=1)), np.nan)
    f["fee_x"] = f.log_fee - np.log(f.valor)

    # objetivos: cambio real a h años y supervivencia
    base = f[["player_id", "anio", "x"]]
    for h in range(1, 11):
        f = f.merge(base.assign(anio=base.anio - h).rename(columns={"x": f"x{h}"}), on=["player_id", "anio"], how="left")
    # Sesgo de selección: la fuente A incluye a un jugador porque ALGÚN DÍA jugó en una liga cubierta. Sus fotos
    # anteriores a esa entrada sólo existen porque después triunfó; usarlas enseñaría al modelo que todo
    # desconocido sube. Se marcan y se excluyen de entrenamiento y de evaluación.
    entrada = f[f.comp_t.notna()].groupby("player_id").anio.min()
    f["pre"] = f.comp_t.isna() & (f.player_id.map(entrada) > f.anio)
    f["estuvo"] = (f.player_id.map(entrada) <= f.anio).astype(float)   # ya pasó por una liga cubierta
    for K in (8,):                                            # máximo futuro dentro de K años (para el valor pico)
        f[f"pico{K}"] = f[[f"x{h}" for h in range(1, K + 1)]].max(axis=1)
    return f, li


def _params(objetivo, alpha=None):
    p = dict(objective=objetivo, learning_rate=0.05, num_leaves=63, min_data_in_leaf=80, bagging_fraction=0.8, bagging_freq=1,
             feature_fraction=0.8, lambda_l2=1.0, verbose=-1, num_threads=4, seed=7)
    if alpha is not None:
        p["alpha"] = alpha
    return p


def _ajustar(X, y, objetivo, alpha=None, rondas=350):
    datos = lgb.Dataset(X, label=y, categorical_feature=CATEGORICAS, free_raw_data=False)
    return lgb.train(_params(objetivo, alpha), datos, num_boost_round=rondas)


def entrenar(f, tope, horizontes=H_MODELO, cuantiles=CUANTILES, supervivencia=True, desde=2008, pico=False):
    """Modelos por horizonte usando sólo pares (año, año+h) con año+h <= tope."""
    modelos = {}
    f = f[~f.pre]
    if pico:                                                  # máximo de los próximos 8 años (incluye el valor actual)
        d = f[(f.anio >= 2005) & (f.anio + 8 <= tope) & f.pico8.notna()]
        y = np.maximum(d.pico8 - d.x, 0)
        for q in (0.5, 0.9):
            modelos[("pico", q)] = _ajustar(d[RASGOS], y, "quantile", q)
    for h in horizontes:
        d = f[(f.anio >= (desde if h < 8 else 2005)) & (f.anio + h <= tope) & (f.edad + h <= 46)]
        vivo = d[f"x{h}"].notna()
        if vivo.sum() < 3000:
            continue
        X, y = d.loc[vivo, RASGOS], (d.loc[vivo, f"x{h}"] - d.loc[vivo, "x"])
        for q in cuantiles:
            modelos[(h, q)] = _ajustar(X, y, "quantile", q)
        if supervivencia:
            modelos[(h, "s")] = _ajustar(d[RASGOS], vivo.astype(int), "binary", rondas=200)
    return modelos


def predecir(modelos, d, h, q):
    return modelos[(h, q)].predict(d[RASGOS])


# ---------------------------------------------------------------- prueba retrospectiva de origen móvil
CASOS = [("Erling Haaland", 2018, 8), ("Kylian Mbappé", 2018, 8), ("Kylian Mbappé", 2016, 5), ("Vinicius Junior", 2018, 5),
         ("Pedri", 2020, 5), ("Jamal Musiala", 2020, 5), ("Florian Wirtz", 2020, 5),
         ("Lamine Yamal", 2024, 2), ("Jude Bellingham", 2021, 5), ("Ansu Fati", 2020, 5), ("Dele Alli", 2018, 5), ("Philippe Coutinho", 2018, 5),
         ("Eden Hazard", 2019, 3), ("João Félix", 2019, 5)]


def inflacion_supuesta(li, origen):
    """Sólo aplica si se entrena con deflactor (con `sin_deflactor` vale 0): mitad del ritmo de 10 años."""
    return 0.5 * (li[origen] - li[origen - 10]) / 10


def retro(f, li, nombres, origenes=range(2016, 2026), horizontes=(1, 3, 5)):
    filas, picks, casos, zs = [], [], [], []
    por_origen = {}
    for o, h in {(o, h) for _, o, h in CASOS}:
        por_origen.setdefault(o, set()).add(h)
    for origen in sorted(set(origenes) | set(por_origen)):
        hs = sorted({h for h in horizontes if origen + h <= li.index.max() and origen in origenes} | por_origen.get(origen, set()))
        if not hs:
            continue
        qs = [0.02, 0.1, 0.5, 0.9, 0.98] if origen in por_origen else [0.1, 0.5, 0.9]
        mods = entrenar(f, origen, horizontes=hs, cuantiles=qs, supervivencia=False)
        infl = inflacion_supuesta(li, origen)
        base = f[(f.anio == origen) & ~f.pre]
        for h in hs:
            if (h, 0.5) not in mods:
                continue
            P = {q: predecir(mods, base, h, q) for q in qs}
            d = base.assign(p02=P.get(0.02, np.nan), p10=P[0.1], p50=P[0.5], p90=P[0.9], p98=P.get(0.98, np.nan))
            for nombre, o_, h_ in CASOS:
                if (o_, h_) != (origen, h):
                    continue
                c = d[d.player_id.map(nombres) == nombre].sort_values("valor").tail(1)
                if not len(c):
                    continue
                c = c.iloc[0]
                esc = lambda v: float(c.valor * np.exp(v + infl * h))
                real = None if np.isnan(c[f"x{h}"]) else float(c.valor * np.exp(c[f"x{h}"] - c.x + li[origen + h] - li[origen]))
                casos.append({"nombre": nombre, "origen": origen, "h": h, "edad": int(c.edad), "valor": float(c.valor),
                              "p02": esc(c.p02), "p10": esc(c.p10), "p50": esc(c.p50), "p90": esc(c.p90), "p98": esc(c.p98), "real": real})
            if origen not in origenes or h not in horizontes:
                continue
            d = d[d[f"x{h}"].notna()]
            y_real = d[f"x{h}"] - d.x
            y = y_real + li[origen + h] - li[origen]
            ed, liga = d.edad, d.comp_t.notna()
            # desvío normalizado por el ancho de su propia banda: sirve para calibrarla (ver calibrar)
            r = y_real - d.p50
            z = np.where(r >= 0, r / np.maximum(d.p90 - d.p50, 0.02), -r / np.maximum(d.p50 - d.p10, 0.02))
            zs.append(pd.DataFrame({"origen": origen, "h": h, "z": z}))
            grupos = {"todos": ed > 0, "liga": liga, "sub23": liga & (ed < 23), "23a28": liga & ed.between(23, 28), "29mas": liga & (ed >= 29),
                      "10M": np.exp(d.x) >= 1e7}
            for g, m in grupos.items():
                if m.sum() < 200:
                    continue
                e = lambda v: float(np.exp(np.median(np.abs(v[m]))) - 1)
                filas.append({"origen": origen, "h": h, "grupo": g, "n": int(m.sum()), "modelo": e(d.p50 + infl * h - y), "ingenuo": e(-y),
                              "modelo_real": e(d.p50 - y_real), "ingenuo_real": e(-y_real),
                              "cobertura": float(((y >= d.p10 + infl * h) & (y <= d.p90 + infl * h))[m].mean()),
                              "spearman": float(d.p50[m].corr(y_real[m], method="spearman"))})
            if h == 3:
                # ¿sirve para elegir? 50 apuestas sub-23 y 50 alertas de devaluación, contra el resto de su grupo
                vn = d.valor
                pob = d[liga & (ed <= 23) & (vn >= 1e6) & (vn <= 25e6)]
                sel = pob.nlargest(50, "p50")
                mult = lambda t: np.exp(t[f"x{h}"] - t.x + li[origen + h] - li[origen])
                viej = d[liga & (ed >= 27) & (vn >= 5e6)]
                al = viej.nsmallest(50, "p50")
                picks.append({"origen": origen, "n_pob": len(pob), "sel_mult": float(mult(sel).median()), "pob_mult": float(mult(pob).median()),
                              "sel_doble": float((mult(sel) >= 2).mean()), "pob_doble": float((mult(pob) >= 2).mean()),
                              "sel_cartera": float((sel.valor * mult(sel)).sum() / sel.valor.sum()), "pob_cartera": float((pob.valor * mult(pob)).sum() / pob.valor.sum()),
                              "n_viej": len(viej), "al_cae": float((mult(al) <= 0.6).mean()), "viej_cae": float((mult(viej) <= 0.6).mean()),
                              "al_mult": float(mult(al).median()), "viej_mult": float(mult(viej).median())})
    return pd.DataFrame(filas), pd.DataFrame(picks), casos, pd.concat(zs)


def calibrar(zs):
    """Factores por horizonte que escalan la banda p10-p90 hasta cubrir 80% y 95% fuera de muestra.

    Cada desvío real se mide en unidades del ancho de la banda del propio jugador (z); el cuantil 80 o 95 de
    z es el factor. Es una calibración conforme: no supone ninguna distribución.

    Devuelve (factores, cobertura dejando fuera cada origen): la cobertura que se reporta nunca usa
    el origen que evalúa.
    """
    salida = []
    for nivel in (0.8, 0.95):
        k = {int(h): float(g.z.quantile(nivel)) for h, g in zs.groupby("h")}
        cob = {}
        for h, g in zs.groupby("h"):
            dentro = [float((g2.z <= g[g.origen != o].z.quantile(nivel)).mean()) for o, g2 in g.groupby("origen")]
            cob[int(h)] = float(np.mean(dentro))
        salida += [k, cob]
    return salida                                             # k80, cobertura80, k95, cobertura95


def calibrar_pico(f, tope):
    """Corrige el sesgo del modelo de valor máximo con una prueba fuera de muestra.

    Entrena con orígenes cuyo desenlace a 8 años se conocía 6 años antes del tope y evalúa en los 4
    orígenes siguientes. Devuelve los factores (sobre el log-cociente) que dejan 50% y 90% de los
    máximos reales por debajo de la mediana y del techo previstos.
    """
    ft = f[~f.pre & f.pico8.notna()]
    ent = ft[(ft.anio >= 2005) & (ft.anio <= tope - 14)]
    pru = ft[ft.anio.between(tope - 11, tope - 8)]
    y = np.maximum(pru.pico8 - pru.x, 0).to_numpy()
    factores = []
    for q in (0.5, 0.9):
        m = _ajustar(ent[RASGOS], np.maximum(ent.pico8 - ent.x, 0), "quantile", q)
        pred = np.maximum(m.predict(pru[RASGOS]), 0)
        dice = pred > 0.02                                    # sólo donde el modelo prevé superar el valor actual
        rejilla = np.linspace(0.3, 1.5, 121)
        cob = np.array([(y[dice] <= c * pred[dice]).mean() for c in rejilla])
        factores.append(float(rejilla[np.abs(cob - q).argmin()]))
    # tope de cordura: ningún techo puede superar el múltiplo que sólo 1 de cada 200 jugadores alcanzó
    factores.append(float(np.quantile(np.maximum(ft.pico8 - ft.x, 0), 0.995)))
    return factores
