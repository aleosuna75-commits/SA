"""
Modelo de predicción del ORDEN FINAL de la CARRERA, parametrizado por GP (Austin 1297, México 1298, ...).

Reutiliza el pipeline auditado del modelo de qualy (modelo_qualy_austin.py) y agrega lo que se sabe
antes de la carrera:
  * Parrilla de salida (qualy + penalizaciones, o la parrilla oficial de OpenF1) y gap de la qualy.
  * FP3 y ritmo de tanda larga de FP1+FP2+FP3.
  * Degradación de neumáticos por piloto/equipo en las tandas largas (degradacion.py).
  * Estrategia por circuito con carreras pasadas: paradas típicas, pérdida en pits, largo de stint.
  * Resultado del sprint (fines de semana sprint).
  * Historial de carrera: resultados recientes, posiciones ganadas vs parrilla, abandonos, forma del equipo
    en carrera, historial del piloto en el circuito y qué tanto se rebasa en el circuito.

Objetivo: posición final de carrera (Jolpica; los abandonos quedan clasificados al fondo en su orden oficial).
Pronóstico oficial: simulador Monte Carlo (sim_carrera.py, variante MC_VAR). Validación walk-forward 2024-2026,
métrica principal NDCG@10.

Uso:
  python3 modelo_carrera_austin.py 1298                         # modo rápido (simulador + walk-forward del simulador)
  python3 modelo_carrera_austin.py 1298 --penalizaciones '{"XXX": 5, "YYY": "fondo", "ZZZ": "pits"}'
  python3 modelo_carrera_austin.py 1298 --qualy-archivo ruta.json --prueba DIR   # prueba: todo se escribe en DIR
  python3 modelo_carrera_austin.py 1298 --parrilla '{"VER": 1, ...}'              # parrilla completa a mano
  python3 modelo_carrera_austin.py 1297 --completo               # además compara los 13 modelos de ML (lento)
Parrilla: --parrilla > cache/starting_grid_<mk>.json (si no se pasan penalizaciones) > qualy (cache/qualy_real_<mk>.json
o --qualy-archivo) + penalizaciones. Salidas: prediccion_carrera_<slug>_2026.csv y web_<slug>/datos_carrera.json
(forma del doc "carrera/<slug>2026" de la página en vivo).
"""
import argparse
import json
import time
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import degradacion as D
import modelo_qualy_austin as Q
from sim_carrera import Simulador, X_media, prep

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent
CACHE = BASE / "cache"
OBJETIVO_MEETING = 1297            # default histórico (Austin); el GP se pasa por línea de comandos
SIM = "Simulador de carrera (Monte Carlo)"
MC_VAR_BASE = {"is26": False, "gn_inter": True}
# Variante oficial (validar_carrera.py / validacion_carrera.json): las variantes con degradación y estrategia empatan
# con la base dentro del ruido Monte Carlo y el coeficiente de degradación sale con signo contrario al esperado,
# así que el pronóstico usa la base y la degradación/paradas van en la salida sólo como información.
MC_VAR = dict(MC_VAR_BASE)
N_SIMS = 20000

# Parrilla oficial Austin 2026 tras penalizaciones de unidad de potencia (FIA, viernes 23/10):
# Lindblad -5 (6.º ICE), Colapinto -10 (4.ª CE), Bortoleto al fondo (ES + CE nuevos).
PARRILLA_AUSTIN = {
    "ANT": 1, "VER": 2, "HAD": 3, "LEC": 4, "HAM": 5, "RUS": 6, "PIA": 7, "NOR": 8, "LAW": 9, "GAS": 10,
    "HUL": 11, "ALO": 12, "BEA": 13, "LIN": 14, "OCO": 15, "STR": 16, "SAI": 17, "ALB": 18, "PER": 19,
    "BOT": 20, "COL": 21, "BOR": 22,
}
PARRILLA_OBJETIVO = PARRILLA_AUSTIN   # compatibilidad
GPS_CARRERA = {
    1297: {"vueltas": 56, "parrilla_manual": PARRILLA_AUSTIN},
    1298: {"vueltas": 71, "parrilla_manual": None},
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
                    "dt": r["date"] + "T" + (r.get("time") or "23:59:59Z"),
                })
    # F1_CORTE (modo retro de gp_pipeline.py): sólo carreras que empezaron antes del corte
    df = Q.jolpica_antes_del_corte(pd.DataFrame(filas)).drop_duplicates(["season", "round", "code"])
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


