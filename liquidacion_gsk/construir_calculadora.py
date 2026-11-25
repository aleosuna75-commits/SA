"""Construye la Calculadora de Liquidación de Personal (formato GSK).

Genera un .xlsx con fórmulas vivas (nada queda "pegado" como valor):
  - Calculadora : captura en 4 pasos, resultado arriba y desglose por concepto.
  - Instrucciones: cómo usarla, qué significa cada concepto y fundamento legal.
  - Tablas      : vacaciones (LFT art. 76), salario mínimo y UMA por vigencia, listas.

Uso:  python construir_calculadora.py [ruta_salida.xlsx]
"""

import datetime as dt
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("Calculadora_Liquidacion_GSK.xlsx")

# --------------------------------------------------------------------------------------
# Identidad visual GSK
# --------------------------------------------------------------------------------------
# Fuente de los colores: hoja de estilos de gsk.com (variable CSS --gsk-orange: #f36633) y
# neutros cálidos del mismo sitio (#151515, #3A3A3A, #F0EFED, #D5D1CE, #F8A385, #F25218).
NARANJA = "F36633"        # GSK orange (color primario de la marca)
NARANJA_INTENSO = "F25218"  # naranja profundo de gsk.com (total a pagar)
NARANJA_OSCURO = "B8410F"  # texto naranja legible sobre fondos claros (derivado)
DURAZNO = "F8A385"        # captura obligatoria (durazno de gsk.com)
CREMA = "FDE4D9"          # captura opcional / política (tinte claro del naranja)
GRIS_CALC = "F0EFED"      # cálculo automático (blanco cálido de gsk.com)
GRIS_BORDE = "D5D1CE"     # divisores (gris cálido de gsk.com)
GRIS_TEXTO = "6B6763"
CARBON = "3A3A3A"         # bandas oscuras (gris carbón de gsk.com)
NEGRO_GSK = "151515"      # texto principal (casi negro de gsk.com)
BLANCO = "FFFFFF"
VERDE_OK = "E3F1E6"
VERDE_OK_TXT = "1E6B33"
ROJO_AVISO = "FCE4E4"
ROJO_AVISO_TXT = "A61B1B"

FUENTE = "Arial"


def f(size=10, bold=False, color=NEGRO_GSK, italic=False):
    return Font(name=FUENTE, size=size, bold=bold, color=color, italic=italic)


def relleno(color):
    return PatternFill("solid", start_color=color, end_color=color)


delgado = Side(style="thin", color=GRIS_BORDE)
naranja_lado = Side(style="thin", color=NARANJA)
naranja_grueso = Side(style="medium", color=NARANJA_OSCURO)
BORDE_CELDA = Border(left=delgado, right=delgado, top=delgado, bottom=delgado)
BORDE_CAPTURA = Border(left=naranja_lado, right=naranja_lado, top=naranja_lado, bottom=naranja_lado)
BORDE_TOTAL = Border(top=naranja_grueso, bottom=naranja_grueso)

FMT_MONEDA = '"$"#,##0.00;-"$"#,##0.00;"–"'
FMT_MONEDA_SIMPLE = '"$"#,##0.00'
FMT_DIAS = '#,##0.00;-#,##0.00;"–"'
FMT_ENTERO = '#,##0'
FMT_FECHA = 'dd/mmm/yyyy'
FMT_PCT = '0%'
FMT_FACTOR = '0.0000'
FMT_ANIOS = '0.0000'

# --------------------------------------------------------------------------------------
# Datos de referencia (se capturan en la hoja Tablas; las fórmulas los buscan por fecha)
# --------------------------------------------------------------------------------------
# Salario mínimo diario: (año, vigente desde, general, zona libre frontera norte, fuente)
SALARIO_MINIMO = [
    (2017, dt.date(2017, 1, 1), 80.04, 80.04, "DOF 19/12/2016 (zona única)"),
    (2018, dt.date(2018, 1, 1), 88.36, 88.36, "DOF 21/12/2017 (zona única)"),
    (2019, dt.date(2019, 1, 1), 102.68, 176.72, "DOF 26/12/2018"),
    (2020, dt.date(2020, 1, 1), 123.22, 185.56, "DOF 23/12/2019"),
    (2021, dt.date(2021, 1, 1), 141.70, 213.39, "DOF 23/12/2020"),
    (2022, dt.date(2022, 1, 1), 172.87, 260.34, "DOF 08/12/2021"),
    (2023, dt.date(2023, 1, 1), 207.44, 312.41, "DOF 07/12/2022"),
    (2024, dt.date(2024, 1, 1), 248.93, 374.89, "DOF 12/12/2023"),
    (2025, dt.date(2025, 1, 1), 278.80, 419.88, "DOF 23/12/2024"),
    (2026, dt.date(2026, 1, 1), 315.04, 440.87, "DOF 2025 (CONASAMI)"),
]
ANIOS_SM_FUTUROS = [2027, 2028, 2029, 2030]

# UMA diaria: (año, vigente desde, valor, fuente)
UMA = [
    (2016, dt.date(2016, 1, 28), 73.04, "INEGI"),
    (2017, dt.date(2017, 2, 1), 75.49, "INEGI, DOF 10/01/2017"),
    (2018, dt.date(2018, 2, 1), 80.60, "INEGI, DOF 10/01/2018"),
    (2019, dt.date(2019, 2, 1), 84.49, "INEGI, DOF 10/01/2019"),
    (2020, dt.date(2020, 2, 1), 86.88, "INEGI, DOF 10/01/2020"),
    (2021, dt.date(2021, 2, 1), 89.62, "INEGI, DOF 08/01/2021"),
    (2022, dt.date(2022, 2, 1), 96.22, "INEGI, DOF 10/01/2022"),
    (2023, dt.date(2023, 2, 1), 103.74, "INEGI, DOF 10/01/2023"),
    (2024, dt.date(2024, 2, 1), 108.57, "INEGI, DOF 10/01/2024"),
    (2025, dt.date(2025, 2, 1), 113.14, "INEGI, DOF 10/01/2025"),
    (2026, dt.date(2026, 2, 1), 117.31, "INEGI, DOF 09/01/2026"),
]
ANIOS_UMA_FUTUROS = [2027, 2028, 2029, 2030]

# Vacaciones LFT art. 76 (reforma DOF 27/12/2022, vigente desde 01/01/2023)
VACACIONES = [(1, 1, 12), (2, 2, 14), (3, 3, 16), (4, 4, 18), (5, 5, 20)]
_d = 22
for desde in range(6, 61, 5):
    VACACIONES.append((desde, desde + 4, _d))
    _d += 2

LISTA_TIPO = [
    "Liquidación (la empresa termina)",
    "Renuncia voluntaria",
    "Despido justificado (rescisión)",
]
LISTA_ZONA = ["General", "Zona Libre Frontera Norte"]
LISTA_SINO = ["Sí", "No"]
LISTA_BASE = ["Integrado", "Base"]
LISTA_UNIDAD = ["Salario mínimo", "UMA"]

# Ejemplo precargado (se sobrescribe con los datos reales)
EJEMPLO = {
    "Nombre": "Colaborador de Ejemplo",
    "NumEmpleado": "000123",
    "Puesto": "Representante Médico",
    "FechaIngreso": dt.date(2019, 3, 15),
    "FechaSalida": dt.date(2026, 11, 30),
    "SueldoMensual": 45000,
    "TipoSalida": LISTA_TIPO[0],
    "ZonaSM": LISTA_ZONA[0],
    "DiasAguinaldo": 15,
    "PctPrimaVac": 0.25,
    "DiasSueldoPend": 5,
    "DiasVacPend": 2,
    "DiasVacTomados": 4,
    "Bono": 20000,
}

wb = Workbook()


def nombrar(nombre, hoja, ref):
    """Define un nombre de libro (ej. FechaIngreso -> 'Calculadora'!$D$14)."""
    wb.defined_names[nombre] = DefinedName(nombre, attr_text=f"'{hoja}'!{ref}")


def abs_ref(col, fila):
    return f"${col}${fila}"


def num_txt(expr):
    """Texto de un número: sin decimales si es entero, con 2 si no (FIXED no depende del idioma)."""
    return f'IF(ROUND({expr},2)=INT({expr}),FIXED({expr},0),FIXED({expr},2))'


# ======================================================================================
# HOJA: Tablas (se construye primero porque las demás usan sus nombres)
# ======================================================================================
wsT = wb.active
wsT.title = "Tablas"
wsT.sheet_view.showGridLines = False
wsT.sheet_properties.tabColor = "9E9E9E"
for col, ancho in {"A": 2, "B": 16, "C": 16, "D": 20, "E": 26, "F": 40, "G": 3, "H": 36}.items():
    wsT.column_dimensions[col].width = ancho

