# Cambios a aplicar · scripts del MEC y de reservas

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

Los cinco scripts de esta carpeta son los originales con los cambios ya aplicados. En `diffs/` está el diff unificado de cada uno para revisarlo línea por línea antes de sustituir nada. Los dos reforecast conservan sus finales de línea Windows (CRLF), así que el diff sale limpio en cualquier herramienta.

Todos los cambios de comportamiento vienen con interruptor: `USAR_FND_CALIBRADO = False` deja los scripts funcionando exactamente como hoy.

| Archivo | Sustituye a | Diff |
|---|---|---|
| `mec_devengamiento.py` | mismo nombre (v2 → v3) | +178 / −30 |
| `reforecastRRC_v11_Esc1_ocl.py` | `reforecastRRC_v10_Esc1_ocl.py` | +89 / −13 |
| `ReforecastSONR_v4.py` | `ReforecastSONR_v3.py` | +88 / −15 |
| `construir_input_mec.py` | `construir input mec.py` | +334 / −53 |
| `generar_output_mec.py` | `generar output mec.py` | +7 / −3 |
| `comparar_outputs_reservas.py` | nuevo (output anterior vs output con FND calibrado) | — |
| `test_integracion_fnd.py` | nuevo (prueba de regresión) | — |

Todos los scripts leen sus insumos y escriben sus salidas en **su propia carpeta**; la guía de qué archivo va en la carpeta local para cada paso está en `LEEME_carpeta_local.md`.

Nota de nombres: `construir input mec.py` y `generar output mec.py` traían espacios; aquí van con guion bajo, que es lo que `generar_output_mec.py` espera al importar el módulo (`mec*devengamiento*.py` con guion bajo).

## 1. `mec_devengamiento.py` (v2 → v3)

Módulo nuevo `M4b · REGISTRO`, que es la base de la v3:

- `NT_MENSUAL` — recta de 24-avos de la Nota Técnica por antigüedad de registro.
- `fnd_registro(ramo, k_reg, delta)` — FND de una cuenta proporcional o facultativa registrada hace `k_reg` meses; `min(1, max(0, NT(k) − δ_ramo))`, cero desde k = 12.
- `vector_registro`, `tabla_registro` — el vector y la tabla ramo × antigüedad publicables.
- `antiguedad_registro(mes_valuacion, mes_registro)` — con la advertencia explícita de que en los reforecast el mes de registro es `CALMONTH` (`aPog_MesProc`) y el de valuación es `Meses`; no son lo mismo.
- `cargar_delta(ruta)` — lee δ de `delta_calibrado.json`, para que una recalibración trimestral no exija tocar código.
- `ConfigMEC`: `DELTA_RAMO` (los diez δ calibrados), `SUBRAMO_A_RAMO` (31/34/35/37/39 → 30, 71/73 → 70, 20 → 10), `COL_TIPOREA`, `USAR_CALIBRADO`, `ARCHIVO_DELTA`.

Correcciones sobre la v2:

- `factor_no_devengado` — reescrita con jerarquía explícita: no proporcional con fechas → prorrata exacta al mes de valuación; proporcional y facultativo → tabla calibrada por antigüedad de registro; si falta información → el valor legado que pasa el llamador. Acepta `mes_valuacion` y `delta`.
- `valor_fnd_directo` — igual, con `tiporea` y `mes_valuacion` (la usan las `zFND*` del SONR).
- `fnd_exacto` — el tercer parámetro pasa de `calmonth` a `mes_valuacion`. Era el bug de fondo: con `CALMONTH` cada registro se valuaba en su propio mes contable y no en la fecha de valuación.
- `antiguedad_de_row` — acepta `mes_valuacion`.
- `TablaFND.factor` — la cola devuelve 0.0 en vez de `vec[-1]`, que dejaba un FND residual permanente (4.3% en Vida con horizonte 24).
- `m4_escenario_frecuencia` — acotada a [0, 1]: con δ negativo (CAT, Crédito) el desplazamiento podía pasar del 100%.
- Encabezado — documenta qué se midió, con qué evidencia y qué se conserva de la v2. El candado de alcance (FS, 1−LAG, MR, IRR, índice) no cambia.

