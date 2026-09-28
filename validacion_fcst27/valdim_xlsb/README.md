# ER vs vistas de ER — validación por dimensión de `FCST_2027_Cesion.xlsb`

Herramienta que evalúa cada renglón del estado de resultados de las vistas
`ER_ram`, `ER_ln`, `ER_reg` y `ER_tre` para **cada miembro** (como si el selector
`A6` se pusiera en cada uno), suma los miembros y los compara contra el renglón
equivalente de la hoja `ER`. El resultado se entrega **dentro del mismo libro**, en
siete hojas nuevas armadas con fórmulas que apuntan a las celdas de origen.

## Resultado

Las cuatro vistas reproducen ER en **13 de los 20 renglones** (diferencia 0.00 en
todos los meses). Los otros 7 no cuadran por la misma cantidad en las cuatro
dimensiones, es decir, no es un problema de datos sino de fuentes distintas:

| Renglón de la vista | Diferencia (dic.) | Por qué |
|---|---:|---|
| 17 Siniestros Ocurridos | −41,811,767.85 | ER agrega `CAT!H27:S27` + `CAT!H83:S83` (eventos CAT globales); la vista toma `CtaMens!AC×xEvCat + AD`, en cero |
| 24 Siniestros Netos | −27,419,200.81 | Lo anterior menos los recuperados CAT `CAT!H41:S41` + `CAT!H84:S84` (14,392,567.04) |
| 31 Gastos Generales | −38,249,042.87 | ER toma `Gastos!C12:N12`; la vista suma `CtaMens!AF`, en cero |
| 20, 28, 33, 35 | — | Resultados que arrastran las tres anteriores |

Las tres diferencias se comprueban al centavo con fórmulas en `Val_Resumen`.

Observaciones adicionales que salieron del análisis:

- `ValDim` no sirve como validación: de sus 31 filas de miembro solo la primera de
  cada vista tiene fórmula (`=ER_x!P$9`); las otras 27 son valores pegados, y esa
  fila viva muestra el miembro del selector, no el de su rótulo. `Val_ValDim` lo
  documenta miembro por miembro.
- Etiquetas: `Crédito` (con acento, en `2_Reservas`) y `Credito` (sin acento, en
  `CtaMens`) son dos filas distintas; `LN04008-Agro` está en `CtaMens` pero no en la
  tabla de reservas, y `LN04008`/`LN04009` al revés. `GMM` y `Crédito` no tienen
  renglones en `CtaMens` pero sí reservas, así que hay que incluirlos.
- Los totales de SONR que usa ER (`2_Reservas` filas 118 y 136) dejan fuera la fila
  de Fianzas (117 y 135), que hoy está en cero.
- `Gastos!C5:N5` rotula los meses como 2026; conviene confirmar que la fila 12 es 2027.

## Hojas que se agregan al libro

| Hoja | Contenido |
|---|---|
| `Val_Resumen` | Los 20 renglones × 4 dimensiones a diciembre: suma de miembros, ER, diferencia y `¿Cuadra?`; abajo, la comprobación de las tres diferencias con los importes de `CAT` y `Gastos` |
| `Val_Ramo`, `Val_LN`, `Val_Region`, `Val_TRea` | Un bloque por renglón: cada miembro con la fórmula de la vista, mes a mes acumulado; suma, ER y diferencia |
| `Val_Origen` | Fórmula de cada renglón en la vista y en ER, mapa de columnas de `CtaMens`, tablas de `2_Reservas`, universo de miembros y selectores vivos |
| `Val_ValDim` | Por qué `ValDim` muestra descuadres |

11,307 fórmulas (6,336 `SUMIFS`), ninguna cifra capturada. El libro queda en su
modo de cálculo manual; las hojas se guardan ya calculadas y `calcChain` no se toca.

## Reparar el libro después de editarlo en Excel

`reparar.py` toma el libro tal como lo dejó el usuario (con columnas u hojas borradas)
y, sin cambiar su disposición:

1. Cambia `SUM(_xlfn.SINGLE(rango))` por `SUM(rango)`. Las primeras versiones de
   `xlsbw.area()` escribían el rango con clase *valor* (`0x45`); Excel lo interpreta
   como `@rango` y la suma da `#VALUE!` en cuanto recalcula. Ya se escribe con clase
   *referencia* (`0x25`).
2. Reemplaza las referencias que quedaron en `#REF!` porque se borró la columna a la que
   apuntaban (hoy: `Val_Resumen!E7:E26`, el ¿Cuadra? de Ramo) por `ABS(D{fila})<0.005`.
3. Recalcula el valor guardado de todas las fórmulas de las hojas `Val_*` con
   `evaluador.py`, porque el libro está en cálculo manual.

Todo lo demás se copia byte a byte. `verificar3.py` comprueba integridad, relee y
reevalúa cada fórmula, y compara celda por celda contra la versión validada
trasladando las columnas borradas.

```bash
cp <libro editado>.xlsb USR.xlsb
cp <libro validado>.xlsb MIO.xlsb        # para la comparación
python3 reparar.py                      # escribe FCST_2027_Cesion.xlsb
python3 verificar3.py
```

## CAT y Gastos Generales en `CtaMens`

Las vistas `ER_*` toman los siniestros CAT de `CtaMens!AC` (eventos), `AD` (attritional) y
`AE` (CAT cedido), y los gastos de `CtaMens!AF`. El ER los toma directo de las hojas `CAT`
(filas 27, 41, 83, 84) y `Gastos` (fila 12). En el FCST 2027 esas columnas venían en cero,
por eso los renglones 17, 24 y 31 (y los resultados 20, 28, 33, 35) no cuadraban.

`Integración2026_Dim_10` sí las trae llenas, y la regla se dedujo de sus datos:

| Columna | Origen | Reparto |
|---|---|---|
| `AD` | `CAT!H14:S25` (Cebe × territorio × mes) | entre renglones B=61 del mismo Cebe, territorio y mes, en proporción a `MONTO` |
| `AE` | `AD` | × % de cesión: 0.25 Ultramar (`CAT!Z38`), 0.86 Terremoto (`Z39`), 0.30 Hidro (`Z40`) |
| `AC` | `CAT!H49:S66` | igual que `AD` |
| `AF` | `Gastos!C12:N12` (mes) | entre todos los renglones B=61 del mes, en proporción a `MONTO` |

Reaplicada a los 293,186 renglones de `Integración2026`, reproduce `AC` y `AF` exactos,
`AD` con diferencia máxima de 0.05 por renglón y `AE` de 0.01.

En 2027 hay 6 combinaciones Cebe × territorio × mes con attritional (y 6 con eventos) sin
prima en el mes (A071 R04 y R06). Se reparten en el mismo Cebe y mes entre los territorios
de la misma clase de cesión; así se conserva mes, ramo y % de cesión, y solo cambia la
región a la que se atribuyen 110,563.30 de attritional.

`aplicar_cat.py` escribe esos importes en `CtaMens`, agrega la hoja `Val_CAT` (todo en
fórmulas: dónde entra hoy el CAT al ER, el reparto mes a mes y por Cebe × territorio, y los
casos sin prima), recalcula los valores guardados de las hojas `Val_*` y enciende
`fFullCalcOnLoad` para que Excel recalcule las vistas al abrir. Como las celdas cambian de
tamaño, se eliminan los índices binarios (`binaryIndexNN.bin`, opcionales, que Excel regenera
al guardar) de toda hoja que se reescribe: `CtaMens` y las hojas `Val_*`. `reparar.py` hace lo
mismo; la primera versión de la reparación los dejaba desfasados.

Observaciones que no se cambiaron porque son decisiones del modelo:

