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
import csv
import datetime as dt
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


def descargar_calendario(anios, verboso=True):
    """Baja scoreboard?dates=AAAA&limit=1000 de cada año y lo guarda recortado y comprimido."""
    resumen = {}
    for anio in anios:
        url = f"{BASE}/scoreboard?dates={anio}&limit=1000"
        d = pedir_json(url)
        eventos = [recortar_evento(e) for e in d.get("events") or []]
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
        if e.get("estado") not in ESTADOS_JUGADO:
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
# Línea de comandos (las tablas y `actualizar` se definen más abajo)
# ----------------------------------------------------------------------------------------------------------
def cmd_calendario(args):
    anio_fin = ahora_utc().astimezone(TZ_MX).year
    r = descargar_calendario(range(args.desde or ANIO_INICIAL, anio_fin + 1))
    log(f"calendario listo: {sum(r.values())} eventos en {len(r)} años")


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


def main(argv=None):
    p = argparse.ArgumentParser(description="Base histórica de Liga MX desde ESPN")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("calendario", help="baja el scoreboard de cada año")
    s.add_argument("--desde", type=int, default=None)
    s = sub.add_parser("resumenes", help="baja el resumen de cada partido jugado (reanudable)")
    s.add_argument("--desde", type=int, default=None)
    s.add_argument("--hasta", type=int, default=None)
    s.add_argument("--forzar", action="store_true")
    args = p.parse_args(argv)
    return {"calendario": cmd_calendario, "resumenes": cmd_resumenes}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
