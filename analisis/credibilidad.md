# ¿Qué hace `k = 10`? — evidencia antes de tocar el modelo

Preguntaste por `k = 10`. Lo medí en vez de opinar, y el resultado me obliga a corregir mi
propia recomendación.

## 1. `k = 10` sí arregla a Atlante

| | ataque | defensa | lugar en la liga |
|---|---|---|---|
| Hoy | **1.5324** | 0.8389 | **#1 de 18** |
| Con `k = 10` | 0.8758 | 1.1248 | #14 de 18 |

Un ascendido deja de ser el mejor ataque del torneo. Eso era lo que buscábamos.

## 2. Pero se lleva a media liga por delante

`Z = w/(w+k)` con `k = 10` da `Z ≈ 0.43-0.51` para **todos** los demás. Es decir: a equipos
con 500-600 partidos reales se les asigna **más de la mitad del peso a un prior que el propio
código llama ILUSTRATIVO** (línea 99: *"sustituidos por MLE si hay histórico"*).

| Equipo | w | ataque hoy | con `k=10` | movimiento |
|---|---|---|---|---|
| Chivas | 7.91 | 0.6619 | 0.8878 | **+34.1%** |
| Juárez | 7.63 | 0.5566 | 0.7217 | **+29.7%** |
| Santos | 7.55 | 0.6259 | 0.7300 | +16.6% |
| América (defensa) | 10.21 | 0.4038 | 0.5837 | **+44.5%** |

América tiene la mejor defensa de la liga estimada sobre 622 partidos, y `k = 10` la empeora
44% para acercarla a un 0.85 escrito a mano.

**El costo está medido**, no es teórico. Backtest walk-forward sobre 681 partidos (3
temporadas, calibrando sólo con lo anterior a cada mes, sin ver el futuro nunca):

| Configuración | Brier | Aciertos |
|---|---|---|
| Sin credibilidad (hoy) | **0.5931** | 51.1% |
| `k = 10` | 0.5968 | 51.4% |

## 3. Por qué el backtest no puede elegir `k` solo

Separé los partidos según el peso del equipo más flaco. En tres temporadas hay **3 partidos**
con un equipo de poco histórico: Liga MX no tuvo ascensos hasta 2026, así que el caso Atlante
casi no existe en la historia reciente.

**No hay evidencia con qué estimar `k`.** Con n = 3 cualquier número que te diera sería
inventado. Por eso la elección tiene que ser de diseño, no de ajuste — pero el *costo* sobre
los otros 678 partidos sí se mide, y es lo que hice arriba.

## 4. La variante que recomiendo: mismo arreglo, costo cero

El problema no es `k`, es la forma funcional. `w` va de 2.77 (Atlante) a 10.21 (América):
apenas un factor de 3.7, así que ningún `k` con `Z = w/(w+k)` logra encoger a uno sin mover al
otro. Basta hacer la transición más nítida:

```
Z = w³ / (w³ + k³)      con k = 4
```

| Equipo | `Z` con k=10, p=1 | `Z` con k=4, p=3 |
|---|---|---|
| Atlante (w=2.77) | 0.217 | **0.249** ← se encoge igual |
| Chivas (w=7.91) | 0.442 | **0.886** ← casi no se mueve |
| América (w=10.21) | 0.505 | **0.943** |

Resultados de las tres opciones, mismo protocolo:

| Configuración | Atlante ataque | Peor movimiento en otro equipo | Brier (681 partidos) | Aciertos |
|---|---|---|---|---|
| Sin credibilidad | 1.5324 (#1) | — | **0.5931** | 51.1% |
| `k = 10`, `p = 1` | 0.8758 (#14) | **34.1%** | 0.5968 | 51.4% |
| **`k = 4`, `p = 3`** | **0.8963 (#12)** | **6.2%** | **0.5931** | **51.4%** |

La focalizada consigue **el mismo arreglo en Atlante sin costo medible**: idéntico Brier al
modelo actual, y un punto de acierto arriba. `k = 10` paga 0.0037 de Brier por lo mismo.

## 5. La versión de libro, si quieres hacerlo bien

Todo esto es encogimiento *post hoc*. Lo correcto es meter el prior **dentro de la
verosimilitud**, como penalización por equipo:

```python
return -(ll.sum()) + 1000*(atk.mean()**2 + dfn.mean()**2) \
       + LAMBDA_PRIOR * sum((atk[i] - atk_prior[i])**2 + (dfn[i] - dfn_prior[i])**2)
```

Así el peso es **automático y correcto**: un equipo con 3 partidos tiene verosimilitud plana y
la penalización manda; uno con 600 la tiene aguda y la penalización es irrelevante. No hace
falta `k`, ni exponente, ni umbral, y el mecanismo sirve para cualquier ascendido futuro. Es
un cambio de tres líneas en `neg_loglik` y es lo que yo haría.

---

## Recomendación

1. **Si quieres el arreglo hoy, sin discutir:** `Z = w³/(w³+4³)`. Diez líneas, costo medido
   cero, Atlante queda #12.
2. **Si quieres hacerlo bien:** el prior dentro de la verosimilitud (§5), y `LAMBDA_PRIOR` se
   calibra con el mismo backtest que ya está escrito.
3. **`k = 10` con `p = 1` tal cual: no lo recomiendo.** Arregla a Atlante moviendo a Chivas
   34% y a la defensa del América 44%, y el backtest dice que se paga.

Dime cuál y lo implemento junto con la Fase 1.
