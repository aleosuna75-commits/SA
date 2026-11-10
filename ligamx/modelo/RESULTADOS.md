# Resultados · Cerebro Liga MX

Documento para el usuario. Se escribe en dos tiempos: primero el PRE-REGISTRO (sección 1, antes de mirar la
PRUEBA) y después lo demás. La sección 1 no se edita una vez abierta la PRUEBA.

## 1. Pre-registro (escrito el 2026-11-10 a las 09:46:20 UTC, ANTES de abrir la PRUEBA)

*Única corrección posterior a esta sección: la hora del título decía "09:50" (estimada al escribir); se puso la real
del archivo. La primera evaluación de la PRUEBA quedó anotada a las 09:46:41 UTC en `pred/ACCESOS_PRUEBA.log`.*

**Estado de la PRUEBA al escribir esto.** `modelo/pred/ACCESOS_PRUEBA.log` tiene una sola línea, un incidente del
agente del arnés: antes de existir el candado se imprimió el log-loss del MERCADO por torneo (Apertura 2025 0.953,
Clausura 2026 1.004, Apertura 2026 1.060). Ningún modelo se ha evaluado en la PRUEBA y ninguna decisión de las de
abajo usó esas tres cifras.

**Periodo de PRUEBA.** Apertura 2025, Clausura 2026 y Apertura 2026 hasta lo jugado al 10-nov-2026 (unos 480
partidos). Se abre una sola vez, con `evaluar(..., periodo="prueba", granularidad="dia", permitir_prueba=True)`:
cada partido se pronostica con lo jugado antes de las 00:00 (hora de la Ciudad de México) de su día.

**Lista cerrada de candidatos** (los seis de `modelo.familias.candidatos.finalistas()`, hiperparámetros fijados en
DESARROLLO; no se cambia nada después de ver la PRUEBA):

| # | Nombre | Qué es | Hiperparámetros | Log-loss DESARROLLO (n = 2,981, por bloque) |
|---|---|---|---|---|
| 1 | `ajuste` | `dc` corregido con tiros de los últimos 10 (a favor y concedidos, ambos equipos), km de viaje del visitante y cambios en su once | ridge 1000; base `dc` | **1.0225** |
| 2 | `ensamble` | media de las lambdas de `ajuste` y `elo` | modo lambdas | 1.0254 |
| 3 | `dc2` | `dc` + ventaja de local por equipo | ridge_local 30 | 1.0291 |
| 4 | `dc` | Dixon-Coles penalizado (ataque, defensa, ventaja de local común, rho) | vida media 365 d, ridge 4 | 1.0297 |
| 5 | `elo` | Elo con margen de goles y conversión a goles | K = 8, regresión 0.15 | 1.0316 |
| 6 | `tiros` | `dc` con resultado 0.7·goles + 0.3·xg por tiros | w_goles 0.7 | 1.0319 |

Detalle técnico declarado de antemano: con corte por día, `ajuste` (y por tanto `ensamble`) lee la tabla de variables
con corte por partido (`Ajuste(tabla="partido")`, como indica el informe de candidatos). Sus seis variables dependen
sólo de partidos anteriores del propio equipo y de geografía, así que para ellas el corte por partido y el corte por
día dan lo mismo (un equipo no juega dos veces el mismo día).

**Referencias** (no compiten por ser campeón): `poisson_simple` (línea base), `cerebro_original_limpio` (el motor de
agosto de 2026 sin lo escrito conociendo el pasado), `cerebro_original_exacto` (el motor exacto, sólo desde el
14-ago-2026, que es donde es fuera de muestra), `mercado_cierre_shin` y `mercado_abre_shin` (momios de cierre y de
apertura sin margen) y `mercado_cierre_marcador` (para el marcador exacto). Se reporta también `frecuencias`.

**Métrica principal.** Log-loss del resultado 1X2 a 90 minutos. Secundarias (se reportan, no deciden): RPS, Brier,
log-verosimilitud del marcador exacto, acierto, marcadores exactos acertados y calibración.

**Regla de decisión.**

1. El campeón provisional es el candidato de menor log-loss 1X2 en DESARROLLO: **`ajuste`** (1.0225). En
   DESARROLLO no está en empate estadístico con ningún otro: le gana a `ensamble` por 0.0029 (ee 0.0010, 2.9 ee) y a
   `dc` por 0.0072 (ee 0.0013, 5.4 ee).
2. La PRUEBA sólo lo destrona si otro candidato de la lista tiene en la PRUEBA un log-loss menor que el de `ajuste`
   por **más de 2 errores estándar pareados** (bootstrap de bloques, 2,000 réplicas, semilla 20261110). Si son varios,
   gana el de menor log-loss en la PRUEBA.
3. Empate estadístico (diferencia pareada menor que 2 ee en DESARROLLO y en PRUEBA): se prefiere el más simple y
   rápido. Orden de simplicidad: `dc` < `elo` < `dc2` < `tiros` < `ajuste` < `ensamble`.
4. Si `ajuste` queda en la PRUEBA por detrás de `dc` o de `poisson_simple` sin llegar a 2 ee, se conserva por la regla
   2, pero se dice con todas las letras y `dc` queda como primer retador.
5. Ganarle o no al mercado no decide el campeón (el mercado no puede simular rondas futuras), pero se reporta la
   diferencia pareada con su intervalo de 95%, a favor o en contra.

