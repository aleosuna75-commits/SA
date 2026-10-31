"""Incrusta los datos de respaldo en web_mexico/index.html (página cinematográfica del pronóstico de qualy).

La página lee en vivo los docs "gp/mexico2026" y "live/qualy" de la base de datos del Artifact; cuando no hay base
(Netlify, archivo local) usa el JSON incrustado en <script type="application/json" id="datos">{"gp":…,"live":…}</script>.
Este script sólo reemplaza ese bloque; el resto del HTML no se toca.

Uso:
  python3 construir_web_mexico.py                       # gp desde resultado_qualy_mexico.pkl (FP2, cambio 0), live pendiente
  python3 construir_web_mexico.py --gp web_mexico/datos_gp.json --live live/qualy_mexico.json
  python3 construir_web_mexico.py --salida /tmp/prueba.html --live prueba_live.json   # copia para pruebas
  python3 construir_web_mexico.py --salida ../sitio_f1/index.html --documento          # copia con doctype (Netlify)
"""
import argparse
import json
import math
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
HTML = BASE / "web_mexico" / "index.html"


def _num(x, nd=3):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd)


def _pos(x):
    v = _num(x, 6)
    return None if v is None else int(round(v))


def _nombre(full):
    if not isinstance(full, str):
        return None
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in full.split())


def gp_desde_pkl(ruta):
    R = pickle.load(open(ruta, "rb"))
    t = R["obj"].sort_values("pred_rank") if "pred_rank" in R["obj"] else R["obj"]
    tab = R["tabla"]
    fila = tab[tab["modelo"] == R.get("mejor")]
    m = (fila if len(fila) else tab).iloc[0]
    pilotos = []
    for _, r in t.iterrows():
        pilotos.append({
            "acr": r["name_acronym"], "nombre": _nombre(r["full_name"]), "equipo": r["team_name"],
            "color": str(r.get("team_colour") or "888888").lstrip("#").upper(),
            "pred": _pos(r["pred_rank"]), "p_q3": _num(r.get("p_q3")), "p_pole": _num(r.get("p_pole")),
            "p_top3": _num(r.get("p_top3")), "p10": _pos(r.get("pos_p10")), "p90": _pos(r.get("pos_p90")),
            "fp1": _pos(r.get("fp1_rank")), "fp2": _pos(r.get("fp2_rank")), "fp3": _pos(r.get("fp3_rank")),
            "cambio": 0,
        })
    return {
        "actualizado": datetime.fromtimestamp(Path(ruta).stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fase": "FP3" if any(p["fp3"] for p in pilotos) else "FP2",
        "modelo": str(R.get("mejor") or m.get("modelo") or "Random Forest"),
        "metricas": {"top10_hits": _num(m.get("top10_hits"), 2), "top10_hits_2026": _num(m.get("top10_hits_2026"), 2),
                     "spearman": _num(m.get("spearman")), "pole_acc": _num(m.get("pole_acc"))},
        "pilotos": pilotos,
    }


def live_pendiente(gp):
    return {"actualizado": gp["actualizado"], "estado": "pendiente", "segmento": 0, "reloj": None,
            "pilotos": [{"acr": p["acr"], "pos": None, "mejor": None, "q1": None, "q2": None, "q3": None,
                         "eliminado_en": None, "en_pits": False, "vueltas": 0} for p in gp["pilotos"]],
            "fuente": "F1 Live Timing"}


def incrustar(html, datos):
    js = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    patron = re.compile(r'(<script type="application/json" id="datos">)(.*?)(</script>)', re.S)
    if not patron.search(html):
        raise SystemExit("No encontré el bloque <script id=\"datos\"> en el HTML")
    return patron.sub(lambda m: m.group(1) + js + m.group(3), html, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkl", default=str(BASE / "resultado_qualy_mexico.pkl"))
    ap.add_argument("--gp", help="JSON del doc gp/mexico2026 (en lugar del .pkl)")
    ap.add_argument("--live", help="JSON del doc live/qualy (por defecto: estado pendiente)")
    ap.add_argument("--entrada", default=str(HTML))
    ap.add_argument("--salida", default=None)
    ap.add_argument("--documento", action="store_true",
                    help="envuelve la salida en <!doctype html><html><head>…<body> (modo estándar, p. ej. para Netlify); "
                         "el Artifact se publica SIN envolver porque claude.ai agrega su propio esqueleto")
    a = ap.parse_args()
    gp = json.load(open(a.gp)) if a.gp else gp_desde_pkl(a.pkl)
    live = json.load(open(a.live)) if a.live else live_pendiente(gp)
    html = Path(a.entrada).read_text(encoding="utf-8")
    out = Path(a.salida) if a.salida else Path(a.entrada)
    final = incrustar(html, {"gp": gp, "live": live})
    if a.documento:
        if out.resolve() == Path(a.entrada).resolve():
            raise SystemExit("--documento requiere --salida distinta de la entrada")
        final = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                 '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>'
                 + final + "</body></html>")
    out.write_text(final, encoding="utf-8")
    print(f"{out}: gp fase={gp.get('fase')} pilotos={len(gp.get('pilotos', []))} live={live.get('estado')}")


if __name__ == "__main__":
    main()
