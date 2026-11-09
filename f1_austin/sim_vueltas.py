"""Simulador de carrera VUELTA A VUELTA (Monte Carlo) calibrado con las carreras de OpenF1 2023-2026.

Qué simula, vuelta por vuelta y para cada uno de N carreras:
  * Ritmo base por piloto (s/vuelta en aire limpio): regresión (Ridge) de las variables pre-carrera (gap de qualy,
    ritmo de tanda larga FP1-3, forma de piloto y equipo) contra el ritmo REAL de carreras pasadas (efecto fijo del
    piloto en un modelo de vueltas limpias), + ruido por carrera con la dispersión de los residuos.
  * Neumáticos: offset por compuesto + degradación lineal por vuelta de edad, combustible/evolución por vuelta
    (ajustados por carrera con vueltas limpias: sin vuelta 1, sin vueltas de entrada/salida a pits, sin SC/VSC ni
    relanzadas), promediados para el circuito (ediciones previas) con contracción hacia el promedio global reciente.
  * Pits: pérdida del circuito (vuelta de entrada + salida vs vueltas limpias), regla de 2 compuestos, plan elegido
    por optimización del tiempo esperado (1 o 2 paradas, compuestos y vueltas) + ruido calibrado (softmax de plan,
    desviación de la vuelta de parada); UNDERCUT (el de atrás a < X s adelanta su parada), reacción del de adelante
    (cubrir), OVERCUT (quedarse fuera) y paradas oportunistas con SC/VSC. Los duelos quedan registrados con resultado.
  * Rebases en pista: logística por vuelta para el auto de atrás a < 2 s (diferencia de ritmo esperado, intervalo,
    < 1 s = DRS/overtake mode, facilidad de rebase del circuito) ajustada con los cambios de posición reales entre
    vueltas (sin pits, sin SC). Si no rebasa queda atrapado a una distancia mínima y pierde por aire sucio.
  * Vuelta 1: cambios de posición y distancias con la distribución histórica por puesto de salida.
  * Safety car / VSC: tasa por vuelta (vuelta 1 aparte) del circuito contraída hacia la global; el SC junta el pelotón
    y ambos abaratan la parada.
  * Abandonos: p_dnf del simulador actual (logística de fiabilidad), vuelta del abandono con la distribución histórica.

Dos modos: "libre" (ritmo sólo desde variables pre-carrera) y "anclado" (ritmo efectivo por piloto ajustado para que la
posición media coincida con la del simulador oficial sim_carrera.py; lo nuevo son estrategias, rebases, duelos, SC, trazas).
Validación walk-forward 2024-2026 (cada GP calibrado sólo con carreras anteriores). Uso (desde f1_austin/):
  python3 sim_vueltas.py preparar                 # baja race_control faltante y procesa 88 carreras -> cache/vueltas_hist.pkl
  python3 sim_vueltas.py validar [--sims 2000]    # walk-forward libre + anclado + duelos -> validacion_vueltas.json (~40 min)
  python3 sim_vueltas.py mexico [--sims 6000] [--carrera]
        # -> web_mexico/datos_vueltas.json; con --carrera también la forma de datos_carrera.json en el scratchpad
        #    (sólo si validacion_vueltas.json dice mejor_o_igual_que_actual)
"""
import argparse
import json
import pickle
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.linear_model import LogisticRegression, Ridge

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent
CACHE = BASE / "cache"
HIST_PKL = CACHE / "vueltas_hist.pkl"
COMP = ["SOFT", "MEDIUM", "HARD"]
CI = {c: i for i, c in enumerate(COMP)}
LETRA = {"SOFT": "S", "MEDIUM": "M", "HARD": "H"}
G_MAX = 2.0          # intervalo máximo (s) para intentar rebase en una vuelta
VERSION_HIST = 5
# predicciones walk-forward del simulador actual (sim_carrera.py), para comparar por GP sin recalcularlas
WF_ACTUAL = CACHE / "wf_sim_carrera_actual.csv"
# GP del pronóstico en curso (textos): México por defecto; gp_pipeline.py lo cambia por GP
CTX = {"meeting": 1298, "lugar": "México"}


# ========================================================================================
# 1) Procesado de las carreras históricas
# ========================================================================================
def _json(nombre):
    f = CACHE / f"{nombre}.json"
    if not f.exists():
        return []
    x = json.loads(f.read_text())
    return x if isinstance(x, list) else []


def tabla_carreras():
    filas = []
    for a in (2023, 2024, 2025, 2026):
        for s in _json(f"sessions_{a}"):
            if s["session_name"] != "Race":
                continue
            sk = s["session_key"]
            filas.append({"session_key": sk, "meeting_key": s["meeting_key"], "circuit_key": s["circuit_key"],
                          "circuito": s["circuit_short_name"], "year": a,
                          "fecha": pd.Timestamp(s["date_start"]).tz_convert(None),
                          "tiene_vueltas": (CACHE / f"race_laps_{sk}.json").exists()})
    return pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)


def neutralizadas_rc(rc, n_vueltas):
    """Vueltas bajo SC / VSC / bandera roja según race_control. Devuelve (set de vueltas neutralizadas, eventos)."""
    neut, eventos = set(), []
    if not rc:
        return neut, eventos
    R = pd.DataFrame(rc)
    if "message" not in R:
        return neut, eventos
    R = R.sort_values("date")
    abierto = None
    for _, r in R.iterrows():
        msg = str(r.get("message") or "").upper()
        lap = r.get("lap_number")
        lap = int(lap) if pd.notna(lap) else None
        if lap is None:
            continue
        if "VIRTUAL SAFETY CAR DEPLOYED" in msg:
            abierto = ("VSC", lap)
        elif "SAFETY CAR DEPLOYED" in msg:
            abierto = ("SC", lap)
        elif ("VIRTUAL SAFETY CAR ENDING" in msg or "SAFETY CAR IN THIS LAP" in msg) and abierto:
            tipo, ini = abierto
            neut.update(range(ini, lap + 1))
            eventos.append({"tipo": tipo, "ini": ini, "fin": lap})
            abierto = None
        elif r.get("flag") == "RED" or msg.startswith("RED FLAG"):
            if abierto:
                tipo, ini = abierto
                neut.update(range(ini, lap + 1))
                eventos.append({"tipo": tipo, "ini": ini, "fin": lap})
                abierto = None
            neut.update({lap, lap + 1})
            eventos.append({"tipo": "RED", "ini": lap, "fin": lap + 1})
    if abierto:
        tipo, ini = abierto
        neut.update(range(ini, min(ini + 4, n_vueltas) + 1))
        eventos.append({"tipo": tipo, "ini": ini, "fin": min(ini + 4, n_vueltas)})
    return neut, eventos


def procesar_carrera(sk):
    """Matrices por piloto x vuelta y tablas de eventos de una carrera ya corrida (None si no sirve)."""
    L = pd.DataFrame(_json(f"race_laps_{sk}"))
    S = pd.DataFrame(_json(f"race_stints_{sk}"))
    P = pd.DataFrame(_json(f"race_pit_{sk}"))
    rc = _json(f"race_rc_{sk}")
    if L.empty or S.empty:
        return None
    L["ds"] = pd.to_datetime(L.date_start, format="ISO8601", errors="coerce")
    t0 = L[L.lap_number == 1].ds.min()
    if pd.isna(t0):
        t0 = L.ds.min()
    L["t_ini"] = (L.ds - t0).dt.total_seconds()
    L["t_fin"] = L.t_ini + L.lap_duration
    drivers = sorted(L.driver_number.unique())
    nv = int(L.lap_number.max())
    idx = {d: i for i, d in enumerate(drivers)}
    nd = len(drivers)
    Tfin = np.full((nd, nv + 2), np.nan)
    Tini = np.full((nd, nv + 2), np.nan)
    DUR = np.full((nd, nv + 2), np.nan)
    OUT = np.zeros((nd, nv + 2), bool)
    for r in L.itertuples():
        i, k = idx[r.driver_number], int(r.lap_number)
        Tfin[i, k] = r.t_fin
        Tini[i, k] = r.t_ini
        DUR[i, k] = r.lap_duration
        OUT[i, k] = bool(r.is_pit_out_lap) if pd.notna(r.is_pit_out_lap) else False
    # completar fin de vuelta con el inicio de la siguiente
    sig_ini = np.c_[Tini[:, 1:], np.full(nd, np.nan)]          # inicio de la vuelta k+1 = fin de la vuelta k
    T = np.where(np.isnan(Tfin), sig_ini, Tfin)
    # vueltas completadas: hasta la última con algún dato
    ult = np.array([np.max(np.where(~np.isnan(T[i]))[0]) if (~np.isnan(T[i])).any() else 0 for i in range(nd)])
    for i in range(nd):                     # huecos internos: interpolar
        k = np.arange(nv + 2)
        ok = ~np.isnan(T[i]) & (k >= 1)
        if ok.sum() >= 2:
            hueco = (~ok) & (k >= 1) & (k <= ult[i])
            T[i, hueco] = np.interp(k[hueco], k[ok], T[i, ok])
        T[i, ult[i] + 1:] = np.nan
    # pits (vuelta de entrada)
    IN = np.zeros((nd, nv + 2), bool)
    paradas = []
    if not P.empty:
        for r in P.itertuples():
            if r.driver_number in idx and pd.notna(r.lap_number) and 1 <= r.lap_number <= nv:
                IN[idx[r.driver_number], int(r.lap_number)] = True
                paradas.append({"driver_number": r.driver_number, "lap": int(r.lap_number),
                                "lane": getattr(r, "lane_duration", np.nan) if pd.notna(getattr(r, "lane_duration", np.nan))
                                else getattr(r, "pit_duration", np.nan)})
    # neumático por vuelta
    CMP = np.full((nd, nv + 2), -1, int)
    AGE = np.full((nd, nv + 2), np.nan)
    STN = np.zeros((nd, nv + 2), int)
    mojada = bool(set(S.compound.dropna()) & {"INTERMEDIATE", "WET"})
    stints = []
    for r in S.sort_values(["driver_number", "stint_number"]).itertuples():
        if r.driver_number not in idx or pd.isna(r.lap_start) or pd.isna(r.lap_end):
            continue
        i = idx[r.driver_number]
        a, b = int(r.lap_start), int(min(r.lap_end, nv))
        c = CI.get(r.compound, -1)
        e0 = 0 if pd.isna(r.tyre_age_at_start) else int(r.tyre_age_at_start)
        CMP[i, a:b + 1] = c
        AGE[i, a:b + 1] = e0 + np.arange(b - a + 1)
        STN[i, a:b + 1] = int(r.stint_number)
        stints.append({"driver_number": r.driver_number, "stint": int(r.stint_number), "compound": r.compound,
                       "lap_start": a, "lap_end": b, "age0": e0})
    neut, eventos = neutralizadas_rc(rc, nv)
    # neutralización por tiempos: mediana del pelotón > 112% de la mediana de vueltas "normales"
    med_k = np.nanmedian(DUR[:, 1:nv + 1], axis=0)
    ref = np.nanmedian(med_k[1:]) if nv > 2 else np.nanmedian(med_k)
    lenta = {k + 1 for k, m in enumerate(med_k) if np.isfinite(m) and m > 1.12 * ref and k + 1 > 1}
    neut_t = set(neut) | lenta
    return {"sk": sk, "drivers": drivers, "nv": nv, "T": T, "DUR": DUR, "OUT": OUT, "IN": IN, "CMP": CMP, "AGE": AGE,
            "STN": STN, "neut": sorted(neut_t), "neut_rc": sorted(neut), "eventos": eventos, "mojada": mojada,
            "paradas": paradas, "stints": stints, "ult": ult, "ref_lap": float(ref)}


def orden_vuelta(T, k):
    """Índices de pilotos que completaron la vuelta k, ordenados por tiempo acumulado."""
    t = T[:, k]
    ok = np.where(np.isfinite(t))[0]
    return ok[np.argsort(t[ok])]


def ajustar_vueltas(c):
    """Modelo de vueltas limpias de una carrera: t = a_piloto + off_compuesto + deg_compuesto*edad + fuel*vuelta
    + aire sucio (<1 s / 1-2 s del de adelante). Devuelve dict de parámetros o None."""
    nd, nv = len(c["drivers"]), c["nv"]
    T, DUR, CMP, AGE = c["T"], c["DUR"], c["CMP"], c["AGE"]
    neut = set(c["neut"])
    gap_ad = np.full((nd, nv + 2), np.nan)       # intervalo al de adelante al INICIO de la vuelta k
    for k in range(1, nv):
        o = orden_vuelta(T, k)
        if len(o) > 1:
            gap_ad[o[1:], k + 1] = T[o[1:], k] - T[o[:-1], k]
    c["gap_ad"] = gap_ad
    filas = []
    for i in range(nd):
        for k in range(2, c["ult"][i] + 1):
            if c["OUT"][i, k] or c["IN"][i, k] or k in neut or (k - 1) in neut or CMP[i, k] < 0:
                continue
            if k == c["ult"][i] and c["ult"][i] < nv - 3:     # vuelta del abandono
                continue
            d = DUR[i, k]
            if not np.isfinite(d) or d > 1.07 * c["ref_lap"] or d < 0.9 * c["ref_lap"]:
                continue
            g = gap_ad[i, k]
            filas.append((i, k, CMP[i, k], AGE[i, k], d, float(np.isfinite(g) and g < 1.0),
                          float(np.isfinite(g) and 1.0 <= g < 2.0)))
    if len(filas) < 200:
        return None
    F = np.array(filas, float)
    di = F[:, 0].astype(int)
    comp = F[:, 2].astype(int)
    usados = sorted(set(comp))
    if CI["MEDIUM"] in usados:
        base_c = CI["MEDIUM"]
    else:
        base_c = max(usados, key=lambda x: (comp == x).sum())
    pil = sorted(set(di))
    pmap = {p: j for j, p in enumerate(pil)}
    ncol = len(pil) + 3 + 3 + 3
    X = np.zeros((len(F), ncol))
    X[np.arange(len(F)), [pmap[p] for p in di]] = 1.0
    o = len(pil)
    for cc in range(3):
        if cc != base_c:
            X[:, o + cc] = (comp == cc)
        X[:, o + 3 + cc] = (comp == cc) * F[:, 3]
    X[:, o + 6] = F[:, 1]
    X[:, o + 7] = F[:, 5]
    X[:, o + 8] = F[:, 6]
    y = F[:, 4]
    keep = np.ones(len(F), bool)
    for _ in range(3):
        cols = X[keep].any(axis=0)
        b = np.zeros(ncol)
        b[cols] = np.linalg.lstsq(X[keep][:, cols], y[keep], rcond=None)[0]
        r = y - X @ b
        mad = np.median(np.abs(r[keep] - np.median(r[keep]))) * 1.4826
        keep = np.abs(r) < max(3 * mad, 0.6)
    n_por_p = np.bincount([pmap[p] for p in di[keep]], minlength=len(pil))
    alpha = {c["drivers"][p]: (b[pmap[p]] if n_por_p[pmap[p]] >= 5 else np.nan) for p in pil}
    n_c = [int(((comp == cc) & keep).sum()) for cc in range(3)]
    off = [b[o + cc] if (cc != base_c and n_c[cc] >= 20) else (0.0 if cc == base_c else np.nan) for cc in range(3)]
    if base_c != CI["MEDIUM"]:               # todo relativo a MEDIUM; si no hubo medio, offsets no comparables
        off = [np.nan, np.nan, np.nan]
    deg = [b[o + 3 + cc] if n_c[cc] >= 20 else np.nan for cc in range(3)]
    return {"alpha": alpha, "off": off, "deg": deg, "fuel": b[o + 6], "sucio1": b[o + 7], "sucio2": b[o + 8],
            "sd": float(mad), "n_c": n_c, "base_c": base_c, "n": int(keep.sum())}


