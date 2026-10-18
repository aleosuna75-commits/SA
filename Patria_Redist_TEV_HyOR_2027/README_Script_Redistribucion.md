# Scripts previos a CtaMens: `0a_Actualizar_Base1.py` (v2.0) y `0_Redistribucion_TEV_HyOR.py` (v2.2)

Redistribuyen primas (GL 61), comisiones (GL 53) y, opcionalmente, siniestros (GL 54) entre los ramos
**71 Terremoto (`A071000000`)** y **73 HyORH (`A073000000`)** en `Inputs\PptoTecnico2027.csv`, **antes** de correr `CtaMens.py`.
La metodología y su justificación están en `Metodologia_Redistribucion_TEV_HyOR_2027.md` (la sección 0.1 resume los cambios de la v2.0);
este README cubre la operación. Las pruebas están en `pruebas/`.

## 0. Cómo se corre (dos pasos, sin mover archivos)

Guarde los scripts en `5_Generacion`, junto a `CtaMens.py`. Toman como carpeta de trabajo la carpeta donde están guardados.

```
python 0a_Actualizar_Base1.py
python 0_Redistribucion_TEV_HyOR.py
```

1. **`0a_Actualizar_Base1.py` arma la Base_1.** Busca solo:
   * la Base_1 más reciente (`Base_1*.xlsx/csv` en `Inputs`, `Inputs\Redistribución` u `Outputs`), que nunca se modifica;
   * los CtaMens de cada año en `Outputs`, el más reciente por año: `BD_CtaMens_MMAA*.xlsx` (año 20AA) y `CtaMens_AAAA_*.xlsx`;
   * archivos reales nuevos, si existen, en `Inputs\Redistribución\Base1_Nueva` (extracto SAP BW de reales o formato Base_1).

   Escribe `Inputs\Redistribución\Base_1_{fecha}.csv` y `.xlsx` con la columna `FUENTE` (REAL o PPTO) y el libro
   `Outputs\Actualizacion_Base1\Control_Actualizacion_Base1_{fecha}.xlsx`.
2. **`0_Redistribucion_TEV_HyOR.py` redistribuye y escribe la base.** Toma la Base_1 más reciente (prefiere el csv) y el CtaMens del
   presupuesto 2026 aprobado, aplica los criterios fijos y escribe `Inputs\PptoTecnico2027_Red.csv`. El diagnóstico queda en
   `Outputs\Redistribucion_TEV_HyOR\Trazabilidad_Redistribucion_TEV_HyOR_{fecha}.xlsx`.
3. **CtaMens.** Apunte `CtaMens.py` a `PptoTecnico2027_Red.csv` (o corra la redistribución con `--sobrescribir-input`, que respalda el
   original en `Inputs\Backups`). **Dos pasadas:** pasada 1 → regenerar `xDnCostoXL`, `xDnRecup`, `xDnEvCat`, `xDnAttritional` con la base
   redistribuida → pasada 2.

Con cada corrida de `0a_Actualizar_Base1.py` se genera una Base_1 nueva con fecha; la redistribución siempre toma la más reciente.

### Reglas de la Base_1

| Tema | Regla |
|---|---|
| FUENTE | Cada fila dice si es REAL (contabilizado) o PPTO (presupuesto de un CtaMens, con el nombre del archivo). Sólo REAL alimenta los pesos; PPTO 2026 alimenta el respaldo. |
| El real manda | Un presupuesto nunca reemplaza meses que ya son reales (ni de la Base_1 previa ni de archivos reales nuevos). Lo descartado queda en la hoja `PPTO_Descartado`. |
| Meses que no pueden ser reales | Si la Base_1 previa no trae `FUENTE`, sus meses posteriores a la fecha en que se guardó el archivo se excluyen (hoja `Previa_Excluida`). |
| CtaMens → Base_1 | LLAVE = ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA; AñoCont/MesCont desde PERIODO o CALMONTH; DescRamo desde la columna RAMO/RamoN del CtaMens, con la ortografía de la previa cuando coincide; Territorio y FUNCAREA_2 directos; `PmaTom`/`CosTom`/`SinTom` desde GL 61/53/54 y `PmaRet`/`CosRet`/`SinRet` desde la columna RETENIDA; el signo se alinea con el de la parte REAL de la previa. |
| Real nuevo (SAP o Base_1) | Debe traer 2 o 3 meses que ya estén como reales en la previa; si esos meses no cuadran (1 % por métrica y por ramo), no se escribe la base. |
| Cuadre | Previa − reemplazada + nueva = final, por métrica (hoja `Cuadre`). |

