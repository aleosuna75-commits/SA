# -*- coding: utf-8 -*-
"""
Combinadas: se arman con el buscador de PRODUCCION (produccion.combinada.combinada_partido, que es lo que se
audita) sobre las celdas calculadas con codigo propio, y se comprueba con codigo propio:
  - que la conjunta anunciada es la suma de las celdas donde se cumplen los cuatro picks (predicados propios);
  - las reglas (familias distintas, banda, ningun par implicado o excluido, condicionales <= 0.97);
  - la calibracion (anunciada contra frecuencia) y el log-loss pareado contra la referencia.
Uso: d_combinadas.py des | ensayo      (lee replica_<modo>.pkl; para PRUEBA lo llama c_replica.py en la misma corrida)
"""
import pickle
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

import a_comun as A
import c_replica as R

sys.path.insert(0, A.RAIZ)
BANDAS = {"segura": (0.55, 0.85), "equilibrada": (0.45, 0.75), "atrevida": (0.30, 0.60)}   # de MERCADOS.md seccion 4
_Q = {}


def _trabajo(arg):
    nom, i0, i1 = arg
    from produccion import combinada as cb
    q, Y = _Q[nom], _Q["Y"]
    filas = []
    for i in range(i0, i1):
        for v in BANDAS:
            c = cb.combinada_partido(q[i], v)
            if c is None:
                filas.append({"config": nom, "i": i, "variante": v, "conjunta": np.nan})
                continue
            cl = [p["clave"] for p in c["picks"]]
            ks = [A.IDX[k] for k in cl]
            masc = A.GM[ks]                                            # (4, celdas) propias
            mia = float(q[i] @ masc.prod(axis=0))
            marg = masc @ q[i]
            lo, hi = c["banda"]
            pares = [(a, b) for a in range(4) for b in range(a + 1, 4)]
            pj = {ab: float(q[i] @ (masc[ab[0]] * masc[ab[1]])) for ab in pares}
            mal = 0
            mal += len({A.FAMILIA[k] for k in cl}) != 4
            mal += bool(((marg < lo - 1e-9) | (marg > hi + 1e-9)).any())
            mal += any(p <= 1e-15 or p >= min(marg[a], marg[b]) - 1e-15 for (a, b), p in pj.items())
            mal += any(p / marg[a] > 0.97 + 1e-9 or p / marg[b] > 0.97 + 1e-9 for (a, b), p in pj.items())
            mal += any(mia / float(q[i] @ np.delete(masc, a, axis=0).prod(axis=0)) > 0.97 + 1e-9 for a in range(4))
            filas.append({"config": nom, "i": i, "variante": v, "conjunta": c["prob_conjunta"], "conjunta_mia": mia,
                          "ingenua": float(marg.prod()), "acierta": float(Y[i, ks].prod()), "claves": "|".join(sorted(cl)),
                          "ampliada": bool(c["banda_ampliada"]), "reglas_rotas": int(mal),
                          "err_prob_pick": float(max(abs(p["prob"] - m) for p, m in zip(c["picks"], marg)))})
    return filas


def combinadas(ev, params, configs=("ref", "forma_1", "forma_2", "mitades_total"), procesos=4):
    from produccion import mercados as mk
    res = R.variantes(ev, params)
    # la implementacion propia contra el motor de produccion
    cat = {m.clave: m for m in mk.catalogo()}
    chequeo = {"celdas_mismo_orden": bool(np.array_equal(A.CEL, mk._cel)),
               "max_dif_q_propia_vs_mk.celdas": float(np.abs(res["ref"][1] - mk.celdas(ev["M0"], ev["pl"], ev["pv"])).max()),
               "mascaras_distintas_de_52": int(sum(not np.array_equal(A.MASC[k], cat[k].mascara) for k in A.CLAVES)),
               "familias_distintas": int(sum(A.FAMILIA[k] != cat[k].familia for k in A.CLAVES)),
               "max_dif_P_propia_vs_mk.probabilidades": float(np.abs(
                   res["ref"][2] - mk.probabilidades(mk.celdas(ev["M0"], ev["pl"], ev["pv"]))[:, [mk.claves().index(k) for k in A.CLAVES]]).max())}
    for nom in configs:
        _Q[nom] = res[nom][1]
    _Q["Y"] = ev["y"]
    n = len(ev["id"])
    paso = max(1, n // 24)
    tareas = [(nom, i, min(n, i + paso)) for nom in configs for i in range(0, n, paso)]
    with Pool(procesos) as pool:
        filas = [f for bloque in pool.map(_trabajo, tareas, chunksize=1) for f in bloque]
    t = pd.DataFrame(filas)
    t["bloque"] = ev["bloque"][t["i"].to_numpy()]
    return t, chequeo


def resumir(t):
    filas = []
    ref = t[t["config"] == "ref"].set_index(["i", "variante"])
    for nom in pd.unique(t["config"]):
        for v in BANDAS:
            g = t[(t["config"] == nom) & (t["variante"] == v)].set_index("i")
            sin = int(g["conjunta"].isna().sum())
            g = g[g["conjunta"].notna()]
            m, e, ea = A.ee_bloques(g["acierta"] - g["conjunta"], g["bloque"])
            fila = {"config": nom, "variante": v, "n": len(g), "sin": sin, "anunciada": g["conjunta"].mean(), "frecuencia": g["acierta"].mean(),
                    "dif": m, "ee": e, "z": m / e, "ingenua": g["ingenua"].mean(), "ll": A.ll_bin(g["conjunta"].to_numpy(), g["acierta"].to_numpy()).mean(),
                    "max_err_conjunta": float((g["conjunta"] - g["conjunta_mia"]).abs().max()), "reglas_rotas": int(g["reglas_rotas"].sum()),
                    "ampliadas": int(g["ampliada"].sum()), "max_err_prob_pick": float(g["err_prob_pick"].max())}
            if nom != "ref":
                r = ref.xs(v, level="variante").reindex(g.index)
                ok = r["conjunta"].notna().to_numpy()
                dd = A.ll_bin(g["conjunta"].to_numpy()[ok], g["acierta"].to_numpy()[ok]) - A.ll_bin(r["conjunta"].to_numpy()[ok], r["acierta"].to_numpy()[ok])
                md, ed, _ = A.ee_bloques(dd, g["bloque"].to_numpy()[ok])
                fila.update({"d_ll": md, "ee_d_ll": ed, "z_d_ll": md / ed, "mismos_picks": float((g["claves"].to_numpy()[ok] == r["claves"].to_numpy()[ok]).mean())})
            filas.append(fila)
    return pd.DataFrame(filas)


def mostrar(t, chequeo, titulo):
    pd.set_option("display.width", 250, "display.max_columns", 40)
    print(f"\n######## COMBINADAS {titulo} ########")
    print("implementacion propia contra produccion:", chequeo)
    print(resumir(t).round(4).to_string(index=False))


if __name__ == "__main__":
    modo = sys.argv[1]
    z = pickle.load(open(f"{A.AUD}/replica_{modo}.pkl", "rb"))
    par = A.leer_partidos()
    tm = A.conteos_mitades(par)
    ev = R.completar(dict(z["ev"]), tm)
    t, ch = combinadas(ev, z["params"])
    t.to_parquet(f"{A.AUD}/combinadas_{modo}.parquet")
    mostrar(t, ch, modo)
