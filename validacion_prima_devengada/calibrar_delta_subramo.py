# -*- coding: utf-8 -*-
"""Calibración final por SUBRAMO, dos formas, con validación fuera de muestra."""
exec(open("calib_subramo.py").read().split("filas = []")[0])
import numpy as np, pandas as pd, json

def bel2(sub, x, modo):
    fijo = sub.loc[~sub.aj, "BEL_mod"].sum(); a = sub[sub.aj]
    base = a.NT_k.to_numpy(); desp = (a.dM4.to_numpy() if modo == "escal" else 0.0) + x
    return fijo + float((a.w.to_numpy()*np.clip(base-desp, 0, 1)).sum())

def aj2(sub, ys, modo):
    best = None
    for x in GR:
        e = np.mean([abs(bel2(sub[sub.MES == m], x, modo)/ys[m]-1) for m in ys])
        if best is None or e < best[1]: best = (x, e)
    return best[0]

old = json.load(open("/home/user/SA/validacion_prima_devengada/salidas/delta_calibrado.json"))
new = json.load(open("/home/user/SA/validacion_prima_devengada/salidas/delta_recalibrado.json"))
D_PL, D_ES, fil, oos = {}, {}, [], []
for r in RAMOS:
    sub = d[d.Ramo == r]; g = GRUPO[r]
    ys = {m: Y.get((r, m), np.nan) for m in MESES}
    ys = {m: v for m, v in ys.items() if np.isfinite(v) and v != 0}
    if not ys: continue
    if not sub.aj.any():                       # CAT: δ no lo mueve, se conserva
        D_PL[r] = D_ES[r] = float(new.get(g, 0.0))
    else:
        D_PL[r] = aj2(sub, ys, "plana"); D_ES[r] = aj2(sub, ys, "escal")
    f = dict(Ramo=r, Grupo=g, real=sum(ys.values()), ajustable=bool(sub.aj.any()),
             d_grupo=float(new.get(g, 0.0)), d_plana=D_PL[r], d_escal=D_ES[r])
    for et, fn in (("leg", lambda m: sub[sub.MES == m].BEL_leg.sum()),
                   ("grp", lambda m: bel2(sub[sub.MES == m], float(new.get(g, 0.0)), "plana")),
                   ("pla", lambda m: bel2(sub[sub.MES == m], D_PL[r], "plana")),
                   ("esc", lambda m: bel2(sub[sub.MES == m], D_ES[r], "escal"))):
        f[f"eam_{et}"] = float(np.mean([abs(fn(m)/ys[m]-1) for m in ys]))
        f[f"raz_{et}"] = sum(fn(m) for m in ys)/sum(ys.values())
    fil.append(f)
    # fuera de muestra
    for mo in ys:
        yi = {m: v for m, v in ys.items() if m != mo}
        s = sub[sub.MES == mo]; y = ys[mo]
        xp = aj2(sub, yi, "plana") if sub.aj.any() else D_PL[r]
        xe = aj2(sub, yi, "escal") if sub.aj.any() else D_ES[r]
        oos.append(dict(Ramo=r, Grupo=g, mes=mo, real=y, dp=xp, de=xe,
                        r_leg=s.BEL_leg.sum()/y, r_grp=bel2(s, float(new.get(g, 0.0)), "plana")/y,
                        r_pla=bel2(s, xp, "plana")/y, r_esc=bel2(s, xe, "escal")/y))
R = pd.DataFrame(fil); O = pd.DataFrame(oos)
R.to_csv("final_calib_ramo.csv", index=False); O.to_csv("final_calib_oos.csv", index=False)
json.dump({str(int(k)): float(v) for k, v in sorted(D_PL.items())}, open("delta_subramo_plana.json", "w"), indent=2)
json.dump({str(int(k)): float(v) for k, v in sorted(D_ES.items())}, open("delta_subramo_escalonada.json", "w"), indent=2)

print("δ POR SUBRAMO · calibrado contra la RRC real (la misma fuente que la columna SAP)\n")
print(f"{'ramo':>5s} {'grupo':9s} {'real M':>8s} | {'δ hoy':>7s} | {'δ plana':>8s} | {'δ escal':>8s}")
for x in R.sort_values("real", ascending=False).itertuples():
    print(f"{x.Ramo:5d} {x.Grupo:9s} {x.real/1e6:8.1f} | {x.d_grupo:+7.3f} | {x.d_plana:+8.3f} | {x.d_escal:+8.3f}")

for et, sel in (("TODOS", O), ("SIN CAT", O[~O.Ramo.isin([71, 73])])):
    print(f"\n=== FUERA DE MUESTRA · {et}  ({len(sel)} pares ramo·mes) ===")
    print(f"  {'variante':34s} {'razón':>7s} {'EAM':>7s} {'peor':>7s} {'>10%':>6s}")
    for c, n in (("r_leg", "legado (la tabla de siempre)"), ("r_grp", "δ por grupo (el que te di)"),
                 ("r_pla", "δ por SUBRAMO, forma plana"), ("r_esc", "δ por SUBRAMO, forma escalonada")):
        e = (sel[c]-1).abs()
        print(f"  {n:34s} {np.average(sel[c], weights=sel.real):7.4f} {np.average(e, weights=sel.real):7.2%}"
              f" {e.max():7.1%} {100*(e > 0.10).mean():5.0f}%")
print("\nEstabilidad de δ entre los 4 pliegues (rango máx−mín):")
g = O.groupby("Ramo")[["dp", "de"]].agg(lambda x: x.max()-x.min())
print(f"  plana: media {g.dp.mean():.4f}, peor {g.dp.max():.3f}   ·   escalonada: media {g.de.mean():.4f}, peor {g.de.max():.3f}")
print("\nPor ramo, fuera de muestra (EAM), ordenado por peso:")
p = O.groupby("Ramo").apply(lambda x: pd.Series({
    "legado": (x.r_leg-1).abs().mean(), "δ grupo": (x.r_grp-1).abs().mean(),
    "δ plana": (x.r_pla-1).abs().mean(), "δ escal": (x.r_esc-1).abs().mean(),
    "real M": x.real.mean()/1e6}), include_groups=False)
p["mejor forma"] = np.where(p["δ escal"] < p["δ plana"], "escalonada", "plana")
p["vs legado (plana)"] = p["legado"] - p["δ plana"]
print(p.sort_values("real M", ascending=False).round(4).to_string())
