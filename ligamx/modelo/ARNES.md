# Arnés de validación · Cerebro Liga MX

Banco de pruebas común para todas las familias de modelos: mismo historial, mismos cortes, mismas métricas y
mismas líneas base. Todo se corre desde la carpeta `ligamx/`. Las cifras de este documento son del periodo de
DESARROLLO (Apertura 2016 a Clausura 2025) y se generaron el 2026-11-10 con los datos de esa fecha.

| Archivo | Qué hace |
|---|---|
| `datos.py` | Carga `datos/partidos.csv` con tipos correctos, fechas UTC y locales, bloque, día, periodo y banderas de calidad. |
| `arnes.py` | Interfaz `Modelo`, `evaluar` (walk-forward), `comparar` (tabla pareada), `resumen`, `registrar`, utilidades de la matriz de marcadores y la línea de comandos. |
| `metricas.py` | Log-loss, RPS, Brier, log-verosimilitud del marcador, acierto, calibración y diferencias pareadas con bootstrap de bloques. |
| `base.py` | Líneas base: `Frecuencias`, `PoissonSimple`, `CerebroOriginal` (limpio y exacto) y `Mercado` (1X2 y marcador). |
| `pruebas/test_arnes.py` | 30 pruebas (pytest): sin fugas, métricas a mano, matriz, bloques, determinismo. |
| `pred/<nombre>.parquet` | Una fila por partido pronosticado (ver §5). `pred/ACCESOS_PRUEBA.log`: quién miró la PRUEBA. |
| `cache/M_<nombre>.npz` | Matrices 11×11 de cada pronóstico (no va a git; se regenera con `evaluar`). |
| `registro_variantes.jsonl` | Una línea por cada variante evaluada (§7). |

## 1. Protocolo

- **Periodos (por torneo).** Calentamiento: Apertura 2001 a Clausura 2016 (5,221 partidos jugados; nunca se
  califica, sólo es historial). **Desarrollo**: Apertura 2016 a Clausura 2025, 18 torneos, 2,983 jugados, 2,981
  evaluables, **510 bloques** y 1,200 días con partidos. **Prueba**: Apertura 2025, Clausura 2026 y Apertura 2026
  (480 jugados al 10-nov-2026). La PRUEBA sólo la mira el agente de selección, una vez, con candidatos declarados
  de antemano: `evaluar(..., periodo="prueba")` exige `permitir_prueba=True` y deja constancia (quién, cuándo, qué
  modelo) en `pred/ACCESOS_PRUEBA.log`; leer esas predicciones con `leer_pred` también queda anotado.
- **Bloques.** Los cortes son cada lunes 00:00 y cada viernes 00:00, hora de la Ciudad de México. Un partido
  pertenece al último corte anterior a su inicio: la jornada de fin de semana (viernes a domingo) es un bloque y la
  de media semana (lunes a jueves) es otro. En desarrollo un bloque tiene 5.8 partidos en promedio (199 bloques de 9,
  83 de uno solo) y sólo en 3 casos de 5,963 un equipo juega dos veces dentro del mismo bloque (reprogramados de
  2021). Cada partido se pronostica con lo ocurrido **antes del corte de su bloque**. Granularidad `dia`: el corte es
  el inicio del día local del partido (para el modelo final, que se recalcula después de cada día de partidos).
  Ningún partido de desarrollo empieza a menos de 2 horas de un corte de bloque (3 a menos de 2 horas de la medianoche).
- **Lo que ve el modelo.** `ajustar(hist, corte)` recibe todos los partidos jugados con `fecha_utc < corte` (las 100
  columnas de `datos.cargar()`: marcador, medio tiempo, estadísticas, momios, etc. de partidos PASADOS).
  `datos.tabla("goles" | "tarjetas" | "alineaciones", hist)` da esas tablas restringidas a los partidos de `hist`.
  `predecir(partidos)` recibe sólo las columnas previas al partido (`datos.COLS_PREPARTIDO`): identidad, fecha, torneo,
  fase, pierna, serie, equipos, sede, árbitro y momios. Nunca el marcador ni las estadísticas del propio partido.
