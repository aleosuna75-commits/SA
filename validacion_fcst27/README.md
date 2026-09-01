# Validación FCST 2027 (PPTO Técnico)

Script de validación de las cifras del FCST 2027 que comparte el área de
Suscripción, con dashboard interactivo estilo PRISMA (mismo formato que el
del RFCST 2026).

## Insumos (carpeta `Inputs/` o junto al script)

| Archivo | Obligatorio | Uso |
|---|---|---|
| `PptoTecnico2026.csv` (o `PptoTecnico*.csv` más reciente) | Sí | FCST 2027 de Suscripción (export SAP BW) |
| `BD_RFCST_26_act.xlsx` (o `BD_RFCST*.xlsx`) | No | Comparativas vs RFCST 2026 / FCST 2026 / Real 2025, y la estacionalidad mensual del FCST 2026 (hoja `Ppto2026`) |
| `BDReal26.xlsx` (hoja `BD`) | No | Real 2026 mensual: da la forma con la que se abre el Ene-Jul del RFCST |
| `Catalogo*.xlsx` (hoja `Valores`, columnas `Ced` / `CedenteRP`) | No | Nombres de cedentes en el dashboard |

Sin la base del RFCST el script corre igual y las comparativas se muestran
como `s/d`.

## Cómo correr

```
pip install pandas numpy openpyxl xlsxwriter
python VAL_FCST27.py
```

## Salidas (carpeta `Outputs/`)

- **`VAL_FCST27.xlsx`** — Dashboard de KPIs, Resumen_Global (tomado/retenido
  vs RFCST/Ppto), Resumen_LN con semáforos y score de riesgo,
  Estacionalidad_LN, Resumen_Cedente, Resumen_Negocio, Excepciones,
  Calidad_Datos, Retencion_Candidatas, Mapeo_Columnas y Parametros.
- **`Dashboard_FCST27.html`** — dashboard interactivo:
  - **General**: KPIs por concepto (Primas, Siniestros, Comisiones y
    P-S-C / %P-S-C) con vistas *Tomado / Retenido*, dona de participación
    por LN (PPTO/FCST 27 vs RFCST 26) y dona de estacionalidad global
    (anillos P·S·C por mes).
  - **Línea de Negocio**: por cada concepto, comparativa por LN, variación
    vs RFCST y estacionalidad mensual en líneas con filtro de LN — al
    elegir una sola LN se agrega el comparativo contra la estacionalidad
    del RFCST 2026 y la del FCST 2026 (líneas punteadas, ver nota abajo).
    Cierran la sección el P-S-C / %P-S-C por LN y una única dona de
    mensualización P·S·C con filtro de LN.
  - **Negocios**: análisis a nivel cedente / negocio (correlativo) con
    filtros, semáforos, resumen por entidad, estacionalidad del negocio
    seleccionado y top de excepciones.
  - Botón **Imprimir PDF** al final: imprime únicamente la sección Línea
    de Negocio.

> \* Falta el incremento a la reserva y los costos de cobertura — señalado
> en el dashboard y en el Excel.

## Notas importantes sobre el export de Suscripción

**Encabezados permutados**: los nombres de columna del CSV no corresponden al
orden real de los datos (típico del export de BW). El script lee por posición
con el layout correspondiente al ancho del archivo (45 o 42 columnas),
documentado en la hoja `Mapeo_Columnas` del Excel.

**Concepto P/S/C**: el export de 45 columnas trae la cuenta contable que
identifica el concepto. El catálogo `CUENTAS_CONCEPTO` lo traduce:

| Cuenta | Concepto |
|---|---|
| 6104010000 · 6108010000 · 6111090000 | Primas (vienen en negativo, por ser abono) |
| 5402010000 · 5402030000 | Siniestros |
| 5310010000 | Comisiones |

El mapeo se validó contra el RFCST 2026 y el real 2026: produce S/P 44.1% y
C/P 18.5%, contra 44.6% y 20.2% del RFCST. La hoja `Cuentas_Concepto` del
Excel muestra cuánto aporta cada cuenta; si aparece una cuenta nueva se
clasifica por prefijo y se reporta en `Calidad_Datos`.

> El export anterior (42 columnas) no traía esa cuenta y el concepto se
> reconstruía por la estructura del archivo. Esa ruta sigue como respaldo,
> pero **no separa siniestros de comisiones** en los negocios con una sola
> corrida positiva (eran 174 M, el 42% de los siniestros reportados).

**Nivel de análisis de negocios**: cedente, contrato y Binder Ppto. La columna
de Binder Ppto viene vacía en el export actual; el filtro y el nivel de
agrupación ya están en el dashboard para cuando se llene.

**Vista Retenido**: la base no trae una marca confiable de retención. Por
default retenido = tomado (con aviso en el dashboard). Cuando Suscripción
confirme la marca, configurar `COL_VISTA_RETENIDO` (hay dos banderas
candidatas, ver hoja `Retencion_Candidatas`) o capturar `RETENCION_LN`
(% de retención por LN).

**Granularidad de la estacionalidad 2026**: el CSV del FCST solo trae
mensualizado el ejercicio 2027 (los demás años vienen como un renglón único en
el periodo 6). Para el comparativo 2026 se usan dos bases adicionales:

| Serie | Fuente | Ajuste |
|---|---|---|
| FCST 2026 | hoja `Ppto2026` del libro del RFCST (12 meses abiertos) | ninguno, se grafica sólida |
| RFCST 2026 · Ene-Jul | forma mensual del real 2026 (`BDReal26.xlsx`), escalada al acumulado a julio del RFCST | ninguno, se grafica sólida |
| RFCST 2026 · Ago-Dic | incremento Ago-Dic del RFCST repartido con la mensualización del FCST 2027 | **sí**, se grafica punteada y se declara al pie de la gráfica |

El ajuste aplica **solo al RFCST 2026**, porque su base no trae esos meses
abiertos. Si falta alguna de las dos bases el perfil cae a plano por bloque.

**Nivel del FCST 2026**: los niveles salen de `BD_RFCST26` (mismo universo de
contratos que el comparativo). La hoja `Ppto2026` trae el presupuesto completo
de la compañía, que es mayor porque incluye contratos sin prima registrada;
para reportar ese presupuesto completo en los niveles, poner
`PPTO26_NIVEL_DESDE_HOJA = True`.

**Nombre del presupuesto 2026**: se reporta como **FCST 2026** (constante
`ETIQ_PPTO26` al inicio del script), tanto en el dashboard como en el Excel.
