# Actualización del Catálogo Centralizado (SIREC y SAP)

Script en Python para VS Code que toma los movimientos pendientes (`#N/D`) de
`Consulta_IDEspeciales_v2_XXXX.xlsm` y los inserta en la hoja
`ID_Esp<AAAA>=TablaExtendida` de `CentralizadoCatálogos_SIRECySAP.xlsx`,
**conservando exactamente el formato actual** del archivo.

## Instalación

```bash
pip install openpyxl
```

## Uso

Pon los dos archivos en esta misma carpeta (o ajusta `RUTA_CONSULTA` /
`RUTA_CENTRALIZADO` en el bloque **CONFIGURACIÓN** del script) y ejecuta:

```bash
python actualizar_catalogo_centralizado.py
```

Genera `CentralizadoCatálogos_SIRECySAP_actualizado.xlsx` junto al original
(el original nunca se toca).

Opciones:

```bash
# rutas explícitas
python actualizar_catalogo_centralizado.py \
    --consulta "C:/.../Consulta_IDEspeciales_v2_0826.xlsm" \
    --centralizado "C:/.../CentralizadoCatálogos_SIRECySAP.xlsx" \
    --salida "C:/.../Centralizado_202608.xlsx"

# ver el reporte sin escribir nada
python actualizar_catalogo_centralizado.py --simular
```

## Qué hace, paso a paso

| # | Paso | Detalle |
|---|------|---------|
| 1 | Detecta pendientes | Recalcula la columna *validación* de `ValidacionProp` y `ValidacionNoProp`: llaves que no están ni en **CENTRALIZADO** ni en **ANTERIOR**. No depende del valor en caché del `#N/D`. |
| 2 | Determina el mes | `AAAAMM` de la **Fecha de Captura** (`aHTP_FecCaptura` / `aHTNP_FecCaptura`) en `Prop`/`Prop_02`/`NoProp`/`NoProp_02`. Ese valor va a la columna **ENTRA**. |
| 3 | Busca el registro parecido | Jerarquía: `MAPEO_MANUAL` → `"ID anterior ..."` de Observaciones → mismo Corredor+Compañía+Contrato → misma Compañía+Contrato → mismo Corredor+Compañía → misma Compañía. Cada renglón se reporta con su nivel de confianza. |
| 4 | Calcula dónde va | Debajo del último movimiento de la **misma cedente dentro del mes**; si no hay, al final del bloque de ese mes; si el mes aún no existe, después del bloque del mes anterior más cercano. |
| 5 | Inserta | Agrega la fila y recorre el resto hacia abajo. Copia el formato del renglón de arriba, hereda de la plantilla los datos que la Consulta no trae (Identificación, DR, LN, SUBLN, MGA, País/Territorio, Binders, Cedente, Clasificación, MGA 2) y pone todas las **Ofertas en cero**. |

## Cómo se conserva el formato

La salida se produce editando el XML del `.xlsx` original dentro del ZIP, no
reconstruyéndolo con una librería. Se conservan intactos estilos, anchos de
columna, paneles, comentarios, `printerSettings`, propiedades del documento y
el `customXml` de la etiqueta de confidencialidad (*USO INTERNO*).

Sólo cambian:

- la hoja del catálogo (renglones nuevos + renumeración),
- el rango del autofiltro / `_FilterDatabase` / `dimension` / `sortState`,
- `xl/calcChain.xml`, que se elimina para que Excel lo reconstruya solo
  (se activa `fullCalcOnLoad` para que recalcule al abrir).

Las fórmulas de **A (Llave)** y **Q (Llave 2)** se reescriben renglón por
renglón (dejan de ser *shared formulas*) para que después del recorrido cada
una siga apuntando a sus propias celdas. El texto de la fórmula es idéntico al
original.

## Ajustes que puedes tocar

En el bloque **CONFIGURACIÓN** del script:

- `MAPEO_MANUAL` — de qué renglón del catálogo se copian los datos de cada
  llave nueva. Lo que pongas aquí manda sobre la búsqueda automática.
- `AGRUPAR_POR_CEDENTE` — `True` pega el renglón nuevo debajo de los
  movimientos de la misma cedente del mes; `False` lo manda siempre al final
  del bloque del mes.
- `OFERTA_NUEVOS` — valor de la columna Oferta (hoy `0`).
- `HOJA_CATALOGO` — si no quieres que detecte sola la hoja `...=TablaExtendida`.

## Corrida del 2026-08

17 movimientos (9 proporcionales + 8 no proporcionales):

| Mes (ENTRA) | Llaves |
|---|---|
| 202604 | `0-555-12-2026-1`, `0-903-14-2026-2`, `0-903-15-2026-1`, `0-903-28-2026-1`, `0-903-29-2026-1`, `0-903-30-2026-2`, `0-903-31-2026-2` |
| 202605 | `204-946-1-2026-2`, `204-946-2-2026-2`, `204-946-4-2026-2`, `394-240-1-2026-2` |
| 202606 | `75-1029-1-2026-1`, `413-1135-1-2026-1`, `413-1135-2-2026-1` |
| 202607 | `0-1029-4-2026-2` |
| 202608 | `0-1144-1-2026-1`, `0-1144-6-2026-1` |

**Para revisar a mano:** `75-1029-1-2026-1` (Echo Reinsurance). Entra por un
corredor nuevo (75) y es un *Agriculture Reinsurance India Quota Share*,
mientras que en el catálogo Echo sólo existe como Chile / Cono Sur / No
Proporcional. El script usa el contrato 1 de Echo como plantilla y corrige la
Clasificación a *Proporcional*, pero es muy probable que **País de Riesgo,
Territorio de Riesgo y la Línea de Negocio** deban cambiarse.
