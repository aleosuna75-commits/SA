# -*- coding: utf-8 -*-
"""
================================================================================
  BASE DE % DE CESIÓN — Logouts del Presupuesto Técnico (hoja ParamPPTO)
================================================================================
Recorre una carpeta con los logouts de una o varias LN (archivos
"Logout_<LN>_r<TR>_b<corredor>_e<cedente>[_c<contrato>]-<TipoVenta>-v<n>.xlsx")
y arma una base con el % de cesión de cada documento:

    LN · TR · Cedente · Corredor · Contrato · Tipo de venta · % de cesión

CÓMO SE LEE CADA LOGOUT (hoja ParamPPTO)
----------------------------------------
Las filas se ubican por su ETIQUETA en la columna A (no por número de fila),
así que si el logout agrega o mueve renglones el script sigue funcionando.

  Línea de Negocio ........ B          -> LN
  Tipo Reas. .............. B          -> TR
  Of. Rep. ................ B
  Compañía ................ B          -> Cedente
  Corredor (1a aparición) . B          -> Corredor del documento
  Contrato ................ B
  Tipo Venta .............. B  (y C = % Renov. cuando es "Comb. Nuevo y Renov.")
  MGA ..................... B  (y F = casilla GS)
  Porcentaje .............. B..E       -> Tradicional, Retro Espec., Fronting,
                                          Retención (tabla "Tipo Retrocesión")
  Porcentaje de Cesión .... C..G       -> 2027..2031
  % Comisiones del Cedido . C..G       -> 2027..2031

Los NOMBRES de LN, TR, cedente y corredor salen del catálogo (hoja "Valores" del
PptoTécnico) que Excel guarda en caché dentro de cada logout.

OJO CON 2031: en los logouts la columna B de "Porcentaje de Cesión" siempre
viene vacía y el 2027 cae en C, pero el recuadro con formato del logout es B..F
(5 celdas). Si ningún logout trae dato en G (2031), el script lo avisa: puede
ser que la macro del logout recorte el último año. Confírmalo capturando la
cesión 2027-2031 en un PRESUPUESTO (M34:Q34) y viendo en qué celdas del logout caen.

SALIDA
------
Un Excel "Base_Cesion_<LN>_<fecha>.xlsx" con las hojas:
  * Base_Cesion   una fila por documento (formato ancho, años en columnas)
  * Cesion_Anual  una fila por documento y año (lista para tablas dinámicas)
  * Resumen       conteos por LN y TR
  * Validaciones  inconsistencias a revisar con la LN
  * Notas         de dónde sale cada columna

CÓMO CORRERLO
-------------
En VSCode: abrir este archivo y dar clic en "Run Python File" (▷). Busca la
carpeta "CIFRAS AJUSTADAS" en Documentos; si no la encuentra, abre una ventana
para elegirla. También se puede indicar la ruta:

    python base_cesion.py "C:\\Users\\<usuario>\\Documents\\CIFRAS AJUSTADAS"

Si falta openpyxl o pandas (o están muy viejos), el script los instala solo con pip.
================================================================================
"""
from __future__ import annotations

import argparse
import importlib
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree


# ------------------------------------------------------------------------------
# CONFIGURACIÓN (ajustar aquí si cambia algo)
# ------------------------------------------------------------------------------
# Ruta de la carpeta con los logouts. Vacío = buscar NOMBRE_CARPETA en Documentos.
CARPETA_LOGOUTS = r""
NOMBRE_CARPETA = "CIFRAS AJUSTADAS"
BUSCAR_EN_SUBCARPETAS = True

# Dónde guardar el Excel de salida. Vacío = carpeta que contiene a los logouts.
CARPETA_SALIDA = r""

HOJA_LOGOUT = "ParamPPTO"
PRIMER_ANIO = 2027
NUM_ANIOS = 5
COL_PRIMER_ANIO = 3  # columna C = 2027 en "Porcentaje de Cesión" y "% Comisiones"

# Si una LN capturó la cesión solo para algunos años (típicamente solo 2027),
# True = los años siguientes toman el último valor capturado. False = se dejan
# vacíos tal como vienen en el logout.
ARRASTRAR_ULTIMO_ANIO = False

# True = abrir el Excel generado al terminar (solo Windows / macOS).
ABRIR_AL_TERMINAR = True

# Catálogo de nombres: hoja del PptoTécnico guardada en caché dentro del logout,
# columna del código -> columnas con los datos que se agregan a la base.
HOJA_CATALOGO = "Valores"
CATALOGOS = {
    "LN": ("BH", ["Nombre LN"]),
    "TR": ("V", ["TR desc."]),
    "Cedente": ("AR", ["Nombre Cedente", "País Cedente", "Grupo Cedente"]),
    "Corredor": ("AX", ["Nombre Corredor"]),
}
COLUMNAS_CATALOGO = {  # nombre en la base -> columna en la hoja Valores
    "Nombre LN": "BI", "TR desc.": "W", "Nombre Cedente": "AS",
    "País Cedente": "AU", "Grupo Cedente": "AV", "Nombre Corredor": "AY",
}
TR_DESC_RESPALDO = {1: "Proporcional", 2: "No Proporcional", 3: "Facultativo"}

TOLERANCIA = 1e-6
MINIMOS = {"pandas": (1, 1), "openpyxl": (3, 0)}  # versión mínima de cada paquete


