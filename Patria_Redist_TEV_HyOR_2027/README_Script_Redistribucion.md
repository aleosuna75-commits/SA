# Script previo a CtaMens: `0_Redistribucion_TEV_HyOR.py` (v1.5)

Redistribuye primas (GL 61), comisiones (GL 53) y, opcionalmente, siniestros (GL 54) entre los
ramos **73 Terremoto (TEV)** y **71 Hidrometeorológicos y Otros Riesgos (HyOR)** en
`Inputs/PptoTecnico2027.csv`, **antes** de correr `CtaMens.py`. La metodología y su justificación están en
`Metodologia_Redistribucion_TEV_HyOR_2027.md`; este README cubre la operación. Las pruebas están en `pruebas/`.

## 0. Paso previo: actualizar la Base_1 con el real del año (`0a_Actualizar_Base1.py`)

La redistribución calcula los pesos con la historia real por LLAVE y ramo. Esa historia es la `Base_1` (la misma del proceso 2026),
actualizada con los meses reales del año en curso. Este script hace la actualización:

1. Deje la Base_1 del año pasado en `Inputs\Redistribucion\Base_1.xlsx` (no se modifica nunca).
2. Deje el real del año en `Inputs\Redistribucion\Base1_Nueva\` (uno o varios csv/xlsx). Acepta dos formatos:
   * **Formato Base_1** (mismas columnas: `LLAVE`, `DescRamo`, `AñoCont`, `MesCont`, `PmaTom`, ...).
   * **Extracto SAP BW de reales** con la misma estructura de columnas que `PptoTecnico2027.csv` (`/ERP/GL_ACCT`, `/ERP/AMOUNT`,
     `/ERP/PROFTCTR`, `/ERP/FUNCAREA`, `ZTIPOREAS`, `ZCEDENTE`, `ZCONTRATO`, `0CALMONTH`, `ZREGIONRP`, ...), pero de la categoría de **reales**.
3. **Incluya en la extracción nueva los últimos 2 o 3 meses que ya están en la Base_1 previa.** Esos meses de traslape son la prueba,
   con datos, de que la consulta nueva tiene la misma definición que la Base_1 (cuentas, signo, LLAVE, ramo).
4. `python 0a_Actualizar_Base1.py --dry-run` → revisar el libro `Outputs\Actualizacion_Base1\Control_Actualizacion_Base1_{fecha}.xlsx`.
5. `python 0a_Actualizar_Base1.py` → escribe `Inputs\Redistribucion\Hist_Real_LLAVE_Ramo.csv` (el insumo por defecto de la redistribución)
   y `Base_1_Actualizada.xlsx` (para `Base1_global.py`, si cabe en Excel).

Reglas del script:

| Tema | Regla |
|---|---|
| Unión | Los meses (AñoCont, MesCont) que trae la información nueva **reemplazan completos** a los mismos meses de la previa; no se suman. Los demás meses de la previa quedan intactos. |
| Traslape | Por métrica y por DescRamo, la nueva debe reproducir a la previa en los meses comunes (tolerancia 1 %). Si no cuadra, no escribe la base. `--aceptar-traslape "justificación"` permite escribir dejando constancia. Un extracto SAP sin traslape se detiene salvo `--sin-traslape "justificación"`. |
| Cuentas (SAP) | Prefijo 61 → `PmaTom`, 53 → `CosTom`, 54 → `SinTom`. Otras cuentas quedan fuera y se reportan en `GL_NoMap_*`. `--mapa-gl` cambia el mapa (columnas GL, METRICA, SIGNO). |
| Signo (SAP) | Primas ×(−1) para pasar de la convención SAP a la de la Base_1. Si el traslape muestra exactamente el signo contrario, se corrige y se documenta. Un `--signo` explícito del usuario nunca se corrige. |
| Categoría, moneda, sociedad | Si el extracto trae más de una, se detiene; se elige con `--filtro COLUMNA=VALOR`. Una categoría de presupuesto (`PRES…`) se rechaza. |
| LLAVE | `ZTIPOREAS-ZCEDENTE-ZCONTRATO-FUNCAREA`, contrato nulo = 0 (misma regla que CtaMens y la redistribución). |
| DescRamo | Desde el CeBe: `--mapa-descramo`, luego lo que diga la Base_1 previa, luego `Subramo.csv`; siempre con la ortografía de la previa. Un CeBe sin ramo o un DescRamo que no existe en la previa detiene la corrida (`--permitir-descramo-nuevo` si de verdad es un ramo nuevo). |
| Demás columnas | Directas del extracto (TipoRea, Susc, ...), `Territorio` con `Pais.csv`, o **aprendidas de la previa** sólo si allí la relación es unívoca (por FUNCAREA, DescRamo o LLAVE). Lo no derivable queda vacío, no en cero; las retenidas (`PmaRet`, `SinRet`, `CosRet`) quedan vacías para los meses nuevos de un extracto SAP. La hoja `Llenado_Columnas` dice cómo se llenó cada columna. |
| Meses que no pueden ser reales | Los periodos de la Base_1 previa posteriores a la fecha de guardado del archivo (p.ej. meses de 2026 en una Base_1 guardada en diciembre de 2025) se excluyen de la historia y se listan en la hoja `Previa_Excluida`; su real debe venir en la información nueva. `--conservar-posteriores` los deja. La redistribución aplica la misma regla: excluye de los años base los años posteriores a la fecha del archivo de histórico. |
| Carpeta | `Inputs\\Redistribucion` se acepta con o sin acento. |
| Periodo | `0CALMONTH` (AAAAMM o MM.AAAA); si no viene, `0FISCPER` con variante K4. Periodos especiales 13-16 detienen la corrida salvo `--especiales-a-diciembre`. |

Hojas del libro de control: `Resumen`, `Fallas`, `Cuadre` (previa − reemplazada + nueva = final, por métrica), `Traslape`, `Periodos`,
`Meses_por_Anio` (para saber si el año en curso llega a 8 meses), `Particip_TEV_HyOR` (participación de Terremoto por año, para comparar con
la serie histórica), `Llenado_Columnas`, `LLAVEs_Nuevas`, `GL_NoMap_*`, `DescRamo_*`.

## 1. Dónde se corre y en qué orden

```
5_Generacion/
├── Inputs/
│   ├── PptoTecnico2027.csv                 <- insumo original (no se modifica salvo --sobrescribir-input)
│   ├── PptoTecnico2027_Red.csv             <- SALIDA del script: mismas 45 columnas y orden
│   ├── Subramo.csv, Pais.csv, Cesion.csv, CesionPI.csv, Porc_Cesión_Hist.xlsx   <- insumos de CtaMens (opcionales: si están, se verifican)
│   └── Redistribucion/
│       ├── Hist_Real_LLAVE_Ramo.csv        <- histórico REAL por LLAVE, ramo, año y mes (ver §3)   [opción A, recomendada]
│       ├── Pesos_Ramo_TEV_HyOR.xlsx        <- tabla de pesos ya calculada / congelada (hoja "Pesos") [opción B, corrida productiva]
│       ├── TD.xlsx                         <- TD con el formato 2026 (hoja "TD")                   [opción C]
│       └── Layout_Redistribucion.xlsx      <- decisiones documentadas (EXCLUIR / INCLUIR / FORZAR)  [opcional]
├── 2_CostosXL/xMatCostoXL.xlsx, xDnCostoXL.xlsx, xDnRecup.xlsx    <- opcionales: verificación de la firma XL de los clones
├── 3_EvCat/xDnEvCat.xlsx, xDnAttritional.xlsx                      <- opcionales: verificación de PROFTCTR+región de los clones
└── Outputs/Redistribucion_TEV_HyOR/
    ├── Trazabilidad_Redistribucion_TEV_HyOR_{fecha}.xlsx   (sufijo _CONTROL_FALLIDO si un control detuvo la corrida)
    ├── Detalle_Filas_{fecha}.csv
    ├── Log_Redistribucion_{fecha}.txt
    ├── ERROR_{fecha}.txt                   <- sólo si la corrida se detuvo con error
    └── registro_salidas.txt                <- sha256 de cada csv generado (anti doble aplicación)
