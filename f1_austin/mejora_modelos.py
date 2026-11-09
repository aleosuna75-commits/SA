#!/usr/bin/env python3
"""Motor de mejora continua de los modelos (campeón / retador), pensado para correr tras cada GP.

Tareas: qualy_fp1, qualy_fp2, qualy_fp3 (modelo_qualy_austin.py tras FP1, FP2 y FP3) y carrera (simulador Monte Carlo
de modelo_carrera_austin.py / sim_carrera.py). Para cada tarea hay un CAMPEÓN (la variante que usan hoy los modelos) y
RETADORES (variantes predefinidas o propuestas con 'agregar-candidato').

Archivos (modelos/):
  registro.json      variantes por tarea (config, descripción, estado campeon|retador|descartado, última evaluación)
  config_activa.json lo que leen los modelos (config_modelos.py): variante vigente por tarea con historial 'desde'
                     (un GP en retro usa la variante que estaba vigente en su corte: sin fugas)
  bitacora.json      doc bitacora/actual: campeones, evolución por GP, cambios con evidencia, candidatos
  cache/<tarea>/     predicciones walk-forward por componente y GP (firma = datos del GP y de todos los anteriores):
                     sólo se recalcula lo que cambió (normalmente sólo el GP recién corrido)

Ciclo ('ciclo'):
  1. Reconstruye los datasets (todos los GP con resultado hasta hoy) y evalúa con walk-forward (2024 en adelante; cada GP
     se predice entrenando sólo con GPs anteriores) al campeón y a los retadores, con presupuesto de tiempo.
  2. Regla de adopción (por tarea; métrica principal qualy = top10_hits, carrera = NDCG@10): un retador reemplaza al
     campeón sólo si (a) la diferencia media pareada por GP supera z_crit errores estándar sobre TODOS los GP, con
     z_crit = max(2, Bonferroni unilateral al 10 % sobre los k retadores evaluados en la tarea: 2.33 con 10, 2.47 con 15), y (b) no
     empeora en la ventana reciente (últimos 8 GP: diferencia media >= 0); (c) CONFIRMACIÓN CON SEMILLAS: se repite con
     la métrica por GP promediada en 3 semillas y debe pasar otra vez. Si varios pasan, el de mayor diferencia.
     Por qué (verificación 9/11): con 1 EE pasaban 7 de 30 retadores IDÉNTICOS al campeón con otra semilla (RF, qualy
     FP1; z hasta 2.31) y 4 de 12 en carrera (el Monte Carlo usa la misma semilla en todos los GP, así que su ruido es
     común a todos y el EE pareado no lo ve).
     Carrera: el EE incluye el ruido de semilla, estimado con las semillas 0, 1 y 2 del campeón (sd de su métrica media
     por semilla x raíz(2) con una semilla, x raíz(2/3) con el promedio de 3). Qualy: el retador (y el campeón si es un
     modelo fijo) se re-evalúan con random_state 1 y 2 en todos sus modelos estocásticos.
     Un retador con diferencia < -z_crit EE (>= 20 GP) pasa a 'descartado' (no se vuelve a evaluar salvo que se re-agregue).
  3. Si adopta: escribe config_activa.json (no se edita código) y registra el cambio con evidencia en la bitácora.
  4. Recalibra lo que depende de carreras pasadas: sim_vueltas (historial incremental), cache/wf_sim_carrera_actual.csv
     (walk-forward del simulador vigente) y el bloque 'oficial' de validacion_carrera.json.
  Nota: elegir variantes mirando el mismo walk-forward sesga a favor del elegido (comparaciones múltiples); la regla de
  1 EE + ventana reciente lo limita pero no lo elimina. La evaluación de 'base' (selección automática) es anidada: en
  cada GP se usa el modelo que el walk-forward de los GP anteriores habría elegido (igual que en producción).

Uso (desde f1_austin/):
  python3 mejora_modelos.py ciclo [--presupuesto-min 60] [--tareas qualy_fp2,carrera] [--sin-adoptar] [--sims 20000]
                                  [--validar-vueltas]   # además rehace validacion_vueltas.json (~40 min)
  python3 mejora_modelos.py evaluar --tareas qualy_fp3     # sólo llena caches (sin adoptar ni escribir registro)
  python3 mejora_modelos.py agregar-candidato '{"tarea": "carrera", "variante": "mi_var", "descripcion": "...",
                                                "config": {"mc_var": {"is26": false, "gn_inter": true, "form3": true}}}'
                                              (o la ruta de un .json con eso; queda como retador para el próximo ciclo)
  python3 mejora_modelos.py bitacora                       # sólo rehace modelos/bitacora.json
  python3 mejora_modelos.py estado                         # resumen del registro
"""
import argparse
import hashlib
import json
import math
import os
import pickle
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("F1_N_JOBS", "2")
os.environ.pop("F1_CORTE", None)          # el ciclo usa todo lo corrido hasta hoy; el walk-forward evita las fugas

import numpy as np
import pandas as pd

import config_modelos as CM

BASE = Path(__file__).resolve().parent
DIR = BASE / "modelos"
REGISTRO = DIR / "registro.json"
BITACORA = DIR / "bitacora.json"
CACHE_DIR = DIR / "cache"
GPS_DIR = BASE / "gps"
TAREAS = CM.TAREAS
DESDE = 2024
VENTANA = 8
Z_MIN = 2.0                      # z crítico mínimo (antes 1.0: adoptaba retadores idénticos con otra semilla)
ALFA_FAMILIA = 0.10              # Bonferroni (unilateral) sobre los retadores evaluados en una tarea y ciclo
SEMILLAS_CONF = (1, 2)           # semillas extra del CAMPEÓN (producción: carrera 0, qualy random_state 7)
SEMILLAS_RETADOR = (3, 4)        # semillas extra del RETADOR: distintas de las del campeón, para que un retador que sólo
                                 # difiere en la semilla no quede igualado al campeón en la confirmación
MIN_GP_PREVIOS_AUTO = 3
N_SIMS = 20000
METRICA = {"qualy_fp1": "top10_hits", "qualy_fp2": "top10_hits", "qualy_fp3": "top10_hits", "carrera": "ndcg10"}
FASE = {"qualy_fp1": "FP1", "qualy_fp2": "FP2", "qualy_fp3": "FP3"}

