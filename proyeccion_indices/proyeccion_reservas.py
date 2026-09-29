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
       - RCONT -> Holt-Winters amortiguado con estacionalidad por mes del trimestre (acumula en los
         meses 1-2 y libera en el 3) si hay al menos 12 meses; con menos, SES (nivel).
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
   Los montos se modelan en USD (modelar en MXN y convertir con el TC fue menos preciso).

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
from dataclasses import dataclass, field  # noqa: E402
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
# Los montos se modelan en USD, asi que el TC no cambia las cifras proyectadas (salvo con MODELAR_EN_MXN).
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
#   Tambien estan disponibles "Holt amortiguado", "Holt-Winters amortiguado (mensual)" y "Holt-Winters amortiguado
#   (trimestral)" (suavizamiento exponencial); RCONT usa el trimestral por su estacionalidad (acumula meses 1-2,
#   libera en el 3).
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
# ano). Se suma a la recta de tendencia en las series que se proyectan con "Tendencia historica".
ESTACIONALIDAD_MENSUAL = True    # False = solo la recta de tendencia
MESES_ESTACIONALIDAD = 36        # historia para estimar el patron: la misma ventana que la tendencia. Con toda la
                                 # historia los picos de anos distintos caen en meses distintos, el promedio sale mas
                                 # plano y el backtest empeora; con 36 meses mejora (indices 18.9 % contra 20.2 % de la
                                 # recta sola). None = toda la historia.
MIN_OBS_ESTACIONALIDAD = 36      # tres anos: quedan 24 meses sin tendencia, dos por cada mes del ano (minimo exigido)
CREDIBILIDAD_ESTACIONAL = "buhlmann"  # cuanto del patron observado se aplica (1 = se repite igual todos los anos;
                                 #   0 = puro ruido, no se aplica):
                                 #   "buhlmann": credibilidad de Buhlmann Z = n/(n+K), K = varianza dentro del mes /
                                 #       varianza entre meses (la estandar actuarial; backtest de indices 18.9 % / 14.1 %
                                 #       a 1-16 / 1-6 meses).
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
#       8.5 % contra 9.5 % en la prueba anidada) y evita que un mes bajo arrastre todo el horizonte.
PERSISTENCIA_DESVIACION = {"nivel": 1.0, "indice": 0.8, "lag": 1.0}
MESES_NIVEL_LOCAL = 12           # meses del nivel promedio (respecto a la recta) al que converge la desviacion
MEDIA_ARITMETICA_INDICES = False # los indices se modelan en logaritmos: el nivel al que convergen es el promedio
                                 # geometrico del ultimo ano, que queda por debajo del promedio aritmetico (el que se ve en
                                 # la historia) tanto mas cuanto mas volatil es la serie (mediana 0.4 %, hasta 6 % en los
                                 # 99.5 % de los ramos 31 y 35). True = se converge al promedio aritmetico (estimador de
                                 # "smearing" de Duan: log del promedio de exp(residuo) de los ultimos 12 meses).
ANCLAR_SERIES = set()            # series (Serie, Ramo) de indices que se dejan ancladas al ultimo real (phi = 1) a
                                 # criterio del area, p. ej. {("Ind sin RRC 99.5%", "31")} si la caida reciente es un
                                 # cambio de nivel y no una desviacion que rebota