def leer_qualy(ruta):
    """Lista OpenF1 session_result (driver_number, position, duration) -> DataFrame; None si no sirve."""
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    x = json.loads(ruta.read_text())
    if not isinstance(x, list) or len(x) < 15:
        return None
    q = pd.DataFrame(x)
    if "duration" not in q:
        q["duration"] = None
    q["position"] = pd.to_numeric(q.get("position"), errors="coerce")
    return q[["driver_number", "position", "duration"]]


def aplicar_penalizaciones(orden, pen):
    """orden: {acr: posición de qualy}; pen: {acr: lugares (int) | 'fondo' | 'pits'} -> {acr: salida 1..n}.
    Lugares: el piloto queda detrás del que clasificó en qualy+lugares. 'fondo' detrás de todos los demás
    (en su orden de qualy); 'pits' sale desde el pit lane, detrás incluso de los enviados al fondo."""
    clave = {}
    for acr, p in orden.items():
        x = (pen or {}).get(acr)
        if x is None:
            clave[acr] = p
        elif str(x).lower() == "fondo":
            clave[acr] = 1000 + p
        elif str(x).lower() in ("pits", "pit", "pitlane"):
            clave[acr] = 2000 + p
        else:
            clave[acr] = p + int(x) + 0.5
    return {a: i + 1 for i, a in enumerate(sorted(clave, key=lambda a: clave[a]))}


def parrilla_openf1(meeting):
    """Parrilla oficial de OpenF1 si ya está publicada (cache/starting_grid_<mk>.json) como {driver_number: pos}."""
    f = CACHE / f"starting_grid_{meeting}.json"
    if not f.exists():
        return None
    g = json.loads(f.read_text())
    if not isinstance(g, list) or len(g) < 15:
        return None
    return {x["driver_number"]: x["position"] for x in g if x.get("position")}


