# -*- coding: utf-8 -*-
"""Entregable ejecutivo: por qué el insumo que necesita ajuste es el IS del SONR."""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ---- Paleta corporativa (verde Patria / Grupo Peña Verde) -----------------------
PRIM  = "165C41"   # verde corporativo oscuro
SEC   = "2E8B57"   # verde medio
LIGHT = "E9F3EE"   # verde muy claro
BAND  = "F5F9F7"   # banda alterna
GOLD  = "B8860B"   # acento
RED   = "B3261E"   # alerta
AMBER = "C77700"   # atención
GREY  = "5A5A5A"
WHITE = "FFFFFF"
LINE  = "C9DCD2"

F = "Arial"
def font(sz=10, b=False, c="000000", i=False): return Font(name=F, size=sz, bold=b, color=c, italic=i)
def fill(c): return PatternFill("solid", fgColor=c)
def box(color=LINE, w="thin"):
    s = Side(style=w, color=color); return Border(left=s, right=s, top=s, bottom=s)
CEN = Alignment(horizontal="center", vertical="center")
CENW = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEF = Alignment(horizontal="left", vertical="center")
LEFW = Alignment(horizontal="left", vertical="top", wrap_text=True)
RIG = Alignment(horizontal="right", vertical="center")

wb = openpyxl.Workbook()

# =================================================================== DETALLE
det = wb.active; det.title = "Detalle por ramo"
DATOS = [  # ramo, nombre, real, proy, IS medio, IS min, IS max, diagnostico
    (60,  "Incendio",                   781.6306, 947.0695, 0.494616, 0.463219, 0.525705, "Nivel del IS"),
    (50,  "Marítimo y Transportes",     484.3106, 554.0311, 0.771450, 0.677071, 1.012100, "Nivel del IS"),
    (10,  "Vida",                       269.5091, 301.0093, 0.840814, 0.768490, 0.916569, "Nivel del IS"),
    (110, "Diversos",                   263.8070, 300.7269, 0.670353, 0.607958, 0.718422, "Nivel del IS"),
    (90,  "Automóviles",                149.2194, 167.3425, 0.730580, 0.671932, 0.815090, "Nivel del IS"),
    (40,  "Responsabilidad Civil",      115.2322, 120.6909, 0.528709, 0.449696, 0.629700, "En meta o cerca"),
    (35,  "Accidentes y Enfermedades",   20.3151,  36.4637, 0.847023, 0.782392, 0.964600, "Parámetro roto"),
    (39,  "Accidentes y Enfermedades",   13.6224,  62.9307, 0.106300, 0.106300, 0.106300, "Parámetro roto"),
    (31,  "Accidentes y Enfermedades",    4.8022,   4.4200, 0.569752, 0.376180, 1.091400, "En meta o cerca"),
    (100, "Crédito",                      1.1879,   0.8016, 0.016300, 0.016300, 0.016300, "Parámetro roto"),
]
ENC = ["Ramo", "Nombre del ramo", "SONR real\n(M USD)", "SONR proyectado\n(M USD)",
       "Razón\nproy / real", "Desviación", "IS actual", "IS que\ncuadraría",
       "Ajuste al IS", "IS mín\n2026", "IS máx\n2026", "¿El IS que cuadra\ncabe en su rango?", "Diagnóstico"]
ANCHO = [8, 30, 13, 16, 11, 11, 10, 11, 11, 9, 9, 18, 18]

det.merge_cells("B2:N2"); det["B2"] = "DETALLE POR RAMO · SONR proyectado contra real"
det["B2"].font = font(14, True, WHITE); det["B2"].fill = fill(PRIM); det["B2"].alignment = LEF
det.row_dimensions[2].height = 26
det.merge_cells("B3:N3")
det["B3"] = ("Escenario 2, BEL riesgo, en dólares. Ventana 202601–202607, que son los meses con cierre real disponible. "
             "El «IS que cuadraría» es el que haría que la proyección igualara al real: IS actual ÷ razón.")
det["B3"].font = font(9, c=GREY); det["B3"].alignment = LEFW; det.row_dimensions[3].height = 26

for j, (h, a) in enumerate(zip(ENC, ANCHO), start=2):
    c = det.cell(row=5, column=j, value=h)
    c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CENW; c.border = box(WHITE)
    det.column_dimensions[get_column_letter(j)].width = a
det.row_dimensions[5].height = 34
det.column_dimensions["A"].width = 2

