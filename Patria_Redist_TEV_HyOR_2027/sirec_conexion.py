# -*- coding: utf-8 -*-
"""
sirec_conexion.py  (versión 1.0)  --  PREPARADO, NO SE EJECUTA POR DEFECTO
==========================================================================
Criterio SIREC de la redistribución Terremoto (71) / HyORH (73):
  Los negocios marcados VALIDAR_SIREC en la trazabilidad (facultativos y contratos nulos: la LLAVE agrupa varios
  contratos) se ajustan con el peso del grupo. Este módulo trae de SIREC los movimientos reales por contrato
  (prima, comisión y siniestro del reaseguro tomado) para cotejar ese peso contrato por contrato.

Estado: la conexión y la lectura robusta están adaptadas del script Ident_RetroEsp_Prop_aod.py del equipo. Las columnas de
aMOV_Mov que dan el SUBRAMO y el MES CONTABLE no se pudieron confirmar con los scripts disponibles; están en COLUMNAS_POR_CONFIRMAR.
Mientras no se confirmen, la consulta se arma sin ellas (sólo totales por contrato) y el resultado no permite separar
Terremoto de HyORH. Por eso este módulo NO se llama desde los otros scripts y, corrido solo, no se conecta salvo con --ejecutar.

Credenciales: NUNCA en el código. Variables de entorno SIREC_USUARIO y SIREC_CLAVE (si faltan, se piden en pantalla sin
mostrarlas). Nota: el script de ejemplo tiene usuario y contraseña escritos en texto plano; conviene retirarlos de ahí.

Uso:
  python sirec_conexion.py                 -> sólo muestra la consulta que correría (no se conecta)
  python sirec_conexion.py --ejecutar      -> se conecta y deja Outputs\\SIREC\\SIREC_Validacion_{fecha}.xlsx
"""
import argparse
import getpass
import glob
import os
import sys
import time
from datetime import datetime

import pandas as pd

SERVIDOR = os.environ.get("SIREC_SERVIDOR", "adsPeru05")
BASE_DATOS = os.environ.get("SIREC_BASE", "pDBSirec2")
ANIO_DESDE = 2023

# Columnas de aMOV_Mov confirmadas en el script de ejemplo
COLUMNAS = {"corredor": "cCOR_IdOrig", "cedente": "cCIA_IdOrig", "contrato": "aMOV_IdentContrOrig", "anio_origen": "aMOV_AñoOrig",
            "cuenta": "cCTA_IdCta", "monto_nacional": "aMOV_MntNal", "moneda": "cMON_IdOrig", "poliza": "aPOG_Num"}
# Columnas POR CONFIRMAR con el equipo de SIREC (None = no se usan). Sin el subramo no se puede separar Terremoto de HyORH.
COLUMNAS_POR_CONFIRMAR = {"subramo": None,   # p.ej. "cSBR_IdOrig"   <- CONFIRMAR
                          "mes_contable": None}  # p.ej. "aPOG_MesProc" <- CONFIRMAR (AAAAMM)
# Cuentas del reaseguro tomado (catálogo del script de ejemplo)
CUENTAS = {318: "PRIMAS_DEL_REASEGURO_TOMADO", 249: "COMISIONES_POR_REASEGURO_Y_REAFIANZAMIENTO_TOMADO",
           254: "SINIESTROS_DEL_REASEGURO_Y_RECLAMACIONES_DE_REAFIANZAMIENTO"}

_aqui = os.path.dirname(os.path.abspath(__file__))


def armar_sql(anio_desde=ANIO_DESDE):
    c = COLUMNAS
    extra = [v for v in COLUMNAS_POR_CONFIRMAR.values() if v]
    dims = [c["corredor"], c["cedente"], c["contrato"], c["anio_origen"]] + extra
    sumas = ", ".join(f"sum(case when {c['cuenta']} in ({k}) then {c['monto_nacional']} else 0 end) as {v}" for k, v in CUENTAS.items())
    return (f"SELECT {', '.join(dims)}, {sumas} FROM {BASE_DATOS}.dbo.aMOV_Mov "
            f"WHERE {c['anio_origen']} >= {int(anio_desde)} GROUP BY {', '.join(dims)}")


