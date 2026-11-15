# -*- coding: utf-8 -*-
"""Arma las tablas en Markdown (fragmentos) a partir de los resultados guardados. Escribe fragmentos.json."""
import json
import pickle

import numpy as np
import pandas as pd

from comun import SAL

T = pickle.load(open(f"{SAL}/mercados_tablas.pkl", "rb"))
R = pickle.load(open(f"{SAL}/diagnostico.pkl", "rb"))
R2 = pickle.load(open(f"{SAL}/diagnostico2.pkl", "rb"))
C = pickle.load(open(f"{SAL}/combinada_modelo.pkl", "rb"))
C0 = pickle.load(open(f"{SAL}/combinada_cero.pkl", "rb"))
CP = pickle.load(open(f"{SAL}/combinada_poisson_simple.pkl", "rb"))
F = {}


def n(x, d=3):
    if round(abs(x), d) == 0:
        x = 0.0
    return f"{x:.{d}f}".replace("-", "−")


def s(x, d=3):
    if round(abs(x), d) == 0:
        return f"{0:.{d}f}"
    return ("+" if x >= 0 else "−") + f"{abs(x):.{d}f}"


def z(x, d=1, negrita=True):
    if 1.9 <= abs(x) < 2.1:
        d = 2
    t = n(x, d)
    return f"**{t}**" if negrita and abs(x) >= 2 else t


def tabla(enc, filas, alin=None):
    alin = alin or ["---"] + ["---:"] * (len(enc) - 1)
    return "\n".join(["| " + " | ".join(enc) + " |", "|" + "|".join(alin) + "|"] + ["| " + " | ".join(f) + " |" for f in filas])


NOM = {"1": "Gana local", "X": "Empate", "2": "Gana visita", "SE_1": "Local, sin empate (†)", "H_L-1.5": "Local gana por 2+",
       "H_V-1.5": "Visita gana por 2+", "HA_L-1": "Local −1 asiático (†)", "O15": "Más de 1.5", "O25": "Más de 2.5",
       "O35": "Más de 3.5", "AA_SI": "Ambos anotan", "L_ANOTA": "Local anota", "L_2MAS": "Local anota 2+",
       "V_ANOTA": "Visita anota", "V_2MAS": "Visita anota 2+", "D_1": "Local gana al descanso", "D_X": "Empate al descanso",
       "D_2": "Visita gana al descanso", "G1T_SI": "Gol en el 1T", "O15_1T": "Más de 1.5 en el 1T", "G2T_SI": "Gol en el 2T",
       "MAS_1T": "Más goles en el 1T", "MAS_2T": "Más goles en el 2T", "MIT_IGUAL": "Mismos goles por mitad",
       "GM_L": "Local gana alguna mitad", "GM_V": "Visita gana alguna mitad"}
PARES = [("1", "X2"), ("X", "12"), ("2", "1X"), ("SE_1", "SE_2"), ("H_L-1.5", "H_V+1.5"), ("H_V-1.5", "H_L+1.5"),
         ("HA_L-1", "HA_V+1"), ("O15", "U15"), ("O25", "U25"), ("O35", "U35"), ("AA_SI", "AA_NO"), ("L_ANOTA", "PC_V"),
         ("L_2MAS", "L_U15"), ("V_ANOTA", "PC_L"), ("V_2MAS", "V_U15"), ("D_1", "D_X2"), ("D_X", "D_12"), ("D_2", "D_1X"),
         ("G1T_SI", "G1T_NO"), ("O15_1T", "U15_1T"), ("G2T_SI", "G2T_NO")]
SOLOS = ["MAS_1T", "MAS_2T", "MIT_IGUAL", "GM_L", "GM_V"] + [f"DF_{a}/{b}" for a in "1X2" for b in "1X2"]
e, ps, e0 = T["ensamble"], T["poisson_simple"], T["ensamble_rho0"]
par = T["par_ens_vs_ps"]
assert len(PARES) * 2 + len(SOLOS) == 56 == len(e)