def eventos_pista(c, fit):
    """Pares consecutivos (atacante detrás a < G_MAX s) en vueltas de bandera verde sin pits: sale rebase o no.
    También cuenta rebases en pista por piloto (cualquier par que cambia de orden entre vueltas)."""
    T, CMP, AGE, IN, OUT = c["T"], c["CMP"], c["AGE"], c["IN"], c["OUT"]
    neut = set(c["neut"])
    nd, nv = len(c["drivers"]), c["nv"]
    al = np.array([fit["alpha"].get(d, np.nan) for d in c["drivers"]])
    off = np.nan_to_num(np.array(fit["off"], float))
    deg = np.nan_to_num(np.array(fit["deg"], float), nan=0.05)

    def pred(i, k):
        cc = CMP[i, k]
        if cc < 0 or not np.isfinite(al[i]):
            return np.nan
        return al[i] + off[cc] + deg[cc] * AGE[i, k]
    pares, gan, per = [], np.zeros(nd, int), np.zeros(nd, int)
    for k in range(2, nv + 1):
        if k in neut:
            continue
        relanza = (k - 1) in neut           # vuelta de relanzamiento tras SC/VSC (se guarda aparte)
        o = orden_vuelta(T, k - 1)
        o = np.array([i for i in o if np.isfinite(T[i, k])])
        if len(o) < 2:
            continue
        lim = IN[:, k] | OUT[:, k] | IN[:, k - 1]
        for p in range(1, len(o)):
            a, b_ = o[p], o[p - 1]
            if lim[a] or lim[b_]:
                continue
            g = T[a, k - 1] - T[b_, k - 1]
            if g >= G_MAX:
                continue
            d = pred(b_, k) - pred(a, k)
            pares.append((k, a, b_, g, d, int(T[a, k] < T[b_, k]), AGE[a, k] - AGE[b_, k], CMP[a, k], CMP[b_, k], p,
                          int(relanza)))
        # conteo de rebases por piloto (cualquier par)
        pos0 = {i: j for j, i in enumerate(o)}
        o1 = sorted(o, key=lambda i: T[i, k])
        pos1 = {i: j for j, i in enumerate(o1)}
        libres = [i for i in o if not lim[i]]
        for x in libres:
            for y in libres:
                if pos0[x] > pos0[y] and pos1[x] < pos1[y]:
                    gan[x] += 1
                    per[y] += 1
    P = pd.DataFrame(pares, columns=["lap", "a", "b", "gap", "d", "rebase", "dedad", "ca", "cb", "pos_def", "relanza"])
    return P, gan, per


def perdidas_pit(c):
    """Pérdida (s) por parada: vuelta de entrada + salida - 2 x vuelta limpia mediana del piloto (bandera verde),
    y bajo SC/VSC contra la mediana del pelotón que no paró en esas vueltas."""
    DUR, IN, OUT = c["DUR"], c["IN"], c["OUT"]
    neut = set(c["neut"])
    nd, nv = len(c["drivers"]), c["nv"]
    verde, neutral = [], []
    for i in range(nd):
        for k in np.where(IN[i])[0]:
            if k + 1 > nv or not (np.isfinite(DUR[i, k]) and np.isfinite(DUR[i, k + 1])):
                continue
            tot = DUR[i, k] + DUR[i, k + 1]
            if k in neut or (k + 1) in neut:
                otros = [j for j in range(nd) if not (IN[j, k] or IN[j, k + 1] or OUT[j, k] or OUT[j, k + 1])]
                if len(otros) >= 5:
                    ref = np.nanmedian(DUR[otros, k]) + np.nanmedian(DUR[otros, k + 1])
                    neutral.append(tot - ref)
                continue
            cerca = [DUR[i, j] for j in range(max(2, k - 6), min(nv, k + 8) + 1)
                     if j not in (k, k + 1) and not IN[i, j] and not OUT[i, j] and j not in neut and np.isfinite(DUR[i, j])]
            if len(cerca) >= 4:
                verde.append(tot - 2 * np.median(cerca))
    verde = [x for x in verde if 12 < x < 45]
    neutral = [x for x in neutral if -5 < x < 45]
    return verde, neutral


def estrategias_reales(c):
    """Plan real por piloto: compuestos por stint, vueltas de parada, terminó."""
    st = pd.DataFrame(c["stints"])
    out = {}
    if st.empty:
        return out
    for dn, g in st.groupby("driver_number"):
        g = g.sort_values("stint")
        comps = [LETRA.get(x, "?") for x in g.compound]
        # fusionar stints consecutivos del mismo compuesto sin parada real (cortes de datos)
        i = c["drivers"].index(dn)
        pits = sorted(int(k) for k in np.where(c["IN"][i])[0])
        out[dn] = {"plan": "-".join(comps), "paradas": len(pits), "vueltas_parada": pits,
                   "termina": bool(c["ult"][i] >= c["nv"] - 3)}
    return out


def descargar_race_control():
    """Mensajes de dirección de carrera (SC/VSC/bandera roja) de cada carrera con vueltas en cache (OpenF1, pausa 0.7 s)."""
    from descarga_datos import OPENF1, get
    for f in sorted(CACHE.glob("race_laps_*.json")):
        sk = f.stem.split("_")[-1]
        if not (CACHE / f"race_rc_{sk}.json").exists():
            get(f"{OPENF1}/race_control?session_key={sk}", f"race_rc_{sk}", pausa=0.7)


def preparar(forzar=False):
    if forzar:
        descargar_race_control()
    if HIST_PKL.exists() and not forzar:
        h = pickle.loads(HIST_PKL.read_bytes())
        if h.get("version") == VERSION_HIST:
            return h
    car = tabla_carreras()
    res = {}
    t0 = time.time()
    for r in car[car.tiene_vueltas].itertuples():
        c = _procesar_completa(r.session_key)
        if c is None:
            continue
        res[r.session_key] = c
        fit = c["fit"]
        print(f"  carrera {r.session_key} ({r.circuito} {r.year}) n={fit['n'] if fit else 0} "
              f"({time.time() - t0:.0f} s)", flush=True)
    h = {"version": VERSION_HIST, "carreras": car, "datos": res}
    HIST_PKL.write_bytes(pickle.dumps(h))
    return h


def actualizar_hist():
    """Agrega al histórico (cache/vueltas_hist.pkl) las carreras con vueltas y race_control en cache que falten
    (p. ej. el GP recién corrido), sin reprocesar las demás. No hay fuga: calibrar() sólo usa carreras anteriores al
    fin de semana objetivo. Devuelve (h, session_keys agregadas)."""
    h = preparar()
    car = tabla_carreras()
    nuevas = []
    for r in car[car.tiene_vueltas].itertuples():
        if r.session_key in h["datos"] or not (CACHE / f"race_rc_{r.session_key}.json").exists():
            continue
        c = _procesar_completa(r.session_key)
        if c is not None:
            h["datos"][r.session_key] = c
            nuevas.append(r.session_key)
    if nuevas or len(car) != len(h["carreras"]):
        h["carreras"] = car
        HIST_PKL.write_bytes(pickle.dumps(h))
    return h, nuevas


def _procesar_completa(sk):
    c = procesar_carrera(sk)
    if c is None:
        return None
    if True:
        fit = ajustar_vueltas(c)
        c["fit"] = fit
        if fit is not None:
            P, gan, per = eventos_pista(c, fit)
            c["pares"] = P
            c["reb_gan"], c["reb_per"] = gan, per
        else:
            c["pares"] = pd.DataFrame()
            c["reb_gan"] = c["reb_per"] = np.zeros(len(c["drivers"]), int)
        c["pit_verde"], c["pit_neutral"] = perdidas_pit(c)
        c["estrategia"] = estrategias_reales(c)
        # orden y distancias al final de la vuelta 1
        o1 = orden_vuelta(c["T"], 1)
        c["orden1"] = [c["drivers"][i] for i in o1]
        c["gaps1"] = np.diff(c["T"][o1, 1]).tolist()
    return c


# ========================================================================================
# 2) Estrategia: costo esperado de cada plan (1 o 2 paradas, regla de 2 compuestos)
# ========================================================================================
from itertools import product

PLANES = [s for n in (2, 3) for s in product(range(3), repeat=n) if len(set(s)) >= 2]
PLAN_TXT = ["-".join("SMH"[c] for c in p) for p in PLANES]
PLAN_PARADAS = np.array([len(p) - 1 for p in PLANES])
MIN_STINT = 6


def costo_stint(off, deg, n):
    """Tiempo extra (s) de un stint de n vueltas con neumático nuevo: n*offset + deg*n(n-1)/2."""
    return n * off + deg * n * (n - 1) / 2.0


def costos_planes(off, deg, L, pit, maxlen):
    """off, deg, maxlen: arrays por compuesto (S, M, H). Devuelve (costo por plan, vueltas de parada por plan [2])."""
    off = np.asarray(off, float)
    deg = np.asarray(deg, float)
    costo = np.full(len(PLANES), np.inf)
    vueltas = np.zeros((len(PLANES), 2), int)
    n = np.arange(L + 1)
    for j, p in enumerate(PLANES):
        if len(p) == 2:
            n1 = np.arange(MIN_STINT, L - MIN_STINT + 1)
            n2 = L - n1
            c = costo_stint(off[p[0]], deg[p[0]], n1) + costo_stint(off[p[1]], deg[p[1]], n2) + pit
            c = np.where((n1 <= maxlen[p[0]]) & (n2 <= maxlen[p[1]]), c, np.inf)
            b = int(np.argmin(c))
            costo[j], vueltas[j] = c[b], (n1[b], 0)
        else:
            n1, n2 = np.meshgrid(np.arange(MIN_STINT, L), np.arange(MIN_STINT, L), indexing="ij")
            n3 = L - n1 - n2
            ok = (n3 >= MIN_STINT) & (n1 <= maxlen[p[0]]) & (n2 <= maxlen[p[1]]) & (n3 <= maxlen[p[2]])
            c = (costo_stint(off[p[0]], deg[p[0]], n1) + costo_stint(off[p[1]], deg[p[1]], n2)
                 + costo_stint(off[p[2]], deg[p[2]], n3) + 2 * pit)
            c = np.where(ok, c, np.inf)
            b = np.unravel_index(int(np.argmin(c)), c.shape)
            costo[j], vueltas[j] = c[b], (n1[b], n1[b] + n2[b])
    return costo, vueltas


# ========================================================================================
# 3) Calibración con carreras anteriores (walk-forward)
# ========================================================================================
def _peso(y, y_obj):
    return np.where(y == y_obj, 3.0, np.where(y == y_obj - 1, 1.5, 1.0))


def _wmed(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    ok = np.isfinite(x)
    x, w = x[ok], w[ok]
    if not len(x):
        return np.nan
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][np.searchsorted(cw, cw[-1] / 2)])


def features_ritmo(df):
    """Variables pre-carrera para el ritmo de carrera (en % de vuelta)."""
    from sim_carrera import prep
    p = prep(df)
    F = pd.DataFrame({
        "qg": p.qg.values, "lg": p.lg.values, "lgm": df.long_gap_all.isna().astype(float).values,
        "form_n": (p.form / p.n).values, "tform_n": (p.tform / p.n).values,
        "tqg": p.assign(_t=df.team.values).groupby(["meeting_key", "_t"]).qg.transform("mean").values,
        "qp_n": ((p.qp - 1) / (p.n - 1)).values,
        "pole": (p.assign(_q=p.qp.values).groupby("meeting_key")._q.rank(method="first") == 1).astype(float).values,
    }, index=df.index)
    return F


COLS_RITMO = ["qg", "lg", "lgm", "form_n", "tform_n", "tqg", "qp_n", "pole"]


