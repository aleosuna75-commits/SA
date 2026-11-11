# CONTRATO de `salidas/actual.json` (versión 1.0)

Lo escribe un solo comando, que rehace todo con lo jugado hasta el corte:

    cd /home/user/SA/ligamx && python3 -m produccion.exportar [--corte AAAA-MM-DDTHH:MM] [--sin-sello] [--salida RUTA]

- Sin `--corte` (uso normal, después de cada partido): escribe `salidas/actual.json`, una copia
  `salidas/historial/actual_<corte UTC>.json`, agrega sellos a `salidas/sellos.jsonl` y actualiza
  `salidas/desempeno.json`.
- Con `--corte` es una corrida RETROSPECTIVA: no sella, no pisa `actual.json` (escribe
  `salidas/historial/retro_<corte>.json`) y `meta.retrospectivo` es `true`.
- Si el documento no pasa `exportar.validar` NO se escribe y el comando termina con código 1.
- El archivo se escribe a un temporal y se renombra: la página nunca lee un JSON a medias.

Convenciones: UTF-8, JSON compacto. Toda probabilidad va en [0, 1] con 4 decimales (también lambdas,
momios y errores estándar; `lat`/`lon` sin redondear). `null` = dato que no existe (nunca se inventa).
Nombres de equipo como en `datos/partidos.csv` (son las llaves de `escudos` en `web/medios.json`);
`estadio.slug` y `sede` son los `slug` de `estadios` en `web/medios.json`. Fechas `*_utc` en ISO 8601
con zona; `fecha_local`/`hora_local` en hora de la Ciudad de México. Resultado 1X2: `"L"` local, `"E"`
empate, `"V"` visitante. Marcadores a 90 minutos. Peso al 2026-11-10 04:12: 222 KB (tope 600 KB).

Campos de primer nivel: `meta`, `tabla`, `pendientes`, `combinada_jornada`, `ultimos_resultados`,
`proyeccion`, `liguilla`, `fuerzas`, `estadios`, `dominios`, `desempeno`, `calibracion_series`, `avisos`,
`vivo` (último documento en vivo incrustado; su contrato está al final: «Documento en vivo»).

## meta

| campo | significado |
|---|---|
| `version_contrato` | versión de este contrato |
| `generado_utc` | cuándo se escribió el archivo |
| `corte_utc`, `corte_local` | instante hasta el que se usó información (todo lo jugado antes) |
| `retrospectivo` | `true` si se pidió `--corte` |
| `torneo` | torneo en curso |
| `modelo.origen` | `"campeon"` (existe `modelo/campeon.json`) o `"provisional"` |
| `modelo.nombre`, `modelo.descripcion` | nombre y descripción llana del modelo |
| `modelo.metricas` | métricas de validación (las de `campeon.json`: `desarrollo_bloque` y `prueba_dia`; con el provisional, las líneas base de `modelo/ARNES.md`) |
| `modelo.contra_referencias` | diferencias pareadas del campeón contra otros modelos y contra el mercado (de `campeon.json`; negativo en `d_logloss` = el campeón es mejor) |
| `modelo.seleccion`, `modelo.avisos`, `modelo.incertidumbre_parametros` | cuándo y por qué se eligió, sus avisos (se repiten en `avisos`) y cómo se muestrean sus parámetros. Sólo con campeón |
| `modelo.provisional` | `true` mientras no haya campeón: la página debe decirlo |
| `partidos_en_la_historia` | partidos jugados antes del corte |
| `sellos_nuevos` | sellos agregados en esta corrida |
| `proporcion_goles_1t` | proporción de los goles que cae en el primer tiempo (local y visitante), usada en los mercados de mitades |
| `segundos` | lo que tardó la corrida |

```json
{
 "version_contrato": "1.0",
 "generado_utc": "2026-11-10T10:12:26.358927+00:00",
 "corte_utc": "2026-11-10T10:12:10.976358+00:00",
 "corte_local": "2026-11-10 04:12",
 "retrospectivo": false,
 "torneo": "Apertura 2026",
 "modelo": {
  "origen": "campeon",
  "nombre": "ajuste",
  "descripcion": "Parte de los goles esperados de dc y los corrige un poco con tres datos previos …",
  "metricas": {
   "desarrollo_bloque": {
    "n": 2981,
    "logloss": 1.0225,
    "ee_logloss": 0.0071,
    "rps": 0.2093,
    "brier": 0.6134,
    "logv_marcador": -2.8707,
    "acierto": 0.488,
    "marcadores_exactos": 387,
    "pendiente_calibracion": 1.01,
    "error_calibracion": 0.011
   },
   "prueba_dia": {
    "n": 480,
    "logloss": 1.0272,
    "ee_logloss": 0.0212,
    "rps": 0.2126,
    "brier": 0.6156,
    "logv_marcador": -3.0057,
    "acierto": 0.49,
    "marcadores_exactos": 58,
    "pendiente_calibracion": 0.78,
    "error_calibracion": 0.035
   }
  },
  "provisional": false,
  "contra_referencias": {
   "desarrollo": {
    "dc": {
     "n": 2981,
     "d_logloss": -0.0072,
     "ee": 0.0013,
     "ic95": [
      -0.0098,
      -0.0047
     ],
     "z": -5.4,
     "d_logv_marcador": 0.0058,
     "ee_logv_marcador": 0.0018
    },
    "…": "…"
   },
   "prueba": "… igual"
  },
  "seleccion": {
   "fecha_seleccion": "2026-11-10",
   "regla": "Pre-registrada en RESULTADOS.md §1: gana el candidato de menor log-loss 1X2 en DESARROLLO …",
   "motivo": "Mejor log-loss 1X2 en DESARROLLO (1.0225; le gana a dc por 0.0072 con ee 0.0013 y a ensamb…"
  },
  "avisos": [
   "En la PRUEBA ajuste (1.0272) no mejoró a dc (1.0264) ni a poisson_simple (1.0276): diferencias de menos de 0.3 ee. La ganancia de DESARROLLO (-0.0072) no se confirmó ni se desmintió (IC 95% de ajuste - dc en PRUEBA: [-0.0079, +0.0099]).",
   "…"
  ],
  "incertidumbre_parametros": "Aproximación normal de Laplace: N(estimación, H^-1) con la hessiana de la verosimilitud de Poisson ponderada y penalizada del Dixon-Coles base y la de la regresión de corrección; rho fijo. Ver RESULTADOS.md §7."
 },
 "partidos_en_la_historia": 8684,
 "sellos_nuevos": 0,
 "proporcion_goles_1t": {
  "local": 0.4562,
  "visitante": 0.4514
 },
 "segundos": 16.0
}
```

