# Mercados, combinada y contexto por partido

Paquete `produccion/` (se usa desde `ligamx/`, igual que `modelo`). Todo consume **sólo el contrato** del
`Pronosticador` (`equipos`, `partidos(df)`, `malla(n, fase, semilla)`, `fuerzas()`); las cifras de validación de este
documento son de DESARROLLO (Apertura 2016 a Clausura 2025, 2,981 partidos) con las lambdas guardadas de
`poisson_simple` (rho = 0) y se generaron el 2026-11-10. La PRUEBA no se tocó.

| Archivo | Qué hace |
|---|---|
| `__init__.py` | `obtener_pronosticador(corte)`: el campeón (`modelo.pronostico`) si existe `modelo/campeon.json`; si no, el provisional. |
| `pronosticador_provisional.py` | `Pronosticador` con `base.PoissonSimple`; incertidumbre por aproximación normal de la verosimilitud. |
| `mercados.py` | Conjunta exacta por mitades, catálogo de 56 mercados + 5 marcadores exactos, validación (`python3 -m produccion.mercados validar`); modelos de córners y tarjetas (`... conteos`), fuera del catálogo. |
| `combinada.py` | Combinada de 4 picks del mismo partido (3 variantes), combinada de jornada, `paquete_partidos`, validación (`python3 -m produccion.combinada validar`). |
| `contexto.py` | Hechos a la fecha para explicar cada partido (no alteran el pronóstico). |
| `pruebas/test_mercados.py` | 36 pruebas, 11 s: `python3 -m pytest produccion/pruebas/test_mercados.py -q`. |

```python
from produccion import obtener_pronosticador, mercados, combinada
from produccion.contexto import Contexto
from modelo import datos

pron = obtener_pronosticador()                       # 0.8 s con el provisional
pend = datos.pendientes()                            # partidos por jugar (columnas previas al partido)
todo = combinada.paquete_partidos(pron, pend)        # mercados + 3 combinadas por partido + combinada de jornada (JSON)
ctx = Contexto()                                     # hechos a hoy
ficha = ctx.partido(pend.iloc[0])                    # forma, rachas, historial, sede, descanso, viaje, suspendidos
```

## 1. Distribución conjunta por mitades

- `M` = matriz 11×11 de `modelo/arnes.py` (Poisson + corrección Dixon-Coles con `rho`, renormalizada).
- Adelgazamiento de Poisson: cada gol del local cae en el primer tiempo con probabilidad `p1_l` (`p1_v` la visita).
  Dado el marcador final (x, y), los goles del primer tiempo son binomiales, así que
  `J[h1, a1, h2, a2] = M[h1+h2, a1+a2] · Bin(h1; h1+h2, p1_l) · Bin(a1; a1+a2, p1_v)`.
  Es la construcción de `_joint_mitades` del motor previo (Poisson por mitad, tau sobre el marcador FINAL,
  renormalizar) escrita desde `M`: la marginal de tiempo completo de `J` **es** `M` (las pruebas exigen menos de
  1e-12; el motor previo perdía hasta 3.4e-4 por truncar cada mitad en 7 goles).
- Sólo 4,356 de las 14,641 celdas tienen masa (h1 ≤ x ≤ 10, a1 ≤ y ≤ 10). Todo el módulo trabaja con el vector `q`
  de esas celdas (`mercados.celdas(M, p1_l, p1_v)`, vectorizado para muchos partidos); `mercados.tensor(q)` da el
  tensor `J[h1, a1, h2, a2]` y `mercados.conjunta_mitades(lam_l, lam_v, rho, p1_l, p1_v)` lo arma directo.
- **Proporción de goles del primer tiempo**: `mercados.proporcion_1t(corte)` = goles del periodo 1 entre goles de los
  periodos 1 y 2 de `goles.csv`, por local y por visita, en los partidos con `fecha_utc` en [corte − 6 años, corte)
  y goles con minuto completos. Al 2026-11-10: **p1_l = 0.4562, p1_v = 0.4514** (2,031 partidos). En el recorrido de
  desarrollo osciló entre 0.439 y 0.459 (local) y entre 0.429 y 0.454 (visita); media 0.4487 y 0.4453.
- Supuesto que queda: los goles de una mitad no dependen de lo ocurrido en la otra (salvo por la corrección sobre el
  marcador final).

## 2. Catálogo (`mercados.catalogo()`, `mercados.mercados_partido(...)`)