- **Qué se califica.** El resultado a 90 minutos (`gl`, `gv`), en todas las fases. Se excluyen de la calificación,
  pero quedan en el historial con `escritorio=True`, los dos resultados de escritorio (ids 590969 y 623106); las
  líneas base los omiten al ajustar.
- **Métrica principal**: log-loss de 1X2. Secundarias: RPS, Brier, log-verosimilitud del marcador exacto, acierto,
  calibración. Toda comparación es pareada por partido, con error estándar por bootstrap de bloques (§6).

## 2. Una familia nueva en 20 líneas

```python
# modelo/mi_familia.py      ->  python3 -m modelo.arnes evaluar modelo.mi_familia:MediaMovil --kw '{"n": 10}'
import numpy as np
from modelo.arnes import Modelo

class MediaMovil(Modelo):
    familia = "ejemplo"                       # las variantes de una familia se cuentan juntas en el registro

    def __init__(self, n=10):
        self.n, self.nombre, self.hiperparametros = n, f"media_movil_{n}", {"n": n}

    def ajustar(self, hist, corte):           # hist: partidos jugados con fecha_utc < corte
        h = hist[hist.evaluable]
        self.liga = (h.gl.mean(), h.gv.mean())
        m = sum(self.liga) / 2
        self.gf, self.gc = {}, {}
        for eq in set(h.local) | set(h.visitante):
            p = h[(h.local == eq) | (h.visitante == eq)].tail(self.n)
            gf, gc = np.where(p.local == eq, p.gl, p.gv), np.where(p.local == eq, p.gv, p.gl)
            self.gf[eq] = (gf.sum() + 3 * m) / ((len(p) + 3) * m)      # 3 partidos promedio de colchón
            self.gc[eq] = (gc.sum() + 3 * m) / ((len(p) + 3) * m)

    def predecir(self, partidos):             # un dict por partido, en el mismo orden
        return [{"lam_l": self.liga[0] * self.gf.get(l, 1) * self.gc.get(v, 1),
                 "lam_v": self.liga[1] * self.gf.get(v, 1) * self.gc.get(l, 1), "rho": 0.0}
                for l, v in zip(partidos.local, partidos.visitante)]
```

Cada pronóstico es un dict con **una** de estas formas (o `None` si el modelo no pronostica ese partido):

| Forma | Qué hace el arnés |
|---|---|
| `{"lam_l", "lam_v", "rho"}` | Arma la matriz 11×11 (Poisson + corrección Dixon-Coles con `rho`, 0 por omisión), la renormaliza y deriva todo de ella. |
| `{"M": matriz 11×11}` | `M[x, y] = P(local x, visita y)`; debe sumar 1 (tolerancia 1e-6). `lam_l`, `lam_v` opcionales (si faltan se guardan las medias de `M`). |
| `{"p1x2": [pl, pe, pv]}` | Sólo 1X2: no entra en las métricas de marcador. |

Claves extra que empiecen con `x_` (escalares) se guardan como columnas. Reglas para toda familia:

1. `nombre` único por variante (letras, números, `_`, `-`, `.`); `familia` y `hiperparametros` completos: es lo que
   queda en el registro.
2. Sólo información de `hist`. Si la familia lee otras tablas (`goles.csv`, `tarjetas.csv`, `alineaciones.csv`),
   debe filtrarlas por los `id` de `hist`. Nada de medias globales, escalados o priors calculados con todo el archivo.
3. Los momios de `partidos` existen antes del silbatazo pero son posteriores al corte: sólo los usa la referencia
   `Mercado`. Una familia que los use como variable debe declararlo en su nombre y no sirve para simular rondas futuras.
4. `ajustar` se llama 510 veces (1,200 con `dia`): conviene guardar estado y arrancar cada ajuste del anterior, o
   reajustar lo caro cada cierto número de cortes y sólo actualizar variables en los demás. Un equipo puede aparecer
   en `predecir` sin un solo partido en `hist` (recién ascendido): hay que darle un valor por omisión.
