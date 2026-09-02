import pandas as pd
import time
import warnings
import getpass
import os

# ==================================================
# CONFIGURACION
# ==================================================

warnings.filterwarnings('ignore')

inicio = time.perf_counter()

usuario = getpass.getuser()

xFolder = fr"C:\Users\{usuario}\OneDrive - GPV\Documentos\Planeación Financiera\Presupuestos\2027\4_Validacion"

xInputs = os.path.join(xFolder, "Inputs")
xOutputs = os.path.join(xFolder, "Inputs")
xCatalogo = os.path.join(xFolder, "Catalogo_Archivos.xlsx")

archivo_salida = os.path.join(
    xOutputs,
    "PptoTecnico2026_1.csv"
)

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

# ==================================================
# VALIDACION DE CARPETAS
# ==================================================

os.makedirs(xOutputs, exist_ok=True)

# ==================================================
# LECTURA DEL CATALOGO
# ==================================================

print("Leyendo catálogo...")

catalogo = pd.read_excel(xCatalogo)

print(f"Archivos encontrados en catálogo: {len(catalogo)}")

# ==================================================
# CARGA DE ARCHIVOS
# ==================================================

tablas = []

print("\nRuta Inputs:")
print(xInputs)
print("\nArchivos encontrados en Inputs:")

for f in os.listdir(xInputs):
    print(f)


for _, row in catalogo.iterrows():

    archivo = str(row["archivo"]).strip()
    tipo = str(row["tipo"]).strip().lower()

    ruta = os.path.join(xInputs, archivo)

    print(f"Leyendo -> {archivo}")

    try:

        if tipo == "txt":

            df = pd.read_csv(
                ruta,
                delimiter="\t",
                names=columnas,
                header=None,
                low_memory=False
            )

        elif tipo in ["excel", "xlsx"]:

            df = pd.read_excel(ruta)

        else:

            print(f"Tipo no reconocido: {tipo}")
            continue

        print(f"     Registros: {len(df):,}")

        df["Archivo_Origen"] = archivo

        tablas.append(df)

    except Exception as e:

        print(f"ERROR: {archivo}")
        print(e)

# ==================================================
# CONSOLIDACION
# ==================================================

if len(tablas) == 0:

    raise Exception(
        "No se cargó ningún archivo. Revisar catálogo."
    )

print("\nConsolidando información...")

bd_final = pd.concat(
    tablas,
    ignore_index=True
)

# ==================================================
# EXPORTACION
# ==================================================

bd_final.to_csv(
    archivo_salida,
    index=False,
    encoding="utf-8-sig"
)

# ==================================================
# RESULTADOS
# ==================================================

fin = time.perf_counter()

print("\n====================================")
print("PROCESO TERMINADO")
print("====================================")
print(f"Registros finales : {len(bd_final):,}")
print(f"Archivo generado  : {archivo_salida}")
print(f"Tiempo ejecución  : {fin - inicio:,.2f} segundos")
print("====================================")