### Archivos del diagnóstico de la redistribución que conviene leer primero

* `Resumen`: participación de Terremoto y HyORH antes y después, fuentes usadas, controles.
* `Alcance_LLAVEs`: decisión, caso, fuente del peso y alertas de cada negocio.
* `Ajustadas_Con_Alertas` y `Validar_SIREC`: lo que conviene revisar.
* `LLAVEs_Sin_Peso`: negocios sin ningún dato propio (no se ajustan).

## 1. Estructura de carpetas

```
5_Generacion/
├── 0a_Actualizar_Base1.py, 0_Redistribucion_TEV_HyOR.py, sirec_conexion.py, CtaMens.py
├── Inputs/
│   ├── PptoTecnico2027.csv                 <- insumo original (no se modifica salvo --sobrescribir-input)
│   ├── PptoTecnico2027_Red.csv             <- SALIDA de la redistribución: mismas columnas y orden
│   ├── Base_1.xlsx                         <- Base_1 original (dic-2025)
│   ├── Subramo.csv, Pais.csv, Cesion.csv, CesionPI.csv, Porc_Cesión_Hist.xlsx
│   └── Redistribución/                     <- con o sin acento
│       ├── Base_1_{fecha}.csv / .xlsx      <- SALIDA de 0a_Actualizar_Base1.py
│       ├── Base1_Nueva/                    <- opcional: reales nuevos (SAP BW o formato Base_1)
│       └── Layout_Redistribucion.xlsx      <- opcional: decisiones documentadas (EXCLUIR / FORZAR / INCLUIR)
├── 2_CostosXL/ y 3_EvCat/                  <- matrices que se verifican y se regeneran entre pasadas de CtaMens
└── Outputs/
    ├── BD_CtaMens_0526_1.xlsx, CtaMens_2027_5.xlsx   <- CtaMens de cada año (se leen, no se mueven)
    ├── Actualizacion_Base1/                <- control y log de la Base_1
    └── Redistribucion_TEV_HyOR/            <- trazabilidad, detalle fila a fila, log, registro sha256
```

## 2. Parámetros metodológicos (bloque `DEFAULTS` del script)

