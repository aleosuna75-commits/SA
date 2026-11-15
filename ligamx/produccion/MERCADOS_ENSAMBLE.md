# Mercados y combinada con el modelo de producción (`ensamble`)

Medición del **2026-11-15**. Repite las dos validaciones de `MERCADOS.md` (§3 y §4), que se escribieron con el
provisional `poisson_simple`, con el modelo que hoy está en `modelo/campeon.json`: `ensamble` (promedio de las lambdas
de `ajuste` y `elo`, con rho de Dixon-Coles). Las secciones 1 a 7 **sólo miden y diagnostican**. Las secciones 8 y 9
(mismo día) fijan la regla de adopción y prueban cuatro correcciones: **ninguna cumplió la regla y no se adoptó
nada**; el código de producción no cambió.

- **Datos**: DESARROLLO (Apertura 2016 a Clausura 2025), 2,981 partidos y 510 bloques, con las predicciones
  walk-forward guardadas en `modelo/pred/ensamble.parquet` (corte por bloque). Los 2,981 tienen medio tiempo.
- **PRUEBA**: no se leyó. Esta medición no agrega líneas a `modelo/pred/ACCESOS_PRUEBA.log`.
- **Reparto por mitades**: el de `MERCADOS.md` §1 (proporción de goles del primer tiempo de los 6 años anteriores a
  cada corte; media 0.4487 local y 0.4453 visita en el recorrido).
- **Errores estándar**: bootstrap de bloques del arnés (2,000 réplicas); el de la pendiente, 300 réplicas.
- **Columnas**: las de `MERCADOS.md` §3 (`dif` = observado − pronosticado; `pendiente` de la recalibración logística;
  `d_ll` = log-loss del modelo menos el de pronosticar siempre la frecuencia del propio periodo, negativo = gana el
  modelo).
- **Variantes probadas**: ninguna corrección. Tres configuraciones de medición (`ensamble` con su rho, `ensamble` con
  rho = 0 y `poisson_simple` como control: reproduce las cifras de `MERCADOS.md` a los decimales impresos) y **un**
  ensayo exploratorio dentro de muestra (§5.4), rotulado como tal.
- **Guiones**: temporales, fuera del repositorio
  (`/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/mercados/`: `comun.py`,
  `medir_mercados.py`, `medir_combinada.py`, `diagnostico.py`, `diagnostico2.py`, `tablas_md.py`). Usan las funciones
  de `produccion/mercados.py` y `produccion/combinada.py` sin modificarlas.

## 0. Resumen

1. **Mejoró casi todo.** De 52 mercados binarios, 35 le ganan a la constante por más de 2 errores estándar (26 con
   `poisson_simple`) y ninguno pierde (antes 2). En la comparación pareada `ensamble` es mejor por más de 2 ee en 28
   mercados y peor en ninguno.
2. **Los totales ya discriminan.** Pendientes de 1.15, 1.26 y 0.91 (ee ≈ 0.2) en más de 1.5, 2.5 y 3.5, contra 0.58,
   0.65 y 0.48; los tres le ganan a la constante (antes ninguno por 2 ee). La causa está medida: las lambdas del
   `ensamble` ya no exageran las diferencias de goles totales entre partidos (b total = 0.97 ± 0.16 contra 0.50 ± 0.09).
3. **Ambos anotan sigue subestimado**, ahora 1.9 puntos (z = 2.0) en vez de 3.4 (z = 3.6), y sigue sin ganarle a la
   constante (d_ll −0.0001, ee 0.0013). «Local anota» pasa de +2.1 (z = 3.0) a +1.4 (z = 2.0) y «visita anota» de +1.5
   a +1.0 (z = 1.2); los dos ya tienen pendiente de 1.
4. **Sesgo que no se había señalado: ganar por 2 o más está sobrestimado** en los dos lados (local −1.7 puntos, z =
   −2.2; visita −1.4, z = −2.5). Con `poisson_simple` ya estaba (z = −1.7 y −2.5).
5. **Un solo origen para 3 y 4**: los goles reales están menos dispersos que la Poisson del modelo (local: razón
   0.91, z = −3.3; diferencia de goles: 0.90, z = −4.0). Hay menos ceros y menos goleadas de los pronosticados, y más
   partidos de 1 y 2 goles por equipo y de un gol de diferencia. No viene de la media (bien centrada a 0.004 goles),
   ni del rho (no mueve las marginales), ni de la dispersión de las lambdas (bien), ni del reparto por mitades.
6. **Combinada: calibrada en las tres variantes** (diferencias de 0.5 a 1.3 ee; ningún decil pasa de 2 ee). Reserva:
   la probabilidad anunciada acierta en promedio pero apenas distingue un partido de otro en `equilibrada` y
   `atrevida`.
7. **Aviso de herramienta**: los comandos `validar ensamble` existentes corren con **rho = 0**, no con el rho de
   producción (§1).
8. **Correcciones** (§6): cuatro candidatas, ninguna implementada. La ganancia esperable de cualquiera es del orden
   de 0.001 de log-loss por mercado: con 2,981 partidos queda en el límite de lo que la regla de 2 ee puede demostrar.
   La que sugería `MERCADOS.md` (encoger el total esperado) **ya no se sostiene** con `ensamble`.
9. **Correcciones probadas** (§8 y §9): con la regla escrita antes, cuatro variantes en walk-forward (forma de la
   matriz con 1 y con 2 parámetros, recalibración por mercado, reparto por mitades según el total). Todas reducen
   los sesgos, pero la mejor mejora el log-loss de sus mercados 1.6 ee (se exigían más de 2). **No se adoptó nada.**

## 1. Aviso: los comandos existentes miden `ensamble` con rho = 0

`modelo/pred/ensamble.parquet` no guarda la columna `x_rho`, así que `python3 -m produccion.mercados validar ensamble` y
`python3 -m produccion.combinada validar ensamble` caen en `rho = 0.0`. Producción sí usa el rho del modelo
(`salidas/actual.json` del 2026-11-15: rho = −0.0512 en los partidos pendientes). Para medir lo que se publica, el rho de cada
partido se recuperó de la matriz que guardó el arnés (`modelo/cache/M_ensamble.npz`): `rho = 1 − (M[1,1]/Pois(1,1)) /
(M[2,2]/Pois(2,2))`. Con ese rho, `arnes.matrices_marcadores` reconstruye la matriz guardada con diferencia máxima de
1.6e-8 (precisión de float32 del caché) y el 1X2 guardado a 2.5e-8.

- rho del `ensamble` en desarrollo: **media −0.057**, desviación 0.017, de −0.095 a −0.002 (negativo = más 0-0 y 1-1,
  menos 1-0 y 0-1).
- Todas las tablas de este documento usan ese rho salvo donde dice «rho = 0».
- Qué cambia si se corre el comando tal cual: empate 24.8% en vez de 26.1% (z del sesgo 2.6 en vez de 0.9), ambos
  anotan 51.7% en vez de 52.4% (z = 2.7 en vez de 2.0), 9 mercados con sesgo de más de 2 ee en vez de 6.
- Arreglo sugerido (no hecho aquí): que el arnés guarde `x_rho` en las predicciones, o que las dos funciones
  `validar_desarrollo` lean la matriz guardada con `arnes.leer_matrices`.

## 2. Validación de los 56 mercados (desarrollo, 2,981 partidos, `ensamble` con su rho)

Un renglón por suceso: el complemento tiene el pronosticado y el observado complementarios, `dif` y `z` con el signo
contrario, y la misma pendiente y `d_ll`. (†) Mercados con devolución: probabilidad condicionada a que no haya
devolución, medida en los partidos sin devolución (sin empate: 2,183; asiático: 2,291); no entran a la combinada ni a
la comparación pareada. En negritas, |z| ≥ 2. La última columna compara el log-loss con el de `poisson_simple` en los
mismos partidos (negativo = `ensamble` mejor).

