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
       - textos con espacios / celdas vacias se limpian; huecos <= 6 meses se interpolan
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
# Moneda en que se modelan los montos. En USD por evidencia: en backtest, modelar en MXN (historia USD x
# TC real) y convertir con el TC real futuro fue MENOS preciso que modelar directo en USD, tanto en Danos
# (WAPE 22.5% vs 19.8%, 21 series) como en Fianzas (RFV BRUTO 7.4% vs 6.0%): las reservas se comportan como
# montos en dolares. True = modelar en MXN y convertir con el TC de cada mes proyectado de la BD.
MODELAR_EN_MXN = {"DANOS": False, "FIANZAS": False}
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


def ajustar_tendencia(z, h: int, meses=None):
    """Linea de tendencia (regresion lineal sobre los ultimos MESES_TENDENCIA valores de z, en la escala del modelo)
    mas, si ESTACIONALIDAD_MENSUAL y se conocen los meses, el patron por mes del ano; continuada desde el ultimo
    dato real con amortiguacion AMORTIGUACION_TENDENCIA. Intervalo: la variabilidad mensual alrededor de la
    tendencia (ya sin el patron estacional), que crece con la raiz del horizonte."""
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
    pron = d[-1] + pendiente * pasos + estacional_fut                  # arranca del ultimo real y repite el patron
    sd = float(np.std(np.diff(w) - pendiente, ddof=1)) if len(w) > 2 else 0.0
    ancho = _cuantil_normal() * sd * np.sqrt(np.arange(1, h + 1))
    params = {"pendiente": float(pendiente), "ventana": int(len(w)), "r2": float(r2),
              "ajuste_ultimo": float(ordenada + pendiente * (len(w) - 1))}   # recta (sin estacionalidad) en el ultimo mes
    if est is not None:
        params.update({"estacional": [float(v) for v in est["factores"]], "credibilidad_estacional": est["credibilidad"],
                       "p_estacional": est["p"], "r2_estacional": est["r2"], "obs_estacional": est["obs"],
                       "amplitud_estacional": est["amplitud"]})
    return pron, pron - ancho, pron + ancho, params, float(pendiente)


def ajustar(z, modelo: str, h: int, meses=None):
    """Pronostico en la escala del modelo: (pronostico, li, ls, parametros, pendiente final). meses = mes del ano
    (1-12) de cada observacion, para la estacionalidad de la tendencia historica."""
    return ajustar_tendencia(z, h, meses) if modelo == TENDENCIA else ajustar_ets(z, modelo, h)


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
    if corte:
        res.alertas.append(f"Hueco de mas de {MAX_HUECO_INTERPOLABLE} meses sin dato: se usa solo la historia "
                           f"desde {per[corte]}")
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
            f, lo, hi, params, pendiente = ajustar(z, modelo, hh, meses)
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
        if n >= 13 and y[-13] > 0 and y[-1] > 0:
            cambio12 = y[-1] / y[-13] - 1
            if abs(cambio12) > 0.05 and np.sign(res.tendencia_mensual) != np.sign(cambio12):
                res.alertas.append(f"La tendencia de {res.parametros['ventana']} meses ({res.tendencia_mensual:+.1%} "
                                   f"mensual) va en sentido contrario al cambio real de los ultimos 12 meses "
                                   f"({cambio12:+.0%})")

    # backtest: se re-proyecta desde cortes pasados con el mismo modelo y se compara contra lo real
    res.error_modelo, res.error_ultimo_valor, res.error_ses, res.n_cortes = backtest(z, y, modelo, inv, meses)
    if (res.n_cortes and np.isfinite(res.error_modelo) and np.isfinite(res.error_ultimo_valor)
            and res.error_modelo > res.error_ultimo_valor * 1.10 + 0.5):
        res.alertas.append(f"En el backtest de esta serie el modelo ({res.error_modelo:.1f}%) no supera a repetir "
                           f"el ultimo valor ({res.error_ultimo_valor:.1f}%)")

    res.pronostico, res.li, res.ls = list(pron[brecha:]), list(li[brecha:]), list(ls[brecha:])
    return _post_proceso(res, y, tipo, serie.dominio)


