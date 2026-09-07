# Validación del FND (MEC) contra la prima devengada real

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

## Conclusión

**El MEC v2 tal como está publicado (FND por prorrata de vigencias, indexado desde el inicio de vigencia) no cuadra con la prima devengada real: reproduce sólo el 25.5% de la RRC real y sobreestima la prima devengada tomada entre 2.6% y 8.4% al año.** La RRC real (base BEL-IRR-MR) devenga la prima proporcional y facultativa por **antigüedad de registro** con la recta de la Nota Técnica, y cerca del 69% de la prima de Patria se registra en un año calendario posterior al de su inicio de vigencia, así que "antigüedad desde la vigencia" y "antigüedad desde el registro" son dos mundos distintos.

**Recalibrado el FND sobre la antigüedad de registro, con un desplazamiento δ por ramo (regla M4 del propio MEC), el modelo reproduce la RRC real con error medio mensual del 3.1% y la prima devengada anual con error de −2.3% (2023), +1.4% (2024), +0.7% (2025) y +1.2% (2026 ene–may), tanto tomada como retenida.** El no proporcional conserva la prorrata exacta por fechas.

## Qué se comparó

| Concepto | Definición usada (igual que Integración Dim, hoja ER_2026) |
|---|---|
| Prima devengada tomada real | Prima emitida − Δ RRC bruta (tomada) |
| Prima devengada retenida real | Prima retenida − Δ RRC neta (bruta − IRR) |
| Saldos reales | `BD_ BEL - IRR - MR.xlsx`, hoja BD_Montos_RRC_SONR (USD, 202201–202605) |
| Prima emitida | BD del MEC (PrimasNal, Tipo Póliza P*), convertida a USD al TC de cierre del mes de registro |
| Prima retenida | Prima emitida × (1 − % cedido anual del ER real por ramo) |
| RRC modelo | PND_modelo × IS × (1 + gasto + MR) e IRR = BEL × % cesión, con IS, gasto, MR y cesión **reales** mes a mes |

Como todo lo que no es FND se toma del real, la razón RRC modelo / RRC real es exactamente la razón prima no devengada modelo / real: la comparación aísla el factor de devengamiento. Fianzas (ramos 130–170) queda fuera porque la base no trae RRC para ese negocio. Todo en USD; la conversión a MXN del resumen usa Δ mensual × TC de cierre, que es como el ER lleva la variación de reserva.

## Resultados

Razón Σ prima no devengada modelo / real y error absoluto medio mensual, 202301–202605 (CAT desde 202401).
El peso es la participación en la PND real sobre la ventana común 202301–202605, así que suma 100%: **el ramo más
pesado es Incendio (31.9%), no CAT (29.8%)**.

| Ramo | Peso en RRC | NT por registro (mensual) | NT por registro (trimestral) | MEC publicado (cohorte vigencia) | **Calibrado δ** | MAPE calibrado |
|---|---|---|---|---|---|---|
| Incendio | 32% | 0.997 | 0.868 | 0.164 | **0.997** | 2.4% |
| CAT (71+73) | 30% | 0.950 | 0.842 | 0.253 | **1.003** | 5.2% |
| MyT | 10% | 0.987 | 0.846 | 0.145 | **1.005** | 5.2% |
| Diversos | 8% | 1.006 | 0.859 | 0.117 | **1.006** | 5.1% |
| Vida | 7% | 1.161 | 1.065 | 0.423 | **1.016** | 10.1% |
| AyE | 4% | 1.100 | 0.985 | 0.350 | **1.018** | 17.1% |
| RC | 3% | 0.989 | 0.857 | 0.145 | **0.989** | 9.8% |
| Autos | 3% | 1.082 | 0.980 | 0.446 | **0.921** | 16.0% |
| Agro | 2% | 1.186 | 1.008 | 0.179 | **0.968** | 8.5% |
| Crédito | 1% | 0.866 | 0.740 | 0.071 | **0.995** | 8.7% |
| **Total** | | **0.993** | 0.871 | **0.218** | **0.989** | **3.1%** |

