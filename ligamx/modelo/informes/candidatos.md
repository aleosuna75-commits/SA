# Candidatos C1 a C6 · evaluación en DESARROLLO

Generado el 2026-11-10. Código: `modelo/familias/candidatos.py`. Protocolo del arnés (`modelo/ARNES.md`): walk-forward
por bloques (510 cortes de lunes y viernes), DESARROLLO = Apertura 2016 a Clausura 2025, **2,981 partidos**. La PRUEBA
no se tocó. Toda diferencia es pareada por partido con error estándar (ee) por bootstrap de bloques; `d < 0` en
log-loss favorece al modelo, `d > 0` en log-verosimilitud del marcador (logv) también.

## 1. Resumen

- Se evaluaron **51 variantes** (todas en `registro_variantes.jsonl`): dc 12, dc2 7, elo 14, tiros 3, ajuste 9,
  ensamble 6. Con 51 comparaciones contra la misma referencia, la mayor diferencia esperable por puro azar es de
  unas 2.8 ee: sólo lo que pasa de ahí con holgura es un hallazgo.
- **Lo único que pasa esa vara es `ajuste`** (C5): log-loss **1.0225** contra 1.0297 de `dc` (d = −0.0072, ee 0.0013,
  z = −5.4) y contra 1.0309 de `poisson_simple` (d = −0.0084, ee 0.0014, z = −5.9). Mejora en los 10 años y en 16 de
  18 torneos. Frente al mercado de cierre queda a +0.0095 (ee 0.0043) en los 1,671 partidos con momios: **cierra la
  mitad de la brecha** que tenía `poisson_simple` (+0.0185).
- La estructura del modelo de fuerzas casi no importa: `dc`, `dc2`, `elo` y `poisson_simple` quedan todos entre 1.029 y
  1.032, dentro de 2 ee entre sí. Estimar `rho` sí mejora el marcador exacto (logv +0.0029, ee 0.0012, frente a
  `poisson_simple`), no el 1X2.
- Mezclar goles con goles esperados por tiros en el "resultado" (C4) **empeora** el 1X2 (w = 0.7: +0.0022, z = +2.2;
  w = 0.3: +0.0092, z = +4.0). Los tiros sirven como variable aparte (son 70% de la ganancia de `ajuste`), no como
  sustituto del marcador.
- El ensamble (C6) no mejora el 1X2 de `ajuste` (+0.0029, z = +2.9: peor), pero `ajuste` + `elo` da el mejor marcador
  exacto (logv −2.8665 contra −2.8707; d = +0.0042, ee 0.0021).

## 2. Finalistas (el mejor de cada C) y cómo usarlos

```python
from modelo.familias import candidatos as C
f = C.finalistas()          # {"dc", "dc2", "elo", "tiros", "ajuste", "ensamble"} -> instancias con hiperparámetros fijos
C.ESTADO, C.DESCRIPCION     # cuáles se recomiendan y explicación llana de cada uno
```

| Nombre (archivo en `pred/`) | Qué es | Hiperparámetros fijos | Variante del registro | Estado |
|---|---|---|---|---|
| `dc` | C1 Dixon-Coles penalizado | vida media 365 d, ridge 4, rho perfilada | `dc_vm365_r4` | finalista |
| `dc2` | C2: `dc` + ventaja de local por equipo | + `ridge_local` 30 | `dc2_a_local30` | referencia: no pasa 2 ee |
| `elo` | C3 Elo con margen de goles | K = 8, regresión 0.15 entre torneos | `elo_k8_reg0.15` | finalista (componente) |
| `tiros` | C4: `dc` con resultado 0.7·goles + 0.3·xg | `w_goles` 0.7 | `tiros_w0.7` | descartado: peor que `dc` |
| `ajuste` | C5: `dc` + corrección con 6 variables | ridge 1000; grupos viaje, rotación, tiros | `ajuste_r1000_vrt` | **finalista: el mejor en 1X2** |
| `ensamble` | C6: media de lambdas de `ajuste` y `elo` | modo `lambdas` | `ens_lambdas_aj_elo` | finalista: el mejor en marcador |

Los seis se reevaluaron con su nombre definitivo (sin volver a registrarlos) y reproducen al dígito la cifra de la
variante registrada. Predicciones en `modelo/pred/<nombre>.parquet` y matrices en `modelo/cache/M_<nombre>.npz`.