**Qué se espera** (del informe de candidatos, escalando los ee de DESARROLLO a unos 480 partidos): `ajuste` − `dc`
con ee ≈ 0.003 (la ganancia de DESARROLLO, −0.0072, se vería a unas 2 ee); `ajuste` − mercado con ee ≈ 0.008 (la
brecha de DESARROLLO, +0.0095, no se distinguirá de cero). Es decir: la PRUEBA puede confirmar o desmentir que
`ajuste` mejora a `dc`, pero no tiene tamaño para decir si se le gana al mercado.

**Variantes probadas antes de este punto** (todas en `registro_variantes.jsonl`): 51 de candidatos (dc 12, dc2 7,
elo 14, tiros 3, ajuste 9, ensamble 6) más 10 corridas de líneas base y referencias.

---

## 2. Resumen para decidir

- **Campeón: `ajuste`**, por la regla pre-registrada. Es el mejor en DESARROLLO (log-loss 1.0225) y en la PRUEBA
  ningún candidato lo superó por más de 2 errores estándar (el más cercano, `ensamble`, por 0.0047 con ee 0.0028:
  1.7 ee).
- **La PRUEBA no confirmó su ventaja.** En los 480 partidos intocados `ajuste` (1.0272) quedó igual que `dc`
  (1.0264) y que `poisson_simple` (1.0276), y fue el sexto de seis candidatos. La mejora de 0.0072 que mostraba en
  DESARROLLO salió +0.0008 (ee 0.0045; IC 95% de −0.0079 a +0.0099): ni confirmada ni desmentida.
- **Los seis candidatos son indistinguibles en la PRUEBA**: van de 1.0221 (`elo`) a 1.0272 (`ajuste`), una franja de
  0.005 con errores pareados de 0.003 a 0.006.
- **No se le gana al mercado de cierre.** El mercado (1.0030) supera al campeón por 0.0237 de log-loss (ee 0.0080;
  IC 95% de +0.0084 a +0.0393) y al mejor candidato de la PRUEBA por 0.0185 (ee 0.0075). Frente a los momios de
  APERTURA de ESPN (313 partidos) hay empate: `ajuste` +0.0125 (ee 0.0086), `elo` −0.0003 (ee 0.0076).
- **Frente al modelo original**: en 1X2 no hay diferencia demostrable (`ajuste` − original limpio: −0.0054, ee
  0.0084); en marcador exacto el campeón es mucho mejor (+0.118 de log-verosimilitud por partido, ee 0.021), porque
  el original pronostica 2.2 goles por partido y se anotaron 2.9.
- **Qué significa en la práctica.** Lo sólido es el modelo de fuerzas (ataque, defensa, localía); todo lo demás
  aporta poco y con incertidumbre. La corrección por tiros, viaje y rotación se conserva porque la evidencia conjunta
  (3,461 partidos) todavía la favorece (−0.0061 frente a `dc`, ee 0.0013), pero entra a producción bajo vigilancia:
  en los últimos 8 bloques (64 partidos) todos los retadores le ganan (sección 5).

## 3. La PRUEBA (Apertura 2025, Clausura 2026 y Apertura 2026; corte por día)

Una sola pasada, el 2026-11-10: 6 candidatos y 7 referencias. 480 partidos evaluables, 170 días con partidos.
Errores estándar por bootstrap de bloques (2,000 réplicas). Azar uniforme: log-loss 1.0986.

### 3.1 Métricas

| Modelo | n | Log-loss | ee | RPS | Brier | logv marcador | Acierto | Marcadores exactos | Pendiente calib. | Error calib. |
|---|---|---|---|---|---|---|---|---|---|---|
| `mercado_cierre_shin` (ref.) | 476 | 1.0030 | 0.0191 | 0.2055 | 0.5994 | — | 0.506 | — | 0.95 | 0.017 |
| `mercado_cierre_marcador` (ref.) | 476 | 1.0030 | 0.0191 | 0.2055 | 0.5994 | -2.9655 | 0.506 | 60 | 0.95 | 0.017 |
| `elo` | 480 | 1.0221 | 0.0191 | 0.2116 | 0.6122 | -2.9884 | 0.508 | 59 | 0.91 | 0.025 |
| `ensamble` | 480 | 1.0225 | 0.0200 | 0.2115 | 0.6125 | -2.9894 | 0.500 | 54 | 0.85 | 0.031 |
| `dc2` | 480 | 1.0245 | 0.0178 | 0.2122 | 0.6138 | -3.0050 | 0.487 | 59 | 0.91 | 0.019 |
| `dc` | 480 | 1.0264 | 0.0181 | 0.2129 | 0.6149 | -3.0056 | 0.481 | 59 | 0.90 | 0.024 |
| `tiros` | 480 | 1.0266 | 0.0163 | 0.2130 | 0.6152 | -3.0019 | 0.483 | 60 | 1.01 | 0.018 |
| **`ajuste`** (campeón) | 480 | 1.0272 | 0.0212 | 0.2126 | 0.6156 | -3.0057 | 0.490 | 58 | 0.78 | 0.035 |
| `poisson_simple` (base) | 480 | 1.0276 | 0.0191 | 0.2132 | 0.6159 | -3.0085 | 0.487 | 52 | 0.86 | 0.023 |
| `cerebro_original_limpio` (ref.) | 480 | 1.0325 | 0.0167 | 0.2130 | 0.6182 | -3.1233 | 0.500 | 48 | 0.93 | 0.033 |
| `mercado_abre_shin` (ref.) | 313 | 1.0517 | 0.0230 | 0.2212 | 0.6330 | — | 0.466 | — | 0.72 | 0.045 |
| `frecuencias` (base) | 480 | 1.0742 | 0.0100 | 0.2292 | 0.6496 | -3.0535 | 0.442 | 59 | 0.92 | 0.036 |
| `cerebro_original_exacto` (ref., desde 14-ago-2026) | 116 | 1.0996 | 0.0349 | 0.2276 | 0.6618 | -3.2497 | 0.422 | 14 | 0.49 | 0.054 |

