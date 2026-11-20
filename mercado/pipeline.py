#!/usr/bin/env python3
"""Mercado: proyección actuarial del valor de mercado de futbolistas.

Fuentes (ambas derivadas de Transfermarkt, abiertas):
  A. dcaribou/transfermarkt-datasets  -> primeras divisiones, corte más reciente, partidos y fichajes
  B. salimt/football-datasets         -> 92 mil perfiles, divisiones inferiores, lesiones
Se bajan a mercado/datos_crudos/ (no se versionan) y de ahí sale todo lo que consume la página.

Modelo, en tres capas:
  1. Base: factores de desarrollo edad-a-edad del valor REAL (deflactado por un índice del mercado),
     por posición y tramo de valor, remuestreados en simulación -> bandas p10/p50/p90 por horizonte,
     máximo de carrera y probabilidad de seguir valuado.
  2. Ajuste individual: regresión lineal sobre el residuo de la capa 1 con tendencia reciente,
     distancia al máximo propio y días de lesión. Lineal a propósito: cada factor se puede explicar.
  3. Precedentes: jugadores históricos de misma posición, edad y valor, y qué les pasó después.

Uso:  python3 mercado/pipeline.py [--sin-descarga]
"""
import argparse
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent
CRUDOS = RAIZ / "datos_crudos"
SALIDA = RAIZ / "web" / "datos"
URL_A = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/{}.csv.gz"
TABLAS_A = ["players", "player_valuations", "clubs", "competitions", "appearances", "transfers"]
REPO_B = "https://github.com/salimt/football-datasets"
TABLAS_B = ["player_latest_market_value", "player_market_value", "player_profiles", "team_details",
            "player_injuries", "team_competitions_seasons"]
B = CRUDOS / "fd" / "datalake" / "transfermarkt"

POSICIONES = ["Goalkeeper", "Defender", "Midfield", "Attack"]
EDAD_MIN, EDAD_MAX = 16, 44                      # la proyección termina a los 44
TRAMOS = [3e5, 1e6, 3e6, 1e7, 3e7, 6e7, 1e8]     # cortes de valor real (euros de hoy)
BINS = np.geomspace(10e3, 200e6, 27)             # valores de arranque de los perfiles
HMAX = EDAD_MAX - EDAD_MIN
N_SIM = 3000
MIN_OBS = 40
PRIMER_ANIO = 2010                               # transiciones anteriores: cobertura pobre
H_AJUSTE = [1, 2, 3, 5]
FACTORES = ["mom", "mom_joven", "dd", "les"]
VIGENTE_DESDE = "2025-01-01"                     # última valuación mínima para aparecer en el sitio
N_TROZOS = 256


