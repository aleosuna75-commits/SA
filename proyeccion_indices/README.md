# Proyección de índices y montos de reservas (202609 – 202712)

Dos scripts de Python pensados para correr desde VSCode (F5 o *Run Python File*). Si falta alguna paquetería, el propio script la instala en el intérprete activo. Para reproducir las cifras exactas, las versiones validadas están en `requirements.txt`.

| Script | Qué hace |
|---|---|
| `llenar_bd_rfv.py` | Llena **BD_ RFV** (ramos de Fianzas 130–170) desde `Res_Rvas_2025` y `Res_Rvas_2026`, con el mismo criterio con el que se llenó a mano la BD de Daños. |
| `proyeccion_reservas.py` | Proyecta de **202609 a 202712** `HParametros_2026` (índices y LAGs “Real”), `BD_Montos_RRC_SONR` (Daños) y `BD_ RFV` (Fianzas), con el mismo formato de los archivos originales. |
| `dashboard.py` | Arma los **dashboards de Excel** de índices y reservas (real y proyectado) a partir de las salidas. Lo llama `proyeccion_reservas.py` al final; también se puede correr solo (ver sección 5). |
| `excel_fiel.py` | Módulo auxiliar que usan los dos scripts para guardar los libros sin perder formato (ver sección 4). |
| `tipo_cambio.py` | Supuesto de tipo de cambio de Inversiones (`TC_Real_Esti.xlsx`, hoja TC: **FCST** 2026 y **FCST 2027**) que se escribe en la columna TC. Actualízalo cuando haya un nuevo pronóstico. |

## Cómo correrlo

1. Copia los cuatro archivos a `proyeccion_indices/entradas/`: `BD_ BEL - IRR - MR.xlsx`, `BD_ RFV.xlsx`, `Res_Rvas_2025.xlsx` y `Res_Rvas_2026.xlsx`.
2. Ejecuta `proyeccion_reservas.py`. Tarda unos 2–3 minutos; en cada corrida vuelve a llenar la BD de Fianzas desde los Res_Rvas (`REGENERAR_BD_RFV`). Genera:
   - `salidas/BD_ RFV.xlsx`: la BD de Fianzas llena, sin proyección.
   - `salidas/BD_ BEL - IRR - MR_Proyeccion.xlsx`
   - `salidas/BD_ RFV_Proyeccion.xlsx`
   - `salidas/Diagnostico_Proyeccion.xlsx`: metodología, validación, modelos por serie, intervalos y alertas.
   - `salidas/Graficas_Proyeccion.pdf`: historia contra proyección de cada serie.
   - `salidas/Dashboard_Indices_Reservas.xlsx`: dashboards interactivos (sección 5).

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

**b) Modelos.** Ingenuo, Ingenuo estacional, Media 12m, SES, Holt amortiguado, Holt-Winters amortiguado, Theta, ARIMA (orden por AICc) y Regresión log-lineal con estacionalidad. Montos e índices se modelan en logaritmos; razones y LAGs, en escala original.

**c) Selección validada fuera de muestra (backtest del método completo).** En cada corrida se simula haber proyectado desde 8 cortes históricos a 1–16 meses con cada procedimiento candidato (modelos solos y combinaciones de pesos iguales):

- **Montos**: se elige el menor **WAPE** (error absoluto / monto real, que pondera por USD). Entre los que están a ≤ 2% del mejor, gana el de menor sesgo agregado.
- **Índices, razones y LAGs**: se elige el menor **AvgRelMAE** (error relativo al ingenuo, media geométrica entre series), con IC bootstrap al 90%. Si la mejora frente al ingenuo no es significativa, se usa el mejor procedimiento **sin tendencia** (parsimonia).

Resultados con historia a 202608 (159 series, 1,256 pronósticos fuera de muestra):

| Tipo de serie | Procedimiento elegido | Evidencia |
|---|---|---|
| Montos (BEL / BRUTO / RCONT) | **Theta + Holt amortiguado** | WAPE 19.7% (ingenuo 24.0%); sesgo agregado a 13–16 m −14% (ingenuo ≈ −30%) |
| Índices (Ind Sin …) | **Ingenuo + Media 12m** | AvgRelMAE 0.942, IC90 [0.906, 0.981]; mejora en 82% de las series |
| Razones (%GTO, %MR, %cesión) | **Ingenuo + SES** | AvgRelMAE 0.991 (no es significativamente mejor que el ingenuo, pero tampoco supone tendencia: suaviza el último dato) |
| LAGs | **Ingenuo** (sin deriva) | El mejor, Ingenuo + Theta, supone tendencia y no mejora significativamente al último valor |

