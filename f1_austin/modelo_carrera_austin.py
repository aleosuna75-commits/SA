"""
Modelo de predicción del Top 10 de la CARRERA - GP de Estados Unidos (COTA, Austin) 2026.

Reutiliza el pipeline auditado del modelo de qualy (modelo_qualy_austin.py) y agrega lo que se sabe
antes de la carrera:
  * Parrilla de salida real (con penalizaciones) y resultado/gap de la qualy.
  * FP3 y ritmo de tanda larga de FP1+FP2+FP3.
  * Resultado del sprint (fines de semana sprint).
  * Historial de carrera: resultados recientes, posiciones ganadas vs parrilla, abandonos, forma del equipo
    en carrera, historial del piloto en el circuito y qué tanto se rebasa en el circuito.

Objetivo: posición final de carrera (Jolpica; los abandonos quedan clasificados al fondo en su orden oficial).
Selección del modelo: walk-forward 2024-2026 y NDCG@10 (premia acertar QUIÉNES quedan en el Top 10 y en
QUÉ ORDEN, con más peso a las primeras posiciones). Desempate: Spearman.

Uso:  python3 descarga_datos.py && python3 modelo_carrera_austin.py
"""
import json
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import modelo_qualy_austin as Q

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent
CACHE = BASE / "cache"
OBJETIVO_MEETING = Q.OBJETIVO_MEETING

# Parrilla oficial Austin 2026 tras penalizaciones de unidad de potencia (FIA, viernes 23/10):
# Lindblad -5 (6.º ICE), Colapinto -10 (4.ª CE), Bortoleto al fondo (ES + CE nuevos).
# Fuentes: formula1.com, the-race.com, gpfans.com. Si OpenF1 publica starting_grid, se usa ésa.
PARRILLA_OBJETIVO = {
    "ANT": 1, "VER": 2, "HAD": 3, "LEC": 4, "HAM": 5, "RUS": 6, "PIA": 7, "NOR": 8, "LAW": 9, "GAS": 10,
    "HUL": 11, "ALO": 12, "BEA": 13, "LIN": 14, "OCO": 15, "STR": 16, "SAI": 17, "ALB": 18, "PER": 19,
    "BOT": 20, "COL": 21, "BOR": 22,
}


# ----------------------------------------------------------------------------------------
# Datos de carrera (Jolpica) y de OpenF1 (qualy, sprint)
# ----------------------------------------------------------------------------------------
def carreras_jolpica():
    filas = []
    for f in sorted(CACHE.glob("jolpica_results_*.json")):
        for r in json.loads(f.read_text())["MRData"]["RaceTable"]["Races"]:
            for x in r["Results"]:
                filas.append({
                    "season": int(r["season"]), "round": int(r["round"]),
                    "date": pd.Timestamp(r["date"]), "circuit": r["Circuit"]["circuitId"],
                    "code": x["Driver"].get("code"), "team": Q.EQUIPO_CANON.get(x["Constructor"]["name"], x["Constructor"]["name"]),
                    "pos": int(x["position"]), "grid": int(x["grid"]), "status": x["status"],
                    "points": float(x["points"]), "laps": int(x["laps"]),
                })
    df = pd.DataFrame(filas).drop_duplicates(["season", "round", "code"])
    n = df.groupby(["season", "round"]).code.transform("count")
    df["grid"] = np.where(df.grid == 0, n, df.grid)       # salida desde pit lane -> fondo
    df["terminado"] = df.status.str.contains(r"Finished|Lap", regex=True)
    df["gain"] = df.grid - df.pos
    return df.sort_values(["date", "pos"]).reset_index(drop=True)


def resultados_openf1():
    res = Q.tabla_resultados()
    res["position"] = pd.to_numeric(res.position, errors="coerce")
    return res