## tabla (18 filas, del 1 al 18)

Tabla general real al corte, ordenada con los criterios oficiales. `PJ, G, E, P, GF, GC, DG, PTS` y
los desgloses `*_L` (de local) y `*_V` (de visita). Columnas de desempate: `goles_visita_8` (goles de
visitante en las primeras 8 visitas), `fair_play` (puntos de Fair Play; menos es mejor) y `cociente`
(puntos entre partidos de fase regular desde el Apertura 2024). `zona`: `"liguilla"` (lugares 1 a 8) o
`"fuera"`. `forma`: últimos 5 partidos, del más reciente al más antiguo (`G`/`E`/`P`); `forma_detalle`
los describe.

```json
{
 "pos": 1,
 "equipo": "Cruz Azul",
 "PJ": 16,
 "G": 10,
 "E": 2,
 "P": 4,
 "GF": 37,
 "GC": 26,
 "DG": 11,
 "PTS": 32,
 "PJ_L": 8,
 "PTS_L": 16,
 "GF_L": 19,
 "GC_L": 13,
 "PJ_V": 8,
 "PTS_V": 16,
 "GF_V": 18,
 "GC_V": 13,
 "goles_visita_8": 18,
 "fair_play": 36,
 "cociente": 2.0833,
 "zona": "liguilla",
 "forma": [
  "G",
  "G",
  "G",
  "G",
  "G"
 ],
 "forma_detalle": [
  {
   "fecha": "2026-11-07",
   "torneo": "Apertura 2026",
   "fase": "regular",
   "rival": "Tigres",
   "condicion": "visita",
   "resultado": "G",
   "gf": 3,
   "gc": 2,
   "marcador": "3-2"
  },
  "…"
 ]
}
```

## pendientes (partidos por jugar, en orden cronológico)

Los primeros 20 llevan ficha completa (`detalle: true`); los demás sólo los campos básicos (hasta
`marcador`), para que el archivo no crezca sin límite al principio del torneo.

| campo | significado |
|---|---|
| `id` | id de ESPN (el de `partidos.csv`) |
| `detalle` | `true` si trae la ficha completa |
| `fecha_utc`, `fecha_local`, `hora_local`, `dia_semana` | inicio del partido |
| `fase`, `pierna`, `etiqueta` | `regular`/`cuartos`/`semifinal`/`final`; pierna 1 o 2; texto listo para mostrar (`"Jornada 17"`, `"Jornada 7 (reprogramado)"`, `"Cuartos de final, ida"`). La jornada se deduce de las fechas (partidos.csv no la trae) |
| `local`, `visitante` | equipos |
| `lam_l`, `lam_v`, `rho` | goles esperados del local y del visitante y correlación de Dixon-Coles |
| `p_local`, `p_empate`, `p_visitante` | 1X2 (suman 1) |
| `pick` | resultado más probable: `resultado` (`L`/`E`/`V`), `equipo` (nombre o `"Empate"`) y `prob` |
| `marcador`, `top5` | marcador más probable y los cinco más probables (`gl`, `gv`, `prob`) |
| `estadio` | `nombre`, `ciudad`, `slug` (de `web/medios.json`) y `altitud_m` |
| `matriz`, `matriz_resto` | `matriz[x][y]` = P(local x goles, visitante y goles) para 0 a 6; `matriz_resto` = masa fuera de ese cuadro |
| `mercados` | 29 mercados principales: `clave`, `etiqueta`, `familia`, `prob`, `momio_justo` (1/prob) y `p_nula` (probabilidad de devolución; en esos `prob` es P(gana \| no hay devolución)). El catálogo completo (56) sale de `produccion.combinada.paquete_partidos` |
| `combinadas` | `segura`, `equilibrada`, `atrevida`: cuatro picks del MISMO partido con `prob_conjunta` (exacta, del modelo de marcador y mitades), `momio_justo`, `prob_ingenua` (producto de las marginales; sólo para contrastar) y `correlacion` (conjunta / ingenua). Puede ser `null` si no hay cuatro picks compatibles |
| `explica` | factores del modelo: `factor`, `detalle`, `efecto_l` y `efecto_v` (multiplicador sobre la lambda; 1 = neutro). Empieza por ataque, defensa y ventaja de local |
| `contexto` | ficha descriptiva (NO entra al pronóstico salvo lo que diga `explica`): `equipo_local` / `equipo_visitante` (posición, balances, forma, rachas), `historial` (total, últimos, en la sede, liguilla, finales, series), `sede` (con `balance_local_3_anios`), `descanso_*`, `viaje_visitante_km`, `suspendidos_*` (suspendidos y apercibidos), `lesionados_*` (`null` si no hay `config/actualidad.json`) |
| `momios` | momios de ESPN si existen (`null` si no): `proveedor`, `ml_local`, `ml_empate`, `ml_visitante` (decimales), `margen`, probabilidades implícitas sin margen (`p_*`, reparto proporcional), `total_linea`, `over`, `under` |

