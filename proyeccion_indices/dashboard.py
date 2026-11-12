# -*- coding: utf-8 -*-
"""
DASHBOARDS EN EXCEL: indices (HParametros) y reservas (RRC / SONR / RFV), real y proyectado.

Genera salidas/Dashboard_Indices_Reservas.xlsx a partir de las salidas de proyeccion_reservas.py:
  * "Dashboard Índices"  : selectores de ramo, indice/LAG y periodo; indicadores; evolucion mensual real vs
                           proyeccion con banda al 80%; comparativo por ramo; patron de desarrollo (LAGs);
                           resumen de los 4 indices del ramo.
  * "Dashboard Reservas" : selectores de reserva, concepto, ramo y moneda (USD/MXN con el TC de la BD);
                           indicadores; mensual 2025-2027; historico 2022-2027; por ramo; por concepto.
  * "Dashboard Razones"  : selectores de ramo (con "Todos") y reserva; indicadores; PND / PD, FACTOR GTO, FACTOR MR,
                           CESION, FD / FND, IS (RL), IS (FA), PE FCST, PRIMA N AÑOS y PEACUMULADA, real y proyeccion
                           (hoja Indicadores_Ramo del diagnostico: los valores de los bloques de la BD de Danos).
  * "Dashboard Razones RFV": selector de ramo (con "Todos"); indicadores; FRV, PRIMA 24M, CESION, FV, RC, PD, monto
                           afianzado y su parte de la RFV (real, proyeccion y una serie de referencia en gris) y los
                           factores constantes del ramo (hoja RFV_Razones del diagnostico: los valores de la BD de RFV).
  * "Análisis"           : tablas con mapas de calor (indices por ramo y totales de reservas) y metodo.
  * "BD_Indices", "BD_Reservas", "BD_PND", "BD_RFV_Razones": bases de datos (tablas de Excel con filtros).
Los dashboards son interactivos sin macros: las listas desplegables alimentan formulas (SUMIFS) y las
graficas se recalculan al cambiar la seleccion.

Uso: se ejecuta solo al final de proyeccion_reservas.py (GENERAR_DASHBOARD) o directamente (F5 en VSCode).
"""
from __future__ import annotations

import importlib
import math
import os
import re
import subprocess
import sys
import textwrap


