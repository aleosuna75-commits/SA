import time

from CONFIG import *

from loaders.LOAD_SBR import cargar_sbr   
from loaders.LOAD_PPTO import cargar_ppto
from loaders.LOAD_REAL import cargar_real

from transformations.LLAVES import crear_llave
from transformations.CONTABLE import procesar_contable
from transformations.SUSCRIPCION import procesar_suscripcion

from reports.EXPORT_EXCEL import exportar_excel
# El reporte Word es opcional y depende de python-docx, que no siempre
# esta instalado en el venv. Se importa protegido para que la falta de esa
# libreria no tumbe todo el proceso: el Excel es lo que si es obligatorio.
try:
    from reports.REPORTE_WORD import generar_reporte_word
    REPORTE_WORD_DISPONIBLE = True

except ModuleNotFoundError:
    REPORTE_WORD_DISPONIBLE = False
    generar_reporte_word = None

    print(
        "AVISO: python-docx no esta instalado, se omite el reporte Word.\n"
        "       Para habilitarlo: pip install python-docx\n"
        "       (el paquete se llama python-docx, NO docx)"
    )

inicio = time.perf_counter()

# Subramo
print("Cargando Subramo...")
inicio_sbr = time.perf_counter()

sbr = cargar_sbr(
    ARCHIVO_SUBRAMO
)

fin_sbr = time.perf_counter()
print(f"Subramo: {fin_sbr - inicio_sbr:.2f} segundos")


# Forecast
print("Cargando Forecast...")
inicio_ppto = time.perf_counter()

ppto = cargar_ppto(
    ARCHIVO_PPTO
)

fin_ppto = time.perf_counter()
print(f"Forecast: {fin_ppto - inicio_ppto:.2f} segundos")

print("\nPPTO")
for c in ppto.columns:
    print(c)
print(ppto.head(20))

# Real
print("Cargando Real...")
inicio_real = time.perf_counter()
real = cargar_real(
    ARCHIVO_REAL
)

fin_real = time.perf_counter()
print(f"Real: {fin_real - inicio_real:.2f} segundos")

print("\nREAL")
for c in real.columns:
     print(c)


# Contable
print("Procesando Contable...")
inicio_cont = time.perf_counter()

tablas_cont, nombres_cont = procesar_contable(
    ppto,
    real,
    sbr
)

fin_cont = time.perf_counter()
print(f"Contable: {fin_cont - inicio_cont:.2f} segundos")

# Suscripción
print("Procesando Suscripción...")
inicio_susc = time.perf_counter()

tablas_susc, nombres_susc = procesar_suscripcion(
    ppto,
    real,
    sbr
)

fin_susc = time.perf_counter()
print(f"Suscripción: {fin_susc - inicio_susc:.2f} segundos")

# Exportación Contable

print("Exportando Contable...")
inicio_exp_cont = time.perf_counter()

exportar_excel(
    tablas_cont,
    nombres_cont,
    f"{OUTPUT}\\Consulta_RP_C.xlsx"
)

fin_exp_cont = time.perf_counter()
print(f"Exportación Contable: {fin_exp_cont - inicio_exp_cont:.2f} segundos")

# Exportación Suscripción
print("Exportando Suscripción...")
inicio_exp_susc = time.perf_counter()

exportar_excel(
    tablas_susc,
    nombres_susc,
    f"{OUTPUT}\\Consulta_RP_S.xlsx"
)

fin_exp_susc = time.perf_counter()
print(f"Exportación Suscripción: {fin_exp_susc - inicio_exp_susc:.2f} segundos")

#print("Generando reporte Word...")
#inicio_rep_word = time.perf_counter()
#resumen_ln = next(
#    tabla
#    for tabla, nombre
#    in zip(tablas_cont, nombres_cont)
#    if nombre == "CONT_LN"
#)

#if not REPORTE_WORD_DISPONIBLE:
#    raise SystemExit(
#        "Falta python-docx. Instalar con: pip install python-docx"
#    )

#generar_reporte_word(
#    resumen_ln=resumen_ln,
#    archivo_docx=f"{OUTPUT}\\Draft_Rep_Val_FCST.docx",
#    carpeta_graficas=f"{OUTPUT}\\Graficas"
#)

#fin_rep_word= time.perf_counter()
#print(f"Generación de Reporte: {fin_rep_word - inicio_rep_word:.2f} segundos")

# Total
#fin = time.perf_counter()

#print(
#    f"Tiempo total: {fin-inicio:.2f} segundos"
#)

#print("\n" + "=" * 60)
#print("RESUMEN DE EJECUCION")
#print("=" * 60)

#print(f"Subramo                 : {fin_sbr - inicio_sbr:.2f}s")
#print(f"Forecast                : {fin_ppto - inicio_ppto:.2f}s")
#print(f"Real                    : {fin_real - inicio_real:.2f}s")
#print(f"Contable                : {fin_cont - inicio_cont:.2f}s")
#print(f"Suscripción             : {fin_susc - inicio_susc:.2f}s")
#print(f"Exportación Contable    : {fin_exp_cont - inicio_exp_cont:.2f}s")
#print(f"Exportación Suscripción : {fin_exp_susc - inicio_exp_susc:.2f}s")
#print(f"Generación de Reporte   : {fin_rep_word - inicio_rep_word:.2f}s")


#print("=" * 60)
#print(f"TOTAL: {fin - inicio:.2f}s")
#print("=" * 60)