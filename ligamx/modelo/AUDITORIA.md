# Auditoría adversarial · Cerebro Liga MX

Auditoría independiente hecha el 2026-11-10, después de la selección del campeón. El objetivo fue encontrar
razones por las que los resultados de `RESULTADOS.md` NO sean confiables o por las que la producción pueda fallar.
Se partió de desconfiar de todo: nada se dio por bueno sin recalcularlo con código propio.

Scripts (se corren desde `ligamx/`; cada uno deja su salida en `modelo/pruebas/auditoria_resultados/`):

| Script | Qué hace | Tiempo |
|---|---|---|
| `python3 -m modelo.pruebas.auditoria_fugas` | cortes y zona horaria, reajuste del campeón desde cero, tablas de variables, cálculo independiente de tiros y rotación | 3 min |
| `python3 -m modelo.pruebas.auditoria_replica` | recalcula todas las cifras desde los CSV y los parquet, sin importar nada del proyecto | 10 s |
| `python3 -m modelo.pruebas.auditoria_seleccion` | cuánto de la ventaja de `ajuste` es sesgo de selección (sólo DESARROLLO) | 1 min |
| `python3 -m modelo.pruebas.auditoria_produccion` | JSON de la página, combinadas, simulador propio, desempates, robustez | 3 min |

## 0. Veredicto en lenguaje llano

**No encontré trampas ni errores de cálculo.** No hay información del futuro en ningún pronóstico, todas las cifras
publicadas salen iguales al recalcularlas por otro camino y la PRUEBA se abrió una sola vez. Lo que sí encontré es
que **la ventaja del modelo llamado campeón es más chica de lo que parece** y que las probabilidades de campeón
tienen mucha más incertidumbre que la que muestra la página.

**(a) Comparación entre modelos: creíble en los números, débil en la conclusión.** Los números están bien. La
conclusión "`ajuste` es el mejor" no se sostiene: su ventaja en DESARROLLO (0.0072) está inflada porque sus
variables se escogieron mirando ese mismo periodo; repitiendo la elección con honestidad la ventaja baja a unos
0.003, y la PRUEBA no la confirmó (+0.0008 ± 0.0045). Lo que sí es sólido: saber qué equipos juegan vale mucho
(0.039 sobre no saber nada) y todo lo demás vale poco. Entre `ajuste`, `ensamble`, `dc` y `elo` no hay un ganador
demostrado; para el usuario dan casi el mismo pronóstico por partido (menos de un punto porcentual de diferencia).

**(b) Distancia al mercado: creíble.** El mercado de cierre le gana a cualquier modelo propio por 0.01 a 0.02 de
log-loss, en los mismos partidos, con el margen bien quitado y el error bien calculado. No encontré señales de
que los momios de la PRUEBA estén capturados con el partido en juego (que es lo único que haría ver al mercado
mejor de lo que es). Reserva: es una sola fuente (ESPN) y con 476 partidos la brecha se conoce con un error de
0.008; lo seguro es "el mercado es mejor", no el tamaño exacto.

**(c) Probabilidades de campeón: bien calculadas, poco precisas.** El cálculo es correcto (un simulador escrito
aparte da lo mismo, con diferencia máxima de 0.002) y respeta el reglamento. Pero el número depende mucho de qué
modelo se use, y la validación no distingue entre ellos: Cruz Azul sale con 21% con `ajuste`, 26% con `ensamble`,
24% con `dc` y 33% con `elo`; Chivas, entre 16% y 22%. El "error" que acompaña a cada probabilidad en la página
(±0.004) sólo mide el ruido de la simulación. Léanse como "América, Chivas, Cruz Azul y Toluca tienen cada uno
más o menos entre una de cada cinco y una de cada tres; los demás, muy poco", no como un orden entre los cuatro.
Además el cálculo de series tiende a quedarse corto con el mejor sembrado (60.8% pronosticado contra 67.2%
observado en 119 series) y nunca se ha podido validar contra campeones reales (hay 17 en el periodo de desarrollo).