# ---- tabla de los 56 mercados
filas = []
for a, b in PARES + [(c, None) for c in SOLOS]:
    r = e.loc[a]
    nombre = NOM.get(a, "Descanso/final " + a[3:].replace("1", "local").replace("2", "visita").replace("X", "empate"))
    cl = f"`{a}`" + (f" / `{b}`" if b else "")
    pz = f"{s(par.loc[a, 'd_ll'], 4)} ({n(par.loc[a, 'z'], 1)})" if a in par.index else "—"
    filas.append([f"{nombre} ({cl})", n(r["pronosticado"]), n(r["observado"]), s(r["dif"]), z(r["z_dif"]),
                  f"{n(r['pendiente'], 2)} ({n(r['ee_pendiente'], 2)})", f"{s(r['d_ll'], 4)} ({n(r['ee_d_ll'], 4)})", pz])
F["mercados56"] = tabla(["Mercado (clave / complemento)", "Pronosticado", "Observado", "dif", "z", "Pendiente (ee)",
                         "d_ll (ee)", "`ensamble` − `poisson_simple`: d_ll (z)"], filas)

# ---- deciles como MERCADOS.md
d = T["deciles"]
dd = T["descanso_ensamble"]["deciles"]
filas = []
for i in range(10):
    f = [str(i + 1)]
    for t in (d[("ensamble", "G1T_SI")], dd, d[("ensamble", "O25")], d[("ensamble", "AA_SI")]):
        f += [n(t["pronosticado"].iloc[i]), n(t["observado"].iloc[i])]
    filas.append(f)
F["deciles"] = tabla(["Decil", "Gol 1T pron.", "obs.", "1X2 descanso pron.", "obs.", "Más de 2.5 pron.", "obs.",
                      "Ambos anotan pron.", "obs."], filas, ["---:"] * 9)
F["deciles_zmax"] = {k: float(d[("ensamble", k)]["z"].abs().max()) for k in ("G1T_SI", "O25", "AA_SI", "O15", "O35", "G2T_SI", "L_ANOTA", "V_ANOTA")}
F["deciles_zmax"]["descanso"] = float(dd["z"].abs().max())
F["deciles_aa_ps"] = d[("poisson_simple", "AA_SI")][["pronosticado", "observado"]].round(3).to_dict("list")

# ---- comparacion
filas = []
for c in ("AA_SI", "L_ANOTA", "V_ANOTA", "L_2MAS", "V_2MAS", "O15", "O25", "O35", "G1T_SI", "O15_1T", "G2T_SI", "D_1", "D_X",
          "D_2", "X", "1", "2", "H_L-1.5", "H_V-1.5", "GM_L", "MAS_2T", "DF_1/1", "DF_X/X"):
    a, b = ps.loc[c], e.loc[c]
    nombre = NOM.get(c, "Descanso/final " + c[3:].replace("1", "local").replace("2", "visita").replace("X", "empate"))
    filas.append([f"{nombre} (`{c}`)", f"{s(a['dif'])} ({z(a['z_dif'])})", f"{s(b['dif'])} ({z(b['z_dif'])})",
                  n(a["pendiente"], 2), f"{n(b['pendiente'], 2)} ({n(b['ee_pendiente'], 2)})",
                  f"{s(a['d_ll'], 4)}", f"{s(b['d_ll'], 4)} ({n(b['ee_d_ll'], 4)})",
                  f"{s(par.loc[c, 'd_ll'], 4)} ({n(par.loc[c, 'ee'], 4)})", z(par.loc[c, "z"])])
F["comparacion"] = tabla(["Mercado", "Sesgo `poisson_simple`: dif (z)", "Sesgo `ensamble`: dif (z)", "Pendiente antes",
                          "Pendiente ahora (ee)", "d_ll contra constante antes", "ahora (ee)",
                          "Pareada ahora − antes (ee)", "z"], filas)

# ---- combinada
enc = ["Modelo", "Variante", "n", "Conjunta anunciada", "Frecuencia observada", "dif (ee)", "z", "Producto ingenuo",
       "Momio justo medio", "Log-loss conjunta / ingenua", "d_ll contra constante (ee)", "Pendiente"]