Cada mercado es una máscara booleana sobre las celdas, con `clave`, `etiqueta` (con los nombres de los equipos),
`tipo` (el nombre del mercado), `familia` (para la regla de la combinada) y `prob`. 56 mercados fijos (52 binarios
"combinables" y 4 con devolución) más los 5 marcadores exactos más probables de cada partido.

| Familia (combinada) | Tipo | Claves |
|---|---|---|
| `resultado` | Resultado | `1`, `X`, `2` |
| | Doble oportunidad | `1X`, `X2`, `12` |
| | Sin empate (con devolución) | `SE_1`, `SE_2` |
| | Hándicap | `H_L-1.5`, `H_V+1.5`, `H_V-1.5`, `H_L+1.5`; asiático con devolución `HA_L-1`, `HA_V+1` |
| `total` | Total de goles | `O15`, `U15`, `O25`, `U25`, `O35`, `U35` |
| `ambos` | Ambos anotan | `AA_SI`, `AA_NO` |
| `goles_local` | Total del local; portería en cero de la visita | `L_ANOTA`, `L_2MAS`, `L_U15`; `PC_V` |
| `goles_visita` | Total de la visita; portería en cero del local | `V_ANOTA`, `V_2MAS`, `V_U15`; `PC_L` |
| `descanso` | Resultado y doble oportunidad al descanso | `D_1`, `D_X`, `D_2`; `D_1X`, `D_X2`, `D_12` |
| `goles_1t` | Gol en el 1T; más/menos 1.5 en el 1T | `G1T_SI`, `G1T_NO`; `O15_1T`, `U15_1T` |
| `goles_2t` | Gol en el 2T | `G2T_SI`, `G2T_NO` |
| `mitades` | Mitad con más goles | `MAS_1T`, `MAS_2T`, `MIT_IGUAL` |
| `gana_mitad` | Gana alguna mitad | `GM_L`, `GM_V` |
| `descanso_final` | Descanso/final | `DF_1/1` … `DF_2/2` (9) |
| `marcador` | Marcador exacto (5 más probables) | `ME_x-y` |

Decisiones:
- **Hándicap.** "Local −1" y "visita +1" con devolución (asiático) no son sucesos binarios: se listan como
  `HA_L-1` / `HA_V+1` con `prob` = P(gana | no hay devolución) y `p_nula`, y no entran a la combinada. Sus versiones
  binarias son `H_L-1.5` (gana por 2 o más) y `H_V+1.5` (gana, empata o pierde por uno), con el espejo para cuando
  el favorito es la visita. Lo mismo "sin empate": `SE_1` = P(gana local | no empatan).
- **Familia** agrupa lo que habla de lo mismo (p. ej. resultado, doble oportunidad y hándicap son una sola familia;
  la portería en cero del local va con los goles de la visita porque es el complemento de "la visita anota").
- Los marcadores exactos se agregan por partido (`familia = "marcador"`); por su probabilidad (5 a 14%) no entran a
  la combinada.

## 3. Validación de los mercados (desarrollo, 2,981 partidos, `poisson_simple`)

`dif` = observado − pronosticado, `z` con error estándar por bootstrap de bloques; `pendiente` de la recalibración
logística (1 = calibrado; < 1 = las probabilidades varían de un partido a otro más de lo que deberían); `d_ll` =
log-loss del modelo menos el de pronosticar siempre la frecuencia observada del propio periodo (referencia
favorecida; negativo = el modelo gana).