**Recomendación (§4):** dejar de presentar a `ajuste` como "campeón" en el sentido de "el mejor demostrado" y usar
**`ensamble`** como modelo de producción, con `dc` como referencia simple. La decisión es del responsable del
proyecto: yo no cambié `campeon.json`.

## 1. Fugas de información (`auditoria_fugas.py`)

| Sospecha | Cómo se probó | Resultado |
|---|---|---|
| Orden temporal roto por zona horaria (nocturnos que caen en el día UTC siguiente) | Día local, corte de bloque y corte de día recalculados con `zoneinfo`, sin pandas, para los 8,684 partidos jugados | **Descartada.** 0 diferencias. 5,104 partidos caen en el día UTC siguiente al local y el proyecto usa siempre el local |
| Partidos del mismo bloque (o día) usados entre sí | Historial truncado físicamente en el corte (ver abajo); además conteo de partidos que empiezan antes de un corte y terminan después | **Descartada**, con un matiz: 3 partidos nocturnos (1 de DESARROLLO, 2 de PRUEBA) empiezan antes de la medianoche y acaban después, así que están en el historial de un corte que cae a media segunda parte. Ningún partido empieza a menos de 9.5 h de su corte: no cambia nada |
| Variables calculadas con el propio partido o con posteriores | (1) Cálculo independiente desde los CSV, sin `variables.py`, de tiros de los últimos 10 y cambios entre los dos últimos onces, para los 3,463 partidos desde 2016. (2) Reconstrucción con historial truncado | **Descartada.** 0 celdas distintas en (1); (2) abajo |
| Escalados o medias globales | Las medias y desviaciones de la corrección se recalcularon sólo con partidos anteriores al primer corte de cada torneo | **Descartada.** El factor de corrección recalculado así es el guardado (a 2e-8) |
| Coeficientes de la corrección ajustados con datos posteriores al corte | 19 ajustes de coeficientes desde cero, cada uno con CSV truncados en el primer corte de su torneo; la regresión se repitió con otro optimizador (L-BFGS de scipy) | **Descartada.** Diferencia máxima entre optimizadores 9e-9 |
| Cachés de variables o de predicciones contaminadas | Reajuste del campeón DESDE CERO para 40 partidos al azar de PRUEBA y 40 de DESARROLLO: CSV truncados físicamente en el corte del partido (ninguna fila posterior existe; la fila del partido va sin marcador, estadísticas, momios ni alineación), variables reconstruidas, Dixon-Coles propio (Newton denso escrito aparte, `rho` por `minimize_scalar`), matriz Poisson + Dixon-Coles propia | **Descartada.** Contra `pred/`: lambda base (`dc`) igual a 4e-16; factor de corrección a 2e-8; lambda final a 1.8e-8 (DESARROLLO) y 8e-9 (PRUEBA); 1X2 a 5e-9 |
| Caché de variables desactualizada respecto de los CSV | Reconstrucción completa contra las dos cachés (5,644 filas) | **Descartada.** 0 celdas distintas en las 6 columnas del campeón |
| Tabla por "partido" usada donde tocaba otra | En la PRUEBA (corte por día) `ajuste` leyó la tabla "partido". Se comparó contra la construida con corte "dia" y con corte "bloque" | **Descartada.** "partido" = "dia" en los 480 partidos de PRUEBA y los 2,983 de DESARROLLO; "partido" = "bloque" en toda la PRUEBA y distinta sólo en 3 partidos de DESARROLLO (equipo que juega dos veces en un bloque), donde se usó la de bloque, que es la correcta |
| Hiperparámetros elegidos mirando la PRUEBA | Fechas de archivos y bitácora (§3) | **Descartada.** `candidatos.py` no se tocó después de las 09:42:22; la PRUEBA se abrió a las 09:46:41 |
| Variables elegidas mirando el periodo en que se califican | Lectura de `VARIABLES.md` §5.1 y experimento de §4 | **Confirmada** (no es fuga del futuro, es sesgo de selección). Ya lo decía `RESULTADOS.md` §4; aquí se mide |