| Parámetro | Valor por defecto | Significado |
|---|---|---|
| `ramos` | `[71, 73]` | Ramos entre los que se redistribuye. Bidireccional (71→73 y 73→71). |
| `anio_decision` | `2027` | Año fiscal sobre el que se decide el alcance (el que filtra CtaMens). El reparto se aplica a `anios_fiscales`. |
| `hist` | `AUTO` | La Base_1 más reciente (o una ruta con `--hist`). |
| `ppto_previo` | `AUTO` | CtaMens del presupuesto aprobado del año anterior en `Outputs` (respaldo de pesos); `''` para no usarlo. |
| `modo_decision` | `fijo` | Criterios fijos: todo lo que difiere más que la tolerancia se ajusta y las cautelas quedan como `ALERTAS`. `revisar` = comportamiento v1. |
| `cartera_nuevos` | `True` | Contratos sin datos propios cargados en un solo ramo toman la mezcla de su grupo (cedente > LN y tipo de reaseguro > LN); grupo mono-ramo = no se tocan. `--sin-cartera` lo apaga. |
| `cartera_min_llaves` | `{CEDENTE: 1, LN_TIPOREA: 3, LN: 3}` | Otras LLAVEs con datos que debe tener el grupo para usarse. |
| `sirec` | `True` | Al terminar, consulta SIREC para los negocios `VALIDAR_SIREC`; si falla sólo avisa. `--sin-sirec` lo omite. |
| `anios_base` | `AUTO` | Los 2 últimos años REALES completos anteriores al año de decisión (hoy 2024 y 2025). |
| `metodo_pesos` | `ponderado` | `ponderado`: suma de \|montos\| de los años base válidos. `ultimo`: último año válido. `promedio_simple`: promedio de las participaciones anuales. |
| `min_meses_anio` | `8` | Un año base cuenta si la **base** tiene información real en al menos 8 meses de ese año (completitud del corte, no de cada negocio). |
| `tolerancia` | `0.05` | Se ajusta cuando la participación del ramo 73 (HyORH) difiere de la de los pesos en más de 5 pp. También define la reclasificación total. El log reporta una tolerancia sugerida por el dato (p90 del rango interanual) cuando el histórico tiene ≥ 3 años. |
| `modo_alcance` | `auto` | `auto`: reglas + layout. `layout`: sólo las LLAVEs del layout. |
| `ajustar_split_explicito` | `False` | Una LLAVE que **ya trae ambos ramos** queda en alerta (en modo `revisar`: `REVISAR`); se ajusta sólo con `INCLUIR`. |
| `reclasificacion_total` | `revisar` | Histórico ≥ 1−tolerancia en un ramo vs presupuesto ≥ 1−tolerancia en el otro → alerta (en modo `revisar`: `REVISAR`) (`auto` lo aplica). |
| `materialidad` | `0` | \|prima 71+73\| mínima (MXN) en el año de decisión para ajustar; 0 = sin filtro. Precedente 2026: 100,000 MXN anuales. |
| `credibilidad_pct` | `0.10` | alerta (en modo `revisar`: `REVISAR`) si la prima histórica base es menor que el 10 % de la prima presupuestada del año de decisión (o que la materialidad). |
| `banda_ratio` | `[1/3, 3]` | alerta (en modo `revisar`: `REVISAR`) si presupuesto ÷ último año real queda fuera de la banda. |
| `revisar_sensibles` | `True` | alerta (en modo `revisar`: `REVISAR`) si los tres métodos de peso difieren más que la tolerancia o hay cambio estructural (un año base mono-ramo y otro bi-ramo). |
| `revisar_facultativos` | `True` | ZTIPOREAS = 3 → alerta (en modo `revisar`: `REVISAR`) (la LLAVE agrupa varios contratos/corredores). Un contrato nulo en negocio no facultativo siempre queda en `REVISAR`. |
| `excluir_funcarea` | `["LN04004"]` | LN cuyo centro de beneficio reescribe CtaMens: fuera de alcance. |
| `comisiones` | `propio` | Pesos propios del histórico de comisiones; si no los hay o son inválidos, los de primas (documentado en `ORIGEN_PESO`). Un `FORZAR` gobierna todos los tipos. Alternativas: `prima`, `no`. |
| `siniestros` | `prima` | Los siniestros GL 54 de 71/73 (si existen) se reparten con los pesos de primas. Alternativas: `propio`, `no` (como en 2026). |
| `anios_fiscales` | `todos` | Aplica el reparto a todos los años fiscales del archivo. Alternativa: `[2027]`. |
| `conservar_filas_cero` | `True` | Una fila cuyo ramo queda con peso 0 se escribe con monto 0 (CtaMens la ignora; el `_ID` de todas las filas originales se mantiene estable). `--no-conservar-cero` las omite. |
| `decimales` | `2` | Redondeo de los montos nuevos (pandas, half-even); si el insumo trae más decimales se usa el máximo observado. |
| `aprobacion` | `""` | Responsable y fecha de aprobación de parámetros y layout; queda en `Resumen` (corrida productiva). |
| `max_filas_excel_detalle` | `200000` | `Detalle_Filas` va siempre en csv; en el xlsx sólo hasta este tamaño. |

## 3. Formato de los insumos

### 3.1 `Hist_Real_LLAVE_Ramo.csv` / `.xlsx` (opción A, recomendada)

Formato largo (una fila por LLAVE × ramo × periodo × cuenta) **o** ancho tipo `Base_1` (columnas `PmaTom`, `CosTom`/`ComTom`, `SinTom`).

