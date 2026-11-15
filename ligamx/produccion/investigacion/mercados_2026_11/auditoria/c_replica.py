# -*- coding: utf-8 -*-
"""
Replica independiente del recorrido walk-forward de las cuatro variantes (forma_1, forma_2, recal_6,
mitades_total) con truncamiento FISICO: para cada corte se arma un subconjunto que solo contiene los
partidos con inicio anterior al corte y se estima con el (optimizador de scipy, no la malla de quien corrigio).

Uso:  c_replica.py des      -> DESARROLLO completo (acervo = DESARROLLO, se califica DESARROLLO)
      c_replica.py ensayo   -> ensayo del camino de PRUEBA sin tocarla: se califican los 3 ultimos torneos de DESARROLLO
      c_replica.py prueba   -> LECTURA UNICA de PRUEBA (queda anotada en ACCESOS_PRUEBA.log)
"""
import os
import pickle
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import a_comun as A

OBJ5 = ["AA_SI", "L_ANOTA", "V_ANOTA", "H_L-1.5", "H_V-1.5"]
OBJ6 = OBJ5 + ["G2T_SI"]
OBJETIVOS = {"forma_1": OBJ5, "forma_2": OBJ5, "recal_6": OBJ6, "mitades_total": ["G2T_SI"]}
_G = {}


def _corte(c):
    """Parametros crudos de un corte, con un acervo truncado fisicamente en el corte."""
    ac = _G["acervo"]
    sel = ac["f"] < c
    m = int(sel.sum())
    if m == 0:
        return c, {"n": 0, "nu1": 1.0, "nu2": 1.0, "ka2": 0.0, "a": np.zeros(len(OBJ6))}
    P = A.subconjunto(ac, sel)                      # nada posterior al corte existe aqui dentro
    assert P["f"].max() < c
    nu1 = A.estimar_nu(P)
    nu2, ka2 = A.estimar_nu_kappa(P)
    a = np.array([A.estimar_intercepto(np.clip(P["pref"][:, A.IDX[k]], 1e-9, 1 - 1e-9), P["y"][:, A.IDX[k]]) for k in OBJ6])
    return c, {"n": m, "nu1": nu1, "nu2": nu2, "ka2": ka2, "a": a}


def referencia(d, tm):
    """Probabilidades de los 52 mercados de lo que se publica hoy (matriz del modelo + reparto unico por mitades)."""
    p1 = A.p1_cortes(tm, d["c"])
    pl = np.array([p1[c][0] for c in d["c"]])
    pv = np.array([p1[c][1] for c in d["c"]])
    M = A.mat_dc(d["ll"], d["lv"], d["rho"])
    q = A.celdas(M, pl, pv)
    return M, q, pl, pv


def recorrido(acervo, ev, tm, procesos=4):
    _G["acervo"] = acervo
    cortes = np.unique(ev["c"])
    with Pool(procesos) as pool:
        par = dict(pool.map(_corte, cortes, chunksize=8))
    n = np.array([par[c]["n"] for c in ev["c"]], float)
    w = n / (n + A.N0)
    out = {"n_prev": n, "w": w,
           "nu1": np.exp(np.log(np.array([par[c]["nu1"] for c in ev["c"]])) * w),
           "nu2": np.exp(np.log(np.array([par[c]["nu2"] for c in ev["c"]])) * w),
           "ka2": np.array([par[c]["ka2"] for c in ev["c"]]) * w,
           "a": np.stack([par[c]["a"] for c in ev["c"]]) * w[:, None], "crudo": par}
    p4 = A.p1_cortes(tm, ev["c"], por_total=True)
    out["p4"] = np.array([p4[c] for c in ev["c"]])              # l bajo, v bajo, l alto, v alto
    return out


def variantes(ev, par):
    """Matrices, celdas y probabilidades (n, 52) de la referencia y de las cuatro variantes."""
    M0, q0, pl, pv = ev["M0"], ev["q0"], ev["pl"], ev["pv"]
    P0 = A.prob_mercados(q0)
    res = {"ref": (M0, q0, P0)}
    for nom, nu, ka in (("forma_1", par["nu1"], 0.0), ("forma_2", par["nu2"], par["ka2"])):
        M = A.mat_forma(ev["ll"], ev["lv"], ev["rho"], nu, ka)
        q = A.celdas(M, pl, pv)
        res[nom] = (M, q, A.prob_mercados(q))
    P = P0.copy()
    for j, k in enumerate(OBJ6):
        p = np.clip(P0[:, A.IDX[k]], 1e-9, 1 - 1e-9)
        pn = 1.0 / (1.0 + np.exp(-(np.log(p / (1 - p)) + par["a"][:, j])))
        P[:, A.IDX[k]] = pn
        P[:, A.IDX[A.COMPL[k]]] = 1.0 - pn
    res["recal_6"] = (M0, None, P)
    bajo = (A.CX + A.CY) <= 2
    plc = np.where(bajo[None, :], par["p4"][:, 0][:, None], par["p4"][:, 2][:, None])
    pvc = np.where(bajo[None, :], par["p4"][:, 1][:, None], par["p4"][:, 3][:, None])
    q = A.celdas(M0, plc, pvc)
    res["mitades_total"] = (M0, q, A.prob_mercados(q))
    return res