# ------------------------------------------------------------------------------
# PAQUETERÍA
# ------------------------------------------------------------------------------
def revisar_paquete(modulo):
    """'' si el paquete importa y cumple la versión mínima; si no, el problema."""
    try:
        paquete = importlib.import_module(modulo)
    except Exception as error:  # no instalado, o instalado pero roto (p. ej. choque con numpy)
        return f"{modulo}: {type(error).__name__}: {error}"
    version = tuple(int(x) for x in re.findall(r"\d+", getattr(paquete, "__version__", "0"))[:2])
    minimo = MINIMOS[modulo]
    if version < minimo:
        return f"{modulo} {paquete.__version__} es muy viejo (se necesita {minimo[0]}.{minimo[1]} o más)"
    return ""


def asegurar_paquetes():
    """Instala con pip (en el mismo Python que corre el script) lo que falte y vuelve a arrancar."""
    problemas = {m: p for m in MINIMOS for p in [revisar_paquete(m)] if p}
    if not problemas:
        return
    requisitos = [f"{m}>={MINIMOS[m][0]}.{MINIMOS[m][1]}" for m in problemas]
    a_mano = ("\nInstálala a mano desde la terminal de VSCode con:\n"
              f'    "{sys.executable}" -m pip install --upgrade {" ".join(requisitos)}\n'
              "Si la red de la oficina usa proxy, agrega: --proxy http://usuario:clave@proxy:puerto")
    if os.environ.get("BASE_CESION_REINTENTO"):
        sys.exit("La paquetería sigue fallando después de instalarla:\n  "
                 + "\n  ".join(problemas.values()) + a_mano)

    print("Instalando / actualizando paquetería: " + ", ".join(requisitos) + " ...")
    pip = [sys.executable, "-m", "pip"]
    silencio = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if subprocess.call(pip + ["--version"], **silencio) != 0:  # este Python no trae pip
        subprocess.call([sys.executable, "-m", "ensurepip", "--upgrade"], **silencio)
    base = pip + ["install", "--upgrade", "--disable-pip-version-check"] + requisitos
    intentos = [base]
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):  # --user no aplica dentro de un venv
        intentos.append(base[:4] + ["--user"] + base[4:])
    if not any(subprocess.call(cmd) == 0 for cmd in intentos):
        sys.exit("\nNo se pudo instalar la paquetería automáticamente." + a_mano)

    # Arrancar de nuevo en un proceso limpio para que tome lo recién instalado.
    print("Paquetería lista. Reiniciando el script...\n")
    entorno = dict(os.environ, BASE_CESION_REINTENTO="1")
    sys.exit(subprocess.call([sys.executable, str(Path(__file__).resolve())] + sys.argv[1:], env=entorno))


asegurar_paquetes()

import pandas as pd  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402


# ------------------------------------------------------------------------------
# UTILERÍAS
# ------------------------------------------------------------------------------
def normalizar(texto):
    if texto is None:
        return ""
    sin_acentos = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(ch for ch in sin_acentos if not unicodedata.combining(ch))
    return " ".join(sin_acentos.lower().split())


def vacio(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == "")


def a_numero(valor):
    """Convierte a float: 0.8, '80%', '0,8', ' 80 % '. Devuelve (numero, es_invalido)."""
    if vacio(valor):
        return None, False
    if isinstance(valor, bool):  # VERDADERO/FALSO en una celda de porcentaje
        return None, True
    if isinstance(valor, (int, float)):
        return float(valor), False
    texto = str(valor).strip()
    es_pct = texto.endswith("%")
    texto = texto.rstrip("%").strip().replace("\u00a0", "").replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None, True
    return (numero / 100 if es_pct else numero), False


def a_codigo(valor):
    """Códigos (TR, cedente, corredor...) como entero cuando se puede."""
    numero, _ = a_numero(valor)
    if numero is not None and float(numero).is_integer():
        return int(numero)
    return None if vacio(valor) else str(valor).strip()


def clave_codigo(valor):
    """Llave de texto para cruzar códigos con el catálogo: 39, '39', 39.0 -> '39'."""
    codigo = a_codigo(valor)
    return None if codigo is None else str(codigo).upper()


def a_si_no(valor):
    if vacio(valor):
        return None
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    texto = normalizar(valor)
    if texto in ("verdadero", "true", "si", "1"):
        return "Sí"
    if texto in ("falso", "false", "no", "0"):
        return "No"
    return str(valor)


# ------------------------------------------------------------------------------
# UBICAR LA CARPETA DE LOGOUTS
# ------------------------------------------------------------------------------
EXT_SOPORTADAS = (".xlsx", ".xlsm")


def carpetas_documentos():
    """Posibles carpetas 'Documentos' del usuario (incluye OneDrive)."""
    casa = Path.home()
    candidatas = []
    if os.name == "nt":
        try:  # Ruta real de "Documentos", aunque esté redirigida a OneDrive
            import ctypes
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
                candidatas.append(Path(buf.value))
        except Exception:
            pass
    for var in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        if os.environ.get(var):
            candidatas += [Path(os.environ[var]) / "Documents",
                           Path(os.environ[var]) / "Documentos"]
    candidatas += [casa / "Documents", casa / "Documentos"]
    for onedrive in sorted(casa.glob("OneDrive*")):
        candidatas += [onedrive / "Documents", onedrive / "Documentos"]
    vistas, unicas = set(), []
    for c in candidatas:
        clave = str(c).lower()
        if clave not in vistas and c.is_dir():
            vistas.add(clave)
            unicas.append(c)
    return unicas


def es_logout(ruta):
    return ruta.name.lower().startswith("logout_") and not ruta.name.startswith("~$")


def hay_logouts(carpeta, recursivo):
    patron = "**/*" if recursivo else "*"
    return any(es_logout(p) and p.suffix.lower() in EXT_SOPORTADAS for p in carpeta.glob(patron))


