# Mapa del repo previo (Cerebro Liga MX, agosto 2026)

Reconocimiento del 2026-11-10. Sólo lectura de la raíz (`/home/user/SA`); nada se modificó. **[verificado]** = se
comprobó corriendo el código original en memoria (sin escribir archivos); **[doc]** = sólo consta en documentos
previos y no se pudo comprobar. Leído: `ARQUITECTURA.md`, `DOMINIO.md` (sólo opciones de publicación),
`cerebro_ligamx_2026.py` (motor), `generar.py`, `proyeccion.py`, `config/jornadas.json`, `analisis/`, `desempeno/`,
`golden/`, `docs/`, `historico_ligamx.csv`, `historico_ht_ligamx.csv`, `leagues_cup_2026.csv`.

## 1. Replicar EXACTAMENTE el modelo original (línea base "Cerebro original")

### 1.1 Parámetros (`cerebro_ligamx_2026.py:62-90`)
- `MAX_GOLES = 10` (malla 11×11 renormalizada) · `RHO_DC = -0.11` (fijo, no se estima) · `MU_GLOBAL = 2.91`.
- `XI_DECAIMIENTO = 0.0038` por día (vida media 182 días) · `PESO_LIGUILLA = 1.25` · `PROP_GOLES_1T = 0.4442`.
- `VENTAJA_LOCAL_BASE = 1.28` sólo inicializa la localía. `N_SIMULACIONES = 100_000` y `RNG` (semilla 20260716)
  son el Monte Carlo del script original; `generar.py` no lo usa.

### 1.2 Calibración (`fit_dixon_coles`, líneas 379-435)
- Parámetros `atk[n]`, `dfn[n]`, `home`, con `n` = TODOS los equipos del archivo (27 con el CSV original).
- `lam = exp(atk_l + dfn_v + home)·MU_GLOBAL/2`; `mu = exp(atk_v + dfn_l)·MU_GLOBAL/2`.
- Log-verosimilitud Poisson con peso `exp(-xi·días)·(1.25 si fase == "liguilla")`, más `log(tau)` (recortado a
  1e-10) en marcadores con ambos ≤ 1, más penalización `1000·(media(atk)² + media(dfn)²)` sobre los `n` equipos.
- Arranque en ceros (`home = log 1.28`); `scipy.optimize.minimize(method="L-BFGS-B")` con gradiente numérico.
- Devuelve `{equipo: (exp(atk), exp(dfn))}`; defensa > 1 = concede más. La localía estimada se imprime y **se
  descarta** (línea 434).

### 1.3 Capas de `lambdas_partido` (líneas 277-336)
1. Base: `lam_l = BASE_HOME_GOALS·atk_l·def_v`, `lam_v = BASE_AWAY_GOALS·atk_v·def_l`. Las bases son la media SIN
   ponderar de goles de local y de visita en fase regular de todo el entrenamiento (≈ 1.485 y 1.154).
2. Localía por estadio: `lam_l *= LOCALIA_ESTADIO[local]` (tabla a mano, 1.01 a 1.10; líneas 142-161).
3. Escudo (172-179): local en `FACTOR_ESCUDO` → `lam_v /= f`; visitante → `lam_l /= f` (América 1.05; Chivas,
   Cruz Azul y Tigres 1.03; Pumas y Monterrey 1.02).
4. H2H: sólo `("Tijuana","Tigres")` → `lam_l ×1.04`, `lam_v ×0.98` (línea 193).
5. DT: `REGLAS_DT` está vacío (sin efecto).
6. Actualidad: factor `f` del equipo → su lambda `×f`, la del rival `÷√f`. En `generar.py` sale del bloque
   `ajustes` de la jornada; sólo la J2 tuvo (América 0.94, Chivas 0.96, Puebla 0.97, Juárez 0.97, Tigres 0.95,
   Monterrey 0.98, Atlante 0.96). El resto de jornadas va sin ajustes.

`generar.py:92-133` (`bitacora`) repite estas capas por su cuenta (sin la 5) en vez de llamar al motor: hoy dan lo
mismo, pero son dos copias de la misma lógica.

Después: `matriz_marcadores` (Poisson independientes × tau en la esquina 2×2, renormalizada); 1X2 exacto con
`np.tril(M,-1).sum()`, `np.trace(M)`, `np.triu(M,1).sum()`; pick = argmax; marcador = moda de la esquina 6×6.