| Mercado (clave / complemento) | Pronosticado | Observado | dif | z | Pendiente (ee) | d_ll (ee) | `ensamble` − `poisson_simple`: d_ll (z) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gana local (`1` / `X2`) | 0.449 | 0.450 | +0.001 | 0.1 | 1.16 (0.08) | −0.0362 (0.0042) | −0.0038 (−3.4) |
| Empate (`X` / `12`) | 0.261 | 0.268 | +0.006 | 0.9 | 1.44 (0.35) | −0.0029 (0.0010) | −0.0005 (−0.6) |
| Gana visita (`2` / `1X`) | 0.290 | 0.282 | −0.007 | −1.0 | 1.15 (0.09) | −0.0309 (0.0040) | −0.0047 (−5.6) |
| Local, sin empate (†) (`SE_1` / `SE_2`) | 0.609 | 0.614 | +0.006 | 0.6 | 1.16 (0.09) | −0.0560 (0.0063) | — |
| Local gana por 2+ (`H_L-1.5` / `H_V+1.5`) | 0.235 | 0.218 | −0.017 | **−2.2** | 1.06 (0.09) | −0.0251 (0.0041) | −0.0019 (−1.7) |
| Visita gana por 2+ (`H_V-1.5` / `H_L+1.5`) | 0.124 | 0.110 | −0.014 | **−2.5** | 1.02 (0.11) | −0.0147 (0.0034) | −0.0028 (−4.0) |
| Local −1 asiático (†) (`HA_L-1` / `HA_V+1`) | 0.296 | 0.284 | −0.012 | −1.4 | 1.11 (0.09) | −0.0455 (0.0056) | — |
| Más de 1.5 (`O15` / `U15`) | 0.749 | 0.749 | 0.000 | 0.0 | 1.15 (0.23) | −0.0043 (0.0015) | −0.0033 (−2.3) |
| Más de 2.5 (`O25` / `U25`) | 0.496 | 0.502 | +0.005 | 0.6 | 1.26 (0.21) | −0.0068 (0.0018) | −0.0028 (−1.8) |
| Más de 3.5 (`O35` / `U35`) | 0.279 | 0.279 | +0.001 | 0.1 | 0.91 (0.19) | −0.0038 (0.0017) | −0.0043 (−2.7) |
| Ambos anotan (`AA_SI` / `AA_NO`) | 0.523 | 0.543 | +0.019 | **2.03** | 0.69 (0.25) | −0.0001 (0.0013) | −0.0051 (−3.9) |
| Local anota (`L_ANOTA` / `PC_V`) | 0.770 | 0.784 | +0.014 | 1.98 | 1.09 (0.12) | −0.0136 (0.0029) | −0.0045 (−4.1) |
| Local anota 2+ (`L_2MAS` / `L_U15`) | 0.441 | 0.446 | +0.004 | 0.5 | 1.07 (0.11) | −0.0227 (0.0038) | −0.0027 (−1.8) |
| Visita anota (`V_ANOTA` / `PC_L`) | 0.676 | 0.686 | +0.010 | 1.2 | 1.04 (0.13) | −0.0112 (0.0028) | −0.0034 (−3.2) |
| Visita anota 2+ (`V_2MAS` / `V_U15`) | 0.318 | 0.321 | +0.003 | 0.3 | 1.00 (0.11) | −0.0145 (0.0030) | −0.0052 (−4.0) |
| Local gana al descanso (`D_1` / `D_X2`) | 0.342 | 0.338 | −0.005 | −0.5 | 0.87 (0.11) | −0.0097 (0.0029) | −0.0024 (−2.8) |
| Empate al descanso (`D_X` / `D_12`) | 0.418 | 0.434 | +0.015 | 1.6 | 0.98 (0.37) | −0.0006 (0.0011) | −0.0009 (−1.4) |
| Visita gana al descanso (`D_2` / `D_1X`) | 0.239 | 0.228 | −0.011 | −1.4 | 0.99 (0.12) | −0.0098 (0.0026) | −0.0025 (−4.5) |
| Gol en el 1T (`G1T_SI` / `G1T_NO`) | 0.694 | 0.692 | −0.002 | −0.2 | 0.82 (0.32) | −0.0011 (0.0011) | −0.0019 (−2.0) |
| Más de 1.5 en el 1T (`O15_1T` / `U15_1T`) | 0.335 | 0.345 | +0.009 | 1.1 | 0.78 (0.27) | −0.0011 (0.0013) | −0.0023 (−2.1) |
| Gol en el 2T (`G2T_SI` / `G2T_NO`) | 0.767 | 0.783 | +0.015 | 1.94 | 1.29 (0.30) | −0.0019 (0.0013) | −0.0017 (−1.8) |
| Más goles en el 1T (`MAS_1T`) | 0.301 | 0.297 | −0.004 | −0.5 | −0.52 (1.71) | +0.0002 (0.0003) | +0.0001 (0.5) |
| Más goles en el 2T (`MAS_2T`) | 0.431 | 0.441 | +0.010 | 1.1 | 1.50 (1.05) | −0.0001 (0.0005) | 0.0000 (0.0) |
| Mismos goles por mitad (`MIT_IGUAL`) | 0.268 | 0.262 | −0.006 | −0.8 | 1.75 (0.73) | −0.0008 (0.0006) | +0.0006 (1.2) |
| Local gana alguna mitad (`GM_L`) | 0.579 | 0.589 | +0.010 | 1.1 | 1.01 (0.10) | −0.0223 (0.0038) | −0.0041 (−3.9) |
| Visita gana alguna mitad (`GM_V`) | 0.431 | 0.433 | +0.002 | 0.2 | 1.13 (0.09) | −0.0251 (0.0035) | −0.0033 (−3.8) |
| Descanso/final local/local (`DF_1/1`) | 0.275 | 0.266 | −0.009 | −1.1 | 1.02 (0.10) | −0.0179 (0.0035) | −0.0022 (−2.2) |
| Descanso/final local/empate (`DF_1/X`) | 0.050 | 0.054 | +0.004 | 0.9 | 1.00 (1.04) | −0.0001 (0.0005) | −0.0003 (−1.2) |
| Descanso/final local/visita (`DF_1/2`) | 0.017 | 0.018 | +0.001 | 0.2 | 1.64 (0.55) | −0.0016 (0.0007) | −0.0002 (−1.1) |
| Descanso/final empate/local (`DF_X/1`) | 0.150 | 0.159 | +0.008 | 1.2 | 1.46 (0.23) | −0.0065 (0.0015) | −0.0007 (−1.8) |
| Descanso/final empate/empate (`DF_X/X`) | 0.162 | 0.165 | +0.003 | 0.4 | 1.09 (0.40) | −0.0015 (0.0010) | −0.0007 (−0.8) |
| Descanso/final empate/visita (`DF_X/2`) | 0.106 | 0.110 | +0.004 | 0.7 | 1.32 (0.20) | −0.0090 (0.0019) | −0.0006 (−1.4) |
| Descanso/final visita/local (`DF_2/1`) | 0.024 | 0.025 | +0.002 | 0.6 | 1.27 (0.60) | −0.0007 (0.0006) | −0.0004 (−1.3) |
| Descanso/final visita/empate (`DF_2/X`) | 0.049 | 0.049 | 0.000 | 0.0 | 1.49 (1.00) | −0.0004 (0.0003) | −0.0003 (−1.1) |
| Descanso/final visita/visita (`DF_2/2`) | 0.166 | 0.154 | −0.012 | −1.8 | 1.03 (0.11) | −0.0138 (0.0031) | −0.0029 (−5.5) |

1X2 al descanso como pronóstico de tres clases: log-loss **1.0520** contra 1.0662 de la constante (−0.0142, ee 0.0034);
con `poisson_simple` era 1.0560 (pareada −0.0039, ee 0.0010).

Pronosticado contra observado por deciles (n ≈ 298 por decil; en el 1X2 al descanso se juntan las tres clases, n ≈ 894):

| Decil | Gol 1T pron. | obs. | 1X2 descanso pron. | obs. | Más de 2.5 pron. | obs. | Ambos anotan pron. | obs. |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.650 | 0.686 | 0.168 | 0.161 | 0.420 | 0.405 | 0.467 | 0.498 |
| 2 | 0.666 | 0.644 | 0.219 | 0.221 | 0.447 | 0.443 | 0.488 | 0.584 |
| 3 | 0.675 | 0.628 | 0.256 | 0.254 | 0.462 | 0.433 | 0.499 | 0.480 |
| 4 | 0.682 | 0.695 | 0.289 | 0.291 | 0.475 | 0.453 | 0.509 | 0.517 |
| 5 | 0.690 | 0.654 | 0.327 | 0.306 | 0.488 | 0.513 | 0.518 | 0.534 |
| 6 | 0.696 | 0.715 | 0.368 | 0.352 | 0.500 | 0.537 | 0.527 | 0.547 |
| 7 | 0.703 | 0.701 | 0.399 | 0.399 | 0.512 | 0.537 | 0.536 | 0.527 |
| 8 | 0.711 | 0.768 | 0.417 | 0.425 | 0.528 | 0.527 | 0.547 | 0.581 |
| 9 | 0.721 | 0.715 | 0.431 | 0.457 | 0.547 | 0.560 | 0.559 | 0.534 |
| 10 | 0.743 | 0.711 | 0.459 | 0.466 | 0.586 | 0.611 | 0.586 | 0.628 |

Lectura:
1. **Sesgos de más de 2 ee: tres sucesos** (seis claves): local gana por 2 o más (`H_L-1.5`, −0.017, z = −2.2), visita
   gana por 2 o más (`H_V-1.5`, −0.014, z = −2.5) y ambos anotan (`AA_SI`, +0.019, z = 2.0). Rozan el umbral «local
   anota» (+0.014, z = 1.98) y «gol en el 2T» (+0.015, z = 1.94). Con 35 sucesos distintos se esperan 1.75 por encima
   de 2 ee por puro azar; lo que les da peso es que comparten una causa medida aparte con z = −3.3 a −4.0 (§5.2).
2. **Lo que depende de quién es mejor**: pendientes de 0.87 a 1.16 (antes 0.75 a 1.04); el 1X2 es ligeramente tímido
   (1.15, ee 0.09), como ya decía `campeon.json`.
3. **Lo que depende de cuántos goles habrá**: ahora con pendientes compatibles con 1 (0.78 a 1.29, ee 0.2 a 0.3).
   Ganan a la constante los totales del partido; gol en el 1T, más de 1.5 en el 1T y gol en el 2T mejoran (−0.0011 a
   −0.0019) pero no llegan a 2 ee.
4. **Siguen sin información** (iguales a la constante): mitad con más goles (`MAS_1T`, `MAS_2T`, `MIT_IGUAL`),
   empate al descanso y cuatro de los nueve descanso/final (`DF_1/X`, `DF_X/X`, `DF_2/1`, `DF_2/X`). Las pendientes de
   mitad con más goles (−0.5 a 1.8, ee 0.7 a 1.7) no dicen nada.
5. **Ambos anotan por deciles**: el pronóstico va de 0.467 a 0.586 (antes de 0.398 a 0.622) y queda corto en 7 de
   los 10 deciles; el peor es el segundo (+0.096, z = 3.3). Ya no está el hundimiento de los deciles bajos de
   `poisson_simple` (0.398 pronosticado contra 0.528 observado), pero la pendiente sigue en 0.69 (ee 0.25) y el
   mercado no le gana a la constante. En las otras tres columnas ningún decil pasa de 2.2 ee.

## 3. Comparación con `poisson_simple` (cifras de `MERCADOS.md` §3)

