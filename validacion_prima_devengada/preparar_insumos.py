# -*- coding: utf-8 -*-
"""
================================================================================
 preparar_insumos.py · Genera la carpeta insumos/ para validar_prima_devengada.py
--------------------------------------------------------------------------------
 Planeación Financiera (BP&A) · Reaseguradora Patria (GPV)

 Lee los archivos CRUDOS que ya existen en la casa y los deja en el formato compacto
 que consume la validación. Pon este script junto a los archivos en tu carpeta de
 Documents y córrelo; crea insumos/ al lado.

 Archivos que busca en su propia carpeta (por patrón, tolera variantes de nombre):
   · BD_ BEL - IRR - MR.xlsx        -> real_rrc_long.csv · is_rrc_real.csv · tc_mensual_bd.csv
   · Input_MEC_Devengamiento.xlsx   -> input_mec_bd.csv           (lo produce construir_input_mec.py)
   · Registros_Vigencia_MEC.csv     -> mec_vectores_h72.csv       (curva PF+ con mec_devengamiento.py)
   · Integración*.xlsb  (OPCIONAL)  -> er_real_primas.csv         (% cedido por ramo del ER real;
                                       requiere pyxlsb; si no está, se conserva el CSV que ya exista)

 Salidas en insumos/ :
   real_rrc_long.csv    saldos RRC/SONR reales por concepto × ramo × mes (USD), sólo meses con saldo
   is_rrc_real.csv      'Ind Sin RRC' de HParametros (tipo Real) por mes × ramo, desde 202201
   tc_mensual_bd.csv    TC de cierre por mes (columna TC de BD_Montos_RRC_SONR)
   input_mec_bd.csv     Input del MEC, fuente BD (prima registrada por LN2 × ramo × cohorte × mes)
   mec_vectores_h72.csv curva PF+ de cartera y por ramo, horizonte 72 meses
   er_real_primas.csv   prima emitida / cedida / retenida / devengada por ramo del ER real
================================================================================
"""
from __future__ import annotations
import glob
import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
INS = os.path.join(BASE, "insumos")
os.makedirs(INS, exist_ok=True)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

DESDE_IS = 202201          # primer mes de índices que se conserva
HORIZONTE_PF = 72          # meses del vector PF+ (Vida tiene cola multianual)


def _buscar(patrones, obligatorio=True, que=""):
    """Busca el archivo en la carpeta del script y, como respaldo, en insumos/."""
    cand = []
    for p in patrones:
        cand += glob.glob(os.path.join(BASE, p))
        cand += glob.glob(os.path.join(INS, p))
    cand = sorted({c for c in cand if not os.path.basename(c).startswith("~$")}, key=os.path.getmtime, reverse=True)
    if cand:
        if len(cand) > 1:
            print(f"[insumos] Varios candidatos para {que}; uso el más reciente: {os.path.basename(cand[0])}")
        return cand[0]
    if obligatorio:
        raise SystemExit(f"[insumos] No encontré {que} en {BASE}. Patrones: {patrones}")
    return None


def _fila_encabezado(path, hoja, clave, max_filas=10):
    """Fila (0-based) donde aparece el nombre de columna `clave`."""
    raw = pd.read_excel(path, sheet_name=hoja, header=None, nrows=max_filas)
    for i in range(len(raw)):
        if any(str(v).strip() == clave for v in raw.iloc[i].tolist()):
            return i
    raise SystemExit(f"[insumos] No encontré la columna «{clave}» en la hoja {hoja} de {os.path.basename(path)}")