def elegir_carpeta_con_ventana():
    try:
        import tkinter as tk
        from tkinter import filedialog
        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        ruta = filedialog.askdirectory(title="Elige la carpeta con los logouts")
        raiz.destroy()
        return Path(ruta) if ruta else None
    except Exception:
        return None


def ubicar_carpeta(ruta_argumento):
    if ruta_argumento:
        return Path(ruta_argumento).expanduser()
    if CARPETA_LOGOUTS:
        return Path(CARPETA_LOGOUTS).expanduser()

    # NOMBRE_CARPETA dentro de Documentos, hasta dos niveles abajo
    # (p. ej. "Documentos\\PPTO\\CIFRAS AJUSTADAS"; acepta "CIFRAS_AJUSTADAS").
    objetivo = normalizar(NOMBRE_CARPETA).replace("_", " ")
    documentos = carpetas_documentos()
    for docs in documentos:
        for c in [docs / NOMBRE_CARPETA, *docs.glob("*/"), *docs.glob("*/*/")]:
            if (c.is_dir() and normalizar(c.name).replace("_", " ") == objetivo
                    and hay_logouts(c, BUSCAR_EN_SUBCARPETAS)):
                return c

    # Logouts junto al script (sin bajar a subcarpetas, y nunca Documentos completo).
    prohibidas = {str(p).lower() for p in documentos + [Path.home()]}
    junto_al_script = Path(__file__).resolve().parent
    for c in (junto_al_script / NOMBRE_CARPETA, junto_al_script):
        if c.is_dir() and str(c).lower() not in prohibidas and hay_logouts(c, False):
            return c

    print(f'No encontré la carpeta "{NOMBRE_CARPETA}" en Documentos.')
    ruta = elegir_carpeta_con_ventana()
    if ruta is None:
        texto = input("Pega la ruta de la carpeta con los logouts: ").strip().strip('"')
        ruta = Path(texto) if texto else None
    if ruta is None:
        sys.exit("No se indicó carpeta. Fin.")
    return ruta


def listar_logouts(carpeta):
    """(logouts .xlsx/.xlsm, logouts en otro formato que no se pueden leer)."""
    patron = "**/*" if BUSCAR_EN_SUBCARPETAS else "*"
    todos = sorted((p for p in carpeta.glob(patron) if p.is_file() and es_logout(p)),
                   key=lambda p: str(p).lower())
    return ([p for p in todos if p.suffix.lower() in EXT_SOPORTADAS],
            [p for p in todos if p.suffix.lower() not in EXT_SOPORTADAS])


# ------------------------------------------------------------------------------
# LECTURA DE UN LOGOUT
# ------------------------------------------------------------------------------
PATRON_NOMBRE = re.compile(
    r"^Logout_(?P<ln>[^_]+)_r(?P<tr>\d+)_b(?P<corredor>\d+)_e(?P<cedente>\d+)"
    r"(?:_c(?P<contrato>\d+))?-(?P<venta>[^-]+)-v(?P<version>\d+)$",
    re.IGNORECASE,
)

# Etiqueta en columna A -> clave interna. Se toma la PRIMERA fila con esa etiqueta
# (la palabra "Corredor" aparece dos veces; la segunda es la distribución proyectada).
ETIQUETAS = {
    "linea de negocio": "ln",
    "tipo reas.": "tr",
    "of. rep.": "of_rep",
    "compania": "cedente",
    "corredor": "corredor",
    "contrato": "contrato",
    "tipo venta": "tipo_venta",
    "mga": "mga",
    "porcentaje": "retro",
    "porcentaje de cesion": "cesion",
    "% comisiones del cedido": "comision",
}
TIPOS_RETRO = ["Tradicional", "Retro Espec.", "Fronting", "Retención"]
ANIOS = list(range(PRIMER_ANIO, PRIMER_ANIO + NUM_ANIOS))
MAX_FILAS_ENCABEZADO = 40
MAX_COLUMNAS = 26  # A..Z: se lee de más para detectar valores fuera de lugar


def leer_filas(ruta, formulas):
    """Primeras filas de la hoja del logout. formulas=True trae el texto de las fórmulas."""
    wb = load_workbook(ruta, read_only=True, data_only=not formulas, keep_links=False)
    try:
        ws = wb[HOJA_LOGOUT] if HOJA_LOGOUT in wb.sheetnames else wb.worksheets[0]
        filas = [list(f) + [None] * (MAX_COLUMNAS - len(f))
                 for f in ws.iter_rows(min_row=1, max_row=MAX_FILAS_ENCABEZADO,
                                       max_col=MAX_COLUMNAS, values_only=True)]
        return ws.title, filas
    finally:
        wb.close()