### 1.4 Credibilidad (`generar.py:55-89`; config `modelo.credibilidad = {activa: true, k: 4, p: 3}`)
- `w` = suma de los pesos del MLE sobre los partidos del equipo anteriores al corte.
- `Z = w^p / (w^p + k^p)`; `log(rating) = Z·log(MLE) + (1-Z)·log(prior)`, ataque y defensa por separado, hacia
  `PRIORS_ILUSTRATIVOS` (motor, 113-133). Sólo para los 18 de `C.EQUIPOS`; equipo sin partidos = su prior.
- Se marca "incertidumbre" si `Z < 0.7` (`generar.py:197`). Al corte 2026-08-15 **[verificado]**: Atlante `w = 2.76`,
  `Z = 0.247` (ataque 1.516 → 0.893); los otros 17 tienen `Z` entre 0.865 y 0.943.

### 1.5 Corte sin fuga (`generar.py:147-159`)
`corte` = primera fecha de la jornada; `entrena` = partidos con `fecha < corte`; bases, MLE (`hoy=corte`) y pesos se
calculan sólo con `entrena`. Es por JORNADA: un partido reprogramado (Querétaro-Monterrey, 14-nov) quedaría cortado
en la fecha original de su jornada. En el proyecto nuevo el corte debe ser por partido.

### 1.6 Receta mínima desde otro módulo
```python
import sys, io, contextlib
sys.dont_write_bytecode = True                     # no dejar __pycache__ en la raíz
sys.path.insert(0, "/home/user/SA")
import cerebro_ligamx_2026 as C
import generar as G                                # importarlo no escribe nada (sólo main() escribe)
CRED = {"activa": True, "k": 4, "p": 3}

def ajustar(partidos, corte):
    """partidos: dicts {fecha: date, local, visitante, gl, gv, fase: 'regular'|'liguilla'}, nombres canónicos."""
    entrena = [p for p in partidos if p["fecha"] < corte]
    reg = [p for p in entrena if p["fase"] == "regular"]
    bases = (sum(p["gl"] for p in reg) / len(reg), sum(p["gv"] for p in reg) / len(reg))
    C.BASE_HOME_GOALS, C.BASE_AWAY_GOALS = bases
    with contextlib.redirect_stdout(io.StringIO()):                 # fit_dixon_coles imprime
        crudos = C.fit_dixon_coles(entrena, hoy=corte)              # SIEMPRE pasar hoy
    for e in C.EQUIPOS:
        crudos.setdefault(e, C.PRIORS_ILUSTRATIVOS[e])
    ratings, _ = G.aplicar_credibilidad(crudos, G.pesos(entrena, corte), CRED)
    return ratings, bases

def predecir(local, visitante, ratings, bases):
    C.BASE_HOME_GOALS, C.BASE_AWAY_GOALS = bases                    # estado global del módulo: fijarlo siempre
    lam_l, lam_v, _ = C.lambdas_partido(local, visitante, ratings, jornada_actual=False)
    M = C.matriz_marcadores(lam_l, lam_v)                           # M[x, y] = P(local x, visita y)
    return lam_l, lam_v, M, G.prob_exacta(M)                        # (p_local, p_empate, p_visita)
```
Comprobado **[verificado]**:
- La receta reproduce `docs/datos/j04.json` con diferencia máxima de 0.00005 en 1X2 (redondeo).
- `G.genera_jornada(bloque, historico, cfg["modelo"], cfg["torneo"])` devuelve un dict IDÉNTICO a los JSON
  publicados de J1, J2, J3, J4 y J7, sin escribir archivos (7 a 12 s por jornada).
- El golden de la J2 sale con `golden/historico_ligamx_4996.csv`, `hoy=date(2026,8,14)`, sin credibilidad y con
  `jornada_actual=True` (ajustes de la J2 escritos en el módulo): lambdas a 0.0004, 1X2 a 0.0028 (ruido del MC).
- Un ajuste tarda 3 a 5 s con 5,014 partidos y 27 equipos (numpy 2.5, scipy 1.18).

Trampas:
- `lambdas_partido` trae `jornada_actual=True` por defecto y aplicaría los ajustes de la J2 (`AJUSTES_JORNADA`,
  216-224). Usar `jornada_actual=False` o `C.AJUSTES_JORNADA = {}`.
- **El resultado depende de la ventana de historia aunque esos partidos pesen cero** (5.2-a). Para replicarlo hay
  que alimentarlo desde 2010-07-23, con los desaparecidos y con los nombres del CSV (Chiapas, Morelia, San Luis,
  Tecos, Leones Negros, Lobos BUAP, Dorados, Veracruz, Mazatlán).
