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
- **`Reporte_Alertas_FCST27.xlsx`** — un renglón por negocio en ROJO o
  AMARILLO, con el mismo formato del reporte de alertas del RFCST 2026:
  identificación (LN, cedente, contrato, binder, país, región, corredor),
  las cifras del FCST 2027 **junto a aquello contra lo que se comparan**
  (RFCST 2026, FCST 2026, real 2026 a julio y real 2025), los índices y
  desviaciones **como fórmulas de Excel**, los cuatro semáforos y el motivo
  con los montos. Las celdas que dispararon cada alerta van **marcadas en
  amarillo** (p. ej. siniestralidad alta marca Primas FCST, Siniestros FCST
  y % Sin; un salto contra el RFCST marca además las dos cifras comparadas).
  Incluye hoja `Leyenda` con las reglas, umbrales y celdas que marca cada una.
- **`Dashboard_FCST27.html`** — dashboard interactivo:
  - **General**: KPIs por concepto (Primas, Siniestros, Comisiones y
    P-S-C / %P-S-C) con vistas *Tomado / Retenido*, dona de participación
    por LN (PPTO/FCST 27 vs RFCST 26) y dona de estacionalidad global
    (anillos P·S·C por mes).
  - **Línea de Negocio**: encabezada por un **filtro de LN que manda sobre
    toda la sección** — al elegir una línea, los cuadros de primas,
    siniestros y comisiones y **todas** las gráficas de abajo se recalculan
    a esa línea (comparativas por LN, variación vs RFCST, P-S-C / %P-S-C,
    estacionalidades y mensualización P·S·C); con *(Todas las LN)* se
    mantiene la vista comparativa entre líneas. Por cada concepto:
    comparativa por LN, variación vs RFCST y estacionalidad mensual, que al
    filtrar una sola LN agrega el comparativo contra la estacionalidad del
    RFCST 2026 y la del FCST 2026 (ver nota abajo). Cierran la sección el
    P-S-C / %P-S-C por LN y una única dona de mensualización P·S·C. Los
    selectores de cada gráfica siguen ahí para refinar una vista concreta y
    se sincronizan con el filtro de la sección.
  - **Negocios**: análisis a nivel cedente, contrato y Binder Ppto, con
    filtros, semáforos, resumen por entidad, estacionalidad del negocio
    seleccionado y top de excepciones.
  - Al final, botón para **descargar el reporte de alertas** (debe estar en
    la misma carpeta que el HTML) y botón **Imprimir PDF**, que imprime
    únicamente la sección Línea de Negocio.

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

**Conteo de negocios**: el negocio es la combinación de línea, cedente y
contrato (1,707 en el ejercicio 2027). Suscripción integra abriendo además por
**corredor**, lo que da un conteo mayor porque un mismo contrato colocado por
dos corredores cuenta doble (1,905 en total; en LN 4001, 571 contra 581). El
dashboard y el Excel reportan ambos conteos para poder reconciliar sin cambiar
el nivel de análisis. Ojo además con el alcance: el conteo del script es del
ejercicio 2027, mientras que una integración sobre todo el archivo incluye
negocios que solo tienen renglones en 2026.

**Comparativo vs RFCST 2026 a nivel negocio**: se compara cada negocio contra
su equivalente por línea + cedente + contrato, y solo se suman los que cruzan.
Comparar contra el total del cedente mezclaba sus otras líneas y desviaba el
dato al filtrar por LN.

## Cómo se levantan las alertas

El semáforo se evalúa **por negocio** (línea + cedente + contrato):

- **ROJO** — inconsistencias duras en negocios materiales: prima negativa,
  siniestros o comisiones sin prima, siniestralidad > 100%, comisiones > 65%.
- **AMARILLO** — índices altos (siniestralidad > 80%, comisiones > 45%,
  siniestralidad negativa) y desviaciones fuertes contra el mismo negocio en
  el RFCST 2026: prima desviada más de 40% o un salto de más de 30 pp en
  siniestralidad o comisiones.
- **VERDE** — sin alertas, o negocio por debajo de la materialidad.

Dos filtros evitan que el reporte se llene de ruido no accionable:
`MATERIALIDAD` (10,000 USD: por debajo no se escala a ROJO) y `RELEVANCIA`
(100,000 USD: una desviación contra 2026 solo alerta si mueve al menos ese
monto, para que un negocio de 30 k con el índice movido 30 pp no pese lo mismo
que uno de 20 M). Con esta calibración quedan 325 negocios con alerta de 1,707.

La **concentración mensual** de la prima se reporta como dato (% en el mes
pico) pero **no levanta semáforo a nivel negocio**: la prima única anual es lo
normal en reaseguro. Sigue siendo señal a nivel línea de negocio.

Los negocios **sin contraparte en el RFCST 2026** (nuevos, o con otra llave)
se señalan en el motivo, pero eso por sí solo no levanta semáforo.

En el dashboard, el semáforo de una entidad agregada es **el peor de sus
negocios**; las columnas Rojos y Amarillos dicen cuántos lo provocaron.

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

**Corrección de signo en el RFCST 2026**: en la LN 4008-Agro los siniestros y
los costos del reforecast se capturaron con la convención contable invertida
(los 57 renglones con siniestros vienen en negativo y 53 de 55 en costos,
cuando en el resto de las líneas y en las demás columnas de la propia LN van
en positivo). El script invierte el signo **renglón por renglón** — no solo el
total — para que el corte Ago-Dic derivado también quede bien, y lo registra
en `Calidad_Datos`. La corrección se valida sola: con ella los índices de esa
línea pasan a S/P 64.4% y C/P 22.9% en el RFCST, contra 63.1% y 23.0% del FCST
2027. Se configura en `SIGNO_INVERTIDO_RFCST`; si Suscripción corrige la base
de origen, basta vaciar ese diccionario.

**Nombre del presupuesto 2026**: se reporta como **FCST 2026** (constante
`ETIQ_PPTO26` al inicio del script), tanto en el dashboard como en el Excel.