r0 = 6
for i, (ram, nom, real, proy, ism, ismin, ismax, diag) in enumerate(DATOS):
    r = r0 + i
    vals = [ram, nom, real, proy,
            f"=IF(D{r}=0,\"\",E{r}/D{r})", f"=IF(F{r}=\"\",\"\",F{r}-1)", ism,
            f"=IF(F{r}=\"\",\"\",H{r}/F{r})", f"=IF(I{r}=\"\",\"\",I{r}/H{r}-1)",
            ismin, ismax,
            f"=IF(I{r}=\"\",\"\",IF(AND(I{r}>=K{r},I{r}<=L{r}),\"Sí\",\"No\"))", diag]
    for j, v in enumerate(vals, start=2):
        c = det.cell(row=r, column=j, value=v)
        c.font = font(10); c.border = box()
        c.fill = fill(BAND if i % 2 else WHITE)
    det.cell(row=r, column=2).alignment = CEN
    det.cell(row=r, column=3).alignment = LEF
    for j in (4, 5): det.cell(row=r, column=j).number_format = '#,##0.0'
    det.cell(row=r, column=6).number_format = '0.000'
    det.cell(row=r, column=7).number_format = '+0.0%;-0.0%;-'
    for j in (8, 9, 11, 12): det.cell(row=r, column=j).number_format = '0.000'
    det.cell(row=r, column=10).number_format = '+0.0%;-0.0%;-'
    for j in (6, 7, 8, 9, 10, 11, 12): det.cell(row=r, column=j).alignment = CEN
    det.cell(row=r, column=13).alignment = CEN
    det.cell(row=r, column=14).alignment = CEN
    det.cell(row=r, column=14).font = font(9, True, {"Nivel del IS": AMBER, "Parámetro roto": RED,
                                                     "En meta o cerca": PRIM}[diag])
rT = r0 + len(DATOS)
det.cell(row=rT, column=2, value="TOTAL").font = font(10, True, WHITE)
det.merge_cells(start_row=rT, start_column=2, end_row=rT, end_column=3)
for j in range(2, 15):
    c = det.cell(row=rT, column=j); c.fill = fill(PRIM); c.font = font(10, True, WHITE); c.border = box(WHITE)
det.cell(row=rT, column=4, value=f"=SUM(D{r0}:D{rT-1})").number_format = '#,##0.0'
det.cell(row=rT, column=5, value=f"=SUM(E{r0}:E{rT-1})").number_format = '#,##0.0'
det.cell(row=rT, column=6, value=f"=E{rT}/D{rT}").number_format = '0.000'
det.cell(row=rT, column=7, value=f"=F{rT}-1").number_format = '+0.0%;-0.0%;-'
for j in (4, 5, 6, 7): det.cell(row=rT, column=j).alignment = CEN if j > 5 else RIG
det.cell(row=rT, column=2).alignment = LEF

# indicadores derivados, abajo (los usa el Resumen)
rK = rT + 2
det.cell(row=rK, column=2, value="Indicadores derivados").font = font(11, True, PRIM)
IND = [
    ("Desviación total del SONR", f"=F{rT}-1", '+0.0%;-0.0%;-'),
    ("Ajuste al IS necesario, promedio ponderado de los ramos de «Nivel del IS»",
     f'=SUMPRODUCT(($N${r0}:$N${rT-1}="Nivel del IS")*$D${r0}:$D${rT-1}*$J${r0}:$J${rT-1})'
     f'/SUMPRODUCT(($N${r0}:$N${rT-1}="Nivel del IS")*$D${r0}:$D${rT-1})', '+0.0%;-0.0%;-'),
    ("Peso de esos ramos en el SONR real",
     f'=SUMPRODUCT(($N${r0}:$N${rT-1}="Nivel del IS")*$D${r0}:$D${rT-1})/D{rT}', '0.0%'),
    ("Ramos cuyo IS necesario NO cabe en el rango que el IS recorre en 2026",
     f'=COUNTIF(M{r0}:M{rT-1},"No")&" de "&COUNTA(M{r0}:M{rT-1})', '@'),
]
for i, (lab, f_, fmt) in enumerate(IND):
    r = rK + 1 + i
    det.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
    a = det.cell(row=r, column=2, value=lab); a.font = font(10); a.alignment = LEF; a.fill = fill(LIGHT)
    for j in range(3, 9): det.cell(row=r, column=j).fill = fill(LIGHT)
    b = det.cell(row=r, column=9, value=f_)
    b.font = font(11, True, PRIM); b.number_format = fmt; b.alignment = CEN; b.fill = fill(LIGHT)
    det.merge_cells(start_row=r, start_column=9, end_row=r, end_column=10)
    det.cell(row=r, column=10).fill = fill(LIGHT)
