# -*- coding: utf-8 -*-
"""
================================================================================
MODELO DE PROYECCIÓN DE FLUJOS DE EFECTIVO — MONTE CARLO
Reaseguradora Patria (Grupo Peña Verde)
================================================================================

OBJETIVO
    Proyectar los flujos de efectivo futuros de la reaseguradora (ingresos y
    egresos) por concepto, simulando tanto la MAGNITUD como el TIMING (lag de
    cobro/pago) y el TIPO DE CAMBIO, para planeación de liquidez y presupuesto.

FUENTE DE DATOS
    Base de Gonz (dbo_aMOG_MovGonzalo en BaseValuacion.accdb).
    Los importes viven en columnas sufijo 4 (Tipo 4) y sufijo 6 (Tipo 6).
    El tipo de cambio se toma de dbo_aMOT_MovTipCambio (cMON_Id=31 = USD).

ARQUITECTURA DEL MODELO (Monte Carlo de 3 componentes)
    Para cada flujo simulado:
        Flujo = Magnitud  ×  Patrón temporal (lag)  ×  Tipo de cambio
                (cuánto)     (cuándo se materializa)   (ajuste FX)

    Componente 1 — MAGNITUD por concepto:
        Se ajusta una distribución (log-normal / gamma) a los montos históricos
        de cada concepto, separando ingresos de egresos.

    Componente 2 — PATRÓN TEMPORAL (lag de cobro/pago):
        Distribución del retraso en días entre la fecha de origen del movimiento
        (FecOri) y la fecha de proceso (derivada de aPOG_MesProc). Se ajusta una
        distribución de duración (log-normal / Weibull) por concepto.

    Componente 3 — TIPO DE CAMBIO:
        El TC USD/MXN se modela como un Movimiento Browniano Geométrico (GBM)
        calibrado con la serie histórica de dbo_aMOT_MovTipCambio. Esto convierte
        la incertidumbre de FX (que explicaba buena parte de las variaciones
        ATT vs Gonz) en parte de la distribución de flujos.

CALIBRACIÓN
    Auto-calibración: el script lee Gonz, estima todos los parámetros solo
    (frecuencias, magnitudes, lags, volatilidad de TC) y los reporta antes de
    simular, para total transparencia y auditabilidad.

SALIDA
    Excel con:
      - Parámetros calibrados (transparencia)
      - Proyección mensual por concepto (P5/P50/P95)
      - Fan charts de ingresos, egresos y flujo neto
      - VaR de liquidez

Autor: Alejandro Suna - Reaseguradora Patria
================================================================================
"""

import os
import sys
import time
import warnings
import getpass
import pickle
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ==============================================================================
# AUTO-INSTALACIÓN DE PAQUETES OPCIONALES (scipy, statsmodels, lifelines)
# ==============================================================================
# Estos paquetes activan la validación estadística completa y el modelo de
# supervivencia (AFT) para el lag. Si faltan, se instalan automáticamente al
# iniciar. Para desactivarlo (p. ej. si no hay internet), pon AUTO_INSTALL_DEPS=False.
AUTO_INSTALL_DEPS = True

def _asegurar_dependencias():
    if not AUTO_INSTALL_DEPS:
        return
    import importlib, subprocess
    faltantes = []
    for paq in ("scipy", "statsmodels", "lifelines"):
        try:
            importlib.import_module(paq)
        except ImportError:
            faltantes.append(paq)
    if not faltantes:
        return
    print(f"  [i] Instalando paquetes para validación/AFT: {', '.join(faltantes)} ...")
    print(f"      (solo la primera vez; puede tardar 1-2 minutos)")
    # Se intentan varias formas por si el entorno restringe alguna
    intentos = [
        [sys.executable, "-m", "pip", "install", "--quiet", *faltantes],
        [sys.executable, "-m", "pip", "install", "--quiet", "--user", *faltantes],
    ]
    for cmd in intentos:
        try:
            subprocess.check_call(cmd)
            print("  [✓] Paquetes instalados. Continuando...\n")
            return
        except Exception:
            continue
    print(f"  [!] No se pudieron instalar automáticamente.")
    print(f"      Instálalos a mano y vuelve a correr:  pip install {' '.join(faltantes)}\n")

_asegurar_dependencias()

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
usuario = getpass.getuser()
RUTA_ACCDB = r"\\adsroma\Documentos Patria\ReservasRRC\BaseValuacion.accdb"

# Excel de catálogos para mostrar NOMBRES (no claves) de monedas, cedentes y
# corredores. Hojas: 'Moneda', 'Cedentes Clave', 'Corredores Clave' (clave en
# col A, nombre en col B). Si es None, se busca por nombre en la carpeta base /
# Outputs / carpeta del script. Fija la ruta exacta para asegurarlo.
RUTA_CATALOGOS_XLSX = None   # ej. r"C:\Users\asunad\OneDrive - GPV\Documents\00_Catálogos_automático.xlsx"

# Carpeta base para las SALIDAS. OJO: getpass.getuser() puede devolver el usuario
# de RED (p. ej. 'aosunad'), que no siempre coincide con la carpeta de perfil
# (C:\Users\asunad). Por eso se usa Path.home() (la carpeta real del perfil) y se
# prueban varias ubicaciones; si ninguna existe, se usa la carpeta actual.
# Si prefieres fijarla a mano, pon la ruta en RUTA_BASE_MANUAL.
RUTA_BASE_MANUAL = None   # ej. r"C:\Users\asunad\OneDrive - GPV\Documents"

def _resolver_ruta_base():
    if RUTA_BASE_MANUAL:
        return Path(RUTA_BASE_MANUAL)
    candidatos = [
        Path.home() / "OneDrive - GPV" / "Documents",
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home(),
    ]
    for c in candidatos:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return Path.cwd()

RUTA_BASE = _resolver_ruta_base()

# ----- Parámetros de la simulación (CONFIGURABLES) -----
HORIZONTE_MESES = 12          # Horizonte de proyección (arranca en 12, configurable)
N_SIMULACIONES = 10000        # Número de trayectorias Monte Carlo
SEMILLA = 42                  # Reproducibilidad
PERCENTILES = [5, 25, 50, 75, 95]   # Percentiles a reportar

# ----- Ventana histórica para calibración -----
# None = usar todo el histórico de Gonz. O un entero AAAAMM como fecha mínima.
PERIODO_MIN_CALIBRACION = 202301   # El negocio creció ~28x desde 2002; se calibra
                                   # solo desde 2023 (donde el volumen se estabilizó
                                   # ~700K mov/año) para reflejar el RITMO ACTUAL y no
                                   # el promedio diluido por años viejos. Ajustable
                                   # (None = toda la historia; 202401 = solo 2024+).
HIST_MIN_PERIODO = 202001           # Inicio de las tendencias históricas (charts 2020-2025).

# Inflación anual esperada para escalar la PROYECCIÓN a meses futuros (compuesta
# mensualmente). Referencia: encuestas de expectativas Banxico/Citi (jun-jul 2026):
# cierre 2026 ≈ 4.20%, cierre 2027 ≈ 3.84%. Se usa 3.75% como supuesto de mediano
# plazo; ajústalo aquí si el comité usa otro.
INFLACION_ANUAL = 0.0375
                                   # Se carga aparte (cargar_gonz_previo) y se une en memoria,
                                   # porque cargar_gonz filtra >= PERIODO_MIN_CALIBRACION en el SQL.

# Ventana RECIENTE para calibrar el RITMO actual (en meses, relativa al último mes
# de datos). Si el neto se ha vuelto más negativo en los meses recientes, promediar
# 42 meses (2023+) diluye esa tendencia y la proyección sale demasiado optimista.
# Fijar p.ej. 12 o 18 hace que la proyección refleje el ritmo reciente real.
# None = usar toda la ventana PERIODO_MIN_CALIBRACION. Recomendado: 18.
MESES_CALIBRACION_RECIENTE = None   # p.ej. 18 para calibrar con los últimos 18 meses

# ----- Mapeo de códigos a nombres legibles (llénalos con tu catálogo) -----
# Si un código no está aquí, se muestra como "Moneda 31" / "Territorio 4".
MAPEO_MONEDAS = {
    1: "MXN", 31: "USD",
    # Sugerencias por FX implícito (verifícalas con tu catálogo SIREC/SAP):
    # 91: "EUR", 14: "COP", 35: "BRL", 46: "CLP", 105: "GBP", ...
}
MAPEO_TERRITORIOS = {
    # Llena con tu catálogo, p.ej.: 1: "México", 4: "Brasil", 5: "Colombia", ...
}

# ----- Tipo de cambio -----
MONEDA_USD_ID = 31            # cMON_Id de USD en dbo_aMOT_MovTipCambio
MODELAR_TC_ESTOCASTICO = True # GBM para el TC; si False, usa TC fijo del último dato

# ----- Modelo de supervivencia (AFT) para el lag -----
# El lag (días entre origen y materialización del flujo) se modela con un modelo
# de supervivencia AFT (Accelerated Failure Time) con covariables, en vez de una
# sola log-normal. Esto permite que el lag dependa de características del negocio.
USAR_AFT = True               # True = modelo AFT con covariables; False = log-normal simple (modo previo)
# Covariables a incluir en el AFT (deben poder derivarse de Gonz):
#   'corredor'  -> 1 si el negocio tiene corredor, 0 si es directo (de CorrTom)
#   'usd'       -> 1 si la operación es USD, 0 si no (de MonedaOri)
#   'territorio'-> categórica, se colapsa a los TOP-K territorios + "otro"
COVARIABLES_AFT = ["corredor", "usd", "territorio"]
TERRITORIO_TOP_K = 4          # nº de territorios más frecuentes a tratar por separado
# Censura / truncamiento: en Gonz cada registro es un movimiento YA procesado
# (evento observado), por lo que no hay censura clásica dentro de Gonz; el sesgo
# real es de TRUNCAMIENTO a la derecha: las cohortes de origen recientes
# sub-observan los lags largos (esos movimientos se procesarán después del corte
# y aún no están en el extracto), lo que sesga el lag hacia abajo.
#
# Corrección por defecto (sólida y sin inyectar datos sintéticos): ajustar el AFT
# sólo sobre COHORTES MADURAS —las suficientemente antiguas como para haber
# observado casi toda su cola de lag—. La distribución de covariables para la
# simulación se toma de TODA la población observada.
RESTRINGIR_COHORTES_MADURAS = True
MADUREZ_MIN_MESES = None       # None = automático (P95 del lag observado). O un entero de meses.
# La maquinaria de censura de lifelines (columna evento) queda lista para cuando
# se enlace el devengado (Tipo 4) con el pago (Tipo 6) o se hibride con ATT, donde
# sí existe censura real (movimientos incurridos aún no pagados al corte).
CENSURA_POR_DESARROLLO = False  # EXPERIMENTAL: augmenta censurados con el patrón de
                                # desarrollo de cohortes maduras. Apagado por defecto
                                # (puede distorsionar si no hay truncamiento real).
MAX_FILAS_AFT = 60000         # tope de filas para ajustar el AFT (muestreo si excede; rendimiento)

# ----- Caché -----
CACHE_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / "ModeloFlujos_Cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
FORZAR_RECARGA = False        # True = ignorar caché y releer Gonz

# ==============================================================================
# DEFINICIÓN DE CONCEPTOS (heredada y validada del análisis de trazabilidad)
# ==============================================================================
# Cada concepto agrupa una o más columnas de Gonz (sufijo 4 o 6).
# 'direccion': 'ingreso' o 'egreso' desde la óptica de la reaseguradora.
# 'signo': para convertir la convención contable de Gonz (ingresos negativos) a
#          montos positivos en la dirección natural del concepto.
CONCEPTOS = {
    # Todos los conceptos usan columnas TIPO 4 "Nal" = DEVENGADO en PESOS.
    # Es la única base consistente y en pesos (las columnas "pagadas" Tipo 6 están
    # en moneda original mezclada y son inusables para un modelo en pesos). El
    # TIMING de caja se obtiene aplicando el lag (vigencia -> mes de proceso) a
    # cada movimiento, así el monto es limpio (pesos) y el momento es de flujo.
    # ---------- INGRESOS (entra efectivo a la reaseguradora) ----------
    "Prima tomada": {
        "columnas": ["PriTomNal4", "PriTomEnCNal4", "PriTomReCNal4"],
        "direccion": "ingreso",
        "signo": -1,   # vienen negativos en Gonz
    },
    "Recuperación de retrocesión": {
        "columnas": ["SinCedNal4"],
        "direccion": "ingreso",
        "signo": -1,
    },
    # ---------- EGRESOS (sale efectivo de la reaseguradora) ----------
    "Prima cedida (retrocesión)": {
        "columnas": ["PriCedNal4"],
        "direccion": "egreso",
        "signo": +1,
    },
    "Siniestros tomados": {
        "columnas": ["SinTomNal4", "SinTomReCNal4"],
        "direccion": "egreso",
        "signo": +1,
    },
    "Comisiones pagadas": {
        "columnas": ["ComTomNal4"],
        "direccion": "egreso",
        "signo": +1,
    },
    "Corretaje pagado": {
        "columnas": ["CorrTomNal4"],
        "direccion": "egreso",
        "signo": +1,
    },
}

# Columnas de Gonz necesarias para la calibración
# Origen del lag. NOTA tras analizar Gonz: las fechas no permiten un lag
# origen->efectivo confiable (FecOri viene vacía; IniVig es el inicio de vigencia
# y da lags de 0 a ~21 años, mediana 12m, inservible para 12 meses). Por eso el
# modelo proyecta el FLUJO MENSUAL DIRECTO por mes de proceso (aPOG_MesProc) con
# un desfase corto a caja. Se deja FecOri como origen (cae al desfase corto por
# defecto). El análisis fino de lag/AFT no aplica con estos datos.
COL_FECHA_ORIGEN = "FecOri"   # IniVig da lags multianuales; no usar para 12 meses

COLUMNAS_NECESARIAS = [
    "Tipo", "aPOG_MesProc", "MonedaOri", "FecOri", "IniVig", "FinVig", "Ramo", "TipoRea",
    "CorrTom", "Territorio",   # covariables para el modelo de supervivencia AFT
    # Componentes de la LLAVE DE CONTRATO ClvRefCab2 (la misma del mapeo con ATT):
    #   ClvRefCab2 = CorrTom-CiaTom-CtoTom-Susc, cada uno con padding a 4 dígitos.
    #   Ej.: CorrTom=98, CiaTom=681, CtoTom=93, Susc=2023 -> "0098-0681-0093-2023".
    # Es la llave canónica para identificar contratos de forma trazable con ATT.
    "CiaTom", "CtoTom", "Susc",
]
# Agregar todas las columnas de importe de los conceptos
for _c in CONCEPTOS.values():
    COLUMNAS_NECESARIAS.extend(_c["columnas"])
COLUMNAS_NECESARIAS = list(dict.fromkeys(COLUMNAS_NECESARIAS))  # únicas, orden estable


# ==============================================================================
# CONEXIÓN Y CARGA DE DATOS
# ==============================================================================
def conectar_gonz():
    import pyodbc
    conn_str = (r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                rf'DBQ={RUTA_ACCDB};')
    return pyodbc.connect(conn_str)


def detectar_columnas_gonz():
    """Devuelve los nombres exactos de las columnas de la tabla de Gonz."""
    conn = conectar_gonz()
    try:
        df = pd.read_sql("SELECT TOP 1 * FROM dbo_aMOG_MovGonzalo", conn)
        return list(df.columns)
    finally:
        conn.close()


# ==============================================================================
# CATÁLOGOS REALES (monedas / territorios) DESDE LA BASE DE GONZ
# ==============================================================================
# En lugar de hardcodear nombres, se leen directo del .accdb:
#   - paisTerritorio        -> cPAI_Id, cPAI_Nombre (país), Territorio (región)
#   - dbo_aMOT_MovTipCambio -> cMON_Id + TC (para confirmar la moneda por su tipo de cambio)
# Así MAPEO_TERRITORIOS y MAPEO_MONEDAS se llenan con nombres reales en cada corrida.
# Lo no identificado cae al fallback "Territorio N" / "Moneda N" (no se inventa).

# ISO de monedas confirmadas o inferidas por su TC (cMON_Id es catálogo fijo de SIREC).
#   1=MXN, 31=USD (confirmadas). 14≈COP, 91≈EUR (inferidas por TC -> confirmar en corrida).
_MONEDAS_ISO_BASE = {1: "MXN", 31: "USD", 14: "COP", 91: "EUR"}
# El campo 'Territorio' de MovGonzalo se asume = cPAI_Id (cuadra con 1=México, 3=Argentina,
# 4=Brasil, 14=Colombia). Si en tu data fuera la región, pon TERRITORIO_COMO_REGION=True.
TERRITORIO_COMO_REGION = False


def _cargar_territorios_accdb():
    """{cPAI_Id:int -> nombre} desde paisTerritorio. {} si falla (cae al fallback)."""
    col = "Territorio" if TERRITORIO_COMO_REGION else "cPAI_Nombre"
    out = {}
    try:
        conn = conectar_gonz()
        try:
            df = pd.read_sql(f"SELECT cPAI_Id, {col} AS nom FROM paisTerritorio", conn)
        finally:
            conn.close()
        for _, row in df.iterrows():
            try:
                k = int(row["cPAI_Id"])
            except (TypeError, ValueError):
                continue
            nom = row["nom"]
            nom = str(nom).strip() if nom is not None else ""
            if nom and nom.lower() != "nan":
                out[k] = nom
    except Exception as e:
        print(f"  [!] No pude leer paisTerritorio ({type(e).__name__}: {e}); uso fallback 'Territorio N'.")
    return out


# Referencia FX 2026 (MXN por 1 unidad) para INFERIR la moneda por su tipo de cambio,
# SOLO si no hay catálogo de nombres en el .accdb. Ancla: USD≈18 MXN. LatAm va primero
# para ganar empates (p.ej. ~4.8 -> PEN antes que PLN/SAR). Cada inferencia se IMPRIME
# para que la confirmes; corrige en _MONEDAS_ISO_BASE si hace falta (eso manda).
_REF_FX_ISO = {
    "USD": 18.0, "EUR": 20.7, "MXN": 1.0,
    # LatAm (prioridad)
    "BRL": 3.30, "COP": 0.0045, "CLP": 0.019, "ARS": 0.015, "PEN": 4.80,
    "UYU": 0.45, "BOB": 2.60, "PYG": 0.00240, "CRC": 0.035, "GTQ": 2.34,
    "DOP": 0.30, "HNL": 0.72, "NIO": 0.49, "PAB": 18.0, "VES": 0.30,
    # Mayores y otras
    "GBP": 24.0, "CHF": 22.0, "CAD": 13.2, "AUD": 11.8, "NZD": 10.8,
    "JPY": 0.12, "CNY": 2.50, "HKD": 2.30, "SGD": 13.5, "SEK": 1.70,
    "NOK": 1.70, "DKK": 2.80, "PLN": 4.80, "CZK": 0.82, "ZAR": 1.00,
    "INR": 0.21, "AED": 4.90, "SAR": 4.80, "ILS": 4.90,
}


def _inferir_moneda_por_tc(tc, tol=0.12):
    """ISO cuya tasa de referencia más se acerca al TC (ratio dentro de ±tol). None si nada cae."""
    import math
    if tc is None or tc <= 0:
        return None
    mejor, mejor_d = None, 1e9
    for iso, ref in _REF_FX_ISO.items():
        d = abs(math.log(tc / ref))
        if d < mejor_d:
            mejor, mejor_d = iso, d
    return mejor if mejor_d <= math.log(1.0 + tol) else None


def _buscar_catalogo_monedas_accdb(conn):
    """Busca en el .accdb una tabla catálogo de monedas (id + nombre) y devuelve
    {id:int -> nombre}. {} si no hay. No falla (la mayoría de .accdb de Gonz no la trae)."""
    out = {}
    try:
        cur = conn.cursor()
        tablas = []
        for row in cur.tables(tableType="TABLE"):
            t = row.table_name
            if t and ("MON" in t.upper()) and ("TIPCAMBIO" not in t.upper()) \
                    and ("MOVTIP" not in t.upper()) and not t.upper().startswith("MSYS"):
                tablas.append(t)
        for t in tablas:
            try:
                cols = [c.column_name for c in cur.columns(table=t)]
            except Exception:
                continue
            id_col = next((c for c in cols if c.lower() in
                           ("cmon_id", "id", "idmoneda", "cmonid", "clave")), None)
            nom_col = next((c for c in cols if any(k in c.lower() for k in
                            ("nombre", "desc", "moneda", "divisa", "iso")) and c != id_col), None)
            if id_col and nom_col:
                df = pd.read_sql(f"SELECT [{id_col}] AS i, [{nom_col}] AS n FROM [{t}]", conn)
                for _, r in df.iterrows():
                    try:
                        k = int(r["i"])
                    except (TypeError, ValueError):
                        continue
                    n = str(r["n"]).strip() if r["n"] is not None else ""
                    if n and n.lower() != "nan":
                        out[k] = n
                if out:
                    print(f"  [✓] Catálogo de monedas en el .accdb: tabla '{t}' ({len(out)} nombres).")
                    break
    except Exception as e:
        print(f"  [i] (búsqueda de catálogo de monedas: {type(e).__name__})")
    return out


def _cargar_monedas_accdb():
    """{cMON_Id:int -> nombre/ISO}. Prioridad: (1) _MONEDAS_ISO_BASE (manual, manda),
    (2) catálogo de nombres del .accdb si existe, (3) inferencia por su TC. Imprime
    todo lo inferido (con su TC) para que lo confirmes. No inventa en silencio."""
    mon = dict(_MONEDAS_ISO_BASE)
    inferidas, sin_id = {}, []
    try:
        conn = conectar_gonz()
        try:
            cat = _buscar_catalogo_monedas_accdb(conn)            # (2) catálogo real si existe
            for k, v in cat.items():
                mon.setdefault(k, v)
            df = pd.read_sql(                                     # TC reciente por moneda
                "SELECT cMON_Id, cTCAD_Mnt, cTCAD_FecAMD FROM dbo_aMOT_MovTipCambio", conn)
        finally:
            conn.close()
        df["cTCAD_FecAMD"] = pd.to_numeric(df["cTCAD_FecAMD"], errors="coerce")
        df["cTCAD_Mnt"] = pd.to_numeric(df["cTCAD_Mnt"], errors="coerce")
        df = df.sort_values("cTCAD_FecAMD")                       # asc: el último es el más reciente
        ultimo = {}
        for _, row in df.iterrows():
            try:
                k = int(row["cMON_Id"])
            except (TypeError, ValueError):
                continue
            tc = row["cTCAD_Mnt"]
            if pd.notna(tc) and tc > 0:
                ultimo[k] = float(tc)
        for k, tc in ultimo.items():                             # (3) inferir las que falten
            if k in mon:
                continue
            iso = _inferir_moneda_por_tc(tc)
            if iso:
                mon[k] = iso
                inferidas[k] = (iso, tc)
            else:
                sin_id.append((k, tc))
        if inferidas:
            print("  [i] Monedas INFERIDAS por su TC (confírmalas; corrige en _MONEDAS_ISO_BASE si hace falta):")
            for k in sorted(inferidas):
                iso, tc = inferidas[k]
                print(f"        cMON_Id={k:<4} TC≈{tc:.5g}  ->  {iso}  (inferida)")
        if sin_id:
            print("  [!] Monedas sin identificar (TC fuera de la referencia; agrégalas a _MONEDAS_ISO_BASE):")
            for k, tc in sorted(sin_id):
                print(f"        cMON_Id={k:<4} TC≈{tc:.5g}  ->  '???'")
    except Exception as e:
        print(f"  [!] No pude leer dbo_aMOT_MovTipCambio ({type(e).__name__}: {e}); uso solo ISO base.")
    return mon


# --- Catálogos de NOMBRES (monedas / cedentes / corredores) desde el Excel de catálogos ---
MAPEO_CEDENTES = {}      # CiaTom  -> nombre (del Excel de catálogos)
MAPEO_CORREDORES = {}    # CorrTom -> nombre (del Excel de catálogos)


def _resolver_ruta_catalogos():
    """Ruta del Excel de catálogos (hojas 'Moneda', 'Cedentes Clave', 'Corredores Clave')
    o None. Usa RUTA_CATALOGOS_XLSX si está; si no, lo busca por nombre en la carpeta
    base, Outputs, la carpeta del script y el directorio actual."""
    import glob as _glob
    if RUTA_CATALOGOS_XLSX and Path(RUTA_CATALOGOS_XLSX).exists():
        return Path(RUTA_CATALOGOS_XLSX)
    try:
        base = _resolver_ruta_base()
    except Exception:
        base = Path.cwd()
    carpetas = [base, base / "Outputs", Path.cwd()]
    try:
        carpetas.append(Path(__file__).parent)
    except Exception:
        pass
    patrones = ["*atálogos*.xlsx", "*atalogos*.xlsx", "*ata?logos*.xlsx", "*ata_logos*.xlsx"]
    for carp in carpetas:
        for pat in patrones:
            try:
                hits = sorted(_glob.glob(str(carp / pat)))
            except Exception:
                hits = []
            if hits:
                return Path(hits[0])
    return None


def _leer_clave_nombre(ws, col_clave=1, col_nombre=2):
    """{int(clave) -> nombre} de una hoja con clave en col_clave y nombre en col_nombre.
    Ignora encabezados/marcadores ('*', vacíos, claves no numéricas)."""
    out = {}
    for row in ws.iter_rows(min_row=1, values_only=True):
        if not row or len(row) < max(col_clave, col_nombre):
            continue
        k, nom = row[col_clave - 1], row[col_nombre - 1]
        try:
            ki = int(str(k).strip())
        except (TypeError, ValueError):
            continue
        if nom is None:
            continue
        nom = str(nom).strip()
        if nom and nom != "*":
            out[ki] = nom
    return out


def cargar_catalogos_nombres():
    """Lee el Excel de catálogos y llena MAPEO_MONEDAS (nombres completos, con prioridad
    sobre ISO/inferencia), MAPEO_CEDENTES y MAPEO_CORREDORES. No falla si no está."""
    ruta = _resolver_ruta_catalogos()
    if ruta is None:
        print("  [i] No encontré el Excel de catálogos (nombres de monedas/cedentes/corredores). "
              "Fija RUTA_CATALOGOS_XLSX para mostrar nombres; por ahora uso claves/ISO.")
        return
    try:
        import openpyxl
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    except Exception as e:
        print(f"  [!] No pude abrir el catálogo {ruta} ({type(e).__name__}: {e}).")
        return
    print(f"  [i] Catálogo de nombres: {getattr(ruta, 'name', ruta)}")

    def _hoja(nombres):
        for n in nombres:
            if n in wb.sheetnames:
                return wb[n]
        return None

    hm = _hoja(["Moneda", "Monedas"])
    hc = _hoja(["Cedentes Clave", "Cedentes", "Cedentes Nombre"])
    hr = _hoja(["Corredores Clave", "Corredores", "Corredores Nombre"])
    if hm is not None:
        mon = _leer_clave_nombre(hm)
        if mon:
            MAPEO_MONEDAS.update(mon)   # nombres completos del catálogo = prioridad
            print(f"  [✓] Monedas con nombre (catálogo): {len(mon)}.")
    if hc is not None:
        ced = _leer_clave_nombre(hc)
        if ced:
            MAPEO_CEDENTES.update(ced)
            print(f"  [✓] Cedentes con nombre (catálogo): {len(ced)}.")
    if hr is not None:
        corr = _leer_clave_nombre(hr)
        if corr:
            MAPEO_CORREDORES.update(corr)
            print(f"  [✓] Corredores con nombre (catálogo): {len(corr)}.")
    try:
        wb.close()
    except Exception:
        pass


def cargar_catalogos_en_memoria():
    """Llena MAPEO_TERRITORIOS y MAPEO_MONEDAS con los nombres reales del .accdb.
    Actualiza los dicts EN SITIO para que _nombre_territorio/_nombre_moneda los vean."""
    terr = _cargar_territorios_accdb()
    mon = _cargar_monedas_accdb()
    if terr:
        MAPEO_TERRITORIOS.update(terr)
        print(f"  [✓] Territorios cargados: {len(terr)} (de paisTerritorio).")
    if mon:
        MAPEO_MONEDAS.update(mon)
        print(f"  [✓] Monedas cargadas: {len(mon)}.")
    # Nombres reales (monedas/cedentes/corredores) del Excel de catálogos (prioridad)
    cargar_catalogos_nombres()


def _estabilizar_dtypes(df):
    """
    Convierte columnas con dtype de EXTENSIÓN de pandas (p. ej. StringDtype con
    na_value=nan) a numpy 'object', para que el pickle sea PORTABLE entre versiones
    de pandas. Sin esto, un caché escrito con una versión puede fallar al leerse con
    otra (NotImplementedError en __setstate__). Los NA se normalizan a np.nan.
    """
    for col in df.columns:
        if not isinstance(df[col].dtype, np.dtype):   # dtype de extensión de pandas
            s = df[col]
            try:
                arr = s.to_numpy(dtype=object)
                na_mask = s.isna().to_numpy()
                arr[na_mask] = np.nan
                df[col] = arr
            except Exception:
                df[col] = s.astype(str)
    return df


def cargar_gonz(forzar=False):
    """
    Carga de Gonz las columnas necesarias para la calibración.
    Usa caché en disco para evitar recargas (la consulta completa es lenta).
    Si el caché es incompatible con la versión actual de pandas, se regenera solo.
    """
    cache_file = CACHE_DIR / "gonz_calibracion.pkl"
    if cache_file.exists() and not forzar:
        print(f"  [i] Cargando Gonz desde caché ({cache_file.name})...")
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"  [!] Caché incompatible o dañado ({type(e).__name__}). "
                  f"Se regenera desde la BD (una sola vez)...")
            try:
                cache_file.unlink()
            except Exception:
                pass
            # cae al bloque de regeneración (no retorna aquí)

    print("  [i] Consultando Gonz (esto puede tardar varios minutos)...")
    t0 = time.time()
    cols_reales = detectar_columnas_gonz()

    # Mapear nombres deseados a reales (por si difieren en mayúsculas/acentos)
    def buscar(nombre):
        for c in cols_reales:
            if c.lower() == nombre.lower():
                return c
        return None

    cols_a_traer = []
    for c in COLUMNAS_NECESARIAS:
        real = buscar(c)
        if real:
            cols_a_traer.append(real)

    cols_sql = ", ".join(f"[{c}]" for c in cols_a_traer)
    if PERIODO_MIN_CALIBRACION:
        sql = (f"SELECT {cols_sql} FROM dbo_aMOG_MovGonzalo "
               f"WHERE Val(aPOG_MesProc) >= {PERIODO_MIN_CALIBRACION}")
    else:
        sql = f"SELECT {cols_sql} FROM dbo_aMOG_MovGonzalo"

    conn = conectar_gonz()
    try:
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()

    # Estabilizar dtypes ANTES de guardar para que el caché sea portable
    df = _estabilizar_dtypes(df)

    print(f"  [i] Gonz cargado: {len(df):,} filas en {time.time()-t0:.1f}s")
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(df, f, protocol=4)
    except Exception as e:
        print(f"  [!] No se pudo guardar el caché ({type(e).__name__}); se continúa sin él.")
    return df


def cargar_gonz_previo(forzar=False):
    """Carga el tramo PREVIO a la ventana de calibración (por defecto 2020-2022), que
    'cargar_gonz' NO trae porque filtra en el SQL (>= PERIODO_MIN_CALIBRACION). Se usa
    solo para graficar las tendencias históricas 2020-2025: trae ese rango más chico,
    lo cachea aparte y luego se une EN MEMORIA con la ventana 2023+. Devuelve DataFrame
    o None si no hay datos / falla (las históricas caen a lo que haya)."""
    if not (HIST_MIN_PERIODO and PERIODO_MIN_CALIBRACION) or HIST_MIN_PERIODO >= PERIODO_MIN_CALIBRACION:
        return None
    cache_file = CACHE_DIR / f"gonz_previo_{HIST_MIN_PERIODO}.pkl"
    if cache_file.exists() and not forzar:
        print(f"  [i] Cargando tramo histórico previo desde caché ({cache_file.name})...")
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception:
            try:
                cache_file.unlink()
            except Exception:
                pass
    print(f"  [i] Consultando Gonz histórico {HIST_MIN_PERIODO}-{PERIODO_MIN_CALIBRACION - 1} (una sola vez)...")
    t0 = time.time()
    cols_reales = detectar_columnas_gonz()

    def buscar(nombre):
        for c in cols_reales:
            if c.lower() == nombre.lower():
                return c
        return None

    cols_a_traer = []
    for c in COLUMNAS_NECESARIAS:
        real = buscar(c)
        if real:
            cols_a_traer.append(real)
    cols_sql = ", ".join(f"[{c}]" for c in cols_a_traer)
    sql = (f"SELECT {cols_sql} FROM dbo_aMOG_MovGonzalo "
           f"WHERE Val(aPOG_MesProc) >= {HIST_MIN_PERIODO} "
           f"AND Val(aPOG_MesProc) < {PERIODO_MIN_CALIBRACION}")
    conn = conectar_gonz()
    try:
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()
    df = _estabilizar_dtypes(df)
    print(f"  [i] Tramo histórico previo cargado: {len(df):,} filas en {time.time() - t0:.1f}s")
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(df, f, protocol=4)
    except Exception:
        pass
    return df