| Mercado | Sesgo `poisson_simple`: dif (z) | Sesgo `ensamble`: dif (z) | Pendiente antes | Pendiente ahora (ee) | d_ll contra constante antes | ahora (ee) | Pareada ahora − antes (ee) | z |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Ambos anotan (`AA_SI`) | +0.034 (**3.6**) | +0.019 (**2.03**) | 0.34 | 0.69 (0.25) | +0.0050 | −0.0001 (0.0013) | −0.0051 (0.0013) | **−3.9** |
| Local anota (`L_ANOTA`) | +0.021 (**3.0**) | +0.014 (1.98) | 0.82 | 1.09 (0.12) | −0.0091 | −0.0136 (0.0029) | −0.0045 (0.0011) | **−4.1** |
| Visita anota (`V_ANOTA`) | +0.015 (1.8) | +0.010 (1.2) | 0.76 | 1.04 (0.13) | −0.0078 | −0.0112 (0.0028) | −0.0034 (0.0011) | **−3.2** |
| Local anota 2+ (`L_2MAS`) | +0.012 (1.4) | +0.004 (0.5) | 0.88 | 1.07 (0.11) | −0.0200 | −0.0227 (0.0038) | −0.0027 (0.0015) | −1.8 |
| Visita anota 2+ (`V_2MAS`) | +0.006 (0.7) | +0.003 (0.3) | 0.72 | 1.00 (0.11) | −0.0093 | −0.0145 (0.0030) | −0.0052 (0.0013) | **−4.0** |
| Más de 1.5 (`O15`) | +0.016 (1.93) | 0.000 (0.0) | 0.58 | 1.15 (0.23) | −0.0010 | −0.0043 (0.0015) | −0.0033 (0.0015) | **−2.3** |
| Más de 2.5 (`O25`) | +0.014 (1.6) | +0.005 (0.6) | 0.65 | 1.26 (0.21) | −0.0040 | −0.0068 (0.0018) | −0.0028 (0.0016) | −1.8 |
| Más de 3.5 (`O35`) | +0.005 (0.7) | +0.001 (0.1) | 0.48 | 0.91 (0.19) | +0.0006 | −0.0038 (0.0017) | −0.0043 (0.0016) | **−2.7** |
| Gol en el 1T (`G1T_SI`) | +0.003 (0.3) | −0.002 (−0.2) | 0.42 | 0.82 (0.32) | +0.0008 | −0.0011 (0.0011) | −0.0019 (0.0010) | −1.97 |
| Más de 1.5 en el 1T (`O15_1T`) | +0.015 (1.7) | +0.009 (1.1) | 0.45 | 0.78 (0.27) | +0.0012 | −0.0011 (0.0013) | −0.0023 (0.0011) | **−2.06** |
| Gol en el 2T (`G2T_SI`) | +0.019 (**2.4**) | +0.015 (1.94) | 0.62 | 1.29 (0.30) | −0.0001 | −0.0019 (0.0013) | −0.0017 (0.0010) | −1.8 |
| Local gana al descanso (`D_1`) | −0.002 (−0.3) | −0.005 (−0.5) | 0.75 | 0.87 (0.11) | −0.0073 | −0.0097 (0.0029) | −0.0024 (0.0009) | **−2.8** |
| Empate al descanso (`D_X`) | +0.014 (1.5) | +0.015 (1.6) | 0.53 | 0.98 (0.37) | +0.0003 | −0.0006 (0.0011) | −0.0009 (0.0006) | −1.4 |
| Visita gana al descanso (`D_2`) | −0.012 (−1.5) | −0.011 (−1.4) | 0.82 | 0.99 (0.12) | −0.0073 | −0.0098 (0.0026) | −0.0025 (0.0006) | **−4.5** |
| Empate (`X`) | +0.017 (**2.3**) | +0.006 (0.9) | 1.17 | 1.44 (0.35) | −0.0024 | −0.0029 (0.0010) | −0.0005 (0.0008) | −0.6 |
| Gana local (`1`) | −0.002 (−0.2) | +0.001 (0.1) | 1.04 | 1.16 (0.08) | −0.0325 | −0.0362 (0.0042) | −0.0038 (0.0011) | **−3.4** |
| Gana visita (`2`) | −0.015 (**−2.02**) | −0.007 (−1.0) | 1.01 | 1.15 (0.09) | −0.0262 | −0.0309 (0.0040) | −0.0047 (0.0008) | **−5.6** |
| Local gana por 2+ (`H_L-1.5`) | −0.013 (−1.7) | −0.017 (**−2.2**) | 0.95 | 1.06 (0.09) | −0.0231 | −0.0251 (0.0041) | −0.0019 (0.0011) | −1.7 |
| Visita gana por 2+ (`H_V-1.5`) | −0.015 (**−2.5**) | −0.014 (**−2.5**) | 0.87 | 1.02 (0.11) | −0.0119 | −0.0147 (0.0034) | −0.0028 (0.0007) | **−4.0** |
| Local gana alguna mitad (`GM_L`) | +0.011 (1.3) | +0.010 (1.1) | 0.87 | 1.01 (0.10) | −0.0182 | −0.0223 (0.0038) | −0.0041 (0.0011) | **−3.9** |
| Más goles en el 2T (`MAS_2T`) | +0.007 (0.8) | +0.010 (1.1) | 0.73 | 1.50 (1.05) | −0.0001 | −0.0001 (0.0005) | 0.0000 (0.0003) | 0.0 |
| Descanso/final local/local (`DF_1/1`) | −0.009 (−1.1) | −0.009 (−1.1) | 0.92 | 1.02 (0.10) | −0.0157 | −0.0179 (0.0035) | −0.0022 (0.0010) | **−2.2** |
| Descanso/final empate/empate (`DF_X/X`) | +0.009 (1.4) | +0.003 (0.4) | 0.69 | 1.09 (0.40) | −0.0008 | −0.0015 (0.0010) | −0.0007 (0.0009) | −0.8 |

| | Qué pasó |
|---|---|
| **Mejoró** | Totales (pendiente 0.48–0.65 → 0.91–1.26; los tres pasan a ganarle a la constante). Anota / no anota (pendiente 0.76–0.82 → 1.04–1.09; sesgo del local de 3.0 a 2.0 ee). Ambos anotan (sesgo de 3.4 a 1.9 puntos; deja de perder contra la constante: +0.0050 → −0.0001; pareada −0.0051, z = −3.9). Empate (z del sesgo 2.3 → 0.9, por el rho). Gana visita (sesgo de −1.5 a −0.7 puntos, z = −2.0 → −1.0). Goles por mitad (pendientes 0.42–0.62 → 0.78–1.29). 1X2 al descanso (−0.0039, ee 0.0010). Resultado, hándicap, gana alguna mitad y descanso/final local/local y visita/visita (pareadas de −0.002 a −0.005). |
| **Empeoró** | Nada por más de 1.2 ee en log-loss. En sesgo, «local gana por 2+» pasa de −0.013 (z = −1.7) a −0.017 (z = −2.2): la media de goles del local subió de 1.495 a 1.513 y la forma de la distribución no cambió. |
| **Sigue igual** | «Visita gana por 2+» sobrestimado (z = −2.5 antes y ahora). Empate al descanso corto 1.5 puntos (z = 1.5 → 1.6). Gol en el 2T corto 1.9 → 1.5 puntos (z = 2.4 → 1.9). Mitad con más goles y descanso/final con vuelco: sin información. |

## 4. Combinada del partido (desarrollo, mismas reglas y bandas de `MERCADOS.md` §4)

En cada partido se armaron las tres combinadas con lo conocido antes del corte y se contó si se cumplieron los cuatro
picks. `d_ll contra constante` = log-loss de la conjunta anunciada menos el de anunciar siempre la frecuencia media de
la variante; `pendiente` = recalibración logística de la conjunta anunciada.

| Modelo | Variante | n | Conjunta anunciada | Frecuencia observada | dif (ee) | z | Producto ingenuo | Momio justo medio | Log-loss conjunta / ingenua | d_ll contra constante (ee) | Pendiente |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `ensamble` (su rho) | segura | 2,981 | 0.481 | 0.486 | +0.005 (0.010) | 0.5 | 0.348 | 2.09 | 0.690 / 0.732 | −0.0029 (0.0012) | 1.11 |
| `ensamble` (su rho) | equilibrada | 2,981 | 0.332 | 0.343 | +0.011 (0.008) | 1.3 | 0.126 | 3.04 | 0.644 / 0.800 | +0.0007 (0.0013) | 0.40 |
| `ensamble` (su rho) | atrevida | 2,981 | 0.203 | 0.209 | +0.005 (0.007) | 0.7 | 0.058 | 5.04 | 0.511 / 0.641 | −0.0009 (0.0014) | 0.67 |
| `ensamble` (rho = 0: lo que da el comando) | segura | 2,981 | 0.481 | 0.492 | +0.012 (0.010) | 1.2 | 0.350 | 2.09 | 0.690 / 0.735 | −0.0028 (0.0014) | 1.09 |
| `ensamble` (rho = 0: lo que da el comando) | equilibrada | 2,981 | 0.335 | 0.339 | +0.004 (0.008) | 0.5 | 0.126 | 3.01 | 0.641 / 0.792 | +0.0001 (0.0012) | 0.48 |
| `ensamble` (rho = 0: lo que da el comando) | atrevida | 2,981 | 0.203 | 0.207 | +0.004 (0.007) | 0.6 | 0.059 | 5.05 | 0.508 / 0.634 | −0.0020 (0.0013) | 0.86 |
| `poisson_simple` | segura | 2,981 | 0.492 | 0.488 | −0.004 (0.010) | −0.4 | 0.358 | 2.05 | 0.691 / 0.729 | −0.0018 (0.0014) | 0.83 |
| `poisson_simple` | equilibrada | 2,981 | 0.332 | 0.341 | +0.010 (0.009) | 1.1 | 0.130 | 3.05 | 0.641 / 0.787 | −0.0011 (0.0015) | 0.74 |
| `poisson_simple` | atrevida | 2,981 | 0.195 | 0.206 | +0.011 (0.008) | 1.4 | 0.057 | 5.34 | 0.509 / 0.645 | +0.0001 (0.0020) | 0.52 |

Por deciles de la probabilidad conjunta anunciada (`ensamble` con su rho, n ≈ 298 por decil):

| Decil | Segura anunciada | obs. | z | Equilibrada anunciada | obs. | z | Atrevida anunciada | obs. | z |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.435 | 0.441 | 0.2 | 0.275 | 0.308 | 1.3 | 0.150 | 0.174 | 1.2 |
| 2 | 0.448 | 0.483 | 1.2 | 0.308 | 0.262 | −1.7 | 0.169 | 0.164 | −0.2 |
| 3 | 0.456 | 0.463 | 0.2 | 0.316 | 0.366 | 1.8 | 0.181 | 0.191 | 0.5 |
| 4 | 0.463 | 0.450 | −0.5 | 0.323 | 0.366 | 1.6 | 0.191 | 0.235 | 1.93 |
| 5 | 0.470 | 0.423 | −1.6 | 0.330 | 0.366 | 1.3 | 0.200 | 0.201 | 0.1 |
| 6 | 0.478 | 0.517 | 1.3 | 0.336 | 0.372 | 1.3 | 0.209 | 0.221 | 0.5 |
| 7 | 0.488 | 0.466 | −0.7 | 0.342 | 0.356 | 0.5 | 0.218 | 0.195 | −1.0 |
| 8 | 0.502 | 0.520 | 0.6 | 0.349 | 0.326 | −0.8 | 0.227 | 0.235 | 0.3 |
| 9 | 0.521 | 0.534 | 0.4 | 0.360 | 0.366 | 0.2 | 0.236 | 0.235 | −0.1 |
| 10 | 0.553 | 0.567 | 0.5 | 0.386 | 0.346 | −1.4 | 0.252 | 0.235 | −0.7 |

Lectura:
1. **Se cumple lo que se anuncia**: diferencias de +0.005, +0.011 y +0.005 (0.5, 1.3 y 0.7 ee), siempre a favor
   (ocurre algo más de lo anunciado). Ningún decil pasa de 2 ee (el mayor, z = 1.9, en 30 deciles). Por quintiles la
   mayor diferencia es +0.046 (z = 2.4) en el segundo quintil de la equilibrada; `MERCADOS.md` reportaba +0.034 (z =
   2.4) en un quintil de la atrevida: del mismo tamaño que el azar en 15 quintiles.
2. **El producto de marginales sigue sin servir**: habría anunciado 1.4, 2.7 y 3.6 veces menos de lo que ocurre.
3. **Contra `poisson_simple`**: misma calibración media (antes −0.004, +0.010 y +0.011). La `atrevida` anuncia algo
   más (0.203 contra 0.195) y lo cumple (0.209).
4. **Reserva nueva: la conjunta casi no distingue entre partidos.** La anunciada varía poco (desviación 0.030 a
   0.035) y sólo en la `segura` esa variación informa (le gana a la constante por 0.0029, 2.4 ee; pendiente 1.11, ee
   0.28). En la `equilibrada` la pendiente es 0.40 (ee 0.26) y no le gana a la constante (+0.0007, ee 0.0013); en la
   `atrevida`, 0.67 (ee 0.25) y −0.0009 (ee 0.0014). Es decir: «33% en promedio» es cierto; «este partido 38% y aquel
   28%» no está demostrado. Con `poisson_simple` pasaba lo mismo (pendientes 0.83, 0.74 y 0.52).
5. **Picks más usados**: segura = gol en el 2T (2,099 de 2,981), más de 1.5 (1,765), local o empate al descanso
   (1,471), local anota (1,364); equilibrada = menos de 1.5 en el 1T (1,886), menos de 2.5 (1,712), al menos uno no
   anota (1,361), visita anota menos de 1.5 (1,004); atrevida = más de 2.5 (2,281), no hay empate al descanso (2,158),
   local anota 2 o más (1,346), local gana alguna mitad (1,052). Los dos picks con sesgo que más pesan en la `segura`
   (gol en el 2T y local anota) están subestimados: por eso la segura queda del lado prudente. La `equilibrada` usa
   «al menos uno no anota» (sobrestimado 1.9 puntos) en 46% de los partidos y aun así cumple más de lo que anuncia.