# --- contexto RRC (la otra metodología), para que el Resumen lo cite con fórmulas
rR = rK + 6
det.cell(row=rR, column=2, value="Contexto · RRC, la otra metodología").font = font(11, True, PRIM)
det.merge_cells(start_row=rR, start_column=2, end_row=rR, end_column=6)
det.cell(row=rR + 1, column=2, value="Ventana 202602–202605, BEL riesgo USD, sin CAT").font = font(9, c=GREY)
det.merge_cells(start_row=rR + 1, start_column=2, end_row=rR + 1, end_column=6)
RRCF = [("RRC real", 1141.2, None), ("RRC proyectado con el δ anterior", 1247.0, "razon_ant"),
        ("RRC proyectado con el δ recalibrado", 1142.9, "razon_new")]
det.merge_cells(start_row=rR + 2, start_column=2, end_row=rR + 2, end_column=4)
for j, h in zip([2, 5, 6, 7], ["Concepto", "M USD", "Razón proy / real", "Desviación"]):
    c = det.cell(row=rR + 2, column=j, value=h)
    c.font = font(9, True, WHITE); c.alignment = CENW
for j in range(2, 8):
    c = det.cell(row=rR + 2, column=j); c.fill = fill(SEC); c.border = box(WHITE)
for i, (lab, val, tag) in enumerate(RRCF):
    rr = rR + 3 + i
    det.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=4)
    det.cell(row=rr, column=2, value=lab).font = font(10, True if i == 2 else False)
    det.cell(row=rr, column=2).alignment = LEF
    det.cell(row=rr, column=5, value=val).number_format = '#,##0.0'
    if tag:
        det.cell(row=rr, column=6, value=f"=E{rr}/E{rR + 3}").number_format = '0.000'
        det.cell(row=rr, column=7, value=f"=F{rr}-1").number_format = '+0.0%;-0.0%;-'
    for j in range(2, 8):
        c = det.cell(row=rr, column=j); c.border = box(); c.alignment = CEN if j > 4 else LEF
        c.fill = fill(LIGHT if i == 2 else (BAND if i % 2 else WHITE))
        if i == 2 and j > 4: c.font = font(10, True, SEC)
det.cell(row=rR + 6, column=2, value="Fuente: recalibrar_delta_reforecast.py sobre ConsultaPPTO_RRC 2–5 contra la RRC real.").font = font(8, c=GREY, i=True)
det.merge_cells(start_row=rR + 6, start_column=2, end_row=rR + 6, end_column=8)

det.freeze_panes = "B6"

# =================================================================== POR QUÉ EL IS
por = wb.create_sheet("Por qué el IS")
por.column_dimensions["A"].width = 2
for col, w in zip("BCDEFGHIJK", [26, 13, 13, 13, 13, 13, 13, 13, 13, 13]):
    por.column_dimensions[col].width = w

por.merge_cells("B2:K2"); por["B2"] = "POR QUÉ EL INSUMO QUE NECESITA AJUSTE ES EL IS"
por["B2"].font = font(14, True, WHITE); por["B2"].fill = fill(PRIM); por["B2"].alignment = LEF
por.row_dimensions[2].height = 26

def titulo(ws, r, txt, sub=None, ancho=10):
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=1 + ancho)
    c = ws.cell(row=r, column=2, value=txt); c.font = font(11, True, WHITE); c.fill = fill(SEC); c.alignment = LEF
    ws.row_dimensions[r].height = 20
    if sub:
        ws.merge_cells(start_row=r + 1, start_column=2, end_row=r + 1, end_column=1 + ancho)
        d = ws.cell(row=r + 1, column=2, value=sub); d.font = font(9, c=GREY); d.alignment = LEFW
        ws.row_dimensions[r + 1].height = 28

titulo(por, 4, "PASO 1 · El SONR es el producto de tres factores",
       "El script calcula, para cada ramo y cada cohorte de suscripción:   BEL = Prima Devengada × LAG × IS. "
       "Se verificó contra la corrida real: la reconstrucción cuadra con un error relativo de 1.9e-16, o sea exacta.")
