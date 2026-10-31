#!/usr/bin/env python3
"""Reconstruye laps/stints/weather de una sesión (FP3 México 2026, OpenF1 session_key 11399) desde una grabación
del F1 Live Timing (jsonl de live_qualy.py --grabar), con el MISMO esquema que OpenF1 usa en cache/laps_<sk>.json,
cache/stints_<sk>.json y cache/weather_<sk>.json.

Uso:
  python3 fp3_desde_live.py --salida DIR [--validar] crudo1.jsonl [crudo2.jsonl ...]

Cómo se reconstruye (TimingData.Lines[num]):
- NumberOfLaps = vuelta EN CURSO (1 al salir del pit la primera vez). Un incremento k -> k+1 cierra la vuelta k con lo
  acumulado durante ella: Sectors[i].Value (S1/S2/S3), Segments (estados != 0), Speeds I1/I2/ST (FL no existe en OpenF1)
  y LastLapTime, sólo si LastLapTime/sector llegó DURANTE esa vuelta (si no, null: nunca se arrastra la de la vuelta
  anterior). La vuelta de entrada a pits recibe LastLapTime al entrar al pit lane, pero se cierra al volver a salir.
  Si LastLapTime/S3 llegan <4 s después del incremento (y aún no hay S1 nuevo) se atribuyen a la vuelta cerrada.
- La vuelta k+1 empieza en ese mensaje (date_start = timestamp del feed) y es is_pit_out_lap si PitOut=true.
- Reconexiones (type 3 = estado completo): se compara el estado nuevo con el acumulado y la diferencia se procesa
  como un delta (se pierde lo que cambió y volvió a cambiar dentro del hueco de ~3 s).
- Vueltas borradas (RaceControlMessages "CAR n ... TIME m:ss.sss DELETED"): se busca la vuelta de ese piloto con ese
  tiempo cerrada antes del mensaje -> lap_duration = null. "LAP DELETED" sin tiempo: la vuelta del número del mensaje
  (numeración de dirección de carrera = la nuestra + 1) cerrada antes del mensaje, también -> null.
- Al final de la grabación se cierra la vuelta en curso de cada piloto (entrada a pits tras la bandera a cuadros),
  para que el número de vueltas = NumberOfLaps final.
- Lo anterior al primer TimingData (en la FP3: 17:30-17:44 UTC) NO está: las vueltas 1..n0-1 de cada piloto quedan
  como marcadores (todo null) salvo: lap_duration de la mejor vuelta (BestLapTime.Lap del estado inicial y
  PersonalBestLapTime de TimingStats, que se graba desde antes), de los mejores tiempos por stint de TimingAppData
  (LapTime/LapNumber, LapNumber = nuestra vuelta + 1), del LastLapTime inicial (vuelta n0-1 si está en pista, n0 si
  está en el pit) y de las mejoras de PB recibidas por TimingStats antes del primer TimingData. Sectores, segmentos y
  velocidades de esas vueltas = null. is_pit_out_lap de esas vueltas = inicio de cada stint (TimingAppData).
- Stints: TimingAppData.Stints final; lap_start acumulando (TotalLaps - StartLaps) por stint; para los stints que
  aparecen en vivo se usa la vuelta en curso al aparecer (más exacto). tyre_age_at_start = StartLaps.
- Weather: sólo si la grabación trae WeatherData (la de la FP3 no lo trae: el colector no se suscribió) -> [].
Se escribe además meta_<sk>.json con el origen de cada vuelta (vivo / estado_inicial / marcador) y la validación.
"""
import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from live_qualy import _d, decodificar_z, entero, fusionar, idx, parse_iso, tiempo_vuelta, valor  # noqa: E402

SK, MK = 11399, 1298
_RE_CAR = re.compile(r"CAR (\d+)")
_RE_TIME = re.compile(r"TIME (\d+:\d{2}\.\d{3})")
_RE_LAP = re.compile(r"\bLAP (\d+)\b")


def iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="microseconds")