Cómo leerla:

- `n` distinto = partidos distintos: el mercado de apertura sólo existe en 313 partidos (desde diciembre de 2025) y
  el original exacto en 116. Para comparar hay que usar las tablas pareadas de abajo, no esta.
- **Marcadores exactos** = partidos en que el marcador más probable del modelo fue el que ocurrió. No discrimina:
  `frecuencias`, que dice 1-1 siempre, acierta 59 de 480 (12%), igual que los mejores. La medida útil del marcador
  es la log-verosimilitud (`logv`, mayor es mejor).
- **Pendiente de calibración**: 1 = calibrado; menor que 1 = sobreconfiado. En la PRUEBA todos bajaron respecto de
  DESARROLLO (el mercado de 1.13 a 0.95, `dc` de 1.06 a 0.90, `ajuste` de 1.01 a 0.78): fue un periodo con más
  sorpresas de lo normal. El error de esa pendiente con 480 partidos es de unos 0.13 (escalando el 0.07 medido en DESARROLLO), así que el 0.78 de `ajuste`
  está a menos de 2 ee de 1; aun así es el más sobreconfiado de los candidatos y hay que vigilarlo.
- **Goles**: en la PRUEBA se anotaron 1.66 + 1.28 = 2.94 por partido, contra 1.51 + 1.15 = 2.66 en DESARROLLO. Los
  modelos se adaptan con retraso (`ajuste` pronosticó 1.67 + 1.24; `dc` 1.60 + 1.21; `elo` 1.55 + 1.18); el original
  no se adapta (1.25 + 0.97). Por eso todos tienen peor `logv` de marcador que en DESARROLLO (−3.00 contra −2.87).

### 3.2 Comparaciones pareadas del campeón y de los candidatos

Diferencia = modelo − referencia, en log-loss 1X2 (negativo = el modelo es mejor), sobre los mismos partidos.

**Contra `poisson_simple`** (480 partidos; `poisson_simple` = 1.0276)

| Modelo | Diferencia | ee | IC 95% | z | Diferencia en logv marcador (ee) |
|---|---|---|---|---|---|
| `ajuste` | -0.0004 | 0.0042 | [-0.0085, +0.0079] | -0.1 | +0.0028 (0.0062) |
| `ensamble` | -0.0051 | 0.0031 | [-0.0111, +0.0010] | -1.7 | +0.0191 (0.0048) |
| `dc2` | -0.0032 | 0.0024 | [-0.0079, +0.0016] | -1.3 | +0.0035 (0.0033) |
| `dc` | -0.0012 | 0.0016 | [-0.0043, +0.0018] | -0.8 | +0.0029 (0.0023) |
| `elo` | -0.0055 | 0.0041 | [-0.0135, +0.0023] | -1.3 | +0.0200 (0.0078) |
| `tiros` | -0.0010 | 0.0032 | [-0.0072, +0.0049] | -0.3 | +0.0066 (0.0041) |

Ningún candidato le gana a la línea base por 2 ee en 1X2. En marcador exacto sí hay dos mejoras claras: `ensamble`
(4.0 ee) y `elo` (2.6 ee).

**Contra el modelo original limpio** (`cerebro_original_limpio` = 1.0325, 480 partidos)

| Modelo | Diferencia | ee | IC 95% | z | Diferencia en logv marcador (ee) |
|---|---|---|---|---|---|
| `ajuste` | -0.0054 | 0.0084 | [-0.0211, +0.0119] | -0.6 | +0.1177 (0.0209) |
| `ensamble` | -0.0100 | 0.0069 | [-0.0231, +0.0041] | -1.4 | +0.1340 (0.0192) |
| `dc` | -0.0061 | 0.0063 | [-0.0176, +0.0069] | -1.0 | +0.1177 (0.0188) |
| `elo` | -0.0104 | 0.0063 | [-0.0224, +0.0025] | -1.6 | +0.1349 (0.0185) |
| `poisson_simple` | -0.0049 | 0.0075 | [-0.0186, +0.0102] | -0.7 | +0.1148 (0.0188) |

En resultado (1X2) el motor original limpio no es peor de forma demostrable: todos los intervalos incluyen el cero.
En marcador sí: pierde 0.12 de log-verosimilitud por partido (más de 5 ee) porque subestima los goles en 0.7 por
partido y pronostica 30% de empates cuando hubo 25.6%.

**Contra el modelo original exacto** (con sus priors y capas; sólo desde el 14-ago-2026, 116 partidos; = 1.0996)