- `fase` sólo vale `regular` o `liguilla`. En el CSV "liguilla" incluye repechaje y play-in (18 partidos por
  torneo en 2020-2023, 17 desde Apertura 2023) y, si hubo tiempo extra, el marcador de 120 minutos
  (`parsear_openfootball.py:43-48`). Con ESPN hay que mapear `season.slug` a esas dos etiquetas.
- Nombres con acento exactos: si no coinciden, localía, escudo y credibilidad se saltan en silencio.
- **Fuga al usarlo hacia atrás:** priors, localía, escudo y H2H se escribieron en julio de 2026 sabiendo lo
  ocurrido en 2025-26; antes del 2026-07-16 la versión "exacta" ve el futuro (del orden de 6 a 13% del peso va al
  prior). Propuesta: (A) "original exacto" evaluado sólo en Apertura 2026 desde la J4 (el código quedó congelado
  el 14-ago-2026, así que de ahí en adelante es fuera de muestra legítimo); (B) "algoritmo original sin priors ni
  capas" para temporadas anteriores (`analisis/backtest_k.py` hace algo así: encoge hacia 1).

## 2. Matemática reutilizable

### 2.1 Joint de mitades por adelgazamiento de Poisson (`_joint_mitades`, 567-592)
- Local 1T ~ Poisson(`lam_l·p`), local 2T ~ Poisson(`lam_l·(1-p)`), igual la visita, `p = 0.4442` para ambos
  (local 44.5%, visita 44.3%). Producto → tensor `J[h1, a1, h2, a2]`, 8 valores por eje (4,096 celdas).
- Tau se aplica como peso sobre el marcador FINAL `(h1+h2, a1+a2)` y se renormaliza: el marginal de tiempo
  completo coincide con `matriz_marcadores`. **[verificado]** diferencia máxima en 1X2: 0.000004 con λ=(1.83, 0.71)
  y 0.000033 con λ=(3.0, 2.5); masa fuera de la malla ≤ 3.4e-4.
- **[verificado]** con `historico_ht_ligamx.csv` (2,047 partidos, 2018-07-20 a 2024-09-18): 2,433/5,477 = 0.4442;
  P(gol en 1T) observado 68.93%.
- Generaliza a cualquier partición (tramos de 15 minutos, antes o después del minuto X) repartiendo cada lambda.
  Con los minutos de gol de ESPN se puede estimar el reparto por tramo y por local/visita. Supuesto que queda: los
  goles de un tramo no dependen del marcador previo.

### 2.2 Catálogo de mercados (`_catalogo_legs`, 595-626)
22 legs, cada uno un predicado sobre `(h1, a1, h2, a2)`, en 10 familias:
- `RES`: gana local, gana visita, local o empate, empate o visita, no hay empate.
- `TOT`: más de 1.5, más de 2.5, menos de 2.5, menos de 3.5. `BTS`: ambos anotan sí / no.
- `EQL`, `EQV`: el equipo anota 2+ / menos de 1.5. `T1G`: gol en 1T / sin goles en 1T. `T1T`: menos de 1.5 en 1T.
- `T2G`: más de 0.5 en 2T. `RHT`: local o empate / empate o visita al descanso. `TMM`: 2T con más goles que 1T.
- No modelado antes: tarjetas, córners, goleador, minuto de gol. ESPN ya los trae, pero el joint de goles no los
  cubre: necesitan modelo propio y medir si son independientes de los goles.

### 2.3 Probabilidad conjunta exacta (`_prob_conjunta`, 629-648)
- Dentro de un partido: suma de `J` sobre las celdas donde TODOS los predicados se cumplen (captura la correlación
  entre legs, incluso 1T contra tiempo completo). Entre partidos: producto. Es justo lo que pide la combinada de
  4 picks del mismo partido.
- Costo **[verificado]**: ~2 ms por evaluación (bucle Python). Las 7,315 combinaciones de 4 legs de un partido
  serían ~15 s; conviene una máscara booleana por leg y `J[m1 & m2 & m3 & m4].sum()`.
- Selección previa (651-722), por jornada y no por partido: voraz que maximiza `nº de picks × P(todos)` con legs
  en [0.58, 0.85], máximo 2 por partido, sin repetir familia; "seguro" y "agresivo" agregan por confianza hasta
  un piso de probabilidad conjunta (0.45 y 0.18).