def items(cont):
    """(índice, valor) de una lista o de un dict con índices '0','1',..."""
    if isinstance(cont, list):
        return list(enumerate(cont))
    if isinstance(cont, dict):
        return [(entero(k), v) for k, v in cont.items() if entero(k) is not None]
    return []


def diff(old, new):
    """Delta mínimo que lleva old -> new (listas como dict de índices). None si son iguales."""
    if isinstance(new, (dict, list)):
        it_new = dict(items(new)) if isinstance(new, list) else new
        it_old = (dict(items(old)) if isinstance(old, list) else old) if isinstance(old, (dict, list)) else {}
        out = {}
        for k, v in it_new.items():
            o = it_old.get(k) if isinstance(it_old, dict) else None
            if o is None and isinstance(it_old, dict):
                o = it_old.get(str(k)) if not isinstance(k, str) else it_old.get(entero(k))
            d = diff(o, v)
            if d is not None:
                out[str(k)] = d
        return out or None
    return None if new == old else new


class Piloto:
    def __init__(self, num, nseg):
        self.num = num
        self.nseg = nseg
        self.n = None            # NumberOfLaps vigente (vuelta en curso)
        self.base = None          # info del estado inicial
        self.laps = {}            # lap_number -> dict
        self.origen = {}          # lap_number -> 'vivo' | 'estado_inicial' | 'marcador'
        self.buf = None
        self.ultimo_cierre = None  # (ts, lap_number)
        self.reset_pend = None     # (ts, {sector: {seg: status}}) de un reset de segmentos antes del incremento

    def nuevo_buf(self, lap, ts, pit_out, parcial=False):
        self.buf = {"lap": lap, "date_start": None if parcial else iso(ts), "t0": ts, "pit_out": bool(pit_out),
                    "s": [None, None, None], "seg": [{}, {}, {}], "sp": {}, "lap_time": None, "parcial": parcial}

    def cerrar(self, ts, origen="vivo"):
        b = self.buf
        if b is None or b["lap"] is None or b["lap"] < 1:
            return
        segs = []
        for i in range(3):
            if b["seg"][i]:
                n = max(self.nseg[i], max(b["seg"][i]) + 1)
                segs.append([b["seg"][i].get(j) for j in range(n)])
            else:
                segs.append(None)
        self.laps[b["lap"]] = {
            "meeting_key": MK, "session_key": SK, "driver_number": int(self.num), "lap_number": b["lap"],
            "date_start": b["date_start"],
            "duration_sector_1": b["s"][0], "duration_sector_2": b["s"][1], "duration_sector_3": b["s"][2],
            "i1_speed": b["sp"].get("I1"), "i2_speed": b["sp"].get("I2"), "is_pit_out_lap": b["pit_out"],
            "lap_duration": b["lap_time"],
            "segments_sector_1": segs[0], "segments_sector_2": segs[1], "segments_sector_3": segs[2],
            "st_speed": b["sp"].get("ST"),
        }
        self.origen[b["lap"]] = "vivo_parcial" if b["parcial"] else origen
        self.ultimo_cierre = (ts, b["lap"])


