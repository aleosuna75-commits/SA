"""Exporta el pronóstico de qualy al JSON que lee la página en vivo (doc "gp/<slug>2026" del contrato).

Entrada: resultado_qualy_<slug>[_fp3].pkl (dict de modelo_qualy_austin.main) y, opcionalmente, un pronóstico
previo (.pkl del mismo tipo o prediccion_qualy_*.csv) para calcular 'cambio' = pred anterior - pred
(positivo = el piloto sube en el pronóstico).

Salida (por defecto web_<slug>/datos_gp.json):
  { actualizado: ISO-UTC, fase: "FP2"|"FP3", modelo: str,
    metricas: {top10_hits, top10_hits_2026, spearman, pole_acc},
    pilotos: [ {acr, nombre, equipo, color, pred, p_q3, p_pole, p_top3, p10, p90, fp1, fp2, fp3, cambio} ] }

Uso:
  python3 exportar_datos_web.py                                   # resultado_qualy_mexico.pkl (FP1/FP2)
  python3 exportar_datos_web.py mexico_fp3 --previo resultado_qualy_mexico.pkl
  python3 exportar_datos_web.py resultado_qualy_mexico_fp3.pkl --previo prediccion_qualy_mexico_2026.csv \
          --salida web_mexico/datos_gp.json
"""
import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent


def _ruta_resultado(arg):
    """Acepta un slug ('mexico', 'mexico_fp3') o una ruta a un .pkl."""
    p = Path(arg)
    if p.suffix == ".pkl":
        return p if p.is_absolute() or p.exists() else BASE / p
    return BASE / f"resultado_qualy_{arg}.pkl"


def _num(x, nd=None):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, nd) if nd is not None else x


def _pos(x):
    v = _num(x)
    return None if v is None else int(round(v))


def _nombre(full):
    """'Kimi ANTONELLI' -> 'Kimi Antonelli' (OpenF1 pone el apellido en mayúsculas)."""
    if not isinstance(full, str):
        return None
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in full.split())


def _color(c):
    if not isinstance(c, str) or not c.strip():
        return "888888"
    return c.strip().lstrip("#").upper()


def _pred_previa(ruta):
    """{acr: pred_rank} desde un .pkl de resultado o un .csv de predicción."""
    ruta = Path(ruta)
    if not ruta.is_absolute() and not ruta.exists():
        ruta = BASE / ruta
    if ruta.suffix == ".pkl":
        df = pd.read_pickle(ruta)["obj"]
    elif ruta.suffix == ".json":                # un datos_gp.json anterior
        return {p["acr"]: p["pred"] for p in json.loads(ruta.read_text())["pilotos"]}
    else:
        df = pd.read_csv(ruta)
    return {r.name_acronym: int(r.pred_rank) for r in df.itertuples() if pd.notna(r.pred_rank)}


def _fase(R):
    if R.get("fase"):
        return R["fase"]
    obj = R["obj"]
    return "FP3" if "fp3_rank" in obj and obj["fp3_rank"].notna().any() else "FP2"


def _actualizado(R, ruta):
    if R.get("generado"):
        return R["generado"]
    return datetime.fromtimestamp(ruta.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def construir(ruta_resultado, previo=None):
    ruta = _ruta_resultado(ruta_resultado)
    R = pd.read_pickle(ruta)
    obj = R["obj"].sort_values("pred_rank")
    tabla = R["tabla"]
    fila = tabla[tabla.modelo == R["mejor"]].iloc[0]
    antes = _pred_previa(previo) if previo else {}

    pilotos = []
    for r in obj.itertuples():
        pred = int(r.pred_rank)
        pilotos.append({
            "acr": r.name_acronym,
            "nombre": _nombre(r.full_name),
            "equipo": r.team_name,
            "color": _color(r.team_colour),
            "pred": pred,
            "p_q3": _num(r.p_q3, 3),
            "p_pole": _num(r.p_pole, 3),
            "p_top3": _num(r.p_top3, 3),
            "p10": _pos(r.pos_p10),
            "p90": _pos(r.pos_p90),
            "fp1": _pos(getattr(r, "fp1_rank", None)),
            "fp2": _pos(getattr(r, "fp2_rank", None)),
            "fp3": _pos(getattr(r, "fp3_rank", None)),
            "cambio": (antes[r.name_acronym] - pred) if r.name_acronym in antes else 0,
        })
    doc = {
        "actualizado": _actualizado(R, ruta),
        "fase": _fase(R),
        "modelo": str(R["mejor"]),
        "metricas": {
            "top10_hits": _num(fila.top10_hits, 2),
            "top10_hits_2026": _num(fila.top10_hits_2026, 2),
            "spearman": _num(fila.spearman, 3),
            "pole_acc": _num(fila.pole_acc, 3),
        },
        "pilotos": pilotos,
    }
    validar(doc)
    return doc, R


def validar(doc):
    assert set(doc) == {"actualizado", "fase", "modelo", "metricas", "pilotos"}
    assert doc["fase"] in ("FP2", "FP3")
    assert set(doc["metricas"]) == {"top10_hits", "top10_hits_2026", "spearman", "pole_acc"}
    claves = {"acr", "nombre", "equipo", "color", "pred", "p_q3", "p_pole", "p_top3", "p10", "p90",
              "fp1", "fp2", "fp3", "cambio"}
    n = len(doc["pilotos"])
    assert sorted(p["pred"] for p in doc["pilotos"]) == list(range(1, n + 1)), "pred debe ser 1..N sin repetir"
    for p in doc["pilotos"]:
        assert set(p) == claves, set(p) ^ claves
        assert len(p["color"]) == 6 and not p["color"].startswith("#")
    json.dumps(doc, allow_nan=False)


def escribir(doc, salida):
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = salida.with_suffix(salida.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False))
    os.replace(tmp, salida)                    # escritura atómica: la página nunca lee un JSON a medias


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resultado", nargs="?", default="mexico", help="slug (mexico, mexico_fp3) o ruta al .pkl")
    ap.add_argument("--previo", help="pronóstico anterior (.pkl, .csv o datos_gp.json) para calcular 'cambio'")
    ap.add_argument("--salida", help="ruta del JSON (default web_<slug>/datos_gp.json)")
    a = ap.parse_args()
    doc, R = construir(a.resultado, a.previo)
    salida = Path(a.salida) if a.salida else BASE / f"web_{R['gp']['slug']}" / "datos_gp.json"
    escribir(doc, salida)
    print(f"{salida}  fase={doc['fase']}  modelo={doc['modelo']}  actualizado={doc['actualizado']}")
    for p in doc["pilotos"][:10]:
        print(f"  {p['pred']:>2} {p['acr']}  Q3 {p['p_q3']:.0%}  pole {p['p_pole']:.0%}  "
              f"FP1 {p['fp1']}  FP2 {p['fp2']}  FP3 {p['fp3']}  cambio {p['cambio']:+d}")


if __name__ == "__main__":
    main()