```

Orden de ejecución:

1. Confirmar que `PptoTecnico2027.csv` es el extracto SAP original. `python 0_Redistribucion_TEV_HyOR.py --dry-run` → revisar
   `Alcance_LLAVEs`, `LLAVEs_Revisar`, `LLAVEs_Sin_Peso`, `Sensibilidad_Metodos`, `Validacion_Tendencia`, y en el log la cobertura y la tolerancia sugerida.
2. Resolver con el negocio los casos `REVISAR` y `SIN_PESO`; capturar las decisiones en el Layout (con justificación).
3. Aprobar por escrito los parámetros; opcionalmente congelar `Pesos_Aplicados` como `Pesos_Ramo_TEV_HyOR.xlsx`.
4. Corrida productiva: `python 0_Redistribucion_TEV_HyOR.py --aprobacion "Nombre, fecha"`. Revisar `Control_Participacion`,
   `Control_Share_LLAVE`, `Combos_Nuevos`, `Combos_Desaparecen` y `Verif_Insumos_CtaMens`; completar las llaves de cesión que falten.
5. En `CtaMens.py` cambiar `xFile` a `PptoTecnico2027_Red.csv` (o correr con `--sobrescribir-input`, que copia el original a
   `Inputs/Backups/PptoTecnico2027_PreRedist_{fecha}.csv` y escribe el redistribuido con el nombre original).
6. **Dos pasadas de CtaMens:** pasada 1 → regenerar `xDnCostoXL`, `xDnRecup`, `xDnEvCat`, `xDnAttritional` con la base redistribuida → pasada 2.

Desde la v1.3 el script toma como carpeta de trabajo la carpeta donde está guardado (`5_Generacion`, junto a `CtaMens.py`), así que no hay que editar rutas. Si ahí no existe la carpeta `Inputs`, usa la ruta estilo `CtaMens.py` (`C:\Users\{usuario}\OneDrive - GPV\...\2027\5_Generacion`).
Cualquier ruta o parámetro se puede sobreescribir por línea de comandos: `python 0_Redistribucion_TEV_HyOR.py --help`.
Si se corre por doble clic, la ventana se queda abierta al terminar y cualquier error queda en el log y en `ERROR_{fecha}.txt`.

## 2. Parámetros metodológicos (bloque `DEFAULTS` del script)

| Parámetro | Valor por defecto | Significado |
|---|---|---|
| `ramos` | `[71, 73]` | Ramos entre los que se redistribuye. Bidireccional (71→73 y 73→71). |
| `anio_decision` | `2027` | Año fiscal sobre el que se decide el alcance (el que filtra CtaMens). El reparto se aplica a `anios_fiscales`. |
| `anios_base` | `[2025, 2026]` | Años del histórico real que alimentan los pesos. |
| `metodo_pesos` | `ponderado` | `ponderado`: suma de \|montos\| de los años base válidos. `ultimo`: último año válido. `promedio_simple`: promedio de las participaciones anuales. |
| `min_meses_anio` | `8` | Si el histórico trae el mes, un año base con menos meses registrados se excluye (precedente 2026: INCOMPLETE_MONTHS < 8). |
| `tolerancia` | `0.05` | Se ajusta cuando la participación del ramo 73 difiere de la de los pesos en más de 5 pp. También define la reclasificación total. El log reporta una tolerancia sugerida por el dato (p90 del rango interanual) cuando el histórico tiene ≥ 3 años. |
| `modo_alcance` | `auto` | `auto`: reglas + layout. `layout`: sólo las LLAVEs del layout. |
| `ajustar_split_explicito` | `False` | Una LLAVE que **ya trae ambos ramos** queda en `REVISAR`; se ajusta sólo con `INCLUIR`. |
| `reclasificacion_total` | `revisar` | Histórico ≥ 1−tolerancia en un ramo vs presupuesto ≥ 1−tolerancia en el otro → `REVISAR` (`auto` lo aplica). |
| `materialidad` | `0` | \|prima 71+73\| mínima (MXN) en el año de decisión para ajustar; 0 = sin filtro. Precedente 2026: 100,000 MXN anuales. |
| `credibilidad_pct` | `0.10` | `REVISAR` si la prima histórica base es menor que el 10 % de la prima presupuestada del año de decisión (o que la materialidad). |
| `banda_ratio` | `[1/3, 3]` | `REVISAR` si presupuesto ÷ último año real queda fuera de la banda. |
| `revisar_sensibles` | `True` | `REVISAR` si los tres métodos de peso difieren más que la tolerancia o hay cambio estructural (un año base mono-ramo y otro bi-ramo). |
| `revisar_facultativos` | `True` | ZTIPOREAS = 3 → `REVISAR` (la LLAVE agrupa varios contratos/corredores). Un contrato nulo en negocio no facultativo siempre queda en `REVISAR`. |
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
| `AJUSTAR` | Negocio cargado en un solo ramo, con pesos creíbles y estables, cuya participación difiere de la de los pesos en más de la tolerancia; o `INCLUIR`/`FORZAR` | Revisar en el dry-run junto con `Validacion_Tendencia`; después nada |
| `REVISAR` | Ya trae ambos ramos; reclasificación total; histórico poco creíble o fuera de banda; pesos sensibles al método o cambio estructural; facultativo; contrato nulo en no facultativo; sin primas de referencia | Confirmar con el negocio y capturar `INCLUIR` (o `EXCLUIR`, o `FORZAR` con el slip) |
| `NO_AJUSTAR` | Dentro de tolerancia, inmaterial, `EXCLUIR`, LN excluida, sin filas en el año de decisión, fuera del layout en modo `layout` | Nada |
| `SIN_PESO` | No hay histórico válido ni layout | Conseguir el dato (histórico real o condición contractual → `FORZAR`) |

Cada fila trae los datos que sustentan la decisión: participación presupuestada y de los pesos, diferencia, prima histórica base, último real,
razón presupuesto/real, años válidos, cambio estructural, sensibilidad, origen y fuente del peso, y si la estructura de ramos difiere en otros años fiscales.

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
