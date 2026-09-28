# Proyección de índices y montos de reservas (202609 – 202712)

Dos scripts de Python pensados para correr desde VSCode (F5 o *Run Python File*). Si falta alguna paquetería, el propio script la instala en el intérprete activo. Para reproducir las cifras exactas, las versiones validadas están en `requirements.txt`.

| Script | Qué hace |
|---|---|
| `llenar_bd_rfv.py` | Herramienta **opcional, fuera del proceso**: llena una BD_ RFV vacía desde `Res_Rvas_2025` y `Res_Rvas_2026` con el criterio de la BD de Daños. La proyección ya no la ejecuta; lee la BD de Fianzas que tú llenas. |
| `proyeccion_reservas.py` | Proyecta de **202609 a 202712** `HParametros_2026` (índices y LAGs “Real”), `BD_Montos_RRC_SONR` (Daños) y `BD_ RFV` (Fianzas), con el mismo formato de los archivos originales, usando suavizamiento exponencial (Holt / Holt-Winters / SES). |
| `dashboard.py` | Arma el **dashboard de Excel** de índices y reservas (real y proyectado) a partir de las salidas. Lo llama `proyeccion_reservas.py` al final; también se puede correr solo (ver sección 5). |
| `dashboard_html.py` | Arma el mismo dashboard en **HTML** (un solo archivo, sin internet), con tooltips, vista de tabla y modo oscuro. |
| `excel_fiel.py` | Módulo auxiliar que usan los dos scripts para guardar los libros sin perder formato (ver sección 4). |
| `tipo_cambio.py` | Supuesto de tipo de cambio de Inversiones (`TC_Real_Esti.xlsx`, hoja TC: **FCST** 2026 y **FCST 2027**) que se escribe en la columna TC. Actualízalo cuando haya un nuevo pronóstico. |

## Cómo correrlo

1. Copia las dos BD a `proyeccion_indices/entradas/`: `BD_ BEL - IRR - MR.xlsx` (Daños) y `BD_ RFV.xlsx` (Fianzas, **ya llena** con la historia real hasta el último mes). Los archivos de entrada no se modifican.
2. Ejecuta `proyeccion_reservas.py`. Tarda alrededor de un minuto. Genera:
   - `salidas/BD_ BEL - IRR - MR_Proyeccion.xlsx`
   - `salidas/BD_ RFV_Proyeccion.xlsx`
   - `salidas/Diagnostico_Proyeccion.xlsx`: metodología, validación, modelos por serie, intervalos y alertas.
   - `salidas/Graficas_Proyeccion.pdf`: historia contra proyección de cada serie.
   - `salidas/Dashboard_Indices_Reservas.xlsx` y `.html`: dashboards interactivos (sección 5).

Los parámetros (periodos, tipo de cambio 2027, resaltado de celdas, etc.) están en la sección **CONFIGURACIÓN** al inicio de cada script.

Protecciones incluidas:

- Si algún archivo de salida está abierto en Excel, o no se puede escribir en `salidas/`, el script avisa **antes** de calcular.
- Si algún mes a proyectar ya trae cifras reales, se detiene en lugar de sobrescribirlas. En ese caso mueve `PERIODO_INICIO`.
- Si el último mes real (`PERIODO_INICIO − 1`) está vacío en algún concepto que el mes anterior sí traía (mes cargado a medias), también se detiene. Si solo falta un ramo, lo deja como alerta en el diagnóstico (puede ser una cartera extinta). Las cifras menores a 1 USD (ruido de redondeo de SAP, como 3e-12) cuentan como cero.

> Las carpetas `entradas/` y `salidas/` y cualquier `.xlsx` están excluidas de git (el repositorio es público y los datos son confidenciales).

## 1. Herramienta opcional: `llenar_bd_rfv.py` (ya no es parte del proceso)

La proyección lee la `BD_ RFV.xlsx` que tú llenas. Este script queda solo por si algún día hace falta llenar una BD de Fianzas vacía desde los Res_Rvas (se corre solo: lee `entradas/Res_Rvas_2025.xlsx`, `Res_Rvas_2026.xlsx` y la plantilla `entradas/BD_ RFV.xlsx`, y escribe `salidas/BD_ RFV.xlsx`). Lo que sigue documenta su criterio.

