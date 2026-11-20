#!/usr/bin/env python3
"""Mercado: proyección actuarial del valor de mercado de futbolistas.

Fuente: transfermarkt-datasets (dcaribou, CC0). Los CSV se bajan a mercado/datos_crudos/
(no se versionan) y de ahí sale todo lo que consume la página en mercado/web/datos/.

Modelo (v0), en una frase: factores de desarrollo edad-a-edad del valor REAL (deflactado
por un índice de inflación del mercado), por posición y tramo de valor, remuestreados en
simulación para obtener bandas p10/p50/p90 por horizonte, valor máximo de carrera y
probabilidad de seguir en el radar de la base.

Uso:  python3 mercado/pipeline.py [--sin-descarga]
"""
import argparse
import gzip
import json
import shutil
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent
CRUDOS = RAIZ / "datos_crudos"
SALIDA = RAIZ / "web" / "datos"
URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/{}.csv.gz"
TABLAS = ["players", "player_valuations", "clubs", "competitions", "appearances"]

POSICIONES = ["Goalkeeper", "Defender", "Midfield", "Attack"]
EDAD_MIN, EDAD_MAX = 16, 38          # 38 agrupa 38+; la proyección termina ahí
TRAMOS = [3e5, 1e6, 3e6, 1e7, 3e7, 6e7, 1e8]   # cortes de valor real (euros de hoy)
BINS = np.geomspace(25e3, 200e6, 24)  # valores de arranque de los perfiles
N_SIM = 3000
MIN_OBS = 40
PRIMER_ANIO = 2010                   # transiciones anteriores: cobertura pobre


def descargar():
    CRUDOS.mkdir(exist_ok=True)
    for t in TABLAS:
        destino = CRUDOS / f"{t}.csv.gz"
        print("bajando", t)
        with urllib.request.urlopen(URL.format(t), timeout=600) as r, open(destino, "wb") as f:
            shutil.copyfileobj(r, f)


def leer(t, **kw):
    return pd.read_csv(CRUDOS / f"{t}.csv.gz", **kw)


# ---------------------------------------------------------------- fotos anuales
def fotos_anuales(val, jug, corte):
    """Una fila por jugador y año: último valor conocido al 1-jul (no más viejo de 12 meses)."""
    val = val.sort_values("date")
    partes = []
    for anio in range(2005, corte.year + 1):
        ref = pd.Timestamp(anio, 7, 1)
        v = val[(val.date > ref - pd.Timedelta(days=365)) & (val.date <= ref)]
        v = v.groupby("player_id").tail(1)[["player_id", "market_value_in_eur"]].copy()
        v["anio"] = anio
        partes.append(v)
    f = pd.concat(partes).rename(columns={"market_value_in_eur": "valor"})
    f = f.merge(jug[["player_id", "position", "date_of_birth"]], on="player_id")
    f = f[f.position.isin(POSICIONES) & f.date_of_birth.notna() & (f.valor > 0)]
    ref = pd.to_datetime(f.anio.astype(str) + "-07-01")
    f["edad"] = ((ref - f.date_of_birth).dt.days / 365.25).astype(int)
    return f[(f.edad >= EDAD_MIN) & (f.edad <= 42)].drop(columns="date_of_birth")


def indice_inflacion(fotos):
    """Canasta de rango fijo: media del log-valor de los 500 jugadores más caros de cada año.

    Los 500 más caros siempre han estado en ligas cubiertas, así que el índice no depende de
    que la base haya ido sumando ligas. Devuelve log-índice por año.
    """
    return fotos.groupby("anio").valor.apply(lambda s: np.log(s.nlargest(500)).mean())


