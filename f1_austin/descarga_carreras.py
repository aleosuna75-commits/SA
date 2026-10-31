"""Descarga (con cache) vueltas, stints y paradas en pits de las CARRERAS pasadas (OpenF1 2023-2026).

Se usan para la parte de estrategia del modelo de carrera (paradas típicas y pérdida en pits por circuito,
degradación observada en carrera). Mismo esquema de cache que descarga_datos.py (cache/<nombre>.json, pausa
entre llamadas y reintentos ante 429). Prefijos distintos a los de prácticas para no mezclar archivos:
  cache/race_laps_<sk>.json, cache/race_stints_<sk>.json, cache/race_pit_<sk>.json

Uso:  python3 descarga_carreras.py            # todas las carreras ya corridas que falten en cache
      python3 descarga_carreras.py 11396      # forzar una carrera (borra y vuelve a bajar)
"""
import json
import sys
from datetime import datetime, timezone

from descarga_datos import CACHE, OPENF1, AÑOS, get


def carreras_pasadas():
    ahora = datetime.now(timezone.utc)
    out = []
    for a in AÑOS:
        f = CACHE / f"sessions_{a}.json"
        if not f.exists():
            continue
        for s in json.loads(f.read_text()):
            if s["session_name"] != "Race" or s.get("is_cancelled"):
                continue
            fin = datetime.fromisoformat(s["date_end"]) if s.get("date_end") else None
            if fin and fin < ahora:
                out.append(s["session_key"])
    return out


def descargar(forzar=()):
    for sk in forzar:
        for pref in ("race_laps", "race_stints", "race_pit"):
            (CACHE / f"{pref}_{sk}.json").unlink(missing_ok=True)
    claves = carreras_pasadas()
    for i, sk in enumerate(claves):
        get(f"{OPENF1}/stints?session_key={sk}", f"race_stints_{sk}", pausa=0.5)
        get(f"{OPENF1}/pit?session_key={sk}", f"race_pit_{sk}", pausa=0.5)
        get(f"{OPENF1}/laps?session_key={sk}", f"race_laps_{sk}", pausa=0.5)
        print(f"  carreras {i + 1}/{len(claves)}", end="\r", flush=True)
    print(f"\n{len(claves)} carreras en cache")


if __name__ == "__main__":
    descargar([int(x) for x in sys.argv[1:]])
