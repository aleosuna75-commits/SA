"""
Modelo de predicción del Top 10 de la Qualy - GP de Estados Unidos (COTA, Austin) 2026.

Fuentes:
  * OpenF1 (2023-2026): vueltas, sectores, speed trap, stints/compuestos y clima de FP1/FP2,
    resultados de Qualy (objetivo).
  * Jolpica/Ergast (2018-2026): historial de qualys y carreras para forma reciente,
    historial por circuito y COTA desde 2012.

Flujo:
  1. descarga_datos.py cachea todo en ./cache
  2. Se construye una fila por piloto-fin de semana con ~60 variables (solo info disponible
     ANTES de la qualy: FP1, FP2 e historial previo).
  3. Validación walk-forward (cada GP 2024-2026 se predice entrenando solo con GPs anteriores)
     comparando baselines, Ridge, Random Forest, Extra Trees, GBM, XGBoost, LightGBM
     (regresión y LambdaRank) y ensambles.
  4. Se elige el mejor por aciertos en el Top 10 (desempate: Spearman) y se reentrena con todo.
  5. Simulación Monte Carlo con los residuos de validación -> P(Q3), P(pole), P(Top 3).
  6. Se genera reporte_qualy_austin_2026.html (estilo texano).

Uso:  python3 modelo_qualy_austin.py [meeting_key]     (1297 = Austin, 1298 = México)
      python3 modelo_qualy_austin.py 1298 --fp3 [--jobs 2] [--modelos "Random Forest"]
          versión sábado: agrega variables de FP3 (NaN en fines de semana sprint) y escribe
          *_fp3 (resultado_qualy_<slug>_fp3.pkl, prediccion_qualy_<slug>_fp3_2026.csv, ...) sin
          tocar el pronóstico FP1/FP2. --jobs (o F1_N_JOBS) limita los hilos de RF/ET/XGB/LGB.
      python3 modelo_qualy_austin.py html <slug>[_fp3]  -> regenera sólo el HTML desde el .pkl
"""
import json
import os
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent
CACHE = BASE / "cache"
OBJETIVO_MEETING = 1297          # United States Grand Prix 2026 (default; ver GPS y main(meeting))

# Configuración por GP objetivo: textos del reporte, circuito en Jolpica y tema visual
GPS = {
    1297: {"slug": "austin", "nombre": "United States Grand Prix", "circuito": "Circuit of the Americas",
           "ciudad": "Austin, Texas", "circuito_jolpica": "americas", "fecha_texto": "Sábado 24 de octubre de 2026",
           "hora_texto": "4:00 PM CT", "tema": "texas"},
    1298: {"slug": "mexico", "nombre": "Gran Premio de la Ciudad de México", "circuito": "Autódromo Hermanos Rodríguez",
           "ciudad": "Ciudad de México", "circuito_jolpica": "rodriguez", "fecha_texto": "Sábado 31 de octubre de 2026",
           "hora_texto": "3:00 PM (hora CDMX)", "tema": "muertos"},
}
AÑOS = [2023, 2024, 2025, 2026]
SEED = 7
# Hilos para RF/ET/XGB/LGB. -1 = comportamiento original (RF/ET todos los núcleos, XGB 4).
# Los resultados de RF/ET con random_state fijo no dependen de n_jobs.
N_JOBS = int(os.environ.get("F1_N_JOBS", "-1"))

# Continuidad de escuderías entre renombres
EQUIPO_CANON = {
    "AlphaTauri": "Racing Bulls", "RB": "Racing Bulls", "Racing Bulls": "Racing Bulls",
    "Alfa Romeo": "Audi", "Kick Sauber": "Audi", "Sauber": "Audi", "Audi": "Audi",
    "Haas F1 Team": "Haas", "Red Bull Racing": "Red Bull",
    # nombres de constructor en Jolpica
    "RB F1 Team": "Racing Bulls", "Alpine F1 Team": "Alpine", "Cadillac F1 Team": "Cadillac",
}


def cargar(nombre):
    return json.loads((CACHE / f"{nombre}.json").read_text())


# ----------------------------------------------------------------------------------------
# 1. Sesiones y resultados OpenF1
# ----------------------------------------------------------------------------------------
def tabla_sesiones():
    filas = []
    for a in AÑOS:
        for s in cargar(f"sessions_{a}"):
            filas.append(s)
    ses = pd.DataFrame(filas)
    ses = ses[~ses["session_name"].str.startswith("Day")]
    ses["date_start"] = pd.to_datetime(ses["date_start"])
    return ses


def tabla_resultados():
    filas = []
    for a in AÑOS:
        filas += cargar(f"results_{a}")
    return pd.DataFrame(filas)


def tabla_pilotos():
    filas = []
    for a in AÑOS:
        filas += cargar(f"drivers_{a}")
    d = pd.DataFrame(filas)[["session_key", "meeting_key", "driver_number", "name_acronym",
                             "full_name", "team_name", "team_colour"]]
    d["team"] = d["team_name"].map(lambda t: EQUIPO_CANON.get(t, t))
    return d