# ------------------------------------------------------------------------------------------------
# Candidatos predefinidos (el campeón inicial 'base' = la configuración que usaban los modelos)
# ------------------------------------------------------------------------------------------------
RF = "Random Forest"
ENS_ARB = "Ensamble árboles (RF+ET+GB+XGB+LGB)"
CANDIDATOS_QUALY = {
    "base": ("Configuración original: el walk-forward compara el catálogo (baselines, Ridge, RF, ET, GB, XGBoost, "
             "LightGBM, rankers y 2 ensambles) y usa el mejor por aciertos en el Top 10", {"seleccion": "auto"}),
    "rf_fijo": ("Random Forest fijo (sin selección automática del modelo)", {"seleccion": "fijo", "fijo": RF}),
    "ens_arboles_fijo": ("Ensamble de árboles fijo (RF+ET+GB+XGB+LGB, promedio de rankings)",
                         {"seleccion": "fijo", "fijo": ENS_ARB}),
    "ens_rf_et_ridge": ("Ensamble RF+ET+Ridge (promedio de rankings)",
                        {"seleccion": "fijo", "fijo": "Ensamble RF+ET+Ridge",
                         "ensambles": {"Ensamble RF+ET+Ridge": [RF, "Extra Trees", "Ridge"]}}),
    "ens_rf_rankers": ("Ensamble RF+ET+LambdaRank+XGBoost Ranker (regresión + ranking)",
                       {"seleccion": "fijo", "fijo": "Ensamble RF+ET+rankers",
                        "ensambles": {"Ensamble RF+ET+rankers": [RF, "Extra Trees", "LightGBM LambdaRank", "XGBoost Ranker"]}}),
    "rf_hojas2": ("Random Forest con hojas más chicas (min_samples_leaf=2, max_features=0.3)",
                  {"seleccion": "fijo", "fijo": RF, "hiper": {RF: {"min_samples_leaf": 2, "max_features": 0.3}}}),
    "rf_recencia_fuerte": ("Random Forest con más peso a lo reciente (2026 x6, 2025 x2, antes x1)",
                           {"seleccion": "fijo", "fijo": RF, "pesos": {"2026": 6.0, "2025": 2.0, "otros": 1.0}}),
    "rf_pesos_planos": ("Random Forest sin pesos por recencia (todos x1)",
                        {"seleccion": "fijo", "fijo": RF, "pesos": {"2026": 1.0, "2025": 1.0, "otros": 1.0}}),
    "rf_sin_circuito": ("Random Forest sin el historial del piloto en el circuito (h_circ_*)",
                        {"seleccion": "fijo", "fijo": RF, "quitar": ["h_circ_*"]}),
    "rf_sin_sectores": ("Random Forest sin sectores ni velocidades punta (menos variables ruidosas)",
                        {"seleccion": "fijo", "fijo": RF,
                         "quitar": ["*_s1_gap", "*_s2_gap", "*_s3_gap", "*_trap_delta", "*_i1_delta", "*_i2_delta"]}),
    "rf_debutantes_equipo": ("Random Forest con prior de debutantes por escudería (forma de qualy del equipo + 2)",
                             {"seleccion": "fijo", "fijo": RF, "debutantes": "equipo"}),
}
B = {"is26": False, "gn_inter": True}
CANDIDATOS_CARRERA = {
    "base": ("Simulador original: salida, ritmo de tanda larga, gap de qualy, forma de piloto/equipo con interacción "
             "por posición de salida, facilidad de rebase, ruido de 1.ª vuelta y abandonos", {"mc_var": dict(B)}),
    "pace_deg": ("Ritmo de tanda larga corregido por degradación x largo de stint", {"mc_var": {**B, "pace_deg": True}}),
    "deg_sig_par": ("Degradación de prácticas + ruido según paradas típicas del circuito",
                    {"mc_var": {**B, "deg": True, "sig_par": True}}),
    "deg_hist": ("Degradación observada en carreras previas del piloto", {"mc_var": {**B, "deg_hist": True}}),
    "racecraft": ("Habilidad de remontada: posiciones ganadas en las últimas 10 carreras y en el circuito",
                  {"mc_var": {**B, "racecraft": True}}),
    "form3": ("Forma de las últimas 3 carreras (además de las últimas 10)", {"mc_var": {**B, "form3": True}}),
    "teamlong": ("Ritmo de tanda larga del mejor auto del equipo", {"mc_var": {**B, "teamlong": True}}),
    "front": ("Efectos de primera fila / pole", {"mc_var": {**B, "front": True}}),
    "gn_mob": ("Interacción ritmo/forma x posición x facilidad de rebase", {"mc_var": {**B, "gn_mob": True}}),
    "corr": ("Correlación parrilla-resultado histórica del circuito", {"mc_var": {**B, "corr": True}}),
    "is26": ("Pendientes propias de 2026 (reglamento nuevo) para ritmo y forma", {"mc_var": {**B, "is26": True}}),
    "w26_5": ("Más peso a 2026 en el ajuste (x5 en vez de x3)", {"mc_var": {**B, "w26": 5.0}}),
    "w26_1_5": ("Menos peso a 2026 en el ajuste (x1.5 en vez de x3)", {"mc_var": {**B, "w26": 1.5}}),
    "alpha_10": ("Regresión más regularizada (Ridge alpha=10)", {"mc_var": {**B, "alpha": 10.0}}),
    "ruido_t5": ("Ruido de carrera con colas pesadas (t de Student, 5 g.l.)", {"mc_var": {**B, "df": 5}}),
    "mediana": ("Pronóstico = mediana de la posición simulada (en vez de la media)", {"mc_var": {**B, "resumen": "median"}}),
}
CLAVES_QUALY = {"seleccion", "fijo", "modelos", "ensambles", "pesos", "quitar", "hiper", "debutantes"}
CLAVES_MC = {"is26", "gn_inter", "grid_mob", "corr", "front", "gn_mob", "gn_all", "racecraft", "teamlong", "form3",
             "pole", "deg", "deg_team", "deg_hist", "deg_gn", "pace_deg", "sig_par", "drop", "w26", "alpha", "sig_k",
             "dnf_k", "df", "resumen"}


def ahora():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer_json(ruta, defecto=None):
    try:
        return json.loads(Path(ruta).read_text())
    except Exception:
        return defecto


def escribir_json(ruta, doc):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False, default=_nan_none))
    os.replace(tmp, ruta)


