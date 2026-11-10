#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cerebro Liga MX · base histórica de partidos desde la API pública de ESPN.

Uso (desde cualquier carpeta):
    python3 espn_descarga.py calendario            # scoreboard de cada año (2001..año en curso)
    python3 espn_descarga.py resumenes [--desde AAAA] [--hasta AAAA] [--forzar]
    python3 espn_descarga.py tablas                # partidos.csv, goles.csv, tarjetas.csv, alineaciones.csv, ...
    python3 espn_descarga.py todo [--desde AAAA]   # calendario + resumenes + tablas
    python3 espn_descarga.py actualizar            # INCREMENTAL: para correr después de cada partido
    python3 espn_descarga.py verificar             # pruebas de consistencia sobre las tablas

Diseño
- Sólo biblioteca estándar para descargar y armar tablas (pandas se usa, si está, en el reporte de cobertura).
- Caché en datos/cache/espn/ (NO va al repositorio): scoreboard/AAAA.json.gz y resumen/<id>.json.gz.
  El resumen que se guarda es un EXTRACTO compacto (no el JSON completo de ESPN).
- Las tablas CSV son la fuente de verdad para lo ya procesado: `actualizar` funciona aunque el caché esté
  vacío (clon nuevo del repositorio): conserva las filas existentes y sólo vuelve a pedir lo que cambió.
- Cortesía con ESPN: máximo 6 hilos y 5 peticiones por segundo, reintentos con espera exponencial,
  User-Agent de navegador (uno con la palabra "bot" recibe 403) y respuesta en gzip.
- Nunca se inventa un dato: lo que ESPN no trae queda vacío.
"""

import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import gzip
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------------------------------------------
# Rutas y constantes
# ----------------------------------------------------------------------------------------------------------
RAIZ = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(RAIZ, "cache", "espn")
DIR_SB = os.path.join(CACHE, "scoreboard")
DIR_RES = os.path.join(CACHE, "resumen")
ARCH_STANDINGS = os.path.join(CACHE, "standings.json.gz")

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1"
URL_STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/mex.1/standings"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")

ANIO_INICIAL = 2001          # ESPN no tiene eventos de Liga MX antes de 2001 (probado 1996-2000: vacío)
ANIO_PRIORIDAD = 2010        # primero 2010..hoy, después lo anterior
MAX_HILOS = 6
MAX_POR_SEG = 4.5            # tope real pedido: 5/s; se deja un margen
REINTENTOS = 6
VERSION_EXTRACTO = 1
TZ_MX = ZoneInfo("America/Mexico_City")

ESTADOS_JUGADO = {"STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET", "STATUS_ABANDONED",
                  "STATUS_FINAL", "STATUS_FORFEIT"}
ESTADOS_POSPUESTO = {"STATUS_POSTPONED", "STATUS_SUSPENDED", "STATUS_DELAYED"}
ESTADOS_CANCELADO = {"STATUS_CANCELED", "STATUS_CANCELLED"}


def es_jugado(e):
    """¿El evento del scoreboard ya terminó con resultado?"""
    st = e.get("estado") or ""
    if st in ESTADOS_JUGADO:
        return True
    if st in ESTADOS_POSPUESTO or st in ESTADOS_CANCELADO:
        return False
    return e.get("estado_fase") == "post" and bool(e.get("completo"))


def log(*a):
    """Bitácora a stderr (stdout se reserva para la salida JSON de `actualizar`)."""
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def ahora_utc():
    return dt.datetime.now(dt.timezone.utc)


def ahora_iso():
    return ahora_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------------------------------------
# Red: limitador global, reintentos, gzip
# ----------------------------------------------------------------------------------------------------------
class Limitador:
    """Reparte turnos entre hilos: como máximo `por_seg` peticiones por segundo en total."""

    def __init__(self, por_seg):
        self.intervalo = 1.0 / por_seg
        self.candado = threading.Lock()
        self.siguiente = 0.0

    def esperar(self):
        with self.candado:
            turno = max(time.monotonic(), self.siguiente)
            self.siguiente = turno + self.intervalo
        falta = turno - time.monotonic()
        if falta > 0:
            time.sleep(falta)

    def frenar(self, segundos):
        """Tras un 429/5xx todos los hilos esperan un poco más."""
        with self.candado:
            self.siguiente = max(self.siguiente, time.monotonic() + segundos)


LIMITADOR = Limitador(MAX_POR_SEG)
CONTADOR = {"peticiones": 0, "reintentos": 0}


class NoExiste(Exception):
    """ESPN respondió 404 (el evento no tiene resumen)."""


class Bloqueado(Exception):
    """403/407: bloqueo de política o de ESPN; no se reintenta."""


def pedir_json(url, reintentos=REINTENTOS):
    """GET con gzip, turno del limitador y reintentos con espera exponencial."""
    ultimo = None
    for intento in range(reintentos):
        LIMITADOR.esperar()
        CONTADOR["peticiones"] += 1
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Encoding": "gzip",
                "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=40) as r:
                crudo = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip" or crudo[:2] == b"\x1f\x8b":
                    crudo = gzip.decompress(crudo)
            return json.loads(crudo.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NoExiste(url)
            if e.code in (401, 403, 407):
                raise Bloqueado(f"HTTP {e.code} en {url}")
            ultimo = f"HTTP {e.code}"
            if e.code == 400:      # ESPN contesta 400 a parámetros inválidos: no tiene caso insistir mucho
                if intento >= 1:
                    break
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError, EOFError) as e:
            ultimo = f"{type(e).__name__}: {e}"
        CONTADOR["reintentos"] += 1
        espera = min(60.0, (2 ** intento)) + random.random()
        LIMITADOR.frenar(min(espera, 5.0))
        time.sleep(espera)
    raise RuntimeError(f"sin respuesta tras {reintentos} intentos ({ultimo}): {url}")


def guardar_gz(ruta, objeto):
    """Escritura atómica de JSON comprimido."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = f"{ruta}.tmp{os.getpid()}.{threading.get_ident()}"
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(objeto, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ruta)


def leer_gz(ruta):
    try:
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


# ----------------------------------------------------------------------------------------------------------
# a) Calendario: scoreboard por año
# ----------------------------------------------------------------------------------------------------------
def ruta_sb(anio):
    return os.path.join(DIR_SB, f"{anio}.json.gz")


def recortar_evento(e):
    """Del evento del scoreboard se guarda sólo lo que se usa (sin logos, ligas ni enlaces)."""
    comp = (e.get("competitions") or [{}])[0]
    st = e.get("status") or comp.get("status") or {}
    tipo = st.get("type") or {}
    sede = comp.get("venue") or {}
    equipos = []
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        equipos.append({
            "id": str(t.get("id") or c.get("id") or ""),
            "lado": c.get("homeAway"),
            "nombre": t.get("displayName"),
            "goles": c.get("score"),
            "tanda": c.get("shootoutScore"),
            "global": c.get("aggregateScore"),
            "gana": c.get("winner"),
            "avanza": c.get("advance"),
            "est": {s.get("name"): s.get("displayValue") for s in c.get("statistics") or []},
        })
    return {
        "id": str(e.get("id")),
        "fecha": e.get("date"),
        "hora_valida": comp.get("timeValid"),
        "temporada": (e.get("season") or {}).get("year"),
        "tipo_temporada": (e.get("season") or {}).get("type"),
        "slug": (e.get("season") or {}).get("slug"),
        "estado": tipo.get("name"),
        "estado_fase": tipo.get("state"),
        "completo": tipo.get("completed"),
        "reloj": st.get("displayClock"),
        "periodo": st.get("period"),
        "pierna": (comp.get("leg") or {}).get("value"),
        "notas": [n.get("headline") or n.get("text") for n in comp.get("notes") or []
                  if (n.get("headline") or n.get("text"))],
        "estadio": sede.get("fullName") or (e.get("venue") or {}).get("displayName"),
        "estadio_id": str(sede.get("id") or ""),
        "ciudad": (sede.get("address") or {}).get("city"),
        "asistencia": comp.get("attendance"),
        "suspendido": comp.get("wasSuspended"),
        "equipos": equipos,
        "detalles": [_detalle(x) for x in comp.get("details") or []],
    }


def _atleta(p):
    a = (p or {}).get("athlete") or p or {}
    return [str(a.get("id") or ""), a.get("displayName") or a.get("fullName") or ""]


def _detalle(x):
    """Jugada de la lista `details` (goles y tarjetas) del scoreboard o del encabezado del resumen."""
    reloj = x.get("clock") or {}
    quienes = x.get("participants") or x.get("athletesInvolved") or []
    d = {"c": reloj.get("value"), "d": reloj.get("displayValue"),
         "e": str((x.get("team") or {}).get("id") or ""),
         "j": [_atleta(p) for p in quienes]}
    t = x.get("type") or {}
    if t.get("text"):
        d["t"] = t.get("text")
    for clave, corto in (("scoringPlay", "gol"), ("penaltyKick", "pen"), ("ownGoal", "ag"),
                         ("yellowCard", "am"), ("redCard", "ro"), ("shootout", "tanda")):
        if x.get(clave):
            d[corto] = 1
    return d


def _eventos_conocidos(anio):
    """Cuántos eventos de ese año (UTC) ya se conocían: por el caché o, si no hay, por partidos.csv."""
    previo = leer_gz(ruta_sb(anio))
    if previo and previo.get("eventos"):
        return len(previo["eventos"])
    ruta = os.path.join(RAIZ, "partidos.csv")
    if not os.path.exists(ruta):
        return 0
    with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for fila in csv.DictReader(f) if (fila.get("fecha_utc") or "").startswith(str(anio)))


def descargar_calendario(anios, verboso=True):
    """Baja scoreboard?dates=AAAA&limit=1000 de cada año y lo guarda recortado y comprimido.
    Si ESPN devuelve muchos menos eventos de los ya conocidos (respuesta trunca), NO se guarda y se aborta:
    así una falla pasajera no borra partidos de las tablas."""
    resumen = {}
    for anio in anios:
        url = f"{BASE}/scoreboard?dates={anio}&limit=1000"
        d = pedir_json(url)
        eventos = [recortar_evento(e) for e in d.get("events") or []]
        conocidos = _eventos_conocidos(anio)
        if conocidos >= 20 and len(eventos) < 0.9 * conocidos:
            raise RuntimeError(f"scoreboard {anio} incompleto: {len(eventos)} eventos contra {conocidos} conocidos; "
                               f"no se guarda (reintenta más tarde)")
        if len(eventos) >= 1000:
            log(f"AVISO: {anio} devolvió {len(eventos)} eventos (posible tope de la API)")
        guardar_gz(ruta_sb(anio), {"anio": anio, "descargado": ahora_iso(), "eventos": eventos})
        resumen[anio] = len(eventos)
        if verboso:
            log(f"calendario {anio}: {len(eventos)} eventos")
    return resumen


def anios_en_cache():
    if not os.path.isdir(DIR_SB):
        return []
    return sorted(int(n[:4]) for n in os.listdir(DIR_SB) if re.fullmatch(r"\d{4}\.json\.gz", n))


def cargar_calendario(anios=None):
    """Regresa {id: evento} con los scoreboards que haya en caché (un evento puede salir en dos años)."""
    eventos = {}
    for anio in (anios or anios_en_cache()):
        d = leer_gz(ruta_sb(anio))
        if not d:
            continue
        for e in d["eventos"]:
            e["_anio_sb"] = anio
            eventos[e["id"]] = e
    return eventos