def cadena_conexion():
    import pyodbc  # sólo al ejecutar
    usuario = os.environ.get("SIREC_USUARIO") or input("Usuario SIREC: ")
    clave = os.environ.get("SIREC_CLAVE") or getpass.getpass("Clave SIREC: ")
    instalados = [d.strip() for d in pyodbc.drivers()]
    driver = next((d for d in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
                               "SQL Server Native Client 11.0", "SQL Server"] if d in instalados), "SQL Server")
    cs = f"DRIVER={{{driver}}};SERVER={SERVIDOR};DATABASE={BASE_DATOS};UID={usuario};PWD={clave}"
    if driver.startswith("ODBC Driver 18"):
        cs += ";Encrypt=no;TrustServerCertificate=yes"
    print(f"Driver ODBC en uso: {driver}")
    return cs


def leer_sql(sql, cs, etiqueta="consulta", intentos=3, espera=10, chunksize=50000):
    """Lectura robusta (reintentos, reconexión y lectura por bloques), como en el script de ejemplo."""
    import pyodbc
    ultimo = None
    for i in range(1, intentos + 1):
        conn = None
        try:
            t0 = time.perf_counter()
            conn = pyodbc.connect(cs)
            partes = list(pd.read_sql(sql, conn, chunksize=chunksize))
            conn.close()
            df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
            print(f"  [{etiqueta}] OK: {len(df):,} filas en {time.perf_counter() - t0:,.1f} s")
            return df
        except Exception as e:  # noqa: BLE001 - se reintenta cualquier error de red/servidor
            ultimo = e
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            if i < intentos:
                print(f"  [{etiqueta}] intento {i}/{intentos} falló ({type(e).__name__}); reintento en {espera}s")
                time.sleep(espera)
    raise ultimo


def llaves_a_validar():
    """LLAVEs con VALIDAR_SIREC de la trazabilidad más reciente de la redistribución."""
    trz = sorted(glob.glob(os.path.join(_aqui, "Outputs", "Redistribucion_TEV_HyOR", "Trazabilidad_Redistribucion_TEV_HyOR_*.xlsx")), key=os.path.getmtime)
    if not trz:
        return pd.DataFrame()
    t = pd.read_excel(trz[-1], sheet_name="Validar_SIREC")
    print(f"LLAVEs a validar ({len(t)}) tomadas de {trz[-1]}")
    return t


def main():
    ap = argparse.ArgumentParser(description="Consulta a SIREC para validar contrato por contrato los negocios VALIDAR_SIREC (no se conecta sin --ejecutar)")
    ap.add_argument("--ejecutar", action="store_true", help="conectarse a SIREC y correr la consulta")
    ap.add_argument("--anio-desde", type=int, default=ANIO_DESDE)
    a = ap.parse_args()
    sql = armar_sql(a.anio_desde)
    faltan = [k for k, v in COLUMNAS_POR_CONFIRMAR.items() if not v]
    print("Consulta que se correría en SIREC:\n" + sql)
    if faltan:
        print(f"\nAVISO: faltan por confirmar las columnas {faltan} de aMOV_Mov. Sin el subramo, el resultado da totales por contrato "
              "pero no separa Terremoto de HyORH.")
    if not a.ejecutar:
        print("\nNo se ejecutó (falta --ejecutar). Nada se conectó.")
        return
    cs = cadena_conexion()
    mov = leer_sql(sql, cs, "Movimientos reaseguro tomado")
    c = COLUMNAS
    # Equivalencia supuesta con la LLAVE del presupuesto (CONFIRMAR): ZCEDENTE = cCIA_IdOrig, ZCONTRATO = aMOV_IdentContrOrig,
    # ZCORREDOR = cCOR_IdOrig, ZSUSCYEAR = aMOV_AñoOrig.
    mov["CEDENTE_CONTRATO"] = mov[c["cedente"]].astype("Int64").astype(str) + "-" + mov[c["contrato"]].astype("Int64").astype(str)
    val = llaves_a_validar()
    if len(val):
        val["CEDENTE_CONTRATO"] = val["ZCEDENTE"].astype(str) + "-" + val["ZCONTRATO"].astype(str)
    out_dir = os.path.join(_aqui, "Outputs", "SIREC"); os.makedirs(out_dir, exist_ok=True)
    destino = os.path.join(out_dir, f"SIREC_Validacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    with pd.ExcelWriter(destino, engine="openpyxl") as w:
        mov.to_excel(w, sheet_name="Movimientos", index=False)
        if len(val):
            val.to_excel(w, sheet_name="LLAVEs_Validar", index=False)
            mov[mov["CEDENTE_CONTRATO"].isin(set(val["CEDENTE_CONTRATO"]))].to_excel(w, sheet_name="Movimientos_LLAVEs", index=False)
        pd.DataFrame({"NOTA": ["Columnas por confirmar: " + str(faltan), "SQL: " + sql]}).to_excel(w, sheet_name="Notas", index=False)
    print(f"Resultado: {destino}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