def leer_logout(ruta):
    """Devuelve (registro, lista_de_validaciones) para un archivo."""
    avisos = []

    def avisar(nivel, tipo, detalle):
        avisos.append({"Archivo": ruta.name, "Nivel": nivel, "Tipo": tipo, "Detalle": detalle})

    registro = {"Archivo": ruta.name}
    hoja, filas = leer_filas(ruta, formulas=False)
    if hoja != HOJA_LOGOUT:
        avisar("Revisar", "Hoja no encontrada", f'No existe la hoja "{HOJA_LOGOUT}"; se leyó "{hoja}".')

    fila_de = {}
    for i, fila in enumerate(filas):
        clave = ETIQUETAS.get(normalizar(fila[0]))
        if clave and clave not in fila_de:
            fila_de[clave] = i
    faltan = [k for k in ETIQUETAS.values() if k not in fila_de]
    if faltan:
        avisar("Error", "Etiquetas no encontradas",
               "No se encontraron en la columna A: " + ", ".join(faltan))

    # Fórmulas guardadas sin valor calculado (se leerían como celda vacía).
    _, crudas = leer_filas(ruta, formulas=True)
    sin_valor = [f"{get_column_letter(j + 1)}{i + 1}"
                 for i in sorted(fila_de.values()) for j in range(1, MAX_COLUMNAS)
                 if isinstance(crudas[i][j], str) and crudas[i][j].startswith("=")
                 and filas[i][j] is None]
    if sin_valor:
        avisar("Error", "Fórmula sin valor calculado",
               "Celdas " + ", ".join(sin_valor) + ": abrir el logout en Excel, guardarlo y volver a correr")

    def celda(clave, col):  # col: 1 = A, 2 = B, ...
        return filas[fila_de[clave]][col - 1] if clave in fila_de else None

    def porcentaje(clave, col, nombre):
        valor = celda(clave, col)
        numero, invalido = a_numero(valor)
        if invalido:
            avisar("Error", "Valor no numérico", f"{nombre}: '{valor}'")
        elif numero is not None and numero < -TOLERANCIA:
            avisar("Revisar", "Porcentaje negativo", f"{nombre} = {numero:g}")
        elif numero is not None and numero > 1 + TOLERANCIA:
            pista = f" (¿capturado como {numero:g} en lugar de {numero / 100:g}?)" if numero <= 100 else ""
            avisar("Revisar", "Porcentaje mayor a 100%", f"{nombre} = {numero:g}{pista}")
        return numero

    def valores_fuera(clave, columnas_validas, nombre):
        fuera = [(get_column_letter(c), celda(clave, c)) for c in range(2, MAX_COLUMNAS + 1)
                 if c not in columnas_validas and not vacio(celda(clave, c))]
        if fuera:
            rango = f"{get_column_letter(min(columnas_validas))}..{get_column_letter(max(columnas_validas))}"
            avisar("Revisar", "Valor fuera de las columnas esperadas",
                   f"{nombre}: " + ", ".join(f"{c}={v}" for c, v in fuera) + f" (se esperan solo en {rango})")

    # --- Llaves del documento --------------------------------------------------
    registro["LN"] = a_codigo(celda("ln", 2))
    registro["TR"] = a_codigo(celda("tr", 2))
    registro["Of. Rep."] = a_codigo(celda("of_rep", 2))
    registro["Cedente"] = a_codigo(celda("cedente", 2))
    registro["Corredor"] = a_codigo(celda("corredor", 2))
    registro["Contrato"] = a_codigo(celda("contrato", 2))
    registro["Tipo Venta"] = celda("tipo_venta", 2)
    registro["% Renov."] = porcentaje("tipo_venta", 3, "% Renov.")
    registro["MGA"] = a_si_no(celda("mga", 2))
    registro["GS"] = a_si_no(celda("mga", 6))

    # --- Tipo de retrocesión ----------------------------------------------------
    total = 0.0
    capturado = False
    for i, tipo in enumerate(TIPOS_RETRO):
        numero = porcentaje("retro", 2 + i, f"% {tipo}")
        registro[f"% {tipo}"] = numero
        if numero is not None:
            total += numero
            capturado = True
    registro["% Total Retrocesión"] = total if capturado else None
    valores_fuera("retro", range(2, 2 + len(TIPOS_RETRO)), "Porcentaje (Tipo Retrocesión)")

    # --- % de cesión y % comisiones del cedido por año --------------------------
    cols_anios = range(COL_PRIMER_ANIO, COL_PRIMER_ANIO + NUM_ANIOS)
    for clave, prefijo in (("cesion", "% Cesión"), ("comision", "% Com. Cedido")):
        valores = [porcentaje(clave, c, f"{prefijo} {anio}") for c, anio in zip(cols_anios, ANIOS)]
        registro[f"_capturados_{clave}"] = [a for a, v in zip(ANIOS, valores) if v is not None]
        if ARRASTRAR_ULTIMO_ANIO:
            for i in range(1, NUM_ANIOS):
                if valores[i] is None:
                    valores[i] = valores[i - 1]
        for anio, v in zip(ANIOS, valores):
            registro[f"{prefijo} {anio}"] = v
        if not vacio(celda(clave, 2)):
            avisar("Error", "Valor en la columna B de años",
                   f"{prefijo}: B={celda(clave, 2)}. En los logouts la columna B viene vacía y 2027 cae "
                   f"en C; si ahora trae dato, revisar si cambió la alineación de años.")
        valores_fuera(clave, [2, *cols_anios], prefijo)

    capturados = registro["_capturados_cesion"]
    cesion_capturada = bool(capturados)
    registro["Cesión capturada"] = "Sí" if cesion_capturada else "No"
    registro["Años con cesión"] = ", ".join(map(str, capturados)) or None

    # --- Consistencia con el nombre del archivo ---------------------------------
    m = PATRON_NOMBRE.match(ruta.stem)
    registro["Versión archivo"] = int(m["version"]) if m else None
    if not m:
        avisar("Info", "Nombre de archivo no estándar",
               "No sigue Logout_<LN>_r<TR>_b<corredor>_e<cedente>[_c<contrato>]-<venta>-v<n>")
    else:
        esperado = {"LN": m["ln"], "TR": int(m["tr"]), "Corredor": int(m["corredor"]),
                    "Cedente": int(m["cedente"]),
                    "Contrato": int(m["contrato"]) if m["contrato"] else None}
        for campo, valor in esperado.items():
            en_hoja = "" if registro[campo] is None else str(registro[campo]).upper()
            if en_hoja != ("" if valor is None else str(valor).upper()):
                avisar("Error", "Nombre vs contenido",
                       f"{campo}: archivo dice {valor}, la hoja dice {registro[campo]}")
        venta_archivo = normalizar(m["venta"])
        venta_hoja = normalizar(registro["Tipo Venta"])
        if (venta_archivo.startswith("renov") and not venta_hoja.startswith("renov")) or \
           (venta_archivo.startswith("nva") and not venta_hoja.startswith("nuevo")):
            avisar("Revisar", "Nombre vs contenido",
                   f"Tipo de venta: archivo dice {m['venta']}, la hoja dice {registro['Tipo Venta']}")

    # --- Reglas de negocio --------------------------------------------------------
    if not capturado:
        avisar("Revisar", "Tipo Retrocesión vacío", "No hay % en Tradicional/Retro Espec./Fronting/Retención")
    elif abs(total - 1) > TOLERANCIA:
        avisar("Revisar", "Tipo Retrocesión no suma 100%", f"Total = {total:.2%}")
    especifica = (registro["% Retro Espec."] or 0) + (registro["% Fronting"] or 0)
    if especifica > TOLERANCIA and not cesion_capturada:
        avisar("Revisar", "Falta % de cesión",
               f"Retro Espec. + Fronting = {especifica:.0%} pero no hay % de cesión capturado")
    if especifica > TOLERANCIA and cesion_capturada and \
            all((registro[f"% Cesión {a}"] or 0) <= TOLERANCIA for a in ANIOS):
        avisar("Revisar", "Cesión 0% con Retro Espec./Fronting",
               f"Retro Espec. + Fronting = {especifica:.0%} pero el % de cesión capturado es 0%")
    if capturado and cesion_capturada and especifica <= TOLERANCIA:
        avisar("Revisar", "Cesión sin Retro Espec./Fronting",
               "Hay % de cesión capturado pero el tipo de retrocesión es 100% Tradicional/Retención")
    if registro["_capturados_comision"] and not cesion_capturada:
        avisar("Revisar", "Comisión sin % de cesión",
               "Hay % Comisiones del Cedido en " + ", ".join(map(str, registro["_capturados_comision"]))
               + " pero no hay % de cesión")
    if cesion_capturada and set(capturados) != set(registro["_capturados_comision"]):
        avisar("Info", "Años distintos en cesión y comisión",
               f"Cesión: {capturados}; Comisión: {registro['_capturados_comision']}")
    if cesion_capturada and len(capturados) < NUM_ANIOS:
        avisar("Info", "Cesión no viene en todos los años del logout",
               "Años con cesión: " + ", ".join(map(str, capturados)))
    es_combinada = "comb" in normalizar(registro["Tipo Venta"])
    if es_combinada and registro["% Renov."] is None:
        avisar("Revisar", "Falta % Renov.", "Tipo de venta combinado sin % de renovación")
    if not es_combinada and registro["% Renov."] is not None:
        avisar("Info", "% Renov. en venta no combinada",
               f"Tipo de venta {registro['Tipo Venta']} con % Renov. = {registro['% Renov.']:g}")

    registro["Ruta"] = str(ruta)
    return registro, avisos