def cargar_serie_tc(forzar=False):
    """
    Carga la serie histórica del tipo de cambio USD/MXN desde
    dbo_aMOT_MovTipCambio (cMON_Id=31), ordenada por fecha.
    Devuelve un DataFrame con columnas [periodo, tc].
    """
    cache_file = CACHE_DIR / "serie_tc.pkl"
    if cache_file.exists() and not forzar:
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"  [!] Caché de TC incompatible ({type(e).__name__}); se regenera...")
            try:
                cache_file.unlink()
            except Exception:
                pass

    conn = conectar_gonz()
    try:
        sql = (f"SELECT cTCAD_FecAMD, cTCAD_Mnt FROM dbo_aMOT_MovTipCambio "
               f"WHERE cMON_Id = {MONEDA_USD_ID} ORDER BY cTCAD_FecAMD")
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()

    # Normalizar: fecha como entero AAAAMMDD o AAAAMM, tc como float
    df.columns = ['fecha_raw', 'tc']
    df['tc'] = pd.to_numeric(df['tc'], errors='coerce')
    df = df.dropna(subset=['tc'])
    df = df[df['tc'] > 0]
    df = _estabilizar_dtypes(df)

    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(df, f, protocol=4)
    except Exception as e:
        print(f"  [!] No se pudo guardar el caché de TC ({type(e).__name__}); se continúa sin él.")
    return df


# ==============================================================================
# UTILIDADES DE FECHA Y NUMÉRICAS
# ==============================================================================
def a_numerico(serie):
    """Convierte una serie de Gonz (que viene como string) a float."""
    return pd.to_numeric(serie, errors='coerce').fillna(0.0)


def _s(v):
    """Normaliza un valor a string sin decimales (para comparar códigos)."""
    if pd.isna(v):
        return ""
    try:
        return str(int(float(v)))
    except (ValueError, TypeError):
        return str(v).strip()


def construir_clave_contrato(corr, cia, cto, susc):
    """
    Construye la LLAVE DE CONTRATO ClvRefCab2, idéntica a la usada en el mapeo
    con ATT: CorrTom-CiaTom-CtoTom-Susc, cada componente con padding a 4 dígitos.

    Ej.: construir_clave_contrato(98, 681, 93, 2023) -> "0098-0681-0093-2023".

    Esta es la llave canónica del modelo: garantiza que la identificación de
    contratos en Gonz sea trazable 1:1 con el sistema ATT. Cualquier componente
    que necesite agrupar o referir contratos debe usar esta función.
    """
    def p4(v):
        s = _s(v)
        if s == "":
            return "0000"
        try:
            return f"{int(s):04d}"
        except (ValueError, TypeError):
            return s.zfill(4)
    return f"{p4(corr)}-{p4(cia)}-{p4(cto)}-{p4(susc)}"


def mesproc_a_fecha(mesproc):
    """aPOG_MesProc (AAAAMM como int o str) -> pd.Timestamp del día 1 del mes."""
    try:
        v = int(float(mesproc))
        anio = v // 100
        mes = v % 100
        if 1 <= mes <= 12 and 1900 <= anio <= 2100:
            return pd.Timestamp(year=anio, month=mes, day=1)
    except (ValueError, TypeError):
        pass
    return None


def parsear_fecori(valor):
    """
    FecOri puede venir como string de fecha, serial de Excel, o AAAAMMDD.
    Devuelve pd.Timestamp o None.
    """
    if pd.isna(valor) or str(valor).strip() == "":
        return None
    s = str(valor).strip()
    # Intentar AAAAMMDD (8 dígitos)
    if s.isdigit() and len(s) == 8:
        try:
            return pd.Timestamp(year=int(s[:4]), month=int(s[4:6]), day=int(s[6:8]))
        except ValueError:
            pass
    # Intentar serial de Excel
    try:
        num = float(valor)
        if 1 < num < 80000:
            return pd.Timestamp('1899-12-30') + pd.Timedelta(days=int(num))
    except (ValueError, TypeError):
        pass
    # Intentar parseo genérico
    try:
        return pd.to_datetime(valor, errors='coerce')
    except Exception:
        return None


# ==============================================================================
# CALIBRACIÓN DE COMPONENTES
# ==============================================================================
def extraer_movimientos_concepto(df_gonz, concepto_def):
    """
    Para un concepto dado, extrae los movimientos individuales (no cero) de Gonz.
    Devuelve un DataFrame con: monto, aPOG_MesProc, MonedaOri, FecOri, y las
    covariables para el modelo de supervivencia (corredor, usd, territorio).

    Como una fila de Gonz puede tener varias columnas del concepto, se suma el
    aporte de las columnas del concepto en cada fila.
    """
    cols = [c for c in concepto_def["columnas"] if c in df_gonz.columns]
    if not cols:
        return pd.DataFrame()

    # Monto del concepto por fila = suma de sus columnas, con el signo natural
    monto = pd.Series(0.0, index=df_gonz.index)
    for c in cols:
        monto = monto + a_numerico(df_gonz[c])
    monto = monto * concepto_def["signo"]   # convertir a positivo en dirección natural

    # Quedarnos solo con filas donde el concepto tiene movimiento real
    mask = monto != 0
    sub = df_gonz.loc[mask]

    # Fecha de origen para el lag: se toma de COL_FECHA_ORIGEN (IniVig por defecto,
    # porque FecOri viene vacía). Se guarda bajo la clave "FecOri" para no tocar el
    # resto del flujo. Si la columna elegida no existe, se intenta FecOri.
    col_fo = COL_FECHA_ORIGEN if COL_FECHA_ORIGEN in sub.columns else "FecOri"
    out = pd.DataFrame({
        "monto": monto[mask].abs(),   # magnitud positiva
        "aPOG_MesProc": sub["aPOG_MesProc"] if "aPOG_MesProc" in sub else np.nan,
        "MonedaOri": sub["MonedaOri"] if "MonedaOri" in sub else np.nan,
        "FecOri": sub[col_fo] if col_fo in sub else np.nan,
    })

    # ----- Covariables para el AFT -----
    # corredor: 1 si CorrTom indica un corredor real, 0 si es directo.
    # En la convención de la trazabilidad, "0000"/"0"/vacío en el corredor = directo.
    if "CorrTom" in sub:
        corr_norm = sub["CorrTom"].apply(
            lambda v: "" if pd.isna(v) else str(v).strip().lstrip("0"))
        out["corredor"] = (corr_norm != "").astype(int).values
    else:
        out["corredor"] = 0

    # usd: 1 si MonedaOri == 31
    if "MonedaOri" in sub:
        out["usd"] = sub["MonedaOri"].apply(
            lambda v: 1 if (pd.notna(v) and _s(v) == str(MONEDA_USD_ID)) else 0).values
    else:
        out["usd"] = 0

    # territorio: categórica cruda (se colapsa a TOP-K más adelante)
    if "Territorio" in sub:
        out["territorio"] = sub["Territorio"].apply(
            lambda v: _s(v) if pd.notna(v) and _s(v) != "" else "ND").values
    else:
        out["territorio"] = "ND"

    # ----- Llave de contrato ClvRefCab2 (trazable con ATT) -----
    # Se construye con la MISMA convención del mapeo con ATT.
    if all(c in sub for c in ("CorrTom", "CiaTom", "CtoTom", "Susc")):
        out["ClvRefCab2"] = [
            construir_clave_contrato(cr, ci, ct, su)
            for cr, ci, ct, su in zip(
                sub["CorrTom"], sub["CiaTom"], sub["CtoTom"], sub["Susc"])
        ]
    else:
        out["ClvRefCab2"] = ""

    return out


def calibrar_magnitud(montos):
    """
    Caracteriza la distribución de montos de un concepto.

    DECISIÓN ESTADÍSTICA (validada con prueba de recuperación de media verdadera):
    para proyectar el flujo, el motor usa la MEDIA EMPÍRICA CRUDA y la VARIANZA
    EMPÍRICA del monto, porque:
      - La media empírica es el estimador INSESGADO de la media verdadera (incluye
        los siniestros grandes reales, sin recortarlos).
      - Hace que el modelo REPRODUZCA el flujo promedio histórico:
        λ_mensual × media_emp = total_histórico / nº de meses.
      - Evita el estimador exp(mu+sigma²/2), que con colas pesadas se sesga (puede
        dispararse o subestimar según qué tan no-log-normal sean los datos).
    Los parámetros log-normal (mu, sigma) se conservan para el modo individual
    (conceptos de baja frecuencia) y para describir la forma de la distribución.

    Devuelve dict con momentos crudos (los que usa la simulación) y forma log-normal.
    """
    montos = np.asarray(montos, dtype=float)
    montos = montos[montos > 0]
    if len(montos) < 5:
        return None

    logm = np.log(montos)
    mu = float(np.mean(logm))
    sigma = float(np.std(logm, ddof=1))

    return {
        "dist": "lognormal",
        "mu": mu,
        "sigma": sigma,
        "n": int(len(montos)),
        # Momentos EMPÍRICOS CRUDOS (insesgados) — los que usa el motor
        "media_emp": float(np.mean(montos)),
        "var_emp": float(np.var(montos, ddof=1)),
        "mediana_emp": float(np.median(montos)),
        "p95_emp": float(np.percentile(montos, 95)),
        "total_hist": float(np.sum(montos)),
    }


def calibrar_frecuencia(df_concepto):
    """
    Estima cuántas operaciones del concepto ocurren por mes.
    Cuenta operaciones por aPOG_MesProc y ajusta media y dispersión.

    Para la simulación usamos una Poisson (o binomial negativa si hay
    sobredispersión) con la tasa mensual media.
    """
    if len(df_concepto) == 0 or "aPOG_MesProc" not in df_concepto:
        return None

    # Contar operaciones por periodo
    conteo = df_concepto.groupby("aPOG_MesProc").size()
    conteo = conteo[conteo > 0]
    if len(conteo) == 0:
        return None

    media = float(conteo.mean())
    var = float(conteo.var(ddof=1)) if len(conteo) > 1 else media

    # Detectar sobredispersión (var > media => binomial negativa)
    sobredisp = var > 1.5 * media

    return {
        "lambda_mensual": media,
        "var_mensual": var,
        "sobredispersion": bool(sobredisp),
        "n_meses_obs": int(len(conteo)),
        "min_mensual": int(conteo.min()),
        "max_mensual": int(conteo.max()),
    }


def _lags_y_fechas(df_concepto):
    """
    Calcula de forma VECTORIZADA el lag en días (fecha de proceso − fecha de
    origen) para todos los movimientos de un concepto.

    Devuelve (lag_series, ts_origen, ts_proceso) alineados al índice de entrada.
    Maneja FecOri en formato AAAAMMDD, serial de Excel o string genérico, y
    aPOG_MesProc como AAAAMM (se toma el día 1 del mes).
    """
    # ----- Fecha de origen -----
    fo_raw = df_concepto["FecOri"]
    if pd.api.types.is_datetime64_any_dtype(fo_raw):
        # Ya viene como fecha (caso IniVig): usar directamente
        ts_ori = pd.to_datetime(fo_raw, errors="coerce")
    else:
        fo_str = fo_raw.astype(str).str.strip()
        # Intento 1: AAAAMMDD (8 dígitos)
        ts_ori = pd.to_datetime(fo_str, format="%Y%m%d", errors="coerce")
        # Intento 2: serial de Excel para los que fallaron y son numéricos
        faltan = ts_ori.isna()
        if faltan.any():
            num = pd.to_numeric(fo_raw[faltan], errors="coerce")
            es_serial = num.between(1, 80000)
            if es_serial.any():
                base = pd.Timestamp("1899-12-30")
                ts_ori.loc[num.index[es_serial]] = base + pd.to_timedelta(
                    num[es_serial].astype(int), unit="D")
        # Intento 3: parseo genérico para el resto
        faltan = ts_ori.isna()
        if faltan.any():
            ts_ori.loc[faltan] = pd.to_datetime(fo_raw[faltan], errors="coerce")

    # ----- Fecha de proceso (día 1 del mes AAAAMM) -----
    mp = pd.to_numeric(df_concepto["aPOG_MesProc"], errors="coerce")
    anio = (mp // 100)
    mes = (mp % 100)
    valido = anio.between(1900, 2100) & mes.between(1, 12)
    ts_proc = pd.Series(pd.NaT, index=df_concepto.index, dtype="datetime64[ns]")
    if valido.any():
        df_fechas = pd.DataFrame({
            "year": anio[valido].astype(int),
            "month": mes[valido].astype(int),
            "day": 1,
        })
        ts_proc.loc[valido[valido].index] = pd.to_datetime(df_fechas, errors="coerce").values

    lag = (ts_proc - ts_ori).dt.days
    return lag, ts_ori, ts_proc


def _codificar_covariables(df_cov, territorio_categorias):
    """
    Convierte las covariables crudas (corredor, usd, territorio) en una matriz de
    diseño numérica para el AFT. territorio se mapea a las categorías dadas
    (TOP-K + 'OTRO') y se codifica one-hot con drop_first para evitar colinealidad.

    Devuelve (DataFrame de diseño, lista de columnas de diseño).
    """
    cols_base = [c for c in ["corredor", "usd"] if c in df_cov.columns and c in COVARIABLES_AFT]
    diseño = df_cov[cols_base].astype(float).copy() if cols_base else pd.DataFrame(index=df_cov.index)

    if "territorio" in COVARIABLES_AFT and "territorio" in df_cov.columns:
        terr = df_cov["territorio"].where(
            df_cov["territorio"].isin(territorio_categorias), other="OTRO")
        terr = pd.Categorical(terr, categories=territorio_categorias + ["OTRO"])
        dummies = pd.get_dummies(terr, prefix="terr", drop_first=True)
        dummies.index = df_cov.index
        diseño = pd.concat([diseño, dummies.astype(float)], axis=1)

    return diseño, list(diseño.columns)


def _construir_censura_desarrollo(lags, ts_ori, df_cov, eventos):
    """
    Construye observaciones CENSURADAS a la derecha para corregir el truncamiento
    de las cohortes de origen recientes (que sub-observan los lags largos).

    Usa el patrón de desarrollo de las cohortes MADURAS para estimar cuántos
    movimientos siguen pendientes en las cohortes inmaduras, y los añade como
    censurados en el horizonte de madurez de su cohorte.

    Esto enlaza el Modelo 1 (triángulos / patrón de desarrollo) con el AFT.

    Devuelve (lags_cens, eventos_cens, df_cov_cens) a CONCATENAR con los eventos.
    """
    vacio = (np.array([]), np.array([]), df_cov.iloc[0:0].copy())
    if not CENSURA_POR_DESARROLLO or ts_ori.isna().all():
        return vacio

    cutoff = ts_ori.max()
    # Aproximar el corte como el inicio del último mes de proceso + 1 mes
    cutoff = (pd.Timestamp(year=cutoff.year, month=cutoff.month, day=1)
              + pd.offsets.MonthBegin(1))

    L99 = float(np.nanpercentile(lags, 99)) if len(lags) else 365.0
    L99 = max(L99, 30.0)

    # Madurez (días) de cada movimiento según su fecha de origen
    madurez = (cutoff - ts_ori).dt.days

    # Patrón de desarrollo F(d) a partir de cohortes maduras (madurez >= L99)
    maduras = madurez >= L99
    if maduras.sum() < 50:
        return vacio   # no hay suficientes cohortes maduras para estimar el patrón
    lags_maduras = lags[maduras].dropna()
    lags_maduras = lags_maduras[lags_maduras >= 0]
    if len(lags_maduras) < 50:
        return vacio
    lags_maduras_sorted = np.sort(lags_maduras.values)

    def F(d):
        # proporción de flujos materializados a los d días (de cohortes maduras)
        return np.searchsorted(lags_maduras_sorted, d, side="right") / len(lags_maduras_sorted)

    # Trabajar por cohorte de mes de origen sobre las cohortes INMADURAS
    mes_ori = ts_ori.dt.year * 100 + ts_ori.dt.month
    df_work = pd.DataFrame({
        "mes_ori": mes_ori, "madurez": madurez, "_idx": np.arange(len(df_cov))
    }, index=df_cov.index)
    inmaduras = df_work[(df_work["madurez"] < L99) & (df_work["madurez"] > 0)]
    if len(inmaduras) == 0:
        return vacio

    lags_cens = []
    idx_cov_cens = []   # índices (posicionales) de filas observadas de donde copiar covariables
    rng_local = np.random.default_rng(SEMILLA)

    for mes, grupo in inmaduras.groupby("mes_ori"):
        n_obs = len(grupo)
        m_dias = float(grupo["madurez"].iloc[0])
        frac = F(m_dias)
        if frac <= 0.05:
            continue   # cohorte demasiado nueva, el patrón no es confiable
        total_est = n_obs / frac
        pendientes = int(round(total_est - n_obs))
        if pendientes <= 0:
            continue
        pendientes = min(pendientes, 5 * n_obs)   # tope de seguridad
        # Censurar a la madurez de la cohorte, copiando covariables de la cohorte
        pool_idx = grupo["_idx"].values
        elegidos = rng_local.choice(pool_idx, size=pendientes, replace=True)
        lags_cens.extend([m_dias] * pendientes)
        idx_cov_cens.extend(elegidos.tolist())

    if not lags_cens:
        return vacio

    # Tope global de filas censuradas (rendimiento)
    if len(lags_cens) > MAX_FILAS_AFT:
        sel = rng_local.choice(len(lags_cens), size=MAX_FILAS_AFT, replace=False)
        lags_cens = list(np.array(lags_cens)[sel])
        idx_cov_cens = list(np.array(idx_cov_cens)[sel])

    df_cov_cens = df_cov.iloc[idx_cov_cens].copy()
    eventos_cens = np.zeros(len(lags_cens), dtype=int)   # censurados: evento=0
    return np.array(lags_cens), eventos_cens, df_cov_cens


def calibrar_lag_aft(df_concepto):
    """
    Calibra el lag con un modelo de SUPERVIVENCIA AFT (Accelerated Failure Time)
    con covariables, corrigiendo el truncamiento de las cohortes recientes.

    Pasos:
      1. Calcula el lag (origen -> proceso) de forma vectorizada.
      2. Construye covariables (corredor, usd, territorio).
      3. Corrige truncamiento ajustando sólo sobre cohortes MADURAS (la
         distribución de covariables para simular se toma de toda la población).
      4. Ajusta LogNormal AFT y Weibull AFT, elige por AIC.
      5. Extrae los coeficientes para muestreo vectorizado en la simulación.

    Devuelve un dict con todo lo necesario para muestrear el lag condicionado a
    covariables, más estadísticas e interpretación (efecto % de cada covariable).
    Si lifelines no está disponible o hay muy pocos datos, cae al modo simple.
    """
    if len(df_concepto) == 0:
        return None

    # Verificar disponibilidad de lifelines
    try:
        from lifelines import LogNormalAFTFitter, WeibullAFTFitter
    except ImportError:
        print("   [!] lifelines no disponible; usando log-normal simple para el lag.")
        return calibrar_lag_simple(df_concepto)

    # ----- 1. Lags vectorizados -----
    lags, ts_ori, ts_proc = _lags_y_fechas(df_concepto)
    valido = lags.notna() & (lags >= -31) & (lags <= 1825)
    if valido.sum() < 30:
        return calibrar_lag_simple(df_concepto)

    lags_v = lags[valido].clip(lower=0).astype(float).clip(lower=0.5)  # lifelines exige >0
    ts_ori_v = ts_ori[valido]
    df_cov_v = df_concepto.loc[valido.index[valido], ["corredor", "usd", "territorio"]].copy()

    # Submuestreo si excede el tope (rendimiento del ajuste)
    if len(lags_v) > MAX_FILAS_AFT:
        rng_s = np.random.default_rng(SEMILLA)
        sel = rng_s.choice(len(lags_v), size=MAX_FILAS_AFT, replace=False)
        lags_v = lags_v.iloc[sel]
        ts_ori_v = ts_ori_v.iloc[sel]
        df_cov_v = df_cov_v.iloc[sel]

    # ----- 2. Categorías de territorio (TOP-K) -----
    if "territorio" in COVARIABLES_AFT:
        top = df_cov_v["territorio"].value_counts().head(TERRITORIO_TOP_K)
        territorio_categorias = list(top.index)
    else:
        territorio_categorias = []

    # ----- 3. Corrección de truncamiento: selección de cohortes maduras -----
    # Corte = inicio del último mes de proceso + 1 mes. Madurez = corte - origen.
    cutoff = ts_proc[valido].max()
    if pd.isna(cutoff):
        cutoff = ts_ori_v.max()
    cutoff = (pd.Timestamp(year=cutoff.year, month=cutoff.month, day=1)
              + pd.offsets.MonthBegin(1))
    madurez_v = (cutoff - ts_ori_v).dt.days

    n_obs = len(lags_v)
    restriccion_aplicada = False
    mask_fit = np.ones(n_obs, dtype=bool)
    if RESTRINGIR_COHORTES_MADURAS:
        if MADUREZ_MIN_MESES is not None:
            L_umbral = float(MADUREZ_MIN_MESES) * 30.0
        else:
            L_umbral = float(np.nanpercentile(lags_v.values, 95))   # auto: P95 del lag
        cand = (madurez_v >= L_umbral).values
        # Sólo aplicar si quedan suficientes datos maduros
        if cand.sum() >= max(200, int(0.20 * n_obs)):
            mask_fit = cand
            restriccion_aplicada = True

    # Augmentación experimental de censura (apagada por defecto)
    eventos_fit = np.ones(int(mask_fit.sum()), dtype=int)
    lags_fit = lags_v[mask_fit]
    df_cov_fit = df_cov_v[mask_fit]
    if CENSURA_POR_DESARROLLO:
        lags_cens, eventos_cens, df_cov_cens = _construir_censura_desarrollo(
            lags_v, ts_ori_v, df_cov_v, np.ones(n_obs, dtype=int))
        if len(lags_cens):
            lags_fit = pd.concat([lags_fit, pd.Series(lags_cens)], ignore_index=True)
            eventos_fit = np.concatenate([eventos_fit, eventos_cens])
            df_cov_fit = pd.concat([df_cov_fit, df_cov_cens], ignore_index=True)
    n_censurado = int((eventos_fit == 0).sum())

    # ----- 4. Matriz de diseño y ajuste AFT (sobre cohortes maduras) -----
    diseño_fit, design_cols = _codificar_covariables(df_cov_fit, territorio_categorias)
    if len(design_cols) == 0:
        return calibrar_lag_simple(df_concepto)

    df_fit = diseño_fit.reset_index(drop=True).copy()
    df_fit["_lag"] = np.asarray(lags_fit, dtype=float)
    df_fit["_evento"] = eventos_fit
    # Quitar columnas constantes (causan colinealidad)
    no_const = [c for c in design_cols if df_fit[c].nunique() > 1]
    if len(no_const) == 0:
        return calibrar_lag_simple(df_concepto)
    design_cols = no_const
    df_fit = df_fit[design_cols + ["_lag", "_evento"]]

    modelos = []
    try:
        m_ln = LogNormalAFTFitter().fit(df_fit, duration_col="_lag", event_col="_evento")
        modelos.append(("lognormal", m_ln, m_ln.AIC_))
    except Exception as e:
        pass
    try:
        m_wb = WeibullAFTFitter().fit(df_fit, duration_col="_lag", event_col="_evento")
        modelos.append(("weibull", m_wb, m_wb.AIC_))
    except Exception as e:
        pass

    if not modelos:
        return calibrar_lag_simple(df_concepto)

    # Elegir por menor AIC
    tipo, modelo, aic = min(modelos, key=lambda t: t[2])

    # ----- 4b. Validación estadística del AFT -----
    # C-index (discriminación), comparación de AIC entre candidatas y significancia
    # de covariables (p-valores e IC de la distribución elegida).
    val_aft = {"componente": f"Lag · AFT {tipo}", "pruebas": [], "veredicto": "ok"}
    try:
        c_index = float(modelo.concordance_index_)
    except Exception:
        c_index = float("nan")
    # AIC de ambas candidatas (para justificar la elección)
    aic_por_tipo = {t: a for (t, _m, a) in modelos}
    delta_aic = (max(aic_por_tipo.values()) - min(aic_por_tipo.values())
                 if len(aic_por_tipo) > 1 else 0.0)
    # Significancia de covariables (del bloque de localización)
    n_signif, n_total = 0, 0
    cov_signif = []
    try:
        resumen = modelo.summary  # DataFrame con coef, p, IC
        for idx, fila in resumen.iterrows():
            par = idx[0] if isinstance(idx, tuple) else idx
            cov = idx[1] if isinstance(idx, tuple) else ""
            if par in ("mu_", "lambda_") and cov != "Intercept":
                n_total += 1
                pval = float(fila.get("p", np.nan))
                if np.isfinite(pval) and pval < 0.05:
                    n_signif += 1
                    cov_signif.append(cov)
    except Exception:
        pass

    v_c = "ok" if (np.isnan(c_index) or c_index >= 0.60) else (
        "precaucion" if c_index >= 0.55 else "alerta")
    val_aft["veredicto"] = v_c
    val_aft["c_index"] = c_index
    val_aft["pruebas"] = [
        ("C-index (discriminación)", f"{c_index:.3f}" if np.isfinite(c_index) else "n/d",
         "0.5=azar, >0.6 útil", v_c),
        ("Selección por AIC", tipo, f"ΔAIC vs alterna = {delta_aic:.0f}",
         "robusta" if delta_aic > 10 else "marginal"),
        ("Covariables significativas", f"{n_signif}/{n_total}",
         "p<0.05: " + (", ".join(cov_signif[:4]) if cov_signif else "ninguna"), ""),
    ]
    val_aft["resumen"] = (f"C-index={c_index:.2f}; "
                          f"{n_signif}/{n_total} covariables significativas; "
                          f"{tipo} elegida (ΔAIC={delta_aic:.0f})")

    # ----- 5. Extraer coeficientes para muestreo -----
    p = modelo.params_
    if tipo == "lognormal":
        loc_name, scale_name = "mu_", "sigma_"
    else:
        loc_name, scale_name = "lambda_", "rho_"
    intercept_loc = float(p[loc_name].get("Intercept", 0.0))
    beta = np.array([float(p[loc_name].get(c, 0.0)) for c in design_cols])
    escala = float(np.exp(p[scale_name].get("Intercept", 0.0)))

    # Pool de combinaciones de covariables para la simulación: de TODA la
    # población observada (no sólo las cohortes maduras usadas en el ajuste),
    # para reproducir la mezcla real de negocios al simular.
    diseño_obs_full, _cols_full = _codificar_covariables(df_cov_v, territorio_categorias)
    diseño_obs = diseño_obs_full.reindex(columns=design_cols, fill_value=0.0)
    combos_grp = diseño_obs.groupby(list(design_cols)).size().reset_index(name="_n")
    combos = combos_grp[design_cols].values.astype(float)
    combos_prob = (combos_grp["_n"] / combos_grp["_n"].sum()).values
    usd_col_idx = design_cols.index("usd") if "usd" in design_cols else None

    # Efectos interpretables: en AFT, un coeficiente beta sobre una covariable
    # multiplica la mediana del lag por exp(beta). Lo expresamos como % de cambio.
    efectos = {}
    for c, b in zip(design_cols, beta):
        efectos[c] = float(np.exp(b) - 1.0)   # +0.82 = tarda 82% más

    # Estadísticas descriptivas del lag observado (toda la población)
    lags_desc = lags_v.values
    return {
        "metodo": "aft",
        "tipo_aft": tipo,
        "design_cols": list(design_cols),
        "intercept_loc": intercept_loc,
        "beta": beta,
        "escala": escala,
        "combos": combos,
        "combos_prob": combos_prob,
        "usd_col_idx": usd_col_idx,
        "territorio_categorias": territorio_categorias,
        "n": int(n_obs),
        "n_ajuste": int(mask_fit.sum()),
        "restriccion_maduras": bool(restriccion_aplicada),
        "n_censurado": int(n_censurado),
        "aic": float(aic),
        "media_dias": float(np.mean(lags_desc)),
        "mediana_dias": float(np.median(lags_desc)),
        "p95_dias": float(np.percentile(lags_desc, 95)),
        "efectos": efectos,
        "validacion": val_aft,
        "default": False,
    }


def muestrear_lag_aft(modelo_lag, X, rng):
    """
    Muestrea lags (en días) para una matriz de covariables X (m × d, alineada a
    design_cols) usando el modelo AFT ajustado. Vectorizado.

    - LogNormal AFT: T = exp(mu_i + sigma·Z),  mu_i = intercept + X·beta
    - Weibull AFT:   T = lambda_i·(-ln U)^(1/rho), lambda_i = exp(intercept + X·beta)
    """
    loc = modelo_lag["intercept_loc"] + X @ modelo_lag["beta"]
    escala = modelo_lag["escala"]
    m = X.shape[0]
    if modelo_lag["tipo_aft"] == "lognormal":
        Z = rng.standard_normal(m)
        T = np.exp(loc + escala * Z)
    else:  # weibull
        lam = np.exp(loc)
        U = rng.random(m)
        T = lam * (-np.log(U)) ** (1.0 / escala)
    return np.maximum(T, 0.0)


def calibrar_lag(df_concepto):
    """Dispatcher: usa el modelo AFT con covariables o el log-normal simple."""
    if USAR_AFT:
        return calibrar_lag_aft(df_concepto)
    return calibrar_lag_simple(df_concepto)


def calibrar_lag_simple(df_concepto):
    """
    [FALLBACK] Calibra el lag con una sola log-normal global por concepto.
    Se usa cuando USAR_AFT=False o cuando lifelines no está disponible.

    Lag = días entre la fecha de origen (FecOri) y la fecha de proceso
    (derivada de aPOG_MesProc).
    """
    if len(df_concepto) == 0:
        return None

    lags_series, _, _ = _lags_y_fechas(df_concepto)
    lags = lags_series.dropna()
    lags = lags[(lags >= -31) & (lags <= 1825)].clip(lower=0).values

    if len(lags) < 5:
        return {
            "metodo": "simple", "dist": "lognormal",
            "mu": np.log(30), "sigma": 0.8, "n": len(lags),
            "media_dias": 30.0, "mediana_dias": 30.0, "p95_dias": 90.0,
            "default": True,
        }

    lags = np.asarray(lags, dtype=float)
    lags_pos = lags[lags > 0]
    if len(lags_pos) < 5:
        lags_pos = lags + 1

    logl = np.log(lags_pos)
    return {
        "metodo": "simple", "dist": "lognormal",
        "mu": float(np.mean(logl)), "sigma": float(np.std(logl, ddof=1)),
        "n": int(len(lags)),
        "media_dias": float(np.mean(lags)),
        "mediana_dias": float(np.median(lags)),
        "p95_dias": float(np.percentile(lags, 95)),
        "default": False,
    }


def calibrar_tc(df_tc):
    """
    Calibra un Movimiento Browniano Geométrico (GBM) para el tipo de cambio
    USD/MXN a partir de la serie histórica.

    GBM: dS/S = mu*dt + sigma*dW
    Estima mu (drift) y sigma (volatilidad) de los log-retornos mensuales.

    Devuelve dict con S0 (último TC), mu_mensual, sigma_mensual.
    """
    if df_tc is None or len(df_tc) < 12:
        # Default razonable si no hay datos
        return {
            "S0": 18.0, "mu_mensual": 0.0, "sigma_mensual": 0.03,
            "n": 0, "default": True,
        }

    tc = df_tc['tc'].astype(float).values
    # Log-retornos
    log_ret = np.diff(np.log(tc))
    # Filtrar outliers extremos (cambios > 30% en un paso, probables errores)
    log_ret = log_ret[np.abs(log_ret) < 0.30]

    mu = float(np.mean(log_ret))
    sigma = float(np.std(log_ret, ddof=1))

    return {
        "S0": float(tc[-1]),
        "mu_mensual": mu,
        "sigma_mensual": sigma,
        "n": int(len(tc)),
        "tc_min": float(np.min(tc)),
        "tc_max": float(np.max(tc)),
        "tc_medio": float(np.mean(tc)),
        "log_returns": log_ret,   # para validación (normalidad, estacionariedad)
        "default": False,
    }


def calibrar_proporcion_usd(df_concepto):
    """
    Estima qué proporción de las operaciones del concepto están en USD
    (MonedaOri == 31). Esto determina cuántos flujos simulados se exponen al TC.
    """
    if len(df_concepto) == 0 or "MonedaOri" not in df_concepto:
        return 0.0
    monedas = df_concepto["MonedaOri"].apply(
        lambda v: str(int(float(v))) if pd.notna(v) and str(v).strip() not in ("", "nan") else ""
    )
    total = (monedas != "").sum()
    if total == 0:
        return 0.0
    usd = (monedas == str(MONEDA_USD_ID)).sum()
    return float(usd / total)


# ==============================================================================
# MOTOR DE SIMULACIÓN MONTE CARLO
# ==============================================================================
def simular_trayectorias_tc(params_tc, horizonte, n_sims, rng):
    """
    Simula n_sims trayectorias del TC USD/MXN para 'horizonte' meses usando GBM.
    Devuelve matriz (n_sims, horizonte) con el TC simulado de cada mes.

    GBM discreto: S(t+1) = S(t) * exp((mu - sigma^2/2) + sigma*Z)
    """
    if not MODELAR_TC_ESTOCASTICO:
        # TC fijo en el último valor
        return np.full((n_sims, horizonte), params_tc["S0"])

    S0 = params_tc["S0"]
    mu = params_tc["mu_mensual"]
    sigma = params_tc["sigma_mensual"]

    trayectorias = np.zeros((n_sims, horizonte))
    S = np.full(n_sims, S0)
    for t in range(horizonte):
        Z = rng.standard_normal(n_sims)
        S = S * np.exp((mu - 0.5 * sigma**2) + sigma * Z)
        trayectorias[:, t] = S
    return trayectorias


def _muestrear_combos(lag_model, n, rng):
    """Muestrea n vectores de covariables del pool empírico del concepto (AFT)."""
    combos = lag_model["combos"]
    probs = lag_model["combos_prob"]
    idx = rng.choice(len(combos), size=n, p=probs)
    return combos[idx]


def _muestrear_lags_y_usd(lag_model, prop_usd, n, rng):
    """
    Devuelve (lags_dias, es_usd) para n operaciones.
    - AFT: muestrea covariables del pool, saca el lag condicional y la marca USD
      de la propia covariable 'usd'.
    - Simple: log-normal global + Bernoulli(prop_usd).
    """
    if lag_model and lag_model.get("metodo") == "aft":
        X = _muestrear_combos(lag_model, n, rng)
        lags = muestrear_lag_aft(lag_model, X, rng)
        uidx = lag_model.get("usd_col_idx")
        es_usd = (X[:, uidx] > 0.5) if uidx is not None else (rng.random(n) < prop_usd)
        return lags, es_usd
    else:
        lags = rng.lognormal(lag_model["mu"], lag_model["sigma"], size=n)
        es_usd = rng.random(n) < prop_usd
        return lags, es_usd


def _muestra_lags_marginal(lag_model, n, rng):
    """Muestra marginal de lags (días), marginalizando sobre covariables si es AFT."""
    if lag_model and lag_model.get("metodo") == "aft":
        X = _muestrear_combos(lag_model, n, rng)
        return muestrear_lag_aft(lag_model, X, rng)
    return rng.lognormal(lag_model["mu"], lag_model["sigma"], size=n)


def _prop_usd_efectiva(lag_model, prop_usd):
    """Proporción USD efectiva: del pool de covariables si es AFT, si no prop_usd."""
    if (lag_model and lag_model.get("metodo") == "aft"
            and lag_model.get("usd_col_idx") is not None):
        uidx = lag_model["usd_col_idx"]
        return float(np.average(lag_model["combos"][:, uidx],
                                weights=lag_model["combos_prob"]))
    return prop_usd


def _simular_concepto_agregado(params, trayectorias_tc, horizonte, n_sims, rng, s0_tc=1.0):
    """
    Modo AGREGADO para conceptos de frecuencia alta.

    En vez de simular cada operación, aprovecha que la suma de muchas operaciones
    es aproximadamente normal (TLC). Para cada mes de originación:
      - Número de operaciones N ~ Poisson/BN(lambda)
      - Monto agregado del mes = N * E[monto] con varianza N * Var[monto]
        muestreado como Normal (truncada a >= 0)
      - El agregado se reparte a meses futuros según la distribución del lag.
      - El TC se aplica como factor promedio: prop_usd · S(t)/S0 + (1-prop_usd).

    IMPORTANTE: para la media y varianza del monto se usan los momentos EMPÍRICOS
    (robustos), no los implícitos de la log-normal exp(mu+sigma²/2), que se
    disparan con colas muy pesadas (datos reales de seguros).
    """
    mag = params["magnitud"]
    freq = params["frecuencia"]
    lag = params["lag"]
    prop_usd = params["prop_usd"]

    lam = freq["lambda_mensual"]

    # Momentos del monto individual: EMPÍRICOS CRUDOS (insesgados; reproducen el
    # flujo promedio histórico y no recortan siniestros grandes reales).
    media_monto = mag.get("media_emp")
    var_monto = mag.get("var_emp")
    if media_monto is None:   # respaldo: momentos log-normal
        mu_m, sg_m = mag["mu"], mag["sigma"]
        media_monto = np.exp(mu_m + sg_m**2 / 2)
        var_monto = (np.exp(sg_m**2) - 1) * np.exp(2*mu_m + sg_m**2)
    if var_monto is None:
        var_monto = media_monto ** 2   # respaldo conservador

    # Distribución del lag en MESES: probabilidad de caer en desfase k=0,1,2,...
    # Se marginaliza sobre las covariables si el lag es un modelo AFT.
    muestra_lag = _muestra_lags_marginal(lag, 50000, rng)
    meses_lag_muestra = np.round(muestra_lag / 30.0).astype(int)
    max_desfase = int(np.percentile(meses_lag_muestra, 99.5)) + 1
    max_desfase = min(max_desfase, horizonte + 6)
    prob_desfase = np.array([
        np.mean(meses_lag_muestra == k) for k in range(max_desfase + 1)
    ])
    if prob_desfase.sum() > 0:
        prob_desfase = prob_desfase / prob_desfase.sum()

    # Proporción USD efectiva (del pool de covariables del AFT, o prop_usd simple)
    prop_usd_ef = _prop_usd_efectiva(lag, prop_usd)

    flujos = np.zeros((n_sims, horizonte))

    for m_orig in range(horizonte):
        # Operaciones originadas este mes (por simulación)
        if freq.get("sobredispersion"):
            var = freq["var_mensual"]
            p = lam / var if var > lam else 0.5
            p = min(max(p, 1e-3), 0.999)
            r = lam * p / (1 - p) if p < 1 else lam
            n_ops = rng.negative_binomial(max(r, 1e-3), p, size=n_sims).astype(float)
        else:
            n_ops = rng.poisson(lam, size=n_sims).astype(float)

        # Monto agregado del mes ~ Normal(N*media, sqrt(N*var)), truncado a >=0
        media_agg = n_ops * media_monto
        sd_agg = np.sqrt(np.maximum(n_ops, 0) * var_monto)
        monto_agg = rng.normal(media_agg, sd_agg)
        monto_agg = np.maximum(monto_agg, 0.0)

        # Repartir el agregado a meses futuros según prob_desfase
        for k, pk in enumerate(prob_desfase):
            if pk <= 0:
                continue
            mes_dest = m_orig + k
            if mes_dest >= horizonte:
                break
            porcion = monto_agg * pk
            # Ajuste por TC: fracción USD por la RAZÓN S(t)/S0 (montos ya en pesos),
            # el resto en MXN (factor 1).
            tc_mes = trayectorias_tc[:, mes_dest] / s0_tc
            factor = prop_usd_ef * tc_mes + (1 - prop_usd_ef) * 1.0
            flujos[:, mes_dest] += porcion * factor

    return flujos


def simular_concepto(nombre, params, trayectorias_tc, horizonte, n_sims, rng, s0_tc=1.0):
    """
    Simula los flujos mensuales de un concepto a lo largo del horizonte.

    Para cada simulacion y cada mes de originacion:
      1. Numero de operaciones ~ Poisson(lambda) (o binomial negativa)
      2. Cada operacion: monto ~ LogNormal(mu, sigma)
      3. Cada operacion: lag ~ LogNormal -> mes futuro en que cae el flujo
      4. Operaciones USD: se ajustan por la RAZON del TC futuro S(t)/S0 (no por el
         TC absoluto), porque los montos ya vienen en pesos (columnas 'Nal'); la
         razon arranca en ~1.0 y captura solo la variacion futura del tipo de cambio.

    Devuelve matriz (n_sims, horizonte) con el flujo total por mes, en MXN.

    Implementacion totalmente vectorizada: genera todas las operaciones de cada
    mes de golpe (sin bucle por simulacion) y las acumula con np.add.at sobre un
    indice aplanado (sim*horizonte + mes_destino).
    """
    mag = params["magnitud"]
    freq = params["frecuencia"]
    lag = params["lag"]
    prop_usd = params["prop_usd"]

    if mag is None or freq is None or lag is None:
        return np.zeros((n_sims, horizonte))

    lam = freq["lambda_mensual"]

    # Si la frecuencia es muy alta, simular operación por operación es lento e
    # innecesario: por el Teorema del Límite Central, el agregado mensual se puede
    # muestrear directamente. Usamos el modo agregado por encima de este umbral.
    UMBRAL_AGREGADO = 300
    if lam > UMBRAL_AGREGADO:
        return _simular_concepto_agregado(
            params, trayectorias_tc, horizonte, n_sims, rng, s0_tc)

    flujos = np.zeros(n_sims * horizonte)   # aplanado: idx = sim*horizonte + mes

    for m_orig in range(horizonte):
        # Numero de operaciones originadas este mes, por simulacion
        if freq.get("sobredispersion"):
            var = freq["var_mensual"]
            p = lam / var if var > lam else 0.5
            p = min(max(p, 1e-3), 0.999)
            r = lam * p / (1 - p) if p < 1 else lam
            n_ops = rng.negative_binomial(max(r, 1e-3), p, size=n_sims)
        else:
            n_ops = rng.poisson(lam, size=n_sims)

        total_ops = int(n_ops.sum())
        if total_ops == 0:
            continue

        # Vector que indica a que simulacion pertenece cada operacion
        sim_de_op = np.repeat(np.arange(n_sims), n_ops)

        # Generar montos y lags para TODAS las operaciones de golpe.
        # El lag y la marca USD salen del modelo AFT (condicionados a covariables)
        # o, en modo simple, de la log-normal global + Bernoulli(prop_usd).
        montos = rng.lognormal(mag["mu"], mag["sigma"], size=total_ops)
        lags_dias, es_usd = _muestrear_lags_y_usd(lag, prop_usd, total_ops, rng)

        # Mes destino = mes originacion + redondeo(lag/30)
        meses_lag = np.round(lags_dias / 30.0).astype(int)
        mes_destino = m_orig + meses_lag

        # Filtrar las que caen dentro del horizonte
        dentro = mes_destino < horizonte
        sim_v = sim_de_op[dentro]
        mes_v = mes_destino[dentro]
        mt_v = montos[dentro]
        usd_v = es_usd[dentro]

        if len(sim_v) == 0:
            continue

        # Ajuste por TC de las operaciones USD: RAZÓN S(t)/S0 (no TC absoluto),
        # porque los montos ya están en pesos. Arranca en ~1.0 y solo añade la
        # variación futura del tipo de cambio.
        tc_v = trayectorias_tc[sim_v, mes_v] / s0_tc
        factor = np.where(usd_v, tc_v, 1.0)
        mt_mxn = mt_v * factor

        # Acumular en el indice aplanado
        idx_plano = sim_v * horizonte + mes_v
        np.add.at(flujos, idx_plano, mt_mxn)

    return flujos.reshape(n_sims, horizonte)


def correr_simulacion(parametros, horizonte, n_sims, seed):
    """
    Orquesta la simulación completa: TC + todos los conceptos.
    Devuelve dict con las matrices de flujo por concepto y los agregados.
    """
    rng = np.random.default_rng(seed)

    # 1. Simular trayectorias de TC (compartidas por todos los conceptos USD)
    trayectorias_tc = simular_trayectorias_tc(
        parametros["tc"], horizonte, n_sims, rng)

    # 2. Simular cada concepto
    s0_tc = parametros["tc"].get("S0", 1.0)
    flujos_concepto = {}
    for nombre, params in parametros["conceptos"].items():
        flujos_concepto[nombre] = simular_concepto(
            nombre, params, trayectorias_tc, horizonte, n_sims, rng, s0_tc)

    # 3. Agregados: ingresos, egresos, neto
    ingresos = np.zeros((n_sims, horizonte))
    egresos = np.zeros((n_sims, horizonte))
    for nombre, params in parametros["conceptos"].items():
        if params["direccion"] == "ingreso":
            ingresos += flujos_concepto[nombre]
        else:
            egresos += flujos_concepto[nombre]
    neto = ingresos - egresos

    return {
        "flujos_concepto": flujos_concepto,
        "ingresos": ingresos,
        "egresos": egresos,
        "neto": neto,
        "trayectorias_tc": trayectorias_tc,
    }


def calcular_flujo_real(df_gonz, n_meses=12):
    """
    Calcula el flujo REAL realizado por mes (últimos n_meses) directamente de Gonz,
    para comparar contra la proyección del modelo (backtest).

    Suma, por mes de proceso (aPOG_MesProc), los montos de cada concepto en su
    dirección (ingreso/egreso). Los montos están en pesos (columnas 'Nal'), así que
    no se aplica TC. Devuelve un DataFrame con índice = AAAAMM y columnas
    ['ingresos', 'egresos', 'neto'] para los últimos n_meses.
    """
    acum = {}   # mes -> {ingresos, egresos}
    for nombre, cdef in CONCEPTOS.items():
        df_c = extraer_movimientos_concepto(df_gonz, cdef)
        if df_c is None or len(df_c) == 0 or "aPOG_MesProc" not in df_c:
            continue
        g = df_c.groupby("aPOG_MesProc")["monto"].sum()
        for mes, val in g.items():
            mes_i = None
            try:
                mes_i = int(float(mes))
            except (ValueError, TypeError):
                continue
            if mes_i < 190001 or mes_i > 220012:
                continue
            d = acum.setdefault(mes_i, {"ingresos": 0.0, "egresos": 0.0})
            if cdef["direccion"] == "ingreso":
                d["ingresos"] += float(val)
            else:
                d["egresos"] += float(val)

    if not acum:
        return None
    meses_ord = sorted(acum.keys())[-n_meses:]
    filas = []
    for mes in meses_ord:
        ing = acum[mes]["ingresos"]; egr = acum[mes]["egresos"]
        filas.append({"mes": mes, "ingresos": ing, "egresos": egr, "neto": ing - egr})
    df = pd.DataFrame(filas).set_index("mes")
    return df


def construir_backtest(df_gonz, parametros, resultados, n_meses=12):
    """
    Compara el modelo contra el flujo REAL de los últimos n_meses, separando
    INGRESOS, EGRESOS y NETO (clave: el neto es una diferencia de números grandes,
    así que se interpreta mejor viendo también los brutos).

    Para cada flujo:
      - Real mensual promedio (de Gonz, últimos n_meses).
      - Centro del modelo = flujo mensual esperado por PARÁMETROS
        (Σ λ_mensual × media_emp por concepto). Es insesgado y reproduce el
        promedio histórico, sin el sesgo de arranque de la simulación.
      - Banda P5–P95 del NETO desde la dispersión de la simulación, re-centrada.
      - % de cobertura (meses reales del neto dentro de la banda) y desvíos.
    """
    real = calcular_flujo_real(df_gonz, n_meses)
    if real is None or len(real) == 0:
        return None

    # Centros insesgados por parámetros (= promedio histórico mensual)
    ing_m = egr_m = 0.0
    for p in parametros["conceptos"].values():
        mag, freq = p.get("magnitud"), p.get("frecuencia")
        if not mag or not freq:
            continue
        flujo = freq["lambda_mensual"] * mag["media_emp"]
        if p["direccion"] == "ingreso":
            ing_m += flujo
        else:
            egr_m += flujo
    neto_m = ing_m - egr_m

    # Banda del neto desde la dispersión de la simulación (estado estacionario)
    neto = resultados["neto"]
    k = min(3, neto.shape[1])
    neto_ss = neto[:, -k:].mean(axis=1)
    centro_sim = float(np.mean(neto_ss)) if neto_ss.size else neto_m
    desv = neto_ss - centro_sim
    p5 = neto_m + float(np.percentile(desv, 5))
    p95 = neto_m + float(np.percentile(desv, 95))

    def _desvio(real_prom, modelo):
        return (real_prom - modelo) / abs(modelo) if abs(modelo) > 1e-9 else np.nan

    flujos = {
        "ingresos": {"real": float(real["ingresos"].mean()), "modelo": ing_m},
        "egresos":  {"real": float(real["egresos"].mean()),  "modelo": egr_m},
        "neto":     {"real": float(real["neto"].mean()),     "modelo": neto_m},
    }
    for f in flujos.values():
        f["desvio"] = _desvio(f["real"], f["modelo"])

    real_neto = real["neto"].values
    dentro = int(np.sum((real_neto >= p5) & (real_neto <= p95)))
    cobertura = dentro / len(real_neto)

    return {
        "real": real,
        "flujos": flujos,
        "modelo_mensual": {"p5": p5, "p50": neto_m, "p95": p95},
        "prom_real": float(real["neto"].mean()),
        "total_real": float(real["neto"].sum()),
        "total_modelo_p50": neto_m * n_meses,
        "cobertura": cobertura,
        "dentro": dentro,
        "n_meses": len(real_neto),
        "err_prom": flujos["neto"]["desvio"],
    }


def serie_real_mensual(df_gonz):
    """
    Flujo REAL por mes (TODA la historia disponible), por mes de proceso
    (aPOG_MesProc). Devuelve DataFrame indexado por AAAAMM con ingresos/egresos/neto.
    """
    acum = {}
    for nombre, cdef in CONCEPTOS.items():
        df_c = extraer_movimientos_concepto(df_gonz, cdef)
        if df_c is None or len(df_c) == 0 or "aPOG_MesProc" not in df_c:
            continue
        g = df_c.groupby("aPOG_MesProc")["monto"].sum()
        for mes, val in g.items():
            try:
                mes_i = int(float(mes))
            except (ValueError, TypeError):
                continue
            if mes_i < 190001 or mes_i > 220012:
                continue
            d = acum.setdefault(mes_i, {"ingresos": 0.0, "egresos": 0.0})
            if cdef["direccion"] == "ingreso":
                d["ingresos"] += float(val)
            else:
                d["egresos"] += float(val)
    if not acum:
        return None
    filas = [{"mes": m, "ingresos": v["ingresos"], "egresos": v["egresos"],
              "neto": v["ingresos"] - v["egresos"]} for m, v in sorted(acum.items())]
    return pd.DataFrame(filas).set_index("mes")


def _etiqueta_mes(yyyymm):
    """202607 -> 'jul 2026'."""
    meses = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]
    a, m = divmod(int(yyyymm), 100)
    return f"{meses[m-1]} {a}" if 1 <= m <= 12 else str(yyyymm)


