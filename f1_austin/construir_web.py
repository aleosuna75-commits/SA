"""Construye la página única de pronósticos (todos los GP) a partir de web/plantilla.html.

La página muestra el GP 'actual' de meta.json (o el del hash: #brasil2026) y cambia de GP con el menú. Con base de datos
(Artifact de claude.ai) lee en vivo meta/actual, bitacora/actual y gp|live|postqualy|carrera|vueltas|postcarrera|historial/<slug>;
sin base (Netlify, archivo local, viewer sin sesión) usa el respaldo que este script incrusta en <script type="application/json" id="datos">:

    {"meta": gps/meta.json,
     "catalogo": {slug: {nombre, nombre_corto, circuito, circuito_corto, ciudad, pais, tema, tz, etq, vueltas,
                         sesiones: {FP1, FP2, FP3, Q, R: ISO UTC}, historial: [{anio, acr, equipo}]}},
     "temas": {tema: web/temas/<tema>.json},
     "gps": {slug: {gp, live, postqualy, carrera, vueltas, postcarrera, historial}},   # desde gps/<slug>/*.json (contrato multi-GP)
     "bitacora": modelos/bitacora.json}   # mejora continua: campeones, evolución por GP, cambios adoptados, candidatos

El catálogo junta: CURADO (abajo: zona horaria, etiqueta de hora, vueltas, nombre corto), gps/<slug>/config.json,
meta.json, cache/sessions_<año>.json (horarios de OpenF1) y el historial de poles del circuito (cache de Jolpica).
También escribe en la cabecera los tokens y las tipografías del tema del GP actual (primer cuadro sin parpadeo).

Uso:
  python3 construir_web.py                                   # -> web/index.html (para el Artifact: sin doctype)
  python3 construir_web.py --salida ../sitio_f1/index.html --documento      # Netlify (con doctype)
  python3 construir_web.py --gps /ruta/a/gps --salida /tmp/prueba.html      # otra carpeta de datos (pruebas)
  python3 construir_web.py --actual lasvegas2026             # fuerza el GP inicial del respaldo (meta.actual)
  python3 construir_web.py --gps X/gps --bitacora X/modelos/bitacora.json   # bitácora: por defecto <carpeta de --gps>/../modelos/
Imágenes: web/img/<tema>/ (rutas relativas img/<tema>/…); publicar la carpeta web/img junto a la página.
"""
import argparse
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
WEB = BASE / "web"
CACHE = BASE / "cache"

# Lo que no sale de OpenF1/Jolpica: zona horaria IANA, etiqueta de hora, vueltas de la carrera y nombres cortos.
CURADO = {
    "mexico2026": {"meeting_key": 1298, "nombre": "Gran Premio de la Ciudad de México", "nombre_corto": "México",
                   "circuito": "Autódromo Hermanos Rodríguez", "circuito_corto": "el Autódromo", "ciudad": "Ciudad de México",
                   "pais": "México", "tema": "muertos", "tz": "America/Mexico_City", "etq": "CDMX", "vueltas": 71,
                   "circuito_jolpica": "rodriguez"},
    "brasil2026": {"meeting_key": 1299, "nombre": "Gran Premio de São Paulo", "nombre_corto": "São Paulo",
                   "circuito": "Autódromo José Carlos Pace", "circuito_corto": "Interlagos", "ciudad": "São Paulo",
                   "pais": "Brasil", "tema": "brasil", "tz": "America/Sao_Paulo", "etq": "hora de São Paulo", "vueltas": 71,
                   "circuito_jolpica": "interlagos"},
    "lasvegas2026": {"meeting_key": 1300, "nombre": "Gran Premio de Las Vegas", "nombre_corto": "Las Vegas",
                     "circuito": "Las Vegas Strip Circuit", "circuito_corto": "el Strip", "ciudad": "Las Vegas",
                     "pais": "Estados Unidos", "tema": "lasvegas", "tz": "America/Los_Angeles", "etq": "hora de Las Vegas",
                     "vueltas": 50, "circuito_jolpica": "vegas"},
    "qatar2026": {"meeting_key": 1301, "nombre": "Gran Premio de Qatar", "nombre_corto": "Qatar",
                  "circuito": "Circuito Internacional de Lusail", "circuito_corto": "Lusail", "ciudad": "Lusail",
                  "pais": "Qatar", "tema": "qatar", "tz": "Asia/Qatar", "etq": "hora de Doha", "vueltas": 57,
                  "circuito_jolpica": "losail"},
    "abudhabi2026": {"meeting_key": 1302, "nombre": "Gran Premio de Abu Dabi", "nombre_corto": "Abu Dabi",
                     "circuito": "Circuito de Yas Marina", "circuito_corto": "Yas Marina", "ciudad": "Abu Dabi",
                     "pais": "Emiratos Árabes Unidos", "tema": "abudhabi", "tz": "Asia/Dubai", "etq": "hora de Abu Dabi",
                     "vueltas": 58, "circuito_jolpica": "yas_marina"},
}
# Archivo de gps/<slug>/ -> clave del doc (gp/<slug>, live/<slug>, ...)
ARCHIVOS = {"gp": "gp.json", "live": "live_qualy.json", "postqualy": "post_qualy.json", "carrera": "carrera.json",
            "vueltas": "vueltas.json", "postcarrera": "post_carrera.json", "historial": "historial.json"}