| Mercado | Pronosticado | Observado | dif | z | Pendiente | d_ll (ee) |
|---|---:|---:|---:|---:|---:|---:|
| Gol en el 1T (`G1T_SI`) | 0.689 | 0.692 | +0.003 | 0.3 | 0.42 | +0.0008 (0.0018) |
| Más de 1.5 en el 1T (`O15_1T`) | 0.330 | 0.345 | +0.015 | 1.7 | 0.45 | +0.0012 (0.0022) |
| Gol en el 2T (`G2T_SI`) | 0.763 | 0.783 | +0.019 | 2.4 | 0.62 | −0.0001 (0.0021) |
| Local gana al descanso (`D_1`) | 0.340 | 0.338 | −0.002 | −0.3 | 0.75 | −0.0073 (0.0032) |
| Empate al descanso (`D_X`) | 0.420 | 0.434 | +0.014 | 1.5 | 0.53 | +0.0003 (0.0014) |
| Visita gana al descanso (`D_2`) | 0.240 | 0.228 | −0.012 | −1.5 | 0.82 | −0.0073 (0.0027) |
| Más de 1.5 (`O15`) | 0.733 | 0.749 | +0.016 | 1.9 | 0.58 | −0.0010 (0.0027) |
| Más de 2.5 (`O25`) | 0.488 | 0.502 | +0.014 | 1.6 | 0.65 | −0.0040 (0.0031) |
| Más de 3.5 (`O35`) | 0.274 | 0.279 | +0.005 | 0.7 | 0.48 | +0.0006 (0.0031) |
| Ambos anotan (`AA_SI`) | 0.509 | 0.543 | **+0.034** | **3.6** | 0.34 | +0.0050 (0.0025) |
| Local anota (`L_ANOTA`) | 0.762 | 0.784 | +0.021 | 3.0 | 0.82 | −0.0091 (0.0034) |
| Visita anota (`V_ANOTA`) | 0.671 | 0.686 | +0.015 | 1.8 | 0.76 | −0.0078 (0.0033) |
| Local gana por 2+ (`H_L-1.5`) | 0.232 | 0.218 | −0.013 | −1.7 | 0.95 | −0.0231 (0.0042) |
| Local gana alguna mitad (`GM_L`) | 0.577 | 0.589 | +0.012 | 1.3 | 0.87 | −0.0182 (0.0042) |
| Más goles en el 2T (`MAS_2T`) | 0.434 | 0.441 | +0.007 | 0.8 | 0.73 | −0.0001 (0.0006) |
| Descanso/final local/local (`DF_1/1`) | 0.275 | 0.266 | −0.009 | −1.1 | 0.92 | −0.0157 (0.0038) |
| Descanso/final empate/empate (`DF_X/X`) | 0.156 | 0.165 | +0.009 | 1.4 | 0.69 | −0.0008 (0.0016) |

1X2 al descanso como pronóstico de tres clases: log-loss **1.0560** contra 1.0662 de la constante (−0.0102, ee 0.0036).

Pronosticado contra observado por deciles (n ≈ 298 por decil; en el 1X2 al descanso se juntan las tres clases, n ≈ 894):

| Decil | Gol 1T pron. | obs. | 1X2 descanso pron. | obs. | Más de 2.5 pron. | obs. | Ambos anotan pron. | obs. |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.607 | 0.642 | 0.164 | 0.179 | 0.349 | 0.385 | 0.398 | 0.528 |
| 2 | 0.642 | 0.715 | 0.217 | 0.203 | 0.403 | 0.473 | 0.443 | 0.513 |
| 3 | 0.658 | 0.611 | 0.254 | 0.263 | 0.430 | 0.453 | 0.464 | 0.544 |
| 4 | 0.671 | 0.678 | 0.289 | 0.291 | 0.453 | 0.473 | 0.482 | 0.520 |
| 5 | 0.684 | 0.708 | 0.326 | 0.299 | 0.475 | 0.477 | 0.499 | 0.490 |
| 6 | 0.696 | 0.681 | 0.364 | 0.370 | 0.497 | 0.523 | 0.517 | 0.550 |
| 7 | 0.707 | 0.695 | 0.394 | 0.371 | 0.518 | 0.537 | 0.533 | 0.560 |
| 8 | 0.721 | 0.765 | 0.415 | 0.455 | 0.543 | 0.544 | 0.552 | 0.570 |
| 9 | 0.737 | 0.695 | 0.437 | 0.438 | 0.574 | 0.523 | 0.576 | 0.537 |
| 10 | 0.769 | 0.728 | 0.474 | 0.464 | 0.635 | 0.631 | 0.622 | 0.614 |

Lectura:
1. **El reparto por mitades está bien centrado**: P(gol en el 1T) 0.689 contra 0.692 observado; el 1X2 al descanso
   queda calibrado decil por decil y le gana a la constante por 0.010 (2.8 ee).
2. **Lo que depende de quién es mejor está bien** (resultado, hándicap, quién gana al descanso o alguna mitad,
   descanso/final): pendientes de 0.75 a 1.04 y ganancias de 0.007 a 0.033 de log-loss.
