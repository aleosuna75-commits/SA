# Variables a la fecha (`modelo/variables.py`)

Generado el 2026-11-10 con los datos de `datos/` de esa fecha. Las tablas de las secciones 4 y 5 salen de
`python3 variables.py --catalogo` y `python3 variables.py --analisis` (se pueden regenerar tal cual).

Resumen: **5,644 filas** (una por partido jugado desde 2010 y por cada uno de los 10 programados) y
**309 variables** en 13 grupos. Reconstrucción completa en ~4.5 s; actualización incremental
tras un partido nuevo en ~2.5 s; 20 pruebas (`pruebas/test_variables.py`, ~2 min 45 s).

## 1. Cómo se usa

```python
import variables as V
df = V.cargar()                         # modelo/cache/variables.parquet   (corte por partido)
dfb = V.cargar("bloque")                # modelo/cache/variables_bloque.parquet (corte por bloque lunes/viernes)
X = df[V.columnas(df)]                  # sólo lo disponible al pronosticar, sin mercado ni "_real"
V.columnas(df, mercado=True)            # agrega mercado_*
V.catalogo()                            # nombre, grupo, definición y disponibilidad de cada variable
V.actualizar()                          # tras `espn_descarga.py actualizar`: recalcula sólo lo afectado
V.construir(partidos, hasta="2026-05-02T01:00Z")   # historial truncado: lo de ese instante en adelante = pendiente
```

- Llave: `id` (entero, el de ESPN). Las filas traen además `fecha_utc`, `corte_utc` (instante hasta el que se usó
  información), `torneo`, `periodo` (calentamiento / desarrollo / prueba), `fase`, `estado`, `local`, `visitante`.
  **No traen el resultado**: se une por `id` con `partidos.csv` o con `datos.cargar()`.
- Sufijos: `_l` local, `_v` visitante, `_dif` = local − visitante. Todo es `float64`; lo que no se sabe es `NaN`
  (nunca cero).
- Línea de comandos: `python3 variables.py` (incremental de las dos cachés), `--completo`, `--catalogo`, `--analisis`.
- `construir` acepta la tabla en texto (como el CSV) o ya tipada (la de `datos.cargar()`); da lo mismo (hay prueba).

## 2. Por qué no hay fuga

**Diseño.** El historial se recorre en orden cronológico. Un partido jugado *entra al estado* cuando ya se conoce y
las variables de un partido se calculan *leyendo* el estado en su corte, sin modificarlo. No hay medias globales,
escalados ni parámetros ajustados con toda la muestra.

**Qué se conoce y cuándo** (parámetro `corte`):

| `corte` | Corte de cada partido | Un partido jugado cuenta si... | Caché | Para qué |
|---|---|---|---|---|
| `partido` (por omisión) | su hora de inicio | empezó al menos 3 h antes | `variables.parquet` | pronóstico en producción justo antes del partido; para los pendientes equivale a "todo lo jugado" |
| `bloque` | lunes o viernes 00:00 (CDMX) anterior | empezó antes de ese corte | `variables_bloque.parquet` | **el protocolo walk-forward por bloque**: nada del propio bloque |
| `dia` | 00:00 (CDMX) del día | empezó antes de ese corte | se construye con `V.actualizar("dia")` | granularidad "día" del modelo final |

Aviso para quien modele: con `corte='partido'` la tabla de posiciones de un partido de domingo ya incluye los
resultados del viernes y sábado de la misma jornada. Eso es legítimo al pronosticar a la hora del partido, pero
**no** respeta el corte por bloque del arnés. Para evaluar con el protocolo de bloques hay que usar
`variables_bloque.parquet`; la diferencia entre ambas es pequeña (cambian tabla, medias de liga y, en 5
casos, el partido anterior de un equipo que jugó dos veces en el mismo bloque).

**Del propio partido sólo se usa lo que existe antes de jugarlo:** equipos, fecha y hora, torneo, fase, pierna,
serie, estadio, árbitro (si ya está) y momios. Dos familias de columnas quedan marcadas por nombre:

- `*_real*` (10 columnas): usan el once que SÍ jugó. No están disponibles al pronosticar (salvo en la hora previa,
  cuando se publica la alineación). Sirven sólo para medir cuánto importaría saber el once.
- `mercado_*` (11 columnas): momios. El de cierre se fija al silbatazo (posterior al corte del bloque) y no existe
  para rondas futuras. Los 6 partidos de DESARROLLO con momios capturados en vivo (misma regla que
  `datos.momios_en_vivo`) quedan con `mercado_dudoso = 1` y el resto de `mercado_*` vacío.

**Calendario.** Las fechas de los partidos (jugados o programados) se toman como públicas de antemano: de ahí salen
el descanso, los partidos en 14 días y la hora local. `pendientes_previos_l/v > 0` avisa que el partido anterior del
equipo todavía no se conoce en el corte (hoy: Querétaro y Monterrey en la Jornada 17, porque su partido del 14-nov
está pendiente); en ese caso las suspensiones quedan vacías y la fila cambiará al actualizar.

**Lo que se estima, se estima sólo con el pasado**, y se refresca al conocerse el primer partido de cada torneo:

- Medias de la liga (goles, ventaja de local, frecuencias de resultado): ventanas móviles de 612 y 1530 partidos.
- Regresión de goles esperados: goles ~ b0 + b1·(tiros fuera de puerta) + b2·(tiros a puerta), mínimos cuadrados con
  las 1224 observaciones equipo-partido anteriores. En DESARROLLO b2 va de 0.25 a 0.30 goles por tiro a puerta y
  b1 de −0.06 a −0.04; hoy: 0.44 − 0.044·fuera + 0.305·a puerta.
- Credibilidad de la ventaja de local por (equipo, sede): K de Bühlmann-Straub = varianza dentro / varianza entre
  unidades, con todas las parejas (equipo, sede) de al menos 17 partidos. En DESARROLLO K va de 79 a 230 (mediana 114);
  hoy K = 100 (σ² = 2.51, τ² = 0.025, 36 unidades), es decir Z ≈ 0.30 con 85 partidos de local: **la ventaja propia
  de cada estadio existe pero es chica (τ ≈ 0.16 goles) y hay que encogerla mucho.**

**Convenciones fijadas de antemano** (constantes del módulo, no ajustadas con resultados): retraso de 3 h para dar
por conocido un partido; ventanas 5 y 10; vida media de 5 partidos en la forma exponencial; Elo con K = 20, ventaja
de local 70 y multiplicador por goles; K = 6 en el historial directo y K = 10 en el árbitro; titular habitual =
60% de titularidades en los últimos 10; altura = 1,800 m o más; topes de 30 días (descanso) y 10 días (diferencia).
Si alguien quiere afinarlas, debe hacerlo dentro del walk-forward y registrar la variante.

**Pruebas** (`python3 -m pytest modelo/pruebas/test_variables.py -q`):

1. 60 partidos al azar repartidos de 2010 a 2026: se recalcula con un historial **truncado físicamente** justo antes
   del partido (y el propio partido sin resultado, estadísticas, tarjetas ni alineación) y se exige igualdad
   **exacta** en las 299 variables no `_real`. 12 de los 60 recalculan toda la tabla truncada.
2. Lo mismo con el parámetro `hasta`, y con corte por bloque (sólo partidos que empezaron antes del corte).
3. Se alteran marcador, estadísticas, tarjetas y alineación del propio partido: ninguna variable no `_real` cambia
   (y las `_real` sí reaccionan).
4. Actualización incremental = reconstrucción completa (con copias de los datos en un directorio temporal).
5. Los pendientes tienen todas las variables disponibles; los vacíos son vacíos (mercado sin momios, árbitro sin
   designar, equipos sin historia, posesión antes de 2012, liguilla en fase regular...).
6. Definiciones reimplementadas con pandas (forma, racha, descanso, puntos de tabla); tabla de los pendientes igual a
   `tabla_apertura2026.csv`; banderas de clasificado/eliminado nunca contradicen lo que pasó; formato de torneos y
   ganador de series por regla contra los datos; sedes completas.

## 3. Lo que se encontró en los datos al construirlas

- **Los CSV cambiaron durante el trabajo** (se regeneraron a las 04:07 UTC con más historia): ahora hay estadísticas
  de 2004-2006 y desde 2008, posesión desde el Apertura 2012, alineaciones con 11 titulares válidos de forma estable
  desde 2013 (2008-2012: 27% a 74% de los equipos-partido) y amarillas con jugador desde el Apertura 2012 (antes sólo
  expulsiones). El módulo no fija fechas: usa lo que haya y deja vacío lo demás. La columna "Hay dato desde" de la
  sección 4 se calcula con los datos.
- **Tiros anteriores a 2010 no sirven para goles esperados**: con datos de 2004-2008 la pendiente de goles sobre
  tiros a puerta es ≈ 0 (b2 = −0.003 al inicio del Clausura 2008); desde 2010 es ≈ 0.28. No afecta a DESARROLLO.
- **Sedes**: ESPN usa 79 `estadio_id` para 34 inmuebles (el Jalisco tiene 4 ids, el Universitario 4, el
  Hidalgo 4...). `datos/estadios_sedes.csv` los une por sede física con coordenadas, altitud y superficie
  (confianza alta en 16, media en 17 y baja en 1). 221 partidos desde 2010 no tienen sede utilizable (213 sin estadio en ESPN: 153 del Apertura
  2012, 58 del Clausura 2020 y 2 sueltos; más 8 con sede errónea; 59 de los 221 caen en DESARROLLO): se imputa la
  sede habitual del local y se marca `sede_imputada`. Tres errores de ESPN corregidos en
  código: la vuelta de la final del Clausura 2017 (aparece en el Universitario; fue en el Estadio Chivas), 7 partidos
  de Necaxa 2010-11 etiquetados en el Nemesio Díez, y partidos de Chivas en el "Omnilife" antes de su apertura.
- **Reglas verificadas con los datos**: (a) el gol de visitante desempató cuartos y semifinales del Apertura 2012 al
  Clausura 2021 y después sólo la tabla; con esa regla el ganador calculado coincide con quien siguió vivo en 336 de
  las 337 series comprobables desde 2001 (la otra es una semifinal de 2007 con una pierna cancelada). (b) **La suspensión por 5 amarillas existe desde el Apertura 2021**: de los
  "suspendidos" que la regla habría dado entre 2013 y 2020, 78% jugó el partido siguiente (n = 471); desde el
  Apertura 2021, 1.1% (n = 180). (c) Zona de postemporada: 8 lugares hasta el Clausura 2020, 12 del Apertura 2020 al
  Clausura 2023, 10 del Apertura 2023 al Apertura 2025 y 8 desde el Clausura 2026. (d) Excepción real que la tabla
  no ve: Querétaro terminó 10.º en el Clausura 2023 y no jugó la reclasificación.
- **Suspendidos por expulsión**: 95.2% de los inferidos en DESARROLLO no jugó el partido siguiente (n = 994); el 4.8%
  restante puede deberse a castigos revocados o a tarjetas mal registradas (no se verificó). La regla da por cumplido el castigo en un partido (las
  sanciones de varios partidos no se ven en los datos).
- **Once previsto**: el once del partido anterior menos suspendidos acierta en promedio 79% del once real (8.7 de 11).
  En un partido típico faltan 1.2 titulares habituales "previsibles" y terminan faltando 2.6.
- **Dos finales sin desempate en los datos**: Clausura 2009 se resuelve con el marcador de 120 minutos; Clausura 2004
  (penales que ESPN no trae) se fija a mano (`GANADOR_MANUAL`).
- **León está justo en 1,800 m** (±10 m): "altura" se definió como 1,800 m o más para que quede dentro. Sedes de
  altura hoy: Toluca 2,680, Pachuca 2,385, CU 2,290, Banorte 2,240, Puebla 2,225, Aguascalientes 1,885,
  Querétaro 1,870, San Luis 1,860 y León 1,800.

Así quedan hoy algunos datos de los 10 pendientes (corte por partido):

| local | visitante | elo_dif | tabla_pos_l | tabla_pos_v | forma10_ppp_dif | descanso_l | descanso_v | sede_alt_dif_v | sede_viaje_km_v | susp_n_l | susp_n_v | aus_tit_previa_l | aus_tit_previa_v | pendientes_previos_l | pendientes_previos_v |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Querétaro | Monterrey | -66.93 | 12 | 10 | 0.10 | 5.96 | 6.92 | 1375 | 566.30 | 1 | 1 | 1 | 1 | 0 | 0 |
| Puebla | Atlético San Luis | -79.52 | 13 | 14 | -0.40 | 12.04 | 14 | 365 | 447.11 | 0 | 0 | 0 | 0 | 0 | 0 |
| Tijuana | Atlante | 188.64 | 9 | 16 | 0.10 | 14.08 | 14 | -2175 | 2304.61 | 0 | 2 | 0 | 3 | 0 | 0 |
| Juárez | Atlas | -74.26 | 18 | 5 | -0.40 | 14.08 | 13.17 | -405 | 1267.58 | 0 | 1 | 0 | 3 | 0 | 0 |
| Pachuca | Toluca | -65.04 | 8 | 4 | 0.30 | 13.99 | 13.91 | -295 | 131.74 | 0 | 1 | 0 | 3 | 0 | 0 |
| Santos | León | -42.86 | 6 | 7 | 1.10 | 14.83 | 12.87 | -680 | 531.72 | 0 | 2 | 2 | 2 | 0 | 0 |
| Pumas | Monterrey | 37.25 | 11 | 10 | 0.10 | 13.91 | 7.08 | 1795 | 712.91 | 1 |  | 1 |  | 0 | 1 |
| Tigres | América | -114.02 | 15 | 2 | -0.40 | 14.08 | 13.99 | -1720 | 723.70 | 0 | 1 | 1 | 2 | 0 | 0 |
| Chivas | Cruz Azul | -74.27 | 3 | 1 | -0.40 | 13.87 | 14.92 | -570 | 475.93 | 0 | 0 | 0 | 1 | 0 | 0 |
| Querétaro | Necaxa | 42.18 | 12 | 17 | 0.70 | 8.08 | 16 | -15 | 245.25 |  | 1 |  | 1 | 1 | 0 |

## 4. Tabla de variables

"Hay dato desde" = primer torneo a partir del cual la variable tiene valor en al menos 80% de los partidos jugados de
todos los torneos siguientes ("parcial" = sólo aplica a un subconjunto, p. ej. liguilla). "Cobertura en DESARROLLO"
= proporción de partidos de DESARROLLO con valor.