# ----------------------------------------------------------------------------------------------------------
# b) Resúmenes: extracto compacto por partido
# ----------------------------------------------------------------------------------------------------------
def ruta_res(eid):
    return os.path.join(DIR_RES, f"{eid}.json.gz")


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def extraer(d, eid):
    """Convierte el JSON de summary?event=<id> en un extracto compacto con todo lo que usan las tablas."""
    cab = d.get("header") or {}
    comp = (cab.get("competitions") or [{}])[0]
    tipo = (comp.get("status") or {}).get("type") or {}
    ex = {"v": VERSION_EXTRACTO, "id": str(eid), "descargado": ahora_iso()}

    series = comp.get("series") or []
    if isinstance(series, dict):
        series = [series]
    ex["cab"] = {
        "fecha": comp.get("date"),
        "estado": tipo.get("name"),
        "estado_fase": tipo.get("state"),
        "completo": tipo.get("completed"),
        "pierna": (comp.get("leg") or {}).get("value"),
        "notas": [n.get("headline") or n.get("text") for n in comp.get("notes") or []
                  if (n.get("headline") or n.get("text"))],
        "serie": [{"titulo": s.get("title"), "completa": s.get("completed"), "partidos": s.get("totalCompetitions"),
                   "equipos": [{"id": str(c.get("id")), "global": c.get("aggregateScore"), "gana": c.get("winner")}
                               for c in s.get("competitors") or []]} for s in series],
        "temporada": {k: (cab.get("season") or {}).get(k) for k in ("year", "type", "name")},
        "neutral": comp.get("neutralSite"),
        "fuente_box": comp.get("boxscoreSource"),
        "fuente_jugadas": comp.get("playByPlaySource"),
        "equipos": [{
            "id": str(c.get("id") or (c.get("team") or {}).get("id") or ""),
            "lado": c.get("homeAway"),
            "nombre": (c.get("team") or {}).get("displayName"),
            "goles": c.get("score"),
            "parciales": [x.get("displayValue") for x in c.get("linescores") or []],
            "tanda": c.get("shootoutScore"),
            "global": c.get("aggregateScore"),
            "gana": c.get("winner"),
        } for c in comp.get("competitors") or []],
        "detalles": [_detalle(x) for x in comp.get("details") or []],
    }

    # Estadísticas por equipo (todas las que traiga el boxscore)
    ex["box"] = {}
    for t in (d.get("boxscore") or {}).get("teams") or []:
        tid = str((t.get("team") or {}).get("id") or "")
        ex["box"][tid] = {"lado": t.get("homeAway"),
                          "est": {s.get("name"): s.get("displayValue") for s in t.get("statistics") or []}}

    # Jugadas clave (goles, tarjetas, cambios, VAR, marcas de periodo), con su texto
    ex["ev"] = []
    for k in d.get("keyEvents") or []:
        t = k.get("type") or {}
        reloj = k.get("clock") or {}
        e = {"id": str(k.get("id") or ""), "ti": str(t.get("id") or ""), "t": t.get("text"), "tt": t.get("type"),
             "p": (k.get("period") or {}).get("number"), "c": reloj.get("value"), "d": reloj.get("displayValue")}
        if k.get("team"):
            e["e"] = str(k["team"].get("id") or "")
        if k.get("participants"):
            e["j"] = [_atleta(p) for p in k["participants"]]
        if k.get("scoringPlay"):
            e["gol"] = 1
        if k.get("shootout"):
            e["tanda"] = 1
        if k.get("text"):
            e["x"] = k["text"]
        if k.get("wallclock"):
            e["w"] = k["wallclock"]
        ex["ev"].append(e)

    # Tanda de penales (si hubo)
    if d.get("shootout"):
        ex["tanda"] = [{"e": str(s.get("id") or ""),
                        "tiros": [[str(x.get("playerId") or ""), x.get("player"), 1 if x.get("didScore") else 0]
                                  for x in s.get("shots") or []]} for s in d["shootout"]]

    # Alineaciones
    ex["al"] = []
    for r in d.get("rosters") or []:
        jug = []
        for p in r.get("roster") or []:
            a = p.get("athlete") or {}
            pos = p.get("position") or {}
            j = {"id": str(a.get("id") or ""), "n": a.get("displayName") or a.get("fullName") or "",
                 "tit": 1 if p.get("starter") else 0, "pos": pos.get("abbreviation"),
                 "lugar": p.get("formationPlace"), "dorsal": p.get("jersey")}
            if p.get("subbedIn"):
                j["entra"] = 1
                if p.get("subbedInFor"):
                    j["por"] = _atleta(p["subbedInFor"])
            if p.get("subbedOut"):
                j["sale"] = 1
                if p.get("subbedOutFor"):
                    j["por_sale"] = _atleta(p["subbedOutFor"])
            jugadas = []
            for y in p.get("plays") or []:
                cod = "".join(letra for clave, letra in (("substitution", "S"), ("scoringPlay", "G"),
                                                         ("yellowCard", "A"), ("redCard", "R"),
                                                         ("penaltyKick", "P"), ("ownGoal", "O")) if y.get(clave))
                jugadas.append([(y.get("clock") or {}).get("displayValue"), cod])
            if jugadas:
                j["jug"] = jugadas
            est = {s.get("name"): _num(s.get("value")) for s in p.get("stats") or []
                   if s.get("value") not in (None, 0, 0.0) and s.get("name") != "appearances"}
            if est:
                j["est"] = est
            jug.append(j)
        ex["al"].append({"e": str((r.get("team") or {}).get("id") or ""), "lado": r.get("homeAway"),
                         "formacion": r.get("formation"), "j": jug})

    # Momios (pickcenter; `odds` trae lo mismo)
    ex["momios"] = []
    for o in (d.get("pickcenter") or d.get("odds") or []):
        if not o:
            continue
        prov = o.get("provider") or {}
        loc = o.get("homeTeamOdds") or {}
        vis = o.get("awayTeamOdds") or {}

        def _oc(bloque, lado, campo="odds"):
            return ((((o.get(bloque) or {}).get(lado) or {}).get("close") or {}).get(campo),
                    (((o.get(bloque) or {}).get(lado) or {}).get("open") or {}).get(campo))

        m = {"prov": prov.get("name"), "prov_id": str(prov.get("id") or ""), "prioridad": prov.get("priority"),
             "detalle": o.get("details"),
             "ml_l": loc.get("moneyLine"), "ml_e": (o.get("drawOdds") or {}).get("moneyLine"),
             "ml_v": vis.get("moneyLine"),
             "total": o.get("overUnder"), "over": o.get("overOdds"), "under": o.get("underOdds"),
             "handicap": o.get("spread"), "h_l": loc.get("spreadOdds"), "h_v": vis.get("spreadOdds"),
             "cierre_abre": {"ml_l": _oc("moneyline", "home"), "ml_e": _oc("moneyline", "draw"),
                             "ml_v": _oc("moneyline", "away"),
                             "over": _oc("total", "over"), "under": _oc("total", "under"),
                             "linea_over": _oc("total", "over", "line"),
                             "h_l": _oc("pointSpread", "home"), "h_v": _oc("pointSpread", "away"),
                             "linea_h_l": _oc("pointSpread", "home", "line")}}
        ex["momios"].append(m)

    # Sede, asistencia, árbitros
    gi = d.get("gameInfo") or {}
    sede = gi.get("venue") or {}
    ex["info"] = {"estadio": sede.get("fullName"), "estadio_id": str(sede.get("id") or ""),
                  "ciudad": (sede.get("address") or {}).get("city"),
                  "pais": (sede.get("address") or {}).get("country"),
                  "asistencia": gi.get("attendance"),
                  "arbitros": [[x.get("displayName") or x.get("fullName"),
                                (x.get("position") or {}).get("name")] for x in gi.get("officials") or []]}
    return ex


def descargar_resumen(eid):
    """Baja y guarda el extracto de un partido. Regresa 'ok', 'sin_resumen' o lanza excepción."""
    try:
        d = pedir_json(f"{BASE}/summary?event={eid}")
    except NoExiste:
        guardar_gz(ruta_res(eid), {"v": VERSION_EXTRACTO, "id": str(eid), "descargado": ahora_iso(),
                                   "error": "404"})
        return "sin_resumen"
    guardar_gz(ruta_res(eid), extraer(d, eid))
    return "ok"


def extracto_vigente(eid, estado_sb):
    """¿Ya hay en caché un extracto de este partido tomado cuando ya estaba terminado?"""
    ruta = ruta_res(eid)
    if not os.path.exists(ruta):
        return False
    ex = leer_gz(ruta)
    if not ex or ex.get("v") != VERSION_EXTRACTO:
        return False
    if ex.get("error"):
        return True
    return (ex.get("cab") or {}).get("estado") == estado_sb


def descargar_resumenes(ids, etiqueta="resumenes"):
    """Baja en paralelo (<= 6 hilos, <= 5 req/s) los resúmenes indicados. Regresa conteos."""
    ids = list(ids)
    cuenta = {"ok": 0, "sin_resumen": 0, "error": 0}
    if not ids:
        return cuenta
    t0 = time.monotonic()
    bloqueado = threading.Event()

    def trabajo(eid):
        if bloqueado.is_set():
            return "error"
        try:
            return descargar_resumen(eid)
        except Bloqueado as e:
            bloqueado.set()
            log(f"BLOQUEO: {e}")
            return "error"
        except Exception as e:          # se anota y se sigue: el comando es reanudable
            log(f"error en {eid}: {e}")
            return "error"

    hechos = 0
    with ThreadPoolExecutor(max_workers=MAX_HILOS) as pool:
        futuros = [pool.submit(trabajo, eid) for eid in ids]
        for f in as_completed(futuros):
            cuenta[f.result()] += 1
            hechos += 1
            if hechos % 200 == 0 or hechos == len(ids):
                seg = time.monotonic() - t0
                log(f"{etiqueta}: {hechos}/{len(ids)} ({hechos / max(seg, 1e-9):.1f}/s) "
                    f"ok={cuenta['ok']} sin_resumen={cuenta['sin_resumen']} error={cuenta['error']} "
                    f"reintentos={CONTADOR['reintentos']}")
    return cuenta


def ids_para_resumen(eventos, desde=None, hasta=None, forzar=False):
    """Partidos JUGADOS sin extracto vigente, en orden de prioridad: 2010..hoy (reciente primero) y luego lo viejo."""
    pendientes = []
    for e in eventos.values():
        if not es_jugado(e):
            continue
        anio = int((e.get("fecha") or "0000")[:4])
        if desde and anio < desde:
            continue
        if hasta and anio > hasta:
            continue
        if not forzar and extracto_vigente(e["id"], e.get("estado")):
            continue
        pendientes.append((0 if anio >= ANIO_PRIORIDAD else 1, -anio, e.get("fecha") or "", e["id"]))
    pendientes.sort()
    return [p[3] for p in pendientes]


# ----------------------------------------------------------------------------------------------------------
# c) Tablas
# ----------------------------------------------------------------------------------------------------------
# Nombre canónico por id de equipo en ESPN (único y estable aunque ESPN cambie el nombre que muestra).
EQUIPOS = {
    "227": "América", "226": "Atlante", "216": "Atlas", "15720": "Atlético San Luis", "218": "Cruz Azul",
    "219": "Chivas", "17851": "Juárez", "228": "León", "220": "Monterrey", "229": "Necaxa", "234": "Pachuca",
    "231": "Puebla", "233": "Pumas", "222": "Querétaro", "225": "Santos", "232": "Tigres", "10125": "Tijuana",
    "223": "Toluca",
    # históricos
    "221": "Morelia", "2569": "Veracruz", "224": "Chiapas", "20702": "Mazatlán", "8814": "Lobos BUAP",
    "230": "Tecos", "2490": "San Luis", "2929": "Dorados", "3432": "Dorados", "10129": "Leones Negros",
    "9759": "Indios", "10126": "Irapuato", "217": "Colibríes",
}

# Avisos escritos a mano para partidos cuyo registro en ESPN necesita contexto (no cambian ningún número).
NOTAS_MANUALES = {
    "623106": "partido suspendido al 62' por violencia en la tribuna con 0-1; ESPN conserva el marcador de cancha y "
              "historico_ligamx.csv trae 0-3 (resultado de escritorio)",
    "348028": "localía dudosa: historico_ligamx.csv pone a Morelia de local (la alternancia de localías lo respalda); "
              "se conserva lo que dice ESPN",
}

ARCH_PARTIDOS = os.path.join(RAIZ, "partidos.csv")
ARCH_GOLES = os.path.join(RAIZ, "goles.csv")
ARCH_TARJETAS = os.path.join(RAIZ, "tarjetas.csv")
ARCH_ALINEACIONES = os.path.join(RAIZ, "alineaciones.csv")
ARCH_PENDIENTE = os.path.join(RAIZ, "calendario_pendiente.json")
ARCH_COBERTURA = os.path.join(RAIZ, "COBERTURA.md")
ARCH_VEREDICTOS = os.path.join(RAIZ, "conciliacion_veredictos.json")
HIST_FT = os.path.join(os.path.dirname(os.path.dirname(RAIZ)), "historico_ligamx.csv")
HIST_HT = os.path.join(os.path.dirname(os.path.dirname(RAIZ)), "historico_ht_ligamx.csv")

# (columna, estadística de ESPN)
STATS_LADO = [("tiros", "totalShots"), ("tiros_puerta", "shotsOnTarget"), ("corners", "wonCorners"),
              ("faltas", "foulsCommitted"), ("amarillas", "yellowCards"), ("rojas", "redCards"),
              ("posesion", "possessionPct"), ("fueras_lugar", "offsides"), ("atajadas", "saves"),
              ("penales_tirados", "penaltyKickShots"), ("penales_gol", "penaltyKickGoals")]
STATS_EXTRA = [("pases", "totalPasses"), ("pases_precisos", "accuratePasses"), ("centros", "totalCrosses"),
               ("centros_precisos", "accurateCrosses"), ("tiros_bloqueados", "blockedShots"),
               ("entradas", "totalTackles"), ("intercepciones", "interceptions"), ("despejes", "totalClearance")]

COLS_PARTIDOS = (
    ["id", "fecha_utc", "fecha_local", "anio", "torneo", "fase", "pierna", "estado", "local", "visitante",
     "gl", "gv", "gl_et", "gv_et", "pen_l", "pen_v", "gl_ht", "gv_ht", "estadio", "ciudad", "asistencia", "arbitro"]
    + [f"{c}_{lado}" for c, _ in STATS_LADO for lado in ("l", "v")]
    + ["ml_l", "ml_e", "ml_v", "total_linea", "over", "under", "proveedor",
       "tiene_stats", "tiene_eventos", "tiene_alineaciones", "tiene_momios",
       # --- columnas adicionales (no pedidas, útiles para modelar y para la actualización incremental) ---
       "tiene_tarjetas", "hora_local", "serie", "local_id", "visitante_id", "estadio_id",
       "formacion_l", "formacion_v"]
    + [f"{c}_{lado}" for c, _ in STATS_EXTRA for lado in ("l", "v")]
    + ["ml_l_abre", "ml_e_abre", "ml_v_abre", "over_abre", "under_abre",
       "ht_fuente", "temporada_espn", "fase_espn", "estado_espn", "nota"]
)
COLS_MOMIOS = ["ml_l", "ml_e", "ml_v", "total_linea", "over", "under", "proveedor", "tiene_momios",
               "ml_l_abre", "ml_e_abre", "ml_v_abre", "over_abre", "under_abre"]
COLS_GOLES = ["partido_id", "minuto", "anadido", "periodo", "equipo", "jugador", "tipo",
              "subtipo", "jugador_id", "asistencia"]
COLS_TARJETAS = ["partido_id", "minuto", "periodo", "equipo", "jugador", "tipo", "anadido", "jugador_id"]
COLS_ALINEACIONES = ["partido_id", "equipo", "jugador_id", "jugador", "titular", "posicion",
                     "minuto_entra", "minuto_sale", "formacion"]


def leer_csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def escribir_csv(ruta, columnas, filas):
    tmp = f"{ruta}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, "") for c in columnas})
    os.replace(tmp, ruta)


def escribir_texto(ruta, texto):
    tmp = f"{ruta}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    os.replace(tmp, ruta)


def nombre_equipo(tid, nombre_espn, desconocidos=None):
    if tid in EQUIPOS:
        return EQUIPOS[tid]
    if desconocidos is not None:
        desconocidos.add(f"{tid}:{nombre_espn}")
    return nombre_espn or f"equipo_{tid}"


def _ent(v):
    """Entero no negativo o None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f < 0:
        return None
    return int(round(f))


def _txt(v):
    return "" if v is None else str(v)


def _fecha_dt(fecha_iso):
    """'2026-11-14T23:00Z' -> datetime con zona UTC."""
    s = (fecha_iso or "").strip().replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+00:00", s):
        s = s[:16] + ":00+00:00"
    return dt.datetime.fromisoformat(s)


def _minuto(d, c):
    """Reloj de ESPN -> (minuto, añadido).  "90'+4'" -> (90, 4);  "45'" -> (45, 0)."""
    if d:
        m = re.match(r"\s*(\d+)'?(?:\s*\+\s*(\d+))?", d)
        if m:
            return int(m.group(1)), int(m.group(2) or 0)
    try:
        return max(1, math.ceil(float(c) / 60.0)), 0
    except (TypeError, ValueError):
        return None, 0


def _periodo(p, minuto):
    if p in (1, 2, 3, 4, 5):
        return p
    if minuto is None:
        return ""
    return 1 if minuto <= 45 else 2 if minuto <= 90 else 3 if minuto <= 105 else 4


def momio_decimal(v):
    """Momio americano (+195, -135, 'EVEN') -> decimal con 3 decimales; None si no se puede."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().upper().replace("−", "-")
        if s in ("EVEN", "EV", "PK"):
            return 2.0
        try:
            v = float(s)
        except ValueError:
            return None
    v = float(v)
    if v >= 100:
        return round(1 + v / 100.0, 3)
    if v <= -100:
        return round(1 + 100.0 / abs(v), 3)
    return None