def backtest(z, y, modelo: str, inv, meses=None):
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
                preds[nombre] = (inv(ajustar(z[:o], mod, hz, None if meses is None else meses[:o])[0])
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


def leer_tc_real(bd: BDMontos, ultimo: int) -> dict:
    """TC real con que la fuente SAP convirtio cada mes a USD (fila 7 de BacktestingRRC, columnas SAP, de
    los Res_Rvas en entradas/). Se usa para regresar la historia a MXN; donde no hay dato se usa la BD."""
    tc = {p: v for p, v in bd.tc.items() if p <= ultimo}
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
                      "medida en que se han repetido. Razones (%GTO, %MR, %cedido): SES (nivel sin tendencia). RCONT: "
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
                              "FCST 2027), en tipo_cambio.py; 202601-202608 = TC real de SAP. Los montos se "
                              "modelan en USD, por lo que el TC no altera las cifras proyectadas."),
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
           "Amplitud estacional", "alpha", "beta", "phi", "gamma",
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

    for k, r in sorted(resultados.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        ult = r.historia_valores[-1] if r.historia_valores else math.nan
        fin = r.pronostico[-1] if r.pronostico else math.nan
        var = (fin / ult - 1) if (ult and not math.isnan(ult) and not math.isnan(fin) and ult != 0) else None
        fila_ = [k[0], k[1], k[2], k[3], r.tipo, r.moneda, r.transformacion, r.n_obs,
                 r.historia_periodos[0] if r.historia_periodos else None, r.regla, r.modelo or None,
                 r.parametros.get("ventana"), num(r.parametros.get("r2")), num(r.parametros.get("ajuste_ultimo")),
                 num(r.parametros.get("credibilidad_estacional")), _amplitud(r),
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
            if enc_ == "Tendencia mensual" and isinstance(c.value, float):
                c.number_format = "0.00%" if fila_[6].value == "log" else "0.0000"
            elif enc_ in ("alpha", "beta", "phi", "gamma", "R2 tendencia", "Credibilidad estacional") and isinstance(c.value, float):
                c.number_format = "0.000"
            elif enc_ == "Amplitud estacional" and isinstance(c.value, float):
                c.number_format = "0.0%" if fila_[6].value == "log" else "0.0000"
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
            tc_hist[libro] = leer_tc_real(bd, ultimo)
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
    validar(proy_danos, proy_rfv)

    info_danos = escribir_bd_montos(bd_danos, proy_danos, periodos_proy, SALIDA_BD_DANOS)
    n_hp = escribir_hparametros(hp, resultados, periodos_proy)
    guardar_libro(bd_danos.wb, SALIDA_BD_DANOS, original=ARCHIVO_BD_DANOS)
    info_rfv = escribir_bd_montos(bd_rfv, proy_rfv, periodos_proy, SALIDA_BD_RFV)
    guardar_libro(bd_rfv.wb, SALIDA_BD_RFV, original=ARCHIVO_BD_RFV)

    historia = {
        "DANOS": {k: v for k, v in bd_danos.valores.items() if k[1] <= ultimo},
        "FIANZAS": {k: v for k, v in bd_rfv.valores.items() if k[1] <= ultimo},
    }
    segundos = time.time() - t0
    escribir_diagnostico(resultados, periodos_proy, alertas, {"DANOS": proy_danos, "FIANZAS": proy_rfv},
                         {"ultimo": ultimo, "segundos": segundos, "versiones": _versiones()})
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
            print(f"      {r.clave[0]} {r.clave[1]} {r.clave[2]} ramo {r.clave[3]}: {cambio:+.0%} "
                  f"(tendencia {r.tendencia_mensual:+.1%} mensual"
                  + (f", regresion sobre {ventana} de {r.n_obs} meses)" if ventana else f", {r.modelo})"))
    con_est = [r.parametros["credibilidad_estacional"] for r in resultados.values()
               if r.parametros.get("credibilidad_estacional")]
    if ESTACIONALIDAD_MENSUAL:
        print(f"   Estacionalidad mensual aplicada en {len(con_est)} series (credibilidad mediana "
              f"{np.median(con_est) if con_est else 0:.2f}); patron por mes en la hoja 'Estacionalidad'")
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