filas = []
for etq, c in (("`ensamble` (su rho)", C), ("`ensamble` (rho = 0: lo que da el comando)", C0), ("`poisson_simple`", CP)):
    for _, r in c["resumen"].iterrows():
        filas.append([etq, r["variante"], f"{int(r['n']):,}", n(r["conjunta_anunciada"]), n(r["frecuencia_observada"]),
                      f"{s(r['dif'])} ({n(r['ee'])})", z(r["z"]), n(r["producto_ingenuo"]), n(r["momio_justo_medio"], 2),
                      f"{n(r['logloss_conjunta'])} / {n(r['logloss_ingenua'])}", f"{s(r['d_ll_cte'], 4)} ({n(r['ee_d_ll_cte'], 4)})",
                      n(r["pendiente"], 2)])
F["combinada"] = tabla(enc, filas, ["---", "---"] + ["---:"] * 10)
filas = []
for i in range(10):
    f = [str(i + 1)]
    for v in ("segura", "equilibrada", "atrevida"):
        t = C["deciles"][v]
        f += [n(t["pronosticado"].iloc[i]), n(t["observado"].iloc[i]), z(t["z"].iloc[i])]
    filas.append(f)
F["combinada_deciles"] = tabla(["Decil", "Segura anunciada", "obs.", "z", "Equilibrada anunciada", "obs.", "z",
                                "Atrevida anunciada", "obs.", "z"], filas, ["---:"] * 10)
F["combinada_razon"] = {r["variante"]: float(r["frecuencia_observada"] / r["producto_ingenuo"]) for _, r in C["resumen"].iterrows()}
F["combinada_picks"] = {v: g.sort_values("veces", ascending=False).head(5)[["clave", "veces"]].values.tolist()
                        for v, g in C["picks"].groupby("variante")}
F["combinada_aciertos"] = {r["variante"]: float(r["picks_acertados_de_4"]) for _, r in C["resumen"].iterrows()}

# ---- diagnostico: ceros
c = R["ceros"]
ET = {"media_local": "Goles del local (media)", "media_visita": "Goles de la visita (media)", "local_sin_gol": "Local sin gol",
      "visita_sin_gol": "Visita sin gol", "0-0": "0-0", "ambos_anotan": "Ambos anotan"}
filas = []
for q in ET:
    f = [ET[q]]
    for m in ("poisson_simple", "ensamble_rho0", "ensamble"):
        r = c[(c["modelo"] == m) & (c["que"] == q)].iloc[0]
        f += [n(r["pron"], 4 if "media" not in q else 3), f"{s(r['dif'], 4 if 'media' not in q else 3)} ({z(r['z'])})"]
    f.insert(1, n(c[(c["modelo"] == "ensamble") & (c["que"] == q)]["obs"].iloc[0], 4 if "media" not in q else 3))
    filas.append(f)
F["ceros"] = tabla(["", "Observado", "`poisson_simple` pron.", "dif (z)", "`ensamble` rho = 0 pron.", "dif (z)",
                    "`ensamble` con rho pron.", "dif (z)"], filas)

# ---- distribuciones
def dist_md(t, nombre):
    return [[nombre, r["valor"], n(r["pron"], 4), n(r["obs"], 4), s(r["dif"], 4), z(r["z"])] for _, r in t.iterrows()]


filas = dist_md(R["dist_local"], "Goles del local") + dist_md(R["dist_visita"], "Goles de la visita") + \
    dist_md(R["dist_total"], "Total") + dist_md(R["dist_dif"], "Diferencia (local − visita)")
F["distribuciones"] = tabla(["Variable", "Valor", "Pronosticado", "Observado", "dif", "z"], filas, ["---", "---:", "---:", "---:", "---:", "---:"])
t0 = R["dist_dif_rho0"]
F["dif_rho0"] = {r["valor"]: (round(float(r["pron"]), 4), round(float(r["z"]), 2)) for _, r in t0.iterrows()}

dp = R2["dispersion_partido"]
NOMD = {"local": "Goles del local", "visita": "Goles de la visita", "total": "Total", "diferencia": "Diferencia",
        "covarianza local-visita": "Covarianza local-visita"}