wsT.merge_cells("B1:F1")
wsT["B1"] = "TABLAS DE REFERENCIA"
wsT["B1"].font = f(16, True, BLANCO)
wsT["B1"].fill = relleno(NARANJA)
wsT["B1"].alignment = Alignment(vertical="center", indent=1)
wsT.row_dimensions[1].height = 30
wsT.merge_cells("B2:F2")
wsT["B2"] = ("Las celdas color crema se pueden actualizar (una vez al año). "
             "Lo demás está protegido para que no se borre por accidente.")
wsT["B2"].font = f(9, italic=True, color=GRIS_TEXTO)


def titulo_tabla(ws, fila, texto, desde="B", hasta="F"):
    ws.merge_cells(f"{desde}{fila}:{hasta}{fila}")
    c = ws[f"{desde}{fila}"]
    c.value = texto
    c.font = f(11, True, BLANCO)
    c.fill = relleno(CARBON)
    c.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[fila].height = 20


def encabezados(ws, fila, columnas, textos):
    for col, t in zip(columnas, textos):
        c = ws[f"{col}{fila}"]
        c.value = t
        c.font = f(9, True, CARBON)
        c.fill = relleno(GRIS_BORDE)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDE_CELDA
    ws.row_dimensions[fila].height = 30


# --- Vacaciones -----------------------------------------------------------------------
r = 4
titulo_tabla(wsT, r, "VACACIONES POR AÑO DE SERVICIO  (LFT art. 76, reforma vigente desde 01/01/2023)")
r += 1
encabezados(wsT, r, "BCDEF", ["Desde el año\nde servicio", "Hasta el año\nde servicio", "Días por ley",
                               "Días que da la empresa\n(editable)", "Nota"])
r += 1
vac_ini = r
for desde, hasta, dias in VACACIONES:
    wsT[f"B{r}"] = desde
    wsT[f"C{r}"] = hasta
    wsT[f"D{r}"] = dias
    wsT[f"E{r}"] = dias
    for col in "BCD":
        wsT[f"{col}{r}"].font = f(10)
        wsT[f"{col}{r}"].alignment = Alignment(horizontal="center")
        wsT[f"{col}{r}"].border = BORDE_CELDA
        wsT[f"{col}{r}"].fill = relleno(GRIS_CALC)
    e = wsT[f"E{r}"]
    e.font = f(10, True)
    e.alignment = Alignment(horizontal="center")
    e.fill = relleno(CREMA)
    e.border = BORDE_CAPTURA
    e.protection = Protection(locked=False)
    wsT[f"F{r}"].border = BORDE_CELDA
    r += 1
vac_fin = r - 1
wsT[f"F{vac_ini}"] = "Si la empresa da más días que la ley, cámbialos en la columna crema."
wsT[f"F{vac_ini}"].font = f(9, italic=True, color=GRIS_TEXTO)
wsT[f"F{vac_ini}"].alignment = Alignment(wrap_text=True, vertical="top")
wsT.merge_cells(f"F{vac_ini}:F{vac_ini + 3}")
nombrar("Vac_Desde", "Tablas", f"$B${vac_ini}:$B${vac_fin}")
nombrar("Vac_Ley", "Tablas", f"$D${vac_ini}:$D${vac_fin}")
nombrar("Vac_Empresa", "Tablas", f"$E${vac_ini}:$E${vac_fin}")

# --- Salario mínimo ---------------------------------------------------------------------
r += 1
titulo_tabla(wsT, r, "SALARIO MÍNIMO DIARIO  (se usa para el tope de la prima de antigüedad, LFT arts. 162, 485 y 486)")
r += 1
encabezados(wsT, r, "BCDEF", ["Año", "Vigente desde", "Zona general", "Zona Libre de la\nFrontera Norte", "Fuente"])
r += 1
sm_ini = r
for anio, desde, gen, zlfn, fuente in SALARIO_MINIMO + [(a, dt.date(a, 1, 1), None, None, "Capturar cuando se publique en el DOF") for a in ANIOS_SM_FUTUROS]:
    wsT[f"B{r}"] = anio
    wsT[f"C{r}"] = desde
    wsT[f"D{r}"] = gen
    wsT[f"E{r}"] = zlfn
    wsT[f"F{r}"] = fuente
    wsT[f"B{r}"].number_format = "0"
    wsT[f"C{r}"].number_format = FMT_FECHA
    for col in "BC":
        wsT[f"{col}{r}"].font = f(10)
        wsT[f"{col}{r}"].alignment = Alignment(horizontal="center")
        wsT[f"{col}{r}"].fill = relleno(GRIS_CALC)
        wsT[f"{col}{r}"].border = BORDE_CELDA
    for col in "DE":
        c = wsT[f"{col}{r}"]
        c.number_format = FMT_MONEDA_SIMPLE
        c.font = f(10, True)
        c.alignment = Alignment(horizontal="center")
        c.fill = relleno(CREMA)
        c.border = BORDE_CAPTURA
        c.protection = Protection(locked=False)
    wsT[f"F{r}"].font = f(8, italic=True, color=GRIS_TEXTO)
    wsT[f"F{r}"].border = BORDE_CELDA
    wsT[f"F{r}"].protection = Protection(locked=False)
    r += 1
sm_fin = r - 1
nombrar("SM_Anio", "Tablas", f"$B${sm_ini}:$B${sm_fin}")
nombrar("SM_Desde", "Tablas", f"$C${sm_ini}:$C${sm_fin}")
nombrar("SM_General", "Tablas", f"$D${sm_ini}:$D${sm_fin}")
nombrar("SM_Frontera", "Tablas", f"$E${sm_ini}:$E${sm_fin}")

# --- UMA --------------------------------------------------------------------------------
r += 1
titulo_tabla(wsT, r, "UMA DIARIA  (sólo se usa si eliges topar la prima de antigüedad en UMA)")
r += 1
encabezados(wsT, r, "BCDEF", ["Año", "Vigente desde", "UMA diaria", "", "Fuente"])
r += 1
uma_ini = r
for anio, desde, valor, fuente in UMA + [(a, dt.date(a, 2, 1), None, "Capturar cuando la publique el INEGI") for a in ANIOS_UMA_FUTUROS]:
    wsT[f"B{r}"] = anio
    wsT[f"C{r}"] = desde
    wsT[f"D{r}"] = valor
    wsT[f"F{r}"] = fuente
    wsT[f"B{r}"].number_format = "0"
    wsT[f"C{r}"].number_format = FMT_FECHA
    for col in "BC":
        wsT[f"{col}{r}"].font = f(10)
        wsT[f"{col}{r}"].alignment = Alignment(horizontal="center")
        wsT[f"{col}{r}"].fill = relleno(GRIS_CALC)
        wsT[f"{col}{r}"].border = BORDE_CELDA
    c = wsT[f"D{r}"]
    c.number_format = FMT_MONEDA_SIMPLE
    c.font = f(10, True)
    c.alignment = Alignment(horizontal="center")
    c.fill = relleno(CREMA)
    c.border = BORDE_CAPTURA
    c.protection = Protection(locked=False)
    wsT[f"F{r}"].font = f(8, italic=True, color=GRIS_TEXTO)
    wsT[f"F{r}"].border = BORDE_CELDA
    wsT[f"F{r}"].protection = Protection(locked=False)
    r += 1
uma_fin = r - 1
nombrar("UMA_Desde", "Tablas", f"$C${uma_ini}:$C${uma_fin}")
nombrar("UMA_Valor", "Tablas", f"$D${uma_ini}:$D${uma_fin}")

# --- Listas para menús desplegables -------------------------------------------------------
titulo_tabla(wsT, 4, "LISTAS DE LOS MENÚS (no modificar)", "H", "H")
fila_lista = 5
for nombre_lista, valores in [("Lista_Tipo", LISTA_TIPO), ("Lista_Zona", LISTA_ZONA), ("Lista_SiNo", LISTA_SINO),
                              ("Lista_Base", LISTA_BASE), ("Lista_Unidad", LISTA_UNIDAD)]:
    wsT[f"H{fila_lista}"] = nombre_lista.replace("Lista_", "Lista: ")
    wsT[f"H{fila_lista}"].font = f(8, True, GRIS_TEXTO)
    ini = fila_lista + 1
    for i, v in enumerate(valores):
        c = wsT[f"H{ini + i}"]
        c.value = v
        c.font = f(10)
        c.fill = relleno(GRIS_CALC)
        c.border = BORDE_CELDA
    nombrar(nombre_lista, "Tablas", f"$H${ini}:$H${ini + len(valores) - 1}")
    fila_lista = ini + len(valores) + 1

wsT.protection.sheet = True
wsT.freeze_panes = "A4"

# ======================================================================================
# HOJA: Calculadora
# ======================================================================================
ws = wb.create_sheet("Calculadora", 0)
ws.sheet_view.showGridLines = False
ws.sheet_view.zoomScale = 90
ws.sheet_properties.tabColor = NARANJA
for col, ancho in {"A": 2, "B": 5, "C": 50, "D": 19, "E": 19, "F": 21, "G": 62, "H": 2}.items():
    ws.column_dimensions[col].width = ancho