| Modelo | Log-loss en esos 116 | Diferencia | ee | IC 95% | Diferencia en logv marcador (ee) |
|---|---|---|---|---|---|
| `ajuste` | 1.1071 | +0.0075 | 0.0172 | [-0.0254, +0.0428] | +0.1396 (0.0373) |
| `ensamble` | 1.0963 | -0.0033 | 0.0147 | [-0.0307, +0.0267] | +0.1524 (0.0340) |
| `dc` | 1.1012 | +0.0016 | 0.0120 | [-0.0222, +0.0252] | +0.1275 (0.0340) |
| `elo` | 1.0920 | -0.0076 | 0.0135 | [-0.0333, +0.0195] | +0.1449 (0.0333) |
| `cerebro_original_limpio` | 1.0973 | -0.0023 | 0.0031 | [-0.0084, +0.0041] | -0.0084 (0.0046) |
| `mercado_cierre_shin` | 1.0581 | -0.0415 | 0.0243 | [-0.0918, +0.0044] | — |

Con franqueza: en estos 116 partidos **nadie** pronosticó bien el resultado. El original exacto (1.0996) y todos los
candidatos (1.092 a 1.107) quedaron al nivel del azar (1.0986); el campeón salió 0.0075 peor que el original exacto,
diferencia que es ruido (ee 0.0172). Sólo el mercado se despega (1.0581). Donde el original sí pierde claro es en el
marcador (0.13 a 0.15 de logv, unas 4 ee) y en calibración (pendiente 0.49: probabilidades demasiado extremas).
Con 116 partidos no se puede decir más.

**Contra el mercado** (momios sin margen por el método de Shin)

| Modelo | vs CIERRE (476): diferencia | ee | IC 95% | z | logv marcador vs cierre (ee) | vs APERTURA (313): diferencia | ee | IC 95% |
|---|---|---|---|---|---|---|---|---|
| `ajuste` | +0.0237 | 0.0080 | [+0.0084, +0.0393] | +3.0 | -0.0457 (0.0098) | +0.0125 | 0.0086 | [-0.0043, +0.0291] |
| `ensamble` | +0.0190 | 0.0073 | [+0.0053, +0.0331] | +2.6 | -0.0298 (0.0087) | +0.0038 | 0.0073 | [-0.0107, +0.0182] |
| `dc2` | +0.0212 | 0.0079 | [+0.0057, +0.0366] | +2.7 | -0.0454 (0.0101) | +0.0039 | 0.0086 | [-0.0125, +0.0217] |
| `dc` | +0.0232 | 0.0077 | [+0.0083, +0.0384] | +3.0 | -0.0460 (0.0100) | +0.0064 | 0.0081 | [-0.0095, +0.0232] |
| `elo` | +0.0185 | 0.0075 | [+0.0040, +0.0334] | +2.5 | -0.0293 (0.0105) | -0.0003 | 0.0076 | [-0.0151, +0.0138] |
| `tiros` | +0.0231 | 0.0073 | [+0.0089, +0.0374] | +3.2 | -0.0420 (0.0090) | +0.0020 | 0.0080 | [-0.0133, +0.0179] |
| `poisson_simple` | +0.0243 | 0.0076 | [+0.0096, +0.0391] | +3.2 | -0.0489 (0.0106) | +0.0082 | 0.0078 | [-0.0068, +0.0240] |
| `cerebro_original_limpio` | +0.0297 | 0.0104 | [+0.0093, +0.0500] | +2.8 | -0.1659 (0.0235) | +0.0117 | 0.0117 | [-0.0114, +0.0357] |

- **Mercado de cierre: nos gana, y no por poco.** Todos los modelos quedan entre 0.019 y 0.030 por detrás, a 2.5 ee o
  más, en resultado y en marcador. En DESARROLLO el campeón estaba a +0.0095 (ee 0.0043); en la PRUEBA, a +0.0237.
  La brecha no se cerró: se parece a la de un modelo de fuerzas simple.
- **Mercado de apertura: empate.** En los 313 partidos con momio de apertura, el cierre le gana a la apertura por
  0.0253 (ee 0.0066, 3.8 ee) y los modelos quedan entre −0.0003 y +0.0125 de la apertura, todos dentro de 2 ee. Es
  decir: el modelo vale más o menos lo que un momio publicado con días de anticipación; lo que no tiene es la
  información de última hora (alineaciones, lesiones, dinero) que el cierre sí incorpora. Reserva: la "apertura" es
  la que guarda ESPN y su pendiente de calibración (0.72) sugiere que es una línea temprana poco afinada.

### 3.3 Por torneo y por fase (log-loss)

| Torneo | n | `ajuste` | `dc` | `ensamble` | `elo` | `poisson_simple` | original limpio | mercado cierre | `ajuste` − `dc` | `ajuste` − mercado (ee) |
|---|---|---|---|---|---|---|---|---|---|---|
| Apertura 2025 | 170 | 0.9530 | 0.9627 | 0.9567 | 0.9639 | 0.9624 | 0.9722 | 0.9505 | -0.0097 | -0.0005 (0.0107) |
| Clausura 2026 | 167 | 1.0397 | 1.0336 | 1.0316 | 1.0268 | 1.0347 | 1.0389 | 1.0038 | +0.0061 | +0.0359 (0.0159) |
| Apertura 2026 | 143 | 1.1008 | 1.0938 | 1.0902 | 1.0859 | 1.0968 | 1.0968 | 1.0631 | +0.0070 | +0.0377 (0.0136) |

