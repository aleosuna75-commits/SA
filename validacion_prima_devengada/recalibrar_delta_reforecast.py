# -*- coding: utf-8 -*-
"""
================================================================================
 recalibrar_delta_reforecast.py · δ ajustado sobre la BASE DE PRIMA DEL REFORECAST
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 POR QUÉ EXISTE. El δ de delta_calibrado.json se ajustó para que
 «Σ prima_BD-MEC × FND ≈ prima no devengada real». El reforecast aplica ese δ sobre
 otra base de prima —la consulta a BD Gonzalo, con sus filtros— que produce del
 orden de 10% más prima no devengada con el MISMO FND. Por eso el δ no transfiere
 y el reforecast sobreestima ~9.5% (sin CAT). Este script vuelve a ajustar δ usando
 la prima del propio reforecast, que es la base sobre la que se va a aplicar.

 QUÉ NECESITA, todo en la misma carpeta que este script:
   · ConsultaPPTO_RRC_<mes>_tradicional.xlsx  — uno o varios; los escribe el propio
     reforecast en Documents\\Outputs. Debe traer, por registro:
         Ramo · TipoRea · CALMONTH · FRECUENCIA · MONTO_PI · BELMEDIA · PORC_ND
         (y TC_Valuación si el monto viene en moneda original)
     El <mes> del nombre es el mes de valuación (1..12) del año ANIO_VALUACION.
   · insumos\\real_rrc_long.csv  — la RRC real (la arma preparar_insumos.py)
   · insumos\\tc_mensual_bd.csv  — TC de cierre por mes
   · mec_devengamiento.py        — para NT y la tabla de ramos

 QUÉ HACE. Para cada ramo ajusta δ minimizando el error contra el BEL real, en dos
 variantes, y se queda con la mejor:
   ESCALONADA   FND = clip(NT(k) − δ_M4(frecuencia) − δ_ramo, 0, 1)   ← recomendada
   PLANA        FND = clip(NT(k) − δ_ramo, 0, 1)                      ← la de hoy
 donde δ_M4(t) = (t−1)/2·30/365 es la regla M4 del MEC, que es exactamente el
 escalonamiento por frecuencia que ya trae la tabla xPND del reforecast.

 Respeta la jerarquía de PORC_ND del script: los ramos 71/73 y el no proporcional
 (TipoRea 2) se dejan como están y no entran al ajuste.

 SALIDA:  delta_recalibrado.json  +  recalibracion_reforecast.csv  +  el resumen en pantalla.

 Uso:  python recalibrar_delta_reforecast.py
================================================================================
"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
INS = os.path.join(BASE, "insumos") if os.path.isdir(os.path.join(BASE, "insumos")) else BASE
sys.path.insert(0, BASE)

ANIO_VALUACION = 2026          # año de los archivos ConsultaPPTO_RRC_<mes>_tradicional
GRID = np.round(np.arange(-0.30, 0.801, 0.005), 3)

# grupos de la calibración (mismos que validar_prima_devengada.py)
RAMO2GRUPO = {10: "Vida", 20: "Vida", 30: "AyE", 31: "AyE", 34: "AyE", 35: "AyE", 37: "AyE", 39: "AyE",
              40: "RC", 50: "MyT", 60: "Incendio", 70: "CAT", 71: "CAT", 73: "CAT",
              80: "Agro", 90: "Autos", 100: "Credito", 110: "Diversos"}
# columna RAM del real -> ramo del reforecast
RAM2RAMO = {"RAM_10": 10, "RAM_30": 31, "RAM_34": 35, "RAM_37": 39, "RAM_40": 40, "RAM_50": 50,
            "RAM_60": 60, "RAM_71": 71, "RAM_73": 73, "RAM_80": 80, "RAM_90": 90,
            "RAM_100": 100, "RAM_110": 110}

try:
    import mec_devengamiento as mec
    NT = mec.NT_MENSUAL
except Exception:
    NT = np.array([0.95890411, 0.876712329, 0.791780822, 0.706849315, 0.624657534, 0.539726027,
                   0.457534247, 0.37260274, 0.295890411, 0.210958904, 0.126027397, 0.043835616])


def d_m4(t):
    """Regla M4 del MEC. Reproduce EXACTO las columnas de frecuencia de xPND."""
    return (t - 1) / 2 * 30 / 365


# código de FRECUENCIA del reforecast -> meses de la cuenta
FREC2MESES = {"1": 1, "2": 2, "3": 3, "6": 6, "0": 12, "NA": 1, "DEF": 3}


def meses_cuenta(f):
    s = str(f).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return FREC2MESES.get(s, 1)


def antiguedad(mes_val, calmonth):
    a, b = int(mes_val), int(calmonth)
    return (a // 100 - b // 100) * 12 + (a % 100 - b % 100)


def leer_consultas():
    """Cada ConsultaPPTO_RRC_<mes>_tradicional.xlsx, con su mes de valuación."""
    pat = os.path.join(BASE, "ConsultaPPTO_RRC_*_tradicional.xls*")
    arch = sorted(x for x in glob.glob(pat) if not os.path.basename(x).startswith("~$"))
    if not arch:
        raise SystemExit(
            "[recal] No encontré ningún «ConsultaPPTO_RRC_<mes>_tradicional.xlsx» en:\n"
            f"        {BASE}\n"
            "        Los escribe el propio reforecast en Documents\\Outputs; copia aquí dos o tres meses.")
    piezas = []
    for a in arch:
        m = re.search(r"ConsultaPPTO_RRC_(\d+)_tradicional", os.path.basename(a))
        if not m:
            continue
        mes = int(m.group(1))
        d = pd.read_excel(a)
        falta = [c for c in ("Ramo", "TipoRea", "CALMONTH", "FRECUENCIA", "MONTO_PI", "BELMEDIA", "PORC_ND")
                 if c not in d.columns]
        if falta:
            raise SystemExit(f"[recal] A «{os.path.basename(a)}» le faltan columnas: {falta}\n"
                             f"        Tiene: {list(d.columns)}")
        d["MES_VAL"] = ANIO_VALUACION * 100 + mes
        piezas.append(d)
        print(f"[recal] {os.path.basename(a)}: {len(d):,} registros · valuación {d.MES_VAL.iloc[0]}")
    return pd.concat(piezas, ignore_index=True)


def main():
    d = leer_consultas()
    for c in ("Ramo", "TipoRea", "CALMONTH", "MONTO_PI", "BELMEDIA", "PORC_ND"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if "TC_Valuación" in d.columns:
        d["TC_Val"] = pd.to_numeric(d["TC_Valuación"], errors="coerce").fillna(1.0)
    else:
        d["TC_Val"] = 1.0
    d = d.dropna(subset=["Ramo", "CALMONTH", "MONTO_PI", "BELMEDIA"])
    d["Grupo"] = d.Ramo.map(RAMO2GRUPO)
    d = d[d.Grupo.notna()].copy()
    d["k"] = [antiguedad(v, c) for v, c in zip(d.MES_VAL, d.CALMONTH)]
    d["t"] = [meses_cuenta(f) for f in d.FRECUENCIA]
    d["dM4"] = d_m4(d.t)

    # la jerarquía de PORC_ND: 71/73 y el no proporcional NO entran al ajuste
    d["ajustable"] = (~d.Ramo.isin([71, 73])) & (d.TipoRea != 2)
    d["peso"] = d.MONTO_PI * d.BELMEDIA * d.TC_Val         # BEL cuando FND = 1
    d["BEL_legado"] = d.peso * d.PORC_ND

    # BEL real (USD) y TC para pasar el archivo a USD
    real = pd.read_csv(os.path.join(INS, "real_rrc_long.csv"))
    real["Ramo"] = real.RAM.map(RAM2RAMO)
    real = real[real.Ramo.notna()].copy()
    real["Grupo"] = real.Ramo.map(RAMO2GRUPO)
    tc = pd.read_csv(os.path.join(INS, "tc_mensual_bd.csv")).set_index("Periodo")["TC"]
    meses_val = sorted(d.MES_VAL.unique())
    faltan = [m for m in meses_val if m not in real.PERIODO.values]
    if faltan:
        print(f"[recal] Aviso: la RRC real no cubre {faltan}; esos meses quedan fuera del ajuste.")
    rr = (real[real.PERIODO.isin(meses_val)].groupby(["Grupo", "PERIODO"])["RRC BEL"].sum())

    d["TC_mes"] = d.MES_VAL.map(tc)
    if d.TC_mes.isna().any():
        raise SystemExit(f"[recal] Sin TC para {sorted(d.loc[d.TC_mes.isna(),'MES_VAL'].unique())} en tc_mensual_bd.csv")
    d["peso_USD"] = d.peso / d.TC_mes
    d["BEL_legado_USD"] = d.BEL_legado / d.TC_mes

    delta_prod = {}
    jp = os.path.join(BASE, "delta_calibrado.json")
    if not os.path.exists(jp):
        jp = os.path.join(BASE, "salidas", "delta_calibrado.json")
    if os.path.exists(jp):
        delta_prod = json.load(open(jp, encoding="utf-8"))

    def bel(sub, dl, escalonada):
        """BEL en USD que produce δ = dl sobre este subconjunto."""
        fijo = sub.loc[~sub.ajustable, "BEL_legado_USD"].sum()
        a = sub[sub.ajustable]
        if a.empty:
            return fijo
        base = NT[np.clip(a.k.to_numpy(int), 0, len(NT) - 1)]
        base = np.where((a.k < 0) | (a.k >= len(NT)), 0.0, base)
        desp = (a.dM4.to_numpy() if escalonada else 0.0) + dl
        return fijo + float((a.peso_USD.to_numpy() * np.clip(base - desp, 0.0, 1.0)).sum())

    filas, mejor = [], {}
    print("\n" + "=" * 108)
    print(f"{'Ramo':10s} {'real':>10s} {'legado':>10s} {'razón':>6s} | {'δ prod':>7s} {'razón':>6s} |"
          f" {'δ plana':>7s} {'razón':>6s} | {'δ escal':>7s} {'razón':>6s}  <- recomendada")
    print("=" * 108)
    for g, sub in d.groupby("Grupo"):
        y = sum(rr.get((g, m), np.nan) for m in meses_val)
        if not np.isfinite(y) or y == 0:
            print(f"{g:10s}  (sin RRC real en estos meses; se omite)")
            continue
        leg = sub.BEL_legado_USD.sum()
        dp = float(delta_prod.get(g, 0.0))
        bprod = bel(sub, dp, False)
        best = {}
        for esc in (False, True):
            cand = min(GRID, key=lambda x: abs(bel(sub, x, esc) - y))
            best[esc] = (cand, bel(sub, cand, esc))
        mejor[g] = {"delta_escalonada": float(best[True][0]), "delta_plana": float(best[False][0])}
        print(f"{g:10s} {y/1e6:10.1f} {leg/1e6:10.1f} {leg/y:6.3f} | {dp:+7.3f} {bprod/y:6.3f} |"
              f" {best[False][0]:+7.3f} {best[False][1]/y:6.3f} | {best[True][0]:+7.3f} {best[True][1]/y:6.3f}")
        filas.append(dict(Grupo=g, BEL_real=y, BEL_legado=leg, razon_legado=leg / y,
                          delta_produccion=dp, razon_produccion=bprod / y,
                          delta_plana=best[False][0], razon_plana=best[False][1] / y,
                          delta_escalonada=best[True][0], razon_escalonada=best[True][1] / y,
                          dM4_medio=np.average(sub.loc[sub.ajustable, "dM4"],
                                               weights=sub.loc[sub.ajustable, "peso_USD"].abs())
                          if sub.ajustable.any() else 0.0))
    r = pd.DataFrame(filas)
    if r.empty:
        raise SystemExit("[recal] No hubo ningún ramo con RRC real en esos meses.")
    print("-" * 108)
    for et, col in [("legado", "razon_legado"), ("δ de producción", "razon_produccion"),
                    ("δ plana reajustada", "razon_plana"), ("δ escalonada reajustada", "razon_escalonada")]:
        tot = (r[col] * r.BEL_real).sum() / r.BEL_real.sum()
        mae = np.mean(np.abs(r[col] - 1))
        print(f"  {et:26s} razón total {tot:.4f}   error absoluto medio por ramo {mae:.2%}")

    r.to_csv(os.path.join(BASE, "recalibracion_reforecast.csv"), index=False)
    json.dump({g: v["delta_escalonada"] for g, v in mejor.items()},
              open(os.path.join(BASE, "delta_recalibrado.json"), "w", encoding="utf-8"), indent=2)
    print(f"\n[recal] delta_recalibrado.json (variante ESCALONADA) y recalibracion_reforecast.csv escritos en {BASE}")
    print("[recal] Para usarlo: sustituye delta_calibrado.json por delta_recalibrado.json y activa el")
    print("        escalonamiento por frecuencia en el FND del reforecast (ver README).")


if __name__ == "__main__":
    main()
