# -*- coding: utf-8 -*-
"""
sirec_conexion.py  (versión 1.1)  --  SE EJECUTA POR DEFECTO
==========================================================================
Criterio SIREC de la redistribución Terremoto (71) / HyORH (73):
  Los negocios marcados VALIDAR_SIREC en la trazabilidad (facultativos y contratos nulos: la LLAVE agrupa varios
  contratos) se ajustan con el peso del grupo. Este módulo trae de SIREC los movimientos reales por contrato
  (prima, comisión y siniestro del reaseguro tomado) para cotejar ese peso contrato por contrato.

Estado: la conexión y la lectura robusta están adaptadas del script Ident_RetroEsp_Prop_aod.py del equipo. Las columnas de
aMOV_Mov que dan el SUBRAMO y el MES CONTABLE no se pudieron confirmar con los scripts disponibles; están en COLUMNAS_POR_CONFIRMAR.
Mientras no se confirmen, la consulta se arma sin ellas (sólo totales por contrato) y el resultado no permite separar
Terremoto de HyORH; da los totales por contrato para cotejar los negocios VALIDAR_SIREC.

Se ejecuta por defecto: corrido solo y también al final de 0_Redistribucion_TEV_HyOR.py (si falla ahí, sólo deja un aviso;
la base redistribuida ya quedó escrita).

Credenciales: archivo local sirec_config.py junto a este script (no se sube al repositorio); las variables de entorno
SIREC_USUARIO / SIREC_CLAVE prevalecen; si no hay ninguna, se piden en pantalla.

Uso:
  python sirec_conexion.py                 -> se conecta y deja Outputs\\SIREC\\SIREC_Validacion_{fecha}.xlsx
  python sirec_conexion.py --no-ejecutar   -> sólo muestra la consulta (no se conecta)
"""
import argparse
import getpass
import glob
import os
import sys
import time
from datetime import datetime

import pandas as pd

_aqui = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _aqui)
try:
    import sirec_config as _cfg  # credenciales locales
except ImportError:
    _cfg = None
SERVIDOR = os.environ.get("SIREC_SERVIDOR") or getattr(_cfg, "SERVIDOR", "adsPeru05")
BASE_DATOS = os.environ.get("SIREC_BASE") or getattr(_cfg, "BASE_DATOS", "pDBSirec2")
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

def armar_sql(anio_desde=ANIO_DESDE):
    c = COLUMNAS
    extra = [v for v in COLUMNAS_POR_CONFIRMAR.values() if v]
    dims = [c["corredor"], c["cedente"], c["contrato"], c["anio_origen"]] + extra
    sumas = ", ".join(f"sum(case when {c['cuenta']} in ({k}) then {c['monto_nacional']} else 0 end) as {v}" for k, v in CUENTAS.items())
    return (f"SELECT {', '.join(dims)}, {sumas} FROM {BASE_DATOS}.dbo.aMOV_Mov "
            f"WHERE {c['anio_origen']} >= {int(anio_desde)} GROUP BY {', '.join(dims)}")


def cadena_conexion():
    import pyodbc  # sólo al ejecutar
    usuario = os.environ.get("SIREC_USUARIO") or getattr(_cfg, "USUARIO", None) or input("Usuario SIREC: ")
    clave = os.environ.get("SIREC_CLAVE") or getattr(_cfg, "CLAVE", None) or getpass.getpass("Clave SIREC: ")
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


def llaves_a_validar(base=_aqui):
    """LLAVEs con VALIDAR_SIREC de la trazabilidad más reciente de la redistribución."""
    trz = sorted(glob.glob(os.path.join(base, "Outputs", "Redistribucion_TEV_HyOR", "Trazabilidad_Redistribucion_TEV_HyOR_*.xlsx")), key=os.path.getmtime)
    if not trz:
        return pd.DataFrame()
    t = pd.read_excel(trz[-1], sheet_name="Validar_SIREC")
    print(f"LLAVEs a validar ({len(t)}) tomadas de {trz[-1]}")
    return t


def ejecutar(base=_aqui, anio_desde=ANIO_DESDE, conectar=True):
    """Corre la consulta a SIREC y deja Outputs\\SIREC\\SIREC_Validacion_{fecha}.xlsx. Devuelve la ruta (o '' si no se conectó)."""
    sql = armar_sql(anio_desde)
    faltan = [k for k, v in COLUMNAS_POR_CONFIRMAR.items() if not v]
    print("Consulta SIREC:\n" + sql)
    if faltan:
        print(f"AVISO: faltan por confirmar las columnas {faltan} de aMOV_Mov; el resultado da totales por contrato sin separar Terremoto de HyORH.")
    if not conectar:
        print("No se ejecutó (--no-ejecutar). Nada se conectó.")
        return ""
    cs = cadena_conexion()
    mov = leer_sql(sql, cs, "Movimientos reaseguro tomado")
    c = COLUMNAS
    # Equivalencia supuesta con la LLAVE del presupuesto (CONFIRMAR): ZCEDENTE = cCIA_IdOrig, ZCONTRATO = aMOV_IdentContrOrig,
    # ZCORREDOR = cCOR_IdOrig, ZSUSCYEAR = aMOV_AñoOrig.
    mov["CEDENTE_CONTRATO"] = mov[c["cedente"]].astype("Int64").astype(str) + "-" + mov[c["contrato"]].astype("Int64").astype(str)
    val = llaves_a_validar(base)
    if len(val):
        val["CEDENTE_CONTRATO"] = val["ZCEDENTE"].astype(str) + "-" + val["ZCONTRATO"].astype(str)
    out_dir = os.path.join(base, "Outputs", "SIREC"); os.makedirs(out_dir, exist_ok=True)
    destino = os.path.join(out_dir, f"SIREC_Validacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    with pd.ExcelWriter(destino, engine="openpyxl") as w:
        mov.to_excel(w, sheet_name="Movimientos", index=False)
        if len(val):
            val.to_excel(w, sheet_name="LLAVEs_Validar", index=False)
            mov[mov["CEDENTE_CONTRATO"].isin(set(val["CEDENTE_CONTRATO"]))].to_excel(w, sheet_name="Movimientos_LLAVEs", index=False)
        pd.DataFrame({"NOTA": ["Columnas por confirmar: " + str(faltan), "SQL: " + sql]}).to_excel(w, sheet_name="Notas", index=False)
    print(f"Resultado SIREC: {destino}")
    return destino


def main():
    ap = argparse.ArgumentParser(description="Consulta a SIREC para validar contrato por contrato los negocios VALIDAR_SIREC")
    ap.add_argument("--no-ejecutar", action="store_true", help="sólo mostrar la consulta, sin conectarse")
    ap.add_argument("--anio-desde", type=int, default=ANIO_DESDE)
    a = ap.parse_args()
    ejecutar(_aqui, a.anio_desde, conectar=not a.no_ejecutar)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