def _nan_none(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return str(x)


def _num(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(x) or math.isinf(x)) else round(x, nd)


def sha(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ------------------------------------------------------------------------------------------------
# Registro
# ------------------------------------------------------------------------------------------------
def registro_inicial():
    t = {}
    for tarea in TAREAS:
        cands = CANDIDATOS_CARRERA if tarea == "carrera" else CANDIDATOS_QUALY
        t[tarea] = {"metrica": METRICA[tarea], "campeon": "base", "desde": CM.ORIGEN,
                    "variantes": {n: {"descripcion": d, "config": c, "estado": "campeon" if n == "base" else "retador",
                                      "origen": "predefinido", "agregado": iso(ahora()), "evaluacion": None}
                                  for n, (d, c) in cands.items()}}
    return {"actualizado": iso(ahora()), "ventana_reciente": VENTANA, "regla": REGLA, "tareas": t}


REGLA = ("Se adopta un retador sólo si su mejora media por GP en la métrica principal (qualy: aciertos en el Top 10; "
         "carrera: NDCG@10) supera 2 errores estándar sobre todos los GP del walk-forward (más si se prueban muchos "
         "retadores a la vez: 2,3 con 10), no empeora en los últimos "
         f"{VENTANA} GP y sigue ganando al repetir la evaluación con otras 2 semillas aleatorias. Así un retador que sólo "
         "tuvo suerte (p. ej. el mismo modelo con otra semilla) no se adopta.")


def leer_registro():
    r = leer_json(REGISTRO)
    if not r:
        r = registro_inicial()
        escribir_json(REGISTRO, r)
        escribir_config_activa(r)
    return r


def escribir_config_activa(reg):
    """modelos/config_activa.json desde el registro (historial de campeones con 'desde')."""
    viejo = CM.leer_config()
    out = {"actualizado": iso(ahora()), "tareas": {}}
    for tarea, t in reg["tareas"].items():
        hist = list(((viejo.get("tareas") or {}).get(tarea) or {}).get("historial") or [])
        if not hist:
            hist = [{"variante": "base", "desde": CM.ORIGEN, "config": t["variantes"]["base"]["config"]}]
        if hist[-1]["variante"] != t["campeon"]:
            hist.append({"variante": t["campeon"], "desde": t.get("desde") or iso(ahora()),
                         "config": t["variantes"][t["campeon"]]["config"]})
        out["tareas"][tarea] = {"vigente": t["campeon"], "historial": hist}
    escribir_json(CM.CONFIG, out)


def validar_candidato(c):
    tarea, nombre, cfg = c.get("tarea"), c.get("variante"), c.get("config")
    if tarea not in TAREAS:
        raise SystemExit(f"tarea inválida: {tarea} (válidas: {TAREAS})")
    if not nombre or not isinstance(nombre, str) or len(nombre) > 60:
        raise SystemExit("variante: nombre corto obligatorio")
    if not isinstance(cfg, dict):
        raise SystemExit("config debe ser un objeto")
    if tarea == "carrera":
        if set(cfg) - {"mc_var"} or not isinstance(cfg.get("mc_var"), dict):
            raise SystemExit('carrera: config = {"mc_var": {...}}')
        malas = set(cfg["mc_var"]) - CLAVES_MC
        if malas:
            raise SystemExit(f"claves de mc_var desconocidas: {sorted(malas)} (válidas: {sorted(CLAVES_MC)})")
    else:
        malas = set(cfg) - CLAVES_QUALY
        if malas:
            raise SystemExit(f"claves desconocidas: {sorted(malas)} (válidas: {sorted(CLAVES_QUALY)})")
        import modelo_qualy_austin as Q
        cat = set(Q.catalogo(tarea == "qualy_fp3", FASE[tarea])) | set(Q.ENSAMBLES) | set(cfg.get("ensambles") or {})
        usados = set(cfg.get("modelos") or []) | set((cfg.get("hiper") or {}).keys()) | \
            {m for ms in (cfg.get("ensambles") or {}).values() for m in ms}
        if cfg.get("seleccion", "auto") == "fijo":
            if not cfg.get("fijo"):
                raise SystemExit("seleccion 'fijo' requiere 'fijo'")
            usados.add(cfg["fijo"])
        faltan = usados - cat
        if faltan:
            raise SystemExit(f"modelos desconocidos: {sorted(faltan)}")
        if cfg.get("debutantes") not in (None, "equipo"):
            raise SystemExit("debutantes: null o 'equipo'")
    return tarea, nombre, cfg


def agregar_candidato(arg):
    arg = arg.strip()
    try:
        c = json.loads(arg) if arg.startswith("{") else leer_json(arg)
    except json.JSONDecodeError as e:
        raise SystemExit(f"JSON inválido: {e}")
    if not isinstance(c, dict):
        raise SystemExit("se espera un objeto JSON (o la ruta de un .json) con tarea, variante, descripcion y config")
    tarea, nombre, cfg = validar_candidato(c)
    reg = leer_registro()
    vs = reg["tareas"][tarea]["variantes"]
    if nombre in vs:
        raise SystemExit(f"ya existe la variante {nombre} en {tarea}")
    for n, v in vs.items():
        if v["config"] == cfg:
            raise SystemExit(f"la misma configuración ya está registrada como {n}")
    vs[nombre] = {"descripcion": str(c.get("descripcion") or nombre)[:300], "config": cfg, "estado": "retador",
                  "origen": str(c.get("origen") or "agente"), "agregado": iso(ahora()), "evaluacion": None}
    reg["actualizado"] = iso(ahora())
    escribir_json(REGISTRO, reg)
    print(f"Agregado retador {tarea}/{nombre}: se evalúa en el próximo ciclo (sólo se adopta si pasa la regla).")


# ------------------------------------------------------------------------------------------------
# Datasets y firmas por GP
# ------------------------------------------------------------------------------------------------
def dataset(tarea):
    if tarea == "carrera":
        import modelo_carrera_austin as C
        data, _ = C.construir_dataset_carrera(0)
        data = data[data.race_pos.notna()].copy()
        return data
    import modelo_qualy_austin as Q
    data, _ = Q.construir_dataset(con_fp3=tarea == "qualy_fp3", solo_fp1=tarea == "qualy_fp1")
    return data


def columnas_firma(tarea, data):
    import modelo_qualy_austin as Q
    if tarea == "carrera":
        import modelo_carrera_austin as C
        cols = C.FEATURES_CARRERA + C.FEATURES_DEG + ["race_pos", "status", "grid", "q_pos", "long_rank_all", "fp_rank_all",
                                                      "long_gap_all", "q_gap", "r_mean10", "team_r_mean5", "sprint_pos",
                                                      "circ_gain_abs", "circ_grid_corr", "circ_dnf_rate", "team_finish_rate5",
                                                      "r_finish_rate10", "year", "deg_rel", "deg_team_rel", "ref_lap",
                                                      "r_gain_mean10", "r_circ_gain", "long_team_best", "r_mean3"]
    else:
        cols = (Q.FEATURES_FP3 if tarea == "qualy_fp3" else Q.FEATURES) + ["q_pos", "q_eval", "year", "fp3_best",
                                                                           "h_team_q_mean5", "fp1_rank", "main3_rank", "c3_rank"]
    return [c for c in dict.fromkeys(cols) if c in data.columns]


def firmas(tarea, data):
    """{meeting_key: firma} = hash de las filas del GP y de todos los GP anteriores (lo que ve su walk-forward)."""
    cols = columnas_firma(tarea, data)
    d = data.sort_values(["date", "meeting_key", "driver_number"])
    orden = d.groupby("meeting_key", sort=False).date.first().sort_values()
    h_gp = {}
    for mk, g in d.groupby("meeting_key", sort=False):
        x = g[["driver_number"] + cols].copy()
        for c in x.columns:
            if x[c].dtype == object:
                x[c] = x[c].astype(str)
        h_gp[mk] = hashlib.sha1(pd.util.hash_pandas_object(x, index=False).values.tobytes()).hexdigest()
    out, acum = {}, hashlib.sha1()
    previo = {}
    for mk, fecha in orden.items():
        previo[mk] = acum.hexdigest()
        acum.update(h_gp[mk].encode())
    for mk in orden.index:
        out[mk] = hashlib.sha1((previo[mk] + h_gp[mk]).encode()).hexdigest()[:16]
    return out, orden


def pruebas_de(tarea, data):
    col = "race_pos" if tarea == "carrera" else "q_pos"
    e = data.dropna(subset=[col])
    return e[e.year >= DESDE].sort_values("date").meeting_key.drop_duplicates().tolist()


# ------------------------------------------------------------------------------------------------
# Componentes (un modelo con su configuración) y cache de predicciones walk-forward por GP
# ------------------------------------------------------------------------------------------------
def miembros_qualy(cfg, tarea):
    import modelo_qualy_austin as Q
    ens = {**Q.ENSAMBLES_BASE, **(cfg.get("ensambles") or {})}
    if cfg.get("seleccion", "auto") == "fijo":
        return list(ens.get(cfg["fijo"], [cfg["fijo"]])), ens
    cat = list(Q.catalogo(tarea == "qualy_fp3", FASE[tarea]))
    return list(cfg.get("modelos") or cat), ens


def componente_qualy(nombre_modelo, cfg):
    es_base = nombre_modelo.startswith("Baseline")
    return {"modelo": nombre_modelo,
            "hiper": None if es_base else (cfg.get("hiper") or {}).get(nombre_modelo),
            "pesos": None if es_base else cfg.get("pesos"),
            "quitar": sorted(cfg.get("quitar") or []),
            "debutantes": None if es_base else cfg.get("debutantes")}


class Cache:
    def __init__(self, tarea):
        self.dir = CACHE_DIR / tarea
        self.dir.mkdir(parents=True, exist_ok=True)
        self.mem = {}

    def ruta(self, h):
        return self.dir / f"{h}.pkl"

    def cargar(self, h):
        if h not in self.mem:
            try:
                self.mem[h] = pickle.loads(self.ruta(h).read_bytes())
            except Exception:
                self.mem[h] = {}
        return self.mem[h]

    def guardar(self, h, comp):
        d = self.mem.get(h, {})
        d["_comp"] = comp
        tmp = self.ruta(h).with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(d))
        os.replace(tmp, self.ruta(h))


class Evaluador:
    """Walk-forward con cache por (componente, GP, firma). Igual que modelo_qualy_austin.walk_forward /
    modelo_carrera_austin.walk_forward_sim (mismas semillas, mismos pesos y mismo orden de filas)."""

    def __init__(self, tarea, n_sims=N_SIMS, log=print):
        self.tarea, self.n_sims, self.log = tarea, n_sims, log
        t0 = time.time()
        self.data = dataset(tarea)
        self.firmas, self.orden = firmas(tarea, self.data)
        self.pruebas = pruebas_de(tarea, self.data)
        self.cache = Cache(tarea)
        self.calculados = 0
        self._datos_var = {}
        log(f"  [{tarea}] dataset {len(self.data)} filas, {len(self.pruebas)} GP de prueba ({time.time() - t0:.0f} s)")

    # ---- qualy
    def _data_var(self, debutantes):
        import modelo_qualy_austin as Q
        if debutantes not in self._datos_var:
            self._datos_var[debutantes] = Q.datos_variante(self.data, {"debutantes": debutantes})
        return self._datos_var[debutantes]

    def faltantes(self, comp):
        h = sha({"t": self.tarea, "c": comp, "n": self.n_sims if self.tarea == "carrera" else None})
        c = self.cache.cargar(h)
        return h, [mk for mk in self.pruebas if (c.get(mk) or {}).get("firma") != self.firmas[mk]]

    def preds_componente(self, comp, limite=None):
        """DataFrame de predicciones walk-forward del componente (todas las pruebas) o None si se agotó el tiempo."""
        h, falta = self.faltantes(comp)
        c = self.cache.cargar(h)
        if falta:
            t0 = time.time()
            for i, mk in enumerate(falta):
                if limite and time.time() > limite:
                    self.cache.guardar(h, comp)
                    self.log(f"    presupuesto agotado en {comp.get('modelo') or 'sim'} ({i}/{len(falta)} GP nuevos)")
                    return None
                c[mk] = {"firma": self.firmas[mk], "pred": self._fold(comp, mk)}
                self.calculados += 1
            self.cache.guardar(h, comp)
            self.log(f"    {self.tarea}: {comp.get('modelo') or json.dumps(comp.get('mc_var'))} -> {len(falta)} GP "
                     f"calculados ({time.time() - t0:.0f} s)")
        return pd.concat([c[mk]["pred"] for mk in self.pruebas], ignore_index=True)

    def _fold(self, comp, mk):
        if self.tarea == "carrera":
            from sim_carrera import Simulador
            e = self.data
            fecha = e[e.meeting_key == mk].date.iloc[0]
            tr = e[e.date < fecha].sort_values(["meeting_key", "driver_number"])
            te = e[e.meeting_key == mk]
            cab = te[["meeting_key", "driver_number", "year"]].assign(real=te.race_pos.values)
            sim = Simulador(comp["mc_var"]).fit(tr)
            if comp["mc_var"].get("resumen") in ("median", "gain"):
                return cab.assign(pred=_resumen(sim, te, self.n_sims, comp["mc_var"]["resumen"], comp.get("semilla", 0)))
            return cab.assign(pred=sim.simular(te, n_sims=self.n_sims, seed=comp.get("semilla", 0))[0])
        import modelo_qualy_austin as Q
        con_fp3 = self.tarea == "qualy_fp3"
        fase = FASE[self.tarea]
        cfg = {"pesos": comp["pesos"], "hiper": {comp["modelo"]: comp["hiper"]} if comp["hiper"] else {},
               "quitar": comp["quitar"]}
        Q.aplicar_config(cfg)
        base_f = Q.FEATURES_FP3 if con_fp3 else Q.FEATURES_FP1 if fase == "FP1" else Q.FEATURES
        feats = Q.features_variante(base_f, cfg)
        feats_sin = Q.features_variante(Q.FEATURES, cfg)
        data = self._data_var(comp["debutantes"])
        e = data.dropna(subset=["q_pos"])
        fecha = e[e.meeting_key == mk].date.iloc[0]
        tr = e[e.date < fecha].sort_values(["meeting_key", "driver_number"])
        te = data[data.meeting_key == mk].assign(q_pos=lambda x: x.q_eval)
        grupos = tr.groupby("meeting_key", sort=False).size().loc[tr.meeting_key.unique()].values
        sin_fp3 = con_fp3 and not te.fp3_best.notna().any()
        m = Q.catalogo(con_fp3, fase)[comp["modelo"]]()
        f = feats_sin if (sin_fp3 and m.tipo != "baseline") else feats
        m.fit(tr[f], tr.q_pos.values, Q.pesos(tr), grupos)
        p = te[["meeting_key", "driver_number", "q_pos", "year"]].copy()
        p["pred"] = m.predict(te[f])
        Q.aplicar_config({})
        return p

    # ---- variantes
    def preds_variante(self, cfg, limite=None, semilla=0):
        """(preds DataFrame con columna pred, nombre del modelo elegido hoy) o (None, None) si no alcanzó el tiempo.
        semilla (sólo carrera): semilla del Monte Carlo (0 = la de producción)."""
        if self.tarea == "carrera":
            comp = {"mc_var": cfg["mc_var"]} if not semilla else {"mc_var": cfg["mc_var"], "semilla": semilla}
            p = self.preds_componente(comp, limite)
            return p, "Simulador Monte Carlo"
        miembros, ens = miembros_qualy(cfg, self.tarea)
        preds = {}
        for n in miembros:
            p = self.preds_componente(componente_qualy(n, cfg), limite)
            if p is None:
                return None, None
            preds[n] = p
        for nom, ms in ens.items():
            if all(m in preds for m in ms) and nom not in preds:
                preds[nom] = _ensamble(preds, ms)
        if cfg.get("seleccion", "auto") == "fijo":
            return preds[cfg["fijo"]], cfg["fijo"]
        return seleccion_anidada(preds, self.pruebas)


def _resumen(sim, te, n_sims, modo, semilla=0):
    m, mu, sig, pd_, pos = sim.simular(te, n_sims=n_sims, seed=semilla)
    if modo == "gain":
        return -np.clip(11 - pos, 0, None).mean(axis=0)
    return np.median(pos, axis=0) + 1e-3 * m


def _ensamble(preds, miembros):
    b = preds[miembros[0]].drop(columns=["pred"]).copy()
    b["pred"] = np.mean([preds[n].groupby("meeting_key").pred.rank().values for n in miembros], axis=0)
    return b


def metricas_gp(tarea, p):
    """Métricas por GP (DataFrame indexado por meeting_key)."""
    if tarea == "carrera":
        import modelo_carrera_austin as C
        m = C.metricas(p, "pred")
    else:
        import modelo_qualy_austin as Q
        m = Q.metricas(p, "pred")
    return m.set_index("meeting_key")


def seleccion_anidada(preds, pruebas):
    """Evaluación honesta de 'seleccion: auto': en cada GP se usa el modelo con mejor top10_hits (desempate Spearman)
    en los GP anteriores del walk-forward, como haría producción en ese momento."""
    import modelo_qualy_austin as Q
    met = {n: Q.metricas(p, "pred").set_index("meeting_key").reindex(pruebas) for n, p in preds.items()}
    out = []
    elegido = RF
    for i, mk in enumerate(pruebas):
        if i >= MIN_GP_PREVIOS_AUTO:
            prev = pruebas[:i]
            tabla = sorted(((met[n].loc[prev, "top10_hits"].mean(), met[n].loc[prev, "spearman"].mean(), n)
                            for n in preds), key=lambda x: (x[0], x[1]), reverse=True)
            elegido = tabla[0][2]
        else:
            elegido = RF if RF in preds else next(iter(preds))
        out.append(preds[elegido][preds[elegido].meeting_key == mk])
    tabla = sorted(((met[n].top10_hits.mean(), met[n].spearman.mean(), n) for n in preds),
                   key=lambda x: (x[0], x[1]), reverse=True)
    return pd.concat(out, ignore_index=True), f"selección automática (hoy elige {tabla[0][2]})"


# ------------------------------------------------------------------------------------------------
# Comparación y regla de adopción
# ------------------------------------------------------------------------------------------------
def resumen(tarea, met, orden):
    m = METRICA[tarea]
    rec = met.loc[[k for k in orden.index if k in met.index][-VENTANA:]]
    out = {m: _num(met[m].mean()), "n_gp": int(len(met)), f"{m}_reciente": _num(rec[m].mean())}
    if tarea == "carrera":
        out.update({"top10_hits": _num(met.top10_hits.mean(), 3), "ganador": _num(met.win_hit.mean(), 3),
                    "podio": _num(met.podium_hits.mean(), 3), "mae_top10": _num(met.mae_top10.mean(), 3),
                    "spearman": _num(met.spearman.mean(), 4)})
    else:
        out.update({"pole": _num(met.pole_hit.mean(), 3), "mae": _num(met.mae.mean(), 3),
                    "spearman": _num(met.spearman.mean(), 4), "top3_hits": _num(met.top3_hits.mean(), 3)})
    return out


def z_critico(k):
    """z mínimo para adoptar con k retadores evaluados en la tarea: max(2, Bonferroni unilateral al 10 %)."""
    from scipy.stats import norm
    return max(Z_MIN, float(norm.ppf(1 - ALFA_FAMILIA / max(int(k), 1))))


def comparar(tarea, met_c, met_r, orden, z_crit=Z_MIN, ee_extra=0.0):
    """ee_extra: componente de ruido que el EE pareado por GP no ve (semilla del Monte Carlo); se suma en cuadratura."""
    m = METRICA[tarea]
    comunes = [k for k in orden.index if k in met_c.index and k in met_r.index]
    d = (met_r.loc[comunes, m] - met_c.loc[comunes, m]).astype(float)
    n = len(d)
    se_p = float(d.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    se = math.sqrt(se_p ** 2 + float(ee_extra or 0) ** 2) if n > 1 else float("nan")
    rec = comunes[-VENTANA:]
    dr = d.loc[rec]
    media = float(d.mean()) if n else float("nan")
    pasa = bool(n >= 10 and media > 0 and (media > z_crit * se if se > 0 else True) and dr.mean() >= 0)
    return {"metrica": m, "antes": _num(met_c.loc[comunes, m].mean()), "despues": _num(met_r.loc[comunes, m].mean()),
            "diferencia": _num(media), "ee": _num(se), "ee_pareado": _num(se_p), "ee_semilla": _num(ee_extra or 0.0),
            "n_gp": n, "z": _num(media / se if se and se > 0 else None, 2), "z_critico": _num(z_crit, 2),
            "ventana_reciente": {"n_gp": len(rec), "antes": _num(met_c.loc[rec, m].mean()),
                                 "despues": _num(met_r.loc[rec, m].mean()), "diferencia": _num(dr.mean())},
            "pasa_regla": pasa}


COLS_PROM = {"carrera": ["ndcg10", "top10_hits", "win_hit", "podium_hits", "mae_top10", "spearman"],
             "qualy": ["top10_hits", "spearman", "pole_hit", "mae", "top3_hits"]}


def promedio_semillas(tarea, mets):
    cols = COLS_PROM["carrera" if tarea == "carrera" else "qualy"]
    return sum(m[[c for c in cols if c in m.columns]] for m in mets) / len(mets)


def cfg_semilla(cfg, semilla):
    """Config de qualy con random_state=semilla en todos sus modelos estocásticos (baselines y Ridge no lo son)."""
    miembros, _ = miembros_qualy(cfg, "qualy_fp2")
    hiper = {k: dict(v) for k, v in (cfg.get("hiper") or {}).items()}
    for n in miembros:
        if not (n.startswith("Baseline") or n == "Ridge"):
            hiper[n] = {**hiper.get(n, {}), "random_state": int(semilla)}
    return {**cfg, "hiper": hiper}


def ruido_semilla(ev, cfg_c, met_c0, limite):
    """Carrera: métricas por GP del campeón con las semillas 0, 1, 2 y sd de su métrica media por semilla."""
    if ev.tarea != "carrera":
        return None
    mets = [met_c0]
    for s in SEMILLAS_CONF:
        p, _ = ev.preds_variante(cfg_c, limite, semilla=s)
        if p is None:
            return None
        mets.append(metricas_gp("carrera", p))
    medias = [float(m[METRICA["carrera"]].mean()) for m in mets]
    return {"mets": mets, "sd": float(np.std(medias, ddof=1)), "medias": [_num(x, 5) for x in medias]}


# ------------------------------------------------------------------------------------------------
# Ciclo
# ------------------------------------------------------------------------------------------------
def ciclo(tareas=None, presupuesto_min=60.0, adoptar=True, n_sims=N_SIMS, solo_evaluar=False, validar_vueltas=False):
    t_ini = time.time()
    limite = t_ini + presupuesto_min * 60
    reg = leer_registro()
    tareas = tareas or TAREAS
    informe = {"inicio": iso(ahora()), "presupuesto_min": presupuesto_min, "tareas": {}}
    evals, resultados = {}, {}
    # 1) campeones primero (todas las tareas), luego retadores de menor a mayor costo
    for tarea in tareas:
        print(f"[{iso(ahora())}] {tarea}: dataset y campeón", flush=True)
        ev = Evaluador(tarea, n_sims=n_sims)
        evals[tarea] = ev
        t = reg["tareas"][tarea]
        camp = t["campeon"]
        p, modelo_hoy = ev.preds_variante(t["variantes"][camp]["config"], limite)
        resultados[(tarea, camp)] = (p, modelo_hoy)
    pend = []
    for tarea in tareas:
        ev, t = evals[tarea], reg["tareas"][tarea]
        for n, v in t["variantes"].items():
            if n == t["campeon"] or v.get("estado") == "descartado":
                continue
            costo = _costo(ev, v["config"])
            pend.append((costo, tarea, n))
    pend.sort()
    for costo, tarea, n in pend:
        if time.time() > limite:
            print(f"  sin tiempo para {tarea}/{n}", flush=True)
            continue
        cfg = reg["tareas"][tarea]["variantes"][n]["config"]
        resultados[(tarea, n)] = evals[tarea].preds_variante(cfg, limite)
    if solo_evaluar:
        print(f"evaluación terminada ({time.time() - t_ini:.0f} s)")
        return None
    # 2) comparar y decidir
    cambios = []
    bit = leer_json(BITACORA, {}) or {}
    for tarea in tareas:
        ev, t = evals[tarea], reg["tareas"][tarea]
        camp = t["campeon"]
        pc, modelo_hoy = resultados.get((tarea, camp), (None, None))
        inf = {"campeon": camp, "evaluados": [], "sin_tiempo": [], "adoptado": None}
        if pc is None:
            inf["nota"] = "presupuesto agotado antes de terminar el campeón: no se decide nada"
            informe["tareas"][tarea] = inf
            continue
        met_c = metricas_gp(tarea, pc)
        t["variantes"][camp]["evaluacion"] = {"fecha": iso(ahora()), "modelo_hoy": modelo_hoy,
                                              **resumen(tarea, met_c, ev.orden)}
        t["modelo_hoy"] = modelo_hoy
        cand = []
        retadores = [n for n, v in t["variantes"].items() if n != camp and v.get("estado") != "descartado"]
        evaluables = [n for n in retadores if resultados.get((tarea, n), (None, None))[0] is not None]
        z_crit = z_critico(len(evaluables))
        inf["z_critico"] = _num(z_crit, 2)
        # carrera: ruido de semilla del Monte Carlo (común a todos los GP; el EE pareado no lo ve) con las semillas 0,1,2
        ruido = ruido_semilla(ev, t["variantes"][camp]["config"], met_c, limite) if tarea == "carrera" else None
        if tarea == "carrera":
            inf["ruido_semilla"] = {"sd": _num(ruido["sd"], 5), "medias": ruido["medias"]} if ruido else None
        for n in retadores:
            v = t["variantes"][n]
            pr, mh = resultados.get((tarea, n), (None, None))
            if pr is None:
                inf["sin_tiempo"].append(n)
                continue
            met_r = metricas_gp(tarea, pr)
            if tarea == "carrera" and ruido is None:
                cmp_ = {**comparar(tarea, met_c, met_r, ev.orden, z_crit), "pasa_regla": False,
                        "nota": "sin tiempo para medir el ruido de semilla del campeón: no se decide"}
            else:
                # una semilla cada uno: ruido de semilla de una diferencia = sd x raíz(2)
                cmp_ = comparar(tarea, met_c, met_r, ev.orden, z_crit, ruido["sd"] * math.sqrt(2) if ruido else 0.0)
            v["evaluacion"] = {"fecha": iso(ahora()), "modelo_hoy": mh, **resumen(tarea, met_r, ev.orden), "vs_campeon": cmp_}
            inf["evaluados"].append({"variante": n, **{k: cmp_.get(k) for k in ("diferencia", "ee", "z", "pasa_regla")},
                                     "reciente": cmp_["ventana_reciente"]["diferencia"]})
            if cmp_["pasa_regla"]:
                # confirmación con 3 semillas (Monte Carlo en carrera; random_state de los modelos en qualy): un
                # retador que sólo tuvo suerte con la semilla de producción no se adopta
                conf = confirmar_semillas(ev, t["variantes"][camp]["config"], v["config"], met_c, met_r, limite,
                                          z_crit, ruido)
                v["evaluacion"]["confirmacion_semillas"] = conf
                if not (conf and conf["pasa_regla"]):
                    nota = ("pasaba con la semilla de producción pero no con el promedio de 3 semillas" if conf else
                            "sin tiempo para confirmar con otras semillas")
                    cmp_ = {**cmp_, "pasa_regla": False, "nota": nota}
                    v["evaluacion"]["vs_campeon"].update({"pasa_regla": False, "nota": nota})
                    inf["evaluados"][-1].update({"pasa_regla": False, "nota": nota})
                else:
                    cmp_ = {**conf, "pasa_regla": True}
            if cmp_["pasa_regla"]:
                cand.append((cmp_["diferencia"], cmp_.get("z") or 0.0, n, cmp_))
            elif cmp_["n_gp"] >= 20 and cmp_["ee"] and cmp_["diferencia"] < -z_crit * cmp_["ee"] and \
                    (tarea != "carrera" or ruido is not None):
                v["estado"] = "descartado"
                v["descartado"] = iso(ahora())
        if cand and adoptar:
            cand.sort(key=lambda x: (x[0], x[1]), reverse=True)     # mayor diferencia; desempate: mayor z
            dif, _, nuevo, cmp_ = cand[0]
            fecha = iso(ahora())
            t["variantes"][camp]["estado"] = "retador"
            t["variantes"][nuevo]["estado"] = "campeon"
            t["campeon"], t["desde"] = nuevo, fecha
            t["modelo_hoy"] = t["variantes"][nuevo]["evaluacion"]["modelo_hoy"]
            motivo = (f"{nuevo} mejora {cmp_['metrica']} en {cmp_['diferencia']:+.4f} por GP (EE {cmp_['ee']:.4f}, "
                      f"z {cmp_.get('z')} > {cmp_.get('z_critico')}, promedio de 3 semillas, {cmp_['n_gp']} GP) y no "
                      f"empeora en los últimos {VENTANA} GP ({cmp_['ventana_reciente']['diferencia']:+.4f}).")
            cambios.append({"fecha": fecha, "tarea": tarea, "de": camp, "a": nuevo, "motivo": motivo,
                            "evidencia": {k: cmp_[k] for k in ("metrica", "antes", "despues", "diferencia", "ee", "n_gp",
                                                               "ventana_reciente")}})
            inf["adoptado"] = nuevo
        informe["tareas"][tarea] = inf
    reg["actualizado"] = iso(ahora())
    escribir_json(REGISTRO, reg)
    escribir_config_activa(reg)
    # 3) recalibraciones que dependen de carreras pasadas
    informe["recalibracion"] = recalibrar(evals.get("carrera"), resultados, reg)
    if validar_vueltas:          # validación walk-forward completa del vuelta a vuelta (~40 min): sólo si se pide
        import subprocess
        r = subprocess.run([sys.executable, "sim_vueltas.py", "validar", "--sims", "2000"], cwd=BASE,
                           capture_output=True, text=True)
        informe["recalibracion"]["validacion_vueltas"] = "rehecha" if r.returncode == 0 else f"falló (rc={r.returncode})"
    informe["segundos"] = round(time.time() - t_ini)
    informe["fin"] = iso(ahora())
    informe["calculados"] = {t: ev.calculados for t, ev in evals.items()}
    doc = construir_bitacora(reg, cambios_nuevos=cambios, informe=informe)
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=_nan_none))
    return informe, doc


