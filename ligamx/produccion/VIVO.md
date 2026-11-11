# Motor en vivo de Cerebro Liga MX

Qué hay: `vivo.py` (consulta ESPN, arma el documento en vivo y avisa de cada evento), `produccion/en_juego.py`
(modelo en juego), el parámetro `en_juego` de `produccion/simulador.py`, el campo `vivo` de `salidas/actual.json`
y las pruebas `produccion/pruebas/test_vivo.py` (22, sin red). Contrato del documento: `salidas/CONTRATO.md`
(«Documento en vivo»); ejemplo: `salidas/vivo_ejemplo.json`.

## 1. Cómo funciona

```
ESPN scoreboard (un día por consulta)
   └─ vivo.py: partidos de HOY ──► pronóstico al momento (en_juego.py)
                                 ├► tabla al momento (desempates oficiales del simulador)
                                 ├► proyección de clasificación y campeón (simulador con en_juego)
                                 └► liguilla: global y P(avanza) de cada serie
        ──► salidas/vivo.json  (escritura atómica, < 40 KB)
        ──► salidas/vivo_eventos.jsonl  (una línea por evento, numerada)
la sesión:  vivo.py esperar ──► copia vivo.json a la base del Artifact ("vivo/actual") ──► la página lo recibe con onSnapshot
```

- **Fuente**: `https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=AAAAMMDD`, gzip,
  User-Agent de navegador. ESPN parte los días en hora del Este de EE. UU. (verificado: `dates=20261107` trae
  los partidos de las 23:00Z del 7 a las 03:10Z del 8), así que se piden el día y el siguiente y se filtra por la
  fecha de México. El «día de partido» cambia a las 04:00 de México, no a medianoche.
- **Nombres**: por id de equipo, con el mismo diccionario de `datos/espn_descarga.py` («Tigres UANL» → Tigres).
- **Estado**: `status.type.state` (`pre`/`in`/`post`) y el nombre del estado (`…HALFTIME…` = descanso). El minuto
  sale de `displayClock` (`57'`, `45'+2'`); en las respuestas guardadas `clock` se queda en 5400 s durante el
  agregado del segundo tiempo, por eso el agregado se lee del texto y no de los segundos.
- **Jugadas**: `competitions[0].details` (goles, penales, autogoles, rojas). En el scoreboard el autogol viene
  con el equipo al que le cuenta; si no cuadra con el marcador se voltea. Si ESPN mueve el marcador antes de
  publicar la jugada, el evento sale sin nombre («Gol de Pumas. Pumas 1-0 América»).
- **Pronóstico previo**: el último sello de `salidas/sellos.jsonl` anterior al silbatazo; si no hay, el de
  `actual.json` (o el del modelo, marcado con `origen`).
- **Nada se inventa**: sin pronóstico previo no hay pronóstico al momento; si la simulación falla, el documento
  sale con la proyección previa y un texto en `avisos`.
- vivo.py no necesita nada fuera de la biblioteca estándar y de los módulos del proyecto (numpy/pandas sólo se
  cargan cuando hay algo en juego: un día sin partidos tarda 0.5 s).

## 2. Modelo en juego (`produccion/en_juego.py`)

    marcador final = marcador actual + goles restantes
    goles restantes de cada equipo ~ Poisson( lambda previa × fracción restante × ajustes )

**Fracción restante.** Curva empírica de goles por minuto (`datos/goles.csv`), en casillas: minutos 1-45,
agregado 45+1…45+12, minutos 46-90 y agregado 90+1…90+16. El peso del agregado ha crecido mucho (segundo
tiempo: 0.5% de los goles en 2001-09, 2.8% en 2010-15, 5.9% en 2016-19, ~7.6% desde 2023; primer tiempo: de
0.3% a 5.3%; parte es que ESPN antes no marcaba el agregado), así que la curva se estima sólo con los **8
torneos anteriores al corte** (hoy: 1,331 partidos y 3,789 goles de 2023 a 2026). Reparto actual: primer tiempo
40.1%, agregado del primero 5.3%, segundo tiempo 47.0%, agregado del segundo 7.6%.