```json
{
 "id": 401876988,
 "detalle": true,
 "fecha_utc": "2026-11-14T23:00:00+00:00",
 "fecha_local": "2026-11-14",
 "hora_local": "17:00",
 "dia_semana": "sábado",
 "torneo": "Apertura 2026",
 "fase": "regular",
 "pierna": null,
 "etiqueta": "Jornada 7 (reprogramado)",
 "local": "Querétaro",
 "visitante": "Monterrey",
 "lam_l": 1.1757,
 "lam_v": 1.6404,
 "rho": -0.0574,
 "p_local": 0.267,
 "p_empate": 0.2576,
 "p_visitante": 0.4754,
 "pick": {
  "resultado": "V",
  "equipo": "Monterrey",
  "prob": 0.4754
 },
 "marcador": {
  "gl": 1,
  "gv": 1,
  "prob": 0.122
 },
 "estadio": {
  "nombre": "Estadio La Corregidora",
  "ciudad": "Querétaro",
  "slug": "corregidora",
  "altitud_m": 1870
 },
 "top5": [
  {
   "gl": 1,
   "gv": 1,
   "prob": 0.122
  },
  {
   "gl": 1,
   "gv": 2,
   "prob": 0.0947
  },
  "…"
 ],
 "matriz": [
  [
   0.0665,
   0.0915,
   0.0805,
   0.044,
   0.0181,
   0.0059,
   0.0016
  ],
  "… 7 filas (goles del local 0 a 6) x 7 columnas (goles del visitante 0 a 6)"
 ],
 "matriz_resto": 0.0018,
 "mercados": [
  {
   "clave": "1",
   "etiqueta": "Gana Querétaro",
   "familia": "resultado",
   "prob": 0.267,
   "momio_justo": 3.7453,
   "p_nula": 0.0
  },
  {
   "clave": "X",
   "etiqueta": "Empate",
   "familia": "resultado",
   "prob": 0.2576,
   "momio_justo": 3.8818,
   "p_nula": 0.0
  },
  "…"
 ],
 "combinadas": {
  "segura": {
   "prob_conjunta": 0.4817,
   "momio_justo": 2.0759,
   "prob_ingenua": 0.3649,
   "correlacion": 1.3201,
   "picks": [
    {
     "clave": "V_ANOTA",
     "etiqueta": "Monterrey anota",
     "familia": "goles_visita",
     "prob": 0.8061
    },
    {
     "clave": "G2T_SI",
     "etiqueta": "Hay gol en el segundo tiempo",
     "familia": "goles_2t",
     "prob": 0.7835
    },
    "…"
   ]
  },
  "equilibrada": "… igual",
  "atrevida": "… igual"
 },
 "explica": [
  {
   "factor": "media de la liga",
   "efecto_l": 1.2223,
   "efecto_v": 1.2223,
   "detalle": "un equipo promedio le anota 1.22 goles a otro promedio sin ventaja de local"
  },
  {
   "factor": "ataque de Querétaro",
   "efecto_l": 0.7884,
   "efecto_v": 1.0,
   "detalle": "Querétaro anota -21% respecto del promedio"
  },
  "…"
 ],
 "contexto": {
  "equipo_local": {
   "equipo": "Querétaro",
   "torneo": "Apertura 2026",
   "posicion": 12,
   "puntos": 20,
   "balance": {
    "pj": 15,
    "g": 6,
    "e": 2,
    "p": 7,
    "gf": 18,
    "gc": 23,
    "pct_puntos": 0.4444
   },
   "balance_local": {
    "pj": 7,
    "g": 2,
    "e": 1,
    "p": 4,
    "gf": 8,
    "gc": 11,
    "pct_puntos": 0.3333
   },
   "balance_visita": {
    "pj": 8,
    "g": 4,
    "e": 1,
    "p": 3,
    "gf": 10,
    "gc": 12,
    "pct_puntos": 0.5417
   },
   "forma": [
    {
     "fecha": "2026-11-08",
     "torneo": "Apertura 2026",
     "fase": "regular",
     "rival": "Puebla",
     "condicion": "local",
     "resultado": "P",
     "gf": 0,
     "gc": 2,
     "marcador": "0-2"
    },
    "…"
   ],
   "rachas": [
    {
     "racha": "partidos sin ganar",
     "partidos": 5
    },
    "…"
   ]
  },
  "equipo_visitante": "… igual que equipo_local",
  "historial": {
   "local": "Querétaro",
   "visitante": "Monterrey",
   "total": {
    "balance": {
     "pj": 42,
     "g": 9,
     "e": 10,
     "p": 23,
     "gf": 47,
     "gc": 79,
     "pct_puntos": 0.2937
    }
   },
   "ultimos": {
    "balance": {
     "pj": 10,
     "g": 1,
     "e": 3,
     "p": 6,
     "gf": 5,
     "gc": 17,
     "pct_puntos": 0.2
    },
    "partidos": [
     {
      "fecha": "2026-03-04",
      "torneo": "Clausura 2026",
      "fase": "regular",
      "local": "Monterrey",
      "visitante": "Querétaro",
      "gl": 4,
      "gv": 0,
      "sede": "bbva"
     },
     "…"
    ]
   },
   "en_sede": {
    "balance": {
     "pj": 10,
     "g": 3,
     "e": 2,
     "p": 5,
     "gf": 10,
     "gc": 15,
     "pct_puntos": 0.3667
    },
    "partidos": [
     {
      "fecha": "2025-09-14",
      "torneo": "Apertura 2025",
      "fase": "regular",
      "local": "Querétaro",
      "visitante": "Monterrey",
      "gl": 0,
      "gv": 1,
      "sede": "corregidora"
     },
     "…"
    ],
    "sede": "corregidora"
   },
   "liguilla": {
    "balance": {
     "pj": 0,
     "g": 0,
     "e": 0,
     "p": 0,
     "gf": 0,
     "gc": 0,
     "pct_puntos": null
    },
    "partidos": []
   },
   "finales": {
    "balance": {
     "pj": 0,
     "g": 0,
     "e": 0,
     "p": 0,
     "gf": 0,
     "gc": 0,
     "pct_puntos": null
    },
    "partidos": []
   },
   "series": {
    "n": 0,
    "gana_local": 0,
    "gana_visitante": 0,
    "finales": 0,
    "lista": []
   }
  },
  "sede": {
   "sede": "corregidora",
   "nombre": "Estadio La Corregidora",
   "ciudad": "Querétaro",
   "lat": 20.57767,
   "lon": -100.36628,
   "altitud_m": 1870,
   "superficie": "natural",
   "aforo": 34107,
   "fuente": "web/medios.json",
   "slug_medios": "corregidora",
   "apodo": "El Coloso del Cimatario",
   "sede_imputada": false,
   "balance_local_3_anios": {
    "pj": 51,
    "g": 17,
    "e": 13,
    "p": 21,
    "gf": 59,
    "gc": 65,
    "pct_puntos": 0.4183,
    "desde": "2023-11-11"
   }
  },
  "descanso_local": {
   "dias": 6.0,
   "previo": "2026-11-08",
   "previo_pendiente": false
  },
  "descanso_visitante": {
   "dias": 6.9,
   "previo": "2026-11-07",
   "previo_pendiente": false
  },
  "viaje_visitante_km": 566.0,
  "suspendidos_local": {
   "equipo": "Querétaro",
   "conocido": true,
   "suspendidos": [
    {
     "jugador": "Santiago Homenchenko",
     "motivo": "llegó a 5 amarillas en el torneo"
    }
   ],
   "apercibidos": [
    {
     "jugador": "Paulo Victor",
     "amarillas": 4
    },
    {
     "jugador": "Daniel Parra",
     "amarillas": 4
    },
    {
     "jugador": "Ali Avila",
     "amarillas": 4
    }
   ],
   "nota": null,
   "ultimo_partido": "2026-11-08 vs Puebla"
  },
  "suspendidos_visitante": {
   "equipo": "Monterrey",
   "conocido": true,
   "suspendidos": [
    {
     "jugador": "Carlos Salcedo",
     "motivo": "expulsado en su último partido (roja)"
    }
   ],
   "apercibidos": [
    {
     "jugador": "Óliver Torres",
     "amarillas": 4
    },
    {
     "jugador": "Ricardo Chávez",
     "amarillas": 4
    }
   ],
   "nota": null,
   "ultimo_partido": "2026-11-07 vs Toluca"
  },
  "lesionados_local": null,
  "lesionados_visitante": null
 },
 "momios": {
  "proveedor": "DraftKings",
  "ml_local": 3.4,
  "ml_empate": 3.6,
  "ml_visitante": 1.952,
  "margen": 0.0842,
  "p_local": 0.2713,
  "p_empate": 0.2562,
  "p_visitante": 0.4725,
  "total_linea": 2.5,
  "over": 1.541,
  "under": 2.25
 }
}
```