def confirmar_semillas(ev, cfg_c, cfg_r, met_c0, met_r0, limite, z_crit=Z_MIN, ruido=None, semillas=SEMILLAS_CONF,
                       semillas_r=SEMILLAS_RETADOR):
    """Re-comparación con la métrica por GP promediada en 3 semillas: campeón = producción + 1, 2; retador = producción
    + 3, 4 (semillas independientes: un retador que es el campeón con otra semilla no se iguala al campeón).
    Carrera: semillas del Monte Carlo; el EE suma el ruido de semilla de la diferencia de dos promedios de 3 (sd entre
    semillas del campeón x raíz(2/3)). Qualy: random_state en los modelos estocásticos del retador y, si el campeón es un
    modelo fijo, también del campeón (la selección automática no se re-evalúa: costaría todo el catálogo por semilla).
    Devuelve None si no alcanzó el presupuesto."""
    mc, mr = [met_c0], [met_r0]
    camp_sem = ev.tarea == "carrera" or cfg_c.get("seleccion", "auto") == "fijo"
    for s, sr in zip(semillas, semillas_r):
        if ev.tarea == "carrera":
            pr, _ = ev.preds_variante(cfg_r, limite, semilla=sr)
            pc, _ = ev.preds_variante(cfg_c, limite, semilla=s) if pr is not None else (None, None)
        else:
            pr, _ = ev.preds_variante(cfg_semilla(cfg_r, sr), limite)
            pc = ev.preds_variante(cfg_semilla(cfg_c, s), limite)[0] if (camp_sem and pr is not None) else None
        if pr is None or (camp_sem and pc is None):
            return None
        if camp_sem:
            mc.append(metricas_gp(ev.tarea, pc))
        mr.append(metricas_gp(ev.tarea, pr))
    ee_extra = (ruido["sd"] * math.sqrt(2 / 3)) if (ev.tarea == "carrera" and ruido) else 0.0
    out = comparar(ev.tarea, promedio_semillas(ev.tarea, mc), promedio_semillas(ev.tarea, mr), ev.orden, z_crit, ee_extra)
    prod = [0] if ev.tarea == "carrera" else [7]
    out["semillas"] = {"campeon": prod + list(semillas) if camp_sem else prod, "retador": prod + list(semillas_r)}
    out["campeon_promediado"] = len(mc) > 1
    return out