FAC = [
    ("Prima Devengada", "La prima que el reaseguro tomó, devengada.\nSale de nuestra propia consulta.",
     "El FND sólo la toca en los últimos 12 meses", "Parcial", AMBER),
    ("LAG", "Qué fracción de la siniestralidad aún no se reporta,\npor año de desarrollo.",
     "Insumo entregado por el área actuarial", "No", GREY),
    ("IS", "Índice de siniestralidad: siniestros esperados\npor cada peso de prima devengada.",
     "Insumo entregado por el área actuarial", "No", RED),
]
r = 7
for h, txt in zip(["Factor", "Qué es", "¿De dónde viene?", "¿Lo controla\nPlaneación?"], [0, 0, 0, 0]):
    pass
enc = ["Factor", "Qué es", "¿De dónde viene?", "¿Lo mueve\nPlaneación?"]
por.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
por.cell(row=r, column=2, value=enc[0]); por.cell(row=r, column=3, value=enc[1])
por.merge_cells(start_row=r, start_column=6, end_row=r, end_column=8)
por.cell(row=r, column=6, value=enc[2]); por.cell(row=r, column=9, value=enc[3])
por.merge_cells(start_row=r, start_column=9, end_row=r, end_column=10)
for j in range(2, 11):
    c = por.cell(row=r, column=j); c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CENW; c.border = box(WHITE)
por.row_dimensions[r].height = 28
for i, (nom, que, ori, mueve, col) in enumerate(FAC):
    rr = r + 1 + i
    por.cell(row=rr, column=2, value=nom).font = font(11, True, col)
    por.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=5)
    por.cell(row=rr, column=3, value=que).font = font(9)
    por.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=8)
    por.cell(row=rr, column=6, value=ori).font = font(9)
    por.merge_cells(start_row=rr, start_column=9, end_row=rr, end_column=10)
    por.cell(row=rr, column=9, value=mueve).font = font(10, True, col)
    for j in range(2, 11):
        c = por.cell(row=rr, column=j); c.border = box(); c.fill = fill(BAND if i % 2 else WHITE)
        c.alignment = LEFW if j in (3, 6) else CEN
    por.row_dimensions[rr].height = 32

titulo(por, 12, "PASO 2 · El FND no alcanza: el 78% del SONR viene de cohortes que no puede tocar",
       "El FND sólo cambia la prima registrada en los últimos 12 meses. Ese tramo vive casi todo en la cohorte 1. "
       "Las cohortes 2 en adelante son negocio de años anteriores, donde el FND vale cero en las dos metodologías.")
COH = [(1, 22.16), (2, 37.43), (3, 24.23), (4, 10.41), (5, 3.21), (6, 1.58), (7, 0.70), (8, 0.21), (9, 0.07), (10, 0.00)]
r = 15
por.cell(row=r, column=2, value="Cohorte (años de desarrollo)").font = font(9, True, WHITE)
por.cell(row=r, column=2).fill = fill(SEC); por.cell(row=r, column=2).alignment = LEF
for i, (n, _) in enumerate(COH):
    c = por.cell(row=r, column=3 + i, value=n); c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CEN
por.cell(row=r + 1, column=2, value="% del SONR que aporta").font = font(9, True)
por.cell(row=r + 1, column=2).alignment = LEF; por.cell(row=r + 1, column=2).fill = fill(LIGHT)
for i, (n, p) in enumerate(COH):
    c = por.cell(row=r + 1, column=3 + i, value=p / 100)
    c.number_format = '0.0%'; c.alignment = CEN; c.border = box()
    c.font = font(10, True, PRIM if n == 1 else "000000")
    c.fill = fill(LIGHT if n == 1 else WHITE)
por.cell(row=r + 2, column=2, value="¿El FND puede moverla?").font = font(9, True)
por.cell(row=r + 2, column=2).alignment = LEF; por.cell(row=r + 2, column=2).fill = fill(LIGHT)
for i, (n, _) in enumerate(COH):
    c = por.cell(row=r + 2, column=3 + i, value="Sí" if n == 1 else "No")
    c.font = font(10, True, SEC if n == 1 else RED); c.alignment = CEN; c.border = box()
por.merge_cells(start_row=r + 4, start_column=2, end_row=r + 4, end_column=11)
c = por.cell(row=r + 4, column=2,
             value="Consecuencia medida: barriendo δ de −0.60 a +0.95 —todo el rango imaginable— el SONR de Incendio "
                   "sólo se mueve entre 1.188 y 1.234. Nunca llega a 1.05. Diversos se mueve menos de un punto.")
