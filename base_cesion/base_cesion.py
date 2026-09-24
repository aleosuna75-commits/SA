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

La columna B de "Porcentaje de Cesión" viene vacía en los logouts: el primer
año presupuestado (2027) cae en la columna C. Si algún día viene algo en B, el
script lo reporta en la hoja Validaciones en lugar de ignorarlo.

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

Si falta openpyxl o pandas, el script los instala solo con pip.
================================================================================
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import re
import site
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path


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

TOLERANCIA = 1e-6
PAQUETES = {"openpyxl": "openpyxl", "pandas": "pandas"}  # módulo -> paquete pip


# ------------------------------------------------------------------------------
# PAQUETERÍA
# ------------------------------------------------------------------------------
def asegurar_paquetes():
    """Instala con pip (en el mismo Python que corre el script) lo que falte."""
    faltantes = [pip for mod, pip in PAQUETES.items()
                 if importlib.util.find_spec(mod) is None]
    if not faltantes:
        return
    print(f"Instalando paquetería faltante: {', '.join(faltantes)} ...")
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    intentos = [base + faltantes, base + ["--user"] + faltantes]
    for cmd in intentos:
        try:
            subprocess.check_call(cmd)
            break
        except (subprocess.CalledProcessError, OSError):
            # Si pip no existe en este Python, intentar habilitarlo una vez.
            subprocess.call([sys.executable, "-m", "ensurepip", "--upgrade"])
    else:
        sys.exit(
            "\nNo se pudo instalar la paquetería automáticamente.\n"
            "Instálala a mano desde la terminal de VSCode con:\n"
            f'    "{sys.executable}" -m pip install {" ".join(faltantes)}\n'
            "Si la red de la oficina usa proxy, agrega: --proxy http://usuario:clave@proxy:puerto"
        )
    # Una instalación con --user puede caer en una carpeta que aún no está en sys.path.
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    importlib.invalidate_caches()


asegurar_paquetes()

import pandas as pd  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402


# ------------------------------------------------------------------------------
# UBICAR LA CARPETA DE LOGOUTS
# ------------------------------------------------------------------------------
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


def hay_logouts(carpeta):
    patron = "**/Logout_*.xls[xm]" if BUSCAR_EN_SUBCARPETAS else "Logout_*.xls[xm]"
    return any(not p.name.startswith("~$") for p in carpeta.glob(patron))


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
    for docs in carpetas_documentos():
        if (docs / NOMBRE_CARPETA).is_dir():
            return docs / NOMBRE_CARPETA
    junto_al_script = Path(__file__).resolve().parent
    for c in (junto_al_script / NOMBRE_CARPETA, junto_al_script):
        if c.is_dir() and hay_logouts(c):
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
    patron = "**/*.xls[xm]" if BUSCAR_EN_SUBCARPETAS else "*.xls[xm]"
    return sorted(
        (p for p in carpeta.glob(patron)
         if p.name.lower().startswith("logout_") and not p.name.startswith("~$")),
        key=lambda p: str(p).lower(),
    )


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
MAX_COLUMNAS = COL_PRIMER_ANIO + NUM_ANIOS + 2


def normalizar(texto):
    if texto is None:
        return ""
    sin_acentos = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(ch for ch in sin_acentos if not unicodedata.combining(ch))
    return " ".join(sin_acentos.lower().split())


def a_numero(valor):
    """Convierte a float: 0.8, '80%', '0,8', ' 80 % '. Devuelve (numero, es_texto_invalido)."""
    if valor is None or isinstance(valor, bool):
        return None, False
    if isinstance(valor, (int, float)):
        return float(valor), False
    texto = str(valor).strip()
    if texto == "":
        return None, False
    es_pct = texto.endswith("%")
    texto = texto.rstrip("%").strip().replace(",", ".")
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
    return None if valor in (None, "") else str(valor).strip()


def a_si_no(valor):
    if valor is None or str(valor).strip() == "":
        return None
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    texto = normalizar(valor)
    if texto in ("verdadero", "true", "si", "1"):
        return "Sí"
    if texto in ("falso", "false", "no", "0"):
        return "No"
    return str(valor)