def _costo(ev, cfg):
    """GP x componente que faltan en cache (para ordenar retadores: primero los que no cuestan nada)."""
    if ev.tarea == "carrera":
        return len(ev.faltantes({"mc_var": cfg["mc_var"]})[1])
    miembros, _ = miembros_qualy(cfg, ev.tarea)
    return sum(len(ev.faltantes(componente_qualy(n, cfg))[1]) for n in miembros)


def recalibrar(ev_carrera, resultados, reg):
    out = {}
    try:
        import sim_vueltas as S
        _, nuevas = S.actualizar_hist()
        out["sim_vueltas_hist"] = f"{len(nuevas)} carrera(s) agregada(s) al historial incremental" if nuevas else "al día"
    except Exception as e:
        out["sim_vueltas_hist"] = f"error: {e}"
    if ev_carrera is not None:
        camp = reg["tareas"]["carrera"]["campeon"]
        p = (resultados.get(("carrera", camp)) or (None, None))[0]
        if p is not None and ev_carrera.n_sims == N_SIMS:
            f = BASE / "cache" / "wf_sim_carrera_actual.csv"
            p[["meeting_key", "driver_number", "year", "real", "pred"]].to_csv(f, index=False)
            out["wf_sim_carrera_actual"] = f"{p.meeting_key.nunique()} GP (variante {camp})"
            vf = BASE / "validacion_carrera.json"
            v = leer_json(vf)
            if v:
                import modelo_carrera_austin as C
                v["oficial"] = {"variante": camp, "mc_var": reg["tareas"]["carrera"]["variantes"][camp]["config"]["mc_var"],
                                "metricas": {k: _num(x, 6) for k, x in C.resumen_metricas(p).items()}}
                v["oficial_actualizado"] = iso(ahora())
                v["oficial_nota"] = "bloque 'oficial' recalculado por mejora_modelos.py (campeón vigente, walk-forward a hoy)"
                escribir_json(vf, v)
                out["validacion_carrera"] = f"oficial = {camp}, NDCG@10 {v['oficial']['metricas']['ndcg10']:.4f} " \
                                            f"({int(v['oficial']['metricas']['n_gp'])} GP)"
    return out