c.font = font(10, True, AMBER); c.alignment = LEFW; c.fill = fill("FFF6E5"); c.border = box(AMBER)
por.row_dimensions[r + 4].height = 30

titulo(por, 22, "PASO 3 · El ajuste que hace falta está fuera del rango que el IS recorre en el año",
       "Si Prima Devengada y LAG estuvieran bien, el IS tendría que bajar entre 10% y 17% en los cinco ramos pesados. "
       "Ese valor queda por debajo del mínimo que el propio IS toma en cualquier mes de 2026: no es ruido del mes, es nivel.")
COMP = [("Incendio", 0.494616, 0.408, 0.463219, 0.525705),
        ("Marítimo y Transportes", 0.771450, 0.674, 0.677071, 1.012100),
        ("Diversos", 0.670353, 0.588, 0.607958, 0.718422),
        ("Automóviles", 0.730580, 0.651, 0.671932, 0.815090),
        ("Vida", 0.840814, 0.753, 0.768490, 0.916569)]
r = 25
enc2 = ["Ramo", "IS actual", "IS que\ncuadraría", "IS mín\n2026", "IS máx\n2026", "¿Cabe en\nel rango?"]
por.cell(row=r, column=2, value=enc2[0])
for j, h in enumerate(enc2[1:], start=3):
    por.cell(row=r, column=j, value=h)
for j in range(2, 8):
    c = por.cell(row=r, column=j); c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CENW; c.border = box(WHITE)
por.row_dimensions[r].height = 30
for i, (nom, act, nec, mn, mx) in enumerate(COMP):
    rr = r + 1 + i
    por.cell(row=rr, column=2, value=nom).alignment = LEF
    por.cell(row=rr, column=3, value=act).number_format = '0.000'
    por.cell(row=rr, column=4, value=nec).number_format = '0.000'
    por.cell(row=rr, column=5, value=mn).number_format = '0.000'
    por.cell(row=rr, column=6, value=mx).number_format = '0.000'
    por.cell(row=rr, column=7, value=f'=IF(AND(D{rr}>=E{rr},D{rr}<=F{rr}),"Sí","No")')
    for j in range(2, 8):
        c = por.cell(row=rr, column=j); c.font = font(10); c.border = box(); c.alignment = CEN if j > 2 else LEF
        c.fill = fill(BAND if i % 2 else WHITE)
    por.cell(row=rr, column=4).font = font(10, True, RED)
    por.cell(row=rr, column=7).font = font(10, True, RED)
por.merge_cells(start_row=r + 7, start_column=2, end_row=r + 7, end_column=11)
c = por.cell(row=r + 7, column=2,
             value="Lectura: el IS y la base de prima no están calibrados uno contra el otro. O el IS se estimó sobre otra "
                   "base de prima, o la que arma nuestra consulta es 10–17% mayor que la que el IS supone. "
                   "No es que uno de los dos esté mal por separado: son inconsistentes entre sí.")
c.font = font(10, True, PRIM); c.alignment = LEFW; c.fill = fill(LIGHT); c.border = box(SEC)
por.row_dimensions[r + 7].height = 34

# =================================================================== ALERTA TC
al = wb.create_sheet("Alerta · Tipo de cambio")
al.column_dimensions["A"].width = 2
for col, w in zip("BCDEFGHIJ", [22, 14, 14, 14, 14, 14, 14, 14, 14]):
    al.column_dimensions[col].width = w
al.merge_cells("B2:J2"); al["B2"] = "ALERTA · EL SONR DE SEPTIEMBRE A DICIEMBRE SALE EN CERO"
al["B2"].font = font(14, True, WHITE); al["B2"].fill = fill(RED); al["B2"].alignment = LEF
al.row_dimensions[2].height = 26
al.merge_cells("B3:J3")
al["B3"] = ("Hallazgo independiente del tema del IS, y de mayor impacto: el cierre de diciembre —la reserva de fin de "
            "ejercicio— se está reportando en cero. Verificado en la salida cruda del script (SONR_esc.xlsx).")
al["B3"].font = font(10, c=GREY); al["B3"].alignment = LEFW; al.row_dimensions[3].height = 28