**Sobre la columna «MEC publicado».** Esos ratios son los de la reconstrucción del banco, que usa los vectores PF+ a
72 meses con la cola a cero. El MEC v2 publicado los trunca a 24 (`HORIZONTE = 24`) y **sostiene `vec[23]` de ahí en
adelante** (`TablaFND.factor`), lo que le da un piso permanente en todos los ramos. Reproducida la regla publicada al
pie de la letra, el ratio total sube de **0.218 a 0.255** y los de ramo a: Incendio 0.189, CAT 0.275, MyT 0.167,
Diversos 0.152, Vida 0.625, AyE 0.360, RC 0.169, Autos 0.470, Agro 0.268, Crédito 0.090. La conclusión no cambia
—el MEC publicado reproduce alrededor de un cuarto de la RRC real— pero la cifra a citar es **25.5%, no 22%**.

Prima devengada del total de la cartera (USD), real vs modelo:

| Año | Prima emitida | PD tomada real | PD tomada calibrado | error | PD tomada MEC publicado | error | PD retenida real | PD retenida calibrado | error |
|---|---|---|---|---|---|---|---|---|---|
| 2023 | 647.8 M | 599.9 M | 586.0 M | −2.3% | 639.1 M | +6.5% | 476.0 M | 464.4 M | −2.4% |
| 2024 | 795.1 M | 730.3 M | 740.5 M | +1.4% | 791.2 M | +8.4% | 564.7 M | 574.3 M | +1.7% |
| 2025 | 1,013.7 M | 962.2 M | 969.4 M | +0.7% | 998.3 M | +3.8% | 695.2 M | 700.5 M | +0.8% |
| 2026 ene–may | 481.5 M | 445.6 M | 451.0 M | +1.2% | 457.3 M | +2.6% | 337.3 M | 339.9 M | +0.8% |

En MXN, 2025: prima devengada tomada real 18,375 M vs calibrado 18,539 M (+0.9%) vs MEC publicado 19,060 M (+3.7%); retenida real 13,278 M vs calibrado 13,403 M (+0.9%).

Saldo al 202605 (USD): RRC bruta real 370.4 M, calibrado 360.3 M (−2.7%), MEC publicado **107.8 M (−70.9%)**. Adoptar el MEC publicado liberaría **262.5 M USD (≈ 4,553 M MXN)** de reserva bruta.

## Por qué el MEC publicado no cuadra

1. En la BD del MEC, la prima se registra con mucho rezago respecto a su vigencia: 8% en el mes de inicio, 14% entre 6 y 8 meses después, 17% entre 9 y 11, 28% entre 12 y 17 y 20% a 18 meses o más. El 69% de la prima (79% del proporcional) se registra en un año calendario posterior al de inicio de vigencia.
2. El MEC v2 asigna a esa prima el FND de su cohorte de vigencia, que ya es cero o casi cero cuando se registra. La RRC real, en cambio, la devenga como riesgo nuevo desde el mes de registro (recta de 24-avos de la Nota Técnica). Es la misma lógica de `xPND[CALMONTH]` de los reforecast, y los datos lo confirman: para Incendio, MyT, Diversos y RC la NT mensual por registro reproduce la RRC real con δ = 0.
3. La prorrata exacta por fechas sí es la regla correcta para el no proporcional (TipoRea 2), **excepto CAT**: en el
   reforecast la rama `Ramo in [71, 73] → VALORFREC` se evalúa **antes** que la de `TipoRea == 2`, así que el CAT no
   proporcional nunca llega a la prorrata y se devenga por `xPND`. CAT es el 49.3% de la prima TipoRea 2, de modo que
   la prorrata cubre el **6.8%** de la prima en USD, no el 13.4% que es el TipoRea 2 completo. Es una razón más para
   mirar CAT aparte.

Nota metodológica: la prorrata por vigencia es la visión económica del riesgo corrido; la RRC real refleja la regla regulatoria de registro. Para que el modelo cuadre con la prima devengada contable hay que reproducir la regla regulatoria, y ese es el objetivo que se pidió aquí.

## Recalibración propuesta

FND por ramo indexado por antigüedad de registro k = mes de valuación − mes de registro:

    FND_ramo(k) = min(1, max(0, NT(k) − δ_ramo)),  k = 0..11;  0 en adelante

δ es el desplazamiento de la regla M4 del MEC (frecuencia de cuentas: δ = (t − 1)/2 · 30/365). Valores ajustados por mínimos cuadrados contra la prima no devengada real:

| Ramo | δ | Meses de cuenta equivalentes | Lectura |
|---|---|---|---|
| Incendio (60), Diversos (110), RC (40) | 0.000 | 1.0 | NT mensual tal cual |
| MyT (50) | −0.010 | 0.8 | NT mensual |
| CAT (70) | −0.035 | 0.1 | ligeramente arriba de NT mensual |
| AyE (30) | 0.045 | 2.1 | bimestral |
| Vida (10) | 0.070 | 2.7 | trimestral aprox. |
| Agro (80) | 0.095 | 3.3 | trimestral–cuatrimestral |
| Autos (90) | 0.130 | 4.2 | cuatrimestral |
| Crédito (100) | −0.085 | — | sobre NT mensual (ramo de 1% del peso; FND acotado a 100%) |

La tabla completa está en `salidas/tabla_fnd_calibrada.csv` y en la hoja TablaFND_calibrada del Excel. El módulo `fnd_calibrado.py` la expone para integrarla en el reforecast RRC y en el SONR (`fnd_calibrado(ramo, k_reg)` y `factor_no_devengado_cal(row, mes_valuacion, fecha_valuacion)`); lee δ de `salidas/delta_calibrado.json` para que una recalibración futura no exija tocar código.

Recomendación de recalibración periódica: correr `validar_prima_devengada.py` en cada cierre trimestral con la base BEL-IRR-MR actualizada; si el ratio total sale de ±3% o algún ramo con peso > 5% sale de ±10%, reajustar δ.

## El δ del modelo estaba calibrado sobre otra base — recalibrado, el FND del modelo ya sirve

Esta sección se reescribió dos veces según fueron llegando datos. Lo que sigue es lo medido con los archivos
`ConsultaPPTO_RRC_2..5_tradicional.xlsx` que produjo el propio reforecast, contra la RRC real de esos mismos meses.
Reproducible con `recalibrar_delta_reforecast.py`.

### El diagnóstico

Corriendo el reforecast RRC con el FND del modelo, la desviación contra la RRC real venía de que **δ se calibró
contra una base de prima y se aplicó a otra**. δ se ajustó para que `Σ prima_BD-MEC × FND ≈ PND_real`; el reforecast
aplica ese mismo δ sobre la prima que sale de su propia consulta, que con el **mismo** FND produce **+6.2% más BEL**
(+9.9% sin CAT). La descomposición cierra al decimal:

    1.0499 (modelo/real en el reforecast) = 0.9886 (modelo/real en el banco) × 1.0620 (brecha de base)

Es decir: si la base fuera la misma, el modelo daría −1.1% en el reforecast, no +5.0%. La brecha explica la
desviación entera y sobra.

**No son dos consultas a universos distintos.** El input del MEC se construye del mismo `BDReal26.xlsx` que alimenta
la BD de la consulta, y la prima registrada coincide ramo por ramo (481.47 vs 481.49 M USD, razón 1.000 en los diez
ramos). La brecha no está en qué prima se lee sino en qué le hace la consulta del reforecast: la valúa al TC del mes
de **valuación** en vez del de **registro** (+2.0 pp de los +6.2, medidos: el TC pasa de 20.69 a 17.34 en la ventana),
arma `MONTO_PI` como `PriTom+PriTomEnC+PriTomReC`, aplica el candado `Val(left(aPog_MesProc,4)) <= Susc`, excluye
`LlavesPol`, y prorratea el no proporcional por fechas exactas en vez del vector PF+ de cartera que usa el banco.
Y la brecha **no es uniforme**: va de +2.8% (Vida) a +26.9% (Diversos), con CAT en −30.2%. Por eso ningún δ ajustado
contra el banco puede aterrizar bien en el reforecast: el factor de traslado cambia por ramo.

### La corrección

Reajustar δ contra el BEL real usando la prima del propio reforecast. La forma funcional no cambia —sigue siendo
`FND = clip(NT(k) − δ_ramo, 0, 1)`— sólo los números:

| Ramo | δ de producción | δ recalibrado | peso en el BEL real (sin CAT) |
|---|---|---|---|
| Incendio | 0.000 | **+0.050** | 37.4% |
| Vida | +0.070 | **+0.055** | 18.7% |
| MyT | −0.010 | **+0.030** | 18.7% |
| Diversos | 0.000 | **+0.060** | 8.5% |
| AyE | +0.045 | **+0.030** | 5.4% |
| RC | 0.000 | **+0.105** | 4.8% |
| Autos | +0.130 | **+0.315** | 3.7% |
| Agro | +0.095 | **+0.130** | 1.7% |
| Crédito | −0.085 | **0.000** | 1.1% |
| CAT | −0.035 | *sin cambio* | — (δ no lo mueve) |

Corrobora el resultado que estos δ recalibrados caen casi encima del **desplazamiento efectivo que el FND legado ya
aplicaba**, despejado por un método completamente distinto (el uplift observado entre las dos corridas):
Incendio 0.050 vs 0.047 · MyT 0.030 vs 0.038 · Vida 0.055 vs 0.043 · Diversos 0.060 vs 0.045 · Autos 0.315 vs 0.356 ·
Agro 0.130 vs 0.100 · Crédito 0.000 vs −0.001. Dos caminos independientes dan la misma respuesta.

### Lo que gana y lo que no

Las tres opciones sobre **la misma base y la misma ventana** (202602–202605, BEL riesgo USD, 36 pares ramo × mes,
sin CAT). El legado se reconstruye sobre los mismos archivos con la regla M4:

| | razón BEL/real | EAM por ramo × mes | peor caso | pares con error > 5% |
|---|---|---|---|---|
| FND legado (reconstruido) | 1.0184 | 4.13% | 32.9% | 25% |
| FND del modelo, δ de producción | 1.0927 | 15.45% | 59.5% | 78% |
| FND del modelo, δ recalibrado (en muestra) | **1.0015** | 3.24% | 18.8% | 17% |
| FND del modelo, δ recalibrado (**fuera de muestra**) | 1.0063 | 4.26% | 26.3% | 28% |

La validación fuera de muestra ajusta δ dejando un mes fuera y lo prueba en ese mes; es la única cifra que no se
juzga a sí misma. Leída con honestidad:

- **El sesgo desaparece.** De +9.3% a +0.6% fuera de muestra. Eso es lo que se pedía arreglar y queda arreglado.
- **δ es estable.** La dispersión de δ entre los cuatro ajustes deja-un-mes-fuera es 0.016 en promedio: el parámetro
  no se está reajustando a cada mes, describe algo real de la cartera.
- **Pero no le gana al legado en precisión mensual.** Fuera de muestra empata (4.26% contra 4.13%). El modelo
  recalibrado queda **al nivel** del FND de siempre, con menos sesgo agregado; no por encima. Los peores casos son
  Agro y Vida en 202602, los ramos chicos del primer mes de la ventana.

Con cuatro meses de un solo año no da para más. La conclusión defendible es que el FND del modelo, **con δ
recalibrado**, ya es utilizable y equivalente al legado — no que lo mejore.

### Qué hacer

1. **Sustituir `delta_calibrado.json` por `delta_recalibrado.json`.** El reforecast **no cambia**: sigue aplicando
   `clip(NT(k) − δ_ramo, 0, 1)`. Es el único cambio necesario, y es de datos, no de código.
2. **Con `USAR_FND_CALIBRADO = True` sólo después de sustituir el JSON.** Con el δ viejo el reforecast sobreestima
   +9.3% sin CAT; con el nuevo queda en +0.2%.
3. **Reajustar en cada cierre**, agregando los `ConsultaPPTO_RRC_<mes>_tradicional.xlsx` nuevos a la carpeta del
   script. Con más meses la validación fuera de muestra se vuelve concluyente y se podrá decir si el modelo mejora
   al legado o sólo lo iguala.
4. **No hace falta meter el escalonamiento por frecuencia.** Se probó la variante `NT(k) − δ_M4(frecuencia) − δ_ramo`
   y empata con la plana (EAM 0.27% contra 0.29%), porque el δ por ramo vuelve a absorber la mezcla. La plana no
   requiere tocar el reforecast, así que se queda. *(Esto corrige la recomendación anterior de esta sección.)*