## 2. `reforecastRRC_v11_Esc1_ocl.py`

- Importa `mec_devengamiento` de la misma carpeta y añade el bloque de configuración `USAR_FND_CALIBRADO`, `FILTRO_ANIO_SUSC`, `DELTA_FND`, `MES_VALUACION` y el helper `fnd_cal(ramo, calmonth, valorfrec_legado)`.
- `VALORFREC` en `ConsultaReal` y en `ConsultaReal_USD` — antes `xPND.get(CALMONTH).get(FRECUENCIA)`, ahora `fnd_cal(Ramo, CALMONTH, <valor legado>)`. La lógica de `PORC_ND` que ya existía (71/73 usan VALORFREC, TipoRea 2 con fechas iguales da 0, TipoRea 2 con fechas distintas va por prorrata, resto VALORFREC) se conserva intacta.
- `PORC_ND` en `ConsultaPPTO2025` — igual, sustituye `xPND2`.
- `MES_VALUACION` se fija por escenario: `Meses` en los escenarios 2 y 3, `Mesesp` (cierre de diciembre) en el 4. Es la corrección que hace que el corte del FND sea la fecha de valuación y no el mes de registro.
- `FILTRO_ANIO_SUSC` — el filtro `Val(left(aPog_MesProc,4)) <= Susc` del WHERE queda conmutable, con el comentario de que reproducido en la validación deja la RRC en el 29% de la real. Por defecto queda en `True`, es decir como hoy: el cambio es deliberadamente opt-in porque hay que confirmarlo contra el campo `Susc` de SIREC antes de moverlo.
- Los diccionarios `xPND` y `xPND2` se conservan como valor legado de respaldo; con el FND calibrado activo ya no gobiernan el resultado.
- **Rutas locales.** Las siete rutas fijas de OneDrive (`C:\Users\<usuario>\…\Financieros`, `…\CSV Auxiliares`, `…\BD_PptoTécnico_2025`, `…\Documentos`) se sustituyen por una sola constante `CARPETA = _DIR`, la carpeta donde está el script. Todos los insumos se leen de ahí y todos los archivos (intermedios y final) se escriben ahí. La base de valuación sigue en `\\adsroma`.
- **Nombre de la salida.** `RRC_esc_FNDcal.xlsx` con el FND calibrado y `RRC_esc_legado.xlsx` con `USAR_FND_CALIBRADO = False`, para no pisar el `RRC_esc.xlsx` de la v10 y poder compararlos con `comparar_outputs_reservas.py`.

## 3. `ReforecastSONR_v4.py`

- Mismo bloque de importación y configuración, más `fnd_cal(xRamo, xMesProc, xFecVal)` y `_es_no_proporcional`.
- `zFND`, `zFND_PPTO` y `zFND2` — reciben `xRamo` como último parámetro (opcional, así la firma sigue siendo compatible) y, cuando el negocio no es TipoRea 2, devuelven el FND calibrado por antigüedad de registro. Toda la lógica del no proporcional queda tal cual, incluido el ajuste de `xFinVig == 45930`.
- Los cinco puntos de llamada pasan el ramo: `Ramo_filt` en `ConsultaReal` y `ConsultaReal_USD`, `Ramo` en `ConsultaPPTO2025`.
- Con esto el SONR consume el mismo factor que la RRC, así que `Dev = 1 − FND` queda coherente entre las dos reservas por construcción, que es lo que pide la sección 8 del documento del MEC.
- **Rutas locales y nombre de la salida**, igual que en el RRC: las seis rutas fijas pasan a `CARPETA = _DIR` y la salida se llama `SONR_esc_FNDcal.xlsx` o `SONR_esc_legado.xlsx` según el interruptor, sin pisar el `SONR_esc.xlsx` de la v3.

