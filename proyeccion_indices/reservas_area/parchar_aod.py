# -*- coding: utf-8 -*-
"""Cambia lo minimo de los scripts del area ReforecastRRC_aod.py y ReforecastSONR_aod.py para que lean nuestros
indices de la BD proyectada (BD_ BEL - IRR - MR_Proyeccion.xlsx) con insumos_bd.py.

Uso: python parchar_aod.py <ReforecastRRC_aod.py> <ReforecastSONR_aod.py> [carpeta de salida]

Escribe <nombre>_BD.py junto a cada original (o en la carpeta de salida). Cada cambio queda marcado con
"### INDICES BD". Que cambia:

RRC  - IS Bel Media-m e IS Bel 99.5%-m: de la BD (HParametros Real hasta el ultimo mes real y Proyección despues; en
       los ramos de RAMOS_IS_FA, el IS de FA en los meses proyectados).
     - Ind. Gasto: el FACTOR GTO de la BD del mes que se valua (antes un valor fijo por ramo).
     - IS_Cat (71 y 73): el Ind Sin RRC de TEV e Hidro de la BD en los meses que la BD trae.
     - MR: PND del contrato x FACTOR MR de la BD (MR_DESDE_BD = True); sin FACTOR MR en la BD, la formula de capital.
SONR - Ind Sin SONR Media y 99.5%, LAG 1 a 10 y Factor_Ret: de la BD (IS de FA en RAMOS_IS_FA en los meses
       proyectados); MR: Prima Dev x (1 - LAG) x Factor_MR de la BD, y sin Factor_MR la formula del script.
Donde la BD no trae un dato se queda el valor de la tabla del area. Catalogos, contratos, FND calibrado, cesion,
duracion, retencion, tipo de cambio, escenario base y rutas no cambian. Al final cada script escribe
Parametros_usados_<reserva>.xlsx (las tablas que uso, de donde salio cada celda y los avisos) junto a su salida.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MARCA = "### INDICES BD"


def _bloque_inicio(reserva: str) -> str:
    que = ("IS (media y 99.5 %), Ind. Gasto, IS_Cat (71 y 73) y FACTOR MR" if reserva == "RRC"
           else "IS SONR (media y 99.5 %), LAG 1 a 10, Factor_Ret y Factor_MR")
    extra = ("" if reserva == "RRC" else
             "RAMOS_FACTOR_RET_AREA = ()   # ramos cuyo Factor_Ret se toma del ParamSONR del area y no de la BD, p. ej. (31,)\n")
    mr = ("MR = PND del contrato x FACTOR MR de la BD" if reserva == "RRC"
          else "MR = Prima Dev x (1 - LAG) x Factor_MR de la BD")
    imports = "" if reserva == "RRC" else "import os\nimport sys\n"
    return f'''
#%% INDICES DE LA BD PROYECTADA                              {MARCA}
# {que} salen de nuestra BD proyectada con
# insumos_bd.py: HParametros (Real hasta el ultimo mes real, Proyección despues) y, en los ramos de RAMOS_IS_FA, el IS
# de FA en los meses proyectados. Donde la BD no trae un dato se queda el de la tabla del area. Lo demas (catalogos,
# contratos, FND, cesion, duracion, retencion, TC, escenario base y rutas) se queda como estaba.
{imports}from pathlib import Path
CARPETA_INDICES = fr"C:\\Users\\{{usuario}}\\Documents\\Proyección Indices"   # insumos_bd.py y salidas\\ con la BD
_AQUI = str(Path(__file__).resolve().parent) if "__file__" in globals() else os.getcwd()
for _c in (_AQUI, CARPETA_INDICES):          # (gana el insumos_bd.py de CARPETA_INDICES)
    if _c not in sys.path:
        sys.path.insert(0, _c)
import insumos_bd
if not hasattr(getattr(insumos_bd, "InsumosBD", None), "param_sonr_area"):
    raise SystemExit(f"{{insumos_bd.__file__}} es una version anterior: copia el insumos_bd.py nuevo en {{CARPETA_INDICES}}")
from insumos_bd import InsumosBD, buscar_bd
RAMOS_IS_FA = {{"RRC": (40, 50, 80, 90), "SONR": (40, 50, 80, 90)}}   # siniestralidad de FA en los meses proyectados
MR_DESDE_BD = True     # True: {mr} (sin factor, la formula del area); False: la formula del area
{extra}INS = InsumosBD(buscar_bd(None, [CARPETA_INDICES, _AQUI]), ramos_is_fa=RAMOS_IS_FA)
'''


def _aviso_tc(sangria: str = "    ") -> str:
    return (f"{sangria}if not (pd.to_numeric(ConsultaTC['cTCAD_FecAMD'], errors='coerce') == Meses).any():   {MARCA}: aviso\n"
            f"{sangria}    print(f'   AVISO: la base Access no trae tipo de cambio de {{Meses}}: los montos de ese mes salen vacios')\n")


def _final(reserva: str, tablas: str) -> str:
    return f'''
try:                                                          {MARCA}: tablas que se usaron y avisos
    INS.exportar_tablas(f"{{xFolder}}\\\\Parametros_usados_{reserva}.xlsx", {tablas})
except PermissionError:
    print(f'   AVISO: no se pudo escribir Parametros_usados_{reserva}.xlsx (esta abierto en Excel)')
for _a in INS.avisos_texto():
    print('   AVISO:', _a)
'''


def _rep(texto: str, patron: str, nuevo, n: int = 1, flags: int = re.M) -> str:
    texto2, k = re.subn(patron, nuevo, texto, flags=flags)
    if k != n:
        raise SystemExit(f"No se encontro (o se encontro {k} veces, se esperaban {n}): {patron[:90]}")
    return texto2


def _en_seccion(texto: str, inicio: str, fin: str, patron: str, nuevo, n: int = 1) -> str:
    i = texto.index(inicio)
    j = texto.index(fin, i)
    return texto[:i] + _rep(texto[i:j], patron, nuevo, n) + texto[j:]


def parchar_rrc(t: str) -> str:
    t = _rep(t, r"\A(.*\n)", r"\1# Version con los indices de la BD proyectada: cambios marcados con " + MARCA + "\n")
    t = _rep(t, r"^(start_time = time\.perf_counter\(\)\n)", lambda m: m.group(1) + _bloque_inicio("RRC"))
    t = _rep(t, r"^(Nomeses = .*\n)", lambda m: m.group(1) + (
        f"_xRRC_area, _xIS_CAT_area = xRRC, xIS_CAT                    {MARCA}: las tablas del area solo dan lo\n"
        "xRRC = INS.parametros_rrc_area(zAño, _xRRC_area)             # que la BD no trae (duracion, retencion, huecos)\n"
        "xIS_CAT = INS.is_cat_area(_xIS_CAT_area)\n"))
    ini, fin = "def ConsultaReal(IS,IS_CAT, MES):", "#%% FUNCION RRC MENSUALIZADOS"
    t = _en_seccion(t, ini, fin, r'("Resto Monedas_ret", "Ind\. Gasto", )(f"IS Bel Media-\{MES\}")', r'\1"FACTOR MR", \2')
    t = _en_seccion(t, ini, fin, r'^([ \t]*f"IS Bel 99\.5%-\{MES\}":"BEL99",\n)',
                    lambda m: m.group(1) + m.group(1).split('f"')[0] + f'"FACTOR MR":"FACTORMR",   {MARCA}\n')
    for col, tc in (("TCVal", "TC_Valuación"), ("TCAñoAnt", "TC_CierreAnterior")):
        t = _en_seccion(t, ini, fin, r"^([ \t]*ConsultaR\['MR\d{4}_" + col + r"'\] = ConsultaR\.apply\(lambda row: )(.*)(, axis = 1\))[ \t]*$",
                        lambda m, tc=tc: (f"{m.group(1)}row['MONTO_PI']*row['PORC_ND']*row['FACTORMR']*row['{tc}'] "
                                          f"if MR_DESDE_BD and row['FACTORMR'] > 0 else {m.group(2)}{m.group(3)}   {MARCA}"))
    t = _rep(t, r"^([ \t]*)(df_Real_IS_Real = ConsultaReal\(xRRC,\s*xIS_CAT,\s*mes_calculo\)\n)",
             lambda m: (f"{m.group(1)}xRRC['Ind. Gasto'] = xRRC[f'Ind. Gasto-{{mes_calculo}}']       {MARCA}: gasto y FACTOR MR\n"
                        f"{m.group(1)}xRRC['FACTOR MR'] = xRRC[f'FACTOR MR-{{mes_calculo}}']         # del mes que se valua\n"
                        + _aviso_tc(m.group(1)) + m.group(1) + m.group(2)))
    t = _rep(t, r"^(xRRC_saldos\.to_excel\(fileName, index=False\)\n)",
             lambda m: m.group(1) + _final("RRC", '{"ParametrosMens_RRC": xRRC, "IS_Cat": xIS_CAT}'))
    return t


def parchar_sonr(t: str) -> str:
    t = _rep(t, r"\A(.*\n)", r"\1# Version con los indices de la BD proyectada: cambios marcados con " + MARCA + "\n")
    t = _rep(t, r"^(warnings\.filterwarnings\('ignore'\)\n)", lambda m: m.group(1) + _bloque_inicio("SONR"))
    t = _rep(t, r"^(ParamSONR_inc = pd\.read_csv\(.*\)[ \t]*\n)", lambda m: m.group(1) + (
        f"_ParamSONR_area = ParamSONR                                   {MARCA}: el ParamSONR del area solo da\n"
        "ParamSONR = INS.param_sonr_area(_ParamSONR_area, RAMOS_FACTOR_RET_AREA)   # lo que la BD no trae\n"))
    t = _rep(t, r'^([ \t]*Tbase_mp_ = Tbase_mp_\.merge\(ParamSONR\[\["Llave","Factor_Ret",)', r'\1"Factor_MR",')
    t = _rep(t, r"^([ \t]*Tbase_mp_\['MR'\] = Tbase_mp_\.apply\(lambda row: )(\(row\['Desviacion'\] / -BC\) \* BC2)(, axis=1\))[ \t]*$",
             lambda m: (f"{m.group(1)}(row['Prima Dev'] * row['LAG'] * row['Factor_MR']) if MR_DESDE_BD and "
                        f"row['Factor_MR'] > 0 else {m.group(2)}{m.group(3)}   {MARCA}"))
    t = _rep(t, r"^([ \t]*)(ConsultaR = ConsultaReal\(mes_calculo, zFechaValuacion, Meses\)\n)",
             lambda m: _aviso_tc(m.group(1)) + m.group(1) + m.group(2))
    t = _rep(t, r"^(df_concatenado\.to_excel\(fileName, index=False\))\s*\Z",
             lambda m: m.group(1) + "\n" + _final("SONR", '{"ParamSONR": ParamSONR}'))
    return t


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    salida = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    for ruta, fn in ((Path(sys.argv[1]), parchar_rrc), (Path(sys.argv[2]), parchar_sonr)):
        crudo = ruta.read_bytes()
        bom = crudo.startswith(b"\xef\xbb\xbf")
        fin_linea = "\r\n" if b"\r\n" in crudo else "\n"   # se respeta el fin de linea del original (CRLF de Windows)
        texto = crudo.decode("utf-8-sig").replace("\r\n", "\n")
        if MARCA in texto:
            raise SystemExit(f"{ruta.name} ya trae cambios {MARCA}: usa el original del area")
        nuevo = fn(texto)
        compile(nuevo, ruta.name, "exec")
        destino = (salida or ruta.parent) / f"{ruta.stem}_BD.py"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(((b"\xef\xbb\xbf" if bom else b"") + nuevo.replace("\n", fin_linea).encode("utf-8")))
        print(f"{destino}: {nuevo.count(MARCA)} cambios marcados")


if __name__ == "__main__":
    main()