El criterio se obtuvo reconstruyendo celda por celda la hoja de referencia de Daños: RRC coincide en 312 de 312 celdas y SONR en 288 de 288. Dos verificadores independientes recalcularon las 480 celdas de Fianzas sin diferencias.

- **Fuente**: hoja `BacktestingFIANZAS`, columnas del escenario **SAP** (fila 1 = `SAP`, “12REALES – BEL REAL”), mismo periodo, transpuestas (los ramos pasan a columnas).
- **Conceptos**:

  | Bloque SAP | Concepto en la BD |
  |---|---|
  | `NETO` | `RFV NETO` |
  | `BRUTO` | `RFV BRUTO` |
  | `IRR` | `RFV IRR` |
  | `CONTIGENCIA SDO` | `RCONT` |

- **Moneda**: la BD está en USD. `Res_Rvas_2025` (“Montos en MXN”) se divide entre el TC de la propia BD, igual que se hizo con SONR 2025. `Res_Rvas_2026` (“Montos en USD”) se copia tal cual.
- **202609–202612**: 0, igual que en la referencia, porque SAP no tiene cifra real.
- **Validaciones**: `NETO = BRUTO − IRR` por ramo y periodo, y cruce contra la columna *REAL CIERRE* de 202512. El guardado es atómico: si algo falla, no queda una BD a medias.

### Puntos que conviene revisar (los reporta el script)

- **TC de 202512.** En `Res_Rvas_2025 › BacktestingFIANZAS!BC7` se capturó a mano **18.08**. RRC, SONR y la columna TC de la BD dicen **18.008**, así que se usó 18.008. Por eso 202512 difiere 0.4% de la columna *REAL CIERRE* de `Res_Rvas_2026`, que se calculó con 18.08.
- **RCONT 2026 ya está en USD.** La fórmula SAP de contingencia no divide entre el TC, pero se verificó que su fuente (`BASE!L`) ya viene convertida: los archivos de ene-26 y feb-26 tienen el mismo MXN y `BASE!L` cambia exactamente en la razón de TC.
- **RCONT 2025.** El bloque SAP de contingencia de `BacktestingFIANZAS` 2025 está vacío. El saldo total real de la reserva de contingencia (USD) sí está en `Res_Rvas_2025 › BacktestingCATAS_` (“RESERVA DE CONTINGENCIA / SALDO TOTAL”); viene del archivo FIA y el renglón siguiente liga a `BASE!L14` con diferencias menores a 0.1%. Se repartió por ramo con la mezcla de 2026 (160 ≈ 88.9%, 150 ≈ 6.6%, 170 ≈ 3.4%, 140 ≈ 1.1%, 130 = 0). Cada celda lleva un comentario con su procedencia. Para dejar 0: `RCONT_COMPLETAR_CON_TOTAL_SAP = False`.
- El valor 3,461,331 de *REAL CIERRE* 202512 en el ramo 130 viene de un archivo de presupuesto y **no** se usa.
- En la fuente SAP, **202602 = 202601 reconvertido con el TC de febrero**: el MXN no cambió en el archivo fuente. Pasa también en RRC de Daños.
- **Columna TC**: se reemplaza con el supuesto de Inversiones de `tipo_cambio.py`. Para 202606–202608 la plantilla traía una interpolación hacia 18.00; ahora lleva el TC real con el que SAP convirtió esos meses (17.4986, 17.3207, 16.9971), así que TC × USD reproduce el MXN. Para 202609–202612 lleva el FCST (17.2228 … 17.9000, que es la interpolación lineal exacta de 16.9971 a 17.90). No cambia ningún monto: 2026 ya viene en USD y 2025 usa su propio TC, que no cambia. Para conservar el TC de la plantilla: `ACTUALIZAR_TC_CON_FCST = False`.

## 2. Proyección: metodología

**a) Coherencia contable.** Se proyectan los *drivers* y el resto se deriva, así las identidades de la historia se cumplen en la proyección:

| Reserva | Drivers | Derivados |
|---|---|---|
| RRC | BEL, %GTO/BEL, %MR/BEL, %IRR/BRUTO | GTO, MR, BRUTO = BEL+GTO+MR, IRR, NETO = BRUTO−IRR |
| SONR | BEL, %MR/BEL, %IRR/BRUTO | MR, BRUTO = BEL+MR, IRR, NETO |
| RFV | BRUTO, %IRR/BRUTO, RCONT total | IRR, NETO; RCONT por ramo con la mezcla de los últimos 8 meses |

**b) Modelo: la línea de tendencia histórica.** Para montos, índices y LAGs se ajusta una regresión lineal (en logaritmos cuando la serie es positiva, es decir, un crecimiento porcentual constante) sobre los últimos **36 meses** (`MESES_TENDENCIA`; `None` = toda la historia) y se continúa **desde el último dato real**, sin amortiguar (`AMORTIGUACION_TENDENCIA = 1.0`). Es la misma línea de tendencia que se obtiene en Excel: la proyección sale paralela a ella y arranca del último real, así que no hay escalón entre lo real y lo proyectado. El dashboard HTML dibuja la línea de tendencia en gris para que se vea de dónde sale la pendiente.

| Tipo de serie | Modelo | Escala |
|---|---|---|
| Montos (BEL, BRUTO) | **Tendencia histórica** (36 meses) | logaritmos: crecimiento % mensual constante |
| Índices (Ind Sin RRC, 99.5%, SONR) | **Tendencia histórica** (36 meses) | logaritmos |
| LAGs (patrón de desarrollo) | **Tendencia histórica** (36 meses) | logaritmos si son positivos (así no cruzan cero) |
| Razones (%GTO, %MR, %cedido) | **SES** (nivel suavizado, sin tendencia) | original, acotado al dominio |
| RCONT | **Holt-Winters amortiguado** con estacionalidad trimestral | logaritmos |

- **Por qué 36 meses y no toda la historia**: con toda la historia entran arranques desde cero y cambios de régimen (el índice SONR del ramo 80 pasó de 0.10 en 2021 a 1.44; Hidro cayó de 4.0 a 0.14) que disparan la pendiente (+109 % o −64 % a 16 meses). Tres años es la tendencia reciente que sí describe el negocio actual. Si la serie tiene menos de 36 meses, se usa lo que hay (mínimo 6; con menos, SES).
- **Por qué sin amortiguar**: fue la decisión del área: si la tendencia ha sido constante, lo más probable es que siga así el próximo año. Con `AMORTIGUACION_TENDENCIA = 0.95` cada mes conserva 95 % de la tendencia (a 16 meses, 44 %) y las proyecciones bajan alrededor de un tercio.
- **Qué implica en los totales** (con la historia a ago-26): RRC BEL +54 % a dic-27 (+38 % anualizado, cuando en los últimos 12 meses reales creció 27 %), SONR BEL +72 % (+50 % anualizado; real +54 %). Son las tendencias de tres años continuadas; conviene contrastarlas con el plan de negocio.
- **Costo en precisión**: en el backtest la línea de tendencia es peor que repetir el último valor en los tres tipos (montos 26.7 % contra 22.3 %; índices 20.2 % contra 13.7 %; LAGs 2.6 % contra 2.1 %). Los modelos de suavizamiento (`"Holt amortiguado"`, con α ≈ 1 y β ≤ 0.15) siguen disponibles en `MODELO_POR_TIPO` para quien prefiera precisión sobre pendiente.
- Las razones usan SES porque dependen de los contratos de reaseguro y de la estructura de gastos, no de una tendencia; en el backtest la tendencia no las mejoró y en algunas series producía cesiones fuera de [0, 1].
- La estacionalidad mensual se probó y empeoró el backtest; solo se usa la trimestral de RCONT, que reproduce el diente de sierra de la historia.
- Los intervalos al 80 % salen de la variabilidad mensual alrededor de la tendencia (crece con la raíz del horizonte) o del propio modelo de suavizamiento.

**c) Backtest por serie.** Cada serie se vuelve a proyectar desde 16, 12 y 8 meses antes del final (horizontes de 1 a 16 meses, con al menos 12 meses de entrenamiento) con el mismo modelo, y se mide el error % (suma de errores absolutos / suma de valores reales) del modelo, de repetir el último valor y de SES. Está por serie en `Series_Modelos` y resumido por tipo en la hoja `Backtest`. Fianzas tiene 20 meses de historia, así que solo alcanza el corte a 8 meses y su cifra es indicativa. Sirve para juzgar la confiabilidad y para las alertas; no cambia el modelo. Con la historia a 202608 (mediana entre series):