## 4. `construir_input_mec.py`

Arrastra al Input tres campos que antes se leían y se tiraban, y sin los cuales no se puede auditar ni recalibrar el FND:

- `AñoSusc` (de `Año Susc.`) — permite verificar el filtro de año de suscripción del punto 2. (Las columnas se llaman `AñoSusc` y `CohorteAño`, con eñe, en el Input y en el triángulo.)
- `FinVigAAAAMM` (de `Fecha Fin de Vigencia`) — separa la prorrata exacta del no proporcional de la tabla por registro.
- `MesesPeriodo` (periodicidad de cuentas) — separa la frecuencia del δ calibrado en la próxima recalibración.

Los tres son opcionales: si la BD no trae la columna, el campo queda vacío, se reporta en Validaciones (`V12`, `V13`) y todo lo demás funciona igual. La periodicidad se busca entre varios nombres posibles (`Meses Periodo`, `Periodos`, `Período`…) porque el nombre exacto varía entre bases. Los `groupby` de las tres fuentes llevan `dropna=False` para que una fila con un campo opcional vacío no se pierda, `CANON` incorpora las tres columnas y la validación `V1` de duplicados usa el grano nuevo. `Registros_Vigencia_MEC.csv` arrastra además `TipoRea` cuando existe.

### 4b. Corte del año: real enero–julio 2026 + FCST agosto–diciembre 2026

`construir_input_mec.py` ahora arma el input con dos fuentes y `FRONTERA_REAL = 202607`, `VENTANA_PPTO = (202608, 202612)`:

- **La BD histórica manda.** `localizar_bd` busca primero la BD histórica del MEC (`BD_PptoTécnicoRPAT_GENERADA.xlsx`, la misma que leía el script original y que ya está actualizada a julio 2026) y sólo si no la encuentra usa `BDReal26.xlsx`. Con la histórica el input conserva toda la historia 2019–2026 y el archivo de vigencias se regenera completo. Si la BD trae registros posteriores a la frontera (un agosto parcial, por ejemplo) se descartan y se avisa en `V20`, para que agosto–diciembre venga siempre del presupuesto.

- **Detección de encabezado.** Ni `BDReal26.xlsx` ni `FCST2026.xlsx` se podían leer: traen filas de títulos y totales antes del encabezado (fila 2 y fila 3), y el script abortaba diciendo que faltaban columnas. `detectar_header` y `hoja_datos` ahora lo buscan en las primeras filas.
- **Nueva fuente `fuente_fcst()`.** Lee la hoja `Ppto2026`, convierte de USD a la moneda del input con el TC de cierre mensual (`cargar_tc`, que prioriza `tc_mensual_bd.csv`), homologa los subramos del FCST al grano de la BD (31/35/39 → 30, 71/73 → 70) y devuelve sólo los meses de la ventana. `localizar_fcst()` lo encuentra por patrón de nombre.
- **Candado de vigencias.** `Registros_Vigencia_MEC.csv` ya no se sobrescribe cuando la BD cubre menos de `MESES_MIN_VIGENCIAS` (24) meses de registro: se guarda aparte y se avisa, porque la curva PF+ del no proporcional se estima de ese archivo.
- **Cohorte = mes contable.** El input se organiza por fecha contable: cada fila es un movimiento que entra a los libros en un mes, y ese mes es su cohorte. El FCST y las fuentes alternas de la herramienta anclaban la cohorte a enero del año de suscripción, lo que arrojaba la prima proyectada a antigüedades de 19 a 71 meses e inflaba el triángulo en ese tramo; ahora cohortan en su mes de registro (antigüedad 0) y el año de suscripción queda como dato descriptivo en `AñoSusc`. La BD real no cambia: ahí hay `Fecha Inicio de Vigencia` por registro y el diseño original cohorta por vigencia.
- **Validaciones nuevas.** `V9` presupuesto contra realidad en el traslape, `V14` subramos colapsados, `V16` conversión de moneda, `V17` qué meses aporta cada fuente y si el año quedó con huecos, `V18` cobertura del histórico de vigencias, `V19` criterio de cohorte del FCST.

