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
    prob, curvas = {}, {}
    for r, s in P[P[PARS].notna().all(axis=1)].groupby("Ramo"):
        lag = np.array([s[c].mean() for c in LAGC])
        nr = 1 - lag
        curvas[int(r)] = nr
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
    return curvas


def revisa_tabla(ruta, curvas=None):
    """Cohortes NoLAG por ramo. `curvas` = {ramo: array '1-LAG'} para cruzarlo.

    Cuenta cohortes DISTINTAS, no filas: TablaBase_MetodoPropio_ext.csv repite
    cada (Ramo, NoLAG) por año, así que contar filas daba 40 y no 10.
    """
    T = pd.read_csv(ruta)
    print(f"\n{'=' * 96}\n{os.path.basename(ruta)}   ({len(T):,} filas)\n{'=' * 96}")
    extra = [c for c in T.columns if c not in ("Ramo", "NoLAG")]
    if extra:
        print(f"  desglosada además por {extra} -> se cuentan cohortes DISTINTAS, no filas")
    g = T.groupby("Ramo").NoLAG.agg(cohortes="nunique", minimo="min", maximo="max")
    mx = int(g["cohortes"].max())
    print(f"  cohortes NoLAG distintas por ramo (el máximo del archivo es {mx}):")
    for r, x in g.iterrows():
        n = int(x["cohortes"])
        nota = ""
        if n < mx:
            nota = f"   <-- sólo {n} cohortes"
            # ¿es coherente con la curva? si '1-LAG' ya es 0 más allá de la última
            # cohorte, truncar ahí no cambia nada y NO es un defecto.
            if curvas is not None and int(r) in curvas:
                nr = curvas[int(r)]
                if len(nr) > n and abs(nr[n:]).max() < 1e-9:
                    nota += f": coherente, '1-LAG' ya es 0 desde n={n + 1}"
                else:
                    nota += f": INCOHERENTE, la curva aún aporta en n>{n}"
        print(f"      ramo {r:4d}: {n:2d}  (NoLAG {int(x['minimo'])}..{int(x['maximo'])}){nota}")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    print(f"Insumos SONR en: {base}")
    hay = False
    curvas = None
    for f in sorted(os.listdir(base)):
        if f.lower().startswith("paramsonr") and f.lower().endswith(".csv"):
            c = revisa_param(os.path.join(base, f)); hay = True
            if curvas is None and c:
                curvas = c            # las del primer ParamSONR, para cruzarlas abajo
    for f in sorted(os.listdir(base)):
        if f.lower().startswith("tablabase_metodopropio") and f.lower().endswith(".csv"):
            revisa_tabla(os.path.join(base, f), curvas); hay = True
    if not hay:
        raise SystemExit(f"[diag] No encontré ParamSONR*.csv ni TablaBase_MetodoPropio*.csv en {base}")
    print(f"\n{'=' * 96}\nDOS COSAS QUE NO SE VEN EN LOS ARCHIVOS\n{'=' * 96}")
    print("  1. ReforecastSONR_aod.py lee ParamSONR2026_3+9.csv y FCST_SONR.py lee ParamSONR2026.csv.")
    print("     Si uno de los dos está incompleto, las dos corridas NO son comparables.")
    print("  2. Los dos escriben el MISMO SONR_esc.xlsx (y auxSONR_sum.xlsx y TablaTCSONR.xlsx)")
    print("     en Documents\\Outputs: el que corra al final pisa al otro sin avisar.")
    print("  3. TablaBase_MetodoPropio_ext.csv (la extensión anual 2026-2029) se lee pero NO se usa:")
    print("     sólo aparece en líneas comentadas de Metodo_propio_reforecast, que además nunca se")
    print("     llama. La proyección sale toda de Metodo_propio(), mensual.")


if __name__ == "__main__":
    main()