### 2.1 Métricas en DESARROLLO (n = 2,981)

| modelo | log-loss | ee | RPS | Brier | logv marcador | acierto | pendiente calib. | error calib. | goles pron. |
|---|---|---|---|---|---|---|---|---|---|
| `dc` | 1.0297 | 0.0066 | 0.2117 | 0.6183 | -2.8765 | 0.479 | 1.06 | 0.014 | 1.49+1.14 |
| `dc2` | 1.0291 | 0.0066 | 0.2114 | 0.6179 | -2.8759 | 0.486 | 1.06 | 0.012 | 1.49+1.14 |
| `elo` | 1.0316 | 0.0063 | 0.2120 | 0.6194 | -2.8766 | 0.481 | 1.11 | 0.011 | 1.50+1.14 |
| `tiros` | 1.0319 | 0.0058 | 0.2123 | 0.6197 | -2.8753 | 0.480 | 1.19 | 0.017 | 1.47+1.17 |
| **`ajuste`** | **1.0225** | 0.0071 | **0.2093** | **0.6134** | -2.8707 | **0.488** | 1.01 | 0.011 | 1.53+1.16 |
| `ensamble` | 1.0254 | 0.0067 | 0.2102 | 0.6152 | **-2.8665** | 0.480 | 1.08 | 0.017 | 1.51+1.15 |
| `poisson_simple` (base) | 1.0309 | 0.0071 | 0.2119 | 0.6189 | -2.8793 | 0.481 | 0.99 | 0.013 | 1.49+1.14 |
| `frecuencias` (base) | 1.0702 | 0.0043 | 0.2252 | 0.6467 | -2.9242 | 0.450 | 0.99 | 0.014 | 1.56+1.17 |

Observado: 1.510 + 1.154 goles; local 45.0%, empate 26.8%, visita 28.2%. Empate medio pronosticado: `dc` 26.3%,
`elo` 26.5%, `ajuste` 25.8%, `ensamble` 26.1%, `poisson_simple` 25.0% (rho corrige el déficit de empates del Poisson
independiente). Pendiente de calibración: 1 = calibrado, > 1 = tímido. `ajuste` es el único candidato sin timidez
(1.01); `tiros` es el más tímido (1.19): la mezcla con tiros comprime las diferencias entre equipos.
`cerebro_original_limpio` no aparece: su evaluación seguía corriendo al cerrar este informe (ver §6).

### 2.2 Comparación pareada contra `poisson_simple` (2,981) y contra el mercado de cierre (1,671 con momios)

| modelo | d_ll vs poisson | ee | z | d_logv vs poisson (ee) | ll con momios | d_ll vs mercado | ee | z | d_logv vs mercado (ee) |
|---|---|---|---|---|---|---|---|---|---|
| `dc` | -0.0012 | 0.0008 | -1.5 | +0.0029 (0.0012) | 1.0214 | +0.0186 | 0.0045 | +4.1 | -0.0355 (0.0058) |
| `dc2` | -0.0018 | 0.0011 | -1.7 | +0.0034 (0.0015) | 1.0211 | +0.0182 | 0.0046 | +4.0 | -0.0363 (0.0059) |
| `elo` | +0.0007 | 0.0018 | +0.4 | +0.0027 (0.0040) | 1.0225 | +0.0197 | 0.0044 | +4.5 | -0.0367 (0.0063) |
| `tiros` | +0.0010 | 0.0015 | +0.6 | +0.0040 (0.0020) | 1.0244 | +0.0216 | 0.0045 | +4.8 | -0.0352 (0.0058) |
| **`ajuste`** | **-0.0084** | 0.0014 | **-5.9** | +0.0086 (0.0021) | 1.0123 | **+0.0095** | 0.0043 | +2.2 | -0.0274 (0.0054) |
| `ensamble` | -0.0055 | 0.0012 | -4.5 | +0.0128 (0.0024) | 1.0159 | +0.0130 | 0.0042 | +3.1 | -0.0250 (0.0052) |
| `frecuencias` | +0.0392 | 0.0053 | +7.4 | -0.0449 (0.0073) | 1.0671 | +0.0643 | 0.0074 | +8.7 | -0.0908 (0.0100) |
| `poisson_simple` | 0 | | | 0 | 1.0213 | +0.0185 | 0.0046 | +4.0 | -0.0374 (0.0061) |

