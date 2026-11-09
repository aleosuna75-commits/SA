#!/usr/bin/env python3
"""Orquestador genérico por GP (meeting_key de OpenF1): todo lo que se hizo a mano para México, paso a paso y solo.

Archivos por GP en gps/<slug>/ (slug = p. ej. "brasil2026") y doc de la base de datos del Artifact que les corresponde:
  gp.json           -> gp/<slug>           pronóstico de qualy (FP2 y luego FP3, con 'cambio')
  live_qualy.json   -> live/<slug>         snapshot del colector en vivo (live_qualy.py)
  post_qualy.json   -> postqualy/<slug>    cómo le fue al modelo en la qualy
  carrera.json      -> carrera/<slug>      pronóstico del orden final (simulador Monte Carlo oficial)
  vueltas.json      -> vueltas/<slug>      simulador vuelta a vuelta anclado (estrategias, undercut, rebases, SC)
  post_carrera.json -> postcarrera/<slug>  cómo le fue al modelo en la carrera (orden y estrategia)
  gps/meta.json     -> meta/actual         calendario, estado de cada GP y GP actual
Además: config.json (generado), ajustes.json (editable a mano: sustituciones, parrilla/penalizaciones, notas),
estado.json (pasos hechos, firmas de entrada, archivos) y logs/.

Pasos (idempotentes; cada uno sólo usa lo que existía antes de su sesión: F1_CORTE en los modelos):
  pre_qualy     tras la FP2: refresca datos, modelo de qualy FP1/FP2 (corte = inicio de la FP3)       -> gp.json
  fp3           tras la FP3: FP3 de OpenF1 o, si responde 401, reconstruida de live/crudo_fp3_<slug>.jsonl
                (fp3_desde_live.py); modelo --fp3 (corte = inicio de la qualy)                           -> gp.json (cambio)
  qualy_en_vivo imprime el comando exacto del colector (el relevo de live/<slug> lo hace el orquestador)
  post_qualy    qualy oficial (OpenF1) o último snapshot del colector; parrilla = ajustes.parrilla > OpenF1
                starting_grid > qualy + ajustes.penalizaciones; modelo de carrera (corte = inicio de la carrera);
                sim_vueltas anclado                                  -> post_qualy.json, carrera.json, vueltas.json
  post_carrera  resultado oficial de la carrera (OpenF1) + evaluación de estrategia -> post_carrera.json

Uso (desde f1_austin/):
  python3 gp_pipeline.py auto [--ahora ISO] [--simular]   # decide qué toca por hora UTC y estado; resumen JSON
  python3 gp_pipeline.py retro 1299                       # todos los pasos en orden para un GP ya corrido
  python3 gp_pipeline.py paso <paso> <meeting> [--forzar] # un paso suelto
  python3 gp_pipeline.py config <meeting>                 # sólo config.json (+ ajustes.json si no existe)
  python3 gp_pipeline.py meta                             # sólo gps/meta.json
  python3 gp_pipeline.py migrar_mexico                    # copia lo de México a gps/mexico2026/ (no borra nada)
  python3 gp_pipeline.py comandos <meeting>               # comandos del colector (FP3 y qualy) con rutas por slug
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
GPS_DIR = BASE / "gps"
CACHE = BASE / "cache"
LIVE = BASE / "live"
OPENF1 = "https://api.openf1.org/v1"
JOLPICA = "https://api.jolpi.ca/ergast/f1"
PY = sys.executable or "python3"
N_JOBS = "2"
PRIMER_MEETING = 1298            # la temporada multi-GP empieza en México 2026

DOCS = {"gp.json": "gp", "live_qualy.json": "live", "post_qualy.json": "postqualy", "carrera.json": "carrera",
        "vueltas.json": "vueltas", "post_carrera.json": "postcarrera"}
PASOS = ["pre_qualy", "fp3", "qualy_en_vivo", "post_qualy", "post_carrera"]

# ------------------------------------------------------------------------------------------------
# Textos en español
# ------------------------------------------------------------------------------------------------
NOMBRE_ES = {
    "Mexico City Grand Prix": "Gran Premio de la Ciudad de México", "São Paulo Grand Prix": "Gran Premio de São Paulo",
    "Sao Paulo Grand Prix": "Gran Premio de São Paulo", "Brazilian Grand Prix": "Gran Premio de Brasil",
    "Las Vegas Grand Prix": "Gran Premio de Las Vegas", "Qatar Grand Prix": "Gran Premio de Qatar",
    "Abu Dhabi Grand Prix": "Gran Premio de Abu Dhabi", "United States Grand Prix": "Gran Premio de Estados Unidos",
    "Miami Grand Prix": "Gran Premio de Miami", "Canadian Grand Prix": "Gran Premio de Canadá",
    "Spanish Grand Prix": "Gran Premio de España", "Barcelona-Catalunya Grand Prix": "Gran Premio de Barcelona-Cataluña",
    "Madrid Grand Prix": "Gran Premio de Madrid", "Monaco Grand Prix": "Gran Premio de Mónaco",
    "Austrian Grand Prix": "Gran Premio de Austria", "British Grand Prix": "Gran Premio de Gran Bretaña",
    "Belgian Grand Prix": "Gran Premio de Bélgica", "Hungarian Grand Prix": "Gran Premio de Hungría",
    "Dutch Grand Prix": "Gran Premio de los Países Bajos", "Italian Grand Prix": "Gran Premio de Italia",
    "Azerbaijan Grand Prix": "Gran Premio de Azerbaiyán", "Singapore Grand Prix": "Gran Premio de Singapur",
    "Japanese Grand Prix": "Gran Premio de Japón", "Chinese Grand Prix": "Gran Premio de China",
    "Australian Grand Prix": "Gran Premio de Australia", "Bahrain Grand Prix": "Gran Premio de Baréin",
    "Saudi Arabian Grand Prix": "Gran Premio de Arabia Saudita", "Emilia Romagna Grand Prix": "Gran Premio de Emilia-Romaña",
}
CIRCUITO_ES = {   # circuit_short_name de OpenF1 -> (nombre del circuito, nombre corto para textos)
    "Mexico City": ("Autódromo Hermanos Rodríguez", "México"),
    "Interlagos": ("Autódromo José Carlos Pace (Interlagos)", "Interlagos"),
    "Las Vegas": ("Circuito urbano de Las Vegas (Las Vegas Strip)", "Las Vegas"),
    "Lusail": ("Circuito Internacional de Lusail", "Lusail"),
    "Yas Marina Circuit": ("Circuito de Yas Marina", "Yas Marina"),
    "Austin": ("Circuit of the Americas", "Austin"),
}
CIUDAD_ES = {"Mexico City": "Ciudad de México", "São Paulo": "São Paulo, Brasil", "Las Vegas": "Las Vegas, Nevada",
             "Lusail": "Lusail, Qatar", "Yas Marina": "Abu Dhabi, Emiratos Árabes Unidos", "Yas Island": "Abu Dhabi, Emiratos Árabes Unidos",
             "Austin": "Austin, Texas"}
SLUG_PAIS = {"Mexico": "mexico", "Brazil": "brasil", "Qatar": "qatar", "United Arab Emirates": "abudhabi"}
TEMA = {"mexico": "muertos", "brasil": "brasil", "lasvegas": "lasvegas", "qatar": "qatar", "abudhabi": "abudhabi"}
CIRCUITO_JOLPICA = {9: "americas", 65: "rodriguez", 14: "interlagos", 152: "vegas", 150: "losail", 70: "yas_marina"}
SESION_ES = {"Practice 1": ("fp1", "Práctica 1"), "Practice 2": ("fp2", "Práctica 2"), "Practice 3": ("fp3", "Práctica 3"),
             "Qualifying": ("q", "Clasificación"), "Sprint Qualifying": ("sq", "Clasificación sprint"),
             "Sprint Shootout": ("sq", "Clasificación sprint"), "Sprint": ("sprint", "Sprint"), "Race": ("r", "Carrera")}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def ahora_utc():
    x = os.environ.get("GP_AHORA")
    return datetime.fromisoformat(x.replace("Z", "+00:00")) if x else datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _offset(gmt):
    """'-03:00:00' -> timedelta."""
    signo = -1 if str(gmt).startswith("-") else 1
    h, m, *_ = str(gmt).lstrip("+-").split(":")
    return signo * timedelta(hours=int(h), minutes=int(m))


def _hora12(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _utc_txt(gmt):
    td = _offset(gmt)
    m = int(td.total_seconds() // 60)
    s = "+" if m >= 0 else "−"
    m = abs(m)
    return f"UTC{s}{m // 60}" + (f":{m % 60:02d}" if m % 60 else "")


def leer_json(ruta, defecto=None):
    try:
        return json.loads(Path(ruta).read_text())
    except Exception:
        return defecto


def escribir_json(ruta, doc):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False))
    os.replace(tmp, ruta)


def firma(*objs):
    return hashlib.sha1(json.dumps(objs, sort_keys=True, default=str).encode()).hexdigest()[:12]


def http_json(url, timeout=60, intentos=4):
    """GET con reintentos (429/5xx). Devuelve (status, data|None). 401/403/404 no se reintentan."""
    ult = None
    for i in range(intentos):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                ult = r.status_code
                time.sleep(4 * (i + 1))
                continue
            if r.status_code != 200:
                return r.status_code, None
            d = r.json()
            if isinstance(d, dict) and "detail" in d:
                return 404, None
            return 200, d
        except requests.RequestException:
            ult = -1
            time.sleep(3 * (i + 1))
    return ult, None


# ------------------------------------------------------------------------------------------------
# Calendario (OpenF1) y configuración automática del GP
# ------------------------------------------------------------------------------------------------
def sesiones_temporada(año, refrescar=False):
    f = CACHE / f"sessions_{año}.json"
    if refrescar or not f.exists():
        st, d = http_json(f"{OPENF1}/sessions?year={año}")
        if st == 200 and d:
            f.write_text(json.dumps(d))
    return leer_json(f, []) or []


def sesiones_meeting(mk):
    for año in (2026, 2025, 2024, 2023):
        s = [x for x in sesiones_temporada(año) if x["meeting_key"] == mk]
        if s:
            return sorted(s, key=lambda x: x["date_start"])
    st, d = http_json(f"{OPENF1}/sessions?meeting_key={mk}")
    return sorted(d or [], key=lambda x: x["date_start"])


def info_meeting(mk):
    f = CACHE / f"meeting_{mk}.json"
    d = leer_json(f)
    if not d:
        st, d = http_json(f"{OPENF1}/meetings?meeting_key={mk}")
        if st == 200 and d:
            f.write_text(json.dumps(d))
    return (d or [{}])[0]


def circuito_jolpica(circuit_key, fecha_carrera, año):
    """circuit_key (OpenF1) -> circuitId (Jolpica): el mapeo aprendido de GPs ya corridos (como en
    modelo_qualy_austin.construir_dataset), luego el calendario de Jolpica por fecha de carrera, luego la tabla fija."""
    if circuit_key in CIRCUITO_JOLPICA:
        return CIRCUITO_JOLPICA[circuit_key]
    try:
        import modelo_qualy_austin as Q
        ses = Q.tabla_sesiones()
        jr = Q.tabla_jolpica("results")
        carreras = ses[(ses.session_name == "Race") & (ses.circuit_key == circuit_key)]
        for _, r in carreras.iterrows():
            m = jr[jr.date == r.date_start.normalize().tz_localize(None)]
            if len(m):
                return m.circuit.iloc[0]
    except Exception:
        pass
    f = CACHE / f"jolpica_calendario_{año}.json"
    d = leer_json(f)
    if not d:
        st, d = http_json(f"{JOLPICA}/{año}.json?limit=100")
        if st == 200 and d:
            f.write_text(json.dumps(d))
    for r in ((d or {}).get("MRData", {}).get("RaceTable", {}).get("Races", [])):
        if r.get("date") == fecha_carrera[:10]:
            return r["Circuit"]["circuitId"]
    return None


def slug_de(info, ses0):
    pais = info.get("country_name") or ses0.get("country_name", "")
    loc = info.get("location") or ses0.get("location", "")
    base = SLUG_PAIS.get(pais)
    if not base:
        base = "".join(ch for ch in _sin_acentos(loc).lower() if ch.isalnum()) or f"gp{ses0['meeting_key']}"
    return base


def config_gp(mk, escribir=True):
    ses = sesiones_meeting(mk)
    if not ses:
        raise SystemExit(f"OpenF1 no tiene sesiones para el meeting {mk}")
    info = info_meeting(mk)
    s0 = ses[0]
    año = int(s0["year"])
    slug_m = slug_de(info, s0)
    slug = f"{slug_m}{año}"
    gmt = s0.get("gmt_offset") or info.get("gmt_offset") or "00:00:00"
    off = _offset(gmt)
    nombre_en = info.get("meeting_name") or f"{s0.get('country_name', '')} Grand Prix"
    nombre = NOMBRE_ES.get(nombre_en) or ("Gran Premio de " + nombre_en.replace(" Grand Prix", ""))
    corto = s0.get("circuit_short_name", "")
    circ, circ_corto = CIRCUITO_ES.get(corto, (info.get("circuit_short_name") or corto, corto))
    ciudad = CIUDAD_ES.get(s0.get("location", ""), f"{s0.get('location', '')}, {s0.get('country_name', '')}")
    sesiones = []
    for s in ses:
        if s.get("is_cancelled"):
            continue
        clave, nom = SESION_ES.get(s["session_name"], (s["session_name"].lower().replace(" ", "_"), s["session_name"]))
        ini = ts(s["date_start"])
        loc = ini + off
        sesiones.append({"clave": clave, "nombre": nom, "nombre_en": s["session_name"], "session_key": s["session_key"],
                         "inicio_utc": iso(ini), "fin_utc": iso(ts(s["date_end"])) if s.get("date_end") else None,
                         "fecha_local": f"{DIAS[loc.weekday()].capitalize()} {loc.day} de {MESES[loc.month - 1]}",
                         "hora_local": _hora12(loc)})
    q = next((s for s in sesiones if s["clave"] == "q"), None)
    r = next((s for s in sesiones if s["clave"] == "r"), None)
    if mk in (1297, 1298):     # entradas fijas de modelo_qualy_austin.GPS (no se cambian sus slugs de archivos)
        import modelo_qualy_austin as Q
        slug_m = Q.GPS[mk]["slug"]
    cfg = {
        "meeting_key": mk, "year": año, "slug": slug, "slug_modelo": slug_m, "nombre": nombre, "nombre_en": nombre_en,
        "circuito": circ, "circuito_corto": circ_corto, "ciudad": ciudad, "pais": s0.get("country_name"),
        "circuit_key": s0.get("circuit_key"),
        "circuito_jolpica": circuito_jolpica(s0.get("circuit_key"), r["inicio_utc"] if r else s0["date_start"], año),
        "gmt_offset": gmt, "utc_texto": _utc_txt(gmt),
        "fecha_texto": (f"{q['fecha_local']} de {año}" if q else ""),
        "hora_texto": (f"{q['hora_local']} (hora local, {_utc_txt(gmt)})" if q else ""),
        "fecha_texto_carrera": (f"{r['fecha_local']} de {año}" if r else ""),
        "hora_texto_carrera": (f"{r['hora_local']} (hora local, {_utc_txt(gmt)})" if r else ""),
        "tema": TEMA.get(slug_m, "generico"),
        "sprint": any(s["clave"] in ("sprint", "sq") for s in sesiones),
        "sesiones": sesiones,
        "generado": iso(ahora_utc()),
    }
    if escribir:
        d = GPS_DIR / slug
        (d / "logs").mkdir(parents=True, exist_ok=True)
        viejo = leer_json(d / "config.json", {})
        if {k: v for k, v in viejo.items() if k != "generado"} != {k: v for k, v in cfg.items() if k != "generado"}:
            escribir_json(d / "config.json", cfg)
        if not (d / "ajustes.json").exists():
            escribir_json(d / "ajustes.json", {"sustituciones": {}, "penalizaciones": {}, "parrilla": {}, "notas": [],
                                               "fuentes": []})
    return cfg


def sesion(cfg, clave):
    return next((s for s in cfg["sesiones"] if s["clave"] == clave), None)


def directorio(cfg):
    d = GPS_DIR / cfg["slug"]
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return d


def ajustes(cfg):
    a = leer_json(GPS_DIR / cfg["slug"] / "ajustes.json", {}) or {}
    for k in ("sustituciones", "penalizaciones", "parrilla"):
        a[k] = a.get(k) or {}
    return a


# ------------------------------------------------------------------------------------------------
# Estado por GP
# ------------------------------------------------------------------------------------------------
def leer_estado(cfg):
    return leer_json(GPS_DIR / cfg["slug"] / "estado.json", {"slug": cfg["slug"], "meeting_key": cfg["meeting_key"],
                                                              "pasos": {}}) or {"pasos": {}}


def marcar(cfg, paso, **info):
    e = leer_estado(cfg)
    e.setdefault("pasos", {})[paso] = {"hecho": iso(ahora_utc()), **info}
    e["slug"], e["meeting_key"] = cfg["slug"], cfg["meeting_key"]
    escribir_json(GPS_DIR / cfg["slug"] / "estado.json", e)


def hecho(cfg, paso):
    return paso in leer_estado(cfg).get("pasos", {})


def correr(cmd, log, env_extra=None, timeout=3600):
    """Corre un comando (lista) desde f1_austin/ con salida a log. Lanza RuntimeError si falla."""
    env = {**os.environ, "F1_N_JOBS": N_JOBS, "PYTHONUNBUFFERED": "1", **(env_extra or {})}
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(log, "a") as fh:
        fh.write(f"\n### {iso(ahora_utc())} {' '.join(map(str, cmd))}  env={env_extra or {}}\n")
        fh.flush()
        p = subprocess.run([str(c) for c in cmd], cwd=BASE, env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
    print(f"  [{time.time() - t0:5.0f} s] {' '.join(map(str, cmd[1:3]))} ... -> {log.name} (rc={p.returncode})", flush=True)
    if p.returncode != 0:
        raise RuntimeError(f"falló {' '.join(map(str, cmd))} (ver {log})")


def copiar_si_cambia(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return False
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


# ------------------------------------------------------------------------------------------------
# Datos
# ------------------------------------------------------------------------------------------------
def refrescar_datos(cfg, log):
    """descarga_datos.py gp <año> <mk> <circuito_jolpica>: temporada en curso + GP objetivo + historial del circuito."""
    correr([PY, "descarga_datos.py", "gp", cfg["year"], cfg["meeting_key"], cfg["circuito_jolpica"] or "americas"], log)


def laps_validas(sk, minimo=10):
    d = leer_json(CACHE / f"laps_{sk}.json", [])
    return isinstance(d, list) and len({x.get("driver_number") for x in d}) >= minimo


def resultado_sesion(sk, refrescar=True, preferir_red=False):
    """session_result de OpenF1 de una sesión (lista) o None (401/404/incompleto). Cache: cache/session_result_<sk>.json.
    preferir_red: pedirlo de nuevo aunque esté en cache (en vivo: descalificaciones/penalizaciones posteriores)."""
    f = CACHE / f"session_result_{sk}.json"
    d = leer_json(f)
    if isinstance(d, list) and len(d) >= 15 and not preferir_red:
        return d
    if refrescar or preferir_red:
        st, d = http_json(f"{OPENF1}/session_result?session_key={sk}")
        if st == 200 and isinstance(d, list) and len(d) >= 15:
            f.write_text(json.dumps(d))
            return d
    d = leer_json(f)
    if isinstance(d, list) and len(d) >= 15:
        return d
    # resultados de la temporada ya en cache (descarga_datos.py)
    for año in (2026, 2025, 2024, 2023):
        r = [x for x in (leer_json(CACHE / f"results_{año}.json", []) or []) if x.get("session_key") == sk]
        if len(r) >= 15:
            return r
    return None


def pilotos_meeting(cfg):
    """{driver_number: {acr, nombre, equipo, color}} del GP (última sesión con lista), con sustituciones de ajustes."""
    import modelo_qualy_austin as Q
    pil = Q.tabla_pilotos()
    pil = pil[pil.meeting_key == cfg["meeting_key"]]
    orden = {s["session_key"]: i for i, s in enumerate(cfg["sesiones"])}
    pil = pil.assign(o=pil.session_key.map(orden).fillna(-1)).sort_values("o")
    out = {}
    for r in pil.itertuples():
        out[int(r.driver_number)] = {"acr": r.name_acronym, "nombre": _nombre(r.full_name), "equipo": r.team_name,
                                     "color": _color(r.team_colour)}
    return out


def _nombre(full):
    if not isinstance(full, str):
        return None
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in full.split())


def _color(c):
    if not isinstance(c, str) or not c.strip():
        return "888888"
    return c.strip().lstrip("#").upper()


def _num(x, nd=None):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd) if nd is not None else x


def _spearman(a, b):
    from scipy.stats import spearmanr
    if len(a) < 3:
        return None
    return _num(spearmanr(a, b).correlation, 3)


# ------------------------------------------------------------------------------------------------
# Paso 1: pre_qualy (tras la FP2)
# ------------------------------------------------------------------------------------------------
def corte_de(cfg, *claves):
    for c in claves:
        s = sesion(cfg, c)
        if s:
            return s["inicio_utc"]
    return None


def paso_pre_qualy(cfg, retro=False, forzar=False):
    d = directorio(cfg)
    log = d / "logs" / "pre_qualy.log"
    mk, sm = cfg["meeting_key"], cfg["slug_modelo"]
    if not retro:
        refrescar_datos(cfg, log)
    fp = [s["session_key"] for s in cfg["sesiones"] if s["clave"] in ("fp1", "fp2")]
    if not any(laps_validas(sk) for sk in fp):
        raise RuntimeError("sin vueltas de FP1/FP2 en cache (OpenF1 aún no las publica o respondió 401)")
    # corte: lo anterior a la sesión siguiente a la FP2 (FP3, o la qualy/sprint en fines de semana sprint)
    corte = corte_de(cfg, "fp3", "sq", "q")
    correr([PY, "modelo_qualy_austin.py", mk, "--jobs", N_JOBS], log, {"F1_CORTE": corte, "F1_SIN_HTML": "1"})
    import exportar_datos_web as E
    doc, R = E.construir(BASE / f"resultado_qualy_{sm}.pkl")
    escribir_json(d / "gp_fp2.json", doc)
    E.escribir(doc, d / "gp.json")
    marcar(cfg, "pre_qualy", corte=corte, modelo=doc["modelo"], top10=[p["acr"] for p in doc["pilotos"][:10]],
           archivos=["gp.json"])
    return ["gp.json"]


# ------------------------------------------------------------------------------------------------
# Paso 2: fp3 (tras la FP3)
# ------------------------------------------------------------------------------------------------
def fp3_desde_openf1(sk):
    """Re-baja laps/stints/weather de la FP3. Devuelve (ok, status)."""
    st, d = http_json(f"{OPENF1}/laps?session_key={sk}")
    if st != 200 or not d or len({x.get("driver_number") for x in d}) < 10:
        return False, st
    (CACHE / f"laps_{sk}.json").write_text(json.dumps(d))
    for nombre, ep in (("stints", "stints"), ("weather", "weather")):
        st2, d2 = http_json(f"{OPENF1}/{ep}?session_key={sk}")
        (CACHE / f"{nombre}_{sk}.json").write_text(json.dumps(d2 if st2 == 200 and d2 else []))
    return True, st


def paso_fp3(cfg, retro=False, forzar=False):
    d = directorio(cfg)
    log = d / "logs" / "fp3.log"
    mk, sm = cfg["meeting_key"], cfg["slug_modelo"]
    s3 = sesion(cfg, "fp3")
    if not s3:
        marcar(cfg, "fp3", nota="fin de semana sin FP3 (sprint): no aplica", archivos=[])
        return []
    sk = s3["session_key"]
    fuente = "OpenF1 (cache)"
    if not retro or not laps_validas(sk):
        ok, st = fp3_desde_openf1(sk)
        fuente = "OpenF1"
        if not ok:
            crudo = LIVE / f"crudo_fp3_{cfg['slug']}.jsonl"
            if not crudo.exists():
                raise RuntimeError(f"OpenF1 respondió {st} para la FP3 {sk} y no existe {crudo.relative_to(BASE)} "
                                   "(grabación del colector durante la FP3)")
            tmp = d / "fp3_live"
            correr([PY, "fp3_desde_live.py", "--sk", sk, "--mk", mk, "--salida", tmp, crudo], log)
            for n in ("laps", "stints", "weather"):
                shutil.copyfile(tmp / f"{n}_{sk}.json", CACHE / f"{n}_{sk}.json")
            fuente = f"reconstruida del live timing ({crudo.name}; OpenF1 {st})"
        if not retro:   # pilotos/resultados del GP (la lista de la FP3 define titulares); si OpenF1 falla, queda la FP2
            for nombre, ep in ((f"drivers_{cfg['year']}", "drivers"), (f"results_{cfg['year']}", "session_result")):
                st2, x = http_json(f"{OPENF1}/{ep}?meeting_key={mk}")
                if st2 == 200 and x:
                    f = CACHE / f"{nombre}.json"
                    viejo = [y for y in (leer_json(f, []) or []) if y.get("meeting_key") != mk]
                    f.write_text(json.dumps(viejo + x))
    if not laps_validas(sk):
        raise RuntimeError("la FP3 no tiene vueltas de ≥10 pilotos")
    corte = corte_de(cfg, "q")
    correr([PY, "modelo_qualy_austin.py", mk, "--fp3", "--jobs", N_JOBS], log, {"F1_CORTE": corte, "F1_SIN_HTML": "1"})
    import exportar_datos_web as E
    previo = BASE / f"resultado_qualy_{sm}.pkl"
    doc, R = E.construir(BASE / f"resultado_qualy_{sm}_fp3.pkl", previo if previo.exists() else None)
    escribir_json(d / "gp_fp3.json", doc)
    E.escribir(doc, d / "gp.json")
    marcar(cfg, "fp3", corte=corte, fuente=fuente, modelo=doc["modelo"],
           top10=[p["acr"] for p in doc["pilotos"][:10]], archivos=["gp.json"])
    return ["gp.json"]


# ------------------------------------------------------------------------------------------------
# Paso 3: qualy en vivo (sólo comandos)
# ------------------------------------------------------------------------------------------------
def comandos_colector(cfg):
    slug, mk = cfg["slug"], cfg["meeting_key"]
    q, s3 = sesion(cfg, "q"), sesion(cfg, "fp3")
    out = {}
    if q:
        hq = ts(q["inicio_utc"])
        out["qualy"] = {
            "lanzar_utc": iso(hq - timedelta(minutes=10)),
            "comando": (f"cd {BASE} && python3 live_qualy.py --salida gps/{slug}/live_qualy.json --minutos 80 "
                        f"--grabar live/crudo_qualy_{slug}.jsonl --precargar live/crudo_qualy_{slug}.jsonl "
                        f"--hora-inicio {iso(hq)} --log gps/{slug}/logs/colector_qualy.log"),
            "relevo": f"gps/{slug}/live_qualy.json -> doc live/{slug} cada ~60-90 s hasta ~{iso(hq + timedelta(minutes=65))}",
            "prueba": f"cd {BASE} && python3 live_qualy.py --cualquier-sesion --minutos 3 --salida /tmp/prueba_colector.json",
        }
    if s3:
        h3 = ts(s3["inicio_utc"])
        out["fp3"] = {
            "lanzar_utc": iso(h3 - timedelta(minutes=10)),
            "comando": (f"cd {BASE} && python3 live_qualy.py --cualquier-sesion --minutos 75 "
                        f"--salida live/fp3_{slug}.json --grabar live/crudo_fp3_{slug}.jsonl "
                        f"--precargar live/crudo_fp3_{slug}.jsonl --hora-inicio {iso(h3)} "
                        f"--log gps/{slug}/logs/colector_fp3.log"),
            "para_que": "respaldo si OpenF1 responde 401 tras la FP3: el paso fp3 la reconstruye con fp3_desde_live.py",
        }
    return out


def _fmt(t):
    if t is None or (isinstance(t, float) and math.isnan(t)):
        return None
    m, s = divmod(float(t), 60)
    return f"{int(m)}:{s:06.3f}"


def live_desde_oficial(cfg, qualy, pil):
    """Snapshot final con la forma de live/qualy_<slug>.json armado con la clasificación oficial de OpenF1 (para GPs
    sin colector en vivo, p. ej. Brasil en retro): tiempos por segmento, eliminados, vueltas y diferencias."""
    n2a = {k: v["acr"] for k, v in pil.items()}
    sust = ajustes(cfg)["sustituciones"]
    filas = sorted(qualy, key=lambda x: (x.get("position") or 99, x["driver_number"]))
    seg = lambda x: (x.get("duration") if isinstance(x.get("duration"), list) else [x.get("duration"), None, None]) + [None] * 3
    mejores = [min((seg(x)[i] for x in filas if seg(x)[i]), default=None) for i in range(3)]
    pilotos = []
    for k, x in enumerate(filas, 1):
        t = seg(x)[:3]
        ult = max((i for i in range(3) if t[i]), default=None)
        a = n2a.get(int(x["driver_number"]))
        pilotos.append({"acr": sust.get(a, a), "num": int(x["driver_number"]), "pos": k,
                        "mejor": _fmt(min((v for v in t if v), default=None)), "q1": _fmt(t[0]), "q2": _fmt(t[1]), "q3": _fmt(t[2]),
                        "eliminado_en": None if k <= 10 else (2 if k <= 16 else 1), "en_pits": False,
                        "vueltas": x.get("number_of_laps"),
                        "dif": None if (ult is None or k == 1) else f"+{t[ult] - mejores[ult]:.3f}", "neumatico": None})
    q = sesion(cfg, "q")
    return {"actualizado": (q or {}).get("fin_utc") or iso(ahora_utc()), "estado": "terminada", "segmento": 3, "reloj": "00:00",
            "fuente": "OpenF1 (clasificación oficial; sin seguimiento en vivo)",
            "detalle": "Qualy terminada (oficial). Este GP no se siguió en vivo: snapshot armado después con OpenF1.",
            "sesion": {"key": (q or {}).get("session_key"), "nombre": "Qualifying", "tipo": "Qualifying",
                       "gp": cfg.get("nombre_en"), "meeting_key": cfg["meeting_key"], "estado_feed": "Finalised"},
            "pista": {"estado": "1", "mensaje": "AllClear"}, "corte": None, "mensajes": [],
            "colector": {"conectado": False, "reconexiones": 0, "ultimo_dato": None, "mensajes": 0, "errores": 0,
                         "version": "oficial"},
            "pilotos": pilotos}


def paso_qualy_en_vivo(cfg, retro=False, forzar=False):
    c = comandos_colector(cfg)
    if retro:
        d = directorio(cfg)
        src = LIVE / "qualy_mexico.json" if cfg["meeting_key"] == 1298 else None
        archivos = ["live_qualy.json"] if src and copiar_si_cambia(src, d / "live_qualy.json") else []
        nota = "retro: copiado del colector" if archivos else "retro: no hubo colector"
        if not (d / "live_qualy.json").exists():
            q = resultado_sesion(sesion(cfg, "q")["session_key"], refrescar=True)
            if q:
                escribir_json(d / "live_qualy.json", live_desde_oficial(cfg, q, pilotos_meeting(cfg)))
                archivos, nota = ["live_qualy.json"], "retro: snapshot final armado con la clasificación oficial de OpenF1"
        marcar(cfg, "qualy_en_vivo", nota=nota, archivos=archivos)
        return archivos
    print("Colector de la qualy (lo lanza y releva el orquestador):\n  " + c.get("qualy", {}).get("comando", "-"))
    marcar(cfg, "qualy_en_vivo", comando=c.get("qualy", {}).get("comando"), archivos=[])
    return []


# ------------------------------------------------------------------------------------------------
# Paso 4: post_qualy
# ------------------------------------------------------------------------------------------------
def _seg(t):
    """'1:16.514' -> 76.514"""
    if not t:
        return None
    try:
        m, s = str(t).split(":") if ":" in str(t) else ("0", t)
        return round(int(m) * 60 + float(s), 3)
    except ValueError:
        return None


def qualy_desde_colector(cfg):
    """Último snapshot del colector -> lista con forma de session_result (driver_number, position, duration)."""
    snap = leer_json(directorio(cfg) / "live_qualy.json")
    if not snap or not snap.get("pilotos"):
        return None, None
    out = []
    for p in snap["pilotos"]:
        out.append({"driver_number": p.get("num"), "position": p.get("pos"),
                    "duration": [_seg(p.get("q1")), _seg(p.get("q2")), _seg(p.get("q3"))],
                    "dnf": False, "dns": False, "dsq": False, "meeting_key": cfg["meeting_key"]})
    return (out if len(out) >= 15 else None), snap.get("estado")


def parrilla_oficial(cfg, retro=False):
    """OpenF1 starting_grid (session_key = la qualy) -> cache/starting_grid_<mk>.json (lo lee modelo_carrera_austin)."""
    q = sesion(cfg, "q")
    f = CACHE / f"starting_grid_{cfg['meeting_key']}.json"
    g = leer_json(f)
    # en vivo se vuelve a pedir siempre (la parrilla puede cambiar por penalizaciones); en retro basta la cache
    if (not retro or not (isinstance(g, list) and len(g) >= 15)) and q:
        st, g = http_json(f"{OPENF1}/starting_grid?session_key={q['session_key']}")
        if st == 200 and isinstance(g, list) and len(g) >= 15:
            f.write_text(json.dumps(g))
    g = leer_json(f)
    return g if isinstance(g, list) and len(g) >= 15 else None


def doc_post_qualy(cfg, gp_doc, qualy, pil):
    """Evaluación del pronóstico de qualy (último gp.json) contra la clasificación (forma de live/post_qualy.json)."""
    n2a = {k: v["acr"] for k, v in pil.items()}
    sust = ajustes(cfg)["sustituciones"]
    real = {}
    for x in sorted(qualy, key=lambda x: (x.get("position") or 99, x["driver_number"])):
        a = n2a.get(int(x["driver_number"]))
        a = sust.get(a, a)
        if a and a not in real:
            real[a] = len(real) + 1
    pred = {p["acr"]: p["pred"] for p in gp_doc["pilotos"]}
    for a in pred:                      # sin resultado: al fondo
        real.setdefault(a, len(real) + 1)
    info = {p["acr"]: p for p in gp_doc["pilotos"]}
    comunes = [a for a in pred if a in real]
    n = len(comunes)
    rk_real = {a: i + 1 for i, a in enumerate(sorted(comunes, key=lambda a: real[a]))}
    rk_pred = {a: i + 1 for i, a in enumerate(sorted(comunes, key=lambda a: pred[a]))}
    top_p = [a for a in sorted(comunes, key=lambda a: rk_pred[a])][:10]
    top_r = [a for a in sorted(comunes, key=lambda a: rk_real[a])][:10]
    c2, c1 = 10, 16                     # cortes de Q3/Q2 (22 autos: eliminan 6 y 6)
    q1p = {a for a in comunes if rk_pred[a] > c1}
    q1r = {a for a in comunes if rk_real[a] > c1}
    q2p = {a for a in comunes if c2 < rk_pred[a] <= c1}
    q2r = {a for a in comunes if c2 < rk_real[a] <= c1}
    filas = []
    for a in sorted(comunes, key=lambda a: rk_real[a]):
        i = info.get(a, {})
        filas.append({"acr": a, "nombre": i.get("nombre"), "equipo": i.get("equipo"), "color": i.get("color", "888888"),
                      "pred": rk_pred[a], "real": rk_real[a], "dif": rk_pred[a] - rk_real[a]})
    mae = sum(abs(f["dif"]) for f in filas) / max(n, 1)
    sp = _spearman([f["pred"] for f in filas], [f["real"] for f in filas])
    ac = len(set(top_p) & set(top_r))
    pole_r, pole_p = top_r[0], top_p[0]
    fuera = [a for a in top_r if a not in top_p]
    nom = lambda a: (info.get(a, {}).get("nombre") or a)
    txt = [f"El modelo ({gp_doc.get('fase', '')}) acertó {ac} de los 10 que llegaron a la Q3"
           + (f" (se le escaparon {', '.join(nom(a) for a in fuera)})." if 0 < len(fuera) <= 3 else ".")]
    if pole_r == pole_p:
        txt.append(f"Acertó la pole: {nom(pole_r)}.")
    else:
        pp = info.get(pole_r, {}).get("p_pole")
        txt.append(f"La pole fue para {nom(pole_r)}, a quien el modelo veía P{rk_pred[pole_r]}"
                   + (f" con {pp * 100:.0f}% de probabilidad." if pp is not None else "."))
    sorpresa = max(filas, key=lambda f: abs(f["dif"]))
    if abs(sorpresa["dif"]) >= 5:
        txt.append(f"La mayor sorpresa: {nom(sorpresa['acr'])} (pronóstico P{sorpresa['pred']}, real P{sorpresa['real']}).")
    txt.append(f"Error medio de {mae:.2f} lugares y correlación de {sp:.3f}." if sp is not None else
               f"Error medio de {mae:.2f} lugares.")
    return {"actualizado": iso(ahora_utc()), "aciertos_top10": ac, "top10_pred": top_p, "top10_real": top_r,
            "pole_pred": pole_p, "pole_real": pole_r, "acierto_pole": pole_p == pole_r,
            "q1_fuera_aciertos": len(q1p & q1r), "q1_fuera_total": len(q1r),
            "q2_fuera_aciertos": len(q2p & q2r), "q2_fuera_total": len(q2r),
            "mae": round(mae, 2), "spearman": sp, "exactos": sum(1 for f in filas if f["dif"] == 0),
            "filas": filas, "resumen": " ".join(txt)}


def nota_parrilla(dc, qualy, pil, aj):
    """Agrega a parrilla_fuente los cambios de la parrilla respecto a la qualy (penalizaciones, salidas desde pits)."""
    n2a = {k: v["acr"] for k, v in pil.items()}
    orden = [aj["sustituciones"].get(n2a.get(int(x["driver_number"])), n2a.get(int(x["driver_number"])))
             for x in sorted(qualy, key=lambda x: (x.get("position") or 99, x["driver_number"]))]
    qpos = {a: i + 1 for i, a in enumerate(a for a in orden if a)}
    movs = sorted(((qpos[p["acr"]], p["salida"], p["acr"]) for p in dc.get("pilotos", [])
                   if p["acr"] in qpos and p.get("salida") and p["salida"] - qpos[p["acr"]] >= 2))
    base = dc.get("parrilla_fuente") or ""
    if movs and "cambios respecto a la qualy" not in base:
        base += " (cambios respecto a la qualy: " + ", ".join(f"{a} {q}.º → {s}.º" for q, s, a in movs) + ")"
    return base


def nota_orden_vueltas(d):
    """Si el vuelta a vuelta (anclado) no reproduce exactamente el orden oficial, lo dice en su resumen (como en México)."""
    v, c = leer_json(d / "vueltas.json"), leer_json(d / "carrera.json")
    if not v or not c:
        return
    of = [x["acr"] for x in sorted(v["orden_final"], key=lambda x: x["pred"])]
    oc = [p["acr"] for p in sorted(c["pilotos"], key=lambda p: p["pred"])]
    if of[:10] == oc[:10] or "orden final oficial" in v.get("resumen", ""):
        return
    pares = [f"{oc[i]}/{oc[i + 1]}" for i in range(min(10, len(oc) - 1)) if of[i] == oc[i + 1] and of[i + 1] == oc[i]]
    v["resumen"] += (" El orden final oficial de la página es el del simulador principal (validó mejor)"
                     + (f"; aquí {', '.join(pares)} aparecen invertidos porque en ambos modelos son prácticamente empates."
                        if pares else "; el vuelta a vuelta sólo lo aproxima (posiciones medias casi empatadas)."))
    escribir_json(d / "vueltas.json", v)


def paso_post_qualy(cfg, retro=False, forzar=False):
    d = directorio(cfg)
    log = d / "logs" / "post_qualy.log"
    mk, sm = cfg["meeting_key"], cfg["slug_modelo"]
    q = sesion(cfg, "q")
    aj = ajustes(cfg)
    # 1) clasificación: oficial de OpenF1 o el último snapshot del colector
    qualy = resultado_sesion(q["session_key"], refrescar=True, preferir_red=not retro)
    fuente_q = "OpenF1 session_result (oficial)"
    if qualy is None:
        qualy, est = qualy_desde_colector(cfg)
        fuente_q = f"último snapshot del colector en vivo (estado {est}; provisional)"
    if qualy is None:
        raise RuntimeError("no hay clasificación: OpenF1 sin session_result y sin gps/<slug>/live_qualy.json")
    (CACHE / f"qualy_real_{mk}.json").write_text(json.dumps(qualy))
    # 2) parrilla: ajustes.parrilla (a mano) > OpenF1 starting_grid > qualy + ajustes.penalizaciones
    args, fuente_p = [], None
    grid = parrilla_oficial(cfg, retro)
    if aj["parrilla"]:
        args = ["--parrilla", json.dumps(aj["parrilla"])]
        fuente_p = "Parrilla indicada en ajustes.json"
    elif grid:
        fuente_p = "Parrilla oficial (OpenF1 starting_grid)"
    elif aj["penalizaciones"]:
        args = ["--penalizaciones", json.dumps(aj["penalizaciones"])]
        fuente_p = "Qualy + penalizaciones de ajustes.json"
    else:
        fuente_p = "Orden de la qualy (sin penalizaciones conocidas)"
    fir = firma(qualy, grid, aj)
    previo = leer_estado(cfg)["pasos"].get("post_qualy", {})
    if previo.get("firma") == fir and not forzar and (d / "carrera.json").exists():
        print("  post_qualy: entradas sin cambios; nada que hacer")
        return []
    pil = pilotos_meeting(cfg)
    gp_doc = leer_json(d / "gp.json")
    cambiados = []
    if gp_doc:
        pq = doc_post_qualy(cfg, gp_doc, qualy, pil)
        if not fuente_q.startswith("OpenF1"):     # mismo esquema que live/post_qualy.json: la fuente va en el texto
            pq["resumen"] = "Provisional (último dato del cronometraje en vivo; falta la clasificación oficial). " + pq["resumen"]
        escribir_json(d / "post_qualy.json", pq)
        cambiados.append("post_qualy.json")
    # 3) modelo de carrera (corte: inicio de la carrera) en un directorio de trabajo del GP
    trabajo = d / "trabajo_carrera"
    corte = corte_de(cfg, "r")
    correr([PY, "modelo_carrera_austin.py", mk, "--prueba", trabajo] + args, log, {"F1_CORTE": corte})
    dc = leer_json(trabajo / "datos_carrera.json")
    dc["parrilla_fuente"] = nota_parrilla(dc, qualy, pil, aj)
    notas = [n for n in aj.get("notas", []) if n]
    if notas:
        dc["parrilla_fuente"] = f"{dc.get('parrilla_fuente') or fuente_p}. " + " ".join(notas)
    escribir_json(d / "carrera.json", dc)
    cambiados.append("carrera.json")
    # 4) vuelta a vuelta anclado al orden oficial
    try:
        correr([PY, "sim_vueltas.py", "gp", "--meeting", mk, "--dataset", trabajo / "dataset_carrera.csv",
                "--objetivo", trabajo / f"prediccion_carrera_{sm}_2026.csv", "--salida", d / "vueltas.json",
                "--lugar", cfg.get("circuito_corto") or cfg["ciudad"], "--sims", "4000"], log, {"F1_CORTE": corte})
        nota_orden_vueltas(d)
        cambiados.append("vueltas.json")
    except Exception as e:
        print("  AVISO: sim_vueltas falló:", e)
    marcar(cfg, "post_qualy", firma=fir, fuente_qualy=fuente_q, fuente_parrilla=dc.get("parrilla_fuente"),
           oficial=fuente_q.startswith("OpenF1"), corte=corte,
           top10_carrera=[p["acr"] for p in dc["pilotos"][:10]], archivos=cambiados)
    return cambiados


# ------------------------------------------------------------------------------------------------
# Paso 5: post_carrera
# ------------------------------------------------------------------------------------------------
def evaluar_estrategia(cfg, vueltas_doc, race_sk, n2a):
    """Paradas y vuelta de la 1.ª parada pronosticadas (vueltas.json) vs reales; rebases en pista reales con la misma
    definición que el simulador (sim_vueltas.eventos_pista)."""
    nulo = {"paradas_acierto": None, "mae_vuelta_parada": None, "rebases_reales": None,
            "nota": "Sin datos de vueltas/stints de la carrera en OpenF1 o sin pronóstico vuelta a vuelta."}
    try:
        import sim_vueltas as S
        correr([PY, "descarga_carreras.py"], directorio(cfg) / "logs" / "post_carrera.log")
        from descarga_datos import get
        get(f"{OPENF1}/race_control?session_key={race_sk}", f"race_rc_{race_sk}", pausa=0.7)
        h, _ = S.actualizar_hist()
        c = h["datos"].get(race_sk)
    except Exception as e:
        nulo["nota"] += f" ({e})"
        return nulo
    if c is None:
        return nulo
    # cambios de neumático con bandera roja no son paradas; la 1.ª parada se compara sin las de la vuelta 1-2 (daños)
    roja = {v for e in c.get("eventos", []) if e["tipo"] == "RED" for v in range(e["ini"], e["fin"] + 1)}
    reales = {}
    for dn, e in c["estrategia"].items():
        vp = [v for v in e["vueltas_parada"] if v not in roja]
        reales[n2a.get(int(dn))] = {**e, "paradas": len(vp), "vueltas_parada": vp,
                                    "primera": next((v for v in vp if v > 2), None)}
    rebases = int(sum(c["reb_gan"])) if c.get("reb_gan") is not None else None
    mojada = bool(c.get("mojada"))
    n_sc = sum(1 for e in c.get("eventos", []) if e["tipo"] in ("SC", "VSC"))
    if not vueltas_doc:
        nulo.update(rebases_reales=rebases, nota="Sin pronóstico vuelta a vuelta para comparar paradas.")
        return nulo
    ok, err, n = 0, [], 0
    for e in vueltas_doc.get("estrategias", []):
        r = reales.get(e["acr"])
        if not r or not r["termina"]:
            continue
        n += 1
        ok += int(e.get("paradas") == r["paradas"])
        if e.get("vueltas_parada") and r["primera"]:
            err.append(abs(e["vueltas_parada"][0] - r["primera"]))
    esp = (vueltas_doc.get("rebases") or {}).get("total_esperado")
    p10p90 = (vueltas_doc.get("rebases") or {}).get("total_p10_p90")
    planes_r = {}
    for a, r in reales.items():
        if r and r["termina"]:
            planes_r[r["paradas"]] = planes_r.get(r["paradas"], 0) + 1
    tipico = max(planes_r, key=planes_r.get) if planes_r else None
    nota = (f"Paradas: el plan más probable del simulador acertó el número de paradas de {ok}/{n} pilotos que terminaron"
            + (f"; lo más común en la carrera fue {tipico} parada{'s' if tipico != 1 else ''}" if tipico is not None else "")
            + (f". Primera parada: error medio de {sum(err) / len(err):.1f} vueltas ({len(err)} pilotos)" if err else "")
            + (f". Rebases en pista: {rebases} reales vs {esp} esperados" if rebases is not None and esp is not None else "")
            + (f" (rango simulado {p10p90[0]}-{p10p90[1]})" if p10p90 else "") + "."
            + (" Hubo bandera roja: los cambios de neumático con la roja no cuentan como parada." if roja else "")
            + (f" Neutralizaciones (SC/VSC): {n_sc}." if n_sc else "")
            + (" Carrera con lluvia (intermedios): el simulador asume carrera seca, así que la comparación de paradas no es"
               " representativa." if mojada else ""))
    return {"paradas_acierto": round(ok / n, 3) if n else None,
            "mae_vuelta_parada": round(sum(err) / len(err), 2) if err else None,
            "rebases_reales": rebases, "nota": nota}


def doc_post_carrera(cfg, carrera_doc, resultado, n2a, estrategia):
    sust = ajustes(cfg)["sustituciones"]
    res = {}
    for x in resultado:
        a = n2a.get(int(x["driver_number"]))
        a = sust.get(a, a)
        if a:
            res[a] = x
    filas = []
    for p in sorted(carrera_doc["pilotos"], key=lambda p: p["pred"]):
        x = res.get(p["acr"], {})
        estado = ("Descalificado" if x.get("dsq") else "Abandonó" if (x.get("dnf") or x.get("dns") or not x) else "Terminó")
        real = x.get("position") if estado != "Descalificado" else None
        real = int(real) if real is not None else None
        filas.append({"acr": p["acr"], "nombre": p.get("nombre"), "equipo": p.get("equipo"), "color": p.get("color", "888888"),
                      "salida": p.get("salida"), "pred": p["pred"], "real": real,
                      "dif": (p["pred"] - real) if real is not None else None, "estado": estado})
    cl = [f for f in filas if f["real"] is not None]
    top_p = [f["acr"] for f in sorted(filas, key=lambda f: f["pred"])][:10]
    top_r = [f["acr"] for f in sorted(cl, key=lambda f: f["real"])][:10]
    podio_p, podio_r = top_p[:3], top_r[:3]
    mae = sum(abs(f["dif"]) for f in cl) / len(cl) if cl else None
    sp = _spearman([f["pred"] for f in cl], [f["real"] for f in cl])
    info = {f["acr"]: f for f in filas}
    nom = lambda a: info[a]["nombre"] or a
    ac = len(set(top_p) & set(top_r))
    txt = [f"El simulador acertó {ac} de los 10 que sumaron puntos y {len(set(podio_p) & set(podio_r))} de 3 en el podio."]
    if top_p[0] == top_r[0]:
        txt.append(f"Acertó al ganador: {nom(top_r[0])}.")
    else:
        g = info[top_r[0]]
        txt.append(f"Ganó {nom(top_r[0])} (salía {g['salida']}.º; el pronóstico lo tenía P{g['pred']}); "
                   f"el favorito del modelo, {nom(top_p[0])}, terminó "
                   + (f"P{info[top_p[0]]['real']}." if info[top_p[0]]["real"] else info[top_p[0]]["estado"].lower() + "."))
    ab = [f["acr"] for f in filas if f["estado"] != "Terminó"]
    if ab:
        txt.append(f"Fuera de la clasificación: {', '.join(ab)}.")
    if mae is not None:
        txt.append(f"Error medio de {mae:.2f} lugares y correlación de {sp:.3f} entre los clasificados." if sp is not None
                   else f"Error medio de {mae:.2f} lugares.")
    if estrategia.get("nota") and estrategia.get("rebases_reales") is not None:
        txt.append(estrategia["nota"])
    filas.sort(key=lambda f: (f["real"] is None, f["real"] or 0, f["pred"]))
    return {"actualizado": iso(ahora_utc()), "aciertos_top10": ac, "top10_pred": top_p, "top10_real": top_r,
            "ganador_pred": top_p[0], "ganador_real": top_r[0] if top_r else None,
            "acierto_ganador": bool(top_r) and top_p[0] == top_r[0], "podio_pred": podio_p, "podio_real": podio_r,
            "aciertos_podio": len(set(podio_p) & set(podio_r)), "exactos": sum(1 for f in cl if f["dif"] == 0),
            "mae": round(mae, 2) if mae is not None else None, "spearman": sp, "filas": filas,
            "estrategia": estrategia, "resumen": " ".join(txt)}


def paso_post_carrera(cfg, retro=False, forzar=False):
    d = directorio(cfg)
    r = sesion(cfg, "r")
    resultado = resultado_sesion(r["session_key"], refrescar=True, preferir_red=not retro)
    if resultado is None:
        raise RuntimeError("OpenF1 aún no tiene el resultado de la carrera")
    carrera_doc = leer_json(d / "carrera.json")
    if not carrera_doc:
        raise RuntimeError("falta carrera.json (paso post_qualy)")
    fir = firma(resultado, carrera_doc.get("actualizado"), (d / "vueltas.json").exists())
    previo = leer_estado(cfg)["pasos"].get("post_carrera", {})
    if previo.get("firma") == fir and not forzar and (d / "post_carrera.json").exists():
        print("  post_carrera: sin cambios")
        return []
    pil = pilotos_meeting(cfg)
    n2a = {k: v["acr"] for k, v in pil.items()}
    est = evaluar_estrategia(cfg, leer_json(d / "vueltas.json"), r["session_key"], n2a)
    doc = doc_post_carrera(cfg, carrera_doc, resultado, n2a, est)
    escribir_json(d / "post_carrera.json", doc)
    marcar(cfg, "post_carrera", firma=fir, aciertos_top10=doc["aciertos_top10"], ganador_real=doc["ganador_real"],
           archivos=["post_carrera.json"])
    return ["post_carrera.json"]


FUNCIONES = {"pre_qualy": paso_pre_qualy, "fp3": paso_fp3, "qualy_en_vivo": paso_qualy_en_vivo,
             "post_qualy": paso_post_qualy, "post_carrera": paso_post_carrera}


# ------------------------------------------------------------------------------------------------
# meta.json
# ------------------------------------------------------------------------------------------------
def meetings_temporada(año=2026):
    """GPs del calendario desde México 2026 (por fecha, no por meeting_key), en orden."""
    ses = sesiones_temporada(año)
    ini = {}
    for x in ses:
        ini[x["meeting_key"]] = min(ini.get(x["meeting_key"], x["date_start"]), x["date_start"])
    desde = ini.get(PRIMER_MEETING, "2026-10-30")
    mks = {x["meeting_key"] for x in ses if x["session_name"] == "Race" and not x.get("is_cancelled")}
    return sorted((m for m in mks if ini[m] >= desde), key=lambda m: ini[m])


def estado_gp(cfg, ahora):
    ini = ts(cfg["sesiones"][0]["inicio_utc"])
    fin_s = cfg["sesiones"][-1].get("fin_utc") or cfg["sesiones"][-1]["inicio_utc"]
    fin = ts(fin_s) + timedelta(hours=0 if cfg["sesiones"][-1].get("fin_utc") else 2)
    if ahora > fin:
        return "terminado"
    if ahora >= ini - timedelta(days=1):
        return "en_curso"
    return "proximo"


def fases_gp(cfg, ahora):
    out = []
    for s in cfg["sesiones"]:
        ini = ts(s["inicio_utc"])
        fin = ts(s["fin_utc"]) if s.get("fin_utc") else ini + timedelta(hours=2)
        out.append({"clave": s["clave"], "nombre": s["nombre"], "session_key": s["session_key"],
                    "inicio_utc": s["inicio_utc"], "fin_utc": iso(fin), "fecha_local": s["fecha_local"],
                    "hora_local": s["hora_local"],
                    "estado": "terminado" if ahora > fin else "en_curso" if ahora >= ini else "proximo"})
    return out


def generar_meta(ahora=None, escribir=True):
    ahora = ahora or ahora_utc()
    gps = []
    for mk in meetings_temporada():
        try:
            cfg = config_gp(mk)
        except SystemExit:
            continue
        d = GPS_DIR / cfg["slug"]
        est = leer_estado(cfg).get("pasos", {})
        docs = {DOCS[f]: f"{DOCS[f]}/{cfg['slug']}" for f in DOCS if (d / f).exists()}
        gps.append({"slug": cfg["slug"], "nombre": cfg["nombre"], "circuito": cfg["circuito"], "ciudad": cfg["ciudad"],
                    "fecha_texto": (cfg["fecha_texto_carrera"] or cfg["fecha_texto"]), "estado": estado_gp(cfg, ahora),
                    "fases": fases_gp(cfg, ahora),
                    # extras (no rompen el contrato): meeting, tema, horarios de qualy/carrera, pasos y docs disponibles
                    "meeting_key": cfg["meeting_key"], "tema": cfg["tema"], "pais": cfg["pais"],
                    "qualy_texto": f"{cfg['fecha_texto']}, {cfg['hora_texto']}".strip(", "),
                    "carrera_texto": f"{cfg['fecha_texto_carrera']}, {cfg['hora_texto_carrera']}".strip(", "),
                    "pasos": {p: est[p]["hecho"] for p in PASOS if p in est}, "docs": docs})
    en_curso = [g for g in gps if g["estado"] == "en_curso"]
    terminados = [g for g in gps if g["estado"] == "terminado"]
    proximos = [g for g in gps if g["estado"] == "proximo"]
    if en_curso:
        actual = en_curso[0]["slug"]
    elif terminados and ahora - ts(terminados[-1]["fases"][-1]["fin_utc"]) < timedelta(days=4):
        actual = terminados[-1]["slug"]
    elif proximos:
        actual = proximos[0]["slug"]
    else:
        actual = gps[-1]["slug"] if gps else None
    meta = {"actualizado": iso(ahora), "actual": actual, "gps": gps}
    viejo = leer_json(GPS_DIR / "meta.json", {}) or {}
    cambio = {k: v for k, v in viejo.items() if k != "actualizado"} != {k: v for k, v in meta.items() if k != "actualizado"}
    if cambio and escribir:
        escribir_json(GPS_DIR / "meta.json", meta)
    return meta, cambio


# ------------------------------------------------------------------------------------------------
# auto / retro
# ------------------------------------------------------------------------------------------------
def pendientes(cfg, ahora):
    """Pasos que tocan ahora (en orden) según la hora UTC y el estado."""
    est = leer_estado(cfg).get("pasos", {})
    fin = lambda c: ts(sesion(cfg, c)["fin_utc"]) if sesion(cfg, c) and sesion(cfg, c).get("fin_utc") else (
        ts(sesion(cfg, c)["inicio_utc"]) + timedelta(hours=1) if sesion(cfg, c) else None)
    ini = lambda c: ts(sesion(cfg, c)["inicio_utc"]) if sesion(cfg, c) else None
    out = []
    ult_fp = next((c for c in ("fp2", "fp1") if sesion(cfg, c)), None)
    q, r = ini("q"), ini("r")
    # pre_qualy y fp3 se ponen al día aunque se haya pasado su ventana (F1_CORTE evita usar datos posteriores)
    if ult_fp and ahora >= fin(ult_fp) + timedelta(minutes=15) and "pre_qualy" not in est:
        out.append("pre_qualy")
    if sesion(cfg, "fp3") and ahora >= fin("fp3") + timedelta(minutes=10) and "fp3" not in est:
        out.append("fp3")
    if q and q - timedelta(minutes=40) <= ahora <= fin("q") + timedelta(minutes=10) and "qualy_en_vivo" not in est:
        out.insert(0, "qualy_en_vivo")        # primero: el colector no puede esperar a los modelos
    if q and ahora >= fin("q") + timedelta(minutes=10) and (r is None or ahora < r + timedelta(hours=3)):
        pq = est.get("post_qualy")
        # se repite (si cambian sus entradas: qualy oficial, parrilla, ajustes) hasta que arranca la carrera
        if pq is None or (r is not None and ahora < r):
            out.append("post_qualy")
    if r and ahora >= fin("r") + timedelta(minutes=30):
        pc = est.get("post_carrera")
        if pc is None or ahora < fin("r") + timedelta(hours=36):
            out.append("post_carrera")
    return out


def ejecutar(cfg, paso, retro=False, forzar=False):
    t0 = time.time()
    print(f"[{iso(ahora_utc())}] {cfg['slug']}: {paso}{' (retro)' if retro else ''}", flush=True)
    try:
        arch = FUNCIONES[paso](cfg, retro=retro, forzar=forzar) or []
        return {"slug": cfg["slug"], "paso": paso, "ok": True, "segundos": round(time.time() - t0),
                "archivos_cambiados": [f"gps/{cfg['slug']}/{a}" for a in arch],
                "docs": [{"coleccion": DOCS[a], "doc_id": cfg["slug"], "archivo": f"gps/{cfg['slug']}/{a}"}
                         for a in arch if a in DOCS]}
    except Exception as e:
        print(f"  ERROR en {paso}: {e}", flush=True)
        return {"slug": cfg["slug"], "paso": paso, "ok": False, "error": str(e), "segundos": round(time.time() - t0),
                "archivos_cambiados": [], "docs": []}


def modo_auto(simular=False):
    ahora = ahora_utc()
    acciones, comandos = [], []
    for mk in meetings_temporada():
        cfg = config_gp(mk)
        if estado_gp(cfg, ahora) == "proximo":
            continue
        cmds = comandos_colector(cfg)
        for clave in ("fp3", "qualy"):
            c = cmds.get(clave)
            s = sesion(cfg, clave if clave == "fp3" else "q")
            if c and s and ts(c["lanzar_utc"]) - timedelta(minutes=30) <= ahora <= ts(s["fin_utc"]):
                comandos.append({"slug": cfg["slug"], "sesion": clave, **c})
                print(f"COLECTOR {cfg['slug']} {clave} (lanzar {c['lanzar_utc']}): {c['comando']}", flush=True)
        for paso in pendientes(cfg, ahora):
            if simular:
                acciones.append({"slug": cfg["slug"], "paso": paso, "ok": None, "simulado": True})
                continue
            a = ejecutar(cfg, paso)
            acciones.append(a)
            if not a["ok"]:
                break                 # los pasos siguientes dependen de éste
    meta, cambio = generar_meta(ahora, escribir=not simular)
    if cambio:
        acciones.append({"slug": None, "paso": "meta", "ok": True, "archivos_cambiados": ["gps/meta.json"],
                         "docs": [{"coleccion": "meta", "doc_id": "actual", "archivo": "gps/meta.json"}]})
    resumen = {"ahora": iso(ahora), "actual": meta["actual"], "acciones": acciones, "comandos_colector": comandos,
               "docs_a_publicar": [x for a in acciones for x in a.get("docs", [])]}
    if not simular:
        escribir_json(GPS_DIR / "ultimo_auto.json", resumen)
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return resumen


def modo_retro(mk, forzar=False, refrescar=True, pasos=None):
    cfg = config_gp(mk)
    r = sesion(cfg, "r")
    if r and ahora_utc() < ts(r["inicio_utc"]):
        raise SystemExit("retro es para GPs ya corridos")
    if refrescar and not hecho(cfg, "descarga"):
        refrescar_datos(cfg, directorio(cfg) / "logs" / "descarga.log")
        marcar(cfg, "descarga", archivos=[])
    acciones = []
    for paso in (pasos or PASOS):
        if hecho(cfg, paso) and not forzar and paso not in ("post_qualy", "post_carrera"):
            print(f"{cfg['slug']}: {paso} ya hecho (usa --forzar para repetir)")
            continue
        a = ejecutar(cfg, paso, retro=True, forzar=forzar)
        acciones.append(a)
        if not a["ok"]:
            break
    meta, _ = generar_meta()
    print(json.dumps({"slug": cfg["slug"], "acciones": acciones}, ensure_ascii=False, indent=1))
    return acciones


# ------------------------------------------------------------------------------------------------
# Migración de México (no borra ni mueve nada: copia a los nombres nuevos)
# ------------------------------------------------------------------------------------------------
def migrar_mexico():
    cfg = config_gp(1298)
    d = directorio(cfg)
    copias = {"gp.json": BASE / "web_mexico" / "datos_gp.json", "live_qualy.json": LIVE / "qualy_mexico.json",
              "post_qualy.json": LIVE / "post_qualy.json", "carrera.json": BASE / "web_mexico" / "datos_carrera.json",
              "vueltas.json": BASE / "web_mexico" / "datos_vueltas.json"}
    hechos = []
    for dst, src in copias.items():
        if copiar_si_cambia(src, d / dst):
            hechos.append(dst)
    carrera = leer_json(d / "carrera.json", {})
    aj = leer_json(d / "ajustes.json", {}) or {}
    if not aj.get("notas"):
        aj = {
            "sustituciones": {"OCO": "HIR"},
            "parrilla": {p["acr"]: p["salida"] for p in carrera.get("pilotos", [])},
            "penalizaciones": {},
            "notas": [],
            "fuentes": [
                "Hirakawa (#50) reemplaza a Ocon en Haas desde la FP3: Haas vía The Race / Sky / RaceFans (31/10/2026)",
                "Parrilla: clasificación oficial + Lawson descalificado de la qualy (MGU-K) -> P22; Verstappen -1 lugar "
                "(choque en FP2); Bottas al fondo (componentes de motor). Crash.net / FIA (1/11/2026). Ver ESTADO_MEXICO.md",
            ],
            "nota_parrilla": "parrilla = la usada en el pronóstico publicado (carrera.json, salida por piloto)",
        }
        escribir_json(d / "ajustes.json", aj)
    e = leer_estado(cfg)
    if not e.get("pasos"):
        def mtime(p):
            return iso(datetime.fromtimestamp(Path(p).stat().st_mtime, tz=timezone.utc)) if Path(p).exists() else None
        e = {"slug": cfg["slug"], "meeting_key": 1298, "pasos": {
            "pre_qualy": {"hecho": mtime(BASE / "resultado_qualy_mexico.pkl"), "nota": "migrado (corrida manual)", "archivos": []},
            "fp3": {"hecho": mtime(BASE / "resultado_qualy_mexico_fp3.pkl"), "nota": "migrado: FP3 reconstruida del live timing",
                    "archivos": ["gp.json"]},
            "qualy_en_vivo": {"hecho": mtime(LIVE / "qualy_mexico.json"), "nota": "migrado", "archivos": ["live_qualy.json"]},
            "post_qualy": {"hecho": mtime(LIVE / "post_qualy.json"), "nota": "migrado (parrilla con DSQ de Lawson)",
                           "oficial": True, "archivos": ["post_qualy.json", "carrera.json", "vueltas.json"]},
        }}
        escribir_json(d / "estado.json", e)
    print("México migrado a", d.relative_to(BASE), "| copiados:", hechos)
    return hechos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["auto", "retro", "paso", "config", "meta", "migrar_mexico", "comandos"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--simular", action="store_true", help="auto: sólo dice qué pasos tocarían")
    ap.add_argument("--ahora", default=None, help="hora UTC simulada (ISO), para probar 'auto'")
    ap.add_argument("--pasos", default=None, help="retro: lista separada por comas")
    a = ap.parse_args()
    if a.ahora:
        os.environ["GP_AHORA"] = a.ahora
    GPS_DIR.mkdir(exist_ok=True)
    if a.accion == "auto":
        modo_auto(a.simular)
    elif a.accion == "retro":
        modo_retro(int(a.args[0]), a.forzar, pasos=a.pasos.split(",") if a.pasos else None)
    elif a.accion == "paso":
        cfg = config_gp(int(a.args[1]))
        res = ejecutar(cfg, a.args[0], retro="--retro" in sys.argv or ahora_utc() > ts(sesion(cfg, "r")["inicio_utc"]),
                       forzar=a.forzar)
        generar_meta()
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if not res["ok"]:
            raise SystemExit(1)
    elif a.accion == "config":
        print(json.dumps(config_gp(int(a.args[0])), ensure_ascii=False, indent=1))
    elif a.accion == "meta":
        meta, cambio = generar_meta()
        print(json.dumps(meta, ensure_ascii=False, indent=1)[:3000], "\ncambió:", cambio)
    elif a.accion == "migrar_mexico":
        migrar_mexico()
        generar_meta()
    elif a.accion == "comandos":
        print(json.dumps(comandos_colector(config_gp(int(a.args[0]))), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
