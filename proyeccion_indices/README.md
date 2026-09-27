# Proyección de índices y montos de reservas (202609 – 202712)

Dos scripts de Python pensados para correr desde VSCode (F5 o *Run Python File*). Si falta alguna paquetería, el propio script la instala en el intérprete activo. Para reproducir las cifras exactas, las versiones validadas están en `requirements.txt`.

| Script | Qué hace |
|---|---|
| `llenar_bd_rfv.py` | Llena **BD_ RFV** (ramos de Fianzas 130–170) desde `Res_Rvas_2025` y `Res_Rvas_2026`, con el mismo criterio con el que se llenó a mano la BD de Daños. |
| `proyeccion_reservas.py` | Proyecta de **202609 a 202712** `HParametros_2026` (índices y LAGs “Real”), `BD_Montos_RRC_SONR` (Daños) y `BD_ RFV` (Fianzas), con el mismo formato de los archivos originales, usando suavizamiento exponencial (Holt / Holt-Winters / SES). |
| `dashboard.py` | Arma el **dashboard de Excel** de índices y reservas (real y proyectado) a partir de las salidas. Lo llama `proyeccion_reservas.py` al final; también se puede correr solo (ver sección 5). |
| `dashboard_html.py` | Arma el mismo dashboard en **HTML** (un solo archivo, sin internet), con tooltips, vista de tabla y modo oscuro. |
| `excel_fiel.py` | Módulo auxiliar que usan los dos scripts para guardar los libros sin perder formato (ver sección 4). |
| `tipo_cambio.py` | Supuesto de tipo de cambio de Inversiones (`TC_Real_Esti.xlsx`, hoja TC: **FCST** 2026 y **FCST 2027**) que se escribe en la columna TC. Actualízalo cuando haya un nuevo pronóstico. |

## Cómo correrlo

1. Copia los cuatro archivos a `proyeccion_indices/entradas/`: `BD_ BEL - IRR - MR.xlsx`, `BD_ RFV.xlsx`, `Res_Rvas_2025.xlsx` y `Res_Rvas_2026.xlsx`.
2. Ejecuta `proyeccion_reservas.py`. Tarda alrededor de un minuto; en cada corrida vuelve a llenar la BD de Fianzas desde los Res_Rvas (`REGENERAR_BD_RFV`). Genera:
   - `salidas/BD_ RFV.xlsx`: la BD de Fianzas llena, sin proyección.
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

## 1. Llenado de BD_ RFV (Fianzas)

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

**b) Un solo tipo de modelo: suavizamiento exponencial (familia Holt-Winters).** Todos son el mismo modelo de nivel + tendencia amortiguada + estacionalidad, en la variante que corresponde a cada tipo de serie (`MODELO_POR_TIPO`):

| Tipo de serie | Modelo | Escala |
|---|---|---|
| Montos (BEL, BRUTO) | **Holt con tendencia amortiguada** | logaritmos (crecimiento porcentual, siempre positivo) |
| Índices (Ind Sin RRC, 99.5%, SONR) | **Holt con tendencia amortiguada** | logaritmos |
| LAGs (patrón de desarrollo) | **Holt con tendencia amortiguada** | original, no negativo |
| Razones (%GTO, %MR, %cedido) | **SES** (nivel suavizado, sin tendencia) | original, acotado al dominio |
| RCONT | **Holt-Winters amortiguado** con estacionalidad por mes del trimestre | logaritmos |