El arnés hace lo que dice: `hist` son los partidos con inicio anterior al corte y `predecir` no ve el resultado.

## 2. Réplica independiente (`auditoria_replica.py`)

El script no importa nada del proyecto: lee `datos/partidos.csv` y los parquet, y calcula log-loss, RPS y Brier
con fórmulas propias, el mercado desde los momios crudos con un método de Shin propio y los errores con un
bootstrap propio (otra semilla, 4,000 réplicas).

| Periodo | Modelo | n | Log-loss recalculado | Reportado | RPS | Brier |
|---|---|---|---|---|---|---|
| DESARROLLO | `ajuste` | 2,981 | 1.0225 | 1.0225 | 0.2093 | 0.6134 |
| DESARROLLO | `dc` | 2,981 | 1.0297 | 1.0297 | 0.2117 | 0.6183 |
| DESARROLLO | `poisson_simple` | 2,981 | 1.0309 | 1.0309 | 0.2119 | 0.6189 |
| DESARROLLO | mercado de cierre | 1,671 | 1.0028 | 1.0028 | 0.2041 | 0.5995 |
| PRUEBA | `elo` | 480 | 1.0221 | 1.0221 | 0.2116 | 0.6122 |
| PRUEBA | `ensamble` | 480 | 1.0225 | 1.0225 | 0.2115 | 0.6125 |
| PRUEBA | `dc` | 480 | 1.0264 | 1.0264 | 0.2129 | 0.6149 |
| PRUEBA | `ajuste` | 480 | 1.0272 | 1.0272 | 0.2126 | 0.6156 |
| PRUEBA | `poisson_simple` | 480 | 1.0276 | 1.0276 | 0.2132 | 0.6159 |
| PRUEBA | original limpio | 480 | 1.0325 | 1.0325 | 0.2130 | 0.6182 |
| PRUEBA | mercado de cierre | 476 | 1.0030 | 1.0030 | 0.2055 | 0.5994 |

- **Integridad de los 19 archivos revisados**: los ids son exactamente los partidos evaluables de cada periodo
  (2,981 y 480), sin duplicados; el resultado guardado es el del CSV; las probabilidades suman 1; el corte guardado
  es anterior al inicio y es el recalculado. Ningún archivo falla.
- **Mercado**: las probabilidades de Shin recalculadas coinciden con las guardadas a 2e-16. En DESARROLLO hay 1,677
  partidos con momios y 6 marcados como capturados en juego (los mismos seis ids), quedan 1,671; sin ese filtro el
  mercado saldría en 0.9998 en vez de 1.0028. En la PRUEBA hay 476 con momios (a 4 les faltan) y el filtro no
  marca ninguno. Proveedores en la PRUEBA: DraftKings 313, ESPN BET 163.
- **Mismos partidos**: cada comparación contra el mercado usa la intersección exacta (1,671 y 476 partidos).
- **Errores estándar** (modelo − referencia en log-loss):

| Comparación | Diferencia | ee reportado | ee recalculado (bloques) | por partido | por semana | por mes | analítico |
|---|---|---|---|---|---|---|---|
| DESARROLLO `ajuste` − mercado | +0.0095 | 0.0043 | 0.0043 | 0.0041 | 0.0042 | 0.0039 | 0.0043 |
| DESARROLLO `ajuste` − `dc` | −0.0072 | 0.0013 | 0.0013 | 0.0014 | 0.0013 | 0.0013 | 0.0014 |
| DESARROLLO `poisson_simple` − mercado | +0.0185 | 0.0046 | 0.0046 | 0.0045 | 0.0045 | 0.0042 | 0.0046 |
| PRUEBA `ajuste` − mercado | +0.0237 | 0.0080 | 0.0082 | 0.0080 | 0.0082 | 0.0083 | 0.0081 |
| PRUEBA `ajuste` − `dc` | +0.0008 | 0.0045 | 0.0045 | 0.0048 | 0.0043 | 0.0048 | 0.0045 |
| PRUEBA `ensamble` − `ajuste` | −0.0047 | 0.0028 | 0.0027 | 0.0030 | 0.0025 | 0.0032 | 0.0027 |
| PRUEBA `elo` − mercado | +0.0185 | 0.0075 | 0.0075 | 0.0082 | 0.0072 | 0.0073 | 0.0075 |
| Todo (3,461) `ajuste` − `dc` | −0.0061 | 0.0013 | 0.0013 | | | | |

  Los errores son correctos y no dependen de la unidad de remuestreo. Lo que el error NO incluye es el sesgo de
  selección (§4): la "z = 5.4" de `ajuste` contra `dc` en DESARROLLO no es una prueba limpia.