5. Para iterar rápido: `evaluar(m, torneos=["Apertura 2023", "Clausura 2024"])` (queda como `__parcial` y también se
   registra). La cifra que cuenta es la del recorrido completo de DESARROLLO.
6. Modelos lentos: correr en segundo plano con `--reanudar` (o `evaluar(m, reanudar=True)`): guarda un punto de
   control cada 20 cortes en `cache/` y, si la corrida se corta, la misma orden la retoma donde se quedó. Supone que
   el resultado de `ajustar` no depende de las llamadas anteriores (el estado sólo sirve para arrancar más rápido).
7. Si el dict trae `M` o las lambdas, el 1X2 sale siempre de la matriz (un `p1x2` adicional se ignora): resultado,
   marcador y totales de un modelo son coherentes entre sí.

## 3. Cómo correr

```bash
cd /home/user/SA/ligamx
python3 -m modelo.arnes evaluar modelo.base:PoissonSimple                       # desarrollo, por bloque
python3 -m modelo.arnes evaluar modelo.base:PoissonSimple --granularidad dia
python3 -m modelo.arnes evaluar modelo.base:PoissonSimple --kw '{"vida_media_dias": 540, "nombre": "poisson_vm540"}'
python3 -m modelo.arnes evaluar modelo.base:PoissonSimple --torneos "Apertura 2023,Clausura 2024"   # parcial
nohup python3 -m modelo.arnes evaluar modelo.base:CerebroOriginal --reanudar > modelo/cache/original.log 2>&1 &   # lento
python3 -m modelo.arnes comparar poisson_simple cerebro_original_limpio --referencia mercado_cierre_shin
python3 -m modelo.arnes resumen                       # todos los modelos guardados, cada uno sobre sus partidos
python3 -m modelo.arnes desglose poisson_simple --por fase        # o torneo, anio
python3 -m modelo.arnes calibracion poisson_simple --por-clase
python3 -m modelo.arnes registro                      # cuántas variantes se han probado, por familia
python3 -m modelo.base                                # reevalúa todas las líneas base (--sin-original: 30 s)
python3 -m pytest modelo/pruebas/test_arnes.py -q     # 30 pruebas, 7 s
```

```python
from modelo import arnes, base, datos, metricas
pred = arnes.evaluar(base.PoissonSimple())                       # DataFrame, y lo guarda en pred/
tabla = arnes.comparar(["poisson_simple", "frecuencias"], referencia="mercado_cierre_shin")
ids, M = arnes.leer_matrices("poisson_simple")                   # (n,), (n, 11, 11) para ensambles
arnes.mercados(M[0])                                             # 1X2, doble oportunidad, totales, ambos anotan, top 5
futuro, Mf = arnes.pronosticar(base.PoissonSimple())             # los partidos pendientes (no califica nada)
```

Tiempos medidos en esta máquina (un proceso): el arnés solo cuesta 2 s por recorrido (510 cortes); `PoissonSimple`
completo **7.5 s** por bloque y 12.7 s por día (Newton con hessiana analítica, 4 iteraciones por corte arrancando
del ajuste anterior); `Mercado` 2 s; `CerebroOriginal` <<SEG_ORIGINAL>> (gradiente numérico, sin arranque en caliente).
Conviene exportar `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` para no ocupar los 4 núcleos.

## 4. Utilidades de la matriz de marcadores (`arnes`)

`matriz_marcadores(lam_l, lam_v, rho)` y `matrices_marcadores` (vectorizada); `p1x2(M)`, `goles_esperados(M)`,
`dist_total(M)` (0 a 20 goles), `p_over(M, linea)`, `p_ambos_anotan(M)`, `marcador_mas_probable(M)`,
`top_marcadores(M, k)`, `mercados(M)` (todo junto) y `ajustar_M_a_1x2(M, p)` (reescala las regiones local/empate/visita
de una matriz para que su 1X2 sea `p`: da una matriz coherente a un ensamble de 1X2). La matriz coincide con la del
motor previo (`C.matriz_marcadores`) a 1e-16.