class Calibracion:
    """Todo lo que el simulador necesita, estimado sólo con carreras anteriores a `corte`."""

    def __init__(self, h, data, var=None):
        self.h, self.data, self.var = h, data, (var or {})
        car = h["carreras"].copy()
        car["fit_ok"] = car.session_key.map(lambda s: s in h["datos"] and h["datos"][s]["fit"] is not None)
        car["mojada"] = car.session_key.map(lambda s: h["datos"][s]["mojada"] if s in h["datos"] else True)
        self.car = car
        self._plan_cache = {}
        self._ritmo_obj = None

    # ---------------- objetivo de ritmo por carrera (efecto fijo del piloto) ----------------
    def ritmo_real(self, sk):
        c = self.h["datos"][sk]
        al = pd.Series(c["fit"]["alpha"]).dropna()
        rel = ((al - al.median()) / c["ref_lap"] * 100).clip(-3, 4)
        return rel

    def tabla_ritmo(self):
        if self._ritmo_obj is None:
            filas = []
            for r in self.car[self.car.fit_ok].itertuples():
                rel = self.ritmo_real(r.session_key)
                for dn, v in rel.items():
                    filas.append((r.meeting_key, dn, v))
            self._ritmo_obj = pd.DataFrame(filas, columns=["meeting_key", "driver_number", "ritmo"])
        return self._ritmo_obj

    # ---------------- plan observado y costos con parámetros de la propia carrera ----------------
    def planes_carrera(self, sk, glob):
        """Para el ajuste de tau/kappa y del ruido de la vuelta de parada (parámetros 'que conocen los equipos')."""
        if sk in self._plan_cache:
            return self._plan_cache[sk]
        c = self.h["datos"][sk]
        f = c["fit"]
        off = np.array([x if np.isfinite(x) and abs(x) < 2 else g for x, g in zip(f["off"], glob["off"])])
        deg = np.array([x if np.isfinite(x) and -0.02 < x < 0.3 else g for x, g in zip(f["deg"], glob["deg"])])
        deg = np.clip(deg, 0.005, 0.3)
        L = c["nv"]
        st = pd.DataFrame(c["stints"])
        maxlen = np.full(3, L)
        if not st.empty:
            st["n"] = st.lap_end - st.lap_start + 1
            for cc, nom in enumerate(COMP):
                x = st[(st.compound == nom) & (st.lap_end < L - 1)].n
                maxlen[cc] = int(np.percentile(x, 95) * 1.1) if len(x) >= 3 else L
        pit = np.median(c["pit_verde"]) if len(c["pit_verde"]) >= 3 else glob["pit"]
        costo, vueltas = costos_planes(off, deg, L, pit, np.maximum(maxlen, MIN_STINT + 2))
        obs = []
        red = any(e["tipo"] == "RED" for e in c["eventos"])
        for dn, e in c["estrategia"].items():
            if not e["termina"] or red:
                continue
            letras = e["plan"].split("-")
            if "?" in letras:
                continue
            seq = tuple("SMH".index(x) for x in letras)
            if seq in PLANES and len(e["vueltas_parada"]) == len(seq) - 1:
                j = PLANES.index(seq)
                if np.isfinite(costo[j]):
                    obs.append((j, e["vueltas_parada"]))
        out = {"costo": costo, "vueltas": vueltas, "obs": obs, "L": L, "neut": set(c["neut"])}
        self._plan_cache[sk] = out
        return out

    def prior_plan(self, sk, circ=None, corte=None, m=20.0):
        """log-frecuencia (suavizada) de cada plan en carreras secas ANTERIORES: circuito contraído hacia global."""
        if sk is not None:
            fila = self.car[self.car.session_key == sk].iloc[0]
            circ, corte = fila.circuit_key, fila.fecha
        clave = (circ, corte)
        if clave in self._plan_cache:
            return self._plan_cache[clave]
        prev = self.car[(self.car.fecha < corte) & self.car.fit_ok & ~self.car.mojada]
        fg, fc = np.ones(len(PLANES)), np.zeros(len(PLANES))
        for r in prev.itertuples():
            for e in self.h["datos"][r.session_key]["estrategia"].values():
                if not e["termina"] or "?" in e["plan"]:
                    continue
                seq = tuple("SMH".index(x) for x in e["plan"].split("-"))
                if seq in PLANES:
                    fg[PLANES.index(seq)] += 1
                    if r.circuit_key == circ:
                        fc[PLANES.index(seq)] += 1
        pg = fg / fg.sum()
        nc = fc.sum()
        p = (fc + m * pg) / (nc + m)
        out = np.log(p)
        self._plan_cache[clave] = out
        return out

    # ---------------- calibración para un GP ----------------
    def calibrar(self, meeting, obj):
        v = self.var
        fila0 = obj.iloc[0]
        corte = pd.Timestamp(fila0.date).tz_convert(None).normalize() if pd.Timestamp(fila0.date).tzinfo else \
            pd.Timestamp(fila0.date).normalize()
        y_obj = int(fila0.year)
        circ = int(fila0.circuit_key)
        tr = self.car[(self.car.fecha < corte) & self.car.fit_ok & ~self.car.mojada]
        tr_all = self.car[(self.car.fecha < corte) & self.car.session_key.isin(self.h["datos"].keys())]
        w = _peso(tr.year.values, y_obj)
        D = self.h["datos"]
        cal = {"meeting": meeting, "corte": corte, "n_train": len(tr), "circuit_key": circ}

        # --- neumáticos, combustible, ruido por vuelta ---
        def par(fun):
            return np.array([fun(D[s]["fit"]) for s in tr.session_key], float)
        offS = par(lambda f: f["off"][0]); offH = par(lambda f: f["off"][2])
        degs = [par(lambda f, i=i: f["deg"][i]) for i in range(3)]
        for a in [offS, offH]:
            a[(np.abs(a) > 2)] = np.nan
        for a in degs:
            a[(a < -0.02) | (a > 0.3)] = np.nan
        fuel = par(lambda f: f["fuel"]); fuel[(fuel < -0.2) | (fuel > 0.05)] = np.nan
        sd = par(lambda f: f["sd"])
        enc = tr.circuit_key.values == circ
        k_enc = v.get("k_circ", 1.0)

        def mezcla(a):
            g = _wmed(a, w)
            ac = a[enc & np.isfinite(a)]
            if len(ac):
                return float((ac.sum() + k_enc * g) / (len(ac) + k_enc)), g
            return g, g
        o_s, g_os = mezcla(offS)
        o_h, g_oh = mezcla(offH)
        dd = [mezcla(a) for a in degs]
        cal["off"] = np.array([o_s, 0.0, o_h])
        cal["deg"] = np.clip(np.array([x[0] for x in dd]), 0.005, 0.3)
        cal["deg_sd"] = float(np.nanstd(np.concatenate([a[np.isfinite(a)] for a in degs])) * v.get("deg_sd_k", 0.5))
        cal["off_sd"] = float(np.nanstd(np.concatenate([offS[np.isfinite(offS)], offH[np.isfinite(offH)]])) * v.get("deg_sd_k", 0.5))
        cal["fuel"] = mezcla(fuel)[0]
        cal["lap_sd"] = float(_wmed(sd, w))
        glob = {"off": np.array([g_os, 0.0, g_oh]), "deg": np.array([x[1] for x in dd])}

        # --- pérdida en pits ---
        pm = np.array([np.median(D[s]["pit_verde"]) if len(D[s]["pit_verde"]) >= 3 else np.nan for s in tr.session_key])
        g_pit = _wmed(pm, w)
        pc = pm[enc & np.isfinite(pm)]
        cal["pit"] = float((pc.sum() + g_pit) / (len(pc) + 1)) if len(pc) else g_pit
        glob["pit"] = g_pit
        resid = np.concatenate([np.array(D[s]["pit_verde"]) - np.median(D[s]["pit_verde"])
                                for s in tr.session_key if len(D[s]["pit_verde"]) >= 3])
        cal["pit_ruido"] = np.clip(resid, -4, 15)
        ratios = [np.median(D[s]["pit_neutral"]) / np.median(D[s]["pit_verde"]) for s in tr.session_key
                  if len(D[s]["pit_neutral"]) >= 2 and len(D[s]["pit_verde"]) >= 3]
        cal["pit_ratio_sc"] = float(np.clip(np.median(ratios), 0.3, 0.9)) if len(ratios) >= 3 else 0.55
        cal["pit_ratio_vsc"] = float(min(0.9, cal["pit_ratio_sc"] + 0.1))

        # --- largo máximo de stint por compuesto (fracción de carrera) ---
        fr = {cc: [] for cc in range(3)}
        frc = {cc: [] for cc in range(3)}
        for s, ec in zip(tr.session_key, enc):
            st = pd.DataFrame(D[s]["stints"])
            if st.empty:
                continue
            L_ = D[s]["nv"]
            st["n"] = st.lap_end - st.lap_start + 1
            for cc, nom in enumerate(COMP):
                x = (st[(st.compound == nom)].n / L_).tolist()
                fr[cc] += x
                if ec:
                    frc[cc] += x
        L = int(obj.vueltas.iloc[0]) if pd.notna(obj.vueltas.iloc[0]) else 60
        mx = []
        for cc in range(3):
            g = np.percentile(fr[cc], 95) if len(fr[cc]) > 10 else 0.6
            c_ = np.percentile(frc[cc], 95) if len(frc[cc]) >= 5 else g
            mx.append(int(round(L * (0.5 * g + 0.5 * c_) * 1.05)))
        cal["maxlen"] = np.clip(np.array(mx), MIN_STINT + 4, L - MIN_STINT)

        # --- base de la vuelta (s) ---
        rf = []
        for s in tr.session_key:
            mk = self.car.set_index("session_key").meeting_key[s]
            fb = self.data[self.data.meeting_key == mk].fp_best_all.min()
            if np.isfinite(fb) and fb > 0:
                rf.append(D[s]["ref_lap"] / fb)
        fb_obj = obj.fp_best_all.min()
        ref_c = [D[s]["ref_lap"] for s in tr.session_key[enc]]
        cal["ref"] = float(fb_obj * np.median(rf)) if np.isfinite(fb_obj) and len(rf) else (
            float(np.mean(ref_c)) if ref_c else 90.0)
        cal["L"] = L

        # --- ritmo de carrera: Ridge de variables pre-carrera -> % de vuelta ---
        R = self.tabla_ritmo()
        mks_tr = set(self.car[self.car.fecha < corte].meeting_key)
        dtr = self.data[self.data.meeting_key.isin(mks_tr)]
        x = dtr.merge(R, on=["meeting_key", "driver_number"], how="inner")
        F = features_ritmo(x)
        yy = x.ritmo - x.groupby("meeting_key").ritmo.transform("median")
        wr = _peso(x.year.values, y_obj)
        cols = v.get("cols_ritmo", COLS_RITMO)
        rr = Ridge(alpha=v.get("alpha_ritmo", 1.0)).fit(F[cols], yy, sample_weight=wr)
        res = yy - rr.predict(F[cols])
        # componente de equipo del residuo (covarianza entre compañeros)
        x = x.assign(res=res.values)
        cov = x.groupby(["meeting_key", "team"]).res.apply(
            lambda s: s.iloc[0] * s.iloc[1] if len(s) == 2 else np.nan).dropna()
        var_tot = float(np.average(res ** 2, weights=wr))
        rho = float(np.clip(cov.mean() / var_tot, 0, 0.8))
        if v.get("sd_robusto", True):          # MAD: los residuos tienen colas pesadas (averías, tráfico, carreras raras)
            var_tot = float((1.4826 * np.median(np.abs(res - np.median(res)))) ** 2)
        var_t = rho * var_tot
        k_sd = v.get("sd_ritmo_k", 1.0)
        cal["ritmo_sd_eq"] = np.sqrt(var_t) * k_sd
        cal["ritmo_sd_pil"] = np.sqrt(var_tot - var_t) * k_sd
        Fo = features_ritmo(obj)
        mu = rr.predict(Fo[cols])
        cal["ritmo_mu"] = (mu - np.median(mu)) / 100 * cal["ref"]          # s/vuelta
        cal["ritmo_coef"] = dict(zip(cols, np.round(rr.coef_, 3)))

        # --- rebases: logística por tramos de intervalo ---
        P = []
        for s, ww, yr, ck in zip(tr.session_key, w, tr.year, tr.circuit_key):
            p = D[s]["pares"]
            if len(p):
                P.append(p.assign(w=ww, y26=float(yr >= 2026), circ=ck))
        P = pd.concat(P, ignore_index=True)
        P = P[np.isfinite(P.d)]
        especiales = (P.relanza == 1) | (P.lap == 2)
        PE = P[especiales]
        P = P[~especiales]
        Xp = self._X_rebase(P.d.values, P.gap.values, P.y26.values)
        lr = LogisticRegression(C=10.0, max_iter=2000).fit(Xp, P.rebase.values, sample_weight=P.w.values)
        cal["reb_lr"] = lr
        p_hat = lr.predict_proba(Xp)[:, 1]
        m = P.circ.values == circ
        m_ps = v.get("m_reb", 15.0)
        cal["reb_off"] = float(np.log((P.rebase.values[m].sum() + m_ps) / (p_hat[m].sum() + m_ps))) if m.any() else 0.0
        # vuelta 2 (sin DRS) y relanzamientos tras SC/VSC: corrección en logit con sus propios datos
        for nom, mm in (("reb_off_v2", PE.lap == 2), ("reb_off_relanza", (PE.relanza == 1) & (PE.lap > 2))):
            q = PE[mm]
            if len(q) >= 30:
                ph = lr.predict_proba(self._X_rebase(q.d.values, q.gap.values, q.y26.values))[:, 1]
                cal[nom] = float(np.log((q.rebase.sum() + 5) / (ph.sum() + 5)))
            else:
                cal[nom] = 0.0
        cal["y26"] = float(y_obj >= 2026)
        cal["d_k"] = v.get("d_k", 1.0)
        cal["rho_plan"] = v.get("rho_plan", 0.0)
        cal["par_comun"] = v.get("par_comun", False)
        cal["par_k"] = v.get("par_k", 1.0)
        cal["rho_sc"] = v.get("rho_sc", 0.0)
        cal["plan_neutral"] = v.get("plan_neutral", 0.0)

        cal["reb_off_circ"] = cal["reb_off"]
        cal["reb_off"] += v.get("reb_shift", 0.0)
        cal["tasa_reb_hist_circ"] = float(P.rebase.values[m].mean()) if m.any() else np.nan

        # --- vuelta 1 ---
        cal.update(self._vuelta1(tr_all, corte))
        fr_dnf = []
        for s in tr_all.session_key:
            c = D[s]
            fr_dnf += [u / c["nv"] for u in c["ult"] if u < c["nv"] - 3]
        cal["dnf_frac"] = np.clip(np.array(fr_dnf or [0.5]), 0.0, 1.0)

        # --- safety car / VSC ---
        cal.update(self._safety(tr_all, circ, y_obj))
        if v.get("sin_sc"):
            cal.update({"sc_p1": 0.0, "sc_por_carrera": 0.0, "vsc_por_carrera": 0.0})

        # --- cubrir el undercut: tasa por posición del defensor (carreras anteriores) ---
        if v.get("cubrir_pos", True):
            cal["cub_tabla"] = self._cubrir(tr)
        if v.get("conf_pos", False):
            cal.update(self._conformidad(tr))
        # --- estrategia: tau y kappa por máxima verosimilitud, ruido de la vuelta de parada ---
        cal.update(self._estrategia(tr, w, glob, cal))
        return cal

    def _eventos_cubrir(self, sk):
        clave = ("cub", sk)
        if clave in self._plan_cache:
            return self._plan_cache[clave]
        c = self.h["datos"][sk]
        T, IN, nv, neut = c["T"], c["IN"], c["nv"], set(c["neut"])
        nstop = np.cumsum(IN, axis=1)
        ev = []
        for k in range(3, nv - 2):
            if k in neut or k - 1 in neut or k + 1 in neut:
                continue
            o = orden_vuelta(T, k - 1)
            for p in range(1, len(o)):
                a, b = o[p], o[p - 1]
                if T[a, k - 1] - T[b, k - 1] < 2.5 and IN[a, k] and not IN[b, k] and nstop[a, k - 1] == nstop[b, k - 1]:
                    ev.append((p, bool(IN[b, k + 1])))
        self._plan_cache[clave] = ev
        return ev

    def _conformidad(self, tr):
        """Por tramo de salida (1-3, 4-6, 7-10, 11-15, 16+): fracción que usa el plan más común de su carrera y
        dispersión (MAD) de la 1.ª parada respecto a la mediana de ese plan (sin SC), relativa a la global."""
        filas = []
        for s in tr.session_key:
            clave = ("conf", s)
            if clave not in self._plan_cache:
                c = self.h["datos"][s]
                mk = self.car.set_index("session_key").meeting_key[s]
                g = self.data[self.data.meeting_key == mk].set_index("driver_number").grid
                E = pd.DataFrame([{"dn": dn, "plan": e["plan"], "v1": e["vueltas_parada"][0] if e["vueltas_parada"] else np.nan}
                                  for dn, e in c["estrategia"].items() if e["termina"]])
                out = []
                if len(E) >= 8 and len(g):
                    m = E.plan.value_counts().index[0]
                    E["modal"] = E.plan == m
                    E["grid"] = E.dn.map(g)
                    E["sc"] = [bool(np.isfinite(v) and (v in c["neut"] or v - 1 in c["neut"])) for v in E.v1]
                    x = E[E.modal & ~E.sc & E.v1.notna()]
                    med = x.v1.median() if len(x) >= 4 else np.nan
                    for _, e in E.iterrows():
                        res = (e.v1 - med) / c["nv"] if (e.modal and not e.sc and np.isfinite(med) and np.isfinite(e.v1)) else np.nan
                        out.append((e.grid, e.modal, res))
                self._plan_cache[clave] = out
            filas += self._plan_cache[clave]
        R = pd.DataFrame(filas, columns=["grid", "modal", "res"]).dropna(subset=["grid"])
        tramos = [(1, 3), (4, 6), (7, 10), (11, 15), (16, 30)]
        share, fac = [], []
        mad_all = 1.4826 * np.nanmedian(np.abs(R.res.dropna()))
        for a, b in tramos:
            x = R[(R.grid >= a) & (R.grid <= b)]
            share.append(float(x.modal.mean()))
            r_ = x.res.dropna()
            fac.append(float(1.4826 * np.median(np.abs(r_)) / mad_all) if len(r_) >= 20 else 1.0)
        return {"conf_share": share, "conf_fac": fac}

    def _cubrir(self, tr, m=3.0):
        ev = [e for s in tr.session_key for e in self._eventos_cubrir(s)]
        E = pd.DataFrame(ev, columns=["pos", "cubre"])
        p0 = E.cubre.mean() if len(E) else 0.2
        tabla = []
        for a, b in [(1, 1), (2, 3), (4, 6), (7, 10), (11, 30)]:
            x = E[(E.pos >= a) & (E.pos <= b)].cubre
            tabla.append(float((x.sum() + m * p0) / (len(x) + m)))
        return tabla

    @staticmethod
    def _X_rebase(d, gap, y26):
        dc = np.clip(np.nan_to_num(d), -2.0, 3.0)
        cols = []
        for a, b in [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, G_MAX + 1)]:
            m = ((gap >= a) & (gap < b)).astype(float)
            cols += [m, m * dc]
        cols.append(np.asarray(y26, float))
        return np.column_stack(cols)

    def _vuelta1(self, tr_all, corte):
        D = self.h["datos"]
        delta, gn_l, g_l, gaps = [], [], [], {}
        for r in tr_all.itertuples():
            c = D[r.session_key]
            g = self.data[self.data.meeting_key == r.meeting_key][["driver_number", "grid"]].dropna()
            if g.empty:
                continue
            gmap = dict(zip(g.driver_number, g.grid))
            o1 = [d for d in c["orden1"] if d in gmap]
            n = len(g)
            gr = pd.Series({d: gmap[d] for d in o1}).rank(method="first")
            for p, d in enumerate(o1):
                delta.append((p + 1) - gr[d])
                g_l.append(gr[d])
                gn_l.append((gr[d] - 1) / max(n - 1, 1))
            for p, gp in enumerate(c["gaps1"]):
                if 0 < gp < 15:
                    gaps.setdefault(min(p + 1, 21), []).append(gp)
        delta, gn_l = np.array(delta), np.array(gn_l)
        g_l = np.array(g_l)
        # sigma(g) = (s0 + s1*gn) * (sf si sale 1.º), latente t(4): momentos |delta| por tramos de salida + P(pole sigue 1.º)
        tramos = [(1, 1), (2, 2), (3, 3), (4, 7), (8, 12), (13, 17), (18, 30)]
        obj = np.array([np.abs(delta[(g_l >= a) & (g_l <= b)]).mean() for a, b in tramos]
                       + [float((delta[g_l == 1] == 0).mean())])
        clave = ("v1", len(delta))
        if clave in self._plan_cache:
            return self._plan_cache[clave]
        rng = np.random.default_rng(1)
        n = 20
        gsim = np.arange(1, n + 1)
        gn = (gsim - 1) / (n - 1)
        eps = rng.standard_t(4, size=(1500, n))
        mejor, best = None, 1e9
        for sf in (0.15, 0.25, 0.35, 0.45, 0.6, 0.8, 1.0):
            for s0 in np.arange(0.2, 2.01, 0.15):
                for s1 in np.arange(0.0, 3.01, 0.25):
                    sig = (s0 + s1 * gn) * np.where(gsim == 1, sf, 1.0)
                    lat = gsim + sig * eps
                    pos = lat.argsort(1).argsort(1) + 1
                    ad = np.abs(pos - gsim)
                    simv = np.array([ad[:, (gsim >= a) & (gsim <= b)].mean() for a, b in tramos]
                                    + [float((pos[:, 0] == 1).mean())])
                    e = ((simv[:-1] - obj[:-1]) ** 2).sum() + 25 * (simv[-1] - obj[-1]) ** 2
                    if e < best:
                        best, mejor = e, (s0, s1, sf)
        out = {"v1_s0": mejor[0], "v1_s1": mejor[1], "v1_sf": mejor[2], "v1_obj": obj.round(2).tolist(),
               "v1_gaps": {k: np.array(v) for k, v in gaps.items()}}
        self._plan_cache[clave] = out
        return out

    def _safety(self, tr_all, circ, y_obj):
        D = self.h["datos"]
        n_r, n_c = 0, 0
        e1 = {"glob": 0, "circ": 0}
        esc = {"glob": 0, "circ": 0}
        evsc = {"glob": 0, "circ": 0}
        vueltas = {"glob": 0, "circ": 0}
        dur_sc, dur_vsc, fr_sc, fr_vsc = [], [], [], []
        for r in tr_all.itertuples():
            c = D[r.session_key]
            if not c.get("eventos") and not (CACHE / f"race_rc_{r.session_key}.json").exists():
                continue
            esc_c = r.circuit_key == circ
            n_r += 1
            n_c += esc_c
            vueltas["glob"] += c["nv"] - 1
            vueltas["circ"] += (c["nv"] - 1) * esc_c
            for e in c["eventos"]:
                tipo = "SC" if e["tipo"] in ("SC", "RED") else "VSC"
                if e["tipo"] == "RED" and any(x["tipo"] == "SC" and x["fin"] >= e["ini"] - 1 for x in c["eventos"]):
                    continue
                if e["ini"] <= 1 and tipo == "SC":
                    e1["glob"] += 1
                    e1["circ"] += esc_c
                elif tipo == "SC":
                    esc["glob"] += 1
                    esc["circ"] += esc_c
                else:
                    evsc["glob"] += 1
                    evsc["circ"] += esc_c
                (dur_sc if tipo == "SC" else dur_vsc).append(max(1, e["fin"] - e["ini"] + 1))
                if e["ini"] > 1:
                    (fr_sc if tipo == "SC" else fr_vsc).append(e["ini"] / c["nv"])
        # tasa de paradas al empezar un SC/VSC (vuelta >= 3) por momento de carrera y paradas previas
        cuenta = np.zeros((2, 6, 2))
        pits = np.zeros((2, 6, 2))
        for r in tr_all.itertuples():
            c = D[r.session_key]
            if c["mojada"]:
                continue
            IN, nv = c["IN"], c["nv"]
            for e in c["eventos"]:
                if e["tipo"] not in ("SC", "VSC") or e["ini"] < 3:
                    continue
                t_ = 0 if e["tipo"] == "SC" else 1
                fb = min(int(np.searchsorted([0.2, 0.35, 0.5, 0.65, 0.8], e["ini"] / nv, side="right")), 5)
                for i in range(len(c["drivers"])):
                    if c["ult"][i] < e["fin"] + 3:
                        continue
                    pv = int(IN[i, :e["ini"]].sum() >= 1)
                    cuenta[t_, fb, pv] += 1
                    pits[t_, fb, pv] += any(IN[i, kk] for kk in range(e["ini"], e["fin"] + 1))
        p0 = (pits.sum((1, 2)) + 1) / (cuenta.sum((1, 2)) + 2)
        tabla = (pits + 5 * p0[:, None, None]) / (cuenta + 5)
        k = self.var.get("k_sc", 4.0)
        p1 = (e1["circ"] + k * e1["glob"] / max(n_r, 1)) / (n_c + k)
        lam_sc = (esc["circ"] + k * esc["glob"] / max(n_r, 1)) / (n_c + k)        # eventos por carrera
        lam_vsc = (evsc["circ"] + k * evsc["glob"] / max(n_r, 1)) / (n_c + k)
        return {"sc_pit_tabla": tabla.tolist(), "sc_p1": float(min(p1, 0.6)), "sc_por_carrera": float(lam_sc), "vsc_por_carrera": float(lam_vsc),
                "sc_dur": np.array(dur_sc or [4]), "vsc_dur": np.array(dur_vsc or [2]),
                "sc_frac": np.array(fr_sc), "vsc_frac": np.array(fr_vsc),
                "sc_glob": {"p1": e1["glob"] / max(n_r, 1), "sc": esc["glob"] / max(n_r, 1), "vsc": evsc["glob"] / max(n_r, 1)},
                "sc_circ_n": int(n_c), "sc_circ_eventos": int(e1["circ"] + esc["circ"] + evsc["circ"])}

    def _estrategia(self, tr, w, glob, cal):
        obs_all = []
        res_v, res_r = [], []
        for s, ww in zip(tr.session_key, w):
            pc = self.planes_carrera(s, glob)
            for j, vp in pc["obs"]:
                obs_all.append((pc["costo"], j, ww, self.prior_plan(s)))
                opt = pc["vueltas"][j]
                for q, lap in enumerate(vp):
                    if lap in pc["neut"] or (lap - 1) in pc["neut"]:
                        continue
                    res_v.append((lap - opt[q]) / pc["L"])
                    res_r.append(s)
        C = np.array([o[0] for o in obs_all])
        J = np.array([o[1] for o in obs_all])
        W = np.array([o[2] for o in obs_all])
        C = np.where(np.isfinite(C), C, 1e6)
        mejor, best = (10.0, 0.0), -np.inf
        PR = np.array([o[3] for o in obs_all])
        mejor = (10.0, 0.0, 0.0)
        for tau in [3, 5, 8, 12, 18, 25, 40, 60, 100, 200]:
            for kap in [-10, 0, 10, 20, 30, 45, 60, 90, 130]:
                for lam in [0.0, 0.5, 1.0, 1.5]:
                    z = -(C + kap * PLAN_PARADAS[None, :]) / tau + lam * PR
                    z = z - z.max(1, keepdims=True)
                    lp = z[np.arange(len(J)), J] - np.log(np.exp(z).sum(1))
                    ll = (lp * W).sum()
                    if ll > best:
                        best, mejor = ll, (tau, kap, lam)
        res_v = np.array(res_v)
        med = float(np.median(res_v))
        mad = float(np.median(np.abs(res_v - med)) * 1.4826)
        # dentro de la carrera vs desplazamiento común de la carrera
        rv = pd.DataFrame({"r": res_r, "v": res_v})
        dentro = rv.groupby("r").v.apply(lambda x: 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) >= 5 else np.nan)
        sd_dentro = float(np.nanmedian(dentro)) if dentro.notna().any() else mad
        sd_comun = float(np.sqrt(max(mad ** 2 - sd_dentro ** 2, 0.0)))
        # costos para el GP objetivo con perturbaciones de los parámetros de neumático
        rng = np.random.default_rng(7)
        K = 40
        costos, vueltas, d_deg, d_off = [], [], [], []
        for kk in range(K):
            dg = np.clip(cal["deg"] + (rng.normal(0, cal["deg_sd"], 3) if kk else 0), 0.005, 0.3)
            of = cal["off"] + (np.r_[rng.normal(0, cal["off_sd"]), 0, rng.normal(0, cal["off_sd"])] if kk else 0)
            c_, v_ = costos_planes(of, dg, cal["L"], cal["pit"], cal["maxlen"])
            d_deg.append(dg)
            d_off.append(of)
            costos.append(c_)
            vueltas.append(v_)
        return {"tau": mejor[0], "kappa": mejor[1], "lam_prior": mejor[2], "loglik_plan": float(best), "n_planes_obs": int(len(J)),
                "prior_plan": self.prior_plan(None, circ=cal["circuit_key"], corte=cal["corte"]),
                "par_sesgo": med, "par_sd": mad, "par_sd_dentro": sd_dentro, "par_sd_comun": sd_comun, "costos": np.array(costos), "vueltas_plan": np.array(vueltas),
                "draw_deg": np.array(d_deg), "draw_off": np.array(d_off)}


