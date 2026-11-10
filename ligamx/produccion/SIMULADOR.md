# Simulador de tabla, liguilla y campeón, sellos y exportación

Archivos: `produccion/simulador.py`, `produccion/sellos.py`, `produccion/exportar.py`, pruebas en
`produccion/pruebas/test_simulador.py` (20 pruebas) y el contrato del JSON en `salidas/CONTRATO.md`.
Todo consume sólo el contrato del `Pronosticador` (`equipos`, `partidos(df)`, `malla(n, fase, semilla)`,
`fuerzas()`), así que funciona igual con el campeón (`modelo/campeon.json`, hoy `ajuste`) que con el
provisional.

    cd /home/user/SA/ligamx
    python3 -m produccion.exportar                 # TODO: sella, califica, simula y escribe salidas/actual.json (17 s)
    python3 -m produccion.exportar --corte 2026-10-30T00:00   # corrida retrospectiva (no sella ni pisa actual.json)
    python3 -m produccion.simulador                # sólo la simulación, a pantalla
    python3 -m produccion.simulador --calibrar [--modelo ajuste --rho -0.0574]   # calibración histórica de series
    python3 -m produccion.sellos calificar         # recalcula salidas/desempeno.json
    python3 -m pytest produccion/pruebas/test_simulador.py -q

Para reevaluar después de cada partido basta volver a correr `python3 -m produccion.exportar` una vez
actualizado `datos/partidos.csv`.

## 1. Fase regular

Tabla real hasta el corte (de `partidos.csv`) más los partidos pendientes simulados. Las lambdas de
cada pendiente son las de `Pronosticador.partidos()` (con el contexto del partido); las muestras de la
malla se recentran en ellas (`malla[k] x lambda_partido / malla[0]`). Con `rho = 0` el marcador son dos
Poisson; con `rho != 0` se sortea de la matriz de Dixon-Coles de `arnes.matrices_marcadores`.

Orden de la tabla, con los criterios oficiales de `config/torneo.json` (`simulador.ordenar`):

| # | criterio | cómo se calcula | aproximación |
|---|---|---|---|
| 1 | puntos | 3 / 1 / 0 | ninguna |
| 2 | diferencia de goles | GF - GC | ninguna |
| 3 | goles a favor | | ninguna |
| 4 | goles de visitante con el mismo número de visitas | goles en las PRIMERAS 8 visitas de cada equipo (unos equipos visitan 8 veces y otros 9) | es la aproximación pedida de la nota del art. 25; el orden de las visitas es el cronológico real |
| 5 | Fair Play (menos es mejor) | `tarjetas.csv`, por jugador y partido: sólo amarilla 1; doble amarilla 3; roja directa 3; amarilla + roja directa 4 | no incluye sanciones de escritorio ni distingue al cuerpo técnico; los partidos simulados no suman tarjetas |
| 6 | cociente | puntos / partidos de fase regular desde el Apertura 2024, con el torneo en curso (y lo simulado) | sólo fase regular |
| 7 | sorteo | número al azar por simulación | en la tabla real mostrada, orden alfabético |

Comprobación: la tabla calculada coincide con `datos/tabla_apertura2026.csv` en las 18 filas (posición,
PJ, G, E, P, GF, GC, DG, PTS y desgloses de local y visita). El total de Fair Play coincide con un conteo
independiente. No se simula la resta de 3 puntos de la regla de menores (art. 49).

## 2. Liguilla

Ocho clasificados; cuartos 1-8, 2-7, 3-6, 4-5 a ida y vuelta, ida en casa del peor sembrado; con el
global empatado en cuartos y semifinales avanza el mejor sembrado; semifinales con RESIEMBRA (mejor
contra peor de los cuatro que quedan); final a ida y vuelta y, si el global queda empatado, tiempos
extra (lambdas de la vuelta x 1/3, sin corrección de Dixon-Coles) y penales a 50/50. Usa
`malla(fase="liguilla")`. `simulador.prob_serie` da además la probabilidad EXACTA de una serie (convolución
de las dos matrices de marcador; reglas `posicion`, `gol_visitante` y `final`), comprobada contra una
enumeración directa de los cuatro marcadores.