class Reconstructor:
    def __init__(self):
        self.temas = {}
        self.pilotos = {}
        self.offset = 0.0           # t_local - t_servidor
        self.t_primer_td = None
        self.pb_previos = {}         # num -> [(ts, tiempo, lap)] mejoras de PB por TimingStats antes del 1er TimingData
        self.stint_vivo = {}         # (num, stint_idx) -> vuelta en curso al aparecer
        self.weather = []
        self.n_reconexiones = 0
        self.tardios = 0

    # ------------------------------------------------------------------ entrada
    def procesar_archivo(self, ruta):
        for linea in open(ruta, encoding="utf-8"):
            linea = linea.strip()
            if not linea:
                continue
            try:
                r = json.loads(linea)
            except ValueError:
                continue
            m = r.get("m")
            if not isinstance(m, dict):
                continue
            t = r.get("t")
            if m.get("type") == 3 and isinstance(m.get("result"), dict):
                self.estado_completo(m["result"], t)
            elif m.get("type") == 1 and str(m.get("target", "")).lower() == "feed":
                a = m.get("arguments") or []
                if len(a) < 2:
                    continue
                ts = parse_iso(a[2]) if len(a) > 2 and isinstance(a[2], str) else None
                if ts is not None and t is not None:
                    self.offset = t - ts
                elif ts is None:
                    ts = (t or 0) - self.offset
                self.feed(a[0], a[1], ts)

    @staticmethod
    def normalizar(topic, data):
        if isinstance(topic, str) and topic.endswith(".z"):
            return topic[:-2], decodificar_z(data)
        return topic, data

    def estado_completo(self, result, t):
        ts = (t or 0) - self.offset
        self.n_reconexiones += 1
        for topic, data in result.items():
            topic, data = self.normalizar(topic, data)
            if data is None:
                continue
            nuevo = fusionar(None, data)
            if topic == "TimingData":
                lines = _d(nuevo).get("Lines")
                if isinstance(lines, dict) and lines:
                    viejas = _d(_d(self.temas.get("TimingData")).get("Lines"))
                    for num, ln in lines.items():
                        d = diff(viejas.get(num), ln)
                        if d:
                            self.linea(num, d, copy.deepcopy(viejas.get(num)), ln, ts, snapshot=True)
            elif topic == "TimingAppData":
                self._stints_vivo(_d(nuevo).get("Lines"), ts)
            elif topic == "WeatherData":
                self._weather(nuevo, ts)
            elif topic == "TimingStats" and self.t_primer_td is None:
                self._pb_previo(_d(nuevo).get("Lines"), ts, inicial=True)
            if topic == "RaceControlMessages" and self.temas.get(topic):
                self.temas[topic] = fusionar(self.temas[topic], data)  # no perder mensajes viejos
            else:
                self.temas[topic] = nuevo

    def feed(self, topic, data, ts):
        topic, data = self.normalizar(topic, data)
        if data is None:
            return
        if topic == "TimingData":
            lines = _d(data).get("Lines")
            td = self.temas.setdefault("TimingData", {})
            td_lines = td.setdefault("Lines", {})
            for num, dl in (lines or {}).items():
                viejo = copy.deepcopy(td_lines.get(num))
                td_lines[num] = fusionar(td_lines.get(num), dl)
                self.linea(num, dl, viejo, td_lines[num], ts)
            for k, v in _d(data).items():
                if k != "Lines":
                    td[k] = fusionar(td.get(k), v)
            return
        if topic == "TimingStats" and self.t_primer_td is None:
            self._pb_previo(_d(data).get("Lines"), ts)
        if topic == "TimingAppData":
            self._stints_vivo(_d(data).get("Lines"), ts)
        if topic == "WeatherData":
            self._weather(data, ts)
        self.temas[topic] = fusionar(self.temas.get(topic), data)

    def _weather(self, data, ts):
        w = _d(data)
        def f(k):
            try:
                return float(w.get(k))
            except (TypeError, ValueError):
                return None
        if f("TrackTemp") is None:
            return
        self.weather.append({"date": iso(ts), "session_key": SK, "track_temperature": f("TrackTemp"),
                             "wind_direction": entero(w.get("WindDirection")), "air_temperature": f("AirTemp"),
                             "meeting_key": MK, "humidity": f("Humidity"), "wind_speed": f("WindSpeed"),
                             "pressure": f("Pressure"), "rainfall": entero(w.get("Rainfall")) or 0})

    def _pb_previo(self, lines, ts, inicial=False):
        for num, ln in _d(lines).items():
            pb = _d(_d(ln).get("PersonalBestLapTime"))
            tv = tiempo_vuelta(pb.get("Value")) if "Value" in pb else None
            if tv:
                self.pb_previos.setdefault(num, []).append((ts, tv, entero(pb.get("Lap")), inicial))

    def _stints_vivo(self, lines, ts):
        """Registra la vuelta en curso cuando aparece un stint nuevo en vivo (después del primer TimingData)."""
        if self.t_primer_td is None:
            return
        for num, ln in _d(lines).items():
            p = self.pilotos.get(num)
            if p is None or p.n is None:
                continue
            for i, st in items(_d(ln).get("Stints")):
                if (num, i) not in self.stint_vivo and isinstance(st, dict) and "TotalLaps" in st:
                    previos = _d(_d(_d(self.temas.get("TimingAppData")).get("Lines")).get(num)).get("Stints")
                    if dict(items(previos)).get(i) is None:
                        self.stint_vivo[(num, i)] = p.n

    # ------------------------------------------------------------------ TimingData por piloto
    def linea(self, num, dl, viejo, nuevo, ts, snapshot=False):
        dl = _d(dl)
        p = self.pilotos.get(num)
        if p is None:
            nseg = [len(items(_d(s).get("Segments"))) or 0 for _, s in items(_d(nuevo).get("Sectors"))] + [0, 0, 0]
            p = self.pilotos[num] = Piloto(num, nseg[:3])
        if p.n is None:
            # primer dato de este piloto: estado inicial (lo previo no está en la grabación)
            if self.t_primer_td is None:
                self.t_primer_td = ts
            n0 = entero(_d(nuevo).get("NumberOfLaps")) or 0
            p.n = n0
            p.base = {"n0": n0, "ts": ts, "in_pit": bool(_d(nuevo).get("InPit")),
                      "best": copy.deepcopy(_d(nuevo).get("BestLapTime")),
                      "last": valor(_d(nuevo).get("LastLapTime")),
                      "sectores": [valor(s) for _, s in items(_d(nuevo).get("Sectors"))],
                      "speeds": {k: valor(v) for k, v in _d(_d(nuevo).get("Speeds")).items()}}
            if n0 >= 1:
                p.nuevo_buf(n0, ts, False, parcial=True)
                if p.base["in_pit"]:
                    # en el pit: la vuelta n0 (de entrada) ya terminó y sus datos siguen en la línea
                    b = p.buf
                    b["lap_time"] = tiempo_vuelta(p.base["last"])
                    for i, s in enumerate(p.base["sectores"][:3]):
                        b["s"][i] = tiempo_vuelta(s)
                    for k in ("I1", "I2", "ST"):
                        b["sp"][k] = entero(p.base["speeds"].get(k))
            return

        b = p.buf
        en_ventana = (p.ultimo_cierre is not None and ts - p.ultimo_cierre[0] < 4.0 and b is not None
                      and b["s"][0] is None and not snapshot)
        cerrada = p.laps.get(p.ultimo_cierre[1]) if p.ultimo_cierre else None

        # reset de segmentos de inicio de vuelta (S2 completo en 0)
        sec = _d(dl.get("Sectors")) if isinstance(dl.get("Sectors"), dict) else dict(
            (str(i), s) for i, s in items(dl.get("Sectors")))
        s2segs = items(_d(sec.get("1")).get("Segments"))
        es_reset = len(s2segs) >= 4 and all(_d(v).get("Status") == 0 for _, v in s2segs)
        nn = entero(dl.get("NumberOfLaps"))
        incrementa = nn is not None and nn > (p.n or 0)

        for si in range(3):
            sd = sec.get(str(si))
            if not isinstance(sd, dict):
                continue
            if "Value" in sd:
                v = tiempo_vuelta(valor(sd.get("Value")))
                if v is not None and b is not None:
                    if si == 2 and en_ventana and cerrada is not None and cerrada["duration_sector_3"] is None:
                        cerrada["duration_sector_3"] = v
                        self.tardios += 1
                    else:
                        b["s"][si] = v
            for j, sg in items(sd.get("Segments")):
                st = _d(sg).get("Status")
                if not st:
                    continue
                if es_reset and not incrementa and (p.ultimo_cierre is None or ts - p.ultimo_cierre[0] > 15):
                    # reset antes del incremento (salida de pits): pertenece a la vuelta que va a empezar
                    p.reset_pend = (ts, {si: {j: st}}) if p.reset_pend is None or ts - p.reset_pend[0] > 1 else p.reset_pend
                    p.reset_pend[1].setdefault(si, {})[j] = st
                elif es_reset and incrementa:
                    continue  # se aplica después de abrir la vuelta nueva
                elif b is not None:
                    b["seg"][si][j] = st
        for k, sv in _d(dl.get("Speeds")).items():
            if k in ("I1", "I2", "ST") and isinstance(sv, dict) and "Value" in sv:
                v = entero(valor(sv.get("Value")))
                if v is not None and b is not None:
                    b["sp"][k] = v
        llt = _d(dl.get("LastLapTime"))
        if "Value" in llt:
            v = tiempo_vuelta(valor(llt.get("Value")))
            if v is not None:
                if en_ventana and cerrada is not None and cerrada["lap_duration"] is None and b["lap_time"] is None:
                    cerrada["lap_duration"] = v
                    self.tardios += 1
                elif b is not None:
                    b["lap_time"] = v

        if incrementa:
            pit_out = bool(_d(nuevo).get("PitOut")) or bool(dl.get("PitOut"))
            for k in range(p.n, nn):
                if k >= 1:
                    if p.buf is None or p.buf["lap"] != k:
                        p.nuevo_buf(k, None, False, parcial=True)
                    p.cerrar(ts)
                    if k < nn - 1:
                        p.origen[k] = "hueco_reconexion"
                p.nuevo_buf(k + 1, ts, pit_out if k + 1 == nn else False)
            p.n = nn
            if es_reset:
                for si in range(3):
                    for j, sg in items(_d(sec.get(str(si))).get("Segments")):
                        if _d(sg).get("Status"):
                            p.buf["seg"][si][j] = _d(sg)["Status"]
            elif p.reset_pend is not None and ts - p.reset_pend[0] < 10:
                for si, d in p.reset_pend[1].items():
                    p.buf["seg"][si].update(d)
            p.reset_pend = None

    # ------------------------------------------------------------------ final
    def finalizar(self):
        apps = _d(_d(self.temas.get("TimingAppData")).get("Lines"))
        stats = _d(_d(self.temas.get("TimingStats")).get("Lines"))
        td = _d(_d(self.temas.get("TimingData")).get("Lines"))
        stints_out, notas = [], []
        for num, p in self.pilotos.items():
            if p.buf is not None and p.buf["lap"] and p.buf["lap"] not in p.laps:
                p.cerrar(None)  # vuelta en curso al final (entrada a pits)
            n_final = entero(_d(td.get(num)).get("NumberOfLaps")) or p.n or 0
            if n_final == 0:
                continue
            # ---- stints
            sts = [s for _, s in sorted(items(_d(apps.get(num)).get("Stints")), key=lambda x: x[0])
                   if isinstance(s, dict)]
            ini = 1
            filas = []
            for i, s in enumerate(sts):
                largo = max(0, (entero(s.get("TotalLaps")) or 0) - (entero(s.get("StartLaps")) or 0))
                ls = self.stint_vivo.get((num, i), ini)
                filas.append({"meeting_key": MK, "session_key": SK, "stint_number": i + 1, "driver_number": int(num),
                              "lap_start": ls, "lap_end": None,
                              "compound": (s.get("Compound") or "UNKNOWN").upper(),
                              "tyre_age_at_start": entero(s.get("StartLaps")) or 0,
                              "_lap_start_acum": ini, "_largo": largo})
                ini = ls + largo
            for i, f in enumerate(filas):
                f["lap_end"] = (filas[i + 1]["lap_start"] - 1) if i + 1 < len(filas) else max(n_final, f["lap_start"])
                if (f["_lap_start_acum"] != f["lap_start"]):
                    notas.append(f"#{num} stint {f['stint_number']}: lap_start vivo {f['lap_start']} vs acumulado "
                                 f"{f['_lap_start_acum']}")
            inicios_stint = {f["lap_start"] for f in filas}
            stints_out += [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas]

            # ---- vueltas previas al primer TimingData: marcadores + tiempos conocidos
            n0 = p.base["n0"] if p.base else 0
            primera_viva = min([k for k, o in p.origen.items() if o in ("vivo", "vivo_parcial")] or [n0])
            for k in range(1, n_final + 1):
                if k not in p.laps:
                    p.laps[k] = {"meeting_key": MK, "session_key": SK, "driver_number": int(num), "lap_number": k,
                                 "date_start": None, "duration_sector_1": None, "duration_sector_2": None,
                                 "duration_sector_3": None, "i1_speed": None, "i2_speed": None,
                                 "is_pit_out_lap": k in inicios_stint or k == 1, "lap_duration": None,
                                 "segments_sector_1": None, "segments_sector_2": None, "segments_sector_3": None,
                                 "st_speed": None}
                    p.origen[k] = "marcador"
            for k, o in p.origen.items():
                if o == "vivo_parcial" or k == 1:  # vuelta en curso al primer TimingData: no se vio la salida
                    p.laps[k]["is_pit_out_lap"] = k in inicios_stint or k == 1
            previos = [k for k in p.laps if p.origen.get(k) == "marcador" and k < primera_viva]

            def poner(lap, tv, fuente):
                if lap in previos and p.laps[lap]["lap_duration"] is None:
                    p.laps[lap]["lap_duration"] = tv
                    p.origen[lap] = "estado_inicial:" + fuente
                    return True
                return lap in p.laps and p.laps[lap]["lap_duration"] == tv

            def poner_cerca(lap, tv, fuente):
                """lap sugerido; si choca, el marcador libre más cercano (los números del feed varían ±1)."""
                if any(l["lap_duration"] is not None and abs(l["lap_duration"] - tv) < 0.0005 for l in p.laps.values()):
                    return  # ese tiempo ya está (p. ej. la vuelta de entrada del estado inicial)
                if lap is not None and poner(lap, tv, fuente):
                    return
                if any(p.laps[k]["lap_duration"] == tv for k in p.laps):
                    return
                libres = [k for k in previos if p.laps[k]["lap_duration"] is None and not p.laps[k]["is_pit_out_lap"]]
                if libres:
                    k = min(libres, key=lambda k: abs(k - (lap or primera_viva)))
                    poner(k, tv, fuente + "(reubicada)")

            if p.base and p.base["last"] and not p.base["in_pit"] and n0 >= 2:
                poner_cerca(n0 - 1, tiempo_vuelta(p.base["last"]), "LastLapTime")
            best = _d(p.base["best"]) if p.base else {}
            if tiempo_vuelta(best.get("Value")):
                poner_cerca(entero(best.get("Lap")), tiempo_vuelta(best.get("Value")), "BestLapTime")
            for s in sts:
                if tiempo_vuelta(s.get("LapTime")) and entero(s.get("LapNumber")):
                    ln = entero(s["LapNumber"]) - 1
                    if ln < primera_viva:
                        poner_cerca(ln, tiempo_vuelta(s["LapTime"]), "TimingAppData.Stints.LapTime")
            for (ts, tv, lap, inicial) in self.pb_previos.get(num, []):
                poner_cerca(lap, tv, "TimingStats.PersonalBestLapTime")

        # ---- vueltas borradas por dirección de carrera
        borradas = []
        rc = _d(self.temas.get("RaceControlMessages")).get("Messages")
        for _, m in items(rc):
            txt = str(_d(m).get("Message") or "").upper()
            if "DELETED" not in txt or "REINSTATED" in txt:
                continue
            mc, mt, ml = _RE_CAR.search(txt), _RE_TIME.search(txt), _RE_LAP.search(txt)
            if not mc or mc.group(1) not in self.pilotos:
                continue
            p = self.pilotos[mc.group(1)]
            t_msg = parse_iso(_d(m).get("Utc"))
            tv = tiempo_vuelta(mt.group(1)) if mt else None
            lap_rc = entero(ml.group(1)) if ml else None
            cand = None
            if tv is not None:
                cs = [k for k, l in p.laps.items() if l["lap_duration"] is not None and abs(l["lap_duration"] - tv) < 0.0005]
                if cs:
                    cand = min(cs, key=lambda k: abs(k - ((lap_rc or k + 1) - 1)))
            elif lap_rc is not None:
                for k in (lap_rc - 1, lap_rc):
                    if k in p.laps:
                        cand = k
                        break
            borradas.append({"driver_number": int(mc.group(1)), "mensaje": _d(m).get("Message"), "utc": _d(m).get("Utc"),
                             "tiempo": tv, "lap_rc": lap_rc, "lap_reconstruida": cand,
                             "lap_duration_original": p.laps[cand]["lap_duration"] if cand else None})
            if cand is not None:
                p.laps[cand]["lap_duration"] = None
                p.origen[cand] = (p.origen.get(cand) or "") + "+borrada"

        laps = []
        for num, p in self.pilotos.items():
            laps += [p.laps[k] for k in sorted(p.laps)]
        laps.sort(key=lambda l: (l["lap_number"], l["date_start"] or "", l["driver_number"]))
        return laps, stints_out, borradas, notas