- **¿Cierres capturados en juego en la PRUEBA?** En los 313 partidos con apertura y cierre, la probabilidad de
  lo que acabó pasando subió en promedio 0.008 (ee 0.003) entre apertura y cierre, que es lo normal en un mercado
  que incorpora noticias. Hay 24 movimientos mayores a 10 puntos; 16 fueron hacia el resultado y 8 en contra
  (por ejemplo Toluca-León 4-1: el local pasó de 1.32 a 1.87 y ganó). No es el patrón de una captura en juego. La
  apertura trae más margen (7.9% contra 5.9%) y se mueve mucho (mediana 3.8 puntos): es una línea temprana.

## 3. Contaminación de la PRUEBA

- **Cuántas veces se evaluó**: 13 llamadas a `evaluar`, una por modelo (6 candidatos y 7 referencias), todas del
  agente de selección, entre las 09:46:41 y las 09:48:26 UTC, desde un solo guion (`prueba_run.py`, escrito a las
  09:46:40). Coincide con el registro de variantes: 13 líneas de PRUEBA, ningún modelo repetido.
- **Antes de eso**: un incidente declarado (04:21 UTC): el agente del arnés imprimió el log-loss del MERCADO por
  torneo, incluidos los tres de la PRUEBA, antes de que existiera el candado. No es un modelo y no pudo guiar la
  elección de variables.
- **Después**: sólo lecturas de archivos ya escritos (el agente de selección para sus tablas, `exportar.py`, una
  prueba del simulador y esta auditoría, que se anotó como `quien=auditoria`). Las corridas posteriores del
  registro son de DESARROLLO: `dc` y `ajuste` por día (declaradas en `RESULTADOS.md` §3.4), `cerebro_original_limpio`
  (venía corriendo desde antes; terminó en 1.0370) y una variante de esta auditoría (`ajuste_auditoria_reglaB`,
  parcial, familia `auditoria`). El registro tiene hoy 78 líneas.
- **El pre-registro**: la regla de `RESULTADOS.md` §1 se aplicó tal como está escrita. Recalculé la condición:
  ningún candidato supera a `ajuste` en la PRUEBA por más de 2 errores pareados (`ensamble` −0.0047, z = −1.7; `elo`
  −0.0051, z = −0.9; `dc2` −0.0027, z = −0.6; `dc` −0.0008, z = −0.2; `tiros` −0.0006, z = −0.1). Lo que no pude
  verificar de forma independiente es la HORA del pre-registro (dice 09:46:20): el archivo se siguió editando y no
  hay un commit entre las 09:17 y las 10:13. La evidencia indirecta es coherente (código de candidatos sin cambios
  desde las 09:42:22 y con `ajuste` ya marcado ahí como "el mejor en resultado (1X2)", guion de la PRUEBA escrito a las 09:46:40).
- **Defecto de diseño de la regla** (no de su aplicación): el campeón provisional era el mejor de DESARROLLO y la
  PRUEBA sólo podía destronarlo por más de 2 errores pareados. Con 480 partidos eso exige una diferencia de 0.006 a
  0.012, mayor que cualquier diferencia real entre estos modelos. La PRUEBA casi no podía cambiar la decisión:
  "ningún candidato lo destronó" pesa poco como evidencia a favor de `ajuste`.