def leer_logout(ruta):
    """Devuelve (registro, lista_de_validaciones) para un archivo."""
    avisos = []

    def avisar(nivel, tipo, detalle):
        avisos.append({"Archivo": ruta.name, "Nivel": nivel, "Tipo": tipo, "Detalle": detalle})

    registro = {"Archivo": ruta.name}
    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        if HOJA_LOGOUT in wb.sheetnames:
            ws = wb[HOJA_LOGOUT]
        else:
            ws = wb.worksheets[0]
            avisar("Revisar", "Hoja no encontrada",
                   f'No existe la hoja "{HOJA_LOGOUT}"; se leyó "{ws.title}".')
        filas = [list(f) for f in ws.iter_rows(min_row=1, max_row=MAX_FILAS_ENCABEZADO,
                                               max_col=MAX_COLUMNAS, values_only=True)]
    finally:
        wb.close()

    fila_de = {}
    for fila in filas:
        clave = ETIQUETAS.get(normalizar(fila[0] if fila else None))
        if clave and clave not in fila_de:
            fila_de[clave] = fila + [None] * (MAX_COLUMNAS - len(fila))
    faltan = [k for k in ETIQUETAS.values() if k not in fila_de]
    if faltan:
        avisar("Error", "Etiquetas no encontradas",
               "No se encontraron en la columna A: " + ", ".join(faltan))

    def celda(clave, col):  # col: 1 = A, 2 = B, ...
        fila = fila_de.get(clave)
        return fila[col - 1] if fila else None

    def porcentaje(clave, col, nombre):
        valor = celda(clave, col)
        numero, invalido = a_numero(valor)
        if invalido:
            avisar("Error", "Valor no numérico", f"{nombre}: '{valor}'")
        elif numero is not None and not (-TOLERANCIA <= numero <= 1 + TOLERANCIA):
            avisar("Revisar", "Porcentaje fuera de 0%-100%",
                   f"{nombre} = {numero:g} (¿capturado como {numero:g}% en lugar de {numero / 100:g}?)")
        return numero

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

    # --- % de cesión y % comisiones del cedido por año --------------------------
    for clave, prefijo in (("cesion", "% Cesión"), ("comision", "% Com. Cedido")):
        valores = [porcentaje(clave, COL_PRIMER_ANIO + i, f"{prefijo} {anio}")
                   for i, anio in enumerate(ANIOS)]
        anios_capturados = [a for a, v in zip(ANIOS, valores) if v is not None]
        if ARRASTRAR_ULTIMO_ANIO and anios_capturados:
            ultimo = None
            for i, v in enumerate(valores):
                if v is not None:
                    ultimo = v
                elif ultimo is not None:
                    valores[i] = ultimo
        for anio, v in zip(ANIOS, valores):
            registro[f"{prefijo} {anio}"] = v
        registro[f"_capturados_{clave}"] = anios_capturados
        # Valores fuera del rango de años esperado (columna B o después del último año)
        fuera = [(get_column_letter(c), celda(clave, c))
                 for c in list(range(2, COL_PRIMER_ANIO)) +
                 list(range(COL_PRIMER_ANIO + NUM_ANIOS, MAX_COLUMNAS + 1))
                 if celda(clave, c) not in (None, "")]
        if fuera:
            avisar("Revisar", "Valor fuera de las columnas de años",
                   f"{prefijo}: " + ", ".join(f"{c}={v}" for c, v in fuera) +
                   f" (se esperan solo en {get_column_letter(COL_PRIMER_ANIO)}.."
                   f"{get_column_letter(COL_PRIMER_ANIO + NUM_ANIOS - 1)})")

    registro["GS"] = a_si_no(celda("mga", 6))
    cesion_capturada = bool(registro["_capturados_cesion"])
    registro["Cesión capturada"] = "Sí" if cesion_capturada else "No"

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
    if capturado and abs(total - 1) > TOLERANCIA:
        avisar("Revisar", "Tipo Retrocesión no suma 100%", f"Total = {total:.2%}")
    if not capturado:
        avisar("Revisar", "Tipo Retrocesión vacío", "No hay % en Tradicional/Retro Espec./Fronting/Retención")
    especifica = (registro["% Retro Espec."] or 0) + (registro["% Fronting"] or 0)
    if especifica > TOLERANCIA and not cesion_capturada:
        avisar("Revisar", "Falta % de cesión",
               f"Retro Espec. + Fronting = {especifica:.0%} pero no hay % de cesión capturado")
    if cesion_capturada and especifica <= TOLERANCIA:
        avisar("Revisar", "Cesión sin Retro Espec./Fronting",
               "Hay % de cesión capturado pero el tipo de retrocesión es 100% Tradicional/Retención")
    if cesion_capturada and set(registro["_capturados_cesion"]) != set(registro["_capturados_comision"]):
        avisar("Info", "Años distintos en cesión y comisión",
               f"Cesión: {registro['_capturados_cesion']}; Comisión: {registro['_capturados_comision']}")
    if cesion_capturada and len(registro["_capturados_cesion"]) < NUM_ANIOS:
        avisar("Info", "Cesión no capturada en todos los años",
               "Años con cesión: " + ", ".join(map(str, registro["_capturados_cesion"])))
    if "comb" in normalizar(registro["Tipo Venta"]) and registro["% Renov."] is None:
        avisar("Revisar", "Falta % Renov.", "Tipo de venta combinado sin % de renovación")

    registro["Ruta"] = str(ruta)
    return registro, avisos


