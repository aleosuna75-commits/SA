# -*- coding: utf-8 -*-
"""
PROYECCION DE INDICES Y MONTOS DE RESERVAS  (202609 - 202712)
==============================================================

Proyecta, con exactamente el mismo formato de los archivos actuales:

  1. "BD_ BEL - IRR - MR.xlsx"
       * HParametros_2026  -> indices (Ind Sin RRC, Ind sin RRC 99.5%, Ind Sin SONR
                              Media, Ind Sin SONR 99.5%) y LAG 1..LAG 10, solo a partir
                              de los renglones "Real" (el mismo filtro de la hoja).
       * BD_Montos_RRC_SONR -> RRC (NETO, BRUTO, BEL, GTO, IRR, MR) y SONR (NETO,
                              BRUTO, BEL, IRR, MR) por ramo.
  2. "BD_ RFV.xlsx" (Fianzas, ya llena por el usuario)
       * BD_Montos_RRC_SONR -> RFV NETO, RFV BRUTO, RFV IRR y RCONT por ramo.

METODOLOGIA (resumen; el detalle queda en salidas/Diagnostico_Proyeccion.xlsx)
------------------------------------------------------------------------------
a) Coherencia contable. No se proyectan todas las lineas por separado: se proyectan
   los "drivers" y el resto se deriva, de modo que las identidades que cumple la
   historia se cumplen tambien en la proyeccion:
       RRC :  BEL (nivel),  g = GTO/BEL,  m = MR/BEL,  c = IRR/BRUTO (razones)
              GTO = g*BEL ; MR = m*BEL ; BRUTO = BEL+GTO+MR ; IRR = c*BRUTO ; NETO = BRUTO-IRR
       SONR:  BEL (nivel),  m = MR/BEL,  c = IRR/BRUTO
              MR = m*BEL ; BRUTO = BEL+MR ; IRR = c*BRUTO ; NETO = BRUTO-IRR
       RFV :  BRUTO (nivel), c = IRR/BRUTO ; IRR = c*BRUTO ; NETO = BRUTO-IRR
              RCONT: se proyecta el total y se reparte por ramo con la mezcla de los ultimos 8 meses.
b) Modelo (MODELO_POR_TIPO):
       - montos (BEL, BRUTO), indices de HParametros y LAGs -> linea de TENDENCIA HISTORICA: regresion
         lineal (en logaritmos cuando la serie es positiva, es decir crecimiento % constante) sobre los
         ultimos MESES_TENDENCIA meses (36), continuada desde el ultimo dato real sin amortiguar
         (AMORTIGUACION_TENDENCIA = 1). En montos e indices se suma LA ESTACIONALIDAD MENSUAL: el patron
         por mes del ano (promedio, por mes, de la serie menos su media movil de 12 meses, sobre los
         mismos 36 meses) ponderado por su credibilidad (Buhlmann, Z = n/(n+K): 1 = el patron se
         repite igual cada ano, 0 = ruido). Los LAGs (patron de desarrollo) van solo con la recta.
         En los indices (razones que se mueven en una banda y rebotan) la desviacion del ultimo mes
         respecto al modelo se desvanece hacia el nivel del ultimo ano (PERSISTENCIA_DESVIACION 0.8) y
         la pendiente se proyecta ponderada por su credibilidad (R2 ajustado de la recta,
         CREDIBILIDAD_PENDIENTE); en montos y LAGs la desviacion se conserva (la proyeccion arranca
         del ultimo real) y la pendiente se proyecta completa.
         Es la linea de tendencia de Excel con los picos y valles del ano: la proyeccion sale paralela
         a ella, arranca del ultimo real y repite el patron en la medida en que se ha repetido;
       - razones (%GTO, %MR, %cedido) -> SES (nivel suavizado, sin tendencia: dependen de los contratos);
       - RCONT -> Holt-Winters sin tendencia: nivel suavizado mas estacionalidad por mes del trimestre
         (acumula en los meses 1-2 y libera en el 3) si hay al menos 12 meses; con menos, SES (nivel).
   Los intervalos al 80% salen de la variabilidad mensual alrededor de la tendencia (crece con la raiz
   del horizonte) o del propio modelo de suavizamiento.
c) Backtest por serie: se vuelve a proyectar desde 16, 12 y 8 meses antes del final y se mide el
   error contra lo real, del modelo y de las alternativas simples (ultimo valor y SES). Se
   reporta por serie (Series_Modelos) y por tipo (Backtest); no cambia el modelo.
d) Reglas actuariales / de calidad de datos (todas reportadas en la hoja "Alertas"):
       - series en cero en los ultimos 6 meses -> se proyectan en cero;
       - parametros "en escalon" (se actualizan esporadicamente, >=50% de meses sin
         cambio) -> se mantiene el ultimo valor;
       - series cortas (< 6 obs) -> SES; (< 4 obs) -> ultimo valor;
       - dominio actuarial: cesion en [0, 1], %GTO y %MR >= 0, LAGs >= 0, montos >= 0;
       - alerta de saltos atipicos en el ultimo mes y de cambios proyectados mayores a los
         observados en la historia;
       - 99.5% >= media cuando asi ha sido siempre en la historia del ramo;
       - textos con espacios / celdas vacias se limpian; huecos <= 6 meses se interpolan, salvo que separen
         dos niveles con razon mayor a SALTO_NIVEL_HUECO (entonces se usa solo la historia posterior)
         y con huecos mayores solo se usa la historia posterior;
       - LAG en 0 despues de que el patron acumulado ya supero 50% se trata como faltante.
   Los montos de Danos se modelan en USD; los de Fianzas en MXN y se convierten con el TC de Inversiones
   (MODELAR_EN_MXN).

USO: abrir en VSCode y ejecutar (F5 o "Run Python File"). Los paquetes que falten se
instalan automaticamente en el interprete activo. Parametros en la seccion CONFIGURACION.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys

# Un hilo de BLAS por proceso: el paralelismo se hace por series (evita sobresuscripcion de CPU).
# Debe definirse antes de importar numpy / statsmodels.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
             "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")


def _asegurar_paquetes(paquetes: dict[str, str]) -> None:
    """Instala con el mismo interprete que ejecuta el script los paquetes que falten."""
    faltantes = []
    for modulo, nombre_pip in paquetes.items():
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltantes.append(nombre_pip)
    if faltantes:
        print(f"Instalando paquetes faltantes: {', '.join(faltantes)} ...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *faltantes])
        except subprocess.CalledProcessError as e:
            raise SystemExit(f"No se pudieron instalar {faltantes} (sin internet, proxy o permisos). Instalalos "
                             f"manualmente con: {sys.executable} -m pip install {' '.join(faltantes)}") from e
        # si pip instalo en la carpeta de usuario (Python 'para todos los usuarios' en Windows), agregarla
        import site
        usuario = site.getusersitepackages()
        if os.path.isdir(usuario) and usuario not in sys.path:
            site.addsitedir(usuario)
        importlib.invalidate_caches()


_asegurar_paquetes({
    "openpyxl": "openpyxl>=3.1",
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "statsmodels": "statsmodels>=0.14",
    "matplotlib": "matplotlib",
})

import math  # noqa: E402

import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from copy import copy  # noqa: E402
from dataclasses import dataclass, field, replace  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import openpyxl  # noqa: E402
from openpyxl.formula.translate import Translator  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import f_oneway as _f_oneway, norm as _normal  # noqa: E402
from statsmodels.tsa.exponential_smoothing.ets import ETSModel  # noqa: E402

# Los scripts se apoyan unos en otros: deben estar todos en la misma carpeta (tal como vienen en el zip).
_FALTAN = [n for n in ("excel_fiel.py", "tipo_cambio.py", "dashboard.py", "dashboard_html.py")
           if not (Path(__file__).resolve().parent / n).exists()]
if _FALTAN:
    raise SystemExit(f"Faltan en la carpeta {Path(__file__).resolve().parent}: {', '.join(_FALTAN)}. "
                     "Copia todos los archivos del zip a esa misma carpeta y vuelve a correr.")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from excel_fiel import guardar_libro, verificar_escritura  # noqa: E402
from tipo_cambio import TC_FCST  # noqa: E402
try:                                  # factor de prima (opcional: sin primas.py o si falla, se usa la recta)
    import primas  # noqa: E402
    _ERROR_PRIMAS = ""
except Exception as _e:  # noqa: BLE001
    primas = None
    _ERROR_PRIMAS = f"{type(_e).__name__}: {_e}"

# =============================================================================
# CONFIGURACION
# =============================================================================
CARPETA = Path(__file__).resolve().parent
ENTRADAS = CARPETA / "entradas"
SALIDAS = CARPETA / "salidas"

ARCHIVO_BD_DANOS = ENTRADAS / "BD_ BEL - IRR - MR.xlsx"
ARCHIVO_BD_RFV = ENTRADAS / "BD_ RFV.xlsx"       # BD de Fianzas ya llena (se lee tal cual, no se regenera)

SALIDA_BD_DANOS = SALIDAS / "BD_ BEL - IRR - MR_Proyeccion.xlsx"
SALIDA_BD_RFV = SALIDAS / "BD_ RFV_Proyeccion.xlsx"
SALIDA_DIAGNOSTICO = SALIDAS / "Diagnostico_Proyeccion.xlsx"
SALIDA_GRAFICAS = SALIDAS / "Graficas_Proyeccion.pdf"
SALIDA_DASHBOARD = SALIDAS / "Dashboard_Indices_Reservas.xlsx"   # lo arma dashboard.py al final
SALIDA_DASHBOARD_HTML = SALIDAS / "Dashboard_Indices_Reservas.html"  # lo arma dashboard_html.py (un solo archivo)

PERIODO_INICIO = 202609          # primer mes proyectado
PERIODO_FIN = 202712             # ultimo mes proyectado

HOJA_PARAMETROS = "HParametros_2026"
HOJA_MONTOS = "BD_Montos_RRC_SONR"
TIPO_INDICE_BASE = "Real"        # solo estos renglones se usan como historia
ETIQUETA_PROYECCION = "Proyección"  # "Tipo de Indice" de los renglones nuevos en HParametros
                                    # (se agrega al filtro de la hoja para que se vean junto a "Real")

INDICES = ["Ind Sin RRC", "Ind sin RRC 99.5%", "Ind Sin SONR Media", "Ind Sin SONR 99.5%"]
LAGS = [f"LAG {i}" for i in range(1, 11)]
PARES_MEDIA_995 = [("Ind Sin RRC", "Ind sin RRC 99.5%"), ("Ind Sin SONR Media", "Ind Sin SONR 99.5%")]

# Tipo de cambio que se escribe en la columna TC: supuesto de Inversiones (tipo_cambio.py, tomado de
# TC_Real_Esti.xlsx hoja TC: FCST para 2026 y FCST 2027 para 2027). Se aplica a los renglones nuevos y,
# si ACTUALIZAR_TC_EXISTENTES, tambien a los renglones que ya existen de esos meses (p.ej. 202606-202612,
# que en la BD traian una interpolacion). Meses sin dato toman el ultimo TC de la BD.
# Danos se modela en USD, asi que el TC no cambia sus cifras proyectadas; Fianzas se modela en MXN (MODELAR_EN_MXN)
# y el TC de cada mes proyectado si mueve sus cifras en USD.
TC_PROYECCION: dict[int, float] = dict(TC_FCST)
ACTUALIZAR_TC_EXISTENTES = True

RESALTAR_PROYECCION = False      # True = relleno azul claro en celdas proyectadas
SOBRESCRIBIR_PERIODOS_CON_DATOS = False  # False = se detiene si algun mes a proyectar ya trae cifras
COLOR_RESALTADO = "DDEBF7"
GENERAR_GRAFICAS = True
GENERAR_DASHBOARD = True         # dashboards de indices y reservas (real vs proyeccion): Excel y HTML
N_PROCESOS = None                # None = automatico (nucleos-1); 1 = sin paralelismo

# Modelo de proyeccion por tipo de serie
#   "Tendencia historica": linea de tendencia (regresion lineal, en logaritmos cuando la serie es positiva) sobre
#       los ultimos MESES_TENDENCIA meses, que se continua desde el ultimo dato real. Es la misma linea de
#       tendencia de Excel; la proyeccion sale paralela a ella y arranca del ultimo real.
#   "SES": nivel suavizado sin tendencia (razones: %GTO, %MR y %cedido dependen de los contratos).
#   Tambien estan disponibles "Holt amortiguado" y "Holt-Winters amortiguado (mensual)" (suavizamiento
#   exponencial). RCONT usa MODELO_TRIMESTRAL si tiene al menos MIN_OBS_TRIMESTRAL meses; con menos, SES.
MODELO_POR_TIPO = {
    "nivel": "Tendencia historica",   # montos (BEL, BRUTO), en logaritmos: crecimiento % mensual constante
    "indice": "Tendencia historica",  # indices de HParametros, en logaritmos
    "lag": "Tendencia historica",     # patron de desarrollo (LAG 1-10); en logaritmos si es positivo
    "razon": "SES",
}
MESES_TENDENCIA = 36             # ventana de la tendencia historica (None = toda la historia). Con toda la historia
                                 # entran arranques desde cero y cambios de regimen (ramo 80 SONR, Hidro) que
                                 # disparan la pendiente; 36 meses = la tendencia de los ultimos tres anos.
AMORTIGUACION_TENDENCIA = 1.0    # 1.0 = la tendencia continua constante (sin amortiguar). Con 0.95, cada mes conserva
                                 # 95% (a 16 meses, 44%); con 0.98, 72%.
MIN_OBS_TENDENCIA = 6            # observaciones minimas para estimar la tendencia; con menos se usa SES
# Estacionalidad mensual (los picos que se repiten cada ano): patron por mes del ano alrededor de la tendencia,
# estimado por descomposicion clasica (la serie menos su media movil centrada de 12 meses, promediada por mes del
# ano). Se suma a la recta de tendencia en las series de TIPOS_CON_ESTACIONALIDAD (montos e indices); los LAGs, que
# tambien van con "Tendencia historica", llevan solo la recta.
ESTACIONALIDAD_MENSUAL = True    # False = solo la recta de tendencia
MESES_ESTACIONALIDAD = 36        # historia para estimar el patron: la misma ventana que la tendencia. Con toda la
                                 # historia los picos de anos distintos caen en meses distintos, el promedio sale mas
                                 # plano y el backtest empeora; con 36 meses mejora (indices 18.9 % contra 20.2 % de la
                                 # recta sola, medido antes de desvanecer la desviacion, ponderar la pendiente y corregir
                                 # el ancla y los huecos con salto de nivel de los indices). None = toda la historia.
MIN_OBS_ESTACIONALIDAD = 36      # tres anos: quedan 24 meses sin tendencia, dos por cada mes del ano (minimo exigido)
CREDIBILIDAD_ESTACIONAL = "buhlmann"  # cuanto del patron observado se aplica (1 = se repite igual todos los anos;
                                 #   0 = puro ruido, no se aplica):
                                 #   "buhlmann": credibilidad de Buhlmann Z = n/(n+K), K = varianza dentro del mes /
                                 #       varianza entre meses (la estandar actuarial; backtest de indices 18.9 % / 14.1 %
                                 #       a 1-16 / 1-6 meses; las cifras de las tres opciones son de antes de
                                 #       desvanecer la desviacion y ponderar la pendiente de los indices; hoy
                                 #       "buhlmann" da 13.6 % a 1-16 meses).
                                 #   "ajustada": R2 ajustado del mes del ano sobre la serie sin tendencia (mas
                                 #       conservadora, picos mas bajos; 18.7 % / 14.4 %).
                                 #   "completa": 100 % del patron cuando la prueba F lo detecta (p < P_ESTACIONALIDAD)
                                 #       y nada en caso contrario (20.0 % / 15.3 %; deja sin patron a la mitad).
P_ESTACIONALIDAD = 0.10          # umbral de la prueba F para la opcion "completa"
TIPOS_CON_ESTACIONALIDAD = ("nivel", "indice")   # montos e indices. Los LAGs (patron de desarrollo) no tienen mes del
                                 # ano: en backtest no cambiaba nada y solo agregaba dientes menores a 3 %.
DESCRIPCION_CREDIBILIDAD = {
    "buhlmann": "credibilidad de Buhlmann Z = n/(n+K), K = varianza dentro del mes / varianza entre meses",
    "ajustada": "R2 ajustado del mes del ano sobre la serie sin tendencia",
    "completa": f"100 % del patron si la prueba F lo detecta (p < {P_ESTACIONALIDAD}) y 0 si no",
}
# Que pasa con la desviacion del ultimo mes respecto al modelo (recta + patron):
#   montos y LAGs: se conserva (phi = 1): la proyeccion arranca del ultimo real y sigue paralela al modelo. Son
#       niveles que se acumulan; en backtest anclar gana con claridad (montos 25.7 % contra 29.4 % si se desvanece).
#   indices: son razones que se mueven en una banda y rebotan (tocan el minimo y vuelven al maximo), asi que la
#       desviacion se desvanece con persistencia phi hacia el nivel promedio del ultimo ano (phi = 0.8: cada mes
#       conserva 80 %, a los 3 meses la mitad). En backtest mejora a los indices (18.3 % contra 18.9 % a 1-16 meses,
#       8.5 % contra 9.5 % en la prueba anidada, medido con la pendiente completa) y evita que un mes bajo arrastre
#       todo el horizonte.
PERSISTENCIA_DESVIACION = {"nivel": 1.0, "indice": 0.8, "lag": 1.0}
MESES_NIVEL_LOCAL = 12           # meses del nivel promedio (respecto a la recta) al que converge la desviacion
MEDIA_ARITMETICA_INDICES = False # los indices se modelan en logaritmos: el nivel al que convergen es el promedio
                                 # geometrico del ultimo ano, que queda por debajo del promedio aritmetico (el que se ve en
                                 # la historia) tanto mas cuanto mas volatil es la serie (mediana 0.3 %, hasta 6 % en los
                                 # 99.5 % de los ramos 31 y 35). True = se converge al promedio aritmetico (estimador de
                                 # "smearing" de Duan: log del promedio de exp(residuo) de los ultimos 12 meses).
ANCLAR_SERIES = set()            # series (Serie, Ramo) de indices que se dejan ancladas al ultimo real (phi = 1) a
                                 # criterio del area, p. ej. {("Ind sin RRC 99.5%", "31")} si la caida reciente es un
                                 # cambio de nivel y no una desviacion que rebota
# Cuanto de la pendiente de la recta se proyecta:
#   montos y LAGs: completa (1.0): la tendencia de los ultimos tres anos se continua tal cual (decision del area).
#   indices: ponderada por su credibilidad = R2 ajustado de la recta ("r2"). Son razones: extrapolar 16 meses una
#       pendiente que la recta explica poco (ramo 31: +1.3 % mensual con R2 0.16) proyecta subidas o bajadas que la
#       serie nunca sostuvo. Backtest de indices (error % mediano a 1-16 / 1-6 meses): pendiente completa 16.5 / 12.6;
#       ponderada por R2 13.6 / 12.5; sin pendiente 13.4 / 11.6. Un numero entre 0 y 1 fija la proporcion.
CREDIBILIDAD_PENDIENTE = {"nivel": 1.0, "indice": "r2", "lag": 1.0}
# Cotas de los modelos de suavizamiento exponencial (si se eligen), estimadas por maxima verosimilitud dentro de
# ellas: alpha ~ 1 (arranca del ultimo dato real), beta <= 0.15 (tendencia de los ultimos anos, no del ultimo mes),
# phi entre 0.80 y 0.98. RCONT (Holt-Winters trimestral) suaviza el nivel (alpha >= 0.2) para separar la
# estacionalidad. SES estima alpha libre.
# Modelo de las series con estacionalidad trimestral (RCONT: acumula en los meses 1-2 del trimestre y libera en el 3):
#   "Holt-Winters (trimestral)": nivel suavizado + patron por mes del trimestre, sin tendencia.
#   "Holt-Winters amortiguado (trimestral)": ademas tendencia amortiguada. Con la RCONT de ene-25 a ago-26 esa
#       tendencia extrapolaba la baja en pesos de 2025 (el nivel ya es estable en 2026); en backtest con 8 cortes
#       (12 a 19 meses de entrenamiento, 1 a 8 meses adelante) el error en pesos fue 6.5 % contra 3.3 % sin tendencia
#       (sin tendencia gana en 7 de los 8 cortes; pierde solo en el primero, el unico del backtest estandar).
MODELO_TRIMESTRAL = "Holt-Winters (trimestral)"
COTAS_SUAVIZAMIENTO = {"smoothing_level": (0.90, 0.99), "smoothing_trend": (0.02, 0.15), "damping_trend": (0.80, 0.98)}
COTAS_ESTACIONAL = {**COTAS_SUAVIZAMIENTO, "smoothing_level": (0.20, 0.99)}
MIN_OBS_HOLT = 12                # con menos observaciones los modelos Holt caen a SES
MIN_OBS_HW_MENSUAL = 24          # Holt-Winters mensual necesita dos anos completos; con menos cae a SES
MIN_OBS_SES = 4                  # con menos observaciones se mantiene el ultimo valor
MIN_OBS_TRIMESTRAL = 12          # observaciones minimas para estimar la estacionalidad trimestral
CORTES_BACKTEST = (16, 12, 8)    # meses antes del final desde los que se re-proyecta para medir el error
MIN_ENTRENAMIENTO = 12           # observaciones minimas para un corte del backtest (Fianzas, con 20 meses, solo
                                 # alcanza el corte a 8 meses: su backtest es indicativo)
MAX_HUECO_INTERPOLABLE = 6       # huecos mas largos cortan la historia
SALTO_NIVEL_HUECO = 2.5          # un hueco (de cualquier largo) que separa dos niveles cuya razon supera 2.5 veces
                                 # tambien corta la historia: interpolar a traves de un cambio de nivel inventaria una
                                 # pendiente (Hidro: 6.4 antes del hueco de jul-dic 23 y 0.13 despues)
UMBRAL_CERO_MONTOS = 1.0         # |monto| < 1 USD se considera 0
MESES_CERO_EXTINTA = 6           # ultimos N meses en cero -> serie extinta
UMBRAL_ESCALON = 0.5             # >= 50% de meses sin cambio -> parametro en escalon
MESES_SIN_DATO_MAX = 12          # sin dato en los ultimos N meses -> no se proyecta
NIVEL_INTERVALO = 0.80

# Estructura de conceptos (drivers y derivados)
ESTRUCTURA = {
    "DANOS": {
        "RRC": {"nivel": "BEL", "razones_bel": ["GTO", "MR"], "cesion": "IRR"},
        "SONR": {"nivel": "BEL", "razones_bel": ["MR"], "cesion": "IRR"},
    },
    "FIANZAS": {
        "RFV": {"nivel": "BRUTO", "razones_bel": [], "cesion": "IRR", "totales_con_mezcla": ["RCONT"]},
    },
}
MESES_MEZCLA = 8                 # meses recientes para repartir por ramo los totales (RCONT)
# Moneda en que se modelan los montos. True = modelar en MXN (historia USD x TC real) y convertir a USD con el TC de
# cada mes proyectado (el supuesto de Inversiones, TC_FCST).
#   Danos: USD. En backtest, modelar en MXN fue menos preciso (WAPE 30.8 % contra 27.0 %, 23 series).
#   Fianzas: MXN. La RFV es una reserva en pesos: de ene-25 a ago-26 la RFV NETO crecio 27 % en pesos pero 55 % en
#       dolares, porque el peso paso de 20.7 a 17.0. Modelar en USD extrapolaba esa apreciacion (dic-27: 134 M USD)
#       cuando Inversiones pronostica 18.5 a dic-27; en MXN con ese TC da 105 M USD. El unico corte de backtest de
#       Fianzas (8 meses de 2026, con el peso aun apreciandose) favorecia USD en el RFV BRUTO (5.3 % contra 7.6 %)
#       justamente por eso.
MODELAR_EN_MXN = {"DANOS": False, "FIANZAS": True}
# Monedas mezcladas en la historia: si un tramo de la BD viene en MXN y otro en USD, el salto entre dos meses seguidos
# es del tamano del TC (p. ej. RFV BRUTO 1,754 M en dic-25 y 104 M en ene-26) y la tendencia lo lee como una caida de
# 94 %. True = se detecta por reserva (RFV, RCONT, RRC, SONR; recorriendo la historia hacia atras desde el ultimo mes,
# que se toma como USD; una reserva que ya viene en USD en esos meses, como la RCONT de 2025, no trae el salto y se
# deja como viene), los meses en
# MXN se convierten a USD con el TC de cada mes de la propia BD, en memoria y en la BD de salida (sin comentarios;
# el detalle queda en la hoja Moneda_corregida), y se avisa en consola y en Alertas. El archivo de entrada no se
# modifica.
CORREGIR_MONEDA_MEZCLADA = True
TOLERANCIA_SALTO_TC = 0.25       # un salto entre dos meses se atribuye al TC si difiere de el en menos de 25 %
# Rango esperado por el area para el total de un concepto en USD (suma de ramos), por libro. Si la proyeccion del
# modelo sale del rango, se reduce en la misma proporcion el crecimiento proyectado de todos los ramos (desde su ultimo
# real) hasta que el total quede dentro en todos los meses; si el ultimo real ya estaba fuera, se lleva al limite mas
# cercano. BRUTO, IRR y NETO de cada ramo se escalan juntos, asi que las identidades se conservan. Es un ajuste de
# criterio experto: la cifra del modelo sin ajuste queda en Alertas. None en un limite = sin limite de ese lado.
# {} = sin rangos.
RANGO_ESPERADO = {("FIANZAS", "RFV NETO"): (80e6, None)}    # RFV NETO total: minimo 80 M USD, sin tope (ago-26 real: 90.6)
# Contraste con el presupuesto (opcional). Si en entradas/ esta el dashboard HTML del presupuesto tecnico ("Validacion
# FCST", con primas, siniestros y comisiones por linea de negocio: real del ano anterior, reestimado del ano en curso y
# presupuesto del siguiente), el diagnostico compara el crecimiento de cada reserva con el de su referencia: RRC con
# las primas tomadas, SONR con los siniestros tomados (Danos = total menos las lineas de Fianzas y menos las lineas
# nuevas: sin primas en el ano en curso pero con presupuesto del siguiente) y RFV con las primas de las lineas de
# Fianzas. No cambia la proyeccion: sirve para ver si las reservas crecen en proporcion al negocio.
PATRON_PRESUPUESTO = "Dashboard_FCST*.html"
LINEAS_FIANZAS_PPTO = ("4003",)  # lineas de negocio del presupuesto donde estan las afianzadoras (aproximacion: la 4003
                                 # mezcla fianzas de Mexico con caucion y credito de otros paises)
TOLERANCIA_PRESUPUESTO = 0.10    # alerta si el crecimiento de la reserva difiere del de su referencia en mas de 10 pts
# Factor de prima (primas.py lee la prima real, el reforecast y el presupuesto de entradas/). Las reservas que dependen
# de la prima (RRC BEL y SONR BEL de Danos por ramo, RFV BRUTO de Fianzas) se escriben como
#     reserva = factor mensual x exposicion de prima del grupo de ramo
# y el crecimiento lo pone la prima del plan (reforecast del resto del ano y presupuesto del siguiente). El factor
# (reserva / exposicion) se proyecta como la recta de 36 meses con su patron del mes (Buhlmann), de fabrica sin
# pendiente y anclado a su ultimo valor real. Exposicion por reserva (DRIVERS_FACTOR; el primero es el de fabrica):
#   RRC: PND12 = prima no devengada en 24avos (el riesgo en curso de la prima suscrita en los ultimos 12 meses).
#   SONR: PDP = prima devengada de cada uno de los ultimos ANIOS_LAG_SONR anos x la parte pendiente de reportar
#         (1 - LAG del ano en HParametros), como el metodo propio de SONR. Alternativas: P24 y P36 (promedios anuales).
#   RFV: P12 = prima de los ultimos 12 meses de Fianzas, en pesos (la RFV se modela en MXN).
# El "factor de error" es el error de ln(factor) como AR(1): su persistencia rho se estima y se reporta siempre, y
# compite en la rejilla con la de fabrica (1 = anclado). Por tipo de reserva el backtest decide entre A (la recta de
# siempre), B (factor de prima) y C (combinacion 50/50 en logaritmos): B si su error no pasa de 1.10 x el de la recta +
# 0.5 pts con la prima real Y, en un corte propio en diciembre del ano anterior, con el presupuesto del ano en curso
# (sus meses tal cual); si no, C con las mismas condiciones; si no, A. La regla favorece al factor cuando la historia no
# distingue: estas reservas dependen de la prima por construccion.
USAR_FACTOR_PRIMA = True
MODELO_MONTOS = "auto"           # "auto" (decide el backtest) | "primas" | "combinacion" | "tendencia": fuerza la
                                 # decision en todas las series elegibles (las no elegibles siguen con la recta)
MODELO_MONTOS_SERIE = {}         # {("DANOS", "RRC", "60"): "tendencia" | "primas" | "combinacion"}: fuerza una serie
                                 # elegible
DRIVERS_FACTOR = {("DANOS", "RRC"): ("PND12", "P12"), ("DANOS", "SONR"): ("PDP", "P24", "P36"),
                  ("FIANZAS", "RFV"): ("P12", "P24")}
PENDIENTES_FACTOR = (0.0,)       # pendiente del factor: 0 = sin pendiente (el crecimiento lo pone la prima). Se puede
                                 # agregar "r2" (ponderada por su R2 ajustado), pero deja que el factor copie la recta
PERSISTENCIAS_FACTOR = (1.0, "estimada")   # desviacion del factor: se conserva (1) o se desvanece con su rho
PRIOR_PERSISTENCIA_FACTOR = 0.8  # rho cuando hay menos de MIN_MESES_AR1 meses de factor
MIN_MESES_AR1 = 24
MARGEN_PREFERENCIA_FACTOR = 1.0  # otra configuracion reemplaza a la de fabrica si baja el error agrupado 1 pt o mas
TOLERANCIA_FACTOR = (1.10, 0.5)  # el factor "no pierde" si su error <= 1.10 x error de la recta + 0.5 pts
MIN_MESES_FACTOR = {"DANOS": 24, "FIANZAS": 12}   # meses minimos de factor para ajustarlo (y en cada corte)
ANIOS_LAG_SONR = 3               # anos de suscripcion en la exposicion de SONR (PDP)
MAPA_RAMO_LAG = {"10": "10", "30": "31", "34": "35", "37": "39", "40": "40", "50": "50", "60": "60", "71": "TEV",
                 "73": "Hidro", "80": "80", "90": "90", "100": "100", "110": "110"}   # ramo de reserva -> HParametros
PENDIENTE_DEFECTO = (0.9, 0.5, 0.2)   # parte pendiente por ano si el ramo no trae LAG en HParametros
UMBRAL_PRIMA_FACTOR = 5e6        # prima de 12 meses minima del grupo (USD) para usar el factor
UMBRAL_RESERVA_FACTOR = 1e6      # reserva minima (USD) para usar el factor
RANGO_FACTOR = (0.01, 10.0)      # factor (reserva / exposicion) sano al ultimo mes
MAX_MESES_PRIMA_ESTIMADA = 2     # meses maximos entre el ultimo real de primas y el de reservas
SENSIBILIDAD_PRIMA = (0.9, 1.1)  # escenarios de prima del ano siguiente para la sensibilidad
ESTACIONALIDAD_TRIMESTRAL = ("RCONT",)   # acumula en meses 1-2 del trimestre y libera en el 3
DOMINIO_CESION = (0.0, 1.0)      # IRR/BRUTO entre 0 y 100%
DOMINIO_RAZON_BEL = (0.0, None)  # GTO/BEL y MR/BEL no negativos
DOMINIO_LAG = (0.0, None)        # patron de desarrollo acumulado (en ramos como el 31 supera 1: no se acota arriba)

warnings.filterwarnings("ignore")


# =============================================================================
# UTILERIAS
# =============================================================================
def periodo_a_indice(p: int) -> int:
    return (p // 100) * 12 + (p % 100 - 1)


def indice_a_periodo(i: int) -> int:
    return (i // 12) * 100 + (i % 12) + 1


def rango_periodos(p_ini: int, p_fin: int) -> list[int]:
    return [indice_a_periodo(i) for i in range(periodo_a_indice(p_ini), periodo_a_indice(p_fin) + 1)]


def a_numero(v):
    """Convierte a float: numeros, textos con espacios (incluye \\xa0) o comas decimales.
    Devuelve (valor|nan, fue_texto)."""
    if v is None:
        return math.nan, False
    if isinstance(v, bool):
        return math.nan, False
    if isinstance(v, (int, float)):
        return float(v), False
    if isinstance(v, str):
        t = v.replace("\xa0", " ").strip().replace(",", "")
        if t == "":
            return math.nan, True
        try:
            return float(t), True
        except ValueError:
            return math.nan, True
    return math.nan, False


def norm(t) -> str:
    return re.sub(r"\s+", " ", str(t or "").replace("\xa0", " ")).strip().upper()


# =============================================================================
# MODELOS
# =============================================================================
#   Tendencia historica = linea de tendencia (regresion) sobre la ventana, continuada desde el ultimo real.
#   Los demas son casos de suavizamiento exponencial (familia Holt-Winters): SES = solo nivel; Holt amortiguado =
#   nivel + tendencia amortiguada; Holt-Winters = estacionalidad sobre el nivel (con o sin tendencia amortiguada;
#   la RCONT usa MODELO_TRIMESTRAL, sin tendencia).
TENDENCIA = "Tendencia historica"
MODELOS = {
    "SES": dict(),
    "Holt amortiguado": dict(trend="add", damped_trend=True),
    "Holt-Winters amortiguado (mensual)": dict(trend="add", damped_trend=True, seasonal="add", seasonal_periods=12),
    "Holt-Winters amortiguado (trimestral)": dict(trend="add", damped_trend=True, seasonal="add",
                                                  seasonal_periods=3),
    "Holt-Winters (trimestral)": dict(seasonal="add", seasonal_periods=3),
}
ULTIMO_VALOR = "Ultimo valor"


@dataclass
class Serie:
    clave: tuple                 # (libro, grupo, concepto, ramo)
    tipo: str                    # nivel | razon | indice | lag
    periodos: list[int]          # historia mensual continua
    valores: list[float]         # nan = sin dato
    ultimo_periodo: int          # ultimo mes real global (la proyeccion arranca al mes siguiente)
    h: int                       # meses a proyectar
    trimestral: bool = False     # estacionalidad por mes del trimestre (p.ej. RCONT)
    dominio: tuple = (None, None)  # cotas actuariales (min, max) de la serie proyectada
    moneda: str = ""             # moneda en que se modela (montos)


@dataclass
class Resultado:
    clave: tuple
    tipo: str
    pronostico: list[float]
    li: list[float]
    ls: list[float]
    regla: str                                       # regla de datos que resolvio la serie (si aplica)
    modelo: str = ""                                 # modelo usado
    transformacion: str = ""
    n_obs: int = 0
    parametros: dict = field(default_factory=dict)   # alpha, beta, phi, gamma estimados
    tendencia_mensual: float = math.nan              # pendiente al final de la historia (log: % mensual)
    n_cortes: int = 0                                # cortes del backtest
    error_modelo: float = math.nan                   # error % (WAPE) del modelo en el backtest
    error_ultimo_valor: float = math.nan             # idem, repitiendo el ultimo valor
    error_ses: float = math.nan                      # idem, SES
    alertas: list = field(default_factory=list)
    moneda: str = ""
    historia_periodos: list = field(default_factory=list)
    historia_valores: list = field(default_factory=list)
    factor: dict = field(default_factory=dict)       # factor de prima (si aplica): decision, driver, recta alternativa


def ajustar_ets(z, modelo: str, h: int):
    """Ajusta el modelo a z (en la escala del modelo) y devuelve pronostico, intervalo y parametros."""
    kw = MODELOS[modelo]
    if kw.get("trend"):
        cotas = dict(COTAS_ESTACIONAL if kw.get("seasonal") else COTAS_SUAVIZAMIENTO)
    elif kw.get("seasonal"):
        cotas = {"smoothing_level": COTAS_ESTACIONAL["smoothing_level"]}   # Holt-Winters sin tendencia
    else:
        cotas = None                                    # SES: alpha libre
    m = ETSModel(pd.Series(np.asarray(z, dtype=float)), error="add", bounds=cotas, **kw).fit(disp=False, maxiter=500)
    pred = m.get_prediction(start=len(z), end=len(z) + h - 1).summary_frame(alpha=1 - NIVEL_INTERVALO)
    nombres = {"smoothing_level": "alpha", "smoothing_trend": "beta", "damping_trend": "phi",
               "smoothing_seasonal": "gamma"}
    params = {nombres[k]: float(v) for k, v in zip(m.param_names, np.asarray(m.params, dtype=float))
              if k in nombres}
    pendiente = float(m.states["trend"].iloc[-1]) if kw.get("trend") else 0.0
    return pred["mean"].to_numpy(), pred["pi_lower"].to_numpy(), pred["pi_upper"].to_numpy(), params, pendiente


def factores_estacionales(z, meses):
    """Patron por mes del ano alrededor de la tendencia (descomposicion clasica): a z se le resta su media movil
    centrada de 12 meses (2x12) y lo que queda se promedia por mes del ano. Devuelve None si no hay historia
    suficiente; si no, un dict con "factores" (12 valores centrados en cero, ya ponderados por la credibilidad, en
    la escala del modelo), "credibilidad", "p" (prueba F del mes del ano), "r2", "obs" y "amplitud"."""
    z = np.asarray(z, dtype=float)
    meses = np.asarray(meses, dtype=int)
    if MESES_ESTACIONALIDAD is not None and len(z) > MESES_ESTACIONALIDAD:
        z, meses = z[-MESES_ESTACIONALIDAD:], meses[-MESES_ESTACIONALIDAD:]
    n = len(z)
    if n < MIN_OBS_ESTACIONALIDAD:
        return None
    pesos = np.r_[0.5, np.ones(11), 0.5] / 12.0                    # media movil 2x12, centrada exactamente en t
    det = z[6:n - 6] - np.convolve(z, pesos, mode="valid")          # serie sin tendencia (t = 6 .. n-7)
    mm = meses[6:n - 6]
    grupos = [det[mm == m] for m in range(1, 13)]
    if min(len(g) for g in grupos) < 2:          # con una sola observacion por mes el "patron" seria la propia serie
        return None
    s = np.array([g.mean() if len(g) else 0.0 for g in grupos])
    s -= s.mean()
    n_det, k = len(det), sum(1 for g in grupos if len(g))
    var_det = float(np.var(det))
    r2 = max(0.0, 1 - float(np.var(det - s[mm - 1])) / var_det) if var_det > 0 else 0.0
    r2_ajustado = max(0.0, 1 - (1 - r2) * (n_det - 1) / max(1, n_det - k))   # 0 cuando el mes no explica nada
    try:
        p = float(_f_oneway(*[g for g in grupos if len(g) >= 2]).pvalue)
    except Exception:  # noqa: BLE001
        p = math.nan
    if CREDIBILIDAD_ESTACIONAL == "completa":
        credibilidad = 1.0 if p < P_ESTACIONALIDAD else 0.0
    elif CREDIBILIDAD_ESTACIONAL == "buhlmann":
        # componentes de varianza (ANOVA de un factor): sigma2 dentro del mes, tau2 entre meses; Z = n/(n+K)
        n_m = np.array([len(g) for g in grupos], dtype=float)
        gl = float(np.sum(np.maximum(n_m - 1, 0)))
        sigma2 = sum(float(np.sum((g - g.mean()) ** 2)) for g in grupos if len(g) > 1) / gl if gl > 0 else 0.0
        medias = np.array([g.mean() if len(g) else det.mean() for g in grupos])
        denom = n_det - float(np.sum(n_m ** 2)) / n_det
        tau2 = max(0.0, (float(np.sum(n_m * (medias - det.mean()) ** 2)) - (k - 1) * sigma2) / denom) if denom > 0 else 0.0
        z_mes = n_m / (n_m + sigma2 / tau2) if tau2 > 0 else np.zeros(12)
        s = s * z_mes
        s -= s.mean()
        credibilidad = float(np.mean(z_mes[n_m > 0])) if k else 0.0
    else:
        credibilidad = r2_ajustado
    if CREDIBILIDAD_ESTACIONAL != "buhlmann":
        s = s * credibilidad
    return {"factores": s, "credibilidad": float(credibilidad), "p": p, "r2": float(r2), "obs": int(n_det),
            "amplitud": float(s.max() - s.min())}


def ajustar_tendencia(z, h: int, meses=None, phi_desv: float = 1.0, cred_pend=1.0, media_aritmetica: bool = False):
    """Linea de tendencia (regresion lineal sobre los ultimos MESES_TENDENCIA valores de z, en la escala del modelo)
    mas, si ESTACIONALIDAD_MENSUAL y se conocen los meses, el patron por mes del ano; continuada desde el ultimo
    dato real con amortiguacion AMORTIGUACION_TENDENCIA. La desviacion del ultimo mes respecto al modelo se
    conserva (phi_desv = 1) o se desvanece con persistencia phi_desv hacia el nivel promedio de los ultimos
    MESES_NIVEL_LOCAL meses (indices). Intervalo: con phi_desv = 1, la variabilidad mensual alrededor de la
    tendencia (sin el patron), que crece con la raiz del horizonte; con phi_desv < 1, la banda estacionaria de los
    residuos mas la incertidumbre de la pendiente. cred_pend: proporcion de la pendiente que se proyecta (1 = toda;
    "r2" = el R2 ajustado de la recta, para indices)."""
    z = np.asarray(z, dtype=float)
    est = factores_estacionales(z, meses) if (ESTACIONALIDAD_MENSUAL and meses is not None) else None
    if est is not None:
        meses = np.asarray(meses, dtype=int)
        s = est["factores"]
        d = z - s[meses - 1]                                          # serie sin el patron estacional
        m_fut = (meses[-1] - 1 + np.arange(1, h + 1)) % 12            # mes del ano (0-11) de cada mes proyectado
        estacional_fut = s[m_fut]
    else:
        d, estacional_fut = z, 0.0
    w = d if MESES_TENDENCIA is None or len(d) <= MESES_TENDENCIA else d[-MESES_TENDENCIA:]
    t = np.arange(len(w), dtype=float)
    pendiente, ordenada = np.polyfit(t, w, 1)
    ajuste = ordenada + pendiente * t
    ss_res, ss_tot = float(np.sum((w - ajuste) ** 2)), float(np.sum((w - w.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else math.nan
    phi = AMORTIGUACION_TENDENCIA
    pasos = np.cumsum(phi ** np.arange(1, h + 1))
    hh = np.arange(1, h + 1)
    r2_ajustado = max(0.0, 1 - (1 - r2) * (len(w) - 1) / max(1, len(w) - 2)) if np.isfinite(r2) else 0.0
    credibilidad_pend = r2_ajustado if cred_pend == "r2" else float(cred_pend)
    pendiente_aplicada = float(pendiente) * credibilidad_pend           # pendiente que se proyecta
    ajuste_ultimo = float(ordenada + pendiente * (len(w) - 1))         # recta (sin estacionalidad) en el ultimo mes
    e = w - ajuste                                                     # residuos alrededor de la recta
    e_ultimo = float(d[-1] - ajuste_ultimo)                            # desviacion del ultimo mes (= e[-1])
    phi_d = float(phi_desv)
    if phi_d < 1:
        # la desviacion converge al nivel promedio del ultimo ano: desv_h = objetivo + phi^h (e_ultimo - objetivo)
        e_local = e[-MESES_NIVEL_LOCAL:]
        # nivel del ultimo ano respecto a la recta: promedio de los residuos (geometrico) o, en logaritmos, log del
        # promedio de exp(residuo) (aritmetico, sin el sesgo de retransformar desde logaritmos)
        objetivo = float(np.log(np.mean(np.exp(e_local)))) if media_aritmetica else float(np.mean(e_local))
        # los residuos se miden contra la recta de pendiente completa: el nivel al que se converge seria el promedio del
        # ultimo ano mas (n-1)/2 meses de pendiente completa. Se le quita la parte de la pendiente sin credibilidad para
        # que el nivel y la extrapolacion usen la misma pendiente (en backtest de indices: error 16.3 % -> 15.2 %)
        objetivo -= (1 - credibilidad_pend) * float(pendiente) * (len(e_local) - 1) / 2
        desviacion = objetivo + phi_d ** hh * (e_ultimo - objetivo)
        sd_e = float(np.std(e, ddof=1)) if len(e) > 2 else 0.0        # banda estacionaria de los residuos
        se_pend = (math.sqrt(ss_res / (len(w) - 2) / float(np.sum((t - t.mean()) ** 2)))
                   if len(w) > 2 and np.sum((t - t.mean()) ** 2) > 0 else 0.0)
        ancho = _cuantil_normal() * np.sqrt(sd_e ** 2 * (1 - phi_d ** (2 * hh)) + (se_pend * hh) ** 2)
    else:
        objetivo = e_ultimo
        desviacion = e_ultimo                                          # se conserva: arranca del ultimo real
        sd = float(np.std(np.diff(w) - pendiente, ddof=1)) if len(w) > 2 else 0.0
        ancho = _cuantil_normal() * sd * np.sqrt(hh)
    pron = ajuste_ultimo + pendiente_aplicada * pasos + desviacion + estacional_fut   # con phi_d = 1 y cred 1: d[-1] + pendiente*pasos + s
    params = {"pendiente": float(pendiente), "ventana": int(len(w)), "r2": float(r2), "ajuste_ultimo": ajuste_ultimo,
              "credibilidad_pendiente": float(credibilidad_pend), "pendiente_aplicada": pendiente_aplicada,
              "phi_desviacion": phi_d, "desviacion_ultimo": e_ultimo, "nivel_local": float(objetivo),
              "sd_residual": float(np.std(e, ddof=1)) if len(e) > 2 else 0.0}
    if est is not None:
        params.update({"estacional": [float(v) for v in est["factores"]], "credibilidad_estacional": est["credibilidad"],
                       "p_estacional": est["p"], "r2_estacional": est["r2"], "obs_estacional": est["obs"],
                       "amplitud_estacional": est["amplitud"]})
    return pron, pron - ancho, pron + ancho, params, float(pendiente)


def ajustar(z, modelo: str, h: int, meses=None, phi_desv: float = 1.0, cred_pend=1.0, media_aritmetica: bool = False):
    """Pronostico en la escala del modelo: (pronostico, li, ls, parametros, pendiente final). meses = mes del ano
    (1-12) de cada observacion, para la estacionalidad de la tendencia historica; phi_desv = persistencia de la
    desviacion del ultimo mes (1 = se conserva); cred_pend = proporcion de la pendiente que se proyecta."""
    return (ajustar_tendencia(z, h, meses, phi_desv, cred_pend, media_aritmetica) if modelo == TENDENCIA
            else ajustar_ets(z, modelo, h))


def elegir_modelo(tipo: str, n: int, trimestral: bool) -> str:
    if n < MIN_OBS_SES:
        return ULTIMO_VALOR
    if trimestral:
        # con menos de MIN_OBS_TRIMESTRAL meses no se puede separar la estacionalidad: nivel suavizado
        return MODELO_TRIMESTRAL if n >= MIN_OBS_TRIMESTRAL else "SES"
    modelo = MODELO_POR_TIPO[tipo]
    minimo = {TENDENCIA: MIN_OBS_TENDENCIA, "Holt-Winters amortiguado (mensual)": MIN_OBS_HW_MENSUAL}.get(modelo, MIN_OBS_HOLT)
    if modelo != "SES" and n < minimo:
        return "SES"
    return modelo


def preparar(serie: Serie):
    """Reglas de calidad de datos. Devuelve (res, prep): si la serie queda resuelta por una regla
    (ceros, constante, escalon, sin datos) prep es None y res trae la proyeccion; si no, prep trae
    la historia limpia {y, per, brecha}."""
    tipo, h = serie.tipo, serie.h
    per = list(serie.periodos)
    y = np.array(serie.valores, dtype=float)
    res = Resultado(clave=serie.clave, tipo=tipo, pronostico=[math.nan] * h, li=[math.nan] * h,
                    ls=[math.nan] * h, regla="")

    def _constante(valor, regla):
        res.pronostico, res.li, res.ls = [float(valor)] * h, [float(valor)] * h, [float(valor)] * h
        res.regla = regla
        return res, None

    if tipo == "nivel":
        y[np.abs(y) < UMBRAL_CERO_MONTOS] = 0.0
    validos = np.where(~np.isnan(y))[0]
    if len(validos) == 0:
        res.regla = "Sin datos (no se proyecta)"
        return res, None
    # meses sin dato al final respecto al ultimo mes real global
    brecha = periodo_a_indice(serie.ultimo_periodo) - periodo_a_indice(per[validos[-1]])
    if brecha >= MESES_SIN_DATO_MAX:
        res.regla = f"Sin datos en los ultimos {MESES_SIN_DATO_MAX} meses (no se proyecta)"
        return res, None

    # 1) ceros / vacios iniciales (antes de que exista el negocio o el dato)
    if tipo in ("nivel", "razon"):
        nz = np.where((~np.isnan(y)) & (y != 0))[0]
        if len(nz) == 0:
            return _constante(0.0, "Serie en cero (se proyecta en cero)")
        inicio = nz[0]
    else:
        inicio = validos[0]
    fin = validos[-1]
    y, per = y[inicio:fin + 1], per[inicio:fin + 1]

    # 2) huecos largos: solo se usa el tramo posterior al ultimo hueco > MAX_HUECO_INTERPOLABLE
    corte, racha = 0, 0
    for i, es_nulo in enumerate(np.isnan(y)):
        racha = racha + 1 if es_nulo else 0
        if racha > MAX_HUECO_INTERPOLABLE:
            corte = i + 1
    motivo = f"Hueco de mas de {MAX_HUECO_INTERPOLABLE} meses sin dato" if corte else ""
    # huecos que separan dos niveles muy distintos (cambio de regimen): tambien cortan
    if tipo != "razon":
        nulos = np.isnan(y)
        i = 0
        while i < len(y):
            if nulos[i]:
                j = i
                while j < len(y) and nulos[j]:
                    j += 1
                if i > 0 and j < len(y) and y[i - 1] > 0 and y[j] > 0 and j > corte:
                    razon_nivel = max(y[i - 1], y[j]) / min(y[i - 1], y[j])
                    if razon_nivel > SALTO_NIVEL_HUECO:
                        corte = j
                        motivo = (f"Cambio de nivel de {razon_nivel:.1f} veces a traves del hueco {per[i]}-{per[j - 1]} "
                                  f"({y[i - 1]:.4g} antes, {y[j]:.4g} despues)")
                i = j
            else:
                i += 1
    if corte:
        res.alertas.append(f"{motivo}: se usa solo la historia desde {per[corte]}")
        y, per = y[corte:], per[corte:]
        primero = np.where(~np.isnan(y))[0][0]
        y, per = y[primero:], per[primero:]

    # 3) parametro "en escalon" (se evalua con lo observado, sin interpolar)
    obs = y[~np.isnan(y)][-25:]
    escalon = len(obs) >= 7 and np.mean(np.abs(np.diff(obs)) < 1e-12) >= UMBRAL_ESCALON

    # 4) huecos cortos: interpolacion lineal
    n_interp = int(np.isnan(y).sum())
    if n_interp:
        idx = np.arange(len(y))
        ok = ~np.isnan(y)
        res.alertas.append(f"{n_interp} mes(es) sin dato interpolado(s) linealmente")
        y = np.interp(idx, idx[ok], y[ok])
    res.historia_periodos, res.historia_valores = per, [float(v) for v in y]
    n = len(y)
    res.n_obs = n
    if brecha > 0:
        res.alertas.append(f"Ultimo dato en {per[-1]}; se proyecta desde ahi ({brecha} mes(es) de rezago)")

    # 5) series extintas / constantes / en escalon
    if tipo == "nivel" and n >= MESES_CERO_EXTINTA and np.all(y[-MESES_CERO_EXTINTA:] == 0):
        return _constante(0.0, f"Serie en cero los ultimos {MESES_CERO_EXTINTA} meses (se proyecta en cero)")
    if n == 1 or np.all(np.abs(np.diff(y[-25:])) < 1e-12):
        return _constante(y[-1], "Serie constante (se mantiene el ultimo valor)")
    if escalon:
        return _constante(y[-1], "Parametro en escalon (se mantiene el ultimo valor)")
    return res, {"y": y, "per": per, "brecha": brecha, "n_interp": n_interp}


def pronosticar(serie: Serie) -> Resultado:
    """Proyecta una serie mensual: reglas de calidad de datos, modelo segun el tipo de serie, backtest y
    cotas actuariales."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _pronosticar(serie)