# ------------------------------------------------------------------------------
# CATÁLOGO DE NOMBRES (caché de la hoja "Valores" del PptoTécnico en el logout)
# ------------------------------------------------------------------------------
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def leer_catalogo(ruta):
    """{'Cedente': {'39': {'Nombre Cedente': ..., ...}}, ...} desde los vínculos externos del logout."""
    catalogo = {clave: {} for clave in CATALOGOS}
    with zipfile.ZipFile(ruta) as libro:
        for parte in libro.namelist():
            if not re.fullmatch(r"xl/externalLinks/externalLink\d+\.xml", parte):
                continue
            raiz = ElementTree.fromstring(libro.read(parte))
            hojas = [h.get("val") for h in raiz.iter(NS + "sheetName")]
            if HOJA_CATALOGO not in hojas:
                continue
            indice = str(hojas.index(HOJA_CATALOGO))
            for datos in raiz.iter(NS + "sheetData"):
                if datos.get("sheetId") != indice:
                    continue
                for fila in datos.iter(NS + "row"):
                    celdas = {}
                    for c in fila.iter(NS + "cell"):
                        v = c.find(NS + "v")
                        if v is not None and v.text:
                            celdas[re.match(r"[A-Z]+", c.get("r", "")).group()] = v.text.strip()
                    for clave, (col_codigo, campos) in CATALOGOS.items():
                        codigo = clave_codigo(celdas.get(col_codigo))
                        if codigo is not None:
                            catalogo[clave].setdefault(
                                codigo, {campo: celdas.get(COLUMNAS_CATALOGO[campo]) for campo in campos})
    return catalogo


def agregar_nombres(registros):
    """Pone los nombres del catálogo; solo abre el catálogo de los archivos con códigos nuevos."""
    catalogo = {clave: {} for clave in CATALOGOS}
    leidos = 0
    for reg in registros:
        if any(clave_codigo(reg[clave]) not in catalogo[clave]
               for clave in CATALOGOS if reg[clave] is not None):
            try:
                nuevo = leer_catalogo(Path(reg["Ruta"]))
            except Exception:
                continue
            leidos += 1
            for clave, codigos in nuevo.items():
                for codigo, datos in codigos.items():
                    catalogo[clave].setdefault(codigo, datos)
    for reg in registros:
        for clave, (_, campos) in CATALOGOS.items():
            datos = catalogo[clave].get(clave_codigo(reg[clave]), {})
            for campo in campos:
                reg[campo] = datos.get(campo)
        if reg["TR desc."] is None:
            reg["TR desc."] = TR_DESC_RESPALDO.get(reg["TR"])
    return catalogo, leidos