def medir(ev, res, B=2000):
    """Condiciones 1, 2, 3a, 3b y 3c de la regla, con errores propios (bootstrap de bloques y formula de conglomerados)."""
    Y, bl, n = ev["y"], ev["bloque"], len(ev["id"])
    ix = np.arange(n)
    M0, _, P0 = res["ref"]
    L0 = A.ll_bin(P0, Y)
    r3 = np.where(ev["gl"] > ev["gv"], 0, np.where(ev["gl"] == ev["gv"], 1, 2))
    k3 = [A.IDX["1"], A.IDX["X"], A.IDX["2"]]
    gl, gv = np.minimum(ev["gl"], 10), np.minimum(ev["gv"], 10)
    out = {}
    sesgo0 = {}
    for k in A.CLAVES:
        m, e, ea = A.ee_bloques(Y[:, A.IDX[k]] - P0[:, A.IDX[k]], bl, B)
        sesgo0[k] = {"pron": P0[:, A.IDX[k]].mean(), "obs": Y[:, A.IDX[k]].mean(), "dif": m, "ee": e, "ee_ana": ea, "z": m / e}
    out["ref"] = {"sesgo": pd.DataFrame(sesgo0).T, "n_sesgo_mas_2ee": int(sum(abs(v["z"]) > 2 for v in sesgo0.values())),
                  "ll_1x2": float(-np.log(P0[ix[:, None], k3][ix, r3]).mean()), "logv": float(np.log(M0[ix, gl, gv]).mean()),
                  "ll_obj": {k: float(L0[:, A.IDX[k]].mean()) for k in OBJ6}}
    for nom, obj in OBJETIVOS.items():
        M1, _, P1 = res[nom]
        L1 = A.ll_bin(P1, Y)
        ko = [A.IDX[k] for k in obj]
        o = {}
        m, e, ea = A.ee_bloques(L1[:, ko].sum(axis=1) - L0[:, ko].sum(axis=1), bl, B)
        o["c1"] = {"d": m, "ee": e, "ee_ana": ea, "z": m / e, "z_ana": m / ea}
        filas = {}
        for k in A.CLAVES:
            j = A.IDX[k]
            mb, eb, _ = A.ee_bloques(Y[:, j] - P1[:, j], bl, B)
            if np.abs(L1[:, j] - L0[:, j]).max() > 1e-12:
                md, ed, _ = A.ee_bloques(L1[:, j] - L0[:, j], bl, B)
            else:
                md, ed = 0.0, np.nan
            filas[k] = {"pron": P1[:, j].mean(), "z_sesgo": mb / eb, "d_ll": md, "z_d_ll": md / ed if ed == ed else np.nan}
        o["mercados"] = pd.DataFrame(filas).T
        o["c2_max_z"] = float(o["mercados"].loc[obj, "z_sesgo"].abs().max())
        o["n_sesgo_mas_2ee"] = int((o["mercados"]["z_sesgo"].abs() > 2).sum())
        o["max_dif_1x2"] = float(np.abs(P1[:, k3] - P0[:, k3]).max())
        dv = np.log(M1[ix, gl, gv]) - np.log(M0[ix, gl, gv])
        if np.abs(dv).max() > 1e-12:
            m, e, _ = A.ee_bloques(dv, bl, B)
            o["c3b"] = {"d": m, "ee": e, "z": m / e}
        else:
            o["c3b"] = {"d": 0.0, "ee": 0.0, "z": np.nan}
        excl = set(obj) | {A.COMPL[k] for k in obj}
        fam = {}
        for f in dict.fromkeys(A.FAMILIA.values()):
            kk = [A.IDX[k] for k in A.CLAVES if A.FAMILIA[k] == f and k not in excl]
            if not kk:
                continue
            dd = L1[:, kk].sum(axis=1) - L0[:, kk].sum(axis=1)
            if np.abs(dd).max() > 1e-12:
                m, e, _ = A.ee_bloques(dd, bl, B)
                fam[f] = {"d": m, "ee": e, "z": m / e}
        o["c3c"] = pd.DataFrame(fam).T
        o["coherencia"] = {"min_p": float(P1.min()), "max_p": float(P1.max()),
                           "max_err_complementos": float(max(np.abs(P1[:, A.IDX[a]] + P1[:, A.IDX[b]] - 1).max() for a, b in A.COMPL.items()))}
        out[nom] = o
    return out