filas = [[NOMD[r["que"]], n(r["var_modelo_media"], 3), n(r["cuadrado_obs_medio"], 3), "—" if np.isnan(r["razon"]) else n(r["razon"], 3),
          f"{s(r['dif'], 3)} ({n(r['ee'], 3)})", z(r["z"])] for _, r in dp.iterrows()]
F["dispersion_partido"] = tabla(["", "Varianza según el modelo", "Observada alrededor del pronóstico", "Razón", "dif (ee)", "z"], filas)

ce = R["celdas"]
filas = [[r["marcador"], n(r["pron_rho0"], 4), n(r["pron_rho"], 4), n(r["obs"], 4), z(r["z_rho0"]), z(r["z_rho"])] for _, r in ce.iterrows()]
F["celdas"] = tabla(["Marcador", "Pron. rho = 0", "Pron. con rho", "Observado", "z (rho = 0)", "z (con rho)"], filas)
er = R["efecto_rho"]
filas = [[f"`{r['clave']}`", n(r["pron_rho0"], 4), n(r["pron_rho"], 4), n(r["obs"], 4), f"{s(r['d_ll_rho_menos_rho0'], 4)} ({n(r['ee'], 4)})"]
         for _, r in er.iterrows()]
F["efecto_rho"] = tabla(["Mercado", "Pron. rho = 0", "Pron. con rho", "Observado", "d_ll con rho − sin rho (ee)"], filas)

di = R["dispersion"]
filas = [[f"`{r['modelo']}`", n(r["media_total"], 3), n(r["sd_total"], 3), f"{n(r['b_total'], 2)} ({n(r['ee_bT'], 2)})",
          f"{n(r['b_local'], 2)} ({n(r['ee_bL'], 2)})", f"{n(r['b_visita'], 2)} ({n(r['ee_bV'], 2)})",
          f"{n(r['b_reparto'], 2)} ({n(r['ee_bS'], 2)})", n(r["corr_total_obs"], 3)] for _, r in di.iterrows()]
F["dispersion"] = tabla(["Modelo", "Total esperado medio", "Desv. est. del total esperado", "b total (ee)", "b local (ee)",
                         "b visita (ee)", "b reparto (ee)", "corr. total esperado–observado"], filas)
q, qp = R["quintiles_total"], R["quintiles_total_ps"]
filas = [[str(i + 1), n(qp["pron"].iloc[i], 2), n(qp["obs"].iloc[i], 2), n(q["pron"].iloc[i], 2), n(q["obs"].iloc[i], 2)] for i in range(5)]
F["quintiles_total"] = tabla(["Quintil del total esperado", "`poisson_simple` pron.", "obs.", "`ensamble` pron.", "obs."], filas, ["---:"] * 5)

ad = R["adelgazamiento"]
filas = [[r["total"], f"{int(r['partidos']):,}", n(r["prop_1T_obs"], 3), n(r["sin_gol_1T_binom"], 3), n(r["sin_gol_1T_obs"], 3),
          n(r["sin_gol_2T_binom"], 3), n(r["sin_gol_2T_obs"], 3)] for _, r in ad.iterrows()]
F["adelgazamiento"] = tabla(["Goles del partido", "Partidos", "Proporción observada en el 1T", "Sin gol en el 1T: binomial",
                             "observado", "Sin gol en el 2T: binomial", "observado"], filas, ["---:"] * 7)
filas = dist_md(R["dist_1t"], "Goles en el 1T") + dist_md(R["dist_2t"], "Goles en el 2T")
F["dist_mitades"] = tabla(["Variable", "Valor", "Pronosticado", "Observado", "dif", "z"], filas, ["---", "---:", "---:", "---:", "---:", "---:"])