MES = [(202601, 334.09), (202602, 342.20), (202603, 350.06), (202604, 365.71),
       (202605, 387.31), (202606, 394.42), (202607, 414.28), (202608, 370.97),
       (202609, 0.0), (202610, 0.0), (202611, 0.0), (202612, 0.0)]
r = 6
al.cell(row=r, column=2, value="Mes de valuación").font = font(9, True, WHITE)
al.cell(row=r, column=2).fill = fill(SEC); al.cell(row=r, column=2).alignment = LEF
for i, (m, _) in enumerate(MES[:6]):
    c = al.cell(row=r, column=3 + i, value=m); c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CEN
al.cell(row=r + 1, column=2, value="SONR BEL (M USD)").font = font(9, True); al.cell(row=r + 1, column=2).alignment = LEF
for i, (m, v) in enumerate(MES[:6]):
    c = al.cell(row=r + 1, column=3 + i, value=v); c.number_format = '#,##0.0'; c.alignment = CEN; c.border = box()
    c.font = font(11, True)
al.cell(row=r + 3, column=2, value="Mes de valuación").font = font(9, True, WHITE)
al.cell(row=r + 3, column=2).fill = fill(SEC); al.cell(row=r + 3, column=2).alignment = LEF
for i, (m, _) in enumerate(MES[6:]):
    c = al.cell(row=r + 3, column=3 + i, value=m); c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CEN
al.cell(row=r + 4, column=2, value="SONR BEL (M USD)").font = font(9, True); al.cell(row=r + 4, column=2).alignment = LEF
for i, (m, v) in enumerate(MES[6:]):
    c = al.cell(row=r + 4, column=3 + i, value=v); c.number_format = '#,##0.0'; c.alignment = CEN; c.border = box()
    cero = (v == 0)
    c.font = font(11, True, RED if cero else "000000"); c.fill = fill("FDEAE8" if cero else WHITE)

titulo(al, 13, "La causa, en una línea", None, 9)
al.merge_cells("B14:J14")
al["B14"] = ("No hay tipo de cambio cargado más allá de 202608. En ConsultaReal la llave «mes de valuación – moneda» no "
             "cruza, el tipo de cambio queda vacío y la prima devengada sale vacía. Después, la suma que arma «Prima Dev» "
             "convierte un conjunto de vacíos en CERO —no en vacío—, así que la fila sí se escribe, con cero, y nadie "
             "recibe un error.")
al["B14"].font = font(10); al["B14"].alignment = LEFW; al["B14"].fill = fill("FDEAE8"); al["B14"].border = box(RED)
al.row_dimensions[14].height = 46

titulo(al, 17, "Qué comprobar y qué hacer", None, 9)
PASOS = [
    ("La prima sí llega", "PmaTomOri suma 972 mil millones de pesos en esos meses y el devengamiento es 1.0. "
                          "El problema no es la prima ni el FND: es la conversión."),
    ("El insumo que falta", "TablaTCSONR.xlsx y TablaTCRRC.xlsx terminan en 202608, y la tabla de tipos de cambio de "
                            "la base de valuación tampoco trae septiembre en adelante."),
    ("Acción", "Cargar los tipos de cambio de septiembre a diciembre y volver a correr. Hasta entonces el cierre anual "
               "no es utilizable, y esto pesa más que la desviación del IS."),
    ("Nota sobre el RRC", "El RRC no lo sufre igual: su Base RRC simplemente no genera filas después de 202608, "
                          "en vez de generarlas en cero. Se nota a simple vista; el del SONR no."),
]
for i, (t, d) in enumerate(PASOS):
    rr = 18 + i
    al.cell(row=rr, column=2, value=t).font = font(10, True, PRIM)
    al.cell(row=rr, column=2).alignment = LEF
    al.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=10)
    c = al.cell(row=rr, column=3, value=d); c.font = font(9); c.alignment = LEFW
    for j in range(2, 11):
        al.cell(row=rr, column=j).fill = fill(BAND if i % 2 else WHITE)
        al.cell(row=rr, column=j).border = box()
    al.row_dimensions[rr].height = 30

# =================================================================== RESUMEN
res = wb.create_sheet("Resumen", 0)
res.column_dimensions["A"].width = 2
for col, w in zip("BCDEFGHIJK", [6, 20, 13, 13, 13, 13, 13, 13, 13, 6]):
    res.column_dimensions[col].width = w