# ----------------------------------------------------------------------------------------
# 2. Features de prácticas libres
# ----------------------------------------------------------------------------------------
def features_practica(sk, pref):
    laps_f, st_f = CACHE / f"laps_{sk}.json", CACHE / f"stints_{sk}.json"
    if not laps_f.exists():
        return pd.DataFrame()
    laps = pd.DataFrame(json.loads(laps_f.read_text()))
    if laps.empty:
        return pd.DataFrame()
    stints = pd.DataFrame(json.loads(st_f.read_text())) if st_f.exists() else pd.DataFrame()
    w_f = CACHE / f"weather_{sk}.json"
    weather = pd.DataFrame(json.loads(w_f.read_text())) if w_f.exists() else pd.DataFrame()

    laps["compound"] = None
    laps["stint"] = np.nan
    if not stints.empty:
        for _, s in stints.iterrows():
            if pd.isna(s.get("lap_start")) or pd.isna(s.get("lap_end")):
                continue
            m = (laps.driver_number == s.driver_number) & laps.lap_number.between(s.lap_start, s.lap_end)
            laps.loc[m, "compound"] = s.get("compound")
            laps.loc[m, "stint"] = s.stint_number

    n_vueltas = laps.groupby("driver_number").size()
    v = laps[laps.lap_duration.notna() & (laps.is_pit_out_lap != True)].copy()
    # descartar vueltas cuyo tiempo no cuadra con la suma de sectores (datos corruptos)
    suma = v[["duration_sector_1", "duration_sector_2", "duration_sector_3"]].sum(axis=1, min_count=3)
    v = v[~((suma - v.lap_duration).abs() > 1.0)]
    if v.empty:
        return pd.DataFrame()
    # referencia robusta: 3.ª mejor marca entre pilotos (no el mínimo absoluto)
    mejores = v.groupby("driver_number").lap_duration.min().sort_values()
    mejor_ses = mejores.iloc[min(2, len(mejores) - 1)]
    v = v[v.lap_duration < mejor_ses * 1.12]
    out = pd.DataFrame(index=sorted(laps.driver_number.unique()))
    out.index.name = "driver_number"

    best = v.groupby("driver_number").lap_duration.min()
    out[f"{pref}_best"] = best
    out[f"{pref}_gap"] = (best - best.min()) / best.min() * 100
    out[f"{pref}_rank"] = best.rank(method="min")
    out[f"{pref}_laps"] = n_vueltas

    # Vuelta ideal (suma de mejores sectores) y ranking por sector
    sect = {}
    for i in (1, 2, 3):
        c = f"duration_sector_{i}"
        sb = laps[laps[c].notna() & (laps.is_pit_out_lap != True)].groupby("driver_number")[c].min()
        sb = sb[sb > 0]
        sect[i] = sb
        out[f"{pref}_s{i}_gap"] = (sb - sb.min()) / sb.min() * 100
    ideal = sect[1] + sect[2] + sect[3]
    out[f"{pref}_ideal_gap"] = (ideal - ideal.min()) / ideal.min() * 100
    out[f"{pref}_ideal_rank"] = ideal.rank(method="min")

    # Velocidades punta
    for c, nom in (("st_speed", "trap"), ("i1_speed", "i1"), ("i2_speed", "i2")):
        sp = laps.groupby("driver_number")[c].max()
        out[f"{pref}_{nom}_delta"] = sp - sp.max()

    # Simulación de qualy: mejor vuelta con blando
    sv = v[v.compound == "SOFT"]
    if not sv.empty:
        sb = sv.groupby("driver_number").lap_duration.min()
        out[f"{pref}_soft_gap"] = (sb - sb.min()) / sb.min() * 100
    else:
        out[f"{pref}_soft_gap"] = np.nan

    # Tanda larga: stints con >=5 vueltas representativas
    lr = {}
    for (dn, st), g in v.dropna(subset=["stint"]).groupby(["driver_number", "stint"]):
        g = g.sort_values("lap_number")
        g = g[g.lap_duration < g.lap_duration.min() + 2.5]
        if len(g) >= 5:
            lr.setdefault(dn, []).append(g.lap_duration.median())
    lr = pd.Series({k: min(x) for k, x in lr.items()}, dtype=float)
    if len(lr):
        out[f"{pref}_long_gap"] = (lr - lr.min()) / lr.min() * 100
        out[f"{pref}_long_rank"] = lr.rank(method="min")
    else:
        out[f"{pref}_long_gap"] = np.nan
        out[f"{pref}_long_rank"] = np.nan

    # Consistencia: desviación de las 3 mejores vueltas
    top3 = v.sort_values("lap_duration").groupby("driver_number").head(3)
    out[f"{pref}_top3_spread"] = top3.groupby("driver_number").lap_duration.agg(lambda x: x.max() - x.min())

    if not weather.empty:
        out[f"{pref}_track_temp"] = weather.track_temperature.mean()
        out[f"{pref}_rain"] = float(weather.rainfall.max() > 0)
    else:
        out[f"{pref}_track_temp"] = np.nan
        out[f"{pref}_rain"] = np.nan
    return out.reset_index()