# ------------------------------------------------------------------------------------------------
# Bitácora (doc bitacora/actual)
# ------------------------------------------------------------------------------------------------
def evolucion():
    filas = []
    for d in sorted(GPS_DIR.glob("*/config.json")):
        cfg = leer_json(d)
        if not cfg:
            continue
        g = d.parent
        pq, pc = leer_json(g / "post_qualy.json"), leer_json(g / "post_carrera.json")
        if not pq and not pc:
            continue
        r = next((s for s in cfg["sesiones"] if s["clave"] == "r"), cfg["sesiones"][-1])
        filas.append({"slug": cfg["slug"], "gp": cfg["nombre"], "_f": r["inicio_utc"],
                      "qualy": {"aciertos": pq["aciertos_top10"], "pole_ok": bool(pq["acierto_pole"]), "mae": pq.get("mae")}
                      if pq else None,
                      "carrera": {"aciertos": pc["aciertos_top10"], "ganador_ok": bool(pc["acierto_ganador"]),
                                  "podio": pc.get("aciertos_podio"), "mae": pc.get("mae")} if pc else None})
    a = evolucion_austin()
    if a and not any(f["slug"] == a["slug"] for f in filas):
        filas.append(a)
    filas.sort(key=lambda f: f["_f"])
    for f in filas:
        f.pop("_f")
    return filas