def mostrar(out, titulo):
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print(f"\n######## {titulo} ########")
    r = out["ref"]
    print("REFERENCIA: ll 1X2 %.5f  logv marcador %.5f  mercados con |z sesgo| > 2: %d de 52" % (r["ll_1x2"], r["logv"], r["n_sesgo_mas_2ee"]))
    print(r["sesgo"].loc[OBJ6, ["pron", "obs", "dif", "ee", "ee_ana", "z"]].astype(float).round(4).to_string())
    for nom in OBJETIVOS:
        o = out[nom]
        print(f"\n--- {nom}: C1 d = %.5f  ee = %.5f (analitico %.5f)  z = %.2f (%.2f) | C2 max|z| = %.2f | sesgos > 2 ee: %d | "
              "1X2 max dif %.1e | marcador d = %.5f (ee %.5f, z %.2f)" % (o["c1"]["d"], o["c1"]["ee"], o["c1"]["ee_ana"], o["c1"]["z"], o["c1"]["z_ana"],
                                                                   o["c2_max_z"], o["n_sesgo_mas_2ee"], o["max_dif_1x2"], o["c3b"]["d"], o["c3b"]["ee"], o["c3b"]["z"]))
        print(o["mercados"].loc[OBJETIVOS[nom]].astype(float).round(4).T.to_string())
        if len(o["c3c"]):
            print("familias (d, z):", "; ".join("%s %+.5f (%+.2f)" % (f, x["d"], x["z"]) for f, x in o["c3c"].iterrows()))
        print("coherencia:", {k: float("%.3g" % v) for k, v in o["coherencia"].items()})


def cargar_des():
    par = A.leer_partidos()
    pred = pd.read_parquet(f"{A.RAIZ}/modelo/pred/ensamble.parquet")
    d = A.preparar(pred, f"{A.RAIZ}/modelo/cache/M_ensamble.npz", par)
    return par, d


def completar(d, tm):
    d["M0"], d["q0"], d["pl"], d["pv"] = referencia(d, tm)
    d["pref"] = A.prob_mercados(d["q0"])
    d["y"] = A.observado(d["gl"], d["gv"], d["hl"], d["hv"])
    return d


if __name__ == "__main__":
    modo = sys.argv[1]
    t0 = time.time()
    par, des = cargar_des()
    tm = A.conteos_mitades(par)
    des = completar(des, tm)
    if modo == "des":
        acervo, ev = des, des
    elif modo == "ensayo":
        ult = list(dict.fromkeys(des["torneo"]))[-3:]
        acervo, ev = des, A.subconjunto(des, np.isin(des["torneo"], ult))
    elif modo == "prueba":
        os.environ["AGENTE"] = "auditoria_mercados"
        sys.path.insert(0, A.RAIZ)
        from modelo import arnes                                      # solo para que la lectura quede en la bitacora
        pp = arnes.leer_pred("ensamble", "prueba", "dia")
        pp = pp[pp["gl"].notna()].reset_index(drop=True)
        pr = A.preparar(pp, f"{A.RAIZ}/modelo/cache/M_ensamble__prueba__dia.npz", par)
        assert not np.isnan(pr["hl"]).any()
        pr = completar(pr, tm)
        acervo, ev = A.unir(des, pr), pr
    else:
        raise SystemExit("modo desconocido")
    params = recorrido(acervo, ev, tm)
    res = variantes(ev, params)
    out = medir(ev, res)
    mostrar(out, f"{modo}: n = {len(ev['id'])}, bloques = {len(set(ev['bloque']))}, err matriz {ev['err_matriz']:.1e}")
    print("\nparametros usados: nu1 media %.4f (%.4f a %.4f) | nu2 media %.4f, kappa media %.4f | n previos %d a %d" % (
        params["nu1"].mean(), params["nu1"].min(), params["nu1"].max(), params["nu2"].mean(), params["ka2"].mean(),
        params["n_prev"].min(), params["n_prev"].max()))
    print("interceptos usados al final:", dict(zip(OBJ6, params["a"][np.argmax(params["n_prev"])].round(4))))
    print("p1 por total, medias (l bajo, v bajo, l alto, v alto):", params["p4"].mean(axis=0).round(4), "| reparto unico:", ev["pl"].mean().round(4), ev["pv"].mean().round(4))
    pickle.dump({"params": params, "out": out, "ev": {k: ev[k] for k in ("id", "bloque", "c", "f", "ll", "lv", "rho", "gl", "gv", "hl", "hv", "pl", "pv")}},
                open(f"{A.AUD}/replica_{modo}.pkl", "wb"))
    if modo in ("ensayo", "prueba"):                 # las combinadas en la misma corrida (una sola lectura)
        import d_combinadas as D
        t, ch = D.combinadas(ev, params)
        t.to_parquet(f"{A.AUD}/combinadas_{modo}.parquet")
        D.mostrar(t, ch, modo)
    print("segundos:", round(time.time() - t0, 1))
