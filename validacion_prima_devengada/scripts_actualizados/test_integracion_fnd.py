# -*- coding: utf-8 -*-
"""
================================================================================
 test_integracion_fnd.py · Prueba de regresión del FND calibrado
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 Verifica que el FND que devuelve la API de integración del módulo parchado
 (mec_devengamiento v3 · factor_no_devengado) reproduce EXACTAMENTE la prima no
 devengada con la que se calibró el modelo contra la RRC real. Si alguien cambia δ,
 la indexación o la cola del vector y con eso se rompe el cuadre, esta prueba lo
 dice de inmediato.

 Correr desde la carpeta del proyecto:  python3 scripts_actualizados/test_integracion_fnd.py
 Requiere insumos/ y salidas/ (los produce validar_prima_devengada.py).
================================================================================
"""
import os
import sys

import numpy as np
import pandas as pd

DIR = os.path.dirname(os.path.abspath(__file__))
PROY = os.path.dirname(DIR)
sys.path.insert(0, DIR)
import mec_devengamiento as mec                                    # noqa: E402

TOLERANCIA = 1.0            # USD sobre una reserva de ~500 M: cuadre al centavo
MESES_PRUEBA = (202312, 202412, 202512, 202605)
RAMOS = (10, 30, 40, 50, 60, 70, 80, 90, 100, 110)   # sin fianzas (sin RRC en la base)

# TC aproximado 2019–2021 (promedio Banxico); 2022+ sale de la base BEL-IRR-MR
TC_APROX = {
    2019: [19.16, 19.20, 19.26, 18.97, 19.14, 19.30, 19.05, 19.65, 19.60, 19.36, 19.34, 19.11],
    2020: [18.83, 18.89, 22.37, 24.16, 23.42, 22.29, 22.44, 22.11, 21.71, 21.30, 20.42, 19.93],
    2021: [19.90, 20.30, 20.72, 20.02, 19.94, 20.05, 19.93, 20.07, 20.03, 20.51, 20.87, 20.85],
}


def _insumos():
    tc = pd.read_csv(os.path.join(PROY, "insumos", "tc_mensual_bd.csv")).set_index("Periodo")["TC"]
    extra = pd.Series({y * 100 + i + 1: v for y, vs in TC_APROX.items() for i, v in enumerate(vs)})
    tc = pd.concat([extra, tc]).sort_index()

    inp = pd.read_csv(os.path.join(PROY, "insumos", "input_mec_bd.csv"))
    inp = inp[(inp["Origen"] == "Real") & (inp["Ramo"].isin(RAMOS))].copy()
    inp["P_USD"] = inp["PrimaDevMes"] / inp["Periodo"].map(tc)
    inp["CALMONTH"] = inp["Periodo"]
    inp["IniVig"] = pd.to_datetime(inp["CohorteAAAAMM"].astype(str) + "01", format="%Y%m%d")

    cart = pd.read_csv(os.path.join(PROY, "insumos", "mec_vectores_h72.csv"),
                       index_col=0).loc["CARTERA"].to_numpy(float)
    esperado = (pd.read_csv(os.path.join(PROY, "salidas", "comparacion_mensual.csv"))
                  .groupby("PERIODO")["PND_CAL"].sum())
    return inp, cart, esperado


def main() -> int:
    cfg = mec.ConfigMEC()
    inp, cart, esperado = _insumos()
    tabla = mec.TablaFND({"0": cart}, cart, cfg)     # ramo sin vector propio -> cartera
    delta = mec.cargar_delta(os.path.join(PROY, "salidas"), cfg)

    fallos = []
    print(f"δ por ramo: {delta}\n")
    print(f"{'mes':>8} {'PND módulo (USD)':>20} {'PND calibración (USD)':>23} {'dif':>10} {'estado':>8}")
    for t in MESES_PRUEBA:
        d = inp[inp["CALMONTH"] <= t]
        f = d.apply(lambda r: mec.factor_no_devengado(tabla, r, 0.0, cfg,
                                                      mes_valuacion=t, delta=delta), axis=1)
        got, exp = float((d["P_USD"] * f).sum()), float(esperado.loc[t])
        ok = abs(got - exp) <= TOLERANCIA
        fallos.append(None if ok else (t, got, exp))
        print(f"{t:>8} {got:>20,.2f} {exp:>23,.2f} {got - exp:>10,.2f} {'OK' if ok else 'FALLA':>8}")

    # propiedades de la tabla que la validación dio por buenas
    assert mec.fnd_registro(60, -1) == 0.0, "k<0 debe dar 0 (prima aún no registrada)"
    assert mec.fnd_registro(60, 12) == 0.0, "k>=12 debe dar 0 (cola en cero)"
    assert mec.fnd_registro(31, 0) == mec.fnd_registro(30, 0), "31 debe colapsar a 30"
    assert mec.fnd_registro(71, 0) == mec.fnd_registro(70, 0), "71 debe colapsar a 70"
    assert 0.0 <= mec.fnd_registro(100, 0) <= 1.0, "el FND debe estar acotado a [0, 1]"
    assert mec.antiguedad_registro(202605, 202512) == 5, "antigüedad de registro mal calculada"
    v = mec.vector_registro(10, delta, horizonte=24)
    assert v[12:].sum() == 0.0, "la cola del vector debe ser cero"

    malos = [f for f in fallos if f]
    if malos:
        print("\nFALLA: el FND del módulo ya no reproduce la calibración.")
        for t, got, exp in malos:
            print(f"  {t}: módulo {got:,.2f} vs calibración {exp:,.2f}")
        return 1
    print("\nOK · el FND del módulo reproduce la calibración y las propiedades de la tabla.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