Resultado de la corrida: 13,255 M MXN reales (enero–julio) + 9,072 M proyectados (agosto–diciembre) = 22,327 M en 2026, sin meses faltantes. El detalle y las cuatro advertencias que dejó la corrida están en `input_mec_2026/LEEME.md`.

## 5. `generar_output_mec.py`

`NOMBRE_RAMO` tenía cruzados cuatro ramos de dos en dos. Corregido a 40 = Responsabilidad Civil, 50 = Marítimo y Transportes, 90 = Automóviles, 110 = Diversos, que es lo que dicen `xNoRamo` del reforecast RRC y el estado de resultados real. Sólo afectaba etiquetas del output.

## 6. `comparar_outputs_reservas.py` (nuevo)

Pone lado a lado el output anterior de cada reforecast (`RRC_esc.xlsx`, `SONR_esc.xlsx`) y el nuevo con el FND del modelo (`RRC_esc_FNDcal.xlsx`, `SONR_esc_FNDcal.xlsx`) y escribe `Comparativo_RRC.xlsx` y `Comparativo_SONR.xlsx` con cuatro hojas: Resumen (Tipo de Monto × Escenario), Por_ramo, Por_periodo (escenario 2) y Detalle (cruce completo por llave Reserva · Escenario · Tipo de Monto · Ramo · Periodo, con la columna `presente` = ambos / solo_base / solo_nuevo). La diferencia es siempre nuevo − base en MXN y USD; el % se recalcula sobre totales, nunca se promedian porcentajes; `Periodo` se cruza como texto porque el escenario 4 trae `202512-<mes>`; las filas repetidas por llave se suman antes de comparar y |dif%| > 2% queda en rojo. Sin argumentos busca los dos pares en su carpeta; con `<base> <nuevo> [etiqueta]` compara cualquier par (por ejemplo `RRC_esc.xlsx RRC_esc_legado.xlsx` para confirmar que la v11 apagada reproduce la v10 al centavo); `--demo` arma un par sintético y se autoverifica.

## 7. Validación (`validar_prima_devengada.py`, `preparar_insumos.py`, `verificar_excel_formulas.py`)