| minuto completo | 0 | 15 | 30 | 45 | descanso | 60 | 75 | 90 | 90+4 | 90+8 |
|---|---|---|---|---|---|---|---|---|---|---|
| fracción restante | 1.000 | 0.877 | 0.746 | 0.599 | 0.546 | 0.390 | 0.233 | 0.076 | 0.035 | 0.009 |

En vivo el reloj dice «se está jugando el minuto m»: se usa el punto medio de esa casilla. Mientras ESPN diga
que se juega en tiempo agregado se supone que falta al menos minuto y medio de juego (piso; ver límites).

**Ajustes.** Regresión de Poisson sobre los tramos de cada partido (exposición = lambda previa fuera de muestra
de `modelo/pred/ensamble.parquet` × parte de la curva del tramo), con 2,981 partidos de DESARROLLO (7,941 goles).
Un ajuste sólo entra si su coeficiente pasa de 2 errores estándar; lo demás vale 1.

| estado del equipo | goles / esperados | multiplicador | z | ¿entra? |
|---|---|---|---|---|
| va perdiendo | 2,113 / 1,944 | **1.12** | +5.1 | sí |
| va ganando por 1 | 1,443 / 1,546 | **0.91** | −3.4 | sí |
| va ganando por 2 o más | 715 / 718 | 0.96 | −1.0 | no (queda en 1) |
| juega con uno menos | 201 / 383 | **0.50** | −9.6 | sí |
| juega con uno más | 614 / 407 | **1.52** | +10.2 | sí |
| nivel general (`base`) | 7,941 / 7,943 | 0.97 | −1.7 | no (queda en 1) |

El error estándar remuestreando torneos completos es prácticamente el mismo (0.021, 0.028, 0.069 y 0.049 en
log), así que los cuatro pasan con las dos cuentas. El efecto de la roja es más grande que el que suele citarse
(−30% / +30%): incluye el penal que a menudo acompaña a la expulsión, que también es «lo que viene».

**Dixon-Coles.** La matriz de lo que falta lleva la misma `rho` del pronóstico sellado: al minuto 0 el
pronóstico al momento es idéntico al previo y la corrección se desvanece con el reloj.

**Liguilla.** `en_juego.prob_avanza` llama a `simulador.prob_serie` con la matriz de cada pierna tal como esté
(marcador fijo si ya se jugó, matriz condicional si está en juego, matriz previa si no ha empezado): global
empatado = mejor sembrado en cuartos y semifinales; en la final, tiempos extra (1/3 de los goles de 90 minutos)
y penales a 50/50. Ya en tiempos extra: marcador del tiempo extra + Poisson de lo que queda de los 30 minutos
(reparto lineal: sólo hay 12 goles de tiempo extra en la base, no alcanza para una curva).

## 3. Validación sin fuga (`python3 -m produccion.en_juego validar`)

Walk-forward por torneo en DESARROLLO (Apertura 2016 a Clausura 2025, 2,981 partidos): para cada torneo, la
curva, los ajustes (con su regla de 2 errores estándar) y la tabla de «se queda como va» se estiman sólo con
partidos anteriores a su primer partido; las lambdas previas son las fuera de muestra del ensamble. Log-loss de
P(resultado final a 90 minutos), menor es mejor; entre paréntesis el error estándar (bootstrap por bloques).

