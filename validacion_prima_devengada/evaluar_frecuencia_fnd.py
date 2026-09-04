# -*- coding: utf-8 -*-
"""
================================================================================
 evaluar_frecuencia_fnd.py · ¿El FND debe escalonarse por la periodicidad de la cuenta?
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 PREGUNTA. La tabla xPND anterior daba un FND distinto según la frecuencia de la
 cuenta (columnas '1','2','3','6','0'). El FND del modelo no distingue frecuencia:
 la absorbe en el δ por ramo. ¿Se pierde precisión por eso? ¿Es ahí donde está la
 diferencia que se ve en ramos como Incendio, cuyo δ es cero?

 MÉTODO. Tres variantes, ajustadas y medidas contra la MISMA RRC real, en la misma
 ventana y con el mismo insumo:

   A · δ por ramo, frecuencia aplastada          -> es lo que está en producción hoy
   B · δ = M4(frecuencia), sin parámetro por ramo -> es, en esencia, la tabla anterior
   C · δ = M4(frecuencia) + δ residual por ramo   -> las dos cosas a la vez

 donde M4 es la regla del propio MEC, δ = (t−1)/2 · 30/365 con t = meses de la
 cuenta. Esa regla reproduce EXACTO las columnas de frecuencia de xPND (verificado
 para t = 3, 6 y 12), así que la tabla anterior ya era «NT(k) − δ_M4(t)».

 CÓMO CORRERLO. Pon en la misma carpeta este script, la carpeta insumos\ (la que
 arma preparar_insumos.py), validar_prima_devengada.py y la BD del MEC
 (BD_PptoTécnicoRPAT_GENERADA.xlsx), que es la única fuente de «Meses Periodo».
 Luego:  python evaluar_frecuencia_fnd.py

 LÍMITE CONOCIDO. La mezcla de periodicidad se toma de los meses que cubra la BD y
 se aplica al histórico completo; para los meses anteriores se usa la mezcla media
 del ramo. Con una BD que cubra toda la ventana de calibración, el reparto es exacto.
================================================================================
"""
import os, sys
import numpy as np, pandas as pd

R = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, R)


def _bd():
    """La BD del MEC: única fuente de «Meses Periodo». Se busca en esta carpeta."""
    import glob
    c = [x for pat in ("BD_Ppto*.xls*", "BD*Tecnico*RPAT*.xls*", "BD*Técnico*RPAT*.xls*", "BDReal*.xls*")
         for x in glob.glob(os.path.join(R, pat)) if not os.path.basename(x).startswith("~$")]
    if not c:
        raise SystemExit("[frec] No encontré la BD del MEC en " + R + ".\n"
                         "       Necesito el Excel con la columna «Meses Periodo».")
    return sorted(c, key=os.path.getmtime)[-1]
import validar_prima_devengada as V

NT = V.NT_M
d_m4 = lambda t: (t - 1) / 2 * 30 / 365


def a_fecha(s):
    s = pd.Series(s); f = pd.to_datetime(s, errors="coerce")
    num = pd.to_numeric(s, errors="coerce"); m = f.isna() & num.notna()
    if m.any():
        f.loc[m] = pd.to_datetime(num[m], unit="D", origin="1899-12-30", errors="coerce")
    return f


# ------------------------------------------------- 1. mezcla de periodicidad, de la BD 2024+
RUTA_BD = _bd()
print("BD del MEC:", os.path.basename(RUTA_BD))
bd = pd.read_excel(RUTA_BD, sheet_name="BD", header=1,
                   usecols=["Periodo", "Ramo", "Tipo Poliza", "Tipo Rea", "PrimasNal", "Meses Periodo"])
b = bd[bd["Tipo Poliza"].astype(str).str.startswith("P")].copy()
b = b[b["Ramo"].isin(V.RAMO2GRUPO)].copy()
b["Grupo"] = b["Ramo"].map(V.RAMO2GRUPO)
b = b[b["Tipo Rea"] != 2]                                   # sólo proporcional/facultativo
b["t"] = pd.to_numeric(b["Meses Periodo"], errors="coerce")
# la frecuencia sólo escalona donde el reforecast la aplica: TipoRea 1 fuera de CAT y Crédito
aplica = (b["Tipo Rea"] == 1) & (~b["Ramo"].isin([70, 71, 73, 100]))
# «Meses Periodo» = 0 es el código de cuenta ANUAL (columna '0' de xPND, δ_M4 = 0.452),
# NO mensual. Leerlo como mensual invierte la mezcla de la cartera por completo.
b.loc[b["t"] == 0, "t"] = 12.0
b.loc[~aplica | b["t"].isna(), "t"] = 1.0
BUCKETS = sorted(b["t"].unique())
print("Buckets de periodicidad (meses):", [int(x) for x in BUCKETS], " → δ_M4:",
      [round(d_m4(x), 4) for x in BUCKETS])

