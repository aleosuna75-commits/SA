# -*- coding: utf-8 -*-
"""Paso 3: de donde sale cada sesgo. Solo DESARROLLO. Diagnostico (no ajusta nada que se adopte)."""
import pickle

import numpy as np
import pandas as pd

from comun import SAL, arnes, datos, mk, metricas, preparar, logloss_vec

pd.set_option("display.width", 250, "display.max_rows", 200, "display.max_columns", 30)
R = {}


def bz(v, bl):
    b = metricas.bootstrap_bloques(v, bl)
    return b["media"], b["ee"], b["media"] / b["ee"]


E = preparar("ensamble", "modelo")
E0 = preparar("ensamble", "cero")
PS = preparar("poisson_simple", "cero")
pred, bl = E["pred"], E["bloques"]
gl, gv = pred["gl"].to_numpy(int), pred["gv"].to_numpy(int)
h1, a1 = pred["gl_ht"].to_numpy(int), pred["gv_ht"].to_numpy(int)
T, T1, T2 = gl + gv, h1 + a1, (gl - h1) + (gv - a1)

# ---------------------------------------------------------------- 1. medias y ceros
print("== 1. medias y ceros (pron / obs / dif / z)")
filas = []
for nom, d in (("ensamble", E), ("ensamble_rho0", E0), ("poisson_simple", PS)):
    M = d["M"]
    ex = arnes.goles_esperados(M)
    px0, py0, p00 = M[:, 0, :].sum(1), M[:, :, 0].sum(1), M[:, 0, 0]
    for etq, p, y in (("media_local", ex[:, 0], gl), ("media_visita", ex[:, 1], gv),
                      ("local_sin_gol", px0, gl == 0), ("visita_sin_gol", py0, gv == 0),
                      ("0-0", p00, (gl == 0) & (gv == 0)),
                      ("ambos_anotan", 1 - px0 - py0 + p00, (gl > 0) & (gv > 0))):
        m, ee, z = bz(np.asarray(y, float) - p, bl)
        filas.append({"modelo": nom, "que": etq, "pron": p.mean(), "obs": float(np.mean(y)), "dif": m, "ee": ee, "z": z})
R["ceros"] = pd.DataFrame(filas)
print(R["ceros"].round(4).to_string(index=False))
print("Poisson con lambda constante (media observada): P(local 0) = %.4f, P(visita 0) = %.4f" %
      (np.exp(-gl.mean()), np.exp(-gv.mean())))

# ---------------------------------------------------------------- 2. distribuciones marginales
print("\n== 2. distribucion de goles (ensamble con rho): pron / obs / z")


def dist(Pk, yk, etqs):
    out = []
    for j, e in enumerate(etqs):
        m, ee, z = bz(yk[:, j] - Pk[:, j], bl)
        out.append({"valor": e, "pron": Pk[:, j].mean(), "obs": yk[:, j].mean(), "dif": m, "z": z})
    return pd.DataFrame(out)


M = E["M"]
ml, mv = M.sum(2), M.sum(1)                      # marginal local (n, 11), visita (n, 11)


def agrupa(P, tope):
    return np.column_stack([P[:, :tope], P[:, tope:].sum(1)])


def ind(y, tope):
    return np.eye(tope + 1)[np.minimum(y, tope)]


R["dist_local"] = dist(agrupa(ml, 4), ind(gl, 4), ["0", "1", "2", "3", "4+"])
R["dist_visita"] = dist(agrupa(mv, 4), ind(gv, 4), ["0", "1", "2", "3", "4+"])
DT = arnes.dist_total(M)
R["dist_total"] = dist(agrupa(DT, 6), ind(T, 6), ["0", "1", "2", "3", "4", "5", "6+"])
# diferencia de goles
ii, jj = np.meshgrid(np.arange(11), np.arange(11), indexing="ij")
dd = np.clip(ii - jj, -3, 3)
PD = np.column_stack([(M * (dd == k)).sum((1, 2)) for k in range(-3, 4)])
R["dist_dif"] = dist(PD, np.eye(7)[np.clip(gl - gv, -3, 3) + 3], ["<=-3", "-2", "-1", "0", "+1", "+2", ">=+3"])
M0 = E0["M"]
PD0 = np.column_stack([(M0 * (dd == k)).sum((1, 2)) for k in range(-3, 4)])
R["dist_dif_rho0"] = dist(PD0, np.eye(7)[np.clip(gl - gv, -3, 3) + 3], ["<=-3", "-2", "-1", "0", "+1", "+2", ">=+3"])
for k in ("dist_local", "dist_visita", "dist_total", "dist_dif", "dist_dif_rho0"):
    print(k)
    print(R[k].round(4).to_string(index=False))