Mercado: `mercado_cierre_shin` 1.0028 en 1X2; `mercado_cierre_marcador` −2.8460 en marcador. Entre finalistas:

- `ajuste` − `dc`: log-loss −0.0072 (ee 0.0013, z −5.4); RPS −0.0023 (ee 0.0004); logv +0.0058 (ee 0.0018, z +3.3).
- `ensamble` − `ajuste`: log-loss +0.0029 (ee 0.0010, z +2.9); logv +0.0042 (ee 0.0021, z +2.0).
- `ensamble` − `dc`: log-loss −0.0043 (ee 0.0009, z −4.6); logv +0.0100 (ee 0.0019, z +5.4).
- `dc2` − `dc`: log-loss −0.0006 (ee 0.0006, z −1.0). `elo` − `dc`: +0.0019 (ee 0.0014, z +1.3). `tiros` − `dc`:
  +0.0022 (ee 0.0010, z +2.2).

### 2.3 Fase regular contra liguilla (log-loss; d = modelo − `poisson_simple`, ee entre paréntesis)

| modelo | ll regular (n = 2,707) | d regular | ll liguilla (n = 274) | d liguilla |
|---|---|---|---|---|
| `dc` | 1.0285 | -0.0010 (0.0009) | 1.0415 | -0.0036 (0.0019) |
| `dc2` | 1.0280 | -0.0015 (0.0011) | 1.0403 | -0.0048 (0.0030) |
| `elo` | 1.0300 | +0.0005 (0.0019) | 1.0471 | +0.0020 (0.0043) |
| `tiros` | 1.0310 | +0.0015 (0.0016) | 1.0412 | -0.0039 (0.0036) |
| `ajuste` | 1.0209 | -0.0086 (0.0016) | 1.0389 | -0.0062 (0.0038) |
| `ensamble` | 1.0237 | -0.0058 (0.0014) | 1.0418 | -0.0033 (0.0029) |
| `poisson_simple` | 1.0295 | 0 | 1.0451 | 0 |
| `mercado_cierre_shin` (con momios) | 0.9973 (n = 1,502) | -0.0194 (0.0048) | 1.0520 (n = 169) | -0.0109 (0.0139) |

La liguilla es más difícil para todos (≈ 1.04 contra ≈ 1.02-1.03), también para el mercado. La ganancia de `ajuste`
tiene el mismo signo en liguilla, pero con 274 partidos no se distingue de cero (1.6 ee).

### 2.4 Por año (log-loss)

| año | n | poisson_simple | dc | dc2 | elo | tiros | ajuste | ensamble | ajuste − dc (ee) | mercado (n) | ajuste − mercado (ee) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 | 167 | 1.0355 | 1.0333 | 1.0356 | 1.0472 | 1.0389 | 1.0300 | 1.0366 | -0.0033 (0.0038) | — | — |
| 2017 | 334 | 1.0662 | 1.0644 | 1.0653 | 1.0665 | 1.0641 | 1.0626 | 1.0626 | -0.0018 (0.0039) | — | — |
| 2018 | 334 | 1.0348 | 1.0336 | 1.0327 | 1.0375 | 1.0377 | 1.0311 | 1.0328 | -0.0025 (0.0031) | — | — |
| 2019 | 352 | 1.0097 | 1.0057 | 1.0019 | 1.0082 | 1.0070 | 1.0009 | 1.0024 | -0.0049 (0.0037) | 0.9812 (86) | +0.0255 (0.0203) |
| 2020 | 261 | 1.0378 | 1.0333 | 1.0313 | 1.0304 | 1.0337 | 1.0285 | 1.0280 | -0.0048 (0.0034) | 0.9782 (90) | +0.0011 (0.0180) |
| 2021 | 341 | 1.0495 | 1.0486 | 1.0471 | 1.0488 | 1.0486 | 1.0458 | 1.0462 | -0.0028 (0.0035) | 1.0257 (328) | +0.0203 (0.0115) |
| 2022 | 341 | 1.0457 | 1.0459 | 1.0471 | 1.0482 | 1.0460 | 1.0329 | 1.0391 | -0.0131 (0.0034) | 1.0251 (336) | +0.0042 (0.0101) |
| 2023 | 341 | 1.0304 | 1.0318 | 1.0314 | 1.0332 | 1.0326 | 1.0224 | 1.0260 | -0.0094 (0.0051) | 1.0166 (341) | +0.0058 (0.0081) |
| 2024 | 340 | 1.0046 | 1.0035 | 1.0023 | 1.0042 | 1.0106 | 0.9865 | 0.9939 | -0.0169 (0.0045) | 0.9789 (320) | +0.0089 (0.0091) |
| 2025 | 170 | 0.9700 | 0.9725 | 0.9741 | 0.9700 | 0.9785 | 0.9598 | 0.9629 | -0.0127 (0.0076) | 0.9560 (170) | +0.0039 (0.0135) |