3. **Lo que depende de CUÁNTOS goles habrá casi no discrimina** con estas lambdas: pendientes de 0.34 a 0.65 y
   log-loss igual al de la constante en gol en el 1T, más de 1.5 en el 1T, gol en el 2T, más de 3.5 y mitad con más
   goles. Las lambdas de `poisson_simple` exageran las diferencias de goles totales entre partidos. Ensayo
   exploratorio (dentro de muestra, sin ajustar nada más): encoger el total esperado a la mitad de su distancia a la
   media, conservando el reparto local/visita, mejora el log-loss de ambos anotan en 0.0039 (ee 0.0011) y empeora el
   de 1X2 en 0.0010 (ee 0.0005). Es tarea del modelo campeón, no del motor de mercados.
4. **Ambos anotan está subestimado 3.4 puntos** (z = 3.6) y pierde contra la constante. Causa medida: Poisson
   pronostica demasiados ceros (local sin gol 23.8% pronosticado contra 21.6% observado; visita 32.9% contra 31.4%),
   aunque la media de goles está bien (1.495 pronosticado contra 1.510 del local; 1.144 contra 1.154 de la visita).
   Con el campeón hay que repetir `python3 -m produccion.mercados validar <nombre>`; mientras tanto, los picks de
   "ambos anotan" y de "anota / no anota" llevan ese sesgo.

## 4. Combinada del partido (`combinada.combinada_partido`, `combinadas_partido`)

Cuatro picks del mismo partido con su probabilidad conjunta **exacta**: suma de `q` sobre la intersección de las
cuatro máscaras (nunca el producto de las marginales). Reglas:

1. Los cuatro de familias distintas (tabla de la sección 2).
2. Ningún par se implica ni se excluye: se comprueba con las máscaras (una contiene a la otra, o no comparten
   celdas), que equivale a P(A y B) = P(A), = P(B) o = 0.
3. Ningún par casi redundante: P(A|B) ≤ 0.97 y P(B|A) ≤ 0.97.
4. (Añadida.) Ningún pick queda casi decidido por los otros tres: P(pick | los otros tres) ≤ 0.97. Cubre las
   implicaciones de conjunto que la regla por pares no ve; p. ej. "local o empate" + "más de 1.5" implican "el
   local anota".
5. La probabilidad marginal de cada pick cae en la banda de la variante.

| Variante | Banda | Qué maximiza |
|---|---|---|
| `segura` | 0.55 – 0.85 | la probabilidad conjunta |
| `equilibrada` | 0.45 – 0.75 | conjunta × momio ingenuo acotado: `P4 · min(1/(p1·p2·p3·p4), 8)`. El momio ingenuo es lo que pagaría el producto de los momios justos de cada pick; premia picks menos obvios y, por el tope, no persigue combinaciones improbables. |
| `atrevida` | 0.30 – 0.60 | la probabilidad conjunta |

Búsqueda exhaustiva vectorizada: se arman todos los pares válidos, sus máscaras y la matriz par × par de
probabilidades de cuatro (cada cuarteta aparece una vez); una prueba la compara contra el recorrido uno por uno de
todas las cuartetas. **0.02 s por partido las tres variantes** (en los 9 partidos de la Jornada 17: 14 a 20 mercados
en banda y 266 a 1,175 cuartetas válidas por variante). Si la banda no alcanza para cuatro picks válidos se ensancha 0.05 por lado hasta tres veces y se marca
`banda_ampliada` (pasó en 2 de 8,943 combinadas de desarrollo).

Salida: `picks` (clave, etiqueta, familia, tipo, prob), `prob_conjunta`, `momio_justo` (1/conjunta), `prob_ingenua`
(producto de marginales), `correlacion` (conjunta / ingenua), `banda`, `banda_ampliada`, `n_candidatos`,
`n_evaluadas`.

**¿Se cumple lo que se anuncia?** (`python3 -m produccion.combinada validar`, 68 s): en cada partido de desarrollo
se armaron las tres combinadas con lo conocido antes del corte y se contó si se cumplieron los cuatro picks.

| Variante | n | Conjunta anunciada | Frecuencia observada | dif (ee) | Producto ingenuo | Momio justo medio | Log-loss conjunta / ingenua |
|---|---:|---:|---:|---:|---:|---:|---:|
| segura | 2,981 | 0.492 | 0.488 | −0.004 (0.010) | 0.358 | 2.05 | 0.691 / 0.729 |
| equilibrada | 2,981 | 0.332 | 0.342 | +0.010 (0.009) | 0.130 | 3.05 | 0.641 / 0.787 |
| atrevida | 2,981 | 0.195 | 0.206 | +0.011 (0.008) | 0.057 | 5.34 | 0.509 / 0.645 |