res.merge_cells("B2:J2"); res["B2"] = "RESERVA SONR · POR QUÉ EL INSUMO QUE NECESITA AJUSTE ES EL IS"
res["B2"].font = font(16, True, WHITE); res["B2"].fill = fill(PRIM); res["B2"].alignment = LEF
res.row_dimensions[2].height = 32
res.merge_cells("B3:J3")
res["B3"] = "Reaseguradora Patria · Planeación Financiera (BP&A) · Ventana 202601–202607 · Escenario 2, BEL riesgo, USD"
res["B3"].font = font(9, c=WHITE); res["B3"].fill = fill(SEC); res["B3"].alignment = LEF
res.row_dimensions[3].height = 18

res.merge_cells("B5:J6")
res["B5"] = ("El modelo de devengamiento (FND) ya llevó el RRC a la meta. El SONR no llega, y no puede llegar por ahí: "
             "el 78% de esa reserva viene de cohortes que el FND no toca. El único factor con capacidad de mover el "
             "nivel es el IS, y el ajuste que haría falta es de −14% en promedio ponderado.")
res["B5"].font = font(12, True, PRIM); res["B5"].alignment = LEFW; res["B5"].fill = fill(LIGHT); res["B5"].border = box(SEC)
res.row_dimensions[5].height = 24; res.row_dimensions[6].height = 24

# --- KPI
KPI = [("RRC", f"='Detalle por ramo'!G{rR + 5}", "Desviación con el δ recalibrado", "EN META", SEC, '+0.0%;-0.0%;-'),
       ("SONR", f"='Detalle por ramo'!I{rK + 1}", "Desviación de la proyección", "FUERA DE META", RED, '+0.0%;-0.0%;-'),
       ("IS", f"='Detalle por ramo'!I{rK + 2}", "Ajuste necesario al IS", "ACCIÓN REQUERIDA", AMBER, '+0.0%;-0.0%;-')]
r = 8
for i, (t, f_, sub, tag, col, fmt) in enumerate(KPI):
    c0 = 2 + i * 3
    res.merge_cells(start_row=r, start_column=c0, end_row=r, end_column=c0 + 1)
    a = res.cell(row=r, column=c0, value=t); a.font = font(11, True, WHITE); a.fill = fill(col); a.alignment = CEN
    res.cell(row=r, column=c0 + 1).fill = fill(col)
    res.merge_cells(start_row=r + 1, start_column=c0, end_row=r + 2, end_column=c0 + 1)
    b = res.cell(row=r + 1, column=c0, value=f_); b.font = font(26, True, col); b.alignment = CEN; b.number_format = fmt
    res.merge_cells(start_row=r + 3, start_column=c0, end_row=r + 3, end_column=c0 + 1)
    d = res.cell(row=r + 3, column=c0, value=sub); d.font = font(9, c=GREY); d.alignment = CEN
    res.merge_cells(start_row=r + 4, start_column=c0, end_row=r + 4, end_column=c0 + 1)
    e = res.cell(row=r + 4, column=c0, value=tag); e.font = font(9, True, WHITE); e.fill = fill(col); e.alignment = CEN
    for rr in range(r, r + 5):
        for j in (c0, c0 + 1):
            res.cell(row=rr, column=j).border = box(col)
res.row_dimensions[r].height = 18
res.row_dimensions[r + 1].height = 22
res.row_dimensions[r + 2].height = 22
res.row_dimensions[r + 4].height = 16

titulo(res, 15, "EL RAZONAMIENTO, EN TRES PASOS", None, 9)
RAZ = [
    ("1", "El SONR es un producto de tres factores",
     "BEL = Prima Devengada × LAG × IS. Verificado contra la corrida real: la reconstrucción es exacta."),
    ("2", "El FND sólo alcanza al 22% de la base",
     "Sólo mueve prima registrada en los últimos 12 meses. El 78% del SONR viene de cohortes anteriores, "
     "donde el FND vale cero en las dos metodologías. Medido: barriendo δ en todo su rango, Incendio se mueve "
     "sólo entre 1.188 y 1.234."),
    ("3", "El ajuste que falta está fuera del rango del IS",
     "En los cinco ramos que pesan el 92%, el IS tendría que bajar entre 10% y 17%, por debajo del mínimo que "
     "el propio IS toma en cualquier mes de 2026. No es ruido: es nivel."),
]
r = 16
for i, (n, t, d) in enumerate(RAZ):
    rr = r + i
    c = res.cell(row=rr, column=2, value=n); c.font = font(20, True, WHITE); c.fill = fill(SEC); c.alignment = CEN
    res.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=4)
    a = res.cell(row=rr, column=3, value=t); a.font = font(10, True, PRIM); a.alignment = LEFW
    res.merge_cells(start_row=rr, start_column=5, end_row=rr, end_column=10)
    b = res.cell(row=rr, column=5, value=d); b.font = font(9); b.alignment = LEFW
    for j in range(2, 11):
        res.cell(row=rr, column=j).border = box(); res.cell(row=rr, column=j).fill = fill(BAND if i % 2 else WHITE)
    res.cell(row=rr, column=2).fill = fill(SEC)
    res.row_dimensions[rr].height = 34

