# Cobertura de la base histórica de Liga MX (ESPN)

Generado automáticamente por `espn_descarga.py` el 2026-11-10 (no editar a mano: se reescribe en cada `tablas` / `actualizar`; los veredictos de la conciliación viven en `conciliacion_veredictos.json`).

- Fuente: API pública de ESPN, liga `mex.1` (scoreboard por año + summary por partido).
- Partidos en `partidos.csv`: **8767** (8684 jugados) de 2001-07-21 a 2026-11-22; 51 torneos.
- ESPN no tiene eventos de Liga MX anteriores al Invierno 2001 (probado 1996-2000: vacío).
- Partidos jugados con algún bloque de detalle (stats, eventos o alineaciones): 8668 (100%).

## 1. Cobertura por torneo

Porcentajes sobre partidos **jugados**. `stats` = boxscore real; `eventos` = goles con minuto que suman el marcador; `tarjetas` = tarjetas con minuto que cuadran con el boxscore; `alin.` = 11 titulares por lado; `HT` = marcador de medio tiempo; `posesión`, `asist.` y `árbitro` = dato presente.

| Torneo | Partidos | Jugados | Regular | Liguilla | stats | eventos | tarjetas | alin. | momios | HT | posesión | asist. | árbitro |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Apertura 2001 | 185 | 185 | 171 | 14 | 0% | 98% | 0% | 0% | 0% | 98% | 0% | 0% | 0% |
| Clausura 2002 | 190 | 189 | 171 | 18 | 0% | 97% | 0% | 3% | 0% | 97% | 0% | 0% | 0% |
| Apertura 2002 | 204 | 204 | 190 | 14 | 0% | 100% | 0% | 48% | 0% | 100% | 0% | 7% | 19% |
| Clausura 2003 | 206 | 206 | 190 | 16 | 0% | 99% | 0% | 47% | 0% | 99% | 0% | 7% | 16% |
| Apertura 2003 | 208 | 208 | 190 | 18 | 100% | 99% | 7% | 43% | 0% | 99% | 0% | 9% | 14% |
| Clausura 2004 | 207 | 206 | 190 | 16 | 100% | 99% | 8% | 39% | 0% | 99% | 0% | 8% | 10% |
| Apertura 2004 | 167 | 167 | 153 | 14 | 99% | 99% | 5% | 40% | 0% | 99% | 0% | 7% | 9% |
| Clausura 2005 | 169 | 167 | 153 | 14 | 99% | 100% | 6% | 57% | 0% | 100% | 0% | 10% | 13% |
| Apertura 2005 | 167 | 167 | 153 | 14 | 100% | 100% | 12% | 99% | 0% | 100% | 0% | 12% | 14% |
| Clausura 2006 | 169 | 167 | 153 | 14 | 99% | 99% | 10% | 100% | 0% | 99% | 0% | 7% | 7% |
| Apertura 2006 | 171 | 171 | 153 | 18 | 100% | 100% | 8% | 100% | 0% | 100% | 0% | 11% | 51% |
| Clausura 2007 | 171 | 170 | 153 | 17 | 0% | 100% | 0% | 100% | 0% | 100% | 0% | 4% | 51% |
| Apertura 2007 | 173 | 171 | 153 | 18 | 0% | 100% | 0% | 100% | 0% | 100% | 0% | 12% | 45% |
| Clausura 2008 | 171 | 171 | 153 | 18 | 81% | 100% | 7% | 44% | 0% | 100% | 0% | 0% | 100% |
| Apertura 2008 | 167 | 167 | 153 | 14 | 100% | 100% | 8% | 43% | 0% | 100% | 0% | 0% | 90% |
| Clausura 2009 | 167 | 167 | 153 | 14 | 100% | 100% | 13% | 17% | 0% | 100% | 0% | 0% | 100% |
| Apertura 2009 | 167 | 167 | 153 | 14 | 99% | 100% | 7% | 15% | 0% | 100% | 0% | 0% | 100% |
| Clausura 2010 | 167 | 167 | 153 | 14 | 100% | 100% | 8% | 13% | 0% | 100% | 0% | 0% | 99% |
| Apertura 2010 | 167 | 167 | 153 | 14 | 100% | 100% | 10% | 14% | 0% | 100% | 0% | 0% | 100% |
| Clausura 2011 | 167 | 167 | 153 | 14 | 99% | 100% | 11% | 22% | 0% | 100% | 0% | 0% | 100% |
| Apertura 2011 | 167 | 167 | 153 | 14 | 100% | 100% | 8% | 22% | 0% | 100% | 0% | 0% | 100% |
| Clausura 2012 | 167 | 167 | 153 | 14 | 100% | 100% | 9% | 37% | 0% | 100% | 0% | 0% | 100% |
| Apertura 2012 | 167 | 167 | 153 | 14 | 98% | 98% | 93% | 99% | 0% | 100% | 98% | 0% | 0% |
| Clausura 2013 | 167 | 167 | 153 | 14 | 100% | 100% | 90% | 100% | 0% | 100% | 100% | 0% | 0% |
| Apertura 2013 | 167 | 167 | 153 | 14 | 100% | 100% | 95% | 100% | 0% | 100% | 100% | 1% | 7% |
| Clausura 2014 | 167 | 167 | 153 | 14 | 100% | 100% | 96% | 100% | 0% | 100% | 100% | 0% | 0% |
| Apertura 2014 | 167 | 167 | 153 | 14 | 100% | 100% | 96% | 100% | 0% | 100% | 100% | 1% | 0% |
| Clausura 2015 | 167 | 167 | 153 | 14 | 100% | 100% | 98% | 100% | 0% | 100% | 100% | 0% | 0% |
| Apertura 2015 | 167 | 167 | 153 | 14 | 99% | 100% | 97% | 100% | 0% | 100% | 99% | 4% | 0% |
| Clausura 2016 | 167 | 167 | 153 | 14 | 100% | 100% | 98% | 100% | 0% | 100% | 100% | 100% | 0% |
| Apertura 2016 | 167 | 167 | 153 | 14 | 99% | 100% | 98% | 99% | 0% | 100% | 99% | 100% | 1% |
| Clausura 2017 | 168 | 167 | 153 | 14 | 100% | 100% | 99% | 98% | 0% | 100% | 100% | 99% | 0% |
| Apertura 2017 | 167 | 167 | 153 | 14 | 100% | 100% | 98% | 99% | 0% | 100% | 100% | 99% | 0% |
| Clausura 2018 | 167 | 167 | 153 | 14 | 92% | 100% | 90% | 100% | 0% | 100% | 92% | 99% | 75% |
| Apertura 2018 | 167 | 167 | 153 | 14 | 84% | 100% | 82% | 98% | 0% | 100% | 83% | 100% | 13% |
| Clausura 2019 | 167 | 167 | 153 | 14 | 94% | 100% | 92% | 100% | 0% | 100% | 93% | 100% | 7% |
| Apertura 2019 | 185 | 185 | 171 | 14 | 78% | 100% | 76% | 99% | 46% | 100% | 76% | 99% | 49% |
| Clausura 2020 | 153 | 90 | 90 | 0 | 87% | 100% | 86% | 99% | 0% | 100% | 86% | 99% | 71% |
| Apertura 2020 | 171 | 171 | 153 | 18 | 91% | 100% | 88% | 100% | 53% | 100% | 91% | 99% | 9% |
| Clausura 2021 | 171 | 171 | 153 | 18 | 95% | 99% | 95% | 100% | 97% | 100% | 95% | 88% | 4% |
| Apertura 2021 | 171 | 171 | 153 | 18 | 94% | 100% | 93% | 100% | 95% | 100% | 94% | 81% | 5% |
| Clausura 2022 | 171 | 171 | 153 | 18 | 89% | 100% | 88% | 98% | 97% | 100% | 89% | 89% | 53% |
| Apertura 2022 | 171 | 171 | 153 | 18 | 87% | 100% | 85% | 100% | 100% | 100% | 87% | 36% | 100% |
| Clausura 2023 | 171 | 171 | 153 | 18 | 91% | 100% | 90% | 100% | 100% | 100% | 90% | 100% | 100% |
| Apertura 2023 | 170 | 170 | 153 | 17 | 89% | 100% | 88% | 100% | 100% | 100% | 88% | 100% | 100% |
| Clausura 2024 | 170 | 170 | 153 | 17 | 89% | 100% | 89% | 100% | 99% | 100% | 89% | 100% | 100% |
| Apertura 2024 | 170 | 170 | 153 | 17 | 91% | 100% | 91% | 100% | 93% | 100% | 91% | 100% | 100% |
| Clausura 2025 | 170 | 170 | 153 | 17 | 98% | 100% | 96% | 100% | 100% | 100% | 98% | 100% | 100% |
| Apertura 2025 | 170 | 170 | 153 | 17 | 100% | 100% | 99% | 100% | 98% | 100% | 100% | 99% | 100% |
| Clausura 2026 | 167 | 167 | 153 | 14 | 100% | 100% | 99% | 100% | 100% | 100% | 100% | 92% | 100% |
| Apertura 2026 | 153 | 143 | 143 | 0 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 1% | 60% |