| Tipo | Libro | Modelo | Error % modelo | Error % último valor | Series en que el modelo mejora al último valor |
|---|---|---|---|---|---|
| Montos | Daños | Tendencia historica | 26.7% | 22.3% | 43% (23 series, 3 cortes) |
| Montos | Fianzas | Tendencia historica | 1507.1% | 1460.8% | 25% (4 series, 1 corte) |
| Índices | HParametros | Tendencia historica | 20.2% | 13.7% | 16% (38 series, 3 cortes) |
| Razones | Daños | SES | 15.2% | 15.2% | 60% (55 series, 3 cortes) |
| Razones | Fianzas | SES | 12.0% | 6.5% | 25% (4 series, 1 corte) |
| LAGs | HParametros | Tendencia historica | 2.6% | 2.1% | 35% (74 series, 3 cortes) |

La línea de tendencia pierde contra la línea plana en los tres tipos (gana en 43 % de los montos, 16 % de los índices y 35 % de los LAGs): continuar una tendencia tres años hacia adelante cuesta precisión a 16 meses, sobre todo en índices ruidosos. Se conserva porque es lo que se necesita para planeación, pero el costo queda a la vista; para precisión sobre pendiente, `MODELO_POR_TIPO` admite `"Holt amortiguado"` o `"SES"` por tipo. Las series en que el modelo no supera al último valor en su propio backtest llevan alerta.

**d) Reglas actuariales y de calidad de datos** (todas reportadas en la hoja `Alertas`):

- **Dominio actuarial**: cesión (IRR/BRUTO) en [0, 1]; %GTO y %MR ≥ 0; LAGs ≥ 0 (no se acotan a 1: en la historia el patrón acumulado supera 1 en 10 de los 13 ramos, hasta 1.21 en el 40); montos ≥ 0.
- **Series especiales**: las series en cero en los últimos 6 meses se proyectan en cero; los parámetros “en escalón” (≥ 50% de meses sin cambio) conservan el último valor.
- **Índice 99.5%**: se mantiene ≥ la media cuando así ha sido siempre en la historia del ramo.
- **Limpieza de datos**:
  - Números guardados como texto (P de 202506 con `\xa0`).
  - Huecos de hasta 6 meses se interpolan (en HParametros falta 202501 en varios ramos); con huecos mayores se usa solo la historia posterior (TEV e Hidro).
  - Un LAG en 0 después de que el patrón acumulado superó 50% se trata como faltante (ramo 35).
- **Alertas**: salto atípico en el último mes (por ejemplo, RFV 150 en 202608, +27.6%; Ind Sin RRC 35, +43.7%), cambio proyectado a 16 meses mayor al máximo observado en la historia, y series en que el modelo no supera al último valor en su propio backtest.
- **Moneda**: los montos se modelan en USD. En backtest, modelar en MXN y convertir con el TC real fue menos preciso. Se puede cambiar con `MODELAR_EN_MXN`.

## 3. Salidas y formato

- **BD_Montos_RRC_SONR** (Daños y Fianzas): se llenan los renglones 202609–202612 (que venían en 0) y se agregan al final los bloques 2027, en el mismo orden de conceptos del bloque 2026. Se copia el formato de la fila equivalente de 2026 y se trasladan las fórmulas `RVATOT` / `RVA_SEXC`.
- **HParametros_2026**: se agregan al final los renglones 202609–202712 de los 13 ramos activos, en el mismo orden del último bloque “Real”. `Tipo de Indice` = **“Proyección”**, y el filtro de la hoja se amplía a “Real” + “Proyección”.
- **TC**: la columna TC de 2026 y 2027 lleva el supuesto de Inversiones de `tipo_cambio.py`: FCST 2026 (202601–202608 real) y FCST 2027, de 17.95 a 18.50. Como los montos se modelan en USD, el TC no cambia las cifras proyectadas.
- Opcional: `RESALTAR_PROYECCION = True` pinta de azul claro las celdas proyectadas.

