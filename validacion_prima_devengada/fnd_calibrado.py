# -*- coding: utf-8 -*-
"""
================================================================================
 fnd_calibrado.py · Tabla FND calibrada contra la prima devengada REAL
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 Resultado de validar_prima_devengada.py: la RRC real (base BEL-IRR-MR) devenga la
 prima proporcional y facultativa por ANTIGÜEDAD DE REGISTRO con la recta de la Nota
 Técnica (24-avos), no por antigüedad desde el inicio de vigencia. Por eso el FND
 aquí se indexa por k_reg = mes de valuación − mes de registro, y el único parámetro
 por ramo es el desplazamiento δ de la regla M4 del MEC (frecuencia de cuentas):

     FND_ramo(k_reg) = max(0, NT(k_reg) − δ_ramo),  k_reg = 0..11, 0 después

 El no proporcional (TipoRea 2) conserva la prorrata exacta por fechas de vigencia
 (cuando hay fechas) o la curva PF+ de cartera por antigüedad de cohorte.

 ESTE ARCHIVO NO ES UN PASO DEL PROCESO. Es un módulo de CONSULTA: no lee ningún
 input, no escribe ningún archivo y no tiene interruptor. Corrido directamente
 (python fnd_calibrado.py) sólo imprime los δ y la tabla FND en pantalla, para
 poder verla sin abrir el Excel. El proceso — input, output del MEC y los dos
 reforecast — usa mec_devengamiento.py, no este archivo.

 DÓNDE ESTÁ EL INTERRUPTOR True / False (no está aquí):
     reforecastRRC_v11_Esc1_ocl.py   USAR_FND_CALIBRADO   (bloque «FND CALIBRADO», arriba)
     ReforecastSONR_v4.py            USAR_FND_CALIBRADO   (bloque «FND CALIBRADO», arriba)
     mec_devengamiento.py            ConfigMEC.USAR_CALIBRADO   (gobierna el output del MEC)
 True  = FND calibrado por antigüedad de REGISTRO (lo que cuadra con la RRC real).
 False = comportamiento anterior, el FND sale de los diccionarios xPND / xPND2.
 Ver LEEME_carpeta_local.md, sección 3.

 USO como librería (sustituye la búsqueda en xPND dentro de ConsultaReal / zFND):
     from fnd_calibrado import fnd_calibrado, factor_no_devengado_cal
     f = fnd_calibrado(ramo=60, k_reg=3)                       # proporcional / facultativo
     f = factor_no_devengado_cal(row, mes_valuacion=202605)    # row del reforecast RRC

 IMPORTANTE: el corte para el FND es el MES DE VALUACIÓN (variable `Meses` del
 reforecast), no el CALMONTH del registro. Si se integra vía mec_devengamiento,
 pasar la fecha de valuación como `calmonth` a fnd_exacto/antiguedad_de_row.
================================================================================
"""
from __future__ import annotations
import json, os
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))

# Nota Técnica / xPND cuentas mensuales: antigüedad de registro k = 0..11
NT_M = np.array([0.95890411, 0.876712329, 0.791780822, 0.706849315, 0.624657534, 0.539726027,
                 0.457534247, 0.37260274, 0.295890411, 0.210958904, 0.126027397, 0.043835616])

# δ calibrado por ramo (mínimos cuadrados vs prima no devengada real, 202301–202605;
# CAT desde 202401). Se recarga de salidas/delta_calibrado.json si existe.
DELTA_RAMO = {10: 0.070, 30: 0.045, 40: 0.000, 50: -0.010, 60: 0.000, 70: -0.050,
              80: 0.095, 90: 0.130, 100: -0.080, 110: 0.000}
GRUPO_RAMO = {"Vida": 10, "AyE": 30, "RC": 40, "MyT": 50, "Incendio": 60, "CAT": 70,
              "Agro": 80, "Autos": 90, "Credito": 100, "Diversos": 110}
# subramos del catálogo SIREC que caen en cada ramo de la tabla
SUBRAMO = {31: 30, 34: 30, 35: 30, 37: 30, 39: 30, 71: 70, 73: 70, 20: 10}

_json = os.path.join(BASE, "salidas", "delta_calibrado.json")
if os.path.exists(_json):
    with open(_json) as _f:
        DELTA_RAMO.update({GRUPO_RAMO[g]: float(d) for g, d in json.load(_f).items() if g in GRUPO_RAMO})