`ajuste` ganó en el primer torneo de la PRUEBA y perdió en los dos siguientes. El Apertura 2026 ha sido muy difícil
de pronosticar para todos (los modelos, al nivel del azar; el mercado, 1.063). Liguilla (31 partidos): `ajuste`
0.9851, `dc` 0.9868, mercado 0.9328 (28): demasiado pocos para concluir.

### 3.4 Comprobación hecha a raíz del resultado (sólo DESARROLLO)

Para descartar que el resultado de `ajuste` en la PRUEBA se debiera al cambio de corte (por día en vez de por
bloque), se evaluaron `dc` y `ajuste` en DESARROLLO con corte por día: `ajuste` − `dc` = −0.0073 (ee 0.0013), igual
que por bloque (−0.0072). No es el corte. Son dos corridas más en el registro.

## 4. La decisión y qué tan segura es

**Se aplica la regla tal como se escribió: campeón `ajuste`.** Ningún candidato lo superó en la PRUEBA por más de 2 ee.

Lo que la PRUEBA sí enseña, sin maquillaje:

1. **La ganancia de `ajuste` medida en DESARROLLO está inflada.** Sus variables se eligieron mirando ese mismo periodo
   (entre 309), así que su −0.0072 lleva sesgo de selección. La estimación limpia es la de la PRUEBA: +0.0008 con ee
   0.0045. Juntando todo (3,461 partidos, DESARROLLO por bloque y PRUEBA por día): `ajuste` − `dc` = −0.0061 (ee
   0.0013). La corrección probablemente ayuda algo, pero menos de lo que parecía.
2. **El orden entre candidatos no es estable.** En DESARROLLO: `ajuste` < `ensamble` < `dc2` < `dc` < `elo` < `tiros`.
   En la PRUEBA: `elo` < `ensamble` < `dc2` < `dc` < `tiros` < `ajuste`. Entre el mejor y el peor hay 0.005 a 0.009 de
   log-loss: menos de un punto porcentual de probabilidad por partido. Para el usuario, cualquiera de ellos da
   prácticamente los mismos pronósticos.
3. **`ensamble` es el retador serio.** En la PRUEBA le gana al campeón por 0.0047 en 1X2 (ee 0.0028) y por 0.0163 en
   marcador (ee 0.0051, 3.2 ee); en el conjunto el campeón aún le gana por 0.0018 (ee 0.0009). Si la tendencia de los
   dos últimos torneos sigue, la regla de mejora continua lo adoptará.
4. **Contra el mercado de cierre no hay modelo propio que alcance**, ni aquí ni en DESARROLLO. El valor del modelo
   está en lo que el mercado no da: probabilidades coherentes de marcador, de series de liguilla y de campeón, con
   días o semanas de anticipación.

Archivos: `campeon.json` (modelo, hiperparámetros, métricas, motivo y avisos) y `registro.json` (campeón, cinco
retadores con sus métricas y la regla de adopción).

## 5. Mejora continua: campeón contra retadores hoy

Regla (en `registro.json`): tras cada jornada se reevalúan todos en walk-forward; un retador sólo se adopta si mejora
al campeón por más de 2 ee pareados sobre todo el periodo **y** no empeora en los últimos 8 bloques.

| Retador | Retador − campeón en todo el periodo (3,461) | ee | z | En los últimos 8 bloques (64 partidos, bloques del 25-sep al 6-nov-2026) | ee | ¿Adoptable hoy? |
|---|---|---|---|---|---|---|
| `ensamble` | +0.0018 | 0.0009 | +1.9 | -0.0174 | 0.0081 | no |
| `dc` | +0.0061 | 0.0013 | +4.7 | -0.0170 | 0.0123 | no |
| `dc2` | +0.0053 | 0.0014 | +3.8 | -0.0237 | 0.0156 | no |
| `elo` | +0.0071 | 0.0019 | +3.7 | -0.0285 | 0.0164 | no |
| `tiros` (descartado) | +0.0080 | 0.0018 | +4.4 | -0.0237 | 0.0155 | no |

El campeón sigue delante en el periodo completo, pero **lleva 8 bloques perdiendo contra todos**. Con 64 partidos
eso es compatible con una mala racha (1.4 a 2.1 ee), y la regla exige evidencia sobre todo el periodo para cambiar;
aun así es la señal que hay que mirar jornada a jornada.

## 6. Qué se probó y qué no funcionó

**Cuántas variantes.** 51 variantes de 6 familias en DESARROLLO (dc 12, dc2 7, elo 14, tiros 3, ajuste 9, ensamble
6), más 309 variables examinadas una por una. Con tantas pruebas, una mejora de 2 ee aparece por puro azar; por eso
la vara fue la PRUEBA intocada. Detalle en `informes/candidatos.md` y `VARIABLES.md`.

**Lo que sí funciona** (DESARROLLO, 2,981 partidos; azar 1.0986):

- Saber qué equipos juegan: de 1.0702 (`frecuencias`) a 1.0309 (`poisson_simple`): −0.039 (ee 0.005). Es, con mucho,
  lo más importante.
- Ajustar la correlación de marcadores bajos (`rho` ≈ −0.06): mejora el marcador exacto (+0.0029 de logv, ee
  0.0012), no el 1X2.
- Tiros de los últimos 10 partidos, viaje del visitante y rotación de su once (`ajuste`): −0.0072 en DESARROLLO
  (ee 0.0013), no confirmado en la PRUEBA (+0.0008, ee 0.0045).