- **`produccion/exportar.py` lee predicciones de PRUEBA**: sólo para mostrar qué había pronosticado el modelo en
  la última jornada (`_pred_guardada`), y las rotula "modelo/pred (walk-forward, no sellado)". No ajusta ni elige
  nada con ellas: no contamina. La calibración de series y la validación de mercados usan sólo DESARROLLO. Dos
  observaciones: (1) esas lecturas quedan en la bitácora como `quien=desconocido`; (2) la regla de mejora continua
  de `registro.json` reevalúa todo "sobre todo el periodo", PRUEBA incluida: desde hoy la PRUEBA es dato de
  selección y cualquier cifra futura sobre ella deja de ser fuera de muestra. La única validación limpia que queda
  son los pronósticos sellados (`salidas/sellos.jsonl`), que hoy tienen 0 partidos calificados.

## 4. Estadística y honestidad: ¿es correcto llamar campeón a `ajuste`?

### 4.1 Cuánto sesgo de selección cabe esperar (`auditoria_seleccion.py`, sólo DESARROLLO)

Las 51 variantes no son el problema principal: dentro de la familia `ajuste` las 9 variantes van de 1.0224 a 1.0246
(salvo la que quita los tiros, 1.0279) y se eligió la tercera. El problema es anterior: las seis variables de
`ajuste` son las que sobrevivieron, entre 285 variables disponibles, a un análisis hecho con TODO DESARROLLO, y la
ganancia se midió después en ese mismo periodo. Repetí la elección con honestidad dentro de DESARROLLO: elegir sólo
con la primera mitad (H1 = Apertura 2016 a Clausura 2021, 1,618 partidos) y medir en la segunda (H2 = Apertura 2021
a Clausura 2025, 1,363 partidos).

- **Con la regla original (q < 0.10) y sólo H1 no sobrevive ninguna variable.** La corrección honesta con la mitad
  de los datos habría sido no corregir.
- Con la regla alterna "las 6 de menor valor p en H1" salen: viaje del visitante, rotación del visitante en 5
  partidos, diferencia de goles del local en casa (dos versiones), cambios en el once del visitante y sede
  compartida. Sólo 2 de las 6 del campeón, y **ninguna de tiros**.
- La señal de los tiros viene casi toda de H2:

| Variable del campeón | z en H1 | z en H2 | z en todo DESARROLLO |
|---|---|---|---|
| `sede_viaje_km_v` | 3.10 | 2.41 | 3.90 |
| `once_previa_cambios_v` | 2.44 | 2.68 | 3.51 |
| `juego10_tiros_f_l` | 1.53 | 3.44 | 3.41 |
| `juego10_tiros_c_l` | −2.16 | −3.14 | −3.79 |
| `juego10_tiros_f_v` | −0.28 | −3.37 | −2.48 |
| `juego10_tiros_c_v` | 0.98 | 3.89 | 3.45 |

- **Ganancia medida contra `dc`**:

| Qué | Dónde | `x` − `dc` | ee |
|---|---|---|---|
| `ajuste` real (variables elegidas con H1 + H2) | H1 | −0.0031 | 0.0016 |
| `ajuste` real | H2 | −0.0121 | 0.0022 |
| Corrección con las 6 variables elegidas sólo con H1 | H2 (limpio) | **−0.0032** | 0.0013 |
| `ajuste` real | PRUEBA (limpio) | +0.0008 | 0.0045 |

  En H2 la corrección elegida con honestidad consigue una cuarta parte de lo que consigue el `ajuste` real
  (0.0089 peor, ee 0.0020). Por torneo, `ajuste` le gana a `dc` en 16 de 18 torneos de DESARROLLO y en 1 de 3 de
  la PRUEBA.