- **Año contable.** Se verificó que el `Año` de Resumen, PD_anual_por_ramo y Mensual es el año contable (`PERIODO // 100`, el mes de valuación de la RRC en la base BEL-IRR-MR, que es el mes en que se registra el movimiento), no el de suscripción. La columna pasó de `Anio` a `Año` en todas las hojas y CSV y el encabezado dice «Año contable»; `PERIODO` se etiqueta «Mes contable (AAAAMM)».
- **Marcas en el Excel.** En Mensual (y en las demás hojas donde aparecen) `PND_real` y `PND_CAL` van en azul: son la prima no devengada real y la del modelo calibrado contra la que se compara. Las columnas en ámbar traen **fórmulas vivas de Excel**: `PR = PE × (1 − ces)`, `BRUTO_CAL = PND_CAL × IS × (1 + g + mr)`, `NETO_CAL = BRUTO_CAL − PND_CAL × IS × c`, `ratio_CAL_real = PND_CAL / PND_real`, las variaciones `dBRUTO_*` y `dNETO_*` (mes contra mes dentro del mismo grupo) y `PD_tom_* = PE − dBRUTO_*`, `PD_ret_* = PR − dNETO_*`. Cada encabezado lleva un comentario con su fórmula y la hoja `Formulas` las lista todas. `verificar_excel_formulas.py` recalcula el libro con LibreOffice y comprueba que las 12 columnas de fórmulas reproducen los valores de Python (diferencia máxima 5e-7 USD en 530 filas).
- **Corribles en la carpeta local.** `preparar_insumos.py` (nuevo) construye `insumos\` a partir de los archivos crudos que estén en la misma carpeta (`BD_ BEL - IRR - MR.xlsx`, `Input_MEC_Devengamiento.xlsx`, `Registros_Vigencia_MEC.csv`, `Integración*.xlsb` opcional); `validar_prima_devengada.py` detecta solo el último mes con saldo de la base real (antes era una constante) y escribe en `salidas\`. Los CSV que genera son idénticos a los de la entrega anterior (diferencia máxima 4e-9).

## 8. Prueba de regresión

`test_integracion_fnd.py` comprueba que `mec.factor_no_devengado` del módulo parchado reproduce la prima no devengada con la que se calibró el modelo contra la RRC real, en cuatro fechas de valuación, y verifica las propiedades de la tabla (k < 0 y k ≥ 12 dan cero, 31 colapsa a 30, 71 a 70, FND acotado a [0, 1], cola del vector en cero).

Resultado actual, cuadre al centavo:

| Mes de valuación | PND módulo (USD) | PND calibración (USD) | Diferencia |
|---|---|---|---|
| 202312 | 341,965,442.52 | 341,965,442.52 | 0.00 |
| 202412 | 423,720,335.82 | 423,720,335.82 | 0.00 |
| 202512 | 515,919,344.48 | 515,919,344.48 | 0.00 |
| 202605 | 544,175,560.71 | 544,175,560.71 | 0.00 |

Correr desde la carpeta del proyecto: `python3 scripts_actualizados/test_integracion_fnd.py` (necesita `insumos/` y `salidas/`).

## Orden sugerido para implantar

0. Regenerar el input con la BD histórica actualizada a julio y el FCST (`construir_input_mec.py`), y volver a correr la validación (`preparar_insumos.py` + `validar_prima_devengada.py`) para tener el `delta_calibrado.json` fresco.
1. Copiar `mec_devengamiento.py` y `delta_calibrado.json` (de `salidas/`) a la carpeta local donde correrán los reforecast (ver `LEEME_carpeta_local.md`).
2. Correr `test_integracion_fnd.py` — debe dar OK antes de tocar los reforecast.
3. Sustituir el reforecast RRC por la v11 y correr un cierre en paralelo (shadow run) contra el vigente, con `USAR_FND_CALIBRADO = False` primero para confirmar que reproduce la v10 al centavo, y luego en `True`.
4. Comparar `RRC_esc.xlsx` (v10) contra `RRC_esc_legado.xlsx` y `RRC_esc_FNDcal.xlsx` con `comparar_outputs_reservas.py`: el primero debe dar cero y el segundo muestra el efecto puro del FND del modelo. Después, la prima devengada resultante contra la base BEL-IRR-MR con `validar_prima_devengada.py`.
5. Repetir 3 y 4 con el SONR.
6. Sólo entonces medir por separado el efecto de `FILTRO_ANIO_SUSC = False`, con el campo `Susc` de SIREC ya verificado.

## Lo que no está en el código y sigue pendiente

- **Documento MEC v6.0 (PDF).** Hay que reemplazar la frase de que el FND sale de la prorrata de vigencias: para proporcional y facultativo se calibra sobre la antigüedad de registro con δ por ramo; la prorrata aplica al no proporcional. El resto del marco (apertura por ramo, back-testing, M4) sigue vigente.
- **Base BEL-IRR-MR, hoja `HParametros_2026`.** El `Ind Sin RRC` de TEV e Hidro anterior a 202401 está en otra base (0.5 a 8.6 frente a 0.11 a 0.27 después). Hay que homologarlo o marcarlo.
- **Campo `Susc` de SIREC** para cerrar el punto del filtro de año de suscripción.
- **Recalibración trimestral.** Correr `validar_prima_devengada.py` en cada cierre y reajustar δ si el ratio total sale de ±3% o un ramo con peso mayor a 5% sale de ±10%. Vigilar Vida: su BEL pasó de 18 a 68 millones de USD entre diciembre de 2024 y mayo de 2026.