**Lo que no funciona** (cifras de DESARROLLO):

| Idea | Resultado | Lectura |
|---|---|---|
| Rachas (ganadas, perdidas, invicto) | 2 de 28 variables con p < 0.05: lo que da el azar | La racha vigente no agrega nada a la fuerza del equipo. |
| Historial directo y "dominios" | 1 de 17 con p < 0.05, y con el signo contrario | Con ~10 cruces por pareja no se distingue un dominio de la diferencia de fuerza. |
| Descanso y calendario | 0 de 15 con p < 0.05 | Sin señal (sólo se ven partidos de liga). |
| Posición en la tabla y motivación | coeficientes menores que 0.01 | Sin señal propia. |
| Forma reciente ("el momento") | signo negativo una vez puesta la fuerza | Reaccionar a lo último empeora. |
| Elo que reacciona rápido | K = 35: 1.0368 a 1.0390; K = 8: 1.0316 | La fuerza se mueve despacio. |
| Dar más peso a la liguilla (el original usa ×1.25) | ×2: +0.0008 (ee 0.0004); ×0.5: −0.0002 (ee 0.0003) | No ayuda; va en la dirección contraria. |
| Efecto propio de liguilla en goles y localía | −0.0001 (ee 0.0002) | Sin señal. |
| Ventaja de local por equipo | −0.0006 (ee 0.0006) | Existe pero es chica; no mejora el pronóstico. |
| Olvido extra al cambiar de torneo | −0.0002 (ee 0.0005) y +0.0001 (ee 0.0009) | Sin señal. |
| Mezclar goles con "goles merecidos" por tiros | +0.0022 a +0.0092 (hasta 4 ee peor) | Los tiros sirven como variable aparte, no como sustituto del gol. |
| Suspendidos | −0.0004 (ee 0.0004) | Sin señal medible. |
| Altitud | +0.0001 (ee 0.0002) | Sin señal medible. |
| Conocer el once real una hora antes | no agrega a lo deducible del partido anterior | Medido con proporción de titulares habituales. |
| Ensambles | +0.0029 en DESARROLLO (ee 0.0010); −0.0047 en la PRUEBA (ee 0.0028) | Contradictorio: queda como retador. |

**El mercado como variable** aporta 7 veces más que la mejor variable propia (0.018 de log-loss por partido), pero no
existe para rondas futuras: es referencia, no insumo.

## 7. Incertidumbre de los parámetros (para la simulación de campeón y series)

**Método.** Aproximación normal de Laplace: los parámetros del Dixon-Coles base (constante, ventaja de local, ataque
y defensa de cada equipo) se muestrean de N(estimación, H⁻¹), con H la hessiana de la verosimilitud de Poisson
ponderada y penalizada en el óptimo (gradiente verificado: menor que 1e-13). Los 14 coeficientes de la corrección se
muestrean igual con la hessiana de su regresión. `rho` se deja fijo. No es bootstrap. `malla(n)` devuelve la
estimación puntual en k = 0 y n − 1 muestras.

**Tamaño.** Hoy el error estándar del logaritmo de una lambda es 0.167 en promedio (0.14 a 0.26; los mayores son
los de Atlante, recién ascendido): un IC de 95% de más o menos ×/÷ 1.39 sobre los goles esperados. En probabilidad de
victoria local, unos ±0.15 (por ejemplo Chivas-Cruz Azul: 0.476, IC 95% por parámetros de 0.335 a 0.619). El rating
de un equipo tiene ee de 0.22 a 0.26 goles (0.41 el de Atlante), contra una dispersión de 0.5 goles entre equipos: el orden de la tabla
de fuerzas es incierto entre vecinos.

**¿Es razonable ese ancho?** Dos comprobaciones, ambas sólo con DESARROLLO:

1. *Contra lo que pasó.* En los 18 torneos de DESARROLLO se congeló el pronóstico al inicio y a la mitad del torneo
   y se compararon los goles a favor y en contra de cada equipo en lo que restaba de fase regular con lo esperado
   (650 casos en cada corte). Si sólo hubiera azar de Poisson, la varianza del error estandarizado sería 1.

   | Corte | Partidos restantes por equipo | Varianza sólo con Poisson | Varianza con la incertidumbre de parámetros | Cobertura del intervalo de 90%: sólo Poisson → con parámetros |
   |---|---|---|---|---|
   | Inicio del torneo | 16.7 | 1.33 | 0.96 | 87.1% → 91.7% |
   | Mitad del torneo | 7.9 | 1.09 | 0.92 | 90.6% → 93.2% |

   Sin incertidumbre de parámetros los intervalos quedan cortos (varianza 1.33 al inicio); con ella quedan bien,
   algo holgados (0.96 y 0.92): el ancho es razonable y ligeramente conservador.
2. *Contra un bootstrap paramétrico* (200 réplicas simulando los goles del historial y reajustando `dc`): da un ee de
   0.119 para el logaritmo de lambda, contra 0.166 de Laplace en ese mismo `dc` (razón 1.39 ≈ √2). La diferencia es
   la esperada: el bootstrap sólo mide el ruido de muestreo; Laplace trata los partidos viejos, que pesan menos,
   como menos informativos, que es la forma de reconocer que la fuerza de los equipos cambia. Repitiendo la
   comprobación 1 con el ancho del bootstrap, la varianza sale 1.10 al inicio del torneo (intervalos cortos) y 0.99
   a la mitad (exactos). Es decir: la verdad está entre los dos; a plazo corto (una jornada, una serie de liguilla)
   Laplace exagera la varianza total de los goles en torno a 8%, y a plazo de un torneo el bootstrap la queda a deber
   en 10%. Se dejó Laplace por ser el lado prudente.