# curva PF+ de cartera (prorrata exacta de vigencias reales) por antigüedad de cohorte,
# para el no proporcional sin fechas; se recarga de insumos/mec_vectores_h72.csv si existe.
_csv = os.path.join(BASE, "insumos", "mec_vectores_h72.csv")
if os.path.exists(_csv):
    PF_CARTERA = pd.read_csv(_csv, index_col=0).loc["CARTERA"].to_numpy(dtype=float)
else:
    PF_CARTERA = np.array([0.9286, 0.8441, 0.7584, 0.6747, 0.5925, 0.5122, 0.4314, 0.3519,
                           0.2726, 0.1956, 0.1213, 0.0466, 0.0316, 0.0274])


def _ramo_tabla(ramo) -> int:
    r = int(float(ramo))
    return SUBRAMO.get(r, r)


def vector_calibrado(ramo, horizonte: int = 24) -> np.ndarray:
    """Vector FND por antigüedad de registro para el ramo (cola en cero)."""
    d = DELTA_RAMO.get(_ramo_tabla(ramo), 0.0)
    v = np.zeros(horizonte)
    v[:12] = np.clip(NT_M - d, 0.0, 1.0)
    return v


def tabla_calibrada(horizonte: int = 12) -> pd.DataFrame:
    t = pd.DataFrame({f"{g} ({r})": vector_calibrado(r, horizonte) for g, r in GRUPO_RAMO.items()}).T
    t.columns = [f"k={k}" for k in range(horizonte)]
    return t


def fnd_calibrado(ramo, k_reg: int) -> float:
    """FND para prima proporcional/facultativa registrada hace k_reg meses."""
    if k_reg is None or k_reg < 0 or k_reg >= 12:
        return 0.0
    return float(vector_calibrado(ramo)[int(k_reg)])


def fnd_prorrata(inivig, finvig, fecha_valuacion) -> float | None:
    """Prorrata exacta por fechas (no proporcional). None si faltan fechas."""
    try:
        ini, fin, val = pd.Timestamp(inivig), pd.Timestamp(finvig), pd.Timestamp(fecha_valuacion)
    except Exception:
        return None
    if pd.isna(ini) or pd.isna(fin):
        return None
    dur = (fin - ini).days
    if dur <= 0:
        return 0.0
    return float(np.clip((fin - val).days / dur, 0.0, 1.0))


def _k(mes_valuacion: int, mes_registro: int) -> int:
    a, b = int(mes_valuacion), int(mes_registro)
    return (a // 100 - b // 100) * 12 + (a % 100 - b % 100)


def factor_no_devengado_cal(row, mes_valuacion: int, fecha_valuacion=None,
                            col_ramo="Ramo", col_calmonth="CALMONTH", col_tipo="TipoRea",
                            col_ini="IniVig", col_fin="FinVig", col_cohorte=None) -> float:
    """Drop-in para el reforecast RRC (sustituye xPND.get(CALMONTH).get(FRECUENCIA)).

    row            : registro con Ramo, CALMONTH (mes de registro AAAAMM), TipoRea, IniVig, FinVig
    mes_valuacion  : AAAAMM de la valuación (variable `Meses` del reforecast)
    fecha_valuacion: fecha de corte (zFechaValuacion) para la prorrata del no proporcional
    """
    k_reg = _k(mes_valuacion, row[col_calmonth])
    if k_reg < 0:
        return 0.0
    tipo = int(row[col_tipo]) if col_tipo in row else 1
    if tipo == 2:
        f = fnd_prorrata(row.get(col_ini), row.get(col_fin), fecha_valuacion) if fecha_valuacion is not None else None
        if f is not None:
            return f
        if col_cohorte and col_cohorte in row:
            k_coh = _k(mes_valuacion, row[col_cohorte])
            return float(PF_CARTERA[k_coh]) if 0 <= k_coh < len(PF_CARTERA) else 0.0
        return float(PF_CARTERA[k_reg]) if k_reg < len(PF_CARTERA) else 0.0
    return fnd_calibrado(row[col_ramo], k_reg)


if __name__ == "__main__":
    pd.set_option("display.width", 200); pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    print("δ por ramo:", DELTA_RAMO)
    print(tabla_calibrada())