# ------------------------------------------------------------------------------
# ARMADO DE LA BASE Y ESCRITURA DEL EXCEL
# ------------------------------------------------------------------------------
LLAVES = ["LN", "TR", "Cedente", "Corredor", "Contrato", "Tipo Venta"]
COLUMNAS_BASE = (
    ["Archivo", "LN", "Nombre LN", "TR", "TR desc.", "Cedente", "Nombre Cedente", "País Cedente",
     "Grupo Cedente", "Corredor", "Nombre Corredor", "Of. Rep.", "Contrato", "Tipo Venta",
     "% Renov.", "MGA"]
    + [f"% {t}" for t in TIPOS_RETRO] + ["% Total Retrocesión", "Cesión capturada", "Años con cesión"]
    + [f"% Cesión {a}" for a in ANIOS] + [f"% Com. Cedido {a}" for a in ANIOS]
    + ["GS", "Versión archivo", "Versión vigente", "Observaciones", "Ruta"]
)


def construir_base(carpeta, archivos, no_soportados):
    registros = []
    validaciones = [{"Archivo": p.name, "Nivel": "Error", "Tipo": "Formato no soportado",
                     "Detalle": f"{p.suffix} no se puede leer; abrirlo en Excel y guardarlo como .xlsx"}
                    for p in no_soportados]
    for n, ruta in enumerate(archivos, 1):
        print(f"  [{n}/{len(archivos)}] {ruta.name}")
        try:
            registro, avisos = leer_logout(ruta)
        except Exception as error:  # archivo dañado, protegido, abierto, etc.
            validaciones.append({"Archivo": ruta.name, "Nivel": "Error",
                                 "Tipo": "No se pudo leer", "Detalle": f"{type(error).__name__}: {error}"})
            continue
        registros.append(registro)
        validaciones.extend(avisos)

    if not registros:
        return pd.DataFrame(columns=COLUMNAS_BASE), pd.DataFrame(
            validaciones, columns=["Archivo", "Nivel", "Tipo", "Detalle"])

    catalogo, leidos = agregar_nombres(registros)
    if leidos == 0 or not any(catalogo.values()):
        validaciones.append({"Archivo": "(todos)", "Nivel": "Info", "Tipo": "Sin catálogo de nombres",
                             "Detalle": f'Los logouts no traen la hoja "{HOJA_CATALOGO}" en caché; '
                                        "las columnas de nombre quedan vacías."})
    else:
        for reg in registros:
            sin_nombre = [clave for clave in ("Cedente", "Corredor")
                          if reg[clave] is not None and reg[CATALOGOS[clave][1][0]] is None]
            if sin_nombre:
                validaciones.append({"Archivo": reg["Archivo"], "Nivel": "Info", "Tipo": "Código sin nombre",
                                     "Detalle": ", ".join(f"{c} {reg[c]}" for c in sin_nombre)
                                     + " no aparece en el catálogo del logout"})

    # Aviso de carpeta: nadie trae el último año (posible recorte del logout)
    ultimo = ANIOS[-1]
    if any(r["_capturados_cesion"] for r in registros) and \
            not any(ultimo in r["_capturados_cesion"] for r in registros):
        multi = sum(len(r["_capturados_cesion"]) > 1 for r in registros)
        col = get_column_letter(COL_PRIMER_ANIO + NUM_ANIOS - 1)
        validaciones.append({
            "Archivo": "(todos)", "Nivel": "Revisar", "Tipo": f"Ningún logout trae {ultimo}",
            "Detalle": f"Ningún documento tiene % de cesión en la col. {col} ({ultimo}); {multi} documento(s) "
                       f"capturaron varios años y todos terminan antes. El recuadro del logout es de 5 celdas "
                       f"(B..F) y B siempre viene vacía: confirmar en un PRESUPUESTO (M34:Q34) si el logout "
                       f"recorta el último año."})

    base = pd.DataFrame(registros)

    # Códigos como enteros (sin ".0") y porcentajes como número aunque vengan vacíos
    for c in ["TR", "Of. Rep.", "Cedente", "Corredor", "Contrato", "Versión archivo"]:
        numeros = pd.to_numeric(base[c], errors="coerce")
        if numeros.notna().sum() == base[c].notna().sum() and (numeros.dropna() % 1 == 0).all():
            base[c] = numeros.astype("Int64")
    for c in [c for c in COLUMNAS_BASE if c.startswith("%") and c in base.columns]:
        base[c] = pd.to_numeric(base[c], errors="coerce").astype("float64")

    # Versiones del mismo documento: la vigente es la de mayor -vN (y, si empatan, la más reciente)
    llave = base[LLAVES].astype(object).where(base[LLAVES].notna(), "").astype(str).agg("|".join, axis=1)
    fecha = base["Ruta"].map(lambda r: os.path.getmtime(r) if os.path.exists(r) else 0)
    orden = base.assign(_llave=llave, _fecha=fecha, _v=base["Versión archivo"].fillna(0))
    vigentes = set(orden.sort_values(["_v", "_fecha"]).groupby("_llave").tail(1).index)
    base["Versión vigente"] = ["Sí" if i in vigentes else "No" for i in base.index]
    for _, grupo in base.groupby(llave):
        if len(grupo) < 2:
            continue
        for i, fila in grupo.iterrows():
            otros = [os.path.relpath(r, carpeta) for r in grupo.drop(index=i)["Ruta"]]
            validaciones.append({"Archivo": fila["Archivo"], "Nivel": "Revisar", "Tipo": "Documento repetido",
                                 "Detalle": f"Versión vigente: {fila['Versión vigente']}. Misma LN/TR/Cedente/"
                                            f"Corredor/Contrato/Venta que: " + ", ".join(otros)})

    val = pd.DataFrame(validaciones, columns=["Archivo", "Nivel", "Tipo", "Detalle"])
    resumen_obs = (val[val["Nivel"] != "Info"].groupby("Archivo")["Tipo"]
                   .apply(lambda s: "; ".join(dict.fromkeys(s))))
    base["Observaciones"] = base["Archivo"].map(resumen_obs)
    base = base.reindex(columns=COLUMNAS_BASE)
    base = base.sort_values(["LN", "TR", "Cedente", "Corredor", "Contrato", "Archivo"],
                            key=lambda s: s.astype(str) if s.name in ("LN", "Archivo")
                            else pd.to_numeric(s, errors="coerce"),
                            na_position="first")
    orden_nivel = {"Error": 0, "Revisar": 1, "Info": 2}
    val = val.sort_values(["Nivel", "Archivo", "Tipo"],
                          key=lambda s: s.map(orden_nivel) if s.name == "Nivel" else s)
    return base.reset_index(drop=True), val.reset_index(drop=True)