def transiciones(fotos, log_idx, anio_base, ultimo_anio):
    """Pares (año, año+1) en valor real del año base. Sin sucesor = salió del radar."""
    f = fotos[fotos.anio <= ultimo_anio].copy()
    f["x"] = np.log(f.valor) + log_idx[anio_base] - f.anio.map(log_idx)
    sig = f[["player_id", "anio", "x"]].assign(anio=lambda d: d.anio - 1).rename(columns={"x": "x1"})
    t = f[(f.anio >= PRIMER_ANIO) & (f.anio < ultimo_anio)].merge(sig, on=["player_id", "anio"], how="left")
    t["salio"] = t.x1.isna()
    t["delta"] = t.x1 - t.x
    t["tramo"] = np.digitize(np.exp(t.x), TRAMOS)
    t["edad"] = t.edad.clip(upper=EDAD_MAX)
    return t


# ---------------------------------------------------------------- celdas y simulación
def ajustar_celdas(t):
    """Para cada (posición, edad, tramo): deltas observados y prob. de salir del radar.

    Si la celda es delgada se ensancha: todas las posiciones -> edades vecinas -> el tramo.
    """
    celdas = {}
    vivos = t[~t.salio]
    for pos in POSICIONES:
        for edad in range(EDAD_MIN, EDAD_MAX + 1):
            for tramo in range(len(TRAMOS) + 1):
                filtros = [
                    (t.position == pos) & (t.edad == edad),
                    (t.edad == edad),
                    (t.edad.between(edad - 2, edad + 2)),
                    (t.edad > -1),
                ]
                for m in filtros:
                    m = m & (t.tramo == tramo)
                    d = vivos.loc[m[vivos.index], "delta"].to_numpy()
                    if len(d) >= MIN_OBS:
                        break
                celdas[(pos, edad, tramo)] = (d, float(t.loc[m, "salio"].mean()), len(d))
    return celdas


def simular(celdas, rng):
    """Perfil por (posición, edad, bin de valor): cuantiles del cociente valor futuro/actual."""
    perfiles = {}
    x0 = np.log(BINS)
    for pi, pos in enumerate(POSICIONES):
        for edad in range(EDAD_MIN, EDAD_MAX):
            H = EDAD_MAX - edad
            x = np.repeat(x0[:, None], N_SIM, axis=1)
            vivo = np.ones_like(x, dtype=bool)
            maximo, edad_max = x.copy(), np.full(x.shape, edad)
            q, sup = [], []
            for h in range(1, H + 1):
                e = edad + h - 1
                tramo = np.digitize(np.exp(x), TRAMOS)
                for tr in range(len(TRAMOS) + 1):
                    m = (tramo == tr) & vivo
                    n = int(m.sum())
                    if not n:
                        continue
                    d, p_salir, _ = celdas[(pos, e, tr)]
                    x[m] += rng.choice(d, n)
                    sale = np.zeros_like(m)
                    sale[m] = rng.random(n) < p_salir
                    vivo &= ~sale
                mejora = vivo & (x > maximo)
                maximo[mejora], edad_max[mejora] = x[mejora], edad + h
                xs = np.where(vivo, x, np.nan)
                q.append(np.nanquantile(xs, [0.1, 0.5, 0.9], axis=1).T - x0[:, None])
                sup.append(vivo.mean(axis=1))
            q, sup = np.stack(q, axis=1), np.stack(sup, axis=1)      # (bin, H, 3), (bin, H)
            pico = np.quantile(maximo, [0.5, 0.9], axis=1).T - x0[:, None]
            for b in range(len(BINS)):
                perfiles[(pi, edad, b)] = {
                    "q": np.round(np.exp(np.nan_to_num(q[b])), 3).tolist(),
                    "s": np.round(sup[b], 3).tolist(),
                    "pico": np.round(np.exp(pico[b]), 3).tolist(),
                    "edad_pico": int(np.median(edad_max[b])),
                }
    return perfiles


def bin_de(valor_real):
    return np.abs(np.log(BINS)[None, :] - np.log(np.asarray(valor_real))[:, None]).argmin(axis=1)