# ---------------------------------------------------------------- descarga y lectura
def descargar():
    CRUDOS.mkdir(exist_ok=True)
    for t in TABLAS_A:
        print("bajando", t)
        with urllib.request.urlopen(URL_A.format(t), timeout=600) as r, open(CRUDOS / f"{t}.csv.gz", "wb") as f:
            shutil.copyfileobj(r, f)
    fd = CRUDOS / "fd"
    shutil.rmtree(fd, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", REPO_B, str(fd)], check=True)
    rutas = [f"datalake/transfermarkt/{t}" for t in TABLAS_B]
    subprocess.run(["git", "-C", str(fd), "sparse-checkout", "set", "--no-cone", *rutas], check=True)
    subprocess.run(["git", "-C", str(fd), "checkout", "-q"], check=True)


def leer_a(t, **kw):
    return pd.read_csv(CRUDOS / f"{t}.csv.gz", **kw)


def leer_b(t, archivo=None, **kw):
    return pd.read_csv(B / t / f"{archivo or t}.csv", low_memory=False, **kw)


def sin_id(s):
    """La fuente B pega el id al nombre: 'Silvio Adzic (1)' -> 'Silvio Adzic'."""
    return s.astype(str).str.replace(r"\s*\(\d+\)$", "", regex=True)


def cargar():
    """Une las dos fuentes en: jugadores, valuaciones, clubes, lesiones, partidos, fichajes."""
    ja = leer_a("players", parse_dates=["date_of_birth"])
    jb = leer_b("player_profiles", parse_dates=["date_of_birth"])
    temporada = ja.last_season.max()

    a = pd.DataFrame({
        "player_id": ja.player_id, "nombre": ja.name, "nac": ja.date_of_birth, "pos": ja.position,
        "subpos": ja.sub_position, "pie": ja.foot, "altura": ja.height_in_cm, "pais": ja.country_of_citizenship,
        "club_id": ja.current_club_id, "club_nombre": ja.current_club_name,
        "contrato": ja.contract_expiration_date.astype(str).str[:7].replace("nan", ""),
        "agente": ja.agent_name, "cedido_de": "", "fresco": ja.last_season == temporada,
    })
    sub = jb.position.astype(str).str.split(" - ").str[1]
    b = pd.DataFrame({
        "player_id": jb.player_id, "nombre": sin_id(jb.player_name), "nac": jb.date_of_birth, "pos": jb.main_position,
        "subpos": sub, "pie": jb.foot, "altura": jb.height, "pais": jb.citizenship.astype(str).str.split("  ").str[0],
        "club_id": jb.current_club_id, "club_nombre": sin_id(jb.current_club_name),
        "contrato": jb.contract_expires.astype(str).str[:7].replace("nan", ""),
        "agente": jb.player_agent_name, "cedido_de": sin_id(jb.on_loan_from_club_name.fillna("")), "fresco": False,
    })
    # A manda cuando el jugador sigue en una liga que A cubre (su corte es más reciente); si no, B.
    a_fresco = a[a.fresco]
    resto_b = b[~b.player_id.isin(a_fresco.player_id)]
    resto_a = a[~a.fresco & ~a.player_id.isin(b.player_id)]
    jug = pd.concat([a_fresco, resto_b, resto_a], ignore_index=True)
    jug = jug[jug.pos.isin(POSICIONES) & jug.nac.notna() & jug.nombre.notna() & ~jug.nombre.isin(["nan", ""])]

    va = leer_a("player_valuations")[["player_id", "date", "market_value_in_eur"]]
    cols = {"date_unix": "date", "value": "market_value_in_eur"}
    val = pd.concat([va, leer_b("player_market_value").rename(columns=cols),
                     leer_b("player_latest_market_value").rename(columns=cols)])
    val["date"] = pd.to_datetime(val.date, errors="coerce")
    val = val[val.date.notna() & (val.market_value_in_eur > 0)].drop_duplicates(["player_id", "date"])
    val = val[val.player_id.isin(jug.player_id)].sort_values(["player_id", "date"])

    # ---- clubes: liga, país y nivel de división
    comps = leer_a("competitions").set_index("competition_id")
    ca = leer_a("clubs")
    liga_a = jug[jug.fresco].groupby("club_id").club_nombre.first().to_frame("nombre")
    comp_de = ja[ja.last_season == temporada].groupby("current_club_id").current_club_domestic_competition_id.first()
    liga_a["comp"] = comp_de.reindex(liga_a.index)
    liga_a = liga_a[liga_a.comp.isin(comps.index)]
    liga_a["pais"] = liga_a.comp.map(comps.country_name)
    liga_a["nivel"] = 1
    liga_a["estadio"] = ca.set_index("club_id").stadium_name.reindex(liga_a.index).fillna("")

    tc = leer_b("team_competitions_seasons")
    tc = tc[tc.season_league_level_level_number.notna()].sort_values("season_id").groupby("club_id").tail(1).set_index("club_id")
    td = leer_b("team_details").drop_duplicates("club_id").set_index("club_id")
    # nombre presentable de las ligas de A: el que más usa B para esos mismos clubes
    bonito = tc.competition_name.reindex(liga_a.index).groupby(liga_a.comp).agg(lambda s: s.mode().iat[0] if s.notna().any() else None)
    liga_a["liga"] = liga_a.comp.map(bonito).fillna(liga_a.comp.map(comps.name).str.replace("-", " ").str.title())

    pais_de_liga = td.country_name.groupby(tc.competition_name.reindex(td.index)).agg(lambda s: s.mode().iat[0] if s.notna().any() else None)
    ids_b = jug.loc[~jug.club_id.isin(liga_a.index), "club_id"].dropna().unique()
    liga_b = pd.DataFrame(index=pd.Index(ids_b, name="club_id"))
    liga_b["nombre"] = jug.groupby("club_id").club_nombre.first().reindex(liga_b.index)
    liga_b["liga"] = tc.competition_name.reindex(liga_b.index)
    liga_b["nivel"] = tc.season_league_level_level_number.reindex(liga_b.index)
    liga_b["pais"] = td.country_name.reindex(liga_b.index).fillna(liga_b.liga.map(pais_de_liga))
    liga_b["estadio"] = ""
    clubes = pd.concat([liga_a.drop(columns="comp"), liga_b])
    libre = clubes.nombre.isin(["Without Club", "Retired", "Career break", "Unknown"])
    clubes.loc[libre, ["liga", "pais", "nivel"]] = ["Sin club", "", 0]
    clubes["nombre"] = clubes.nombre.where(clubes.nombre.notna() & (clubes.nombre != "nan"), "Club " + clubes.index.astype(str))
    clubes["estadio"] = clubes.estadio.fillna("")
    clubes["liga"] = clubes.liga.fillna("Sin liga identificada")
    clubes["pais"] = clubes.pais.fillna("")
    clubes["nivel"] = clubes.nivel.fillna(9).astype(int)

    les = leer_b("player_injuries", "player_injuries_updated_20260929", parse_dates=["from_date"])
    les = les[les.from_date.notna() & les.player_id.isin(jug.player_id)]
    apar = leer_a("appearances", usecols=["game_id", "player_id", "date", "goals", "assists", "minutes_played"], parse_dates=["date"])
    fich = leer_a("transfers", parse_dates=["transfer_date"])
    return jug, val, clubes, les, apar, fich


# ---------------------------------------------------------------- fotos anuales y panel
def fotos_anuales(val, jug, les, corte):
    """Una fila por jugador y año: último valor conocido al 1-jul (no más viejo de 12 meses)."""
    partes = []
    for anio in range(2005, corte.year + 1):
        ref = pd.Timestamp(anio, 7, 1)
        v = val[(val.date > ref - pd.Timedelta(days=365)) & (val.date <= ref)]
        v = v.groupby("player_id").tail(1)[["player_id", "market_value_in_eur"]].copy()
        v["anio"] = anio
        partes.append(v)
    f = pd.concat(partes).rename(columns={"market_value_in_eur": "valor"})
    f = f.merge(jug[["player_id", "pos", "nac"]], on="player_id")
    ref = pd.to_datetime(f.anio.astype(str) + "-07-01")
    f["edad"] = ((ref - f.nac).dt.days / 365.25).astype(int)
    f = f[(f.edad >= EDAD_MIN) & (f.edad <= 48)].drop(columns="nac")
    # días de lesión en los 12 meses previos a cada foto
    le = les.assign(anio=les.from_date.dt.year + (les.from_date.dt.month > 6))
    dias = le.groupby(["player_id", "anio"]).days_missed.sum().rename("les_dias").reset_index()
    return f.merge(dias, on=["player_id", "anio"], how="left").fillna({"les_dias": 0})


def indice_inflacion(fotos):
    """Canasta de rango fijo: media del log-valor de los 500 jugadores más caros de cada año."""
    return fotos.groupby("anio").valor.apply(lambda s: np.log(s.nlargest(500)).mean())


def armar_panel(fotos, log_idx, anio_base, ultimo_anio):
    """Valor real (euros del año base), factores individuales y valores futuros conocidos a `ultimo_anio`."""
    f = fotos[fotos.anio <= ultimo_anio].sort_values(["player_id", "anio"]).copy()
    f["x"] = np.log(f.valor) + log_idx[anio_base] - f.anio.map(log_idx)
    previo = f.groupby("player_id")[["anio", "x"]].shift(1)
    seguido = previo.anio == f.anio - 1
    f["mom"] = np.where(seguido, (f.x - previo.x).clip(-1.5, 1.5), 0.0)
    f["nuevo"] = (~seguido).astype(float)
    f["mom_joven"] = f.mom * (f.edad < 23)
    f["dd"] = (f.x - f.groupby("player_id").x.cummax()).clip(lower=-3)
    f["les"] = (f.les_dias / 100).clip(upper=3)
    f["pico_futuro"] = f[::-1].groupby("player_id").x.cummax()[::-1]
    base = f[["player_id", "anio", "x"]]
    for h in sorted(set(H_AJUSTE) | {1}):
        f = f.merge(base.assign(anio=base.anio - h).rename(columns={"x": f"x{h}"}), on=["player_id", "anio"], how="left")
    f["tramo"] = np.digitize(np.exp(f.x), TRAMOS)
    f["e"] = f.edad.clip(upper=EDAD_MAX)
    f["b"] = bin_de(f.x)
    f["pi"] = f.pos.map(POSICIONES.index)
    return f


def bin_de(x):
    return np.abs(np.log(BINS)[None, :] - np.asarray(x)[:, None]).argmin(axis=1)


# ---------------------------------------------------------------- capa 1: celdas y simulación
def ajustar_celdas(panel, ultimo_anio):
    """Para cada (posición, edad, tramo): deltas observados y prob. de dejar de estar valuado."""
    t = panel[(panel.anio >= PRIMER_ANIO) & (panel.anio < ultimo_anio)]
    pos, edad, tramo = t.pi.to_numpy(), t.e.to_numpy(), t.tramo.to_numpy()
    delta, salio = (t.x1 - t.x).to_numpy(), t.x1.isna().to_numpy()
    celdas = {}
    for p in range(4):
        for e in range(EDAD_MIN, EDAD_MAX + 1):
            for tr in range(len(TRAMOS) + 1):
                for m in ((pos == p) & (edad == e), edad == e, np.abs(edad - e) <= 2, np.abs(edad - e) <= 5, edad > 0):
                    m = m & (tramo == tr)
                    d = delta[m & ~salio]
                    if len(d) >= MIN_OBS:
                        break
                celdas[(p, e, tr)] = (d, float(salio[m].mean()))
    return celdas, len(t), float(salio.mean())


def simular(celdas, rng):
    """Q[pos, edad, bin, h, 3] cociente valor futuro/actual; S supervivencia; PICO [.,.,.,2]; EP edad del pico."""
    nb, ne = len(BINS), EDAD_MAX - EDAD_MIN
    Q = np.full((4, ne, nb, HMAX, 3), np.nan)
    S = np.full((4, ne, nb, HMAX), np.nan)
    PICO, EP = np.ones((4, ne, nb, 2)), np.zeros((4, ne, nb), int)
    x0 = np.log(BINS)
    for p in range(4):
        for edad in range(EDAD_MIN, EDAD_MAX):
            x = np.repeat(x0[:, None], N_SIM, axis=1)
            vivo = np.ones_like(x, dtype=bool)
            maximo, edad_max = x.copy(), np.full(x.shape, edad)
            for h in range(1, EDAD_MAX - edad + 1):
                tramo = np.digitize(np.exp(x), TRAMOS)
                for tr in range(len(TRAMOS) + 1):
                    m = (tramo == tr) & vivo
                    n = int(m.sum())
                    if not n:
                        continue
                    d, p_salir = celdas[(p, edad + h - 1, tr)]
                    x[m] += rng.choice(d, n)
                    sale = np.zeros_like(m)
                    sale[m] = rng.random(n) < p_salir
                    vivo &= ~sale
                mejora = vivo & (x > maximo)
                maximo[mejora], edad_max[mejora] = x[mejora], edad + h
                s = vivo.mean(axis=1)
                with np.errstate(all="ignore"):
                    q = np.nanquantile(np.where(vivo, x, np.nan), [0.1, 0.5, 0.9], axis=1).T - x0[:, None]
                ok = vivo.sum(axis=1) >= 30          # con menos trayectorias vivas la banda no significa nada
                Q[p, edad - EDAD_MIN, ok, h - 1] = np.exp(q[ok])
                S[p, edad - EDAD_MIN, :, h - 1] = s
            PICO[p, edad - EDAD_MIN] = np.exp(np.quantile(maximo, [0.5, 0.9], axis=1).T - x0[:, None])
            EP[p, edad - EDAD_MIN] = np.median(edad_max, axis=1)
    return Q, S, PICO, EP


# ---------------------------------------------------------------- capa 2: ajuste individual
def mediana_base(Q, d, h):
    e = d.e.to_numpy().clip(EDAD_MIN, EDAD_MAX - 1) - EDAD_MIN
    with np.errstate(all="ignore"):
        return np.log(Q[d.pi.to_numpy(), e, d.b.to_numpy(), h - 1, :])


def regresion_mediana(X, y, vueltas=25):
    """Regresión a la mediana (mínimos desvíos absolutos) por mínimos cuadrados reponderados.

    El cambio de valor es asimétrico (unos pocos se disparan): la media sesga la proyección central.
    """
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(vueltas):
        w = 1 / np.maximum(np.abs(y - X @ b), 1e-3)
        b = np.linalg.lstsq(X * w[:, None] ** 0.5, y * w ** 0.5, rcond=None)[0]
    return b


def ajustar_factores(panel, Q, ultimo_anio):
    """Regresión mediana del residuo (cambio real observado - mediana de la capa 1) contra los factores, por horizonte."""
    betas = {}
    for h in H_AJUSTE:
        d = panel[(panel.anio >= PRIMER_ANIO + 1) & (panel.anio + h <= ultimo_anio) & panel[f"x{h}"].notna() & (panel.e + h <= EDAD_MAX)]
        y = (d[f"x{h}"] - d.x).to_numpy() - mediana_base(Q, d, h)[:, 1]
        ok = np.isfinite(y)
        X = np.column_stack([np.ones(ok.sum())] + [d[c].to_numpy()[ok] for c in FACTORES])
        betas[h] = regresion_mediana(X, y[ok])
    return betas


def backtest(fotos, log_idx, rng, origen=2021):
    """Entrena sólo con lo conocido a jul-`origen` y compara contra lo que pasó después."""
    panel = armar_panel(fotos, log_idx, origen, origen)
    celdas, _, _ = ajustar_celdas(panel, origen)
    Q, *_ = simular(celdas, rng)
    betas = ajustar_factores(panel, Q, origen)
    infl = (log_idx[origen] - log_idx[origen - 10]) / 10
    base = panel[(panel.anio == origen) & (panel.e < EDAD_MAX)]
    filas = []
    for h in (1, 3, 5):
        real = fotos[fotos.anio == origen + h][["player_id", "valor"]].rename(columns={"valor": "real"})
        d = base.merge(real, on="player_id", how="left")
        d = d[d.e + h <= EDAD_MAX]
        q = mediana_base(Q, d, h)
        s = betas[h][0] + sum(betas[h][i + 1] * d[c].to_numpy() for i, c in enumerate(FACTORES))
        lv = np.log(d.valor.to_numpy())
        obs = d.real.notna().to_numpy() & np.isfinite(q[:, 1])
        y = np.log(d.real.to_numpy()[obs])
        e_base = np.abs(lv[obs] + q[obs, 1] + infl * h - y)
        e_aj = np.abs(lv[obs] + q[obs, 1] + s[obs] + infl * h - y)
        e_ing = np.abs(lv[obs] - y)
        dentro = (y >= lv[obs] + q[obs, 0] + s[obs] + infl * h) & (y <= lv[obs] + q[obs, 2] + s[obs] + infl * h)
        ed = d.edad.to_numpy()[obs]
        grupos = {"todos": ed > 0, "sub23": ed < 23, "23a28": (ed >= 23) & (ed <= 28), "29a33": (ed >= 29) & (ed <= 33), "34mas": ed >= 34}
        err = lambda v, m: round(float(np.exp(np.median(v[m])) - 1), 3)
        for g, m in grupos.items():
            if m.sum() < 30:
                continue
            filas.append({"horizonte": h, "grupo": g, "n": int(m.sum()), "error_modelo": err(e_aj, m), "error_base": err(e_base, m),
                          "error_ingenuo": err(e_ing, m), "cobertura": round(float(dentro[m].mean()), 3)})
    return {"origen": origen, "inflacion_supuesta": round(float(np.exp(infl) - 1), 4), "filas": filas}


# ---------------------------------------------------------------- capa 3: precedentes
def precedentes(panel, actuales, nombres, anio_tope):
    """Para cada jugador vigente: los 5 históricos más parecidos (posición, edad, valor real, tendencia)."""
    h = panel[(panel.anio <= anio_tope) & (panel.anio >= 2008)]
    grupos = {k: g for k, g in h.groupby(["pi", "e"])}
    salida = {}
    for (pi, e), act in actuales.groupby(["pi", "e"]):
        g = grupos.get((pi, e))
        if g is None or len(g) < 20:
            continue
        gx, gm, gid = g.x.to_numpy(), g.mom.to_numpy(), g.player_id.to_numpy()
        g3, gp, ga = g.x3.to_numpy(), g.pico_futuro.to_numpy(), g.anio.to_numpy()
        for pid, x, mom in zip(act.player_id.to_numpy(), act.x.to_numpy(), act.mom.to_numpy()):
            d = np.abs(gx - x) + 0.5 * np.abs(gm - mom)
            d[gid == pid] = np.inf
            orden = np.argsort(d, kind="stable")[:60]
            orden = orden[d[orden] < 0.6]
            if len(orden) < 5:
                continue
            vistos, comps = set(), []
            for i in orden:
                if gid[i] in vistos:
                    continue
                vistos.add(gid[i])
                comps.append([nombres.get(gid[i], "?"), int(ga[i]), int(np.exp(gx[i]) // 1000),
                              None if np.isnan(g3[i]) else int(np.exp(g3[i]) // 1000), int(np.exp(gp[i]) // 1000)])
                if len(comps) == 5:
                    break
            r3 = g3[orden] - gx[orden]
            ok = ~np.isnan(r3)
            salida[int(pid)] = {"c": comps, "n": int(len(orden)), "sigue": round(float(ok.mean()), 2),
                                "sube": round(float((r3[ok] > 0.05).mean()), 2) if ok.any() else None,
                                "med": round(float(np.exp(np.median(r3[ok]))), 2) if ok.any() else None}
    return salida


# ---------------------------------------------------------------- exportación
def exportar(jug, val, clubes, les, apar, fich, panel, sim, betas, log_idx, bt, corte, stats):
    Q, S, PICO, EP = sim
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    (SALIDA / "det").mkdir(parents=True)

    ult = val.groupby("player_id").tail(1).set_index("player_id")
    maximo = val.groupby("player_id").market_value_in_eur.max()
    j = jug[jug.player_id.isin(ult.index[ult.date >= VIGENTE_DESDE]) & ~jug.club_nombre.isin(["Retired"])].copy()
    j["valor"] = j.player_id.map(ult.market_value_in_eur)
    j["fecha_valor"] = j.player_id.map(ult.date)
    j["max_hist"] = j.player_id.map(maximo)
    j["edad"] = ((corte - j.nac).dt.days / 365.25).astype(int)
    j = j[(j.edad >= 15) & j.club_id.isin(clubes.index)]

    # factores individuales: los de la foto más reciente de cada jugador
    f = panel.sort_values("anio").groupby("player_id").tail(1).set_index("player_id")
    for c in ["mom", "nuevo", "dd", "les", "x"]:
        j[c] = j.player_id.map(f[c]).fillna(0 if c != "nuevo" else 1)

    a = apar[apar.date > corte - pd.Timedelta(days=365)]
    a = a.groupby("player_id").agg(pj=("game_id", "count"), minutos=("minutes_played", "sum"), goles=("goals", "sum"), asist=("assists", "sum"))
    j = j.merge(a, on="player_id", how="left")
    les24 = les[les.from_date > corte - pd.Timedelta(days=730)].groupby("player_id").days_missed.sum()
    j["les24"] = j.player_id.map(les24).fillna(0)

    def indice(serie):
        vals = sorted(serie.dropna().astype(str).unique())
        return vals, {v: i for i, v in enumerate(vals)}
    paises, ip = indice(j.pais.replace({"nan": np.nan, "": np.nan}))
    subpos, isub = indice(j.subpos.replace({"nan": np.nan}))
    pies = ["right", "left", "both"]
    n = lambda v: -1 if pd.isna(v) else int(v)
    filas = [[
        int(r.player_id), r.nombre, int(r.club_id), POSICIONES.index(r.pos), isub.get(str(r.subpos), -1), int(r.edad),
        ip.get(str(r.pais), -1), int(r.valor), int(r.max_hist), n(r.pj), n(r.minutos), n(r.goles), n(r.asist),
        r.contrato if isinstance(r.contrato, str) else "", int(r.fecha_valor.strftime("%Y%m")),
        pies.index(r.pie) if r.pie in pies else -1, int(r.altura) if r.altura and r.altura > 100 else 0,
        round(float(r.mom), 2), int(r.nuevo), round(float(r.dd), 2), int(r.les * 100), int(r.les24), 1 if r.cedido_de else 0,
    ] for r in j.itertuples()]

    cl = clubes[clubes.index.isin(j.club_id)].copy()
    # Clubes sin liga identificada: el país se INFIERE de la nacionalidad dominante de su plantilla
    # (mínimo 3 jugadores y mayoría absoluta). La página lo marca como inferido.
    nac = j[j.club_id.isin(cl.index[(cl.pais == "") & (cl.nivel == 9)])].groupby("club_id").pais.agg(
        lambda s_: s_.mode().iat[0] if len(s_) >= 3 and s_.notna().any() and s_.value_counts().iat[0] > len(s_) / 2 else "")
    cl["inferido"] = False
    cl.loc[nac.index[nac != ""], "inferido"] = True
    cl.loc[nac.index[nac != ""], "pais"] = nac[nac != ""]
    lista_clubes = [{"id": int(i), "nombre": r.nombre, "liga": r.liga, "pais": r.pais, "nivel": int(r.nivel), "estadio": r.estadio,
                     **({"inf": 1} if r.inferido else {})}
                    for i, r in cl.iterrows()]

    # ---- detalle por jugador, repartido en trozos que la página pide bajo demanda
    nombres = jug.set_index("player_id").nombre.to_dict()
    act = j[["player_id", "x", "mom", "pos", "edad"]].copy()
    act["pi"], act["e"] = act.pos.map(POSICIONES.index), act.edad.clip(EDAD_MIN, EDAD_MAX)
    prec = precedentes(panel, act, nombres, corte.year - 3)
    vj = val[val.player_id.isin(j.player_id)]
    hist = {pid: [[int(d.strftime("%Y%m")) for d in g.date][-44:], [int(v // 1000) for v in g.market_value_in_eur][-44:]]
            for pid, g in vj.groupby("player_id")}
    fj = fich[fich.player_id.isin(j.player_id) & (fich.transfer_date <= corte + pd.Timedelta(days=120))].sort_values("transfer_date")
    tras = {pid: [[d.strftime("%Y-%m"), a_, b_, n(c), n(m)] for d, a_, b_, c, m in
                  zip(g.transfer_date, g.from_club_name, g.to_club_name, g.transfer_fee, g.market_value_in_eur)][-5:]
            for pid, g in fj.groupby("player_id")}
    lj = les[les.player_id.isin(j.player_id)].sort_values("from_date")
    lesiones = {pid: [[d.strftime("%Y-%m"), str(m), n(dd)] for d, m, dd in zip(g.from_date, g.injury_reason, g.days_missed)][-4:]
                for pid, g in lj.groupby("player_id")}
    agentes = j.set_index("player_id").agente.dropna().to_dict()
    cedidos = j[j.cedido_de != ""].set_index("player_id").cedido_de.to_dict()
    trozos = [{} for _ in range(N_TROZOS)]
    for pid in j.player_id:
        pid = int(pid)
        d = {"h": hist.get(pid, [[], []])}
        for k, src in (("t", tras), ("l", lesiones), ("p", prec), ("a", agentes), ("c", cedidos)):
            if pid in src:
                d[k] = src[pid]
        trozos[pid % N_TROZOS][pid] = d
    def limpio(o):
        """Ningún NaN llega al JSON: rompería la carga en el navegador."""
        if isinstance(o, float):
            return o if np.isfinite(o) else None
        if isinstance(o, dict):
            return {k: limpio(v) for k, v in o.items()}
        if isinstance(o, list):
            return [limpio(v) for v in o]
        return o
    volcar = lambda ruta, obj: ruta.write_text(json.dumps(limpio(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    for i, t in enumerate(trozos):
        volcar(SALIDA / "det" / f"{i}.json", t)

    # ---- perfiles: sólo los (posición, edad, bin) que algún jugador usa
    red = lambda arr: [None if not np.isfinite(v) else round(float(v), 3) for v in arr]
    perf = {}
    usados = set(zip(act.pi, act.e.clip(upper=EDAD_MAX - 1), bin_de(np.log(j.valor.to_numpy()))))
    for p, e, b in usados:
        i = e - EDAD_MIN
        H = EDAD_MAX - e
        perf[f"{p}_{e}_{b}"] = {"q": [red(Q[p, i, b, h]) for h in range(H)], "s": red(S[p, i, b, :H]),
                                "pico": red(PICO[p, i, b]), "ep": int(EP[p, i, b])}

    anios = [int(a_) for a_ in log_idx.index if a_ >= 2006]
    meta = {
        "corte": corte.strftime("%Y-%m-%d"), "jugadores": len(filas), "clubes": len(lista_clubes),
        "ligas": int(cl[cl.nivel.between(1, 8)].groupby(["pais", "liga"]).ngroups), "paises_liga": int(cl[cl.pais != ""].pais.nunique()),
        "posiciones": POSICIONES, "subposiciones": subpos, "paises": paises,
        "bins": [round(float(b)) for b in BINS], "edad_min": EDAD_MIN, "edad_max": EDAD_MAX, "trozos": N_TROZOS,
        "indice_mercado": {"anios": anios, "valor": [round(float(np.exp(log_idx[a_] - log_idx[anios[0]])), 3) for a_ in anios]},
        "inflacion_10a": round(float(np.exp((log_idx.iloc[-1] - log_idx.iloc[-11]) / 10) - 1), 4),
        "ajuste": {"horizontes": H_AJUSTE, "factores": ["base"] + FACTORES, "betas": [[round(float(v), 4) for v in betas[h]] for h in H_AJUSTE]},
        "backtest": bt, **stats,
    }
    for nombre, obj in [("meta", meta), ("jugadores", filas), ("clubes", lista_clubes), ("perfiles", perf)]:
        volcar(SALIDA / f"{nombre}.json", obj)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-descarga", action="store_true")
    if not ap.parse_args().sin_descarga:
        descargar()
    jug, val, clubes, les, apar, fich = cargar()
    corte = val.date.max()
    rng = np.random.default_rng(2026)

    fotos = fotos_anuales(val, jug, les, corte)
    log_idx = indice_inflacion(fotos)
    bt = backtest(fotos, log_idx, rng)
    panel = armar_panel(fotos, log_idx, corte.year, corte.year)
    celdas, n_trans, p_salida = ajustar_celdas(panel, corte.year)
    sim = simular(celdas, rng)
    betas = ajustar_factores(panel, sim[0], corte.year)
    stats = {"transiciones": n_trans, "salida_anual": round(p_salida, 3), "valuaciones": len(val), "jugadores_historia": int(val.player_id.nunique())}
    meta = exportar(jug, val, clubes, les, apar, fich, panel, sim, betas, log_idx, bt, corte, stats)

    print(f"corte {meta['corte']} | {meta['jugadores']} jugadores, {meta['clubes']} clubes, {meta['ligas']} ligas, {meta['paises_liga']} países")
    print(f"transiciones {n_trans} | deja de estar valuado {p_salida:.1%}/año | inflación 10a {meta['inflacion_10a']:.1%}")
    print(pd.DataFrame(meta["ajuste"]["betas"], columns=meta["ajuste"]["factores"], index=H_AJUSTE).to_string())
    print(pd.DataFrame(bt["filas"]).to_string(index=False))


if __name__ == "__main__":
    main()
