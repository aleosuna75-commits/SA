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
  - **Línea de Negocio**: comparativa por LN y variación vs RFCST,
    estacionalidad mensual en líneas con filtro de LN, y mensualización
    P·S·C en dona de anillos con filtro de LN — para primas, siniestros y
    comisiones; P-S-C / %P-S-C por LN al final.
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
