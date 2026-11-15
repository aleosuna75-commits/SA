# -*- coding: utf-8 -*-
"""Escribe produccion/MERCADOS_ENSAMBLE.md con las tablas de fragmentos.json."""
import json

SAL = "/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/mercados"
F = json.load(open(f"{SAL}/fragmentos.json"))

DOC = r"""# Mercados y combinada con el modelo de producción (`ensamble`)

Medición del **2026-11-15**. Repite las dos validaciones de `MERCADOS.md` (§3 y §4), que se escribieron con el
provisional `poisson_simple`, con el modelo que hoy está en `modelo/campeon.json`: `ensamble` (promedio de las lambdas
de `ajuste` y `elo`, con rho de Dixon-Coles). **Sólo mide y diagnostica**: no cambia código de producción, no adopta
nada y no toca `MERCADOS.md`.

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

{mercados56}

1X2 al descanso como pronóstico de tres clases: log-loss **1.0520** contra 1.0662 de la constante (−0.0142, ee 0.0034);
con `poisson_simple` era 1.0560 (pareada −0.0039, ee 0.0010).

Pronosticado contra observado por deciles (n ≈ 298 por decil; en el 1X2 al descanso se juntan las tres clases, n ≈ 894):

{deciles}

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

{comparacion}

| | Qué pasó |
|---|---|
| **Mejoró** | Totales (pendiente 0.48–0.65 → 0.91–1.26; los tres pasan a ganarle a la constante). Anota / no anota (pendiente 0.76–0.82 → 1.04–1.09; sesgo del local de 3.0 a 2.0 ee). Ambos anotan (sesgo de 3.4 a 1.9 puntos; deja de perder contra la constante: +0.0050 → −0.0001; pareada −0.0051, z = −3.9). Empate (z del sesgo 2.3 → 0.9, por el rho). Gana visita (sesgo de −1.5 a −0.7 puntos, z = −2.0 → −1.0). Goles por mitad (pendientes 0.42–0.62 → 0.78–1.29). 1X2 al descanso (−0.0039, ee 0.0010). Resultado, hándicap, gana alguna mitad y descanso/final local/local y visita/visita (pareadas de −0.002 a −0.005). |
| **Empeoró** | Nada por más de 1.2 ee en log-loss. En sesgo, «local gana por 2+» pasa de −0.013 (z = −1.7) a −0.017 (z = −2.2): la media de goles del local subió de 1.495 a 1.513 y la forma de la distribución no cambió. |
| **Sigue igual** | «Visita gana por 2+» sobrestimado (z = −2.5 antes y ahora). Empate al descanso corto 1.5 puntos (z = 1.5 → 1.6). Gol en el 2T corto 1.9 → 1.5 puntos (z = 2.4 → 1.9). Mitad con más goles y descanso/final con vuelco: sin información. |

## 4. Combinada del partido (desarrollo, mismas reglas y bandas de `MERCADOS.md` §4)

En cada partido se armaron las tres combinadas con lo conocido antes del corte y se contó si se cumplieron los cuatro
picks. `d_ll contra constante` = log-loss de la conjunta anunciada menos el de anunciar siempre la frecuencia media de
la variante; `pendiente` = recalibración logística de la conjunta anunciada.

{combinada}

Por deciles de la probabilidad conjunta anunciada (`ensamble` con su rho, n ≈ 298 por decil):

{combinada_deciles}

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

{ceros}

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

{distribuciones}

Dispersión por partido: media de (observado − esperado)² contra la varianza que el modelo le asigna a ese partido.

{dispersion_partido}

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

{ceros_por_lambda}

### 5.3 Efecto del rho de Dixon-Coles

{celdas}

{efecto_rho}

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

{dispersion}

{quintiles_total}

- **Ya no.** `ensamble`: b total = 0.97 (ee 0.16), con el total esperado calibrado quintil por quintil. `poisson_simple`,
  `dc` y `ajuste` exageran al doble (b ≈ 0.50 a 0.55); `poisson_simple` pronostica de 2.20 a 3.14 goles entre quintiles
  y se observan de 2.47 a 2.93.
- Por qué: `ajuste` reparte el total con mucho ruido (desviación 0.345) y `elo` casi no lo mueve (0.120); el promedio
  deja la mitad (0.197). Es, de hecho, el «encoger el total a la mitad» que `MERCADOS.md` §3 dejó como tarea.
- Lo que queda: el total esperado discrimina poco (correlación 0.12 con el observado). Bien calibrado, pero con poca
  señal.
- **Ensayo exploratorio (1 variante, dentro de muestra; el mismo de `MERCADOS.md` §3, lectura 3)**: encoger otra vez el total a
  la mitad de su distancia a la media, conservando el reparto local/visita. Con `ensamble` **empeora**:

{encoger}

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

{adelgazamiento}

{dist_mitades}

### 5.6 El nivel de goles de la liga cambia de un tramo a otro

{tramos}

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

{torneos}

### 5.7 Ceros por equipo

Pronosticado contra observado de «el equipo se queda sin anotar» y de «deja en cero al rival», juntando sus partidos de
local y de visita (z binomial simple).

{equipos}

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

## 6. Correcciones candidatas (de la más simple a la más ambiciosa; ninguna implementada)

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
"""

for k, v in F.items():
    if isinstance(v, str):
        DOC = DOC.replace("{" + k + "}", v)
assert "{" not in DOC.replace("{id}", ""), [x for x in DOC.split("{")[1:]][:3]
open("/home/user/SA/ligamx/produccion/MERCADOS_ENSAMBLE.md", "w").write(DOC)
print(len(DOC.splitlines()), "lineas")