# varianza: observada contra la que implica el modelo (E[var condicional] + Var(media))
vl_mod = ((ml * np.arange(11) ** 2).sum(1) - (ml * np.arange(11)).sum(1) ** 2).mean() + (ml * np.arange(11)).sum(1).var()
vv_mod = ((mv * np.arange(11) ** 2).sum(1) - (mv * np.arange(11)).sum(1) ** 2).mean() + (mv * np.arange(11)).sum(1).var()
tt = np.arange(21)
vt_mod = ((DT * tt ** 2).sum(1) - (DT * tt).sum(1) ** 2).mean() + (DT * tt).sum(1).var()
R["varianzas"] = {"local": (gl.var(), vl_mod, gl.mean()), "visita": (gv.var(), vv_mod, gv.mean()),
                  "total": (T.var(), vt_mod, T.mean()), "corr_gl_gv": float(np.corrcoef(gl, gv)[0, 1])}
print("varianza obs / modelo / media obs:", {k: tuple(round(float(x), 4) for x in v) if isinstance(v, tuple) else round(v, 4)
                                             for k, v in R["varianzas"].items()})

# ---------------------------------------------------------------- 3. rho
print("\n== 3. rho de Dixon-Coles: celdas bajas pron (rho) / pron (rho=0) / obs")
filas = []
for (x, y) in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2), (2, 1), (1, 2), (2, 2)):
    o = ((gl == x) & (gv == y)).astype(float)
    m, ee, z = bz(o - M[:, x, y], bl)
    m0, ee0, z0 = bz(o - M0[:, x, y], bl)
    filas.append({"marcador": f"{x}-{y}", "pron_rho": M[:, x, y].mean(), "pron_rho0": M0[:, x, y].mean(), "obs": o.mean(),
                  "z_rho": z, "z_rho0": z0})
R["celdas"] = pd.DataFrame(filas)
print(R["celdas"].round(4).to_string(index=False))
# rho de maxima verosimilitud DENTRO de desarrollo dadas las lambdas del ensamble (solo diagnostico)
ll_, lv_ = E["lam_l"], E["lam_v"]


def ll_rho(r):
    tau = np.ones(len(gl))
    tau = np.where((gl == 0) & (gv == 0), 1 - ll_ * lv_ * r, tau)
    tau = np.where((gl == 0) & (gv == 1), 1 + ll_ * r, tau)
    tau = np.where((gl == 1) & (gv == 0), 1 + lv_ * r, tau)
    tau = np.where((gl == 1) & (gv == 1), 1 - r, tau)
    return np.log(tau).sum()


rr = np.linspace(-0.25, 0.10, 351)
vals = np.array([ll_rho(r) for r in rr])
r_mv = rr[vals.argmax()]
dentro = rr[vals >= vals.max() - 0.5]
R["rho"] = {"media_usada": float(pred["rho"].mean()), "sd": float(pred["rho"].std()), "min": float(pred["rho"].min()),
            "max": float(pred["rho"].max()), "mv_desarrollo": float(r_mv), "ic68": (float(dentro.min()), float(dentro.max()))}
print("rho:", {k: (round(v, 4) if not isinstance(v, tuple) else tuple(round(x, 3) for x in v)) for k, v in R["rho"].items()})
kc = {c: i for i, c in enumerate(mk.claves())}
filas = []
G, _ = mk._matrices()
for c in ("X", "AA_SI", "O15", "O25", "U25", "L_ANOTA", "V_ANOTA", "D_X", "G1T_NO", "DF_X/X", "H_L-1.5", "H_V-1.5"):
    i = kc[c]
    y = G[i, E["obs"]]
    d = metricas.diferencia_pareada(logloss_vec(E["P"][:, i], y), logloss_vec(E0["P"][:, i], y), bl)
    filas.append({"clave": c, "pron_rho": E["P"][:, i].mean(), "pron_rho0": E0["P"][:, i].mean(), "obs": y.mean(),
                  "d_ll_rho_menos_rho0": d["dif"], "ee": d["ee"]})
R["efecto_rho"] = pd.DataFrame(filas)
print(R["efecto_rho"].round(4).to_string(index=False))

# ---------------------------------------------------------------- 4. dispersion de las lambdas
print("\n== 4. dispersion de las lambdas (regresion de Poisson de lo observado sobre log de lo pronosticado)")