# ========================================================================================
# 4) Motor vuelta a vuelta (vectorizado sobre simulaciones)
# ========================================================================================
GRANDE = 1e7
DIN = {"x_uc": 1.2, "w_uc": 3, "p_uc": 0.30, "x_cov": 2.5, "w_cov": 20, "p_cov": 0.2,
       "w_sc": 15, "p_sc": 0.85, "p_vsc": 0.55, "sucio": 0.15, "mg0": 0.35, "mg_exp": 0.35}


def simular(cal, obj, p_dnf, n_sims=2000, seed=0, din=None, guardar=True):
    """obj: DataFrame del GP (grid, team, ...) en el mismo orden que cal['ritmo_mu'] y p_dnf.
    Devuelve dict con tiempos acumulados por vuelta, paradas, compuestos, rebases y SC por simulación."""
    din = {**DIN, **(din or {})}
    rng = np.random.default_rng(seed)
    S, n, L = n_sims, len(obj), cal["L"]
    ar = np.arange(S)
    ref, fuel = cal["ref"], cal["fuel"]
    # --- ritmo por simulación (piloto + equipo) ---
    eq = pd.factorize(obj.team.values)[0]
    pace = (cal["ritmo_mu"][None, :] + rng.normal(0, cal["ritmo_sd_pil"], (S, n))
            + rng.normal(0, cal["ritmo_sd_eq"], (S, eq.max() + 1))[:, eq])
    # --- neumáticos por simulación (sorteo de parámetros) y plan ---
    K = len(cal["costos"])
    kd = rng.integers(0, K, S)
    deg = cal["draw_deg"][kd]                     # (S,3)
    off = cal["draw_off"][kd]
    z = (-(cal["costos"][kd] + cal["kappa"] * PLAN_PARADAS[None, :]) / cal["tau"]
         + cal["lam_prior"] * cal["prior_plan"][None, :])          # (S,P)
    z = np.where(np.isfinite(z), z, -1e9)
    gum = rng.gumbel(size=(S, n, len(PLANES)))
    plan = np.argmax(z[:, None, :] + gum, axis=2)                  # (S,n)
    rho = cal.get("rho_plan", 0.0)
    tramo = np.searchsorted([3, 6, 10, 15], pd.Series(obj.grid.values).rank(method="first").values, side="left")
    if "conf_share" in cal:          # conformidad con el plan de la carrera según la salida (calibrada)
        pz = np.exp(z - z.max(1, keepdims=True))
        pz = pz / pz.sum(1, keepdims=True)
        base = float(np.mean((pz ** 2).sum(1)))        # prob. de coincidir con el plan de la carrera por azar
        rho = np.clip((np.asarray(cal["conf_share"])[tramo] - base) / (1 - base), 0, 1)[None, :]
    if np.any(np.asarray(rho) > 0):      # estrategias correlacionadas dentro de la carrera: plan "de la carrera" que adopta una fracción rho
        plan_c = np.argmax(z + rng.gumbel(size=z.shape), axis=1)
        sigue = rng.random((S, n)) < rho
        plan = np.where(sigue, plan_c[:, None], plan)
    plan_comp = np.array([list(p) + [-1] * (4 - len(p)) for p in PLANES])[plan]   # (S,n,4)
    # preferencia revelada: los equipos eligen planes casi equivalentes; se descuenta (fracción c) la desventaja
    # de tiempo que el modelo de neumáticos le asigna al plan elegido frente al mejor plan de ese sorteo
    c_neu = cal.get("plan_neutral", 0.0)
    cst = cal["costos"][kd]
    ventaja = np.zeros((S, n))
    if c_neu > 0:
        mejor = np.min(np.where(np.isfinite(cst), cst, np.inf), axis=1)
        dif = np.take_along_axis(cst, plan, axis=1) - mejor[:, None]
        ventaja = c_neu * np.where(np.isfinite(dif), dif, 0.0) / L          # s por vuelta
    n_par = PLAN_PARADAS[plan].copy()
    vp = cal["vueltas_plan"][kd[:, None], plan].astype(float)                  # (S,n,2)
    if cal.get("par_comun", False):      # desplazamiento común de la carrera + ruido propio de cada equipo
        kp = cal.get("par_k", 1.0)
        ruido = (rng.normal(cal["par_sesgo"] * L, max(cal["par_sd_comun"] * L, 0.5) * kp, (S, 1, 1))
                 + rng.normal(0, max(cal["par_sd_dentro"] * L, 1.0) * kp, (S, n, 2))
                 * (np.asarray(cal["conf_fac"])[tramo][None, :, None] if "conf_fac" in cal else 1.0))
    else:
        ruido = rng.normal(cal["par_sesgo"] * L, max(cal["par_sd"] * L, 1.0), (S, n, 2))
    vp = np.round(vp + ruido)
    vp[..., 0] = np.clip(vp[..., 0], 3, L - 4)
    vp[..., 1] = np.where(n_par >= 2, np.clip(vp[..., 1], vp[..., 0] + 5, L - 2), 10 ** 6)
    vparada = np.concatenate([vp, np.full((S, n, 2), 10 ** 6)], axis=2)       # (S,n,4)
    # --- safety car / VSC: estado por vuelta (0 verde, 1 SC, 2 VSC) ---
    neut = np.zeros((S, L + 2), int)
    sc1 = rng.random(S) < cal["sc_p1"]
    d1 = rng.choice(cal["sc_dur"], S)
    for s in np.where(sc1)[0]:
        neut[s, 2:min(L, 1 + d1[s]) + 1] = 1
    for tipo, lam, durs, fr in ((1, cal["sc_por_carrera"], cal["sc_dur"], cal.get("sc_frac")),
                                (2, cal["vsc_por_carrera"], cal["vsc_dur"], cal.get("vsc_frac"))):
        n_ev = rng.poisson(lam, S)
        for s in np.where(n_ev > 0)[0]:
            for _ in range(n_ev[s]):
                if fr is not None and len(fr) >= 5:
                    k = int(np.clip(np.ceil(rng.choice(fr) * L), 2, L - 1))
                else:
                    k = int(rng.integers(2, L))
                if neut[s, k] == 0:
                    neut[s, k:min(L, k + rng.choice(durs) - 1) + 1] = tipo
    # --- abandonos ---
    out = rng.random((S, n)) < p_dnf[None, :]
    frac = rng.choice(cal["dnf_frac"], (S, n))
    vuelta_dnf = np.where(out, np.clip(np.ceil(frac * L), 1, L), L + 5).astype(int)
    # --- vuelta 1 ---
    g = obj.grid.values.astype(float)
    gn = (g - 1) / max(n - 1, 1)
    gr_ = pd.Series(g).rank(method="first").values
    sig1 = (cal["v1_s0"] + cal["v1_s1"] * gn) * np.where(gr_ == 1, cal.get("v1_sf", 1.0), 1.0)
    lat = g[None, :] + sig1[None, :] * rng.standard_t(4, (S, n))
    o1 = np.argsort(lat, axis=1)
    gaps = np.zeros((S, n))
    for p in range(1, n):
        pool = cal["v1_gaps"].get(min(p, 21))
        if pool is None or len(pool) < 5:
            pool = np.concatenate(list(cal["v1_gaps"].values()))
        gaps[:, p] = rng.choice(pool, S)
    T = np.zeros((S, n))
    T[ar[:, None], o1] = ref * 1.04 + np.cumsum(gaps, axis=1)
    muerto1 = vuelta_dnf == 1
    T = np.where(muerto1, GRANDE + (L - 1) * 1000 + rng.random((S, n)), T)
    pos1 = T.argsort(1).argsort(1) + 1
    comp = plan_comp[..., 0].copy()
    edad = np.ones((S, n))                         # ya dieron la vuelta 1
    paradas = np.zeros((S, n), int)
    usados = np.zeros((S, n, 3), bool)
    usados[ar[:, None], np.arange(n)[None, :], comp] = True
    gan = np.zeros((S, n), int)
    per = np.zeros((S, n), int)
    hist = np.zeros((S, n, L + 1), np.float32) if guardar else None
    if guardar:
        hist[:, :, 1] = T
    vuelta_par = np.zeros((S, n, 3), int)
    comp_stint = np.full((S, n, 4), -1, int)
    comp_stint[..., 0] = comp
    tipo_par = np.zeros((S, n, 3), int)            # 1 plan, 2 undercut, 3 cubrir, 4 SC/VSC
    pitted_prev = np.zeros((S, n), bool)
    pos_prev = np.tile(np.arange(1, n + 1), (S, 1))
    detras_prev = np.full((S, n), -1)
    gap_detras_prev = np.full((S, n), np.inf)
    off_i = lambda c_: np.take_along_axis(off, np.maximum(c_, 0), axis=1)
    deg_i = lambda c_: np.take_along_axis(deg, np.maximum(c_, 0), axis=1)
    maxlen = np.asarray(cal["maxlen"])
    for k in range(2, L + 1):
        vivo = T < GRANDE
        orden = np.argsort(T, axis=1)
        To = np.take_along_axis(T, orden, axis=1)
        gap_o = np.diff(To, axis=1, prepend=-np.inf)
        gap = np.empty((S, n))
        gap[ar[:, None], orden] = gap_o
        adelante = np.full((S, n), -1)
        adelante[ar[:, None], orden[:, 1:]] = orden[:, :-1]
        detras = np.full((S, n), -1)
        detras[ar[:, None], orden[:, :-1]] = orden[:, 1:]
        gap_detras = np.full((S, n), np.inf)
        gap_detras[ar[:, None], orden[:, :-1]] = gap_o[:, 1:]
        nz = neut[:, k]
        verde = nz == 0
        prox = np.take_along_axis(vparada, paradas[..., None], axis=2)[..., 0]
        quedan = paradas < n_par
        prox = np.where(quedan, prox, 10 ** 6)
        falta = prox - k
        # 1) parada del plan
        pit = vivo & quedan & (falta <= 0) & (k < L)
        # 2) undercut: atrapado a < x_uc del de adelante con la misma cantidad de paradas y ventana abierta
        ad = np.maximum(adelante, 0)
        mismo = (adelante >= 0) & (np.take_along_axis(paradas, ad, 1) == paradas) & np.take_along_axis(vivo, ad, 1)
        uc = (vivo & quedan & ~pit & verde[:, None] & mismo & (gap < din["x_uc"]) & (falta > 0) & (falta <= din["w_uc"])
              & (rng.random((S, n)) < din["p_uc"]) & (k < L - 3))
        # 3) cubrir: el de atrás (a < x_cov al inicio de la vuelta anterior) paró la vuelta pasada
        dp = np.maximum(detras_prev, 0)
        if "cub_tabla" in cal:
            p_cov = np.asarray(cal["cub_tabla"])[np.searchsorted([1, 3, 6, 10], pos_prev, side="left")]
        else:
            p_cov = din["p_cov"]
        cub = (vivo & quedan & ~pit & ~uc & verde[:, None] & (detras_prev >= 0)
               & np.take_along_axis(pitted_prev, dp, 1) & (gap_detras_prev < din["x_cov"])
               & (np.take_along_axis(paradas, dp, 1) == paradas + 1) & (falta <= din["w_cov"])
               & (rng.random((S, n)) < p_cov) & (k < L - 3))
        # 4) parada barata con SC/VSC
        sig_c = np.take_along_axis(plan_comp, np.minimum(paradas + 1, 3)[..., None], axis=2)[..., 0]
        aguanta = (L - k) <= maxlen[np.maximum(sig_c, 0)]
        ultima = paradas + 1 >= n_par
        p_n = np.where(nz == 1, din["p_sc"], np.where(nz == 2, din["p_vsc"], 0.0))
        scp = (vivo & quedan & ~pit & ~uc & ~cub & (nz > 0)[:, None] & (falta <= din["w_sc"]) & (aguanta | ~ultima)
               & (rng.random((S, n)) < p_n[:, None]) & (k < L - 1))
        extra_sc = np.zeros((S, n), bool)
        if "sc_pit_tabla" in cal:     # decisión al empezar el SC/VSC con la tasa histórica (momento de carrera x paradas previas)
            inicio = (nz > 0) & (neut[:, k - 1] == 0)
            if inicio.any():
                tb = np.asarray(cal["sc_pit_tabla"])            # (2 tipos, 6 tramos, 2 [sin/con parada previa])
                fb = min(int(np.searchsorted([0.2, 0.35, 0.5, 0.65, 0.8], k / L, side="right")), 5)
                p_t = tb[np.clip(nz - 1, 0, 1), fb][:, None, :]               # (S,1,2)
                p_i = np.where(paradas >= 1, p_t[..., 1], p_t[..., 0])
                rc_ = cal.get("rho_sc", 0.0)     # decisiones correlacionadas dentro del mismo SC (todos paran o nadie)
                zlat = np.sqrt(rc_) * rng.standard_normal((S, 1)) + np.sqrt(1 - rc_) * rng.standard_normal((S, n))
                from scipy.special import ndtr
                quiere = vivo & inicio[:, None] & (ndtr(zlat) < p_i) & (k < L - 1) & (edad > 4) & ~pit & ~uc & ~cub
                scp = quiere & quedan
                extra_sc = quiere & ~quedan & (paradas < 3)
        para = pit | uc | cub | scp | extra_sc
        # tiempo de vuelta potencial
        pot = pace + off_i(comp) + deg_i(comp) * edad
        lt = ref + fuel * k + pot - ventaja + rng.normal(0, cal["lap_sd"], (S, n)) + din["sucio"] * (gap < 1.0)
        perdida = cal["pit"] + rng.choice(cal["pit_ruido"], (S, n))
        perdida = perdida * np.where(nz == 1, cal["pit_ratio_sc"], np.where(nz == 2, cal["pit_ratio_vsc"], 1.0))[:, None]
        cand = T + lt + para * perdida
        nuevoT = cand.copy()
        if True:  # bloque de interacción de la vuelta
            # SC: el pelotón se junta (sin rebases); VSC: todos al mismo delta (sin rebases)
            sc = nz == 1
            vsc = nz == 2
            if sc.any() or vsc.any():
                base_n = T + ref * 1.35 + para * perdida
                if sc.any():
                    Tc = To.copy()
                    for p in range(1, n):
                        gp = To[:, p] - To[:, p - 1]
                        Tc[:, p] = np.where(To[:, p] < GRANDE, Tc[:, p - 1] + np.minimum(gp, np.maximum(gp * 0.35, 0.6)),
                                            To[:, p])
                    Tcomp = np.empty((S, n))
                    Tcomp[ar[:, None], orden] = Tc
                    # comprimir: diferencias al líder <= originales
                    Tcomp = np.minimum(Tcomp, T)
                    base_sc = Tcomp + ref * 1.35 + para * perdida
                    nuevoT = np.where(sc[:, None], base_sc, nuevoT)
                nuevoT = np.where(vsc[:, None], base_n, nuevoT)
            # verde: interacción en pista entre autos que no entran a pits, en el orden de salida de la vuelta
            if verde.any():
                ultT = np.full(S, -np.inf)
                penT = np.full(S, -np.inf)
                ult_i = np.full(S, -1)
                ult_pot = np.zeros(S)
                X_off = cal["reb_off"] + (cal.get("reb_off_v2", 0.0) if k == 2 else 0.0)
                X_off = X_off + np.where(neut[:, k - 1] > 0, cal.get("reb_off_relanza", 0.0), 0.0)
                for p in range(n):
                    j = orden[:, p]
                    cj = cand[ar, j]
                    act = verde & vivo[ar, j] & ~para[ar, j]
                    tiene = act & (ult_i >= 0)
                    gj = T[ar, j] - np.where(ult_i >= 0, T[ar, np.maximum(ult_i, 0)], -np.inf)
                    d = (ult_pot - pot[ar, j]) * cal.get("d_k", 1.0)
                    intenta = tiene & (gj < G_MAX)
                    Xr = Calibracion._X_rebase(d, gj, np.full(S, cal["y26"]))
                    pr = expit(Xr @ cal["reb_lr"].coef_[0] + cal["reb_lr"].intercept_[0] + X_off)
                    exito = intenta & (rng.random(S) < pr)
                    mg = din["mg0"] + rng.exponential(din["mg_exp"], S)
                    t_ex = np.clip(cj, penT + mg, ultT - 0.15)
                    t_ex = np.where(penT + mg > ultT - 0.15, (penT + ultT) / 2, t_ex)
                    t_no = np.maximum(cj, ultT + mg)
                    tj = np.where(exito, t_ex, np.where(tiene, t_no, cj))
                    nuevoT[ar, j] = np.where(verde, tj, nuevoT[ar, j])
                    gan[ar, j] += exito
                    per[ar, np.maximum(ult_i, 0)] += exito & (ult_i >= 0)
                    upd = act & ~exito
                    penT = np.where(upd, ultT, np.where(exito, np.maximum(penT, tj), penT))
                    ult_pot = np.where(upd, pot[ar, j], ult_pot)
                    ultT = np.where(upd, tj, ultT)
                    ult_i = np.where(upd, j, ult_i)
        # abandonos en esta vuelta
        muere = vivo & (vuelta_dnf == k)
        nuevoT = np.where(muere, GRANDE + (L - k) * 1000 + rng.random((S, n)), nuevoT)
        nuevoT = np.where(~vivo, T, nuevoT)
        # actualizar neumáticos y paradas
        para = para & ~muere
        idx_p = np.minimum(paradas, 2)
        tp = np.where(pit, 1, np.where(uc, 2, np.where(cub, 3, 4)))      # 4 = SC/VSC (también paradas extra)
        si, di = np.where(para)
        vuelta_par[si, di, idx_p[si, di]] = k
        tipo_par[si, di, idx_p[si, di]] = tp[si, di]
        nuevo_c = np.take_along_axis(plan_comp, np.minimum(paradas + 1, 3)[..., None], axis=2)[..., 0]
        nuevo_c = np.where(nuevo_c < 0, comp, nuevo_c)
        if extra_sc.any():           # parada extra (gomas nuevas): el compuesto más blando que llega al final
            blando = np.where(maxlen[0] >= L - k, 0, np.where(maxlen[1] >= L - k, 1, 2))
            nuevo_c = np.where(extra_sc, blando, nuevo_c)
            si_, di_ = np.where(extra_sc)
            plan_comp[si_, di_, np.minimum(paradas[si_, di_] + 1, 3)] = blando
            n_par = np.where(extra_sc, n_par + 1, n_par)
        temprano = para & (falta > 0)
        paradas = paradas + para
        comp = np.where(para, nuevo_c, comp)
        comp_stint[si, di, np.minimum(paradas[si, di], 3)] = comp[si, di]
        usados[si, di, comp[si, di]] = True
        edad = np.where(para, 0, edad) + 1
        # tras una parada adelantada: correr la siguiente; con SC/VSC y gomas que llegan al final, cancelar las demás
        sig = np.minimum(paradas, 3)
        resto = paradas < n_par
        corr = np.where(temprano & resto, np.round(0.5 * (k - prox)), 0)
        if corr.any():
            vv = np.take_along_axis(vparada, sig[..., None], axis=2)[..., 0]
            vv = np.where(temprano & resto, np.maximum(vv + corr, k + 5), vv)
            np.put_along_axis(vparada, sig[..., None], vv[..., None], axis=2)
        cancela = (para & resto & ((L - k) <= maxlen[comp]) & (usados.sum(2) >= 2) & (nz > 0)[:, None]
                   & (rng.random((S, n)) < 0.8))
        n_par = np.where(cancela, paradas, n_par)
        pitted_prev = para
        detras_prev, gap_detras_prev = detras, gap_detras
        pos_prev = np.empty((S, n), int)
        pos_prev[ar[:, None], orden] = np.arange(1, n + 1)[None, :]
        T = nuevoT
        if guardar:
            hist[:, :, k] = T
    # obligación de 2 compuestos: quien terminó con un solo compuesto (por cancelaciones) se considera con el plan
    fin = T.argsort(1).argsort(1) + 1
    return {"pos": fin, "T": hist, "vuelta_par": vuelta_par, "tipo_par": tipo_par, "comp_stint": comp_stint,
            "paradas": paradas, "gan": gan, "per": per, "neut": neut, "pos1": pos1, "plan": plan, "vivo": T < GRANDE}


