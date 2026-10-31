#!/usr/bin/env python3
"""Colector del F1 Live Timing (SignalR Core) para seguir una qualy en vivo.

Mantiene el estado de la sesión fusionando los deltas del feed y escribe snapshots con la forma del
doc "live/qualy" (ver el contrato en ESTADO_MEXICO.md / workflow) en un JSON, con escritura atómica
(archivo temporal + rename) cada ~20 s o cuando cambia algo.

Uso:
  python3 live_qualy.py --salida live/qualy_mexico.json --minutos 80            # feed real
  python3 live_qualy.py --salida live/qualy_mexico.json --minutos 80 --grabar live/crudo.jsonl
  python3 live_qualy.py --replay grabacion.jsonl --salida /tmp/x.json --historial /tmp/snaps.jsonl
  python3 live_qualy.py --cualquier-sesion --minutos 3                           # prueba con FP3/carrera

Protocolo (sin autenticación): POST /signalrcore/negotiate?negotiateVersion=1 -> connectionToken + cookie
AWSALB; websocket wss://livetiming.formula1.com/signalrcore?id=<token>; handshake {"protocol":"json",
"version":1}; invocación Subscribe(topics). Respuesta type 3 = estado completo; luego type 1 target
"feed" con [topic, delta, timestamp] (deltas que se fusionan recursivamente); type 6 = ping; type 7 = close.

Formato de --grabar / --replay (JSON Lines), una línea por registro SignalR:
  {"t": <epoch recepción>, "m": <mensaje SignalR ya parseado>}
  {"t": ..., "raw": "<texto que no se pudo parsear>"}
  {"t": ..., "evento": "conectado" | "desconectado", ...}
También se aceptan líneas que son directamente el mensaje SignalR ({"type": 1, ...}).
"""
import argparse
import base64
import json
import logging
import logging.handlers
import os
import random
import re
import signal
import sys
import tempfile
import time
import traceback
import urllib.parse
import zlib
from datetime import datetime, timezone

VERSION = "1.0"
NEGOTIATE_URL = "https://livetiming.formula1.com/signalrcore/negotiate?negotiateVersion=1"
WS_URL = "wss://livetiming.formula1.com/signalrcore?id={token}"
SEP = "\x1e"
TOPICOS = ["Heartbeat", "SessionInfo", "SessionStatus", "DriverList", "TimingData", "TimingStats",
           "TimingAppData", "TrackStatus", "ExtrapolatedClock", "LapCount", "RaceControlMessages",
           "SessionData"]
PING_CADA = 10.0          # s entre pings del cliente (el servidor corta a los ~30 s sin nada del cliente)
SIN_DATOS_MAX = 45.0      # s sin recibir nada (el servidor manda ping cada 15 s) -> reconectar
BACKOFF_MAX = 30.0
MIN_ENTRE_ESCRITURAS = 2.0  # s mínimos entre escrituras por cambio

log = logging.getLogger("live_qualy")


class _FiltroSim(logging.Filter):
    """En --replay antepone la hora simulada (la de la grabación) a cada línea del log."""
    t = None

    def filter(self, record):
        if _FiltroSim.t is not None:
            record.msg = f"[{datetime.fromtimestamp(_FiltroSim.t, timezone.utc):%H:%M:%S} sim] {record.msg}"
        return True


# --------------------------------------------------------------------------------------------- utilidades
def iso_utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


_RE_FRAC = re.compile(r"\.(\d+)")