Sobre la mezcla de frecuencias: medida en los archivos del propio reforecast es 41.7% trimestral, 52.0% mensual
(`1` + `NA`), 5.0% anual y 1.3% semestral, lo que da un δ_M4 medio de **0.0594**. La tabla que traía antes esta
sección estimaba δ_M4 de 0.24–0.33 a partir de la BD histórica; la estimación buena es la del archivo del
reforecast, que es la cartera sobre la que efectivamente se aplica. El 100% de la prima cae dentro del catálogo de
`xPND`, así que el legado no está anulando prima por frecuencias fuera de tabla.

### Lo que sí es un problema grande y no es del FND

**CAT (ramos 71 y 73) queda 40.6% por debajo de la RRC real, y δ no puede tocarlo:** el 100% de su prima queda fuera
de la jerarquía de `PORC_ND` (ramo 71/73 o TipoRea 2), así que el ajuste no la mueve ni un peso. Falla idéntico en
las tres opciones (razón 0.594 en las tres), o sea que es previo al cambio de FND y el modelo no lo causa ni lo
empeora. Y **se está deteriorando rápido dentro del propio 2026**:

| mes de valuación | 202602 | 202603 | 202604 | 202605 |
|---|---|---|---|---|
| CAT reforecast / CAT real | 0.767 | 0.659 | 0.516 | 0.425 |

En el banco de validación CAT sí cuadra (razón 0.946 contra la RRC real), lo que apunta a que la consulta del
reforecast deja fuera prima CAT que sí está en la base del MEC. Son unos 48 M USD en estos cuatro meses y va en
aumento: es la desviación más grande que queda y merece atacarse aparte.

## Hallazgos colaterales que conviene revisar

- **Filtro de año de suscripción en `reforecastRRC_v10_Esc1_ocl.py`.** La consulta a Gonzalo excluye la prima positiva registrada en un año calendario posterior al de suscripción (`Val(left(aPog_MesProc,4)) <= Susc`). Reproducido con año de suscripción ≈ año de inicio de vigencia, ese filtro deja el modelo en el 29% de la RRC real (variante `NT_reg_susc` del Excel). Es un candidato fuerte a la desviación considerable contra la Nota Técnica que motivó este trabajo; hay que verificarlo con el campo Susc real de SIREC, que la BD del MEC no trae.
- **Fecha de corte en la integración del MEC.** `factor_no_devengado` y `fnd_exacto` en `mec_devengamiento.py` usan `CALMONTH` del registro como corte. En el reforecast, CALMONTH es el mes de registro (`aPog_MesProc`), no la fecha de valuación; el corte debe ser `Meses` / `zFechaValuacion`.
- **Nombres de ramo cruzados en `generar output mec.py`.** `NOMBRE_RAMO` etiqueta 40 = Automóviles, 50 = Diversos, 90 = MyT y 110 = RC; el ER real y el script RRC (`xNoRamo`) indican 40 = RC, 50 = MyT, 90 = Autos y 110 = Diversos. Sólo afecta etiquetas del output.
- **Cola del vector en `TablaFND.factor`.** Para antigüedades mayores al horizonte devuelve el último valor del vector (4.3% en Vida con horizonte 24) en lugar de cero.
- **Índices CAT en HParametros.** El "Ind Sin RRC" de TEV e Hidro antes de 2024 está en otra base (0.5 a 8.6 frente a 0.11 a 0.27 desde 2024). Aquí se sustituyó por el primer valor de 2024; el índice implícito BEL / PND del modelo calibrado para CAT es estable, lo que confirma que el problema es del índice y no del devengamiento.
- **Vida, AyE, Autos, RC y Agro** tienen ratios mensuales más volátiles (MAPE 8–17%); su peso conjunto en la RRC es 19%. Vida crece rápido (BEL de 18 M USD en dic-24 a 68 M en may-26) y conviene vigilar su δ en el próximo cierre.

## Supuestos y límites

- La BD del MEC no trae fecha fin de vigencia ni frecuencia de cuentas por registro; para el no proporcional se usa la curva PF+ de cartera por antigüedad de cohorte como proxy de la prorrata exacta, y para el proporcional la frecuencia se absorbe en δ.
- AyE agrupa 30/31/34/35/37/39 y CAT agrupa 71/73 (la BD del MEC trae 30 y 70). El IS efectivo de cada grupo es BEL / Σ(BEL_sub / IS_sub).
- TC 2022–2026 de la base BEL-IRR-MR; 2019–2021 promedios Banxico aproximados, que sólo afectan reservas anteriores a 2023.
- Ventana de reporte 202301–202605; 2022 se usa como rampa (la BD del MEC empieza en 201901).