def p_dnf_modelo(data, meeting, obj):
    """Probabilidad de abandono del simulador actual (logística de fiabilidad de sim_carrera), sólo con el pasado."""
    from sim_carrera import Simulador
    fecha = obj.date.iloc[0]
    tr = data[(data.date < fecha) & data.race_pos.notna() & (data.meeting_key != meeting)]
    sim = Simulador({"is26": False, "gn_inter": True}).fit(tr.sort_values(["meeting_key", "driver_number"]))
    from sim_carrera import X_dnf, prep
    return sim.rd.predict_proba(X_dnf(prep(obj)))[:, 1]


ANCLA_IT, ANCLA_ETA, ANCLA_SIMS = 8, 0.06, 1500


def anclar(cal, obj, pdnf, objetivo, n_it=6, n_sims=300, eta=0.05, seed=0, din=None):
    """Ajusta un 'ritmo efectivo' por piloto (s/vuelta) para que la posición media del vuelta a vuelta coincida con
    la del simulador actual (objetivo: posición media por piloto). Devuelve el ajuste por piloto."""
    base = cal["ritmo_mu"].copy()
    delta = np.zeros(len(obj))
    for _ in range(n_it):
        cal["ritmo_mu"] = base + delta
        r = simular(cal, obj, pdnf, n_sims=n_sims, seed=seed, din=din, guardar=False)
        m = r["pos"].mean(0)
        delta -= eta * (m - objetivo)
    cal["ritmo_mu"] = base + delta
    cal["ajuste_ancla"] = delta
    return delta


# ========================================================================================
# 5) Validación walk-forward
# ========================================================================================
def resumen_sim(r, obj):
    """Métricas por piloto de un conjunto de simulaciones."""
    pos = r["pos"]
    out = pd.DataFrame({"driver_number": obj.driver_number.values, "pos_media": pos.mean(0),
                        "p_win": (pos == 1).mean(0), "p_podio": (pos <= 3).mean(0), "p_top10": (pos <= 10).mean(0),
                        "gan": r["gan"].mean(0), "per": r["per"].mean(0)})
    viv = r["vivo"]
    par = np.where(viv, r["paradas"], -1)
    moda = []
    prim = []
    for i in range(len(obj)):
        x = par[:, i][par[:, i] >= 0]
        moda.append(int(np.bincount(x).argmax()) if len(x) else 1)
        v1 = r["vuelta_par"][:, i, 0]
        v1 = v1[(v1 > 0) & viv[:, i]]
        prim.append(float(np.median(v1)) if len(v1) else np.nan)
    out["paradas_moda"] = moda
    out["primera_parada"] = prim
    out["rebases_total"] = r["gan"].sum(1).mean()
    return out


def validar(n_sims=400, desde=2024, var=None, din=None, comparar_actual=True, salida=None, verbose=True):
    import modelo_carrera_austin as M
    h = preparar()
    data = pd.read_csv(BASE / "dataset_carrera.csv")
    data = data[data.meeting_key != 1298]
    C = Calibracion(h, data, var)
    ent = data.dropna(subset=["race_pos"])
    pruebas = ent[ent.year >= desde].meeting_key.drop_duplicates().tolist()
    sk_de = dict(zip(h["carreras"].meeting_key, h["carreras"].session_key))
    preds, estr, reb, tot = [], [], [], []
    t0 = time.time()
    for i, mk in enumerate(pruebas):
        obj = ent[ent.meeting_key == mk].reset_index(drop=True)
        cal = C.calibrar(mk, obj)
        pdnf = p_dnf_modelo(data, mk, obj)
        if (var or {}).get("anclar"):
            act = pd.read_csv(WF_ACTUAL)
            obj_m = obj[["driver_number"]].merge(act[act.meeting_key == mk][["driver_number", "pred"]], how="left").pred.values
            anclar(cal, obj, pdnf, obj_m, n_it=ANCLA_IT, eta=ANCLA_ETA, n_sims=ANCLA_SIMS, seed=1000 + i, din=din)
        r = simular(cal, obj, pdnf, n_sims=n_sims, seed=i, din=din, guardar=False)
        rs = resumen_sim(r, obj)
        p = obj[["meeting_key", "driver_number", "year"]].assign(real=obj.race_pos.values, pred=rs.pos_media.values)
        preds.append(p)
        sk = sk_de.get(mk)
        c = h["datos"].get(sk) if sk else None
        if c is not None and not c["mojada"] and c["fit"] is not None:
            # referencia ingenua: mediana de la 1.ª parada (fracción de carrera) en ediciones previas secas del circuito
            prev = h["carreras"][(h["carreras"].fecha < cal["corte"]) & (h["carreras"].circuit_key == cal["circuit_key"])]
            fr_prev = [e["vueltas_parada"][0] / h["datos"][s2]["nv"] for s2 in prev.session_key if s2 in h["datos"]
                       and not h["datos"][s2]["mojada"] for e in h["datos"][s2]["estrategia"].values()
                       if e["termina"] and e["vueltas_parada"]]
            par_prev = [e["paradas"] for s2 in prev.session_key if s2 in h["datos"] and not h["datos"][s2]["mojada"]
                        for e in h["datos"][s2]["estrategia"].values() if e["termina"]]
            v1_base = np.median(fr_prev) * c["nv"] if fr_prev else 0.45 * c["nv"]
            par_base = int(np.median(par_prev)) if par_prev else 1
            for _, x in rs.iterrows():
                dn = x.driver_number
                if dn not in c["drivers"]:
                    continue
                e = c["estrategia"].get(dn)
                j = c["drivers"].index(dn)
                if e and e["termina"] and not any(ev["tipo"] == "RED" for ev in c["eventos"]):
                    v1 = e["vueltas_parada"][0] if e["vueltas_parada"] else np.nan
                    sc_v1 = bool(e["vueltas_parada"]) and (v1 in c["neut"] or v1 - 1 in c["neut"])
                    estr.append({"meeting_key": mk, "driver_number": dn, "par_pred": x.paradas_moda, "par_real": e["paradas"],
                                 "v1_base": v1_base, "par_base": par_base,
                                 "v1_pred": x.primera_parada, "v1_real": v1, "v1_sc": sc_v1})
                reb.append({"meeting_key": mk, "driver_number": dn, "gan_pred": x.gan, "per_pred": x.per,
                            "gan_real": int(c["reb_gan"][j]), "per_real": int(c["reb_per"][j])})
            tot.append({"meeting_key": mk, "pred": float(rs.rebases_total.iloc[0]), "real": int(c["reb_gan"].sum()),
                        "circ": h["carreras"].set_index("meeting_key").circuito.get(mk)})
        if verbose:
            print(f"  {i + 1}/{len(pruebas)} mk={mk} ({time.time() - t0:.0f} s)", end="\r", flush=True)
    if verbose:
        print()
    P = pd.concat(preds)
    res = {"vueltas": M.resumen_metricas(P)}
    base = {"Baseline: orden de qualy": P.assign(pred=ent.set_index(["meeting_key", "driver_number"]).q_pos.reindex(
        pd.MultiIndex.from_frame(P[["meeting_key", "driver_number"]])).fillna(25).values)}
    res["qualy"] = M.resumen_metricas(base["Baseline: orden de qualy"])
    if comparar_actual:
        f_act = WF_ACTUAL
        if f_act.exists():
            pa = {"actual": pd.read_csv(f_act)}
        else:
            pa = M.walk_forward_sim(ent, {"actual": M.MC_VAR}, desde=desde, n_sims=20000)
            f_act.parent.mkdir(parents=True, exist_ok=True)
            pa["actual"].to_csv(f_act, index=False)
        res["actual"] = M.resumen_metricas(pa["actual"])
        P = P.merge(pa["actual"][["meeting_key", "driver_number", "pred"]].rename(columns={"pred": "pred_actual"}),
                    on=["meeting_key", "driver_number"])
        m1 = M.metricas(P, "pred").set_index("meeting_key").ndcg10
        m0 = M.metricas(P.assign(pred=P.pred_actual), "pred").set_index("meeting_key").ndcg10
        dif = (m1 - m0).values
        bs = np.random.default_rng(0).choice(dif, (5000, len(dif))).mean(1)
        res["dif_vs_actual"] = {"media": float(dif.mean()), "ic90": [float(np.percentile(bs, 5)), float(np.percentile(bs, 95))],
                                "gana": int((dif > 0).sum()), "pierde": int((dif < 0).sum())}
        # mezcla (promedio de rangos) como referencia
        Pm = P.assign(pred=P.groupby("meeting_key").pred.rank() + P.groupby("meeting_key").pred_actual.rank())
        res["mezcla_rangos"] = M.resumen_metricas(Pm)
    E = pd.DataFrame(estr)
    if len(E):
        ok = E.dropna(subset=["v1_pred", "v1_real"])
        okv = ok[~ok.v1_sc]
        res["estrategia"] = {
            "n": int(len(E)), "acierto_paradas": float((E.par_pred == E.par_real).mean()),
            "acierto_paradas_base_1": float((E.par_real == 1).mean()),
            "paradas_pred_media": float(E.par_pred.mean()), "paradas_real_media": float(E.par_real.mean()),
            "mae_primera_parada": float((ok.v1_pred - ok.v1_real).abs().mean()),
            "sesgo_primera_parada": float((ok.v1_pred - ok.v1_real).mean()),
            "mae_primera_parada_verde": float((okv.v1_pred - okv.v1_real).abs().mean()),
            "mae_base_mediana_circuito": float((ok.v1_base - ok.v1_real).abs().mean()),
            "acierto_paradas_base_circuito": float((E.par_base == E.par_real).mean()),
        }
    R = pd.DataFrame(reb)
    if len(R):
        from scipy.stats import pearsonr, spearmanr
        R["net_pred"] = R.gan_pred - R.per_pred
        R["net_real"] = R.gan_real - R.per_real
        res["rebases"] = {
            "n": int(len(R)),
            "corr_ganados": float(pearsonr(R.gan_pred, R.gan_real)[0]),
            "corr_perdidos": float(pearsonr(R.per_pred, R.per_real)[0]),
            "corr_netos": float(pearsonr(R.net_pred, R.net_real)[0]),
            "spearman_netos": float(spearmanr(R.net_pred, R.net_real).correlation),
        }
        Tt = pd.DataFrame(tot)
        res["rebases"]["total_pred_medio"] = float(Tt.pred.mean())
        res["rebases"]["total_real_medio"] = float(Tt.real.mean())
        res["rebases"]["corr_total_carrera"] = float(np.corrcoef(Tt.pred, Tt.real)[0, 1])
    if salida:
        P.to_csv(salida, index=False)
    res["tiempo_s"] = round(time.time() - t0)
    return res, P, E, R