- La validación de montos usa las 21 series BEL de Daños con historia suficiente; Fianzas (20 meses) no alcanza para validar y se le aplica el mismo procedimiento por extensión.
- Regla de parsimonia: si el intervalo de confianza del mejor procedimiento incluye 1 **y** el procedimiento supone tendencia, se usa el mejor procedimiento sin tendencia. Los procedimientos sin tendencia se consideran igual de parsimoniosos.
- Elegir el modelo serie por serie (“torneo”) fue menos preciso. Queda como modo alternativo: `MODO_SELECCION = "torneo"`.
- **Moneda**: los montos se modelan en USD. En backtest, modelar en MXN y convertir con el TC real fue menos preciso en Daños (WAPE 22.5% vs 19.8%) y en Fianzas (7.4% vs 6.0%). Se puede cambiar con `MODELAR_EN_MXN`.
- **Sesgo conocido**: en 2023–2026 hubo un crecimiento muy fuerte. Los modelos amortiguan la tendencia y a 13–16 meses quedaron en promedio 14% por debajo de lo real. Si el plan de negocio prevé un crecimiento sostenido, conviene contrastarlo.

**d) Backtest por serie**, con todos los modelos y los mismos cortes (sin fuga de información):

- Da el MASE de cada modelo en cada serie (hoja `Series_Modelos`) y los intervalos al 80%, con piso de caminata aleatoria en series cortas.
- Incluye una **red de seguridad**: si en la propia serie el procedimiento validado fue más de 1.5 veces peor que el ingenuo (por ejemplo, un cambio de régimen como el ramo 37), se usa el ensamble propio de esa serie.

**e) Reglas actuariales y de calidad de datos** (todas reportadas en la hoja `Alertas`):

- **Dominio actuarial**: cesión (IRR/BRUTO) en [0, 1] y %GTO, %MR ≥ 0. Razones y LAGs se acotan además al rango histórico.
- **RCONT**: se proyecta con factores por mes del trimestre (acumula en los meses 1–2 y libera en el 3). En un backtest con 7 cortes (12 a 18 meses de entrenamiento), el MAPE con Theta + Holt bajó de 8.6% a 6.2%. Con tan poca historia la cifra es indicativa.
- **Series especiales**:
  - Las series en cero en los últimos 6 meses se proyectan en cero.
  - Los parámetros “en escalón” conservan el último valor.
  - Las series cortas usan SES.
- **Índice 99.5%**: se mantiene ≥ la media cuando así ha sido siempre en la historia del ramo.
- **Limpieza de datos**:
  - Números guardados como texto (P de 202506 con `\xa0`).
  - Huecos de hasta 6 meses se interpolan; con huecos mayores se usa solo la historia posterior (TEV e Hidro).
  - Un LAG en 0 después de que el patrón acumulado superó 50% se trata como faltante (ramo 35).
- **Alerta de salto atípico en el último mes** (por ejemplo, RFV 150 en 202608, +27.6%).

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

## 5. Dashboards (`Dashboard_Indices_Reservas.xlsx`)

Con el estilo del ejemplo: panel de navegación con selectores a la izquierda, banda de indicadores y paneles de gráficas. Azul = real, naranja punteado = proyección, gris = banda al 80% o ramos no seleccionados. No usa macros: los selectores son listas desplegables que alimentan fórmulas (`SUMIFS`) y las gráficas se recalculan al cambiar la selección.

| Hoja | Contenido |
|---|---|
| **Dashboard Índices** | Selectores: ramo, índice o LAG y periodo. Indicadores: último real, promedio real de 12 meses, proyección a dic-26 y dic-27, variación. Gráficas: evolución mensual 2021–2027 con banda al 80%, comparativo por ramo (el ramo elegido resaltado), patrón de desarrollo LAG 1–10 (ago-24, ago-25, ago-26 y dic-27 proyectado). Tabla resumen de los índices del ramo. |
| **Dashboard Reservas** | Selectores: reserva (RRC, SONR, RFV), concepto, ramo (o “Todos”) y moneda (USD, o MXN con el TC de cada mes). Indicadores: real ago-26, proyección dic-26 y dic-27, crecimiento anual proyectado, crecimiento real de 12 meses y % cedido. Gráficas: mensual 2025–2027, histórico 2022–2027, por ramo y por concepto. |
| **Análisis** | Tablas fijas con mapa de calor: índices por ramo (real contra dic-27), totales de reservas por concepto (dic-24 a dic-27) y el método elegido en la validación. |
| **BD_Indices**, **BD_Reservas** | Las bases que alimentan los dashboards, como tablas de Excel con filtros. |

- Se regenera en cada corrida de la proyección (`GENERAR_DASHBOARD`). Para rehacerlo sin volver a proyectar, corre `dashboard.py`.
- `#N/D` o `s/d` = sin dato para esa combinación; por ejemplo, TEV e Hidro no tienen índices de SONR ni LAGs.
- Si cambias la reserva y el concepto o el ramo elegidos no existen en ella (por ejemplo GTO en SONR), aparece un aviso bajo los selectores.
- Hereda la etiqueta de sensibilidad **USO INTERNO** y el pie de página de la BD de origen.
- Está pensado para Excel. En LibreOffice las fórmulas funcionan, pero los `#N/D` se dibujan como cero en las líneas.