| minuto | modelo | previo (a) | «se queda como va» (b) | sólo curva | modelo − (a) | modelo − (b) | modelo − sólo curva | acierto modelo / previo / «como va» |
|---|---|---|---|---|---|---|---|---|
| 15 | 0.9822 | 1.0254 | 1.0253 | 0.9851 | −0.043 (0.005) | −0.043 (0.005) | −0.0028 (0.0015) | 51.3% / 48.0% / 38.8% |
| 30 | 0.9194 | 1.0254 | 0.9654 | 0.9224 | −0.106 (0.007) | −0.046 (0.005) | −0.0031 (0.0022) | 55.5% / 48.0% / 48.8% |
| 45 (descanso) | 0.8229 | 1.0254 | 0.8799 | 0.8317 | −0.203 (0.010) | −0.057 (0.005) | −0.0088 (0.0026) | 61.4% / 48.0% / 58.5% |
| 60 | 0.7163 | 1.0254 | 0.7752 | 0.7233 | −0.309 (0.012) | −0.059 (0.005) | −0.0070 (0.0024) | 68.3% / 48.0% / 67.4% |
| 75 | 0.5647 | 1.0254 | 0.6114 | 0.5700 | −0.461 (0.013) | −0.047 (0.005) | −0.0053 (0.0022) | 78.1% / 48.0% / 78.1% |

- (a) es el pronóstico previo sin mirar el marcador. (b) no puede ser «el resultado de ahora con probabilidad 1»
  (log-loss infinito): es la frecuencia histórica del resultado final dado el resultado parcial en ese minuto,
  estimada con la ventana previa y sin mirar a los equipos; su «acierto» es el de apostar a que no cambia nada.
- **Lo que sí**: el modelo le gana a las dos referencias en todos los minutos por 9 errores estándar o más, y
  está bien calibrado (error de calibración por deciles de 0.4 a 1.3 puntos; pendiente de 1.00 a 1.09: algo
  tímido al principio, igual que el pronóstico previo). Los goles que faltaban: 2.30 esperados contra 2.34
  observados al 15', 1.94 contra 1.97 al 30', 1.47 contra 1.47 al descanso, 1.05 contra 1.05 al 60' y 0.63
  contra 0.63 al 75'.
- **Lo que casi no**: de los ajustes, el que aporta es el de las expulsiones. Con todo junto el modelo mejora
  −0.0054 (ee 0.0017) al que sólo usa la curva; con sólo el efecto del marcador la mejora es de −0.0001: es
  real en los goles (z = 5) pero no mueve el 1X2. En los partidos con hombres disparejos el ajuste de rojas
  vale −0.10 de log-loss al descanso (256 partidos, ee 0.025) y −0.03 al 75' (488, ee 0.013).
- **En acierto** al 75' el modelo elige lo mismo que «se queda como va» (78.1%): la ganancia está en la
  probabilidad que le pone, no en el pick.
- Con `rho = −0.05` en lugar de 0 el log-loss mejora 0.0004 (ee 0.0002): no es concluyente; se usa la `rho` del
  sello por coherencia con el previo.
- Los ajustes se aplicaron en la validación tal como habrían estado disponibles: ninguno en el Apertura 2016,
  y un nivel general `base` < 1 (de 0.89 a 0.96) entró en 6 de los 18 torneos (Apertura 2017 a Clausura 2019,
  Clausura 2022 y Clausura 2025); con todos los datos `base` ya no pasa el umbral (z = −1.7) y queda en 1.
- **No está validado**: lo que pasa después del 75' y en el tiempo agregado (el piso de minuto y medio es un
  supuesto), los tiempos extra, ni la proyección de campeón al momento (no hay historia para hacerlo).

## 4. Proyección al momento (simulador)

`simulador.simular(..., en_juego={id: {"gl", "gv", "lam_rest_l", "lam_rest_v"[, "lam_l", "lam_v", "extra", "avanza"]}})`
simula esos partidos como marcador actual + Poisson(lo que falta). Detalles que importan:

- Los partidos en juego se sortean con un generador aparte y **acoplados** al sorteo normal
  (`acoplar_en_juego`, acoplamiento máximo): con la misma semilla todo lo demás sale igual que sin `en_juego`,
  y al minuto 0 no cambia ni un marcador (probado). Así la diferencia entre las dos corridas es sólo lo que ha
  pasado en la cancha. Esto vale porque el modelo de producción usa `rho ≠ 0` (un sorteo uniforme por partido);
  con un modelo de `rho = 0` las corridas dejan de estar sincronizadas y el `delta` trae más ruido.