# ----------------------------------------------------------------------------------------
# Dataset
# ----------------------------------------------------------------------------------------
def construir_dataset_carrera(meeting=OBJETIVO_MEETING, qualy=None, parrilla=None):
    """qualy: DataFrame (driver_number, position, duration) de la qualy del GP objetivo si OpenF1 aún no la tiene
    en results_<año>.json. parrilla: {driver_number: salida} del GP objetivo (None -> starting_grid o qualy)."""
    data, meetings = Q.construir_dataset()       # FP1/FP2 + historial de qualy (ya auditado)
    ses = Q.tabla_sesiones()
    res = resultados_openf1()
    jr = carreras_jolpica()
    est_tabla, est_degs = D.tabla_estrategia()
    pil = Q.tabla_pilotos().drop_duplicates(["meeting_key", "driver_number"])
    deg_hist = D.deg_carrera_piloto(est_tabla, est_degs).merge(
        pil[["meeting_key", "driver_number", "name_acronym"]], on=["meeting_key", "driver_number"]).sort_values("fecha")

    obj = data.meeting_key == meeting
    if qualy is not None and obj.any():
        mq = meetings.set_index("meeting_key").q.get(meeting)
        res = pd.concat([res[res.session_key != mq], qualy.assign(session_key=mq, meeting_key=meeting)], ignore_index=True)
        qp = qualy.set_index("driver_number").position
        data.loc[obj, "q_pos"] = data.loc[obj, "driver_number"].map(qp).values
        # sin tiempo / no clasificados: al fondo en el orden del archivo
        falta = obj & data.q_pos.isna()
        if falta.any():
            base_n = data.loc[obj, "q_pos"].max()
            base_n = 0 if pd.isna(base_n) else base_n
            data.loc[falta, "q_pos"] = base_n + np.arange(1, falta.sum() + 1)

    # FP3, qualy (gap), sprint y degradación por GP
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
        dg = D.deg_gp([(nombres.get(s), s) for s in ("Practice 1", "Practice 2", "Practice 3")])
        if len(dg):
            base = base.merge(dg[["driver_number", "deg_rel", "deg_abs", "deg_laps", "deg_gp_med"]], on="driver_number", how="left")
        rk = nombres.get("Race")
        base["meeting_key"] = m.meeting_key
        base["race_start"] = g[g.session_name == "Race"].date_start.min() if rk else pd.NaT
        extra.append(base)
    extra = pd.concat(extra, ignore_index=True)
    data = data.merge(extra, on=["meeting_key", "driver_number"], how="left")
    for c in Q.FEATURES + ["fp3_gap", "fp3_rank", "fp3_long_gap", "fp3_long_rank", "fp3_ideal_gap",
                           "fp3_soft_gap", "fp3_laps", "sprint_pos", "fp3_trap_delta", "fp3_best",
                           "deg_rel", "deg_abs", "deg_laps", "deg_gp_med"]:
        if c not in data:
            data[c] = np.nan

    # Gap de qualy, compañero, ritmo de carrera combinado
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
    # degradación: equipo y cobertura del campo
    data["deg_team_rel"] = data.groupby(["meeting_key", "team"]).deg_rel.transform("mean")
    data["deg_cov"] = data.groupby("meeting_key").deg_rel.transform("count") / data.n_drivers
    data["ref_lap"] = data.groupby("meeting_key").fp_best_all.transform("min")

    # Emparejar cada GP con su carrera de Jolpica (fecha de carrera dentro del fin de semana)
    carreras = jr[["season", "round", "date", "circuit"]].drop_duplicates(["season", "round"])
    vueltas_carrera = jr.groupby(["season", "round"]).laps.max()
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
    obj = data.meeting_key == meeting
    if parrilla:
        data.loc[obj, "grid"] = data.loc[obj, "driver_number"].map(parrilla)
    data["grid"] = data.grid.fillna(data.q_pos).fillna(data.n_drivers)
    data["grid_penalty"] = data.grid - data.q_pos
    data["grid_team_best"] = data.groupby(["meeting_key", "team"]).grid.transform("min")

    # Historial de carrera y estrategia (corte: inicio del fin de semana, igual que en la qualy)
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
        # vueltas programadas: configuración del GP o la carrera emparejada / edición anterior del circuito
        if mk in GPS_CARRERA:
            vueltas = GPS_CARRERA[mk]["vueltas"]
        elif mk in emparejo:
            vueltas = vueltas_carrera.get((emparejo[mk].season, emparejo[mk]["round"]))
        else:
            vueltas = pc_all.laps.max() if len(pc_all) else np.nan
        est = D.estrategia_circuito(est_tabla, grupo.circuit_key.iloc[0], corte, vueltas)
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
                "est_paradas": est["paradas"], "est_paradas_media": est["paradas_media"],
                "est_perdida_pit": est["perdida_pit"], "est_n_ediciones": est["n_ediciones"], "vueltas": est["vueltas"],
            }
            # degradación observada en las últimas 6 carreras secas del piloto (sólo pasado)
            dh = deg_hist[(deg_hist.name_acronym == row.name_acronym) & (deg_hist.fecha < corte)].race_rel.tail(6)
            h["deg_hist_rel"] = dh.sum() / (len(dh) + 2) if len(dh) else np.nan     # encogida hacia 0
            t = prev[prev.team == row.team]
            ult = t[["season", "round"]].drop_duplicates().tail(5)
            tt = t.merge(ult, on=["season", "round"])
            h["team_r_mean5"] = tt.pos.mean() if len(tt) else np.nan
            h["team_finish_rate5"] = tt.terminado.mean() if len(tt) else np.nan
            hist[idx] = h
    data = data.join(pd.DataFrame.from_dict(hist, orient="index"))
    data["stint_len"] = data.vueltas / (data.est_paradas.round() + 1)
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
# Degradación y estrategia: las usa el simulador (variantes en sim_carrera.py); se dejan fuera del catálogo de ML
# para que la comparación de los 13 modelos sea la misma que la auditada en Austin.
FEATURES_DEG = ["deg_rel", "deg_abs", "deg_laps", "deg_team_rel", "deg_cov", "deg_hist_rel", "est_paradas", "est_paradas_media",
                "est_perdida_pit", "vueltas", "stint_len"]


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


