"""Consolidacion de los extractos SAP del Presupuesto Tecnico.

Lee los archivos planos (TAB) que exporta SAP por Linea de Negocio y los
concatena en un unico CSV que consumen CONFIG.ARCHIVO_PPTO / LOAD_PPTO.

Correcciones sobre la version anterior
--------------------------------------
1. ENCODING. SAP no exporta todas las lineas en UTF-8: LN04006 viene en
   ANSI (cp1252) porque trae texto acentuado en ZSEGMENTO / BINDER_PPTO
   ("Alchemy Lineas Financieras"). pd.read_csv usa UTF-8 por omision y
   truena con UnicodeDecodeError. Ahora se intenta una cascada de
   encodings por archivo.

2. NOMBRE DEL ARCHIVO EN EL CATALOGO. El nombre trae "e" acentuada
   ("PptoTecnico2027_..."), y Excel / OneDrive pueden guardarla como un
   solo caracter (NFC) o como "e" + tilde combinante (NFD). Son cadenas
   distintas para os.path.join, asi que el archivo "existe" y aun asi
   marca FileNotFoundError. El emparejamiento ahora normaliza a NFC y
   compara sin distinguir mayusculas ni espacios sobrantes.

3. ERRORES SILENCIOSOS. El try/except imprimia el error y seguia. Si un
   archivo fallaba (4006 por encoding, 4008-Agro por nombre) la BD se
   generaba igual, incompleta, y nadie se enteraba. Ahora se acumulan los
   fallos y el proceso truena al final indicando cuales fueron.

4. TIPOS. Al concatenar, una columna que en un archivo era int64 y en
   otro float64 (ZCONTRATO, ZCORREDOR, ZMGA) quedaba float64 y el CSV
   salia con "34.0" en vez de "34"; los codigos con ceros a la izquierda
   tambien se perdian. Todo se lee como texto y se escribe tal cual viene
   de SAP. La conversion numerica es responsabilidad de utils/PARSEO.

5. MEMORIA. Ya no se guardan los 8 DataFrames en una lista para un
   pd.concat final (~1.9 millones de renglones): cada archivo se escribe
   al CSV de salida en cuanto se lee.

6. NOMBRE DE SALIDA. Escribe "PptoTecnico2026.csv", que es exactamente lo
   que espera CONFIG.ARCHIVO_PPTO (antes decia "PptoTecnico2026_1.csv").
"""

import getpass
import os
import time
import unicodedata
import warnings

import pandas as pd

# ==================================================
# CONFIGURACION
# ==================================================

warnings.filterwarnings("ignore")

inicio = time.perf_counter()

usuario = getpass.getuser()

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\2027\4_Validacion"

# Permite sobreescribir la ruta base sin tocar el codigo (util para probar
# fuera de la maquina del usuario).
xFolder = os.environ.get("PPTO_FOLDER", xFolder)

xInputs = os.path.join(xFolder, "Inputs")
xOutputs = os.path.join(xFolder, "Inputs")
xCatalogo = os.path.join(xFolder, "Catalogo_Archivos.xlsx")

archivo_salida = os.path.join(
    xOutputs,
    "PptoTecnico2026.csv"
)

# Encodings a intentar, en orden. utf-8-sig cubre UTF-8 con y sin BOM;
# cp1252 es lo que exporta SAP/Windows en ANSI; latin-1 nunca falla y
# queda como ultimo recurso.
ENCODINGS = ["utf-8-sig", "cp1252", "latin-1"]

# ==================================================
# COLUMNAS SAP
# ==================================================

columnas = [
        '/ERP/CHRTACCT',
        '/ERP/GL_ACCT',
        '/ERP/CATEGORY',
        'ZSOURCE',
        '/ERP/CO_AREA',
        '/ERP/COMPCODE',
        '/ERP/FUNCAREA',
        'ZPAISCEDN',
        '/ERP/PRODUCT',
        'ZCUSTOMER',
        '0CURRENCY',
        '/ERP/TWAERS',
        '/ERP/COSTCNTR',
        '/ERP/PROFTCTR',
        'ZCONTRATO',
        'ZPLANYEAR',
        '0FISCPER',
        '0FISCPER3',
        '0FISCYEAR',
        '0FISCVARNT',
        '0CALMONTH',
        '0CALMONTH2',
        '0CALYEAR',
        'ZINDICES',
        'ZCONCEPTO',
        'ZDISTCHRP',
        'ZDISTCHGS',
        'ZTIPOREAS',
        'ZTIPOCES',
        'ZMGA',
        'ZOFICN_RP',
        'ZOFICN_GS',
        'ZSUSCYEAR',
        'ZCEDENTE',
        'ZCORREDOR',
        'ZTIPVENTA',
        'ZSEGMENTO',
        'ZCICCULTV',
        '/ERP/AMOUNT_T',
        '/ERP/AMOUNT',
        'MANDT',
        'ZREGIONRP',
        'BINDER_PPTO',
        'FW/CF'
]

