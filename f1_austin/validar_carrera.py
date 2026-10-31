"""Validación walk-forward 2024-2026 de las variantes del simulador de carrera con degradación y estrategia.

Protocolo (fijado ANTES de ver resultados):
  * Variantes: base (oficial en Austin), deg, deg_team, pace_deg, deg_hist, sig_par, deg+sig_par.
  * Cada GP de 2024-2026 se predice entrenando sólo con GPs anteriores (corte por inicio del fin de semana).
  * Selección: mejor NDCG@10 en 2024-2025; se adopta en lugar de la base sólo si también supera a la base en
    2026 (que funciona como control, aunque se mira). Si no, queda la base y las variables nuevas se muestran
    sólo como información (deg_s_vuelta, paradas).
  * Se reporta todo (por año, top10_hits, win_acc, podium_hits) contra el orden de qualy y de parrilla.

Resultado (31/10/2026, dataset con Austin 2026, 66 GPs): la regla elige deg+sig_par (+0.0008 NDCG@10 en 2024-2025,
empate en 2026), pero (1) la diferencia es menor que el ruido Monte Carlo (con otras semillas la base va de 0.8884
a 0.8898 y deg+sig_par de 0.8884 a 0.8910) y (2) el coeficiente de degradación sale NEGATIVO (más degradación en
prácticas -> mejor resultado), contrario a la hipótesis. Decisión tomada MIRANDO este walk-forward (se declara):
queda la base como oficial y la degradación/paradas se muestran sólo como información. Ver OFICIAL/MOTIVO.

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
OFICIAL = "base"
MOTIVO = ("La regla elige la mejor variante en 2024-2025, pero las diferencias con la base (<0.001 NDCG@10) son menores "
          "que el ruido Monte Carlo entre semillas (~0.0015) y el coeficiente de degradación tiene el signo contrario al "
          "esperado; decisión tomada mirando el walk-forward. La degradación de prácticas apenas anticipa la de carrera "
          "(Spearman medio 0.06 en 57 GPs secos) y no anticipa el número de paradas (0.02).")
VARIANTES = {
    "base": dict(B),
    "deg": {**B, "deg": True},
    "deg_team": {**B, "deg_team": True},
    "pace_deg": {**B, "pace_deg": True},
    "deg_hist": {**B, "deg_hist": True},
    "sig_par": {**B, "sig_par": True},
    "deg+sig_par": {**B, "deg": True, "sig_par": True},
}


def diagnosticos():
    """Lo que se puede validar de las piezas de degradación y estrategia (sin pasar por el orden final)."""
    from scipy.stats import spearmanr
    import degradacion as D
    import modelo_qualy_austin as Q
    tab, degs = D.tabla_estrategia()
    ses = Q.tabla_sesiones()
    # 1) paradas típicas y pérdida en pits con ediciones anteriores vs lo ocurrido (carreras secas 2024-2026)
    filas = []
    for _, r in tab[(tab.fecha.dt.year >= 2024) & ~tab.mojada].iterrows():
        e = D.estrategia_circuito(tab, r.circuit_key, r.fecha)
        filas.append({"par_pred": round(e["paradas"]), "par_real": r.paradas_med, "pp_pred": e["perdida_pit"],
                      "pp_real": r.perdida_pit, "n_ed": e["n_ediciones"]})
    f = pd.DataFrame(filas)
    con = f[f.n_ed > 0]
    est = {"n_carreras": int(len(f)), "n_con_historia": int(len(con)),
           "paradas_acierto": float((con.par_pred == con.par_real.round()).mean()),
           "paradas_mae": float((con.par_pred - con.par_real).abs().mean()),
           "paradas_mae_siempre_1": float((1 - con.par_real).abs().mean()),
           "perdida_pit_mae_s": float((con.pp_pred - con.pp_real).abs().mean()),
           "perdida_pit_mae_mediana_global_s": float((con.pp_real - con.pp_real.median()).abs().mean())}
    # 2) degradación de prácticas vs degradación observada en la carrera (mismo GP, relativa al campo)
    rc = D.deg_carrera_piloto(tab, degs)
    rho = []
    for mk, g in rc.groupby("meeting_key"):
        gs = ses[ses.meeting_key == mk]
        nombres = dict(zip(gs.session_name, gs.session_key))
        pr = D.deg_gp([(nombres.get(x), x) for x in ("Practice 1", "Practice 2", "Practice 3")])
        m = pr.merge(g, on="driver_number")
        if len(m) >= 8:
            rho.append(spearmanr(m.deg_rel, m.race_rel).correlation)
    rho = np.array(rho)
    dg = {"n_gp": int(len(rho)), "spearman_medio": float(np.nanmean(rho)), "pct_positivos": float(np.nanmean(rho > 0))}
    print("Estrategia (ediciones previas vs real):", {k: round(v, 3) for k, v in est.items()})
    print("Degradación prácticas vs carrera:", {k: round(v, 3) for k, v in dg.items()})
    return {"estrategia": est, "degradacion_practicas_vs_carrera": dg}


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
    regla = cand if adoptar else "base"
    oficial = OFICIAL
    print(f"\nMejor en 2024-2025: {cand} | ¿supera a la base también en 2026? {adoptar} -> regla: {regla} | oficial: {oficial}")
    if oficial != regla:
        print("  Motivo:", MOTIVO)
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
        "candidata_2024_25": cand, "regla": regla, "motivo": MOTIVO if oficial != regla else "", "oficial": {"variante": oficial, "mc_var": VARIANTES[oficial],
                                               "metricas": t.set_index("variante").loc[oficial, cols[1:]].to_dict()},
        "duelo_vs_base": duelo,
        "diagnosticos": diagnosticos(),
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