- **A favor de que algo hay**: los coeficientes de los tiros ya tenían el mismo signo y tamaño en julio de 2016,
  cuando se ajustaron sólo con partidos de 2011 a 2016, que la selección de variables nunca vio; y viaje y rotación
  aparecen en las dos mitades. La corrección no es puro ruido.
- **Estimación**: de los 0.0072 de ventaja en DESARROLLO, del orden de 0.004 es sesgo de selección; la ganancia
  honesta esperable de la corrección es de unos **0.003** (entre 0 y 0.005). Eso es compatible con la PRUEBA
  (queda a 0.9 errores de +0.0008), y es demasiado chico para verlo en 480 partidos (harían falta entre 2,000 y
  4,500 para verlo a 2 errores).

### 4.2 Recomendación

**No es correcto seguir llamándolo "campeón" si con eso se entiende "el mejor demostrado".** Es el modelo que la
regla escrita de antemano dejó en pie, y eso sí es cierto. Propongo llamarlo "modelo en uso" y decir que no tiene
ventaja demostrada sobre un Dixon-Coles simple.

**Para producción recomiendo `ensamble`** (media de las lambdas de `ajuste` y `elo`), por tres razones que no
dependen de mirar otra vez la PRUEBA:

1. **Es el único con un resultado estable en los dos periodos.** Contra `dc`: −0.0043 en DESARROLLO (ee 0.0009) y
   −0.0039 en la PRUEBA (ee 0.0032): mismo signo y mismo tamaño. `ajuste` contra `dc`: −0.0072 y +0.0008. En
   DESARROLLO `ajuste` le gana a `ensamble` por 0.0029 (ee 0.0010), pero `ensamble` sólo lleva media corrección, así
   que carga la mitad del sesgo de selección (unos 0.002): corregido, es un empate. En la PRUEBA gana `ensamble`
   por 0.0047 (ee 0.0027).
2. **Es el mejor en marcador exacto en los dos periodos**, que es de donde salen los marcadores, los mercados, las
   combinadas y el simulador: contra `ajuste` +0.0042 de log-verosimilitud en DESARROLLO (ee 0.0021) y +0.0163 en
   la PRUEBA (ee 0.0052); contra `dc` +0.0100 (ee 0.0019) y +0.0162 (ee 0.0044).
3. **Reparte el riesgo.** Si la corrección por tiros resulta valer menos de lo estimado, `ensamble` pierde la
   mitad; si falla la fuente de tiros o de alineaciones, depende la mitad. `ajuste` fue además el más
   sobreconfiado en la PRUEBA (pendiente de calibración 0.78).

Reservas, dichas de frente: es una decisión tomada después de ver la PRUEBA, así que sus cifras de PRUEBA ya no
cuentan como confirmación; la diferencia por partido es menor a un punto porcentual; su incertidumbre para el
simulador es prestada de `dc`; y es el modelo menos simple. Quien prefiera lo más simple y transparente puede usar
`dc` sin perder nada demostrable en resultado (queda unos 0.004 por detrás de `ensamble` en los dos periodos, y
0.010 a 0.016 en marcador exacto). Lo que no recomiendo es presentar a `ajuste` solo como el mejor.

Con cualquiera de los tres, lo honesto para **probabilidades de campeón** es decir el rango entre modelos (§5),
no sólo el error de simulación.

## 5. Producción (`auditoria_produccion.py`)

Corrida de `python3 -m produccion.exportar --sin-sello --salida <temporal>`: 16 s, 222 KB, 10 pendientes, sin
errores de validación.