def resumen_metricas(p):
    """Métricas walk-forward medias (todas y por año) de un DataFrame de predicciones."""
    mt = metricas(p, "pred")
    yr = p.groupby("meeting_key").year.first()
    mt["year"] = mt.meeting_key.map(yr)
    out = {"ndcg10": mt.ndcg10.mean()}
    for y in sorted(mt.year.unique()):
        out[f"ndcg10_{y}"] = mt[mt.year == y].ndcg10.mean()
    out.update({"top10_hits": mt.top10_hits.mean(), "pos_exact10": mt.pos_exact10.mean(),
                "mae_top10": mt.mae_top10.mean(), "spearman": mt.spearman.mean(),
                "win_acc": mt.win_hit.mean(), "podium_hits": mt.podium_hits.mean(), "n_gp": int(len(mt))})
    return out


def walk_forward_sim(data, variantes, desde=2024, n_sims=N_SIMS):
    """Walk-forward sólo del simulador (rápido): {nombre_variante: preds}. Incluye el orden de qualy como referencia."""
    entrenables = data.dropna(subset=["race_pos"])
    pruebas = entrenables[entrenables.year >= desde].meeting_key.drop_duplicates().tolist()
    preds = {n: [] for n in list(variantes) + ["Baseline: orden de qualy", "Baseline: orden de parrilla"]}
    for mk in pruebas:
        fecha = entrenables[entrenables.meeting_key == mk].date.iloc[0]
        tr = entrenables[entrenables.date < fecha].sort_values(["meeting_key", "driver_number"])
        te = entrenables[entrenables.meeting_key == mk]
        cab = te[["meeting_key", "driver_number", "year"]].assign(real=te.race_pos.values)
        for n, var in variantes.items():
            sim = Simulador(var).fit(tr)
            preds[n].append(cab.assign(pred=sim.simular(te, n_sims=n_sims, seed=0)[0]))
        preds["Baseline: orden de qualy"].append(cab.assign(pred=te.q_pos.fillna(25).values))
        preds["Baseline: orden de parrilla"].append(cab.assign(pred=te.grid.fillna(25).values))
    return {n: pd.concat(v) for n, v in preds.items()}


def walk_forward(data, desde=2024):
    entrenables = data.dropna(subset=["race_pos"])
    pruebas = entrenables[entrenables.year >= desde].meeting_key.drop_duplicates().tolist()
    cat = catalogo()
    preds = {n: [] for n in list(cat) + [SIM]}
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
        p = te[["meeting_key", "driver_number", "year"]].assign(real=te.race_pos.values)
        p["pred"] = Simulador(MC_VAR).fit(tr).predict(te)
        preds[SIM].append(p)
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


