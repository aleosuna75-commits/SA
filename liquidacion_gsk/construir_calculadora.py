"""Construye la Calculadora de Liquidación de Personal (formato GSK).

Genera un .xlsx con fórmulas vivas (nada queda "pegado" como valor):
  - Calculadora : captura en 4 pasos; arriba el resultado (bruto, ISR y neto); abajo el
                  desglose por concepto, el cálculo del ISR y los cálculos de apoyo.
  - Instrucciones: cómo usarla, qué significa cada concepto y fundamento legal.
  - Tablas      : vacaciones (LFT art. 76), salario mínimo y UMA por vigencia,
                  tarifa mensual de ISR (art. 96 LISR) y listas de los menús.

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
NARANJA = "F36633"          # GSK orange (color primario de la marca)
NARANJA_INTENSO = "F25218"  # naranja profundo de gsk.com (totales)
NARANJA_OSCURO = "B8410F"   # texto naranja legible sobre fondos claros (derivado)
DURAZNO = "F8A385"          # captura obligatoria (durazno de gsk.com)
CREMA = "FDE4D9"            # captura opcional / política (tinte claro del naranja)
GRIS_CALC = "F0EFED"        # cálculo automático (blanco cálido de gsk.com)
GRIS_BORDE = "D5D1CE"       # divisores (gris cálido de gsk.com)
GRIS_TEXTO = "6B6763"
CARBON = "3A3A3A"           # bandas oscuras (gris carbón de gsk.com)
NEGRO_GSK = "151515"        # texto principal (casi negro de gsk.com)
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
BORDE_CELDA = Border(left=delgado, right=delgado, top=delgado, bottom=delgado)
BORDE_CAPTURA = Border(left=naranja_lado, right=naranja_lado, top=naranja_lado, bottom=naranja_lado)

FMT_MONEDA = '"$"#,##0.00;-"$"#,##0.00;"–"'
FMT_MONEDA_SIMPLE = '"$"#,##0.00'
FMT_DIAS = '#,##0.00;-#,##0.00;"–"'
FMT_ENTERO = '#,##0'
FMT_FECHA = '[$-80A]dd/mmm/yyyy'   # mes abreviado siempre en español
FMT_PCT = '0%'
FMT_PCT2 = '0.00%'
FMT_FACTOR = '0.0000'
FMT_ANIOS = '0.0000'

# --------------------------------------------------------------------------------------
# Datos de referencia (se capturan en la hoja Tablas; las fórmulas los buscan por fecha)
# --------------------------------------------------------------------------------------
# Salario mínimo diario: (año, vigente desde, general, zona libre frontera norte, fuente)
SALARIO_MINIMO = [
    (2017, dt.date(2017, 1, 1), 80.04, 80.04, "CONASAMI (zona única)"),
    (2018, dt.date(2018, 1, 1), 88.36, 88.36, "CONASAMI (zona única)"),
    (2019, dt.date(2019, 1, 1), 102.68, 176.72, "CONASAMI, tabla 2019"),
    (2020, dt.date(2020, 1, 1), 123.22, 185.56, "CONASAMI, tabla 2020 (DOF 23/12/2019)"),
    (2021, dt.date(2021, 1, 1), 141.70, 213.39, "CONASAMI, tabla 2021 (DOF 23/12/2020)"),
    (2022, dt.date(2022, 1, 1), 172.87, 260.34, "CONASAMI, tabla 2022 (DOF 08/12/2021)"),
    (2023, dt.date(2023, 1, 1), 207.44, 312.41, "CONASAMI, tabla 2023"),
    (2024, dt.date(2024, 1, 1), 248.93, 374.89, "CONASAMI, tabla 2024"),
    (2025, dt.date(2025, 1, 1), 278.80, 419.88, "CONASAMI, tabla 2025"),
    (2026, dt.date(2026, 1, 1), 315.04, 440.87, "CONASAMI, tabla 2026 (DOF 09/12/2025)"),
]
ANIOS_SM_FUTUROS = [2027, 2028, 2029, 2030]

# UMA diaria: (año, vigente desde, valor, fuente)
UMA = [
    (2016, dt.date(2016, 1, 28), 73.04, "DOF 27/01/2016 (valor inicial)"),
    (2017, dt.date(2017, 2, 1), 75.49, "INEGI, DOF 10/01/2017"),
    (2018, dt.date(2018, 2, 1), 80.60, "INEGI, comunicado 007/18"),
    (2019, dt.date(2019, 2, 1), 84.49, "INEGI, comunicado 06/19"),
    (2020, dt.date(2020, 2, 1), 86.88, "INEGI, comunicado 008/20"),
    (2021, dt.date(2021, 2, 1), 89.62, "INEGI, comunicado 008/21"),
    (2022, dt.date(2022, 2, 1), 96.22, "INEGI, comunicado 10/22"),
    (2023, dt.date(2023, 2, 1), 103.74, "INEGI, comunicado 10/23"),
    (2024, dt.date(2024, 2, 1), 108.57, "INEGI, comunicado 10/24"),
    (2025, dt.date(2025, 2, 1), 113.14, "INEGI, comunicado 1/25"),
    (2026, dt.date(2026, 2, 1), 117.31, "INEGI, comunicado 1/26"),
]
ANIOS_UMA_FUTUROS = [2027, 2028, 2029, 2030]

# Tarifa mensual de ISR para retenciones (art. 96 LISR, Anexo 8 RMF):
# (límite inferior, límite superior o None, cuota fija, % sobre el excedente del límite inferior)
TARIFA_ISR = [
    (0.01, 844.59, 0.00, 0.0192),
    (844.60, 7168.51, 16.22, 0.0640),
    (7168.52, 12598.02, 420.95, 0.1088),
    (12598.03, 14644.64, 1011.68, 0.1600),
    (14644.65, 17533.64, 1339.14, 0.1792),
    (17533.65, 35362.83, 1856.84, 0.2136),
    (35362.84, 55736.68, 5665.16, 0.2352),
    (55736.69, 106410.50, 10457.09, 0.3000),
    (106410.51, 141880.66, 25659.23, 0.3200),
    (141880.67, 425641.99, 37009.69, 0.3400),
    (425642.00, None, 133488.54, 0.3500),
]
TARIFA_ISR_ANIO = 2026
TARIFA_ISR_FUENTE = "Anexo 8 RMF 2026, apartado B.V (DOF 28/12/2025). Rige desde 01/01/2026."
# Subsidio para el empleo 2026 (decreto DOF 31/12/2025): 15.02% de la UMA mensual si el ingreso
# gravado ordinario del mes no pasa de $11,492.66.
SUBSIDIO_PCT = 0.1502
SUBSIDIO_LIMITE = 11492.66
SUBSIDIO_FUENTE = "Decreto del subsidio para el empleo, DOF 31/12/2025 (vigente desde 01/01/2026)"

# Vacaciones LFT art. 76 (reforma DOF 27/12/2022, vigente desde 01/01/2023)
VACACIONES = [(1, 1, 12), (2, 2, 14), (3, 3, 16), (4, 4, 18), (5, 5, 20)]
_d = 22
for desde in range(6, 101, 5):
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
LISTA_COBERTURA = ["Indemnización (7 y 8)", "Indemnización y prima de antigüedad (7, 8 y 9)"]

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
    "DiasSueldoPend": 0,
    "DiasVacPend": 0,
    "DiasVacTomados": 0,
    "AguinaldoPagadoDias": 0,
    "OtrasPrestInteg": 0,
    "Bono": 0,
    "OtrasDeducciones": 0,
}

wb = Workbook()


def nombrar(nombre, hoja, ref):
    """Define un nombre de libro (ej. FechaIngreso -> 'Calculadora'!$D$16)."""
    wb.defined_names[nombre] = DefinedName(nombre, attr_text=f"'{hoja}'!{ref}")


def abs_ref(col, fila):
    return f"${col}${fila}"


def num_txt(expr):
    """Texto de un número: sin decimales si es entero, con 2 si no (FIXED no depende del idioma)."""
    return f'IF(ROUND({expr},2)=INT({expr}),FIXED({expr},0),FIXED({expr},2))'


def seguro_txt(x):
    """Envuelve un texto-fórmula en IFERROR para que nunca muestre #¡VALOR!."""
    if isinstance(x, str) and x.startswith("=") and not x.startswith("=IFERROR("):
        return f'=IFERROR({x[1:]},"")'
    return x


SIN_GUARDA = {"DatosOK", "ListasOK", "TextoOK", "NegOK", "PoliticaOK", "AplicaIndem", "AplicaPrimaAnt"}


def guardar(formula, nombre, fmt):
    """Si faltan datos, los cálculos de apoyo dan 0 (y nunca un error)."""
    if not (isinstance(formula, str) and formula.startswith("=")) or nombre in SIN_GUARDA:
        return formula
    if fmt is None:
        return f'=IFERROR({formula[1:]},"No")'
    return f'=IF(DatosOK="Sí",{formula[1:]},0)'


def pesos(expr):
    return f'"$"&FIXED({expr},2)'


def isr_tarifa(x):
    """ISR de la tarifa mensual del art. 96 para el ingreso x (0 si x <= 0)."""
    m = f"MATCH({x},ISR_LimInf,1)"
    return (f"IF({x}<0.01,0,INDEX(ISR_Cuota,{m})+({x}-INDEX(ISR_LimInf,{m}))*INDEX(ISR_Tasa,{m}))")


# ======================================================================================
# HOJA: Tablas (se construye primero porque las demás usan sus nombres)
# ======================================================================================
wsT = wb.active
wsT.title = "Tablas"
wsT.sheet_view.showGridLines = False
wsT.sheet_properties.tabColor = GRIS_BORDE
for col, ancho in {"A": 2, "B": 16, "C": 16, "D": 20, "E": 22, "F": 40, "G": 3, "H": 44}.items():
    wsT.column_dimensions[col].width = ancho

wsT.merge_cells("B1:F1")
wsT["B1"] = "TABLAS DE REFERENCIA"
wsT["B1"].font = f(16, True, BLANCO)
wsT["B1"].fill = relleno(NARANJA)
wsT["B1"].alignment = Alignment(vertical="center", indent=1)
wsT.row_dimensions[1].height = 30
wsT.merge_cells("B2:F2")
wsT["B2"] = ("Las celdas color durazno claro se actualizan una vez al año (salario mínimo en enero, UMA en febrero, "
             "tarifa de ISR cuando el SAT la cambie). Lo gris está protegido para que no se borre por accidente.")
wsT["B2"].font = f(9, italic=True, color=GRIS_TEXTO)
wsT["B2"].alignment = Alignment(wrap_text=True, vertical="center")
wsT.row_dimensions[2].height = 28


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
        c.font = f(9, True)
        c.fill = relleno(GRIS_BORDE)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDE_CELDA
    ws.row_dimensions[fila].height = 30


def celda_fija(ws, ref, valor, fmt=None):
    c = ws[ref]
    c.value = valor
    c.font = f(10)
    c.alignment = Alignment(horizontal="center")
    c.fill = relleno(GRIS_CALC)
    c.border = BORDE_CELDA
    if fmt:
        c.number_format = fmt


def celda_editable(ws, ref, valor, fmt=None):
    c = ws[ref]
    c.value = valor
    c.font = f(10, True)
    c.alignment = Alignment(horizontal="center")
    c.fill = relleno(CREMA)
    c.border = BORDE_CAPTURA
    c.protection = Protection(locked=False)
    if fmt:
        c.number_format = fmt


def celda_fuente(ws, ref, valor):
    c = ws[ref]
    c.value = valor
    c.font = f(8, italic=True, color=GRIS_TEXTO)
    c.alignment = Alignment(wrap_text=True, vertical="center")
    c.border = BORDE_CELDA
    c.protection = Protection(locked=False)