## 5. Columnas de `pred/<nombre>.parquet`

Nombre del archivo: `<nombre>.parquet` (desarrollo, por bloque); sufijos `__dia`, `__prueba`, `__calentamiento` y
`__parcial` en los demás casos.

| Columna | Significado |
|---|---|
| `id` | Id del partido en ESPN (llave de `partidos.csv`). |
| `fecha_utc`, `torneo`, `fase`, `pierna`, `local`, `visitante` | Identidad del partido. |
| `bloque` | Fecha local (AAAA-MM-DD) del corte de lunes o viernes; es la unidad del bootstrap en ambas granularidades. |
| `dia` | Fecha local del partido. |
| `corte` | Instante UTC del corte con que se pronosticó (el del bloque o el del día). |
| `p_l`, `p_e`, `p_v` | Probabilidad de victoria local, empate y victoria visitante a 90 minutos (suman 1). |
| `lam_l`, `lam_v` | Goles esperados que declaró el modelo (o las medias de su matriz). NaN si sólo dio 1X2. |
| `p_over15`, `p_over25`, `p_over35` | P(total de goles > 1.5, 2.5, 3.5). |
| `p_ambos` | P(ambos equipos anotan). |
| `marcador_probable`, `p_marcador_probable` | Marcador más probable ("1-1") y su probabilidad. |
| `gl`, `gv`, `resultado` | Lo que ocurrió a 90 minutos; `resultado`: 0 local, 1 empate, 2 visita. |
| `logp_marcador` | ln de la probabilidad que la matriz daba al marcador exacto (malla 0-10). NaN si sólo dio 1X2. |
| `x_*` | Columnas extra que devolvió el modelo. |

## 6. Métricas y comparación pareada

- Log-loss con logaritmo natural (azar uniforme 1.0986). RPS con el orden local > empate > visita, dividido entre 2
  (azar 0.222). Brier multicategoría, suma sobre los 3 resultados (azar 0.667). En las tres, **menor es mejor**.
- `logv marcador` = media de ln P(marcador exacto): **mayor es mejor** (menos negativo). Un marcador con más de 10
  goles de un lado se evalúa en la celda 10 (el máximo histórico es 9).
- `comparar` usa sólo los partidos que ambos modelos pronosticaron y reporta `d_* = modelo − referencia` con
  `ee_*` = error estándar por **bootstrap de bloques** (2,000 réplicas, semilla 20261110; se remuestrean bloques
  enteros porque los partidos de una jornada comparten información), el intervalo de 95% por percentiles y
  `z_ll = d_ll / ee_ll`. En log-loss, RPS y Brier, `d < 0` favorece al modelo; en `d_logv`, `d > 0`.
  Comprobado en desarrollo: el error estándar casi no cambia con la unidad de remuestreo (Poisson menos mercado:
  0.0046 por partido, 0.0047 por bloque, 0.0044 por mes) y la diferencia media por bloque no tiene autocorrelación
  positiva (−0.14 al primer rezago): el bloque es una unidad suficiente.
- Calibración: `metricas.calibracion_deciles` (probabilidad media contra frecuencia observada por decil, juntando
  los tres resultados o por clase), `error_calibracion` (media ponderada de |diferencia|) y `pendiente_calibracion`
  (exponente t que minimiza el log-loss de P^t renormalizada: 1 = calibrado, > 1 = tímido, < 1 = sobreconfiado).

**Cuánto ruido hay.** El log-loss de un modelo solo tiene un error estándar de 0.004 a 0.009 en desarrollo (lo domina
lo impredecible de los resultados), pero lo que importa es la diferencia pareada, cuyo error depende de cuánto se
parezcan los dos modelos:

<<TABLA_RUIDO>>