SESIONES_OPENF1 = {"Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3", "Qualifying": "Q", "Race": "R",
                   "Sprint": "SPR", "Sprint Qualifying": "SQ", "Sprint Shootout": "SQ"}
SLUG_OK = re.compile(r"^[a-z0-9-]{2,40}$")


def leer(ruta):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        return None


# Validación mínima de cada doc (la misma idea que la página: si no tiene forma, no se incrusta)
def _con_acr(lista):
    return isinstance(lista, list) and any(isinstance(x, dict) and x.get("acr") for x in lista)


VALIDOS = {
    "gp": lambda d: isinstance(d.get("pilotos"), list) and len(d["pilotos"]) > 0,
    "live": lambda d: isinstance(d.get("pilotos"), list),
    "postqualy": lambda d: _con_acr(d.get("filas")) or bool(d.get("top10_real")),
    "carrera": lambda d: _con_acr(d.get("pilotos")),
    "vueltas": lambda d: _con_acr(d.get("trazas")) or _con_acr(d.get("estrategias")),
    "postcarrera": lambda d: _con_acr(d.get("filas")) or bool(d.get("top10_real")),
    "historial": lambda d: isinstance(d.get("fases"), list) and any(isinstance(f, dict) and f.get("fase") for f in d["fases"]),
}


def bitacora_valida(d):
    """modelos/bitacora.json (doc bitacora/actual): basta con que traiga alguna de sus partes con forma."""
    return isinstance(d, dict) and (
        isinstance(d.get("campeones"), dict) or isinstance(d.get("evolucion"), list)
        or isinstance(d.get("cambios"), list) or isinstance(d.get("candidatos"), list))


def docs_gp(carpeta):
    r = {}
    for k, nombre in ARCHIVOS.items():
        d = leer(carpeta / nombre)
        if isinstance(d, dict) and VALIDOS[k](d):
            r[k] = d
    return r


def sesiones_openf1(meeting_key, anio):
    r = {}
    for s in leer(CACHE / f"sessions_{anio}.json") or []:
        if s.get("meeting_key") == meeting_key and s.get("session_name") in SESIONES_OPENF1 and s.get("date_start"):
            t = datetime.fromisoformat(s["date_start"]).astimezone(timezone.utc)
            r[SESIONES_OPENF1[s["session_name"]]] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    return r


def sesiones_config(lista):
    r = {}
    for s in lista or []:
        if isinstance(s, dict) and s.get("inicio_utc"):
            k = str(s.get("clave", "")).upper()
            k = {"QUALY": "Q", "CARRERA": "R", "RACE": "R", "SPRINT": "SPR"}.get(k, k)
            if k:
                r[k] = s["inicio_utc"]
    return r


def _poles_jolpica():
    """{circuitId: {año: (acr, equipo)}} con las qualys de la cache de Jolpica (por temporada y por circuito)."""
    pol = {}
    for fn in sorted(glob.glob(str(CACHE / "jolpica_qualifying_*.json")) + glob.glob(str(CACHE / "jolpica_circ_*.json"))):
        d = leer(fn)
        try:
            carreras = d["MRData"]["RaceTable"]["Races"]
        except (TypeError, KeyError):
            continue
        for r in carreras:
            q = [x for x in r.get("QualifyingResults", []) if x.get("position") == "1"]
            if q:
                drv = q[0]["Driver"]
                acr = drv.get("code") or drv.get("familyName", "")[:3].upper()
                pol.setdefault(r["Circuit"]["circuitId"], {})[int(r["season"])] = (acr, q[0]["Constructor"]["name"])
    return pol


