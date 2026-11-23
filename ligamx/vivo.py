#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cerebro Liga MX · motor EN VIVO.

    python3 vivo.py una-vez                       # consulta ESPN y escribe salidas/vivo.json
    python3 vivo.py observar [--hasta AAAA-MM-DDTHH:MM]   # bucle del día de partido (candado: sólo uno a la vez)
    python3 vivo.py esperar --desde N [--max-seg 6600]    # sale en cuanto hay un evento con número > N
    python3 vivo.py repetir <id> [--velocidad 60] [--salida salidas/vivo_prueba.json]   # reproduce un partido ya jugado
    python3 vivo.py plan [--horas 48]             # próximos inicios (UTC y hora de México)
    python3 vivo.py estado                        # ¿hay un `observar` corriendo? último evento

El documento que escribe (contrato en salidas/CONTRATO.md y ejemplo en salidas/vivo_ejemplo.json) trae los
partidos de HOY con su marcador, minuto y eventos, el pronóstico previo sellado, el pronóstico al momento
(produccion/en_juego.py), la tabla al momento, la proyección de clasificación y campeón recalculada con los
marcadores del momento (produccion/simulador.py con `en_juego`) y, en liguilla, cada serie con su global, su
probabilidad de avanzar y cómo va (quién avanzaría si terminara así, qué le falta a cada uno y quién avanzó, por
el reglamento y no por el `winner` de ESPN). La sesión lo copia a la base de datos del Artifact ("vivo/actual") cada vez que
`esperar` avisa de un evento. Cómo se opera un día de partido: produccion/VIVO.md.

Sólo biblioteca estándar más los módulos del proyecto (que usan numpy y pandas y se cargan cuando hacen falta).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import gzip
import json
import math
import os
import pickle
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

SALIDAS = RAIZ / "salidas"
RUTA_VIVO = SALIDAS / "vivo.json"
RUTA_EVENTOS = SALIDAS / "vivo_eventos.jsonl"
RUTA_CANDADO = SALIDAS / "vivo_observar.lock"
RUTA_ACTUAL = SALIDAS / "actual.json"
RUTA_SELLOS = SALIDAS / "sellos.jsonl"
RUTA_BASE = RAIZ / "modelo" / "cache" / "vivo_base.pkl"       # pronosticador congelado + simulación base (no va al repo)

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")                       # de navegador: con la palabra "bot" ESPN responde 403
ZONA = ZoneInfo("America/Mexico_City")
ZONA_ESPN = ZoneInfo("America/New_York")                      # el parámetro dates= de ESPN parte los días en hora del Este
UTC = dt.timezone.utc

VERSION = 1
PESO_MAXIMO = 40 * 1024
CORTE_DIA_H = 4                  # el «día de partido» acaba a las 04:00 de México (un partido nocturno no cambia de día)
N_SIM = 100_000                  # simulaciones de la proyección al momento (se recalcula en cada consulta: ~4 s; con
                                 # 1,000,000, como el pronóstico previo, cada gol llegaría ~40 s tarde)
N_MUESTRAS = 10_000              # muestras de parámetros entre las que se reparten
SEG_ACTIVO = 20                  # cada cuánto se consulta con partido en juego o a menos de 15 min de uno
SEG_REPOSO = 120
MIN_ANTES = 15
MIN_TRAS_FINAL = 10              # `observar` termina cuando todos llevan 10 minutos finalizados
MIN_REFRESCO = 25                # evento «refresco» (latido) si hay partido en juego y nada que avisar en ese rato
MIN_VENCE = 12                   # margen sobre el refresco: pasado `vence_utc` la página deja de decir «en vivo»
CONFIRMAR_MENOS = 6              # consultas seguidas para creerle a ESPN que un partido de hoy ya no está en la lista
CONFIRMAR_MENOS_ACTIVO = 45      # lo mismo si el que falta estaba en juego (unos 15 minutos)
SEG_LATIDO_VIEJO = 420           # `esperar`: con el candado tomado y el latido más viejo que esto, `observar` está colgado
SEG_AGRUPAR = 40                 # `esperar`: un evento que no es gol ni roja espera esto por si llega otro (un solo aviso)
TIPOS_URGENTES = ("gol", "gol_anulado", "roja")
RUIDO_DELTA = 0.003              # por debajo de esto un cambio de la proyección puede ser ruido de simulación
                                 # (medido el 11-nov-2026: desviación del cambio entre semillas 0.0012 con 100,000; era 0.004 con 6,000)
ESTADOS_ACTIVOS = ("en_juego", "descanso")
NOMBRE_FASE = {"cuartos": "Cuartos de final", "semifinal": "Semifinal", "final": "Final", "repechaje": "Repechaje"}
TIPOS_GOL = ("gol", "penal", "autogol")
ALIAS = {"Tigres UANL": "Tigres", "Pumas UNAM": "Pumas", "Guadalajara": "Chivas", "Chivas Guadalajara": "Chivas",
         "FC Juarez": "Juárez", "FC Juárez": "Juárez", "Atlético de San Luis": "Atlético San Luis", "Santos Laguna": "Santos",
         "Club Tijuana": "Tijuana", "Club América": "América", "Club León": "León", "CF Monterrey": "Monterrey",
         "CF Pachuca": "Pachuca", "Querétaro FC": "Querétaro", "Deportivo Toluca": "Toluca"}


class ErrorRed(Exception):
    """ESPN no respondió (o respondió algo que no es el marcador) tras los reintentos."""


# ==================================================================================================
# Utilidades
# ==================================================================================================
def log(*a) -> None:
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def ahora_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def iso(t: dt.datetime | None) -> str | None:
    return None if t is None else t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def de_iso(s) -> dt.datetime | None:
    """'2026-11-14T23:00Z', '...:00Z' o con desfase -> datetime en UTC (None si no se puede)."""
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(\+00:00)?", s):
        s = s[:16] + ":00+00:00"
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return (t.replace(tzinfo=ZONA) if t.tzinfo is None else t).astimezone(UTC)


def dia_de_juego(t: dt.datetime) -> dt.date:
    """Fecha de México del «día de partido» de un instante (el día cambia a las 04:00, no a medianoche)."""
    return (t.astimezone(ZONA) - dt.timedelta(hours=CORTE_DIA_H)).date()