# ---------------------------------------------------------------- jugadas (goles, tarjetas, cambios) ------
def _jugada(k, fuente):
    """Normaliza una jugada de keyEvents ('ev') o de la lista details ('det'). None si no es gol ni tarjeta."""
    tt = k.get("tt") or ""
    t = k.get("t") or ""
    if fuente == "ev":
        if k.get("tanda") or k.get("p") == 5 and (k.get("gol") or tt.startswith("penalty")):
            return None
        es_gol = bool(k.get("gol")) or tt.startswith("goal") or tt in ("penalty---scored", "own-goal")
        clase = "gol" if es_gol else "am" if tt == "yellow-card" or t == "Yellow Card" else \
            "ro" if tt == "red-card" or t == "Red Card" else None
        tipo = "penal" if tt == "penalty---scored" else "autogol" if tt == "own-goal" else "gol"
        sub = "cabeza" if "header" in tt else "tiro_libre" if "free-kick" in tt else "volea" if "volley" in tt else ""
    else:
        if k.get("tanda"):
            return None
        clase = "gol" if k.get("gol") else "am" if k.get("am") else "ro" if k.get("ro") else None
        tipo = "penal" if k.get("pen") else "autogol" if k.get("ag") else "gol"
        sub = ""
    if clase is None:
        return None
    minuto, anad = _minuto(k.get("d"), k.get("c"))
    quienes = k.get("j") or []
    texto = k.get("x") or ""
    if clase == "ro":
        tipo = "segunda_amarilla" if texto.lower().startswith("second yellow") else "roja"
    elif clase == "am":
        tipo = "amarilla"
    try:
        num = int(k.get("id") or 0)
    except ValueError:
        num = 0
    try:
        reloj = float(k.get("c")) if k.get("c") is not None else (minuto or 0) * 60.0
    except (TypeError, ValueError):
        reloj = (minuto or 0) * 60.0
    return {"clase": clase, "tipo": tipo, "subtipo": sub, "c": reloj, "min": minuto, "anad": anad,
            "p": _periodo(k.get("p"), minuto), "e": k.get("e") or "",
            "jid": quienes[0][0] if quienes else "", "jug": quienes[0][1] if quienes else "",
            "asis": quienes[1][1] if (len(quienes) > 1 and clase == "gol" and tipo == "gol") else "",
            "id": num, "w": k.get("w") or ""}


def _sin_repetidos(lista):
    """Quita jugadas repetidas (ESPN a veces ingiere dos veces el mismo partido): misma clase, equipo y jugador
    con relojes a <= 2 min (una roja por jugador como máximo). Se queda la de id mayor (la reprocesada)."""
    orden = sorted(lista, key=lambda g: (g["clase"], g["e"], g["jid"] or g["jug"], g["c"], g["id"]))
    fuera = []
    for g in orden:
        if fuera:
            u = fuera[-1]
            mismo = (u["clase"], u["e"], u["jid"] or u["jug"]) == (g["clase"], g["e"], g["jid"] or g["jug"])
            if mismo and (g["jid"] or g["jug"]) and (g["clase"] == "ro" or abs(g["c"] - u["c"]) <= 120):
                if g["id"] > u["id"]:
                    fuera[-1] = g
                continue
        fuera.append(g)
    return fuera


def _orden_juego(lista):
    return sorted(lista, key=lambda g: (g["p"] or 0, g["c"], g["anad"], g["id"]))


def _goles_por_equipo(lista, id_l, id_v):
    return (sum(1 for g in lista if g["clase"] == "gol" and g["e"] == id_l),
            sum(1 for g in lista if g["clase"] == "gol" and g["e"] == id_v))


def _voltear_autogoles(lista, id_l, id_v):
    fuera = []
    for g in lista:
        if g["clase"] == "gol" and g["tipo"] == "autogol" and g["e"] in (id_l, id_v):
            g = dict(g, e=id_v if g["e"] == id_l else id_l)
        fuera.append(g)
    return fuera


