# -*- coding: utf-8 -*-
"""
Evaluacion walk-forward en DESARROLLO de las cuatro variantes declaradas en MERCADOS_ENSAMBLE.md (seccion 8).
Uso: evaluar_variantes.py forma_1 forma_2 recal_6 mitades_total   (las que se quieran, en ese orden)
No lee PRUEBA. No toca produccion. Deja <variante>.pkl en la carpeta temporal.
"""
import pickle
import sys
import time

import numpy as np
import pandas as pd

from comun import SAL, mk, metricas, preparar, logloss_vec
import forma
from produccion import combinada as cb

N0 = 300.0                                    # encogimiento n / (n + 300), fijado en la regla
OBJ_FORMA = ["AA_SI", "L_ANOTA", "V_ANOTA", "H_L-1.5", "H_V-1.5"]
NUS = np.round(np.arange(0.50, 2.0001, 0.01), 2)
KAPPAS = np.round(np.arange(-0.10, 0.2001, 0.01), 2)
A_MALLA = np.round(np.arange(-0.80, 0.8001, 0.01), 2)

d = preparar("ensamble", "modelo")
pred, obs, bl = d["pred"], d["obs"], d["bloques"]
assert d["ok"].all() and len(pred) == 2981
n = len(pred)
G, _Z = mk._matrices()
CAT = mk.catalogo()
CLAVES = mk.claves()
IDX = {c: i for i, c in enumerate(CLAVES)}
Y = G[:, obs].T                                # (n, 56) 1 si el mercado se cumplio
ll_, lv_, rho_ = d["lam_l"], d["lam_v"], pred["rho"].to_numpy(float)
gl = np.minimum(pred["gl"].to_numpy(int), 10)
gv = np.minimum(pred["gv"].to_numpy(int), 10)
res3 = pred["resultado"].to_numpy(int)
fecha = pd.DatetimeIndex(pred["fecha_utc"]).as_unit("ns").asi8
corte = pd.DatetimeIndex(pd.to_datetime(pred["corte"], utc=True)).as_unit("ns").asi8
orden = np.argsort(fecha, kind="mergesort")
n_prev = np.searchsorted(fecha[orden], corte, side="left")      # partidos de desarrollo anteriores al corte
assert (n_prev <= np.argsort(orden)).all()                      # nadie se ve a si mismo ni a su bloque
ENC = n_prev / (n_prev + N0)


def complemento(k: int) -> int | None:
    for j, m in enumerate(CAT):
        if m.combinable and np.array_equal(m.mascara, ~CAT[k].mascara):
            return j
    return None


