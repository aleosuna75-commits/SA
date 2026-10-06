# -*- coding: utf-8 -*-
"""Configuracion local de los scripts del area (RRC y SONR) con insumos de la BD proyectada.

Copia este archivo como ``config_local.py`` en la misma carpeta y pon tus rutas y parametros. ``config_local.py``
no se versiona (lleva rutas internas y parametros de capital). Todo lo que no este aqui lo toman los scripts de la
BD proyectada (``RUTA_BD``).
"""
from pathlib import Path

CARPETA = Path(__file__).resolve().parent            # la carpeta local donde estan estos scripts

# ---- BD proyectada (salida de proyeccion_reservas.py). Abre y guarda la BD en Excel antes de correr, para que las
# formulas (montos y factores proyectados) tengan valor; si no, se toman del Diagnostico de la misma corrida.
RUTA_BD = CARPETA / "BD_ BEL - IRR - MR_Proyeccion.xlsx"
RUTA_DIAGNOSTICO = CARPETA / "Diagnostico_Proyeccion.xlsx"     # opcional
CARPETA_SALIDA = CARPETA / "salidas_area"                        # RRC_esc.xlsx, SONR_esc.xlsx, Parametros_usados_*.xlsx

# ---- Periodo de valuacion. None = el del ultimo mes real de la BD (hoy 2026 y 8)
ANIO = None
MES = None

# ---- Indices
USAR_IS_FA = True                                     # IS de la funcion actuarial (hoja IS_FA) en los meses proyectados de
RAMOS_IS_FA = {"RRC": (40, 50, 80, 90), "SONR": (40, 50, 80, 90)}   # estos ramos (los mismos del BEL por FND de la BD)

# ---- Escenarios
MESES_FALTANTES_ESC3 = "BD"      # meses que el script no valua en el escenario 3: "BD" = saldos proyectados de la BD;
                                 # "CSV" = los del presupuesto en Escenario_base_<reserva>.csv (escenario 1), como antes
ESCENARIO_BASE_CSV = {"RRC": CARPETA / "Escenario_base_RRC.csv",      # opcional: renglones del escenario 1 (presupuesto);
                      "SONR": CARPETA / "Escenario_base_SONR.csv"}    # el escenario 0 (ano base) sale de la BD
GUARDAR_INTERMEDIOS = False      # True = guarda en CARPETA_SALIDA las consultas intermedias (ConsultaR, ConsultaPPTO...)

# ---- Base de valuacion (Access) y archivos del area que la BD no trae
ACCESS_DBQ = r"\\SERVIDOR\CARPETA\BaseValuacion.accdb"
CATALOGOS = r"C:\RUTA\CentralizadoCatálogos_SIRECySAP.xlsx"          # hoja Valores: xRamo (J:M) y xPais (O:T)
CSV_AUXILIARES_RRC = r"C:\RUTA\CSV Auxiliares"                        # LlavesPol, AjManuales, Subramo, CesionPI, AFUN,
                                                                      # zFrecuencias, TablaCesion_Esc1, Cesion ID Esp
CSV_AUXILIARES_SONR = r"C:\RUTA\CSV Auxiliares"                       # AjManuales_SONR, Subramo, TablaBase_MetodoPropio
CSV_DURACION_RRC = CSV_AUXILIARES_RRC + r"\ParametrosMens2026.csv"    # solo Pesos_dur, Resto Monedas_dur, Pesos_ret y
                                                                      # Resto Monedas_ret (el MR); los indices van de la BD
CSV_IS_CAT = CSV_AUXILIARES_RRC + r"\IS_Cat.csv"                      # opcional: 71 y 73 en meses anteriores a HParametros
PPTO_TECNICO_RRC = r"C:\RUTA\PptoTecnico2026.csv"                     # presupuesto tecnico del ano de valuacion
PPTO_TECNICO_SONR = r"C:\RUTA\PptoTecnico2026.csv"
CSV_PARAM_SONR = CSV_AUXILIARES_SONR + r"\ParamSONR2026.csv"   # ParamSONR del area, solo para RAMOS_FACTOR_RET_CSV
RAMOS_FACTOR_RET_CSV = ()        # ramos cuyo Factor_Ret se toma del CSV del area y no de 1 - IRR / BEL de la BD, p. ej.
                                 # (31,): en Acc. Personales SAP registra IRR mayor que el BEL desde jun-26 y la BD da 0
FINVIG_AJUSTE_MANUAL = 45930     # FinVig (serial de Excel) con que vienen los ajustes manuales del SONR; su FND es 0

# ---- Margen de riesgo: parametros del area (ponlos tal cual los traen los scripts originales)
MR_RRC = {"REAL": {"RCS": None, "COC": 0.1},              # ConsultaReal (escenarios 2 y 3): MR = -DESV x RCS x COC x DUR / BC_total
          "REAL_USD": {"RCS": None, "COC": 0.1},          # ConsultaReal_USD (escenario 4, parte real)
          "PPTO": {"RCS": None, "BC": None, "COC": 0.1},  # ConsultaPPTO (escenario 4, parte presupuesto): divide entre BC
          "BC_SONR": 0.0}                                 # base de capital del SONR que se suma a la del RRC
MR_SONR = {"BC": None, "BC2": None}                       # Metodo propio: MR = Desviacion / -BC x BC2