### 2.4 Legs que se implican lógicamente
`ARQUITECTURA.md §3.2` documentó 3 pares que el filtro "misma familia" (línea 666) no ve. Sobre el catálogo
completo **[verificado]** son 7 implicaciones entre familias distintas:

| Leg A | ⟹ Leg B | Familias |
|---|---|---|
| Ambos anotan: Sí | Más de 1.5 goles | BTS / TOT |
| Local anota 2+ · Visita anota 2+ | Más de 1.5 goles | EQL, EQV / TOT |
| Sin goles en el 1T | Menos de 1.5 goles 1T | T1G / T1T |
| Sin goles en el 1T | Local o empate al descanso · Empate o visita al descanso | T1G / RHT |
| 2T con más goles que 1T | Más de 0.5 goles 2T | TMM / T2G |

- Si A ⟹ B, `P(A y B) = P(A)`: el número publicado es correcto, pero B es un pick "gratis" y el objetivo `n × P`
  siempre lo toma. Con λ realistas, 5 de los 7 pares caben con ambos legs en [0.58, 0.85].
- No hay pares mutuamente excluyentes entre familias distintas **[verificado]**.
- Filtro general: al agregar un leg a un conjunto S, rechazarlo si `P(S ∪ {leg}) ≥ P(S) - ε` (implicado) o si
  `P(S ∪ {leg}) = 0` (contradictorio). En agosto quedó como decisión pendiente del usuario (§10.3); para 4 picks
  del mismo partido es indispensable.
- `desempeno/j02.md`: las tres variantes de parlay compartían patas y cayeron por el mismo leg: medir traslape.

## 3. `proyeccion.py`: supuestos y lo que le falta

Supuestos:
- Tabla 3/1/0; desempate por puntos → diferencia de goles → goles a favor → **sorteo** (178-179).
- Clasifican los 8 primeros, sin play-in (`CLASIFICAN = 8`; config `play_in: false`). Es lo que asumió la versión
  previa para Apertura 2026: confirmar contra `config/torneo.json`.
- Cuartos 1-8, 2-7, 3-6, 4-5 a ida y vuelta, ida en casa del peor sembrado; global empatado → avanza el mejor
  sembrado, sin gol de visitante (190-195). Semifinales resembradas (200-202).
- Final a ida y vuelta; global empatado → penales 50/50 (211). Sin tiempos extra.
- Cada partido se sortea de la matriz con `lambdas_partido(jornada_actual=False)`: lambdas de fase regular.
- En agosto no se conocían los cruces de J11+ y se sorteaban 200 orientaciones local/visita válidas
  (`orientacion_valida`; `NUEVE_LOCALES` en `generar.py:277`). Ya no hace falta: ESPN da el calendario.
- 20,000 simulaciones, semilla 20260814. Salida por equipo: campeón, finalista, clasifica, líder, puntos esperados.

Le falta:
- **Incertidumbre de parámetros:** los ratings son un punto fijo en todas las simulaciones, así que el favorito
  sale sobreconfiado. Hay que sortear los ratings por simulación (bootstrap o posterior).
- **Tiempos extra** en la final antes de los penales, y penales que no sean 50/50 fijo.
- **Criterios oficiales** de desempate después de goles a favor y reglas vigentes de liguilla (play-in, sembrado,
  sedes): tomarlos de `config/torneo.json`; aquí no se verificaron.
- **Efecto liguilla:** goles, localía y la vuelta condicionada al marcador de la ida (los dos partidos se sortean
  independientes). El CSV previo trae 442 partidos de liguilla, pero mezcla formatos y reglas de distintas épocas.
- **Pronóstico por serie:** probabilidad de avanzar en cada cruce, global probable, cruces más probables.
- Bajas, suspensiones, descanso; historial sellado (`proyeccion.json` se sobrescribe en cada corrida).
- **Error [verificado] `generar.py:296-306`:** los partidos programados SIN resultado (J4-J10, 63) no entran ni
  como jugados ni como restantes. `proyeccion.json` dice 27 jugados + 63 restantes = 90, no 153: a cada equipo se
  le simularon 7 partidos en lugar de 14 (América: 7 puntos y sólo 20.2 esperados al final). Las probabilidades
  de campeón de agosto (América 43.8%) están mal calculadas: no mostrarlas como historial.

## 4. Desempeño sellado de lo ya publicado

Convención de Brier (`generar.py:205-210, 404`): **multicategoría**, suma de `(p - o)²` sobre los 3 resultados,
rango 0 a 2, azar uniforme = 0.667. Por jornada = media de sus partidos. Acumulado = media de las medias por
jornada (`generar.py:401`), igual a la media por partido sólo si todas las jornadas califican los mismos partidos.