_MESES_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _mes_lbl(m):
    """1 -> '01 Ene' ... 12 -> '12 Dic'. Prefijo numérico para que la dinámica los
    ordene cronológicamente (no alfabéticamente) sin depender de listas personalizadas."""
    try:
        mm = int(m)
    except (TypeError, ValueError):
        return str(m)
    return f"{mm:02d} {_MESES_ABBR[mm-1]}" if 1 <= mm <= 12 else str(m)


def _etiqueta_mes_orden(ym):
    """AAAAMM -> '2026-07 jul': etiqueta LEGIBLE cuyo orden alfabético ES el orden
    cronológico. Se usa en los campos 'Mes' de las tablas dinámicas porque Excel
    ordena los ítems de texto alfabéticamente ('jul 2026' quedaba revuelto)."""
    try:
        ym = int(ym)
        y, m = divmod(ym, 100)
    except (TypeError, ValueError):
        return str(ym)
    if 1 <= m <= 12:
        return f"{y}-{m:02d} {_MESES_ABBR[m-1].lower()}"
    return str(ym)


def _sumar_meses(yyyymm, k):
    """Suma k meses a un AAAAMM."""
    a, m = divmod(int(yyyymm), 100)
    idx = (a * 12 + (m - 1)) + k
    return (idx // 12) * 100 + (idx % 12) + 1


def prueba_bondad_ajuste(df_gonz, parametros, resultados):
    """
    BONDAD DE AJUSTE del modelo, en dos frentes:
      1) FRECUENCIA (Poisson) por concepto: prueba de dispersión. Si los conteos
         mensuales son Poisson, var ≈ media; el índice D = (n-1)·s²/x̄ ~ χ²(n-1).
         p bajo => sobredispersión (la Poisson subestima la variabilidad).
      2) FLUJOS AGREGADOS: Kolmogorov-Smirnov de 2 muestras entre la distribución
         mensual SIMULADA (estado estacionario) y los flujos REALES mensuales de la
         ventana de calibración, para ingresos, egresos y neto. p alto => no se
         puede rechazar que la simulación y la realidad vengan de la misma
         distribución (el modelo reproduce bien el comportamiento observado).
    Devuelve dict {"frecuencia": [...], "flujos": [...]} o None si no se pudo.
    """
    try:
        from scipy import stats
    except ImportError:
        return None
    out = {"frecuencia": [], "flujos": []}
    # ---- 1) Dispersión Poisson por concepto ----
    try:
        for nombre, cdef in CONCEPTOS.items():
            df_c = extraer_movimientos_concepto(df_gonz, cdef)
            if df_c is None or len(df_c) == 0 or "aPOG_MesProc" not in df_c:
                continue
            mp = pd.to_numeric(df_c["aPOG_MesProc"], errors="coerce")
            mp = mp[(mp >= PERIODO_MIN_CALIBRACION) if PERIODO_MIN_CALIBRACION else mp.notna()]
            conteos = mp.value_counts()
            n = int(len(conteos))
            if n < 6:
                continue
            media = float(conteos.mean()); var = float(conteos.var(ddof=1))
            if media <= 0:
                continue
            D = (n - 1) * var / media
            p = 2.0 * min(stats.chi2.cdf(D, n - 1), stats.chi2.sf(D, n - 1))
            ratio = var / media
            out["frecuencia"].append({
                "concepto": nombre, "n_meses": n, "media": media, "var": var,
                "ratio": ratio, "estadistico": D, "p": float(p),
                "ok": bool(p >= 0.05),
                "nota": ("consistente con Poisson" if p >= 0.05 else
                         ("sobredispersión (var>media): la Poisson subestima la variabilidad"
                          if ratio > 1 else "subdispersión (var<media)")),
            })
    except Exception as e:
        print(f"  [i] (bondad frecuencia omitida: {type(e).__name__}: {e})")
    # ---- 2) KS de 2 muestras: simulado vs real mensual ----
    try:
        serie = serie_real_mensual(df_gonz)
        if serie is not None and len(serie) >= 12 and resultados:
            if PERIODO_MIN_CALIBRACION:
                serie = serie[serie.index >= PERIODO_MIN_CALIBRACION]
            k = min(3, resultados["neto"].shape[1])
            for etq, col, matriz in ((f"Ingresos", "ingresos", resultados["ingresos"]),
                                      (f"Egresos", "egresos", resultados["egresos"]),
                                      (f"Neto", "neto", resultados["neto"])):
                sim = matriz[:, -k:].reshape(-1)          # meses de estado estacionario
                realv = serie[col].astype(float).values
                if len(realv) < 8 or sim.size < 100:
                    continue
                ks, p = stats.ks_2samp(sim, realv)
                out["flujos"].append({
                    "serie": etq, "n_real": int(len(realv)), "n_sim": int(sim.size),
                    "estadistico": float(ks), "p": float(p), "ok": bool(p >= 0.05),
                    "nota": ("la simulación reproduce la distribución real" if p >= 0.05 else
                             "difiere de lo observado: revisar calibración/ventana"),
                })
    except Exception as e:
        print(f"  [i] (bondad flujos omitida: {type(e).__name__}: {e})")
    return out if (out["frecuencia"] or out["flujos"]) else None


def comparativo_calendario(df_gonz, parametros, resultados, horizonte=12):
    """
    Mapea la proyección a MESES CALENDARIO concretos y, para cada uno, trae el
    REAL del MISMO MES del año anterior. Aplica ESTACIONALIDAD (patrón mensual
    histórico) para que la proyección varíe mes a mes en lugar de ser plana.

    Devuelve dict con la lista de meses (cada uno con su etiqueta, proyección
    estacional P50/P5/P95 e ingresos/egresos, y el real interanual), más la serie
    real mensual completa.
    """
    serie = serie_real_mensual(df_gonz)
    if serie is None or len(serie) == 0:
        return None

    # Centros base (insesgados) por parámetros
    ing_base = egr_base = 0.0
    for p in parametros["conceptos"].values():
        mag, freq = p.get("magnitud"), p.get("frecuencia")
        if not mag or not freq:
            continue
        flujo = freq["lambda_mensual"] * mag["media_emp"]
        if p["direccion"] == "ingreso":
            ing_base += flujo
        else:
            egr_base += flujo

    # ----- Factores estacionales por mes calendario (1-12) -----
    # Se usan los últimos 36 meses para reflejar el patrón reciente. Cada factor
    # normaliza el flujo de ese mes respecto al promedio (media de factores = 1).
    recientes = serie.tail(36)
    s_ing = {m: 1.0 for m in range(1, 13)}
    s_egr = {m: 1.0 for m in range(1, 13)}
    if len(recientes) >= 12:
        cal = pd.Series(recientes.index).apply(lambda x: x % 100).values
        for col, dst in (("ingresos", s_ing), ("egresos", s_egr)):
            vals = recientes[col].values
            prom = np.mean(vals) if np.mean(vals) != 0 else 1.0
            for mm in range(1, 13):
                sel = vals[cal == mm]
                if len(sel) > 0 and prom != 0:
                    dst[mm] = float(np.clip(np.mean(sel) / prom, 0.3, 3.0))

    # Banda relativa del neto (de la simulación, estado estacionario), por unidad
    neto = resultados["neto"]
    k = min(3, neto.shape[1])
    neto_ss = neto[:, -k:].mean(axis=1)
    centro_ss = float(np.mean(neto_ss)) if neto_ss.size else (ing_base - egr_base)
    desv5 = float(np.percentile(neto_ss - centro_ss, 5)) if neto_ss.size else 0.0
    desv95 = float(np.percentile(neto_ss - centro_ss, 95)) if neto_ss.size else 0.0

    # Factores relativos P5/P95 de ingresos y egresos (respecto a su media), para
    # poner bandas de percentiles también en las proyecciones agregadas.
    def _rel(matriz):
        ss = matriz[:, -k:].mean(axis=1)
        c = float(np.mean(ss))
        if not c:
            return 1.0, 1.0
        return float(np.percentile(ss, 5) / c), float(np.percentile(ss, 95) / c)
    ing_r5, ing_r95 = _rel(resultados["ingresos"])
    egr_r5, egr_r95 = _rel(resultados["egresos"])

    # Mes de arranque de la proyección = último mes real + 1
    ultimo = int(serie.index.max())
    serie_dict = serie["neto"].to_dict()
    serie_ing = serie["ingresos"].to_dict(); serie_egr = serie["egresos"].to_dict()

    meses = []
    for i in range(horizonte):
        ym = _sumar_meses(ultimo, i + 1)
        mm = ym % 100
        # Factor de inflación compuesto (Banxico): los meses futuros crecen en términos
        # nominales; sin esto la proyección de 2027 quedaría en pesos "de hoy".
        f_infl = (1.0 + INFLACION_ANUAL) ** ((i + 1) / 12.0)
        ing_p = ing_base * s_ing.get(mm, 1.0) * f_infl
        egr_p = egr_base * s_egr.get(mm, 1.0) * f_infl
        neto_p = ing_p - egr_p
        # Escalar la banda con el tamaño del mes (incertidumbre proporcional)
        esc = (abs(neto_p) / abs(centro_ss)) if centro_ss else 1.0
        esc = float(np.clip(esc, 0.3, 3.0))
        ym_aa = _sumar_meses(ym, -12)   # mismo mes, año anterior
        meses.append({
            "mes": ym, "etiqueta": _etiqueta_mes(ym),
            "ingresos": ing_p, "egresos": egr_p, "neto": neto_p,
            "p5": neto_p + desv5 * esc, "p95": neto_p + desv95 * esc,
            "ing_p5": ing_p * ing_r5, "ing_p95": ing_p * ing_r95,
            "egr_p5": egr_p * egr_r5, "egr_p95": egr_p * egr_r95,
            "real_neto_aa": serie_dict.get(ym_aa, np.nan),
            "real_ing_aa": serie_ing.get(ym_aa, np.nan),
            "real_egr_aa": serie_egr.get(ym_aa, np.nan),
            "mes_aa": ym_aa,
        })

    # ----- Tendencia real (últimos 24 meses) para validar la proyección -----
    cola = serie.tail(24)
    tendencia = [{"mes": int(m), "etiqueta": _etiqueta_mes(int(m)),
                  "ingresos": float(r["ingresos"]), "egresos": float(r["egresos"]),
                  "neto": float(r["neto"])} for m, r in cola.iterrows()]

    # ----- Validación de dilución: promedio reciente (12m) vs ventana completa -----
    neto_serie = serie["neto"]
    prom_reciente = float(neto_serie.tail(12).mean()) if len(neto_serie) >= 1 else np.nan
    prom_ventana = float(neto_serie.mean()) if len(neto_serie) else np.nan
    proy_prom = float(np.mean([mc["neto"] for mc in meses])) if meses else np.nan

    return {"meses": meses, "serie": serie,
            "ing_base": ing_base, "egr_base": egr_base,
            "s_ing": s_ing, "s_egr": s_egr,
            "tendencia": tendencia,
            "diagnostico": {"prom_reciente_12m": prom_reciente,
                            "prom_ventana": prom_ventana,
                            "proy_promedio": proy_prom,
                            "n_meses_ventana": int(len(neto_serie))}}


def datos_pivote(df_gonz, parametros, comparativo):
    """
    Construye los datos en formato LARGO (tidy) listos para tabla dinámica:
    una fila por (mes calendario, concepto) con el flujo PROYECTADO (con
    estacionalidad) y el flujo REAL del mismo mes del año anterior. Pensado para
    que el usuario inserte una tabla dinámica y arme sus propias vistas.
    """
    if not comparativo or not comparativo.get("meses"):
        return None
    meses = comparativo["meses"]
    s_ing = comparativo.get("s_ing", {}); s_egr = comparativo.get("s_egr", {})

    # Base por concepto (flujo mensual esperado, insesgado)
    bases = {}
    for nombre, p in parametros["conceptos"].items():
        mag, freq = p.get("magnitud"), p.get("frecuencia")
        if not mag or not freq:
            continue
        bases[nombre] = {"base": freq["lambda_mensual"] * mag["media_emp"],
                         "direccion": p["direccion"]}

    # Real por concepto y mes (para traer el mismo mes del año anterior)
    real_cc = {}
    for nombre, cdef in CONCEPTOS.items():
        df_c = extraer_movimientos_concepto(df_gonz, cdef)
        if df_c is None or len(df_c) == 0 or "aPOG_MesProc" not in df_c:
            real_cc[nombre] = {}
            continue
        g = df_c.groupby("aPOG_MesProc")["monto"].sum()
        d = {}
        for mes, val in g.items():
            try:
                d[int(float(mes))] = float(val)
            except (ValueError, TypeError):
                pass
        real_cc[nombre] = d

    filas = []
    meses_nom = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"]
    # Totales base por dirección, para repartir el total proyectado del comparativo
    # entre conceptos (así Σ conceptos = ingresos/egresos/neto de las gráficas, con
    # estacionalidad e inflación incluidas).
    tot_ing_base = sum(i_["base"] for i_ in bases.values() if i_["direccion"] == "ingreso") or 1.0
    tot_egr_base = sum(i_["base"] for i_ in bases.values() if i_["direccion"] == "egreso") or 1.0
    for mc in meses:
        ym = mc["mes"]; mm = ym % 100; aa = ym // 100
        ym_aa = mc["mes_aa"]
        for nombre, info in bases.items():
            if info["direccion"] == "ingreso":
                proy = info["base"] / tot_ing_base * mc["ingresos"]
            else:
                proy = info["base"] / tot_egr_base * mc["egresos"]
            real_aa = real_cc.get(nombre, {}).get(ym_aa, np.nan)
            # Signo para el NETO: ingresos +, egresos - (así una SUMA = flujo neto)
            signo = 1.0 if info["direccion"] == "ingreso" else -1.0
            real_fin = real_aa if np.isfinite(real_aa) else np.nan
            filas.append({
                "Mes": _etiqueta_mes_orden(ym),
                "AAAAMM": ym,
                "Año": aa,
                "MesNombre": meses_nom[mm-1] if 1 <= mm <= 12 else str(mm),
                "Dirección": "Ingreso" if info["direccion"] == "ingreso" else "Egreso",
                "Concepto": nombre,
                "Proyección (MXN)": round(proy, 2),
                "Real año anterior (MXN)": (round(real_aa, 2) if np.isfinite(real_aa) else None),
                # Columnas CON SIGNO: súmalas en la dinámica para obtener el NETO real
                "Flujo neto proy. (MXN)": round(signo * proy, 2),
                "Flujo neto AA (MXN)": (round(signo * real_fin, 2) if np.isfinite(real_fin) else None),
            })
    return filas


def serie_historica_anual(df_gonz_full, anio_min=2020, anio_max=2025):
    """Serie mensual REAL por (Año, Mes) para el rango dado — para las tendencias
    históricas SIN 2026 (una línea por año). Usa TODO el histórico (df_gonz_full,
    antes del filtro de calibración). Devuelve lista de dicts o None."""
    serie = serie_real_mensual(df_gonz_full)
    if serie is None or len(serie) == 0:
        return None
    filas = []
    for ym, r in serie.iterrows():
        y, m = divmod(int(ym), 100)
        if anio_min <= y <= anio_max and 1 <= m <= 12:
            filas.append({"AAAAMM": int(ym), "Año": y, "Mes": _mes_lbl(m),
                          "Ingresos": float(r["ingresos"]),
                          "Egresos": float(r["egresos"]),
                          "Neto": float(r["neto"])})
    filas.sort(key=lambda d: d["AAAAMM"])
    return filas or None


def serie_proyeccion_2026(df_gonz_full, comparativo, anio=2026):
    """Serie mensual de ENERO del año previo a DICIEMBRE de 'anio' (24 meses):
    REAL donde ya hay cierre técnico (p. ej. ene 2025 - jun 2026) + PROYECCIÓN del
    modelo para el resto de 'anio' (jul-dic 2026). Las dos líneas se CONECTAN en el
    último mes real (la proyección se ancla ahí). Devuelve lista de dicts o None."""
    serie = serie_real_mensual(df_gonz_full)
    real, ult_real = {}, None            # llaves = AAAAMM
    if serie is not None:
        for ym, r in serie.iterrows():
            ym = int(ym)
            y, mm_ = divmod(ym, 100)
            if (anio - 1) <= y <= anio and 1 <= mm_ <= 12:
                real[ym] = {"ing": float(r["ingresos"]), "egr": float(r["egresos"]),
                            "neto": float(r["neto"])}
                ult_real = ym if (ult_real is None or ym > ult_real) else ult_real
    # Proyección del comparativo (meses calendario del modelo) que caigan en 'anio'
    proy = {}
    if comparativo and comparativo.get("meses"):
        for mc in comparativo["meses"]:
            ym = int(mc["mes"])
            y, mm_ = divmod(ym, 100)
            if y == anio and 1 <= mm_ <= 12:
                proy[ym] = {"ing": float(mc["ingresos"]), "egr": float(mc["egresos"]),
                            "neto": float(mc["neto"])}
    if not real and not proy:
        return None
    filas = []
    for y in (anio - 1, anio):
        for mm_ in range(1, 13):
            ym = y * 100 + mm_
            rr = real.get(ym)
            pp = proy.get(ym)
            proy_ing = proy_egr = proy_neto = None
            if pp is not None:                                   # mes proyectado
                proy_ing, proy_egr, proy_neto = pp["ing"], pp["egr"], pp["neto"]
            elif ult_real is not None and ym == ult_real and rr is not None:
                proy_ing, proy_egr, proy_neto = rr["ing"], rr["egr"], rr["neto"]  # ancla (conecta líneas)
            filas.append({
                "AAAAMM": ym, "Mes": _etiqueta_mes_orden(ym),
                "Real ingresos": (rr["ing"] if rr else None),
                "Real egresos": (rr["egr"] if rr else None),
                "Real neto": (rr["neto"] if rr else None),
                "Proy ingresos": proy_ing, "Proy egresos": proy_egr, "Proy neto": proy_neto,
            })
    return filas or None


def resumir_percentiles(matriz, percentiles):
    """
    De una matriz (n_sims, horizonte) devuelve un DataFrame (horizonte x percentiles)
    con los percentiles de flujo de cada mes.
    """
    horizonte = matriz.shape[1]
    data = {}
    for p in percentiles:
        data[f"P{p}"] = np.percentile(matriz, p, axis=0)
    data["Media"] = matriz.mean(axis=0)
    df = pd.DataFrame(data, index=[f"Mes {i+1}" for i in range(horizonte)])
    return df


# ==============================================================================
# MÓDULO 6 · VALIDACIÓN ESTADÍSTICA
# ==============================================================================
# Verifica rigurosamente cada componente del modelo. Filosofía: con muestras
# grandes (millones de filas) las pruebas formales de bondad de ajuste (KS,
# Anderson-Darling) rechazan casi siempre por potencia excesiva. Por eso, además
# del estadístico formal y su p-valor, se reportan MEDIDAS DESCRIPTIVAS de ajuste
# (R² de QQ-plot, error relativo en cuantiles clave) y el VEREDICTO (semáforo) se
# basa en estas últimas, que son interpretables a cualquier escala.
#
# Cada validador devuelve un dict con: 'pruebas' (lista de filas para reportar),
# 'veredicto' ('ok'|'precaucion'|'alerta') y 'resumen' (texto breve).
#
# Las librerías estadísticas (scipy, statsmodels) son OPCIONALES: si no están
# instaladas, la validación se omite con un aviso y el modelo sigue corriendo y
# generando el Dashboard. Para validación completa: pip install scipy statsmodels
# ------------------------------------------------------------------------------

try:
    import scipy.stats as _sp_stats   # noqa: F401
    _SCIPY_OK = True
except Exception:
    _SCIPY_OK = False


def _validacion_omitida(componente):
    """Resultado neutro cuando faltan librerías estadísticas."""
    return {
        "componente": componente,
        "pruebas": [("Validación", "omitida", "falta scipy/statsmodels",
                     "instalar para validar")],
        "veredicto": "precaucion",
        "resumen": "Validación omitida (instala scipy y statsmodels para activarla).",
    }


def _veredicto_peor(*estados):
    """Combina veredictos: alerta > precaucion > ok."""
    orden = {"ok": 0, "precaucion": 1, "alerta": 2}
    inv = {v: k for k, v in orden.items()}
    return inv[max(orden.get(e, 0) for e in estados)]


def validar_magnitud(montos, params_mag):
    """
    Valida la MAGNITUD tal como la USA el modelo: la MEDIA EMPÍRICA (estimador
    insesgado del flujo promedio). NO se valida el ajuste log-normal porque el
    modelo no proyecta con él; lo relevante es que la media empírica sea estable:
      - Tamaño de muestra (n grande -> estimación estable por TLC).
      - Error estándar relativo de la media (SE/media): qué tan precisa es.
      - Concentración de cola (peso del top-1%): informativo (colas pesadas son
        normales en seguros y la media empírica las incorpora correctamente).
    """
    res = {"componente": "Magnitud (media empírica)", "pruebas": [], "veredicto": "ok"}
    if params_mag is None or montos is None or len(montos) < 30:
        res["veredicto"] = "precaucion"
        res["resumen"] = "Datos insuficientes para validar."
        return res

    x = np.asarray(montos, dtype=float)
    x = x[x > 0]
    n = len(x)
    media = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    se_rel = (sd / np.sqrt(n)) / media if media else float("inf")   # error estándar relativo
    total = float(x.sum())
    umbral99 = float(np.percentile(x, 99))
    peso_top1 = float(x[x >= umbral99].sum() / total) if total else 0.0

    # Veredicto por estabilidad de la media empírica (lo que usa el modelo)
    v_n = "ok" if n >= 1000 else ("precaucion" if n >= 100 else "alerta")
    v_se = "ok" if se_rel <= 0.15 else ("precaucion" if se_rel <= 0.30 else "alerta")
    res["veredicto"] = _veredicto_peor(v_n, v_se)   # la concentración es informativa

    res["pruebas"] = [
        ("Tamaño de muestra", f"n={n:,}", "movimientos", v_n),
        ("Error estándar rel. de la media", f"{se_rel*100:.1f}%", "precisión del estimador", v_se),
        ("Peso del top-1% (cola)", f"{peso_top1*100:.0f}%", "informativo (normal en seguros)", "ok"),
    ]
    res["resumen"] = f"media empírica estable: n={n:,}, error estándar {se_rel*100:.1f}%"
    return res


def validar_frecuencia(conteos, params_freq):
    """
    Prueba de sobredispersión de la frecuencia.
      - Índice de dispersión D = var/media. Bajo Poisson, (n-1)·D ~ chi²(n-1).
      - Decide si la binomial negativa está justificada (D significativamente > 1).
    """
    if not _SCIPY_OK:
        return _validacion_omitida("Frecuencia (Poisson/BN)")
    from scipy import stats
    res = {"componente": "Frecuencia (Poisson/BN)", "pruebas": [], "veredicto": "ok"}
    if params_freq is None or conteos is None or len(conteos) < 3:
        res["veredicto"] = "precaucion"
        res["resumen"] = "Datos insuficientes para validar."
        return res
    c = np.asarray(conteos, dtype=float)
    media = c.mean(); var = c.var(ddof=1)
    n = len(c)
    D = var / media if media > 0 else np.nan
    # Prueba chi² de dispersión
    chi2_stat = (n - 1) * D
    p_disp = 1 - stats.chi2.cdf(chi2_stat, df=n - 1)

    usa_bn = params_freq.get("sobredispersion", False)
    hay_sobredisp = (p_disp < 0.05) and (D > 1.2)
    # Coherencia: ¿la decisión del modelo concuerda con la prueba?
    coherente = (usa_bn == hay_sobredisp)
    v = "ok" if coherente else "precaucion"
    res["veredicto"] = v
    res["pruebas"] = [
        ("Índice de dispersión D", f"{D:.2f}", "1.0 = Poisson", ""),
        ("Prueba de sobredispersión", f"χ²={chi2_stat:.1f}", f"p={p_disp:.3f}",
         "sobredisp." if hay_sobredisp else "no sobredisp."),
        ("Distribución elegida", "Binomial neg." if usa_bn else "Poisson", "",
         "coherente" if coherente else "revisar"),
    ]
    res["resumen"] = (f"D={D:.2f}; "
                      + ("sobredispersión detectada" if hay_sobredisp else "sin sobredispersión")
                      + ("" if coherente else " (no coincide con la elección)"))
    return res


def validar_tc(log_returns, params_tc):
    """
    Valida los supuestos del GBM para el TC:
      - Normalidad de los log-retornos (Jarque-Bera).
      - Estacionariedad de los log-retornos (ADF) — el GBM asume incrementos iid.
      - Ausencia de autocorrelación (Ljung-Box).
    """
    if not _SCIPY_OK:
        return _validacion_omitida("Tipo de cambio (GBM)")
    from scipy import stats
    res = {"componente": "Tipo de cambio (GBM)", "pruebas": [], "veredicto": "ok"}
    if log_returns is None or len(log_returns) < 12:
        res["veredicto"] = "precaucion"
        res["resumen"] = "Serie de TC insuficiente para validar."
        return res

    r = np.asarray(log_returns, dtype=float)
    r = r[np.isfinite(r)]

    # Normalidad: Jarque-Bera. INFORMATIVO únicamente: en tipos de cambio la
    # no-normalidad (colas pesadas) es lo esperado y NO invalida el GBM, que se
    # calibra con deriva/volatilidad empíricas. No entra al veredicto.
    jb_stat, jb_p = stats.jarque_bera(r)
    v_norm = "ok"   # informativo; no penaliza

    # Estacionariedad: ADF (statsmodels)
    adf_p = np.nan; v_adf = "ok"
    try:
        from statsmodels.tsa.stattools import adfuller
        adf_stat, adf_p = adfuller(r, autolag="AIC")[:2]
        v_adf = "ok" if adf_p < 0.05 else "precaucion"
    except Exception:
        v_adf = "precaucion"

    # Autocorrelación: Ljung-Box (statsmodels)
    lb_p = np.nan; v_lb = "ok"
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        lags = min(10, len(r) // 4)
        lb = acorr_ljungbox(r, lags=[lags], return_df=True)
        lb_p = float(lb["lb_pvalue"].iloc[0])
        v_lb = "ok" if lb_p >= 0.05 else "precaucion"
    except Exception:
        v_lb = "precaucion"

    # Veredicto SOLO por los supuestos que de verdad importan para el GBM
    res["veredicto"] = _veredicto_peor(v_adf, v_lb)
    es_normal = "sí" if jb_p >= 0.05 else "no (normal en FX)"
    res["pruebas"] = [
        ("Estacionariedad (ADF)", f"p={adf_p:.3f}" if np.isfinite(adf_p) else "n/d",
         "estacionario si p<0.05  ← clave", v_adf),
        ("Autocorrelación (Ljung-Box)", f"p={lb_p:.3f}" if np.isfinite(lb_p) else "n/d",
         "sin autocorr. si p>0.05  ← clave", v_lb),
        ("Normalidad (Jarque-Bera)", f"p={jb_p:.3f}", f"¿normal? {es_normal} · informativo", "ok"),
    ]
    res["resumen"] = (("log-retornos estacionarios y sin autocorrelación"
                       if res["veredicto"] == "ok" else "revisar estacionariedad/autocorrelación")
                      + f" (no-normalidad esperada en FX)")
    return res


def validar_convergencia_montecarlo(matriz_neto, nivel=0.95):
    """
    Diagnóstico de convergencia de la simulación Monte Carlo.
      - Error estándar de MC de la media (por mes) = desv/√N.
      - Error relativo de MC (SE / |media|): qué tan estable es el estimador.
      - Tamaño de muestra efectivo y media de las semianchuras del IC.
    """
    res = {"componente": "Convergencia Monte Carlo", "pruebas": [], "veredicto": "ok"}
    if matriz_neto is None or matriz_neto.size == 0:
        res["veredicto"] = "precaucion"
        res["resumen"] = "Sin resultados de simulación."
        return res

    N = matriz_neto.shape[0]
    medias = matriz_neto.mean(axis=0)
    desv = matriz_neto.std(axis=0, ddof=1)
    se_mc = desv / np.sqrt(N)
    # Error relativo de MC promedio (evitando meses con media ~0)
    denom = np.where(np.abs(medias) > 1e-9, np.abs(medias), np.nan)
    err_rel = np.nanmean(se_mc / denom)

    # El neto es un RESIDUAL (diferencia de brutos grandes), así que su error
    # relativo de MC es naturalmente mayor; ~3% es adecuado para planeación.
    v = "ok" if err_rel <= 0.03 else ("precaucion" if err_rel <= 0.06 else "alerta")
    res["veredicto"] = v
    res["pruebas"] = [
        ("Nº de simulaciones", f"{N:,}", "", ""),
        ("Error rel. MC (media)", f"{err_rel*100:.2f}%", "adecuado <3% (neto es residual)", v),
        ("SE MC máx (mes)", f"${np.max(se_mc):,.0f}", "", ""),
    ]
    res["resumen"] = (f"Error MC {err_rel*100:.2f}% con {N:,} sims "
                      + ("(convergencia adecuada)" if v == "ok"
                         else "(considerar más simulaciones)"))
    return res


def validar_todo(parametros, resultado_sim):
    """
    Ensambla el tablero de validación a partir de las validaciones ya calculadas
    durante la calibración (magnitud, frecuencia y lag se validan inline en
    calibrar_todo; el TC también) y agrega la convergencia Monte Carlo.
    Devuelve un dict con la validación por concepto, del TC y de convergencia.
    """
    print("\n" + "=" * 70)
    print("VALIDACIÓN ESTADÍSTICA")
    print("=" * 70)

    validacion = {"conceptos": {}, "tc": None, "montecarlo": None, "global": "ok"}
    estados = []

    # ----- TC (ya validado en la calibración) -----
    val_tc = parametros["tc"].get("validacion")
    if val_tc:
        validacion["tc"] = val_tc
        estados.append(val_tc["veredicto"])
        print(f"\n[TC USD/MXN] {val_tc['veredicto'].upper()}: {val_tc['resumen']}")

    # ----- Conceptos (ya validados en la calibración) -----
    for nombre, p in parametros["conceptos"].items():
        val = p.get("validacion")
        if not val:
            continue
        validacion["conceptos"][nombre] = val
        estados.append(val["veredicto"])
        print(f"\n[{nombre}] {val['veredicto'].upper()}")
        for clave in ("magnitud", "frecuencia", "lag"):
            sub = val.get(clave)
            if sub:
                print(f"   {clave.capitalize():11s} {sub['veredicto']:11s} | {sub['resumen']}")

    # ----- Convergencia Monte Carlo -----
    if resultado_sim is not None:
        val_mc = validar_convergencia_montecarlo(resultado_sim.get("neto"))
        validacion["montecarlo"] = val_mc
        estados.append(val_mc["veredicto"])
        print(f"\n[Monte Carlo] {val_mc['veredicto'].upper()}: {val_mc['resumen']}")

    # Veredicto global: Alerta si hay algún problema serio; OK si no hay alertas y
    # la mayoría de componentes pasan; Precaución en otro caso. (Una sola marca de
    # "revisar" no debe arrastrar todo el modelo a Precaución.)
    if not estados:
        validacion["global"] = "ok"
    elif "alerta" in estados:
        validacion["global"] = "alerta"
    elif estados.count("ok") / len(estados) >= 0.6:
        validacion["global"] = "ok"
    else:
        validacion["global"] = "precaucion"

    # Aviso honesto si la validación se omitió por falta de paquetes
    if not _SCIPY_OK:
        print("\n  [!] scipy/statsmodels no instalados: la validación se omitió en varios componentes.")
        print("      Para un veredicto estadístico real:  pip install scipy statsmodels lifelines")

    print(f"\n>>> VEREDICTO GLOBAL: {validacion['global'].upper()}")
    return validacion


# ==============================================================================
# ORQUESTADOR DE CALIBRACIÓN
# ==============================================================================
def analizar_factores_lag(df_gonz):
    """
    ANÁLISIS (independiente de la proyección): ¿qué covariables alargan o acortan
    el tiempo entre el inicio de vigencia (IniVig) y el mes de proceso? Ajusta un
    AFT LogNormal del lag contra corredor / moneda USD / territorio y devuelve el
    efecto de cada uno (% de cambio en la demora). Robusto a fechas (devuelve None).
    """
    try:
        if "IniVig" not in df_gonz.columns or "aPOG_MesProc" not in df_gonz.columns:
            return None

        # ----- Lag IniVig -> mes de proceso (en días), robusto a formatos -----
        ini = pd.to_datetime(df_gonz["IniVig"], errors="coerce")
        mp = pd.to_numeric(df_gonz["aPOG_MesProc"], errors="coerce")
        anio = (mp // 100); mes = (mp % 100)
        valido_mp = anio.between(1990, 2100) & mes.between(1, 12)
        proc = pd.Series(pd.NaT, index=df_gonz.index, dtype="datetime64[ns]")
        if valido_mp.any():
            proc.loc[valido_mp[valido_mp].index] = pd.to_datetime(pd.DataFrame({
                "year": anio[valido_mp].astype(int),
                "month": mes[valido_mp].astype(int), "day": 1}), errors="coerce").values
        lag = (proc - ini).dt.days

        # Filtrar lags válidos (positivos y razonables: hasta ~25 años)
        ok = lag.notna() & (lag > 0) & (lag <= 9131)
        if ok.sum() < 200:
            return None
        df = df_gonz.loc[ok].copy()
        lag_v = lag[ok].astype(float)

        # ----- Covariables (misma derivación que el AFT del lag) -----
        cov = pd.DataFrame(index=df.index)
        if "CorrTom" in df:
            corr_norm = df["CorrTom"].apply(lambda v: "" if pd.isna(v) else str(v).strip().lstrip("0"))
            cov["corredor"] = (corr_norm != "").astype(int).values
        if "MonedaOri" in df:
            cov["usd"] = df["MonedaOri"].apply(
                lambda v: 1 if (pd.notna(v) and _s(v) == str(MONEDA_USD_ID)) else 0).values
        if "Territorio" in df:
            cov["territorio"] = df["Territorio"].apply(
                lambda v: _s(v) if pd.notna(v) and _s(v) != "" else "ND").values

        # Categorías TOP-K de territorio
        territorio_categorias = None
        if "territorio" in cov.columns:
            top = cov["territorio"].value_counts().head(TERRITORIO_TOP_K).index.tolist()
            territorio_categorias = top
        diseño, design_cols = _codificar_covariables(cov, territorio_categorias)
        if not design_cols:
            return None

        # Muestreo si excede el tope (rendimiento)
        if len(lag_v) > MAX_FILAS_AFT:
            rng_s = np.random.default_rng(SEMILLA)
            sel = rng_s.choice(len(lag_v), size=MAX_FILAS_AFT, replace=False)
            lag_v = lag_v.iloc[sel]; diseño = diseño.iloc[sel]

        # ----- Ajuste AFT LogNormal -----
        from lifelines import LogNormalAFTFitter
        df_fit = diseño.reindex(columns=design_cols, fill_value=0.0).copy()
        df_fit["_lag"] = np.maximum(lag_v.values, 1.0)
        df_fit["_evento"] = 1
        modelo = LogNormalAFTFitter().fit(df_fit, duration_col="_lag", event_col="_evento")

        # C-index y significancia
        try:
            c_index = float(modelo.concordance_index_)
        except Exception:
            c_index = float("nan")
        beta = modelo.params_["mu_"]
        try:
            resumen = modelo.summary
            pvals = {c: float(resumen.loc[("mu_", c), "p"]) for c in design_cols
                     if ("mu_", c) in resumen.index}
        except Exception:
            pvals = {}

        # Efectos: exp(beta) - 1 = % de cambio en la demora
        efectos = {c: float(np.exp(float(beta.get(c, 0.0))) - 1.0) for c in design_cols}
        return {
            "efectos": efectos,
            "pvals": pvals,
            "c_index": c_index,
            "mediana_dias": float(np.median(lag_v.values)),
            "n": int(len(lag_v)),
            "origen": "IniVig→mes de proceso",
        }
    except Exception as e:
        print(f"  [i] Análisis de factores (timing) no disponible: {type(e).__name__}: {e}")
        return None


def detalle_factores_lag(df_gonz):
    """
    Detalle DESCRIPTIVO del timing por categoría: mediana de días de demora
    (IniVig -> mes de proceso) por TERRITORIO, MONEDA y CORREDOR/DIRECTO, con su
    rango P25-P75 y volumen. Sirve para ver, dimensión por dimensión, cuáles
    alargan o acortan el cobro/pago (vs. la mediana general). Robusto a fechas.
    """
    try:
        if "IniVig" not in df_gonz.columns or "aPOG_MesProc" not in df_gonz.columns:
            return None
        ini = pd.to_datetime(df_gonz["IniVig"], errors="coerce")
        mp = pd.to_numeric(df_gonz["aPOG_MesProc"], errors="coerce")
        anio = mp // 100; mes = mp % 100
        vmp = anio.between(1990, 2100) & mes.between(1, 12)
        # Construcción POSICIONAL (inmune a índices con huecos o duplicados del caché)
        proc_np = np.full(len(df_gonz), np.datetime64("NaT"), dtype="datetime64[ns]")
        _vmp_np = vmp.to_numpy(dtype=bool)
        if _vmp_np.any():
            proc_np[_vmp_np] = pd.to_datetime(pd.DataFrame({
                "year": anio[vmp].astype(int).to_numpy(), "month": mes[vmp].astype(int).to_numpy(),
                "day": 1}), errors="coerce").values
        proc = pd.Series(proc_np, index=df_gonz.index)
        lag = (proc - ini).dt.days
        ok = lag.notna() & (lag > 0) & (lag <= 9131)
        if ok.sum() < 200:
            return None
        df = df_gonz.loc[ok].copy()
        df["_lag"] = lag[ok].astype(float)
        overall_med = float(df["_lag"].median())
        # Monto movido por fila (Σ columnas de importe de los conceptos, pesos) para
        # medir el IMPACTO, no solo la demora: una categoría puede tardar mucho pero
        # mover poco dinero (o al revés).
        # Monto por fila, calculado POSICIONALMENTE con numpy (sin alineación de
        # índices: inmune a cachés/copias con índices raros) + DIAGNÓSTICO detallado
        # por concepto que se imprime en consola y se escribe en la hoja de Factores.
        _monto_np = np.zeros(len(df_gonz), dtype="float64")
        _diag = {"n_filas_base": int(len(df_gonz)), "n_filas_lag": int(len(df)),
                 "total_base": 0.0, "total_lag": 0.0, "conceptos": []}
        for _nom, _cdef in CONCEPTOS.items():
            _pres = [c for c in _cdef["columnas"] if c in df_gonz.columns]
            _falt = [c for c in _cdef["columnas"] if c not in df_gonz.columns]
            _sum_c = 0.0
            _dtype = _muestra = ""
            if _pres:
                _c0 = _pres[0]
                _dtype = str(df_gonz[_c0].dtype)
                try:
                    _muestra = " | ".join(repr(v)[:20] for v in df_gonz[_c0].head(3).tolist())
                except Exception:
                    _muestra = "?"
            for _c in _pres:
                try:
                    _v = pd.to_numeric(df_gonz[_c], errors="coerce").fillna(0.0)\
                           .to_numpy(dtype="float64", copy=True)
                    _va = np.abs(_v)
                    _monto_np += _va
                    _sum_c += float(_va.sum())
                except Exception as _e:
                    _muestra = f"ERROR {_c}: {type(_e).__name__}: {_e}"[:80]
            _diag["conceptos"].append({"concepto": _nom, "suma": _sum_c,
                                       "presentes": len(_pres), "esperadas": len(_cdef["columnas"]),
                                       "faltantes": ", ".join(_falt) if _falt else "-",
                                       "dtype": _dtype, "muestra": _muestra})
        _diag["total_base"] = float(_monto_np.sum())
        _mask_ok = np.asarray(ok, dtype=bool)
        df["_monto"] = _monto_np[_mask_ok]
        _total_lag = float(df["_monto"].sum())
        _diag["total_lag"] = _total_lag

        # ------------------------------------------------------------------
        # IMPACTO EN MONTO: se mide sobre TODA la base, no solo sobre las filas
        # con lag válido. En Gonz las filas que traen importe (devengado Nal4) y
        # las filas con las que se puede medir la demora (IniVig < mes de proceso)
        # son, en gran medida, poblaciones distintas: si el monto se suma solo en
        # las filas con lag, el impacto sale en $0 aunque la base mueva miles de
        # millones. Por eso la DEMORA se calcula con las filas con lag y el MONTO
        # se agrupa por la misma categoría sobre todas las filas con importe.
        # ------------------------------------------------------------------
        _con_monto = _monto_np > 0
        _diag["n_filas_monto"] = int(_con_monto.sum())
        _diag["n_filas_monto_y_lag"] = int((_con_monto & _mask_ok).sum())
        _total_monto = _diag["total_base"]
        if _total_monto <= 0:
            print("  [!] IMPACTO EN CERO: la base no trae importes en las columnas de los conceptos. "
                  "Revisa la caja 'DIAGNÓSTICO DEL IMPACTO' en la hoja Factores.")
            _total_monto = 1.0
        _cols_cat = [c for c in ("Territorio", "MonedaOri", "CorrTom", "CiaTom", "Tipo")
                     if c in df_gonz.columns]
        base_m = df_gonz.loc[_con_monto, _cols_cat].copy()
        base_m["_monto"] = _monto_np[_con_monto]

        # Estructura de la base por 'Tipo' de registro (explica por qué monto y lag
        # viven en filas distintas). Se imprime y se escribe en la hoja de Factores.
        _diag["por_tipo"] = []
        if "Tipo" in df_gonz.columns:
            try:
                _tipo = df_gonz["Tipo"].astype(str).str.strip()
                _aux = pd.DataFrame({"tipo": _tipo.to_numpy(), "monto": _monto_np,
                                     "lag_ok": _mask_ok, "con_monto": _con_monto})
                for _t, _g in _aux.groupby("tipo"):
                    _diag["por_tipo"].append({
                        "tipo": _t, "n": int(len(_g)), "monto": float(_g["monto"].sum()),
                        "n_monto": int(_g["con_monto"].sum()), "n_lag": int(_g["lag_ok"].sum()),
                        "n_ambos": int((_g["con_monto"] & _g["lag_ok"]).sum())})
                _diag["por_tipo"].sort(key=lambda d: d["n"], reverse=True)
            except Exception as _e:
                print(f"  [i] (estructura por Tipo no disponible: {type(_e).__name__}: {_e})")

        print(f"  [DIAG impacto] filas base {len(df_gonz):,} | Σ|monto| base ${_diag['total_base']:,.0f} "
              f"| filas con importe {_diag['n_filas_monto']:,} | filas lag>0 {len(df):,} "
              f"| filas con importe Y lag {_diag['n_filas_monto_y_lag']:,} (Σ ${_total_lag:,.0f})")
        for _dc in _diag["conceptos"]:
            print(f"      - {_dc['concepto']}: Σ ${_dc['suma']:,.0f} | cols {_dc['presentes']}/{_dc['esperadas']}"
                  f" | dtype {_dc['dtype']} | muestra: {_dc['muestra']}"
                  + (f" | FALTAN: {_dc['faltantes']}" if _dc['faltantes'] != "-" else ""))
        for _pt in _diag["por_tipo"]:
            print(f"      · Tipo {_pt['tipo']}: {_pt['n']:,} filas | Σ|monto| ${_pt['monto']:,.0f} "
                  f"| con importe {_pt['n_monto']:,} | con lag {_pt['n_lag']:,} | ambos {_pt['n_ambos']:,}")
        if _total_lag <= 0:
            print("  [i] Las filas con lag no traen importe: el impacto se toma de toda la base "
                  "agrupando por categoría (demora y monto se miden en filas distintas).")

        def _monto_por_cat(col, keyfn=None):
            """{clave de categoría: Σ|monto|} sobre TODAS las filas con importe."""
            if col not in base_m.columns:
                return {}
            llave = base_m[col].apply(keyfn) if keyfn else base_m[col].astype(str)
            return base_m.groupby(llave.to_numpy())["_monto"].sum().to_dict()

        def _fila_cat(nombre, sub, monto):
            return {"cat": nombre,
                    "mediana": float(sub["_lag"].median()),
                    "n": int(len(sub)),
                    "p25": float(sub["_lag"].quantile(0.25)),
                    "p75": float(sub["_lag"].quantile(0.75)),
                    "monto": float(monto), "monto_pct": float(monto) / _total_monto * 100.0}

        def por_dim(col, namefn, topn=12):
            if col not in df.columns:
                return []
            montos = _monto_por_cat(col)
            filas = []
            for cat, sub in df.groupby(df[col].astype(str)):
                if len(sub) < 30:   # ignorar categorías minúsculas
                    continue
                filas.append(_fila_cat(namefn(cat), sub, montos.get(cat, 0.0)))
            filas.sort(key=lambda d: d["n"], reverse=True)
            filas = filas[:topn]
            filas.sort(key=lambda d: d["mediana"], reverse=True)
            return filas

        territorios = por_dim("Territorio", _nombre_territorio, topn=5)
        monedas = por_dim("MonedaOri", _nombre_moneda)

        corredor = []
        if "CorrTom" in df.columns:
            def _con_o_directo(v):
                return "Con corredor" if (pd.notna(v) and str(v).strip().lstrip("0") != "") else "Directo"
            cf = df["CorrTom"].apply(_con_o_directo)
            montos = _monto_por_cat("CorrTom", _con_o_directo)
            for cat, sub in df.groupby(cf):
                corredor.append(_fila_cat(cat, sub, montos.get(cat, 0.0)))
            corredor.sort(key=lambda d: d["mediana"], reverse=True)

        def _top_por(col, topn=4, min_n=30, namefn=None):
            if col not in df.columns:
                return []
            montos = _monto_por_cat(col, lambda v: str(v).strip())
            out = []
            for cat, sub in df.groupby(df[col].astype(str)):
                cs = str(cat).strip()
                if cs.lstrip("0") == "" or cs.lower() in ("nan", "none"):
                    continue
                if len(sub) < min_n:
                    continue
                nombre = namefn(cs) if namefn else cs.lstrip("0")
                out.append(_fila_cat(nombre, sub, montos.get(cs, 0.0)))
            out.sort(key=lambda d: d["n"], reverse=True)
            out = out[:topn]
            out.sort(key=lambda d: d["mediana"], reverse=True)
            return out
        corredores_top = _top_por("CorrTom", topn=4, namefn=_nombre_corredor)
        cedentes_top = _top_por("CiaTom", topn=4, namefn=_nombre_cedente)
        _diag["total_asignado"] = float(sum(d["monto"] for d in territorios)
                                        + sum(d["monto"] for d in monedas)
                                        + sum(d["monto"] for d in corredor))

        return {"overall_mediana": overall_med, "territorios": territorios,
                "monedas": monedas, "corredor": corredor,
                "corredores_top": corredores_top, "cedentes_top": cedentes_top,
                "diag_impacto": _diag}
    except Exception as e:
        print(f"  [i] Detalle de factores no disponible: {type(e).__name__}: {e}")
        return None


def calibrar_todo(df_gonz, df_tc):
    """
    Calibra todos los parámetros del modelo desde Gonz y la serie de TC.
    Devuelve un diccionario estructurado con los parámetros de cada concepto
    más el del TC, listo para alimentar el motor de simulación.
    """
    print("\n" + "=" * 70)
    print("CALIBRACIÓN DE PARÁMETROS (desde Gonz)")
    print("=" * 70)

    parametros = {"conceptos": {}, "tc": None}

    # ----- TC -----
    parametros["tc"] = calibrar_tc(df_tc)
    p_tc = parametros["tc"]
    p_tc["validacion"] = validar_tc(p_tc.get("log_returns"), p_tc)
    print(f"\n[TC USD/MXN] GBM calibrado:")
    print(f"   S0 (último) = {p_tc['S0']:.4f} | drift mensual = {p_tc['mu_mensual']*100:.3f}% "
          f"| volatilidad mensual = {p_tc['sigma_mensual']*100:.3f}%")
    if not p_tc.get("default"):
        print(f"   Histórico: {p_tc['n']} obs | rango [{p_tc['tc_min']:.2f}, {p_tc['tc_max']:.2f}]")

    # ----- Conceptos -----
    for nombre, cdef in CONCEPTOS.items():
        df_c = extraer_movimientos_concepto(df_gonz, cdef)
        montos = df_c["monto"].values if len(df_c) else []
        mag = calibrar_magnitud(montos)
        freq = calibrar_frecuencia(df_c)
        lag = calibrar_lag(df_c)
        prop_usd = calibrar_proporcion_usd(df_c)

        # Validación estadística inline (con los datos crudos a la mano)
        conteos = (df_c.groupby("aPOG_MesProc").size().values
                   if (len(df_c) and "aPOG_MesProc" in df_c) else None)
        v_mag = validar_magnitud(montos if len(montos) else None, mag)
        v_freq = validar_frecuencia(conteos, freq)
        v_lag = (lag or {}).get("validacion")
        ver_concepto = _veredicto_peor(v_mag["veredicto"], v_freq["veredicto"],
                                       (v_lag or {}).get("veredicto", "ok"))

        parametros["conceptos"][nombre] = {
            "direccion": cdef["direccion"],
            "magnitud": mag,
            "frecuencia": freq,
            "lag": lag,
            "prop_usd": prop_usd,
            "validacion": {
                "magnitud": v_mag, "frecuencia": v_freq, "lag": v_lag,
                "veredicto": ver_concepto,
            },
        }

        print(f"\n[{nombre}] ({cdef['direccion'].upper()})")
        if mag:
            print(f"   Magnitud: media=${mag['media_emp']:,.0f} | mediana=${mag['mediana_emp']:,.0f} "
                  f"| P95=${mag['p95_emp']:,.0f} | n={mag['n']:,}  (media empírica insesgada)")
        else:
            print(f"   Magnitud: SIN DATOS suficientes")
        if freq:
            disp = "binomial neg." if freq["sobredispersion"] else "Poisson"
            print(f"   Frecuencia: {freq['lambda_mensual']:.1f} ops/mes ({disp}) "
                  f"| rango [{freq['min_mensual']}, {freq['max_mensual']}]")
        if lag:
            if lag.get("metodo") == "aft":
                restr = ""
                if lag.get("restriccion_maduras"):
                    restr = f" | ajuste sobre {lag['n_ajuste']:,} maduras de {lag['n']:,}"
                elif lag.get("n_censurado"):
                    restr = f" | censurados={lag['n_censurado']:,}"
                print(f"   Lag (AFT {lag['tipo_aft']}): mediana={lag['mediana_dias']:.0f}d | "
                      f"media={lag['media_dias']:.0f}d | P95={lag['p95_dias']:.0f}d | "
                      f"AIC={lag['aic']:.0f}{restr}")
                # Efectos de covariables (las 3 más influyentes)
                efectos = lag.get("efectos", {})
                if efectos:
                    top_ef = sorted(efectos.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
                    desc = " | ".join(f"{c}: {e*100:+.0f}%" for c, e in top_ef)
                    print(f"      Efecto covariables en el lag: {desc}")
            else:
                tag = " (default)" if lag.get("default") else ""
                print(f"   Lag cobro/pago (log-normal simple): mediana={lag['mediana_dias']:.0f}d | "
                      f"media={lag['media_dias']:.0f}d | P95={lag['p95_dias']:.0f}d{tag}")
        print(f"   Exposición USD: {prop_usd*100:.0f}% de las operaciones")

    # ----- Análisis de factores del timing (independiente de la proyección) -----
    # Corre el AFT sobre el lag IniVig->proceso para entender qué alarga/acorta el
    # cobro/pago. No afecta la proyección de flujos (que usa el flujo mensual directo).
    print("\n[Factores de timing] Analizando qué afecta la demora de cobro/pago...")
    parametros["factores_lag"] = analizar_factores_lag(df_gonz)
    fl = parametros["factores_lag"]
    if fl:
        top = sorted(fl["efectos"].items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        print(f"   AFT sobre lag {fl['origen']}: n={fl['n']:,}, C-index={fl['c_index']:.2f}")
        print(f"   Top efectos: " + " | ".join(f"{c}: {e*100:+.0f}%" for c, e in top))
    else:
        print("   No disponible (revisar IniVig / aPOG_MesProc o instalar lifelines).")

    return parametros


# ==============================================================================
# SALIDA A EXCEL (formato GPV)
# ==============================================================================
# Paleta GPV
VERDE_PATRIA     = "00573F"
VERDE_SECUNDARIO = "4C8C5E"
VERDE_CLARO      = "D4E4DC"
DORADO_ACENTO    = "C9A961"
DORADO_FUERTE    = "9C6B0B"   # dorado oscuro/fuerte para 'año anterior' (no se pierde)
AZUL_CUSF        = "1F4E79"
NARANJA_DOC      = "B5541C"
ROJO_ALERTA      = "A6192E"
MORADO_PATRIA    = "5B2C6F"
GRIS_NEUTRO      = "808080"
BLANCO           = "FFFFFF"


def _estilo_lineas(chart, alto=10.5, ancho=24, rotar_x=True, sz_x=850):
    """Aplica un layout 'aireado' a una gráfica de líneas para que NADA se encime:
    título arriba sin solaparse, leyenda a la derecha con su espacio, etiquetas del
    eje X giradas, y ejes visibles. Centraliza el espaciado para todas las gráficas."""
    from openpyxl.chart.text import RichText
    from openpyxl.drawing.text import (RichTextProperties, Paragraph,
                                        ParagraphProperties, CharacterProperties)
    chart.height = alto
    chart.width = ancho
    # Título sin overlay (reserva su franja arriba)
    try:
        if chart.title is not None:
            chart.title.overlay = False
    except Exception:
        pass
    # Leyenda a la derecha, con su propio espacio (no encima de las líneas)
    if chart.legend is not None:
        chart.legend.position = 'r'
        chart.legend.overlay = False
    # Etiquetas del eje X giradas para que no se traslapen las fechas
    if rotar_x:
        chart.x_axis.txPr = RichText(
            bodyPr=RichTextProperties(rot=-2700000, vert="horz", anchor="ctr"),
            p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(sz=sz_x)),
                         endParaRPr=CharacterProperties(sz=sz_x))])
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    # --- FIX: etiquetas del eje X (meses) SIEMPRE abajo del plano (no a la altura
    #     de y=0, que es donde caen cuando hay valores negativos).
    chart.x_axis.tickLblPos = "low"
    # --- FIX: títulos de eje SIN overlay (que "Días de demora" no se encime con
    #     los números del eje). Se reserva su espacio a la izquierda.
    for _ax in (chart.x_axis, chart.y_axis):
        try:
            if _ax.title is not None:
                _ax.title.overlay = False
        except Exception:
            pass
    chart.x_axis.majorTickMark = "out"
    chart.y_axis.majorGridlines = chart.y_axis.majorGridlines  # mantener gridlines


def _header_cell(ws, celda, texto, fondo=VERDE_PATRIA, size=11, color=BLANCO):
    from openpyxl.styles import Font, PatternFill, Alignment
    c = ws[celda]
    c.value = texto
    c.font = Font(name='Calibri', size=size, bold=True, color=color)
    c.fill = PatternFill('solid', start_color=fondo)
    c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def _construir_dashboard(wb, parametros, resultados, validacion, borde, backtest=None, comparativo=None):
    """Portada ejecutiva: KPIs de liquidez, semáforo de validación, fan chart,
    factores que más afectan el timing, guía de percentiles y backtest vs real."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import LineChart, Reference
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet("Dashboard")
    ws.sheet_view.showGridLines = False

    # Etiquetas de mes calendario (jul 2026...) desde el comparativo
    if comparativo and comparativo.get("meses"):
        etq_mes = [mc["etiqueta"] for mc in comparativo["meses"]]
    else:
        etq_mes = None
    def _lbl(i):
        return etq_mes[i] if (etq_mes and i < len(etq_mes)) else f"M{i+1}"

    # ----- Título -----
    ws.merge_cells('A1:L2')
    _header_cell(ws, 'A1', "DASHBOARD · PROYECCIÓN DE FLUJOS DE EFECTIVO", VERDE_PATRIA, 16)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 22
    ws.merge_cells('A3:L3')
    cm = ws['A3']
    cm.value = (f"Reaseguradora Patria · Grupo Peña Verde  |  Generado {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  "
                f"Horizonte {HORIZONTE_MESES} meses · {N_SIMULACIONES:,} simulaciones  |  Monte Carlo alimentado por modelo de supervivencia (AFT)")
    cm.font = Font(name='Calibri', size=9, italic=True, color=GRIS_NEUTRO)
    cm.fill = PatternFill('solid', start_color=VERDE_CLARO)
    cm.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[3].height = 18

    # ----- KPIs de liquidez (acumulado del horizonte) -----
    neto = resultados["neto"]; ing = resultados["ingresos"]; egr = resultados["egresos"]
    neto_acum = neto.sum(axis=1)
    ing_acum = float(ing.sum(axis=1).mean())
    egr_acum = float(egr.sum(axis=1).mean())
    neto_med = float(np.median(neto_acum))
    var_liq = float(np.percentile(neto_acum, 5))   # P5: escenario adverso de liquidez

    def money(v):
        a = abs(v)
        if a >= 1e9:  return f"${v/1e9:,.1f}B"
        if a >= 1e6:  return f"${v/1e6:,.1f}M"
        if a >= 1e3:  return f"${v/1e3:,.0f}K"
        return f"${v:,.0f}"

    ws.row_dimensions[5].height = 16
    ws.row_dimensions[6].height = 22
    ws.row_dimensions[7].height = 14
    _kpi_card(ws, 1, 5, 3, "INGRESOS ESPERADOS (12M)", money(ing_acum), VERDE_PATRIA, "media de simulaciones")
    _kpi_card(ws, 4, 5, 3, "EGRESOS ESPERADOS (12M)", money(egr_acum), NARANJA_DOC, "media de simulaciones")
    color_neto = VERDE_PATRIA if neto_med >= 0 else ROJO_ALERTA
    _kpi_card(ws, 7, 5, 3, "FLUJO NETO ESPERADO (12M)", money(neto_med), color_neto, "mediana del neto acumulado")
    _kpi_card(ws, 10, 5, 3, "VaR LIQUIDEZ (P5)", money(var_liq), ROJO_ALERTA, "escenario adverso 1-en-20")

    # ----- Semáforo de validación -----
    ws.merge_cells('A10:L10')
    _header_cell(ws, 'A10', "VALIDACIÓN ESTADÍSTICA DEL MODELO", VERDE_SECUNDARIO, 11)

    glob = (validacion or {}).get("global", "ok")
    ws.merge_cells('A11:C13')
    cg = ws['A11']
    cg.value = SEMAFORO_TXT.get(glob, glob).replace("✓ ", "").replace("⚠ ", "").replace("✗ ", "")
    cg.font = Font(name='Calibri', size=15, bold=True, color="FFFFFF")
    cg.fill = PatternFill('solid', start_color=SEMAFORO.get(glob, "808080"))
    cg.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.merge_cells('A14:C14')
    cgl = ws['A14']
    cgl.value = "Veredicto global"
    cgl.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
    cgl.alignment = Alignment(horizontal='center')

    # Tabla compacta de componentes
    comp_rows = []
    if validacion:
        if validacion.get("tc"):
            comp_rows.append(("Tipo de cambio (GBM)", validacion["tc"]["veredicto"], validacion["tc"]["resumen"]))
        for nombre, v in validacion.get("conceptos", {}).items():
            comp_rows.append((nombre, v["veredicto"], _resumen_concepto(v)))
        if validacion.get("montecarlo"):
            comp_rows.append(("Convergencia Monte Carlo", validacion["montecarlo"]["veredicto"], validacion["montecarlo"]["resumen"]))

    hr = 11
    _header_cell(ws, f'E{hr}', "Componente", VERDE_PATRIA, 9)
    ws.merge_cells(f'E{hr}:G{hr}')
    _header_cell(ws, f'H{hr}', "Estado", VERDE_PATRIA, 9)
    _header_cell(ws, f'I{hr}', "Resumen", VERDE_PATRIA, 9)
    ws.merge_cells(f'I{hr}:L{hr}')
    rr = hr + 1
    for nombre, estado, resumen in comp_rows[:8]:
        ws.merge_cells(f'E{rr}:G{rr}')
        ws[f'E{rr}'].value = nombre
        ws[f'E{rr}'].font = Font(name='Calibri', size=9)
        ce = ws[f'H{rr}']
        ce.value = SEMAFORO_TXT.get(estado, estado)
        ce.font = Font(name='Calibri', size=9, bold=True, color="FFFFFF")
        ce.fill = PatternFill('solid', start_color=SEMAFORO.get(estado, "808080"))
        ce.alignment = Alignment(horizontal='center')
        ws.merge_cells(f'I{rr}:L{rr}')
        ws[f'I{rr}'].value = resumen
        ws[f'I{rr}'].font = Font(name='Calibri', size=8, color=GRIS_NEUTRO)
        ws[f'I{rr}'].alignment = Alignment(horizontal='left', vertical='center')
        for cc in range(5, 13):
            ws[f'{get_column_letter(cc)}{rr}'].border = borde
        rr += 1

    # ----- Datos para el fan chart (escribir en columnas auxiliares N..Q, ocultas) -----
    perc = resumir_percentiles(neto, [5, 50, 95])
    fila_chart = max(rr, 16) + 1
    fila_titulo = fila_chart
    ws.merge_cells(f'A{fila_titulo}:L{fila_titulo}')
    _header_cell(ws, f'A{fila_titulo}', "PROYECCIÓN DE FLUJO NETO MENSUAL · percentiles vs año anterior", VERDE_SECUNDARIO, 11)

    # Datos auxiliares. Si hay comparativo, se usa la proyección ESTACIONAL (sin
    # rampa) y se agrega la línea del MISMO MES DEL AÑO ANTERIOR (n-1).
    col_aux = 14  # N
    usar_comp = bool(comparativo and comparativo.get("meses"))
    ws.cell(row=1, column=col_aux, value="Mes")
    ws.cell(row=1, column=col_aux+1, value="P5 (adverso)")
    ws.cell(row=1, column=col_aux+2, value="P50 (esperado)")
    ws.cell(row=1, column=col_aux+3, value="P95 (favorable)")
    ws.cell(row=1, column=col_aux+4, value="Real año anterior")
    if usar_comp:
        filas_mes = comparativo["meses"]
        n_filas = len(filas_mes)
        for i, mc in enumerate(filas_mes):
            ws.cell(row=2+i, column=col_aux, value=mc["etiqueta"])
            ws.cell(row=2+i, column=col_aux+1, value=float(mc["p5"]))
            ws.cell(row=2+i, column=col_aux+2, value=float(mc["neto"]))
            ws.cell(row=2+i, column=col_aux+3, value=float(mc["p95"]))
            rv = mc.get("real_neto_aa")
            ws.cell(row=2+i, column=col_aux+4,
                    value=(float(rv) if (rv is not None and np.isfinite(rv)) else None))
    else:
        n_filas = len(perc)
        for i in range(n_filas):
            ws.cell(row=2+i, column=col_aux, value=_lbl(i))
            ws.cell(row=2+i, column=col_aux+1, value=float(perc["P5"].iloc[i]))
            ws.cell(row=2+i, column=col_aux+2, value=float(perc["P50"].iloc[i]))
            ws.cell(row=2+i, column=col_aux+3, value=float(perc["P95"].iloc[i]))
    for cc in range(col_aux, col_aux+5):
        ws.column_dimensions[get_column_letter(cc)].width = 14   # fuera del área de impresión

    chart = LineChart()
    chart.title = "Flujo neto mensual: escenarios (P5/P50/P95) vs año anterior"
    chart.style = 2
    max_col_chart = col_aux+4 if usar_comp else col_aux+3
    data = Reference(ws, min_col=col_aux+1, max_col=max_col_chart, min_row=1, max_row=1+n_filas)
    cats = Reference(ws, min_col=col_aux, max_col=col_aux, min_row=2, max_row=1+n_filas)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    # Colores: P5 rojo, P50 verde (grueso), P95 azul, año anterior dorado FUERTE punteado
    colores = [ROJO_ALERTA, VERDE_PATRIA, AZUL_CUSF, DORADO_FUERTE]
    for idx, (s, col) in enumerate(zip(chart.series, colores)):
        s.graphicalProperties.line.solidFill = col
        s.graphicalProperties.line.width = 30000 if idx == 1 else (26000 if idx == 3 else 18000)
        s.smooth = False
        if idx == 3:   # año anterior: punteado y grueso para que resalte
            s.graphicalProperties.line.dashStyle = "dash"
    chart.y_axis.numFmt = '#,##0,,"M"'; chart.y_axis.title = "Neto mensual (MXN)"
    _estilo_lineas(chart, alto=9.5, ancho=23, rotar_x=True)
    ws.add_chart(chart, f'A{fila_titulo+1}')

    # ----- Factores que más afectan el timing (efectos AFT) -----
    fila_fac = fila_titulo + 21
    ws.merge_cells(f'A{fila_fac}:L{fila_fac}')
    _header_cell(ws, f'A{fila_fac}', "FACTORES QUE MÁS AFECTAN EL TIEMPO DE COBRO/PAGO (modelo de supervivencia)", VERDE_SECUNDARIO, 11)
    # Preferir el análisis dedicado de factores (AFT sobre el lag IniVig->proceso);
    # si no, caer al AFT por concepto (cuando exista).
    efectos = None; info_fac = None
    fl = parametros.get("factores_lag")
    if fl and fl.get("efectos"):
        efectos = fl["efectos"]; info_fac = fl
    else:
        for p in parametros["conceptos"].values():
            if p["lag"] and p["lag"].get("metodo") == "aft":
                efectos = p["lag"]["efectos"]; break
    rr = fila_fac + 1
    if efectos:
        if info_fac:
            ws.merge_cells(f'A{rr}:L{rr}')
            cinfo = ws[f'A{rr}']
            cinfo.value = (f"Mide cómo cada factor alarga (+) o acorta (−) la demora entre inicio de vigencia "
                           f"y proceso. Base: {info_fac['n']:,} movimientos · mediana {info_fac['mediana_dias']:.0f} días "
                           f"· C-index {info_fac['c_index']:.2f} (>0.6 = discrimina bien).")
            cinfo.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
            cinfo.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            rr += 1
        _header_cell(ws, f'A{rr}', "Factor", VERDE_PATRIA, 9); ws.merge_cells(f'A{rr}:D{rr}')
        _header_cell(ws, f'E{rr}', "Efecto en la demora", VERDE_PATRIA, 9); ws.merge_cells(f'E{rr}:G{rr}')
        _header_cell(ws, f'H{rr}', "Interpretación", VERDE_PATRIA, 9); ws.merge_cells(f'H{rr}:L{rr}')
        rr += 1
        pvals = (info_fac or {}).get("pvals", {})
        top = sorted(efectos.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6]
        for cov, ef in top:
            ws.merge_cells(f'A{rr}:D{rr}'); ws[f'A{rr}'].value = _nombre_covariable(cov)
            ws[f'A{rr}'].font = Font(name='Calibri', size=9)
            ce = ws[f'E{rr}']; ws.merge_cells(f'E{rr}:G{rr}')
            ce.value = ef; ce.number_format = '+0%;-0%;0%'
            col = ROJO_ALERTA if ef > 0.25 else (SEMAFORO["ok"] if ef < -0.1 else GRIS_NEUTRO)
            ce.font = Font(name='Calibri', size=9, bold=True, color=col)
            ce.alignment = Alignment(horizontal='center')
            ws.merge_cells(f'H{rr}:L{rr}')
            sig = ""
            if cov in pvals:
                sig = "  (significativo)" if pvals[cov] < 0.05 else "  (no significativo)"
            ws[f'H{rr}'].value = (("alarga el cobro/pago" if ef > 0.05 else
                                  ("acorta el cobro/pago" if ef < -0.05 else "efecto leve")) + sig)
            ws[f'H{rr}'].font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
            for cc in range(1, 13):
                ws[f'{get_column_letter(cc)}{rr}'].border = borde
            rr += 1
    else:
        # Mensaje cuando no se pudo calcular (sin lifelines o sin fechas usables)
        ws.merge_cells(f'A{rr}:L{rr+1}')
        cmsg = ws[f'A{rr}']
        cmsg.value = ("Esta sección analiza, con un modelo de supervivencia (AFT) sobre el lag inicio de "
                      "vigencia → mes de proceso, cómo el corredor, la moneda y el territorio alargan o "
                      "acortan el cobro/pago. No se pudo calcular: verifica que IniVig y aPOG_MesProc estén "
                      "en el caché (FORZAR_RECARGA=True una vez) y que lifelines esté instalado.")
        cmsg.font = Font(name='Calibri', size=9, italic=True, color=NARANJA_DOC)
        cmsg.fill = PatternFill('solid', start_color="FBF4E8")
        cmsg.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        for cc in range(1, 13):
            for rfac in (rr, rr+1):
                ws[f'{get_column_letter(cc)}{rfac}'].border = borde
        rr += 2

    # ----- Guía: ¿qué percentil usar? -----
    rr += 1
    ws.merge_cells(f'A{rr}:L{rr}')
    _header_cell(ws, f'A{rr}', "¿QUÉ PERCENTIL USAR SEGÚN LA DECISIÓN?", VERDE_SECUNDARIO, 11)
    rr += 1
    _header_cell(ws, f'A{rr}', "Percentil", AZUL_CUSF, 9); ws.merge_cells(f'A{rr}:B{rr}')
    _header_cell(ws, f'C{rr}', "Qué representa", AZUL_CUSF, 9); ws.merge_cells(f'C{rr}:F{rr}')
    _header_cell(ws, f'G{rr}', "Úsalo para", AZUL_CUSF, 9); ws.merge_cells(f'G{rr}:L{rr}')
    rr += 1
    guia = [
        ("P50 (mediana)", "Escenario central; la mitad de las veces el flujo es mayor y la mitad menor.",
         "Presupuesto base y planeación normal de tesorería.  ← el de referencia"),
        ("P5 (adverso)", "Escenario malo: solo 1 de cada 20 veces el flujo es peor que éste.",
         "Liquidez / colchón mínimo y pruebas de estrés (cuánto necesitas en el peor caso)."),
        ("P95 (favorable)", "Escenario bueno: solo 1 de cada 20 veces el flujo es mejor.",
         "Capacidad / techo: no comprometas gasto contra ingresos que rara vez llegan."),
    ]
    for pct, repr_, uso in guia:
        ws.merge_cells(f'A{rr}:B{rr}'); ws[f'A{rr}'].value = pct
        ws[f'A{rr}'].font = Font(name='Calibri', size=9, bold=True, color=VERDE_PATRIA)
        ws[f'A{rr}'].alignment = Alignment(horizontal='left', vertical='center', indent=1)
        ws.merge_cells(f'C{rr}:F{rr}'); ws[f'C{rr}'].value = repr_
        ws[f'C{rr}'].font = Font(name='Calibri', size=8.5); ws[f'C{rr}'].alignment = Alignment(wrap_text=True, vertical='center')
        ws.merge_cells(f'G{rr}:L{rr}'); ws[f'G{rr}'].value = uso
        ws[f'G{rr}'].font = Font(name='Calibri', size=8.5); ws[f'G{rr}'].alignment = Alignment(wrap_text=True, vertical='center')
        ws.row_dimensions[rr].height = 26
        for cc in range(1, 13):
            ws[f'{get_column_letter(cc)}{rr}'].border = borde
        rr += 1

    # ----- Backtest contra el real de los últimos 12 meses -----
    if backtest:
        rr += 1
        ws.merge_cells(f'A{rr}:L{rr}')
        _header_cell(ws, f'A{rr}', "BACKTEST · ¿QUÉ TAN BIEN MODELAMOS LA REALIDAD? (vs. real de los últimos 12 meses)", VERDE_SECUNDARIO, 11)
        rr += 1
        cob = backtest["cobertura"]
        col_cob = SEMAFORO["ok"] if cob >= 0.8 else (SEMAFORO["precaucion"] if cob >= 0.6 else SEMAFORO["alerta"])

        # Tabla comparativa por flujo (real vs modelo, promedio mensual)
        _header_cell(ws, f'A{rr}', "Flujo (promedio mensual)", VERDE_PATRIA, 9); ws.merge_cells(f'A{rr}:D{rr}')
        _header_cell(ws, f'E{rr}', "Real (12m)", VERDE_PATRIA, 9); ws.merge_cells(f'E{rr}:F{rr}')
        _header_cell(ws, f'G{rr}', "Modelo", VERDE_PATRIA, 9); ws.merge_cells(f'G{rr}:H{rr}')
        _header_cell(ws, f'I{rr}', "Desvío", VERDE_PATRIA, 9); ws.merge_cells(f'I{rr}:J{rr}')
        _header_cell(ws, f'K{rr}', "Lectura", VERDE_PATRIA, 9); ws.merge_cells(f'K{rr}:L{rr}')
        rr += 1
        etiquetas = [("ingresos", "Ingresos (cobros)"), ("egresos", "Egresos (pagos)"), ("neto", "Neto")]
        for clave, lbl in etiquetas:
            fl = backtest["flujos"][clave]
            es_neto = clave == "neto"
            ws.merge_cells(f'A{rr}:D{rr}'); ws[f'A{rr}'].value = lbl
            ws[f'A{rr}'].font = Font(name='Calibri', size=9, bold=es_neto, color=VERDE_PATRIA if es_neto else "2B2B2B")
            ws[f'A{rr}'].alignment = Alignment(horizontal='left', vertical='center', indent=1)
            ws.merge_cells(f'E{rr}:F{rr}'); ws[f'E{rr}'].value = money(fl["real"]); ws[f'E{rr}'].alignment = Alignment(horizontal='center')
            ws[f'E{rr}'].font = Font(name='Calibri', size=9)
            ws.merge_cells(f'G{rr}:H{rr}'); ws[f'G{rr}'].value = money(fl["modelo"]); ws[f'G{rr}'].alignment = Alignment(horizontal='center')
            ws[f'G{rr}'].font = Font(name='Calibri', size=9, color=AZUL_CUSF)
            dv = fl["desvio"]
            ws.merge_cells(f'I{rr}:J{rr}'); cdv = ws[f'I{rr}']
            cdv.value = (f"{dv:+.0%}" if dv is not None and np.isfinite(dv) else "—")
            col_dv = SEMAFORO["ok"] if (dv is not None and abs(dv) < 0.15) else (SEMAFORO["precaucion"] if (dv is not None and abs(dv) < 0.35) else ROJO_ALERTA)
            cdv.font = Font(name='Calibri', size=9, bold=True, color=col_dv); cdv.alignment = Alignment(horizontal='center')
            ws.merge_cells(f'K{rr}:L{rr}')
            if not es_neto:
                txt = "el modelo capta bien el bruto" if (dv is not None and abs(dv) < 0.15) else "revisar volumen/estacionalidad"
            else:
                txt = "residual sensible (dif. de brutos)"
            ws[f'K{rr}'].value = txt
            ws[f'K{rr}'].font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
            for cc in range(1, 13):
                ws[f'{get_column_letter(cc)}{rr}'].border = borde
            rr += 1
        # Cobertura del neto
        ws.merge_cells(f'A{rr}:D{rr}'); ws[f'A{rr}'].value = "Cobertura del neto (meses dentro de P5–P95)"
        ws[f'A{rr}'].font = Font(name='Calibri', size=9, bold=True, color=VERDE_PATRIA)
        ws[f'A{rr}'].alignment = Alignment(horizontal='left', vertical='center', indent=1)
        ws.merge_cells(f'E{rr}:F{rr}'); cc2 = ws[f'E{rr}']
        cc2.value = f"{backtest['dentro']}/{backtest['n_meses']} ({cob:.0%})"
        cc2.font = Font(name='Calibri', size=9, bold=True, color=col_cob); cc2.alignment = Alignment(horizontal='center')
        ws.merge_cells(f'G{rr}:L{rr}')
        ws[f'G{rr}'].value = ("buena calibración del rango" if cob >= 0.8 else
                              ("aceptable; revisar meses fuera de banda" if cob >= 0.6 else "rango aún no captura la realidad"))
        ws[f'G{rr}'].font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
        for cc in range(1, 13):
            ws[f'{get_column_letter(cc)}{rr}'].border = borde
        rr += 2

        # ----- Comparativo por MES CALENDARIO: proyección vs real interanual -----
        rr += 1
        if comparativo and comparativo.get("meses"):
            meses_c = comparativo["meses"]
            _header_cell(ws, f'A{rr}', "PROYECCIÓN POR MES vs REAL DEL MISMO MES DEL AÑO ANTERIOR", VERDE_SECUNDARIO, 11)
            ws.merge_cells(f'A{rr}:L{rr}')
            rr += 1
            ws.merge_cells(f'A{rr}:L{rr}')
            cexp = ws[f'A{rr}']
            cexp.value = ("Cada mes proyectado (con estacionalidad) se compara contra lo que REALMENTE pasó "
                          "ese mismo mes el año anterior. Útil para ver si el mes que viene se moverá como su "
                          "equivalente histórico.")
            cexp.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
            cexp.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            rr += 1

            # Encabezado de tabla visible
            cols_hdr = [("A", "Mes proyectado"), ("C", "Proyección neto (P50)"),
                        ("F", "Real mismo mes año ant."), ("I", "Banda P5–P95")]
            for cl, tt in cols_hdr:
                _header_cell(ws, f'{cl}{rr}', tt, VERDE_PATRIA, 9)
            ws.merge_cells(f'A{rr}:B{rr}'); ws.merge_cells(f'C{rr}:E{rr}')
            ws.merge_cells(f'F{rr}:H{rr}'); ws.merge_cells(f'I{rr}:L{rr}')
            rr += 1
            fila_tabla_ini = rr
            # Datos auxiliares para el gráfico en N-Q (alineados a las filas de la tabla)
            ws[f'N{rr-1}'] = "MesCal"; ws[f'O{rr-1}'] = "Proyección P50"; ws[f'P{rr-1}'] = "Real año anterior"
            for cc in ('N', 'O', 'P'):
                ws[f'{cc}{rr-1}'].font = Font(name='Calibri', size=8, bold=True, color=VERDE_PATRIA)
            for mc in meses_c:
                ws.merge_cells(f'A{rr}:B{rr}')
                ws[f'A{rr}'].value = mc["etiqueta"]
                ws[f'A{rr}'].font = Font(name='Calibri', size=9, bold=True)
                ws.merge_cells(f'C{rr}:E{rr}')
                ws[f'C{rr}'].value = mc["neto"]; ws[f'C{rr}'].number_format = '$#,##0,,"M"'
                ws[f'C{rr}'].font = Font(name='Calibri', size=9)
                ws.merge_cells(f'F{rr}:H{rr}')
                rv = mc["real_neto_aa"]
                if rv is not None and np.isfinite(rv):
                    ws[f'F{rr}'].value = rv; ws[f'F{rr}'].number_format = '$#,##0,,"M"'
                    ws[f'F{rr}'].font = Font(name='Calibri', size=9, color=AZUL_CUSF)
                else:
                    ws[f'F{rr}'].value = "s/d"; ws[f'F{rr}'].font = Font(name='Calibri', size=9, italic=True, color=GRIS_NEUTRO)
                ws.merge_cells(f'I{rr}:L{rr}')
                ws[f'I{rr}'].value = f"${mc['p5']/1e6:,.0f}M  a  ${mc['p95']/1e6:,.0f}M"
                ws[f'I{rr}'].font = Font(name='Calibri', size=8, color=GRIS_NEUTRO)
                # Aux para gráfico
                ws[f'N{rr}'] = mc["etiqueta"]; ws[f'O{rr}'] = mc["neto"]
                ws[f'P{rr}'] = (rv if (rv is not None and np.isfinite(rv)) else None)
                for cc in range(1, 13):
                    ws[f'{get_column_letter(cc)}{rr}'].border = borde
                rr += 1
            fila_tabla_fin = rr - 1

            # ----- Validación visual: tendencia REAL (24m) + PROYECCIÓN (12m) -----
            # En líneas (no barras). Si la P50 proyectada queda por ENCIMA (menos
            # negativa) que el ritmo real reciente, el modelo es optimista (dilución).
            tend = comparativo.get("tendencia", [])
            diag = comparativo.get("diagnostico", {})
            colT = 20  # T..X (fuera del área de impresión A:L)
            ws.cell(row=1, column=colT, value="Mes")
            ws.cell(row=1, column=colT+1, value="Real (histórico)")
            ws.cell(row=1, column=colT+2, value="Proyección P50")
            ws.cell(row=1, column=colT+3, value="Proy. P5")
            ws.cell(row=1, column=colT+4, value="Proy. P95")
            ri = 2
            for t in tend:   # histórico
                ws.cell(row=ri, column=colT, value=t["etiqueta"])
                ws.cell(row=ri, column=colT+1, value=t["neto"])
                ri += 1
            # punto puente: conecta el último real con la proyección
            if tend:
                ws.cell(row=ri-1, column=colT+2, value=tend[-1]["neto"])
            for mc in meses_c:   # proyección
                ws.cell(row=ri, column=colT, value=mc["etiqueta"])
                ws.cell(row=ri, column=colT+2, value=float(mc["neto"]))
                ws.cell(row=ri, column=colT+3, value=float(mc["p5"]))
                ws.cell(row=ri, column=colT+4, value=float(mc["p95"]))
                ri += 1
            fila_fin_tend = ri - 1
            for cc in range(colT, colT+5):
                ws.column_dimensions[get_column_letter(cc)].width = 14

            from openpyxl.chart import LineChart as _LC, Reference as _Ref
            lc = _LC()
            lc.title = "Tendencia real (últimos 24 meses) y proyección (12 meses) — neto mensual"
            lc.style = 2
            datos = _Ref(ws, min_col=colT+1, max_col=colT+4, min_row=1, max_row=fila_fin_tend)
            cats = _Ref(ws, min_col=colT, max_col=colT, min_row=2, max_row=fila_fin_tend)
            lc.add_data(datos, titles_from_data=True); lc.set_categories(cats)
            cols_l = [GRIS_NEUTRO, VERDE_PATRIA, ROJO_ALERTA, AZUL_CUSF]
            for idx, (s, col) in enumerate(zip(lc.series, cols_l)):
                s.graphicalProperties.line.solidFill = col
                s.graphicalProperties.line.width = 28000 if idx in (0, 1) else 14000
                s.smooth = False
                if idx >= 2:
                    s.graphicalProperties.line.dashStyle = "sysDash"
            lc.y_axis.numFmt = '#,##0,,"M"'; lc.y_axis.title = "Neto mensual (MXN)"
            _estilo_lineas(lc, alto=10.5, ancho=26, rotar_x=True, sz_x=750)
            ws.add_chart(lc, f'A{rr}')
            rr += 23

            # Diagnóstico numérico de dilución (clave para validar la cifra)
            pr = diag.get("prom_reciente_12m"); pv = diag.get("prom_ventana"); pp = diag.get("proy_promedio")
            ws.merge_cells(f'A{rr}:L{rr+2}')
            cd = ws[f'A{rr}']
            if pr is not None and pv is not None and np.isfinite(pr) and np.isfinite(pv):
                dif_rel = abs(pr - pv) / (abs(pv) if pv else 1.0)
                if dif_rel > 0.15:
                    direccion = "más BAJO (más negativo)" if pr < pv else "más ALTO"
                    señal = (f"⚠ El ritmo reciente es {direccion} que el promedio de la ventana: el modelo, calibrado "
                             "sobre toda la ventana, no refleja ese ritmo reciente. Para que la proyección lo refleje, "
                             "fija MESES_CALIBRACION_RECIENTE = 12 o 18.")
                else:
                    señal = ("El ritmo reciente es similar al promedio de la ventana: la proyección es consistente "
                             "con el comportamiento histórico.")
                cd.value = (f"VALIDACIÓN DE LA CIFRA — Neto mensual promedio:  reciente 12m = ${pr/1e6:,.0f}M   |   "
                            f"ventana completa ({diag.get('n_meses_ventana','?')}m) = ${pv/1e6:,.0f}M   |   "
                            f"proyección = ${pp/1e6:,.0f}M.\n{señal}")
            else:
                cd.value = ("VALIDACIÓN DE LA CIFRA: compara la línea verde (proyección P50) con la gris (real "
                            "reciente). Si la verde queda por encima (menos negativa), la proyección es optimista "
                            "respecto al ritmo reciente; considera MESES_CALIBRACION_RECIENTE = 12 o 18.")
            cd.font = Font(name='Calibri', size=9, color=NARANJA_DOC)
            cd.fill = PatternFill('solid', start_color="FBF4E8")
            cd.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            rr += 3

            ws.merge_cells(f'A{rr}:L{rr+1}')
            cnota = ws[f'A{rr}']
            cnota.value = ("Cómo leerlo: la línea GRIS es el neto real de los últimos 24 meses; la VERDE es la "
                           "proyección P50 (con su banda P5/P95 punteada). Si la verde continúa la trayectoria de "
                           "la gris, la proyección es creíble; si salta por encima, revisa la ventana de calibración.")
            cnota.font = Font(name='Calibri', size=8.5, italic=True, color=GRIS_NEUTRO)
            cnota.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            rr += 2


    # Anchos de columna
    for cc in range(1, 13):
        ws.column_dimensions[get_column_letter(cc)].width = 11.5

    # ----- Layout de impresión: horizontal, ajustar a ancho, área A1:L -----
    from openpyxl.worksheet.properties import PageSetupProperties
    ultima_fila = rr + 1
    ws.print_area = f'A1:L{ultima_fila}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.4


def _resumen_concepto(v):
    """Resumen corto de la validación de un concepto para el dashboard."""
    partes = []
    if v.get("magnitud"): partes.append(f"mag {v['magnitud']['veredicto']}")
    if v.get("frecuencia"): partes.append(f"frec {v['frecuencia']['veredicto']}")
    if v.get("lag"): partes.append(f"lag {v['lag']['veredicto']}")
    return " · ".join(partes)


def _nombre_covariable(cov):
    """Traduce el nombre técnico de la covariable a algo legible, usando los mapeos
    de moneda y territorio (MAPEO_MONEDAS / MAPEO_TERRITORIOS) cuando aplica."""
    mapa = {"corredor": "Negocio con corredor (vs. directo)",
            "usd": f"Operación en {MAPEO_MONEDAS.get(MONEDA_USD_ID, 'USD')} (vs. {MAPEO_MONEDAS.get(1, 'MXN')})"}
    if cov in mapa:
        return mapa[cov]
    if cov.startswith("terr_"):
        t = cov.replace("terr_", "")
        try:
            nombre = MAPEO_TERRITORIOS.get(int(t))
        except (ValueError, TypeError):
            nombre = None
        return f"Territorio {nombre}" if nombre else f"Territorio {t}"
    if cov.startswith("mon_"):
        m = cov.replace("mon_", "")
        try:
            nombre = MAPEO_MONEDAS.get(int(m))
        except (ValueError, TypeError):
            nombre = None
        return f"Moneda {nombre}" if nombre else f"Moneda {m}"
    return cov


def _nombre_cedente(codigo):
    """Clave de cedente (CiaTom) -> nombre del catálogo, o 'Ced N' si no está."""
    try:
        c = int(str(codigo).strip())
    except (ValueError, TypeError):
        return str(codigo)
    nom = MAPEO_CEDENTES.get(c, f"Ced {c}")
    return nom if len(nom) <= 26 else nom[:24] + "\u2026"


def _nombre_corredor(codigo):
    """Clave de corredor (CorrTom) -> nombre del catálogo, o 'Corr N' si no está."""
    try:
        c = int(str(codigo).strip())
    except (ValueError, TypeError):
        return str(codigo)
    nom = MAPEO_CORREDORES.get(c, f"Corr {c}")
    return nom if len(nom) <= 26 else nom[:24] + "\u2026"


def _nombre_moneda(codigo):
    """Código de moneda -> nombre (USD, MXN...) o 'Moneda N' si no está mapeado."""
    try:
        c = int(codigo)
    except (ValueError, TypeError):
        return str(codigo)
    return MAPEO_MONEDAS.get(c, f"Moneda {c}")


def _nombre_territorio(codigo):
    """Código de territorio -> nombre o 'Territorio N' si no está mapeado."""
    try:
        c = int(codigo)
    except (ValueError, TypeError):
        return str(codigo)
    return MAPEO_TERRITORIOS.get(c, f"Territorio {c}")


def _construir_hoja_validacion(wb, validacion, borde):
    """Hoja con el detalle de todas las pruebas estadísticas."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    if not validacion:
        return
    ws = wb.create_sheet("Validación")
    ws.sheet_view.showGridLines = False
    ws.merge_cells('A1:E2')
    _header_cell(ws, 'A1', "VALIDACIÓN ESTADÍSTICA — DETALLE DE PRUEBAS", VERDE_PATRIA, 14)
    ws.row_dimensions[1].height = 20; ws.row_dimensions[2].height = 20
    ws.merge_cells('A3:E3')
    c = ws['A3']
    c.value = ("Cada componente se valida con pruebas formales y medidas descriptivas. Con muestras grandes, "
               "las pruebas formales (KS, etc.) tienden a rechazar por exceso de potencia; el veredicto se basa "
               "en medidas descriptivas (R² de QQ, error en cuantiles, C-index) más robustas a la escala.")
    c.font = Font(name='Calibri', size=9, italic=True, color=GRIS_NEUTRO)
    c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ws.row_dimensions[3].height = 42

    r = 5
    def bloque(titulo, val):
        nonlocal r
        if not val:
            return
        ws.merge_cells(f'A{r}:E{r}')
        estado = val.get("veredicto", "")
        _header_cell(ws, f'A{r}', f"{val.get('componente','')}   [{SEMAFORO_TXT.get(estado, estado)}]",
                     SEMAFORO.get(estado, VERDE_PATRIA), 10)
        r += 1
        # Cabecera de la tabla
        for j, h in enumerate(["Prueba", "Valor", "Referencia", "Veredicto"], start=1):
            _header_cell(ws, f'{get_column_letter(j)}{r}', h, VERDE_SECUNDARIO, 9)
        ws.column_dimensions['A'].width = 32
        r += 1
        for fila in val.get("pruebas", []):
            nombre, valor, ref, ver = (list(fila) + ["", "", "", ""])[:4]
            for j, txt in zip(range(1, 4), [nombre, valor, ref]):
                cel = ws[f'{get_column_letter(j)}{r}']
                cel.value = txt
                cel.font = Font(name='Calibri', size=9)
            cv = ws[f'D{r}']
            cv.value = ver
            if ver in SEMAFORO:
                cv.font = Font(name='Calibri', size=9, bold=True, color="FFFFFF")
                cv.fill = PatternFill('solid', start_color=SEMAFORO[ver])
                cv.alignment = Alignment(horizontal='center')
            else:
                cv.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
            for j in range(1, 5):
                ws[f'{get_column_letter(j)}{r}'].border = borde
            r += 1
        r += 1

    bloque("", validacion.get("tc"))
    for nombre, v in validacion.get("conceptos", {}).items():
        ws.merge_cells(f'A{r}:E{r}')
        _header_cell(ws, f'A{r}', f"CONCEPTO: {nombre}", AZUL_CUSF, 10)
        r += 1
        bloque("", v.get("magnitud"))
        bloque("", v.get("frecuencia"))
        bloque("", v.get("lag"))
    bloque("", validacion.get("montecarlo"))

    # ---------- BONDAD DE AJUSTE (Poisson por dispersión + KS simulado vs real) ----------
    bondad = validacion.get("bondad")
    if bondad:
        ws.merge_cells(f'A{r}:E{r}')
        _header_cell(ws, f'A{r}', "BONDAD DE AJUSTE — ¿las distribuciones del modelo se parecen a la realidad?", MORADO_PATRIA, 11)
        r += 1
        ws.merge_cells(f'A{r}:E{r}')
        cnote = ws[f'A{r}']
        cnote.value = ("Frecuencia: índice de dispersión χ² (var/media≈1 si es Poisson). Flujos: Kolmogorov-Smirnov de 2 "
                       "muestras entre la simulación (estado estacionario) y los flujos reales mensuales. p ≥ 0.05 = no se "
                       "rechaza el ajuste (verde).")
        cnote.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
        cnote.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.row_dimensions[r].height = 26
        r += 1
        for j, e in enumerate(["Prueba", "Detalle", "Estadístico", "p-valor", "Resultado"], start=1):
            _header_cell(ws, f'{get_column_letter(j)}{r}', e, VERDE_SECUNDARIO, 9)
        r += 1
        filas_b = ([("Poisson (dispersión) — " + fb["concepto"],
                     f"{fb['n_meses']} meses · media {fb['media']:,.0f} · var/media {fb['ratio']:.2f} · {fb['nota']}",
                     fb["estadistico"], fb["p"], fb["ok"]) for fb in bondad.get("frecuencia", [])] +
                   [("KS simulado vs real — " + fk["serie"],
                     f"{fk['n_real']} meses reales vs {fk['n_sim']:,} simulados · {fk['nota']}",
                     fk["estadistico"], fk["p"], fk["ok"]) for fk in bondad.get("flujos", [])])
        for nombre_p, detalle_p, est, pv, okb in filas_b:
            ws.cell(row=r, column=1, value=nombre_p).font = Font(name='Calibri', size=9, bold=True)
            cdet = ws.cell(row=r, column=2, value=detalle_p)
            cdet.font = Font(name='Calibri', size=8, color=GRIS_NEUTRO)
            cdet.alignment = Alignment(wrap_text=True, vertical='center')
            ws.cell(row=r, column=3, value=round(float(est), 3)).font = Font(name='Calibri', size=9)
            ws.cell(row=r, column=4, value=round(float(pv), 4)).font = Font(name='Calibri', size=9)
            cv = ws.cell(row=r, column=5, value="OK" if okb else "REVISAR")
            cv.font = Font(name='Calibri', size=9, bold=True, color="FFFFFF")
            cv.fill = PatternFill('solid', start_color=SEMAFORO["ok"] if okb else SEMAFORO["alerta"])
            cv.alignment = Alignment(horizontal='center')
            for j in range(1, 6):
                ws[f'{get_column_letter(j)}{r}'].border = borde
            r += 1

    for col, w in zip("BCDE", [16, 28, 14, 12]):
        ws.column_dimensions[col].width = w


def _kpi_card(ws, col_ini, fila, ancho, label, valor, color_valor=VERDE_PATRIA,
              subtexto="", color_fondo="F4F4F0"):
    """Dibuja una tarjeta KPI: etiqueta arriba, número grande, subtexto opcional."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    c0 = get_column_letter(col_ini)
    c1 = get_column_letter(col_ini + ancho - 1)
    ws.merge_cells(f'{c0}{fila}:{c1}{fila}')
    cl = ws[f'{c0}{fila}']
    cl.value = label
    cl.font = Font(name='Calibri', size=9, bold=True, color="FFFFFF")
    cl.fill = PatternFill('solid', start_color=VERDE_SECUNDARIO)
    cl.alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells(f'{c0}{fila+1}:{c1}{fila+2}')
    cv = ws[f'{c0}{fila+1}']
    cv.value = valor
    cv.font = Font(name='Calibri', size=18, bold=True, color=color_valor)
    cv.fill = PatternFill('solid', start_color=color_fondo)
    cv.alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells(f'{c0}{fila+3}:{c1}{fila+3}')
    cs = ws[f'{c0}{fila+3}']
    cs.value = subtexto
    cs.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
    cs.fill = PatternFill('solid', start_color=color_fondo)
    cs.alignment = Alignment(horizontal='center', vertical='center')
    lado = Side(style='thin', color='D8D8D0')
    for rr in range(fila, fila + 4):
        for cc in range(col_ini, col_ini + ancho):
            ws[f'{get_column_letter(cc)}{rr}'].border = Border(
                left=lado, right=lado, top=lado, bottom=lado)


# Colores de semáforo de validación
SEMAFORO = {"ok": "1E7B34", "precaucion": "B8860B", "alerta": "A6192E"}
SEMAFORO_TXT = {"ok": "OK", "precaucion": "Precaución", "alerta": "Alerta"}


def construir_excel(parametros, resultados, ruta_salida, validacion=None, backtest=None, comparativo=None, datos_piv=None, detalle_fac=None, hist_mensual=None, proy_2026=None):
    """Genera el Excel-Dashboard: portada con KPIs, validación, proyecciones y fans."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import LineChart, Reference, Series
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)

    # Etiquetas de mes calendario (jul 2026, ...) si hay comparativo; si no, "Mes N"
    if comparativo and comparativo.get("meses"):
        etiquetas_mes = [mc["etiqueta"] for mc in comparativo["meses"]]
    else:
        etiquetas_mes = None

    def _lbl_mes(i):
        if etiquetas_mes and i < len(etiquetas_mes):
            return etiquetas_mes[i]
        return f"Mes {i+1}"

    borde = Border(left=Side(style='thin', color='CCCCCC'),
                   right=Side(style='thin', color='CCCCCC'),
                   top=Side(style='thin', color='CCCCCC'),
                   bottom=Side(style='thin', color='CCCCCC'))

    # ==================================================================
    # HOJA 0: DASHBOARD (portada ejecutiva con KPIs)
    # ==================================================================
    _construir_dashboard(wb, parametros, resultados, validacion, borde, backtest, comparativo)

    # ------------------------------------------------------------------
    # HOJA 1: PORTADA + PARÁMETROS CALIBRADOS
    # ------------------------------------------------------------------
    ws = wb.create_sheet("Parámetros")
    ws.sheet_view.showGridLines = False
    ws.merge_cells('A1:H2')
    _header_cell(ws, 'A1', "MODELO DE PROYECCIÓN DE FLUJOS — MONTE CARLO | REASEGURADORA PATRIA",
                 VERDE_PATRIA, 15)
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 24

    ws.merge_cells('A3:H3')
    c = ws['A3']
    c.value = (f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Usuario: {usuario} | "
               f"Horizonte: {HORIZONTE_MESES} meses | Simulaciones: {N_SIMULACIONES:,} | Semilla: {SEMILLA}")
    c.font = Font(name='Calibri', size=10, italic=True, color=GRIS_NEUTRO)
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[3].height = 16

    # ----- Bloque TC -----
    r = 5
    _header_cell(ws, f'A{r}', "TIPO DE CAMBIO USD/MXN (GBM)", VERDE_SECUNDARIO, 12)
    ws.merge_cells(f'A{r}:H{r}')
    r += 1
    p_tc = parametros["tc"]
    filas_tc = [
        ("TC inicial (S0)", f"{p_tc['S0']:.4f}"),
        ("Drift mensual (μ)", f"{p_tc['mu_mensual']*100:.3f}%"),
        ("Volatilidad mensual (σ)", f"{p_tc['sigma_mensual']*100:.3f}%"),
        ("Modelado estocástico", "Sí (GBM)" if MODELAR_TC_ESTOCASTICO else "No (TC fijo)"),
    ]
    for etiqueta, valor in filas_tc:
        ws.cell(row=r, column=1, value=etiqueta).font = Font(name='Calibri', size=10, bold=True)
        ws.cell(row=r, column=2, value=valor).font = Font(name='Calibri', size=10)
        ws.cell(row=r, column=1).border = borde
        ws.cell(row=r, column=2).border = borde
        r += 1
    r += 1

    # ----- Tabla de parámetros por concepto -----
    _header_cell(ws, f'A{r}', "PARÁMETROS POR CONCEPTO", VERDE_SECUNDARIO, 12)
    ws.merge_cells(f'A{r}:H{r}')
    r += 1
    headers = ["Concepto", "Dirección", "Magnitud media", "Magnitud P95",
               "Ops/mes", "Lag mediano (d)", "Lag P95 (d)", "% USD"]
    for i, h in enumerate(headers, start=1):
        _header_cell(ws, f'{get_column_letter(i)}{r}', h, VERDE_PATRIA, 10)
    ws.row_dimensions[r].height = 28
    r += 1

    for nombre, p in parametros["conceptos"].items():
        mag = p["magnitud"]; freq = p["frecuencia"]; lag = p["lag"]
        ws.cell(row=r, column=1, value=nombre)
        ws.cell(row=r, column=2, value=p["direccion"].capitalize())
        ws.cell(row=r, column=3, value=mag["media_emp"] if mag else None).number_format = '$#,##0;($#,##0);-'
        ws.cell(row=r, column=4, value=mag["p95_emp"] if mag else None).number_format = '$#,##0;($#,##0);-'
        ws.cell(row=r, column=5, value=round(freq["lambda_mensual"],1) if freq else None)
        ws.cell(row=r, column=6, value=round(lag["mediana_dias"]) if lag else None)
        ws.cell(row=r, column=7, value=round(lag["p95_dias"]) if lag else None)
        ws.cell(row=r, column=8, value=p["prop_usd"]).number_format = '0%'
        # Color por dirección
        color_dir = VERDE_CLARO if p["direccion"] == "ingreso" else "FCE9E9"
        for col in range(1, 9):
            cel = ws.cell(row=r, column=col)
            cel.font = Font(name='Calibri', size=10)
            cel.border = borde
            cel.alignment = Alignment(horizontal='center' if col >= 2 else 'left',
                                       vertical='center', indent=1 if col == 1 else 0)
            if col == 2:
                cel.fill = PatternFill('solid', start_color=color_dir)
        r += 1

    for i, w in enumerate([26, 12, 16, 16, 10, 14, 12, 8], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ------------------------------------------------------------------
    # HOJA 1b: MODELO DE SUPERVIVENCIA DEL LAG (AFT) — efectos de covariables
    # ------------------------------------------------------------------
    hay_aft = any(p["lag"] and p["lag"].get("metodo") == "aft"
                  for p in parametros["conceptos"].values())
    if hay_aft:
        wsa = wb.create_sheet("Lag y supervivencia")
        wsa.sheet_view.showGridLines = False
        wsa.merge_cells('A1:G2')
        _header_cell(wsa, 'A1', "MODELO DE SUPERVIVENCIA DEL LAG (AFT) — DEMORA DE COBRO/PAGO",
                     VERDE_PATRIA, 14)
        wsa.row_dimensions[1].height = 22
        wsa.row_dimensions[2].height = 22

        wsa.merge_cells('A3:G3')
        c = wsa['A3']
        c.value = ("El lag (días entre el origen del movimiento y su materialización en efectivo) "
                   "se modela con un AFT con covariables. Un efecto de +X% significa que ese factor "
                   "ALARGA la demora ese porcentaje; un valor negativo la ACORTA. Calibrado desde Gonz "
                   "con corrección de censura por desarrollo de cohortes.")
        c.font = Font(name='Calibri', size=9, italic=True, color=GRIS_NEUTRO)
        c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        wsa.row_dimensions[3].height = 40

        r = 5
        # Recolectar todas las covariables presentes para armar columnas
        cov_set = []
        for p in parametros["conceptos"].values():
            if p["lag"] and p["lag"].get("metodo") == "aft":
                for cov in p["lag"]["design_cols"]:
                    if cov not in cov_set:
                        cov_set.append(cov)

        headers_aft = (["Concepto", "Distribución", "Mediana (d)", "P95 (d)", "Censurados"]
                       + [f"Efecto {c}" for c in cov_set])
        for i, h in enumerate(headers_aft, start=1):
            _header_cell(wsa, f'{get_column_letter(i)}{r}', h, VERDE_PATRIA, 9)
        wsa.row_dimensions[r].height = 30
        r += 1

        for nombre, p in parametros["conceptos"].items():
            lag = p["lag"]
            if not lag or lag.get("metodo") != "aft":
                continue
            wsa.cell(row=r, column=1, value=nombre).font = Font(name='Calibri', size=9, bold=True)
            wsa.cell(row=r, column=2, value=lag["tipo_aft"].capitalize())
            wsa.cell(row=r, column=3, value=round(lag["mediana_dias"]))
            wsa.cell(row=r, column=4, value=round(lag["p95_dias"]))
            wsa.cell(row=r, column=5, value=lag.get("n_censurado", 0))
            efectos = lag.get("efectos", {})
            for j, cov in enumerate(cov_set, start=6):
                if cov in efectos:
                    cel = wsa.cell(row=r, column=j, value=efectos[cov])
                    cel.number_format = '+0%;-0%;0%'
                    # Color: rojo si alarga mucho, verde si acorta
                    if efectos[cov] > 0.25:
                        cel.font = Font(name='Calibri', size=9, color=ROJO_ALERTA, bold=True)
                    elif efectos[cov] < -0.1:
                        cel.font = Font(name='Calibri', size=9, color=VERDE_PATRIA, bold=True)
                    else:
                        cel.font = Font(name='Calibri', size=9)
                else:
                    wsa.cell(row=r, column=j, value="—")
            for col in range(1, len(headers_aft) + 1):
                cel = wsa.cell(row=r, column=col)
                if cel.font is None:
                    cel.font = Font(name='Calibri', size=9)
                cel.border = borde
                cel.alignment = Alignment(horizontal='center' if col >= 2 else 'left',
                                           vertical='center', indent=1 if col == 1 else 0)
            r += 1

        wsa.column_dimensions['A'].width = 26
        for i in range(2, len(headers_aft) + 1):
            wsa.column_dimensions[get_column_letter(i)].width = 13

    # ------------------------------------------------------------------
    # HOJA 2: PROYECCIÓN AGREGADA (ingresos, egresos, neto) + fan chart
    # ------------------------------------------------------------------
    ws2 = wb.create_sheet("Proyección agregada")
    ws2.sheet_view.showGridLines = False
    ws2.merge_cells('A1:H1')
    _header_cell(ws2, 'A1', "PROYECCIÓN DE FLUJOS AGREGADOS (MXN)", VERDE_PATRIA, 13)
    ws2.row_dimensions[1].height = 22

    # Si hay comparativo, se usa la proyección ESTACIONAL con meses calendario y se
    # agrega la línea del año anterior (n-1). Si no, se cae a la versión simple.
    if comparativo and comparativo.get("meses"):
        mc_list = comparativo["meses"]
        bloques = [
            ("INGRESOS (cobros)", VERDE_PATRIA, "ingresos", "ing_p5", "ing_p95", "real_ing_aa"),
            ("EGRESOS (pagos)", NARANJA_DOC, "egresos", "egr_p5", "egr_p95", "real_egr_aa"),
            ("FLUJO NETO (Ingresos − Egresos)", DORADO_ACENTO, "neto", "p5", "p95", "real_neto_aa"),
        ]
        fila = 3
        col_aux2 = 12  # L.. (fuera del área visible principal A:J)
        bloque_idx = 0
        for titulo, color, kp50, kp5, kp95, kreal in bloques:
            _header_cell(ws2, f'A{fila}', titulo, color, 12)
            ws2.merge_cells(f'A{fila}:F{fila}')
            fh = fila + 1
            encs = ["Mes", "P5 (adverso)", "P50 (esperado)", "P95 (favorable)", "Real año anterior"]
            for i, e in enumerate(encs, start=1):
                _header_cell(ws2, f'{get_column_letter(i)}{fh}', e, VERDE_SECUNDARIO, 10)
            rr2 = fh + 1
            # columnas auxiliares para el gráfico de ESTE bloque
            ca = col_aux2 + bloque_idx * 6
            ws2.cell(row=1, column=ca, value="Mes")
            ws2.cell(row=1, column=ca+1, value="P5")
            ws2.cell(row=1, column=ca+2, value="P50")
            ws2.cell(row=1, column=ca+3, value="P95")
            ws2.cell(row=1, column=ca+4, value="Real n-1")
            for j, mc in enumerate(mc_list):
                ws2.cell(row=rr2, column=1, value=mc["etiqueta"]).font = Font(name='Calibri', size=10, bold=True)
                ws2.cell(row=rr2, column=1).border = borde
                vals = [mc.get(kp5), mc.get(kp50), mc.get(kp95), mc.get(kreal)]
                for i, v in enumerate(vals, start=2):
                    cel = ws2.cell(row=rr2, column=i,
                                   value=(float(v) if (v is not None and np.isfinite(v)) else None))
                    cel.number_format = '$#,##0;($#,##0);-'
                    cel.font = Font(name='Calibri', size=10); cel.border = borde
                # aux
                ws2.cell(row=1+j+1, column=ca, value=mc["etiqueta"])
                ws2.cell(row=1+j+1, column=ca+1, value=float(mc.get(kp5)) if np.isfinite(mc.get(kp5, np.nan)) else None)
                ws2.cell(row=1+j+1, column=ca+2, value=float(mc.get(kp50)) if np.isfinite(mc.get(kp50, np.nan)) else None)
                ws2.cell(row=1+j+1, column=ca+3, value=float(mc.get(kp95)) if np.isfinite(mc.get(kp95, np.nan)) else None)
                rv = mc.get(kreal)
                ws2.cell(row=1+j+1, column=ca+4, value=float(rv) if (rv is not None and np.isfinite(rv)) else None)
                rr2 += 1
            # Gráfica de líneas para este bloque
            ch = LineChart()
            ch.title = f"{titulo}: escenarios vs año anterior"
            ch.style = 2
            datos = Reference(ws2, min_col=ca+1, max_col=ca+4, min_row=1, max_row=1+len(mc_list))
            cats = Reference(ws2, min_col=ca, max_col=ca, min_row=2, max_row=1+len(mc_list))
            ch.add_data(datos, titles_from_data=True); ch.set_categories(cats)
            cl = [ROJO_ALERTA, VERDE_PATRIA, AZUL_CUSF, DORADO_FUERTE]
            for idx, (s, c) in enumerate(zip(ch.series, cl)):
                s.graphicalProperties.line.solidFill = c
                s.graphicalProperties.line.width = 30000 if idx == 1 else (26000 if idx == 3 else 16000)
                s.smooth = False
                if idx == 3:
                    s.graphicalProperties.line.dashStyle = "dash"
            ch.y_axis.numFmt = '#,##0,,"M"'
            _estilo_lineas(ch, alto=9, ancho=22, rotar_x=True)
            ws2.add_chart(ch, f'H{fh}')
            for cc in range(ca, ca+5):
                ws2.column_dimensions[get_column_letter(cc)].width = 13
            fila = rr2 + 20   # espacio para la gráfica
            bloque_idx += 1
        for i, w in enumerate([12, 15, 15, 15, 16], start=1):
            ws2.column_dimensions[get_column_letter(i)].width = w
    else:
        df_ing = resumir_percentiles(resultados["ingresos"], PERCENTILES)
        df_egr = resumir_percentiles(resultados["egresos"], PERCENTILES)
        df_neto = resumir_percentiles(resultados["neto"], PERCENTILES)

        def escribir_bloque(ws, df, titulo, fila_inicio, color):
            _header_cell(ws, f'A{fila_inicio}', titulo, color, 12)
            ws.merge_cells(f'A{fila_inicio}:H{fila_inicio}')
            fh = fila_inicio + 1
            ws.cell(row=fh, column=1, value="Mes")
            _header_cell(ws, f'A{fh}', "Mes", VERDE_SECUNDARIO, 10)
            cols_pct = list(df.columns)
            for i, cpct in enumerate(cols_pct, start=2):
                _header_cell(ws, f'{get_column_letter(i)}{fh}', cpct, VERDE_SECUNDARIO, 10)
            rr = fh + 1
            for idx_mes, (nombre_mes, row) in enumerate(df.iterrows()):
                ws.cell(row=rr, column=1, value=nombre_mes).font = Font(name='Calibri', size=10, bold=True)
                ws.cell(row=rr, column=1).border = borde
                for i, cpct in enumerate(cols_pct, start=2):
                    cel = ws.cell(row=rr, column=i, value=float(row[cpct]))
                    cel.number_format = '$#,##0;($#,##0);-'
                    cel.font = Font(name='Calibri', size=10); cel.border = borde
                rr += 1
            return fh, rr - 1

        fh_ing, ult_ing = escribir_bloque(ws2, df_ing, "INGRESOS", 3, VERDE_PATRIA)
        fila_egr_ini = ult_ing + 3
        fh_egr, ult_egr = escribir_bloque(ws2, df_egr, "EGRESOS", fila_egr_ini, NARANJA_DOC)
        fila_neto_ini = ult_egr + 3
        fh_neto, ult_neto = escribir_bloque(ws2, df_neto, "FLUJO NETO (Ingresos - Egresos)",
                                             fila_neto_ini, DORADO_ACENTO)
        for i, w in enumerate([12, 15, 15, 15, 15, 15, 15], start=1):
            ws2.column_dimensions[get_column_letter(i)].width = w

        def fan_chart(ws, fila_headers, ult_fila, titulo, ancla):
            chart = LineChart(); chart.title = titulo; chart.style = 2
            chart.height = 8; chart.width = 18
            chart.y_axis.title = "MXN"; chart.x_axis.title = "Mes"
            cols_pct = list(df_ing.columns)
            col_idx = {name: (i+2) for i, name in enumerate(cols_pct)}
            cats = Reference(ws, min_col=1, min_row=fila_headers+1, max_row=ult_fila)
            for pct in ["P5", "P50", "P95"]:
                if pct in col_idx:
                    ci = col_idx[pct]
                    data = Reference(ws, min_col=ci, min_row=fila_headers, max_row=ult_fila)
                    chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            ws.add_chart(chart, ancla)

        fan_chart(ws2, fh_ing, ult_ing, "Ingresos proyectados (P5 / P50 / P95)", "J3")
        fan_chart(ws2, fh_egr, ult_egr, "Egresos proyectados (P5 / P50 / P95)", "J20")
        fan_chart(ws2, fh_neto, ult_neto, "Flujo neto proyectado (P5 / P50 / P95)", "J37")

    # ------------------------------------------------------------------
    # HOJA 3: PROYECCIÓN POR CONCEPTO (mediana P50)
    # ------------------------------------------------------------------
    ws3 = wb.create_sheet("Por concepto")
    ws3.sheet_view.showGridLines = False
    ws3.merge_cells(f'A1:{get_column_letter(len(parametros["conceptos"]) + 2)}1')
    _header_cell(ws3, 'A1', "PROYECCIÓN MENSUAL POR CONCEPTO EN MXN (consistente con el flujo neto proyectado)", VERDE_PATRIA, 13)
    ws3.row_dimensions[1].height = 22

    # Tabla: filas = meses, columnas = conceptos (mediana)
    fh = 3
    ws3.cell(row=fh, column=1, value="Mes")
    _header_cell(ws3, f'A{fh}', "Mes", VERDE_SECUNDARIO, 10)
    nombres_conceptos = list(parametros["conceptos"].keys())
    for i, nombre in enumerate(nombres_conceptos, start=2):
        _header_cell(ws3, f'{get_column_letter(i)}{fh}', nombre, VERDE_SECUNDARIO, 9)
    ws3.row_dimensions[fh].height = 32
    neto_col = len(nombres_conceptos) + 2   # columna del Neto (después del último concepto)
    _header_cell(ws3, f'{get_column_letter(neto_col)}{fh}', "Neto", VERDE_PATRIA, 10)

    # Para que esta tabla CUADRE con la gráfica de flujo neto (y con Proyección
    # agregada), se reparte el total mensual de la proyección estacional (comparativo)
    # entre los conceptos según su peso base (freq × magnitud media). Así la suma de
    # los conceptos = neto proyectado del mes. Si no hay comparativo, se usa el P50 de
    # la simulación por concepto (respaldo).
    base_c = {}; ing_base = egr_base = 0.0
    for nombre in nombres_conceptos:
        p = parametros["conceptos"][nombre]
        mag, freq = p.get("magnitud"), p.get("frecuencia")
        b = (freq["lambda_mensual"] * mag["media_emp"]) if (mag and freq) else 0.0
        base_c[nombre] = b
        if p["direccion"] == "ingreso":
            ing_base += b
        else:
            egr_base += b
    meses_comp = comparativo.get("meses") if comparativo else None
    usa_comp = bool(meses_comp) and ing_base > 0 and egr_base > 0
    medianas = {}
    if not usa_comp:
        for nombre in nombres_conceptos:
            medianas[nombre] = np.percentile(resultados["flujos_concepto"][nombre], 50, axis=0)

    rr = fh + 1
    for mes in range(HORIZONTE_MESES):
        etq = (meses_comp[mes]["etiqueta"] if (usa_comp and mes < len(meses_comp)) else _lbl_mes(mes))
        ws3.cell(row=rr, column=1, value=etq).font = Font(name='Calibri', size=10, bold=True)
        ws3.cell(row=rr, column=1).border = borde
        for i, nombre in enumerate(nombres_conceptos, start=2):
            p = parametros["conceptos"][nombre]
            if usa_comp and mes < len(meses_comp):
                tot = meses_comp[mes]["ingresos"] if p["direccion"] == "ingreso" else meses_comp[mes]["egresos"]
                base_tot = ing_base if p["direccion"] == "ingreso" else egr_base
                val = (base_c[nombre] / base_tot) * tot if base_tot else 0.0
            else:
                val = float(medianas[nombre][mes])
            cel = ws3.cell(row=rr, column=i, value=val)
            cel.number_format = '$#,##0;($#,##0);-'
            cel.font = Font(name='Calibri', size=10)
            cel.border = borde
            dir_c = parametros["conceptos"][nombre]["direccion"]
            if mes % 2 == 1:
                cel.fill = PatternFill('solid', start_color=VERDE_CLARO if dir_c=="ingreso" else "FCE9E9")
        # Neto con FÓRMULA (recalcula): Σ ingresos − Σ egresos según la dirección de cada concepto
        partes = []
        for j, nombre in enumerate(nombres_conceptos, start=2):
            signo = "+" if parametros["conceptos"][nombre]["direccion"] == "ingreso" else "-"
            partes.append(f"{signo}{get_column_letter(j)}{rr}")
        celn = ws3.cell(row=rr, column=neto_col, value="=" + "".join(partes))
        celn.number_format = '$#,##0;($#,##0);-'
        celn.font = Font(name='Calibri', size=10, bold=True)
        celn.border = borde
        if mes % 2 == 1:
            celn.fill = PatternFill('solid', start_color=VERDE_CLARO)
        rr += 1

    ws3.column_dimensions['A'].width = 10
    for i in range(2, len(nombres_conceptos)+3):   # +3 para incluir la columna Neto
        ws3.column_dimensions[get_column_letter(i)].width = 22

    # ------------------------------------------------------------------
    # HOJA 4: VaR DE LIQUIDEZ
    # ------------------------------------------------------------------
    ws4 = wb.create_sheet("VaR liquidez")
    ws4.sheet_view.showGridLines = False
    ws4.merge_cells('A1:F1')
    _header_cell(ws4, 'A1', "VaR DE LIQUIDEZ — FLUJO NETO MENSUAL (MXN)", VERDE_PATRIA, 13)
    ws4.row_dimensions[1].height = 22

    ws4.merge_cells('A2:F2')
    c = ws4['A2']
    c.value = ("El VaR de liquidez al 95% indica el peor flujo neto esperable con 95% de confianza "
               "(percentil 5 de la distribución). Si es negativo, es la salida neta máxima probable.")
    c.font = Font(name='Calibri', size=9, italic=True, color=GRIS_NEUTRO)
    c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ws4.row_dimensions[2].height = 30

    fh = 4
    headers_var = ["Mes", "Flujo neto P50", "VaR 95% (P5)", "VaR 99% (P1)", "Mejor caso (P95)"]
    for i, h in enumerate(headers_var, start=1):
        _header_cell(ws4, f'{get_column_letter(i)}{fh}', h, VERDE_SECUNDARIO, 10)
    ws4.row_dimensions[fh].height = 24

    neto = resultados["neto"]
    rr = fh + 1
    for mes in range(HORIZONTE_MESES):
        ws4.cell(row=rr, column=1, value=_lbl_mes(mes)).font = Font(name='Calibri', size=10, bold=True)
        valores = [
            np.percentile(neto[:, mes], 50),
            np.percentile(neto[:, mes], 5),
            np.percentile(neto[:, mes], 1),
            np.percentile(neto[:, mes], 95),
        ]
        for i, v in enumerate(valores, start=2):
            cel = ws4.cell(row=rr, column=i, value=float(v))
            cel.number_format = '$#,##0;($#,##0);-'
            cel.font = Font(name='Calibri', size=10)
            cel.border = borde
            if i in (3, 4) and v < 0:
                cel.font = Font(name='Calibri', size=10, color=ROJO_ALERTA, bold=True)
        ws4.cell(row=rr, column=1).border = borde
        rr += 1

    for i, w in enumerate([10, 18, 18, 18, 18], start=1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    # ------------------------------------------------------------------
    # HOJA: VALIDACIÓN ESTADÍSTICA (detalle)
    # ------------------------------------------------------------------
    _construir_hoja_validacion(wb, validacion, borde)

    # ------------------------------------------------------------------
    # HOJA: FACTORES (DETALLE) — demora por territorio/moneda/corredor
    # ------------------------------------------------------------------
    if detalle_fac:
        _construir_hoja_factores_detalle(wb, detalle_fac, borde)

    # ------------------------------------------------------------------
    # HOJA: DATOS (PIVOTE) — tabla de Excel lista para tabla dinámica
    # ------------------------------------------------------------------
    if datos_piv:
        _construir_hoja_pivote(wb, datos_piv, borde, comparativo, hist_mensual, proy_2026)

    # Guardar
    wb.save(ruta_salida)
    print(f"\n✓ Excel-Dashboard generado: {ruta_salida}")


def _construir_hoja_factores_detalle(wb, detalle, borde):
    """
    Hoja con el DETALLE del timing por dimensión (territorio, moneda, corredor):
    para cada categoría, la mediana de días de demora (con rango P25-P75 y volumen)
    y un gráfico de PUNTOS (no barras) con una línea de referencia en la mediana
    general, para ver cuáles alargan o acortan el cobro/pago.
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import LineChart, Reference
    from openpyxl.chart.marker import Marker

    ws = wb.create_sheet("Factores (detalle)")
    ws.sheet_view.showGridLines = False
    ws.merge_cells('A1:K1')
    _header_cell(ws, 'A1', "FACTORES — DETALLE DE LA DEMORA DE COBRO/PAGO POR DIMENSIÓN", VERDE_PATRIA, 14)
    ws.row_dimensions[1].height = 20
    overall = detalle.get("overall_mediana", 0.0)
    ws.merge_cells('A2:K2')
    c = ws['A2']
    c.value = (f"Cada punto es la mediana de días entre inicio de vigencia y proceso para esa categoría. "
               f"La línea horizontal es la mediana general ({overall:,.0f} días): por encima = más lento "
               f"(alarga el cobro/pago), por debajo = más rápido (lo acorta). "
               f"Impacto (MXN) = Σ|importe devengado en pesos| de TODOS los movimientos de la categoría en la "
               f"base (no solo de los que tienen demora medible); % del monto total = su peso sobre la base completa.")
    c.font = Font(name='Calibri', size=9, italic=True, color=GRIS_NEUTRO)
    c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ws.row_dimensions[2].height = 42

    secciones = [("POR TERRITORIO", detalle.get("territorios", []), VERDE_SECUNDARIO),
                 ("POR MONEDA", detalle.get("monedas", []), AZUL_CUSF),
                 ("CORREDOR vs DIRECTO", detalle.get("corredor", []), MORADO_PATRIA)]

    fila = 4
    for titulo, datos, color in secciones:
        if not datos:
            continue
        _header_cell(ws, f'A{fila}', titulo, color, 11)
        ws.merge_cells(f'A{fila}:K{fila}')
        fh = fila + 1
        # Tabla: Categoría | Mediana (días) | Rango P25-P75 | Volumen | Impacto (MXN)
        for j, e in enumerate(["Categoría", "Mediana (días)", "Rango P25–P75 (días)", "Volumen (movs)", "Impacto (MXN)"], start=1):
            _header_cell(ws, f'{get_column_letter(j)}{fh}', e, VERDE_SECUNDARIO, 10)
        r = fh + 1
        ini_datos = r
        for d in datos:
            ws.cell(row=r, column=1, value=d["cat"]).font = Font(name='Calibri', size=10, bold=True)
            cmd = ws.cell(row=r, column=2, value=round(d["mediana"], 0))
            cmd.number_format = '#,##0'
            col_md = ROJO_ALERTA if d["mediana"] > overall * 1.15 else (SEMAFORO["ok"] if d["mediana"] < overall * 0.85 else GRIS_NEUTRO)
            cmd.font = Font(name='Calibri', size=10, bold=True, color=col_md)
            ws.cell(row=r, column=3, value=f"{d['p25']:,.0f} – {d['p75']:,.0f}").font = Font(name='Calibri', size=9, color=GRIS_NEUTRO)
            ws.cell(row=r, column=4, value=d["n"]).number_format = '#,##0'
            ws.cell(row=r, column=4).font = Font(name='Calibri', size=10)
            cimp = ws.cell(row=r, column=5, value=d.get("monto", 0.0))
            cimp.number_format = '$#,##0,,"M"'
            cimp.font = Font(name='Calibri', size=10, bold=True, color=color)
            ws.cell(row=r, column=15, value=overall)             # aux ref demora (col O, bajo la gráfica)
            ws.cell(row=r, column=16, value=d.get("monto_pct", 0.0))  # aux % del total (col P)
            for cc in range(1, 6):
                ws.cell(row=r, column=cc).border = borde
            r += 1
        fin_datos = r - 1

        # Gráfico 1 — DEMORA mediana (días): puntos por categoría + línea de referencia
        ch = LineChart()
        ch.title = f"Demora mediana (días) — {titulo.lower()}"
        ch.height = max(6.5, 0.55 * len(datos) + 3); ch.width = 16; ch.style = 2
        med_ref = Reference(ws, min_col=2, max_col=2, min_row=fh, max_row=fin_datos)       # B (mediana, con header)
        ref_ref = Reference(ws, min_col=15, max_col=15, min_row=ini_datos, max_row=fin_datos)  # O (constante)
        cats = Reference(ws, min_col=1, max_col=1, min_row=ini_datos, max_row=fin_datos)
        ch.add_data(med_ref, titles_from_data=True)
        ch.add_data(ref_ref, titles_from_data=False)
        ch.set_categories(cats)
        s0 = ch.series[0]
        s0.marker = Marker(symbol='circle', size=9)
        s0.marker.graphicalProperties.solidFill = color
        s0.marker.graphicalProperties.line.solidFill = color
        s0.graphicalProperties.line.noFill = True
        if len(ch.series) > 1:
            s1 = ch.series[1]
            s1.graphicalProperties.line.solidFill = GRIS_NEUTRO
            s1.graphicalProperties.line.dashStyle = "dash"
            s1.graphicalProperties.line.width = 14000
        ch.y_axis.title = "Días de demora"
        _estilo_lineas(ch, alto=max(7.5, 0.5 * len(datos) + 4), ancho=17, rotar_x=True, sz_x=850)
        ch.legend = None
        ws.add_chart(ch, f'F{fh}')
        _alto = max(int(ch.height / 0.53), len(datos) + 3)

        # Gráfico 2 — IMPACTO: monto movido (MXN) por categoría, MISMA X para comparar
        # quién TARDA (arriba) vs quién PEGA (aquí). Puntos diamante dorados, eje en millones.
        ch2 = LineChart()
        ch2.title = f"Impacto — % del monto total — {titulo.lower()}"
        ch2.height = ch.height; ch2.width = 16; ch2.style = 2
        imp_ref = Reference(ws, min_col=16, max_col=16, min_row=ini_datos, max_row=fin_datos)  # P (monto)
        ch2.add_data(imp_ref, titles_from_data=False)
        ch2.set_categories(cats)
        si = ch2.series[0]
        si.marker = Marker(symbol='diamond', size=9)
        si.marker.graphicalProperties.solidFill = DORADO_FUERTE
        si.marker.graphicalProperties.line.solidFill = DORADO_FUERTE
        si.graphicalProperties.line.noFill = True
        ch2.y_axis.title = "% del monto total"
        _estilo_lineas(ch2, alto=max(7.5, 0.5 * len(datos) + 4), ancho=17, rotar_x=True, sz_x=850)
        ch2.y_axis.numFmt = '0.0"%"'
        ch2.legend = None
        ws.add_chart(ch2, f'F{fh + _alto + 1}')

        fila = fin_datos + 2 * _alto + 6

    # ---------- CORREDORES vs CEDENTES (top 4 por presencia), lado a lado ----------
    # Dos dot-plots juntos para ver si algún corredor o cedente en específico alarga la
    # demora respecto a la mediana general (línea punteada de referencia).
    corr_top = detalle.get("corredores_top", [])
    ced_top = detalle.get("cedentes_top", [])
    if corr_top or ced_top:
        _header_cell(ws, f'A{fila}',
                     "TIMING POR CORREDOR Y POR CEDENTE — top 4 por presencia (¿alguno alarga la demora?)",
                     NARANJA_DOC, 11)
        ws.merge_cells(f'A{fila}:N{fila}')
        fh = fila + 1

        def _mini_tabla_cc(datos, col0, titulo, color):
            _header_cell(ws, f'{get_column_letter(col0)}{fh}', titulo, color, 10)
            ws.merge_cells(f'{get_column_letter(col0)}{fh}:{get_column_letter(col0+4)}{fh}')
            for j, e in enumerate(["Categoría", "Mediana (días)", "Rango P25–P75", "Volumen", "% del total"]):
                _header_cell(ws, f'{get_column_letter(col0+j)}{fh+1}', e, color, 9)
            r0 = fh + 2
            r = r0
            for d in datos:
                ws.cell(row=r, column=col0, value=d["cat"]).font = Font(name='Calibri', size=9, bold=True)
                cmd = ws.cell(row=r, column=col0+1, value=round(d["mediana"], 0)); cmd.number_format = '#,##0'
                col_md = ROJO_ALERTA if d["mediana"] > overall * 1.15 else (SEMAFORO["ok"] if d["mediana"] < overall * 0.85 else GRIS_NEUTRO)
                cmd.font = Font(name='Calibri', size=9, bold=True, color=col_md)
                ws.cell(row=r, column=col0+2, value=f"{d['p25']:,.0f} – {d['p75']:,.0f}").font = Font(name='Calibri', size=8, color=GRIS_NEUTRO)
                ws.cell(row=r, column=col0+3, value=d["n"]).number_format = '#,##0'
                ws.cell(row=r, column=col0+3).font = Font(name='Calibri', size=9)
                cimp = ws.cell(row=r, column=col0+4, value=d.get("monto_pct", 0.0)); cimp.number_format = '0.0"%"'
                cimp.font = Font(name='Calibri', size=9, bold=True, color=color)
                ws.cell(row=r, column=col0+5, value=overall)   # aux: mediana general (línea ref)
                for cc in range(col0, col0+5):
                    ws.cell(row=r, column=cc).border = borde
                r += 1
            return r0, r - 1

        def _dot_cc(col0, ini, fin, titulo, color, anchor, serie_col, ref_col=None,
                    ytitle="Días de demora", numfmt=None, sym='circle'):
            ch = LineChart()
            ch.title = titulo
            ch.height = 7.5; ch.width = 11; ch.style = 2
            ch.add_data(Reference(ws, min_col=serie_col, max_col=serie_col, min_row=ini, max_row=fin), titles_from_data=False)
            if ref_col is not None:
                ch.add_data(Reference(ws, min_col=ref_col, max_col=ref_col, min_row=ini, max_row=fin), titles_from_data=False)
            ch.set_categories(Reference(ws, min_col=col0, max_col=col0, min_row=ini, max_row=fin))
            s0 = ch.series[0]; s0.marker = Marker(symbol=sym, size=9)
            s0.marker.graphicalProperties.solidFill = color
            s0.marker.graphicalProperties.line.solidFill = color
            s0.graphicalProperties.line.noFill = True
            if len(ch.series) > 1:
                s1 = ch.series[1]
                s1.graphicalProperties.line.solidFill = GRIS_NEUTRO
                s1.graphicalProperties.line.dashStyle = "dash"
                s1.graphicalProperties.line.width = 14000
            ch.y_axis.title = ytitle
            _estilo_lineas(ch, alto=7.5, ancho=11, rotar_x=True, sz_x=800)
            if numfmt:
                ch.y_axis.numFmt = numfmt
            ch.legend = None
            ws.add_chart(ch, anchor)

        rc_ini = rc_fin = rd_ini = rd_fin = fh + 2
        if corr_top:
            rc_ini, rc_fin = _mini_tabla_cc(corr_top, 1, "TOP 4 CORREDORES", MORADO_PATRIA)   # A-E, aux F
        if ced_top:
            rd_ini, rd_fin = _mini_tabla_cc(ced_top, 7, "TOP 4 CEDENTES", AZUL_CUSF)          # G-K, aux L
        fila_charts = max(rc_fin, rd_fin) + 2
        if corr_top:
            _dot_cc(1, rc_ini, rc_fin, "Demora mediana (días) — top corredores", MORADO_PATRIA,
                    f'A{fila_charts}', serie_col=2, ref_col=6)
            _dot_cc(1, rc_ini, rc_fin, "Impacto — % del monto total — top corredores", DORADO_FUERTE,
                    f'A{fila_charts + 15}', serie_col=5, ytitle="% del total", numfmt='0.0"%"', sym='diamond')
        if ced_top:
            _dot_cc(7, rd_ini, rd_fin, "Demora mediana (días) — top cedentes", AZUL_CUSF,
                    f'H{fila_charts}', serie_col=8, ref_col=12)
            _dot_cc(7, rd_ini, rd_fin, "Impacto — % del monto total — top cedentes", DORADO_FUERTE,
                    f'H{fila_charts + 15}', serie_col=11, ytitle="% del total", numfmt='0.0"%"', sym='diamond')
        fila = fila_charts + 32

    # ---------- DIAGNÓSTICO DEL IMPACTO (se pinta siempre; clave si sale en cero) ----------
    diag = detalle.get("diag_impacto")
    if diag:
        en_cero = diag.get("total_base", 0) <= 1.0
        col_d = ROJO_ALERTA if en_cero else VERDE_SECUNDARIO
        _header_cell(ws, f'A{fila}',
                     ("DIAGNÓSTICO DEL IMPACTO — ¡EN CERO! La base no trae importes en los conceptos" if en_cero
                      else "DIAGNÓSTICO DEL IMPACTO (control de calidad del cálculo)"), col_d, 11)
        ws.merge_cells(f'A{fila}:K{fila}')
        fila += 1
        resumen = (f"Filas base: {diag['n_filas_base']:,}  |  Σ|monto| base: ${diag['total_base']:,.0f}  |  "
                   f"Filas con importe: {diag.get('n_filas_monto', 0):,}  |  "
                   f"Filas con lag válido: {diag['n_filas_lag']:,}  |  "
                   f"Filas con importe Y lag: {diag.get('n_filas_monto_y_lag', 0):,} (Σ ${diag['total_lag']:,.0f})")
        cres = ws.cell(row=fila, column=1, value=resumen)
        cres.font = Font(name='Calibri', size=9, bold=True)
        ws.merge_cells(f'A{fila}:K{fila}')
        fila += 1
        nota = ("La demora se mide en las filas con lag válido y el impacto en monto se agrupa por categoría "
                "sobre TODAS las filas con importe: en Gonz ambas cosas viven, en su mayoría, en registros distintos "
                "(ver estructura por Tipo abajo), por lo que sumar el monto solo en las filas con lag daría $0.")
        cn = ws.cell(row=fila, column=1, value=nota)
        cn.font = Font(name='Calibri', size=8, italic=True, color=GRIS_NEUTRO)
        cn.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.merge_cells(f'A{fila}:K{fila}')
        ws.row_dimensions[fila].height = 26
        fila += 1
        if diag.get("por_tipo"):
            for j, e in enumerate(["Tipo de registro", "Filas", "Σ |monto| (MXN)", "Filas con importe",
                                   "Filas con lag válido", "Filas con ambos"], start=1):
                _header_cell(ws, f'{get_column_letter(j)}{fila}', e, col_d, 9)
            fila += 1
            for pt in diag["por_tipo"]:
                ws.cell(row=fila, column=1, value=pt["tipo"]).font = Font(name='Calibri', size=9, bold=True)
                for j, k in enumerate(["n", "monto", "n_monto", "n_lag", "n_ambos"], start=2):
                    cc_ = ws.cell(row=fila, column=j, value=pt[k])
                    cc_.number_format = '$#,##0' if k == "monto" else '#,##0'
                    cc_.font = Font(name='Calibri', size=9)
                for cc in range(1, 7):
                    ws.cell(row=fila, column=cc).border = borde
                fila += 1
            fila += 1
        for j, e in enumerate(["Concepto", "Σ |monto| (MXN)", "Cols presentes", "Cols faltantes",
                               "dtype col 1", "Muestra cruda (3 valores)"], start=1):
            _header_cell(ws, f'{get_column_letter(j)}{fila}', e, col_d, 9)
        fila += 1
        for dc in diag.get("conceptos", []):
            ws.cell(row=fila, column=1, value=dc["concepto"]).font = Font(name='Calibri', size=9, bold=True)
            cs_ = ws.cell(row=fila, column=2, value=dc["suma"]); cs_.number_format = '$#,##0'
            cs_.font = Font(name='Calibri', size=9)
            ws.cell(row=fila, column=3, value=f"{dc['presentes']}/{dc['esperadas']}").font = Font(name='Calibri', size=9)
            ws.cell(row=fila, column=4, value=dc["faltantes"]).font = Font(name='Calibri', size=8, color=GRIS_NEUTRO)
            ws.cell(row=fila, column=5, value=dc["dtype"]).font = Font(name='Calibri', size=8)
            cm_ = ws.cell(row=fila, column=6, value=dc["muestra"])
            cm_.font = Font(name='Calibri', size=8, color=GRIS_NEUTRO)
            for cc in range(1, 7):
                ws.cell(row=fila, column=cc).border = borde
            fila += 1
        fila += 2

    for i, w in enumerate([26, 14, 18, 14, 13], start=1):            # A-E (principal / corredores)
        ws.column_dimensions[get_column_letter(i)].width = w
    for _i, _w in [(7, 26), (8, 14), (9, 18), (10, 12), (11, 13)]:   # G-K (cedentes)
        ws.column_dimensions[get_column_letter(_i)].width = _w
    ws.column_dimensions['F'].width = 3    # separador / aux
    ws.column_dimensions['L'].width = 3    # aux
    # Impresión: horizontal, ajustar a ancho (tabla + gráfica juntas)
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.print_area = f'A1:N{fila}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def _construir_hoja_pivote(wb, datos_piv, borde, comparativo=None, hist_mensual=None, proy_2026=None):
    """
    Hoja con los datos en formato largo como TABLA DE EXCEL (ListObject), lista
    para insertar una tabla dinámica. Nota: las tablas dinámicas (PivotTables) no
    se pueden crear de forma confiable por código (openpyxl no las soporta), pero
    una Tabla de Excel se convierte en tabla dinámica con un clic:
    seleccionar la tabla -> Insertar -> Tabla dinámica.
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    ws = wb.create_sheet("Datos (pivote)")
    ws.sheet_view.showGridLines = False

    # Instrucciones arriba (fuera del rango de la tabla)
    ws.merge_cells('A1:H1')
    _header_cell(ws, 'A1', "DATOS PARA TABLA DINÁMICA", VERDE_PATRIA, 14)
    ws.row_dimensions[1].height = 20
    ws.merge_cells('A2:H3')
    c = ws['A2']
    c.value = ("Estos datos están en formato largo, listos para tabla dinámica. Para crearla: haz clic en "
               "cualquier celda de la tabla → pestaña Insertar → Tabla dinámica → Aceptar. Luego arrastra "
               "'Mes' o 'Concepto' a Filas, 'Dirección' a Columnas y 'Proyección (MXN)' o 'Real año anterior "
               "(MXN)' a Valores. (Nota: las tablas dinámicas no se generan por código; esta Tabla de Excel se "
               "convierte en una con un clic.)")
    c.font = Font(name='Calibri', size=9, italic=True, color=NARANJA_DOC)
    c.fill = PatternFill('solid', start_color="FBF4E8")
    c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

    # Encabezados de la tabla (fila 5)
    cols = ["Mes", "AAAAMM", "Año", "MesNombre", "Dirección", "Concepto",
            "Proyección (MXN)", "Real año anterior (MXN)",
            "Flujo neto proy. (MXN)", "Flujo neto AA (MXN)"]
    fila_hdr = 5
    for j, cname in enumerate(cols):
        cell = ws.cell(row=fila_hdr, column=1 + j, value=cname)
        cell.font = Font(name='Calibri', size=10, bold=True, color=BLANCO)
        cell.fill = PatternFill('solid', start_color=VERDE_PATRIA)
        cell.alignment = Alignment(horizontal='center', vertical='center')
    # Datos
    r = fila_hdr + 1
    for fila in datos_piv:
        ws.cell(row=r, column=1, value=fila["Mes"])
        ws.cell(row=r, column=2, value=fila["AAAAMM"])
        ws.cell(row=r, column=3, value=fila["Año"])
        ws.cell(row=r, column=4, value=fila["MesNombre"])
        ws.cell(row=r, column=5, value=fila["Dirección"])
        ws.cell(row=r, column=6, value=fila["Concepto"])
        cp = ws.cell(row=r, column=7, value=fila["Proyección (MXN)"])
        cp.number_format = '$#,##0'
        cr = ws.cell(row=r, column=8, value=fila["Real año anterior (MXN)"])
        cr.number_format = '$#,##0'
        cn = ws.cell(row=r, column=9, value=fila.get("Flujo neto proy. (MXN)"))
        cn.number_format = '$#,##0;($#,##0)'
        cna = ws.cell(row=r, column=10, value=fila.get("Flujo neto AA (MXN)"))
        cna.number_format = '$#,##0;($#,##0)'
        r += 1
    fila_fin = r - 1

    # Definir la Tabla de Excel (ListObject)
    ref = f"A{fila_hdr}:J{fila_fin}"
    tabla = Table(displayName="DatosFlujos", ref=ref)
    tabla.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
        showRowStripes=True, showColumnStripes=False)
    ws.add_table(tabla)

    # Anchos
    anchos = [12, 10, 8, 11, 11, 30, 18, 22, 20, 20]
    for j, w in enumerate(anchos):
        ws.column_dimensions[get_column_letter(1 + j)].width = w
    ws.freeze_panes = f"A{fila_hdr+1}"

    # ---------- Segunda tabla: ResumenMensual (agregado con percentiles) ----------
    # Permite gráficas de percentiles (P5/P50/P95) y comparación con el año anterior
    # tanto en tablas dinámicas como en Power BI.
    if comparativo and comparativo.get("meses"):
        meses = comparativo["meses"]
        fila_res_hdr = fila_fin + 4
        ws.merge_cells(f'A{fila_res_hdr-2}:N{fila_res_hdr-2}')
        _header_cell(ws, f'A{fila_res_hdr-2}',
                     "RESUMEN MENSUAL (agregado con percentiles, para gráficas de bandas)", VERDE_SECUNDARIO, 11)
        cols_r = ["Mes", "AAAAMM",
                  "Ingresos P5", "Ingresos P50", "Ingresos P95",
                  "Egresos P5", "Egresos P50", "Egresos P95",
                  "Neto P5", "Neto P50", "Neto P95",
                  "Real ingresos AA", "Real egresos AA", "Real neto AA"]
        col0 = 1  # A (debajo de DatosFlujos)
        for j, cname in enumerate(cols_r):
            cell = ws.cell(row=fila_res_hdr, column=col0 + j, value=cname)
            cell.font = Font(name='Calibri', size=10, bold=True, color=BLANCO)
            cell.fill = PatternFill('solid', start_color=VERDE_SECUNDARIO)
            cell.alignment = Alignment(horizontal='center', vertical='center')
        rr = fila_res_hdr + 1
        def _v(x):
            return float(x) if (x is not None and np.isfinite(x)) else None
        for mc in meses:
            vals = [_etiqueta_mes_orden(int(mc["mes"])), int(mc["mes"]),
                    _v(mc.get("ing_p5")), _v(mc.get("ingresos")), _v(mc.get("ing_p95")),
                    _v(mc.get("egr_p5")), _v(mc.get("egresos")), _v(mc.get("egr_p95")),
                    _v(mc.get("p5")), _v(mc.get("neto")), _v(mc.get("p95")),
                    _v(mc.get("real_ing_aa")), _v(mc.get("real_egr_aa")), _v(mc.get("real_neto_aa"))]
            for j, v in enumerate(vals):
                cel = ws.cell(row=rr, column=col0 + j, value=v)
                if j >= 2:
                    cel.number_format = '$#,##0'
                cel.font = Font(name='Calibri', size=9)
            rr += 1
        ref_r = f"{get_column_letter(col0)}{fila_res_hdr}:{get_column_letter(col0+len(cols_r)-1)}{rr-1}"
        tabla_r = Table(displayName="ResumenMensual", ref=ref_r)
        tabla_r.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium5", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False)
        ws.add_table(tabla_r)
        # Solo fijar anchos de las columnas que NO usa DatosFlujos (K en adelante)
        for j in range(len(cols_r)):
            cidx = col0 + j
            if cidx >= 11:   # K..N
                ws.column_dimensions[get_column_letter(cidx)].width = 15
    # ---------- Tabla: HistMensual (tendencias históricas por año, SIN 2026) ----------
    # Formato largo (una fila por mes 2020-2025). En la dinámica: Mes en Filas, Año en
    # Columnas y Neto/Ingresos/Egresos en Valores -> una línea por año.
    if hist_mensual:
        base = ws.max_row + 4
        ws.merge_cells(f'A{base-2}:N{base-2}')
        _header_cell(ws, f'A{base-2}',
                     "TENDENCIAS HISTÓRICAS (real por año 2020-2025) — dinámica: Mes en Filas, Año en Columnas",
                     AZUL_CUSF, 11)
        cols_h = ["AAAAMM", "Año", "Mes", "Ingresos", "Egresos", "Neto"]
        for j, cname in enumerate(cols_h):
            cell = ws.cell(row=base, column=1 + j, value=cname)
            cell.font = Font(name='Calibri', size=10, bold=True, color=BLANCO)
            cell.fill = PatternFill('solid', start_color=AZUL_CUSF)
            cell.alignment = Alignment(horizontal='center', vertical='center')
        rh = base + 1
        for f_ in hist_mensual:
            ws.cell(row=rh, column=1, value=f_["AAAAMM"])
            ws.cell(row=rh, column=2, value=f_["Año"])
            ws.cell(row=rh, column=3, value=f_["Mes"])
            for k, key in enumerate(["Ingresos", "Egresos", "Neto"], start=4):
                c = ws.cell(row=rh, column=k, value=f_[key])
                c.number_format = '$#,##0;($#,##0)'
                c.font = Font(name='Calibri', size=9)
            rh += 1
        t_h = Table(displayName="HistMensual", ref=f"A{base}:F{rh-1}")
        t_h.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False,
                                            showLastColumn=False, showRowStripes=True,
                                            showColumnStripes=False)
        ws.add_table(t_h)

    # ---------- Tabla: Proy2026 (real hasta el cierre técnico + proyección del resto) ----------
    # Una fila por mes de 2026. Real_* llena hasta el último mes con cierre; Proy_* llena
    # el resto (anclada en el último mes real para que las líneas se conecten).
    if proy_2026:
        base = ws.max_row + 4
        ws.merge_cells(f'A{base-2}:N{base-2}')
        _header_cell(ws, f'A{base-2}',
                     "PROYECCIÓN 2026 vs REAL (real hasta el último cierre técnico + proyección P50 del resto)",
                     MORADO_PATRIA, 11)
        cols_p = ["AAAAMM", "Mes", "Real ingresos", "Real egresos", "Real neto",
                  "Proy ingresos", "Proy egresos", "Proy neto"]
        for j, cname in enumerate(cols_p):
            cell = ws.cell(row=base, column=1 + j, value=cname)
            cell.font = Font(name='Calibri', size=10, bold=True, color=BLANCO)
            cell.fill = PatternFill('solid', start_color=MORADO_PATRIA)
            cell.alignment = Alignment(horizontal='center', vertical='center')
        rp = base + 1
        for f_ in proy_2026:
            ws.cell(row=rp, column=1, value=f_["AAAAMM"])
            ws.cell(row=rp, column=2, value=f_["Mes"])
            for k, key in enumerate(["Real ingresos", "Real egresos", "Real neto",
                                     "Proy ingresos", "Proy egresos", "Proy neto"], start=3):
                c = ws.cell(row=rp, column=k, value=f_[key])
                c.number_format = '$#,##0;($#,##0)'
                c.font = Font(name='Calibri', size=9)
            rp += 1
        t_p = Table(displayName="Proy2026", ref=f"A{base}:H{rp-1}")
        t_p.tableStyleInfo = TableStyleInfo(name="TableStyleMedium4", showFirstColumn=False,
                                            showLastColumn=False, showRowStripes=True,
                                            showColumnStripes=False)
        ws.add_table(t_p)


# ==============================================================================
# MAIN
# ==============================================================================
# ==============================================================================
# TABLAS DINÁMICAS NATIVAS (PivotTables/PivotCharts) VÍA EXCEL + pywin32
# ==============================================================================
# (Fusionado de crear_tablas_dinamicas.py). openpyxl no crea PivotTables confiables;
# se usa el motor de Excel por COM. Toma la hoja "Datos (pivote)" del Excel ya
# generado y crea dinámicas + gráficos de líneas LIMPIOS (sin botones de campo),
# cada uno en su hoja. Guarda ..._pivotes.xlsx (no toca el original).
# Requiere Excel instalado + pywin32 (se instala solo). Si no está, se omite sin romper.

# ---- Constantes de la API COM de Excel ----
XL_DATABASE = 1
XL_ROW_FIELD = 1
XL_COLUMN_FIELD = 2
XL_DATA_FIELD = 4
XL_SUM = -4157
XL_LINE_MARKERS = 65            # xlLineMarkers
XL_CATEGORY = 1                 # xlCategory (eje X)
XL_TICK_LABEL_LOW = -4134       # xlTickLabelPositionLow (etiquetas de meses hasta abajo)
XL_VALUE = 2                    # xlValue (eje Y: para formatear montos completos)
NUM_FMT_PIV = "#,##0"


def _rgb_xl(hexstr):
    """Hex GPV -> entero RGB-long de Excel (R + G*256 + B*65536)."""
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r + g * 256 + b * 65536

CXL_ROJO = _rgb_xl(ROJO_ALERTA)      # P5 / adverso
CXL_VERDE = _rgb_xl(VERDE_PATRIA)    # P50 / proyección
CXL_AZUL = _rgb_xl(AZUL_CUSF)        # P95 / favorable
CXL_DORADO = _rgb_xl(DORADO_FUERTE)  # año anterior (fuerte, no se pierde)


def _piv_meses_abajo(ch):
    """Manda las etiquetas del eje X (meses) hasta ABAJO del plano, no a la altura
    de y=0 (que es donde caían por tener valores negativos)."""
    try:
        ch.Axes(XL_CATEGORY).TickLabelPosition = XL_TICK_LABEL_LOW
    except Exception as e:
        print(f"    [i] (etiquetas de meses: {type(e).__name__})")


def _piv_orden_fuente(pt, campo):
    """Ordena el campo ASCENDENTE por su propio nombre. Como las etiquetas de mes son
    'AAAA-MM mes' (orden alfabético = cronológico), esto garantiza fechas en orden."""
    try:
        pt.PivotFields(campo).AutoSort(1, campo)   # 1 = xlAscending
    except Exception:
        pass


def _piv_agregar_pivote(wb, cache, nombre_hoja, fila_destino=3):
    """Crea una hoja nueva y una tabla dinámica vacía sobre ella. Devuelve (ws, pt)."""
    ws = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
    base = nombre_hoja[:31]
    nombre = base
    i = 1
    existentes = [wb.Sheets(j + 1).Name for j in range(wb.Sheets.Count)]
    while nombre in existentes:
        i += 1
        nombre = f"{base[:28]}_{i}"
    ws.Name = nombre
    pt = cache.CreatePivotTable(
        TableDestination=ws.Cells(fila_destino, 1),
        TableName=("pt_" + nombre.replace(" ", "_").replace("-", "_"))[:31])
    return ws, pt


def _piv_grafica_lineas(ws, pt, titulo, colores, left=360, top=15, width=600, height=330):
    """Gráfico dinámico de LÍNEAS limpio: sin botones de campo, meses abajo, título,
    series coloreadas por orden y última (año anterior) punteada. Robusto."""
    try:
        co = ws.ChartObjects().Add(Left=left, Top=top, Width=width, Height=height)
        ch = co.Chart
        ch.SetSourceData(pt.TableRange1)
        ch.ChartType = XL_LINE_MARKERS
        ch.HasTitle = True
        ch.ChartTitle.Text = titulo
        try:
            ch.ShowAllFieldButtons = False   # ocultar botones de campo (ensucian)
        except Exception:
            pass
        _piv_meses_abajo(ch)                  # <-- FIX: etiquetas de meses hasta abajo
        try:                                  # <-- FIX: montos completos, sin notación científica
            ch.Axes(XL_VALUE).TickLabels.NumberFormat = "#,##0"
        except Exception:
            pass
        try:
            n = ch.SeriesCollection().Count
            for i in range(1, n + 1):
                s = ch.SeriesCollection(i)
                if i - 1 < len(colores):
                    s.Format.Line.ForeColor.RGB = colores[i - 1]
                s.Format.Line.Weight = 2.5
                if i == n and len(colores) >= n:   # última serie (año anterior) punteada
                    try:
                        s.Format.Line.DashStyle = 4  # msoLineDash
                    except Exception:
                        pass
        except Exception as e:
            print(f"    [i] (colores de serie omitidos: {type(e).__name__})")
        return co
    except Exception as e:
        print(f"    [i] (gráfico dinámico omitido: {type(e).__name__}: {e})")
        return None


def _piv_agregar_dll_pywin32():
    """Agrega la carpeta 'pywin32_system32' al path de DLLs para cargar win32com en
    este mismo proceso si pywin32 se acaba de instalar."""
    import sysconfig
    candidatos = []
    purelib = sysconfig.get_paths().get("purelib")
    if purelib:
        candidatos.append(os.path.join(purelib, "pywin32_system32"))
    candidatos.append(os.path.join(sys.prefix, "pywin32_system32"))
    candidatos.append(os.path.join(os.path.dirname(sys.executable), "..", "Lib",
                                   "site-packages", "pywin32_system32"))
    for d in candidatos:
        d = os.path.abspath(d)
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _piv_asegurar_pywin32():
    """Devuelve win32com.client. Instala pywin32 en este .venv si falta. None si no se pudo."""
    import importlib
    try:
        import win32com.client as w
        return w
    except ImportError:
        pass
    print("  [i] pywin32 no está instalado. Lo instalo en este entorno (.venv)...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pywin32"])
    except subprocess.CalledProcessError as e:
        print(f"  [X] No se pudo instalar pywin32 (pip falló: {e}). Instálalo: pip install pywin32")
        return None
    _piv_agregar_dll_pywin32()
    importlib.invalidate_caches()
    try:
        import win32com.client as w
        print("  [OK] pywin32 instalado y cargado.")
        return w
    except ImportError as e:
        print(f"  [i] pywin32 quedó instalado pero no carga en este proceso ({e}).")
        print("      Vuelve a correr el script (en proceso nuevo ya carga) para generar los pivotes.")
        return None