def q_gap_segmento(qr):
    """Gap % dentro del último segmento (Q1/Q2/Q3) que corrió cada piloto, contra el mejor de ese segmento."""
    seg = pd.DataFrame([v if isinstance(v, list) else [v, None, None] for v in qr.duration],
                       index=qr.index).reindex(columns=[0, 1, 2]).apply(pd.to_numeric, errors="coerce")
    gap = (seg - seg.min()) / seg.min() * 100
    ult = seg.notna().cumsum(axis=1).idxmax(axis=1)
    tiene = seg.notna().any(axis=1)
    return pd.Series([gap.at[i, c] if tiene[i] else np.nan for i, c in ult.items()],
                     index=qr.index, dtype=float).clip(upper=5)


def mejor_tiempo(d):
    if isinstance(d, list):
        v = [x for x in d if x]
        return min(v) if v else np.nan
    return d if d else np.nan


# ----------------------------------------------------------------------------------------
# Dataset
# ----------------------------------------------------------------------------------------
def construir_dataset_carrera():
    data, meetings = Q.construir_dataset()       # FP1/FP2 + historial de qualy (ya auditado)
    ses = Q.tabla_sesiones()
    res = resultados_openf1()
    jr = carreras_jolpica()

    # FP3, qualy (gap), sprint por GP
    extra = []
    for _, m in meetings.iterrows():
        g = ses[ses.meeting_key == m.meeting_key]
        nombres = dict(zip(g.session_name, g.session_key))
        base = data.loc[data.meeting_key == m.meeting_key, ["driver_number"]].copy()
        if "Practice 3" in nombres:
            f3 = Q.features_practica(int(nombres["Practice 3"]), "fp3")
            if not f3.empty:
                base = base.merge(f3, on="driver_number", how="left")
        qr = res[res.session_key == m.q][["driver_number", "duration"]].copy()
        qr["q_best"] = pd.to_numeric(qr.duration.map(mejor_tiempo), errors="coerce")
        qr["q_gap"] = q_gap_segmento(qr) if len(qr) else np.nan
        base = base.merge(qr[["driver_number", "q_best", "q_gap"]], on="driver_number", how="left")
        if "Sprint" in nombres:
            sp = res[res.session_key == nombres["Sprint"]][["driver_number", "position"]]
            base = base.merge(sp.rename(columns={"position": "sprint_pos"}), on="driver_number", how="left")
        rk = nombres.get("Race")
        base["meeting_key"] = m.meeting_key
        base["race_start"] = g[g.session_name == "Race"].date_start.min() if rk else pd.NaT
        extra.append(base)
    extra = pd.concat(extra, ignore_index=True)
    data = data.merge(extra, on=["meeting_key", "driver_number"], how="left")
    for c in Q.FEATURES + ["fp3_gap", "fp3_rank", "fp3_long_gap", "fp3_long_rank", "fp3_ideal_gap",
                           "fp3_soft_gap", "fp3_laps", "sprint_pos", "fp3_trap_delta"]:
        if c not in data:
            data[c] = np.nan

    # Gap de qualy, compañero, ritmo de carrera combinado
    g = data.groupby("meeting_key")
    data["q_team_best"] = data.groupby(["meeting_key", "team"]).q_pos.transform("min")
    data["q_teammate_delta"] = data.q_pos - data.q_team_best
    # ritmo de carrera: media de los gaps de tanda larga sólo en sesiones donde >=60% del campo hizo tanda larga
    cols = ["fp1_long_gap", "fp2_long_gap", "fp3_long_gap"]
    cob = data.groupby("meeting_key")[cols].transform("count").div(data.n_drivers, axis=0)
    lg = data[cols].where(cob >= 0.6)
    lg = lg.where(lg.notna().any(axis=1), data[cols])      # si no queda ninguna, usar lo que haya
    data["long_gap_all"] = lg.mean(axis=1)
    data["long_rank_all"] = data.groupby("meeting_key").long_gap_all.rank(method="min")
    data["long_team_best"] = data.groupby(["meeting_key", "team"]).long_gap_all.transform("min")
    data["fp_best_all"] = data[["fp1_best", "fp2_best", "fp3_best"]].min(axis=1)
    data["fp_rank_all"] = data.groupby("meeting_key").fp_best_all.rank(method="min")
    data["race_vs_q_pace"] = data.long_rank_all - data.q_pos     # <0: mejor ritmo de carrera que de qualy

    # Emparejar cada GP con su carrera de Jolpica (fecha de carrera dentro del fin de semana)
    carreras = jr[["season", "round", "date", "circuit"]].drop_duplicates(["season", "round"])
    emparejo = {}
    for _, m in meetings.iterrows():
        ini = pd.Timestamp(m.date).tz_convert(None).normalize()
        c = carreras[(carreras.date >= ini) & (carreras.date <= ini + pd.Timedelta(days=4))]
        if len(c):
            emparejo[m.meeting_key] = c.iloc[0]
    mapa_circ = {meetings.set_index("meeting_key").circuit_key[mk]: r.circuit for mk, r in emparejo.items()}

    # Objetivo y parrilla
    tgt = []
    for mk, r in emparejo.items():
        x = jr[(jr.season == r.season) & (jr["round"] == r["round"])][["code", "pos", "grid", "status"]]
        x["meeting_key"] = mk
        tgt.append(x)
    tgt = pd.concat(tgt).rename(columns={"code": "name_acronym", "pos": "race_pos"})
    data = data.merge(tgt, on=["meeting_key", "name_acronym"], how="left")
    obj = data.meeting_key == OBJETIVO_MEETING
    grid_openf1 = parrilla_openf1()
    data.loc[obj, "grid"] = data.loc[obj, "name_acronym"].map(grid_openf1 or PARRILLA_OBJETIVO)
    data["grid"] = data.grid.fillna(data.q_pos).fillna(data.n_drivers)
    data["grid_penalty"] = data.grid - data.q_pos
    data["grid_team_best"] = data.groupby(["meeting_key", "team"]).grid.transform("min")

    # Historial de carrera (corte: inicio del fin de semana, igual que en la qualy)
    hist = defaultdict(dict)
    for mk, grupo in data.groupby("meeting_key", sort=False):
        corte = pd.Timestamp(grupo.date.iloc[0]).tz_convert(None).normalize()
        prev = jr[jr.date < corte]
        circ = mapa_circ.get(grupo.circuit_key.iloc[0])
        pc_all = prev[prev.circuit == circ] if circ else prev.iloc[0:0]
        # facilidad de rebase del circuito en ediciones anteriores
        if len(pc_all):
            top = pc_all[pc_all.grid <= 10]
            circ_gain_abs = top.gain.abs().mean()
            circ_corr = pc_all.groupby(["season"]).apply(
                lambda x: spearmanr(x.grid, x.pos).correlation if len(x) > 5 else np.nan).mean()
            circ_dnf = 1 - pc_all.terminado.mean()
        else:
            circ_gain_abs = circ_corr = circ_dnf = np.nan
        temporada = grupo.year.iloc[0]
        for idx, row in grupo.iterrows():
            p = prev[prev.code == row.name_acronym]
            h = {
                "r_mean3": p.pos.tail(3).mean() if len(p) else np.nan,
                "r_mean10": p.pos.tail(10).mean() if len(p) else np.nan,
                "r_season": p[p.season == temporada].pos.mean() if len(p) else np.nan,
                "r_top10_rate10": (p.pos.tail(10) <= 10).mean() if len(p) else np.nan,
                "r_podium_rate10": (p.pos.tail(10) <= 3).mean() if len(p) else np.nan,
                "r_gain_mean10": p.gain.tail(10).mean() if len(p) else np.nan,
                "r_finish_rate10": p.terminado.tail(10).mean() if len(p) else np.nan,
                "r_last": p.pos.iloc[-1] if len(p) else np.nan,
                "r_circ_mean": p[p.circuit == circ].pos.mean() if circ and len(p) else np.nan,
                "r_circ_gain": p[p.circuit == circ].gain.mean() if circ and len(p) else np.nan,
                "circ_gain_abs": circ_gain_abs, "circ_grid_corr": circ_corr, "circ_dnf_rate": circ_dnf,
            }
            t = prev[prev.team == row.team]
            ult = t[["season", "round"]].drop_duplicates().tail(5)
            tt = t.merge(ult, on=["season", "round"])
            h["team_r_mean5"] = tt.pos.mean() if len(tt) else np.nan
            h["team_finish_rate5"] = tt.terminado.mean() if len(tt) else np.nan
            hist[idx] = h
    data = data.join(pd.DataFrame.from_dict(hist, orient="index"))
    data["r_eval"] = data.race_pos
    data[FEATURES_CARRERA] = data[FEATURES_CARRERA].apply(pd.to_numeric, errors="coerce")
    return data, meetings