def construir_anual(base):
    ids = ["Archivo", "LN", "TR", "TR desc.", "Cedente", "Nombre Cedente", "Corredor", "Nombre Corredor",
           "Contrato", "Tipo Venta", "Cesión capturada", "Versión vigente"]
    filas = []
    for _, doc in base.iterrows():
        for anio in ANIOS:
            fila = {c: doc[c] for c in ids}
            fila["Año"] = anio
            fila["% Cesión"] = doc[f"% Cesión {anio}"]
            fila["% Com. Cedido"] = doc[f"% Com. Cedido {anio}"]
            filas.append(fila)
    anual = pd.DataFrame(filas, columns=ids + ["Año", "% Cesión", "% Com. Cedido"])
    for c in ["TR", "Cedente", "Corredor", "Contrato"]:
        if str(base[c].dtype) == "Int64":
            anual[c] = anual[c].astype("Int64")
    return anual


def construir_resumen(base):
    """Solo versiones vigentes; los % fuera de 0..100% no entran a mín./promedio/máx."""
    if base.empty:
        return pd.DataFrame()
    b = base[base["Versión vigente"].eq("Sí")]
    col = f"% Cesión {PRIMER_ANIO}"
    b = b.assign(_con=b["Cesión capturada"].eq("Sí"), _obs=b["Observaciones"].notna(),
                 _pct=b[col].where(b[col].between(0, 1)),
                 _desc=b["TR desc."].fillna(""), _nom=b["Nombre LN"].fillna(""))
    nombres = {"Documentos": ("Archivo", "count"), "Con % cesión": ("_con", "sum"),
               "Con observaciones": ("_obs", "sum"), f"% Cesión {PRIMER_ANIO} mín.": ("_pct", "min"),
               f"% Cesión {PRIMER_ANIO} promedio simple": ("_pct", "mean"),
               f"% Cesión {PRIMER_ANIO} máx.": ("_pct", "max")}
    resumen = b.groupby(["LN", "_nom", "TR", "_desc"], dropna=False).agg(**nombres).reset_index()
    resumen = resumen.rename(columns={"_nom": "Nombre LN", "_desc": "TR desc."})
    total = {"LN": "TOTAL", "Documentos": len(b), "Con % cesión": int(b["_con"].sum()),
             "Con observaciones": int(b["_obs"].sum()), f"% Cesión {PRIMER_ANIO} mín.": b["_pct"].min(),
             f"% Cesión {PRIMER_ANIO} promedio simple": b["_pct"].mean(),
             f"% Cesión {PRIMER_ANIO} máx.": b["_pct"].max()}
    return pd.concat([resumen, pd.DataFrame([total])], ignore_index=True)