**Series reales.** Cuando la fase regular ya terminó y `partidos.csv` trae partidos de cuartos, semifinal
o final del torneo, se respeta lo jugado antes del corte: las piernas jugadas quedan fijas, las pendientes
se sortean con las lambdas de `Pronosticador.partidos()` (la localía real del calendario manda sobre la
regla) y una serie terminada fija a su ganador (en la final, con `gl_et`/`gv_et` y `pen_l`/`pen_v`). Cada
serie real sale con el pronóstico de sus piernas pendientes, la distribución del marcador global y
P(avanza) condicionada a la ida (`liguilla.series` en el JSON). Probado con escenarios construidos: ida
4-0 en contra del líder (su probabilidad de avanzar cae de más de 0.5 a menos de 0.2 y coincide con el
cálculo exacto), global empatado (pasa el mejor sembrado), cuadro completo con final en penales.

## 3. Incertidumbre y error de Monte Carlo

20,000 torneos repartidos en 2,000 muestras de parámetros (`malla(n)`, k >= 1; 10 torneos por muestra).
Tarda 4.2 s con el campeón (rho distinto de 0) y 0.4 s con el provisional. El error de Monte Carlo
(`ee_*`) se calcula entre muestras, así que incluye el ruido de haber sorteado parámetros; se comprobó
contra la dispersión entre 8 semillas (0.0024 observado vs 0.0037 informado para P(campeón) de América).
Con `n_muestras=0` se usa sólo la estimación puntual.

Efecto de propagar la incertidumbre (100,000 torneos, modelo `ajuste`, 10-nov-2026): aplana un poco a
los favoritos. América 0.2924 puntual -> 0.2816; Chivas 0.2240 -> 0.2192; Pachuca 0.0238 -> 0.0271;
Monterrey 0.0230 -> 0.0267 (ee de 0.0004 a 0.0017). Ese error NO incluye el error del modelo mismo.

## 4. Calibración histórica del cálculo de series (DESARROLLO, sin fuga)

`python3 -m produccion.simulador --calibrar` -> `salidas/calibracion_series.json`. 119 series a ida y
vuelta (68 de cuartos, 34 semifinales, 17 finales) de 17 torneos, Apertura 2016 a Clausura 2025. Lambdas
fuera de muestra de `modelo/pred/poisson_simple.parquet`; regla vigente en cada torneo (gol de visitante
de Apertura 2012 a Clausura 2021 en cuartos y semifinales, 54 series; posición en la tabla después, 48;
tiempos extra y penales en las 17 finales). La vuelta fue en casa del mejor sembrado en 119 de 119; 34
series (29%) terminaron con el global empatado a 90 minutos. Errores estándar por bootstrap de torneos
completos (2,000 réplicas). Referencias: frecuencia con que avanzó el mejor sembrado en las series
anteriores al torneo (desde el Apertura 2012) y 50/50.

El mejor sembrado avanzó en **67.2%** de las series (ee 4.8; IC 95% 58.0 a 76.5).

| pronóstico de P(avanza el mejor sembrado) | media | Brier (ee) | log-loss (ee) |
|---|---|---|---|
| simulador, antes de la serie | 0.606 | 0.2090 (0.0102) | 0.6084 (0.0223) |
| simulador estricto (las dos piernas con el ajuste previo a la ida) | 0.607 | 0.2115 (0.0103) | 0.6140 (0.0226) |
| frecuencia histórica previa | 0.623 | 0.2250 (0.0127) | 0.6426 (0.0260) |
| 50/50 | 0.500 | 0.2500 | 0.6931 |
| simulador, ya jugada la ida | 0.576 | 0.1845 (0.0202) | 0.5561 (0.0546) |

| comparación pareada | dif. Brier (ee; IC 95%) | dif. log-loss (ee) | lectura |
|---|---|---|---|
| simulador - 50/50 | -0.0410 (0.0102; -0.061 a -0.022) | -0.0847 (0.0223) | gana con claridad (4.0 ee) |
| simulador - frecuencia previa | -0.0160 (0.0110; -0.038 a +0.005) | -0.0342 (0.0232) | mejor, pero NO concluyente (1.5 ee) |
| estricto - frecuencia previa | -0.0135 (0.0111; -0.036 a +0.007) | -0.0287 (0.0234) | NO concluyente (1.2 ee) |
| estricto - simulador | +0.0025 (0.0005) | +0.0055 (0.0011) | la vuelta guardada ya conocía la ida; el estricto es la cifra limpia |
| tras la ida - frecuencia previa | -0.0405 (0.0181; -0.075 a -0.004) | -0.0865 (0.0504) | 2.2 ee en Brier |