| Dato | Columnas aceptadas | Ejemplo |
|---|---|---|
| Negocio | `LLAVE`, o `ZTIPOREAS`, `ZCEDENTE`, `ZCONTRATO`, `FUNCAREA` (alias `TipoRea`, `CiaTom`, `CtoTom`, `LN`); contrato nulo o vacío = 0 | `1-40-16-LN04001` |
| Ramo | `RAMO` (71/73), `PROFTCTR`/`CeBe` (`A071000000`), o `DescRamo`/`RamoN` texto (`Terremoto`, `HYORH`) | `73` |
| Periodo | `CALMONTH`/`PERIODO` (AAAAMM, recomendado: permite validar meses), o `ANIO`/`AñoCont` (+ `Mes` opcional) | `202503` |
| Cuenta | `GL`/`TIPO`/`TY` (`61`/`53`/`54`, `6108010000`, `Primas`…) + `MONTO`; o columnas anchas `PmaTom`/`CosTom`/`SinTom` | `61` |
| Monto | `MONTO`, `AMOUNT`, `/ERP/AMOUNT`, `IMPORTE` | `-1234567.89` |

Reglas: los montos deben ser numéricos (el script aborta si encuentra texto). La validez se evalúa **año por año**: un año cuenta sólo si
los montos de ambos ramos tienen el mismo signo, no suman cero y (con detalle mensual) tiene al menos `min_meses_anio` meses; los años
excluidos quedan en `MOTIVO`. Si no queda ningún año válido, la LLAVE va a `LLAVEs_Sin_Peso`. Los pesos se redondean a 10 decimales y se renormalizan.
`Pesos_Calculados` trae además, por LLAVE y tipo, los años válidos, el último año y su monto, y si hubo cambio estructural.

### 3.2 `Pesos_Ramo_TEV_HyOR.xlsx`, hoja `Pesos` (opción B)

`LLAVE | RAMO | TIPO | PESO | FUENTE | DETALLE | ORIGEN_PESO`, un renglón por ramo y tipo; los pesos de cada LLAVE-TIPO deben sumar 1 y no
repetirse. La hoja `Pesos_Aplicados` de la trazabilidad tiene exactamente este formato, de modo que una corrida con histórico puede
"congelarse" como tabla revisada y aprobada conservando el origen de cada peso. Con esta opción no hay sensibilidad ni credibilidad
(los pesos ya fueron revisados), pero sí todas las demás reglas de alcance.

### 3.3 `TD.xlsx`, hoja `TD` (opción C, compatibilidad con 2026)

`LLAVE | Ramo | Monto Prima | Monto Comisiones | Monto Siniestros`. Los montos se convierten en pesos por LLAVE y tipo (valor absoluto;
signos opuestos entre ramos → inválido). Las LLAVEs con tramo de contrato vacío (`3-25--LN04002`, formato 2026) se homologan a `3-25-0-LN04002`.

### 3.4 `Layout_Redistribucion.xlsx` (opcional, decisiones documentadas)

| LLAVE | ACCION | RAMO | PESO_PRIMA | PESO_COMISION | PESO_SINIESTRO | METODO | FUENTE | JUSTIFICACION |
|---|---|---|---|---|---|---|---|---|
| `1-181-4-LN04001` | `EXCLUIR` | | | | | | Suscripción | Renovado 2027 sólo HyOR (correo del suscriptor, fecha) |
| `2-85-4-LN04001` | `FORZAR` | 71 | 0.5 | | | | Slip 2027 | El slip fija 50 % TEV / 50 % HyOR |
| `2-85-4-LN04001` | `FORZAR` | 73 | 0.5 | | | | Slip 2027 | El slip fija 50 % TEV / 50 % HyOR |
| `1-264-19-LN04001` | `INCLUIR` | | | | | `ultimo` | | Confirmado por el negocio (caso REVISAR); renovación 2026, usar último año |