# ========================================================================================
# 6) Duelos de estrategia (undercut / overcut): misma definición en datos reales y simulados
# ========================================================================================
X_DUELO = 3.0      # el atacante va a < 3 s detrás antes de la primera de las dos paradas
MAX_DESFASE = 8    # vueltas máximas entre las dos paradas para considerarlo duelo


def duelos_matriz(T, vpar, neut_set, L):
    """T: (n, L+1) tiempos acumulados; vpar: lista por piloto de vueltas de parada; neut_set: vueltas SC/VSC.
    Devuelve lista de dicts (a=atacante, b=defensor, tipo, vuelta, exito, ganancia)."""
    out = []
    n = T.shape[0]
    for q in (0, 1):
        for a in range(n):
            for b in range(n):
                if a == b or len(vpar[a]) <= q or len(vpar[b]) <= q:
                    continue
                la, lb = vpar[a][q], vpar[b][q]
                if la == lb or abs(la - lb) > MAX_DESFASE:
                    continue
                k0 = min(la, lb)
                k1 = max(la, lb) + 1
                if k0 < 3 or k1 > L:
                    continue
                if q == 1 and not (vpar[a][0] < k0 - 1 and vpar[b][0] < k0 - 1):
                    continue
                if any(k in neut_set for k in range(k0 - 1, k1 + 1)):
                    continue
                g0 = T[a, k0 - 1] - T[b, k0 - 1]
                g1 = T[a, k1] - T[b, k1]
                if not (np.isfinite(g0) and np.isfinite(g1)) or not (0 < g0 < X_DUELO) or abs(g1) > 100:
                    continue
                out.append({"a": a, "b": b, "tipo": "undercut" if la < lb else "overcut", "vuelta": k0,
                            "exito": bool(g1 < 0), "ganancia": float(g0 - g1), "desfase": abs(la - lb), "q": q})
    return out


def duelos_reales(h, sks):
    filas = []
    for sk in sks:
        c = h["datos"].get(sk)
        if c is None or c["mojada"]:
            continue
        vpar = [sorted(int(k) for k in np.where(c["IN"][i])[0]) for i in range(len(c["drivers"]))]
        for d in duelos_matriz(c["T"], vpar, set(c["neut"]), c["nv"]):
            d["sk"] = sk
            filas.append(d)
    return pd.DataFrame(filas)


def duelos_sim(r, L, max_sims=None):
    """Duelos en las simulaciones (vectorizado por par)."""
    T = r["T"]
    S, n, _ = T.shape
    if max_sims:
        S = min(S, max_sims)
    vp = r["vuelta_par"][:S]
    neut = r["neut"][:S] > 0
    cneut = np.cumsum(neut, axis=1)
    filas = []
    ar = np.arange(S)
    for q in (0, 1):
        for a in range(n):
            for b in range(n):
                if a == b:
                    continue
                la, lb = vp[:, a, q], vp[:, b, q]
                ok = (la > 0) & (lb > 0) & (la != lb) & (np.abs(la - lb) <= MAX_DESFASE)
                k0 = np.minimum(la, lb)
                k1 = np.maximum(la, lb) + 1
                ok &= (k0 >= 3) & (k1 <= L)
                if q == 1:
                    ok &= (vp[:, a, 0] < k0 - 1) & (vp[:, b, 0] < k0 - 1) & (vp[:, a, 0] > 0) & (vp[:, b, 0] > 0)
                if not ok.any():
                    continue
                k0c, k1c = np.clip(k0, 1, L), np.clip(k1, 1, L)
                hay_neut = (cneut[ar, np.clip(k1c, 0, L + 1)] - cneut[ar, np.clip(k0c - 2, 0, L + 1)]) > 0
                ok &= ~hay_neut
                g0 = T[ar, a, k0c - 1] - T[ar, b, k0c - 1]
                g1 = T[ar, a, k1c] - T[ar, b, k1c]
                ok &= (g0 > 0) & (g0 < X_DUELO) & (np.abs(g1) < 100)
                for s in np.where(ok)[0]:
                    filas.append((s, a, b, q, "undercut" if la[s] < lb[s] else "overcut", int(k0[s]),
                                  bool(g1[s] < 0), float(g0[s] - g1[s])))
    return pd.DataFrame(filas, columns=["sim", "a", "b", "q", "tipo", "vuelta", "exito", "ganancia"])


# ========================================================================================
# 7) Pronóstico del GP objetivo y salidas para la página
# ========================================================================================
def _nombre(full):
    if not isinstance(full, str):
        return None
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in full.split())


def _color(c):
    return c.strip().lstrip("#").upper() if isinstance(c, str) and c.strip() else "888888"


def _r(x, nd=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, nd)


def plan_texto(comp_stint, paradas):
    return "-".join("SMH"[c] for c in comp_stint[:paradas + 1] if c >= 0)


def construir_salidas(r, obj, cal, pdnf, val, n_sims, fuente_parrilla=""):
    L = cal["L"]
    acr = obj.name_acronym.tolist()
    n = len(obj)
    S = r["pos"].shape[0]
    viv = r["vivo"]
    pos = r["pos"]
    media = pos.mean(0)
    rank = pd.Series(media).rank(method="first").astype(int).values
    orden = np.argsort(media)
    colores = [_color(c) for c in obj.team_colour]
    # --- estrategias ---
    estr = []
    for i in range(n):
        planes = pd.Series([plan_texto(r["comp_stint"][s, i], r["paradas"][s, i]) for s in range(S)])
        ok = viv[:, i] & (r["paradas"][:, i] >= 1)
        vc = planes[ok].value_counts(normalize=True)
        top = vc.index[0] if len(vc) else "M-H"
        sel = ok & (planes.values == top)
        npar = int(r["paradas"][sel, i][0]) if sel.any() else 1
        vps = [int(np.median(r["vuelta_par"][sel, i, q])) for q in range(npar)] if sel.any() else []
        alt = [{"plan": p, "paradas": p.count("-"), "prob": _r(v)} for p, v in vc.iloc[1:4].items()]
        estr.append({"acr": acr[i], "nombre": _nombre(obj.full_name.iloc[i]), "equipo": obj.team_name.iloc[i],
                     "color": colores[i], "salida": int(obj.grid.iloc[i]), "plan": top, "paradas": npar,
                     "vueltas_parada": vps, "prob_plan": _r(vc.iloc[0]) if len(vc) else None, "alternativas": alt,
                     "p_paradas": {str(k): _r(((r["paradas"][:, i] == k) & viv[:, i]).sum() / max(viv[:, i].sum(), 1))
                                   for k in (1, 2, 3)},
                     "primera_parada_p10_p90": [int(np.percentile(r["vuelta_par"][ok, i, 0], 10)),
                                                int(np.percentile(r["vuelta_par"][ok, i, 0], 90))] if ok.any() else None})
    estr = [estr[i] for i in orden]
    # --- rebases en pista ---
    reb = {"total_esperado": _r(r["gan"].sum(1).mean(), 1),
           "total_p10_p90": [int(np.percentile(r["gan"].sum(1), 10)), int(np.percentile(r["gan"].sum(1), 90))],
           "por_piloto": sorted([{"acr": acr[i], "ganados": _r(r["gan"][:, i].mean(), 2), "perdidos": _r(r["per"][:, i].mean(), 2),
                                  "netos": _r(r["gan"][:, i].mean() - r["per"][:, i].mean(), 2),
                                  "vuelta1_netos": _r((obj.grid.values[i] - r["pos1"][:, i]).mean(), 2)} for i in range(n)],
                                key=lambda x: -x["netos"]),
           "nota": "Rebases en pista con bandera verde desde la vuelta 2 (no cuentan cambios por paradas ni la vuelta 1; "
                   "vuelta1_netos = lugares ganados en la arrancada)."}
    # --- duelos ---
    Dd = duelos_sim(r, L)
    duelos = []
    if len(Dd):
        g = Dd.groupby(["a", "b", "tipo"]).agg(n=("exito", "size"), exito=("exito", "mean"), vuelta=("vuelta", "median"),
                                               gan=("ganancia", "mean")).reset_index()
        g["prob"] = g.n / S
        top_pos = set(orden[:14]) | {acr.index(x) for x in ("LAW", "PIA") if x in acr}
        g = g[g.a.isin(top_pos) | g.b.isin(top_pos)]
        g["rel"] = g.prob * (1 + (g.a.map(lambda i: rank[i]) <= 10))
        # que aparezcan también los duelos más probables de pilotos de interés (p. ej. LAW y PIA)
        for interes in ("LAW", "PIA"):
            if interes in acr:
                ii = acr.index(interes)
                sub = g[(g.a == ii) | (g.b == ii)]
                if len(sub):
                    g.loc[sub.prob.idxmax(), "rel"] += 1.0
        g = g.sort_values("rel", ascending=False)
        # [verificación] éxito calibrado con la validación walk-forward (tasa real / simulada por tipo de duelo):
        # el overcut sale sobrestimado (≈0.20 simulado vs ≈0.12 real). prob_exito_sim conserva el valor crudo.
        dv = val.get("duelos", {}) if isinstance(val, dict) else {}
        fac = {}
        for t_ in ("undercut", "overcut"):
            try:
                fac[t_] = float(dv["real"][t_]["mean"]) / float(dv["sim"][t_]["mean"])
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                fac[t_] = 1.0
        # [verificación] antes se deduplicaba por par (a, b) y el undercut del mismo par tapaba siempre al overcut
        # (salían 0 overcuts); ahora hasta 10 undercuts y 4 overcuts, cada uno con su par y tipo.
        cupo = {"undercut": 10, "overcut": 4}
        vistos = set()
        for _, x in g.iterrows():
            par_ = (int(x.a), int(x.b), x.tipo)
            if par_ in vistos or x.prob < 0.02 or cupo.get(x.tipo, 0) <= 0:
                continue
            vistos.add(par_)
            cupo[x.tipo] -= 1
            a_, b_ = acr[int(x.a)], acr[int(x.b)]
            p_ex = float(np.clip(x.exito * fac.get(x.tipo, 1.0), 0, 1))
            if x.tipo == "undercut":
                nota = (f"{a_} para antes que {b_} estando a < 3 s (pasa en {x.prob * 100:.0f}% de las carreras); "
                        f"le sale {p_ex * 100:.0f}% de las veces")
            else:
                nota = (f"{a_} se queda fuera más vueltas que {b_} estando a < 3 s detrás (pasa en {x.prob * 100:.0f}% de "
                        f"las carreras); lo rebasa por estrategia {p_ex * 100:.0f}% de las veces")
            duelos.append({"ataca": a_, "defiende": b_, "tipo": x.tipo, "vuelta": int(round(x.vuelta)),
                           "prob_exito": _r(p_ex), "prob_exito_sim": _r(x.exito), "ganancia_s": _r(x.gan, 2),
                           "prob_ocurre": _r(x.prob), "nota": nota})
            if len(duelos) >= 14:
                break
        duelos.sort(key=lambda d: -d["prob_ocurre"])
        tot_d = Dd.groupby("tipo").agg(n=("exito", "size"), exito=("exito", "mean"))
    # --- trazas: posición mediana al final de cada vuelta ---
    T = r["T"]
    trazas = []
    posk = T[:, :, 1:].argsort(1).argsort(1) + 1             # (S, n, L)
    # [verificación] la mediana por piloto no es un orden (al final nadie quedaba P1, HAM terminaba P2 siendo el
    # favorito y 4 autos compartían P10): 'posiciones' = orden por posición media en cada vuelta (permutación 1..n,
    # en la última vuelta coincide con orden_final); la mediana cruda queda en 'posiciones_mediana'.
    rk_media = posk.mean(0).argsort(0, kind="stable").argsort(0, kind="stable") + 1      # (n, L)
    for i in orden:
        trazas.append({"acr": acr[i], "color": colores[i], "salida": int(obj.grid.iloc[i]),
                       "posiciones": [int(x) for x in rk_media[i]],
                       "posiciones_mediana": [int(round(x)) for x in np.median(posk[:, i, :], axis=0)],
                       "p25": [int(round(x)) for x in np.percentile(posk[:, i, :], 25, axis=0)][::5],
                       "p75": [int(round(x)) for x in np.percentile(posk[:, i, :], 75, axis=0)][::5]})
    # --- safety car ---
    ne = r["neut"][:, 1:L + 1]
    p_sc = float((ne == 1).any(1).mean())
    p_vsc = float((ne == 2).any(1).mean())
    inicio = (ne > 0) & ~np.c_[np.zeros((S, 1), bool), ne[:, :-1] > 0]
    pk = inicio.mean(0)
    # las 2 últimas vueltas se omiten: efecto de recorte de la simulación (en México se quitó la v70 a mano)
    tipicas = [int(k + 1) for k in np.argsort(-pk)[:3] if k + 1 < L - 1]
    tramos = {}
    for a, b in ((1, 5), (6, 25), (26, 50), (51, L)):
        tramos[f"v{a}-{b}"] = _r(float(inicio[:, a - 1:b].any(1).mean()))
    sc = {"prob": _r(float((ne > 0).any(1).mean())), "prob_sc": _r(p_sc), "prob_vsc": _r(p_vsc),
          "vueltas_tipicas": sorted(tipicas), "prob_por_tramo": tramos,
          "nota": (f"SC en la vuelta 1: {cal['sc_p1'] * 100:.0f}%; después {cal['sc_por_carrera']:.2f} SC y "
                   f"{cal['vsc_por_carrera']:.2f} VSC esperados por carrera ({CTX['lugar']} {cal['sc_circ_eventos']} neutralizaciones en "
                   f"{cal['sc_circ_n']} ediciones {'2023-2025' if CTX['meeting'] == 1298 else 'anteriores (OpenF1)'}, contraído hacia la tasa global). Con SC la parada cuesta "
                   f"≈{cal['pit'] * cal['pit_ratio_sc']:.0f} s en lugar de ≈{cal['pit']:.0f} s.")}
    # --- orden final ---
    p_dnf_sim = 1 - viv.mean(0)
    of = []
    for i in orden:
        of.append({"acr": acr[i], "pred": int(rank[i]), "pos_media": _r(media[i], 2), "p_win": _r((pos[:, i] == 1).mean()),
                   "p_podio": _r((pos[:, i] <= 3).mean()), "p_top10": _r((pos[:, i] <= 10).mean()), "p_dnf": _r(p_dnf_sim[i]),
                   "salida": int(obj.grid.iloc[i]), "p10": int(np.percentile(pos[:, i], 10)), "p90": int(np.percentile(pos[:, i], 90))})
    return {"estrategias": estr, "rebases": reb, "duelos": duelos, "trazas": trazas, "safety_car": sc, "orden_final": of,
            "rank": rank, "media": media, "duelos_tabla": Dd}