def evaluar(nombre, objetivos, M_new=None, Q_new=None, P_new=None, combinadas=True, extra=None) -> dict:
    M0, Q0, P0 = d["M"], d["Q"], d["P"]
    if M_new is not None:
        Q_new = mk.celdas(M_new, d["p1"]["p1_l"].to_numpy(), d["p1"]["p1_v"].to_numpy())
    if Q_new is not None:
        P_new = mk.probabilidades(Q_new)
    M1 = M0 if M_new is None else M_new
    out = {"variante": nombre, "objetivos": objetivos, "extra": extra or {}}
    ko = [IDX[c] for c in objetivos]
    excl = set(ko) | {complemento(k) for k in ko}
    L0 = np.stack([logloss_vec(P0[:, k], Y[:, k]) for k in range(len(CAT))], axis=1)
    L1 = np.stack([logloss_vec(P_new[:, k], Y[:, k]) for k in range(len(CAT))], axis=1)
    # condicion 1
    r = metricas.diferencia_pareada(L1[:, ko].sum(axis=1), L0[:, ko].sum(axis=1), bl)
    out["c1"] = {"d": r["dif"], "ee": r["ee"], "z": r["z"]}
    # condicion 2 (y tabla de sesgo de todos los combinables)
    ses = []
    for k, m in enumerate(CAT):
        if not m.combinable:
            continue
        b0 = metricas.bootstrap_bloques(Y[:, k] - P0[:, k], bl)
        b1 = metricas.bootstrap_bloques(Y[:, k] - P_new[:, k], bl)
        par = metricas.diferencia_pareada(L1[:, k], L0[:, k], bl) if np.any(L1[:, k] != L0[:, k]) else {"dif": 0.0, "ee": 0.0, "z": np.nan}
        ses.append({"clave": m.clave, "familia": m.familia, "objetivo": k in ko, "pron0": P0[:, k].mean(),
                    "pron1": P_new[:, k].mean(), "obs": Y[:, k].mean(), "dif0": b0["media"], "z0": b0["media"] / b0["ee"],
                    "dif1": b1["media"], "z1": b1["media"] / b1["ee"], "d_ll": par["dif"], "ee_d_ll": par["ee"], "z_d_ll": par["z"]})
    out["mercados"] = pd.DataFrame(ses).set_index("clave")
    # condicion 3a: 1X2
    k3 = [IDX["1"], IDX["X"], IDX["2"]]
    a = -np.log(P_new[np.arange(n)[:, None], k3][np.arange(n), res3] / P_new[:, k3].sum(axis=1))
    b = -np.log(P0[np.arange(n)[:, None], k3][np.arange(n), res3] / P0[:, k3].sum(axis=1))
    out["max_dif_1x2"] = float(np.abs(P_new[:, k3] - P0[:, k3]).max())
    r = metricas.diferencia_pareada(a, b, bl) if out["max_dif_1x2"] > 1e-12 else {"dif": 0.0, "ee": 0.0, "z": np.nan}
    out["c3a_1x2"] = {"ll0": float(b.mean()), "d": r["dif"], "ee": r["ee"], "z": r["z"]}
    # condicion 3b: marcador exacto
    a = np.log(M1[np.arange(n), gl, gv])
    b = np.log(M0[np.arange(n), gl, gv])
    r = metricas.diferencia_pareada(a, b, bl) if np.abs(a - b).max() > 1e-12 else {"dif": 0.0, "ee": 0.0, "z": np.nan}
    out["c3b_marcador"] = {"logv0": float(b.mean()), "d": r["dif"], "ee": r["ee"], "z": r["z"]}
    # condicion 3c: familias (sin objetivos ni complementos)
    fam = []
    for f in dict.fromkeys(m.familia for m in CAT):
        kk = [k for k, m in enumerate(CAT) if m.familia == f and m.combinable and k not in excl]
        if not kk:
            fam.append({"familia": f, "n_mercados": 0, "d": 0.0, "ee": 0.0, "z": np.nan})
            continue
        a, b = L1[:, kk].sum(axis=1), L0[:, kk].sum(axis=1)
        r = metricas.diferencia_pareada(a, b, bl) if np.abs(a - b).max() > 1e-12 else {"dif": 0.0, "ee": 0.0, "z": np.nan}
        fam.append({"familia": f, "n_mercados": len(kk), "d": r["dif"], "ee": r["ee"], "z": r["z"]})
    out["c3c_familias"] = pd.DataFrame(fam).set_index("familia")
    # condicion 3d: combinadas
    if combinadas and Q_new is not None:
        t0 = time.time()
        base = pd.read_parquet(f"{SAL}/combinadas_ensamble_rho_modelo.parquet")
        base = base[~base["sin_combinada"]]
        cat = {m.clave: m for m in CAT}
        filas = []
        for i in range(n):
            for v in cb.BANDAS:
                c = cb.combinada_partido(Q_new[i], v)
                if c is None:
                    continue
                ac = all(bool(cat[p["clave"]].mascara[obs[i]]) for p in c["picks"])
                filas.append({"variante": v, "id": pred["id"].iloc[i], "bloque": bl[i], "conjunta": c["prob_conjunta"],
                              "acierta": float(ac), "claves": "|".join(sorted(p["clave"] for p in c["picks"]))})
        t = pd.DataFrame(filas)
        t.to_parquet(f"{SAL}/combinadas_{nombre}.parquet")
        com = []
        for v in cb.BANDAS:
            g1 = t[t["variante"] == v].set_index("id")
            g0 = base[base["variante"] == v].set_index("id")
            ids = g1.index.intersection(g0.index)
            g1, g0 = g1.loc[ids], g0.loc[ids]
            s1 = metricas.bootstrap_bloques(g1["acierta"] - g1["conjunta"], g1["bloque"])
            s0 = metricas.bootstrap_bloques(g0["acierta"] - g0["conjunta"], g0["bloque"])
            l1 = logloss_vec(np.clip(g1["conjunta"].to_numpy(), 1e-9, 1 - 1e-9), g1["acierta"].to_numpy())
            l0 = logloss_vec(np.clip(g0["conjunta"].to_numpy(), 1e-9, 1 - 1e-9), g0["acierta"].to_numpy())
            r = metricas.diferencia_pareada(l1, l0, g1["bloque"].to_numpy())
            com.append({"variante": v, "n": len(ids), "anunciada0": g0["conjunta"].mean(), "frec0": g0["acierta"].mean(),
                        "z0": s0["media"] / s0["ee"], "anunciada1": g1["conjunta"].mean(), "frec1": g1["acierta"].mean(),
                        "z1": s1["media"] / s1["ee"], "ll0": l0.mean(), "d_ll": r["dif"], "ee": r["ee"], "z_d_ll": r["z"],
                        "mismos_picks": float((g1["claves"] == g0["claves"]).mean())})
        out["c3d_combinadas"] = pd.DataFrame(com).set_index("variante")
        out["seg_combinadas"] = time.time() - t0
    # veredicto
    m = out["mercados"]
    c1 = out["c1"]["z"] < -2
    c2 = bool((m.loc[objetivos, "z1"].abs() <= 2).all())
    peor = lambda z, signo=1: bool(np.isfinite(z) and signo * z > 1)          # noqa: E731
    c3 = {"1x2": not peor(out["c3a_1x2"]["z"]), "marcador": not peor(out["c3b_marcador"]["z"], -1),
          "familias": not any(peor(z) for z in out["c3c_familias"]["z"])}
    if "c3d_combinadas" in out:
        cc = out["c3d_combinadas"]
        c3["combinadas"] = not (any(peor(z) for z in cc["z_d_ll"]) or (cc["z1"].abs() > 2).any())
    out["veredicto"] = {"c1": bool(c1), "c2": c2, **{"c3_" + k: v for k, v in c3.items()},
                        "cumple": bool(c1 and c2 and all(c3.values()))}
    pickle.dump(out, open(f"{SAL}/{nombre}.pkl", "wb"))
    return out