**Lo que no incluye**: la incertidumbre de `rho`, la de los hiperparámetros (vida media, encogimiento) ni la del
modelo mismo (que `elo` o `ensamble` pronostiquen distinto). Para un retador sin verosimilitud propia (`elo`,
`ensamble`) la dispersión se toma prestada de un `dc` ajustado con el mismo historial (atributo `incertidumbre`).

## 8. API de producción (`modelo/pronostico.py`)

```python
from modelo.pronostico import Pronosticador, tabla_pronosticos
p = Pronosticador()                       # campeón de campeon.json con todo lo jugado: 6.5 s
p.equipos                                 # los 18 del torneo, en orden alfabético
p.partidos(df)                            # lam_l, lam_v, rho y explicación por factores (1.4 s)
p.malla(n=2000, fase="liguilla", semilla=0)   # n x 18 x 18; k = 0 puntual, k >= 1 muestras (1 a 3 s)
p.fuerzas()                               # ataque, defensa, rating, ventaja de local y sus errores estándar
Pronosticador(corte="2025-03-07", modelo="ensamble")   # cualquier retador, en cualquier fecha
python3 -m modelo.pronostico              # imprime los pendientes y la tabla de fuerzas
```

- Se ajusta igual que en el walk-forward: coeficientes fijados al inicio del torneo en curso y fuerzas al día. Las
  variables de cada partido se recalculan truncando el historial en el corte. Verificado: con corte en un bloque
  pasado reproduce las lambdas guardadas en `pred/` con error menor que 1e-15 (`ajuste`, `dc`, `elo`, `ensamble`).
- `explica` es una lista de factores multiplicativos cuyo producto es exactamente la lambda: media de la liga,
  ataque y defensa de cada equipo, ventaja de local, y luego viaje, rotación, tiros y la constante de la corrección.
- La diagonal de la malla es NaN (nadie juega contra sí mismo).
- Pruebas: `python3 -m pytest modelo/pruebas/test_pronostico.py -q` → 22 pruebas, 46 s. Cubren el contrato de formas,
  lambdas positivas, k = 0 igual a `partidos()`, reproducibilidad con semilla, reproducción de `pred/` con corte
  pasado (5 casos), que el futuro no cambia el pronóstico, hessiana en el óptimo, ancho de la incertidumbre, cruces
  hipotéticos de liguilla y retadores por nombre o por instancia.
- Antes de pronosticar hay que actualizar datos y caché de variables (`espn_descarga.py actualizar` y
  `variables.actualizar("bloque")`): los coeficientes de la corrección leen esa caché. Desde la auditoría del 2026-11-10
  el `Pronosticador` lo comprueba al crearse: si la caché no está al día emite un `RuntimeWarning` y deja el texto en
  `avisos` (3 pruebas más: 25 en total). Ver `AUDITORIA.md`.

## 9. Pronóstico de los 10 partidos pendientes del Apertura 2026

`Pronosticador()` con todo lo jugado hasta el 8-nov-2026 (corte 10-nov-2026 10:02 UTC). `rho` = −0.057.

| Fecha (CDMX) | Local | Visitante | λ local | λ visita | P(local) | P(empate) | P(visita) | Marcador más probable | P(más de 2.5) | P(ambos anotan) |
|---|---|---|---|---|---|---|---|---|---|---|
| 14-nov 17:00 | Querétaro | Monterrey | 1.18 | 1.64 | 0.267 | 0.258 | 0.475 | 1-1 (0.122) | 0.534 | 0.564 |
| 20-nov 19:00 | Puebla | Atlético San Luis | 1.36 | 1.45 | 0.346 | 0.265 | 0.389 | 1-1 (0.125) | 0.534 | 0.576 |
| 20-nov 21:00 | Tijuana | Atlante | 2.07 | 0.99 | 0.617 | 0.216 | 0.167 | 1-1 (0.102) | 0.588 | 0.553 |
| 20-nov 21:00 | Juárez | Atlas | 1.63 | 1.44 | 0.415 | 0.251 | 0.333 | 1-1 (0.115) | 0.592 | 0.620 |
| 21-nov 16:50 | Pachuca | Toluca | 1.68 | 1.46 | 0.423 | 0.248 | 0.329 | 1-1 (0.113) | 0.606 | 0.630 |
| 21-nov 17:00 | Santos | León | 1.63 | 1.36 | 0.432 | 0.254 | 0.314 | 1-1 (0.118) | 0.575 | 0.605 |
| 21-nov 19:00 | Pumas | Monterrey | 1.58 | 1.53 | 0.386 | 0.250 | 0.364 | 1-1 (0.114) | 0.602 | 0.629 |
| 21-nov 21:00 | Tigres | América | 1.42 | 1.43 | 0.367 | 0.264 | 0.369 | 1-1 (0.124) | 0.543 | 0.584 |
| 22-nov 17:07 | Chivas | Cruz Azul | 1.64 | 1.18 | 0.476 | 0.257 | 0.266 | 1-1 (0.122) | 0.535 | 0.564 |
| 22-nov 19:00 | Querétaro | Necaxa | 1.47 | 1.23 | 0.421 | 0.270 | 0.309 | 1-1 (0.128) | 0.507 | 0.552 |