| Revisión | Resultado |
|---|---|
| 1X2 suma 1; matriz 7×7 más resto suma 1; pares complementarios (más/menos, ambos anotan, gol en el primer tiempo, anota / portería en cero) | Desviación máxima 0.0001 y 0.0005 (redondeo a 4 decimales). Ningún par falla |
| NaN, infinitos, nulos en campos numéricos, probabilidades fuera de [0, 1] | 0 |
| 1X2, más de 2.5, ambos anotan y marcador más probable de 3 partidos, a mano con Poisson + Dixon-Coles | Diferencia máxima 0.00006; matriz de marcadores a 0.00005; mismo marcador más probable |
| Probabilidad conjunta de 3 combinadas por simulación (2 millones de partidos cada una; goles repartidos entre mitades con una binomial) | Querétaro-Monterrey "segura": 0.4817 exportada, 0.4814 simulada. Puebla-San Luis "equilibrada": 0.3066 y 0.3068. Tijuana-Atlante "atrevida": 0.2176 y 0.2176. Error de simulación 0.0003. Las tres coinciden (el producto ingenuo daría 0.36, 0.13 y 0.05) |
| Combinada de jornada | Un pick por partido distinto; la conjunta es el producto (0.4990 y 0.2105) |
| Tabla actual | 18 equipos, 0 celdas distintas contra `datos/tabla_apertura2026.csv` (que coincide con ESPN en los 18) y contra un recuento propio de `partidos.csv` |
| Proyección | Campeón suma 1.0001; finalistas 1.9999; semifinalistas 4.0002; clasificados 7.9999; campeón ≤ final ≤ semifinal ≤ clasifica en los 18; cada fila y cada columna de la distribución de posiciones suma 1 |
| Desempates de la tabla contra `config/torneo.json` | El orden es el del reglamento: puntos, diferencia, goles a favor, goles de visitante, menos Fair Play, cociente, sorteo (probado con pares que empatan en todo lo anterior) |
| Desempates de series | Cuartos y semifinales con global empatado: avanza el mejor sembrado, sin gol de visitante (probado con un 2-2 global en que el peor tiene más goles de visita). Final empatada: tiempos extra y penales a 50%; coincide con la fórmula a mano. Cruces 1-8, 2-7, 3-6, 4-5 y resiembra en semifinales |
| Simulador propio (escrito aparte, lambdas puntuales, 60,000 torneos) contra el del proyecto | Diferencia máxima en P(campeón) 0.0017 (1.2 errores de simulación). Añadir la incertidumbre de parámetros mueve las probabilidades hasta 0.009 |
| Equipo sin historial (local y visitante) | Lambdas finitas (vale el promedio; sin corrección) |
| Equipo sin estadísticas ni alineaciones en sus últimos 25 partidos | No se rompe: lambdas finitas; las variables que faltan valen "promedio" y no corrigen (Querétaro-Necaxa pasa de 1.47/1.23 a 1.40/1.22) |
| Caché de variables desactualizada | **Fallaba en silencio** (arreglado, §6) |
| Caché de variables ausente | Falla con `FileNotFoundError` (bien: no pronostica con datos inventados) |

**P(campeón) según el modelo** (20,000 torneos cada uno; el error de simulación es ±0.004):

| Equipo | `ajuste` | `ensamble` | `dc` | `elo` | Rango |
|---|---|---|---|---|---|
| América | 0.281 | 0.272 | 0.275 | 0.245 | 0.037 |
| Chivas | 0.223 | 0.199 | 0.181 | 0.160 | 0.062 |
| Cruz Azul | 0.211 | 0.257 | 0.236 | 0.327 | 0.116 |
| Toluca | 0.200 | 0.195 | 0.216 | 0.198 | 0.021 |
| Pachuca | 0.027 | 0.022 | 0.024 | 0.018 | 0.009 |
| Monterrey | 0.026 | 0.018 | 0.020 | 0.010 | 0.016 |

Cuatro modelos que la validación no distingue dan hasta 12 puntos de diferencia para un mismo equipo. Esa es la
incertidumbre real de la probabilidad de campeón, y la página hoy no la muestra.

## 6. Qué estaba mal y qué cambié

**Ninguna cifra reportada cambió**: todas se reprodujeron. Los cambios son de producción y de documentación.