`ajuste` mejora a `dc` en los 10 años y en 16 de 18 torneos (peor torneo +0.0008, mejor −0.0177). **La ganancia no es
pareja en el tiempo**: −0.0033 (ee 0.0015; n = 1,789) en 2016-2021 y −0.0131 (ee 0.0025; n = 1,192) en 2022-2025.
No es que al principio los coeficientes estuvieran demasiado encogidos: con ridge 300 la ganancia de 2016-2021 es
−0.0026 (ee 0.0021), no mayor. La señal de tiros, viaje y rotación fue más fuerte en los años recientes y no se sabe
por qué (ver §6); la PRUEBA cae del lado reciente.

## 3. Qué se probó en cada candidato

Todas las tablas: log-loss en DESARROLLO (n = 2,981).

**C1 `dc` (12 variantes).** `log lam_l = c + h + atk[local] + dfn[visita]`, `log lam_v = c + atk[visita] + dfn[local]`,
prior normal (ridge) sobre ataque y defensa, peso `0.5^(antigüedad / vida media)`, ventana de 10 vidas medias. Dos
etapas: (1) verosimilitud de Poisson penalizada por Newton (matriz rala, arranque en caliente; mismo algoritmo que
`base.ajustar_poisson`); (2) `rho` por verosimilitud perfilada dadas las medias (cóncava, Newton en una dimensión).
No es la verosimilitud conjunta exacta de Dixon-Coles: con `rho` ≈ −0.06 el efecto sobre las lambdas es de milésimas.

| vida media (días) | ridge 1 | ridge 4 | ridge 10 |
|---|---|---|---|
| 180 | 1.0326 | 1.0310 | 1.0313 |
| 365 | 1.0306 | **1.0297** | 1.0300 |
| 730 | 1.0320 | 1.0310 | 1.0311 |
| 1095 | 1.0330 | 1.0320 | 1.0319 |

La superficie es plana: de la mejor a la peor hay 0.0033 y la mejor queda a −0.0012 (ee 0.0008) de `poisson_simple`.
El logv del marcador prefiere más encogimiento (ridge 10: −2.8749 con 365 d; −2.8748 con 730 d).

**C2 `dc2` (7 variantes), cada mejora por separado sobre `dc_vm365_r4`.** Regla: se queda sólo si mejora más de 2 ee.

| variante | log-loss | d vs `dc` | ee | z | ¿se queda? |
|---|---|---|---|---|---|
| (a) ventaja de local por equipo, ridge 30 | 1.0291 | -0.0006 | 0.0006 | -1.0 | no |
| (a) ventaja de local por equipo, ridge 100 | 1.0293 | -0.0004 | 0.0003 | -1.6 | no |
| (b) efecto de liguilla en total y en localía (ridge 50) | 1.0296 | -0.0001 | 0.0002 | -0.6 | no |
| (c) peso de liguilla × 0.5 | 1.0295 | -0.0002 | 0.0003 | -0.9 | no |
| (c) peso de liguilla × 2 | 1.0305 | +0.0008 | 0.0004 | +1.9 | no |
| (d) olvido 0.9 por cambio de torneo | 1.0296 | -0.0002 | 0.0005 | -0.4 | no |
| (d) olvido 0.8 por cambio de torneo | 1.0298 | +0.0001 | 0.0009 | +0.1 | no |

