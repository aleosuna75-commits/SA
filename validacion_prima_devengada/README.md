# Validación del FND (MEC) contra la prima devengada real

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

## Conclusión

**El MEC v2 tal como está publicado (FND por prorrata de vigencias, indexado desde el inicio de vigencia) no cuadra con la prima devengada real: reproduce sólo el 22% de la RRC real y sobreestima la prima devengada tomada entre 2.6% y 8.4% al año.** La RRC real (base BEL-IRR-MR) devenga la prima proporcional y facultativa por **antigüedad de registro** con la recta de la Nota Técnica, y cerca del 69% de la prima de Patria se registra en un año calendario posterior al de su inicio de vigencia, así que "antigüedad desde la vigencia" y "antigüedad desde el registro" son dos mundos distintos.

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

Razón Σ prima no devengada modelo / real y error absoluto medio mensual, 202301–202605 (CAT desde 202401):

| Ramo | Peso en RRC | NT por registro (mensual) | NT por registro (trimestral) | MEC publicado (cohorte vigencia) | **Calibrado δ** | MAPE calibrado |
|---|---|---|---|---|---|---|
| Incendio | 32% | 0.997 | 0.868 | 0.164 | **0.997** | 2.4% |
| CAT (71+73) | 32% | 0.950 | 0.842 | 0.253 | **1.003** | 5.2% |
| MyT | 10% | 0.987 | 0.846 | 0.145 | **1.005** | 5.2% |
| Diversos | 8% | 1.006 | 0.859 | 0.117 | **1.006** | 5.1% |
| Vida | 7% | 1.161 | 1.065 | 0.423 | **1.016** | 10.1% |
| AyE | 4% | 1.100 | 0.985 | 0.350 | **1.018** | 17.1% |
| RC | 3% | 0.989 | 0.857 | 0.145 | **0.989** | 9.8% |
| Autos | 3% | 1.082 | 0.980 | 0.446 | **0.921** | 16.0% |
| Agro | 2% | 1.186 | 1.008 | 0.179 | **0.968** | 8.5% |
| Crédito | 1% | 0.866 | 0.740 | 0.071 | **0.995** | 8.7% |
| **Total** | | **0.993** | 0.871 | **0.218** | **0.989** | **3.1%** |

Prima devengada del total de la cartera (USD), real vs modelo:

| Año | Prima emitida | PD tomada real | PD tomada calibrado | error | PD tomada MEC publicado | error | PD retenida real | PD retenida calibrado | error |
|---|---|---|---|---|---|---|---|---|---|
| 2023 | 647.8 M | 599.9 M | 586.0 M | −2.3% | 639.1 M | +6.5% | 476.0 M | 464.4 M | −2.4% |
| 2024 | 795.1 M | 730.3 M | 740.5 M | +1.4% | 791.2 M | +8.4% | 564.7 M | 574.3 M | +1.7% |
| 2025 | 1,013.7 M | 962.2 M | 969.4 M | +0.7% | 998.3 M | +3.8% | 695.2 M | 700.5 M | +0.8% |
| 2026 ene–may | 481.5 M | 445.6 M | 451.0 M | +1.2% | 457.3 M | +2.6% | 337.3 M | 339.9 M | +0.8% |

En MXN, 2025: prima devengada tomada real 18,375 M vs calibrado 18,539 M (+0.9%) vs MEC publicado 19,060 M (+3.7%); retenida real 13,278 M vs calibrado 13,403 M (+0.9%).

Saldo al 202605 (USD): RRC bruta real 370.4 M, calibrado 360.3 M (−2.7%), MEC publicado 88.1 M (−76%). RRC neta real 247.8 M, calibrado 241.6 M, MEC publicado 54.5 M. Adoptar el MEC publicado liberaría del orden de 280 M USD (≈ 4,900 M MXN) de reserva bruta.

## Por qué el MEC publicado no cuadra