| Variable | Grupo | Definición | Hay dato desde | Cobertura en DESARROLLO | Disponible al pronosticar |
|---|---|---|---|---:|---|
| `elo_l` | 0) fuerza base | Elo simple previo al partido (K=20, multiplicador por diferencia de goles, ventaja de local 70 sólo al actualizar; equipos de 2001 en 1500, nuevos en 1450). Sólo referencia: las familias de modelos tienen mejores fuerzas | Clausura 2010 | 100% | sí |
| `elo_v` | 0) fuerza base | Elo simple previo al partido (K=20, multiplicador por diferencia de goles, ventaja de local 70 sólo al actualizar; equipos de 2001 en 1500, nuevos en 1450). Sólo referencia: las familias de modelos tienen mejores fuerzas | Clausura 2010 | 100% | sí |
| `elo_dif` | 0) fuerza base | Elo simple previo al partido (K=20, multiplicador por diferencia de goles, ventaja de local 70 sólo al actualizar; equipos de 2001 en 1500, nuevos en 1450). Sólo referencia: las familias de modelos tienen mejores fuerzas | Clausura 2010 | 100% | sí |
| `liga_goles` | 0) fuerza base | goles por partido de la liga, últimos 612 partidos de fase regular | Clausura 2010 | 100% | sí |
| `liga_vl` | 0) fuerza base | ventaja de local de la liga en goles (local - visita por partido), últimos 1530 de fase regular | Clausura 2010 | 100% | sí |
| `liga_p_local` | 0) fuerza base | frecuencia de victoria local, últimos 1530 de fase regular | Clausura 2010 | 100% | sí |
| `liga_p_empate` | 0) fuerza base | frecuencia de empate, últimos 1530 de fase regular | Clausura 2010 | 100% | sí |
| `forma5_ppp_l` | a) forma | puntos por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_ppp_v` | a) forma | puntos por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_ppp_dif` | a) forma | puntos por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_ppp_l` | a) forma | puntos por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_ppp_v` | a) forma | puntos por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_gf_l` | a) forma | goles a favor por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_gf_v` | a) forma | goles a favor por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_gf_l` | a) forma | goles a favor por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_gf_v` | a) forma | goles a favor por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_gc_l` | a) forma | goles en contra por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_gc_v` | a) forma | goles en contra por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_gc_l` | a) forma | goles en contra por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_gc_v` | a) forma | goles en contra por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_dg_l` | a) forma | diferencia de goles por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_dg_v` | a) forma | diferencia de goles por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_dg_dif` | a) forma | diferencia de goles por partido, últimos 5 partidos de liga del equipo (cualquier fase y torneo; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_dg_l` | a) forma | diferencia de goles por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma5_cond_dg_v` | a) forma | diferencia de goles por partido, últimos 5 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 3) | Clausura 2010 | 100% | sí |
| `forma10_ppp_l` | a) forma | puntos por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_ppp_v` | a) forma | puntos por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_ppp_dif` | a) forma | puntos por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_ppp_l` | a) forma | puntos por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_ppp_v` | a) forma | puntos por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_ppp_dif` | a) forma | puntos por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_gf_l` | a) forma | goles a favor por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_gf_v` | a) forma | goles a favor por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_cond_gf_l` | a) forma | goles a favor por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_gf_v` | a) forma | goles a favor por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_gc_l` | a) forma | goles en contra por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_gc_v` | a) forma | goles en contra por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_cond_gc_l` | a) forma | goles en contra por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_gc_v` | a) forma | goles en contra por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_dg_l` | a) forma | diferencia de goles por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_dg_v` | a) forma | diferencia de goles por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 100% | sí |
| `forma10_dg_dif` | a) forma | diferencia de goles por partido, últimos 10 partidos de liga del equipo (cualquier fase y torneo; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_dg_l` | a) forma | diferencia de goles por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_dg_v` | a) forma | diferencia de goles por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `forma10_cond_dg_dif` | a) forma | diferencia de goles por partido, últimos 10 partidos EN SU CONDICIÓN (el local sólo de local, el visitante sólo de visita; mínimo 5) | Clausura 2010 | 99% | sí |
| `formaexp_ppp_l` | a) forma | puntos por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_ppp_v` | a) forma | puntos por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_ppp_dif` | a) forma | puntos por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_ppp_l` | a) forma | puntos por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_ppp_v` | a) forma | puntos por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_gf_l` | a) forma | goles a favor por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_gf_v` | a) forma | goles a favor por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_gf_l` | a) forma | goles a favor por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_gf_v` | a) forma | goles a favor por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_gc_l` | a) forma | goles en contra por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_gc_v` | a) forma | goles en contra por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_gc_l` | a) forma | goles en contra por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_gc_v` | a) forma | goles en contra por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_dg_l` | a) forma | diferencia de goles por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_dg_v` | a) forma | diferencia de goles por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_dg_dif` | a) forma | diferencia de goles por partido con peso exponencial (vida media 5 partidos, últimos 30; mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_dg_l` | a) forma | diferencia de goles por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `formaexp_cond_dg_v` | a) forma | diferencia de goles por partido con peso exponencial, sólo partidos en su condición (mínimo 3) | Clausura 2010 | 100% | sí |
| `torneo_pj_l` | a) forma | partidos jugados en el torneo en curso (todas las fases) | Clausura 2010 | 100% | sí |
| `torneo_pj_v` | a) forma | partidos jugados en el torneo en curso (todas las fases) | Clausura 2010 | 100% | sí |
| `torneo_ppp_l` | a) forma | puntos por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_ppp_v` | a) forma | puntos por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_ppp_dif` | a) forma | puntos por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 94% | sí |
| `torneo_gf_l` | a) forma | goles a favor por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_gf_v` | a) forma | goles a favor por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_gc_l` | a) forma | goles en contra por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_gc_v` | a) forma | goles en contra por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_dg_l` | a) forma | diferencia de goles por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_dg_v` | a) forma | diferencia de goles por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 95% | sí |
| `torneo_dg_dif` | a) forma | diferencia de goles por partido en el torneo en curso (todas las fases; vacío sin partidos) | Clausura 2010 | 94% | sí |
| `racha_vict_l` | b) rachas | racha vigente: victorias consecutivas (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_vict_v` | b) rachas | racha vigente: victorias consecutivas (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_vict_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): victorias consecutivas | Clausura 2010 | 100% | sí |
| `racha_cond_vict_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): victorias consecutivas | Clausura 2010 | 100% | sí |
| `racha_inv_l` | b) rachas | racha vigente: partidos sin perder (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_inv_v` | b) rachas | racha vigente: partidos sin perder (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_inv_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos sin perder | Clausura 2010 | 100% | sí |
| `racha_cond_inv_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos sin perder | Clausura 2010 | 100% | sí |
| `racha_singanar_l` | b) rachas | racha vigente: partidos sin ganar (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_singanar_v` | b) rachas | racha vigente: partidos sin ganar (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_singanar_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos sin ganar | Clausura 2010 | 100% | sí |
| `racha_cond_singanar_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos sin ganar | Clausura 2010 | 100% | sí |
| `racha_derr_l` | b) rachas | racha vigente: derrotas consecutivas (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_derr_v` | b) rachas | racha vigente: derrotas consecutivas (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_derr_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): derrotas consecutivas | Clausura 2010 | 100% | sí |
| `racha_cond_derr_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): derrotas consecutivas | Clausura 2010 | 100% | sí |
| `racha_anot_l` | b) rachas | racha vigente: partidos anotando (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_anot_v` | b) rachas | racha vigente: partidos anotando (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_anot_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos anotando | Clausura 2010 | 100% | sí |
| `racha_cond_anot_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos anotando | Clausura 2010 | 100% | sí |
| `racha_sinanot_l` | b) rachas | racha vigente: partidos sin anotar (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_sinanot_v` | b) rachas | racha vigente: partidos sin anotar (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_sinanot_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos sin anotar | Clausura 2010 | 100% | sí |
| `racha_cond_sinanot_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos sin anotar | Clausura 2010 | 100% | sí |
| `racha_cero_l` | b) rachas | racha vigente: partidos con portería en cero (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cero_v` | b) rachas | racha vigente: partidos con portería en cero (todos los partidos de liga, cruza torneos; tope 60) | Clausura 2010 | 100% | sí |
| `racha_cond_cero_l` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos con portería en cero | Clausura 2010 | 100% | sí |
| `racha_cond_cero_v` | b) rachas | racha vigente en su condición (local en casa / visitante fuera): partidos con portería en cero | Clausura 2010 | 100% | sí |
| `tabla_pos_l` | c) tabla | posición en la tabla general del torneo antes del partido (puntos, DG, GF, nombre; vacío sin partidos). En liguilla es la tabla final (= sembrado) | Clausura 2010 | 95% | sí |
| `tabla_pos_v` | c) tabla | posición en la tabla general del torneo antes del partido (puntos, DG, GF, nombre; vacío sin partidos). En liguilla es la tabla final (= sembrado) | Clausura 2010 | 95% | sí |
| `tabla_pos_dif` | c) tabla | posición en la tabla general del torneo antes del partido (puntos, DG, GF, nombre; vacío sin partidos). En liguilla es la tabla final (= sembrado) | Clausura 2010 | 94% | sí |
| `tabla_pj_l` | c) tabla | partidos de fase regular jugados en el torneo | Clausura 2010 | 100% | sí |
| `tabla_pj_v` | c) tabla | partidos de fase regular jugados en el torneo | Clausura 2010 | 100% | sí |
| `tabla_pts_l` | c) tabla | puntos en la fase regular del torneo | Clausura 2010 | 100% | sí |
| `tabla_pts_v` | c) tabla | puntos en la fase regular del torneo | Clausura 2010 | 100% | sí |
| `tabla_ppp_l` | c) tabla | puntos por partido en la fase regular del torneo | Clausura 2010 | 95% | sí |
| `tabla_ppp_v` | c) tabla | puntos por partido en la fase regular del torneo | Clausura 2010 | 95% | sí |
| `tabla_ppp_dif` | c) tabla | puntos por partido en la fase regular del torneo | Clausura 2010 | 94% | sí |
| `tabla_dgpp_l` | c) tabla | diferencia de goles por partido en la fase regular del torneo | Clausura 2010 | 95% | sí |
| `tabla_dgpp_v` | c) tabla | diferencia de goles por partido en la fase regular del torneo | Clausura 2010 | 95% | sí |
| `tabla_dist8_l` | c) tabla | puntos propios menos puntos del 8.º lugar (positivo = arriba del 8.º) | Clausura 2010 | 95% | sí |
| `tabla_dist8_v` | c) tabla | puntos propios menos puntos del 8.º lugar (positivo = arriba del 8.º) | Clausura 2010 | 95% | sí |
| `tabla_dist_zona_l` | c) tabla | puntos propios menos puntos del último lugar con postemporada según el formato del torneo (8, 12 o 10) | Clausura 2010 | 95% | sí |
| `tabla_dist_zona_v` | c) tabla | puntos propios menos puntos del último lugar con postemporada según el formato del torneo (8, 12 o 10) | Clausura 2010 | 95% | sí |
| `tabla_rest_l` | c) tabla | partidos de fase regular que le faltan al equipo (según reglamento) | Clausura 2010 | 100% | sí |
| `tabla_rest_v` | c) tabla | partidos de fase regular que le faltan al equipo (según reglamento) | Clausura 2010 | 100% | sí |
| `tabla_clasificado_l` | c) tabla | 1 si ya tiene asegurada la postemporada: menos equipos que lugares pueden igualarlo o pasarlo (conservador: los empates cuentan en contra) | Clausura 2010 | 100% | sí |
| `tabla_clasificado_v` | c) tabla | 1 si ya tiene asegurada la postemporada: menos equipos que lugares pueden igualarlo o pasarlo (conservador: los empates cuentan en contra) | Clausura 2010 | 100% | sí |
| `tabla_eliminado_l` | c) tabla | 1 si ya no alcanza la zona: tantos equipos como lugares ya tienen más puntos que su máximo posible (conservador) | Clausura 2010 | 100% | sí |
| `tabla_eliminado_v` | c) tabla | 1 si ya no alcanza la zona: tantos equipos como lugares ya tienen más puntos que su máximo posible (conservador) | Clausura 2010 | 100% | sí |
| `jornada_est` | c) tabla | jornada estimada: promedio de partidos jugados de ambos + 1 (vacío en liguilla) | Clausura 2010 | 91% | sí |
| `avance_torneo` | c) tabla | fracción de la fase regular ya jugada por ambos (1 en liguilla) | Clausura 2010 | 100% | sí |
| `descanso_l` | d) calendario | días desde el partido de liga anterior del equipo (calendario; tope 30). No ve copas ni torneos internacionales | Clausura 2010 | 100% | sí |
| `descanso_v` | d) calendario | días desde el partido de liga anterior del equipo (calendario; tope 30). No ve copas ni torneos internacionales | Clausura 2010 | 100% | sí |
| `descanso_dif` | d) calendario | diferencia de descanso local - visitante, cada uno con tope de 10 días | Clausura 2010 | 100% | sí |
| `pj14_l` | d) calendario | partidos de liga del equipo en los 14 días previos (calendario) | Clausura 2010 | 100% | sí |
| `pj14_v` | d) calendario | partidos de liga del equipo en los 14 días previos (calendario) | Clausura 2010 | 100% | sí |
| `pj14_dif` | d) calendario | partidos de liga del equipo en los 14 días previos (calendario) | Clausura 2010 | 100% | sí |
| `pausa_larga_l` | d) calendario | 1 si descansó más de 10 días dentro del mismo torneo | Clausura 2010 | 100% | sí |
| `pausa_larga_v` | d) calendario | 1 si descansó más de 10 días dentro del mismo torneo | Clausura 2010 | 100% | sí |
| `regreso_pausa` | d) calendario | 1 si AMBOS vienen de más de 10 días sin jugar dentro del torneo (regreso de fecha FIFA u otra pausa) | Clausura 2010 | 100% | sí |
| `primer_partido_torneo_l` | d) calendario | 1 si es el primer partido del equipo en el torneo | Clausura 2010 | 100% | sí |
| `primer_partido_torneo_v` | d) calendario | 1 si es el primer partido del equipo en el torneo | Clausura 2010 | 100% | sí |
| `pendientes_previos_l` | d) calendario | partidos del equipo anteriores a éste que aún no se conocen en el corte (programados o del mismo bloque): si > 0 la fila cambiará | Clausura 2010 | 100% | sí |
| `pendientes_previos_v` | d) calendario | partidos del equipo anteriores a éste que aún no se conocen en el corte (programados o del mismo bloque): si > 0 la fila cambiará | Clausura 2010 | 100% | sí |
| `media_semana` | d) calendario | 1 si se juega martes, miércoles o jueves (hora local) | Clausura 2010 | 100% | sí |
| `dia_semana` | d) calendario | día de la semana local (0 = lunes ... 6 = domingo) | Clausura 2010 | 100% | sí |
| `hora_local` | d) calendario | hora local de inicio en decimal (19.5 = 19:30) | Clausura 2010 | 100% | sí |
| `mes` | d) calendario | mes local del partido | Clausura 2010 | 100% | sí |
| `sede_altitud` | e) sede | altitud de la sede en metros (datos/estadios_sedes.csv) | Clausura 2010 | 100% | sí |
| `sede_altura` | e) sede | 1 si la sede está a 1800 m o más | Clausura 2010 | 100% | sí |
| `sede_sintetico` | e) sede | 1 si la cancha era de pasto sintético en esa fecha | Clausura 2010 | 100% | sí |
| `sede_imputada` | e) sede | 1 si ESPN no trae estadio y se supuso la sede habitual del local | Clausura 2010 | 100% | sí |
| `sede_habitual_l` | e) sede | 1 si el local juega en su sede habitual (la más frecuente en sus últimos 6 partidos de local del último año); 0 en mudanzas y sedes prestadas | Clausura 2010 | 100% | sí |
| `sede_compartida` | e) sede | 1 si la sede es también la habitual de otro equipo activo (inmueble compartido) | Clausura 2010 | 100% | sí |
| `sede_tambien_v` | e) sede | 1 si la sede es también la habitual del visitante (clásico en casa compartida) | Clausura 2010 | 100% | sí |
| `sede_alt_dif_v` | e) sede | altitud de la sede menos altitud de la sede habitual del visitante (m) | Clausura 2010 | 100% | sí |
| `sede_viaje_km_v` | e) sede | kilómetros (haversine) entre la sede habitual del visitante y esta sede | Clausura 2010 | 100% | sí |
| `sede_viaje_km_l` | e) sede | kilómetros entre la sede habitual del local y esta sede (0 si juega en casa) | Clausura 2010 | 100% | sí |
| `sede_n_l` | e) sede | partidos previos del local, como local, en esta sede (desde 2001) | Clausura 2010 | 100% | sí |
| `sede_vl_l` | e) sede | ventaja de local del equipo EN ESTA SEDE en goles, con credibilidad: liga_vl + Z*(D - 2*liga_vl), donde D = DG por partido de local aquí (últimos 85) menos su DG por partido de visita en el mismo lapso y Z = m/(m+K), m = n_l*n_v/(n_l+n_v); K es de Bühlmann-Straub y se reestima al inicio de cada torneo sólo con el pasado | Clausura 2010 | 100% | sí |
| `sede_vl_rel_l` | e) sede | exceso de esa ventaja sobre la media de la liga: Z*(D - 2*liga_vl) | Clausura 2010 | 100% | sí |
| `sede_vl_z_l` | e) sede | credibilidad Z usada en sede_vl_l (0 = sin historia o sin varianza entre sedes) | Clausura 2010 | 100% | sí |
| `visita_altura_n_v` | e) sede | visitas previas del visitante a sedes de 1800 m o más (últimas 20) | Clausura 2010 | 100% | sí |
| `visita_altura_dg_v` | e) sede | DG por partido del visitante en esas visitas a la altura (mínimo 3) | Clausura 2010 | 99% | sí |
| `visita_altura_rel_v` | e) sede | esa DG menos su DG por partido en sus últimas 40 visitas a sedes bajas (mínimo 3 y 3) | Clausura 2010 | 99% | sí |
| `visita_sint_n_v` | e) sede | visitas previas del visitante a canchas sintéticas (últimas 10) | Clausura 2010 | 100% | sí |
| `visita_sint_dg_v` | e) sede | DG por partido del visitante en canchas sintéticas (mínimo 3) | Apertura 2022 | 88% | sí |
| `visita_sint_rel_v` | e) sede | esa DG menos su DG por partido en sus últimas 40 visitas a pasto natural | Apertura 2022 | 88% | sí |
| `h2h_n` | f) h2h | enfrentamientos previos entre los dos equipos en la base (desde 2001) | Clausura 2010 | 100% | sí |
| `h2h6_pts_l` | f) h2h | últimos 6 enfrentamientos: puntos por partido del local actual MENOS lo esperado por jugar en casa o fuera (medias de la liga), encogido por credibilidad Z = n/(n+6) hacia 0 | Clausura 2010 | 98% | sí |
| `h2h6_dg_l` | f) h2h | últimos 6: diferencia de goles por partido del local actual menos la ventaja de local de la liga (con su signo), encogida igual | Clausura 2010 | 98% | sí |
| `h2h10_pts_l` | f) h2h | igual que h2h6_pts_l con los últimos 10 | Clausura 2010 | 98% | sí |
| `h2h10_dg_l` | f) h2h | igual que h2h6_dg_l con los últimos 10 | Clausura 2010 | 98% | sí |
| `h2h_sede_n` | f) h2h | enfrentamientos previos con el local actual de local EN ESTA SEDE (se usan los últimos 6) | Clausura 2010 | 100% | sí |
| `h2h_sede_pts_l` | f) h2h | esos partidos: puntos por partido del local menos lo esperado en casa, encogido por credibilidad | Apertura 2020 | 93% | sí |
| `h2h_sede_dg_l` | f) h2h | esos partidos: DG por partido del local menos la ventaja de local de la liga, encogida | Apertura 2020 | 93% | sí |
| `h2h_lig_n` | f) h2h | partidos de liguilla previos entre ambos (se usan los últimos 10) | Clausura 2010 | 100% | sí |
| `h2h_lig_pts_l` | f) h2h | liguilla: puntos por partido del local actual menos lo esperado, encogido | Clausura 2010 (parcial) | 57% | sí |
| `h2h_lig_dg_l` | f) h2h | liguilla: DG por partido del local actual ajustada por localía, encogida | Clausura 2010 (parcial) | 57% | sí |
| `h2h_lig_series_n` | f) h2h | series de liguilla previas entre ambos (desde 2001) | Clausura 2010 | 100% | sí |
| `h2h_lig_series_bal_l` | f) h2h | series de liguilla ganadas por el local actual menos las ganadas por el visitante | Clausura 2010 | 100% | sí |
| `h2h_final_n` | f) h2h | partidos de FINAL previos entre ambos | Clausura 2010 | 100% | sí |
| `h2h_final_dg_l` | f) h2h | finales: DG por partido del local actual ajustada por localía, encogida | Clausura 2010 (parcial) | 21% | sí |
| `h2h_final_series_n` | f) h2h | finales previas entre ambos | Clausura 2010 | 100% | sí |
| `h2h_final_series_bal_l` | f) h2h | finales ganadas por el local actual menos las ganadas por el visitante (dominio en finales) | Clausura 2010 | 100% | sí |
| `juego10_tiros_f_l` | g) juego | media de tiros totales a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tiros_f_v` | g) juego | media de tiros totales a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tiros_c_l` | g) juego | media de tiros totales en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tiros_c_v` | g) juego | media de tiros totales en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tp_f_l` | g) juego | media de tiros a puerta a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tp_f_v` | g) juego | media de tiros a puerta a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tp_c_l` | g) juego | media de tiros a puerta en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_tp_c_v` | g) juego | media de tiros a puerta en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_corners_f_l` | g) juego | media de tiros de esquina a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_corners_f_v` | g) juego | media de tiros de esquina a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_corners_c_l` | g) juego | media de tiros de esquina en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_corners_c_v` | g) juego | media de tiros de esquina en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_faltas_f_l` | g) juego | media de faltas cometidas a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_faltas_f_v` | g) juego | media de faltas cometidas a favor en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_faltas_c_l` | g) juego | media de faltas cometidas en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_faltas_c_v` | g) juego | media de faltas cometidas en contra en los últimos 10 partidos con estadísticas (mínimo 5) | Clausura 2010 | 99% | sí |
| `juego10_xg_f_l` | g) juego | media de goles esperados aproximados a favor en los últimos 10 partidos con estadísticas (mínimo 5) (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de cada torneo con las 1224 observaciones equipo-partido anteriores) | Clausura 2010 | 99% | sí |
| `juego10_xg_f_v` | g) juego | media de goles esperados aproximados a favor en los últimos 10 partidos con estadísticas (mínimo 5) (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de cada torneo con las 1224 observaciones equipo-partido anteriores) | Clausura 2010 | 99% | sí |
| `juego10_xg_f_dif` | g) juego | media de goles esperados aproximados a favor en los últimos 10 partidos con estadísticas (mínimo 5) (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de cada torneo con las 1224 observaciones equipo-partido anteriores) | Clausura 2010 | 97% | sí |
| `juego10_xg_c_l` | g) juego | media de goles esperados aproximados en contra en los últimos 10 partidos con estadísticas (mínimo 5) (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de cada torneo con las 1224 observaciones equipo-partido anteriores) | Clausura 2010 | 99% | sí |
| `juego10_xg_c_v` | g) juego | media de goles esperados aproximados en contra en los últimos 10 partidos con estadísticas (mínimo 5) (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de cada torneo con las 1224 observaciones equipo-partido anteriores) | Clausura 2010 | 99% | sí |
| `juego10_xg_c_dif` | g) juego | media de goles esperados aproximados en contra en los últimos 10 partidos con estadísticas (mínimo 5) (regresión lineal de goles sobre tiros fuera de puerta y tiros a puerta, ajustada al inicio de cada torneo con las 1224 observaciones equipo-partido anteriores) | Clausura 2010 | 97% | sí |
| `juego5_tiros_f_l` | g) juego | media de tiros totales a favor en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tiros_f_v` | g) juego | media de tiros totales a favor en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tiros_c_l` | g) juego | media de tiros totales en contra en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tiros_c_v` | g) juego | media de tiros totales en contra en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tp_f_l` | g) juego | media de tiros a puerta a favor en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tp_f_v` | g) juego | media de tiros a puerta a favor en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tp_c_l` | g) juego | media de tiros a puerta en contra en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_tp_c_v` | g) juego | media de tiros a puerta en contra en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_xg_f_l` | g) juego | media de goles esperados aproximados a favor en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_xg_f_v` | g) juego | media de goles esperados aproximados a favor en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_xg_c_l` | g) juego | media de goles esperados aproximados en contra en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego5_xg_c_v` | g) juego | media de goles esperados aproximados en contra en los últimos 5 partidos con estadísticas (mínimo 3) | Clausura 2010 | 99% | sí |
| `juego10_posesion_l` | g) juego | posesión media (%) en los últimos 10 partidos con estadísticas (mínimo 3 con dato) | Apertura 2012 | 99% | sí |
| `juego10_posesion_v` | g) juego | posesión media (%) en los últimos 10 partidos con estadísticas (mínimo 3 con dato) | Apertura 2012 | 99% | sí |
| `juego10_posesion_dif` | g) juego | posesión media (%) en los últimos 10 partidos con estadísticas (mínimo 3 con dato) | Apertura 2012 | 97% | sí |
| `juego10_amarillas_l` | g) juego | amarillas propias por partido, últimos 10 con estadísticas | Clausura 2010 | 99% | sí |
| `juego10_amarillas_v` | g) juego | amarillas propias por partido, últimos 10 con estadísticas | Clausura 2010 | 99% | sí |
| `juego10_xgdif_l` | g) juego | goles esperados a favor menos en contra, últimos 10 con estadísticas | Clausura 2010 | 99% | sí |
| `juego10_xgdif_v` | g) juego | goles esperados a favor menos en contra, últimos 10 con estadísticas | Clausura 2010 | 99% | sí |
| `juego10_xgdif_dif` | g) juego | goles esperados a favor menos en contra, últimos 10 con estadísticas | Clausura 2010 | 97% | sí |
| `juego10_suerte_f_l` | g) juego | goles reales menos esperados A FAVOR por partido, últimos 10 (definición/suerte) | Clausura 2010 | 99% | sí |
| `juego10_suerte_f_v` | g) juego | goles reales menos esperados A FAVOR por partido, últimos 10 (definición/suerte) | Clausura 2010 | 99% | sí |
| `juego10_suerte_c_l` | g) juego | goles reales menos esperados EN CONTRA por partido, últimos 10 (portero/suerte) | Clausura 2010 | 99% | sí |
| `juego10_suerte_c_v` | g) juego | goles reales menos esperados EN CONTRA por partido, últimos 10 (portero/suerte) | Clausura 2010 | 99% | sí |
| `juego_n_l` | g) juego | partidos con estadísticas disponibles entre los últimos 20 (máximo 10) | Clausura 2010 | 100% | sí |
| `juego_n_v` | g) juego | partidos con estadísticas disponibles entre los últimos 20 (máximo 10) | Clausura 2010 | 100% | sí |
| `rojas_prev_l` | h) disciplina | expulsados del equipo en su partido anterior (tarjetas.csv; 0 si fue hace más de 90 días; vacío si ese partido aún no se conoce, pendientes_previos > 0) | Clausura 2010 | 100% | sí |
| `rojas_prev_v` | h) disciplina | expulsados del equipo en su partido anterior (tarjetas.csv; 0 si fue hace más de 90 días; vacío si ese partido aún no se conoce, pendientes_previos > 0) | Clausura 2010 | 100% | sí |
| `susp_n_l` | h) disciplina | jugadores SUSPENDIDOS para este partido deducidos de tarjetas: expulsado en el partido anterior o, desde el Apertura 2021 (cuando empezó esa regla), amarilla múltiplo de 5 acumulada en el torneo (cuenta aparte en liguilla). Vacío si el partido anterior aún no se conoce | Clausura 2010 | 100% | sí |
| `susp_n_v` | h) disciplina | jugadores SUSPENDIDOS para este partido deducidos de tarjetas: expulsado en el partido anterior o, desde el Apertura 2021 (cuando empezó esa regla), amarilla múltiplo de 5 acumulada en el torneo (cuenta aparte en liguilla). Vacío si el partido anterior aún no se conoce | Clausura 2010 | 100% | sí |
| `susp_n_dif` | h) disciplina | jugadores SUSPENDIDOS para este partido deducidos de tarjetas: expulsado en el partido anterior o, desde el Apertura 2021 (cuando empezó esa regla), amarilla múltiplo de 5 acumulada en el torneo (cuenta aparte en liguilla). Vacío si el partido anterior aún no se conoce | Clausura 2010 | 100% | sí |
| `susp_imp_l` | h) disciplina | importancia de los suspendidos: suma de su proporción de titularidades en los últimos 10 partidos del equipo con once válido | Clausura 2010 | 100% | sí |
| `susp_imp_v` | h) disciplina | importancia de los suspendidos: suma de su proporción de titularidades en los últimos 10 partidos del equipo con once válido | Clausura 2010 | 100% | sí |
| `susp_imp_dif` | h) disciplina | importancia de los suspendidos: suma de su proporción de titularidades en los últimos 10 partidos del equipo con once válido | Clausura 2012 | 100% | sí |
| `susp_titulares_l` | h) disciplina | suspendidos que son titulares habituales (>= 60% de titularidades) | Clausura 2010 | 100% | sí |
| `susp_titulares_v` | h) disciplina | suspendidos que son titulares habituales (>= 60% de titularidades) | Clausura 2010 | 100% | sí |
| `aus_conv_n_l` | h) disciplina | titulares habituales que NO estuvieron en la lista (once + banca) del partido anterior: indicio de lesión, salida o castigo | Apertura 2012 | 99% | sí |
| `aus_conv_n_v` | h) disciplina | titulares habituales que NO estuvieron en la lista (once + banca) del partido anterior: indicio de lesión, salida o castigo | Apertura 2012 | 99% | sí |
| `aus_conv_imp_l` | h) disciplina | suma de la proporción de titularidades de esos ausentes | Apertura 2012 | 99% | sí |
| `aus_conv_imp_v` | h) disciplina | suma de la proporción de titularidades de esos ausentes | Apertura 2012 | 99% | sí |
| `aus_tit_previa_l` | h) disciplina | titulares habituales ausentes previsibles: suspendidos o fuera de la lista anterior (unión). Vacío si el partido anterior aún no se conoce | Apertura 2012 | 99% | sí |
| `aus_tit_previa_v` | h) disciplina | titulares habituales ausentes previsibles: suspendidos o fuera de la lista anterior (unión). Vacío si el partido anterior aún no se conoce | Apertura 2012 | 99% | sí |
| `aus_tit_previa_dif` | h) disciplina | titulares habituales ausentes previsibles: suspendidos o fuera de la lista anterior (unión). Vacío si el partido anterior aún no se conoce | Apertura 2012 | 98% | sí |
| `once_previa_hab_l` | i) alineación | continuidad del once PREVISTO (once del último partido conocido menos suspendidos): suma de sus proporciones de titularidad en los últimos 10 partidos, entre 11 (1 = repite el once de siempre) | Apertura 2012 | 99% | sí |
| `once_previa_hab_v` | i) alineación | continuidad del once PREVISTO (once del último partido conocido menos suspendidos): suma de sus proporciones de titularidad en los últimos 10 partidos, entre 11 (1 = repite el once de siempre) | Apertura 2012 | 99% | sí |
| `once_previa_hab_dif` | i) alineación | continuidad del once PREVISTO (once del último partido conocido menos suspendidos): suma de sus proporciones de titularidad en los últimos 10 partidos, entre 11 (1 = repite el once de siempre) | Apertura 2012 | 99% | sí |
| `once_previa_cambios_l` | i) alineación | cambios entre los dos últimos onces del equipo (0 a 11) | Clausura 2010 | 100% | sí |
| `once_previa_cambios_v` | i) alineación | cambios entre los dos últimos onces del equipo (0 a 11) | Clausura 2010 | 100% | sí |
| `once_previa_rot5_l` | i) alineación | rotación reciente: jugadores distintos usados como titulares en los últimos 5 partidos (11 a 55) | Apertura 2012 | 100% | sí |
| `once_previa_rot5_v` | i) alineación | rotación reciente: jugadores distintos usados como titulares en los últimos 5 partidos (11 a 55) | Apertura 2012 | 100% | sí |
| `once_real_hab_l` | i) alineación | NO DISPONIBLE AL PRONOSTICAR: proporción media de titularidades (últimos 10) del once que SÍ jugó este partido | Apertura 2012 | 99% | NO (_real) |
| `once_real_hab_v` | i) alineación | NO DISPONIBLE AL PRONOSTICAR: proporción media de titularidades (últimos 10) del once que SÍ jugó este partido | Apertura 2012 | 99% | NO (_real) |
| `once_real_hab_dif` | i) alineación | NO DISPONIBLE AL PRONOSTICAR: proporción media de titularidades (últimos 10) del once que SÍ jugó este partido | Apertura 2012 | 99% | NO (_real) |
| `once_real_cambios_l` | i) alineación | NO DISPONIBLE: cambios del once que jugó respecto del once anterior | Apertura 2012 | 100% | NO (_real) |
| `once_real_cambios_v` | i) alineación | NO DISPONIBLE: cambios del once que jugó respecto del once anterior | Apertura 2012 | 100% | NO (_real) |
| `once_real_aus_l` | i) alineación | NO DISPONIBLE: titulares habituales que no salieron de inicio en este partido | Apertura 2012 | 99% | NO (_real) |
| `once_real_aus_v` | i) alineación | NO DISPONIBLE: titulares habituales que no salieron de inicio en este partido | Apertura 2012 | 99% | NO (_real) |
| `once_real_aus_dif` | i) alineación | NO DISPONIBLE: titulares habituales que no salieron de inicio en este partido | Apertura 2012 | 99% | NO (_real) |
| `once_real_acierto_previa_l` | i) alineación | NO DISPONIBLE: fracción del once previsto que efectivamente fue titular (mide la calidad de la versión previa) | Apertura 2012 | 99% | NO (_real) |
| `once_real_acierto_previa_v` | i) alineación | NO DISPONIBLE: fracción del once previsto que efectivamente fue titular (mide la calidad de la versión previa) | Apertura 2012 | 99% | NO (_real) |
| `es_liguilla` | j) fase | 1 si no es fase regular (repechaje, cuartos, semifinal o final) | Clausura 2010 | 100% | sí |
| `ronda` | j) fase | 0 regular, 1 repechaje/play-in, 2 cuartos, 3 semifinal, 4 final | Clausura 2010 | 100% | sí |
| `pierna` | j) fase | 1 ida, 2 vuelta (vacío en fase regular y partido único) | Clausura 2010 (parcial) | 8% | sí |
| `es_vuelta` | j) fase | 1 si es el partido de vuelta de una serie | Clausura 2010 | 100% | sí |
| `global_gf_l` | j) fase | goles del local actual en la ida (sólo en la vuelta) | Clausura 2010 (parcial) | 4% | sí |
| `global_gc_l` | j) fase | goles del visitante actual en la ida (sólo en la vuelta) | Clausura 2010 (parcial) | 4% | sí |
| `global_dif_l` | j) fase | marcador global antes de la vuelta, visto por el local actual | Clausura 2010 (parcial) | 4% | sí |
| `sembrado_l` | j) fase | posición final en la tabla del torneo (sólo liguilla) | Clausura 2010 (parcial) | 9% | sí |
| `sembrado_v` | j) fase | posición final en la tabla del torneo (sólo liguilla) | Clausura 2010 (parcial) | 9% | sí |
| `sembrado_dif` | j) fase | posición final en la tabla del torneo (sólo liguilla) | Clausura 2010 (parcial) | 9% | sí |
| `empate_favorece_l` | j) fase | 1 si en cuartos o semifinal el empate global favorece al local (mejor sembrado) | Clausura 2010 | 100% | sí |
| `empate_favorece_v` | j) fase | 1 si favorece al visitante | Clausura 2010 | 100% | sí |
| `regla_gol_visitante` | j) fase | 1 si en ese torneo el gol de visitante desempataba antes que la tabla (Apertura 2012 a Clausura 2021, cuartos y semifinal) | Clausura 2010 | 100% | sí |
| `ventaja_serie_l` | j) fase | ventaja efectiva del local al empezar la vuelta: global_dif_l + 0.5 si el empate lo favorece, - 0.5 si favorece al visitante | Clausura 2010 (parcial) | 4% | sí |
| `lig_series6_l` | j) fase | series de liguilla jugadas (terminadas) en los últimos 6 torneos y el actual | Clausura 2010 | 100% | sí |
| `lig_series6_v` | j) fase | series de liguilla jugadas (terminadas) en los últimos 6 torneos y el actual | Clausura 2010 | 100% | sí |
| `lig_series6_dif` | j) fase | series de liguilla jugadas (terminadas) en los últimos 6 torneos y el actual | Clausura 2010 | 100% | sí |
| `lig_ganadas6_l` | j) fase | series de liguilla ganadas en ese lapso | Clausura 2010 | 100% | sí |
| `lig_ganadas6_v` | j) fase | series de liguilla ganadas en ese lapso | Clausura 2010 | 100% | sí |
| `lig_ganadas6_dif` | j) fase | series de liguilla ganadas en ese lapso | Clausura 2010 | 100% | sí |
| `finales10_l` | j) fase | finales jugadas en los últimos 10 torneos | Clausura 2010 | 100% | sí |
| `finales10_v` | j) fase | finales jugadas en los últimos 10 torneos | Clausura 2010 | 100% | sí |
| `finales10_dif` | j) fase | finales jugadas en los últimos 10 torneos | Clausura 2010 | 100% | sí |
| `titulos10_l` | j) fase | títulos ganados en los últimos 10 torneos | Clausura 2010 | 100% | sí |
| `titulos10_v` | j) fase | títulos ganados en los últimos 10 torneos | Clausura 2010 | 100% | sí |
| `mercado_p_l` | k) mercado | probabilidad implícita de victoria local al CIERRE, sin margen (normalización proporcional). El cierre se conoce al silbatazo, no al corte del bloque | Clausura 2021 | 56% | sólo con momios publicados |
| `mercado_p_e` | k) mercado | probabilidad implícita de empate al cierre, sin margen | Clausura 2021 | 56% | sólo con momios publicados |
| `mercado_p_v` | k) mercado | probabilidad implícita de victoria visitante al cierre, sin margen | Clausura 2021 | 56% | sólo con momios publicados |
| `mercado_margen` | k) mercado | margen del 1X2 de cierre (suma de inversos - 1) | Clausura 2021 | 56% | sólo con momios publicados |
| `mercado_abre_p_l` | k) mercado | probabilidad implícita local con momios de APERTURA, sin margen | Clausura 2026 | 0% | sólo con momios publicados |
| `mercado_abre_p_e` | k) mercado | empate con momios de apertura | Clausura 2026 | 0% | sólo con momios publicados |
| `mercado_abre_p_v` | k) mercado | visitante con momios de apertura | Clausura 2026 | 0% | sólo con momios publicados |
| `mercado_linea` | k) mercado | línea de goles totales | Clausura 2021 | 56% | sólo con momios publicados |
| `mercado_p_over` | k) mercado | probabilidad implícita del 'más de' al cierre, sin margen | Clausura 2021 | 55% | sólo con momios publicados |
| `mercado_abre_p_over` | k) mercado | probabilidad implícita del 'más de' en la apertura | Clausura 2026 | 0% | sólo con momios publicados |
| `mercado_dudoso` | k) mercado | 1 si los momios parecen capturados EN VIVO (misma regla que datos.momios_en_vivo); en ese caso las demás mercado_* quedan vacías | Clausura 2021 | 56% | sólo con momios publicados |
| `n_prev_l` | l) otros | partidos previos del equipo en la base (desde 2001) | Clausura 2010 | 100% | sí |
| `n_prev_v` | l) otros | partidos previos del equipo en la base (desde 2001) | Clausura 2010 | 100% | sí |
| `poca_historia_l` | l) otros | 1 si tiene menos de 34 partidos previos | Clausura 2010 | 100% | sí |
| `poca_historia_v` | l) otros | 1 si tiene menos de 34 partidos previos | Clausura 2010 | 100% | sí |
| `recien_ascendido_l` | l) otros | 1 si no jugó alguno de los dos torneos anteriores (ascendido o franquicia nueva) | Clausura 2010 | 100% | sí |
| `recien_ascendido_v` | l) otros | 1 si no jugó alguno de los dos torneos anteriores (ascendido o franquicia nueva) | Clausura 2010 | 100% | sí |
| `arb_n` | l) otros | partidos previos del árbitro en la base (vacío si aún no hay árbitro designado) | Clausura 2010 (parcial) | 49% | sí, si ya hay árbitro designado |
| `arb_tarjetas` | l) otros | tarjetas (amarillas + rojas) por partido del árbitro, encogidas a la media de la liga con K=10 | Clausura 2010 (parcial) | 49% | sí, si ya hay árbitro designado |
| `arb_penales` | l) otros | penales marcados por partido del árbitro, encogidos a la media de la liga con K=10 | Clausura 2010 (parcial) | 49% | sí, si ya hay árbitro designado |
| `asistencia5_l` | l) otros | asistencia media de los últimos 5 partidos de local con dato (> 0; mínimo 3) | Apertura 2021 | 93% | sí |

