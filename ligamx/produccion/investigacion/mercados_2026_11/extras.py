import pickle, numpy as np, pandas as pd
from comun import SAL, mk, arnes, ee_pendiente
pd.set_option("display.width", 250, "display.max_columns", 30)
T = pickle.load(open(f"{SAL}/mercados_tablas.pkl", "rb"))
for k in ("ensamble", "poisson_simple", "ensamble_rho0"):
    t = T[k]; t = t[t["combinable"]]
    z = t["d_ll"] / t["ee_d_ll"]
    print(k, "mercados combinables:", len(t), "| ganan a la cte por >2 ee:", int((z < -2).sum()), "| pierden por >2 ee:", int((z > 2).sum()),
          "| |z sesgo|>2:", int((t["z_dif"].abs() > 2).sum()), "| pendiente<0.7:", int((t["pendiente"] < 0.7).sum()))
    if k != "ensamble_rho0":
        print("   no ganan a la cte (z > -2):", ", ".join(t.index[z > -2]))
e = T["ensamble"]
print("z sesgo >2 (56):", e.index[e["z_dif"].abs() > 2].tolist())
print("pareada ens-ps: mejora >2ee:", int((T["par_ens_vs_ps"]["z"] < -2).sum()), "empeora >2ee:", int((T["par_ens_vs_ps"]["z"] > 2).sum()), "de", len(T["par_ens_vs_ps"]))
print("peores pareadas:", T["par_ens_vs_ps"].sort_values("z").tail(4).round(4).to_dict("index"))
# combinadas: ee de la pendiente y quintiles
for modo in ("modelo",):
    t = pd.read_parquet(f"{SAL}/combinadas_ensamble_rho_{modo}.parquet")
    for v, g in t.groupby("variante", sort=False):
        p, y, b = g["conjunta"].to_numpy(), g["acierta"].to_numpy(), g["bloque"].to_numpy()
        q = mk.tabla_deciles(p, y, 5)
        print(v, "pendiente %.2f (ee %.2f)" % (mk._pendiente_logit(p, y), ee_pendiente(p, y, b, 300)),
              "| quintiles dif:", q["dif"].round(3).tolist(), "z:", q["z"].round(2).tolist(),
              "| sd conjunta %.3f" % p.std(), "| distintas cuartetas:", g["claves"].nunique())
# sd de lambdas y ceros por Jensen
for n in ("ensamble", "poisson_simple", "ajuste", "elo"):
    p = arnes.leer_pred(n)
    print(n, "sd lam_l %.3f sd lam_v %.3f | ceros local %.4f visita %.4f | exp(-media) %.4f %.4f" % (
        p["lam_l"].std(), p["lam_v"].std(), np.exp(-p["lam_l"]).mean(), np.exp(-p["lam_v"]).mean(),
        np.exp(-p["lam_l"].mean()), np.exp(-p["lam_v"].mean())))