1. En la BD del MEC, la prima se registra con mucho rezago respecto a su vigencia: 8% en el mes de inicio, 14% entre 6 y 8 meses después, 17% entre 9 y 11, 28% entre 12 y 17 y 20% a 18 meses o más. El 69% de la prima (79% del proporcional) se registra en un año calendario posterior al de inicio de vigencia.
2. El MEC v2 asigna a esa prima el FND de su cohorte de vigencia, que ya es cero o casi cero cuando se registra. La RRC real, en cambio, la devenga como riesgo nuevo desde el mes de registro (recta de 24-avos de la Nota Técnica). Es la misma lógica de `xPND[CALMONTH]` de los reforecast, y los datos lo confirman: para Incendio, MyT, Diversos y RC la NT mensual por registro reproduce la RRC real con δ = 0.
3. La prorrata exacta por fechas sí es la regla correcta para el no proporcional (TipoRea 2), que es donde el reforecast ya la aplica.

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

## El δ calibrado NO transfiere al reforecast — no adoptar el FND del modelo todavía

**Corrección importante a lo que decía antes esta sección.** Al correr el reforecast RRC con el FND del modelo y
contrastar contra la RRC real, el modelo queda peor que el FND de siempre. Es un resultado medido, no una sospecha:

| Prima no devengada, 202601–202605, USD | Total | Sin CAT | Sólo CAT |
|---|---|---|---|
| RRC **real** | 2,750 M | 1,907 M | 843 M |
| Reforecast con el FND **legado** | 2,454 M (−10.8%) | **1,936 M (+1.5%)** | 518 M (−38.6%) |
| Reforecast con el FND **del modelo** | 2,644 M (−3.8%) | **2,088 M (+9.5%)** | 557 M (−34.0%) |

Sobre el BEL en escenario 2 el error absoluto medio por ramo × mes pasa de **9.1%** (legado) a **17.5%** (modelo), y el
legado gana en 11 de 13 ramos.

### Por qué

δ se calibró para que `Σ prima_BD-MEC × FND ≈ PND_real`. El reforecast aplica ese δ sobre **otra base de prima**: la
consulta a BD Gonzalo, con sus propios filtros (ventana de `aPog_MesProc`, el candado de año de suscripción, exclusión
de `LlavesPol`). Con el **mismo** FND del modelo, esa base produce alrededor de **10% más** prima no devengada que la
base del MEC. El δ absorbe el nivel de una base y se aplica a otra, así que sobreestima.

El FND legado no tiene ese problema porque nunca se calibró fuera: es `NT(k) − δ_M4(frecuencia)`, y su escalonamiento
por periodicidad de la cuenta actúa justo como la reducción que esa base más grande necesita. Se ve en el δ que haría
cuadrar cada ramo dentro del reforecast, comparado con el δ_M4 que implica su mezcla de frecuencias:

| Ramo | δ actual | δ_M4 de su mezcla | δ que haría cuadrar |
|---|---|---|---|
| Incendio | 0.000 | 0.241 | 0.271 |
| Diversos | 0.000 | 0.261 | 0.336 |
| MyT | −0.010 | 0.239 | 0.215 |
| AyE | +0.045 | 0.334 | 0.227 |
| Autos | +0.130 | 0.322 | 0.318 |
| Vida | +0.070 | 0.069 | 0.069 |

El δ necesario cae encima del δ_M4 de la frecuencia. Es decir: **dentro del reforecast, la respuesta correcta es
básicamente lo que el FND legado ya hace.** Vida lo confirma por el otro lado: es 75% cuentas mensuales, su δ_M4 es
0.069, su δ calibrado 0.070 y el necesario 0.069 — ahí sí transfiere, porque no hay escalonamiento que perder.

### Sobre la frecuencia

La sección anterior concluía que la frecuencia no aportaba. Esa conclusión tenía un error de dato: `Meses Periodo = 0`
en la BD del MEC es el código de cuenta **anual** (columna `'0'` de xPND, δ_M4 = 0.452), y se estaba leyendo como
mensual. Con el mapeo correcto la mezcla real de la cartera proporcional es del orden de 48–76% anual, no 59% mensual.

Rehecha con el mapeo bueno, la comparación **sobre la base del MEC** sigue dando lo mismo: la variante «M4 por
frecuencia + δ residual» empata con «δ por ramo» (razón 1.00 contra 1.00, MAPE 8.99% contra 8.89%) porque el δ residual
vuelve a cancelar el escalonamiento. Lo que cambia es la lectura: esa cancelación es un artefacto de esa base de prima,
y no sobrevive al cambio de base. Reproducible con `evaluar_frecuencia_fnd.py`.