FEATURES_CARRERA = Q.FEATURES + [
    "grid", "q_pos", "grid_penalty", "grid_team_best", "q_gap", "q_team_best", "q_teammate_delta",
    "fp3_gap", "fp3_rank", "fp3_long_gap", "fp3_long_rank", "fp3_ideal_gap", "fp3_soft_gap", "fp3_laps",
    "fp3_trap_delta", "long_gap_all", "long_rank_all", "long_team_best", "fp_rank_all", "race_vs_q_pace",
    "sprint_pos", "r_mean3", "r_mean10", "r_season", "r_top10_rate10", "r_podium_rate10", "r_gain_mean10",
    "r_finish_rate10", "r_last", "r_circ_mean", "r_circ_gain", "circ_gain_abs", "circ_grid_corr",
    "circ_dnf_rate", "team_r_mean5", "team_finish_rate5",
]
FEATURES_CARRERA = list(dict.fromkeys(FEATURES_CARRERA))


def parrilla_openf1():
    """Parrilla oficial de OpenF1 si ya está publicada (cache/starting_grid_1297.json)."""
    f = CACHE / "starting_grid_1297.json"
    if not f.exists():
        return None
    g = json.loads(f.read_text())
    if not isinstance(g, list) or len(g) < 15:
        return None
    pil = Q.tabla_pilotos()
    acr = pil[pil.meeting_key == OBJETIVO_MEETING].drop_duplicates("driver_number").set_index("driver_number").name_acronym
    return {acr[x["driver_number"]]: x["position"] for x in g if x["driver_number"] in acr}