- `CAT!T14:T25` (primer año) usa la tasa de Terremoto `Z$8` en las 12 filas; los años
  siguientes usan la tasa por tipo (fila 7 Ultramar, 8 Terremoto, 9 Hidro). Con esa lógica el
  attritional 2027 sería 50,102,582.76 en vez de 41,811,767.85. `Integración2026` hace lo mismo.
- Las tasas `CAT!Z7:Z9` de 2027 son las mismas constantes que en `Integración2026` eran de 2026.
- El "Ajuste para Londres" (`CAT!T32:T33`, 8.4 M) no entra en ningún total.
- `ER_ram!E47:P60` suma `CtaMens!AC` sin multiplicar por `xEvCat`: con `AC` lleno, su control
  de la fila 66 muestra los eventos CAT como diferencia para Incendio, Terremoto y HyORH.
- Si `xEvCat` fuera 1, la fila 24 de las vistas no cuadraría: el ER resta `CAT!84` (6 M de
  eventos Ultramar) y las vistas no, y `AB` entra con signo contrario.

```bash
python3 load_int.py NUESTRO.xlsb nuestro_ctamens.pkl
python3 cat_reparto.py        # reparto.pkl
python3 aplicar_cat.py        # FCST_2027_Cesion.xlsb
python3 verificar4.py
```

## `05_FCST_2027.xlsx`: llenado desde las vistas y su validación

El reporte `05_FCST_2027.xlsx` (seis hojas `Ppto…_Red`, en MXN) se llena recorriendo un año:

| Donde estaba | Ahora va | De dónde sale |
|---|---|---|
| 2026 | **2027** | Vistas `ER_ln`, `ER_ram`, `ER_reg`, `ER_tre` evaluadas por miembro, y `ER` para el total mensual |
| 2025 | **2026** | El presupuesto 2026 que ya traía el mismo archivo, recorrido una posición |
| 2024 | **2025** | El real 2025 que ya traía el archivo (es la columna D de cada vista) |

**Moneda.** 2027 va en pesos: cada flujo mensual × `'Parámetros'!F3:Q3` y acumulado, que es lo
que dan las vistas con `xMonEEFF = "MXN"`. El libro se guarda en USD, así que las cifras se
calculan fuera y la validación convierte con fórmulas.

**Bloques.** Cada bloque del 05 se asigna a uno o más miembros de la vista. Los casos
compuestos son:

- Daños Facultativos Sur y Agropecuario = `LN04008` (reservas) + `LN04008-Agro` (`CtaMens`);
- Crédito = `Crédito` (reservas) + `Credito` (`CtaMens`).

Así ningún miembro queda fuera y los bloques suman `ER`. El mapeo se comprobó con el 2025: el
real que traía el 05 es igual, celda por celda, a la columna D de la vista para esos miembros, y
el 2024 a la columna C.

**Lo que quedó vacío o con criterio:**

- **`'2027 CA'`** (PptoxLN_Red) se deja vacía. En el archivo anterior `'2026 CA'` era el mismo
  total con otro reparto entre LN, y el libro no trae esa clasificación para 2027.
- **Filas financieras de 2027** en PptoxMes_Red: quedan vacías las que dependen de `ER!Q62`,
  `Q63` y `Q67`, que tienen `=$Q63/12+P63` (referencia circular, sin cálculo iterativo). Con
  ellas quedan vacíos el RIF, los impuestos y la utilidad.
- **Columnas T/U/V:** T y U se recorren; V se calcula con la regla de cada renglón. Las filas de
  variación de reserva (11 y 12) quedan vacías en V porque su razón no sale de la hoja.
- **Mayo de 2026:** traía `'|'` en lugar de cifra. Se puso Prima Tomada − Prima Devengada, que es
  como sale en los demás meses.

**Hojas que se agregan al libro de Cesión** (mismo formato que las `Val_*`, todo en fórmulas
salvo las cifras del 05, que van capturadas):

