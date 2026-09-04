# -*- coding: utf-8 -*-
"""
================================================================================
 diagnostico_sonr.py · revisa los insumos del SONR antes de correr el reforecast
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 POR QUÉ EXISTE. La corrida de septiembre perdió 8 de los 11 ramos desde 202604 y
 nadie se enteró hasta comparar los Excel: `ParamSONR2026_3+9.csv` traía vacías las
 12 columnas de parámetros para esos ramos de 202604 en adelante, y como
 `.stack()` descarta los NaN, esas filas desaparecían de la salida sin error.
 Esto lo detecta ANTES de correr, en dos segundos.

 QUÉ REVISA
   1. Huecos: parámetros vacíos por ramo × fecha. Cada hueco es un ramo que se va
      a perder en la salida de ese mes.
   2. Cobertura de TablaBase_MetodoPropio: cohortes NoLAG por ramo.
   3. Curvas de desarrollo. `1 - LAG n` es la fracción aún NO reportada tras n
      años, así que debe ser decreciente y estar entre 0 y 1. Marca:
        · valores negativos  (más del 100% reportado: imposible)
        · tramos que suben   (se "des-reporta" siniestralidad)
        · cortes abruptos a cero (horizonte truncado)
        · IS constante los 12 meses (huele a valor por defecto sin actualizar)

 Uso:  python diagnostico_sonr.py [carpeta_de_Inputs]
       (por defecto, la carpeta donde está este archivo)
================================================================================
"""
import os
import sys

import numpy as np
import pandas as pd

LAGC = [f"LAG {i}" for i in range(1, 11)]
PARS = ["Ind Sin SONR Media", "Ind Sin SONR 99.5%"] + LAGC


def revisa_param(ruta):
    P = pd.read_csv(ruta)
    nom = os.path.basename(ruta)
    print(f"\n{'=' * 96}\n{nom}   ({len(P):,} filas)\n{'=' * 96}")
    falta = [c for c in ["Llave", "Fecha", "Ramo"] + PARS if c not in P.columns]
    if falta:
        print(f"  [x] le faltan columnas: {falta}")
        return None

    # ---- 1. huecos
    hue = P[P[PARS].isna().any(axis=1)]
    if len(hue):
        print(f"  [X] {len(hue)} filas con parámetros VACÍOS de {len(P)} ({100*len(hue)/len(P):.0f}%).")
        print(f"      Cada una es un ramo que NO saldrá en la Base SONR de ese mes.")
        print(f"      ramos : {sorted(hue.Ramo.unique())}")
        print(f"      fechas: {sorted(hue.Fecha.unique())}")
        piv = P.pivot_table(index="Ramo", columns="Fecha", values="Ind Sin SONR Media", aggfunc="first")
        print("\n      'Ind Sin SONR Media'   (X = vacío):")
        print("      ramo  " + " ".join(f"{c % 10000:>6d}" for c in piv.columns))
        for r, row in piv.iterrows():
            print(f"      {r:5d} " + " ".join(("     X" if pd.isna(v) else f"{v:6.3f}") for v in row))
    else:
        print("  [ok] sin parámetros vacíos.")

    # ---- 2. curvas de desarrollo
    print("\n  Curvas de desarrollo — '1 - LAG n' = fracción aún NO reportada tras n años")
    print(f"  {'ramo':>5s} {'IS':>6s} " + " ".join(f"{'n=' + str(i):>6s}" for i in range(1, 11)) + f" {'Σ':>6s}")
    prob = {}
    for r, s in P[P[PARS].notna().all(axis=1)].groupby("Ramo"):
        lag = np.array([s[c].mean() for c in LAGC])
        nr = 1 - lag
        print(f"  {r:5d} {s['Ind Sin SONR Media'].mean():6.3f} " + " ".join(f"{x:6.3f}" for x in nr) + f" {nr.sum():6.2f}")
        p = []
        neg = [i + 1 for i, v in enumerate(nr) if v < -1e-9]
        if neg:
            p.append(f"'1-LAG' NEGATIVO en n={neg} (más del 100% reportado: imposible)")
        sube = [i + 2 for i, v in enumerate(np.diff(nr)) if v > 1e-6]
        if sube:
            p.append(f"curva NO decreciente en n={sube}")
        corte = [i + 1 for i in range(len(nr) - 1) if nr[i] > 0.3 and nr[i + 1] < 1e-9]
        if corte:
            p.append(f"CORTE de {nr[corte[0]-1]:.3f} a 0 entre n={corte[0]} y {corte[0]+1} (horizonte truncado)")
        if s["Ind Sin SONR Media"].nunique() == 1:
            p.append(f"IS CONSTANTE en todas las fechas ({s['Ind Sin SONR Media'].iloc[0]:.4f}): ¿valor por defecto?")
        if p:
            prob[int(r)] = p
    if prob:
        print("\n  [X] curvas con problemas:")
        for r, p in prob.items():
            print(f"      ramo {r}: " + "; ".join(p))
    else:
        print("\n  [ok] todas las curvas son decrecientes y están en [0, 1].")
    return P


def revisa_tabla(ruta):
    T = pd.read_csv(ruta)
    print(f"\n{'=' * 96}\n{os.path.basename(ruta)}\n{'=' * 96}")
    g = T.groupby("Ramo").NoLAG.agg(["count", "min", "max"])
    mx = int(g["count"].max())
    print(f"  cohortes NoLAG por ramo (el máximo del archivo es {mx}):")
    for r, x in g.iterrows():
        flag = "" if x["count"] == mx else f"   <-- sólo {int(x['count'])} cohortes, horizonte más corto"
        print(f"      ramo {r:4d}: {int(x['count']):2d}  (NoLAG {int(x['min'])}..{int(x['max'])}){flag}")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    print(f"Insumos SONR en: {base}")
    hay = False
    for f in sorted(os.listdir(base)):
        if f.lower().startswith("paramsonr") and f.lower().endswith(".csv"):
            revisa_param(os.path.join(base, f)); hay = True
    for f in sorted(os.listdir(base)):
        if f.lower().startswith("tablabase_metodopropio") and f.lower().endswith(".csv"):
            revisa_tabla(os.path.join(base, f)); hay = True
    if not hay:
        raise SystemExit(f"[diag] No encontré ParamSONR*.csv ni TablaBase_MetodoPropio*.csv en {base}")
    print("\nRecordatorio: ReforecastSONR_aod.py lee ParamSONR2026_3+9.csv y FCST_SONR.py lee")
    print("ParamSONR2026.csv. Si uno de los dos está incompleto, las dos corridas NO son comparables.")


if __name__ == "__main__":
    main()