def evolucion_austin():
    """Austin 2026 (1297, antes del flujo multi-GP) desde los archivos viejos: prediccion_qualy_austin_2026.csv y
    prediccion_carrera_austin_2026.csv contra la qualy (OpenF1) y la carrera (Jolpica)."""
    try:
        import modelo_qualy_austin as Q
        import modelo_carrera_austin as C
        pq = pd.read_csv(BASE / "prediccion_qualy_austin_2026.csv")
        ses = Q.tabla_sesiones()
        s = ses[(ses.meeting_key == 1297)]
        sk_q = int(s[s.session_name == "Qualifying"].session_key.iloc[0])
        f_r = s[s.session_name == "Race"].date_start.iloc[0]
        res = Q.tabla_resultados()
        q = res[res.session_key == sk_q][["driver_number", "position"]].copy()
        q["position"] = pd.to_numeric(q.position, errors="coerce")
        m = pq[["driver_number", "name_acronym", "pred_rank"]].merge(q, on="driver_number", how="left")
        m["real"] = m.position.fillna(99).rank(method="first")
        m["pr"] = m.pred_rank.rank(method="first")
        top_p, top_r = set(m[m.pr <= 10].name_acronym), set(m[m.real <= 10].name_acronym)
        qualy = {"aciertos": len(top_p & top_r), "pole_ok": bool(m.loc[m.pr.idxmin(), "real"] == 1),
                 "mae": _num((m.pr - m.real).abs().mean(), 2)}
        carrera = None
        pcf = BASE / "prediccion_carrera_austin_2026.csv"
        if pcf.exists():
            pc = pd.read_csv(pcf)
            jr = C.carreras_jolpica()
            jr = jr[(jr.date >= f_r.tz_convert(None).normalize() - pd.Timedelta(days=1)) &
                    (jr.date <= f_r.tz_convert(None).normalize() + pd.Timedelta(days=1))]
            if len(jr):
                mm = pc[["name_acronym", "pred_rank"]].merge(jr[["code", "pos", "terminado"]], left_on="name_acronym",
                                                             right_on="code", how="left")
                mm["pr"] = mm.pred_rank.rank(method="first")
                cl = mm.dropna(subset=["pos"])
                tp, tr = list(mm.sort_values("pr").name_acronym[:10]), list(cl.sort_values("pos").name_acronym[:10])
                carrera = {"aciertos": len(set(tp) & set(tr)), "ganador_ok": tp[0] == tr[0],
                           "podio": len(set(tp[:3]) & set(tr[:3])), "mae": _num((cl.pr - cl.pos).abs().mean(), 2)}
        return {"slug": "austin2026", "gp": "Gran Premio de Estados Unidos (archivos previos al flujo automático)",
                "_f": f_r.strftime("%Y-%m-%dT%H:%M:%SZ"), "qualy": qualy, "carrera": carrera}
    except Exception as e:
        print("  AVISO: Austin no se pudo reconstruir:", e)
        return None