## 5. Análisis exploratorio (sólo DESARROLLO: Apertura 2016 a Clausura 2025)

**Método.** Para cada variable x: logit ordenado del resultado a 90 minutos (visita < empate < local) sobre una
fuerza base y x estandarizada. Se reporta el coeficiente de x por desviación estándar (positivo = favorece al
local), su error estándar, el valor p de la razón de verosimilitudes y la mejora de log-loss por partido frente al
modelo con sólo la base, en la misma muestra. Dos bases:

- **Elo** (`elo_dif`/100; 2,981 partidos, sin los 2 resultados de escritorio). El coeficiente del propio Elo es ≈ 0.44 por
  100 puntos. Es una base DÉBIL a propósito: parte de lo que "agrega" una variable es fuerza que este Elo no mide.
- **Mercado** (log del cociente de probabilidades local/visita del cierre sin margen; 1,671 partidos con momios,
  2019-2025). Es la base exigente: lo que agregue aquí sería información que el cierre no trae.

**Advertencias.** (1) Es DENTRO de muestra y univariado: orienta, no selecciona. (2) Se probaron 283 variables
disponibles: con p < 0.05 salieron **32** contra base Elo (por azar se esperan ~14) y **14** de 281
contra base mercado (por azar ~14). Con corrección de Benjamini-Hochberg (q < 0.10) sobreviven **8**
contra Elo y **0** contra el mercado. (3) Con n ≈ 3,000 el error estándar es ≈ 0.035 por desviación estándar:
efectos menores a ~0.07 no se pueden distinguir de cero con una sola variable. (4) Los errores estándar suponen
partidos independientes. (5) PRUEBA no se tocó.

### 5.1 Qué parece tener señal y qué no

Sobreviven a la corrección por pruebas múltiples (base Elo): `sede_viaje_km_v`, `juego10_tiros_c_l`, `juego10_corners_c_v`, `once_previa_cambios_v`, `juego10_tiros_c_v`, `juego10_tiros_f_l`, `juego10_corners_c_l`, `juego5_tiros_c_v`.