def glm_poisson(x, y, n_iter=50):
    X_ = np.column_stack([np.ones(len(x)), x])
    b = np.array([np.log(y.mean()), 0.0])
    for _ in range(n_iter):
        mu = np.exp(X_ @ b)
        paso = np.linalg.solve(X_.T @ (X_ * mu[:, None]), X_.T @ (y - mu))
        b = b + paso
        if np.abs(paso).max() < 1e-10:
            break
    return b


def glm_binom(x, k, n, n_iter=50):
    X_ = np.column_stack([np.ones(len(x)), x])
    b = np.array([0.0, 1.0])
    for _ in range(n_iter):
        p = 1 / (1 + np.exp(-(X_ @ b)))
        w = n * p * (1 - p)
        paso = np.linalg.solve(X_.T @ (X_ * w[:, None]) + 1e-9 * np.eye(2), X_.T @ (k - n * p))
        b = b + paso
        if np.abs(paso).max() < 1e-10:
            break
    return b


def con_ee(f, B=400, semilla=20261115):
    cod, _ = pd.factorize(bl, sort=True)
    nb = cod.max() + 1
    grupos = [np.flatnonzero(cod == b) for b in range(nb)]
    rng = np.random.default_rng(semilla)
    est = f(np.arange(len(bl)))
    reps = [f(np.concatenate([grupos[b] for b in rng.integers(0, nb, nb)])) for _ in range(B)]
    return est, float(np.std(reps, ddof=1))


filas = []
for nom in ("ensamble", "ajuste", "elo", "dc", "poisson_simple"):
    p = arnes.leer_pred(nom)
    assert (p["id"].to_numpy() == pred["id"].to_numpy()).all()
    l_, v_ = p["lam_l"].to_numpy(float), p["lam_v"].to_numpy(float)
    lt = l_ + v_
    bT, eT = con_ee(lambda ix: glm_poisson(np.log(lt[ix]), T[ix].astype(float))[1])
    bL, eL = con_ee(lambda ix: glm_poisson(np.log(l_[ix]), gl[ix].astype(float))[1])
    bV, eV = con_ee(lambda ix: glm_poisson(np.log(v_[ix]), gv[ix].astype(float))[1])
    xs = np.log(l_ / v_)
    bS, eS = con_ee(lambda ix: glm_binom(xs[ix], gl[ix].astype(float), T[ix].astype(float))[1])
    filas.append({"modelo": nom, "media_total": lt.mean(), "sd_total": lt.std(), "sd_log_total": np.log(lt).std(),
                  "sd_log_razon": xs.std(), "b_total": bT, "ee_bT": eT, "b_local": bL, "ee_bL": eL, "b_visita": bV,
                  "ee_bV": eV, "b_reparto": bS, "ee_bS": eS,
                  "corr_total_obs": float(np.corrcoef(lt, T)[0, 1])})
R["dispersion"] = pd.DataFrame(filas)
print(R["dispersion"].round(4).to_string(index=False))
print("total observado: media %.4f, varianza %.4f; var - media = %.4f (dispersión 'real' entre partidos si el total fuera Poisson)"
      % (T.mean(), T.var(), T.var() - T.mean()))
lt = E["lam_l"] + E["lam_v"]
q5 = pd.qcut(lt, 5, labels=False)
R["quintiles_total"] = pd.DataFrame({"pron": pd.Series(lt).groupby(q5).mean(), "obs": pd.Series(T).groupby(q5).mean(),
                                     "n": pd.Series(T).groupby(q5).size()})
ltp = (arnes.leer_pred("poisson_simple")["lam_l"] + arnes.leer_pred("poisson_simple")["lam_v"]).to_numpy()
q5p = pd.qcut(ltp, 5, labels=False)
R["quintiles_total_ps"] = pd.DataFrame({"pron": pd.Series(ltp).groupby(q5p).mean(), "obs": pd.Series(T).groupby(q5p).mean()})
print("quintiles del total pronosticado, ensamble:\n", R["quintiles_total"].round(3).T.to_string())
print("quintiles del total pronosticado, poisson_simple:\n", R["quintiles_total_ps"].round(3).T.to_string())

