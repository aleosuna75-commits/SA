"""Degradación de neumáticos (prácticas) y estrategia (carreras pasadas) para el modelo de carrera.

1) Degradación por piloto en las tandas largas de FP1/FP2/FP3 (OpenF1 laps_ + stints_):
   * vueltas del stint sin vuelta de salida, con tiempo consistente con la suma de sectores;
   * filtro de vueltas lentas: < mínimo del stint + 2.5 s; luego ajuste robusto (Theil-Sen) del tiempo
     contra la edad del neumático (tyre_age_at_start + vueltas en el stint), se descartan residuos
     > max(0.4 s, 3·MAD) y se reajusta;
   * se exigen >= 6 vueltas representativas que cubran >= 6 vueltas de edad;
   * corrección de combustible: el auto se aligera ~0.045 s/vuelta (rango 0.03-0.06), así que la
     degradación = pendiente + 0.045. La evolución de pista sesga todo el campo por igual (no afecta
     a las variables relativas).
   Variables por GP: deg_rel (piloto vs mediana del GP en el mismo compuesto, encogida hacia 0 según
   vueltas), deg_team_rel (equipo), deg_abs, deg_laps, deg_cov (fracción del campo con tanda larga).

2) Estrategia por circuito, sólo con carreras ANTERIORES al GP (OpenF1 race_stints_/race_pit_/race_laps_):
   * paradas típicas: mediana de paradas de los que terminan (carreras secas), mediana entre ediciones;
   * pérdida en pits: (vuelta de entrada + vuelta de salida) - 2 x mediana de vueltas limpias del piloto
     alrededor de la parada; se descartan paradas bajo SC/VSC (pérdida < 12 s) y valores > 45 s;
   * degradación observada en carrera (para validar la de prácticas).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import theilslopes

CACHE = Path(__file__).parent / "cache"
FUEL_S_VUELTA = 0.045
MIN_VUELTAS = 6
K_ENCOGE = 8.0          # vueltas "virtuales" en 0 para encoger pilotos con pocas vueltas
SECOS = {"SOFT", "MEDIUM", "HARD"}


def _cargar(nombre):
    f = CACHE / f"{nombre}.json"
    if not f.exists():
        return pd.DataFrame()
    x = json.loads(f.read_text())
    return pd.DataFrame(x) if isinstance(x, list) else pd.DataFrame()


def _asignar_stints(laps, stints):
    laps = laps.copy()
    laps["compound"] = None
    laps["stint"] = np.nan
    laps["tyre_age"] = np.nan
    if stints.empty:
        return laps
    for _, s in stints.iterrows():
        if pd.isna(s.get("lap_start")) or pd.isna(s.get("lap_end")):
            continue
        m = (laps.driver_number == s.driver_number) & laps.lap_number.between(s.lap_start, s.lap_end)
        laps.loc[m, "compound"] = s.get("compound")
        laps.loc[m, "stint"] = s.stint_number
        edad0 = s.get("tyre_age_at_start")
        edad0 = 0 if pd.isna(edad0) else edad0
        laps.loc[m, "tyre_age"] = edad0 + laps.loc[m, "lap_number"] - s.lap_start
    return laps


def pendiente_stint(t, edad, umbral=2.5, min_v=MIN_VUELTAS):
    """Pendiente robusta (s/vuelta) del tiempo contra la edad del neumático; None si no alcanza."""
    t, edad = np.asarray(t, float), np.asarray(edad, float)
    ok = t < np.nanmin(t) + umbral
    t, edad = t[ok], edad[ok]
    if len(t) < min_v or np.ptp(edad) < min_v - 1:
        return None
    b, a, _, _ = theilslopes(t, edad)
    r = t - (a + b * edad)
    mad = np.median(np.abs(r - np.median(r))) * 1.4826
    ok = np.abs(r) <= max(0.4, 3 * mad)
    if ok.sum() < min_v:
        return None
    b, a, _, _ = theilslopes(t[ok], edad[ok])
    return {"slope": float(b), "n": int(ok.sum()), "t_med": float(np.median(t[ok])), "edad_med": float(np.median(edad[ok]))}


def stints_practica(sk, sesion=""):
    """Una fila por stint largo de una práctica: driver_number, compound, slope, n, t_med."""
    laps, stints = _cargar(f"laps_{sk}"), _cargar(f"stints_{sk}")
    if laps.empty or stints.empty:
        return pd.DataFrame()
    laps = _asignar_stints(laps, stints)
    v = laps[laps.lap_duration.notna() & (laps.is_pit_out_lap != True) & laps.stint.notna()].copy()
    suma = v[["duration_sector_1", "duration_sector_2", "duration_sector_3"]].sum(axis=1, min_count=3)
    v = v[~((suma - v.lap_duration).abs() > 1.0)]
    if v.empty:
        return pd.DataFrame()
    mejor = v.groupby("driver_number").lap_duration.min().sort_values()
    ref = mejor.iloc[min(2, len(mejor) - 1)]
    v = v[v.lap_duration < ref * 1.12]
    filas = []
    for (dn, st), g in v.groupby(["driver_number", "stint"]):
        comp = g.compound.iloc[0]
        if comp not in SECOS:
            continue
        r = pendiente_stint(g.lap_duration.values, g.tyre_age.values)
        if r:
            filas.append({"driver_number": dn, "stint": st, "compound": comp, "sesion": sesion, **r})
    return pd.DataFrame(filas)


def deg_gp(sesiones):
    """sesiones: lista de (session_key, nombre). Devuelve variables por driver_number (relativas al GP)."""
    st = [stints_practica(int(sk), nom) for sk, nom in sesiones if pd.notna(sk)]
    st = [x for x in st if not x.empty]
    if not st:
        return pd.DataFrame(columns=["driver_number", "deg_rel", "deg_abs", "deg_laps", "deg_n_stints"])
    st = pd.concat(st, ignore_index=True)
    st["deg"] = st.slope + FUEL_S_VUELTA
    st["deg"] = st.deg.clip(-0.3, 0.6)
    # referencia por compuesto (si hay >=3 stints de ese compuesto; si no, mediana global del GP)
    med_glob = st.deg.median()
    ref = st.groupby("compound").deg.agg(["median", "size"])
    st["ref"] = st.compound.map(lambda c: ref.at[c, "median"] if ref.at[c, "size"] >= 3 else med_glob)
    st["rel"] = st.deg - st.ref
    w = st.n.astype(float)
    agg = st.assign(w=w, wr=w * st.rel, wd=w * st.deg).groupby("driver_number").agg(
        sw=("w", "sum"), swr=("wr", "sum"), swd=("wd", "sum"), deg_n_stints=("n", "size"),
        comp=("compound", lambda s: "/".join(sorted(set(s)))))
    out = pd.DataFrame({
        "deg_rel": agg.swr / (agg.sw + K_ENCOGE),           # encogida hacia 0
        "deg_abs": agg.swd / agg.sw,
        "deg_laps": agg.sw, "deg_n_stints": agg.deg_n_stints, "deg_comp": agg.comp,
    })
    out["deg_gp_med"] = med_glob
    return out.reset_index()


# ----------------------------------------------------------------------------------------
# Estrategia: carreras pasadas
# ----------------------------------------------------------------------------------------
def resumen_carrera(sk):
    """Paradas, pérdida en pits y degradación observada en una carrera ya corrida (None si no hay datos)."""
    st, pit, laps = _cargar(f"race_stints_{sk}"), _cargar(f"race_pit_{sk}"), _cargar(f"race_laps_{sk}")
    if st.empty or laps.empty:
        return None
    comps = set(st.compound.dropna())
    mojada = bool(comps & {"INTERMEDIATE", "WET"})
    n_vueltas = int(laps.lap_number.max())
    ult = laps.groupby("driver_number").lap_number.max()
    terminan = ult[ult >= n_vueltas - 3].index           # terminan (o a 1-3 vueltas)
    paradas = st[st.driver_number.isin(terminan)].groupby("driver_number").stint_number.max() - 1
    # pérdida en pits: vuelta de entrada + salida - 2 x vuelta limpia mediana
    perd = []
    lp = laps.set_index(["driver_number", "lap_number"]).lap_duration
    if not pit.empty:
        for _, p in pit.iterrows():
            dn, k = p.driver_number, p.lap_number
            if pd.isna(k) or (dn, k) not in lp.index or (dn, k + 1) not in lp.index:
                continue
            tin, tout = lp.get((dn, k)), lp.get((dn, k + 1))
            cerca = [lp.get((dn, j)) for j in range(int(k) - 6, int(k) + 8) if j not in (k, k + 1) and (dn, j) in lp.index]
            cerca = [x for x in cerca if pd.notna(x)]
            if pd.isna(tin) or pd.isna(tout) or len(cerca) < 4:
                continue
            base = np.median(cerca)
            perd.append(tin + tout - 2 * base)
    perd = np.array([x for x in perd if 12 < x < 45])
    # degradación observada en carrera (stints secos >= 8 vueltas); combustible de carrera ~0.06 s/vuelta
    lap_st = _asignar_stints(laps, st)
    v = lap_st[lap_st.lap_duration.notna() & (lap_st.is_pit_out_lap != True) & lap_st.stint.notna() & (lap_st.lap_number > 1)]
    degs = []
    for (dn, s), g in v.groupby(["driver_number", "stint"]):
        if g.compound.iloc[0] not in SECOS:
            continue
        r = pendiente_stint(g.lap_duration.values, g.tyre_age.values, umbral=2.0, min_v=8)
        if r:
            degs.append({"driver_number": dn, "stint": s, "compound": g.compound.iloc[0], "deg": r["slope"] + 0.06, "n": r["n"]})
    degs = pd.DataFrame(degs)
    return {
        "session_key": sk, "mojada": mojada, "vueltas": n_vueltas,
        "paradas_med": float(paradas.median()) if len(paradas) else np.nan,
        "paradas_media": float(paradas.mean()) if len(paradas) else np.nan,
        "perdida_pit": float(np.median(perd)) if len(perd) >= 3 else np.nan,
        "lane_med": float(pit.pit_duration.median()) if not pit.empty and "pit_duration" in pit else np.nan,
        "deg_carrera": degs,
    }


def tabla_estrategia():
    """Una fila por carrera ya corrida (OpenF1): meeting_key, circuit_key, fecha, paradas, pérdida en pits, deg."""
    filas, degs = [], []
    for a in (2023, 2024, 2025, 2026):
        f = CACHE / f"sessions_{a}.json"
        if not f.exists():
            continue
        for s in json.loads(f.read_text()):
            if s["session_name"] != "Race":
                continue
            r = resumen_carrera(s["session_key"])
            if r is None:
                continue
            d = r.pop("deg_carrera")
            filas.append({**r, "meeting_key": s["meeting_key"], "circuit_key": s["circuit_key"],
                          "fecha": pd.Timestamp(s["date_start"]).tz_convert(None)})
            if len(d):
                d["meeting_key"] = s["meeting_key"]
                degs.append(d)
    t = pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)
    return t, (pd.concat(degs, ignore_index=True) if degs else pd.DataFrame())


def estrategia_circuito(tabla, circuit_key, antes_de, vueltas=None):
    """Paradas típicas y pérdida en pits del circuito con carreras anteriores a `antes_de` (sin fuga).
    Si el circuito no tiene historia seca, usa la mediana de todas las carreras previas."""
    prev = tabla[(tabla.fecha < antes_de) & ~tabla.mojada]
    c = prev[prev.circuit_key == circuit_key]
    glob_par = prev.paradas_med.median() if len(prev) else 1.0
    glob_pp = prev.perdida_pit.median() if len(prev) else 22.0
    par = c.paradas_med.median() if c.paradas_med.notna().any() else glob_par
    pp = c.perdida_pit.median() if c.perdida_pit.notna().any() else glob_pp
    par_media = c.paradas_media.mean() if c.paradas_media.notna().any() else (prev.paradas_media.median() if len(prev) else 1.2)
    return {"paradas": float(par), "paradas_media": float(par_media), "perdida_pit": float(pp),
            "n_ediciones": int(len(c)), "vueltas": vueltas if vueltas else (int(c.vueltas.max()) if len(c) else np.nan)}


def deg_carrera_piloto(tabla, degs):
    """Degradación relativa observada en cada carrera seca ya corrida, por piloto (s/vuelta vs la mediana del
    compuesto en esa carrera). Columnas: meeting_key, driver_number, race_rel, fecha."""
    if degs is None or degs.empty:
        return pd.DataFrame(columns=["meeting_key", "driver_number", "race_rel", "fecha"])
    seco = tabla[~tabla.mojada][["meeting_key", "fecha"]]
    d = degs[degs.meeting_key.isin(seco.meeting_key)].copy()
    d["rel"] = d.deg - d.groupby(["meeting_key", "compound"]).deg.transform("median")
    d["wr"] = d.rel * d.n
    r = d.groupby(["meeting_key", "driver_number"]).agg(wr=("wr", "sum"), w=("n", "sum")).reset_index()
    r["race_rel"] = (r.wr / r.w).clip(-0.3, 0.3)
    return r[["meeting_key", "driver_number", "race_rel"]].merge(seco, on="meeting_key")
