# Validación de las vistas por dimensión de `FCST_2027_Cesion.xlsb`

Herramienta para auditar la hoja `ValDim` del libro del presupuesto y devolver el
resultado **dentro del mismo libro**, en hojas nuevas armadas con fórmulas que
apuntan a las celdas de origen.

## Qué encontró

La hoja `ValDim` compara, para cada dimensión, la suma de sus miembros contra el
global del presupuesto. Hoy muestra descuadres en las cuatro vistas. Al recalcular
esas mismas sumas directo de `CtaMens` con la fórmula del propio libro, **las cuatro
dimensiones cuadran contra el global en 0.00**:

| Dimensión | Descuadre que muestra ValDim (prima, dic) | Descuadre real |
|---|---:|---:|
| Ramo | 165,162,122.33 | 0.00 |
| Línea de negocio | 1,329,234.26 | 0.00 |
| Región | −153,749,220.68 | 0.00 |
| Tipo de reaseguro | −767,645,968.60 | 0.00 |

El descuadre no está en los datos. Está en cómo se llena `ValDim`:

- De las 31 filas de miembro, **solo la primera de cada vista tiene fórmula**
  (`ValDim!O10 = ER_ram!P$9`, y su equivalente en LN, Región y Tipo Rea).
  Las 27 restantes son **valores pegados**: 552 celdas constantes contra 96 con fórmula.
- Esa única fila viva muestra el miembro que tenga seleccionado el combo de la vista
  (`ER_ram!A6`, `ER_ln!A6`, `ER_reg!A6`, `ER_tre!A6`), no el que dice su rótulo.
  Hoy Región está parada en `R06` bajo el rótulo `R01`, y Tipo Rea en `3` bajo el rótulo `1`.
- Dos etiquetas de `ValDim` no empatan con el detalle: `Crédito` (con acento) contra
  `Credito` (sin acento) en `CtaMens`, y `LN04008` contra `LN04008-Agro`.
  `GMM`, `Crédito`, `LN04008` y `LN04009` no tienen ni un renglón con ese nombre exacto.

## Cómo se arman las cifras del libro

```
ValDim!O3   = ER!Q$5      = -SUMIFS(CtaMens!Q; CtaMens!B;61; CtaMens!A;mes)   (global prima)
ValDim!O4   = ER!Q$17     =  SUMIFS(CtaMens!Q; CtaMens!B;53; CtaMens!A;mes)   (global comisiones)
ValDim!O10  = ER_ram!P$9  = -SUMIFS(CtaMens!Q; B;61; A;mes; R;ER_ram!A6)      (miembro de Ramo)
ValDim!AC10 = ER_ln!P$9   -> filtra por CtaMens!C     ValDim!AQ10 = ER_reg!P$9 -> CtaMens!E
ValDim!BE10 = ER_tre!P$9  -> filtra por CtaMens!L
```

Columnas de `CtaMens` (encabezado real en la fila 3, datos de la fila 4 a la 201,234):
`A` mes, `B` familia de cuenta (61 prima / 53 comisiones / 54 siniestros), `C` línea de
negocio, `E` región, `L` tipo de reaseguro, `Q` monto, `R` ramo.

## Hojas que se agregan al libro

| Hoja | Contenido |
|---|---|
| `Val_Resumen` | Veredicto por dimensión y concepto: suma según ValDim vs suma recalculada, contra el global |
| `Val_Ramo`, `Val_LN`, `Val_Region`, `Val_TRea` | Miembro por miembro y mes por mes, en tres bloques: lo que muestra ValDim (`=ValDim!...`), el recálculo (`SUMIFS` sobre `CtaMens`) y la diferencia |
| `Val_Origen` | Rastreo de cada cifra: celda, fórmula tal cual está en el libro, valor vivo, mapa de columnas de `CtaMens`, censo de celdas vivas vs pegadas y en qué miembro está parado cada combo |

Todo va en fórmulas: 3,259 en total, ninguna cifra capturada a mano.

## Por qué se escribe el `.xlsb` a mano

LibreOffice no abre este libro (`source file could not be loaded`) y `pyxlsb` es solo
lectura, así que no hay forma de convertirlo ni de reescribirlo con una librería. Los
módulos `xlsbw.py` y `empaquetar.py` generan los registros BIFF12 de las hojas nuevas y
las insertan en el ZIP del libro original. Las 229 partes originales se copian
intactas byte a byte; solo cambian `workbook.bin` (se agregan las hojas y se amplía la
tabla de referencias externas), los rels, `[Content_Types].xml` y `sharedStrings.bin`.
Se elimina `calcChain.bin` para que Excel lo reconstruya, que es lo que se acostumbra
al agregar hojas fuera de Excel.

## Módulos

| Archivo | Para qué |
|---|---|
| `biff.py` | Lector de registros BIFF12 y mapa de hojas |
| `fmla.py` | Decodifica `rgce` a fórmula legible (tabla de funciones verificada contra el propio libro) |
| `dump.py` | Recorre una hoja y devuelve celda, valor y fórmula |
| `xlsbw.py` | Escritor: registros de celda, codificación de fórmulas y armado de la hoja |
| `empaquetar.py` | Inserta las hojas en el ZIP del libro |
| `load_ctamens.py` | Lee `CtaMens` respetando las columnas de Excel |
| `analisis.py` | Calcula las 12 columnas mensuales de cada miembro |
| `comparar.py` | Reporte en pantalla de ValDim contra el recálculo |
| `construir.py` | Arma las seis hojas y genera el libro |
| `verificar.py` | Auditoría del archivo generado |

## Cómo correrlo

```bash
cp <ruta>/FCST_2027_Cesion.xlsb FCST.xlsb
python3 load_ctamens.py     # cachea CtaMens (~35 s)
python3 analisis.py         # calcula y guarda analisis.pkl
python3 construir.py        # escribe FCST_2027_Cesion.xlsb con las seis hojas
python3 verificar.py        # audita el resultado
```

`construir.py` necesita `valdim.pkl` (volcado de `ValDim`), que se genera con `dump.py`
sobre la hoja `ValDim`.

## Qué verifica `verificar.py`

1. Las 229 partes originales quedan idénticas.
2. Ninguna de las 3,259 fórmulas quedó mal codificada.
3. Los 792 `SUMIFS` se vuelven a leer del archivo, se evalúan contra `CtaMens` y se
   comparan con el valor guardado — desviación máxima 0.000000.
4. Las 744 referencias `=ValDim!...` apuntan a la celda y al valor correctos.
5. Las 1,464 sumas y restas internas son consistentes.
6. El libro completo se abre y se recorre con `pyxlsb`.
