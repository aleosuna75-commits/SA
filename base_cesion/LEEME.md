# Base de % de cesión desde los logouts del PPTO

`base_cesion.py` lee todos los logouts de una carpeta (hoja `ParamPPTO`) y
genera un Excel con el % de cesión de cada documento: **LN, TR, cedente,
corredor, contrato, tipo de venta y % de cesión 2027–2031**, con los nombres
de LN, TR, cedente y corredor.

## Cómo correrlo en VSCode

1. Descomprime la carpeta de logouts en **Documentos**, por ejemplo
   `C:\Users\<usuario>\Documents\CIFRAS AJUSTADAS`. Si al descomprimir queda
   una carpeta dentro de otra, o si está una o dos carpetas más abajo
   (`Documentos\PPTO 2027\CIFRAS AJUSTADAS`), también la encuentra.
2. Abre `base_cesion.py` en VSCode y da clic en **Run Python File** (▷, arriba
   a la derecha).
3. La primera vez instala solo `openpyxl` y `pandas` si no los tienes (o si
   están muy viejos) y se reinicia solo.
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
| `Base_Cesion` | Una fila por documento, con todas las columnas de la base (lista abajo). |
| `Cesion_Anual` | La misma información en una fila por documento y año, lista para tablas dinámicas. |
| `Resumen` | Por LN y TR (solo versiones vigentes): documentos, documentos con % de cesión y mín./promedio/máx. del % de cesión 2027. |
| `Validaciones` | Inconsistencias a revisar con la LN (ver abajo). |
| `Notas` | De qué celda del logout sale cada columna. |

Columnas de `Base_Cesion`:

- **Llaves y nombres:** LN y nombre, TR y descripción (Proporcional / No
  Proporcional / Facultativo), Cedente con nombre, país y grupo, Corredor y
  nombre.
- **Datos del documento:** Of. Rep., Contrato, Tipo Venta, % Renov., MGA.
- **Tipo de retrocesión:** % Tradicional, % Retro Espec., % Fronting y
  % Retención.
- **Cesión:** `Cesión capturada`, `Años con cesión`, **% Cesión 2027–2031** y
  % Com. Cedido 2027–2031.
- **Control:** GS, versión del archivo, `Versión vigente` y observaciones.

Los nombres salen del catálogo de la hoja `Valores` del PptoTécnico. Excel lo
guarda dentro de cada logout, así que no hace falta tener abierto el archivo
del presupuesto.

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

El % de cesión es el valor que capturó la LN. No está multiplicado por el
% de Retro Espec. + Fronting.

### Ojo con 2031

En los logouts, la columna B de "Porcentaje de Cesión" siempre viene vacía y
el 2027 cae en la columna C. Sin embargo, el recuadro con formato del logout es
de 5 celdas (B…F), y en esta LN los dos documentos que capturaron varios años
llegan solo hasta 2030 (columna F). Ningún logout trae dato en G (2031).

Puede ser que la macro del logout recorte el último año. Para confirmarlo,
captura la cesión 2027–2031 en un PRESUPUESTO (celdas M34:Q34), genera su
logout y revisa en qué celdas cae. Si cambia la alineación, basta con ajustar
`COL_PRIMER_ANIO` al inicio del script.

Mientras ningún logout traiga 2031, el script lo avisa en consola y en
`Validaciones`.

## Validaciones que revisa

- **Error**:
  - un archivo que no se puede abrir o que tiene formato `.xls`/`.xlsb`;
  - etiquetas que no aparecen;
  - un % capturado como texto que no es número;
  - fórmulas guardadas sin valor;
  - un dato en la columna B de los años;
  - un nombre de archivo que no coincide con el contenido (LN, TR, corredor,
    cedente, contrato).
- **Revisar**:
  - un % negativo o mayor a 100% (por ejemplo, 80 en lugar de 80%);
  - un reparto por tipo de retrocesión vacío o que no suma 100%;
  - Retro Espec. o Fronting sin % de cesión, o con cesión en 0%;
  - % de cesión con el documento 100% Tradicional;
  - comisión del cedido sin % de cesión;
  - venta combinada sin % Renov.;
  - un documento repetido en varias versiones;
  - un valor fuera de las columnas esperadas;
  - que ningún logout traiga 2031.
- **Info**:
  - % de cesión que no viene en todos los años;
  - años distintos entre cesión y comisión;
  - % Renov. en una venta no combinada;
  - un código que no está en el catálogo.

## Ajustes al inicio del script

| Variable | Para qué |
|---|---|
| `CARPETA_LOGOUTS` | Ruta fija de la carpeta de logouts. |
| `CARPETA_SALIDA` | Dónde guardar el Excel. |
| `ARRASTRAR_ULTIMO_ANIO` | `True` hace que, si la LN capturó solo 2027, los años siguientes tomen ese mismo %. Por omisión (`False`) los deja vacíos. |
| `PRIMER_ANIO`, `COL_PRIMER_ANIO` | Primer año presupuestado y la columna donde cae (C). |
| `ABRIR_AL_TERMINAR` | Abrir el Excel al final. |

## Si la instalación automática falla

Normalmente pasa por el proxy de la oficina. El script muestra el comando para
instalar a mano desde la terminal de VSCode (con el mismo Python que tienes
seleccionado), algo como:

```
python -m pip install --upgrade "pandas>=1.1" "openpyxl>=3.0"
```