Lectura: (a) en la PRUEBA (≈ 480 partidos) una diferencia de log-loss contra el mercado menor que ≈ 0.017 (2 ee) no se
distinguirá del azar; la que hoy separa a `poisson_simple` del mercado (0.0185) apenas llegaría a 2 ee. (b) Para
decidir entre dos modelos con desviación pareada `s` por partido hacen falta `n ≈ (2·s/Δ)²` partidos para ver una
diferencia Δ a 2 ee: con `s = 0.19` y Δ = 0.01, 1,444 partidos; una jornada (9 partidos) no decide nada (ee ≈ 0.06).
(c) Al comparar N variantes contra la misma referencia, la mayor diferencia por puro azar es del orden de
`ee·√(2·ln N)` (2.1 ee con N = 10; 3.0 ee con N = 100): por eso el registro de variantes (§7).

## 7. Registro de variantes

`evaluar` anota **cada** corrida en `registro_variantes.jsonl`: fecha, nombre, familia, hiperparámetros, periodo,
granularidad, si fue parcial y las métricas (n, log-loss y su error estándar, RPS, Brier, logv, acierto, tiempos).
Quien califique una variante por otra vía debe llamar `arnes.registrar(nombre, familia, hiperparametros, metricas)`.
`python3 -m modelo.arnes registro` da el conteo por familia y `arnes.leer_registro()` la tabla completa. Elegir la
mejor de N variantes mirando el mismo periodo sesga a favor de la elegida: al reportar un ganador hay que decir N.
Al cierre de esta fase el registro tiene <<N_REGISTRO>>.

## 8. Candados contra fugas

Lo que el arnés impone en cada corte (y las pruebas verifican con un modelo espía):

1. `hist` contiene exactamente los partidos jugados con `fecha_utc < corte`; si algo es igual o posterior al
   corte, o un partido a pronosticar está en el historial, la corrida se detiene (`AssertionError`).
2. `predecir` recibe sólo `COLS_PREPARTIDO`: ni marcador, ni estadísticas, ni alineación del propio partido.
3. Los resultados reales se pegan después de pronosticar; el modelo nunca los toca.
4. `datos.cargar()` no calcula nada con información global: tipos, zona horaria, bloque, periodo y banderas.
5. La PRUEBA exige permiso explícito y queda en bitácora.

Lo que el arnés **no** puede verificar y queda a cargo de cada familia y de la revisión adversarial: hiperparámetros
o priors escritos conociendo el futuro (p. ej. una constante de liga de 2025-26), tablas leídas por fuera sin filtrar
por `hist`, y el uso de momios de cierre como variable. `arbitro` viene en `COLS_PREPARTIDO` porque la designación
es previa al partido, pero ESPN lo publica con el partido: úsese con esa reserva.

## 9. Líneas base

- **`frecuencias`**: el mismo pronóstico para todos los partidos del bloque. 1X2 = proporciones históricas de
  local/empate/visita (todo el historial previo); marcador = Poisson independientes con las medias de goles de local
  y de visita, reescalado para que su 1X2 sea esas proporciones.
- **`poisson_simple`**: `log lam_l = c + h + atk[local] + dfn[visita]`, `log lam_v = c + atk[visita] + dfn[local]`;
  máxima verosimilitud con peso `0.5^(antigüedad / 365 días)`, ventaja de local común, goles independientes
  (`rho = 0`), ventana de 10 años. Lleva una penalización cuadrática mínima (`ridge = 1`, equivalente a un prior
  N(0, 1) en escala logarítmica) que identifica el modelo y evita que un equipo con dos partidos diverja; un equipo
  sin partidos previos vale el promedio. Hiperparámetros fijados de antemano, sin búsqueda.
- **`cerebro_original_limpio`**: el motor de agosto de 2026 llamado tal cual (`C.fit_dixon_coles`: xi = 0.0038,
  liguilla ×1.25, `rho = −0.11` fijo, historia desde el 23-jul-2010; bases = medias sin ponderar de fase regular;
  `C.matriz_marcadores`), **sin** lo que se escribió en julio de 2026 conociendo el pasado: priors por equipo,
  localía por estadio, escudo y H2H. La credibilidad conserva su fórmula (`Z = w³ / (w³ + 4³)`) pero encoge hacia
  el equipo promedio (1, 1). Conserva sus defectos conocidos (escala inconsistente: subestima los goles).
