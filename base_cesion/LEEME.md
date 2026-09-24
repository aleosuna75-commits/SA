# Base de % de cesión desde los logouts del PPTO

`base_cesion.py` lee todos los logouts de una carpeta (hoja `ParamPPTO`) y
genera un Excel con el % de cesión de cada documento: **LN, TR, cedente,
corredor, contrato, tipo de venta y % de cesión 2027–2031**.

## Cómo correrlo en VSCode

1. Descomprime la carpeta de logouts en **Documentos**, por ejemplo
   `C:\Users\<usuario>\Documents\CIFRAS AJUSTADAS`.
2. Abre `base_cesion.py` en VSCode y da clic en **Run Python File** (▷, arriba
   a la derecha).
3. La primera vez instala solo `openpyxl` y `pandas` si no los tienes.
4. Al terminar abre el Excel `Base_Cesion_<LN>_<fecha>.xlsx`, que queda
   guardado junto a la carpeta de logouts (en Documentos).

Si la carpeta tiene otro nombre o está en otro lado, hay tres opciones:

- Si no la encuentra, el script abre una ventana para elegirla.
- Escribe la ruta en `CARPETA_LOGOUTS` al inicio del script.
- Pásala desde la terminal:
  `python base_cesion.py "C:\Users\<usuario>\Documents\OTRA CARPETA" --salida "C:\Users\<usuario>\Desktop"`

La búsqueda incluye subcarpetas, así que puedes poner los logouts de varias LN
en carpetas separadas dentro de una misma carpeta y generar una sola base.

## Qué trae el Excel

| Hoja | Contenido |
|---|---|
| `Base_Cesion` | Una fila por documento: LN, TR, Cedente, Corredor, Of. Rep., Contrato, Tipo Venta, % Renov., MGA, reparto por tipo de retrocesión (Tradicional / Retro Espec. / Fronting / Retención), `Cesión capturada`, **% Cesión 2027–2031**, % Com. Cedido 2027–2031, GS, versión y observaciones. |
| `Cesion_Anual` | La misma información en una fila por documento y año, lista para tablas dinámicas. |
| `Resumen` | Documentos, documentos con % de cesión y mín./promedio/máx. del % de cesión 2027, por LN y TR. |
| `Validaciones` | Inconsistencias a revisar con la LN (ver abajo). |
| `Notas` | De qué celda del logout sale cada columna. |

## De dónde sale cada dato del logout

Las filas se ubican por su etiqueta en la columna A, así que el script sigue
funcionando aunque el logout agregue o mueva renglones.

| Columna de la base | Renglón del logout (columna A) | Columnas |
|---|---|---|
| LN | Línea de Negocio | B |
| TR | Tipo Reas. | B |
| Cedente | Compañía | B |
| Corredor | Corredor (la primera vez que aparece) | B |
| Contrato | Contrato | B |
| Tipo Venta / % Renov. | Tipo Venta | B / C |
| % Tradicional, % Retro Espec., % Fronting, % Retención | Porcentaje | B, C, D, E |
| % Cesión 2027 … 2031 | Porcentaje de Cesión | C … G |
| % Com. Cedido 2027 … 2031 | % Comisiones del Cedido | C … G |
| GS | MGA | F |

En los logouts la columna B de "Porcentaje de Cesión" viene vacía y el 2027
cae en la columna C. Si algún archivo trae algo fuera de C…G, se reporta en
`Validaciones`.

## Validaciones que revisa

- **Error**: archivo que no se puede abrir, etiquetas que no aparecen, un %
  capturado como texto que no es número, o un nombre de archivo que no
  coincide con el contenido (LN, TR, corredor, cedente, contrato).
- **Revisar**:
  - un % fuera de 0–100% (por ejemplo, 80 en lugar de 80%);
  - un reparto por tipo de retrocesión que no suma 100%;
  - Retro Espec. o Fronting sin % de cesión;
  - % de cesión con el documento 100% Tradicional;
  - venta combinada sin % Renov.;
  - un documento repetido en varias versiones.
- **Info**: % de cesión capturado solo en algunos años.

## Ajustes al inicio del script

| Variable | Para qué |
|---|---|
| `CARPETA_LOGOUTS` | Ruta fija de la carpeta de logouts. |
| `CARPETA_SALIDA` | Dónde guardar el Excel. |
| `ARRASTRAR_ULTIMO_ANIO` | `True` hace que, si la LN capturó solo 2027, los años siguientes tomen ese mismo %. Por omisión (`False`) los deja vacíos. |
| `PRIMER_ANIO`, `COL_PRIMER_ANIO` | Primer año presupuestado y la columna donde cae (C). |
| `ABRIR_AL_TERMINAR` | Abrir el Excel al final. |

## Si la instalación automática falla

Normalmente pasa por el proxy de la oficina. Instala a mano desde la terminal
de VSCode (con el mismo Python que tienes seleccionado):

```
python -m pip install openpyxl pandas
```
