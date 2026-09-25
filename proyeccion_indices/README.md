# Proyección de índices y montos de reservas (202609 – 202712)

Dos scripts de Python, pensados para correr desde VSCode (F5 o *Run Python File*). Si falta alguna paquetería, el propio script la instala en el intérprete activo.

| Script | Qué hace |
|---|---|
| `llenar_bd_rfv.py` | Llena **BD_ RFV** (ramos de Fianzas 130–170) desde `Res_Rvas_2025` y `Res_Rvas_2026` con el mismo criterio con que se llenó a mano la BD de Daños. |
| `proyeccion_reservas.py` | Proyecta de **202609 a 202712** `HParametros_2026` (índices y LAGs “Real”), `BD_Montos_RRC_SONR` (Daños) y `BD_ RFV` (Fianzas), con el mismo formato de los archivos originales. |

## Cómo correrlo

1. Copia los cuatro archivos a `proyeccion_indices/entradas/`:
   `BD_ BEL - IRR - MR.xlsx`, `BD_ RFV.xlsx`, `Res_Rvas_2025.xlsx` y `Res_Rvas_2026.xlsx`.
2. Ejecuta `llenar_bd_rfv.py`. Genera `salidas/BD_ RFV.xlsx`.
3. Ejecuta `proyeccion_reservas.py` (si el paso 2 no se ha corrido, lo corre solo). Tarda de 2 a 3 minutos y genera:
   - `salidas/BD_ BEL - IRR - MR_Proyeccion.xlsx`
   - `salidas/BD_ RFV_Proyeccion.xlsx`
   - `salidas/Diagnostico_Proyeccion.xlsx`: metodología, validación, modelos por serie, intervalos y alertas.
   - `salidas/Graficas_Proyeccion.pdf`: historia contra proyección de cada serie.

Los parámetros (periodos, tipo de cambio 2027, resaltado de celdas, etc.) están en la sección **CONFIGURACIÓN** al inicio de cada script.

> Las carpetas `entradas/` y `salidas/` y cualquier `.xlsx` están excluidas de git (el repositorio es público y los datos son confidenciales).

## 1. Llenado de BD_ RFV (Fianzas)

El criterio se obtuvo reconstruyendo celda por celda la hoja de referencia de Daños. RRC coincide en 312 de 312 celdas y SONR en 288 de 288.

- **Fuente**: hoja `BacktestingFIANZAS`, columnas del escenario **SAP** (fila 1 = `SAP`, “12REALES – BEL REAL”), mismo periodo, transpuesto (ramos en columnas).
- **Conceptos**:

  | Bloque SAP | Concepto en la BD |
  |---|---|
  | `NETO` | `RFV NETO` |
  | `BRUTO` | `RFV BRUTO` |
  | `IRR` | `RFV IRR` |
  | `CONTIGENCIA SDO` | `RCONT` |

- **Moneda**: la BD está en USD.
  - `Res_Rvas_2025` (“Montos en MXN”) se divide entre el TC de la propia BD, igual que se hizo con SONR 2025.
  - `Res_Rvas_2026` (“Montos en USD”) se copia tal cual.
- **202609–202612**: 0, igual que en la referencia (SAP no tiene cifra real).
- **Validaciones**: `NETO = BRUTO − IRR` por ramo y periodo, y cruce contra la columna *REAL CIERRE* de 202512.

### Puntos que conviene revisar (los reporta el script)

- **TC de 202512.** En `Res_Rvas_2025 › BacktestingFIANZAS!BC7` se capturó a mano **18.08**. RRC, SONR y la columna TC de la BD dicen **18.008**, así que se usó 18.008. Por eso 202512 difiere 0.4% de la columna *REAL CIERRE* de `Res_Rvas_2026`, que se calculó con 18.08.
- **RCONT 2026 ya está en USD.** La fórmula SAP de contingencia no divide entre el TC, pero se verificó que su fuente (`BASE!L`) ya viene convertida. Los archivos de ene-26 y feb-26 tienen el mismo MXN y `BASE!L` cambia exactamente en la razón de TC.
- **RCONT 2025.** El bloque SAP de contingencia de `BacktestingFIANZAS` 2025 está vacío. El saldo SAP total de la reserva de contingencia (misma fuente `BASE!L`, en USD) está en `Res_Rvas_2025 › BacktestingCATAS_` (“RESERVA DE CONTINGENCIA / SALDO TOTAL”). Se repartió por ramo con la mezcla de 2026 (160 ≈ 88.9%, 150 ≈ 6.6%, 170 ≈ 3.4%, 140 ≈ 1.1%, 130 = 0). Cada celda lleva un comentario con su procedencia. Si prefieres dejar 0, pon `RCONT_COMPLETAR_CON_TOTAL_SAP = False`.
- El valor 3,461,331 de *REAL CIERRE* 202512 en el ramo 130 viene de un archivo de presupuesto y **no** se usa.
- En la fuente SAP, **202602 = 202601 reconvertido con el TC de febrero**: el MXN no cambió en el archivo fuente. Pasa también en RRC de Daños.