# ---------------------------------------------------------------- 5. mitades
print("\n== 5. reparto por mitades")
p1 = E["p1"]
obs_p1_l, obs_p1_v = h1.sum() / gl.sum(), a1.sum() / gv.sum()
pron_p1_l = (p1["p1_l"].to_numpy() * E["lam_l"]).sum() / E["lam_l"].sum()
pron_p1_v = (p1["p1_v"].to_numpy() * E["lam_v"]).sum() / E["lam_v"].sum()
# ee de la proporcion observada por bootstrap de bloques
cod, _ = pd.factorize(bl, sort=True)
nb = cod.max() + 1
rng = np.random.default_rng(20261115)
s = {k: np.bincount(cod, weights=v.astype(float), minlength=nb) for k, v in (("h1", h1), ("gl", gl), ("a1", a1), ("gv", gv))}
idx = rng.integers(0, nb, size=(2000, nb))
ee_l = (s["h1"][idx].sum(1) / s["gl"][idx].sum(1)).std(ddof=1)
ee_v = (s["a1"][idx].sum(1) / s["gv"][idx].sum(1)).std(ddof=1)
ee_t = ((s["h1"][idx].sum(1) + s["a1"][idx].sum(1)) / (s["gl"][idx].sum(1) + s["gv"][idx].sum(1))).std(ddof=1)
R["p1"] = {"local": (pron_p1_l, obs_p1_l, ee_l), "visita": (pron_p1_v, obs_p1_v, ee_v),
           "total_obs": (float((h1.sum() + a1.sum()) / T.sum()), float(ee_t))}
print("proporcion 1T pron / obs / ee:", {k: tuple(round(float(x), 4) for x in v) for k, v in R["p1"].items()})
Q = E["Q"]
eT1 = Q @ (mk.H1 + mk.A1)
eT2 = Q @ (mk.H2 + mk.A2)
for etq, e, o in (("goles 1T", eT1, T1), ("goles 2T", eT2, T2)):
    m, ee, z = bz(o - e, bl)
    print(f"{etq}: pron {e.mean():.4f} obs {o.mean():.4f} dif {m:+.4f} (ee {ee:.4f}, z {z:.2f})")
    R["media_" + etq] = (float(e.mean()), float(o.mean()), m, ee, z)
PT1 = np.column_stack([Q @ ((mk.H1 + mk.A1) == k) for k in range(3)] + [Q @ ((mk.H1 + mk.A1) >= 3)])
PT2 = np.column_stack([Q @ ((mk.H2 + mk.A2) == k) for k in range(3)] + [Q @ ((mk.H2 + mk.A2) >= 3)])
R["dist_1t"] = dist(PT1, ind(T1, 3), ["0", "1", "2", "3+"])
R["dist_2t"] = dist(PT2, ind(T2, 3), ["0", "1", "2", "3+"])
print("dist 1T\n", R["dist_1t"].round(4).to_string(index=False))
print("dist 2T\n", R["dist_2t"].round(4).to_string(index=False))
# adelgazamiento: dado el total n, P(sin gol en el 2T) = p1^n ; P(sin gol en el 1T) = (1-p1)^n
p1m = (p1["p1_l"].to_numpy() * E["lam_l"] + p1["p1_v"].to_numpy() * E["lam_v"]) / (E["lam_l"] + E["lam_v"])
filas = []
for n in range(1, 6):
    s_ = T == n if n < 5 else T >= 5
    nn = T[s_]
    filas.append({"total": str(n) if n < 5 else "5+", "partidos": int(s_.sum()),
                  "sin_gol_1T_binom": float(((1 - p1m[s_]) ** nn).mean()), "sin_gol_1T_obs": float((T1[s_] == 0).mean()),
                  "sin_gol_2T_binom": float((p1m[s_] ** nn).mean()), "sin_gol_2T_obs": float((T2[s_] == 0).mean()),
                  "prop_1T_obs": float(T1[s_].sum() / nn.sum())})
R["adelgazamiento"] = pd.DataFrame(filas)
print(R["adelgazamiento"].round(4).to_string(index=False))
print("corr(T1, T2) observada %.4f; var(T1)/media %.3f; var(T2)/media %.3f" %
      (np.corrcoef(T1, T2)[0, 1], T1.var() / T1.mean(), T2.var() / T2.mean()))