* **Toda** acción exige `JUSTIFICACION`; `FORZAR` exige además `FUENTE`, una fila por ramo y `PESO_PRIMA` para todos los ramos
  (`PESO_COMISION`/`PESO_SINIESTRO` opcionales, pero si se dan, para todos los ramos; si faltan se usan los de primas forzados).
  `FORZAR` sustituye por completo los pesos de la fuente para esa LLAVE. `INCLUIR` admite `METODO` (`ponderado`, `ultimo`, `promedio_simple`)
  para esa LLAVE; `INCLUIR`/`EXCLUIR` con pesos capturados detienen la corrida (use `FORZAR`). Filas en blanco se ignoran; LLAVEs con `4.0`
  o minúsculas se normalizan; una LLAVE del layout que no exista en el presupuesto detiene la corrida.

## 4. Decisiones de alcance (hoja `Alcance_LLAVEs`, sobre el año de decisión)

| DECISION | Cuándo | Qué hacer |
|---|---|---|
| `AJUSTAR` | La participación presupuestada difiere de la del peso en más de la tolerancia (`CASO`: `MONO_RAMO`, `SPLIT_EXPLICITO` o `RECLASIFICACION_TOTAL`); o `INCLUIR`/`FORZAR` en el layout | Revisar `ALERTAS` cuando las haya; si una es fundada, `EXCLUIR` o `FORZAR` en el layout y volver a correr |
| `NO_AJUSTAR` | Dentro de tolerancia, inmaterial, `EXCLUIR`, LN04004, sin filas en el año de decisión | Nada |
| `SIN_PESO` | Sin peso contractual, ni real válido, ni presupuesto aprobado 2026 | Conseguir el dato (condición contractual → `FORZAR`) |
| `REVISAR` | Sólo en `--modo-decision revisar` | Confirmar con `INCLUIR` / `EXCLUIR` |

`FUENTE_PESO` dice de dónde salió el porcentaje (`HIST_ponderado` = real; `PPTO_APROBADO_2026` = respaldo; `CARTERA_*` = contrato nuevo con la mezcla
de su grupo; `LAYOUT_FORZADO` = contrato). La hoja `Cartera_Nuevos` explica, contrato por contrato, qué grupo se usó o por qué no se tocó.
`VALIDAR_SIREC` marca facultativos y contratos nulos, que conviene cotejar contrato por contrato con `sirec_conexion.py`.

## 5. Qué produce

* `PptoTecnico2027_Red.csv`: mismas columnas, mismo orden y mismos tipos que el original, en `utf-8-sig`. Las filas no afectadas quedan
  **idénticas en valor y tipo** al leerlas con `pd.read_csv(thousands=',')` y en la misma posición (el texto se reserializa; la prueba es el
  control 1, no un `diff`). Los clones se agregan al final con el centro de beneficio del ramo destino (`A073000000` / `A071000000`).
* `Trazabilidad_Redistribucion_TEV_HyOR_{fecha}.xlsx`:
  * `Resumen`: parámetros, aprobación, fuentes, sha256 del insumo, cobertura, conteos y resultado de los controles.
  * `Alcance_LLAVEs`, `LLAVEs_Revisar`, `LLAVEs_Sin_Peso`, `LLAVEs_No_Cruzan`.
  * `Pesos_Calculados` / `Pesos_Aplicados`; `Sensibilidad_Metodos`; `Validacion_Tendencia`.
  * `Detalle_Filas` (también en csv): cada fila tocada con `_ID_ORIGEN`, firma, pool, signo, ramo origen/destino, monto original, peso, origen
    del peso, monto nuevo, residuo y movimiento (`RECALCULADA`, `CLON`, `A_CERO`, `SIN_CAMBIO`).
  * `Control_Participacion` (global, LN, región), `Control_Share_LLAVE`, `Control_Tipo_Anio`, `Control_LLAVE_Mes`.
  * `Combos_Nuevos` y `Combos_Desaparecen`: combinaciones (PROFTCTR-región, LN-ramo-región-tipo, llave de cesión histórica) con prima que
    aparecen o desaparecen; `Verif_Insumos_CtaMens`: para los clones, existencia de su llave en `Cesion.csv` (LLAVE1 exacta con `Pais.csv` y
    `Subramo.csv`), `CesionPI.csv`, `Porc_Cesión_Hist.xlsx`, `xDnEvCat`, `xDnAttritional` y de su firma en `xDnCostoXL`/`xDnRecup`
    (con `xMatCostoXL`), según los archivos que existan en disco.
