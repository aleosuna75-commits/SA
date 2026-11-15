# -*- coding: utf-8 -*-
"""
Paso 1 (combinada): las tres variantes en DESARROLLO con ensamble y el rho de su matriz guardada.
Misma logica que produccion.combinada.validar_desarrollo, pero con Q armado con rho (el comando
existente cae en rho = 0 porque ensamble.parquet no trae x_rho). Uso: medir_combinada.py [modelo|cero]
"""
import pickle
import sys

import numpy as np
import pandas as pd

from comun import SAL, mk, metricas, preparar
from produccion import combinada as cb

modo = sys.argv[1] if len(sys.argv) > 1 else "modelo"
nombre = sys.argv[2] if len(sys.argv) > 2 else "ensamble"
etq = modo if nombre == "ensamble" else nombre
d = preparar(nombre, modo)
pred, Q, obs = d["pred"], d["Q"], d["obs"]
cat = {m.clave: m for m in mk.catalogo()}
filas, uso = [], {}
for i in np.flatnonzero(obs >= 0):
    for v in cb.BANDAS:
        c = cb.combinada_partido(Q[i], v)
        if c is None:
            filas.append({"variante": v, "id": pred["id"].iloc[i], "bloque": pred["bloque"].iloc[i], "sin_combinada": True})
            continue
        ac = [bool(cat[p["clave"]].mascara[obs[i]]) for p in c["picks"]]
        for p in c["picks"]:
            uso[(v, p["clave"])] = uso.get((v, p["clave"]), 0) + 1
        filas.append({"variante": v, "id": pred["id"].iloc[i], "bloque": pred["bloque"].iloc[i],
                      "conjunta": c["prob_conjunta"], "ingenua": c["prob_ingenua"], "ampliada": c["banda_ampliada"],
                      "acierta": float(all(ac)), "picks_acertados": float(sum(ac)),
                      "claves": "|".join(sorted(p["clave"] for p in c["picks"])), "sin_combinada": False})
t = pd.DataFrame(filas)
t.to_parquet(f"{SAL}/combinadas_{nombre}_rho_{modo}.parquet")
sinc = t[t["sin_combinada"]]
t = t[~t["sin_combinada"]]
res, dec, quint = [], {}, {}
for v, g in t.groupby("variante", sort=False):
    b = metricas.bootstrap_bloques(g["acierta"] - g["conjunta"], g["bloque"])
    p = np.clip(g["conjunta"].to_numpy(), 1e-9, 1 - 1e-9)
    pi = np.clip(g["ingenua"].to_numpy(), 1e-9, 1 - 1e-9)
    y = g["acierta"].to_numpy()
    f = y.mean()
    ll = lambda pr: -(y * np.log(pr) + (1 - y) * np.log(1 - pr))          # noqa: E731
    ll0 = -(y * np.log(f) + (1 - y) * np.log(1 - f))
    dc = metricas.diferencia_pareada(ll(p), ll0, g["bloque"])
    res.append({"variante": v, "n": len(g), "conjunta_anunciada": g["conjunta"].mean(), "frecuencia_observada": f,
                "dif": b["media"], "ee": b["ee"], "z": b["media"] / b["ee"], "producto_ingenuo": g["ingenua"].mean(),
                "momio_justo_medio": (1 / g["conjunta"]).mean(), "picks_acertados_de_4": g["picks_acertados"].mean(),
                "logloss_conjunta": float(ll(p).mean()), "logloss_ingenua": float(ll(pi).mean()),
                "logloss_cte": float(ll0.mean()), "d_ll_cte": dc["dif"], "ee_d_ll_cte": dc["ee"],
                "pendiente": mk._pendiente_logit(p, y), "banda_ampliada": int(g["ampliada"].sum()),
                "min": g["conjunta"].min(), "max": g["conjunta"].max()})
    dec[v] = mk.tabla_deciles(g["conjunta"].to_numpy(), y, 10)
    quint[v] = mk.tabla_deciles(g["conjunta"].to_numpy(), y, 5)
res = pd.DataFrame(res)
picks = pd.Series(uso).rename_axis(["variante", "clave"]).rename("veces").reset_index()
pickle.dump({"resumen": res, "deciles": dec, "quintiles": quint, "picks": picks, "sin_combinada": len(sinc)},
            open(f"{SAL}/combinada_{etq}.pkl", "wb"))
pd.set_option("display.width", 250, "display.max_columns", 30)
print("modo rho:", modo, "| partidos sin combinada:", len(sinc))
print(res.round(4).T.to_string())
for v in dec:
    print(f"\n### {v} (deciles)\n" + dec[v].round(3).to_string(index=False))
p = picks.sort_values(["variante", "veces"], ascending=[True, False])
for k, g in p.groupby("variante"):
    print(f"\n{k}: " + ", ".join(f"{c} {n}" for c, n in zip(g["clave"].head(10), g["veces"].head(10))))