HOJA = "Calculadora"
cond_grises = []      # filas del desglose que se ven grises cuando el importe es cero


def banda(fila, texto, color=NARANJA, tam=12, alto=24, color_txt=BLANCO, desde="B", hasta="G"):
    ws.merge_cells(f"{desde}{fila}:{hasta}{fila}")
    c = ws[f"{desde}{fila}"]
    c.value = texto
    c.font = f(tam, True, color_txt)
    c.fill = relleno(color)
    c.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[fila].height = alto


def ayuda(fila, texto, desde="E", hasta="G"):
    ws.merge_cells(f"{desde}{fila}:{hasta}{fila}")
    c = ws[f"{desde}{fila}"]
    c.value = texto
    c.font = f(9, italic=True, color=GRIS_TEXTO)
    c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)


def etiqueta(fila, texto, negrita=False, sangria=1):
    c = ws[f"C{fila}"]
    c.value = texto
    c.font = f(10, negrita)
    c.alignment = Alignment(vertical="center", indent=sangria, wrap_text=True)


def captura(fila, nombre, valor, fmt=None, obligatorio=True, alinear="center"):
    c = ws[f"D{fila}"]
    c.value = valor
    c.font = f(11 if obligatorio else 10, True, "000000")
    c.fill = relleno(DURAZNO if obligatorio else CREMA)
    c.border = BORDE_CAPTURA
    c.alignment = Alignment(horizontal=alinear, vertical="center")
    c.protection = Protection(locked=False)
    if fmt:
        c.number_format = fmt
    nombrar(nombre, HOJA, abs_ref("D", fila))
    ws.row_dimensions[fila].height = 20
    return c


def calculo(fila, nombre, formula, fmt=None, col="D", negrita=False):
    c = ws[f"{col}{fila}"]
    c.value = formula
    c.font = f(10, negrita)
    c.fill = relleno(GRIS_CALC)
    c.border = BORDE_CELDA
    c.alignment = Alignment(horizontal="center", vertical="center")
    if fmt:
        c.number_format = fmt
    if nombre:
        nombrar(nombre, HOJA, abs_ref(col, fila))
    return c


dv_fecha = DataValidation(type="date", operator="between", formula1="18264", formula2="73415", allow_blank=True)
dv_fecha.errorTitle = "Fecha no válida"
dv_fecha.error = "Escribe una fecha como 15/03/2019 (día/mes/año)."
dv_fecha.promptTitle = "Fecha"
dv_fecha.prompt = "Escríbela como día/mes/año, por ejemplo 15/03/2019."
dv_dinero = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
dv_dinero.errorTitle = "Monto no válido"
dv_dinero.error = "Escribe sólo el número, sin signo de pesos ni letras. Ej. 45000"
dv_dias = DataValidation(type="decimal", operator="between", formula1="0", formula2="400", allow_blank=True)
dv_dias.errorTitle = "Número de días no válido"
dv_dias.error = "Escribe un número de días entre 0 y 400 (puede llevar decimales)."
dv_pct = DataValidation(type="decimal", operator="between", formula1="0", formula2="5", allow_blank=False)
dv_pct.errorTitle = "Porcentaje no válido"
dv_pct.error = "Escribe el porcentaje, por ejemplo 25%."
dv_entero_pos = DataValidation(type="decimal", operator="between", formula1="0", formula2="1000", allow_blank=False)
dv_entero_pos.errorTitle = "Valor no válido"
dv_entero_pos.error = "Escribe un número positivo."


def lista(nombre_lista, titulo):
    dv = DataValidation(type="list", formula1=f"={nombre_lista}", allow_blank=False)
    dv.errorTitle = titulo
    dv.error = "Elige una opción de la lista (flechita a la derecha de la celda)."
    dv.promptTitle = titulo
    dv.prompt = "Elige una opción de la lista."
    ws.add_data_validation(dv)
    return dv


for dv in (dv_fecha, dv_dinero, dv_dias, dv_pct, dv_entero_pos):
    dv.showErrorMessage = True
    dv.showInputMessage = True
    ws.add_data_validation(dv)

# --- Encabezado -------------------------------------------------------------------------
ws.merge_cells("B1:G1")
ws["B1"] = "GSK  ·  Calculadora de Liquidación de Personal"
ws["B1"].font = f(20, True, BLANCO)
ws["B1"].fill = relleno(NARANJA)
ws["B1"].alignment = Alignment(vertical="center", indent=1)
ws.row_dimensions[1].height = 42
ws.merge_cells("B2:G2")
ws["B2"] = ("Llena sólo las celdas color durazno. Todo lo gris se calcula solo. "
            "¿Dudas? Abre la pestaña «Instrucciones».")
ws["B2"].font = f(10, False, NEGRO_GSK)
for col in "BCDEFG":
    ws[f"{col}2"].border = Border(bottom=naranja_lado)
ws["B2"].alignment = Alignment(vertical="center", indent=1)
ws.row_dimensions[2].height = 22

ws["C3"] = "Colores:"
ws["C3"].font = f(9, True, GRIS_TEXTO)
ws["C3"].alignment = Alignment(horizontal="right", vertical="center")
for col, txt, color, borde in [("D", "Captura", DURAZNO, BORDE_CAPTURA), ("E", "Opcional / política", CREMA, BORDE_CAPTURA),
                               ("F", "Automático (no tocar)", GRIS_CALC, BORDE_CELDA)]:
    c = ws[f"{col}3"]
    c.value = txt
    c.font = f(8, True)
    c.fill = relleno(color)
    c.border = borde
    c.alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[3].height = 18

# Las filas del resultado se llenan al final (necesitan las filas del desglose).
FILA_RES = 5
banda(FILA_RES, "RESULTADO", CARBON, 11, 22)
ws.row_dimensions[FILA_RES + 1].height = 18
ws.row_dimensions[FILA_RES + 2].height = 34
ws.row_dimensions[FILA_RES + 3].height = 22

# --- PASO 1 -----------------------------------------------------------------------------
r = 10
banda(r, "PASO 1 ·  DATOS DEL COLABORADOR")
r += 1
etiqueta(r, "Nombre completo"); captura(r, "Nombre", EJEMPLO["Nombre"], alinear="left")
ws.merge_cells(f"D{r}:E{r}")
ayuda(r, "Como aparecerá en el resultado.", "F", "G")
r += 1
etiqueta(r, "Número de empleado (opcional)"); captura(r, "NumEmpleado", EJEMPLO["NumEmpleado"], obligatorio=False, alinear="left")
ws[f"D{r}"].number_format = "@"
ws.merge_cells(f"D{r}:E{r}")
ayuda(r, "Opcional.", "F", "G")
r += 1
etiqueta(r, "Puesto (opcional)"); captura(r, "Puesto", EJEMPLO["Puesto"], obligatorio=False, alinear="left")
ws.merge_cells(f"D{r}:E{r}")
ayuda(r, "Opcional.", "F", "G")
r += 1
etiqueta(r, "Fecha de ingreso"); captura(r, "FechaIngreso", EJEMPLO["FechaIngreso"], FMT_FECHA)
dv_fecha.add(f"D{r}")
ayuda(r, "Día/mes/año. Ej. 15/03/2019. Si le reconocen antigüedad anterior, pon esa fecha.")
r += 1
etiqueta(r, "Fecha de salida (último día trabajado)"); captura(r, "FechaSalida", EJEMPLO["FechaSalida"], FMT_FECHA)
dv_fecha.add(f"D{r}")
ayuda(r, "Día/mes/año. Es el último día que se le paga.")
r += 1
etiqueta(r, "Sueldo mensual bruto (base)"); captura(r, "SueldoMensual", EJEMPLO["SueldoMensual"], FMT_MONEDA_SIMPLE)
dv_dinero.add(f"D{r}")
ayuda(r, "Sueldo nominal del mes, sin bonos ni prestaciones. Sólo el número: 45000")
r += 1
etiqueta(r, "Tipo de salida"); captura(r, "TipoSalida", EJEMPLO["TipoSalida"], alinear="left")
ws[f"D{r}"].font = f(9, True, "000000")
lista("Lista_Tipo", "Tipo de salida").add(f"D{r}")
ws.merge_cells(f"D{r}:E{r}")
ayuda(r, "Elige de la lista. Define qué conceptos se pagan.", "F", "G")
r += 1
etiqueta(r, "Zona de salario mínimo"); captura(r, "ZonaSM", EJEMPLO["ZonaSM"], obligatorio=False, alinear="left")
lista("Lista_Zona", "Zona de salario mínimo").add(f"D{r}")
ws.merge_cells(f"D{r}:E{r}")
ayuda(r, "«General» para casi todo el país. Frontera Norte sólo en esos municipios.", "F", "G")