def proxima_revision():
    t = ahora()
    prox = []
    for d in GPS_DIR.glob("*/config.json"):
        cfg = leer_json(d) or {}
        r = next((s for s in cfg.get("sesiones", []) if s["clave"] == "r"), None)
        if r:
            f = datetime.fromisoformat(r["inicio_utc"].replace("Z", "+00:00")) + timedelta(hours=2, minutes=15)
            if f > t:
                prox.append(f)
    return iso(min(prox)) if prox else None


def construir_bitacora(reg=None, cambios_nuevos=None, informe=None):
    reg = reg or leer_registro()
    viejo = leer_json(BITACORA, {}) or {}
    cambios = list(viejo.get("cambios") or []) + list(cambios_nuevos or [])
    camp = {}
    nombres = {"qualy_fp1": "qualy_fp1", "qualy_fp2": "qualy_fp2", "qualy_fp3": "qualy_fp3", "carrera": "carrera"}
    for tarea, t in reg["tareas"].items():
        v = t["variantes"][t["campeon"]]
        ev = v.get("evaluacion") or {}
        modelo = ev.get("modelo_hoy") or t.get("modelo_hoy") or ("Simulador Monte Carlo" if tarea == "carrera" else "-")
        if tarea == "carrera":
            modelo = f"Simulador Monte Carlo de carrera ({v['descripcion']})"
        desde = t.get("desde") or CM.ORIGEN
        if desde == CM.ORIGEN:      # configuración original: campeona desde que existe el registro
            desde = t["variantes"]["base"].get("agregado") or desde
        camp[nombres[tarea]] = {"modelo": str(modelo), "variante": t["campeon"], "desde": desde,
                                "metricas": {k: x for k, x in ev.items() if k not in ("fecha", "modelo_hoy", "n_gp", "vs_campeon")},
                                "n_gp": int(ev.get("n_gp") or 0)}
    cands = []
    for tarea, t in reg["tareas"].items():
        for n, v in t["variantes"].items():
            ev = v.get("evaluacion")
            um = None
            if ev:
                m = METRICA[tarea]
                vs = ev.get("vs_campeon") or {}
                um = {"metrica": m, "valor": ev.get(m), "reciente": ev.get(f"{m}_reciente"), "n_gp": ev.get("n_gp"),
                      "fecha": ev.get("fecha")}
                if vs:
                    um.update({"diferencia_vs_campeon": vs.get("diferencia"), "ee": vs.get("ee"),
                               "diferencia_reciente": (vs.get("ventana_reciente") or {}).get("diferencia"),
                               "pasa_regla": vs.get("pasa_regla")})
            cands.append({"tarea": tarea, "variante": n, "descripcion": v["descripcion"], "estado": v["estado"],
                          "origen": v.get("origen"), "ultima_metrica": um})
    doc = {"actualizado": iso(ahora()), "campeones": camp, "evolucion": evolucion(), "cambios": cambios,
           "candidatos": cands, "proxima_revision": proxima_revision(), "regla": REGLA}
    if informe:
        doc["ultimo_ciclo"] = {"inicio": informe.get("inicio"), "fin": informe.get("fin"), "segundos": informe.get("segundos"),
                               "presupuesto_min": informe.get("presupuesto_min"),
                               "adoptados": {t: i.get("adoptado") for t, i in informe["tareas"].items()},
                               "sin_tiempo": {t: i.get("sin_tiempo") for t, i in informe["tareas"].items() if i.get("sin_tiempo")},
                               "recalibracion": informe.get("recalibracion")}
    elif viejo.get("ultimo_ciclo"):
        doc["ultimo_ciclo"] = viejo["ultimo_ciclo"]
    escribir_json(BITACORA, doc)
    return doc


def estado():
    reg = leer_registro()
    for tarea, t in reg["tareas"].items():
        print(f"{tarea}: campeón {t['campeon']} (desde {t.get('desde')})  hoy: {t.get('modelo_hoy')}")
        for n, v in t["variantes"].items():
            ev = v.get("evaluacion") or {}
            vs = ev.get("vs_campeon") or {}
            print(f"   {v['estado']:10s} {n:22s} {METRICA[tarea]}={ev.get(METRICA[tarea])} "
                  f"dif={vs.get('diferencia')} ee={vs.get('ee')} rec={(vs.get('ventana_reciente') or {}).get('diferencia')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["ciclo", "evaluar", "agregar-candidato", "bitacora", "estado"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--presupuesto-min", type=float, default=60.0)
    ap.add_argument("--tareas", default=None)
    ap.add_argument("--sin-adoptar", action="store_true")
    ap.add_argument("--sims", type=int, default=N_SIMS)
    ap.add_argument("--validar-vueltas", action="store_true", help="ciclo: rehace validacion_vueltas.json (~40 min)")
    a = ap.parse_args()
    tareas = a.tareas.split(",") if a.tareas else None
    if tareas and set(tareas) - set(TAREAS):
        raise SystemExit(f"tareas válidas: {TAREAS}")
    if a.accion == "ciclo":
        ciclo(tareas, a.presupuesto_min, not a.sin_adoptar, a.sims, validar_vueltas=a.validar_vueltas)
    elif a.accion == "evaluar":
        leer_registro()
        ciclo(tareas, a.presupuesto_min, False, a.sims, solo_evaluar=True)
    elif a.accion == "agregar-candidato":
        agregar_candidato(a.args[0])
    elif a.accion == "bitacora":
        construir_bitacora()
        print(json.dumps(leer_json(BITACORA), ensure_ascii=False, indent=1)[:4000])
    else:
        estado()


if __name__ == "__main__":
    main()