def dispersion(var=None, din=None, n_sims=300, sks=None):
    """Calibración de la dispersión con carreras de 2023 (anteriores a todo el periodo de prueba):
    |final - salida| medio y Spearman(salida, final) reales vs simulados."""
    from scipy.stats import spearmanr
    h = preparar()
    data = pd.read_csv(BASE / "dataset_carrera.csv")
    C = Calibracion(h, data, var)
    car = h["carreras"]
    if sks is None:
        sks = car[(car.year == 2023) & car.tiene_vueltas].session_key.tolist()[8:]
    filas = []
    for i, sk in enumerate(sks):
        mk = car.set_index("session_key").meeting_key[sk]
        obj = data[(data.meeting_key == mk)].dropna(subset=["race_pos"]).reset_index(drop=True)
        if obj.empty:
            continue
        cal = C.calibrar(mk, obj)
        r = simular(cal, obj, p_dnf_modelo(data, mk, obj), n_sims=n_sims, seed=100 + i, din=din, guardar=False)
        g = obj.grid.values
        fin = r["vivo"]
        sim_abs = np.mean([np.abs(r["pos"][s][fin[s]] - g[fin[s]]).mean() for s in range(n_sims)])
        sim_sp = np.mean([spearmanr(g, r["pos"][s]).correlation for s in range(0, n_sims, 3)])
        term = obj.status.isin(["Finished", "Lapped"]) | obj.status.str.contains("Lap", na=False)
        real_abs = np.abs(obj.race_pos[term] - g[term]).mean()
        real_sp = spearmanr(g, obj.race_pos).correlation
        planes = [[plan_texto(r["comp_stint"][s, i], r["paradas"][s, i]) for i in range(len(obj)) if r["vivo"][s, i]]
                  for s in range(0, n_sims, 4)]
        moda = np.mean([pd.Series(p).value_counts(normalize=True).iloc[0] for p in planes if len(p) > 5])
        pole = int(np.argmin(g))
        gr = pd.Series(g).rank(method="first").values
        extra = {}
        fr_ev = []
        for s_ in range(0, n_sims, 2):
            ne = r["neut"][s_]
            k_ = 3
            while k_ <= cal["L"]:
                if ne[k_] > 0 and ne[k_ - 1] == 0:
                    j_ = k_
                    while j_ <= cal["L"] and ne[j_] > 0:
                        j_ += 1
                    ks = np.arange(k_, j_)
                    al = [i for i in range(len(obj)) if r["vivo"][s_, i]]
                    fr_ev.append(np.mean([np.isin(r["vuelta_par"][s_, i], ks).any() for i in al]))
                    k_ = j_
                k_ += 1
        extra["sim_sc_frac_media"] = float(np.mean(fr_ev)) if fr_ev else np.nan
        extra["sim_sc_frac_var"] = float(np.var(fr_ev)) if fr_ev else np.nan
        for nom_b, (a, b) in {"b1": (1, 1), "b2_3": (2, 3), "b4_6": (4, 6), "b7_10": (7, 10)}.items():
            m = (gr >= a) & (gr <= b)
            extra["sim_" + nom_b] = np.nanmean([np.abs(r["pos"][s][fin[s] & m] - gr[fin[s] & m]).mean()
                                                 for s in range(n_sims) if (fin[s] & m).any()])
            mm = m & term.values
            extra["real_" + nom_b] = float(np.abs(obj.race_pos.values[mm] - gr[mm]).mean()) if mm.any() else np.nan
        extra["sim_pole_win"] = float((r["pos"][:, int(np.argmin(gr))] == 1).mean())
        # recuperación de autos fuera de su sitio (salen >= 5 lugares detrás de su rango de ritmo esperado)
        rk = pd.Series(cal["ritmo_mu"]).rank(method="first").values
        fuera = (gr - rk >= 5)
        if fuera.any():
            extra["sim_recupera"] = float(np.nanmean([(gr[fin[s] & fuera] - r["pos"][s][fin[s] & fuera]).mean()
                                                      for s in range(n_sims) if (fin[s] & fuera).any()]))
            mm = fuera & term.values
            extra["real_recupera"] = float((gr[mm] - obj.race_pos.values[mm]).mean()) if mm.any() else np.nan
            extra["n_fuera"] = int(mm.sum())
        extra["real_pole_win"] = float(obj.race_pos.values[int(np.argmin(gr))] == 1)
        filas.append({**extra, "sk": sk, "moda_plan": moda, "pole_v1": float((r["pos1"][:, pole] == 1).mean()),
                      "par_media": float(r["paradas"][r["vivo"]].mean()), "sim_abs": sim_abs, "real_abs": real_abs, "sim_sp": sim_sp, "real_sp": real_sp,
                      "sim_reb": r["gan"].sum(1).mean(), "real_reb": int(h["datos"][sk]["reb_gan"].sum())})
    return pd.DataFrame(filas)


# ========================================================================================
# 8) Main
# ========================================================================================
VAR_OFICIAL = {"sd_ritmo_k": 0.7, "d_k": 1.0, "reb_shift": -0.5, "rho_plan": 0.4, "par_comun": True, "rho_sc": 0.9,
               "plan_neutral": 1.0, "conf_pos": True}
DIN_OFICIAL = {}
SCRATCH_CARRERA = Path("/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/vueltas")
VAL_JSON = BASE / "validacion_vueltas.json"


def resumen_texto(sal, obj, cal):
    """3-4 frases en español de México."""
    of = sal["orden_final"]
    fav = of[0]
    nom = dict(zip(obj.name_acronym, obj.full_name.map(_nombre)))
    podio = ", ".join(x["acr"] for x in of[:3])
    est = sal["estrategias"]
    planes = pd.Series([e["plan"] for e in est]).value_counts()
    p1 = np.mean([e["p_paradas"]["1"] or 0 for e in est])
    v1 = int(np.median([e["vueltas_parada"][0] for e in est if e["vueltas_parada"]]))
    r1 = (f"El simulador vuelta a vuelta pone a {nom[fav['acr']]} como favorito ({fav['p_win'] * 100:.0f}% de ganar) "
          f"y el podio más probable es {podio}.")
    d_uc = [d for d in sal["duelos"] if d["tipo"] == "undercut"]
    r2 = (f"Lo más probable es una sola parada ({p1 * 100:.0f}% de las carreras; plan más común {planes.index[0]}) hacia la "
          f"vuelta {v1}, con ≈{cal['pit']:.0f} s perdidos en pits")
    if d_uc:
        d = d_uc[0]
        r2 += (f", y el undercut más probable es el de {d['ataca']} sobre {d['defiende']} cerca de la vuelta {d['vuelta']} "
               f"(le funciona {d['prob_exito'] * 100:.0f}% de las veces)")
    d_oc = [d for d in sal["duelos"] if d["tipo"] == "overcut" and d.get("prob_exito") is not None]
    if d_oc:
        r2 += (f"; quedarse fuera más vueltas (overcut) casi nunca paga en {CTX['lugar']} "
               f"(≈{np.mean([d['prob_exito'] for d in d_oc]) * 100:.0f}% de éxito)")
    r2 += "."
    law = next((x for x in of if x["acr"] == "LAW"), None) if CTX["meeting"] == 1298 else None
    r3 = ""
    if CTX["meeting"] != 1298:            # genérico: la mayor remontada desde el fondo de la parrilla
        cand = [x for x in of if x["salida"] >= 12 and x["salida"] - x["pred"] >= 3]
        if cand:
            x = max(cand, key=lambda x: x["salida"] - x["pred"])
            reb = next((y for y in sal["rebases"]["por_piloto"] if y["acr"] == x["acr"]), {"ganados": 0})
            r3 = (f"{nom[x['acr']]} arranca {x['salida']}.º y remonta hasta el {x['pred']}.º lugar (posición media "
                  f"{x['pos_media']:.1f}; {x['p_top10'] * 100:.0f}% de llegar a puntos), con unos {reb['ganados']:.0f} rebases en pista.")
    if law:
        reb = next(x for x in sal["rebases"]["por_piloto"] if x["acr"] == "LAW")
        r3 = (f"Lawson, descalificado de la qualy, arranca 22.º y remonta hasta el {law['pred']}.º lugar (posición media {law['pos_media']:.1f}; "
              f"{law['p_top10'] * 100:.0f}% de llegar a puntos), con unos {reb['ganados']:.0f} rebases en pista.")
    r4 = f"Hay safety car o VSC en {sal['safety_car']['prob'] * 100:.0f}% de las carreras simuladas."
    return " ".join(x for x in (r1, r2, r3, r4) if x)


def objetivo_actual(obj, meeting=1298, ruta=None):
    """Posición media por piloto del simulador actual (pronóstico oficial publicado: prediccion_carrera_<slug>_2026.csv)."""
    f = Path(ruta) if ruta else BASE / "prediccion_carrera_mexico_2026.csv"
    pc = pd.read_csv(f).set_index("name_acronym")
    return obj.name_acronym.map(pc.pos_media).values, f.name


def pronostico(meeting=1298, n_sims=4000, var=None, din=None, escribir_carrera=False, seed=2026,
               dataset=None, objetivo=None, salida=None, lugar=None, ancla_it=None):
    """dataset/objetivo/salida: rutas (default México: dataset_carrera.csv, prediccion_carrera_mexico_2026.csv,
    web_mexico/datos_vueltas.json). lugar: nombre corto del GP para los textos."""
    CTX["meeting"], CTX["lugar"] = meeting, (lugar or ("México" if meeting == 1298 else "este circuito"))
    h = preparar()
    data = pd.read_csv(dataset or (BASE / "dataset_carrera.csv"))
    var = VAR_OFICIAL if var is None else var
    din = DIN_OFICIAL if din is None else din
    obj = data[data.meeting_key == meeting].sort_values("grid").reset_index(drop=True)
    # sólo GPs anteriores (al reproducir un GP pasado el dataset ya trae carreras posteriores)
    hist = data[(data.meeting_key != meeting) & (pd.to_datetime(data.date, utc=True) < pd.to_datetime(obj.date, utc=True).min())]
    C = Calibracion(h, hist, var)
    cal = C.calibrar(meeting, obj)
    pdnf = p_dnf_modelo(hist, meeting, obj)
    val = json.loads(VAL_JSON.read_text()) if VAL_JSON.exists() else {}
    modo = val.get("modo_oficial", "anclado")
    t0 = time.time()
    # 1) libre: ritmo sólo desde variables pre-carrera
    r_libre = simular(cal, obj, pdnf, n_sims=n_sims, seed=seed, din=din)
    media_libre = r_libre["pos"].mean(0)
    # 2) anclado: ritmo efectivo ajustado para reproducir la posición media del simulador oficial
    cal_a = dict(cal)
    cal_a["ritmo_mu"] = cal["ritmo_mu"].copy()
    tgt, fuente_tgt = objetivo_actual(obj, meeting, objetivo)
    anclar(cal_a, obj, pdnf, tgt, n_it=ancla_it or ANCLA_IT, eta=ANCLA_ETA, n_sims=ANCLA_SIMS, seed=seed + 1, din=din)
    r_anc = simular(cal_a, obj, pdnf, n_sims=n_sims, seed=seed, din=din)
    print(f"{2 * n_sims} carreras simuladas (+ anclaje) en {time.time() - t0:.0f} s")
    r, cal_u = (r_anc, cal_a) if modo == "anclado" else (r_libre, cal)
    sal = construir_salidas(r, obj, cal_u, pdnf, val, n_sims)
    vo = val.get("resumen_doc", {})
    orden_libre = [{"acr": obj.name_acronym[i], "pred": int(k + 1), "pos_media": _r(media_libre[i], 2),
                    "p_win": _r((r_libre["pos"][:, i] == 1).mean()), "p_top10": _r((r_libre["pos"][:, i] <= 10).mean())}
                   for k, i in enumerate(np.argsort(media_libre))]
    planes = pd.Series([plan_texto(r["comp_stint"][s_, i], r["paradas"][s_, i]) for s_ in range(0, n_sims, 4)
                        for i in range(len(obj)) if r["vivo"][s_, i]]).value_counts(normalize=True)
    doc = {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_sims": int(n_sims), "vueltas": int(cal["L"]),
        "modelo": ("Simulador vuelta a vuelta (Monte Carlo, " + ("anclado al simulador oficial" if modo == "anclado" else "libre") +
                   "): ritmo de carrera por piloto, degradación y offset por compuesto, combustible, pits (pérdida del circuito, "
                   "plan óptimo + ruido calibrado, undercut, cubrir, paradas con SC/VSC), rebases en pista por diferencia de ritmo e "
                   "intervalo, vuelta 1, SC/VSC y abandonos; calibrado con " + (
                       "84 carreras 2023-2026" if meeting == 1298 else f"{cal['n_train']} carreras anteriores") + " de OpenF1."),
        "modo": modo,
        "nota_modo": ("anclado = el ritmo efectivo de cada piloto se ajusta para que su posición media coincida con la del simulador "
                      "oficial (" + fuente_tgt + "); las estrategias, rebases, duelos, SC y trazas salen del modelo vuelta a vuelta. "
                      "orden_final_libre = mismo simulador con el ritmo sólo de prácticas/qualy/forma (validó peor)."),
        "validacion": vo,
        "parametros": {"perdida_pit_s": _r(cal["pit"], 1), "perdida_pit_sc_s": _r(cal["pit"] * cal["pit_ratio_sc"], 1),
                       "deg_s_vuelta": {c: _r(x, 3) for c, x in zip("SMH", cal["deg"])},
                       "offset_s": {c: _r(x, 2) for c, x in zip("SMH", cal["off"])},
                       "combustible_s_vuelta": _r(cal["fuel"], 3), "max_stint": {c: int(x) for c, x in zip("SMH", cal["maxlen"])},
                       "ritmo_ref_s": _r(cal["ref"], 2), "prob_rebase_circuito_vs_global": _r(np.exp(cal.get("reb_off_circ", cal["reb_off"])), 2),
                       "planes_carrera": [{"plan": p, "prob": _r(v)} for p, v in planes.head(8).items()],
                       "ritmo_s_vuelta": {obj.name_acronym[i]: _r(cal_u["ritmo_mu"][i], 3) for i in range(len(obj))},
                       "ritmo_libre_s_vuelta": {obj.name_acronym[i]: _r(cal["ritmo_mu"][i], 3) for i in range(len(obj))},
                       "nota_ritmo": "s/vuelta vs la mediana del campo; ritmo_s_vuelta es el usado en el modo oficial"},
        "estrategias": sal["estrategias"], "rebases": sal["rebases"], "duelos": sal["duelos"], "trazas": sal["trazas"],
        "safety_car": sal["safety_car"], "orden_final": sal["orden_final"], "orden_final_libre": orden_libre,
        "nota_trazas": ("posiciones = orden de los pilotos por su posición media en las simulaciones al final de cada vuelta "
                        "(una posición por piloto; en la vuelta " + str(int(cal["L"])) + " coincide con orden_final). posiciones_mediana = mediana "
                        "por piloto (puede repetir lugares); p25/p75 cada 5 vueltas."),
        "nota_duelos": ("Duelo = el de atrás va a < 3 s y las dos paradas quedan a ≤ 8 vueltas, sin SC/VSC de por medio. "
                        "prob_exito está calibrada con la validación 2024-2026 (éxito real/simulado por tipo: el overcut "
                        "crudo sale sobrestimado, ≈20% vs ≈12% real); prob_exito_sim es el valor crudo del simulador. "
                        "La probabilidad por par no supera a la tasa general del tipo de duelo (Brier "
                        f"{val.get('duelos', {}).get('brier_sim', float('nan')):.3f} vs "
                        f"{val.get('duelos', {}).get('brier_tasa_por_tipo', float('nan')):.3f})."),
    }
    doc["resumen"] = resumen_texto(sal, obj, cal_u)
    ruta = Path(salida) if salida else BASE / "web_mexico" / "datos_vueltas.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print("Escrito", ruta)
    if escribir_carrera and not val.get("mejor_o_igual_que_actual", False):
        print("No se escribe datos_carrera_vueltas.json: el vuelta a vuelta no validó mejor o igual que el simulador actual "
              "(ver validacion_vueltas.json).")
    elif escribir_carrera:
        dc = doc_forma_carrera(sal, obj, cal_u, pdnf, val.get("resumen_doc", {}), n_sims, modo)
        SCRATCH_CARRERA.mkdir(parents=True, exist_ok=True)
        f = SCRATCH_CARRERA / "datos_carrera_vueltas.json"
        f.write_text(json.dumps(dc, ensure_ascii=False, indent=1))
        print("Escrito", f)
    return doc, sal, r, cal_u, obj


