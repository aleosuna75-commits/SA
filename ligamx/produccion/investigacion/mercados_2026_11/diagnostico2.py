# -*- coding: utf-8 -*-
"""Paso 3 (segunda parte): dispersion por partido, dependencia local/visita, nivel por tramos, mitades."""
import pickle

import numpy as np
import pandas as pd

from comun import SAL, arnes, mk, metricas, preparar, logloss_vec

pd.set_option("display.width", 250, "display.max_rows", 200, "display.max_columns", 30)
R = {}
E = preparar("ensamble", "modelo")
pred, bl, M, Q = E["pred"], E["bloques"], E["M"], E["Q"]
gl, gv = pred["gl"].to_numpy(int), pred["gv"].to_numpy(int)
h1, a1 = pred["gl_ht"].to_numpy(int), pred["gv_ht"].to_numpy(int)
T, T1, T2, Dg = gl + gv, h1 + a1, (gl - h1) + (gv - a1), gl - gv
k = np.arange(11)
ii, jj = np.meshgrid(k, k, indexing="ij")


def bz(v, b=bl):
    r = metricas.bootstrap_bloques(v, b)
    return r["media"], r["ee"], r["media"] / r["ee"]


def mom(f):
    """media y varianza por partido de f(x, y) bajo M."""
    e = (M * f).sum((1, 2))
    v = (M * f ** 2).sum((1, 2)) - e ** 2
    return e, v


print("== A. dispersion por partido: media de (obs - E)^2 - Var_modelo  (negativo = menos dispersion que el modelo)")
filas = []
for etq, f, y in (("local", ii, gl), ("visita", jj, gv), ("total", ii + jj, T), ("diferencia", ii - jj, Dg)):
    e, v = mom(f.astype(float))
    m, ee, z = bz((y - e) ** 2 - v)
    filas.append({"que": etq, "var_modelo_media": v.mean(), "cuadrado_obs_medio": ((y - e) ** 2).mean(),
                  "razon": ((y - e) ** 2).mean() / v.mean(), "dif": m, "ee": ee, "z": z})
el, vl = mom(ii.astype(float))
ev, vv = mom(jj.astype(float))
cov_mod = (M * ii * jj).sum((1, 2)) - el * ev
m, ee, z = bz((gl - el) * (gv - ev) - cov_mod)
filas.append({"que": "covarianza local-visita", "var_modelo_media": cov_mod.mean(), "cuadrado_obs_medio": ((gl - el) * (gv - ev)).mean(),
              "razon": np.nan, "dif": m, "ee": ee, "z": z})
R["dispersion_partido"] = pd.DataFrame(filas)
print(R["dispersion_partido"].round(4).to_string(index=False))
print("corr(lam_l, lam_v) entre partidos: %.3f ; corr(gl, gv) observada: %.4f" %
      (np.corrcoef(E["lam_l"], E["lam_v"])[0, 1], np.corrcoef(gl, gv)[0, 1]))
R["corr"] = (float(np.corrcoef(E["lam_l"], E["lam_v"])[0, 1]), float(np.corrcoef(gl, gv)[0, 1]))

print("\n== B. por tramos: nivel de goles y ceros con el nivel corregido (diagnostico dentro de muestra)")
anio = pd.to_datetime(pred["fecha_utc"]).dt.year.to_numpy()
tramo = np.where(anio <= 2018, "2016-18", np.where(anio <= 2021, "2019-21", "2022-25"))
filas = []
G, _ = mk._matrices()
kc = {c: i for i, c in enumerate(mk.claves())}
for t in ("2016-18", "2019-21", "2022-25", "todo"):
    s = np.ones(len(gl), bool) if t == "todo" else tramo == t
    f = {"tramo": t, "n": int(s.sum())}
    for etq, lam, y, ax in (("l", E["lam_l"], gl, 2), ("v", E["lam_v"], gv, 1)):
        p0 = M[s].sum(ax)[:, 0]
        m, ee, z = bz((y[s] == 0) - p0, bl[s])
        f[f"media_{etq}_pron"], f[f"media_{etq}_obs"] = lam[s].mean(), y[s].mean()
        f[f"cero_{etq}_dif"], f[f"cero_{etq}_z"] = m, z
        esc = y[s].mean() / lam[s].mean()
        f[f"cero_{etq}_dif_nivel"] = float((y[s] == 0).mean() - np.exp(-lam[s] * esc).mean())
        e_, v_ = lam[s], lam[s]
        f[f"disp_{etq}"] = float(((y[s] - lam[s] * esc) ** 2).mean() / (lam[s] * esc).mean())
    m, ee, z = bz(T[s] - (E["lam_l"] + E["lam_v"])[s], bl[s])
    f["total_dif"], f["total_z"] = m, z
    for c in ("AA_SI", "H_L-1.5", "H_V-1.5", "G2T_SI", "O25"):
        y = G[kc[c], E["obs"][s]]
        m, ee, z = bz(y - E["P"][s, kc[c]], bl[s])
        f[c + "_dif"], f[c + "_z"] = m, z
    filas.append(f)
R["tramos"] = pd.DataFrame(filas)
print(R["tramos"].round(3).T.to_string())

# por torneo: total pronosticado contra observado (retraso del nivel)
tor = pred.groupby("torneo", sort=False).apply(
    lambda g: pd.Series({"n": len(g), "total_pron": (g["lam_l"] + g["lam_v"]).mean(), "total_obs": (g["gl"] + g["gv"]).mean()}),
    include_groups=False)