# Cuanto de la pendiente de la recta se proyecta:
#   montos y LAGs: completa (1.0): la tendencia de los ultimos tres anos se continua tal cual (decision del area).
#   indices: ponderada por su credibilidad = R2 ajustado de la recta ("r2"). Son razones: extrapolar 16 meses una
#       pendiente que la recta explica poco (ramo 31: +1.3 % mensual con R2 0.16) proyecta subidas o bajadas que la
#       serie nunca sostuvo. Backtest de indices (error % mediano a 1-16 / 1-6 meses): pendiente completa 18.3 / 14.0;
#       ponderada por R2 16.3 / 13.5; sin pendiente 13.9 / 12.6. Un numero entre 0 y 1 fija la proporcion.
CREDIBILIDAD_PENDIENTE = {"nivel": 1.0, "indice": "r2", "lag": 1.0}
# Cotas de los modelos de suavizamiento exponencial (si se eligen), estimadas por maxima verosimilitud dentro de
# ellas: alpha ~ 1 (arranca del ultimo dato real), beta <= 0.15 (tendencia de los ultimos anos, no del ultimo mes),
# phi entre 0.80 y 0.98. RCONT (Holt-Winters trimestral) suaviza el nivel (alpha >= 0.2) para separar la
# estacionalidad. SES estima alpha libre.
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
#   Danos: USD. En backtest, modelar en MXN fue menos preciso (WAPE 22.5 % contra 19.8 %, 21 series).
#   Fianzas: MXN. La RFV es una reserva en pesos: de ene-25 a ago-26 la RFV NETO crecio 27 % en pesos pero 55 % en
#       dolares, porque el peso paso de 20.7 a 17.0. Modelar en USD extrapolaba esa apreciacion (dic-27: 134 M USD)
#       cuando Inversiones pronostica 18.5 a dic-27; en MXN con ese TC da 105 M USD. El unico corte de backtest de
#       Fianzas (8 meses de 2026, con el peso aun apreciandose) favorecia USD (6.0 % contra 7.4 %) justamente por eso.
MODELAR_EN_MXN = {"DANOS": False, "FIANZAS": True}
# Monedas mezcladas en la historia: si un tramo de la BD viene en MXN y otro en USD, el salto entre dos meses seguidos
# es del tamano del TC (p. ej. RFV BRUTO 1,754 M en dic-25 y 104 M en ene-26) y la tendencia lo lee como una caida de
# 94 %. True = se detecta (recorriendo la historia hacia atras desde el ultimo mes, que se toma como USD), los meses en
# MXN se convierten a USD con el TC de cada mes de la propia BD, en memoria y en la BD de salida (con comentario en cada
# celda corregida), y se avisa en consola y en Alertas. El archivo de entrada no se modifica.
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
# las primas tomadas, SONR con los siniestros tomados (Danos = total menos las lineas de Fianzas) y RFV con las primas
# de las lineas de Fianzas. No cambia la proyeccion: sirve para ver si las reservas crecen en proporcion al negocio.
PATRON_PRESUPUESTO = "Dashboard_FCST*.html"
LINEAS_FIANZAS_PPTO = ("4003",)  # lineas de negocio del presupuesto donde estan las afianzadoras (aproximacion: la 4003
                                 # mezcla fianzas de Mexico con caucion y credito de otros paises)