# ----------------------------------------------------------------------------------------
# Parrilla del GP objetivo
# ----------------------------------------------------------------------------------------
def resolver_parrilla(meeting, pilotos, qualy_archivo=None, penalizaciones=None, parrilla_manual=None):
    """pilotos: DataFrame (driver_number, name_acronym) del GP objetivo.
    Devuelve (qualy DataFrame o None, {driver_number: salida} o None, texto de la fuente)."""
    acr2num = dict(zip(pilotos.name_acronym, pilotos.driver_number))
    num2acr = {v: k for k, v in acr2num.items()}
    ruta_q = Path(qualy_archivo) if qualy_archivo else CACHE / f"qualy_real_{meeting}.json"
    qualy = leer_qualy(ruta_q)
    manual = parrilla_manual or GPS_CARRERA.get(meeting, {}).get("parrilla_manual")
    if parrilla_manual:
        faltan = set(acr2num) - set(parrilla_manual)
        if faltan:
            raise SystemExit(f"--parrilla incompleta, faltan: {sorted(faltan)}")
        return qualy, {acr2num[a]: int(p) for a, p in parrilla_manual.items() if a in acr2num}, "Parrilla indicada a mano"
    if manual and not penalizaciones:              # parrilla oficial ya cargada en GPS_CARRERA (p. ej. Austin)
        return qualy, {acr2num[a]: p for a, p in manual.items() if a in acr2num}, "Parrilla configurada en GPS_CARRERA"
    oficial = parrilla_openf1(meeting)
    if oficial and not penalizaciones:
        return qualy, oficial, "Parrilla oficial (OpenF1 starting_grid)"
    if qualy is not None:
        q = qualy.copy()
        q["acr"] = q.driver_number.map(num2acr)
        desconocidos = [a for a in (penalizaciones or {}) if a not in acr2num]
        if desconocidos:
            raise SystemExit(f"Penalizaciones con siglas desconocidas: {desconocidos} (válidas: {sorted(acr2num)})")
        fuera = q[q.acr.isna()].driver_number.tolist()
        if fuera:
            print(f"AVISO: la qualy trae números que no son titulares de este GP: {fuera} (se ignoran)")
        q = q.dropna(subset=["acr"])
        sin_q = sorted(set(acr2num) - set(q.acr))
        if sin_q:
            print(f"AVISO: titulares sin resultado de qualy (salen al fondo): {sin_q}")
        q["pos_ord"] = q.position.fillna(99)
        q = q.sort_values(["pos_ord", "driver_number"])
        orden = {a: i + 1 for i, a in enumerate(q.acr)}
        for a in acr2num:                          # titulares que no aparecen en la qualy: al fondo
            orden.setdefault(a, len(orden) + 1)
        salida = aplicar_penalizaciones(orden, penalizaciones)
        fuente = "Qualy oficial (OpenF1)" if qualy_archivo is None else f"Qualy de archivo ({ruta_q.name})"
        if penalizaciones:
            fuente += " + penalizaciones: " + ", ".join(
                f"{a} {('+' + str(v) + ' lugares') if str(v).lstrip('-').isdigit() else ('al fondo' if str(v).lower() == 'fondo' else 'desde pits')}"
                for a, v in penalizaciones.items())
        return qualy, {acr2num[a]: p for a, p in salida.items()}, fuente
    if manual:
        return None, {acr2num[a]: p for a, p in manual.items() if a in acr2num}, "Parrilla configurada en GPS_CARRERA"
    return None, None, None


# ----------------------------------------------------------------------------------------
# Salida para la página en vivo
# ----------------------------------------------------------------------------------------
def _f(x, nd=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, nd)


def nota_piloto(r, umbral_deg, umbral_dnf):
    """Frase corta por piloto (prioridad: favorito, movimiento, degradación, abandono, gomas)."""
    mov = r.grid - r.pred_rank
    if r.pred_rank == 1:
        return "favorito"
    if mov >= 3 and r.grid_penalty >= 3:
        return "remonta tras la penalización"
    if mov >= 3:
        return "remonta por ritmo" if r.ritmo_rank < r.grid else "remonta"
    if mov <= -3:
        return "pierde posiciones por ritmo" if r.ritmo_rank > r.grid else "pierde posiciones"
    if pd.notna(r.deg_rel) and r.deg_rel >= umbral_deg and r.deg_rel > 0.02:
        return "riesgo de degradación"
    if r.p_dnf >= umbral_dnf:
        return "riesgo de abandono"
    if r.grid_penalty >= 3:
        return "sale con penalización"
    if pd.notna(r.deg_rel) and r.deg_rel <= -0.03:
        return "cuida bien los neumáticos"
    return ""