tor["dif"] = tor["total_obs"] - tor["total_pron"]
R["torneos"] = tor
print(tor.round(3).T.to_string())
d = tor["dif"].to_numpy()
print("autocorrelacion de la diferencia por torneo (rezago 1): %.2f" % np.corrcoef(d[:-1], d[1:])[0, 1])
R["autocorr_torneo"] = float(np.corrcoef(d[:-1], d[1:])[0, 1])

print("\n== C. mitades: proporcion del 1T segun el total del partido (bootstrap de bloques)")
cod, _ = pd.factorize(bl, sort=True)
nb = cod.max() + 1
rng = np.random.default_rng(20261115)
idx = rng.integers(0, nb, size=(2000, nb))
filas = []
for etq, s in (("total 1-2", (T >= 1) & (T <= 2)), ("total 3+", T >= 3), ("total 1", T == 1), ("total 2", T == 2)):
    a = np.bincount(cod, weights=(T1 * s).astype(float), minlength=nb)
    b = np.bincount(cod, weights=(T * s).astype(float), minlength=nb)
    rep = a[idx].sum(1) / b[idx].sum(1)
    filas.append({"partidos": etq, "n": int(s.sum()), "goles": int(T[s].sum()), "prop_1T": a.sum() / b.sum(), "ee": rep.std(ddof=1)})
a = np.bincount(cod, weights=(T1 * (T <= 2)).astype(float), minlength=nb)
b = np.bincount(cod, weights=(T * (T <= 2)).astype(float), minlength=nb)
a3 = np.bincount(cod, weights=(T1 * (T >= 3)).astype(float), minlength=nb)
b3 = np.bincount(cod, weights=(T * (T >= 3)).astype(float), minlength=nb)
rep = a[idx].sum(1) / b[idx].sum(1) - a3[idx].sum(1) / b3[idx].sum(1)
dif = a.sum() / b.sum() - a3.sum() / b3.sum()
R["p1_por_total"] = pd.DataFrame(filas)
R["p1_bajo_menos_alto"] = (float(dif), float(rep.std(ddof=1)))
print(R["p1_por_total"].round(4).to_string(index=False))
print("prop_1T(total 1-2) - prop_1T(total 3+) = %.4f (ee %.4f, z %.2f)" % (dif, rep.std(ddof=1), dif / rep.std(ddof=1)))
# cuanto del sesgo de G2T sale del reparto dentro del partido: P(sin gol 2T) con el total OBSERVADO y p1 del pasado
p1 = E["p1"]
p1m = (p1["p1_l"].to_numpy() * E["lam_l"] + p1["p1_v"].to_numpy() * E["lam_v"]) / (E["lam_l"] + E["lam_v"])
p_sin2_dado_total = p1["p1_l"].to_numpy() ** gl * p1["p1_v"].to_numpy() ** gv
p_sin1_dado_total = (1 - p1["p1_l"].to_numpy()) ** gl * (1 - p1["p1_v"].to_numpy()) ** gv
kk2, kk1 = kc["G2T_NO"], kc["G1T_NO"]
R["g2t"] = {"pron": float(E["P"][:, kk2].mean()), "obs": float((T2 == 0).mean()), "binomial_con_marcador_obs": float(p_sin2_dado_total.mean())}
R["g1t"] = {"pron": float(E["P"][:, kk1].mean()), "obs": float((T1 == 0).mean()), "binomial_con_marcador_obs": float(p_sin1_dado_total.mean())}
m, ee, z = bz((T2 == 0) - p_sin2_dado_total)
R["g2t"]["dif_reparto"], R["g2t"]["z_reparto"] = m, z
m, ee, z = bz((T1 == 0) - p_sin1_dado_total)
R["g1t"]["dif_reparto"], R["g1t"]["z_reparto"] = m, z
print("sin gol en el 2T:", {a: round(b, 4) for a, b in R["g2t"].items()})
print("sin gol en el 1T:", {a: round(b, 4) for a, b in R["g1t"].items()})

print("\n== D. ensayo exploratorio (1 variante, DENTRO de muestra; el mismo de MERCADOS.md §3.3): encoger el total a la mitad")
lt = E["lam_l"] + E["lam_v"]
lt2 = lt.mean() + 0.5 * (lt - lt.mean())
E2 = preparar("ensamble", "modelo", lam=(E["lam_l"] * lt2 / lt, E["lam_v"] * lt2 / lt))
filas = []
for c in ("AA_SI", "O15", "O25", "O35", "L_ANOTA", "V_ANOTA", "G1T_SI", "G2T_SI"):
    y = G[kc[c], E["obs"]]
    r = metricas.diferencia_pareada(logloss_vec(E2["P"][:, kc[c]], y), logloss_vec(E["P"][:, kc[c]], y), bl)
    filas.append({"clave": c, "d_ll": r["dif"], "ee": r["ee"], "z": r["z"]})
y3 = pred["resultado"].to_numpy(int)
P3a = arnes.p1x2(E["M"])
P3b = arnes.p1x2(E2["M"])
r = metricas.diferencia_pareada(-np.log(P3b[np.arange(len(y3)), y3]), -np.log(P3a[np.arange(len(y3)), y3]), bl)
filas.append({"clave": "1X2", "d_ll": r["dif"], "ee": r["ee"], "z": r["z"]})
R["encoger_mitad"] = pd.DataFrame(filas)
print(R["encoger_mitad"].round(4).to_string(index=False))

pickle.dump(R, open(f"{SAL}/diagnostico2.pkl", "wb"))