6. La banda se amplió en 1 de 8,943 combinadas. Aciertos medios por combinada: 3.08, 2.43 y 1.97 de 4.

## 5. Diagnóstico: de dónde sale cada sesgo

### 5.1 Medias y ceros

|  | Observado | `poisson_simple` pron. | dif (z) | `ensamble` rho = 0 pron. | dif (z) | `ensamble` con rho pron. | dif (z) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Goles del local (media) | 1.510 | 1.495 | +0.015 (0.7) | 1.513 | −0.004 (−0.2) | 1.513 | −0.004 (−0.2) |
| Goles de la visita (media) | 1.154 | 1.144 | +0.010 (0.5) | 1.151 | +0.003 (0.2) | 1.151 | +0.003 (0.2) |
| Local sin gol | 0.2164 | 0.2376 | −0.0212 (**−3.0**) | 0.2303 | −0.0139 (−1.98) | 0.2303 | −0.0139 (−1.98) |
| Visita sin gol | 0.3140 | 0.3294 | −0.0154 (−1.8) | 0.3239 | −0.0099 (−1.2) | 0.3239 | −0.0099 (−1.2) |
| 0-0 | 0.0731 | 0.0756 | −0.0024 (−0.5) | 0.0709 | +0.0022 (0.4) | 0.0776 | −0.0045 (−0.9) |
| Ambos anotan | 0.5428 | 0.5085 | +0.0342 (**3.6**) | 0.5168 | +0.0260 (**2.7**) | 0.5235 | +0.0193 (**2.03**) |

- **La media está bien** (1.513 pronosticado contra 1.510 del local; 1.151 contra 1.154 de la visita) y aun así
  sobran ceros: local sin gol 23.0% contra 21.6% (z = −2.0); visita 32.4% contra 31.4% (z = −1.2).
- Una Poisson con lambda **constante** e igual a la media observada ya da 22.1% y 31.5%: más ceros que los
  observados aunque no hubiera ninguna diferencia entre partidos. El exceso no viene de las lambdas sino de la forma
  de la distribución.
- Por qué mejoró respecto a `poisson_simple` (23.8% → 23.0% en el local): 0.4 puntos por la media (1.495 → 1.513) y 0.3
  por lambdas menos dispersas (desviación de `lam_l` 0.350 → 0.307).
- **Descomposición de ambos anotan** (P = 1 − P(local 0) − P(visita 0) + P(0-0)): +1.39 puntos por los ceros del
  local, +0.99 por los de la visita y −0.45 porque el 0-0 quedó sobrestimado (7.76% contra 7.31%) = **+1.93**.

### 5.2 Forma de la distribución: menos dispersión que Poisson

| Variable | Valor | Pronosticado | Observado | dif | z |
|---|---:|---:|---:|---:|---:|
| Goles del local | 0 | 0.2303 | 0.2164 | −0.0139 | −1.98 |
| Goles del local | 1 | 0.3283 | 0.3378 | +0.0095 | 1.1 |
| Goles del local | 2 | 0.2434 | 0.2539 | +0.0105 | 1.4 |
| Goles del local | 3 | 0.1250 | 0.1275 | +0.0024 | 0.4 |
| Goles del local | 4+ | 0.0730 | 0.0644 | −0.0086 | **−2.01** |
| Goles de la visita | 0 | 0.3239 | 0.3140 | −0.0099 | −1.2 |
| Goles de la visita | 1 | 0.3578 | 0.3650 | +0.0072 | 0.9 |
| Goles de la visita | 2 | 0.2047 | 0.2123 | +0.0077 | 1.1 |
| Goles de la visita | 3 | 0.0809 | 0.0788 | −0.0020 | −0.4 |
| Goles de la visita | 4+ | 0.0328 | 0.0299 | −0.0030 | −1.0 |
| Total | 0 | 0.0776 | 0.0731 | −0.0045 | −0.9 |
| Total | 1 | 0.1731 | 0.1775 | +0.0044 | 0.6 |
| Total | 2 | 0.2529 | 0.2476 | −0.0053 | −0.7 |
| Total | 3 | 0.2179 | 0.2224 | +0.0046 | 0.6 |
| Total | 4 | 0.1454 | 0.1432 | −0.0021 | −0.3 |
| Total | 5 | 0.0780 | 0.0906 | +0.0126 | **2.4** |
| Total | 6+ | 0.0552 | 0.0456 | −0.0096 | **−2.6** |
| Diferencia (local − visita) | <=-3 | 0.0419 | 0.0379 | −0.0040 | −1.1 |
| Diferencia (local − visita) | -2 | 0.0825 | 0.0725 | −0.0101 | **−2.1** |
| Diferencia (local − visita) | -1 | 0.1653 | 0.1721 | +0.0068 | 1.0 |
| Diferencia (local − visita) | 0 | 0.2612 | 0.2677 | +0.0065 | 0.9 |
| Diferencia (local − visita) | +1 | 0.2138 | 0.2315 | +0.0177 | **2.3** |
| Diferencia (local − visita) | +2 | 0.1359 | 0.1255 | −0.0105 | −1.7 |
| Diferencia (local − visita) | >=+3 | 0.0993 | 0.0929 | −0.0064 | −1.2 |

Dispersión por partido: media de (observado − esperado)² contra la varianza que el modelo le asigna a ese partido.

|  | Varianza según el modelo | Observada alrededor del pronóstico | Razón | dif (ee) | z |
|---|---:|---:|---:|---:|---:|
| Goles del local | 1.513 | 1.380 | 0.912 | −0.133 (0.040) | **−3.3** |
| Goles de la visita | 1.151 | 1.098 | 0.954 | −0.053 (0.032) | −1.7 |
| Total | 2.678 | 2.573 | 0.961 | −0.105 (0.070) | −1.5 |
| Diferencia | 2.651 | 2.384 | 0.899 | −0.267 (0.066) | **−4.0** |
| Covarianza local-visita | 0.007 | 0.047 | — | +0.040 (0.022) | 1.8 |

- Los goles del local tienen **91% de la varianza** que supone el modelo (z = −3.3); los de la visita, 95% (z =
  −1.7); la diferencia de goles, **90%** (z = −4.0). En bruto: varianza observada de los goles del local 1.484 con
  media 1.510 (menor que la media, cuando una mezcla de Poisson debería estar por encima).
- Se ve en las colas: local sin gol −1.4 puntos y local con 4 o más −0.9 (z = −2.0); 1 y 2 goles, +1.0 cada uno. En
  el total: 6 o más goles 5.5% pronosticado contra 4.6% (z = −2.6).
- **Diferencia de goles**: ganar por uno el local 21.4% contra 23.2% observado (z = +2.3); ganar por dos, 1.0 punto de
  más en cada lado; por tres o más, 0.4 a 0.6 de más. De los 0.267 de varianza que sobran en la diferencia, 0.133 son
  del local, 0.053 de la visita y 0.081 de una covarianza positiva entre los goles de los dos equipos que el modelo no
  tiene (observada +0.047 contra +0.007 del modelo; z = 1.8).
- No es que el modelo separe de más a los equipos: la pendiente del reparto local/visita es 1.06 (ee 0.06, §5.4).
- Es propiedad de los datos frente a Poisson, no de este modelo: con `poisson_simple` las razones son 0.94 (local), 0.97
  (visita) y 0.92 (diferencia, z = −3.3).

Por cuartil de lambda (el exceso de ceros aparece en 7 de las 8 casillas):

| Lado | Cuartil de lambda | Lambda media | Goles observados | Sin gol: pron. | obs. | 2 o más: pron. | obs. |
|---|---:|---:|---:|---:|---:|---:|---:|
| local | 1 | 1.15 | 1.13 | 0.319 | 0.310 | 0.319 | 0.324 |
| local | 2 | 1.39 | 1.39 | 0.250 | 0.228 | 0.404 | 0.401 |
| local | 3 | 1.59 | 1.56 | 0.205 | 0.203 | 0.471 | 0.463 |
| local | 4 | 1.93 | 1.97 | 0.148 | 0.125 | 0.572 | 0.595 |
| visita | 1 | 0.89 | 0.88 | 0.412 | 0.417 | 0.223 | 0.224 |
| visita | 2 | 1.06 | 1.05 | 0.347 | 0.333 | 0.286 | 0.287 |
| visita | 3 | 1.21 | 1.23 | 0.300 | 0.285 | 0.340 | 0.342 |
| visita | 4 | 1.45 | 1.47 | 0.237 | 0.221 | 0.424 | 0.431 |

### 5.3 Efecto del rho de Dixon-Coles

| Marcador | Pron. rho = 0 | Pron. con rho | Observado | z (rho = 0) | z (con rho) |
|---|---:|---:|---:|---:|---:|
| 0-0 | 0.0709 | 0.0776 | 0.0731 | 0.4 | −0.9 |
| 1-0 | 0.1046 | 0.0979 | 0.1020 | −0.5 | 0.7 |
| 0-1 | 0.0818 | 0.0752 | 0.0755 | −1.3 | 0.1 |
| 1-1 | 0.1173 | 0.1239 | 0.1298 | **2.1** | 1.0 |
| 2-0 | 0.0801 | 0.0801 | 0.0755 | −1.0 | −1.0 |
| 0-2 | 0.0488 | 0.0488 | 0.0423 | −1.9 | −1.9 |
| 2-1 | 0.0873 | 0.0873 | 0.0919 | 0.9 | 0.9 |
| 1-2 | 0.0680 | 0.0680 | 0.0715 | 0.7 | 0.7 |
| 2-2 | 0.0492 | 0.0492 | 0.0550 | 1.5 | 1.5 |

| Mercado | Pron. rho = 0 | Pron. con rho | Observado | d_ll con rho − sin rho (ee) |
|---|---:|---:|---:|---:|
| `X` | 0.2479 | 0.2612 | 0.2677 | −0.0007 (0.0005) |
| `AA_SI` | 0.5168 | 0.5235 | 0.5428 | −0.0006 (0.0003) |
| `O15` | 0.7426 | 0.7493 | 0.7494 | −0.0001 (0.0003) |
| `O25` | 0.4964 | 0.4964 | 0.5018 | 0.0000 (0.0000) |
| `U25` | 0.5036 | 0.5036 | 0.4982 | 0.0000 (0.0000) |
| `L_ANOTA` | 0.7697 | 0.7697 | 0.7836 | 0.0000 (0.0000) |
| `V_ANOTA` | 0.6761 | 0.6761 | 0.6860 | 0.0000 (0.0000) |
| `D_X` | 0.4158 | 0.4185 | 0.4337 | −0.0001 (0.0001) |
| `G1T_NO` | 0.3049 | 0.3063 | 0.3083 | 0.0000 (0.0001) |
| `DF_X/X` | 0.1521 | 0.1621 | 0.1650 | −0.0003 (0.0005) |
| `H_L-1.5` | 0.2352 | 0.2352 | 0.2184 | 0.0000 (0.0000) |
| `H_V-1.5` | 0.1244 | 0.1244 | 0.1104 | 0.0000 (0.0000) |