def _pronosticar(serie: Serie) -> Resultado:
    res, prep = preparar(serie)
    if prep is None:
        return _post_proceso(res, None, serie.tipo, serie.dominio)
    tipo, h = serie.tipo, serie.h
    y, per, brecha = prep["y"], prep["per"], prep["brecha"]
    n = len(y)
    hh = h + brecha                       # si el ultimo dato es anterior al ultimo mes real

    res.moneda = serie.moneda
    usar_log = tipo in ("nivel", "indice", "lag") and np.all(y > 0)   # LAGs positivos: tendencia en % (no cruzan 0)
    res.transformacion = "log" if usar_log else "ninguna"
    z = np.log(y) if usar_log else y.copy()
    meses = (np.array([p % 100 for p in per], dtype=int)              # mes del ano de cada observacion
             if tipo in TIPOS_CON_ESTACIONALIDAD else None)          # (solo montos e indices llevan patron)
    phi_desv = float(PERSISTENCIA_DESVIACION.get(tipo, 1.0))          # indices: la desviacion se desvanece
    if (serie.clave[2], str(serie.clave[3])) in ANCLAR_SERIES:
        phi_desv = 1.0
        res.alertas.append("Serie anclada al ultimo real por decision del area (ANCLAR_SERIES)")
    cred_pend = CREDIBILIDAD_PENDIENTE.get(tipo, 1.0)                  # indices: pendiente ponderada por su R2
    media_arit = bool(MEDIA_ARITMETICA_INDICES and usar_log and phi_desv < 1)   # converger al promedio aritmetico

    def inv(v):
        return np.exp(v) if usar_log else v

    # alerta de atipico en el ultimo mes (salto > 3 desviaciones de los cambios mensuales)
    if tipo in ("nivel", "indice") and n >= 13:
        d = np.diff(z)
        sd_d = np.std(d[:-1], ddof=1)
        if sd_d > 0 and abs(d[-1] - np.mean(d[:-1])) > 3 * sd_d:
            res.alertas.append(f"Salto atipico en el ultimo mes ({(y[-1] / y[-2] - 1):+.1%}); revisar si es un "
                               "evento puntual que se liberara")

    modelo = elegir_modelo(tipo, n, serie.trimestral)
    if n < MIN_OBS_HOLT:
        res.alertas.append(f"Solo {n} observaciones: proyeccion de baja confiabilidad")
    if serie.trimestral and modelo == "SES":
        res.alertas.append(f"Serie trimestral con {n} meses (< {MIN_OBS_TRIMESTRAL}): no se estima estacionalidad ni "
                           "tendencia; se proyecta el nivel suavizado (completa la historia para usar Holt-Winters)")
    pron = li = ls = None
    while modelo != ULTIMO_VALOR:
        try:
            f, lo, hi, params, pendiente = ajustar(z, modelo, hh, meses, phi_desv, cred_pend, media_arit)
            if np.all(np.isfinite(f)):
                pron, li, ls = inv(f), inv(lo), inv(hi)
                res.parametros = params
                res.tendencia_mensual = (math.exp(pendiente) - 1) if usar_log else pendiente
                break
            res.alertas.append(f"No se pudo ajustar {modelo} (pronostico no finito)")
        except Exception as e:  # noqa: BLE001
            res.alertas.append(f"No se pudo ajustar {modelo} ({type(e).__name__})")
        modelo = "SES" if modelo != "SES" else ULTIMO_VALOR     # respaldo: SES, y si tampoco, ultimo valor
        res.alertas.append(f"Se usa {modelo}")
    if pron is None:
        pron = np.repeat(y[-1], hh)
        sd = (np.std(np.diff(z), ddof=1) if n > 2 else 0.0) * np.sqrt(np.arange(1, hh + 1)) * _cuantil_normal()
        li, ls = inv(z[-1] - sd), inv(z[-1] + sd)
    res.modelo = modelo
    if modelo == TENDENCIA and res.parametros:
        r2 = res.parametros.get("r2", math.nan)
        if np.isfinite(r2) and r2 < 0.3:
            res.alertas.append(f"R2 de la tendencia {r2:.2f}: la recta explica poco de los ultimos "
                               f"{res.parametros['ventana']} meses; revisar antes de usar la pendiente")
        pe = res.parametros
        if pe.get("phi_desviacion", 1.0) < 1 and pe.get("sd_residual", 0) > 0:
            brecha_nivel = pe["desviacion_ultimo"] - pe["nivel_local"]
            if abs(brecha_nivel) > 2 * pe["sd_residual"]:
                res.alertas.append(f"El ultimo mes esta {(math.expm1(brecha_nivel) if usar_log else brecha_nivel):+.1%} "
                                   f"respecto al nivel del ultimo ano (mas de 2 desviaciones); la proyeccion desvanece "
                                   f"esa diferencia con persistencia {pe['phi_desviacion']:.2f}")
        if n >= 13 and y[-13] > 0 and y[-1] > 0:
            cambio12 = y[-1] / y[-13] - 1
            if abs(cambio12) > 0.05 and np.sign(res.tendencia_mensual) != np.sign(cambio12):
                res.alertas.append(f"La tendencia de {res.parametros['ventana']} meses ({res.tendencia_mensual:+.1%} "
                                   f"mensual) va en sentido contrario al cambio real de los ultimos 12 meses "
                                   f"({cambio12:+.0%})")

    # backtest: se re-proyecta desde cortes pasados con el mismo modelo y se compara contra lo real
    res.error_modelo, res.error_ultimo_valor, res.error_ses, res.n_cortes = backtest(z, y, modelo, inv, meses, phi_desv,
                                                                                  cred_pend, media_arit)
    if (res.n_cortes and np.isfinite(res.error_modelo) and np.isfinite(res.error_ultimo_valor)
            and res.error_modelo > res.error_ultimo_valor * 1.10 + 0.5):
        res.alertas.append(f"En el backtest de esta serie el modelo ({res.error_modelo:.1f}%) no supera a repetir "
                           f"el ultimo valor ({res.error_ultimo_valor:.1f}%)")

    res.pronostico, res.li, res.ls = list(pron[brecha:]), list(li[brecha:]), list(ls[brecha:])
    return _post_proceso(res, y, tipo, serie.dominio)


