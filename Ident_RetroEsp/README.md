# Ident RetroEsp — versión con nombres

Versión actualizada de las consultas de Identificación RetroEsp que, además del
archivo de siempre (con claves), genera un archivo gemelo con el sufijo
`_nombres` en el que las claves ya vienen escritas como texto.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `Ident_RetroEsp__Prop_aod_nombres.py` | Consulta de retrocesión **proporcional**. Genera `Ident_RetroEsp_Propv2.xlsm` y `Ident_RetroEsp_Propv2_nombres.xlsm`. |
| `Ident_RetroEsp__Fac_aod_nombres.py` | Consulta de retrocesión **facultativa**. Genera `Ident_RetroEsp_Facv2.xlsm` y `Ident_RetroEsp_Facv2_nombres.xlsm`. |
| `catalogo_nombres.py` | Módulo con la traducción clave → nombre. Lo usan los tres scripts. **Debe estar en la misma carpeta.** |
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

- **Ramo**: 30, 70
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