Sólo hay 3 jornadas calificadas (27 partidos), en `docs/datos/j01.json` a `j03.json` e `indice.json`. Brier,
log-loss y RPS recalculados aquí desde las probabilidades guardadas **[verificado]** (RPS dividido entre 2, azar
0.222):

| Jornada | Origen | Corte | Aciertos | Exactos | Brier | Log-loss | RPS | Parlays |
|---|---|---|---|---|---|---|---|---|
| J1 | reconstruido | 2026-07-16 | 5/9 | 1 | 0.5567 | 0.9555 | 0.2368 | 1 falló; 2 sin dato de mitades |
| J2 | **publicado** | 2026-07-21 | 4/9 | 0 | 0.7053 | 1.2065 | 0.2732 | fallaron los 3 |
| J3 | reconstruido | 2026-07-31 | 5/9 | 0 | 0.6214 | 1.0742 | 0.2305 | fallaron los 3 |
| **Total** | | | **14/27 (51.9%)** | **1** | **0.6278** | 1.0787 | 0.2468 | 0 pegados |

- **Sólo la J2 se publicó antes de jugarse** (`golden/pronostico_j2_apertura2026.csv`, 1X2 por Monte Carlo). J1 y
  J3 se reconstruyeron el 14-ago con corte anterior a cada jornada.
- **Dos versiones de la J1:** `ARQUITECTURA.md §12` y `desempeno/j02.md` citan 6/9, 1 exacto, Brier 0.568
  (acumulado 15/27 y 0.632) **[doc]**; ese pronóstico no está en el repo. Lo que hay en `docs/datos` es la
  reconstrucción (5/9, 0.5567). Mostrar la que tiene archivo y decirlo.
- Detalle de la J2 en `desempeno/j02.md`. Los legs de mitades quedaron "sin_dato" por no capturar el medio
  tiempo; con los goles por minuto de ESPN ya se pueden calificar.
- J4-J10 tienen JSON generado el 14-ago-2026 (commit `dee0269`, historia hasta el 02-ago) sin resultado cargado.
  La J4 (15-17 ago) es anterior a sus partidos; J5-J10 usan ratings cada vez más viejos. Se pueden calificar hoy
  con ESPN como "congelado al 14-ago", pero no son desempeño sellado.
- Referencia no publicada: `analisis/backtest_k.py` corrido aquí tal cual **[verificado]**: 681 partidos
  (2023-08-01 a 2026-08-02, ajuste mensual, sin credibilidad, con capas): Brier 0.5931, log-loss 0.9955, RPS
  0.2062, aciertos 51.1%. Usa el CSV con el hueco de 2025-26 (5.2-c).

## 5. Decisiones con el usuario y errores o limitaciones

### 5.1 Decisiones que conviene respetar
- **Sellado:** el pronóstico se fija antes del partido; después sólo se agrega el resultado observado. Nunca se
  recalcula algo ya jugado. Cada JSON dice con qué corte e historia se calculó.
- **JavaScript no calcula probabilidades**, sólo formatea (`docs/app.js:3`); 4 decimales en JSON, 1 en pantalla.
- **Honestidad de datos:** lo no modelado se lista (`no_modelado`); las bajas no se inventan (ajustes vacíos si no
  se capturaron); equipos con poco histórico se marcan; se distingue "publicado" de "reconstruido".
- **Atlante** conserva su historia 2010-2014 (138 partidos; hoy pesan ~1e-6) y **no hereda de Mazatlán** (entidad
  aparte: 172 partidos, 2020-07-27 a 2025-04-19). El comentario de `cerebro_ligamx_2026.py:110` aún dice
  "franquicia ex-Mazatlán".
- **Credibilidad `k=4, p=3`** en lugar de `k=10, p=1` (`analisis/credibilidad.md`). El prior dentro de la
  verosimilitud quedó propuesto, no hecho.
- **Leagues Cup aparte** (54 partidos en `leagues_cup_2026.csv`): mezclarla movía los ratings 13.3% en promedio.
- **Brier con convención escrita** y aviso de muestra chica (9 partidos = ±16 puntos): vale el acumulado.
- Sitio estático con contrato JSON (`esquema: cerebro-ligamx/v1`); `indice.json` es el único archivo mutable.
- Quedaron abiertas en agosto: filtro de implicación en parlays y agregar RPS al desempeño.