def escribir_json(doc: dict, ruta: Path) -> int:
    """Escritura atómica y compacta (quien lee nunca ve un archivo a medias). Devuelve los bytes."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos_ = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        f.write(datos_)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)
    return len(datos_)


def leer_json(ruta: Path):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ent(v) -> int | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (f != f or f < 0) else int(round(f))


def _r4(x):
    return None if x is None else round(float(x), 4)


# ==================================================================================================
# ESPN
# ==================================================================================================
def pedir_json(url: str, intentos: int = 3, limite: float = 15.0) -> dict:
    """GET con gzip y reintentos cortos. Lanza ErrorRed si no hay respuesta útil (nunca otra cosa)."""
    ultimo = "?"
    for k in range(intentos):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json,text/plain,*/*", "Accept-Encoding": "gzip",
                "Accept-Language": "es-MX,es;q=0.9,en;q=0.8", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=limite) as r:
                crudo = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip" or crudo[:2] == b"\x1f\x8b":
                    crudo = gzip.decompress(crudo)
            d = json.loads(crudo.decode("utf-8"))
            if isinstance(d, dict):
                return d
            ultimo = "respuesta que no es un objeto JSON"
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            if e.code in (401, 403, 404, 407):
                break
        except Exception as e:                                   # red, tiempo agotado, gzip o JSON rotos
            ultimo = f"{type(e).__name__}: {e}"
        if k + 1 < intentos:
            time.sleep(1.5 * (k + 1))
    raise ErrorRed(f"{ultimo} en {url}")


_EQUIPOS: dict | None = None
_FASE_SLUG = None


def _tablas_espn() -> dict:
    """Nombre canónico por id de equipo: el mismo diccionario que usa datos/espn_descarga.py."""
    global _EQUIPOS, _FASE_SLUG
    if _EQUIPOS is None:
        try:
            import importlib.util
            esp = importlib.util.spec_from_file_location("espn_descarga_vivo", RAIZ / "datos" / "espn_descarga.py")
            mod = importlib.util.module_from_spec(esp)
            esp.loader.exec_module(mod)
            _EQUIPOS, _FASE_SLUG = dict(mod.EQUIPOS), mod.fase_de_slug
        except Exception as e:                                   # sin el módulo se usa el nombre de ESPN con alias
            log(f"aviso: no se pudo leer datos/espn_descarga.py ({e}); se usan los nombres de ESPN")
            _EQUIPOS = {}
    return _EQUIPOS


def nombre_equipo(tid: str, nombre_espn: str | None) -> str:
    eq = _tablas_espn()
    if tid in eq:
        return eq[tid]
    return ALIAS.get(nombre_espn or "", nombre_espn or f"equipo_{tid}")


def _minuto(reloj: str | None, segundos) -> tuple[int | None, int | None]:
    """Reloj de ESPN -> (minuto, añadido): "90'+4'" -> (90, 4); "57'" -> (57, None); si no, de los segundos."""
    m = re.match(r"\s*(\d+)'?(?:\s*\+\s*(\d+))?", reloj or "")
    if m and int(m.group(1)) > 0:
        return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
    try:
        s = float(segundos)
    except (TypeError, ValueError):
        return None, None
    return (max(1, math.ceil(s / 60.0)), None) if s > 0 else (None, None)


def normalizar_evento(e: dict) -> dict | None:
    """
    Evento del scoreboard de ESPN -> forma interna «cruda»: id, inicio, equipos con nombre canónico,
    estado (programado | en_juego | descanso | final | pospuesto), periodo, minuto, añadido, segundos
    de reloj, marcador y la lista de jugadas (goles y tarjetas) en orden. None si no se puede leer.
    """
    try:
        comp = (e.get("competitions") or [{}])[0]
        st = e.get("status") or comp.get("status") or {}
        tipo = st.get("type") or {}
        lados = {}
        for c in comp.get("competitors") or []:
            t = c.get("team") or {}
            tid = str(t.get("id") or c.get("id") or "")
            lados[c.get("homeAway")] = {"id": tid, "nombre": nombre_equipo(tid, t.get("displayName")),
                                        "goles": _ent(c.get("score")), "tanda": _ent(c.get("shootoutScore")),
                                        "global": _ent(c.get("aggregateScore")),     # vuelta de liguilla: global de la serie
                                        "gana": c.get("winner"), "avanza": c.get("advance")}
        if "home" not in lados or "away" not in lados:
            return None
        inicio = de_iso(e.get("date") or comp.get("date"))
        if inicio is None:
            return None
        nombre, fase_espn = str(tipo.get("name") or ""), str(tipo.get("state") or "")
        periodo = _ent(st.get("period")) or 0
        minuto, anadido = _minuto(st.get("displayClock"), st.get("clock"))
        if nombre in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED"):
            estado = "pospuesto"
        elif fase_espn == "pre":
            estado = "programado"
        elif fase_espn == "post":
            estado = "pospuesto" if nombre in ("STATUS_SUSPENDED", "STATUS_DELAYED") else "final"
        elif fase_espn == "in":
            pausa = ("HALFTIME" in nombre or nombre in ("STATUS_END_OF_REGULATION", "STATUS_END_OF_EXTRATIME",
                                                        "STATUS_END_PERIOD", "STATUS_DELAYED", "STATUS_SUSPENDED", "STATUS_RAIN_DELAY"))
            estado = "descanso" if pausa else "en_juego"
        else:
            estado = "programado"
        if fase_espn == "in":                                      # por si ESPN no mueve `period` en tiempos extra o penales
            if "SHOOTOUT" in nombre:
                periodo = 5
            elif (nombre == "STATUS_END_OF_EXTRATIME" or ("SECOND_HALF" in nombre and ("EXTRA" in nombre or "OVERTIME" in nombre))) \
                    and periodo < 4:
                periodo = 4                                        # segundo tiempo extra o la pausa antes de los penales
            elif ("OVERTIME" in nombre or "EXTRA" in nombre or nombre == "STATUS_HALFTIME_ET") and periodo < 3:
                periodo = 3
        elif fase_espn == "post":                                  # final tras tiempos extra o penales: que el periodo lo diga
            if nombre == "STATUS_FINAL_PEN" or "SHOOTOUT" in nombre:
                periodo = 5
            elif nombre in ("STATUS_FINAL_AET", "STATUS_FINAL_ET") and periodo < 4:
                periodo = 4
        # medio tiempo: lo dice el nombre del estado o, si ESPN usa otro nombre, una pausa justo al minuto 45
        medio_tiempo = estado == "descanso" and periodo <= 2 and (
            "HALFTIME" in nombre or (minuto is not None and 44 <= minuto <= 46
                                     and nombre not in ("STATUS_DELAYED", "STATUS_SUSPENDED", "STATUS_RAIN_DELAY")))
        jug = []
        for x in comp.get("details") or []:
            reloj = x.get("clock") or {}
            m, a = _minuto(reloj.get("displayValue"), reloj.get("value"))
            quien = (x.get("athletesInvolved") or x.get("participants") or [{}])[0] or {}
            quien = quien.get("athlete") or quien
            tid = str((x.get("team") or {}).get("id") or "")
            lado = 0 if tid == lados["home"]["id"] else 1 if tid == lados["away"]["id"] else None
            if lado is None or bool(x.get("shootout")):
                continue
            clase = ("gol" if x.get("scoringPlay") else "roja" if x.get("redCard") else "amarilla" if x.get("yellowCard") else None)
            if clase is None:
                continue
            try:
                seg = float(reloj.get("value"))
            except (TypeError, ValueError):
                seg = float((m or 0) * 60)
            jug.append({"clase": clase, "tipo": ("penal" if x.get("penaltyKick") else "autogol" if x.get("ownGoal") else "gol")
                        if clase == "gol" else clase, "lado": lado, "min": m, "anadido": a, "seg": seg,
                        "jugador": quien.get("displayName") or quien.get("fullName") or "", "jid": str(quien.get("id") or "")})
        jug.sort(key=lambda d: d["seg"])
        gl, gv = lados["home"]["goles"], lados["away"]["goles"]
        if estado != "programado" and gl is not None and gv is not None:
            # ESPN no siempre dice a quién le cuenta el autogol: se voltea si así cuadra con el marcador
            cuenta = [sum(1 for d in jug if d["clase"] == "gol" and d["lado"] == k) for k in (0, 1)]
            if cuenta != [gl, gv]:
                volteo = [dict(d, lado=1 - d["lado"]) if d["tipo"] == "autogol" else d for d in jug]
                if [sum(1 for d in volteo if d["clase"] == "gol" and d["lado"] == k) for k in (0, 1)] == [gl, gv]:
                    jug = volteo
        try:
            seg_reloj = float(st.get("clock"))
        except (TypeError, ValueError):
            seg_reloj = None
        gana = "local" if lados["home"]["gana"] else "visitante" if lados["away"]["gana"] else None
        return {"id": int(e["id"]), "inicio": inicio, "local": lados["home"]["nombre"], "visitante": lados["away"]["nombre"],
                "estado": estado, "estado_espn": nombre, "periodo": periodo, "minuto": minuto, "anadido": anadido,
                "segundos": seg_reloj, "gl": gl, "gv": gv, "tanda_l": lados["home"]["tanda"], "tanda_v": lados["away"]["tanda"],
                "global_l": lados["home"]["global"], "global_v": lados["away"]["global"],
                "gana": gana, "pierna": _ent((comp.get("leg") or {}).get("value")), "medio_tiempo": medio_tiempo,
                "slug": (e.get("season") or {}).get("slug"), "jugadas": jug}
    except Exception as ex:                                      # un evento raro no tumba el ciclo
        log(f"aviso: evento de ESPN ilegible ({type(ex).__name__}: {ex})")
        return None


def leer_dia(dia: dt.date, pedir=None) -> list[dict]:
    """Partidos que ESPN lista en dates=AAAAMMDD (día en hora del Este), ya normalizados."""
    d = (pedir or pedir_json)(f"{ESPN}/scoreboard?dates={dia:%Y%m%d}")
    if not isinstance(d, dict) or "events" not in d:
        raise ErrorRed(f"respuesta sin 'events' para {dia}")
    return [c for c in (normalizar_evento(e) for e in d.get("events") or []) if c]


def leer_hoy(ahora: dt.datetime, pedir=None) -> tuple[list[dict], list[str]]:
    """
    Partidos del día de partido de `ahora`. ESPN parte los días en hora del Este, así que un partido
    nocturno puede caer en el día siguiente: se consultan el día y el siguiente y se filtra por la fecha
    de México. Si falla la consulta del día principal lanza ErrorRed; si falla la del siguiente, se avisa.
    """
    hoy = dia_de_juego(ahora)
    avisos, vistos = [], {}
    for k, d in enumerate((hoy, hoy + dt.timedelta(days=1))):
        try:
            for c in leer_dia(d, pedir):
                vistos[c["id"]] = c
        except ErrorRed as e:
            if k == 0:
                raise
            avisos.append(f"ESPN no respondió para {d:%Y-%m-%d}: {e}")
    crudas = [c for c in vistos.values() if dia_de_juego(c["inicio"]) == hoy]
    crudas.sort(key=lambda c: (c["inicio"], c["id"]))
    return crudas, avisos


# ==================================================================================================
# Contexto: lo que se sabía antes del partido
# ==================================================================================================
def _sellos_oficiales(ruta: Path = RUTA_SELLOS) -> dict[int, dict]:
    """Último sello de cada partido con sellado_utc anterior a su inicio (el pronóstico previo oficial)."""
    of: dict[int, dict] = {}
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    s = json.loads(linea)
                    t_s, t_p = de_iso(s.get("sellado_utc")), de_iso(s.get("fecha_utc"))
                    if t_s is None or t_p is None or t_s >= t_p:
                        continue
                    previo = of.get(int(s["id"]))
                    if previo is None or t_s >= de_iso(previo["sellado_utc"]):
                        of[int(s["id"])] = s
                except (ValueError, KeyError, TypeError):
                    continue
    except OSError:
        pass
    return of


def _previo(p_l, p_e, p_v, lam_l, lam_v, rho, marcador, origen) -> dict:
    return {"p_local": float(p_l), "p_empate": float(p_e), "p_visitante": float(p_v),
            "marcador": {"gl": int(marcador["gl"]), "gv": int(marcador["gv"])} if marcador else None,
            "lam_l": float(lam_l), "lam_v": float(lam_v), "rho": float(rho or 0.0), "origen": origen}


def contexto_de_actual(actual: dict | None, sellos: dict[int, dict] | None = None) -> dict:
    """
    Contexto a partir de salidas/actual.json (y de los sellos): etiqueta, fase y pronóstico previo de
    cada partido, tabla, probabilidades de clasificar y de campeón, series reales de la liguilla y
    los próximos partidos. Sin actual.json devuelve un contexto vacío (el documento sale sin previos).
    """
    ctx = {"torneo": None, "regular_completa": False, "tabla": [], "p_clasifica": {}, "p_campeon": {},
           "partidos": {}, "series": [], "futuros": [], "origen": "actual.json", "corte_utc": None, "n_sim": None,
           "por_equipos": {}}                                      # piernas de liguilla sin id: (local, visitante) -> info
    if not actual:
        ctx["origen"] = "sin actual.json"
        return ctx
    ctx["torneo"] = (actual.get("meta") or {}).get("torneo")
    ctx["corte_utc"] = (actual.get("meta") or {}).get("corte_utc")
    pr = actual.get("proyeccion") or {}
    ctx["regular_completa"] = bool(pr.get("regular_completa"))
    ctx["n_sim"] = pr.get("n_sim")
    ctx["tabla"] = [{k: f.get(k) for k in ("pos", "equipo", "PJ", "PTS", "DG", "GF")} for f in actual.get("tabla") or []]
    ctx["p_clasifica"] = {d["equipo"]: float(d["p_clasifica"]) for d in pr.get("tabla_final") or []}
    ctx["p_campeon"] = {d["equipo"]: float(d["prob"]) for d in pr.get("campeon") or []}
    for p in actual.get("pendientes") or []:
        ctx["partidos"][int(p["id"])] = {
            "fase": p.get("fase"), "etiqueta": p.get("etiqueta"), "pierna": p.get("pierna"),
            "previo": _previo(p["p_local"], p["p_empate"], p["p_visitante"], p["lam_l"], p["lam_v"], p.get("rho"),
                              p.get("marcador"), "actual.json")}
        ctx["futuros"].append({"id": int(p["id"]), "inicio_utc": iso(de_iso(p.get("fecha_utc"))), "local": p["local"],
                               "visitante": p["visitante"]})
    for u in actual.get("ultimos_resultados") or []:
        ctx["partidos"].setdefault(int(u["id"]), {"fase": u.get("fase"), "etiqueta": u.get("etiqueta"), "pierna": None, "previo": None})
    rho_modelo = next((float(p["rho"]) for p in actual.get("pendientes") or [] if p.get("rho") is not None), None)
    if rho_modelo is None and sellos:                             # la misma rho del modelo que sella (el último sello)
        ult = max(sellos.values(), key=lambda s: str(s.get("sellado_utc") or ""))
        rho_modelo = float(ult.get("rho") or 0.0)
    tor = (actual.get("liguilla") or {}).get("torneo") or {}
    for ronda in tor.get("rondas") or []:
        for s in ronda.get("series") or []:
            # una serie entra si ya está en el calendario (`real`) o si sus dos equipos ya son seguros (`definida`):
            # así, si ESPN lista el partido antes de que corra pipeline.py auto, la pierna se reconoce por sus equipos
            if not (s.get("real") or s.get("definida")):
                continue
            ctx["series"].append(s)
            for pi in s.get("piernas") or []:
                etiqueta = f"{NOMBRE_FASE.get(s.get('fase'), s.get('fase'))}, {'ida' if pi.get('pierna') == 1 else 'vuelta'}"
                if pi.get("id") is not None:
                    d = ctx["partidos"].setdefault(int(pi["id"]), {"previo": None})
                else:
                    d = ctx["por_equipos"].setdefault((pi.get("local"), pi.get("visitante")), {"previo": None})
                d.setdefault("fase", s.get("fase"))
                d.setdefault("etiqueta", etiqueta)
                d["pierna"] = pi.get("pierna")
                if d.get("previo") is None and not pi.get("jugado") and pi.get("lam_l") is not None and pi.get("p_local") is not None:
                    # sin sello ni «pendientes»: el pronóstico de la pierna que ya publica la página (liguilla.torneo)
                    d["previo"] = _previo(pi["p_local"], pi["p_empate"], pi["p_visitante"], pi["lam_l"], pi["lam_v"],
                                          pi["rho"] if pi.get("rho") is not None else rho_modelo, pi.get("marcador"),
                                          "liguilla.torneo")
                if (pi.get("id") is not None and not pi.get("jugado") and pi.get("fecha_utc")
                        and all(f["id"] != int(pi["id"]) for f in ctx["futuros"])):
                    ctx["futuros"].append({"id": int(pi["id"]), "inicio_utc": iso(de_iso(pi["fecha_utc"])),
                                           "local": pi["local"], "visitante": pi["visitante"]})
    for pid, s in (sellos or {}).items():                         # el sello manda sobre lo que diga actual.json
        d = ctx["partidos"].setdefault(int(pid), {"fase": s.get("fase"), "etiqueta": None, "pierna": s.get("pierna")})
        try:
            d["previo"] = _previo(s["p_l"], s["p_e"], s["p_v"], s["lam_l"], s["lam_v"], s.get("rho"), s.get("marcador"), "sello")
            d["previo"]["sellado_utc"] = s.get("sellado_utc")
        except (KeyError, TypeError, ValueError):
            pass
    return ctx


class PronCongelado:
    """Pronosticador «congelado»: mallas y pronósticos ya calculados (lo que consume el simulador)."""

    def __init__(self, equipos, torneo, nombre, corte, mallas: dict, partidos: dict):
        self.equipos, self.torneo, self.nombre, self.corte = list(equipos), torneo, nombre, corte
        self._mallas, self._partidos = mallas, partidos

    def malla(self, n: int = 1, fase: str = "regular", semilla: int = 0) -> dict:
        return self._mallas[(int(n), fase, int(semilla))]

    def partidos(self, df) -> list[dict]:
        """
        Pronósticos guardados. Un partido que no estaba pendiente al armar la base (una ida de ayer que
        partidos.csv todavía no da por jugada porque no corrió pipeline.py auto) sale de la malla puntual
        (k = 0) de su fase, en vez de tumbar la simulación con un KeyError.
        """
        out = []
        ix = {e: i for i, e in enumerate(self.equipos)}
        cols = {c: list(df[c]) for c in ("id", "local", "visitante", "fase") if c in df}
        for k, i in enumerate(cols["id"]):
            d = self._partidos.get(int(i))
            if d is None:
                loc, vis = cols["local"][k], cols["visitante"][k]
                fase = "regular" if cols.get("fase", ["regular"] * len(cols["id"]))[k] == "regular" else "liguilla"
                m = next(v for (n, f, _), v in self._mallas.items() if f == fase)
                d = {"id": int(i), "local": loc, "visitante": vis, "lam_l": float(m["lam_l"][0][ix[loc]][ix[vis]]),
                     "lam_v": float(m["lam_v"][0][ix[loc]][ix[vis]]), "rho": float(m.get("rho", 0.0))}
            out.append(dict(d))
        return out


# ==================================================================================================
# Motor: arma el documento
# ==================================================================================================
class Motor:
    """
    Guarda entre ciclos lo que cuesta calcular (parámetros en juego, partidos.csv, el pronosticador
    congelado y la simulación base) y arma el documento del contrato a partir de los partidos «crudos».

    `pron`, `df` y `corte` sólo se pasan en pruebas y en `repetir` (contexto al corte de un partido
    viejo); en operación normal el contexto sale de salidas/actual.json y de los sellos.
    """

    def __init__(self, n_sim: int = N_SIM, n_muestras: int = N_MUESTRAS, proyectar: bool = True, pron=None, df=None,
                 corte: dt.datetime | None = None, actual: dict | None = None, sellos: dict | None = None,
                 parametros=None, pedir=None):
        self.n_sim, self.n_muestras, self.proyectar = int(n_sim), int(n_muestras), bool(proyectar)
        self.pron_fijo, self.df_fijo, self.corte = pron, df, corte
        self.actual_fijo, self.sellos_fijos, self.par = actual, sellos, parametros
        self.pedir = pedir
        # sólo el motor de producción (todo por omisión) reajusta los parámetros en juego, y sólo desde `una_vez`
        self.reajustar = pron is None and df is None and actual is None and sellos is None and parametros is None and pedir is None
        self._base: dict | None = None
        self._ctx: tuple | None = None
        self.memoria: dict[int, dict] = {}                       # por partido: cuándo se vio el descanso, el final...

    # ---------------- piezas pesadas (se cargan cuando hacen falta) ----------------
    def parametros(self):
        if self.par is None:
            from produccion import en_juego as EJ
            self.par = EJ.leer_parametros(actualizar=False) or EJ.leer_parametros()   # el reajuste es cosa de `pipeline.py auto`
            if self.par is None:
                raise RuntimeError("no hay parámetros del modelo en juego (python3 -m produccion.en_juego ajustar)")
        return self.par

    def df(self):
        if self.df_fijo is not None:
            return self.df_fijo
        from modelo import datos
        return datos.cargar()

    def contexto(self, ahora: dt.datetime) -> dict:
        """Contexto del día: de actual.json y sellos (operación) o reconstruido al corte (`repetir`)."""
        if self.corte is not None and self.actual_fijo is None:
            if self._ctx is None:
                self._ctx = ("corte", self._contexto_al_corte())
            return self._ctx[1]
        if self.actual_fijo is not None:
            if self._ctx is None:
                self._ctx = ("fijo", contexto_de_actual(self.actual_fijo, self.sellos_fijos or {}))
            return self._ctx[1]
        firma = tuple((r.stat().st_mtime_ns if r.exists() else 0) for r in (RUTA_ACTUAL, RUTA_SELLOS))
        if self._ctx is None or self._ctx[0] != firma:
            self._ctx = (firma, contexto_de_actual(leer_json(RUTA_ACTUAL), _sellos_oficiales()))
        return self._ctx[1]

    def _firma_base(self, ahora: dt.datetime) -> str:
        partes = [str(self.n_sim), str(self.n_muestras), str(dia_de_juego(ahora))]
        for r in (RAIZ / "datos" / "partidos.csv", RAIZ / "modelo" / "campeon.json"):
            try:
                st = r.stat()
                partes.append(f"{st.st_size}:{st.st_mtime_ns}")
            except OSError:
                partes.append("no")
        return "|".join(partes)

    def base(self, ahora: dt.datetime) -> dict:
        """
        Pronosticador congelado + simulación base (sin nada en juego) con la misma semilla y tamaño que la
        simulación al momento. Se guarda en memoria y en modelo/cache/vivo_base.pkl; se rehace cuando
        cambian partidos.csv, el modelo o el día.
        """
        from produccion import simulador as S
        corte = self.corte or ahora
        if self.pron_fijo is not None:                           # pruebas y `repetir`: sin caché en disco
            if self._base is None:
                sim = S.simular(self.pron_fijo, corte, self.df(), n_sim=self.n_sim, n_muestras=self.n_muestras)
                self._base = {"firma": "fijo", "pron": self.pron_fijo, "sim": _resumen_sim(sim)}
            return self._base
        firma = self._firma_base(ahora)
        if self._base is not None and self._base["firma"] == firma:
            return self._base
        try:
            with open(RUTA_BASE, "rb") as f:
                b = pickle.load(f)
            if b.get("firma") == firma:
                self._base = b
                return b
        except Exception:
            pass
        t0 = time.time()
        from produccion import obtener_pronosticador
        import pandas as pd
        df = self.df()
        # el pronosticador sólo pronostica hacia adelante: su corte es el arranque del día de partido (04:00 de
        # México), antes de cualquier partido de hoy; así también pronostica los que ya empezaron
        dia = dia_de_juego(corte)
        corte_pron = dt.datetime(dia.year, dia.month, dia.day, CORTE_DIA_H, tzinfo=ZONA).astimezone(UTC)
        pron = obtener_pronosticador(pd.Timestamp(corte_pron))
        K = max(1, min(self.n_muestras, self.n_sim))
        mallas = {(K + 1, f, S.SEMILLA): pron.malla(n=K + 1, fase=f, semilla=S.SEMILLA) for f in ("regular", "liguilla")}
        torneo = getattr(pron, "torneo", None) or S.cargar_reglas()["torneo"]
        pend = df[(df["torneo"] == torneo) & df["estado"].isin(S.ESTADOS_PENDIENTES) & (df["fecha_utc"] >= pd.Timestamp(corte_pron))]
        partidos = {int(d["id"]): {k: d[k] for k in ("id", "local", "visitante", "lam_l", "lam_v") if k in d} | {"rho": float(d.get("rho", 0.0))}
                    for d in (pron.partidos(pend) if len(pend) else [])}
        cong = PronCongelado(pron.equipos, torneo, getattr(pron, "nombre", type(pron).__name__), corte, mallas, partidos)
        sim = S.simular(cong, corte, df, n_sim=self.n_sim, n_muestras=self.n_muestras, torneo=torneo)
        b = {"firma": firma, "pron": cong, "sim": _resumen_sim(sim), "segundos": round(time.time() - t0, 1)}
        try:
            RUTA_BASE.parent.mkdir(parents=True, exist_ok=True)
            tmp = RUTA_BASE.with_suffix(f".{os.getpid()}.tmp")
            with open(tmp, "wb") as f:
                pickle.dump(b, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, RUTA_BASE)
        except OSError as e:
            log(f"aviso: no se pudo guardar {RUTA_BASE.name}: {e}")
        self._base = b
        return b

    def _contexto_al_corte(self) -> dict:
        """Contexto reconstruido con lo que se sabía en `self.corte` (para reproducir un partido ya jugado)."""
        import pandas as pd
        from produccion import exportar as EX
        from produccion import simulador as S
        df, corte = self.df(), pd.Timestamp(self.corte)
        b = self.base(self.corte)
        pron, sim = b["pron"], b["sim"]
        torneo = sim["torneo"]
        ctx = {"torneo": torneo, "regular_completa": sim["regular_completa"], "origen": "reconstruido al corte",
               "corte_utc": iso(self.corte), "n_sim": sim["n_sim"], "tabla": [{k: f[k] for k in ("pos", "equipo", "PJ", "PTS", "DG", "GF")} for f in sim["tabla"]],
               "p_clasifica": {e: v[0] for e, v in sim["p"].items()}, "p_campeon": {e: v[1] for e, v in sim["p"].items()},
               "partidos": {}, "series": [], "futuros": [], "por_equipos": {}}
        df_t = df[(df["torneo"] == torneo) & (df["estado"] != "cancelado")]
        jornadas = EX.etiquetas_jornada(df_t[df_t["fase"] == "regular"], int(S.cargar_reglas().get("jornadas", 17)))
        dia = dia_de_juego(self.corte + dt.timedelta(minutes=5))
        from modelo import arnes
        import numpy as np
        es_hoy = np.array([dia_de_juego(t.to_pydatetime()) == dia for t in df_t["fecha_utc"]], dtype=bool)
        hoy = df_t[es_hoy & (df_t["fecha_utc"] >= corte).to_numpy()]
        sellos = self.sellos_fijos if self.sellos_fijos is not None else _sellos_oficiales()
        for (_, fila), d in zip(hoy.iterrows(), pron.partidos(hoy) if len(hoy) else []):
            M = arnes.matriz_marcadores(d["lam_l"], d["lam_v"], d.get("rho", 0.0))
            p = np.asarray(arnes.p1x2(M), float).ravel()
            x, y, _ = arnes.marcador_mas_probable(M)
            pid = int(fila["id"])
            ctx["partidos"][pid] = {"fase": fila["fase"], "etiqueta": EX.etiqueta_partido(fila, jornadas),
                                    "pierna": int(fila["pierna"]) if pd.notna(fila["pierna"]) else None,
                                    "previo": _previo(p[0], p[1], p[2], d["lam_l"], d["lam_v"], d.get("rho", 0.0),
                                                      {"gl": x, "gv": y}, "modelo al corte (no sellado)")}
            s = sellos.get(pid)
            if s is not None:
                ctx["partidos"][pid]["previo"] = _previo(s["p_l"], s["p_e"], s["p_v"], s["lam_l"], s["lam_v"], s.get("rho"),
                                                         s.get("marcador"), "sello")
        if sim["regular_completa"] and sim.get("completo"):
            try:
                clasificados = [f["equipo"] for f in sim["tabla"][: sim["clasifican"]]]
                tor = EX.redondear(EX.torneo_liguilla(pron, sim["completo"], S.cargar_reglas(), clasificados, df))
                # partidos.csv ya trae las rondas siguientes (se jugaron después): ese día ESPN todavía no las listaba
                orden = {"repechaje": 0, "cuartos": 1, "semifinal": 2, "final": 3}
                tope = max((orden.get(i.get("fase"), 0) for i in ctx["partidos"].values()), default=3)
                ctx["series"] = [s for r in tor["rondas"] for s in r["series"] if s.get("real") and orden.get(s["fase"], 0) <= tope]
            except Exception as e:
                log(f"aviso: no se pudo armar la liguilla al corte: {type(e).__name__}: {e}")
        return ctx

    # ---------------- documento ----------------
    def documento(self, crudas: list[dict], ahora: dt.datetime, ahora_juego: dt.datetime | None = None,
                  ultimo_evento: dict | None = None, avisos: list[str] | None = None, prueba: bool = False) -> dict:
        """
        Documento del contrato. `ahora` es el reloj real (generado_utc, reloj_utc); `ahora_juego` el reloj
        con el que se decide qué partidos son de hoy (sólo difiere en `repetir`).
        """
        t_juego = ahora_juego or ahora
        avisos = list(avisos or [])
        ctx = self.contexto(t_juego)
        hoy = dia_de_juego(t_juego)
        partidos = [self._partido(c, ctx, ahora, avisos) for c in crudas if dia_de_juego(c["inicio"]) == hoy]
        partidos.sort(key=lambda p: (p["inicio_utc"], p["id"]))
        activos = [p for p in partidos if p["estado"] in ESTADOS_ACTIVOS]
        if not partidos:
            estado = "sin_partidos"
        elif any(p["estado"] == "en_juego" for p in partidos):
            estado = "en_juego"
        elif activos:
            estado = "descanso"
        elif any(p["estado"] == "programado" for p in partidos):
            estado = "previo"
        else:
            estado = "terminado_hoy"
        doc = {"version": VERSION, "generado_utc": iso(ahora), "dia": str(hoy), "estado": estado, "partidos": partidos}
        # con algo en juego el motor vuelve a escribir, como muy tarde, en MIN_REFRESCO minutos: pasado `vence_utc` la
        # página deja de presentarlo como «en vivo» (se cortó el flujo). Sin nada en juego no caduca.
        doc["vence_utc"] = iso(ahora + dt.timedelta(minutes=MIN_REFRESCO + MIN_VENCE)) if activos else None
        if prueba:
            doc["prueba"] = True
        # tabla, proyección y series: cada bloque aislado (si uno falla, el documento sale con lo previo y un aviso)
        tocados = [p for p in partidos if p["estado"] in ("en_juego", "descanso", "final")]
        # liguilla: la tabla ya no se mueve con los marcadores (la página puede titularla «Tabla final» y quitar las flechas)
        doc["tabla_fija"] = bool(ctx.get("regular_completa"))
        try:
            doc["tabla"], doc["tabla_nota"] = self._tabla(ctx, partidos, tocados, t_juego)
        except Exception as e:
            avisos.append(f"tabla al momento no disponible ({type(e).__name__}: {e}); se muestra la previa")
            doc["tabla"] = [dict(f, cambio=0, en_juego=False) for f in ctx["tabla"]]
            doc["tabla_nota"] = "Tabla previa a los partidos de hoy."
        # las series van antes que la proyección: el campeón al momento usa el ganador que dicta el reglamento
        idas = {}                                                  # idas que actual.json no traía y se completaron
        try:
            doc["series"] = self._series(ctx, partidos, avisos, idas)
        except Exception as e:
            traceback.print_exc()
            avisos.append(f"series al momento no disponibles ({type(e).__name__}: {e})")
            doc["series"] = []
        por_llave = {}
        for s in doc["series"]:
            for pi in s["piernas"]:
                if pi.get("id") is not None:
                    por_llave[pi["id"]] = s
        ganadores = {pi["id"]: s["ganador"] for s in doc["series"] if s.get("decidida") and s.get("ganador")
                     for pi in s["piernas"] if pi.get("id") is not None and pi.get("pierna") == 2 and pi.get("estado") == "final"}
        try:
            doc["proyeccion"] = self._proyeccion(ctx, tocados, t_juego, ganadores, idas)
        except Exception as e:
            traceback.print_exc()
            avisos.append(f"proyección al momento no disponible ({type(e).__name__}: {e}); se muestra la previa")
            doc["proyeccion"] = _proyeccion_previa(ctx, self.n_sim, "No se pudo recalcular: es la proyección previa.")
        for p in partidos:
            s = por_llave.get(p["id"])
            p["serie"] = None if s is None else {
                "llave": s["llave"], "mejor": s["mejor"]["equipo"], "peor": s["peor"]["equipo"], "global_mejor": s["global_mejor"],
                "global_peor": s["global_peor"], "p_avanza_mejor": s["p_avanza_mejor"], "p_avanza_peor": s["p_avanza_peor"],
                "fase": s["fase"], "decidida": s["decidida"], "ganador": s["ganador"],
                "pierna": next((pi["pierna"] for pi in s["piernas"] if pi.get("id") == p["id"]), None),
                "ida": s.get("ida"), "momento": s.get("momento"), "avanza_ahora": s.get("avanza_ahora"),
                "motivo_ahora": s.get("motivo_ahora"), "le_falta": s.get("le_falta"), "texto": s.get("texto")}
            p.pop("_cruda", None)
        doc["ultimo_evento"] = ultimo_evento
        doc["siguiente"] = self._siguiente(ctx, partidos, t_juego)
        if avisos:
            doc["avisos"] = avisos
        return doc

    def _partido(self, c: dict, ctx: dict, ahora: dt.datetime, avisos: list[str]) -> dict:
        info = ctx["partidos"].get(c["id"]) or (ctx.get("por_equipos") or {}).get((c["local"], c["visitante"])) or {}
        fase = info.get("fase")
        if not fase:
            _tablas_espn()
            fase = _FASE_SLUG(c.get("slug")) if _FASE_SLUG else "regular"
        pierna = info.get("pierna") or c.get("pierna")
        etiqueta = info.get("etiqueta") or ("Fase regular" if fase == "regular" else
                                           NOMBRE_FASE.get(fase, str(fase).capitalize()) + (f", {'ida' if pierna == 1 else 'vuelta'}" if pierna else ""))
        estado, periodo, minuto, anadido = c["estado"], c.get("periodo") or 0, c.get("minuto"), c.get("anadido")
        mem = self.memoria.setdefault(c["id"], {})
        reloj, medio = None, False
        if estado == "programado" or estado == "pospuesto":
            periodo = minuto = anadido = None
        elif estado == "descanso":
            # medio tiempo (ESPN puede decir periodo 1 o 2) o una pausa a media cancha (lluvia, suspensión)
            medio = c.get("medio_tiempo")
            if medio is None:
                medio = periodo <= 2 and (minuto is None or 40 <= minuto <= 50)
            if medio:
                periodo, minuto, anadido = 1, 45, None
            reloj = mem.setdefault("descanso_utc", iso(ahora))
        elif estado == "en_juego":
            periodo = max(periodo, 1)
            if minuto is None:
                minuto = {1: 1, 2: 46, 3: 91, 4: 106}.get(periodo, 120)
            elif periodo == 2 and minuto <= 45:                    # ya es el segundo tiempo y el reloj sigue en «45'+3'»
                minuto, anadido = 46, None
            elif anadido is None:                                  # agregado escrito como «92'» y no «90'+2'»: mismo reloj
                tope = {1: 45, 2: 90, 3: 105, 4: 120}.get(periodo)
                # ventana corta en el primer tiempo extra: si ESPN no movió el periodo, «112'» es del segundo
                if tope is not None and tope < minuto <= tope + {1: 15, 2: 30, 3: 5, 4: 30}[periodo]:
                    minuto, anadido = tope, minuto - tope
            seg = c.get("segundos")
            dentro = (seg % 60.0) if (seg and seg > 0) else 30.0  # segundos ya corridos del minuto que marca el reloj
            reloj = iso(ahora - dt.timedelta(seconds=dentro))
            mem.pop("descanso_utc", None)
        else:                                                      # final
            periodo = periodo or 2
            if minuto is None:
                minuto = 90 if periodo <= 2 else 120
        gl, gv = (None, None) if estado in ("programado", "pospuesto") else (c.get("gl") or 0, c.get("gv") or 0)
        eventos, a, b, rl, rv, g90 = [], 0, 0, 0, 0, [0, 0]
        fair = [{}, {}]
        for j in c.get("jugadas") or []:
            if j["clase"] == "gol":
                a, b = (a + 1, b) if j["lado"] == 0 else (a, b + 1)
                if (j["min"] or 0) <= 90:                         # el agregado viene como «90'+3'» (minuto 90)
                    g90[j["lado"]] += 1
            elif j["clase"] == "roja":
                rl, rv = (rl + 1, rv) if j["lado"] == 0 else (rl, rv + 1)
            if j["clase"] in ("roja", "amarilla"):               # Fair Play: sólo amarilla 1; cualquier roja 3
                llave = j["jid"] or j["jugador"]
                fair[j["lado"]][llave] = 3 if j["clase"] == "roja" else max(fair[j["lado"]].get(llave, 0), 1)
            if j["clase"] in ("gol", "roja"):
                eventos.append({"min": j["min"], "anadido": j["anadido"], "tipo": j["tipo"],
                                "equipo": c["local"] if j["lado"] == 0 else c["visitante"], "jugador": j["jugador"],
                                "marcador": f"{a}-{b}"})
        if estado in ("programado", "pospuesto"):
            eventos, rl, rv = [], 0, 0
        # marcador a 90 minutos (el que cuenta para el pronóstico y la tabla): ESPN suma los goles del tiempo extra
        if gl is not None and periodo and periodo >= 3:
            if (a, b) == (gl, gv):                                 # todas las jugadas publicadas: mandan sus minutos
                extra = [(a, b)[k] - g90[k] for k in (0, 1)]
            elif mem.get("g90"):                                   # ESPN movió el marcador sin publicar la jugada: es del tiempo extra
                extra = [max(0, gl - mem["g90"][0]), max(0, gv - mem["g90"][1])]
            else:
                extra = [0, 0]
            gl90, gv90 = gl - extra[0], gv - extra[1]
        else:
            gl90, gv90, extra = gl, gv, [0, 0]
            if gl is not None and estado in ESTADOS_ACTIVOS:
                mem["g90"] = (gl, gv)                              # mientras no haya tiempo extra, éste es el marcador a 90 minutos
        previo = info.get("previo")
        if previo is None and self.proyectar and estado in ("en_juego", "descanso", "final"):
            try:                                                   # sin sello: el pronóstico del modelo congelado
                d = self.base(ahora)["pron"].partidos({"id": [c["id"]]})[0]
                from modelo import arnes
                import numpy as np
                M = arnes.matriz_marcadores(d["lam_l"], d["lam_v"], d.get("rho", 0.0))
                pp = np.asarray(arnes.p1x2(M), float).ravel()
                x, y, _ = arnes.marcador_mas_probable(M)
                previo = _previo(pp[0], pp[1], pp[2], d["lam_l"], d["lam_v"], d.get("rho", 0.0), {"gl": x, "gv": y}, "modelo (sin sello)")
            except Exception:
                previo = None
        vivo, rest = None, None
        if estado in ESTADOS_ACTIVOS and previo is not None:
            try:
                from produccion import en_juego as EJ
                par = self.parametros()
                fin90 = periodo >= 3 or (estado == "descanso" and not medio and periodo == 2 and (minuto or 0) >= 90)
                if fin90:                                          # tiempos extra, penales o pausa tras los 90: ya acabaron
                    r = EJ.pronostico(par, previo["lam_l"], previo["lam_v"], gl90, gv90, 90, 2, terminado=True)
                else:
                    r = EJ.pronostico(par, previo["lam_l"], previo["lam_v"], gl90, gv90, minuto, periodo, anadido, rl, rv,
                                      descanso=medio, en_curso=True, rho=previo.get("rho", 0.0))
                vivo = {"p_local": _r4(r["p_local"]), "p_empate": _r4(r["p_empate"]), "p_visitante": _r4(r["p_visitante"]),
                        "goles_restantes_l": round(r["goles_restantes_l"], 2), "goles_restantes_v": round(r["goles_restantes_v"], 2),
                        "marcador_final": {"gl": r["marcador_final"]["gl"], "gv": r["marcador_final"]["gv"],
                                           "prob": _r4(r["marcador_final"]["prob"])}}
                rest = (r["goles_restantes_l"], r["goles_restantes_v"])
            except Exception as e:
                avisos.append(f"{c['local']} vs {c['visitante']}: sin pronóstico al momento ({type(e).__name__}: {e})")
        elif estado in ESTADOS_ACTIVOS:
            avisos.append(f"{c['local']} vs {c['visitante']}: no hay pronóstico previo, no se calcula el pronóstico al momento")
        if estado == "final":
            rest = (0.0, 0.0)
        p = {"id": c["id"], "fase": fase, "etiqueta": etiqueta, "local": c["local"], "visitante": c["visitante"],
             "estado": estado, "inicio_utc": iso(c["inicio"]), "periodo": periodo, "minuto": minuto, "anadido": anadido,
             "reloj_utc": reloj, "gl": gl, "gv": gv, "rojas_l": rl, "rojas_v": rv, "eventos": eventos,
             "previo": None if previo is None else {
                 "p_local": _r4(previo["p_local"]), "p_empate": _r4(previo["p_empate"]), "p_visitante": _r4(previo["p_visitante"]),
                 "marcador": previo["marcador"], "lam_l": _r4(previo["lam_l"]), "lam_v": _r4(previo["lam_v"])},
             "vivo": vivo, "serie": None}
        if previo is not None and previo.get("origen") != "sello":
            p["previo"]["origen"] = previo.get("origen")
        if gl is not None and (periodo or 0) >= 3:                 # con tiempo extra: el marcador a 90' (el del pronóstico)
            p["gl90"], p["gv90"] = gl90, gv90
        if c.get("tanda_l") is not None and c.get("tanda_v") is not None and (periodo or 0) >= 5:
            p["penales"] = {"l": c["tanda_l"], "v": c["tanda_v"]}
        # lo que necesitan la tabla, la simulación y las series (no sale en el documento)
        p["_cruda"] = {"gl90": gl90, "gv90": gv90, "extra": extra, "rest": rest, "previo": previo, "pierna": pierna,
                       "fair": [sum(fair[0].values()), sum(fair[1].values())], "gana": c.get("gana"),
                       "segundos": c.get("segundos"), "rojas": (rl, rv), "tanda": (c.get("tanda_l"), c.get("tanda_v")),
                       "global": (c.get("global_l"), c.get("global_v"))}
        return p

    def _tabla(self, ctx: dict, partidos: list[dict], tocados: list[dict], ahora: dt.datetime) -> tuple[list[dict], str]:
        """Tabla al momento: los marcadores en juego cuentan como finales (desempates oficiales del simulador)."""
        reg = [p for p in tocados if p["fase"] == "regular"]
        jugando = {e for p in partidos if p["estado"] in ESTADOS_ACTIVOS for e in (p["local"], p["visitante"])}
        if ctx.get("regular_completa") or (not reg and ctx.get("series")):
            # liguilla: la tabla ya no se mueve (la liguilla no suma puntos); sólo decide quién es el mejor sembrado
            return ([dict(f, cambio=0, en_juego=f["equipo"] in jugando) for f in ctx["tabla"]],
                    "Tabla final de la fase regular: en la liguilla no se suman puntos; el lugar decide quién avanza "
                    "con el global empatado en cuartos y semifinales.")
        if not reg:
            return ([dict(f, cambio=0, en_juego=f["equipo"] in jugando) for f in ctx["tabla"]],
                    "Tabla general: hoy no hay partidos de fase regular en juego.")
        import numpy as np
        import pandas as pd
        from produccion import simulador as S
        df = self.df()
        torneo = ctx.get("torneo") or S.cargar_reglas()["torneo"]
        est = S.estado_torneo(df, torneo, pd.Timestamp(self.corte or ahora))
        ix = {e: i for i, e in enumerate(est["equipos"])}
        pos_pend = {int(i): j for j, i in enumerate(est["pendientes"]["id"])}

        def copia(e):
            return {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in e.items()}

        def sumar(e, p):
            j = pos_pend.get(p["id"])
            if j is None or p["local"] not in ix or p["visitante"] not in ix:
                return False                                       # ya está contado en partidos.csv (o no es de este torneo)
            a, b = ix[p["local"]], ix[p["visitante"]]
            x, y = p["_cruda"]["gl90"], p["_cruda"]["gv90"]
            pl, pv = (3, 0) if x > y else ((1, 1) if x == y else (0, 3))
            for i, gf, gc, pt, lado in ((a, x, y, pl, "l"), (b, y, x, pv, "v")):
                e["pj"][i] += 1; e["gf"][i] += gf; e["gc"][i] += gc; e["pts"][i] += pt
                e["g"][i] += pt == 3; e["e"][i] += pt == 1; e["p"][i] += pt == 0
                e["pj_" + lado][i] += 1; e["pts_" + lado][i] += pt
                e["gf_" + lado][i] += gf; e["gc_" + lado][i] += gc
                e["coc_pts"][i] += pt; e["coc_pj"][i] += 1
            e["n_vis"][b] += 1
            if est["pend_cuenta_vis"][j]:
                e["gvis"][b] += y
            e["fair"][a] += p["_cruda"]["fair"][0]; e["fair"][b] += p["_cruda"]["fair"][1]
            e["dg"] = e["gf"] - e["gc"]
            e["cociente"] = np.divide(e["coc_pts"], e["coc_pj"], out=np.zeros(len(e["equipos"])), where=e["coc_pj"] > 0)
            return True

        base = copia(est)
        for p in reg:
            if p["estado"] == "final":
                sumar(base, p)
        viva = copia(base)
        n_vivos = sum(sumar(viva, p) for p in reg if p["estado"] in ESTADOS_ACTIVOS)
        tb, tv = S.tabla_actual(base), S.tabla_actual(viva)
        pos_b = dict(zip(tb["equipo"], tb["pos"]))
        filas = [{"pos": int(r.pos), "equipo": r.equipo, "PJ": int(r.PJ), "PTS": int(r.PTS), "DG": int(r.DG), "GF": int(r.GF),
                  "cambio": int(pos_b[r.equipo] - r.pos), "en_juego": r.equipo in jugando} for r in tv.itertuples(index=False)]
        nota = ("Tabla al momento: cuenta los marcadores de los partidos en juego como si terminaran así."
                if n_vivos else "Tabla con los resultados de hoy.")
        return filas, nota

    def _en_juego_sim(self, tocados: list[dict], ganadores: dict | None = None) -> dict:
        """
        Entrada `en_juego` del simulador: marcador a 90' y goles que faltan de cada partido tocado hoy. Una
        vuelta de liguilla que ya terminó lleva `avanza` = el ganador de la serie según el reglamento
        (`ganadores`, calculado en `_series`; no el `winner` de ESPN, que es el del partido).
        """
        ganadores = ganadores or {}
        ej = {}
        for p in tocados:
            c = p["_cruda"]
            if c["rest"] is None:                                  # en juego sin pronóstico previo: no se puede condicionar
                continue
            d = {"gl": c["gl90"], "gv": c["gv90"], "lam_rest_l": float(c["rest"][0]), "lam_rest_v": float(c["rest"][1])}
            if c["previo"] is not None:
                d["lam_l"], d["lam_v"] = c["previo"]["lam_l"], c["previo"]["lam_v"]
            x = self._extra(p)
            if x is not None:
                d["extra"] = x
            if p["estado"] == "final" and ganadores.get(p["id"]):
                d["avanza"] = ganadores[p["id"]]
            ej[p["id"]] = d
        return ej

    def _extra(self, p: dict) -> dict | None:
        """Estado del tiempo extra de la vuelta de la final (None si no está en tiempo extra)."""
        c = p["_cruda"]
        if p["fase"] != "final" or (p["periodo"] or 0) < 3 or p["estado"] not in ESTADOS_ACTIVOS or c["previo"] is None:
            return None
        from produccion import en_juego as EJ
        par = self.parametros()
        fr = EJ.fraccion_extra_restante(p["minuto"], p["periodo"])
        dif = c["extra"][0] - c["extra"][1]
        rl, rv = c["rojas"]
        return {"gl": c["extra"][0], "gv": c["extra"][1], "penales": (p["periodo"] or 0) >= 5,
                "lam_rest_l": c["previo"]["lam_l"] * EJ.FRACCION_EXTRA * fr * EJ.multiplicador(par.ef, dif, rl, rv),
                "lam_rest_v": c["previo"]["lam_v"] * EJ.FRACCION_EXTRA * fr * EJ.multiplicador(par.ef, -dif, rv, rl)}

    def _proyeccion(self, ctx: dict, tocados: list[dict], ahora: dt.datetime, ganadores: dict | None = None,
                    idas: dict | None = None) -> dict:
        """
        Clasificación y campeón al momento, con el cambio frente al último pronóstico previo. `idas` = {id:
        (gl, gv)} de idas que partidos.csv aún no da por jugadas: entran con su marcador fijo.
        """
        if not tocados or not self.proyectar:
            return _proyeccion_previa(ctx, self.n_sim, None if not tocados else "Proyección previa (no se recalculó).")
        from produccion import simulador as S
        ej = self._en_juego_sim(tocados, ganadores)
        for pid, (gl, gv) in (idas or {}).items():
            ej.setdefault(int(pid), {"gl": int(gl), "gv": int(gv), "lam_rest_l": 0.0, "lam_rest_v": 0.0})
        for intento in (0, 1):
            b = self.base(ahora)
            try:
                sim = _resumen_sim(S.simular(b["pron"], self.corte or ahora, self.df(), n_sim=self.n_sim, n_muestras=self.n_muestras,
                                             torneo=b["sim"]["torneo"], en_juego=ej), completo=False)
                break
            except KeyError:                                       # la base guardada no conoce un partido nuevo: se rehace
                if intento or self.pron_fijo is not None:
                    raise
                self._base = None
                RUTA_BASE.unlink(missing_ok=True)
        aplicados = set(sim["en_juego"])
        if not aplicados:                                          # todo lo de hoy ya está en partidos.csv
            return _proyeccion_previa(ctx, self.n_sim, None)
        out = {"n_sim": sim["n_sim"], "clasifica": [], "campeon": [], "ruido": RUIDO_DELTA,
               "partidos_considerados": sorted(aplicados)}
        for k, llave, previa in ((0, "clasifica", ctx["p_clasifica"]), (1, "campeon", ctx["p_campeon"])):
            if llave == "clasifica" and sim["regular_completa"]:
                continue
            for e, v in sim["p"].items():
                delta = v[k] - b["sim"]["p"].get(e, (0.0, 0.0))[k]
                p0 = previa.get(e, b["sim"]["p"].get(e, (0.0, 0.0))[k])
                # control de varianza: último pronóstico previo + cambio medido con los mismos sorteos
                p1 = p0 + delta
                if v[k] <= 0.0 or v[k] >= 1.0 or not (0.0 < p1 < 1.0):
                    p1 = v[k]                                      # ya decidido (0 o 1), o la suma se salió de rango
                if (llave == "clasifica" and 0.0005 < max(p0, p1) and min(p0, p1) < 0.9995) or (llave == "campeon" and max(p0, p1) >= 0.0005):
                    out[llave].append({"equipo": e, "p": _r4(p1), "delta": _r4(p1 - p0)})
            out[llave].sort(key=lambda d: (-d["p"], d["equipo"]))
        return out

    def _series(self, ctx: dict, partidos: list[dict], avisos: list[str] | None = None, idas: dict | None = None) -> list[dict]:
        """
        Series de la liguilla (las de `liguilla.torneo` que ya están en el calendario o cuyos dos equipos ya
        son seguros) con el global y la probabilidad de avanzar al momento, y cómo va la serie: `momento`,
        `ida`, `avanza_ahora` / `motivo_ahora` (si terminara así), `le_falta` (goles netos que le faltan a
        cada uno) y `texto` (una línea lista para mostrar). Una pierna de hoy se reconoce por su id o, si
        actual.json todavía no lo trae, por sus equipos. Si la vuelta se juega hoy y actual.json no tiene la
        ida como jugada (no corrió pipeline.py auto), la ida sale de partidos.csv o del global que da ESPN, con
        un aviso; nunca se trata como por jugar en silencio.
        """
        if not ctx["series"]:
            return []
        avisos = avisos if avisos is not None else []
        from modelo import arnes
        from produccion import en_juego as EJ
        from produccion import simulador as S
        hoy = {p["id"]: p for p in partidos}
        por_eq = {(p["local"], p["visitante"]): p for p in partidos}
        out = []
        for s in ctx["series"]:
            mejor, peor, fase = s["mejor"]["equipo"], s["peor"]["equipo"], s["fase"]
            legs = [dict(pi) for pi in sorted(s.get("piernas") or [], key=lambda d: d["pierna"])]
            de_hoy = {}
            for pi in legs:
                p = hoy.get(pi.get("id")) if pi.get("id") is not None else por_eq.get((pi["local"], pi["visitante"]))
                if p is not None and (pi.get("id") is not None or p["fase"] == fase):
                    de_hoy[pi["pierna"]] = p
                    pi["id"] = p["id"]
            self._ida_que_falta(legs, de_hoy, mejor, peor, avisos)
            ida0 = legs[0] if legs and legs[0]["pierna"] == 1 else None
            if idas is not None and ida0 is not None and ida0.get("supuesta") and ida0.get("id") is not None:
                idas[int(ida0["id"])] = (ida0["gl"], ida0["gv"])
            piernas, Ms, gm, gp, tocada, lam2 = [], {}, 0, 0, False, None
            fin_hoy, vuelta, estados = None, None, {}
            for pi in legs:
                num = pi["pierna"]
                p = de_hoy.get(num)
                d = {"pierna": num, "id": pi.get("id"), "local": pi["local"], "visitante": pi["visitante"],
                     "estado": "final" if pi.get("jugado") else "programado", "gl": pi.get("gl"), "gv": pi.get("gv")}
                info = ctx["partidos"].get(pi.get("id")) or (ctx.get("por_equipos") or {}).get((pi["local"], pi["visitante"])) or {}
                rho = float((info.get("previo") or {}).get("rho", 0.0))
                if num == 2 and not pi.get("jugado"):
                    lam2 = (pi.get("lam_l"), pi.get("lam_v"))
                if pi.get("jugado"):
                    Ms[num] = S.matriz_fija(pi["gl"], pi["gv"])
                    a, b = pi["gl"], pi["gv"]
                elif p is not None and p["estado"] in ("en_juego", "descanso", "final"):
                    tocada = True
                    c = p["_cruda"]
                    d.update({"estado": p["estado"], "gl": p["gl"], "gv": p["gv"]})
                    a, b = p["gl"], p["gv"]                        # el global que se ve incluye el tiempo extra
                    rest = c["rest"] if c["rest"] is not None else (0.0, 0.0)
                    Ms[num] = EJ.matriz_final(c["gl90"], c["gv90"], rest[0], rest[1], rho if p["estado"] != "final" else 0.0)
                    if num == 2:
                        vuelta = p
                        fin_hoy = p if p["estado"] == "final" else None
                else:
                    Ms[num] = arnes.matriz_marcadores(pi["lam_l"], pi["lam_v"], rho)
                    a = b = None
                if a is not None:
                    gm += a if pi["local"] == mejor else b
                    gp += b if pi["local"] == mejor else a
                estados[num] = d["estado"]
                piernas.append(d)
            ida = next(({"local": d["local"], "visitante": d["visitante"], "gl": d["gl"], "gv": d["gv"]}
                        for d in piernas if d["pierna"] == 1 and d["estado"] == "final"), None)
            base = {"llave": s["llave"], "fase": fase, "mejor": s["mejor"], "peor": s["peor"], "piernas": piernas,
                    "global_mejor": gm, "global_peor": gp, "ida": ida}
            if not tocada or len(Ms) < 2:                          # nada de hoy: lo que ya decía actual.json
                pm = float(s.get("p_avanza_mejor", 0.5))
                decidida, ganador = bool(s.get("decidida")), s.get("ganador")
                fila = {**base, "p_avanza_mejor": _r4(pm), "p_avanza_peor": _r4(1 - pm), "delta_avanza_mejor": 0.0,
                        "favorito": s.get("favorito"), "p_favorito": _r4(s.get("p_favorito")),
                        "decidida": decidida, "ganador": ganador, "al_momento": False}
            else:
                l1 = next(d["local"] for d in piernas if d["pierna"] == 1) == mejor
                l2 = next(d["local"] for d in piernas if d["pierna"] == 2) == mejor
                if lam2 is None or lam2[0] is None:
                    pv = (ctx["partidos"].get(vuelta["id"]) or {}).get("previo") if vuelta else None
                    lam2 = (pv["lam_l"], pv["lam_v"]) if pv else (1.3, 1.1)
                r = EJ.prob_avanza(fase, Ms[1], Ms[2], l1, l2, lam2)
                pm = r["p_avanza_mejor"]
                decidida, ganador = False, None
                x = self._extra(vuelta) if vuelta is not None else None
                if x is not None:                                  # final en tiempo extra: el global a 90' quedó empatado
                    p_loc = EJ.prob_tiempos_extra(x["gl"], x["gv"], x["lam_rest_l"], x["lam_rest_v"], x["penales"])
                    pm = r["p_global_mejor"] + r["p_global_empate"] * (p_loc if l2 else 1.0 - p_loc)
                if fin_hoy is not None:                            # la vuelta acabó hoy: quién avanzó lo dice el reglamento
                    lado = self._ganador_vuelta(fase, fin_hoy, legs, mejor)
                    if lado is not None:
                        decidida, ganador = True, (mejor if lado == "mejor" else peor)
                        pm = 1.0 if ganador == mejor else 0.0
                    elif fase == "final" and (fin_hoy["periodo"] or 0) >= 3:
                        pm = 0.5                                   # hubo tiempos extra sin ganador: penales sin dato de ESPN
                fav = ganador or (mejor if pm >= 0.5 else peor)
                fila = {**base, "p_avanza_mejor": _r4(pm), "p_avanza_peor": _r4(1 - pm),
                        "delta_avanza_mejor": _r4(pm - float(s.get("p_avanza_mejor", pm))), "favorito": fav,
                        "p_favorito": _r4(pm if fav == mejor else 1 - pm), "decidida": decidida, "ganador": ganador,
                        "al_momento": True}
            fila.update(self._como_va(fase, mejor, peor, piernas, estados, vuelta, fila["decidida"], fila["ganador"], gm, gp))
            out.append(fila)
        return out

    def _ida_que_falta(self, legs: list[dict], de_hoy: dict, mejor: str, peor: str, avisos: list[str]) -> None:
        """
        La vuelta se juega hoy y actual.json no tiene la ida como jugada (no corrió pipeline.py auto después de
        la ida): se completa con partidos.csv o, si tampoco está ahí, con el global que da ESPN en la vuelta
        (`aggregateScore` menos el marcador de la vuelta). Si ninguno sirve, se avisa. Si la ida sí está y el
        global de ESPN no cuadra con ella, también se avisa (manda actual.json).
        """
        ida = next((pi for pi in legs if pi["pierna"] == 1), None)
        v = de_hoy.get(2)
        if ida is None or v is None or v["estado"] not in ("en_juego", "descanso", "final"):
            return
        gl_v, gv_v = v["_cruda"].get("global") or (None, None)
        del_espn = None
        if gl_v is not None and gv_v is not None and v["gl"] is not None:
            # goles de la ida de cada equipo = global de la serie − goles de la vuelta (con su tiempo extra)
            ida_de = {v["local"]: gl_v - v["gl"], v["visitante"]: gv_v - v["gv"]}
            if set(ida_de) == {ida["local"], ida["visitante"]} and min(ida_de.values()) >= 0:
                del_espn = (ida_de[ida["local"]], ida_de[ida["visitante"]])
        if ida.get("jugado"):
            if del_espn is not None and del_espn != (ida["gl"], ida["gv"]):
                avisos.append(f"El global de ESPN no cuadra con la ida de actual.json ({ida['local']} {ida['gl']}-{ida['gv']} "
                              f"{ida['visitante']}; según ESPN {del_espn[0]}-{del_espn[1]}): se usa actual.json.")
            return
        if de_hoy.get(1) is not None:                              # la ida también es hoy: no falta nada
            return
        fuente = None
        if ida.get("id") is not None:
            try:
                df = self.df()
                fila = df[df["id"] == int(ida["id"])]
                if len(fila) and fila.iloc[0]["estado"] == "jugado":
                    ida.update(jugado=True, gl=int(fila.iloc[0]["gl"]), gv=int(fila.iloc[0]["gv"]))
                    fuente = "de datos/partidos.csv"
            except Exception as e:                                 # sin partidos.csv se intenta con ESPN
                log(f"aviso: no se pudo leer la ida en partidos.csv: {type(e).__name__}: {e}")
        if fuente is None and del_espn is not None:
            ida.update(jugado=True, gl=del_espn[0], gv=del_espn[1], supuesta=True)   # la simulación no la conoce
            fuente = "del global que da ESPN"
        if fuente is not None:
            avisos.append(f"La ida {ida['local']} {ida['gl']}-{ida['gv']} {ida['visitante']} no estaba jugada en actual.json: "
                          f"se tomó {fuente}. Correr python3 pipeline.py auto.")
        else:
            avisos.append(f"La ida {ida['local']}-{ida['visitante']} no aparece jugada ni en actual.json ni en partidos.csv y ESPN "
                          "no da el global: la probabilidad de avanzar la trata como por jugar. Correr python3 pipeline.py auto.")

    def _ganador_vuelta(self, fase: str, fin: dict, legs: list[dict], mejor: str) -> str | None:
        """
        Quién ganó la serie («mejor» o «peor») con la vuelta ya terminada, por el reglamento: global a 90
        minutos; empatado en cuartos o semifinales, el mejor sembrado; en la final, los goles del tiempo extra
        y luego la tanda. En la vuelta el `winner` de ESPN marca a quien avanza según ESPN (Clausura 2009:
        Pachuca perdió 2-3 la vuelta y es `winner` por el global 4-3), pero ESPN aplica reglas viejas: en
        Pumas 3-3 América (Clausura 2026, global 6-6) no marcó a nadie y su nota dio a América por gol de
        visitante, regla que ya no existe. Por eso sólo se usa en la final, tras el tiempo extra sin goles de
        diferencia y mientras ESPN no publique la tanda. None si todavía no se sabe.
        """
        c = fin["_cruda"]
        if any(not pi.get("jugado") for pi in legs if pi["pierna"] != 2):
            return None                                            # sin el marcador de la ida no se puede decidir (ya hay aviso)
        lado_m = 0 if fin["local"] == mejor else 1
        g90m = sum((pi["gl"] if pi["local"] == mejor else pi["gv"]) for pi in legs if pi.get("jugado") and pi["pierna"] != 2)
        g90p = sum((pi["gv"] if pi["local"] == mejor else pi["gl"]) for pi in legs if pi.get("jugado") and pi["pierna"] != 2)
        g90 = (c["gl90"], c["gv90"])
        g90m, g90p = g90m + g90[lado_m], g90p + g90[1 - lado_m]
        extra = list(c.get("extra") or (0, 0))
        tanda = c.get("tanda") or (None, None)
        if g90m != g90p:
            return "mejor" if g90m > g90p else "peor"
        if fase != "final":
            return "mejor"                                         # global empatado: avanza el mejor sembrado
        if extra[lado_m] != extra[1 - lado_m]:
            return "mejor" if extra[lado_m] > extra[1 - lado_m] else "peor"
        if None not in tanda and tanda[0] != tanda[1]:
            gana_local = tanda[0] > tanda[1]
            return "mejor" if gana_local == (lado_m == 0) else "peor"
        if c.get("gana") in ("local", "visitante") and (fin["periodo"] or 0) >= 3:
            return "mejor" if (c["gana"] == "local") == (lado_m == 0) else "peor"
        return None

    def _como_va(self, fase: str, mejor: str, peor: str, piernas: list[dict], estados: dict, vuelta: dict | None,
                 decidida: bool, ganador: str | None, gm: int, gp: int) -> dict:
        """`momento`, `avanza_ahora`, `motivo_ahora`, `le_falta` y `texto` de una serie (en_juego.situacion_serie)."""
        from produccion import en_juego as EJ
        e1, e2 = estados.get(1, "programado"), estados.get(2, "programado")
        tanda = (None, None)
        if decidida or e2 == "final":
            momento = "terminada"
        elif e2 in ESTADOS_ACTIVOS and vuelta is not None:
            per = vuelta.get("periodo") or 0
            pausa_90 = vuelta["estado"] == "descanso" and per == 2 and (vuelta.get("minuto") or 0) >= 90
            momento = "penales" if per >= 5 else "tiempos_extra" if (per >= 3 or (pausa_90 and fase == "final")) else "vuelta"
        elif e1 == "final":
            momento = "entre"
        elif e1 in ESTADOS_ACTIVOS:
            momento = "ida"
        else:
            momento = "por_jugar"
        if vuelta is not None and vuelta.get("penales"):
            pen = vuelta["penales"]
            tanda = (pen["l"], pen["v"]) if vuelta["local"] == mejor else (pen["v"], pen["l"])
        sit = EJ.situacion_serie(fase, gm, gp, momento, tanda[0], tanda[1])
        nombre = {"mejor": mejor, "peor": peor}
        avanza = ganador if decidida else nombre.get(sit["avanza_ahora"])
        if momento == "terminada" and not decidida:
            avanza = None
        return {"momento": momento, "avanza_ahora": avanza, "motivo_ahora": sit["motivo_ahora"], "le_falta": sit["le_falta"],
                "texto": _texto_serie(fase, mejor, peor, momento, gm, gp, sit, avanza, piernas, tanda, vuelta)}

    def _siguiente(self, ctx: dict, partidos: list[dict], ahora: dt.datetime) -> dict | None:
        """El próximo partido que no ha empezado: de hoy si queda alguno; si no, del calendario previo."""
        cand = [{"id": p["id"], "inicio_utc": p["inicio_utc"], "local": p["local"], "visitante": p["visitante"]}
                for p in partidos if p["estado"] == "programado"]
        if not cand:
            hoy = {p["id"] for p in partidos}
            cand = [f for f in ctx["futuros"] if f["id"] not in hoy and f.get("inicio_utc") and de_iso(f["inicio_utc"]) > ahora]
        return min(cand, key=lambda f: (f["inicio_utc"], f["id"])) if cand else None


def _resumen_sim(sim: dict, completo: bool = True) -> dict:
    """Lo que se usa de `simulador.simular`: P(clasifica) y P(campeón) por equipo, tabla y metadatos."""
    out = {"p": {d["equipo"]: (float(d["p_clasifica"]), float(d["p_campeon"])) for d in sim["por_equipo"]},
           "n_sim": sim["meta"]["n_sim"], "torneo": sim["meta"]["torneo"], "regular_completa": sim["meta"]["regular_completa"],
           "clasifican": sim["meta"]["clasifican"], "en_juego": sim["meta"].get("en_juego", []), "tabla": sim["tabla_actual"]}
    if completo and sim["meta"]["regular_completa"]:
        out["completo"] = sim                                      # para armar la liguilla al corte (`repetir`)
    return out


def _goles(n: int) -> str:
    return "un gol" if n == 1 else f"{n} goles"


def _le_faltan(n: int) -> str:
    return f"le {'falta' if n == 1 else 'faltan'} {_goles(n)}"


def _may(s: str) -> str:
    return s[:1].upper() + s[1:]


def _global(mejor: str, peor: str, gm: int, gp: int) -> str:
    """«global 3-3» o «global Tigres 4-3 Chivas» (primero el que va arriba)."""
    if gm == gp:
        return f"global {gm}-{gp}"
    return f"global {mejor} {gm}-{gp} {peor}" if gm > gp else f"global {peor} {gp}-{gm} {mejor}"


def _texto_serie(fase: str, mejor: str, peor: str, momento: str, gm: int, gp: int, sit: dict, avanza: str | None,
                 piernas: list[dict], tanda: tuple, vuelta: dict | None) -> str:
    """Una línea en español de cómo va la serie (la página la muestra tal cual; JavaScript no calcula nada)."""
    final = fase == "final"
    p1 = next((d for d in piernas if d["pierna"] == 1), None)
    p2 = next((d for d in piernas if d["pierna"] == 2), None)
    casa_vuelta = p2["local"] if p2 else mejor
    regla = ("con el global empatado hay tiempos extra y, si sigue el empate, penales" if final
             else f"con el global empatado avanza {mejor} por su mejor lugar en la tabla")
    falta = sit.get("le_falta") or {}
    if momento == "por_jugar":
        return f"Serie por jugar: la ida es en casa de {p1['local'] if p1 else peor} y la vuelta en casa de {casa_vuelta}; {regla}."
    if momento in ("ida", "entre"):
        marc = f"{p1['local']} {p1['gl']}-{p1['gv']} {p1['visitante']}" if p1 and p1.get("gl") is not None else "por jugar"
        return f"{'Ida en juego' if momento == 'ida' else 'Ida'}: {marc}. Falta la vuelta en casa de {casa_vuelta}; {regla}."
    g = _global(mejor, peor, gm, gp)
    otro = None if avanza is None else (peor if avanza == mejor else mejor)
    n = abs(gm - gp)
    if momento == "vuelta":
        if not final:
            if sit["motivo_ahora"] == "mejor_sembrado":
                return f"{_may(g)}: si termina así, avanza {mejor} por su mejor lugar en la tabla. A {peor} le falta un gol."
            k = falta.get("peor" if avanza == mejor else "mejor", n)
            cola = " (con el empate global le alcanza, por su mejor lugar en la tabla)" if otro == mejor else ""
            return f"{_may(g)}: si termina así, avanza {avanza}. A {otro} {_le_faltan(k)}{cola}."
        if avanza is None:
            return f"{_may(g)}: si termina así, habrá tiempos extra y, si sigue el empate, penales."
        return f"{_may(g)}: si termina así, {avanza} es campeón. A {otro} {_le_faltan(n)} para empatar el global y llevar la final a tiempos extra."
    if momento == "tiempos_extra":
        if avanza is None:
            return f"Tiempos extra, {g}: si termina así, se define en penales."
        return f"Tiempos extra, {g}: si termina así, {avanza} es campeón. A {otro} {_le_faltan(n)} para llevarla a penales."
    if momento == "penales":
        t = ""
        if vuelta is not None and vuelta.get("penales"):
            t = f": {vuelta['local']} {vuelta['penales']['l']}-{vuelta['penales']['v']} {vuelta['visitante']} en la tanda"
        return f"Se define en penales ({g}){t}."
    if avanza is None:                                             # terminada, sin ganador confirmado
        return f"Terminó la vuelta, {g}: falta que ESPN confirme quién ganó."
    if not final:
        return f"Avanza {avanza}: {g}, por su mejor lugar en la tabla." if gm == gp else f"Avanza {avanza}: {g}."
    if gm == gp:
        t = f" ({max(tanda)}-{min(tanda)})" if None not in tanda else ""
        return f"{avanza} es campeón en penales{t} tras empatar {gm}-{gp} el global."
    et = " en tiempos extra" if vuelta is not None and (vuelta.get("periodo") or 0) >= 3 else ""
    return f"{avanza} es campeón{et}: {g}."


def _proyeccion_previa(ctx: dict, n_sim: int, nota: str | None) -> dict:
    """Proyección sin cambios: la del último pronóstico previo, con delta 0."""
    cl = [{"equipo": e, "p": _r4(p), "delta": 0.0} for e, p in ctx["p_clasifica"].items() if 0.0005 < p < 0.9995]
    ca = [{"equipo": e, "p": _r4(p), "delta": 0.0} for e, p in ctx["p_campeon"].items() if p >= 0.0005]
    out = {"n_sim": ctx.get("n_sim"), "clasifica": sorted(cl, key=lambda d: (-d["p"], d["equipo"])),
           "campeon": sorted(ca, key=lambda d: (-d["p"], d["equipo"])), "ruido": RUIDO_DELTA, "partidos_considerados": []}
    if nota:
        out["nota"] = nota
    return out


# ==================================================================================================
# Eventos notificables
# ==================================================================================================
def _etapa(p: dict) -> int:
    """0 programado · 1 primer tiempo · 2 descanso · 3 segundo tiempo · 4 pausa tras los 90 · 5 tiempos extra · 6 penales · 7 final."""
    e, per, m = p["estado"], p.get("periodo") or 0, p.get("minuto") or 0
    if e == "pospuesto":
        return -1
    if e == "programado":
        return 0
    if e == "final":
        return 7
    if per >= 5:
        return 6
    if per >= 3:
        return 5
    if e == "descanso":
        return 4 if (per == 2 and m >= 90) else 2
    return 3 if per == 2 else 1


def _marcador(p: dict) -> str:
    return f"{p['local']} {p['gl'] or 0}-{p['gv'] or 0} {p['visitante']}"


def _min(e: dict) -> str:
    if e.get("min") is None:
        return ""
    return f" ({e['min']}'+{e['anadido']}')" if e.get("anadido") else f" ({e['min']}')"


def _con_global(p: dict, gl=None, gv=None) -> str:
    """« (global 2-4)» en el orden local-visitante del partido si es una vuelta con la ida ya jugada; si no, «»."""
    s = p.get("serie") or {}
    ida = s.get("ida")
    if s.get("pierna") != 2 or not ida or ida.get("gl") is None:
        return ""
    gl = p["gl"] if gl is None else gl
    gv = p["gv"] if gv is None else gv
    if gl is None or gv is None:
        return ""
    de = {ida["local"]: ida["gl"], ida["visitante"]: ida["gv"]}
    if p["local"] not in de or p["visitante"] not in de:
        return ""
    return f" (global {int(gl) + de[p['local']]}-{int(gv) + de[p['visitante']]})"


def detectar_eventos(previos: dict, nuevos: list[dict]) -> list[dict]:
    """
    Eventos notificables entre dos fotos del día (`previos` = {id: partido del documento anterior}):
    inicio, gol, gol_anulado (el marcador bajó o se corrigió), roja, descanso, segundo_tiempo,
    tiempos_extra, penales, final y pospuesto. Un partido que no estaba en la foto anterior no genera
    eventos (no se «anuncian» de golpe cosas que pasaron antes de empezar a observar).
    """
    evs = []

    def ev(tipo, p, texto, **extra):
        evs.append({"tipo": tipo, "partido_id": p["id"], "texto": texto, "marcador": None if p["gl"] is None else f"{p['gl']}-{p['gv']}",
                    "minuto": p.get("minuto"), **extra})

    for p in nuevos:
        a = previos.get(p["id"])
        if a is None:
            continue
        ea, eb = _etapa(a), _etapa(p)
        if eb == -1:
            if ea != -1:
                ev("pospuesto", p, f"Pospuesto o suspendido: {p['local']} vs {p['visitante']}")
            continue
        if eb == 0:
            continue
        if ea <= 0:
            ev("inicio", p, f"Arranca {p['local']} vs {p['visitante']}")
        ga, gn = (a["gl"] or 0, a["gv"] or 0), (p["gl"] or 0, p["gv"] or 0)
        if gn[0] < ga[0] or gn[1] < ga[1]:
            ev("gol_anulado", p, f"Gol anulado o marcador corregido: {_marcador(p)} (antes {ga[0]}-{ga[1]})")
        goles = [e for e in p["eventos"] if e["tipo"] in TIPOS_GOL]
        rojas = [e for e in p["eventos"] if e["tipo"] == "roja"]
        nuevas = []

        def lugar(e, lista=p["eventos"]):
            return next(i for i, x in enumerate(lista) if x is e)
        for k, eq in ((0, p["local"]), (1, p["visitante"])):
            del_equipo = [e for e in goles if e["equipo"] == eq]
            for n in range(ga[k] + 1, gn[k] + 1):
                e = del_equipo[n - 1] if n <= len(del_equipo) else None
                orden = lugar(e) if e is not None else 10 ** 6 + n
                if e is not None:
                    como = " de penal" if e["tipo"] == "penal" else " (autogol)" if e["tipo"] == "autogol" else ""
                    quien = f": {e['jugador']}" if e.get("jugador") else ""
                    parcial = e["marcador"].split("-")
                    texto = (f"Gol de {eq}{como}{_min(e)}{quien}. {p['local']} {parcial[0]}-{parcial[1]} {p['visitante']}"
                             + _con_global(p, int(parcial[0]), int(parcial[1])))
                else:                                               # ESPN ya movió el marcador pero aún no publica la jugada
                    texto = f"Gol de {eq}. {_marcador(p)}{_con_global(p)}"
                nuevas.append((orden, "gol", texto))
            antes = a["rojas_l"] if k == 0 else a["rojas_v"]
            ahora_ = p["rojas_l"] if k == 0 else p["rojas_v"]
            del_equipo_r = [e for e in rojas if e["equipo"] == eq]
            for n in range((antes or 0) + 1, (ahora_ or 0) + 1):
                e = del_equipo_r[n - 1] if n <= len(del_equipo_r) else None
                quien = f": {e['jugador']}" if (e and e.get("jugador")) else ""
                orden = lugar(e) if e is not None else 10 ** 6 + 50 + n
                nuevas.append((orden, "roja", f"Expulsión en {eq}{_min(e) if e else ''}{quien}. {_marcador(p)}{_con_global(p)}"))
        for _, tipo, texto in sorted(nuevas, key=lambda t: t[0]):   # en el orden de la lista de jugadas del partido
            ev(tipo, p, texto)
        if eb != ea:
            glob = _con_global(p)
            serie = p.get("serie") or {}
            if eb == 2:
                ev("descanso", p, f"Descanso: {_marcador(p)}{glob}")
            elif eb == 3 and ea < 3:
                ev("segundo_tiempo", p, f"Arranca el segundo tiempo: {_marcador(p)}{glob}")
            elif eb in (4, 5) and ea < 4 and (eb == 5 or p.get("fase") == "final"):
                ev("tiempos_extra", p, f"Habrá tiempos extra: {_marcador(p)}{glob}")
            elif eb == 6:
                ev("penales", p, f"Se va a penales: {_marcador(p)}{glob}")
            elif eb == 7:
                pen = f" (penales {p['penales']['l']}-{p['penales']['v']})" if p.get("penales") else ""
                if serie.get("pierna") == 1:
                    texto = f"Final de la ida: {_marcador(p)}{pen}"
                elif serie.get("pierna") == 2 and serie.get("decidida") and serie.get("texto"):
                    texto = f"Final: {_marcador(p)}{pen}. {serie['texto']}"       # quién avanzó y por qué
                else:
                    texto = f"Final: {_marcador(p)}{pen}{glob}"
                ev("final", p, texto)
    return evs


def leer_eventos(ruta: Path = RUTA_EVENTOS) -> list[dict]:
    out = []
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                try:
                    d = json.loads(linea)
                    if isinstance(d, dict) and isinstance(d.get("n"), int):
                        out.append(d)
                except ValueError:
                    continue
    except OSError:
        pass
    return out


class Bitacora:
    """Eventos numerados en un archivo de líneas JSON (el número sigue al último que haya en el archivo)."""

    def __init__(self, ruta: Path = RUTA_EVENTOS, reiniciar: bool = False):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        if reiniciar and self.ruta.exists():
            self.ruta.unlink()
        previos = leer_eventos(self.ruta)
        self.n = max((e["n"] for e in previos), default=0)
        self.ultimo = next((e for e in reversed(previos) if e.get("tipo") != "refresco"), None)
        self.t_ultimo: float = 0.0                                 # reloj monótono del último evento (para el refresco)

    def anotar(self, eventos: list[dict], ahora: dt.datetime) -> list[dict]:
        out = []
        if not eventos:
            return out
        with open(self.ruta, "a", encoding="utf-8") as f:
            for e in eventos:
                self.n += 1
                d = {"n": self.n, "utc": iso(ahora), **e}
                f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
                out.append(d)
                if d["tipo"] != "refresco":
                    self.ultimo = d
            f.flush()
            os.fsync(f.fileno())
        self.t_ultimo = time.monotonic()
        return out

    def ultimo_del_dia(self, dia: dt.date) -> dict | None:
        """Último evento (que no sea refresco) del día de partido, en la forma del contrato."""
        u = self.ultimo
        t = de_iso(u["utc"]) if u else None
        if u is None or t is None or dia_de_juego(t) != dia:
            return None
        return {"utc": u["utc"], "tipo": u["tipo"], "partido_id": u.get("partido_id"), "texto": u.get("texto"), "n": u["n"]}


# ==================================================================================================
# Comandos
# ==================================================================================================
def validar_documento(doc: dict) -> list[str]:
    """Errores de forma del documento en vivo (lista vacía = cumple el contrato)."""
    err = []
    for k in ("version", "generado_utc", "estado", "partidos", "tabla", "tabla_nota", "proyeccion", "series", "ultimo_evento", "siguiente"):
        if k not in doc:
            err.append(f"falta '{k}'")
    if err:
        return err
    if doc["estado"] not in ("sin_partidos", "previo", "en_juego", "descanso", "terminado_hoy"):
        err.append(f"estado inválido: {doc['estado']}")
    for p in doc["partidos"]:
        for k in ("id", "fase", "etiqueta", "local", "visitante", "estado", "inicio_utc", "periodo", "minuto", "anadido", "reloj_utc",
                  "gl", "gv", "rojas_l", "rojas_v", "eventos", "previo", "vivo", "serie"):
            if k not in p:
                err.append(f"partido {p.get('id')}: falta '{k}'")
        if p.get("estado") not in ("programado", "en_juego", "descanso", "final", "pospuesto"):
            err.append(f"partido {p.get('id')}: estado inválido")
        for bloque in ("previo", "vivo"):
            b = p.get(bloque)
            if b:
                s = b["p_local"] + b["p_empate"] + b["p_visitante"]
                if abs(s - 1.0) > 3e-4 or min(b["p_local"], b["p_empate"], b["p_visitante"]) < 0:
                    err.append(f"partido {p.get('id')}: {bloque} no suma 1 ({s})")
        for e in p.get("eventos") or []:
            if e.get("tipo") not in ("gol", "penal", "autogol", "roja"):
                err.append(f"partido {p.get('id')}: evento de tipo inválido")
    for s in doc["series"]:
        if s.get("momento") not in (None, "por_jugar", "ida", "entre", "vuelta", "tiempos_extra", "penales", "terminada"):
            err.append(f"serie {s.get('llave')}: momento inválido")
        equipos = {(s.get("mejor") or {}).get("equipo"), (s.get("peor") or {}).get("equipo")}
        if s.get("avanza_ahora") is not None and s["avanza_ahora"] not in equipos:
            err.append(f"serie {s.get('llave')}: avanza_ahora no es de la serie")
        if s.get("decidida") and s.get("ganador") not in equipos:
            err.append(f"serie {s.get('llave')}: decidida sin ganador de la serie")
        if not (0.0 <= float(s.get("p_avanza_mejor", 0.0)) <= 1.0):
            err.append(f"serie {s.get('llave')}: p_avanza_mejor fuera de rango")
    if doc["tabla"] and [f["pos"] for f in doc["tabla"]] != list(range(1, len(doc["tabla"]) + 1)):
        err.append("posiciones de la tabla no consecutivas")
    for llave in ("clasifica", "campeon"):
        for d in doc["proyeccion"].get(llave) or []:
            if not (0.0 <= d["p"] <= 1.0):
                err.append(f"proyeccion.{llave}: probabilidad fuera de rango para {d['equipo']}")
    peso = len(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if peso >= PESO_MAXIMO:
        err.append(f"el documento pesa {peso} bytes (máximo {PESO_MAXIMO})")
    return err


def una_vez(motor: Motor | None = None, ahora: dt.datetime | None = None, salida: Path | None = RUTA_VIVO,
            bitacora: Bitacora | None = None) -> dict:
    """Un ciclo: consulta ESPN, arma el documento y lo escribe. Lanza ErrorRed si ESPN no responde."""
    motor = motor or Motor()
    ahora = ahora or ahora_utc()
    crudas, avisos = leer_hoy(ahora, motor.pedir)
    ult = None
    try:
        ult = (bitacora or Bitacora()).ultimo_del_dia(dia_de_juego(ahora))
    except OSError:
        pass
    doc = motor.documento(crudas, ahora, ultimo_evento=ult, avisos=avisos)
    if salida is not None:
        escribir_json(doc, salida)
    if motor.reajustar and doc["estado"] not in ESTADOS_ACTIVOS:   # nunca a medio partido: `observar` no reajusta
        try:
            from produccion import en_juego as EJ
            EJ.leer_parametros()                                   # reajusta sólo si cambiaron los datos (firma por contenido)
        except Exception as e:
            log(f"aviso: no se revisaron los parámetros en juego: {type(e).__name__}: {e}")
    return doc


def _candado(ruta: Path = RUTA_CANDADO):
    """Candado exclusivo de `observar` (None si ya hay otro corriendo). Se suelta al cerrar el archivo o morir el proceso."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    f = open(ruta, "a+", encoding="utf-8")
    for intento in range(4):                                       # `esperar` y `estado` lo prueban un instante con LOCK_SH
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            if intento < 3:
                time.sleep(0.15)
    f.close()
    return None