- vivo.py publica `p = último pronóstico previo (actual.json) + (simulación con en_juego − simulación base)`,
  las dos con 6,000 simulaciones, 600 muestras de parámetros y la misma semilla. Sin nada en juego `p` es
  exactamente el de `actual.json` y `delta` = 0.
- Ruido: un `delta` de campeón de menos de ~1 punto en un equipo que no juega puede ser ruido (`proyeccion.ruido`).
- Costo: armar la base (pronosticador + simulación) tarda ~10 s la primera vez del día y se guarda en
  `modelo/cache/vivo_base.pkl`; cada ciclo posterior tarda ~0.3 s.
- Un partido que ya acabó pero todavía no está en `partidos.csv` entra con `lam_rest = 0` (marcador fijo).

## 5. Comandos

| comando | qué hace |
|---|---|
| `python3 vivo.py una-vez` | una consulta; escribe `salidas/vivo.json` e imprime un resumen. Código 1 si ESPN no responde (no pisa el archivo) |
| `python3 vivo.py observar [--hasta AAAA-MM-DDTHH:MM]` | bucle: cada 20 s con partido en juego o a menos de 15 min de uno; cada 120 s si no. Anota los eventos. Termina solo 10 minutos después del último final, si hoy no hay partidos, al cambiar el día (04:00) o al llegar `--hasta` (hora de México; con `Z`, UTC). Código 2 si ya hay otro corriendo |
| `python3 vivo.py esperar --desde N [--max-seg 6600]` | imprime en UNA línea el primer evento con número > N (más `pendientes` y `ultimo_n`) y sale con 0; 3 si `observar` ya no corre y no hay más; 4 si se agotó el tiempo |
| `python3 vivo.py repetir <id> [--velocidad 60] [--salida salidas/vivo_prueba.json]` | reproduce un partido ya jugado (goles y rojas de los CSV) con el contexto de ese día; documentos con `"prueba": true` |
| `python3 vivo.py plan [--horas 48]` · `python3 pipeline.py vivo-plan` | próximos inicios en UTC y hora de México |
| `python3 vivo.py estado` | ¿corre `observar`?, último latido, último evento (`ultimo_n`) |
| `python3 -m produccion.en_juego ajustar` / `validar` / `curva` | parámetros, validación y curva del modelo en juego |

Eventos (`tipo`): `inicio`, `gol`, `gol_anulado` (el marcador bajó o se corrigió), `roja`, `descanso`,
`segundo_tiempo`, `tiempos_extra`, `penales`, `final`, `pospuesto` y `refresco` (cada 15 minutos si hay partido
en juego y nada que avisar). Si ESPN no responde un rato, al volver salen de golpe y en orden todos los que se
perdieron. Un partido que ya iba empezado cuando arrancó `observar` no «anuncia» lo que pasó antes: sale un
`refresco` con el estado.

`pipeline.py auto` corre `vivo.py una-vez` después de los pronósticos y **antes** de construir la página (para
que ésta lleve el estado del día en `actual.json` → `vivo`); si ESPN no responde queda un aviso en
`ultimo_auto.json` (`vivo.aviso`) y la corrida no cuenta como fallida.

## 6. Procedimiento de un día de partido

Todo desde `/home/user/SA/ligamx`.

1. **Antes** (la tarea diaria de la 01:20 ya lo deja hecho): `python3 pipeline.py auto` sella los pronósticos y
   deja `actual.json` y `vivo.json` al día. `python3 pipeline.py vivo-plan --horas 48` dice a qué hora empieza
   cada partido y desde cuándo conviene observar (`observar_desde_utc`, 15 minutos antes).
2. **Unos 20 minutos antes del primer partido**, lanzar el observador desligado de la terminal:

       setsid nohup python3 vivo.py observar > salidas/vivo_observar.log 2>&1 &
       python3 vivo.py estado          # observar_activo: true; anotar ultimo_n

   y copiar una primera vez `salidas/vivo.json` a la base del Artifact (colección `vivo`, documento `actual`;
   con ArtifactData: acción `set` y `file_path=salidas/vivo.json`) para que la página muestre «previo».