# --- Vacaciones -----------------------------------------------------------------------
r = 4
titulo_tabla(wsT, r, "VACACIONES POR AÑO DE SERVICIO  (LFT art. 76, reforma vigente desde 01/01/2023)")
r += 1
encabezados(wsT, r, "BCDEF", ["Desde el año\nde servicio", "Hasta el año\nde servicio", "Días por ley",
                               "Días que da la empresa\n(editable)", "Nota"])
r += 1
vac_ini = r
for desde, hasta, dias in VACACIONES:
    celda_fija(wsT, f"B{r}", desde)
    celda_fija(wsT, f"C{r}", hasta)
    celda_fija(wsT, f"D{r}", dias)
    celda_editable(wsT, f"E{r}", dias)
    wsT[f"F{r}"].border = BORDE_CELDA
    r += 1
vac_fin = r - 1
wsT[f"F{vac_ini}"] = "Si la empresa da más días que la ley, cámbialos en la columna «Días que da la empresa»."
wsT[f"F{vac_ini}"].font = f(9, italic=True, color=GRIS_TEXTO)
wsT[f"F{vac_ini}"].alignment = Alignment(wrap_text=True, vertical="top")
wsT.merge_cells(f"F{vac_ini}:F{vac_ini + 3}")
nombrar("Vac_Desde", "Tablas", f"$B${vac_ini}:$B${vac_fin}")
nombrar("Vac_Ley", "Tablas", f"$D${vac_ini}:$D${vac_fin}")
nombrar("Vac_Empresa", "Tablas", f"$E${vac_ini}:$E${vac_fin}")

# --- Salario mínimo ---------------------------------------------------------------------
r += 1
titulo_tabla(wsT, r, "SALARIO MÍNIMO DIARIO  (tope y piso de la prima de antigüedad, LFT arts. 162, 485 y 486)")
r += 1
encabezados(wsT, r, "BCDEF", ["Año", "Vigente desde", "Zona general", "Zona Libre de la\nFrontera Norte", "Fuente"])
r += 1
sm_ini = r
for anio, desde, gen, zlfn, fuente in SALARIO_MINIMO + [
        (a, dt.date(a, 1, 1), None, None, "Capturar cuando se publique en el DOF (diciembre)") for a in ANIOS_SM_FUTUROS]:
    celda_fija(wsT, f"B{r}", anio, "0")
    celda_fija(wsT, f"C{r}", desde, FMT_FECHA)
    celda_editable(wsT, f"D{r}", gen, FMT_MONEDA_SIMPLE)
    celda_editable(wsT, f"E{r}", zlfn, FMT_MONEDA_SIMPLE)
    celda_fuente(wsT, f"F{r}", fuente)
    r += 1
sm_fin = r - 1
nombrar("SM_Anio", "Tablas", f"$B${sm_ini}:$B${sm_fin}")
nombrar("SM_Desde", "Tablas", f"$C${sm_ini}:$C${sm_fin}")
nombrar("SM_General", "Tablas", f"$D${sm_ini}:$D${sm_fin}")
nombrar("SM_Frontera", "Tablas", f"$E${sm_ini}:$E${sm_fin}")

# --- UMA --------------------------------------------------------------------------------
r += 1
titulo_tabla(wsT, r, "UMA DIARIA  (partes exentas de ISR, LISR art. 93 fracciones XIII y XIV)")
r += 1
encabezados(wsT, r, "BCDEF", ["Año", "Vigente desde", "UMA diaria", "", "Fuente"])
r += 1
uma_ini = r
for anio, desde, valor, fuente in UMA + [
        (a, dt.date(a, 2, 1), None, "Capturar cuando la publique el INEGI (enero)") for a in ANIOS_UMA_FUTUROS]:
    celda_fija(wsT, f"B{r}", anio, "0")
    celda_fija(wsT, f"C{r}", desde, FMT_FECHA)
    celda_editable(wsT, f"D{r}", valor, FMT_MONEDA_SIMPLE)
    celda_fuente(wsT, f"F{r}", fuente)
    r += 1
uma_fin = r - 1
nombrar("UMA_Desde", "Tablas", f"$C${uma_ini}:$C${uma_fin}")
nombrar("UMA_Valor", "Tablas", f"$D${uma_ini}:$D${uma_fin}")

# --- Tarifa ISR -------------------------------------------------------------------------
r += 1
wsT.row_breaks.append(Break(id=r))
titulo_tabla(wsT, r, "TARIFA MENSUAL DE ISR 2026  (LISR art. 96; ISR del finiquito y tasa del último sueldo para la indemnización)")
r += 1
encabezados(wsT, r, "BCDEF", ["Límite inferior", "Límite superior", "Cuota fija", "% sobre el excedente\ndel límite inferior", "Fuente"])
r += 1
isr_ini = r
for li, ls, cuota, tasa in TARIFA_ISR:
    celda_editable(wsT, f"B{r}", li, '#,##0.00')
    celda_editable(wsT, f"C{r}", ls if ls is not None else "En adelante", '#,##0.00')
    celda_editable(wsT, f"D{r}", cuota, '#,##0.00')
    celda_editable(wsT, f"E{r}", tasa, FMT_PCT2)
    celda_fuente(wsT, f"F{r}", TARIFA_ISR_FUENTE if r == isr_ini else None)
    r += 1
isr_fin = r - 1
nombrar("ISR_LimInf", "Tablas", f"$B${isr_ini}:$B${isr_fin}")
nombrar("ISR_Cuota", "Tablas", f"$D${isr_ini}:$D${isr_fin}")
nombrar("ISR_Tasa", "Tablas", f"$E${isr_ini}:$E${isr_fin}")
wsT[f"B{r}"] = "Año desde el que rige esta tarifa:"
wsT[f"B{r}"].font = f(9, True)
wsT.merge_cells(f"B{r}:C{r}")
celda_editable(wsT, f"D{r}", TARIFA_ISR_ANIO, "0")
nombrar("ISR_AnioTarifa", "Tablas", f"$D${r}")
celda_fuente(wsT, f"F{r}", "Si la salida es de un año anterior, la calculadora te avisa.")
r += 2
titulo_tabla(wsT, r, "SUBSIDIO PARA EL EMPLEO  (sólo para sueldos bajos; nunca se aplica a la indemnización)")
r += 1
encabezados(wsT, r, "BCDEF", ["% de la UMA\nmensual", "", "Ingreso mensual\nmáximo", "", "Fuente"])
r += 1
celda_editable(wsT, f"B{r}", SUBSIDIO_PCT, FMT_PCT2)
celda_editable(wsT, f"D{r}", SUBSIDIO_LIMITE, FMT_MONEDA_SIMPLE)
celda_fuente(wsT, f"F{r}", SUBSIDIO_FUENTE)
nombrar("SubsidioPct", "Tablas", f"$B${r}")
nombrar("SubsidioLimite", "Tablas", f"$D${r}")
isr_fin = r

# --- Listas para menús desplegables -------------------------------------------------------
titulo_tabla(wsT, 4, "LISTAS DE LOS MENÚS (no modificar)", "H", "H")
fila_lista = 5
for nombre_lista, valores in [("Lista_Tipo", LISTA_TIPO), ("Lista_Zona", LISTA_ZONA), ("Lista_SiNo", LISTA_SINO),
                              ("Lista_Base", LISTA_BASE), ("Lista_Cobertura", LISTA_COBERTURA)]:
    wsT[f"H{fila_lista}"] = nombre_lista.replace("Lista_", "Lista: ")
    wsT[f"H{fila_lista}"].font = f(8, True, GRIS_TEXTO)
    ini = fila_lista + 1
    for i, v in enumerate(valores):
        celda_fija(wsT, f"H{ini + i}", v)
        wsT[f"H{ini + i}"].alignment = Alignment(horizontal="left", indent=1)
    nombrar(nombre_lista, "Tablas", f"$H${ini}:$H${ini + len(valores) - 1}")
    fila_lista = ini + len(valores) + 1

wsT.protection.sheet = True
wsT.freeze_panes = "A4"
wsT.print_area = f"A1:H{isr_fin}"
wsT.page_setup.orientation = "landscape"
wsT.page_setup.fitToWidth = 1
wsT.page_setup.fitToHeight = 0
wsT.sheet_properties.pageSetUpPr.fitToPage = True

# ======================================================================================
# HOJA: Calculadora
# ======================================================================================
ws = wb.create_sheet("Calculadora", 0)
ws.sheet_view.showGridLines = False
ws.sheet_view.zoomScale = 90
ws.sheet_properties.tabColor = NARANJA
for col, ancho in {"A": 2, "B": 5, "C": 50, "D": 19, "E": 21, "F": 21, "G": 62, "H": 2}.items():
    ws.column_dimensions[col].width = ancho

HOJA = "Calculadora"
cond_grises = []      # filas que se ven grises cuando su importe es cero


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


def captura(fila, nombre, valor, fmt=None, obligatorio=True, alinear="center", ancho_doble=False):
    c = ws[f"D{fila}"]
    c.value = valor
    c.font = f(11 if obligatorio else 10, True, "000000")
    c.fill = relleno(DURAZNO if obligatorio else CREMA)
    c.border = BORDE_CAPTURA
    c.alignment = Alignment(horizontal=alinear, vertical="center", shrink_to_fit=(alinear == "left"))
    c.protection = Protection(locked=False)
    if fmt:
        c.number_format = fmt
    if ancho_doble:
        e = ws[f"E{fila}"]
        e.fill = relleno(DURAZNO if obligatorio else CREMA)
        e.border = BORDE_CAPTURA
        e.protection = Protection(locked=False)
        ws.merge_cells(f"D{fila}:E{fila}")
    nombrar(nombre, HOJA, abs_ref("D", fila))
    ws.row_dimensions[fila].height = 20
    return c


MESES = ('"enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"')


def fecha_txt(x):
    return f'DAY({x})&" de "&CHOOSE(MONTH({x}),{MESES})&" de "&YEAR({x})'


def confirmacion(fila, formula):
    c = ws[f"E{fila}"]
    c.value = formula
    c.font = f(9, True, VERDE_OK_TXT)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1, shrink_to_fit=True)


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


def validacion(tipo, operador=None, f1=None, f2=None, titulo="", error="", prompt=None, blanco=True):
    dv = DataValidation(type=tipo, operator=operador, formula1=f1, formula2=f2, allow_blank=blanco)
    dv.errorTitle = titulo
    dv.error = error
    dv.showErrorMessage = True
    if prompt:
        dv.promptTitle = titulo
        dv.prompt = prompt
        dv.showInputMessage = True
    ws.add_data_validation(dv)
    return dv


dv_fecha = validacion("date", "between", "18264", "73415", "Fecha",
                      "Escribe la fecha como 15/03/2019 (día/mes/año). Si tu computadora está en inglés y no la acepta, "
                      "escríbela como 2019-03-15 (año-mes-día).",
                      "Día/mes/año, por ejemplo 15/03/2019. A la derecha verás cómo la leyó Excel.")
dv_dinero = validacion("decimal", "greaterThanOrEqual", "0", None, "Monto no válido",
                       "Escribe sólo el número, sin signo de pesos ni letras. Ej. 45000")
dv_dias = validacion("decimal", "between", "0", "400", "Número de días no válido",
                     "Escribe un número de días entre 0 y 400 (puede llevar decimales).")
dv_pct = validacion("decimal", "between", "0", "5", "Porcentaje no válido", "Escribe el porcentaje, por ejemplo 25%.")
dv_pos = validacion("decimal", "between", "0", "1000", "Valor no válido", "Escribe un número positivo.")


def lista(nombre_lista, titulo):
    return validacion("list", None, nombre_lista, None, titulo,
                      "Elige una opción de la lista (flechita a la derecha de la celda).",
                      "Elige una opción de la lista.", blanco=False)