def parse_iso(s):
    """'2026-10-31T21:05:12.0266264Z' (fracción de 0-7 dígitos, Z u offset o sin zona) -> epoch."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace("Z", "+00:00")
    s = _RE_FRAC.sub(lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def hms_a_seg(s):
    """'00:14:47' / '14:47' / '00:14:47.123' -> segundos."""
    if not s or not isinstance(s, str):
        return None
    try:
        partes = [float(p) for p in s.strip().split(":")]
    except ValueError:
        return None
    seg = 0.0
    for p in partes:
        seg = seg * 60 + p
    return seg


def seg_a_mmss(seg):
    if seg is None:
        return None
    seg = max(0, int(seg + 0.999))  # redondeo hacia arriba, como el reloj de la transmisión
    return f"{seg // 60:02d}:{seg % 60:02d}"


def tiempo_vuelta(s):
    """'1:15.432' / '75.432' -> 75.432 (None si vacío)."""
    if not s or not isinstance(s, str):
        return None
    try:
        if ":" in s:
            m, r = s.split(":", 1)
            return int(m) * 60 + float(r)
        return float(s)
    except ValueError:
        return None


def idx(cont, i):
    """Elemento i de una lista o de un dict con índices '0','1',... (como llegan los deltas)."""
    if isinstance(cont, list):
        return cont[i] if 0 <= i < len(cont) else None
    if isinstance(cont, dict):
        v = cont.get(str(i))
        return v if v is not None else cont.get(i)
    return None


def valor(x):
    """{'Value': '1:15.432', ...} -> '1:15.432'; '' -> None."""
    if isinstance(x, dict):
        x = x.get("Value")
    if isinstance(x, str):
        x = x.strip()
        return x or None
    return None


def _d(x):
    return x if isinstance(x, dict) else {}


def entero(x):
    try:
        if x is None or x == "":
            return None
        return int(x)
    except (TypeError, ValueError):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return None


def fusionar(dst, delta):
    """Fusiona recursivamente un delta del feed sobre el estado y devuelve el nuevo valor.

    - dict sobre dict: clave a clave (recursivo).
    - dict con índices "0","1",... sobre lista: actualiza/extiende la lista por índice.
    - lista o escalar: reemplaza.
    - "_kf" se ignora; "_deleted": [claves] borra esas claves/índices.
    """
    if isinstance(delta, dict):
        borrar = delta.get("_deleted")
        if isinstance(dst, list):
            for k, v in delta.items():
                if k in ("_kf", "_deleted"):
                    continue
                i = entero(k)
                if i is None or i < 0:
                    # clave no numérica sobre una lista: pasar a dict para no perder el dato
                    dst = {str(j): e for j, e in enumerate(dst)}
                    return fusionar(dst, delta)
                while len(dst) <= i:
                    dst.append(None)
                dst[i] = fusionar(dst[i], v)
            if isinstance(borrar, list):
                for i in sorted({entero(k) for k in borrar if entero(k) is not None}, reverse=True):
                    if 0 <= i < len(dst):
                        del dst[i]
            return dst
        if not isinstance(dst, dict):
            dst = {}
        for k, v in delta.items():
            if k in ("_kf", "_deleted"):
                continue
            dst[k] = fusionar(dst.get(k), v)
        if isinstance(borrar, list):
            for k in borrar:
                dst.pop(str(k), None)
        return dst
    if isinstance(delta, list):
        return json.loads(json.dumps(delta))  # copia profunda
    return delta


def decodificar_z(data):
    """Tópicos '.z': base64 + deflate crudo -> objeto JSON."""
    raw = zlib.decompress(base64.b64decode(data), -zlib.MAX_WBITS)
    return json.loads(raw.decode("utf-8-sig"))


def escribir_atomico(ruta, obj):
    d = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------------------------- estado
class EstadoLT:
    """Estado fusionado de todos los tópicos + metadatos del colector."""

    def __init__(self, cualquier_sesion=False, meeting=None):
        self.temas = {}
        self.cualquier_sesion = cualquier_sesion
        self.meeting = meeting
        self.tiene_estado = False
        self.conectado = False
        self.reconexiones = 0
        self.ultimo_rx = None          # epoch del último mensaje recibido (cualquier tipo)
        self.ultimo_feed = None        # epoch del último mensaje de datos
        self.n_msgs = 0
        self.n_errores = 0
        self.offsets = []              # Heartbeat.Utc - hora local (reloj del servidor)
        self.ko_visto = {}             # num -> SessionPart cuando se vio KnockedOut por primera vez
        self.q3_iniciada = False
        self.parte_iniciada = None     # segmento del último "Started" (para la pausa entre segmentos)
        self.n_terminados = 0          # segmentos cuyo "Finished" se vio en vivo
        self.sesion_key = None
        self.pedir_reconexion = None   # motivo si hay que reconectar (p.ej. cambió la sesión)
        self._prev = {}                # para registrar transiciones en el log
        self._rc_vistos = 0
        self._errores_por_tipo = {}

    # ---- entrada de datos
    def reemplazar(self, result, t):
        """Respuesta type 3 al Subscribe: estado completo de cada tópico."""
        nuevos = {}
        for topic, data in (result or {}).items():
            try:
                topic, data = self._normalizar(topic, data)
                if data is None:
                    continue
                nuevos[topic] = fusionar(None, data)
            except Exception as e:  # noqa: BLE001
                self.error("estado inicial " + str(topic), e, data)
        self.temas = nuevos
        self.tiene_estado = True
        self.ultimo_feed = t
        self._rc_vistos = len(self._rc_lista())
        log.info("Estado completo recibido: %s", ", ".join(f"{k}" for k in sorted(nuevos)))
        self._revisar_sesion(inicial=True)
        self._revisar_transiciones(t)

    def aplicar(self, topic, data, t):
        topic, data = self._normalizar(topic, data)
        if data is None:
            return
        self.temas[topic] = fusionar(self.temas.get(topic), data)
        self.ultimo_feed = t
        if topic == "Heartbeat":
            hb = parse_iso((data or {}).get("Utc")) if isinstance(data, dict) else None
            if hb is not None and t is not None:
                self.offsets = (self.offsets + [hb - t])[-7:]
        elif topic == "SessionInfo":
            self._revisar_sesion()
        elif topic == "RaceControlMessages":
            self._log_rc()
        self._revisar_transiciones(t)

    @staticmethod
    def _normalizar(topic, data):
        if isinstance(topic, str) and topic.endswith(".z"):
            topic = topic[:-2]
            if isinstance(data, str):
                data = decodificar_z(data)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass
        return topic, data

    def error(self, donde, exc, contenido=None):
        self.n_errores += 1
        clave = (donde.split(" ")[0], type(exc).__name__)
        n = self._errores_por_tipo.get(clave, 0) + 1
        self._errores_por_tipo[clave] = n
        if n <= 5 or n % 100 == 0:
            frag = json.dumps(contenido, ensure_ascii=False, default=str)[:300] if contenido is not None else ""
            donde_tb = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
            log.warning("Error procesando %s (%s #%d): %r en %s | %s", donde, type(exc).__name__, n, exc,
                        f"línea {donde_tb.lineno} ({donde_tb.name})" if donde_tb else "?", frag)

    # ---- derivados
    def ahora_servidor(self, t_local):
        if not self.offsets:
            return t_local
        o = sorted(self.offsets)[len(self.offsets) // 2]
        return t_local + (o if abs(o) > 1.0 else 0.0)

    def _rc_lista(self):
        msgs = _d(self.temas.get("RaceControlMessages")).get("Messages")
        if isinstance(msgs, dict):
            msgs = [msgs[k] for k in sorted(msgs, key=lambda x: entero(x) or 0)]
        return [m for m in (msgs or []) if isinstance(m, dict)]

    def _log_rc(self):
        lst = self._rc_lista()
        for m in lst[self._rc_vistos:]:
            log.info("Control de carrera: %s", m.get("Message"))
        self._rc_vistos = len(lst)

    def _revisar_sesion(self, inicial=False):
        info = _d(self.temas.get("SessionInfo"))
        key = info.get("Key")
        if key != self.sesion_key:
            if self.sesion_key is not None and not inicial:
                log.warning("Cambió la sesión del feed: %s -> %s (%s); reconectando para estado limpio",
                            self.sesion_key, key, info.get("Name"))
                self.pedir_reconexion = "cambio de sesión"
            if self.sesion_key is not None:
                self.ko_visto = {}
                self.q3_iniciada = False
                self.parte_iniciada = None
                self.n_terminados = 0
            self.sesion_key = key
            meet = _d(info.get("Meeting"))
            log.info("Sesión del feed: %s %s (key %s, tipo %s, meeting %s %s)", meet.get("Name"), info.get("Name"),
                     key, info.get("Type"), meet.get("Key"), info.get("StartDate"))

    def _revisar_transiciones(self, t):
        td = _d(self.temas.get("TimingData"))
        parte = entero(td.get("SessionPart"))
        status = self.status_sesion()
        if status == "Started":
            # un "Started" después de un "Finished" es el segmento siguiente aunque SessionPart aún no cambie
            self.parte_iniciada = max(parte or 1, min(3, self.n_terminados + 1))
            if self.parte_iniciada >= 3:
                self.q3_iniciada = True
        elif (status == "Finished" and self._prev.get("status") not in (None, "Finished")
              and self.parte_iniciada):
            self.n_terminados = max(self.n_terminados, self.parte_iniciada)
        lines = td.get("Lines") if isinstance(td.get("Lines"), dict) else {}
        kos = []
        for num, L in lines.items():
            if isinstance(L, dict) and L.get("KnockedOut") and num not in self.ko_visto:
                self.ko_visto[num] = parte or 1
                kos.append(self.acr(num))
        if kos:
            log.info("Eliminados (KnockedOut, SessionPart=%s): %s", parte, ", ".join(kos))
        track = _d(self.temas.get("TrackStatus"))
        actual = {"status": status, "parte": parte,
                  "pista": f"{track.get('Status')} {track.get('Message')}" if track else None}
        for k, v in actual.items():
            if self._prev.get(k, "∅") != v:
                if k in self._prev:
                    log.info("Cambio %s: %s -> %s", k, self._prev.get(k), v)
                self._prev[k] = v

    def status_sesion(self):
        ss = _d(self.temas.get("SessionStatus"))
        st = ss.get("Status") if isinstance(ss, dict) else None
        if not st:
            st = _d(self.temas.get("SessionInfo")).get("SessionStatus")
        return st or "Inactive"

    def acr(self, num):
        d = _d(self.temas.get("DriverList")).get(str(num))
        if isinstance(d, dict):
            if d.get("Tla"):
                return d["Tla"]
            bn = (d.get("BroadcastName") or "").split()
            if bn:
                return bn[-1][:3].upper()
        return str(num)

    def es_objetivo(self):
        info = _d(self.temas.get("SessionInfo"))
        if self.meeting is not None and _d(info.get("Meeting")).get("Key") not in (None, self.meeting):
            return False
        if self.cualquier_sesion:
            return True
        return str(info.get("Type") or "").lower() == "qualifying" or "qualifying" in str(info.get("Name") or "").lower()

    # ---- snapshot con la forma del doc "live/qualy"
    def snapshot(self, t_local):
        T = self.temas
        info = _d(T.get("SessionInfo"))
        td = _d(T.get("TimingData"))
        dl = _d(T.get("DriverList"))
        track = _d(T.get("TrackStatus"))
        status = self.status_sesion()
        objetivo = self.es_objetivo()
        parte = entero(td.get("SessionPart")) or 1
        parte = min(max(parte, 1), 3)
        lines = td.get("Lines") if isinstance(td.get("Lines"), dict) else {}

        # pilotos (sólo F1: los autos de soporte/SC/médico no tienen equipo y usan números >= 100)
        nums = [n for n, L in lines.items() if isinstance(L, dict)]
        if not nums:
            nums = [n for n, d in dl.items() if isinstance(d, dict) and d.get("TeamName")]
        nums = [n for n in nums if (isinstance(dl.get(n), dict) and dl[n].get("TeamName"))
                or (entero(n) is not None and entero(n) < 100)]
        n_total = len(nums)
        no_ent = td.get("NoEntries")
        corte_q2 = entero(idx(no_ent, 1)) or (10 + max(0, n_total - 10) // 2)  # 22 autos -> 16
        corte_q3 = entero(idx(no_ent, 2)) or 10
        # si el feed no trae KnockedOut, se infiere por posición una vez que empezó el segmento siguiente
        hay_ko = any(isinstance(L, dict) and L.get("KnockedOut") for L in lines.values())

        pilotos = []
        aux = {}
        hay_tiempos = False
        hay_q3 = False
        for num in nums:
            L = lines.get(num) if isinstance(lines.get(num), dict) else {}
            p = {"acr": self.acr(num), "num": entero(num), "pos": None, "mejor": None, "q1": None, "q2": None,
                 "q3": None, "eliminado_en": None, "en_pits": bool(L.get("InPit")),
                 "vueltas": entero(L.get("NumberOfLaps")) or 0, "dif": None, "neumatico": None}
            if objetivo:
                pos = entero(L.get("Position"))
                p["pos"] = pos if pos and pos > 0 else None
                blt = L.get("BestLapTimes")
                q = [valor(idx(blt, i)) for i in range(3)]
                p["q1"], p["q2"], p["q3"] = q
                if any(q):
                    hay_tiempos = True
                if q[2]:
                    hay_q3 = True
                ko = bool(L.get("KnockedOut"))
                if ko:
                    if q[1]:
                        p["eliminado_en"] = 2
                    elif self.ko_visto.get(num) == 1:
                        p["eliminado_en"] = 1
                    elif p["pos"]:
                        p["eliminado_en"] = 1 if p["pos"] > corte_q2 else 2
                    else:
                        p["eliminado_en"] = min(max(self.ko_visto.get(num, 1), 1), 2)
                elif not hay_ko and parte >= 2 and p["pos"] and blt is not None:
                    if p["pos"] > corte_q2:
                        p["eliminado_en"] = 1
                    elif parte >= 3 and p["pos"] > corte_q3:
                        p["eliminado_en"] = 2
                if blt is None:
                    # sesión sin segmentos (práctica, con --cualquier-sesion): mejor vuelta global
                    p["mejor"] = valor(L.get("BestLapTime"))
                    hay_tiempos = hay_tiempos or bool(p["mejor"])
                aux[id(p)] = (blt is not None, q, L.get("Stats"), valor(L.get("TimeDiffToFastest")))
                stints = _d(_d(_d(T.get("TimingAppData")).get("Lines")).get(num))
                stints = stints.get("Stints")
                if isinstance(stints, dict):
                    stints = [stints[k] for k in sorted(stints, key=lambda x: entero(x) or 0)]
                ult = stints[-1] if isinstance(stints, list) and stints else None
                p["neumatico"] = ult.get("Compound") if isinstance(ult, dict) else None
            pilotos.append(p)

        # estado
        if not objetivo or not self.tiene_estado:
            estado = "pendiente"
        elif status in ("Finalised", "Ends"):
            estado = "terminada"
        elif status == "Finished" and parte >= 3 and (hay_q3 or self.q3_iniciada):
            estado = "terminada"
        elif status == "Aborted" or str(track.get("Status")) == "5":
            estado = "bandera_roja"
        elif status in ("Started", "Finished"):
            estado = "en_vivo"
        else:  # Inactive
            estado = "en_vivo" if hay_tiempos else "pendiente"

        segmento = 0 if estado == "pendiente" else parte
        if estado != "pendiente" and self.parte_iniciada:
            if status == "Finished" and estado == "en_vivo":
                segmento = min(segmento, self.parte_iniciada)  # pausa entre segmentos: el que acaba de terminar
            elif status in ("Started", "Aborted"):
                segmento = max(segmento, self.parte_iniciada)  # SessionPart puede llegar después del Started
        # mejor tiempo y diferencia del segmento que define la posición (el de eliminación o el actual)
        for p in pilotos:
            a = aux.get(id(p))
            if not a or segmento == 0:
                continue
            con_segmentos, q, stats, dif_top = a
            ref = p["eliminado_en"] or segmento
            if con_segmentos:
                p["mejor"] = q[ref - 1]
            st = idx(stats, ref - 1)
            p["dif"] = valor(st.get("TimeDiffToFastest") if isinstance(st, dict) else None) or dif_top
        if estado == "pendiente":
            for p in pilotos:
                p.update(pos=None, mejor=None, q1=None, q2=None, q3=None, eliminado_en=None, dif=None)
                if not objetivo:  # datos de otra sesión (FP3, carrera...): no mezclarlos con la qualy
                    p.update(en_pits=False, vueltas=0, neumatico=None)

        # reloj
        reloj = None
        ec = _d(T.get("ExtrapolatedClock"))
        if estado != "pendiente" and ec.get("Remaining"):
            rem = hms_a_seg(ec.get("Remaining"))
            if rem is not None:
                if ec.get("Extrapolating"):
                    u = parse_iso(ec.get("Utc"))
                    if u is not None:
                        rem -= max(0.0, self.ahora_servidor(t_local) - u)
                reloj = seg_a_mmss(max(0.0, rem))
        if estado == "terminada":
            reloj = "00:00"

        if not objetivo:
            detalle = f"El feed está en {info.get('Name') or info.get('Type') or 'otra sesión'}; esperando la qualy"
        elif estado == "pendiente":
            detalle = "Qualy por comenzar"
        elif estado == "terminada":
            nombre = "Qualy" if "qualifying" in str(info.get("Name") or "qualifying").lower() else info.get("Name")
            detalle = f"{nombre} terminada" + ("" if status in ("Finalised", "Ends") else " (provisional)")
        elif estado == "bandera_roja":
            detalle = f"Bandera roja en Q{segmento}"
        elif status == "Finished":
            detalle = f"Fin de Q{segmento}; esperando Q{segmento + 1}"
        else:
            detalle = f"Q{segmento} en curso"

        pilotos.sort(key=lambda p: (p["pos"] is None, p["pos"] or 0,
                                    entero(_d(dl.get(str(p["num"]))).get("Line")) or 99, p["acr"]))
        rc = [{"utc": m.get("Utc"), "texto": m.get("Message"), "bandera": m.get("Flag")}
              for m in self._rc_lista()[-4:]] if objetivo else []
        meet = _d(info.get("Meeting"))
        return {
            "actualizado": iso_utc(t_local),
            "estado": estado,
            "segmento": segmento,
            "reloj": reloj,
            "pilotos": pilotos,
            "fuente": "F1 Live Timing",
            # extras (fuera del contrato mínimo)
            "detalle": detalle,
            "sesion": {"key": info.get("Key"), "nombre": info.get("Name"), "tipo": info.get("Type"),
                       "gp": meet.get("Name"), "meeting_key": meet.get("Key"), "estado_feed": status},
            "pista": {"estado": track.get("Status"), "mensaje": track.get("Message")} if track else None,
            "corte": valor(td.get("CutOffTime")),
            "mensajes": rc,
            "colector": {"conectado": self.conectado, "reconexiones": self.reconexiones,
                         "ultimo_dato": iso_utc(self.ultimo_feed) if self.ultimo_feed else None,
                         "mensajes": self.n_msgs, "errores": self.n_errores, "version": VERSION},
        }


# --------------------------------------------------------------------------------------------- escritura
class Escritor:
    def __init__(self, ruta, intervalo, historial=None):
        self.ruta = ruta
        self.intervalo = intervalo
        self.historial = historial
        self.t_ult = None
        self.clave_ult = None
        self.n = 0
        self.ultimo = None
        self.t_finalizada = None   # hora en que se vio la qualy Finalised/Ends (para --salir-al-terminar)

    def tick(self, estado, t, forzar=False):
        if not estado.tiene_estado:
            return False
        try:
            snap = estado.snapshot(t)
        except Exception as e:  # noqa: BLE001
            estado.error("snapshot", e)
            return False
        clave = json.dumps({k: v for k, v in snap.items() if k not in ("actualizado", "reloj", "colector")},
                           sort_keys=True, ensure_ascii=False)
        cambio = clave != self.clave_ult
        vencido = self.t_ult is None or t - self.t_ult >= self.intervalo
        if not (forzar or vencido or (cambio and t - self.t_ult >= MIN_ENTRE_ESCRITURAS)):
            return False
        try:
            escribir_atomico(self.ruta, snap)
            if self.historial:
                with open(self.historial, "a", encoding="utf-8") as f:
                    f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            estado.error("escritura", e)
            return False
        if self.ultimo is None or snap["estado"] != self.ultimo["estado"] or snap["segmento"] != self.ultimo["segmento"]:
            log.info("Snapshot: estado=%s segmento=%s reloj=%s (%s)", snap["estado"], snap["segmento"], snap["reloj"],
                     snap["detalle"])
        self.t_ult, self.clave_ult, self.ultimo = t, clave, snap
        self.n += 1
        if snap["estado"] == "terminada" and snap["sesion"].get("estado_feed") in ("Finalised", "Ends"):
            self.t_finalizada = self.t_finalizada or t
        return True

    def debe_salir(self, args, t):
        """--salir-al-terminar: 2 min después de ver la qualy Finalised/Ends."""
        if args.salir_al_terminar and self.t_finalizada and t - self.t_finalizada > 120:
            if not Parar.flag:
                log.info("Qualy finalizada hace más de 2 min; saliendo (--salir-al-terminar)")
            Parar.flag = True
        return Parar.flag


class Grabador:
    def __init__(self, ruta):
        self.f = None
        if ruta:
            os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
            self.f = open(ruta, "a", encoding="utf-8")

    def registro(self, obj):
        if self.f:
            try:
                self.f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                self.f.flush()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo grabar")

    def cerrar(self):
        if self.f:
            self.f.close()


class ConexionCerrada(Exception):
    pass


# --------------------------------------------------------------------------------------------- proceso de mensajes
def procesar_texto(texto, t, estado, grabador):
    """Procesa un registro SignalR (texto JSON sin el separador). Nunca lanza salvo ConexionCerrada."""
    texto = texto.strip()
    if not texto:
        return
    try:
        m = json.loads(texto)
    except ValueError as e:
        grabador.registro({"t": t, "raw": texto})
        estado.error("json", e, texto)
        return
    grabador.registro({"t": t, "m": m})
    procesar_mensaje(m, t, estado)


def procesar_mensaje(m, t, estado):
    estado.ultimo_rx = t
    estado.n_msgs += 1
    try:
        if not isinstance(m, dict):
            raise ValueError("mensaje no es un objeto")
        tipo = m.get("type")
        if tipo == 1:
            if str(m.get("target", "")).lower() != "feed":
                log.debug("Invocación ignorada: %s", m.get("target"))
                return
            args = m.get("arguments") or []
            if len(args) < 2:
                raise ValueError("feed sin [topic, data]")
            topic, data = args[0], args[1]
            try:
                estado.aplicar(topic, data, t)
            except Exception as e:  # noqa: BLE001
                estado.error(f"feed {topic}", e, data)
        elif tipo == 3:
            if m.get("error"):
                log.error("Subscribe falló: %s", m.get("error"))
            elif isinstance(m.get("result"), dict):
                estado.reemplazar(m["result"], t)
            else:
                log.warning("Completion sin resultado: %s", json.dumps(m)[:200])
        elif tipo == 6:
            pass
        elif tipo == 7:
            raise ConexionCerrada(f"close del servidor: {m.get('error')} (allowReconnect={m.get('allowReconnect')})")
        elif tipo == 2:
            log.debug("StreamItem ignorado")
        else:
            log.debug("Mensaje tipo %s ignorado", tipo)
    except ConexionCerrada:
        raise
    except Exception as e:  # noqa: BLE001
        estado.error("mensaje", e, m)


# --------------------------------------------------------------------------------------------- modo en vivo
class Parar:
    flag = False


def _handler(signum, frame):  # noqa: ARG001
    log.info("Señal %s recibida; terminando", signum)
    Parar.flag = True


def conectar_y_leer(args, estado, escritor, grabador, fin):
    import requests
    import websocket

    topicos = [x.strip() for x in args.topicos.split(",")] if args.topicos else TOPICOS
    r = requests.post(NEGOTIATE_URL, timeout=15, headers={"User-Agent": "live_qualy/" + VERSION})
    r.raise_for_status()
    neg = r.json()
    token = neg.get("connectionToken") or neg.get("connectionId")
    if not token:
        raise RuntimeError(f"negotiate sin token: {str(neg)[:200]}")
    cookie = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
    url = WS_URL.format(token=urllib.parse.quote(token, safe=""))
    hdr = [f"Cookie: {cookie}"] if cookie else []
    ws = websocket.create_connection(url, timeout=15, header=hdr)
    try:
        ws.send(json.dumps({"protocol": "json", "version": 1}) + SEP)
        hs = ws.recv()
        if isinstance(hs, bytes):
            hs = hs.decode("utf-8", "replace")
        primero, _, resto = hs.partition(SEP)
        if '"error"' in primero:
            raise RuntimeError("handshake rechazado: " + primero)
        ws.send(json.dumps({"type": 1, "invocationId": "1", "target": "Subscribe", "arguments": [topicos]}) + SEP)
        estado.conectado = True
        t = time.time()
        estado.ultimo_rx = t
        grabador.registro({"t": t, "evento": "conectado", "topicos": topicos})
        log.info("Conectado (cookie %s); suscrito a %d tópicos", "sí" if cookie else "no", len(topicos))
        ws.settimeout(1.0)
        buf = resto
        t_ping = time.time()
        t_resumen = time.time()
        t_conexion = time.time()
        t_tick = 0.0
        while not Parar.flag:
            ahora = time.time()
            if ahora >= fin:
                log.info("Se cumplió el tiempo (--minutos); cerrando")
                return
            texto = None
            try:
                texto = ws.recv()
            except websocket.WebSocketTimeoutException:
                pass
            ahora = time.time()
            if texto is not None:
                if isinstance(texto, bytes):
                    texto = texto.decode("utf-8", "replace")
                if texto == "":
                    raise ConexionCerrada("websocket cerrado por el servidor")
                buf += texto
            if SEP in buf:  # también procesa lo que vino pegado a la respuesta del handshake
                partes = buf.split(SEP)
                buf = partes.pop()
                for p in partes:
                    procesar_texto(p, ahora, estado, grabador)
            if len(buf) > 5_000_000:
                estado.error("buffer", ValueError("registro sin separador demasiado grande"), buf[:200])
                buf = ""
            if args.cortar_cada and ahora - t_conexion > args.cortar_cada:
                raise ConexionCerrada("corte de prueba (--cortar-cada)")
            if estado.pedir_reconexion:
                motivo, estado.pedir_reconexion = estado.pedir_reconexion, None
                raise ConexionCerrada(motivo)
            if ahora - t_ping >= PING_CADA:
                ws.send(json.dumps({"type": 6}) + SEP)
                t_ping = ahora
            if estado.ultimo_rx and ahora - estado.ultimo_rx > SIN_DATOS_MAX:
                raise ConexionCerrada(f"sin datos hace {ahora - estado.ultimo_rx:.0f} s")
            if ahora - t_tick >= 0.5:  # en qualy llegan decenas de mensajes por segundo
                t_tick = ahora
                escritor.tick(estado, ahora)
            if escritor.debe_salir(args, ahora):
                return
            if ahora - t_resumen >= 60:
                t_resumen = ahora
                resumen(estado, escritor)
    finally:
        estado.conectado = False
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass
        grabador.registro({"t": time.time(), "evento": "desconectado"})


def resumen(estado, escritor):
    s = escritor.ultimo
    if not s:
        log.info("Resumen: sin snapshot todavía (msgs=%d)", estado.n_msgs)
        return
    top = ",".join(f"{p['acr']}" for p in s["pilotos"][:5] if p["pos"])
    log.info("Resumen: %s seg=%s reloj=%s top5=%s | msgs=%d errores=%d escrituras=%d", s["estado"], s["segmento"],
             s["reloj"], top or "-", estado.n_msgs, estado.n_errores, escritor.n)


def esperar(segundos, estado, escritor, fin, args):
    """Espera (backoff) sin dejar de refrescar el snapshot (el reloj sigue corriendo)."""
    limite = min(time.time() + segundos, fin)
    while not escritor.debe_salir(args, time.time()) and time.time() < limite:
        time.sleep(0.5)
        escritor.tick(estado, time.time())


def modo_en_vivo(args, estado, escritor, grabador):
    fin = time.time() + args.minutos * 60
    intento = 0
    while not Parar.flag and time.time() < fin:
        t0 = time.time()
        try:
            conectar_y_leer(args, estado, escritor, grabador, fin)
            motivo = None
        except ConexionCerrada as e:
            motivo = str(e)
        except Exception as e:  # noqa: BLE001
            motivo = f"{type(e).__name__}: {e}"
        escritor.tick(estado, time.time(), forzar=True)
        if Parar.flag or time.time() >= fin:
            break
        if time.time() - t0 > 60:
            intento = 0
        espera = min(BACKOFF_MAX, 2 ** intento) * random.uniform(0.8, 1.2)
        intento += 1
        estado.reconexiones += 1
        log.warning("Conexión terminada (%s). Reintento #%d en %.1f s", motivo, estado.reconexiones, espera)
        esperar(espera, estado, escritor, fin, args)
    escritor.tick(estado, time.time(), forzar=True)


# --------------------------------------------------------------------------------------------- replay
def modo_replay(args, estado, escritor, grabador):
    t_prev = None
    t_sim = None
    n = 0
    with open(args.replay, encoding="utf-8") as f:
        for linea in f:
            if Parar.flag:
                break
            linea = linea.strip()
            if not linea:
                continue
            try:
                obj = json.loads(linea)
            except ValueError as e:
                estado.error("replay-linea", e, linea)
                continue
            if not isinstance(obj, dict):
                estado.error("replay-linea", ValueError("línea no es objeto"), obj)
                continue
            t = obj.get("t")
            m = obj.get("m") if "m" in obj else (obj if "type" in obj else None)
            if t is None and isinstance(m, dict) and m.get("type") == 1:
                a = m.get("arguments") or []
                t = parse_iso(a[2]) if len(a) > 2 and isinstance(a[2], str) else None
            if t is None:
                t = t_sim if t_sim is not None else time.time()
            if args.velocidad and t_prev is not None and t > t_prev:
                time.sleep(min((t - t_prev) / args.velocidad, 5.0))
            # en replay el "ahora" es la hora grabada; antes de aplicar este mensaje se emulan los ticks que el
            # modo en vivo haría (cada ~1 s) en el hueco: cambios retenidos por el mínimo de 2 s y latidos de 20 s
            if escritor.t_ult is not None and t_prev is not None:
                tt = max(t_prev, escritor.t_ult + MIN_ENTRE_ESCRITURAS)
                if tt < t:
                    escritor.tick(estado, tt)
                while t - escritor.t_ult > escritor.intervalo:
                    if not escritor.tick(estado, escritor.t_ult + escritor.intervalo):
                        break
            t_prev = t
            t_sim = t
            _FiltroSim.t = t
            if "evento" in obj:
                if obj["evento"] == "conectado":
                    estado.conectado = True
                elif obj["evento"] == "desconectado":
                    estado.conectado = False
                    estado.reconexiones += 1
                log.info("[replay] evento %s", obj["evento"])
            elif "raw" in obj:
                for p in str(obj["raw"]).split(SEP):
                    try:
                        procesar_texto(p, t, estado, grabador)
                    except ConexionCerrada as e:
                        log.info("[replay] %s", e)
            elif m is not None:
                try:
                    procesar_mensaje(m, t, estado)
                except ConexionCerrada as e:
                    log.info("[replay] %s", e)
                    estado.conectado = False
            n += 1
            escritor.tick(estado, t)
    if t_sim is not None:
        escritor.tick(estado, t_sim, forzar=True)
    _FiltroSim.t = None
    log.info("Replay terminado: %d registros, %d escrituras, %d errores", n, escritor.n, estado.n_errores)


# --------------------------------------------------------------------------------------------- main
def configurar_log(ruta, verbose):
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.addFilter(_FiltroSim())
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    fmt.converter = time.gmtime
    if ruta:
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(ruta, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    log.addHandler(sh)


def main(argv=None):
    base = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Colector F1 Live Timing -> snapshot JSON del doc live/qualy. "
                                 "Las rutas relativas de --salida/--log/--grabar/--historial son relativas a "
                                 "la carpeta del script.")
    ap.add_argument("--salida", default=os.path.join(base, "live", "qualy_mexico.json"))
    ap.add_argument("--log", default=None, help="log (por defecto colector.log junto a --salida)")
    ap.add_argument("--minutos", type=float, default=80.0, help="se detiene solo después de N minutos")
    ap.add_argument("--intervalo", type=float, default=20.0, help="s entre snapshots aunque no cambie nada")
    ap.add_argument("--grabar", default=None, help="JSONL con todos los mensajes crudos recibidos")
    ap.add_argument("--replay", default=None, help="reproducir un JSONL grabado en vez de conectarse")
    ap.add_argument("--velocidad", type=float, default=0.0,
                    help="replay: factor de velocidad (0 = lo más rápido posible, 1 = tiempo real)")
    ap.add_argument("--historial", default=None, help="JSONL donde se agrega cada snapshot escrito")
    ap.add_argument("--cualquier-sesion", action="store_true",
                    help="no exigir que la sesión del feed sea Qualifying (para probar con FP/carrera)")
    ap.add_argument("--meeting", type=int, default=None, help="exigir este meeting key (p.ej. 1298)")
    ap.add_argument("--topicos", default=None, help="lista separada por comas (por defecto: " + ",".join(TOPICOS) + ")")
    ap.add_argument("--salir-al-terminar", action="store_true",
                    help="salir cuando la qualy quede Finalised/terminada (por defecto sigue hasta --minutos)")
    ap.add_argument("--cortar-cada", type=float, default=0, help=argparse.SUPPRESS)  # pruebas de reconexión
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    # las rutas relativas de salida se resuelven contra la carpeta del script (f1_austin/), no contra el cwd
    for k in ("salida", "log", "grabar", "historial"):
        v = getattr(args, k)
        if v and not os.path.isabs(v):
            setattr(args, k, os.path.join(base, v))
    if args.replay and not os.path.isabs(args.replay) and not os.path.exists(args.replay):
        args.replay = os.path.join(base, args.replay)
    args.log = args.log or os.path.join(os.path.dirname(args.salida), "colector.log")
    configurar_log(args.log, args.verbose)
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)

    estado = EstadoLT(cualquier_sesion=args.cualquier_sesion, meeting=args.meeting)
    escritor = Escritor(args.salida, args.intervalo, args.historial)
    grabador = Grabador(args.grabar)
    log.info("live_qualy %s | modo=%s salida=%s minutos=%s grabar=%s", VERSION, "replay" if args.replay else "en vivo",
             args.salida, args.minutos, args.grabar)
    try:
        if args.replay:
            modo_replay(args, estado, escritor, grabador)
        else:
            modo_en_vivo(args, estado, escritor, grabador)
    finally:
        grabador.cerrar()
        resumen(estado, escritor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