TOLERANCIA_PRESUPUESTO = 0.10    # alerta si el crecimiento de la reserva difiere del de su referencia en mas de 10 pts
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
#   nivel + tendencia amortiguada; Holt-Winters = ademas estacionalidad (aqui la trimestral de RCONT).
TENDENCIA = "Tendencia historica"
MODELOS = {
    "SES": dict(),
    "Holt amortiguado": dict(trend="add", damped_trend=True),
    "Holt-Winters amortiguado (mensual)": dict(trend="add", damped_trend=True, seasonal="add", seasonal_periods=12),
    "Holt-Winters amortiguado (trimestral)": dict(trend="add", damped_trend=True, seasonal="add",
                                                  seasonal_periods=3),
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


def ajustar_ets(z, modelo: str, h: int):
    """Ajusta el modelo a z (en la escala del modelo) y devuelve pronostico, intervalo y parametros."""
    kw = MODELOS[modelo]
    if not kw.get("trend"):
        cotas = None                                    # SES: alpha libre
    else:
        cotas = dict(COTAS_ESTACIONAL if kw.get("seasonal") else COTAS_SUAVIZAMIENTO)
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
        return "Holt-Winters amortiguado (trimestral)" if n >= MIN_OBS_TRIMESTRAL else "SES"
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


def detectar_moneda_mezclada(bd: BDMontos, ultimo: int) -> dict:
    """Meses de la historia que vienen en MXN dentro de una BD en USD: {periodo: TC de la BD}. Se recorre la historia
    hacia atras desde el ultimo mes (que se toma como USD); un salto entre dos meses seguidos del tamano del TC
    (dentro de TOLERANCIA_SALTO_TC) marca un cambio de moneda. Se usa el total de todos los conceptos y ramos."""
    totales = {}
    for (_, p, _), v in bd.valores.items():
        if p <= ultimo and isinstance(v, (int, float)) and not math.isnan(v):
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
    """Convierte a USD (en memoria) los meses que la BD trae en MXN. Regresa las celdas corregidas
    [(concepto, periodo, ramo, valor original, valor en USD, tc)] para escribirlas tambien en la BD de salida."""
    en_mxn = detectar_moneda_mezclada(bd, ultimo)
    if not en_mxn:
        return []
    cambios = []
    for (c, p, r), v in list(bd.valores.items()):
        if p in en_mxn and v:
            bd.valores[(c, p, r)] = v / en_mxn[p]
            cambios.append((c, p, r, v, v / en_mxn[p], en_mxn[p]))
    meses = sorted(en_mxn)
    texto = (f"{len(meses)} meses ({meses[0]} a {meses[-1]}) venian en pesos (el salto contra el mes siguiente es del "
             f"tamano del TC); se convirtieron a USD con el TC de cada mes de la BD ({len(cambios)} celdas). Sin esto la "
             "tendencia leia el cambio de moneda como una caida de ~94 %. Revisa la BD de entrada.")
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
    salida = {"archivo": ruta.name, "anio": anio, "lineas_nuevas": nuevas}
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
                      "Holt-Winters amortiguado con estacionalidad por mes del trimestre si hay al menos 12 meses; "
                      "con menos, SES (nivel). Series cortas: SES (< 6 obs para la tendencia) o ultimo valor (< 4). "
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
                        "modelo."),
        ("5. Intervalos", f"{NIVEL_INTERVALO:.0%}, calculados por el propio modelo (en logaritmos para montos e "
                          "indices, por lo que son asimetricos)."),
        ("6. Reglas", "Series en cero -> 0; parametros en escalon -> ultimo valor; dominio actuarial (cesion en "
                      "[0,1], %GTO y %MR >= 0, LAGs >= 0); 99.5% >= media si siempre lo fue; limpieza de textos "
                      "y LAG=0 marcadores; alertas de saltos atipicos y de cambios mayores a los historicos."),
        ("7. Tipo de cambio", "Columna TC = supuesto de Inversiones (TC_Real_Esti.xlsx, hoja TC: FCST 2026 y "
                              "FCST 2027), en tipo_cambio.py; los meses reales = TC real de SAP. "
                              + "; ".join(f"{lib}: se modela en {'MXN y se convierte a USD con el TC de cada mes proyectado, asi que el TC si mueve las cifras en USD' if v else 'USD, asi que el TC no altera las cifras proyectadas'}"
                                          for lib, v in MODELAR_EN_MXN.items()) + "."),
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
           f"Proy {periodos_proy[-1]}", "Var % vs ultimo real", "Alertas"]
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
                 num(fin), var, " | ".join(r.alertas)]
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

    ws = wb.create_sheet("Alertas")
    ws.append(["Libro", "Serie / Elemento", "Detalle"])
    for a in alertas_generales:
        ws.append(list(a))
    for k, r in sorted(resultados.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        for a in r.alertas:
            ws.append([k[0], f"{k[1]} | {k[2]} | ramo {k[3]}", a])
    _formato_tabla(ws, negrita, encab)
    guardar_libro(wb, SALIDA_DIAGNOSTICO)


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

    print("Aplicando identidades contables y escribiendo archivos ...", flush=True)
    proy_danos = derivar_montos(bd_danos, "DANOS", ESTRUCTURA["DANOS"], resultados, periodos_proy,
                                en_mxn="DANOS" in tc_hist)
    proy_rfv = derivar_montos(bd_rfv, "FIANZAS", ESTRUCTURA["FIANZAS"], resultados, periodos_proy,
                              en_mxn="FIANZAS" in tc_hist)
    resumen_rangos = (aplicar_rango_esperado(proy_danos, bd_danos, "DANOS", ESTRUCTURA["DANOS"], resultados,
                                             periodos_proy, ultimo, alertas)
                      + aplicar_rango_esperado(proy_rfv, bd_rfv, "FIANZAS", ESTRUCTURA["FIANZAS"], resultados,
                                               periodos_proy, ultimo, alertas))
    validar(proy_danos, proy_rfv)

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
    ppto = leer_presupuesto()
    filas_ppto = contraste_presupuesto(ppto, {"DANOS": bd_danos, "FIANZAS": bd_rfv},
                                       {"DANOS": proy_danos, "FIANZAS": proy_rfv}, alertas) if ppto and ppto.get("anio") else []
    escribir_diagnostico(resultados, periodos_proy, alertas, {"DANOS": proy_danos, "FIANZAS": proy_rfv},
                         {"ultimo": ultimo, "segundos": segundos, "versiones": _versiones(),
                          "rangos": resumen_rangos,
                          "moneda_corregida": {k: len(v) for k, v in correcciones.items() if v},
                          "celdas_moneda": correcciones,
                          "presupuesto": filas_ppto, "archivo_presupuesto": ppto["archivo"] if ppto else "",
                          "lineas_nuevas_presupuesto": (ppto or {}).get("lineas_nuevas") or []})
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