# ----------------------------------------------------------------------------
# 1 · Base BEL-IRR-MR
# ----------------------------------------------------------------------------
def base_bel_irr_mr():
    path = _buscar(["BD_ BEL - IRR - MR*.xls*", "BD*BEL*IRR*MR*.xls*", "*BEL*IRR*MR*.xls*"], que="la base BEL-IRR-MR")
    print(f"[insumos] Base BEL-IRR-MR: {os.path.basename(path)}")

    # --- saldos por concepto × ramo × mes ---
    hdr = _fila_encabezado(path, "BD_Montos_RRC_SONR", "CONCEPTO")
    bd = pd.read_excel(path, sheet_name="BD_Montos_RRC_SONR", header=hdr).dropna(axis=1, how="all")
    bd.columns = [str(c).strip() for c in bd.columns]
    bd = bd.dropna(subset=["CONCEPTO", "PERIODO"])
    bd["PERIODO"] = pd.to_numeric(bd["PERIODO"], errors="coerce").astype(int)
    ram = [c for c in bd.columns if c.startswith("RAM_")]
    for c in ram + ["TC", "RVATOT"]:
        bd[c] = pd.to_numeric(bd[c], errors="coerce")
    con_saldo = sorted(bd.loc[(bd["CONCEPTO"] == "RRC BRUTO") & (bd["RVATOT"].abs() > 0), "PERIODO"].unique())
    largo = bd.melt(id_vars=["CONCEPTO", "PERIODO"], value_vars=ram, var_name="RAM", value_name="v")
    w = largo.pivot_table(index=["PERIODO", "RAM"], columns="CONCEPTO", values="v", aggfunc="sum").reset_index()
    w.columns.name = None
    w = w[w["PERIODO"].isin(con_saldo)].copy()
    for a, b, nom in [("RRC IRR", "RRC BEL", "IRR/BEL"), ("RRC GTO", "RRC BEL", "GTO/BEL"), ("RRC MR", "RRC BEL", "MR/BEL")]:
        if a in w and b in w:
            w[nom] = w[a] / w[b]
    w.to_csv(os.path.join(INS, "real_rrc_long.csv"), index=False)
    print(f"[insumos]   real_rrc_long.csv · {len(w):,} filas · {con_saldo[0]}–{con_saldo[-1]} ({len(con_saldo)} meses con saldo)")

    # --- TC de cierre por mes (incluye meses proyectados) ---
    tc = bd.groupby("PERIODO")["TC"].first().dropna().reset_index()
    tc.columns = ["Periodo", "TC"]
    tc.to_csv(os.path.join(INS, "tc_mensual_bd.csv"), index=False)
    print(f"[insumos]   tc_mensual_bd.csv · {tc['Periodo'].min()}–{tc['Periodo'].max()}")

    # --- índices de siniestralidad reales ---
    hdr = _fila_encabezado(path, "HParametros_2026", "Tipo de Indice")
    hp = pd.read_excel(path, sheet_name="HParametros_2026", header=hdr)
    hp.columns = [str(c).strip() for c in hp.columns]
    falt = {"Tipo de Indice", "Fecha", "Ramo", "Ind Sin RRC"} - set(hp.columns)
    if falt:
        raise SystemExit(f"[insumos] A HParametros_2026 le faltan columnas {falt}")
    hp = hp.dropna(subset=["Tipo de Indice"])
    hp["Fecha"] = pd.to_numeric(hp["Fecha"], errors="coerce")
    hp["Ramo"] = hp["Ramo"].astype(str).str.strip()
    real = hp[(hp["Tipo de Indice"] == "Real") & (hp["Fecha"] >= DESDE_IS)]
    pv = real.pivot_table(index="Fecha", columns="Ramo", values="Ind Sin RRC", aggfunc="first")
    pv.index = pv.index.astype(int)
    pv.to_csv(os.path.join(INS, "is_rrc_real.csv"))
    print(f"[insumos]   is_rrc_real.csv · {pv.index.min()}–{pv.index.max()} · ramos {list(pv.columns)}")
    return con_saldo[-1]


# ----------------------------------------------------------------------------
# 2 · Input del MEC (prima registrada)
# ----------------------------------------------------------------------------
def input_mec():
    path = _buscar(["Input_MEC_Devengamiento*.xlsx"], que="Input_MEC_Devengamiento.xlsx")
    hdr = _fila_encabezado(path, "Input", "Fuente")
    inp = pd.read_excel(path, sheet_name="Input", header=hdr)
    inp.columns = [str(c).strip() for c in inp.columns]
    # compatibilidad con inputs anteriores (Anio): se homologa a la grafía nueva (Año)
    inp = inp.rename(columns={"CohorteAnio": "CohorteAño", "AnioSusc": "AñoSusc"})
    bd = inp[inp["Fuente"] == "BD"].copy()
    bd.to_csv(os.path.join(INS, "input_mec_bd.csv"), index=False)
    print(f"[insumos]   input_mec_bd.csv · {len(bd):,} filas · periodos {bd['Periodo'].min()}–{bd['Periodo'].max()} "
          f"· prima {bd['PrimaDevMes'].sum():,.0f}")