# ----------------------------------------------------------------------------------------
# Modelos y métricas
# ----------------------------------------------------------------------------------------
def catalogo():
    cat = Q.catalogo()
    cat.pop("Baseline: rank FP2 (o FP1)")
    cat.pop("Baseline: mejor vuelta FP1+FP2")
    base = {
        "Baseline: orden de parrilla": lambda: Q.Modelo("bg", "baseline", "grid"),
        "Baseline: orden de qualy": lambda: Q.Modelo("bq", "baseline", "q_pos"),
    }
    return {**base, **cat}


def ndcg10(pred_rank, real):
    rel = np.clip(11 - real, 0, None)
    orden = np.argsort(pred_rank.values)[:10]
    dcg = (rel.values[orden] / np.log2(np.arange(2, 12))).sum()
    ideal = (np.sort(rel.values)[::-1][:10] / np.log2(np.arange(2, 12))).sum()
    return dcg / ideal


def metricas(df, col):
    out = []
    for mk, g in df.groupby("meeting_key"):
        g = g.dropna(subset=["real"])
        pr = g[col].rank(method="first")
        real_top = g.real <= 10
        out.append({
            "meeting_key": mk,
            "top10_hits": len(set(g[real_top].driver_number) & set(g[pr <= 10].driver_number)),
            "ndcg10": ndcg10(pr, g.real),
            "pos_exact10": int(((pr == g.real) & real_top).sum()),
            "mae_top10": (pr[real_top] - g.real[real_top]).abs().mean(),
            "spearman": spearmanr(pr, g.real).correlation,
            "win_hit": int(g.loc[pr.idxmin(), "real"] == 1),
            "podium_hits": len(set(g[g.real <= 3].driver_number) & set(g[pr <= 3].driver_number)),
        })
    return pd.DataFrame(out)