# ---------------------------------------------------------------- backtest
def backtest(fotos, log_idx, rng, origen=2021):
    """Entrena sólo con lo conocido a jul-`origen` y compara contra lo que pasó después.

    La inflación futura se supone igual al promedio de los 10 años previos al origen (es lo
    único que se habría sabido entonces). Referencia: 'el valor no cambia'.
    """
    t = transiciones(fotos, log_idx, origen, origen)
    perfiles = simular(ajustar_celdas(t), rng)
    infl = (log_idx[origen] - log_idx[origen - 10]) / 10
    base = fotos[(fotos.anio == origen) & (fotos.edad < EDAD_MAX)]
    filas = []
    for h in (1, 3, 5):
        real = fotos[fotos.anio == origen + h][["player_id", "valor"]].rename(columns={"valor": "real"})
        d = base.merge(real, on="player_id", how="left")
        d = d[d.edad + h <= EDAD_MAX]
        b = bin_de(d.valor)
        pos = d.position.map(POSICIONES.index).to_numpy()
        qs = np.array([perfiles[(p, e, bb)]["q"][h - 1] for p, e, bb in zip(pos, d.edad, b)])
        pred = np.log(d.valor.to_numpy())[:, None] + np.log(np.maximum(qs, 1e-9)) + infl * h
        obs = d.real.notna().to_numpy()
        y = np.log(d.real.to_numpy()[obs])
        err_m = np.abs(pred[obs, 1] - y)
        err_n = np.abs(np.log(d.valor.to_numpy()[obs]) - y)
        grupos = {"todos": np.ones(obs.sum(), bool), "sub23": d.edad.to_numpy()[obs] < 23,
                  "23a28": (d.edad.to_numpy()[obs] >= 23) & (d.edad.to_numpy()[obs] <= 28),
                  "29mas": d.edad.to_numpy()[obs] > 28}
        for g, m in grupos.items():
            filas.append({
                "horizonte": h, "grupo": g, "n": int(m.sum()),
                "error_modelo": round(float(np.exp(np.median(err_m[m])) - 1), 3),
                "error_ingenuo": round(float(np.exp(np.median(err_n[m])) - 1), 3),
                "cobertura_p10_p90": round(float(((y >= pred[obs, 0]) & (y <= pred[obs, 2]))[m].mean()), 3),
            })
        filas[-4]["fuera_del_radar"] = round(float(1 - obs.mean()), 3)
    return {"origen": origen, "inflacion_supuesta": round(float(np.exp(infl) - 1), 4), "filas": filas}