**Dicho con franqueza:** el cálculo de series le gana sin duda a la moneda al aire, pero con 119 series
no se puede afirmar que le gane a la simple frecuencia histórica «el mejor sembrado avanza 62%»: la
ventaja medida (0.014 a 0.016 de Brier) es de 1.2 a 1.5 errores estándar. Lo que sí aporta es
discriminar entre series (pendiente de calibración 1.02) y actualizarse con la ida.

Tabla de calibración (cuartiles de la probabilidad pronosticada antes de la serie):

| rango pronosticado | n | media pronosticada | avanzó el mejor (ee) |
|---|---|---|---|
| 0.31 a 0.50 | 30 | 0.433 | 0.367 (0.088) |
| 0.51 a 0.61 | 30 | 0.570 | 0.733 (0.081) |
| 0.62 a 0.71 | 29 | 0.661 | 0.793 (0.075) |
| 0.71 a 0.87 | 30 | 0.764 | 0.800 (0.073) |

Por fase: cuartos 0.628 pronosticado vs 0.676 observado (n 68); semifinal 0.610 vs 0.706 (n 34); final
0.511 vs 0.588 (n 17).

**Sesgo a favor del peor sembrado.** El simulador subestima al mejor sembrado: +6.6 puntos antes de la
serie (ee 4.8; IC -2.5 a +15.4, no significativo) y **+9.7 puntos ya jugada la ida (ee 3.5; IC +2.8 a
+16.2; 2.7 ee)**. Es decir, el que cierra en casa remonta o aguanta más de lo que dicen dos partidos
independientes. Ensayo exploratorio: multiplicar en la vuelta la lambda del local por f y dividir la del
visitante entre f; eligiendo f con los demás torneos (dejando uno fuera) sale f de 1.25 a 1.35, el sesgo
tras la ida baja a -1.0 puntos y el Brier tras la ida mejora 0.0097 (ee 0.0086; 1.1 ee), pero antes de la
serie no mejora (+0.0005, ee 0.0104). No alcanza 2 errores estándar: **no se incorporó**. Queda como
candidato para `malla(fase="liguilla")` del modelo.

**Con el modelo campeón** (`ajuste`, `salidas/calibracion_series_ajuste.json`, rho -0.0574 fijo; con
rho 0 da lo mismo a la tercera cifra): Brier 0.2078 (ee 0.0091) contra 0.2250 de la frecuencia previa:
-0.0172 (ee 0.0106; 1.6 ee) y -0.0422 contra 50/50 (ee 0.0091; 4.6 ee). Misma conclusión y mismo sesgo
(+6.4 puntos antes de la serie, ee 4.9; +9.9 tras la ida, ee 3.7).

### ¿Hay menos goles o distinta ventaja de local en liguilla?

Partidos de DESARROLLO contra lo que esperaban las lambdas de `poisson_simple` (residuo = observado menos
esperado, por partido; ee por bootstrap de bloques). Ventaja de local = goles del local menos goles del
visitante.

| grupo | n | goles obs. | goles esp. | residuo goles (ee) | residuo ventaja de local (ee) | empates obs. / esp. |
|---|---|---|---|---|---|---|
| fase regular | 2,707 | 2.668 | 2.644 | +0.024 (0.030) | -0.009 (0.030) | 26.5% / 25.0% |
| liguilla (cuartos a final) | 238 | 2.546 | 2.573 | -0.027 (0.100) | +0.164 (0.100) | 28.6% / 25.7% |
| idas | 119 | 2.454 | 2.552 | -0.099 (0.140) | +0.179 (0.136) | 32.8% / 26.2% |
| vueltas | 119 | 2.639 | 2.593 | +0.045 (0.146) | +0.148 (0.144) | 24.4% / 25.2% |
| cuartos | 136 | 2.721 | 2.606 | +0.115 (0.112) | +0.122 (0.125) | 27.9% / 25.4% |
| semifinales | 68 | 2.412 | 2.539 | -0.127 (0.226) | +0.349 (0.234) | 20.6% / 26.0% |
| finales | 34 | 2.118 | 2.509 | -0.391 (0.261) | -0.039 (0.183) | 47.1% / 26.3% |

Lectura: ninguna diferencia llega a 2 errores estándar. En conjunto la liguilla NO tiene menos goles de
los esperados (-0.03, ee 0.10). Hay indicios, no pruebas, de (a) más ventaja de local que en fase regular
(+0.16 goles, 1.6 ee; parecida en idas y vueltas), (b) finales más cerradas (-0.39 goles, 1.5 ee; 16
empates en 34 partidos) y (c) idas con algo menos de goles que las vueltas (2.45 vs 2.64; diferencia de
0.9 ee). Con el modelo `ajuste` las cifras son casi iguales (liguilla -0.056, ee 0.101; ventaja de local
+0.169, ee 0.100; finales -0.404, ee 0.260). Por eso el simulador NO aplica ningún ajuste propio de
liguilla: usa lo que entregue `malla(fase="liguilla")`.

