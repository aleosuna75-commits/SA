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
| `render.py` | Vista previa HTML de las hojas con los estilos reales del libro |
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
