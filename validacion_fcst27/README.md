# Validación FCST 2027 (PPTO Técnico)

Script de validación de las cifras del FCST 2027 que comparte el área de
Suscripción, con dashboard interactivo estilo PRISMA (mismo formato que el
del RFCST 2026).

## Insumos (carpeta `Inputs/` o junto al script)

| Archivo | Obligatorio | Uso |
|---|---|---|
| `PptoTecnico2027_Ced.csv` (o `PptoTecnico*.csv` más reciente) | Sí | FCST 2027 de Suscripción (export SAP BW), con la columna `PRCT_CED` del % de cesión |
| `BD_RFCST_26_act.xlsx` (o `BD_RFCST*.xlsx`) | No | Comparativas vs RFCST 2026 / FCST 2026 / Real 2025, y la estacionalidad mensual del FCST 2026 (hoja `Ppto2026`) |
| `BDReal26.xlsx` (hoja `BD`) | No | Real 2026 mensual por LN y en dólares: da la forma con la que se abre el Ene-Jul del RFCST y se grafica como serie propia |
| `BDReal25.xlsx` (mismo formato) | No | Real 2025 mensual, como serie propia en la estacionalidad |
| `BD_082026.xlsx` (export operativo) | No | Extiende el real 2026 con los meses que la base en dólares todavía no tiene |
| `Catalogo*.xlsx` (hoja `Valores`, columnas `Ced` / `CedenteRP`) | No | Nombres de cedentes en el dashboard |

Sin la base del RFCST el script corre igual y las comparativas se muestran
como `s/d`.

La base del FCST se busca por nombre, en este orden: `PptoTecnico2027_Ced`
(tomado + % de cesión), `PptoTecnico2027` (solo tomado) y `PptoTecnico2026`
(nombre del export anterior). Si no aparece ninguno se usa el `PptoTecnico*`
más reciente de la carpeta, avisando cuál tomó.

**`.csv` y `.xlsx`, con prioridad siempre del CSV.** La extensión se decide
por fuera del nombre: primero se recorren los tres nombres buscando `.csv` y
solo si no aparece ninguno se recorren otra vez buscando `.xlsx`. Así un CSV de
menor prioridad en la lista le gana a cualquier XLSX.

> Conviene que la base llegue en CSV. El XLSX se lee bastante más lento y una
> hoja de Excel no pasa de 1,048,576 renglones, así que una base grande
> guardada en ese formato queda truncada; si la hoja llega al límite, el script
> lo avisa.

## Cómo correr

```
pip install pandas numpy openpyxl xlsxwriter
python VAL_FCST27.py
```

## Salidas (carpeta `Outputs/`)

- **`VAL_FCST27.xlsx`** — Dashboard de KPIs, Resumen_Global (tomado/retenido
  vs RFCST/Ppto), Resumen_LN con semáforos y score de riesgo,
  Estacionalidad_LN, Resumen_Cedente, Resumen_Negocio, Excepciones,
  Calidad_Datos, Cuentas_Concepto, Cuadre_LN, Cesion, Mapeo_Columnas y
  Parametros.
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

**Cómo se identifican las columnas**: el export trae los nombres técnicos de
SAP (`/ERP/GL_ACCT`, `/ERP/FUNCAREA`, `ZCEDENTE`, `PRCT_CED`, …). El script
intenta primero armar el layout **por nombre de encabezado** (`MAPEO_NOMBRES`)
y **siempre lo verifica contra el contenido** — LN con formato `LN0…`, cuentas
contables, periodo, año, mes, región, moneda y un monto numérico y variable.
Si pasa, se usa; así la base aguanta columnas nuevas (el `_ID` y el `PRCT_CED`
de la base con cesión) o reordenadas sin tocar nada.

Si los nombres no alcanzan o no cuadran con los datos, cae al **mapeo
posicional** de siempre, con el layout correspondiente al ancho del archivo
(45 o 42 columnas). Cuál de los dos caminos se usó queda escrito en el
parámetro *Layout del CSV* y, columna por columna, en la hoja
`Mapeo_Columnas` del Excel.

**Concepto P/S/C**: el export de 45 columnas trae la cuenta contable que
identifica el concepto. El catálogo `CUENTAS_CONCEPTO` lo traduce:

| Cuenta | Concepto |
|---|---|
| 6104010000 · 6108010000 · 6111090000 | Primas (vienen en negativo, por ser abono) |
| 5402010000 · 5402030000 | Siniestros |
| 5310010000 | Comisiones |

El mapeo se validó contra el RFCST 2026 y el real 2026: produce S/P 44.1% y
C/P 18.5%, contra 44.6% y 20.2% del RFCST.

**Cuentas nuevas.** Lo que no está en el catálogo se resuelve por **familia de
dos dígitos** (`PREFIJOS_CONCEPTO`): `61` → primas, `54` → siniestros, `53` →
costos de adquisición. La familia y no el subgrupo, para que una subcuenta
nueva (`5403…`, `5404…`) entre en su concepto en vez de quedarse sin clasificar
y salir de las cifras. Además:

- se imprime en consola cada cuenta fuera del catálogo con su monto;
- si algo queda sin clasificar, sale un **ATENCIÓN con el desglose por LN y
  cuenta** y el monto que queda fuera;
- la hoja `Cuentas_Concepto` abre por **LN × cuenta × concepto**, marcando si
  la cuenta está en el catálogo o entró por prefijo.

### Estacionalidad: ejercicios reales

Las gráficas comparan la mensualización del FCST 2027 contra el RFCST 2026, el
FCST 2026 y **los ejercicios reales**. Cada real se configura en
`BASES_REALES` (archivo y año); basta con dejarlo en `Inputs/`.

La normalización es lo único delicado, porque hay años incompletos:

| Serie | Denominador | Por qué |
|---|---|---|
| Año cerrado (2025) | su propio año | es su estacionalidad |
| Año del RFCST (2026), con meses abiertos | el año completo del RFCST 2026 | así se lee mes a mes contra esa curva: la separación entre las dos líneas es cuánto va adelantado o atrasado el real contra el plan |
| Cualquier otro año incompleto | su propio acumulado | no hay contra qué referenciarlo |

Los meses sin dato van en `null`, así que la línea corta en el último mes
cerrado. El pie de la gráfica declara el criterio de cada serie.

**Extensión con el export operativo.** `BD_082026.xlsx` cierra antes que la
base en dólares, pero no trae LN ni dólares. Los meses que le faltan a la base
en dólares se toman de ahí (`BASES_REALES_CRUDAS`):

- los importes salen de `PriTomNal5`, `SinTomNal5` y **`CosTomNal5`** — la de
  costo, que es comisión + utilidad + corretaje, no la de comisión sola: con
  `ComTomNal5` el tipo de cambio implícito se va a 15 en vez de 17.4;
- se convierten con el **tipo de cambio implícito de los meses que ambas bases
  comparten**, calculado por concepto;
- se reparten por LN con una **cascada de llaves de contrato** (tipo rea +
  corredor + compañía + contrato + año susc., luego sin el año, luego compañía
  + contrato). El año de suscripción sale del segundo nivel porque la LN es del
  contrato y no de la cohorte: exigirlo baja la cobertura de 95% a 80%. Lo que
  no cruza se prorratea entre las LN que sí cruzaron.

Todo eso se imprime en consola y se declara al pie de la gráfica. El tramo
extendido **solo alimenta la estacionalidad**: el acumulado por negocio que usa
el reporte de alertas sigue siendo el de la base en dólares.

### Estacionalidad por LN o por ramo

Cada gráfica de estacionalidad trae un selector **Por LN / Por ramo**. El ramo
se maneja con su **código** (`Ramo 60`, `Ramo 110`…), igual que la LN, y se
resuelve con dos catálogos sacados de la hoja `Valores` del libro del RFCST:

```
 10 Vida          31 Acc Per.     39 Salud        50 MyT        71 Terremoto
 20 Vida (pens.)  35 GMM          40 Resp. Civil  60 Incendio   73 HyORH
 80 Agropecuario  90 Autos       100 Crédito     110 Diversos  130 Fianzas
```

Los dos caminos (centro de beneficio y subramo) devuelven exactamente el mismo
juego de 15 códigos, así que las fuentes cruzan sin traducción intermedia.