## 5. Sellos y desempeño real

`salidas/sellos.jsonl` sólo crece. Cada corrida de `exportar` (sin `--corte`) agrega un sello por cada
uno de los próximos 20 partidos que no han empezado: id, `sellado_utc` (reloj del sistema: no se puede
sellar hacia atrás), modelo, lambdas, 1X2, pick, marcador probable y top 5, y las tres combinadas con sus
picks. Un sello idéntico al último del mismo partido no se repite. El sello OFICIAL de un partido es el
último anterior a su inicio. `sellos.calificar()` escribe `salidas/desempeno.json`: por partido y
acumulado (también por modelo y por torneo) acierto 1X2, marcador exacto, log-loss, Brier, RPS y, por
combinada, cuántos de los 4 picks pegaron y si pegó completa (los picks de mitades con `gl_ht`/`gv_ht`;
si falta el descanso quedan sin calificar).

Al 10-nov-2026 hay 22 sellos de 10 partidos (10 del modelo provisional a las 09:57 UTC y 12 de `ajuste`
desde las 10:03 UTC; los oficiales serán los últimos previos a cada partido) y 0 partidos calificados:
todavía no existe desempeño real hacia adelante.

## 6. Salida al 10-nov-2026, 04:12 (CDMX): modelo `ajuste`, 143 de 153 partidos jugados

20,000 torneos, semilla 20261110. Probabilidad de campeón (ee de Monte Carlo):

| Equipo | Lugar hoy | Pts hoy | Pts esperados | P(clasifica) | P(top 4) | P(semifinal) | P(final) | P(campeón) | ee |
|---|---|---|---|---|---|---|---|---|---|
| América | 2 | 30 | 31.4 | 1.000 | 1.000 | 0.801 | 0.502 | 0.2813 | 0.0037 |
| Chivas | 3 | 30 | 31.7 | 1.000 | 1.000 | 0.757 | 0.438 | 0.2226 | 0.0034 |
| Cruz Azul | 1 | 32 | 33.1 | 1.000 | 1.000 | 0.745 | 0.441 | 0.2109 | 0.0033 |
| Toluca | 4 | 27 | 28.2 | 1.000 | 0.591 | 0.760 | 0.372 | 0.2000 | 0.0033 |
| Pachuca | 8 | 22 | 23.5 | 0.455 | 0.000 | 0.154 | 0.058 | 0.0266 | 0.0012 |
| Monterrey | 10 | 21 | 24.0 | 0.454 | 0.000 | 0.158 | 0.058 | 0.0261 | 0.0012 |
| Atlas | 5 | 27 | 28.3 | 1.000 | 0.285 | 0.229 | 0.049 | 0.0116 | 0.0008 |
| Tijuana | 9 | 22 | 24.1 | 0.554 | 0.000 | 0.111 | 0.025 | 0.0062 | 0.0006 |
| Santos | 6 | 25 | 26.6 | 0.834 | 0.124 | 0.156 | 0.028 | 0.0060 | 0.0005 |
| León | 7 | 23 | 24.2 | 0.439 | 0.000 | 0.077 | 0.016 | 0.0044 | 0.0005 |
| Pumas | 11 | 21 | 22.4 | 0.110 | 0.000 | 0.029 | 0.008 | 0.0035 | 0.0004 |
| Querétaro | 12 | 20 | 22.6 | 0.154 | 0.000 | 0.024 | 0.004 | 0.0009 | 0.0002 |

Puebla, Atlético San Luis, Tigres, Atlante, Necaxa y Juárez ya no clasifican en ninguna simulación.
Líder de la fase regular: Cruz Azul 0.434, Chivas 0.296, América 0.270. Cinco equipos ya están
clasificados (Cruz Azul, América, Chivas, Toluca, Atlas); los otros tres boletos se reparten entre Santos
(0.834), Tijuana (0.554), Pachuca (0.455), Monterrey (0.454), León (0.439), Querétaro (0.154) y Pumas
(0.110).

Cruces de cuartos más probables (P del cruce; P de que avance el mejor sembrado si se da):