La conjunta exacta queda calibrada (diferencias de 0.4 a 1.4 ee) pese a elegirse como la mejor de cientos de
cuartetas; el producto de marginales habría anunciado 1.4, 2.6 y 3.6 veces menos de lo que ocurre. Por quintiles de
la probabilidad anunciada, la diferencia mayor es de +0.034 (z = 2.4) en el quintil más bajo de la atrevida.
Advertencia: es la calibración de la probabilidad propia; no dice nada del margen que cobre una casa en estas
combinadas.

Ejemplo (Chivas–Cruz Azul, Jornada 17, provisional, lambdas 1.46–1.22):

| Variante | Picks (probabilidad) | Conjunta | Momio justo | Conjunta / ingenua |
|---|---|---:|---:|---:|
| segura | Hay gol en el 2T (0.77), Chivas anota (0.77), más de 1.5 (0.75), Chivas o empate al descanso (0.74) | 0.451 | 2.22 | 1.38 |
| equilibrada | Cruz Azul o empate al descanso (0.67), menos de 1.5 en el 1T (0.66), Chivas anota menos de 1.5 (0.57), menos de 2.5 (0.50) | 0.314 | 3.18 | 2.49 |
| atrevida | No hay empate al descanso (0.58), Chivas gana alguna mitad (0.56), más de 2.5 (0.50), Chivas anota 2 o más (0.43) | 0.237 | 4.22 | 3.37 |

Picks más usados en desarrollo: segura = gol en el 2T, local o empate al descanso, más de 1.5, local anota;
equilibrada = menos de 1.5 en el 1T, menos de 2.5, al menos uno no anota; atrevida = más de 2.5, no hay empate al
descanso, local anota 2 o más, gana alguna mitad.

## 5. Combinada de jornada (`combinada.combinada_jornada`)

Un pick por partido: el más probable dentro de 0.58–0.85 (banda del proyecto anterior), sin repetir el mismo tipo de
mercado más de 3 veces; entre partidos la conjunta es el producto. Variantes: `equilibrada` (los n primeros que
maximizan n × P(todos), criterio del proyecto anterior), `segura` (se agregan picks mientras P(todos) ≥ 0.45) y
`atrevida` (≥ 0.18). Para la Jornada 17 con el provisional: segura 4 picks (0.504), equilibrada 5 (0.409), atrevida 8
(0.199). No se validó aparte: hereda la calibración de los mercados sueltos (sección 3).

## 6. Pronosticador provisional

`base.PoissonSimple` ajustado con todo lo jugado antes del corte (0.8 s), `rho = 0`. Muestras de `malla(n)`:
theta ~ N(theta_hat, H⁻¹), con H la hessiana de la verosimilitud ponderada y penalizada del propio ajuste (peso
efectivo al 10-nov-2026: 495 partidos). Es la posterior de una verosimilitud descontada: más ancha que la varianza
muestral del estimador. `fuerzas()` da ataque, defensa, goles a favor y en contra frente a un rival promedio en
cancha neutral, `rating` y sus errores estándar (el del rating ronda 0.20 goles; el líder, Toluca, tiene +0.73).
`partidos(df)` agrega `lam_base` para que `lam = lam_base × producto de efectos` de `explica`. Límites: ventaja de
local común a todos y `fase="liguilla"` no cambia nada.

## 7. Contexto (`contexto.Contexto(fecha)`)

Sólo usa partidos jugados con `fecha_utc < fecha` (y la agenda posterior: fecha, equipos y sede). Una prueba
compara las salidas con y sin los resultados futuros.

- `partido(fila)`: `equipo_local` / `equipo_visitante` (posición, puntos, balance total, de local y de visita en
  el torneo, forma de los últimos 5 con rival y marcador, rachas vigentes), `historial` (total, últimos 10, en esa
  sede, liguilla, finales y series con su ganador), `sede` (nombre, ciudad, altitud, aforo y superficie de
  `web/medios.json`, emparejado por coordenadas; balance del local ahí en 3 años), `descanso_*` (días desde su
  partido anterior de Liga MX, jugado o agendado), `viaje_visitante_km` (línea recta desde su sede habitual),
  `suspendidos_*` y `lesionados_*`.
- `suspendidos(equipo, fecha)`: expulsados en su último partido y quienes llegaron ahí a un múltiplo de 5 amarillas
  en el torneo (cuenta aparte en liguilla; la amarilla de una doble amarilla no acumula), más `apercibidos` (a una
  amarilla). Si el equipo tiene otro partido agendado antes, devuelve `conocido = False`. No ve castigos de más de un
  partido ni apelaciones.