| Fuente | De dónde sale el ramo | Cobertura |
|---|---|---|
| FCST 2027 | centro de beneficio (`/ERP/PROFTCTR`) → `CAT_RAMO` | 100% |
| Real 2026 (`BD_082026.xlsx`) | subramo (`SRamo`) → `CAT_SUBRAMO` | 100% |
| FCST 2026 (`Ppto2026`) | subramo (`Subramo`) → `CAT_SUBRAMO` | 100% |
| **RFCST 2026** | no trae ramo; por llave de contrato solo cruza 24.5% | **no se dibuja** |

Por eso en vista por ramo **no aparece el RFCST 2026**: mostrarlo con una
cuarta parte de la prima sería peor que no mostrarlo.

Dos detalles del catálogo que importan:

- el ramo se resuelve por **subramo** y no por la columna `Ramo` de las bases
  operativas, porque esa agrupa 31/35/39 en 30 y 71/73 en 70, y no llegaría al
  mismo corte que el catálogo de centros de beneficio;
- en vista por ramo el real 2026 sale **completo del export operativo**
  (ene-ago), no de la base en dólares: esa solo trae el ramo agrupado, y
  mezclar las dos daría claves distintas. Por eso ese tramo va convertido con
  el tipo de cambio implícito, y el pie de la gráfica lo declara.

El filtro maestro de la sección es por LN, así que al usarlo las gráficas
vuelven a la vista por LN.

### Hoja `Cuadre_LN`

Cuadre de la cuenta contable a las cifras publicadas, una línea por LN. La
identidad tiene que cerrar:

```
monto del export = −primas + siniestros + comisiones + sin clasificar
```

La columna **Cuadre (debe ser 0)** verifica esa identidad, **Sin clasificar**
dice cuánto monto quedó fuera, y las tres últimas columnas muestran los
renglones capturados con el signo contrario al esperado (primas en positivo,
siniestros o comisiones en negativo).

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

## Vista Retenido (cesión)

La base con cesión, **`PptoTecnico2027_Ced.csv`**, es la misma del FCST con dos
columnas extra: `_ID` (consecutivo del renglón, no se usa) y **`PRCT_CED`**, el
**% de cesión del renglón** en fracción (0-1). De ahí:

```
cedido   = monto tomado × % de cesión
retenido = tomado − cedido = tomado × (1 − % de cesión)
```

Se aplica renglón por renglón, así que vale igual para primas, siniestros y
comisiones. El script prefiere esta base sobre `PptoTecnico2026.csv` cuando
ambas están en `Inputs/`.

**Cómo se localiza la columna**: **por nombre** (`PRCT_CED`, `Prc_Ced` y
variantes en `COL_CESION_ALIAS`, sin distinguir mayúsculas ni acentos), en
cualquier posición del archivo. Cuando el layout se resolvió por nombre de
encabezado, la columna de cesión se toma de ahí directo; cuando se resolvió
por posición, `localizar_cesion()` la aparta verificándola contra el contenido
y contra el perfil estructural del resto de columnas.

**Formato del número**: se distingue la coma decimal de la coma de miles. Un
export guardado con configuración regional en español trae el porcentaje como
`0,0411`; quitarle la coma lo volvería 411 y el retenido saldría disparatado.
La coma se toma como decimal cuando no hay ningún punto en la columna y los
valores con coma son dígitos a ambos lados sin pinta de grupos de miles; el
script dice en consola cuál de las dos lecturas usó.

**Si la cesión se agrega al mapeo de columnas** (un layout posicional con un
campo llamado `Prc_Cesion`), el script la toma de ahí: antes ese campo se
sobrescribía con cero y el retenido salía igual al tomado sin que nada lo
dijera. Y cuando de plano no se localiza el porcentaje, el aviso es explícito
—dice que no se multiplicó nada y dónde busca la columna—, porque esa es la
única forma de que la vista retenido salga silenciosamente mal.

**Varias columnas con nombre de cesión**: manda la que se llame exactamente
como `COL_CESION` (avisando cuáles había); si ninguna desempata, falla en vez
de adivinar.

**Escala**: se decide con el **percentil 99** de la columna completa, no con el
máximo — así un renglón mal capturado (un 1.5 en una columna de fracciones) no
cambia la lectura de toda la columna. Si el p99 ≤ 1 se lee como fracción; si
está entre 1 y 100 se divide entre 100; arriba de eso el script falla con un
error explícito. Los valores negativos y los que rebasan el tope se recortan y
**se avisan en consola con su conteo**.