# --- Encabezado -------------------------------------------------------------------------
ws.merge_cells("B1:G1")
ws["B1"] = "GSK  ·  Calculadora de Liquidación de Personal"
ws["B1"].font = f(20, True, BLANCO)
ws["B1"].fill = relleno(NARANJA)
ws["B1"].alignment = Alignment(vertical="center", indent=1)
ws.row_dimensions[1].height = 42
ws.merge_cells("B2:G2")
ws["B2"] = ("Llena las celdas DURAZNO. Las de color CLARO ya traen un valor: cámbialas sólo si es distinto. "
            "Lo GRIS se calcula solo. ¿Dudas? Pestaña «Instrucciones».")
ws["B2"].font = f(10)
ws["B2"].alignment = Alignment(vertical="center", indent=1)
for col in "BCDEFG":
    ws[f"{col}2"].border = Border(bottom=naranja_lado)
ws.row_dimensions[2].height = 22

ws["C3"] = "Colores:"
ws["C3"].font = f(9, True, GRIS_TEXTO)
ws["C3"].alignment = Alignment(horizontal="right", vertical="center")
for col, txt, color, borde in [("D", "Durazno = llenar", DURAZNO, BORDE_CAPTURA), ("E", "Claro = ya trae valor", CREMA, BORDE_CAPTURA),
                               ("F", "Gris = automático", GRIS_CALC, BORDE_CELDA)]:
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

# --- PASO 1 -----------------------------------------------------------------------------
r = FILA_RES + 7
banda(r, "PASO 1 ·  DATOS DEL COLABORADOR")
r += 1
etiqueta(r, "Nombre completo"); captura(r, "Nombre", EJEMPLO["Nombre"], alinear="left", ancho_doble=True)
ayuda(r, "Como aparecerá en el resultado.", "F", "G")
r += 1
etiqueta(r, "Número de empleado (opcional)")
captura(r, "NumEmpleado", EJEMPLO["NumEmpleado"], "@", obligatorio=False, alinear="left", ancho_doble=True)
ayuda(r, "Opcional.", "F", "G")
r += 1
etiqueta(r, "Puesto (opcional)")
captura(r, "Puesto", EJEMPLO["Puesto"], obligatorio=False, alinear="left", ancho_doble=True)
ayuda(r, "Opcional.", "F", "G")
r += 1
FILA_INGRESO = r
etiqueta(r, "Fecha de ingreso"); captura(r, "FechaIngreso", EJEMPLO["FechaIngreso"], FMT_FECHA)
dv_fecha.add(f"D{r}")
confirmacion(r, f'=IFERROR(IF(ISNUMBER(FechaIngreso),"Se leyó: "&{fecha_txt("FechaIngreso")},""),"")')
ayuda(r, "Día/mes/año (15/03/2019). Revisa que a la izquierda diga la fecha correcta.", "F", "G")
ws[f"D{r}"].comment = Comment("Si le reconocen antigüedad de otra empresa del grupo, pon esa fecha. "
                              "Si el patrón anterior ya le pagó parte del aguinaldo de este año, captúralo en el Paso 3.", "Calculadora")
r += 1
FILA_SALIDA = r
etiqueta(r, "Fecha de salida (último día trabajado)"); captura(r, "FechaSalida", EJEMPLO["FechaSalida"], FMT_FECHA)
dv_fecha.add(f"D{r}")
confirmacion(r, f'=IFERROR(IF(ISNUMBER(FechaSalida),"Se leyó: "&{fecha_txt("FechaSalida")},""),"")')
ayuda(r, "El último día que trabajó (ese día sí cuenta).", "F", "G")
r += 1
FILA_SUELDO = r
etiqueta(r, "Sueldo mensual bruto (base)"); captura(r, "SueldoMensual", EJEMPLO["SueldoMensual"], FMT_MONEDA_SIMPLE)
dv_dinero.add(f"D{r}")
confirmacion(r, f'=IFERROR(IF(AND(ISNUMBER(SueldoMensual),ISNUMBER(DiasMes),DiasMes>0),"= "&{pesos("SueldoMensual/DiasMes")}&" diarios",""),"")')
ayuda(r, "Sueldo nominal del mes, sin bonos ni prestaciones. Sólo el número: 45000", "F", "G")
r += 1
etiqueta(r, "Tipo de salida")
captura(r, "TipoSalida", EJEMPLO["TipoSalida"], alinear="left", ancho_doble=True)
ws[f"D{r}"].font = f(10, True, "000000")
lista("Lista_Tipo", "Tipo de salida").add(f"D{r}")
ayuda(r, "Elige de la lista. Define qué conceptos se pagan.", "F", "G")
r += 1
etiqueta(r, "Zona de salario mínimo")
captura(r, "ZonaSM", EJEMPLO["ZonaSM"], obligatorio=False, alinear="left", ancho_doble=True)
lista("Lista_Zona", "Zona de salario mínimo").add(f"D{r}")
ayuda(r, "«General» para casi todo el país. Frontera Norte sólo en esos municipios.", "F", "G")

# --- PASO 2 -----------------------------------------------------------------------------
r += 2
banda(r, "PASO 2 ·  PRESTACIONES  (vienen con el mínimo de ley; cámbialas si la empresa da más)")
r += 1
etiqueta(r, "Días de aguinaldo al año"); captura(r, "DiasAguinaldo", EJEMPLO["DiasAguinaldo"], "General", obligatorio=False)
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
captura(r, "DiasVacManual", None, "General", obligatorio=False)
dv_dias.add(f"D{r}")
ayuda(r, "Déjala vacía (o en 0) para usar la tabla. Si escribes un número, se usa ese.")
r += 1
etiqueta(r, "Otras prestaciones fijas que integran ($ al mes, opcional)")
captura(r, "OtrasPrestInteg", EJEMPLO["OtrasPrestInteg"], FMT_MONEDA_SIMPLE, obligatorio=False)
dv_dinero.add(f"D{r}")
ayuda(r, "Vales de despensa, fondo de ahorro (parte de la empresa), etc. Se suman al salario integrado. El bono NO va aquí.")

# --- PASO 3 -----------------------------------------------------------------------------
r += 2
banda(r, "PASO 3 ·  PENDIENTES DE PAGO, BONO Y DESCUENTOS")
r += 1
etiqueta(r, "Días que trabajó y todavía no se le pagan"); captura(r, "DiasSueldoPend", EJEMPLO["DiasSueldoPend"], "General")
dv_dias.add(f"D{r}")
ayuda(r, "Ej. los días de la quincena en curso. Si ya se le pagó todo, pon 0.")
r += 1
etiqueta(r, "Saldo de vacaciones ya ganadas y no tomadas (días)"); captura(r, "DiasVacPend", EJEMPLO["DiasVacPend"], "General")
dv_dias.add(f"D{r}")
ayuda(r, "Lo que tiene pendiente de aniversarios YA cumplidos (según el control de vacaciones). El año que está corriendo se calcula solo.")
r += 1
etiqueta(r, "¿La prima vacacional de ese saldo ya se pagó?"); captura(r, "PVSaldoPagada", "No", obligatorio=False)
lista("Lista_SiNo", "¿Prima vacacional del saldo ya pagada?").add(f"D{r}")
ayuda(r, "Sí sólo si la empresa ya pagó la prima de esos días (por ejemplo, en el aniversario). Evita pagarla doble.")
r += 1
etiqueta(r, "Días de vacaciones tomados por adelantado (opcional)"); captura(r, "DiasVacTomados", EJEMPLO["DiasVacTomados"], "General", obligatorio=False)
dv_dias.add(f"D{r}")
ayuda(r, "Sólo si ya usó todo su saldo y tomó días del año en curso que aún no ganaba. Se restan del concepto 3.")
r += 1
etiqueta(r, "Días de aguinaldo de este año ya pagados (opcional)")
captura(r, "AguinaldoPagadoDias", EJEMPLO["AguinaldoPagadoDias"], "General", obligatorio=False)
dv_dias.add(f"D{r}")
ayuda(r, "Ej. si sale en diciembre y ya cobró su aguinaldo, o si recibió un anticipo. Si no, déjalo en 0.")
r += 1
etiqueta(r, "Bono a pagar en la liquidación ($)"); captura(r, "Bono", EJEMPLO["Bono"], FMT_MONEDA_SIMPLE)
dv_dinero.add(f"D{r}")
ayuda(r, "Se paga completo, pero NO se suma al salario integrado. Si no hay, pon 0.")
r += 1
etiqueta(r, "Otros descuentos ($): préstamos, anticipos, etc."); captura(r, "OtrasDeducciones", EJEMPLO["OtrasDeducciones"], FMT_MONEDA_SIMPLE)
dv_dinero.add(f"D{r}")
ayuda(r, "Se restan al final, después del ISR. Si no hay, pon 0.")

# --- PASO 4 -----------------------------------------------------------------------------
r += 2
banda(r, "PASO 4 ·  POLÍTICA DE PAGO GSK  (normalmente no se toca)", CARBON)
r += 1
etiqueta(r, "Meses de indemnización (TRL)"); captura(r, "MesesIndem", 4, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "Ley: 3 meses (art. 123 constitucional; arts. 48 y 50 LFT). GSK paga 4 meses de salario integrado.")
r += 1
etiqueta(r, "Días de indemnización por cada año de servicio"); captura(r, "DiasPorAnio", 20, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "GSK paga 20 días de salario integrado por año (con fracción). Es política: la ley sólo lo exige en ciertos casos (arts. 49 a 52).")
r += 1
etiqueta(r, "¿Poner tope a la indemnización?"); captura(r, "ToparIndem", "Sí", obligatorio=False)
lista("Lista_SiNo", "¿Topar la indemnización?").add(f"D{r}")
ayuda(r, "Sí = la indemnización no puede pasar del número de años de salario integrado de abajo.")
r += 1
etiqueta(r, "Tope: años de salario integrado"); captura(r, "AniosTopeIndem", 2, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "Viene en 2 años (2 × 365 días de salario integrado). Muévelo si la política es otra.")
r += 1
etiqueta(r, "¿Qué conceptos cubre el tope?")
captura(r, "CoberturaTope", LISTA_COBERTURA[0], obligatorio=False, alinear="left", ancho_doble=True)
ws[f"D{r}"].font = f(9, True, "000000")
lista("Lista_Cobertura", "Conceptos que cubre el tope").add(f"D{r}")
ayuda(r, "El finiquito (1 a 6) nunca se topa: ya lo ganó.", "F", "G")
r += 1
etiqueta(r, "Días de prima de antigüedad por año"); captura(r, "DiasPrimaAnt", 12, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "Ley: 12 días por año de servicio (art. 162 LFT).")
r += 1
etiqueta(r, "¿Topar el salario de la prima de antigüedad?"); captura(r, "ToparPrimaAnt", "Sí", obligatorio=False)
lista("Lista_SiNo", "¿Topar la prima de antigüedad?").add(f"D{r}")
ayuda(r, "Sí = como dice la ley: el salario diario no pasa del tope de abajo.")
r += 1
etiqueta(r, "Tope de la prima: veces el salario mínimo"); captura(r, "VecesTope", 2, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "Ley: 2 salarios mínimos diarios (arts. 485 y 486 LFT).")
r += 1
etiqueta(r, "Salario para la prima de antigüedad"); captura(r, "BasePrimaAnt", LISTA_BASE[0], obligatorio=False)
lista("Lista_Base", "Salario para prima de antigüedad").add(f"D{r}")
ayuda(r, "Integrado (con aguinaldo y prima vacacional) o Base (sólo sueldo). Luego se aplica el tope.")
r += 1
etiqueta(r, "Años mínimos para pagar prima de antigüedad en renuncia"); captura(r, "AntMinRenuncia", 15, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "Ley: 15 años (art. 162 LFT). Sólo aplica en renuncia voluntaria.")
r += 1
etiqueta(r, "Días por mes"); captura(r, "DiasMes", 30, "General", obligatorio=False)
dv_pos.add(f"D{r}")
ayuda(r, "Sueldo mensual ÷ 30 = salario diario (art. 89 LFT). Normalmente 30.")

# --- DESGLOSE ---------------------------------------------------------------------------
OK = 'DatosOK="Sí"'