### Qué hacer

1. **No adoptar el FND del modelo en producción todavía.** Dejar `USAR_FND_CALIBRADO = False` hasta recalibrar.
2. **Recalibrar δ sobre la base de prima del propio reforecast**, no sobre la del MEC. Para eso está
   `recalibrar_delta_reforecast.py`: pon en su carpeta dos o tres `ConsultaPPTO_RRC_<mes>_tradicional.xlsx` (los
   escribe el propio reforecast en `Documents\Outputs`), más `insumos\` y `mec_devengamiento.py`, y córrelo. Ajusta δ
   por ramo contra el BEL real en dos variantes —escalonada por frecuencia y plana— y escribe `delta_recalibrado.json`.
   Respeta la jerarquía de `PORC_ND`: deja fuera del ajuste los ramos 71/73 y el no proporcional. Probado contra un caso
   sintético con δ conocido: lo recupera al milésimo.
3. Al recalibrar, **conservar el escalonamiento por frecuencia** (`FND = NT(k) − δ_M4(frecuencia) − δ_ramo`): la
   evidencia de arriba dice que dentro del reforecast es necesario.

### Lo que sí es un problema grande y no es nuestro

**CAT (ramos 71 y 73) queda 38.6% por debajo de la RRC real en la corrida legada y 34.0% en la del modelo** — unos
325 M USD. Falla en las dos, así que es previo al cambio de FND y no lo causa el modelo. En el banco de validación, en
cambio, CAT cuadra (razón 0.946 contra la RRC real), lo que apunta a que la consulta del reforecast deja fuera prima
CAT que sí está en la base del MEC. Vale la pena atacarlo: es la desviación más grande de todo el reporte.

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
| `recalibrar_delta_reforecast.py` | reajusta δ sobre la base de prima del reforecast, a partir de sus propios `ConsultaPPTO_RRC_<mes>_tradicional.xlsx` |
| `fnd_calibrado.py` | tabla FND calibrada y funciones de integración para RRC / SONR |
| `insumos/` | prima por ramo × cohorte × mes de registro (BD del MEC), saldos RRC reales, IS por ramo × mes, TC, vectores PF+ (horizonte 72), primas del ER real, vigencias del MEC |
| `salidas/Validacion_Prima_Devengada.xlsx` | Resumen, Formulas, Graficas, PD anual por ramo, ajuste PND, calibración, tabla FND, detalle mensual, parámetros reales, supuestos |
| `salidas/*.csv`, `delta_calibrado.json` | mismas tablas en texto plano |
| `scripts_actualizados/` | los scripts del MEC y de reservas ya modificados, con sus diffs, el comparador de outputs y `LEEME_carpeta_local.md` (qué archivo va en la carpeta local para correr cada paso) |
| `input_mec_2026/` | input del MEC 2026: real enero–julio + FCST agosto–diciembre, con su `LEEME.md` |

Correr, desde una carpeta que tenga los archivos crudos: `python preparar_insumos.py` y luego `python validar_prima_devengada.py` (pandas, numpy, openpyxl). Los dos scripts se anclan a su propia carpeta.

## Cómo leer el Excel

- `Año` es el **año contable**: el mes de valuación de la RRC en la base BEL-IRR-MR (`PERIODO // 100`), es decir el mes en que el movimiento entra a los libros. No es el año de suscripción. `PERIODO` es el mes contable en formato AAAAMM.
- Las columnas **azules** son la prima no devengada real (`PND_real`) y la del modelo calibrado con la que se compara (`PND_CAL`).
- Las columnas **ámbar** de la hoja Mensual son fórmulas vivas de Excel, para auditar celda por celda cómo sale la prima devengada: `PR = PE × (1 − ces)`; `BRUTO_CAL = PND_CAL × IS_eff × (1 + g + mr)`; `NETO_CAL = BRUTO_CAL − PND_CAL × IS_eff × c`; `dBRUTO` y `dNETO` son la variación mes a mes dentro del mismo grupo; `PD_tom = PE − dBRUTO` y `PD_ret = PR − dNETO`, tanto para el real como para el modelo. Cada encabezado trae la fórmula en un comentario y la hoja `Formulas` las lista todas. Las verifica `verificar_excel_formulas.py` (diferencia máxima 5e-7 USD contra Python).