- **Juego por tiros: sí, y es el grupo con más señal** (14 de 48 con p < 0.05; 6 con q < 0.10). Conceder pocos
  tiros y córners predice mejor que el marcador reciente: `juego10_tiros_c_l` −0.142 (0.037), `juego10_tiros_c_v`
  +0.128 (0.037), `juego10_tiros_f_l` +0.123 (0.036). Los goles esperados aproximados van en la dirección correcta
  pero son más débiles que los tiros crudos (`juego10_xg_f_dif` +0.050 (0.038)). La "suerte" (goles menos esperados)
  no predice nada: |coef| ≤ 0.012 en las cuatro versiones, es decir, **regresa a la media**: conviene valorar a los
  equipos por lo que generan y conceden, no por lo que les entró. Frente al mercado casi todo se apaga.
- **Viaje del visitante: sí frente a Elo, no frente al mercado.** `sede_viaje_km_v` +0.138 (0.035) por cada 579 km
  (p = 0.0001, la variable disponible más fuerte), pero +0.029 (0.047) frente al mercado. Lectura: parte es ventaja
  de local propia de las plazas lejanas (Tijuana, Juárez, Torreón, Monterrey), que el mercado ya cobra y que un
  modelo con localía por equipo o por sede debería capturar. Vale la pena probarla como variable y como
  interacción con la localía.
- **Altitud: sin evidencia clara.** `sede_altitud` −0.040 (0.035) y `sede_altura` −0.034 (0.035) frente a Elo; la
  diferencia de altitud que sufre el visitante, `sede_alt_dif_v`, +0.045 (0.035) frente a Elo y +0.098 (0.047,
  p = 0.039) frente al mercado: va en la dirección esperada pero no resiste las pruebas múltiples. El historial del
  visitante en altura no predice (`visita_altura_rel_v` −0.021 (0.036)). Tampoco hay más goles en la altura
  (+0.9% ± 1.1% por desviación estándar). Si se usa, que sea `sede_alt_dif_v` con encogimiento fuerte.
- **Ventaja de local por estadio: indicio débil.** `sede_vl_rel_l` +0.072 (0.035), p = 0.039, q = 0.38; frente al
  mercado +0.016 (0.047). Coherente con una varianza real pequeña entre sedes (τ ≈ 0.16 goles).
- **Rachas: no.** 2 de 28 con p < 0.05, lo que da el azar, y la más "significativa" tiene el signo contrario al
  folclor: la racha sin perder del visitante favorece al LOCAL (`racha_inv_v` +0.098 (0.036)). Las de victorias y
  derrotas, en casa o fuera, están todas dentro de ±0.05. Dada la fuerza, la racha vigente no agrega.
- **Forma reciente: poco y contradictorio.** Con la fuerza ya puesta, los puntos de los últimos 10 partidos tienen
  signo NEGATIVO (`forma10_ppp_dif` −0.140 (0.051)): este Elo ya reacciona de más a lo reciente; en cambio la
  diferencia de goles en su condición (local en casa, visitante fuera) es positiva (`forma10_cond_dg_dif` +0.133
  (0.050)). Ninguna pasa la corrección y frente al mercado todas son ≈ 0. Lo útil de la forma es la parte
  casa/visita, no "el momento".
- **Tabla y motivación: casi nada.** Posición y puntos por partido no agregan (|coef| < 0.01). El local ya eliminado
  rinde algo peor (`tabla_eliminado_l` −0.083 (0.035), p = 0.018, q = 0.25; son 2.8% de los partidos). Ya
  clasificado: sin efecto.
- **Descanso y calendario: no.** `descanso_dif` −0.056 (0.035) (signo contrario al esperado, no significativo);
  partidos en 14 días, pausa larga, regreso de fecha FIFA y media semana: nada con p < 0.05 frente a Elo (0 de 15).
  Ojo: el descanso sólo ve partidos de liga (no Leagues Cup ni Concacaf).
- **Historial directo y dominios: no.** 1 de 17 con p < 0.05 y con signo contrario (`h2h6_pts_l` −0.085 (0.041)).
  El historial en la misma sede, en liguilla y el balance de series y de finales ("dominios") están todos dentro de
  ±0.05 con errores de 0.035 a 0.05. Con 10 enfrentamientos por pareja no hay cómo distinguir un dominio real de la
  diferencia de fuerza. Sirven para la narrativa de la página, no para mover probabilidades.
- **Suspendidos y ausencias: señal chica, en la dirección esperada, sin significancia.** Las ausencias del local
  restan: `aus_tit_previa_l` −0.067 (0.034), p = 0.050; `susp_titulares_l` −0.063 (0.034); `susp_imp_l` −0.051
  (0.035). Las del visitante no muestran el signo esperado (`susp_n_v` −0.038 (0.035)). Hay suspendidos en 18% de
  los equipos-partido, así que el efecto medio sobre el log-loss es mínimo; puede valer como ajuste pequeño y
  encogido (versión con importancia, no el conteo).
- **Continuidad del once: lo que predice es la ROTACIÓN del visitante, y saber el once real no ayuda más.**
  `once_previa_cambios_v` +0.123 (0.035), q = 0.026, y `once_previa_rot5_v` +0.092 (0.035): un visitante que viene
  cambiando su once rinde peor. En cambio las versiones `_real` (el once que sí jugó) no agregan nada medible:
  `once_real_hab_dif` +0.028 (0.036), `once_real_aus_dif` −0.032 (0.035), frente a `once_previa_hab_dif` +0.062
  (0.036). Conclusión práctica: **conocer la alineación una hora antes no vale más que lo que ya se deduce del
  partido anterior** (medido con proporción de titulares habituales; no mide la calidad individual del ausente).
- **Fase y liguilla: una pista en las vueltas.** En las 119 vueltas de DESARROLLO, llegar con ventaja en el global
  predice un PEOR partido de vuelta del local (`global_dif_l` −0.47 (0.21), p = 0.024; `ventaja_serie_l` −0.49
  (0.22)): el que va ganando administra. Muestra chica, pero es justo el tipo de efecto que el simulador de series
  debe considerar. El sembrado, la experiencia de liguilla y las finales jugadas no agregan (n = 274 partidos de
  liguilla con sembrado; errores de 0.13 a 0.15). `empate_favorece_v` +0.080 (0.034), p = 0.019 sin corregir: en las
  idas, donde el visitante suele ser el mejor sembrado, al local le va algo mejor de lo que dice Elo.
- **Recién ascendidos, árbitro, asistencia: no** (árbitro sólo existe en 49% de DESARROLLO).
- **Mercado: sí, y mucho.** `mercado_p_l` +0.637 (0.083) sobre Elo y 0.018 de log-loss por partido: siete veces
  la mejor variable propia (0.0026). Y al revés, `elo_dif` no agrega al mercado (+0.078 (0.083)). Ninguna variable
  disponible agrega al cierre de forma demostrable con esta muestra.

En una frase para quien modele: **prioridad a tiros a favor y en contra, viaje/localía por plaza y rotación del
once; rachas, historial directo, descanso y tabla no muestran señal propia**; suspendidos, altitud relativa y ventaja
por estadio son efectos chicos que sólo tienen sentido con mucho encogimiento. Las mejoras univariadas son del orden
de 0.001 a 0.003 de log-loss por partido: cualquier ganancia real habrá que demostrarla en el walk-forward.

### 5.2 Resumen por grupo (base Elo)

| Grupo | Variables | p < 0.05 | q < 0.10 | Mejor variable | coef (ee) | p | Δ log-loss por partido |
|---|---:|---:|---:|---|---:|---:|---:|
| 0) fuerza base | 4 | 0 | 0 | `liga_goles` | +0.035 (0.035) | 0.3091 | 0.00017 |
| a) forma | 68 | 4 | 0 | `forma10_ppp_dif` | -0.140 (0.051) | 0.0063 | 0.00126 |
| b) rachas | 28 | 2 | 0 | `racha_inv_v` | +0.098 (0.036) | 0.0067 | 0.00123 |
| c) tabla | 24 | 1 | 0 | `tabla_eliminado_l` | -0.083 (0.035) | 0.0183 | 0.00093 |
| d) calendario | 15 | 0 | 0 | `primer_partido_torneo_v` | -0.067 (0.034) | 0.0542 | 0.00062 |
| e) sede | 20 | 4 | 1 | `sede_viaje_km_v` | +0.138 (0.035) | 0.0001 | 0.00258 |
| f) h2h | 17 | 1 | 0 | `h2h6_pts_l` | -0.085 (0.041) | 0.0400 | 0.00072 |
| g) juego | 48 | 14 | 6 | `juego10_tiros_c_l` | -0.142 (0.037) | 0.0001 | 0.00245 |
| h) disciplina | 17 | 0 | 0 | `aus_tit_previa_l` | -0.067 (0.034) | 0.0504 | 0.00065 |
| i) alineación | 17 | 3 | 1 | `once_previa_cambios_v` | +0.123 (0.035) | 0.0004 | 0.00213 |
| j) fase | 25 | 3 | 0 | `empate_favorece_v` | +0.080 (0.034) | 0.0188 | 0.00093 |
| k) mercado | 7 | 3 | 0 | `mercado_p_l` | +0.637 (0.083) | 0.0000 | 0.01794 |
| l) otros | 10 | 0 | 0 | `asistencia5_l` | +0.070 (0.040) | 0.0774 | 0.00056 |

### 5.3 Variables clave, con las dos bases

DE = desviación estándar de la variable en la muestra (el coeficiente es por una DE).

**Forma**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `forma5_ppp_dif` | 2969 | 0.845 | -0.015 (0.042) | 0.721 | 0.95 | +0.054 (0.054) | 0.324 |
| `forma10_ppp_dif` | 2961 | 0.651 | -0.140 (0.051) | 0.006 | 0.13 | -0.056 (0.061) | 0.351 |
| `forma10_dg_dif` | 2961 | 0.885 | +0.012 (0.053) | 0.826 | 0.97 | -0.046 (0.065) | 0.473 |
| `forma10_cond_ppp_dif` | 2941 | 0.661 | +0.049 (0.047) | 0.298 | 0.74 | +0.000 (0.059) | 0.999 |
| `forma10_cond_dg_dif` | 2941 | 0.889 | +0.133 (0.050) | 0.007 | 0.13 | -0.005 (0.063) | 0.934 |
| `formaexp_ppp_dif` | 2969 | 0.576 | -0.124 (0.059) | 0.035 | 0.38 | -0.008 (0.065) | 0.907 |
| `formaexp_dg_dif` | 2969 | 0.795 | +0.038 (0.061) | 0.530 | 0.85 | -0.004 (0.070) | 0.952 |
| `torneo_ppp_dif` | 2811 | 0.844 | -0.013 (0.043) | 0.758 | 0.97 | -0.030 (0.057) | 0.594 |
| `torneo_dg_dif` | 2811 | 1.1 | +0.037 (0.044) | 0.392 | 0.77 | -0.053 (0.059) | 0.372 |

**Rachas**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `racha_vict_l` | 2978 | 1.05 | +0.051 (0.036) | 0.157 | 0.65 | +0.078 (0.049) | 0.105 |
| `racha_vict_v` | 2980 | 1.13 | -0.002 (0.035) | 0.954 | 0.99 | +0.009 (0.046) | 0.843 |
| `racha_inv_l` | 2978 | 2.32 | +0.042 (0.037) | 0.254 | 0.70 | +0.052 (0.050) | 0.296 |
| `racha_inv_v` | 2980 | 2.46 | +0.098 (0.036) | 0.007 | 0.13 | +0.096 (0.049) | 0.047 |
| `racha_singanar_l` | 2978 | 2.97 | +0.017 (0.036) | 0.633 | 0.91 | +0.021 (0.048) | 0.669 |
| `racha_singanar_v` | 2980 | 2.92 | +0.006 (0.039) | 0.870 | 0.98 | +0.023 (0.052) | 0.663 |
| `racha_derr_l` | 2978 | 1.06 | +0.029 (0.036) | 0.418 | 0.77 | +0.023 (0.048) | 0.636 |
| `racha_derr_v` | 2980 | 1 | -0.035 (0.036) | 0.332 | 0.76 | -0.046 (0.048) | 0.340 |
| `racha_cond_vict_l` | 2977 | 1.38 | +0.041 (0.036) | 0.256 | 0.70 | +0.013 (0.049) | 0.790 |
| `racha_cond_derr_v` | 2977 | 1.47 | +0.022 (0.037) | 0.559 | 0.86 | -0.005 (0.050) | 0.917 |
| `racha_cero_v` | 2980 | 0.729 | +0.077 (0.035) | 0.025 | 0.30 | +0.135 (0.047) | 0.004 |

**Tabla y lo que se juegan**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tabla_pos_dif` | 2811 | 6.91 | +0.001 (0.046) | 0.987 | 0.99 | +0.032 (0.060) | 0.596 |
| `tabla_ppp_dif` | 2811 | 0.847 | -0.008 (0.043) | 0.852 | 0.98 | -0.029 (0.057) | 0.616 |
| `tabla_dist_zona_l` | 2818 | 5.32 | +0.025 (0.039) | 0.523 | 0.85 | -0.021 (0.053) | 0.690 |
| `tabla_dist_zona_v` | 2819 | 5.28 | +0.033 (0.039) | 0.400 | 0.77 | +0.007 (0.052) | 0.892 |
| `tabla_clasificado_l` | 2981 | 0.343 | +0.033 (0.035) | 0.342 | 0.76 | +0.042 (0.047) | 0.380 |
| `tabla_clasificado_v` | 2981 | 0.337 | +0.058 (0.035) | 0.097 | 0.49 | +0.014 (0.047) | 0.761 |
| `tabla_eliminado_l` | 2981 | 0.166 | -0.083 (0.035) | 0.018 | 0.25 | -0.052 (0.048) | 0.269 |
| `tabla_eliminado_v` | 2981 | 0.171 | -0.002 (0.037) | 0.950 | 0.99 | +0.004 (0.052) | 0.942 |

**Descanso y calendario**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `descanso_l` | 2978 | 6.29 | -0.049 (0.035) | 0.158 | 0.65 | -0.078 (0.047) | 0.096 |
| `descanso_v` | 2980 | 6.33 | -0.046 (0.034) | 0.185 | 0.66 | -0.045 (0.046) | 0.333 |
| `descanso_dif` | 2977 | 1.53 | -0.056 (0.035) | 0.110 | 0.53 | -0.080 (0.047) | 0.089 |
| `pj14_dif` | 2981 | 0.627 | +0.041 (0.035) | 0.236 | 0.70 | +0.085 (0.047) | 0.070 |
| `pausa_larga_l` | 2981 | 0.315 | -0.020 (0.035) | 0.573 | 0.87 | +0.043 (0.048) | 0.369 |
| `pausa_larga_v` | 2981 | 0.328 | +0.029 (0.035) | 0.409 | 0.77 | +0.129 (0.048) | 0.007 |
| `regreso_pausa` | 2981 | 0.299 | -0.004 (0.035) | 0.906 | 0.99 | +0.055 (0.048) | 0.248 |
| `media_semana` | 2981 | 0.38 | +0.063 (0.035) | 0.069 | 0.44 | +0.104 (0.047) | 0.027 |
| `hora_local` | 2981 | 2.36 | -0.032 (0.035) | 0.355 | 0.76 | -0.066 (0.048) | 0.166 |
| `primer_partido_torneo_l` | 2981 | 0.227 | -0.045 (0.034) | 0.193 | 0.66 | -0.102 (0.046) | 0.028 |

**Altitud, viaje y sede**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sede_altitud` | 2981 | 797 | -0.040 (0.035) | 0.254 | 0.70 | +0.061 (0.047) | 0.194 |
| `sede_altura` | 2981 | 0.495 | -0.034 (0.035) | 0.322 | 0.76 | +0.058 (0.047) | 0.217 |
| `sede_alt_dif_v` | 2979 | 1.16e+03 | +0.045 (0.035) | 0.195 | 0.66 | +0.098 (0.047) | 0.038 |
| `sede_viaje_km_v` | 2979 | 579 | +0.138 (0.035) | 0.000 | 0.02 | +0.029 (0.047) | 0.539 |
| `sede_habitual_l` | 2976 | 0.103 | -0.068 (0.040) | 0.080 | 0.44 | -0.032 (0.053) | 0.545 |
| `sede_compartida` | 2981 | 0.281 | +0.021 (0.038) | 0.582 | 0.88 | -0.009 (0.050) | 0.855 |
| `sede_tambien_v` | 2979 | 0.0753 | -0.026 (0.032) | 0.416 | 0.77 | -0.037 (0.044) | 0.398 |
| `sede_sintetico` | 2981 | 0.225 | +0.085 (0.035) | 0.014 | 0.22 | -0.031 (0.046) | 0.500 |
| `sede_vl_l` | 2981 | 0.095 | +0.062 (0.035) | 0.075 | 0.44 | +0.016 (0.047) | 0.728 |
| `sede_vl_rel_l` | 2981 | 0.0923 | +0.072 (0.035) | 0.038 | 0.38 | +0.016 (0.047) | 0.734 |
| `visita_altura_dg_v` | 2961 | 0.519 | -0.057 (0.041) | 0.164 | 0.66 | -0.029 (0.054) | 0.590 |
| `visita_altura_rel_v` | 2949 | 0.479 | -0.021 (0.036) | 0.554 | 0.86 | +0.017 (0.047) | 0.723 |
| `visita_sint_rel_v` | 2612 | 0.618 | +0.038 (0.037) | 0.301 | 0.74 | +0.043 (0.050) | 0.392 |

**Historial directo y dominios**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `h2h6_pts_l` | 2911 | 0.275 | -0.085 (0.041) | 0.040 | 0.38 | -0.042 (0.053) | 0.424 |
| `h2h6_dg_l` | 2911 | 0.367 | -0.025 (0.043) | 0.550 | 0.86 | -0.007 (0.054) | 0.904 |
| `h2h10_pts_l` | 2911 | 0.274 | -0.048 (0.041) | 0.246 | 0.70 | -0.035 (0.053) | 0.510 |
| `h2h10_dg_l` | 2911 | 0.371 | -0.001 (0.042) | 0.979 | 0.99 | -0.015 (0.054) | 0.789 |
| `h2h_sede_pts_l` | 2777 | 0.278 | +0.011 (0.039) | 0.775 | 0.97 | -0.048 (0.052) | 0.359 |
| `h2h_sede_dg_l` | 2777 | 0.355 | +0.030 (0.039) | 0.441 | 0.78 | -0.062 (0.052) | 0.235 |
| `h2h_lig_dg_l` | 1701 | 0.287 | -0.010 (0.049) | 0.842 | 0.97 | -0.044 (0.064) | 0.496 |
| `h2h_lig_series_bal_l` | 2981 | 1.35 | -0.029 (0.035) | 0.400 | 0.77 | -0.006 (0.047) | 0.903 |
| `h2h_final_series_bal_l` | 2981 | 0.481 | +0.001 (0.034) | 0.980 | 0.99 | -0.016 (0.046) | 0.732 |