## Archivos

| Archivo | Contenido |
|---|---|
| `preparar_insumos.py` | construye `insumos/` a partir de los archivos crudos (`BD_ BEL - IRR - MR.xlsx`, `Input_MEC_Devengamiento.xlsx`, `Registros_Vigencia_MEC.csv`, Integración Dim opcional) que estén en la misma carpeta |
| `validar_prima_devengada.py` | motor de reconstrucción, comparación y calibración; genera todo lo de `salidas/` |
| `verificar_excel_formulas.py` | recalcula el Excel con LibreOffice y comprueba que las fórmulas de la hoja Mensual reproducen los valores de Python |
| `evaluar_frecuencia_fnd.py` | contrasta δ por ramo contra δ por frecuencia (regla M4) contra las dos juntas |
| `recalibrar_delta_reforecast.py` | reajusta δ sobre la base de prima del reforecast, a partir de sus propios `ConsultaPPTO_RRC_<mes>_tradicional.xlsx`; detecta si la corrida es del modelo o del legado, reconstruye el legado para comparar en la misma base, y valida fuera de muestra |
| `fnd_calibrado.py` | tabla FND calibrada y funciones de integración para RRC / SONR |
| `insumos/` | prima por ramo × cohorte × mes de registro (BD del MEC), saldos RRC reales, IS por ramo × mes, TC, vectores PF+ (horizonte 72), primas del ER real, vigencias del MEC |
| `salidas/Validacion_Prima_Devengada.xlsx` | Resumen, Formulas, Graficas, PD anual por ramo, ajuste PND, calibración, tabla FND, detalle mensual, parámetros reales, supuestos |
| `salidas/*.csv`, `delta_calibrado.json` | mismas tablas en texto plano |
| `salidas/delta_recalibrado.json` | **el δ por ramo ajustado sobre la base del reforecast**: el que hay que poner en Documents para correr el reforecast con `USAR_FND_CALIBRADO = True` |
| `salidas/comparacion_tres_opciones.csv`, `validacion_fuera_de_muestra.csv`, `recalibracion_reforecast.csv` | legado / modelo / δ recalibrado en la misma base, y la validación deja-un-mes-fuera |
| `scripts_actualizados/` | los scripts del MEC y de reservas ya modificados, con sus diffs, el comparador de outputs y `LEEME_carpeta_local.md` (qué archivo va en la carpeta local para correr cada paso) |
| `input_mec_2026/` | input del MEC 2026: real enero–julio + FCST agosto–diciembre, con su `LEEME.md` |

Correr, desde una carpeta que tenga los archivos crudos: `python preparar_insumos.py` y luego `python validar_prima_devengada.py` (pandas, numpy, openpyxl). Los dos scripts se anclan a su propia carpeta.

## Cómo leer el Excel

- `Año` es el **año contable**: el mes de valuación de la RRC en la base BEL-IRR-MR (`PERIODO // 100`), es decir el mes en que el movimiento entra a los libros. No es el año de suscripción. `PERIODO` es el mes contable en formato AAAAMM.
- Las columnas **azules** son la prima no devengada real (`PND_real`) y la del modelo calibrado con la que se compara (`PND_CAL`).
- Las columnas **ámbar** de la hoja Mensual son fórmulas vivas de Excel, para auditar celda por celda cómo sale la prima devengada: `PR = PE × (1 − ces)`; `BRUTO_CAL = PND_CAL × IS_eff × (1 + g + mr)`; `NETO_CAL = BRUTO_CAL − PND_CAL × IS_eff × c`; `dBRUTO` y `dNETO` son la variación mes a mes dentro del mismo grupo; `PD_tom = PE − dBRUTO` y `PD_ret = PR − dNETO`, tanto para el real como para el modelo. Cada encabezado trae la fórmula en un comentario y la hoja `Formulas` las lista todas. Las verifica `verificar_excel_formulas.py` (diferencia máxima 5e-7 USD contra Python).