**Ninguna pasa la regla**, así que `dc2` = `dc` a efectos prácticos. Se guarda como `dc2` la de menor log-loss (ventaja
de local por equipo, ridge 30) sólo como referencia. Dar más peso a la liguilla (lo que hacía el motor original, ×1.25)
va en la dirección equivocada.

**C3 `elo` (14 variantes).** Elo con multiplicador por margen de goles (el del Elo mundial), ventaja de local en puntos
Elo que se actualiza sola, regresión a la media de los equipos activos al cambiar de torneo y conversión a goles con
dos regresiones de Poisson sobre la diferencia de Elo previa a cada partido, reajustadas al inicio de cada torneo.

| K | regresión 0 | regresión 0.15 | regresión 0.30 |
|---|---|---|---|
| 8 | 1.0321 | **1.0316** | — |
| 12 | 1.0323 | 1.0323 | 1.0332 |
| 18 | 1.0331 | 1.0336 | 1.0348 |
| 25 | 1.0345 | 1.0353 | 1.0367 |
| 35 | 1.0368 | 1.0377 | 1.0390 |

La rejilla original (K de 12 a 35) tuvo su mínimo en el borde, así que se añadió K = 8 (dos variantes): mejora
0.0007 (ee 0.0004). El mínimo sigue en el borde, pero la curva ya es plana y no se siguió bajando. Lectura: en la
Liga MX la fuerza de un equipo se mueve despacio; reaccionar rápido al último resultado empeora.

**C4 `tiros` (3 variantes).** Mismo ajuste que `dc_vm365_r4`, pero el resultado de cada partido es
`w·goles + (1−w)·xg`, con xg = regresión lineal ponderada de goles sobre tiros fuera de puerta y tiros a puerta
estimada sólo con el historial de cada corte (último ajuste: 0.58 − 0.05·fuera + 0.26·a puerta).

| w (peso de los goles) | log-loss | d vs `dc` | ee | z | logv marcador |
|---|---|---|---|---|---|
| 1 (= `dc`) | 1.0297 | 0 | | | -2.8765 |
| 0.7 | 1.0319 | +0.0022 | 0.0010 | +2.2 | -2.8753 |
| 0.5 | 1.0348 | +0.0051 | 0.0016 | +3.1 | -2.8774 |
| 0.3 | 1.0389 | +0.0092 | 0.0023 | +4.0 | -2.8817 |

Empeora de forma monótona. La pendiente de calibración (1.19 con w = 0.7) indica por qué: un xg lineal en tiros varía
mucho menos entre equipos que los goles, y al mezclarlo las fuerzas se comprimen hacia el promedio. No se probó
reescalar el xg ni otra vida media (habría sido exploración fuera del encargo).

**C5 `ajuste` (9 variantes).** Base = `dc_vm365_r4`. Corrección `lam' = lam · exp(b0 + z·b)` para local y visita por
separado, con z = variables estandarizadas con media y desviación del pasado (faltante = 0). Coeficientes por
regresión de Poisson con la lambda base como compensación y ridge sobre `b`; se reajustan al inicio de cada torneo (18
reajustes) con todos los partidos anteriores desde julio de 2011, usando para cada uno la lambda base que se habría
pronosticado en su propio bloque (el modelo recorre internamente el historial; nada posterior al corte). Las variables
salen de `cache/variables_bloque.parquet`.

| variante | log-loss | d vs `dc` | ee | z |
|---|---|---|---|---|
| 9 variables, ridge 300 | 1.0224 | -0.0073 | 0.0017 | -4.3 |
| 9 variables, ridge 1000 | 1.0228 | -0.0070 | 0.0015 | -4.8 |
| 9 variables, ridge 3000 | 1.0240 | -0.0057 | 0.0010 | -5.4 |
| **6 variables (viaje, rotación, tiros), ridge 1000 = `ajuste`** | **1.0225** | -0.0072 | 0.0013 | -5.4 |

Se eligió ridge 1000 y no 300 aunque 300 da 0.0004 menos: la diferencia es ruido y más encogimiento es más prudente.

Ablación sobre el modelo de 9 variables (ridge 1000): cuánto empeora el log-loss al quitar cada grupo.