# ------------------------------------------------------------------------------
# ARMADO DE LA BASE Y ESCRITURA DEL EXCEL
# ------------------------------------------------------------------------------
LLAVES = ["LN", "TR", "Cedente", "Corredor", "Contrato", "Tipo Venta"]


def construir_base(archivos):
    registros, validaciones = [], []
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

    columnas = (["Archivo"] + LLAVES[:4] + ["Of. Rep.", "Contrato", "Tipo Venta", "% Renov.", "MGA"]
                + [f"% {t}" for t in TIPOS_RETRO] + ["% Total Retrocesión", "Cesión capturada"]
                + [f"% Cesión {a}" for a in ANIOS] + [f"% Com. Cedido {a}" for a in ANIOS]
                + ["GS", "Versión archivo", "Observaciones", "Ruta"])
    base = pd.DataFrame(registros)
    if base.empty:
        return pd.DataFrame(columns=columnas), pd.DataFrame(validaciones)

    # Documentos repetidos (misma llave en más de un archivo, p. ej. v1 y v2)
    repetidos = base[base.duplicated(LLAVES, keep=False)]
    for _, fila in repetidos.iterrows():
        otros = repetidos[(repetidos[LLAVES].astype(str) == fila[LLAVES].astype(str)).all(axis=1)
                          & (repetidos["Archivo"] != fila["Archivo"])]["Archivo"]
        validaciones.append({"Archivo": fila["Archivo"], "Nivel": "Revisar",
                             "Tipo": "Documento repetido",
                             "Detalle": "Misma LN/TR/Cedente/Corredor/Contrato/Venta que: " + ", ".join(otros)})

    # Códigos como enteros (sin ".0") y porcentajes como número aunque vengan vacíos
    for c in ["TR", "Of. Rep.", "Cedente", "Corredor", "Contrato", "Versión archivo"]:
        numeros = pd.to_numeric(base[c], errors="coerce")
        if numeros.notna().sum() == base[c].notna().sum():
            base[c] = numeros.round().astype("Int64")
    for c in [c for c in columnas if c.startswith("%") and c in base.columns]:
        base[c] = pd.to_numeric(base[c], errors="coerce").astype("float64")

    val = pd.DataFrame(validaciones, columns=["Archivo", "Nivel", "Tipo", "Detalle"])
    resumen_obs = (val[val["Nivel"] != "Info"].groupby("Archivo")["Tipo"]
                   .apply(lambda s: "; ".join(dict.fromkeys(s))))
    base["Observaciones"] = base["Archivo"].map(resumen_obs)
    base = base.reindex(columns=columnas)
    base = base.sort_values(["LN", "TR", "Cedente", "Corredor", "Contrato", "Archivo"],
                            key=lambda s: s.astype(str) if s.name in ("LN", "Archivo")
                            else pd.to_numeric(s, errors="coerce"),
                            na_position="first")
    orden_nivel = {"Error": 0, "Revisar": 1, "Info": 2}
    val = val.sort_values(["Nivel", "Archivo", "Tipo"], key=lambda s: s.map(orden_nivel)
                          if s.name == "Nivel" else s)
    return base.reset_index(drop=True), val.reset_index(drop=True)


def construir_anual(base):
    ids = ["Archivo"] + LLAVES + ["Cesión capturada"]
    filas = []
    for _, doc in base.iterrows():
        for anio in ANIOS:
            fila = {c: doc[c] for c in ids}
            fila["Año"] = anio
            fila["% Cesión"] = doc[f"% Cesión {anio}"]
            fila["% Com. Cedido"] = doc[f"% Com. Cedido {anio}"]
            filas.append(fila)
    return pd.DataFrame(filas, columns=ids + ["Año", "% Cesión", "% Com. Cedido"])


