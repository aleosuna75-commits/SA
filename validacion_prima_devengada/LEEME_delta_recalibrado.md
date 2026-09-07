# δ recalibrado — el FND del modelo ya cuadra en el reforecast

Planeación Financiera (BP&A) · Reaseguradora Patria · septiembre 2026

## Lo que había que arreglar

Tenías razón en que el problema estaba en nuestro FND, y en que había que atacarlo por los ramos que "no se
deberían mover". Ahí estaba la pista: **Incendio tiene δ = 0.000 y aun así subía +10.8%.** Si δ es cero, el FND del
modelo es exactamente la recta de la Nota Técnica; que aun así se moviera significa que el problema no era el
número de δ de cada ramo, sino que **δ se calibró contra una base de prima y se aplicó a otra**.

δ se ajustó para que `Σ prima_del_MEC × FND ≈ prima no devengada real`. El reforecast aplica ese δ sobre la prima
que sale de su propia consulta, que con el **mismo** FND produce **+6.2% más BEL** (+9.9% sin CAT). Las cuentas
cierran exactamente:

    1.0499 (modelo/real en el reforecast) = 0.9886 (modelo/real en el banco) × 1.0620 (brecha de base)

Sin esa brecha el modelo daría −1.1% en el reforecast, no +5.0%. La brecha explica la desviación entera.

No es que la consulta lea otra prima: lee el **mismo** `BDReal26.xlsx`, y la prima registrada coincide ramo por
ramo (481.47 contra 481.49 M USD). La diferencia está en lo que la consulta le hace: la valúa al TC del mes de
**valuación** en vez del de **registro** (eso solo son +2.0 de los +6.2 puntos), arma `MONTO_PI` sumando tres
columnas, aplica el candado de año de suscripción, excluye `LlavesPol` y prorratea el no proporcional por fechas
exactas. Y no afecta igual a todos los ramos: va de +2.8% en Vida a +26.9% en Diversos. Por eso ningún δ ajustado
fuera del reforecast podía aterrizar bien dentro.

## Lo que hay que hacer: cambiar un archivo, nada de código

**Sustituye `delta_calibrado.json` en tu carpeta de Documents por el que viene aquí.** El reforecast no cambia:
sigue aplicando `clip(NT(k) − δ_ramo, 0, 1)`. Sólo cambian los números de δ. Tu copia anterior está en
`soporte\delta_calibrado_ANTERIOR.json` por si quieres volver atrás.

| Ramo | δ anterior | **δ nuevo** | peso en el BEL real (sin CAT) |
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
| CAT | −0.035 | sin cambio | δ no lo mueve (ver abajo) |

Después de sustituirlo puedes dejar `USAR_FND_CALIBRADO = True`. **Antes de sustituirlo, no**: con el δ viejo el
reforecast sobreestima +9.3% sin CAT.

## Qué tan bien queda

Las tres opciones sobre **la misma base y la misma ventana** (202602–202605, BEL riesgo en USD, 36 pares
ramo × mes, sin CAT). El legado se reconstruye sobre tus propios archivos con la regla M4 del MEC:

| | razón BEL/real | error medio por ramo × mes | peor caso |
|---|---|---|---|
| FND legado | 1.0184 | 4.13% | 32.9% |
| FND del modelo, δ anterior | 1.0927 | 15.45% | 59.5% |
| FND del modelo, δ nuevo (en muestra) | **1.0015** | 3.24% | 18.8% |
| FND del modelo, δ nuevo (**fuera de muestra**) | 1.0063 | 4.26% | 26.3% |

La última línea es la que importa: ajusta δ dejando un mes fuera y lo prueba **en** ese mes, así que no se juzga a
sí misma. Dicho sin adornos:

- **El sesgo desaparece**, que es lo que se pedía: de +9.3% a +0.6%.
- **δ es estable**: entre los cuatro ajustes deja-un-mes-fuera se mueve 0.016 en promedio. No se está reajustando a
  cada mes, describe algo real de la cartera.
- **Pero no le gana al legado en precisión mensual**: fuera de muestra empatan (4.26% contra 4.13%). El FND del
  modelo con δ nuevo queda **al nivel** del de siempre, con menos sesgo agregado. No por encima.

Con cuatro meses de un solo año no da para más. Si en el próximo cierre agregas los `ConsultaPPTO_RRC` nuevos a la
carpeta del script y lo vuelves a correr, la validación fuera de muestra se vuelve concluyente.

Una confirmación que da confianza: estos δ nuevos caen casi encima del desplazamiento que **el FND legado ya
aplicaba de hecho**, despejado por un camino completamente distinto — Incendio 0.050 contra 0.047, MyT 0.030 contra
0.038, Vida 0.055 contra 0.043, Autos 0.315 contra 0.356. Dos métodos independientes dan lo mismo.

## Lo que esto NO arregla: CAT

**CAT (ramos 71 y 73) está 40.6% por debajo de la RRC real, y δ no puede tocarlo.** El 100% de su prima queda
fuera de la jerarquía de `PORC_ND` (ramo 71/73 o TipoRea 2), así que el ajuste no la mueve ni un peso: da 0.594
con el δ viejo, con el nuevo y con el legado, idéntico en los tres. Es previo al cambio de FND; el modelo ni lo
causa ni lo empeora. Y se está deteriorando dentro de 2026:

| mes de valuación | 202602 | 202603 | 202604 | 202605 |
|---|---|---|---|---|
| CAT reforecast / CAT real | 0.767 | 0.659 | 0.516 | 0.425 |

En el banco de validación CAT sí cuadra (0.946 contra la RRC real), lo que apunta a que la consulta del reforecast
deja fuera prima CAT que sí está en la base del MEC. Son unos 48 M USD en estos cuatro meses y va en aumento: es la
desviación más grande que queda y hay que atacarla aparte de todo esto.

## Cómo lo reproduces / lo repites el próximo cierre

En una carpeta cualquiera pon: `recalibrar_delta_reforecast.py`, `soporte\mec_devengamiento.py`, `insumos\`, el
`delta_calibrado.json` con el que corriste, y **los `ConsultaPPTO_RRC_<mes>_tradicional.xlsx` que quieras usar**
(los escribe el propio reforecast en `Documents\Outputs`; el número del nombre es el mes de valuación). Luego:

    python recalibrar_delta_reforecast.py

El script detecta solo si la corrida es del modelo o del legado, reconstruye el legado para comparar en la misma
base, ajusta δ, valida fuera de muestra y escribe `delta_recalibrado.json`. En `soporte\` van las tablas de arriba
en CSV.

Dos detalles que resuelve solo, por si los ves en pantalla:

- **El BEL del archivo viene negativo.** `MONTO_PI` es negativo, así que `MONTO_PI × BELMEDIA × PORC_ND ×
  TC_Valuación` reproduce exacto tu columna `BELRIESGO2026_TCVal`, que también lo es. Es convenio de signo del
  archivo: se voltea el agregado completo (nunca fila por fila, eso destruiría las contrapartidas legítimas). El
  script imprime un control contra tu propia columna; sale 1.4e-16.
- **Las cuentas `NA` llegan vacías.** El viaje a Excel convierte la cadena `'NA'` de `FRECUENCIA` en celda vacía;
  se remapean a `'NA'`, que sí está en el catálogo de `xPND`. Con eso, **el 100% de tu prima cae dentro del
  catálogo**: el legado no está anulando prima por frecuencias fuera de tabla.