def observador_activo(ruta: Path = RUTA_CANDADO) -> bool:
    """¿Hay un `observar` vivo? (prueba si el candado está tomado)."""
    try:
        f = open(ruta, "a+", encoding="utf-8")
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        f.close()
    return False


def _latido(f, datos_: dict) -> None:
    try:
        f.seek(0)
        f.truncate()
        f.write(json.dumps(datos_, ensure_ascii=False))
        f.flush()
    except OSError:
        pass


def observar(hasta: dt.datetime | None = None, motor: Motor | None = None, salida: Path = RUTA_VIVO,
             ruta_eventos: Path = RUTA_EVENTOS, ruta_candado: Path = RUTA_CANDADO, dormir=time.sleep,
             reloj=ahora_utc, max_ciclos: int | None = None) -> int:
    """
    Bucle del día de partido: repite el ciclo cada SEG_ACTIVO segundos si hay partido en juego o falta
    menos de MIN_ANTES minutos para uno, y cada SEG_REPOSO si no; anota cada evento notificable; termina
    cuando todos los partidos del día llevan MIN_TRAS_FINAL minutos finalizados, cuando no hay partidos
    hoy, o al llegar `hasta`. Nunca muere por una respuesta mala de ESPN. Devuelve 0 (2 si ya hay otro).
    """
    candado = _candado(ruta_candado)
    if candado is None:
        log("ya hay un `observar` corriendo (candado tomado): no se arranca otro")
        return 2
    try:
        motor = motor or Motor()
        bit = Bitacora(ruta_eventos)
        bit.t_ultimo = time.monotonic()
        inicio = reloj()
        dia0 = dia_de_juego(inicio)
        previos: dict[int, dict] = {}
        viejo = leer_json(salida)                                 # si se reinicia a medio día no se repiten avisos
        if viejo and not viejo.get("prueba") and viejo.get("dia") == str(dia0):
            previos = {p["id"]: p for p in viejo.get("partidos") or []}
        t_final: dict[int, dt.datetime] = {}
        # `primero`: al arrancar (o relanzar a medio partido) siempre sale un «refresco» si hay algo en juego y nada
        # que avisar, para que la sesión copie el estado aunque alguien haya pisado vivo.json mientras tanto
        fallos, ciclos, primero, menos, vacios = 0, 0, True, 0, 0
        log(f"observar: día {dia0}, eventos desde el número {bit.n + 1}" + (f", hasta {iso(hasta)}" if hasta else ""))
        while True:
            ahora = reloj()
            if hasta is not None and ahora >= hasta:
                log("observar: se llegó a --hasta")
                return 0
            if dia_de_juego(ahora) != dia0:
                log("observar: cambió el día de partido")
                return 0
            espera = SEG_REPOSO
            try:
                crudas, avisos = leer_hoy(ahora, motor.pedir)
                # una respuesta con menos partidos que la anterior (lista vacía, evento ilegible) es casi siempre un
                # tropiezo de ESPN: no se escribe ni se da por cierta hasta que se repite varias consultas seguidas
                faltan = [a for i, a in previos.items() if i not in {c["id"] for c in crudas}]
                if faltan:
                    menos += 1
                    tope = CONFIRMAR_MENOS_ACTIVO if any(a.get("estado") in ESTADOS_ACTIVOS for a in faltan) else CONFIRMAR_MENOS
                    if menos < tope:
                        raise ErrorRed(f"ESPN devolvió {len(crudas)} partidos de hoy y antes había {len(previos)} "
                                       f"(falta {', '.join(str(a.get('local')) + '-' + str(a.get('visitante')) for a in faltan)}; "
                                       f"consulta {menos} de {tope} antes de creerlo)")
                    log(f"observar: ESPN ya no lista {len(faltan)} partido(s) de hoy tras {menos} consultas; se acepta")
                menos = 0
                doc = motor.documento(crudas, ahora, ultimo_evento=bit.ultimo_del_dia(dia0), avisos=avisos)
                evs = detectar_eventos(previos, doc["partidos"])
                activos = [p for p in doc["partidos"] if p["estado"] in ESTADOS_ACTIVOS]
                if activos and not evs and (primero or time.monotonic() - bit.t_ultimo >= MIN_REFRESCO * 60):
                    evs = [{"tipo": "refresco", "partido_id": None, "marcador": None, "minuto": None,
                            "texto": "Refresco: " + "; ".join(f"{_marcador(p)} ({'descanso' if p['estado'] == 'descanso' else str(p['minuto']) + chr(39)})"
                                                               for p in activos)}]
                primero = False
                if evs:
                    doc["ultimo_evento"] = None                    # se rellena tras numerarlos
                nuevos = bit.anotar(evs, ahora)
                if nuevos:
                    doc["ultimo_evento"] = bit.ultimo_del_dia(dia0)
                    for e in nuevos:
                        log(f"evento {e['n']} [{e['tipo']}] {e['texto']}")
                escribir_json(doc, salida)                         # primero el documento, luego ya se puede avisar
                previos = {p["id"]: p for p in doc["partidos"]}
                fallos = 0
                for p in doc["partidos"]:
                    if p["estado"] in ("final", "pospuesto"):
                        viejo_final = de_iso(p["inicio_utc"]) + dt.timedelta(hours=3) < ahora
                        t_final.setdefault(p["id"], ahora - dt.timedelta(minutes=MIN_TRAS_FINAL) if (viejo_final and ciclos == 0) else ahora)
                    else:
                        t_final.pop(p["id"], None)
                _latido(candado, {"pid": os.getpid(), "inicio_utc": iso(inicio), "ultimo_ciclo_utc": iso(ahora),
                                  "latido": time.time(), "estado": doc["estado"], "partidos": len(doc["partidos"]),
                                  "ultimo_evento_n": bit.n})
                if not doc["partidos"]:
                    vacios += 1
                    if vacios >= 2:                                # dos consultas seguidas sin partidos: se le cree
                        log("observar: hoy no hay partidos; termina")
                        return 0
                    raise ErrorRed("ESPN dice que hoy no hay partidos; se confirma en la siguiente consulta")
                vacios = 0
                if all(p["id"] in t_final and (ahora - t_final[p["id"]]) >= dt.timedelta(minutes=MIN_TRAS_FINAL)
                       for p in doc["partidos"]):
                    log("observar: todos los partidos de hoy llevan 10 minutos finalizados; termina")
                    return 0
                pronto = any(p["estado"] == "programado" and de_iso(p["inicio_utc"]) - ahora <= dt.timedelta(minutes=MIN_ANTES)
                             for p in doc["partidos"])
                cierre = all(p["id"] in t_final for p in doc["partidos"])      # sólo falta que pasen los 10 minutos
                espera = SEG_ACTIVO if (activos or pronto) else (60 if cierre else SEG_REPOSO)
            except ErrorRed as e:
                fallos += 1
                espera = min(SEG_REPOSO, SEG_ACTIVO * fallos)
                log(f"observar: ESPN no respondió ({e}); reintento en {espera} s (fallo {fallos} seguido)")
            except Exception as e:                                 # nada tumba el bucle
                fallos += 1
                espera = min(SEG_REPOSO, SEG_ACTIVO * fallos)
                log(f"observar: error {type(e).__name__}: {e}; reintento en {espera} s")
                traceback.print_exc()
            if fallos:                                             # el latido dice que el proceso sigue vivo aunque ESPN falle
                _latido(candado, {"pid": os.getpid(), "inicio_utc": iso(inicio), "ultimo_ciclo_utc": None, "latido": time.time(),
                                  "fallos": fallos, "ultimo_evento_n": bit.n})
            ciclos += 1
            if max_ciclos is not None and ciclos >= max_ciclos:
                return 0
            if hasta is not None:
                espera = max(1.0, min(espera, (hasta - reloj()).total_seconds()))
            dormir(espera)
    finally:
        try:
            fcntl.flock(candado, fcntl.LOCK_UN)
        finally:
            candado.close()