def walk_forward(data, desde=2024):
    entrenables = data.dropna(subset=["race_pos"])
    pruebas = entrenables[entrenables.year >= desde].meeting_key.drop_duplicates().tolist()
    cat = catalogo()
    preds = {n: [] for n in cat}
    for i, mk in enumerate(pruebas):
        fecha = entrenables[entrenables.meeting_key == mk].date.iloc[0]
        tr = entrenables[entrenables.date < fecha].sort_values(["meeting_key", "driver_number"])
        te = entrenables[entrenables.meeting_key == mk]
        grupos = tr.groupby("meeting_key", sort=False).size().loc[tr.meeting_key.unique()].values
        for nombre, fab in cat.items():
            m = fab().fit(tr[FEATURES_CARRERA], tr.race_pos.values, Q.pesos(tr), grupos)
            p = te[["meeting_key", "driver_number", "year"]].assign(real=te.race_pos.values)
            p["pred"] = m.predict(te[FEATURES_CARRERA])
            preds[nombre].append(p)
        print(f"  walk-forward {i + 1}/{len(pruebas)}", end="\r", flush=True)
    print()
    preds = {n: pd.concat(v) for n, v in preds.items()}

    def ens(nombres):
        b = preds[nombres[0]][["meeting_key", "driver_number", "real", "year"]].copy()
        b["pred"] = np.mean([preds[n].groupby("meeting_key").pred.rank().values for n in nombres], axis=0)
        return b
    preds["Ensamble árboles (RF+ET+GB+XGB+LGB)"] = ens(["Random Forest", "Extra Trees", "Gradient Boosting", "XGBoost", "LightGBM"])
    preds["Ensamble total (Ridge+árboles+rankers)"] = ens(["Ridge", "Random Forest", "Extra Trees", "Gradient Boosting",
                                                           "XGBoost", "LightGBM", "LightGBM LambdaRank", "XGBoost Ranker"])
    tabla = []
    for n, p in preds.items():
        mt = metricas(p, "pred")
        mt26 = metricas(p[p.year >= 2026], "pred")
        tabla.append({"modelo": n, "ndcg10": mt.ndcg10.mean(), "ndcg10_2026": mt26.ndcg10.mean(),
                      "top10_hits": mt.top10_hits.mean(), "pos_exact10": mt.pos_exact10.mean(),
                      "mae_top10": mt.mae_top10.mean(), "spearman": mt.spearman.mean(),
                      "win_acc": mt.win_hit.mean(), "podium_hits": mt.podium_hits.mean(), "n_gp": len(mt)})
    tabla = pd.DataFrame(tabla).sort_values(["ndcg10", "spearman"], ascending=False).reset_index(drop=True)
    return tabla, preds


def ajustar_final(nombre, train):
    train = train.sort_values(["meeting_key", "driver_number"])
    grupos = train.groupby("meeting_key", sort=False).size().loc[train.meeting_key.unique()].values
    if nombre.startswith("Ensamble"):
        miembros = (["Random Forest", "Extra Trees", "Gradient Boosting", "XGBoost", "LightGBM"] if "árboles" in nombre else
                    ["Ridge", "Random Forest", "Extra Trees", "Gradient Boosting", "XGBoost", "LightGBM",
                     "LightGBM LambdaRank", "XGBoost Ranker"])
    else:
        miembros = [nombre]
    cat = catalogo()
    modelos = [cat[n]().fit(train[FEATURES_CARRERA], train.race_pos.values, Q.pesos(train), grupos) for n in miembros]

    def predecir(X):
        return np.mean([pd.Series(m.predict(X)).rank().values for m in modelos], axis=0)
    return predecir, modelos


