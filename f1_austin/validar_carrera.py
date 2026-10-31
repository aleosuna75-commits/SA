"""Validación walk-forward 2024-2026 de las variantes del simulador de carrera con degradación y estrategia.

Protocolo (fijado ANTES de ver resultados):
  * Variantes: base (oficial en Austin), deg, deg_team, pace_deg, deg_hist, sig_par, deg+sig_par.
  * Cada GP de 2024-2026 se predice entrenando sólo con GPs anteriores (corte por inicio del fin de semana).
  * Selección: mejor NDCG@10 en 2024-2025; se adopta en lugar de la base sólo si también supera a la base en
    2026 (que funciona como control, aunque se mira). Si no, queda la base y las variables nuevas se muestran
    sólo como información (deg_s_vuelta, paradas).
  * Se reporta todo (por año, top10_hits, win_acc, podium_hits) contra el orden de qualy y de parrilla.

Uso: python3 validar_carrera.py [dataset_carrera.csv] [--meeting 1298]   -> validacion_carrera.json
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import modelo_carrera_austin as C

BASE = Path(__file__).parent
B = C.MC_VAR_BASE
VARIANTES = {
    "base": dict(B),
    "deg": {**B, "deg": True},
    "deg_team": {**B, "deg_team": True},
    "pace_deg": {**B, "pace_deg": True},
    "deg_hist": {**B, "deg_hist": True},
    "sig_par": {**B, "sig_par": True},
    "deg+sig_par": {**B, "deg": True, "sig_par": True},
}


def main(ruta, meeting, salida, n_sims):
    d = pd.read_csv(ruta, parse_dates=["date"])
    hist = d[(d.meeting_key != meeting) & d.race_pos.notna()].sort_values(["date", "driver_number"]).reset_index(drop=True)
    print(f"Historia: {len(hist)} filas, {hist.meeting_key.nunique()} GPs")
    preds = C.walk_forward_sim(hist, VARIANTES, n_sims=n_sims)
    filas = []
    for n, p in preds.items():
        m = C.resumen_metricas(p)
        m24_25 = C.resumen_metricas(p[p.year.isin([2024, 2025])])["ndcg10"]
        filas.append({"variante": n, **m, "ndcg10_2024_25": m24_25})
    t = pd.DataFrame(filas)
    cols = ["variante", "ndcg10", "ndcg10_2024", "ndcg10_2025", "ndcg10_2026", "ndcg10_2024_25", "top10_hits",
            "win_acc", "podium_hits", "pos_exact10", "spearman", "n_gp"]
    print(t[cols].round(4).to_string(index=False))

    var = t[t.variante.isin(VARIANTES)].set_index("variante")
    cand = var.ndcg10_2024_25.idxmax()
    adoptar = (cand != "base" and var.at[cand, "ndcg10_2024_25"] > var.at["base", "ndcg10_2024_25"]
               and var.at[cand, "ndcg10_2026"] > var.at["base", "ndcg10_2026"])
    oficial = cand if adoptar else "base"
    print(f"\nMejor en 2024-2025: {cand} | ¿supera a la base también en 2026? {adoptar} -> oficial: {oficial}")
    # NDCG por GP de la oficial y de la base (para ver cuántos GPs gana/pierde)
    por_gp = {n: C.metricas(preds[n], "pred").set_index("meeting_key").ndcg10 for n in VARIANTES}
    duelo = {n: {"gana": int((por_gp[n] > por_gp["base"] + 1e-9).sum()), "pierde": int((por_gp[n] < por_gp["base"] - 1e-9).sum())}
             for n in VARIANTES if n != "base"}
    print("GPs donde cada variante gana/pierde NDCG@10 vs base:", duelo)
    out = {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": str(ruta), "protocolo": __doc__.split("Uso:")[0].strip(),
        "variantes": {k: v for k, v in VARIANTES.items()},
        "tabla": t[cols].round(4).to_dict(orient="records"),
        "candidata_2024_25": cand, "oficial": {"variante": oficial, "mc_var": VARIANTES[oficial],
                                               "metricas": t.set_index("variante").loc[oficial, cols[1:]].to_dict()},
        "duelo_vs_base": duelo,
    }
    Path(salida).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
    print("Escrito", salida)
    return t, preds


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", nargs="?", default=str(BASE / "dataset_carrera.csv"))
    ap.add_argument("--meeting", type=int, default=1298)
    ap.add_argument("--salida", default=str(BASE / "validacion_carrera.json"))
    ap.add_argument("--sims", type=int, default=20000)
    a = ap.parse_args()
    main(a.dataset, a.meeting, a.salida, a.sims)