* `Log_Redistribucion_{fecha}.txt`, `registro_salidas.txt` y, si aplica, `ERROR_{fecha}.txt`.

## 6. Controles que el script impone (se detiene, sin escribir el csv, si fallan; la trazabilidad se escribe con sufijo `_CONTROL_FALLIDO`)

1. Las filas fuera del alcance son idénticas al original (todas las columnas).
2. Conservación exacta por **firma** (todas las columnas excepto centro de beneficio y monto) en todo el archivo; cuadre por LLAVE × tipo × año × mes, por tipo × año y global (0.00).
3. La participación resultante de cada LLAVE ajustada y tipo es igual al peso aplicado (tolerancia 0.001); las no ajustadas conservan su participación.
4. Conteo de filas = original − filas a cero omitidas + clones.
5. Pesos válidos y únicos; layout completo y justificado; monto no vacío y numérico; centros de beneficio de los clones presentes en `Subramo.csv`; la salida no puede ser el insumo sin respaldo.
6. Anti doble aplicación por sha256.

Diagnósticos en el log: cobertura (porcentaje de la prima del año de decisión en LLAVEs con pesos; advertencia por debajo del 50 %) y firmas
huérfanas (firmas con un solo ramo en LLAVEs bi-ramo).

## 7. Diferencias deliberadas respecto al proceso 2026

| Tema | 2026 (`2.1.redistribucion_llave_ocl.py`) | 2027 (este script) | Por qué |
|---|---|---|---|
| Qué define el monto por ramo | `TD.xlsx` traía **montos objetivo absolutos** por LLAVE-Ramo-Tipo capturados a mano; el total del negocio podía cambiar | **Pesos** con fórmula explícita; el total de cada firma (y del negocio) se conserva exactamente | Corrección de asignación, no recalibración de niveles |
| Ramos tocados | Todos los ramos de la LLAVE presentes en el TD, con clon hacia cualquier ramo faltante | Sólo 71 y 73 | Alcance acotado al problema |
| Unidad de reparto | Grupo LLAVE-Ramo-Tipo, `Pct_Distrib = \|monto\| / Σ\|monto\|` redondeado a 6 decimales; signo del TD | Pool por firma y signo: cada fila se reparte con el peso; los reversos conservan su signo | Reproduce al cargador y evita que el signo dependa del TD |
| Cierre al centavo | Mayor resto por grupo | Residuo a la fila mayor del pool | Conservación exacta por firma; diferencia máxima 0.01 por fila |
| Centro de beneficio del clon | Reemplazo de cadena (`estricto` inoperante, parchado) | Código observado en el archivo, validado contra `Subramo.csv` | Robustez |
| Contrato nulo / facultativos | De hecho fuera del proceso (1.1 omitía la LLAVE; 3.1 escribía tramo vacío) | En alcance con contrato 0, siempre en `REVISAR` | Decisión nueva, documentada |
| Siniestros GL 54 | No se tocaban; clones a cero | Política parametrizable (por defecto pesos de primas); no existen para 71/73 en el presupuesto | Decisión documentada |
| Selección de LLAVEs | Banderas de tendencia + selección manual | Reglas objetivas sobre el año de decisión + `REVISAR` + layout justificado; umbrales 2026 como validación y materialidad | Reproducible y auditable |
| Orden | Redistribuir sobre BD_CtaMens y ceder después (pasos manuales) | Un script sobre el csv crudo antes de CtaMens, y dos pasadas de CtaMens por las matrices | Sin pasos manuales |

## 8. Pruebas realizadas y desempeño