mix_gp = (b.pivot_table(index=["Grupo", "Periodo"], columns="t", values="PrimasNal", aggfunc="sum")
            .fillna(0.0))
mix_gp = mix_gp.div(mix_gp.sum(axis=1).replace(0, np.nan), axis=0)
mix_g = (b.pivot_table(index="Grupo", columns="t", values="PrimasNal", aggfunc="sum").fillna(0.0))
mix_g = mix_g.div(mix_g.sum(axis=1), axis=0)
print("\n=== mezcla de periodicidad por ramo (prima proporcional, BD 2024–2026) ===")
print((mix_g * 100).round(1).to_string())
print("\n  δ_M4 medio implícito por ramo (lo que un δ por ramo debería recoger si la frecuencia mandara):")
for g in mix_g.index:
    print(f"    {g:10s} {sum(mix_g.loc[g, t] * d_m4(t) for t in mix_g.columns):.4f}")

# ------------------------------------------------- 2. insumo completo de la calibración
tc = V.cargar_tc()
V.T1 = 202605
real, is_ram, _ = V.cargar_real()
inp = V.cargar_input(tc)
vecs = pd.read_csv(os.path.join(V.INS, "mec_vectores_h72.csv"), index_col=0)
cart = vecs.loc["CARTERA"].to_numpy(dtype=float)
print(f"\nInsumo de calibración: {len(inp):,} filas · periodos {inp.Periodo.min()}–{inp.Periodo.max()}"
      f" · prima {inp.P_USD.sum()/1e6:,.0f} M USD")

grupos = sorted(V.GRUPOS)
gidx = np.array([grupos.index(g) for g in inp.Grupo])
prop = (inp.TipoRea != 2).to_numpy()
P = inp.P_USD.to_numpy(); mreg = inp.m_reg.to_numpy(); mcoh = inp.m_coh.to_numpy()

# peso de cada bucket para cada fila proporcional, según la mezcla de su (Grupo, Periodo)
W = np.zeros((len(inp), len(BUCKETS)))
for j, t in enumerate(BUCKETS):
    w = [mix_gp.loc[(g, per), t] if (g, per) in mix_gp.index else mix_g.loc[g, t]
         for g, per in zip(inp.Grupo, inp.Periodo)]
    W[:, j] = np.nan_to_num(np.array(w, dtype=float))
W = W / W.sum(axis=1, keepdims=True)

tt = V.meses(V.CAL0, 202605)
fixed = {g: np.zeros(len(tt)) for g in grupos}
Pk = {g: np.zeros((len(tt), 12)) for g in grupos}
Pkb = {g: np.zeros((len(tt), 12, len(BUCKETS))) for g in grupos}
for i, t in enumerate(tt):
    kr = int(V.midx(t)) - mreg
    kc = int(V.midx(t)) - mcoh
    fnp = np.zeros(len(P)); fnp[~prop] = V._vec_lookup(cart, kc[~prop]); fnp[kr < 0] = 0
    s = np.bincount(gidx, weights=P * fnp, minlength=len(grupos))
    for gj, g in enumerate(grupos):
        fixed[g][i] = s[gj]
        m = prop & (gidx == gj) & (kr >= 0) & (kr < 12)
        Pk[g][i] = np.bincount(kr[m], weights=P[m], minlength=12)[:12]
        for j in range(len(BUCKETS)):
            np.add.at(Pkb[g][i], (kr[m], np.full(int(m.sum()), j)), P[m] * W[m, j])

rr = real.set_index(["Grupo", "PERIODO"])["PND_real"]
GRID = np.round(np.arange(-0.30, 0.601, 0.005), 3)