## combinada_jornada

Un pick por partido de la jornada próxima (el grupo de pendientes más numeroso; `null` si hay menos de
dos partidos). `candidatos`: un pick por partido, de más a menos probable; `segura`, `equilibrada` y
`atrevida`: los primeros `n` candidatos con su `prob_conjunta` (producto: entre partidos distintos se
supone independencia) y `momio_justo`. `sin_pick`: ids sin pick dentro de la `banda`.

```json
{
 "etiqueta": "Jornada 17",
 "n_partidos": 9,
 "candidatos": [
  {
   "id": 401877050,
   "partido": "Pachuca vs Toluca",
   "clave": "H_L+1.5",
   "etiqueta": "Pachuca gana, empata o pierde por un gol (hándicap +1.5)",
   "familia": "resultado",
   "prob": 0.8445
  },
  "…"
 ],
 "banda": [
  0.58,
  0.85
 ],
 "sin_pick": [],
 "equilibrada": {
  "n": 5,
  "picks": [
   {
    "id": 401877050,
    "partido": "Pachuca vs Toluca",
    "clave": "H_L+1.5",
    "etiqueta": "Pachuca gana, empata o pierde por un gol (hándicap +1.5)",
    "familia": "resultado",
    "prob": 0.8445
   },
   "…"
  ],
  "prob_conjunta": 0.411,
  "momio_justo": 2.4333
 },
 "segura": {
  "n": 4,
  "picks": [
   {
    "id": 401877050,
    "partido": "Pachuca vs Toluca",
    "clave": "H_L+1.5",
    "etiqueta": "Pachuca gana, empata o pierde por un gol (hándicap +1.5)",
    "familia": "resultado",
    "prob": 0.8445
   },
   "…"
  ],
  "prob_conjunta": 0.499,
  "momio_justo": 2.0039
 },
 "atrevida": {
  "n": 8,
  "picks": [
   {
    "id": 401877050,
    "partido": "Pachuca vs Toluca",
    "clave": "H_L+1.5",
    "etiqueta": "Pachuca gana, empata o pierde por un gol (hándicap +1.5)",
    "familia": "resultado",
    "prob": 0.8445
   },
   "…"
  ],
  "prob_conjunta": 0.2105,
  "momio_justo": 4.7514
 }
}
```

## ultimos_resultados

Los resultados más recientes del torneo (los grupos de fechas más nuevos hasta juntar 8 partidos), del
más reciente al más antiguo, con lo que el modelo había dicho ANTES del partido. `pronostico` es `null`
si no hubo pronóstico sellado (ni guardado en `modelo/pred`): no se reconstruye después de conocer el
resultado. Cuando existe: `origen` (`"sello"` o `"modelo/pred (walk-forward, no sellado)"`),
`sellado_utc`, `modelo`, `p_local`, `p_empate`, `p_visitante`, `pick`, `marcador`, `acierto_1x2`,
`marcador_exacto`, `prob_del_resultado` y `logloss`.

```json
{
 "id": 401876902,
 "fecha_local": "2026-11-08",
 "hora_local": "20:10",
 "fase": "regular",
 "etiqueta": "Jornada 16",
 "local": "León",
 "visitante": "Chivas",
 "gl": 1,
 "gv": 1,
 "gl_ht": 0,
 "gv_ht": 0,
 "resultado": "E",
 "pronostico": {
  "origen": "modelo/pred (walk-forward, no sellado)",
  "sellado_utc": null,
  "modelo": "ajuste",
  "p_local": 0.2652,
  "p_empate": 0.2669,
  "p_visitante": 0.4679,
  "pick": "V",
  "marcador": {
   "gl": 1,
   "gv": 1,
   "prob": 0.1272
  },
  "acierto_1x2": false,
  "marcador_exacto": true,
  "prob_del_resultado": 0.2669,
  "logloss": 1.321
 }
}
```

## proyeccion

Resultado de la simulación (20,000 torneos repartidos en 2,000 muestras de los parámetros; `semilla` fija).
`partidos_pendientes_regular` y `regular_completa` dicen en qué punto está el torneo.

- `tabla_final` (18 filas, ordenadas por lugar esperado): `pos_actual`, `pts_actual`, `pj_actual`,
  `puntos_esperados`, `pts_min`/`pts_max` (de las simulaciones), `pos_esperada`, `pos_mas_probable`,
  `posicion` (18 probabilidades: lugar 1 a 18; suman 1), `p_lider`, `p_top4` (cierra los cuartos en
  casa), `p_clasifica`, `p_semifinal`, `p_final`, `p_campeon` y sus errores de Monte Carlo `ee_*`.