titulo(res, 21, "QUÉ SE NECESITA", None, 9)
ACC = [("1", "Cargar el tipo de cambio de septiembre a diciembre", "Planeación Financiera", "Inmediato",
        "Sin él, el SONR de esos cuatro meses sale en CERO y el cierre anual no es utilizable. Ver la hoja de alerta."),
       ("2", "Reconciliar el IS con la base de prima", "Área actuarial", "Alta",
        "El IS entregado, aplicado a la prima que produce nuestra consulta, tendría que bajar entre 10% y 17% en "
        "los ramos que pesan el 93%. Uno de los dos tiene que ajustarse."),
       ("3", "Revisar los parámetros de los ramos 39 y 35", "Área actuarial", "Alta",
        "El ramo 39 proyecta 4.6 veces el real: su curva de desarrollo no reporta nada durante cuatro años y su "
        "IS está congelado en 0.1063 todo el año. Ahí el parámetro está roto, no el nivel."),
       ("4", "Mantener el δ recalibrado en el RRC", "Planeación Financiera", "Hecho",
        "Lleva el RRC de +9.3% a +0.2%, y no empeora el SONR.")]
r = 22
enc3 = ["#", "Acción", "Responsable", "Prioridad", "Por qué"]
res.cell(row=r, column=2, value=enc3[0])
res.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4); res.cell(row=r, column=3, value=enc3[1])
res.cell(row=r, column=5, value=enc3[2]); res.cell(row=r, column=6, value=enc3[3])
res.merge_cells(start_row=r, start_column=7, end_row=r, end_column=10); res.cell(row=r, column=7, value=enc3[4])
for j in range(2, 11):
    c = res.cell(row=r, column=j); c.font = font(9, True, WHITE); c.fill = fill(SEC); c.alignment = CEN; c.border = box(WHITE)
for i, (n, a_, resp, pri, why) in enumerate(ACC):
    rr = r + 1 + i
    res.cell(row=rr, column=2, value=n).font = font(11, True, PRIM)
    res.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=4)
    res.cell(row=rr, column=3, value=a_).font = font(10, True)
    res.cell(row=rr, column=5, value=resp).font = font(9)
    pc = res.cell(row=rr, column=6, value=pri)
    pc.font = font(9, True, {"Inmediato": RED, "Alta": AMBER, "Hecho": SEC}[pri])
    res.merge_cells(start_row=rr, start_column=7, end_row=rr, end_column=10)
    res.cell(row=rr, column=7, value=why).font = font(9)
    for j in range(2, 11):
        c = res.cell(row=rr, column=j); c.border = box(); c.fill = fill(BAND if i % 2 else WHITE)
        c.alignment = LEFW if j in (3, 7) else CEN
    res.row_dimensions[rr].height = 32

res.merge_cells("B28:J28")
res["B28"] = ("Nota de método: todas las cifras salen de la corrida del propio script (SONR_esc.xlsx y el volcado de "
              "Metodo_propio), contrastadas contra el cierre real de SAP. Las celdas verdes son fórmulas vivas: si "
              "cambias el real o la proyección en «Detalle por ramo», todo lo demás se recalcula.")
res["B28"].font = font(8, c=GREY, i=True); res["B28"].alignment = LEFW
res.row_dimensions[28].height = 26

# --- presentación e impresión -------------------------------------------------
AREAS = {"Resumen": "A1:J28", "Detalle por ramo": "A1:N32",
         "Por qué el IS": "A1:L33", "Alerta · Tipo de cambio": "A1:J22"}
for ws in wb.worksheets:
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    if ws.title in AREAS:
        ws.print_area = AREAS[ws.title]
wb.active = 0
wb.save("SONR_Diagnostico_Ejecutivo.xlsx")
print("guardado")