El script falla con un error explícito —en vez de adivinar— si hay dos
columnas con nombre de cesión, si la columna no es numérica, o si el layout no
se puede resolver ni por nombre ni por posición. Antes eso que calcular mal el
retenido en silencio. Para forzar una posición de datos existe `POS_CESION`.

La hoja `Calidad_Datos` reporta cuántos renglones traen cesión en 0% (se
retienen completos) y cuántos en 100% (se ceden completos), con su prima.

**El dashboard completo en las dos vistas.** El switch **Tomado / Retenido**
del encabezado cambia *todo*: los cuadros de General, los de Línea de Negocio,
las comparativas por LN, las estacionalidades, la mensualización P·S·C, la
sección de Negocios con sus filtros, semáforos y excepciones, y el reporte de
alertas que se descarga. Las dos vistas tienen exactamente las mismas gráficas
y tablas; lo único que cambia es la fuente de datos y aquello contra lo que se
compara:

| | Tomado | Retenido |
|---|---|---|
| Comparativa por LN | FCST 2027 · RFCST 2026 · FCST 2026 | Tomado · Cedido · Retenido |
| Segunda gráfica | Variación vs RFCST 2026 | % de retención por LN |
| Estacionalidad de una LN | vs RFCST 2026 y FCST 2026 | vs el tomado de esa misma LN |
| KPI de negocios | Crecimiento vs RFCST 2026 | % de retención |
| Reporte de alertas | `Reporte_Alertas_FCST27.xlsx` | `..._Retenido.xlsx` |

**Por qué el retenido no se compara contra 2026**: el RFCST 2026, el FCST 2026
y los reales son cifras de **tomado** — en la hoja `Ppto2026` las columnas
`PmasRetro`, `SinReten` y `CostosNetosAdq` vienen en cero, así que no hay
retenido de referencia en ninguna base. Contrastar el retenido del FCST 2027
contra ellas daría una caída que solo refleja la cesión. Por eso esa vista se
contrasta contra el **propio tomado del ejercicio** y muestra el cedido y el %
de retención. Si más adelante llega el retenido del RFCST 2026, ahí sí tendría
sentido volver a comparar.

El Excel trae la hoja `Cesion` (tomado, cedido, retenido y porcentajes por LN y
concepto) y las hojas `Resumen_LN_Ret` y `Resumen_Negocio_Ret` con las cifras
netas.

Si la base cargada no trae la columna, el retenido queda igual al tomado y se
señala con una nota discreta al pie de la vista (no con un banner). Como
respaldo manual existe `RETENCION_LN`, un % de retención por LN capturado a
mano.

### Candado de simulación (`SIMULAR_CESION`)

Interruptor binario en la configuración, para ver cómo queda el tablero
retenido **mientras llega la base con la cesión**:

| Valor | Efecto |
|---|---|
| `SIMULAR_CESION = 1` | Si la base **no** trae la columna de cesión, se sortea un % aleatorio y el retenido se calcula con él |
| `SIMULAR_CESION = 0` | Comportamiento normal: sin columna de cesión, retenido = tomado |

El rango y la semilla del sorteo se controlan con `SIM_CESION_MIN`,
`SIM_CESION_MAX` (0 y 1 por omisión) y `SIM_CESION_SEMILLA`.

Tres reglas del candado:

1. **El dato real siempre gana.** Si la base trae `PRCT_CED`, el candado se
   ignora aunque esté en 1, y el script lo avisa en consola.
2. **El % se sortea por negocio** (LN + cedente + contrato), no por renglón:
   así cada negocio conserva la misma retención en los 12 meses y en los tres
   conceptos, y las gráficas se comportan como se van a comportar con la
   cesión real. Con la semilla fija, dos corridas dan los mismos porcentajes.
3. **Las cifras simuladas quedan marcadas** en todas las salidas: banner
   amarillo arriba de la vista retenido del dashboard (que además sí sale en
   la impresión de la sección de LN), nota al pie de cada bloque de tarjetas,
   título y leyenda del `Reporte_Alertas_FCST27_Retenido.xlsx`, y el
   parámetro `Vista retenido` de la hoja `Parametros`.

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
