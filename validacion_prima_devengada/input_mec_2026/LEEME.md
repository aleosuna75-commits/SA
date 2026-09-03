# Input MEC 2026 · real enero–julio + FCST agosto–diciembre

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

Generado con `scripts_actualizados/construir_input_mec.py` a partir de `BDReal26.xlsx` (hoja BD) y `FCST2026.xlsx` (hoja Ppto2026).

Reproducir: poner los dos Excel, el script y `tc_mensual_bd.csv` en la misma carpeta y correr `python3 construir_input_mec.py`. El corte está en las constantes `FRONTERA_REAL = 202607` y `VENTANA_PPTO = (202608, 202612)`.

## Lo que quedó

| | Meses | Filas | Prima emitida (MXN) |
|---|---|---|---|
| Real (BD) | 202601–202607 | 7,629 | 13,255,232,986 |
| FCST | 202608–202612 | 734 | 9,072,059,729 |
| **2026 completo** | **12 meses, sin huecos** | **8,363** | **22,327,292,716** |

Para referencia: el presupuesto 2026 de Integración Dim trae 23,367 M y el reforecast 9+3 trae 22,155 M, así que 22,327 M queda entre los dos.

| Archivo | Contenido |
|---|---|
| `Input_MEC_Devengamiento.xlsx` | hojas Input (8,363 filas), Cobertura por fuente × LN2 y Validaciones |
| `TriangulosPrimaDevengada.csv` | triángulo por LN2 × cohorte × antigüedad que consume el MEC |
| `Registros_Vigencia_MEC_202601_202607.csv` | vigencias de los registros de 2026 (3,433 combinaciones) |

## Cuatro cosas que hay que saber antes de usarlo

**1. El FCST viene en dólares y se convirtió a pesos.** Todas sus filas traen `Moneda = 31` (USD) y su total, 1,215.7 M USD, corresponde a la cifra de control de 21,882.6 M que el propio archivo trae arriba, con un TC plano de 18.0. Aquí se convirtió mes a mes con el TC de cierre de la base BEL-IRR-MR (17.62 en agosto a 18.00 en diciembre), que da 9,072 M para agosto–diciembre; con el TC plano de 18.0 habrían sido 9,169 M, un 1% más. La regla `V16` deja constancia de la conversión. Si prefieres correr todo en dólares, `MONEDA = "USD"` y no se convierte nada.

**2. El FCST no trae año de suscripción 2026.** Sus años van de 2021 a 2025, así que toda la prima proyectada de agosto a diciembre cuelga de cohortes anteriores, ancladas además a enero de cada año porque el archivo sólo da el año. Bajo el FND calibrado esto **no afecta la reserva**, porque ese factor se indexa por antigüedad de registro y no por cohorte de vigencia. Sí deforma el triángulo por cohorte, que es un producto de trazabilidad. Queda reportado en la regla `V19`. Si el equipo de presupuesto puede etiquetar la suscripción 2026, el triángulo mejora sin tocar el modelo.

**3. La proyección se queda 6.9% corta contra lo ya realizado.** El FCST proyecta los doce meses, así que sus meses ya conocidos se pueden contrastar contra el real: enero–julio proyectaba 12,342 M contra 13,255 M reales. Por mes va de −23.8% (febrero) a +8.6% (julio), con tres meses fuera de ±10%. No es un error del input —son dos cosas distintas, presupuesto y realidad— pero conviene tenerlo presente al leer los cinco meses proyectados. Está en la regla `V9`.

**4. No se pisó el histórico de vigencias.** `BDReal26.xlsx` cubre siete meses de registro, y la curva PF+ de cartera —la que usa el no proporcional— se estima de ese archivo. Reescribirlo con siete meses habría degradado la curva, así que el script guarda las vigencias de 2026 aparte y deja intacto `Registros_Vigencia_MEC.csv`. Para regenerar el histórico hay que correrlo con una BD que cubra al menos 24 meses de registro (`MESES_MIN_VIGENCIAS`). Queda en la regla `V18`.

## Comprobación de punta a punta

Con este input y el FND calibrado, la prima no devengada al 31 de diciembre de 2026 sale de 10,619 M MXN (590 M USD al TC de cierre), es decir una prima devengada del año de 11,708 M MXN. Es una cifra indicativa a grano mes: el cálculo oficial corre registro por registro dentro del reforecast. Sirve para confirmar que la cadena completa —input, factor, reserva— corre sin huecos y da un orden de magnitud coherente con la RRC real (559 M USD de prima no devengada a mayo de 2026).

## Otros cambios que trajo esta corrida

El script no podía leer ninguno de los dos archivos tal como vienen: ambos traen filas de títulos y totales antes del encabezado (la BD lo tiene en la fila 2 y el FCST en la 3), y leerlos con el encabezado en la primera fila devolvía columnas `Unnamed` y el script abortaba diciendo que faltaban columnas. Ahora detecta la fila del encabezado buscando las columnas clave en las primeras filas, tanto para la BD como para el FCST.

También homologa el ramo: el FCST abre subramos (31, 35 y 39 de Accidentes y Enfermedades; 71 y 73 de catastróficos) y la BD real los trae agregados en 30 y 70, así que se colapsan al grano de la BD para que las dos fuentes sumen en el mismo eje (regla `V14`). Y la nueva regla `V17` reporta qué meses aporta cada fuente y si el año quedó con huecos.