def _asegurar_paquetes(paquetes: dict[str, str]) -> None:
    faltantes = []
    for modulo, nombre_pip in paquetes.items():
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltantes.append(nombre_pip)
    if faltantes:
        print(f"Instalando paquetes faltantes: {', '.join(faltantes)} ...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *faltantes])
        import site
        usuario = site.getusersitepackages()
        if os.path.isdir(usuario) and usuario not in sys.path:
            site.addsitedir(usuario)
        importlib.invalidate_caches()


_asegurar_paquetes({"openpyxl": "openpyxl>=3.1"})

from pathlib import Path  # noqa: E402

import openpyxl  # noqa: E402
from openpyxl.chart import BarChart, LineChart, Reference, Series  # noqa: E402
from openpyxl.chart.series import SeriesLabel  # noqa: E402
from openpyxl.chart.shapes import GraphicalProperties  # noqa: E402
from openpyxl.chart.text import RichText  # noqa: E402
from openpyxl.drawing.line import LineProperties  # noqa: E402
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, TwoCellAnchor  # noqa: E402
from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties  # noqa: E402
from openpyxl.formatting.rule import ColorScaleRule  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import column_index_from_string, get_column_letter  # noqa: E402
from openpyxl.utils.cell import coordinate_from_string  # noqa: E402
from openpyxl.workbook.defined_name import DefinedName  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402
from openpyxl.worksheet.hyperlink import Hyperlink  # noqa: E402
from openpyxl.worksheet.pagebreak import Break  # noqa: E402
from openpyxl.worksheet.table import Table, TableStyleInfo  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from excel_fiel import guardar_libro  # noqa: E402
except ModuleNotFoundError as _e:
    if _e.name == "excel_fiel":
        raise SystemExit("Falta excel_fiel.py en la misma carpeta que dashboard.py. Los archivos del zip deben estar "
                         "juntos en una sola carpeta.") from _e
    raise

# =============================================================================
# CONFIGURACION
# =============================================================================
CARPETA = Path(__file__).resolve().parent
SALIDAS = CARPETA / "salidas"
ARCHIVO_DANOS = SALIDAS / "BD_ BEL - IRR - MR_Proyeccion.xlsx"
ARCHIVO_RFV = SALIDAS / "BD_ RFV_Proyeccion.xlsx"
ARCHIVO_DIAGNOSTICO = SALIDAS / "Diagnostico_Proyeccion.xlsx"
SALIDA_DASHBOARD = SALIDAS / "Dashboard_Indices_Reservas.xlsx"

HOJA_PARAMETROS = "HParametros_2026"
HOJA_MONTOS = "BD_Montos_RRC_SONR"
ETIQUETA_BACKTESTING = "BACKTESTING"     # renglones de backtesting de la BD (BACKTESTING_ETIQUETA del modelo)
INDICES = ["Ind Sin RRC", "Ind sin RRC 99.5%", "Ind Sin SONR Media", "Ind Sin SONR 99.5%"]
LAGS = [f"LAG {i}" for i in range(1, 11)]
PRIMER_PERIODO_INDICES = 202101
PRIMER_PERIODO_MONTOS = 202201
PRIMER_PERIODO_MENSUAL = 202501          # grafica de columnas mensual de reservas

# Colores (paleta validada: azul = real, naranja = proyeccion; gris = contexto)
AZUL, NARANJA, GRIS_BANDA, GRIS_BARRA = "2A78D6", "EB6834", "B5B3AC", "C3C8D4"
AZULES_ORDINALES = ["86B6EF", "3987E5", "184F95"]
FONDO, PANEL, BANDA_KPI, NAV_ACTIVO = "EEF1F6", "FFFFFF", "C9D3EE", "DDE3F3"
TEXTO, TEXTO_2, BORDE = "1F2937", "52514E", "D5DAE5"
FUENTE = "Aptos Narrow"
ANCHO_REJILLA = 4.3                      # ancho de las 30 columnas de la rejilla de los dashboards (D:AG)
PIE_PAGINA = "Información de uso interno de Grupo Peña Verde"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# =============================================================================
# UTILERIAS
# =============================================================================
def etiqueta(p: int) -> str:
    return f"{MESES[p % 100 - 1]}-{str(p // 100)[2:]}"


def mover(p: int, meses: int) -> int:
    i = (p // 100) * 12 + p % 100 - 1 + meses
    return (i // 12) * 100 + i % 12 + 1


def rango(p1: int, p2: int) -> list[int]:
    out, p = [], p1
    while p <= p2:
        out.append(p)
        p = mover(p, 1)
    return out


def numero(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        t = v.replace("\xa0", " ").strip().replace(",", "")
        try:
            return float(t)
        except ValueError:
            return None
    return None


def norm(t) -> str:
    return re.sub(r"\s+", " ", str(t or "").replace("\xa0", " ")).strip().upper()


# =============================================================================
# LECTURA DE LAS SALIDAS DE LA PROYECCION
# =============================================================================
def leer_indices():
    wb = openpyxl.load_workbook(ARCHIVO_DANOS, read_only=True, data_only=True)
    ws = wb[HOJA_PARAMETROS]
    filas = ws.iter_rows(min_row=3, values_only=True)
    enc = next(filas)
    col = {}
    for i, h in enumerate(enc):
        if h is not None and str(h).strip() not in col:
            col[str(h).strip()] = i
    registros, activos = [], []
    for f in filas:
        if not f or len(f) <= col["Ramo"]:
            continue
        tipo, fecha, ramo = f[col["Tipo de Indice"]], f[col["Fecha"]], f[col["Ramo"]]
        if tipo not in ("Real", "Proyección") or not isinstance(fecha, (int, float)) or ramo is None:
            continue
        ramo = str(ramo).strip()
        fecha = int(fecha)
        if tipo == "Proyección" and ramo not in activos:
            activos.append(ramo)
        max_previo = 0.0
        for serie in INDICES + LAGS:
            v = numero(f[col[serie]]) if col[serie] < len(f) else None
            if serie in LAGS:          # 0 despues de que el patron acumulado supero 50% = marcador de faltante
                if v == 0 and max_previo > 0.5:
                    v = None
                if v is not None:
                    max_previo = max(max_previo, v)
            if v is not None:
                registros.append((tipo, ramo, serie, fecha, v))
    wb.close()
    ultimo = max(r[3] for r in registros if r[0] == "Real")
    registros = [r for r in registros if r[1] in activos and r[3] >= PRIMER_PERIODO_INDICES]
    return registros, activos, ultimo


def leer_intervalos() -> dict:
    """{(serie, ramo, periodo): (LI, LS)} de los indices (hoja Pronosticos_Drivers del diagnostico)."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return {}
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    ws = wb["Pronosticos_Drivers"]
    filas = ws.iter_rows(values_only=True)
    enc = [str(h) for h in next(filas)]
    i = {h: k for k, h in enumerate(enc)}
    li_col = next(k for h, k in i.items() if h.startswith("LI"))
    ls_col = next(k for h, k in i.items() if h.startswith("LS"))
    out = {}
    for f in filas:
        if f[i["Libro"]] == "HPARAM":
            out[(f[i["Serie"]], str(f[i["Ramo"]]), int(f[i["Periodo"]]))] = (numero(f[li_col]), numero(f[ls_col]))
    wb.close()
    return out


# Montos que calcula el script de proyeccion para las celdas de la BD que van como formula (BEL por FND de Danos, RFV por
# prima de Fianzas y sus derivados): la BD se guarda sin recalcular, asi que esas celdas no traen valor.
# {(libro, concepto, periodo, ramo): v}. Si el tablero se corre solo (sin la proyeccion), esos montos salen de la hoja
# Montos_Proyectados del diagnostico de la misma corrida (lo que el script escribio en las BD).
MONTOS_CALCULADOS: dict = {}
HOJA_DIAG_MONTOS = "Montos_Proyectados"


def montos_diagnostico() -> dict:
    """{(libro, concepto, periodo, ramo): USD} de la hoja Montos_Proyectados del diagnostico ({} si no esta)."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return {}
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    try:
        if HOJA_DIAG_MONTOS not in wb.sheetnames:
            return {}
        filas = wb[HOJA_DIAG_MONTOS].iter_rows(values_only=True)
        enc = [norm(x) for x in next(filas, ())]
        if not all(c in enc for c in ("LIBRO", "CONCEPTO", "PERIODO", "RAMO", "VALOR USD")):
            return {}
        j = {c: enc.index(c) for c in ("LIBRO", "CONCEPTO", "PERIODO", "RAMO", "VALOR USD")}
        out = {}
        for f in filas:
            v, per = numero(f[j["VALOR USD"]]), numero(f[j["PERIODO"]])
            if v is None or per is None:
                continue
            out[(str(f[j["LIBRO"]]).strip(), norm(f[j["CONCEPTO"]]), int(per), str(f[j["RAMO"]]).strip())] = v
        return out
    finally:
        wb.close()


def leer_montos(ultimo: int):
    registros, tc = [], {}
    ramos = {}
    respaldo = None                      # Montos_Proyectados del diagnostico (solo si hace falta)
    for libro, ruta in (("DANOS", ARCHIVO_DANOS), ("FIANZAS", ARCHIVO_RFV)):
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb[HOJA_MONTOS]
        filas = ws.iter_rows(min_row=3, values_only=True)
        enc = [str(h).strip() if h is not None else None for h in next(filas)]
        c_conc, c_per, c_tc = enc.index("CONCEPTO"), enc.index("PERIODO"), enc.index("TC")
        c_ramos = {h.split("_", 1)[1]: k for k, h in enumerate(enc) if h and h.startswith("RAM_")}
        for f in filas:
            if not f or f[c_conc] is None or not isinstance(f[c_per], (int, float)):
                continue
            per = int(f[c_per])
            if per < PRIMER_PERIODO_MONTOS:
                continue
            concepto = norm(f[c_conc])
            if concepto == norm(ETIQUETA_BACKTESTING) or concepto.startswith(norm(ETIQUETA_BACKTESTING) + " "):   # (backtesting)
                continue
            reserva, conc = ("RFV", "RCONT") if concepto == "RCONT" else concepto.split(" ", 1)
            ramos.setdefault(reserva, list(c_ramos))
            t = numero(f[c_tc])
            if t:
                tc.setdefault(per, t)
            tipo = "Real" if per <= ultimo else "Proyección"
            for ramo, k in c_ramos.items():
                v = numero(f[k])
                if v is None:                    # formula sin valor guardado: el monto que calculo la proyeccion
                    v = MONTOS_CALCULADOS.get((libro, concepto, per, ramo))
                if v is None and per > ultimo:   # (tablero corrido solo: lo que el script escribio en la BD)
                    if respaldo is None:
                        respaldo = montos_diagnostico()
                    v = respaldo.get((libro, concepto, per, ramo))
                if v is None:                    # celda vacia (mes sin captura): sin dato, no un cero real
                    continue
                registros.append((libro, reserva, conc, ramo, per, tipo, v))
        wb.close()
    return registros, tc, ramos


HOJA_RAZONES = "Dashboard Razones"                # seccion Razones (en el HTML, la pestaña "Razones")
HOJA_INDICADORES_RAMO = "Indicadores_Ramo"      # hoja del diagnostico con los indicadores por ramo de la BD de Danos
# indicadores de la seccion Razones (pestaña del HTML y hoja del Excel): (columna de la hoja, titulo, unidad: "monto" en USD, "pct" razon o "fnd")
INDICADORES_PND = [
    ("PND/PD", "PND / PD", "monto"),
    ("FACTOR GTO", "FACTOR GTO (GTO / PND)", "pct"),
    ("FACTOR MR", "FACTOR MR (MR / PND o PD)", "pct"),
    ("CESION", "CESIÓN (IRR / BRUTO)", "pct"),
    ("FD/FND", "FD / FND (PND o PD / PEACUMULADA)", "fnd"),
    ("IS (RL)", "IS (RL): índice de siniestralidad de HParametros", "pct"),
    ("IS (FA)", "IS (FA): índice de siniestralidad de la función actuarial", "pct"),
    ("PE FCST", "PE FCST: prima tomada del mes", "monto"),
    ("PRIMA N AÑOS", "PRIMA N AÑOS: prima de los últimos 12 meses", "monto"),
    ("PEACUMULADA", "PEACUMULADA", "monto"),
]
# "Todos los ramos": en cada mes, los ramos con PND / PD (sin IS (RL) no hay PND, y un PD en 0 no es reserva); los montos
# se suman y los factores e indices son el promedio ponderado de esos ramos, que equivale a la razon de las sumas: FACTOR
# GTO, FACTOR MR e IS con el PND / PD (GTO / PND, MR / PND, BEL / PND), CESION con el BRUTO (IRR / BRUTO) y FD / FND =
# suma de PND / suma de PEACUMULADA. Todas las graficas de "Todos" usan los mismos ramos en cada mes
COLUMNAS_METODO_AREA = ("PND/PD", "FACTOR MR", "CESION", "FD/FND")   # historia del metodo del area (Res_Rvas) de las
SUFIJO_METODO_AREA = "(metodo del area)"     # series que SAP no registra (BEL_METODO_AREA del script): va en gris
PESO_TODOS = {"FACTOR GTO": "PND/PD", "FACTOR MR": "PND/PD", "IS (RL)": "PND/PD", "IS (FA)": "PND/PD", "CESION": "BRUTO"}
# una razon cuyo denominador casi no existe (menos de 1 USD o del 0.1 % de su nivel tipico en la serie: p. ej. el BEL de
# SONR 80 en 0 desde 2022) va sin dato en el tablero: en la BD la formula da ruido de punto flotante (miles de millones
# de %) o 0 por SI.ERROR
DENOMINADOR = {"FACTOR GTO": "PND/PD", "FACTOR MR": "PND/PD", "CESION": "BRUTO", "FD/FND": "PEACUMULADA"}
DENOMINADOR_MIN, DENOMINADOR_REL = 1.0, 0.001


def _rangos_meses(meses: list) -> list:
    """[(primer, ultimo)] de los tramos consecutivos de una lista ordenada de AAAAMM."""
    out = []
    for p in meses:
        if out and mover(out[-1][1], 1) == p:
            out[-1][1] = p
        else:
            out.append([p, p])
    return [tuple(x) for x in out]


def leer_indicadores_ramo() -> dict | None:
    """Hoja HOJA_INDICADORES_RAMO del diagnostico (los valores de los bloques de indicadores de la BD de Danos, RRC y
    SONR, por ramo y mes): {"periodos": [...], "ramos": [...], "datos": {reserva: {ramo o "Todos": {indicador:
    [valor por periodo o None]}}} ("Todos" trae ademas "IS (RL) ramos FA": el IS (RL) ponderado solo con los ramos de
    IS (FA), para compararlos), "con_fa": [ramos con IS (FA)], "is_fa_bel": {reserva: [ramos cuyo BEL y PND / PD
    proyectados usan el IS (FA)]}, "lleva_gto": {reserva: bool}, "fnd": {reserva: [ramos con
    BEL por FND]}, "faltan": {reserva: texto de los ramos que no entran a "Todos" y en que meses}, "distinto": {reserva:
    [posiciones de los meses en que "Todos" no tiene los mismos ramos que en el ultimo mes real]}, "sin_denominador":
    {reserva: n de razones sin dato por denominador casi nulo}, "metodo_area": {reserva: [ramos cuya historia del FND
    sale del metodo del area; sus datos traen ademas "<indicador> (metodo del area)"]}, "falla_area": {reserva: {ramo:
    por que no se pudo usar el metodo del area (su BEL queda en 0)}}, "meses_n", "anios_lag": {reserva: n},
    "renglones": n}.
    None si no esta la hoja (diagnostico de una version anterior)."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return None
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    try:
        if HOJA_INDICADORES_RAMO not in wb.sheetnames:
            return None
        filas = wb[HOJA_INDICADORES_RAMO].iter_rows(values_only=True)
        enc = [str(h) if h is not None else "" for h in next(filas)]
        crudos = [dict(zip(enc, f)) for f in filas if f and f[0] in ("RRC", "SONR")]
    finally:
        wb.close()
    if not crudos:
        return None
    periodos = sorted({int(r["Periodo"]) for r in crudos})
    ramos = sorted({str(r["Ramo"]) for r in crudos}, key=lambda x: int(x) if x.isdigit() else 10 ** 6)
    pos = {p: i for i, p in enumerate(periodos)}
    columnas = [c for c, _, _ in INDICADORES_PND] + ["BRUTO"]
    datos, lleva_gto, fnd, anios_lag, metodo_area, falla_area = {}, {}, {}, {}, {}, {}
    meses_n = next((int(numero(r.get("Meses PRIMA N AÑOS"))) for r in crudos if numero(r.get("Meses PRIMA N AÑOS"))), 12)
    for r in crudos:
        res, ramo, i = r["Reserva"], str(r["Ramo"]), pos[int(r["Periodo"])]
        d = datos.setdefault(res, {}).setdefault(ramo, {c: [None] * len(periodos) for c in columnas})
        for c in columnas:
            d[c][i] = numero(r.get(c))
        if numero(r.get("Lleva GTO")):
            lleva_gto[res] = True
        if numero(r.get("BEL por FND")) and ramo not in fnd.setdefault(res, []):
            fnd[res].append(ramo)
        hist_bel = str(r.get("Historia del BEL") or "")
        if hist_bel.startswith(("sin metodo del area", "no se pudo usar el metodo del area")):
            falla_area.setdefault(res, {})[ramo] = hist_bel.split(": ", 1)[-1]
        if hist_bel == "metodo del area":
            if ramo not in metodo_area.setdefault(res, []):
                metodo_area[res].append(ramo)
            for c in COLUMNAS_METODO_AREA:
                d.setdefault(f"{c} {SUFIJO_METODO_AREA}", [None] * len(periodos))[i] = numero(
                    r.get(f"{c} {SUFIJO_METODO_AREA}"))
        if numero(r.get("Años LAG PEACUMULADA")) is not None:
            anios_lag[res] = int(numero(r.get("Años LAG PEACUMULADA")))
    faltan, sin_den, distinto = {}, {}, {}
    for res, por_ramo in datos.items():
        lleva_gto.setdefault(res, False)
        sin_den[res] = 0
        for v in por_ramo.values():
            if not lleva_gto[res]:             # SONR no tiene GTO: la BD pone 0; en el tablero va sin dato, no 0
                v["FACTOR GTO"] = [None] * len(periodos)
            for c, den in DENOMINADOR.items():  # razones con denominador casi nulo: sin dato
                tipicos = sorted(abs(x) for x in v[den] if x is not None and abs(x) >= DENOMINADOR_MIN)
                umbral = max(DENOMINADOR_MIN, DENOMINADOR_REL * (tipicos[len(tipicos) // 2] if tipicos else 0))
                for i, x in enumerate(v[den]):
                    if v[c][i] is not None and (x is None or abs(x) < umbral):
                        v[c][i] = None
                        sin_den[res] += 1
        # "Todos": en cada mes, los ramos con PND / PD (los mismos en todas las graficas)
        dentro = {r: [x is not None and abs(x) >= DENOMINADOR_MIN for x in v["PND/PD"]] for r, v in por_ramo.items()}
        tot = {c: [None] * len(periodos) for c in columnas + ["IS (RL) ramos FA"]}
        con_fa_res = {r for r, v in por_ramo.items() if any(x is not None for x in v["IS (FA)"])}
        for i in range(len(periodos)):
            rs = [r for r in por_ramo if dentro[r][i]]
            if not rs:
                continue
            for c in columnas:
                if c not in PESO_TODOS and c != "FD/FND":          # montos: suma de los ramos
                    xs = [por_ramo[r][c][i] for r in rs if por_ramo[r][c][i] is not None]
                    tot[c][i] = sum(xs) if xs else None
            for c, w in list(PESO_TODOS.items()) + [("IS (RL) ramos FA", "PND/PD")]:   # razones ponderadas
                col = "IS (RL)" if c == "IS (RL) ramos FA" else c
                pares = [(por_ramo[r][col][i], por_ramo[r][w][i]) for r in rs
                         if (c != "IS (RL) ramos FA" or r in con_fa_res)
                         and por_ramo[r][col][i] is not None and por_ramo[r][w][i] is not None]
                sw = sum(b for _, b in pares)
                tot[c][i] = sum(a * b for a, b in pares) / sw if pares and sw > 0 else None
            pares = [(por_ramo[r]["PND/PD"][i], por_ramo[r]["PEACUMULADA"][i]) for r in rs
                     if por_ramo[r]["PEACUMULADA"][i] is not None]
            sp = sum(b for _, b in pares)
            tot["FD/FND"][i] = sum(a for a, _ in pares) / sp if pares and sp >= DENOMINADOR_MIN else None
        # meses en que "Todos" no tiene los mismos ramos que en el ultimo mes real (se sombrean en el HTML)
        i_ult = max((pos[int(r["Periodo"])] for r in crudos if r.get("Tipo") == "Real"), default=len(periodos) - 1)
        base = {r for r in por_ramo if dentro[r][i_ult]}
        distinto[res] = [i for i in range(len(periodos)) if {r for r in por_ramo if dentro[r][i]} != base]
        # ramos que no entran a "Todos" y en que meses (en el rango con algun ramo)
        activos = [i for i in range(len(periodos)) if any(dentro[r][i] for r in por_ramo)]
        grupos = {}
        for r in por_ramo:
            fuera = [periodos[i] for i in activos if not dentro[r][i]]
            if fuera:
                grupos.setdefault(tuple(_rangos_meses(fuera)), []).append(r)
        faltan[res] = "; ".join(
            f"{', '.join(rs[:-1]) + ' y ' + rs[-1] if len(rs) > 1 else rs[0]}: "
            + ("todo el periodo" if len(tramos) == 1 and tramos[0] == (periodos[activos[0]], periodos[activos[-1]])
               else ", ".join(f"{etiqueta(a)} a {etiqueta(b)}" if a != b else etiqueta(a) for a, b in tramos))
            for tramos, rs in sorted(grupos.items(), key=lambda x: (x[0][0][0], x[1])))
        por_ramo["Todos"] = tot
    con_fa = [r for r in ramos if any(x is not None for res in datos.values() for x in res.get(r, {}).get("IS (FA)", []))]
    is_fa_bel = {res: sorted({str(f["Ramo"]) for f in crudos if f.get("Reserva") == res and f.get("IS del BEL") == "FA"},
                             key=lambda x: int(x) if x.isdigit() else 10 ** 6) for res in datos}
    return {"periodos": periodos, "ramos": ramos, "datos": datos, "con_fa": con_fa, "is_fa_bel": is_fa_bel,
            "lleva_gto": lleva_gto,
            "fnd": {res: sorted(v, key=lambda x: int(x) if x.isdigit() else 10 ** 6) for res, v in fnd.items()},
            "faltan": faltan, "distinto": distinto, "sin_denominador": sin_den, "meses_n": meses_n, "anios_lag": anios_lag,
            "metodo_area": metodo_area, "falla_area": falla_area,
            "renglones": len(crudos)}


HOJA_RAZONES_RFV = "RFV_Razones"                 # hoja del diagnostico con las razones de la RFV de Fianzas
HOJA_DASH_RFV = "Dashboard Razones RFV"          # seccion de las razones de la RFV (en el HTML, la pestaña "Razones RFV")
FILAS_HOJA_RFV = 150                             # renglones de esa hoja (graficas, factores y prima base)
# (columna de la hoja, titulo, unidad, serie de referencia en gris o None)
# (titulos cortos: en Excel los paneles de media hoja caben unos 55 caracteres con " · todos los ramos" y la unidad;
# el orden fija la rejilla: el primero y el ultimo a todo lo ancho, los demas por pares)
INDICADORES_RFV = [
    ("FRV", "FRV: RFV BRUTO × TC / PRIMA 24M", "razon", "FRV residual (sin RFV MA)"),
    ("PRIMA 24M (MXN)", "PRIMA 24M (prima tomada)", "mxn", None),
    ("CESION", "CESIÓN: IRR / BRUTO", "pct", None),
    ("FV", "FV: (RFV − RFV MA aparte) / (PR + GA)", "razon", None),
    ("RC", "RC: CESIÓN / FCR", "pct", "RC PRIMA"),
    ("PD", "PD del reasegurador (Res_Rvas)", "pct3", "PD xDefault 24 meses"),
    ("MA (MXN)", "MA: monto afianzado", "mxn", None),
    ("RFV MA / RFV BRUTO", "RFV por MA: RFV MA / RFV BRUTO", "pct", None),
]
COL_BDREAL_RFV = "Meses de BDReal (%SEG PR y %COM PR)"
ESCALA_REF_RFV = 3      # la serie gris sale de la grafica (queda en la tabla) si su rango es mas de 3 veces el de la serie
FACTORES_RFV_TABLA = ("%SEG PR", "%COM PR", "%CARGAS", "FPR", "%GA", "OMEGA", "ALFA", "FCR")


def _filas_hoja(wb, hoja: str) -> list:
    """Renglones de una hoja del diagnostico como dicts (encabezado en el renglon 1); [] si no esta."""
    if hoja not in wb.sheetnames:
        return []
    filas = wb[hoja].iter_rows(values_only=True)
    enc = [str(h) if h is not None else "" for h in next(filas, ())]
    return [dict(zip(enc, f)) for f in filas if f and any(v is not None for v in f)]


def _leer_extra_rfv() -> dict:
    """Del diagnostico, para la seccion de Razones RFV: la tendencia que se aplico al FRV y a la CESION de cada ramo
    (RFV_Prima_Resumen), el motivo de un N/A del monto afianzado o de la PD (Alertas) y la prima base (RFV_Prima_Base,
    RFV_Prima_Bloques y RFV_Prima_Sensibilidad)."""
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    try:
        res = _filas_hoja(wb, "RFV_Prima_Resumen")
        alertas = [f for f in _filas_hoja(wb, "Alertas")]
        base = _filas_hoja(wb, "RFV_Prima_Base")
        bloques = _filas_hoja(wb, "RFV_Prima_Bloques")
        sens = _filas_hoja(wb, "RFV_Prima_Sensibilidad")
    finally:
        wb.close()
    tend = {}
    for f in res:
        r = str(f.get("Ramo") or "")
        if r and any(f.get(c) for c in ("FRV tendencia aplicada", "CESION tendencia aplicada", "FRV modelo",
                                         "CESION modelo")):
            tend[r] = {k: str(f.get(c) or "") for k, c in (("frv", "FRV tendencia aplicada"),
                                                            ("ces", "CESION tendencia aplicada"),
                                                            ("modelo_frv", "FRV modelo"), ("modelo_ces", "CESION modelo"),
                                                            ("proyecta", "El modelo proyecta"))}
    na = {}
    for f in alertas:
        vals = [str(v) for v in f.values() if v is not None]
        txt = next((v for v in vals if "N/A" in v), "")
        if not txt:
            continue
        txt = re.sub(r"\s*\[carpeta de entradas: [^\]]*\]", "", txt)   # (la ruta local no va a los tableros)
        if any(v == "Monto afianzado" for v in vals) and "MA" not in na:
            na["MA"] = txt
        elif any(v == "PD de Fianzas" for v in vals) and txt.startswith("PD de Fianzas: N/A") and "PD" not in na:
            na["PD"] = txt                           # (sin Res_Rvas pero con xDefault la PD no esta en N/A: es la referencia)
    num = (int, float)
    prima = {"base": [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in f.items()
                       if k in ("Ramo", "Periodo", "Real o proyeccion", "Fuente", "PT usada (MXN)",
                                "PT mismo mes ano anterior (MXN)", "Crecimiento contra el mismo mes", "PRIMA 24M (MXN)",
                                "Parte no real de la PRIMA 24M")} for f in base],
             "bloques": [{k: v for k, v in f.items() if isinstance(v, num + (str,))} for f in bloques],
             "sens": [{k: v for k, v in f.items() if isinstance(v, num + (str,)) and not k.startswith("RFV BRUTO 1")}
                      for f in sens]}
    return {"tendencia": tend, "na": na, "prima": prima}


def leer_razones_rfv() -> dict | None:
    """Hoja HOJA_RAZONES_RFV del diagnostico (las razones de la RFV de Fianzas por ramo y mes, con "Todos"): {"periodos",
    "ramos": [ramos con RFV por prima], "datos": {ramo o "Todos": {columna: [valor por periodo o None]}}, "origen_ma":
    {ramo: [texto por periodo]}, "pd_medida": {ramo: [la PD del mes se midio en Res_Rvas]}, "pd_origen": {ramo: [origen
    de la PD del mes: medida, ultima medida fija, referencia de xDefault o sin PD]}, "split": [ramos con el
    monto afianzado aparte], "factores": {ramo: {factor: valor del
    ultimo mes real y del ultimo proyectado}}, "ramos_todos": [texto por periodo], "renglones": n}. None sin la hoja
    (diagnostico de una version anterior o sin RFV por prima)."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return None
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    try:
        if HOJA_RAZONES_RFV not in wb.sheetnames:
            return None
        filas = wb[HOJA_RAZONES_RFV].iter_rows(values_only=True)
        enc = [str(h) if h is not None else "" for h in next(filas)]
        crudos = [dict(zip(enc, f)) for f in filas if f and f[0] is not None and f[1] is not None]
    finally:
        wb.close()
    if not crudos:
        return None
    periodos = sorted({int(r["Periodo"]) for r in crudos})
    pos = {p: i for i, p in enumerate(periodos)}
    ramos = sorted({str(r["Ramo"]) for r in crudos if str(r["Ramo"]) != "Todos"}, key=lambda x: int(x) if x.isdigit() else 0)
    columnas = [c for c, _, _, _ in INDICADORES_RFV] + [g for _, _, _, g in INDICADORES_RFV if g] \
        + list(FACTORES_RFV_TABLA) + ["RFV BRUTO (MXN)", "RFV MA (MXN)"]
    datos, origen, ramos_todos, split, factores, pd_medida = {}, {}, [""] * len(periodos), set(), {}, {}
    pd_origen = {}
    for r in crudos:
        ramo, i = str(r["Ramo"]), pos[int(r["Periodo"])]
        d = datos.setdefault(ramo, {c: [None] * len(periodos) for c in columnas})
        for c in columnas:
            d[c][i] = numero(r.get(c))
        origen.setdefault(ramo, [""] * len(periodos))[i] = str(r.get("Origen del MA") or "")
        pd_medida.setdefault(ramo, [False] * len(periodos))[i] = str(r.get("PD medida") or "") == "si"
        pd_origen.setdefault(ramo, [""] * len(periodos))[i] = str(r.get("Origen de la PD") or "")
        if ramo == "Todos":
            ramos_todos[i] = str(r.get("Ramos en Todos") or "")
        elif str(r.get("MA aparte") or "") == "si":
            split.add(ramo)
    real = [str(r.get("Real o proyeccion")) == "real" for r in sorted(crudos, key=lambda x: int(x["Periodo"]))]
    p_ult = max((int(r["Periodo"]) for r in crudos if str(r.get("Real o proyeccion")) == "real"), default=periodos[0])
    for ramo, d in datos.items():
        factores[ramo] = {c: {"real": d[c][pos[p_ult]], "proy": d[c][-1]} for c in FACTORES_RFV_TABLA}
    # meses del CSV del area: con MA real, estimado (en "Todos", si algun ramo lo trae estimado) y huecos (meses sin MA
    # entre el primero y el ultimo con MA, en algun ramo)
    ma_est = {r: [o == "Estimado" for o in v] for r, v in origen.items() if r != "Todos"}
    if ma_est:
        ma_est["Todos"] = [any(v[i] for v in ma_est.values()) for i in range(len(periodos))]
    ma_interp = sorted({periodos[i] for v in origen.values() for i, o in enumerate(v) if o.startswith("Interpolado")})
    ma_proy = sorted({periodos[i] for v in origen.values() for i, o in enumerate(v) if o.startswith("Proyectado")})
    ma_real = [p for i, p in enumerate(periodos) if any(v[i].startswith("Real") for r, v in origen.items() if r != "Todos")]
    huecos = set()
    for ramo, d in datos.items():
        con = [i for i, v in enumerate(d["MA (MXN)"]) if v is not None]
        if con:
            huecos |= {periodos[i] for i in range(con[0], con[-1]) if d["MA (MXN)"][i] is None}
    con_xd = [i for d in datos.values() for i, v in enumerate(d["PD xDefault 24 meses"]) if v is not None]
    bdreal = next((str(r.get(COL_BDREAL_RFV)) for r in crudos if str(r.get(COL_BDREAL_RFV) or "-") != "-"), "")
    bdreal = re.sub(r"\b(\d{6})\b", lambda m: etiqueta(int(m.group(1))), bdreal)     # "202601 a 202607" -> "ene-26 a jul-26"
    extra = _leer_extra_rfv()
    return {"periodos": periodos, "ramos": ramos, "datos": datos, "origen_ma": origen, "split": sorted(split),
            "pd_medida": pd_medida, "pd_origen": pd_origen, **extra,
            "factores": factores, "ramos_todos": ramos_todos, "ultimo_real": p_ult, "renglones": len(crudos),
            "hay_real": any(real), "ma_estimado": ma_est, "ma_real_hasta": max(ma_real, default=0),
            "ma_interpolado": ma_interp, "ma_proyectado": ma_proy,
            "ma_huecos": sorted(huecos), "xdefault_hasta": periodos[max(con_xd)] if con_xd else 0, "bdreal": bdreal,
            "escala_ref": ESCALA_REF_RFV}


def texto_meses(meses: list) -> str:
    """"nov-25 a ene-26 y mar-26" para una lista de AAAAMM."""
    t = [etiqueta(a) if a == b else f"{etiqueta(a)} a {etiqueta(b)}" for a, b in _rangos_meses(sorted(meses))]
    return (", ".join(t[:-1]) + " y " + t[-1]) if len(t) > 1 else (t[0] if t else "")


def ramos_ma_informativa(rz: dict) -> list:
    """Ramos con monto afianzado que no lo llevan aparte (su RFV MA es informativa: queda dentro de FV)."""
    return [r for r in rz["ramos"] if r not in rz["split"] and any(v is not None for v in rz["datos"][r]["MA (MXN)"])]


def parte_ma_aparte(rz: dict, p: int):
    """Suma de la RFV MA de los ramos con el monto afianzado aparte / suma de la RFV BRUTO de "Todos", en el mes p."""
    i = rz["periodos"].index(p)
    tot = rz["datos"].get("Todos", {}).get("RFV BRUTO (MXN)", [None] * (i + 1))[i]
    ma = [rz["datos"][r]["RFV MA (MXN)"][i] for r in rz["split"]]
    return sum(ma) / tot if tot and ma and all(v is not None for v in ma) else None


def ref_en_escala(rz: dict, ramo: str, col: str = "PD", ref: str = "PD xDefault 24 meses") -> bool:
    """La serie de referencia cabe en la grafica de col: su rango no pasa de ESCALA_REF_RFV veces el de la serie (la
    misma regla que el HTML; fuera de escala aplanaria la serie, y va solo en la tabla)."""
    a = [v for v in rz["datos"].get(ramo, {}).get(col, []) if v is not None and v > 0]
    b = [v for v in rz["datos"].get(ramo, {}).get(ref, []) if v is not None and v > 0]
    return not a or not b or (max(b) <= ESCALA_REF_RFV * max(a) and min(b) >= min(a) / ESCALA_REF_RFV)


def _motivo_corto(txt: str, n: int = 70) -> str:
    """El motivo de un N/A de la consola (Alertas), corto para un renglon: lo que sigue a "N/A:" hasta el primer ";" o ":"."""
    m = re.split(r"N/A:\s*", str(txt), maxsplit=1)[-1].split(";")[0].split(": ")[0].split(" [carpeta")[0].strip().rstrip(".")
    return m if len(m) <= n else m[:n - 1].rstrip() + "…"


def notas_ramo_rfv(rz: dict, ultimo: int) -> dict:
    """{ramo o "Todos": texto} sobre el monto afianzado del ramo en el ultimo mes real (lo lee el renglon 9 de la hoja
    de Razones RFV con el ramo elegido)."""
    split, info, i = rz["split"], ramos_ma_informativa(rz), rz["periodos"].index(ultimo)
    na = rz.get("na") or {}
    out = {}
    for ramo in ["Todos"] + rz["ramos"]:
        if na.get("MA"):                             # (MA en N/A: el motivo corto; completo en Alertas y la consola)
            t = f"{'Todos' if ramo == 'Todos' else f'Ramo {ramo}'}: MA en N/A ({_motivo_corto(na['MA'])}; ver Alertas)."
        elif ramo == "Todos":                        # (textos de un renglon: caben en D9:AG9)
            x = parte_ma_aparte(rz, ultimo)
            t = (f"Todos: RFV por MA = aparte ({', '.join(split) or 'ninguno'}) + informativa "
                 f"({', '.join(info) or 'ninguno'}, dentro de FV)"
                 + (f"; la aparte es {x * 100:.1f} % de la RFV en {etiqueta(ultimo)}." if x is not None else "."))
        elif ramo in split:
            t = f"Ramo {ramo}: la RFV MA va aparte (FRV = FRV residual + RFV MA / PRIMA 24M)."
        elif ramo in info:
            t = f"Ramo {ramo}: la RFV MA es informativa (queda dentro de FV)."
        else:
            t = f"Ramo {ramo}: sin monto afianzado en el CSV del área."
        if na.get("PD"):
            t += " PD en N/A (FCR = 1)."
        elif ramo != "Todos" and not any((rz.get("pd_medida") or {}).get(ramo, [])) \
                and any("referencia" in o for o in (rz.get("pd_origen") or {}).get(ramo, [])):
            t += " PD de referencia (xDefault del área; sin castigo medido)."
        if (rz.get("ma_estimado") or {}).get(ramo, [False] * (i + 1))[i]:
            t += (f" MA de {etiqueta(ultimo)} estimado por el área (real hasta {etiqueta(rz['ma_real_hasta'])})."
                  if rz.get("ma_real_hasta") and ramo != "Todos" else f" MA de {etiqueta(ultimo)} estimado por el área.")
        if rz.get("ma_interpolado"):
            t += f" MA interpolado en {texto_meses(rz['ma_interpolado'])}."
        o_proy = next((o for o in (rz.get("origen_ma") or {}).get(ramo, []) if o.startswith("Proyectado")), "")
        if ramo != "Todos" and o_proy:
            t += " MA 2027 " + ("por tendencia." if "tendencia" in o_proy else "sigue a la prima." if "PRIMA" in o_proy
                                else "proyectado.")
        out[ramo] = t
    return out


def etiquetas_modelo(metodo: list) -> dict:
    """Modelo por tipo de serie para las etiquetas (hoja Backtest, una fila por tipo y libro): los modelos de todos los
    libros sin repetir; el de las series trimestrales (RCONT) va aparte para no atribuirselo a todos los montos."""
    modelos = {}
    for d in metodo:
        for m in str(d.get("Modelo") or "").split(", "):
            if m and m not in modelos.setdefault(d.get("Tipo"), []):
                modelos[d.get("Tipo")].append(m)
    out = {}
    for tipo, ms in modelos.items():
        otros, trim = [m for m in ms if "trimestral" not in m], [m for m in ms if "trimestral" in m]
        out[tipo] = ", ".join(otros) + (f"; RCONT: {', '.join(trim)}" if otros and trim else ", ".join(trim) if trim else "")
    return out


def version_codigo() -> str:
    """Version de los scripts que generaron el diagnostico (hoja Resumen, "Version del codigo")."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return "sin diagnostico"
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    try:
        filas = {str(a).strip(): b for a, b, *_ in wb["Resumen"].iter_rows(values_only=True) if a} \
            if "Resumen" in wb.sheetnames else {}
    finally:
        wb.close()
    return str(filas.get("Version del codigo") or "anterior a 2026-10-05b")


def nota_modelo() -> str:
    """Nota corta sobre el modelo de tendencia (ventana y estacionalidad), leida de la hoja Resumen del diagnostico."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return ""
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    filas = {str(a).strip(): b for a, b, *_ in wb["Resumen"].iter_rows(values_only=True) if a} if "Resumen" in wb.sheetnames else {}
    wb.close()
    ventana = filas.get("Ventana de tendencia (meses)")
    texto_est = str(filas.get("Estacionalidad mensual", "")).lower()
    estacional = texto_est.startswith("si")
    tipos = texto_est.split(":")[0].replace("si, en ", "").strip() if estacional else ""
    recta = f"recta de {ventana} meses" if ventana and str(ventana).isdigit() else "recta de toda la historia"
    etiqueta = {"nivel": "montos", "indice": "índices"}
    donde = " e ".join(etiqueta.get(x.strip(), x.strip()) for x in tipos.split(" e ") if x.strip()) if tipos else ""
    return f"({recta}" + (f" + patrón del año en {donde})" if estacional and donde else ")")


def leer_metodo() -> list:
    """Filas de la hoja Backtest del diagnostico (modelo y error por tipo de serie)."""
    if not ARCHIVO_DIAGNOSTICO.exists():
        return []
    wb = openpyxl.load_workbook(ARCHIVO_DIAGNOSTICO, read_only=True, data_only=True)
    if "Backtest" not in wb.sheetnames:
        return []
    filas = wb["Backtest"].iter_rows(values_only=True)
    enc = [str(h) for h in next(filas)]
    out = [dict(zip(enc, f)) for f in filas if f and f[0] in ("nivel", "indice", "razon", "lag")]
    wb.close()
    return out


# =============================================================================
# ESTILO
# =============================================================================
def relleno(color):
    return PatternFill("solid", fgColor=color)


def fuente(tam=10, negrita=False, color=TEXTO, cursiva=False):
    return Font(name=FUENTE, size=tam, bold=negrita, color=color, italic=cursiva)


LADO = Side(style="thin", color=BORDE)
BORDE_CAJA = Border(left=LADO, right=LADO, top=LADO, bottom=LADO)


def pintar(ws, rango_celdas, color):
    for fila in ws[rango_celdas]:
        for c in fila:
            c.fill = relleno(color)


def caja(ws, rango_celdas, color=PANEL):
    """Panel con relleno y contorno fino."""
    filas = ws[rango_celdas]
    for i, fila in enumerate(filas):
        for j, c in enumerate(fila):
            c.fill = relleno(color)
            c.border = Border(left=LADO if j == 0 else None, right=LADO if j == len(fila) - 1 else None,
                              top=LADO if i == 0 else None, bottom=LADO if i == len(filas) - 1 else None)


def preparar_hoja(ws, ancho_nav=27, columnas=30, ancho=ANCHO_REJILLA, filas=48):
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 85
    ws.column_dimensions["A"].width = 1.5
    ws.column_dimensions["B"].width = ancho_nav
    ws.column_dimensions["C"].width = 1.5
    for k in range(4, 4 + columnas):
        ws.column_dimensions[get_column_letter(k)].width = ancho
    ws.column_dimensions[get_column_letter(4 + columnas)].width = 1.5
    pintar(ws, f"A1:{get_column_letter(4 + columnas)}{filas}", FONDO)


def texto_ejes(tam=800, color=TEXTO_2):
    cp = CharacterProperties(sz=tam, solidFill=color, latin=None)
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])


def colocar(ws, ch, desde: str, hasta: str, margen_px: int = 5):
    """Ancla la grafica a las celdas (se estira con ellas): de la esquina superior izquierda de `desde` a la
    inferior derecha de `hasta`, con un margen para no tapar el contorno del panel."""
    emu = 9525
    c1, f1 = coordinate_from_string(desde)
    c2, f2 = coordinate_from_string(hasta)
    k2 = column_index_from_string(c2)
    ancho = ws.column_dimensions[c2].width if c2 in ws.column_dimensions else 8.43
    alto = ws.row_dimensions[f2].height if f2 in ws.row_dimensions and ws.row_dimensions[f2].height else 15
    ancla = TwoCellAnchor()
    ancla._from = AnchorMarker(col=column_index_from_string(c1) - 1, colOff=margen_px * emu,
                               row=f1 - 1, rowOff=margen_px * emu)
    ancla.to = AnchorMarker(col=k2 - 1, colOff=max(int(ancho * 7 + 5) - margen_px, 0) * emu,
                            row=f2 - 1, rowOff=max(int(alto * 4 / 3) - margen_px, 0) * emu)
    ws.add_chart(ch, ancla)


def estilo_grafica(ch, formato_y="General", leyenda=True):
    ch.graphical_properties = GraphicalProperties(ln=LineProperties(noFill=True))
    ch.plot_area.graphicalProperties = GraphicalProperties(ln=LineProperties(noFill=True))
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    ch.y_axis.number_format = formato_y
    ch.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E6E8EE", w=6350))
    ch.x_axis.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill="C9CCD4", w=6350))
    ch.y_axis.graphicalProperties = GraphicalProperties(ln=LineProperties(noFill=True))
    ch.x_axis.txPr = texto_ejes()
    ch.y_axis.txPr = texto_ejes()
    ch.display_blanks = "gap"
    if leyenda:
        ch.legend.position = "b"
        ch.legend.txPr = texto_ejes(850, TEXTO)
    else:
        ch.legend = None
    return ch