`pruebas/01_generar_datos_prueba.py` crea, a partir del extracto `PptoTecnico2027.xlsx`, un csv de prueba, un histórico sintético escalado a la
prima 2027 de cada LLAVE y un layout; `pruebas/02_verificacion_independiente.py` comprueba, sin reutilizar código del script, columnas y
tipos idénticos, filas fuera del alcance idénticas, totales por LLAVE-cuenta-mes-año iguales al centavo, clones con atributos idénticos a su
fila origen y participación resultante igual al peso esperado; `pruebas/03_casos_limite.py` corre 24 casos (ambos ramos presentes, sólo 71,
sólo 73, histórico sólo de primas, pesos propios de comisiones, varios años y métodos, año con reversa, histórico inválido, LLAVE ausente,
separador de miles, años base vacíos, formato ancho Base_1, EXCLUIR/INCLUIR/FORZAR y sus errores, layout con filas en blanco y LLAVEs `4.0`,
LLAVE inexistente, firmas con signos mixtos, monto vacío, doble aplicación, reclasificación total, materialidad, tabla de pesos duplicada y
congelada, respaldo, sólo FY 2027, sin `ZREGIONRP`, dry-run, fila original en cero, salida igual al insumo, INCLUIR sin justificación,
`Subramo.csv` sin el CeBe del clon). Compatibilidad probada por revisores en pandas 2.0.3, 2.1.4, 2.2.3 y 3.0.5.

Desempeño (4 núcleos, 16 GB): 1.4 millones de filas con 6,580 LLAVEs ajustadas (peor caso): unos 220 s, de los cuales unos 60 s son controles
y unos 50 s la trazabilidad. Memoria pico del orden de 3 a 4 GB por millón de filas.

**Pruebas de la v2.0.** Los 24 casos de `03_casos_limite.py` corren con `--modo-decision revisar` para seguir midiendo el comportamiento v1.
`pruebas/04_prueba_actualizar_base1.py` (20 verificaciones) prueba la Base_1: traslape, signos, categorías, CeBe sin ramo, formatos SAP y Base_1,
periodos posteriores a la fecha del archivo y lectura por la redistribución. `pruebas/05_prueba_criterios_fijos.py` (21 verificaciones) prueba
los criterios fijos: búsqueda de la Base_1 más reciente, traducción Terremoto = 71 / HyORH = 73, años base automáticos, peso real,
respaldo con el presupuesto 2026 aprobado, `SIN_PESO`, tolerancia, que el presupuesto 2027 nunca sea peso, conservación del total y, desde la v2.2,
la cartera para contratos nuevos (peso de la cedente, partición de la LN respetada, cedente mono-ramo sin tocar y `--sin-cartera`).

**Corrida con los archivos reales (16/10/2026).** Con el extracto LN04001/LN04002, la `BD_CtaMens_0526_1.xlsx` y el `CtaMens_2027_5.xlsx`:
`0a_Actualizar_Base1.py` tarda unos 2 minutos (lectura de los dos xlsx) y reproduce la participación de Terremoto de cada CtaMens (54.08 % en
2026 y 30.16 % en 2027); la redistribución tarda 31 s, ajusta 194 de 329 negocios y lleva Terremoto de 10.9 % a 46.1 % de la prima 2027 del
extracto. Una verificación independiente confirmó totales por LLAVE-cuenta-año-mes intactos, filas de otros ramos idénticas y, en los 194
negocios ajustados, una participación igual a la del presupuesto 2026 aprobado (diferencia máxima 0.000003). En esa corrida la Base_1 real era
sintética; con la Base_1 real los negocios con real válido tomarán su peso del real.

**Cartera para contratos nuevos (v2.2, 18/10/2026).** Con el CtaMens 2027 completo convertido a formato de presupuesto (todas las LN, 614
negocios con Terremoto o HyORH) y los pesos del presupuesto 2026, el script deja a Terremoto en 50.18 % sin cartera y en 53.06 % con cartera.
45 contratos nuevos (14.5M USD de prima) toman la mezcla de su grupo: 24 la de su cedente y 21 la de su LN y tipo de reaseguro. Otros 36 se dejan
como vienen porque su grupo es de un solo ramo. Una verificación independiente recalculó el grupo, la fuente y el peso de los 81 candidatos
sin usar el código del script y coincidió en los 81.