def doc_forma_carrera(sal, obj, cal, pdnf, vo, n_sims, modo="anclado"):
    """Misma forma que web_mexico/datos_carrera.json (doc carrera/mexico2026)."""
    prev = json.loads((BASE / "web_mexico" / "datos_carrera.json").read_text())
    viejo = {p["acr"]: p for p in prev.get("pilotos", [])}
    est = {e["acr"]: e for e in sal["estrategias"]}
    pil = []
    for x in sal["orden_final"]:
        i = obj.index[obj.name_acronym == x["acr"]][0]
        r = obj.loc[i]
        mov = r.grid - x["pred"]
        nota = ("favorito" if x["pred"] == 1 else "remonta" if mov >= 3 else "pierde posiciones" if mov <= -3 else "")
        pil.append({"acr": x["acr"], "nombre": _nombre(r.full_name), "equipo": r.team_name, "color": _color(r.team_colour),
                    "salida": int(r.grid), "pred": x["pred"], "pos_media": x["pos_media"], "p_win": x["p_win"],
                    "p_podio": x["p_podio"], "p_top10": x["p_top10"], "p_dnf": x["p_dnf"], "p10": x["p10"], "p90": x["p90"],
                    "ritmo_rank": int(pd.Series(cal["ritmo_mu"]).rank(method="first")[i]),
                    "deg_s_vuelta": viejo.get(x["acr"], {}).get("deg_s_vuelta"), "paradas": est[x["acr"]]["paradas"],
                    "plan": est[x["acr"]]["plan"], "nota": nota})
    return {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modelo": (f"Simulador vuelta a vuelta ({n_sims} carreras simuladas: ritmo, neumáticos, pits/undercut, rebases, SC/VSC, "
                   f"abandonos" + ("; ritmo efectivo anclado al simulador oficial)" if modo == "anclado" else ")")),
        "validacion": {k: vo.get(k) for k in ("ndcg10", "top10_hits", "win_acc", "podium_hits", "n_gp")},
        "parrilla_fuente": prev.get("parrilla_fuente"),
        "vueltas": int(cal["L"]),
        "estrategia": {"paradas_tipicas": 1.0, "perdida_pit_s": _r(cal["pit"], 1),
                       "nota": "Plan y paradas por piloto del simulador vuelta a vuelta (plan más probable)."},
        "pilotos": pil,
        "resumen": resumen_texto(sal, obj, cal),
    }


def validar_duelos(n_sims=300, desde=2024, var=None, din=None, verbose=False):
    """Walk-forward de los duelos de estrategia: tasa de éxito simulada vs real del undercut/overcut, y calibración
    de prob_exito por par (cuando el duelo real ocurrió y el par también aparece en las simulaciones)."""
    h = preparar()
    data = pd.read_csv(BASE / "dataset_carrera.csv")
    data = data[data.meeting_key != 1298]
    C = Calibracion(h, data, var)
    ent = data.dropna(subset=["race_pos"])
    pruebas = ent[ent.year >= desde].meeting_key.drop_duplicates().tolist()
    sk_de = dict(zip(h["carreras"].meeting_key, h["carreras"].session_key))
    sim_tot, real_tot, pares = [], [], []
    for i, mk in enumerate(pruebas):
        sk = sk_de.get(mk)
        c = h["datos"].get(sk) if sk else None
        if c is None or c["mojada"]:
            continue
        obj = ent[ent.meeting_key == mk].reset_index(drop=True)
        cal = C.calibrar(mk, obj)
        r = simular(cal, obj, p_dnf_modelo(data, mk, obj), n_sims=n_sims, seed=500 + i, din=din)
        Ds = duelos_sim(r, cal["L"])
        Ds["mk"] = mk
        sim_tot.append(Ds)
        vpar = [sorted(int(k) for k in np.where(c["IN"][j])[0]) for j in range(len(c["drivers"]))]
        Dr = pd.DataFrame(duelos_matriz(c["T"], vpar, set(c["neut"]), c["nv"]))
        if len(Dr):
            num = {j: c["drivers"][j] for j in range(len(c["drivers"]))}
            idx = {dn: j for j, dn in enumerate(obj.driver_number)}
            Dr["a_o"] = Dr.a.map(lambda j: idx.get(num[j], -1))
            Dr["b_o"] = Dr.b.map(lambda j: idx.get(num[j], -1))
            Dr["mk"] = mk
            real_tot.append(Dr)
            g = Ds.groupby(["a", "b", "tipo"]).exito.agg(["mean", "size"])
            for _, d in Dr.iterrows():
                clave = (d.a_o, d.b_o, d.tipo)
                if clave in g.index and g.loc[clave, "size"] >= 5:
                    pares.append({"tipo": d.tipo, "real": int(d.exito), "p_sim": float(g.loc[clave, "mean"])})
        if verbose:
            print(f"  duelos {i + 1}/{len(pruebas)}", end="\r", flush=True)
    S = pd.concat(sim_tot)
    R = pd.concat(real_tot)
    Pp = pd.DataFrame(pares)
    out = {"n_gp": int(R.mk.nunique()),
           "real": R.groupby("tipo").exito.agg(["mean", "size"]).round(3).to_dict("index"),
           "sim": S.groupby("tipo").exito.agg(["mean", "size"]).round(3).to_dict("index"),
           "duelos_por_carrera_real": float(len(R) / R.mk.nunique()),
           "duelos_por_carrera_sim": float(len(S) / n_sims / S.mk.nunique())}
    if len(Pp):
        base = Pp.groupby("tipo").real.transform("mean")
        out["brier_sim"] = float(((Pp.p_sim - Pp.real) ** 2).mean())
        out["brier_tasa_por_tipo"] = float(((base - Pp.real) ** 2).mean())
        out["n_pares"] = int(len(Pp))
        out["acierto_sim"] = float(((Pp.p_sim > 0.5) == (Pp.real == 1)).mean())
    return out


VARIANTES_PROBADAS = [
    # walk-forward 2024-2026 completo (66 GP). Se miraron sus resultados al pasar de una a otra: sesgo de selección declarado.
    ("v1", "base: ruido de ritmo = sd de residuos, rebases sin escalar (300 carreras/GP)", 0.8758),
    ("v2", "ruido de ritmo MAD x0.7 y pendiente de rebase x0.6 (calibrados en 2023-2S, fuera de la prueba)", 0.8775),
    ("v3", "+ plan de carrera compartido (rho 0.4) + vuelta 1 con P(pole sigue 1.º)", 0.8745),
    ("v4", "+ ruido de parada común/propio, cubrir por posición, paradas con SC por tabla histórica, relanzamientos", 0.8793),
    ("v4 anclado", "v4 con ritmo efectivo anclado al simulador oficial (300 carreras/GP)", 0.8834),
    ("v4b", "+ indicador de pole en el modelo de ritmo (2000 carreras/GP)", 0.8758),
    ("v4b anclado", "v4b anclado (2000 carreras/GP)", 0.8845),
    ("v5", "+ decisiones correlacionadas bajo SC (rho 0.9), planes casi equivalentes, conformidad por posición", 0.8791),
    ("v6 libre (final)", "pendiente de rebase sin escalar y menor intercepto (-0.5) para igualar rebases totales en 2023-2S", None),
    ("v6 anclado (final)", "v6 anclado al simulador oficial (2000 carreras/GP)", None),
]


def escribir_validacion(res_libre, res_anc, duelos, n_sims):
    """Arma validacion_vueltas.json y decide el modo oficial (anclado o libre) por NDCG@10."""
    modo = "anclado" if res_anc["vueltas"]["ndcg10"] >= res_libre["vueltas"]["ndcg10"] else "libre"
    ro = res_anc if modo == "anclado" else res_libre
    dif = ro.get("dif_vs_actual", {})
    empate = bool(dif and dif["ic90"][0] <= 0 <= dif["ic90"][1])
    mejor_o_igual = bool(dif and (dif["media"] >= 0 or empate))
    var = [{"variante": a, "cambio": b, "ndcg10": c} for a, b, c in VARIANTES_PROBADAS]
    var[-2]["ndcg10"] = round(res_libre["vueltas"]["ndcg10"], 4)
    var[-1]["ndcg10"] = round(res_anc["vueltas"]["ndcg10"], 4)

    def m(r):
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
    doc = {
        "protocolo": (f"Walk-forward 2024-2026 ({ro['vueltas']['n_gp']} GP): cada GP se calibra sólo con carreras anteriores "
                      f"(corte por inicio del fin de semana) y se simulan {n_sims} carreras; métricas por GP promediadas. "
                      "El simulador actual se evalúa en los mismos GP con 20 000 carreras."),
        "modo_oficial": modo,
        "vueltas_libre": m(res_libre["vueltas"]), "vueltas_anclado": m(res_anc["vueltas"]),
        "actual": m(res_libre["actual"]), "orden_qualy": m(res_libre["qualy"]),
        "dif_vs_actual_libre": res_libre.get("dif_vs_actual"), "dif_vs_actual_anclado": res_anc.get("dif_vs_actual"),
        "mejor_o_igual_que_actual": mejor_o_igual,
        "estrategia": m(ro["estrategia"]), "rebases": m(ro["rebases"]), "duelos": duelos,
        "variantes_probadas": var,
        "nota": ("Ajustes de ruido de ritmo, sensibilidad de rebase, conformidad de plan y vuelta 1 calibrados con 13 carreras de la "
                 "2.ª mitad de 2023 (fuera del periodo de prueba) igualando dispersión de posiciones, rebases totales, plan modal y "
                 "paradas bajo SC (~20 configuraciones probadas ahí); las 10 corridas v1-v6 se compararon mirando este walk-forward "
                 "(sesgo de selección declarado). "
                 "El modo anclado usa como objetivo la posición media del simulador oficial, así que su orden no es independiente "
                 "de él: lo nuevo son estrategias, rebases, duelos, SC y trazas."),
    }
    vo = res_anc["vueltas"] if modo == "anclado" else res_libre["vueltas"]
    resumen_doc = {"ndcg10": round(vo["ndcg10"], 4), "ndcg10_2024": round(vo["ndcg10_2024"], 4),
                   "ndcg10_2025": round(vo["ndcg10_2025"], 4), "ndcg10_2026": round(vo["ndcg10_2026"], 4),
                   "top10_hits": round(vo["top10_hits"], 2), "win_acc": round(vo["win_acc"], 3),
                   "podium_hits": round(vo["podium_hits"], 2), "n_gp": int(vo["n_gp"]), "modo": modo,
                   "ndcg10_libre": round(res_libre["vueltas"]["ndcg10"], 4),
                   "ndcg10_actual": round(res_libre["actual"]["ndcg10"], 4),
                   "ndcg10_orden_qualy": round(res_libre["qualy"]["ndcg10"], 4),
                   "paradas_acierto": round(ro["estrategia"]["acierto_paradas"], 3),
                   "paradas_acierto_base_todos_1": round(ro["estrategia"]["acierto_paradas_base_1"], 3),
                   "primera_parada_mae_vueltas": round(ro["estrategia"]["mae_primera_parada"], 2),
                   "primera_parada_mae_base_circuito": round(ro["estrategia"]["mae_base_mediana_circuito"], 2),
                   "rebases_corr_netos": round(ro["rebases"]["corr_netos"], 3),
                   "rebases_total_pred_vs_real": [round(ro["rebases"]["total_pred_medio"], 1), round(ro["rebases"]["total_real_medio"], 1)],
                   "undercut_exito_sim_vs_real": [duelos.get("sim", {}).get("undercut", {}).get("mean"),
                                                  duelos.get("real", {}).get("undercut", {}).get("mean")],
                   "overcut_exito_sim_vs_real": [duelos.get("sim", {}).get("overcut", {}).get("mean"),
                                                 duelos.get("real", {}).get("overcut", {}).get("mean")],
                   "dif_ndcg10_vs_actual": round(dif.get("media", float("nan")), 4) if dif else None,
                   "dif_ic90": [round(x, 4) for x in dif["ic90"]] if dif else None,
                   "ndcg10_por_año": {"anclado": [round(res_anc["vueltas"][f"ndcg10_{y}"], 4) for y in (2024, 2025, 2026)],
                                      "libre": [round(res_libre["vueltas"][f"ndcg10_{y}"], 4) for y in (2024, 2025, 2026)],
                                      "actual": [round(res_libre["actual"][f"ndcg10_{y}"], 4) for y in (2024, 2025, 2026)],
                                      "orden_qualy": [round(res_libre["qualy"][f"ndcg10_{y}"], 4) for y in (2024, 2025, 2026)]},
                   "nota": ("Walk-forward 2024-2026: el modo anclado empata con el simulador oficial dentro del ruido (IC90 de la "
                            "diferencia por GP toca 0) pero acierta menos ganadores; el libre queda por debajo del oficial y apenas "
                            "arriba del orden de qualy. Estrategia: acierta el número de paradas más que 'todos a 1 parada' y la "
                            "1.ª parada mejor que la mediana histórica del circuito; el éxito del undercut está bien calibrado y el "
                            "del overcut sobrestimado."),
                   "variantes_probadas": len(VARIANTES_PROBADAS)}
    doc["resumen_doc"] = resumen_doc
    doc["actualizado"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    VAL_JSON.write_text(json.dumps(doc, indent=1, default=float, ensure_ascii=False))
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["preparar", "validar", "mexico", "gp", "actualizar"])
    ap.add_argument("--meeting", type=int, default=None, help="gp: meeting_key del GP")
    ap.add_argument("--dataset", default=None, help="gp: dataset_carrera.csv del modelo de carrera")
    ap.add_argument("--objetivo", default=None, help="gp: prediccion_carrera_<slug>_2026.csv (posición media oficial)")
    ap.add_argument("--salida", default=None, help="gp: ruta del JSON (forma de datos_vueltas.json)")
    ap.add_argument("--lugar", default=None, help="gp: nombre corto del GP para los textos (p. ej. Interlagos)")
    ap.add_argument("--ancla-it", type=int, default=None, help="gp: iteraciones del anclaje (default ANCLA_IT)")
    ap.add_argument("--sims", type=int, default=None)
    ap.add_argument("--carrera", action="store_true", help="también escribe datos_carrera_vueltas.json (scratchpad)")
    a = ap.parse_args()
    if a.accion == "preparar":
        preparar(forzar=True)
    elif a.accion == "validar":
        ns = a.sims or 2000
        res_l, *_ = validar(n_sims=ns, var=VAR_OFICIAL, din=DIN_OFICIAL)
        res_a, *_ = validar(n_sims=ns, var={**VAR_OFICIAL, "anclar": True}, din=DIN_OFICIAL)
        du = validar_duelos(n_sims=300, var=VAR_OFICIAL, din=DIN_OFICIAL)
        doc = escribir_validacion(res_l, res_a, du, ns)
        print(json.dumps(doc["resumen_doc"], indent=1, ensure_ascii=False))
    elif a.accion == "actualizar":
        _, nuevas = actualizar_hist()
        print("carreras agregadas al histórico:", nuevas)
    elif a.accion == "gp":
        actualizar_hist()
        pronostico(a.meeting, n_sims=a.sims or 4000, dataset=a.dataset, objetivo=a.objetivo, salida=a.salida, lugar=a.lugar,
                   ancla_it=a.ancla_it)
    else:
        pronostico(1298, n_sims=a.sims or 4000, escribir_carrera=a.carrera)