def _latido_viejo(ruta_candado: Path, limite: float = SEG_LATIDO_VIEJO) -> dict | None:
    """Latido de `observar` si tiene más de `limite` segundos (proceso colgado); None si es reciente o no se puede saber."""
    try:
        d = json.loads(Path(ruta_candado).read_text(encoding="utf-8") or "null")
        t = float(d["latido"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return d if time.time() - t > limite else None


def esperar(desde: int, max_seg: float = 6600.0, ruta_eventos: Path = RUTA_EVENTOS, ruta_candado: Path = RUTA_CANDADO,
            pausa: float = 2.0, salida=None, agrupar: float = SEG_AGRUPAR, limite_latido: float = SEG_LATIDO_VIEJO) -> int:
    """
    Sale con 0 imprimiendo en UNA línea el primer evento con número > `desde` (más `pendientes`: cuántos
    eventos más hay después de ése, `ultimo_n` y `tipos`); con 3 si `observar` ya no corre y no hay más
    eventos; con 4 si se agotó `max_seg`; con 5 si `observar` tiene el candado pero su latido es viejo
    (colgado: hay que matarlo y relanzarlo). Un gol, un gol anulado o una roja salen de inmediato; con
    cualquier otro evento espera `agrupar` segundos por si llega otro (así dos descansos o dos finales
    casi simultáneos son un solo aviso).
    """
    salida = salida or sys.stdout
    t0 = time.monotonic()
    t_primero = None

    def nuevos():
        return [e for e in leer_eventos(ruta_eventos) if e["n"] > desde]

    def entregar(evs):
        print(json.dumps({**evs[0], "pendientes": len(evs) - 1, "ultimo_n": evs[-1]["n"], "tipos": [e.get("tipo") for e in evs]},
                         ensure_ascii=False, separators=(",", ":")), file=salida, flush=True)
        return 0

    while True:
        evs = nuevos()
        activo = observador_activo(ruta_candado)
        if not evs and not activo:
            evs = nuevos()                                        # pudo anotar justo antes de terminar
            if not evs:
                ult = max((e["n"] for e in leer_eventos(ruta_eventos)), default=0)
                print(json.dumps({"terminado": True, "desde": desde, "ultimo_n": ult}, ensure_ascii=False), file=salida, flush=True)
                return 3
        if evs:
            t_primero = t_primero if t_primero is not None else time.monotonic()
            if (not activo or any(e.get("tipo") in TIPOS_URGENTES for e in evs)
                    or time.monotonic() - t_primero >= agrupar):
                return entregar(evs)
        elif activo:
            viejo = _latido_viejo(ruta_candado, limite_latido)
            if viejo is not None:
                print(json.dumps({"colgado": True, "desde": desde, "pid": viejo.get("pid"),
                                  "segundos_sin_latido": round(time.time() - float(viejo["latido"]))}, ensure_ascii=False),
                      file=salida, flush=True)
                return 5
        if time.monotonic() - t0 >= max_seg:
            if evs:
                return entregar(evs)
            print(json.dumps({"agotado": True, "desde": desde, "segundos": round(time.monotonic() - t0)}, ensure_ascii=False),
                  file=salida, flush=True)
            return 4
        time.sleep(pausa)


def guion_de_partido(fila, goles, tarjetas, paso_min: int = 5) -> list[tuple[float, dict]]:
    """
    Secuencia de fotos «crudas» de un partido ya jugado, como las habría dado ESPN: [(segundos desde el
    silbatazo, cruda)]. Hay una foto antes de empezar, una en cada gol y expulsión (datos/goles.csv y
    tarjetas.csv), una cada `paso_min` minutos de juego, el descanso, el arranque del segundo tiempo y el
    final. Sólo el tiempo reglamentario. El descanso dura 15 minutos y el agregado es el de la última
    jugada registrada (mínimo 2 y 4 minutos).
    """
    pid, local, visitante = int(fila["id"]), fila["local"], fila["visitante"]
    inicio = fila["fecha_utc"].to_pydatetime()
    jug = []
    for r in goles.itertuples(index=False):
        if r.periodo <= 2:
            jug.append({"clase": "gol", "tipo": r.tipo if r.tipo in TIPOS_GOL else "gol", "lado": 0 if r.equipo == local else 1,
                        "periodo": int(r.periodo), "min": int(r.minuto), "anadido": int(r.anadido) or None,
                        "jugador": r.jugador if isinstance(r.jugador, str) else "", "jid": ""})
    for r in tarjetas.itertuples(index=False):
        if r.periodo <= 2 and r.tipo in ("roja", "segunda_amarilla"):
            jug.append({"clase": "roja", "tipo": "roja", "lado": 0 if r.equipo == local else 1, "periodo": int(r.periodo),
                        "min": int(r.minuto), "anadido": int(r.anadido) or None,
                        "jugador": r.jugador if isinstance(r.jugador, str) else "", "jid": ""})
    for j in jug:                                                  # registros viejos: 47' del primer tiempo = 45'+2'
        tope = 45 if j["periodo"] == 1 else 90
        if j["min"] > tope:
            j["min"], j["anadido"] = tope, (j["min"] - tope) + (j["anadido"] or 0)
    a1 = max([j["anadido"] or 0 for j in jug if j["periodo"] == 1] + [2])
    a2 = max([j["anadido"] or 0 for j in jug if j["periodo"] == 2] + [4])
    ini2 = (45 + a1 + 15) * 60.0

    def seg_juego(periodo, minuto, anadido):                       # segundos de reloj de partido (como status.clock)
        return (minuto + (anadido or 0)) * 60.0 - 20.0

    def t_real(periodo, minuto, anadido):
        s = seg_juego(periodo, minuto, anadido)
        return s if periodo == 1 else ini2 + (s - 45 * 60.0)

    for j in jug:
        j["seg"] = seg_juego(j["periodo"], j["min"], j["anadido"])
        j["t"] = t_real(j["periodo"], j["min"], j["anadido"])
    jug.sort(key=lambda j: (j["t"], j["clase"] != "gol"))

    def foto(t, estado, periodo, minuto, anadido, segundos):
        hechas = [dict(j) for j in jug if j["t"] <= t] if estado != "programado" else []
        gl = sum(1 for j in hechas if j["clase"] == "gol" and j["lado"] == 0)
        gv = sum(1 for j in hechas if j["clase"] == "gol" and j["lado"] == 1)
        return (t, {"id": pid, "inicio": inicio, "local": local, "visitante": visitante, "estado": estado,
                    "estado_espn": "REPETICION", "periodo": periodo, "minuto": minuto, "anadido": anadido, "segundos": segundos,
                    "gl": gl if estado != "programado" else None, "gv": gv if estado != "programado" else None,
                    "tanda_l": None, "tanda_v": None, "gana": None, "pierna": None, "slug": None,
                    "medio_tiempo": estado == "descanso", "jugadas": hechas})

    fotos = [foto(-60.0, "programado", 0, None, None, 0.0), foto(5.0, "en_juego", 1, 1, None, 5.0)]
    for m in range(paso_min, 46, paso_min):
        fotos.append(foto(m * 60.0 - 30.0, "en_juego", 1, m, None, m * 60.0 - 30.0))
    for j in jug:
        fotos.append(foto(j["t"] + 1.0, "en_juego", j["periodo"], j["min"], j["anadido"], j["seg"] + 1.0))
    fotos.append(foto((45 + a1) * 60.0, "descanso", 1, 45, None, 45 * 60.0))
    fotos.append(foto(ini2 + 5.0, "en_juego", 2, 46, None, 45 * 60.0 + 5.0))
    for m in range(45 + paso_min, 91, paso_min):
        fotos.append(foto(ini2 + (m - 45) * 60.0 - 30.0, "en_juego", 2, m, None, m * 60.0 - 30.0))
    fin = ini2 + (45 + a2) * 60.0
    fotos.append(foto(fin, "final", 2, 90, a2, 90 * 60.0))
    fotos.sort(key=lambda f: f[0])
    return fotos


def repetir(pid: int, velocidad: float = 60.0, salida: Path | None = None, ruta_eventos: Path | None = None,
            n_sim: int = N_SIM, proyectar: bool = True, pron=None, df=None, paso_min: int = 5, dormir=time.sleep,
            reloj=ahora_utc, sellos: dict | None = None) -> dict:
    """
    Reproduce un partido YA jugado: genera la misma secuencia de documentos y de eventos que habría dado
    `observar` ese día, con el contexto de entonces (tabla y pronóstico previo al corte del silbatazo).
    `velocidad` = segundos de partido por segundo real (0 = sin pausas). Los documentos llevan
    "prueba": true y van a `salida` (por omisión salidas/vivo_prueba.json); los eventos, a un archivo
    aparte que se reinicia en cada corrida (<salida>_eventos.jsonl). Mientras corre mantiene su propio
    candado (<salida>.lock) para que `esperar --eventos ... --candado ...` funcione igual que con `observar`.
    """
    from modelo import datos
    df = datos.cargar() if df is None else df
    sel = df[df["id"] == int(pid)]
    if sel.empty:
        raise ValueError(f"no existe el partido {pid} en datos/partidos.csv")
    fila = sel.iloc[0]
    if fila["estado"] != "jugado":
        raise ValueError(f"el partido {pid} no está jugado (estado: {fila['estado']})")
    salida = Path(salida or (SALIDAS / "vivo_prueba.json"))
    ruta_eventos = Path(ruta_eventos or salida.with_name(salida.stem + "_eventos.jsonl"))
    g = datos.tabla("goles"); g = g[g["partido_id"] == int(pid)]
    t = datos.tabla("tarjetas"); t = t[t["partido_id"] == int(pid)]
    inicio = fila["fecha_utc"].to_pydatetime()
    corte = inicio - dt.timedelta(minutes=1)
    if pron is None and proyectar:
        import pandas as pd
        from produccion import obtener_pronosticador
        pron = obtener_pronosticador(pd.Timestamp(corte))
    if pron is None:                                               # sin proyección: pronosticador ligero para el previo
        from produccion.pronosticador_provisional import Pronosticador
        pron = Pronosticador(corte=corte, partidos=df)
    candado = _candado(salida.with_suffix(".lock"))
    if candado is None:
        raise RuntimeError(f"ya hay una repetición corriendo con la salida {salida}")
    try:
        motor = Motor(n_sim=n_sim, proyectar=proyectar, pron=pron, df=df, corte=corte, sellos=sellos)
        bit = Bitacora(ruta_eventos, reiniciar=True)
        fotos = guion_de_partido(fila, g, t, paso_min)
        previos: dict[int, dict] = {}
        n_docs, avisos_et = 0, []
        if (g["periodo"] > 2).any():
            avisos_et = ["El partido tuvo tiempos extra: la repetición sólo cubre los 90 minutos."]
        doc = {}
        motor.contexto(inicio)                                     # lo pesado (simulación base) antes de echar a andar el reloj
        t0 = time.monotonic()
        for seg, cruda in fotos:
            if velocidad and velocidad > 0:
                falta = (seg - fotos[0][0]) / velocidad - (time.monotonic() - t0)
                if falta > 0:
                    dormir(falta)
            ahora = reloj()
            doc = motor.documento([cruda], ahora, ahora_juego=inicio + dt.timedelta(seconds=max(seg, 0.0)),
                                  ultimo_evento=bit.ultimo_del_dia(dia_de_juego(ahora)), avisos=list(avisos_et), prueba=True)
            nuevos = bit.anotar(detectar_eventos(previos, doc["partidos"]), ahora)
            if nuevos:
                doc["ultimo_evento"] = bit.ultimo_del_dia(dia_de_juego(ahora))
                for e in nuevos:
                    log(f"evento {e['n']} [{e['tipo']}] {e['texto']}")
            escribir_json(doc, salida)
            previos = {p["id"]: p for p in doc["partidos"]}
            n_docs += 1
    finally:
        candado.close()
    return {"partido": f"{fila['local']} {int(fila['gl'])}-{int(fila['gv'])} {fila['visitante']}", "id": int(pid),
            "documentos": n_docs, "eventos": bit.n, "salida": str(salida), "eventos_en": str(ruta_eventos),
            "segundos": round(time.monotonic() - t0, 1), "ultimo": doc}


def plan(horas: float = 48.0, ahora: dt.datetime | None = None, pedir=None) -> dict:
    """Próximos inicios en las siguientes `horas` (ESPN; si no responde, el calendario de actual.json)."""
    ahora = ahora or ahora_utc()
    fin = ahora + dt.timedelta(hours=horas)
    ctx = contexto_de_actual(leer_json(RUTA_ACTUAL))
    out = {"generado_utc": iso(ahora), "horas": horas, "fuente": "ESPN", "partidos": [], "siguiente": None}
    crudas, dia = {}, ahora.astimezone(ZONA_ESPN).date()
    try:
        while dia <= fin.astimezone(ZONA_ESPN).date():
            for c in leer_dia(dia, pedir):
                crudas[c["id"]] = c
            dia += dt.timedelta(days=1)
        lista = [{"id": c["id"], "inicio": c["inicio"], "local": c["local"], "visitante": c["visitante"], "estado": c["estado"],
                  "slug": c.get("slug"), "pierna": c.get("pierna")}
                 for c in crudas.values() if c["estado"] in ("programado", "en_juego", "descanso")]
    except ErrorRed as e:
        out["fuente"] = f"actual.json (ESPN no respondió: {e})"
        lista = [{"id": f["id"], "inicio": de_iso(f["inicio_utc"]), "local": f["local"], "visitante": f["visitante"], "estado": "programado"}
                 for f in ctx["futuros"] if f.get("inicio_utc")]
    for d in sorted(lista, key=lambda d: (d["inicio"], d["id"])):
        if d["estado"] == "programado" and not (ahora <= d["inicio"] <= fin):
            continue
        loc = d["inicio"].astimezone(ZONA)
        info = ctx["partidos"].get(d["id"]) or ctx["por_equipos"].get((d["local"], d["visitante"])) or {}
        fase, etiqueta = info.get("fase"), info.get("etiqueta")
        if not fase and d.get("slug"):                             # ESPN ya lo lista y actual.json todavía no: fase del slug
            _tablas_espn()
            fase = _FASE_SLUG(d["slug"]) if _FASE_SLUG else None
        if not etiqueta and fase and fase != "regular":
            etiqueta = NOMBRE_FASE.get(fase, str(fase).capitalize()) + (
                f", {'ida' if d.get('pierna') == 1 else 'vuelta'}" if d.get("pierna") in (1, 2) else "")
        out["partidos"].append({"id": d["id"], "inicio_utc": iso(d["inicio"]), "inicio_mexico": loc.strftime("%Y-%m-%d %H:%M"),
                                "observar_desde_utc": iso(d["inicio"] - dt.timedelta(minutes=MIN_ANTES)),
                                "local": d["local"], "visitante": d["visitante"], "estado": d["estado"],
                                "fase": fase, "etiqueta": etiqueta})
    fut = [f for f in ctx["futuros"] if f.get("inicio_utc") and de_iso(f["inicio_utc"]) > ahora]
    if fut:
        s = min(fut, key=lambda f: f["inicio_utc"])
        out["siguiente"] = {**s, "inicio_mexico": de_iso(s["inicio_utc"]).astimezone(ZONA).strftime("%Y-%m-%d %H:%M")}
    return out


def estado() -> dict:
    """¿Corre `observar`?, su último latido, el último evento y la edad de salidas/vivo.json."""
    latido = None
    try:
        latido = json.loads(RUTA_CANDADO.read_text(encoding="utf-8") or "null")
    except (OSError, ValueError):
        pass
    evs = leer_eventos()
    doc = leer_json(RUTA_VIVO) or {}
    activo = observador_activo()
    return {"observar_activo": activo, "observar_colgado": bool(activo and _latido_viejo(RUTA_CANDADO)), "latido": latido,
            "eventos": len(evs),
            "ultimo_n": max((e["n"] for e in evs), default=0), "ultimo_evento": evs[-1] if evs else None,
            "vivo": {"generado_utc": doc.get("generado_utc"), "vence_utc": doc.get("vence_utc"), "estado": doc.get("estado"),
                     "partidos": len(doc.get("partidos") or [])}}


def _resumen(doc: dict, peso: int | None = None) -> dict:
    return {"estado": doc["estado"], "dia": doc.get("dia"), "generado_utc": doc["generado_utc"],
            "partidos": [f"{p['local']} {'' if p['gl'] is None else str(p['gl']) + '-' + str(p['gv'])} {p['visitante']} [{p['estado']}"
                         + (f" {p['minuto']}'" if p["estado"] == "en_juego" else "") + "]" for p in doc["partidos"]],
            "siguiente": doc.get("siguiente"), "ultimo_evento": doc.get("ultimo_evento"), "avisos": doc.get("avisos", []),
            "bytes": peso}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cerebro Liga MX · motor en vivo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("una-vez", help="consulta ESPN una vez y escribe salidas/vivo.json")
    s.add_argument("--salida", default=str(RUTA_VIVO))
    s.add_argument("--n-sim", type=int, default=N_SIM)
    s.add_argument("--sin-proyeccion", action="store_true", help="no recalcula clasificación ni campeón")
    s = sub.add_parser("observar", help="bucle del día de partido")
    s.add_argument("--hasta", default=None, help="AAAA-MM-DDTHH:MM (hora de México) o con Z para UTC")
    s.add_argument("--n-sim", type=int, default=N_SIM)
    s.add_argument("--sin-proyeccion", action="store_true")
    s = sub.add_parser("esperar", help="espera al siguiente evento")
    s.add_argument("--desde", type=int, required=True)
    s.add_argument("--max-seg", type=float, default=6600.0)
    s.add_argument("--agrupar", type=float, default=SEG_AGRUPAR, help="segundos que espera un evento que no es gol ni roja por si llega otro")
    s.add_argument("--eventos", default=str(RUTA_EVENTOS), help="archivo de eventos (el de una repetición: <salida>_eventos.jsonl)")
    s.add_argument("--candado", default=str(RUTA_CANDADO), help="candado del proceso que los anota (repetición: <salida>.lock)")
    s = sub.add_parser("repetir", help="reproduce un partido ya jugado")
    s.add_argument("id", type=int)
    s.add_argument("--velocidad", type=float, default=60.0, help="segundos de partido por segundo real (0 = sin pausas)")
    s.add_argument("--salida", default=str(SALIDAS / "vivo_prueba.json"))
    s.add_argument("--n-sim", type=int, default=N_SIM)
    s.add_argument("--sin-proyeccion", action="store_true")
    s = sub.add_parser("plan", help="próximos inicios")
    s.add_argument("--horas", type=float, default=48.0)
    sub.add_parser("estado", help="¿corre observar?, último evento")
    a = ap.parse_args(argv)

    if a.cmd == "una-vez":
        t0 = time.time()
        try:
            doc = una_vez(Motor(n_sim=a.n_sim, proyectar=not a.sin_proyeccion), salida=None)
        except ErrorRed as e:
            print(json.dumps({"error": f"ESPN no respondió: {e}", "vivo_json": "sin cambios"}, ensure_ascii=False))
            return 1
        err = validar_documento(doc)
        if err:
            print(json.dumps({"error": "documento inválido, no se escribe", "detalle": err[:10]}, ensure_ascii=False))
            return 1
        peso = escribir_json(doc, Path(a.salida))
        print(json.dumps({**_resumen(doc, peso), "segundos": round(time.time() - t0, 1)}, ensure_ascii=False))
        return 0
    if a.cmd == "observar":
        hasta = de_iso(a.hasta) if a.hasta else None
        if a.hasta and hasta is None:
            ap.error("--hasta debe ser AAAA-MM-DDTHH:MM")
        return observar(hasta, Motor(n_sim=a.n_sim, proyectar=not a.sin_proyeccion))
    if a.cmd == "esperar":
        return esperar(a.desde, a.max_seg, Path(a.eventos), Path(a.candado), agrupar=a.agrupar)
    if a.cmd == "repetir":
        r = repetir(a.id, a.velocidad, Path(a.salida), n_sim=a.n_sim, proyectar=not a.sin_proyeccion)
        r["ultimo"] = _resumen(r["ultimo"])
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if a.cmd == "plan":
        print(json.dumps(plan(a.horas), ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(estado(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