def mostrar(o):
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_rows", 80)
    print(f"\n================ {o['variante']} ================")
    print("extra:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in o["extra"].items()})
    print("C1 suma log-loss objetivos: d = %.5f  ee = %.5f  z = %.2f" % (o["c1"]["d"], o["c1"]["ee"], o["c1"]["z"]))
    m = o["mercados"]
    print(m.loc[o["objetivos"], ["pron0", "pron1", "obs", "z0", "z1", "d_ll", "ee_d_ll", "z_d_ll"]].round(4).to_string())
    print("C3a 1X2:", {k: round(v, 5) for k, v in o["c3a_1x2"].items()}, "max dif", "%.1e" % o["max_dif_1x2"])
    print("C3b marcador:", {k: round(v, 5) for k, v in o["c3b_marcador"].items()})
    print(o["c3c_familias"].round(5).to_string())
    if "c3d_combinadas" in o:
        print(o["c3d_combinadas"].round(4).T.to_string())
    otros = m[(~m["objetivo"]) & ((m["z1"].abs() > 2) | (m["z_d_ll"].abs() > 1))]
    print("no objetivo con |z sesgo| > 2 despues o |z pareada| > 1:")
    print(otros[["pron0", "pron1", "obs", "z0", "z1", "d_ll", "ee_d_ll", "z_d_ll"]].round(4).to_string())
    print("n mercados con sesgo |z| > 2: antes", int((m["z0"].abs() > 2).sum()), "despues", int((m["z1"].abs() > 2).sum()))
    print("VEREDICTO:", o["veredicto"])


# ------------------------------------------------------------------------------------------------
_malla = {}


def malla_forma():
    if "C" not in _malla:
        t0 = time.time()
        LL = forma.malla_logv(ll_, lv_, rho_, gl, gv, NUS, KAPPAS)          # (nus, kappas, n)
        _malla["C"] = np.cumsum(LL[:, :, orden], axis=2)
        _malla["seg"] = time.time() - t0
    return _malla["C"]


def parametros_forma(con_kappa: bool):
    C = malla_forma()
    j0 = int(np.flatnonzero(KAPPAS == 0.0)[0])
    nu_i, ka_i, crudo = np.ones(n), np.zeros(n), {}
    for m in np.unique(n_prev):
        if m == 0:
            continue
        S = C[:, :, m - 1] if con_kappa else C[:, j0:j0 + 1, m - 1]
        nu, ka = forma.maximo_malla(S, NUS, KAPPAS if con_kappa else KAPPAS[j0:j0 + 1])
        crudo[int(m)] = (nu, ka)
        sel = n_prev == m
        nu_i[sel] = np.exp(np.log(nu) * m / (m + N0))
        ka_i[sel] = ka * m / (m + N0)
    # estimacion con TODO desarrollo (solo informativa; es lo que usaria produccion hoy sin leer PRUEBA)
    S = C[:, :, n - 1] if con_kappa else C[:, j0:j0 + 1, n - 1]
    fin = forma.maximo_malla(S, NUS, KAPPAS if con_kappa else KAPPAS[j0:j0 + 1])
    return nu_i, ka_i, crudo, fin


def correr_forma(nombre, con_kappa):
    nu_i, ka_i, crudo, fin = parametros_forma(con_kappa)
    M = forma.matrices_forma(ll_, lv_, rho_, nu_i, ka_i, p_fijo=None)
    q = np.quantile(n_prev, [0.1, 0.5, 0.9]).astype(int)
    ms = sorted(crudo)
    extra = {"nu_usado_medio": float(nu_i.mean()), "nu_usado_min": float(nu_i.min()), "nu_usado_max": float(nu_i.max()),
             "nu_crudo_n500": crudo[min(ms, key=lambda m: abs(m - 500))][0], "nu_crudo_n1500": crudo[min(ms, key=lambda m: abs(m - 1500))][0],
             "nu_todo_desarrollo": fin[0], "kappa_usado_medio": float(ka_i.mean()), "kappa_todo_desarrollo": fin[1],
             "kappa_crudo_n1500": crudo[min(ms, key=lambda m: abs(m - 1500))][1], "seg_malla": _malla["seg"],
             "goles_esp_l_antes": float((d["M"].sum(axis=2) * forma.K).sum(axis=1).mean()),
             "goles_esp_l_despues": float((M.sum(axis=2) * forma.K).sum(axis=1).mean()),
             "goles_esp_v_antes": float((d["M"].sum(axis=1) * forma.K).sum(axis=1).mean()),
             "goles_esp_v_despues": float((M.sum(axis=1) * forma.K).sum(axis=1).mean())}
    pickle.dump({"nu": nu_i, "kappa": ka_i, "crudo": crudo, "fin": fin, "n_prev": n_prev}, open(f"{SAL}/params_{nombre}.pkl", "wb"))
    return evaluar(nombre, OBJ_FORMA, M_new=M, extra=extra)


def correr_recal():
    objetivos = OBJ_FORMA + ["G2T_SI"]
    P = d["P"].copy()
    extra = {}
    for c in objetivos:
        k = IDX[c]
        p, y = np.clip(d["P"][:, k], 1e-9, 1 - 1e-9), Y[:, k]
        lg = np.log(p / (1 - p))
        pa = 1.0 / (1.0 + np.exp(-(lg[None, :] + A_MALLA[:, None])))            # (malla, n)
        C = np.cumsum((y[None, :] * np.log(pa) + (1 - y[None, :]) * np.log(1 - pa))[:, orden], axis=1)
        a_i = np.zeros(n)
        for m in np.unique(n_prev):
            if m == 0:
                continue
            S = C[:, m - 1]
            i = int(np.argmax(S))
            a = float(A_MALLA[i])
            if 0 < i < len(A_MALLA) - 1:
                a += forma._vertice(S[i - 1], S[i], S[i + 1]) * 0.01
            a_i[n_prev == m] = a * m / (m + N0)
        pn = 1.0 / (1.0 + np.exp(-(lg + a_i)))
        P[:, k] = pn
        kc = complemento(k)
        P[:, kc] = 1.0 - pn
        extra["a_medio_" + c] = float(a_i.mean())
        extra["a_final_" + c] = float(a_i[np.argmax(n_prev)])
    return evaluar("recal_6", objetivos, P_new=P, combinadas=False, extra=extra)


def correr_mitades():
    df = mk.datos.cargar()
    t = mk._conteos_mitades(df)
    f = pd.DatetimeIndex(t["fecha_utc"]).as_unit("ns").asi8
    tot = (t["g_l"] + t["g_v"]).to_numpy(float)
    cols = t[["g1_l", "g_l", "g1_v", "g_v"]].to_numpy(float)
    c_ns = corte
    hi = np.searchsorted(f, c_ns, side="left")
    lo = np.searchsorted(f, c_ns - int(mk.ANIOS_P1 * 365.25 * 86400 * 1e9), side="left")
    p = {}
    for nombre, sel in (("bajo", tot <= 2), ("alto", tot >= 3)):
        cs = np.vstack([np.zeros(4), np.cumsum(cols * sel[:, None], axis=0)])
        s = cs[hi] - cs[lo]
        p[nombre] = (s[:, 0] / s[:, 1], s[:, 2] / s[:, 3])
    bajo = (mk.X + mk.Y) <= 2
    pl = np.where(bajo[None, :], p["bajo"][0][:, None], p["alto"][0][:, None])
    pv = np.where(bajo[None, :], p["bajo"][1][:, None], p["alto"][1][:, None])
    Q = (d["M"][:, mk.X, mk.Y] * mk._COMB_L * pl ** mk.H1 * (1.0 - pl) ** mk.H2 * mk._COMB_V * pv ** mk.A1 * (1.0 - pv) ** mk.A2)
    assert np.abs(Q.sum(axis=1) - 1).max() < 1e-9
    extra = {"p1_l_bajo": float(p["bajo"][0].mean()), "p1_l_alto": float(p["alto"][0].mean()),
             "p1_v_bajo": float(p["bajo"][1].mean()), "p1_v_alto": float(p["alto"][1].mean()),
             "p1_l_base": float(d["p1"]["p1_l"].mean()), "p1_v_base": float(d["p1"]["p1_v"].mean())}
    return evaluar("mitades_total", ["G2T_SI"], Q_new=Q, extra=extra)


if __name__ == "__main__":
    for v in sys.argv[1:]:
        t0 = time.time()
        o = {"forma_1": lambda: correr_forma("forma_1", False), "forma_2": lambda: correr_forma("forma_2", True),
             "recal_6": correr_recal, "mitades_total": correr_mitades}[v]()
        mostrar(o)
        print("segundos:", round(time.time() - t0, 1))
