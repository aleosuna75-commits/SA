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
         (AMORTIGUACION_TENDENCIA = 1). En los montos se suma LA ESTACIONALIDAD MENSUAL: el patron
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
       - BEL por FND (Danos): el FND con Holt amortiguado con guardia de saltos (serie de tiempo, HOLT_FND), FACTOR GTO
         y FACTOR MR con la pendiente combinada (PENDIENTE_COMBINADA) y la CESION con SES;
       - RCONT -> Holt-Winters sin tendencia: nivel suavizado mas estacionalidad por mes del trimestre
         (acumula en los meses 1-2 y libera en el 3) si hay al menos 12 meses; con menos, SES (nivel).
   Los intervalos al 80% salen de la variabilidad mensual alrededor de la tendencia (crece con la raiz
   del horizonte) o del propio modelo de suavizamiento.
c) Backtest por serie: se vuelve a proyectar desde 16, 12 y 8 meses antes del final y se mide el
   error contra lo real, del modelo y de las alternativas simples (ultimo valor y SES). Se
   reporta por serie (Series_Modelos) y por tipo (Backtest); no cambia el modelo.
d) Reglas actuariales / de calidad de datos (todas reportadas en la hoja "Alertas"):
       - ramos estatutarios (RAMOS_ESTATUTARIOS: la CNSF otorga sus IS y LAGs) -> los indices y LAG 1-10
         de HParametros se quedan fijos en el ultimo valor real;
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

import fnmatch  # noqa: E402
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
from openpyxl.utils import column_index_from_string, get_column_letter  # noqa: E402
from openpyxl.worksheet.properties import Outline  # noqa: E402
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
VERSION_CODIGO = "2026-10-08a"   # version de los scripts: sale en la consola, en la hoja Resumen del diagnostico, en el pie
                                 # del tablero HTML y en la hoja Dashboard Razones del Excel, para saber con que version se corrio
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
    "fnd": "Holt amortiguado con guardia de saltos",   # FND del BEL por FND: serie de tiempo (HOLT_FND), en logaritmos,
                                      # anclado al ultimo real; "Tendencia historica" = la pendiente combinada
    "factor_log": "Tendencia historica",   # FACTOR GTO y FACTOR MR del BEL por FND: igual que el FND (en logaritmos)
    "factor": "Tendencia historica",  # (sin uso hoy) pendiente combinada en niveles, puntos por mes; p. ej. la CESION
}
MESES_TENDENCIA = 36             # ventana de la tendencia historica (None = toda la historia). Con toda la historia
                                 # entran arranques desde cero y cambios de regimen (ramo 80 SONR, Hidro) que
                                 # disparan la pendiente; 36 meses = la tendencia de los ultimos tres anos.
AMORTIGUACION_TENDENCIA = 1.0    # 1.0 = la tendencia continua constante (sin amortiguar). Con 0.95, cada mes conserva
                                 # 95% (a 16 meses, 44%); con 0.98, 72%.
MIN_OBS_TENDENCIA = 6            # observaciones minimas para estimar la tendencia; con menos se usa SES
# Estacionalidad mensual (los picos que se repiten cada ano): patron por mes del ano alrededor de la tendencia,
# estimado por descomposicion clasica (la serie menos su media movil centrada de 12 meses, promediada por mes del
# ano). Se suma a la recta de tendencia en las series de TIPOS_CON_ESTACIONALIDAD (hoy solo los montos); los indices, los
# LAGs, el FND y los factores del BEL por FND llevan solo la recta (o el Holt del FND).
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
TIPOS_CON_ESTACIONALIDAD = ("nivel",)   # solo los montos (BEL y BRUTO: Fianzas y los ramos sin BEL por FND) llevan el patron.
                                 # Indices, FND y factores del BEL por FND van sin patron del mes (2026-10-07, revision del
                                 # area: la reserva proyectada liberaba y constituia de mas de un mes a otro). En la historia
                                 # el patron del FND (PND / PRIMA N AÑOS) se compensaba con el movimiento de la prima: en
                                 # SONR es en buena parte el espejo de cuando crecio la prima de 12 meses (correlacion del
                                 # patron del FND con el de la prima, con signo cambiado, de 0.7 a 0.9 por ramo); en RRC no
                                 # es estable de un ano a otro (el FND dic / ago de RRC 50: +15 %, -1 %, -15 % y -22 % en
                                 # 2022 a 2025) y el pico de agosto que restaba el ancla no ocurrio en 2026. Aplicado sobre
                                 # la prima del FCST, que tiene otro calendario, metia dientes de sierra en el BEL. En
                                 # backtest del BEL (IS y PEACUMULADA reales, 17 series con 36 meses de FND, 85 cortes) la
                                 # precision no cambia (error 14.3 % con patron y 14.5 % sin el) y la dispersion de los
                                 # cambios mensuales proyectados baja a la mitad. En los indices, sin patron el backtest
                                 # mejora (error mediano 12.4 % contra 14.2 %; el modelo gana al ultimo valor en 69 % de las
                                 # series contra 56 %). Los LAGs (patron de desarrollo) no tienen mes del ano. El factor de
                                 # prima (ajustar_factor) tiene su propio camino y conserva su patron. Para volver al
                                 # patron: ("nivel", "indice", "fnd", "factor_log", "factor").
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
#   FND y factores del BEL por FND (fnd, factor): se conserva (phi = 1), por decision del area. Son razones que vienen
#       con tendencia o con cambios de nivel recientes (el FACTOR MR de Acc. Personales bajo de 10 % a 2.5 % en un ano; el
#       FACTOR GTO cambia por escalones anuales): si la desviacion se desvaneciera hacia el nivel del ultimo ano, la
#       proyeccion arrancaria con una curva de regreso hacia donde estaba la serie hace meses, en contra de su tendencia.
#       Anclada, la proyeccion arranca del ultimo real y sigue su tendencia (pendiente combinada, PENDIENTE_COMBINADA),
#       sin patron del mes desde 2026-10-07 (TIPOS_CON_ESTACIONALIDAD).
PERSISTENCIA_DESVIACION = {"nivel": 1.0, "indice": 0.8, "lag": 1.0, "fnd": 1.0, "factor_log": 1.0, "factor": 1.0}
# Con la desviacion conservada (phi = 1), de donde arranca la proyeccion: la desviacion del ultimo mes (1) o el promedio
# de las desviaciones de los ultimos k meses respecto a la recta (k > 1: arranca del nivel reciente de la serie, no de un
# solo mes; util en razones con picos, como el FACTOR MR, donde anclar a un mes atipico arrastra el pico a todo el
# horizonte). No aplica a los tipos con phi < 1.
ANCLA_MESES = {"nivel": 1, "lag": 1, "fnd": 1, "factor_log": 1, "factor": 1}
ANCLA_MESES_SERIE = {"FACTOR MR": 3}   # por nombre de serie, encima del tipo. FACTOR MR tiene picos de un mes: anclado al
                                 # ultimo mes su backtest es 30.3 % de error mediano, anclado a 3 meses 25.1 % (con la
                                 # pendiente combinada; el FND y la CESION van con 1 mes: 15.3 % y 15.0 %; FACTOR GTO
                                 # cambia por escalones y da igual)
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
#   FND y factores del BEL por FND (fnd, factor): "combinada" (PENDIENTE_COMBINADA). Con el R2 de la recta de 36 meses
#       quedaban planas 31 de 75 series: cuando una razon dio la vuelta dentro de la ventana (cesion RRC 40: 21 % -> 41 %
#       en ene-25 -> 28.6 % en ago-26) el R2 vale casi 0 y la proyeccion era una linea recta en el ultimo real.
CREDIBILIDAD_PENDIENTE = {"nivel": 1.0, "indice": "r2", "lag": 1.0, "fnd": "combinada", "factor_log": "combinada",
                          "factor": "combinada"}
# Pendiente "combinada" del FND, FACTOR GTO, FACTOR MR y CESION (sobre la serie sin el patron del mes, en la escala del
# modelo: logaritmos en FND, GTO y MR, puntos en la CESION):
#   1. Rectas de los ultimos 24 y 36 meses con Theil-Sen (mediana de las pendientes entre todos los pares de meses: un
#      pico o un salto de un solo mes casi no la mueve); el FACTOR GTO con minimos cuadrados, porque cambia por
#      escalones anuales y Theil-Sen da 0 cuando la mayoria de los pares cae en el mismo escalon. Cada recta lleva su
#      estadistico t con el error estandar corregido por la autocorrelacion de sus residuos (AR(1)).
#   2. Se promedian, con pesos iguales, pronosticos que arrancan del mismo punto: plano, recta de 24 meses y recta de
#      36 (esta solo si no va en contra de la de 24: si apunta al reves describe un regimen anterior). Si la recta de 24
#      meses tiene tendencia clara (|t| >= t_clara) el plano sale del promedio: la proyeccion no queda plana.
#   3. Meseta: si los ultimos 12 meses no confirman la direccion de la recta de 24 (su t en esa direccion < t_meseta,
#      sin tendencia o ya dando la vuelta) se proyecta la mitad de la recta de 24 meses (plano y recta de 24), sin la de
#      36. En el GTO (series_gto_meseta) el plano solo se queda en el promedio.
#   4. Salto del ultimo mes (FND y CESION): si el ultimo cambio mensual supera k_salto veces la mediana de las
#      desviaciones absolutas (MAD) de los cambios de 24 meses, no se extrapola tendencia desde el nuevo nivel
#      (pendiente 0; se conserva el patron del mes si el tipo lo lleva).
#   5. La pendiente se amortigua (amortiguacion 0.95 por mes: a 16 meses recorre 66 % de la recta; nunca da la vuelta,
#      asi que no hay curvas de regreso) y se reduce, sin cambiar de signo, si a meses_tope meses sacaria la razon del
#      rango de los ultimos 36 meses reales ampliado tope_rango veces ese rango (salvaguarda de plausibilidad).
#   La proyeccion arranca del ultimo real (FACTOR MR: del nivel de sus ultimos 3 meses, ANCLA_MESES_SERIE).
# Se eligio en un banco de pruebas de las 75 series (13 ramos RRC x FND/CESION, 11 x GTO/MR y 9 ramos SONR x
# FND/MR/CESION, historia a ago-26) contra cuatro alternativas (recta ponderada por recencia, Holt amortiguado, tendencia del ultimo
# tramo y pendiente robusta en 4 ventanas): backtest con 9 cortes (4 a 20 meses antes del final, horizonte hasta 16)
# error % mediano / medio 16.4 / 23.7 contra 17.4 / 24.0 de la recta ponderada por R2 (repetir el ultimo valor: 14.9);
# series aplanadas 13 contra 31 (7 por las reglas de salto o meseta; las demas por la escala logaritmica, el plano en
# el promedio o la cota de 100 %), ninguna contraria a su tendencia.
# t_clara, t_meseta, k_salto, la amortiguacion y el tope son criterios de modelacion, no se estimaron de los datos.
# FND: Holt amortiguado con guardia de saltos (MODELO_POR_TIPO["fnd"]), un modelo de series de tiempo (ETS(A,Ad,N), por
# indicacion del area: "para el FND utiliza series de tiempo"), sobre el logaritmo del FND sin su patron del mes:
#   - nivel = el ultimo real (alpha = 1: la proyeccion arranca donde esta la serie, sin salto);
#   - tendencia = promedio exponencial de los cambios mensuales (beta = 0.05: memoria media de unos 9 meses, ni el ultimo
#     mes ni toda la historia), amortiguada phi = 0.95 por mes (en 16 meses se recorren 10.6 meses de tendencia y nunca
#     da la vuelta: no hay curvas de regreso);
#   - guardia de saltos: un cambio mensual mayor a k_salto MAD de los cambios de los 24 meses anteriores mueve el nivel
#     pero no entra a la tendencia (en toda la historia, para que la proyeccion no cambie de golpe cuando el salto deja de
#     ser el ultimo mes); si el salto es el ultimo mes, no se proyecta tendencia desde el nuevo nivel
#     (salto_ultimo_sin_tendencia, como la regla de la pendiente combinada);
#   - tope de plausibilidad: la tendencia se reduce, sin invertirse, si a meses_tope meses sacaria el FND del rango de los
#     ultimos 36 meses reales ampliado tope_rango veces el rango; encima iria el patron del mes del ano, que el FND
#     ya no lleva (TIPOS_CON_ESTACIONALIDAD, 2026-10-07).
# beta, phi, k_salto y el tope son supuestos de modelacion declarados, no estimados: toda estimacion por verosimilitud o
# AICc (ETS, SARIMA) lleva la tendencia a cero y aplana (una deriva de 1 % mensual contra un ruido de 10 % no la paga la
# verosimilitud a un mes). Elegido en el banco de pruebas de los 22 FND contra ETS por maxima verosimilitud, SARIMA con
# deriva, Theta y la pendiente combinada: backtest con 9 cortes (4 a 20 meses antes del final) error % mediano / medio
# 13.7 / 20.3 contra 15.9 / 22.2 de la pendiente combinada (gana en 15 de 22 series), ninguna serie fuera del rango de
# 36 meses ni con cambio mayor a 30 %, arranque en el ultimo real en las 22; la malla beta 0.03-0.05 x phi 0.92-0.98 da
# resultados parecidos (no es un optimo puntual). Costo declarado: cada mes real nuevo mueve la tendencia (revision media
# de la proyeccion 10.5 % contra 8.6 % con la pendiente combinada).
HOLT_FND = {
    "alpha": 1.0, "beta": 0.05, "phi": 0.95,
    "k_salto": 5.0, "ventana_salto": 24, "min_cambios_salto": 12,
    "salto_ultimo_sin_tendencia": True,
    "tope_rango": 0.5, "meses_tope": 16,
}
PENDIENTE_COMBINADA = {
    "ventanas": (24, 36),               # rectas candidatas (meses), ademas del plano; la primera da la direccion
    "ventana_meseta": 12,
    "estimador": "theil",               # "theil" (Theil-Sen) o "mco" (minimos cuadrados)
    "estimador_serie": {"FACTOR GTO": "mco"},
    "t_clara": 2.5,                     # |t| (AR(1)) de la recta de 24 meses: tendencia clara
    "t_meseta": 1.0,                    # t (AR(1)) de la recta de 12 meses en la direccion de la de 24: debajo, meseta
    "series_gto_meseta": ("FACTOR GTO",),   # en meseta el plano se queda en el promedio (sin la regla de la mitad)
    "k_salto": 5.0,                     # ultimo cambio mensual > k_salto x MAD de los cambios de 24 meses: salto
    "series_salto": ("FND", "CESION"),  # el GTO cambia por escalones y el MR ya arranca del nivel de 3 meses
    "amortiguacion": 0.95,              # el mes k suma 0.95^k de la pendiente
    "tope_rango": 0.5,                  # rango de 36 meses +- 0.5 veces el rango (None = sin tope)
    "meses_tope": 16,
    "min_obs": 6,                       # menos observaciones: sin pendiente
}
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
# Ramos estatutarios: la CNSF otorga sus IS y sus LAGs, asi que en HParametros no se modelan; la proyeccion de los
# indices y de los LAG 1-10 se queda fija en el ultimo valor real (si el ultimo real tiene mas de MESES_SIN_DATO_MAX
# meses no se proyecta, como en los demas ramos).
RAMOS_ESTATUTARIOS = ("37", "71", "73", "100")   # ramos de reserva (Salud, TEV, Hidro, Credito)
HP_ESTATUTARIOS = {MAPA_RAMO_LAG[r] for r in RAMOS_ESTATUTARIOS}   # su clave en HParametros
REGLA_ESTATUTARIO = "Ramo estatutario (IS y LAG de la CNSF): se mantiene el ultimo valor real"
PENDIENTE_DEFECTO = (0.9, 0.5, 0.2)   # parte pendiente por ano si el ramo no trae LAG en HParametros
UMBRAL_PRIMA_FACTOR = 5e6        # prima de 12 meses minima del grupo (USD) para usar el factor
UMBRAL_RESERVA_FACTOR = 1e6      # reserva minima (USD) para usar el factor
RANGO_FACTOR = (0.01, 10.0)      # factor (reserva / exposicion) sano al ultimo mes
MAX_MESES_PRIMA_ESTIMADA = 2     # meses maximos entre el ultimo real de primas y el de reservas
SENSIBILIDAD_PRIMA = (0.9, 1.1)  # escenarios de prima del ano siguiente para la sensibilidad
# Escenarios PND / PD (Danos RRC y SONR): la reserva se escribe sobre la prima no devengada (RRC) o devengada (SONR)
# implicita en la valuacion. BEL RRC = PND x IS RRC y BEL SONR (IBNR) = PD x IS SONR media x (1 - LAG 1), asi que con
# el BEL, el indice y el LAG 1 reales de cada mes (renglon Real de HParametros) se despeja PND = BEL / "Ind Sin RRC" y
# PD = BEL SONR / ("Ind Sin SONR Media" x (1 - "LAG 1")). Esa base se liga a la prima tomada con FA = PND / PE (PE =
# prima de los ultimos 12 o 18 meses, anualizada) y los gastos y el margen se expresan sobre ella: FG = GTO / PND y
# FM = MR / PND (MR SONR / PD). Proyeccion: FA sin pendiente (su nivel con el patron del mes; la desviacion se conserva
# o se desvanece, lo decide el backtest), PE con la prima real, el reforecast y el presupuesto, IS y LAG 1 con su
# proyeccion de HParametros, FG el ultimo valor (es un % anual, el mismo en casi todos los ramos) y FM con SES como las
# demas razones. PND = FA x PE; BEL = PND x IS (x (1 - LAG 1) en SONR); GTO = FG x PND; MR = FM x PND.
USAR_ESCENARIOS_PND = True
ESCENARIOS_PND = {"PE12": 12, "PE18": 18}   # escenario -> meses de prima tomada en la base del factor (FA)
BD_CON_ESCENARIO_PND = None      # None: la BD principal no cambia y cada escenario va en su propio archivo
                                 # (..._Proyeccion_PE12.xlsx, ..._PE18.xlsx); "PE12" o "PE18": la BD principal usa ese
                                 # escenario en las series donde aplica
INDICE_BASE_PND = {"RRC": ("Ind Sin RRC", "PND"), "SONR": ("Ind Sin SONR Media", "PD")}   # indice y nombre de la base
LAG_BASE_PND = {}                # {"SONR": "LAG 1"}: la base se despeja con el indice x (1 - ese LAG). Por decision
                                 # del area la PND / PD vuelve a BEL / IS y el LAG entra en la PEACUMULADA de SONR
PERSISTENCIAS_PND = (1.0, "estimada")   # desviacion del FA: se conserva (1) o se desvanece con su rho
RANGO_FA = (0.001, 20.0)         # FA (base / prima anualizada) sano al ultimo mes
INDICES_PND_EN_BD = True         # columnas a la derecha de BD_Montos_RRC_SONR con los indicadores por ramo: un bloque
                                 # por indicador, con una columna por ramo ("PND/PD 10", "FA 10", ...)
COLUMNAS_INDICES_PND = {"PND/PD": "#,##0", "FA": "0.0000", "FACTOR GTO": "0.00%", "FACTOR MR": "0.00%", "CESION": "0.00%",
                        "IS (RL)": "0.00%", "LAG (RL)": "0.00%", "PE FCST": "#,##0", "PRIMA N AÑOS": "#,##0",
                        "PEACUMULADA": "#,##0", "FD/FND": "0.0000", "IS (FA)": "0.00%"}
                                 # todos los bloques van en todos los renglones de RRC y SONR (historia y
                                 # proyeccion), aunque el modelo no los use; las divisiones con SI.ERROR (0 en un 0/0)
INDICES_PND_RETIRADOS = ("PD/PND CORREGIDA", "BEL", "BEL (MEC)", "FD/FND (MEC)")   # bloques de versiones anteriores: se limpian
AGRUPAR_BLOQUES = True           # agrupa (esquema de Excel) las columnas de cada bloque con varios ramos, incluidas las
                                 # RAM_: queda visible la primera (ramo 10) y el boton +/- junto a ella
INDICES_PND_CAPTURA = {"PE FCST": ("RRC", "SONR")}   # datos de captura: PE FCST sale de la hoja HOJA_PE_RAMO (PExRamo,
                                 # reforecast y FCST; 0 en un mes que ninguna trae). En un mes sin PE se puede capturar
                                 # en el renglon BEL de la BD de entrada (columna "<indicador> <ramo>"): un numero entra a
                                 # la PE y a las sumas; una formula se conserva en la celda
INDICES_PND_FORMULAS = True      # True: los indicadores van como formulas de Excel (celdas del indice y del LAG 1 en
                                 # HParametros, BEL / indice, base / PE de la hoja Primas_PE, GTO / PND, MR / base, ...);
                                 # False: como valores
HOJA_PRIMAS_PE = "Primas_PE"     # hoja que se agrega a la BD de Danos con la prima mensual por grupo y su PE (formulas)
# PE FCST (prima tomada del mes por ramo): la historia de la base PExRamo (por ramo y mes de ocurrencia) y el ano del
# FCST como lo arma la hoja ER_ram del archivo de FCST (por mes, -SUMAR.SI.CONJUNTO(CtaMens!AMOUNT; GL_ACCT = 61;
# CALMONTH = mes; RamoN = ramo)). Se agrega a la BD la hoja HOJA_PE_RAMO (prima del mes en valores y su suma de 12
# meses como formula) y los bloques "PE FCST <ramo>", "PRIMA N AÑOS <ramo>" y "PEACUMULADA <ramo>" la referencian.
ARCHIVO_PE_FCST = ENTRADAS / "FCST_2027.xlsb"
PATRON_PE_RAMO = "PExRamo*"      # base historica de PE por ramo y mes (en entradas/): periodo, Ramo, Sramo, PmaTom
PATRON_PE_RFCST_FA = "*RCST*FA*.xlsx"    # reforecast del ano por mes y ramo (en entradas/; hoja Ana_RFCST<aa>_FA: MesProc,
                                 # Tipo Rea, Susc, RAMO, Primas Tomadas USD y MXN): PE de los meses entre PExRamo y el
                                 # FCST (sep-dic 2026). Sin el archivo, esos meses salen del reforecast por grupo de primas.py
PATRON_IS_FA = "PPTO*FA*.xlsx"   # indices de siniestralidad de la funcion actuarial (en entradas/; una hoja con Ramo,
                                 # MesProc, IS RRC e IS SONR, desde el primer mes proyectado): bloque "IS (FA) <ramo>",
                                 # con IS RRC en los renglones de RRC e IS SONR en los de SONR (como el IS (RL)); N/A en
                                 # los meses y ramos que no trae. El BEL por FND y el PND / PD lo usan en los ramos de
                                 # RAMOS_IS_FA_BEL; los demas ramos siguen con el IS (RL)
COLUMNAS_TABLERO_PND = ("PND/PD", "FACTOR GTO", "FACTOR MR", "CESION", "IS (RL)", "IS (FA)", "PE FCST", "PRIMA N AÑOS",
                        "PEACUMULADA", "FD/FND")   # indicadores por ramo y mes que van a la hoja HOJA_INDICADORES_RAMO del
                                 # diagnostico (los mismos valores de los bloques de la BD principal), para el tablero
HOJA_INDICADORES_RAMO = "Indicadores_Ramo"
COLUMNAS_METODO_AREA = ("PND/PD", "FACTOR MR", "CESION", "FD/FND")   # historia del metodo del area (BEL_METODO_AREA) que
SUFIJO_METODO_AREA = "(metodo del area)"     # va a HOJA_INDICADORES_RAMO como "<indicador> (metodo del area)", para el tablero
HOJA_IS_FA = "IS_FA"             # hoja de apoyo en la BD de Danos con la tabla del archivo de la funcion actuarial
RAMOS_IS_FA_BEL = {"RRC": ("40", "50", "80", "90"), "SONR": ("40", "50", "80", "90")}
                                 # ramos cuyo BEL por FND usa el IS de la funcion actuarial (IS (FA)) en lugar del IS (RL)
                                 # de HParametros, por decision del area: BEL = IS (FA) x PEACUMULADA x FND y PND / PD =
                                 # BEL / IS (FA) desde el primer mes proyectado (la historia y el FND siguen con el IS (RL));
                                 # en un mes sin IS (FA) se usa el IS (RL) con aviso. Los demas ramos siguen con el IS (RL).
BEL_METODO_AREA = {("SONR", "80"): (3, 2)}
                                 # series cuyo BEL no registra SAP pero que el area si calcula con su metodo (SONR 80: la
                                 # BD trae BEL 0 desde 202206 y la hoja "Base SONR" de los Res_Rvas lo calcula). Mientras
                                 # el BEL real del ultimo mes no sea positivo, la historia del FND, del FACTOR MR y de la
                                 # CESION sale del BEL, MR, BRUTO e IRR en USD de la hoja "Base <reserva>" de los
                                 # Res_Rvas de entradas/ (PATRON_RES_RVAS), con los escenarios en orden de preferencia por mes
                                 # (3 = Recalculo / Backtesting; 2 = Reforecast, que en los meses reales coincide con el 3
                                 # y trae 202512, que el 3 no trae). El BEL proyectado queda como en los demas ramos:
                                 # IS x PEACUMULADA x FND, formulado. La historia de la BD (SAP) no se toca. {} = esas
                                 # series siguen con el modelo (BEL 0)
PATRON_RES_RVAS = r"res[\s_\-.]*rvas.*\.(xlsx|xlsm)$"   # Res_Rvas de entradas/ (TC real y BEL del metodo del area), en
                                 # cualquier parte del nombre y sin distinguir mayusculas ni el separador: "Res_Rvas_2026",
                                 # "Res Rvas 2026", "Copia de Res_Rvas_2026", "Res_Rvas_2026 - copia". Se leen en orden de
                                 # nombre y el ultimo gana en un mes repetido; los de nombre exacto ("Res_Rvas_2026.xlsx")
                                 # van al final, asi que ganan sobre las copias
PERFIL_REFORECAST = "FCST"       # meses del reforecast (entre PExRamo y el FCST, hoy sep-dic 2026): "FCST" = el total de
                                 # esos meses por ramo se reparte entre ellos con la mezcla mensual de los mismos meses del
                                 # FCST del ano siguiente (el archivo de reforecast concentra la prima en uno o dos meses,
                                 # septiembre u octubre en casi todos los ramos, y deja casi vacios los ultimos, lo que
                                 # achata la PEACUMULADA de diciembre); None = los meses del archivo tal cual
RAMOS_PERFIL_REFORECAST = None   # None = todos los ramos; o una tupla de ramos de la BD, p. ej. ("10", "60")
COLUMNA_IS_FA = {"RRC": "IS RRC", "SONR": "IS SONR"}   # columna del archivo para cada reserva
MAX_IS_FA = 10.0                 # aviso si un indice del archivo pasa de 1,000 % (p. ej. si viene en % y no en razon)
MONEDA_PE_RFCST_FA = "MXN"       # "MXN": Primas Tomadas MXN entre el TC del mes del proyecto (tipo_cambio.py, FCST de
                                 # Inversiones), por indicacion del area; "USD": Primas Tomadas USD del archivo tal cual
                                 # (convertidas con el TC de su columna TC)
MONEDA_PE_RAMO = "MXN"           # PExRamo viene en pesos (dividida entre el TC del mes cuadra con la prima real en USD);
                                 # antes del primer mes con TC en la BD (202201) se usa ese primer TC
SUBRAMO_A_BD = {"30": {"30": "30", "31": "30", "32": "30", "33": "30", "34": "34", "35": "34", "36": "34",
                       "37": "37", "38": "37", "39": "37"},
                "70": {"71": "71", "73": "73", "75": "73", "70": None, "72": None, "74": None}}
                                 # ramos de PExRamo que se abren por subramo (catalogo de centros de beneficio de
                                 # primas.py: 31-33 Acc Per., 34-36 GMM, 37-39 Salud, 71 TEV, 73 y 75 Hidro); None = se
                                 # reparte entre los demas subramos del ramo en proporcion a su prima del mes (el 70, 72
                                 # y 74 entre TEV e Hidro). Los demas ramos van completos al ramo de la BD con su numero
HOJA_PE_FCST = "PE_FCST"         # (hoja de versiones anteriores: se quita)
HOJA_PE_RAMO = "PE_RAMO"
MESES_PRIMA_N_ANOS = 12          # PRIMA N AÑOS = suma de los ultimos 12 meses de PE FCST; PEACUMULADA de RRC = esa suma
GRUPOS_CON_MEZCLA = ("30", "70")   # grupos de prima con varios ramos de la BD (30: 30, 34 y 37; 70: 71 y 73): en el
                                 # reforecast y en el FCST se toma el total del grupo y se reparte con la mezcla de
                                 # PExRamo de los ultimos 12 meses (el FCST pone casi todo el grupo 30 en Acc Per. y
                                 # reparte TEV / Hidro distinto que la historia). () = el FCST por ramo tal cual
AGREGAR_MESES_PRIMA = True       # agrega al final de BD_Montos_RRC_SONR los meses con PE por ramo anteriores al primer
                                 # mes de la BD (hoy 201901 a 202112, de PExRamo), con los conceptos de RRC y SONR y sin
                                 # montos (no hay BEL ni IS), para que los bloques lleven la prima y su acumulado
TEXTO_SIN_DATO = "N/A"           # en los bloques: no hay IS (o LAG) en HParametros o no hay BEL para ese mes y ramo, y lo
                                 # que se calcula con ellos
ANIOS_LAG_PEACUMULADA = {"SONR": 3}    # SONR: PEACUMULADA = LAG 1 x PRIMA N AÑOS del mes + LAG 2 x la del mismo mes del
                                 # ano anterior + LAG 3 x la de dos anos antes (LAG k de HParametros del mes, real o
                                 # proyectado). 3 anos: con PExRamo desde 2019 no alcanzan 10
# BEL por FND (Danos RRC y SONR): desde el primer mes proyectado BEL = IS x PEACUMULADA x FND, con FND = PND / PEACUMULADA
# de la historia proyectado con la tendencia (TIPO_MODELO_FND), el IS y los LAG proyectados de HParametros y la PE del
# FCST. GTO y MR = su razon proyectada sobre el BEL (la del modelo) x el BEL nuevo; BRUTO = BEL + GTO + MR; IRR = BRUTO x
# la razon de cesion del modelo; NETO = BRUTO - IRR. En la BD principal van como formulas en las columnas RAM_.
USAR_BEL_POR_FND = True
TIPO_MODELO_FND = "fnd"          # el FND se proyecta en logaritmos, sin patron del mes (TIPOS_CON_ESTACIONALIDAD), con el modelo de
                                 # MODELO_POR_TIPO["fnd"] (Holt amortiguado con guardia de saltos, HOLT_FND), anclado al
                                 # ultimo real: la proyeccion arranca donde esta la serie
MIN_MESES_FND = 12               # meses minimos de FND real para proyectarlo
TIPO_MODELO_FACTORES = {"FACTOR GTO": "factor_log", "FACTOR MR": "factor_log", "CESION": "razon"}
                                 # CESION: "razon" = nivel suavizado sin tendencia (SES, como las demas razones de cesion
                                 # del modelo): depende de los contratos de reaseguro, y con la tendencia la cesion de Vida
                                 # (RRC 10) subia de 62.5 % a 86 % y la RRC retenida bajaba de mas (observacion del area).
                                 # FACTOR GTO (GTO / PND) y FACTOR MR (MR / PND o PD) de las series con BEL por FND: reales
                                 # hasta el ultimo mes y, desde el primer mes proyectado, la pendiente combinada
                                 # (PENDIENTE_COMBINADA) sin patron del mes, en logaritmos ("factor_log"; por
                                 # decision del area siguen su comportamiento y no una recta). "factor" = la pendiente
                                 # combinada en niveles (puntos por mes), alternativa para la CESION: en logaritmos la
                                 # tendencia es de crecimiento % constante y la de RRC 10, que paso de 1 % a 63 %, llegaba a
                                 # 100 % en tres meses.
                                 # GTO = PND x FACTOR GTO, MR = PND x FACTOR MR, BRUTO = BEL + GTO + MR, IRR = BRUTO x CESION,
                                 # NETO = BRUTO - IRR
# Cesion (IRR / BRUTO) por ramo, por indicacion del area (2026-10-07), sobre la proyeccion de la CESION del BEL por FND; los
# demas ramos siguen con el modelo (SES). La clave es (reserva, ramo de la BD); hoy solo RRC: los niveles pedidos son los de
# la cesion del RRC (la del SONR de esos ramos es otra y se queda con el modelo).
CESION_OBJETIVO = {("RRC", "60"): 0.39, ("RRC", "71"): 0.56, ("RRC", "90"): 0.15}
                                 # nivel al que llega la cesion poco a poco: en linea recta desde el ultimo real hasta
                                 # CESION_OBJETIVO_MES y de ahi en adelante se queda en el objetivo ("que suba poco a poco
                                 # hasta llegar a 39 %", "que suba lentamente a 56 %", "que suba a 15 %")
CESION_OBJETIVO_MES = None       # mes AAAAMM en que llega al objetivo; None = el ultimo mes proyectado (PERIODO_FIN)
CESION_TENDENCIA = {("RRC", "50"): 12}
                                 # ramo -> meses de historia cuya tendencia sigue: recta Theil-Sen de los ultimos 12 meses
                                 # reales de la cesion (puntos por mes), frenada como la pendiente combinada
                                 # (PENDIENTE_COMBINADA["amortiguacion"] por mes) y acotada a DOMINIO_CESION ("que tome la
                                 # tendencia del ultimo ano, poco a poco")
# Margenes del BEL por FND fijos (indicacion del area, 2026-10-07): FACTOR GTO (GTO / PND) y FACTOR MR (MR / PND o PD) se
# quedan desde el primer mes proyectado en su ultimo real (202608) en todas las series con BEL por FND, en lugar de
# proyectarse con la pendiente combinada. Tambien en el backtesting (en su ultimo real, 202512). () = se proyectan.
FACTORES_BEL_FIJOS = ("FACTOR GTO", "FACTOR MR")
                                 # (en las series sin BEL por FND, p. ej. SONR 37, los margenes GTO / BEL y MR / BEL del
                                 # modelo tambien se quedan en su ultimo real; un real negativo se lleva a 0)
UMBRAL_MARGEN_ATIPICO = 0.30     # aviso si el margen que se fija se aleja mas de 30 % de la mediana de sus 12 meses previos
# Suavizado del BEL entre diciembres (indicacion del area, 2026-10-07): en estas series (reserva, ramo) el BEL de cada
# diciembre proyectado (y del ultimo mes proyectado) se queda como lo da IS x PEACUMULADA x FND, y los meses de en medio
# siguen una linea en logaritmos entre el ultimo real y esos diciembres (crecimiento parejo) mas el patron del mes de la
# historia del BEL (ultimos MESES_ESTACIONALIDAD meses), puesto en cero en los meses ancla. El FND de esos meses se
# ajusta para que IS x PEACUMULADA x FND de el BEL suavizado (la formula de la BD no cambia) y MR, BRUTO, IRR y NETO lo
# siguen. Patron: "credibilidad" = ponderado por su credibilidad (Buhlmann, como el patron de los montos del modelo);
# "observada" = el promedio por mes tal como se observo, sin ponderar; "ninguna" = solo la linea. No va en el backtesting.
SUAVIZAR_BEL = {("SONR", "50"): "credibilidad"}
# Backtesting (Danos, 2026-10-07): el mismo calculo de la proyeccion (modelo de las series, IS y LAG de HParametros
# proyectados, BEL = IS x PEACUMULADA x FND, factores y cesion), pero con la historia cortada en el mes anterior a
# BACKTESTING_DESDE, para los meses BACKTESTING_DESDE a BACKTESTING_HASTA. Va al final de BD_Montos_RRC_SONR, despues de
# todos los conceptos, con CONCEPTO "<BACKTESTING_ETIQUETA> <concepto>" (p. ej. "BACKTESTING RRC BEL"), un bloque de meses por
# concepto, en valores (sus parametros son los de la fecha de corte, no los de la hoja), con los bloques de indicadores del
# mes; y en las hojas Backtesting_Resumen y Backtesting_Mensual del diagnostico contra lo real (y contra la proyeccion
# vigente en los meses que todavia no son reales). No cambia la proyeccion. La PE es la misma de la proyeccion (la real
# en los meses reales): el backtesting mide el metodo dada la prima. No lleva las indicaciones del area de la cesion
# (CESION_OBJETIVO, CESION_TENDENCIA: se fijaron con la historia a 202608 y para el horizonte de la proyeccion) ni el
# factor de prima. El IS (FA) entra en los meses que trae el archivo, como en la proyeccion.
BACKTESTING = True
BACKTESTING_DESDE = 202601       # primer mes del backtesting (la historia llega al mes anterior)
BACKTESTING_HASTA = 202612       # ultimo mes del backtesting
BACKTESTING_ETIQUETA = "BACKTESTING"
MIN_REAL_BACKTESTING = 1e5       # USD: con un real menor a esto (promedio por mes, o en el mes) no se calcula el error % (p. ej.
                                 # SONR 80, que SAP registra en 0 y el backtesting saca del metodo del area)
# RFV por prima (Fianzas, 2026-10-07): la RFV se descompone como la reserva de Danos (BEL = IS x PEACUMULADA x FND). La
# metodologia vigente constituye la reserva de cada contrato en vigor sobre su prima de reserva (prima tomada menos
# cargas, comisiones y gastos, mas el gasto de administracion) o sobre su monto afianzado por (omega + alfa), y la mantiene
# mientras el contrato sigue en vigor; con los montos de la BD (por ramo, sin contratos) eso se resume en:
#   PRIMA 24M = prima tomada de Fianzas de los ultimos MESES_PRIMA_RFV meses (MXN; hoja HOJA_PT_RAMO)
#   FRV       = RFV BRUTO (MXN) / PRIMA 24M: factor de reserva (lo que queda constituido por peso de prima reciente:
#               carga, comisiones, gasto de administracion, omega + alfa y permanencia), real hasta el ultimo mes y
#               proyectado con TIPO_MODELO_FRV
#   RFV BRUTO = PRIMA 24M x FRV / TC ; RFV IRR = RFV BRUTO x CESION (IRR / BRUTO, proyectada como la de Danos) ;
#   RFV NETO  = RFV BRUTO - RFV IRR. La RCONT se queda con su modelo (no guarda una relacion estable con la prima).
# 24 meses porque en el backtesting con la historia a 202512 (meses 202601 a 202608 reales, la prima real y el TC real de
# SAP) fue la ventana que menos fallo en la RFV BRUTO total: 1.5 % de error medio con 24 meses contra 3.0 % con 12,
# 3.6 % con 36, 3.4 % con 48 y 3.9 % con 60 (repetir la RFV BRUTO sin prima: 10.3 %); con la historia a 202602, 2.4 %
# contra 4.9 % o mas. SES y repetir el ultimo FRV quedan parejos (1.5 % contra 1.4 %; 2.4 % contra 2.7 %); la tendencia
# (Holt amortiguado) falla mas (2.1 % y 3.6 %).
USAR_RFV_POR_PRIMA = True
RAMOS_RFV_POR_PRIMA = None       # None = todos los ramos con prima y RFV; o una tupla, p. ej. ("140", "160", "170"): los demas
                                 # siguen con el modelo de la serie (sin formula)
MESES_PRIMA_RFV = 24             # meses de prima tomada de la PRIMA 24M (si cambia, cambia el encabezado del bloque)
TIPO_MODELO_FRV = "razon"        # "razon" = nivel suavizado sin tendencia (SES); "fnd" = Holt amortiguado con guardia
MIN_MESES_FRV = 12               # meses minimos de FRV real para proyectarlo
HOJA_PT_RAMO = "PT_RAMO"         # hoja de la BD de RFV con la prima tomada del mes por ramo (MXN) y su suma de 24 meses
# Factores de la metodologia del area (Resumen de la metodologia de Reservas de Fianzas en Vigor y script de FCST de
# Fianzas): en el reafianzamiento extranjero proporcional y en el no proporcional (el "segmento PR"), RFV = PR + GA con
# PR = PT - CAT - CRT - GAT - MUT y GA = PR x alfa; en el proporcional de Mexico y el facultativo, RFV = MA x (omega +
# alfa_k) (sin monto afianzado en las bases); IRR = RFV x RC x FCR, FCR = 1 - PD. En la BD de RFV, por ramo:
# RFV BRUTO = PRIMA 24M x FPR x (1 + %GA) x FV / TC, FPR = %SEG PR x (1 - %COM PR - %CARGAS), y FV el factor residual
# (permanencia, segmento de monto afianzado y TC); IRR = RFV BRUTO x RC x FCR. FV y RC se proyectan con los modelos del
# FRV y de la cesion; los demas factores salen de los datos o del area. Con los factores medidos, la RFV proyectada es
# la misma que sin los bloques; COMISION_RFV y PD_FIANZAS la mueven (y lo mismo cambiarlos en la hoja PT_RAMO).
FACTORES_RFV = True
CARGAS_RFV = 0.171903149570019   # %CARGAS sobre la prima tomada (%CargasPma del script de FCST de Fianzas del area):
                                 # 4.268 % de gasto de administracion (GAT, el mismo alfa) + 12.922 % de costos de
                                 # cobertura y margen de utilidad (CRT + MUT; su reparto no esta documentado)
GASTO_ADMON_RFV = 0.0426831495700193
                                 # %GA: gastos de administracion sobre la prima de reserva (GA = PR x alfa; %GastoAdmon del
                                 # mismo script)
COMISION_RFV = None              # %COM PR de la proyeccion por ramo, p. ej. {"160": 0.40}; None = el medido (comisiones /
                                 # prima tomada del segmento PR en la base del real por contrato, BDReal). Con otro valor,
                                 # la FPR proyectada cambia y la RFV se mueve con ella (FV se queda)
PD_FIANZAS = {}                  # PD de la proyeccion por ramo (Anexo 8.20.2 de la CUSF), p. ej. {"160": 0.003}; sin el
                                 # ramo, la ultima medida en Res_Rvas (CASTIGO / (IRR + CASTIGO) del metodo del area). Con
                                 # otro valor, la FCR cambia y la IRR se mueve con ella (RC se queda)
# Segmento de monto afianzado (proporcional de Mexico): RFV MA = MA x (omega + alfa_k) del Anexo 5.15.3, con el MA del
# CSV del area (MontosAfianzados: real y el estimado del area). En los ramos de MA_RFV_RAMOS se proyecta aparte: FRV =
# FRV residual del modelo + RFV MA / PRIMA 24M, con el residual = (RFV BRUTO x TC - RFV MA) / PRIMA 24M proyectado con el
# mismo modelo del FRV. En 140 y 170 la RFV MA es 54 a 63 % y 76 a 85 % de la RFV y el backtest con 12 meses o mas de
# historia (cortes 202512, 202602 y 202604) baja el error de 8.0 a 3.5 % (140) y de 1.9 a 1.4 % (170); en 150 (4 a 7 %
# de la RFV) y 160 (6 %) no mejora y el resultado depende de como se tratan los meses sin MA: siguen con el FRV total y
# su RFV MA es informativa. Despues del ultimo mes del CSV (202612), el MA queda fijo en ese ultimo valor (ningun insumo
# trae MA de 2027; supuesto declarado, editable en PT_RAMO como sensibilidad).
MA_RFV = True
MA_RFV_RAMOS = ("140", "170")
PATRON_MONTOS_AFIANZADOS = "MontosAfianzados*.csv"   # en entradas/ (no toma Proy_MontosAfianzados.csv)
OMEGA_FIANZAS = {"130": 0.0147, "140": 0.0147, "150": 0.0079, "160": 0.0023, "170": 0.0081}
                                 # omega: indice de reclamaciones del mercado (Omega del script del area)
ALFA_FIANZAS = {"130": 0.0103, "140": 0.0103, "150": 0.003, "160": 0.0009, "170": 0.0018}
                                 # alfa_k: indice de gastos de administracion (FactorGastos del script del area)
FACTOR_MA_FIANZAS = {"130": 16.34, "140": 16.34, "150": 35.05, "160": 80.13, "170": 41.8}
                                 # Factor MA del script del area: constante fija; el script no la usa en ningun calculo y
                                 # aqui tampoco (va en PT_RAMO y en la BD tal cual)
PATRON_XDEFAULT = "xDefault*.csv"            # PD por poliza del area (referencia; la PD de la IRR sigue siendo la del castigo)
MESES_PD_XDEFAULT = (24, 121)    # ventanas de aPOG_MesProc de la PD de referencia (121 = 10 anos como el area: del mismo
                                 # mes de hace 10 anos al mes de valuacion)
PATRON_VIGMAX_PROP = "xVigMaxProp*.csv"      # bandera Id Uti por contrato (comision sobre utilidades)
PATRON_COM_UTIL = "xComUtil*.csv"            # contratos con la comision sobre utilidades ya pagada
COM_UTILIDAD_FIANZAS = {"160": 0.0668602076612849, "170": 0.0359763798998371}
                                 # %ComUti del script del area (Id Uti = 1 y sin pagar): se mide y se reporta; no entra
                                 # al FPR (40 % de la prima del 160 son contratos nuevos sin bandera: el medido es un piso)
ESCENARIOS_FIANZAS_AREA = (2,)   # escenarios de la hoja Base FIANZAS de los Res_Rvas (2 = metodo del area)
TOLERANCIA_AREA_SAP = 0.10       # la PD de un mes solo se mide si la RVABRUTA del area queda a menos de 10 % de la RFV
                                 # BRUTO de SAP (en ago y sep-25 el area se aparta de SAP)
RAMO_FCST_FIANZAS = {"130": "130", "140": "140", "150": "150", "160": "160", "170": "170"}
                                 # Ramo2 de CtaMens del FCST -> ramo de la BD de RFV (la prima del ano siguiente)
RAMO_RFCST_FIANZAS = "130"       # RAMO del reforecast por mes (RCST_FA) con toda la prima de Fianzas: se reparte entre los
                                 # ramos de la BD de RFV con la mezcla de PExRamo de los ultimos 12 meses
CUENTA_PE_FCST = "61"            # cuenta de prima tomada en CtaMens (la que suma ER_ram)
CUENTA_COM_FCST = "53"           # cuenta de comisiones en CtaMens (hoja Valores del FCST: Comisiones 5310...); Fianzas
RAMO_FCST_A_BD = {"10": "10", "31": "30", "35": "34", "39": "37", "40": "40", "46": "40", "50": "50", "60": "60",
                  "71": "71", "73": "73", "80": "80", "90": "90", "100": "100", "110": "110"}
                                 # Ramo2 de CtaMens -> ramo de la BD (Resp. Civil trae 40 y 46; Fianzas, 140 a 170,
                                 # no esta en la BD de Danos)
RAMO_RFCST_FA_A_BD = {**RAMO_FCST_A_BD, "34": "34", "37": "37"}
                                 # RAMO del reforecast por mes (subramo del catalogo: 31 Acc Per., 34 GMM, 37 Salud y los
                                 # demas con el numero del ramo) -> ramo de la BD; Fianzas (130) no esta en la BD de Danos
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


def _recta_robusta(w, estimador: str = "theil"):
    """Pendiente y estadistico t de la recta sobre w: Theil-Sen (mediana de las pendientes entre todos los pares de
    meses) o minimos cuadrados ("mco"); el error estandar se corrige por la autocorrelacion de primer orden de los
    residuos (rho acotada a [0, 0.95]: n efectivo = n (1 - rho) / (1 + rho))."""
    w = np.asarray(w, dtype=float)
    n = len(w)
    t = np.arange(n, dtype=float)
    if estimador == "theil":
        i, j = np.triu_indices(n, 1)
        b = float(np.median((w[j] - w[i]) / (j - i)))
        a = float(np.median(w - b * t))
    else:
        b, a = (float(v) for v in np.polyfit(t, w, 1))
    r = w - (a + b * t)
    sxx = float(np.sum((t - t.mean()) ** 2))
    s2 = float(np.sum((r - r.mean()) ** 2)) / max(1, n - 2)
    se = math.sqrt(s2 / sxx) if sxx > 0 and s2 > 0 else math.inf
    rho = 0.0
    if n >= 4 and np.std(r) > 0:
        rho = float(np.corrcoef(r[:-1], r[1:])[0, 1])
        rho = min(max(0.0, rho if np.isfinite(rho) else 0.0), 0.95)
    if np.isfinite(se):
        se *= math.sqrt((1 + rho) / (1 - rho))
    t_est = b / se if np.isfinite(se) and se > 0 else (0.0 if b == 0 else math.copysign(99.0, b))
    return b, float(t_est)


def pendiente_combinada(d, z, nombre: str = ""):
    """Pendiente mensual (escala del modelo, sin amortiguar ni topar) del FND y los factores del BEL por FND
    (PENDIENTE_COMBINADA) y el detalle: d = serie sin el patron del mes, z = serie en la escala del modelo con el patron
    (para la regla de salto: un mes que solo se aparta del patron no es salto)."""
    P = PENDIENTE_COMBINADA
    d = np.asarray(d, dtype=float)
    det = {"regla_pendiente": "", "clara": False, "meseta": False, "salto": False}
    if len(d) < P["min_obs"]:
        det["regla_pendiente"] = f"menos de {P['min_obs']} meses: sin pendiente"
        return 0.0, det
    est = P["estimador_serie"].get(nombre, P["estimador"])
    v_dir, v_larga = P["ventanas"]
    b_dir, t_dir = _recta_robusta(d[-v_dir:], est)
    b_larga, _ = _recta_robusta(d[-v_larga:], est)
    det.update({"pendiente_24": b_dir, "t_24": t_dir, "pendiente_36": b_larga})
    usar_larga = np.sign(b_larga) != -np.sign(b_dir)             # la de 36 no va en contra de la de 24
    if len(d) < 12:
        b = float(np.mean([0.0, b_dir, b_larga]))
        det["regla_pendiente"] = "menos de 12 meses: promedio de plano y rectas"
        return b, det
    b12, t12 = _recta_robusta(d[-P["ventana_meseta"]:], est)
    det.update({"pendiente_12": b12, "t_12": t12})
    if nombre in P["series_salto"] and len(d) >= 13 and z is not None:
        dif = np.diff(np.asarray(z, dtype=float)[-24:])
        mad = float(np.median(np.abs(dif - np.median(dif))))
        if mad > 0 and abs(float(dif[-1])) > P["k_salto"] * mad:
            det.update(salto=True, regla_pendiente=f"salto del ultimo mes ({abs(float(dif[-1])) / mad:.1f} MAD): "
                                                    "sin tendencia desde el nuevo nivel")
            return 0.0, det
    clara = abs(t_dir) >= P["t_clara"]
    meseta = bool(t12 * np.sign(b_dir) < P["t_meseta"])
    det.update(clara=clara, meseta=meseta)
    if meseta and nombre not in P["series_gto_meseta"]:
        det["regla_pendiente"] = "meseta: los ultimos 12 meses no confirman la recta de 24; mitad de su pendiente"
        return 0.5 * b_dir, det
    rectas = [b_dir] + ([b_larga] if usar_larga else [])
    if clara:
        rectas = [b for b in rectas if np.sign(b) == np.sign(b_dir)]
    con_plano = not clara or meseta
    valores = rectas + ([0.0] if con_plano else [])
    det["regla_pendiente"] = (("tendencia clara: " if clara else "") + ("promedio de " if len(valores) > 1 else "")
                              + " y ".join((["plano"] if con_plano else [])
                                           + [f"recta de {v} meses" for v, b in ((v_dir, b_dir), (v_larga, b_larga))
                                              if b in rectas]))
    return float(np.mean(valores)) if valores else 0.0, det


def _tope_rango(b: float, a0: float, y, escala_log: bool, phi: float | None = None, tope: float | None = None,
                meses: int | None = None) -> float:
    """Reduce la pendiente (nunca la invierte) para que a meses_tope meses la tendencia quede dentro del rango de los
    ultimos 36 meses reales ampliado tope_rango veces ese rango (phi, tope y meses: los de PENDIENTE_COMBINADA si no
    se dan)."""
    P = PENDIENTE_COMBINADA
    phi = P["amortiguacion"] if phi is None else phi
    tope = P["tope_rango"] if tope is None else tope
    meses = P["meses_tope"] if meses is None else meses
    y36 = np.asarray(y, dtype=float)[-36:]
    lo, hi = float(y36.min()), float(y36.max())
    lo, hi = lo - tope * (hi - lo), hi + tope * (hi - lo)
    pasos = float(np.sum(phi ** np.arange(1, meses + 1)))
    if escala_log:
        lim = math.log(hi) if b > 0 else (math.log(lo) if lo > 0 else -math.inf)
    else:
        lim = hi if b > 0 else lo
    fin = a0 + b * pasos
    if (b > 0 and fin > lim) or (b < 0 and fin < lim):
        b_nuevo = (lim - a0) / pasos
        return b_nuevo if np.sign(b_nuevo) == np.sign(b) else 0.0
    return b


HOLT_GUARDIA = "Holt amortiguado con guardia de saltos"


def _saltos_holt(z):
    """Mascara por mes: True si el cambio mensual de z (en la escala del modelo, con el patron) supera k_salto veces la
    MAD de los cambios de los ultimos ventana_salto meses (ventana que termina en ese mes), como en pendiente_combinada."""
    P = HOLT_FND
    z = np.asarray(z, dtype=float)
    m = np.zeros(len(z), dtype=bool)
    for t in range(1, len(z)):
        dif = np.diff(z[max(0, t - P["ventana_salto"] + 1):t + 1])
        if len(dif) < P["min_cambios_salto"]:
            continue
        mad = float(np.median(np.abs(dif - np.median(dif))))
        if mad > 0 and abs(float(dif[-1])) > P["k_salto"] * mad:
            m[t] = True
    return m


def ajustar_holt_guardia(z, h: int, meses=None, escala_log: bool = False):
    """FND: Holt amortiguado (ETS(A,Ad,N)) con alpha = 1 y guardia de saltos (HOLT_FND) sobre z sin el patron del mes:
    nivel = ultimo real; tendencia b_t = phi b_{t-1} + beta (d_t - l_{t-1} - phi b_{t-1}), que no se actualiza en los
    meses marcados como salto; proyeccion = nivel + b (phi + ... + phi^k) + patron del mes. Intervalo: la variabilidad
    mensual alrededor de la tendencia, que crece con la raiz del horizonte. Mismo contrato que ajustar_tendencia."""
    P = HOLT_FND
    z = np.asarray(z, dtype=float)
    est = factores_estacionales(z, meses) if (ESTACIONALIDAD_MENSUAL and meses is not None) else None
    if est is not None:
        meses = np.asarray(meses, dtype=int)
        s = est["factores"]
        d = z - s[meses - 1]
        estacional_fut = s[(meses[-1] - 1 + np.arange(1, h + 1)) % 12]
    else:
        d, estacional_fut = z, 0.0
    masc = _saltos_holt(z)
    alpha, beta, phi = P["alpha"], P["beta"], P["phi"]
    nivel, b = float(d[0]), 0.0
    for t, x in enumerate(d):
        e = x - (nivel + phi * b)
        nivel = nivel + phi * b + alpha * e
        b = phi * b if masc[t] else phi * b + beta * e
    regla = f"Holt amortiguado (beta {beta}, phi {phi}): tendencia {b:+.4f}/mes"
    if P["salto_ultimo_sin_tendencia"] and len(masc) and masc[-1]:
        b, regla = 0.0, "salto del ultimo mes: sin tendencia desde el nuevo nivel (Holt amortiguado)"
    b_sin_tope, tope = b, False
    if P["tope_rango"] is not None and b != 0:
        b = _tope_rango(b, nivel, np.exp(z) if escala_log else z, escala_log, phi, P["tope_rango"], P["meses_tope"])
        tope = b != b_sin_tope
    hh = np.arange(1, h + 1)
    pron = nivel + b * np.cumsum(phi ** hh) + estacional_fut
    w = d if MESES_TENDENCIA is None or len(d) <= MESES_TENDENCIA else d[-MESES_TENDENCIA:]
    sd = float(np.std(np.diff(w) - b, ddof=1)) if len(w) > 2 else 0.0
    ancho = _cuantil_normal() * sd * np.sqrt(hh)
    params = {"pendiente": float(b), "pendiente_aplicada": float(b), "pendiente_sin_tope": float(b_sin_tope),
              "tope": bool(tope), "ventana": int(len(d)), "r2": math.nan, "amortiguacion": float(phi),
              "phi_desviacion": 1.0, "ancla": float(nivel), "sd_residual": sd, "alpha": float(alpha),
              "beta": float(beta), "phi": float(phi), "n_saltos": int(masc.sum()),
              "salto": bool(len(masc) and masc[-1]), "regla_pendiente": regla}
    if est is not None:
        params.update({"estacional": [float(v) for v in est["factores"]], "credibilidad_estacional": est["credibilidad"],
                       "p_estacional": est["p"], "r2_estacional": est["r2"], "obs_estacional": est["obs"],
                       "amplitud_estacional": est["amplitud"]})
    return pron, pron - ancho, pron + ancho, params, float(b)


def _tendencia_combinada(z, d, h: int, estacional_fut, est, ancla_meses: int, nombre: str, escala_log: bool):
    """Proyeccion del FND y los factores del BEL por FND con la pendiente combinada (PENDIENTE_COMBINADA): arranca del
    ultimo real sin su patron del mes (o del nivel de los ultimos ancla_meses meses, llevado al ultimo mes con la recta
    de 24), suma la pendiente amortiguada (y topada al rango) y el patron del mes. Intervalo: la variabilidad mensual
    alrededor de la pendiente, que crece con la raiz del horizonte. Regresa lo mismo que ajustar_tendencia."""
    P = PENDIENTE_COMBINADA
    b, det = pendiente_combinada(d, z, nombre)
    k = max(1, min(int(ancla_meses), len(d)))
    b_ref = det.get("pendiente_24", b)
    a0 = float(d[-1]) if k == 1 else float(np.mean(d[-k:] + b_ref * np.arange(k)[::-1]))
    b_sin_tope = b
    if P["tope_rango"] is not None and b != 0:
        b = _tope_rango(b, a0, np.exp(z) if escala_log else z, escala_log)
    hh = np.arange(1, h + 1)
    pron = a0 + b * np.cumsum(P["amortiguacion"] ** hh) + estacional_fut
    w = d if MESES_TENDENCIA is None or len(d) <= MESES_TENDENCIA else d[-MESES_TENDENCIA:]
    sd = float(np.std(np.diff(w) - b, ddof=1)) if len(w) > 2 else 0.0
    ancho = _cuantil_normal() * sd * np.sqrt(hh)
    params = {"pendiente": float(b), "pendiente_aplicada": float(b), "pendiente_sin_tope": float(b_sin_tope),
              "tope": bool(b != b_sin_tope), "ventana": int(P["ventanas"][0]), "r2": math.nan,
              "amortiguacion": float(P["amortiguacion"]), "phi_desviacion": 1.0, "ancla": a0,
              "sd_residual": sd, **det}
    if est is not None:
        params.update({"estacional": [float(v) for v in est["factores"]], "credibilidad_estacional": est["credibilidad"],
                       "p_estacional": est["p"], "r2_estacional": est["r2"], "obs_estacional": est["obs"],
                       "amplitud_estacional": est["amplitud"]})
    return pron, pron - ancho, pron + ancho, params, float(b)


def ajustar_tendencia(z, h: int, meses=None, phi_desv: float = 1.0, cred_pend=1.0, media_aritmetica: bool = False,
                      ancla_meses: int = 1, nombre: str = "", escala_log: bool = False):
    """Linea de tendencia (regresion lineal sobre los ultimos MESES_TENDENCIA valores de z, en la escala del modelo)
    mas, si ESTACIONALIDAD_MENSUAL y se conocen los meses, el patron por mes del ano; continuada desde el ultimo
    dato real con amortiguacion AMORTIGUACION_TENDENCIA. La desviacion del ultimo mes respecto al modelo se
    conserva (phi_desv = 1) o se desvanece con persistencia phi_desv hacia el nivel promedio de los ultimos
    MESES_NIVEL_LOCAL meses (indices). Intervalo: con phi_desv = 1, la variabilidad mensual alrededor de la
    tendencia (sin el patron), que crece con la raiz del horizonte; con phi_desv < 1, la banda estacionaria de los
    residuos mas la incertidumbre de la pendiente. cred_pend: proporcion de la pendiente que se proyecta (1 = toda;
    "r2" = el R2 ajustado de la recta, para indices; "combinada" = la pendiente combinada del FND y los factores del
    BEL por FND, _tendencia_combinada, que usa nombre = serie y escala_log = z en logaritmos). ancla_meses: con
    phi_desv = 1, la proyeccion arranca del promedio de las desviaciones de los ultimos ancla_meses meses (1 = la del
    ultimo mes)."""
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
    if cred_pend == "combinada":                                       # FND y factores del BEL por FND
        return _tendencia_combinada(z, d, h, estacional_fut, est, ancla_meses, nombre, escala_log)
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
        k = max(1, min(int(ancla_meses), len(e)))
        objetivo = float(np.mean(e[-k:]))                              # se conserva: arranca del ultimo real (k = 1) o
        desviacion = objetivo                                          # del nivel de los ultimos k meses
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


def ajustar(z, modelo: str, h: int, meses=None, phi_desv: float = 1.0, cred_pend=1.0, media_aritmetica: bool = False,
            ancla_meses: int = 1, nombre: str = "", escala_log: bool = False):
    """Pronostico en la escala del modelo: (pronostico, li, ls, parametros, pendiente final). meses = mes del ano
    (1-12) de cada observacion, para la estacionalidad de la tendencia historica; phi_desv = persistencia de la
    desviacion del ultimo mes (1 = se conserva); cred_pend = proporcion de la pendiente que se proyecta."""
    if modelo == TENDENCIA:
        return ajustar_tendencia(z, h, meses, phi_desv, cred_pend, media_aritmetica, ancla_meses, nombre, escala_log)
    if modelo == HOLT_GUARDIA:
        return ajustar_holt_guardia(z, h, meses, escala_log)
    return ajustar_ets(z, modelo, h)


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
    (ramo estatutario, ceros, constante, escalon, sin datos) prep es None y res trae la proyeccion; si no, prep trae
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

    # 5) ramos estatutarios / series extintas / constantes / en escalon
    if serie.clave[0] == "HPARAM" and str(serie.clave[3]).strip() in HP_ESTATUTARIOS:
        return _constante(y[-1], REGLA_ESTATUTARIO)
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
    usar_log = tipo in ("nivel", "indice", "lag", "fnd", "factor_log") and np.all(y > 0)   # LAGs positivos: tendencia en %
    res.transformacion = "log" if usar_log else "ninguna"
    z = np.log(y) if usar_log else y.copy()
    meses = (np.array([p % 100 for p in per], dtype=int)              # mes del ano de cada observacion
             if tipo in TIPOS_CON_ESTACIONALIDAD else None)          # (solo esos tipos llevan patron)
    phi_desv = float(PERSISTENCIA_DESVIACION.get(tipo, 1.0))          # indices: la desviacion se desvanece
    if (serie.clave[2], str(serie.clave[3])) in ANCLAR_SERIES:
        phi_desv = 1.0
        res.alertas.append("Serie anclada al ultimo real por decision del area (ANCLAR_SERIES)")
    cred_pend = CREDIBILIDAD_PENDIENTE.get(tipo, 1.0)                  # indices: pendiente ponderada por su R2
    ancla = int(ANCLA_MESES_SERIE.get(str(serie.clave[2]), ANCLA_MESES.get(tipo, 1)))   # con phi = 1: de donde arranca
    nombre_serie = str(serie.clave[2])                                 # FND, FACTOR GTO, ... (pendiente combinada)
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
            f, lo, hi, params, pendiente = ajustar(z, modelo, hh, meses, phi_desv, cred_pend, media_arit, ancla,
                                                   nombre_serie, usar_log)
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
    if modelo == HOLT_GUARDIA and res.parametros:
        pe = res.parametros
        if pe.get("salto"):
            res.alertas.append("Holt con guardia: el ultimo mes es un salto (mas de "
                               f"{HOLT_FND['k_salto']:.0f} MAD); no se proyecta tendencia desde el nuevo nivel")
        if pe.get("tope"):
            res.alertas.append(f"Holt con guardia: la tendencia se redujo para quedar a {HOLT_FND['meses_tope']} meses "
                               f"dentro del rango de 36 meses ampliado {HOLT_FND['tope_rango']:.0%}")
    if modelo == TENDENCIA and res.parametros:
        r2 = res.parametros.get("r2", math.nan)
        if np.isfinite(r2) and r2 < 0.3:
            res.alertas.append(f"R2 de la tendencia {r2:.2f}: la recta explica poco de los ultimos "
                               f"{res.parametros['ventana']} meses; revisar antes de usar la pendiente")
        pe = res.parametros
        if pe.get("salto"):
            res.alertas.append(f"Pendiente combinada: {pe['regla_pendiente']}; revisar si el nuevo nivel se sostiene")
        if pe.get("tope"):
            res.alertas.append(f"Pendiente combinada: la tendencia se redujo para quedar a {PENDIENTE_COMBINADA['meses_tope']} "
                               f"meses dentro del rango de 36 meses ampliado {PENDIENTE_COMBINADA['tope_rango']:.0%}")
        if pe.get("phi_desviacion", 1.0) < 1 and pe.get("sd_residual", 0) > 0:
            brecha_nivel = pe["desviacion_ultimo"] - pe["nivel_local"]
            if abs(brecha_nivel) > 2 * pe["sd_residual"]:
                res.alertas.append(f"El ultimo mes esta {(math.expm1(brecha_nivel) if usar_log else brecha_nivel):+.1%} "
                                   f"respecto al nivel del ultimo ano (mas de 2 desviaciones); la proyeccion desvanece "
                                   f"esa diferencia con persistencia {pe['phi_desviacion']:.2f}")
        if n >= 13 and y[-13] > 0 and y[-1] > 0:
            cambio12 = y[-1] / y[-13] - 1
            if abs(cambio12) > 0.05 and np.sign(res.tendencia_mensual) == -np.sign(cambio12):
                etiqueta = ("La pendiente proyectada" if "regla_pendiente" in res.parametros
                            else f"La tendencia de {res.parametros['ventana']} meses")
                res.alertas.append(f"{etiqueta} ({res.tendencia_mensual:+.1%} "
                                   f"mensual) va en sentido contrario al cambio real de los ultimos 12 meses "
                                   f"({cambio12:+.0%})")

    # backtest: se re-proyecta desde cortes pasados con el mismo modelo y se compara contra lo real
    res.error_modelo, res.error_ultimo_valor, res.error_ses, res.n_cortes = backtest(z, y, modelo, inv, meses, phi_desv,
                                                                                  cred_pend, media_arit, ancla,
                                                                                  nombre_serie, usar_log)
    if (res.n_cortes and np.isfinite(res.error_modelo) and np.isfinite(res.error_ultimo_valor)
            and res.error_modelo > res.error_ultimo_valor * 1.10 + 0.5):
        res.alertas.append(f"En el backtest de esta serie el modelo ({res.error_modelo:.1f}%) no supera a repetir "
                           f"el ultimo valor ({res.error_ultimo_valor:.1f}%)")

    res.pronostico, res.li, res.ls = list(pron[brecha:]), list(li[brecha:]), list(ls[brecha:])
    return _post_proceso(res, y, tipo, serie.dominio)


def backtest(z, y, modelo: str, inv, meses=None, phi_desv: float = 1.0, cred_pend=1.0, media_arit: bool = False,
             ancla_meses: int = 1, nombre: str = "", escala_log: bool = False):
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
        for nombre_p, mod in (("modelo", modelo), ("ses", "SES")):
            try:
                preds[nombre_p] = (inv(ajustar(z[:o], mod, hz, None if meses is None else meses[:o], phi_desv,
                                               cred_pend, media_arit, ancla_meses, nombre, escala_log)[0])
                                 if mod != ULTIMO_VALOR else preds["ultimo"])
            except Exception:  # noqa: BLE001
                preds[nombre_p] = None
        if any(p is None or not np.all(np.isfinite(p)) for p in preds.values()):
            continue
        cortes += 1
        for nombre_p, p in preds.items():
            errores[nombre_p][0] += float(np.sum(np.abs(p - real)))
            errores[nombre_p][1] += float(np.sum(np.abs(real)))

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
    filas_entrada: set = field(default_factory=set)   # renglones que ya traia la BD de entrada (no los que se agregan)
    filas_prima: dict = field(default_factory=dict)   # (concepto, periodo) -> fila de los meses de prima anteriores al
                                                      # primer mes con montos (AGREGAR_MESES_PRIMA): sin montos, no son
                                                      # historia del modelo
    filas_backtest: dict = field(default_factory=dict)   # (concepto, periodo) -> fila "BACKTESTING <concepto>" (BACKTESTING):
                                                         # no son historia; se reutilizan al volver a escribir


def leer_bd_montos(ruta: Path) -> BDMontos:
    wb = openpyxl.load_workbook(ruta)
    ws = wb[HOJA_MONTOS]
    enc = {norm(ws.cell(3, c).value): c for c in range(1, ws.max_column + 1) if ws.cell(3, c).value}
    cols_ramo = {h.split("_", 1)[1]: c for h, c in enc.items() if h.startswith("RAM_")}
    filas, valores, tc, conceptos, vacias = {}, {}, {}, [], set()
    filas_bt, etiqueta_bt = {}, norm(BACKTESTING_ETIQUETA) + " "
    for r in range(4, ws.max_row + 1):
        concepto = ws.cell(r, enc["CONCEPTO"]).value
        periodo = ws.cell(r, enc["PERIODO"]).value
        if not concepto or not isinstance(periodo, (int, float)):
            continue
        concepto, periodo = norm(concepto), int(periodo)
        if concepto.startswith(etiqueta_bt) or concepto == etiqueta_bt.strip():   # (backtesting de una corrida anterior o
            base = concepto[len(etiqueta_bt):] if concepto.startswith(etiqueta_bt) else f"#{r}"   # escrito a mano: no
            filas_bt[(base, periodo)] = r                                                     # son historia)
            continue
        if concepto not in conceptos:
            conceptos.append(concepto)
        filas[(concepto, periodo)] = r
        if all(ws.cell(r, c).value is None or str(ws.cell(r, c).value).strip() == "" for c in cols_ramo.values()):
            vacias.add((concepto, periodo))
        for ramo, c in cols_ramo.items():
            v, _ = a_numero(ws.cell(r, c).value)
            valores[(concepto, periodo, ramo)] = 0.0 if math.isnan(v) else v
        t, _ = a_numero(ws.cell(r, enc["TC"]).value)
        if not math.isnan(t):
            tc[periodo] = t
    # renglones sin ningun monto antes del primer mes con montos (los meses de prima que agrega AGREGAR_MESES_PRIMA, si
    # la BD de salida se vuelve a usar como entrada): no son historia; se guardan aparte para no duplicarlos
    con_dato = [p for (c, p) in filas if (c, p) not in vacias]
    inicio = min(con_dato) if con_dato else None
    filas_prima = {k: filas.pop(k) for k in [k for k in filas if k in vacias and inicio is not None and k[1] < inicio]}
    for (c, p) in filas_prima:
        for ramo in cols_ramo:
            valores.pop((c, p, ramo), None)
    # si los renglones de backtesting son los ultimos de la hoja se borran: se vuelven a escribir al final, despues de lo
    # que se agregue (meses nuevos, meses de prima); si hay otros renglones abajo, se reutilizan en su lugar
    if filas_bt and min(filas_bt.values()) > max(list(filas.values()) + list(filas_prima.values()) + [3]):
        ini_bt = min(filas_bt.values())
        ws.delete_rows(ini_bt, ws.max_row - ini_bt + 1)
        filas_bt = {}
    return BDMontos(ruta, wb, ws, enc["CONCEPTO"], enc["PERIODO"], enc["TC"], cols_ramo, filas, valores, tc,
                    conceptos, set(filas.values()) | set(filas_prima.values()), filas_prima, filas_bt)


def tc_para_periodo(bd: BDMontos, p: int) -> float:
    """TC con que se escribe (y se convierte) cada mes: TC_PROYECCION (supuesto de Inversiones) si lo trae
    (y, para renglones existentes, solo si ACTUALIZAR_TC_EXISTENTES); si no, el de la BD o su ultimo TC."""
    if p in TC_PROYECCION and (ACTUALIZAR_TC_EXISTENTES or p not in bd.tc):
        return TC_PROYECCION[p]
    if p in bd.tc:
        return bd.tc[p]
    return bd.tc[max(bd.tc)]


def archivos_res_rvas() -> list:
    """Res_Rvas de entradas/ (PATRON_RES_RVAS), sin los temporales de Office (~$), por ano del nombre y nombre, con los de
    nombre exacto (Res_Rvas_AAAA) al final: el ultimo gana en un mes que traigan dos archivos."""
    if not ENTRADAS.exists():
        return []
    pat = re.compile(PATRON_RES_RVAS, re.I)
    exacto = re.compile(r"res[\s_\-.]*rvas[\s_\-.]*\d{4}\.(xlsx|xlsm)", re.I)
    return sorted((c for c in ENTRADAS.iterdir() if c.is_file() and not c.name.startswith("~$") and pat.search(c.name)),
                  key=lambda c: (bool(exacto.fullmatch(c.name)),
                                 int(m.group(1)) if (m := re.search(r"(20\d\d)", c.name)) else 0, c.name.lower()))


def _parecidos_res_rvas() -> list:
    """Nombres de entradas/ que parecen Res_Rvas pero no se pueden leer (otra extension, p. ej. .xlsb o .xls)."""
    if not ENTRADAS.exists():
        return []
    leidos = {c.name for c in archivos_res_rvas()}
    nombre = re.compile(r"res[\s_\-.]*rvas", re.I)
    return sorted(c.name for c in ENTRADAS.iterdir() if c.is_file() and not c.name.startswith("~$")
                  and nombre.search(c.stem) and c.name not in leidos)


def leer_tc_real(bd: BDMontos, ultimo: int, libro: str = "", alertas: list | None = None) -> dict:
    """TC real con que la fuente SAP convirtio cada mes a USD. Se usa para regresar la historia a MXN. Prioridad:
    1) Res_Rvas en entradas/ (fila 7 de BacktestingRRC, columnas SAP), si estan; 2) los meses reales de
    TC_PROYECCION (tipo_cambio.py: 202601 en adelante hasta el ultimo real = TC de SAP); 3) la columna TC de la BD.
    Si la columna TC de la BD difiere del TC real en algun mes de la historia, se avisa: la historia se regresa a
    pesos con el real, que es con el que se convirtieron los montos."""
    tc = {p: v for p, v in bd.tc.items() if p <= ultimo}
    tc.update({p: v for p, v in TC_PROYECCION.items() if p <= ultimo})
    for ruta in archivos_res_rvas():
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


def _bel_metodo_area() -> dict:
    """BEL_METODO_AREA con las llaves normalizadas: {(reserva, ramo como texto): escenarios}."""
    return {(norm(pref), str(int(r)) if str(r).strip().isdigit() else str(r).strip()): tuple(escs)
            for (pref, r), escs in (BEL_METODO_AREA or {}).items()}


def leer_bel_metodo_area(ultimo: int, alertas: list | None = None, info: dict | None = None) -> dict:
    """BEL, MR, BRUTO e IRR en USD de las series de BEL_METODO_AREA, de la hoja "Base <reserva>" de los Res_Rvas_*.xlsx
    de entradas/ (columnas Escenario, Tipo Monto, Ramo, Periodo y Monto_USD), en los meses hasta el ultimo real. En cada
    mes se toma el primer escenario de la lista que trae BEL positivo, con sus cuatro conceptos; si dos archivos traen el
    mismo mes, el ultimo en orden de nombre. Regresa {(reserva, ramo): {"valores": {(concepto, periodo): USD},
    "meses": [...], "escenarios": {periodo: escenario}, "archivos": [...], "renglones": n}}. Si se pasa info, se llena
    con {"archivos": [Res_Rvas encontrados], "motivos": {(reserva, ramo): por que no hay datos de esa serie}}."""
    config = _bel_metodo_area()
    info = info if info is not None else {}
    info.update({"archivos": [], "con_hoja": [], "ilegibles": [], "motivos": {}, "parecidos": _parecidos_res_rvas()})
    if info["parecidos"] and alertas is not None:
        alertas.append(("PND", "BEL del metodo del area", f"{', '.join(info['parecidos'])} parecen Res_Rvas pero no se "
                        "leen (deben ser .xlsx o .xlsm): guardalos como .xlsx si traen meses que faltan"))
    if not config:
        return {}
    conceptos = ("BEL", "MR", "BRUTO", "IRR")
    crudo: dict = {}                  # (reserva, ramo) -> periodo -> escenario -> {concepto: USD}
    archivos, renglones = {}, {}
    buscadas = set(config)
    for ruta in archivos_res_rvas():
        info["archivos"].append(ruta.name)
        try:
            wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            info["ilegibles"].append(f"{ruta.name} ({type(e).__name__})")
            if alertas is not None:
                alertas.append(("PND", "BEL del metodo del area", f"no se pudo leer {ruta.name}: {type(e).__name__}"))
            continue
        try:
            if _leer_base_res_rvas(wb, ruta, buscadas, config, conceptos, ultimo, crudo, archivos, renglones):
                info["con_hoja"].append(ruta.name)
        except Exception as e:  # noqa: BLE001
            if alertas is not None:
                alertas.append(("PND", "BEL del metodo del area", f"no se pudo leer {ruta.name}: {type(e).__name__}: {e}"))
        finally:
            wb.close()
    out = {}
    for (pref, ramo), por_mes in crudo.items():
        valores, escs = {}, {}
        for per in sorted(por_mes):
            for esc in config[(pref, ramo)]:
                d = por_mes[per].get(esc, {})
                if d.get("BEL", 0.0) > UMBRAL_CERO_MONTOS:
                    valores.update({(c, per): d.get(c, math.nan) for c in conceptos})
                    escs[per] = esc
                    break
        descuadre = [per for per in escs if all(np.isfinite(valores.get((c, per), math.nan)) for c in ("BEL", "MR", "BRUTO"))
                     and abs(valores[("BRUTO", per)] - valores[("BEL", per)] - valores[("MR", per)])
                     > 0.01 * abs(valores[("BRUTO", per)])]
        if descuadre and alertas is not None:
            alertas.append(("PND", f"BEL del metodo del area {pref} {ramo}",
                            f"BRUTO distinto de BEL + MR (mas de 1 %) en {len(descuadre)} mes(es) de Res_Rvas "
                            f"({descuadre[0]} a {descuadre[-1]}): revisar la conversion a USD"))
        if escs:
            out[(pref, ramo)] = {"valores": valores, "meses": sorted(escs), "escenarios": escs,
                                 "archivos": sorted(archivos[(pref, ramo)]), "renglones": renglones[(pref, ramo)]}
    for (pref, ramo), escs_cfg in config.items():         # por que una serie no trae datos
        if (pref, ramo) in out:
            continue
        legibles = [n for n in info["archivos"] if not any(x.startswith(n + " (") for x in info["ilegibles"])]
        if not info["archivos"]:
            m = ("no hay ningun archivo Res_Rvas en entradas/" + (
                f"; hay {', '.join(info['parecidos'])}, pero deben ser .xlsx o .xlsm: guardalos como .xlsx"
                if info["parecidos"] else
                f": pon ahi Res_Rvas_{ultimo // 100 - 1}.xlsx y Res_Rvas_{ultimo // 100}.xlsx"))
        elif not legibles:
            m = (f"no se pudieron abrir {', '.join(info['ilegibles'])}: revisa que no esten danados ni protegidos con "
                 "contrasena o con una etiqueta de confidencialidad")
        elif not info["con_hoja"]:
            m = (f"{', '.join(legibles)} no traen la hoja Base {pref} con las columnas Escenario, Tipo Monto, Ramo, "
                 "Periodo y Monto_USD: revisa que sean los Res_Rvas del area"
                 + (f" (tampoco se pudieron abrir {', '.join(info['ilegibles'])})" if info["ilegibles"] else ""))
        else:
            m = (f"{', '.join(info['con_hoja'])} no traen BEL positivo del ramo {ramo} en los escenarios "
                 f"{', '.join(str(e) for e in escs_cfg)} hasta {ultimo}: revisa que esten al dia")
        info["motivos"][(pref, ramo)] = m
    return out


def _leer_base_res_rvas(wb, ruta, buscadas, config, conceptos, ultimo, crudo, archivos, renglones) -> bool:
    """Renglones de las hojas "Base <reserva>" de un Res_Rvas para leer_bel_metodo_area (llena crudo, archivos y
    renglones). Hoy solo SONR: "Base RRC" trae otro encabezado ("Tipo de Monto") y el BEL con signo negativo. Regresa
    True si alguna hoja trae el encabezado."""
    req = {k: norm(k) for k in ("Escenario", "Tipo Monto", "Ramo", "Periodo", "Monto_USD")}
    con_encabezado = False
    for pref in sorted({p for p, _ in buscadas}):
        hoja = f"Base {pref}"
        if hoja not in wb.sheetnames:
            continue
        col = None
        for fila in wb[hoja].iter_rows(values_only=True):
            if col is None:                           # renglon de encabezados
                nombres = [norm(x) if isinstance(x, str) else None for x in fila]
                if all(v in nombres for v in req.values()):
                    col = {k: nombres.index(v) for k, v in req.items()}
                    con_encabezado = True
                continue
            try:
                esc, conc = int(fila[col["Escenario"]]), norm(str(fila[col["Tipo Monto"]]))
                ramo, per = str(int(fila[col["Ramo"]])), int(fila[col["Periodo"]])
                usd = float(fila[col["Monto_USD"]])
            except (TypeError, ValueError, IndexError):
                continue
            if (pref, ramo) not in buscadas or per > ultimo or conc not in conceptos or not np.isfinite(usd):
                continue
            if esc not in config.get((pref, ramo), ()):
                continue
            crudo.setdefault((pref, ramo), {}).setdefault(per, {}).setdefault(esc, {})[conc] = usd
            archivos.setdefault((pref, ramo), set()).add(ruta.name)
            renglones[(pref, ramo)] = renglones.get((pref, ramo), 0) + 1
    return con_encabezado


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


# =============================================================================
# ESCENARIOS PND / PD (Danos RRC y SONR): reserva = base implicita x indice de siniestralidad
# =============================================================================
def ruta_escenario_pnd(esc: str) -> Path:
    """Archivo de la BD de Danos con el escenario esc (junto a la BD principal)."""
    return SALIDA_BD_DANOS.with_name(f"{SALIDA_BD_DANOS.stem}_{esc}{SALIDA_BD_DANOS.suffix}")


def _indice_mensual(hp, ramo, nombre: str, hasta: int | None = None) -> dict:
    """{periodo: indice} de HParametros para el ramo de reserva (via MAPA_RAMO_LAG), con la historia hasta `hasta`.
    Como en la preparacion de las series: un hueco que separa dos niveles cuya razon pasa SALTO_NIVEL_HUECO corta la
    historia (se usa solo lo posterior); los demas huecos de hasta MAX_HUECO_INTERPOLABLE meses se interpolan en linea
    recta y los mas largos se dejan vacios."""
    r_hp = MAPA_RAMO_LAG.get(str(ramo))
    h = hp.historia.get((r_hp, nombre), {}) if (hp is not None and r_hp) else {}
    fechas = sorted(p for p, v in h.items() if v is not None and not math.isnan(v) and (hasta is None or p <= hasta))
    if not fechas:
        return {}
    per = rango_periodos(fechas[0], fechas[-1])
    x = np.array([h.get(p, math.nan) for p in per], dtype=float)
    ok = np.isfinite(x)
    i = 0
    while i < len(x):
        if ok[i]:
            i += 1
            continue
        j = i
        while j < len(x) and not ok[j]:
            j += 1
        if 0 < i and j < len(x):
            a_, b_ = x[i - 1], x[j]
            salto = (a_ > 0 and b_ > 0 and max(a_, b_) / min(a_, b_) > SALTO_NIVEL_HUECO)
            if salto:
                x[:j] = np.nan               # cambio de nivel: la historia empieza despues del hueco
            elif j - i <= MAX_HUECO_INTERPOLABLE:
                x[i:j] = np.interp(np.arange(i, j), [i - 1, j], [a_, b_])
        i = j
    return {int(p): float(v) for p, v in zip(per, x) if np.isfinite(v)}


def _pe(pr, grupo: str, meses: int) -> pd.Series:
    """Prima tomada del grupo de los ultimos `meses` meses, anualizada (x 12 / meses)."""
    p = pr.mensual[grupo].astype(float)
    return p.rolling(meses, min_periods=meses).sum() * (12.0 / meses)


def _razon_ses(clave: tuple, per: list, valores, pc: int, h: int):
    """Proyeccion de una razon con el mismo tratamiento que las demas razones del modelo (SES y sus reglas)."""
    res = pronosticar(Serie(clave, "razon", list(per), [float(v) for v in valores], pc, h, dominio=DOMINIO_RAZON_BEL))
    f = np.asarray(res.pronostico, dtype=float)
    return np.nan_to_num(f, nan=0.0) if len(f) == h else None


def _indice_al_corte(hp, ramo, nombre: str, pc: int, h: int):
    """Indice (o LAG) de HParametros proyectado desde el corte pc con el mismo metodo de la hoja (para el backtest)."""
    r_hp = MAPA_RAMO_LAG.get(str(ramo))
    hist = hp.historia.get((r_hp, nombre), {}) if r_hp else {}
    fechas = [f for f, v in hist.items() if f <= pc and not math.isnan(v)]
    if not fechas:
        return None
    periodos = rango_periodos(min(fechas), pc)
    tipo = "lag" if nombre in LAGS else "indice"
    res = pronosticar(Serie(("HPARAM", HOJA_PARAMETROS, nombre, r_hp), tipo, periodos,
                            [hist.get(p, math.nan) for p in periodos], pc, h,
                            dominio=DOMINIO_LAG if tipo == "lag" else (None, None)))
    f = np.asarray(res.pronostico, dtype=float)
    return f if len(f) == h and np.all(np.isfinite(f)) and (tipo == "lag" or np.all(f > 0)) else None


def _lag_pnd(pref: str) -> str:
    """LAG que se reporta junto al indice de la reserva (el de LAG_BASE_PND, o el LAG 1 si la base no lo usa)."""
    return LAG_BASE_PND.get(pref) or LAGS[0]


def _divisor_base(hp, ramo, pref: str, per: list, hasta: int | None = None):
    """Indice, LAG y divisor de la base por mes de per: BEL = base x divisor, con divisor = IS (RRC) o
    IS x (1 - LAG 1) (SONR, ver LAG_BASE_PND). Los tres como arreglos; el divisor, solo donde es positivo."""
    ind = _indice_mensual(hp, ramo, INDICE_BASE_PND[pref][0], hasta)
    lag = _indice_mensual(hp, ramo, _lag_pnd(pref), hasta)
    iv = np.array([ind.get(p, math.nan) for p in per], dtype=float)
    lv = np.array([lag.get(p, math.nan) for p in per], dtype=float)
    dv = iv * (1.0 - lv) if pref in LAG_BASE_PND else iv.copy()
    return iv, lv, np.where(np.isfinite(dv) & (dv > 0), dv, np.nan)


def _divisor_proyectado(resultados: dict, ramo, pref: str, h: int):
    """(indice, LAG, divisor) proyectados de HParametros para el ramo (los que se escriben en sus renglones de
    Proyeccion); None en lo que no se pudo proyectar."""
    r_hp = MAPA_RAMO_LAG.get(str(ramo))

    def pron(nombre):
        r = resultados.get(("HPARAM", HOJA_PARAMETROS, nombre, r_hp))
        f = np.asarray(r.pronostico, dtype=float) if r is not None else None
        return f if f is not None and len(f) == h else None
    is_f, lag_f = pron(INDICE_BASE_PND[pref][0]), pron(_lag_pnd(pref))
    if is_f is None:
        return None, lag_f, None
    if pref in LAG_BASE_PND:
        return is_f, lag_f, (is_f * (1.0 - lag_f) if lag_f is not None else None)
    return is_f, lag_f, is_f.copy()


def leer_pe_fcst(ruta: Path | None = None) -> dict | None:
    """Prima tomada del FCST por ramo de la BD y mes (USD), como la arma la hoja ER_ram del archivo de FCST: por mes,
    -suma de AMOUNT de CtaMens con GL_ACCT = CUENTA_PE_FCST y el ramo (Ramo2 via RAMO_FCST_A_BD). Regresa
    {"ruta", "mensual": {(ramo, periodo): prima del mes}, "acumulada": {(ramo, periodo): acumulado del ano},
    "nombres": {ramo: "Incendio"...}, "periodos", "renglones", "usados", "fuera": {ramo del FCST: prima},
    "fuera_mensual": {(Ramo2, periodo): prima del mes} de los ramos fuera de la BD (Fianzas: RFV por prima),
    "fuera_cedida_mensual" (la columna CEDIDA de esa prima) y "fuera_com_mensual" (cuenta CUENTA_COM_FCST) de esos
    ramos, "fuera_seg": {(Ramo2, "PR" o "MA", "prima" o "com"): monto del ano} (segmento de prima de reserva: ZTIPOREAS 1
    fuera de Mexico o ZTIPOREAS 2; el resto, monto afianzado), "control": texto de la verificacion contra lo que muestra
    ER_ram, "avisos": [...]}; None si no hay archivo."""
    ruta = Path(ruta or ARCHIVO_PE_FCST)
    if not ruta.exists():
        return None
    try:                                               # lee .xlsb (solo si hay archivo de FCST)
        _asegurar_paquetes({"python_calamine": "python-calamine"})
    except SystemExit as e:                            # sin pip: la corrida sigue y PE FCST queda como captura
        raise ImportError(str(e)) from None
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(str(ruta))
    if "CtaMens" not in wb.sheet_names:
        raise ValueError(f"{ruta.name} no trae la hoja CtaMens")
    filas = wb.get_sheet_by_name("CtaMens").to_python()
    i_enc = next((i for i, f in enumerate(filas[:20]) if "CALMONTH" in f and "AMOUNT" in f), None)
    if i_enc is None:
        raise ValueError(f"{ruta.name} › CtaMens: no se encontro el encabezado (CALMONTH, GL_ACCT, AMOUNT, RamoN, Ramo2)")
    enc = filas[i_enc]
    j = {n: enc.index(n) for n in ("CALMONTH", "GL_ACCT", "AMOUNT", "RamoN", "Ramo2")}
    j_ced = enc.index("CEDIDA") if "CEDIDA" in enc else None
    j_tr, j_terr = (enc.index(n) if n in enc else None for n in ("ZTIPOREAS", "Territorio"))
    ced_fuera, com_fuera, seg_fuera = {}, {}, {}   # (Ramo2 fuera de la BD, ...) -> cedida, comisiones, por segmento

    def segmento(f_):                      # segmento de prima de reserva de la metodologia de Fianzas (o None)
        if j_tr is None or j_terr is None or len(f_) <= max(j_tr, j_terr):
            return None
        tr_ = a_numero(f_[j_tr])[0]
        mex = norm(f_[j_terr]).replace("É", "E") in ("MEXICO", "1")
        return "PR" if (tr_ == 1 and not mex) or tr_ == 2 else "MA"

    def codigo(v):
        return str(int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) \
            else str(v or "").strip()
    mensual, por_nombre, nombres, fuera, fuera_mes = {}, {}, {}, {}, {}
    renglones = usados = 0
    for f in filas[i_enc + 1:]:
        mes = f[j["CALMONTH"]] if len(f) > j["CALMONTH"] else None
        if not isinstance(mes, (int, float)) or isinstance(mes, bool) or not 190001 <= mes <= 299912:
            continue                                   # (renglon de totales o encabezado repetido)
        renglones += 1
        cta = codigo(f[j["GL_ACCT"]])
        if cta == CUENTA_COM_FCST and RAMO_FCST_A_BD.get(codigo(f[j["Ramo2"]])) is None:
            c_, _ = a_numero(f[j["AMOUNT"]])
            if np.isfinite(c_):
                k_ = (codigo(f[j["Ramo2"]]), int(mes))
                com_fuera[k_] = com_fuera.get(k_, 0.0) + c_
                if (sg_ := segmento(f)):
                    seg_fuera[(k_[0], sg_, "com")] = seg_fuera.get((k_[0], sg_, "com"), 0.0) + c_
            continue
        if cta != CUENTA_PE_FCST:
            continue
        monto, _ = a_numero(f[j["AMOUNT"]])
        if not np.isfinite(monto):
            continue
        p, nombre, r2 = int(mes), str(f[j["RamoN"]] or "").strip(), codigo(f[j["Ramo2"]])
        por_nombre[(nombre, p)] = por_nombre.get((nombre, p), 0.0) - monto
        ramo = RAMO_FCST_A_BD.get(r2)
        if ramo is None:
            fuera[f"{r2} {nombre}"] = fuera.get(f"{r2} {nombre}", 0.0) - monto
            fuera_mes[(r2, p)] = fuera_mes.get((r2, p), 0.0) - monto
            if j_ced is not None and len(f) > j_ced:
                c_, _ = a_numero(f[j_ced])
                if np.isfinite(c_):
                    ced_fuera[(r2, p)] = ced_fuera.get((r2, p), 0.0) - c_
            if (sg_ := segmento(f)):
                seg_fuera[(r2, sg_, "prima")] = seg_fuera.get((r2, sg_, "prima"), 0.0) - monto
            continue
        usados += 1
        mensual[(ramo, p)] = mensual.get((ramo, p), 0.0) - monto
        nombres.setdefault(ramo, set()).add(nombre)
    periodos = sorted({p for _, p in mensual})
    for ramo in set(RAMO_FCST_A_BD.values()):          # un ramo o mes sin renglones es prima 0, como en ER_ram
        for p in periodos:
            mensual.setdefault((ramo, p), 0.0)
    if not periodos:
        raise ValueError(f"{ruta.name} › CtaMens: {renglones:,} renglones, ninguno con la cuenta {CUENTA_PE_FCST} de "
                         "ramos de la BD" + (f" (fuera de la BD: {', '.join(sorted(fuera))})" if fuera else ""))
    acumulada = {}
    for ramo in {r for r, _ in mensual}:
        acum, anio = 0.0, None
        for p in periodos:                             # acumulado del ano, como las columnas de ER_ram (+ mes anterior)
            if p // 100 != anio:
                acum, anio = 0.0, p // 100
            acum += mensual.get((ramo, p), 0.0)
            acumulada[(ramo, p)] = acum
    avisos = []
    if any(p // 100 != periodos[0] // 100 for p in periodos) or len(periodos) != 12:
        avisos.append(f"CtaMens trae {len(periodos)} meses ({periodos[0]} a {periodos[-1]}), no un ano completo")
    # verificacion contra lo que muestra ER_ram (solo tiene el ramo seleccionado en su celda de ramo)
    control = "no se pudo comparar con ER_ram"
    if "ER_ram" in wb.sheet_names:
        er = wb.get_sheet_by_name("ER_ram").to_python()
        i_mes = next((i for i, f in enumerate(er[:30]) if sum(1 for v in f if isinstance(v, (int, float))
                                                              and int(v) in periodos) >= 6), None)
        i_pt = next((i for i, f in enumerate(er[:40]) if any(norm(v) == norm("Prima Tomada") for v in f)), None)
        sel = next((str(f[0]).strip() for f in er[:15] if f and str(f[0]).strip() in {n for n, _ in por_nombre}), None)
        if i_mes is not None and i_pt is not None and sel:
            fac = [er[i_mes - 1][k] for k, v in enumerate(er[i_mes]) if isinstance(v, (int, float)) and int(v) in periodos]
            if any(not isinstance(x, (int, float)) or abs(x - 1) > 1e-12 for x in fac):
                avisos.append("ER_ram no esta en USD (su factor de moneda no es 1); PE FCST se toma en USD de CtaMens")
            dif, n = 0.0, 0
            acum = 0.0
            for k, v in enumerate(er[i_mes]):
                if isinstance(v, (int, float)) and int(v) in periodos:
                    p = int(v)
                    acum = (0.0 if p % 100 == 1 else acum) + por_nombre.get((sel, p), 0.0)
                    x = er[i_pt][k] if k < len(er[i_pt]) else None
                    if isinstance(x, (int, float)):
                        dif, n = max(dif, abs(x - acum)), n + 1
            control = (f"igual a ER_ram en {n} meses del ramo que tiene seleccionado ({sel}); diferencia maxima "
                       f"{dif:,.2f} USD" if n else control)
            if n and dif > 1.0:
                avisos.append(f"PE FCST no cuadra con ER_ram en {sel} (diferencia maxima {dif:,.0f} USD)")
    return {"ruta": ruta, "mensual": mensual, "acumulada": acumulada,
            "nombres": {r: ", ".join(sorted(v)) for r, v in nombres.items()}, "periodos": periodos,
            "renglones": renglones, "usados": usados, "fuera": fuera, "fuera_mensual": fuera_mes,
            "fuera_cedida_mensual": ced_fuera, "fuera_com_mensual": com_fuera, "fuera_seg": seg_fuera, "control": control,
            "avisos": avisos}


def escribir_primas_pe(wb, pr, grupos: list) -> dict | None:
    """Hoja HOJA_PRIMAS_PE con la prima tomada mensual (USD) de los grupos de ramo de Danos (real, reforecast y
    presupuesto, como la arma primas.py) y, como formulas, su PE de cada escenario: suma de los ultimos N meses
    anualizada (x 12 / N). Regresa {"fila": {periodo: renglon}, "col": {(meses, grupo): letra}} o None sin prima."""
    if pr is None or not grupos:
        return None
    if HOJA_PRIMAS_PE in wb.sheetnames:
        del wb[HOJA_PRIMAS_PE]
    ws = wb.create_sheet(HOJA_PRIMAS_PE)
    negrita = Font(bold=True)
    ws.cell(1, 1, "Prima tomada mensual por grupo de ramo (USD) y su exposicion PE (suma de los ultimos N meses x 12 / N), "
                  "como la usan el FA y los escenarios PND / PD").font = negrita
    cab = ["PERIODO", "FUENTE"] + [f"PRIMA {g}" for g in grupos] + [f"PE{m} {g}" for m in ESCENARIOS_PND.values()
                                                                    for g in grupos]
    for j, h in enumerate(cab, start=1):
        ws.cell(3, j, h).font = negrita
    per = [int(x) for x in pr.mensual.index]
    col_p = {g: 3 + i for i, g in enumerate(grupos)}
    col = {}
    k = 3 + len(grupos)
    for m in ESCENARIOS_PND.values():
        for g in grupos:
            col[(m, g)] = get_column_letter(k)
            k += 1
    filas = {}
    for i, p in enumerate(per):
        r = 4 + i
        filas[p] = r
        ws.cell(r, 1, p)
        ws.cell(r, 2, ", ".join(sorted({str(pr.fuente.at[p, g]) for g in grupos if g in pr.fuente.columns})))
        for g in grupos:
            c = ws.cell(r, col_p[g], float(pr.mensual.at[p, g]) if g in pr.mensual.columns else None)
            c.number_format = "#,##0"
        for m in ESCENARIOS_PND.values():
            for g in grupos:
                if i + 1 >= m:
                    letra = get_column_letter(col_p[g])
                    c = ws[f"{col[(m, g)]}{r}"]
                    c.value = f"=SUM({letra}{r - m + 1}:{letra}{r})" + (f"*12/{m}" if m != 12 else "")
                    c.number_format = "#,##0"
    ws.freeze_panes = "C4"
    for j in range(1, len(cab) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 14 if j > 2 else 12
    _agrupar(ws, [list(col_p.values())] + [[column_index_from_string(col[(m, g)]) for g in grupos]
                                           for m in ESCENARIOS_PND.values()])
    return {"fila": filas, "col": col}


def leer_pe_ramo(tc: dict, ruta: Path | None = None) -> dict | None:
    """PE historica (prima tomada, PmaTom) por ramo de la BD y mes de la base PExRamo, en USD: MONEDA_PE_RAMO dividida
    entre el TC del mes (tc; antes del primer mes con TC, el primer TC; en un mes posterior sin TC, el del ultimo mes
    anterior). Los ramos de SUBRAMO_A_BD se abren por subramo; los subramos sin ramo de la BD (None) se reparten entre
    los demas del ramo en proporcion a su prima del mes (sin pesos negativos). Un mes sin renglones de un ramo, desde
    su primer mes en la base, es prima 0 (la base omite las combinaciones sin movimiento). Regresa {"ruta", "mensual":
    {(ramo, periodo): USD}, "periodos", "renglones", "fuera": {ramo: USD}, "fuera_mensual": {(ramo, periodo): monto en
    MONEDA_PE_RAMO} de los ramos fuera de la BD de Danos (Fianzas: RFV por prima), "fuera_cedida_mensual": lo mismo con
    la prima cedida (PmaCed, si la base la trae), "sin_mapa": {ramo/subramo: USD}, "repartidos": USD, "avisos"} o None si
    no hay archivo."""
    candidatos = [Path(ruta)] if ruta else sorted((c for c in ENTRADAS.glob(PATRON_PE_RAMO) if not c.name.startswith("~$")),
                                                  key=lambda c: c.stat().st_size, reverse=True)
    if not candidatos or not candidatos[0].exists():
        return None
    ruta = candidatos[0]
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    filas = wb.worksheets[0].iter_rows(values_only=True)
    cab = next(filas, None)
    if cab is None:
        raise ValueError(f"{ruta.name}: la primera hoja no tiene renglones")
    enc = [norm(x) for x in cab]
    faltan = [n for n in ("RAMO", "SRAMO", "PMATOM") if n not in enc]
    j_per = next((k for k, n in enumerate(enc) if n in ("PERIODO", "EXPR1000", "FECHA", "MES", "PERIODO OCURRENCIA")
                  or n.startswith("PERIODO")), None)
    if faltan or j_per is None:
        raise ValueError(f"{ruta.name}: faltan las columnas {faltan + ([] if j_per is not None else ['PERIODO'])} "
                         f"(trae {enc})")
    j_r, j_s, j_p = enc.index("RAMO"), enc.index("SRAMO"), enc.index("PMATOM")
    j_c = enc.index("PMACED") if "PMACED" in enc else None
    cedida_fuera = {}                      # (ramo fuera de la BD, periodo) -> PmaCed en la moneda del archivo (Fianzas)
    if MONEDA_PE_RAMO == "MXN" and not tc:
        raise ValueError("sin TC para pasar PExRamo de pesos a USD")
    bruto, renglones, omitidos = {}, 0, []      # (ramo PExRamo, subramo, periodo) -> monto en la moneda del archivo
    for i, f in enumerate(filas, start=2):
        if f is None or len(f) <= max(j_r, j_s, j_p, j_per):
            continue
        v_per = f[j_per]
        per = float(v_per.year * 100 + v_per.month) if isinstance(v_per, datetime) else a_numero(v_per)[0]
        monto, r_num, s_num = a_numero(f[j_p])[0], a_numero(f[j_r])[0], a_numero(f[j_s])[0]
        if not (np.isfinite(per) and 190001 <= per <= 299912):
            continue
        if not (np.isfinite(monto) and np.isfinite(r_num) and np.isfinite(s_num)):
            omitidos.append(i)
            continue
        renglones += 1
        clave = (str(int(r_num)), str(int(s_num)), int(per))
        bruto[clave] = bruto.get(clave, 0.0) + monto
        if j_c is not None and len(f) > j_c and clave[0] not in MAPA_RAMO_LAG and clave[0] not in SUBRAMO_A_BD:
            ced = a_numero(f[j_c])[0]
            if np.isfinite(ced):
                cedida_fuera[(clave[0], clave[2])] = cedida_fuera.get((clave[0], clave[2]), 0.0) + ced
    if not renglones:
        raise ValueError(f"{ruta.name}: ningun renglon con periodo AAAAMM, Ramo, Sramo y PmaTom validos")
    ramos_bd = set(MAPA_RAMO_LAG)
    tc_ini = min(tc) if tc else None
    mensual, fuera, sin_mapa, repartidos, antes_tc, hueco_tc, negativos = {}, {}, {}, 0.0, set(), set(), set()
    fuera_mes = {}                         # (ramo fuera de la BD, periodo) -> monto en la moneda del archivo (Fianzas)

    def usd(p, v):
        if MONEDA_PE_RAMO != "MXN":
            return v
        if p in tc:
            return v / tc[p]
        if p < tc_ini:
            antes_tc.add(p)
            return v / tc[tc_ini]
        hueco_tc.add(p)
        return v / tc[max(q for q in tc if q < p)]
    for (r, s_, p), v in bruto.items():
        mapa = SUBRAMO_A_BD.get(r)
        if mapa is None:
            if r in ramos_bd:
                mensual[(r, p)] = mensual.get((r, p), 0.0) + usd(p, v)
            else:
                fuera[r] = fuera.get(r, 0.0) + usd(p, v)
                fuera_mes[(r, p)] = fuera_mes.get((r, p), 0.0) + v
            continue
        destino = mapa.get(s_, "sin mapa")
        if destino == "sin mapa":
            sin_mapa[f"{r}/{s_}"] = sin_mapa.get(f"{r}/{s_}", 0.0) + usd(p, v)
            continue
        if destino is not None:
            mensual[(destino, p)] = mensual.get((destino, p), 0.0) + usd(p, v)
            continue
        # subramo sin ramo de la BD: se reparte entre los destinos del ramo en proporcion a su prima del mes
        dest = sorted({d for d in mapa.values() if d})
        crudos = {d: sum(x for (r2, s2, p2), x in bruto.items() if r2 == r and p2 == p and mapa.get(s2) == d)
                  for d in dest}
        if any(x < 0 for x in crudos.values()):
            negativos.add(p)
        pesos = {d: max(x, 0.0) for d, x in crudos.items()}
        tot = sum(pesos.values())
        for d in dest:
            mensual[(d, p)] = mensual.get((d, p), 0.0) + usd(p, v) * (pesos[d] / tot if tot > 0 else 1.0 / len(dest))
        repartidos += usd(p, v)
    # un mes sin renglones de un ramo, desde su primer mes en la base, es prima 0
    ult = max(p for _, p in mensual)
    ceros = {}
    for r in sorted({r for r, _ in mensual}, key=int):
        for p in rango_periodos(min(p for (r2, p) in mensual if r2 == r), ult):
            if (r, p) not in mensual:
                mensual[(r, p)] = 0.0
                ceros.setdefault(r, []).append(p)
    avisos = []
    if antes_tc:
        avisos.append(f"{len(antes_tc)} meses de {min(antes_tc)} a {max(antes_tc)} sin TC en la BD: se usa el TC de "
                      f"{tc_ini} ({tc[tc_ini]:.4f})")
    if hueco_tc:
        avisos.append(f"{len(hueco_tc)} meses sin TC despues de {tc_ini} ({', '.join(map(str, sorted(hueco_tc)))}): se "
                      "usa el TC del ultimo mes anterior con TC")
    if ceros:
        avisos.append("meses sin renglones en PExRamo tomados como prima 0: " + "; ".join(
            f"ramo {r}: {len(ps)} ({ps[0]} a {ps[-1]})" for r, ps in ceros.items()))
    if negativos:
        avisos.append(f"subramos 70, 72 y 74 repartidos solo al destino con prima positiva en {len(negativos)} mes(es) "
                      f"con prima negativa de TEV o Hidro ({', '.join(map(str, sorted(negativos)))})")
    if sin_mapa:
        avisos.append("subramos de PExRamo sin mapa en SUBRAMO_A_BD (no entran a la PE del ramo): " + ", ".join(
            f"{k} ({v / 1e6:,.1f} M USD)" for k, v in sorted(sin_mapa.items())))
    if omitidos:
        avisos.append(f"{len(omitidos)} renglones con Ramo, Sramo o PmaTom no numerico omitidos (primero: renglon "
                      f"{omitidos[0]})")
    return {"ruta": ruta, "mensual": mensual, "renglones": renglones, "fuera": fuera, "fuera_mensual": fuera_mes,
            "fuera_cedida_mensual": cedida_fuera, "sin_mapa": sin_mapa, "repartidos": repartidos, "avisos": avisos,
            "periodos": sorted({p for _, p in mensual})}


def leer_pe_rfcst_fa(tc: dict, ruta: Path | None = None) -> dict | None:
    """Reforecast del ano por mes y ramo (archivo PATRON_PE_RFCST_FA, hoja con MesProc, RAMO y Primas Tomadas USD /
    MXN; si la hoja repite el encabezado en otros bloques a la derecha, se toma el primero): prima tomada de cada
    MesProc y RAMO, todas las Tipo Rea y Susc. Con MONEDA_PE_RFCST_FA = "MXN", Primas Tomadas MXN entre el TC del mes
    del proyecto (tc; si no lo trae, TC_PROYECCION); con "USD", Primas Tomadas USD. RAMO_RFCST_FA_A_BD lleva el RAMO al
    ramo de la BD; un ramo de la BD sin renglones en un mes del archivo es prima 0. Regresa {"ruta", "hoja", "mensual": {(ramo, periodo): USD},
    "usd_archivo": {(ramo, periodo): USD del archivo}, "tc_archivo": {periodo: TC del archivo}, "tc_usado": {periodo:
    TC}, "periodos", "renglones", "por_tipo": {Tipo Rea: renglones}, "fuera": {(ramo, periodo): USD}, "otros_mxn":
    {"cedida" / "comisiones": {(RAMO, periodo): Primas Cedidas / Comisiones Tomadas MXN del archivo}} (si las trae; la RFV
    de Fianzas los usa como referencia), "control", "avisos"} o None si no hay archivo."""
    candidatos = [Path(ruta)] if ruta else _archivos_entrada(PATRON_PE_RFCST_FA)
    if not candidatos or not candidatos[0].exists():
        return None
    ruta = candidatos[0]
    nombres = {k: norm(v) for k, v in (("mes", "MesProc"), ("ramo", "RAMO"), ("tipo", "Tipo Rea"), ("tc", "TC"),
                                       ("usd", "Primas Tomadas USD"), ("mxn", "Primas Tomadas MXN"))}
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        hoja = filas = j = None
        for ws in wb.worksheets:
            filas = list(ws.iter_rows(values_only=True))
            for i, f in enumerate(filas[:40]):
                enc = [norm(x) for x in f]
                if all(n in enc for n in nombres.values()):
                    j = {k: enc.index(n) for k, n in nombres.items()}      # (el primer bloque de la hoja)
                    for k_, n_ in (("cedida", "PRIMAS CEDIDAS MXN"), ("comisiones", "COMISIONES TOMADAS MXN")):
                        if n_ in enc:
                            j[k_] = enc.index(n_)
                    hoja, i_enc = ws.title, i
                    break
            if hoja:
                break
    finally:
        wb.close()
    if hoja is None:
        raise ValueError(f"{ruta.name}: ninguna hoja trae el encabezado {', '.join(sorted(set(nombres.values())))}")
    usd_archivo, mxn, tc_archivo, por_tipo, desvio_tc = {}, {}, {}, {}, 0.0
    otros = {k: {} for k in ("cedida", "comisiones") if k in j}
    renglones, omitidos = 0, []
    for i, f in enumerate(filas[i_enc + 1:], start=i_enc + 2):
        if not f:
            continue
        f = tuple(f) + (None,) * (max(j.values()) + 1 - len(f))
        mes = a_numero(f[j["mes"]])[0]
        if not (np.isfinite(mes) and 190001 <= mes <= 299912):
            continue                                   # (totales, bloques de otras columnas o renglones vacios)
        u, m, r_num, t = (a_numero(f[j[k]])[0] for k in ("usd", "mxn", "ramo", "tc"))
        if not (np.isfinite(u) and np.isfinite(m) and np.isfinite(r_num)):
            omitidos.append(i)
            continue
        renglones += 1
        p, r = int(mes), str(int(r_num))
        por_tipo[f[j["tipo"]]] = por_tipo.get(f[j["tipo"]], 0) + 1
        usd_archivo[(r, p)] = usd_archivo.get((r, p), 0.0) + u
        mxn[(r, p)] = mxn.get((r, p), 0.0) + m
        for k_, d_ in otros.items():
            x_ = a_numero(f[j[k_]])[0]
            if np.isfinite(x_):
                d_[(r, p)] = d_.get((r, p), 0.0) + x_
        if np.isfinite(t) and t > 0:
            tc_archivo.setdefault(p, t)
            desvio_tc = max(desvio_tc, abs(u * t - m))
    if not renglones:
        raise ValueError(f"{ruta.name} › {hoja}: ningun renglon con MesProc AAAAMM, RAMO y Primas Tomadas numericos")
    periodos = sorted({p for _, p in usd_archivo})
    tc_usado, avisos = {}, []
    for p in periodos:
        tc_usado[p] = tc.get(p) or TC_PROYECCION.get(p)
    if MONEDA_PE_RFCST_FA == "MXN":
        sin_tc = [p for p in periodos if not tc_usado[p]]
        if sin_tc:
            avisos.append(f"{', '.join(map(str, sin_tc))} sin TC del proyecto: se toma Primas Tomadas USD del archivo")
        fuente = {k: (v / tc_usado[k[1]] if tc_usado[k[1]] else usd_archivo[k]) for k, v in mxn.items()}
    else:
        fuente = dict(usd_archivo)
    mensual, fuera = {}, {}
    for (r, p), v in fuente.items():
        destino = RAMO_RFCST_FA_A_BD.get(r)
        if destino is None:
            fuera[(r, p)] = fuera.get((r, p), 0.0) + v
            continue
        mensual[(destino, p)] = mensual.get((destino, p), 0.0) + v
    for destino in set(RAMO_RFCST_FA_A_BD.values()):   # un ramo de la BD sin renglones en el mes es prima 0
        for p in periodos:
            mensual.setdefault((destino, p), 0.0)
    total = sum(usd_archivo.values())
    arriba = [x for f in filas[:i_enc] if f and len(f) > j["usd"]
              for x in [a_numero(f[j["usd"]])[0]] if np.isfinite(x) and x]
    control = (f"Primas Tomadas USD suman {total / 1e6:,.1f} M"
               + ("; igual al total del encabezado del archivo" if any(abs(x - total) <= 1.0 for x in arriba) else
                  (f"; el total del encabezado del archivo dice {arriba[0] / 1e6:,.1f} M (filtro aplicado?)"
                   if arriba else "")))
    if desvio_tc > 1.0:
        avisos.append(f"en algun renglon MXN no es USD x TC del archivo (diferencia maxima {desvio_tc:,.0f} MXN)")
    if omitidos:
        avisos.append(f"{len(omitidos)} renglones con RAMO o Primas Tomadas no numericos omitidos (primero: renglon "
                      f"{omitidos[0]})")
    return {"ruta": ruta, "hoja": hoja, "mensual": mensual, "usd_archivo": usd_archivo, "tc_archivo": tc_archivo,
            "tc_usado": tc_usado, "periodos": periodos, "renglones": renglones, "por_tipo": por_tipo, "fuera": fuera,
            "otros_mxn": otros, "control": control, "avisos": avisos}


def _archivos_entrada(patron: str) -> list:
    """Archivos de entradas/ cuyo nombre cumple el patron sin distinguir mayusculas ni el separador antes de las
    letras (como en Windows: "PPTO_2026_2027 FA" y "PPTO_2026_2027_FA" cumplen "PPTO*FA*.xlsx"), sin los temporales
    de Office (~$), del mas grande al mas chico."""
    if not ENTRADAS.exists():
        return []
    pat = patron.lower()
    return sorted((c for c in ENTRADAS.iterdir() if c.is_file() and not c.name.startswith("~$")
                   and fnmatch.fnmatch(c.name.lower(), pat)), key=lambda c: c.stat().st_size, reverse=True)


def _num_is(v) -> tuple:
    """(valor, venia como texto) de un indice: numero, o texto con coma decimal ('0,894') o con % ('89.4%')."""
    if isinstance(v, str):
        t = v.strip().replace("\xa0", "").replace(" ", "")
        pct = t.endswith("%")
        t = t.rstrip("%")
        if t.count(",") == 1 and "." not in t:
            t = t.replace(",", ".")
        x = a_numero(t)[0] if t else math.nan
        return (x / 100 if pct else x), True
    return a_numero(v)[0], False


def leer_is_fa(ruta: Path | None = None) -> dict | None:
    """Indices de siniestralidad de la funcion actuarial (archivo PATRON_IS_FA): la primera hoja con Ramo, MesProc,
    IS RRC e IS SONR en su encabezado. Regresa {"ruta", "hoja", "cab": encabezado del archivo, "tabla": [renglones
    validos tal cual, con los indices que venian como texto ya como numero], "val": {(reserva, ramo, periodo): IS}
    (reserva segun COLUMNA_IS_FA; el primero con dato si se repite), "tipo": {(reserva, ramo, periodo): Tipo del renglon
    que se usa}, "periodos", "ramos", "renglones", "omitidos", "por_tipo": {Tipo: [meses]}, "otros": [archivos que
    tambien cumplen el nombre], "avisos"} o None si no hay archivo. Con varios archivos que cumplen el nombre (sin
    distinguir mayusculas ni "_FA" de " FA"), usa el mas grande que traiga ese encabezado."""
    candidatos = [Path(ruta)] if ruta else _archivos_entrada(PATRON_IS_FA)
    if not candidatos or not candidatos[0].exists():
        return None
    nombres = {"ramo": "RAMO", "mes": "MESPROC", **{k: norm(v) for k, v in COLUMNA_IS_FA.items()}}
    hoja, sin_enc, errores = None, [], []
    for cand in candidatos:
        try:
            wb = openpyxl.load_workbook(cand, read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            errores.append(f"{cand.name} ({type(e).__name__}: {e})")
            continue
        try:
            for ws in wb.worksheets:
                it = ws.iter_rows(values_only=True)
                filas = []
                for i, f in enumerate(it):                 # (el encabezado se busca en los primeros 40 renglones)
                    filas.append(f)
                    enc = [norm(x) for x in f]
                    if all(n in enc for n in nombres.values()):
                        j = {k: enc.index(n) for k, n in nombres.items()}
                        j_tipo = enc.index("TIPO") if "TIPO" in enc else None
                        ult = max(k for k, x in enumerate(f) if x not in (None, ""))
                        hoja, i_enc, cab = ws.title, i, [x for x in f[:ult + 1]]
                        filas += list(it)
                        break
                    if i >= 39:
                        break
                if hoja:
                    break
        finally:
            wb.close()
        if hoja:
            ruta = cand
            break
        sin_enc.append(cand.name)
    if hoja is None:
        raise ValueError(f"ningun archivo que cumple {PATRON_IS_FA} trae una hoja con el encabezado Ramo, MesProc, "
                         f"{', '.join(COLUMNA_IS_FA.values())} (revisados: {', '.join(sin_enc + errores)})")
    otros = [c.name for c in candidatos if c != ruta]
    tabla, val, tipo_val, por_tipo = [], {}, {}, {}
    omitidos, repetidos, negativos, altos, textos, no_num = [], [], [], [], [], []
    for i, f in enumerate(filas[i_enc + 1:], start=i_enc + 2):
        if not f or all(x in (None, "") for x in f):
            continue
        f = list(f[:len(cab)]) + [None] * (len(cab) - len(f))
        v_mes = f[j["mes"]]
        mes = float(v_mes.year * 100 + v_mes.month) if isinstance(v_mes, datetime) else a_numero(v_mes)[0]
        r_num = a_numero(f[j["ramo"]])[0]
        if not (np.isfinite(mes) and 190001 <= mes <= 299912 and 1 <= int(mes) % 100 <= 12 and np.isfinite(r_num)):
            omitidos.append(i)
            continue
        p, r = int(mes), str(int(r_num))
        f[j["mes"]], f[j["ramo"]] = p, int(r_num)
        tipo = f[j_tipo] if j_tipo is not None else None
        por_tipo.setdefault(tipo, set()).add(p)
        for pref in COLUMNA_IS_FA:
            x, era_texto = _num_is(f[j[pref]])
            if not np.isfinite(x):
                if isinstance(f[j[pref]], str) and f[j[pref]].strip():
                    no_num.append(f"{pref} {r} {p} ('{f[j[pref]].strip()}')")
                continue                               # sin dato de esa reserva: N/A en el bloque
            if era_texto:
                textos.append(f"{pref} {r} {p}")
                f[j[pref]] = x                         # (en la hoja IS_FA va como numero, igual que en el bloque)
            if x < 0:
                negativos.append(f"{pref} {r} {p}")
            if x > MAX_IS_FA:
                altos.append(f"{pref} {r} {p} ({x:,.2f})")
            if (pref, r, p) in val:
                if abs(val[(pref, r, p)] - x) > 1e-12:
                    repetidos.append(f"{pref} {r} {p}")
                continue
            val[(pref, r, p)], tipo_val[(pref, r, p)] = x, tipo
        tabla.append(tuple(f))
    if not val:
        raise ValueError(f"{ruta.name} › {hoja}: ningun renglon con Ramo, MesProc AAAAMM e indice numerico")
    avisos = []
    if repetidos:
        avisos.append(f"{len(repetidos)} indice(s) repetidos con otro valor para el mismo ramo y mes; se toma el primero "
                      f"({', '.join(repetidos[:5])})")
    if negativos:
        avisos.append(f"{len(negativos)} indice(s) negativos ({', '.join(negativos[:5])})")
    if altos:
        avisos.append(f"{len(altos)} indice(s) mayores a {MAX_IS_FA:.0%}: revisar si vienen en % y no como razon "
                      f"({', '.join(altos[:5])})")
    if textos:
        avisos.append(f"{len(textos)} indice(s) venian como texto y se tomaron como numero ({', '.join(textos[:5])})")
    if no_num:
        avisos.append(f"{len(no_num)} indice(s) con texto no numerico van en {TEXTO_SIN_DATO} ({', '.join(no_num[:5])})")
    if omitidos:
        avisos.append(f"{len(omitidos)} renglones sin MesProc AAAAMM o Ramo numerico omitidos (primero: renglon "
                      f"{omitidos[0]})")
    if otros:
        avisos.append(f"tambien cumplen {PATRON_IS_FA}: {', '.join(otros)}; se usa {ruta.name} (el mas grande con el "
                      "encabezado de indices)" + (f"; sin ese encabezado: {', '.join(sin_enc)}" if sin_enc else "")
                      + (f"; no se pudieron abrir: {', '.join(errores)}" if errores else ""))
    return {"ruta": ruta, "hoja": hoja, "cab": cab, "tabla": tabla, "val": val, "tipo": tipo_val,
            "periodos": sorted({p for _, _, p in val}), "ramos": sorted({r for _, r, _ in val}, key=int),
            "renglones": len(tabla), "omitidos": len(omitidos), "por_tipo": {k: sorted(v) for k, v in por_tipo.items()}, "otros": otros,
            "avisos": avisos}


def _mezcla(pe_hist: dict, ramos: list) -> dict:
    """{ramo: peso} con la PE historica de los ultimos 12 meses (partes iguales si no hay)."""
    ult = max((p for _, p in pe_hist), default=None)
    meses = [_mes_menos(ult, j) for j in range(12)] if ult else []
    pesos = {r: max(sum(pe_hist.get((r, m), 0.0) for m in meses), 0.0) for r in ramos}
    tot = sum(pesos.values())
    return {r: (pesos[r] / tot if tot > 0 else 1.0 / len(ramos)) for r in ramos}


def repartir_grupos(mensual: dict, pe_hist: dict) -> tuple[dict, list]:
    """PE del FCST con los grupos de GRUPOS_CON_MEZCLA como total del grupo repartido con la mezcla de PExRamo.
    Regresa (PE, ramos repartidos)."""
    if primas is None or not GRUPOS_CON_MEZCLA or not pe_hist:
        return mensual, []
    out, repartidos = dict(mensual), []
    for g in GRUPOS_CON_MEZCLA:
        ramos = [r for r in MAPA_RAMO_LAG if primas.GRUPO_DE_RAMO_RESERVA.get(r) == g]
        if not any(pe_hist.get((r, p)) for r in ramos for p in {q for _, q in pe_hist}):
            continue                             # sin historia del grupo: el FCST por ramo tal cual
        w = _mezcla(pe_hist, ramos)
        for p in sorted({q for (r, q) in mensual if r in ramos}):
            tot = sum(mensual.get((r, p), 0.0) for r in ramos)
            for r in ramos:
                out[(r, p)] = tot * w[r]
        repartidos += ramos
    return out, repartidos


def perfilar_reforecast(fa: dict, meses: list, pef_mensual: dict, grupos_mezcla: dict) -> tuple[dict, list]:
    """PERFIL_REFORECAST = "FCST": el total de los meses del reforecast de cada ramo se reparte entre esos meses con la
    mezcla mensual de los mismos meses del calendario en el FCST del ano siguiente (pef_mensual, {(ramo, periodo): USD};
    en los ramos de un grupo con mezcla, grupos_mezcla {ramo: [ramos del grupo]}, la mezcla es la del grupo). Un ramo
    sin FCST positivo en esos meses, o con total negativo o cero en el reforecast, se deja como viene. Regresa
    ({(ramo, periodo): USD}, [ramos reperfilados])."""
    out, hechos = dict(fa), []
    ramos = sorted({r for r, _ in fa})
    for r in ramos:
        if RAMOS_PERFIL_REFORECAST and r not in RAMOS_PERFIL_REFORECAST:
            continue
        tot = sum(fa.get((r, p), 0.0) for p in meses)
        base = grupos_mezcla.get(r, [r])
        pesos = {p: sum(pef_mensual.get((x, p + 100), 0.0) for x in base) for p in meses}   # mismo mes, ano siguiente
        if tot <= 0 or any(w < 0 for w in pesos.values()) or sum(pesos.values()) <= 0:
            continue
        s_w = sum(pesos.values())
        for p in meses:
            out[(r, p)] = tot * pesos[p] / s_w
        hechos.append(r)
    return out, hechos


def pe_reforecast(pr, pe_hist: dict, desde: int, hasta: int) -> dict:
    """PE de los meses entre la historia (PExRamo) y el FCST, del reforecast del ano por grupo que arma primas.py.
    Los grupos con varios ramos de la BD (30: 30, 34 y 37; 70: 71 y 73) se reparten con la mezcla de la PE historica
    de los ultimos 12 meses. {(ramo, periodo): USD}."""
    if pr is None or primas is None or desde > hasta:
        return {}
    out = {}
    for p in rango_periodos(desde, hasta):
        if p not in pr.mensual.index:
            continue
        for g in pr.mensual.columns:
            ramos = [r for r in MAPA_RAMO_LAG if primas.GRUPO_DE_RAMO_RESERVA.get(r) == g]
            if not ramos:
                continue
            v = float(pr.mensual.at[p, g])
            for r, w in _mezcla(pe_hist, ramos).items():
                out[(r, p)] = v * w
    return out


def pe_por_mes(pe_ramo: dict | None, pef: dict | None, pe_rf: dict | None = None,
               capturas: dict | None = None) -> dict:
    """{(ramo, periodo): (prima del mes USD, fuente)}: PExRamo en su historia, el reforecast entre la historia y el
    FCST (pe_rf: valor, o (valor, fuente) si no es el de primas.py), y el FCST en los meses que no traen los otros (en
    un mes que traigan varios, manda el real); una PE capturada en la BD de entrada solo entra en los meses que ninguna
    fuente trae."""
    out = {}
    if pef:
        for (r, p), v in pef["mensual"].items():
            out[(r, p)] = (float(v), (pef.get("fuente_ramo") or {}).get(r, pef["ruta"].name))
    for (r, p), v in (pe_rf or {}).items():       # (valor o (valor, fuente))
        out[(r, p)] = (float(v[0]), v[1]) if isinstance(v, tuple) else (float(v), "reforecast")
    if pe_ramo:
        for (r, p), v in pe_ramo["mensual"].items():
            out[(r, p)] = (float(v), pe_ramo["ruta"].name)
    for (r, p), v in (capturas or {}).items():
        out.setdefault((r, p), (float(v), "captura en la BD de entrada"))
    return out


def leer_capturas_pe(bd: BDMontos) -> dict:
    """PE FCST capturada con numero en la BD de entrada (columnas "PE FCST <ramo>", renglon BEL de RRC o, si no, de
    SONR): {(ramo, periodo): USD}. Un 0 no cuenta como captura: es el relleno que escribe la hoja en un mes sin PE (si la
    BD de salida se vuelve a usar como entrada, no debe completar ventanas de 12 meses que no tienen prima)."""
    ws = bd.ws
    enc = {norm(ws.cell(3, c).value): c for c in range(1, ws.max_column + 1) if ws.cell(3, c).value}
    out = {}
    for r in bd.cols_ramo:
        c = enc.get(norm(f"PE FCST {r}"))
        if c is None:
            continue
        for (conc, p), f in {**bd.filas, **bd.filas_prima}.items():    # (tambien los meses de prima sin montos)
            if conc in (norm("RRC BEL"), norm("SONR BEL")) and f in bd.filas_entrada:
                v = ws.cell(f, c).value
                if isinstance(v, str) and not v.strip().startswith("="):
                    v = a_numero(v)[0]                # texto numerico ("12,345"): cuenta como numero
                if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) and v != 0:
                    if conc == norm("RRC BEL") or (r, p) not in out:
                        out[(r, p)] = float(v)
    return out


def _suma_12(pe: dict) -> dict:
    """{(ramo, periodo): suma de la PE de los ultimos MESES_PRIMA_N_ANOS meses} donde estan todos."""
    out = {}
    for (r, p) in pe:
        ms = [indice_a_periodo(periodo_a_indice(p) - j) for j in range(MESES_PRIMA_N_ANOS)]
        if all((r, m) in pe for m in ms):
            out[(r, p)] = float(sum(pe[(r, m)][0] if isinstance(pe[(r, m)], tuple) else pe[(r, m)] for m in ms))
    return out


def _mes_menos(p: int, meses: int) -> int:
    return indice_a_periodo(periodo_a_indice(p) - meses)


def _hp_fuente(hp, resultados: dict, r_hp, nombre: str, periodo: int, pos_proy: dict):
    """Indice o LAG del mes como lo toma la hoja: (valor, ("celda", periodo)) del renglon Real o de Proyeccion;
    (valor, ("interp", pa, pb, k, n)) en un hueco de hasta MAX_HUECO_INTERPOLABLE meses sin cambio de nivel (como la
    preparacion de las series); (nan, None) si no hay con que."""
    if r_hp is None:
        return math.nan, None
    if periodo > hp.ultimo:
        res = resultados.get(("HPARAM", HOJA_PARAMETROS, nombre, r_hp))
        if res is None or periodo not in pos_proy:
            return math.nan, None
        v = float(res.pronostico[pos_proy[periodo]])
        return (v, ("celda", periodo)) if np.isfinite(v) else (math.nan, None)
    hist = hp.historia.get((r_hp, nombre), {})
    v = hist.get(periodo, math.nan)
    if np.isfinite(v) and (r_hp, periodo) in hp.filas:
        return float(v), ("celda", periodo)
    antes = [q for q, x in hist.items() if q < periodo and np.isfinite(x) and (r_hp, q) in hp.filas]
    despues = [q for q, x in hist.items() if q > periodo and np.isfinite(x) and (r_hp, q) in hp.filas]
    if not antes or not despues:
        return math.nan, None
    pa, pb = max(antes), min(despues)
    n = periodo_a_indice(pb) - periodo_a_indice(pa) - 1
    a_, b_ = hist[pa], hist[pb]
    if n > MAX_HUECO_INTERPOLABLE or (a_ > 0 and b_ > 0 and max(a_, b_) / min(a_, b_) > SALTO_NIVEL_HUECO):
        return math.nan, None
    k = periodo_a_indice(periodo) - periodo_a_indice(pa)
    return float(a_ + (b_ - a_) * k / (n + 1)), ("interp", pa, pb, k, n + 1)


def _peacumulada(pref: str, r, p: int, p12: dict, lags: dict):
    """PEACUMULADA del mes: RRC = PRIMA N AÑOS; SONR = suma de LAG k del mes x PRIMA N AÑOS del mismo mes k - 1 anos
    antes (ANIOS_LAG_PEACUMULADA). lags = {k: valor}. nan si falta algun termino."""
    anios = ANIOS_LAG_PEACUMULADA.get(pref)
    if not anios:
        return p12.get((r, p), math.nan)
    tot = 0.0
    for k in range(1, anios + 1):
        x, lag = p12.get((r, _mes_menos(p, 12 * (k - 1)))), lags.get(k, math.nan)
        if x is None or not np.isfinite(lag):
            return math.nan
        tot += lag * x
    return tot


def _cambio_mensual(res: Resultado, ultimo_real: float) -> float:
    """Pendiente mensual proyectada (la del primer mes, antes de amortiguar) en unidades de la razon: en logaritmos,
    ultimo real x (e^pendiente - 1); en niveles, la pendiente."""
    b = (res.parametros or {}).get("pendiente", math.nan)
    if not np.isfinite(b) or not np.isfinite(ultimo_real):
        return math.nan
    return float(ultimo_real * math.expm1(b)) if res.transformacion == "log" else float(b)


def _nota_cesion_area() -> str:
    """Texto de la cesion por indicacion del area (CESION_OBJETIVO y CESION_TENDENCIA) para la hoja, el Resumen y el README
    de la corrida; "" si no hay indicaciones."""
    partes = []
    if CESION_OBJETIVO:
        mes = CESION_OBJETIVO_MES or PERIODO_FIN
        partes.append("en linea recta desde el ultimo real hasta " + ", ".join(
            f"{pr} {r}: {v * 100:g}%" for (pr, r), v in sorted(CESION_OBJETIVO.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))))
                      + f" en {mes} (CESION_OBJETIVO)")
    if CESION_TENDENCIA:
        partes.append(", ".join(f"{pr} {r}: la tendencia de sus ultimos {n} meses (Theil-Sen, frenada "
                                f"{1 - PENDIENTE_COMBINADA['amortiguacion']:.0%} por mes)"
                                for (pr, r), n in sorted(CESION_TENDENCIA.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))))
                      + " (CESION_TENDENCIA)")
    return "; por indicacion del area, " + "; ".join(partes) if partes else ""


def _cesion_area(pref: str, ramo, per: list[int], vals: list[float], f_modelo, periodos_proy: list[int], dom) -> tuple:
    """Cesion de un ramo por indicacion del area, en lugar de la del modelo (SES): CESION_OBJETIVO = camino en linea recta
    del ultimo real al objetivo en CESION_OBJETIVO_MES (despues se queda ahi); CESION_TENDENCIA = recta Theil-Sen de los
    ultimos n meses reales, frenada por mes como la pendiente combinada. Acotada a dom. Regresa (f, None) si el ramo no
    tiene indicacion; si la tiene, (f nuevo, {"modelo", "regla", "cambio_mensual", "alerta"})."""
    clave = (pref, str(ramo))
    if clave not in CESION_OBJETIVO and clave not in CESION_TENDENCIA:
        return f_modelo, None
    y = np.asarray(vals, dtype=float)
    ok = np.where(np.isfinite(y))[0]
    if not len(ok) or not periodos_proy:
        return f_modelo, None
    u, ultimo = float(y[ok[-1]]), per[int(ok[-1])]
    h = len(periodos_proy)
    lo = -math.inf if dom[0] is None else float(dom[0])
    hi = math.inf if dom[1] is None else float(dom[1])
    f_mod = float(f_modelo[-1]) if len(f_modelo) else math.nan
    if clave in CESION_OBJETIVO:
        objetivo = float(CESION_OBJETIVO[clave])
        mes_obj = int(CESION_OBJETIVO_MES or periodos_proy[-1])
        if mes_obj not in periodos_proy:
            raise ValueError(f"CESION_OBJETIVO_MES = {mes_obj} no es un mes proyectado ({periodos_proy[0]} a "
                             f"{periodos_proy[-1]}): pon un mes del horizonte o None (el ultimo)")
        n = periodos_proy.index(mes_obj) + 1
        f = u + (objetivo - u) * np.minimum(np.arange(1, h + 1), n) / n
        cambio = (objetivo - u) / n
        texto = (f"indicacion del area: de {u:.1%} ({ultimo}) a {objetivo:.1%} en {mes_obj}, en linea recta "
                 f"({cambio * 100:+.2f} pts por mes){', y se queda ahi' if n < h else ''}; el modelo (SES) daba {f_mod:.1%}")
        return np.clip(f, lo, hi), {"modelo": "indicacion del area: objetivo", "regla": texto, "cambio_mensual": cambio,
                                    "alerta": texto}
    n = max(2, int(CESION_TENDENCIA[clave]))
    w = y[ok[-n:]]                                            # los ultimos n meses con dato
    if len(w) < 3:                                            # (sin historia suficiente: se queda el modelo, con aviso)
        return f_modelo, None
    b, _ = _recta_robusta(w, "theil")                         # puntos por mes
    if not np.isfinite(b):
        return f_modelo, None
    phi = PENDIENTE_COMBINADA["amortiguacion"]
    f = np.clip(u + b * np.cumsum(phi ** np.arange(1, h + 1)), lo, hi)
    texto = (f"indicacion del area: sigue la tendencia de sus ultimos {len(w)} meses reales ({b * 100:+.2f} pts por mes, "
             f"Theil-Sen, frenada {1 - phi:.0%} por mes): de {u:.1%} ({ultimo}) a {float(f[-1]):.1%} ({periodos_proy[-1]}); "
             f"el modelo (SES) daba {f_mod:.1%}")
    return f, {"modelo": "indicacion del area: tendencia del ultimo ano", "regla": texto, "cambio_mensual": float(b),
               "alerta": texto}


def _factores_fijos_txt(fijos: bool = True) -> str:
    """'FACTOR GTO y FACTOR MR' (los de FACTORES_BEL_FIJOS, o los que no estan si fijos=False)."""
    return " y ".join(f for f in ("FACTOR GTO", "FACTOR MR") if (f in FACTORES_BEL_FIJOS) == fijos)


def _razones_modelo_txt() -> str:
    """Como se proyectan las razones del modelo (%GTO, %MR, %cedido), segun FACTORES_BEL_FIJOS."""
    pares = (("FACTOR GTO", "%GTO"), ("FACTOR MR", "%MR"))
    fijas = [c for f, c in pares if f in FACTORES_BEL_FIJOS]
    ses = [c for f, c in pares if f not in FACTORES_BEL_FIJOS] + ["%cedido"]
    if not fijas:
        return "Razones (%GTO, %MR, %cedido): SES (nivel sin tendencia). "
    return (f"Razones: {' y '.join(fijas)} de Danos fijos en su ultimo real (FACTORES_BEL_FIJOS, indicacion del area; "
            f"un real negativo se lleva a 0); {', '.join(ses)}: SES (nivel sin tendencia). ")


def fijar_margenes_modelo(resultados: dict, h: int) -> list:
    """FACTORES_BEL_FIJOS en el modelo de la serie de Danos: las razones GTO / BEL y MR / BEL proyectadas se quedan en
    su ultimo real (un real negativo se lleva a 0), para que los ramos y meses que no llevan BEL por FND (p. ej. SONR 37)
    tambien conserven su margen. Regresa las series que fijo."""
    concepto = {"FACTOR GTO": "GTO", "FACTOR MR": "MR"}
    hechas = []
    for k, r in resultados.items():
        if k[0] != "DANOS" or not r.historia_valores:
            continue
        if any(k[2] == f"{concepto[f]}/BEL" for f in FACTORES_BEL_FIJOS if f in concepto):
            u_r = float(r.historia_valores[-1])
            u = max(0.0, u_r)
            r.pronostico, r.li, r.ls = [u] * h, [u] * h, [u] * h
            r.modelo = f"fijo en el ultimo real ({r.historia_periodos[-1]}; FACTORES_BEL_FIJOS)"
            r.parametros, r.tendencia_mensual = {}, 0.0
            r.error_modelo = r.error_ultimo_valor        # (lo que se proyecta es repetir el ultimo valor)
            r.alertas = [x for x in r.alertas
                         if not x.startswith(("En el backtest de esta serie el modelo (", "Proyeccion fuera del dominio",
                                              "Cambio proyectado a"))]
            if u != u_r:
                r.alertas.append(f"Ultimo real negativo ({u_r:.2%}): el margen se fija en 0")
            hechas.append(k)
    return hechas


def _patron_mes(per: list, vals: list, modo: str) -> tuple[np.ndarray, str]:
    """Patron por mes del ano (12 valores en logaritmos, centrados en cero) de una serie positiva, sobre los ultimos
    MESES_ESTACIONALIDAD meses: con modo "credibilidad", el de factores_estacionales (ponderado por su credibilidad);
    con "observada", el promedio por mes de la serie menos su media movil centrada de 12 meses, sin ponderar; con
    "ninguna" (o sin historia suficiente), ceros. Regresa (patron, texto)."""
    ok = [(p, v) for p, v in zip(per, vals) if np.isfinite(v) and v > 0]
    if modo == "ninguna" or len(ok) < MIN_OBS_ESTACIONALIDAD:
        return np.zeros(12), ("sin patron del mes" if modo == "ninguna" else
                              f"sin patron del mes (menos de {MIN_OBS_ESTACIONALIDAD} meses de historia)")
    z = np.log([v for _, v in ok])
    meses = np.array([p % 100 for p, _ in ok])
    fe = factores_estacionales(z, meses)
    if fe is None:
        return np.zeros(12), "sin patron del mes (historia insuficiente)"
    if modo == "observada":
        n_v = MESES_ESTACIONALIDAD or len(z)
        zz, mm_ = z[-n_v:], meses[-n_v:]
        pesos = np.r_[0.5, np.ones(11), 0.5] / 12.0
        det = zz[6:len(zz) - 6] - np.convolve(zz, pesos, mode="valid")
        mm = mm_[6:len(zz) - 6]
        s = np.array([det[mm == k].mean() if np.any(mm == k) else 0.0 for k in range(1, 13)])
        s -= s.mean()
        return s, (f"patron del mes observado (sin ponderar; credibilidad {fe['credibilidad']:.0%}, amplitud "
                   f"{s.max() - s.min():.1%})")
    s = fe["factores"]
    return s, f"patron del mes con credibilidad {fe['credibilidad']:.0%} (amplitud {s.max() - s.min():.1%})"


def _suavizar_bel(out: dict, pref: str, r, periodos_proy: list[int], ultimo: int, bel_u: float, modo: str,
                  hist: dict, fila: dict):
    """SUAVIZAR_BEL: deja el BEL de cada diciembre proyectado (y del ultimo mes proyectado) y lleva los meses de en medio
    a una linea en logaritmos entre anclas (el ultimo real y esos meses) mas el patron del mes de la historia (_patron_mes),
    puesto en cero en las anclas. Ajusta el FND del mes para que IS x PEACUMULADA x FND de ese BEL y recalcula GTO, MR,
    BRUTO, IRR y NETO con los mismos factores. Escribe en out (proy, fnd, series, neto_fijo, suavizado, alertas) y fila."""
    c_bel = norm(f"{pref} BEL")
    bel = {p: out["proy"][(c_bel, p, r)] for p in periodos_proy}
    anclas = {ultimo: bel_u, **{p: bel[p] for p in periodos_proy if p % 100 == 12 or p == periodos_proy[-1]}}
    per_h = sorted(hist)
    s, texto = _patron_mes(per_h, [hist[p] for p in per_h], modo)
    sf = lambda p: float(s[(p % 100) - 1])        # noqa: E731
    todos = [ultimo] + list(periodos_proy)
    pos = {p: i for i, p in enumerate(todos)}
    ka = sorted(anclas)
    objetivo = {}
    for a, b in zip(ka, ka[1:]):
        for p in todos[pos[a]: pos[b] + 1]:
            w = (pos[p] - pos[a]) / (pos[b] - pos[a])
            objetivo[p] = math.exp((1 - w) * math.log(anclas[a]) + w * math.log(anclas[b])
                                   + sf(p) - ((1 - w) * sf(a) + w * sf(b)))
    filas_serie = {x["Periodo"]: x for x in out["series"] if x["Reserva"] == pref and x["Ramo"] == r}
    for p in periodos_proy:
        k = objetivo[p] / bel[p] if bel[p] else 1.0
        raz = out["razones"][(pref, p, r)]
        fnd0 = out["fnd"][(pref, p, r)]
        out["fnd"][(pref, p, r)] = fnd0 * k
        b_n = bel[p] * k
        x = filas_serie[p]
        pnd = float(x["PEACUMULADA"]) * fnd0 * k        # PND = BEL / IS = PEACUMULADA x FND
        gto, mr = pnd * raz.get("FACTOR GTO", 0.0), pnd * raz.get("FACTOR MR", 0.0)
        bruto = b_n + gto + mr
        irr = bruto * raz.get("CESION", 0.0)
        nuevos = {"BEL": b_n, "MR": mr, "BRUTO": bruto, "IRR": irr, "NETO": bruto - irr}
        if pref == "RRC":
            nuevos["GTO"] = gto
        for c, v in nuevos.items():
            out["proy"][(norm(f"{pref} {c}"), p, r)] = float(v)
        if (pref, p, r) in out["neto_fijo"]:
            out["neto_fijo"][(pref, p, r)] *= k
        x.update({"BEL antes del suavizado": bel[p], "FND antes del suavizado": fnd0, "FND": fnd0 * k,
                  "BEL IS x PEACUMULADA x FND": b_n})
    cambios = lambda d: np.diff(np.log([d[p] for p in todos]))          # noqa: E731
    antes = cambios({ultimo: bel_u, **bel})
    despues = cambios({ultimo: bel_u, **{p: objetivo[p] for p in periodos_proy}})
    resumen = (f"BEL de {', '.join(str(a) for a in ka[1:])} fijo y los meses de en medio en linea entre anclas; "
               f"{texto}; cambio mensual: desviacion estandar {np.std(antes):.1%} -> {np.std(despues):.1%}, mayor "
               f"{np.max(np.abs(antes)):.1%} -> {np.max(np.abs(despues)):.1%}")
    fila["Suavizado entre diciembres"] = resumen
    out.setdefault("suavizado", {})[(pref, str(r))] = {"texto": resumen, "modo": modo, "anclas": ka[1:]}
    out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}", f"SUAVIZAR_BEL: {resumen} (el FND de esos meses se ajusta "
                           "para dar el BEL suavizado: el FND lleva el inverso de los brincos de IS x PEACUMULADA, y el "
                           "PND / PD y el MR el de los brincos del IS del mes; BRUTO y NETO quedan suaves)"))


def calcular_bel_fnd(bd: BDMontos, hp, resultados: dict, proy: dict, pe: dict, periodos_proy: list[int],
                     ultimo: int, is_fa_val: dict | None = None, bel_area: dict | None = None,
                     motivo_area: dict | None = None, indicaciones_area: bool = True) -> dict:
    """BEL por FND: FND = PND / PEACUMULADA en la historia (PND = BEL / IS), proyectado con la tendencia desde el primer
    mes proyectado; BEL = IS x PEACUMULADA x FND; GTO = PND x FACTOR GTO y MR = PND x FACTOR MR (PND = BEL / IS), con los
    factores reales proyectados con el modelo del FND (TIPO_MODELO_FACTORES); BRUTO = BEL + GTO + MR; IRR = BRUTO x CESION (IRR /
    BRUTO real proyectado igual); NETO = BRUTO - IRR.
    En los ramos de RAMOS_IS_FA_BEL el IS del BEL (y del PND / PD) es el de la funcion actuarial, is_fa_val
    {(reserva, ramo, periodo): IS}; sin IS (FA) en un mes, el IS (RL) con aviso.
    En las series de BEL_METODO_AREA sin BEL real positivo al ultimo mes, la historia del FND y de los factores sale de
    bel_area (leer_bel_metodo_area: BEL, MR, BRUTO e IRR del metodo del area) en lugar de la BD; motivo_area {(reserva,
    ramo): texto} dice por que una de esas series no trae datos. "estado_area" {(reserva, ramo): texto} y "sin_area"
    [textos] dicen si se uso y, si no, por que (para la consola, el diagnostico y el tablero).
    Regresa {"proy": montos con el BEL nuevo, "aplica": {(reserva, periodo, ramo)}, "fnd": {(reserva, periodo, ramo):
    FND proyectado}, "razones": {...}, "is_fa_bel": {(reserva, periodo, ramo) con IS (FA)}, "series": filas para el
    diagnostico, "resumen", "estado"}."""
    h = len(periodos_proy)
    pos = {p: i for i, p in enumerate(periodos_proy)}
    p12 = _suma_12(pe)
    out = {"proy": dict(proy), "aplica": set(), "fnd": {}, "razones": {}, "series": [], "resumen": [], "estado": "",
           "p12": p12, "alertas": [], "neto_fijo": {}, "is_fa_bel": set(), "bel_area": {}, "estado_area": {},
           "sin_area": [], "cesion_area": set()}
    is_fa_val = is_fa_val or {}
    bel_area, motivo_area = bel_area or {}, motivo_area or {}
    config_area = _bel_metodo_area()
    if not pe:
        out["estado"] = "sin PE por ramo (PExRamo y FCST): el BEL sigue con el modelo"
        return out
    per_hist = sorted({p for (_, p) in bd.filas if p <= ultimo})
    for pref, (nombre_is, _) in INDICE_BASE_PND.items():
        anios = ANIOS_LAG_PEACUMULADA.get(pref, 0)
        for r in bd.cols_ramo:
            r_hp = MAPA_RAMO_LAG.get(str(r))

            def peac(p):
                lags = {k: _hp_fuente(hp, resultados, r_hp, f"LAG {k}", p, pos)[0] for k in range(1, anios + 1)}
                return _peacumulada(pref, r, p, p12, lags)
            # historia: la BD (SAP) o, en las series de BEL_METODO_AREA sin BEL real positivo al ultimo mes, el BEL, MR,
            # BRUTO e IRR del metodo del area (Res_Rvas)
            area = bel_area.get((pref, str(r))) if (pref, str(r)) in config_area else None
            bel_u_bd = bd.valores.get((f"{pref} BEL", ultimo, r), math.nan)
            usa_area = area is not None and not (np.isfinite(bel_u_bd) and bel_u_bd > UMBRAL_CERO_MONTOS)

            def val(conc, p, _area=area if usa_area else None, _pref=pref, _r=r):
                if _area is not None:
                    return _area["valores"].get((conc, p), math.nan)
                return bd.valores.get((f"{_pref} {conc}", p, _r), math.nan)
            fnd_h, per_ok = [], []
            for p in per_hist:
                bel = val("BEL", p)
                is_ = _hp_fuente(hp, resultados, r_hp, nombre_is, p, pos)[0]
                pa = peac(p)
                f = (bel / is_) / pa if np.isfinite(bel) and np.isfinite(is_) and is_ != 0 and np.isfinite(pa) \
                    and pa != 0 else math.nan
                fnd_h.append(f)
                if np.isfinite(f):
                    per_ok.append(p)
            fila = {"Reserva": pref, "Ramo": r, "Meses de FND real": len(per_ok),
                    "Desde": per_ok[0] if per_ok else None, "Hasta": per_ok[-1] if per_ok else None,
                    "Historia del BEL": "BD (SAP)"}
            if usa_area:
                escs = sorted(set(area["escenarios"].values()), key=config_area[(pref, str(r))].index)
                otros = [f"{q}: escenario {e}" for q, e in sorted(area["escenarios"].items()) if e != escs[0]]
                fila["Historia del BEL"] = (f"metodo del area ({', '.join(area['archivos'])}, hoja Base {pref}, "
                                            f"escenario {escs[0]}{'; ' + ', '.join(otros) if otros else ''}): SAP "
                                            f"registra BEL {f'{bel_u_bd:,.0f}' if np.isfinite(bel_u_bd) else 'vacio'} en {ultimo}")
            elif area is not None:
                fila["Historia del BEL"] = "BD (SAP): ya registra BEL, no se usa el metodo del area"
                out["estado_area"][(pref, str(r))] = "SAP: ya registra BEL"
            elif (pref, str(r)) in config_area and np.isfinite(bel_u_bd) and bel_u_bd > UMBRAL_CERO_MONTOS:
                out["estado_area"][(pref, str(r))] = "SAP: ya registra BEL"     # (no hace falta el metodo del area)
            elif (pref, str(r)) in config_area:                # sin datos del metodo del area y SAP en 0
                m_a = motivo_area.get((pref, str(r)), "sin datos del metodo del area")
                fila["Historia del BEL"] = f"sin metodo del area: {m_a}"
                out["estado_area"][(pref, str(r))] = f"sin metodo del area: {m_a}"
                out["sin_area"].append(f"{pref} {r}: {m_a}")
                out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}",
                                       f"SAP registra BEL {f'{bel_u_bd:,.0f}' if np.isfinite(bel_u_bd) else 'vacio'} en "
                                       f"{ultimo} y no hay historia del metodo del area ({m_a}): el BEL proyectado queda "
                                       "con el modelo (0, sin formula)"))
            motivo = ""
            bel_u = val("BEL", ultimo)
            if len(per_ok) < MIN_MESES_FND:
                motivo = f"menos de {MIN_MESES_FND} meses de FND real (falta PE, IS o LAG)"
            elif not (np.isfinite(bel_u) and bel_u > 0):
                motivo = (f"el BEL del metodo del area llega a {area['meses'][-1]} y el real a {ultimo}: actualiza los "
                          "Res_Rvas de entradas/ con el mes" if usa_area else "BEL real no positivo al ultimo mes")
            fnd_f = None
            if not motivo:
                per = rango_periodos(per_ok[0], ultimo)
                v = [fnd_h[per_hist.index(p)] if p in per_hist else math.nan for p in per]
                res = pronosticar(Serie(("DANOS", pref, "FND", r), TIPO_MODELO_FND, per, v, ultimo, h,
                                        dominio=(0.0, None)))
                fnd_f = np.asarray(res.pronostico, dtype=float)
                out["alertas"] += [("DANOS", f"{pref} | FND | ramo {r}", a) for a in res.alertas
                                   if str(a).startswith(("Pendiente combinada", "Holt con guardia"))]
                prm_fnd = res.parametros or {}
                fila.update({"Modelo": res.modelo if hasattr(res, "modelo") else "",
                             "FND regla de la pendiente": res.regla or prm_fnd.get("regla_pendiente", ""),
                             "Cambio mensual de la tendencia del FND": _cambio_mensual(res, [x for x in v if np.isfinite(x)][-1]),
                             "Error % backtest (modelo)": getattr(res, "error_modelo", math.nan),
                             "Error % backtest (ultimo valor)": getattr(res, "error_ultimo_valor", math.nan),
                             f"FND {ultimo}": fnd_h[per_hist.index(ultimo)] if ultimo in per_hist else math.nan,
                             f"FND {periodos_proy[-1]}": fnd_f[-1] if len(fnd_f) == h else math.nan})
                if len(fnd_f) != h:
                    motivo, fnd_f = "no se pudo proyectar el FND", None
            # FACTOR GTO, FACTOR MR y CESION reales (como los bloques de la hoja) y su recta desde el primer mes proyectado
            fac_f, fac_u = {}, {}
            if fnd_f is not None:
                specs = {"FACTOR GTO": ("GTO", "PND", DOMINIO_RAZON_BEL)} if pref == "RRC" else {}
                specs.update({"FACTOR MR": ("MR", "PND", DOMINIO_RAZON_BEL), "CESION": ("IRR", "BRUTO", DOMINIO_CESION)})
                for nombre, (conc, base, dom) in specs.items():
                    vals = {}
                    for p in per_hist:
                        x = val(conc, p)
                        if base == "PND":
                            bel = val("BEL", p)
                            is_ = _hp_fuente(hp, resultados, r_hp, nombre_is, p, pos)[0]
                            d = bel / is_ if np.isfinite(bel) and np.isfinite(is_) and is_ != 0 else math.nan
                        else:
                            d = val("BRUTO", p)
                        vals[p] = x / d if np.isfinite(x) and np.isfinite(d) and d != 0 else math.nan
                    ok_p = [p for p in per_hist if np.isfinite(vals[p])]
                    f = np.zeros(h)
                    clave_al = f"{pref} | {nombre} | ramo {r}"
                    if ok_p:
                        per_f = rango_periodos(ok_p[0], ultimo)
                        res_f = pronosticar(Serie(("DANOS", pref, nombre, r), TIPO_MODELO_FACTORES[nombre], per_f,
                                                  [vals.get(q, math.nan) for q in per_f], ultimo, h, dominio=dom))
                        f = np.asarray(res_f.pronostico, dtype=float)
                        if len(f) != h or not np.all(np.isfinite(f)):
                            f = np.full(h, vals[ok_p[-1]])          # (sin modelo: el ultimo real)
                        prm = res_f.parametros or {}
                        regla_p = prm.get("regla_pendiente", "")
                        if not regla_p and res_f.modelo == "SES":
                            regla_p = f"nivel suavizado (SES, alpha {prm.get('alpha', math.nan):.2f}), sin tendencia"
                        modelo_txt, cambio_txt = res_f.regla or res_f.modelo, _cambio_mensual(res_f, vals[ok_p[-1]])
                        area_ces = None
                        if nombre == "CESION" and indicaciones_area:   # cesion por indicacion del area (CESION_OBJETIVO, CESION_TENDENCIA)
                            f, area_ces = _cesion_area(pref, r, per_f, [vals.get(q, math.nan) for q in per_f], f,
                                                       periodos_proy, dom)
                            if area_ces:
                                modelo_txt, regla_p = area_ces["modelo"], area_ces["regla"]
                                cambio_txt = area_ces["cambio_mensual"]
                                out["alertas"].append(("DANOS", clave_al, area_ces["alerta"]))
                                out["cesion_area"].add((pref, str(r)))
                            if len(f) != h or not np.all(np.isfinite(f)):
                                f = np.full(h, vals[ok_p[-1]])      # (por si la indicacion no dio un camino finito)
                        fijo = nombre in FACTORES_BEL_FIJOS
                        if fijo:                               # margen fijo en su ultimo real (indicacion del area)
                            u_f = vals[ok_p[-1]]
                            u_f = max(u_f, dom[0]) if dom[0] is not None else u_f
                            u_f = min(u_f, dom[1]) if dom[1] is not None else u_f
                            f = np.full(h, float(u_f))
                            modelo_txt = f"fijo en el ultimo real ({ok_p[-1]}; FACTORES_BEL_FIJOS)"
                            regla_p, cambio_txt = "sin pendiente: el ultimo real", 0.0
                            if ok_p[-1] != ultimo:
                                out["alertas"].append(("DANOS", clave_al, f"sin {nombre} real en {ultimo}: se fija el de "
                                                       f"{ok_p[-1]} ({u_f:.2%})"))
                            i_f = per_f.index(ok_p[-1]) if ok_p[-1] in per_f else len(per_f) - 1
                            prev = [vals[q] for q in per_f[max(0, i_f - 12):i_f] if np.isfinite(vals.get(q, math.nan))]
                            med = float(np.median(prev)) if len(prev) >= 6 else math.nan
                            if np.isfinite(med) and med > 0 and abs(vals[ok_p[-1]] / med - 1) > UMBRAL_MARGEN_ATIPICO:
                                txt_at = (f"el {nombre} que se fija ({vals[ok_p[-1]]:.2%} en {ok_p[-1]}) esta "
                                          f"{vals[ok_p[-1]] / med - 1:+.0%} contra la mediana de los 12 meses anteriores "
                                          f"({med:.2%}): confirma que ese mes es el que se quiere fijar")
                                if u_f != vals[ok_p[-1]]:
                                    txt_at += f" (fuera del dominio del factor: se fija en {u_f:.2%})"
                                out["alertas"].append(("DANOS", clave_al, txt_at))
                                out.setdefault("margen_atipico", []).append(
                                    {"Reserva": pref, "Ramo": r, "Factor": nombre, "Fijo": float(vals[ok_p[-1]]), "Se fija en": float(u_f),
                                     "Mes": ok_p[-1], "Mediana 12 meses anteriores": med})
                        fila.update({f"{nombre} modelo": modelo_txt,
                                     f"{nombre} regla de la pendiente": regla_p,
                                     f"{nombre} cambio mensual de la tendencia": cambio_txt,
                                     f"{nombre} error % backtest (modelo)": (res_f.error_ultimo_valor if fijo else
                                                                             res_f.error_modelo),
                                     f"{nombre} error % backtest (ultimo valor)": res_f.error_ultimo_valor})
                        out["alertas"] += [("DANOS", clave_al, a) for a in res_f.alertas
                                           if not str(a).startswith("Se usa") and not fijo]
                        u = vals[ok_p[-1]]
                        fuera = [q for q in per_f[-MESES_TENDENCIA:] if np.isfinite(vals.get(q, math.nan))
                                 and ((dom[0] is not None and vals[q] < dom[0]) or (dom[1] is not None and vals[q] > dom[1]))]
                        if fuera:
                            out["alertas"].append(("DANOS", clave_al, f"{len(fuera)} mes(es) real(es) fuera de rango "
                                                   f"({fuera[0]} a {fuera[-1]}; ultimo {u:.2%}): revisar {conc} y "
                                                   f"{base} de origen; la proyeccion se acota a {dom}"))
                        if nombre == "CESION" and area_ces is None and abs(f[-1] - u) > 0.10:
                            out["alertas"].append(("DANOS", clave_al, f"la proyeccion lleva la cesion de {u:.1%} ({ultimo}) a "
                                                   f"{f[-1]:.1%} ({periodos_proy[-1]}); revisar si la tendencia sigue"))
                        elif nombre != "CESION" and u > 0 and f[-1] < 0.5 * u:
                            out["alertas"].append(("DANOS", clave_al, f"la proyeccion baja el factor de {u:.2%} ({ultimo}) a "
                                                   f"{f[-1]:.2%} ({periodos_proy[-1]}), menos de la mitad"))
                        fac_u[nombre] = min(max(u, dom[0] if dom[0] is not None else u), dom[1] if dom[1] is not None else u)
                    fac_f[nombre] = f
                    fila[f"{nombre} {ultimo}"] = vals.get(ultimo, math.nan)
                    fila[f"{nombre} {periodos_proy[-1]}"] = float(f[-1])
            n_ap, sin_fa = 0, []
            con_fa = str(r) in RAMOS_IS_FA_BEL.get(pref, ())     # el BEL con el IS de la funcion actuarial
            fila["IS del BEL"] = "IS (FA)" if con_fa else "IS (RL)"
            for j, p in enumerate(periodos_proy):
                is_rl = _hp_fuente(hp, resultados, r_hp, nombre_is, p, pos)[0]
                is_f, fuente_is = is_rl, "RL"
                if con_fa:
                    v_fa = is_fa_val.get((pref, str(r), p))
                    if v_fa is not None and np.isfinite(v_fa):
                        is_f, fuente_is = float(v_fa), "FA"
                    else:
                        sin_fa.append(p)
                pa = peac(p)
                fz = fnd_f[j] if fnd_f is not None else math.nan
                bel_m = proy.get((norm(f"{pref} BEL"), p, r), math.nan)
                bel_n = is_f * pa * fz if all(np.isfinite(x) for x in (is_f, pa, fz)) else math.nan
                fac = {k: float(v[j]) for k, v in fac_f.items()}
                out["series"].append({"Reserva": pref, "Ramo": r, "Periodo": p, "IS": is_f, "IS usado": fuente_is,
                                      "IS (RL)": is_rl, "PEACUMULADA": pa,
                                      "FND": fz, "BEL IS x PEACUMULADA x FND": bel_n, "BEL del modelo": bel_m,
                                      "FACTOR GTO": fac.get("FACTOR GTO", math.nan),
                                      "FACTOR MR": fac.get("FACTOR MR", math.nan), "CESION": fac.get("CESION", math.nan)})
                if not np.isfinite(bel_n) or bel_n < 0:           # (PE o IS negativos: el mes sigue con el modelo)
                    continue
                out["fnd"][(pref, p, r)] = float(fz)
                if fuente_is == "FA":
                    out["is_fa_bel"].add((pref, p, r))
                raz = {"FACTOR GTO": fac.get("FACTOR GTO", 0.0) if pref == "RRC" else 0.0,
                       "FACTOR MR": fac.get("FACTOR MR", 0.0), "CESION": fac.get("CESION", 0.0)}
                pnd_f = pa * fz                                    # PND (PD) = BEL / IS = PEACUMULADA x FND
                gto, mr = pnd_f * raz["FACTOR GTO"], pnd_f * raz["FACTOR MR"]
                bruto = bel_n + gto + mr
                irr = bruto * raz["CESION"]
                nuevos = {"BEL": bel_n, "MR": mr, "BRUTO": bruto, "IRR": irr, "NETO": bruto - irr}
                if pref == "RRC":
                    nuevos["GTO"] = gto
                for c, x in nuevos.items():
                    out["proy"][(norm(f"{pref} {c}"), p, r)] = float(x)
                b_fijo = bel_n + pnd_f * ((fac_u.get("FACTOR GTO", 0.0) if pref == "RRC" else 0.0)
                                          + fac_u.get("FACTOR MR", 0.0))      # comparativo: factores fijos
                out["neto_fijo"][(pref, p, r)] = b_fijo * (1 - fac_u.get("CESION", 0.0))
                out["razones"][(pref, p, r)] = raz
                out["aplica"].add((pref, p, r))
                n_ap += 1
            modo_s = SUAVIZAR_BEL.get((pref, str(r))) if indicaciones_area else None
            if modo_s:
                bel_s = [out["proy"].get((norm(f"{pref} BEL"), p, r), math.nan) for p in periodos_proy]
                if n_ap != h or not (np.isfinite(bel_u) and bel_u > 0) or not all(np.isfinite(x) and x > 0 for x in bel_s):
                    out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}", "indicacion del area (SUAVIZAR_BEL) sin "
                                           f"aplicar: {n_ap} de {h} meses con BEL por FND"
                                           + (f" ({motivo})" if motivo else "") + " o un BEL no positivo; queda sin suavizar"))
                else:
                    try:
                        _suavizar_bel(out, pref, r, periodos_proy, ultimo, bel_u, modo_s,
                                      {p: val("BEL", p) for p in per_hist}, fila)
                    except Exception as e:  # noqa: BLE001
                        out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}", f"no se pudo suavizar ({type(e).__name__}: "
                                               f"{e}); queda sin suavizar"))
            fila["Meses con BEL por FND"] = n_ap
            if usa_area and not n_ap:                      # (no se pudo usar: la serie queda con el modelo, en 0)
                fila["Historia del BEL"] = f"no se pudo usar el metodo del area: {motivo or 'sin meses con BEL por FND'}"
                out["estado_area"][(pref, str(r))] = fila["Historia del BEL"]
                out["sin_area"].append(f"{pref} {r}: {motivo or 'sin meses con BEL por FND'}")
                out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}",
                                       f"SAP registra BEL {f'{bel_u_bd:,.0f}' if np.isfinite(bel_u_bd) else 'vacio'} en "
                                       f"{ultimo} y la historia del metodo del area no alcanza ({motivo or 'sin meses con BEL por FND'}): "
                                       "el BEL proyectado queda con el modelo (0, sin formula)"))
            if usa_area and n_ap:
                out["estado_area"][(pref, str(r))] = "metodo del area"
                out["bel_area"][(pref, str(r))] = {"desde": per_ok[0] if per_ok else None, "hasta": ultimo,
                                              "meses": len(per_ok), "fuente": fila["Historia del BEL"]}
                hist_a = {}                                   # la historia que se uso, para el tablero
                for p in per_ok:
                    is_ = _hp_fuente(hp, resultados, r_hp, nombre_is, p, pos)[0]
                    pd_a = val("BEL", p) / is_
                    mr_a, irr_a, br_a = val("MR", p), val("IRR", p), val("BRUTO", p)
                    hist_a[p] = {"PND/PD": pd_a, "FD/FND": fnd_h[per_hist.index(p)],
                                 "FACTOR MR": mr_a / pd_a if np.isfinite(mr_a) and pd_a else math.nan,
                                 "CESION": irr_a / br_a if np.isfinite(irr_a) and np.isfinite(br_a) and br_a else math.nan}
                out["bel_area"][(pref, str(r))]["historia"] = hist_a
                out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}",
                                       f"SAP registra BEL {f'{bel_u_bd:,.0f}' if np.isfinite(bel_u_bd) else 'vacio'} en {ultimo}: "
                                       f"la historia del FND, del FACTOR MR y de la CESION ({len(per_ok)} meses, "
                                       f"{per_ok[0]} a {per_ok[-1]}) sale del {fila['Historia del BEL'].split(': SAP')[0]}; "
                                       f"el BEL proyectado es IS x PEACUMULADA x FND como en los demas ramos "
                                       f"(BEL_METODO_AREA)"))
            if con_fa and sin_fa and fnd_f is not None:
                out["alertas"].append(("DANOS", f"{pref} | BEL | ramo {r}",
                                       f"{len(sin_fa)} mes(es) sin IS de la funcion actuarial ({sin_fa[0]} a {sin_fa[-1]}): "
                                       "el BEL de esos meses usa el IS (RL)"))
            fila["Motivo"] = motivo if motivo else ("" if n_ap == h else
                                                    f"{h - n_ap} mes(es) sin IS, LAG o PE, o con BEL negativo (quedan "
                                                    "con el modelo)")
            for p in (periodos_proy[3] if len(periodos_proy) > 3 else periodos_proy[-1], periodos_proy[-1]):
                fila[f"BEL modelo {p}"] = proy.get((norm(f"{pref} BEL"), p, r), math.nan)
                fila[f"BEL por FND {p}"] = out["proy"].get((norm(f"{pref} BEL"), p, r), math.nan) \
                    if (pref, p, r) in out["aplica"] else math.nan
                fila[f"NETO por FND {p}"] = out["proy"].get((norm(f"{pref} NETO"), p, r), math.nan) \
                    if (pref, p, r) in out["aplica"] else math.nan
                fila[f"NETO con factores fijos en {ultimo} {p}"] = out["neto_fijo"].get((pref, p, r), math.nan)
            out["resumen"].append(fila)
    for pr_, r_ in sorted((set(CESION_OBJETIVO) | set(CESION_TENDENCIA)) - out["cesion_area"] if indicaciones_area else ()):
        out["alertas"].append(("DANOS", f"{pr_} | CESION | ramo {r_}",
                               "indicacion del area (CESION_OBJETIVO / CESION_TENDENCIA) sin aplicar: la serie no lleva BEL "
                               "por FND, el ramo no esta en la BD o no tiene al menos 3 meses reales de cesion; su cesion "
                               "sigue con el modelo aunque la nota de la columna CESION y el Resumen la mencionen"))
    n = len({(a, c) for a, _, c in out["aplica"]})
    out["estado"] = (f"{n} series (reserva x ramo) con BEL = IS x PEACUMULADA x FND desde {periodos_proy[0]}; "
                     f"{len(out['aplica'])} de {2 * len(bd.cols_ramo) * h} meses") if n else \
        "ninguna serie con PE, IS y LAG suficientes: el BEL sigue con el modelo"
    return out


def calcular_backtesting(bd: BDMontos, hp: HParam, pe: dict, is_fa_val: dict | None, ultimo: int) -> dict:
    """BACKTESTING: la proyeccion de Danos con la historia cortada en el mes anterior a BACKTESTING_DESDE (BD de montos y
    HParametros), para los meses BACKTESTING_DESDE a BACKTESTING_HASTA: las mismas series y modelos (correr_series), las
    mismas identidades (derivar_montos) y el mismo BEL por FND (calcular_bel_fnd, sin las indicaciones del area de la
    cesion), con la PE de la proyeccion y el IS (FA) donde el archivo lo trae. Regresa {"estado", "corte", "periodos",
    "proy": {(concepto, periodo, ramo): USD}, "indicadores": {(reserva, periodo, ramo): {bloque: valor}}, "aplica",
    "metodo": {(reserva, ramo): texto}, "alertas": [textos]}; "proy" vacio si no se calcula."""
    out = {"estado": "", "corte": None, "periodos": [], "proy": {}, "indicadores": {}, "aplica": set(), "metodo": {},
           "alertas": []}
    if not BACKTESTING:
        out["estado"] = "apagado (BACKTESTING = False)"
        return out
    desde, hasta = int(BACKTESTING_DESDE), int(BACKTESTING_HASTA)
    corte = _mes_menos(desde, 1)
    primero = min((p for (_, p) in bd.filas), default=None)
    if primero is None or hasta < desde or corte >= ultimo or corte < _mes_menos(primero, -MIN_MESES_FND):
        out["estado"] = (f"no se calcula: BACKTESTING_DESDE ({desde}) a BACKTESTING_HASTA ({hasta}) debe empezar despues de "
                         f"{MIN_MESES_FND} meses de historia y antes del ultimo mes real ({ultimo})")
        return out
    per = rango_periodos(desde, hasta)
    h = len(per)
    bd_bt = replace(bd, filas={k: v for k, v in bd.filas.items() if k[1] <= corte},
                    valores={k: v for k, v in bd.valores.items() if k[1] <= corte}, filas_prima={}, filas_backtest={})
    filas_hp = {k: r for k, r in hp.filas.items() if k[1] <= corte}
    if not filas_hp:
        out["estado"] = f"no se calcula: {HOJA_PARAMETROS} no trae renglones '{TIPO_INDICE_BASE}' hasta {corte}"
        return out
    u_hp = max(f for (_, f) in filas_hp)
    activos = sorted(((hp.ws.cell(f, hp.cols["Ramo"]).value, f) for (_, q), f in filas_hp.items() if q == u_hp),
                     key=lambda x: x[1]) or list(hp.ramos_activos)
    hp_bt = replace(hp, historia={k: {f: v for f, v in d.items() if f <= corte} for k, d in hp.historia.items()},
                    filas=filas_hp, ultimo=u_hp, lags_cero=[], ramos_activos=activos)
    tc_hist = leer_tc_real(bd_bt, corte, "DANOS") if MODELAR_EN_MXN.get("DANOS") else None
    series = (series_montos(bd_bt, "DANOS", ESTRUCTURA["DANOS"], corte, h, tc_hist)
              + series_hparametros(hp_bt, h, corte))
    print(f"   Backtesting: historia hasta {corte}, {len(series)} series, meses {per[0]} a {per[-1]} ...", flush=True)
    res = correr_series(series)
    ajustar_orden_indices(hp_bt, res, [])
    if FACTORES_BEL_FIJOS:
        fijar_margenes_modelo(res, h)
    proy = derivar_montos(bd_bt, "DANOS", ESTRUCTURA["DANOS"], res, per, en_mxn=tc_hist is not None)
    info = {"proy": proy, "aplica": set(), "series": [], "resumen": [], "estado": "sin BEL por FND"}
    if USAR_BEL_POR_FND:
        info_area, basura = {}, []
        try:
            bel_area = leer_bel_metodo_area(corte, basura, info_area)
        except Exception as e:  # noqa: BLE001
            bel_area = {}
            out["alertas"].append(f"no se pudo leer el BEL del metodo del area ({type(e).__name__}: {e})")
        info = calcular_bel_fnd(bd_bt, hp_bt, res, proy, pe, per, corte, is_fa_val, bel_area,
                                info_area.get("motivos"), indicaciones_area=False)
    validar(info["proy"], {})
    out.update({"corte": corte, "periodos": per, "proy": {k: v for k, v in info["proy"].items() if k[1] in per},
                "aplica": set(info.get("aplica") or ()), "estado_fnd": info.get("estado", "")})
    for f in info.get("resumen") or []:
        out["metodo"][(f["Reserva"], str(f["Ramo"]))] = (
            "BEL por FND" if f.get("Meses con BEL por FND") else f"modelo ({f.get('Motivo') or 'sin BEL por FND'})")
    # indicadores del mes como los bloques de la hoja (en valores): IS, PEACUMULADA, FND, PND/PD, factores y cesion
    pos = {p: i for i, p in enumerate(per)}
    serie = {(s["Reserva"], s["Periodo"], s["Ramo"]): s for s in info.get("series") or []}
    p12 = _suma_12(pe)
    for pref, (nombre_is, _) in INDICE_BASE_PND.items():
        anios = ANIOS_LAG_PEACUMULADA.get(pref, 0)
        for r in bd.cols_ramo:
            r_hp = MAPA_RAMO_LAG.get(str(r))
            for p in per:
                def m(c):
                    return out["proy"].get((norm(f"{pref} {c}"), p, r), math.nan)
                bel, mr, bruto, irr = m("BEL"), m("MR"), m("BRUTO"), m("IRR")
                gto = m("GTO") if pref == "RRC" else 0.0
                is_rl = _hp_fuente(hp_bt, res, r_hp, nombre_is, p, pos)[0]
                lags = {k: _hp_fuente(hp_bt, res, r_hp, f"LAG {k}", p, pos)[0] for k in range(1, max(1, anios) + 1)}
                s = serie.get((pref, p, r)) if (pref, p, r) in out["aplica"] else None
                is_u = float(s["IS"]) if s else is_rl
                pnd = bel / is_u if np.isfinite(bel) and np.isfinite(is_u) and is_u != 0 else math.nan
                peac = float(s["PEACUMULADA"]) if s else _peacumulada(pref, r, p, p12, lags)
                fnd = float(s["FND"]) if s else (pnd / peac if np.isfinite(pnd) and np.isfinite(peac) and peac else math.nan)
                pe_v = pe.get((r, p))
                fa = (is_fa_val or {}).get((pref, str(r), p))
                ok_pnd = np.isfinite(pnd) and pnd != 0
                out["indicadores"][(pref, p, r)] = {
                    "PND/PD": pnd,
                    "FA": pnd / p12[(r, p)] if np.isfinite(pnd) and p12.get((r, p)) else math.nan,
                    "FACTOR GTO": (gto / pnd if ok_pnd and np.isfinite(gto) else math.nan) if pref == "RRC"
                    else (0.0 if np.isfinite(pnd) else math.nan),
                    "FACTOR MR": mr / pnd if ok_pnd and np.isfinite(mr) else math.nan,
                    "CESION": irr / bruto if np.isfinite(irr) and np.isfinite(bruto) and bruto else
                    (0.0 if np.isfinite(bruto) else math.nan),
                    "IS (RL)": is_rl, "IS (FA)": float(fa) if fa is not None and np.isfinite(fa) else math.nan,
                    "LAG (RL)": lags.get(1, math.nan),
                    "PE FCST": float(pe_v[0]) if isinstance(pe_v, tuple) else (float(pe_v) if pe_v is not None else math.nan),
                    "PRIMA N AÑOS": p12.get((r, p), math.nan), "PEACUMULADA": peac, "FD/FND": fnd}
    n_fnd = len({(a, c) for a, _, c in out["aplica"]})
    out["estado"] = (f"historia hasta {corte}; {per[0]} a {per[-1]} ({h} meses); {n_fnd} series (reserva x ramo) con BEL por "
                     "FND; misma PE que la proyeccion; sin las indicaciones del area de la cesion ni el suavizado del "
                     "BEL (SUAVIZAR_BEL)" + ("; con FACTORES_BEL_FIJOS" if FACTORES_BEL_FIJOS else ""))
    return out


def comparar_backtesting(bt: dict, bd: BDMontos, proy_final: dict, ultimo: int, bel_area: dict | None = None) -> dict:
    """Backtesting contra lo real (meses hasta ultimo) y contra la proyeccion vigente (meses despues), por concepto, ramo y
    mes, con el total de ramos: {"mensual": [...], "resumen": [...]} para el diagnostico. En las series de BEL_METODO_AREA
    que SAP registra en cero (SONR 80), lo real es el del metodo del area (bel_area, Res_Rvas), de donde sale su BEL; el
    TOTAL suma los ramos con real comparable (MIN_REAL_BACKTESTING) y dice cuales deja fuera."""
    proy, per = bt.get("proy") or {}, bt.get("periodos") or []
    if not proy:
        return {"mensual": [], "resumen": []}
    conceptos = [c for c in bd.conceptos if any((c, p, r) in proy for p in per for r in bd.cols_ramo)]
    ramos = list(bd.cols_ramo)
    bel_area = bel_area or {}

    def referencia(c, p, x):
        """(valor, etiqueta) de la referencia del mes."""
        if p > ultimo:
            return proy_final.get((c, p, x), 0.0), "proyeccion vigente"
        pref, conc = (c.split(" ", 1) + [""])[:2]            # (RCONT no lleva concepto)
        a = bel_area.get((pref, str(x)))
        if a and p in (a.get("meses") or []) and abs(bd.valores.get((norm(f"{pref} BEL"), p, x), 0.0)) < UMBRAL_CERO_MONTOS:
            v = a["valores"]
            y = (v.get(("BRUTO", p), math.nan) - v.get(("IRR", p), math.nan)) if conc == "NETO" else v.get((conc, p), math.nan)
            if np.isfinite(y):
                return float(y), "real (metodo del area)"
        return bd.valores.get((c, p, x), 0.0), "real"

    mensual, resumen = [], []
    for c in conceptos:
        pref = c.split()[0]
        comparables, fuera = [], []
        for r in ramos + ["TOTAL"]:
            rs = (comparables or ramos) if r == "TOTAL" else [r]
            filas = []
            for p in per:
                b = sum(proy.get((c, p, x), 0.0) for x in rs)
                refs = [referencia(c, p, x) for x in rs]
                ref = sum(v for v, _ in refs)
                es_real = p <= ultimo
                etiquetas = sorted({e for _, e in refs})
                filas.append((p, b, ref, es_real))
                mensual.append({"Concepto": c, "Ramo": r, "Periodo": p, "Backtesting": b,
                                "Referencia": ref, "Referencia es": " y ".join(etiquetas),
                                "Diferencia": b - ref,
                                "Diferencia %": (b / ref - 1) if abs(ref) >= MIN_REAL_BACKTESTING else None})
            reales = [(b, ref) for _, b, ref, es in filas if es]
            den = sum(abs(ref) for _, ref in reales)
            comparable = bool(reales) and den >= MIN_REAL_BACKTESTING * len(reales)
            if r != "TOTAL":
                (comparables if comparable else fuera).append(r)
            fin = filas[-1]
            ult = next(((b, ref) for p, b, ref, es in filas if p == ultimo), None)
            resumen.append({
                "Concepto": c, "Ramo": r,
                "Como se proyecto": ("varios" if r == "TOTAL" else bt.get("metodo", {}).get((pref, r), "modelo")),
                "Meses reales comparados": len(reales),
                "Error % (suma |dif| / suma |real|)": (sum(abs(b - ref) for b, ref in reales) / den) if comparable else None,
                "Sesgo % (suma dif / suma |real|)": (sum(b - ref for b, ref in reales) / den) if comparable else None,
                f"Real {ultimo}": ult[1] if ult else None, f"Backtesting {ultimo}": ult[0] if ult else None,
                f"Dif % {ultimo}": (ult[0] / ult[1] - 1) if ult and abs(ult[1]) >= MIN_REAL_BACKTESTING else None,
                f"Proyeccion vigente {fin[0]}" if not fin[3] else f"Real {fin[0]}": fin[2],
                f"Backtesting {fin[0]}": fin[1],
                f"Dif % {fin[0]}": (fin[1] / fin[2] - 1) if abs(fin[2]) >= MIN_REAL_BACKTESTING else None,
                "Nota": "; ".join(x for x in (
                    (f"TOTAL sin los ramos {', '.join(fuera)} (real casi cero)" if r == "TOTAL" and fuera and comparables
                     else "" if comparable or not reales or r == "TOTAL" else
                     f"real menor a {MIN_REAL_BACKTESTING:,.0f} USD al mes en promedio: sin error % (SAP en cero o casi)"),
                    (("ramo " + ", ".join(x_ for x_ in rs if any(referencia(c, q, x_)[1] == "real (metodo del area)"
                                                                 for q in per if q <= ultimo))
                      + ": real del metodo del area (Res_Rvas), SAP lo registra en cero")
                     if any(referencia(c, q, x_)[1] == "real (metodo del area)" for x_ in rs for q in per if q <= ultimo)
                     else "")) if x)})
    return {"mensual": mensual, "resumen": resumen}


def escribir_backtesting(bd: BDMontos, bt: dict, cols_ind: dict | None, pe_tab: dict | None = None) -> int:
    """Renglones BACKTESTING al final de la hoja de montos: un bloque de meses por concepto (en el orden de los conceptos
    del ano), CONCEPTO "<BACKTESTING_ETIQUETA> <concepto>", el TC del mes, los montos del backtesting en valores, RVATOT y
    RVA_SEXC con su formula y los bloques de indicadores con los del backtesting en valores (N/A sin dato; el FA contra la
    PE del grupo, pe_tab, si la hoja la usa, como los demas renglones). Reutiliza los renglones que ya traia la BD de
    entrada (si no estaban al final) y vacia los que sobran. Regresa cuantos renglones escribio."""
    ws = bd.ws
    proy, per = bt.get("proy") or {}, bt.get("periodos") or []
    ultima_col = ws.max_column
    usadas = set()
    if proy and per:
        conceptos = [c for c in bd.conceptos if any((c, p, r) in proy for p in per for r in bd.cols_ramo)]
        anio_ref = per[0] // 100
        primera = {c: min((r for (cc, p), r in bd.filas.items() if cc == c and p // 100 == anio_ref), default=10 ** 9)
                   for c in conceptos}
        orden = sorted(conceptos, key=lambda c: primera[c])
        cols_bloque = set((cols_ind or {}).values())
        for col in range(1, ultima_col + 1):              # (bloques de una corrida anterior aunque hoy no se escriban)
            m = re.match(r"^(.*\S)\s+(\d+)$", str(ws.cell(3, col).value or "").strip())
            if m and not m.group(1).upper().startswith("RAM") and m.group(2) in bd.cols_ramo:
                cols_bloque.add(col)
        base = {bd.col_concepto, bd.col_periodo, bd.col_tc, *bd.cols_ramo.values()}
        fila_nueva = ws.max_row + 1
        for c in orden:
            pref = c.split()[0]
            for p in per:
                plantilla = bd.filas.get((c, p)) or _fila_plantilla(bd, c, p)
                r = bd.filas_backtest.get((c, p))
                if r is None:
                    r, fila_nueva = fila_nueva, fila_nueva + 1
                usadas.add(r)
                for col in range(1, ultima_col + 1):
                    src, dst = ws.cell(plantilla, col), ws.cell(r, col)
                    _copiar_estilo(src, dst)
                    if col in base:
                        continue
                    v = src.value
                    dst.value = (Translator(v, origin=src.coordinate).translate_formula(dst.coordinate)
                                 if col not in cols_bloque and isinstance(v, str) and v.startswith("=") else None)
                if ws.row_dimensions[plantilla].height:
                    ws.row_dimensions[r].height = ws.row_dimensions[plantilla].height
                ws.cell(r, bd.col_concepto).value = f"{BACKTESTING_ETIQUETA} {ws.cell(plantilla, bd.col_concepto).value}"
                ws.cell(r, bd.col_periodo).value = p
                ws.cell(r, bd.col_tc).value = (bt.get("tc") or {}).get(p) or tc_para_periodo(bd, p)
                for ramo, col in bd.cols_ramo.items():
                    v = proy.get((c, p, ramo))
                    ws.cell(r, col).value = float(v) if v is not None and np.isfinite(v) else None
                ind_mes = bt.get("indicadores") or {}
                for (ind, ramo), col in (cols_ind or {}).items():
                    x = (ind_mes.get((pref, p, ramo)) or {}).get(ind, math.nan)
                    if ind == "FA" and pe_tab:                   # (FA = PND/PD / PE del grupo, como la hoja)
                        g = primas.GRUPO_DE_RAMO_RESERVA.get(str(ramo)) if primas is not None else None
                        pe_g = pe_tab.get(g)
                        pe_g = float(pe_g.get(p, math.nan)) if pe_g is not None else math.nan
                        pnd = (ind_mes.get((pref, p, ramo)) or {}).get("PND/PD", math.nan)
                        x = pnd / pe_g if np.isfinite(pnd) and np.isfinite(pe_g) and pe_g else math.nan
                    ws.cell(r, col).value = float(x) if isinstance(x, (int, float)) and np.isfinite(x) else TEXTO_SIN_DATO
                bd.filas_backtest[(c, p)] = r
    for k, r in list(bd.filas_backtest.items()):          # renglones de una corrida anterior que ya no van: se vacian
        if r not in usadas:
            for col in range(1, ultima_col + 1):
                ws.cell(r, col).value = None
            del bd.filas_backtest[k]
    if ws.auto_filter and ws.auto_filter.ref:
        ini, fin = ws.auto_filter.ref.split(":")
        ws.auto_filter.ref = f"{ini}:{re.match(r'[A-Z]+', fin).group()}{ws.max_row}"
    return len(usadas)


# =============================================================================
# RFV POR PRIMA (FIANZAS): RFV BRUTO = PRIMA 24M x FRV / TC; IRR = BRUTO x CESION; NETO = BRUTO - IRR
# =============================================================================
BLOQUES_RFV = ("PT", "PRIMA", "FRV", "CESION")     # bloques de la BD de RFV, en este orden (claves internas)
BLOQUES_RFV_FACTORES = ("PT", "PRIMA", "RCP", "SEG", "PCOM", "PCARGAS", "FPR", "PR", "PGA", "GA", "MA", "OMEGA", "ALFA",
                        "RMA", "FMA", "FV", "FRV", "PD", "FCR", "RC", "CESION")   # con FACTORES_RFV: los del area
FORMATO_BLOQUES_RFV = {"PT": "#,##0", "PRIMA": "#,##0", "FRV": "0.0000", "CESION": "0.00%", "SEG": "0.00%",
                       "PCOM": "0.00%", "PCARGAS": "0.00%", "FPR": "0.00%", "PR": "#,##0", "PGA": "0.00%", "GA": "#,##0",
                       "FV": "0.0000", "RCP": "0.00%", "PD": "0.000%", "FCR": "0.000%", "RC": "0.00%", "MA": "#,##0",
                       "OMEGA": "0.00%", "ALFA": "0.00%", "RMA": "#,##0", "FMA": "0.00"}
assert set(BLOQUES_RFV_FACTORES) <= set(FORMATO_BLOQUES_RFV), "bloque de la RFV sin formato"


def bloques_rfv() -> tuple:
    """Bloques de la BD de RFV que se escriben (con FACTORES_RFV, los de la metodologia del area)."""
    return BLOQUES_RFV_FACTORES if FACTORES_RFV else BLOQUES_RFV


def nombre_bloque_rfv(clave: str) -> str:
    """Encabezado del bloque (sin el ramo): PT, PRIMA 24M, RC PRIMA, %SEG PR, %COM PR, %CARGAS, FPR, PR 24M, %GA,
    GA 24M, MA, OMEGA, ALFA, RFV MA, FACTOR MA, FV, FRV, PD, FCR, RC, CESION."""
    n = MESES_PRIMA_RFV
    return {"PRIMA": f"PRIMA {n}M", "SEG": "%SEG PR", "PCOM": "%COM PR", "PCARGAS": "%CARGAS", "PR": f"PR {n}M",
            "PGA": "%GA", "GA": f"GA {n}M", "RCP": "RC PRIMA", "RMA": "RFV MA", "FMA": "FACTOR MA"}.get(clave, clave)


def _tc_cercano(tc: dict, p: int) -> float:
    """TC del mes; sin el, el del ultimo mes anterior con TC o, antes del primero, el primero."""
    if p in tc:
        return tc[p]
    antes = [q for q in tc if q < p]
    return tc[max(antes)] if antes else tc[min(tc)]


def pt_fianzas(pe_ramo: dict | None, pe_rfa: dict | None, pef: dict | None, bd: BDMontos, tc: dict,
               periodos_proy: list[int]) -> dict:
    """Prima tomada del mes por ramo de la BD de RFV, en MXN (la RFV se modela en pesos), para la RFV por prima:
    1) PExRamo (los ramos de Fianzas, que no estan en la BD de Danos) en todos sus meses; desde el primer mes de Fianzas
       en la base, un mes sin renglones de un ramo es prima 0 (la base omite los meses sin movimiento);
    2) despues de PExRamo y hasta el mes anterior al FCST, el reforecast por mes (RCST_FA: RAMO_RFCST_FIANZAS trae toda la
       prima de Fianzas) repartido entre los ramos con la mezcla de PExRamo de los ultimos 12 meses y, con
       PERFIL_REFORECAST = "FCST", llevado a la forma mensual de los mismos meses del FCST del ano siguiente (como en Danos);
    3) el FCST (CtaMens, cuenta CUENTA_PE_FCST, Ramo2 de RAMO_FCST_FIANZAS, en USD) por el TC del mes del proyecto.
    En un mes que traigan varias fuentes manda la primera (real, reforecast, FCST). tc: TC por mes (para PExRamo si
    viniera en USD). La prima cedida del mes (PC, para RC PRIMA) sale de PmaCed de PExRamo y de la columna CEDIDA de la
    cuenta de prima del FCST; el reforecast no trae la cesion de Fianzas (sus razones por RAMO 130 son las de toda la
    compania), asi que esos meses van sin cedida. Regresa {"mensual": {(ramo, periodo): MXN}, "fuente": {periodo:
    texto}, "cedida": {(ramo, periodo): MXN}, "texto", "texto_cedida", "referencia": {"fcst": {ramo: {"cesion",
    "comisiones", "seg_pr", "com_pr"}}}, "avisos"}."""
    ramos = list(bd.cols_ramo)
    out = {"mensual": {}, "fuente": {}, "cedida": {}, "texto": "", "texto_cedida": "", "referencia": {}, "avisos": []}
    partes = []
    hist = {}
    for (r, p), v in ((pe_ramo or {}).get("fuera_mensual") or {}).items():
        if r in ramos and np.isfinite(v):
            hist[(r, p)] = float(v) if MONEDA_PE_RAMO == "MXN" else float(v) * _tc_cercano(tc, p)
    if not hist:
        out["texto"] = ("PExRamo no trae prima de los ramos de Fianzas " + ", ".join(ramos)
                        + (" (no se leyo la base)" if not pe_ramo else ""))
        out["avisos"].append(out["texto"] + ": sin historia de prima, la RFV sigue con el modelo")
        return out
    p0, p1 = min(p for _, p in hist), max(p for _, p in hist)
    for p in rango_periodos(p0, p1):
        for r in ramos:
            hist.setdefault((r, p), 0.0)
        out["fuente"][p] = pe_ramo["ruta"].name
    out["mensual"].update(hist)
    ultimo = _mes_menos(periodos_proy[0], 1)
    con_prima = [r for r in ramos if any(hist.get((r, q)) for q in rango_periodos(p0, p1))]
    partes.append(f"{p0} a {p1}: {pe_ramo['ruta'].name} (PmaTom en {MONEDA_PE_RAMO}; ramos con prima: "
                  f"{', '.join(con_prima)})")
    fcst = {}
    for (r2, p), v in ((pef or {}).get("fuera_mensual") or {}).items():
        r = RAMO_FCST_FIANZAS.get(str(r2))
        if r in ramos and np.isfinite(v):
            fcst[(r, p)] = fcst.get((r, p), 0.0) + float(v)
    per_fcst = sorted({p for _, p in fcst})
    desde = _mes_menos(p1, -1)
    hasta = _mes_menos(per_fcst[0], 1) if per_fcst else periodos_proy[-1]
    if pe_rfa and desde <= hasta:
        tcs, tot = pe_rfa.get("tc_usado") or {}, {}
        for (r, p), v in (pe_rfa.get("fuera") or {}).items():
            if str(r) == RAMO_RFCST_FIANZAS and desde <= p <= hasta:
                t = tcs.get(p) if MONEDA_PE_RFCST_FA == "MXN" and tcs.get(p) else tc_para_periodo(bd, p)
                tot[p] = tot.get(p, 0.0) + float(v) * t        # (MXN del archivo, o USD por el TC del proyecto)
        if tot:
            meses = sorted(tot)
            w = _mezcla(hist, ramos)
            fa = {(r, p): tot[p] * w[r] for p in meses for r in ramos}
            perfilados = []
            if PERFIL_REFORECAST == "FCST" and fcst:
                fa, perfilados = perfilar_reforecast(fa, meses, fcst, {})
            out["mensual"].update(fa)
            for p in meses:
                out["fuente"][p] = (f"{pe_rfa['ruta'].name} (RAMO {RAMO_RFCST_FIANZAS} repartido con la mezcla de "
                                    "PExRamo" + ("; forma mensual del FCST" if perfilados else "") + ")")
            partes.append(f"{meses[0]} a {meses[-1]}: {pe_rfa['ruta'].name} › {pe_rfa.get('hoja', '')}, RAMO "
                          f"{RAMO_RFCST_FIANZAS} ({sum(tot.values()) / 1e6:,.1f} M MXN; "
                          + ", ".join(f"{p} {tot[p] / 1e6:,.1f}" for p in meses)
                          + ") repartido con la mezcla de PExRamo de los ultimos 12 meses ("
                          + ", ".join(f"{r}: {w[r]:.1%}" for r in ramos if w[r]) + ")"
                          + (f"; total de esos meses de cada ramo con la forma mensual de los mismos meses del FCST "
                             f"(ramos {', '.join(perfilados)})" if perfilados else ""))
    for p in per_fcst:
        if p in out["fuente"]:
            continue
        t = tc_para_periodo(bd, p)
        for r in ramos:
            out["mensual"][(r, p)] = fcst.get((r, p), 0.0) * t
        out["fuente"][p] = f"{pef['ruta'].name} (CtaMens, cuenta {CUENTA_PE_FCST}, USD x TC del proyecto)"
    if per_fcst:
        tot_f = {r: sum(v for (x, q), v in fcst.items() if x == r) for r in ramos}
        partes.append(f"{per_fcst[0]} a {per_fcst[-1]}: {pef['ruta'].name} › CtaMens, cuenta {CUENTA_PE_FCST}, Ramo2 "
                      + ", ".join(f"{r} ({v / 1e6:,.1f} M USD)" for r, v in tot_f.items() if v)
                      + ", por el TC del mes del proyecto")
    if p1 < ultimo:                                    # PExRamo no llega al ultimo mes real
        hueco = rango_periodos(_mes_menos(p1, -1), ultimo)
        con = [p for p in hueco if p in out["fuente"]]
        out["avisos"].append(f"PExRamo trae la prima de Fianzas hasta {p1} y el ultimo mes real es {ultimo}: "
                             + (f"{', '.join(map(str, con))} toman el reforecast o el FCST" if con else
                                "ningun mes de ese hueco tiene otra fuente")
                             + (f"; {', '.join(str(p) for p in hueco if p not in con)} quedan sin prima" if len(con) < len(hueco)
                                else "") + "; actualiza PExRamo")
    falta = [p for p in rango_periodos(p0, periodos_proy[-1]) if p not in out["fuente"]]
    if falta:
        out["avisos"].append(f"{len(falta)} mes(es) sin prima de Fianzas en ninguna fuente ({falta[0]} a {falta[-1]}): "
                             f"van en 0 en {HOJA_PT_RAMO} y la RFV de los meses cuya PRIMA {MESES_PRIMA_RFV}M los incluye "
                             "sigue con el modelo")
    out["texto"] = "; ".join(partes)
    # prima cedida del mes (RC PRIMA): PmaCed de PExRamo y la columna CEDIDA del FCST (el reforecast no la trae)
    ced = {(r, p): float(v) if MONEDA_PE_RAMO == "MXN" else float(v) * _tc_cercano(tc, p)
           for (r, p), v in ((pe_ramo or {}).get("fuera_cedida_mensual") or {}).items() if r in ramos and np.isfinite(v)}
    if ced:
        partes_c = [f"{p0} a {p1}: PmaCed de {pe_ramo['ruta'].name}"]
        for p in rango_periodos(p0, p1):
            for r in ramos:
                ced.setdefault((r, p), 0.0)
        ced_f = {}
        for (r2, p), v in ((pef or {}).get("fuera_cedida_mensual") or {}).items():
            r = RAMO_FCST_FIANZAS.get(str(r2))
            if r in ramos and np.isfinite(v):
                ced_f[(r, p)] = ced_f.get((r, p), 0.0) + float(v)
        meses_f = [p for p in per_fcst if str(out["fuente"].get(p, "")).startswith(pef["ruta"].name)] if pef else []
        if meses_f and ced_f:
            for p in meses_f:
                t = tc_para_periodo(bd, p)
                for r in ramos:
                    ced[(r, p)] = ced_f.get((r, p), 0.0) * t
            partes_c.append(f"{meses_f[0]} a {meses_f[-1]}: columna CEDIDA de la cuenta {CUENTA_PE_FCST} del FCST "
                            "(USD x TC del proyecto)")
        out["cedida"] = ced
        out["inicio"] = p0
        out["texto_cedida"] = "; ".join(partes_c)
    com_f = {}
    for (r2, p), v in ((pef or {}).get("fuera_com_mensual") or {}).items():
        r = RAMO_FCST_FIANZAS.get(str(r2))
        if r in ramos and np.isfinite(v):
            com_f[r] = com_f.get(r, 0.0) + float(v)
    pt_f = {r: sum(v for (x, q), v in fcst.items() if x == r) for r in ramos}
    ced_t = {r: sum(v for (x, q), v in ced_f.items() if x == r) for r in ramos} if ced else {}
    seg = (pef or {}).get("fuera_seg") or {}
    seg_r = {r: {(g_, k): sum(v for (r2, sg, kk), v in seg.items() if RAMO_FCST_FIANZAS.get(str(r2)) == r and sg == g_
                              and kk == k) for g_, k in (("PR", "prima"), ("MA", "prima"), ("PR", "com"))} for r in ramos}
    out["referencia"]["fcst"] = {r: {"comisiones": com_f.get(r, math.nan) / pt_f[r] if pt_f.get(r) else math.nan,
                                     "cesion": ced_t.get(r, math.nan) / pt_f[r] if pt_f.get(r) else math.nan,
                                     "seg_pr": (seg_r[r][("PR", "prima")] / (seg_r[r][("PR", "prima")]
                                                                             + seg_r[r][("MA", "prima")])
                                                if seg and seg_r[r][("PR", "prima")] + seg_r[r][("MA", "prima")] else math.nan),
                                     "com_pr": (seg_r[r][("PR", "com")] / seg_r[r][("PR", "prima")]
                                                if seg and seg_r[r][("PR", "prima")] else math.nan)}
                                 for r in ramos}
    return out


def _rc_prima(pt: dict | None, r, p: int) -> float:
    """RC PRIMA del ramo al mes p: prima cedida / prima tomada desde el primer mes de PExRamo (la ventana larga, la mas
    cercana a los anos de vigencia de los contratos con que el area pondera la cesion de cada uno) hasta p; nan si falta
    la cedida de algun mes (p. ej. los del reforecast) o si la prima es 0."""
    if not pt or not pt.get("cedida") or not pt.get("inicio") or p < pt["inicio"]:
        return math.nan
    qs = rango_periodos(pt["inicio"], p)
    if not all(q in pt["fuente"] and (r, q) in pt["cedida"] for q in qs):
        return math.nan
    s_ = sum(pt["mensual"].get((r, q), 0.0) for q in qs)
    return float(sum(pt["cedida"][(r, q)] for q in qs) / s_) if s_ > 0 else math.nan


def _texto_factores_rfv(info: dict) -> str:
    """Linea del Resumen con los factores de la metodologia del area en la RFV (FACTORES_RFV)."""
    if not FACTORES_RFV:
        return "no (FACTORES_RFV = False)"
    fac = info.get("factores") or {}
    if not fac or not info.get("aplica"):
        return "sin RFV por prima: no se separan"
    com = info.get("com") or {}
    ult = (info.get("pdinfo") or {}).get("ultimo") or {}
    primer_fv = {}
    for (p, r), v in sorted((info.get("fv") or {}).items()):
        if r not in primer_fv and np.isfinite(v):
            primer_fv[r] = (p, v)
    split = sorted(info.get("split") or (), key=int)
    return ("RFV BRUTO = PRIMA 24M x FPR x (1 + %GA) x FV / TC"
            + (f" (en {', '.join(split)}, mas RFV MA / TC, con RFV MA = MA x (omega + alfa_k))" if split else "")
            + ", FPR = %SEG PR x (1 - %COM PR - %CARGAS); IRR = RFV BRUTO x RC x FCR, FCR = 1 - PD. Se proyectan FV (factor residual: permanencia, "
            + ("facultativo, cedentes sin MA y TC en " + ", ".join(split) + "; en los demas tambien la reserva por monto "
               "afianzado" if split else "reserva por monto afianzado y TC")
            + ") y RC con los modelos del FRV y de la cesion. %SEG PR y %COM PR (segmento de prima de reserva: "
            "extranjero proporcional y no proporcional): "
            + (com.get("texto") or "sin dato")
            + (f"; proyeccion con COMISION_RFV {indicaciones_rfv()[0]}" if indicaciones_rfv()[0] else
               "; fijos en la proyeccion")
            + f"; %CARGAS {CARGAS_RFV:.2%} (con %GA {GASTO_ADMON_RFV:.2%} incluido) y %GA {GASTO_ADMON_RFV:.2%} "
            "(parametros del area); PD: "
            + (", ".join(f"{r}: {v:.3%} ({p})" for r, (p, v) in ult.items()) + " (CASTIGO / (IRR + CASTIGO) de "
               "Res_Rvas, ultimo mes medido; fija despues)" if ult else "sin dato (FCR = 1 y RC = CESION)")
            + (f"; PD_FIANZAS en la proyeccion {indicaciones_rfv()[1]}" if indicaciones_rfv()[1] else "")
            + "; RC PRIMA (prima cedida / prima tomada desde 2019) es informativa. Por ramo: "
            + "; ".join(f"{r}: %SEG PR {f['SEG']:.1%}, FPR {f['FPR']:.2%}"
                        + (f", FV {primer_fv[r][1]:.2f} ({primer_fv[r][0]})" if r in primer_fv else "")
                        for r, f in fac.items() if np.isfinite(f["FPR"])))


def _texto_insumos_fianzas(info: dict) -> str:
    """Linea del Resumen con los insumos del area de Fianzas: monto afianzado, PD de referencia, comision sobre
    utilidades, cobertura del CSV y FACTOR MA."""
    if not FACTORES_RFV:
        return "no (FACTORES_RFV = False)"
    if not MA_RFV:
        return "no (MA_RFV = False)"
    ma_info = info.get("ma_info") or {}
    if not ma_info.get("ma"):
        return (ma_info.get("texto") or f"sin {PATRON_MONTOS_AFIANZADOS} en entradas/") + \
            ": la reserva por monto afianzado queda dentro de FV"
    ins = info.get("insumos") or []
    ult = max((f["Periodo"] for f in ins if f["Real o proyeccion"] == "real"), default=None)
    partes = [f"Monto afianzado: {ma_info.get('texto')}; RFV MA = MA x (omega + alfa_k) a {ult}: " + ", ".join(
        f"{f['Ramo']}: {f['RFV MA = MA x (OMEGA + ALFA) (MXN)'] / 1e6:,.1f} M MXN ({f['RFV MA / RFV BRUTO']:.0%} de la "
        "RFV)" for f in ins if f["Periodo"] == ult and np.isfinite(f["RFV MA / RFV BRUTO"]))
        + (f"; aparte en {', '.join(sorted(info.get('split') or (), key=int))} (FRV = FRV residual + RFV MA / PRIMA "
           f"{MESES_PRIMA_RFV}M); en los demas, informativa" if info.get("split") else "; informativa en todos los ramos")
        + f"; despues de {ma_info.get('ultimo')} el MA queda fijo en ese mes (ningun insumo trae MA posterior)"]
    if info.get("texto_pdx"):
        partes.append("PD de referencia: " + info["texto_pdx"] + "; no entra a la IRR (la PD sigue siendo la del castigo "
                      "de Res_Rvas; la de xDefault pondera por prima cedida, no por la reserva cedida vigente)")
    if info.get("texto_csu"):
        partes.append("Comision sobre utilidades: " + info["texto_csu"] + "; no entra al FPR")
    cob = [c for c in info.get("cobertura") or [] if c.get("% sin MA", 0) > 0]
    if cob:
        partes.append("Proporcional de Mexico sin MA en el CSV: " + "; ".join(
            f"{c['Ramo']}: {c['% sin MA']:.0%} de su prima ({c['Cedentes sin MA']})" for c in cob))
    partes.append("FACTOR MA: " + ", ".join(f"{r}: {v}" for r, v in FACTOR_MA_FIANZAS.items())
                  + " (constante del area, fija como esta; no entra a ningun calculo)")
    return ". ".join(partes)


def _agregar_seg_fianzas(ruta: Path):
    """Prima tomada y comisiones de Fianzas (ramos 130 a 199) en MXN de la base del real por contrato (hoja BD:
    PrimasNal y ComisionesNal), por periodo, ramo, segmento, Tipo Rea, Terr, compania y llave del contrato del area
    (TipoRea|Corredor|Compania|Num Contrato|Ano Susc., la de xVigMaxProp y xComUtil; vacia si la base no trae esas
    columnas). Segmento "PR" (prima de reserva: Tipo Rea 1 fuera de Mexico, Terr distinto de 1, o Tipo Rea 2) y "MA"
    (monto afianzado: proporcional de Mexico y facultativo). Regresa (tabla, renglones leidos, renglones fisicos)."""
    cols = {"periodo": ("Periodo",), "ramo": ("Ramo2", "Ramo"), "tipo": ("Tipo Rea",), "terr": ("Terr",),
            "prima": ("PrimasNal",), "com": ("ComisionesNal",)}
    llave = {"corr": ("Corredor",), "cia": ("Compañía", "Compania"), "cto": ("Num Contrato",),
             "susc": ("Año Susc.", "Ano Susc.", "Año Susc")}
    df, leidos, fisicos = primas._leer_columnas(ruta, "BD", ("Periodo", "PrimasNal"), {**cols, **llave})
    if any(c not in df for c in cols):
        return None, leidos, fisicos
    t = pd.DataFrame({"periodo": pd.to_numeric(df["periodo"], errors="coerce"),
                      "ramo": pd.to_numeric(df["ramo"], errors="coerce"),
                      "tipo": pd.to_numeric(df["tipo"], errors="coerce"),
                      "terr": pd.to_numeric(df["terr"], errors="coerce"),
                      "prima": pd.to_numeric(df["prima"], errors="coerce").fillna(0.0),
                      "com": pd.to_numeric(df["com"], errors="coerce").fillna(0.0)})

    def entero(c):
        x = pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(np.nan, index=df.index)
        return x.map(lambda v: str(int(v)) if np.isfinite(v) else "")
    partes = [entero("tipo")] + [entero(c) for c in llave]
    t["cia"] = entero("cia")
    t["llave"] = partes[0].str.cat(partes[1:], sep="|") if all(c in df for c in llave) else ""
    t = t[t["periodo"].between(190001, 299912) & t["ramo"].between(130, 199)].copy()
    t["seg"] = np.where(((t["tipo"] == 1) & (t["terr"] != 1)) | (t["tipo"] == 2), "PR", "MA")
    t["periodo"], t["ramo"] = t["periodo"].astype(int), t["ramo"].astype(int).astype(str)
    t["tipo"], t["terr"] = t["tipo"].fillna(-1).astype(int), t["terr"].fillna(-1).astype(int)
    return (t.groupby(["periodo", "ramo", "seg", "tipo", "terr", "cia", "llave"], as_index=False)
            .agg(prima=("prima", "sum"), com=("com", "sum"), n=("prima", "size")), leidos, fisicos)


def segmento_pr_fianzas(ramos: list, ultimo: int) -> dict:
    """Segmento de prima de reserva de Fianzas por ramo, de la base del real por contrato (BD_Real*.xlsx y BDReal{aa}
    del ano y del anterior; de cada patron, el archivo mas grande que no este recortado, y el mas reciente manda en sus
    meses), en los meses hasta ultimo: %SEG PR = prima tomada del segmento PR / prima tomada del ramo y %COM PR =
    comisiones / prima tomada del segmento PR (MXN). Hoy solo BDReal26 trae Fianzas (BD_Real viene recortada y sin
    renglones de Fianzas). Regresa {"seg_pr": {ramo: razon}, "pcom": {ramo: %COM PR}, "pcom_ramo": {ramo: %COM del
    ramo}, "mensual": {(ramo, periodo): {"seg_pr", "pcom"}}, "meses": [periodos], "contratos": tabla por periodo, ramo,
    segmento, Tipo Rea, Terr, compania y llave del contrato (para la comision sobre utilidades y la cobertura del monto
    afianzado), "renglones": renglones leidos, "texto", "avisos"}."""
    out = {"seg_pr": {}, "pcom": {}, "pcom_ramo": {}, "mensual": {}, "meses": [], "texto": "", "avisos": [],
           "contratos": None, "renglones": 0}
    if primas is None:
        out["texto"] = "sin primas.py: no se lee la base del real"
        return out
    a = ultimo // 100
    patrones = [primas.PATRON_REAL_HIST.format(aa=f"{a % 100:02d}", aaaa=str(a), sig=str(a + 1))]
    patrones += [primas.PATRON_REAL_ANIO.format(aa=f"{x % 100:02d}", aaaa=str(x), sig=str(x + 1)) for x in (a - 1, a)]
    datos, usados = {}, []
    for patron in patrones:                            # (los posteriores mandan en sus meses)
        for ruta in primas._buscar(patron):
            try:
                (t, leidos, fisicos), _ = primas._con_cache(ruta, "fz_seg", _agregar_seg_fianzas)
            except Exception as e:  # noqa: BLE001
                out["avisos"].append(f"{ruta.name}: no se pudo leer para el segmento de Fianzas ({type(e).__name__})")
                continue
            if leidos in primas.LIMITES_TRUNCADO or fisicos in primas.LIMITES_TRUNCADO:
                continue                               # (recortado: el siguiente del patron)
            if t is None:
                break
            t = t[t["ramo"].isin([str(r) for r in ramos]) & (t["periodo"] <= ultimo)]
            if len(t):
                meses_t = {int(x) for x in t["periodo"]}
                datos = {k: v for k, v in datos.items() if k[0] not in meses_t}
                for f in t.itertuples(index=False):
                    k = (int(f.periodo), str(f.ramo), f.seg, int(getattr(f, "tipo", -1)), int(getattr(f, "terr", -1)),
                         str(getattr(f, "cia", "")), str(getattr(f, "llave", "")))
                    v0 = datos.get(k, (0.0, 0.0, 0))
                    datos[k] = (v0[0] + float(f.prima), v0[1] + float(f.com), v0[2] + int(getattr(f, "n", 1)))
                out["renglones"] += int(leidos)
                usados.append(f"{ruta.name} ({min(meses_t)} a {max(meses_t)})")
            break
    meses = sorted({k[0] for k in datos})
    out["contratos"] = pd.DataFrame([{"periodo": k[0], "ramo": k[1], "seg": k[2], "tipo": k[3], "terr": k[4],
                                      "cia": k[5], "llave": k[6], "prima": v[0], "com": v[1], "n": v[2]}
                                     for k, v in datos.items()])
    for r in ramos:
        def suma(seg, k, ps=meses, _r=str(r)):
            return sum(v[k] for (p, x, g, *_), v in datos.items() if x == _r and (seg is None or g == seg) and p in ps)
        pt_r, pt_pr = suma(None, 0), suma("PR", 0)
        if pt_r > 0:
            out["seg_pr"][str(r)] = pt_pr / pt_r
            out["pcom_ramo"][str(r)] = suma(None, 1) / pt_r
            if pt_pr > 0:
                out["pcom"][str(r)] = suma("PR", 1) / pt_pr
        for p in meses:
            t_, tp_ = suma(None, 0, [p]), suma("PR", 0, [p])
            out["mensual"][(str(r), p)] = {"seg_pr": tp_ / t_ if t_ else math.nan,
                                          "pcom": suma("PR", 1, [p]) / tp_ if tp_ else math.nan}
    out["meses"] = meses
    out["texto"] = (f"{', '.join(usados)}: " + "; ".join(
        f"{r}: %SEG PR {out['seg_pr'][r]:.1%}, %COM PR {out['pcom'].get(r, math.nan):.1%} (del ramo "
        f"{out['pcom_ramo'][r]:.1%})" for r in out["seg_pr"])) if out["seg_pr"] else \
        "ninguna base del real trae la prima y las comisiones de Fianzas"
    if not out["seg_pr"]:
        out["avisos"].append("SIN COMISIONES DE FIANZAS: ninguna base del real (BD_Real, BDReal del ano o del anterior) "
                             "trae Fianzas; %SEG PR, %COM PR, FPR y FV van en N/A")
    return out


def leer_fianzas_area(ramos: list, ultimo: int) -> dict:
    """Calculo del area de la RFV de Fianzas por ramo y mes: hoja Base FIANZAS de los Res_Rvas de entradas/ (Reserva
    FIANZAS, escenarios ESCENARIOS_FIANZAS_AREA en orden de preferencia por mes; el ultimo archivo gana), con PRIMA (de
    los contratos vigentes), RVABRUTA, IRR, CASTIGO, RVACONT y RVNETA en MXN, hasta ultimo. Regresa {(ramo, periodo):
    {tipo: monto}} (vacio sin archivos o sin la hoja)."""
    out, escogido = {}, {}
    for ruta in archivos_res_rvas():
        try:
            wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
            if "Base FIANZAS" not in wb.sheetnames:
                wb.close()
                continue
            filas = list(wb["Base FIANZAS"].iter_rows(values_only=True))
            wb.close()
        except Exception:  # noqa: BLE001
            continue
        i_enc = next((i for i, f in enumerate(filas[:20]) if f and "Tipo Monto" in f and "Periodo" in f), None)
        if i_enc is None:
            continue
        enc = list(filas[i_enc])
        j = {n: enc.index(n) for n in ("Reserva", "Escenario", "Tipo Monto", "Ramo", "Periodo", "Monto") if n in enc}
        if len(j) < 6:
            continue
        for f in filas[i_enc + 1:]:
            if not f or norm(f[j["Reserva"]]) != "FIANZAS":
                continue
            esc, r, per, v = (a_numero(f[j[k]])[0] for k in ("Escenario", "Ramo", "Periodo", "Monto"))
            if not (np.isfinite(esc) and np.isfinite(r) and np.isfinite(per)) or int(esc) not in ESCENARIOS_FIANZAS_AREA \
                    or str(int(r)) not in ramos or int(per) > ultimo:
                continue
            k = (str(int(r)), int(per))
            pref = ESCENARIOS_FIANZAS_AREA.index(int(esc))
            if k in escogido and escogido[k] < pref:
                continue
            if escogido.get(k) != pref:
                out[k], escogido[k] = {}, pref
            out[k][norm(f[j["Tipo Monto"]])] = float(v) if np.isfinite(v) else 0.0
    return out


def _rangos_meses(periodos) -> str:
    """Meses como rangos: 202412 a 202510, 202602, 202604 a 202606."""
    ps = sorted(set(periodos))
    if not ps:
        return "-"
    tramos, ini, ant = [], ps[0], ps[0]
    for p in ps[1:] + [None]:
        if p is not None and periodo_a_indice(p) == periodo_a_indice(ant) + 1:
            ant = p
            continue
        tramos.append(str(ini) if ini == ant else f"{ini} a {ant}")
        if p is not None:
            ini = ant = p
    return ", ".join(tramos)


def _csv_entrada(patron: str):
    """El CSV mas reciente de entradas/ cuyo nombre completo cumple el patron (sin distinguir mayusculas; sin los
    temporales ~$): "MontosAfianzados*.csv" no toma "Proy_MontosAfianzados.csv"."""
    if not ENTRADAS.exists():
        return None
    c = [x for x in ENTRADAS.iterdir() if x.is_file() and not x.name.startswith("~$")
         and fnmatch.fnmatch(x.name.lower(), patron.lower())]
    return max(c, key=lambda x: x.stat().st_mtime) if c else None


def _leer_csv_area(ruta) -> pd.DataFrame:
    """CSV de los insumos del area (separador detectado; UTF-8 con o sin BOM, o latin-1), todo como texto y con los
    encabezados sin espacios de mas."""
    ultimo_error = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(ruta, sep=None, engine="python", encoding=enc, dtype=str, keep_default_na=False)
            break
        except UnicodeDecodeError as e:
            ultimo_error = e
    else:
        raise ultimo_error
    df.columns = [str(c).replace("﻿", "").strip() for c in df.columns]
    return df


def _col_csv(df: pd.DataFrame, *nombres):
    """La columna de df con alguno de los nombres (sin distinguir mayusculas ni espacios), o None."""
    enc = {norm(c): c for c in df.columns}
    return next((enc[norm(n)] for n in nombres if norm(n) in enc), None)


def _num_csv(s: pd.Series) -> pd.Series:
    """Numeros de un CSV (texto vacio = sin dato)."""
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False).str.strip().replace("", np.nan),
                         errors="coerce")


def _texto_ramo(v) -> str:
    return str(int(v)) if isinstance(v, (int, float)) and np.isfinite(v) else ""


def leer_montos_afianzados(ramos: list) -> dict:
    """Monto afianzado (MA) del segmento nacional proporcional por ramo y mes, en MXN, del CSV del area
    (PATRON_MONTOS_AFIANZADOS en entradas/): suma de "Monto Afianzado Tot" de todas las cedentes, con su Escenario (Real
    o Estimado del area; un mes con algun renglon Estimado cuenta como Estimado). Un ramo-mes sin dato o en 0 no lleva
    MA. Revisa la calidad: renglones negativos, meses que repiten al anterior y el salto del ultimo real al primer
    estimado. Regresa {"ma": {(ramo, periodo): MXN}, "escenario": {(ramo, periodo): "Real" | "Estimado"}, "claves":
    {ramo: claves de cedente}, "ruta", "renglones", "usados", "ultimo", "texto", "avisos"}."""
    ruta = _csv_entrada(PATRON_MONTOS_AFIANZADOS)
    out = {"ma": {}, "escenario": {}, "claves": {}, "ruta": ruta, "renglones": 0, "usados": 0, "ultimo": None,
           "texto": "", "avisos": []}
    if ruta is None:
        out["texto"] = f"sin {PATRON_MONTOS_AFIANZADOS} en entradas/"
        return out
    try:
        df = _leer_csv_area(ruta)
    except Exception as e:  # noqa: BLE001
        out["avisos"].append(f"{ruta.name}: no se pudo leer ({type(e).__name__}); sin monto afianzado")
        out["texto"] = out["avisos"][-1]
        return out
    out["renglones"] = len(df)
    c_p, c_r, c_t = _col_csv(df, "Periodo"), _col_csv(df, "Ramo"), _col_csv(df, "Monto Afianzado Tot")
    c_e, c_k = _col_csv(df, "Escenario"), _col_csv(df, "Clave")
    if c_p is None or c_r is None or c_t is None:
        out["avisos"].append(f"{ruta.name}: faltan las columnas Periodo, Ramo o Monto Afianzado Tot; sin monto afianzado")
        out["texto"] = out["avisos"][-1]
        return out
    per, m = _num_csv(df[c_p]), _num_csv(df[c_t])
    ram = _num_csv(df[c_r]).map(_texto_ramo)
    esc = df[c_e].astype(str).str.strip() if c_e else pd.Series("Real", index=df.index)
    cla = df[c_k].astype(str).str.strip() if c_k else pd.Series("", index=df.index)
    ok = per.between(190001, 299912) & ram.isin([str(r) for r in ramos])
    vacios = int((ok & m.isna()).sum())
    t = pd.DataFrame({"p": per[ok].astype(int), "r": ram[ok], "m": m[ok], "e": esc[ok], "k": cla[ok]})
    t = t[t["m"].notna()]
    out["usados"] = len(t)
    t["est"] = t["e"].str.lower().str.startswith("est")
    en_cero = []
    for (r, p), g in t.groupby(["r", "p"]):
        v = float(g["m"].sum())
        if v == 0:
            en_cero.append(f"{r} {p}")
            continue
        out["ma"][(r, int(p))] = v
        out["escenario"][(r, int(p))] = "Estimado" if g["est"].any() else "Real"
    out["claves"] = {r: set(g["k"]) for r, g in t.groupby("r")}
    reales = sorted({p for (r, p), e in out["escenario"].items() if e == "Real"})
    est = sorted({p for (r, p), e in out["escenario"].items() if e != "Real"})
    out["ultimo"] = max(p for _, p in out["ma"]) if out["ma"] else None
    out["texto"] = (f"{ruta.name}: {out['usados']:,} de {out['renglones']:,} renglones (filtros: ramos de la BD de RFV y "
                    f"Monto Afianzado Tot con dato; {t['k'].nunique()} cedentes); real {_rangos_meses(reales)}"
                    + (f"; estimado del area {_rangos_meses(est)}" if est else ""))
    if vacios:
        out["avisos"].append(f"{ruta.name}: {vacios} renglon(es) sin Monto Afianzado Tot (no se usan)")
    if en_cero:
        out["avisos"].append(f"{ruta.name}: monto afianzado en 0 en {', '.join(en_cero)} (sin MA esos meses)")
    neg = t[t["m"] < 0]
    if len(neg):
        out["avisos"].append(f"{ruta.name}: {len(neg)} renglon(es) con monto afianzado negativo ("
                             + ", ".join(f"{n} {'estimado' if e else 'real'}" for e, n in neg.groupby("est").size().items())
                             + f"; suman {neg['m'].sum() / 1e6:,.2f} M MXN); se usan tal cual")
    meses = sorted(t["p"].unique())
    for a, b in zip(meses, meses[1:]):                 # un mes que repite al anterior renglon por renglon (copia)
        va = t[t["p"] == a].groupby(["r", "k"])["m"].sum()
        vb = t[t["p"] == b].groupby(["r", "k"])["m"].sum()
        if len(va) >= 5 and len(va) == len(vb) and va.index.equals(vb.index) and np.allclose(va.values, vb.values):
            out["avisos"].append(f"{ruta.name}: {b} es igual a {a} en los {len(vb)} pares ramo-cedente (parece copia "
                                 "del mes anterior); se usa tal cual")
    if reales and est:
        u, e1 = reales[-1], est[0]
        saltos = [(r, out["ma"][(r, e1)] / out["ma"][(r, u)] - 1) for r in sorted(out["claves"], key=int)
                  if (r, u) in out["ma"] and (r, e1) in out["ma"]]
        grandes = [f"{r}: {x:+.1%}" for r, x in saltos if abs(x) > 0.03]
        if grandes:
            out["avisos"].append(f"{ruta.name}: el estimado del area de {e1} se aparta del real de {u} en "
                                 + ", ".join(grandes) + " (el estimado no arranca en el ultimo real)")
    if not out["ma"]:
        out["avisos"].append(f"{ruta.name}: ningun renglon de los ramos de la BD de RFV con monto afianzado")
    return out


def ma_del_mes(ma_info: dict | None, r, p: int) -> tuple[float, str]:
    """MA del ramo en el mes (MXN) y su origen: el del CSV ("Real" o "Estimado"); despues del ultimo mes del CSV, el de
    ese ultimo mes ("fijo en AAAAMM"); en un hueco entre dos meses del CSV o antes del primero, (nan, "sin dato")."""
    ma = (ma_info or {}).get("ma") or {}
    r = str(r)
    if (r, p) in ma:
        return ma[(r, p)], (ma_info.get("escenario") or {}).get((r, p), "Real")
    meses = [q for (x, q) in ma if x == r]
    if meses and p > max(meses):
        u = max(meses)
        return ma[(r, u)], f"fijo en {u}"
    return math.nan, "sin dato"


def ma_hasta(ma_info: dict | None, corte: int, solo_real: bool = True) -> dict:
    """ma_info con solo los meses hasta corte (y, con solo_real, los Real): el MA que se conocia al corte (backtesting)."""
    if not ma_info:
        return {}
    esc = ma_info.get("escenario") or {}
    keep = {k for k in (ma_info.get("ma") or {}) if k[1] <= corte and (not solo_real or esc.get(k) == "Real")}
    return {**ma_info, "ma": {k: v for k, v in ma_info["ma"].items() if k in keep},
            "escenario": {k: v for k, v in esc.items() if k in keep}}


def pd_xdefault(ramos: list, periodos: list[int]) -> dict:
    """PD de referencia por ramo y mes con el CSV de default por poliza del area (PATRON_XDEFAULT): suma de
    PrimaCedidaOriginal x Default_Total / suma de PrimaCedidaOriginal de las polizas con aPOG_MesProc en los ultimos N
    meses (MESES_PD_XDEFAULT, contando el mes), en moneda original como viene. No entra a la IRR (el area pondera cada
    contrato por su reserva cedida vigente y esa liga esta en su base Access): se compara con la PD del castigo. Regresa
    {"pd": {(meses, ramo, periodo): PD}, "renglones", "usados", "texto", "avisos"}."""
    ruta = _csv_entrada(PATRON_XDEFAULT)
    out = {"pd": {}, "renglones": 0, "usados": 0, "texto": "", "avisos": [], "ruta": ruta}
    if ruta is None:
        out["texto"] = f"sin {PATRON_XDEFAULT} en entradas/"
        return out
    try:
        df = _leer_csv_area(ruta)
    except Exception as e:  # noqa: BLE001
        out["texto"] = f"{ruta.name}: no se pudo leer ({type(e).__name__})"
        return out
    out["renglones"] = len(df)
    c = {k: _col_csv(df, n) for k, n in (("p", "aPOG_MesProc"), ("r", "Ramo"), ("c", "PrimaCedidaOriginal"),
                                         ("d", "Default_Total"))}
    if any(v is None for v in c.values()):
        out["texto"] = f"{ruta.name}: faltan aPOG_MesProc, Ramo, PrimaCedidaOriginal o Default_Total"
        return out
    t = pd.DataFrame({"p": _num_csv(df[c["p"]]), "r": _num_csv(df[c["r"]]).map(_texto_ramo),
                      "c": _num_csv(df[c["c"]]), "d": _num_csv(df[c["d"]])})
    sin_pd = int(t["d"].isna().sum())
    t = t[t["p"].between(190001, 299912) & t["r"].isin([str(r) for r in ramos]) & t["d"].notna() & t["c"].notna()]
    out["usados"] = len(t)
    if t.empty:
        out["texto"] = f"{ruta.name}: sin polizas de los ramos de la BD de RFV con PD"
        return out
    t = t.assign(p=t["p"].astype(int), w=t["c"] * t["d"])
    p_max = int(t["p"].max())
    for r, g in t.groupby("r"):
        agg = g.groupby("p")[["w", "c"]].sum()
        idx = np.array([periodo_a_indice(int(q)) for q in agg.index])
        for p in periodos:
            if p > p_max:
                continue
            i = periodo_a_indice(p)
            for n in MESES_PD_XDEFAULT:
                sel = (idx <= i) & (idx > i - n)
                cs = float(agg["c"].values[sel].sum())
                if cs:
                    out["pd"][(n, r, p)] = float(agg["w"].values[sel].sum()) / cs
    altos, unos = int((t["d"] >= 0.5).sum()), int((t["d"] >= 1).sum())
    out["texto"] = (f"{ruta.name}: {out['usados']:,} de {out['renglones']:,} renglones (filtros: ramos de la BD de RFV y "
                    f"Default_Total con dato; {sin_pd:,} sin PD), polizas de {int(t['p'].min())} a {p_max}; "
                    f"{altos} con PD de 0.5 o mas ({unos} con PD = 1); PD ponderada por la prima cedida en moneda "
                    "original, ventanas de " + " y ".join(f"{n} meses" for n in MESES_PD_XDEFAULT))
    return out


def csu_fianzas(seg: dict | None, ramos: list) -> dict:
    """Comision sobre utilidades no pagada (%CSU) por ramo como el script del area: en el segmento de prima de reserva,
    la prima de los contratos Tipo Rea 1 con Id Uti = 1 (xVigMaxProp) cuya llave no esta pagada en xComUtil (IdCom = 1)
    lleva %ComUti (COM_UTILIDAD_FIANZAS: 160 y 170); %CSU = esa comision / prima tomada del segmento PR (base del real
    por contrato). Se mide y se reporta; no entra al FPR. Regresa {"pcsu": {ramo: razon}, "detalle": [renglones],
    "texto", "avisos"}."""
    out = {"pcsu": {}, "detalle": [], "texto": "", "avisos": [], "renglones": 0}
    tab = (seg or {}).get("contratos")
    rv, rc = _csv_entrada(PATRON_VIGMAX_PROP), _csv_entrada(PATRON_COM_UTIL)
    if tab is None or tab.empty or rv is None or rc is None or not (tab["llave"] != "").any():
        out["texto"] = ("sin " + " ni ".join(x for x, f in ((PATRON_VIGMAX_PROP, rv), (PATRON_COM_UTIL, rc)) if f is None)
                        + " en entradas/" if rv is None or rc is None else
                        "la base del real no trae la llave del contrato (Corredor, Compania, Num Contrato, Ano Susc.)")
        return out
    try:
        vp, cu = _leer_csv_area(rv), _leer_csv_area(rc)
    except Exception as e:  # noqa: BLE001
        out["texto"] = f"no se pudieron leer {rv.name} o {rc.name} ({type(e).__name__})"
        return out
    c_lv, c_iu, c_lc, c_ic = _col_csv(vp, "Llave"), _col_csv(vp, "Id Uti"), _col_csv(cu, "Llave"), _col_csv(cu, "IdCom")
    if None in (c_lv, c_iu, c_lc, c_ic):
        out["texto"] = f"faltan Llave e Id Uti en {rv.name} o Llave e IdCom en {rc.name}"
        return out
    iu = pd.DataFrame({"llave": vp[c_lv].astype(str).str.strip(), "iu": _num_csv(vp[c_iu])})
    conflicto = int((iu.dropna().groupby("llave")["iu"].nunique() > 1).sum())
    id_uti = iu.groupby("llave")["iu"].max()            # (una llave con 1 en algun renglon cuenta con la bandera)
    cu_ = pd.DataFrame({"llave": cu[c_lc].astype(str).str.strip(), "ic": _num_csv(cu[c_ic])})
    pagada = set(cu_.loc[cu_["ic"] == 1, "llave"])
    for r in ramos:
        r = str(r)
        x = tab[(tab["ramo"] == r) & (tab["seg"] == "PR")]
        p_pr = float(x["prima"].sum())
        if not p_pr:
            continue
        t1 = x[x["tipo"] == 1]
        bandera = t1["llave"].map(id_uti)
        en_vp = t1["llave"].isin(id_uti.index)
        con = t1[(bandera == 1) & ~t1["llave"].isin(pagada)]
        pcu = float(COM_UTILIDAD_FIANZAS.get(r, 0.0))
        csu = float(con["prima"].sum()) * pcu
        out["pcsu"][r] = csu / p_pr
        p1 = float(t1["prima"].sum())
        p1 = p1 if p1 > 0 else math.nan                 # (sin prima Tipo Rea 1 positiva, las razones van en N/A)
        out["detalle"].append({
            "Ramo": r, "Meses": _rangos_meses(x["periodo"].unique()), "Renglones del segmento PR": int(x["n"].sum()),
            "Prima PR (MXN)": p_pr, "Prima PR Tipo Rea 1 (MXN)": p1,
            "% sin llave en xVigMaxProp": float(t1.loc[~en_vp, "prima"].sum()) / p1,
            "% con llave y sin Id Uti": float(t1.loc[en_vp & bandera.isna(), "prima"].sum()) / p1,
            "% con Id Uti = 1": float(t1.loc[bandera == 1, "prima"].sum()) / p1,
            "% pagada (xComUtil)": float(t1.loc[t1["llave"].isin(pagada), "prima"].sum()) / p1,
            "%ComUti del area": pcu, "Comision sobre utilidades no pagada (MXN)": csu, "%CSU = CSU / prima PR": csu / p_pr})
        out["renglones"] = out.get("renglones", 0) + int(x["n"].sum())
    out["texto"] = (f"{rv.name} ({len(vp):,} renglones, {iu['llave'].nunique():,} llaves, "
                    f"{int(iu['iu'].isna().sum())} sin Id Uti) y {rc.name} ({len(cu):,} renglones) cruzados con "
                    f"{out['renglones']:,} renglones del segmento PR de la base del real por contrato (Tipo Rea 1): "
                    + "; ".join(f"{d['Ramo']}: {d['%CSU = CSU / prima PR']:.2%}" for d in out["detalle"])
                    + " de la prima PR (un piso: la prima con llave sin Id Uti, contratos nuevos, va sin comision)")
    if conflicto:
        out["avisos"].append(f"{rv.name}: {conflicto} llave(s) con Id Uti distinto en varios renglones")
    return out


def cobertura_ma(seg: dict | None, ma_info: dict | None, ramos: list) -> list:
    """Prima del proporcional de Mexico (Tipo Rea 1, Terr 1) de la base del real por contrato por ramo y si su cedente
    (compania) trae monto afianzado en el CSV: la que no lo trae no tiene reserva por MA en el calculo y queda en el FV
    residual. Regresa renglones para el diagnostico."""
    tab = (seg or {}).get("contratos")
    claves = (ma_info or {}).get("claves") or {}
    if tab is None or tab.empty or not claves:
        return []
    out = []
    for r in ramos:
        r = str(r)
        x = tab[(tab["ramo"] == r) & (tab["tipo"] == 1) & (tab["terr"] == 1)]
        if x.empty:
            continue
        sin = x[~x["cia"].isin(claves.get(r, set()))]
        tot = float(x["prima"].sum())
        out.append({"Ramo": r, "Meses": _rangos_meses(x["periodo"].unique()), "Renglones": int(x["n"].sum()),
                    "Prima proporcional de Mexico (MXN)": tot,
                    "Prima de cedentes sin MA en el CSV (MXN)": float(sin["prima"].sum()),
                    "% sin MA": float(sin["prima"].sum()) / tot if tot else math.nan,
                    "Cedentes sin MA": ", ".join(sorted(set(sin["cia"]) - {""}, key=lambda c: (len(c), c)))})
    return out


def pd_fianzas(area: dict, bd: BDMontos, tc_hist: dict, ramos: list, periodos: list[int], pt: dict | None = None) -> dict:
    """PD del reasegurador por ramo y mes de la BD de RFV: CASTIGO / (IRR + CASTIGO) del calculo del area (el castigo es
    la reserva cedida por la PD de cada contrato), en los meses en que su RVABRUTA queda a menos de TOLERANCIA_AREA_SAP
    de la RFV BRUTO de SAP (en pesos, con tc_hist); despues del ultimo mes medido, ese mismo (supuesto declarado: el area
    no reporta castigo despues). Con pt (prima de Fianzas), el diagnostico lleva la permanencia del area (PRIMA vigente /
    PRIMA 24M) y la contingencia del mes entre la PT del mes. Regresa {"hist": {(ramo, periodo): PD}, "medido":
    {(ramo, periodo): bool}, "ultimo": {ramo: (periodo, PD)}, "diag": [renglones para la hoja RFV_Metodo_Area]}."""
    out = {"hist": {}, "medido": {}, "ultimo": {}, "diag": []}
    c_b, c_i = norm("RFV BRUTO"), norm("RFV IRR")
    for r in ramos:
        u = None
        for p in periodos:
            a = area.get((str(r), p))
            medido = False
            if a:
                t = tc_hist.get(p) or tc_para_periodo(bd, p)
                b_sap = bd.valores.get((c_b, p, r), math.nan)
                sap = b_sap * t
                bruta, irr, cas, prima = (a.get(k, 0.0) for k in ("RVABRUTA", "IRR", "CASTIGO", "PRIMA"))
                cerca = bool(np.isfinite(sap) and sap > 0 and abs(abs(bruta) / sap - 1) <= TOLERANCIA_AREA_SAP)
                ced = irr + cas
                pd_ = cas / ced if ced and np.sign(cas) in (0, np.sign(ced)) else math.nan
                completo = bool(prima and ced)
                medido = completo and cerca and bool(np.isfinite(pd_))
                if medido:
                    u = (p, float(pd_))
                s24, _ = _prima_ventana(pt, r, p) if pt and pt.get("mensual") else (math.nan, False)
                pt_mes = (pt or {}).get("mensual", {}).get((r, p), math.nan)
                out["diag"].append({
                    "Ramo": r, "Periodo": p, "RVABRUTA del area (MXN)": bruta, "RFV BRUTO SAP (MXN)": sap,
                    "Diferencia %": abs(bruta) / sap - 1 if np.isfinite(sap) and sap else math.nan,
                    "PD medida": ("si" if medido else "no: sin dato completo (sin prima o sin cesion)" if not completo
                                  else "no: se aparta de SAP" if not cerca else "no"),
                    "PRIMA vigente (MXN)": prima,
                    "FACTOR RVA = RVABRUTA / PRIMA vigente": abs(bruta / prima) if prima else math.nan,
                    f"PERMANENCIA = PRIMA vigente / PRIMA {MESES_PRIMA_RFV}M": abs(prima) / s24 if s24 and prima else math.nan,
                    "CASTIGO (MXN)": cas, "PD = CASTIGO / (IRR + CASTIGO)": pd_,
                    "RC del area = (IRR + CASTIGO) / RVABRUTA": abs(ced / bruta) if bruta and ced else math.nan,
                    "CESION SAP": bd.valores.get((c_i, p, r), math.nan) / b_sap if b_sap else math.nan,
                    "RVACONT del mes (MXN)": a.get("RVACONT", 0.0),
                    "RVACONT / PT del mes": (abs(a.get("RVACONT", 0.0)) / pt_mes
                                             if pt_mes and abs(a.get("RVACONT", 0.0)) >= 1000 else math.nan),
                    "Nota": "el area reporta los montos con signo negativo y las razones van en valor absoluto; RVACONT "
                            "trae la contingencia del segmento de prima de reserva (15 % de la PR) y la del facultativo, "
                            "mas un marcador de 1 por renglon de montos afianzados del script del area (por eso, abajo "
                            "de 1,000 la razon va en N/A)"})
            if u is not None:
                out["hist"][(r, p)] = u[1]
                out["medido"][(r, p)] = medido
        if u is not None:
            out["ultimo"][r] = u
    return out


def _prima_ventana(pt: dict, r, p: int) -> tuple[float, bool]:
    """(PRIMA 24M del ramo al mes p: suma de los ultimos MESES_PRIMA_RFV meses de PT, si todos sus meses vienen de
    alguna fuente)."""
    qs = [_mes_menos(p, k) for k in range(MESES_PRIMA_RFV)]
    return (float(sum(pt["mensual"].get((r, q), 0.0) for q in qs)), all(q in pt["fuente"] for q in qs))


def indicaciones_rfv(ramos=None) -> tuple[dict, dict, list]:
    """COMISION_RFV y PD_FIANZAS normalizados ({ramo como texto: valor}) y validados: un dict con valores entre 0 y
    1 - CARGAS_RFV (comision) o entre 0 y 1 (PD), en fraccion; lo demas se ignora con aviso (tambien una clave que no sea
    un ramo de la BD, si se dan los ramos). Regresa (comision, pd, avisos)."""
    avisos, out = [], []
    for nombre, valor, tope in (("COMISION_RFV", COMISION_RFV, 1 - CARGAS_RFV), ("PD_FIANZAS", PD_FIANZAS, 1.0)):
        d = {}
        if valor and not isinstance(valor, dict):
            avisos.append(f"{nombre} debe ser un diccionario por ramo, p. ej. {{'160': 0.4}}: se ignora")
        for k, v in (valor.items() if isinstance(valor, dict) else []):
            r = str(int(k)) if isinstance(k, (int, float)) and not isinstance(k, bool) else str(k).strip()
            x = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else a_numero(v)[0]
            if not (np.isfinite(x) and 0 <= x < tope):
                avisos.append(f"{nombre}[{r}] = {v}: fuera de 0 a {tope:.4f} (en fraccion: 0.40 es 40 %), se ignora")
            elif ramos is not None and r not in [str(x_) for x_ in ramos]:
                avisos.append(f"{nombre}: {r} no es un ramo de la BD de RFV, se ignora")
            else:
                d[r] = x
        out.append(d)
    return out[0], out[1], avisos


def factores_rfv_ramo(r, seg: dict | None, pdinfo: dict | None, indicaciones: bool = True) -> dict | None:
    """Factores de la metodologia del area para el ramo (FACTORES_RFV): %SEG PR y %COM PR medidos (seg, de
    segmento_pr_fianzas), %CARGAS, %GA, FPR = %SEG PR x (1 - %COM PR - %CARGAS), la ultima PD medida (pdinfo, de
    pd_fianzas) y FCR = 1 - PD (1 sin PD); con _P, los de la proyeccion: COMISION_RFV (solo si el ramo trae %SEG PR) y
    PD_FIANZAS, validados (indicaciones_rfv); sin indicaciones (backtesting), los medidos. None si FACTORES_RFV esta
    apagado."""
    if not FACTORES_RFV:
        return None
    r = str(r)
    sp = (seg or {}).get("seg_pr", {}).get(r, math.nan)
    pc = (seg or {}).get("pcom", {}).get(r, math.nan)
    pd_ = ((pdinfo or {}).get("ultimo", {}).get(r) or (None, math.nan))[1]
    com_i, pd_i, _ = indicaciones_rfv() if indicaciones else ({}, {}, [])
    pc_p = com_i.get(r, pc) if np.isfinite(sp) else pc
    pd_p = pd_i.get(r, pd_)
    fpr = sp * (1 - pc - CARGAS_RFV) if np.isfinite(sp) and np.isfinite(pc) else math.nan
    fpr_p = sp * (1 - pc_p - CARGAS_RFV) if np.isfinite(sp) and np.isfinite(pc_p) else math.nan
    return {"SEG": sp, "PCOM": pc, "PCOM_P": pc_p, "PCARGAS": CARGAS_RFV, "PGA": GASTO_ADMON_RFV, "FPR": fpr,
            "FPR_P": fpr_p, "PD": pd_, "PD_P": pd_p, "FCR": 1 - pd_ if np.isfinite(pd_) else 1.0,
            "FCR_P": 1 - pd_p if np.isfinite(pd_p) else 1.0,
            "completo": bool(np.isfinite(fpr) and fpr > 0 and np.isfinite(fpr_p) and fpr_p > 0)}


def calcular_rfv_prima(bd: BDMontos, proy: dict, pt: dict | None, periodos_proy: list[int], ultimo: int,
                       tc_hist: dict | None = None, tc_pt: dict | None = None, com: dict | None = None,
                       pdinfo: dict | None = None, indicaciones: bool = True, ma_info: dict | None = None) -> dict:
    """RFV por prima (Fianzas): FRV = RFV BRUTO x TC / PRIMA 24M en la historia, proyectado con TIPO_MODELO_FRV desde el
    ultimo mes real; CESION = RFV IRR / RFV BRUTO real proyectada con el modelo de la cesion de Danos
    (TIPO_MODELO_FACTORES["CESION"]); RFV BRUTO = PRIMA 24M x FRV / TC (el del mes proyectado), RFV IRR = BRUTO x CESION,
    RFV NETO = BRUTO - IRR. La RCONT no cambia. El TC de la historia es el de tc_hist (el real con que SAP convirtio
    cada mes, y en los meses que la BD traia en pesos el de esa correccion, como el modelo) y, sin el, el de la columna
    TC (tc_para_periodo). Un mes cuya PRIMA 24M no esta completa (algun mes sin fuente) y los ramos fuera de
    RAMOS_RFV_POR_PRIMA siguen con el modelo. Con tc_pt (TC por mes de la prima) se calcula ademas la sensibilidad en
    dolares: la misma descomposicion con la prima y la RFV en USD (la reserva como si fuera en dolares). Con
    FACTORES_RFV (factores_rfv_ramo, con el segmento de com y la PD de pdinfo), el FRV se separa en FPR x (1 + %GA) x FV
    y la cesion en RC x FCR: FV = FRV del modelo / (FPR x (1 + %GA)) y RC = CESION del modelo / FCR con los factores
    medidos, y FRV = FPR_P x (1 + %GA) x FV y CESION = RC x FCR_P con los de la proyeccion (iguales a los medidos salvo
    COMISION_RFV o PD_FIANZAS). Con MA_RFV y el monto afianzado (ma_info, de leer_montos_afianzados), en los ramos de
    MA_RFV_RAMOS la reserva del segmento de monto afianzado va aparte: RFV MA = MA x (omega + alfa_k) (ma_del_mes: el del
    CSV, real o estimado, y despues de su ultimo mes ese ultimo, fijo), el modelo proyecta el FRV residual = (RFV BRUTO x
    TC - RFV MA) / PRIMA 24M (los meses sin MA van sin dato y el modelo los interpola; los ultimos meses sin MA hasta
    ultimo toman el ultimo MA conocido) y FRV = FRV residual + RFV MA / PRIMA 24M; FV = FRV residual / (FPR x (1 + %GA)).
    Regresa {"proy": montos con la RFV nueva, "aplica": {(periodo, ramo)}, "frv":
    {(periodo, ramo): FRV}, "cesion": {...}, "factores": {ramo: factores_rfv_ramo}, "fv": {(periodo, ramo): FV}, "rc":
    {(periodo, ramo): RC},
    "tc_hist": {periodo: TC usado en la historia}, "usd": {(periodo, ramo): RFV BRUTO en dolares}, "split": ramos con
    el monto afianzado aparte, "ma": {(periodo, ramo): (MA, origen)} y "rfv_ma": {(periodo, ramo): RFV MA en MXN} (todos
    los ramos y meses, historia y proyeccion), "ma_info", "series", "resumen", "alertas", "estado"}."""
    h = len(periodos_proy)
    out = {"proy": dict(proy), "aplica": set(), "frv": {}, "cesion": {}, "tc_hist": {}, "usd": {}, "series": [],
           "resumen": [], "alertas": [], "estado": "", "factores": {}, "fv": {}, "rc": {}, "com": com or {}, "pt": pt,
           "pdinfo": pdinfo or {}, "split": set(), "ma": {}, "rfv_ma": {}, "ma_info": ma_info or {}}
    if not pt or not pt.get("mensual"):
        out["estado"] = "sin prima tomada de Fianzas por ramo: la RFV sigue con el modelo"
        return out
    c_b, c_i, c_n = norm("RFV BRUTO"), norm("RFV IRR"), norm("RFV NETO")
    per_hist = sorted({p for (c, p) in bd.filas if c == c_b and p <= ultimo})
    tc_hist = tc_hist or {}
    tc = {p: tc_hist.get(p) or tc_para_periodo(bd, p) for p in per_hist + list(periodos_proy)}
    sel = RAMOS_RFV_POR_PRIMA                          # (un "160" sin coma de tupla es un solo ramo, no "1", "6", "0")
    ramos_sel = None if sel is None else {str(x).strip() for x in ((sel,) if isinstance(sel, (str, int)) else sel)}
    out["tc_hist"] = {p: tc[p] for p in per_hist}
    marcas = sorted({p for p in periodos_proy if p % 100 == 12} | {periodos_proy[-1]})

    def prima_usd(r, p):                               # PRIMA 24M en dolares (cada mes con su TC)
        qs = [_mes_menos(p, k) for k in range(MESES_PRIMA_RFV)]
        return float(sum(pt["mensual"].get((r, q), 0.0) / _tc_cercano(tc_pt, q) for q in qs))
    ramos_ma = {str(x).strip() for x in ((MA_RFV_RAMOS,) if isinstance(MA_RFV_RAMOS, (str, int)) else MA_RFV_RAMOS or ())}
    for r in bd.cols_ramo:
        frv_h, ces_h, res_h = {}, {}, {}
        oa = OMEGA_FIANZAS.get(str(r), math.nan) + ALFA_FIANZAS.get(str(r), math.nan)
        con_ma = bool(MA_RFV and ma_info and any(x == str(r) for x, _ in (ma_info.get("ma") or {})))
        for p in per_hist + list(periodos_proy):       # (MA y RFV MA de todos los meses: informativos fuera del split)
            v_ma, o_ma = ma_del_mes(ma_info, r, p) if con_ma else (math.nan, "sin dato")
            if np.isfinite(v_ma):
                out["ma"][(p, r)] = (v_ma, o_ma)
                out["rfv_ma"][(p, r)] = v_ma * oa if np.isfinite(oa) else math.nan
        for p in per_hist:
            b, i_ = bd.valores.get((c_b, p, r), math.nan), bd.valores.get((c_i, p, r), math.nan)
            s, completa = _prima_ventana(pt, r, p)
            frv_h[p] = b * tc[p] / s if completa and s > 0 and np.isfinite(b) else math.nan
            ces_h[p] = i_ / b if np.isfinite(i_) and np.isfinite(b) and b > UMBRAL_CERO_MONTOS else math.nan
            rma = out["rfv_ma"].get((p, r), math.nan)
            res_h[p] = (b * tc[p] - rma) / s if np.isfinite(frv_h[p]) and np.isfinite(rma) else math.nan
        ok_p = [p for p in per_hist if np.isfinite(frv_h[p])]
        ok_r = [p for p in ok_p if np.isfinite(res_h[p])]
        motivo_ma = ("" if str(r) in ramos_ma else "fuera de MA_RFV_RAMOS (RFV MA informativa)") if MA_RFV else \
            "MA_RFV = False"
        if not motivo_ma:
            motivo_ma = ("sin monto afianzado del ramo" if not con_ma else
                         "sin omega o alfa del ramo" if not np.isfinite(oa) else
                         f"menos de {MIN_MESES_FRV} meses con FRV y MA" if len(ok_r) < MIN_MESES_FRV else
                         f"sin MA al ultimo mes ({ultimo})" if ultimo not in ok_r else "")
        split = not motivo_ma
        b_u = bd.valores.get((c_b, ultimo, r), math.nan)
        fac = factores_rfv_ramo(r, com, pdinfo, indicaciones)
        if fac is not None:
            out["factores"][r] = fac
        fila = {"Ramo": r, "Meses de FRV real": len(ok_p), "Desde": ok_p[0] if ok_p else None,
                "Hasta": ok_p[-1] if ok_p else None}
        motivo = ""
        if ramos_sel is not None and str(r) not in ramos_sel:
            motivo = "fuera de RAMOS_RFV_POR_PRIMA: sigue con el modelo"
        elif not (np.isfinite(b_u) and b_u > UMBRAL_CERO_MONTOS):
            motivo = "RFV BRUTO real en cero al ultimo mes"
        elif len(ok_p) < MIN_MESES_FRV:
            motivo = f"menos de {MIN_MESES_FRV} meses de FRV real (falta prima de {MESES_PRIMA_RFV} meses)"
        elif ultimo not in ok_p:
            motivo = f"sin PRIMA {MESES_PRIMA_RFV}M completa al ultimo mes"
        frv_f = ces_f = None
        if not motivo:
            per = rango_periodos((ok_r if split else ok_p)[0], ultimo)
            base_m = res_h if split else frv_h         # (con el MA aparte, el modelo va sobre el FRV residual)
            res = pronosticar(Serie(("FIANZAS", "RFV", "FRV", r), TIPO_MODELO_FRV, per,
                                    [base_m.get(q, math.nan) for q in per], ultimo, h, dominio=(0.0, None)))
            frv_f = np.asarray(res.pronostico, dtype=float)
            if len(frv_f) != h or not np.all(np.isfinite(frv_f)):
                motivo, frv_f = "no se pudo proyectar el FRV", None
            else:
                prm = res.parametros or {}
                fila.update({"FRV modelo": res.regla or res.modelo,
                             "FRV alpha": prm.get("alpha", math.nan),
                             "FRV error % backtest (modelo)": res.error_modelo,
                             "FRV error % backtest (ultimo valor)": res.error_ultimo_valor,
                             f"FRV {ultimo}": frv_h[ultimo]})
                out["alertas"] += [("FIANZAS", f"RFV | FRV | ramo {r}", a) for a in res.alertas
                                   if not str(a).startswith("Se usa")]
        if frv_f is not None:
            ok_c = [p for p in per_hist if np.isfinite(ces_h[p])]
            ces_f = np.full(h, ces_h[ok_c[-1]]) if ok_c else np.zeros(h)
            if ok_c:
                per_c = rango_periodos(ok_c[0], ultimo)
                res_c = pronosticar(Serie(("FIANZAS", "RFV", "CESION", r), TIPO_MODELO_FACTORES["CESION"], per_c,
                                          [ces_h.get(q, math.nan) for q in per_c], ultimo, h, dominio=DOMINIO_CESION))
                x = np.asarray(res_c.pronostico, dtype=float)
                if len(x) == h and np.all(np.isfinite(x)):
                    ces_f = x
                u = ces_h[ok_c[-1]]
                fila.update({"CESION modelo": res_c.regla or res_c.modelo,
                             "CESION error % backtest (modelo)": res_c.error_modelo,
                             "CESION error % backtest (ultimo valor)": res_c.error_ultimo_valor,
                             f"CESION {ultimo}": u, f"CESION {periodos_proy[-1]}": float(ces_f[-1])})
                if abs(ces_f[-1] - u) > 0.10:
                    out["alertas"].append(("FIANZAS", f"RFV | CESION | ramo {r}",
                                           f"la proyeccion lleva la cesion de {u:.1%} ({ultimo}) a {ces_f[-1]:.1%} "
                                           f"({periodos_proy[-1]}); revisar si sigue"))
        usd_f = None
        if frv_f is not None and tc_pt:                # sensibilidad: la reserva como si fuera en dolares
            per_u = rango_periodos(ok_p[0], ultimo)
            v_u = [bd.valores.get((c_b, q, r), math.nan) / prima_usd(r, q) if prima_usd(r, q) > 0 else math.nan
                   for q in per_u]
            res_u = pronosticar(Serie(("FIANZAS", "RFV", "FRV USD", r), TIPO_MODELO_FRV, per_u, v_u, ultimo, h,
                                      dominio=(0.0, None)))
            x = np.asarray(res_u.pronostico, dtype=float)
            if len(x) == h and np.all(np.isfinite(x)):
                usd_f = x
        n_ap = 0
        for j, p in enumerate(periodos_proy):
            if frv_f is None:
                break
            s, completa = _prima_ventana(pt, r, p)
            fz, cz = float(frv_f[j]), float(ces_f[j])  # (con el MA aparte, fz es el FRV residual)
            rma = out["rfv_ma"].get((p, r), math.nan) if split else 0.0
            if split and not (np.isfinite(rma) and s > 0):
                continue
            dec = fac is not None and fac["completo"]
            fv_ = fz / (fac["FPR"] * (1 + fac["PGA"])) if dec else math.nan
            rc_ = cz / fac["FCR"] if fac is not None and fac["FCR"] > 0 else cz
            if dec:                                    # (con COMISION_RFV o PD_FIANZAS, FPR y FCR de la proyeccion)
                fz = fac["FPR_P"] * (1 + fac["PGA"]) * fv_
            if split:                                  # FRV = residual + RFV MA / PRIMA 24M
                fz += rma / s
            if fac is not None:
                cz = min(max(rc_ * fac["FCR_P"], 0.0), 1.0)
            bruto = s * fz / tc[p] if completa and tc[p] else math.nan
            out["series"].append({"Ramo": r, "Periodo": p, "PT del mes (MXN)": pt["mensual"].get((r, p), 0.0),
                                  f"PRIMA {MESES_PRIMA_RFV}M (MXN)": s, "Prima completa": "si" if completa else "no",
                                  "Fuente de la PT": pt["fuente"].get(p, "sin prima (0)"), "FRV": fz, "CESION": cz,
                                  "TC": tc[p], **({"%SEG PR": fac["SEG"], "%COM PR": fac["PCOM_P"], "%CARGAS": fac["PCARGAS"],
                                                   "FPR": fac["FPR_P"], "%GA": fac["PGA"], "FV": fv_, "PD": fac["PD_P"],
                                                   "FCR": fac["FCR_P"], "RC": rc_} if fac else {}),
                                  "RC PRIMA": _rc_prima(pt, r, p),
                                  "MA (MXN)": (out["ma"].get((p, r)) or (math.nan,))[0],
                                  "Origen del MA": (out["ma"].get((p, r)) or (None, "sin dato"))[1],
                                  "RFV MA (MXN)": out["rfv_ma"].get((p, r), math.nan),
                                  "MA aparte": "si" if split else "no", "RFV BRUTO por prima": bruto,
                                  "RFV BRUTO del modelo": proy.get((c_b, p, r), math.nan),
                                  "RFV NETO por prima": bruto * (1 - cz) if np.isfinite(bruto) else math.nan,
                                  "RFV NETO del modelo": proy.get((c_n, p, r), math.nan)})
            if not np.isfinite(bruto) or bruto < 0:
                continue
            irr = bruto * cz
            out["proy"][(c_b, p, r)] = float(bruto)
            out["proy"][(c_i, p, r)] = float(irr)
            out["proy"][(c_n, p, r)] = float(bruto - irr)
            out["aplica"].add((p, r))
            out["frv"][(p, r)], out["cesion"][(p, r)] = fz, cz
            if dec:
                out["fv"][(p, r)] = fv_
            if fac is not None:
                out["rc"][(p, r)] = rc_
            if usd_f is not None:
                out["usd"][(p, r)] = prima_usd(r, p) * float(usd_f[j])
            n_ap += 1
        fila["Meses con RFV por prima"] = n_ap
        fila[f"FRV {periodos_proy[-1]}"] = out["frv"].get((periodos_proy[-1], r), math.nan)
        rma_u, b_u_mxn = out["rfv_ma"].get((ultimo, r), math.nan), b_u * tc.get(ultimo, math.nan)
        fila.update({"MA aparte": "si" if split else f"no ({motivo_ma})",
                     f"MA {ultimo} (MXN)": (out["ma"].get((ultimo, r)) or (math.nan,))[0],
                     f"Origen del MA {ultimo}": (out["ma"].get((ultimo, r)) or (None, "sin dato"))[1],
                     f"RFV MA {ultimo} (MXN)": rma_u,
                     f"RFV MA / RFV BRUTO {ultimo}": rma_u / b_u_mxn if np.isfinite(b_u_mxn) and b_u_mxn else math.nan,
                     f"MA {periodos_proy[-1]} (MXN)": (out["ma"].get((periodos_proy[-1], r)) or (math.nan,))[0],
                     f"Origen del MA {periodos_proy[-1]}": (out["ma"].get((periodos_proy[-1], r)) or (None, "sin dato"))[1],
                     f"FRV residual {ultimo}": res_h.get(ultimo, math.nan) if split else math.nan,
                     "Meses de FRV residual": len(ok_r) if split else 0,
                     "FACTOR MA (constante del area, no se usa)": FACTOR_MA_FIANZAS.get(str(r), math.nan)})
        if split and n_ap:
            out["split"].add(r)
        if fac is not None:                            # factores de la metodologia del area (FACTORES_RFV)
            ref_f = (((pt or {}).get("referencia") or {}).get("fcst") or {}).get(str(r)) or {}
            u_pd = ((pdinfo or {}).get("ultimo") or {}).get(str(r))
            fila.update({"%SEG PR": fac["SEG"], "%SEG PR del FCST": ref_f.get("seg_pr", math.nan),
                         "%COM PR": fac["PCOM"], "%COM PR del FCST": ref_f.get("com_pr", math.nan),
                         "%COM PR de la proyeccion": fac["PCOM_P"],
                         "%COM del ramo": (com or {}).get("pcom_ramo", {}).get(str(r), math.nan),
                         "%COM del ramo en el FCST": ref_f.get("comisiones", math.nan),
                         "%CARGAS": fac["PCARGAS"], "FPR": fac["FPR"], "%GA": fac["PGA"],
                         f"FV {ultimo}": ((res_h if split else frv_h).get(ultimo, math.nan)
                                          / (fac["FPR"] * (1 + fac["PGA"])) if fac["completo"] else math.nan),
                         f"FV {periodos_proy[-1]}": out["fv"].get((periodos_proy[-1], r), math.nan),
                         f"RC PRIMA {ultimo} (desde {(pt or {}).get('inicio', '-')})": _rc_prima(pt, r, ultimo),
                         "Cesion de prima del FCST": ref_f.get("cesion", math.nan),
                         "PD (ultima medida)": fac["PD"], "Mes de la PD": u_pd[0] if u_pd else None,
                         "PD de la proyeccion": fac["PD_P"], "FCR": fac["FCR_P"]})
            if n_ap and fac["completo"] and fac["SEG"] < 0.5 and not split:
                out["alertas"].append(("FIANZAS", f"RFV | FV | ramo {r}",
                                       f"solo {fac['SEG']:.0%} de la prima del ramo es del segmento de prima de reserva; "
                                       "el resto se reserva por monto afianzado (omega + alfa del Anexo 5.15.3), asi que "
                                       f"FV ({fv_ if np.isfinite(fv_) else math.nan:.2f}) es sobre todo esa reserva, no "
                                       "permanencia"))
            if n_ap and np.isfinite(fac["PCOM"]) and np.isfinite(ref_f.get("com_pr", math.nan)) \
                    and abs(ref_f["com_pr"] - fac["PCOM"]) > 0.05:
                out["alertas"].append(("FIANZAS", f"RFV | %COM PR | ramo {r}",
                                       f"el FCST trae comisiones de {ref_f['com_pr']:.1%} de la prima del segmento de "
                                       f"prima de reserva y el real {fac['PCOM']:.1%}: la proyeccion usa "
                                       + (f"{fac['PCOM_P']:.1%} (COMISION_RFV)" if fac["PCOM_P"] != fac["PCOM"] else
                                          "el real (COMISION_RFV para cambiarlo)")))
            rcp_u, ces_f_ = _rc_prima(pt, r, ultimo), ref_f.get("cesion", math.nan)
            if n_ap and np.isfinite(rcp_u) and np.isfinite(ces_f_) and abs(ces_f_ - rcp_u) > 0.05:
                out["alertas"].append(("FIANZAS", f"RFV | RC PRIMA | ramo {r}",
                                       f"el FCST cede {ces_f_:.1%} de la prima y desde {(pt or {}).get('inicio')} se "
                                       f"cedio {rcp_u:.1%}: la CESION de la reserva sigue con su modelo (RC PRIMA es "
                                       "informativa); conviene confirmar que el FCST traiga toda la retrocesion"))
        fila["Motivo"] = motivo or ("" if n_ap == h else f"{h - n_ap} mes(es) sin PRIMA {MESES_PRIMA_RFV}M completa "
                                                         "(quedan con el modelo)")
        for p in marcas:
            fila[f"RFV BRUTO modelo {p}"] = proy.get((c_b, p, r), math.nan)
            fila[f"RFV BRUTO por prima {p}"] = out["proy"][(c_b, p, r)] if (p, r) in out["aplica"] else math.nan
            fila[f"RFV NETO por prima {p}"] = out["proy"][(c_n, p, r)] if (p, r) in out["aplica"] else math.nan
            fila[f"RFV BRUTO {p} si fuera en dolares"] = out["usd"].get((p, r), math.nan)
        bm, bf = fila.get(f"RFV BRUTO modelo {periodos_proy[-1]}"), fila.get(f"RFV BRUTO por prima {periodos_proy[-1]}")
        if bm and np.isfinite(bf) and bm > 1e6 and abs(bf / bm - 1) > 0.5:
            out["alertas"].append(("FIANZAS", f"RFV | BRUTO | ramo {r}",
                                   f"{periodos_proy[-1]}: {bf / 1e6:,.1f} M USD por prima contra {bm / 1e6:,.1f} M del "
                                   "modelo"))
        out["resumen"].append(fila)
    ramos_ap = sorted({r for _, r in out["aplica"]}, key=int)
    out["estado"] = (f"ramos {', '.join(ramos_ap)} con RFV BRUTO = PRIMA {MESES_PRIMA_RFV}M x FRV / TC desde "
                     f"{periodos_proy[0]} ({len(out['aplica'])} de {len(bd.cols_ramo) * h} meses); IRR = BRUTO x "
                     "CESION; NETO = BRUTO - IRR; RCONT con su modelo"
                     + ((f"; FRV = FPR x (1 + %GA) x FV y CESION = RC x FCR en {', '.join(rs_f)} (FPR = %SEG PR x (1 - "
                         f"%COM PR - %CARGAS), %CARGAS {CARGAS_RFV:.2%}, %GA {GASTO_ADMON_RFV:.2%}; PD "
                         + ("medida en Res_Rvas (CASTIGO / (IRR + CASTIGO)), fija desde su ultimo mes medido"
                            if (pdinfo or {}).get("ultimo") else "sin dato: FCR = 1")
                         + ("; COMISION_RFV" if indicaciones and indicaciones_rfv()[0] else "")
                         + ("; PD_FIANZAS" if indicaciones and indicaciones_rfv()[1] else "") + ")")
                        if (rs_f := sorted({r for _, r in out["fv"]}, key=int)) else "")
                     + ((f"; monto afianzado aparte en {', '.join(sorted(out['split'], key=int))}: FRV = FRV residual + "
                         f"RFV MA / PRIMA {MESES_PRIMA_RFV}M (en la BD, FRV = FPR x (1 + %GA) x FV + RFV MA / PRIMA "
                         f"{MESES_PRIMA_RFV}M), RFV MA = MA x (omega + alfa_k), MA del CSV del area hasta "
                         f"{(ma_info or {}).get('ultimo')} y fijo despues") if out["split"] else "")) if ramos_ap else \
        ("ningun ramo aplica, la RFV sigue con el modelo: " + "; ".join(f"{f['Ramo']}: {f['Motivo']}"
                                                                      for f in out["resumen"] if f.get("Motivo")))
    if out["usd"]:                                     # sensibilidad a la moneda (total de los ramos con prima)
        sens = []
        for p in marcas:
            ap = [r for r in ramos_ap if (p, r) in out["usd"]]
            if ap:
                sens.append(f"{p}: {sum(out['proy'][(c_b, p, r)] for r in ap) / 1e6:,.1f} en pesos contra "
                            f"{sum(out['usd'][(p, r)] for r in ap) / 1e6:,.1f} si fuera en dolares")
        out["sensibilidad"] = ("RFV BRUTO (M USD) de los ramos con RFV por prima, " + "; ".join(sens)
                               + ": la descomposicion se hace en pesos (MODELAR_EN_MXN) y el TC de Inversiones la "
                               "convierte; si la reserva se comportara como en dolares (prima y RFV en USD), no "
                               "bajaria con el TC") if sens else ""
    return out


def insumos_area_fianzas(info: dict, bd: BDMontos, ramos: list, per_hist: list[int], periodos_proy: list[int]):
    """Diagnostico de los insumos del area de Fianzas (info de calcular_rfv_prima, que se completa): por ramo y mes, el
    MA y su origen, OMEGA, ALFA, RFV MA, la RFV BRUTO de SAP en MXN y su parte de MA, el FACTOR MA, la PD del castigo
    y la PD de referencia de xDefault (pd_xdefault); la comision sobre utilidades (csu_fianzas) y la prima del
    proporcional de Mexico sin monto afianzado en el CSV (cobertura_ma). Agrega a info "insumos", "csu", "cobertura",
    "pdx", "texto_ma", "texto_pdx", "texto_csu" e "insumos_avisos"."""
    ma_info, seg = info.get("ma_info") or {}, info.get("com") or {}
    pdx = pd_xdefault(ramos, per_hist) if MA_RFV else {}
    csu = csu_fianzas(seg, ramos)
    cob = cobertura_ma(seg, ma_info, ramos)
    tc = info.get("tc_hist") or {}
    c_b = norm("RFV BRUTO")
    pd_h = (info.get("pdinfo") or {}).get("hist") or {}
    medido = (info.get("pdinfo") or {}).get("medido") or {}
    filas, avisos = [], list(csu.get("avisos") or [])
    for r in ramos:
        for p in list(per_hist) + list(periodos_proy):
            ma_p = (info.get("ma") or {}).get((p, r))
            if ma_p is None and p > per_hist[-1]:
                continue
            b = bd.valores.get((c_b, p, r), math.nan) * tc.get(p, math.nan) if p <= per_hist[-1] else math.nan
            rma = (info.get("rfv_ma") or {}).get((p, r), math.nan)
            filas.append({"Ramo": r, "Periodo": p, "Real o proyeccion": "real" if p <= per_hist[-1] else "proyeccion",
                          "Origen del MA": ma_p[1] if ma_p else "sin dato", "MA (MXN)": ma_p[0] if ma_p else math.nan,
                          "OMEGA": OMEGA_FIANZAS.get(str(r), math.nan), "ALFA": ALFA_FIANZAS.get(str(r), math.nan),
                          "RFV MA = MA x (OMEGA + ALFA) (MXN)": rma, "RFV BRUTO SAP (MXN)": b,
                          "RFV MA / RFV BRUTO": rma / b if np.isfinite(b) and b and np.isfinite(rma) else math.nan,
                          "MA aparte": "si" if r in (info.get("split") or ()) else "no (informativa)",
                          "FACTOR MA (constante del area, no se usa)": FACTOR_MA_FIANZAS.get(str(r), math.nan),
                          "PD del castigo (Res_Rvas)": pd_h.get((r, p), math.nan) if medido.get((r, p)) else math.nan,
                          **{f"PD xDefault {n} meses": (pdx.get("pd") or {}).get((n, str(r), p), math.nan)
                             for n in MESES_PD_XDEFAULT}})
    c_i = norm("RFV IRR")                              # una RFV de SAP que repite la del mes anterior (en MXN)
    for a, b_ in zip(per_hist, per_hist[1:]):
        rep = [r for r in ramos if all(
            np.isfinite(bd.valores.get((c, q, r), math.nan)) and bd.valores[(c, q, r)] > 0 for c in (c_b, c_i)
            for q in (a, b_))
            and all(abs(bd.valores[(c, b_, r)] * tc.get(b_, math.nan) / (bd.valores[(c, a, r)] * tc.get(a, math.nan)) - 1)
                    < 5e-4 for c in (c_b, c_i))]
        if rep:
            avisos.append(f"la RFV BRUTO e IRR de SAP de {b_} en pesos repiten las de {a} (difieren menos de 0.05 %) en "
                          f"{', '.join(rep)}: parece un mes sin actualizar"
                          + ("; en " + ", ".join(x for x in rep if x in (info.get("split") or ())) + " el FV residual de "
                             "ese mes cambia solo por el MA" if any(x in (info.get("split") or ()) for x in rep) else ""))
    info.update({"insumos": filas, "csu": csu, "cobertura": cob, "pdx": pdx, "insumos_avisos": avisos,
                 "texto_ma": ma_info.get("texto") or "", "texto_pdx": pdx.get("texto") or "",
                 "texto_csu": csu.get("texto") or ""})
    sin_ma = [f"{c['Ramo']}: {c['% sin MA']:.0%} ({c['Cedentes sin MA']})" for c in cob if c.get("% sin MA", 0) > 0.05]
    if sin_ma:
        info["insumos_avisos"].append("prima del proporcional de Mexico de cedentes sin monto afianzado en el CSV ("
                                      + "; ".join(sin_ma) + "): si SAP la reserva por monto afianzado, esa reserva queda "
                                      "en el FV residual; conviene confirmarlo con el area")


def calcular_backtesting_rfv(bd: BDMontos, pt: dict | None, ultimo: int, tc_hist: dict | None = None,
                             area: dict | None = None, ma_info: dict | None = None) -> dict:
    """BACKTESTING de Fianzas: la proyeccion de la BD de RFV con la historia cortada en el mes anterior a
    BACKTESTING_DESDE (mismas series y modelos, mismas identidades y la misma RFV por prima, con la misma prima de la
    proyeccion: la real en los meses reales), para los meses BACKTESTING_DESDE a BACKTESTING_HASTA. Con ma_info, el
    monto afianzado real conocido al corte (ma_hasta): en los meses de prueba, el ultimo MA real anterior al corte, fijo.
    Regresa lo mismo que
    calcular_backtesting: {"estado", "corte", "periodos", "proy", "indicadores": {(reserva, periodo, ramo): {bloque:
    valor}}, "aplica", "metodo", "alertas"}."""
    out = {"estado": "", "corte": None, "periodos": [], "proy": {}, "indicadores": {}, "aplica": set(), "metodo": {},
           "alertas": []}
    if not BACKTESTING:
        out["estado"] = "apagado (BACKTESTING = False)"
        return out
    desde, hasta = int(BACKTESTING_DESDE), int(BACKTESTING_HASTA)
    corte = _mes_menos(desde, 1)
    primero = min((p for (_, p) in bd.filas), default=None)
    if primero is None or hasta < desde or corte >= ultimo or corte < _mes_menos(primero, -(MIN_MESES_FRV - 1)):
        out["estado"] = (f"no se calcula: BACKTESTING_DESDE ({desde}) a BACKTESTING_HASTA ({hasta}) debe empezar despues de "
                         f"{MIN_MESES_FRV} meses de historia de la BD de RFV y antes del ultimo mes real ({ultimo})")
        return out
    per = rango_periodos(desde, hasta)
    h = len(per)
    bd_bt = replace(bd, filas={k: v for k, v in bd.filas.items() if k[1] <= corte},
                    valores={k: v for k, v in bd.valores.items() if k[1] <= corte}, filas_prima={}, filas_backtest={})
    tc_series = leer_tc_real(bd_bt, corte, "FIANZAS") if MODELAR_EN_MXN.get("FIANZAS") else None
    tc_hist = {**(tc_series or {}), **(tc_hist or {})}  # (el TC real de los meses reales del backtesting tambien)
    out["tc"] = {p: t for p, t in tc_hist.items() if p in per}
    series = series_montos(bd_bt, "FIANZAS", ESTRUCTURA["FIANZAS"], corte, h, tc_series)
    n_hist = len({p for (_, p) in bd_bt.filas})
    print(f"   Backtesting Fianzas: historia hasta {corte} ({n_hist} meses), {len(series)} series, meses {per[0]} a "
          f"{per[-1]} ...", flush=True)
    res = correr_series(series)
    proy = derivar_montos(bd_bt, "FIANZAS", ESTRUCTURA["FIANZAS"], res, per, en_mxn=tc_series is not None)
    pd_bt = (pd_fianzas({k: v for k, v in area.items() if k[1] <= corte}, bd_bt, tc_hist, list(bd.cols_ramo),
                        sorted({p for (_, p) in bd_bt.filas}), pt) if area else None)
    info = calcular_rfv_prima(bd_bt, proy, pt, per, corte, tc_hist, None, None, pd_bt, indicaciones=False,
                              ma_info=ma_hasta(ma_info, corte)) \
        if USAR_RFV_POR_PRIMA else \
        {"proy": proy, "aplica": set(), "frv": {}, "cesion": {}, "resumen": []}
    validar({}, info["proy"])
    out.update({"corte": corte, "periodos": per, "proy": {k: v for k, v in info["proy"].items() if k[1] in per},
                "aplica": set(info.get("aplica") or ())})
    motivos = {str(f["Ramo"]): f.get("Motivo") or "" for f in info.get("resumen") or []}
    c_b, c_i = norm("RFV BRUTO"), norm("RFV IRR")
    for r in bd.cols_ramo:
        out["metodo"][("RFV", r)] = ("RFV por prima" if any(x == r for _, x in out["aplica"])
                                     else f"modelo ({motivos.get(r) or 'sin RFV por prima'})")
        out["metodo"][("RCONT", r)] = "modelo (RCONT total repartido con la mezcla)"
        for p in per:
            s, _ = _prima_ventana(pt, r, p) if pt and pt.get("mensual") else (math.nan, False)
            b, i_ = out["proy"].get((c_b, p, r), math.nan), out["proy"].get((c_i, p, r), math.nan)
            t = tc_hist.get(p) or tc_para_periodo(bd, p)
            ind = {"PT": (pt or {}).get("mensual", {}).get((r, p), math.nan), "PRIMA": s,
                   "FRV": info["frv"].get((p, r), b * t / s if np.isfinite(b) and np.isfinite(s) and s else math.nan),
                   "CESION": info["cesion"].get((p, r), i_ / b if np.isfinite(i_) and np.isfinite(b) and b else
                                                (0.0 if np.isfinite(b) else math.nan))}
            ma_p = (info.get("ma") or {}).get((p, r))
            ind.update({"MA": ma_p[0] if ma_p else math.nan, "RMA": (info.get("rfv_ma") or {}).get((p, r), math.nan),
                        "OMEGA": OMEGA_FIANZAS.get(str(r), math.nan), "ALFA": ALFA_FIANZAS.get(str(r), math.nan),
                        "FMA": FACTOR_MA_FIANZAS.get(str(r), math.nan)})
            f_r = (info.get("factores") or {}).get(r)
            if f_r is not None:                        # (sin comisiones al corte: %SEG PR, %COM PR, FPR, PR, GA y FV
                ind.update({"PCARGAS": f_r["PCARGAS"], "PGA": f_r["PGA"], "PD": f_r["PD_P"],   # van en N/A)
                            "FCR": f_r["FCR_P"],
                            "RC": ind["CESION"] / f_r["FCR_P"] if np.isfinite(ind["CESION"]) and f_r["FCR_P"] else math.nan,
                            "RCP": _rc_prima(pt, r, p)})
            for pref in ("RFV", "RCONT"):
                out["indicadores"][(pref, p, r)] = ind
    n = len({r for _, r in out["aplica"]})
    out["split"] = set(info.get("split") or ())
    out["estado"] = (f"historia hasta {corte} ({n_hist} meses: indicativo); {per[0]} a {per[-1]} ({h} meses); "
                     + (f"{n} ramos con RFV por prima; misma prima que la proyeccion (la real en los meses reales)"
                        if n else "sin RFV por prima (" + ("USAR_RFV_POR_PRIMA = False" if not USAR_RFV_POR_PRIMA else
                                                           "sin prima de Fianzas" if not (pt or {}).get("mensual") else
                                                           "; ".join(f"{r}: {m_}" for r, m_ in motivos.items() if m_)
                                                           or "ningun ramo aplica") + "): solo el modelo de la serie")
                     + (f"; monto afianzado aparte en {', '.join(sorted(out['split'], key=int))} con el MA real conocido "
                        "al corte (fijo en los meses de prueba)" if out["split"] else "")
                     + "; RCONT con su modelo")
    return out


def escribir_pt_ramo(wb, pt: dict | None, ramos: list, periodos_bd=(), info: dict | None = None,
                     ultimo: int | None = None) -> dict | None:
    """Hoja HOJA_PT_RAMO de la BD de RFV: prima tomada del mes por ramo (MXN, valores, con su fuente) y PRIMA 24M (suma
    de los ultimos MESES_PRIMA_RFV meses) como formula, de todos los meses de la prima y de la BD; si hay prima cedida
    (pt["cedida"]), PC del mes y las sumas desde el primer mes de PT y de PC (para RC PRIMA); con FACTORES_RFV e info
    (de calcular_rfv_prima), los insumos editables de los factores, una celda por mes (y ramo): %SEG PR y %COM PR (los
    medidos desde su primer mes; en los meses despues de ultimo, los de la proyeccion), PD (medida o la ultima medida; en
    la proyeccion, la de la proyeccion), FV y RC proyectados (solo en los meses con RFV por prima), MA (monto
    afianzado del CSV del area; despues de su ultimo mes, ese ultimo), OMEGA, ALFA y FACTOR MA (constantes del area),
    %CARGAS, %GA y el origen del MA del mes. Los bloques de la BD los referencian. Regresa {"fila": {periodo: renglon},
    "pt", "suma", "pc", "pt_acum", "pc_acum", "seg", "com", "pd", "fv", "rc", "ma", "omega", "alfa", "fma": {ramo:
    letra}, "cargas", "ga": letra, "valor": {(clave, ramo, periodo): valor escrito}} o None sin prima."""
    if HOJA_PT_RAMO in wb.sheetnames:
        del wb[HOJA_PT_RAMO]
    if not pt or not pt.get("mensual"):
        return None
    ws = wb.create_sheet(HOJA_PT_RAMO)
    negrita = Font(bold=True)
    n = MESES_PRIMA_RFV
    todos = {p for _, p in pt["mensual"]} | set(periodos_bd)
    per = rango_periodos(min(todos), max(todos))
    ced = pt.get("cedida") or {}
    info = info or {}
    fac = (info.get("factores") or {}) if FACTORES_RFV else {}
    seg = info.get("com") or {}
    pdinfo = info.get("pdinfo") or {}
    p_seg = min(seg.get("meses") or [10 ** 6])
    ini = per[0]
    ws.cell(1, 1, f"Prima tomada (PT) de Fianzas del mes por ramo (MXN) y PRIMA {n}M = suma de los ultimos {n} meses. "
                  f"Fuentes: {pt.get('texto', '')}").font = negrita
    ws.cell(2, 1, f"Un mes que ninguna fuente trae va en 0 (FUENTE: sin prima). En los primeros {n - 1} meses de la hoja "
                  f"la suma lleva solo los meses que hay. La RFV por prima solo usa las sumas con sus {n} meses en alguna "
                  "fuente"
                  + (f". PC = prima cedida del mes (MXN; {pt.get('texto_cedida', '')}); un mes sin dato de cedida va en "
                     f"blanco y RC PRIMA solo usa las sumas desde {ini} con todos sus meses" if ced else "")
                  + (". Insumos de los factores de la RFV (se pueden cambiar; la BD los toma de aqui): %SEG PR y %COM PR "
                     f"(BDReal, desde {p_seg}; N/A antes), PD (Res_Rvas: CASTIGO / (IRR + CASTIGO) en los meses que "
                     "coinciden con SAP; en los demas, la ultima medida anterior), FV y RC proyectados (de los modelos del "
                     "FRV y de la cesion), MA (monto afianzado del proporcional de Mexico, MXN: "
                     + (((info.get("ma_info") or {}).get("texto") or "sin CSV del area") + "; despues de su ultimo mes, "
                        "ese ultimo, fijo; cambiarlo aqui es una sensibilidad: la hoja se rehace con el CSV en cada "
                        "corrida") + "), OMEGA y ALFA (indices del Anexo 5.15.3 del script del area), FACTOR MA "
                     "(constante del script del area, fija; no entra a ningun calculo), %CARGAS y %GA (parametros del "
                     "area)" if fac else ""))
    grupos = {"pt": "PT", "suma": f"PRIMA {n}M"}
    if ced:
        grupos.update({"pc": "PC", "pt_acum": f"PT DESDE {ini}", "pc_acum": f"PC DESDE {ini}"})
    if fac:
        grupos.update({"seg": "%SEG PR", "com": "%COM PR", "pd": "PD", "fv": "FV", "rc": "RC", "ma": "MA",
                       "omega": "OMEGA", "alfa": "ALFA", "fma": "FACTOR MA"})
    cols, c = {}, 3
    for g in grupos:
        cols[g] = {r: c + i for i, r in enumerate(ramos)}
        c += len(ramos)
    c_cargas = c if fac else None
    c_ga = c + 1 if fac else None
    c_esc = c + 2 if fac else None
    cab = ["PERIODO", "FUENTE"] + [f"{t} {r}" for g, t in grupos.items() for r in ramos] \
        + (["%CARGAS", "%GA", "ORIGEN DEL MA"] if fac else [])
    for k, t in enumerate(cab, start=1):
        ws.cell(3, k, t).font = negrita
    fmt = {"pt": "#,##0", "suma": "#,##0", "pc": "#,##0", "pt_acum": "#,##0", "pc_acum": "#,##0", "seg": "0.00%",
           "com": "0.00%", "pd": "0.000%", "fv": "0.0000", "rc": "0.00%", "ma": "#,##0", "omega": "0.00%",
           "alfa": "0.00%", "fma": "0.00"}
    ma_mes = info.get("ma") or {}
    filas, valor = {}, {}
    for i, p in enumerate(per):
        fila = 4 + i
        filas[p] = fila
        ws.cell(fila, 1, p)
        ws.cell(fila, 2, pt["fuente"].get(p, "sin prima (0)"))
        proy_mes = ultimo is not None and p > ultimo
        for r in ramos:
            def poner(g, v, _r=r):
                celda = ws.cell(fila, cols[g][_r], v)
                celda.number_format = fmt[g]
                if isinstance(v, str) and not v.startswith("="):
                    celda.alignment = Alignment(horizontal="right")
                valor[(g, _r, p)] = v
            poner("pt", float(pt["mensual"].get((r, p), 0.0)))
            le = get_column_letter(cols["pt"][r])
            poner("suma", f"=SUM({le}{max(4, fila - n + 1)}:{le}{fila})")
            if ced:
                v_ = ced.get((r, p))
                poner("pc", float(v_) if v_ is not None and np.isfinite(v_) else None)
                poner("pt_acum", f"=SUM({le}$4:{le}{fila})")
                lc = get_column_letter(cols["pc"][r])
                poner("pc_acum", f"=SUM({lc}$4:{lc}{fila})")
            if fac:
                f_r = fac.get(r) or {}
                sp, pc_ = f_r.get("SEG", math.nan), f_r.get("PCOM_P" if proy_mes else "PCOM", math.nan)
                poner("seg", float(sp) if p >= p_seg and np.isfinite(sp) else TEXTO_SIN_DATO)
                poner("com", float(pc_) if p >= p_seg and np.isfinite(pc_) else TEXTO_SIN_DATO)
                pd_ = f_r.get("PD_P", math.nan) if proy_mes else (pdinfo.get("hist") or {}).get((r, p), math.nan)
                poner("pd", float(pd_) if np.isfinite(pd_) else TEXTO_SIN_DATO)
                fv_, rc_ = (info.get("fv") or {}).get((p, r)), (info.get("rc") or {}).get((p, r))
                poner("fv", float(fv_) if fv_ is not None and (p, r) in info.get("aplica", ()) else None)
                poner("rc", float(rc_) if rc_ is not None and (p, r) in info.get("aplica", ()) else None)
                v_ma = (ma_mes.get((p, r)) or (math.nan,))[0]
                poner("ma", float(v_ma) if np.isfinite(v_ma) else TEXTO_SIN_DATO)
                for g_, dic_ in (("omega", OMEGA_FIANZAS), ("alfa", ALFA_FIANZAS), ("fma", FACTOR_MA_FIANZAS)):
                    v_ = dic_.get(str(r))
                    poner(g_, float(v_) if isinstance(v_, (int, float)) else TEXTO_SIN_DATO)
        if fac:
            ws.cell(fila, c_cargas, CARGAS_RFV).number_format = "0.000%"
            ws.cell(fila, c_ga, GASTO_ADMON_RFV).number_format = "0.000%"
            origenes = sorted({ma_mes[(p, r)][1] for r in ramos if (p, r) in ma_mes})
            ws.cell(fila, c_esc, ", ".join(origenes) if origenes else "sin dato")
    ws.freeze_panes = "C4"
    for k in range(1, len(cab) + 1):
        ws.column_dimensions[get_column_letter(k)].width = 16 if k > 2 else 12
    if fac:                                            # validacion de los insumos editables (en fraccion; FV >= 0)
        from openpyxl.worksheet.datavalidation import DataValidation
        ult = 3 + len(per)
        fraccion = DataValidation(type="decimal", operator="between", formula1="0", formula2="1", allow_blank=True,
                                  showErrorMessage=True, errorTitle="Factor de la RFV",
                                  error="En fraccion entre 0 y 1 (0.40 = 40 %)")
        positivo = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                                  showErrorMessage=True, errorTitle="Factor de la RFV",
                                  error="FV, MA y FACTOR MA no pueden ser negativos")
        for g in ("seg", "com", "pd", "rc", "omega", "alfa"):
            for r in ramos:
                le = get_column_letter(cols[g][r])
                fraccion.add(f"{le}4:{le}{ult}")
        for c_ in (c_cargas, c_ga):
            fraccion.add(f"{get_column_letter(c_)}4:{get_column_letter(c_)}{ult}")
        for g in ("fv", "ma", "fma"):
            for r in ramos:
                le = get_column_letter(cols[g][r])
                positivo.add(f"{le}4:{le}{ult}")
        ws.add_data_validation(fraccion)
        ws.add_data_validation(positivo)
    _agrupar(ws, [list(v.values()) for v in cols.values()])
    out = {"fila": filas, "valor": valor, "cargas": get_column_letter(c_cargas) if fac else None,
           "ga": get_column_letter(c_ga) if fac else None}
    for g in ("pt", "suma", "pc", "pt_acum", "pc_acum", "seg", "com", "pd", "fv", "rc", "ma", "omega", "alfa", "fma"):
        out[g] = {r: get_column_letter(x) for r, x in cols.get(g, {}).items()}
    return out


def escribir_bloques_rfv(bd: BDMontos, info: dict, hoja_pt: dict | None, periodos_proy: list[int],
                         solo_limpiar: bool = False) -> dict:
    """Bloques de la RFV por prima a la derecha de la hoja de montos de la BD de RFV, una columna por ramo, en todos los
    renglones (historia y proyeccion, de todos los conceptos), en el orden de bloques_rfv(): PT y PRIMA 24M (de la hoja
    HOJA_PT_RAMO), FRV y CESION y, con FACTORES_RFV, los factores de la metodologia del area: RC PRIMA, %SEG PR, %COM PR,
    %CARGAS, FPR, PR 24M, %GA, GA 24M, FV, PD, FCR y RC. Los insumos (%SEG PR, %COM PR, %CARGAS, %GA, PD y, en los meses
    con RFV por prima, FV y RC) son referencias a HOJA_PT_RAMO, una celda por mes y ramo, asi que cambiarlos ahi mueve los
    cuatro renglones del mes. En la historia (y en los meses sin RFV por prima): FRV = RFV BRUTO del mes x TC / PRIMA 24M,
    CESION = RFV IRR / RFV BRUTO, FV = RFV BRUTO x TC / (PR 24M + GA 24M) y RC = CESION / FCR como formulas (el monto del
    mes con SUMAR.SI.CONJUNTO por CONCEPTO y PERIODO fuera de su renglon). En los meses con RFV por prima: FRV = FPR x
    (1 + %GA) x FV y CESION = RC x FCR (sin el segmento del ramo, FRV y CESION proyectados en valores, como antes).
    FPR = %SEG PR x (1 - %COM PR - %CARGAS), PR 24M = PRIMA 24M x FPR, GA 24M = PR 24M x %GA, RC PRIMA = PC / PT desde el
    primer mes de la hoja y FCR = 1 - PD (1 sin PD) como formulas; N/A sin dato. MA, OMEGA, ALFA y FACTOR MA tambien son
    referencias a HOJA_PT_RAMO y RFV MA = MA x (OMEGA + ALFA); en los ramos con el monto afianzado aparte (info["split"]),
    FV = (RFV BRUTO x TC - RFV MA) / (PR 24M + GA 24M) en la historia y FRV = FPR x (1 + %GA) x FV + RFV MA / PRIMA 24M
    en la proyeccion. Cada referencia a la hoja va como SI(ESNUMERO(celda), celda, "N/A"): una celda borrada en PT_RAMO
    no se vuelve 0 en silencio. Los bloques de una corrida anterior se limpian (con solo_limpiar, solo eso: sin prima de
    Fianzas no se escriben). Regresa {(bloque, ramo): columna}."""
    ws = bd.ws
    ramos = list(bd.cols_ramo)
    bloques = bloques_rfv()
    nombres_todos = sorted({nombre_bloque_rfv(k) for k in BLOQUES_RFV_FACTORES} | {"%COM"}, key=len, reverse=True)
    patron = re.compile(r"^(" + "|".join(re.escape(x) for x in nombres_todos) + r"|PRIMA \d+M|PR \d+M|GA \d+M) (\S+)$")
    enc = {c: norm(ws.cell(3, c).value) for c in range(1, ws.max_column + 1) if ws.cell(3, c).value is not None}
    viejas = sorted(c for c, t in enc.items() if (m := patron.match(t)) and m.group(2) in ramos)
    fijas = [c for c in enc if c not in viejas]
    for c in viejas:
        for f in range(1, ws.max_row + 1):
            ws.cell(f, c).value = None
        if solo_limpiar:
            ws.cell(3, c).value = None
    if solo_limpiar:
        return {}
    _partir_columnas(ws)                               # (la BD de entrada trae rangos <col> de varias columnas)
    col_estilo = max(fijas)
    ancho = ws.column_dimensions[get_column_letter(next(iter(bd.cols_ramo.values())))].width
    modelo_frv = MODELO_POR_TIPO.get(TIPO_MODELO_FRV, TIPO_MODELO_FRV)
    modelo_ces = MODELO_POR_TIPO.get(TIPO_MODELO_FACTORES["CESION"], "")
    desde = f"; desde {periodos_proy[0]}, en los ramos con RFV por prima, " if periodos_proy else ""
    si_error = " (SI.ERROR: 0 si divide entre 0)"
    n = MESES_PRIMA_RFV
    pt_info = info.get("pt") or {}
    seg = info.get("com") or {}
    con_fv, con_rc = bool(info.get("fv")), bool(info.get("rc"))
    ult_pd = (info.get("pdinfo") or {}).get("ultimo") or {}
    split = set(info.get("split") or ())
    t_split = ", ".join(sorted(split, key=int))
    ma_info = info.get("ma_info") or {}
    hoja = f"hoja {HOJA_PT_RAMO}"
    descripcion = {
        "PT": f"PT = prima tomada de Fianzas del mes en MXN ({hoja}: PExRamo, reforecast y FCST; 0 si ninguna fuente la "
              "trae)",
        "PRIMA": f"PRIMA {n}M = suma de los ultimos {n} meses de PT en MXN ({hoja}): la prima que sostiene la reserva en "
                 "vigor",
        "RCP": (f"RC PRIMA = prima cedida / prima tomada desde {pt_info.get('inicio', '-')} ({hoja}: PmaCed de PExRamo): "
                "la RC de la metodologia aproximada con la cartera; informativa (el area la aplica contrato por contrato). "
                "N/A sin la cedida de todos los meses (el reforecast no la trae)" + si_error),
        "SEG": (f"%SEG PR = prima tomada del segmento de prima de reserva (extranjero proporcional y no proporcional) / "
                f"prima tomada del ramo ({hoja}; {seg.get('texto') or 'sin base del real con Fianzas'}); el resto se "
                "reserva por monto afianzado (omega + alfa del Anexo 5.15.3), que no esta en las bases. N/A antes del "
                "primer mes medido"),
        "PCOM": (f"%COM PR = comisiones / prima tomada del segmento de prima de reserva (CAT; {hoja}, misma base); no "
                 "incluye la comision sobre utilidades no pagada (bandera por contrato que no esta en las bases)"
                 + (f"; en la proyeccion, COMISION_RFV en {', '.join(indicaciones_rfv()[0])}" if indicaciones_rfv()[0]
                    else "; en la proyeccion, el mismo")),
        "PCARGAS": (f"%CARGAS = {CARGAS_RFV:.4%} de la prima tomada ({hoja}; parametro del area, %CargasPma: "
                    f"{GASTO_ADMON_RFV:.4%} de gasto de administracion mas {CARGAS_RFV - GASTO_ADMON_RFV:.4%} de costos "
                    "de cobertura y margen de utilidad)"),
        "FPR": "FPR = PR / PT = %SEG PR x (1 - %COM PR - %CARGAS): prima de reserva por cada peso de prima tomada del ramo",
        "PR": f"PR {n}M = PRIMA {n}M x FPR: prima de reserva de los ultimos {n} meses en MXN",
        "PGA": (f"%GA = GA / PR = {GASTO_ADMON_RFV:.4%} ({hoja}; parametro del area, %GastoAdmon, el alfa del segmento "
                "de prima de reserva)"),
        "GA": f"GA {n}M = PR {n}M x %GA: gastos de administracion de los ultimos {n} meses en MXN",
        "MA": (f"MA = monto afianzado del proporcional de Mexico (cuota parte y excedente de las cedentes) en MXN ({hoja}: "
               + (ma_info.get("texto") or "sin CSV del area") + f"); despues del ultimo mes del CSV "
               f"({ma_info.get('ultimo') or '-'}), ese ultimo, fijo (ningun insumo trae MA posterior). N/A sin dato"),
        "OMEGA": f"OMEGA = indice de reclamaciones del mercado del Anexo 5.15.3 (Omega del script del area; {hoja})",
        "ALFA": f"ALFA = indice anual de gastos de administracion alfa_k del Anexo 5.15.3 (FactorGastos del script del area; {hoja})",
        "RMA": ("RFV MA = MA x (OMEGA + ALFA) en MXN: la reserva del segmento de monto afianzado como la calcula el area"
                + (f"; en {t_split} va aparte (FV es el residual y FRV la suma); en los demas ramos es informativa y "
                   "queda dentro de FV" if split else "; informativa (queda dentro de FV)")),
        "FMA": (f"FACTOR MA = constante del script del area por ramo ({hoja}); fija como esta: el script no la usa en ningun "
                "calculo y aqui tampoco entra"),
        "FV": (f"FV = RFV BRUTO del mes x TC / (PR {n}M + GA {n}M): factor residual; reune la permanencia de la PR + GA "
               "(el area la mantiene mientras el contrato sigue en vigor), la reserva por monto afianzado del resto del "
               "ramo y el TC de valuacion de los contratos en otras monedas"
               + (f". En {t_split}: FV = (RFV BRUTO x TC - RFV MA) / (PR {n}M + GA {n}M), el resto: permanencia del "
                  "segmento de prima de reserva, facultativo, cedentes sin monto afianzado en el CSV, TC y diferencias "
                  "entre SAP y el calculo del area (N/A en los meses sin MA)" if split else "") + si_error
               + (desde + f"el FV proyectado ({hoja}: FRV {'residual ' if split else ''}del modelo / (FPR x (1 + %GA)), "
                  f"{modelo_frv})" if con_fv else "")),
        "FRV": (f"FRV = RFV BRUTO del mes x TC / PRIMA {n}M: factor de reserva, lo que queda constituido por cada peso de "
                f"prima de los ultimos {n} meses (en el renglon RFV BRUTO, su monto; en los demas, con "
                "SUMAR.SI.CONJUNTO)" + si_error
                + ((desde + "FRV = FPR x (1 + %GA) x FV" + (f" (en {t_split}, + RFV MA / PRIMA {n}M)" if split else "")
                    + " (formula; sin el segmento del ramo, el FRV proyectado en valor). "
                    f"RFV BRUTO = PRIMA {n}M x FRV / TC") if periodos_proy and con_fv else
                   (desde + f"el FRV proyectado ({modelo_frv}, {TIPO_MODELO_FRV}) (valor) en todos los renglones del "
                    f"mes. RFV BRUTO = PRIMA {n}M x FRV / TC" if periodos_proy else ""))),
        "PD": (f"PD = probabilidad de incumplimiento del reasegurador ({hoja}): CASTIGO / (IRR + CASTIGO) del calculo del "
               "area (Res_Rvas, Base FIANZAS) en los meses en que coincide con SAP; en los demas, la ultima medida "
               "anterior (despues del ultimo mes medido, esa: "
               + (f"{', '.join(f'{r}: {p}' for r, (p, _) in ult_pd.items())})" if ult_pd else "sin datos: N/A)")
               + (f"; en la proyeccion, PD_FIANZAS en {', '.join(indicaciones_rfv()[1])}" if indicaciones_rfv()[1] else "")),
        "FCR": "FCR = 1 - PD: factor de calidad del reaseguro (1 sin PD)",
        "RC": ("RC = CESION / FCR: proporcion cedida de la reserva con transferencia cierta" + si_error
               + (desde + f"la RC proyectada ({hoja}: CESION del modelo / FCR, {modelo_ces})" if con_rc else "")),
        "CESION": ("CESION = RFV IRR del mes / RFV BRUTO del mes (en el renglon IRR o BRUTO, su monto; en los demas, con "
                   "SUMAR.SI.CONJUNTO)" + si_error
                   + ((desde + "CESION = RC x FCR (formula). RFV IRR = RFV BRUTO x CESION y RFV NETO = RFV BRUTO x "
                       "(1 - CESION)") if periodos_proy and con_rc else
                      (desde + f"la cesion proyectada ({modelo_ces}) (valor). RFV IRR = RFV BRUTO x CESION y RFV NETO = "
                       "RFV BRUTO x (1 - CESION)" if periodos_proy else ""))),
    }
    faltan = [k for k in bloques if k not in descripcion]
    if faltan:
        raise KeyError(f"bloques de la RFV sin descripcion: {faltan}")
    cols, c = {}, max(fijas) + 1
    for clave in bloques:
        for r in ramos:
            cols[(clave, r)] = c
            _copiar_estilo(ws.cell(3, col_estilo), ws.cell(3, c))
            ws.cell(3, c).value = f"{nombre_bloque_rfv(clave)} {r}"
            if ancho:
                ws.column_dimensions[get_column_letter(c)].width = ancho
            c += 1
        c0 = cols[(clave, ramos[0])]
        ws.cell(2, c0).value = descripcion[clave]
        ws.cell(2, c0).font = Font(bold=True)
    c_conc, c_per, c_tc = (get_column_letter(x) for x in (bd.col_concepto, bd.col_periodo, bd.col_tc))
    ref_pt = _ref_hoja(HOJA_PT_RAMO)
    val_pt = (hoja_pt or {}).get("valor") or {}
    for (conc, p), fila in bd.filas.items():
        con_pt = bool(hoja_pt and p in hoja_pt["fila"])
        fpt = hoja_pt["fila"][p] if con_pt else None

        def ref(g, r, _f=fpt):                         # celda de la hoja PT_RAMO (un ramo o, sin r, una columna)
            letra = hoja_pt[g][r] if r is not None else hoja_pt[g]
            return f"={ref_pt}!${letra}${_f}"

        def gref(g, r, _f=fpt):                        # la misma, con guardia: vacia o texto -> N/A (no 0)
            celda = ref(g, r, _f)[1:]
            return f'=IF(ISNUMBER({celda}),{celda},"{TEXTO_SIN_DATO}")'

        def numero(g, r, _p=p):                        # el valor que lleva esa celda es un numero
            v = val_pt.get((g, r, _p))
            return isinstance(v, (int, float)) and np.isfinite(v)
        for r in ramos:
            ram = get_column_letter(bd.cols_ramo[r])

            def del_mes(concepto, _r=ram, _p=p, _f=fila):
                f_obj = bd.filas.get((norm(concepto), _p))
                if f_obj is None:
                    return None
                if f_obj == _f:
                    return f"{_r}{_f}"
                texto = str(ws.cell(f_obj, bd.col_concepto).value).strip().replace('"', '""')
                return f'SUMIFS(${_r}:${_r},${c_conc}:${c_conc},"{texto}",${c_per}:${c_per},${c_per}{_f})'
            L = {k: f"{get_column_letter(cols[(k, r)])}{fila}" for k in bloques}
            celdas = {k: ws.cell(fila, cols[(k, r)]) for k in bloques}
            vals = {}
            for k, celda in celdas.items():
                celda.number_format = FORMATO_BLOQUES_RFV[k]
            if con_pt:
                vals["PT"], vals["PRIMA"] = ref("pt", r), ref("suma", r)
            aplica = (p, r) in info.get("aplica", ())
            b, i_ = del_mes("RFV BRUTO"), del_mes("RFV IRR")
            if "SEG" in bloques and con_pt and hoja_pt.get("cargas"):
                vals["RCP"] = (f"=IFERROR({ref_pt}!${hoja_pt['pc_acum'][r]}${fpt}/{ref_pt}!${hoja_pt['pt_acum'][r]}${fpt},0)"
                               if hoja_pt.get("pc_acum") and np.isfinite(_rc_prima(pt_info, r, p)) else None)
                con_seg = numero("seg", r) and numero("com", r)
                # (los insumos siempre referencian PT_RAMO, aunque ahi digan N/A: si el area los llena, la BD los toma;
                # FPR, PR, GA y FV quedan en N/A mientras falte alguno)
                vals["SEG"], vals["PCOM"] = gref("seg", r), gref("com", r)
                vals["PCARGAS"], vals["PGA"] = gref("cargas", None), gref("ga", None)
                vals["FPR"] = (f"=IF(AND(ISNUMBER({L['SEG']}),ISNUMBER({L['PCOM']}),ISNUMBER({L['PCARGAS']})),"
                               f"{L['SEG']}*(1-{L['PCOM']}-{L['PCARGAS']}),\"{TEXTO_SIN_DATO}\")")
                vals["PR"] = f"=IF(ISNUMBER({L['FPR']}),{L['PRIMA']}*{L['FPR']},\"{TEXTO_SIN_DATO}\")"
                vals["GA"] = (f"=IF(AND(ISNUMBER({L['PR']}),ISNUMBER({L['PGA']})),{L['PR']}*{L['PGA']},"
                              f"\"{TEXTO_SIN_DATO}\")")
                vals["PD"] = gref("pd", r)
                vals["FCR"] = f"=IF(ISNUMBER({L['PD']}),1-{L['PD']},1)"
                vals["MA"], vals["OMEGA"], vals["ALFA"] = gref("ma", r), gref("omega", r), gref("alfa", r)
                vals["FMA"] = gref("fma", r)
                vals["RMA"] = (f"=IF(AND(ISNUMBER({L['MA']}),ISNUMBER({L['OMEGA']}),ISNUMBER({L['ALFA']})),"
                               f"{L['MA']}*({L['OMEGA']}+{L['ALFA']}),\"{TEXTO_SIN_DATO}\")")
                if aplica and numero("fv", r) and con_seg:
                    vals["FV"] = gref("fv", r)
                    vals["FRV"] = (f"={L['FPR']}*(1+{L['PGA']})*{L['FV']}"
                                   + (f"+{L['RMA']}/{L['PRIMA']}" if r in split else ""))
                elif r in split:                       # (FV residual: sin la reserva por monto afianzado)
                    vals["FV"] = (f"=IF(AND(ISNUMBER({L['PR']}),ISNUMBER({L['RMA']})),IFERROR(({b}*${c_tc}{fila}"
                                  f"-{L['RMA']})/({L['PR']}+{L['GA']}),0),\"{TEXTO_SIN_DATO}\")" if b else None)
                else:
                    vals["FV"] = (f"=IF(ISNUMBER({L['PR']}),IFERROR({b}*${c_tc}{fila}/({L['PR']}+{L['GA']}),0),"
                                  f"\"{TEXTO_SIN_DATO}\")" if b else None)
                if aplica and numero("rc", r):
                    vals["RC"] = gref("rc", r)
                    vals["CESION"] = f"={L['RC']}*{L['FCR']}"
                else:
                    vals["RC"] = f"=IFERROR({L['CESION']}/{L['FCR']},0)" if b and i_ else None
            if aplica:
                vals.setdefault("FRV", float(info["frv"][(p, r)]))
                vals.setdefault("CESION", float(info["cesion"][(p, r)]))
            else:
                vals.setdefault("FRV", f"=IFERROR({b}*${c_tc}{fila}/{L['PRIMA']},0)" if b and con_pt else None)
                vals.setdefault("CESION", f"=IFERROR({i_}/{b},0)" if b and i_ else None)
            for k, celda in celdas.items():
                v = vals.get(k)
                if v is None:
                    celda.value = TEXTO_SIN_DATO
                    celda.alignment = Alignment(horizontal="right")
                else:
                    celda.value = v
    fin = max(cols.values())
    if ws.auto_filter and ws.auto_filter.ref:
        ini, fin_ref = ws.auto_filter.ref.split(":")
        fila_fin = re.match(r"[A-Z]+(\d+)", fin_ref).group(1)
        ws.auto_filter.ref = f"{ini}:{get_column_letter(fin)}{fila_fin}"
    for c in viejas:
        if c > fin:
            ws.cell(3, c).value = None
    _agrupar(ws, [[bd.cols_ramo[r] for r in ramos]] + [[cols[(k, r)] for r in ramos] for k in bloques])
    return cols


def escribir_rfv_prima(bd: BDMontos, info: dict, cols: dict):
    """En los meses con RFV por prima, las celdas RAM_ de RFV BRUTO, RFV IRR y RFV NETO van como formulas que solo usan
    celdas de su propio renglon (PRIMA 24M, FRV, CESION y TC), para que la hoja se pueda ordenar y filtrar:
    RFV BRUTO = PRIMA 24M x FRV / TC; RFV IRR = RFV BRUTO x CESION; RFV NETO = RFV BRUTO x (1 - CESION)."""
    ws = bd.ws
    c_tc = get_column_letter(bd.col_tc)
    for (p, r) in sorted(info.get("aplica") or ()):
        ram = get_column_letter(bd.cols_ramo[r])
        for conc in ("RFV BRUTO", "RFV IRR", "RFV NETO"):
            f = bd.filas.get((norm(conc), p))
            if not f:
                continue
            L = {k: f"{get_column_letter(cols[(k, r)])}{f}" for k in ("PRIMA", "FRV", "CESION")}
            bruto = f"{L['PRIMA']}*{L['FRV']}/${c_tc}{f}"
            ws[f"{ram}{f}"] = "=" + {"RFV BRUTO": bruto, "RFV IRR": f"{bruto}*{L['CESION']}",
                                     "RFV NETO": f"{bruto}*(1-{L['CESION']})"}[conc]


def _diag_pnd_bd_final(diag: dict, proy_modelo: dict, proy_final: dict, ramos: list, periodos_proy: list[int]):
    """Tras el BEL por FND, las columnas 'BD principal' del diagnostico PND (calculadas con el modelo) pasan a 'Modelo
    (antes del BEL por FND)' y 'BD principal' toma los montos que lleva la BD."""
    etiqueta = "Modelo (antes del BEL por FND)"

    def v(dic, pref, conc, p, r):
        return dic.get((norm(f"{pref} {conc}"), p, r), math.nan)
    for f in diag.get("totales") or []:
        pref, conc = f["Reserva"].split(" ", 1)
        for k in [k for k in f if k.startswith("BD principal ")]:
            p = int(k.rsplit(" ", 1)[1])
            f[k.replace("BD principal", etiqueta)] = f.pop(k)
            f[k] = float(sum(x for x in (v(proy_final, pref, conc, p, r) for r in ramos) if np.isfinite(x)))
    for f in diag.get("resumen") or []:
        for k in [k for k in f if " BD principal " in k]:
            conc, p = k.split(" BD principal ")[0], int(k.rsplit(" ", 1)[1])
            f[k.replace("BD principal", etiqueta)] = f.pop(k)
            f[k] = v(proy_final, f["Reserva"], conc, p, f["Ramo"])
    for f in diag.get("mensual") or []:
        if "BEL BD principal" in f:
            f[f"BEL {etiqueta}"] = f.pop("BEL BD principal")
            f["BEL BD principal"] = v(proy_final, f["Reserva"], "BEL", f["Periodo"], f["Ramo"])


def _pe_hoja(pe: dict, ramos: list, periodos: list) -> tuple[dict, dict]:
    """PE y PRIMA N AÑOS como las calcula la hoja HOJA_PE_RAMO: un mes que ninguna fuente trae va en 0 y la suma de los
    ultimos MESES_PRIMA_N_ANOS meses se recorta al inicio de la hoja. Regresa ({(ramo, periodo): PE},
    {(ramo, periodo): suma}) para todos los ramos y meses de la hoja."""
    val, suma = {}, {}
    for r in ramos:
        xs = [float(pe[(r, p)][0]) if (r, p) in pe else 0.0 for p in periodos]
        for i, p in enumerate(periodos):
            val[(r, p)] = xs[i]
            suma[(r, p)] = float(sum(xs[max(0, i - MESES_PRIMA_N_ANOS + 1): i + 1]))
    return val, suma


def escribir_pe_ramo(wb, pe: dict, ramos: list, periodos_bd=()) -> dict | None:
    """Hoja HOJA_PE_RAMO: PE del mes por ramo (valores, con su fuente) y PRIMA N AÑOS (suma de los ultimos
    MESES_PRIMA_N_ANOS meses) como formula, para todos los ramos y todos los meses de la PE y de la BD (periodos_bd): un
    mes que ninguna fuente trae va en 0. Regresa {"fila": {periodo: renglon}, "pe": {ramo: letra}, "p12": {ramo: letra},
    "val": {(ramo, periodo): PE de la hoja}, "suma": {(ramo, periodo): PRIMA N AÑOS de la hoja}} o None sin PE."""
    for vieja in (HOJA_PE_FCST, HOJA_PE_RAMO):
        if vieja in wb.sheetnames:
            del wb[vieja]
    if not pe:
        return None
    ws = wb.create_sheet(HOJA_PE_RAMO)
    negrita = Font(bold=True)
    todos = {p for _, p in pe} | set(periodos_bd)
    per = rango_periodos(min(todos), max(todos))
    val, suma = _pe_hoja(pe, ramos, per)
    fuentes = sorted({f for _, f in pe.values()})
    ws.cell(1, 1, f"Prima tomada (PE) del mes por ramo (USD) y PRIMA N AÑOS = suma de los ultimos {MESES_PRIMA_N_ANOS} "
                  f"meses. Fuente: {', '.join(fuentes)}").font = negrita
    ws.cell(2, 1, f"Un mes que ninguna fuente trae va en 0 (la columna FUENTE dice en que ramos). En los primeros "
                  f"{MESES_PRIMA_N_ANOS - 1} meses de la hoja la suma lleva solo los meses que hay. El BEL por FND solo "
                  f"usa las sumas con sus {MESES_PRIMA_N_ANOS} meses en alguna fuente")
    cab = ["PERIODO", "FUENTE"] + [f"PE {r}" for r in ramos] + [f"PRIMA N AÑOS {r}" for r in ramos]
    for k, t in enumerate(cab, start=1):
        ws.cell(3, k, t).font = negrita
    c_pe = {r: 3 + i for i, r in enumerate(ramos)}
    c_12 = {r: 3 + len(ramos) + i for i, r in enumerate(ramos)}
    filas = {}
    for i, p in enumerate(per):
        fila = 4 + i
        filas[p] = fila
        ws.cell(fila, 1, p)
        sin = [str(r) for r in ramos if (r, p) not in pe]
        ws.cell(fila, 2, ", ".join(sorted({pe[(r, p)][1] for r in ramos if (r, p) in pe}))
                + (("; " if len(sin) < len(ramos) else "") + f"sin PE (0): {', '.join(sin)}" if sin else ""))
        for r in ramos:
            ws.cell(fila, c_pe[r], val[(r, p)]).number_format = "#,##0"
            le = get_column_letter(c_pe[r])
            ws.cell(fila, c_12[r], f"=SUM({le}{max(4, fila - MESES_PRIMA_N_ANOS + 1)}:{le}{fila})").number_format = "#,##0"
    ws.freeze_panes = "C4"
    for k in range(1, len(cab) + 1):
        ws.column_dimensions[get_column_letter(k)].width = 15 if k > 2 else 12
    _agrupar(ws, [list(c_pe.values()), list(c_12.values())])
    return {"fila": filas, "pe": {r: get_column_letter(c) for r, c in c_pe.items()},
            "p12": {r: get_column_letter(c) for r, c in c_12.items()}, "val": val, "suma": suma}


def escribir_is_fa(wb, is_fa: dict | None) -> dict | None:
    """Hoja HOJA_IS_FA con la tabla del archivo de la funcion actuarial tal cual (valores). Regresa {(reserva, ramo,
    periodo): referencia absoluta a la celda del indice} (la del renglon que se usa: el primero de ese ramo y mes con
    dato) o None sin archivo."""
    if HOJA_IS_FA in wb.sheetnames:
        del wb[HOJA_IS_FA]
    if not is_fa:
        return None
    ws = wb.create_sheet(HOJA_IS_FA)
    negrita = Font(bold=True)
    ws.cell(1, 1, f"Indices de siniestralidad de la funcion actuarial: {is_fa['ruta'].name} › {is_fa['hoja']}, tal "
                  "cual" + (f" (sin {is_fa['omitidos']} renglon(es) sin Ramo o MesProc validos; ver Alertas)"
                            if is_fa.get("omitidos") else "")
                  + ". El bloque IS (FA) de la hoja de montos toma " + " y ".join(
                      f"{c} en los renglones de {p}" for p, c in COLUMNA_IS_FA.items())).font = negrita
    ws.cell(2, 1, f"En el bloque va {TEXTO_SIN_DATO} en los meses y ramos que no vienen aqui; si un ramo y mes se "
                  "repite, se usa el primer renglon")
    for k, t in enumerate(is_fa["cab"], start=1):
        ws.cell(3, k, t).font = negrita
    enc = [norm(x) for x in is_fa["cab"]]
    j = {"ramo": enc.index("RAMO"), "mes": enc.index("MESPROC"),
         **{p: enc.index(norm(c)) for p, c in COLUMNA_IS_FA.items()}}
    ref, hoja = {}, _ref_hoja(HOJA_IS_FA)
    for i, f in enumerate(is_fa["tabla"]):
        fila = 4 + i
        for k, x in enumerate(f, start=1):
            c = ws.cell(fila, k, x)
            if k - 1 in [j[p] for p in COLUMNA_IS_FA] or (isinstance(x, float) and "IS" in enc[k - 1]):
                c.number_format = "0.00%"
        clave = (str(int(f[j["ramo"]])), int(f[j["mes"]]))
        for p in COLUMNA_IS_FA:
            if isinstance(f[j[p]], (int, float)) and not isinstance(f[j[p]], bool) and np.isfinite(f[j[p]]):
                ref.setdefault((p,) + clave, f"{hoja}!${get_column_letter(j[p] + 1)}${fila}")
    ws.freeze_panes = "A4"
    for k in range(1, len(is_fa["cab"]) + 1):
        ws.column_dimensions[get_column_letter(k)].width = 16
    return ref


def _ref_hoja(nombre: str) -> str:
    return nombre if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nombre) else f"'{nombre}'"


def escribir_indices_pnd(bd: BDMontos, ctx: dict, avisos: list | None = None) -> dict:
    """Escribe los indicadores por ramo a la derecha de la hoja de montos: un bloque por indicador de
    COLUMNAS_INDICES_PND con una columna por ramo (encabezado "<indicador> <ramo>" en el renglon 3, que no empieza con
    RAM_, y el nombre del bloque en el renglon 2), despues de las columnas propias de la BD. Si la BD de entrada ya traia
    bloques (de cualquier version), se limpian y se vuelven a escribir; sus datos de captura se conservan. Todos los
    bloques van en todos los renglones de RRC y SONR (historia y proyeccion), aunque el modelo no los use, como formulas
    sencillas (=J33/BZ33); las divisiones con SI.ERROR (IFERROR) para dejar 0 en un 0/0, un mes sin PE es 0 y sin IS,
    sin LAG o sin BEL (los meses de prima sin montos, bd.filas_prima, que tambien llevan los bloques) va TEXTO_SIN_DATO
    en ese dato y en lo que se calcula con el. El renglon 2 describe cada bloque.
    ctx: hp, resultados, periodos_proy, ultimo, proy (montos proyectados de este archivo), pe (pe_por_mes), hoja_pe
    (escribir_pe_ramo), primas_pe (escribir_primas_pe), pe_tab y meses_pe (PE de Primas_PE para el FA), fnd ({(reserva,
    periodo, ramo): FND proyectado} solo en la BD principal), registro (solo en la BD principal: dict que se llena con
    {(reserva, ramo, periodo): {indicador: valor del renglon BEL}} de los meses de la BD, para el tablero). Regresa
    {(indicador, ramo): columna}."""
    ws = bd.ws
    hp, resultados, periodos_proy, ultimo = ctx["hp"], ctx["resultados"], ctx["periodos_proy"], ctx["ultimo"]
    proy, pe, hoja_pe, fnd = ctx["proy"], ctx.get("pe") or {}, ctx.get("hoja_pe"), ctx.get("fnd") or {}
    razones = ctx.get("razones") or {}             # FACTOR GTO, FACTOR MR y CESION proyectados (BEL por FND)
    is_fa_bel = ctx.get("is_fa_bel") or set()        # (reserva, periodo, ramo) cuyo BEL y PND / PD usan el IS (FA)
    is_fa = ctx.get("is_fa") or {}                 # {"val": {(reserva, ramo, periodo): IS}, "ref": {...: celda}, ...}
    is_fa_val, is_fa_ref = is_fa.get("val") or {}, is_fa.get("ref") or {}
    registro = ctx.get("registro")                 # {(reserva, ramo, periodo): {indicador: valor}} para el tablero
    filas_bd = set(bd.filas.values())              # (sin los meses de prima anteriores a la BD)
    primas_pe, pe_tab, meses_pe = ctx.get("primas_pe"), ctx.get("pe_tab") or {}, ctx.get("meses_pe")
    pos = {p: i for i, p in enumerate(periodos_proy)}
    formulas = INDICES_PND_FORMULAS and hp is not None and getattr(hp, "filas", None)
    todos = list(COLUMNAS_INDICES_PND) + list(INDICES_PND_RETIRADOS)
    ramos = list(bd.cols_ramo)
    enc = {norm(ws.cell(3, c).value): c for c in range(1, ws.max_column + 1) if ws.cell(3, c).value}
    de_bloque = ({norm(f"{i} {r}") for i in todos for r in ramos} | {norm(i) for i in todos}
                 | {norm(f"{i} RAMO") for i in todos})   # (un encabezado "IS (FA) RAMO" escrito a mano es del bloque)
    fijas = [c for n, c in enc.items() if n not in de_bloque]
    viejas = sorted(c for n, c in enc.items() if n in de_bloque)
    for n, c in enc.items():                           # encabezado "<indicador> RAMO" escrito a mano: se limpia
        if n in {norm(f"{i} RAMO") for i in todos}:
            k = sum(1 for f in range(4, ws.max_row + 1) if ws.cell(f, c).value not in (None, ""))
            if k and avisos is not None:
                ind_ = str(ws.cell(3, c).value).strip()[:-len("RAMO")].strip()
                captura_ = next((i for i in INDICES_PND_CAPTURA if norm(i) == norm(ind_)), None)
                avisos.append(f"La columna '{ws.cell(3, c).value}' (encabezado sin numero de ramo) traia {k} dato(s); "
                              "se toma como parte de los bloques y se limpia; "
                              + (f"para capturar, usa la columna del ramo (p. ej. '{captura_} 60')" if captura_ else
                                 "ese bloque se llena solo (no lleva captura)"))
    # capturas de la BD de entrada (columnas "<indicador> <ramo>" de los datos de captura), antes de limpiar
    capturas = {}
    for ind in INDICES_PND_CAPTURA:
        for r in ramos:
            c = enc.get(norm(f"{ind} {r}"))
            if c is not None:
                for f in bd.filas_entrada:
                    v = ws.cell(f, c).value
                    if v is not None and v != "":
                        capturas[(ind, r, f)] = v
        c = enc.get(norm(ind))
        n = 0 if c is None else sum(1 for f in range(4, ws.max_row + 1) if isinstance(ws.cell(f, c).value, (int, float))
                                    and not isinstance(ws.cell(f, c).value, bool))
        if n and avisos is not None:
            avisos.append(f"La columna '{ws.cell(3, c).value}' (sin ramo) traia {n} dato(s) de captura; los bloques por "
                          f"ramo la reemplazan. Captura en la columna del ramo (p. ej. '{ind} 60') de la BD de entrada")
    retirados = {}                                     # datos en bloques que ya no se usan: se descartan con aviso
    for ind in INDICES_PND_RETIRADOS:
        for cab_ in [ind] + [f"{ind} {r}" for r in ramos]:
            c = enc.get(norm(cab_))
            n = 0 if c is None else sum(1 for f in bd.filas_entrada if ws.cell(f, c).value not in (None, ""))
            if n:
                retirados[ind] = retirados.get(ind, 0) + n
    if retirados and avisos is not None:
        avisos.append("La BD de entrada traia datos en bloques que ya no se usan; se descartan: "
                      + ", ".join(f"{k} ({n})" for k, n in retirados.items()))
    for c in viejas:                                   # se limpian los bloques que traia la BD (se escriben de nuevo)
        for f in range(1, ws.max_row + 1):
            ws.cell(f, c).value = None
    _partir_columnas(ws)                               # (al agrupar no deben quedar rangos <col> encimados)
    usa_primas = bool(pe_tab)          # FA contra la PE del grupo (Primas_PE); sin ella, contra PRIMA N AÑOS del ramo
    anios_sonr = ANIOS_LAG_PEACUMULADA.get("SONR", 0)
    peac_sonr = " + ".join(["LAG 1 x PRIMA N AÑOS del mes"] + [f"LAG {k} x la de {12 * (k - 1)} meses antes"
                                                                for k in range(2, anios_sonr + 1)])
    si_error = " (SI.ERROR: 0 si divide entre 0)"
    claves_hp = ", ".join(f"{r} -> {k}" for r, k in MAPA_RAMO_LAG.items() if str(r) != str(k) and r in ramos)
    na_pnd = f"; {TEXTO_SIN_DATO} si PND/PD es {TEXTO_SIN_DATO}"
    def _proy_fac(nombre):
        if not (razones and periodos_proy):
            return ""
        if nombre in FACTORES_BEL_FIJOS:
            return (f"; desde {min(periodos_proy)}, en las series con BEL por FND, el ultimo real ({ultimo}) fijo "
                    "(FACTORES_BEL_FIJOS, indicacion del area; un real negativo se fija en 0) (valor) en todos los "
                    "renglones del mes")
        modelo_f = MODELO_POR_TIPO.get(TIPO_MODELO_FACTORES.get(nombre, ""), "")
        como = ("el nivel suavizado de los ultimos meses (SES), sin tendencia" if modelo_f == "SES" else
                "la pendiente combinada en logaritmos" + (" con el patron del mes" if TIPO_MODELO_FACTORES.get(nombre) in
                                                          TIPOS_CON_ESTACIONALIDAD else ", sin patron del mes")
                if modelo_f == TENDENCIA else modelo_f)
        return (f"; desde {min(periodos_proy)}, en las series con BEL por FND, {como} (valor) en todos los renglones del mes"
                + (_nota_cesion_area() if nombre == "CESION" else ""))
    ramos_fa_bel = "; ".join(f"{k} {', '.join(v)}" for k, v in RAMOS_IS_FA_BEL.items() if v)
    bel_area = ctx.get("bel_area") or {}           # {(reserva, ramo): ...} series con la historia del metodo del area
    nota_area = "".join(f"; {pr_} {r_}: SAP no registra BEL, el valor proyectado sale de la historia del metodo del area "
                        f"({d_['desde']} a {d_['hasta']}, Res_Rvas; BEL_METODO_AREA, ver BEL_FND_Resumen del diagnostico)"
                        for (pr_, r_), d_ in sorted(bel_area.items())) if periodos_proy else ""
    descripcion = {
        "PND/PD": ("PND/PD = BEL / IS (RL): en el renglon BEL, BEL del renglon / IS; en los demas renglones, el BEL del mes "
                   "con SUMAR.SI.CONJUNTO por CONCEPTO y PERIODO (ninguna formula apunta a otro renglon: la hoja se puede "
                   "ordenar y filtrar)" + si_error + f"; {TEXTO_SIN_DATO} sin IS o sin BEL (meses de prima sin montos)"
                   + (f"; en los ramos {ramos_fa_bel}, desde el primer mes proyectado con BEL por FND, BEL / IS (FA) "
                      "(RAMOS_IS_FA_BEL)" if ramos_fa_bel else "")),
        "FA": ((f"FA = PND/PD / PE de {meses_pe} meses del grupo (hoja {HOJA_PRIMAS_PE})" if formulas and primas_pe else
                f"FA = PND/PD / PE de {meses_pe} meses del grupo (prima de primas.py; la hoja {HOJA_PRIMAS_PE} solo se "
                "agrega con formulas)") if usa_primas else
               "FA = PND/PD / PRIMA N AÑOS del ramo (sin hoja " + f"{HOJA_PRIMAS_PE}: la prima del proyecto no esta "
               "completa)") + si_error + na_pnd,
        "FACTOR GTO": ("FACTOR GTO = GTO del mes / PND/PD (en el renglon RRC GTO, su monto; en los demas, con "
                       "SUMAR.SI.CONJUNTO); SONR no tiene GTO: 0" + si_error + na_pnd + _proy_fac("FACTOR GTO")),
        "FACTOR MR": ("FACTOR MR = MR del mes / PND/PD (en el renglon MR de la reserva, su monto; en los demas, con "
                      "SUMAR.SI.CONJUNTO)" + si_error + na_pnd + _proy_fac("FACTOR MR") + nota_area),
        "CESION": ("CESION = IRR del mes / BRUTO del mes (razon de cesion; en el renglon IRR o BRUTO, su monto; en los "
                   "demas, con SUMAR.SI.CONJUNTO)" + si_error + f"; {TEXTO_SIN_DATO} sin montos (meses de prima)"
                   + _proy_fac("CESION") + nota_area),
        "IS (RL)": f"IS (RL) = {' / '.join(v[0] for v in INDICE_BASE_PND.values())} de {HOJA_PARAMETROS} del mes (real o "
                   f"proyectado; {TEXTO_SIN_DATO} si no hay; ramo de la hoja segun MAPA_RAMO_LAG: {claves_hp})",
        "LAG (RL)": f"LAG (RL) = LAG 1 de {HOJA_PARAMETROS} del mes (real o proyectado; {TEXTO_SIN_DATO} si no hay)",
        "PE FCST": (f"PE FCST = prima tomada del mes (hoja {HOJA_PE_RAMO}; 0 si ninguna fuente la trae; se puede capturar "
                    "en el renglon BEL de la BD de entrada)") if pe else (
            f"PE FCST: {TEXTO_SIN_DATO} en esta corrida porque no se leyo ninguna prima por ramo (la base "
            f"{PATRON_PE_RAMO} ni el FCST {ARCHIVO_PE_FCST.name} de entradas/; el motivo esta en Alertas del diagnostico)"),
        "PRIMA N AÑOS": f"PRIMA N AÑOS = suma de los ultimos {MESES_PRIMA_N_ANOS} meses de PE (hoja {HOJA_PE_RAMO})"
                        + ("" if pe else f"; {TEXTO_SIN_DATO}: sin prima por ramo en esta corrida"),
        "PEACUMULADA": "PEACUMULADA: RRC = PRIMA N AÑOS" + (f"; SONR = {peac_sonr} (LAG de {HOJA_PARAMETROS}; "
                                                            f"{TEXTO_SIN_DATO} si el mes no trae LAG)"
                                                            if anios_sonr else "")
                       + ("" if pe else f"; {TEXTO_SIN_DATO}: sin prima por ramo en esta corrida"),
        "IS (FA)": (f"IS (FA) = indice de siniestralidad de la funcion actuarial (hoja {HOJA_IS_FA}, de "
                    f"{is_fa['archivo']}): " + "; ".join(f"{c} en los renglones de {p}" for p, c in COLUMNA_IS_FA.items())
                    + f"; {TEXTO_SIN_DATO} en los meses y ramos que no trae"
                    + (f" (trae {is_fa['periodos'][0]} a {is_fa['periodos'][-1]}; sin ramos "
                       f"{', '.join(r for r in ramos if r not in is_fa['ramos'])})"
                       if is_fa.get("periodos") and any(r not in is_fa["ramos"] for r in ramos) else
                       (f" (trae {is_fa['periodos'][0]} a {is_fa['periodos'][-1]})" if is_fa.get("periodos") else ""))
                    + ". El BEL por FND y el PND / PD de los ramos " + ", ".join(
                        f"{k}: {', '.join(v)}" for k, v in RAMOS_IS_FA_BEL.items() if v)
                    + " lo usan desde el primer mes proyectado (RAMOS_IS_FA_BEL); los demas ramos usan el IS (RL)")
                   if is_fa_val else (
            f"IS (FA): {TEXTO_SIN_DATO} en esta corrida porque no se leyo el archivo de la funcion actuarial "
            f"({PATRON_IS_FA} en entradas/; el motivo esta en Alertas del diagnostico)"),
        "FD/FND": "FD/FND = PND/PD / PEACUMULADA" + si_error + (
            f"; desde {min(periodos_proy)}, en las series con BEL por FND, el FND proyectado (valor) en todos los renglones "
            "del mes"
            if fnd and periodos_proy else "") + f"; {TEXTO_SIN_DATO} si PND/PD o PEACUMULADA son {TEXTO_SIN_DATO}"
                  + nota_area
                  + "".join(f"; {pr_} {r_}: el FND de los meses entre diciembres se ajusta para suavizar el BEL "
                            f"(SUAVIZAR_BEL: {d_['texto']})" for (pr_, r_), d_ in sorted((ctx.get("suavizado") or {}).items())),
    }
    col_estilo = max(fijas)
    col_ramo = next(iter(bd.cols_ramo.values()))
    ancho = ws.column_dimensions[get_column_letter(col_ramo)].width
    cols, c = {}, max(fijas) + 1
    for ind in COLUMNAS_INDICES_PND:
        for r in ramos:
            cols[(ind, r)] = c
            _copiar_estilo(ws.cell(3, col_estilo), ws.cell(3, c))
            ws.cell(3, c).value = f"{ind} {r}"
            if ancho:
                ws.column_dimensions[get_column_letter(c)].width = ancho
            c += 1
        c0 = cols[(ind, ramos[0])]
        ws.cell(2, c0).value = descripcion.get(ind, ind)
        ws.cell(2, c0).font = Font(bold=True)
    hoja_hp = _ref_hoja(HOJA_PARAMETROS)

    def L(ind, r):
        return get_column_letter(cols[(ind, r)])

    def ref_hp(r_hp, nombre, periodo):
        f = hp.filas.get((r_hp, periodo))
        if f is None:
            return None
        ref = f"{hoja_hp}!${get_column_letter(hp.cols[nombre])}${f}"     # (absoluta: se puede ordenar la hoja)
        if isinstance(hp.ws.cell(f, hp.cols[nombre]).value, str):
            ref = f'VALUE(SUBSTITUTE({ref},CHAR(160),""))'
        return ref

    def expr_hp(r_hp, nombre, fuente):
        """Formula del indice o LAG segun su fuente (_hp_fuente); None si no hay celda."""
        if fuente is None:
            return None
        if fuente[0] == "celda":
            return ref_hp(r_hp, nombre, fuente[1])
        _, pa, pb, k, n = fuente
        ra, rb = ref_hp(r_hp, nombre, pa), ref_hp(r_hp, nombre, pb)
        return None if ra is None or rb is None else f"{ra}+({rb}-{ra})*{k}/{n}"

    descartados, viejas_ref, formulas_val = [], [], []
    ref_apoyo = re.compile(rf"'?({re.escape(HOJA_PE_FCST)}|{re.escape(HOJA_PE_RAMO)}|{re.escape(HOJA_PRIMAS_PE)})'?!",
                           re.I)

    def captura(v, fila, c):
        """Dato de captura que la BD de entrada ya traia: un numero o una formula se conservan; un texto numerico se
        convierte. Una referencia a las hojas de apoyo (de una corrida anterior) no es captura: se limpia."""
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return v if np.isfinite(v) else None
        if isinstance(v, str) and v.strip().startswith("="):
            refs_blq = set()
            for m in re.findall(r"(?<![!A-Za-z_$])\$?([A-Z]{1,3})\$?\d+", v):
                try:
                    refs_blq.add(column_index_from_string(m))
                except ValueError:
                    pass
            if ref_apoyo.search(v) or refs_blq & set(viejas):   # hojas de apoyo o columnas de bloque: se reacomodan
                viejas_ref.append(f"{get_column_letter(c)}{fila}")
                return None
            if not formulas:
                formulas_val.append(f"{get_column_letter(c)}{fila}")
            return v.strip()
        x, _ = a_numero(v)
        if not np.isfinite(x):
            descartados.append(f"{get_column_letter(c)}{fila}")
            return None
        return x

    def monto(pref, conc, p, r):
        if p <= ultimo:
            return bd.valores.get((f"{pref} {conc}", p, r), math.nan)
        return proy.get((norm(f"{pref} {conc}"), p, r), math.nan)

    ok = lambda x: x is not None and np.isfinite(x)               # noqa: E731
    num = lambda x: float(x) if ok(x) else 0.0                    # noqa: E731  (un dato que no hay es 0, como en Excel)
    div = lambda a, b: num(a) / b if ok(b) and b != 0 else 0.0    # noqa: E731  (SI.ERROR(a / b; 0))
    NA = TEXTO_SIN_DATO
    pe_val, p12_h = (hoja_pe["val"], hoja_pe["suma"]) if hoja_pe else ({}, {})
    ref_pe = _ref_hoja(HOJA_PE_RAMO)

    def hp_expr(r_hp, nombre, fuente):
        """(expresion, es_interpolacion) del indice o LAG del mes: la celda de HParametros o la interpolacion entre
        meses vecinos (_hp_fuente); (None, False) si no hay."""
        e = expr_hp(r_hp, nombre, fuente)
        return (e, fuente[0] == "interp") if e is not None else (None, False)

    c_conc, c_per = get_column_letter(bd.col_concepto), get_column_letter(bd.col_periodo)

    def del_mes(ram, f_obj, fila):
        """Monto del concepto del renglon f_obj en el mes del renglon fila: la celda misma si es su renglon; si no,
        SUMAR.SI.CONJUNTO por CONCEPTO y PERIODO (sin referencias a otro renglon: la hoja se puede ordenar y filtrar)."""
        if f_obj == fila:
            return f"{ram}{fila}"
        concepto = str(ws.cell(f_obj, bd.col_concepto).value).strip().replace('"', '""')
        return f'SUMIFS(${ram}:${ram},${c_conc}:${c_conc},"{concepto}",${c_per}:${c_per},${c_per}{fila})'

    cap_fila = {}                      # PE capturada con numero que si entro a la PE: (renglon BEL donde se capturo, USD)
    for (r, p), (_, fuente_pe) in pe.items():
        if str(fuente_pe).startswith("captura"):
            for pref_ in ("RRC", "SONR"):
                fb = bd.filas.get((norm(f"{pref_} BEL"), p)) or bd.filas_prima.get((norm(f"{pref_} BEL"), p))
                x = capturas.get(("PE FCST", r, fb))
                if isinstance(x, str) and not x.strip().startswith("="):
                    x = a_numero(x)[0]
                if fb in bd.filas_entrada and isinstance(x, (int, float)) and not isinstance(x, bool) \
                        and np.isfinite(x) and x != 0:
                    cap_fila[(r, p)] = (fb, float(x))
                    break
    propia = re.compile(rf"=\s*'?{re.escape(HOJA_PE_RAMO)}'?!\$?[A-Z]{{1,3}}\$?\d+\s*", re.I)
    filas_todas = {**bd.filas, **bd.filas_prima}      # (los meses de prima sin montos tambien llevan los bloques)
    for (conc, p), fila in filas_todas.items():
        pref = conc.split()[0]
        if pref not in INDICE_BASE_PND:
            continue
        f_bel = filas_todas.get((norm(f"{pref} BEL"), p))
        es_bel = fila == f_bel
        f_gto = filas_todas.get((norm("RRC GTO"), p)) if pref == "RRC" else None
        f_mr = filas_todas.get((norm(f"{pref} MR"), p))
        f_irr = filas_todas.get((norm(f"{pref} IRR"), p))
        f_bruto = filas_todas.get((norm(f"{pref} BRUTO"), p))
        nombre_is = INDICE_BASE_PND[pref][0]
        anios = ANIOS_LAG_PEACUMULADA.get(pref, 0)
        for r in ramos:
            r_hp = MAPA_RAMO_LAG.get(str(r))
            ram = get_column_letter(bd.cols_ramo[r])
            # valores como los calcula la hoja (modo valores y control): 0 en una division entre 0; N/A sin IS, sin BEL
            # (los meses de prima sin montos) o sin LAG, y en lo que se calcula con ellos
            bel = monto(pref, "BEL", p, r) if f_bel else math.nan
            is_, f_is = _hp_fuente(hp, resultados, r_hp, nombre_is, p, pos)
            lag1, f_l1 = _hp_fuente(hp, resultados, r_hp, "LAG 1", p, pos)
            is_fa_v = is_fa_val.get((pref, str(r), p))
            usa_fa = (pref, p, r) in is_fa_bel and ok(is_fa_v)   # PND / PD = BEL / IS (FA) en esos ramos y meses
            is_b = is_fa_v if usa_fa else is_
            hay_pnd = ok(is_b) and ok(bel)
            pnd = div(bel, is_b) if hay_pnd else NA
            pe_v = pe_val.get((r, p), num(pe.get((r, p), (None, None))[0])) if pe else NA
            p12_v = p12_h.get((r, p), 0.0) if pe else NA      # (sin ninguna PE por ramo: N/A, no 0)
            lags = {k: _hp_fuente(hp, resultados, r_hp, f"LAG {k}", p, pos) for k in range(1, anios + 1)}
            hay_peac = bool(pe) and (not anios or any(ok(x) for x, _ in lags.values()))
            if not hay_peac:
                peac = NA
            elif anios:
                peac = sum(num(lags[k][0]) * p12_h.get((r, _mes_menos(p, 12 * (k - 1))), 0.0)
                           for k in range(1, anios + 1))
            else:
                peac = p12_v
            fnd_proy = p > ultimo and (pref, p, r) in fnd       # (en todos los renglones del mes)
            fac = razones.get((pref, p, r)) if fnd_proy else None   # factores proyectados (valores)
            fnd_v = fnd[(pref, p, r)] if fnd_proy else (div(pnd, peac) if hay_pnd and hay_peac else NA)
            g = primas.GRUPO_DE_RAMO_RESERVA.get(str(r)) if primas is not None else None
            pe_g = pe_tab.get(g)
            pe_g = float(pe_g.get(p, math.nan)) if pe_g is not None else math.nan
            vals = {"PND/PD": pnd, "IS (RL)": is_ if ok(is_) else NA, "LAG (RL)": lag1 if ok(lag1) else NA,
                    "IS (FA)": is_fa_v if ok(is_fa_v) else NA,
                    "PE FCST": pe_v, "PRIMA N AÑOS": p12_v, "PEACUMULADA": peac, "FD/FND": fnd_v,
                    "FA": (div(pnd, pe_g if usa_primas else p12_v) if hay_pnd and (usa_primas or pe) else NA),
                    "FACTOR GTO": (div(monto(pref, "GTO", p, r), pnd) if hay_pnd else NA) if f_gto else 0.0,
                    "FACTOR MR": (div(monto(pref, "MR", p, r), pnd) if hay_pnd else NA) if f_mr else 0.0}
            bruto_m = monto(pref, "BRUTO", p, r) if f_bruto else math.nan
            vals["CESION"] = (div(monto(pref, "IRR", p, r), bruto_m) if f_irr else 0.0) if ok(bruto_m) else NA
            if fac:
                vals.update({k: float(x) for k, x in fac.items() if k != "FACTOR GTO" or f_gto})
            if registro is not None and es_bel and fila in filas_bd:   # (el valor que muestra la hoja)
                registro[(pref, str(r), p)] = {**{k: (None if isinstance(x, str) else float(x)) for k, x in vals.items()},
                                               "BEL": bel if ok(bel) else None,
                                               "BRUTO": bruto_m if ok(bruto_m) else None,
                                               "GTO": 1.0 if f_gto else 0.0,
                                               "FND": 1.0 if fnd_proy else 0.0,
                                               "IS del BEL": "FA" if usa_fa else "RL"}
            for ind in COLUMNAS_INDICES_PND:
                c = cols[(ind, r)]
                celda = ws.cell(fila, c)
                celda.number_format = COLUMNAS_INDICES_PND[ind]
                v = vals.get(ind, 0.0)
                if ind == "PE FCST":
                    if cap_fila.get((r, p), (None,))[0] == fila:   # PE capturada en este renglon: se conserva el numero
                        celda.value = cap_fila[(r, p)][1]
                        continue
                    x = capturas.get((ind, r, fila))
                    if (isinstance(x, str) and propia.fullmatch(x.strip())) or (isinstance(x, (int, float)) and x == 0):
                        x = None                              # la referencia o el 0 que escribe el bloque: no es captura
                    if es_bel and (r, p) not in pe and fila in bd.filas_entrada:
                        x = captura(x, fila, c)               # formula capturada (sin PE del mes)
                        if x is not None:
                            celda.value = x
                            continue
                elif pref in INDICES_PND_CAPTURA.get(ind, ()):
                    x = captura(capturas.get((ind, r, fila)), fila, c) if fila in bd.filas_entrada else None
                    celda.value = 0.0 if x is None else x
                    continue
                if isinstance(v, str):                       # N/A
                    celda.value = v
                    celda.alignment = Alignment(horizontal="right")
                    continue
                if not formulas or (ind == "FD/FND" and fnd_proy) or (fac and ind in fac):   # (proyectados: valor)
                    celda.value = float(v)
                    continue
                pnd_c = f"{L('PND/PD', r)}{fila}"
                if ind == "PND/PD":
                    is_col = L("IS (FA)" if usa_fa else "IS (RL)", r)
                    if es_bel:
                        celda.value = f"=IFERROR({ram}{fila}/{is_col}{fila},0)"
                    else:                                 # el BEL del mes sin apuntar a otro renglon
                        celda.value = f"=IFERROR({del_mes(ram, f_bel, fila)}/{is_col}{fila},0)"
                elif ind == "IS (FA)":
                    e = is_fa_ref.get((pref, str(r), p))
                    celda.value = f"={e}" if e else float(v)
                elif ind in ("IS (RL)", "LAG (RL)"):
                    e, _ = hp_expr(r_hp, nombre_is, f_is) if ind == "IS (RL)" else hp_expr(r_hp, "LAG 1", f_l1)
                    celda.value = f"={e}" if e else float(v)
                elif ind == "PE FCST":
                    celda.value = (f"={ref_pe}!${hoja_pe['pe'][r]}${hoja_pe['fila'][p]}"
                                   if hoja_pe and p in hoja_pe["fila"] else float(v))
                elif ind == "PRIMA N AÑOS":
                    celda.value = (f"={ref_pe}!${hoja_pe['p12'][r]}${hoja_pe['fila'][p]}"
                                   if hoja_pe and p in hoja_pe["fila"] else float(v))
                elif ind == "PEACUMULADA":
                    if not anios:
                        celda.value = f"={L('PRIMA N AÑOS', r)}{fila}"
                    else:
                        terminos = []
                        for k in range(1, anios + 1):
                            q = _mes_menos(p, 12 * (k - 1))
                            e, interp = hp_expr(r_hp, f"LAG {k}", lags[k][1])
                            if e is None or not hoja_pe or q not in hoja_pe["fila"]:
                                continue                       # sin ese LAG o sin PE de ese ano: el termino vale 0
                            terminos.append(f"{f'({e})' if interp else e}*{ref_pe}!${hoja_pe['p12'][r]}"
                                            f"${hoja_pe['fila'][q]}")
                        celda.value = ("=" + "+".join(terminos)) if terminos else float(v)
                elif ind == "FD/FND":
                    celda.value = f"=IFERROR({pnd_c}/{L('PEACUMULADA', r)}{fila},0)"
                elif ind == "FA":
                    if not usa_primas:
                        celda.value = f"=IFERROR({pnd_c}/{L('PRIMA N AÑOS', r)}{fila},0)"
                    elif primas_pe and (meses_pe, g) in primas_pe["col"] and p in primas_pe["fila"]:
                        celda.value = (f"=IFERROR({pnd_c}/{_ref_hoja(HOJA_PRIMAS_PE)}!${primas_pe['col'][(meses_pe, g)]}"
                                       f"${primas_pe['fila'][p]},0)")
                    else:
                        celda.value = float(v)
                elif ind == "FACTOR GTO":
                    celda.value = f"=IFERROR({del_mes(ram, f_gto, fila)}/{pnd_c},0)" if f_gto else 0.0
                elif ind == "FACTOR MR":
                    celda.value = f"=IFERROR({del_mes(ram, f_mr, fila)}/{pnd_c},0)" if f_mr else 0.0
                elif ind == "CESION":
                    celda.value = (f"=IFERROR({del_mes(ram, f_irr, fila)}/{del_mes(ram, f_bruto, fila)},0)"
                                   if f_irr else 0.0)

    def lista(xs):
        return f"{', '.join(xs[:5])}{'...' if len(xs) > 5 else ''}"
    if avisos is not None:
        if descartados:
            avisos.append(f"{len(descartados)} dato(s) de captura con texto no numerico se descartaron; la celda toma "
                          f"la PE de {HOJA_PE_RAMO} (0 en un mes sin PE) ({lista(descartados)})")
        if viejas_ref:
            avisos.append(f"{len(viejas_ref)} celda(s) de captura traian una referencia a una hoja de apoyo o a otra "
                          f"columna de indicadores (que se reacomodan en cada corrida); se reemplazaron por la formula "
                          f"del bloque ({lista(viejas_ref)})")
        if formulas_val:
            avisos.append(f"{len(formulas_val)} dato(s) de captura son formulas: con INDICES_PND_FORMULAS = False no se "
                          f"evaluan ({lista(formulas_val)})")
    fin = max(cols.values())
    if ws.auto_filter and ws.auto_filter.ref:          # el filtro de la hoja llega a las columnas nuevas
        ini, fin_ref = ws.auto_filter.ref.split(":")
        fila_fin = re.match(r"[A-Z]+(\d+)", fin_ref).group(1)
        ws.auto_filter.ref = f"{ini}:{get_column_letter(fin)}{fila_fin}"
    for c in viejas:                                   # columnas viejas que quedaron fuera de los bloques nuevos
        if c > fin:
            ws.cell(3, c).value = None
    _agrupar(ws, [[bd.cols_ramo[r] for r in ramos]] + [[cols[(ind, r)] for r in ramos] for ind in COLUMNAS_INDICES_PND])
    return cols


def _partir_columnas(ws):
    """Rangos <col> de varias columnas (p. ej. los que trae la BD de entrada): uno por columna, para que al cambiar
    anchos o agrupar no queden rangos encimados (Excel marca el archivo como danado y ofrece repararlo)."""
    for d in list(ws.column_dimensions.values()):
        if d.min and d.max and d.max > d.min:
            for cc in range(d.min + 1, d.max + 1):
                nd = copy(d)
                nd.index, nd.min, nd.max = get_column_letter(cc), cc, cc
                ws.column_dimensions[get_column_letter(cc)] = nd
            d.max = d.min


def _agrupar(ws, secciones: list):
    """Agrupa (esquema de Excel) cada seccion de columnas: queda visible la primera y el boton +/- junto a ella."""
    if not AGRUPAR_BLOQUES:
        return
    _partir_columnas(ws)
    if ws.sheet_properties.outlinePr is None:
        ws.sheet_properties.outlinePr = Outline()
    ws.sheet_properties.outlinePr.summaryRight = False
    for g in secciones:
        if len(g) > 1:
            ws.column_dimensions.group(get_column_letter(min(g) + 1), get_column_letter(max(g)), outline_level=1,
                                       hidden=False)


def escribir_bel_fnd(bd: BDMontos, info: dict, cols: dict):
    """En los meses donde aplica el BEL por FND, las celdas RAM_ de RRC y SONR van como formulas que solo usan celdas de
    su propio renglon (IS (RL), o IS (FA) en los ramos de RAMOS_IS_FA_BEL, PEACUMULADA, FD/FND, FACTOR GTO, FACTOR MR y
    CESION, que son las del mes en todos los renglones), sin numeros escritos en la formula, para que la hoja se pueda
    ordenar y filtrar:
    BEL = IS x PEACUMULADA x FND; PND = BEL / IS = PEACUMULADA x FND; GTO = PND x FACTOR GTO; MR = PND x FACTOR MR;
    BRUTO = BEL + GTO + MR; IRR = BRUTO x CESION; NETO = BRUTO x (1 - CESION) = BRUTO - IRR."""
    ws = bd.ws
    for (pref, p, r) in sorted(info["aplica"]):
        ram = get_column_letter(bd.cols_ramo[r])
        for c in ("BEL", "GTO", "MR", "BRUTO", "IRR", "NETO"):
            if c == "GTO" and pref != "RRC":
                continue
            f = bd.filas.get((norm(f"{pref} {c}"), p))
            if not f:
                continue
            L = lambda ind: f"{get_column_letter(cols[(ind, r)])}{f}"         # noqa: E731
            is_col = "IS (FA)" if (pref, p, r) in (info.get("is_fa_bel") or set()) else "IS (RL)"
            bel, pnd = f"{L(is_col)}*{L('PEACUMULADA')}*{L('FD/FND')}", f"{L('PEACUMULADA')}*{L('FD/FND')}"
            gto, mr = f"{pnd}*{L('FACTOR GTO')}", f"{pnd}*{L('FACTOR MR')}"
            bruto = f"{bel}+{gto}+{mr}" if pref == "RRC" else f"{bel}+{mr}"
            ws[f"{ram}{f}"] = "=" + {"BEL": bel, "GTO": gto, "MR": mr, "BRUTO": bruto,
                                     "IRR": f"({bruto})*{L('CESION')}", "NETO": f"({bruto})*(1-{L('CESION')})"}[c]


def escenarios_pnd(bd: BDMontos, hp, resultados: dict, pr, proy_base: dict, periodos_proy: list[int], ultimo: int,
                   alertas: list, motivo_sin_prima: str = "") -> dict:
    """Escenarios PND / PD de Danos (ver ESCENARIOS_PND). Regresa el diagnostico y, por escenario, el diccionario de
    montos derivados (el de proy_base con RRC y SONR reemplazados donde el escenario aplica)."""
    diag = {"estado": "", "resumen": [], "mensual": [], "decision": [], "backtest": [], "totales": [], "proy": {},
            "config": {}}
    h = len(periodos_proy)
    pos = {p: i for i, p in enumerate(periodos_proy)}
    dics = [p for p in periodos_proy if p % 100 == 12]
    # 1) historia (aunque no haya prima): base implicita, gastos y margen sobre la base
    hist = {}
    for pref, (nombre_is, base) in INDICE_BASE_PND.items():
        for ramo in bd.cols_ramo:
            res = resultados.get(("DANOS", pref, "BEL", ramo))
            if res is None or not res.historia_periodos:
                continue
            per = list(res.historia_periodos)             # (los meses de la serie del modelo, en USD de la BD)
            bel = np.array([bd.valores.get((f"{pref} BEL", p, ramo), math.nan) for p in per], dtype=float)
            iv, lv, dv = _divisor_base(hp, ramo, pref, per)
            with np.errstate(divide="ignore", invalid="ignore"):
                b = np.where(np.isfinite(dv) & np.isfinite(bel), bel / dv, np.nan)
            gto = np.array([bd.valores.get((f"{pref} GTO", p, ramo), math.nan) for p in per], dtype=float) \
                if pref == "RRC" else np.full(len(per), np.nan)
            mr = np.array([bd.valores.get((f"{pref} MR", p, ramo), math.nan) for p in per], dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                fg = np.where(b > 0, gto / b, np.nan)
                fm = np.where(b > 0, mr / b, np.nan)
                # el margen se suaviza sobre BEL / IS (= base x (1 - LAG) en SONR): un brinco del LAG que el BEL no
                # refleja no rompe la razon; MR = FM_s x base x (1 - LAG)
                k = np.where(np.isfinite(dv) & np.isfinite(iv) & (iv > 0), dv / iv, np.nan)
                fm_s = np.where(b * k > 0, mr / (b * k), np.nan)
            hist[(pref, ramo)] = {"per": per, "bel": bel, "is": iv, "lag": lv, "div": dv, "base": b, "gto": gto,
                                  "mr": mr, "fg": fg, "fm": fm, "fm_s": fm_s, "nombre_is": nombre_is,
                                  "base_nombre": base, "nombre_lag": _lag_pnd(pref), "con_lag": pref in LAG_BASE_PND,
                                  "clave_fm": ("MR/(BEL/IS)" if pref in LAG_BASE_PND else f"MR/{base}")}
    if not USAR_ESCENARIOS_PND:
        diag["estado"] = "apagado (USAR_ESCENARIOS_PND = False)"
    elif motivo_sin_prima:
        diag["estado"] = f"{motivo_sin_prima}: solo se reporta la base implicita (sin escenarios)"
    elif pr is None:
        diag["estado"] = "sin archivos de prima real en entradas/: solo se reporta la base implicita (sin escenarios)"
    elif not pr.tiene_siguiente:
        diag["estado"] = ("sin prima del ano siguiente (presupuesto completo): solo se reporta la base implicita "
                          "(sin escenarios)")
    elif periodo_a_indice(ultimo) - periodo_a_indice(pr.ultimo_real) > MAX_MESES_PRIMA_ESTIMADA:
        diag["estado"] = (f"la prima real llega a {pr.ultimo_real} y las reservas a {ultimo}: actualiza el real de "
                          "primas; solo se reporta la base implicita (sin escenarios)")
    pe_tab = {}
    if not diag["estado"]:
        for esc, meses in ESCENARIOS_PND.items():
            for g in pr.mensual.columns:
                pe_tab[(esc, g)] = _pe(pr, g, meses)

    # 2) elegibilidad, ajuste del FA por configuracion y backtest (por escenario y reserva)
    ajustes, motivos, bts = {}, {}, {}
    cache_bt = {}
    for (pref, ramo), d in hist.items():
        grupo = primas.GRUPO_DE_RAMO_RESERVA.get(str(ramo)) if primas is not None else None
        d["grupo"] = grupo
        motivo = ""
        if diag["estado"]:
            motivo = diag["estado"]
        elif resultados[("DANOS", pref, "BEL", ramo)].regla or d["per"][-1] != ultimo:
            motivo = "BEL resuelto por regla o sin dato al ultimo mes"
        elif hp.ultimo < ultimo and not np.isfinite(d["base"][-1]):
            motivo = (f"{HOJA_PARAMETROS} llega a {hp.ultimo} y las reservas a {ultimo}: sin el indice real del ultimo "
                      "mes no se puede despejar la base")
        elif not (np.isfinite(d["base"][-1]) and d["base"][-1] > 0):
            motivo = (f"sin {d['nombre_is']}" + (f" o sin {d['nombre_lag']} (con 1 - LAG positivo)" if d["con_lag"]
                                                 else "") + " o sin BEL positivo al ultimo mes")
        elif grupo is None or pr.cobertura.get(grupo) is None or pr.cobertura[grupo] < primas.MIN_COBERTURA_HISTORIA:
            motivo = f"cobertura de prima insuficiente en el grupo {grupo}"
        is_f = lag_f = dv_f = None
        if not motivo:
            is_f, lag_f, dv_f = _divisor_proyectado(resultados, ramo, pref, h)
            if dv_f is None or not np.all(np.isfinite(dv_f)) or not np.all(dv_f > 0):
                motivo = (f"sin proyeccion de {d['nombre_is']}" + (f" x (1 - {d['nombre_lag']}) positiva"
                                                                   if d["con_lag"] else "") + " para el ramo")
        d["is_f"], d["lag_f"], d["div_f"] = is_f, lag_f, dv_f
        for esc in ESCENARIOS_PND:
            if motivo:
                motivos[(esc, pref, ramo)] = motivo
                continue
            PE = pe_tab[(esc, grupo)]
            for persist in PERSISTENCIAS_PND:
                cfg = (esc, 0.0, persist)
                a = ajustar_factor(d["per"], d["base"], PE, periodos_proy, cfg, "DANOS")
                if a is None or not (RANGO_FA[0] <= a["kappa_hist"][-1] <= RANGO_FA[1]):
                    continue
                ajustes[(esc, pref, ramo, persist)] = a
                # backtest en los cortes estandar (prima real despues del corte; indice proyectado desde el corte)
                filas = []
                for c in CORTES_BACKTEST:
                    o = len(d["per"]) - c
                    if o < MIN_ENTRENAMIENTO:
                        continue
                    hz = min(16, len(d["per"]) - o)
                    pc, per_h = d["per"][o - 1], d["per"][o:o + hz]
                    k_b = (pref, ramo, c, "base")
                    if k_b not in cache_bt:        # base con el indice (y LAG) conocidos al corte (sin interpolar
                        _, _, dv_c = _divisor_base(hp, ramo, pref, d["per"][:o], hasta=d["per"][o - 1])  # adelante)
                        with np.errstate(divide="ignore", invalid="ignore"):
                            cache_bt[k_b] = np.where(np.isfinite(dv_c), d["bel"][:o] / dv_c, np.nan)
                    b = ajustar_factor(d["per"][:o], cache_bt[k_b], PE, per_h, cfg, "DANOS")
                    if b is None:
                        continue
                    # la misma proyeccion con la prima plana despues del corte (sin saber la prima que vino)
                    pe_pl = PE.copy()
                    pe_pl[[x for x in pe_pl.index if x > d["per"][o - 1]]] = PE.get(d["per"][o - 1], math.nan)
                    b_pl = ajustar_factor(d["per"][:o], cache_bt[k_b], pe_pl, per_h, cfg, "DANOS")
                    k_c = (pref, ramo, c)
                    if k_c not in cache_bt:        # lo que no depende del escenario: indice, FG, FM y la recta
                        is_c = _indice_al_corte(hp, ramo, d["nombre_is"], pc, hz)
                        fac_c = np.ones(hz)                # (1 - LAG) proyectado desde el corte (1 en RRC)
                        if is_c is not None and d["con_lag"]:
                            lag_c = _indice_al_corte(hp, ramo, d["nombre_lag"], pc, hz)
                            fac_c = (1.0 - lag_c) if lag_c is not None else None
                            is_c = is_c * fac_c if fac_c is not None else None
                            if is_c is not None and not np.all(is_c > 0):
                                is_c = None
                        fg_ok = [x for x in d["fg"][:o] if np.isfinite(x)]
                        fm_c = _razon_ses(("DANOS", pref, d["clave_fm"], ramo), d["per"][:o], d["fm_s"][:o], pc, hz)
                        try:
                            bel_a = (_recta(d["bel"][:o], d["per"][:o], hz)
                                     if np.all(np.isfinite(d["bel"][:o]) & (d["bel"][:o] > 0)) else None)
                        except Exception:  # noqa: BLE001
                            bel_a = None
                        with np.errstate(divide="ignore", invalid="ignore"):
                            rg = np.where(d["bel"][:o] > 0, d["gto"][:o] / d["bel"][:o], np.nan)
                            rm = np.where(d["bel"][:o] > 0, d["mr"][:o] / d["bel"][:o], np.nan)
                        ga = (_razon_ses(("DANOS", pref, "GTO/BEL", ramo), d["per"][:o], rg, pc, hz)
                              if pref == "RRC" else np.zeros(hz))
                        ma = _razon_ses(("DANOS", pref, "MR/BEL", ramo), d["per"][:o], rm, pc, hz)
                        cache_bt[k_c] = {"is": is_c, "fg": fg_ok[-1] if fg_ok else (0.0 if pref == "SONR" else None),
                                         "fm": fm_c, "k": fac_c, "bel_a": bel_a, "ga": ga, "ma": ma}
                    cb = cache_bt[k_c]
                    if cb["is"] is None or cb["fm"] is None or cb["fg"] is None or cb["bel_a"] is None \
                            or cb["ma"] is None or cb["ga"] is None or not np.all(np.isfinite(cb["bel_a"])):
                        continue
                    base_b = b["pron"]
                    is_real = d["div"][o:o + hz]
                    real = {"BEL": d["bel"][o:o + hz], "GTO": np.nan_to_num(d["gto"][o:o + hz]),
                            "MR": np.nan_to_num(d["mr"][o:o + hz])}
                    esc_f = {"BEL": base_b * cb["is"], "GTO": cb["fg"] * base_b, "MR": cb["fm"] * base_b * cb["k"]}
                    pl_f = None
                    if b_pl is not None:
                        pb = np.asarray(b_pl["pron"], dtype=float)
                        pl_f = {"BEL": pb * cb["is"], "GTO": cb["fg"] * pb, "MR": cb["fm"] * pb * cb["k"]}
                    rec_f = {"BEL": cb["bel_a"], "GTO": cb["ga"] * cb["bel_a"], "MR": cb["ma"] * cb["bel_a"]}
                    ora = base_b * is_real if np.all(np.isfinite(is_real)) else None
                    filas.append({"corte": pc, "meses": hz, "real": real, "esc": esc_f, "recta": rec_f,
                                  "plana": pl_f, "bel_is_real": ora})
                bts[(esc, pref, ramo, persist)] = filas
            if not any(k[:3] == (esc, pref, ramo) for k in ajustes):
                motivos[(esc, pref, ramo)] = (f"{d['base_nombre']} / prima con menos de {MIN_MESES_FACTOR['DANOS']} "
                                              "meses validos o FA fuera de rango")

    def _err(filas, modelo, concepto):
        filas = [f for f in filas if f.get(modelo) is not None]
        num = sum(float(np.sum(np.abs(f[modelo][concepto] - f["real"][concepto]))) for f in filas)
        den = sum(float(np.sum(np.abs(f["real"][concepto]))) for f in filas)
        return num / den * 100 if den > 0 else math.nan

    def _err_bruto(filas, modelo):
        num = den = 0.0
        for f in filas:
            if f.get(modelo) is None:
                continue
            tot_f = f[modelo]["BEL"] + f[modelo]["GTO"] + f[modelo]["MR"]
            tot_r = f["real"]["BEL"] + f["real"]["GTO"] + f["real"]["MR"]
            num += float(np.sum(np.abs(tot_f - tot_r)))
            den += float(np.sum(np.abs(tot_r)))
        return num / den * 100 if den > 0 else math.nan

    # 3) persistencia del FA por escenario y reserva: la de fabrica (1) salvo que la estimada baje el error del BEL
    #    agrupado MARGEN_PREFERENCIA_FACTOR puntos o mas (mismos casos)
    for esc in ESCENARIOS_PND:
        for pref in INDICE_BASE_PND:
            ramos = sorted({k[2] for k in ajustes if k[:2] == (esc, pref)}, key=str)
            if not ramos:
                continue
            comunes = [(r, f["corte"]) for r in ramos
                       for f in bts.get((esc, pref, r, PERSISTENCIAS_PND[0]), [])
                       if all(any(g["corte"] == f["corte"] for g in bts.get((esc, pref, r, ps), []))
                              for ps in PERSISTENCIAS_PND)]
            errs = {}
            for ps in PERSISTENCIAS_PND:
                filas = [f for r in ramos for f in bts.get((esc, pref, r, ps), []) if (r, f["corte"]) in comunes]
                errs[ps] = _err(filas, "esc", "BEL") if filas else math.nan
            elegida = PERSISTENCIAS_PND[0]
            mejor = min((ps for ps in PERSISTENCIAS_PND if np.isfinite(errs[ps])), key=lambda ps: errs[ps],
                        default=elegida)
            if np.isfinite(errs.get(elegida, math.nan)) and errs[mejor] <= errs[elegida] - MARGEN_PREFERENCIA_FACTOR:
                elegida = mejor
            diag["config"][(esc, pref)] = elegida
            filas = [f for r in ramos for f in bts.get((esc, pref, r, elegida), [])]
            fila = {"Escenario": esc, "Reserva": pref, "Base": INDICE_BASE_PND[pref][1],
                    "Indice": INDICE_BASE_PND[pref][0], "Persistencia del FA": str(elegida),
                    "Series": len({r for r in ramos if bts.get((esc, pref, r, elegida))}), "Cortes (serie x corte)": len(filas)}
            for ps in PERSISTENCIAS_PND:
                fila[f"Error % BEL (persistencia {ps})"] = errs[ps]
            for conc in ("BEL", "GTO", "MR") if pref == "RRC" else ("BEL", "MR"):
                fila[f"Error % {conc} recta"] = _err(filas, "recta", conc) if filas else math.nan
                fila[f"Error % {conc} escenario"] = _err(filas, "esc", conc) if filas else math.nan
            fila["Error % BRUTO recta"] = _err_bruto(filas, "recta") if filas else math.nan
            fila["Error % BRUTO escenario"] = _err_bruto(filas, "esc") if filas else math.nan
            fila["Error % BEL escenario con prima plana"] = _err(filas, "plana", "BEL") if filas else math.nan
            fila["Error % BRUTO escenario con prima plana"] = _err_bruto(filas, "plana") if filas else math.nan
            ora = [f for f in filas if f["bel_is_real"] is not None]
            if ora:
                num = sum(float(np.sum(np.abs(f["bel_is_real"] - f["real"]["BEL"]))) for f in ora)
                den = sum(float(np.sum(np.abs(f["real"]["BEL"]))) for f in ora)
                fila["Error % BEL escenario con el indice real"] = num / den * 100 if den else math.nan
            diag["decision"].append(fila)
            for r in ramos:
                for f in bts.get((esc, pref, r, elegida), []):
                    diag["backtest"].append({
                        "Escenario": esc, "Reserva": pref, "Ramo": r, "Corte": f["corte"], "Meses": f["meses"],
                        **{f"{conc} recta": _err([f], "recta", conc) for conc in ("BEL", "GTO", "MR")},
                        **{f"{conc} escenario": _err([f], "esc", conc) for conc in ("BEL", "GTO", "MR")},
                        "BRUTO recta": _err_bruto([f], "recta"), "BRUTO escenario": _err_bruto([f], "esc"),
                        "BRUTO escenario con prima plana": _err_bruto([f], "plana")})

    # 4) proyeccion por escenario y montos derivados (IRR con la misma razon de cesion del modelo)
    finales = {}
    for esc in ESCENARIOS_PND:
        proy = dict(proy_base)
        aplicadas = 0
        for (pref, ramo), d in hist.items():
            cfg_p = diag["config"].get((esc, pref), PERSISTENCIAS_PND[0])
            a = ajustes.get((esc, pref, ramo, cfg_p)) or next(
                (ajustes[k] for k in ajustes if k[:3] == (esc, pref, ramo)), None)
            if a is None:
                continue
            base_f = np.asarray(a["pron"], dtype=float)
            bel_f = base_f * d["div_f"]
            fg_ok = [x for x in d["fg"] if np.isfinite(x)]
            fg = fg_ok[-1] if (pref == "RRC" and fg_ok) else 0.0
            fm_s_f = _razon_ses(("DANOS", pref, d["clave_fm"], ramo), d["per"], d["fm_s"], ultimo, h)
            if fm_s_f is None:
                motivos[(esc, pref, ramo)] = f"no se pudo proyectar {d['clave_fm']}"
                continue
            fm_f = fm_s_f * (d["div_f"] / d["is_f"])       # MR / base (en SONR, x (1 - LAG) proyectado)
            gto_f, mr_f = fg * base_f, fm_f * base_f
            ces = resultados.get(("DANOS", pref, "IRR/BRUTO", ramo))
            c = np.nan_to_num(np.asarray(ces.pronostico, dtype=float), nan=0.0) if ces is not None else np.zeros(h)
            bruto = bel_f + gto_f + mr_f
            irr = c * bruto
            valores = {f"{pref} BEL": bel_f, f"{pref} MR": mr_f, f"{pref} BRUTO": bruto, f"{pref} IRR": irr,
                       f"{pref} NETO": bruto - irr}
            if pref == "RRC":
                valores["RRC GTO"] = gto_f
            for conc, arr in valores.items():
                for i, p in enumerate(periodos_proy):
                    proy[(norm(conc), p, ramo)] = float(arr[i])
            aplicadas += 1
            finales[(esc, pref, ramo)] = {"a": a, "cfg": cfg_p, "base": base_f, "bel": bel_f, "gto": gto_f, "mr": mr_f,
                                          "fg": fg, "fm": fm_f, "neto": bruto - irr}
        if aplicadas:
            if any(lib == "DANOS" for (lib, _) in RANGO_ESPERADO):
                al_tmp = []
                print(f"   Escenario {esc}:", flush=True)
                diag.setdefault("rangos", {})[esc] = aplicar_rango_esperado(
                    proy, bd, "DANOS", ESTRUCTURA["DANOS"], {}, periodos_proy, ultimo, al_tmp)
            diag["proy"][esc] = proy

    diag["_hist"], diag["_pe"] = hist, pe_tab       # (para las columnas de indicadores de la BD)

    # 5) tablas del diagnostico
    def _v(proy, conc, p, ramo):
        return proy.get((norm(conc), p, ramo), math.nan)

    for (pref, ramo), d in hist.items():
        per, base = d["per"], d["base_nombre"]
        lbl = f"{base} (BEL / (indice x (1 - {d['nombre_lag']})))" if d["con_lag"] else f"{base} (BEL / indice)"
        for i, p in enumerate(per):
            if not np.isfinite(d["base"][i]):
                continue
            fila = {"Reserva": pref, "Ramo": ramo, "Periodo": p, "Tipo": "Real", d["nombre_is"]: d["is"][i]}
            if d["con_lag"]:
                fila[d["nombre_lag"]] = d["lag"][i]
            fila.update({lbl: d["base"][i], "BEL": d["bel"][i], "MR": d["mr"][i], f"MR / {base} (FM)": d["fm"][i]})
            if pref == "RRC":
                fila.update({"GTO": d["gto"][i], f"GTO / {base} (FG)": d["fg"][i]})
            for esc in ESCENARIOS_PND:
                pe = pe_tab.get((esc, d.get("grupo")))
                v = float(pe.get(p, math.nan)) if pe is not None else math.nan
                fila[f"Prima {esc} (anualizada)"] = v
                fila[f"FA {esc}"] = d["base"][i] / v if v and np.isfinite(v) and v > 0 else math.nan
            diag["mensual"].append(fila)
        if not any((esc, pref, ramo) in finales for esc in ESCENARIOS_PND):
            continue
        for j, p in enumerate(periodos_proy):
            fila = {"Reserva": pref, "Ramo": ramo, "Periodo": p, "Tipo": "Proyeccion",
                    d["nombre_is"]: d["is_f"][j] if d.get("is_f") is not None else math.nan}
            if d["con_lag"]:
                fila[d["nombre_lag"]] = d["lag_f"][j] if d.get("lag_f") is not None else math.nan
            fila["BEL BD principal"] = _v(proy_base, f"{pref} BEL", p, ramo)
            for esc in ESCENARIOS_PND:
                fz = finales.get((esc, pref, ramo))
                if fz is None:
                    continue
                pe = pe_tab[(esc, d["grupo"])]
                fila.update({f"Prima {esc} (anualizada)": float(pe.get(p, math.nan)), f"FA {esc}": fz["a"]["kappa_fut"][j],
                             f"{base} {esc}": fz["base"][j], f"BEL {esc}": fz["bel"][j], f"MR {esc}": fz["mr"][j],
                             f"MR / {base} (FM) {esc}": fz["fm"][j]})
                if pref == "RRC":
                    fila.update({f"GTO {esc}": fz["gto"][j], f"GTO / {base} (FG) {esc}": fz["fg"]})
            diag["mensual"].append(fila)
    for esc in ESCENARIOS_PND:
        for (pref, ramo), d in hist.items():
            fz = finales.get((esc, pref, ramo))
            fila = {"Escenario": esc, "Reserva": pref, "Ramo": ramo, "Grupo de prima": d.get("grupo"),
                    "Aplica": fz is not None, "Motivo": "" if fz is not None else motivos.get((esc, pref, ramo), "")}
            if fz is not None:
                a = fz["a"]
                fila.update({"Persistencia del FA": str(fz["cfg"]), "Rho del FA (AR1)": a["rho"],
                             f"FA {ultimo}": a["kappa_hist"][-1], f"FA {periodos_proy[-1]}": a["kappa_fut"][-1],
                             f"{d['nombre_is']} {ultimo}": d["is"][-1], f"{d['nombre_is']} {periodos_proy[-1]}": d["is_f"][-1]})
                if d["con_lag"]:
                    fila.update({f"{d['nombre_lag']} {ultimo}": d["lag"][-1],
                                 f"{d['nombre_lag']} {periodos_proy[-1]}": d["lag_f"][-1]})
                if pref == "RRC":
                    fila["FG (ultimo)"] = fz["fg"]
                fila[f"FM {periodos_proy[-1]}"] = fz["fm"][-1]
                for conc in (("BEL", "GTO", "MR", "NETO") if pref == "RRC" else ("BEL", "MR", "NETO")):
                    fila[f"{conc} real {ultimo}"] = bd.valores.get((f"{pref} {conc}", ultimo, ramo), math.nan)
                    for p in dics:
                        fila[f"{conc} BD principal {p}"] = _v(proy_base, f"{pref} {conc}", p, ramo)
                        fila[f"{conc} {esc} {p}"] = _v(diag["proy"][esc], f"{pref} {conc}", p, ramo)
            diag["resumen"].append(fila)
    # totales por reserva (todos los ramos)
    for pref in INDICE_BASE_PND:
        for conc in (("BEL", "GTO", "MR", "BRUTO", "NETO") if pref == "RRC" else ("BEL", "MR", "BRUTO", "NETO")):
            reales = [bd.valores.get((f"{pref} {conc}", ultimo, r), math.nan) for r in bd.cols_ramo]
            fila = {"Reserva": f"{pref} {conc}", f"Real {ultimo}": float(sum(v for v in reales if np.isfinite(v)))}
            for nombre, proy in [("BD principal", proy_base)] + [(e, diag["proy"][e]) for e in diag["proy"]]:
                for p in dics:
                    fila[f"{nombre} {p}"] = sum(_v(proy, f"{pref} {conc}", p, r) for r in bd.cols_ramo
                                                if np.isfinite(_v(proy, f"{pref} {conc}", p, r)))
            diag["totales"].append(fila)
    if not diag["estado"]:
        n = {esc: sum(1 for k in finales if k[0] == esc) for esc in ESCENARIOS_PND}
        diag["estado"] = "; ".join(f"{esc}: {v} series (reserva x ramo) con el escenario" for esc, v in n.items())
        for f in diag["decision"]:
            alertas.append(("PND", f"Escenario {f['Escenario']} {f['Reserva']}",
                            f"Error % backtest BEL: recta {f.get('Error % BEL recta', math.nan):.1f}, escenario "
                            f"{f.get('Error % BEL escenario', math.nan):.1f}; BRUTO: recta "
                            f"{f.get('Error % BRUTO recta', math.nan):.1f}, escenario "
                            f"{f.get('Error % BRUTO escenario', math.nan):.1f} (persistencia del FA "
                            f"{f['Persistencia del FA']})"))
    return diag


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


def agregar_meses_prima(bd: BDMontos, pe: dict) -> list[int]:
    """AGREGAR_MESES_PRIMA: agrega al final de la hoja de montos los meses con PE por ramo anteriores al primer mes de la
    BD (hoy 201901 a 202112, de PExRamo), un bloque por ano con los conceptos de RRC y SONR en el orden de los bloques
    nuevos, sin montos ni TC (no hay dato), para que los bloques de indicadores lleven la prima del mes y su acumulado
    desde el primer mes de prima. Van en bd.filas_prima, no en bd.filas: no son historia del modelo. Si la BD de entrada
    ya los trae (una salida que se vuelve a usar), se reutilizan. Regresa los meses."""
    if not AGREGAR_MESES_PRIMA or not pe:
        return []
    ws = bd.ws
    conceptos = [c for c in bd.conceptos if c.split()[0] in INDICE_BASE_PND and any(cc == c for cc, _ in bd.filas)]
    if not conceptos:
        return []
    inicio = min(p for (c, p) in bd.filas if c in conceptos)
    meses = sorted({p for (_, p) in pe if p < inicio})
    if not meses:
        return []
    anio_ref = max((p for (_, p) in bd.filas if p < PERIODO_INICIO), default=inicio) // 100
    primera = {c: min((r for (cc, p), r in bd.filas.items() if cc == c and p // 100 == anio_ref), default=10 ** 9)
               for c in conceptos}
    orden = sorted(conceptos, key=lambda c: primera[c])
    ultima_col = ws.max_column
    fila = ws.max_row + 1
    for anio in sorted({p // 100 for p in meses}):
        for c in orden:
            for p in [q for q in meses if q // 100 == anio]:
                if (c, p) in bd.filas_prima:
                    continue
                cands = [(q, r) for (cc, q), r in bd.filas.items() if cc == c and q % 100 == p % 100 and q < PERIODO_INICIO]
                plantilla = min(cands)[1] if cands else _fila_plantilla(bd, c, p)
                for col in range(1, ultima_col + 1):
                    _copiar_estilo(ws.cell(plantilla, col), ws.cell(fila, col))
                if ws.row_dimensions[plantilla].height:
                    ws.row_dimensions[fila].height = ws.row_dimensions[plantilla].height
                ws.cell(fila, bd.col_concepto).value = ws.cell(plantilla, bd.col_concepto).value
                ws.cell(fila, bd.col_periodo).value = p
                bd.filas_prima[(c, p)] = fila
                fila += 1
    if ws.auto_filter and ws.auto_filter.ref:
        ini, fin = ws.auto_filter.ref.split(":")
        ws.auto_filter.ref = f"{ini}:{re.match(r'[A-Z]+', fin).group()}{ws.max_row}"
    return meses


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
    filas: dict = field(default_factory=dict)   # (ramo_str, periodo) -> renglon "Real" (y "Proyeccion" al escribirla)


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
    historia, textos, ultimos, filas_hp = {}, 0, {}, {}
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
        filas_hp[(clave_ramo, fecha)] = r
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
    return HParam(ws, cols, historia, ultimos[ultimo], ultimo, textos, lags_cero, filas_hp)


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
            hp.filas[(clave_ramo, p)] = fila
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
        ("Version del codigo", VERSION_CODIGO),
        ("Ultimo mes real usado", str(resumen.get("ultimo"))),
        ("Series modeladas", str(len(resultados))),
        ("Ventana de tendencia (meses)", str(MESES_TENDENCIA) if MESES_TENDENCIA else "toda la historia"),
        ("Amortiguacion de la tendencia (phi)", str(AMORTIGUACION_TENDENCIA)),
        ("Estacionalidad mensual", (f"si, en {' e '.join(TIPOS_CON_ESTACIONALIDAD)}: patron por mes del ano con credibilidad "
                                    f"'{CREDIBILIDAD_ESTACIONAL}' ({DESCRIPCION_CREDIBILIDAD[CREDIBILIDAD_ESTACIONAL]}), "
                                    f"estimado sobre {'toda la historia' if MESES_ESTACIONALIDAD is None else 'los ultimos ' + str(MESES_ESTACIONALIDAD) + ' meses'} "
                                    f"(minimo {MIN_OBS_ESTACIONALIDAD} meses)") if ESTACIONALIDAD_MENSUAL else "no"),
        ("Cesion por indicacion del area", _nota_cesion_area().replace("; por indicacion del area, ", "", 1) or "no"),
        ("Margenes GTO y MR del BEL por FND", (f"fijos en el ultimo real ({resumen.get('ultimo')}) desde "
                                               f"{periodos_proy[0]}: " + ", ".join(FACTORES_BEL_FIJOS)
                                               + " (FACTORES_BEL_FIJOS, indicacion del area; tambien en el backtesting y en "
                                               "los margenes GTO / BEL y MR / BEL del modelo de los ramos sin BEL por FND; "
                                               "un real negativo se fija en 0)")
         + (f"; mas de {UMBRAL_MARGEN_ATIPICO:.0%} lejos de la mediana de sus 12 meses previos (confirmar el mes): " + ", ".join(
             f"{a['Reserva']} {a['Ramo']} {a['Factor'].split()[1]} {a['Fijo']:.2%} contra {a['Mediana 12 meses anteriores']:.2%}"
             + (f" (se fija en {a['Se fija en']:.2%})" if a["Se fija en"] != a["Fijo"] else "")
             for a in (((resumen.get("pnd") or {}).get("bel_fnd") or {}).get("margen_atipico") or []))
            if (((resumen.get("pnd") or {}).get("bel_fnd") or {}).get("margen_atipico")) else "")
         if FACTORES_BEL_FIJOS else "proyectados con la pendiente combinada"),
        ("Suavizado del BEL entre diciembres", " | ".join(
            f"{pr_} {r_}: {d_['texto']}" for (pr_, r_), d_ in sorted(
                (((resumen.get("pnd") or {}).get("bel_fnd") or {}).get("suavizado") or {}).items()))
         or ("no aplico" if SUAVIZAR_BEL else "no")),
        ("Moneda del modelo", ", ".join(f"{lib}: {'MXN (convertido con el TC de Inversiones)' if v else 'USD'}"
                                         for lib, v in MODELAR_EN_MXN.items())),
        ("Rango esperado", "; ".join(f"{lib} {c} (total de ramos): {texto_rango(a, b)}"
                                     for (lib, c), (a, b) in RANGO_ESPERADO.items()) or "sin rangos"),
        ("Ajuste por rango esperado", " | ".join(resumen.get("rangos") or []) or "no aplico"),
        ("Moneda mezclada corregida", ", ".join(f"{k}: {v} celdas convertidas de MXN a USD"
                                                for k, v in (resumen.get("moneda_corregida") or {}).items())
                                      or "no se detecto"),
        ("Pendiente proyectada", ("montos y LAGs: la pendiente completa de la recta; indices: ponderada por su credibilidad "
                                  "(R2 ajustado de la recta)" if CREDIBILIDAD_PENDIENTE.get("indice") == "r2"
                                  else f"proporcion de la pendiente por tipo: {CREDIBILIDAD_PENDIENTE}")
                                 + (f"; {_factores_fijos_txt()} del BEL por FND: fijos en el ultimo real (FACTORES_BEL_FIJOS)"
                                    if _factores_fijos_txt() and "combinada" in CREDIBILIDAD_PENDIENTE.values() else "")
                                 + (f"; {_factores_fijos_txt(False)} del BEL por FND: pendiente combinada (promedio de plano y rectas "
                                    "Theil-Sen de 24 y 36 meses, minimos cuadrados en el FACTOR GTO; sin el plano si la "
                                    f"tendencia de 24 meses es clara, |t| >= {PENDIENTE_COMBINADA['t_clara']}; la mitad de "
                                    "la recta de 24 si los ultimos 12 meses no la confirman (en el GTO el plano se queda en "
                                    "el promedio); amortiguada "
                                    f"{PENDIENTE_COMBINADA['amortiguacion']} por mes y topada al rango de 36 meses)"
                                    if "combinada" in CREDIBILIDAD_PENDIENTE.values() and _factores_fijos_txt(False) else "")
                                 + (f"; FND: {MODELO_POR_TIPO['fnd']} (HOLT_FND: alpha {HOLT_FND['alpha']}, beta "
                                    f"{HOLT_FND['beta']}, phi {HOLT_FND['phi']}, salto > {HOLT_FND['k_salto']:.0f} MAD, tope "
                                    f"{HOLT_FND['tope_rango']:.0%} del rango de 36 meses)" if MODELO_POR_TIPO.get("fnd") == HOLT_GUARDIA else "")),
        ("Desviacion del ultimo mes", f"indices: se desvanece hacia el nivel promedio de los ultimos {MESES_NIVEL_LOCAL} meses con "
                                       f"persistencia {PERSISTENCIA_DESVIACION.get('indice', 1.0)}; montos y LAGs: se conserva "
                                       f"(persistencia {PERSISTENCIA_DESVIACION.get('nivel', 1.0)} / {PERSISTENCIA_DESVIACION.get('lag', 1.0)})"),
        ("Factor de prima", (resumen.get("factor") or {}).get("estado", "")
         + (f"; perfil mensual de la prima estimada: {resumen['primas'].perfil['elegido']}"
            if resumen.get("primas") is not None else "")),
        ("Factor de prima: decision", " | ".join(f"{d['Tipo']}: {d['Decision']} ({d['Configuracion']}; {d['Motivo']})"
                                                 for d in (resumen.get("factor") or {}).get("decision", [])) or "-"),
        ("Factor de prima: reservas NETO (M USD)", (" | ".join(
            f"{f['Escenario']} {f['Reserva']}: " + ", ".join(f"{k[5:]} {v / 1e6:,.1f}" for k, v in f.items()
                                                           if k.startswith("Proy ") and v is not None)
            for f in (resumen.get("comparativo") or {}).get("filas", [])) or "-")
         + ("; modelo de las series, antes del BEL por FND de Danos y de la RFV por prima de Fianzas (la BD lleva esos)"
            if (resumen.get("comparativo") or {}).get("filas") else "")),
        ("Backtesting", (((resumen.get("pnd") or {}).get("backtesting") or {}).get("estado") or "-")
         + (f"; renglones '{BACKTESTING_ETIQUETA} <concepto>' al final de {HOJA_MONTOS}; hojas Backtesting_Resumen y "
            "Backtesting_Mensual" if ((resumen.get("pnd") or {}).get("backtesting") or {}).get("proy") else "")),
        ("RFV por prima (Fianzas)", (((resumen.get("pnd") or {}).get("rfv_prima") or {}).get("estado") or "-")
         + (f"; sensibilidad a la moneda: {((resumen.get('pnd') or {}).get('rfv_prima') or {}).get('sensibilidad')}"
            if ((resumen.get("pnd") or {}).get("rfv_prima") or {}).get("sensibilidad") else "")
         + (f"; prima: {(resumen.get('pnd') or {}).get('pt_fianzas')}" if (resumen.get("pnd") or {}).get("pt_fianzas")
            else "")
         + (f"; hojas RFV_Prima_Resumen y RFV_Prima_Mensual; en la BD de RFV, hoja {HOJA_PT_RAMO} y bloques "
            + ", ".join(nombre_bloque_rfv(k) for k in bloques_rfv())
            if ((resumen.get("pnd") or {}).get("rfv_prima") or {}).get("aplica") else "")),
        ("Factores de la RFV (metodologia del area)", _texto_factores_rfv((resumen.get("pnd") or {}).get("rfv_prima") or {})),
        ("Insumos del area (Fianzas)", _texto_insumos_fianzas((resumen.get("pnd") or {}).get("rfv_prima") or {})),
        ("Backtesting Fianzas", (((resumen.get("pnd") or {}).get("backtesting_rfv") or {}).get("estado") or "-")
         + (f"; renglones '{BACKTESTING_ETIQUETA} <concepto>' al final de {HOJA_MONTOS} de la BD de RFV; hojas "
            "Backtesting_Resumen y Backtesting_Mensual (Libro FIANZAS)"
            if ((resumen.get("pnd") or {}).get("backtesting_rfv") or {}).get("proy") else "")),
        ("BEL del metodo del area", (resumen.get("pnd") or {}).get("sin_metodo_area")
         or (resumen.get("pnd") or {}).get("metodo_area") or "-"),
        ("Tiempo de ejecucion (s)", f"{resumen.get('segundos', 0):,.0f}"),
        ("", ""),
        ("METODOLOGIA", ""),
        ("1. Coherencia contable", "Se proyectan drivers (BEL / BRUTO y razones) y se derivan las demas lineas: "
                                   "RRC: BRUTO = BEL+GTO+MR, IRR = %ces*BRUTO, NETO = BRUTO-IRR; SONR: BRUTO = BEL+MR; "
                                   + (f"RFV: BRUTO = PRIMA {MESES_PRIMA_RFV}M x FRV / TC (RFV por prima), IRR = "
                                      "BRUTO x CESION, NETO = BRUTO-IRR; "
                                      if ((resumen.get("pnd") or {}).get("rfv_prima") or {}).get("aplica") else
                                      "RFV: NETO = BRUTO-IRR; ")
                                   + "RCONT: total repartido por ramo con la mezcla de los ultimos 8 meses."),
        ("2. Modelo", "Montos, indices y LAGs: linea de tendencia historica (regresion lineal, en logaritmos cuando "
                      f"la serie es positiva) sobre los ultimos {MESES_TENDENCIA or 'N/A'} meses, continuada desde el "
                      "ultimo dato real: la proyeccion sale paralela a la linea de tendencia de Excel y arranca del "
                      "ultimo real. En " + ("los montos" if tuple(TIPOS_CON_ESTACIONALIDAD) == ("nivel",) else
                                             " e ".join(TIPOS_CON_ESTACIONALIDAD)) + " se suma ademas el patron por mes del ano (estacionalidad "
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
                      "ultimo real) y la pendiente se proyecta completa. "
                      + _razones_modelo_txt()
                      + "BEL por FND (Danos): FND con Holt amortiguado con guardia de saltos (serie de tiempo: "
                      f"nivel = ultimo real, tendencia = promedio exponencial de los cambios mensuales, beta {HOLT_FND['beta']}, "
                      f"amortiguada {HOLT_FND['phi']} por mes; un salto de mas de {HOLT_FND['k_salto']:.0f} MAD mueve el nivel "
                      "y no la tendencia; tope al rango de 36 meses; " + ("con" if "fnd" in TIPOS_CON_ESTACIONALIDAD else "sin")
                      + " el patron del mes), "
                      + (f"{_factores_fijos_txt()} fijos en su ultimo real (FACTORES_BEL_FIJOS), " if _factores_fijos_txt() else "")
                      + (f"{_factores_fijos_txt(False)} con la pendiente combinada (ver 'Pendiente proyectada'), "
                         + ("con" if "factor_log" in TIPOS_CON_ESTACIONALIDAD else "sin") + " patron del mes, "
                         if _factores_fijos_txt(False) else "")
                      + "y CESION con SES"
                      + (" salvo los ramos con indicacion del area (ver 'Cesion por indicacion del area')" if CESION_OBJETIVO or CESION_TENDENCIA else "")
                      + ". RCONT: "
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
        ("6. Reglas", "Ramos estatutarios (" + ", ".join(RAMOS_ESTATUTARIOS) + "; IS y LAGs de la CNSF) -> indices y "
                      "LAGs fijos en el ultimo valor real; "
                      "series en cero -> 0; parametros en escalon -> ultimo valor; dominio actuarial (cesion en "
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
                               "pendiente de reportar segun los LAG (PDP), RFV con la prima de 12 meses en pesos (con "
                               "USAR_RFV_POR_PRIMA, en los ramos y meses con RFV por prima la RFV BRUTO de la BD sale de "
                               "ahi, no de este factor). El "
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
    _hojas_pnd(wb, resumen.get("pnd") or {}, negrita, encab)

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


def _hojas_pnd(wb, diag: dict, negrita, encab):
    """Hojas de los escenarios PND / PD: resumen (estado, backtest por escenario, totales y detalle por serie), la base
    implicita y los factores mes a mes (historia y proyeccion) y el backtest por serie y corte; y las del BEL por FND."""
    def hojas_fnd():
        fnd = (diag or {}).get("bel_fnd") or {}
        if (diag or {}).get("indicadores_ramo"):        # (lo lee el tablero: seccion Razones)
            _hoja_filas(wb, HOJA_INDICADORES_RAMO, diag["indicadores_ramo"], negrita, encab,
                        {**{c: COLUMNAS_INDICES_PND.get(c, "0.0000") for c in COLUMNAS_TABLERO_PND},
                         **{f"{c} {SUFIJO_METODO_AREA}": COLUMNAS_INDICES_PND.get(c, "0.0000") for c in COLUMNAS_METODO_AREA},
                         "BEL": "#,##0", "BRUTO": "#,##0"})
        if (diag or {}).get("is_fa_comp"):
            _hoja_filas(wb, "IS_FA_Comparativo", diag["is_fa_comp"], negrita, encab,
                        {"IS (FA)": "0.00%", "IS (RL)": "0.00%", "Diferencia": "0.00"})
        if fnd.get("resumen") or fnd.get("series"):
            _hoja_filas(wb, "BEL_FND_Resumen", fnd.get("resumen") or [], negrita, encab,
                        {"Cambio mensual de la tendencia del FND": "0.0000", "FACTOR GTO cambio": "0.000%",
                         "FACTOR MR cambio": "0.000%", "CESION cambio": "0.00%", "FND": "0.0000", "Error": "0.0",
                         "BEL": "#,##0"})
            _hoja_filas(wb, "BEL_FND_Mensual", fnd.get("series") or [], negrita, encab,
                        {"IS": "0.0000", "FND": "0.0000", "PEACUMULADA": "#,##0", "BEL": "#,##0"})
        rfv_ = (diag or {}).get("rfv_prima") or {}
        if rfv_.get("resumen") or rfv_.get("series"):
            fmt_fac = {"%": "0.00%", "FPR": "0.00%", "RC": "0.00%", "PD": "0.000%", "FCR": "0.000%", "Cesion": "0.00%",
                       "FV": "0.0000"}
            _hoja_filas(wb, "RFV_Prima_Resumen", rfv_.get("resumen") or [], negrita, encab,
                        {"FRV error": "0.0", "CESION error": "0.0", "FRV": "0.0000", "CESION": "0.00%", "RFV": "#,##0",
                         **fmt_fac})
            _hoja_filas(wb, "RFV_Prima_Mensual", rfv_.get("series") or [], negrita, encab,
                        {"PT": "#,##0", "PRIMA": "#,##0", "FRV": "0.0000", "CESION": "0.00%", "TC": "0.0000",
                         "RFV": "#,##0", **fmt_fac})
            if FACTORES_RFV and (rfv_.get("pdinfo") or {}).get("diag"):
                _hoja_filas(wb, "RFV_Metodo_Area", rfv_["pdinfo"]["diag"], negrita, encab,
                            {"RVABRUTA": "#,##0", "RFV BRUTO": "#,##0", "Diferencia": "0.0%", "PRIMA": "#,##0",
                             "FACTOR": "0.0000", "PERMANENCIA": "0.0000", "CASTIGO": "#,##0", "PD": "0.000%",
                             "RC": "0.00%", "CESION": "0.00%", "RVACONT /": "0.00%", "RVACONT": "#,##0"})
            if FACTORES_RFV and rfv_.get("insumos"):
                _hoja_filas(wb, "RFV_Insumos_Area", rfv_["insumos"], negrita, encab,
                            {"MA (MXN)": "#,##0", "OMEGA": "0.00%", "ALFA": "0.00%", "RFV MA =": "#,##0",
                             "RFV BRUTO": "#,##0", "RFV MA /": "0.0%", "FACTOR MA": "0.00", "PD": "0.000%"})
            if FACTORES_RFV and ((rfv_.get("csu") or {}).get("detalle") or rfv_.get("cobertura")):
                _hoja_filas(wb, "RFV_CSU_Cobertura",
                            [{"Tabla": "Comision sobre utilidades (no entra al FPR)", **d}
                             for d in (rfv_.get("csu") or {}).get("detalle") or []]
                            + [{"Tabla": "Proporcional de Mexico sin monto afianzado en el CSV", **d}
                               for d in rfv_.get("cobertura") or []], negrita, encab,
                            {"Prima": "#,##0", "%": "0.00%", "Comision": "#,##0"})
        bt_ = (diag or {}).get("backtesting") or {}
        bt_f = (diag or {}).get("backtesting_rfv") or {}
        if bt_.get("resumen") or bt_f.get("resumen"):
            libros = [("DANOS", bt_), ("FIANZAS", bt_f)]
            _hoja_filas(wb, "Backtesting_Resumen", [{"Libro": lib, **f} for lib, b_ in libros
                                                    for f in b_.get("resumen") or []], negrita, encab,
                        {"Error": "0.0%", "Sesgo": "0.0%", "Dif": "0.0%", "Real": "#,##0", "Backtesting": "#,##0",
                         "Proyeccion": "#,##0"})
            _hoja_filas(wb, "Backtesting_Mensual", [{"Libro": lib, **f} for lib, b_ in libros
                                                    for f in b_.get("mensual") or []], negrita, encab,
                        {"Backtesting": "#,##0", "Referencia": "#,##0", "Diferencia %": "0.0%", "Diferencia": "#,##0"})
    if not diag or not (diag.get("mensual") or diag.get("resumen")):
        hojas_fnd()
        return
    ws = wb.create_sheet("PND_Resumen")
    fila = 1
    bloques = [("Estado", [{"Escenarios PND / PD": diag.get("estado", ""), "PE FCST (FCST)": diag.get("pe_fcst", ""),
                            "PE historica (PExRamo)": diag.get("pe_ramo", ""),
                            "PE entre PExRamo y el FCST": diag.get("pe_reforecast", ""),
                            "IS de la funcion actuarial (IS (FA))": diag.get("is_fa", ""),
                            "BEL por FND": (diag.get("bel_fnd") or {}).get("estado", "")}]),
               ("Backtest agrupado por escenario y reserva (error %: la recta, tendencia historica, contra el escenario, "
                "con el indice proyectado desde cada corte. 'Escenario' usa la prima que si se emitio despues del "
                "corte (cota optimista); 'con prima plana' la deja en su valor al corte (cota pesimista))",
                diag.get("decision")),
               ("Totales de todos los ramos (USD). 'BD principal' = lo que lleva la BD principal (con el BEL por FND "
                "donde aplica, seccion 2i); 'Modelo (antes del BEL por FND)' = la recta o el factor de prima segun la "
                "seccion 2g", diag.get("totales")),
               ("Detalle por serie", diag.get("resumen"))]
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
        _formatear(ws, enc_fila, {"Error": "0.0", "FA": "0.0000", "FG": "0.0000", "FM": "0.0000", "Rho": "0.00",
                                  "Ind": "0.0000", "LAG": "0.0000", "BEL": "#,##0", "GTO": "#,##0", "MR": "#,##0", "NETO": "#,##0",
                                  "Real": "#,##0", "BD principal": "#,##0", "PE": "#,##0"}, fila)
        fila += 2
    ws.column_dimensions["A"].width = 26
    _hoja_filas(wb, "PND_Mensual", diag.get("mensual") or [], negrita, encab,
                {"GTO /": "0.0000", "MR /": "0.0000", "Ind": "0.0000", "LAG": "0.0000", "PND": "#,##0", "PD": "#,##0", "BEL": "#,##0",
                 "GTO": "#,##0", "MR": "#,##0", "Prima": "#,##0", "FA": "0.0000"})
    _hoja_filas(wb, "PND_Backtest", diag.get("backtest") or [], negrita, encab,
                {"BEL": "0.0", "GTO": "0.0", "MR": "0.0", "BRUTO": "0.0"})
    hojas_fnd()


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
    print(f"Proyeccion {periodos_proy[0]} - {periodos_proy[-1]} ({h} meses). Historia hasta {ultimo}. Version del codigo "
          f"{VERSION_CODIGO}.", flush=True)
    for ruta in (ARCHIVO_BD_DANOS, ARCHIVO_BD_RFV):
        if not ruta.exists():
            raise SystemExit(f"Falta {ruta}: copia la BD (Fianzas ya llena) a la carpeta entradas/.")
    salidas = ([SALIDA_BD_DANOS, SALIDA_BD_RFV, SALIDA_DIAGNOSTICO] + ([SALIDA_GRAFICAS] if GENERAR_GRAFICAS else [])
               + ([SALIDA_DASHBOARD, SALIDA_DASHBOARD_HTML] if GENERAR_DASHBOARD else [])
               + ([ruta_escenario_pnd(e) for e in ESCENARIOS_PND] if USAR_ESCENARIOS_PND else []))
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
    if FACTORES_BEL_FIJOS:                             # margenes del modelo (ramos sin BEL por FND) en su ultimo real
        fijar_margenes_modelo(resultados, h)

    # factor de prima: las reservas que dependen de la prima se escriben como factor x exposicion de prima
    ppto = leer_presupuesto()
    tc_primas = {**bd_danos.tc, **bd_rfv.tc, **(tc_hist.get("FIANZAS") or leer_tc_real(bd_rfv, ultimo))}
    tc_primas.update({p: tc_para_periodo(bd_rfv, p) for p in periodos_proy})
    pr, diag_factor = None, {"estado": "apagado (USAR_FACTOR_PRIMA = False)"}
    error_lectura = ""                     # por que no hay primas (lo usan el factor y los escenarios PND)
    if USAR_FACTOR_PRIMA or USAR_ESCENARIOS_PND:
        print("Primas ...", flush=True)
        if primas is None:
            error_lectura = f"no se pudo cargar primas.py ({_ERROR_PRIMAS})"
        else:
            try:
                pr = primas.leer_primas(ultimo, periodos_proy[-1], primas.lineas_del_dashboard(ppto), tc_primas)
            except Exception as e:  # noqa: BLE001
                pr = None
                error_lectura = f"no se pudieron leer las primas ({type(e).__name__}: {e})"
                alertas.append(("PRIMAS", "Lectura", error_lectura))
                print(f"   AVISO: {error_lectura}", flush=True)
            for a in (pr.avisos if pr is not None else []):
                alertas.append(("PRIMAS", "Primas", a))
                print(f"   AVISO {a}", flush=True)
    if USAR_FACTOR_PRIMA:
        print("Factor de prima ...", flush=True)
        if error_lectura:
            diag_factor = {"estado": f"{error_lectura}: se usa la recta"}
        else:
            respaldo = {k: (list(r.pronostico), list(r.li), list(r.ls), r.modelo, list(r.alertas), r.error_modelo,
                            r.error_ultimo_valor, r.error_ses, r.n_cortes)
                        for k, r in resultados.items() if r.tipo == "nivel"}
            n0 = len(alertas)
            try:
                diag_factor = aplicar_factor_prima(resultados, pr, hp, tc_primas, {"DANOS": bd_danos, "FIANZAS": bd_rfv},
                                                   periodos_proy, ultimo, alertas)
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
    rangos_danos = aplicar_rango_esperado(proy_danos, bd_danos, "DANOS", ESTRUCTURA["DANOS"], resultados,
                                          periodos_proy, ultimo, alertas)
    n_al_rango = len(alertas)
    proy_rfv_sin_rango = dict(proy_rfv)                # (si la RFV va por prima, el rango no se aplica: se restaura)
    res_rfv_sin_rango = {k: (list(r.pronostico), list(r.li), list(r.ls), list(r.alertas), dict(r.parametros))
                         for k, r in resultados.items() if k[0] == "FIANZAS"}
    rangos_rfv = aplicar_rango_esperado(proy_rfv, bd_rfv, "FIANZAS", ESTRUCTURA["FIANZAS"], resultados,
                                        periodos_proy, ultimo, alertas)
    alertas_rango_rfv = list(range(n_al_rango, len(alertas)))   # (se reetiquetan si la RFV va por prima)
    resumen_rangos = rangos_danos + rangos_rfv
    validar(proy_danos, proy_rfv)
    # escenarios PND / PD (Danos): cada uno en su archivo; la BD principal solo cambia con BD_CON_ESCENARIO_PND
    diag_pnd = {"estado": "apagado (USAR_ESCENARIOS_PND = False)"}
    if USAR_ESCENARIOS_PND:
        print("Escenarios PND / PD (Danos) ...", flush=True)
        n0 = len(alertas)
        try:
            diag_pnd = escenarios_pnd(bd_danos, hp, resultados, pr, proy_danos, periodos_proy, ultimo, alertas,
                                      motivo_sin_prima=error_lectura)
        except Exception as e:  # noqa: BLE001
            del alertas[n0:]
            diag_pnd = {"estado": f"error en los escenarios PND ({type(e).__name__}: {e}); no se generan"}
            alertas.append(("PND", "Escenarios PND", diag_pnd["estado"]))
        print(f"   {diag_pnd['estado']}", flush=True)
        if BD_CON_ESCENARIO_PND:
            if BD_CON_ESCENARIO_PND in (diag_pnd.get("proy") or {}):
                proy_danos = diag_pnd["proy"][BD_CON_ESCENARIO_PND]
                alertas.append(("PND", "BD principal", f"La BD de Danos usa el escenario {BD_CON_ESCENARIO_PND} "
                                                       "(BD_CON_ESCENARIO_PND) en las series donde aplica"))
            else:
                alertas.append(("PND", "BD principal", f"BD_CON_ESCENARIO_PND = {BD_CON_ESCENARIO_PND} pero el escenario "
                                                       "no se pudo calcular: la BD de Danos queda con el modelo actual"))
        validar(proy_danos, proy_rfv)
    comparativo = comparar_factor(resultados, diag_factor, pr, tc_primas, {"DANOS": bd_danos, "FIANZAS": bd_rfv},
                                  {"DANOS": proy_danos, "FIANZAS": proy_rfv}, periodos_proy, tc_hist, ultimo, sin_rango)
    actualizar_finales_factor(diag_factor, resultados, periodos_proy)
    # PE por ramo y mes (PExRamo y FCST) y BEL por FND (BEL = IS x PEACUMULADA x FND desde el primer mes proyectado)
    pef = pe_ramo = None
    try:
        pef = leer_pe_fcst()
    except Exception as e:  # noqa: BLE001
        diag_pnd["pe_fcst"] = f"no se pudo leer {ARCHIVO_PE_FCST.name} ({type(e).__name__}: {e}); sin PE del FCST"
        alertas.append(("PND", "PE FCST", diag_pnd["pe_fcst"]))
    if pef is not None:
        diag_pnd["pe_fcst"] = (
            f"{pef['ruta'].name} › CtaMens: {pef['renglones']:,} renglones, {pef['usados']:,} con la cuenta "
            f"{CUENTA_PE_FCST} de ramos de la BD; meses {pef['periodos'][0]} a {pef['periodos'][-1]}; "
            f"{pef['control']}; fuera de la BD de Danos: "
            + (", ".join(f"{k} ({v / 1e6:,.1f} M USD)" for k, v in sorted(pef["fuera"].items())) or "nada"))
        for a in pef["avisos"]:
            alertas.append(("PND", "PE FCST", a))
    elif "pe_fcst" not in diag_pnd:
        diag_pnd["pe_fcst"] = f"no se encontro {ARCHIVO_PE_FCST.name} en entradas/"
        alertas.append(("PND", "PE FCST", diag_pnd["pe_fcst"]))
    try:
        pe_ramo = leer_pe_ramo(tc_primas)
    except Exception as e:  # noqa: BLE001
        diag_pnd["pe_ramo"] = f"no se pudo leer la base PExRamo ({type(e).__name__}: {e})"
        alertas.append(("PND", "PExRamo", diag_pnd["pe_ramo"]))
    pe_rf, pe_rfa = {}, None
    try:
        pe_rfa = leer_pe_rfcst_fa(tc_primas)
    except Exception as e:  # noqa: BLE001
        diag_pnd["pe_rfcst_fa"] = (f"no se pudo leer el reforecast por mes y ramo ({PATRON_PE_RFCST_FA}: "
                                   f"{type(e).__name__}: {e}); sep-dic sale del reforecast por grupo de primas.py")
        alertas.append(("PND", "PE reforecast", diag_pnd["pe_rfcst_fa"]))
    if pe_rfa is not None:
        for a in pe_rfa["avisos"]:
            alertas.append(("PND", "PE reforecast", a))
    if pe_ramo is not None and pe_ramo["periodos"]:
        # control: PExRamo en USD contra la prima real por grupo del proyecto, en los meses que comparten
        control = ""
        if pr is not None and primas is not None:
            difs = []
            for p in pe_ramo["periodos"]:
                if p not in pr.mensual.index:
                    continue
                for g in pr.mensual.columns:
                    if str(pr.fuente.at[p, g]) != "real" or float(pr.mensual.at[p, g]) <= 1e6:
                        continue
                    v = sum(x for (r, q), x in pe_ramo["mensual"].items()
                            if q == p and primas.GRUPO_DE_RAMO_RESERVA.get(r) == g)
                    if v:
                        difs.append(abs(v / float(pr.mensual.at[p, g]) - 1))
            if difs:
                control = (f"; contra la prima real por grupo del proyecto ({len(difs)} grupo-mes con mas de 1 M USD): "
                           f"diferencia mediana {np.median(difs):.1%}, maxima {max(difs):.1%}")
        diag_pnd["pe_ramo"] = (
            f"{pe_ramo['ruta'].name}: {pe_ramo['renglones']:,} renglones, meses {pe_ramo['periodos'][0]} a "
            f"{pe_ramo['periodos'][-1]}, en {MONEDA_PE_RAMO} convertidos a USD con el TC de cada mes"
            + (f"; {'; '.join(pe_ramo['avisos'])}" if pe_ramo.get("avisos") else "")
            + f"; subramos repartidos entre TEV e Hidro: {pe_ramo['repartidos'] / 1e6:,.1f} M USD"
            + "; fuera de la BD de Danos: " + (", ".join(f"{k} ({v / 1e6:,.1f} M USD)"
                                                         for k, v in sorted(pe_ramo["fuera"].items())) or "nada")
            + control)
        for a in pe_ramo.get("avisos") or []:
            alertas.append(("PND", "PExRamo", a))
        # meses entre PExRamo y el FCST: reforecast del ano por mes y ramo (PATRON_PE_RFCST_FA) o, si no esta, el
        # reforecast por grupo de primas.py
        desde = _mes_menos(pe_ramo["periodos"][-1], -1)
        hasta = _mes_menos(pef["periodos"][0], 1) if pef else periodos_proy[-1]
        if desde > hasta:
            diag_pnd["pe_reforecast"] = (f"sin meses entre PExRamo (hasta {pe_ramo['periodos'][-1]}) y el FCST (desde "
                                         f"{pef['periodos'][0] if pef else '-'}): no hace falta reforecast")
        else:
            pe_rf = pe_reforecast(pr, pe_ramo["mensual"], desde, hasta)
            meses_fa = [p for p in rango_periodos(desde, hasta) if pe_rfa and p in pe_rfa["periodos"]]
            txt_fa = ""
            if meses_fa:
                nombre = pe_rfa["ruta"].name
                fa, ramos_fa = repartir_grupos({k: v for k, v in pe_rfa["mensual"].items() if k[1] in meses_fa},
                                               pe_ramo["mensual"])
                antes = sum(v for (_, q), v in pe_rf.items() if q in meses_fa)
                pe_rf = {k: v for k, v in pe_rf.items() if k[1] not in meses_fa}
                perfilados, txt_perfil = [], ""
                if PERFIL_REFORECAST == "FCST" and pef is not None:
                    grupos_mz = {}
                    if primas is not None:
                        for g in GRUPOS_CON_MEZCLA:
                            rs = [x for x in MAPA_RAMO_LAG if primas.GRUPO_DE_RAMO_RESERVA.get(x) == g]
                            grupos_mz.update({x: rs for x in rs})
                    archivo_fa = dict(fa)
                    fa, perfilados = perfilar_reforecast(fa, meses_fa, pef["mensual"], grupos_mz)
                    if perfilados:
                        cambios = ", ".join(f"{r}: " + "/".join(f"{archivo_fa.get((r, q), 0.0) / 1e6:.1f}" for q in meses_fa)
                                            + " -> " + "/".join(f"{fa.get((r, q), 0.0) / 1e6:.1f}" for q in meses_fa)
                                            for r in perfilados)
                        txt_perfil = (f"; PERFIL_REFORECAST: el total de {meses_fa[0]} a {meses_fa[-1]} de cada ramo se "
                                      f"reparte entre esos meses con la mezcla mensual de los mismos meses del FCST "
                                      f"{pef['periodos'][0] // 100} (el archivo concentra la prima en uno o dos meses y "
                                      f"deja casi vacios los ultimos); M USD por mes, archivo -> perfilado: {cambios}")
                pe_rf.update({(r, p): (v, f"{nombre} (total del grupo repartido con la mezcla de PExRamo)"
                                       if r in ramos_fa else nombre) for (r, p), v in fa.items()})
                if perfilados:
                    pe_rf.update({(r, p): (v, f"{pe_rf[(r, p)][1]}; meses perfilados con el FCST")
                                  for (r, p), v in fa.items() if r in perfilados})
                tcs, tca = pe_rfa["tc_usado"], pe_rfa["tc_archivo"]
                tc_txt = ", ".join(f"{p} {tcs[p]:.4f}" for p in meses_fa if tcs[p])
                tca_txt = ", ".join(f"{p} {tca[p]:.4f}" for p in meses_fa if p in tca)
                moneda = (f"Primas Tomadas MXN / TC del proyecto ({tc_txt}; el archivo trae TC {tca_txt})"
                          if MONEDA_PE_RFCST_FA == "MXN" else f"Primas Tomadas USD del archivo (TC del archivo {tca_txt})")
                otros = [p for p in pe_rfa["periodos"] if p not in meses_fa]
                fuera_fa = {}
                for (r, p), v in pe_rfa["fuera"].items():
                    if p in meses_fa:
                        fuera_fa[r] = fuera_fa.get(r, 0.0) + v
                despues = sum(v for (_, q), v in fa.items() if q in meses_fa)
                txt_fa = (f"{meses_fa[0]} a {meses_fa[-1]}: {nombre} › {pe_rfa['hoja']}, reforecast por mes y ramo "
                          f"({pe_rfa['renglones']:,} renglones, todas las Tipo Rea ("
                          + ", ".join(f"{k}: {v}" for k, v in sorted(pe_rfa["por_tipo"].items(), key=lambda x: str(x[0])))
                          + f") y Susc; {moneda}); {pe_rfa['control']}; Danos {despues / 1e6:,.1f} M USD en esos meses "
                          f"(el reforecast por grupo de primas.py daba {antes / 1e6:,.1f} M)"
                          + (f"; ramos {', '.join(ramos_fa)}: total de su grupo repartido con la mezcla de PExRamo de "
                             "los ultimos 12 meses (GRUPOS_CON_MEZCLA)" if ramos_fa else "")
                          + (f"; meses del archivo que no se usan (real o FCST): {', '.join(map(str, otros))}" if otros else "")
                          + "; fuera de la BD de Danos: " + (", ".join(f"{k} ({v / 1e6:,.1f} M USD)" for k, v in
                                                                      sorted(fuera_fa.items())) or "nada")
                          + txt_perfil)
            cub = sorted({p for _, p in pe_rf})
            falta = [p for p in rango_periodos(desde, hasta) if p not in cub]
            de_primas = [p for p in cub if p not in meses_fa]
            diag_pnd["pe_reforecast"] = (
                "; ".join(x for x in (
                    txt_fa,
                    (f"{de_primas[0]} a {de_primas[-1]}: reforecast del ano por grupo (primas.py), 30 y 70 repartidos con "
                     "la mezcla de PExRamo de los ultimos 12 meses" if de_primas else "")) if x)
                or "sin reforecast (sin bases de primas)")
            diag_pnd["pe_reforecast"] += (f"; {falta[0]} a {falta[-1]} sin PE (ni reforecast ni FCST): el BEL de esos "
                                          "meses sigue con el modelo" if falta else "")
            if pe_rfa is None and not diag_pnd.get("pe_rfcst_fa"):
                diag_pnd["pe_reforecast"] += (f"; no se encontro el reforecast por mes y ramo ({PATRON_PE_RFCST_FA}) en "
                                              "entradas/")
            if falta:
                alertas.append(("PND", "PE por ramo", diag_pnd["pe_reforecast"]))
            anio = PERIODO_FIN // 100
            if pef is None and any(p // 100 == anio for p in cub):   # sin FCST: el ano sale del presupuesto parejo
                perfil = (getattr(pr, "perfil", None) or {}).get("elegido", "") if pr is not None else ""
                diag_pnd["sin_fcst"] = (f"SIN FCST: {diag_pnd.get('pe_fcst', '')}. La PE de {anio} sale del presupuesto "
                                        f"de primas.py por grupo repartido a meses con el perfil de la prima"
                                        + (f" ({perfil})" if perfil else "") + ", no del FCST mes a mes (con el perfil "
                                        "parejo, el mismo monto cada mes). Copia el FCST en entradas/ y revisa que se "
                                        "pueda leer (python-calamine)")
                alertas.append(("PND", "PE FCST", diag_pnd["sin_fcst"]))
    elif "pe_ramo" not in diag_pnd:
        diag_pnd["pe_ramo"] = f"no se encontro la base {PATRON_PE_RAMO} en entradas/: sin PE historica por ramo"
        alertas.append(("PND", "PExRamo", diag_pnd["pe_ramo"]))
    if pef is not None and pe_ramo is not None and GRUPOS_CON_MEZCLA:
        mensual_rep, ramos_rep = repartir_grupos(pef["mensual"], pe_ramo["mensual"])
        if ramos_rep:
            pef = {**pef, "mensual": mensual_rep,
                   "fuente_ramo": {r: f"{pef['ruta'].name} (total del grupo repartido con la mezcla de PExRamo)"
                                   for r in ramos_rep}}
            diag_pnd["pe_fcst"] += (f"; ramos {', '.join(ramos_rep)}: total de su grupo en el FCST repartido con la "
                                    "mezcla de PExRamo de los ultimos 12 meses (GRUPOS_CON_MEZCLA)")
    capturas_pe = leer_capturas_pe(bd_danos)
    pe_mes = pe_por_mes(pe_ramo, pef, pe_rf, capturas_pe)
    n_cap = sum(1 for v in pe_mes.values() if v[1].startswith("captura"))
    if n_cap:
        diag_pnd["pe_ramo"] = diag_pnd.get("pe_ramo", "") + f"; {n_cap} mes(es) con PE capturada en la BD de entrada"
    # salto de nivel entre la historia y la PE del reforecast / FCST (p. ej. otra definicion del ramo)
    if pe_ramo is not None and pe_ramo["periodos"] and pef is not None:
        p12 = _suma_12(pe_mes)
        u, fin = pe_ramo["periodos"][-1], pef["periodos"][-1]
        for r in bd_danos.cols_ramo:
            a_, b_ = p12.get((r, u)), p12.get((r, fin))
            if a_ and b_ is not None and a_ > 1e6 and not (0.5 <= b_ / a_ <= 2.0):
                alertas.append(("PND", f"PE ramo {r}", f"la PE de 12 meses pasa de {a_ / 1e6:,.1f} M USD (PExRamo a "
                                f"{u}) a {b_ / 1e6:,.1f} M (a {fin}, reforecast y FCST): revisar si es un cambio real o "
                                "de definicion; el BEL por FND lo sigue"))
    print(f"   PE FCST (FCST): {diag_pnd['pe_fcst']}", flush=True)
    print(f"   PE historica (PExRamo): {diag_pnd['pe_ramo']}", flush=True)
    if diag_pnd.get("sin_fcst"):
        print(f"   AVISO: {diag_pnd['sin_fcst']}", flush=True)
    if not pe_mes:
        no_leidos = [k for k in ("pe_ramo", "pe_fcst") if str(diag_pnd.get(k, "")).startswith("no se pudo leer")]
        diag_pnd["sin_pe"] = (f"SIN PRIMA POR RAMO (PExRamo: {diag_pnd.get('pe_ramo', '')}; FCST: "
                              f"{diag_pnd.get('pe_fcst', '')}). PE FCST, PRIMA N AÑOS, PEACUMULADA y FD/FND van en "
                              f"{TEXTO_SIN_DATO} y el BEL por FND no aplica. "
                              + ("Corrige lo que impidio leer el archivo (motivo arriba)" if no_leidos else
                                 f"Copia la base PExRamo y {ARCHIVO_PE_FCST.name} en {ENTRADAS}"))
        alertas.append(("PND", "PE por ramo", diag_pnd["sin_pe"]))
        print(f"   AVISO: {diag_pnd['sin_pe']}", flush=True)
    if diag_pnd.get("pe_reforecast"):
        print(f"   PE entre PExRamo y el FCST: {diag_pnd['pe_reforecast']}", flush=True)
    # IS de la funcion actuarial (bloque IS (FA); solo se muestra) y su comparativo contra el IS (RL)
    is_fa = None
    try:
        is_fa = leer_is_fa()
    except Exception as e:  # noqa: BLE001
        diag_pnd["is_fa"] = (f"no se pudo leer el archivo de la funcion actuarial ({PATRON_IS_FA}: {type(e).__name__}: "
                             f"{e}); el bloque IS (FA) va en {TEXTO_SIN_DATO}")
        alertas.append(("PND", "IS (FA)", diag_pnd["is_fa"]))
    if is_fa is not None:
        ramos_bd = list(bd_danos.cols_ramo)
        sin_fa = [r for r in ramos_bd if r not in is_fa["ramos"]]
        fuera_fa = [r for r in is_fa["ramos"] if r not in ramos_bd]
        diag_pnd["is_fa"] = (
            f"{is_fa['ruta'].name} › {is_fa['hoja']}: {is_fa['renglones']:,} renglones, "
            + (f"{is_fa['omitidos']} omitidos sin Ramo o MesProc validos" if is_fa["omitidos"] else "sin filtros")
            + "; ramos "
            f"{', '.join(is_fa['ramos'])}; meses {is_fa['periodos'][0]} a {is_fa['periodos'][-1]} ("
            + "; ".join(f"{t}: {m[0]} a {m[-1]}" for t, m in is_fa["por_tipo"].items()) + "); "
            + " y ".join(f"{c} en {p}" for p, c in COLUMNA_IS_FA.items())
            + (f"; ramos de la BD sin indice ({TEXTO_SIN_DATO}): {', '.join(sin_fa)}" if sin_fa else "")
            + (f"; ramos del archivo que no estan en la BD de Danos: {', '.join(fuera_fa)}" if fuera_fa else "")
            + f"; antes de {is_fa['periodos'][0]}: {TEXTO_SIN_DATO}")
        for a in is_fa["avisos"]:
            alertas.append(("PND", "IS (FA)", a))
        if sin_fa:
            alertas.append(("PND", "IS (FA)", f"la funcion actuarial no trae indice de los ramos {', '.join(sin_fa)}: su "
                                              f"bloque IS (FA) va en {TEXTO_SIN_DATO}"))
        if fuera_fa:
            alertas.append(("PND", "IS (FA)", f"ramos del archivo que no estan en la BD de Danos (no entran al bloque): "
                                              f"{', '.join(fuera_fa)}"))
        pos_proy = {p: i for i, p in enumerate(periodos_proy)}
        comp = []
        for pref in COLUMNA_IS_FA:
            for r in [x for x in ramos_bd if x in is_fa["ramos"]]:
                for p in is_fa["periodos"]:
                    v = is_fa["val"].get((pref, r, p))
                    if v is None:
                        continue
                    rl, _ = _hp_fuente(hp, resultados, MAPA_RAMO_LAG.get(str(r)), INDICE_BASE_PND[pref][0], p, pos_proy)
                    comp.append({"Reserva": pref, "Ramo": r, "Periodo": p, "Tipo (FA)": is_fa["tipo"].get((pref, r, p)),
                                 "IS (FA)": v, "IS (RL)": rl if np.isfinite(rl) else None,
                                 "Diferencia FA - RL (puntos %)": (v - rl) * 100 if np.isfinite(rl) else None})
        diag_pnd["is_fa_comp"] = comp
    elif "is_fa" not in diag_pnd:
        parecidos = sorted(c.name for c in (ENTRADAS.iterdir() if ENTRADAS.exists() else [])
                           if c.suffix.lower() in (".xlsx", ".xlsm", ".xls") and not c.name.startswith("~$")
                           and ("fa" in c.stem.lower() or "ppto" in c.stem.lower()))
        diag_pnd["is_fa"] = (f"no se encontro {PATRON_IS_FA} en entradas/: el bloque IS (FA) va en {TEXTO_SIN_DATO}"
                             + (f" (en entradas/ hay {', '.join(parecidos)}; el nombre debe empezar con PPTO y llevar "
                                "FA, y ser .xlsx)" if parecidos else ""))
        alertas.append(("PND", "IS (FA)", diag_pnd["is_fa"]))
    if is_fa is None:
        diag_pnd["sin_is_fa"] = f"SIN IS (FA): {diag_pnd['is_fa']}"
        print(f"   AVISO: {diag_pnd['sin_is_fa']}", flush=True)
    else:
        print(f"   IS de la funcion actuarial: {diag_pnd['is_fa']}", flush=True)
    info_fnd = {"estado": "apagado (USAR_BEL_POR_FND = False)", "aplica": set(), "fnd": {}, "series": [], "resumen": []}
    proy_modelo = proy_danos
    bel_area = {}
    if USAR_BEL_POR_FND:
        print("BEL por FND (Danos) ...", flush=True)
        info_area = {}
        try:                                              # (una falla aqui no apaga el BEL por FND de las demas)
            bel_area = leer_bel_metodo_area(ultimo, alertas, info_area)
        except Exception as e:  # noqa: BLE001
            bel_area = {}
            info_area["motivos"] = {k: f"no se pudieron leer los Res_Rvas ({type(e).__name__}: {e})"
                                    for k in _bel_metodo_area()}
            alertas.append(("PND", "BEL del metodo del area", f"no se pudo leer ({type(e).__name__}: {e}); las series de "
                            "BEL_METODO_AREA siguen con su historia de la BD"))
        for (pref_a, r_a) in _bel_metodo_area():
            d_a = bel_area.get((pref_a, r_a))
            texto_a = (f"{d_a['renglones']} renglones de {', '.join(d_a['archivos'])} (hoja Base {pref_a}, escenarios "
                       f"{', '.join(str(e) for e in _bel_metodo_area()[(pref_a, r_a)])}, BEL / MR / BRUTO / IRR hasta "
                       f"{ultimo}), {len(d_a['meses'])} meses con BEL ({d_a['meses'][0]} a {d_a['meses'][-1]})"
                       if d_a else (info_area.get("motivos") or {}).get((pref_a, r_a), "sin datos"))
            print(f"   BEL del metodo del area {pref_a} {r_a}: {texto_a}", flush=True)
        try:
            info_fnd = calcular_bel_fnd(bd_danos, hp, resultados, proy_danos, pe_mes, periodos_proy, ultimo,
                                        is_fa["val"] if is_fa is not None else None, bel_area,
                                        info_area.get("motivos"))
            validar(info_fnd["proy"], proy_rfv)
            alertas.extend(info_fnd.get("alertas") or [])
            proy_danos = info_fnd["proy"]
        except Exception as e:  # noqa: BLE001
            info_fnd = {"estado": f"error en el BEL por FND ({type(e).__name__}: {e}); el BEL sigue con el modelo",
                        "aplica": set(), "fnd": {}, "series": [], "resumen": []}
            alertas.append(("PND", "BEL por FND", info_fnd["estado"]))
        print(f"   {info_fnd['estado']}", flush=True)
        if info_fnd.get("sin_area"):                      # (el IBNR de esas series queda en 0, sin formula)
            diag_pnd["sin_metodo_area"] = ("SIN METODO DEL AREA: " + " | ".join(info_fnd["sin_area"])
                                           + ". Ese BEL queda en 0, sin formula; corrigelo y vuelve a correr")
            print(f"   AVISO: {diag_pnd['sin_metodo_area']}", flush=True)
        diag_pnd["metodo_area"] = "; ".join(f"{k[0]} {k[1]}: {v}" for k, v in sorted(
            (info_fnd.get("estado_area") or {}).items())) or ("sin series en BEL_METODO_AREA" if not BEL_METODO_AREA else "")
        for f in info_fnd.get("resumen") or []:           # cambios grandes contra el modelo al ultimo mes
            bm, bf = f.get(f"BEL modelo {periodos_proy[-1]}"), f.get(f"BEL por FND {periodos_proy[-1]}")
            if bm and bf is not None and np.isfinite(bf) and bm > 1e6 and abs(bf / bm - 1) > 0.5:
                alertas.append(("PND", f"BEL por FND {f['Reserva']} {f['Ramo']}",
                                f"{periodos_proy[-1]}: {bf / 1e6:,.1f} M USD por FND contra {bm / 1e6:,.1f} M del modelo"))
        if info_fnd.get("aplica"):                        # el diagnostico PND compara contra lo que lleva la BD
            _diag_pnd_bd_final(diag_pnd, proy_modelo, proy_danos, list(bd_danos.cols_ramo), periodos_proy)
    diag_pnd["bel_fnd"] = info_fnd
    diag_pnd["proy_modelo"] = proy_modelo
    bt = {"estado": "apagado (BACKTESTING = False)", "proy": {}}
    if BACKTESTING:
        print("Backtesting (Danos) ...", flush=True)
        n0 = len(alertas)
        try:
            bt = calcular_backtesting(bd_danos, hp, pe_mes, is_fa["val"] if is_fa is not None else None, ultimo)
            bt.update(comparar_backtesting(bt, bd_danos, proy_danos, ultimo, bel_area))
            alertas.extend(("PND", "Backtesting", a) for a in bt.get("alertas") or [])
        except Exception as e:  # noqa: BLE001
            del alertas[n0:]
            bt = {"estado": f"error en el backtesting ({type(e).__name__}: {e}); no se agrega", "proy": {}}
            alertas.append(("PND", "Backtesting", bt["estado"]))
        print(f"   {bt['estado']}", flush=True)
        for f in bt.get("resumen") or []:
            if f["Ramo"] == "TOTAL" and f["Concepto"] in (norm("RRC BEL"), norm("RRC NETO"), norm("SONR BEL"),
                                                           norm("SONR NETO")):
                e_ = f["Error % (suma |dif| / suma |real|)"]
                s_ = f["Sesgo % (suma dif / suma |real|)"]
                print(f"      {f['Concepto']:<10} error {e_:.1%} y sesgo {s_:+.1%} en {f['Meses reales comparados']} meses reales"
                      if e_ is not None else f"      {f['Concepto']}: sin meses reales", flush=True)
    diag_pnd["backtesting"] = bt
    # RFV por prima (Fianzas): RFV BRUTO = PRIMA 24M x FRV / TC; RFV IRR = BRUTO x CESION; RFV NETO = BRUTO - IRR
    info_rfvp = {"estado": "apagado (USAR_RFV_POR_PRIMA = False)", "aplica": set(), "frv": {}, "cesion": {},
                 "series": [], "resumen": []}
    pt_fz, bt_rfv = None, {"estado": "apagado (BACKTESTING = False)", "proy": {}}
    area_fz, ma_fz = {}, {}
    # TC de la historia de la RFV: el real con que SAP convirtio cada mes y, en los meses que la BD traia en pesos, el de
    # esa correccion (los pesos originales); el mismo con que el modelo regresa la historia a pesos
    tc_frv = {p: t for p, t in (tc_hist.get("FIANZAS") or leer_tc_real(bd_rfv, ultimo)).items() if p <= ultimo}
    tc_frv.update({p_: t_ for (c_, p_, _, _, _, t_) in correcciones["FIANZAS"] if c_.startswith("RFV")})
    if USAR_RFV_POR_PRIMA:
        print("RFV por prima (Fianzas) ...", flush=True)
        n0 = len(alertas)
        try:
            pt_fz = pt_fianzas(pe_ramo, pe_rfa, pef, bd_rfv, tc_primas, periodos_proy)
            for a in pt_fz["avisos"]:
                alertas.append(("FIANZAS", "Prima de Fianzas", a))
            com_fz = segmento_pr_fianzas(list(bd_rfv.cols_ramo), ultimo) if FACTORES_RFV else None
            for a in (com_fz or {}).get("avisos") or []:
                alertas.append(("FIANZAS", "Comisiones de Fianzas", a))
            area_fz = leer_fianzas_area(list(bd_rfv.cols_ramo), ultimo) if FACTORES_RFV else {}
            for a in (indicaciones_rfv(list(bd_rfv.cols_ramo))[2] if FACTORES_RFV else []):
                alertas.append(("FIANZAS", "Indicaciones de la RFV", a))
                print(f"   AVISO FIANZAS: {a}", flush=True)
            pd_fz = (pd_fianzas(area_fz, bd_rfv, tc_frv, list(bd_rfv.cols_ramo),
                                sorted({p_ for (_, p_) in bd_rfv.filas if p_ <= ultimo}), pt_fz)
                     if FACTORES_RFV else None)
            ma_fz = leer_montos_afianzados(list(bd_rfv.cols_ramo)) if FACTORES_RFV and MA_RFV else {}
            for a in (ma_fz or {}).get("avisos") or []:
                alertas.append(("FIANZAS", "Monto afianzado", a))
                print(f"   AVISO FIANZAS: {a}", flush=True)
            if FACTORES_RFV and MA_RFV and not (ma_fz or {}).get("ma"):
                alertas.append(("FIANZAS", "Monto afianzado", f"sin {PATRON_MONTOS_AFIANZADOS} en entradas/ (o sin "
                                "renglones utiles): la reserva por monto afianzado queda dentro de FV, como antes"))
            if FACTORES_RFV and not (pd_fz or {}).get("ultimo"):
                alertas.append(("FIANZAS", "PD de Fianzas", "ningun Res_Rvas de entradas/ trae la hoja Base FIANZAS con "
                                "castigo en meses que coincidan con SAP: la PD va en N/A y FCR = 1"))
            info_rfvp = calcular_rfv_prima(bd_rfv, proy_rfv, pt_fz, periodos_proy, ultimo, tc_frv, tc_primas, com_fz,
                                           pd_fz, ma_info=ma_fz)
            if FACTORES_RFV:
                insumos_area_fianzas(info_rfvp, bd_rfv, list(bd_rfv.cols_ramo),
                                     sorted({p_ for (_, p_) in bd_rfv.filas if p_ <= ultimo}), periodos_proy)
                for a in (info_rfvp.get("insumos_avisos") or []):
                    alertas.append(("FIANZAS", "Insumos del area", a))
            validar(proy_danos, info_rfvp["proy"])
            alertas.extend(info_rfvp["alertas"])
            proy_rfv = info_rfvp["proy"]
        except Exception as e:  # noqa: BLE001
            del alertas[n0:]
            info_rfvp = {"estado": f"error en la RFV por prima ({type(e).__name__}: {e}); la RFV sigue con el modelo",
                         "aplica": set(), "frv": {}, "cesion": {}, "series": [], "resumen": []}
            alertas.append(("FIANZAS", "RFV por prima", info_rfvp["estado"]))
        print(f"   Prima de Fianzas: {(pt_fz or {}).get('texto') or '-'}", flush=True)
        if (pt_fz or {}).get("texto_cedida"):
            print(f"   Prima cedida de Fianzas: {pt_fz['texto_cedida']}", flush=True)
        if FACTORES_RFV and (info_rfvp.get("com") or {}).get("texto"):
            print(f"   Segmento de prima de reserva de Fianzas: {info_rfvp['com']['texto']}", flush=True)
        for t_ in ("ma", "pdx", "csu"):
            if (info_rfvp.get(f"texto_{t_}") or ""):
                print(f"   {dict(ma='Monto afianzado', pdx='PD de referencia (xDefault)', csu='Comision sobre utilidades')[t_]}"
                      f": {info_rfvp[f'texto_{t_}']}", flush=True)
        if FACTORES_RFV and (info_rfvp.get("pdinfo") or {}).get("ultimo"):
            print("   PD de Fianzas (Res_Rvas, CASTIGO / (IRR + CASTIGO), ultimo mes medido): " + ", ".join(
                f"{r_}: {v_:.3%} ({q_})" for r_, (q_, v_) in info_rfvp["pdinfo"]["ultimo"].items()), flush=True)
        print(f"   {info_rfvp['estado']}", flush=True)
        if info_rfvp.get("sensibilidad"):
            print(f"   Sensibilidad a la moneda: {info_rfvp['sensibilidad']}", flush=True)
        if info_rfvp.get("aplica"):                    # con la RFV por prima el rango esperado solo se avisa: no se
            for i in alertas_rango_rfv:                # aplica a la RFV (tampoco a los ramos y meses que siguen con
                lib_, cl_, tx_ = alertas[i]            # el modelo, que se regresan a su valor sin el rango)
                alertas[i] = (lib_, cl_, f"(no se aplico: con la RFV por prima el rango solo se avisa) {tx_}")
            if rangos_rfv and any(not t.startswith("FIANZAS") for t in rangos_rfv):   # (el rango si habia ajustado)
                for k_, (pn_, li_, ls_, al_, pm_) in res_rfv_sin_rango.items():
                    r_ = resultados[k_]
                    r_.pronostico, r_.li, r_.ls, r_.alertas, r_.parametros = pn_, li_, ls_, al_, pm_
                for k_ in list(proy_rfv):
                    if k_[0].startswith("RFV ") and (k_[1], k_[2]) not in info_rfvp["aplica"] and k_ in proy_rfv_sin_rango:
                        proy_rfv[k_] = proy_rfv_sin_rango[k_]
                validar(proy_danos, proy_rfv)
            nuevos_r = []
            for (lib, conc), (inf, sup) in RANGO_ESPERADO.items():
                if lib != "FIANZAS":
                    continue
                tot = {p: sum(proy_rfv.get((norm(conc), p, r), 0.0) for r in bd_rfv.cols_ramo) for p in periodos_proy}
                fuera = [p for p, v in tot.items() if (inf is not None and v < inf) or (sup is not None and v > sup)]
                nuevos_r.append(f"FIANZAS {conc}: con la RFV por prima el rango solo se avisa (no ajusta la RFV de la BD, "
                                "ni la de los ramos o meses que siguen con el modelo); la BD "
                                f"lleva {periodos_proy[0]}: {tot[periodos_proy[0]] / 1e6:,.1f} y {periodos_proy[-1]}: "
                                f"{tot[periodos_proy[-1]] / 1e6:,.1f} M USD, "
                                + (f"fuera del rango ({texto_rango(inf, sup)}) en {len(fuera)} mes(es)" if fuera else
                                   f"dentro del rango ({texto_rango(inf, sup)})"))
                if fuera:
                    alertas.append(("FIANZAS", f"{conc} total", f"con la RFV por prima, {len(fuera)} mes(es) fuera del "
                                    f"rango esperado ({texto_rango(inf, sup)}): {fuera[0]} a {fuera[-1]}; no se ajusta"))
            resumen_rangos = rangos_danos + nuevos_r
            for t_ in nuevos_r:
                print(f"   {t_}", flush=True)
    if BACKTESTING:
        print("Backtesting (Fianzas) ...", flush=True)
        n0 = len(alertas)
        try:
            bt_rfv = calcular_backtesting_rfv(bd_rfv, pt_fz, ultimo, tc_frv,
                                              area_fz if USAR_RFV_POR_PRIMA and FACTORES_RFV else None,
                                              ma_fz if USAR_RFV_POR_PRIMA and FACTORES_RFV and MA_RFV else None)
            bt_rfv.update(comparar_backtesting(bt_rfv, bd_rfv, proy_rfv, ultimo))
            alertas.extend(("FIANZAS", "Backtesting", a) for a in bt_rfv.get("alertas") or [])
        except Exception as e:  # noqa: BLE001
            del alertas[n0:]
            bt_rfv = {"estado": f"error en el backtesting de Fianzas ({type(e).__name__}: {e}); no se agrega", "proy": {}}
            alertas.append(("FIANZAS", "Backtesting", bt_rfv["estado"]))
        print(f"   {bt_rfv['estado']}", flush=True)
        for f in bt_rfv.get("resumen") or []:
            if f["Ramo"] == "TOTAL" and f["Concepto"] in (norm("RFV BRUTO"), norm("RFV NETO"), norm("RCONT")):
                e_ = f["Error % (suma |dif| / suma |real|)"]
                s_ = f["Sesgo % (suma dif / suma |real|)"]
                print(f"      {f['Concepto']:<10} error {e_:.1%} y sesgo {s_:+.1%} en {f['Meses reales comparados']} meses reales"
                      if e_ is not None else f"      {f['Concepto']}: sin meses reales", flush=True)
    diag_pnd["rfv_prima"] = info_rfvp
    diag_pnd["pt_fianzas"] = (pt_fz or {}).get("texto") or ""
    diag_pnd["backtesting_rfv"] = bt_rfv

    info_danos = escribir_bd_montos(bd_danos, proy_danos, periodos_proy, SALIDA_BD_DANOS)
    escribir_correccion_moneda(bd_danos, correcciones["DANOS"])
    n_hp = escribir_hparametros(hp, resultados, periodos_proy)
    meses_bd = ESCENARIOS_PND.get(BD_CON_ESCENARIO_PND) or next(iter(ESCENARIOS_PND.values()), None)
    hoja_pe = hoja_pe_ramo = None
    cols_ind = {}                          # (bloque, ramo) -> columna de los bloques de indicadores
    ctx_is_fa = None                       # IS (FA): valores y celdas de la hoja HOJA_IS_FA
    avisos_ind = []

    def ctx_indices(proy, meses, fnd, razones=None):
        esc = next((e for e, m in ESCENARIOS_PND.items() if m == meses), None)
        return {"hp": hp, "resultados": resultados, "periodos_proy": periodos_proy, "ultimo": ultimo, "proy": proy,
                "pe": pe_mes, "hoja_pe": hoja_pe_ramo, "primas_pe": hoja_pe, "meses_pe": meses, "fnd": fnd,
                "razones": razones, "is_fa": ctx_is_fa,
                "is_fa_bel": (info_fnd.get("is_fa_bel") or set()) if fnd is not None else set(),
                "bel_area": (info_fnd.get("bel_area") or {}) if fnd is not None else {},
                "suavizado": (info_fnd.get("suavizado") or {}) if fnd is not None else {},
                "pe_tab": {g: x for (e, g), x in (diag_pnd.get("_pe") or {}).items() if e == esc}}
    if INDICES_PND_EN_BD:
        if INDICES_PND_FORMULAS and diag_pnd.get("_pe") and primas is not None:   # solo con prima completa y verificada
            grupos_pe = [g for g in pr.mensual.columns
                         if g in {primas.GRUPO_DE_RAMO_RESERVA.get(str(r)) for r in bd_danos.cols_ramo}]
            hoja_pe = escribir_primas_pe(bd_danos.wb, pr, grupos_pe)
        meses_prima = agregar_meses_prima(bd_danos, pe_mes)
        if meses_prima:
            print(f"   Meses de prima antes de la BD: {meses_prima[0]} a {meses_prima[-1]} ({len(meses_prima)} meses, "
                  f"{len(bd_danos.filas_prima)} renglones sin montos al final de {HOJA_MONTOS})", flush=True)
        hoja_pe_ramo = escribir_pe_ramo(bd_danos.wb, pe_mes, list(bd_danos.cols_ramo),
                                        sorted({p for _, p in {**bd_danos.filas, **bd_danos.filas_prima}}))
        ref_is_fa = escribir_is_fa(bd_danos.wb, is_fa)
        if is_fa is not None:
            ctx_is_fa = {"val": is_fa["val"], "ref": ref_is_fa or {}, "archivo": is_fa["ruta"].name,
                         "periodos": is_fa["periodos"], "ramos": is_fa["ramos"]}
        registro_ind = {}
        hist_area = {k: d.get("historia") or {} for k, d in (info_fnd.get("bel_area") or {}).items()}
        estado_area = info_fnd.get("estado_area") or {}
        cols_ind = escribir_indices_pnd(bd_danos, {**ctx_indices(proy_danos, meses_bd, info_fnd.get("fnd"),
                                                                 info_fnd.get("razones")), "registro": registro_ind},
                                        avisos_ind)
        diag_pnd["indicadores_ramo"] = [
            {"Reserva": pref, "Ramo": r, "Periodo": p, "Tipo": "Real" if p <= ultimo else "Proyección",
             **{c: v.get(c) for c in COLUMNAS_TABLERO_PND}, "BEL": v.get("BEL"), "BRUTO": v.get("BRUTO"),
             "Lleva GTO": v.get("GTO"), "BEL por FND": v.get("FND"), "IS del BEL": v.get("IS del BEL"),
             "Meses PRIMA N AÑOS": MESES_PRIMA_N_ANOS, "Años LAG PEACUMULADA": ANIOS_LAG_PEACUMULADA.get(pref, 0),
             "Historia del BEL": estado_area.get((pref, r)) or "SAP",
             **{f"{c} {SUFIJO_METODO_AREA}": hist_area.get((pref, r), {}).get(p, {}).get(c) for c in COLUMNAS_METODO_AREA}}
            for (pref, r, p), v in sorted(registro_ind.items(), key=lambda x: (x[0][0], int(x[0][1]), x[0][2]))]
        if INDICES_PND_FORMULAS and info_fnd.get("aplica"):
            escribir_bel_fnd(bd_danos, info_fnd, cols_ind)
        for a in avisos_ind:
            alertas.append(("PND", "Indicadores de la BD", a))
            print(f"   AVISO: {a}", flush=True)
    pe_tab_bd = ctx_indices(proy_danos, meses_bd, None)["pe_tab"] if INDICES_PND_EN_BD else {}
    n_bt = escribir_backtesting(bd_danos, bt, cols_ind, pe_tab_bd)
    if n_bt:
        al_final = min(bd_danos.filas_backtest.values()) > max(list(bd_danos.filas.values())
                                                               + list(bd_danos.filas_prima.values()))
        print(f"   Backtesting: {n_bt} renglones '{BACKTESTING_ETIQUETA} <concepto>' "
              + (f"al final de {HOJA_MONTOS}" if al_final else f"en {HOJA_MONTOS} (en los renglones que ya traia la BD de "
                 "entrada, que no estaban al final)"), flush=True)
    guardar_libro(bd_danos.wb, SALIDA_BD_DANOS, original=ARCHIVO_BD_DANOS)
    info_rfv = escribir_bd_montos(bd_rfv, proy_rfv, periodos_proy, SALIDA_BD_RFV)
    escribir_correccion_moneda(bd_rfv, correcciones["FIANZAS"])
    cols_rfv = {}
    if info_rfvp.get("aplica"):                        # el FRV de la hoja usa la columna TC: la del TC de la historia
        cambiados = {}
        for (c_, p_), f_ in bd_rfv.filas.items():
            t_ = (info_rfvp.get("tc_hist") or {}).get(p_)
            v_ = bd_rfv.ws.cell(f_, bd_rfv.col_tc).value
            if t_ and isinstance(v_, (int, float)) and abs(v_ - t_) > 1e-9:
                bd_rfv.ws.cell(f_, bd_rfv.col_tc).value = t_
                cambiados[p_] = (v_, t_)
        if cambiados:
            texto_tc = ("La columna TC de la BD de RFV se llevo al TC real de SAP (con el que se convirtieron los montos) "
                        f"en {len(cambiados)} mes(es) de la historia, para que el FRV de la hoja sea el de la proyeccion: "
                        + ", ".join(f"{q}: {a:.4f} -> {b:.4f}" for q, (a, b) in sorted(cambiados.items())))
            alertas.append(("FIANZAS", "TC de la historia", texto_tc))
            print(f"   AVISO FIANZAS: {texto_tc}", flush=True)
            info_rfv["tc_cambiados"] += sum(1 for (c_, p_) in bd_rfv.filas if p_ in cambiados)
    if pt_fz and pt_fz.get("mensual"):                 # RFV por prima: hoja PT_RAMO, bloques y formulas de la RFV
        hoja_pt = escribir_pt_ramo(bd_rfv.wb, pt_fz, list(bd_rfv.cols_ramo), sorted({p for _, p in bd_rfv.filas}),
                                   info_rfvp, ultimo)
        cols_rfv = escribir_bloques_rfv(bd_rfv, info_rfvp, hoja_pt, periodos_proy)
        if info_rfvp.get("aplica"):
            escribir_rfv_prima(bd_rfv, info_rfvp, cols_rfv)
    else:                                              # (sin prima de Fianzas: se quitan los de una corrida anterior)
        escribir_pt_ramo(bd_rfv.wb, None, [])
        escribir_bloques_rfv(bd_rfv, info_rfvp, None, periodos_proy, solo_limpiar=True)
    n_bt_rfv = escribir_backtesting(bd_rfv, bt_rfv, cols_rfv)
    if n_bt_rfv:
        print(f"   Backtesting Fianzas: {n_bt_rfv} renglones '{BACKTESTING_ETIQUETA} <concepto>' en {HOJA_MONTOS} de "
              f"{SALIDA_BD_RFV.name}", flush=True)
    guardar_libro(bd_rfv.wb, SALIDA_BD_RFV, original=ARCHIVO_BD_RFV)
    # una BD de Danos por escenario (mismo libro, con HParametros ya proyectado; solo cambian RRC y SONR)
    archivos_pnd = []
    for esc, proy_esc in (diag_pnd.get("proy") or {}).items():
        ruta = ruta_escenario_pnd(esc)
        escribir_bd_montos(bd_danos, proy_esc, periodos_proy, ruta)
        if INDICES_PND_EN_BD:
            ctx_esc = ctx_indices(proy_esc, ESCENARIOS_PND[esc], None)
            cols_esc = escribir_indices_pnd(bd_danos, ctx_esc)
            escribir_backtesting(bd_danos, bt, cols_esc, ctx_esc["pe_tab"])   # (los bloques se reescriben en cada renglon)
        guardar_libro(bd_danos.wb, ruta, original=ARCHIVO_BD_DANOS)
        archivos_pnd.append(ruta.name)
    viejos = [ruta_escenario_pnd(e).name for e in ESCENARIOS_PND
              if ruta_escenario_pnd(e).exists() and ruta_escenario_pnd(e).name not in archivos_pnd]
    if viejos:
        alertas.append(("PND", "Archivos de escenarios", f"{', '.join(viejos)} en salidas/ son de una corrida anterior "
                                                         "(esta vez no se generaron)"))

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
                          "primas": pr, "factor": diag_factor, "comparativo": comparativo, "pnd": diag_pnd})
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
            # los dashboards leen las salidas de ESTA corrida (y no la carpeta salidas/ fija) si se redirigieron
            dashboard.SALIDAS, dashboard.ARCHIVO_DANOS = SALIDAS, SALIDA_BD_DANOS
            dashboard.ETIQUETA_BACKTESTING = BACKTESTING_ETIQUETA
            dashboard.ARCHIVO_RFV, dashboard.ARCHIVO_DIAGNOSTICO = SALIDA_BD_RFV, SALIDA_DIAGNOSTICO
            dashboard.MONTOS_CALCULADOS = {**{("DANOS", c, p, r): v for (c, p, r), v in proy_danos.items()},
                                           **{("FIANZAS", c, p, r): v for (c, p, r), v in proy_rfv.items()}}
            dashboard.generar(SALIDA_DASHBOARD)
            dashboard_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"   No se pudo generar el dashboard de Excel: {e!r}")
        try:
            import dashboard as _dx  # noqa: WPS433
            import dashboard_html  # noqa: WPS433
            _dx.SALIDAS, _dx.ARCHIVO_DANOS = SALIDAS, SALIDA_BD_DANOS
            _dx.ETIQUETA_BACKTESTING = BACKTESTING_ETIQUETA
            _dx.ARCHIVO_RFV, _dx.ARCHIVO_DIAGNOSTICO = SALIDA_BD_RFV, SALIDA_DIAGNOSTICO
            _dx.MONTOS_CALCULADOS = {**{("DANOS", c, p, r): v for (c, p, r), v in proy_danos.items()},
                                     **{("FIANZAS", c, p, r): v for (c, p, r), v in proy_rfv.items()}}
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
    if USAR_ESCENARIOS_PND:
        print(f"   Escenarios PND / PD (Danos): {diag_pnd.get('estado')}")
        for f in diag_pnd.get("decision") or []:
            if not f.get("Cortes (serie x corte)"):
                continue
            conc = ("BEL", "GTO", "MR", "BRUTO") if f["Reserva"] == "RRC" else ("BEL", "MR", "BRUTO")
            print(f"      {f['Escenario']} {f['Reserva']:<5} error backtest recta / escenario: "
                  + ", ".join(f"{c} {f.get(f'Error % {c} recta', math.nan):.1f} / {f.get(f'Error % {c} escenario', math.nan):.1f}"
                              for c in conc)
                  + f"; BRUTO con prima plana {f.get('Error % BRUTO escenario con prima plana', math.nan):.1f}"
                  + f" ({f['Cortes (serie x corte)']} casos)")
        tot = [f for f in diag_pnd.get("totales") or [] if f["Reserva"].endswith("NETO")]
        if tot and diag_pnd.get("proy"):
            cols = [k for k in tot[0] if k != "Reserva"]
            print(f"      Totales NETO (M USD; 'BD principal' = lo que lleva la BD, con el BEL por FND donde aplica): "
                  + " | ".join(cols))
            for f in tot:
                print(f"      {f['Reserva']:<10} " + " | ".join(f"{(f.get(k) or 0) / 1e6:,.1f}" for k in cols))
        if archivos_pnd:
            print(f"      Archivos: {', '.join(archivos_pnd)}")
    fnd = diag_pnd.get("bel_fnd") or {}
    if diag_pnd.get("sin_pe"):
        print(f"   AVISO: {diag_pnd['sin_pe']}")
    if diag_pnd.get("sin_fcst"):
        print(f"   AVISO: {diag_pnd['sin_fcst']}")
    if diag_pnd.get("sin_is_fa"):
        print(f"   AVISO: {diag_pnd['sin_is_fa']}")
    if diag_pnd.get("sin_metodo_area"):
        print(f"   AVISO: {diag_pnd['sin_metodo_area']}")
    if USAR_BEL_POR_FND:
        print(f"   BEL por FND (Danos): {fnd.get('estado', '')}")
        if fnd.get("aplica"):
            pm = diag_pnd.get("proy_modelo") or {}
            dics = [p for p in periodos_proy if p % 100 == 12]
            for pref in INDICE_BASE_PND:
                for conc in ("BEL", "NETO"):
                    tot = lambda dic, p: sum(dic.get((norm(f"{pref} {conc}"), p, r), 0.0) for r in bd_danos.cols_ramo)  # noqa: E731
                    print(f"      {pref} {conc:<5} (M USD) modelo / por FND: "
                          + " | ".join(f"{p}: {tot(pm, p) / 1e6:,.1f} / {tot(proy_danos, p) / 1e6:,.1f}" for p in dics))
                nf = fnd.get("neto_fijo") or {}
                fijo = lambda p: sum(nf.get((pref, p, r), proy_danos.get((norm(f"{pref} NETO"), p, r), 0.0))  # noqa: E731
                                     for r in bd_danos.cols_ramo)
                print(f"      {pref} NETO  (M USD) con FACTOR GTO, FACTOR MR y CESION fijos en {ultimo} (comparativo): "
                      + " | ".join(f"{p}: {fijo(p) / 1e6:,.1f}" for p in dics))
    if viejos:
        print(f"   OJO: {', '.join(viejos)} en salidas/ son de una corrida anterior (esta vez no se generaron)")
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