def construir_notas(carpeta, n_archivos):
    col = get_column_letter
    anios = f"{col(COL_PRIMER_ANIO)}..{col(COL_PRIMER_ANIO + NUM_ANIOS - 1)}"
    filas = [
        ("Generado", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Carpeta leída", str(carpeta)),
        ("Archivos leídos", n_archivos),
        ("Hoja del logout", HOJA_LOGOUT),
        ("LN", "Línea de Negocio, col. B"),
        ("TR", "Tipo Reas., col. B"),
        ("Cedente", "Compañía, col. B"),
        ("Corredor", "Corredor (primera aparición, fila del documento), col. B"),
        ("Of. Rep.", "Of. Rep., col. B"),
        ("Contrato", "Contrato, col. B (vacío si el documento no tiene contrato)"),
        ("Tipo Venta / % Renov.", "Tipo Venta, col. B / col. C"),
        ("MGA / GS", "MGA, col. B / col. F (casilla GS de la tabla de cesión)"),
        ("Nombre LN, TR desc., Nombre / País / Grupo Cedente, Nombre Corredor",
         f'Catálogo de la hoja "{HOJA_CATALOGO}" del PptoTécnico, guardado en caché dentro de cada logout'),
        ("% Tradicional ... % Retención", "Porcentaje, cols. B..E (tabla Tipo Retrocesión)"),
        ("% Cesión <año>", f"Porcentaje de Cesión, cols. {anios} = {ANIOS[0]}..{ANIOS[-1]}. Es el valor "
                           "capturado por la LN; no está multiplicado por % Retro Espec. + % Fronting"),
        ("% Com. Cedido <año>", f"% Comisiones del Cedido, cols. {anios} = {ANIOS[0]}..{ANIOS[-1]}"),
        ("Advertencia último año", f"El recuadro con formato del logout es B..F y la col. B siempre viene "
                                   f"vacía; si ningún logout trae dato en {col(COL_PRIMER_ANIO + NUM_ANIOS - 1)}"
                                   f" ({ANIOS[-1]}), confirmar si la macro del logout lo exporta"),
        ("Cesión capturada / Años con cesión", "Años con al menos un % de cesión en el logout"),
        ("Años sin captura", "Se arrastró el último año capturado" if ARRASTRAR_ULTIMO_ANIO
         else "Se dejan vacíos, tal como vienen en el logout"),
        ("Versión archivo", "Sufijo -vN del nombre del archivo (no es la fila 'Versión' del logout)"),
        ("Versión vigente", "Sí = la versión más alta de cada documento (misma LN/TR/Cedente/Corredor/"
                            "Contrato/Venta); si empatan, la modificada más recientemente"),
        ("Resumen", "Solo versiones vigentes; los % fuera de 0%..100% no entran a mín./promedio/máx."),
        ("Observaciones", "Resumen de la hoja Validaciones (niveles Error y Revisar)"),
    ]
    return pd.DataFrame(filas, columns=["Concepto", "Detalle"])


AZUL = PatternFill("solid", fgColor="1F4E78")
BLANCO_NEGRITA = Font(bold=True, color="FFFFFF")


def dar_formato(ws, df, anchos=None):
    for celda in ws[1]:
        celda.fill = AZUL
        celda.font = BLANCO_NEGRITA
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2" if "Archivo" in df.columns else "A2"
    if len(df):
        ws.auto_filter.ref = ws.dimensions
    for i, nombre in enumerate(df.columns, 1):
        es_pct = str(nombre).startswith("%")
        if es_pct:
            for (celda,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                celda.number_format = "0.00%"
        muestra = [len(str(nombre)) * (0.6 if es_pct else 1)] + \
                  [len(str(v)) for v in df[nombre].head(200) if pd.notna(v)]
        ancho = (anchos or {}).get(nombre, min(max(muestra) + 2, 50))
        ws.column_dimensions[get_column_letter(i)].width = max(ancho, 9 if es_pct else 6)


def escribir_excel(salida, hojas):
    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        for nombre, df in hojas.items():
            df.to_excel(writer, sheet_name=nombre, index=False)
            dar_formato(writer.sheets[nombre], df,
                        anchos={"Archivo": 48, "Ruta": 80, "Detalle": 90, "Observaciones": 60})


# ------------------------------------------------------------------------------
# PRINCIPAL
# ------------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Base de % de cesión a partir de los logouts del PPTO.")
    parser.add_argument("carpeta", nargs="?", help="Carpeta con los logouts (opcional)")
    parser.add_argument("--salida", help="Carpeta donde guardar el Excel (opcional)")
    args = parser.parse_args()

    carpeta = ubicar_carpeta(args.carpeta)
    if not carpeta.is_dir():
        sys.exit(f"La carpeta no existe: {carpeta}")
    archivos, no_soportados = listar_logouts(carpeta)
    if not archivos and not no_soportados:
        sys.exit(f"No hay archivos Logout_*.xlsx en: {carpeta}")

    subcarpetas = sorted({str(p.parent.relative_to(carpeta)) for p in archivos})
    print(f"Leyendo {len(archivos)} logouts de: {carpeta}")
    if len(subcarpetas) > 1:
        print(f"  (vienen de {len(subcarpetas)} subcarpetas: {', '.join(subcarpetas)})")
    base, validaciones = construir_base(carpeta, archivos, no_soportados)

    lns = sorted(base["LN"].dropna().astype(str).unique()) if not base.empty else []
    etiqueta_ln = lns[0] if len(lns) == 1 else ("varias_LN" if lns else "sin_LN")
    destino = Path(args.salida or CARPETA_SALIDA or carpeta.parent).expanduser()
    salida = destino / f"Base_Cesion_{etiqueta_ln}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"

    hojas = {
        "Base_Cesion": base,
        "Cesion_Anual": construir_anual(base),
        "Resumen": construir_resumen(base),
        "Validaciones": validaciones,
        "Notas": construir_notas(carpeta, len(archivos)),
    }
    try:
        destino.mkdir(parents=True, exist_ok=True)
        escribir_excel(salida, hojas)
    except OSError as error:
        sys.exit(f"No se pudo guardar {salida}:\n  {error}\n"
                 f"Revisa que puedas escribir en {destino} o indica otra carpeta con --salida o CARPETA_SALIDA.")

    con_cesion = int(base["Cesión capturada"].eq("Sí").sum()) if not base.empty else 0
    solo_primero = int(base["Años con cesión"].eq(str(PRIMER_ANIO)).sum()) if not base.empty else 0
    niveles = validaciones["Nivel"].value_counts() if not validaciones.empty else {}
    print("\n" + "=" * 70)
    print(f"Documentos en la base ......... {len(base)} (de {len(archivos) + len(no_soportados)} archivos)")
    print(f"Con % de cesión capturado ..... {con_cesion} ({solo_primero} solo en {PRIMER_ANIO})")
    print("Validaciones .................. " +
          ", ".join(f"{k}: {niveles.get(k, 0)}" for k in ("Error", "Revisar", "Info")))
    if not validaciones.empty and validaciones["Tipo"].str.startswith("Ningún logout trae").any():
        print(f"OJO: ningún logout trae % de cesión {ANIOS[-1]}; ver hoja Validaciones.")
    print(f"Archivo generado .............. {salida}")
    print("=" * 70)

    if ABRIR_AL_TERMINAR:
        try:
            if os.name == "nt":
                os.startfile(salida)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(salida)])
        except Exception:
            pass


if __name__ == "__main__":
    main()