def backtest(z, y, modelo: str, inv, meses=None, phi_desv: float = 1.0, cred_pend=1.0, media_arit: bool = False):
    """Error % (WAPE = suma |error| / suma |real|) del modelo, del ultimo valor y de SES, re-proyectando desde
    CORTES_BACKTEST meses antes del final (horizontes de 1 a 16 meses). La estacionalidad se re-estima en cada
    corte solo con la historia anterior al corte."""
    n = len(y)
    errores = {"modelo": [0.0, 0.0], "ultimo": [0.0, 0.0], "ses": [0.0, 0.0]}
    cortes = 0
    for c in CORTES_BACKTEST:
        o = n - c
        if o < MIN_ENTRENAMIENTO:
            continue
        hz = min(16, n - o)
        real = y[o:o + hz]
        preds = {"ultimo": np.repeat(inv(z[o - 1]), hz)}
        for nombre, mod in (("modelo", modelo), ("ses", "SES")):
            try:
                preds[nombre] = (inv(ajustar(z[:o], mod, hz, None if meses is None else meses[:o], phi_desv, cred_pend,
                                             media_arit)[0])
                                 if mod != ULTIMO_VALOR else preds["ultimo"])
            except Exception:  # noqa: BLE001
                preds[nombre] = None
        if any(p is None or not np.all(np.isfinite(p)) for p in preds.values()):
            continue
        cortes += 1
        for nombre, p in preds.items():
            errores[nombre][0] += float(np.sum(np.abs(p - real)))
            errores[nombre][1] += float(np.sum(np.abs(real)))

    def wape(e):
        return (e[0] / e[1] * 100) if cortes and e[1] > 0 else math.nan

    return wape(errores["modelo"]), wape(errores["ultimo"]), wape(errores["ses"]), cortes


def _cuantil_normal():
    return float(_normal.ppf(0.5 + NIVEL_INTERVALO / 2))


def _post_proceso(res: Resultado, y, tipo, dominio=(None, None)):
    """Cotas actuariales (dominio) y alerta de cambios mayores a los observados en la historia."""
    p = np.array(res.pronostico, dtype=float)
    if np.all(np.isnan(p)):
        return res
    li = np.array(res.li, dtype=float)
    ls = np.array(res.ls, dtype=float)
    lo_d, hi_d = dominio
    lo_d = -np.inf if lo_d is None else lo_d
    hi_d = np.inf if hi_d is None else hi_d
    if tipo == "nivel":
        lo_d = max(lo_d, 0.0)
    if np.any(p < lo_d - 1e-12) or np.any(p > hi_d + 1e-12):
        res.alertas.append(f"Proyeccion fuera del dominio actuarial [{lo_d}, {hi_d}]: se acota")
    p, li, ls = np.clip(p, lo_d, hi_d), np.clip(li, lo_d, hi_d), np.clip(ls, lo_d, hi_d)
    if y is not None and tipo in ("nivel", "indice") and len(y) > len(p) and np.all(y > 0) and "trimestral" not in res.modelo:
        k = len(p)
        cambios = np.abs(np.log(y[k:] / y[:-k]))
        if len(cambios) and p[-1] > 0:
            cambio = abs(math.log(p[-1] / y[-1]))
            if cambio > np.max(cambios) + 1e-12:
                res.alertas.append(
                    f"Cambio proyectado a {k} meses ({(p[-1] / y[-1] - 1):+.1%}) mayor al maximo historico "
                    f"a {k} meses ({(math.exp(np.max(cambios)) - 1):.1%})")
    res.pronostico, res.li, res.ls = [float(v) for v in p], [float(v) for v in li], [float(v) for v in ls]
    return res


def correr_series(series: list[Serie]) -> dict:
    n_proc = N_PROCESOS or max(1, (os.cpu_count() or 2) - 1)
    resultados = {}
    t0 = time.time()
    if n_proc > 1 and len(series) > 1:
        try:
            with ProcessPoolExecutor(max_workers=n_proc) as ex:
                for i, r in enumerate(ex.map(pronosticar, series, chunksize=2), start=1):
                    resultados[r.clave] = r
                    if i % 50 == 0 or i == len(series):
                        print(f"   {i}/{len(series)} series ({time.time() - t0:,.0f} s)", flush=True)
            return resultados
        except Exception as e:  # noqa: BLE001
            print(f"   Paralelismo no disponible ({e!r}); se continua en un solo proceso", flush=True)
            resultados = {}
    for i, s in enumerate(series, start=1):
        r = pronosticar(s)
        resultados[r.clave] = r
        if i % 50 == 0 or i == len(series):
            print(f"   {i}/{len(series)} series ({time.time() - t0:,.0f} s)", flush=True)
    return resultados


def resumen_backtest(resultados: dict) -> list[dict]:
    """Una fila por tipo de serie y libro: error % mediano del modelo, del ultimo valor y de SES en el backtest."""
    filas = []
    grupos = sorted({(r.tipo, r.clave[0]) for r in resultados.values()},
                    key=lambda g: (["nivel", "indice", "razon", "lag"].index(g[0]), g[1]))
    for tipo, libro in grupos:
        todos = [r for r in resultados.values() if r.tipo == tipo and r.clave[0] == libro]
        rs = [r for r in todos if r.n_cortes and np.isfinite(r.error_modelo) and np.isfinite(r.error_ultimo_valor)]
        modelos = ", ".join(sorted({r.modelo for r in (rs or todos) if r.modelo}))  # solo los modelos de las series con backtest
        fila = {"Tipo": tipo, "Libro": libro, "Modelo": modelos, "Series con backtest": len(rs)}
        if rs:
            em = np.array([r.error_modelo for r in rs])
            eu = np.array([r.error_ultimo_valor for r in rs])
            es = np.array([r.error_ses for r in rs])
            fila.update({
                "Cortes por serie (mediana)": float(np.median([r.n_cortes for r in rs])),
                "Error % modelo (mediana)": float(np.median(em)),
                "Error % ultimo valor (mediana)": float(np.median(eu)),
                "Error % SES (mediana)": float(np.nanmedian(es)) if np.any(np.isfinite(es)) else None,
                "% series en que el modelo mejora al ultimo valor": float(np.mean(em < eu)),
            })
        filas.append(fila)
    return filas


# =============================================================================
# LECTURA DE LAS BD DE MONTOS
# =============================================================================
@dataclass
class BDMontos:
    ruta: Path
    wb: object
    ws: object
    col_concepto: int
    col_periodo: int
    col_tc: int
    cols_ramo: dict            # ramo(str) -> columna
    filas: dict                # (concepto, periodo) -> fila
    valores: dict              # (concepto, periodo, ramo) -> float
    tc: dict                   # periodo -> tc
    conceptos: list            # en el orden en que aparecen


def leer_bd_montos(ruta: Path) -> BDMontos:
    wb = openpyxl.load_workbook(ruta)
    ws = wb[HOJA_MONTOS]
    enc = {norm(ws.cell(3, c).value): c for c in range(1, ws.max_column + 1) if ws.cell(3, c).value}
    cols_ramo = {h.split("_", 1)[1]: c for h, c in enc.items() if h.startswith("RAM_")}
    filas, valores, tc, conceptos = {}, {}, {}, []
    for r in range(4, ws.max_row + 1):
        concepto = ws.cell(r, enc["CONCEPTO"]).value
        periodo = ws.cell(r, enc["PERIODO"]).value
        if not concepto or not isinstance(periodo, (int, float)):
            continue
        concepto, periodo = norm(concepto), int(periodo)
        if concepto not in conceptos:
            conceptos.append(concepto)
        filas[(concepto, periodo)] = r
        for ramo, c in cols_ramo.items():
            v, _ = a_numero(ws.cell(r, c).value)
            valores[(concepto, periodo, ramo)] = 0.0 if math.isnan(v) else v
        t, _ = a_numero(ws.cell(r, enc["TC"]).value)
        if not math.isnan(t):
            tc[periodo] = t
    return BDMontos(ruta, wb, ws, enc["CONCEPTO"], enc["PERIODO"], enc["TC"], cols_ramo, filas, valores, tc,
                    conceptos)


def tc_para_periodo(bd: BDMontos, p: int) -> float:
    """TC con que se escribe (y se convierte) cada mes: TC_PROYECCION (supuesto de Inversiones) si lo trae
    (y, para renglones existentes, solo si ACTUALIZAR_TC_EXISTENTES); si no, el de la BD o su ultimo TC."""
    if p in TC_PROYECCION and (ACTUALIZAR_TC_EXISTENTES or p not in bd.tc):
        return TC_PROYECCION[p]
    if p in bd.tc:
        return bd.tc[p]
    return bd.tc[max(bd.tc)]


def leer_tc_real(bd: BDMontos, ultimo: int, libro: str = "", alertas: list | None = None) -> dict:
    """TC real con que la fuente SAP convirtio cada mes a USD. Se usa para regresar la historia a MXN. Prioridad:
    1) Res_Rvas en entradas/ (fila 7 de BacktestingRRC, columnas SAP), si estan; 2) los meses reales de
    TC_PROYECCION (tipo_cambio.py: 202601 en adelante hasta el ultimo real = TC de SAP); 3) la columna TC de la BD.
    Si la columna TC de la BD difiere del TC real en algun mes de la historia, se avisa: la historia se regresa a
    pesos con el real, que es con el que se convirtieron los montos."""
    tc = {p: v for p, v in bd.tc.items() if p <= ultimo}
    tc.update({p: v for p, v in TC_PROYECCION.items() if p <= ultimo})
    for ruta in sorted(ENTRADAS.glob("Res_Rvas_*.xlsx")):
        try:
            wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
            if "BacktestingRRC" not in wb.sheetnames:
                continue
            filas = list(wb["BacktestingRRC"].iter_rows(min_row=1, max_row=8, values_only=True))
            wb.close()
        except Exception:  # noqa: BLE001
            continue
        for c, escenario in enumerate(filas[0]):
            per, v = filas[7][c], filas[6][c]
            if norm(escenario) == "SAP" and isinstance(per, (int, float)) and isinstance(v, (int, float)) \
                    and int(per) <= ultimo:
                tc[int(per)] = float(v)
    if alertas is not None:
        difieren = [p for p, v in sorted(tc.items()) if p in bd.tc and bd.tc[p] and abs(bd.tc[p] / v - 1) > 0.005]
        if difieren:
            detalle = ", ".join(f"{p}: BD {bd.tc[p]:.4f} vs real {tc[p]:.4f}" for p in difieren)
            texto = (f"La columna TC de la BD no es el TC real de SAP en {len(difieren)} meses de la historia ({detalle}). "
                     "Para regresar la historia a pesos se usa el real (con el que se convirtieron los montos).")
            alertas.append((libro, "TC de la historia", texto))
            print(f"   AVISO {libro}: {texto}", flush=True)
    return tc


def series_montos(bd: BDMontos, libro: str, reservas: dict, ultimo: int, h: int,
                  tc_hist: dict | None = None) -> list[Serie]:
    """reservas = {"RRC": {"nivel": "BEL", "razones_bel": [...], "cesion": "IRR"}, ...}. Construye las
    series driver (nivel y razones). Si tc_hist se indica, los montos se modelan en MXN (USD x TC real)."""
    periodos = sorted({p for (_, p) in bd.filas if p <= ultimo})
    periodos = rango_periodos(periodos[0], ultimo)
    moneda = "MXN" if tc_hist else "USD"

    def a_moneda(v, p):
        return v * tc_hist[p] if tc_hist and not math.isnan(v) else v

    series = []
    for pref, est in reservas.items():
        for ramo in bd.cols_ramo:
            def val(conc, p):
                return bd.valores.get((f"{pref} {conc}".strip(), p, ramo), math.nan)
            nivel = [a_moneda(val(est["nivel"], p), p) for p in periodos]
            series.append(Serie((libro, pref, est["nivel"], ramo), "nivel", periodos, nivel, ultimo, h,
                                moneda=moneda))
            for conc in est.get("razones_bel", []):
                raz = []
                for p in periodos:
                    b, x = val(est["nivel"], p), val(conc, p)
                    raz.append(x / b if (b and not math.isnan(b) and abs(b) >= UMBRAL_CERO_MONTOS
                                         and not math.isnan(x)) else math.nan)
                series.append(Serie((libro, pref, f"{conc}/{est['nivel']}", ramo), "razon", periodos, raz,
                                    ultimo, h, dominio=DOMINIO_RAZON_BEL))
            if est.get("cesion"):
                raz = []
                for p in periodos:
                    br = _bruto(bd, pref, est, ramo, p)
                    x = val(est["cesion"], p)
                    raz.append(x / br if (br and not math.isnan(br) and abs(br) >= UMBRAL_CERO_MONTOS
                                          and not math.isnan(x)) else math.nan)
                series.append(Serie((libro, pref, f"{est['cesion']}/BRUTO", ramo), "razon", periodos, raz,
                                    ultimo, h, dominio=DOMINIO_CESION))
        # conceptos que se proyectan como total y se reparten por ramo con la mezcla reciente (p.ej. RCONT)
        for conc in est.get("totales_con_mezcla", []):
            serie = [a_moneda(sum(bd.valores.get((norm(conc), p, r), 0.0) for r in bd.cols_ramo), p)
                     for p in periodos]
            series.append(Serie((libro, pref, f"{conc} TOTAL", "TOTAL"), "nivel", periodos, serie, ultimo, h,
                                trimestral=norm(conc) in {norm(c) for c in ESTACIONALIDAD_TRIMESTRAL},
                                moneda=moneda))
    return series


def mezcla_reciente(bd: BDMontos, concepto: str, ultimo: int, meses: int) -> dict:
    """Participacion de cada ramo en el concepto durante los ultimos `meses` meses con dato."""
    periodos = [p for p in sorted({p for (c, p) in bd.filas if c == norm(concepto) and p <= ultimo})
                if any(bd.valores.get((norm(concepto), p, r), 0.0) for r in bd.cols_ramo)][-meses:]
    totales = {r: sum(bd.valores.get((norm(concepto), p, r), 0.0) for p in periodos) for r in bd.cols_ramo}
    suma = sum(totales.values())
    return {r: (v / suma if suma else 0.0) for r, v in totales.items()}


def _bruto(bd, pref, est, ramo, p):
    """BRUTO historico tal como esta en la BD (en RRC/SONR la historia cumple BRUTO = BEL + GTO + MR)."""
    return bd.valores.get((f"{pref} BRUTO", p, ramo), math.nan)


def periodo_ultimo_real(periodos_proy: list[int]) -> int:
    return indice_a_periodo(periodo_a_indice(periodos_proy[0]) - 1)


def detectar_moneda_mezclada(bd: BDMontos, ultimo: int, conceptos: list | None = None) -> dict:
    """Meses de la historia que vienen en MXN dentro de una BD en USD: {periodo: TC de la BD}. Se recorre la historia
    hacia atras desde el ultimo mes (que se toma como USD); un salto entre dos meses seguidos del tamano del TC
    (dentro de TOLERANCIA_SALTO_TC) marca un cambio de moneda. Se usa el total de ramos de los conceptos dados (o de
    todos si conceptos es None)."""
    totales = {}
    for (c, p, _), v in bd.valores.items():
        if (conceptos is None or c in conceptos) and p <= ultimo and isinstance(v, (int, float)) and not math.isnan(v):
            totales[p] = totales.get(p, 0.0) + abs(v)
    periodos = [p for p in sorted(totales) if totales[p] > 0]
    tolerancia = math.log(1 + TOLERANCIA_SALTO_TC)
    en_mxn, unidad = {}, "USD"
    for i in range(len(periodos) - 1, 0, -1):
        a, b = periodos[i - 1], periodos[i]          # a = mes anterior, b = mes siguiente
        razon = totales[a] / totales[b]
        tc_a, tc_b = bd.tc.get(a), bd.tc.get(b)
        if unidad == "USD" and tc_a and tc_a > 3 and abs(math.log(razon / tc_a)) < tolerancia:
            unidad = "MXN"                           # el mes anterior es ~TC veces mayor: viene en pesos
        elif unidad == "MXN" and tc_b and tc_b > 3 and abs(math.log(1 / razon / tc_b)) < tolerancia:
            unidad = "USD"                           # regreso a dolares
        if unidad == "MXN" and tc_a:
            en_mxn[a] = tc_a
    return en_mxn