def construir_resumen(base):
    if base.empty:
        return pd.DataFrame()
    b = base.assign(_con=base["Cesión capturada"].eq("Sí"),
                    _obs=base["Observaciones"].notna())
    col = f"% Cesión {PRIMER_ANIO}"
    resumen = b.groupby(["LN", "TR"], dropna=False).agg(
        **{"Documentos": ("Archivo", "count"),
           "Con % cesión": ("_con", "sum"),
           "Con observaciones": ("_obs", "sum"),
           f"% Cesión {PRIMER_ANIO} mín.": (col, "min"),
           f"% Cesión {PRIMER_ANIO} promedio simple": (col, "mean"),
           f"% Cesión {PRIMER_ANIO} máx.": (col, "max")}
    ).reset_index()
    total = pd.DataFrame([{"LN": "TOTAL", "Documentos": len(b), "Con % cesión": int(b["_con"].sum()),
                           "Con observaciones": int(b["_obs"].sum()),
                           f"% Cesión {PRIMER_ANIO} mín.": b[col].min(),
                           f"% Cesión {PRIMER_ANIO} promedio simple": b[col].mean(),
                           f"% Cesión {PRIMER_ANIO} máx.": b[col].max()}])
    return pd.concat([resumen, total], ignore_index=True)


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
        ("Contrato", "Contrato, col. B (vacío si el documento no tiene contrato)"),
        ("Tipo Venta / % Renov.", "Tipo Venta, col. B / col. C"),
        ("% Tradicional ... % Retención", "Porcentaje, cols. B..E (tabla Tipo Retrocesión)"),
        ("% Cesión <año>", f"Porcentaje de Cesión, cols. {anios} = {ANIOS[0]}..{ANIOS[-1]}"),
        ("% Com. Cedido <año>", f"% Comisiones del Cedido, cols. {anios} = {ANIOS[0]}..{ANIOS[-1]}"),
        ("GS", "MGA, col. F (casilla GS de la tabla de cesión)"),
        ("Cesión capturada", "Sí = hay al menos un año con % de cesión en el logout"),
        ("Años sin captura", "Se arrastró el último año capturado" if ARRASTRAR_ULTIMO_ANIO
         else "Se dejan vacíos, tal como vienen en el logout"),
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
        letra = get_column_letter(i)
        es_pct = str(nombre).startswith("%")
        if es_pct:
            for (celda,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                celda.number_format = "0.00%"
        muestra = [len(str(nombre)) * (0.6 if es_pct else 1)] + [len(str(v)) for v in df[nombre].head(200) if pd.notna(v)]
        ancho = (anchos or {}).get(nombre, min(max(muestra) + 2, 60))
        ws.column_dimensions[letra].width = max(ancho, 9 if es_pct else 6)


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
    archivos = listar_logouts(carpeta)
    if not archivos:
        sys.exit(f"No hay archivos Logout_*.xlsx en: {carpeta}")

    print(f"Leyendo {len(archivos)} logouts de: {carpeta}")
    base, validaciones = construir_base(archivos)

    lns = sorted(base["LN"].dropna().astype(str).unique()) if not base.empty else []
    etiqueta_ln = lns[0] if len(lns) == 1 else ("varias_LN" if lns else "sin_LN")
    destino = Path(args.salida or CARPETA_SALIDA or carpeta.parent).expanduser()
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / f"Base_Cesion_{etiqueta_ln}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"

    hojas = {
        "Base_Cesion": base,
        "Cesion_Anual": construir_anual(base),
        "Resumen": construir_resumen(base),
        "Validaciones": validaciones,
        "Notas": construir_notas(carpeta, len(archivos)),
    }
    try:
        escribir_excel(salida, hojas)
    except PermissionError:
        sys.exit(f"No se pudo guardar {salida}. ¿Está abierto en Excel? Ciérralo y vuelve a correr.")

    con_cesion = int(base["Cesión capturada"].eq("Sí").sum()) if not base.empty else 0
    niveles = validaciones["Nivel"].value_counts() if not validaciones.empty else {}
    print("\n" + "=" * 70)
    print(f"Documentos en la base ......... {len(base)} (de {len(archivos)} archivos)")
    print(f"Con % de cesión capturado ..... {con_cesion}")
    print("Validaciones .................. " +
          ", ".join(f"{k}: {niveles.get(k, 0)}" for k in ("Error", "Revisar", "Info")))
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