## 4. Fidelidad de los archivos

Se verificó celda por celda que los valores, fórmulas y estilos originales quedan idénticos, así como las filas y columnas ocultas, anchos, paneles, zoom, autofiltro y nombres definidos. `excel_fiel.py` corrige lo que `openpyxl` altera por sí solo:

- escribe los números con 17 dígitos, así que el valor queda exacto;
- conserva la agrupación de columnas (`outlineLevelCol`);
- conserva el pie de página de la etiqueta de sensibilidad;
- guarda de forma atómica.

Siguen perdiéndose metadatos no visibles:

- `customXml` de SharePoint, `calcChain` y las propiedades de hoja `_pios_id`;
- datos de versión del libro;
- las celdas con texto vacío (`''`), que quedan en blanco.

Excel recalcula las fórmulas al abrir.

## 5. Dashboards (`Dashboard_Indices_Reservas.xlsx` y `.html`)

Hay dos versiones con el mismo contenido. Ambas se regeneran en cada corrida de la proyección (`GENERAR_DASHBOARD`); para rehacerlas sin volver a proyectar, corre `dashboard.py` (Excel) o `dashboard_html.py` (HTML). Azul = real, naranja punteado = proyección, gris = banda al 80 % u otros ramos. `#N/D` / `s/d` = sin dato para esa combinación (por ejemplo, TEV e Hidro no tienen índices de SONR ni LAGs; un LAG en 0 después de superar 50 % es marcador de faltante).

| Hoja / pestaña | Contenido |
|---|---|
| **Índices** | Selectores: ramo, índice o LAG y periodo. Indicadores: último real, promedio real de 12 meses, proyección a dic-26 y dic-27, variación. Gráficas: evolución mensual 2021–2027 con banda al 80 %, comparativo por ramo (el ramo elegido resaltado), patrón de desarrollo LAG 1–10 (ago-24, ago-25, ago-26 y dic-27 proyectado). Tabla resumen de los índices del ramo. |
| **Reservas** | Selectores: reserva (RRC, SONR, RFV), concepto, ramo (o “Todos”) y moneda (USD, o MXN con el TC de cada mes). Indicadores: real ago-26, proyección dic-26 y dic-27, crecimiento anual proyectado, crecimiento real de 12 meses y % cedido. Gráficas: mensual 2025–2027, histórico 2022–2027, por ramo y por concepto. |
| **Análisis** | Tablas con mapa de calor: índices por ramo (real contra dic-27), totales de reservas por concepto (dic-24 a dic-27) y el modelo por tipo de serie con su error de backtest. |

**Excel** (`Dashboard_Indices_Reservas.xlsx`): con el estilo del ejemplo (panel de navegación con selectores, banda de indicadores, paneles de gráficas). Sin macros: los selectores son listas desplegables que alimentan fórmulas (`SUMIFS`) y las gráficas se recalculan al cambiar la selección. Incluye las hojas `BD_Indices` y `BD_Reservas` con las bases como tablas con filtros. Si cambias la reserva y el concepto o el ramo elegidos no existen en ella (por ejemplo GTO en SONR), aparece un aviso bajo los selectores. Hereda la etiqueta de sensibilidad **USO INTERNO** y el pie de página de la BD. Está pensado para Excel: en LibreOffice las fórmulas funcionan, pero los `#N/D` se dibujan como cero en las líneas.

**HTML** (`Dashboard_Indices_Reservas.html`): un solo archivo de ~400 KB con los datos incrustados, que se abre con doble clic en cualquier navegador actual (Chrome, Edge, Firefox o Safari de 2021 en adelante), sin internet ni instalación, y se puede mandar por correo; lleva la leyenda de uso interno en el pie. Agrega: tooltip que sigue al cursor (en las gráficas de líneas también con las flechas del teclado; en barras, con Tab), botón **Tabla** en cada gráfica con los números exactos, tema claro/oscuro (botón arriba a la derecha; por omisión sigue el del sistema), diseño que se acomoda al celular y estilos de impresión. Al cambiar de reserva, el concepto o el ramo que no existan en ella cambian en silencio al primero disponible / “Todos”.