| Hoja | Contenido |
|---|---|
| `Val05_Resumen` | Los 20 renglones a diciembre por hoja del 05 contra su referencia, y el conteo de celdas que cuadran. Incluye el 2025 recorrido y las observaciones |
| `Val05_Mensual` | PptoxMes_Red contra ER en MXN, mes a mes; W (2025) contra `ER!E` |
| `Val05_LN`, `Val05_Ramo`, `Val05_Region`, `Val05_TRea` | Cada bloque del 05 contra la vista en MXN, que sale de `Val_x` × `'Parámetros'!F3:Q3` ÷ `ER_x!E6:P6`. Traen la suma de bloques contra ER y el 2025 contra la columna D de la vista. `Val05_LN` trae además PptoxLN_Red |

La conversión divide entre el factor vigente de la vista, así que la comparación vale con
`xMonEEFF` en USD o en MXN.

```bash
python3 cargar_v3.py          # CtaMens y celdas del libro de Cesión (en cesion/)
python3 datos05.py            # 2027 por miembro en USD y MXN; se cruza contra Val_* y ER
python3 llenar05.py           # escribe 05_FCST_2027.xlsx editando el XML (solo valores)
python3 construir05.py        # agrega las hojas Val05_* al libro de Cesión
```

## Cómo se escribe el `.xlsb`

LibreOffice no abre este libro y `pyxlsb` es solo lectura. `xlsbw.py` genera los
registros BIFF12 de las hojas (celdas, fórmulas `rgce`, anchos, paneles),
`estilos.py` anexa fuentes, rellenos, bordes y `cellXfs` a `styles.bin` copiando el
formato de los registros existentes, y `empaquetar2.py` copia el ZIP original y solo
reemplaza o añade las partes que cambian (`zip -u`), de modo que los 229 componentes
originales conservan sus bytes comprimidos.

## Módulos

| Archivo | Para qué |
|---|---|
| `biff.py`, `fmla.py`, `dump.py` | Lector BIFF12, decodificador de fórmulas (tabla de funciones verificada contra el libro), volcado de celdas |
| `load_ctamens2.py` | Lee `CtaMens` con todas las columnas que usan las vistas |
| `motor.py` | Evalúa los 20 renglones por miembro y valida contra las vistas vivas |
| `xlsbw.py`, `estilos.py`, `empaquetar2.py` | Escritura del `.xlsb` |
| `construir2.py` | Arma las siete hojas |
| `verificar2.py` | Auditoría: integridad, estilos, orden de celdas y reevaluación de todas las fórmulas |
| `reparar.py`, `evaluador.py`, `verificar3.py` | Reparación del libro editado en Excel y su auditoría |
| `render.py`, `render2.py` | Vista previa HTML de las hojas con los estilos reales del libro |
| `load_int.py`, `flujo.py` | Carga completa de `CtaMens` y lectura parcial de hojas grandes |
| `cat_reparto.py`, `aplicar_cat.py`, `evaluador2.py`, `verificar4.py` | Reparto de CAT y Gastos en `CtaMens`, hoja `Val_CAT` y su auditoría |
| `cargar_v3.py`, `datos05.py`, `llenar05.py`, `construir05.py` | Llenado de `05_FCST_2027.xlsx` desde las vistas y hojas `Val05_*` |
| `analisis.py`, `comparar.py`, `construir.py`, `verificar.py`, `empaquetar.py`, `load_ctamens.py` | Versión anterior (ValDim vs recálculo), se conserva por referencia |

## Cómo correrlo

```bash
cp <ruta>/FCST_2027_Cesion.xlsb FCST.xlsb
python3 load_ctamens2.py     # ~35 s
python3 motor.py             # valida contra las vistas y guarda motor.pkl
python3 construir2.py        # escribe FCST_2027_Cesion.xlsb
python3 verificar2.py        # audita el resultado
```

`construir2.py` necesita además `valdim.pkl` (volcado de `ValDim` con `dump.py`) y
`celdas_ref.pkl` (valores de `ER`, `2_Reservas`, `Parámetros`, `Inicio`, `CAT`,
`Gastos` y las vistas, generado con `dump.py`).