# --- PASO 2 -----------------------------------------------------------------------------
r += 2
banda(r, "PASO 2 ·  PRESTACIONES  (vienen con el mínimo de ley; cámbialas si la empresa da más)")
r += 1
etiqueta(r, "Días de aguinaldo al año"); captura(r, "DiasAguinaldo", EJEMPLO["DiasAguinaldo"], "0.##", obligatorio=False)
dv_dias.add(f"D{r}")
ayuda(r, "Ley: 15 días (art. 87 LFT). Integra al salario.")
r += 1
etiqueta(r, "Prima vacacional (%)"); captura(r, "PctPrimaVac", EJEMPLO["PctPrimaVac"], FMT_PCT, obligatorio=False)
dv_pct.add(f"D{r}")
ayuda(r, "Ley: 25% de los días de vacaciones (art. 80 LFT). Integra al salario.")
r += 1
fila_vac_tabla = r
etiqueta(r, "Días de vacaciones al año según la tabla (automático)")
ayuda(r, "Se toma de la hoja «Tablas» según el año de servicio que está corriendo.")
r += 1
etiqueta(r, "Días de vacaciones al año, sólo si son distintos (opcional)")
captura(r, "DiasVacManual", None, "0.##", obligatorio=False)
dv_dias.add(f"D{r}")
ayuda(r, "Déjala vacía para usar la tabla. Si escribes un número, se usa ese.")

# --- PASO 3 -----------------------------------------------------------------------------
r += 2
banda(r, "PASO 3 ·  PENDIENTES DE PAGO Y BONO")
r += 1
etiqueta(r, "Días que trabajó y todavía no se le pagan"); captura(r, "DiasSueldoPend", EJEMPLO["DiasSueldoPend"], "0.##")
dv_dias.add(f"D{r}")
ayuda(r, "Ej. los días de la quincena en curso. Si ya se le pagó todo, pon 0.")
r += 1
etiqueta(r, "Días de vacaciones de años anteriores que no tomó"); captura(r, "DiasVacPend", EJEMPLO["DiasVacPend"], "0.##")
dv_dias.add(f"D{r}")
ayuda(r, "Vacaciones ya ganadas en aniversarios pasados y no disfrutadas. Si no hay, pon 0.")
r += 1
etiqueta(r, "Días de vacaciones que ya tomó desde su último aniversario"); captura(r, "DiasVacTomados", EJEMPLO["DiasVacTomados"], "0.##")
dv_dias.add(f"D{r}")
ayuda(r, "Se restan de las vacaciones proporcionales de este año. Si no ha tomado, pon 0.")
r += 1
etiqueta(r, "Bono a pagar en la liquidación ($)"); captura(r, "Bono", EJEMPLO["Bono"], FMT_MONEDA_SIMPLE)
dv_dinero.add(f"D{r}")
ayuda(r, "Se paga completo, pero NO se suma al salario integrado. Si no hay, pon 0.")

# --- PASO 4 -----------------------------------------------------------------------------
r += 2
banda(r, "PASO 4 ·  POLÍTICA DE PAGO GSK  (normalmente no se toca)", CARBON)
r += 1
etiqueta(r, "Meses de indemnización (TRL)"); captura(r, "MesesIndem", 4, "0.##", obligatorio=False)
dv_entero_pos.add(f"D{r}")
ayuda(r, "Ley: 3 meses (art. 50 LFT). GSK paga 4 meses de salario integrado.")
r += 1
etiqueta(r, "Días de indemnización por cada año de servicio"); captura(r, "DiasPorAnio", 20, "0.##", obligatorio=False)
dv_entero_pos.add(f"D{r}")
ayuda(r, "GSK paga 20 días de salario integrado por año, incluyendo la fracción del año.")
r += 1
etiqueta(r, "Días de prima de antigüedad por año"); captura(r, "DiasPrimaAnt", 12, "0.##", obligatorio=False)
dv_entero_pos.add(f"D{r}")
ayuda(r, "Ley: 12 días por año de servicio (art. 162 LFT).")
r += 1
etiqueta(r, "¿Topar el salario de la prima de antigüedad?"); captura(r, "ToparPrimaAnt", "Sí", obligatorio=False)
lista("Lista_SiNo", "¿Topar?").add(f"D{r}")
ayuda(r, "Sí = el salario diario no puede pasar del tope de abajo (así lo marca la ley).")
r += 1
etiqueta(r, "Tope: número de veces"); captura(r, "VecesTope", 2, "0.##", obligatorio=False)
dv_entero_pos.add(f"D{r}")
ayuda(r, "Ley: 2 veces el salario mínimo (arts. 485 y 486 LFT). Puedes moverlo.")
r += 1
etiqueta(r, "El tope se mide en"); captura(r, "UnidadTope", LISTA_UNIDAD[0], obligatorio=False)
ws[f"D{r}"].font = f(9, True, "000000")
lista("Lista_Unidad", "Unidad del tope").add(f"D{r}")
ayuda(r, "La ley usa salario mínimo. UMA sólo si la política lo pide.")
r += 1
etiqueta(r, "Salario para la prima de antigüedad"); captura(r, "BasePrimaAnt", LISTA_BASE[0], obligatorio=False)
lista("Lista_Base", "Salario para prima de antigüedad").add(f"D{r}")
ayuda(r, "Integrado (con aguinaldo y prima vacacional) o Base (sólo sueldo). Luego se aplica el tope.")
r += 1
etiqueta(r, "Años mínimos para pagar prima de antigüedad en renuncia"); captura(r, "AntMinRenuncia", 15, "0.##", obligatorio=False)
dv_entero_pos.add(f"D{r}")
ayuda(r, "Ley: 15 años (art. 162 LFT). Sólo aplica en renuncia voluntaria.")
r += 1
etiqueta(r, "Días por mes"); captura(r, "DiasMes", 30, "0.##", obligatorio=False)
dv_entero_pos.add(f"D{r}")
ayuda(r, "Para pasar el sueldo mensual a diario y los meses a días. Normalmente 30.")

# --- DESGLOSE ---------------------------------------------------------------------------
r += 2
FILA_DESGLOSE = r
banda(r, "DESGLOSE DE LA LIQUIDACIÓN", NARANJA, 13, 26)
r += 1
for col, txt in zip("BCDEFG", ["#", "Concepto", "Días", "Salario diario", "Importe", "Cómo se calcula"]):
    c = ws[f"{col}{r}"]
    c.value = txt
    c.font = f(10, True, BLANCO)
    c.fill = relleno(CARBON)
    c.alignment = Alignment(horizontal="center" if col != "G" else "left", vertical="center", indent=1 if col == "G" else 0)
ws.row_dimensions[r].height = 20


def subtitulo(fila, texto):
    ws.merge_cells(f"B{fila}:G{fila}")
    c = ws[f"B{fila}"]
    c.value = texto
    c.font = f(10, True, NARANJA_OSCURO)
    c.alignment = Alignment(vertical="center", indent=1)
    for col in "BCDEFG":
        ws[f"{col}{fila}"].border = Border(bottom=naranja_lado)
    ws.row_dimensions[fila].height = 22


def concepto(fila, numero, texto, dias, salario, importe, explicacion, fmt_dias=FMT_DIAS, alto=30):
    ws[f"B{fila}"] = numero
    ws[f"B{fila}"].font = f(10, True, NARANJA)
    ws[f"B{fila}"].alignment = Alignment(horizontal="center", vertical="center")
    ws[f"C{fila}"] = texto
    ws[f"C{fila}"].font = f(10, True)
    ws[f"C{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col, val, fmt in [("D", dias, fmt_dias), ("E", salario, FMT_MONEDA), ("F", importe, FMT_MONEDA)]:
        c = ws[f"{col}{fila}"]
        c.value = val
        c.number_format = fmt
        c.font = f(10, col == "F")
        c.alignment = Alignment(horizontal="right" if col != "D" else "center", vertical="center")
    ws[f"G{fila}"] = explicacion
    ws[f"G{fila}"].font = f(9, color=GRIS_TEXTO)
    ws[f"G{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col in "BCDEFG":
        ws[f"{col}{fila}"].border = Border(bottom=delgado)
    ws.row_dimensions[fila].height = alto
    cond_grises.append(fila)


def subtotal(fila, texto, formula, nombre):
    ws.merge_cells(f"B{fila}:E{fila}")
    ws[f"B{fila}"] = texto
    ws[f"B{fila}"].font = f(10, True)
    ws[f"B{fila}"].alignment = Alignment(horizontal="right", vertical="center", indent=1)
    c = ws[f"F{fila}"]
    c.value = formula
    c.number_format = FMT_MONEDA
    c.font = f(11, True)
    c.alignment = Alignment(horizontal="right", vertical="center")
    c.border = Border(top=Side(style="thin", color=CARBON))
    nombrar(nombre, HOJA, abs_ref("F", fila))
    ws.row_dimensions[fila].height = 22


OK = 'DatosOK="Sí"'
r += 1
subtitulo(r, "A.  FINIQUITO  —  lo que ya se ganó; se paga en cualquier tipo de salida")
r += 1
f_sueldo = r
concepto(r, 1, "Sueldo pendiente de pago",
         f"=IF({OK},DiasSueldoPend,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasSueldoPend")}&" días trabajados no pagados × salario diario","")')
