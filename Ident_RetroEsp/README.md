# Ident RetroEsp — versión con nombres

Versión actualizada de las consultas de Identificación RetroEsp que, además del
archivo de siempre (con claves), genera un archivo gemelo con el sufijo
`_nombres` en el que las claves ya vienen escritas como texto.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `Ident_RetroEsp__Prop_aod_nombres.py` | Consulta de retrocesión **proporcional**. Genera `Ident_RetroEsp_Propv2.xlsm` y `Ident_RetroEsp_Propv2_nombres.xlsm`. |
| `Ident_RetroEsp__Fac_aod_nombres.py` | Consulta de retrocesión **facultativa**. Genera `Ident_RetroEsp_Facv2.xlsm` y `Ident_RetroEsp_Facv2_nombres.xlsm`. |
| `catalogo_nombres.py` | Módulo con la traducción clave → nombre. **Debe estar en la misma carpeta.** |
| `resumen_sudamerica.py` | Módulo que arma la pestaña `América del Sur`. **Debe estar en la misma carpeta.** |
| `Convertir_Ident_RetroEsp_a_nombres.py` | Convierte un archivo ya generado a su versión `_nombres` **sin volver a correr la consulta a SIREC**. |

## Qué se traduce

Se toma la hoja `Catálogo` del archivo `Catálogo consulta ident_retroesp.xlsx`
(la misma que ya se pega como pestaña en el resultado) y se sustituyen, en la
misma columna y sin cambiar el layout:

| Columna del Excel | Catálogo |
|---|---|
| Corredor (cedido y tomado) | No. Corredor → Nombre Corredor |
| Ramos Cubiertos (cedido y tomado) | ID Ramo → Ramo |
| Subramos Excluidos / Subramos Cubiertos | ID Subramo → Subramo |
| Territorios Cubiertos / Territorio llave | ID Territorios → Territorio |
| Paises Excluidos / Paises Cubiertos | ID País → País |
| Negocio MGA (Prop) | 0 → No, 1 → Sí |

Las listas se traducen completas: `60, 71` → `General, Terremoto y Erupción Volcánica`.

Hay claves de ramo que solo están dadas de alta en el catálogo de subramos
(30 `Accidentes Personales General`, 70 `Catastróficos en General`), así que el
catálogo de ramos se completa con el de subramos cuando la clave no existe
(`CATALOGO_RESPALDO` en `catalogo_nombres.py`). Al terminar la corrida se
imprimen cuáles se resolvieron por esa vía, para poder darlas de alta en su
propio catálogo.

Lo que **no** se toca: No. Contrato, Ident Contrato, No. Oferta, Endoso, Año de
Vigencia, importes, porcentajes y validaciones. El nombre del cedente ya venía
resuelto desde antes (columna `Cedente`), y `No. Cedente` se deja como número
para poder amarrar contra SIREC.

Sin catálogo se quedan `DescComision`, `Tipo Contrato` y `Monedas del Movimiento`;
si se agregan al archivo de catálogo, basta con darlos de alta en
`CATALOGOS_COLUMNAS` y en `COLUMNAS_A_CATALOGO` dentro de `catalogo_nombres.py`.

## Claves que no están en el catálogo

No se pierde información: una clave que no aparece en el catálogo se escribe
como `70 (sin catálogo)` y al terminar la corrida se imprime el listado
completo para poder darlas de alta. En la corrida contra los archivos actuales
salieron:

- **Territorio**: 6
- **País**: 0, 158, 164, 168, 169, 170, 171
- **Corredor**: 462, 463, 468, 470, 474, 475, 476, 477, 479, 483, 490, 495, 496, 498

Si se prefiere ver la clave pelada, en `catalogo_nombres.py` se cambia
`FORMATO_CLAVE_DESCONOCIDA = "{clave}"`.

## Cómo se usa

1. Copiar los cuatro archivos `.py` en la carpeta de OneDrive
   `...\Consulta Identificación RetroEsp` (junto al catálogo).
2. Correr `Ident_RetroEsp__Prop_aod_nombres.py` y `Ident_RetroEsp__Fac_aod_nombres.py`
   igual que siempre. Cada uno deja los dos archivos: el de claves y el `_nombres`.
3. Si solo se quiere la versión con nombres de un archivo que ya existe:
   `python Convertir_Ident_RetroEsp_a_nombres.py` (o pasándole la ruta del archivo).

Requisitos: los mismos de siempre (`pandas`, `openpyxl`, `pyodbc`); el convertidor
no necesita `pyodbc` ni conexión a la base.

## Pestaña `América del Sur`

El archivo `_nombres` trae una tercera pestaña que es **una copia exacta de la
hoja de datos** —mismos encabezados, bandas CEDIDO/TOMADO/MOVIMIENTOS, colores,
anchos, formatos y paneles inmovilizados— con el **filtro de Excel ya aplicado**
en la columna `Paises Cubiertos` sobre los países de América del Sur.

Es un filtro normal de Excel: los renglones que no son de la región quedan
ocultos, pero siguen ahí. Desde la flechita de la columna se puede quitar el
filtro, agregar países o combinarlo con otras columnas (por ejemplo
`Tipo Reaseguro` = FACULTATIVO DAÑOS), sin perder nada.

La lista de países está en `PAISES_SUDAMERICA`, dentro de `resumen_sudamerica.py`:
Argentina, Bolivia, Brasil, Chile, Colombia, Ecuador (y Quito, que está dado de
alta como país aparte), Guyana, Guyana Francesa, Paraguay, Perú, Surinam,
Uruguay y Venezuela. Un renglón entra si **alguno** de sus países cubiertos es
de la región.

Para desactivar la pestaña: `generar_libro(..., hoja_sudamerica=False)` en los
scripts, o `AGREGAR_RESUMEN_SUDAMERICA = False` en el convertidor.

### Copia completa o compacta

Como la hoja se duplica, el archivo crece. La constante `SOLO_RENGLONES_FILTRADOS`
(en cada script y en el convertidor) decide cómo:

| Valor | Qué hace | Cuándo conviene |
|---|---|---|
| `False` | Copia la hoja completa y oculta los renglones de fuera de la región. El filtro se puede quitar o ampliar desde Excel. | Facultativo (~1,300 renglones). |
| `True` | Copia únicamente los renglones de la región. Se ve igual, pero en esa hoja ya no se puede quitar el filtro para ver otras regiones — la hoja original sigue completa. | Proporcional (~30,000 renglones): baja el archivo de 34 MB a menos de 1 MB. |

Viene en `False` en el script de facultativo y en `True` en el de proporcional.

### Resumen calculado (opcional, no se genera por omisión)

`resumen_sudamerica.py` conserva `construir_resumen()` y `agregar_hoja_resumen()`,
que arman una hoja ejecutiva con asegurado, país, cedente, corredor, prima al
100%, % de retrocesión y fee de Patria (la prima al 100% del facultativo y del
proporcional es estimada: prima contable ÷ % de participación de Patria). No se
usa en el flujo actual; queda disponible por si se vuelve a pedir.
