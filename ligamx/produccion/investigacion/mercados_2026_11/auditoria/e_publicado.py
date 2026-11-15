# Coherencia de lo publicado (salidas/actual.json), recalculada con codigo propio desde lam_l, lam_v, rho y el reparto por mitades publicados.
import json, sys, subprocess
import numpy as np
import a_comun as A

ruta = sys.argv[1] if len(sys.argv) > 1 else f"{A.RAIZ}/salidas/actual.json"
a = json.load(open(ruta))
p1 = a["meta"]["proporcion_goles_1t"]
print("archivo:", ruta, "| generado", a["meta"]["generado_utc"], "| modelo", a["meta"]["modelo"]["nombre"], "| p1", p1, "| pendientes", len(a["pendientes"]))
mx = {"1x2": 0, "mercado": 0, "conjunta": 0, "matriz": 0, "marcador": 0, "pick": 0, "compl": 0, "ingenua": 0}
fuera, n_merc, n_comb, sin_det, claves_raras, marcador_mal = 0, 0, 0, 0, set(), 0
resumen = []
for x in a["pendientes"]:
    if x.get("lam_l") is None:
        sin_det += 1
        continue
    M = A.mat_dc([x["lam_l"]], [x["lam_v"]], [x["rho"]])
    q = A.celdas(M, np.array([p1["local"]]), np.array([p1["visitante"]]))[0]
    P = dict(zip(A.CLAVES, A.prob_mercados(q[None])[0]))
    p3 = A.p1x2(M)[0]
    mx["1x2"] = max(mx["1x2"], abs(p3[0] - x["p_local"]), abs(p3[1] - x["p_empate"]), abs(p3[2] - x["p_visitante"]))
    fuera += not (abs(x["p_local"] + x["p_empate"] + x["p_visitante"] - 1) < 2e-4)
    i, j = np.unravel_index(np.argmax(M[0]), M[0].shape)
    marcador_mal += (x["marcador"]["gl"], x["marcador"]["gv"]) != (int(i), int(j))
    mx["marcador"] = max(mx["marcador"], abs(x["marcador"]["prob"] - M[0, i, j]))
    if x.get("matriz"):
        Mp = np.array(x["matriz"])
        mx["matriz"] = max(mx["matriz"], np.abs(Mp - M[0, :Mp.shape[0], :Mp.shape[1]]).max(), abs(1 - Mp.sum() - x["matriz_resto"]) if "matriz_resto" in x else 0)
    pub = {m["clave"]: m for m in x.get("mercados", [])}
    for k, m in pub.items():
        n_merc += 1
        fuera += not (0.0 <= m["prob"] <= 1.0)
        if k in P:
            mx["mercado"] = max(mx["mercado"], abs(m["prob"] - P[k]))
        elif k == "SE_1":
            mx["mercado"] = max(mx["mercado"], abs(m["prob"] - P["1"] / (P["1"] + P["2"])), abs(m["p_nula"] - P["X"]))
        elif k == "SE_2":
            mx["mercado"] = max(mx["mercado"], abs(m["prob"] - P["2"] / (P["1"] + P["2"])), abs(m["p_nula"] - P["X"]))
        else:
            claves_raras.add(k)
    for k, e in A.COMPL.items():
        if k in pub and e in pub:
            mx["compl"] = max(mx["compl"], abs(pub[k]["prob"] + pub[e]["prob"] - 1))
    for v, c in (x.get("combinadas") or {}).items():
        if not c:
            continue
        n_comb += 1
        ks = [A.IDX[p["clave"]] for p in c["picks"]]
        mia = float(q @ A.GM[ks].prod(axis=0))
        mx["conjunta"] = max(mx["conjunta"], abs(mia - c["prob_conjunta"]))
        mx["ingenua"] = max(mx["ingenua"], abs(float((A.GM[ks] @ q).prod()) - c["prob_ingenua"]))
        for p in c["picks"]:
            mx["pick"] = max(mx["pick"], abs(p["prob"] - P[p["clave"]]))
            fuera += not (0.0 <= p["prob"] <= 1.0)
        fuera += not (0.0 <= c["prob_conjunta"] <= min(p["prob"] for p in c["picks"]) + 1e-4)
        fuera += len({A.FAMILIA[p["clave"]] for p in c["picks"]}) != 4
    resumen.append((x["id"], x["local"], x["visitante"], x["p_local"], x["p_empate"], x["p_visitante"], f'{x["marcador"]["gl"]}-{x["marcador"]["gv"]}'))
print("partidos con detalle:", len(resumen), "sin lambdas:", sin_det, "| mercados revisados:", n_merc, "| combinadas revisadas:", n_comb)
print("diferencia maxima publicado - recalculado (el JSON redondea a 4 decimales):", {k: float("%.2g" % v) for k, v in mx.items()})
print("fuera de [0,1] / incoherencias:", fuera, "| marcador mas probable distinto:", marcador_mal, "| claves no reconocidas:", sorted(claves_raras))
json.dump(resumen, open(f"{A.AUD}/publicado_{sys.argv[2] if len(sys.argv) > 2 else 'antes'}.json", "w"), ensure_ascii=False)