- `campeon` (18 filas, de más a menos probable): `equipo`, `prob`, `ee`, `p_final`, `p_semifinal`,
  `p_clasifica`. Las `prob` suman 1.
- `cruces_cuartos`: por llave (`"1-8"`, `"2-7"`, `"3-6"`, `"4-5"`), los cruces más probables: `mejor` y
  `peor` sembrado, `prob` de que se dé ese cruce en esa llave (con `ee`), y `p_avanza_mejor` /
  `p_avanza_peor` condicionadas a que se crucen (`ee_avanza`, `n` simulaciones).
- `cuadro_mas_probable`: los ocho clasificados en su orden exacto más frecuente, con su `prob` (suele
  ser pequeña: es el más probable entre muchísimos) y sus `cruces`.
- `series_posibles`: por fase (`cuartos`, `semifinal`, `final`), los cruces con probabilidad de 1% o
  más, sin importar la llave, con los mismos campos.

```json
{
 "n_sim": 20000,
 "n_muestras": 2000,
 "semilla": 20261110,
 "partidos_pendientes_regular": 10,
 "regular_completa": false,
 "tabla_final": [
  {
   "equipo": "Cruz Azul",
   "pos_actual": 1,
   "pts_actual": 32,
   "pj_actual": 16,
   "puntos_esperados": 33.0779,
   "ee_puntos_esperados": 0.0097,
   "pts_min": 32,
   "pts_max": 35,
   "pos_esperada": 1.7389,
   "pos_mas_probable": 1,
   "posicion": [
    0.4344,
    0.3923,
    0.1733,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0
   ],
   "p_lider": 0.4344,
   "p_top4": 1.0,
   "p_clasifica": 1.0,
   "ee_p_clasifica": 0.0,
   "p_semifinal": 0.7449,
   "ee_p_semifinal": 0.0033,
   "p_final": 0.4413,
   "ee_p_final": 0.004,
   "p_campeon": 0.2109,
   "ee_p_campeon": 0.0033
  },
  "…"
 ],
 "campeon": [
  {
   "equipo": "América",
   "prob": 0.2813,
   "ee": 0.0037,
   "p_final": 0.5023,
   "p_semifinal": 0.8012,
   "p_clasifica": 1.0
  },
  "…"
 ],
 "cruces_cuartos": [
  {
   "llave": "1-8",
   "opciones": [
    {
     "mejor": "Cruz Azul",
     "peor": "Tijuana",
     "prob": 0.1354,
     "ee": 0.0024,
     "p_avanza_mejor": 0.7922,
     "p_avanza_peor": 0.2078,
     "ee_avanza": 0.0078,
     "n": 2709
    },
    "…"
   ]
  },
  "…"
 ],
 "cuadro_mas_probable": {
  "prob": 0.012,
  "siembra": [
   "Cruz Azul",
   "América",
   "Chivas",
   "Santos",
   "Toluca",
   "Atlas",
   "Pachuca",
   "Tijuana"
  ],
  "cruces": [
   {
    "llave": "1-8",
    "mejor": "Cruz Azul",
    "peor": "Tijuana"
   },
   {
    "llave": "2-7",
    "mejor": "América",
    "peor": "Pachuca"
   },
   {
    "llave": "3-6",
    "mejor": "Chivas",
    "peor": "Atlas"
   },
   {
    "llave": "4-5",
    "mejor": "Santos",
    "peor": "Toluca"
   }
  ]
 },
 "series_posibles": {
  "cuartos": [
   {
    "mejor": "Toluca",
    "peor": "Atlas",
    "prob": 0.3098,
    "ee": 0.0033,
    "p_avanza_mejor": 0.8515,
    "p_avanza_peor": 0.1485,
    "ee_avanza": 0.0045,
    "n": 6196
   },
   "…"
  ],
  "semifinal": [
   {
    "mejor": "América",
    "peor": "Toluca",
    "prob": 0.2157,
    "ee": 0.0029,
    "p_avanza_mejor": 0.5977,
    "p_avanza_peor": 0.4023,
    "ee_avanza": 0.0075,
    "n": 4315
   },
   "…"
  ],
  "final": [
   {
    "mejor": "Cruz Azul",
    "peor": "América",
    "prob": 0.1211,
    "ee": 0.0023,
    "p_avanza_mejor": 0.4684,
    "p_avanza_peor": 0.5316,
    "ee_avanza": 0.0101,
    "n": 2421
   },
   "…"
  ]
 }
}
```

## liguilla

`en_curso`: `true` cuando partidos.csv ya trae partidos de liguilla del torneo. `clasificados`: los ocho
en orden de siembra cuando la fase regular terminó (`null` antes). `formato`: reglas y fechas de
`config/torneo.json`. `series`: una entrada por serie REAL (vacío mientras no existan):

| campo | significado |
|---|---|
| `fase`, `mejor`, `peor`, `siembra_mejor`, `siembra_peor` | la serie y quién es el mejor sembrado |
| `piernas` | ida y vuelta: `local`, `visitante`, `jugado`; si ya se jugó `gl`, `gv`; si no, `lam_l`, `lam_v`, `p_local`, `p_empate`, `p_visitante` y `marcadores` (top 5) |
| `p_avanza_mejor`, `p_avanza_peor` | probabilidad EXACTA de avanzar, condicionada a lo ya jugado (lambdas puntuales) |
| `p_avanza_mejor_sim`, `n_sim_cruce` | la misma probabilidad en la simulación (incluye la incertidumbre de los parámetros) |
| `p_global_mejor`, `p_global_empate`, `p_global_peor` | quién gana el marcador global a 180 minutos |
| `globales` | marcadores globales más probables (`mejor`, `peor`, `prob`) |
| `decidida`, `ganador` | si la serie ya terminó y quién avanzó |
| `regla_empate` | qué pasa con el global empatado |

Ejemplo CONSTRUIDO (marcador de ida inventado, sólo para mostrar la forma):

