"""Descarga y cachea datos de OpenF1 (2023-2026) y Jolpica (histórico COTA)."""
import json, time, os, sys
from pathlib import Path
import requests

CACHE = Path(__file__).parent / "cache"
CACHE.mkdir(exist_ok=True)
OPENF1 = "https://api.openf1.org/v1"
JOLPICA = "https://api.jolpi.ca/ergast/f1"
AÑOS = [2023, 2024, 2025, 2026]


def get(url, nombre, pausa=0.6):
    f = CACHE / f"{nombre}.json"
    if f.exists():
        return json.loads(f.read_text())
    for intento in range(8):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 429:
                time.sleep(5 * (intento + 1)); continue
            if r.status_code == 404:
                data = []
            else:
                r.raise_for_status(); data = r.json()
            if isinstance(data, dict) and "detail" in data:
                data = []
            f.write_text(json.dumps(data))
            time.sleep(pausa)
            return data
        except requests.RequestException as e:
            print("  reintento", nombre, e); time.sleep(3 * (intento + 1))
    raise RuntimeError(url)


def descargar(forzar_actual=None):
    """forzar_actual: session_keys a re-descargar (sesiones del fin de semana en curso)."""
    for sk in forzar_actual or []:
        for p in CACHE.glob(f"*_{sk}.json"):
            p.unlink()
    for año in AÑOS:
        ses = get(f"{OPENF1}/sessions?year={año}", f"sessions_{año}")
        keys = [s["session_key"] for s in ses]
        lo, hi = min(keys), max(keys)
        print(año, len(ses), "sesiones")
        get(f"{OPENF1}/session_result?session_key>={lo}&session_key<={hi}", f"results_{año}")
        get(f"{OPENF1}/drivers?session_key>={lo}&session_key<={hi}", f"drivers_{año}")
        for s in ses:
            if s["session_name"] in ("Practice 1", "Practice 2") and not s.get("is_cancelled"):
                sk = s["session_key"]
                get(f"{OPENF1}/laps?session_key={sk}", f"laps_{sk}")
                get(f"{OPENF1}/stints?session_key={sk}", f"stints_{sk}")
                get(f"{OPENF1}/weather?session_key={sk}", f"weather_{sk}")
    # Histórico de qualys en COTA (2012-2025)
    filas, off = [], 0
    while True:
        d = get(f"{JOLPICA}/circuits/americas/qualifying.json?limit=100&offset={off}", f"jolpica_cota_{off}")
        races = d["MRData"]["RaceTable"]["Races"]
        filas += races
        off += 100
        if off >= int(d["MRData"]["total"]):
            break
    print("COTA histórico:", len(filas), "bloques")
    descargar_jolpica()


def descargar_jolpica(desde=2018, hasta=2026):
    """Qualys y carreras de todas las temporadas (para forma e historial por circuito)."""
    for año in range(desde, hasta + 1):
        for tipo in ("qualifying", "results"):
            off = 0
            while True:
                d = get(f"{JOLPICA}/{año}/{tipo}.json?limit=100&offset={off}",
                        f"jolpica_{tipo}_{año}_{off}", pausa=0.4)
                off += 100
                if off >= int(d["MRData"]["total"]):
                    break
        print("Jolpica", año, "ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["jolpica"]:
        descargar_jolpica()
    else:
        descargar([int(x) for x in sys.argv[1:]])