3. **Bucle de la sesión** (N = `ultimo_n` del paso 2):

       python3 vivo.py esperar --desde N     # en segundo plano; despierta sola (hasta 110 minutos)

   - código **0**: pasó algo. Copiar `salidas/vivo.json` a `vivo/actual` (el archivo ya trae TODO lo ocurrido,
     no hace falta atender los `pendientes` uno por uno), tomar N = `ultimo_n` de la línea impresa y volver a esperar.
   - código **4**: no pasó nada en 110 minutos; volver a esperar con el mismo N.
   - código **3**: `observar` ya no corre. `python3 vivo.py estado`: si `vivo.estado` es `terminado_hoy` (o
     `sin_partidos`) ir al paso 4; si no (lo mató el entorno o se cayó), relanzarlo como en el paso 2 —retoma
     desde el `vivo.json` que dejó, sin repetir ni perder avisos— y seguir esperando con el mismo N.
4. **Cierre**: `python3 pipeline.py auto` (baja los resultados, califica los sellos, rehace tabla, liguilla y
   campeón, y vuelve a correr `una-vez`); copiar el `vivo.json` final a `vivo/actual`; si
   `salidas/ultimo_auto.json` dice `publicar: true`, republicar la página y `python3 pipeline.py publicado`;
   commit y push.

En liguilla, además: `pipeline.py auto` debe haber corrido DESPUÉS de la ida (lo hace la tarea diaria) para que
`liguilla.torneo` traiga la serie real con la ida ya jugada; el P(avanza) al momento parte de ahí.

**Probar sin partido real**: `python3 vivo.py repetir 401876913 --velocidad 60` (América 2-2 Toluca del
31-oct-2026: dos goles por lado, dos rojas y un penal al 90'+2'; dura 2 minutos) y en otra terminal
`python3 vivo.py esperar --desde 0 --eventos salidas/vivo_prueba_eventos.jsonl --candado salidas/vivo_prueba.lock`.
Si se copia `salidas/vivo_prueba.json` a `vivo/actual` para ver la página moverse, al terminar hay que volver a
poner el real (`python3 vivo.py una-vez` y copiar `salidas/vivo.json`).

**Si algo falla**: ESPN sin respuesta → `observar` reintenta solo (20, 40… hasta 120 s) y lo dice en
`salidas/vivo_observar.log`; candado tomado (código 2) → ya hay un observador (`vivo.py estado`); documento sin
`vivo` en un partido en juego → falta el pronóstico previo (ver `avisos`); proyección sin cambios con `nota` →
falló la simulación (el resto del documento es válido).

## 7. Límites honestos

- El estado se congela: el multiplicador de ahora se aplica a todo lo que falta. Si el que pierde empata, su
  ritmo real vuelve al de empate; el error es de segundo orden y la validación no lo distingue.
- No se modelan cambios, lesiones durante el partido, penales por cobrar ni VAR en curso; ESPN puede corregir
  un gol o una roja minutos después (sale como `gol_anulado` y el documento se recalcula).
- El agregado: la curva sabe cuántos goles caen después del 90'+a en promedio, no cuánto agregó el árbitro hoy.
- ESPN va entre 30 y 60 segundos detrás de la cancha y el observador pregunta cada 20 s: el aviso de un gol
  puede tardar hasta ~1.5 minutos. No se pudo probar contra un partido real en juego (el 10-nov-2026 no hubo):
  el manejo de los estados en vivo de ESPN está probado con partidos reales rebobinados; el primer partido
  real (Querétaro-Monterrey, 14-nov) es la prueba de fuego, sobre todo de cómo marca ESPN el descanso.
- La tabla al momento suma las tarjetas de hoy al Fair Play de forma aproximada (amarilla 1, cualquier roja 3).
- En tiempos extra y penales el modelo es deliberadamente simple (reparto lineal y 50/50).
