# Validación FCST 2027 (PPTO Técnico)

Script de validación de las cifras del FCST 2027 que comparte el área de
Suscripción, con dashboard interactivo estilo PRISMA (mismo formato que el
del RFCST 2026).

## Insumos (carpeta `Inputs/` o junto al script)

| Archivo | Obligatorio | Uso |
|---|---|---|
| `PptoTecnico2026_Completo.csv` (o `PptoTecnico*.csv` más reciente) | Sí | FCST 2027 de Suscripción (export SAP BW) |
| `BD_RFCST_26_act.xlsx` (o `BD_RFCST*.xlsx`) | No | Comparativas vs RFCST 2026 / Ppto 2026 / Real 2025 (la misma base del dashboard del RFCST) |
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

El CSV actual trae dos defectos de origen (documentados también en las
hojas `Mapeo_Columnas` y `Calidad_Datos` del Excel):

1. **Encabezados permutados**: los nombres de columna no corresponden al
   orden real de los datos. El script lee por posición con el mapeo
   `MAPEO_POSICIONAL` (verificado contra la estructura de los datos, con
   chequeo automático LN ↔ cuenta contable).
2. **`ZCONCEPTO` vacía**: primas / siniestros / comisiones se distinguen
   solo por la estructura del archivo (corridas por negocio en orden
   P → S → C; primas en negativo, gastos en positivo). El script
   reconstruye el concepto con esa regla y reporta lo no clasificable.
   Si Suscripción reexporta con el concepto lleno, basta configurar
   `COL_CONCEPTO_EXPLICITO`.

**Vista Retenido**: la base no trae una marca confiable de retención. Por
default retenido = tomado (con aviso en el dashboard). Cuando Suscripción
confirme la marca, configurar `COL_VISTA_RETENIDO` (hay dos banderas
candidatas, ver hoja `Retencion_Candidatas`) o capturar `RETENCION_LN`
(% de retención por LN).

**Nivel MGA / número de contrato**: el export no trae número de contrato ni
marca de MGA; el análisis de negocios usa cedente + correlativo del sistema.

**Granularidad de la estacionalidad 2026**: el CSV solo trae mensualizado el
ejercicio 2027 (los demás años vienen como un renglón único en el periodo 6),
y la base del RFCST no está mensualizada: solo separa Ene-Jul (real
devengado) de Ago-Dic (proyección). Por eso el comparativo de estacionalidad
contra RFCST 2026 y FCST 2026 se dibuja **punteado y plano dentro de cada
bloque** — es el share real de cada semestre repartido entre sus meses, no
una mensualización inventada. Si Suscripción comparte la mensualización de
2026, se puede alimentar directo al perfil.

**Nombre del presupuesto 2026**: se reporta como **FCST 2026** (constante
`ETIQ_PPTO26` al inicio del script), tanto en el dashboard como en el Excel.