## 2. Desde qué torneo es confiable cada bloque

Regla: primer torneo a partir del cual TODOS los torneos siguientes (con partidos jugados) cumplen el umbral.

| Bloque | ≥ 95% desde | ≥ 80% desde | Cobertura en ese tramo (≥95%) |
|---|---|---|---|
| Estadísticas (tiros, córners, faltas, tarjetas...) | Clausura 2025 | Clausura 2020 | 647 de 650 (100%) |
| Posesión | Clausura 2025 | Clausura 2020 | 646 de 650 (99%) |
| Goles con minuto | Apertura 2001 | Apertura 2001 | 8659 de 8684 (100%) |
| Marcador de medio tiempo | Apertura 2001 | Apertura 2001 | 8664 de 8684 (100%) |
| Tarjetas con minuto | Clausura 2025 | Clausura 2020 | 642 de 650 (99%) |
| Alineaciones (11 titulares) | Apertura 2012 | Apertura 2012 | 4780 de 4799 (100%) |
| Momios 1X2 | Clausura 2025 | Clausura 2021 | 646 de 650 (99%) |
| Asistencia | nunca | nunca |  |
| Árbitro | nunca | nunca |  |

## 3. Notas de calidad de los datos

- **Marcador de 90 minutos**: `gl`/`gv` nunca incluyen tiempos extra. Hay 15 partidos con tiempos extra (`gl_et`/`gv_et`) y 20 con tanda de penales (`pen_l`/`pen_v`). El campo `score` de ESPN SÍ incluye los goles del tiempo extra; aquí se separan con el marcador por periodos y los goles con minuto.
- **Jugadas duplicadas**: ESPN ingirió dos veces algunos partidos (sobre todo 2016-2018): los goles y tarjetas salen repetidos con un minuto de diferencia. Se depuran (se conserva la versión reprocesada) y sólo se marca `tiene_eventos`=1 si los goles suman el marcador.
- **Estadísticas en ceros**: en partidos viejos ESPN manda 0 en lo que no midió. Se dejan VACÍAS (no cero) cuando el boxscore no tiene tiros y faltas; la posesión sólo cuando ambos lados suman 100.
- **Estadios**: ESPN usa el nombre actual del inmueble (p. ej. el Azteca aparece como Estadio Banorte en todos los años); `estadio_id` es estable.
- **Asistencia**: ESPN manda 0 cuando no la tiene; se deja vacío salvo partidos a puerta cerrada.
- **Momios**: valor de cierre del proveedor principal (se excluyen los momios en vivo). Ver la sección 2 para saber desde cuándo existen.
- **Equipos 2001-2003**: el nombre sigue al id de ESPN, que agrupa franquicias. En Invierno 2001 y Verano 2002 `Querétaro` (id 222) corresponde a La Piedad y `Chiapas` (id 224) a la franquicia que después fue Jaguares; `Colibríes` (id 217) es Celaya hasta el Apertura 2002. No se verificó partido por partido; no afecta de 2004 en adelante.
- **Resultados de escritorio / abandonados**: 2021-02-20 Atlas 3-0 América (id 590969: abandonado según ESPN; resultado oficial 3-0 distinto de los goles en cancha 0-2 (resultado de escritorio)); 2022-03-05 Querétaro 0-1 Atlas (id 623106: partido suspendido al 62' por violencia en la tribuna con 0-1; ESPN conserva el marcador de cancha y historico_ligamx.csv trae 0-3 (resultado de escritorio)). `gl`/`gv` llevan lo que publica ESPN (en el abandonado de 2021, el resultado oficial de escritorio; en el suspendido de 2022, el de cancha); los goles de cancha están en goles.csv. Conviene excluir estos partidos al ajustar modelos de goles.
- **Fases corregidas** (19 partidos en Apertura 2002, Apertura 2003, Apertura 2009, Clausura 2014): ESPN etiquetó mal la fase (liguilla completa como 'reclassification', final como semifinal o cuartos como fase regular); se dedujo por la estructura de las series. El valor original queda en `fase_espn`.
- **Registros fantasma** (3): eventos que ESPN dejó como 'programado' con fecha pasada y sin resultado; quedan como `pospuesto` con nota: 40393 (2002-02-03 Querétaro-Morelia), 194736 (2006-01-30 Morelia-Atlas), 490116 (2016-07-17 Tigres-Chivas).
- **Medio tiempo**: en 10 partidos el conteo de goles del primer tiempo difiere del marcador por periodos de ESPN; se usa el de los goles con minuto y se anota en `nota`.

## 4. Diccionario de columnas

### partidos.csv (una fila por partido, incluidos los programados)

| Columna | Significado |
|---|---|
| `id` | Identificador del evento en ESPN (llave de todas las tablas). |
| `fecha_utc` | Fecha y hora de inicio en UTC, ISO 8601 (`2026-11-14T23:00Z`). |
| `fecha_local` | Fecha en America/Mexico_City (los partidos nocturnos caen en el día UTC siguiente). |
| `anio` | Año de `fecha_local`. |
| `torneo` | `Apertura AAAA` o `Clausura AAAA` (Invierno/Verano de 2001-2002 se nombran igual). |
| `fase` | `regular`, `repechaje` (reclasificación o play-in), `cuartos`, `semifinal`, `final`. |
| `pierna` | 1 = ida, 2 = vuelta en series a dos partidos (orden cronológico del cruce); vacío en fase regular y en repechaje a partido único. |
| `estado` | `jugado`, `programado`, `pospuesto`, `cancelado` (y `en_juego` si se corre durante un partido). |
| `local, visitante` | Nombre canónico, único y estable por id de ESPN. |
| `gl, gv` | Goles al final del tiempo REGLAMENTARIO (90 min + agregado). Nunca incluyen tiempos extra ni penales. |
| `gl_et, gv_et` | Marcador tras 120 min; sólo si hubo tiempos extra (finales). Vacío en los demás. |
| `pen_l, pen_v` | Tanda de penales, si hubo. |
| `gl_ht, gv_ht` | Marcador al medio tiempo. `ht_fuente` dice de dónde sale. |
| `estadio, ciudad` | Sede según ESPN (ESPN usa el nombre ACTUAL del inmueble aun en partidos viejos). |
| `asistencia` | Asistencia reportada; vacío si ESPN no la trae (ESPN manda 0); 0 sólo si fue a puerta cerrada. |
| `arbitro` | Árbitro central, si viene. |
| `tiros, tiros_puerta, corners, faltas, amarillas, rojas, posesion, fueras_lugar, atajadas, penales_tirados, penales_gol (_l / _v)` | Estadísticas del boxscore por lado. Vacías si `tiene_stats`=0. `posesion` en % (sólo desde que ESPN la mide). |
| `ml_l, ml_e, ml_v` | Momios 1X2 en DECIMAL (local, empate, visitante), valor de cierre del proveedor. |
| `total_linea, over, under` | Línea de goles totales y momios decimales de más/menos. |
| `proveedor` | Casa de apuestas de la que salen los momios. |
| `tiene_stats` | 1 si el boxscore trae estadísticas reales (tiros y faltas > 0). |
| `tiene_eventos` | 1 si los goles con minuto de goles.csv suman exactamente el marcador. |
| `tiene_alineaciones` | 1 si ambos equipos tienen 11 titulares en alineaciones.csv. |
| `tiene_momios` | 1 si hay momios 1X2 completos. |
| `tiene_tarjetas` | (extra) 1 si las tarjetas con minuto coinciden (±1) con las amarillas del boxscore. |
| `hora_local` | (extra) Hora de inicio en America/Mexico_City. |
| `serie` | (extra) En liguilla, los dos equipos del cruce en orden alfabético. |
| `local_id, visitante_id, estadio_id` | (extra) Ids de ESPN. |
| `formacion_l, formacion_v` | (extra) Formación inicial (4-4-2...). |
| `pases, pases_precisos, centros, centros_precisos, tiros_bloqueados, entradas, intercepciones, despejes (_l / _v)` | (extra) Estadísticas avanzadas; sólo temporadas recientes. |
| `ml_l_abre, ml_e_abre, ml_v_abre, over_abre, under_abre` | (extra) Momios de apertura en decimal. |
| `ht_fuente` | (extra) `eventos` = contado de los goles con minuto; `parciales` = marcador por tiempos de ESPN; `marcador` = el partido terminó 0-0. |
| `temporada_espn, fase_espn, estado_espn` | (extra) Valores crudos de ESPN (season.year, season.slug, status). |
| `nota` | (extra) Avisos: fase corregida, resultado de escritorio, registro fantasma, etc. |

### Otras tablas

**goles.csv** (un renglón por gol; no incluye la tanda de penales): `partido_id`, `minuto`, `anadido` (minutos de
compensación: `90'+4'` → minuto 90, añadido 4), `periodo` (1, 2; 3 y 4 = tiempos extra), `equipo` (el que recibe
el gol a favor), `jugador`, `tipo` (`gol`, `penal`, `autogol`), y extras `subtipo` (`cabeza`, `tiro_libre`,
`volea`), `jugador_id`, `asistencia`.

**tarjetas.csv**: `partido_id`, `minuto`, `periodo`, `equipo`, `jugador`, `tipo` (`amarilla`, `roja`,
`segunda_amarilla`), y extras `anadido`, `jugador_id`. `segunda_amarilla` sólo se distingue cuando ESPN trae el
texto de la jugada ("Second yellow card..."); en partidos viejos toda expulsión sale como `roja`.

**alineaciones.csv** (un renglón por jugador convocado): `partido_id`, `equipo`, `jugador_id`, `jugador`,
`titular` (1/0), `posicion` (abreviatura de ESPN: G, CD-L, LB, AM, F...; vacío para suplentes),
`minuto_entra`, `minuto_sale` (sólo por cambio; las expulsiones están en tarjetas.csv), `formacion`.

**calendario_pendiente.json**: partidos por jugar del torneo en curso (`id`, `fecha_utc`, `fecha_local`,
`hora_local`, `fase`, `pierna`, `estado`, `local`, `visitante`, `estadio`, `ciudad`, `momios` si ya hay).

**tabla_<torneo>.csv**: tabla general calculada desde partidos.csv (`PJ, G, E, P, GF, GC, DG, PTS`, y lo mismo
con sufijo `_L` de local y `_V` de visita) junto a las cifras del endpoint `standings` de ESPN (`espn_*`) y
`coincide_espn` (1 = cifras y posición iguales; `cifras` = cifras iguales pero ESPN ordena distinto un empate).

## 5. Conciliación con los históricos previos del repositorio

### 5.1 `historico_ligamx.csv` (5014 partidos, 2010-07-23 a 2026-08-02)

- Partidos jugados de ESPN en ese rango de fechas: 5351.
- Emparejados (mismos equipos y localía, fecha a ±4 días): **5014 de 5014**; 5009 con la misma fecha local y 5 con otra fecha.
- Marcador idéntico: **4999 de 5014** (el histórico usa el marcador tras tiempos extra; se comparó contra `gl_et`/`gv_et` cuando existen: 5 finales coinciden sólo así).
- Discrepancias de marcador: 15; de fase regular/liguilla: 0; con localía invertida: 1; sólo en el histórico: 0; sólo en ESPN: 337.

**Discrepancias de marcador**

| Fecha | Partido | Histórico | ESPN (90') | ESPN tras TE | Goles con minuto | id ESPN | Veredicto |
|---|---|---|---|---|---|---|---|
| 2015-11-29 | Veracruz - Pumas | 0-1 | 1-0 |  | cuadran con ESPN | 438108 | ESPN. El histórico no tiene la ida: en su lugar repite la vuelta en espejo (misma fecha 2015-11-29, equipos invertidos). La ida se jugó el 2015-11-26 y terminó Veracruz 1-0 Pumas; los goles con minuto de ESPN lo confirman. |
| 2015-11-29 | Puebla - Toluca | 0-1 | 2-2 |  | cuadran con ESPN | 438109 | ESPN. El histórico no tiene la ida: en su lugar repite la vuelta en espejo (misma fecha 2015-11-29, equipos invertidos). La ida se jugó el 2015-11-26 y terminó Puebla 2-2 Toluca; los goles con minuto de ESPN lo confirman. |
| 2019-12-08 | Morelia - América | 0-2 | 2-0 |  | cuadran con ESPN | 560356 | ESPN. El histórico no tiene la ida: en su lugar repite la vuelta en espejo (misma fecha 2019-12-08, equipos invertidos). La ida se jugó el 2019-12-05 y terminó Morelia 2-0 América; los goles con minuto de ESPN lo confirman. |
| 2020-11-22 | Monterrey - Puebla | 2-4 | 2-2 |  | cuadran con ESPN | 588199 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 2-2 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 2-4. Los goles con minuto de ESPN suman 2-2. |
| 2021-05-09 | León - Toluca | 2-4 | 2-2 |  | cuadran con ESPN | 602127 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 2-2 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 2-4. Los goles con minuto de ESPN suman 2-2. |
| 2021-11-20 | Puebla - Chivas | 6-5 | 2-2 |  | cuadran con ESPN | 621667 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 2-2 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 6-5. Los goles con minuto de ESPN suman 2-2. |
| 2022-03-05 | Querétaro - Atlas | 0-3 | 0-1 |  | cuadran con ESPN | 623106 | Ambas, cada una en lo suyo: ESPN trae 0-1, el marcador de cancha cuando el partido se suspendió al 62' por la violencia en la tribuna; el histórico trae 0-3, que corresponde a un resultado de escritorio. Para tabla oficial vale el histórico; para modelos de goles conviene excluirlo (queda marcado en `nota`). |
| 2022-05-07 | Cruz Azul - Necaxa | 3-1 | 1-1 |  | cuadran con ESPN | 634829 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 1-1 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 3-1. Los goles con minuto de ESPN suman 1-1. |
| 2022-05-07 | Monterrey - Atlético San Luis | 1-3 | 2-2 |  | cuadran con ESPN | 634830 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 2-2 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 1-3. Los goles con minuto de ESPN suman 2-2. |
| 2022-05-08 | Puebla - Mazatlán | 3-1 | 2-2 |  | cuadran con ESPN | 634831 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 2-2 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 3-1. Los goles con minuto de ESPN suman 2-2. |
| 2022-10-09 | Puebla - Chivas | 5-4 | 1-1 |  | cuadran con ESPN | 654397 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 1-1 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 5-4. Los goles con minuto de ESPN suman 1-1. |
| 2024-05-02 | Necaxa - Querétaro | 3-2 | 1-1 |  | cuadran con ESPN | 702270 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 1-1 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 3-2. Los goles con minuto de ESPN suman 1-1. |
| 2024-05-02 | Pachuca - Pumas | 3-5 | 0-0 |  | cuadran con ESPN | 702271 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 0-0 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 3-5. Los goles con minuto de ESPN suman 0-0. |
| 2024-11-21 | Tijuana - América | 2-3 | 2-2 |  | cuadran con ESPN | 723397 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 2-2 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 2-3. Los goles con minuto de ESPN suman 2-2. |
| 2025-04-27 | Juárez - Pumas | 1-2 | 1-1 |  | cuadran con ESPN | 735470 | ESPN. El histórico guardó el marcador de la TANDA de penales como si fueran goles; el partido terminó 1-1 en 90 min (repechaje a partido único, sin tiempos extra) y la tanda fue 1-2. Los goles con minuto de ESPN suman 1-1. |

**Diferencias de fecha** (días ESPN − histórico: partidos): -3: 3, +1: 2.

Las 3 diferencias de -3 días son las idas de liguilla mal fechadas en el histórico (ver tabla de marcadores). En las de +1 día se prefiere ESPN, que da hora exacta de inicio en UTC: Puebla-América (cuartos de ida, Clausura 2022) se jugó el miércoles 11-may-2022 por la noche; para Tigres-Atlético San Luis (jul-2026) no hay tercera fuente, pero la hora UTC de ESPN (03:00Z del 26) es coherente con sábado 25 a las 21:00 locales.

| Histórico | ESPN local | ESPN UTC | Partido | id |
|---|---|---|---|---|
| 2015-11-29 | 2015-11-26 | 2015-11-27T01:00Z | Veracruz - Pumas | 438108 |
| 2015-11-29 | 2015-11-26 | 2015-11-27T03:00Z | Puebla - Toluca | 438109 |
| 2019-12-08 | 2019-12-05 | 2019-12-06T02:30Z | Morelia - América | 560356 |
| 2022-05-10 | 2022-05-11 | 2022-05-12T02:05Z | Puebla - América | 635029 |
| 2026-07-24 | 2026-07-25 | 2026-07-26T03:00Z | Tigres - Atlético San Luis | 401877034 |

**Localía invertida**: 2012-10-04 Morelia-Chiapas (ESPN: Chiapas local, id 348028) Probablemente el histórico (Morelia local). Indicio: en el histórico la localía de este cruce alterna torneo a torneo (A2011 Morelia, C2012 Chiapas, A2012 Morelia, C2013 Chiapas), mientras que ESPN pone a Chiapas de local tres torneos seguidos y no trae sede para este partido. Marcador 1-1 en ambas. No verificado con tercera fuente; `partidos.csv` conserva lo que dice ESPN..

**Sólo en ESPN** (jugados, dentro del rango, sin par en el histórico): 2025-07-11 Puebla 2-3 Atlas (Apertura 2025 regular, id 736614); 2025-07-11 Juárez 1-1 América (Apertura 2025 regular, id 736616); 2025-07-11 Tijuana 1-0 Querétaro (Apertura 2025 regular, id 736615); 2025-07-12 Santos 3-0 Pumas (Apertura 2025 regular, id 736617); 2025-07-12 Toluca 3-1 Necaxa (Apertura 2025 regular, id 736618); 2025-07-12 Cruz Azul 0-0 Mazatlán (Apertura 2025 regular, id 736619); 2025-07-13 Pachuca 3-0 Monterrey (Apertura 2025 regular, id 736620); 2025-07-13 León 0-1 Atlético San Luis (Apertura 2025 regular, id 736621); 2025-07-16 América 3-1 Tijuana (Apertura 2025 regular, id 736622); 2025-07-16 Santos 2-4 Toluca (Apertura 2025 regular, id 736623); 2025-07-18 Necaxa 3-1 Querétaro (Apertura 2025 regular, id 736624); 2025-07-18 Atlético San Luis 0-1 Monterrey (Apertura 2025 regular, id 736626); 2025-07-18 Mazatlán 2-1 Puebla (Apertura 2025 regular, id 736625); 2025-07-19 Tigres 1-0 Juárez (Apertura 2025 regular, id 736627); 2025-07-19 León 1-0 Chivas (Apertura 2025 regular, id 736628); 2025-07-19 Atlas 3-3 Cruz Azul (Apertura 2025 regular, id 736629); 2025-07-20 Pumas 2-3 Pachuca (Apertura 2025 regular, id 736630); 2025-07-25 Puebla 1-0 Santos (Apertura 2025 regular, id 736631); 2025-07-25 Querétaro 0-2 Pumas (Apertura 2025 regular, id 736632); 2025-07-25 Tijuana 1-1 Juárez (Apertura 2025 regular, id 736633); 2025-07-26 Pachuca 1-0 Mazatlán (Apertura 2025 regular, id 736635); 2025-07-26 Chivas 4-3 Atlético San Luis (Apertura 2025 regular, id 736634); 2025-07-26 Cruz Azul 4-1 León (Apertura 2025 regular, id 736636); 2025-07-26 Toluca 3-4 Tigres (Apertura 2025 regular, id 736637); 2025-07-26 Monterrey 3-1 Atlas (Apertura 2025 regular, id 736639); 2025-07-26 Necaxa 1-1 América (Apertura 2025 regular, id 736638); 2025-08-08 Tigres 7-0 Puebla (Apertura 2025 regular, id 736640); 2025-08-09 América 1-0 Querétaro (Apertura 2025 regular, id 736641); 2025-08-09 Mazatlán 2-2 Tijuana (Apertura 2025 regular, id 736643); 2025-08-09 Atlas 0-3 Pachuca (Apertura 2025 regular, id 736642); 2025-08-10 Pumas 1-1 Necaxa (Apertura 2025 regular, id 736644); 2025-08-10 Santos 1-0 Chivas (Apertura 2025 regular, id 736645); 2025-08-11 León 1-3 Monterrey (Apertura 2025 regular, id 736646); 2025-08-11 Juárez 0-2 Toluca (Apertura 2025 regular, id 736648); 2025-08-11 Atlético San Luis 1-2 Cruz Azul (Apertura 2025 regular, id 736647); 2025-08-15 Puebla 0-2 Atlético San Luis (Apertura 2025 regular, id 736649); 2025-08-15 Necaxa 0-1 León (Apertura 2025 regular, id 736650); 2025-08-16 Chivas 1-2 Juárez (Apertura 2025 regular, id 736652); 2025-08-16 Pachuca 0-2 Tijuana (Apertura 2025 regular, id 736653); 2025-08-16 Tigres 1-3 América (Apertura 2025 regular, id 736654); 2025-08-16 Cruz Azul 3-2 Santos (Apertura 2025 regular, id 736655); 2025-08-16 Toluca 1-1 Pumas (Apertura 2025 regular, id 736651); 2025-08-17 Querétaro 3-3 Atlas (Apertura 2025 regular, id 736656); 2025-08-17 Monterrey 3-2 Mazatlán (Apertura 2025 regular, id 736657); 2025-08-22 Juárez 2-1 Santos (Apertura 2025 regular, id 736658); 2025-08-22 Querétaro 3-2 Atlético San Luis (Apertura 2025 regular, id 736659); 2025-08-22 Tijuana 3-3 Chivas (Apertura 2025 regular, id 736660); 2025-08-23 León 1-1 Pachuca (Apertura 2025 regular, id 736662); 2025-08-23 Mazatlán 2-2 Tigres (Apertura 2025 regular, id 736661); 2025-08-23 Monterrey 3-0 Necaxa (Apertura 2025 regular, id 736663); 2025-08-23 Cruz Azul 1-0 Toluca (Apertura 2025 regular, id 736664); 2025-08-24 Pumas 0-0 Puebla (Apertura 2025 regular, id 736665); 2025-08-24 Atlas 2-4 América (Apertura 2025 regular, id 736666); 2025-08-29 Atlético San Luis 1-3 Toluca (Apertura 2025 regular, id 736667); 2025-08-29 Juárez 1-0 Mazatlán (Apertura 2025 regular, id 736668); 2025-08-29 Puebla 2-4 Monterrey (Apertura 2025 regular, id 736669); 2025-08-30 León 3-0 Querétaro (Apertura 2025 regular, id 736670); 2025-08-30 Santos 0-1 Tigres (Apertura 2025 regular, id 736672); 2025-08-30 Chivas 1-2 Cruz Azul (Apertura 2025 regular, id 736671); 2025-08-30 América 2-0 Pachuca (Apertura 2025 regular, id 736673) ....

**Lectura general.** Las dos fuentes coinciden en 4,999 de 5,014 partidos (99.7%). Las 15 diferencias de marcador son errores sistemáticos del histórico y no de ESPN: (a) 11 partidos de repechaje/play-in definidos en penales donde el histórico guardó la tanda como marcador; (b) 3 idas de liguilla (2015 x2, 2019) sustituidas por una copia en espejo de la vuelta; (c) Querétaro-Atlas del 5-mar-2022, donde cada fuente guarda una cosa distinta (cancha vs escritorio). Además el histórico NO contiene el Apertura 2025 ni el Clausura 2026 (337 partidos jugados que ESPN sí tiene) y en finales con tiempos extra trae el marcador de 120 min. Para modelar goles debe usarse `partidos.csv` (gl/gv a 90 min).

### 5.2 `historico_ht_ligamx.csv` (2047 partidos, 2018-07-20 a 2024-09-18)

- Emparejados: **2047 de 2047** (ESPN tiene 2049 jugados en el rango; 2 no están en ese histórico).
- Medio tiempo idéntico: **2046 de 2047** con dato en ambas fuentes (0 sin medio tiempo en ESPN). Discrepancias de medio tiempo: 1; de marcador final: 1; sin par: 0.

**Discrepancias de medio tiempo**

| Fecha | Partido | Final | HT histórico | HT ESPN | fuente ESPN | id ESPN | Veredicto |
|---|---|---|---|---|---|---|---|
| 2019-12-08 | Morelia - América | 2-0 | 0-2 | 1-0 | eventos | 560356 | ESPN. El histórico no tiene la ida: en su lugar repite la vuelta en espejo (misma fecha 2019-12-08, equipos invertidos). La ida se jugó el 2019-12-05 y terminó Morelia 2-0 América; los goles con minuto de ESPN lo confirman. |

**Discrepancias de marcador final**: 2019-12-08 Morelia-América (hist 0-2, ESPN 2-0) ESPN. El histórico no tiene la ida: en su lugar repite la vuelta en espejo (misma fecha 2019-12-08, equipos invertidos). La ida se jugó el 2019-12-05 y terminó Morelia 2-0 América; los goles con minuto de ESPN lo confirman..

**Lectura general.** Donde ambas fuentes tienen medio tiempo, coinciden; ESPN es por tanto confiable para mercados de mitades y además cubre desde 2001 (el histórico sólo 2018-2024).

## 6. Verificaciones automáticas (`espn_descarga.py verificar`)

| Prueba | Resultado | Detalle |
|---|---|---|
| ids únicos | OK | 8767 filas, 8767 ids |
| sin partidos jugados duplicados (torneo, fase, pierna, local, visitante) | OK |  |
| todo partido jugado tiene marcador | OK |  |
| gl_ht <= gl y gv_ht <= gv | OK |  / excepciones documentadas (resultado de escritorio): 590969 2021-02-20 Atlas-América HT 0-1 FT 3-0 |
| marcador tras tiempos extra >= marcador de 90 min | OK |  |
| fecha_local = fecha_utc convertida a America/Mexico_City | OK | 5157 partidos nocturnos caen en el día UTC siguiente y quedan en su día local correcto |
| fase regular completa por torneo (n equipos a una vuelta) | OK | 49 torneos completos; incompletos: Clausura 2020: 90 de 153 jugados (18 equipos; otros: {'cancelado': 63}); Apertura 2026: 143 de 153 jugados (18 equipos; otros: {'programado': 10}) |
| liguilla: 8 partidos de cuartos, 4 de semifinal y 2 de final por torneo | OK |  |
| goles.csv suma el marcador en los partidos con tiene_eventos=1 | OK |  |
| todos los equipos tienen nombre canónico | OK |  |
| no hay partidos 'programado' con fecha pasada | OK |  |
| tabla del Apertura 2026 = standings de ESPN | OK | 18 equipos con PJ, G, E, P, GF, GC, DG, PTS y posición idénticos |

## 7. Cómo se actualiza

```
python3 ligamx/datos/espn_descarga.py actualizar   # después de cada partido (incremental, ~10 peticiones)
python3 ligamx/datos/espn_descarga.py todo         # reconstrucción completa (miles de peticiones, ~35 min)
python3 ligamx/datos/espn_descarga.py verificar    # pruebas de consistencia (código de salida 1 si falla)
```

`actualizar` imprime en stdout un JSON con lo que cambió (partidos nuevos jugados, reprogramados, nuevos en calendario, correcciones) y funciona aunque `cache/` esté vacío (clon nuevo): conserva las filas de los CSV y sólo pide a ESPN lo nuevo.