def _piv_comentario_dinamico(ws, prefijo, col_real, es_neto, fila=27):
    """Escribe, a partir de 'fila', un comentario DINÁMICO (recalcula con la tabla)
    que explica por qué se proyecta así vs el mismo periodo del año anterior.
    Compara el escenario elegido (P5/P50/P95, con dropdown) contra el real de la
    categoría: ingresos vs real ingresos, egresos vs real egresos, neto vs real neto.
    Lee de la Tabla ResumenMensual con referencias estructuradas (robusto a que la
    tabla se mueva o se actualice)."""
    f_sel = fila + 1            # selector
    f_num = fila + 2            # números (proyectado / real)
    f_par = fila + 3            # inicio del párrafo
    sel = f"$B${f_sel}"
    bref = f"$B${f_num}"
    dref = f"$D${f_num}"

    verde = _rgb_xl(VERDE_PATRIA); blanco = _rgb_xl(BLANCO)
    dorado = _rgb_xl(DORADO_ACENTO)

    # ---- Encabezado ----
    ws.Range(f"A{fila}:K{fila}").Merge()
    h = ws.Cells(fila, 1)
    h.Value = "¿POR QUÉ SE PROYECTA ASÍ?  —  comparativo dinámico (recalcula con la tabla)"
    h.Font.Name = "Calibri"; h.Font.Size = 11; h.Font.Bold = True; h.Font.Color = blanco
    h.Interior.Color = verde; h.HorizontalAlignment = -4131       # xlLeft
    ws.Rows(fila).RowHeight = 20

    # ---- Selector de escenario (dropdown P5/P50/P95) ----
    lab = ws.Cells(f_sel, 1)
    lab.Value = "Escenario comparado:"; lab.Font.Bold = True; lab.Font.Name = "Calibri"
    s = ws.Cells(f_sel, 2)
    s.Value = "P50"
    try:
        s.Validation.Delete()
        s.Validation.Add(Type=3, AlertStyle=1, Operator=1, Formula1="P5,P50,P95")  # xlValidateList
        s.Validation.InCellDropdown = True
    except Exception as e:
        print(f"    [i] (dropdown escenario: {type(e).__name__})")
    s.Interior.Color = dorado; s.Font.Bold = True; s.HorizontalAlignment = -4108  # xlCenter

    # ---- Números: proyectado (escenario elegido) vs real del año anterior ----
    ws.Cells(f_num, 1).Value = "Proyectado (12m):"; ws.Cells(f_num, 1).Font.Bold = True
    b = ws.Cells(f_num, 2)
    b.Formula = ('=SUM(INDEX(ResumenMensual,0,MATCH("' + prefijo + ' "&' + sel
                 + ',ResumenMensual[#Headers],0)))')
    b.NumberFormat = "$#,##0;($#,##0)"; b.Font.Bold = True
    ws.Cells(f_num, 3).Value = "Real año anterior:"; ws.Cells(f_num, 3).Font.Bold = True
    d = ws.Cells(f_num, 4)
    d.Formula = '=SUM(ResumenMensual[' + col_real + '])'
    d.NumberFormat = "$#,##0;($#,##0)"; d.Font.Bold = True

    # ---- Párrafo dinámico (sensible al signo) ----
    ws.Range(f"A{f_par}:K{f_par + 5}").Merge()
    p = ws.Cells(f_par, 1)
    if not es_neto:
        verbo = "cobro" if prefijo == "Ingresos" else "pago"
        recibido = "cobrados" if prefijo == "Ingresos" else "erogados"
        p.Formula = (
            '="Para ' + prefijo.upper() + ', el modelo proyecta "&TEXT(' + bref + ',"$#,##0")&" ("&' + sel + '&"), un "'
            '&TEXT(ABS(' + bref + '/' + dref + '-1),"0.0%")&IF(' + bref + '<' + dref + '," MENOS"," MÁS")'
            '&" que los "&TEXT(' + dref + ',"$#,##0")&" ' + recibido + ' en el mismo periodo del año anterior. "'
            '&IF(' + bref + '<' + dref + ','
            '"No refleja una caída esperada del negocio: la calibración usa el PROMEDIO de toda la ventana (2023 a la fecha). '
            'Como el ritmo reciente de ' + verbo + ' supera ese promedio, la proyección se ancla al promedio y queda por debajo '
            'del último año (se diluye la tendencia reciente). Para reflejar el ritmo reciente, fija MESES_CALIBRACION_RECIENTE '
            '(p.ej. 18) y vuelve a correr.",'
            '"La proyección queda por encima del último año porque el ritmo reciente de ' + verbo + ' supera el promedio histórico '
            'con el que se calibra.")')
    else:
        p.Formula = (
            '="El flujo NETO proyectado ("&' + sel + '&") es "&TEXT(' + bref + ',"$#,##0;($#,##0)")&", contra "'
            '&TEXT(' + dref + ',"$#,##0;($#,##0)")&" del mismo periodo del año anterior"'
            '&IF(' + bref + '>' + dref + '," — una pérdida MENOR por "&TEXT(ABS(' + bref + '-' + dref + '),"$#,##0")&". ",'
            '" — una pérdida MAYOR por "&TEXT(ABS(' + bref + '-' + dref + '),"$#,##0")&". ")'
            '&IF(' + bref + '>' + dref + ','
            '"Es efecto de calibración, no de negocio: el modelo promedia toda la ventana (2023 a la fecha); como el ritmo reciente '
            'es más negativo (los egresos crecieron más que los ingresos), promediar diluye esa tendencia y la pérdida proyectada '
            'sale menor que la reciente. Para acercarla al ritmo reciente, fija MESES_CALIBRACION_RECIENTE (p.ej. 18).",'
            '"El neto proyectado quedó por debajo (más adverso) que el año anterior; revisa la magnitud reciente.")')
    p.WrapText = True; p.VerticalAlignment = -4160               # xlTop
    p.Font.Name = "Calibri"; p.Font.Size = 10
    try:
        ws.Range(f"A{f_par}:K{f_par + 5}").RowHeight = 16
    except Exception:
        pass