- Los parámetros de cada serie (α nivel, β tendencia, φ amortiguación, γ estacionalidad) se estiman por máxima verosimilitud con `statsmodels` (`ETSModel`), y los intervalos al 80% salen del propio modelo. Quedan en la hoja `Series_Modelos` del diagnóstico, junto con la **tendencia mensual** al final de la historia.
- **Amortiguación fija** (`AMORTIGUACION_TENDENCIA = 0.95`): cada mes hacia adelante la tendencia conserva 95% de su valor; a 16 meses conserva 44% y el cambio acumulado equivale a 10.7 meses de la tendencia mensual. Es el mismo φ para todas las series, y es el parámetro que conviene tocar si se quiere más o menos tendencia: con 0.98 la proyección es casi lineal (72% a 16 meses) y con 0.90 se apaga pronto (19%). Se fijó porque, al dejar que la máxima verosimilitud lo estime, en la mitad de las series se iba al mínimo permitido y la tendencia se apagaba en 2027, que era justo la queja original.
- **Cotas de los demás parámetros** (`COTAS_SUAVIZAMIENTO`), estimados por máxima verosimilitud en cada serie:
  - α ≈ 1 (nivel, en Holt): la proyección **arranca del último dato real**, sin escalón entre lo real y lo proyectado. Sin esta cota, en varias series el modelo suavizaba el nivel y el primer mes proyectado caía o subía de golpe (hasta −4% en el total de RRC).
  - β ≤ 0.15 (tendencia): la tendencia es el promedio suavizado de los cambios de los últimos años, **no la del último mes**; así un salto puntual no se convierte en tendencia.
  - En RCONT (Holt-Winters) el nivel sí se suaviza (α ≥ 0.2) para separar la estacionalidad. En las razones (SES) α se estima libre: si la razón cambió de nivel, α ≈ 1 y sigue al último dato (por ejemplo la cesión del ramo 10 de RRC, que subió de 0.40 a 0.63 en seis meses); si solo tiene ruido, usa el promedio reciente. Ponerle una cota inferior hacía que el optimizador se quedara pegado a ella y sí producía escalones en NETO.
  - Sin cotas, en series cortas o ruidosas la estimación caía en casos degenerados: α = 0 (el modelo ignora el nivel actual y proyecta el promedio o la recta de toda la historia) y β alto (un salto de un mes se vuelve tendencia), con proyecciones de +65% o −49% a 16 meses en índices y LAGs.
- Las razones usan SES porque dependen de los contratos de reaseguro y de la estructura de gastos, no de una tendencia; en el backtest la tendencia no las mejoró y en algunas series producía cesiones fuera de [0, 1].
- La estacionalidad mensual (Holt-Winters de periodo 12) se probó en montos e índices y empeoró el backtest, así que solo se usa la trimestral de RCONT (acumula en los meses 1–2 del trimestre y libera en el 3), que reproduce el diente de sierra de la historia.
- Series cortas: SES con menos de 12 observaciones; último valor con menos de 4.

**c) Backtest por serie.** Cada serie se vuelve a proyectar desde 16, 12 y 8 meses antes del final (horizontes de 1 a 16 meses, con al menos 12 meses de entrenamiento) con el mismo modelo, y se mide el error % (suma de errores absolutos / suma de valores reales) del modelo, de repetir el último valor y de SES. Está por serie en `Series_Modelos` y resumido por tipo en la hoja `Backtest`. Fianzas tiene 20 meses de historia, así que solo alcanza el corte a 8 meses y su cifra es indicativa. Sirve para juzgar la confiabilidad y para las alertas; no cambia el modelo. Con la historia a 202608 (mediana entre series):

| Tipo | Libro | Modelo | Error % modelo | Error % último valor | Series en que el modelo mejora al último valor |
|---|---|---|---|---|---|
| Montos | Daños | Holt amortiguado | 21.5% | 22.3% | 57% (23 series, 3 cortes) |
| Montos | Fianzas | Holt amortiguado, Holt-Winters amortiguado (trimestral) | 8.2% | 13.3% | 80% (5 series, 1 corte) |
| Índices | HParametros | Holt amortiguado | 13.9% | 13.7% | 16% (38 series, 3 cortes) |
| Razones | Daños | SES | 15.2% | 15.2% | 60% (55 series, 3 cortes) |
| Razones | Fianzas | SES | 12.0% | 6.5% | 25% (4 series, 1 corte) |
| LAGs | HParametros | Holt amortiguado | 2.5% | 2.1% | 36% (74 series, 3 cortes) |

En montos la tendencia mejora la precisión (Daños: mejor que el último valor en 57% de las series; Fianzas: en 80%, con un solo corte). En índices y LAGs **no**: el error mediano es algo mayor que el de la línea plana y el modelo solo gana en 16% de los índices y 36% de los LAGs, porque los índices son ruidosos y los LAGs casi no se mueven. Se conserva la tendencia porque es lo que se necesita para planeación, pero el costo queda a la vista; si se prefiere precisión sobre pendiente en índices, basta cambiar `MODELO_POR_TIPO["indice"]` a `"SES"`. Las series en que el modelo no supera al último valor en su propio backtest llevan alerta.

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
