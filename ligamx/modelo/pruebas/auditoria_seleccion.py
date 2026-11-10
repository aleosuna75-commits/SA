# -*- coding: utf-8 -*-
"""
Auditoría · SESGO DE SELECCIÓN de la corrección `ajuste`, sin tocar la PRUEBA (no es pytest):

    cd /home/user/SA/ligamx && python3 -m modelo.pruebas.auditoria_seleccion

Las seis variables de `ajuste` se escogieron mirando TODO DESARROLLO (las que sobrevivieron a la corrección
por pruebas múltiples entre 309, VARIABLES.md §5.1) y luego su ganancia se midió en ese mismo periodo.
Aquí se repite la elección con honestidad dentro de DESARROLLO:

  mitad de selección     H1 = Apertura 2016 a Clausura 2021 (10 torneos)
  mitad de confirmación  H2 = Apertura 2021 a Clausura 2025 (8 torneos)

  1. Se corre el MISMO análisis univariado del proyecto (variables.analisis_exploratorio, base Elo)
     sólo con H1 y se aplican dos reglas fijadas antes de mirar H2:
        regla A: las variables disponibles con q de Benjamini-Hochberg < 0.10 (la regla original);
        regla B: las 6 variables disponibles de menor valor p (mismo tamaño que el campeón).
  2. Con cada conjunto se arma un `Ajuste` (misma base dc, mismo ridge 1000) y se evalúa walk-forward
     en H2, pareado contra `dc` y contra el `ajuste` real (cuyas variables sí vieron H2).
  3. Se reporta además la z univariada de las seis variables del campeón en H1, en H2 y en todo
     DESARROLLO (la "maldición del ganador" se ve como una z que se encoge fuera de la mitad que eligió).

Cada evaluación queda en el registro de variantes (familia "auditoria", parcial). No se guarda nada en pred/.
Resultado: modelo/pruebas/auditoria_resultados/seleccion.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from modelo import arnes, datos, metricas, variables as V   # noqa: E402
from modelo.familias import candidatos as C                 # noqa: E402

DIR_SAL = Path(__file__).resolve().parent / "auditoria_resultados"
SEIS = [c for g in C.GRUPOS_FINALES for c in C.GRUPOS_AJUSTE[g]]


def main():
    DIR_SAL.mkdir(exist_ok=True)
    torneos = datos.torneos_de("desarrollo")
    corte = torneos.index("Apertura 2021")
    H1, H2 = torneos[:corte], torneos[corte:]
    tab = V.cargar("bloque")
    res: dict = {"H1": [H1[0], H1[-1], len(H1)], "H2": [H2[0], H2[-1], len(H2)]}

    # ------------------------------------------------------------------ 1. selección sólo con H1
    an = {"H1": V.analisis_exploratorio(tab[tab["torneo"].isin(H1)]),
          "H2": V.analisis_exploratorio(tab[tab["torneo"].isin(H2)]),
          "todo": V.analisis_exploratorio(tab)}
    a1 = an["H1"]
    disp = a1[a1["disponible"].isin(["si", "si*"]) & a1["p_rv"].notna()].sort_values("p_rv")
    disp = disp[~disp["variable"].str.endswith("_dif")]          # como el campeón: variables por lado, no diferencias
    regla_a = disp.loc[disp["q_bh"] < 0.10, "variable"].tolist()
    regla_b = disp["variable"].head(6).tolist()
    res["regla_A_q<0.10_en_H1"] = regla_a
    res["regla_B_top6_en_H1"] = regla_b
    res["top12_H1"] = disp.head(12)[["variable", "z", "p_rv", "q_bh"]].round(4).to_dict("records")
    print("regla A (q < 0.10 en H1):", regla_a)
    print("regla B (6 de menor p en H1):", regla_b)
    z = {k: v.set_index("variable")["z"] for k, v in an.items()}
    q = {k: v.set_index("variable")["q_bh"] for k, v in an.items()}
    res["z_de_las_seis"] = {v: {k: round(float(z[k][v]), 2) for k in an} | {"q_H1": round(float(q["H1"][v]), 3),
                                                                           "q_todo": round(float(q["todo"][v]), 3)}
                            for v in SEIS}
    print(pd.DataFrame(res["z_de_las_seis"]).T.to_string())
    todo = an["todo"]
    sobre = todo[todo["disponible"].isin(["si", "si*"]) & (todo["q_bh"] < 0.10)]["variable"].tolist()
    res["sobreviven_en_todo_desarrollo"] = sobre
    res["n_variables_disponibles_probadas"] = int((todo["disponible"].isin(["si", "si*"]) & todo["p_rv"].notna()).sum())

    # ------------------------------------------------------------------ 2. evaluación en H2
    dc = arnes.leer_pred("dc").set_index("id")
    aj = arnes.leer_pred("ajuste").set_index("id")

    def ll(t):
        return pd.Series(metricas.logloss_1x2(t[["p_l", "p_e", "p_v"]].to_numpy(float), t["resultado"].to_numpy(int)), index=t.index)

    ids2 = dc.index[dc["torneo"].isin(H2)]
    bl = dc.loc[ids2, "bloque"].to_numpy()
    ll_dc, ll_aj = ll(dc.loc[ids2]), ll(aj.loc[ids2])
    base = metricas.diferencia_pareada(ll_aj.to_numpy(), ll_dc.to_numpy(), bl)
    res["ajuste_real_menos_dc_en_H2"] = {k: base[k] for k in ("dif", "ee", "z", "n")}
    ids1 = dc.index[dc["torneo"].isin(H1)]
    b1 = metricas.diferencia_pareada(ll(aj.loc[ids1]).to_numpy(), ll(dc.loc[ids1]).to_numpy(), dc.loc[ids1, "bloque"].to_numpy())
    res["ajuste_real_menos_dc_en_H1"] = {k: b1[k] for k in ("dif", "ee", "z", "n")}
    print("ajuste real - dc en H1:", res["ajuste_real_menos_dc_en_H1"])
    print("ajuste real - dc en H2:", res["ajuste_real_menos_dc_en_H2"])

    res["honesta"] = {}
    for nombre, cols in (("A", regla_a), ("B", regla_b)):
        if not cols:
            res["honesta"][nombre] = {"variables": [], "nota": "ninguna variable pasa la regla en H1: sin corrección (igual a dc)"}
            print(f"regla {nombre}: ninguna variable; la corrección honesta sería no corregir (dif = 0 frente a dc)")
            continue
        C.GRUPOS_AJUSTE[f"aud_{nombre}"] = list(cols)
        C._tablas_variables["bloque"] = tab.set_index("id")[sorted(set(cols) | set(SEIS))]
        m = C.Ajuste(C._dc(), ridge=1000, grupos=[f"aud_{nombre}"], nombre=f"ajuste_auditoria_regla{nombre}")
        m.familia = "auditoria"
        pred = arnes.evaluar(m, torneos=H2, guardar=False, verbose=False).set_index("id")
        assert set(pred.index) == set(ids2)
        l = ll(pred.loc[ids2])
        d_dc = metricas.diferencia_pareada(l.to_numpy(), ll_dc.to_numpy(), bl)
        d_aj = metricas.diferencia_pareada(l.to_numpy(), ll_aj.to_numpy(), bl)
        res["honesta"][nombre] = {"variables": cols, "logloss_H2": float(l.mean()), "logloss_dc_H2": float(ll_dc.mean()),
                                  "logloss_ajuste_real_H2": float(ll_aj.mean()),
                                  "menos_dc": {k: d_dc[k] for k in ("dif", "ee", "z", "n")},
                                  "menos_ajuste_real": {k: d_aj[k] for k in ("dif", "ee", "z")},
                                  "coeficientes_ultimo_reajuste": m.bitacora[-1]}
        print(f"regla {nombre}: honesta - dc en H2 = {d_dc['dif']:+.4f} (ee {d_dc['ee']:.4f}, z {d_dc['z']:+.1f});"
              f" honesta - ajuste real = {d_aj['dif']:+.4f} (ee {d_aj['ee']:.4f})")
    C._tablas_variables.clear()
    (DIR_SAL / "seleccion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