# ----------------------------------------------------------------------------
# 3 · Vectores PF+ (curva de prorrata de cartera y por ramo)
# ----------------------------------------------------------------------------
def vectores_pf():
    path = _buscar(["Registros_Vigencia_MEC.csv"], que="Registros_Vigencia_MEC.csv")
    try:
        import mec_devengamiento as mec
    except ModuleNotFoundError:
        raise SystemExit("[insumos] Falta mec_devengamiento.py en esta carpeta (lo necesito para la curva PF+).")
    cfg = mec.ConfigMEC(); cfg.HORIZONTE = HORIZONTE_PF
    df = mec.m1_cargar_registros(path, cfg)
    vec, cart, _ = mec.m2_fnd_prorrata(df, cfg)
    rows = {"CARTERA": cart}; rows.update(vec)
    V = pd.DataFrame(rows).T
    V.columns = [f"k{k}" for k in range(cfg.HORIZONTE)]
    V.to_csv(os.path.join(INS, "mec_vectores_h72.csv"))
    print(f"[insumos]   mec_vectores_h72.csv · {len(df):,} vigencias · {len(vec)} ramos · cartera k0={cart[0]:.4f}")


# ----------------------------------------------------------------------------
# 4 · ER real (opcional): % cedido por ramo y año
# ----------------------------------------------------------------------------
def er_real():
    destino = os.path.join(INS, "er_real_primas.csv")
    path = _buscar(["Integraci*n*.xlsb", "*Integracio*n*.xlsb"], obligatorio=False, que="Integración Dim (xlsb)")
    if path is None:
        if os.path.exists(destino) or os.path.exists(os.path.join(BASE, "er_real_primas.csv")):
            if not os.path.exists(destino):
                import shutil; shutil.copy(os.path.join(BASE, "er_real_primas.csv"), destino)
            print("[insumos]   er_real_primas.csv · sin xlsb de Integración; conservo el CSV existente")
            return
        raise SystemExit("[insumos] No hay Integración*.xlsb ni er_real_primas.csv; necesito uno de los dos.")
    try:
        from pyxlsb import open_workbook
    except ModuleNotFoundError:
        if os.path.exists(destino):
            print("[insumos]   er_real_primas.csv · falta pyxlsb (pip install pyxlsb); conservo el CSV existente")
            return
        raise SystemExit("[insumos] Falta pyxlsb para leer el xlsb:  pip install pyxlsb")
    filas = []
    with open_workbook(path) as wb:
        with wb.get_sheet("ER1225_Real") as sh:
            for row in sh.rows():
                filas.append([c.v for c in row])
    raw = pd.DataFrame(filas)
    bloques = []
    for i, v in raw[1].items():
        try:
            f = float(v)
            if 200000 < f < 210000:
                bloques.append((i, int(f)))
        except (TypeError, ValueError):
            pass
    keep = ['PRIMA EMITIDA', '(-) PRIMA CEDIDA / RETROCEDIDA', 'PRIMA RETENIDA', 'PRIMA DEVENGADA',
            'PRIMA CEDIDA DEVENGADA', 'PRIMA A RETENCIÓN DEVENGADA']
    out, cols = [], None
    for (i, per) in bloques:
        cols = [str(c).strip() for c in raw.iloc[i + 2, 2:17].tolist()]
        for j in range(i + 3, min(i + 62, len(raw))):
            lab = str(raw.iloc[j, 1]).strip()
            if lab in keep:
                out.append([per, lab] + pd.to_numeric(raw.iloc[j, 2:17], errors="coerce").tolist())
    er = pd.DataFrame(out, columns=["Periodo", "Concepto"] + cols)
    er.to_csv(destino, index=False)
    print(f"[insumos]   er_real_primas.csv · bloques {[int(x) for x in sorted(er['Periodo'].unique())]}")


if __name__ == "__main__":
    t1 = base_bel_irr_mr()
    input_mec()
    vectores_pf()
    er_real()
    print(f"\n[insumos] Listo. Último mes con RRC real: {t1}. Ahora corre:  python validar_prima_devengada.py")