- El rho **no cambia las marginales**: «local anota», «visita anota», totales de equipo y hándicap de 2 o más quedan
  idénticos con y sin rho. No puede corregir los ceros de más.
- Le quita 0.67 puntos al 1-0 y otros tantos al 0-1, y se los da al 0-0 y al 1-1. Arregla el **empate** (24.8% → 26.1%, observado 26.8%; z = 2.6 →
  0.9) y sube ambos anotan de 51.7% a 52.4% (un cuarto del hueco). Costo: el 0-0 pasa de corto (7.09%) a largo (7.76%
  contra 7.31%) y la victoria local por un gol queda más corta (z = 1.5 → 2.3), porque lo que el dato pide es más 1-1,
  2-1, 1-2 y 2-2, no más 0-0.
- El valor usado es razonable: media −0.057 contra −0.052 del rho de máxima verosimilitud dentro de desarrollo dadas
  las lambdas (intervalo de 68%: −0.074 a −0.029). En log-loss su efecto es mínimo (−0.0007 en el empate, ee 0.0005).

### 5.4 Dispersión de las lambdas: ¿exageran las diferencias de goles totales?

Regresión de Poisson de los goles observados sobre el logaritmo de los esperados (b = 1: las diferencias entre
partidos son del tamaño correcto; b < 1: exageradas). `b reparto`: regresión binomial de los goles del local dentro del
total sobre el logit de su parte esperada.