- **`cerebro_original_exacto`** (`base.CerebroOriginalExacto`): el motor exacto con priors y capas. Verificado: con
  el CSV original reproduce `docs/datos/j04.json` (diferencia máxima 0.00005 en 1X2 y 0.0004 en lambdas). Sus priors
  y capas ven el futuro antes de agosto de 2026, así que **se niega a ajustar con cortes anteriores al 14-ago-2026**
  y no se evaluó aquí (cae en la PRUEBA). El agente de selección puede correrlo con
  `evaluar(base.CerebroOriginalExacto(), "prueba", desde="2026-08-14 06:00", permitir_prueba=True)` (06:00 UTC = viernes
  14 a las 00:00 de la Ciudad de México, primer corte válido). Se alimenta con ESPN,
  es decir, sin el hueco de 2025-26 que tenía el CSV de agosto.
- **`mercado_cierre_prop` / `_shin` / `_pot`**: 1X2 implícito en los momios de cierre sin margen, por normalización
  proporcional, método de Shin y método de potencia. Sólo donde hay momios (1,671 de 2,981 partidos de desarrollo:
  46% a 53% de Apertura 2019 y Apertura 2020, y ≥ 93% desde Clausura 2021). **`mercado_cierre_marcador`**: la matriz
  Dixon-Coles implícita en el 1X2 (Shin) y la línea de goles (tres ecuaciones, tres incógnitas: `lam_l`, `lam_v`,
  `rho`); sirve de referencia para el marcador y los totales. El mercado es referencia: no puede simular rondas futuras.
- **`mercado_abre_*`** (momios de apertura): **sin datos en desarrollo**. ESPN sólo trae apertura desde diciembre de
  2025 (313 partidos, todos en la PRUEBA). La comparación apertura contra cierre queda para el agente de selección.

### 9.1 Tabla de líneas base en DESARROLLO (corte por bloque)

<<TABLA_BASE>>

### 9.2 Comparación pareada contra el mercado (cierre, Shin) en los partidos con momios

<<TABLA_PAREADA>>

### 9.3 Lectura

<<LECTURA>>

## 10. Hallazgos sobre los momios

1. **Cobertura del cierre.** No hay momios antes de Apertura 2019. En desarrollo hay 1,673 partidos con 1X2 de
   cierre utilizable (1,671 evaluables): 46% de Apertura 2019, 0% de Clausura 2020, 53% de Apertura 2020 y entre 93% y
   100% desde Clausura 2021. Casas: Bet365 (1,302; jul-2019 a abr-2024), ESPN BET (343; desde may-2024), Caesars (27),
   DraftKings (1). Margen medio del 1X2: 6.2% (percentiles 5 a 95: 4.5% a 9.3%).
2. **Apertura.** `ml_*_abre` sólo existe desde diciembre de 2025: 313 partidos, todos en la PRUEBA. En desarrollo
   no se puede comparar apertura contra cierre.
3. **Momios capturados en vivo.** Seis partidos de abril de 2024 (Bet365; ids 692368, 692377, 692383, 692385,
   692386, 692388) traen como "cierre" un momio tomado con el partido en juego (empate a 1.04 en un 1-1, local a 151,
   más de 2.5 a 1.03). `datos.momios_en_vivo` los detecta con una regla que usa sólo los momios (favorito < 1.08,
   empate < 2.0 o > 12, o un lado de la línea de 2.5 goles < 1.15) y `datos.cargar()` vacía sus momios
   (`momios_dudosos=True`). No es un detalle: con ellos el log-loss del mercado en desarrollo baja de 1.0028 a 0.9998
   y el de Clausura 2024 de 0.9798 a 0.9508. La misma regla se aplica, sin mirarla, a la PRUEBA.