## 2. Proyección (metodología)

**a) Coherencia contable.** Se proyectan los *drivers* y el resto se deriva, así las identidades de la historia se cumplen también en la proyección:

| Reserva | Drivers | Derivados |
|---|---|---|
| RRC | BEL, %GTO/BEL, %MR/BEL, %IRR/BRUTO | GTO, MR, BRUTO = BEL+GTO+MR, IRR, NETO = BRUTO−IRR |
| SONR | BEL, %MR/BEL, %IRR/BRUTO | MR, BRUTO = BEL+MR, IRR, NETO |
| RFV | BRUTO, %IRR/BRUTO, RCONT total | IRR, NETO; RCONT por ramo con la mezcla de los últimos 8 meses |

**b) Modelos.** Ingenuo, Ingenuo estacional, Media 12m, SES, Holt amortiguado, Holt-Winters amortiguado, Theta, ARIMA (orden por AICc) y Regresión log-lineal con estacionalidad. Montos e índices se modelan en logaritmos; razones y LAGs, en escala original.

**c) Selección validada fuera de muestra.** En cada corrida se hace un backtest del método completo:

- Se simula haber proyectado desde 8 cortes históricos a 1–16 meses con cada procedimiento candidato (modelos solos y combinaciones de pesos iguales).
- Por tipo de serie se elige el de menor **AvgRelMAE**: error relativo al ingenuo, media geométrica entre series; menor que 1 significa mejor que “repetir el último valor”.

Resultados con historia a 202608 (1,256 pronósticos fuera de muestra):

| Tipo de serie | Procedimiento elegido | AvgRelMAE | Series que mejoran vs. ingenuo |
|---|---|---|---|
| Montos (BEL / BRUTO / RCONT) | Theta | 0.882 | 67% |
| Índices (Ind Sin …) | Ingenuo + Media 12m | 0.942 | 82% |
| Razones (%GTO, %MR, %cesión) | Ingenuo + SES | 0.991 | 50% |
| LAGs | Ingenuo + Theta | 0.998 | 40% |

En la misma validación, elegir el modelo serie por serie (“torneo”) resultó menos preciso (≈1.0–1.07). Queda como modo alternativo: `MODO_SELECCION = "torneo"`.

**d) Backtest por serie.** Con todos los modelos y los mismos cortes para todos, da tres cosas:

- El MASE de cada modelo en cada serie (hoja `Series_Modelos`).
- Los intervalos al 80%.
- Una **red de seguridad**: si en la propia serie el procedimiento validado fue más de 1.5 veces peor que el ingenuo (por ejemplo, por un cambio de régimen), se usa el ensamble propio de esa serie.

**e) Reglas actuariales y de calidad de datos**, todas reportadas en la hoja `Alertas`:

- Series en cero en los últimos 6 meses se proyectan en cero.
- Parámetros “en escalón” (se actualizan esporádicamente, ≥ 50% de meses sin cambio) mantienen el último valor.
- Series cortas (< 18 observaciones) usan SES.
- Razones y LAGs se acotan al rango histórico.
- El índice 99.5% se mantiene ≥ media cuando así ha sido siempre en la historia del ramo.
- Se limpian números guardados como texto (por ejemplo, P de 202506 con espacios `\xa0`).
- Huecos de hasta 6 meses se interpolan; con huecos mayores solo se usa la historia posterior (TEV e Hidro).
- Un LAG en 0 después de que el patrón acumulado ya superó 50% (ramo 35) se trata como faltante.

## 3. Salidas y formato

- **BD_Montos_RRC_SONR** (Daños y Fianzas): se llenan los renglones 202609–202612 (que venían en 0) y se agregan al final los bloques 2027, en el mismo orden de conceptos del bloque 2026. Se copia el formato de la fila equivalente de 2026 y se trasladan las fórmulas `RVATOT` / `RVA_SEXC`.
- **HParametros_2026**: se agregan al final los renglones 202609–202712 de los 13 ramos activos, en el mismo orden del último bloque “Real”. `Tipo de Indice` = **“Proyección”**; el filtro de la hoja se amplía a “Real” + “Proyección”.
- **TC**: los meses existentes conservan el TC de la BD. Los meses de 2027 usan `TC_PROYECCION` o, si no se indica, el último TC de la BD (18.00), bajo el supuesto de caminata aleatoria.
- Opcional: `RESALTAR_PROYECCION = True` pinta de azul claro las celdas proyectadas.

Nota: los libros se guardan con `openpyxl`. Se conservan valores, formatos, fórmulas, filtros, nombres definidos, anchos y paneles. Se pierden metadatos internos no visibles (`customXml` de SharePoint y `calcChain`). Excel recalcula las fórmulas al abrir.