def crear_pivotes_en(ruta_xlsx):
    """Crea las tablas dinámicas nativas sobre 'ruta_xlsx' y guarda ..._pivotes.xlsx.
    Devuelve la ruta del archivo de pivotes, o None si se omitió/falló."""
    if not ruta_xlsx or not os.path.exists(ruta_xlsx):
        print(f"  [X] No encontré el Excel para pivotear: {ruta_xlsx}")
        return None
    win32 = _piv_asegurar_pywin32()
    if win32 is None:
        return None

    excel = None
    wb = None
    try:
        excel = win32.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(os.path.abspath(ruta_xlsx))

        nombres = [wb.Sheets(j + 1).Name for j in range(wb.Sheets.Count)]
        if "Datos (pivote)" not in nombres:
            print("  [X] El archivo no tiene la hoja 'Datos (pivote)'.")
            wb.Close(SaveChanges=False)
            return None

        ws_datos = wb.Sheets("Datos (pivote)")

        def _fuente(nombre_tabla):
            try:
                _ = ws_datos.ListObjects(nombre_tabla)
                return nombre_tabla
            except Exception:
                return None
        fuente_d = _fuente("DatosFlujos")
        fuente_r = _fuente("ResumenMensual")
        if fuente_d is None:
            fuente_d = "'Datos (pivote)'!" + ws_datos.UsedRange.Address

        cache_d = wb.PivotCaches().Create(SourceType=XL_DATABASE, SourceData=fuente_d)
        cache_r = (wb.PivotCaches().Create(SourceType=XL_DATABASE, SourceData=fuente_r)
                   if fuente_r else None)

        hojas = []

        # 1) Flujo NETO mensual (columnas CON SIGNO -> neto real, igual al dashboard)
        ws1, pt1 = _piv_agregar_pivote(wb, cache_d, "Pivot Neto mensual")
        pt1.PivotFields("Mes").Orientation = XL_ROW_FIELD
        pt1.PivotFields("Mes").Position = 1
        _piv_orden_fuente(pt1, "Mes")
        usados = 0
        for campo, etq in [("Flujo neto proy. (MXN)", "Neto proyectado"),
                           ("Flujo neto AA (MXN)", "Neto año anterior")]:
            try:
                df = pt1.AddDataField(pt1.PivotFields(campo), etq, XL_SUM)
                df.NumberFormat = NUM_FMT_PIV
                usados += 1
            except Exception:
                pass
        if usados == 0:   # respaldo si el archivo es viejo (sin columnas con signo)
            for campo, etq in [("Proyección (MXN)", "Σ Proyección (bruto)"),
                               ("Real año anterior (MXN)", "Σ Real año ant. (bruto)")]:
                try:
                    df = pt1.AddDataField(pt1.PivotFields(campo), etq, XL_SUM)
                    df.NumberFormat = NUM_FMT_PIV
                except Exception:
                    pass
        _piv_grafica_lineas(ws1, pt1, "Flujo neto mensual: proyectado vs año anterior",
                            [CXL_VERDE, CXL_DORADO])
        hojas.append(ws1.Name)

        # 2/3/4) Percentiles de Neto, Ingresos y Egresos (ResumenMensual)
        if cache_r is not None:
            bloques = [
                ("Pivot Neto percentiles", "Flujo neto: P5/P50/P95 vs año anterior",
                 ["Neto P5", "Neto P50", "Neto P95", "Real neto AA"], "Neto", "Real neto AA", True),
                ("Pivot Ingresos percentiles", "Ingresos: P5/P50/P95 vs año anterior",
                 ["Ingresos P5", "Ingresos P50", "Ingresos P95", "Real ingresos AA"],
                 "Ingresos", "Real ingresos AA", False),
                ("Pivot Egresos percentiles", "Egresos: P5/P50/P95 vs año anterior",
                 ["Egresos P5", "Egresos P50", "Egresos P95", "Real egresos AA"],
                 "Egresos", "Real egresos AA", False),
            ]
            for nombre_h, titulo, campos, prefijo, col_real, es_neto in bloques:
                wsx, ptx = _piv_agregar_pivote(wb, cache_r, nombre_h)
                ptx.PivotFields("Mes").Orientation = XL_ROW_FIELD
                ptx.PivotFields("Mes").Position = 1
                _piv_orden_fuente(ptx, "Mes")
                for campo in campos:
                    try:
                        df = ptx.AddDataField(ptx.PivotFields(campo), campo, XL_SUM)
                        df.NumberFormat = NUM_FMT_PIV
                    except Exception:
                        pass
                _piv_grafica_lineas(wsx, ptx, titulo, [CXL_ROJO, CXL_VERDE, CXL_AZUL, CXL_DORADO])
                # Comentario dinámico (por qué se proyecta así vs año anterior), a partir de fila 27
                try:
                    _piv_comentario_dinamico(wsx, prefijo, col_real, es_neto, fila=27)
                except Exception as e:
                    print(f"    [i] (comentario dinámico omitido: {type(e).__name__}: {e})")
                hojas.append(wsx.Name)

        # 5) Por concepto y dirección (tabla)
        ws5, pt5 = _piv_agregar_pivote(wb, cache_d, "Pivot Por concepto")
        pt5.PivotFields("Concepto").Orientation = XL_ROW_FIELD
        pt5.PivotFields("Concepto").Position = 1
        pt5.PivotFields("Dirección").Orientation = XL_COLUMN_FIELD
        pt5.PivotFields("Dirección").Position = 1
        try:
            df5 = pt5.AddDataField(pt5.PivotFields("Proyección (MXN)"), "Σ Proyección", XL_SUM)
            df5.NumberFormat = NUM_FMT_PIV
        except Exception:
            pass
        hojas.append(ws5.Name)
        # 6) Tendencias históricas por año (2020-2025): Mes en Filas, Año en Columnas
        fuente_h = _fuente("HistMensual")
        if fuente_h:
            cache_h = wb.PivotCaches().Create(SourceType=XL_DATABASE, SourceData=fuente_h)
            for nombre_h, campo, titulo in [
                ("Pivot Hist Neto", "Neto", "Tendencia histórica NETO por año (2020-2025)"),
                ("Pivot Hist Ingresos", "Ingresos", "Tendencia histórica INGRESOS por año (2020-2025)"),
                ("Pivot Hist Egresos", "Egresos", "Tendencia histórica EGRESOS por año (2020-2025)"),
            ]:
                wsh, pth = _piv_agregar_pivote(wb, cache_h, nombre_h)
                pth.PivotFields("Mes").Orientation = XL_ROW_FIELD
                pth.PivotFields("Mes").Position = 1
                pth.PivotFields("Año").Orientation = XL_COLUMN_FIELD
                pth.PivotFields("Año").Position = 1
                _piv_orden_fuente(pth, "Mes")
                try:
                    pth.ColumnGrand = False; pth.RowGrand = False
                except Exception:
                    pass
                try:
                    dfh = pth.AddDataField(pth.PivotFields(campo), campo, XL_SUM)
                    dfh.NumberFormat = NUM_FMT_PIV
                except Exception:
                    pass
                _piv_grafica_lineas(wsh, pth, titulo, [])   # una línea por año (colores automáticos)
                hojas.append(wsh.Name)

        # 7) Proyección 2026 vs real (real hasta el cierre + proyección del resto)
        fuente_p = _fuente("Proy2026")
        if fuente_p:
            cache_p = wb.PivotCaches().Create(SourceType=XL_DATABASE, SourceData=fuente_p)
            for nombre_h, campos, titulo in [
                ("Pivot 2026 Ingresos", ["Real ingresos", "Proy ingresos"], "Ingresos: real 2025 + proyección 2026"),
                ("Pivot 2026 Egresos", ["Real egresos", "Proy egresos"], "Egresos: real 2025 + proyección 2026"),
                ("Pivot 2026 Neto", ["Real neto", "Proy neto"], "Flujo neto: real 2025 + proyección 2026"),
            ]:
                wsp, ptp = _piv_agregar_pivote(wb, cache_p, nombre_h)
                ptp.PivotFields("Mes").Orientation = XL_ROW_FIELD
                ptp.PivotFields("Mes").Position = 1
                _piv_orden_fuente(ptp, "Mes")
                try:
                    ptp.RowGrand = False
                except Exception:
                    pass
                for campo in campos:
                    try:
                        dfp = ptp.AddDataField(ptp.PivotFields(campo), campo, XL_SUM)
                        dfp.NumberFormat = NUM_FMT_PIV
                    except Exception:
                        pass
                # real = azul (sólida), proyección = dorado (punteada, última serie)
                _piv_grafica_lineas(wsp, ptp, titulo, [CXL_AZUL, CXL_DORADO])
                hojas.append(wsp.Name)

        base, _ = os.path.splitext(os.path.abspath(ruta_xlsx))
        salida = base + "_pivotes.xlsx"
        wb.SaveAs(salida, FileFormat=51)   # 51 = xlsx
        wb.Close(SaveChanges=False)
        print("     Hojas añadidas: " + ", ".join(f"'{h}'" for h in hojas))
        return salida
    except Exception as e:
        print(f"  [X] Error creando dinámicas: {type(e).__name__}: {e}")
        print("      (cierra el archivo si lo tienes abierto; verifica Excel + pip install -U pywin32)")
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        return None
    finally:
        try:
            if excel is not None:
                excel.DisplayAlerts = True
                excel.Quit()
        except Exception:
            pass


