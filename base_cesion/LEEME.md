# Base de % de cesión desde los logouts del PPTO

`base_cesion.py` lee los logouts de una LN (hoja `ParamPPTO`) y genera un Excel
con el % de cesión de cada documento: **LN, nivel (cedente / contrato /
binder), TR, cedente, corredor, contrato, binder y % de cesión
2027–2031**, con los nombres de LN, TR, cedente y corredor.

## Cómo correrlo

1. Deja cada LN en su carpeta: `LN4001`, `LN4002`, …, `LN4006`, … Pueden
   estar en Documentos, Escritorio o Descargas (o hasta tres carpetas más
   abajo, por ejemplo `Documentos\Presupuesto 2027\LN4006`) o junto al
   script.
2. Abre `base_cesion.py` en VSCode y cambia **solo esta línea** al inicio:

   ```python
   LN = "LN4006"      # o "LN4001", "LN4003", ... o "TODAS"
   ```

3. Da clic en **Run Python File** (▷).
4. Al terminar abre `Base_Cesion_LN4006_<fecha>.xlsx`, que se guarda junto a
   las carpetas de las LN.

Con `LN = "TODAS"` procesa todas las carpetas LN que encuentre y genera una
sola base, `Base_Cesion_TODAS_<fecha>.xlsx`, con la columna `Carpeta LN`.

Detalles:

- **Nombres de los archivos:** no importan. Un archivo es logout si tiene la
  hoja `ParamPPTO`, así que sirven tanto `Logout_LN04003_r1_...xlsx` como
  `11 CCUW Carga.xlsx`.
- **Si la carpeta quedó dentro de otra** al descomprimir
  (`LN4006\LN4006\...`), también la encuentra.
- **Si hay dos carpetas de la misma LN** (por ejemplo, `LN4006` y
  `LN4006 - copia`), usa primero la de `CARPETA_LNS` o la que está junto al
  script. Si empatan, usa la de archivos más recientes, y siempre avisa.
- **Si eliges a mano una carpeta que contiene varias LN,** la separa en sus
  carpetas LN.
- **`LN = "LN4008"` con sublíneas** (`LN4008-Agro`, `LN4008-Vida`) las
  procesa todas.
- **Para moverlo:** basta con copiar el script junto a las carpetas LN, o
  escribir en `CARPETA_LNS` la carpeta que las contiene.
- **La primera vez** instala solo `openpyxl` y `pandas` si faltan.

## Cardinalidad: nivel de cada documento

El script clasifica cada documento según lo que trae el logout:

| Nivel | Cuándo |
|---|---|
| **Binder** | La casilla MGA es Verdadero, o trae Binder general / Binder segmentado. |
| **Contrato** | No hay MGA, pero sí contrato. |
| **Cedente** | Sin contrato ni MGA. |

La hoja `Cardinalidad_LN` dice cuántos documentos hay de cada nivel en cada LN
y cuál es la cardinalidad de la línea (el nivel más granular que aparece). Si
hay más de un nivel, lo marca como "mixta".

La llave de cada documento incluye nivel, cedente, corredor, contrato, los
dos nombres de binder y el tipo de venta. Así, los binders de un mismo cedente
(por ejemplo, los 10 de CCUW en LN4006) no se toman como documentos repetidos.

Aplicando esta regla, **LN4003 sale "Contrato (mixta)"**: 99 de sus 133
logouts traen contrato (14 de ellos con el 99, todos TR 3 Facultativo) y 34
no. Además, hay cedentes con dos documentos que solo se distinguen por el
contrato (954, 1143 y 1293).

## Qué trae el Excel

| Hoja | Contenido |
|---|---|
| `Base_Cesion` | Una fila por documento. |
| `Cesion_Anual` | Una fila por documento y año, lista para tablas dinámicas. |
| `Resumen` | Por LN, nivel y TR: documentos, documentos con % de cesión y mín./promedio/máx. del % de cesión 2027. |
| `Cardinalidad_LN` | Por LN: documentos de cada nivel, cardinalidad y columna del primer año. |
| `Validaciones` | Inconsistencias a revisar con la LN. |
| `Notas` | De qué celda sale cada columna y qué carpetas se leyeron. |

Columnas de `Base_Cesion`:

- **Llaves:**
  - Archivo, Carpeta LN y Nivel;
  - LN y su nombre;
  - TR y su descripción;
  - Cedente con nombre, país y grupo;
  - Corredor y su nombre;
  - Contrato, `Es MGA`, `Binder general` y `Binder segmentado`.
- **Del documento:** Of. Rep., Tipo Venta, % Renov.
- **Tipo de retrocesión:** % Tradicional, % Retro Espec., % Fronting,
  % Retención.
- **Cesión:** `Cesión capturada`, `Años con cesión`, **% Cesión 2027–2031**,
  % Com. Cedido 2027–2031.
- **Control:** GS, `Col. 1er año`, versión, `Versión vigente`, Observaciones.