```json
{
 "fase": "cuartos",
 "mejor": "Cruz Azul",
 "peor": "Pachuca",
 "siembra_mejor": 1,
 "siembra_peor": 8,
 "piernas": [
  {
   "pierna": 1,
   "id": 990000000,
   "fecha_utc": "2026-11-26T01:00:00+00:00",
   "local": "Pachuca",
   "visitante": "Cruz Azul",
   "jugado": true,
   "gl": 1,
   "gv": 0
  },
  {
   "pierna": 2,
   "id": 990000001,
   "fecha_utc": "2026-11-29T01:00:00+00:00",
   "local": "Cruz Azul",
   "visitante": "Pachuca",
   "jugado": false,
   "lam_l": 1.7583,
   "lam_v": 1.1389,
   "p_local": 0.5188,
   "p_empate": 0.235,
   "p_visitante": 0.2462,
   "marcadores": [
    {
     "gl": 1,
     "gv": 1,
     "prob": 0.1105
    },
    {
     "gl": 2,
     "gv": 1,
     "prob": 0.0971
    },
    "…"
   ]
  }
 ],
 "decidida": false,
 "ganador": null,
 "p_avanza_mejor": 0.5188,
 "p_avanza_peor": 0.4812,
 "p_global_mejor": 0.2862,
 "p_global_empate": 0.2326,
 "p_global_peor": 0.4812,
 "globales": [
  {
   "mejor": 1,
   "peor": 2,
   "prob": 0.1105
  },
  {
   "mejor": 2,
   "peor": 2,
   "prob": 0.0971
  },
  "…"
 ],
 "regla_empate": "avanza el mejor sembrado",
 "p_avanza_mejor_sim": 0.5139,
 "n_sim_cruce": 20000
}
```

Hoy:

```json
{
 "en_curso": false,
 "clasificados": null,
 "series": [],
 "formato": {
  "cruces_cuartos": [
   [
    1,
    8
   ],
   [
    2,
    7
   ],
   [
    3,
    6
   ],
   [
    4,
    5
   ]
  ],
  "resiembra_semifinal": true,
  "empate_global_cuartos_semis": "avanza el mejor ubicado en la tabla general; sin tiempos extra ni penales",
  "final_empate": "dos tiempos extra de 15 minutos y, si sigue el empate, penales; la tabla no desempata",
  "cierra_en_casa": "mejor posición en la tabla (práctica en 7 de 7 series del Clausura 2026; en la final es derecho del mejor sembrado)",
  "fechas": {
   "cuartos_ida": [
    "2026-11-25",
    "2026-11-26"
   ],
   "cuartos_vuelta": [
    "2026-11-28",
    "2026-11-29"
   ],
   "semis_ida": [
    "2026-12-02",
    "2026-12-03"
   ],
   "semis_vuelta": [
    "2026-12-05",
    "2026-12-06"
   ],
   "final_ida": [
    "2026-12-10"
   ],
   "final_vuelta": [
    "2026-12-13"
   ],
   "final_ida_opcion2": [
    "2026-12-24"
   ],
   "final_vuelta_opcion2": [
    "2026-12-27"
   ]
  }
 }
}
```

### liguilla.torneo (la liguilla con estructura de torneo)

`estado` (`proyectado` antes de que acabe la fase regular, `definido` con los ocho clasificados,
`en_curso`, `terminado`), `origen_siembra`, `siembra` (8 filas: `pos`, `equipo`, `p_clasifica`,
`p_semifinal`, `p_final`, `p_campeon`), `rondas` (cuartos, semifinal, final: `fase`, `nombre`, `fechas`
de ida y vuelta y `series`), `campeon_ruta`, `campeon_decidido`, `p_campeon_ruta` y `nota`. Cada SERIE:

| campo | significado |
|---|---|
| `llave` | `C1`..`C4`, `S1`, `S2`, `F` |
| `fase`, `real`, `viene_de` | `real` = el cruce ya está en el calendario; `viene_de` = llaves de las que salen sus equipos (resiembra) |
| `mejor`, `peor` | `{equipo, siembra}` |
| `piernas` | ida y vuelta: `pierna`, `nombre`, `id`, `fecha_utc`, `fecha_local`, `hora_local`, `local`, `visitante`, `estadio` (`slug`, `nombre`), `jugado`, `gl`, `gv`; sin jugar: `lam_l`, `lam_v`, `p_local`, `p_empate`, `p_visitante`, `marcador` y `marcadores` (5) |
| `global` | `probable` (`mejor`, `peor`, `prob`), `top` (5), `p_gana_mejor`, `p_empate`, `p_gana_peor` |
| `p_avanza_mejor`, `p_avanza_peor`, `favorito`, `p_favorito` | probabilidad exacta de avanzar en ESA serie |
| `decidida`, `ganador`, `regla_empate`, `alternativas` | `alternativas`: otros cruces posibles de esa llave (`mejor`, `peor`, `prob`, `p_avanza_mejor`) |

## fuerzas (18 filas, de mayor a menor `rating`)

Son las columnas que entrega `Pronosticador.fuerzas()`. Con el modelo campeón, todo en GOLES frente a
un rival promedio: `ataque` = goles esperados a favor en cancha neutral; `defensa` = goles esperados
en contra (menos es mejor); `rating` = ataque - defensa; `ventaja_local` = diferencia de goles esperada
en casa menos la de cancha neutral; `ee_*` = errores estándar por la incertidumbre de los parámetros.
(Con el provisional `ataque` y `defensa` son multiplicadores y vienen además `gf_neutral` y
`gc_neutral`; la página debe guiarse por `meta.modelo.origen`.)

```json
{
 "equipo": "América",
 "ataque": 1.9935,
 "defensa": 1.1368,
 "rating": 0.8566,
 "ventaja_local": 0.5104,
 "ee_ataque": 0.1956,
 "ee_defensa": 0.1333,
 "ee_rating": 0.2326,
 "ee_ventaja_local": 0.1168
}
```

## estadios

Balance del local en su sede: `equipo`, `sede` (slug), `estadio`, `altitud_m`, `historico` y
`ultimos_3_anios` (pj, g, e, p, gf, gc, `pct_puntos`, `desde`).