4. **¿Hay más capturas en vivo que la regla no ve?** No hay indicios: la ventaja del mercado sobre `poisson_simple`
   es pareja por torneo (entre −0.003 y +0.030 de log-loss) y no es mayor con ESPN BET (+0.023 en Apertura 2024 y
   +0.014 en Clausura 2025) que con Bet365 (+0.004 a +0.030); los torneos en que el mercado luce muy bien (Clausura
   2025: 0.956) también son buenos para Poisson (0.970). Pero una captura a los pocos minutos de iniciado el partido,
   con momios todavía verosímiles, no se distinguiría: conviene cotejar una muestra con otra fuente.
5. **Cómo quitar el margen.** Shin mejora a la normalización proporcional en 0.0011 de log-loss (ee 0.0004, z = 2.5)
   y calibra mejor (error de calibración 0.021 contra 0.026); el método de potencia queda 0.0003 (ee 0.0002) por
   debajo de Shin, indistinguible. La referencia del proyecto es **`mercado_cierre_shin`**.
6. **El mercado sin margen sigue siendo tímido.** Su pendiente de calibración es 1.13 (ee 0.07; proporcional 1.19,
   potencia 1.11): los favoritos ganan más de lo que dice el momio (decil más alto: 0.619 pronosticado, 0.661
   observado) y los desvalidos menos (decil más bajo: 0.152 contra 0.131). Es el sesgo favorito-desvalido, que ningún
   método de margen quita del todo. `poisson_simple` no lo tiene (pendiente 0.99, ee 0.05).
7. **Marcador implícito.** La matriz que reproduce el 1X2 y la línea de goles (1,642 de 1,673 partidos traen una línea
   de medio gol utilizable; Bet365 publicó la de 4.5 en 267) pide en promedio 1.52 + 1.16 = 2.68 goles (observado
   2.68) y una correlación Dixon-Coles `rho` de −0.076 (desviación 0.052; percentiles 5 a 95: −0.159 a 0.016). Su
   log-verosimilitud del marcador es −2.846 y pronostica 49.8% de más de 2.5 goles (observado 50.8%) y 52.0% de ambos
   anotan (observado 54.2%).
8. **Liguilla.** El mercado predice peor la liguilla que la fase regular: log-loss 0.997 en fase regular (n = 1,502)
   contra 1.042 en cuartos (78), 1.103 en semifinales (37), 1.008 en finales (20) y 1.045 en repechaje (34). Con 169
   partidos de liguilla el ruido es grande, pero es un aviso para la simulación de series.

## 11. Pruebas (`pruebas/test_arnes.py`)

30 pruebas, 7 segundos, ninguna toca la PRUEBA real ni escribe en `pred/`:

- **Sin fugas**: un modelo espía registra lo que ve en cada corte (bloque y día): el máximo de `hist` siempre es
  anterior al corte, `hist` es exactamente todo lo jugado antes, ningún partido del bloque está en el historial y
  `predecir` no recibe columnas de resultado. El candado detiene tres fugas provocadas a propósito.
- **Métricas a mano**: log-loss, RPS, Brier, acierto y log-verosimilitud en un ejemplo de 3 partidos calculado en
  los comentarios; valores de azar (ln 3, 2/3, 2/9); calibración y bootstrap con datos simulados.
- **Matriz**: suma 1 con y sin `rho`, coincide con el producto de Poisson y con la fórmula de Dixon-Coles a mano, y
  con la del motor original.
- **Bloques**: límites sintéticos (jueves 23:59, viernes 00:00, domingo 23:00 que ya es lunes en UTC, horario de
  verano) y la semana real del 26-feb-2024 con jornada doble (3 partidos de media semana + 9 de fin de semana).
- **Determinismo**: dos corridas de `PoissonSimple` dan tablas idénticas; lo guardado es igual a lo devuelto.
- Además: periodos, exclusión de los resultados de escritorio, tablas auxiliares restringidas al historial, formatos
  de salida válidos e inválidos, permiso y bitácora de la PRUEBA (simulada re-etiquetando un torneo viejo), registro,
  reanudación de una corrida interrumpida, Newton contra un optimizador independiente, los tres métodos de quitar
  el margen, el marcador implícito del mercado (ida y vuelta) y el filtro de momios en vivo.

## 12. Pendientes y dudas

<<PENDIENTES>>