# ---------------------------------------------------------------- exportación
def exportar(jug, clubes, comps, apar, perfiles, log_idx, bt, corte, celdas):
    SALIDA.mkdir(parents=True, exist_ok=True)
    temporada = jug.last_season.max()
    j = jug[(jug.last_season == temporada) & jug.market_value_in_eur.gt(0) & jug.position.isin(POSICIONES)
            & jug.date_of_birth.notna()].copy()
    j["edad"] = ((corte - j.date_of_birth).dt.days / 365.25).astype(int)
    comps = comps[comps.type == "domestic_league"].set_index("competition_id")
    j = j[j.current_club_domestic_competition_id.isin(comps.index) & (j.edad >= EDAD_MIN)]

    a = apar[apar.date > corte - pd.Timedelta(days=365)]
    a = a.groupby("player_id").agg(pj=("game_id", "count"), minutos=("minutes_played", "sum"),
                                   goles=("goals", "sum"), asist=("assists", "sum"))
    j = j.merge(a, on="player_id", how="left").fillna({"pj": 0, "minutos": 0, "goles": 0, "asist": 0})

    paises = sorted(j.country_of_citizenship.dropna().unique())
    ip = {p: i for i, p in enumerate(paises)}
    subpos = sorted(j.sub_position.dropna().unique())
    isub = {p: i for i, p in enumerate(subpos)}
    filas = [[
        int(r.player_id), r.name, int(r.current_club_id), POSICIONES.index(r.position),
        isub.get(r.sub_position, -1), int(r.edad), ip.get(r.country_of_citizenship, -1),
        int(r.market_value_in_eur), int(max(r.highest_market_value_in_eur or 0, r.market_value_in_eur)),
        int(r.pj), int(r.minutos), int(r.goles), int(r.asist),
        (r.contract_expiration_date or "")[:4] if isinstance(r.contract_expiration_date, str) else "",
    ] for r in j.itertuples()]

    c = clubes[clubes.club_id.isin(j.current_club_id)]
    nombres = j.groupby("current_club_id").current_club_name.first()
    comp_club = j.groupby("current_club_id").current_club_domestic_competition_id.first()
    lista_clubes = [{"id": int(r.club_id), "nombre": r.name, "liga": comp_club[r.club_id],
                     "estadio": r.stadium_name if isinstance(r.stadium_name, str) else ""}
                    for r in c.itertuples()]
    faltan = set(j.current_club_id) - set(c.club_id)
    lista_clubes += [{"id": int(i), "nombre": nombres[i], "liga": comp_club[i], "estadio": ""} for i in faltan]
    ligas = {k: {"nombre": r["name"].replace("-", " ").title(), "pais": r.country_name}
             for k, r in comps.iterrows() if k in set(comp_club)}

    anios = [int(a) for a in log_idx.index if a >= 2006]
    meta = {
        "corte": corte.strftime("%Y-%m-%d"), "temporada": int(temporada),
        "jugadores": len(filas), "clubes": len(lista_clubes), "ligas": len(ligas),
        "posiciones": POSICIONES, "subposiciones": subpos, "paises": paises,
        "bins": [round(float(b)) for b in BINS], "edad_min": EDAD_MIN, "edad_max": EDAD_MAX,
        "indice_mercado": {"anios": anios,
                           "valor": [round(float(np.exp(log_idx[a] - log_idx[anios[0]])), 3) for a in anios]},
        "inflacion_10a": round(float(np.exp((log_idx.iloc[-1] - log_idx.iloc[-11]) / 10) - 1), 4),
        "backtest": bt,
        "celdas_delgadas": int(sum(1 for v in celdas.values() if v[2] < MIN_OBS)),
        "columnas": ["id", "nombre", "club", "pos", "subpos", "edad", "pais", "valor", "max_hist",
                     "pj", "min", "goles", "asist", "contrato"],
    }
    perf = {f"{p}_{e}_{b}": v for (p, e, b), v in perfiles.items()}
    for nombre, obj in [("meta", meta), ("jugadores", filas), ("clubes", lista_clubes),
                        ("ligas", ligas), ("perfiles", perf)]:
        (SALIDA / f"{nombre}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-descarga", action="store_true")
    args = ap.parse_args()
    if not args.sin_descarga:
        descargar()
    jug = leer("players", parse_dates=["date_of_birth"])
    val = leer("player_valuations", parse_dates=["date"])
    apar = leer("appearances", usecols=["game_id", "player_id", "date", "goals", "assists", "minutes_played"],
                parse_dates=["date"])
    corte = val.date.max()
    rng = np.random.default_rng(2026)

    fotos = fotos_anuales(val, jug, corte)
    log_idx = indice_inflacion(fotos)
    bt = backtest(fotos, log_idx, rng)
    t = transiciones(fotos, log_idx, corte.year, corte.year)
    celdas = ajustar_celdas(t)
    perfiles = simular(celdas, rng)
    meta = exportar(jug, leer("clubs"), leer("competitions"), apar, perfiles, log_idx, bt, corte, celdas)

    print(f"corte {meta['corte']} | {meta['jugadores']} jugadores, {meta['clubes']} clubes, {meta['ligas']} ligas")
    print(f"transiciones {len(t)} | salidas del radar {t.salio.mean():.1%} | inflación 10a {meta['inflacion_10a']:.1%}")
    print(pd.DataFrame(bt["filas"]).to_string(index=False))


if __name__ == "__main__":
    main()