def doc_carrera(obj, meeting, val, fuente, est, var_nombre):
    gp = Q.GPS.get(meeting, {})
    obj = obj.sort_values("pred_rank")
    umbral = obj.deg_rel.quantile(0.8) if obj.deg_rel.notna().sum() >= 5 else np.inf
    umbral_dnf = max(0.2, obj.p_dnf.quantile(0.85))
    pil = []
    for _, r in obj.iterrows():
        par = r.get("paradas_pred")
        pil.append({
            "acr": r.name_acronym, "nombre": _nombre(r.full_name), "equipo": r.team_name, "color": _color(r.team_colour),
            "salida": int(r.grid), "pred": int(r.pred_rank), "pos_media": _f(r.pos_media, 2),
            "p_win": _f(r.p_win), "p_podio": _f(r.p_podio), "p_top10": _f(r.p_top10), "p_dnf": _f(r.p_dnf),
            "p10": int(r.pos_p10), "p90": int(r.pos_p90), "ritmo_rank": int(r.ritmo_rank),
            "deg_s_vuelta": _f(r.deg_rel, 3), "paradas": None if pd.isna(par) else int(par),
            "nota": nota_piloto(r, umbral, umbral_dnf),
        })
    top = obj.head(3)
    fav = top.iloc[0]
    remontas = obj[(obj.grid - obj.pred_rank) >= 3].sort_values("pred_rank")
    caidas = obj[(obj.grid - obj.pred_rank) <= -3].sort_values("pred_rank")
    n_txt = f"{N_SIMS:,}".replace(",", " ")
    r1 = (f"El simulador ({n_txt} carreras) ve a {_nombre(fav.full_name)} como favorito "
          f"({fav.p_win * 100:.0f}% de victoria); el podio más probable es {', '.join(top.name_acronym)}.")
    r2 = (f"Estrategia esperada: {est['paradas']:.0f} parada{'s' if round(est['paradas']) != 1 else ''} "
          f"(pérdida en pits ≈ {est['perdida_pit']:.0f} s).")
    def motivo(r, sube):
        if sube and r.grid_penalty >= 3:
            return "tras su penalización"
        if sube and r.ritmo_rank < r.grid:
            return "por ritmo de carrera"
        if not sube and r.ritmo_rank > r.grid:
            return "por ritmo de carrera"
        return "por forma reciente"
    mov = []
    if len(remontas):
        mov.append("Remontan " + ", ".join(f"{r.name_acronym} ({int(r.grid)}.º → {int(r.pred_rank)}.º, {motivo(r, True)})"
                                            for _, r in remontas.head(3).iterrows()))
    if len(caidas):
        mov.append("pierden terreno " + ", ".join(f"{r.name_acronym} ({int(r.grid)}.º → {int(r.pred_rank)}.º, {motivo(r, False)})"
                                                  for _, r in caidas.head(2).iterrows()))
    r3 = ("; ".join(mov) + ".") if mov else ""
    return {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modelo": f"Simulador Monte Carlo de carrera ({n_txt} carreras simuladas: {var_nombre})",
        "validacion": {"ndcg10": _f(val["ndcg10"], 4), "top10_hits": _f(val["top10_hits"], 2), "win_acc": _f(val["win_acc"], 3),
                       "podium_hits": _f(val["podium_hits"], 2), "n_gp": int(val["n_gp"])},
        "parrilla_fuente": fuente,
        "vueltas": int(est["vueltas"]) if pd.notna(est["vueltas"]) else GPS_CARRERA.get(meeting, {}).get("vueltas"),
        "estrategia": {"paradas_tipicas": _f(est["paradas"], 1), "perdida_pit_s": _f(est["perdida_pit"], 1),
                       "nota": est["nota"]},
        "pilotos": pil,
        "resumen": " ".join(x for x in (r1, r2, r3) if x),
    }


def _nombre(full):
    if not isinstance(full, str):
        return None
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in full.split())


def _color(c):
    if not isinstance(c, str) or not c.strip():
        return "888888"
    return c.strip().lstrip("#").upper()


def paradas_piloto(obj, est):
    """Paradas esperadas por piloto: las típicas del circuito; +1 si su degradación relativa es muy alta y
    con esa degradación una parada extra cuesta menos que lo que pierde con el stint largo (regla, no validada)."""
    n = round(est["paradas"])
    L, pp = est["vueltas"], est["perdida_pit"]
    out = []
    for _, r in obj.iterrows():
        k = n
        if pd.notna(r.deg_rel) and pd.notna(L) and pd.notna(pp) and r.deg_rel > 0.03:
            # tiempo extra por degradación relativa con n vs n+1 paradas: deg·L²/(2(n+1)) - deg·L²/(2(n+2))
            ahorro = r.deg_rel * L ** 2 * (1 / (2 * (n + 1)) - 1 / (2 * (n + 2)))
            if ahorro > pp:
                k = n + 1
        out.append(k)
    return out


