# -*- coding: utf-8 -*-
"""Paso 1 y 2: los 56 mercados con ensamble (rho del modelo), ensamble (rho = 0) y poisson_simple."""
import json
import pickle

import numpy as np
import pandas as pd

from comun import SAL, mk, metricas, preparar, tabla_mercados, pareada_mercados

pd.set_option("display.width", 250, "display.max_rows", 200, "display.max_columns", 30)

out = {}
D = {"ensamble": preparar("ensamble", "modelo"), "ensamble_rho0": preparar("ensamble", "cero"),
     "poisson_simple": preparar("poisson_simple", "cero")}
for k, d in D.items():
    out[k] = tabla_mercados(d)
    print(k, "n =", int(d["ok"].sum()), "sin medio tiempo:", int((~d["ok"]).sum()),
          "rho medio = %.4f" % d["pred"]["rho"].mean())
out["par_ens_vs_ps"] = pareada_mercados(D["ensamble"], D["poisson_simple"])
out["par_rho_vs_rho0"] = pareada_mercados(D["ensamble"], D["ensamble_rho0"])


# 1X2 al descanso de tres clases y deciles
def descanso(d):
    G, _ = mk._matrices()
    ok, obs, P, bl = d["ok"], d["obs"], d["P"], d["bloques"]
    kk = [mk.claves().index(c) for c in ("D_1", "D_X", "D_2")]
    P3 = P[ok][:, kk]
    P3 = P3 / P3.sum(axis=1, keepdims=True)
    y3 = np.argmax(G[np.array(kk)][:, obs[ok]], axis=0)
    ll3 = -np.log(P3[np.arange(len(y3)), y3])
    f3 = np.bincount(y3, minlength=3) / len(y3)
    r = metricas.diferencia_pareada(ll3, -np.log(f3[y3]), bl[ok])
    return {"logloss": float(ll3.mean()), "logloss_cte": float((-np.log(f3[y3])).mean()), "d_ll": r["dif"],
            "ee": r["ee"], "deciles": mk.tabla_deciles(P3.ravel(), np.eye(3)[y3].ravel()), "ll3": ll3}


for k in ("ensamble", "poisson_simple"):
    out["descanso_" + k] = descanso(D[k])
r = metricas.diferencia_pareada(out["descanso_ensamble"]["ll3"], out["descanso_poisson_simple"]["ll3"],
                                D["ensamble"]["bloques"][D["ensamble"]["ok"]])
out["descanso_par"] = {"d_ll": r["dif"], "ee": r["ee"]}

G, _ = mk._matrices()
dec = {}
for k in ("ensamble", "poisson_simple"):
    d = D[k]
    for c in ("G1T_SI", "O25", "AA_SI", "O15", "O35", "G2T_SI", "L_ANOTA", "V_ANOTA", "D_X", "X"):
        i = mk.claves().index(c)
        dec[(k, c)] = mk.tabla_deciles(d["P"][d["ok"], i], G[i, d["obs"][d["ok"]]])
out["deciles"] = dec

# p1 del recorrido
p1 = D["ensamble"]["p1"]
out["p1"] = {c: float(getattr(p1[col], f)()) for c, col, f in
             [("p1_l_media", "p1_l", "mean"), ("p1_v_media", "p1_v", "mean"), ("p1_l_min", "p1_l", "min"),
              ("p1_l_max", "p1_l", "max"), ("p1_v_min", "p1_v", "min"), ("p1_v_max", "p1_v", "max")]}

pickle.dump(out, open(f"{SAL}/mercados_tablas.pkl", "wb"))

cols = ["pronosticado", "observado", "dif", "z_dif", "pendiente", "ee_pendiente", "d_ll", "ee_d_ll"]
e, p0, e0 = out["ensamble"], out["poisson_simple"], out["ensamble_rho0"]
t = e[cols].copy()
t["z_ps"] = p0["z_dif"]
t["pend_ps"] = p0["pendiente"]
t["dll_ps"] = p0["d_ll"]
t["z_rho0"] = e0["z_dif"]
t["par_ens_ps"] = out["par_ens_vs_ps"]["d_ll"]
t["par_z"] = out["par_ens_vs_ps"]["z"]
t["rho_z"] = out["par_rho_vs_rho0"]["z"]
print(t.round(4).to_string())
print("\ndescanso 3 clases:", {k: {a: round(b, 4) for a, b in out["descanso_" + k].items() if a in ("logloss", "logloss_cte", "d_ll", "ee")}
                               for k in ("ensamble", "poisson_simple")}, out["descanso_par"])
print(json.dumps(out["p1"]))
