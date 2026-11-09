"""Descarga y cachea datos de OpenF1 (2023-2026) y Jolpica (historial por temporada y por circuito).

Uso:
  python3 descarga_datos.py                        # todo lo que falte en cache
  python3 descarga_datos.py gp 2026 1298 rodriguez # refresca la temporada y el GP objetivo (México)
"""
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
            if r.status_code in (401, 403):   # OpenF1 bloqueado (sesión en vivo / sin acceso): no insistir 8 veces
                raise RuntimeError(f"{url}: OpenF1 respondió {r.status_code}")
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
            if s["session_name"] in ("Practice 1", "Practice 2", "Practice 3") and not s.get("is_cancelled"):
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


def descargar_circuito(circuito):
    """Histórico de qualys de un circuito de Jolpica (p.ej. 'americas', 'rodriguez')."""
    prefijo = "jolpica_cota" if circuito == "americas" else f"jolpica_circ_{circuito}"
    off = 0
    while True:
        d = get(f"{JOLPICA}/circuits/{circuito}/qualifying.json?limit=100&offset={off}", f"{prefijo}_{off}")
        off += 100
        if off >= int(d["MRData"]["total"]):
            break


RESPALDO = CACHE / "_respaldo_refresco"


def refrescar_temporada(año, meeting_key):
    """Aparta (no borra) la cache de la temporada en curso y del GP objetivo para volver a bajarla con lo más reciente.
    Antes comprueba que OpenF1 responde: con 401/403 (sesión en vivo) no se toca nada. Lo apartado queda en
    cache/_respaldo_refresco/ y restaurar_respaldo() lo devuelve si la descarga falla a medias."""
    r = requests.get(f"{OPENF1}/sessions?meeting_key={meeting_key}", timeout=60)
    ses = r.json() if r.status_code == 200 else None
    if not isinstance(ses, list) or not ses:
        raise SystemExit(f"OpenF1 respondió {r.status_code} para el meeting {meeting_key}: no se toca la cache "
                         "(reintentar más tarde)")
    restaurar_respaldo()          # restos de un refresco anterior que falló
    RESPALDO.mkdir(exist_ok=True)
    apartar = [CACHE / f"{p}.json" for p in (f"sessions_{año}", f"results_{año}", f"drivers_{año}")]
    apartar += list(CACHE.glob(f"jolpica_*_{año}_*.json"))
    for s in ses:
        apartar += list(CACHE.glob(f"*_{s['session_key']}.json"))
    for p in apartar:
        if p.exists():
            p.replace(RESPALDO / p.name)


def restaurar_respaldo(devolver=True):
    """devolver=True (la descarga falló): devuelve a la cache lo apartado que no se pudo volver a bajar.
    devolver=False (salió bien): descarta lo apartado, como el borrado original. Devuelve cuántos volvieron."""
    if not RESPALDO.exists():
        return 0
    n = 0
    for p in RESPALDO.glob("*.json"):
        if devolver and not (CACHE / p.name).exists():
            p.replace(CACHE / p.name)
            n += 1
        else:
            p.unlink()
    RESPALDO.rmdir()
    return n


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
    elif sys.argv[1:2] == ["gp"]:
        # python3 descarga_datos.py gp <año> <meeting_key> <circuito_jolpica>
        año, mk, circ = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
        refrescar_temporada(año, mk)
        try:
            descargar()
            descargar_circuito(circ)
        except BaseException:     # falló a medias (p. ej. 401): vuelve lo que no se pudo bajar de nuevo
            print(f"  restaurados {restaurar_respaldo()} archivos de cache que no se pudieron volver a bajar")
            raise
        restaurar_respaldo(devolver=False)
    else:
        descargar([int(x) for x in sys.argv[1:]])