EQUIPOS_CORTOS = {"Haas F1 Team": "Haas", "Red Bull Racing": "Red Bull", "Alfa Romeo": "Alfa Romeo", "RB F1 Team": "RB"}


def historial(circuito_jolpica, anio, poles):
    filas = sorted((a, v) for a, v in poles.get(circuito_jolpica, {}).items() if a < anio)[-10:]
    return [{"anio": a, "acr": acr, "equipo": EQUIPOS_CORTOS.get(eq, eq)} for a, (acr, eq) in filas]


def tz_de_offset(gmt):
    """'-03:00:00' -> ('Etc/GMT+3', 'UTC−3'); sólo horas enteras (Intl no acepta offsets con minutos en Etc/)."""
    m = re.match(r"^([+-]?)(\d{1,2}):(\d{2})", str(gmt or ""))
    if not m or m.group(3) != "00":
        return "UTC", "UTC"
    h = int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
    if h == 0:
        return "UTC", "UTC"
    return f"Etc/GMT{'-' if h > 0 else '+'}{abs(h)}", f"UTC{'+' if h > 0 else '−'}{abs(h)}"


def catalogo(gps_dir, meta, poles):
    slugs = []
    for g in (meta or {}).get("gps", []):
        if isinstance(g, dict) and SLUG_OK.match(str(g.get("slug", ""))) and g["slug"] not in slugs:
            slugs.append(g["slug"])
    # carpetas gps/<slug>/ sólo si meta.json no trae calendario: meta (gp_pipeline.py) ya lista los GPs desde México;
    # una carpeta suelta (p. ej. una config de un GP anterior) no debe aparecer en el menú
    for p in (sorted(gps_dir.glob("*/")) if not slugs else []):
        if SLUG_OK.match(p.name) and p.name not in slugs and (p / "config.json").exists():
            slugs.append(p.name)
    for s in CURADO:
        if s not in slugs:
            slugs.append(s)
    metas = {g["slug"]: g for g in (meta or {}).get("gps", []) if isinstance(g, dict) and g.get("slug")}
    cat = {}
    for s in slugs:
        cfg = leer(gps_dir / s / "config.json") or {}
        m = metas.get(s, {})
        c = {}
        for k in ("meeting_key", "nombre", "circuito", "circuito_corto", "ciudad", "pais", "tema", "circuito_jolpica", "fecha_texto"):
            v = cfg.get(k) or m.get(k)
            if v:
                c[k] = v
        c.update({k: v for k, v in CURADO.get(s, {}).items() if v is not None})   # lo curado gana (zona, nombres en español)
        if "tz" not in c:
            c["tz"], c["etq"] = tz_de_offset(cfg.get("gmt_offset"))
        anio = int(cfg.get("year") or (re.search(r"(20\d\d)$", s).group(1) if re.search(r"(20\d\d)$", s) else 2026))
        ses = sesiones_openf1(c.get("meeting_key"), anio) if c.get("meeting_key") else {}
        ses.update(sesiones_config(cfg.get("sesiones")))
        ses.update({k: v for k, v in sesiones_config(m.get("fases")).items() if k not in ses})
        c["sesiones"] = ses
        if c.get("circuito_jolpica"):
            c["historial"] = historial(c["circuito_jolpica"], anio, poles)
        c.setdefault("nombre", s)
        c.setdefault("nombre_corto", c.get("circuito_corto") or c["nombre"])
        c.setdefault("tema", "generico")
        cat[s] = c
    return cat


def temas():
    r = {}
    for f in sorted((WEB / "temas").glob("*.json")):
        t = leer(f)
        if isinstance(t, dict):
            t["id"] = f.stem
            r[f.stem] = t
    return r


def hex_rgb(h):
    h = str(h).lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4)) if re.fullmatch(r"[0-9a-fA-F]{6}", h) else None


RGB = {"noche": "--n-rgb", "carbon": "--c-rgb", "carbon-2": "--c2-rgb", "hueso": "--h-rgb", "cempa": "--a-rgb",
       "vela": "--v-rgb", "azul": "--az-rgb", "rosa": "--r-rgb", "jade": "--j-rgb", "frio": "--f-rgb"}