| grupo que se quita | variables | log-loss | aporte del grupo (d al quitarlo) | ee | z |
|---|---|---|---|---|---|
| tiros | `juego10_tiros_f_l`, `_c_l`, `_f_v`, `_c_v` | 1.0279 | **+0.0051** | 0.0012 | +4.3 |
| viaje | `sede_viaje_km_v` | 1.0246 | **+0.0018** | 0.0006 | +2.9 |
| rotación | `once_previa_cambios_v` | 1.0234 | +0.0007 | 0.0003 | +2.2 |
| altitud | `sede_alt_dif_v` | 1.0229 | +0.0001 | 0.0002 | +0.6 |
| suspensión | `susp_imp_l`, `susp_imp_v` | 1.0224 | -0.0004 | 0.0004 | -0.9 |

Suspensión y altitud no aportan y se quitaron del finalista (quitar las dos: −0.0003, ee 0.0005, frente al de 9).
La rotación aporta poco (2.2 ee, no robusto a 51 comparaciones) pero se dejó por tener respaldo previo en VARIABLES.md.

Coeficientes del finalista (por desviación estándar de la variable; efecto multiplicativo ≈ el coeficiente). Último
reajuste: 10-ene-2025, n = 4,481 partidos; entre corchetes el rango en los 18 reajustes.

| variable (1 desviación) | sobre goles del local | sobre goles de la visita |
|---|---|---|
| viaje del visitante (579 km) | +0.035 [+0.020, +0.035] | -0.027 [-0.029, -0.009] |
| cambios en el once previo del visitante (1.7) | +0.016 [+0.002, +0.016] | -0.019 [-0.019, +0.007] |
| tiros a favor del local, últimos 10 (2.2) | +0.034 [+0.024, +0.047] | -0.026 [-0.039, -0.025] |
| tiros concedidos por el local (2.2) | -0.005 [-0.007, +0.012] | +0.036 [+0.025, +0.040] |
| tiros a favor del visitante (2.2) | +0.012 [-0.001, +0.021] | +0.024 [+0.013, +0.028] |
| tiros concedidos por el visitante (2.2) | +0.043 [+0.027, +0.043] | -0.021 [-0.022, -0.006] |
| constante | +0.002 | +0.006 |

Los signos son los esperados y estables (sólo cambian de signo los tres coeficientes más chicos). La corrección es
pequeña: el factor sobre la lambda del local va de 0.94 a 1.11 (percentiles 5 a 95) y el de la visita de 0.90 a 1.12.

**C6 `ensamble` (6 variantes).** Promedio de lambdas (y de rho) o de matrices de marcadores.

| variante | log-loss | d vs `ajuste` | ee | z | logv marcador |
|---|---|---|---|---|---|
| lambdas: ajuste + dc | 1.0253 | +0.0028 | 0.0007 | +4.3 | -2.8722 |
| **lambdas: ajuste + elo = `ensamble`** | 1.0254 | +0.0029 | 0.0010 | +2.9 | **-2.8665** |
| lambdas: ajuste + dc + elo | 1.0265 | +0.0040 | 0.0010 | +3.9 | -2.8685 |
| probabilidades: ajuste + dc | 1.0254 | +0.0029 | 0.0007 | +4.3 | -2.8724 |
| probabilidades: ajuste + elo | 1.0255 | +0.0029 | 0.0010 | +2.9 | -2.8673 |
| probabilidades: ajuste + dc + elo | 1.0266 | +0.0041 | 0.0010 | +3.9 | -2.8692 |

Promediar `ajuste` con modelos que no llevan la corrección la diluye: todos pierden en 1X2. Promediar lambdas o
probabilidades da lo mismo (diferencia ≤ 0.0001). Las dos primeras empatan en log-loss; se eligió `ajuste` + `elo`
por su mejor marcador exacto y porque junta dos modelos distintos de verdad (`ajuste` + `dc` es sólo media corrección).

## 4. Revisión de fugas

- `dc`, `dc2`, `elo`, `tiros` sólo usan `hist` (el arnés detiene cualquier partido igual o posterior al corte). El
  torneo en curso se deduce del calendario del corte (Apertura desde el 20 de junio), no de la etiqueta `torneo`.
