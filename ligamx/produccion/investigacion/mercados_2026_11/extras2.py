import pickle, numpy as np, pandas as pd
from comun import SAL, mk, arnes, metricas, preparar
T = pickle.load(open(f"{SAL}/mercados_tablas.pkl", "rb"))
e = T["ensamble"]
print(e.loc[["SE_1", "HA_L-1"], ["n", "pronosticado", "observado"]].round(4).to_dict("index"))
R2 = pickle.load(open(f"{SAL}/diagnostico2.pkl", "rb"))
tor = R2["torneos"]
p = arnes.leer_pred("ensamble")
res = (p["gl"] + p["gv"]) - (p["lam_l"] + p["lam_v"])
v = res.var()
chi = float(((tor["dif"] ** 2) / (v / tor["n"])).sum())
from scipy.stats import chi2
print("var residuo total %.3f; chi2 %.1f con %d gl, p = %.4f; sd dif torneo %.3f; ee esperado %.3f" % (v, chi, len(tor), chi2.sf(chi, len(tor)), tor["dif"].std(), np.sqrt(v / 170)))
# igual con poisson_simple, ajuste, elo (nivel por torneo)
for n in ("poisson_simple", "ajuste", "elo", "dc"):
    q = arnes.leer_pred(n)
    r = (q["gl"] + q["gv"]) - (q["lam_l"] + q["lam_v"])
    t = r.groupby(q["torneo"], sort=False).agg(["mean", "size"])
    print(n, "chi2 %.1f" % float((t["mean"] ** 2 / (r.var() / t["size"])).sum()), "2022-25 dif %.3f" % r[pd.to_datetime(q["fecha_utc"]).dt.year >= 2022].mean())
# dispersion por partido con poisson_simple (para comparar)
for n, modo in (("poisson_simple", "cero"), ("ensamble", "modelo")):
    d = preparar(n, modo); M = d["M"]; pr = d["pred"]
    k = np.arange(11); ii, jj = np.meshgrid(k, k, indexing="ij")
    out = {}
    for etq, f, y in (("local", ii, pr["gl"]), ("visita", jj, pr["gv"]), ("dif", ii - jj, pr["gl"] - pr["gv"]), ("total", ii + jj, pr["gl"] + pr["gv"])):
        ex = (M * f).sum((1, 2)); va = (M * f * f).sum((1, 2)) - ex ** 2
        b = metricas.bootstrap_bloques((y.to_numpy() - ex) ** 2 - va, d["bloques"])
        out[etq] = (round(float(((y.to_numpy() - ex) ** 2).mean() / va.mean()), 3), round(b["media"] / b["ee"], 2))
    print(n, out)