**Juego (tiros, posesión, goles esperados)**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `juego10_tiros_f_l` | 2939 | 2.18 | +0.123 (0.036) | 0.001 | 0.03 | +0.038 (0.052) | 0.466 |
| `juego10_tiros_c_l` | 2939 | 2.19 | -0.142 (0.037) | 0.000 | 0.02 | -0.034 (0.053) | 0.523 |
| `juego10_tiros_f_v` | 2944 | 2.19 | -0.089 (0.036) | 0.013 | 0.21 | -0.074 (0.050) | 0.140 |
| `juego10_tiros_c_v` | 2944 | 2.18 | +0.128 (0.037) | 0.001 | 0.03 | +0.083 (0.053) | 0.117 |
| `juego10_corners_c_l` | 2939 | 1.04 | -0.119 (0.036) | 0.001 | 0.04 | -0.041 (0.050) | 0.408 |
| `juego10_corners_c_v` | 2944 | 1.04 | +0.132 (0.037) | 0.000 | 0.03 | +0.141 (0.051) | 0.005 |
| `juego10_xg_f_dif` | 2902 | 0.321 | +0.050 (0.038) | 0.191 | 0.66 | +0.034 (0.053) | 0.520 |
| `juego10_xg_c_dif` | 2902 | 0.294 | +0.020 (0.038) | 0.599 | 0.88 | +0.124 (0.051) | 0.016 |
| `juego10_xgdif_dif` | 2902 | 0.463 | +0.025 (0.041) | 0.545 | 0.86 | -0.064 (0.056) | 0.258 |
| `juego10_posesion_dif` | 2899 | 7.29 | +0.113 (0.040) | 0.004 | 0.12 | +0.063 (0.057) | 0.269 |
| `juego10_suerte_f_l` | 2939 | 0.333 | -0.012 (0.036) | 0.740 | 0.96 | -0.017 (0.049) | 0.732 |
| `juego10_suerte_f_v` | 2944 | 0.335 | -0.008 (0.037) | 0.819 | 0.97 | +0.010 (0.048) | 0.839 |
| `juego10_suerte_c_l` | 2939 | 0.342 | +0.006 (0.037) | 0.862 | 0.98 | +0.017 (0.049) | 0.727 |
| `juego10_suerte_c_v` | 2944 | 0.341 | -0.007 (0.037) | 0.843 | 0.97 | +0.009 (0.051) | 0.867 |