- `ajuste` lee además la tabla de variables por bloque. Como su ganancia es grande, se auditó su grupo principal: se
  recalcularon las 4 variables de tiros de los 2,983 partidos de DESARROLLO usando sólo partidos anteriores al corte
  del bloque. En 2,777 (93.1%) coinciden exactamente con la tabla; en los 206 restantes la tabla usó menos de 10
  partidos (otra definición de la ventana, no información posterior). La ganancia de `ajuste` sobre `dc` restringida a
  los 2,775 evaluables con variables idénticas al recálculo estricto es −0.0071 (ee 0.0014): **no viene de una fuga**.
- El viaje es geografía fija; la rotación sale de alineaciones de partidos previos (no se auditó aparte).
- Sesgo de selección: ridge y grupos de `ajuste` se eligieron mirando DESARROLLO (9 variantes), pero su ventaja (5.4 ee)
  supera con mucho lo que explica elegir entre 51. Las de `dc` (12), `elo` (14) y `ensamble` (6) no: sus diferencias
  internas son ruido.

## 5. Lectura para las siguientes fases

1. Candidato principal para resultado: **`ajuste`**. Respaldo sin tabla de variables: **`dc`**.
2. Para marcador exacto y totales conviene comparar `ajuste` y `ensamble` en la PRUEBA; la ventaja del ensamble en
   logv (2.0 ee) no es firme.
3. Qué esperar en la PRUEBA (≈ 480 partidos), escalando los ee pareados de aquí con la raíz de n: `ajuste` − mercado
   tendría ee ≈ 0.008, así que la brecha de +0.0095 (≈ 1.2 ee) no se distinguirá de cero; `ajuste` − `dc` tendría
   ee ≈ 0.0032, así que una ganancia como la de aquí (−0.0072) se vería a unas 2.2 ee, justo en el límite.
4. Para simular la liguilla, `Ajuste.predecir` acepta las variables como columnas de `partidos` (cruces hipotéticos sin
   id en la tabla); si faltan, la corrección es nula y el pronóstico es el de `dc` (por la constante, lambdas +0.2% y +0.6%).
5. Todos los modelos predicen peor la liguilla; ninguna de las opciones de fase o de peso de liguilla ayudó.

## 6. Estado

**Terminado**
- `modelo/familias/candidatos.py`: `DixonColes` (C1, C2, C4), `Elo` (C3), `Ajuste` (C5), `Ensamble` (C6),
  `finalistas()`, `ESTADO` y `DESCRIPCION`.
- 51 variantes evaluadas en el recorrido completo de DESARROLLO y registradas; ningún acceso a la PRUEBA.
- Predicciones de los seis finalistas en `modelo/pred/` (`dc`, `dc2`, `elo`, `tiros`, `ajuste`, `ensamble`) y sus
  matrices en `modelo/cache/`.
- Tablas de métricas, pareadas, por fase y por año; coeficientes y ablación de `ajuste`; auditoría de fugas de tiros.
- Marcadores `<<N_REGISTRO>>`, `<<TABLA_BASE>>`, `<<TABLA_PAREADA>>` y `<<LECTURA>>` de `ARNES.md` rellenados.

**Faltó o es dudoso**
- `cerebro_original_limpio` no entró en las tablas: su evaluación (otro proceso) iba en el corte 200 de 510 cuando se
  cerró este informe. Al terminar: `python3 -m modelo.arnes comparar cerebro_original_limpio ajuste dc --referencia poisson_simple`.
- La ganancia de `ajuste` se concentra en 2022-2025 (−0.0131 contra −0.0033 antes) y no se explicó por qué.
- No se hizo la ablación sobre el modelo final de 6 variables (se hizo sobre el de 9) ni se auditaron viaje y rotación
  con un recálculo independiente.
- `ajuste` se evaluó sólo con corte por bloque. Con corte por día hay que darle la tabla de variables de ese corte
  (`Ajuste(tabla="partido")` lee `variables.parquet`); no se evaluó.
- `rho` se estima en dos etapas, no con la verosimilitud conjunta.
- El mínimo de `elo` quedó en el borde de la rejilla (K = 8) y el de ridge de `ajuste` también (300): no se extendieron.
- El partido 490116 (Tigres-Chivas, 17-jul-2016) viene rotulado "Clausura 2017" en `partidos.csv`; los modelos de aquí
  no dependen de esa etiqueta, pero los desgloses por torneo sí.