def encabezado_tabla(fila, textos):
    for col, txt in zip("BCDEFG", textos):
        c = ws[f"{col}{fila}"]
        c.value = txt
        c.font = f(10, True, BLANCO)
        c.fill = relleno(CARBON)
        c.alignment = Alignment(horizontal={"G": "left", "E": "right", "F": "right"}.get(col, "center"), vertical="center",
                                indent={"G": 2, "E": 1, "F": 1}.get(col, 0), wrap_text=True)
    ws.row_dimensions[fila].height = 22


def subtitulo(fila, texto):
    ws.merge_cells(f"B{fila}:G{fila}")
    c = ws[f"B{fila}"]
    c.value = texto
    c.font = f(10, True, NARANJA_OSCURO)
    c.alignment = Alignment(vertical="center", indent=1)
    for col in "BCDEFG":
        ws[f"{col}{fila}"].border = Border(bottom=naranja_lado)
    ws.row_dimensions[fila].height = 22


def concepto(fila, numero, texto, d, e, fimp, explicacion, fmt_d=FMT_DIAS, fmt_e=FMT_MONEDA, alto=30):
    ws[f"B{fila}"] = numero
    ws[f"B{fila}"].font = f(10, True, NARANJA_OSCURO)
    ws[f"B{fila}"].alignment = Alignment(horizontal="center", vertical="center")
    ws[f"C{fila}"] = texto
    ws[f"C{fila}"].font = f(10, True)
    ws[f"C{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col, val, fmt in [("D", d, fmt_d), ("E", e, fmt_e), ("F", fimp, FMT_MONEDA)]:
        c = ws[f"{col}{fila}"]
        c.value = val
        c.number_format = fmt
        c.font = f(10, col == "F")
        c.alignment = Alignment(horizontal="center" if col == "D" else "right", vertical="center", indent=0 if col == "D" else 1)
    ws[f"G{fila}"] = seguro_txt(explicacion)
    ws[f"G{fila}"].font = f(9, color=GRIS_TEXTO)
    ws[f"G{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=2)
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


def gran_total(fila, texto, formula, nombre, color, nota=None):
    ws.merge_cells(f"B{fila}:E{fila}")
    ws[f"B{fila}"] = texto
    ws[f"B{fila}"].font = f(13, True, BLANCO)
    ws[f"B{fila}"].alignment = Alignment(horizontal="right", vertical="center", indent=1)
    for col in "BCDE":
        ws[f"{col}{fila}"].fill = relleno(color)
    c = ws[f"F{fila}"]
    c.value = formula
    c.number_format = FMT_MONEDA
    c.font = f(14, True, BLANCO)
    c.fill = relleno(color)
    c.alignment = Alignment(horizontal="right", vertical="center", indent=1)
    nombrar(nombre, HOJA, abs_ref("F", fila))
    if nota:
        ws[f"G{fila}"] = seguro_txt(nota)
        ws[f"G{fila}"].font = f(10, True, NARANJA_OSCURO)
        ws[f"G{fila}"].alignment = Alignment(vertical="center", indent=2, wrap_text=True)
    ws.row_dimensions[fila].height = 30


r += 2
FILA_DESGLOSE = r
banda(r, '="DESGLOSE DE LA LIQUIDACIÓN  ·  "&IF(Nombre="","(sin nombre)",Nombre)&"  (importes brutos)"', NARANJA, 13, 26)
r += 1
encabezado_tabla(r, ["#", "Concepto", "Días", "Salario diario", "Importe", "Cómo se calcula"])
r += 1
subtitulo(r, "A.  FINIQUITO  —  lo que ya se ganó; se paga en cualquier tipo de salida (salario diario sin integrar)")
r += 1
f_sueldo = r
concepto(r, 1, "Sueldo pendiente de pago",
         f"=IF({OK},DiasSueldoPend,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasSueldoPend")}&IF(DiasSueldoPend=1," día trabajado no pagado"," días trabajados no pagados")&" × salario diario","")')
r += 1
f_agui = r
concepto(r, 2, "Aguinaldo proporcional",
         f"=IF({OK},MAX(0,DiasAguinaldo*DiasAnioCal/365-AguinaldoPagadoDias),0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasAguinaldo")}&" días de aguinaldo × "&FIXED(DiasAnioCal,0)&" días trabajados en "&YEAR(FechaSalida)&" ÷ 365"'
         f'&IF(AguinaldoPagadoDias>0," − "&{num_txt("AguinaldoPagadoDias")}&" días ya pagados","")'
         f'&IF(DiasAguinaldo*DiasAnioCal/365<AguinaldoPagadoDias," (ya se pagó más de lo ganado: queda en 0)",""),"")')
r += 1
f_vacprop = r
concepto(r, 3, "Vacaciones proporcionales del año de servicio en curso",
         f"=IF({OK},MAX(0,DiasVacAnio*DiasVacProp/365-DiasVacTomados),0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasVacAnio")}&" días de vacaciones × "&FIXED(DiasVacProp,0)&IF(DiasDesdeAniv=0," días (cumplió el año completo)"," días desde el último aniversario")&" ÷ 365"'
         f'&IF(DiasVacTomados>0," − "&{num_txt("DiasVacTomados")}&" días tomados por adelantado","")'
         f'&IF(DiasVacAnio*DiasVacProp/365<DiasVacTomados," (tomó más de lo ganado: se paga 0)",""),"")')