- `lesionados(equipo)`: sólo si existe `config/actualidad.json` (hoy no existe: devuelve `None`). Formatos:
  `{"lesionados": [{"equipo", "jugador", ...}]}` o `{"equipos": {equipo: {"lesionados": [...]}}}`.
- `tabla()`: puntos, diferencia de goles, goles a favor y nombre; no aplica los criterios posteriores del
  reglamento ni la resta por regla de menores.
- `dominios_liguilla()`: pares con más eliminatorias (cuartos, semifinal, final) desde 2001. Al 10-nov-2026:
  Monterrey–Tigres 9 series (5–4, una final); **América–Cruz Azul 8 series, 8–0 para América, 3 finales (3–0)**;
  América–Monterrey 8 (4–4, 2 finales para América); América–Toluca 8 (3–5); América–Pumas 8 (5–3). El ganador de
  cada serie se deduce por regla (global; en finales, tiempos extra y penales; gol de visitante del Apertura 2012 al
  Clausura 2021; después la tabla). De 395 series sólo una no se decide con los datos (final del Clausura 2009:
  ESPN no trae los tiempos extra) y se fija a mano: Pumas.
- `balance_estadios()`: por equipo, su sede habitual y su balance como local ahí, histórico y de 3 años.

## 8. Córners y tarjetas: probados, NO pasan el umbral, fuera del catálogo

`mercados.ModeloConteo` (binomial negativa del total: tasas a favor y en contra por equipo en sus últimos 34
partidos, encogidas con 10 de liga; en tarjetas, además, la media del árbitro designado, 30 partidos encogidos con
10; dispersión por momentos sobre 612 partidos de liga). Una sola configuración por mercado, fijada de antemano.
Walk-forward por bloque en los 2,729 partidos de desarrollo con estadísticas (`python3 -m produccion.mercados
conteos`, 3 s), contra la frecuencia de liga de los 612 partidos previos:

| Mercado | Línea | Media observada | P(más) pron. / obs. | Log-loss modelo / liga | d_ll (ee) | Pendiente |
|---|---:|---:|---:|---:|---:|---:|
| Córners totales | 9.5 | 9.91 | 0.517 / 0.517 | 0.6955 / 0.6930 | +0.0025 (0.0036) | 0.41 |
| Tarjetas totales (amarillas + rojas) | 4.5 | 4.51 | 0.474 / 0.478 | 0.6915 / 0.6926 | −0.0011 (0.0044) | 0.50 |

Ninguno le gana a la frecuencia de liga por más de 2 ee (el de córners ni siquiera en el signo), así que **no se
agregan al catálogo** y la página no debe ofrecer picks de córners ni de tarjetas con estos modelos. Están bien
centrados pero sobreconfiados (los deciles extremos fallan por 8 a 13 puntos): las tasas por equipo de 34 partidos
son casi todo ruido. El árbitro sólo estaba designado en 43% de los partidos calificados. La clase y la validación
quedan en `mercados.py` para repetir la medición; no se probaron más variantes.

## 9. Pendientes y dudas

- Repetir las dos validaciones con el modelo campeón (su `rho` y sus lambdas cambian la calibración de totales y de
  ambos anotan).
- El sesgo de ambos anotan y la poca discriminación de los totales (sección 3) son del modelo de goles.
- La regla de suspensiones no se contrastó aquí contra las alineaciones siguientes (`modelo/VARIABLES.md` documenta
  esa comprobación para la misma regla).
- El tope 8 de la variante equilibrada y la regla 4 son decisiones de diseño, no parámetros ajustados con datos.
- Córners y tarjetas: un encogimiento mayor (la pendiente de 0.4 a 0.5 lo sugiere) sería una segunda variante; habría
  que evaluarla contando el número de intentos.

## Estado (2026-11-10)

- **Terminado y probado** (36 pruebas): conjunta exacta por mitades, catálogo, validación de mercados en desarrollo,
  combinada del partido (3 variantes) con su validación, combinada de jornada, `paquete_partidos`, contexto,
  pronosticador provisional y `obtener_pronosticador`.
- **Hecho y descartado por los datos**: córners y tarjetas (sección 8).
- **Falta**: repetir las validaciones con el modelo campeón cuando exista `modelo/campeon.json`; `config/actualidad.json`
  (lesionados) no existe; la combinada de jornada no tiene validación propia.