**Suspendidos y ausencias**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rojas_prev_l` | 2978 | 0.418 | -0.021 (0.034) | 0.545 | 0.86 | +0.005 (0.047) | 0.914 |
| `rojas_prev_v` | 2980 | 0.402 | -0.007 (0.034) | 0.840 | 0.97 | +0.032 (0.047) | 0.501 |
| `susp_n_l` | 2978 | 0.442 | -0.036 (0.034) | 0.289 | 0.73 | -0.028 (0.047) | 0.545 |
| `susp_n_v` | 2980 | 0.45 | -0.038 (0.035) | 0.269 | 0.71 | -0.033 (0.047) | 0.479 |
| `susp_n_dif` | 2977 | 0.617 | +0.002 (0.034) | 0.951 | 0.99 | +0.005 (0.047) | 0.918 |
| `susp_imp_l` | 2977 | 0.327 | -0.051 (0.035) | 0.138 | 0.60 | -0.041 (0.047) | 0.392 |
| `susp_imp_v` | 2978 | 0.335 | -0.046 (0.035) | 0.187 | 0.66 | -0.049 (0.047) | 0.297 |
| `susp_imp_dif` | 2974 | 0.46 | -0.004 (0.035) | 0.901 | 0.99 | +0.009 (0.047) | 0.855 |
| `susp_titulares_l` | 2977 | 0.363 | -0.063 (0.034) | 0.067 | 0.44 | -0.042 (0.048) | 0.378 |
| `susp_titulares_v` | 2978 | 0.373 | -0.045 (0.035) | 0.199 | 0.66 | -0.044 (0.047) | 0.347 |
| `aus_conv_n_l` | 2948 | 1.19 | -0.051 (0.034) | 0.133 | 0.60 | -0.072 (0.046) | 0.116 |
| `aus_conv_n_v` | 2946 | 1.2 | +0.027 (0.035) | 0.446 | 0.79 | -0.051 (0.047) | 0.278 |
| `aus_tit_previa_l` | 2948 | 1.23 | -0.067 (0.034) | 0.050 | 0.40 | -0.083 (0.046) | 0.073 |
| `aus_tit_previa_v` | 2946 | 1.23 | +0.012 (0.035) | 0.723 | 0.95 | -0.064 (0.047) | 0.175 |
| `aus_tit_previa_dif` | 2925 | 1.52 | -0.062 (0.035) | 0.074 | 0.44 | -0.019 (0.047) | 0.689 |

**Continuidad del once: versión previa (disponible) contra versión real (no disponible)**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `once_previa_hab_l` | 2960 | 0.11 | +0.002 (0.035) | 0.953 | 0.99 | -0.026 (0.047) | 0.573 |
| `once_previa_hab_v` | 2960 | 0.112 | -0.072 (0.035) | 0.040 | 0.38 | -0.020 (0.047) | 0.671 |
| `once_previa_hab_dif` | 2939 | 0.139 | +0.062 (0.036) | 0.082 | 0.44 | -0.003 (0.048) | 0.947 |
| `once_previa_cambios_l` | 2977 | 1.74 | +0.001 (0.035) | 0.966 | 0.99 | -0.000 (0.047) | 0.999 |
| `once_previa_cambios_v` | 2977 | 1.7 | +0.123 (0.035) | 0.000 | 0.03 | +0.067 (0.046) | 0.146 |
| `once_previa_rot5_l` | 2970 | 2.64 | +0.026 (0.035) | 0.453 | 0.79 | -0.003 (0.047) | 0.953 |
| `once_previa_rot5_v` | 2972 | 2.62 | +0.092 (0.035) | 0.009 | 0.15 | -0.000 (0.047) | 0.998 |
| `once_real_hab_l` | 2959 | 0.123 | +0.011 (0.035) | 0.755 | — | +0.003 (0.047) | 0.950 |
| `once_real_hab_v` | 2962 | 0.121 | -0.018 (0.035) | 0.616 | — | +0.049 (0.047) | 0.303 |
| `once_real_hab_dif` | 2944 | 0.151 | +0.028 (0.036) | 0.426 | — | -0.038 (0.048) | 0.436 |
| `once_real_cambios_l` | 2967 | 1.7 | -0.010 (0.035) | 0.784 | — | -0.018 (0.047) | 0.696 |
| `once_real_cambios_v` | 2970 | 1.73 | -0.020 (0.035) | 0.569 | — | -0.077 (0.047) | 0.103 |
| `once_real_aus_l` | 2959 | 1.57 | -0.052 (0.035) | 0.133 | — | -0.056 (0.047) | 0.231 |
| `once_real_aus_v` | 2962 | 1.57 | -0.017 (0.035) | 0.630 | — | -0.080 (0.047) | 0.088 |
| `once_real_aus_dif` | 2944 | 2 | -0.032 (0.035) | 0.357 | — | +0.019 (0.047) | 0.681 |

**Fase y liguilla**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `es_liguilla` | 2981 | 0.289 | +0.062 (0.035) | 0.071 | 0.44 | +0.072 (0.047) | 0.125 |
| `ronda` | 2981 | 0.732 | +0.061 (0.034) | 0.075 | 0.44 | +0.068 (0.047) | 0.145 |
| `es_vuelta` | 2981 | 0.196 | +0.012 (0.035) | 0.730 | 0.96 | -0.012 (0.048) | 0.804 |
| `global_dif_l` | 119 | 1.55 | -0.474 (0.214) | 0.024 | 0.30 | — | — |
| `ventaja_serie_l` | 119 | 1.55 | -0.492 (0.216) | 0.020 | 0.26 | — | — |
| `sembrado_dif` | 274 | 4.53 | +0.033 (0.152) | 0.829 | 0.97 | +0.072 (0.180) | 0.689 |
| `empate_favorece_l` | 2981 | 0.182 | +0.005 (0.036) | 0.898 | 0.99 | -0.038 (0.049) | 0.442 |
| `empate_favorece_v` | 2981 | 0.182 | +0.080 (0.034) | 0.019 | 0.25 | +0.122 (0.046) | 0.007 |
| `lig_series6_dif` | 2981 | 5.25 | -0.013 (0.051) | 0.801 | 0.97 | +0.005 (0.058) | 0.926 |
| `lig_ganadas6_dif` | 2981 | 3.75 | -0.013 (0.046) | 0.783 | 0.97 | -0.017 (0.054) | 0.751 |
| `finales10_dif` | 2981 | 1.7 | +0.050 (0.045) | 0.263 | 0.70 | -0.016 (0.057) | 0.772 |

**Otros**

| Variable | n | DE | coef (ee), base Elo | p | q BH | coef (ee), base mercado | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| `recien_ascendido_l` | 2981 | 0.163 | -0.007 (0.035) | 0.830 | 0.97 | +0.031 (0.046) | 0.494 |
| `recien_ascendido_v` | 2981 | 0.163 | -0.012 (0.036) | 0.733 | 0.96 | +0.042 (0.055) | 0.434 |
| `poca_historia_v` | 2981 | 0.149 | +0.005 (0.037) | 0.888 | 0.99 | +0.031 (0.052) | 0.545 |
| `arb_tarjetas` | 1456 | 0.425 | +0.001 (0.051) | 0.987 | 0.99 | +0.020 (0.058) | 0.730 |
| `arb_penales` | 1456 | 0.0749 | -0.044 (0.050) | 0.381 | 0.77 | -0.029 (0.057) | 0.610 |
| `asistencia5_l` | 2770 | 1.03e+04 | +0.070 (0.040) | 0.077 | 0.44 | +0.001 (0.055) | 0.992 |
| `liga_goles` | 2981 | 0.13 | +0.035 (0.035) | 0.309 | 0.75 | +0.089 (0.047) | 0.057 |
| `liga_vl` | 2981 | 0.022 | -0.035 (0.035) | 0.322 | 0.76 | +0.003 (0.047) | 0.943 |

### 5.4 Total de goles

Regresión de Poisson del total de goles sobre `liga_goles` y la variable estandarizada (coeficiente por DE: 0.03 =
+3% de goles). Las sumas son de ambos equipos: `goles10_suma` = goles a favor y en contra de los dos en sus últimos
10; `xg10_suma` y `tiros10_suma`, igual con goles esperados y tiros.

| Variable | n | coef por DE (ee) | z | p |
|---|---:|---:|---:|---:|
| `goles10_suma` | 2961 | +0.060 (0.011) | +5.30 | 0.0000 |
| `xg10_suma` | 2902 | +0.053 (0.012) | +4.41 | 0.0000 |
| `tiros10_suma` | 2902 | +0.060 (0.011) | +5.25 | 0.0000 |
| `elo_abs` | 2981 | +0.015 (0.011) | +1.37 | 0.1706 |
| `sede_altitud` | 2981 | +0.009 (0.011) | +0.78 | 0.4370 |
| `sede_alt_dif_v` | 2979 | -0.004 (0.011) | -0.37 | 0.7109 |
| `sede_viaje_km_v` | 2979 | +0.003 (0.011) | +0.27 | 0.7857 |
| `sede_sintetico` | 2981 | +0.003 (0.011) | +0.24 | 0.8087 |
| `es_liguilla` | 2981 | -0.005 (0.011) | -0.42 | 0.6702 |
| `es_vuelta` | 2981 | -0.002 (0.011) | -0.17 | 0.8639 |
| `media_semana` | 2981 | -0.014 (0.011) | -1.23 | 0.2163 |
| `hora_local` | 2981 | -0.033 (0.011) | -3.05 | 0.0025 |
| `mes` | 2981 | +0.005 (0.011) | +0.44 | 0.6571 |
| `descanso_l` | 2978 | +0.000 (0.011) | +0.01 | 0.9927 |
| `descanso_v` | 2980 | -0.000 (0.011) | -0.01 | 0.9897 |
| `avance_torneo` | 2981 | +0.016 (0.011) | +1.45 | 0.1457 |
| `susp_n_l` | 2978 | -0.005 (0.011) | -0.42 | 0.6740 |
| `susp_n_v` | 2980 | +0.007 (0.011) | +0.58 | 0.5600 |
| `arb_penales` | 1456 | -0.027 (0.016) | -1.73 | 0.0823 |
| `arb_tarjetas` | 1456 | +0.001 (0.016) | +0.08 | 0.9386 |
| `mercado_linea` | 1668 | +0.055 (0.015) | +3.77 | 0.0002 |
| `mercado_p_over` | 1643 | +0.008 (0.015) | +0.52 | 0.6018 |

Lectura: el nivel goleador reciente de los dos equipos sí anticipa goles (+6% por DE, tanto con goles como con
tiros); la altitud, el viaje, la liguilla y el descanso no; los partidos más tarde tienen algo menos de goles
(−3.3% por DE de hora, p = 0.003; puede ser efecto de qué equipos juegan a esa hora). La línea del mercado agrega
+5.5% por DE.

### 5.5 Todas las variables

| Variable | Grupo | n | coef (ee), base Elo | z | p | q BH | Δ log-loss | n con momios | coef (ee), base mercado | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `elo_l` | 0) fuerza base | 0 | sin datos suficientes |  |  |  |  | 1671 | -0.001 (0.056) | 0.9908 |
| `elo_v` | 0) fuerza base | 0 | sin datos suficientes |  |  |  |  | 1671 | -0.053 (0.057) | 0.3539 |
| `elo_dif` | 0) fuerza base | 0 | sin datos suficientes |  |  |  |  | 1671 | +0.078 (0.083) | 0.3439 |
| `liga_goles` | 0) fuerza base | 2981 | +0.035 (0.035) | +1.02 | 0.3091 | 0.748 | 0.00017 | 1671 | +0.089 (0.047) | 0.0567 |
| `liga_vl` | 0) fuerza base | 2981 | -0.035 (0.035) | -0.99 | 0.3222 | 0.755 | 0.00016 | 1671 | +0.003 (0.047) | 0.9429 |
| `liga_p_local` | 0) fuerza base | 2981 | -0.031 (0.035) | -0.90 | 0.3669 | 0.763 | 0.00014 | 1671 | -0.002 (0.047) | 0.9681 |
| `liga_p_empate` | 0) fuerza base | 2981 | -0.001 (0.034) | -0.02 | 0.9865 | 0.991 | 0.00000 | 1671 | -0.030 (0.047) | 0.5280 |
| `forma5_ppp_l` | a) forma | 2974 | +0.003 (0.037) | +0.07 | 0.9418 | 0.986 | 0.00000 | 1670 | +0.025 (0.049) | 0.6075 |
| `forma5_ppp_v` | a) forma | 2976 | +0.016 (0.038) | +0.42 | 0.6709 | 0.922 | 0.00003 | 1669 | -0.036 (0.050) | 0.4773 |
| `forma5_ppp_dif` | a) forma | 2969 | -0.015 (0.042) | -0.36 | 0.7208 | 0.952 | 0.00002 | 1668 | +0.054 (0.054) | 0.3235 |
| `forma5_cond_ppp_l` | a) forma | 2969 | -0.007 (0.037) | -0.17 | 0.8616 | 0.980 | 0.00001 | 1668 | -0.064 (0.050) | 0.2016 |
| `forma5_cond_ppp_v` | a) forma | 2969 | +0.012 (0.037) | +0.31 | 0.7577 | 0.966 | 0.00002 | 1666 | +0.009 (0.051) | 0.8630 |
| `forma5_gf_l` | a) forma | 2974 | +0.044 (0.036) | +1.21 | 0.2250 | 0.690 | 0.00025 | 1670 | +0.071 (0.049) | 0.1495 |
| `forma5_gf_v` | a) forma | 2976 | -0.039 (0.036) | -1.08 | 0.2801 | 0.723 | 0.00020 | 1669 | -0.021 (0.048) | 0.6707 |
| `forma5_cond_gf_l` | a) forma | 2969 | +0.051 (0.037) | +1.38 | 0.1678 | 0.658 | 0.00032 | 1668 | -0.004 (0.049) | 0.9269 |
| `forma5_cond_gf_v` | a) forma | 2969 | -0.017 (0.036) | -0.48 | 0.6328 | 0.909 | 0.00004 | 1666 | +0.026 (0.049) | 0.5880 |
| `forma5_gc_l` | a) forma | 2974 | -0.016 (0.036) | -0.45 | 0.6559 | 0.914 | 0.00003 | 1670 | -0.019 (0.048) | 0.6874 |
| `forma5_gc_v` | a) forma | 2976 | -0.033 (0.037) | -0.91 | 0.3609 | 0.763 | 0.00014 | 1669 | -0.035 (0.049) | 0.4782 |
| `forma5_cond_gc_l` | a) forma | 2969 | +0.016 (0.036) | +0.44 | 0.6594 | 0.915 | 0.00003 | 1668 | +0.082 (0.049) | 0.0928 |
| `forma5_cond_gc_v` | a) forma | 2969 | +0.008 (0.037) | +0.21 | 0.8363 | 0.970 | 0.00001 | 1666 | -0.033 (0.050) | 0.5044 |
| `forma5_dg_l` | a) forma | 2974 | +0.044 (0.038) | +1.17 | 0.2409 | 0.696 | 0.00023 | 1670 | +0.064 (0.050) | 0.1991 |
| `forma5_dg_v` | a) forma | 2976 | -0.005 (0.038) | -0.14 | 0.8878 | 0.986 | 0.00000 | 1669 | +0.010 (0.051) | 0.8463 |
| `forma5_dg_dif` | a) forma | 2969 | +0.044 (0.043) | +1.03 | 0.3025 | 0.738 | 0.00018 | 1668 | +0.051 (0.057) | 0.3676 |
| `forma5_cond_dg_l` | a) forma | 2969 | +0.028 (0.038) | +0.74 | 0.4592 | 0.792 | 0.00009 | 1668 | -0.058 (0.050) | 0.2466 |
| `forma5_cond_dg_v` | a) forma | 2969 | -0.018 (0.038) | -0.47 | 0.6388 | 0.911 | 0.00004 | 1666 | +0.045 (0.052) | 0.3836 |
| `forma10_ppp_l` | a) forma | 2970 | -0.045 (0.040) | -1.14 | 0.2547 | 0.696 | 0.00022 | 1668 | -0.053 (0.051) | 0.3008 |
| `forma10_ppp_v` | a) forma | 2972 | +0.071 (0.040) | +1.77 | 0.0764 | 0.437 | 0.00053 | 1667 | +0.002 (0.052) | 0.9766 |
| `forma10_ppp_dif` | a) forma | 2961 | -0.140 (0.051) | -2.73 | 0.0063 | 0.128 | 0.00126 | 1664 | -0.056 (0.061) | 0.3514 |
| `forma10_cond_ppp_l` | a) forma | 2961 | +0.030 (0.039) | +0.75 | 0.4507 | 0.791 | 0.00010 | 1667 | -0.045 (0.052) | 0.3849 |
| `forma10_cond_ppp_v` | a) forma | 2961 | -0.021 (0.039) | -0.54 | 0.5886 | 0.878 | 0.00005 | 1665 | -0.043 (0.051) | 0.3978 |
| `forma10_cond_ppp_dif` | a) forma | 2941 | +0.049 (0.047) | +1.04 | 0.2976 | 0.738 | 0.00018 | 1661 | +0.000 (0.059) | 0.9989 |
| `forma10_gf_l` | a) forma | 2970 | +0.030 (0.037) | +0.80 | 0.4251 | 0.771 | 0.00011 | 1668 | +0.019 (0.050) | 0.7008 |
| `forma10_gf_v` | a) forma | 2972 | -0.006 (0.038) | -0.16 | 0.8696 | 0.981 | 0.00000 | 1667 | +0.009 (0.049) | 0.8542 |
| `forma10_cond_gf_l` | a) forma | 2961 | +0.062 (0.038) | +1.62 | 0.1050 | 0.512 | 0.00044 | 1667 | +0.025 (0.050) | 0.6187 |
| `forma10_cond_gf_v` | a) forma | 2961 | -0.019 (0.037) | -0.53 | 0.5989 | 0.878 | 0.00005 | 1665 | +0.006 (0.050) | 0.8961 |
| `forma10_gc_l` | a) forma | 2970 | -0.004 (0.038) | -0.11 | 0.9087 | 0.986 | 0.00000 | 1668 | +0.043 (0.050) | 0.3877 |
| `forma10_gc_v` | a) forma | 2972 | -0.028 (0.038) | -0.74 | 0.4581 | 0.792 | 0.00009 | 1667 | -0.021 (0.051) | 0.6815 |
| `forma10_cond_gc_l` | a) forma | 2961 | -0.042 (0.037) | -1.13 | 0.2590 | 0.698 | 0.00022 | 1667 | +0.066 (0.050) | 0.1878 |
| `forma10_cond_gc_v` | a) forma | 2961 | +0.044 (0.038) | +1.16 | 0.2456 | 0.696 | 0.00023 | 1665 | +0.024 (0.051) | 0.6405 |
| `forma10_dg_l` | a) forma | 2970 | +0.026 (0.040) | +0.65 | 0.5183 | 0.846 | 0.00007 | 1668 | -0.018 (0.052) | 0.7259 |
| `forma10_dg_v` | a) forma | 2972 | +0.017 (0.041) | +0.41 | 0.6846 | 0.936 | 0.00003 | 1667 | +0.022 (0.053) | 0.6749 |
| `forma10_dg_dif` | a) forma | 2961 | +0.012 (0.053) | +0.22 | 0.8262 | 0.970 | 0.00001 | 1664 | -0.046 (0.065) | 0.4732 |
| `forma10_cond_dg_l` | a) forma | 2961 | +0.075 (0.040) | +1.89 | 0.0583 | 0.402 | 0.00061 | 1667 | -0.024 (0.052) | 0.6431 |
| `forma10_cond_dg_v` | a) forma | 2961 | -0.048 (0.040) | -1.20 | 0.2292 | 0.690 | 0.00024 | 1665 | -0.014 (0.053) | 0.7846 |
| `forma10_cond_dg_dif` | a) forma | 2941 | +0.133 (0.050) | +2.68 | 0.0073 | 0.128 | 0.00123 | 1661 | -0.005 (0.063) | 0.9343 |
| `formaexp_ppp_l` | a) forma | 2974 | -0.025 (0.041) | -0.61 | 0.5398 | 0.857 | 0.00006 | 1670 | -0.021 (0.052) | 0.6897 |
| `formaexp_ppp_v` | a) forma | 2976 | +0.055 (0.042) | +1.32 | 0.1875 | 0.658 | 0.00029 | 1669 | -0.014 (0.053) | 0.7926 |
| `formaexp_ppp_dif` | a) forma | 2969 | -0.124 (0.059) | -2.10 | 0.0354 | 0.378 | 0.00075 | 1668 | -0.008 (0.065) | 0.9071 |
| `formaexp_cond_ppp_l` | a) forma | 2969 | +0.032 (0.040) | +0.80 | 0.4232 | 0.771 | 0.00011 | 1668 | -0.039 (0.052) | 0.4573 |
| `formaexp_cond_ppp_v` | a) forma | 2969 | -0.028 (0.040) | -0.70 | 0.4821 | 0.817 | 0.00008 | 1666 | -0.048 (0.052) | 0.3606 |
| `formaexp_gf_l` | a) forma | 2974 | +0.037 (0.038) | +0.98 | 0.3284 | 0.755 | 0.00016 | 1670 | +0.045 (0.051) | 0.3718 |
| `formaexp_gf_v` | a) forma | 2976 | +0.002 (0.038) | +0.04 | 0.9687 | 0.991 | 0.00000 | 1669 | +0.006 (0.050) | 0.9111 |
| `formaexp_cond_gf_l` | a) forma | 2969 | +0.075 (0.039) | +1.94 | 0.0519 | 0.402 | 0.00064 | 1668 | +0.032 (0.050) | 0.5262 |
| `formaexp_cond_gf_v` | a) forma | 2969 | -0.022 (0.037) | -0.59 | 0.5566 | 0.860 | 0.00006 | 1666 | +0.001 (0.050) | 0.9824 |
| `formaexp_gc_l` | a) forma | 2974 | -0.017 (0.038) | -0.43 | 0.6661 | 0.920 | 0.00003 | 1670 | +0.024 (0.051) | 0.6352 |
| `formaexp_gc_v` | a) forma | 2976 | -0.018 (0.039) | -0.47 | 0.6404 | 0.911 | 0.00004 | 1669 | -0.021 (0.052) | 0.6919 |
| `formaexp_cond_gc_l` | a) forma | 2969 | -0.035 (0.038) | -0.93 | 0.3512 | 0.763 | 0.00015 | 1668 | +0.059 (0.051) | 0.2407 |
| `formaexp_cond_gc_v` | a) forma | 2969 | +0.051 (0.039) | +1.33 | 0.1828 | 0.658 | 0.00030 | 1666 | +0.023 (0.052) | 0.6511 |
| `formaexp_dg_l` | a) forma | 2974 | +0.041 (0.041) | +0.99 | 0.3236 | 0.755 | 0.00016 | 1670 | +0.014 (0.053) | 0.7917 |
| `formaexp_dg_v` | a) forma | 2976 | +0.015 (0.042) | +0.35 | 0.7229 | 0.952 | 0.00002 | 1669 | +0.019 (0.055) | 0.7250 |
| `formaexp_dg_dif` | a) forma | 2969 | +0.038 (0.061) | +0.63 | 0.5298 | 0.847 | 0.00007 | 1668 | -0.004 (0.070) | 0.9523 |
| `formaexp_cond_dg_l` | a) forma | 2969 | +0.082 (0.041) | +2.00 | 0.0451 | 0.402 | 0.00068 | 1668 | -0.014 (0.053) | 0.7946 |
| `formaexp_cond_dg_v` | a) forma | 2969 | -0.055 (0.041) | -1.35 | 0.1766 | 0.658 | 0.00031 | 1666 | -0.017 (0.054) | 0.7478 |
| `torneo_pj_l` | a) forma | 2981 | -0.003 (0.035) | -0.08 | 0.9381 | 0.986 | 0.00000 | 1671 | +0.031 (0.047) | 0.5009 |
| `torneo_pj_v` | a) forma | 2981 | -0.004 (0.035) | -0.10 | 0.9179 | 0.986 | 0.00000 | 1671 | +0.027 (0.047) | 0.5673 |
| `torneo_ppp_l` | a) forma | 2818 | +0.022 (0.038) | +0.57 | 0.5689 | 0.870 | 0.00006 | 1585 | -0.009 (0.051) | 0.8624 |
| `torneo_ppp_v` | a) forma | 2819 | +0.036 (0.039) | +0.92 | 0.3558 | 0.763 | 0.00015 | 1588 | +0.013 (0.052) | 0.8021 |
| `torneo_ppp_dif` | a) forma | 2811 | -0.013 (0.043) | -0.31 | 0.7575 | 0.966 | 0.00002 | 1583 | -0.030 (0.057) | 0.5939 |
| `torneo_gf_l` | a) forma | 2818 | +0.027 (0.037) | +0.72 | 0.4708 | 0.804 | 0.00009 | 1585 | +0.013 (0.050) | 0.7939 |
| `torneo_gf_v` | a) forma | 2819 | -0.020 (0.037) | -0.53 | 0.5929 | 0.878 | 0.00005 | 1588 | +0.017 (0.049) | 0.7337 |
| `torneo_gc_l` | a) forma | 2818 | -0.037 (0.037) | -0.99 | 0.3230 | 0.755 | 0.00017 | 1585 | +0.007 (0.051) | 0.8954 |
| `torneo_gc_v` | a) forma | 2819 | -0.027 (0.037) | -0.72 | 0.4715 | 0.804 | 0.00009 | 1588 | -0.054 (0.051) | 0.2906 |
| `torneo_dg_l` | a) forma | 2818 | +0.046 (0.038) | +1.20 | 0.2315 | 0.690 | 0.00025 | 1585 | +0.005 (0.052) | 0.9311 |
| `torneo_dg_v` | a) forma | 2819 | +0.004 (0.039) | +0.11 | 0.9158 | 0.986 | 0.00000 | 1588 | +0.052 (0.053) | 0.3228 |
| `torneo_dg_dif` | a) forma | 2811 | +0.037 (0.044) | +0.86 | 0.3915 | 0.769 | 0.00013 | 1583 | -0.053 (0.059) | 0.3718 |
| `racha_vict_l` | b) rachas | 2978 | +0.051 (0.036) | +1.40 | 0.1573 | 0.648 | 0.00034 | 1671 | +0.078 (0.049) | 0.1051 |
| `racha_vict_v` | b) rachas | 2980 | -0.002 (0.035) | -0.06 | 0.9537 | 0.986 | 0.00000 | 1671 | +0.009 (0.046) | 0.8429 |
| `racha_cond_vict_l` | b) rachas | 2977 | +0.041 (0.036) | +1.13 | 0.2559 | 0.696 | 0.00022 | 1670 | +0.013 (0.049) | 0.7902 |
| `racha_cond_vict_v` | b) rachas | 2977 | -0.035 (0.035) | -0.98 | 0.3262 | 0.755 | 0.00016 | 1670 | -0.046 (0.048) | 0.3397 |
| `racha_inv_l` | b) rachas | 2978 | +0.042 (0.037) | +1.14 | 0.2536 | 0.696 | 0.00022 | 1671 | +0.052 (0.050) | 0.2957 |
| `racha_inv_v` | b) rachas | 2980 | +0.098 (0.036) | +2.70 | 0.0067 | 0.128 | 0.00123 | 1671 | +0.096 (0.049) | 0.0472 |
| `racha_cond_inv_l` | b) rachas | 2977 | +0.030 (0.037) | +0.82 | 0.4110 | 0.769 | 0.00011 | 1670 | -0.039 (0.050) | 0.4359 |
| `racha_cond_inv_v` | b) rachas | 2977 | +0.007 (0.035) | +0.21 | 0.8376 | 0.970 | 0.00001 | 1670 | +0.017 (0.048) | 0.7229 |
| `racha_singanar_l` | b) rachas | 2978 | +0.017 (0.036) | +0.48 | 0.6331 | 0.909 | 0.00004 | 1671 | +0.021 (0.048) | 0.6692 |
| `racha_singanar_v` | b) rachas | 2980 | +0.006 (0.039) | +0.16 | 0.8704 | 0.981 | 0.00000 | 1671 | +0.023 (0.052) | 0.6629 |
| `racha_cond_singanar_l` | b) rachas | 2977 | +0.004 (0.036) | +0.13 | 0.9003 | 0.986 | 0.00000 | 1670 | +0.007 (0.047) | 0.8821 |
| `racha_cond_singanar_v` | b) rachas | 2977 | +0.035 (0.037) | +0.95 | 0.3398 | 0.755 | 0.00015 | 1670 | +0.058 (0.048) | 0.2261 |
| `racha_derr_l` | b) rachas | 2978 | +0.029 (0.036) | +0.81 | 0.4180 | 0.769 | 0.00011 | 1671 | +0.023 (0.048) | 0.6365 |
| `racha_derr_v` | b) rachas | 2980 | -0.035 (0.036) | -0.97 | 0.3325 | 0.755 | 0.00016 | 1671 | -0.046 (0.048) | 0.3404 |
| `racha_cond_derr_l` | b) rachas | 2977 | -0.002 (0.035) | -0.06 | 0.9504 | 0.986 | 0.00000 | 1670 | +0.011 (0.047) | 0.8147 |
| `racha_cond_derr_v` | b) rachas | 2977 | +0.022 (0.037) | +0.58 | 0.5591 | 0.860 | 0.00006 | 1670 | -0.005 (0.050) | 0.9170 |
| `racha_anot_l` | b) rachas | 2978 | -0.007 (0.035) | -0.20 | 0.8399 | 0.970 | 0.00001 | 1671 | -0.006 (0.048) | 0.8955 |
| `racha_anot_v` | b) rachas | 2980 | +0.019 (0.035) | +0.54 | 0.5875 | 0.878 | 0.00005 | 1671 | +0.052 (0.048) | 0.2719 |
| `racha_cond_anot_l` | b) rachas | 2977 | +0.060 (0.036) | +1.66 | 0.0962 | 0.488 | 0.00046 | 1670 | +0.031 (0.049) | 0.5321 |
| `racha_cond_anot_v` | b) rachas | 2977 | -0.042 (0.035) | -1.20 | 0.2306 | 0.690 | 0.00024 | 1670 | -0.019 (0.047) | 0.6827 |
| `racha_sinanot_l` | b) rachas | 2978 | -0.016 (0.034) | -0.45 | 0.6509 | 0.912 | 0.00003 | 1671 | +0.002 (0.047) | 0.9609 |
| `racha_sinanot_v` | b) rachas | 2980 | +0.052 (0.036) | +1.45 | 0.1445 | 0.617 | 0.00036 | 1671 | +0.014 (0.047) | 0.7737 |
| `racha_cond_sinanot_l` | b) rachas | 2977 | -0.031 (0.034) | -0.89 | 0.3722 | 0.763 | 0.00013 | 1670 | -0.007 (0.045) | 0.8827 |
| `racha_cond_sinanot_v` | b) rachas | 2977 | +0.067 (0.036) | +1.89 | 0.0569 | 0.402 | 0.00061 | 1670 | +0.038 (0.047) | 0.4198 |
| `racha_cero_l` | b) rachas | 2978 | +0.029 (0.035) | +0.82 | 0.4100 | 0.769 | 0.00011 | 1671 | +0.048 (0.047) | 0.3030 |
| `racha_cero_v` | b) rachas | 2980 | +0.077 (0.035) | +2.23 | 0.0253 | 0.299 | 0.00084 | 1671 | +0.135 (0.047) | 0.0039 |
| `racha_cond_cero_l` | b) rachas | 2977 | +0.003 (0.035) | +0.08 | 0.9349 | 0.986 | 0.00000 | 1670 | +0.010 (0.047) | 0.8292 |
| `racha_cond_cero_v` | b) rachas | 2977 | -0.023 (0.035) | -0.66 | 0.5071 | 0.839 | 0.00007 | 1670 | -0.026 (0.047) | 0.5799 |
| `tabla_pos_l` | c) tabla | 2818 | -0.032 (0.039) | -0.83 | 0.4050 | 0.769 | 0.00012 | 1585 | +0.012 (0.052) | 0.8154 |
| `tabla_pos_v` | c) tabla | 2819 | -0.033 (0.039) | -0.84 | 0.4009 | 0.769 | 0.00013 | 1588 | -0.016 (0.053) | 0.7609 |
| `tabla_pos_dif` | c) tabla | 2811 | +0.001 (0.046) | +0.02 | 0.9873 | 0.991 | 0.00000 | 1583 | +0.032 (0.060) | 0.5956 |
| `tabla_pj_l` | c) tabla | 2981 | -0.009 (0.035) | -0.25 | 0.8024 | 0.970 | 0.00001 | 1671 | +0.026 (0.047) | 0.5734 |
| `tabla_pj_v` | c) tabla | 2981 | -0.008 (0.035) | -0.23 | 0.8170 | 0.970 | 0.00001 | 1671 | +0.025 (0.047) | 0.5908 |
| `tabla_pts_l` | c) tabla | 2981 | +0.007 (0.035) | +0.20 | 0.8407 | 0.970 | 0.00001 | 1671 | +0.019 (0.048) | 0.6978 |
| `tabla_pts_v` | c) tabla | 2981 | +0.008 (0.035) | +0.22 | 0.8248 | 0.970 | 0.00001 | 1671 | +0.024 (0.047) | 0.6111 |
| `tabla_ppp_l` | c) tabla | 2818 | +0.025 (0.038) | +0.65 | 0.5189 | 0.846 | 0.00007 | 1585 | -0.008 (0.051) | 0.8734 |
| `tabla_ppp_v` | c) tabla | 2819 | +0.033 (0.039) | +0.85 | 0.3933 | 0.769 | 0.00013 | 1588 | +0.012 (0.052) | 0.8200 |
| `tabla_ppp_dif` | c) tabla | 2811 | -0.008 (0.043) | -0.19 | 0.8517 | 0.976 | 0.00001 | 1583 | -0.029 (0.057) | 0.6162 |
| `tabla_dgpp_l` | c) tabla | 2818 | +0.049 (0.038) | +1.27 | 0.2046 | 0.658 | 0.00029 | 1585 | +0.006 (0.052) | 0.9138 |
| `tabla_dgpp_v` | c) tabla | 2819 | +0.002 (0.039) | +0.06 | 0.9542 | 0.986 | 0.00000 | 1588 | +0.051 (0.053) | 0.3351 |
| `tabla_dist8_l` | c) tabla | 2818 | +0.033 (0.040) | +0.84 | 0.4005 | 0.769 | 0.00013 | 1585 | -0.006 (0.053) | 0.9081 |
| `tabla_dist8_v` | c) tabla | 2819 | +0.043 (0.040) | +1.08 | 0.2799 | 0.723 | 0.00021 | 1588 | +0.025 (0.053) | 0.6359 |
| `tabla_dist_zona_l` | c) tabla | 2818 | +0.025 (0.039) | +0.64 | 0.5231 | 0.846 | 0.00007 | 1585 | -0.021 (0.053) | 0.6899 |
| `tabla_dist_zona_v` | c) tabla | 2819 | +0.033 (0.039) | +0.84 | 0.4004 | 0.769 | 0.00013 | 1588 | +0.007 (0.052) | 0.8921 |
| `tabla_rest_l` | c) tabla | 2981 | +0.008 (0.035) | +0.23 | 0.8165 | 0.970 | 0.00001 | 1671 | -0.025 (0.047) | 0.5876 |
| `tabla_rest_v` | c) tabla | 2981 | +0.007 (0.035) | +0.21 | 0.8312 | 0.970 | 0.00001 | 1671 | -0.024 (0.047) | 0.6052 |
| `tabla_clasificado_l` | c) tabla | 2981 | +0.033 (0.035) | +0.95 | 0.3418 | 0.755 | 0.00015 | 1671 | +0.042 (0.047) | 0.3801 |
| `tabla_clasificado_v` | c) tabla | 2981 | +0.058 (0.035) | +1.66 | 0.0965 | 0.488 | 0.00046 | 1671 | +0.014 (0.047) | 0.7606 |
| `tabla_eliminado_l` | c) tabla | 2981 | -0.083 (0.035) | -2.35 | 0.0183 | 0.253 | 0.00093 | 1671 | -0.052 (0.048) | 0.2694 |
| `tabla_eliminado_v` | c) tabla | 2981 | -0.002 (0.037) | -0.06 | 0.9498 | 0.986 | 0.00000 | 1671 | +0.004 (0.052) | 0.9422 |
| `jornada_est` | c) tabla | 2707 | -0.049 (0.036) | -1.35 | 0.1777 | 0.658 | 0.00034 | 1502 | -0.016 (0.050) | 0.7495 |
| `avance_torneo` | c) tabla | 2981 | -0.008 (0.035) | -0.22 | 0.8235 | 0.970 | 0.00001 | 1671 | +0.025 (0.047) | 0.5932 |
| `descanso_l` | d) calendario | 2978 | -0.049 (0.035) | -1.41 | 0.1579 | 0.648 | 0.00033 | 1671 | -0.078 (0.047) | 0.0964 |
| `descanso_v` | d) calendario | 2980 | -0.046 (0.034) | -1.33 | 0.1848 | 0.658 | 0.00030 | 1671 | -0.045 (0.046) | 0.3331 |
| `descanso_dif` | d) calendario | 2977 | -0.056 (0.035) | -1.60 | 0.1100 | 0.528 | 0.00043 | 1671 | -0.080 (0.047) | 0.0887 |
| `pj14_l` | d) calendario | 2981 | +0.044 (0.035) | +1.25 | 0.2097 | 0.667 | 0.00026 | 1671 | +0.049 (0.047) | 0.2999 |
| `pj14_v` | d) calendario | 2981 | +0.013 (0.035) | +0.38 | 0.7071 | 0.952 | 0.00002 | 1671 | -0.016 (0.047) | 0.7283 |
| `pj14_dif` | d) calendario | 2981 | +0.041 (0.035) | +1.18 | 0.2363 | 0.696 | 0.00024 | 1671 | +0.085 (0.047) | 0.0705 |
| `pausa_larga_l` | d) calendario | 2981 | -0.020 (0.035) | -0.56 | 0.5727 | 0.871 | 0.00005 | 1671 | +0.043 (0.048) | 0.3690 |
| `pausa_larga_v` | d) calendario | 2981 | +0.029 (0.035) | +0.82 | 0.4088 | 0.769 | 0.00011 | 1671 | +0.129 (0.048) | 0.0069 |
| `regreso_pausa` | d) calendario | 2981 | -0.004 (0.035) | -0.12 | 0.9057 | 0.986 | 0.00000 | 1671 | +0.055 (0.048) | 0.2483 |
| `primer_partido_torneo_l` | d) calendario | 2981 | -0.045 (0.034) | -1.30 | 0.1929 | 0.658 | 0.00028 | 1671 | -0.102 (0.046) | 0.0278 |
| `primer_partido_torneo_v` | d) calendario | 2981 | -0.067 (0.034) | -1.93 | 0.0542 | 0.402 | 0.00062 | 1671 | -0.129 (0.046) | 0.0053 |
| `pendientes_previos_l` | d) calendario | 2981 | sin datos suficientes |  |  |  |  | 1671 |  |  |
| `pendientes_previos_v` | d) calendario | 2981 | sin datos suficientes |  |  |  |  | 1671 |  |  |
| `media_semana` | d) calendario | 2981 | +0.063 (0.035) | +1.81 | 0.0690 | 0.437 | 0.00055 | 1671 | +0.104 (0.047) | 0.0273 |
| `dia_semana` | d) calendario | 2981 | +0.006 (0.035) | +0.16 | 0.8740 | 0.982 | 0.00000 | 1671 | -0.008 (0.048) | 0.8625 |
| `hora_local` | d) calendario | 2981 | -0.032 (0.035) | -0.92 | 0.3549 | 0.763 | 0.00014 | 1671 | -0.066 (0.048) | 0.1660 |
| `mes` | d) calendario | 2981 | -0.002 (0.035) | -0.07 | 0.9465 | 0.986 | 0.00000 | 1671 | +0.063 (0.047) | 0.1843 |
| `sede_altitud` | e) sede | 2981 | -0.040 (0.035) | -1.14 | 0.2537 | 0.696 | 0.00022 | 1671 | +0.061 (0.047) | 0.1939 |
| `sede_altura` | e) sede | 2981 | -0.034 (0.035) | -0.99 | 0.3219 | 0.755 | 0.00016 | 1671 | +0.058 (0.047) | 0.2169 |
| `sede_sintetico` | e) sede | 2981 | +0.085 (0.035) | +2.43 | 0.0145 | 0.215 | 0.00100 | 1671 | -0.031 (0.046) | 0.4995 |
| `sede_imputada` | e) sede | 2981 | -0.025 (0.036) | -0.70 | 0.4854 | 0.818 | 0.00008 | 1671 |  |  |
| `sede_habitual_l` | e) sede | 2976 | -0.068 (0.040) | -1.69 | 0.0802 | 0.437 | 0.00051 | 1670 | -0.032 (0.053) | 0.5449 |
| `sede_compartida` | e) sede | 2981 | +0.021 (0.038) | +0.55 | 0.5824 | 0.878 | 0.00005 | 1671 | -0.009 (0.050) | 0.8550 |
| `sede_tambien_v` | e) sede | 2979 | -0.026 (0.032) | -0.82 | 0.4158 | 0.769 | 0.00011 | 1670 | -0.037 (0.044) | 0.3975 |
| `sede_alt_dif_v` | e) sede | 2979 | +0.045 (0.035) | +1.30 | 0.1946 | 0.658 | 0.00028 | 1670 | +0.098 (0.047) | 0.0385 |
| `sede_viaje_km_v` | e) sede | 2979 | +0.138 (0.035) | +3.90 | 0.0001 | 0.021 | 0.00258 | 1670 | +0.029 (0.047) | 0.5394 |
| `sede_viaje_km_l` | e) sede | 2976 | +0.045 (0.047) | +0.97 | 0.2953 | 0.738 | 0.00018 | 1670 | +0.155 (0.113) | 0.0329 |
| `sede_n_l` | e) sede | 2981 | +0.023 (0.035) | +0.66 | 0.5068 | 0.839 | 0.00007 | 1671 | +0.011 (0.048) | 0.8225 |
| `sede_vl_l` | e) sede | 2981 | +0.062 (0.035) | +1.78 | 0.0750 | 0.437 | 0.00053 | 1671 | +0.016 (0.047) | 0.7282 |
| `sede_vl_rel_l` | e) sede | 2981 | +0.072 (0.035) | +2.07 | 0.0385 | 0.378 | 0.00072 | 1671 | +0.016 (0.047) | 0.7338 |
| `sede_vl_z_l` | e) sede | 2981 | -0.016 (0.035) | -0.45 | 0.6512 | 0.912 | 0.00003 | 1671 | -0.078 (0.048) | 0.1020 |
| `visita_altura_n_v` | e) sede | 2981 | -0.035 (0.038) | -0.94 | 0.3443 | 0.755 | 0.00015 | 1671 | -0.076 (0.055) | 0.1538 |
| `visita_altura_dg_v` | e) sede | 2961 | -0.057 (0.041) | -1.39 | 0.1636 | 0.658 | 0.00033 | 1665 | -0.029 (0.054) | 0.5901 |
| `visita_altura_rel_v` | e) sede | 2949 | -0.021 (0.036) | -0.59 | 0.5541 | 0.860 | 0.00006 | 1663 | +0.017 (0.047) | 0.7228 |
| `visita_sint_n_v` | e) sede | 2981 | -0.079 (0.038) | -2.08 | 0.0366 | 0.378 | 0.00073 | 1671 | -0.081 (0.052) | 0.1144 |
| `visita_sint_dg_v` | e) sede | 2612 | +0.012 (0.038) | +0.32 | 0.7459 | 0.964 | 0.00002 | 1465 | +0.006 (0.051) | 0.9029 |
| `visita_sint_rel_v` | e) sede | 2612 | +0.038 (0.037) | +1.03 | 0.3013 | 0.738 | 0.00020 | 1465 | +0.043 (0.050) | 0.3922 |
| `h2h_n` | f) h2h | 2981 | -0.011 (0.035) | -0.32 | 0.7519 | 0.966 | 0.00002 | 1671 | -0.015 (0.047) | 0.7539 |
| `h2h6_pts_l` | f) h2h | 2911 | -0.085 (0.041) | -2.05 | 0.0400 | 0.378 | 0.00072 | 1654 | -0.042 (0.053) | 0.4243 |
| `h2h6_dg_l` | f) h2h | 2911 | -0.025 (0.043) | -0.60 | 0.5499 | 0.860 | 0.00006 | 1654 | -0.007 (0.054) | 0.9044 |
| `h2h10_pts_l` | f) h2h | 2911 | -0.048 (0.041) | -1.16 | 0.2459 | 0.696 | 0.00023 | 1654 | -0.035 (0.053) | 0.5100 |
| `h2h10_dg_l` | f) h2h | 2911 | -0.001 (0.042) | -0.03 | 0.9790 | 0.991 | 0.00000 | 1654 | -0.015 (0.054) | 0.7889 |
| `h2h_sede_n` | f) h2h | 2981 | -0.013 (0.035) | -0.37 | 0.7147 | 0.952 | 0.00002 | 1671 | +0.003 (0.047) | 0.9432 |
| `h2h_sede_pts_l` | f) h2h | 2777 | +0.011 (0.039) | +0.29 | 0.7754 | 0.970 | 0.00001 | 1594 | -0.048 (0.052) | 0.3588 |
| `h2h_sede_dg_l` | f) h2h | 2777 | +0.030 (0.039) | +0.77 | 0.4406 | 0.784 | 0.00011 | 1594 | -0.062 (0.052) | 0.2353 |
| `h2h_lig_n` | f) h2h | 2981 | +0.027 (0.034) | +0.78 | 0.4368 | 0.782 | 0.00010 | 1671 | +0.017 (0.047) | 0.7191 |
| `h2h_lig_pts_l` | f) h2h | 1701 | -0.023 (0.047) | -0.49 | 0.6245 | 0.906 | 0.00007 | 958 | -0.015 (0.062) | 0.8100 |
| `h2h_lig_dg_l` | f) h2h | 1701 | -0.010 (0.049) | -0.20 | 0.8418 | 0.970 | 0.00001 | 958 | -0.044 (0.064) | 0.4957 |
| `h2h_lig_series_n` | f) h2h | 2981 | +0.028 (0.034) | +0.81 | 0.4185 | 0.769 | 0.00011 | 1671 | +0.022 (0.047) | 0.6382 |
| `h2h_lig_series_bal_l` | f) h2h | 2981 | -0.029 (0.035) | -0.84 | 0.4003 | 0.769 | 0.00012 | 1671 | -0.006 (0.047) | 0.9033 |
| `h2h_final_n` | f) h2h | 2981 | +0.067 (0.035) | +1.93 | 0.0523 | 0.402 | 0.00063 | 1671 | +0.064 (0.047) | 0.1706 |
| `h2h_final_dg_l` | f) h2h | 612 | -0.029 (0.077) | -0.38 | 0.7056 | 0.952 | 0.00012 | 348 | -0.155 (0.103) | 0.1300 |
| `h2h_final_series_n` | f) h2h | 2981 | +0.066 (0.035) | +1.91 | 0.0556 | 0.402 | 0.00061 | 1671 | +0.061 (0.047) | 0.1925 |
| `h2h_final_series_bal_l` | f) h2h | 2981 | +0.001 (0.034) | +0.02 | 0.9802 | 0.991 | 0.00000 | 1671 | -0.016 (0.046) | 0.7321 |
| `juego10_tiros_f_l` | g) juego | 2939 | +0.123 (0.036) | +3.41 | 0.0006 | 0.030 | 0.00199 | 1638 | +0.038 (0.052) | 0.4662 |
| `juego10_tiros_f_v` | g) juego | 2944 | -0.089 (0.036) | -2.47 | 0.0135 | 0.212 | 0.00104 | 1640 | -0.074 (0.050) | 0.1400 |
| `juego10_tiros_c_l` | g) juego | 2939 | -0.142 (0.037) | -3.79 | 0.0001 | 0.021 | 0.00245 | 1638 | -0.034 (0.053) | 0.5227 |
| `juego10_tiros_c_v` | g) juego | 2944 | +0.128 (0.037) | +3.46 | 0.0005 | 0.030 | 0.00204 | 1640 | +0.083 (0.053) | 0.1168 |
| `juego10_tp_f_l` | g) juego | 2939 | +0.099 (0.037) | +2.69 | 0.0071 | 0.128 | 0.00123 | 1638 | +0.053 (0.051) | 0.3037 |
| `juego10_tp_f_v` | g) juego | 2944 | -0.025 (0.037) | -0.69 | 0.4891 | 0.819 | 0.00008 | 1640 | -0.013 (0.050) | 0.7994 |
| `juego10_tp_c_l` | g) juego | 2939 | -0.067 (0.037) | -1.83 | 0.0679 | 0.437 | 0.00057 | 1638 | +0.012 (0.050) | 0.8108 |
| `juego10_tp_c_v` | g) juego | 2944 | +0.024 (0.037) | +0.64 | 0.5204 | 0.846 | 0.00007 | 1640 | -0.048 (0.051) | 0.3487 |
| `juego10_corners_f_l` | g) juego | 2939 | +0.034 (0.036) | +0.96 | 0.3372 | 0.755 | 0.00016 | 1638 | +0.024 (0.050) | 0.6308 |
| `juego10_corners_f_v` | g) juego | 2944 | -0.096 (0.035) | -2.70 | 0.0070 | 0.128 | 0.00124 | 1640 | -0.074 (0.049) | 0.1317 |
| `juego10_corners_c_l` | g) juego | 2939 | -0.119 (0.036) | -3.29 | 0.0010 | 0.040 | 0.00185 | 1638 | -0.041 (0.050) | 0.4076 |
| `juego10_corners_c_v` | g) juego | 2944 | +0.132 (0.037) | +3.62 | 0.0003 | 0.026 | 0.00224 | 1640 | +0.141 (0.051) | 0.0053 |
| `juego10_faltas_f_l` | g) juego | 2939 | +0.003 (0.035) | +0.08 | 0.9397 | 0.986 | 0.00000 | 1638 | +0.027 (0.048) | 0.5773 |
| `juego10_faltas_f_v` | g) juego | 2944 | -0.000 (0.035) | -0.01 | 0.9912 | 0.991 | 0.00000 | 1640 | +0.047 (0.048) | 0.3324 |
| `juego10_faltas_c_l` | g) juego | 2939 | +0.016 (0.035) | +0.46 | 0.6484 | 0.912 | 0.00004 | 1638 | +0.050 (0.048) | 0.2983 |
| `juego10_faltas_c_v` | g) juego | 2944 | +0.046 (0.035) | +1.31 | 0.1889 | 0.658 | 0.00029 | 1640 | +0.055 (0.047) | 0.2415 |
| `juego10_xg_f_l` | g) juego | 2939 | +0.073 (0.037) | +2.00 | 0.0458 | 0.402 | 0.00068 | 1638 | +0.064 (0.050) | 0.1974 |
| `juego10_xg_f_v` | g) juego | 2944 | +0.011 (0.036) | +0.30 | 0.7631 | 0.968 | 0.00002 | 1640 | +0.024 (0.049) | 0.6204 |
| `juego10_xg_f_dif` | g) juego | 2902 | +0.050 (0.038) | +1.31 | 0.1912 | 0.658 | 0.00029 | 1607 | +0.034 (0.053) | 0.5200 |
| `juego10_xg_c_l` | g) juego | 2939 | -0.010 (0.036) | -0.29 | 0.7696 | 0.970 | 0.00001 | 1638 | +0.050 (0.048) | 0.2998 |
| `juego10_xg_c_v` | g) juego | 2944 | -0.033 (0.036) | -0.91 | 0.3634 | 0.763 | 0.00014 | 1640 | -0.089 (0.049) | 0.0731 |
| `juego10_xg_c_dif` | g) juego | 2902 | +0.020 (0.038) | +0.53 | 0.5990 | 0.878 | 0.00005 | 1607 | +0.124 (0.051) | 0.0157 |
| `juego5_tiros_f_l` | g) juego | 2957 | +0.075 (0.036) | +2.11 | 0.0348 | 0.378 | 0.00075 | 1653 | +0.006 (0.050) | 0.9073 |
| `juego5_tiros_f_v` | g) juego | 2962 | -0.061 (0.035) | -1.72 | 0.0852 | 0.446 | 0.00050 | 1655 | -0.004 (0.049) | 0.9382 |
| `juego5_tiros_c_l` | g) juego | 2957 | -0.107 (0.037) | -2.94 | 0.0033 | 0.102 | 0.00146 | 1653 | -0.044 (0.051) | 0.3897 |
| `juego5_tiros_c_v` | g) juego | 2962 | +0.115 (0.036) | +3.19 | 0.0014 | 0.050 | 0.00172 | 1655 | +0.081 (0.051) | 0.1106 |
| `juego5_tp_f_l` | g) juego | 2957 | +0.068 (0.036) | +1.91 | 0.0564 | 0.402 | 0.00062 | 1653 | +0.049 (0.050) | 0.3230 |
| `juego5_tp_f_v` | g) juego | 2962 | -0.013 (0.036) | -0.36 | 0.7186 | 0.952 | 0.00002 | 1655 | +0.031 (0.049) | 0.5302 |
| `juego5_tp_c_l` | g) juego | 2957 | -0.057 (0.036) | -1.58 | 0.1150 | 0.542 | 0.00042 | 1653 | -0.013 (0.049) | 0.7954 |
| `juego5_tp_c_v` | g) juego | 2962 | +0.047 (0.036) | +1.31 | 0.1902 | 0.658 | 0.00029 | 1655 | -0.001 (0.049) | 0.9903 |
| `juego5_xg_f_l` | g) juego | 2957 | +0.053 (0.036) | +1.49 | 0.1361 | 0.602 | 0.00038 | 1653 | +0.066 (0.049) | 0.1753 |
| `juego5_xg_f_v` | g) juego | 2962 | +0.010 (0.036) | +0.27 | 0.7834 | 0.970 | 0.00001 | 1655 | +0.043 (0.048) | 0.3744 |
| `juego5_xg_c_l` | g) juego | 2957 | -0.019 (0.035) | -0.53 | 0.5942 | 0.878 | 0.00005 | 1653 | +0.014 (0.048) | 0.7692 |
| `juego5_xg_c_v` | g) juego | 2962 | +0.007 (0.035) | +0.20 | 0.8377 | 0.970 | 0.00001 | 1655 | -0.028 (0.048) | 0.5672 |
| `juego10_posesion_l` | g) juego | 2938 | +0.047 (0.037) | +1.28 | 0.2018 | 0.658 | 0.00028 | 1638 | -0.020 (0.052) | 0.7039 |
| `juego10_posesion_v` | g) juego | 2942 | -0.104 (0.037) | -2.82 | 0.0048 | 0.123 | 0.00135 | 1640 | -0.108 (0.051) | 0.0339 |
| `juego10_posesion_dif` | g) juego | 2899 | +0.113 (0.040) | +2.84 | 0.0045 | 0.123 | 0.00139 | 1607 | +0.063 (0.057) | 0.2687 |
| `juego10_amarillas_l` | g) juego | 2939 | -0.037 (0.035) | -1.06 | 0.2874 | 0.731 | 0.00019 | 1638 | -0.018 (0.048) | 0.7063 |
| `juego10_amarillas_v` | g) juego | 2944 | +0.045 (0.035) | +1.28 | 0.1996 | 0.658 | 0.00028 | 1640 | +0.038 (0.049) | 0.4300 |
| `juego10_xgdif_l` | g) juego | 2939 | +0.061 (0.037) | +1.63 | 0.1023 | 0.508 | 0.00045 | 1638 | +0.014 (0.051) | 0.7899 |
| `juego10_xgdif_v` | g) juego | 2944 | +0.031 (0.038) | +0.83 | 0.4057 | 0.769 | 0.00012 | 1640 | +0.080 (0.051) | 0.1190 |
| `juego10_xgdif_dif` | g) juego | 2902 | +0.025 (0.041) | +0.60 | 0.5452 | 0.857 | 0.00006 | 1607 | -0.064 (0.056) | 0.2580 |
| `juego10_suerte_f_l` | g) juego | 2939 | -0.012 (0.036) | -0.33 | 0.7404 | 0.961 | 0.00002 | 1638 | -0.017 (0.049) | 0.7324 |
| `juego10_suerte_f_v` | g) juego | 2944 | -0.008 (0.037) | -0.23 | 0.8189 | 0.970 | 0.00001 | 1640 | +0.010 (0.048) | 0.8389 |
| `juego10_suerte_c_l` | g) juego | 2939 | +0.006 (0.037) | +0.17 | 0.8622 | 0.980 | 0.00001 | 1638 | +0.017 (0.049) | 0.7274 |
| `juego10_suerte_c_v` | g) juego | 2944 | -0.007 (0.037) | -0.20 | 0.8428 | 0.970 | 0.00001 | 1640 | +0.009 (0.051) | 0.8667 |
| `juego_n_l` | g) juego | 2981 | -0.021 (0.034) | -0.63 | 0.5278 | 0.847 | 0.00007 | 1671 | -0.037 (0.044) | 0.4015 |
| `juego_n_v` | g) juego | 2981 | +0.061 (0.035) | +1.75 | 0.0818 | 0.437 | 0.00051 | 1671 | +0.123 (0.047) | 0.0096 |
| `rojas_prev_l` | h) disciplina | 2978 | -0.021 (0.034) | -0.61 | 0.5453 | 0.857 | 0.00006 | 1671 | +0.005 (0.047) | 0.9140 |
| `rojas_prev_v` | h) disciplina | 2980 | -0.007 (0.034) | -0.20 | 0.8405 | 0.970 | 0.00001 | 1671 | +0.032 (0.047) | 0.5012 |
| `susp_n_l` | h) disciplina | 2978 | -0.036 (0.034) | -1.06 | 0.2892 | 0.731 | 0.00019 | 1671 | -0.028 (0.047) | 0.5446 |
| `susp_n_v` | h) disciplina | 2980 | -0.038 (0.035) | -1.11 | 0.2686 | 0.710 | 0.00021 | 1671 | -0.033 (0.047) | 0.4792 |
| `susp_n_dif` | h) disciplina | 2977 | +0.002 (0.034) | +0.06 | 0.9507 | 0.986 | 0.00000 | 1671 | +0.005 (0.047) | 0.9177 |
| `susp_imp_l` | h) disciplina | 2977 | -0.051 (0.035) | -1.48 | 0.1385 | 0.603 | 0.00037 | 1671 | -0.041 (0.047) | 0.3917 |
| `susp_imp_v` | h) disciplina | 2978 | -0.046 (0.035) | -1.32 | 0.1871 | 0.658 | 0.00029 | 1670 | -0.049 (0.047) | 0.2967 |
| `susp_imp_dif` | h) disciplina | 2974 | -0.004 (0.035) | -0.12 | 0.9008 | 0.986 | 0.00000 | 1670 | +0.009 (0.047) | 0.8555 |
| `susp_titulares_l` | h) disciplina | 2977 | -0.063 (0.034) | -1.84 | 0.0668 | 0.437 | 0.00056 | 1671 | -0.042 (0.048) | 0.3784 |
| `susp_titulares_v` | h) disciplina | 2978 | -0.045 (0.035) | -1.29 | 0.1985 | 0.658 | 0.00028 | 1670 | -0.044 (0.047) | 0.3466 |
| `aus_conv_n_l` | h) disciplina | 2948 | -0.051 (0.034) | -1.50 | 0.1333 | 0.599 | 0.00038 | 1659 | -0.072 (0.046) | 0.1160 |
| `aus_conv_n_v` | h) disciplina | 2946 | +0.027 (0.035) | +0.76 | 0.4458 | 0.789 | 0.00010 | 1655 | -0.051 (0.047) | 0.2784 |
| `aus_conv_imp_l` | h) disciplina | 2948 | -0.050 (0.034) | -1.46 | 0.1461 | 0.617 | 0.00036 | 1659 | -0.066 (0.046) | 0.1490 |
| `aus_conv_imp_v` | h) disciplina | 2946 | +0.032 (0.035) | +0.90 | 0.3663 | 0.763 | 0.00014 | 1655 | -0.049 (0.047) | 0.3008 |
| `aus_tit_previa_l` | h) disciplina | 2948 | -0.067 (0.034) | -1.96 | 0.0504 | 0.402 | 0.00065 | 1659 | -0.083 (0.046) | 0.0729 |
| `aus_tit_previa_v` | h) disciplina | 2946 | +0.012 (0.035) | +0.35 | 0.7232 | 0.952 | 0.00002 | 1655 | -0.064 (0.047) | 0.1746 |
| `aus_tit_previa_dif` | h) disciplina | 2925 | -0.062 (0.035) | -1.79 | 0.0738 | 0.437 | 0.00055 | 1650 | -0.019 (0.047) | 0.6888 |
| `once_previa_hab_l` | i) alineación | 2960 | +0.002 (0.035) | +0.06 | 0.9534 | 0.986 | 0.00000 | 1667 | -0.026 (0.047) | 0.5729 |
| `once_previa_hab_v` | i) alineación | 2960 | -0.072 (0.035) | -2.05 | 0.0399 | 0.378 | 0.00071 | 1664 | -0.020 (0.047) | 0.6708 |
| `once_previa_hab_dif` | i) alineación | 2939 | +0.062 (0.036) | +1.74 | 0.0817 | 0.437 | 0.00052 | 1660 | -0.003 (0.048) | 0.9471 |
| `once_previa_cambios_l` | i) alineación | 2977 | +0.001 (0.035) | +0.04 | 0.9663 | 0.991 | 0.00000 | 1671 | -0.000 (0.047) | 0.9990 |
| `once_previa_cambios_v` | i) alineación | 2977 | +0.123 (0.035) | +3.55 | 0.0004 | 0.026 | 0.00213 | 1670 | +0.067 (0.046) | 0.1460 |
| `once_previa_rot5_l` | i) alineación | 2970 | +0.026 (0.035) | +0.75 | 0.4525 | 0.791 | 0.00009 | 1668 | -0.003 (0.047) | 0.9530 |
| `once_previa_rot5_v` | i) alineación | 2972 | +0.092 (0.035) | +2.61 | 0.0089 | 0.148 | 0.00115 | 1667 | -0.000 (0.047) | 0.9978 |
| `once_real_hab_l` | i) alineación | 2959 | +0.011 (0.035) | +0.31 | 0.7554 |  | 0.00002 | 1665 | +0.003 (0.047) | 0.9500 |
| `once_real_hab_v` | i) alineación | 2962 | -0.018 (0.035) | -0.50 | 0.6162 |  | 0.00004 | 1667 | +0.049 (0.047) | 0.3031 |
| `once_real_hab_dif` | i) alineación | 2944 | +0.028 (0.036) | +0.80 | 0.4257 |  | 0.00011 | 1661 | -0.038 (0.048) | 0.4362 |
| `once_real_cambios_l` | i) alineación | 2967 | -0.010 (0.035) | -0.27 | 0.7838 |  | 0.00001 | 1668 | -0.018 (0.047) | 0.6958 |
| `once_real_cambios_v` | i) alineación | 2970 | -0.020 (0.035) | -0.57 | 0.5690 |  | 0.00005 | 1671 | -0.077 (0.047) | 0.1027 |
| `once_real_aus_l` | i) alineación | 2959 | -0.052 (0.035) | -1.50 | 0.1330 |  | 0.00038 | 1665 | -0.056 (0.047) | 0.2311 |
| `once_real_aus_v` | i) alineación | 2962 | -0.017 (0.035) | -0.48 | 0.6297 |  | 0.00004 | 1667 | -0.080 (0.047) | 0.0876 |
| `once_real_aus_dif` | i) alineación | 2944 | -0.032 (0.035) | -0.92 | 0.3568 |  | 0.00014 | 1661 | +0.019 (0.047) | 0.6808 |
| `once_real_acierto_previa_l` | i) alineación | 2950 | +0.012 (0.035) | +0.35 | 0.7293 |  | 0.00002 | 1664 | +0.022 (0.047) | 0.6370 |
| `once_real_acierto_previa_v` | i) alineación | 2951 | +0.021 (0.035) | +0.59 | 0.5558 |  | 0.00006 | 1664 | +0.078 (0.047) | 0.0955 |
| `es_liguilla` | j) fase | 2981 | +0.062 (0.035) | +1.80 | 0.0708 | 0.437 | 0.00055 | 1671 | +0.072 (0.047) | 0.1250 |
| `ronda` | j) fase | 2981 | +0.061 (0.034) | +1.77 | 0.0750 | 0.437 | 0.00053 | 1671 | +0.068 (0.047) | 0.1449 |
| `pierna` | j) fase | 238 | -0.132 (0.149) | -0.88 | 0.3775 | 0.769 | 0.00164 | 135 | -0.141 (0.203) | 0.4875 |
| `es_vuelta` | j) fase | 2981 | +0.012 (0.035) | +0.34 | 0.7303 | 0.956 | 0.00002 | 1671 | -0.012 (0.048) | 0.8036 |
| `global_gf_l` | j) fase | 119 | -0.246 (0.201) | -1.22 | 0.2194 | 0.682 | 0.00634 | 68 |  |  |
| `global_gc_l` | j) fase | 119 | +0.292 (0.191) | +1.53 | 0.1194 | 0.554 | 0.01019 | 68 |  |  |
| `global_dif_l` | j) fase | 119 | -0.474 (0.214) | -2.21 | 0.0241 | 0.297 | 0.02137 | 68 |  |  |
| `sembrado_l` | j) fase | 274 | -0.013 (0.128) | -0.10 | 0.9204 | 0.986 | 0.00002 | 169 | -0.031 (0.161) | 0.8491 |
| `sembrado_v` | j) fase | 274 | -0.050 (0.137) | -0.36 | 0.7157 | 0.952 | 0.00024 | 169 | -0.106 (0.164) | 0.5157 |
| `sembrado_dif` | j) fase | 274 | +0.033 (0.152) | +0.22 | 0.8291 | 0.970 | 0.00008 | 169 | +0.072 (0.180) | 0.6892 |
| `empate_favorece_l` | j) fase | 2981 | +0.005 (0.036) | +0.13 | 0.8983 | 0.986 | 0.00000 | 1671 | -0.038 (0.049) | 0.4417 |
| `empate_favorece_v` | j) fase | 2981 | +0.080 (0.034) | +2.33 | 0.0188 | 0.253 | 0.00093 | 1671 | +0.122 (0.046) | 0.0073 |
| `regla_gol_visitante` | j) fase | 2981 | +0.069 (0.036) | +1.94 | 0.0503 | 0.402 | 0.00064 | 1671 | +0.123 (0.053) | 0.0151 |
| `ventaja_serie_l` | j) fase | 119 | -0.492 (0.216) | -2.28 | 0.0203 | 0.262 | 0.02262 | 68 |  |  |
| `lig_series6_l` | j) fase | 2981 | +0.036 (0.040) | +0.90 | 0.3694 | 0.763 | 0.00014 | 1671 | +0.017 (0.050) | 0.7280 |
| `lig_series6_v` | j) fase | 2981 | +0.047 (0.040) | +1.17 | 0.2398 | 0.696 | 0.00023 | 1671 | +0.013 (0.051) | 0.8048 |
| `lig_series6_dif` | j) fase | 2981 | -0.013 (0.051) | -0.25 | 0.8013 | 0.970 | 0.00001 | 1671 | +0.005 (0.058) | 0.9255 |
| `lig_ganadas6_l` | j) fase | 2981 | +0.037 (0.039) | +0.96 | 0.3349 | 0.755 | 0.00016 | 1671 | +0.018 (0.049) | 0.7148 |
| `lig_ganadas6_v` | j) fase | 2981 | +0.050 (0.039) | +1.29 | 0.1962 | 0.658 | 0.00028 | 1671 | +0.038 (0.050) | 0.4477 |
| `lig_ganadas6_dif` | j) fase | 2981 | -0.013 (0.046) | -0.28 | 0.7826 | 0.970 | 0.00001 | 1671 | -0.017 (0.054) | 0.7513 |
| `finales10_l` | j) fase | 2981 | +0.050 (0.039) | +1.27 | 0.2037 | 0.658 | 0.00027 | 1671 | -0.016 (0.051) | 0.7498 |
| `finales10_v` | j) fase | 2981 | -0.005 (0.038) | -0.13 | 0.8935 | 0.986 | 0.00000 | 1671 | +0.003 (0.051) | 0.9534 |
| `finales10_dif` | j) fase | 2981 | +0.050 (0.045) | +1.12 | 0.2629 | 0.702 | 0.00021 | 1671 | -0.016 (0.057) | 0.7722 |
| `titulos10_l` | j) fase | 2981 | -0.000 (0.037) | -0.01 | 0.9904 | 0.991 | 0.00000 | 1671 | -0.078 (0.049) | 0.1158 |
| `titulos10_v` | j) fase | 2981 | -0.029 (0.037) | -0.78 | 0.4325 | 0.780 | 0.00010 | 1671 | -0.016 (0.049) | 0.7422 |
| `mercado_p_l` | k) mercado | 1671 | +0.637 (0.083) | +7.64 | 0.0000 |  | 0.01794 | 0 |  |  |
| `mercado_p_e` | k) mercado | 1671 | -0.209 (0.055) | -3.76 | 0.0001 |  | 0.00430 | 0 |  |  |
| `mercado_p_v` | k) mercado | 1671 | -0.593 (0.082) | -7.21 | 0.0000 |  | 0.01593 | 0 |  |  |
| `mercado_margen` | k) mercado | 1671 | +0.086 (0.047) | +1.84 | 0.0650 |  | 0.00102 | 1671 | +0.074 (0.047) | 0.1170 |
| `mercado_abre_p_l` | k) mercado | 0 | sin datos suficientes |  |  |  |  | 0 |  |  |
| `mercado_abre_p_e` | k) mercado | 0 | sin datos suficientes |  |  |  |  | 0 |  |  |
| `mercado_abre_p_v` | k) mercado | 0 | sin datos suficientes |  |  |  |  | 0 |  |  |
| `mercado_linea` | k) mercado | 1668 | +0.063 (0.047) | +1.33 | 0.1832 |  | 0.00053 | 1668 | +0.047 (0.048) | 0.3204 |
| `mercado_p_over` | k) mercado | 1643 | -0.007 (0.047) | -0.16 | 0.8754 |  | 0.00001 | 1643 | -0.024 (0.048) | 0.6151 |
| `mercado_abre_p_over` | k) mercado | 0 | sin datos suficientes |  |  |  |  | 0 |  |  |
| `mercado_dudoso` | k) mercado | 1677 | +0.086 (0.052) | +1.65 | 0.0801 |  | 0.00091 | 0 |  |  |
| `n_prev_l` | l) otros | 2981 | +0.046 (0.037) | +1.24 | 0.2154 | 0.677 | 0.00026 | 1671 | +0.007 (0.050) | 0.8876 |
| `n_prev_v` | l) otros | 2981 | -0.057 (0.038) | -1.51 | 0.1317 | 0.599 | 0.00038 | 1671 | -0.048 (0.052) | 0.3531 |
| `poca_historia_l` | l) otros | 2981 | -0.038 (0.035) | -1.08 | 0.2810 | 0.723 | 0.00019 | 1671 | +0.017 (0.045) | 0.7075 |
| `poca_historia_v` | l) otros | 2981 | +0.005 (0.037) | +0.14 | 0.8884 | 0.986 | 0.00000 | 1671 | +0.031 (0.052) | 0.5450 |
| `recien_ascendido_l` | l) otros | 2981 | -0.007 (0.035) | -0.22 | 0.8295 | 0.970 | 0.00001 | 1671 | +0.031 (0.046) | 0.4943 |
| `recien_ascendido_v` | l) otros | 2981 | -0.012 (0.036) | -0.34 | 0.7332 | 0.956 | 0.00002 | 1671 | +0.042 (0.055) | 0.4343 |
| `arb_n` | l) otros | 1456 | -0.025 (0.050) | -0.50 | 0.6163 | 0.899 | 0.00009 | 1129 | -0.028 (0.058) | 0.6273 |
| `arb_tarjetas` | l) otros | 1456 | +0.001 (0.051) | +0.02 | 0.9866 | 0.991 | 0.00000 | 1129 | +0.020 (0.058) | 0.7299 |
| `arb_penales` | l) otros | 1456 | -0.044 (0.050) | -0.88 | 0.3813 | 0.769 | 0.00026 | 1129 | -0.029 (0.057) | 0.6096 |
| `asistencia5_l` | l) otros | 2770 | +0.070 (0.040) | +1.76 | 0.0774 | 0.437 | 0.00056 | 1488 | +0.001 (0.055) | 0.9915 |

## 6. Limitaciones y pendientes

- **Lesionados**: no hay dato. `aus_conv_*` (titulares habituales fuera de la lista anterior) es un indicio, no un
  parte médico; `config/actualidad.json` no se usa aquí.
- **Sanciones de varios partidos**: sólo se deduce un partido por expulsión; las de 5 amarillas sólo desde el
  Apertura 2021.
- **Descanso y viaje sólo ven la liga**: Leagues Cup, Concacaf e Intercontinental no están en la base (la pausa de
  la Leagues Cup aparece como descanso largo).
- **Importancia de un ausente = cuánto juega**, no qué tan bueno es. Una medida de calidad (goles, minutos,
  valor) queda para una segunda versión.
- **Sedes**: coordenadas y altitud de los 16 inmuebles actuales vienen de `web/medios_parts`; las de sedes
  históricas, de Wikipedia + modelo de elevación (±20 m); el Estadio Municipal de Aguascalientes (2 partidos de
  2002) es aproximado. Un `estadio_id` nuevo de ESPN se imputa a la sede habitual y `python3 variables.py` avisa.
- **Tabla**: desempates por puntos, diferencia de goles, goles a favor y nombre (sin goles de visitante, fair play
  ni cociente); no aplica la resta de 3 puntos por la regla de menores ni exclusiones administrativas.
- **Era de grupos (hasta Clausura 2011)**: la clasificación por grupos se aproxima con los 8 primeros de la general
  (es calentamiento).
- **Elo de referencia**: un equipo que regresa (Atlante 2026) conserva su Elo de hace años; es una base simple, no
  la fuerza a usar en el modelo final.
- **Momios de apertura**: sólo existen desde 2026 (no hay en DESARROLLO).
- **El análisis exploratorio es univariado**: no mide interacciones (p. ej. altitud × origen del visitante más allá
  de la diferencia de altitud) ni efectos sobre goles de cada lado por separado.
