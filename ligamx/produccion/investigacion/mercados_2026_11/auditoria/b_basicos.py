# Comprobaciones basicas de la implementacion propia y de la referencia (solo DESARROLLO).
import sys, pickle
import numpy as np, pandas as pd
import a_comun as A

par = A.leer_partidos()
pred = pd.read_parquet(f"{A.RAIZ}/modelo/pred/ensamble.parquet")
d = A.preparar(pred, f"{A.RAIZ}/modelo/cache/M_ensamble.npz", par)
n = len(d["id"])
print("n", n, "bloques", len(set(d["bloque"])), "err matriz reconstruida", d["err_matriz"])
print("rho media %.4f de %.4f min %.4f max %.4f" % (d["rho"].mean(), d["rho"].std(), d["rho"].min(), d["rho"].max()))
print("medio tiempo faltante:", int(np.isnan(d["hl"]).sum()), "incoherente:", int(((d["hl"] > d["gl"]) | (d["hv"] > d["gv"])).sum()))
print("x_rho en parquet:", "x_rho" in pred.columns)
# claves y complementos
print("claves", len(A.CLAVES), "complementos", len(A.COMPL), "sin complemento:", [c for c in A.CLAVES if c not in A.COMPL])
# cortes: nadie usa su propio bloque
orden = np.argsort(d["f"], kind="mergesort")
nprev = np.array([(d["f"] < c).sum() for c in d["c"]])
mismo = [(d["f"][d["bloque"] == b] < d["c"][d["bloque"] == b].max()).sum() for b in pd.unique(d["bloque"])]
print("partidos con fecha anterior al corte de su propio bloque:", int(np.sum(mismo)))
print("cortes distintos por bloque (max):", max(len(set(d["c"][d["bloque"] == b])) for b in pd.unique(d["bloque"])))
print("min horas entre corte e inicio:", ((d["f"] - d["c"]) / 3.6e12).min())
# partidos usados (fecha < corte) que no habian terminado 2.5 h antes del corte
fs = np.sort(d["f"])
viol = sum(int(((fs < c) & (fs + int(2.5 * 3.6e12) > c)).sum()) for c in np.unique(d["c"]))
print("partidos del pasado que empezaron a menos de 2.5 h del corte:", viol)
# forma con nu=1,kappa=0 = dc
M0 = A.mat_dc(d["ll"], d["lv"], d["rho"])
M1 = A.mat_forma(d["ll"], d["lv"], d["rho"], 1.0, 0.0)
print("forma(nu=1,kappa=0) - dc:", np.abs(M1 - M0).max(), " 1x2 guardado - matriz:", np.abs(A.p1x2(M0) - d["p3"]).max())
M2 = A.mat_forma(d["ll"], d["lv"], d["rho"], 1.11, 0.03)
print("forma(1.11,0.03): 1x2 dif", np.abs(A.p1x2(M2) - A.p1x2(M0)).max(), "media l dif", np.abs((M2.sum(2) * A.KK).sum(1) - (M0.sum(2) * A.KK).sum(1)).mean())
pickle.dump({"d": d, "nprev": nprev}, open(f"{A.AUD}/des.pkl", "wb"))