def importancias(modelos):
    imp = []
    for m in modelos:
        est = m.est.steps[-1][1] if hasattr(m.est, "steps") else m.est
        if hasattr(est, "feature_importances_"):
            v = np.asarray(est.feature_importances_, dtype=float)
            imp.append(v / v.sum())
    return pd.Series(np.mean(imp, axis=0), index=FEATURES_CARRERA).sort_values(ascending=False) if imp else pd.Series(dtype=float)


def main():
    print("Construyendo dataset de carrera...")
    data, meetings = construir_dataset_carrera()
    data.to_csv(BASE / "dataset_carrera.csv", index=False)
    obj = data[data.meeting_key == OBJETIVO_MEETING].copy().reset_index(drop=True)
    historia = data[(data.meeting_key != OBJETIVO_MEETING) & data.race_pos.notna()]
    print(f"Filas: {len(historia)} | GPs: {historia.meeting_key.nunique()} | Variables: {len(FEATURES_CARRERA)}")
    print("Parrilla objetivo:", dict(zip(obj.name_acronym, obj.grid)))

    print("Validación walk-forward 2024-2026...")
    tabla, preds = walk_forward(historia)
    print(tabla.to_string(index=False))
    mejor = tabla.modelo.iloc[0]          # el mejor por NDCG@10, aunque sea un baseline
    print("Mejor modelo (NDCG@10):", mejor)

    p = preds[mejor].copy()
    p["pred_rank"] = p.groupby("meeting_key").pred.rank(method="first")
    p["res"] = p.real - p.pred_rank
    mejor_ml = tabla[~tabla.modelo.str.startswith("Baseline")].modelo.iloc[0]
    nombre_base = tabla[tabla.modelo.str.startswith("Baseline")].modelo.iloc[0]
    por_gp = metricas(preds[mejor_ml], "pred").merge(meetings[["meeting_key", "circuit", "year"]], on="meeting_key")
    base_gp = metricas(preds[nombre_base], "pred")

    predecir, _ = ajustar_final(mejor, historia)
    predecir_ml, modelos = ajustar_final(mejor_ml, historia)
    imp = importancias(modelos)
    if imp.empty:
        _, mods = ajustar_final("Ensamble árboles (RF+ET+GB+XGB+LGB)", historia)
        imp = importancias(mods)
    obj["score"] = predecir(obj[FEATURES_CARRERA])
    obj["pred_rank"] = obj.score.rank(method="first").astype(int)
    obj["pred_ml"] = pd.Series(predecir_ml(obj[FEATURES_CARRERA])).rank(method="first").astype(int).values
    mc = Q.montecarlo(obj.pred_rank.values, p[["pred_rank", "res"]].dropna()).rename(
        columns={"p_pole": "p_win", "p_top3": "p_podio", "p_q3": "p_top10", "p_q2": "p_top16"})
    obj = pd.concat([obj, mc], axis=1).sort_values("pred_rank")
    obj.to_csv(BASE / "prediccion_carrera_austin_2026.csv", index=False)

    R = {"tabla": tabla, "mejor": mejor, "mejor_ml": mejor_ml, "base": nombre_base, "obj": obj, "imp": imp, "por_gp": por_gp, "base_gp": base_gp,
         "historia": historia, "n_vars": len(FEATURES_CARRERA), "jr": carreras_jolpica()}
    from reporte_carrera_html import generar_html
    generar_html(R, BASE / "reporte_carrera_austin_2026.html")
    print("\nPREDICCIÓN TOP 10 CARRERA:")
    print(obj[["pred_rank", "name_acronym", "grid", "q_pos", "long_rank_all", "pred_ml", "p_top10", "p_podio", "p_win"]].head(12).to_string(index=False))
    return R


if __name__ == "__main__":
    main()