| llave | cruce | P(cruce) | P(avanza el mejor) |
|---|---|---|---|
| 1-8 | Cruz Azul - Tijuana | 0.135 | 0.792 |
| 1-8 | Chivas - Tijuana | 0.094 | 0.786 |
| 1-8 | Cruz Azul - Monterrey | 0.086 | 0.637 |
| 2-7 | Cruz Azul - Pachuca | 0.117 | 0.627 |
| 2-7 | América - Pachuca | 0.103 | 0.702 |
| 2-7 | Cruz Azul - Tijuana | 0.097 | 0.791 |
| 3-6 | América - Santos | 0.096 | 0.889 |
| 3-6 | Chivas - Santos | 0.094 | 0.855 |
| 3-6 | Chivas - León | 0.091 | 0.807 |
| 4-5 | Toluca - Atlas (Toluca cuarto) | 0.264 | 0.847 |
| 4-5 | Atlas - Toluca (Atlas cuarto) | 0.222 | 0.278 |
| 4-5 | Toluca - Santos | 0.111 | 0.864 |

Sin importar la llave: Toluca vs Atlas se da en 53% de las simulaciones (0.310 con Toluca mejor sembrado
y 0.222 con Atlas); Cruz Azul - Tijuana 0.233; Cruz Azul - Pachuca 0.185; América - Santos 0.179; Chivas -
Santos 0.175. El cuadro completo más probable (Cruz Azul, América, Chivas, Santos, Toluca, Atlas, Pachuca,
Tijuana en ese orden) sólo tiene probabilidad 0.012: el orden exacto sigue muy abierto. Finales más
probables: Cruz Azul - América 0.121, Cruz Azul - Toluca 0.102, América - Chivas 0.095, América - Toluca
0.094.

Con el modelo provisional (Poisson simple, corrida de las 03:57) el orden de favoritos era América 0.267,
Cruz Azul 0.234, Toluca 0.218, Chivas 0.185: el cambio de modelo mueve a Chivas del cuarto al segundo
lugar, señal de que entre los cuatro primeros las diferencias dependen del modelo.

## 7. Pruebas (`produccion/pruebas/test_simulador.py`, 20 pruebas, 25 s)

Desempates a mano (cada criterio decide cuando empatan los anteriores; Fair Play al revés) y por
simulación; Fair Play contra un conteo independiente; goles de visitante y cociente; la tabla calculada y
la simulada sin pendientes coinciden con `datos/tabla_apertura2026.csv`; las probabilidades de campeón
suman 1 (las de final 2, semifinal 4 y clasificar 8) y son monótonas; reproducible con semilla;
marcadores con y sin rho; `prob_serie` contra enumeración y casos a mano; serie real con la ida jugada;
cuadro completo con final en penales; regla por torneo; sellar y calificar (incluye que un sello tardío
no cuenta y que no se sella hacia atrás); picks a mano; etiquetas de jornada; `exportar` valida su propio
JSON (campos, probabilidades en [0, 1], 1X2 suma 1, peso) y detecta un documento estropeado; el JSON de
inicio de torneo (más de 100 pendientes) cabe en 600 KB; los últimos resultados usan el sello oficial.

## Estado

Terminado: simulador (fase regular, liguilla, series reales, cálculo exacto de series), calibración
histórica (con `poisson_simple` y con `ajuste`), sellos y calificación, exportación con validación,
contrato y 20 pruebas (todas pasan; las 36 de `test_mercados.py` también). `salidas/actual.json` (222 KB)
está generado con el modelo campeón `ajuste`.

Faltó o es dudoso:
- `ultimos_resultados` de la Jornada 16 se llena con `modelo/pred/ajuste__prueba__dia.parquet` (walk-forward,
  no sellado): cada corrida de `exportar` deja una línea en `modelo/pred/ACCESOS_PRUEBA.log`. Además, tres
  líneas de las 10:03 UTC vienen de una corrida de pruebas de este módulo (ya corregido: las pruebas no leen la PRUEBA).
- La jornada se deduce de las fechas: dentro de un grupo con partidos reprogramados (p. ej. 10 a 15 de
  septiembre) todos se etiquetan con la jornada del grupo.
- El sesgo a favor del peor sembrado tras la ida (2.7 ee) no se corrige; el factor de vuelta no pasó la validación.
- Las series reales están probadas con escenarios construidos; no hay aún liguilla real del Apertura 2026.
- No se modela: regla de menores, sede de Cruz Azul en liguilla, cambio de fechas de la final por la Intercontinental.