- **Momios de ESPN**: sólo existen para Querétaro-Monterrey (DraftKings, capturados el 10-nov): 3.40 / 3.60 / 1.952,
  que sin margen (Shin) son 0.267 / 0.251 / 0.481. El modelo da 0.267 / 0.258 / 0.475: coinciden. En goles, el
  mercado da 0.594 a más de 2.5 (momios 1.541 y 2.25) y el modelo 0.534. Los otros nueve aún no tienen momios.
- El marcador más probable es 1-1 en los diez, con 10% a 13%: es lo normal en partidos parejos y la razón por la que
  "acertar el marcador" es mal criterio. Lo informativo son las lambdas y las probabilidades.
- Los dos partidos de Querétaro y los dos de Monterrey usan la misma información; el del 22-nov cambiará cuando se
  juegue el del 14.
- Ejemplo de explicación (Tijuana-Atlante, λ local 2.07): media de la liga 1.22 × ataque de Tijuana 1.05 × defensa
  de Atlante 1.12 × ventaja de local 1.28 × viaje del visitante 1.10 (Atlante viaja 2,305 km) × tiros 1.02 ×
  rotación 1.00 × constante 1.00.

Tabla de fuerzas de hoy (goles frente a un rival promedio en cancha neutral; ee entre paréntesis): América +0.86
(0.23), Toluca +0.81 (0.26), Cruz Azul +0.66 (0.24), Chivas +0.61 (0.23), Monterrey +0.44 (0.25), Pachuca +0.41
(0.24), Tigres +0.23 (0.22), Pumas +0.12 (0.23), Tijuana −0.14 (0.24), Atlético San Luis −0.26 (0.24), León −0.29
(0.25), Atlas −0.30 (0.24), Necaxa −0.38 (0.25), Querétaro −0.45 (0.22), Atlante −0.48 (0.41), Santos −0.48 (0.25),
Juárez −0.65 (0.25), Puebla −0.71 (0.24).

## 10. Límites

1. **La PRUEBA es chica para lo que se quiere distinguir.** Con 480 partidos el error pareado entre candidatos es de
   0.003 a 0.006 y las diferencias reales son de ese tamaño o menores. No hay forma de saber hoy cuál de los seis es
   el mejor; sí se sabe que todos son parecidos y que ninguno alcanza al mercado de cierre.
2. **La PRUEBA ya se usó.** A partir de aquí la única validación limpia son los partidos que se jueguen.
3. **El campeón no demostró su ventaja fuera de muestra** y salió sobreconfiado en la PRUEBA (pendiente 0.78).
4. **El nivel de goles cambió** (2.94 por partido en la PRUEBA contra 2.66): los modelos lo siguen con retraso y
   subestiman un poco los goles del visitante.
5. **Liguilla**: 31 partidos en la PRUEBA y 274 en DESARROLLO. Ningún efecto propio de la fase final resultó
   demostrable, y en DESARROLLO todos los modelos pronostican peor la liguilla (campeón 1.039 contra 1.021).
6. **El modelo pronostica 90 minutos.** Tiempos extra, penales y criterios de desempate corresponden al simulador.
7. **La corrección depende de datos de ESPN** (tiros y alineaciones de los últimos partidos). Si faltan, la variable
   queda vacía y la corrección de ese factor es nula.
8. **`rho` se estima en dos etapas** y su incertidumbre no entra en las muestras.
9. **Momios de apertura**: sólo 313 partidos y de una sola fuente.

## 11. Estado

**Terminado**

- Pre-registro escrito antes de abrir la PRUEBA (sección 1); PRUEBA abierta una sola vez, por día, con los 6
  candidatos y 7 referencias; bitácora en `pred/ACCESOS_PRUEBA.log`.
- Tablas de métricas y pareadas con IC de 95% contra `poisson_simple`, original limpio, original exacto (desde el
  14-ago-2026), mercado de cierre y de apertura.
- `campeon.json` y `registro.json` (campeón, 5 retadores, 7 referencias, regla de adopción).
- `pronostico.py` con el contrato completo, incertidumbre de Laplace verificada, y 22 pruebas que pasan.
- Pronóstico de los 10 pendientes con el momio disponible.

**Faltó o es dudoso**

- `cerebro_original_limpio` en DESARROLLO: su corrida (otro proceso, lenta) no había terminado al cerrar; sólo se
  reportan sus cifras de la PRUEBA. Al terminar: `python3 -m modelo.arnes comparar cerebro_original_limpio ajuste dc`.
- No se evaluó la PRUEBA con corte por bloque (se pidió una sola pasada, por día). La cifra "todo el periodo" de la
  sección 5 mezcla DESARROLLO por bloque con PRUEBA por día.
- No se midió si integrar la incertidumbre de parámetros en el 1X2 mejora la calibración del campeón.
- `candidatos.Ajuste._z` falla (arreglo de sólo lectura) cuando recibe las variables como columnas; `pronostico.py`
  lo evita inyectando las filas en la tabla de variables, sin tocar ese archivo.
- La incertidumbre de `elo` y `ensamble` es prestada de `dc`, no propia.