def ajusta(g, modo):
    y = np.array([rr.get((g, t), np.nan) for t in tt])
    ok = ~np.isnan(y) & (np.array(tt) >= V.CAL0_GRUPO.get(g, V.CAL0))
    if ok.sum() == 0:
        return None
    if modo == "B":
        m = fixed[g] + sum(Pkb[g][:, :, j] @ np.clip(NT - d_m4(t), 0, 1) for j, t in enumerate(BUCKETS))
        return 0.0, m, y, ok
    best = None
    for d in GRID:
        if modo == "A":
            m = fixed[g] + Pk[g] @ np.clip(NT - d, 0, 1)
        else:
            m = fixed[g] + sum(Pkb[g][:, :, j] @ np.clip(NT - d_m4(t) - d, 0, 1) for j, t in enumerate(BUCKETS))
        sse = np.sum((m[ok] - y[ok]) ** 2)
        if best is None or sse < best[1]:
            best = (d, sse, m)
    return best[0], best[2], y, ok


print("\n" + "=" * 100)
print("A = δ por ramo (producción)  ·  B = M4 por frecuencia, sin δ  ·  C = M4 por frecuencia + δ residual por ramo")
print("=" * 100)
print(f"{'Ramo':10s} {'PND M USD':>9s} | {'δ_A':>7s} {'ratio_A':>7s} {'MAPE_A':>7s} | {'ratio_B':>7s} {'MAPE_B':>7s}"
      f" | {'δ_C':>7s} {'ratio_C':>7s} {'MAPE_C':>7s}")
tot = {}
for g in grupos:
    o = {m: ajusta(g, m) for m in "ABC"}
    if o["A"] is None:
        continue
    y, ok = o["A"][2], o["A"][3]
    v = {}
    for m in "ABC":
        d, mm, _, _ = o[m]
        v[m] = (d, mm[ok].sum() / y[ok].sum(), np.mean(np.abs(mm[ok] / y[ok] - 1)))
        tot.setdefault(m, []).append((mm[ok], y[ok]))
    print(f"{g:10s} {y[ok].mean()/1e6:9.0f} | {v['A'][0]:+7.3f} {v['A'][1]:7.3f} {v['A'][2]:7.1%} |"
          f" {v['B'][1]:7.3f} {v['B'][2]:7.1%} | {v['C'][0]:+7.3f} {v['C'][1]:7.3f} {v['C'][2]:7.1%}")
print("-" * 100)
for m in "ABC":
    mm = np.concatenate([a for a, _ in tot[m]]); yy = np.concatenate([bq for _, bq in tot[m]])
    print(f"  TOTAL {m}:  ratio {mm.sum()/yy.sum():.4f}   MAPE {np.mean(np.abs(mm/yy-1)):.2%}"
          f"   |error| medio {np.mean(np.abs(mm-yy))/1e6:.1f} M USD")

# ------------------------------------------------- métricas agregadas e impacto en reserva
print("\n" + "=" * 100)
print("Métricas sobre el TOTAL de la cartera (suma de ramos por mes)")
print("=" * 100)
serie = {}
for m in "ABC":
    acum = None
    for g in grupos:
        o = ajusta(g, m)
        if o is None:
            continue
        d, mm, y, ok = o
        df = pd.DataFrame({"modelo": np.where(ok, mm, np.nan), "real": np.where(ok, y, np.nan)}, index=tt)
        acum = df if acum is None else acum.add(df, fill_value=0)
    acum = acum.dropna()
    serie[m] = acum
    mo, re_ = acum["modelo"], acum["real"]
    print(f"  variante {m}:  ratio {mo.sum()/re_.sum():.4f}   MAPE mensual del total {np.mean(np.abs(mo/re_-1)):.2%}"
          f"   PND al {acum.index[-1]}: modelo {mo.iloc[-1]/1e6:,.1f} vs real {re_.iloc[-1]/1e6:,.1f} M USD"
          f" ({mo.iloc[-1]/re_.iloc[-1]-1:+.2%})")
print("\nImpacto en la prima NO devengada al cierre de la ventana, contra la variante A (producción):")
a = serie["A"]["modelo"].iloc[-1]
for m in "BC":
    v = serie[m]["modelo"].iloc[-1]
    print(f"  {m}: {v/1e6:,.1f} M USD   ({(v-a)/1e6:+,.1f} M USD, {v/a-1:+.2%} vs A)")