def corregir_moneda_mezclada(bd: BDMontos, libro: str, ultimo: int, alertas: list) -> list:
    """Convierte a USD (en memoria) los meses que la BD trae en MXN. La deteccion es por reserva (primera palabra del
    concepto: RFV, RCONT, RRC, SONR): los conceptos de una reserva (BRUTO, IRR, NETO...) se detectan juntos, asi que
    se convierten juntos y las identidades se conservan; una reserva que se capturo en USD en esos meses (p. ej. la
    RCONT de 2025) no trae el salto y se deja como viene. Regresa las celdas corregidas
    [(concepto, periodo, ramo, valor original, valor en USD, tc)] para escribirlas en la BD de salida."""
    familias = {}
    for c in sorted({c for (c, _, _) in bd.valores}):
        familias.setdefault(c.split(" ")[0], []).append(c)
    por_familia = {f: detectar_moneda_mezclada(bd, ultimo, cs) for f, cs in familias.items()}
    por_familia = {f: m for f, m in por_familia.items() if m}
    if not por_familia:
        return []
    cambios = []
    for (c, p, r), v in list(bd.valores.items()):
        en_mxn = por_familia.get(c.split(" ")[0], {})
        if p in en_mxn and v:
            bd.valores[(c, p, r)] = v / en_mxn[p]
            cambios.append((c, p, r, v, v / en_mxn[p], en_mxn[p]))
    grupos = {}                                      # conceptos que comparten el mismo tramo en pesos
    for f, m in por_familia.items():
        grupos.setdefault(tuple(sorted(m)), []).extend(familias[f])
    tramos = "; ".join(f"{', '.join(cs)}: {len(ms)} meses ({ms[0]} a {ms[-1]})" for ms, cs in grupos.items())
    meses = sorted(set().union(*por_familia.values()))
    sin_salto = [c for f, cs in familias.items() if f not in por_familia for c in cs
                 if any(bd.valores.get((c, p, r)) for p in meses for r in bd.cols_ramo)]
    texto = (f"{tramos} venian en pesos (el salto contra el mes siguiente es del tamano del TC); se convirtieron a USD "
             f"con el TC de cada mes de la BD ({len(cambios)} celdas). Sin esto la tendencia leia el cambio de moneda "
             "como una caida de ~94 %."
             + (f" {', '.join(sin_salto)}: no trae ese salto en esos meses (se toma como USD) y se deja como viene."
                if sin_salto else "")
             + " Revisa la BD de entrada.")
    alertas.append((libro, "Moneda mezclada en la historia", texto + " Detalle por celda: hoja Moneda_corregida."))
    print(f"   AVISO {libro}: {texto}", flush=True)
    return cambios


def escribir_correccion_moneda(bd: BDMontos, cambios: list):
    """Escribe en la BD de salida los valores historicos convertidos a USD. No agrega comentarios ni otras partes al
    libro (la BD de salida conserva la estructura de la de entrada); el detalle celda por celda queda en la hoja
    Moneda_corregida del diagnostico."""
    for c, p, r, original, nuevo, tc in cambios:
        fila, col = bd.filas.get((c, p)), bd.cols_ramo.get(r)
        if fila is None or col is None:
            continue
        bd.ws.cell(fila, col).value = nuevo


def texto_rango(inf: float | None, sup: float | None) -> str:
    """Rango esperado para textos: "80-100 M USD", "minimo 80 M USD, sin tope" o "maximo 100 M USD, sin piso"."""
    if inf is not None and sup is not None:
        return f"{inf/1e6:,.0f}-{sup/1e6:,.0f} M USD"
    if inf is not None:
        return f"minimo {inf/1e6:,.0f} M USD, sin tope"
    if sup is not None:
        return f"maximo {sup/1e6:,.0f} M USD, sin piso"
    return "sin limites"


def aplicar_rango_esperado(proy: dict, bd: BDMontos, libro: str, reservas: dict, resultados: dict,
                           periodos_proy: list[int], ultimo: int, alertas: list) -> list:
    """Mantiene el total (suma de ramos, USD) de los conceptos de RANGO_ESPERADO dentro de su rango. Si la proyeccion
    sale, el crecimiento de cada ramo respecto a su ultimo real se eleva a una potencia k en [0, 1] (la misma para
    todos los ramos), la mayor que deja todos los meses dentro; BRUTO, IRR, NETO y demas conceptos de la reserva de
    cada ramo se escalan con el mismo factor, y tambien el driver (pronostico e intervalo) del diagnostico. Si ni con
    k = 0 (nivel del ultimo real) queda dentro, cada mes se lleva al limite. Regresa lineas de resumen."""
    resumen = []
    for (lib, concepto), (inf_cfg, sup_cfg) in RANGO_ESPERADO.items():
        if lib != libro:
            continue
        inf = -np.inf if inf_cfg is None else inf_cfg
        sup = np.inf if sup_cfg is None else sup_cfg
        rango = texto_rango(inf_cfg, sup_cfg)
        pref = concepto.split()[0]
        est = reservas.get(pref)
        if not est:
            continue
        driver = f"{pref} {est['nivel']}"
        ramos = list(bd.cols_ramo)
        n = len(periodos_proy)
        # crecimiento del driver (en USD) respecto al ultimo real, por ramo y mes
        crec = {}
        for r in ramos:
            base = bd.valores.get((norm(driver), ultimo, r), 0.0)
            proy_r = np.array([proy.get((norm(driver), p, r), 0.0) for p in periodos_proy])
            crec[r] = proy_r / base if base > 0 and np.all(proy_r > 0) else np.ones(n)
        objetivo = {r: np.array([proy.get((norm(concepto), p, r), 0.0) for p in periodos_proy]) for r in ramos}

        def total(k):
            return sum(objetivo[r] * crec[r] ** (k - 1) for r in ramos)      # factor = crec**k / crec

        def fuera(k):
            tt = total(k)
            return float(np.max(np.maximum(tt - sup, inf - tt)))

        sin_ajuste = total(1.0)
        if fuera(1.0) <= 0:
            resumen.append(f"{libro} {concepto}: dentro del rango ({rango}) sin ajuste "
                           f"({periodos_proy[0]}: {sin_ajuste[0]/1e6:,.1f}; {periodos_proy[-1]}: {sin_ajuste[-1]/1e6:,.1f})")
            continue
        if fuera(0.0) <= 0:
            lo, hi = 0.0, 1.0
            for _ in range(60):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if fuera(mid) <= 0 else (lo, mid)
            k = lo
            factores = {r: crec[r] ** (k - 1) for r in ramos}
            nota = f"se conservo el {k:.0%} del crecimiento proyectado"
        else:
            k = 0.0
            nivel = total(0.0)
            recorte = np.clip(nivel, inf, sup) / nivel
            factores = {r: crec[r] ** -1 * recorte for r in ramos}
            nota = "el ultimo real ya estaba fuera del rango: se llevo cada mes al limite"
        for r in ramos:
            f = factores[r]
            for (c, p, rr) in list(proy):
                if rr == r and c.startswith(pref + " ") and p in periodos_proy:
                    proy[(c, p, rr)] *= float(f[periodos_proy.index(p)])
            res = resultados.get((libro, pref, est["nivel"], r))
            if res is not None:
                res.pronostico = [v * float(fi) for v, fi in zip(res.pronostico, f)]
                res.li = [v * float(fi) for v, fi in zip(res.li, f)]
                res.ls = [v * float(fi) for v, fi in zip(res.ls, f)]
                res.alertas.append(f"Rango esperado de {concepto} total ({rango}): {nota}")
                res.parametros["factor_rango_esperado"] = float(k)
        con_ajuste = sum(np.array([proy.get((norm(concepto), p, r), 0.0) for p in periodos_proy]) for r in ramos)
        texto = (f"El modelo proyectaba {concepto} total de {sin_ajuste[0]/1e6:,.1f} a {sin_ajuste[-1]/1e6:,.1f} M USD "
                 f"({periodos_proy[0]} a {periodos_proy[-1]}), fuera del rango esperado ({rango}); "
                 f"{nota}: queda de {con_ajuste[0]/1e6:,.1f} a {con_ajuste[-1]/1e6:,.1f} (RANGO_ESPERADO).")
        alertas.append((libro, f"Rango esperado {concepto}", texto))
        resumen.append(texto)
        print(f"   {libro}: {texto}", flush=True)
    return resumen


def leer_presupuesto() -> dict | None:
    """Lee el dashboard HTML del presupuesto tecnico (objeto DATA incrustado). Regresa {"archivo", "anio", "P", "S"},
    con P y S = {"total": {...}, "fianzas": {...}} y cada uno {"real_ant", "ppto_curso", "reest_curso", "ppto"}
    (real del ano anterior, presupuesto original y reestimado del ano en curso, presupuesto del ano siguiente)."""
    archivos = sorted(ENTRADAS.glob(PATRON_PRESUPUESTO), key=lambda f: f.stat().st_mtime)
    if not archivos:
        return None
    ruta = archivos[-1]
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        i = texto.index("const DATA = ") + len("const DATA = ")
        datos, _ = json.JSONDecoder().raw_decode(texto[i:])
        kpi = datos["vistas"]["T"]["lnKpi"]                       # vista "tomado"
        anio = int((datos.get("cfg") or {}).get("anio") or 0)
    except Exception as e:  # noqa: BLE001
        print(f"   Aviso: no se pudo leer el presupuesto {ruta.name}: {e!r}", flush=True)
        return {"archivo": ruta.name, "anio": 0, "error": repr(e)}
    if not anio:
        print(f"   Aviso: el presupuesto {ruta.name} no trae el ano (cfg.anio); no se hace el contraste", flush=True)
        return {"archivo": ruta.name, "anio": 0, "error": "sin anio"}
    campos = {"real_ant": "r25", "ppto_curso": "p", "reest_curso": "r", "ppto": "f"}

    def val(ln, medida, c):
        return float((((kpi.get(ln) or {}).get(medida)) or {}).get(c) or 0.0)
    # lineas nuevas: sin reestimado del ano en curso pero con presupuesto (negocio sin base: la reserva proyectada por
    # tendencia no puede traerlo, asi que se excluyen de la referencia comparable)
    nuevas = [ln for ln in kpi if ln != "_tot" and ln not in LINEAS_FIANZAS_PPTO
              and val(ln, "P", "r") <= 0 and val(ln, "P", "p") <= 0 and val(ln, "P", "f") > 0]
    salida = {"archivo": ruta.name, "anio": anio, "lineas_nuevas": nuevas,
              "prima_ln_siguiente": {ln: val(ln, "P", "f") for ln in kpi if ln != "_tot"}}
    for medida in ("P", "S"):
        total = {k: val("_tot", medida, c) for k, c in campos.items()}
        fianzas = {k: sum(val(ln, medida, c) for ln in LINEAS_FIANZAS_PPTO) for k, c in campos.items()}
        nuevo = {k: sum(val(ln, medida, c) for ln in nuevas) for k, c in campos.items()}
        salida[medida] = {"total": total, "fianzas": fianzas, "nuevas": nuevo,
                          "danos": {k: total[k] - fianzas[k] - nuevo[k] for k in campos},
                          "danos_con_nuevas": {k: total[k] - fianzas[k] for k in campos}}
    return salida


def contraste_presupuesto(ppto: dict, bds: dict, proys: dict, alertas: list) -> list:
    """Filas del contraste reservas contra presupuesto: total NETO de cada reserva a diciembre de los tres anos del
    presupuesto (real si ya paso, proyectado si no) contra su referencia (primas o siniestros tomados)."""
    anio = ppto["anio"]
    if not anio:
        return []
    cortes = [(anio - 2) * 100 + 12, (anio - 1) * 100 + 12, anio * 100 + 12]
    nuevas = ppto.get("lineas_nuevas") or []
    sin_nuevas = f", sin la{'s' if len(nuevas) > 1 else ''} linea{'s' if len(nuevas) > 1 else ''} nueva{'s' if len(nuevas) > 1 else ''} {', '.join(nuevas)}" if nuevas else ""
    referencias = [("DANOS", "RRC NETO", "P", "danos", f"Primas tomadas (Daños{sin_nuevas})"),
                   ("DANOS", "SONR NETO", "S", "danos", f"Siniestros tomados (Daños{sin_nuevas})"),
                   ("FIANZAS", "RFV NETO", "P", "fianzas", f"Primas líneas {', '.join(LINEAS_FIANZAS_PPTO)} (Fianzas)")]
    filas = []
    for libro, concepto, medida, grupo, nombre_ref in referencias:
        bd, proy = bds[libro], proys[libro]

        def total(p):
            if any((concepto, p, r) in proy for r in bd.cols_ramo):          # mes proyectado
                return sum(proy.get((concepto, p, r), 0.0) for r in bd.cols_ramo) or None
            return sum(bd.valores.get((concepto, p, r), 0.0) for r in bd.cols_ramo) or None   # mes real
        res = [total(p) for p in cortes]
        ref = ppto[medida][grupo]
        refs = [ref["real_ant"], ref["reest_curso"], ref["ppto"]]

        def crec(a, b):
            return (b / a - 1) if a and b else None
        fila = {"Reserva": concepto, "Referencia": nombre_ref}
        for p, v in zip(cortes, res):
            fila[f"Reserva {p}"] = v
        fila.update({f"Referencia {anio - 2} real": refs[0], f"Referencia {anio - 1} reestimado": refs[1],
                     f"Referencia {anio} presupuesto": refs[2],
                     f"Crec. reserva {anio - 1}": crec(res[0], res[1]), f"Crec. referencia {anio - 1}": crec(refs[0], refs[1]),
                     f"Crec. reserva {anio}": crec(res[1], res[2]), f"Crec. referencia {anio}": crec(refs[1], refs[2])})
        for k, (v, rf) in enumerate(zip(res, refs)):
            fila[f"Reserva / referencia {anio - 2 + k}"] = (v / rf) if v and rf else None
        dif = (fila[f"Crec. reserva {anio}"] - fila[f"Crec. referencia {anio}"]
               if fila[f"Crec. reserva {anio}"] is not None and fila[f"Crec. referencia {anio}"] is not None else None)
        fila[f"Diferencia {anio} (pts)"] = dif * 100 if dif is not None else None   # puntos porcentuales
        if grupo == "danos" and nuevas:
            con = ppto[medida]["danos_con_nuevas"]
            fila[f"Crec. referencia {anio} con líneas nuevas"] = crec(con["reest_curso"], con["ppto"])
        if dif is not None and abs(dif) > TOLERANCIA_PRESUPUESTO:
            texto = (f"{concepto} crece {fila[f'Crec. reserva {anio}']:+.1%} en {anio} (dic contra dic) y su referencia en el "
                     f"presupuesto, {nombre_ref[0].lower() + nombre_ref[1:]}, {fila[f'Crec. referencia {anio}']:+.1%}: diferencia de "
                     f"{dif * 100:+.0f} pts. La razon reserva / referencia pasa de {fila[f'Reserva / referencia {anio - 1}'] or 0:.2f} "
                     f"a {fila[f'Reserva / referencia {anio}'] or 0:.2f}. Revisa si el crecimiento proyectado es coherente con el negocio.")
            alertas.append((libro, f"Presupuesto {concepto}", texto))
        filas.append(fila)
    return filas


# =============================================================================
# FACTOR DE PRIMA (reserva = factor mensual x exposicion de prima del grupo de ramo)
# =============================================================================
MODELO_FACTOR = "Factor de prima"
MODELO_COMBINACION = "Combinacion recta y factor de prima"
SERIES_FACTOR = {("DANOS", "RRC"): "BEL", ("DANOS", "SONR"): "BEL", ("FIANZAS", "RFV"): "BRUTO"}


def persistencia_ar1(z, meses=None) -> tuple[float, float]:
    """"Factor de error" del factor de prima: el error de ln(factor) alrededor de su recta (sin el patron del mes)
    como AR(1). rho = sum e_t e_(t-1) / sum e_(t-1)^2 sobre los ultimos MESES_TENDENCIA meses, con la correccion de
    sesgo de primer orden para residuos de una recta (rho + (2 + 4 rho) / n), acotado a [0, 1]; con 36 meses sigue
    sesgado a la baja cerca de 1. Regresa (rho corregido, persistencia a usar): con
    menos de MIN_MESES_AR1 meses, PRIOR_PERSISTENCIA_FACTOR; con rho >= 0.98, 1 (el error no se desvanece)."""
    z = np.asarray(z, dtype=float)
    est = factores_estacionales(z, meses) if (ESTACIONALIDAD_MENSUAL and meses is not None) else None
    d = z - est["factores"][np.asarray(meses, dtype=int) - 1] if est is not None else z
    w = d[-MESES_TENDENCIA:] if MESES_TENDENCIA and len(d) > MESES_TENDENCIA else d
    n = len(w)
    if n < MIN_MESES_AR1:
        return math.nan, PRIOR_PERSISTENCIA_FACTOR
    t = np.arange(n, dtype=float)
    e = w - np.polyval(np.polyfit(t, w, 1), t)
    den = float(np.sum(e[:-1] ** 2))
    rho = float(np.sum(e[1:] * e[:-1]) / den) if den > 0 else 0.0
    rho_c = float(np.clip(rho + (2 + 4 * rho) / n, 0.0, 1.0))
    return rho_c, (1.0 if rho_c >= 0.98 else rho_c)


def pendientes_sonr(hp, ramo, periodo: int) -> tuple[list, str]:
    """Parte pendiente de reportar por ano de suscripcion, v_a = 1 - LAG a (a = 1..ANIOS_LAG_SONR), del patron de
    desarrollo del ramo en HParametros al ultimo mes con dato hasta 'periodo'."""
    r_hp = MAPA_RAMO_LAG.get(str(ramo))
    v, notas = [], []
    for a in range(1, ANIOS_LAG_SONR + 1):
        h = hp.historia.get((r_hp, f"LAG {a}"), {}) if (hp is not None and r_hp) else {}
        fechas = [f for f, x in h.items() if f <= periodo and not math.isnan(x)]
        if fechas:
            v.append(float(np.clip(1 - h[max(fechas)], 0.0, 1.0)))
            if periodo_a_indice(periodo) - periodo_a_indice(max(fechas)) > 12:
                notas.append(f"LAG {a} de {max(fechas)}")
        else:
            v.append(PENDIENTE_DEFECTO[a - 1] if a - 1 < len(PENDIENTE_DEFECTO) else 0.0)
            notas.append(f"LAG {a} por defecto")
    return v, "; ".join(notas)