### 5.2 Errores y limitaciones (archivo:línea)
- **a.** **Escala inconsistente** `cerebro_ligamx_2026.py:406-407` contra `291-292`, y `418`. El MLE ajusta con
   `MU_GLOBAL/2 × localía estimada`; producción multiplica esos ratings por `BASE_HOME/AWAY_GOALS`. Además la
   penalización de media cero abarca los 27 equipos: los desaparecidos de peso ≈ 0 absorben el nivel (varios con
   rating ≈ 1.34) y los 18 activos quedan con media geométrica 0.964 en ataque y 0.886 en defensa. **[verificado]**
   al corte 2026-08-15: lo observado ponderado es 1.51 + 1.31 = 2.82 goles; el propio MLE implica 2.89; las
   lambdas de producción promedian 1.39 + 1.04 = 2.43 en los 306 cruces: **subestima los goles ~14%** (visitante
   ~20%). Y depende de la ventana: con historia desde 2022-07 (19 equipos) los goles esperados de la J4 suben de
   2.48 a 2.96 y el 1X2 se mueve hasta 4.5 puntos, aunque los partidos viejos pesan menos de 1%.
- **b.** `generar.py:84-85`: la credibilidad mezcla ratings MLE (media ≠ 1) con priors en escala de media 1 (América,
   defensa MLE 0.408 contra prior 0.85).
- **c.** **Hueco de 417 días en `historico_ligamx.csv`** **[verificado]**: salta del 2025-05-25 al 2026-07-16. Faltan
   completos Apertura 2025 y Clausura 2026; el modelo de agosto calibró sin la temporada 2025-26.
- **d.** **Pocos datos efectivos** (`cerebro_ligamx_2026.py:71, 392-396`): al corte de la J4 el peso total es 74
   partidos (24.9 son de los 27 jugados en 2026) para 55 parámetros.
- **e.** `cerebro_ligamx_2026.py:387`: sin `hoy` usa `date.today()` (no reproducible). Línea 393: un partido con fecha
   posterior a `hoy` recibiría peso > 1; la única guarda es el corte de `generar.py`.
- **f.** `cerebro_ligamx_2026.py:510-512`: 1X2 por Monte Carlo en el script original (±0.0015); `generar.py:136` ya usa
   el exacto. `923-925`: comentario falso (Atlante sí tiene histórico; el `setdefault` no se dispara).
- **g.** `cerebro_ligamx_2026.py:142-196`: localía, escudo y H2H son multiplicadores a mano, nunca estimados; `70`: `rho`
   fijo; `72`: peso de liguilla sin validar; `86`: reparto de mitades constante con datos hasta 2024.
- **h.** **Sellado parcial** `generar.py:46, 163-165, 176-184`: el snapshot "publicado" está cableado al CSV de la J2;
   las demás jornadas se recalculan en cada corrida (deterministas por el corte, pero un cambio de código o de
   config las reescribe). En `j02.json` sólo `prob`, `pick` y `marcador_probable` vienen del sello; lambdas, top
   de marcadores, bitácora y parlays se recalcularon con otra configuración **[verificado]**: Atlante-América
   λ sellado 0.400/1.219 contra 0.483/1.533 en el JSON; parlays del JSON (6 picks/36.9%, 4/46.6%, 10/18.8%)
   distintos de los publicados (5/47.2%, 4/49.2%, 10/18.5%). `generar.py:32`: `hashlib` se importa pero el hash
   del histórico nunca se escribe.
- **i.** `generar.py:239`: `pego` nunca vale `True` (`None if pendiente else (False if fallo else None)`);
   `parlays_pegados` (267) siempre da 0. `225-230`: legs de mitades sin calificar.
- **j.** `generar.py:296-306`: error de la proyección (sección 3).
- **k.** `generar.py:152-153, 287-288`: las bases son globales del módulo que se pisan entre llamadas, y son medias sin
   ponderar de toda la historia (1.485/1.154 contra 1.51/1.31 ponderado). `392`: `datetime.now()` sin zona.
- **l.** `analisis/backtest_k.py:19-21`: importa `cerebro` desde el scratchpad de una sesión vieja; no corre tal cual
   (aquí se corrió inyectando el módulo real en `sys.modules`).
- **m.** `config/jornadas.json`: fixture sólo de J1-J10 y resultados sólo de J1-J3; el sitio previo quedó detenido el
   14-ago-2026.
- **n.** `docs/LEEME.md`, `DOMINIO.md` y `golden/README.md` traen usuario y rutas personales: no copiarlos a archivos
   nuevos ni a peticiones externas.