| Modelo | Total esperado medio | Desv. est. del total esperado | b total (ee) | b local (ee) | b visita (ee) | b reparto (ee) | corr. total esperado–observado |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ensamble` | 2.665 | 0.196 | 0.97 (0.16) | 1.05 (0.08) | 1.03 (0.09) | 1.06 (0.06) | 0.118 |
| `ajuste` | 2.691 | 0.345 | 0.54 (0.09) | 0.88 (0.06) | 0.77 (0.07) | 0.94 (0.05) | 0.115 |
| `elo` | 2.638 | 0.120 | 0.73 (0.27) | 1.06 (0.08) | 1.23 (0.11) | 1.15 (0.07) | 0.055 |
| `dc` | 2.640 | 0.316 | 0.55 (0.09) | 0.91 (0.07) | 0.81 (0.08) | 1.01 (0.06) | 0.107 |
| `poisson_simple` | 2.639 | 0.341 | 0.50 (0.09) | 0.85 (0.07) | 0.75 (0.07) | 0.95 (0.06) | 0.106 |

| Quintil del total esperado | `poisson_simple` pron. | obs. | `ensamble` pron. | obs. |
|---:|---:|---:|---:|---:|
| 1 | 2.20 | 2.47 | 2.41 | 2.43 |
| 2 | 2.44 | 2.48 | 2.55 | 2.50 |
| 3 | 2.62 | 2.67 | 2.65 | 2.66 |
| 4 | 2.80 | 2.77 | 2.76 | 2.74 |
| 5 | 3.14 | 2.93 | 2.96 | 2.98 |

- **Ya no.** `ensamble`: b total = 0.97 (ee 0.16), con el total esperado calibrado quintil por quintil. `poisson_simple`,
  `dc` y `ajuste` exageran al doble (b ≈ 0.50 a 0.55); `poisson_simple` pronostica de 2.20 a 3.14 goles entre quintiles
  y se observan de 2.47 a 2.93.
- Por qué: `ajuste` reparte el total con mucho ruido (desviación 0.345) y `elo` casi no lo mueve (0.120); el promedio
  deja la mitad (0.197). Es, de hecho, el «encoger el total a la mitad» que `MERCADOS.md` §3 dejó como tarea.
- Lo que queda: el total esperado discrimina poco (correlación 0.12 con el observado). Bien calibrado, pero con poca
  señal.
- **Ensayo exploratorio (1 variante, dentro de muestra; el mismo de `MERCADOS.md` §3, lectura 3)**: encoger otra vez el total a
  la mitad de su distancia a la media, conservando el reparto local/visita. Con `ensamble` **empeora**:

| Mercado | d_ll encogido − actual (ee) | z |
|---|---:|---:|
| `AA_SI` | −0.0003 (0.0006) | −0.5 |
| `O15` | +0.0013 (0.0008) | 1.7 |
| `O25` | +0.0023 (0.0009) | **2.5** |
| `O35` | +0.0008 (0.0009) | 0.9 |
| `L_ANOTA` | +0.0002 (0.0005) | 0.5 |
| `V_ANOTA` | −0.0002 (0.0005) | −0.3 |
| `G1T_SI` | +0.0002 (0.0005) | 0.3 |
| `G2T_SI` | +0.0008 (0.0005) | 1.5 |
| `1X2` | +0.0008 (0.0003) | **3.2** |

### 5.5 Reparto por mitades

- **Centrado**: proporción del 1T pronosticada 0.4487 (local) y 0.4453 (visita) contra 0.4489 y 0.4487 observadas (ee
  0.008). Goles del 1T: 1.192 pronosticados contra 1.196; del 2T: 1.473 contra 1.468.
- **El sesgo de «gol en el 2T» (+1.5 puntos) no es de la media sino de cuándo caen los goles en los partidos de pocos
  goles.** La proporción del 1T es 0.422 en los partidos de 1 o 2 goles y 0.458 en los de 3 o más (diferencia −0.036,
  ee 0.012, z = −2.9; el corte en 2 goles se eligió después de ver la tabla). El adelgazamiento binomial usa la misma
  proporción para todos.
- Con el marcador final **observado** y la proporción del pasado, la binomial da 22.96% de partidos sin gol en el 2T;
  el modelo completo da 23.26% y lo observado es 21.74%. De los 1.52 puntos de sesgo, **1.22 son del reparto dentro del
  partido** (z = −1.9) y 0.30 de la distribución del marcador final (el 0-0 de más).
- En el 1T los dos efectos se cancelan (30.6% sin gol pronosticado contra 30.8%).
- Los goles de una mitad casi no dependen de los de la otra (correlación observada 0.03); el 2T está algo menos
  disperso que Poisson (varianza / media 0.93).

| Goles del partido | Partidos | Proporción observada en el 1T | Sin gol en el 1T: binomial | observado | Sin gol en el 2T: binomial | observado |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 529 | 0.406 | 0.553 | 0.594 | 0.447 | 0.406 |
| 2 | 738 | 0.428 | 0.306 | 0.324 | 0.200 | 0.179 |
| 3 | 663 | 0.455 | 0.169 | 0.166 | 0.089 | 0.097 |
| 4 | 427 | 0.464 | 0.093 | 0.068 | 0.040 | 0.035 |
| 5+ | 406 | 0.456 | 0.042 | 0.022 | 0.014 | 0.010 |

| Variable | Valor | Pronosticado | Observado | dif | z |
|---|---:|---:|---:|---:|---:|
| Goles en el 1T | 0 | 0.3063 | 0.3083 | +0.0020 | 0.2 |
| Goles en el 1T | 1 | 0.3583 | 0.3469 | −0.0115 | −1.3 |
| Goles en el 1T | 2 | 0.2162 | 0.2204 | +0.0042 | 0.5 |
| Goles en el 1T | 3+ | 0.1192 | 0.1245 | +0.0052 | 0.9 |
| Goles en el 2T | 0 | 0.2326 | 0.2174 | −0.0152 | −1.94 |
| Goles en el 2T | 1 | 0.3329 | 0.3472 | +0.0143 | 1.6 |
| Goles en el 2T | 2 | 0.2496 | 0.2509 | +0.0013 | 0.2 |
| Goles en el 2T | 3+ | 0.1849 | 0.1845 | −0.0004 | −0.1 |

### 5.6 El nivel de goles de la liga cambia de un tramo a otro

| Tramo (año) | n | Total pron. / obs. | dif del total (z) | Más de 2.5: dif (z) | Ambos anotan: dif (z) | Sin gol local / visita: dif | igual, con el nivel del tramo corregido | Dispersión local / visita | Gana por 2+ local / visita: dif | Gol 2T: dif |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2016-18 | 835 | 2.666 / 2.605 | −0.061 (−1.2) | −0.017 (−1.0) | +0.009 (0.5) | −0.004 / −0.004 | −0.011 / −0.013 | 0.94 / 0.92 | −0.016 / −0.022 | +0.004 |
| 2019-21 | 954 | 2.651 / 2.585 | −0.066 (−1.3) | −0.015 (−1.0) | +0.001 (0.1) | −0.009 / 0.000 | −0.017 / −0.009 | 0.91 / 0.97 | −0.012 / −0.015 | +0.024 |
| 2022-25 | 1,192 | 2.674 / 2.768 | +0.094 (**2.08**) | +0.037 (**2.6**) | +0.041 (**2.7**) | −0.025 / −0.022 | −0.016 / −0.007 | 0.90 / 0.96 | −0.022 / −0.008 | +0.016 |
| todo | 2,981 | 2.665 / 2.664 | −0.001 (0.0) | +0.005 (0.6) | +0.019 (**2.03**) | −0.014 / −0.010 | −0.015 / −0.009 | 0.91 / 0.95 | −0.017 / −0.014 | +0.015 |

«Con el nivel del tramo corregido»: ceros de Poisson con las lambdas multiplicadas por (goles observados / esperados) del
tramo. «Dispersión»: (observado − esperado)² medio entre la varianza de Poisson, con ese mismo nivel corregido. Los tramos
son por año calendario. Diagnóstico dentro de muestra: no es un pronóstico.

- En promedio el total está centrado (dif −0.001), pero **por tramos no**: sobrestimado 0.06 goles de 2016 a 2021 y
  subestimado 0.09 de 2022 a 2025 (z = 2.1). Entre los 18 torneos la diferencia tiene desviación 0.18 goles por
  partido contra 0.12 que daría el puro azar (ji cuadrada 35.6 con 18 grados de libertad, p = 0.008) y autocorrelación
  de 0.41 al primer rezago (ee ≈ 0.24: indicio, no prueba). Los otros modelos tienen el mismo retraso (ji cuadrada de
  34 a 41).
- Por eso el sesgo crudo de **ambos anotan se concentra en 2022-25** (+4.1 puntos, z = 2.7; +0.9 y +0.1 en los tramos
  anteriores) y «más de 2.5» pasa de −1.7 y −1.5 a +3.7 puntos (z = 2.6): en los tramos en que el nivel quedó alto,
  ese error tapó el exceso de ceros; cuando quedó bajo, se sumaron.
- Con el nivel de cada tramo corregido a mano (diagnóstico dentro de muestra), el exceso de ceros es estable: local
  −1.1, −1.7 y −1.6 puntos; visita −1.3, −0.9 y −0.7. La razón de dispersión del local es 0.94, 0.91 y 0.90.
- El exceso de victorias por 2 o más es negativo en las 6 casillas (tramo × lado).

Por torneo:

| Torneo | n | Total esperado | Total observado | dif |
|---|---:|---:|---:|---:|
| Apertura 2016 | 167 | 2.68 | 2.78 | +0.10 |
| Clausura 2017 | 167 | 2.69 | 2.46 | −0.23 |
| Apertura 2017 | 167 | 2.69 | 2.51 | −0.17 |
| Clausura 2018 | 167 | 2.64 | 2.60 | −0.04 |
| Apertura 2018 | 167 | 2.64 | 2.67 | +0.03 |
| Clausura 2019 | 167 | 2.66 | 2.69 | +0.03 |
| Apertura 2019 | 185 | 2.66 | 2.94 | +0.28 |
| Clausura 2020 | 90 | 2.70 | 2.89 | +0.19 |
| Apertura 2020 | 171 | 2.70 | 2.52 | −0.18 |
| Clausura 2021 | 170 | 2.63 | 2.39 | −0.24 |
| Apertura 2021 | 171 | 2.57 | 2.19 | −0.38 |
| Clausura 2022 | 170 | 2.54 | 2.59 | +0.06 |
| Apertura 2022 | 171 | 2.58 | 2.81 | +0.23 |
| Clausura 2023 | 171 | 2.67 | 2.80 | +0.12 |
| Apertura 2023 | 170 | 2.71 | 2.83 | +0.12 |
| Clausura 2024 | 170 | 2.71 | 2.86 | +0.15 |
| Apertura 2024 | 170 | 2.74 | 2.68 | −0.06 |
| Clausura 2025 | 170 | 2.76 | 2.81 | +0.04 |

### 5.7 Ceros por equipo

Pronosticado contra observado de «el equipo se queda sin anotar» y de «deja en cero al rival», juntando sus partidos de
local y de visita (z binomial simple).

| Equipo | Partidos | Se queda sin gol: pron. | obs. | dif | z | Deja en cero al rival: pron. | obs. | dif | z |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Morelia | 142 | 0.283 | 0.197 | −0.086 | **−2.3** | 0.244 | 0.204 | −0.040 | −1.1 |
| Atlético San Luis | 214 | 0.320 | 0.280 | −0.039 | −1.2 | 0.217 | 0.206 | −0.011 | −0.4 |
| Necaxa | 317 | 0.302 | 0.265 | −0.037 | −1.4 | 0.265 | 0.256 | −0.009 | −0.4 |
| Toluca | 338 | 0.254 | 0.219 | −0.035 | −1.5 | 0.276 | 0.234 | −0.042 | −1.7 |
| Cruz Azul | 342 | 0.259 | 0.225 | −0.034 | −1.4 | 0.317 | 0.333 | +0.017 | 0.7 |
| América | 372 | 0.212 | 0.183 | −0.029 | −1.4 | 0.342 | 0.371 | +0.029 | 1.2 |
| Chivas | 332 | 0.286 | 0.262 | −0.024 | −1.0 | 0.301 | 0.304 | +0.003 | 0.1 |
| Monterrey | 355 | 0.221 | 0.203 | −0.019 | −0.8 | 0.331 | 0.304 | −0.027 | −1.1 |
| Mazatlán | 172 | 0.326 | 0.308 | −0.018 | −0.5 | 0.208 | 0.192 | −0.017 | −0.5 |
| León | 335 | 0.242 | 0.224 | −0.018 | −0.8 | 0.288 | 0.269 | −0.020 | −0.8 |
| Puebla | 319 | 0.307 | 0.292 | −0.016 | −0.6 | 0.245 | 0.213 | −0.032 | −1.3 |
| Juárez | 200 | 0.351 | 0.340 | −0.011 | −0.3 | 0.222 | 0.190 | −0.032 | −1.1 |
| Querétaro | 305 | 0.325 | 0.318 | −0.007 | −0.2 | 0.237 | 0.230 | −0.007 | −0.3 |
| Tigres | 366 | 0.227 | 0.227 | −0.001 | 0.0 | 0.356 | 0.380 | +0.024 | 1.0 |
| Santos | 330 | 0.258 | 0.258 | 0.000 | 0.0 | 0.269 | 0.209 | −0.060 | **−2.4** |
| Atlas | 322 | 0.323 | 0.326 | +0.003 | 0.1 | 0.261 | 0.261 | 0.000 | 0.0 |
| Pumas | 331 | 0.278 | 0.281 | +0.003 | 0.1 | 0.269 | 0.275 | +0.006 | 0.3 |
| Tijuana | 316 | 0.309 | 0.320 | +0.010 | 0.4 | 0.246 | 0.228 | −0.018 | −0.7 |
| Pachuca | 332 | 0.239 | 0.250 | +0.011 | 0.5 | 0.299 | 0.277 | −0.022 | −0.9 |
| Lobos BUAP | 68 | 0.293 | 0.309 | +0.015 | 0.3 | 0.205 | 0.191 | −0.013 | −0.3 |
| Veracruz | 120 | 0.368 | 0.483 | +0.115 | **2.6** | 0.195 | 0.167 | −0.028 | −0.8 |
| Chiapas | 34 | 0.325 | 0.471 | +0.146 | 1.8 | 0.203 | 0.235 | +0.033 | 0.5 |

- De los 20 equipos con 100 partidos o más, **15 se quedan sin gol menos veces de lo pronosticado** y 15 dejan en cero
  al rival menos veces de lo pronosticado. La desviación de z entre equipos es 1.03 y 0.89 (1 = sólo ruido): el
  sesgo es general, no de unos cuantos equipos.
- Extremos en ataque: Morelia (−8.6 puntos, z = −2.3; 142 partidos) y Veracruz (+11.5, z = +2.6; 120 partidos); en
  portería, Santos (−6.0, z = −2.4). Tres de 44 comparaciones por encima de 2 ee: poco más de lo esperable por azar.

### 5.8 Cada sesgo de más de 2 ee, con su origen

| Mercado | Sesgo | De dónde sale |
|---|---|---|
| Ambos anotan (`AA_SI` / `AA_NO`) | +0.019 (z = 2.0) | Ceros de más por equipo: +1.39 local, +0.99 visita, −0.45 del 0-0 (§5.1). Causa: goles menos dispersos que Poisson (§5.2). El rho ayuda 0.67 puntos (§5.3). No es de la media ni de la dispersión de las lambdas (§5.4). En el tiempo: +4.1 puntos en 2022-25, cuando además el nivel de goles quedó 0.09 bajo (§5.6). |
| Local gana por 2+ (`H_L-1.5` / `H_V+1.5`) | −0.017 (z = −2.2) | Diferencia de goles con 90% de la varianza del modelo (z = −4.0): la mitad por la subdispersión del local, un tercio por la covarianza positiva entre los dos marcadores (§5.2). El rho no toca diferencias de 2 o más. Negativo en los tres tramos. |
| Visita gana por 2+ (`H_V-1.5` / `H_L+1.5`) | −0.014 (z = −2.5) | Lo mismo. Ya estaba con `poisson_simple` (z = −2.5). |
| Local anota (`L_ANOTA` / `PC_V`), z = 1.98 | +0.014 | Ceros de más del local (§5.1, §5.2). |
| Gol en el 2T (`G2T_SI` / `G2T_NO`), z = 1.94 | +0.015 | 1.22 puntos del reparto dentro del partido (en partidos de 1 o 2 goles, los goles caen más en el 2T) y 0.30 del 0-0 de más (§5.5). |

## 6. Correcciones candidatas (de la más simple a la más ambiciosa; lo que se probó después está en §8 y §9)

**Cuánto se puede ganar.** Corregir un sesgo constante de δ en un mercado binario de probabilidad p mejora el log-loss
en δ² / (2·p·(1−p)): 0.0007 en ambos anotan, 0.0008 en «local gana por 2+», 0.0009 en «visita gana por 2+», 0.0005
en «local anota» y 0.0006 en «gol en el 2T». La z pareada de esa mejora es más o menos la mitad de la z del sesgo:
**≈ 1 a 1.2** con los 2,981 partidos de desarrollo. Ninguna corrección de un solo mercado puede pasar la regla de 2 ee; sólo una que arregle
varios a la vez con los mismos parámetros (candidata 3, cuya evidencia es z = −3.3 a −4.0) tiene con qué.

| # | Candidata | Qué hace | Parámetros libres | Riesgos |
|---|---|---|---:|---|
| 1 | **Recalibración por mercado, ajustada sólo con el pasado** | Para cada suceso binario con sesgo (ambos anotan, local anota, visita anota, gol en el 2T, gana por 2+ de cada lado): `logit(p') = a + logit(p)`, con `a` estimado en cada corte con los partidos anteriores (ventana expansiva o de 6 años). Las pendientes ya están en 1: no hace falta el segundo parámetro. | 6 (uno por suceso; 12 con pendiente) | **Rompe la coherencia**: P(ambos anotan) deja de ser 1 − P(local 0) − P(visita 0) + P(0-0), los mercados sueltos dejan de sumar con la matriz de marcadores que muestra la página y con la conjunta exacta de la combinada (que se calcula sobre las celdas). No toca el 1X2. Sobreajuste bajo, pero **el sesgo no es estable en el tiempo** (ambos anotan: +0.9, +0.1 y +4.1 puntos por tramo): un intercepto aprendido hasta 2021 habría valido ≈ +0.5 puntos cuando el sesgo fue de +4; corrige poco y tarde. Ganancia esperada < 0.001 por mercado (z ≈ 1). |
| 2 | **Reparto por mitades que depende del total** | En `celdas()`, la proporción del 1T pasa a depender del marcador final: una para partidos de 1 o 2 goles (≈ 0.42) y otra para 3 o más (≈ 0.46), estimadas con la misma ventana de 6 años anterior al corte. | 1 (2 si se separa local y visita) | **Conserva la coherencia** (sigue siendo una conjunta sobre las mismas celdas y su marginal de tiempo completo es `M`): no toca 1X2, totales ni ambos anotan. Sólo corrige mitades (gol en el 2T: de 1.5 a ≈ 0.3 puntos). El corte en 2 goles se eligió mirando desarrollo (z = −2.9 sin descontar eso). Ganancia ≈ 0.0006 en un mercado: no pasará de 2 ee. Hay que rehacer las pruebas que fijan la construcción binomial (`test_conjunta_coincide_con_monte_carlo`, `test_conjunta_con_mitades_poisson_independientes`). |
| 3 | **Forma de la matriz conjunta: subdispersión y dependencia** | Sustituir «Poisson + Dixon-Coles» por una conjunta con un parámetro de dispersión por lado (o uno común) que quite masa al 0 y al 4+ conservando la media, y uno de dependencia que estreche la diferencia de goles (hoy el rho sólo mueve 0-0, 1-0, 0-1 y 1-1). Estimados en cada corte por verosimilitud perfilada dadas las lambdas, como hoy el rho. | 2 a 3 | **Conserva la coherencia** y ataca la causa común de ambos anotan, anota / no anota y gana por 2+. Pero **cambia el 1X2** (menos varianza en la diferencia = más empates y victorias por uno; hoy el 1X2 está centrado, z de 0.1 a 1.0), el marcador exacto, el simulador y la liguilla, porque todos usan `arnes.matrices_marcadores`: es un cambio de modelo y debe pasar por `modelo.mejora` (2 ee pareados en 1X2 y no peor en los últimos 8 bloques) y por la log-verosimilitud del marcador. Hay que reparametrizar para que la media no se mueva. Evidencia de z = −3.3 a −4.0: la ganancia pareada esperable ronda 2 ee, en el límite. Riesgo de implementación alto (`ARNES.md` §4 fija esa matriz contra el motor previo a 1e-16). |
| 4 | **Nivel de goles de la liga más reciente** | Factor común sobre las dos lambdas (conserva el reparto local/visita) = goles observados / esperados de la liga en los últimos N partidos, encogido hacia 1. Ataca el retraso de §5.6 (2022-25: 0.09 goles bajo; más de 2.5 con +3.7 puntos y ambos anotan con +4.1). | 1 a 2 (ventana y encogimiento) | Es un cambio en las lambdas: pasa por `modelo.mejora` y mueve un poco el 1X2. **La evidencia de persistencia es débil** (autocorrelación 0.41 entre torneos con ee 0.24; ji cuadrada p = 0.008 de que el nivel varía, no de que sea predecible): riesgo real de perseguir ruido y de sobreajustar al tramo 2022-25. No corrige el exceso de ceros, que es estable. |

**Descartada por los datos (no es candidata):** encoger el total esperado conservando el reparto local/visita. Era la
propuesta de `MERCADOS.md` §3 (lectura 3) para `poisson_simple` (b total 0.50). Con `ensamble` el total ya está en su tamaño (b =
0.97, ee 0.16) y encogerlo empeora más de 2.5 (+0.0023, z = 2.5) y el 1X2 (+0.0008, z = 3.2) (§5.4).

Orden sugerido si se decide probar algo: la 2 es barata y no rompe nada, pero rinde poco; la 3 es la única que va a la
causa y la única con evidencia suficiente para aspirar a 2 ee; la 1 sólo si se acepta que los mercados sueltos dejen
de cuadrar con la matriz; la 4 necesita antes una medición walk-forward de si el nivel es predecible. Cualquier prueba
debe registrarse (`arnes.registrar`) y contar sus variantes.

## 7. Pendientes y reservas

- Las cifras son de DESARROLLO por bloque. Producción recalcula por día; `ensamble__dia` no existe en `modelo/pred/`
  y no se midió.
- Los dos comandos `validar` siguen usando rho = 0 con `ensamble` (§1).
- La combinada de jornada sigue sin validación propia (`MERCADOS.md` §5).
- La página hoy muestra «ambos anotan» ≈ 2 puntos corto, «gana por 2 o más» ≈ 1.5 largo y «gol en el 2T» ≈ 1.5 corto:
  sesgos de 2 ee, del tamaño del redondeo que ve el usuario, y la combinada los absorbe (queda calibrada).
- No se midió nada en PRUEBA: con 480 partidos un sesgo de 2 puntos tiene un error de ≈ 2.3 puntos y no se
  distinguiría de cero.

## 8. Regla de adopción de correcciones (escrita el 2026-11-15, ANTES de probar ninguna)

Esta sección se escribió antes de programar o correr cualquier corrección. Lo único medido hasta aquí es lo de las
secciones 1 a 7 (ninguna corrección; un ensayo exploratorio dentro de muestra, §5.4).

### 8.1 La regla

Una corrección se adopta **sólo si**, en walk-forward sobre DESARROLLO (ajustada en cada corte únicamente con partidos
anteriores a ese corte):

1. **mejora** el log-loss de los mercados que pretende corregir en **más de 2 errores estándar pareados** (bootstrap de
   bloques);
2. **deja el sesgo** de cada uno de esos mercados **dentro de 2 errores estándar**;
3. **no empeora en más de 1 error estándar** ni el 1X2, ni el marcador exacto, ni ninguna otra familia de mercados, ni
   la calibración de las combinadas.

Entre las variantes que cumplan, gana **la de menos parámetros**. **Máximo 4 variantes**; se informan todas, también
las que fallen. Si ninguna cumple, no se adopta nada.

### 8.2 Cómo se mide cada condición (fijado de antemano; no se retoca después de ver resultados)

- **Referencia**: lo que se publica hoy, `ensamble` con su rho (el de la matriz guardada, §1) y el reparto por mitades
  de `MERCADOS.md` §1. Mismos 2,981 partidos y 510 bloques. Toda diferencia es `corrección − referencia`, pareada por
  partido, con el bootstrap de bloques del arnés (`metricas.diferencia_pareada`, 2,000 réplicas, semilla del arnés).
- **Walk-forward**: para cada partido, los parámetros de la corrección se estiman con los partidos de DESARROLLO con
  `fecha_utc` anterior al corte de su bloque, usando las predicciones walk-forward ya guardadas de esos partidos
  (`modelo/pred/ensamble.parquet` y su matriz en caché). No hay predicciones guardadas anteriores a Apertura 2016, así
  que la ventana es expansiva desde el primer partido de DESARROLLO.
- **Encogimiento** (uno solo, igual para todas las variantes que se estiman con predicciones): el parámetro estimado
  con `n` partidos previos se usa multiplicado por `n / (n + 300)` hacia «sin corrección» (300 ≈ un año de partidos).
  Con `n = 0` no hay corrección. El 300 no se ajusta. Los 2,981 partidos entran a la calificación, también los
  primeros, donde la corrección es casi nula.
- **Condición 1**: por partido se suma el log-loss binario de los sucesos objetivo de la variante (uno por par
  complementario); se exige `d / ee < −2` en esa suma.
- **Condición 2**: para cada suceso objetivo, `|observado − pronosticado| / ee ≤ 2` (ee por bloques).
- **Condición 3** («empeora en más de 1 ee» = la diferencia va en contra y su valor absoluto supera 1 ee pareado):
  (a) log-loss del 1X2; (b) log-verosimilitud del marcador exacto; (c) cada una de las familias del catálogo
  (`resultado`, `total`, `ambos`, `goles_local`, `goles_visita`, `descanso`, `goles_1t`, `goles_2t`, `mitades`,
  `gana_mitad`, `descanso_final`): suma por partido del log-loss de sus mercados combinables, sin contar los sucesos
  objetivo ni sus complementos; (d) combinadas, en cada una de las tres variantes (`segura`, `equilibrada`,
  `atrevida`): el log-loss de la conjunta anunciada contra «se cumplieron los cuatro picks» no empeora en más de 1 ee
  pareado y `|frecuencia − anunciada| / ee ≤ 2`.
- **Desempate**: menos parámetros; a igualdad, la que conserva una sola distribución conjunta.
- **Conteo**: cada variante se corre una vez con la configuración declarada abajo. Corregir un error de programación
  demostrable no cuenta como variante nueva, pero se informa. No hay segunda vuelta de hiperparámetros.
- **PRUEBA**: no se lee. La confirmación la hace después un auditor independiente, una sola vez.

### 8.3 Las cuatro variantes declaradas

Ninguna cambia las lambdas del modelo ni el 1X2: las cuatro dejan `P(local)`, `P(empate)` y `P(visita)` exactamente
como hoy. La 1 y la 2 **sí cambian las probabilidades de marcador exacto** (y, si se adoptan, el marcador más probable
que se publica y se sella): por eso la regla exige que el marcador exacto no empeore.

| # | Variante | Qué hace | Parámetros | Sucesos objetivo |
|---|---|---|---:|---|
| 1 | `forma_1` | Matriz de marcadores con dispersión libre: cada marginal pasa de Poisson a Conway-Maxwell-Poisson con la misma media y un exponente común `nu` (`nu` = 1 es la matriz de hoy; `nu` > 1 quita masa al 0 y a las goleadas), con la misma corrección de Dixon-Coles; después se reescalan las tres regiones (`arnes.ajustar_M_a_1x2`) para que el 1X2 sea exactamente el del modelo. `nu` se estima en cada corte por máxima verosimilitud del marcador exacto. Los 56 mercados y las combinadas salen de esa única matriz. | 1 | `AA_SI`, `L_ANOTA`, `V_ANOTA`, `H_L-1.5`, `H_V-1.5` |
| 2 | `forma_2` | La 1 más un parámetro de dependencia `kappa`: la matriz se multiplica por `exp(kappa·(x − lam_l)·(y − lam_v) / raíz(lam_l·lam_v))` (`kappa` > 0 = los dos marcadores suben o bajan juntos, la diferencia de goles se estrecha), antes de fijar el 1X2. `nu` y `kappa` se estiman juntos. | 2 | los mismos 5 |
| 3 | `recal_6` | Recalibración suelta: `logit(p') = a + logit(p)` con un intercepto por suceso, estimado por máxima verosimilitud con el pasado. **No es coherente** (los mercados dejan de salir de una sola matriz); se mide como referencia de cuánto da corregir cada mercado de frente. Si fuera la única que cumple, antes de adoptarla habría que montarla sobre las celdas (ajuste proporcional iterativo) y repetir la condición 3 dentro de esta misma variante. | 6 | los 5 anteriores y `G2T_SI` |
| 4 | `mitades_total` | La proporción de goles del primer tiempo depende del total del partido: una para partidos de 1 o 2 goles y otra para 3 o más, por lado, con la misma ventana de 6 años anterior al corte (conteos de `goles.csv`, sin encogimiento: hay ≈ 2,000 partidos en cada corte). La marginal de tiempo completo sigue siendo la matriz del modelo. El corte en 2 goles se eligió mirando DESARROLLO (§5.5). | 2 (de más) | `G2T_SI` |

Qué se espera, dicho antes de medir (§6): la ganancia posible es del orden de 0.001 de log-loss por mercado; la 3 y la
4 difícilmente llegarán a 2 ee; la 1 y la 2 están en el límite.

## 9. Resultado: ninguna corrección cumple la regla; no se adopta nada (2026-11-15)

Las cuatro variantes de §8.3 se corrieron **una vez cada una**, con la configuración declarada, en walk-forward sobre
los 2,981 partidos de DESARROLLO (510 bloques). No hubo repeticiones, ni errores de programación que corregir, ni
variantes adicionales. PRUEBA no se leyó (ninguna línea nueva en `ACCESOS_PRUEBA.log`). No se tocó código de
producción: lo que se publica sigue siendo exactamente lo de antes. Las cuatro quedaron anotadas en
`modelo/registro_variantes.jsonl` (familia `mercados_correccion`).

### 9.1 Veredicto por variante

`d` = corrección − referencia (negativo = mejora, salvo en el marcador exacto, donde positivo = mejora); entre
paréntesis el error estándar pareado por bloques.

| Variante | Parámetros | 1. Mejora en los objetivos (se exige z < −2) | 2. Sesgo de los objetivos (mayor \|z\| después) | 3a. 1X2 | 3b. Marcador exacto | 3c. Familias | 3d. Combinadas | ¿Cumple? |
|---|---:|---|---|---|---|---|---|---|
| `forma_1` | 1 | −0.00159 (0.00113), **z = −1.41**: no | 1.96: sí | idéntico | +0.00136 (0.00087), mejora 1.6 ee | **falla**: `descanso` +0.00029 (0.00021), z = +1.39 | sí | **No** |
| `forma_2` | 2 | −0.00211 (0.00133), **z = −1.59**: no | 1.46: sí | idéntico | +0.00145 (0.00104), mejora 1.4 ee | sí | **falla**: `equilibrada` queda 2.2 ee corta y su log-loss empeora 1.3 ee | **No** |
| `recal_6` | 6 | −0.00112 (0.00146), **z = −0.77**: no | 1.16: sí | no lo toca | no lo toca | no las toca | no las toca | **No** |
| `mitades_total` | 2 | −0.00044 (0.00038), **z = −1.16**: no | 0.90: sí | idéntico | idéntico | **falla** por un margen diminuto: `gana_mitad` +0.00004 (0.00003), z = +1.24 | sí | **No** |

**Ninguna pasa la condición 1** (la mejor se queda en 1.6 ee) y tres de las cuatro fallan además alguna parte de la
condición 3. Conforme a la regla, **no se adopta ninguna**.

### 9.2 Detalle

Sesgo de los sucesos objetivo (pronosticado medio; z = (observado − pronosticado) / ee):

| Suceso | Observado | Hoy | z | `forma_1` | z | `forma_2` | z | `recal_6` | z | `mitades_total` | z |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ambos anotan (`AA_SI`) | 0.5428 | 0.5235 | 2.03 | 0.5353 | 0.79 | 0.5384 | 0.45 | 0.5317 | 1.16 | — | — |
| Local anota (`L_ANOTA`) | 0.7836 | 0.7697 | 1.98 | 0.7779 | 0.81 | 0.7783 | 0.76 | 0.7767 | 0.98 | — | — |
| Visita anota (`V_ANOTA`) | 0.6860 | 0.6761 | 1.16 | 0.6852 | 0.09 | 0.6868 | −0.09 | 0.6792 | 0.80 | — | — |
| Local gana por 2+ (`H_L-1.5`) | 0.2184 | 0.2352 | −2.18 | 0.2318 | −1.73 | 0.2283 | −1.28 | 0.2236 | −0.68 | — | — |
| Visita gana por 2+ (`H_V-1.5`) | 0.1104 | 0.1244 | −2.46 | 0.1216 | −1.96 | 0.1187 | −1.46 | 0.1122 | −0.32 | — | — |
| Gol en el 2T (`G2T_SI`) | 0.7826 | 0.7674 | 1.94 | 0.7722 | 1.32 | 0.7707 | 1.52 | 0.7762 | 0.82 | 0.7755 | 0.90 |

(En `forma_1` y `forma_2` «gol en el 2T» no era objetivo: se mueve porque cambia la matriz.)

Mejora pareada por suceso objetivo (`d` de log-loss; z):

| Suceso | `forma_1` | `forma_2` | `recal_6` | `mitades_total` |
|---|---:|---:|---:|---:|
| `AA_SI` | −0.0004 (−0.8) | −0.0004 (−0.7) | −0.0002 (−0.5) | — |
| `L_ANOTA` | −0.0004 (−1.1) | −0.0004 (−1.1) | −0.0001 (−0.4) | — |
| `V_ANOTA` | −0.0001 (−0.3) | −0.0001 (−0.1) | +0.0003 (+0.9) | — |
| `H_L-1.5` | −0.0003 (−1.5) | −0.0006 (−1.7) | −0.0004 (−0.6) | — |
| `H_V-1.5` | −0.0004 (−2.0) | −0.0007 (−2.0) | −0.0004 (−0.6) | — |
| `G2T_SI` | — | — | −0.0002 (−0.3) | −0.0004 (−1.2) |

Familias (condición 3c; suma del log-loss de los mercados de la familia que no son objetivo; `d` (z)):

| Familia | `forma_1` | `forma_2` | `mitades_total` |
|---|---:|---:|---:|
| `resultado` (1X2 y doble oportunidad) | 0 | 0 | 0 |
| `total` | −0.00007 (−0.1) | −0.00028 (−0.5) | 0 |
| `goles_local` | −0.00021 (−1.2) | −0.00014 (−0.7) | 0 |
| `goles_visita` | +0.00000 (0.0) | +0.00005 (+0.2) | 0 |
| `descanso` | **+0.00029 (+1.4)** | −0.00011 (−0.4) | −0.00097 (−1.0) |
| `goles_1t` | +0.00022 (+0.5) | +0.00011 (+0.3) | +0.00033 (+0.4) |
| `goles_2t` | −0.00073 (−1.5) | −0.00057 (−1.5) | (objetivo) |
| `mitades` | −0.00024 (−1.0) | −0.00023 (−0.8) | −0.00001 (0.0) |
| `gana_mitad` | −0.00011 (−0.5) | −0.00011 (−0.5) | **+0.00004 (+1.2)** |
| `descanso_final` | −0.00037 (−1.1) | −0.00059 (−1.4) | −0.00043 (−0.9) |

Combinadas (condición 3d; anunciada / frecuencia / z; `d` del log-loss de la conjunta anunciada (z)):

| Variante de combinada | Hoy | `forma_1` | `forma_2` | `mitades_total` |
|---|---|---|---|---|
| `segura` | 0.481 / 0.486 / 0.5 | 0.483 / 0.486 / 0.3; −0.0004 (−0.4) | 0.481 / 0.484 / 0.3; −0.0004 (−0.4) | 0.485 / 0.486 / 0.1; +0.0001 (+0.2) |
| `equilibrada` | 0.333 / 0.343 / 1.3 | 0.331 / 0.346 / 1.9; +0.0004 (+0.1) | 0.333 / 0.351 / **2.2**; **+0.0041 (+1.3)** | 0.335 / 0.344 / 1.0; −0.0008 (−0.4) |
| `atrevida` | 0.203 / 0.209 / 0.7 | 0.200 / 0.206 / 0.8; −0.0043 (−1.1) | 0.200 / 0.207 / 0.9; −0.0032 (−0.6) | 0.205 / 0.207 / 0.2; −0.0045 (−1.2) |

Con la matriz corregida cambian los picks elegidos en 11 a 19% de las combinadas (10% en `mitades_total`).

Parámetros estimados en el recorrido:

- `forma_1`: `nu` crudo 0.72 con 54 partidos, 1.00 con 300, 1.08 con 600, 1.09 con 1,000, 1.13 con 2,000 y **1.11 con
  todo DESARROLLO** (varianza de cada marginal ≈ 93% de la de Poisson). Usado (encogido): media 1.077, de 0.924 a
  1.116. Los goles esperados casi no se mueven al fijar el 1X2 (local 1.513 → 1.511; visita 1.151 → 1.155).
- `forma_2`: con todo DESARROLLO, `nu` = 1.12 y `kappa` = 0.035. `kappa` arrancó en 0.18 (150 partidos) y 0.16 (300),
  bajó a 0.06 (600) y se estabilizó en 0.03 a 0.04 desde los 1,000.
- `recal_6`: interceptos al final del recorrido (logit, ya encogidos): ambos anotan +0.071, local anota +0.074,
  visita anota +0.043, local por 2+ −0.093, visita por 2+ −0.127, gol en el 2T +0.079.
- `mitades_total`: proporción del primer tiempo, media del recorrido: local 0.427 (partidos de 1 o 2 goles) y 0.456
  (3 o más); visita 0.416 y 0.456. Hoy se usa 0.449 y 0.445 para todos.

### 9.3 Lectura

1. **Las correcciones van en la dirección correcta, pero lo que ganan no se distingue del ruido.** Con `forma_1` o
   `forma_2` ningún mercado queda con sesgo de más de 2 ee (hoy son 6, contando complementos), el marcador exacto
   mejora 0.0014 (1.4 a 1.6 ee) y 18 de los 52 mercados binarios mejoran más de 1 ee contra 4 (o ninguno) que
   empeoran. Pero la suma de log-loss de los cinco sucesos objetivo mejora 0.0016 a 0.0021 (de 0.0001 a 0.0007 por
   suceso), **1.4 a 1.6 ee**. Es lo que §6 anticipaba: un techo de 0.0005 a 0.0009 por mercado, en el límite de lo
   demostrable con 2,981 partidos.
2. **Con cuatro intentos, 1.6 ee es lo que da el azar.** La mayor de N diferencias nulas ronda `ee·raíz(2·ln N)`
   (`ARNES.md` §6): 1.67 ee con N = 4. La mejor variante quedó en 1.59.
3. **La recalibración suelta rinde menos que corregir la matriz** (z = −0.77 contra −1.41 con un solo parámetro):
   seis interceptos aprendidos sobre la marcha persiguen un sesgo que no es estable (§5.6) y en «visita anota»
   empeoran. No hay motivo para romper la coherencia.
4. **Costos medidos de las que cambian la matriz**: `forma_1` empeora un poco el resultado al descanso (el empate al
   descanso pasa de 1.6 a 1.8 ee corto); `forma_2` deja la combinada `equilibrada` anunciando 1.8 puntos menos de lo
   que ocurre (2.2 ee). Son efectos chicos, pero la regla los cuenta y están escritos de antemano.
5. **Cuántos partidos harían falta.** Si la mejora de `forma_1` fuera real y del tamaño medido (0.0016, desviación
   pareada por partido 0.062), verla a 2 ee pide unos 6,000 partidos (unos 4,700 para `forma_2`): el doble de
   DESARROLLO. Los 480 de PRUEBA no pueden confirmarla ni desmentirla (ee ≈ 0.003 contra un efecto de 0.0016), así
   que **no hay nada que llevar a PRUEBA** y no conviene gastar una lectura en esto.
6. **Qué queda en la página**: lo mismo que en §7. «Ambos anotan» ≈ 2 puntos corto, «gana por 2 o más» ≈ 1.5 puntos
   largo y «gol en el 2T» ≈ 1.5 puntos corto, sesgos de 2 ee y del tamaño del redondeo; las combinadas siguen
   calibradas con la matriz de hoy.

### 9.4 Conteo y archivos

- **Variantes probadas: 4 correcciones** (todas informadas arriba; ninguna adoptada), además de lo ya contado en la
  medición (3 configuraciones de medición y 1 ensayo exploratorio dentro de muestra). No se hizo ningún ensayo
  dentro de muestra de las correcciones.
- Código de evaluación (temporal, fuera del repositorio, no forma parte de producción):
  `/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/mercados/forma.py` (matriz con
  dispersión y dependencia) y `evaluar_variantes.py` (walk-forward y las tres condiciones); salidas `eval_a.out`,
  `eval_b.out`, `<variante>.pkl`, `params_forma_*.pkl` y `combinadas_<variante>.parquet` en la misma carpeta.
- Comprobaciones del código antes de medir: con `nu` = 1 y `kappa` = 0 la matriz es la del arnés (diferencia 1e-16);
  la media de cada marginal se conserva a 1e-15; el 1X2 queda idéntico al del modelo (3e-15); nadie se pronostica con
  partidos de su propio bloque (aserción en el guion).

### 9.5 Si se quiere volver a intentar

- No repetir estas cuatro sobre el mismo DESARROLLO con otros hiperparámetros (el 300, las mallas, el corte en 2
  goles): sería elegir mirando el resultado.
- La vía con más sustento sigue siendo la forma de la matriz (candidata 3 de §6), pero como **cambio de modelo** por
  `modelo.mejora` (ahí también movería el 1X2) o repitiendo `forma_1` tal cual, con esta misma regla, cuando haya
  bastantes más partidos pronosticados fuera de muestra.
- El aviso de §1 (los comandos `validar` corren con rho = 0) sigue pendiente.