| Archivo | Cambio | Por qué |
|---|---|---|
| `modelo/variables.py` | Función nueva `estado_cache(corte, hasta)`: compara las firmas de la caché con los CSV actuales sin reconstruir ni escribir | Hacía falta una forma barata (0.8 s) de saber si la caché sirve |
| `modelo/pronostico.py` | `Pronosticador` revisa la caché al crearse (`_revisar_cache_variables`): si le faltan partidos anteriores al corte de coeficientes, o esos partidos cambiaron, emite `RuntimeWarning` y deja el texto en `self.avisos` | **Error real.** Con una caché a la que le faltaban 99 partidos (parada en marzo de 2026) el modelo se ajustaba sin decir nada y las lambdas cambiaban hasta 0.019: un dato ausente cuenta como "promedio" |
| `produccion/exportar.py` | Los `avisos` del Pronosticador se copian al inicio de los avisos del JSON (prefijo "DATOS:") | Que el aviso llegue a la página |
| `modelo/pruebas/test_pronostico.py` | 3 pruebas nuevas: caché al día no avisa; caché incompleta avisa (y `dc`, que no la usa, no); `estado_cache` detecta un partido modificado | Dejar el arreglo cubierto |
| `modelo/ARNES.md` | Se llenaron tres marcadores de plantilla que habían quedado sin sustituir (`<<SEG_ORIGINAL>>`, `<<TABLA_RUIDO>>`, `<<PENDIENTES>>`) | El documento se había publicado con huecos |
| `modelo/pred/ACCESOS_PRUEBA.log` | Líneas `quien=auditoria` (lecturas de esta auditoría) y más lecturas de `exportar.py` | Constancia |
| `modelo/registro_variantes.jsonl` | Una línea: `ajuste_auditoria_reglaB` (DESARROLLO, parcial, familia `auditoria`) | El experimento de §4.1 es una variante más y debe contarse |

Pruebas después de los cambios: `pytest modelo/pruebas` 75 de 75 (72 que había más 3 nuevas) y
`pytest produccion/pruebas` 56 de 56.

No cambié `campeon.json`, `registro.json` ni `RESULTADOS.md`: la recomendación de §4.2 es una decisión, no una
corrección.

## 7. Riesgos que quedan

1. **El modelo en uso no tiene ventaja demostrada** y fue el más sobreconfiado en la PRUEBA. Ver §4.2.
2. **La PRUEBA ya no sirve para decidir nada.** La regla de mejora continua la usa junto con DESARROLLO. Lo único
   limpio hacia adelante son los pronósticos sellados, y hoy hay 0 partidos calificados: con una jornada de 9
   partidos el error del log-loss es de 0.06, así que harán falta varios torneos.
3. **Probabilidades de campeón sin validación directa** y sensibles al modelo (§5). El cálculo de series subestima
   al mejor sembrado en 6 puntos (ee 5) y no le gana de forma concluyente a la frecuencia histórica.
4. **Momios de una sola fuente.** No hay cotejo con otra casa; una captura en juego con momios verosímiles no se
   detectaría. Si existiera, la brecha con el mercado estaría exagerada, no disimulada.
5. **Hora del pre-registro no verificable de forma independiente.** Para la próxima vez: hacer commit del
   pre-registro antes de abrir la PRUEBA.
6. **La caché de variables no se actualiza sola.** Ahora el Pronosticador avisa, pero sigue pronosticando. Falta
   el paso automático: descargar datos, `variables.actualizar("bloque")` y `("partido")`, y después exportar; y
   decidir si un aviso de "DATOS" debe detener la publicación.
7. **Exportar a otra ruta todavía reescribe `salidas/desempeno.json`** (sólo cambia la hora de generación) y sus
   lecturas de la PRUEBA quedan como `quien=desconocido`. Menor; no lo toqué.
8. **Lo que no se revisó**: la página (`web/`), el contenido de `contexto.py` (rachas, dominios, textos), los
   mercados de córners y tarjetas, la descarga de ESPN, y las corridas retrospectivas con `--corte`. La liguilla en
   curso (series reales ya jugadas) sólo se revisó por sus reglas, no con un caso real, porque aún no empieza.