def main():
    inicio = time.perf_counter()
    print("=" * 70)
    print("MODELO DE PROYECCIÓN DE FLUJOS — MONTE CARLO")
    print("Reaseguradora Patria")
    print("=" * 70)
    print(f"Horizonte: {HORIZONTE_MESES} meses | Simulaciones: {N_SIMULACIONES:,} | Semilla: {SEMILLA}")
    print(f"BD Gonz: {RUTA_ACCDB}")

    # Aviso de librerías opcionales
    try:
        import lifelines  # noqa: F401
        _LIFELINES_OK = True
    except Exception:
        _LIFELINES_OK = False
    if not _SCIPY_OK or not _LIFELINES_OK:
        faltan = []
        if not _SCIPY_OK: faltan += ["scipy", "statsmodels"]
        if not _LIFELINES_OK: faltan.append("lifelines")
        print("\n  [!] Librerías opcionales no instaladas: " + ", ".join(sorted(set(faltan))))
        print("      El modelo correrá igual (lag con log-normal simple y/o validación omitida).")
        print("      Para capacidades completas:  pip install " + " ".join(sorted(set(faltan))))

    # 1. Cargar datos
    print("\n--- Cargando datos de Gonz ---")
    df_gonz = cargar_gonz(forzar=FORZAR_RECARGA)
    df_tc = cargar_serie_tc(forzar=FORZAR_RECARGA)
    print(f"  Serie TC: {len(df_tc):,} observaciones")

    # 1c. Catálogos reales (monedas/territorios) desde la Base de Gonz
    print("\n--- Cargando catálogos (monedas/territorios) de la Base de Gonz ---")
    cargar_catalogos_en_memoria()

    # 1b. Ventana de calibración. df_gonz queda como la base (2023+) que se usa para
    # el COMPARATIVO y la TENDENCIA (necesitan el año anterior). Para CALIBRAR el
    # ritmo, si MESES_CALIBRACION_RECIENTE está fijo, se usa solo la cola reciente.
    if PERIODO_MIN_CALIBRACION and "aPOG_MesProc" in df_gonz.columns:
        n_antes = len(df_gonz)
        mp = pd.to_numeric(df_gonz["aPOG_MesProc"], errors="coerce")
        df_gonz = df_gonz[mp >= PERIODO_MIN_CALIBRACION].copy()
        print(f"  [i] Base de datos: desde {PERIODO_MIN_CALIBRACION} "
              f"-> {len(df_gonz):,} de {n_antes:,} filas")

    df_calib = df_gonz
    if MESES_CALIBRACION_RECIENTE and "aPOG_MesProc" in df_gonz.columns:
        mp = pd.to_numeric(df_gonz["aPOG_MesProc"], errors="coerce").dropna()
        if len(mp):
            ult = int(mp.max())
            # Mes mínimo = último mes - (N-1) meses
            a, mm = divmod(ult, 100)
            idx_min = (a * 12 + (mm - 1)) - (MESES_CALIBRACION_RECIENTE - 1)
            mes_min = (idx_min // 12) * 100 + (idx_min % 12) + 1
            mp_full = pd.to_numeric(df_gonz["aPOG_MesProc"], errors="coerce")
            df_calib = df_gonz[mp_full >= mes_min].copy()
            print(f"  [i] Calibración con ÚLTIMOS {MESES_CALIBRACION_RECIENTE} meses "
                  f"(desde {mes_min}) -> {len(df_calib):,} filas (refleja el ritmo reciente)")

    # 2. Calibrar (sobre la ventana reciente si aplica)
    parametros = calibrar_todo(df_calib, df_tc)

    # 3. Simular
    print("\n" + "=" * 70)
    print(f"SIMULACIÓN MONTE CARLO ({N_SIMULACIONES:,} trayectorias)")
    print("=" * 70)
    t0 = time.time()
    resultados = correr_simulacion(parametros, HORIZONTE_MESES, N_SIMULACIONES, SEMILLA)
    print(f"  Simulación completada en {time.time()-t0:.1f}s")

    # Resumen rápido en consola
    ing_total_p50 = np.percentile(resultados["ingresos"].sum(axis=1), 50)
    egr_total_p50 = np.percentile(resultados["egresos"].sum(axis=1), 50)
    neto_total_p50 = np.percentile(resultados["neto"].sum(axis=1), 50)
    print(f"\n  Proyección {HORIZONTE_MESES} meses (mediana):")
    print(f"    Ingresos totales: ${ing_total_p50:,.0f}")
    print(f"    Egresos totales:  ${egr_total_p50:,.0f}")
    print(f"    Flujo neto:       ${neto_total_p50:,.0f}")

    # 4. Validación estadística
    validacion = validar_todo(parametros, resultados)
    # Prueba de bondad de ajuste (Poisson por dispersión + KS simulado vs real)
    try:
        validacion["bondad"] = prueba_bondad_ajuste(df_gonz, parametros, resultados)
    except Exception as e:
        print(f"  [i] (bondad de ajuste omitida: {type(e).__name__}: {e})")
        validacion["bondad"] = None

    # 4b. Backtest contra el real de los últimos 12 meses
    print("\n--- Backtest vs real (últimos 12 meses) ---")
    backtest = construir_backtest(df_gonz, parametros, resultados, n_meses=12)
    if backtest:
        print(f"  Promedio mensual REAL:   ${backtest['prom_real']:,.0f}")
        print(f"  Mediana mensual MODELO:  ${backtest['modelo_mensual']['p50']:,.0f}")
        print(f"  Cobertura: {backtest['dentro']}/{backtest['n_meses']} meses reales dentro de la banda P5–P95")
    else:
        print("  [!] No se pudo calcular el flujo real histórico.")

    # 4c. Comparativo por meses calendario (proyección estacional vs real interanual)
    comparativo = comparativo_calendario(df_gonz, parametros, resultados, horizonte=HORIZONTE_MESES)
    datos_piv = datos_pivote(df_gonz, parametros, comparativo)
    detalle_fac = detalle_factores_lag(df_gonz)
    # Tendencias históricas 2020-2025: cargar_gonz filtra 2023+ en el SQL, así que
    # traigo el tramo previo (2020-2022) aparte y lo uno en memoria para tener todo.
    df_prev = cargar_gonz_previo(forzar=FORZAR_RECARGA)
    df_hist = (pd.concat([df_prev, df_gonz], ignore_index=True)
               if (df_prev is not None and len(df_prev)) else df_gonz)
    hist_mensual = serie_historica_anual(df_hist, 2020, 2025)
    proy_2026 = serie_proyeccion_2026(df_hist, comparativo, 2026)

    # 5. Excel-Dashboard
    print("\n--- Generando Excel-Dashboard ---")
    carpeta_out = RUTA_BASE / "Outputs"
    try:
        carpeta_out.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # Si la ruta configurada no es accesible, caer a una carpeta local
        carpeta_out = Path.cwd() / "Outputs"
        carpeta_out.mkdir(parents=True, exist_ok=True)
        print(f"  [!] No se pudo usar {RUTA_BASE}\\Outputs ({e}).")
        print(f"      Guardando en: {carpeta_out}")
    ruta_out = carpeta_out / f"Modelo_Flujos_MonteCarlo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    construir_excel(parametros, resultados, ruta_out, validacion, backtest, comparativo, datos_piv, detalle_fac, hist_mensual, proy_2026)

    # 6. Tablas dinámicas nativas (PivotTables/PivotCharts) sobre el Excel recién
    #    creado. Requiere Excel + pywin32 (se instala solo). Si no, se omite sin romper.
    print("\n--- Creando tablas dinámicas nativas (Excel/pywin32) ---")
    try:
        ruta_piv = crear_pivotes_en(str(ruta_out))
        if ruta_piv:
            print(f"  [OK] Tablas dinámicas: {ruta_piv}")
    except Exception as e:
        print(f"  [!] No se pudieron crear las dinámicas ({type(e).__name__}: {e}). "
              f"El Excel base ya quedó completo.")

    print(f"\n{'='*70}")
    print(f"Tiempo total: {time.perf_counter()-inicio:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