# ----------------------------------------------------------------------------------------
# 3. Historial Jolpica (forma, circuito, COTA)
# ----------------------------------------------------------------------------------------
def tabla_jolpica(tipo):
    filas = []
    for f in sorted(CACHE.glob(f"jolpica_{tipo}_*.json")):
        for r in json.loads(f.read_text())["MRData"]["RaceTable"]["Races"]:
            clave = "QualifyingResults" if tipo == "qualifying" else "Results"
            for q in r.get(clave, []):
                filas.append({
                    "season": int(r["season"]), "round": int(r["round"]), "date": r["date"],
                    "circuit": r["Circuit"]["circuitId"], "code": q["Driver"].get("code"),
                    "driverId": q["Driver"]["driverId"],
                    "pos": int(q["position"]) if q.get("position", "").isdigit() else np.nan,
                    "team": q["Constructor"]["name"],
                    "points": float(q.get("points", 0) or 0),
                    "status": q.get("status", ""),
                })
    df = pd.DataFrame(filas).drop_duplicates(["season", "round", "driverId"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def tabla_cota(circuito="americas"):
    """Historial de qualys de un circuito (Jolpica). COTA usa los archivos jolpica_cota_*."""
    patron = "jolpica_cota_*.json" if circuito == "americas" else f"jolpica_circ_{circuito}_*.json"
    filas = []
    for f in sorted(CACHE.glob(patron)):
        for r in json.loads(f.read_text())["MRData"]["RaceTable"]["Races"]:
            for q in r["QualifyingResults"]:
                filas.append({"season": int(r["season"]), "code": q["Driver"].get("code"),
                              "name": f'{q["Driver"]["givenName"]} {q["Driver"]["familyName"]}',
                              "team": q["Constructor"]["name"], "pos": int(q["position"])})
    return pd.DataFrame(filas).drop_duplicates(["season", "code"])


# ----------------------------------------------------------------------------------------
# 4. Dataset piloto-fin de semana
# ----------------------------------------------------------------------------------------
def construir_dataset(con_fp3=False):
    """con_fp3=True agrega variables de la FP3 (sábado, antes de la qualy) y combinadas FP1-3.
    En fines de semana sprint no hay FP3: fp3_* queda NaN y las combinadas usan FP1/FP2."""
    ses = tabla_sesiones()
    res = tabla_resultados()
    pil = tabla_pilotos()
    jq, jr = tabla_jolpica("qualifying"), tabla_jolpica("results")

    meetings = []
    for mk, g in ses.groupby("meeting_key"):
        nombres = dict(zip(g.session_name, g.session_key))
        if "Qualifying" not in nombres or "Practice 1" not in nombres:
            continue
        carrera = g[g.session_name == "Race"]
        fecha_carrera = carrera.date_start.iloc[0].normalize().tz_localize(None) if len(carrera) else None
        meetings.append({
            "meeting_key": mk, "year": g.year.iloc[0], "date": g.date_start.min(),
            "circuit": g.circuit_short_name.iloc[0], "circuit_key": g.circuit_key.iloc[0],
            "fp1": nombres.get("Practice 1"), "fp2": nombres.get("Practice 2"), "fp3": nombres.get("Practice 3"),
            "q": nombres["Qualifying"], "sprint": int("Sprint" in nombres),
            "race_date": fecha_carrera,
        })
    meetings = pd.DataFrame(meetings).sort_values("date").reset_index(drop=True)

    filas = []
    for _, m in meetings.iterrows():
        # pilotos titulares: los de la qualy; si aún no existe, los de FP3/FP2 (en FP1 puede haber novatos)
        dq = pil[pil.meeting_key == m.meeting_key]
        for sk in (m.q, m.fp3, m.fp2):
            if pd.notna(sk) and (pil.session_key == sk).any():
                dq = pil[pil.session_key == sk]
                break
        dq = dq.drop_duplicates("driver_number")
        base = dq[["driver_number", "name_acronym", "full_name", "team", "team_name", "team_colour"]].copy()
        f1 = features_practica(int(m.fp1), "fp1")
        f2 = features_practica(int(m.fp2), "fp2") if pd.notna(m.fp2) else pd.DataFrame()
        if f1.empty and f2.empty:
            continue
        df = base.merge(f1, on="driver_number", how="left") if not f1.empty else base
        if not f2.empty:
            df = df.merge(f2, on="driver_number", how="left")
        if con_fp3 and pd.notna(m.fp3):
            f3 = features_practica(int(m.fp3), "fp3")
            if not f3.empty:
                df = df.merge(f3, on="driver_number", how="left")
        qr = res[res.session_key == m.q][["driver_number", "position"]].rename(columns={"position": "q_pos"})
        df = df.merge(qr, on="driver_number", how="left")
        df["q_pos"] = pd.to_numeric(df.q_pos, errors="coerce")
        for c in ("meeting_key", "year", "date", "circuit", "circuit_key", "sprint", "race_date"):
            df[c] = m[c]
        filas.append(df)
    data = pd.concat(filas, ignore_index=True)

    # Combinado FP1+FP2
    if "fp2_best" not in data:
        for c in [c for c in data.columns if c.startswith("fp1_")]:
            data[c.replace("fp1_", "fp2_")] = np.nan
    data["comb_best"] = data[["fp1_best", "fp2_best"]].min(axis=1)
    g = data.groupby("meeting_key")
    data["comb_gap"] = (data.comb_best - g.comb_best.transform("min")) / g.comb_best.transform("min") * 100
    data["comb_rank"] = g.comb_best.rank(method="min")
    data["main_gap"] = data.fp2_gap.fillna(data.fp1_gap)           # sesión más representativa
    data["main_rank"] = data.fp2_rank.fillna(data.fp1_rank)
    data["fp_improve"] = data.fp1_rank - data.fp2_rank              # mejora de FP1 a FP2
    data["ideal_best_gap"] = data[["fp1_ideal_gap", "fp2_ideal_gap"]].min(axis=1)
    data["laps_total"] = data[["fp1_laps", "fp2_laps"]].sum(axis=1, min_count=1)
    data["long_gap_best"] = data[["fp1_long_gap", "fp2_long_gap"]].min(axis=1)
    data["fp_rain"] = data[["fp1_rain", "fp2_rain"]].max(axis=1)
    if con_fp3:
        data = agregar_combinadas_fp3(data)

    # Compañero de equipo y nivel de la escudería
    data["team_best_gap"] = data.groupby(["meeting_key", "team"]).comb_gap.transform("min")
    data["team_mean_gap"] = data.groupby(["meeting_key", "team"]).comb_gap.transform("mean")
    data["teammate_delta"] = data.comb_gap - data.team_best_gap
    tr = data.groupby("meeting_key").team_best_gap.rank(method="dense")
    data["team_fp_rank"] = tr
    data["n_drivers"] = data.groupby("meeting_key").driver_number.transform("count")

    # ---------------- Historial (solo información anterior a cada fin de semana) -------------
    data = data.sort_values(["date", "driver_number"]).reset_index(drop=True)
    jq = jq.sort_values("date")
    jr = jr.sort_values("date")
    jq_team = jq.assign(team=jq.team.map(lambda t: EQUIPO_CANON.get(t, t)))

    # circuit_key (OpenF1) -> circuitId (Jolpica), aprendido de los GPs ya corridos
    mapa_circ = {}
    for _, m in meetings.iterrows():
        mismo = jq[jq.date == m.race_date]
        if len(mismo):
            mapa_circ[m.circuit_key] = mismo.circuit.iloc[0]

    hist = defaultdict(dict)
    for mk, grupo in data.groupby("meeting_key", sort=False):
        # inicio del fin de semana (FP1): la carrera anterior siempre cae antes y la del propio GP después
        fecha = pd.Timestamp(grupo.date.iloc[0]).tz_convert(None).normalize()
        circuito_jolpica = mapa_circ.get(grupo.circuit_key.iloc[0])
        prev_q = jq[jq.date < fecha]
        prev_r = jr[jr.date < fecha]
        temporada = grupo.year.iloc[0]
        for idx, row in grupo.iterrows():
            code = row.name_acronym
            pq = prev_q[prev_q.code == code]
            pr = prev_r[prev_r.code == code]
            h = {}
            h["h_q_last"] = pq.pos.iloc[-1] if len(pq) else np.nan
            for n in (3, 5, 10):
                h[f"h_q_mean{n}"] = pq.pos.tail(n).mean() if len(pq) else np.nan
            h["h_q_season"] = pq[pq.season == temporada].pos.mean() if len(pq) else np.nan
            h["h_q3_rate10"] = (pq.pos.tail(10) <= 10).mean() if len(pq) else np.nan
            h["h_q_std10"] = pq.pos.tail(10).std() if len(pq) > 2 else np.nan
            h["h_r_mean5"] = pr.pos.tail(5).mean() if len(pr) else np.nan
            h["h_pts_season"] = pr[pr.season == temporada].points.sum() if len(pr) else 0.0
            h["h_dnf_rate10"] = (~pr.tail(10).status.str.contains("Finished|Lap", regex=True)).mean() if len(pr) else np.nan
            h["h_experience"] = len(pq)
            if circuito_jolpica:
                pc = pq[pq.circuit == circuito_jolpica]
                h["h_circ_mean"] = pc.pos.mean() if len(pc) else np.nan
                h["h_circ_best"] = pc.pos.min() if len(pc) else np.nan
                h["h_circ_n"] = len(pc)
            else:
                h["h_circ_mean"] = h["h_circ_best"] = np.nan
                h["h_circ_n"] = 0
            # forma de la escudería
            tq = jq_team[(jq_team.date < fecha) & (jq_team.team == row.team)]
            ult = tq.date.drop_duplicates().tail(5)
            h["h_team_q_mean5"] = tq[tq.date.isin(ult)].pos.mean() if len(tq) else np.nan
            hist[idx] = h
    H = pd.DataFrame.from_dict(hist, orient="index")
    data = data.join(H)
    data["h_pts_rank"] = data.groupby("meeting_key").h_pts_season.rank(ascending=False, method="min")

    # Sesgo histórico "prácticas -> qualy": cuánto gana/pierde el piloto vs su rank de FP
    data["fp_to_q"] = data.q_pos - data.comb_rank
    data["h_fp_to_q_driver"] = (data.groupby("name_acronym").fp_to_q
                                .transform(lambda s: s.shift(1).rolling(8, min_periods=2).mean()))
    data["h_fp_to_q_team"] = (data.groupby("team").fp_to_q
                              .transform(lambda s: s.shift(1).rolling(12, min_periods=3).mean()))
    # la primera fila de cada (GP, equipo) sólo ve GPs anteriores: se usa para ambos pilotos
    data["h_fp_to_q_team"] = data.groupby(["meeting_key", "team"]).h_fp_to_q_team.transform("first")
    # Posición para evaluar: los que no marcaron tiempo en qualy van al fondo
    data["q_eval"] = data.q_pos.fillna(99)
    data["q_eval"] = data.groupby("meeting_key").q_eval.rank(method="first")
    data["year_idx"] = data.year - 2023
    data["is_2026_regs"] = (data.year >= 2026).astype(int)
    return data, meetings


def agregar_combinadas_fp3(data):
    """Variables combinadas FP1-FP3 por GP (sólo información de ese fin de semana, previa a la qualy)."""
    for c in [c for c in data.columns if c.startswith("fp1_")]:
        c3 = c.replace("fp1_", "fp3_")
        if c3 not in data:                     # ningún GP con FP3 (o todos sprint)
            data[c3] = np.nan
    g = data.groupby("meeting_key")
    data["c3_best"] = data[["fp1_best", "fp2_best", "fp3_best"]].min(axis=1)
    data["c3_gap"] = (data.c3_best - g.c3_best.transform("min")) / g.c3_best.transform("min") * 100
    data["c3_rank"] = g.c3_best.rank(method="min")
    data["main3_gap"] = data.fp3_gap.fillna(data.fp2_gap).fillna(data.fp1_gap)   # última sesión disponible
    data["main3_rank"] = data.fp3_rank.fillna(data.fp2_rank).fillna(data.fp1_rank)
    data["fp3_improve"] = data.fp2_rank - data.fp3_rank            # mejora de FP2 a FP3 (NaN en sprint)
    data["ideal3_best_gap"] = data[["fp1_ideal_gap", "fp2_ideal_gap", "fp3_ideal_gap"]].min(axis=1)
    data["long3_gap_best"] = data[["fp1_long_gap", "fp2_long_gap", "fp3_long_gap"]].min(axis=1)
    data["laps3_total"] = data[["fp1_laps", "fp2_laps", "fp3_laps"]].sum(axis=1, min_count=1)
    data["team3_best_gap"] = data.groupby(["meeting_key", "team"]).c3_gap.transform("min")
    data["teammate3_delta"] = data.c3_gap - data.team3_best_gap
    data["has_fp3"] = data.groupby("meeting_key").fp3_best.transform(lambda s: float(s.notna().any()))
    return data


FEATURES = [
    # FP1
    "fp1_gap", "fp1_rank", "fp1_laps", "fp1_ideal_gap", "fp1_s1_gap", "fp1_s2_gap", "fp1_s3_gap",
    "fp1_trap_delta", "fp1_soft_gap", "fp1_long_gap", "fp1_top3_spread",
    # FP2
    "fp2_gap", "fp2_rank", "fp2_laps", "fp2_ideal_gap", "fp2_ideal_rank", "fp2_s1_gap", "fp2_s2_gap",
    "fp2_s3_gap", "fp2_trap_delta", "fp2_i1_delta", "fp2_i2_delta", "fp2_soft_gap", "fp2_long_gap",
    "fp2_long_rank", "fp2_top3_spread", "fp2_track_temp",
    # Combinadas
    "comb_gap", "comb_rank", "main_gap", "main_rank", "fp_improve", "ideal_best_gap", "laps_total",
    "long_gap_best", "fp_rain", "team_best_gap", "team_mean_gap", "teammate_delta", "team_fp_rank",
    "sprint", "n_drivers",
    # Historial
    "h_q_last", "h_q_mean3", "h_q_mean5", "h_q_mean10", "h_q_season", "h_q3_rate10", "h_q_std10",
    "h_r_mean5", "h_pts_season", "h_pts_rank", "h_dnf_rate10", "h_experience", "h_circ_mean",
    "h_circ_best", "h_circ_n", "h_team_q_mean5", "h_fp_to_q_driver", "h_fp_to_q_team",
    "year_idx", "is_2026_regs",
]

# Versión sábado (después de la FP3): todo lo anterior + FP3 + combinadas FP1-FP3
FEATURES_FP3 = FEATURES + [
    # FP3
    "fp3_gap", "fp3_rank", "fp3_laps", "fp3_ideal_gap", "fp3_ideal_rank", "fp3_s1_gap", "fp3_s2_gap",
    "fp3_s3_gap", "fp3_trap_delta", "fp3_i1_delta", "fp3_i2_delta", "fp3_soft_gap", "fp3_long_gap",
    "fp3_top3_spread", "fp3_track_temp", "fp3_rain",
    # Combinadas FP1-FP3
    "c3_gap", "c3_rank", "main3_gap", "main3_rank", "fp3_improve", "ideal3_best_gap", "long3_gap_best",
    "laps3_total", "team3_best_gap", "teammate3_delta", "has_fp3",
]


# ----------------------------------------------------------------------------------------
# 5. Modelos
# ----------------------------------------------------------------------------------------
def pesos(df):
    # Más peso a lo reciente (2026 = nuevo reglamento)
    return np.where(df.year >= 2026, 3.0, np.where(df.year == 2025, 1.5, 1.0))


def relevancia(pos):
    return np.clip(21 - pos, 0, 30).astype(int)


class Modelo:
    def __init__(self, nombre, tipo, est=None):
        self.nombre, self.tipo, self.est = nombre, tipo, est

    def fit(self, X, y, w, grupos=None):
        if self.tipo == "baseline":
            return self
        if self.tipo == "rank":
            orden = X.index
            self.est.fit(X, relevancia(y), group=grupos, sample_weight=None)
        elif self.tipo == "sk":
            try:
                self.est.fit(X, y, **{f"{self.est.steps[-1][0]}__sample_weight": w})
            except Exception:
                self.est.fit(X, y)
        else:
            self.est.fit(X, y, sample_weight=w)
        return self

    def predict(self, X):
        """Devuelve 'posición esperada' (menor = mejor)."""
        if self.tipo == "baseline":
            return X[self.est].fillna(25).values
        p = self.est.predict(X)
        return -p if self.tipo == "rank" else p


def catalogo(con_fp3=False):
    imp = lambda: SimpleImputer(strategy="median")
    nj = N_JOBS
    xgb_jobs = 4 if nj < 0 else nj
    lgb_jobs = {} if nj < 0 else {"n_jobs": nj}
    cat = {
        "Baseline: rank FP2 (o FP1)": lambda: Modelo("b1", "baseline", "main_rank"),
        "Baseline: mejor vuelta FP1+FP2": lambda: Modelo("b2", "baseline", "comb_rank"),
        "Ridge": lambda: Modelo("ridge", "sk", make_pipeline(imp(), StandardScaler(), Ridge(alpha=10))),
        "Random Forest": lambda: Modelo("rf", "sk", make_pipeline(imp(), RandomForestRegressor(
            n_estimators=500, min_samples_leaf=4, max_features=0.4, random_state=SEED, n_jobs=nj))),
        "Extra Trees": lambda: Modelo("et", "sk", make_pipeline(imp(), ExtraTreesRegressor(
            n_estimators=600, min_samples_leaf=3, max_features=0.5, random_state=SEED, n_jobs=nj))),
        "Gradient Boosting": lambda: Modelo("gb", "sk", make_pipeline(imp(), GradientBoostingRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.03, subsample=0.8, random_state=SEED))),
        "XGBoost": lambda: Modelo("xgb", "native", xgb.XGBRegressor(
            n_estimators=500, max_depth=3, learning_rate=0.03, subsample=0.8, colsample_bytree=0.6,
            min_child_weight=3, reg_lambda=2.0, random_state=SEED, n_jobs=xgb_jobs)),
        "LightGBM": lambda: Modelo("lgb", "native", lgb.LGBMRegressor(
            n_estimators=500, num_leaves=15, learning_rate=0.03, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.6, min_child_samples=15, reg_lambda=2.0, random_state=SEED, verbose=-1, **lgb_jobs)),
        "LightGBM LambdaRank": lambda: Modelo("lgbr", "rank", lgb.LGBMRanker(
            n_estimators=400, num_leaves=15, learning_rate=0.03, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.6, min_child_samples=15, random_state=SEED, verbose=-1,
            label_gain=list(range(31)), **lgb_jobs)),
        "XGBoost Ranker": lambda: Modelo("xgbr", "rank", xgb.XGBRanker(
            n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.6,
            objective="rank:pairwise", random_state=SEED, n_jobs=xgb_jobs)),
    }
    if con_fp3:
        cat = {"Baseline: rank FP3 (o FP2/FP1)": lambda: Modelo("b3", "baseline", "main3_rank"),
               "Baseline: mejor vuelta FP1-FP3": lambda: Modelo("b4", "baseline", "c3_rank"), **cat}
    return cat


def metricas(df_pred, col):
    out = []
    for mk, g in df_pred.groupby("meeting_key"):
        g = g.dropna(subset=["q_pos"])
        pr = g[col].rank(method="first")
        top_real = set(g[g.q_pos <= 10].driver_number)
        top_pred = set(g[pr <= 10].driver_number)
        out.append({
            "meeting_key": mk,
            "top10_hits": len(top_real & top_pred),
            "spearman": spearmanr(pr, g.q_pos).correlation,
            "mae": np.abs(pr - g.q_pos).mean(),
            "pole_hit": int(g.loc[pr.idxmin(), "q_pos"] == 1),
            "top3_hits": len(set(g[g.q_pos <= 3].driver_number) & set(g[pr <= 3].driver_number)),
        })
    return pd.DataFrame(out)


def walk_forward(data, desde=2024, features=None, con_fp3=False, nombres=None):
    """Entrena con pilotos con tiempo de qualy; evalúa con TODOS los inscritos (sin tiempo = al fondo).
    features: lista de variables (default FEATURES); nombres: subconjunto del catálogo (default todo)."""
    features = FEATURES if features is None else features
    cat = catalogo(con_fp3)
    if nombres is not None:
        cat = {n: cat[n] for n in nombres}
    entrenables = data.dropna(subset=["q_pos"])
    pruebas = entrenables[entrenables.year >= desde].meeting_key.drop_duplicates().tolist()
    preds = {n: [] for n in cat}
    for i, mk in enumerate(pruebas):
        fecha = entrenables[entrenables.meeting_key == mk].date.iloc[0]
        tr = entrenables[entrenables.date < fecha].sort_values(["meeting_key", "driver_number"])
        te = data[data.meeting_key == mk].assign(q_pos=lambda x: x.q_eval)
        grupos = tr.groupby("meeting_key", sort=False).size().loc[tr.meeting_key.unique()].values
        for nombre, fab in cat.items():
            m = fab().fit(tr[features], tr.q_pos.values, pesos(tr), grupos)
            p = te[["meeting_key", "driver_number", "q_pos", "year"]].copy()
            p["pred"] = m.predict(te[features])
            preds[nombre].append(p)
        print(f"  walk-forward {i + 1}/{len(pruebas)}", end="\r")
    print()
    preds = {n: pd.concat(v) for n, v in preds.items()}
    # Ensambles por promedio de ranking
    def ens(nombres):
        base = preds[nombres[0]][["meeting_key", "driver_number", "q_pos", "year"]].copy()
        rk = [preds[n].groupby("meeting_key").pred.rank().values for n in nombres]
        base["pred"] = np.mean(rk, axis=0)
        return base
    for nom_ens, miembros in ENSAMBLES.items():
        if all(n in preds for n in miembros):
            preds[nom_ens] = ens(miembros)
    tabla = []
    for n, p in preds.items():
        mt = metricas(p, "pred")
        mt26 = metricas(p[p.year >= 2026], "pred")
        tabla.append({"modelo": n, "top10_hits": mt.top10_hits.mean(), "top10_hits_2026": mt26.top10_hits.mean(),
                      "spearman": mt.spearman.mean(), "mae": mt.mae.mean(), "pole_acc": mt.pole_hit.mean(),
                      "top3_hits": mt.top3_hits.mean(), "n_gp": len(mt)})
    tabla = pd.DataFrame(tabla).sort_values(["top10_hits", "spearman"], ascending=False).reset_index(drop=True)
    return tabla, preds


ENSAMBLES = {
    "Ensamble árboles (RF+ET+GB+XGB+LGB)": ["Random Forest", "Extra Trees", "Gradient Boosting", "XGBoost", "LightGBM"],
    "Ensamble total (Ridge+árboles+rankers)": ["Ridge", "Random Forest", "Extra Trees", "Gradient Boosting",
                                               "XGBoost", "LightGBM", "LightGBM LambdaRank", "XGBoost Ranker"],
}


def ajustar_final(nombre, train, features=None, con_fp3=False):
    features = FEATURES if features is None else features
    train = train.sort_values(["meeting_key", "driver_number"])
    grupos = train.groupby("meeting_key", sort=False).size().loc[train.meeting_key.unique()].values
    miembros = ENSAMBLES.get(nombre, [nombre])
    cat = catalogo(con_fp3)
    modelos = [cat[n]().fit(train[features], train.q_pos.values, pesos(train), grupos) for n in miembros]

    def predecir(X):
        rk = [pd.Series(m.predict(X)).rank().values for m in modelos]
        return np.mean(rk, axis=0)
    return predecir, modelos


def importancias(modelos, features=None):
    features = FEATURES if features is None else features
    imp = []
    for m in modelos:
        est = m.est.steps[-1][1] if hasattr(m.est, "steps") else m.est
        if hasattr(est, "feature_importances_"):
            v = np.asarray(est.feature_importances_, dtype=float)
            imp.append(v / v.sum())
    if not imp:
        return pd.Series(dtype=float)
    return pd.Series(np.mean(imp, axis=0), index=features).sort_values(ascending=False)


def montecarlo(pred_rank, residuos, n=20000, seed=SEED):
    """Ruido empírico de los residuos walk-forward (ventana de ±2 posiciones predichas)."""
    rng = np.random.default_rng(seed)
    k = len(pred_rank)
    sims = np.zeros((n, k))
    for j, pr in enumerate(pred_rank):
        r = residuos[(residuos.pred_rank - pr).abs() <= 2].res.values
        if len(r) < 30:
            r = residuos.res.values
        sims[:, j] = pr + rng.choice(r, n) + rng.uniform(-0.5, 0.5, n)
    pos = sims.argsort(axis=1).argsort(axis=1) + 1
    return pd.DataFrame({
        "p_pole": (pos == 1).mean(0), "p_top3": (pos <= 3).mean(0),
        "p_q3": (pos <= 10).mean(0), "p_q2": (pos <= 16).mean(0),
        "pos_p10": np.percentile(pos, 10, axis=0), "pos_p90": np.percentile(pos, 90, axis=0),
        "pos_media": pos.mean(0),
    })


# ----------------------------------------------------------------------------------------
# 6. Main
# ----------------------------------------------------------------------------------------
def generar_reporte(resultado):
    gp = resultado["gp"]
    if gp["tema"] == "muertos":
        from reporte_mexico_html import generar_html
    else:
        from reporte_html import generar_html
    sufijo = resultado.get("sufijo", "")
    generar_html(resultado, BASE / f"reporte_qualy_{gp['slug']}{sufijo}_2026.html")


def main(meeting=OBJETIVO_MEETING, con_fp3=False, nombres_modelos=None):
    """con_fp3=True: versión del sábado con FP3; escribe archivos *_fp3 (no pisa el pronóstico FP1/FP2).
    nombres_modelos: lista de nombres del catálogo para el walk-forward (default: todos; más rápido con uno solo)."""
    gp = {**GPS[meeting], "meeting_key": meeting}
    feats = FEATURES_FP3 if con_fp3 else FEATURES
    sufijo = "_fp3" if con_fp3 else ""
    print(f"GP objetivo: {gp['nombre']} (meeting {meeting})" + ("  [con FP3]" if con_fp3 else ""))
    print("Construyendo dataset...")
    data, meetings = construir_dataset(con_fp3=con_fp3)
    data.to_csv(BASE / f"dataset_qualy{sufijo}.csv", index=False)
    obj = data[data.meeting_key == meeting].copy()
    print(f"Pilotos del GP objetivo: {len(obj)}")
    if con_fp3 and obj.fp3_best.notna().sum() < 10:
        print(f"AVISO: la FP3 del GP objetivo tiene datos de sólo {obj.fp3_best.notna().sum()} pilotos "
              "(¿falta bajarla? python3 descarga_datos.py <session_key_fp3>)")
    historia = data[(data.meeting_key != meeting) & (data.date < obj.date.min()) & data.q_eval.notna()]
    train = historia[historia.q_pos.notna()]
    print(f"Filas de entrenamiento: {len(train)}  | GPs: {train.meeting_key.nunique()}  | Features: {len(feats)}")

    print("Validación walk-forward 2024-2026...")
    tabla, preds = walk_forward(historia, features=feats, con_fp3=con_fp3, nombres=nombres_modelos)
    print(tabla.to_string(index=False))
    mejor = tabla.modelo.iloc[0]
    print("Mejor modelo:", mejor)

    p = preds[mejor].copy()
    p["pred_rank"] = p.groupby("meeting_key").pred.rank(method="first")
    p["res"] = p.q_pos - p.pred_rank
    p = p.dropna(subset=["res"])
    por_gp = metricas(preds[mejor], "pred").merge(
        meetings[["meeting_key", "circuit", "year"]], on="meeting_key")

    predecir, modelos = ajustar_final(mejor, train, feats, con_fp3)
    if not importancias(modelos, feats).empty:
        imp = importancias(modelos, feats)
    else:
        _, mods_imp = ajustar_final("Ensamble árboles (RF+ET+GB+XGB+LGB)", train, feats, con_fp3)
        imp = importancias(mods_imp, feats)

    obj = obj.reset_index(drop=True)
    obj["score"] = predecir(obj[feats])
    obj["pred_rank"] = obj.score.rank(method="first").astype(int)
    mc = montecarlo(obj.pred_rank.values, p[["pred_rank", "res"]])
    obj = pd.concat([obj, mc], axis=1).sort_values("pred_rank")

    circ = tabla_cota(gp["circuito_jolpica"])
    resultado = {"tabla": tabla, "mejor": mejor, "obj": obj, "imp": imp, "por_gp": por_gp, "cota": circ, "circ": circ,
                 "train": train, "residuos": p, "n_vars": len(feats), "gp": gp,
                 "fase": "FP3" if con_fp3 else "FP2", "con_fp3": con_fp3, "sufijo": sufijo, "features": list(feats),
                 "generado": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")}
    obj.to_csv(BASE / f"prediccion_qualy_{gp['slug']}{sufijo}_2026.csv", index=False)
    pd.to_pickle(resultado, BASE / f"resultado_qualy_{gp['slug']}{sufijo}.pkl")   # para regenerar el HTML sin reentrenar
    try:
        generar_reporte(resultado)
    except Exception as e:                    # el .pkl/.csv ya quedaron escritos
        print("AVISO: no se pudo generar el HTML:", repr(e))
        if not con_fp3:
            raise
    print("\nPREDICCIÓN TOP 10:")
    cols = ["pred_rank", "name_acronym", "team_name", "fp1_rank", "fp2_rank"] + (["fp3_rank"] if con_fp3 else []) + ["p_q3", "p_pole"]
    print(obj[cols].head(12).to_string(index=False))
    return resultado


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args[:1] == ["html"]:
        # python3 modelo_qualy_austin.py html mexico      -> desde resultado_qualy_mexico.pkl
        # python3 modelo_qualy_austin.py html mexico_fp3  -> desde resultado_qualy_mexico_fp3.pkl
        generar_reporte(pd.read_pickle(BASE / f"resultado_qualy_{args[1]}.pkl"))
    else:
        con_fp3 = "--fp3" in args
        if "--jobs" in args:
            N_JOBS = int(args[args.index("--jobs") + 1])
            args.pop(args.index("--jobs") + 1)
        modelos = None
        if "--modelos" in args:          # p. ej. --modelos "Random Forest"  (separados por coma)
            modelos = [m.strip() for m in args.pop(args.index("--modelos") + 1).split(",")]
        posicionales = [a for a in args if not a.startswith("--")]
        main(int(posicionales[0]) if posicionales else OBJETIVO_MEETING, con_fp3=con_fp3, nombres_modelos=modelos)