```json
{
 "equipo": "Monterrey",
 "sede": "bbva",
 "estadio": "Estadio BBVA",
 "altitud_m": 495,
 "historico": {
  "pj": 221,
  "g": 128,
  "e": 56,
  "p": 37,
  "gf": 413,
  "gc": 215,
  "pct_puntos": 0.6637,
  "desde": "2015-08-11"
 },
 "ultimos_3_anios": {
  "pj": 62,
  "g": 33,
  "e": 15,
  "p": 14,
  "gf": 114,
  "gc": 75,
  "pct_puntos": 0.6129,
  "desde": "2023-12-02"
 }
}
```

## dominios

Series de liguilla más repetidas desde 2001: `a`, `b`, `series`, `gana_a`, `gana_b`, `sin_decidir`,
`finales`, `finales_a`, `finales_b`, `ultima`. Es descriptivo: en la validación el historial directo no
aporta señal al pronóstico.

```json
{
 "a": "Monterrey",
 "b": "Tigres",
 "series": 9,
 "gana_a": 5,
 "gana_b": 4,
 "sin_decidir": 0,
 "finales": 1,
 "finales_a": 0,
 "finales_b": 1,
 "ultima": "Clausura 2024 (cuartos): Monterrey 3-2 Tigres"
}
```

## desempeno

Desempeño REAL hacia adelante, sólo con pronósticos sellados antes del inicio de cada partido
(`salidas/sellos.jsonl`, que sólo crece; el sello oficial de un partido es el último anterior a su
inicio). `acumulado` (y lo mismo en `por_modelo` y `por_torneo`): `n`, `aciertos_1x2`, `acierto_1x2`,
`marcadores_exactos`, `marcador_exacto`, `logloss` (con `ee_logloss`), `brier`, `rps`,
`prob_media_del_pick`, `logloss_referencia_tercios` (ln 3 = 1.0986) y `combinadas` por variante (`n`,
`completas`, `frecuencia`, `prob_anunciada`, `picks_acertados_media`). Con cero partidos calificados
`acumulado` es `{"n": 0}`. `partidos`: los últimos 40 calificados (`id`, `fecha_utc`, equipos, `gl`,
`gv`, `resultado`, `pick`, `acierto_1x2`, `marcador_exacto`, `logloss`, y por combinada `aciertos` de 4
y `completa`). El detalle completo está en `salidas/desempeno.json`.

```json
{
 "generado_utc": "2026-11-10T10:12:22.746041+00:00",
 "n_sellos": 22,
 "n_partidos_sellados": 10,
 "n_calificados": 0,
 "primer_sello_utc": "2026-11-10T09:57:18.747707+00:00",
 "acumulado": {
  "n": 0
 },
 "por_modelo": {},
 "por_torneo": {},
 "nota": "Sólo cuentan pronósticos sellados antes del inicio de cada partido; con pocos partidos el error estándar es grande y ninguna cifra es concluyente.",
 "partidos": []
}
```

## calibracion_series

Resumen de `salidas/calibracion_series.json` (contraste histórico del cálculo de series; ver
`produccion/SIMULADOR.md`); `null` si no se ha corrido `python3 -m produccion.simulador --calibrar`.

```json
{
 "modelo": "ajuste",
 "n_series": 119,
 "avanza_mejor_observado": 0.6723,
 "avanza_mejor_pronosticado": 0.608,
 "brier": {
  "simulador": 0.2078,
  "frecuencia_previa": 0.225,
  "mitad": 0.25
 },
 "dif_brier_vs_frecuencia": {
  "dif": -0.0172,
  "ee": 0.0106
 },
 "dif_brier_vs_mitad": {
  "dif": -0.0422,
  "ee": 0.0091
 }
}
```

## avisos

Lista de textos con los límites honestos del sistema (lo que no se modela). La página debe mostrarlos.

```json
[
 "Modelo «ajuste»: En la PRUEBA ajuste (1.0272) no mejoró a dc (1.0264) ni a poisson_simple (1.0276): diferencias de menos de 0.3 ee. La ganancia de DESARROLLO (-0.0072) no se confirmó ni se desmintió (IC 95% de ajuste - dc en PRUEBA: [-0.0079, +0.0099]).",
 "Modelo «ajuste»: En la PRUEBA ajuste salió sobreconfiado (pendiente de calibración 0.78; en DESARROLLO 1.01). Todos los modelos y el mercado bajaron de pendiente en ese periodo.",
 "…"
]
```

## vivo (último documento en vivo, incrustado)

Copia de `salidas/vivo.json` en el momento de exportar (o de `exportar.incrustar_vivo()`, que es lo que hace
`pipeline.py auto` justo después de correr `vivo.py una-vez`). Es `null` si el archivo no existe, no se puede
leer, es una repetición de prueba o su `generado_utc` tiene más de 36 horas, y siempre `null` en una corrida
retrospectiva. Sirve como estado inicial de la página: en cuanto llega el documento de la base de datos del
Artifact (`vivo/actual`, por `onSnapshot`) manda el que tenga el `generado_utc` más reciente.

## Documento en vivo (`salidas/vivo.json` · base de datos del Artifact, ruta `vivo/actual`)

Lo escribe `vivo.py` (`una-vez`, `observar` o `repetir`; ver `produccion/VIVO.md`). JSON compacto, escritura
atómica, menos de 40 KB (un día de 4 partidos pesa unos 6 KB). Ejemplo con la forma completa:
`salidas/vivo_ejemplo.json`. JavaScript no calcula nada: todas las probabilidades vienen de aquí.