# ----------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------
def main(meeting=OBJETIVO_MEETING, penalizaciones=None, qualy_archivo=None, parrilla_manual=None,
         completo=False, prueba=None, n_sims=N_SIMS, sin_validacion=False):
    t0 = time.time()
    gp = {**Q.GPS.get(meeting, {"slug": str(meeting)}), "meeting_key": meeting}
    slug = gp["slug"]
    salida_dir = Path(prueba) if prueba else BASE
    salida_dir.mkdir(parents=True, exist_ok=True)
    pil = Q.tabla_pilotos()
    ses = Q.tabla_sesiones()
    sk_obj = ses[ses.meeting_key == meeting].set_index("session_name").session_key
    # titulares: qualy > FP3 > FP2 (FP1 puede tener novatos)
    titulares = pil[pil.meeting_key == meeting]
    for s in ("Qualifying", "Practice 3", "Practice 2"):
        if s in sk_obj and (pil.session_key == sk_obj[s]).any():
            titulares = pil[pil.session_key == sk_obj[s]]
            break
    titulares = titulares.drop_duplicates("driver_number")
    if hasattr(Q, "aplicar_sustituciones"):        # p. ej. OCO -> HIR en México 2026 (GPS[...]["sustituciones"])
        cols = ["driver_number", "name_acronym", "full_name", "team", "team_name", "team_colour"]
        titulares = Q.aplicar_sustituciones(titulares[cols].reset_index(drop=True), pil, meeting)
    titulares = titulares[["driver_number", "name_acronym"]]
    qualy, parrilla, fuente = resolver_parrilla(meeting, titulares, qualy_archivo, penalizaciones, parrilla_manual)
    if parrilla is None:
        raise SystemExit(f"No hay parrilla para {meeting}: falta cache/qualy_real_{meeting}.json "
                         "(o pasar --qualy-archivo / --parrilla).")
    print("Parrilla:", fuente)

    print("Construyendo dataset de carrera...")
    data, meetings = construir_dataset_carrera(meeting, qualy=qualy, parrilla=parrilla)
    if prueba is None:
        data.to_csv(BASE / "dataset_carrera.csv", index=False)
    else:
        data.to_csv(salida_dir / "dataset_carrera.csv", index=False)
    obj = data[data.meeting_key == meeting].copy().reset_index(drop=True)
    # sólo GPs anteriores al objetivo (al reproducir un GP pasado no se entrena con carreras posteriores)
    historia = data[(data.meeting_key != meeting) & data.race_pos.notna() & (data.date < obj.date.min())]
    print(f"Filas: {len(historia)} | GPs: {historia.meeting_key.nunique()} | ({time.time() - t0:.0f} s)")
    print("Parrilla objetivo:", dict(zip(obj.name_acronym, obj.grid.astype(int))))

    # Validación: walk-forward del simulador oficial (rápido) o guardada
    val_f = BASE / "validacion_carrera.json"
    val = None
    if not sin_validacion:
        print("Validación walk-forward 2024-2026 del simulador...")
        preds = walk_forward_sim(historia, {SIM: MC_VAR}, n_sims=n_sims)
        tab = {n: resumen_metricas(p) for n, p in preds.items()}
        for n, v in tab.items():
            print(f"  {n:38s} NDCG@10 {v['ndcg10']:.4f} | top10 {v['top10_hits']:.2f} | win {v['win_acc']:.3f} | "
                  f"podio {v['podium_hits']:.2f} | n={v['n_gp']}")
        val = tab[SIM]
    elif val_f.exists():
        val = json.loads(val_f.read_text())["oficial"]["metricas"]
    else:
        val = {"ndcg10": np.nan, "top10_hits": np.nan, "win_acc": np.nan, "podium_hits": np.nan, "n_gp": 0}

    if completo:
        print("Comparación completa de modelos (lento)...")
        tabla, _ = walk_forward(historia)
        print(tabla.to_string(index=False))
        tabla.to_csv(salida_dir / f"comparacion_modelos_carrera_{slug}.csv", index=False)

    # Pronóstico: N carreras simuladas
    sim = Simulador(MC_VAR).fit(historia)
    media, mu, sig, p_dnf, pos = sim.simular(obj, n_sims=n_sims, seed=0)
    obj["score"] = media
    obj["pred_rank"] = obj.score.rank(method="first").astype(int)
    mc = pd.DataFrame({"p_win": (pos == 1).mean(0), "p_podio": (pos <= 3).mean(0), "p_top10": (pos <= 10).mean(0),
                       "p_dnf": p_dnf, "pos_media": media, "pos_p10": np.percentile(pos, 10, axis=0),
                       "pos_p90": np.percentile(pos, 90, axis=0)})
    obj = pd.concat([obj, mc], axis=1)
    d = prep(obj)
    obj["ritmo_rank"] = d.pace_r.rank(method="first").astype(int).values
    est_row = obj.iloc[0]
    est = {"paradas": est_row.est_paradas, "perdida_pit": est_row.est_perdida_pit, "vueltas": est_row.vueltas,
           "n_ediciones": int(est_row.est_n_ediciones)}
    obj["paradas_pred"] = paradas_piloto(obj, est)
    est["nota"] = (f"Paradas típicas y pérdida en pits: mediana de {est['n_ediciones']} edicion(es) anteriores en seco "
                   f"(OpenF1). deg_s_vuelta = degradación de neumáticos en tandas largas de FP1-FP3 relativa al promedio "
                   f"del campo en el mismo compuesto (s/vuelta, corregida por combustible; + = degrada más).")
    obj = obj.sort_values("pred_rank").reset_index(drop=True)
    csv = salida_dir / f"prediccion_carrera_{slug}_2026.csv"
    obj.to_csv(csv, index=False)

    doc = doc_carrera(obj, meeting, val, fuente, est, VARIANTE_NOMBRE)
    web_dir = BASE / f"web_{slug}"
    ruta_json = (salida_dir / "datos_carrera.json") if prueba else (
        web_dir / "datos_carrera.json" if web_dir.exists() else BASE / f"datos_carrera_{slug}.json")
    ruta_json.write_text(json.dumps(doc, ensure_ascii=False, indent=1))

    if completo and meeting == 1297 and prueba is None:
        print("(El reporte HTML temático de Austin se regenera con la versión anterior del flujo.)")
    print(f"\nPRONÓSTICO ORDEN FINAL ({fuente}):")
    print(obj[["pred_rank", "name_acronym", "grid", "q_pos", "ritmo_rank", "deg_rel", "paradas_pred",
               "p_top10", "p_podio", "p_win", "p_dnf"]].round(3).to_string(index=False))
    print(f"\nEscrito: {csv}\nEscrito: {ruta_json}\n({time.time() - t0:.0f} s)")
    return obj, doc