COLUMNA_IMPORTE = "/ERP/AMOUNT"


# ==================================================
# UTILERIAS
# ==================================================

def clave(nombre):
    """Normaliza un nombre de archivo para poder compararlo.

    Unifica la forma Unicode (NFC), quita espacios de los extremos y
    elimina la distincion de mayusculas. Con esto "PptoTecnico2027_
    LN04008-Agro.txt" escrito en Excel empata con el archivo en disco
    aunque la "e" acentuada este codificada distinto.
    """

    return unicodedata.normalize("NFC", str(nombre)).strip().casefold()


def renglones_de_datos(ruta, encoding):
    """Cuenta los renglones con datos del archivo plano.

    El extracto de SAP trae un renglon en blanco al inicio y otro al
    final; pandas los ignora. Se cuentan aparte para verificar que no se
    haya perdido informacion al parsear.
    """

    total = 0

    with open(ruta, "r", encoding=encoding, errors="strict", newline="") as f:
        for linea in f:
            if linea.strip("\r\n").strip():
                total += 1

    return total


def leer_txt_sap(ruta):
    """Lee un extracto SAP probando varios encodings.

    Devuelve (DataFrame, encoding_usado). Todo se lee como texto para no
    alterar los valores originales: los codigos conservan sus ceros a la
    izquierda y los enteros no se vuelven "34.0" al concatenar archivos
    con tipos distintos.
    """

    ultimo_error = None

    for encoding in ENCODINGS:

        try:

            df = pd.read_csv(
                ruta,
                delimiter="\t",
                names=columnas,
                header=None,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
                skip_blank_lines=True,
                encoding=encoding,
                low_memory=False
            )

            esperados = renglones_de_datos(ruta, encoding)

            if len(df) != esperados:
                raise ValueError(
                    f"Se leyeron {len(df):,} renglones pero el archivo "
                    f"tiene {esperados:,} con datos."
                )

            return df, encoding

        except (UnicodeDecodeError, UnicodeError) as e:

            ultimo_error = e
            continue

    raise UnicodeDecodeError(
        getattr(ultimo_error, "encoding", "utf-8"),
        b"", 0, 1,
        f"no se pudo decodificar con ninguno de {ENCODINGS}"
    )


def total_importe(serie):
    """Suma la columna de importes que viene como texto con separador de miles."""

    return pd.to_numeric(
        serie.astype("string")
             .str.replace(",", "", regex=False)
             .str.strip()
             .replace("", None),
        errors="coerce"
    ).sum()


# ==================================================
# VALIDACION DE CARPETAS
# ==================================================

if not os.path.isdir(xInputs):
    raise FileNotFoundError(f"No existe la carpeta de Inputs: {xInputs}")

os.makedirs(xOutputs, exist_ok=True)

# ==================================================
# ARCHIVOS EN DISCO
# ==================================================

print("Ruta Inputs:")
print(xInputs)

en_disco = {}

for f in sorted(os.listdir(xInputs)):

    ruta = os.path.join(xInputs, f)

    if os.path.isfile(ruta):
        en_disco[clave(f)] = f

print(f"\nArchivos encontrados en Inputs: {len(en_disco)}")

for f in sorted(en_disco.values()):
    print(f"   {f}")

# ==================================================
# LECTURA DEL CATALOGO
# ==================================================
# El catalogo es opcional: si no esta, se toman todos los .txt de Inputs.

pendientes = []