def validar(rec, laps, stints, salida):
    import pandas as pd
    td = _d(_d(rec.temas.get("TimingData")).get("Lines"))
    stats = _d(_d(rec.temas.get("TimingStats")).get("Lines"))
    dl = _d(rec.temas.get("DriverList"))
    df = pd.DataFrame(laps)
    filas = []
    for num in sorted(td, key=lambda k: entero(_d(stats.get(k)).get("PersonalBestLapTime", {}).get("Position")) or 99):
        tla = _d(dl.get(num)).get("Tla")
        g = df[df.driver_number == int(num)]
        fin_stint = {s["lap_end"] for s in stints if s["driver_number"] == int(num)}
        gv = g[(g.is_pit_out_lap != True) & ~g.lap_number.isin(fin_stint)]  # BestLapTime no cuenta salida/entrada
        pb_stats = tiempo_vuelta(_d(_d(stats.get(num)).get("PersonalBestLapTime")).get("Value"))
        pb_td = tiempo_vuelta(_d(_d(td.get(num)).get("BestLapTime")).get("Value"))
        best = gv.lap_duration.min() if len(gv) else None
        best_lap = int(gv.loc[gv.lap_duration.idxmin(), "lap_number"]) if len(gv) and gv.lap_duration.notna().any() else None
        best_todas = g.lap_duration.min() if len(g) else None
        p = rec.pilotos.get(num)
        filas.append({"num": int(num), "tla": tla,
                      "pos_stats": entero(_d(_d(stats.get(num)).get("PersonalBestLapTime")).get("Position")),
                      "best_rec": None if best is None or pd.isna(best) else round(float(best), 3),
                      "lap_best_rec": best_lap,
                      "best_incl_entrada_salida": None if best_todas is None or pd.isna(best_todas) else round(float(best_todas), 3),
                      "lap_best_td": entero(_d(_d(td.get(num)).get("BestLapTime")).get("Lap")),
                      "pb_timingstats": pb_stats, "best_timingdata": pb_td,
                      "ok_best": (pb_stats is None and (best is None or pd.isna(best))) or (
                          best is not None and pb_stats is not None and abs(best - pb_stats) < 0.0005
                          and pb_td is not None and abs(best - pb_td) < 0.0005),
                      "n_laps_rec": len(g), "n_laps_td": entero(_d(td.get(num)).get("NumberOfLaps")),
                      "n0_inicio": p.base["n0"] if p and p.base else None,
                      "con_tiempo": int(g.lap_duration.notna().sum()),
                      "con_tiempo_y_3_sectores": int((g.lap_duration.notna() & g.duration_sector_1.notna()
                                                      & g.duration_sector_2.notna() & g.duration_sector_3.notna()).sum()),
                      "marcadores": sum(1 for o in (p.origen.values() if p else []) if o == "marcador")})
    val = pd.DataFrame(filas)
    print("\n=== (1)+(2) mejor vuelta y número de vueltas por piloto ===")
    print(val.to_string(index=False))
    print(f"\nmejor vuelta OK: {int(val.ok_best.sum())}/{len(val)} | vueltas = NumberOfLaps: "
          f"{int((val.n_laps_rec == val.n_laps_td).sum())}/{len(val)}")

    # (3) features_practica sobre un CACHE temporal
    import tempfile
    import modelo_qualy_austin as mq
    tmp = Path(tempfile.mkdtemp(prefix="cache_fp3_", dir=str(salida)))
    for nombre in ("laps", "stints", "weather"):
        src = salida / f"{nombre}_{SK}.json"
        (tmp / f"{nombre}_{SK}.json").write_text(src.read_text())
    cache_orig = mq.CACHE
    mq.CACHE = tmp
    try:
        feats = mq.features_practica(SK, "fp3")
    finally:
        mq.CACHE = cache_orig
    feats["tla"] = feats.driver_number.map(lambda n: _d(dl.get(str(n))).get("Tla"))
    feats["pos_timingstats"] = feats.driver_number.map(
        lambda n: entero(_d(_d(stats.get(str(n))).get("PersonalBestLapTime")).get("Position")))
    cols = ["driver_number", "tla", "pos_timingstats", "fp3_best", "fp3_gap", "fp3_rank", "fp3_long_gap",
            "fp3_long_rank", "fp3_laps", "fp3_soft_gap", "fp3_ideal_rank", "fp3_track_temp"]
    feats = feats[[c for c in cols if c in feats.columns]].sort_values(["fp3_rank", "pos_timingstats"])
    print(f"\n=== (3) features_practica(11399, 'fp3') con CACHE={tmp} ===")
    print(feats.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    ok = feats.dropna(subset=["fp3_rank", "pos_timingstats"])
    iguales = int((ok.fp3_rank == ok.pos_timingstats).sum())
    print(f"fp3_rank == posición TimingStats: {iguales}/{len(ok)} (pilotos con tiempo)")
    return val, feats, tmp


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("crudos", nargs="+", help="grabaciones jsonl en orden cronológico")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--validar", action="store_true")
    args = ap.parse_args(argv)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    rec = Reconstructor()
    for c in args.crudos:
        rec.procesar_archivo(c)
    laps, stints, borradas, notas = rec.finalizar()
    for l in laps:  # OpenF1 da milésimas exactas (evitar 80.46000000000001)
        for k in ("duration_sector_1", "duration_sector_2", "duration_sector_3", "lap_duration"):
            if l[k] is not None:
                l[k] = round(l[k], 3)
    for b in borradas:
        if b["lap_duration_original"] is not None:
            b["lap_duration_original"] = round(b["lap_duration_original"], 3)
    (salida / f"laps_{SK}.json").write_text(json.dumps(laps))
    (salida / f"stints_{SK}.json").write_text(json.dumps(stints))
    (salida / f"weather_{SK}.json").write_text(json.dumps(rec.weather))
    origen = {f"{num}:{k}": o for num, p in rec.pilotos.items() for k, o in sorted(p.origen.items())}
    meta = {"session_key": SK, "fuentes": [str(c) for c in args.crudos],
            "primer_timingdata_utc": iso(rec.t_primer_td), "estados_completos": rec.n_reconexiones,
            "atribuciones_tardias": rec.tardios, "borradas": borradas, "notas_stints": notas,
            "weather": "sin WeatherData en la grabación" if not rec.weather else f"{len(rec.weather)} muestras",
            "origen_vueltas": origen}
    print(f"vueltas: {len(laps)} | pilotos: {len({l['driver_number'] for l in laps})} | stints: {len(stints)} | "
          f"weather: {len(rec.weather)} | primer TimingData: {iso(rec.t_primer_td)} | estados completos: "
          f"{rec.n_reconexiones} | atribuciones tardías: {rec.tardios}")
    print(f"borradas: {sum(1 for b in borradas if b['lap_reconstruida'])}/{len(borradas)} ubicadas")
    for b in borradas:
        print(f"  #{b['driver_number']} {b['tiempo']} RC lap {b['lap_rc']} -> lap {b['lap_reconstruida']} "
              f"({b['lap_duration_original']})")
    for n in notas:
        print("  stint:", n)
    if args.validar:
        val, feats, tmp = validar(rec, laps, stints, salida)
        meta["validacion"] = val.to_dict(orient="records")
        meta["features_fp3"] = json.loads(feats.to_json(orient="records"))
        meta["cache_temporal"] = str(tmp)
    (salida / f"meta_{SK}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print("escrito en", salida)


if __name__ == "__main__":
    main()