r += 1
f_agui = r
concepto(r, 2, "Aguinaldo proporcional",
         f"=IF({OK},DiasAguinaldo*DiasAnioCal/365,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasAguinaldo")}&" días de aguinaldo × "&FIXED(DiasAnioCal,0)&" días trabajados en "&YEAR(FechaSalida)&" ÷ 365","")')
r += 1
f_vacprop = r
concepto(r, 3, "Vacaciones proporcionales del año de servicio en curso",
         f"=IF({OK},MAX(0,DiasVacAnio*DiasDesdeAniv/365-DiasVacTomados),0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasVacAnio")}&" días de vacaciones × "&FIXED(DiasDesdeAniv,0)&" días desde el último aniversario ÷ 365"'
         f'&IF(DiasVacTomados>0," − "&{num_txt("DiasVacTomados")}&" días ya tomados","")'
         f'&IF(DiasVacAnio*DiasDesdeAniv/365<DiasVacTomados," (tomó más de lo ganado: se paga 0)",""),"")')
r += 1
f_vacpend = r
concepto(r, 4, "Vacaciones pendientes de años anteriores",
         f"=IF({OK},DiasVacPend,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasVacPend")}&" días no tomados de años anteriores × salario diario","")')
r += 1
f_pv = r
concepto(r, 5, "Prima vacacional",
         f"=IF({OK},(D{f_vacprop}+D{f_vacpend})*PctPrimaVac,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},FIXED(PctPrimaVac*100,0)&"% × "&{num_txt(f"(D{f_vacprop}+D{f_vacpend})")}&" días de vacaciones a pagar (conceptos 3 y 4)","")')
r += 1
f_bono = r
concepto(r, 6, "Bono (no integra al salario)",
         None, None, f"=IF({OK},ROUND(Bono,2),0)",
         f'=IF({OK},IF(Bono>0,"Monto capturado en el Paso 3. Se paga completo y no entra al salario integrado.","Sin bono"),"")')
r += 1
f_subfin = r
subtotal(r, "Subtotal finiquito", f"=SUM(F{f_sueldo}:F{f_bono})", "TotalFiniquito")

r += 1
subtitulo(r, "B.  INDEMNIZACIÓN  —  sólo cuando la empresa termina la relación  (salario diario integrado)")
r += 1
f_indem = r
concepto(r, 7, "Indemnización constitucional (TRL)",
         f"=IF(AND({OK},AplicaIndem=\"Sí\"),MesesIndem*DiasMes,0)", f"=IF({OK},SalarioIntegrado,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},IF(AplicaIndem="Sí",{num_txt("MesesIndem")}&" meses × "&{num_txt("DiasMes")}&" días × salario diario integrado","No aplica en: "&TipoSalida),"")')
r += 1
f_20 = r
concepto(r, 8, "Días por año de servicio",
         f"=IF(AND({OK},AplicaIndem=\"Sí\"),DiasPorAnio*AniosServicio,0)", f"=IF({OK},SalarioIntegrado,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},IF(AplicaIndem="Sí",{num_txt("DiasPorAnio")}&" días × "&FIXED(AniosServicio,4)&" años de servicio × salario diario integrado","No aplica en: "&TipoSalida),"")')
ws[f"C{f_20}"] = f'="Indemnización de "&{num_txt("DiasPorAnio")}&" días por año de servicio"'
r += 1
f_subind = r
subtotal(r, "Subtotal indemnización", f"=SUM(F{f_indem}:F{f_20})", "TotalIndemnizacion")

r += 1
subtitulo(r, "C.  PRIMA DE ANTIGÜEDAD  (LFT art. 162)")
r += 1
f_pa = r
concepto(r, 9, "Prima de antigüedad",
         f"=IF(AND({OK},AplicaPrimaAnt=\"Sí\"),DiasPrimaAnt*AniosServicio,0)", f"=IF({OK},SalarioPrimaAnt,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},IF(AplicaPrimaAnt="Sí",{num_txt("DiasPrimaAnt")}&" días × "&FIXED(AniosServicio,4)&" años × "'
         f'&IF(PrimaAntPiso="Sí","salario mínimo (la base no puede ser menor, art. 485 LFT)",'
         f'IF(PrimaAntTopada="Sí","salario topado a "&{num_txt("VecesTope")}&IF(UnidadTope="UMA"," UMA"," salarios mínimos")&" ($"&FIXED(TopePrimaAnt,2)&" diarios)",'
         f'"salario "&IF(BasePrimaAnt="Base","base","integrado")&IF(ToparPrimaAnt="Sí"," (no rebasa el tope)",""))),'
         f'"No aplica: en renuncia se paga con "&{num_txt("AntMinRenuncia")}&" años cumplidos o más"),"")', alto=34)
r += 1
f_subpa = r
subtotal(r, "Subtotal prima de antigüedad", f"=SUM(F{f_pa}:F{f_pa})", "TotalPrimaAnt")

r += 2
f_total = r
ws.merge_cells(f"B{r}:E{r}")
ws[f"B{r}"] = "TOTAL A PAGAR  (bruto, antes de impuestos)"
ws[f"B{r}"].font = f(13, True, BLANCO)
ws[f"B{r}"].fill = relleno(NARANJA)
ws[f"B{r}"].alignment = Alignment(horizontal="right", vertical="center", indent=1)
c = ws[f"F{r}"]
c.value = f"=F{f_subfin}+F{f_subind}+F{f_subpa}"
c.number_format = FMT_MONEDA
c.font = f(14, True, BLANCO)
c.fill = relleno(NARANJA_INTENSO)
c.alignment = Alignment(horizontal="right", vertical="center")
nombrar("TotalLiquidacion", HOJA, abs_ref("F", r))
ws[f"G{r}"] = f'=IF(AND({OK},SueldoMensual>0),"Equivale a "&FIXED(TotalLiquidacion/SueldoMensual,1)&" meses de sueldo base","")'
ws[f"G{r}"].font = f(10, True, NARANJA_OSCURO)
ws[f"G{r}"].alignment = Alignment(vertical="center", indent=1)
ws.row_dimensions[r].height = 30

r += 2
notas = [
    "Notas:",
    "• Los importes son BRUTOS: todavía no se resta el ISR ni otras deducciones (préstamos, anticipos, etc.).",
    "• Salario diario integrado = salario diario × factor de integración (incluye la parte proporcional de aguinaldo y prima vacacional). El bono no integra.",
    "• Los conceptos 7, 8 y 9 usan la antigüedad con decimales (los días del año incompleto también cuentan).",
    "• La prima vacacional se paga sobre las vacaciones que se liquidan (conceptos 3 y 4).",
]
for t in notas:
    ws.merge_cells(f"B{r}:G{r}")
    ws[f"B{r}"] = t
    ws[f"B{r}"].font = f(9, t == "Notas:", GRIS_TEXTO, italic=t != "Notas:")
    ws[f"B{r}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[r].height = 16
    r += 1
f_fin_desglose = r - 1

# --- CÁLCULOS DE APOYO ----------------------------------------------------------------------
r += 1
FILA_APOYO = r
banda(r, "CÁLCULOS DE APOYO  (automáticos, no se tocan)", CARBON, 11, 22)
r += 1


def fila_apoyo(fila, texto, nombre, formula, fmt, explicacion, negrita=False):
    etiqueta(fila, texto, negrita)
    calculo(fila, nombre, formula, fmt, negrita=negrita)
    ws.merge_cells(f"E{fila}:G{fila}")
    c = ws[f"E{fila}"]
    c.value = explicacion
    c.font = f(9, color=GRIS_TEXTO, italic=not str(explicacion).startswith("="))
    c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[fila].height = 18


def sub_apoyo(fila, texto):
    ws[f"C{fila}"] = texto
    ws[f"C{fila}"].font = f(10, True, NARANJA_OSCURO)
    ws[f"C{fila}"].border = Border(bottom=naranja_lado)
    for col in "DEFG":
        ws[f"{col}{fila}"].border = Border(bottom=naranja_lado)
    ws.row_dimensions[fila].height = 20


sub_apoyo(r, "Revisión de datos")
r += 1
fila_apoyo(r, "¿Están completos los datos para calcular?", "DatosOK",
           "=IF(AND(ISNUMBER(FechaIngreso),ISNUMBER(FechaSalida),ISNUMBER(SueldoMensual)),"
           "IF(AND(FechaSalida>=FechaIngreso,SueldoMensual>0,DiasMes>0),\"Sí\",\"No\"),\"No\")",
           None, "Necesita fecha de ingreso, fecha de salida (posterior) y sueldo mensual.")
r += 1
fila_apoyo(r, "¿Se paga indemnización (conceptos 7 y 8)?", "AplicaIndem",
           "=IF(TipoSalida=INDEX(Lista_Tipo,1),\"Sí\",\"No\")", None,
           "Sólo en «Liquidación (la empresa termina)».")
r += 1
fila_apoyo(r, "¿Se paga prima de antigüedad (concepto 9)?", "AplicaPrimaAnt",
           "=IF(TipoSalida=INDEX(Lista_Tipo,2),IF(AniosCompletos>=AntMinRenuncia,\"Sí\",\"No\"),\"Sí\")", None,
           "En despido (con o sin causa) siempre; en renuncia sólo con 15 años o más (art. 162 LFT).")

r += 2
sub_apoyo(r, "Antigüedad")
r += 1
fila_apoyo(r, "Días de servicio (del ingreso a la salida, ambos cuentan)", "DiasServicio",
           f"=IF({OK},FechaSalida-FechaIngreso+1,0)", FMT_ENTERO, "Fecha de salida − fecha de ingreso + 1")
r += 1
fila_apoyo(r, "Años completos cumplidos", "AniosCompletos",
           f"=IF({OK},DATEDIF(FechaIngreso,FechaSalida+1,\"y\"),0)", FMT_ENTERO, "Aniversarios cumplidos al último día trabajado.")
r += 1
fila_apoyo(r, "Último aniversario", "UltimoAniv",
           f"=IF({OK},EDATE(FechaIngreso,12*AniosCompletos),\"\")", FMT_FECHA, "Fecha de ingreso + años completos.")
r += 1
fila_apoyo(r, "Días trabajados desde el último aniversario", "DiasDesdeAniv",
           f"=IF({OK},FechaSalida-UltimoAniv+1,0)", FMT_ENTERO, "Fracción del año de servicio que está corriendo.")
r += 1
fila_apoyo(r, "Antigüedad en años (con decimales)", "AniosServicio",
           f"=IF({OK},AniosCompletos+DiasDesdeAniv/365,0)", FMT_ANIOS,
           "Años completos + días desde el último aniversario ÷ 365.  Se usa en los conceptos 8 y 9.", negrita=True)
r += 1
fila_apoyo(r, "Año de servicio que está corriendo", "AnioServicioActual",
           f"=IF({OK},AniosCompletos+1,0)", FMT_ENTERO, "Define los días de vacaciones de la tabla (art. 76 LFT).")
r += 1
fila_apoyo(r, "Días trabajados en el año calendario de la salida", "DiasAnioCal",
           f"=IF({OK},MIN(365,FechaSalida-MAX(FechaIngreso,DATE(YEAR(FechaSalida),1,1))+1),0)", FMT_ENTERO,
           "Del 1 de enero (o del ingreso, si fue después) a la salida. Se usa para el aguinaldo.")

r += 2
sub_apoyo(r, "Vacaciones")
r += 1
fila_apoyo(r, "Días de vacaciones de la tabla para este año de servicio", "DiasVacTabla",
           f"=IF({OK},IFERROR(IF(INDEX(Vac_Empresa,MATCH(AnioServicioActual,Vac_Desde,1))=\"\","
           f"INDEX(Vac_Ley,MATCH(AnioServicioActual,Vac_Desde,1)),INDEX(Vac_Empresa,MATCH(AnioServicioActual,Vac_Desde,1))),0),0)",
           "0.##", "Columna «Días que da la empresa» de la hoja Tablas.")
r += 1
fila_apoyo(r, "Días de vacaciones al año que se usan", "DiasVacAnio",
           "=IF(ISNUMBER(DiasVacManual),DiasVacManual,DiasVacTabla)", "0.##",
           "Los de la tabla, salvo que hayas escrito otro número en el Paso 2.", negrita=True)
r += 1
fila_apoyo(r, "Días de prima vacacional al año", "DiasPrimaVacAnio",
           "=DiasVacAnio*PctPrimaVac", "0.00", "Días de vacaciones × % de prima vacacional.")

r += 2
sub_apoyo(r, "¿Cómo se integra el salario?")
for col, txt in zip("DEF", ["Diario", "Mensual", ""]):
    if txt:
        ws[f"{col}{r}"] = txt
        ws[f"{col}{r}"].font = f(9, True, NARANJA_OSCURO)
        ws[f"{col}{r}"].alignment = Alignment(horizontal="center")
r += 1


def fila_integ(fila, texto, nombre, f_diario, f_mensual, explicacion, negrita=False):
    etiqueta(fila, texto, negrita)
    calculo(fila, nombre, f_diario, FMT_MONEDA_SIMPLE, "D", negrita)
    calculo(fila, None, f_mensual, FMT_MONEDA_SIMPLE, "E", negrita)
    ws.merge_cells(f"F{fila}:G{fila}")
    c = ws[f"F{fila}"]
    c.value = explicacion
    c.font = f(9, color=GRIS_TEXTO, italic=not str(explicacion).startswith("="))
    c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[fila].height = 18


fila_integ(r, "Sueldo base", "SalarioDiario", f"=IF({OK},SueldoMensual/DiasMes,0)", f"=D{r}*DiasMes",
           f'="Sueldo mensual ÷ "&{num_txt("DiasMes")}&" días"')
f_sb = r
r += 1
fila_integ(r, "+ Parte proporcional de aguinaldo", "IntegAguinaldo", f"=SalarioDiario*DiasAguinaldo/365", f"=D{r}*DiasMes",
           f'="Salario diario × "&{num_txt("DiasAguinaldo")}&" días ÷ 365"')
r += 1
fila_integ(r, "+ Parte proporcional de prima vacacional", "IntegPrimaVac", f"=SalarioDiario*DiasPrimaVacAnio/365", f"=D{r}*DiasMes",
           f'="Salario diario × "&{num_txt("DiasVacAnio")}&" días × "&FIXED(PctPrimaVac*100,0)&"% ÷ 365"')
r += 1
fila_integ(r, "Salario diario integrado (SDI)", "SalarioIntegrado", f"=SalarioDiario*FactorIntegracion", f"=D{r}*DiasMes",
           "Salario diario × factor de integración.  Se usa en los conceptos 7 y 8.", negrita=True)
for col in "DE":
    ws[f"{col}{r}"].border = Border(top=Side(style="thin", color=CARBON), bottom=Side(style="double", color=CARBON))
f_sdi = r
r += 1
fila_apoyo(r, "Factor de integración", "FactorIntegracion",
           "=1+DiasAguinaldo/365+DiasPrimaVacAnio/365", FMT_FACTOR,
           f'="1 + "&{num_txt("DiasAguinaldo")}&"/365 + ("&{num_txt("DiasVacAnio")}&" × "&FIXED(PctPrimaVac*100,0)&"%)/365"')

r += 2
sub_apoyo(r, "Tope de la prima de antigüedad")
r += 1
fila_apoyo(r, "Salario mínimo: vigente desde", "FechaSM",
           f"=IF({OK},SUMPRODUCT(MAX((SM_Desde<=FechaSalida)*(SM_General<>\"\")*SM_Desde)),\"\")", FMT_FECHA,
           "El más reciente capturado en «Tablas» a la fecha de salida.")
r += 1
fila_apoyo(r, "Salario mínimo diario aplicable", "SalMinAplicable",
           f"=IF({OK},IFERROR(IF(ZonaSM=INDEX(Lista_Zona,2),INDEX(SM_Frontera,MATCH(FechaSM,SM_Desde,0)),"
           f"INDEX(SM_General,MATCH(FechaSM,SM_Desde,0))),0),0)", FMT_MONEDA_SIMPLE,
           f'=IF({OK},"Año "&IFERROR(YEAR(FechaSM),"—")&", zona "&ZonaSM,"")')
r += 1
fila_apoyo(r, "UMA: vigente desde", "FechaUMA",
           f"=IF({OK},SUMPRODUCT(MAX((UMA_Desde<=FechaSalida)*(UMA_Valor<>\"\")*UMA_Desde)),\"\")", FMT_FECHA,
           "Sólo se usa si el tope se mide en UMA.")
r += 1
fila_apoyo(r, "UMA diaria aplicable", "UMAAplicable",
           f"=IF({OK},IFERROR(INDEX(UMA_Valor,MATCH(FechaUMA,UMA_Desde,0)),0),0)", FMT_MONEDA_SIMPLE,
           "Tabla de UMA de la hoja «Tablas».")
r += 1
fila_apoyo(r, "Tope diario", "TopePrimaAnt",
           "=VecesTope*IF(UnidadTope=\"UMA\",UMAAplicable,SalMinAplicable)", FMT_MONEDA_SIMPLE,
           f'={num_txt("VecesTope")}&IF(UnidadTope="UMA"," × UMA diaria"," × salario mínimo diario")')
r += 1
fila_apoyo(r, "Salario antes del tope", "SalarioPrimaAntSinTope",
           "=IF(BasePrimaAnt=\"Base\",SalarioDiario,SalarioIntegrado)", FMT_MONEDA_SIMPLE,
           '="Salario "&IF(BasePrimaAnt="Base","base","integrado")&" (Paso 4)"')
r += 1
fila_apoyo(r, "¿Se topó?", "PrimaAntTopada",
           "=IF(AND(ToparPrimaAnt=\"Sí\",SalarioPrimaAntSinTope>TopePrimaAnt),\"Sí\",\"No\")", None,
           "Sí = el salario rebasa el tope y se usa el tope.")
r += 1
fila_apoyo(r, "¿Se subió al salario mínimo?", "PrimaAntPiso",
           "=IF(IF(PrimaAntTopada=\"Sí\",TopePrimaAnt,SalarioPrimaAntSinTope)<SalMinAplicable,\"Sí\",\"No\")", None,
           "La base nunca puede ser menor a 1 salario mínimo (art. 485 LFT).")
r += 1
fila_apoyo(r, "Salario diario para la prima de antigüedad", "SalarioPrimaAnt",
           "=MAX(IF(PrimaAntTopada=\"Sí\",TopePrimaAnt,SalarioPrimaAntSinTope),SalMinAplicable)", FMT_MONEDA_SIMPLE,
           "Se usa en el concepto 9.", negrita=True)
f_fin = r

# Valor de la tabla de vacaciones mostrado en el Paso 2
c = ws[f"D{fila_vac_tabla}"]
c.value = "=DiasVacTabla"
c.number_format = "0.##"
c.font = f(10, True)
c.fill = relleno(GRIS_CALC)
c.border = BORDE_CELDA
c.alignment = Alignment(horizontal="center", vertical="center")

# --- RESULTADO (arriba) ------------------------------------------------------------------
fr = FILA_RES + 1
for col, txt in zip("DEFG", ["Finiquito", "Indemnización", "Prima de antigüedad", "TOTAL A PAGAR (bruto)"]):
    c = ws[f"{col}{fr}"]
    c.value = txt
    c.font = f(9, True, GRIS_TEXTO if col != "G" else NARANJA_OSCURO)
    c.alignment = Alignment(horizontal="center", vertical="bottom")
ws[f"C{fr}"] = "=IF(Nombre=\"\",\"(sin nombre)\",Nombre)"
ws[f"C{fr}"].font = f(12, True, CARBON)
ws[f"C{fr}"].alignment = Alignment(vertical="bottom", indent=1)
fr += 1
for col, ref in zip("DEF", ["TotalFiniquito", "TotalIndemnizacion", "TotalPrimaAnt"]):
    c = ws[f"{col}{fr}"]
    c.value = f"={ref}"
    c.number_format = FMT_MONEDA
    c.font = f(12, True, CARBON)
    c.fill = relleno(GRIS_CALC)
    c.alignment = Alignment(horizontal="center", vertical="center")
c = ws[f"G{fr}"]
c.value = "=TotalLiquidacion"
c.number_format = FMT_MONEDA
c.font = f(20, True, BLANCO)
c.fill = relleno(NARANJA)
c.alignment = Alignment(horizontal="center", vertical="center")
ws[f"C{fr}"] = (f'=IF({OK},TipoSalida&"  ·  "&AniosCompletos&IF(AniosCompletos=1," año"," años")&" y "'
                f'&DiasDesdeAniv&IF(DiasDesdeAniv=1," día"," días")&" de antigüedad","")')
ws[f"C{fr}"].font = f(9, False, GRIS_TEXTO)
ws[f"C{fr}"].alignment = Alignment(vertical="top", wrap_text=True, indent=1)
fr += 1
FILA_ESTADO = fr
estado = (
    '=IF(NOT(ISNUMBER(FechaIngreso)),"⚠ Falta la fecha de ingreso (Paso 1).",'
    'IF(NOT(ISNUMBER(FechaSalida)),"⚠ Falta la fecha de salida (Paso 1).",'
    'IF(FechaSalida<FechaIngreso,"⚠ La fecha de salida es anterior a la de ingreso. Revísalas.",'
    'IF(OR(NOT(ISNUMBER(SueldoMensual)),SueldoMensual<=0),"⚠ Falta el sueldo mensual (Paso 1).",'
    'IF(SalMinAplicable=0,"⚠ No hay salario mínimo capturado para esa fecha (hoja Tablas).",'
    'IF(YEAR(FechaSM)<YEAR(FechaSalida),"⚠ Falta capturar el salario mínimo "&YEAR(FechaSalida)&" en la hoja Tablas; se usó el de "&YEAR(FechaSM)&".",'
    'IF(AND(UnidadTope="UMA",ToparPrimaAnt="Sí",UMAAplicable=0),"⚠ No hay UMA capturada para esa fecha (hoja Tablas).",'
    'IF(AND(UnidadTope="UMA",ToparPrimaAnt="Sí",YEAR(FechaUMA)<YEAR(FechaSalida),MONTH(FechaSalida)>1),"⚠ Falta capturar la UMA "&YEAR(FechaSalida)&" en la hoja Tablas; se usó la de "&YEAR(FechaUMA)&".",'
    'IF(DiasVacAnio*DiasDesdeAniv/365<DiasVacTomados,"⚠ Tomó más vacaciones de las que lleva ganadas este año; las proporcionales quedan en 0.",'
    '"✓ Listo. Revisa el desglose más abajo.")))))))))'
)
ws.merge_cells(f"C{fr}:F{fr}")
ws[f"C{fr}"] = estado
ws[f"C{fr}"].font = f(10, True, CARBON)
ws[f"C{fr}"].alignment = Alignment(vertical="center", indent=1, wrap_text=True)
ws[f"G{fr}"] = f'=IF(AND({OK},SueldoMensual>0),"Equivale a "&FIXED(TotalLiquidacion/SueldoMensual,1)&" meses de sueldo base","")'
ws[f"G{fr}"].font = f(9, True, NARANJA_OSCURO)
ws[f"G{fr}"].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[fr].height = 24

# Formato condicional: estado (verde / rojo) y conceptos en cero en gris
ws.conditional_formatting.add(
    f"C{FILA_ESTADO}:F{FILA_ESTADO}",
    FormulaRule(formula=[f'LEFT($C${FILA_ESTADO},1)="✓"'], fill=relleno(VERDE_OK), font=Font(name=FUENTE, bold=True, color=VERDE_OK_TXT)))
ws.conditional_formatting.add(
    f"C{FILA_ESTADO}:F{FILA_ESTADO}",
    FormulaRule(formula=[f'LEFT($C${FILA_ESTADO},1)="⚠"'], fill=relleno(ROJO_AVISO), font=Font(name=FUENTE, bold=True, color=ROJO_AVISO_TXT)))
for fila in cond_grises:
    ws.conditional_formatting.add(
        f"B{fila}:F{fila}",
        FormulaRule(formula=[f"$F${fila}=0"], font=Font(name=FUENTE, color="B0B0B0")))
# Aviso visual si la fecha de salida es anterior al ingreso
ws.conditional_formatting.add(
    "D15", FormulaRule(formula=["AND(ISNUMBER($D$15),ISNUMBER($D$14),$D$15<$D$14)"], fill=relleno(ROJO_AVISO)))

# Comentarios (ayuda al pasar el mouse)
ws["D16"].comment = Comment("Sueldo mensual nominal (base). Ejemplo: 45000.\nEl salario diario = sueldo mensual ÷ 30.", "Calculadora")
ws[f"F{f_total}"].comment = Comment("Suma de finiquito + indemnización + prima de antigüedad. Importe bruto (antes de ISR).", "Calculadora")

# Impresión
ws.print_area = f"A1:H{f_fin}"
ws.page_setup.orientation = "portrait"
ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.print_options.horizontalCentered = True
ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.6)
ws.row_breaks.append(Break(id=FILA_DESGLOSE - 1))
ws.row_breaks.append(Break(id=FILA_APOYO - 1))
ws.oddFooter.left.text = "Calculadora de liquidación · Confidencial"
ws.oddFooter.left.size = 8
ws.oddFooter.right.text = "Página &P de &N"
ws.oddFooter.right.size = 8

ws.protection.sheet = True
ws.sheet_view.selection[0].activeCell = "D11"
ws.sheet_view.selection[0].sqref = "D11"

# ======================================================================================
# HOJA: Instrucciones
# ======================================================================================
wsI = wb.create_sheet("Instrucciones", 1)
wsI.sheet_view.showGridLines = False
wsI.sheet_properties.tabColor = CARBON
wsI.column_dimensions["A"].width = 2
wsI.column_dimensions["B"].width = 6
wsI.column_dimensions["C"].width = 34
wsI.column_dimensions["D"].width = 90

wsI.merge_cells("B1:D1")
wsI["B1"] = "Cómo usar la calculadora"
wsI["B1"].font = f(20, True, BLANCO)
wsI["B1"].fill = relleno(NARANJA)
wsI["B1"].alignment = Alignment(vertical="center", indent=1)
wsI.row_dimensions[1].height = 42

fila = 3


def bloque_titulo(texto):
    global fila
    wsI.merge_cells(f"B{fila}:D{fila}")
    wsI[f"B{fila}"] = texto
    wsI[f"B{fila}"].font = f(12, True, BLANCO)
    wsI[f"B{fila}"].fill = relleno(CARBON)
    wsI[f"B{fila}"].alignment = Alignment(vertical="center", indent=1)
    wsI.row_dimensions[fila].height = 22
    fila += 1


def paso(numero, titulo, texto, alto=32):
    global fila
    wsI[f"B{fila}"] = numero
    wsI[f"B{fila}"].font = f(16, True, NARANJA)
    wsI[f"B{fila}"].alignment = Alignment(horizontal="center", vertical="center")
    wsI[f"C{fila}"] = titulo
    wsI[f"C{fila}"].font = f(11, True)
    wsI[f"C{fila}"].alignment = Alignment(vertical="center", wrap_text=True)
    wsI[f"D{fila}"] = texto
    wsI[f"D{fila}"].font = f(10)
    wsI[f"D{fila}"].alignment = Alignment(vertical="center", wrap_text=True)
    for col in "BCD":
        wsI[f"{col}{fila}"].border = Border(bottom=delgado)
    wsI.row_dimensions[fila].height = alto
    fila += 1


bloque_titulo("EN 4 PASOS")
paso(1, "Abre la pestaña «Calculadora»", "Todo se hace en esa hoja. Viene con un ejemplo: escribe encima los datos reales.")
paso(2, "Llena las celdas color durazno", "Nombre, fecha de ingreso, fecha de salida, sueldo mensual y tipo de salida (Paso 1). "
     "Luego los días pendientes y el bono (Paso 3). Si algo no aplica, pon 0.", 40)
paso(3, "Revisa las celdas color crema", "Aguinaldo y prima vacacional (Paso 2) vienen con el mínimo de ley; cámbialos si la empresa da más. "
     "La política GSK (Paso 4: 4 meses + 20 días, prima de antigüedad con tope de 2 salarios mínimos) normalmente no se toca.", 44)
paso(4, "Lee el resultado", "Arriba, en RESULTADO, está el total y un mensaje: verde = todo bien; rojo = te dice qué falta. "
     "Abajo está el desglose de cada concepto con su explicación. Para imprimir: Ctrl + P (ya está ajustada).", 44)

fila += 1
bloque_titulo("COLORES")
for color, borde, txt, desc in [
    (DURAZNO, BORDE_CAPTURA, "Durazno", "Captura obligatoria: datos del colaborador."),
    (CREMA, BORDE_CAPTURA, "Crema", "Opcional o política: ya trae un valor; cámbialo sólo si es distinto."),
    (GRIS_CALC, BORDE_CELDA, "Gris", "Automático: es una fórmula. No se escribe ahí (la hoja está protegida para evitar accidentes)."),
]:
    wsI[f"C{fila}"] = txt
    wsI[f"C{fila}"].fill = relleno(color)
    wsI[f"C{fila}"].border = borde
    wsI[f"C{fila}"].font = f(10, True)
    wsI[f"C{fila}"].alignment = Alignment(horizontal="center", vertical="center")
    wsI[f"D{fila}"] = desc
    wsI[f"D{fila}"].font = f(10)
    wsI[f"D{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    wsI.row_dimensions[fila].height = 22
    fila += 1

fila += 1
bloque_titulo("QUÉ SIGNIFICA CADA CONCEPTO")
conceptos = [
    ("Salario diario", "Sueldo mensual ÷ 30."),
    ("Factor de integración", "1 + días de aguinaldo/365 + (días de vacaciones × % prima vacacional)/365. "
     "Ej. con ley y 3er año de servicio: 1 + 15/365 + (16 × 25%)/365 = 1.0521."),
    ("Salario diario integrado (SDI)", "Salario diario × factor de integración. Es el sueldo + la parte proporcional diaria del aguinaldo y de la prima vacacional. "
     "Se usa para la indemnización (conceptos 7 y 8). El bono NO integra."),
    ("1. Sueldo pendiente", "Días trabajados que todavía no se pagan × salario diario."),
    ("2. Aguinaldo proporcional", "Días de aguinaldo × días trabajados en el año de la salida ÷ 365 × salario diario (art. 87 LFT)."),
    ("3. Vacaciones proporcionales", "Días de vacaciones del año de servicio que está corriendo × días desde el último aniversario ÷ 365, "
     "menos los que ya tomó (art. 79 LFT). Los días por año salen de la tabla de la ley (art. 76, reforma 2023)."),
    ("4. Vacaciones pendientes", "Vacaciones de años anteriores que no tomó × salario diario."),
    ("5. Prima vacacional", "% de prima vacacional × (días de vacaciones de los conceptos 3 y 4) × salario diario (art. 80 LFT)."),
    ("6. Bono", "Monto capturado; se paga completo y no forma parte del salario integrado."),
    ("7. Indemnización (TRL)", "Meses de indemnización × 30 días × SDI. La ley marca 3 meses (art. 50); GSK paga 4."),
    ("8. 20 días por año", "20 días × antigüedad en años con decimales × SDI."),
    ("9. Prima de antigüedad", "12 días × antigüedad en años con decimales × salario diario topado a 2 salarios mínimos (arts. 162, 485 y 486 LFT). "
     "Se paga en cualquier despido; en renuncia, sólo con 15 años o más."),
    ("Finiquito vs. liquidación", "Finiquito = lo ya ganado (conceptos 1 a 6). Liquidación = finiquito + indemnización + prima de antigüedad."),
]
for t, d in conceptos:
    wsI[f"C{fila}"] = t
    wsI[f"C{fila}"].font = f(10, True)
    wsI[f"C{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    wsI[f"D{fila}"] = d
    wsI[f"D{fila}"].font = f(10)
    wsI[f"D{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col in "CD":
        wsI[f"{col}{fila}"].border = Border(bottom=delgado)
    wsI.row_dimensions[fila].height = 30 if len(d) < 110 else 44
    fila += 1

fila += 1
bloque_titulo("QUÉ SE PAGA SEGÚN EL TIPO DE SALIDA")
for col, txt in zip("CD", ["Tipo de salida", "Conceptos que se pagan"]):
    wsI[f"{col}{fila}"] = txt
    wsI[f"{col}{fila}"].font = f(10, True)
    wsI[f"{col}{fila}"].fill = relleno(GRIS_BORDE)
fila += 1
for t, d in [
    (LISTA_TIPO[0], "Finiquito (1 a 6) + indemnización 4 meses (7) + 20 días por año (8) + prima de antigüedad (9)."),
    (LISTA_TIPO[1], "Finiquito (1 a 6). Prima de antigüedad (9) sólo si tiene 15 años cumplidos o más."),
    (LISTA_TIPO[2], "Finiquito (1 a 6) + prima de antigüedad (9). Sin indemnización."),
]:
    wsI[f"C{fila}"] = t
    wsI[f"C{fila}"].font = f(10, True)
    wsI[f"C{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    wsI[f"D{fila}"] = d
    wsI[f"D{fila}"].font = f(10)
    wsI[f"D{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col in "CD":
        wsI[f"{col}{fila}"].border = Border(bottom=delgado)
    wsI.row_dimensions[fila].height = 30
    fila += 1

fila += 1
bloque_titulo("MANTENIMIENTO (una vez al año) Y AVISOS")
for t in [
    "• Cada enero: captura el nuevo salario mínimo en la hoja «Tablas» (ya hay renglones listos para 2027 a 2030). "
    "Si falta, la calculadora usa el último que encuentre y te avisa en rojo.",
    "• Cada febrero: captura la nueva UMA en «Tablas» (sólo importa si el tope se mide en UMA).",
    "• Si la empresa da más días de vacaciones que la ley, cámbialos una sola vez en la columna crema de «Tablas».",
    "• Los importes son brutos: no incluyen ISR ni otras deducciones.",
    "• Las hojas están protegidas SIN contraseña sólo para que no se borren fórmulas por accidente. "
    "Si necesitas cambiar algo: Revisar → Desproteger hoja.",
    "• Para calcular a varias personas: clic derecho en la pestaña «Calculadora» → Mover o copiar → Crear una copia.",
]:
    wsI.merge_cells(f"B{fila}:D{fila}")
    wsI[f"B{fila}"] = t
    wsI[f"B{fila}"].font = f(10)
    wsI[f"B{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    wsI.row_dimensions[fila].height = 30
    fila += 1

wsI.protection.sheet = True
wsI.print_area = f"A1:D{fila}"
wsI.page_setup.fitToWidth = 1
wsI.page_setup.fitToHeight = 0
wsI.sheet_properties.pageSetUpPr.fitToPage = True

# Orden final de pestañas: Calculadora, Instrucciones, Tablas (abre en Calculadora)
wb._sheets = [ws, wsI, wsT]
wb.active = 0
for hoja in wb.worksheets:
    hoja.sheet_view.tabSelected = hoja is ws

wb.save(SALIDA)
print(f"OK -> {SALIDA}")
print({"desglose": FILA_DESGLOSE, "total": f_total, "apoyo": FILA_APOYO, "fin": f_fin})