## De dónde sale cada dato del logout

Las filas se ubican por su etiqueta en la columna A.

| Columna de la base | Renglón del logout | Columnas |
|---|---|---|
| LN / TR / Cedente | Línea de Negocio / Tipo Reas. / Compañía | B |
| Corredor | Corredor (la primera vez que aparece) | B |
| Contrato | Contrato | B |
| Es MGA / Binder general / Binder segmentado / GS | MGA | B / C / E / F |
| Tipo Venta / % Renov. | Tipo Venta | B / C |
| % Tradicional, Retro Espec., Fronting, Retención | Porcentaje | B, C, D, E |
| % Cesión 2027 … 2031 | Porcentaje de Cesión | 5 columnas desde `Col. 1er año` |
| % Com. Cedido 2027 … 2031 | % Comisiones del Cedido | 5 columnas desde `Col. 1er año` |

`Binder general` (col. C) es el binder elegido en el PRESUPUESTO (celda E18,
nombre `yBind`; por ejemplo, "Cargo Corp Marine" agrupa 8 binders de CCUW).
`Binder segmentado` (col. E) es el binder específico, por ejemplo
"Cargo Corp Hull". El nombre del archivo suele ser una abreviatura de él.

Los nombres salen del catálogo del PptoTécnico que Excel guarda dentro de cada
logout (rangos `xAFUN`, `xTIPOREA`, `xCEDENTES` y `xCORREDORES`).

### Columna del primer año (2027)

El recuadro de la plantilla es de 5 celdas, **B…F = 2027…2031**, y así vienen,
por ejemplo, los logouts de LN4006.

Los de LN4003 (Fianzas) traen el 2027 en la columna C, recorridos una
columna, y nunca traen 2031. Por eso el script lo detecta para cada LN, según
la LN del propio logout (así, un logout de otra LN que se coló en la carpeta
no cambia a los demás):

- **B:** si la mayoría de los logouts de la LN trae dato en la columna B.
- **C:** si la mayoría empieza en C. En ese caso lo avisa en consola y en
  `Validaciones`, porque probablemente esa herramienta no exporta 2031.
- **Mezcla:** si hay logouts de los dos tipos, avisa "Columna del primer año
  mixta" y marca los de la minoría.

La columna `Col. 1er año` dice qué se usó. Si hiciera falta, se puede fijar
con `COLUMNA_PRIMER_ANIO = "B"` o `"C"`.

## Validaciones que revisa

- **Error:**
  - archivo que no se puede abrir;
  - etiquetas que no aparecen;
  - % capturado como texto que no es número;
  - fórmulas guardadas sin valor;
  - nombre `Logout_...` que no coincide con el contenido.
- **Revisar:**
  - % negativo o mayor a 100%;
  - reparto por tipo de retrocesión vacío o que no suma 100%;
  - Retro Espec. o Fronting sin % de cesión, o con cesión en 0%;
  - % de cesión con el documento 100% Tradicional;
  - comisión sin % de cesión;
  - cesión que no empieza en 2027;
  - binder con la casilla MGA en Falso;
  - casilla MGA sin nombre de binder;
  - columna del primer año mixta;
  - logout de otra LN dentro de la carpeta;
  - documento repetido;
  - valor fuera de las columnas esperadas;
  - años recorridos una columna;
  - ningún logout trae 2031.
- **Info:**
  - cesión que no viene en todos los años;
  - cesión sin % de comisión, o años distintos entre cesión y comisión;
  - binder con un solo nombre (general o segmentado);
  - TR, cedente o corredor vacíos (distintos de 0);
  - archivos que no son logout o están en `.xlsb`/`.xls`;
  - código sin nombre en el catálogo.

## Ajustes al inicio del script

| Variable | Para qué |
|---|---|
| `LN` | La LN a procesar (`"LN4006"`) o `"TODAS"`. |
| `CARPETA_LNS` | Carpeta que contiene las carpetas LN, si no están en Documentos ni junto al script. |
| `CARPETA_LOGOUTS` | Ruta directa a una carpeta de logouts (ignora `LN`). |
| `CARPETA_SALIDA` | Dónde guardar el Excel. |
| `COLUMNA_PRIMER_ANIO` | `"AUTO"` (por omisión, lo que haga la mayoría), `"B"` o `"C"`. |
| `ARRASTRAR_ULTIMO_ANIO` | `True` hace que, si un documento trae solo 2027, los años siguientes tomen ese %. |
| `ABRIR_AL_TERMINAR` | Abrir el Excel al final. |

Desde la terminal también se puede:
`python base_cesion.py --ln LN4006` o `python base_cesion.py "C:\ruta\a\una\carpeta"`.

## Si la instalación automática falla

Normalmente pasa por el proxy de la oficina. El script muestra el comando para
instalar a mano desde la terminal de VSCode, algo como:

```
python -m pip install --upgrade "pandas>=1.1" "openpyxl>=3.0"
```