def jugadas_del_partido(e, ex, id_l, id_v, fin_l, fin_v):
    """Elige la mejor lectura de goles y tarjetas. Regresa (goles, tarjetas, cuadran, hay_marcas).
    `cuadran` = los goles con minuto suman exactamente el marcador final de ESPN (incluye tiempos extra)."""
    ev = [j for j in (_jugada(k, "ev") for k in (ex or {}).get("ev") or []) if j]
    det_crudo = ((ex or {}).get("cab") or {}).get("detalles") or e.get("detalles") or []
    det = [j for j in (_jugada(k, "det") for k in det_crudo) if j]
    hay_marcas = bool((ex or {}).get("ev"))

    try:
        limite = (_fecha_dt(e.get("fecha")) + dt.timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        limite = ""
    vivo = [g for g in ev if not g["w"] or not limite or g["w"] <= limite]
    repro = [g for g in ev if g["w"] and limite and g["w"] > limite]

    candidatos = [("ev", ev)]
    if vivo and repro:
        candidatos += [("ev", repro), ("ev", _sin_repetidos(ev)), ("ev", vivo)]
    else:
        candidatos += [("ev", _sin_repetidos(ev))]
    candidatos += [("det", det), ("det", _sin_repetidos(det))]

    elegido = None
    if fin_l is not None and fin_v is not None:
        for fuente, lista in candidatos:
            for variante in (lista, _voltear_autogoles(lista, id_l, id_v)):
                if _goles_por_equipo(variante, id_l, id_v) == (fin_l, fin_v):
                    elegido = (fuente, variante, True)
                    break
            if elegido:
                break
    if not elegido:
        if any(g["clase"] == "gol" for g in ev):
            elegido = ("ev", _sin_repetidos(ev), False)
        else:
            elegido = ("det", _sin_repetidos(det), False)
    fuente, lista, cuadran = elegido

    goles = _orden_juego([g for g in lista if g["clase"] == "gol"])
    tarj = [g for g in lista if g["clase"] in ("am", "ro")]
    if not tarj:      # la fuente elegida no trae tarjetas: se prueba la otra
        otra = det if fuente == "ev" else ev
        tarj = [g for g in otra if g["clase"] in ("am", "ro")]
    tarj = _orden_juego(_sin_repetidos(tarj))
    return goles, tarj, cuadran, hay_marcas


# ---------------------------------------------------------------- fila de partido -------------------------
def estado_de(e, hoy=None):
    """estado (jugado | programado | pospuesto | cancelado | en_juego) y nota."""
    st = e.get("estado") or ""
    if st in ESTADOS_JUGADO:
        return "jugado", ("abandonado según ESPN" if st == "STATUS_ABANDONED" else "")
    if st in ESTADOS_CANCELADO:
        return "cancelado", ""
    if st in ESTADOS_POSPUESTO:
        return "pospuesto", ""
    if e.get("estado_fase") == "in":
        return "en_juego", ""
    if es_jugado(e):
        return "jugado", f"estado ESPN {st}"
    # programado; si la fecha ya pasó hace días es un registro fantasma (ESPN nunca lo actualizó)
    hoy = hoy or ahora_utc()
    try:
        if _fecha_dt(e.get("fecha")) < hoy - dt.timedelta(days=5):
            return "pospuesto", "registro sin resultado en ESPN: sigue como programado con fecha pasada"
    except (TypeError, ValueError):
        pass
    return "programado", ""


def _mejor_momio(ex):
    """Proveedor con 1X2 completo y prioridad más alta (se excluyen momios en vivo)."""
    cand = []
    for m in (ex or {}).get("momios") or []:
        if "live" in (m.get("prov") or "").lower():
            continue
        if None in (momio_decimal(m.get("ml_l")), momio_decimal(m.get("ml_e")), momio_decimal(m.get("ml_v"))):
            continue
        cand.append((m.get("prioridad") if m.get("prioridad") is not None else 99, m))
    if not cand:
        return None
    cand.sort(key=lambda x: x[0])
    return cand[0][1]


def construir_partido(e, ex, desconocidos=None, hoy=None):
    """Arma la fila de partidos.csv y las filas de goles, tarjetas y alineaciones de un evento."""
    if ex and ex.get("error"):
        ex = None
    f = {c: "" for c in COLS_PARTIDOS}
    equipos = e.get("equipos") or []
    loc = next((x for x in equipos if x.get("lado") == "home"), equipos[0] if equipos else {})
    vis = next((x for x in equipos if x.get("lado") == "away"), equipos[1] if len(equipos) > 1 else {})
    id_l, id_v = str(loc.get("id") or ""), str(vis.get("id") or "")
    nom_l = nombre_equipo(id_l, loc.get("nombre"), desconocidos)
    nom_v = nombre_equipo(id_v, vis.get("nombre"), desconocidos)

    f["id"] = e["id"]
    f["fecha_utc"] = e.get("fecha") or ""
    try:
        local_dt = _fecha_dt(e.get("fecha")).astimezone(TZ_MX)
        f["fecha_local"] = local_dt.strftime("%Y-%m-%d")
        f["hora_local"] = local_dt.strftime("%H:%M")
        f["anio"] = str(local_dt.year)
    except (TypeError, ValueError):
        pass
    f["local"], f["visitante"], f["local_id"], f["visitante_id"] = nom_l, nom_v, id_l, id_v
    f["temporada_espn"] = _txt(e.get("temporada"))
    f["fase_espn"] = e.get("slug") or ""
    f["estado_espn"] = e.get("estado") or ""
    estado, nota = estado_de(e, hoy)
    f["estado"] = estado
    notas = [n for n in (nota, NOTAS_MANUALES.get(e["id"], "")) if n]

    info = (ex or {}).get("info") or {}
    f["estadio"] = info.get("estadio") or e.get("estadio") or ""
    f["estadio_id"] = info.get("estadio_id") or e.get("estadio_id") or ""
    f["ciudad"] = info.get("ciudad") or e.get("ciudad") or ""

    # momios (también para partidos programados: sirven de referencia de mercado antes del partido)
    m = _mejor_momio(ex)
    if m:
        f["ml_l"], f["ml_e"], f["ml_v"] = (_txt(momio_decimal(m.get(k))) for k in ("ml_l", "ml_e", "ml_v"))
        f["total_linea"] = _txt(m.get("total"))
        f["over"], f["under"] = _txt(momio_decimal(m.get("over"))), _txt(momio_decimal(m.get("under")))
        f["proveedor"] = m.get("prov") or ""
        ca = m.get("cierre_abre") or {}
        for col, clave in (("ml_l_abre", "ml_l"), ("ml_e_abre", "ml_e"), ("ml_v_abre", "ml_v"),
                           ("over_abre", "over"), ("under_abre", "under")):
            par = ca.get(clave) or [None, None]
            f[col] = _txt(momio_decimal(par[1] if len(par) > 1 else None))
        f["tiene_momios"] = "1"
    else:
        f["tiene_momios"] = "0"
    for c in ("tiene_stats", "tiene_eventos", "tiene_alineaciones", "tiene_tarjetas"):
        f[c] = "0"

    goles_f, tarj_f, alin_f = [], [], []
    if estado != "jugado":
        f["nota"] = "; ".join(notas)
        return f, goles_f, tarj_f, alin_f

    # ---------------- marcador ----------------
    cab = (ex or {}).get("cab") or {}
    cab_eq = {str(x.get("id")): x for x in cab.get("equipos") or []}
    fin_l, fin_v = _ent(loc.get("goles")), _ent(vis.get("goles"))
    if cab_eq.get(id_l) and cab_eq.get(id_v) and cab.get("estado") in ESTADOS_JUGADO:
        # el resumen es más reciente que el scoreboard en caché: manda si trae marcador
        cl, cv = _ent(cab_eq[id_l].get("goles")), _ent(cab_eq[id_v].get("goles"))
        if cl is not None and cv is not None:
            fin_l, fin_v = cl, cv
    goles, tarj, cuadran, hay_marcas = jugadas_del_partido(e, ex, id_l, id_v, fin_l, fin_v)

    marcas = {(k.get("tt") or "") for k in (ex or {}).get("ev") or []}
    periodos = {k.get("p") for k in (ex or {}).get("ev") or []}
    st = e.get("estado")
    hubo_et = (st == "STATUS_FINAL_AET"
               or bool(marcas & {"start-extra-time", "halftime-extra-time", "start-2nd-half-extra-time",
                                 "end-extra-time"})
               or bool(periodos & {3, 4})
               or (st == "STATUS_FINAL_PEN" and str(e.get("reloj") or "").startswith("120")))
    par_l = [_ent(x) for x in (cab_eq.get(id_l) or {}).get("parciales") or []]
    par_v = [_ent(x) for x in (cab_eq.get(id_v) or {}).get("parciales") or []]
    par_ok = (len(par_l) >= 2 and len(par_v) >= 2 and None not in par_l and None not in par_v)

    et_l = et_v = 0
    if hubo_et:
        if par_ok and len(par_l) >= 4 and len(par_v) >= 4 and \
                sum(par_l[:4]) == fin_l and sum(par_v[:4]) == fin_v:
            et_l, et_v = par_l[2] + par_l[3], par_v[2] + par_v[3]
        elif cuadran:
            et_l = sum(1 for g in goles if g["e"] == id_l and g["p"] in (3, 4))
            et_v = sum(1 for g in goles if g["e"] == id_v and g["p"] in (3, 4))
        else:
            notas.append("hubo tiempos extra y no se pudo separar el marcador de 90 min")
    if fin_l is not None and fin_v is not None:
        f["gl"], f["gv"] = str(fin_l - et_l), str(fin_v - et_v)
        if hubo_et:
            f["gl_et"], f["gv_et"] = str(fin_l), str(fin_v)
    pen_l = _ent((cab_eq.get(id_l) or {}).get("tanda") if cab_eq.get(id_l) else None)
    pen_v = _ent((cab_eq.get(id_v) or {}).get("tanda") if cab_eq.get(id_v) else None)
    if pen_l is None or pen_v is None:
        pen_l, pen_v = _ent(loc.get("tanda")), _ent(vis.get("tanda"))
    if pen_l is not None and pen_v is not None and (st == "STATUS_FINAL_PEN" or pen_l + pen_v > 0):
        f["pen_l"], f["pen_v"] = str(pen_l), str(pen_v)
    elif st == "STATUS_FINAL_PEN":
        notas.append("se definió en penales pero ESPN no trae el marcador de la tanda")

    # ---------------- medio tiempo ----------------
    reg_l, reg_v = (fin_l or 0) - et_l, (fin_v or 0) - et_v
    ht_par = ht_ev = None
    if par_ok and par_l[0] + par_l[1] == reg_l and par_v[0] + par_v[1] == reg_v:
        ht_par = (par_l[0], par_v[0])
    if cuadran and (goles or hay_marcas):
        ht_ev = (sum(1 for g in goles if g["e"] == id_l and g["p"] == 1),
                 sum(1 for g in goles if g["e"] == id_v and g["p"] == 1))
    if fin_l == 0 and fin_v == 0:
        f["gl_ht"], f["gv_ht"], f["ht_fuente"] = "0", "0", "marcador"     # 0-0 final: el descanso fue 0-0
    elif ht_ev is not None:
        f["gl_ht"], f["gv_ht"], f["ht_fuente"] = str(ht_ev[0]), str(ht_ev[1]), "eventos"
        if ht_par is not None and ht_par != ht_ev:
            notas.append(f"medio tiempo: eventos {ht_ev[0]}-{ht_ev[1]} vs parciales ESPN {ht_par[0]}-{ht_par[1]}")
    elif ht_par is not None:
        f["gl_ht"], f["gv_ht"], f["ht_fuente"] = str(ht_par[0]), str(ht_par[1]), "parciales"
    if st == "STATUS_ABANDONED" and goles and not cuadran:
        en_cancha = _goles_por_equipo(goles, id_l, id_v)
        notas.append(f"resultado oficial {fin_l}-{fin_v} distinto de los goles en cancha "
                     f"{en_cancha[0]}-{en_cancha[1]} (resultado de escritorio)")
        f["gl_ht"] = str(sum(1 for g in goles if g["e"] == id_l and g["p"] == 1))
        f["gv_ht"] = str(sum(1 for g in goles if g["e"] == id_v and g["p"] == 1))
        f["ht_fuente"] = "eventos"

    # ---------------- sede, asistencia, árbitro ----------------
    asis = _ent(info.get("asistencia"))
    if not asis:
        asis = _ent(e.get("asistencia"))
    todas_notas = " ".join(cab.get("notas") or e.get("notas") or [])
    if asis:
        f["asistencia"] = str(asis)
    elif "behind closed doors" in todas_notas.lower():
        f["asistencia"] = "0"
    for nombre, puesto in info.get("arbitros") or []:
        if nombre and nombre.strip() not in ("", "0") and (puesto in (None, "Referee")):
            nombre = nombre.strip()
            if "," in nombre:       # "Archundia, Armando" -> "Armando Archundia"
                ap, _, nom = nombre.partition(",")
                nombre = f"{nom.strip()} {ap.strip()}".strip()
            f["arbitro"] = nombre
            break

    # ---------------- estadísticas ----------------
    box = (ex or {}).get("box") or {}
    bl = (box.get(id_l) or {}).get("est") or {}
    bv = (box.get(id_v) or {}).get("est") or {}

    def val(d, k):
        try:
            return float(d.get(k))
        except (TypeError, ValueError):
            return None

    def fmt(x, decimales=False):
        if x is None:
            return ""
        return (f"{x:.1f}" if decimales else str(int(round(x))))

    tiros = (val(bl, "totalShots") or 0) + (val(bv, "totalShots") or 0)
    faltas = (val(bl, "foulsCommitted") or 0) + (val(bv, "foulsCommitted") or 0)
    if bl and bv and tiros > 0 and faltas > 0:
        f["tiene_stats"] = "1"
        for col, clave in STATS_LADO + STATS_EXTRA:
            a, b = val(bl, clave), val(bv, clave)
            if a is None or b is None:
                continue
            if clave == "possessionPct":
                if a > 0 and b > 0 and abs(a + b - 100) <= 1.5:
                    f[f"{col}_l"], f[f"{col}_v"] = fmt(a, True), fmt(b, True)
                continue
            if (col, clave) in STATS_EXTRA and a + b <= 0:
                continue    # ESPN manda 0 cuando no midió pases, centros, etc.
            f[f"{col}_l"], f[f"{col}_v"] = fmt(a), fmt(b)

    # ---------------- goles y tarjetas ----------------
    nombre_de = {id_l: nom_l, id_v: nom_v}
    total_goles = (fin_l or 0) + (fin_v or 0)
    if cuadran:       # incluye el 0-0 (no hay goles que listar)
        f["tiene_eventos"] = "1"
    for g in goles:
        goles_f.append({"partido_id": e["id"], "minuto": _txt(g["min"]), "anadido": str(g["anad"]),
                        "periodo": _txt(g["p"]), "equipo": nombre_de.get(g["e"], ""), "jugador": g["jug"],
                        "tipo": g["tipo"], "subtipo": g["subtipo"], "jugador_id": g["jid"],
                        "asistencia": g["asis"]})
    for g in tarj:
        tarj_f.append({"partido_id": e["id"], "minuto": _txt(g["min"]), "periodo": _txt(g["p"]),
                       "equipo": nombre_de.get(g["e"], ""), "jugador": g["jug"], "tipo": g["tipo"],
                       "anadido": str(g["anad"]), "jugador_id": g["jid"]})
    if f["tiene_stats"] == "1" and hay_marcas:
        # las tarjetas con minuto son confiables si su conteo de amarillas coincide con el boxscore
        am_ev = sum(1 for g in tarj if g["clase"] == "am")
        am_box = (val(bl, "yellowCards") or 0) + (val(bv, "yellowCards") or 0)
        if am_ev == am_box or (am_box > 0 and abs(am_ev - am_box) <= 1):
            f["tiene_tarjetas"] = "1"

    # ---------------- alineaciones ----------------
    cambios = {}      # jugador_id -> [minuto_entra, minuto_sale] según las jugadas de cambio
    for k in (ex or {}).get("ev") or []:
        if (k.get("tt") == "substitution" or k.get("t") == "Substitution") and k.get("j"):
            minuto, _a = _minuto(k.get("d"), k.get("c"))
            entra = k["j"][0][0]
            sale = k["j"][1][0] if len(k["j"]) > 1 else ""
            if entra:
                cambios.setdefault(entra, [None, None])
                if cambios[entra][0] is None:
                    cambios[entra][0] = minuto
            if sale:
                cambios.setdefault(sale, [None, None])
                cambios[sale][1] = minuto
    titulares = {}
    for a in (ex or {}).get("al") or []:
        tid = a.get("e") or ""
        titulares[tid] = sum(1 for j in a.get("j") or [] if j.get("tit"))
        forma = a.get("formacion") or ""
        if tid == id_l:
            f["formacion_l"] = forma
        elif tid == id_v:
            f["formacion_v"] = forma
        for j in a.get("j") or []:
            mins = sorted(m for m in (_minuto(x[0], None)[0] for x in j.get("jug") or [] if "S" in (x[1] or ""))
                          if m is not None)
            entra = sale = None
            if j.get("entra") and j.get("sale"):
                entra = mins[0] if mins else None
                sale = mins[-1] if len(mins) > 1 and mins[-1] > mins[0] else None
            elif j.get("entra"):
                entra = mins[0] if mins else None
            elif j.get("sale"):
                sale = mins[0] if mins else None
            c = cambios.get(j.get("id") or "", [None, None])
            if j.get("entra") and entra is None:
                entra = c[0]
            if j.get("sale") and sale is None:
                sale = c[1]
            alin_f.append({"partido_id": e["id"], "equipo": nombre_de.get(tid, ""), "jugador_id": j.get("id") or "",
                           "jugador": j.get("n") or "", "titular": "1" if j.get("tit") else "0",
                           "posicion": "" if j.get("pos") in (None, "SUB") else j.get("pos"),
                           "minuto_entra": _txt(entra), "minuto_sale": _txt(sale), "formacion": forma})
    if titulares.get(id_l) == 11 and titulares.get(id_v) == 11:
        f["tiene_alineaciones"] = "1"

    f["nota"] = "; ".join(n for n in notas if n)
    return f, goles_f, tarj_f, alin_f


# ---------------------------------------------------------------- torneo, fase, pierna --------------------
FASES_SLUG = {"final": "final", "finals": "final", "semi-finals": "semifinal", "semifinals": "semifinal",
              "quarter-finals": "cuartos", "quarterfinals": "cuartos"}


def torneo_de(slug, temporada):
    """('Apertura'|'Clausura', año). El año viene en el slug hasta 2023; después se deduce de la temporada."""
    base = (slug or "").split("---")[0]
    nombre = "Apertura" if "apertura" in base else "Clausura" if "clausura" in base else ""
    m = re.search(r"(\d{4})", slug or "")
    if m:
        anio = int(m.group(1))
    else:
        try:
            anio = int(temporada) + (1 if nombre == "Clausura" else 0)
        except (TypeError, ValueError):
            anio = 0
    return nombre, anio


def fase_de_slug(slug):
    if "---" not in (slug or ""):
        return "regular"
    cola = slug.split("---", 1)[1]
    return FASES_SLUG.get(cola, "repechaje")     # reclassification, 7th-place-vs-8th-place, 8th-seed-game...


def clave_torneo(nombre):
    """Orden cronológico de torneos: 'Clausura 2026' < 'Apertura 2026'."""
    tipo, _, anio = nombre.partition(" ")
    return (int(anio or 0), 0 if tipo == "Clausura" else 1)


def asignar_torneo_fase(filas, hoy=None):
    """Llena torneo, fase, pierna y serie de TODAS las filas (sólo depende de columnas de la propia tabla)."""
    hoy = hoy or ahora_utc()
    por_torneo = {}
    for f in filas:
        nombre, anio = torneo_de(f["fase_espn"], f["temporada_espn"])
        f["torneo"] = f"{nombre} {anio}".strip()
        f["fase"] = fase_de_slug(f["fase_espn"])
        f["pierna"], f["serie"] = "", ""
        f["nota"] = "; ".join(n for n in f.get("nota", "").split("; ")
                              if n and not n.startswith(("fase corregida", "posible duplicado")))
        por_torneo.setdefault(f["torneo"], []).append(f)

    def anota(f, texto):
        f["nota"] = "; ".join(x for x in (f.get("nota", ""), texto) if x)

    for torneo, lista in por_torneo.items():
        lista.sort(key=lambda f: (f["fecha_utc"], f["id"]))
        liguilla = [f for f in lista if f["fase"] != "regular"]
        ini_liguilla = min((f["fecha_utc"] for f in liguilla), default=None)

        # 1) cruces repetidos en fase regular (torneo a una vuelta): los posteriores son de liguilla mal etiquetados
        vistos = {}
        for f in lista:
            if f["fase"] != "regular" or f["estado"] != "jugado":
                continue
            par = frozenset((f["local_id"], f["visitante_id"]))
            if par in vistos:
                if ini_liguilla and f["fecha_utc"] >= (
                        _fecha_dt(ini_liguilla) - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%MZ"):
                    f["fase"] = "liguilla?"
                    liguilla.append(f)
                else:
                    anota(f, "posible duplicado: el cruce ya aparece en fase regular de este torneo")
            else:
                vistos[par] = f

        # 2) estructura de la liguilla por series (pareja de equipos)
        if liguilla:
            series = {}
            for f in liguilla:
                series.setdefault(frozenset((f["local_id"], f["visitante_id"])), []).append(f)
            orden = sorted(series.values(), key=lambda s: max(x["fecha_utc"] for x in s))
            cuenta = {}
            for s in orden:
                fases = {x["fase"] for x in s}
                cuenta[tuple(sorted(fases))] = cuenta.get(tuple(sorted(fases)), 0) + 1
            coherente = (cuenta.get(("final",), 0) == 1 and cuenta.get(("semifinal",), 0) == 2
                         and cuenta.get(("cuartos",), 0) == 4
                         and all(k in (("final",), ("semifinal",), ("cuartos",), ("repechaje",)) for k in cuenta))
            terminado = max(f["fecha_utc"] for f in lista) < (hoy - dt.timedelta(days=45)).strftime("%Y-%m-%dT%H:%MZ")
            if not coherente and terminado and len(orden) >= 7:
                # torneo histórico con fases mal etiquetadas en ESPN: se deduce por orden cronológico de las series
                esperado = ["final"] + ["semifinal"] * 2 + ["cuartos"] * 4
                for i, s in enumerate(reversed(orden)):
                    fase = esperado[i] if i < len(esperado) else "repechaje"
                    for x in s:
                        if x["fase"] != fase:
                            anota(x, f"fase corregida por estructura (ESPN: {fase_de_slug(x['fase_espn'])})")
                            x["fase"] = fase
            else:
                for s in orden:       # 'liguilla?' hereda la fase de su serie, si la serie tiene una sola
                    fases = {x["fase"] for x in s} - {"liguilla?"}
                    for x in s:
                        if x["fase"] == "liguilla?":
                            x["fase"] = fases.pop() if len(fases) == 1 else "repechaje"
                            anota(x, "fase corregida por estructura (ESPN: regular)")
            # 3) pierna y serie
            for s in orden:
                s.sort(key=lambda x: (x["fecha_utc"], x["id"]))
                nombres = sorted({s[0]["local"], s[0]["visitante"]})
                for i, x in enumerate(s):
                    x["serie"] = " vs ".join(nombres)
                    if len(s) >= 2:
                        x["pierna"] = str(min(i + 1, 2))
                    elif x["fase"] in ("cuartos", "semifinal", "final"):
                        x["pierna"] = "1"     # serie a ida y vuelta de la que todavía sólo hay un partido
                    else:
                        x["pierna"] = ""      # repechaje / play-in a partido único
    return filas


# ---------------------------------------------------------------- armado incremental ----------------------
def _agrupar(filas, clave="partido_id"):
    grupos = {}
    for f in filas:
        grupos.setdefault(f[clave], []).append(f)
    return grupos


def _fila_cuadra(fila, e):
    """¿La fila guardada sigue describiendo lo que hoy dice el scoreboard? (mismo estado, fecha y marcador)"""
    if fila.get("estado_espn") != (e.get("estado") or "") or fila.get("fecha_utc") != (e.get("fecha") or ""):
        return False
    if fila.get("estado") == "jugado":
        eq = e.get("equipos") or []
        loc = next((x for x in eq if x.get("lado") == "home"), eq[0] if eq else {})
        vis = next((x for x in eq if x.get("lado") == "away"), eq[1] if len(eq) > 1 else {})
        fin = (fila.get("gl_et") or fila.get("gl"), fila.get("gv_et") or fila.get("gv"))
        if fin != (_txt(_ent(loc.get("goles"))), _txt(_ent(vis.get("goles")))):
            return False
    return True


def construir_tablas(ids_rehacer=None, verboso=True):
    """Regenera partidos/goles/tarjetas/alineaciones.
    - ids_rehacer=None: rehace todo partido que tenga extracto en caché; el resto se conserva del CSV.
    - ids_rehacer=conjunto: sólo rehace esos (más lo nuevo o lo que cambió en el scoreboard).
    Regresa un dict con conteos y la lista de equipos sin nombre canónico."""
    hoy = ahora_utc()
    viejos = {f["id"]: f for f in leer_csv(ARCH_PARTIDOS)}
    viejos_g = _agrupar(leer_csv(ARCH_GOLES))
    viejos_t = _agrupar(leer_csv(ARCH_TARJETAS))
    viejos_a = _agrupar(leer_csv(ARCH_ALINEACIONES))
    eventos = cargar_calendario()
    anios_sb = set(anios_en_cache())
    desconocidos = set()

    partidos, goles, tarjetas, alineaciones = {}, {}, {}, {}
    rehechos = conservados = 0
    for eid, e in eventos.items():
        tiene_ex = os.path.exists(ruta_res(eid))
        viejo = viejos.get(eid)
        if ids_rehacer is None:
            rehacer = tiene_ex or viejo is None or not _fila_cuadra(viejo, e)
        else:
            rehacer = eid in ids_rehacer or viejo is None or not _fila_cuadra(viejo, e)
        if not rehacer:
            # el estado "programado con fecha pasada" depende del día en que se corre
            if viejo["estado"] == "programado" and estado_de(e, hoy)[0] != "programado":
                rehacer = True
        if rehacer:
            ex = leer_gz(ruta_res(eid)) if tiene_ex else None
            f, g, t, a = construir_partido(e, ex, desconocidos, hoy)
            if viejo and f["tiene_momios"] == "0" and viejo.get("tiene_momios") == "1":
                for c in COLS_MOMIOS:       # ESPN retiró los momios: se conservan los ya capturados
                    f[c] = viejo.get(c, "")
            if viejo and not tiene_ex and f["estado"] == "jugado" and _fila_cuadra(viejo, e):
                f, g, t, a = viejo, viejos_g.get(eid, []), viejos_t.get(eid, []), viejos_a.get(eid, [])
            rehechos += 1
        else:
            f, g, t, a = viejo, viejos_g.get(eid, []), viejos_t.get(eid, []), viejos_a.get(eid, [])
            conservados += 1
        partidos[eid], goles[eid], tarjetas[eid], alineaciones[eid] = f, g, t, a

    eliminados = []
    for eid, viejo in viejos.items():
        if eid in partidos:
            continue
        try:
            anio_utc = int(viejo["fecha_utc"][:4])
        except ValueError:
            anio_utc = 0
        if anio_utc in anios_sb:
            eliminados.append(eid)      # ESPN ya no lista el evento en ese año
            continue
        partidos[eid] = viejo
        goles[eid], tarjetas[eid], alineaciones[eid] = viejos_g.get(eid, []), viejos_t.get(eid, []), viejos_a.get(eid, [])
        conservados += 1

    filas = list(partidos.values())
    for f in filas:
        for c in COLS_PARTIDOS:
            f.setdefault(c, "")
    asignar_torneo_fase(filas, hoy)
    filas.sort(key=lambda f: (f["fecha_utc"], f["id"]))
    orden_ids = [f["id"] for f in filas]
    escribir_csv(ARCH_PARTIDOS, COLS_PARTIDOS, filas)
    escribir_csv(ARCH_GOLES, COLS_GOLES, (x for i in orden_ids for x in goles.get(i, [])))
    escribir_csv(ARCH_TARJETAS, COLS_TARJETAS, (x for i in orden_ids for x in tarjetas.get(i, [])))
    escribir_csv(ARCH_ALINEACIONES, COLS_ALINEACIONES, (x for i in orden_ids for x in alineaciones.get(i, [])))
    r = {"partidos": len(filas), "rehechos": rehechos, "conservados": conservados,
         "eliminados": eliminados, "equipos_sin_nombre_canonico": sorted(desconocidos)}
    if verboso:
        log(f"tablas: {r['partidos']} partidos ({rehechos} rehechos, {conservados} conservados, "
            f"{len(eliminados)} eliminados)")
    return r


# ---------------------------------------------------------------- torneo en curso, pendientes, tabla ------
def torneo_en_curso(filas):
    """El torneo más reciente que tenga partidos (por orden cronológico de torneos)."""
    torneos = {f["torneo"] for f in filas if f.get("torneo")}
    return max(torneos, key=clave_torneo) if torneos else ""


def escribir_pendientes(filas):
    torneo = torneo_en_curso(filas)
    pend = [f for f in filas if f["torneo"] == torneo and f["estado"] in ("programado", "en_juego", "pospuesto")]
    pend.sort(key=lambda f: (f["fecha_utc"], f["id"]))

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    salida = {"torneo": torneo, "generado_utc": ahora_iso(), "fuente": "ESPN scoreboard mex.1",
              "partidos": [{"id": f["id"], "fecha_utc": f["fecha_utc"], "fecha_local": f["fecha_local"],
                            "hora_local": f["hora_local"], "fase": f["fase"], "pierna": f["pierna"],
                            "estado": f["estado"], "local": f["local"], "visitante": f["visitante"],
                            "estadio": f["estadio"], "ciudad": f["ciudad"],
                            "momios": ({"ml_l": num(f["ml_l"]), "ml_e": num(f["ml_e"]), "ml_v": num(f["ml_v"]),
                                        "total_linea": num(f["total_linea"]), "over": num(f["over"]),
                                        "under": num(f["under"]), "proveedor": f["proveedor"]}
                                       if f["tiene_momios"] == "1" else None)} for f in pend]}
    # generado_utc cambia en cada corrida: sólo se reescribe si cambió el contenido
    anterior = None
    if os.path.exists(ARCH_PENDIENTE):
        try:
            with open(ARCH_PENDIENTE, encoding="utf-8") as fh:
                anterior = json.load(fh)
        except (OSError, ValueError):
            anterior = None
    if anterior and {k: v for k, v in anterior.items() if k != "generado_utc"} == \
            {k: v for k, v in salida.items() if k != "generado_utc"}:
        return anterior
    escribir_texto(ARCH_PENDIENTE, json.dumps(salida, ensure_ascii=False, indent=1) + "\n")
    return salida


def descargar_standings():
    d = pedir_json(URL_STANDINGS)
    guardar_gz(ARCH_STANDINGS, {"descargado": ahora_iso(), "datos": d})
    return d


def leer_standings(d):
    """{equipo canónico: {pos, PJ, G, E, P, GF, GC, DG, PTS}} y nombre de la tabla en ESPN."""
    hijos = (d or {}).get("children") or []
    if not hijos:
        return {}, ""
    tabla = {}
    for ent in (hijos[0].get("standings") or {}).get("entries") or []:
        s = {x.get("name"): x.get("value", x.get("displayValue")) for x in ent.get("stats") or []}
        nombre = nombre_equipo(str((ent.get("team") or {}).get("id")), (ent.get("team") or {}).get("displayName"))
        tabla[nombre] = {"pos": _ent(s.get("rank")), "PJ": _ent(s.get("gamesPlayed")), "G": _ent(s.get("wins")),
                         "E": _ent(s.get("ties")), "P": _ent(s.get("losses")), "GF": _ent(s.get("pointsFor")),
                         "GC": _ent(s.get("pointsAgainst")), "PTS": _ent(s.get("points"))}
        t = tabla[nombre]
        t["DG"] = (t["GF"] - t["GC"]) if None not in (t["GF"], t["GC"]) else None
    return tabla, hijos[0].get("name") or ""


def calcular_tabla(filas, torneo):
    """Tabla general del torneo (fase regular) con desglose local/visita. Desempate: PTS, DG, GF,
    resultado entre empatados, goles de visita, nombre (el reglamento sigue con Fair Play y sorteo)."""
    reg = [f for f in filas if f["torneo"] == torneo and f["fase"] == "regular"]
    equipos = sorted({f["local"] for f in reg} | {f["visitante"] for f in reg})
    campos = ("PJ", "G", "E", "P", "GF", "GC", "PTS")
    t = {eq: {f"{c}{s}": 0 for c in campos for s in ("", "_L", "_V")} for eq in equipos}
    jugados = [f for f in reg if f["estado"] == "jugado" and f["gl"] != "" and f["gv"] != ""]
    for f in jugados:
        gl, gv = int(f["gl"]), int(f["gv"])
        for eq, suf, gf, gc in ((f["local"], "_L", gl, gv), (f["visitante"], "_V", gv, gl)):
            pts = 3 if gf > gc else 1 if gf == gc else 0
            for s in ("", suf):
                r = t[eq]
                r[f"PJ{s}"] += 1
                r[f"G{s}"] += gf > gc
                r[f"E{s}"] += gf == gc
                r[f"P{s}"] += gf < gc
                r[f"GF{s}"] += gf
                r[f"GC{s}"] += gc
                r[f"PTS{s}"] += pts
    for eq in equipos:
        for s in ("", "_L", "_V"):
            t[eq][f"DG{s}"] = t[eq][f"GF{s}"] - t[eq][f"GC{s}"]

    def entre_si(eq, grupo):
        pts = dg = 0
        for f in jugados:
            if f["local"] in grupo and f["visitante"] in grupo and eq in (f["local"], f["visitante"]):
                gf, gc = (int(f["gl"]), int(f["gv"])) if f["local"] == eq else (int(f["gv"]), int(f["gl"]))
                pts += 3 if gf > gc else 1 if gf == gc else 0
                dg += gf - gc
        return pts, dg

    grupos = {}
    for eq in equipos:
        grupos.setdefault((t[eq]["PTS"], t[eq]["DG"], t[eq]["GF"]), []).append(eq)
    orden = []
    for clave in sorted(grupos, reverse=True):
        g = grupos[clave]
        g.sort(key=lambda eq: (-entre_si(eq, g)[0], -entre_si(eq, g)[1], -t[eq]["GF_V"], eq))
        orden += g
    return [dict(equipo=eq, pos=i + 1, **t[eq]) for i, eq in enumerate(orden)]


def escribir_tabla(filas, standings=None):
    """tabla_<torneo>.csv del torneo en curso, comparada con el endpoint standings de ESPN."""
    torneo = torneo_en_curso(filas)
    if not torneo:
        return {}
    tabla = calcular_tabla(filas, torneo)
    espn, nombre_espn = leer_standings(standings) if standings else ({}, "")
    tipo, _, anio = torneo.partition(" ")
    # la tabla de ESPN sólo es comparable si es la del mismo torneo
    # (en el Clausura ESPN puede nombrar la tabla con el año de inicio de la temporada: se aceptan ambos)
    anios_ok = [anio] + ([str(int(anio) - 1)] if tipo == "Clausura" and anio.isdigit() else [])
    comparable = bool(espn) and tipo.lower() in nombre_espn.lower() and any(a in nombre_espn for a in anios_ok)
    if comparable and set(espn) != {r["equipo"] for r in tabla}:
        comparable = False        # no son los mismos equipos: es la tabla de otro torneo
    columnas = (["pos", "equipo"] + [f"{c}{s}" for s in ("", "_L", "_V")
                                     for c in ("PJ", "G", "E", "P", "GF", "GC", "DG", "PTS")]
                + ["espn_pos", "espn_PJ", "espn_G", "espn_E", "espn_P", "espn_GF", "espn_GC", "espn_DG", "espn_PTS",
                   "coincide_espn"])
    difs = []
    for r in tabla:
        s = espn.get(r["equipo"]) if comparable else None
        if s:
            for c in ("pos", "PJ", "G", "E", "P", "GF", "GC", "DG", "PTS"):
                r[f"espn_{c}"] = _txt(s.get(c))
            cifras = all(r[c] == s.get(c) for c in ("PJ", "G", "E", "P", "GF", "GC", "DG", "PTS"))
            r["coincide_espn"] = "1" if cifras and r["pos"] == s.get("pos") else ("cifras" if cifras else "0")
            if not cifras:
                difs.append({"equipo": r["equipo"], "calculado": {c: r[c] for c in ("PJ", "G", "E", "P", "GF", "GC", "PTS")},
                             "espn": {c: s.get(c) for c in ("PJ", "G", "E", "P", "GF", "GC", "PTS")}})
            elif r["pos"] != s.get("pos"):
                difs.append({"equipo": r["equipo"], "pos_calculada": r["pos"], "pos_espn": s.get("pos")})
        else:
            r["coincide_espn"] = ""
    archivo = os.path.join(RAIZ, f"tabla_{tipo.lower()}{anio}.csv")
    escribir_csv(archivo, columnas, ({k: _txt(v) for k, v in r.items()} for r in tabla))
    return {"torneo": torneo, "archivo": archivo, "comparada_con_espn": comparable,
            "tabla_espn": nombre_espn, "coincide_con_espn": comparable and not difs, "diferencias": difs,
            "lider": tabla[0]["equipo"] if tabla else ""}


# ----------------------------------------------------------------------------------------------------------
# Verificación
# ----------------------------------------------------------------------------------------------------------
def verificar(filas=None, tabla_info=None):
    """Pruebas de consistencia sobre las tablas. Regresa lista de {prueba, ok, detalle}."""
    filas = filas if filas is not None else leer_csv(ARCH_PARTIDOS)
    goles = _agrupar(leer_csv(ARCH_GOLES))
    hoy = ahora_utc()
    pruebas = []

    def agrega(nombre, ok, detalle=""):
        pruebas.append({"prueba": nombre, "ok": bool(ok), "detalle": detalle})

    ids = [f["id"] for f in filas]
    agrega("ids únicos", len(ids) == len(set(ids)), f"{len(ids)} filas, {len(set(ids))} ids")

    vistos, rep = {}, []
    for f in filas:
        if f["estado"] != "jugado":
            continue
        k = (f["torneo"], f["fase"], f["pierna"], f["local"], f["visitante"])
        if k in vistos:
            rep.append(f"{f['torneo']} {f['fase']} {f['local']}-{f['visitante']} ({vistos[k]} y {f['id']})")
        vistos[k] = f["id"]
    agrega("sin partidos jugados duplicados (torneo, fase, pierna, local, visitante)", not rep, "; ".join(rep[:10]))

    sin_marcador = [f["id"] for f in filas if f["estado"] == "jugado" and (f["gl"] == "" or f["gv"] == "")]
    agrega("todo partido jugado tiene marcador", not sin_marcador, ",".join(sin_marcador[:10]))

    malos, excepciones = [], []
    for f in filas:
        if f["gl_ht"] == "" or f["gl"] == "":
            continue
        if int(f["gl_ht"]) > int(f["gl"]) or int(f["gv_ht"]) > int(f["gv"]):
            (excepciones if "escritorio" in f["nota"] else malos).append(
                f"{f['id']} {f['fecha_local']} {f['local']}-{f['visitante']} HT {f['gl_ht']}-{f['gv_ht']} FT {f['gl']}-{f['gv']}")
    agrega("gl_ht <= gl y gv_ht <= gv", not malos,
           "; ".join(malos[:10]) + (f" | excepciones documentadas (resultado de escritorio): {'; '.join(excepciones)}"
                                    if excepciones else ""))

    malos = [f["id"] for f in filas if f["gl_et"] != "" and
             (int(f["gl_et"]) < int(f["gl"]) or int(f["gv_et"]) < int(f["gv"]))]
    agrega("marcador tras tiempos extra >= marcador de 90 min", not malos, ",".join(malos))

    malos = []
    nocturnos = 0
    for f in filas:
        try:
            loc = _fecha_dt(f["fecha_utc"]).astimezone(TZ_MX)
        except (TypeError, ValueError):
            malos.append(f["id"])
            continue
        if loc.strftime("%Y-%m-%d") != f["fecha_local"]:
            malos.append(f["id"])
        if f["fecha_utc"][:10] != f["fecha_local"]:
            nocturnos += 1
    agrega("fecha_local = fecha_utc convertida a America/Mexico_City", not malos,
           f"{nocturnos} partidos nocturnos caen en el día UTC siguiente y quedan en su día local correcto"
           + (f"; fallan {malos[:10]}" if malos else ""))

    # partidos por torneo en fase regular: n equipos a una vuelta = n(n-1)/2
    por_torneo = {}
    for f in filas:
        por_torneo.setdefault(f["torneo"], []).append(f)
    raros, normales = [], 0
    en_curso = torneo_en_curso(filas)
    for torneo in sorted(por_torneo, key=clave_torneo):
        reg = [f for f in por_torneo[torneo] if f["fase"] == "regular"]
        equipos = {f["local"] for f in reg} | {f["visitante"] for f in reg}
        esperado = len(equipos) * (len(equipos) - 1) // 2
        jug = sum(1 for f in reg if f["estado"] == "jugado")
        pares = {frozenset((f["local"], f["visitante"])) for f in reg if f["estado"] == "jugado"}
        if jug == esperado and len(pares) == esperado:
            normales += 1
        else:
            otros = {}
            for f in reg:
                if f["estado"] != "jugado":
                    otros[f["estado"]] = otros.get(f["estado"], 0) + 1
            raros.append(f"{torneo}: {jug} de {esperado} jugados ({len(equipos)} equipos; otros: {otros or '-'})")
    explicables = [r for r in raros if r.startswith(("Clausura 2020", en_curso))]
    agrega("fase regular completa por torneo (n equipos a una vuelta)", len(raros) == len(explicables),
           f"{normales} torneos completos; incompletos: {'; '.join(raros) or 'ninguno'}")

    raros = []
    for torneo in sorted(por_torneo, key=clave_torneo):
        lig = [f for f in por_torneo[torneo] if f["fase"] != "regular"]
        if not lig:
            continue
        if max(f["fecha_utc"] for f in por_torneo[torneo]) >= (hoy - dt.timedelta(days=45)).strftime("%Y-%m-%dT%H:%MZ"):
            continue      # liguilla todavía en juego
        c = {}
        for f in lig:
            c[f["fase"]] = c.get(f["fase"], 0) + 1
        if (c.get("final"), c.get("semifinal"), c.get("cuartos")) != (2, 4, 8):
            raros.append(f"{torneo}: {c}")
        piernas = [f for f in lig if f["fase"] in ("final", "semifinal", "cuartos") and f["pierna"] not in ("1", "2")]
        if piernas:
            raros.append(f"{torneo}: {len(piernas)} partidos de liguilla sin pierna")
    agrega("liguilla: 8 partidos de cuartos, 4 de semifinal y 2 de final por torneo", not raros, "; ".join(raros))

    malos = []
    for f in filas:
        if f["tiene_eventos"] != "1":
            continue
        g = goles.get(f["id"], [])
        gl = sum(1 for x in g if x["equipo"] == f["local"])
        gv = sum(1 for x in g if x["equipo"] == f["visitante"])
        fin = (int(f["gl_et"] or f["gl"]), int(f["gv_et"] or f["gv"]))
        if (gl, gv) != fin:
            malos.append(f["id"])
    agrega("goles.csv suma el marcador en los partidos con tiene_eventos=1", not malos, ",".join(malos[:10]))

    canon = set(EQUIPOS.values())
    fuera = sorted(({f["local"] for f in filas} | {f["visitante"] for f in filas}) - canon)
    agrega("todos los equipos tienen nombre canónico", not fuera, ", ".join(fuera))

    pend = [f for f in filas if f["estado"] == "programado"]
    viejos = [f["id"] for f in pend if f["fecha_utc"] < (hoy - dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%MZ")]
    agrega("no hay partidos 'programado' con fecha pasada", not viejos, ",".join(viejos))

    if tabla_info:
        if tabla_info.get("comparada_con_espn"):
            agrega(f"tabla del {tabla_info['torneo']} = standings de ESPN", tabla_info.get("coincide_con_espn"),
                   json.dumps(tabla_info.get("diferencias"), ensure_ascii=False) if tabla_info.get("diferencias") else
                   "18 equipos con PJ, G, E, P, GF, GC, DG, PTS y posición idénticos")
        else:
            agrega(f"tabla del {tabla_info.get('torneo')} = standings de ESPN", True,
                   f"sin comparar: ESPN publica la tabla de '{tabla_info.get('tabla_espn')}'")
    return pruebas


# ----------------------------------------------------------------------------------------------------------
# d) COBERTURA.md (cobertura por torneo, diccionario de columnas y conciliación con los históricos previos)
# ----------------------------------------------------------------------------------------------------------
DICCIONARIO = [
    ("id", "Identificador del evento en ESPN (llave de todas las tablas)."),
    ("fecha_utc", "Fecha y hora de inicio en UTC, ISO 8601 (`2026-11-14T23:00Z`)."),
    ("fecha_local", "Fecha en America/Mexico_City (los partidos nocturnos caen en el día UTC siguiente)."),
    ("anio", "Año de `fecha_local`."),
    ("torneo", "`Apertura AAAA` o `Clausura AAAA` (Invierno/Verano de 2001-2002 se nombran igual)."),
    ("fase", "`regular`, `repechaje` (reclasificación o play-in), `cuartos`, `semifinal`, `final`."),
    ("pierna", "1 = ida, 2 = vuelta en series a dos partidos (orden cronológico del cruce); vacío en fase "
               "regular y en repechaje a partido único."),
    ("estado", "`jugado`, `programado`, `pospuesto`, `cancelado` (y `en_juego` si se corre durante un partido)."),
    ("local, visitante", "Nombre canónico, único y estable por id de ESPN."),
    ("gl, gv", "Goles al final del tiempo REGLAMENTARIO (90 min + agregado). Nunca incluyen tiempos extra ni penales."),
    ("gl_et, gv_et", "Marcador tras 120 min; sólo si hubo tiempos extra (finales). Vacío en los demás."),
    ("pen_l, pen_v", "Tanda de penales, si hubo."),
    ("gl_ht, gv_ht", "Marcador al medio tiempo. `ht_fuente` dice de dónde sale."),
    ("estadio, ciudad", "Sede según ESPN (ESPN usa el nombre ACTUAL del inmueble aun en partidos viejos)."),
    ("asistencia", "Asistencia reportada; vacío si ESPN no la trae (ESPN manda 0); 0 sólo si fue a puerta cerrada."),
    ("arbitro", "Árbitro central, si viene."),
    ("tiros, tiros_puerta, corners, faltas, amarillas, rojas, posesion, fueras_lugar, atajadas, penales_tirados, "
     "penales_gol (_l / _v)", "Estadísticas del boxscore por lado. Vacías si `tiene_stats`=0. `posesion` en % "
                              "(sólo desde que ESPN la mide)."),
    ("ml_l, ml_e, ml_v", "Momios 1X2 en DECIMAL (local, empate, visitante), valor de cierre del proveedor."),
    ("total_linea, over, under", "Línea de goles totales y momios decimales de más/menos."),
    ("proveedor", "Casa de apuestas de la que salen los momios."),
    ("tiene_stats", "1 si el boxscore trae estadísticas reales (tiros y faltas > 0)."),
    ("tiene_eventos", "1 si los goles con minuto de goles.csv suman exactamente el marcador."),
    ("tiene_alineaciones", "1 si ambos equipos tienen 11 titulares en alineaciones.csv."),
    ("tiene_momios", "1 si hay momios 1X2 completos."),
    ("tiene_tarjetas", "(extra) 1 si las tarjetas con minuto coinciden (±1) con las amarillas del boxscore."),
    ("hora_local", "(extra) Hora de inicio en America/Mexico_City."),
    ("serie", "(extra) En liguilla, los dos equipos del cruce en orden alfabético."),
    ("local_id, visitante_id, estadio_id", "(extra) Ids de ESPN."),
    ("formacion_l, formacion_v", "(extra) Formación inicial (4-4-2...)."),
    ("pases, pases_precisos, centros, centros_precisos, tiros_bloqueados, entradas, intercepciones, despejes "
     "(_l / _v)", "(extra) Estadísticas avanzadas; sólo temporadas recientes."),
    ("ml_l_abre, ml_e_abre, ml_v_abre, over_abre, under_abre", "(extra) Momios de apertura en decimal."),
    ("ht_fuente", "(extra) `eventos` = contado de los goles con minuto; `parciales` = marcador por tiempos de ESPN; "
                  "`marcador` = el partido terminó 0-0."),
    ("temporada_espn, fase_espn, estado_espn", "(extra) Valores crudos de ESPN (season.year, season.slug, status)."),
    ("nota", "(extra) Avisos: fase corregida, resultado de escritorio, registro fantasma, etc."),
]

DICCIONARIO_OTRAS = """
**goles.csv** (un renglón por gol; no incluye la tanda de penales): `partido_id`, `minuto`, `anadido` (minutos de
compensación: `90'+4'` → minuto 90, añadido 4), `periodo` (1, 2; 3 y 4 = tiempos extra), `equipo` (el que recibe
el gol a favor), `jugador`, `tipo` (`gol`, `penal`, `autogol`), y extras `subtipo` (`cabeza`, `tiro_libre`,
`volea`), `jugador_id`, `asistencia`.

**tarjetas.csv**: `partido_id`, `minuto`, `periodo`, `equipo`, `jugador`, `tipo` (`amarilla`, `roja`,
`segunda_amarilla`), y extras `anadido`, `jugador_id`. `segunda_amarilla` sólo se distingue cuando ESPN trae el
texto de la jugada ("Second yellow card..."); en partidos viejos toda expulsión sale como `roja`.

**alineaciones.csv** (un renglón por jugador convocado): `partido_id`, `equipo`, `jugador_id`, `jugador`,
`titular` (1/0), `posicion` (abreviatura de ESPN: G, CD-L, LB, AM, F...; vacío para suplentes),
`minuto_entra`, `minuto_sale` (sólo por cambio; las expulsiones están en tarjetas.csv), `formacion`.

**calendario_pendiente.json**: partidos por jugar del torneo en curso (`id`, `fecha_utc`, `fecha_local`,
`hora_local`, `fase`, `pierna`, `estado`, `local`, `visitante`, `estadio`, `ciudad`, `momios` si ya hay).

**tabla_<torneo>.csv**: tabla general calculada desde partidos.csv (`PJ, G, E, P, GF, GC, DG, PTS`, y lo mismo
con sufijo `_L` de local y `_V` de visita) junto a las cifras del endpoint `standings` de ESPN (`espn_*`) y
`coincide_espn` (1 = cifras y posición iguales; `cifras` = cifras iguales pero ESPN ordena distinto un empate).
"""


def _pct(n, d):
    return f"{100.0 * n / d:.0f}%" if d else "-"


def _empareja(hist, mios, tolerancia=4):
    """Empareja filas de un histórico (fecha, local, visitante) con partidos.csv por equipos y fecha cercana."""
    indice = {}
    for f in mios:
        indice.setdefault((f["local"], f["visitante"]), []).append(f)
    usados, pares, sin_par = set(), [], []
    for h in hist:
        try:
            fh = dt.date.fromisoformat(h["fecha"])
        except ValueError:
            sin_par.append(h)
            continue
        mejor, invertido = None, False
        for inv, clave in ((False, (h["local"], h["visitante"])), (True, (h["visitante"], h["local"]))):
            for f in indice.get(clave, []):
                if f["id"] in usados:
                    continue
                d = abs((dt.date.fromisoformat(f["fecha_local"]) - fh).days)
                if d <= tolerancia and (mejor is None or d < mejor[0]):
                    mejor, invertido = (d, f), inv
            if mejor:
                break
        if mejor:
            usados.add(mejor[1]["id"])
            pares.append((h, mejor[1], mejor[0], invertido))
        else:
            sin_par.append(h)
    return pares, sin_par, usados


def conciliar(filas):
    """Compara partidos.csv con historico_ligamx.csv e historico_ht_ligamx.csv. Regresa dict con resultados."""
    r = {}
    veredictos = {}
    if os.path.exists(ARCH_VEREDICTOS):
        try:
            with open(ARCH_VEREDICTOS, encoding="utf-8") as fh:
                veredictos = json.load(fh)
        except (OSError, ValueError):
            veredictos = {}
    r["veredictos"] = veredictos
    jugados = [f for f in filas if f["estado"] == "jugado"]

    if os.path.exists(HIST_FT):
        hist = leer_csv(HIST_FT)
        fmin, fmax = min(h["fecha"] for h in hist), max(h["fecha"] for h in hist)
        en_rango = [f for f in jugados if fmin <= f["fecha_local"] <= fmax]
        pares, sin_par, usados = _empareja(hist, en_rango)
        dif_marcador, dif_fase, dif_fecha, invertidos, solo_90 = [], [], [], [], 0
        for h, f, dias, inv in pares:
            fin = (f["gl_et"] or f["gl"], f["gv_et"] or f["gv"])
            mio = (fin[1], fin[0]) if inv else fin
            if inv:
                invertidos.append((h, f))
            if (h["gl"], h["gv"]) != mio:
                dif_marcador.append((h, f))
            elif f["gl_et"] != "" and (f["gl"], f["gv"]) != fin:
                solo_90 += 1
            fase_h = h.get("fase", "")
            if (fase_h == "regular") != (f["fase"] == "regular"):
                dif_fase.append((h, f))
            if dias:
                dif_fecha.append((h, f, dias))
        solo_espn = [f for f in en_rango if f["id"] not in usados]
        r["ft"] = {"n_hist": len(hist), "rango": (fmin, fmax), "n_espn": len(en_rango), "pares": len(pares),
                   "misma_fecha": sum(1 for p in pares if p[2] == 0), "dif_fecha": dif_fecha,
                   "dif_marcador": dif_marcador, "dif_fase": dif_fase, "invertidos": invertidos,
                   "solo_hist": sin_par, "solo_espn": solo_espn, "finales_con_et": solo_90}
    if os.path.exists(HIST_HT):
        hist = leer_csv(HIST_HT)
        fmin, fmax = min(h["fecha"] for h in hist), max(h["fecha"] for h in hist)
        en_rango = [f for f in jugados if fmin <= f["fecha_local"] <= fmax]
        pares, sin_par, usados = _empareja(hist, en_rango)
        dif_ht, dif_ft, sin_ht = [], [], []
        for h, f, dias, inv in pares:
            if inv:
                continue
            if f["gl_ht"] == "":
                sin_ht.append((h, f))
            elif (h["h1"], h["a1"]) != (f["gl_ht"], f["gv_ht"]):
                dif_ht.append((h, f))
            fin = (f["gl_et"] or f["gl"], f["gv_et"] or f["gv"])
            if (h["hf"], h["af"]) != fin and (h["hf"], h["af"]) != (f["gl"], f["gv"]):
                dif_ft.append((h, f))
        r["ht"] = {"n_hist": len(hist), "rango": (fmin, fmax), "n_espn": len(en_rango), "pares": len(pares),
                   "dif_ht": dif_ht, "dif_ft": dif_ft, "sin_ht": sin_ht, "solo_hist": sin_par,
                   "solo_espn_n": sum(1 for f in en_rango if f["id"] not in usados)}
    return r


def escribir_cobertura(filas=None, tabla_info=None):
    filas = filas if filas is not None else leer_csv(ARCH_PARTIDOS)
    L = []
    hoy_local = ahora_utc().astimezone(TZ_MX).strftime("%Y-%m-%d")
    jugados = [f for f in filas if f["estado"] == "jugado"]
    L.append("# Cobertura de la base histórica de Liga MX (ESPN)\n")
    L.append(f"Generado automáticamente por `espn_descarga.py` el {hoy_local} (no editar a mano: se reescribe en "
             f"cada `tablas` / `actualizar`; los veredictos de la conciliación viven en "
             f"`conciliacion_veredictos.json`).\n")
    L.append(f"- Fuente: API pública de ESPN, liga `mex.1` (scoreboard por año + summary por partido).")
    L.append(f"- Partidos en `partidos.csv`: **{len(filas)}** ({len(jugados)} jugados) de "
             f"{min(f['fecha_local'] for f in filas)} a {max(f['fecha_local'] for f in filas)}; "
             f"{len({f['torneo'] for f in filas})} torneos.")
    L.append("- ESPN no tiene eventos de Liga MX anteriores al Invierno 2001 (probado 1996-2000: vacío).")
    con_ex = sum(1 for f in jugados if f["tiene_stats"] == "1" or f["tiene_eventos"] == "1"
                 or f["tiene_alineaciones"] == "1")
    L.append(f"- Partidos jugados con algún bloque de detalle (stats, eventos o alineaciones): {con_ex} "
             f"({_pct(con_ex, len(jugados))}).\n")

    # ---- cobertura por torneo
    L.append("## 1. Cobertura por torneo\n")
    L.append("Porcentajes sobre partidos **jugados**. `stats` = boxscore real; `eventos` = goles con minuto que suman "
             "el marcador; `tarjetas` = tarjetas con minuto que cuadran con el boxscore; `alin.` = 11 titulares "
             "por lado; `HT` = marcador de medio tiempo; `posesión`, `asist.` y `árbitro` = dato presente.\n")
    L.append("| Torneo | Partidos | Jugados | Regular | Liguilla | stats | eventos | tarjetas | alin. | momios | HT | "
             "posesión | asist. | árbitro |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    por_torneo = {}
    for f in filas:
        por_torneo.setdefault(f["torneo"], []).append(f)
    orden = sorted(por_torneo, key=clave_torneo)
    cob = {}
    for t in orden:
        todos = por_torneo[t]
        j = [f for f in todos if f["estado"] == "jugado"]
        n = len(j)
        c = {"stats": sum(f["tiene_stats"] == "1" for f in j), "eventos": sum(f["tiene_eventos"] == "1" for f in j),
             "tarjetas": sum(f["tiene_tarjetas"] == "1" for f in j),
             "alineaciones": sum(f["tiene_alineaciones"] == "1" for f in j),
             "momios": sum(f["tiene_momios"] == "1" for f in j), "ht": sum(f["gl_ht"] != "" for f in j),
             "posesion": sum(f["posesion_l"] != "" for f in j), "asistencia": sum(f["asistencia"] != "" for f in j),
             "arbitro": sum(f["arbitro"] != "" for f in j)}
        cob[t] = (n, c)
        L.append(f"| {t} | {len(todos)} | {n} | {sum(f['fase'] == 'regular' for f in j)} | "
                 f"{sum(f['fase'] != 'regular' for f in j)} | " +
                 " | ".join(_pct(c[k], n) for k in ("stats", "eventos", "tarjetas", "alineaciones", "momios", "ht",
                                                    "posesion", "asistencia", "arbitro")) + " |")
    L.append("")

    # ---- desde cuándo es confiable cada bloque
    L.append("## 2. Desde qué torneo es confiable cada bloque\n")
    L.append("Regla: primer torneo a partir del cual TODOS los torneos siguientes (con partidos jugados) cumplen el "
             "umbral.\n")
    L.append("| Bloque | ≥ 95% desde | ≥ 80% desde | Cobertura en ese tramo (≥95%) |")
    L.append("|---|---|---|---|")
    con_juego = [t for t in orden if cob[t][0] > 0]

    def desde(clave, umbral):
        inicio = None
        for t in reversed(con_juego):
            n, c = cob[t]
            if c[clave] / n >= umbral:
                inicio = t
            else:
                break
        return inicio

    for clave, nombre in (("stats", "Estadísticas (tiros, córners, faltas, tarjetas...)"),
                          ("posesion", "Posesión"), ("eventos", "Goles con minuto"),
                          ("ht", "Marcador de medio tiempo"), ("tarjetas", "Tarjetas con minuto"),
                          ("alineaciones", "Alineaciones (11 titulares)"), ("momios", "Momios 1X2"),
                          ("asistencia", "Asistencia"), ("arbitro", "Árbitro")):
        d95, d80 = desde(clave, 0.95), desde(clave, 0.80)
        tramo = ""
        if d95:
            ts = [t for t in con_juego if clave_torneo(t) >= clave_torneo(d95)]
            n = sum(cob[t][0] for t in ts)
            tramo = f"{sum(cob[t][1][clave] for t in ts)} de {n} ({_pct(sum(cob[t][1][clave] for t in ts), n)})"
        L.append(f"| {nombre} | {d95 or 'nunca'} | {d80 or 'nunca'} | {tramo} |")
    L.append("")

    # ---- notas de calidad
    n_et = sum(1 for f in filas if f["gl_et"] != "")
    n_pen = sum(1 for f in filas if f["pen_l"] != "")
    corregidas = [f for f in filas if "fase corregida" in f["nota"]]
    fantasmas = [f for f in filas if "registro sin resultado" in f["nota"]]
    escritorio = [f for f in filas if "escritorio" in f["nota"] or "abandonado" in f["nota"]
                  or "suspendido" in f["nota"]]
    ht_dif = [f for f in filas if "medio tiempo: eventos" in f["nota"]]
    L.append("## 3. Notas de calidad de los datos\n")
    L.append(f"- **Marcador de 90 minutos**: `gl`/`gv` nunca incluyen tiempos extra. Hay {n_et} partidos con tiempos "
             f"extra (`gl_et`/`gv_et`) y {n_pen} con tanda de penales (`pen_l`/`pen_v`). El campo `score` de ESPN SÍ "
             f"incluye los goles del tiempo extra; aquí se separan con el marcador por periodos y los goles con minuto.")
    L.append("- **Jugadas duplicadas**: ESPN ingirió dos veces algunos partidos (sobre todo 2016-2018): los goles y "
             "tarjetas salen repetidos con un minuto de diferencia. Se depuran (se conserva la versión reprocesada) y "
             "sólo se marca `tiene_eventos`=1 si los goles suman el marcador.")
    L.append("- **Estadísticas en ceros**: en partidos viejos ESPN manda 0 en lo que no midió. Se dejan VACÍAS "
             "(no cero) cuando el boxscore no tiene tiros y faltas; la posesión sólo cuando ambos lados suman 100.")
    L.append("- **Estadios**: ESPN usa el nombre actual del inmueble (p. ej. el Azteca aparece como Estadio Banorte "
             "en todos los años); `estadio_id` es estable.")
    L.append("- **Asistencia**: ESPN manda 0 cuando no la tiene; se deja vacío salvo partidos a puerta cerrada.")
    L.append("- **Momios**: valor de cierre del proveedor principal (se excluyen los momios en vivo). "
             "Ver la sección 2 para saber desde cuándo existen.")
    L.append("- **Equipos 2001-2003**: el nombre sigue al id de ESPN, que agrupa franquicias. En Invierno 2001 y "
             "Verano 2002 `Querétaro` (id 222) corresponde a La Piedad y `Chiapas` (id 224) a la franquicia que "
             "después fue Jaguares; `Colibríes` (id 217) es Celaya hasta el Apertura 2002. No se verificó partido "
             "por partido; no afecta de 2004 en adelante.")
    if escritorio:
        L.append("- **Resultados de escritorio / abandonados**: " + "; ".join(
            f"{f['fecha_local']} {f['local']} {f['gl']}-{f['gv']} {f['visitante']} (id {f['id']}: {f['nota']})"
            for f in escritorio) + ". `gl`/`gv` llevan lo que publica ESPN (en el abandonado de 2021, el resultado "
            "oficial de escritorio; en el suspendido de 2022, el de cancha); los goles de cancha están en goles.csv. "
            "Conviene excluir estos partidos al ajustar modelos de goles.")
    if corregidas:
        tor = sorted({f["torneo"] for f in corregidas}, key=clave_torneo)
        L.append(f"- **Fases corregidas** ({len(corregidas)} partidos en {', '.join(tor)}): ESPN etiquetó mal la fase "
                 f"(liguilla completa como 'reclassification', final como semifinal o cuartos como fase regular); se "
                 f"dedujo por la estructura de las series. El valor original queda en `fase_espn`.")
    if fantasmas:
        L.append(f"- **Registros fantasma** ({len(fantasmas)}): eventos que ESPN dejó como 'programado' con fecha "
                 f"pasada y sin resultado; quedan como `pospuesto` con nota: " +
                 ", ".join(f"{f['id']} ({f['fecha_local']} {f['local']}-{f['visitante']})" for f in fantasmas) + ".")
    if ht_dif:
        L.append(f"- **Medio tiempo**: en {len(ht_dif)} partidos el conteo de goles del primer tiempo difiere del "
                 f"marcador por periodos de ESPN; se usa el de los goles con minuto y se anota en `nota`.")
    L.append("")

    # ---- diccionario
    L.append("## 4. Diccionario de columnas\n")
    L.append("### partidos.csv (una fila por partido, incluidos los programados)\n")
    L.append("| Columna | Significado |")
    L.append("|---|---|")
    for col, desc in DICCIONARIO:
        L.append(f"| `{col}` | {desc} |")
    L.append("")
    L.append("### Otras tablas\n" + DICCIONARIO_OTRAS)

    # ---- conciliación
    L.append("## 5. Conciliación con los históricos previos del repositorio\n")
    c = conciliar(filas)
    ver = c.get("veredictos") or {}

    def clave_v(h):
        return f"{h['fecha']}|{h['local']}|{h['visitante']}"

    if "ft" in c:
        x = c["ft"]
        L.append(f"### 5.1 `historico_ligamx.csv` ({x['n_hist']} partidos, {x['rango'][0]} a {x['rango'][1]})\n")
        L.append(f"- Partidos jugados de ESPN en ese rango de fechas: {x['n_espn']}.")
        L.append(f"- Emparejados (mismos equipos y localía, fecha a ±4 días): **{x['pares']} de {x['n_hist']}**; "
                 f"{x['misma_fecha']} con la misma fecha local y {len(x['dif_fecha'])} con otra fecha.")
        ok = x["pares"] - len(x["dif_marcador"])
        L.append(f"- Marcador idéntico: **{ok} de {x['pares']}** (el histórico usa el marcador tras tiempos extra; se "
                 f"comparó contra `gl_et`/`gv_et` cuando existen: {x['finales_con_et']} finales coinciden sólo así).")
        L.append(f"- Discrepancias de marcador: {len(x['dif_marcador'])}; de fase regular/liguilla: "
                 f"{len(x['dif_fase'])}; con localía invertida: {len(x['invertidos'])}; sólo en el histórico: "
                 f"{len(x['solo_hist'])}; sólo en ESPN: {len(x['solo_espn'])}.\n")
        if x["dif_marcador"]:
            L.append("**Discrepancias de marcador**\n")
            L.append("| Fecha | Partido | Histórico | ESPN (90') | ESPN tras TE | Goles con minuto | id ESPN | Veredicto |")
            L.append("|---|---|---|---|---|---|---|---|")
            for h, f in x["dif_marcador"]:
                L.append(f"| {h['fecha']} | {h['local']} - {h['visitante']} | {h['gl']}-{h['gv']} | {f['gl']}-{f['gv']} | "
                         f"{(f['gl_et'] + '-' + f['gv_et']) if f['gl_et'] else ''} | "
                         f"{'cuadran con ESPN' if f['tiene_eventos'] == '1' else 'no cuadran'} | {f['id']} | "
                         f"{ver.get(clave_v(h), '')} |")
            L.append("")
        if x["dif_fecha"]:
            dias = {}
            for h, f, d in x["dif_fecha"]:
                signo = (dt.date.fromisoformat(f["fecha_local"]) - dt.date.fromisoformat(h["fecha"])).days
                dias[signo] = dias.get(signo, 0) + 1
            L.append("**Diferencias de fecha** (días ESPN − histórico: partidos): " +
                     ", ".join(f"{k:+d}: {v}" for k, v in sorted(dias.items())) + ".\n")
            L.append(ver.get("_fechas", "") + "\n")
            if len(x["dif_fecha"]) <= 60:
                L.append("| Histórico | ESPN local | ESPN UTC | Partido | id |")
                L.append("|---|---|---|---|---|")
                for h, f, d in x["dif_fecha"]:
                    L.append(f"| {h['fecha']} | {f['fecha_local']} | {f['fecha_utc']} | {h['local']} - {h['visitante']} | {f['id']} |")
                L.append("")
        if x["dif_fase"]:
            L.append("**Diferencias de fase** (histórico vs ESPN): " + "; ".join(
                f"{h['fecha']} {h['local']}-{h['visitante']} ({h['fase']} vs {f['fase']})" for h, f in x["dif_fase"][:40]) + ".\n")
        if x["invertidos"]:
            L.append("**Localía invertida**: " + "; ".join(
                f"{h['fecha']} {h['local']}-{h['visitante']} (ESPN: {f['local']} local, id {f['id']}) "
                f"{ver.get(clave_v(h), '')}" for h, f in x["invertidos"][:40]) + ".\n")
        if x["solo_hist"]:
            L.append("**Sólo en el histórico** (sin par en ESPN): " + "; ".join(
                f"{h['fecha']} {h['local']} {h['gl']}-{h['gv']} {h['visitante']} {ver.get(clave_v(h), '')}".strip()
                for h in x["solo_hist"][:60]) + ".\n")
        if x["solo_espn"]:
            L.append("**Sólo en ESPN** (jugados, dentro del rango, sin par en el histórico): " + "; ".join(
                f"{f['fecha_local']} {f['local']} {f['gl']}-{f['gv']} {f['visitante']} ({f['torneo']} {f['fase']}, id {f['id']})"
                for f in x["solo_espn"][:60]) + (" ..." if len(x["solo_espn"]) > 60 else "") + ".\n")
        if ver.get("_ft"):
            L.append(ver["_ft"] + "\n")
    else:
        L.append("No se encontró `historico_ligamx.csv`.\n")
    if "ht" in c:
        x = c["ht"]
        L.append(f"### 5.2 `historico_ht_ligamx.csv` ({x['n_hist']} partidos, {x['rango'][0]} a {x['rango'][1]})\n")
        con_ht = x["pares"] - len(x["sin_ht"])
        L.append(f"- Emparejados: **{x['pares']} de {x['n_hist']}** (ESPN tiene {x['n_espn']} jugados en el rango; "
                 f"{x['solo_espn_n']} no están en ese histórico).")
        L.append(f"- Medio tiempo idéntico: **{con_ht - len(x['dif_ht'])} de {con_ht}** con dato en ambas fuentes "
                 f"({len(x['sin_ht'])} sin medio tiempo en ESPN). Discrepancias de medio tiempo: {len(x['dif_ht'])}; "
                 f"de marcador final: {len(x['dif_ft'])}; sin par: {len(x['solo_hist'])}.\n")
        if x["dif_ht"]:
            L.append("**Discrepancias de medio tiempo**\n")
            L.append("| Fecha | Partido | Final | HT histórico | HT ESPN | fuente ESPN | id ESPN | Veredicto |")
            L.append("|---|---|---|---|---|---|---|---|")
            for h, f in x["dif_ht"]:
                L.append(f"| {h['fecha']} | {h['local']} - {h['visitante']} | {f['gl']}-{f['gv']} | {h['h1']}-{h['a1']} | "
                         f"{f['gl_ht']}-{f['gv_ht']} | {f['ht_fuente']} | {f['id']} | {ver.get(clave_v(h), '')} |")
            L.append("")
        if x["dif_ft"]:
            L.append("**Discrepancias de marcador final**: " + "; ".join(
                f"{h['fecha']} {h['local']}-{h['visitante']} (hist {h['hf']}-{h['af']}, ESPN {f['gl']}-{f['gv']}) "
                f"{ver.get(clave_v(h), '')}".strip() for h, f in x["dif_ft"][:40]) + ".\n")
        if x["solo_hist"]:
            L.append("**Sin par en ESPN**: " + "; ".join(
                f"{h['fecha']} {h['local']}-{h['visitante']}" for h in x["solo_hist"][:40]) + ".\n")
        if ver.get("_ht"):
            L.append(ver["_ht"] + "\n")
    else:
        L.append("No se encontró `historico_ht_ligamx.csv`.\n")

    # ---- verificaciones
    L.append("## 6. Verificaciones automáticas (`espn_descarga.py verificar`)\n")
    L.append("| Prueba | Resultado | Detalle |")
    L.append("|---|---|---|")
    for p in verificar(filas, tabla_info):
        L.append(f"| {p['prueba']} | {'OK' if p['ok'] else 'FALLA'} | {p['detalle'].replace('|', '/')} |")
    L.append("")
    L.append("## 7. Cómo se actualiza\n")
    L.append("```\n"
             "python3 ligamx/datos/espn_descarga.py actualizar   # después de cada partido (incremental, ~10 peticiones)\n"
             "python3 ligamx/datos/espn_descarga.py todo         # reconstrucción completa (miles de peticiones, ~35 min)\n"
             "python3 ligamx/datos/espn_descarga.py verificar    # pruebas de consistencia (código de salida 1 si falla)\n"
             "```\n")
    L.append("`actualizar` imprime en stdout un JSON con lo que cambió (partidos nuevos jugados, reprogramados, "
             "nuevos en calendario, correcciones) y funciona aunque `cache/` esté vacío (clon nuevo): conserva las "
             "filas de los CSV y sólo pide a ESPN lo nuevo.\n")
    escribir_texto(ARCH_COBERTURA, "\n".join(L))
    return c


# ----------------------------------------------------------------------------------------------------------
# Comandos
# ----------------------------------------------------------------------------------------------------------
def anio_actual():
    return ahora_utc().astimezone(TZ_MX).year


def derivados(con_red=True):
    """Pendientes, tabla del torneo en curso (vs standings de ESPN) y COBERTURA.md."""
    filas = leer_csv(ARCH_PARTIDOS)
    pend = escribir_pendientes(filas)
    standings = None
    if con_red:
        try:
            standings = descargar_standings()
        except Exception as e:
            log(f"standings no disponible ({e}); se usa el de caché si existe")
    if standings is None:
        standings = (leer_gz(ARCH_STANDINGS) or {}).get("datos")
    tabla_info = escribir_tabla(filas, standings)
    escribir_cobertura(filas, tabla_info)
    return filas, pend, tabla_info


def cmd_calendario(args):
    r = descargar_calendario(range(args.desde or ANIO_INICIAL, anio_actual() + 1))
    log(f"calendario listo: {sum(r.values())} eventos en {len(r)} años")
    return 0


def cmd_resumenes(args):
    eventos = cargar_calendario()
    if not eventos:
        log("no hay calendario en caché: corre primero `calendario`")
        return 1
    ids = ids_para_resumen(eventos, args.desde, args.hasta, args.forzar)
    log(f"resúmenes por bajar: {len(ids)}")
    c = descargar_resumenes(ids)
    log(f"resúmenes listos: {c}")
    return 0 if c["error"] == 0 else 2


def cmd_tablas(args):
    r = construir_tablas()
    filas, pend, tabla_info = derivados(con_red=not getattr(args, "sin_red", False))
    log(f"pendientes del {pend.get('torneo')}: {len(pend.get('partidos', []))}; tabla: "
        f"{os.path.basename(tabla_info.get('archivo', ''))} coincide con ESPN: {tabla_info.get('coincide_con_espn')}")
    if r["equipos_sin_nombre_canonico"]:
        log(f"AVISO: equipos sin nombre canónico: {r['equipos_sin_nombre_canonico']}")
    return 0


def cmd_todo(args):
    cmd_calendario(args)
    args.hasta, args.forzar = None, False
    cmd_resumenes(args)
    # los programados cercanos también se piden: traen momios antes del partido
    eventos = cargar_calendario([anio_actual()])
    descargar_resumenes(_ids_programados(eventos), "programados")
    return cmd_tablas(args)


def cmd_verificar(args):
    filas = leer_csv(ARCH_PARTIDOS)
    standings = (leer_gz(ARCH_STANDINGS) or {}).get("datos")
    tabla_info = escribir_tabla(filas, standings) if standings else None
    pruebas = verificar(filas, tabla_info)
    print(json.dumps(pruebas, ensure_ascii=False, indent=1))
    return 0 if all(p["ok"] for p in pruebas) else 1


def cmd_cobertura(args):
    derivados(con_red=False)
    return 0


def _ids_programados(eventos, dias=21):
    """Partidos aún no jugados de los próximos días (para capturar momios previos al partido)."""
    ahora = ahora_utc()
    ids = []
    for e in eventos.values():
        if es_jugado(e) or e.get("estado") in ESTADOS_CANCELADO:
            continue
        try:
            f = _fecha_dt(e.get("fecha"))
        except (TypeError, ValueError):
            continue
        if ahora - dt.timedelta(days=1) <= f <= ahora + dt.timedelta(days=dias):
            ids.append(e["id"])
    return ids


def cmd_actualizar(args):
    """Incremental e idempotente. Imprime un JSON con lo que cambió."""
    t0 = time.monotonic()
    ahora = ahora_utc()
    anio = anio_actual()
    antes = {f["id"]: f for f in leer_csv(ARCH_PARTIDOS)}
    anios = [anio - 1, anio] if ahora.astimezone(TZ_MX).month == 1 else [anio]
    descargar_calendario(anios, verboso=False)
    eventos = cargar_calendario(anios)

    por_bajar, motivos = [], {}
    for eid, e in eventos.items():
        viejo = antes.get(eid)
        try:
            fecha = _fecha_dt(e.get("fecha"))
        except (TypeError, ValueError):
            continue
        dias = (ahora - fecha).total_seconds() / 86400.0
        if es_jugado(e):
            if viejo is None or viejo.get("estado") != "jugado" or not _fila_cuadra(viejo, e):
                motivos[eid] = "nuevo_jugado"
            elif dias <= 21 and "0" in (viejo.get("tiene_stats"), viejo.get("tiene_eventos"),
                                        viejo.get("tiene_alineaciones")):
                motivos[eid] = "le_faltaba_detalle"
            elif dias <= 3:
                motivos[eid] = "recien_terminado"      # ESPN corrige estadísticas en los días siguientes
            elif not os.path.exists(ruta_res(eid)) and viejo.get("tiene_stats") != "1" and dias <= 21:
                motivos[eid] = "sin_extracto"
        elif e.get("estado") not in ESTADOS_CANCELADO and e.get("estado_fase") != "in" and -1 <= -dias <= 21:
            motivos[eid] = "programado_cercano"        # momios previos al partido
    por_bajar = list(motivos)
    cuenta = descargar_resumenes(por_bajar, "actualizar") if por_bajar else {"ok": 0, "sin_resumen": 0, "error": 0}

    r = construir_tablas(ids_rehacer=set(por_bajar), verboso=False)
    filas, pend, tabla_info = derivados(con_red=True)
    despues = {f["id"]: f for f in filas}

    def corto(f):
        return {"id": f["id"], "fecha_local": f["fecha_local"], "torneo": f["torneo"], "fase": f["fase"],
                "local": f["local"], "visitante": f["visitante"]}

    nuevos_jugados, reprogramados, nuevos_calendario, corregidos, momios_nuevos = [], [], [], [], []
    for eid, f in despues.items():
        v = antes.get(eid)
        if f["estado"] == "jugado" and (v is None or v.get("estado") != "jugado"):
            nuevos_jugados.append(dict(corto(f), gl=int(f["gl"]) if f["gl"] != "" else None,
                                       gv=int(f["gv"]) if f["gv"] != "" else None,
                                       tiene_stats=f["tiene_stats"] == "1", tiene_eventos=f["tiene_eventos"] == "1"))
        elif v is None:
            nuevos_calendario.append(dict(corto(f), estado=f["estado"], fecha_utc=f["fecha_utc"]))
        elif f["estado"] != "jugado" and (v.get("fecha_utc") != f["fecha_utc"] or v.get("estado") != f["estado"]):
            reprogramados.append(dict(corto(f), fecha_utc_anterior=v.get("fecha_utc"), fecha_utc_nueva=f["fecha_utc"],
                                      estado_anterior=v.get("estado"), estado_nuevo=f["estado"]))
        elif f["estado"] == "jugado":
            cambios = [c for c in COLS_PARTIDOS if v.get(c, "") != f.get(c, "")]
            if cambios:
                corregidos.append(dict(corto(f), columnas=cambios))
        elif v.get("tiene_momios") != f["tiene_momios"] or any(v.get(c, "") != f.get(c, "") for c in ("ml_l", "ml_e", "ml_v")):
            momios_nuevos.append(dict(corto(f), ml_l=f["ml_l"], ml_e=f["ml_e"], ml_v=f["ml_v"]))
    pendientes = pend.get("partidos", [])
    salida = {
        "corrida_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "torneo_en_curso": pend.get("torneo"),
        "partidos_nuevos_jugados": nuevos_jugados,
        "partidos_reprogramados": reprogramados,
        "partidos_nuevos_en_calendario": nuevos_calendario,
        "partidos_corregidos": corregidos,
        "momios_actualizados": momios_nuevos,
        "eventos_eliminados_por_espn": r["eliminados"],
        "equipos_sin_nombre_canonico": r["equipos_sin_nombre_canonico"],
        "resumenes_descargados": cuenta["ok"], "resumenes_con_error": cuenta["error"],
        "motivos_descarga": {m: sum(1 for x in motivos.values() if x == m) for m in sorted(set(motivos.values()))},
        "peticiones": CONTADOR["peticiones"],
        "partidos_en_tabla": len(filas),
        "pendientes": len(pendientes),
        "proximo_partido": pendientes[0] if pendientes else None,
        "tabla": {k: tabla_info.get(k) for k in ("torneo", "archivo", "comparada_con_espn", "coincide_con_espn",
                                                 "diferencias", "lider")},
        "hubo_cambios": bool(nuevos_jugados or reprogramados or nuevos_calendario or corregidos or r["eliminados"]),
        "segundos": round(time.monotonic() - t0, 1),
    }
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 0 if cuenta["error"] == 0 else 2


@contextlib.contextmanager
def candado(espera=300):
    """Evita que dos corridas escriban las tablas al mismo tiempo (p. ej. dos tareas programadas encimadas)."""
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "tablas.lock"), "w") as fh:
        limite = time.monotonic() + espera
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > limite:
                    raise SystemExit("otra corrida de espn_descarga.py tiene el candado de las tablas")
                time.sleep(2)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def main(argv=None):
    p = argparse.ArgumentParser(description="Base histórica de Liga MX desde la API pública de ESPN")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("calendario", help="baja el scoreboard de cada año")
    s.add_argument("--desde", type=int, default=None, help="primer año (por omisión 2001)")
    s = sub.add_parser("resumenes", help="baja el resumen de cada partido jugado (reanudable)")
    s.add_argument("--desde", type=int, default=None)
    s.add_argument("--hasta", type=int, default=None)
    s.add_argument("--forzar", action="store_true", help="vuelve a bajar aunque ya esté en caché")
    s = sub.add_parser("tablas", help="regenera CSV, pendientes, tabla y COBERTURA.md desde el caché")
    s.add_argument("--sin-red", dest="sin_red", action="store_true", help="no pide standings a ESPN")
    s = sub.add_parser("todo", help="calendario + resumenes + tablas")
    s.add_argument("--desde", type=int, default=None)
    sub.add_parser("actualizar", help="incremental: para correr después de cada partido; imprime JSON")
    sub.add_parser("verificar", help="pruebas de consistencia; código de salida 1 si alguna falla")
    sub.add_parser("cobertura", help="reescribe COBERTURA.md, pendientes y tabla sin usar la red")
    args = p.parse_args(argv)
    cmds = {"calendario": cmd_calendario, "resumenes": cmd_resumenes, "tablas": cmd_tablas, "todo": cmd_todo,
            "actualizar": cmd_actualizar, "verificar": cmd_verificar, "cobertura": cmd_cobertura}
    if args.cmd in ("tablas", "todo", "actualizar", "cobertura"):
        with candado():
            return cmds[args.cmd](args) or 0
    return cmds[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