VARIANTE_NOMBRE = ("salida, ritmo de tanda larga FP1-FP3, gap de qualy, forma de piloto y equipo, facilidad de rebase "
                   "del circuito, primera vuelta e incidentes, abandonos")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Pronóstico del orden final de carrera (simulador Monte Carlo).")
    ap.add_argument("meeting", nargs="?", type=int, default=OBJETIVO_MEETING)
    ap.add_argument("--penalizaciones", default=None, help='JSON {"ACR": lugares | "fondo" | "pits"}')
    ap.add_argument("--qualy-archivo", default=None, help="lista OpenF1 session_result (default cache/qualy_real_<mk>.json)")
    ap.add_argument("--parrilla", default=None, help='JSON {"ACR": salida} con la parrilla completa')
    ap.add_argument("--prueba", default=None, help="directorio: escribe CSV/JSON/dataset ahí y no toca los archivos oficiales")
    ap.add_argument("--completo", action="store_true", help="también compara los 13 modelos de ML (lento)")
    ap.add_argument("--sin-validacion", action="store_true", help="usa la validación guardada en validacion_carrera.json")
    ap.add_argument("--sims", type=int, default=N_SIMS)
    ap.add_argument("--solo-dataset", action="store_true", help="sólo reconstruye dataset_carrera.csv (sin parrilla ni pronóstico)")
    a = ap.parse_args()
    if a.solo_dataset:
        d, _ = construir_dataset_carrera(a.meeting)
        d.to_csv(BASE / "dataset_carrera.csv", index=False)
        print("Escrito", BASE / "dataset_carrera.csv", len(d), "filas")
        raise SystemExit
    main(a.meeting, json.loads(a.penalizaciones) if a.penalizaciones else None, a.qualy_archivo,
         json.loads(a.parrilla) if a.parrilla else None, a.completo, a.prueba, a.sims, a.sin_validacion)
