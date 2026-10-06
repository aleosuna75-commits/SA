# -*- coding: utf-8 -*-
"""Versiones 2027 de los scripts del area: ReforecastRRC_aod_2027.py y ReforecastSONR_aod_2027.py.

Uso: python parchar_aod_2027.py <ReforecastRRC_aod.py> <ReforecastSONR_aod.py> [carpeta de salida]

Parte de los mismos cambios de parchar_aod.py (indices, FND y TC de la BD, marcados con "### INDICES BD") y agrega lo
necesario para valuar 2027 sin la base de valuacion Access (marcado con "### 2027"):
  - zAño = 2027; el diccionario xAños (mes - k -> AAAAMM) se arma con el ano; la fecha de valuacion del RRC y la consulta
    de monedas del SONR ya no traen 2026 fijo; las columnas BELRIESGO2026, MR2026, ... se llaman 2027.
  - Sin SQL: los contratos son la prima tomada de la BD por ramo y mes (hoja PE_RAMO: real de PExRamo hasta el ultimo mes
    real y FCST despues), uno por ramo y mes, en dolares, con 12 meses de vigencia y la cesion del bloque CESION del RRC;
    el tipo de cambio sale de la columna TC de la BD (dolar) y el peso en 1. El resto del metodo del area (FND por
    antiguedad escalado a nuestro FND, IS, LAG, MR, escenarios) no cambia.
  - Escenarios 0 y 1: del Escenario_base del area se quedan diciembre del ano anterior y el presupuesto del ano; si no trae
    el escenario 0, sale de los montos de la BD de diciembre 2026.
  - Lo que falte de 2027 en los archivos del area sale de los de 2026, solo como previo: en ParamSONR el mismo mes de 2026
    (ParametrosMens no trae ano: sus columnas por mes ya son las de 2026) y, con PREVIO_CON_2026 = True, el presupuesto
    2026 con los meses de 2027 en el escenario 1 (False: sin escenario 1).
  - RRC: la cesion de los contratos es el IRR / BEL de la BD del mes que se valua (el script hace IRR = BEL x cesion y la
    BD IRR = BRUTO x CESION), asi BEL, IRR y NETO son los de la BD. SONR_NIVEL_BD = True: el BEL del SONR de cada ramo y mes
    se lleva al de la BD (con un contrato por ramo y mes el metodo propio pone toda la prima en la ventana del ano en que se
    registra); el IRR y el MR siguen al BEL.
  - TC_DESDE_BD se queda en True (sin la base el TC solo sale de la BD). Todos los contratos van en dolares: el escenario
    5 (TC del cierre anterior) revalua toda la cartera.
  - Las salidas llevan _2027 en el nombre (RRC_esc_2027.xlsx, SONR_esc_2027.xlsx, Parametros_usados_RRC_2027.xlsx, ...).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parchar_aod import MARCA, _en_seccion, _rep, parchar_rrc, parchar_sonr   # noqa: E402

M27 = "### 2027"
ANIO = 2027


def _sin_conexion(t: str, inicio: str, fin: str, lectura: str, nuevo: str) -> str:
    """En la funcion entre inicio y fin: la conexion a Access se comenta y la lectura SQL se cambia por la de la BD."""
    i = t.index(inicio)
    j = t.index(fin, i)
    s = t[i:j]
    s = _rep(s, r"^([ \t]*)(conn = pyodbc\.connect\(conn_str\)[ \t]*\n)", lambda m: f"{m.group(1)}# {m.group(2).rstrip()}   {M27}: sin la base Access\n")
    s = _rep(s, r"^([ \t]*)(cursor = conn\.cursor\(\)[ \t]*\n)", lambda m: f"{m.group(1)}# {m.group(2)}")
    s = _rep(s, r"^([ \t]*)(conn\.close\(\)[ \t]*\n)", lambda m: f"{m.group(1)}# {m.group(2)}")
    s = _rep(s, r"^([ \t]*)" + re.escape(lectura) + r"[ \t]*\n", lambda m: f"{m.group(1)}{nuevo}   {M27}\n")
    return t[:i] + s + t[j:]


def _comunes(t: str, reserva: str) -> str:
    t = _rep(t, r"\A(.*\n)(.*\n)", lambda m: m.group(1) + m.group(2) + (
        f"# Version 2027 sin la base de valuacion Access: los contratos son la prima de la BD por ramo y mes (hoja PE_RAMO)\n"
        f"# y el tipo de cambio el de la BD; cambios para 2027 marcados con {M27}. Las salidas llevan _2027.\n"
        f"PREVIO_CON_2026 = True   {M27}: si el Escenario_base del area no trae presupuesto 2027, va el de 2026 con los\n"
        "                         # meses de 2027, solo como previo; False: el escenario 1 no se incluye. Los parametros que\n"
        "                         # falten de 2027 (ParamSONR) salen del mismo mes de los archivos de 2026, tambien como previo\n"))
    t = _rep(t, r"^TC_DESDE_BD = True[^\n]*\n[ \t]*#[^\n]*\n", lambda m: (
        f"TC_DESDE_BD = True     {M27}: sin la base Access el TC MXN / USD solo sale de la BD (TC_Real_Esti: M en 2027,\n"
        "                       # J en diciembre 2026) y el peso en 1; en esta version se queda en True\n"
        f"if not TC_DESDE_BD:                                       {M27}\n"
        "    raise SystemExit('Sin la base Access el tipo de cambio solo sale de la BD: deja TC_DESDE_BD = True')\n"))
    t = _rep(t, r"^import pyodbc[ \t]*\n", f"try:                                   {M27}: no se usa (sin la base Access)\n"
                                            "    import pyodbc\nexcept ImportError:\n    pyodbc = None\n")
    # diccionario mes - k -> AAAAMM armado con el ano que se valua
    t = _rep(t, r"^([ \t]*)xAños =[ \t]*\{[^}]*\}[ \t]*\n",
             lambda m: (f"{m.group(1)}xAños = {{**{{zAño * 100 + k: zAño * 100 + k for k in range(1, 13)}},   {M27}: del ano\n"
                        f"{m.group(1)}         **{{zAño * 100 - k: (zAño - 1) * 100 + 12 - k for k in range(12)}}}}   # que se valua\n"))
    # columnas con el ano en el nombre (BELRIESGO2026_TCVal, MR2026, PMADEV_2026, BC_SONR_2026, ...): 2027
    lineas = []
    for linea in t.split("\n"):
        if (not linea.lstrip().startswith("#") and "read_csv" not in linea and "xFolder" not in linea
                and "VERSION_AOD" not in linea and M27 not in linea):
            linea = re.sub(r"(?<=[A-Za-zÑñ_])2026(?![0-9])", str(ANIO), linea)
        lineas.append(linea)
    t = "\n".join(lineas)
    # salidas con _2027
    patron = r'^([ \t]*fileName = f"[^"\n]*?)\.xlsx"'
    t = _rep(t, patron, r'\1_2027.xlsx"', n=len(re.findall(patron, t, flags=re.M)))
    t = _rep(t, rf"Parametros_usados_{reserva}\.xlsx", f"Parametros_usados_{reserva}_2027.xlsx", n=2)
    # escenarios 0 y 1 del ano
    t = _rep(t, r"^(xEsc_base = xEsc_base\[columnas_finales\][ \t]*\n)", lambda m: m.group(1) + (
        f'xEsc_base = INS.escenario_base_area("{reserva}", xEsc_base, zAño, PREVIO_CON_2026)   {M27}: diciembre anterior\n'
        "              # y presupuesto del ano; sin escenario 0 del area, el de la BD; sin presupuesto del ano, el de 2026 (previo)\n"))
    # tipo de cambio de la BD (sin la base)
    t = _sin_conexion(t, "def ConsultaMoneda_usd():", "TC_USD = ConsultaMoneda_usd()",
                      "ConsultaTC_USD = pd.read_sql(xSQL, conn)", "ConsultaTC_USD = INS.tc_tabla()                  # TC USD de la BD")
    t = _sin_conexion(t, "def ConsultaMoneda():", "ConsultaTC = ConsultaMoneda()",
                      "ConsultaTC = pd.read_sql(xSQL, conn)", "ConsultaTC = INS.tc_monedas_bd()            # dolar de la BD y peso en 1")
    return t


def parchar_rrc_2027(t: str) -> str:
    t = parchar_rrc(t)
    t = _comunes(t, "RRC")
    t = _rep(t, r"^zAño = 2026[ \t]*$", f"zAño = {ANIO}                                   {M27}")
    t = _rep(t, r"(zFechaValuacion = f'\{dia\}/\{AuxMes\}\{mes_calculo\}/)2026'", r"\1{zAño}'")
    ini, fin = "def ConsultaReal(IS,IS_CAT, MES):", "#%% FUNCION RRC MENSUALIZADOS"
    t = _sin_conexion(t, ini, fin, "tMovGG = pd.read_sql(xSQL, conn)",
                      "tMovGG = INS.contratos_rrc_bd(AuxMesI, AuxMesF)   # contratos = prima de la BD por ramo y mes")
    # los contratos ya traen el ramo como clave del script: sin el catalogo de subramos
    t = _en_seccion(t, ini, fin, r'^([ \t]*)(ConsultaR = ConsultaR\.merge\(xRamo\[\["SR","Ramo"\]\]\.drop_duplicates\(\),[ \t]*\n)([^\n]*\n)',
                    lambda m: f"{m.group(1)}# {m.group(2)}{m.group(1)}# {m.group(3).lstrip()}".replace(
                        m.group(2).rstrip("\n"), m.group(2).rstrip("\n") + f"   {M27}: el ramo ya viene"))
    t = _en_seccion(t, ini, fin, r"^([ \t]*)(ConsultaR = ConsultaR\.drop\('SR', axis=1\)[ \t]*\n)",
                    lambda m: f"{m.group(1)}# {m.group(2)}")
    # sin pais ni region, la linea de negocio no es dato: no se reparte
    t = _en_seccion(t, ini, fin, r"^([ \t]*)(ConsultaR\['LN2'\] = ConsultaR\.apply\(lambda y: zLN\([^\n]*\n)",
                    lambda m: f"{m.group(1)}{m.group(2)}{m.group(1)}ConsultaR['LN2'] = 'Sin LN (prima de la BD por ramo)'"
                              f"   {M27}: sin pais ni region\n")
    t = _en_seccion(t, ini, fin, r"^([ \t]*)(ConsultaR\['Ramo'\] = ConsultaR\['Ramo'\]\.apply\(lambda x: xNoRamo\[x\]\)[ \t]*\n)",
                    lambda m: f"{m.group(1)}# {m.group(2)}")
    return t


def parchar_sonr_2027(t: str) -> str:
    t = parchar_sonr(t)
    t = _comunes(t, "SONR")
    t = _rep(t, r"^([ \t]*# falten de 2027 \(ParamSONR\)[^\n]*\n)", lambda m: m.group(1) + (
        f"SONR_NIVEL_BD = True     {M27}: el BEL de cada ramo y mes es el de la BD (FD SONR x PEACUMULADA x IS): con un\n"
        "                         # contrato por ramo y mes toda la prima cae en la ventana del ano en que se registra y el\n"
        "                         # metodo da un BEL mas alto; el IRR y el MR siguen al BEL. False: el metodo tal cual\n"))
    t = _en_seccion(t, "def Metodo_propio():", "#%% FUNCIÓN MÉTODO PROPIO REFORECAST",
                    r"^([ \t]*)(Tbase_mp_\['Prima Dev'\] = Tbase_mp_\.apply\(calcular_tbase_mp, args=\(ConsultaR,\), axis=1\)[ \t]*\n)",
                    lambda m: (f"{m.group(1)}{m.group(2)}{m.group(1)}if SONR_NIVEL_BD:                                         "
                               f"{M27}: BEL del mes = el de la BD\n"
                               f"{m.group(1)}    Tbase_mp_['Prima Dev'] = INS.nivel_sonr_bd(Tbase_mp_, Meses, TC_USD)\n"))
    t = _rep(t, r"^zAñoPpto = 2026[ \t]*$", f"zAñoPpto = {ANIO}                               {M27}")
    t = _rep(t, r"^zAño= 2026[ \t]*$", f"zAño= {ANIO}                                    {M27}")
    t = _en_seccion(t, "def ConsultaMoneda():", "ConsultaTC = ConsultaMoneda()", r"^([ \t]+)(zAño = 2026[ \t]*\n)",
                    lambda m: f"{m.group(1)}# {m.group(2).rstrip()}   {M27}: se usa el zAño del script\n")
    t = _sin_conexion(t, "def ConsultaReal(MES, FECVAL, AÑOMES):", "#%% FUNCIÓN CONSULTA PARA SONR REAL USD",
                      "tMovGG = pd.read_sql(xSQL, conn)",
                      "tMovGG = INS.contratos_sonr_bd(zInicio, zFin)   # contratos = prima de la BD por ramo y mes")
    return t


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    salida = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    for ruta, fn in ((Path(sys.argv[1]), parchar_rrc_2027), (Path(sys.argv[2]), parchar_sonr_2027)):
        crudo = ruta.read_bytes()
        bom = crudo.startswith(b"\xef\xbb\xbf")
        fin_linea = "\r\n" if b"\r\n" in crudo else "\n"
        texto = crudo.decode("utf-8-sig").replace("\r\n", "\n")
        if MARCA in texto or M27 in texto:
            raise SystemExit(f"{ruta.name} ya trae cambios: usa el original del area")
        nuevo = fn(texto)
        compile(nuevo, ruta.name, "exec")
        destino = (salida or ruta.parent) / f"{ruta.stem}_2027.py"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes((b"\xef\xbb\xbf" if bom else b"") + nuevo.replace("\n", fin_linea).encode("utf-8"))
        print(f"{destino}: {nuevo.count(MARCA)} cambios de indices y {nuevo.count(M27)} de 2027")


if __name__ == "__main__":
    main()