tr = R2["tramos"]
filas = []
for _, r in tr.iterrows():
    filas.append([r["tramo"], f"{int(r['n']):,}", f"{n(r['media_l_pron'] + r['media_v_pron'], 3)} / {n(r['media_l_obs'] + r['media_v_obs'], 3)}",
                  f"{s(r['total_dif'], 3)} ({z(r['total_z'])})", f"{s(r['O25_dif'], 3)} ({z(r['O25_z'])})",
                  f"{s(r['AA_SI_dif'], 3)} ({z(r['AA_SI_z'])})", f"{s(r['cero_l_dif'], 3)} / {s(r['cero_v_dif'], 3)}",
                  f"{s(r['cero_l_dif_nivel'], 3)} / {s(r['cero_v_dif_nivel'], 3)}", f"{n(r['disp_l'], 2)} / {n(r['disp_v'], 2)}",
                  f"{s(r['H_L-1.5_dif'], 3)} / {s(r['H_V-1.5_dif'], 3)}", f"{s(r['G2T_SI_dif'], 3)}"])
F["tramos"] = tabla(["Tramo (año)", "n", "Total pron. / obs.", "dif del total (z)", "Más de 2.5: dif (z)", "Ambos anotan: dif (z)",
                     "Sin gol local / visita: dif", "igual, con el nivel del tramo corregido", "Dispersión local / visita",
                     "Gana por 2+ local / visita: dif", "Gol 2T: dif"], filas)
to = R2["torneos"]
F["torneos"] = tabla(["Torneo", "n", "Total esperado", "Total observado", "dif"],
                     [[i, str(int(r["n"])), n(r["total_pron"], 2), n(r["total_obs"], 2), s(r["dif"], 2)] for i, r in to.iterrows()])

eq = R["equipos"].sort_values("dif")
filas = [[i, str(int(r["n"])), n(r["pron"], 3), n(r["obs"], 3), s(r["dif"], 3), z(r["z"]), n(r["pron_pc"], 3), n(r["obs_pc"], 3),
          s(r["dif_pc"], 3), z(r["z_pc"])] for i, r in eq.iterrows()]
F["equipos"] = tabla(["Equipo", "Partidos", "Se queda sin gol: pron.", "obs.", "dif", "z", "Deja en cero al rival: pron.", "obs.", "dif", "z"], filas)
F["equipos_n"] = {"total": len(eq), "n_min": int(eq["n"].min()), "chicos": eq.index[eq["n"] < 100].tolist()}
cl = R["ceros_por_lambda"]
filas = [[r["lado"], str(int(r["cuartil_lambda"])), n(r["lambda"], 2), n(r["goles_obs"], 2), n(r["cero_pron"], 3), n(r["cero_obs"], 3),
          n(r["2mas_pron"], 3), n(r["2mas_obs"], 3)] for _, r in cl.iterrows()]
F["ceros_por_lambda"] = tabla(["Lado", "Cuartil de lambda", "Lambda media", "Goles observados", "Sin gol: pron.", "obs.", "2 o más: pron.", "obs."],
                              filas, ["---"] + ["---:"] * 7)
enc_ = R2["encoger_mitad"]
F["encoger"] = tabla(["Mercado", "d_ll encogido − actual (ee)", "z"],
                     [[f"`{r['clave']}`", f"{s(r['d_ll'], 4)} ({n(r['ee'], 4)})", z(r["z"])] for _, r in enc_.iterrows()])
F["otros"] = {"p1": T["p1"], "descanso": {k: {a: float(b) for a, b in T["descanso_" + k].items() if a in ("logloss", "logloss_cte", "d_ll", "ee")}
                                          for k in ("ensamble", "poisson_simple")}, "descanso_par": T["descanso_par"],
              "rho": R["rho"], "varianzas": {k: [float(x) for x in v] if isinstance(v, tuple) else v for k, v in R["varianzas"].items()},
              "p1_diag": {k: [float(x) for x in v] for k, v in R["p1"].items()}, "g2t": R2["g2t"], "g1t": R2["g1t"],
              "p1_bajo_menos_alto": R2["p1_bajo_menos_alto"], "equipos_resumen": R["equipos_resumen"]}
json.dump(F, open(f"{SAL}/fragmentos.json", "w"), ensure_ascii=False, indent=1, default=float)
for k in ("deciles_zmax", "combinada_razon", "combinada_picks", "combinada_aciertos", "dif_rho0", "equipos_n", "deciles_aa_ps"):
    print(k, F[k])
print(json.dumps(F["otros"], default=float)[:1500])