if os.path.isfile(xCatalogo):

    print("\nLeyendo catálogo...")

    catalogo = pd.read_excel(xCatalogo)

    print(f"Archivos listados en catálogo: {len(catalogo)}")

    faltantes = []

    for _, row in catalogo.iterrows():

        archivo = str(row["archivo"]).strip()
        tipo = str(row["tipo"]).strip().lower()

        real = en_disco.get(clave(archivo))

        if real is None:
            faltantes.append(archivo)
            continue

        pendientes.append((real, tipo))

    if faltantes:
        raise FileNotFoundError(
            "El catálogo lista archivos que no están en Inputs:\n  - "
            + "\n  - ".join(faltantes)
            + "\n\nArchivos disponibles:\n  - "
            + "\n  - ".join(sorted(en_disco.values()))
        )

    catalogados = {clave(a) for a, _ in pendientes}

    sobrantes = [
        real for k, real in en_disco.items()
        if k not in catalogados and real.lower().endswith(".txt")
    ]

    if sobrantes:
        print("\nAVISO: hay .txt en Inputs que NO están en el catálogo")
        print("       (no se van a cargar):")
        for s in sorted(sobrantes):
            print(f"   {s}")

else:

    print(f"\nAVISO: no se encontró el catálogo ({xCatalogo}).")
    print("       Se cargan todos los .txt de Inputs.")

    pendientes = [
        (real, "txt")
        for real in sorted(en_disco.values())
        if real.lower().endswith(".txt")
    ]

if not pendientes:
    raise Exception("No hay archivos que cargar. Revisar catálogo / Inputs.")

# ==================================================
# CARGA Y ESCRITURA INCREMENTAL
# ==================================================

print("\nConsolidando información...")

if os.path.exists(archivo_salida):
    os.remove(archivo_salida)

resumen = []
errores = []
total_renglones = 0
gran_total = 0.0
primero = True

for archivo, tipo in pendientes:

    ruta = os.path.join(xInputs, archivo)

    print(f"\nLeyendo -> {archivo}")

    try:

        if tipo == "txt":

            df, encoding = leer_txt_sap(ruta)

        elif tipo in ("excel", "xlsx"):

            df = pd.read_excel(ruta, dtype=str).fillna("")
            df = df.reindex(columns=columnas, fill_value="")
            encoding = "xlsx"

        else:

            raise ValueError(f"Tipo no reconocido en catálogo: '{tipo}'")

        if len(df.columns) != len(columnas):
            raise ValueError(
                f"Se esperaban {len(columnas)} columnas y llegaron "
                f"{len(df.columns)}."
            )

        df["Archivo_Origen"] = archivo

        importe = total_importe(df[COLUMNA_IMPORTE])

        print(f"     Encoding  : {encoding}")
        print(f"     Registros : {len(df):,}")
        print(f"     Importe   : {importe:,.2f}")

        df.to_csv(
            archivo_salida,
            index=False,
            header=primero,
            mode="w" if primero else "a",
            encoding="utf-8-sig",
            lineterminator="\n"
        )

        primero = False

        total_renglones += len(df)
        gran_total += importe

        resumen.append({
            "Archivo": archivo,
            "Encoding": encoding,
            "Registros": len(df),
            "Importe": importe
        })

        del df

    except Exception as e:

        print(f"     ERROR: {type(e).__name__}: {e}")

        errores.append((archivo, f"{type(e).__name__}: {e}"))

# ==================================================
# VALIDACION FINAL
# ==================================================

if errores:

    detalle = "\n  - ".join(f"{a}: {m}" for a, m in errores)

    raise Exception(
        "La base NO se generó completa. Fallaron estos archivos:\n  - "
        + detalle
    )

print("\n" + "=" * 60)
print("RESUMEN POR ARCHIVO")
print("=" * 60)
print(
    pd.DataFrame(resumen)
    .to_string(index=False, formatters={"Importe": "{:,.2f}".format})
)

# El CSV debe tener exactamente un renglon por registro mas el encabezado.
with open(archivo_salida, "r", encoding="utf-8-sig", newline="") as f:
    lineas_csv = sum(1 for _ in f)

esperadas = total_renglones + 1

if lineas_csv != esperadas:
    raise ValueError(
        f"El CSV generado tiene {lineas_csv:,} líneas y se esperaban "
        f"{esperadas:,} (encabezado + {total_renglones:,} registros)."
    )

# ==================================================
# RESULTADOS
# ==================================================

fin = time.perf_counter()

print("\n====================================")
print("PROCESO TERMINADO")
print("====================================")
print(f"Archivos cargados : {len(resumen)}")
print(f"Registros finales : {total_renglones:,}")
print(f"Importe total     : {gran_total:,.2f}")
print(f"Archivo generado  : {archivo_salida}")
print(f"Tiempo ejecución  : {fin - inicio:,.2f} segundos")
print("====================================")