r += 1
f_vacpend = r
concepto(r, 4, "Saldo de vacaciones ya ganadas y no tomadas",
         f"=IF({OK},DiasVacPend,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},{num_txt("DiasVacPend")}&" días de saldo de aniversarios ya cumplidos × salario diario","")')
r += 1
f_pv = r
concepto(r, 5, "Prima vacacional",
         f"=IF({OK},(D{f_vacprop}+IF(PVSaldoPagada=\"Sí\",0,D{f_vacpend}))*PctPrimaVac,0)", f"=IF({OK},SalarioDiario,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},FIXED(PctPrimaVac*100,0)&"% × "&{num_txt(f"(D{f_vacprop}+IF(PVSaldoPagada=\"Sí\",0,D{f_vacpend}))")}'
         f'&IF(PVSaldoPagada="Sí"," días del concepto 3 (la prima del saldo ya se pagó)"," días de vacaciones a pagar (conceptos 3 y 4)"),"")')
r += 1
f_bono = r
concepto(r, 6, "Bono (no integra al salario)",
         None, None, f"=IF({OK},ROUND(Bono,2),0)",
         f'=IF({OK},IF(Bono>0,"Monto capturado en el Paso 3. Se paga completo y no entra al salario integrado.","Sin bono"),"")')
r += 1
f_subfin = r
subtotal(r, "Subtotal finiquito", f"=SUM(F{f_sueldo}:F{f_bono})", "TotalFiniquito")

r += 1
subtitulo(r, "B.  INDEMNIZACIÓN Y PRIMA DE ANTIGÜEDAD  —  según el tipo de salida")
r += 1
f_indem = r
concepto(r, 7, "Indemnización (TRL)",
         f"=IF(AND({OK},AplicaIndem=\"Sí\"),MesesIndem*DiasMes,0)", f"=IF({OK},SalarioIntegrado,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},IF(AplicaIndem="Sí",{num_txt("MesesIndem")}&" meses × "&{num_txt("DiasMes")}&" días × salario diario integrado","No aplica en: "&TipoSalida),"")')
r += 1
f_20 = r
concepto(r, 8, "Días por año de servicio",
         f"=IF(AND({OK},AplicaIndem=\"Sí\"),DiasPorAnio*AniosServicio,0)", f"=IF({OK},SalarioIntegrado,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},IF(AplicaIndem="Sí",{num_txt("DiasPorAnio")}&" días × "&FIXED(AniosServicio,4)&" años de servicio × salario diario integrado","No aplica en: "&TipoSalida),"")')
ws[f"C{f_20}"] = f'="Indemnización de "&{num_txt("DiasPorAnio")}&" días por año de servicio"'
ws[f"C{f_indem}"] = (f'="Indemnización de "&{num_txt("MesesIndem")}&" meses (TRL)"&IF(MesesIndem>3,": 3 de ley + "'
                     f'&{num_txt("(MesesIndem-3)")}&IF(MesesIndem-3=1," adicional"," adicionales")&" GSK","")')
r += 1
f_pa = r
concepto(r, 9, "Prima de antigüedad (LFT art. 162)",
         f"=IF(AND({OK},AplicaPrimaAnt=\"Sí\"),DiasPrimaAnt*AniosServicio,0)", f"=IF({OK},SalarioPrimaAnt,0)", f"=ROUND(D{r}*E{r},2)",
         f'=IF({OK},IF(AplicaPrimaAnt="Sí",{num_txt("DiasPrimaAnt")}&" días × "&FIXED(AniosServicio,4)&" años × "'
         f'&IF(PrimaAntPiso="Sí","salario mínimo (la base no puede ser menor, art. 485 LFT)",'
         f'IF(PrimaAntTopada="Sí","salario topado a "&{num_txt("VecesTope")}&" salarios mínimos ("&{pesos("TopePrimaAnt")}&" diarios)",'
         f'"salario "&IF(BasePrimaAnt="Base","base","integrado")&IF(ToparPrimaAnt="Sí"," (no rebasa el tope)",""))),'
         f'"No aplica: en renuncia se paga con "&{num_txt("AntMinRenuncia")}&" años cumplidos o más"),"")', alto=34)
r += 1
f_tope = r
concepto(r, 10, "Ajuste por tope de indemnización",
         None, None, "=AjusteTope",
         f'=IF({OK},IF(ToparIndem<>"Sí","Sin tope (Paso 4).",IF(MontoSujetoTope=0,"No hay indemnización que topar.",'
         f'IF(AjusteTope<0,"Conceptos "&IF(CoberturaTope=INDEX(Lista_Cobertura,2),"7 a 9","7 y 8")&" suman "&{pesos("MontoSujetoTope")}'
         f'&" y el tope es "&{num_txt("AniosTopeIndem")}&" años × 365 × SDI = "&{pesos("TopeIndemMonto")}&". Se descuenta la diferencia.",'
         f'"No llega al tope de "&{num_txt("AniosTopeIndem")}&" años de salario integrado ("&{pesos("TopeIndemMonto")}&")."))),"")', alto=34)
ws[f"C{f_tope}"] = f'="Ajuste por tope ("&{num_txt("AniosTopeIndem")}&" años de salario integrado)"'
r += 1
f_subind = r
subtotal(r, "Subtotal indemnización y prima de antigüedad", f"=SUM(F{f_indem}:F{f_tope})", "TotalIndemnizacion")

r += 2
f_total = r
gran_total(r, "TOTAL BRUTO  (antes de impuestos)", f"=F{f_subfin}+F{f_subind}", "TotalBruto", NARANJA,
           f'=IF(AND({OK},SueldoMensual>0),"Equivale a "&FIXED(TotalBruto/SueldoMensual,1)&" meses de sueldo base","")')

# --- IMPUESTOS (ISR) Y NETO ---------------------------------------------------------------
r += 2
FILA_ISR = r
banda(r, "IMPUESTOS (ISR) Y NETO A RECIBIR  (estimado)", NARANJA, 13, 26)
r += 1
encabezado_tabla(r, ["", "Concepto", "Bruto", "Parte exenta", "Parte gravada", "Cómo se calcula la parte exenta"])
r += 1


def fila_isr(fila, letra, texto, bruto, exento, explicacion, alto=30):
    concepto(fila, letra, texto, bruto, exento, f"=D{fila}-E{fila}", explicacion, fmt_d=FMT_MONEDA, alto=alto)
    ws[f"D{fila}"].alignment = Alignment(horizontal="right", vertical="center")
    ws[f"F{fila}"].font = f(10)


f_isr1 = r
fila_isr(r, "a", "Sueldo pendiente y vacaciones (1, 3 y 4)",
         f"=F{f_sueldo}+F{f_vacprop}+F{f_vacpend}", "=0", '=IF(' + OK + ',"Todo gravado.","")')
r += 1
f_isr2 = r
fila_isr(r, "b", "Aguinaldo (2)", f"=F{f_agui}", f"=MIN(D{r},ExentoAguinaldo)",
         f'=IF({OK},"Exento hasta 30 UMA = "&{pesos("ExentoAguinaldo")}&" (LISR art. 93 fr. XIV).","")')
r += 1
f_isr3 = r
fila_isr(r, "c", "Prima vacacional (5)", f"=F{f_pv}", f"=MIN(D{r},ExentoPrimaVac)",
         f'=IF({OK},"Exenta hasta 15 UMA = "&{pesos("ExentoPrimaVac")}&" (LISR art. 93 fr. XIV).","")')
r += 1
f_isr4 = r
fila_isr(r, "d", "Bono (6)", f"=F{f_bono}", "=0", '=IF(' + OK + ',"Todo gravado.","")')
r += 1
f_isr5 = r
fila_isr(r, "e", "Indemnización y prima de antigüedad (7 a 10)", f"=F{f_subind}", f"=MIN(D{r},ExentoSeparacion)",
         f'=IF({OK},"Exento hasta 90 UMA × "&AniosExencion&IF(AniosExencion=1," año"," años")&" de servicio = "&{pesos("ExentoSeparacion")}'
         f'&" (LISR art. 93 fr. XIII; la fracción de más de 6 meses cuenta como año).","")', alto=34)
r += 1
f_isrtot = r
ws.merge_cells(f"B{r}:C{r}")
ws[f"B{r}"] = "Totales"
ws[f"B{r}"].font = f(10, True)
ws[f"B{r}"].alignment = Alignment(horizontal="right", vertical="center", indent=1)
for col in "DEF":
    c = ws[f"{col}{r}"]
    c.value = f"=SUM({col}{f_isr1}:{col}{f_isr5})"
    c.number_format = FMT_MONEDA
    c.font = f(10, True)
    c.alignment = Alignment(horizontal="right", vertical="center")
    c.border = Border(top=Side(style="thin", color=CARBON))
ws.row_dimensions[r].height = 22
nombrar("TotalExento", HOJA, abs_ref("E", r))
nombrar("TotalGravado", HOJA, abs_ref("F", r))

r += 1


def renglon_isr(fila, texto, formula, explicacion, nombre=None, negrita=False, alto=30):
    ws.merge_cells(f"B{fila}:E{fila}")
    ws[f"B{fila}"] = texto
    ws[f"B{fila}"].font = f(10, negrita)
    ws[f"B{fila}"].alignment = Alignment(horizontal="right", vertical="center", indent=1, wrap_text=True)
    c = ws[f"F{fila}"]
    c.value = formula
    c.number_format = FMT_MONEDA
    c.font = f(11 if negrita else 10, negrita)
    c.alignment = Alignment(horizontal="right", vertical="center")
    ws[f"G{fila}"] = seguro_txt(explicacion)
    ws[f"G{fila}"].font = f(9, color=GRIS_TEXTO)
    ws[f"G{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=2)
    for col in "BCDEFG":
        ws[f"{col}{fila}"].border = Border(bottom=delgado)
    if nombre:
        nombrar(nombre, HOJA, abs_ref("F", fila))
    ws.row_dimensions[fila].height = alto


f_isr_ord = r
renglon_isr(r, "ISR de los pagos ordinarios (a, b, c y d)", "=ISROrdinario",
            f'=IF({OK},"Tarifa mensual del art. 96 LISR sobre "&{pesos("GravadoOrdinario")}&" gravados"'
            f'&IF(SubsidioEmpleo>0," − subsidio para el empleo de "&{pesos("SubsidioEmpleo")},"")&".","")',
            "ISROrdinarioRenglon")
r += 1
f_isr_sep = r
renglon_isr(r, "ISR de la indemnización y prima de antigüedad (e)", "=ISRSeparacion",
            f'=IF({OK},IF(GravadoSeparacion=0,"Todo exento: no paga ISR.",IF(SepATarifa="Sí",'
            f'"Es menor a un sueldo mensual: se calcula con la tarifa, sumada a los pagos ordinarios (art. 96 LISR).",'
            f'{pesos("GravadoSeparacion")}&" gravados × "&FIXED(TasaArt95*100,2)&"% "'
            f'&"(ISR de un sueldo mensual ÷ sueldo mensual, art. 96 LISR).")),"")', "ISRSepRenglon")
r += 1
f_isr_tot = r
renglon_isr(r, "ISR total estimado", f"=F{f_isr_ord}+F{f_isr_sep}",
            f'=IF(AND({OK},TotalBruto>0),"Equivale al "&FIXED(F{r}/TotalBruto*100,1)&"% del total bruto.","")', "ISRTotal", negrita=True, alto=24)
r += 1
f_otras = r
renglon_isr(r, "Otros descuentos (Paso 3)", f"=IF({OK},ROUND(OtrasDeducciones,2),0)",
            '="Préstamos, anticipos u otros descuentos capturados."', "DescuentosTotal", alto=22)
r += 2
f_neto = r
gran_total(r, "NETO A RECIBIR  (estimado)", f"=TotalBruto-ISRTotal-DescuentosTotal", "TotalNeto", CARBON,
           f'=IF(AND({OK},SueldoMensual>0),"Equivale a "&FIXED(TotalNeto/SueldoMensual,1)&" meses de sueldo base","")')

r += 2
notas = [
    "Notas:",
    "• El ISR es una ESTIMACIÓN de la retención con la tarifa 2026. La nómina real puede variar si en el mismo mes ya se pagó otro sueldo "
    "o si en el año ya se usó la exención de prima vacacional; el ISR definitivo se ajusta en la declaración anual de la persona.",
    "• Salario diario integrado (SDI) = sueldo diario + parte proporcional de aguinaldo y prima vacacional (+ otras prestaciones fijas si se capturaron). El bono no integra (política).",
    "• Los conceptos 8 y 9 usan la antigüedad con decimales (los días del año incompleto también cuentan).",
    "• El tope de indemnización sólo reduce los conceptos 7 y 8 (o 7 a 9 si así se eligió); el finiquito nunca se topa.",
]
for t in notas:
    ws.merge_cells(f"B{r}:G{r}")
    ws[f"B{r}"] = t
    ws[f"B{r}"].font = f(9, t == "Notas:", GRIS_TEXTO, italic=t != "Notas:")
    ws[f"B{r}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[r].height = 26 if len(t) > 140 else 16
    r += 1

# --- CÁLCULOS DE APOYO ----------------------------------------------------------------------
r += 1
FILA_APOYO = r
banda(r, "CÁLCULOS DE APOYO  (automáticos, no se tocan)", CARBON, 11, 22)
r += 1


def fila_apoyo(fila, texto, nombre, formula, fmt, explicacion, negrita=False):
    etiqueta(fila, texto, negrita)
    calculo(fila, nombre, guardar(formula, nombre, fmt), fmt, negrita=negrita)
    ws.merge_cells(f"E{fila}:G{fila}")
    c = ws[f"E{fila}"]
    c.value = seguro_txt(explicacion)
    c.font = f(9, color=GRIS_TEXTO, italic=not str(explicacion).startswith("="))
    c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[fila].height = 18


def sub_apoyo(fila, texto):
    ws[f"C{fila}"] = texto
    ws[f"C{fila}"].font = f(10, True, NARANJA_OSCURO)
    for col in "CDEFG":
        ws[f"{col}{fila}"].border = Border(bottom=naranja_lado)
    ws.row_dimensions[fila].height = 20


sub_apoyo(r, "Revisión de datos")
r += 1
fila_apoyo(r, "¿Las opciones de las listas son válidas?", "ListasOK",
           '=IF(AND(ISNUMBER(MATCH(TipoSalida,Lista_Tipo,0)),ISNUMBER(MATCH(ZonaSM,Lista_Zona,0)),ISNUMBER(MATCH(ToparIndem,Lista_SiNo,0)),ISNUMBER(MATCH(CoberturaTope,Lista_Cobertura,0)),ISNUMBER(MATCH(ToparPrimaAnt,Lista_SiNo,0)),ISNUMBER(MATCH(BasePrimaAnt,Lista_Base,0)),ISNUMBER(MATCH(PVSaldoPagada,Lista_SiNo,0))),"Sí","No")', None, "Cada menú (tipo de salida, zona, Sí/No, cobertura, salario) debe tener una opción de su lista.")
r += 1
fila_apoyo(r, "¿Los números son números (sin letras)?", "TextoOK",
           '=IF(COUNTA(FechaIngreso,FechaSalida,SueldoMensual,DiasAguinaldo,PctPrimaVac,DiasVacManual,OtrasPrestInteg,DiasSueldoPend,DiasVacPend,DiasVacTomados,AguinaldoPagadoDias,Bono,OtrasDeducciones,MesesIndem,DiasPorAnio,AniosTopeIndem,DiasPrimaAnt,VecesTope,AntMinRenuncia,DiasMes)=COUNT(FechaIngreso,FechaSalida,SueldoMensual,DiasAguinaldo,PctPrimaVac,DiasVacManual,OtrasPrestInteg,DiasSueldoPend,DiasVacPend,DiasVacTomados,AguinaldoPagadoDias,Bono,OtrasDeducciones,MesesIndem,DiasPorAnio,AniosTopeIndem,DiasPrimaAnt,VecesTope,AntMinRenuncia,DiasMes),"Sí","No")', None, "Una celda con letras o espacios donde va un número no se puede calcular.")
r += 1
fila_apoyo(r, "¿Sin números negativos?", "NegOK",
           '=IF(MIN(FechaIngreso,FechaSalida,SueldoMensual,DiasAguinaldo,PctPrimaVac,DiasVacManual,OtrasPrestInteg,DiasSueldoPend,DiasVacPend,DiasVacTomados,AguinaldoPagadoDias,Bono,OtrasDeducciones,MesesIndem,DiasPorAnio,AniosTopeIndem,DiasPrimaAnt,VecesTope,AntMinRenuncia,DiasMes)>=0,"Sí","No")', None, "Ningún dato de captura puede ser negativo.")
r += 1
fila_apoyo(r, "¿Están llenos los Pasos 2 y 4?", "PoliticaOK",
           '=IF(AND(COUNT(DiasAguinaldo,PctPrimaVac,MesesIndem,DiasPorAnio,AniosTopeIndem,DiasPrimaAnt,VecesTope,AntMinRenuncia,DiasMes)=9,DiasMes>0),"Sí","No")', None, "Aguinaldo, prima vacacional y la política GSK no pueden quedar vacíos.")
r += 1
fila_apoyo(r, "¿Están completos los datos para calcular?", "DatosOK",
           "=IF(AND(ISNUMBER(FechaIngreso),ISNUMBER(FechaSalida),ISNUMBER(SueldoMensual)),"
           "IF(AND(FechaSalida>=FechaIngreso,SueldoMensual>0,ListasOK=\"Sí\",TextoOK=\"Sí\",NegOK=\"Sí\",PoliticaOK=\"Sí\"),\"Sí\",\"No\"),\"No\")",
           None, "Si dice No, todo da 0 y el mensaje de arriba dice qué falta.", negrita=True)
r += 1
fila_apoyo(r, "¿Se paga indemnización (conceptos 7 y 8)?", "AplicaIndem",
           "=IF(AND(DatosOK=\"Sí\",TipoSalida=INDEX(Lista_Tipo,1)),\"Sí\",\"No\")", None,
           "Sólo en «Liquidación (la empresa termina)».")
r += 1
fila_apoyo(r, "¿Se paga prima de antigüedad (concepto 9)?", "AplicaPrimaAnt",
           "=IF(DatosOK<>\"Sí\",\"No\",IF(TipoSalida=INDEX(Lista_Tipo,2),IF(AniosCompletos>=AntMinRenuncia,\"Sí\",\"No\"),\"Sí\"))", None,
           "En despido (con o sin causa) siempre; en renuncia sólo con 15 años cumplidos o más (art. 162 LFT).")

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
fila_apoyo(r, "Año de servicio de las vacaciones proporcionales", "AnioServicioActual",
           f"=IF({OK},AniosCompletos+IF(DiasDesdeAniv=0,0,1),0)", FMT_ENTERO,
           "El año que está corriendo (o el recién cumplido si sale el día antes de su aniversario). Define los días de la tabla.")
r += 1
fila_apoyo(r, "Días que cuentan para las vacaciones proporcionales", "DiasVacProp",
           f"=IF({OK},IF(DiasDesdeAniv=0,365,DiasDesdeAniv),0)", FMT_ENTERO,
           "Días desde el último aniversario; si sale el día antes de su aniversario, cuenta el año completo (365).")
r += 1
fila_apoyo(r, "Días trabajados en el año calendario de la salida", "DiasAnioCal",
           f"=IF({OK},MIN(365,FechaSalida-MAX(FechaIngreso,DATE(YEAR(FechaSalida),1,1))+1),0)", FMT_ENTERO,
           "Del 1 de enero (o del ingreso, si fue después) a la salida. Se usa para el aguinaldo.")

r += 2
sub_apoyo(r, "Vacaciones")
r += 1
fila_apoyo(r, "Días de vacaciones de la tabla para este año de servicio", "DiasVacTabla",
           f"=IF({OK},IFERROR(IF(ISNUMBER(INDEX(Vac_Empresa,MATCH(AnioServicioActual,Vac_Desde,1))),"
           f"INDEX(Vac_Empresa,MATCH(AnioServicioActual,Vac_Desde,1)),INDEX(Vac_Ley,MATCH(AnioServicioActual,Vac_Desde,1))),0),0)",
           "General", "Columna «Días que da la empresa» de la hoja Tablas.")
r += 1
fila_apoyo(r, "Días de vacaciones según la ley (referencia)", "DiasVacLey",
           f"=IF({OK},IFERROR(INDEX(Vac_Ley,MATCH(AnioServicioActual,Vac_Desde,1)),0),0)", "General",
           "Columna «Días por ley» de la hoja Tablas (art. 76 LFT).")
r += 1
fila_apoyo(r, "Días de vacaciones al año que se usan", "DiasVacAnio",
           "=IF(AND(ISNUMBER(DiasVacManual),DiasVacManual>0),DiasVacManual,DiasVacTabla)", "General",
           "Los de la tabla, salvo que hayas escrito otro número en el Paso 2.", negrita=True)
r += 1
fila_apoyo(r, "Días de prima vacacional al año", "DiasPrimaVacAnio",
           "=DiasVacAnio*PctPrimaVac", "0.00", "Días de vacaciones × % de prima vacacional.")

r += 2
sub_apoyo(r, "¿Cómo se integra el salario?")
for col, txt in zip("DE", ["Diario", "Mensual"]):
    ws[f"{col}{r}"] = txt
    ws[f"{col}{r}"].font = f(9, True, NARANJA_OSCURO)
    ws[f"{col}{r}"].alignment = Alignment(horizontal="center")
r += 1


def fila_integ(fila, texto, nombre, f_diario, f_mensual, explicacion, negrita=False):
    etiqueta(fila, texto, negrita)
    calculo(fila, nombre, guardar(f_diario, nombre, FMT_MONEDA_SIMPLE), FMT_MONEDA_SIMPLE, "D", negrita)
    calculo(fila, None, guardar(f_mensual, None, FMT_MONEDA_SIMPLE), FMT_MONEDA_SIMPLE, "E", negrita)
    ws.merge_cells(f"F{fila}:G{fila}")
    c = ws[f"F{fila}"]
    c.value = seguro_txt(explicacion)
    c.font = f(9, color=GRIS_TEXTO, italic=not str(explicacion).startswith("="))
    c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    ws.row_dimensions[fila].height = 18


fila_integ(r, "Sueldo base", "SalarioDiario", f"=IF({OK},SueldoMensual/DiasMes,0)", f"=D{r}*DiasMes",
           f'="Sueldo mensual ÷ "&{num_txt("DiasMes")}&" días"')
r += 1
fila_integ(r, "+ Parte proporcional de aguinaldo", "IntegAguinaldo", "=SalarioDiario*DiasAguinaldo/365", f"=D{r}*DiasMes",
           f'="Salario diario × "&{num_txt("DiasAguinaldo")}&" días ÷ 365"')
r += 1
fila_integ(r, "+ Parte proporcional de prima vacacional", "IntegPrimaVac", "=SalarioDiario*DiasPrimaVacAnio/365", f"=D{r}*DiasMes",
           f'="Salario diario × "&{num_txt("DiasVacAnio")}&" días × "&FIXED(PctPrimaVac*100,0)&"% ÷ 365"')
r += 1
fila_integ(r, "+ Otras prestaciones fijas que integran", "IntegOtras", "=OtrasPrestInteg/DiasMes", f"=D{r}*DiasMes",
           '=IF(OtrasPrestInteg>0,"Monto mensual del Paso 2 ÷ "&' + num_txt("DiasMes") + '&" días","No capturaste otras prestaciones (Paso 2).")')
r += 1
fila_integ(r, "Salario diario integrado (SDI)", "SalarioIntegrado", "=SalarioDiario*FactorIntegracion+IntegOtras", f"=D{r}*DiasMes",
           "Suma de lo anterior.  Se usa en los conceptos 7 y 8 (y en el tope).", negrita=True)
for col in "DE":
    ws[f"{col}{r}"].border = Border(top=Side(style="thin", color=CARBON), bottom=Side(style="double", color=CARBON))
r += 1
fila_apoyo(r, "Factor de integración (aguinaldo y prima vacacional)", "FactorIntegracion",
           "=1+DiasAguinaldo/365+DiasPrimaVacAnio/365", FMT_FACTOR,
           f'="1 + "&{num_txt("DiasAguinaldo")}&"/365 + ("&{num_txt("DiasVacAnio")}&" × "&FIXED(PctPrimaVac*100,0)&"%)/365"')

r += 2
sub_apoyo(r, "Tope de la indemnización")
r += 1
fila_apoyo(r, "Tope en pesos", "TopeIndemMonto", "=ROUND(AniosTopeIndem*365*SalarioIntegrado,2)", FMT_MONEDA_SIMPLE,
           f'={num_txt("AniosTopeIndem")}&" años × 365 días × salario diario integrado"')
r += 1
fila_apoyo(r, "Importe que cubre el tope", "MontoSujetoTope",
           f"=F{f_indem}+F{f_20}+IF(CoberturaTope=INDEX(Lista_Cobertura,2),F{f_pa},0)", FMT_MONEDA_SIMPLE,
           '="Conceptos "&IF(CoberturaTope=INDEX(Lista_Cobertura,2),"7, 8 y 9","7 y 8")&" (Paso 4)"')
r += 1
fila_apoyo(r, "Ajuste (se descuenta lo que pasa del tope)", "AjusteTope",
           f"=IF(AND({OK},ToparIndem=\"Sí\"),-MAX(0,MontoSujetoTope-TopeIndemMonto),0)", FMT_MONEDA,
           "Negativo = se recorta; cero = no llega al tope.", negrita=True)

r += 2
sub_apoyo(r, "Prima de antigüedad")
r += 1
fila_apoyo(r, "Salario mínimo: vigente desde", "FechaSM",
           f"=IF({OK},SUMPRODUCT(MAX((SM_Desde<=FechaSalida)*IF(ZonaSM=INDEX(Lista_Zona,2),1,0)*ISNUMBER(SM_Frontera)*SM_Desde)"
           f"+MAX((SM_Desde<=FechaSalida)*IF(ZonaSM=INDEX(Lista_Zona,2),0,1)*ISNUMBER(SM_General)*SM_Desde)),0)", FMT_FECHA,
           "El más reciente capturado en «Tablas» a la fecha de salida.")
r += 1
fila_apoyo(r, "Salario mínimo diario aplicable", "SalMinAplicable",
           f"=IF({OK},IFERROR(IF(ZonaSM=INDEX(Lista_Zona,2),INDEX(SM_Frontera,MATCH(FechaSM,SM_Desde,0)),"
           f"INDEX(SM_General,MATCH(FechaSM,SM_Desde,0))),0),0)", FMT_MONEDA_SIMPLE,
           f'=IF({OK},"Año "&IFERROR(YEAR(FechaSM),"—")&", zona "&ZonaSM,"")')
r += 1
fila_apoyo(r, "Tope diario", "TopePrimaAnt", "=VecesTope*SalMinAplicable", FMT_MONEDA_SIMPLE,
           f'={num_txt("VecesTope")}&" × salario mínimo diario"')
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

r += 2
sub_apoyo(r, "ISR (impuesto sobre la renta)")
r += 1
fila_apoyo(r, "UMA: vigente desde", "FechaUMA",
           f"=IF({OK},SUMPRODUCT(MAX((UMA_Desde<=FechaSalida)*ISNUMBER(UMA_Valor)*UMA_Desde)),0)", FMT_FECHA,
           "La UMA cambia cada 1 de febrero (hoja «Tablas»).")
r += 1
fila_apoyo(r, "UMA diaria aplicable", "UMAAplicable",
           f"=IF({OK},IFERROR(INDEX(UMA_Valor,MATCH(FechaUMA,UMA_Desde,0)),0),0)", FMT_MONEDA_SIMPLE,
           "Sirve para calcular las partes exentas.")
r += 1
fila_apoyo(r, "Aguinaldo exento (30 UMA, menos lo ya exentado en el año)", "ExentoAguinaldo",
           "=ROUND(MAX(0,30*UMAAplicable-AguinaldoPagadoDias*SalarioDiario),2)", FMT_MONEDA_SIMPLE,
           "LISR art. 93 fr. XIV. Si ya se pagó aguinaldo este año, ese pago ya usó parte de la exención.")
r += 1
fila_apoyo(r, "Prima vacacional exenta (15 UMA)", "ExentoPrimaVac", "=ROUND(15*UMAAplicable,2)", FMT_MONEDA_SIMPLE,
           "LISR art. 93 fracción XIV.")
r += 1
fila_apoyo(r, "Años de servicio para la exención", "AniosExencion",
           f"=IF({OK},AniosCompletos+IF(FechaSalida+1>EDATE(UltimoAniv,6),1,0),0)", FMT_ENTERO,
           "Años completos; la fracción de más de 6 meses cuenta como un año más (art. 93 fr. XIII).")
r += 1
fila_apoyo(r, "Indemnización y prima de antigüedad exentas", "ExentoSeparacion",
           "=ROUND(90*UMAAplicable*AniosExencion,2)", FMT_MONEDA_SIMPLE, "90 UMA × años de servicio (art. 93 fr. XIII).")
r += 1
fila_apoyo(r, "Gravado de pagos ordinarios (a a d)", "GravadoOrdinario",
           f"=F{f_isr1}+F{f_isr2}+F{f_isr3}+F{f_isr4}", FMT_MONEDA_SIMPLE, "Parte gravada de sueldo, vacaciones, aguinaldo, prima vacacional y bono.")
r += 1
fila_apoyo(r, "Gravado de indemnización y prima de antigüedad (e)", "GravadoSeparacion",
           f"=F{f_isr5}", FMT_MONEDA_SIMPLE, "Lo que pasa de la parte exenta.")
r += 1
fila_apoyo(r, "ISR de un sueldo mensual (tarifa art. 96)", "ISRSueldoMensual",
           f"=IF({OK},ROUND({isr_tarifa('SueldoMensual')},2),0)", FMT_MONEDA_SIMPLE,
           "Tarifa mensual de la hoja «Tablas» aplicada al último sueldo mensual ordinario.")
r += 1
fila_apoyo(r, "Tasa del art. 96 (6º párrafo) para la indemnización", "TasaArt95",
           "=IF(SueldoMensual>0,ISRSueldoMensual/SueldoMensual,0)", "0.00%",
           "ISR de un sueldo mensual ÷ sueldo mensual. Se aplica a la indemnización gravada.")
r += 1
fila_apoyo(r, "¿La indemnización gravada va con la tarifa?", "SepATarifa",
           "=IF(AND(GravadoSeparacion>0,GravadoSeparacion<SueldoMensual),\"Sí\",\"No\")", None,
           "Sí cuando es menor a un sueldo mensual: entonces se calcula con la tarifa, sumada a los pagos ordinarios.")
r += 1
fila_apoyo(r, "ISR de los pagos ordinarios con tarifa (antes de subsidio)", "ISRTarifaOrd",
           f"=IF({OK},ROUND({isr_tarifa('GravadoOrdinario')},2),0)", FMT_MONEDA_SIMPLE,
           "Cuota fija + % sobre el excedente del límite inferior (tarifa mensual).")
r += 1
fila_apoyo(r, "Subsidio para el empleo", "SubsidioEmpleo",
           f"=IF(AND({OK},GravadoOrdinario>0,GravadoOrdinario<=SubsidioLimite),MIN(ISRTarifaOrd,ROUND(UMAAplicable*30.4*SubsidioPct,2)),0)",
           FMT_MONEDA_SIMPLE, "Sólo si los pagos ordinarios gravados no pasan del límite de la hoja «Tablas».")
r += 1
fila_apoyo(r, "ISR de los pagos ordinarios", "ISROrdinario", "=MAX(0,ISRTarifaOrd-SubsidioEmpleo)", FMT_MONEDA_SIMPLE,
           "ISR con tarifa − subsidio.", negrita=True)
r += 1
fila_apoyo(r, "ISR de indemnización y prima de antigüedad", "ISRSeparacion",
           f"=IF(OR(NOT({OK}),GravadoSeparacion=0),0,IF(SepATarifa=\"Sí\","
           f"ROUND({isr_tarifa('(GravadoOrdinario+GravadoSeparacion)')},2)-ISRTarifaOrd,ROUND(GravadoSeparacion*TasaArt95,2)))",
           FMT_MONEDA_SIMPLE, "Gravado × tasa; o, si es menor a un sueldo mensual, lo que sube la tarifa al sumarlo.", negrita=True)
f_fin = r

# Valor de la tabla de vacaciones mostrado en el Paso 2
calculo(fila_vac_tabla, None, "=DiasVacTabla", "General", negrita=True)

# --- RESULTADO (arriba) ------------------------------------------------------------------
fr = FILA_RES + 1


def tile_label(fila, col, texto, color=GRIS_TEXTO):
    c = ws[f"{col}{fila}"]
    c.value = texto
    c.font = f(9, True, color)
    c.alignment = Alignment(horizontal="center", vertical="bottom", wrap_text=True)


def tile_valor(fila, col, formula, tam=12, color_txt=NEGRO_GSK, fondo=GRIS_CALC):
    c = ws[f"{col}{fila}"]
    c.value = formula
    c.number_format = FMT_MONEDA
    c.font = f(tam, True, color_txt)
    c.fill = relleno(fondo)
    c.alignment = Alignment(horizontal="center", vertical="center")


ws[f"C{fr}"] = "=IF(Nombre=\"\",\"(sin nombre)\",Nombre)"
ws[f"C{fr}"].font = f(12, True)
ws[f"C{fr}"].alignment = Alignment(vertical="bottom", indent=1, shrink_to_fit=True)
tile_label(fr, "D", "Finiquito")
tile_label(fr, "E", "Indemnización y prima de antigüedad")
tile_label(fr, "F", "TOTAL BRUTO", NEGRO_GSK)
tile_label(fr, "G", "NETO A RECIBIR (estimado)", NARANJA_OSCURO)
ws.row_dimensions[fr].height = 26
fr += 1
ws[f"C{fr}"] = seguro_txt(f'=IF({OK},TipoSalida&"  ·  "&AniosCompletos&IF(AniosCompletos=1," año"," años")&" y "'
                          f'&DiasDesdeAniv&IF(DiasDesdeAniv=1," día"," días")&" de antigüedad","")')
ws[f"C{fr}"].font = f(9, color=GRIS_TEXTO)
ws[f"C{fr}"].alignment = Alignment(vertical="top", wrap_text=True, indent=1)
tile_valor(fr, "D", "=TotalFiniquito")
tile_valor(fr, "E", "=TotalIndemnizacion")
tile_valor(fr, "F", "=TotalBruto", 13, BLANCO, NEGRO_GSK)
tile_valor(fr, "G", "=TotalNeto", 20, BLANCO, NARANJA)
ws.row_dimensions[fr].height = 34
fr += 1
ws[f"C{fr}"] = seguro_txt(f'=IF({OK},"Salario diario integrado: "&{pesos("SalarioIntegrado")}&" ("&{pesos("SalarioIntegrado*DiasMes")}&" al mes)","")')
ws[f"C{fr}"].font = f(9, True)
ws[f"C{fr}"].alignment = Alignment(vertical="bottom", indent=1, shrink_to_fit=True)
tile_label(fr, "D", "Ajuste por tope")
tile_label(fr, "E", "ISR estimado")
tile_label(fr, "F", "Otros descuentos")
ws[f"G{fr}"] = seguro_txt(f'=IF(AND({OK},SueldoMensual>0),"Neto = "&FIXED(TotalNeto/SueldoMensual,1)&" meses de sueldo base","")')
ws[f"G{fr}"].font = f(9, True, NARANJA_OSCURO)
ws[f"G{fr}"].alignment = Alignment(horizontal="center", vertical="bottom")
ws.row_dimensions[fr].height = 18
fr += 1
ws[f"C{fr}"] = seguro_txt(f'=IF({OK},IF(ToparIndem="Sí","Tope de indemnización: "&{num_txt("AniosTopeIndem")}&" años = "&{pesos("TopeIndemMonto")},"Indemnización sin tope"),"")')
ws[f"C{fr}"].font = f(9, color=GRIS_TEXTO)
ws[f"C{fr}"].alignment = Alignment(vertical="center", indent=1, shrink_to_fit=True)
tile_valor(fr, "D", "=AjusteTope", 11)
tile_valor(fr, "E", "=-ISRTotal", 11)
tile_valor(fr, "F", "=-DescuentosTotal", 11)
ws[f"G{fr}"] = seguro_txt(f'=IF({OK},"Total bruto "&{pesos("TotalBruto")}&" − ISR "&{pesos("ISRTotal")}&IF(DescuentosTotal>0," − descuentos "&{pesos("DescuentosTotal")},""),"")')
ws[f"G{fr}"].font = f(9, color=GRIS_TEXTO)
ws[f"G{fr}"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
ws.row_dimensions[fr].height = 24
fr += 1
FILA_ESTADO = fr
AVISOS = [
    ('NOT(ISNUMBER(FechaIngreso))', '"⚠ Falta la fecha de ingreso (Paso 1)."'),
    ('NOT(ISNUMBER(FechaSalida))', '"⚠ Falta la fecha de salida (Paso 1)."'),
    ('FechaSalida<FechaIngreso', '"⚠ La fecha de salida es anterior a la de ingreso. Revísalas."'),
    ('OR(NOT(ISNUMBER(SueldoMensual)),SueldoMensual<=0)', '"⚠ Falta el sueldo mensual (Paso 1)."'),
    ('ISNA(MATCH(TipoSalida,Lista_Tipo,0))', '"⚠ Elige el tipo de salida con la flechita de la lista (Paso 1)."'),
    ('ListasOK<>"Sí"', '"⚠ Hay una opción escrita a mano (zona, Sí/No, cobertura o salario). Elígela con la flechita de la lista."'),
    ('TextoOK<>"Sí"', '"⚠ Hay letras, espacios o símbolos donde va un número (Pasos 2, 3 o 4). Escribe sólo números."'),
    ('NegOK<>"Sí"', '"⚠ Hay un número negativo en los Pasos 2, 3 o 4. Si no aplica, escribe 0."'),
    ('PoliticaOK<>"Sí"', '"⚠ Hay una celda vacía en el Paso 2 o 4. Valores normales: aguinaldo 15, prima 25%, 4 meses, 20 días, '
                         'tope 2 años, 12 días, 2 salarios mínimos, 15 años y 30 días por mes."'),
    ('AND(AplicaPrimaAnt="Sí",SalMinAplicable=0)', '"⚠ No hay salario mínimo capturado para esa fecha y zona (hoja Tablas)."'),
    ('AND(AplicaPrimaAnt="Sí",YEAR(FechaSM)<YEAR(FechaSalida))',
     '"⚠ Falta capturar el salario mínimo "&YEAR(FechaSalida)&" en la hoja Tablas; se usó el de "&YEAR(FechaSM)&"."'),
    ('UMAAplicable=0', '"⚠ No hay UMA capturada para esa fecha (hoja Tablas); el ISR no es confiable."'),
    ('AND(YEAR(FechaUMA)<YEAR(FechaSalida),MONTH(FechaSalida)>1)',
     '"⚠ Falta capturar la UMA "&YEAR(FechaSalida)&" en la hoja Tablas; se usó la de "&YEAR(FechaUMA)&"."'),
    ('YEAR(FechaSalida)<ISR_AnioTarifa',
     '"⚠ La tarifa de ISR de «Tablas» rige desde "&ISR_AnioTarifa&"; para una salida de "&YEAR(FechaSalida)&" el ISR es sólo aproximado."'),
    ('DiasVacAnio*DiasVacProp/365<DiasVacTomados', '"⚠ Tomó más vacaciones de las que lleva ganadas este año; las proporcionales quedan en 0."'),
    ('OR(DiasAguinaldo<15,PctPrimaVac<0.25,DiasVacAnio<DiasVacLey)',
     '"⚠ Hay prestaciones por debajo de la ley (aguinaldo 15 días, prima vacacional 25%, tabla de vacaciones). Revisa el Paso 2."'),
    (f'Nombre="{EJEMPLO["Nombre"]}"', '"⚠ Son datos de EJEMPLO: escribe encima los del colaborador (Pasos 1 y 3)."'),
]
estado = '"✓ Listo. Revisa el desglose más abajo."'
for cond, msg in reversed(AVISOS):
    estado = f"IF({cond},{msg},{estado})"
estado = f'=IFERROR({estado},"⚠ Revisa los datos: hay un valor que no se puede calcular.")'
ws.merge_cells(f"C{fr}:G{fr}")
ws[f"C{fr}"] = estado
ws[f"C{fr}"].font = f(10, True)
ws[f"C{fr}"].alignment = Alignment(vertical="center", indent=1, wrap_text=True)
ws.row_dimensions[fr].height = 24
assert fr < FILA_RES + 7

# Formato condicional: estado (verde / rojo) y conceptos en cero en gris
ws.conditional_formatting.add(
    f"C{FILA_ESTADO}:G{FILA_ESTADO}",
    FormulaRule(formula=[f'LEFT($C${FILA_ESTADO},1)="✓"'], fill=relleno(VERDE_OK), font=Font(name=FUENTE, bold=True, color=VERDE_OK_TXT)))
ws.conditional_formatting.add(
    f"C{FILA_ESTADO}:G{FILA_ESTADO}",
    FormulaRule(formula=[f'LEFT($C${FILA_ESTADO},1)="⚠"'], fill=relleno(ROJO_AVISO), font=Font(name=FUENTE, bold=True, color=ROJO_AVISO_TXT)))
for fila in cond_grises:
    ws.conditional_formatting.add(
        f"B{fila}:F{fila}",
        FormulaRule(formula=[f"AND($F${fila}=0,$D${fila}=0)"], font=Font(name=FUENTE, color="B0ACA8")))
ws.conditional_formatting.add(
    f"D{FILA_SALIDA}",
    FormulaRule(formula=[f"AND(ISNUMBER($D${FILA_SALIDA}),ISNUMBER($D${FILA_INGRESO}),$D${FILA_SALIDA}<$D${FILA_INGRESO})"],
                fill=relleno(ROJO_AVISO)))

# Comentarios (ayuda al pasar el mouse)
ws[f"D{FILA_SUELDO}"].comment = Comment(
    "Sueldo mensual nominal (base). Ejemplo: 45000.\nEl salario diario = sueldo mensual ÷ 30.", "Calculadora")
ws[f"F{f_total}"].comment = Comment(
    "Finiquito + indemnización + prima de antigüedad (ya con el tope). Importe bruto, antes de ISR.", "Calculadora")
ws[f"F{f_neto}"].comment = Comment(
    "Total bruto − ISR estimado − otros descuentos. Es una estimación de lo que recibe la persona.", "Calculadora")

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
ws.oddFooter.left.font = "Arial"
ws.oddFooter.right.text = "Página &P de &N"
ws.oddFooter.right.size = 8
ws.oddFooter.right.font = "Arial"

ws.protection.sheet = True
ws.sheet_view.selection[0].activeCell = f"D{FILA_RES + 8}"
ws.sheet_view.selection[0].sqref = f"D{FILA_RES + 8}"

# ======================================================================================
# HOJA: Instrucciones
# ======================================================================================
wsI = wb.create_sheet("Instrucciones", 1)
wsI.sheet_view.showGridLines = False
wsI.sheet_properties.tabColor = CARBON
wsI.column_dimensions["A"].width = 2
wsI.column_dimensions["B"].width = 6
wsI.column_dimensions["C"].width = 34
wsI.column_dimensions["D"].width = 92

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


def renglon_instr(c_txt, d_txt, numero=None, alto=None):
    global fila
    if numero is not None:
        wsI[f"B{fila}"] = numero
        wsI[f"B{fila}"].font = f(16, True, NARANJA)
        wsI[f"B{fila}"].alignment = Alignment(horizontal="center", vertical="center")
    wsI[f"C{fila}"] = c_txt
    wsI[f"C{fila}"].font = f(10 if numero is None else 11, True)
    wsI[f"C{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    wsI[f"D{fila}"] = d_txt
    wsI[f"D{fila}"].font = f(10)
    wsI[f"D{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col in "BCD":
        wsI[f"{col}{fila}"].border = Border(bottom=delgado)
    wsI.row_dimensions[fila].height = alto or (30 if len(d_txt) < 105 else 44 if len(d_txt) < 210 else 58)
    fila += 1


bloque_titulo("CÓMO SE USA  (todo se hace en la pestaña «Calculadora»)")
renglon_instr("Paso 1 · Datos del colaborador", "Nombre, fecha de ingreso, fecha de salida, sueldo mensual y tipo de salida (celdas durazno). "
              "Junto a cada fecha aparece cómo la leyó Excel («Se leyó: 15 de marzo de 2019»): revisa que sea la correcta.", 1)
renglon_instr("Paso 2 · Prestaciones", "Aguinaldo y prima vacacional ya traen el mínimo de ley; cámbialos sólo si la empresa da más. "
              "Las vacaciones salen solas de la tabla de la ley.", 2)
renglon_instr("Paso 3 · Pendientes, bono y descuentos", "Días no pagados, saldo de vacaciones, bono y otros descuentos. Vienen en 0: "
              "escribe sólo lo que aplique.", 3)
renglon_instr("Paso 4 · Política GSK", "4 meses + 20 días por año, tope de 2 años de salario integrado y prima de antigüedad de ley "
              "(12 días por año, topada a 2 salarios mínimos). Normalmente no se toca.", 4)
renglon_instr("Resultado", "Arriba, en RESULTADO, está el total bruto, el ISR y el NETO A RECIBIR, con un mensaje: verde = todo bien; "
              "rojo = te dice qué falta o qué revisar. Abajo está el desglose de cada concepto y del ISR. Para imprimir: Ctrl + P.", "✓")
fila += 1
bloque_titulo("COLORES")
for color, borde, txt, desc in [
    (DURAZNO, BORDE_CAPTURA, "Durazno", "Llenar: datos del colaborador (Paso 1) y pendientes y bono (Paso 3)."),
    (CREMA, BORDE_CAPTURA, "Claro", "Ya trae un valor (ley o política GSK); cámbialo sólo si es distinto."),
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
for t, d in [
    ("Salario diario", "Sueldo mensual ÷ 30 (art. 89 LFT)."),
    ("Factor de integración", "1 + días de aguinaldo/365 + (días de vacaciones × % prima vacacional)/365. "
     "Ej. con prestaciones de ley en el 3er año de servicio: 1 + 15/365 + (16 × 25%)/365 = 1.0521."),
    ("Salario diario integrado (SDI)", "Salario diario × factor de integración: el sueldo más la parte proporcional diaria del aguinaldo y de la "
     "prima vacacional (arts. 84 y 89 LFT). Se usa para la indemnización (conceptos 7 y 8). El bono NO integra."),
    ("1. Sueldo pendiente", "Días trabajados que todavía no se pagan × salario diario."),
    ("2. Aguinaldo proporcional", "Días de aguinaldo × días trabajados en el año de la salida ÷ 365 × salario diario, menos los días de "
     "aguinaldo de ese año que ya se le pagaron (art. 87 LFT)."),
    ("3. Vacaciones proporcionales", "Días de vacaciones del año de servicio que está corriendo × días desde el último aniversario ÷ 365, "
     "menos los días que tomó por adelantado (art. 79 LFT). Si sale el día antes de su aniversario, se paga el año completo. "
     "Los días por año salen de la tabla de la ley (art. 76, reforma 2023)."),
    ("4. Saldo de vacaciones", "Vacaciones ya ganadas en aniversarios cumplidos y no tomadas (según el control de vacaciones) × salario diario."),
    ("5. Prima vacacional", "% de prima vacacional × (días de vacaciones de los conceptos 3 y 4) × salario diario (art. 80 LFT). "
     "Si la prima del saldo ya se pagó, sólo se paga la del concepto 3."),
    ("6. Bono", "Monto capturado; se paga completo y no forma parte del salario integrado (decisión de política)."),
    ("7. Indemnización (TRL)", "Meses de indemnización × 30 días × SDI. La ley marca 3 meses (art. 50); GSK paga 4."),
    ("8. 20 días por año", "20 días × antigüedad en años con decimales × SDI."),
    ("9. Prima de antigüedad", "12 días × antigüedad en años con decimales × salario diario topado a 2 salarios mínimos "
     "(y nunca menor a 1 salario mínimo) (arts. 162, 485 y 486 LFT). Se paga en cualquier despido; en renuncia, sólo con 15 años o más."),
    ("10. Ajuste por tope", "La indemnización (7 y 8) no puede pasar de 2 años de salario integrado (2 × 365 × SDI). Si pasa, se descuenta la "
     "diferencia. Los años se mueven en el Paso 4, y ahí también se puede elegir que el tope incluya la prima de antigüedad."),
    ("Finiquito vs. liquidación", "Finiquito = lo ya ganado (conceptos 1 a 6). Liquidación = finiquito + indemnización + prima de antigüedad."),
]:
    renglon_instr(t, d)

fila += 1
bloque_titulo("CÓMO SE ESTIMA EL ISR (BRUTO → NETO)")
for t, d in [
    ("Partes exentas", "Aguinaldo: hasta 30 UMA. Prima vacacional: hasta 15 UMA. Indemnización y prima de antigüedad: hasta 90 UMA por cada "
     "año de servicio (la fracción de más de 6 meses cuenta como año). Sueldo, vacaciones y bono: todo gravado (LISR art. 93)."),
    ("Pagos ordinarios", "A la parte gravada de sueldo, vacaciones, aguinaldo, prima vacacional y bono se le aplica la tarifa mensual 2026 del art. 96 "
     "(hoja «Tablas»), como un pago del mes. Si esa suma no pasa de $11,492.66, se resta el subsidio para el empleo."),
    ("Indemnización y prima de antigüedad", "A su parte gravada se le aplica la tasa del último sueldo: ISR de un sueldo mensual ÷ sueldo mensual "
     "(art. 96, 6º párrafo, LISR). Si la parte gravada es menor a un sueldo mensual, se calcula con la tarifa, sumada a los pagos ordinarios."),
    ("Es una estimación", "La retención real de nómina puede variar (sueldos ya pagados en el mes, subsidio para el empleo en sueldos bajos, "
     "declaración anual). Otros descuentos (préstamos, anticipos) se capturan en el Paso 3."),
]:
    renglon_instr(t, d)

wsI.row_breaks.append(Break(id=fila))
fila += 1
bloque_titulo("QUÉ SE PAGA SEGÚN EL TIPO DE SALIDA")
for col, txt in zip("CD", ["Tipo de salida", "Conceptos que se pagan"]):
    wsI[f"{col}{fila}"] = txt
    wsI[f"{col}{fila}"].font = f(10, True)
    wsI[f"{col}{fila}"].fill = relleno(GRIS_BORDE)
fila += 1
for t, d in [
    (LISTA_TIPO[0], "Finiquito (1 a 6) + indemnización 4 meses (7) + 20 días por año (8) + prima de antigüedad (9), con el tope (10)."),
    (LISTA_TIPO[1], "Finiquito (1 a 6). Prima de antigüedad (9) sólo si tiene 15 años cumplidos o más."),
    (LISTA_TIPO[2], "Finiquito (1 a 6) + prima de antigüedad (9). Sin indemnización."),
]:
    renglon_instr(t, d)

fila += 1
bloque_titulo("ANTES DE PAGAR, REVISA (no lo calcula esta hoja)")
for t in [
    "• Fondo de ahorro: saldo del trabajador y de la empresa.",
    "• PTU pendiente: se paga en mayo aunque ya no trabaje en la empresa (arts. 117 a 122 LFT).",
    "• Comisiones, incentivos u horas extra ya devengados y no pagados.",
    "• Retenciones obligatorias: pensión alimenticia, crédito INFONAVIT o FONACOT, préstamos (captúralos en «Otros descuentos»).",
    "• Rescisión por causa imputable a la empresa (art. 51): elige «Liquidación». La regla de 15 años sólo aplica en renuncia voluntaria.",
    "• El convenio va por escrito, con el desglose de conceptos, y se ratifica ante el Centro de Conciliación o el Tribunal (art. 33 LFT).",
]:
    wsI.merge_cells(f"B{fila}:D{fila}")
    wsI[f"B{fila}"] = t
    wsI[f"B{fila}"].font = f(10)
    wsI[f"B{fila}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    wsI.row_dimensions[fila].height = 22
    fila += 1

fila += 1
bloque_titulo("MANTENIMIENTO (una vez al año) Y AVISOS")
for t in [
    "• Cada diciembre/enero: captura el nuevo salario mínimo en la hoja «Tablas» (ya hay renglones listos para 2027 a 2030). "
    "Si falta, la calculadora usa el último que encuentre y te avisa en rojo.",
    "• Cada enero/febrero: captura la nueva UMA en «Tablas» (cambia el 1 de febrero).",
    "• La tarifa mensual de ISR es la de 2026 (el SAT la actualiza cuando la inflación acumulada pasa de 10%). Revisa el Anexo 8 de la RMF cada enero "
    "y, si cambió, actualízala en «Tablas». Lo mismo el subsidio para el empleo.",
    "• Si la empresa da más días de vacaciones que la ley, cámbialos una sola vez en la columna «Días que da la empresa» de «Tablas».",
    "• Las hojas están protegidas SIN contraseña sólo para que no se borren fórmulas por accidente. "
    "Si necesitas cambiar algo: Revisar → Desproteger hoja.",
    "• Para calcular a otra persona, guarda una copia del ARCHIVO (Archivo → Guardar como; en Google Sheets: Archivo → Crear una copia) "
    "y úsala. No dupliques la pestaña: en Google Sheets la copia seguiría leyendo los datos de la original.",
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
print({"desglose": FILA_DESGLOSE, "total_bruto": f_total, "isr": FILA_ISR, "neto": f_neto, "apoyo": FILA_APOYO, "fin": f_fin})