| campo | significado |
|---|---|
| `version` | 1 |
| `generado_utc` | cuándo se armó (reloj real) |
| `dia` | fecha de México del día de partido (cambia a las 04:00, no a medianoche) |
| `estado` | `sin_partidos` · `previo` (hay partidos hoy y ninguno en juego: falta alguno por empezar) · `en_juego` · `descanso` (los que se juegan están todos en pausa) · `terminado_hoy` |
| `partidos` | los de HOY, por hora de inicio (abajo) |
| `tabla`, `tabla_nota` | tabla general AL MOMENTO (18 filas): `pos`, `equipo`, `PJ`, `PTS`, `DG`, `GF`, `cambio` (lugares ganados, positivo, o perdidos frente a la tabla sin los partidos en juego) y `en_juego`. Los marcadores en juego cuentan como finales; desempates oficiales del simulador (las tarjetas de hoy suman al Fair Play de forma aproximada: amarilla 1, roja 3). En liguilla es la tabla final de la fase regular |
| `proyeccion` | `n_sim`, `clasifica` y `campeon`: listas `{equipo, p, delta}` ordenadas por `p`. `delta` = cambio frente al último pronóstico previo (el de `actual.json`). `clasifica` sólo trae a los equipos sin decidir (vacía en liguilla). `ruido` (0.01): un `delta` menor puede ser ruido de simulación. `partidos_considerados`: ids cuyos marcadores del momento entraron en la simulación. `nota` si no se pudo recalcular |
| `series` | liguilla: una entrada por serie REAL de `liguilla.torneo` (abajo); `[]` en fase regular |
| `ultimo_evento` | `{utc, tipo, partido_id, texto, n}` del último evento notificable del día, o `null` |
| `siguiente` | `{id, inicio_utc, local, visitante}` del próximo partido que no ha empezado (de hoy si queda alguno) |
| `avisos` | (opcional) textos: algo no se pudo calcular o ESPN no respondió para un día |
| `prueba` | (opcional) `true` en los documentos de `vivo.py repetir`; la página debe decirlo |

Cada elemento de `partidos`:

| campo | significado |
|---|---|
| `id`, `fase`, `etiqueta`, `local`, `visitante`, `inicio_utc` | como en `pendientes` (`fase`: `regular`, `cuartos`, `semifinal`, `final`) |
| `estado` | `programado` · `en_juego` · `descanso` · `final` · `pospuesto` |
| `periodo`, `minuto`, `anadido` | `periodo` 1 o 2 (3 y 4 tiempos extra, 5 penales); `minuto` del reloj de ESPN (se está jugando ese minuto); `anadido` en tiempo agregado (`45'+2'` = minuto 45, añadido 2). En el descanso: periodo 1, minuto 45. Al final: minuto 90 y el agregado que hubo. `null` si no ha empezado |
| `reloj_utc` | instante en que empezó el minuto `minuto` (para que la página avance el reloj sola: minuto actual = `minuto` + minutos enteros desde `reloj_utc`, sin pasar de 45 / 90 mientras no llegue otro documento); en el descanso, cuándo se vio empezar; `null` si no se juega |
| `gl`, `gv`, `rojas_l`, `rojas_v` | marcador y expulsiones al momento (`gl`/`gv` `null` si no ha empezado). En tiempos extra el marcador incluye sus goles |
| `eventos` | goles y expulsiones en orden: `min`, `anadido`, `tipo` (`gol`, `penal`, `autogol`, `roja`), `equipo` (en un autogol, el equipo al que le cuenta), `jugador`, `marcador` (parcial tras la jugada, "local-visitante") |
| `previo` | pronóstico SELLADO antes del partido: `p_local`, `p_empate`, `p_visitante`, `marcador` (`gl`, `gv`), `lam_l`, `lam_v`. Si no hay sello trae además `origen` (de dónde salió) |
| `vivo` | sólo en juego o en descanso: `p_local`, `p_empate`, `p_visitante` del resultado FINAL a 90 minutos, `goles_restantes_l`, `goles_restantes_v` (goles que se espera que falten) y `marcador_final` (`gl`, `gv`, `prob`: el marcador final más probable). `null` antes de empezar y al terminar |
| `serie` | `null` o `{llave, mejor, peor, global_mejor, global_peor, p_avanza_mejor, p_avanza_peor}` |
| `penales` | (opcional) `{l, v}` si hubo tanda |

Cada elemento de `series` (SERIE compacta): `llave`, `fase`, `mejor` y `peor` (`{equipo, siembra}`), `piernas`
(`pierna`, `id`, `local`, `visitante`, `estado` [`programado`, `en_juego`, `descanso`, `final`], `gl`, `gv`),
`global_mejor`, `global_peor` (goles de las piernas jugadas o en juego), `p_avanza_mejor`, `p_avanza_peor`
(cálculo exacto con lo ya jugado, el marcador y el minuto de la pierna en juego; final: tiempos extra y
penales a 50/50), `delta_avanza_mejor` (frente a `actual.json`), `favorito`, `p_favorito`, `decidida`,
`ganador` y `al_momento` (`false` = ninguna pierna de la serie se juega hoy: son los números de `actual.json`).

## Otros archivos de `salidas/`

| archivo | contenido |
|---|---|
| `sellos.jsonl` | un renglón por sello: `id`, `sellado_utc`, `corte_modelo_utc`, `modelo`, `torneo`, `fase`, `pierna`, `fecha_utc`, `local`, `visitante`, `lam_l`, `lam_v`, `rho`, `p1_l`, `p1_v`, `p_l`, `p_e`, `p_v`, `pick`, `marcador`, `top5`, `combinadas` (por variante: `prob_conjunta` y `picks` con `clave`, `etiqueta`, `prob`). Sólo se agrega |
| `desempeno.json` | lo de `desempeno` con todos los partidos calificados y el detalle de cada pick |
| `calibracion_series.json` | salida completa de la calibración histórica de series |
| `historial/actual_<corte>.json` | copia de cada corrida |
| `vivo.json` | último documento en vivo (contrato arriba); lo escribe `vivo.py` |
| `vivo_ejemplo.json` | ejemplo con la forma completa del documento en vivo (`"ejemplo": true`) |
| `vivo_eventos.jsonl` | un renglón por evento notificable de `vivo.py observar`: `n` (consecutivo), `utc`, `tipo` (`inicio`, `gol`, `gol_anulado`, `roja`, `descanso`, `segundo_tiempo`, `tiempos_extra`, `penales`, `final`, `pospuesto`, `refresco`), `partido_id`, `texto`, `marcador`, `minuto`. Sólo se agrega |
| `vivo_prueba.json`, `vivo_prueba_eventos.jsonl` | lo mismo para `vivo.py repetir` (no van al repositorio) |
| `en_juego_parametros.json` | parámetros del modelo en juego: curva de goles por casilla (`w`), `efectos` (multiplicadores) y de dónde salieron; se reajusta sola cuando cambian los datos |
| `en_juego_validacion.json` | validación sin fuga del modelo en juego (`python3 -m produccion.en_juego validar`) |