def _prima_grupo(pr, grupo: str, moneda: str, tc: dict, factor_sig: float = 1.0) -> pd.Series:
    """Prima mensual del grupo en la moneda del modelo (MXN = USD x TC del mes). factor_sig escala la prima del ano
    siguiente (sensibilidad)."""
    p = pr.mensual[grupo].astype(float).copy()
    if factor_sig != 1.0:
        p[[x for x in p.index if x // 100 >= pr.anio_sig]] *= factor_sig
    if moneda == "MXN":
        p = p * pd.Series([tc.get(int(x), math.nan) for x in p.index], index=p.index)
    return p


def ajustar_factor(y_per: list, y_val, D: pd.Series, per_proy: list, cfg: tuple, libro: str) -> dict | None:
    """Ajusta ln(factor) = ln(reserva) - ln(driver) con la recta de la tendencia historica (pendiente y persistencia
    de cfg = (driver, pendiente, persistencia)) y proyecta reserva = factor x driver. None si no hay factor valido
    suficiente o el driver no esta definido en la proyeccion."""
    y = np.asarray(y_val, dtype=float)
    d_hist = np.array([D.get(p, np.nan) for p in y_per], dtype=float)
    ok = (y > 0) & np.isfinite(d_hist) & (d_hist > 0)
    if not len(ok) or not ok[-1]:
        return None
    ini = len(ok)
    while ini > 0 and ok[ini - 1]:
        ini -= 1
    if len(ok) - ini < MIN_MESES_FACTOR.get(libro, 24):
        return None
    d_fut = np.array([D.get(p, np.nan) for p in per_proy], dtype=float)
    if not np.all(np.isfinite(d_fut) & (d_fut > 0)):
        return None
    per_k = list(y_per[ini:])
    z = np.log(y[ini:]) - np.log(d_hist[ini:])
    meses = np.array([p % 100 for p in per_k], dtype=int)
    rho, phi_est = persistencia_ar1(z, meses)
    phi = 1.0 if cfg[2] == 1.0 else phi_est
    f, lo, hi, params, _ = ajustar_tendencia(z, len(per_proy), meses, phi, cfg[1])
    if not np.all(np.isfinite(f)):
        return None
    return {"pron": np.exp(f + np.log(d_fut)), "ln_pron": f + np.log(d_fut), "hw": f - lo, "per_kappa": per_k,
            "kappa_hist": np.exp(z), "kappa_fut": np.exp(f), "d_hist": d_hist[ini:], "d_fut": d_fut,
            "params": params, "rho": rho, "phi": phi, "n": len(z)}


def _recta(y, per, hz: int):
    """Proyeccion de la recta actual de montos (la misma de _pronosticar para 'nivel') desde y (positiva)."""
    meses = np.array([p % 100 for p in per], dtype=int)
    f = ajustar(np.log(np.asarray(y, dtype=float)), TENDENCIA, hz, meses, float(PERSISTENCIA_DESVIACION.get("nivel", 1.0)),
                CREDIBILIDAD_PENDIENTE.get("nivel", 1.0))[0]
    return np.exp(f)


def _wape(pares) -> float:
    e = sum(a for a, _ in pares)
    r = sum(b for _, b in pares)
    return e / r * 100 if r > 0 else math.nan


def _tol(x: float) -> float:
    return TOLERANCIA_FACTOR[0] * x + TOLERANCIA_FACTOR[1]


def aplicar_factor_prima(resultados: dict, pr, hp, tc: dict, bds: dict, periodos_proy: list[int], ultimo: int,
                         alertas: list) -> dict:
    """Etapa del factor de prima: elegibilidad por serie, backtest (oraculo, ex ante con el presupuesto del ano en
    curso y prima plana), configuracion y decision por tipo (A recta, B factor, C combinacion) y aplicacion a
    res.pronostico de las series con B o C. Regresa el diagnostico."""
    diag = {"series": [], "rejilla": [], "decision": [], "backtest": [], "mensual": [], "estado": ""}
    if not USAR_FACTOR_PRIMA:
        diag["estado"] = "apagado (USAR_FACTOR_PRIMA = False)"
        return diag
    if pr is None:
        diag["estado"] = "sin archivos de prima real en entradas/: se usa la recta"
        return diag
    if not pr.tiene_siguiente:
        diag["estado"] = "sin prima del ano siguiente (presupuesto): se usa la recta"
        return diag
    atraso = periodo_a_indice(ultimo) - periodo_a_indice(pr.ultimo_real)
    if atraso > MAX_MESES_PRIMA_ESTIMADA:
        diag["estado"] = (f"la prima real llega a {pr.ultimo_real} y las reservas a {ultimo}: actualiza el real de primas "
                          "del ano; se usa la recta")
        alertas.append(("PRIMAS", "Factor de prima", diag["estado"]))
        return diag
    z90 = _cuantil_normal()
    h = len(periodos_proy)
    anio = pr.ultimo_real // 100
    corte_ppto = (anio - 1) * 100 + 12                 # corte del backtest ex ante (con el presupuesto del ano)
    cfgs_tipo = {t: [(d, pe, ps) for d in DRIVERS_FACTOR[t] for pe in PENDIENTES_FACTOR for ps in PERSISTENCIAS_FACTOR]
                 for t in SERIES_FACTOR}
    por_serie = {}

    for (libro, reserva), nivel in SERIES_FACTOR.items():
        moneda = "MXN" if MODELAR_EN_MXN.get(libro) else "USD"
        for ramo in bds[libro].cols_ramo:
            clave = (libro, reserva, nivel, ramo)
            res = resultados.get(clave)
            if res is None:
                continue
            grupo = primas.GRUPO_DE_RAMO_RESERVA.get(str(ramo))
            info = {"libro": libro, "reserva": reserva, "ramo": ramo, "grupo": grupo, "moneda": moneda,
                    "elegible": False, "motivo": ""}
            por_serie[clave] = info
            y, per = np.asarray(res.historia_valores, dtype=float), list(res.historia_periodos)
            tc_t = tc.get(ultimo, math.nan) if moneda == "MXN" else 1.0
            p12 = primas.exposicion(pr.mensual[grupo], "P12").get(ultimo, math.nan) if grupo in pr.mensual else math.nan
            if res.regla or not per or per[-1] != ultimo:
                info["motivo"] = f"resuelta por regla ({res.regla or 'sin dato al ultimo mes'})"
            elif grupo is None or pr.cobertura.get(grupo) is None or pr.cobertura[grupo] < primas.MIN_COBERTURA_HISTORIA:
                c = pr.cobertura.get(grupo) if grupo else None
                info["motivo"] = f"cobertura de prima insuficiente en el grupo {grupo} ({'s/d' if c is None else f'{c:.0%}'})"
            elif not np.isfinite(p12) or p12 < UMBRAL_PRIMA_FACTOR:
                info["motivo"] = f"prima de 12 meses del grupo {grupo} menor a {UMBRAL_PRIMA_FACTOR / 1e6:,.0f} M USD"
            elif y[-1] / tc_t < UMBRAL_RESERVA_FACTOR:
                info["motivo"] = f"reserva menor a {UMBRAL_RESERVA_FACTOR / 1e6:,.0f} M USD"
            elif not np.all(y > 0):
                info["motivo"] = "reserva con valores no positivos en la historia"
            if info["motivo"]:
                continue
            prima = _prima_grupo(pr, grupo, moneda, tc)
            ajustes, bts = {}, {}
            for cfg in cfgs_tipo[(libro, reserva)]:
                v, nota_v = pendientes_sonr(hp, ramo, ultimo) if cfg[0] == "PDP" else (None, "")
                D = primas.exposicion(prima, cfg[0], v)
                a = ajustar_factor(per, y, D, periodos_proy, cfg, libro)
                if a is None:
                    continue
                k_t = a["kappa_hist"][-1]
                if not (RANGO_FACTOR[0] <= k_t <= RANGO_FACTOR[1]):
                    continue
                a["nota_lag"], a["v"] = nota_v, v
                ajustes[cfg] = a
                # backtest de esta configuracion
                cortes = {}
                cs = list(CORTES_BACKTEST)
                if pr.ppto_curso is not None and corte_ppto in per:     # ex ante en su propio corte de diciembre
                    c_pp = len(per) - 1 - per.index(corte_ppto)
                    if c_pp >= 1 and c_pp not in cs:
                        cs.append(c_pp)
                for c in cs:
                    o = len(y) - c
                    if o < MIN_ENTRENAMIENTO:
                        continue
                    hz = min(16, len(y) - o)
                    real = y[o:o + hz]
                    pc = per[o - 1]
                    per_h = per[o:o + hz]
                    v_c = pendientes_sonr(hp, ramo, pc)[0] if cfg[0] == "PDP" else None
                    b = ajustar_factor(per[:o], y[:o], primas.exposicion(prima, cfg[0], v_c), per_h, cfg, libro)
                    if b is None:
                        continue
                    try:
                        ra = _recta(y[:o], per[:o], hz)
                    except Exception:  # noqa: BLE001
                        continue
                    fila = {"A": ra, "B": b["pron"], "C": np.exp(0.5 * (np.log(ra) + b["ln_pron"])), "real": real,
                            "U": np.repeat(y[o - 1], hz), "cv": c in CORTES_BACKTEST}
                    # prima plana: despues del corte, el mismo mes del ano anterior
                    pl = prima.copy()
                    for x in pl.index:
                        if x > pc and _mas_meses(x, -12) in pl.index:
                            pl[x] = pl[_mas_meses(x, -12)]
                    bp = ajustar_factor(per[:o], y[:o], primas.exposicion(pl, cfg[0], v_c), per_h, cfg, libro)
                    if bp is not None:
                        fila["B plana"] = bp["pron"]
                    if pc == corte_ppto and pr.ppto_curso is not None and grupo in pr.ppto_curso:
                        pp = _prima_grupo(pr, grupo, "USD", tc).copy()
                        for x in pr.ppto_curso.index:
                            if x in pp.index and x > pc:
                                pp[x] = pr.ppto_curso.at[x, grupo]
                        if moneda == "MXN":         # despues del corte, el TC disponible al corte (no el realizado)
                            pp = pp * pd.Series([tc.get(int(min(x, pc)), math.nan) for x in pp.index], index=pp.index)
                        bx = ajustar_factor(per[:o], y[:o], primas.exposicion(pp, cfg[0], v_c), per_h, cfg, libro)
                        if bx is not None:
                            fila["B ppto"] = bx["pron"]
                            fila["C ppto"] = np.exp(0.5 * (np.log(ra) + np.log(bx["pron"])))
                    cortes[pc] = fila
                bts[cfg] = cortes
            if not ajustes:
                info["motivo"] = f"factor fuera de rango o con menos de {MIN_MESES_FACTOR.get(libro)} meses validos"
                continue
            info.update({"elegible": True, "ajustes": ajustes, "bts": bts, "prima": prima})

    # configuracion y decision por tipo
    decision_tipo = {}
    for tipo, cfgs in cfgs_tipo.items():
        elegibles = [k for k, i in por_serie.items() if i["elegible"] and (i["libro"], i["reserva"]) == tipo]
        # (serie, corte) en que todas las configuraciones tienen backtest (se comparan en los mismos casos)
        comunes = set()
        for k in elegibles:
            cortes_cfg = [{pc for pc, f in por_serie[k]["bts"].get(cfg, {}).items() if f["cv"]} for cfg in cfgs]
            comunes |= {(k, pc) for pc in (set.intersection(*cortes_cfg) if cortes_cfg else set())}
        wape_cfg = {}
        for cfg in cfgs:
            pares = [(float(np.sum(np.abs(por_serie[k]["bts"][cfg][pc]["B"] - por_serie[k]["bts"][cfg][pc]["real"]))),
                      float(np.sum(np.abs(por_serie[k]["bts"][cfg][pc]["real"])))) for k, pc in comunes]
            wape_cfg[cfg] = _wape(pares) if pares else math.nan
            diag["rejilla"].append({"Tipo": f"{tipo[0]} {tipo[1]}", "Driver": cfg[0], "Pendiente del factor": str(cfg[1]),
                                    "Persistencia": str(cfg[2]), "Series": len({k for k, _ in comunes}),
                                    "Cortes (serie x corte)": len(comunes), "Error % (oraculo)": wape_cfg[cfg]})
        defecto = cfgs[0]
        elegida = defecto
        if len({k for k, _ in comunes}) >= 2 and np.isfinite(wape_cfg.get(defecto, math.nan)):
            mejor = min((c for c in cfgs if np.isfinite(wape_cfg[c])), key=lambda c: wape_cfg[c], default=defecto)
            if wape_cfg[mejor] <= wape_cfg[defecto] - MARGEN_PREFERENCIA_FACTOR:
                elegida = mejor
        # errores agrupados con la configuracion elegida
        pares = {m: [] for m in ("A", "B", "C", "A ppto", "B ppto", "C ppto", "B plana", "A plana")}
        n_series = set()
        for k in elegibles:
            for pc, f in por_serie[k]["bts"].get(elegida, {}).items():
                n_series.add(k)
                den = float(np.sum(np.abs(f["real"])))
                if f["cv"]:                        # cortes estandar: prueba con la prima real
                    for m in ("A", "B", "C"):
                        pares[m].append((float(np.sum(np.abs(f[m] - f["real"]))), den))
                if "B ppto" in f:
                    pares["B ppto"].append((float(np.sum(np.abs(f["B ppto"] - f["real"]))), den))
                    pares["C ppto"].append((float(np.sum(np.abs(f["C ppto"] - f["real"]))), den))
                    pares["A ppto"].append((float(np.sum(np.abs(f["A"] - f["real"]))), den))
                if "B plana" in f:
                    pares["B plana"].append((float(np.sum(np.abs(f["B plana"] - f["real"]))), den))
                    pares["A plana"].append((float(np.sum(np.abs(f["A"] - f["real"]))), den))
                diag["backtest"].append({"Tipo": f"{tipo[0]} {tipo[1]}", "Ramo": k[3], "Corte": pc, "Meses": len(f["real"]),
                                         "Corte estandar": bool(f["cv"]), "Configuracion": f"{elegida[0]}",
                                         "Recta (A)": _wape([(float(np.sum(np.abs(f["A"] - f["real"]))), den)]),
                                         "Factor, prima real (B)": _wape([(float(np.sum(np.abs(f["B"] - f["real"]))), den)]),
                                         "Factor, presupuesto (B)": _wape([(float(np.sum(np.abs(f["B ppto"] - f["real"]))), den)]) if "B ppto" in f else None,
                                         "Factor, prima plana (B)": _wape([(float(np.sum(np.abs(f["B plana"] - f["real"]))), den)]) if "B plana" in f else None,
                                         "Combinacion (C)": _wape([(float(np.sum(np.abs(f["C"] - f["real"]))), den)])})
        w = {m: _wape(v) if v else math.nan for m, v in pares.items()}
        n_cortes = len(pares["A"])
        forzado = MODELO_MONTOS if MODELO_MONTOS in ("primas", "combinacion", "tendencia") else None
        if forzado:
            dec, motivo = {"primas": "B", "combinacion": "C", "tendencia": "A"}[forzado], f"forzado (MODELO_MONTOS = {forzado})"
        elif not n_cortes:
            dec, motivo = "A", "sin series con backtest del factor"
        else:
            hay_ppto = bool(pares["B ppto"])

            def pasa(m):
                ok_or = np.isfinite(w[m]) and w[m] <= _tol(w["A"])
                ok_pp = (not hay_ppto) or (np.isfinite(w[f"{m} ppto"]) and w[f"{m} ppto"] <= _tol(w["A ppto"]))
                return ok_or and ok_pp
            if pasa("B"):
                dec, motivo = "B", "el factor no pierde contra la recta (prima real" + (" y presupuesto" if hay_ppto else "") + ")"
            elif pasa("C"):
                dec, motivo = "C", "la combinacion no pierde contra la recta; el factor solo, si"
            else:
                dec, motivo = "A", "la prima no mejora a la recta en este tipo de reserva"
            if not hay_ppto:
                motivo += (f"; sin prueba con el presupuesto del ano en curso (sin presupuesto mensual del ano o sin "
                           f"historia suficiente al corte {corte_ppto}): decide solo la prima real")
            if len(n_series) < 2 or n_cortes < 3:
                motivo += f"; indicativo ({len(n_series)} series, {n_cortes} cortes)"
        decision_tipo[tipo] = (dec, elegida)
        diag["decision"].append({"Tipo": f"{tipo[0]} {tipo[1]}", "Series elegibles": len(elegibles),
                                 "Series con backtest": len(n_series), "Cortes (serie x corte)": n_cortes,
                                 "Configuracion": f"{elegida[0]}, pendiente {elegida[1]}, persistencia {elegida[2]}",
                                 "Recta (A)": w["A"], "Factor, prima real (B)": w["B"], "Combinacion (C)": w["C"],
                                 "Recta en el corte ex ante": w["A ppto"], "Factor con presupuesto (B)": w["B ppto"],
                                 "Combinacion con presupuesto (C)": w["C ppto"], "Factor con prima plana (B)": w["B plana"],
                                 "Decision": {"A": "recta", "B": "factor de prima", "C": "combinacion"}[dec],
                                 "Motivo": motivo})
        if elegibles:
            alertas.append(("PRIMAS", f"Factor de prima {tipo[0]} {tipo[1]}",
                            f"Decision: {({'A': 'recta', 'B': 'factor de prima', 'C': 'combinacion'})[dec]} ({motivo}). "
                            f"Error % backtest: recta {w['A']:.1f}, factor {w['B']:.1f}, combinacion {w['C']:.1f}"
                            + (f"; con presupuesto: recta {w['A ppto']:.1f}, factor {w['B ppto']:.1f}" if np.isfinite(w['B ppto']) else "")))

    # aplicacion
    i_dic = next((i for i, p in enumerate(periodos_proy) if p % 100 == 12), None)
    for clave, info in por_serie.items():
        res = resultados[clave]
        tipo = (info["libro"], info["reserva"])
        dec, cfg = decision_tipo.get(tipo, ("A", None))
        forzada = MODELO_MONTOS_SERIE.get((info["libro"], info["reserva"], str(info["ramo"])))
        if forzada in ("primas", "combinacion", "tendencia"):
            dec = {"primas": "B", "combinacion": "C", "tendencia": "A"}[forzada]
        fila = {"Libro": info["libro"], "Reserva": info["reserva"], "Ramo": info["ramo"], "Grupo": info["grupo"],
                "Moneda": info["moneda"], "Elegible": info["elegible"], "Motivo": info["motivo"]}
        if not info["elegible"]:
            res.factor = {"decision": "recta", "motivo": info["motivo"]}
            diag["series"].append(fila)
            continue
        forzado_global = MODELO_MONTOS in ("primas", "combinacion")
        if forzada in ("primas", "combinacion", "tendencia") or forzado_global:
            fila["Motivo"] = f"forzado ({'MODELO_MONTOS_SERIE' if forzada else 'MODELO_MONTOS'})"
        if cfg not in info["ajustes"]:
            alterna = next((c for c in info["ajustes"] if c[1:] == (cfg or (None,))[1:]), next(iter(info["ajustes"])))
            if forzada not in ("primas", "combinacion") and not forzado_global:
                dec = "A"
                fila["Motivo"] = (f"el driver del tipo ({cfg[0] if cfg else '-'}) no aplica a esta serie (factor fuera de "
                                  f"rango o sin meses suficientes) y {alterna[0]} no paso por la decision del tipo: recta")
            cfg = alterna
        a = info["ajustes"][cfg]
        prima = info["prima"]
        es_est = pd.Series(pr.fuente[info["grupo"]] != "real", index=pr.fuente.index)
        f_est = primas.fraccion_estimada(prima, es_est, cfg[0], a["v"])
        f_est_proy = np.array([f_est.get(p, 0.0) for p in periodos_proy])
        hw_b = np.sqrt(a["hw"] ** 2 + (z90 * f_est_proy * pr.sigma_plan.get(info["grupo"], 0.15)) ** 2)
        recta = np.array(res.pronostico, dtype=float)
        li_r, ls_r = np.array(res.li, dtype=float), np.array(res.ls, dtype=float)
        hw_a = (np.log(np.maximum(ls_r, 1e-12)) - np.log(np.maximum(li_r, 1e-12))) / 2
        # elasticidad observada (diagnostico): MCO de cambios de 12 meses de ln reserva sobre ln driver
        lr = np.log(np.asarray(res.historia_valores, dtype=float)[-len(a["kappa_hist"]):])
        ld = np.log(a["d_hist"])
        elast = (float(np.polyfit(ld[12:] - ld[:-12], lr[12:] - lr[:-12], 1)[0])
                 if len(lr) > 14 and np.std(ld[12:] - ld[:-12]) > 0 else math.nan)
        pe = a["params"]
        fila.update({"Driver": cfg[0], "Pendiente del factor": str(cfg[1]), "Persistencia": str(cfg[2]),
                     "Meses del factor": a["n"], "Factor al ultimo mes": a["kappa_hist"][-1],
                     "Rho del error (AR1)": a["rho"], "Persistencia usada": a["phi"],
                     "Credibilidad estacional del factor": pe.get("credibilidad_estacional"),
                     "Pendiente aplicada del factor (mensual)": math.expm1(pe.get("pendiente_aplicada", 0.0)),
                     "Pendiente observada del factor (mensual)": math.expm1(pe.get("pendiente", 0.0)),
                     "R2 del factor": pe.get("r2"), "Elasticidad observada": elast,
                     "% del driver estimado a dic": f_est_proy[-1], "Nota LAG": a.get("nota_lag", "")})
        if np.isfinite(elast) and not (0.3 <= elast <= 2.0):
            res.alertas.append(f"Elasticidad observada reserva / prima de {elast:.2f} (fuera de 0.3-2): la reserva no se "
                               "ha movido en proporcion a su driver de prima")
        bts_c = [f for f in info["bts"].get(cfg, {}).values() if f["cv"]]      # cortes estandar

        def _w(m):
            return _wape([(float(np.sum(np.abs(f[m] - f["real"]))), float(np.sum(f["real"]))) for f in bts_c])
        wa, wb_, wc, wu = _w("A"), _w("B"), _w("C"), _w("U")
        fila.update({"Error % recta": wa, "Error % factor": wb_, "Error % combinacion": wc})
        if np.isfinite(wb_) and np.isfinite(wa) and wb_ > 2 * wa + 5:
            res.alertas.append(f"En el backtest de esta serie el factor de prima ({wb_:.1f}%) queda muy por arriba de "
                               f"la recta ({wa:.1f}%)")
        pron_b = a["pron"]
        if dec == "B":
            nuevo, hw, modelo = pron_b, hw_b, f"{MODELO_FACTOR} ({cfg[0]})"
        elif dec == "C":
            nuevo = np.exp(0.5 * (np.log(recta) + np.log(pron_b)))
            hw, modelo = 0.5 * (hw_a + hw_b), f"{MODELO_COMBINACION} ({cfg[0]})"
        else:
            nuevo, modelo = None, res.modelo
        decomp = ""
        if i_dic is not None and i_dic + 12 < len(periodos_proy):
            j0, j1 = i_dic, i_dic + 12
            cd = a["d_fut"][j1] / a["d_fut"][j0] - 1
            ck = a["kappa_fut"][j1] / a["kappa_fut"][j0] - 1
            decomp = f"prima {cd:+.1%}, factor {ck:+.1%}"
            fila.update({f"Crec. driver {periodos_proy[j0]}-{periodos_proy[j1]}": cd,
                         f"Crec. factor {periodos_proy[j0]}-{periodos_proy[j1]}": ck,
                         f"Crec. recta {periodos_proy[j0]}-{periodos_proy[j1]}": recta[j1] / recta[j0] - 1,
                         f"Crec. factor de prima {periodos_proy[j0]}-{periodos_proy[j1]}": pron_b[j1] / pron_b[j0] - 1})
        res.factor = {"decision": {"A": "recta", "B": "factor de prima", "C": "combinacion"}[dec], "driver": cfg[0],
                      "config": cfg, "pron_recta": list(recta), "li_recta": list(li_r), "ls_recta": list(ls_r),
                      "error_recta": wa, "modelo_recta": res.modelo, "pron_factor": list(pron_b),
                      "descomposicion": decomp, "grupo": info["grupo"], "kappa_T": float(a["kappa_hist"][-1])}
        fila["Decision"] = res.factor["decision"]
        fila[f"Recta {periodos_proy[-1]}"] = recta[-1]
        fila[f"Factor de prima {periodos_proy[-1]}"] = pron_b[-1]
        if nuevo is not None:
            res.pronostico = [float(v) for v in nuevo]
            res.li = [float(v) for v in np.exp(np.log(nuevo) - hw)]
            res.ls = [float(v) for v in np.exp(np.log(nuevo) + hw)]
            res.modelo = modelo
            res.error_modelo = wb_ if dec == "B" else wc
            res.error_ultimo_valor, res.error_ses, res.n_cortes = wu, math.nan, len(bts_c)
            # las alertas de la recta quedan como de la alternativa; las del backtest se rehacen con los mismos cortes
            res.alertas = [("Recta alternativa: " + x) if x.startswith(("R2 de la tendencia", "La tendencia de",
                                                                        "El ultimo mes esta")) else x
                           for x in res.alertas
                           if not x.startswith(("Cambio proyectado a", "En el backtest de esta serie el modelo ("))]
            if res.n_cortes and np.isfinite(res.error_modelo) and np.isfinite(wu) and res.error_modelo > wu * 1.10 + 0.5:
                res.alertas.append(f"En el backtest de esta serie el modelo ({res.error_modelo:.1f}%) no supera a "
                                   f"repetir el ultimo valor ({wu:.1f}%)")
            _post_proceso(res, np.asarray(res.historia_valores, dtype=float), res.tipo)
            res.alertas.append(f"Modelo final: {modelo}; recta alternativa a {periodos_proy[-1]}: {recta[-1]:,.0f} "
                               f"{info['moneda']} (error backtest {wa:.1f}% contra {res.error_modelo:.1f}%)"
                               + (f"; dic/dic: {decomp}" if decomp else ""))
        fila[f"Final {periodos_proy[-1]}"] = res.pronostico[-1]
        diag["series"].append(fila)
        # factor mensual (historia y proyeccion)
        for p_, k_, d_ in zip(a["per_kappa"], a["kappa_hist"], a["d_hist"]):
            diag["mensual"].append({"Libro": info["libro"], "Reserva": info["reserva"], "Ramo": info["ramo"],
                                    "Grupo": info["grupo"], "Periodo": p_, "Tipo": "Real", "Driver": cfg[0],
                                    "Valor del driver": d_, "% del driver estimado": float(f_est.get(p_, 0.0)),
                                    "Factor (reserva / driver)": k_, "Reserva con factor de prima": k_ * d_,
                                    "Reserva con recta": None, "Reserva final": k_ * d_, "Moneda": info["moneda"]})
        for i, p_ in enumerate(periodos_proy):
            diag["mensual"].append({"Libro": info["libro"], "Reserva": info["reserva"], "Ramo": info["ramo"],
                                    "Grupo": info["grupo"], "Periodo": p_, "Tipo": "Proyeccion", "Driver": cfg[0],
                                    "Valor del driver": a["d_fut"][i], "% del driver estimado": f_est_proy[i],
                                    "Factor (reserva / driver)": a["kappa_fut"][i],
                                    "Reserva con factor de prima": pron_b[i], "Reserva con recta": recta[i],
                                    "Reserva final": res.pronostico[i], "Moneda": info["moneda"]})
    usadas = [f for f in diag["series"] if f.get("Decision") in ("factor de prima", "combinacion")]
    diag["estado"] = (f"{len(usadas)} de {len(diag['series'])} series con factor de prima o combinacion; "
                      f"{sum(1 for f in diag['series'] if f['Elegible'])} elegibles")
    diag["_por_serie"] = por_serie
    diag["_decision_tipo"] = decision_tipo
    return diag


def sensibilidad_factor(resultados: dict, diag: dict, pr, tc: dict, periodos_proy: list[int]) -> dict:
    """Pronosticos de las series con factor (o combinacion) si la prima del ano siguiente fuera SENSIBILIDAD_PRIMA
    veces la del presupuesto: {escala: {clave: pronostico}} (el factor no cambia: solo el driver)."""
    salida = {}
    for escala in SENSIBILIDAD_PRIMA:
        mod = {}
        for clave, info in (diag.get("_por_serie") or {}).items():
            res = resultados[clave]
            if not info.get("elegible") or res.factor.get("decision") not in ("factor de prima", "combinacion"):
                continue
            cfg = res.factor["config"]
            a = info["ajustes"][cfg]
            D = primas.exposicion(_prima_grupo(pr, info["grupo"], info["moneda"], tc, escala), cfg[0], a["v"])
            d_fut = np.array([D.get(p, np.nan) for p in periodos_proy])
            pron_b = a["kappa_fut"] * d_fut
            if res.factor["decision"] == "combinacion":
                pron_b = np.exp(0.5 * (np.log(np.array(res.factor["pron_recta"])) + np.log(pron_b)))
            mod[clave] = [float(v) for v in pron_b]
        salida[escala] = mod
    return salida


def _totales_neto(proy: dict, periodos: list[int]) -> dict:
    """{reserva: {periodo: total NETO de todos los ramos}} de un diccionario de montos derivados."""
    out = {}
    for (c, p, _), v in proy.items():
        if c.endswith(" NETO") and p in periodos:
            pref = c.split()[0]
            out.setdefault(pref, {}).setdefault(p, 0.0)
            out[pref][p] += v
    return out


def comparar_factor(resultados: dict, diag: dict, pr, tc: dict, bds: dict, proys: dict, periodos_proy: list[int],
                    tc_hist: dict, ultimo: int, sin_rango: dict | None = None) -> dict:
    """Totales NETO (todos los ramos, USD) de RRC, SONR y RFV con el modelo final (con el ajuste por rango esperado,
    como en la BD), con el modelo final sin ese ajuste, con la recta en todas las series y con la prima del ano
    siguiente movida SENSIBILIDAD_PRIMA. Los ultimos tres se arman con los pronosticos antes del rango esperado
    (sin_rango), asi que son comparables entre si."""
    por_serie = diag.get("_por_serie") or {}
    con_factor = [k for k, i in por_serie.items() if i.get("elegible")
                  and resultados[k].factor.get("decision") in ("factor de prima", "combinacion")]
    if not con_factor:
        return {}

    base = sin_rango or {}

    def derivar_con(mods: dict) -> dict:
        res2 = {k: replace(r, pronostico=list(mods[k]) if k in mods else list(base.get(k, r.pronostico)))
                for k, r in resultados.items()}
        return {lib: derivar_montos(bds[lib], lib, ESTRUCTURA[lib], res2, periodos_proy, en_mxn=lib in tc_hist)
                for lib in bds}

    escenarios = {"Modelo final": proys}
    if base and any(base[k] != list(r.pronostico) for k, r in resultados.items() if k in base):
        escenarios["Modelo final sin rango esperado"] = derivar_con({})
    escenarios["Recta en todas las series"] = derivar_con({k: resultados[k].factor["pron_recta"] for k in con_factor})
    for escala, mods in sensibilidad_factor(resultados, diag, pr, tc, periodos_proy).items():
        escenarios[f"Prima {pr.anio_sig} x {escala:.2f}"] = derivar_con(mods)
    dics = [p for p in periodos_proy if p % 100 == 12]
    reales = {}
    for lib, bd in bds.items():
        for (c, p, _), v in bd.valores.items():
            if p == ultimo and c.endswith(" NETO") and isinstance(v, (int, float)) and not math.isnan(v):
                reales.setdefault(c.split()[0], 0.0)
                reales[c.split()[0]] += v
    filas = []
    for nombre, proy in escenarios.items():
        tot = {}
        for lib in proy:
            for pref, d in _totales_neto(proy[lib], dics).items():
                tot[pref] = d
        for pref in ("RRC", "SONR", "RFV"):
            if pref not in tot:
                continue
            fila = {"Escenario": nombre, "Reserva": f"{pref} NETO", f"Real {ultimo}": reales.get(pref)}
            for p in dics:
                fila[f"Proy {p}"] = tot[pref].get(p)
            if len(dics) >= 2 and tot[pref].get(dics[0]):
                fila[f"Crec. {dics[0]}-{dics[1]}"] = tot[pref][dics[1]] / tot[pref][dics[0]] - 1
            filas.append(fila)
    return {"filas": filas, "series_con_factor": len(con_factor)}


def actualizar_finales_factor(diag: dict, resultados: dict, periodos_proy: list[int]):
    """Despues del rango esperado: 'Final' y 'Reserva final' del diagnostico del factor con el pronostico que se
    escribe en la BD."""
    for fila in diag.get("series") or []:
        clave = next((k for k in resultados if k[0] == fila["Libro"] and k[1] == fila["Reserva"] and k[3] == fila["Ramo"]
                      and resultados[k].tipo == "nivel" and k[2] == SERIES_FACTOR.get((k[0], k[1]))), None)
        if clave and f"Final {periodos_proy[-1]}" in fila:
            fila[f"Final {periodos_proy[-1]}"] = resultados[clave].pronostico[-1]
    pos = {p: i for i, p in enumerate(periodos_proy)}
    for fila in diag.get("mensual") or []:
        if fila["Tipo"] == "Proyeccion":
            clave = (fila["Libro"], fila["Reserva"], SERIES_FACTOR[(fila["Libro"], fila["Reserva"])], fila["Ramo"])
            if clave in resultados:
                fila["Reserva final"] = resultados[clave].pronostico[pos[fila["Periodo"]]]


def _mas_meses(periodo: int, meses: int) -> int:
    return indice_a_periodo(periodo_a_indice(periodo) + meses)


def derivar_montos(bd: BDMontos, libro: str, reservas: dict, resultados: dict, periodos_proy: list[int],
                   en_mxn: bool = False):
    """Aplica las identidades contables y regresa {(concepto, periodo, ramo): valor en USD}. Si los montos
    se modelaron en MXN se convierten con el TC de cada mes proyectado (el mismo que se escribe en la BD)."""
    tc_proy = np.array([tc_para_periodo(bd, p) for p in periodos_proy]) if en_mxn else 1.0
    salida = {}
    for pref, est in reservas.items():
        for ramo in bd.cols_ramo:
            nivel = np.array(resultados[(libro, pref, est["nivel"], ramo)].pronostico, dtype=float)
            nivel = np.nan_to_num(nivel, nan=0.0) / tc_proy
            comps = {}
            for conc in est.get("razones_bel", []):
                r = np.nan_to_num(np.array(resultados[(libro, pref, f"{conc}/{est['nivel']}", ramo)].pronostico),
                                  nan=0.0)
                comps[conc] = r * nivel
            if est["nivel"] == "BRUTO":
                bruto = nivel
            else:
                bruto = nivel + sum(comps.values()) if comps else nivel.copy()
            c = np.nan_to_num(np.array(resultados[(libro, pref, f"{est['cesion']}/BRUTO", ramo)].pronostico),
                              nan=0.0)
            irr = c * bruto
            neto = bruto - irr
            valores = {f"{pref} BRUTO": bruto, f"{pref} {est['cesion']}": irr, f"{pref} NETO": neto}
            if est["nivel"] != "BRUTO":
                valores[f"{pref} {est['nivel']}"] = nivel
            for conc, v in comps.items():
                valores[f"{pref} {conc}"] = v
            for conc in est.get("totales_con_mezcla", []):
                total = np.nan_to_num(np.array(resultados[(libro, pref, f"{conc} TOTAL", "TOTAL")].pronostico),
                                      nan=0.0) / tc_proy
                mezcla = mezcla_reciente(bd, conc, periodo_ultimo_real(periodos_proy), MESES_MEZCLA)
                valores[conc] = total * mezcla[ramo]
            for conc, arr in valores.items():
                for i, p in enumerate(periodos_proy):
                    salida[(norm(conc), p, ramo)] = float(arr[i])
    return salida


# =============================================================================
# ESCRITURA DE LAS BD DE MONTOS (mismo formato)
# =============================================================================
def _copiar_estilo(origen, destino):
    if origen.has_style:
        destino.font = copy(origen.font)
        destino.border = copy(origen.border)
        destino.fill = copy(origen.fill)
        destino.number_format = origen.number_format
        destino.protection = copy(origen.protection)
        destino.alignment = copy(origen.alignment)


def escribir_bd_montos(bd: BDMontos, proy: dict, periodos_proy: list[int], ruta_salida: Path) -> dict:
    ws = bd.ws
    relleno = PatternFill("solid", fgColor=COLOR_RESALTADO) if RESALTAR_PROYECCION else None
    ultima_col = ws.max_column

    faltan = {c for (c, _, _) in proy} - set(bd.conceptos)
    if faltan:
        raise ValueError(f"Conceptos proyectados que no existen en la BD: {faltan}")
    conceptos_bd = [c for c in bd.conceptos if any((c, p, r) in proy for p in periodos_proy for r in bd.cols_ramo)]
    nuevos, actualizados = 0, 0
    # orden de los conceptos en los bloques nuevos: el del bloque del anio mas reciente
    anio_ref = max(p for (_, p) in bd.filas if p < PERIODO_INICIO) // 100
    primera_fila = {c: min((r for (cc, p), r in bd.filas.items() if cc == c and p // 100 == anio_ref),
                           default=10 ** 9) for c in conceptos_bd}
    orden = sorted(conceptos_bd, key=lambda c: primera_fila[c])
    fila_nueva = ws.max_row + 1
    # 0) TC de los renglones existentes segun el supuesto de Inversiones
    tc_cambiados = 0
    if ACTUALIZAR_TC_EXISTENTES:
        for (c, p), r in bd.filas.items():
            if p in TC_PROYECCION:
                nuevo = TC_PROYECCION[p]
                if ws.cell(r, bd.col_tc).value != nuevo:
                    ws.cell(r, bd.col_tc).value = nuevo
                    tc_cambiados += 1
    # 1) periodos que ya existen (p.ej. 202609-202612 en ceros)
    for (c, p), r in list(bd.filas.items()):
        if p in periodos_proy and c in conceptos_bd:
            for ramo, col in bd.cols_ramo.items():
                celda = ws.cell(r, col)
                celda.value = proy[(c, p, ramo)]
                if relleno:
                    celda.fill = relleno
            actualizados += 1
    # 2) periodos nuevos: se agregan al final, bloque por concepto (mismo orden que la BD)
    anios_nuevos = sorted({p // 100 for p in periodos_proy if all((c, p) not in bd.filas for c in conceptos_bd)})
    for anio in anios_nuevos:
        for c in orden:
            for p in [q for q in periodos_proy if q // 100 == anio]:
                if (c, p) in bd.filas:
                    continue
                plantilla = _fila_plantilla(bd, c, p)
                r = fila_nueva
                for col in range(1, ultima_col + 1):
                    _copiar_estilo(ws.cell(plantilla, col), ws.cell(r, col))
                    v = ws.cell(plantilla, col).value
                    if isinstance(v, str) and v.startswith("="):
                        ws.cell(r, col).value = Translator(v, origin=ws.cell(plantilla, col).coordinate) \
                            .translate_formula(ws.cell(r, col).coordinate)
                if ws.row_dimensions[plantilla].height:
                    ws.row_dimensions[r].height = ws.row_dimensions[plantilla].height
                ws.cell(r, bd.col_concepto).value = ws.cell(plantilla, bd.col_concepto).value
                ws.cell(r, bd.col_periodo).value = p
                ws.cell(r, bd.col_tc).value = tc_para_periodo(bd, p)
                for ramo, col in bd.cols_ramo.items():
                    ws.cell(r, col).value = proy[(c, p, ramo)]
                    if relleno:
                        ws.cell(r, col).fill = relleno
                bd.filas[(c, p)] = r
                fila_nueva += 1
                nuevos += 1
    if ws.auto_filter and ws.auto_filter.ref:
        ini, fin = ws.auto_filter.ref.split(":")
        col_fin = re.match(r"[A-Z]+", fin).group()
        ws.auto_filter.ref = f"{ini}:{col_fin}{ws.max_row}"
    return {"actualizados": actualizados, "nuevos": nuevos, "tc_cambiados": tc_cambiados}


def _fila_plantilla(bd: BDMontos, concepto: str, periodo: int) -> int:
    """Renglon del mismo concepto y mismo mes del anio mas reciente (para copiar formato)."""
    candidatos = [(p, r) for (c, p), r in bd.filas.items() if c == concepto and p % 100 == periodo % 100]
    if not candidatos:
        candidatos = [(p, r) for (c, p), r in bd.filas.items() if c == concepto]
    return max(candidatos)[1]


# =============================================================================
# HPARAMETROS
# =============================================================================
@dataclass
class HParam:
    ws: object
    cols: dict                 # nombre encabezado -> columna (primera aparicion)
    historia: dict             # (ramo_str, columna) -> {periodo: valor}
    ramos_activos: list        # (ramo_original, fila_plantilla) en el orden del ultimo bloque
    ultimo: int
    textos_limpiados: int
    lags_cero: list


def leer_hparametros(wb) -> HParam:
    ws = wb[HOJA_PARAMETROS]
    cols = {}
    for c in range(1, 60):
        v = ws.cell(3, c).value
        if v is not None and str(v).strip() not in cols:
            cols[str(v).strip()] = c
    necesarias = ["Tipo de Indice", "Llave", "Fecha", "Ramo"] + INDICES + LAGS
    faltan = [n for n in necesarias if n not in cols]
    if faltan:
        raise ValueError(f"{HOJA_PARAMETROS}: faltan columnas {faltan}")
    historia, textos, ultimos = {}, 0, {}
    lags_cero = []
    for r in range(4, ws.max_row + 1):
        if norm(ws.cell(r, cols["Tipo de Indice"]).value) != norm(TIPO_INDICE_BASE):
            continue
        fecha = ws.cell(r, cols["Fecha"]).value
        ramo = ws.cell(r, cols["Ramo"]).value
        if not isinstance(fecha, (int, float)) or ramo is None:
            continue
        fecha = int(fecha)
        clave_ramo = str(ramo).strip()
        ultimos.setdefault(fecha, []).append((ramo, r))
        max_previo = 0.0
        for nombre in INDICES + LAGS:
            v, fue_texto = a_numero(ws.cell(r, cols[nombre]).value)
            if fue_texto and not math.isnan(v):
                textos += 1
            if nombre in LAGS:
                # patron acumulado: un 0 despues de haber superado 50% es marcador de faltante
                if not math.isnan(v) and v == 0 and max_previo > 0.5:
                    lags_cero.append((fecha, clave_ramo, nombre))
                    v = math.nan
                if not math.isnan(v):
                    max_previo = max(max_previo, v)
            historia.setdefault((clave_ramo, nombre), {})[fecha] = v
    ultimo = max(ultimos)
    return HParam(ws, cols, historia, ultimos[ultimo], ultimo, textos, lags_cero)


def series_hparametros(hp: HParam, h: int, ultimo: int) -> list[Serie]:
    """ultimo = ultimo mes real global (PERIODO_INICIO - 1): si el ultimo 'Real' de la hoja es anterior, el
    mecanismo de rezago proyecta desde el ultimo dato y entrega exactamente los meses a proyectar."""
    series = []
    for ramo, _ in hp.ramos_activos:
        clave_ramo = str(ramo).strip()
        for nombre in INDICES + LAGS:
            hist = hp.historia.get((clave_ramo, nombre), {})
            fechas = [f for f, v in hist.items() if not math.isnan(v)]
            if not fechas:
                periodos, valores = [hp.ultimo], [math.nan]
            else:
                periodos = rango_periodos(min(fechas), hp.ultimo)
                valores = [hist.get(p, math.nan) for p in periodos]
            tipo = "indice" if nombre in INDICES else "lag"
            series.append(Serie(("HPARAM", HOJA_PARAMETROS, nombre, clave_ramo), tipo, periodos, valores,
                                ultimo, h, dominio=DOMINIO_LAG if tipo == "lag" else (None, None)))
    return series


def ajustar_orden_indices(hp: HParam, resultados: dict, alertas: list):
    """Si en la historia del ramo el 99.5% siempre ha sido >= la media, se respeta en la proyeccion."""
    for ramo, _ in hp.ramos_activos:
        clave_ramo = str(ramo).strip()
        for media, alto in PARES_MEDIA_995:
            hm = hp.historia.get((clave_ramo, media), {})
            ha = hp.historia.get((clave_ramo, alto), {})
            comunes = [f for f in hm if f in ha and not math.isnan(hm[f]) and not math.isnan(ha[f])]
            if not comunes or any(ha[f] < hm[f] for f in comunes):
                continue
            rm = resultados[("HPARAM", HOJA_PARAMETROS, media, clave_ramo)]
            ra = resultados[("HPARAM", HOJA_PARAMETROS, alto, clave_ramo)]
            cambios = 0
            for i, (vm, va) in enumerate(zip(rm.pronostico, ra.pronostico)):
                if not math.isnan(vm) and not math.isnan(va) and va < vm:
                    ra.pronostico[i] = vm
                    cambios += 1
            if cambios:
                alertas.append(("HPARAM", f"{alto} ramo {clave_ramo}",
                                f"{cambios} mes(es) ajustados para que {alto} >= {media}"))


def escribir_hparametros(hp: HParam, resultados: dict, periodos_proy: list[int]) -> int:
    ws = hp.ws
    relleno = PatternFill("solid", fgColor=COLOR_RESALTADO) if RESALTAR_PROYECCION else None
    ult_col = max(hp.cols.values())
    if ws.auto_filter and ws.auto_filter.ref:
        ult_col = max(ult_col, openpyxl.utils.column_index_from_string(
            re.match(r"[A-Z]+", ws.auto_filter.ref.split(":")[1]).group()))
    fila = ws.max_row + 1
    nuevas = 0
    for i, p in enumerate(periodos_proy):
        for ramo, plantilla in hp.ramos_activos:
            clave_ramo = str(ramo).strip()
            for col in range(1, ult_col + 1):
                _copiar_estilo(ws.cell(plantilla, col), ws.cell(fila, col))
            ws.cell(fila, hp.cols["Tipo de Indice"]).value = ETIQUETA_PROYECCION
            ws.cell(fila, hp.cols["Llave"]).value = f"{p}-{ramo}"
            ws.cell(fila, hp.cols["Fecha"]).value = p
            ws.cell(fila, hp.cols["Ramo"]).value = ramo
            for nombre in INDICES + LAGS:
                v = resultados[("HPARAM", HOJA_PARAMETROS, nombre, clave_ramo)].pronostico[i]
                celda = ws.cell(fila, hp.cols[nombre])
                celda.value = None if (v is None or math.isnan(v)) else float(v)
                if relleno and celda.value is not None:
                    celda.fill = relleno
            fila += 1
            nuevas += 1
    if ws.auto_filter and ws.auto_filter.ref:
        ini, fin = ws.auto_filter.ref.split(":")
        col_fin = re.match(r"[A-Z]+", fin).group()
        ws.auto_filter.ref = f"{ini}:{col_fin}{fila - 1}"
        for fc in ws.auto_filter.filterColumn:
            if fc.filters is not None and fc.filters.filter and TIPO_INDICE_BASE in fc.filters.filter \
                    and ETIQUETA_PROYECCION not in fc.filters.filter:
                fc.filters.filter.append(ETIQUETA_PROYECCION)
    return nuevas


# =============================================================================
# DIAGNOSTICO Y GRAFICAS
# =============================================================================
def escribir_diagnostico(resultados: dict, periodos_proy: list[int], alertas_generales: list, derivados: dict,
                         resumen: dict):
    wb = openpyxl.Workbook()
    negrita = Font(bold=True)
    encab = PatternFill("solid", fgColor="D9E1F2")

    ws = wb.active
    ws.title = "Resumen"
    lineas = [
        ("Proyeccion de indices y montos de reservas", ""),
        ("Fecha de ejecucion", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Periodos proyectados", f"{periodos_proy[0]} - {periodos_proy[-1]} ({len(periodos_proy)} meses)"),
        ("Ultimo mes real usado", str(resumen.get("ultimo"))),
        ("Series modeladas", str(len(resultados))),
        ("Ventana de tendencia (meses)", str(MESES_TENDENCIA) if MESES_TENDENCIA else "toda la historia"),
        ("Amortiguacion de la tendencia (phi)", str(AMORTIGUACION_TENDENCIA)),
        ("Estacionalidad mensual", (f"si, en {' e '.join(TIPOS_CON_ESTACIONALIDAD)}: patron por mes del ano con credibilidad "
                                    f"'{CREDIBILIDAD_ESTACIONAL}' ({DESCRIPCION_CREDIBILIDAD[CREDIBILIDAD_ESTACIONAL]}), "
                                    f"estimado sobre {'toda la historia' if MESES_ESTACIONALIDAD is None else 'los ultimos ' + str(MESES_ESTACIONALIDAD) + ' meses'} "
                                    f"(minimo {MIN_OBS_ESTACIONALIDAD} meses)") if ESTACIONALIDAD_MENSUAL else "no"),
        ("Moneda del modelo", ", ".join(f"{lib}: {'MXN (convertido con el TC de Inversiones)' if v else 'USD'}"
                                         for lib, v in MODELAR_EN_MXN.items())),
        ("Rango esperado", "; ".join(f"{lib} {c} (total de ramos): {texto_rango(a, b)}"
                                     for (lib, c), (a, b) in RANGO_ESPERADO.items()) or "sin rangos"),
        ("Ajuste por rango esperado", " | ".join(resumen.get("rangos") or []) or "no aplico"),
        ("Moneda mezclada corregida", ", ".join(f"{k}: {v} celdas convertidas de MXN a USD"
                                                for k, v in (resumen.get("moneda_corregida") or {}).items())
                                      or "no se detecto"),
        ("Pendiente proyectada", "montos y LAGs: la pendiente completa de la recta; indices: ponderada por su credibilidad "
                                 "(R2 ajustado de la recta)" if CREDIBILIDAD_PENDIENTE.get("indice") == "r2"
                                 else f"proporcion de la pendiente por tipo: {CREDIBILIDAD_PENDIENTE}"),
        ("Desviacion del ultimo mes", f"indices: se desvanece hacia el nivel promedio de los ultimos {MESES_NIVEL_LOCAL} meses con "
                                       f"persistencia {PERSISTENCIA_DESVIACION.get('indice', 1.0)}; montos y LAGs: se conserva "
                                       f"(persistencia {PERSISTENCIA_DESVIACION.get('nivel', 1.0)} / {PERSISTENCIA_DESVIACION.get('lag', 1.0)})"),
        ("Factor de prima", (resumen.get("factor") or {}).get("estado", "")
         + (f"; perfil mensual de la prima estimada: {resumen['primas'].perfil['elegido']}"
            if resumen.get("primas") is not None else "")),
        ("Factor de prima: decision", " | ".join(f"{d['Tipo']}: {d['Decision']} ({d['Configuracion']}; {d['Motivo']})"
                                                 for d in (resumen.get("factor") or {}).get("decision", [])) or "-"),
        ("Factor de prima: reservas NETO (M USD)", " | ".join(
            f"{f['Escenario']} {f['Reserva']}: " + ", ".join(f"{k[5:]} {v / 1e6:,.1f}" for k, v in f.items()
                                                           if k.startswith("Proy ") and v is not None)
            for f in (resumen.get("comparativo") or {}).get("filas", [])) or "-"),
        ("Tiempo de ejecucion (s)", f"{resumen.get('segundos', 0):,.0f}"),
        ("", ""),
        ("METODOLOGIA", ""),
        ("1. Coherencia contable", "Se proyectan drivers (BEL / BRUTO y razones) y se derivan las demas lineas: "
                                   "RRC: BRUTO = BEL+GTO+MR, IRR = %ces*BRUTO, NETO = BRUTO-IRR; SONR: BRUTO = BEL+MR; "
                                   "RFV: NETO = BRUTO-IRR; RCONT: total repartido por ramo con la mezcla de los "
                                   "ultimos 8 meses."),
        ("2. Modelo", "Montos, indices y LAGs: linea de tendencia historica (regresion lineal, en logaritmos cuando "
                      f"la serie es positiva) sobre los ultimos {MESES_TENDENCIA or 'N/A'} meses, continuada desde el "
                      "ultimo dato real: la proyeccion sale paralela a la linea de tendencia de Excel y arranca del "
                      "ultimo real. En montos e indices se suma ademas el patron por mes del ano (estacionalidad "
                      "mensual: promedio, por mes del ano, de la serie menos su media movil centrada de 12 meses, sobre "
                      f"{'toda la historia' if MESES_ESTACIONALIDAD is None else 'los ultimos ' + str(MESES_ESTACIONALIDAD) + ' meses'}, "
                      f"ponderado por su credibilidad: {DESCRIPCION_CREDIBILIDAD[CREDIBILIDAD_ESTACIONAL]}; con menos de "
                      f"{MIN_OBS_ESTACIONALIDAD} meses no se estima): proyeccion = ultimo real sin su factor del mes + "
                      "pendiente x meses + factor del mes proyectado, asi que repite los picos y valles del ano en la "
                      "medida en que se han repetido. En los indices (razones que se mueven en una banda y rebotan) la "
                      "desviacion del ultimo mes respecto a la recta no se conserva: converge al nivel promedio del "
                      f"ultimo ano con persistencia {PERSISTENCIA_DESVIACION.get('indice', 1.0)} por mes, y la pendiente "
                      "se proyecta ponderada por su credibilidad (R2 ajustado de la recta: una pendiente que la recta "
                      "explica poco casi no se extrapola); en montos y LAGs la desviacion se conserva (arrancan del "
                      "ultimo real) y la pendiente se proyecta completa. Razones (%GTO, %MR, %cedido): SES (nivel sin "
                      "tendencia). RCONT: "
                      f"{MODELO_TRIMESTRAL} (estacionalidad por mes del trimestre) si hay al menos "
                      f"{MIN_OBS_TRIMESTRAL} meses; con menos, SES (nivel). Series cortas: SES (< 6 obs para la tendencia) o ultimo valor (< 4). "
                      "Los conceptos derivados (NETO, BRUTO de Danos, IRR, GTO, MR) y los totales por ramo no siguen "
                      "una recta propia: salen de las identidades y de la suma de ramos."),
        ("3. Parametros", f"Tendencia: pendiente de la regresion (columna 'Tendencia mensual' de Series_Modelos, en "
                          f"% mensual cuando la serie va en logaritmos), ventana usada y R2. Amortiguacion phi = "
                          f"{AMORTIGUACION_TENDENCIA} (1 = constante; con 0.95 cada mes conserva 95%). Estacionalidad: "
                          "hoja Estacionalidad (factor aplicado por mes del ano, credibilidad, R2 del mes del ano y p de "
                          "la prueba F; columnas 'Credibilidad estacional' y 'Amplitud estacional' de Series_Modelos; "
                          "amplitud = (1 + factor del mes mas alto) / (1 + factor del mes mas bajo) - 1). "
                          "Modelos de "
                          "suavizamiento (SES, Holt, Holt-Winters): alpha, beta, phi y gamma por maxima verosimilitud "
                          + f"dentro de {COTAS_SUAVIZAMIENTO} (RCONT alpha >= 0.2; SES alpha libre)."),
        ("4. Backtest", "Cada serie se vuelve a proyectar desde 16, 12 y 8 meses antes del final (horizontes de 1 a "
                        "16 meses, con al menos 12 meses de entrenamiento) y se mide el error % (suma de errores "
                        "absolutos / suma de valores reales) del modelo, de repetir el ultimo valor y de SES. Hoja "
                        "Backtest: resumen por tipo; Series_Modelos: por serie. Fianzas (20 meses de historia) solo "
                        "alcanza el corte a 8 meses: indicativo. Sirve para juzgar la confiabilidad; no cambia el "
                        "modelo, salvo en el factor de prima (8), donde decide entre la recta y el factor."),
        ("5. Intervalos", f"{NIVEL_INTERVALO:.0%}, calculados por el propio modelo (en logaritmos para montos e "
                          "indices, por lo que son asimetricos)."),
        ("6. Reglas", "Series en cero -> 0; parametros en escalon -> ultimo valor; dominio actuarial (cesion en "
                      "[0,1], %GTO y %MR >= 0, LAGs >= 0); 99.5% >= media si siempre lo fue; limpieza de textos "
                      "y LAG=0 marcadores; alertas de saltos atipicos y de cambios mayores a los historicos."),
        ("7. Tipo de cambio", "Columna TC = supuesto de Inversiones (TC_Real_Esti.xlsx, hoja TC: FCST 2026 y "
                              "FCST 2027), en tipo_cambio.py; los meses reales = TC real de SAP. "
                              + "; ".join(f"{lib}: se modela en {'MXN y se convierte a USD con el TC de cada mes proyectado, asi que el TC si mueve las cifras en USD' if v else 'USD, asi que el TC no altera las cifras proyectadas'}"
                                          for lib, v in MODELAR_EN_MXN.items()) + "."),
        ("8. Factor de prima", "Si en entradas/ estan las bases de primas (real historico, real del ano, reforecast y "
                               "presupuesto; primas.py), RRC BEL y SONR BEL de Danos por ramo y RFV BRUTO de Fianzas se "
                               "escriben como factor mensual x exposicion de prima del grupo de ramo: RRC con la prima no "
                               "devengada en 24avos (PND12), SONR con la prima devengada de los ultimos anos por la parte "
                               "pendiente de reportar segun los LAG (PDP), RFV con la prima de 12 meses en pesos. El "
                               "factor se proyecta con la recta de 36 meses y su patron del mes, sin pendiente "
                               f"(PENDIENTES_FACTOR = {PENDIENTES_FACTOR}) y anclado a su ultimo valor; su error como "
                               "AR(1) (rho) es el 'factor de error' y su persistencia compite en la rejilla. Por tipo de "
                               "reserva el backtest decide entre la recta, el factor o la combinacion 50/50: con la prima "
                               "real en los cortes estandar y con el presupuesto del ano en curso (sus meses tal cual) en "
                               "un corte propio en diciembre del ano anterior (configuracion y decision en 'Factor de "
                               "prima: decision' y en Factor_Prima_Resumen). La prima del resto del ano sale del "
                               "reforecast repartido por contrato, cedente y LN; la del ano siguiente, del total del "
                               "presupuesto por grupo repartido a meses con el perfil elegido (el mes a mes del CSV solo "
                               "si el perfil es 'presupuesto'); controles en Primas_Controles."),
        ("Versiones", resumen.get("versiones", "")),
    ]
    for i, (a, b) in enumerate(lineas, start=1):
        ws.cell(i, 1, a).font = negrita if a and b == "" or a in ("METODOLOGIA",) else Font()
        ws.cell(i, 2, b).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 120
    fila = ws.max_row + 2
    ws.cell(fila, 1, "MODELO POR TIPO DE SERIE").font = negrita
    for i, (tipo, nombre) in enumerate(MODELO_POR_TIPO.items(), start=1):
        ws.cell(fila + i, 1, tipo)
        ws.cell(fila + i, 2, nombre)

    # Backtest por tipo
    ws = wb.create_sheet("Backtest")
    tabla = resumen_backtest(resultados)
    cols = ["Tipo", "Libro", "Modelo", "Series con backtest", "Cortes por serie (mediana)", "Error % modelo (mediana)",
            "Error % ultimo valor (mediana)", "Error % SES (mediana)", "% series en que el modelo mejora al ultimo valor"]
    ws.append(cols)
    for d in tabla:
        ws.append([d.get(c) for c in cols])
    _formato_tabla(ws, negrita, encab)
    for fila_ in ws.iter_rows(min_row=2):
        for c in fila_:
            enc_ = ws.cell(1, c.column).value
            if enc_.startswith("Error %"):
                c.number_format = "0.0"
            elif enc_.startswith("% series"):
                c.number_format = "0%"
    nota = ws.max_row + 2
    for i, texto in enumerate([
        "Error % = suma de errores absolutos / suma de valores reales, re-proyectando desde 16, 12 y 8 meses antes "
        "del final (horizontes 1-16, minimo 12 meses de entrenamiento). Mediana entre series del tipo y libro. "
        "FIANZAS tiene 20 meses de historia: un solo corte (a 8 meses), indicativo.",
        "El modelo elegido continua la tendencia observada" + (" (amortiguada)" if AMORTIGUACION_TENDENCIA < 1 else "")
        + ". Continuar una recta 16 meses cuesta precision frente a repetir el ultimo valor; el costo queda aqui a la vista.",
    ]):
        ws.cell(nota + i, 1, texto)

    # Series y modelos
    ws = wb.create_sheet("Series_Modelos")
    cab = ["Libro", "Grupo", "Serie", "Ramo", "Tipo", "Moneda modelo", "Transformacion", "Obs", "Desde", "Regla",
           "Modelo", "Ventana (meses)", "R2 tendencia", "Ajuste tendencia ultimo mes", "Credibilidad estacional",
           "Amplitud estacional", "Persistencia desviacion", "Desviacion ultimo mes vs recta", "Nivel ultimo ano vs recta",
           "Credibilidad pendiente", "Pendiente aplicada", "alpha", "beta", "phi", "gamma",
           "Tendencia mensual",
           "Cortes backtest", "Error % modelo",
           "Error % ultimo valor", "Error % SES", "Ultimo real", f"Proy {periodos_proy[0]}",
           f"Proy {periodos_proy[-1]}", "Var % vs ultimo real", "Alertas", "Factor de prima (decision)",
           "Driver de prima", "Recta alternativa (ultimo mes)", "Error % recta (alternativa)"]
    ws.append(cab)

    def num(v):
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else v

    def _amplitud(r):
        a = r.parametros.get("amplitud_estacional")
        if a is None:
            return None
        return math.expm1(a) if r.transformacion == "log" else a

    def _en_escala(r, clave):
        """Parametro en la escala del modelo convertido a % si la serie va en logaritmos."""
        a = r.parametros.get(clave)
        if a is None:
            return None
        return math.expm1(a) if r.transformacion == "log" else a

    for k, r in sorted(resultados.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        ult = r.historia_valores[-1] if r.historia_valores else math.nan
        fin = r.pronostico[-1] if r.pronostico else math.nan
        var = (fin / ult - 1) if (ult and not math.isnan(ult) and not math.isnan(fin) and ult != 0) else None
        fila_ = [k[0], k[1], k[2], k[3], r.tipo, r.moneda, r.transformacion, r.n_obs,
                 r.historia_periodos[0] if r.historia_periodos else None, r.regla, r.modelo or None,
                 r.parametros.get("ventana"), num(r.parametros.get("r2")), num(r.parametros.get("ajuste_ultimo")),
                 num(r.parametros.get("credibilidad_estacional")), _amplitud(r),
                 num(r.parametros.get("phi_desviacion")), _en_escala(r, "desviacion_ultimo"), _en_escala(r, "nivel_local"),
                 num(r.parametros.get("credibilidad_pendiente")), _en_escala(r, "pendiente_aplicada"),
                 num(r.parametros.get("alpha")), num(r.parametros.get("beta")), num(r.parametros.get("phi")),
                 num(r.parametros.get("gamma")), num(r.tendencia_mensual), r.n_cortes or None,
                 num(r.error_modelo), num(r.error_ultimo_valor), num(r.error_ses), num(ult),
                 None if not r.pronostico or math.isnan(r.pronostico[0]) else r.pronostico[0],
                 num(fin), var, " | ".join(r.alertas), r.factor.get("decision"), r.factor.get("driver"),
                 num(r.factor["pron_recta"][-1]) if r.factor.get("pron_recta") else None,
                 num(r.factor.get("error_recta")) if r.factor.get("pron_recta") else None]
        ws.append(fila_)
    _formato_tabla(ws, negrita, encab)
    for fila_ in ws.iter_rows(min_row=2):
        for c in fila_:
            enc_ = ws.cell(1, c.column).value
            if enc_ in ("Tendencia mensual", "Pendiente aplicada") and isinstance(c.value, float):
                c.number_format = "0.00%" if fila_[6].value == "log" else "0.0000"
            elif enc_ in ("alpha", "beta", "phi", "gamma", "R2 tendencia", "Credibilidad estacional") and isinstance(c.value, float):
                c.number_format = "0.000"
            elif enc_ in ("Amplitud estacional", "Desviacion ultimo mes vs recta", "Nivel ultimo ano vs recta") and isinstance(c.value, float):
                c.number_format = "0.0%" if fila_[6].value == "log" else "0.0000"
            elif enc_ in ("Persistencia desviacion", "Credibilidad pendiente") and isinstance(c.value, float):
                c.number_format = "0.00"
            elif enc_ and enc_.startswith("Error %") and isinstance(c.value, float):
                c.number_format = "0.0"

    # Estacionalidad: patron por mes del ano aplicado a cada serie (en % si la serie va en logaritmos)
    ws = wb.create_sheet("Estacionalidad")
    meses_nombre = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    ws.append(["Libro", "Grupo", "Serie", "Ramo", "Transformacion", "Obs sin tendencia", "p (prueba F del mes del ano)",
               "R2 del mes del ano", "Credibilidad aplicada", "Amplitud aplicada (mes mas alto / mes mas bajo - 1)"]
              + meses_nombre)
    for k, r in sorted(resultados.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        pe = r.parametros
        if "estacional" not in pe:
            continue
        log_ = r.transformacion == "log"
        conv = (lambda v: math.expm1(v)) if log_ else (lambda v: v)
        ws.append([k[0], k[1], k[2], k[3], r.transformacion, pe.get("obs_estacional"), num(pe.get("p_estacional")),
                   num(pe.get("r2_estacional")), num(pe.get("credibilidad_estacional")), _amplitud(r)]
                  + [conv(v) for v in pe["estacional"]])
    _formato_tabla(ws, negrita, encab)
    for fila_ in ws.iter_rows(min_row=2):
        log_ = fila_[4].value == "log"
        for c in fila_[6:]:
            if isinstance(c.value, float):
                enc_ = ws.cell(1, c.column).value
                c.number_format = "0.000" if enc_ in ("p (prueba F del mes del ano)", "R2 del mes del ano", "Credibilidad aplicada") \
                    else ("0.0%" if log_ else "0.0000")
    ws.cell(ws.max_row + 2, 1, "Factor aplicado = promedio por mes del ano de la serie sin tendencia (media movil centrada "
            f"de 12 meses, {'toda la historia' if MESES_ESTACIONALIDAD is None else 'ultimos ' + str(MESES_ESTACIONALIDAD) + ' meses'}), "
            f"centrado en cero y ponderado por la credibilidad ({DESCRIPCION_CREDIBILIDAD[CREDIBILIDAD_ESTACIONAL]}; "
            "0 = el mes no explica nada y no se aplica patron). En % cuando la serie se modela en logaritmos. "
            "Amplitud = (1 + factor del mes mas alto) / (1 + factor del mes mas bajo) - 1. Proyeccion = ultimo real sin su "
            "factor del mes + pendiente de la tendencia x meses + factor del mes proyectado (paralela a la recta de "
            "tendencia, anclada al ultimo real).")

    # Contraste con el presupuesto (si se leyo)
    filas_ppto = resumen.get("presupuesto") or []
    if filas_ppto:
        ws = wb.create_sheet("Contraste_Presupuesto")
        cab_p = list(filas_ppto[0])
        ws.append(cab_p)
        for f in filas_ppto:
            ws.append([f.get(c) for c in cab_p])
        _formato_tabla(ws, negrita, encab)
        for fila_ in ws.iter_rows(min_row=2):
            for c in fila_:
                enc_ = str(ws.cell(1, c.column).value)
                if enc_.startswith("Crec.") and isinstance(c.value, float):
                    c.number_format = "+0.0%;-0.0%;0.0%"
                elif enc_.startswith("Diferencia") and isinstance(c.value, (int, float)):
                    c.number_format = "+0.0;-0.0;0.0"
                elif enc_.startswith("Reserva / referencia") and isinstance(c.value, float):
                    c.number_format = "0.00"
                elif isinstance(c.value, float):
                    c.number_format = "#,##0"
        nota = ws.max_row + 2
        for i, texto in enumerate([
            f"Fuente del presupuesto: {resumen.get('archivo_presupuesto', '')} (vista tomado, USD). Reservas: total NETO de "
            "todos los ramos a diciembre (real si ya paso, proyectado si no).",
            "Referencia: RRC contra primas tomadas y SONR contra siniestros tomados de Danos (total menos las lineas de "
            f"Fianzas {', '.join(LINEAS_FIANZAS_PPTO)} y menos las lineas nuevas sin base en el ano en curso"
            + (f": {', '.join(resumen.get('lineas_nuevas_presupuesto') or [])}" if resumen.get('lineas_nuevas_presupuesto') else "")
            + "); RFV contra las primas de las lineas de Fianzas. Las lineas nuevas se excluyen porque la reserva proyectada "
            "por tendencia no puede traer ese negocio; su efecto se ve en la columna 'con lineas nuevas'. Las lineas cambiaron "
            "de clasificacion entre el ano anterior y el actual, asi que el crecimiento de la referencia del ano en curso no es "
            "comparable; el contraste util es el del ultimo ano.",
            "Si la razon reserva / referencia se mantiene estable, la reserva crece en proporcion al negocio. No cambia la "
            f"proyeccion; una diferencia mayor a {TOLERANCIA_PRESUPUESTO * 100:.0f} pts queda en Alertas.",
        ]):
            ws.cell(nota + i, 1, texto)

    # Celdas de la historia convertidas de MXN a USD (monedas mezcladas)
    celdas = resumen.get("celdas_moneda") or {}
    if any(celdas.values()):
        ws = wb.create_sheet("Moneda_corregida")
        ws.append(["Libro", "Concepto", "Periodo", "Ramo", "Valor en la BD (MXN)", "TC", "Valor usado (USD)"])
        for libro, lista in celdas.items():
            for c, p, r, original, nuevo, tc in lista:
                ws.append([libro, c, p, r, original, tc, nuevo])
        _formato_tabla(ws, negrita, encab)
        for fila_ in ws.iter_rows(min_row=2):
            fila_[4].number_format = "#,##0.00"
            fila_[6].number_format = "#,##0.00"

    # Pronosticos (drivers con intervalos)
    ws = wb.create_sheet("Pronosticos_Drivers")
    ws.append(["Libro", "Grupo", "Serie", "Ramo", "Moneda", "Periodo", "Pronostico", f"LI {NIVEL_INTERVALO:.0%}",
               f"LS {NIVEL_INTERVALO:.0%}"])
    for k, r in sorted(resultados.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        for i, p in enumerate(periodos_proy):
            v = r.pronostico[i]
            if v is None or math.isnan(v):
                continue
            ws.append([k[0], k[1], k[2], k[3], r.moneda or "-", p, v, r.li[i], r.ls[i]])
    _formato_tabla(ws, negrita, encab)

    # Montos derivados (lo que se escribio en las BD)
    ws = wb.create_sheet("Montos_Proyectados")
    ws.append(["Libro", "Concepto", "Periodo", "Ramo", "Valor USD"])
    for libro, dic in derivados.items():
        for (c, p, ramo), v in sorted(dic.items()):
            ws.append([libro, c, p, ramo, v])
    _formato_tabla(ws, negrita, encab)

    _hojas_primas(wb, resumen, negrita, encab)

    ws = wb.create_sheet("Alertas")
    ws.append(["Libro", "Serie / Elemento", "Detalle"])
    for a in alertas_generales:
        ws.append(list(a))
    for k, r in sorted(resultados.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        for a in r.alertas:
            ws.append([k[0], f"{k[1]} | {k[2]} | ramo {k[3]}", a])
    _formato_tabla(ws, negrita, encab)
    guardar_libro(wb, SALIDA_DIAGNOSTICO)


def _hoja_filas(wb, nombre: str, filas: list, negrita, encab, formatos: dict | None = None):
    """Hoja con una tabla (lista de dicts); formatos = {prefijo de encabezado: number_format}."""
    ws = wb.create_sheet(nombre)
    if not filas:
        ws.append(["(sin datos)"])
        return ws
    cab = []
    for f in filas:
        for c in f:
            if c not in cab:
                cab.append(c)
    ws.append(cab)
    for f in filas:
        ws.append([_celda(f.get(c)) for c in cab])
    _formato_tabla(ws, negrita, encab)
    _formatear(ws, 1, formatos)
    return ws


def _celda(v):
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (list, tuple, dict, set)):
        return str(v)
    return v


def _formatear(ws, fila_enc: int, formatos: dict | None, fila_fin: int | None = None):
    formatos = formatos or {}
    fin = fila_fin or ws.max_row
    for c in range(1, ws.max_column + 1):
        enc_ = str(ws.cell(fila_enc, c).value or "")
        fmt = next((f for pref, f in formatos.items() if enc_.startswith(pref)), None)
        if fmt is None:
            continue
        for r in range(fila_enc + 1, fin + 1):
            if isinstance(ws.cell(r, c).value, (int, float)):
                ws.cell(r, c).number_format = fmt


def _hojas_primas(wb, resumen: dict, negrita, encab):
    """Hojas del factor de prima: controles de las bases de primas, prima mensual por grupo, decision y rejilla por
    tipo de reserva, detalle por serie, factor mensual y backtest."""
    pr, diag, comp = resumen.get("primas"), resumen.get("factor") or {}, resumen.get("comparativo") or {}
    formato_pct = {"Crec.": "+0.0%;-0.0%;0.0%", "Crecimiento": "+0.0%;-0.0%;0.0%", "%": "0.0%", "Cobertura": "0%",
                   "Diferencia": "+0.0%;-0.0%;0.0%", "Error": "0.0", "Recta (A)": "0.0", "Factor": "0.0",
                   "Combinacion": "0.0", "Sigma": "0.00", "S/P": "0.0%", "C/P": "0.0%"}
    if pr is not None:
        ws = wb.create_sheet("Primas_Controles")
        fila = 1
        bloques = [("Controles por archivo", pd.DataFrame(pr.controles))] + list(pr.tablas.items())
        bloques.append(("Avisos", pd.DataFrame({"Aviso": pr.avisos or ["(ninguno)"]})))
        for titulo, tabla in bloques:
            ws.cell(fila, 1, titulo).font = negrita
            fila += 1
            if tabla is None or not len(tabla):
                ws.cell(fila, 1, "(sin datos)")
                fila += 2
                continue
            enc_fila = fila
            for j, c in enumerate(tabla.columns, start=1):
                ws.cell(fila, j, str(c)).font = negrita
                ws.cell(fila, j).fill = encab
            for reg in tabla.itertuples(index=False):
                fila += 1
                for j, v in enumerate(reg, start=1):
                    ws.cell(fila, j, _celda(v))
            _formatear(ws, enc_fila, {**formato_pct, "Prima": "#,##0.00", "Real": "#,##0.00", "Presupuesto": "#,##0.00",
                                      "CSV": "#,##0.00", "Referencia": "#,##0.00", "Ano 20": "#,##0.00",
                                      "Historico": "#,##0.00", "Resto": "#,##0.00", "Completado": "#,##0.00",
                                      "Reforecast": "#,##0.00", "20": "#,##0.00", "1": "#,##0.00", "3": "#,##0.00",
                                      "4": "#,##0.00", "5": "#,##0.00", "6": "#,##0.00", "7": "#,##0.00",
                                      "8": "#,##0.00", "9": "#,##0.00"}, fila)
            fila += 2
        ws.column_dimensions["A"].width = 30
        # prima mensual por grupo con sus drivers
        filas = []
        for g in pr.mensual.columns:
            p = pr.mensual[g]
            drivers = {n: primas.exposicion(p, n) for n in ("P12", "PND12", "P24", "P36", "PD12")}
            for per, v in p.items():
                filas.append({"Periodo": int(per), "Grupo": g, "Prima USD": float(v), "Fuente": pr.fuente.at[per, g],
                              **{f"{n} USD": _celda(float(d.get(per, math.nan))) for n, d in drivers.items()}})
        _hoja_filas(wb, "Primas_Mensual", filas, negrita, encab, {"Prima": "#,##0", "P": "#,##0"})
    if diag.get("decision") or diag.get("series"):
        ws = wb.create_sheet("Factor_Prima_Resumen")
        fila = 1
        bloques = [("Estado", [{"Factor de prima": diag.get("estado", "")}]),
                   ("Decision por tipo de reserva (error % del backtest agrupado)", diag.get("decision")),
                   ("Rejilla de configuraciones (error % del factor con la prima real, mismos casos)", diag.get("rejilla")),
                   ("Reservas NETO totales (USD): modelo final (con el ajuste por RANGO_ESPERADO) contra el mismo "
                    "sin ese ajuste, la recta y la sensibilidad a la prima del ano siguiente (estas tres sin el ajuste)",
                    comp.get("filas")),
                   ("Detalle por serie", diag.get("series"))]
        for titulo, filas in bloques:
            ws.cell(fila, 1, titulo).font = negrita
            fila += 1
            if not filas:
                ws.cell(fila, 1, "(sin datos)")
                fila += 2
                continue
            cab = []
            for f in filas:
                cab += [c for c in f if c not in cab]
            for j, c in enumerate(cab, start=1):
                ws.cell(fila, j, c).font = negrita
                ws.cell(fila, j).fill = encab
                ws.cell(fila, j).alignment = Alignment(wrap_text=True, vertical="center")
            enc_fila = fila
            for f in filas:
                fila += 1
                for j, c in enumerate(cab, start=1):
                    ws.cell(fila, j, _celda(f.get(c)))
            _formatear(ws, enc_fila, {**formato_pct, "Real": "#,##0", "Proy": "#,##0", "Recta ": "#,##0",
                                      "Factor de prima 2": "#,##0", "Final": "#,##0", "Factor al": "0.000",
                                      "Rho": "0.00", "Persistencia usada": "0.00", "R2": "0.00",
                                      "Elasticidad": "0.00", "Pendiente aplicada": "0.00%",
                                      "Pendiente observada": "0.00%"}, fila)
            fila += 2
        ws.column_dimensions["A"].width = 26
        _hoja_filas(wb, "Factor_Mensual", diag.get("mensual") or [], negrita, encab,
                    {"Valor": "#,##0", "Reserva": "#,##0", "Factor": "0.0000", "%": "0.0%"})
        _hoja_filas(wb, "Backtest_Primas", diag.get("backtest") or [], negrita, encab,
                    {"Recta": "0.0", "Factor": "0.0", "Combinacion": "0.0"})


def _formato_tabla(ws, negrita, encab):
    for c in ws[1]:
        c.font = negrita
        c.fill = encab
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in range(1, ws.max_column + 1):
        letra = get_column_letter(col)
        largo = max((len(str(c.value)) for c in ws[letra][:200] if c.value is not None), default=8)
        ws.column_dimensions[letra].width = min(max(10, largo + 2), 60)
    for fila in ws.iter_rows(min_row=2):
        for c in fila:
            if isinstance(c.value, float):
                c.number_format = "0.0%" if ws.cell(1, c.column).value == "Var % vs ultimo real" else (
                    "#,##0.0000" if abs(c.value) < 100 else "#,##0")


def graficar(resultados: dict, derivados: dict, historia_montos: dict, periodos_proy: list[int]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    def fechas(ps):
        return [datetime(p // 100, p % 100, 1) for p in ps]

    with PdfPages(SALIDA_GRAFICAS) as pdf:
        # 1) Montos: un concepto por pagina, un panel por ramo
        for libro, dic in derivados.items():
            conceptos = sorted({c for (c, _, _) in dic})
            ramos = sorted({r for (_, _, r) in dic}, key=lambda x: (len(x), x))
            for c in conceptos:
                fig, ejes = plt.subplots(int(math.ceil(len(ramos) / 4)), 4, figsize=(16, 10), squeeze=False)
                for ax, ramo in zip(ejes.flat, ramos):
                    hist = historia_montos[libro]
                    ph = sorted(p for (cc, p, rr) in hist if cc == c and rr == ramo)
                    ax.plot(fechas(ph), [hist[(c, p, ramo)] / 1e6 for p in ph], color="#1f4e79", lw=1.4)
                    ax.plot(fechas(periodos_proy), [dic[(c, p, ramo)] / 1e6 for p in periodos_proy],
                            color="#c55a11", lw=1.6, ls="--")
                    ax.set_title(f"RAM_{ramo}", fontsize=9)
                    ax.tick_params(labelsize=7)
                for ax in list(ejes.flat)[len(ramos):]:
                    ax.axis("off")
                fig.suptitle(f"{libro} - {c} (millones USD)   azul: real   naranja: proyeccion", fontsize=12)
                fig.tight_layout()
                pdf.savefig(fig)
                plt.close(fig)
        # 2) Drivers con intervalo (niveles e indices)
        grupos = {}
        for k, r in resultados.items():
            if r.tipo in ("nivel", "indice", "razon"):
                grupos.setdefault((k[0], k[1], k[2]), []).append(r)
        for (libro, grupo, serie), lista in sorted(grupos.items()):
            lista = sorted(lista, key=lambda r: (len(r.clave[3]), r.clave[3]))
            fig, ejes = plt.subplots(int(math.ceil(len(lista) / 4)), 4, figsize=(16, 10), squeeze=False)
            for ax, r in zip(ejes.flat, lista):
                if r.historia_periodos:
                    ax.plot(fechas(r.historia_periodos), r.historia_valores, color="#1f4e79", lw=1.3)
                pr = np.array(r.pronostico, dtype=float)
                if np.any(~np.isnan(pr)):
                    ax.plot(fechas(periodos_proy), pr, color="#c55a11", lw=1.5, ls="--")
                    ax.fill_between(fechas(periodos_proy), r.li, r.ls, color="#f4b183", alpha=0.35, lw=0)
                ax.set_title(f"{r.clave[3]}: {r.modelo or r.regla}"[:60], fontsize=7)
                ax.tick_params(labelsize=6)
            for ax in list(ejes.flat)[len(lista):]:
                ax.axis("off")
            fig.suptitle(f"{libro} | {grupo} | {serie}  (banda {NIVEL_INTERVALO:.0%})", fontsize=12)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
        # 3) LAGs por ramo
        lags_ramo = {}
        for k, r in resultados.items():
            if r.tipo == "lag":
                lags_ramo.setdefault(k[3], []).append(r)
        for ramo, lista in sorted(lags_ramo.items(), key=lambda kv: (len(kv[0]), kv[0])):
            fig, ax = plt.subplots(figsize=(14, 7))
            for r in sorted(lista, key=lambda r: int(r.clave[2].split()[-1])):
                if r.historia_periodos:
                    linea, = ax.plot(fechas(r.historia_periodos), r.historia_valores, lw=1.1, label=r.clave[2])
                    ax.plot(fechas(periodos_proy), r.pronostico, lw=1.3, ls="--", color=linea.get_color())
            ax.set_title(f"HParametros - LAGs ramo {ramo} (continua: real, punteada: proyeccion)")
            ax.legend(fontsize=7, ncol=5)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)


# =============================================================================
# PROCESO PRINCIPAL
# =============================================================================
def _versiones() -> str:
    from importlib.metadata import PackageNotFoundError, version
    partes = [f"Python {sys.version.split()[0]}"]
    for paquete in ("openpyxl", "numpy", "pandas", "scipy", "statsmodels", "matplotlib"):
        try:
            partes.append(f"{paquete} {version(paquete)}")
        except PackageNotFoundError:
            continue
    return ", ".join(partes)


UMBRAL_CIFRA = 1.0   # USD; debajo es ruido de redondeo de SAP (p.ej. 3e-12) y cuenta como cero


def revisar_periodos(bd: BDMontos, nombre: str, ultimo: int, periodos_proy: list[int], alertas: list):
    """Evita proyectar sobre cifras reales y usar un mes historico vacio como si fuera cero real."""
    con_datos = sorted({p for (c, p, r), v in bd.valores.items() if p in periodos_proy and abs(v) > UMBRAL_CIFRA})
    if con_datos and not SOBRESCRIBIR_PERIODOS_CON_DATOS:
        raise SystemExit(f"{nombre}: los meses {con_datos} ya tienen cifras (reales?) y se sobrescribirian con la "
                         f"proyeccion. Mueve PERIODO_INICIO al mes siguiente al ultimo real o pon "
                         f"SOBRESCRIBIR_PERIODOS_CON_DATOS = True.")
    previo = indice_a_periodo(periodo_a_indice(ultimo) - 1)
    incompletos = []
    for concepto in bd.conceptos:
        tenia = any(abs(bd.valores.get((concepto, previo, r), 0.0)) > UMBRAL_CIFRA for r in bd.cols_ramo)
        tiene = any(abs(bd.valores.get((concepto, ultimo, r), 0.0)) > UMBRAL_CIFRA for r in bd.cols_ramo)
        if tenia and not tiene:
            incompletos.append(concepto)
    if incompletos:
        raise SystemExit(f"{nombre}: el mes {ultimo} (ultimo real, PERIODO_INICIO - 1) no tiene cifras en "
                         f"{incompletos}, aunque {previo} si. Carga ese mes completo o ajusta PERIODO_INICIO.")
    for concepto in bd.conceptos:            # un ramo que se quedo en cero puede ser real (cartera extinta)
        for r in bd.cols_ramo:
            if (abs(bd.valores.get((concepto, previo, r), 0.0)) > UMBRAL_CIFRA
                    and abs(bd.valores.get((concepto, ultimo, r), 0.0)) <= UMBRAL_CIFRA):
                alertas.append((nombre, f"{concepto} RAM_{r}", f"Tiene cifra en {previo} y 0 en {ultimo} (ultimo real): "
                                                               "confirma que el mes esta completo"))
    if not any(abs(v) > UMBRAL_CIFRA for (c, p, r), v in bd.valores.items() if p <= ultimo):
        raise SystemExit(f"{nombre}: la historia esta vacia (todo en cero).")


def main():
    t0 = time.time()
    SALIDAS.mkdir(parents=True, exist_ok=True)
    periodos_proy = rango_periodos(PERIODO_INICIO, PERIODO_FIN)
    ultimo = indice_a_periodo(periodo_a_indice(PERIODO_INICIO) - 1)
    h = len(periodos_proy)
    print(f"Proyeccion {periodos_proy[0]} - {periodos_proy[-1]} ({h} meses). Historia hasta {ultimo}.", flush=True)
    for ruta in (ARCHIVO_BD_DANOS, ARCHIVO_BD_RFV):
        if not ruta.exists():
            raise SystemExit(f"Falta {ruta}: copia la BD (Fianzas ya llena) a la carpeta entradas/.")
    salidas = ([SALIDA_BD_DANOS, SALIDA_BD_RFV, SALIDA_DIAGNOSTICO] + ([SALIDA_GRAFICAS] if GENERAR_GRAFICAS else [])
               + ([SALIDA_DASHBOARD, SALIDA_DASHBOARD_HTML] if GENERAR_DASHBOARD else []))
    verificar_escritura(salidas)
    for ruta in (ARCHIVO_BD_DANOS, ARCHIVO_BD_RFV):
        print(f"   Entrada: {ruta.name} ({datetime.fromtimestamp(ruta.stat().st_mtime):%Y-%m-%d %H:%M})", flush=True)

    alertas = []
    print("Leyendo archivos ...", flush=True)
    bd_danos = leer_bd_montos(ARCHIVO_BD_DANOS)
    bd_rfv = leer_bd_montos(ARCHIVO_BD_RFV)
    correcciones = {"DANOS": [], "FIANZAS": []}
    if CORREGIR_MONEDA_MEZCLADA:
        correcciones = {"DANOS": corregir_moneda_mezclada(bd_danos, "DANOS", ultimo, alertas),
                        "FIANZAS": corregir_moneda_mezclada(bd_rfv, "FIANZAS", ultimo, alertas)}
    revisar_periodos(bd_danos, "BD Daños", ultimo, periodos_proy, alertas)
    revisar_periodos(bd_rfv, "BD RFV", ultimo, periodos_proy, alertas)
    hp = leer_hparametros(bd_danos.wb)
    if hp.ultimo > ultimo:
        raise SystemExit(f"{HOJA_PARAMETROS}: ya hay renglones '{TIPO_INDICE_BASE}' de {hp.ultimo}, posteriores a "
                         f"{ultimo}. Mueve PERIODO_INICIO.")
    if hp.ultimo < ultimo:
        alertas.append(("HPARAM", "Ultimo mes Real", f"El ultimo '{TIPO_INDICE_BASE}' es {hp.ultimo}; los indices "
                                                     f"se proyectan desde ahi hasta cubrir {periodos_proy[0]}"))
    if hp.textos_limpiados:
        alertas.append(("HPARAM", "Limpieza", f"{hp.textos_limpiados} celdas con numeros guardados como texto "
                                              "(p.ej. espacios \\xa0) se convirtieron a numero"))
    for fecha, ramo, lag in hp.lags_cero:
        alertas.append(("HPARAM", f"{lag} ramo {ramo}", f"{fecha}: valor 0 tratado como faltante "
                                                        "(el patron acumulado ya superaba 50%)"))

    # Revision de identidades en la historia (deben cumplirse para que la derivacion sea valida)
    for libro, bd in (("DANOS", bd_danos), ("FIANZAS", bd_rfv)):
        for (c, p, ramo), v in bd.valores.items():
            if p > ultimo or not c.endswith("NETO"):
                continue
            pref = c.split()[0]
            bruto = bd.valores.get((f"{pref} BRUTO", p, ramo), 0.0)
            irr = bd.valores.get((f"{pref} IRR", p, ramo), 0.0)
            if abs(v - (bruto - irr)) > 1.0:
                alertas.append((libro, f"{c} {p} RAM_{ramo}", "La historia no cumple NETO = BRUTO - IRR"))

    tc_hist = {}
    for libro, bd in (("DANOS", bd_danos), ("FIANZAS", bd_rfv)):
        if MODELAR_EN_MXN.get(libro):
            tc_hist[libro] = leer_tc_real(bd, ultimo, libro, alertas)
            alertas.append(("METODO", f"Moneda {libro}", "Montos modelados en MXN (historia USD x TC real de SAP) y "
                                                         "convertidos a USD con el TC de cada mes proyectado de la BD"))

    print("Construyendo series ...", flush=True)
    series = (series_montos(bd_danos, "DANOS", ESTRUCTURA["DANOS"], ultimo, h, tc_hist.get("DANOS"))
              + series_montos(bd_rfv, "FIANZAS", ESTRUCTURA["FIANZAS"], ultimo, h, tc_hist.get("FIANZAS"))
              + series_hparametros(hp, h, ultimo))
    for tipo, nombre in MODELO_POR_TIPO.items():
        print(f"   {tipo:<7} -> {nombre}", flush=True)
    print(f"   {len(series)} series a proyectar (con backtest por serie) ...", flush=True)
    resultados = correr_series(series)
    ajustar_orden_indices(hp, resultados, alertas)

    # factor de prima: las reservas que dependen de la prima se escriben como factor x exposicion de prima
    ppto = leer_presupuesto()
    tc_primas = {**bd_danos.tc, **bd_rfv.tc, **(tc_hist.get("FIANZAS") or leer_tc_real(bd_rfv, ultimo))}
    tc_primas.update({p: tc_para_periodo(bd_rfv, p) for p in periodos_proy})
    pr, diag_factor = None, {"estado": "apagado (USAR_FACTOR_PRIMA = False)"}
    if USAR_FACTOR_PRIMA:
        print("Factor de prima ...", flush=True)
        if primas is None:
            diag_factor = {"estado": f"no se pudo cargar primas.py ({_ERROR_PRIMAS}): se usa la recta"}
        else:
            error_lectura = ""
            try:
                pr = primas.leer_primas(ultimo, periodos_proy[-1], primas.lineas_del_dashboard(ppto), tc_primas)
            except Exception as e:  # noqa: BLE001
                pr = None
                error_lectura = f"no se pudieron leer las primas ({type(e).__name__}: {e}): se usa la recta"
                alertas.append(("PRIMAS", "Lectura", error_lectura))
                print(f"   AVISO: {error_lectura}", flush=True)
            for a in (pr.avisos if pr is not None else []):
                alertas.append(("PRIMAS", "Primas", a))
                print(f"   AVISO {a}", flush=True)
            respaldo = {k: (list(r.pronostico), list(r.li), list(r.ls), r.modelo, list(r.alertas), r.error_modelo,
                            r.error_ultimo_valor, r.error_ses, r.n_cortes)
                        for k, r in resultados.items() if r.tipo == "nivel"}
            n0 = len(alertas)
            try:
                diag_factor = ({"estado": error_lectura} if error_lectura else
                               aplicar_factor_prima(resultados, pr, hp, tc_primas, {"DANOS": bd_danos, "FIANZAS": bd_rfv},
                                                    periodos_proy, ultimo, alertas))
            except Exception as e:  # noqa: BLE001
                del alertas[n0:]
                for k, (pn, lo, hi, mo, al, em, eu, es, nc) in respaldo.items():
                    r = resultados[k]
                    r.pronostico, r.li, r.ls, r.modelo, r.alertas, r.factor = pn, lo, hi, mo, al, {}
                    r.error_modelo, r.error_ultimo_valor, r.error_ses, r.n_cortes = em, eu, es, nc
                diag_factor = {"estado": f"error en el factor de prima ({type(e).__name__}: {e}); se usa la recta"}
                alertas.append(("PRIMAS", "Factor de prima", diag_factor["estado"]))
        print(f"   {diag_factor.get('estado')}", flush=True)

    print("Aplicando identidades contables y escribiendo archivos ...", flush=True)
    proy_danos = derivar_montos(bd_danos, "DANOS", ESTRUCTURA["DANOS"], resultados, periodos_proy,
                                en_mxn="DANOS" in tc_hist)
    proy_rfv = derivar_montos(bd_rfv, "FIANZAS", ESTRUCTURA["FIANZAS"], resultados, periodos_proy,
                              en_mxn="FIANZAS" in tc_hist)
    sin_rango = {k: list(r.pronostico) for k, r in resultados.items()}   # para el comparativo del factor
    resumen_rangos = (aplicar_rango_esperado(proy_danos, bd_danos, "DANOS", ESTRUCTURA["DANOS"], resultados,
                                             periodos_proy, ultimo, alertas)
                      + aplicar_rango_esperado(proy_rfv, bd_rfv, "FIANZAS", ESTRUCTURA["FIANZAS"], resultados,
                                               periodos_proy, ultimo, alertas))
    validar(proy_danos, proy_rfv)
    comparativo = comparar_factor(resultados, diag_factor, pr, tc_primas, {"DANOS": bd_danos, "FIANZAS": bd_rfv},
                                  {"DANOS": proy_danos, "FIANZAS": proy_rfv}, periodos_proy, tc_hist, ultimo, sin_rango)
    actualizar_finales_factor(diag_factor, resultados, periodos_proy)

    info_danos = escribir_bd_montos(bd_danos, proy_danos, periodos_proy, SALIDA_BD_DANOS)
    escribir_correccion_moneda(bd_danos, correcciones["DANOS"])
    n_hp = escribir_hparametros(hp, resultados, periodos_proy)
    guardar_libro(bd_danos.wb, SALIDA_BD_DANOS, original=ARCHIVO_BD_DANOS)
    info_rfv = escribir_bd_montos(bd_rfv, proy_rfv, periodos_proy, SALIDA_BD_RFV)
    escribir_correccion_moneda(bd_rfv, correcciones["FIANZAS"])
    guardar_libro(bd_rfv.wb, SALIDA_BD_RFV, original=ARCHIVO_BD_RFV)

    historia = {
        "DANOS": {k: v for k, v in bd_danos.valores.items() if k[1] <= ultimo},
        "FIANZAS": {k: v for k, v in bd_rfv.valores.items() if k[1] <= ultimo},
    }
    segundos = time.time() - t0
    filas_ppto = contraste_presupuesto(ppto, {"DANOS": bd_danos, "FIANZAS": bd_rfv},
                                       {"DANOS": proy_danos, "FIANZAS": proy_rfv}, alertas) if ppto and ppto.get("anio") else []
    escribir_diagnostico(resultados, periodos_proy, alertas, {"DANOS": proy_danos, "FIANZAS": proy_rfv},
                         {"ultimo": ultimo, "segundos": segundos, "versiones": _versiones(),
                          "rangos": resumen_rangos,
                          "moneda_corregida": {k: len(v) for k, v in correcciones.items() if v},
                          "celdas_moneda": correcciones,
                          "presupuesto": filas_ppto, "archivo_presupuesto": ppto["archivo"] if ppto else "",
                          "lineas_nuevas_presupuesto": (ppto or {}).get("lineas_nuevas") or [],
                          "primas": pr, "factor": diag_factor, "comparativo": comparativo})
    graficas_ok = False
    if GENERAR_GRAFICAS:
        print("Generando graficas ...", flush=True)
        try:
            graficar(resultados, {"DANOS": proy_danos, "FIANZAS": proy_rfv}, historia, periodos_proy)
            graficas_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"   No se pudieron generar las graficas: {e!r}")
    dashboard_ok = html_ok = False
    if GENERAR_DASHBOARD:
        try:
            import dashboard  # noqa: WPS433
            dashboard.generar(SALIDA_DASHBOARD)
            dashboard_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"   No se pudo generar el dashboard de Excel: {e!r}")
        try:
            import dashboard_html  # noqa: WPS433
            dashboard_html.generar(SALIDA_DASHBOARD_HTML)
            html_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"   No se pudo generar el dashboard HTML: {e!r}")

    print("\nRESUMEN")
    print(f"   {SALIDA_BD_DANOS.name}: {info_danos['actualizados']} renglones actualizados, "
          f"{info_danos['nuevos']} renglones nuevos en {HOJA_MONTOS}; {n_hp} renglones nuevos en {HOJA_PARAMETROS}; "
          f"TC actualizado en {info_danos['tc_cambiados']} renglones")
    print(f"   {SALIDA_BD_RFV.name}: {info_rfv['actualizados']} renglones actualizados, "
          f"{info_rfv['nuevos']} renglones nuevos; TC actualizado en {info_rfv['tc_cambiados']} renglones")
    print(f"   Diagnostico: {SALIDA_DIAGNOSTICO.name}")
    if GENERAR_GRAFICAS:
        print(f"   Graficas: {SALIDA_GRAFICAS.name}" if graficas_ok
              else "   Graficas: NO se actualizaron (ver mensaje arriba)")
    if GENERAR_DASHBOARD:
        print(f"   Dashboard Excel: {SALIDA_DASHBOARD.name}" if dashboard_ok
              else "   Dashboard Excel: NO se actualizo (ver mensaje arriba)")
        print(f"   Dashboard HTML: {SALIDA_DASHBOARD_HTML.name}" if html_ok
              else "   Dashboard HTML: NO se actualizo (ver mensaje arriba)")
    mayores = sorted(((r.pronostico[-1] / r.historia_valores[-1] - 1, r) for r in resultados.values()
                      if r.tipo in ("nivel", "indice") and r.historia_valores and r.historia_valores[-1] > 0
                      and r.pronostico and not math.isnan(r.pronostico[-1])), key=lambda t: -abs(t[0]))[:6]
    if mayores:
        print(f"   Mayores cambios proyectados a {periodos_proy[-1]} (revisalos contra el plan de negocio):")
        for cambio, r in mayores:
            ventana = r.parametros.get("ventana")
            pa = r.parametros.get("pendiente_aplicada")
            aplicada = ""
            if pa is not None and abs(pa - math.log1p(r.tendencia_mensual) if r.transformacion == "log" else pa - r.tendencia_mensual) > 1e-9:
                aplicada = f", se proyecta {(math.expm1(pa) if r.transformacion == 'log' else pa):+.1%} por credibilidad {r.parametros.get('credibilidad_pendiente', 1):.2f}"
            if r.factor.get("decision") in ("factor de prima", "combinacion"):
                print(f"      {r.clave[0]} {r.clave[1]} {r.clave[2]} ramo {r.clave[3]}: {cambio:+.0%} ({r.modelo}; "
                      f"dic/dic {r.factor.get('descomposicion') or 's/d'}; la recta daba "
                      f"{r.factor['pron_recta'][-1] / r.historia_valores[-1] - 1:+.0%})")
                continue
            print(f"      {r.clave[0]} {r.clave[1]} {r.clave[2]} ramo {r.clave[3]}: {cambio:+.0%} "
                  f"(tendencia {r.tendencia_mensual:+.1%} mensual{aplicada}"
                  + (f", regresion sobre {ventana} de {r.n_obs} meses)" if ventana else f", {r.modelo})"))
    con_est = [r.parametros["credibilidad_estacional"] for r in resultados.values()
               if r.parametros.get("credibilidad_estacional")]
    if ESTACIONALIDAD_MENSUAL:
        print(f"   Estacionalidad mensual aplicada en {len(con_est)} series (credibilidad mediana "
              f"{np.median(con_est) if con_est else 0:.2f}); patron por mes en la hoja 'Estacionalidad'")
    if filas_ppto:
        anio = ppto["anio"]
        print(f"   Contraste con el presupuesto ({ppto['archivo']}), crecimiento dic {anio} contra dic {anio - 1}:")
        for f in filas_ppto:
            cr, rf = f.get(f"Crec. reserva {anio}"), f.get(f"Crec. referencia {anio}")
            if cr is not None and rf is not None:
                print(f"      {f['Reserva']:<10} {cr:+6.1%}  contra {f['Referencia'].lower()} {rf:+6.1%}")
    elif ppto:
        print(f"   (Sin contraste con presupuesto: no se pudo usar {ppto['archivo']}; ver aviso arriba)")
    else:
        print(f"   (Sin contraste con presupuesto: no hay {PATRON_PRESUPUESTO} en entradas/)")
    if USAR_FACTOR_PRIMA:
        def _f(v):
            return "s/d" if v is None or not np.isfinite(v) else f"{v:.1f}"
        print(f"   Factor de prima: {diag_factor.get('estado')}"
              + (f"; perfil mensual de la prima estimada: {pr.perfil['elegido']}" if pr is not None else ""))
        for d in diag_factor.get("decision", []):
            if d["Series elegibles"]:
                print(f"      {d['Tipo']:<13} {d['Decision']:<16} error backtest: recta {_f(d['Recta (A)'])}, factor "
                      f"{_f(d['Factor, prima real (B)'])}, combinacion {_f(d['Combinacion (C)'])}; con presupuesto: recta "
                      f"{_f(d['Recta en el corte ex ante'])}, factor {_f(d['Factor con presupuesto (B)'])} ({d['Motivo']})")
        filas_c = (comparativo or {}).get("filas", [])
        if filas_c:
            dics = [k for k in filas_c[0] if k.startswith("Proy ")]
            print(f"   Reservas NETO totales (M USD) {' / '.join(k[5:] for k in dics)}:")
            for f in filas_c:
                crec = next((v for k, v in f.items() if k.startswith("Crec.")), None)
                print(f"      {f['Reserva']:<10} {f['Escenario']:<27} "
                      + " / ".join(f"{(f.get(k) or 0) / 1e6:,.1f}" for k in dics)
                      + (f"  (crec. {crec:+.1%})" if crec is not None else ""))
    n_alertas = len(alertas) + sum(len(r.alertas) for r in resultados.values())
    print(f"   Alertas a revisar: {n_alertas} (hoja 'Alertas' del diagnostico)")
    print(f"   Tiempo total: {time.time() - t0:,.0f} s")


def validar(proy_danos: dict, proy_rfv: dict):
    """Chequeos de consistencia de lo que se va a escribir."""
    for nombre, dic, reglas in (("DANOS", proy_danos, [("RRC", ["BEL", "GTO", "MR"]), ("SONR", ["BEL", "MR"])]),
                                ("FIANZAS", proy_rfv, [("RFV", None)])):
        for (c, p, ramo), v in dic.items():
            if not np.isfinite(v):
                raise AssertionError(f"{nombre}: valor no finito en {c} {p} {ramo}")
        for pref, comps in reglas:
            claves = {(p, r) for (c, p, r) in dic if c.startswith(pref + " ")}
            for p, r in claves:
                bruto = dic[(f"{pref} BRUTO", p, r)]
                neto = dic[(f"{pref} NETO", p, r)]
                irr = dic[(f"{pref} IRR", p, r)]
                assert abs(neto - (bruto - irr)) < 1e-6 * max(1.0, abs(bruto)), (nombre, pref, p, r)
                if comps:
                    suma = sum(dic[(f"{pref} {x}", p, r)] for x in comps)
                    assert abs(bruto - suma) < 1e-6 * max(1.0, abs(bruto)), (nombre, pref, p, r)
                assert bruto >= -1e-6, (nombre, pref, p, r, bruto)


if __name__ == "__main__":
    main()