def linea(serie, color, ancho_pt=2.0, punteada=False, marcador=False):
    serie.graphicalProperties.line.solidFill = color
    serie.graphicalProperties.line.width = int(ancho_pt * 12700)
    if punteada:
        serie.graphicalProperties.line.dashStyle = "dash"
    if marcador:                                     # punto chico en cada mes con dato: se ve un mes suelto entre #N/D
        serie.marker.symbol = "circle"
        serie.marker.size = 4
        serie.marker.graphicalProperties = GraphicalProperties(solidFill=color, ln=LineProperties(solidFill=color))
    else:
        serie.marker.symbol = "none"
    serie.smooth = False


def barra(serie, color):
    serie.graphicalProperties.solidFill = color
    serie.graphicalProperties.line.solidFill = PANEL


# =============================================================================
# CONSTRUCCION
# =============================================================================
def generar(ruta_salida: Path = SALIDA_DASHBOARD) -> Path:
    print("Generando dashboards ...", flush=True)
    registros_i, ramos_i, ultimo = leer_indices()
    intervalos = leer_intervalos()
    registros_m, tc, ramos_m = leer_montos(ultimo)
    metodo = leer_metodo()
    proc = etiquetas_modelo(metodo)
    fin = max(r[3] for r in registros_i)
    fin_m = max(r[4] for r in registros_m)
    p_dic_actual = (ultimo // 100) * 100 + 12
    p_12 = mover(ultimo, -12)
    pnd = leer_indicadores_ramo()                    # None con un diagnostico de una version anterior
    rz = leer_razones_rfv()                          # razones de la RFV (None sin RFV por prima o diagnostico anterior)

    wb = openpyxl.Workbook()
    wd_i = wb.active
    wd_i.title = "Dashboard Índices"
    wd_r = wb.create_sheet("Dashboard Reservas")
    wd_p = wb.create_sheet(HOJA_RAZONES) if pnd else None
    wd_rz = wb.create_sheet(HOJA_DASH_RFV) if rz else None
    wa = wb.create_sheet("Análisis")
    wbi = wb.create_sheet("BD_Indices")
    wbr = wb.create_sheet("BD_Reservas")
    wbp = wb.create_sheet("BD_PND") if pnd else None
    wl = wb.create_sheet("Listas")
    wc = wb.create_sheet("Calc")
    wcp = wb.create_sheet("CalcPND") if pnd else None
    wbd_rz = wb.create_sheet("BD_RFV_Razones") if rz else None
    wc_rz = wb.create_sheet("CalcRFV") if rz else None

    def nombre(n, ref):
        wb.defined_names[n] = DefinedName(n, attr_text=ref)

    # ------------------------------------------------------------ bases de datos
    wbi.append(["Tipo", "Ramo", "Serie", "Periodo", "Valor", "LI 80%", "LS 80%"])
    for tipo, ramo, serie, per, v in registros_i:
        li, ls = intervalos.get((serie, ramo, per), (None, None)) if tipo == "Proyección" else (None, None)
        wbi.append([tipo, ramo, serie, per, v, li, ls])
    n_i = wbi.max_row
    wbr.append(["Libro", "Reserva", "Concepto", "Ramo", "Periodo", "Tipo", "Valor USD", "TC"])
    for libro, reserva, conc, ramo, per, tipo, v in registros_m:
        wbr.append([libro, reserva, conc, ramo, per, tipo, v, tc.get(per)])
    n_r = wbr.max_row
    for ws, n, ref, nombre_tabla in ((wbi, n_i, f"A1:G{n_i}", "TablaIndices"), (wbr, n_r, f"A1:H{n_r}", "TablaReservas")):
        tabla = Table(displayName=nombre_tabla, ref=ref)
        tabla.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(tabla)
        ws.freeze_panes = "A2"
        for k in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(k)].width = 14
        for fila in ws.iter_rows(min_row=2, min_col=2, max_col=2):
            for c in fila:
                c.number_format = "@"
    for c in wbi["E"][1:] + wbi["F"][1:] + wbi["G"][1:]:
        c.number_format = "0.0000"
    for c in wbr["G"][1:]:
        c.number_format = "#,##0"
    for c in wbr["D"][1:]:
        c.number_format = "@"
    for n_, col in (("I_Tipo", "A"), ("I_Ramo", "B"), ("I_Serie", "C"), ("I_Per", "D"), ("I_Val", "E"),
                    ("I_LI", "F"), ("I_LS", "G")):
        nombre(n_, f"BD_Indices!${col}$2:${col}${n_i}")
    for n_, col in (("R_Res", "B"), ("R_Conc", "C"), ("R_Ramo", "D"), ("R_Per", "E"), ("R_Tipo", "F"), ("R_Val", "G")):
        nombre(n_, f"BD_Reservas!${col}$2:${col}${n_r}")

    # ------------------------------------------------------------ listas (selectores)
    conceptos = {"RRC": ["NETO", "BRUTO", "BEL", "GTO", "IRR", "MR"], "SONR": ["NETO", "BRUTO", "BEL", "IRR", "MR"],
                 "RFV": ["NETO", "BRUTO", "IRR", "RCONT"]}
    periodos_sel = rango(PRIMER_PERIODO_INDICES, fin)
    listas = {
        "L_RamosInd": ramos_i, "L_SeriesInd": INDICES + LAGS, "L_PeriodosInd": periodos_sel,
        "L_Reservas": list(conceptos), "L_Unidades": ["USD", "MXN"],
        **{f"Conceptos_{k}": v for k, v in conceptos.items()},
        **{f"Ramos_{k}": ["Todos"] + ramos_m.get(k, []) for k in conceptos},
        **{f"RamosSin_{k}": ramos_m.get(k, []) for k in conceptos},
        **({"L_RamosPnd": ["Todos"] + pnd["ramos"], "L_ResPnd": list(pnd["datos"]), "L_RamosFA": pnd["con_fa"] or ["-"]}
           if pnd else {}),
        **({"L_RamosRfv": ["Todos"] + rz["ramos"],
            "L_NotaRfv": [notas_ramo_rfv(rz, ultimo)[r] for r in ["Todos"] + rz["ramos"]],
            "L_XdefEscala": [ref_en_escala(rz, r) for r in ["Todos"] + rz["ramos"]],
            "L_PdMedida": [r == "Todos" or any((rz.get("pd_medida") or {}).get(r, []))
                           for r in ["Todos"] + rz["ramos"]]} if rz else {}),
    }
    for j, (n_, valores) in enumerate(listas.items(), start=1):
        letra = get_column_letter(j)
        wl.cell(1, j, n_).font = Font(bold=True)
        for i, v in enumerate(valores, start=2):
            c = wl.cell(i, j, v)
            if isinstance(v, str):
                c.number_format = "@"
        nombre(n_, f"Listas!${letra}$2:${letra}${len(valores) + 1}")
    j_tc = len(listas) + 2
    wl.cell(1, j_tc, "Periodo").font = Font(bold=True)
    wl.cell(1, j_tc + 1, "TC").font = Font(bold=True)
    periodos_m = rango(PRIMER_PERIODO_MONTOS, fin_m)
    for i, p in enumerate(periodos_m, start=2):
        wl.cell(i, j_tc, p)
        wl.cell(i, j_tc + 1, tc.get(p))
    lp, lt = get_column_letter(j_tc), get_column_letter(j_tc + 1)
    nombre("TC_Per", f"Listas!${lp}$2:${lp}${len(periodos_m) + 1}")
    nombre("TC_Val", f"Listas!${lt}$2:${lt}${len(periodos_m) + 1}")
    wl.sheet_state = "hidden"

    # ------------------------------------------------------------ dashboard indices
    ws = wd_i
    preparar_hoja(ws)
    ultima_col = get_column_letter(33)
    caja(ws, "B2:B46")
    ws["B3"] = "◆ ÍNDICES Y RESERVAS"
    ws["B3"].font = fuente(13, True)
    menu = [("Dashboard Índices", "'Dashboard Índices'!A1"), ("Dashboard Reservas", "'Dashboard Reservas'!A1"),
            *([(HOJA_RAZONES, f"'{HOJA_RAZONES}'!A1")] if pnd else []),
            *([(HOJA_DASH_RFV, f"'{HOJA_DASH_RFV}'!A1")] if rz else []),
            ("Análisis", "'Análisis'!A1"), ("Base de datos: índices", "'BD_Indices'!A1"),
            ("Base de datos: reservas", "'BD_Reservas'!A1")]

    def navegacion(hoja, activo):
        for k, (texto, destino) in enumerate(menu):
            c = hoja.cell(4 + k, 2, ("▸ " if texto == activo else "   ") + texto)
            c.hyperlink = Hyperlink(ref=c.coordinate, location=destino)
            c.font = fuente(10.5, texto == activo, TEXTO if texto == activo else TEXTO_2)
            c.alignment = Alignment(vertical="top")  # (una fila mas alta por un panel no separa las opciones)
            c.fill = relleno(NAV_ACTIVO if texto == activo else PANEL)
            if k == 0:
                c.border = Border(left=LADO, right=LADO, top=LADO)
            else:
                c.border = Border(left=LADO, right=LADO)

    navegacion(ws, "Dashboard Índices")

    def selector(hoja, fila, titulo, valor, formula_lista, nombre_celda, formato="@"):
        hoja.cell(fila, 2, titulo).font = fuente(9, True, TEXTO_2)
        c = hoja.cell(fila + 1, 2, valor)
        c.number_format = formato
        c.font = fuente(11, True, AZUL)
        c.fill = relleno("F4F6FB")
        c.border = Border(left=Side(style="thin", color=AZUL), right=Side(style="thin", color=AZUL),
                          top=Side(style="thin", color=AZUL), bottom=Side(style="thin", color=AZUL))
        c.alignment = Alignment(horizontal="center")
        # en el XML la formula de la validacion va sin "=" (con "=" Excel la considera dañada)
        dv = DataValidation(type="list", formula1=formula_lista.lstrip("="), allow_blank=False,
                            showDropDown=False, showErrorMessage=True)
        dv.error, dv.errorTitle = "Elige un valor de la lista", "Valor no válido"
        hoja.add_data_validation(dv)
        dv.add(c.coordinate)
        nombre(nombre_celda, f"'{hoja.title}'!${get_column_letter(c.column)}${c.row}")
        return c

    ramo_ini = "10" if "10" in ramos_i else ramos_i[0]
    selector(ws, 12, "RAMO", ramo_ini, "=L_RamosInd", "SelRamoInd")       # (renglon 11 libre: el menu llega al 10)
    selector(ws, 15, "ÍNDICE / LAG", INDICES[0], "=L_SeriesInd", "SelIndice")
    selector(ws, 18, "PERIODO (COMPARATIVO POR RAMO)", fin, "=L_PeriodosInd", "SelPeriodoInd", "0")
    notas = [f"Real hasta {etiqueta(ultimo)}", f"Proyección {etiqueta(mover(ultimo, 1))} a {etiqueta(fin)}",
             "", "Cambia los selectores (listas", "desplegables) y las gráficas", "se actualizan solas.", "",
             f"Índices: {proc.get('indice', 'n/d')}", f"LAGs: {proc.get('lag', 'n/d')}",
             nota_modelo()]
    for k, t in enumerate(notas):
        ws.cell(22 + k, 2, t).font = fuente(9, k < 2, TEXTO_2, k >= 3)

    ws["D2"] = "Dashboard de Índices de Reservas"
    ws["D2"].font = fuente(18, True)
    ws["D3"] = (f"Seguimiento mensual {etiqueta(PRIMER_PERIODO_INDICES)} a {etiqueta(ultimo)} (real) y proyección "
                f"{etiqueta(mover(ultimo, 1))} a {etiqueta(fin)} · HParametros_2026")
    ws["D3"].font = fuente(10, False, TEXTO_2)

    # KPI (formulas)
    crit = "I_Ramo,SelRamoInd,I_Serie,SelIndice"

    def valor_indice(per_expr):
        return f'IFERROR(SUMIFS(I_Val,{crit},I_Per,{per_expr})/(COUNTIFS({crit},I_Per,{per_expr})>0),NA())'

    kpis = [
        (f"Último real ({etiqueta(ultimo)})", "=" + valor_indice(ultimo), "0.0000"),
        ("Promedio real 12 meses",
         f'=IF(COUNTIFS(I_Tipo,"Real",{crit},I_Per,">"&{p_12})<12,NA(),'
         f'AVERAGEIFS(I_Val,I_Tipo,"Real",{crit},I_Per,">"&{p_12}))', "0.0000"),
        (f"Proyección {etiqueta(p_dic_actual)}", "=" + valor_indice(p_dic_actual), "0.0000"),
        (f"Proyección {etiqueta(fin)}", "=" + valor_indice(fin), "0.0000"),
        (f"Var. prom. 12 m ({etiqueta(mover(ultimo, 1))}–{etiqueta(mover(ultimo, 12))} vs "
         f"{etiqueta(mover(ultimo, -11))}–{etiqueta(ultimo)})", "", "+0.0%;-0.0%;0.0%"),
    ]
    pintar(ws, f"D5:{ultima_col}8", BANDA_KPI)
    for k, (tit, form, fmt) in enumerate(kpis):
        col = 4 + k * 6
        ws.merge_cells(start_row=5, start_column=col, end_row=6, end_column=col + 5)
        ws.merge_cells(start_row=7, start_column=col, end_row=8, end_column=col + 5)
        ws.cell(5, col, tit).font = fuente(9.5, True, TEXTO_2)
        ws.cell(5, col).alignment = Alignment(horizontal="left", vertical="bottom", indent=1)
        c = ws.cell(7, col, f'=IFERROR({form[1:]},"s/d")' if form else None)   # s/d = sin dato
        c.number_format = fmt
        c.font = fuente(20, True)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    # promedio de los proximos 12 meses proyectados contra el de los ultimos 12 reales (J7): ano contra ano, sin el
    # efecto del mes del ano
    ws.cell(7, 28).value = (f'=IF(COUNTIFS({crit},I_Per,">"&{ultimo},I_Per,"<="&{mover(ultimo, 12)})<12,"s/d",'
                            f'IFERROR(ROUND(AVERAGEIFS(I_Val,{crit},I_Per,">"&{ultimo},I_Per,"<="&{mover(ultimo, 12)})'
                            f'/J7-1,4),"s/d"))')

    # paneles
    caja(ws, "D10:S27")
    caja(ws, "U10:AG27")
    caja(ws, "D29:S46")
    caja(ws, "U29:AG46")
    ws["D10"] = '="Evolución mensual · "&SelIndice&" · Ramo "&SelRamoInd'
    ws["U10"] = (f'=SelIndice&" por ramo · "&IFERROR(INDEX(Calc!$B:$B,MATCH(SelPeriodoInd,Calc!$A:$A,0)),'
                 f'SelPeriodoInd)&IF(SelPeriodoInd>{ultimo}," (proyección)"," (real)")')
    ws["D29"] = '="Patrón de desarrollo acumulado (LAG 1-10) · Ramo "&SelRamoInd'
    ws["U29"] = '="Resumen de índices · Ramo "&SelRamoInd'
    for ref in ("D10", "U10", "D29", "U29"):
        ws[ref].font = fuente(11.5, True)
        ws[ref].alignment = Alignment(indent=1, vertical="center")
    ws.row_dimensions[10].height = 22
    ws.row_dimensions[29].height = 22

    # Calc: serie mensual del indice seleccionado
    wc["A1"], wc["B1"], wc["C1"], wc["D1"], wc["E1"], wc["F1"] = ("Periodo", "Mes", "Real", "Proyección",
                                                                  "Banda 80% inferior", "Banda 80% superior")
    per_i = rango(PRIMER_PERIODO_INDICES, fin)
    for k, p in enumerate(per_i, start=2):
        wc.cell(k, 1, p)
        wc.cell(k, 2, etiqueta(p))
        base = f"{crit},I_Per,$A{k}"
        wc.cell(k, 3, f'=IF(COUNTIFS(I_Tipo,"Real",{base})=0,NA(),SUMIFS(I_Val,I_Tipo,"Real",{base}))')
        proy = f'COUNTIFS(I_Tipo,"Proyección",{base})'
        wc.cell(k, 4, f'=IF($A{k}={ultimo},C{k},IF({proy}=0,NA(),SUMIFS(I_Val,I_Tipo,"Proyección",{base})))')
        wc.cell(k, 5, f'=IF($A{k}={ultimo},C{k},IF({proy}=0,NA(),SUMIFS(I_LI,I_Tipo,"Proyección",{base})))')
        wc.cell(k, 6, f'=IF($A{k}={ultimo},C{k},IF({proy}=0,NA(),SUMIFS(I_LS,I_Tipo,"Proyección",{base})))')
    n_ci = len(per_i) + 1
    ch = LineChart()
    ch.add_data(Reference(wc, min_col=3, max_col=6, min_row=1, max_row=n_ci), titles_from_data=True)
    ch.set_categories(Reference(wc, min_col=2, min_row=2, max_row=n_ci))
    linea(ch.series[0], AZUL, 2.0)
    linea(ch.series[1], NARANJA, 2.0, punteada=True)
    linea(ch.series[2], GRIS_BANDA, 1.0)
    linea(ch.series[3], GRIS_BANDA, 1.0)
    estilo_grafica(ch, "0.00")
    ch.x_axis.tickLblSkip = 6
    ch.x_axis.tickMarkSkip = 6
    colocar(ws, ch, "D11", "S27")

    # Calc: comparativo por ramo (seleccionado resaltado)
    wc["H1"], wc["I1"], wc["J1"], wc["K1"] = "Ramo", "Valor", "Ramo seleccionado", "Otros ramos"
    for k, ramo in enumerate(ramos_i, start=2):
        wc.cell(k, 8, ramo).number_format = "@"
        base = f'I_Ramo,$H{k},I_Serie,SelIndice,I_Per,SelPeriodoInd'
        wc.cell(k, 9, f"=IF(COUNTIFS({base})=0,NA(),SUMIFS(I_Val,{base}))")
        wc.cell(k, 10, f"=IF($H{k}=SelRamoInd,I{k},NA())")
        wc.cell(k, 11, f"=IF($H{k}<>SelRamoInd,I{k},NA())")
    n_cr = len(ramos_i) + 1
    ch = BarChart()
    ch.type, ch.grouping, ch.overlap, ch.gapWidth = "bar", "clustered", 100, 55
    ch.add_data(Reference(wc, min_col=10, max_col=11, min_row=1, max_row=n_cr), titles_from_data=True)
    ch.set_categories(Reference(wc, min_col=8, min_row=2, max_row=n_cr))
    barra(ch.series[0], AZUL)
    barra(ch.series[1], GRIS_BARRA)
    estilo_grafica(ch, "0.00")
    ch.x_axis.scaling.orientation = "maxMin"
    ch.y_axis.crosses = "max"
    colocar(ws, ch, "U11", "AG27")

    # Calc: patron de LAGs (instantaneas)
    instantaneas = [mover(ultimo, -24), mover(ultimo, -12), ultimo, fin]
    titulos = [f"{etiqueta(p)} (real)" for p in instantaneas[:3]] + [f"{etiqueta(fin)} (proyección)"]
    wc["M1"] = "LAG"
    for j, t in enumerate(titulos):
        wc.cell(1, 14 + j, t)
    for k, lag in enumerate(LAGS, start=2):
        wc.cell(k, 13, lag)
        for j, p in enumerate(instantaneas):
            base = f'I_Ramo,SelRamoInd,I_Serie,$M{k},I_Per,{p}'
            wc.cell(k, 14 + j, f"=IF(COUNTIFS({base})=0,NA(),SUMIFS(I_Val,{base}))")
    ch = LineChart()
    ch.add_data(Reference(wc, min_col=14, max_col=17, min_row=1, max_row=11), titles_from_data=True)
    ch.set_categories(Reference(wc, min_col=13, min_row=2, max_row=11))
    for s, color in zip(ch.series[:3], AZULES_ORDINALES):
        linea(s, color, 2.0)
        s.marker.symbol = "circle"
        s.marker.size = 5
        s.marker.graphicalProperties = GraphicalProperties(solidFill=color, ln=LineProperties(solidFill=color))
    linea(ch.series[3], NARANJA, 2.0, punteada=True)
    estilo_grafica(ch, "0.00")
    colocar(ws, ch, "D30", "S46")

    # Tabla resumen del ramo (formulas); cada dato ocupa 2 columnas x 2 filas de la rejilla
    cab = [("Índice", 21, 24), (f"Real\n{etiqueta(ultimo)}", 25, 26), (f"Proy.\n{etiqueta(p_dic_actual)}", 27, 28),
           (f"Proy.\n{etiqueta(fin)}", 29, 30), ("Var. prom.\n12 m", 31, 32)]
    linea_fina = Border(bottom=Side(style="thin", color=BORDE))
    for t, c1_, c2_ in cab:
        ws.merge_cells(start_row=31, start_column=c1_, end_row=31, end_column=c2_)
        cel = ws.cell(31, c1_, t)
        cel.font = fuente(9, True, TEXTO_2)
        cel.alignment = Alignment(horizontal="left" if c1_ == 21 else "right", vertical="bottom", wrap_text=True,
                                  indent=1 if c1_ == 21 else 0)
        for k in range(c1_, c2_ + 1):
            ws.cell(31, k).border = linea_fina
    ws.row_dimensions[31].height = 30
    for k, serie in enumerate(INDICES + ["LAG 1", "LAG 2", "LAG 3"]):
        f_ = 32 + k * 2
        base = f'I_Ramo,SelRamoInd,I_Serie,"{serie}"'
        forms = [serie] + [f"=IFERROR(SUMIFS(I_Val,{base},I_Per,{p})/(COUNTIFS({base},I_Per,{p})>0),NA())"
                           for p in (ultimo, p_dic_actual, fin)]
        # promedio de los proximos 12 meses proyectados contra el de los ultimos 12 reales
        # exige los 12 meses de cada lado (las series con meses faltantes quedan en #N/D, igual que en Analisis)
        forms.append(f'=IF(OR(COUNTIFS({base},I_Per,">"&{mover(ultimo, -12)},I_Per,"<="&{ultimo})<12,'
                     f'COUNTIFS({base},I_Per,">"&{ultimo},I_Per,"<="&{mover(ultimo, 12)})<12),NA(),'
                     f'IFERROR(ROUND(AVERAGEIFS(I_Val,{base},I_Per,">"&{ultimo},I_Per,"<="&{mover(ultimo, 12)})'
                     f'/AVERAGEIFS(I_Val,{base},I_Per,">"&{mover(ultimo, -12)},I_Per,"<="&{ultimo})-1,4),NA()))')
        for (_, c1_, c2_), form in zip(cab, forms):
            ws.merge_cells(start_row=f_, start_column=c1_, end_row=f_ + 1, end_column=c2_)
            cel = ws.cell(f_, c1_, form)
            cel.font = fuente(10, c1_ == 31)
            cel.number_format = "+0.0%;-0.0%;0.0%" if c1_ == 31 else "0.0000"
            cel.alignment = Alignment(horizontal="left" if c1_ == 21 else "right", vertical="center",
                                      indent=1 if c1_ == 21 else 0)
            for k2 in range(c1_, c2_ + 1):
                ws.cell(f_ + 1, k2).border = linea_fina
    ws.conditional_formatting.add(
        "AE32:AF45", ColorScaleRule(start_type="num", start_value=-0.3, start_color="6DA7EC", mid_type="num",
                                    mid_value=0, mid_color="F0EFEC", end_type="num", end_value=0.3,
                                    end_color="E66767"))
    ws.cell(46, 21, "#N/D = sin dato para ese ramo/índice").font = fuente(8, False, TEXTO_2, True)

    # ------------------------------------------------------------ dashboard reservas
    ws = wd_r
    preparar_hoja(ws)
    caja(ws, "B2:B46")
    ws["B3"] = "◆ ÍNDICES Y RESERVAS"
    ws["B3"].font = fuente(13, True)
    navegacion(ws, "Dashboard Reservas")
    selector(ws, 12, "RESERVA", "RRC", "=L_Reservas", "SelReserva")      # (renglon 11 libre: el menu llega al 10)
    selector(ws, 15, "CONCEPTO", "NETO", '=INDIRECT("Conceptos_"&SelReserva)', "SelConcepto")
    selector(ws, 18, "RAMO", "Todos", '=INDIRECT("Ramos_"&SelReserva)', "SelRamoRes")
    selector(ws, 21, "MONEDA", "USD", "=L_Unidades", "SelUnidad")
    ws["B23"] = ('=IF(AND(ISNUMBER(MATCH(SelConcepto,INDIRECT("Conceptos_"&SelReserva),0)),'
                 'ISNUMBER(MATCH(SelRamoRes,INDIRECT("Ramos_"&SelReserva),0))),"",'
                 '"⚠ Concepto o ramo no existe en "&SelReserva&": elígelo de nuevo")')
    ws["B23"].font = fuente(9, True, "B4541F")
    ws["B23"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[23].height = 26
    notas = [f"Real hasta {etiqueta(ultimo)}", f"Proyección {etiqueta(mover(ultimo, 1))} a {etiqueta(fin_m)}",
             "Cifras en millones.", "MXN = USD × TC del mes", "(TC FCST de Inversiones).", "",
             f"Montos: {proc.get('nivel', 'n/d')}", f"Razones: {proc.get('razon', 'n/d')}",
             "NETO = BRUTO - IRR"]
    for k, t in enumerate(notas):
        ws.cell(25 + k, 2, t).font = fuente(9, k < 2, TEXTO_2, k >= 3)
    ws["D2"] = "Dashboard de Reservas: Real y Proyección"
    ws["D2"].font = fuente(18, True)
    ws["D3"] = (f"RRC y SONR (Daños) y RFV (Fianzas) por concepto y ramo · real {etiqueta(PRIMER_PERIODO_MONTOS)} "
                f"a {etiqueta(ultimo)} y proyección {etiqueta(mover(ultimo, 1))} a {etiqueta(fin_m)}")
    ws["D3"].font = fuente(10, False, TEXTO_2)

    wc["X1"] = '=IF(SelRamoRes="Todos","*",SelRamoRes)'
    nombre("CritRamoRes", "Calc!$X$1")
    unidad = 'IF(SelUnidad="MXN",INDEX(TC_Val,MATCH({p},TC_Per,0)),1)'

    def monto(conc_expr, per_expr, ramo_expr="CritRamoRes"):
        base = f"R_Res,SelReserva,R_Conc,{conc_expr},R_Ramo,{ramo_expr},R_Per,{per_expr}"
        return (f"IF(COUNTIFS({base})=0,NA(),SUMIFS(R_Val,{base})*{unidad.format(p=per_expr)}/1000000)")

    pintar(ws, f"D5:{ultima_col}8", BANDA_KPI)
    kpis_r = [
        ('="Real "&"' + etiqueta(ultimo) + '"&" (M "&SelUnidad&")"', "=" + monto("SelConcepto", ultimo), "#,##0.0"),
        (f'="Proy. {etiqueta(p_dic_actual)} (M "&SelUnidad&")"', "=" + monto("SelConcepto", p_dic_actual), "#,##0.0"),
        (f'="Proy. {etiqueta(fin_m)} (M "&SelUnidad&")"', "=" + monto("SelConcepto", fin_m), "#,##0.0"),
        ("Crec. anual proyectado", f"=IFERROR((P7/D7)^(12/{len(rango(ultimo, fin_m)) - 1})-1,NA())",
         "+0.0%;-0.0%;0.0%"),
        ("Crec. real 12 meses",
         f"=IFERROR(D7/({monto('SelConcepto', p_12)})-1,NA())", "+0.0%;-0.0%;0.0%"),
    ]
    for k, (tit, form, fmt) in enumerate(kpis_r):
        col = 4 + k * 6
        ws.merge_cells(start_row=5, start_column=col, end_row=6, end_column=col + 5)
        ws.merge_cells(start_row=7, start_column=col, end_row=8, end_column=col + 5)
        ws.cell(5, col, tit).font = fuente(9.5, True, TEXTO_2)
        ws.cell(5, col).alignment = Alignment(horizontal="left", vertical="bottom", indent=1)
        c = ws.cell(7, col, f'=IFERROR({form[1:]},"s/d")' if form else None)   # s/d = sin dato
        c.number_format = fmt
        c.font = fuente(20, True)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    # En USD y MXN el % cedido es el mismo
    ws["D9"] = (f'="% cedido (IRR/BRUTO) {etiqueta(fin_m)}: "&IFERROR(TEXT({monto(chr(34) + "IRR" + chr(34), fin_m)}/'
                f'{monto(chr(34) + "BRUTO" + chr(34), fin_m)},"0.0%"),"n/d")&"   ·   '
                f'% cedido {etiqueta(ultimo)}: "&IFERROR(TEXT({monto(chr(34) + "IRR" + chr(34), ultimo)}/'
                f'{monto(chr(34) + "BRUTO" + chr(34), ultimo)},"0.0%"),"n/d")')
    ws["D9"].font = fuente(9.5, True, TEXTO_2)

    caja(ws, "D11:S27")
    caja(ws, "U11:AG27")
    caja(ws, "D29:S46")
    caja(ws, "U29:AG46")
    ws["D11"] = f'=SelReserva&" "&SelConcepto&" mensual {etiqueta(PRIMER_PERIODO_MENSUAL)}-{etiqueta(fin_m)} · Ramo "&SelRamoRes&" (M "&SelUnidad&")"'
    ws["U11"] = f'=SelReserva&" "&SelConcepto&" por ramo · {etiqueta(ultimo)} vs {etiqueta(fin_m)} (M "&SelUnidad&")"'
    ws["D29"] = f'=SelReserva&" "&SelConcepto&" histórico y proyección · Ramo "&SelRamoRes&" (M "&SelUnidad&")"'
    ws["U29"] = f'=SelReserva&" por concepto · {etiqueta(ultimo)} vs {etiqueta(fin_m)} · Ramo "&SelRamoRes&" (M "&SelUnidad&")"'
    for ref in ("D11", "U11", "D29", "U29"):
        ws[ref].font = fuente(11.5, True)
        ws[ref].alignment = Alignment(indent=1, vertical="center")
    ws.row_dimensions[11].height = 22
    ws.row_dimensions[29].height = 22

    # Calc: serie mensual de reservas
    c0 = 25   # columna Y
    for j, t in enumerate(["Periodo", "Mes", "Monto", "Real", "Proyección", "Proyección (columnas)"]):
        wc.cell(1, c0 + j, t)
    per_m = rango(PRIMER_PERIODO_MONTOS, fin_m)
    for k, p in enumerate(per_m, start=2):
        L = get_column_letter
        wc.cell(k, c0, p)
        wc.cell(k, c0 + 1, etiqueta(p))
        wc.cell(k, c0 + 2, "=" + monto("SelConcepto", f"${L(c0)}{k}"))
        m = f"{L(c0 + 2)}{k}"
        wc.cell(k, c0 + 3, f"=IF(${L(c0)}{k}<={ultimo},{m},NA())")
        wc.cell(k, c0 + 4, f"=IF(${L(c0)}{k}>={ultimo},{m},NA())")
        wc.cell(k, c0 + 5, f"=IF(${L(c0)}{k}>{ultimo},{m},NA())")
    n_m = len(per_m) + 1
    k_ini = per_m.index(PRIMER_PERIODO_MENSUAL) + 2 if PRIMER_PERIODO_MENSUAL in per_m else 2
    ch = BarChart()
    ch.type, ch.grouping, ch.overlap, ch.gapWidth = "col", "clustered", 100, 45
    real = Reference(wc, min_col=c0 + 3, min_row=k_ini, max_row=n_m)
    proy = Reference(wc, min_col=c0 + 5, min_row=k_ini, max_row=n_m)
    s_real, s_proy = Series(real), Series(proy)
    s_real.tx = SeriesLabel(v="Real")
    s_proy.tx = SeriesLabel(v="Proyección")
    ch.series.extend([s_real, s_proy])
    ch.set_categories(Reference(wc, min_col=c0 + 1, min_row=k_ini, max_row=n_m))
    barra(ch.series[0], AZUL)
    barra(ch.series[1], NARANJA)
    estilo_grafica(ch, "#,##0")
    ch.x_axis.tickLblSkip = 3
    colocar(ws, ch, "D12", "S27")

    ch = LineChart()
    ch.add_data(Reference(wc, min_col=c0 + 3, max_col=c0 + 4, min_row=1, max_row=n_m), titles_from_data=True)
    ch.set_categories(Reference(wc, min_col=c0 + 1, min_row=2, max_row=n_m))
    linea(ch.series[0], AZUL, 2.0)
    linea(ch.series[1], NARANJA, 2.0, punteada=True)
    estilo_grafica(ch, "#,##0")
    ch.x_axis.tickLblSkip = 6
    ch.x_axis.tickMarkSkip = 6
    colocar(ws, ch, "D30", "S46")

    # Calc: por ramo (lista dependiente de la reserva)
    c1 = 32   # AF
    for j, t in enumerate(["Ramo", f"{etiqueta(ultimo)} (real)", f"{etiqueta(fin_m)} (proyección)"]):
        wc.cell(1, c1 + j, t)
    max_ramos = max(len(v) for v in ramos_m.values())
    for k in range(2, max_ramos + 2):
        L = get_column_letter
        wc.cell(k, c1, f'=IFERROR(INDEX(INDIRECT("RamosSin_"&SelReserva),{k - 1}),"")')
        r_ = f"{L(c1)}{k}"
        wc.cell(k, c1 + 1, f'=IF({r_}="",NA(),{monto("SelConcepto", ultimo, r_)})')
        wc.cell(k, c1 + 2, f'=IF({r_}="",NA(),{monto("SelConcepto", fin_m, r_)})')
    ch = BarChart()
    ch.type, ch.grouping, ch.gapWidth = "bar", "clustered", 50
    ch.add_data(Reference(wc, min_col=c1 + 1, max_col=c1 + 2, min_row=1, max_row=max_ramos + 1), titles_from_data=True)
    ch.set_categories(Reference(wc, min_col=c1, min_row=2, max_row=max_ramos + 1))
    barra(ch.series[0], AZUL)
    barra(ch.series[1], NARANJA)
    estilo_grafica(ch, "#,##0")
    ch.x_axis.scaling.orientation = "maxMin"
    ch.y_axis.crosses = "max"
    colocar(ws, ch, "U12", "AG27")

    # Calc: por concepto
    c2 = 36   # AJ
    for j, t in enumerate(["Concepto", f"{etiqueta(ultimo)} (real)", f"{etiqueta(fin_m)} (proyección)"]):
        wc.cell(1, c2 + j, t)
    for k in range(2, 8):
        L = get_column_letter
        wc.cell(k, c2, f'=IFERROR(INDEX(INDIRECT("Conceptos_"&SelReserva),{k - 1}),"")')
        cc = f"{L(c2)}{k}"
        wc.cell(k, c2 + 1, f'=IF({cc}="",NA(),{monto(cc, ultimo)})')
        wc.cell(k, c2 + 2, f'=IF({cc}="",NA(),{monto(cc, fin_m)})')
    ch = BarChart()
    ch.type, ch.grouping, ch.gapWidth = "col", "clustered", 60
    ch.add_data(Reference(wc, min_col=c2 + 1, max_col=c2 + 2, min_row=1, max_row=7), titles_from_data=True)
    ch.set_categories(Reference(wc, min_col=c2, min_row=2, max_row=7))
    barra(ch.series[0], AZUL)
    barra(ch.series[1], NARANJA)
    estilo_grafica(ch, "#,##0")
    colocar(ws, ch, "U30", "AG46")
    wc.sheet_state = "hidden"

    if pnd:
        construir_pnd(wd_p, wbp, wcp, pnd, ultimo, p_dic_actual, nombre, selector, navegacion)
    if rz:
        construir_razones_rfv(wd_rz, wbd_rz, wc_rz, rz, ultimo, p_dic_actual, nombre, selector, navegacion)

    # ------------------------------------------------------------ analisis (valores)
    construir_analisis(wa, registros_i, ramos_i, registros_m, ultimo, p_dic_actual, fin, fin_m, p_12, metodo)
    for hoja, area in ((wd_i, "A1:AH47"), (wd_r, "A1:AH47"), *([(wd_p, "A1:AH124")] if wd_p else []),
                       *([(wd_rz, f"A1:AH{FILAS_HOJA_RFV}")] if wd_rz else []), (wa, None)):
        hoja.sheet_properties.tabColor = "8EA9DB"
        hoja.page_setup.orientation = "landscape"
        hoja.page_setup.paperSize = hoja.PAPERSIZE_LETTER
        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.page_setup.fitToWidth = 1
        hoja.page_setup.fitToHeight = 1 if area and hoja not in (wd_p, wd_rz) else 0
        hoja.print_options.horizontalCentered = True
        hoja.page_margins.left = hoja.page_margins.right = 0.3
        hoja.page_margins.top = hoja.page_margins.bottom = 0.4
        if area:
            hoja.print_area = area
    for hoja in (wd_p, wd_rz):                 # Razones y Razones RFV: hojas carta con cortes entre paneles
        if hoja is not None:                   # (sin partir graficas; la RFV con una cuarta de prima base)
            hoja.sheet_properties.pageSetUpPr.fitToPage = False
            hoja.page_setup.scale = 62
            for fila in (46, 84) + ((116,) if hoja is wd_rz else ()):
                hoja.row_breaks.append(Break(id=fila))
    wd_i.sheet_view.tabSelected = True
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True
    clasificar(wb)
    guardar_libro(wb, ruta_salida)
    print(f"   Dashboard: {ruta_salida.name}", flush=True)
    return ruta_salida


def construir_pnd(ws, wbp, wcp, pnd: dict, ultimo: int, p_dic: int, nombre, selector, navegacion) -> None:
    """Hoja HOJA_RAZONES: selectores de ramo (con "Todos") y reserva, indicadores y una grafica de lineas (real y
    proyeccion) por indicador de INDICADORES_PND. Los datos van en BD_PND (valores de leer_indicadores_ramo, con
    "Todos" ya agregado) y las series en CalcPND con formulas (INDEX / MATCH por reserva, ramo y periodo), asi las
    graficas se actualizan al cambiar los selectores; un dato que no hay va como #N/D (hueco en la linea)."""
    periodos, cols = pnd["periodos"], [c for c, _, _ in INDICADORES_PND]
    # ---- base de datos
    wbp.append(["Clave", "Reserva", "Ramo", "Periodo", "Tipo"] + cols)
    for res, por_ramo in pnd["datos"].items():
        for ramo in ["Todos"] + pnd["ramos"]:
            if ramo not in por_ramo:
                continue
            for i, p in enumerate(periodos):
                wbp.append([f"{res}|{ramo}|{p}", res, ramo, p, "Real" if p <= ultimo else "Proyección"]
                           + [por_ramo[ramo][c][i] for c in cols])
    n_p = wbp.max_row
    tabla = Table(displayName="TablaPND", ref=f"A1:{get_column_letter(5 + len(cols))}{n_p}")
    tabla.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    wbp.add_table(tabla)
    wbp.freeze_panes = "B2"
    unidad = {c: u for c, _, u in INDICADORES_PND}
    for k in range(1, 6 + len(cols)):
        wbp.column_dimensions[get_column_letter(k)].width = 14
    for fila in wbp.iter_rows(min_row=2, min_col=3, max_col=3):
        for c in fila:
            c.number_format = "@"
    for j, c_ in enumerate(cols, start=6):
        fmt = {"monto": "#,##0", "pct": "0.00%", "fnd": "0.0000"}[unidad[c_]]
        for fila in wbp.iter_rows(min_row=2, min_col=j, max_col=j):
            for c in fila:
                c.number_format = fmt
    nombre("P_Clave", f"BD_PND!$A$2:$A${n_p}")
    for j, c_ in enumerate(cols, start=6):
        letra = get_column_letter(j)
        nombre(f"P_{j - 5}", f"BD_PND!${letra}$2:${letra}${n_p}")

    # ---- hoja
    preparar_hoja(ws, filas=124)
    caja(ws, "B2:B46")
    ws["B3"] = "◆ ÍNDICES Y RESERVAS"
    ws["B3"].font = fuente(13, True)
    navegacion(ws, HOJA_RAZONES)
    selector(ws, 12, "RAMO", "Todos", "=L_RamosPnd", "SelRamoPnd")
    selector(ws, 15, "RESERVA", "RRC", "=L_ResPnd", "SelResPnd")
    notas = [f"Real hasta {etiqueta(ultimo)}", f"Proyección {etiqueta(mover(ultimo, 1))} a {etiqueta(periodos[-1])}", "",
             "RRC: PND · SONR: PD", "Mismos valores que los bloques de la BD de Daños.", "",
             "Todos los ramos: en cada mes, los ramos con PND / PD; montos sumados, factores e índices ponderados "
             "por el PND / PD (CESIÓN por el BRUTO).",
             *[f"No entran a Todos en {res}: {txt}." for res, txt in pnd.get("faltan", {}).items() if txt],
             *[f"{res} {', '.join(rs)}: SAP registra 0; la proyección sale de la historia del método del área "
               "(Res_Rvas)." for res, rs in (pnd.get("metodo_area") or {}).items() if rs],
             *[f"{res} {', '.join(fs)}: SAP registra 0 y no se pudo usar el método del área (ver Alertas del "
               "diagnóstico): sigue en 0." for res, fs in (pnd.get("falla_area") or {}).items() if fs], "",
             f"#N/D = sin dato: IS (FA) antes de {etiqueta(mover(ultimo, 1))} o en ramos que FA no manda; SONR sin GTO; "
             "una razón cuyo denominador es casi 0."]
    fila = 19
    for k, t in enumerate(notas):                    # (renglones cortos: la rejilla de la hoja no cambia de alto)
        for linea_ in textwrap.wrap(t, 31) or [""]:
            ws.cell(fila, 2, linea_).font = fuente(9, k < 2, TEXTO_2, k >= 3)
            fila += 1
    ws["D2"] = "Dashboard de Razones: PND / PD y sus indicadores por ramo"
    ws["D2"].font = fuente(18, True)
    ws["D3"] = (f"Real {etiqueta(periodos[0])} a {etiqueta(ultimo)} y proyección {etiqueta(mover(ultimo, 1))} a "
                f"{etiqueta(periodos[-1])} · BD_Montos_RRC_SONR (Daños) · versión del código {version_codigo()}")
    ws["D3"].font = fuente(10, False, TEXTO_2)

    # ---- CalcPND: una columna Real y una Proyeccion por indicador
    wcp["A1"], wcp["B1"], wcp["C1"] = "Periodo", "Mes", "Renglon en BD_PND"
    esc = {"monto": 1e-6, "pct": 1, "fnd": 1}
    fila_de = {}
    for k, p in enumerate(periodos, start=2):
        fila_de[p] = k
        wcp.cell(k, 1, p)
        wcp.cell(k, 2, etiqueta(p))
        wcp.cell(k, 3, f'=IFERROR(MATCH(SelResPnd&"|"&SelRamoPnd&"|"&$A{k},P_Clave,0),0)')
    col_real = {}
    for j, c_ in enumerate(cols):
        cr, cp = 4 + 2 * j, 5 + 2 * j
        col_real[c_] = cr
        wcp.cell(1, cr, "Real")
        wcp.cell(1, cp, "Proyección")
        rng, f = f"P_{j + 1}", esc[unidad[c_]]
        fmt = {"monto": "#,##0.0", "pct": "0.0%", "fnd": "0.000"}[unidad[c_]]
        # IS (FA): la historia real es el IS (RL) y la proyeccion de FA arranca del ultimo real del IS (RL)
        rng_real = f"P_{cols.index('IS (RL)') + 1}" if c_ == "IS (FA)" and "IS (RL)" in cols else rng
        for k, p in enumerate(periodos, start=2):
            def v(r):
                return f'IF($C{k}=0,NA(),IF(INDEX({r},$C{k})="",NA(),INDEX({r},$C{k}){"/1000000" if f == 1e-6 else ""}))'
            wcp.cell(k, cr, f"=IF($A{k}>{ultimo},NA(),{v(rng_real)})").number_format = fmt
            proy = v(rng) if rng_real == rng else f"IF($A{k}={ultimo},{v(rng_real)},{v(rng)})"
            wcp.cell(k, cp, f"=IF($A{k}<{ultimo},NA(),{proy})").number_format = fmt
    n_c = len(periodos) + 1
    wcp.sheet_state = "hidden"

    # ---- indicadores (PND / PD)
    L = get_column_letter
    cpnd = col_real["PND/PD"]
    nb = 'IF(SelResPnd="RRC","PND","PD")'
    p12 = mover(ultimo, 12)
    kpis = [
        (f'={nb}&" real {etiqueta(ultimo)} (M USD)"', f"=CalcPND!{L(cpnd)}{fila_de[ultimo]}", "#,##0.0"),
        (f'={nb}&" proyección {etiqueta(p_dic)} (M USD)"', f"=CalcPND!{L(cpnd + 1)}{fila_de.get(p_dic, n_c)}", "#,##0.0"),
        (f'={nb}&" proyección {etiqueta(periodos[-1])} (M USD)"', f"=CalcPND!{L(cpnd + 1)}{n_c}", "#,##0.0"),
        (f'="Crec. "&{nb}&" {etiqueta(ultimo)} a {etiqueta(p12)}"',
         f"=CalcPND!{L(cpnd + 1)}{fila_de.get(p12, n_c)}/CalcPND!{L(cpnd)}{fila_de[ultimo]}-1", "+0.0%;-0.0%;0.0%"),
    ]
    pintar(ws, "D5:AG8", BANDA_KPI)
    for k, (tit, form, fmt) in enumerate(kpis):
        col = 4 + k * 8                                  # D:J, L:R, T:Z, AB:AG
        fin_col = min(col + 6, 33)
        ws.merge_cells(start_row=5, start_column=col, end_row=6, end_column=fin_col)
        ws.merge_cells(start_row=7, start_column=col, end_row=8, end_column=fin_col)
        ws.cell(5, col, tit).font = fuente(9.5, True, TEXTO_2)
        ws.cell(5, col).alignment = Alignment(horizontal="left", vertical="bottom", indent=1)
        c = ws.cell(7, col, f'=IFERROR({form[1:]},"s/d")')
        c.number_format = fmt
        c.font = fuente(20, True)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # ---- paneles y graficas
    ramo_txt = 'IF(SelRamoPnd="Todos","todos los ramos","ramo "&SelRamoPnd)'
    titulos = {
        "PND/PD": f'=IF(SelResPnd="RRC","PND (RRC)","PD (SONR)")&" · "&{ramo_txt}&" · M USD"' + "".join(
            f'&IF(AND(SelResPnd="{res}",OR({",".join(f"SelRamoPnd={chr(34)}{r}{chr(34)}" for r in rs)}))," · BEL / IS (FA) en la proyección","")'
            for res, rs in (pnd.get("is_fa_bel") or {}).items() if rs),
        "FACTOR GTO": f'=IF(SelResPnd="RRC","FACTOR GTO (GTO / PND) · "&{ramo_txt},"FACTOR GTO · "&SelResPnd&" no lleva GTO (solo RRC)")',
        "FACTOR MR": f'="FACTOR MR (MR / "&{nb}&") · "&{ramo_txt}',
        "CESION": f'="CESIÓN (IRR / BRUTO) · "&{ramo_txt}',
        "FD/FND": f'=IF(SelResPnd="RRC","FND (PND / PEACUMULADA)","FD (PD / PEACUMULADA)")&" · "&{ramo_txt}',
        "IS (RL)": f'="IS (RL): "&IF(SelResPnd="RRC","Ind Sin RRC","Ind Sin SONR Media")&" de HParametros · "&{ramo_txt}',
        "IS (FA)": (f'=IF(INDEX(L_RamosFA,1)="-","IS (FA): no se cargó el archivo de la función actuarial",'
                    f'"IS (FA): real = IS (RL); proyección = función actuarial · "&{ramo_txt}&IF(SelRamoPnd="Todos"," (solo los ramos de FA)",'
                    f'IF(ISNUMBER(MATCH(SelRamoPnd,L_RamosFA,0)),""," · FA no manda este ramo")))'),
        "PE FCST": f'="PE FCST (prima tomada del mes) · "&{ramo_txt}&" · M USD"',
        "PRIMA N AÑOS": f'="PRIMA N AÑOS ({pnd.get("meses_n", 12)} meses de PE) · "&{ramo_txt}&" · M USD"',
        "PEACUMULADA": (f'="PEACUMULADA · "&{ramo_txt}&IF(SelResPnd="RRC"," (en RRC = PRIMA N AÑOS)",'
                        f'" (LAG 1 a {pnd.get("anios_lag", {}).get("SONR", 1)} × PRIMA N AÑOS)")&" · M USD"'),
    }
    for j, c_ in enumerate(cols):
        fila0 = 10 + 19 * ((j + 1) // 2) if 0 < j < len(cols) - 1 else (10 if j == 0 else 10 + 19 * ((len(cols) - 1) // 2 + 1))
        ancha = j in (0, len(cols) - 1)
        izq = ancha or j % 2 == 1
        c1, c2 = ("D", "AG") if ancha else (("D", "S") if izq else ("U", "AG"))
        caja(ws, f"{c1}{fila0}:{c2}{fila0 + 17}")
        ws[f"{c1}{fila0}"] = titulos[c_]
        ws[f"{c1}{fila0}"].font = fuente(11.5, True)
        ws[f"{c1}{fila0}"].alignment = Alignment(indent=1, vertical="center")
        ws.row_dimensions[fila0].height = 22
        cr = col_real[c_]
        ch = LineChart()
        ch.add_data(Reference(wcp, min_col=cr, max_col=cr + 1, min_row=1, max_row=n_c), titles_from_data=True)
        ch.set_categories(Reference(wcp, min_col=2, min_row=2, max_row=n_c))
        linea(ch.series[0], AZUL, 2.0)
        linea(ch.series[1], NARANJA, 2.0, punteada=True)
        estilo_grafica(ch, {"monto": "#,##0", "pct": "0%", "fnd": "0.00"}[unidad[c_]])
        if unidad[c_] == "pct":
            ch.y_axis.number_format = "0.0%" if c_ in ("FACTOR GTO", "FACTOR MR") else "0%"
        ch.x_axis.tickLblSkip = 6
        ch.x_axis.tickMarkSkip = 6
        colocar(ws, ch, f"{c1}{fila0 + 1}", f"{c2}{fila0 + 17}")


def construir_razones_rfv(ws, wbd, wcr, rz: dict, ultimo: int, p_dic: int, nombre, selector, navegacion) -> None:
    """Hoja HOJA_DASH_RFV: selector de ramo (con "Todos"), indicadores, una grafica de lineas (real, proyeccion y, si
    la hay, la serie de referencia en gris) por razon de INDICADORES_RFV y la tabla de los factores constantes del ramo.
    Los datos van en BD_RFV_Razones (valores de la hoja RFV_Razones del diagnostico, los mismos de la BD de RFV) y las
    series en CalcRFV con INDEX / MATCH por ramo y periodo; un dato que no hay va como #N/D (hueco en la linea)."""
    periodos = rz["periodos"]
    cols = [c for c, _, _, _ in INDICADORES_RFV]
    refs = [g for _, _, _, g in INDICADORES_RFV if g]
    todas = cols + refs + list(FACTORES_RFV_TABLA)
    unidad = {c: u for c, _, u, _ in INDICADORES_RFV}
    unidad.update({g: unidad[c] for c, _, _, g in INDICADORES_RFV if g})
    unidad.update({f: "pct" for f in FACTORES_RFV_TABLA if f not in ("OMEGA", "ALFA")})
    unidad.update({"OMEGA": "pct", "ALFA": "pct"})
    fmt_bd = {"mxn": "#,##0", "pct": "0.00%", "pct3": "0.000%", "razon": "0.0000"}
    # ---- base de datos
    wbd.append(["Clave", "Ramo", "Periodo", "Tipo"] + todas + ["PD medida", "Origen de la PD", "Origen del MA"])
    for ramo in ["Todos"] + rz["ramos"]:
        if ramo not in rz["datos"]:
            continue
        for i, p in enumerate(periodos):
            wbd.append([f"{ramo}|{p}", ramo, p, "Real" if p <= ultimo else "Proyección"]
                       + [rz["datos"][ramo][c][i] for c in todas]
                       + ["si" if (rz.get("pd_medida") or {}).get(ramo, [False] * len(periodos))[i] else "no",
                          (rz.get("pd_origen") or {}).get(ramo, [""] * len(periodos))[i],
                          (rz.get("origen_ma") or {}).get(ramo, [""] * len(periodos))[i]])
    n_d = wbd.max_row
    tabla = Table(displayName="TablaRazonesRFV", ref=f"A1:{get_column_letter(7 + len(todas))}{n_d}")
    tabla.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    wbd.add_table(tabla)
    wbd.freeze_panes = "B2"
    for k in range(1, 8 + len(todas)):
        wbd.column_dimensions[get_column_letter(k)].width = 15
    for fila in wbd.iter_rows(min_row=2, min_col=2, max_col=2):
        for c in fila:
            c.number_format = "@"
    col_bd = {}
    for j, c_ in enumerate(todas, start=5):
        col_bd[c_] = j
        for fila in wbd.iter_rows(min_row=2, min_col=j, max_col=j):
            for c in fila:
                c.number_format = fmt_bd[unidad[c_]]
        letra = get_column_letter(j)
        nombre(f"RF_{j - 4}", f"BD_RFV_Razones!${letra}$2:${letra}${n_d}")
    nombre("RF_Clave", f"BD_RFV_Razones!$A$2:$A${n_d}")
    letra_pdm = get_column_letter(5 + len(todas))
    nombre("RF_PDM", f"BD_RFV_Razones!${letra_pdm}$2:${letra_pdm}${n_d}")
    rango_de = {c_: f"RF_{col_bd[c_] - 4}" for c_ in todas}

    # ---- hoja
    preparar_hoja(ws, filas=FILAS_HOJA_RFV)
    caja(ws, "B2:B48")
    ws["B3"] = "◆ ÍNDICES Y RESERVAS"
    ws["B3"].font = fuente(13, True)
    navegacion(ws, HOJA_DASH_RFV)
    selector(ws, 12, "RAMO", "Todos", "=L_RamosRfv", "SelRamoRfv")
    split = ", ".join(rz.get("split") or []) or "ninguno"
    info = ", ".join(ramos_ma_informativa(rz)) or "ninguno"
    est = [p for i, p in enumerate(periodos) if (rz.get("ma_estimado") or {}).get("Todos", [False] * len(periodos))[i]]
    proy_r = sorted((r for r, v in (rz.get("origen_ma") or {}).items() if r != "Todos"
                     and any(o.startswith("Proyectado") for o in v)), key=lambda x: int(x) if x.isdigit() else 0)
    o_proy = next((o for v in (rz.get("origen_ma") or {}).values() for o in v if o.startswith("Proyectado")), "")
    nota_ma = "; ".join(x for x in [
        f"estimado del área {texto_meses(est)}" if est else "",
        f"interpolado (el CSV no trae esos meses) {texto_meses(rz['ma_interpolado'])}" if rz.get("ma_interpolado") else "",
        (f"2027 {'por tendencia' if 'tendencia' in o_proy else 'sigue a la prima' if 'PRIMA' in o_proy else 'proyectado'} "
         f"en {', '.join(proy_r)}, fijo en los demás" if proy_r else "2027 fijo en el último mes del CSV")
        if rz.get("ma_proyectado") or est else ""] if x)
    huecos = texto_meses(rz.get("ma_huecos") or [])
    con_fv = [i for d in rz["datos"].values() for i, v in enumerate(d["FV"]) if v is not None]
    fv_h = [p for p in (rz.get("ma_huecos") or []) if con_fv and p >= periodos[min(con_fv)]]   # meses de FV sin MA
    notas = [f"Real hasta {etiqueta(ultimo)}", f"Proyección {etiqueta(mover(ultimo, 1))} a {etiqueta(periodos[-1])}", "",
             "Valores de los bloques de la BD de RFV. Montos en M MXN."
             + (" Proyección como saldo: reserva anterior − liberación + la de la prima nueva."
                if any(str(d.get("modelo_frv") or "").startswith("saldo") for d in (rz.get("tendencia") or {}).values())
                else ""),
             f"MA aparte en {split}; en {info}, la RFV MA es informativa.",
             "Todos: razón de las sumas. Su PD pondera la de cada ramo por su reserva cedida.",
             *([f"MA: {nota_ma}."] if nota_ma else []),
             "Gris: FRV residual, RC PRIMA y PD de xDefault (fuera de la gráfica si es más de "
             f"{ESCALA_REF_RFV} veces mayor o menor que la PD). PD de un ramo: azul = medida en Res_Rvas, naranja = la última "
             "medida, fija; sin medida, la referencia de xDefault (prima cedida 24 m), fija.", "",
             f"#N/D = sin dato: FV antes de {etiqueta(periodos[min(con_fv)]) if con_fv else 'ene-26'}"
             + (f"; MA, RFV MA y FRV residual en {huecos} (el CSV no los trae" + (f"; por eso tampoco hay FV de {split} ni de "
                f"Todos en {texto_meses(fv_h)})" if fv_h else ")") if huecos else "")
             + (f"; PD de xDefault después de {etiqueta(rz['xdefault_hasta'])}" if rz.get("xdefault_hasta") else "")
             + "; RC PRIMA sin la cedida del reforecast."]
    fila = 15
    for k, t in enumerate(notas):
        for linea_ in textwrap.wrap(t, 31) or [""]:
            ws.cell(fila, 2, linea_).font = fuente(9, k < 2, TEXTO_2, k >= 3)
            fila += 1
    if fila > 49:
        print(f"   Aviso: las notas de {HOJA_DASH_RFV} llegan al renglón {fila - 1} (el panel lateral termina en el 48)",
              flush=True)
    ws.merge_cells("D9:AG9")                         # el monto afianzado del ramo elegido (texto de L_NotaRfv; un
    ws["D9"] = '=IFERROR(INDEX(L_NotaRfv,MATCH(SelRamoRfv,L_RamosRfv,0)),"")'   # renglon: la fila 9 es del menu)
    ws["D9"].font = fuente(9, True, TEXTO_2)
    ws["D9"].alignment = Alignment(vertical="center", indent=1)
    ws["D2"] = "Dashboard de Razones RFV: factores de la reserva de Fianzas en Vigor por ramo"
    ws["D2"].font = fuente(18, True)
    ws["D3"] = (f"Real {etiqueta(periodos[0])} a {etiqueta(ultimo)} y proyección {etiqueta(mover(ultimo, 1))} a "
                f"{etiqueta(periodos[-1])} · hoja RFV_Razones del diagnóstico (BD de RFV) · versión del código "
                f"{version_codigo()}")
    ws["D3"].font = fuente(10, False, TEXTO_2)

    # ---- CalcRFV: Real, Proyeccion y Referencia por razon
    wcr["A1"], wcr["B1"], wcr["C1"] = "Periodo", "Mes", "Renglon en BD_RFV_Razones"
    fila_de = {}
    for k, p in enumerate(periodos, start=2):
        fila_de[p] = k
        wcr.cell(k, 1, p)
        wcr.cell(k, 2, etiqueta(p))
        wcr.cell(k, 3, f'=IFERROR(MATCH(SelRamoRfv&"|"&$A{k},RF_Clave,0),0)')
    col_real, col_ref = {}, {}
    cc = 4
    n_c = len(periodos) + 1
    fmt_c = {"mxn": "#,##0.0", "pct": "0.0%", "pct3": "0.000%", "razon": "0.000"}
    todos_sel = 'SelRamoRfv="Todos"'
    L = get_column_letter
    for c_, _, u, g in INDICADORES_RFV:
        col_real[c_] = cc
        es_pd = c_ == "PD"
        # un ramo: azul = PD medida en Res_Rvas, naranja = la ultima medida, fija; Todos: real y proyeccion por mes (su
        # PD pondera la de cada ramo por su reserva cedida y cambia con la mezcla)
        pdmed = "IFERROR(INDEX(L_PdMedida,MATCH(SelRamoRfv,L_RamosRfv,0)),TRUE)"
        wcr.cell(1, cc, f'=IF({todos_sel},"Real",IF({pdmed},"Medida (Res_Rvas)","Sin PD medida"))' if es_pd else "Real")
        wcr.cell(1, cc + 1, f'=IF({todos_sel},"Proyección",IF({pdmed},"Última medida, fija",'
                            f'"Referencia (xDefault del área, prima cedida 24 m), fija"))' if es_pd else "Proyección")
        div = "/1000000" if u == "mxn" else ""
        for k, p in enumerate(periodos, start=2):
            def v(rng, _k=k, _div=div):
                return f'IF($C{_k}=0,NA(),IF(INDEX({rng},$C{_k})="",NA(),INDEX({rng},$C{_k}){_div}))'
            real = f"IF($A{k}>{ultimo},NA(),{v(rango_de[c_])})"
            proy = f"IF($A{k}<{ultimo},NA(),{v(rango_de[c_])})"
            if es_pd:
                med = f'IFERROR(INDEX(RF_PDM,$C{k})="si",FALSE)'
                sig = f'IFERROR(INDEX(RF_PDM,$C{k + 1})="si",TRUE)' if k < n_c else "TRUE"
                real = f"IF({todos_sel},{real},IF({med},{v(rango_de[c_])},NA()))"
                proy = f"IF({todos_sel},{proy},IF(OR(NOT({med}),NOT({sig})),{v(rango_de[c_])},NA()))"
            wcr.cell(k, cc, f"={real}").number_format = fmt_c[u]
            wcr.cell(k, cc + 1, f"={proy}").number_format = fmt_c[u]
        if g:
            col_ref[c_] = cc + 2
            gr = f"{L(cc + 2)}2:{L(cc + 2)}{n_c}"
            if es_pd:                                # columna cc + 3: la PD de xDefault de todos los meses
                cruda = f"{L(cc + 3)}2:{L(cc + 3)}{n_c}"
                wcr.cell(1, cc + 3, f"{g} (todos los meses)")
                wcr.cell(n_c + 2, cc + 2, "En escala")   # (ref_en_escala por ramo, en Listas)
                wcr.cell(n_c + 2, cc + 3, "=IFERROR(INDEX(L_XdefEscala,MATCH(SelRamoRfv,L_RamosRfv,0)),FALSE)")
                wcr.cell(n_c + 3, cc + 2, "Con PD medida")   # (sin medida, la PD ya es la de xDefault: la gris sobra)
                wcr.cell(n_c + 3, cc + 3, f"={pdmed}")
                for k in range(2, n_c + 1):
                    wcr.cell(k, cc + 3, f"={v(rango_de[g], k)}").number_format = fmt_c[u]
                    wcr.cell(k, cc + 2, f"=IF(AND(${L(cc + 3)}${n_c + 2},${L(cc + 3)}${n_c + 3}),{L(cc + 3)}{k},NA())"
                             ).number_format = fmt_c[u]
                wcr.cell(1, cc + 2, f'=IF(COUNT({gr})>0,"{g}",IF(NOT(${L(cc + 3)}${n_c + 3}),"{g} (es la misma PD)",'
                                    f'IF(COUNT({cruda})=0,"{g} (sin dato en esta selección)",'
                                    f'"{g} (fuera de escala: ver BD_RFV_Razones)")))')
            else:
                for k in range(2, n_c + 1):
                    wcr.cell(k, cc + 2, f"={v(rango_de[g], k)}").number_format = fmt_c[u]
                wcr.cell(1, cc + 2, f'=IF(COUNT({gr})>0,"{g}","{g} (sin dato en esta selección)")')
        cc += (4 if es_pd else 3) if g else 2
    wcr.sheet_state = "hidden"

    # ---- indicadores
    cf, cm = col_real["FRV"], col_real["RFV MA / RFV BRUTO"]
    kpis = [
        (f"FRV real {etiqueta(ultimo)}", f"=CalcRFV!{L(cf)}{fila_de[ultimo]}", "0.000"),
        (f"FRV proyección {etiqueta(p_dic)}", f"=CalcRFV!{L(cf + 1)}{fila_de.get(p_dic, n_c)}", "0.000"),
        (f"FRV proyección {etiqueta(periodos[-1])}", f"=CalcRFV!{L(cf + 1)}{n_c}", "0.000"),
        (f"RFV por MA {etiqueta(ultimo)}", f"=CalcRFV!{L(cm)}{fila_de[ultimo]}", "0.0%"),   # (renglon 9: que incluye)
    ]
    pintar(ws, "D5:AG8", BANDA_KPI)
    for k, (tit, form, fmt) in enumerate(kpis):
        col = 4 + k * 8
        fin_col = min(col + 6, 33)
        ws.merge_cells(start_row=5, start_column=col, end_row=6, end_column=fin_col)
        ws.merge_cells(start_row=7, start_column=col, end_row=8, end_column=fin_col)
        ws.cell(5, col, tit).font = fuente(9.5, True, TEXTO_2)
        ws.cell(5, col).alignment = Alignment(horizontal="left", vertical="bottom", indent=1)
        c = ws.cell(7, col, f'=IFERROR({form[1:]},"s/d")')
        c.number_format = fmt
        c.font = fuente(20, True)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # ---- paneles y graficas
    ramo_txt = 'IF(SelRamoRfv="Todos","todos los ramos","ramo "&SelRamoRfv)'
    eje = {"mxn": " · M MXN", "pct": " · %", "pct3": " · %", "razon": ""}
    for j, (c_, tit, u, g) in enumerate(INDICADORES_RFV):
        fila0 = 10 + 19 * ((j + 1) // 2) if 0 < j < len(cols) - 1 else (10 if j == 0 else 10 + 19 * ((len(cols) - 1) // 2 + 1))
        ancha = j in (0, len(cols) - 1)
        izq = ancha or j % 2 == 1
        c1, c2 = ("D", "AG") if ancha else (("D", "S") if izq else ("U", "AG"))
        caja(ws, f"{c1}{fila0}:{c2}{fila0 + 17}")
        ws[f"{c1}{fila0}"] = f'="{tit} · "&{ramo_txt}&"{eje[u]}"'
        ws[f"{c1}{fila0}"].font = fuente(11.5, True)
        ws[f"{c1}{fila0}"].alignment = Alignment(indent=1, vertical="center")
        ws.row_dimensions[fila0].height = 22
        cr = col_real[c_]
        ch = LineChart()
        ch.add_data(Reference(wcr, min_col=cr, max_col=cr + (2 if g else 1), min_row=1, max_row=n_c), titles_from_data=True)
        ch.set_categories(Reference(wcr, min_col=2, min_row=2, max_row=n_c))
        linea(ch.series[0], AZUL, 2.0, marcador=True)
        linea(ch.series[1], NARANJA, 2.0, punteada=True, marcador=True)
        if g:
            linea(ch.series[2], GRIS_BANDA, 1.25, marcador=True)
        estilo_grafica(ch, {"mxn": "#,##0", "pct": "0%", "pct3": "0.00%", "razon": "0.00"}[u])
        ch.x_axis.tickLblSkip = 6
        ch.x_axis.tickMarkSkip = 6
        colocar(ws, ch, f"{c1}{fila0 + 1}", f"{c2}{fila0 + 17}")

    # ---- factores constantes del ramo (ultimo real y ultimo proyectado)
    f0 = 10 + 19 * ((len(cols) - 1) // 2 + 2)
    caja(ws, f"D{f0}:S{f0 + len(FACTORES_RFV_TABLA) + 2}")
    ws[f"D{f0}"] = f'="Factores constantes · "&{ramo_txt}'
    ws[f"D{f0}"].font = fuente(11.5, True)
    ws[f"D{f0}"].alignment = Alignment(indent=1, vertical="center")
    # (cada valor en un bloque combinado de 5 columnas: en una sola columna de la rejilla el numero sale como ###)
    for k, t in enumerate(("Factor", f"Real {etiqueta(ultimo)}", f"Proyección {etiqueta(periodos[-1])}")):
        ws.merge_cells(start_row=f0 + 1, start_column=4 + 5 * k, end_row=f0 + 1, end_column=8 + 5 * k)
        c = ws.cell(f0 + 1, 4 + 5 * k, t)
        c.font = fuente(9.5, True, TEXTO_2)
        c.alignment = Alignment(horizontal="left" if k == 0 else "right", indent=1)
    for i, fac in enumerate(FACTORES_RFV_TABLA, start=f0 + 2):
        ws.merge_cells(start_row=i, start_column=4, end_row=i, end_column=8)
        ws.cell(i, 4, fac).font = fuente(10)
        ws.cell(i, 4).alignment = Alignment(indent=1)
        rng = rango_de[fac]
        for k, p in ((1, ultimo), (2, periodos[-1])):
            ws.merge_cells(start_row=i, start_column=4 + 5 * k, end_row=i, end_column=8 + 5 * k)
            x = f'INDEX({rng},MATCH(SelRamoRfv&"|"&{p},RF_Clave,0))'
            c = ws.cell(i, 4 + 5 * k, f'=IFERROR(IF({x}="","s/d",{x}),"s/d")')
            c.number_format = "0.000%" if fac == "FCR" else "0.00%"
            c.font = fuente(10)
            c.alignment = Alignment(horizontal="right", indent=1)
    _tablas_prima_rfv(ws, rz, f0 + len(FACTORES_RFV_TABLA) + 5)


def _celda_bloque(ws, fila: int, c1: int, c2: int, valor, fmt=None, negrita=False, derecha=False, color=TEXTO):
    """Valor en un bloque combinado de columnas (la rejilla es angosta: un numero en una sola columna sale ###)."""
    if c2 > c1:
        ws.merge_cells(start_row=fila, start_column=c1, end_row=fila, end_column=c2)
    c = ws.cell(fila, c1, valor)
    c.font = fuente(9.5 if negrita else 10, negrita, color)
    c.alignment = Alignment(horizontal="right" if derecha else "left", indent=1, vertical="center", wrap_text=False)
    if fmt:
        c.number_format = fmt
    return c


def _tablas_prima_rfv(ws, rz: dict, r0: int) -> None:
    """Hoja HOJA_DASH_RFV, debajo de los factores: la prima no real contra su historia (RFV_Prima_Bloques) y la
    sensibilidad de la RFV a la prima (RFV_Prima_Sensibilidad), para todos los ramos (no dependen del selector)."""
    pr = rz.get("prima") or {}
    bloques, sens = pr.get("bloques") or [], pr.get("sens") or []
    num = (int, float)
    if bloques:
        caja(ws, f"D{r0}:AG{r0 + len(bloques) + 2}")
        sp = list(rz.get("split") or [])
        con_saldo = any(str(d.get("modelo_frv") or "").startswith("saldo") for d in (rz.get("tendencia") or {}).values())
        ws.cell(r0, 4, "Prima no real contra su historia · todos los ramos (" + (
            "la RFV suma la reserva de cada prima nueva; la cartera en vigor sigue su liberación" if con_saldo else
            "la RFV se mueve casi en la misma proporción que su PRIMA 24M"
            + (f"; en {' y '.join(sp)}, solo la parte sin RFV MA" if sp else "")) + ")").font = fuente(11.5, True)
        cols = ((4, 6, "Ramo"), (7, 11, "Bloque"), (12, 15, "PT (M MXN)"), (16, 19, "Contra año anterior"),
                (20, 26, "Rango de esos meses en su historia"), (27, 29, "Fuera"), (30, 33, "Peso en la PRIMA 24M"))
        for c1, c2, t in cols:
            _celda_bloque(ws, r0 + 1, c1, c2, t, negrita=True, color=TEXTO_2, derecha=c1 >= 12)
        for i, f in enumerate(bloques, start=r0 + 2):
            g, lo, hi = (f.get(k) for k in ("Crecimiento contra el ano anterior", "Crecimiento minimo de esos meses (historia)",
                                            "Crecimiento maximo de esos meses (historia)"))
            rango = (f"{lo:+.1%} a {hi:+.1%} ({f.get('Anos de historia')} años)"
                     if isinstance(lo, num) and isinstance(hi, num) else "s/d")
            _celda_bloque(ws, i, 4, 6, str(f.get("Ramo")))
            _celda_bloque(ws, i, 7, 11, f.get("Bloque"))
            _celda_bloque(ws, i, 12, 15, (f.get("PT usada (MXN)") or 0) / 1e6, "#,##0.0", derecha=True)
            _celda_bloque(ws, i, 16, 19, g if isinstance(g, num) else "s/d", "+0.0%;-0.0%;0.0%", derecha=True)
            _celda_bloque(ws, i, 20, 26, rango, derecha=True)
            fuera = f.get("Fuera del rango historico") == "si"
            _celda_bloque(ws, i, 27, 29, "sí" if fuera else "no", derecha=True, negrita=fuera,
                          color="B4541F" if fuera else TEXTO)
            pz = f.get("Peso del bloque en la PRIMA 24M del ramo")
            _celda_bloque(ws, i, 30, 33, pz if isinstance(pz, num) else "s/d", "0%", derecha=True)
        r0 += len(bloques) + 4
    if sens:
        marcas = sorted({f["Periodo"] for f in sens})[-2:]
        claves = list(dict.fromkeys((f["Cambio"], f["Valor"]) for f in sens))
        caja(ws, f"D{r0}:AG{r0 + len(claves) + 2}")
        b0 = ", ".join(f"{etiqueta(p)}: {next(f['RFV BRUTO base (USD)'] for f in sens if f['Periodo'] == p) / 1e6:,.1f} "
                       "M USD" for p in marcas)
        ws.cell(r0, 4, f"Sensibilidad de la RFV BRUTO a la prima · todos los ramos (base {b0})").font = fuente(11.5, True)
        _celda_bloque(ws, r0 + 1, 4, 13, "Cambio", negrita=True, color=TEXTO_2)
        _celda_bloque(ws, r0 + 1, 14, 16, "Valor", negrita=True, color=TEXTO_2, derecha=True)
        for k, p in enumerate(marcas):
            _celda_bloque(ws, r0 + 1, 17 + 8 * k, 21 + 8 * k, f"RFV BRUTO {etiqueta(p)} (M USD)", negrita=True,
                          color=TEXTO_2, derecha=True)
            _celda_bloque(ws, r0 + 1, 22 + 8 * k, 24 + 8 * k, "Cambio", negrita=True, color=TEXTO_2, derecha=True)
        for i, (cb, v) in enumerate(claves, start=r0 + 2):
            _celda_bloque(ws, i, 4, 13, cb)
            _celda_bloque(ws, i, 14, 16, v, derecha=True)
            for k, p in enumerate(marcas):
                f = next((x for x in sens if (x["Cambio"], x["Valor"], x["Periodo"]) == (cb, v, p)), {})
                _celda_bloque(ws, i, 17 + 8 * k, 21 + 8 * k, (f.get("RFV BRUTO con el cambio (USD)") or 0) / 1e6,
                              "#,##0.0", derecha=True)
                _celda_bloque(ws, i, 22 + 8 * k, 24 + 8 * k, f.get("Cambio % RFV BRUTO"), "+0.0%;-0.0%;0.0%",
                              derecha=True)


def clasificar(wb) -> None:
    """El dashboard trae los mismos datos que la BD: hereda su etiqueta de sensibilidad (propiedades MSIP) y
    lleva el mismo pie de pagina de uso interno."""
    try:
        origen = openpyxl.load_workbook(ARCHIVO_DANOS, read_only=True)
        for prop in origen.custom_doc_props:
            if prop.name.startswith("MSIP_Label_"):
                wb.custom_doc_props.append(prop)
        origen.close()
    except Exception as e:  # noqa: BLE001
        print(f"   Aviso: no se pudo copiar la etiqueta de sensibilidad de {ARCHIVO_DANOS.name}: {e!r}")
    for ws in wb.worksheets:
        pie = ws.oddFooter.center
        pie.text, pie.font, pie.size, pie.color = PIE_PAGINA, "Aptos", 10, "000000"


def construir_analisis(ws, registros_i, ramos_i, registros_m, ultimo, p_dic, fin, fin_m, p_12, metodo):
    preparar_hoja(ws, ancho_nav=16, columnas=16, ancho=11.5, filas=80)
    ws.column_dimensions["C"].width = 11.5
    ws["B2"] = "Análisis: real vs proyección"
    ws["B2"].font = fuente(18, True)
    ws["B3"] = "Valores fijos calculados al generar el archivo (se actualizan en cada corrida de la proyección)."
    ws["B3"].font = fuente(10, False, TEXTO_2)
    for k, (t, d) in enumerate([("‹ Dashboard Índices", "'Dashboard Índices'!A1"),
                                ("‹ Dashboard Reservas", "'Dashboard Reservas'!A1")]):
        c = ws.cell(4, 2 + k * 4, t)
        c.hyperlink = Hyperlink(ref=c.coordinate, location=d)
        c.font = fuente(10, True, AZUL)

    val_i = {(r[1], r[2], r[3]): r[4] for r in registros_i}
    fila = 6
    ws.cell(fila, 2, f"1. Índices por ramo: promedio de los últimos 12 meses reales contra los próximos 12 proyectados "
                     f"({etiqueta(mover(ultimo, 1))} a {etiqueta(mover(ultimo, 12))})").font = fuente(12, True)
    fila += 1
    cab = ["Ramo"]
    for serie in INDICES:
        cab += [f"{serie}\nreal 12 m", f"{serie}\nproy. 12 m", "Var. %"]
    for j, t in enumerate(cab):
        c = ws.cell(fila, 2 + j, t)
        c.font = fuente(9, True, TEXTO_2)
        c.fill = relleno(BANDA_KPI)
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    ws.row_dimensions[fila].height = 42
    ini = fila + 1
    for ramo in ramos_i:
        fila += 1
        ws.cell(fila, 2, ramo).font = fuente(10, True)
        ws.cell(fila, 2).fill = relleno(PANEL)
        for k, serie in enumerate(INDICES):
            reales = [val_i.get((ramo, serie, mover(ultimo, -k))) for k in range(12)]
            proys = [val_i.get((ramo, serie, mover(ultimo, k))) for k in range(1, 13)]
            a = sum(reales) / 12 if all(x is not None for x in reales) else None
            b = sum(proys) / 12 if all(x is not None for x in proys) else None
            for j, v in enumerate([a, b, (b / a - 1) if a and b is not None else None]):
                c = ws.cell(fila, 3 + k * 3 + j, v)
                c.number_format = "+0.0%;-0.0%;0.0%" if j == 2 else "0.0000"
                c.fill = relleno(PANEL)
                c.font = fuente(10)
    for k in range(len(INDICES)):
        col = get_column_letter(5 + k * 3)
        ws.conditional_formatting.add(
            f"{col}{ini}:{col}{fila}",
            ColorScaleRule(start_type="num", start_value=-0.3, start_color="6DA7EC", mid_type="num", mid_value=0,
                           mid_color="F0EFEC", end_type="num", end_value=0.3, end_color="E66767"))
        for col_v in (get_column_letter(3 + k * 3), get_column_letter(4 + k * 3)):
            ws.conditional_formatting.add(
                f"{col_v}{ini}:{col_v}{fila}",
                ColorScaleRule(start_type="min", start_color="EAF2FD", end_type="max", end_color="6DA7EC"))

    fila += 3
    ws.cell(fila, 2, "2. Reservas: totales por concepto (millones USD)").font = fuente(12, True)
    fila += 1
    cortes = [mover(ultimo, -20) // 100 * 100 + 12, mover(ultimo, -8) // 100 * 100 + 12, ultimo, p_dic, fin_m]
    cortes = list(dict.fromkeys(cortes))
    cab = ["Reserva", "Concepto"] + [f"{etiqueta(p)}{' (real)' if p <= ultimo else ' (proy.)'}" for p in cortes] + \
          ["Crec. real 12m", "Crec. anualizado proy."]
    for j, t in enumerate(cab):
        c = ws.cell(fila, 2 + j, t)
        c.font = fuente(9, True, TEXTO_2)
        c.fill = relleno(BANDA_KPI)
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    ws.row_dimensions[fila].height = 32
    tot = {}
    for _, reserva, conc, _, per, _, v in registros_m:
        tot[(reserva, conc, per)] = tot.get((reserva, conc, per), 0.0) + v
    ini = fila + 1
    orden = [("RRC", c) for c in ["NETO", "BRUTO", "BEL", "GTO", "IRR", "MR"]] + \
            [("SONR", c) for c in ["NETO", "BRUTO", "BEL", "IRR", "MR"]] + [("RFV", c) for c in ["NETO", "BRUTO", "IRR", "RCONT"]]
    meses_proy = len(rango(ultimo, fin_m)) - 1
    for reserva, conc in orden:
        fila += 1
        ws.cell(fila, 2, reserva).font = fuente(10, True)
        ws.cell(fila, 3, conc).font = fuente(10)
        valores = [tot.get((reserva, conc, p)) for p in cortes]
        for j, v in enumerate(valores):
            c = ws.cell(fila, 4 + j, None if v is None else v / 1e6)
            c.number_format = "#,##0.0"
            c.font = fuente(10, j >= 3)
        v12, vu, vf = tot.get((reserva, conc, p_12)), tot.get((reserva, conc, ultimo)), tot.get((reserva, conc, fin_m))
        c = ws.cell(fila, 4 + len(cortes), (vu / v12 - 1) if v12 and vu else None)
        c.number_format = "+0.0%;-0.0%;0.0%"
        c = ws.cell(fila, 5 + len(cortes), ((vf / vu) ** (12 / meses_proy) - 1) if vu and vf and vu > 0 and vf > 0 else None)
        c.number_format = "+0.0%;-0.0%;0.0%"
        for j in range(2, 6 + len(cortes)):
            ws.cell(fila, j).fill = relleno(PANEL)
    for col in (get_column_letter(4 + len(cortes)), get_column_letter(5 + len(cortes))):
        ws.conditional_formatting.add(
            f"{col}{ini}:{col}{fila}",
            ColorScaleRule(start_type="num", start_value=-0.5, start_color="6DA7EC", mid_type="num", mid_value=0,
                           mid_color="F0EFEC", end_type="num", end_value=0.5, end_color="E66767"))

    fila += 3
    ws.cell(fila, 2, "3. Modelo por tipo de serie y error del backtest").font = fuente(12, True)
    fila += 1
    # columnas: B tipo | C:D modelo | E series | F error modelo | G error ultimo valor | H:I % series mejor
    posiciones = [(2, 3), (4, 5), (6, 6), (7, 7), (8, 8), (9, 10)]
    cab = ["Tipo de serie", "Modelo", "Series con backtest", "Error % modelo (mediana)",
           "Error % último valor (mediana)", "% series en que el modelo mejora al último valor"]
    for (c1_, c2_), t in zip(posiciones, cab):
        ws.merge_cells(start_row=fila, start_column=c1_, end_row=fila, end_column=c2_)
        c = ws.cell(fila, c1_, t)
        c.font = fuente(9, True, TEXTO_2)
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        for k in range(c1_, c2_ + 1):
            ws.cell(fila, k).fill = relleno(BANDA_KPI)
    ws.row_dimensions[fila].height = 32
    nombres = {"nivel": "Montos", "indice": "Índices", "razon": "Razones", "lag": "LAGs"}
    for d in metodo:
        fila += 1
        libros = {"DANOS": "Daños", "FIANZAS": "Fianzas", "HPARAM": "HParametros"}
        etiqueta_tipo = nombres.get(d.get("Tipo"), d.get("Tipo"))
        if d.get("Libro"):
            etiqueta_tipo += f" · {libros.get(d['Libro'], d['Libro'])}"
        vals = [etiqueta_tipo, d.get("Modelo"), d.get("Series con backtest"),
                d.get("Error % modelo (mediana)"), d.get("Error % ultimo valor (mediana)"),
                d.get("% series en que el modelo mejora al ultimo valor")]
        for j, ((c1_, c2_), v) in enumerate(zip(posiciones, vals)):
            ws.merge_cells(start_row=fila, start_column=c1_, end_row=fila, end_column=c2_)
            c = ws.cell(fila, c1_, v)
            c.font = fuente(10, j == 1)
            c.number_format = "0%" if j == 5 else ("0.0" if j in (3, 4) else "General")
            c.alignment = Alignment(wrap_text=j in (0, 1), vertical="center")
            for k in range(c1_, c2_ + 1):
                ws.cell(fila, k).fill = relleno(PANEL)
        ws.row_dimensions[fila].height = 30
    ws.freeze_panes = "A5"


if __name__ == "__main__":
    generar()