R["corr_mitades"] = float(np.corrcoef(T1, T2)[0, 1])
# por temporadas: p1 pronosticado contra observado
anio = pd.to_datetime(pred["fecha_utc"]).dt.year.to_numpy()
tramo = np.where(anio <= 2018, "2016-18", np.where(anio <= 2021, "2019-21", "2022-25"))
filas = []
kAA, kL, kV, kG2 = kc["AA_SI"], kc["L_ANOTA"], kc["V_ANOTA"], kc["G2T_SI"]
kH, kHV = kc["H_L-1.5"], kc["H_V-1.5"]
for t in ("2016-18", "2019-21", "2022-25"):
    s_ = tramo == t
    f = {"tramo": t, "n": int(s_.sum()), "p1_pron": float(p1m[s_].mean()), "p1_obs": float(T1[s_].sum() / T[s_].sum()),
         "total_pron": float(lt[s_].mean()), "total_obs": float(T[s_].mean())}
    for c, k in (("AA", kAA), ("L_anota", kL), ("V_anota", kV), ("G2T", kG2), ("H_L-1.5", kH), ("H_V-1.5", kHV)):
        y = G[k, E["obs"][s_]]
        f[c + "_dif"] = float(y.mean() - E["P"][s_, k].mean())
    filas.append(f)
R["tramos"] = pd.DataFrame(filas)
print(R["tramos"].round(4).to_string(index=False))

# ---------------------------------------------------------------- 6. ceros por equipo
print("\n== 6. ceros por equipo (ensamble): el equipo se queda sin anotar, pron / obs")
px0, py0 = M[:, 0, :].sum(1), M[:, :, 0].sum(1)
a = pd.DataFrame({"equipo": pred["local"], "p": px0, "y": (gl == 0).astype(float)})
b = pd.DataFrame({"equipo": pred["visitante"], "p": py0, "y": (gv == 0).astype(float)})
eq = pd.concat([a, b]).groupby("equipo").agg(n=("y", "size"), pron=("p", "mean"), obs=("y", "mean"))
eq["dif"] = eq["obs"] - eq["pron"]
eq["z"] = eq["dif"] / np.sqrt(eq["pron"] * (1 - eq["pron"]) / eq["n"])
c2 = pd.concat([pd.DataFrame({"equipo": pred["local"], "p": py0, "y": (gv == 0).astype(float)}),
                pd.DataFrame({"equipo": pred["visitante"], "p": px0, "y": (gl == 0).astype(float)})])
pc = c2.groupby("equipo").agg(pron_pc=("p", "mean"), obs_pc=("y", "mean"))
eq = eq.join(pc)
eq["dif_pc"] = eq["obs_pc"] - eq["pron_pc"]
eq["z_pc"] = eq["dif_pc"] / np.sqrt(eq["pron_pc"] * (1 - eq["pron_pc"]) / eq["n"])
R["equipos"] = eq.sort_values("dif")
g = eq[eq["n"] >= 100]
print(g.sort_values("dif").round(3).to_string())
print("equipos con n >= 100: %d; con menos ceros de los pronosticados (ataque): %d; (porteria en cero): %d" %
      (len(g), int((g["dif"] < 0).sum()), int((g["dif_pc"] < 0).sum())))
print("sd de z entre equipos: ataque %.2f, porteria %.2f (1 = solo ruido)" % (g["z"].std(), g["z_pc"].std()))
print("media ponderada dif ataque %.4f" % (np.average(eq["dif"], weights=eq["n"])))
R["equipos_resumen"] = {"n_eq": len(g), "menos_ceros_ataque": int((g["dif"] < 0).sum()),
                        "menos_ceros_porteria": int((g["dif_pc"] < 0).sum()), "sd_z_ataque": float(g["z"].std()),
                        "sd_z_porteria": float(g["z_pc"].std())}
# por nivel de lambda: ceros pronosticados vs observados
filas = []
for etq, lam, p0_, y in (("local", E["lam_l"], px0, gl), ("visita", E["lam_v"], py0, gv)):
    q4 = pd.qcut(lam, 4, labels=False)
    for k in range(4):
        s_ = q4 == k
        filas.append({"lado": etq, "cuartil_lambda": k + 1, "lambda": float(lam[s_].mean()), "goles_obs": float(y[s_].mean()),
                      "cero_pron": float(p0_[s_].mean()), "cero_obs": float((y[s_] == 0).mean()),
                      "2mas_pron": float(1 - p0_[s_].mean() - (M[s_, 1, :].sum(1).mean() if etq == "local" else M[s_, :, 1].sum(1).mean())),
                      "2mas_obs": float((y[s_] >= 2).mean()),
                      "3mas_obs": float((y[s_] >= 3).mean())})
R["ceros_por_lambda"] = pd.DataFrame(filas)
print(R["ceros_por_lambda"].round(4).to_string(index=False))

pickle.dump(R, open(f"{SAL}/diagnostico.pkl", "wb"))