def css_tema(t):
    v = []
    for k, h in (t.get("colores") or {}).items():
        if re.fullmatch(r"[a-z0-9-]+", k) and hex_rgb(h):
            v.append(f"--{k}:{h}")
            if k in RGB:
                v.append(f"{RGB[k]}:{hex_rgb(h)}")
    f = t.get("fuentes") or {}
    for k, var in (("display", "--f-display"), ("body", "--f-body"), ("dato", "--f-dato")):
        if f.get(k):
            v.append(f"{var}:{f[k]}")
    v += [f"--t-peso:{f.get('t_peso', 300)}", f"--t-esp:{f.get('t_esp', '.07em')}", f"--t-em:{f.get('t_em', 'italic')}"]
    im = (t.get("imagenes") or {}).get("heroe") or {}
    v.append(f"--heroe-pos:{im.get('pos', '50% 42%')}")
    return ":root{" + ";".join(v).replace("</", "") + "}"


def construir(plantilla, gps_dir, actual=None, bitacora=None):
    meta = leer(gps_dir / "meta.json")
    if not isinstance(meta, dict):
        meta = {"actualizado": None, "actual": None, "gps": []}
    if actual:
        meta = dict(meta, actual=actual)
    poles = _poles_jolpica()
    cat = catalogo(gps_dir, meta, poles)
    tms = temas()
    gps = {}
    for s in cat:
        d = docs_gp(gps_dir / s)
        if d:
            gps[s] = d
    bit = leer(bitacora if bitacora else gps_dir.parent / "modelos" / "bitacora.json")
    datos = {"meta": meta, "catalogo": cat, "temas": tms, "gps": gps}
    if bitacora_valida(bit):
        datos["bitacora"] = bit
    js = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = plantilla
    patron = re.compile(r'(<script type="application/json" id="datos">)(.*?)(</script>)', re.S)
    if not patron.search(html):
        raise SystemExit('No encontré el bloque <script id="datos"> en la plantilla')
    html = patron.sub(lambda m: m.group(1) + js + m.group(3), html, count=1)
    # Tema del GP inicial en la cabecera (el script lo vuelve a aplicar y lo cambia al cambiar de GP)
    ini = meta.get("actual") if meta.get("actual") in cat else next(iter(cat), None)
    t = tms.get((cat.get(ini) or {}).get("tema")) or tms.get("generico") or {}
    html = re.sub(r'(<style id="tema-inicial">)(.*?)(</style>)', lambda m: m.group(1) + css_tema(t) + m.group(3), html, count=1, flags=re.S)
    url = (t.get("fuentes") or {}).get("url")
    if url and url.startswith("https://fonts.googleapis.com/css2?"):
        html = re.sub(r'(<link rel="stylesheet" id="fuentes-tema" href=")[^"]*(")', lambda m: m.group(1) + url.replace("&", "&amp;") + m.group(2), html, count=1)
    resumen = {s: sorted(d) for s, d in gps.items()}
    if "bitacora" in datos:
        resumen["(bitácora)"] = [f"{len(bit.get('evolucion') or [])} GP evaluados", f"{len(bit.get('cambios') or [])} cambios adoptados",
                                 f"{len(bit.get('candidatos') or [])} candidatos"]
    return html, ini, resumen, sorted(tms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plantilla", default=str(WEB / "plantilla.html"))
    ap.add_argument("--gps", default=str(BASE / "gps"), help="carpeta con meta.json y <slug>/*.json")
    ap.add_argument("--salida", default=str(WEB / "index.html"))
    ap.add_argument("--actual", help="slug del GP inicial del respaldo (por defecto meta.actual)")
    ap.add_argument("--bitacora", help="bitácora de mejora continua (por defecto <carpeta de --gps>/../modelos/bitacora.json)")
    ap.add_argument("--documento", action="store_true",
                    help="envuelve en <!doctype html><html><head>…<body> (Netlify); el Artifact se publica SIN envolver")
    a = ap.parse_args()
    if a.actual and not SLUG_OK.match(a.actual):
        raise SystemExit("--actual: sólo letras minúsculas, dígitos y guiones")
    html, ini, resumen, tms = construir(Path(a.plantilla).read_text(encoding="utf-8"), Path(a.gps), a.actual,
                                        Path(a.bitacora) if a.bitacora else None)
    if a.documento:
        html = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>'
                + html + "</body></html>")
    out = Path(a.salida)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out}: GP inicial={ini} · temas={', '.join(tms)} · {len(html) // 1024} KB")
    for s, d in resumen.items():
        print(f"  {s}: {', '.join(d)}")


if __name__ == "__main__":
    main()
