# Cerebro Liga MX 2026 → Web · Propuesta de arquitectura

**Estado: propuesta. No he escrito código del proyecto.** Aquí está el plan para que lo
confirmes o lo corrijas antes de tocar `cerebro_ligamx_2026.py`.

---

## 1. Veredicto sobre tu pregunta de arquitectura

**Tu inclinación es la correcta: Python exporta JSON + sitio estático. Estoy de acuerdo, y
no por comodidad técnica sino por una razón actuarial.**

El argumento que a mí me parece decisivo no es el de hosting gratis, sino este: **un
pronóstico sólo es medible si queda sellado antes de que se juegue la jornada.** Si la web
recalculara en vivo contra FastAPI, cada consulta usaría el histórico *de hoy* — que ya
incluye los resultados que quieres predecir. El Brier score de la J2 se "mejoraría" solo,
retroactivamente, cada vez que corrieras el modelo. Eso destruye justo lo que dices que es
clave del proyecto: medir el desempeño del modelo a lo largo del torneo.

Con JSON por jornada, cada archivo es un **snapshot inmutable con fecha y hash del
histórico que lo generó**. Es el equivalente a cerrar una valuación: los supuestos quedan
congelados y el resultado se compara contra ellos. Versionado en git, además, es auditable
por un tercero.

Lo demás refuerza la misma decisión:

- Son 9 partidos por semana y una corrida. No hay nada que recalcular por request.
- La calibración MLE + los parlays son trabajo de lotes, no de la ruta de un HTTP request.
- Sin servidor, sin base de datos, sin secretos, sin Node. Encaja con tu laptop corporativa.

**Cuándo cambiaría de opinión:** si algún día quieres un simulador interactivo ("¿y si
Toluca juega sin su 9?"), eso sí necesita cómputo bajo demanda y ahí sí entra una API. El
diseño que propongo sobrevive a esa migración sin rehacer el frontend, porque lo que separa
las dos capas es un **contrato JSON**, no un formato de archivo. No lo construyamos hoy.

---

## 2. Qué leí y qué verifiqué

Leí completo `cerebro_ligamx_2026.py` (948 líneas), los dos parsers, el Excel de la J2 y el
CSV de medios tiempos. Antes de proponer nada, corrí verificaciones sobre lo que sí es
auditable con los archivos disponibles.

**Lo que confirmé (todo correcto):**

| Afirmación | Verificación |
|---|---|
| `PROP_GOLES_1T = 0.4442` | 2,433 goles en 1T / 5,477 totales = **0.4442** exacto |
| P(gol en 1T) observado 68.9% | 1,411 / 2,047 partidos = **68.93%** |
| Escala local/visita | media local **1.5164**, visita **1.1593** (2,047 partidos HT) |
| `historico_ht_ligamx.csv` íntegro | 2,047 filas, **0 inconsistentes** (ningún `hf < h1`) |

Un detalle que habla bien del modelo: bajo Poisson homogéneo, P(gol en 1T) daría
1 − e^(−0.4442 × 2.676) = **69.5%**. Tu modelo reporta 68.8% y lo observado es 68.9%. La
diferencia va en la dirección correcta: al tener λ heterogéneas por partido, E[e^(−λ)] >
e^(−E[λ]) por Jensen, así que P(al menos un gol) baja. El 68.8% no es un ajuste afortunado,
es lo que predice la heterogeneidad. **No lo toco.**

**Una sospecha mía que resultó falsa, y la reporto porque cambia el plan:** creí que
`matriz_marcadores` (malla 11×11) y `_joint_mitades` (malla 8 por mitad) podían discrepar en
los marginales de tiempo completo, y que la web acabaría mostrando dos números distintos
para "gana el local". Lo probé: **coinciden a 4 decimales** en todas las λ que probé. La
construcción por adelgazamiento con τ aplicado al marcador final está bien hecha. No hay
nada que arreglar ahí.

---

## 3. Hallazgos en el código

Tres cosas que encontré leyendo. Ninguna es un error de matemáticas; las tres afectan lo que
la web va a publicar.

### 3.1 El Monte Carlo introduce ruido en números que publicas con 4 decimales

En `pronosticar_jornada` (líneas 510–512) las probabilidades 1X2 salen del Monte Carlo:

```python
p_local = float(np.mean(gl > gv))
```

Pero la matriz `M` que ya calculaste **es la distribución exacta**. De hecho tú mismo lo
sabes: en la línea 516 los marcadores exactos los sacas de `M` con el comentario *"más fina
que el MC"*. El 1X2 quedó en Monte Carlo por inercia.

Cuánto importa, medido:

| λ (local, visita) | Exacto (matriz) | Monte Carlo 100k | Discrepancia |
|---|---|---|---|
| (1.83, 0.71) | 0.6300 / 0.2424 / 0.1276 | 0.6286 / 0.2442 / 0.1272 | 0.0018 |
| (0.75, 1.60) | 0.1615 / 0.2743 / 0.5643 | 0.1590 / 0.2743 / 0.5668 | 0.0025 |

El error estándar de MC con n=100,000 para p≈0.6 es 0.0015. O sea: **el tercer decimal de lo
que publicas ya es ruido de simulación.** El Excel de la J2 dice `0.6926` — de esos cuatro
decimales, dos son reales.

Arreglo: tres líneas (`np.tril(M,-1).sum()`, `np.trace(M)`, `np.triu(M,1).sum()`). Ganas
números exactos, la corrida se vuelve instantánea, y **el resultado deja de depender del
orden del fixture** (hoy el `RNG` global se consume partido por partido, así que reordenar
el fixture cambia los decimales). Esto último es lo que hace viable una prueba de regresión
seria.

El Monte Carlo no se tira: lo dejaría corriendo como verificación cruzada, comparando contra
el exacto y avisando si difieren más de 3 errores estándar. Es un control de calidad gratis.

### 3.2 El optimizador de parlays puede tomar picks lógicamente gratis

`_greedy_parlay` maximiza `nº de picks × P(todos peguen)` y bloquea dos legs de la **misma
familia** en un partido. Pero hay pares donde un leg **implica lógicamente** al otro y son de
familias distintas, así que el filtro no los ve. Los busqué de forma sistemática sobre una
malla de λ realistas, exigiendo que ambos caigan en tu banda de trabajo [0.58, 0.85]:

| Leg A | implica | Leg B | Familias |
|---|---|---|---|
| Ambos anotan: Sí | ⟹ | Más de 1.5 goles | BTS / TOT |
| {Local} anota 2+ | ⟹ | Más de 1.5 goles | EQL / TOT |
| {Visita} anota 2+ | ⟹ | Más de 1.5 goles | EQV / TOT |

Si ambos entran, `P(A y B) = P(A)` exactamente. El objetivo `n × P` **sube siempre** al
agregar el implicado (n crece, P no baja), así que el voraz lo va a tomar cada vez que pueda.

Dos matices importantes: **(a) el número publicado sigue siendo honesto** — `_prob_conjunta`
suma sobre el joint y captura la implicación perfectamente, no hay error aritmético;
**(b) no se disparó en la J2** — revisé los tres parlays del Excel y ninguno tiene un par
implicado. Está latente, no activo.

La decisión es tuya y depende del reglamento de tu quiniela: si el concurso cuenta picks,
un pick implicado infla el conteo sin aportar información. Yo agregaría un filtro de
implicación (barato: `P(A∧B) == P(A)` ya lo sabes calcular), pero es tu llamada.

### 3.3 Atlante no está en el histórico y hereda un prior de otra escala

En `main()`, `ratings.setdefault(e, PRIORS_ILUSTRATIVOS[e])` le da a Atlante `(0.75, 1.22)`
porque no tiene partidos. El problema es que los ratings del MLE están normalizados a media
0 en log y los priors ilustrativos están en una escala cualitativa distinta: **un 0.75 del
prior y un 0.75 del MLE no significan lo mismo.** El partido Atlante vs América de la J2
(0.11 / 0.33 / 0.56) descansa sobre ese número.

Hay además una decisión de modelación que sólo tú puedes tomar: el comentario dice que
Atlante es la franquicia ex-Mazatlán, y **Mazatlán sí está en el histórico**
(`parsear_openfootball.py` lo mapea). ¿Hereda Atlante el historial de Mazatlán, o entra
como equipo nuevo? Cambia materialmente sus λ.

Como mínimo, la web debe marcar esos partidos con una bandera de incertidumbre: *"equipo sin
histórico: fuerza asumida, no estimada"*. Es exactamente la honestidad de datos que pides
en el punto 7 de tu prompt.

### 3.4 Cosas menores, para la lista

- La bitácora de `lambdas_partido` **se imprime y se pierde**: `pronosticar_jornada` no la
  guarda en `filas`. Para el panel colapsable hay que propagarla al JSON.
- La bitácora **no registra la capa 1** (la base MLE). Para valor didáctico debería empezar
  con *"base: ataque Cruz Azul 1.21 × defensa Puebla 0.94 → λ 1.83"* y registrar λ antes y
  después de cada capa, no sólo el multiplicador. Así la web puede dibujar la cascada.
- `fit_dixon_coles` estima la ventaja local (`theta[-1]`), la imprime y **la descarta**:
  `lambdas_partido` usa `BASE_HOME_GOALS / BASE_AWAY_GOALS` en su lugar. Es defendible y está
  comentado, pero conviene comparar `exp(theta[-1])` contra `BASE_HOME/BASE_AWAY ≈ 1.31`
  como chequeo de especificación: si se separan mucho, algo no cuadra.
- El estadio está en `FIXTURE` pero no llega al CSV ni al Excel. Es gratis para la web.
- Los nombres de salida están fijos a la J2 (`Cerebro_LigaMX_J2.xlsx`); con config externa
  se derivan de la jornada.

---

## 4. Estructura propuesta

```
liga-mx/
├─ cerebro/
│  ├─ cerebro_ligamx_2026.py      # el modelo — cambios quirúrgicos, nada más
│  ├─ config/
│  │  ├─ jornada.json             # JORNADA_ACTUAL + FIXTURE + AJUSTES_JORNADA
│  │  └─ liga_mx.json             # estadios, escudo, H2H, DT (parámetros de liga)
│  └─ datos/
│     ├─ historico_ligamx.csv
│     └─ historico_ht_ligamx.csv
├─ docs/                          # GitHub Pages sirve /docs de main, sin build ni CI
│  ├─ index.html
│  ├─ app.js
│  ├─ estilos.css
│  └─ datos/
│     ├─ indice.json              # catálogo de jornadas (único archivo mutable)
│     ├─ j01.json … j17.json      # snapshots sellados
│     └─ desempeno.json           # métricas acumuladas (derivado)
└─ ARQUITECTURA.md
```

`/docs` en `main` porque GitHub Pages lo publica sin Actions ni build: `git push` y ya. Nada
que instalar en la laptop corporativa.

**Caché, que sí va a morder en los celulares de tus colegas:** los `jXX.json` son inmutables
una vez sellados, así que se pueden cachear para siempre. Sólo `indice.json` cambia, y ése
se pide con `cache: 'no-cache'`. Así nadie ve una jornada vieja creyendo que es la vigente.

---

## 5. El contrato JSON (v1)

Este es el verdadero entregable de esta etapa. Todo lo demás se deriva de aquí.

```jsonc
{
  "esquema": "cerebro-ligamx/v1",
  "torneo": "Apertura 2026",
  "jornada": 2,
  "generado": "2026-07-19T22:14:03-06:00",
  "modelo": {
    "motor": "Dixon-Coles + malla exacta",
    "rho_dc": -0.11,
    "xi_decaimiento": 0.0038,
    "prop_goles_1t": 0.4442,
    "base_local": 1.516, "base_visita": 1.159,
    "historico": {
      "partidos": 4996, "desde": "2010-07-23", "hasta": "2026-07-18",
      "sha256": "…"                       // sella con qué datos se predijo
    }
  },
  "partidos": [{
    "id": "j02-cruzazul-puebla",
    "fecha": "2026-07-21", "estadio": "CDMX (adelantado)",
    "local": "Cruz Azul", "visitante": "Puebla",
    "lambdas": { "local": 1.83, "visita": 0.71 },
    "prob": { "local": 0.6926, "empate": 0.2269, "visita": 0.0805 },
    "pick": "Cruz Azul",
    "top_marcadores": [ { "marcador": "1-0", "prob": 0.1234 } ],
    "mercados": [ { "clave": "mas_1_5", "etiqueta": "Más de 1.5 goles", "prob": 0.8398 } ],
    "bitacora": [
      { "capa": "base_mle",   "detalle": "ataque Cruz Azul 1.21 × defensa Puebla 0.94",
        "lam": { "local": 1.73, "visita": 0.79 } },
      { "capa": "localia",    "detalle": "Ciudad de los Deportes ×1.02",
        "lam": { "local": 1.77, "visita": 0.79 } }
    ],
    "incertidumbre": null,        // "Atlante sin histórico: fuerza asumida"
    "resultado": null             // se sella DESPUÉS de jugarse
  }],
  "parlays": {
    "recomendado": {
      "descripcion": "Equilibrio óptimo entre número de picks y seguridad.",
      "legs": [ { "partido_id": "j02-chivas-juarez", "etiqueta": "Chivas o empate",
                  "prob": 0.8487 } ],
      "prob_conjunta": 0.4722,
      "valor_esperado": 2.361
    }
  },
  "no_modelado": ["tarjetas", "córners", "goleador", "minuto de gol"]
}
```

### Reglas duras del contrato

1. **JavaScript no calcula probabilidades. Nunca.** Si un número necesita algo más que
   `toFixed()` o `×100`, lo produce Python. `valor_esperado` viene calculado (hoy es una
   fórmula de Excel, `=COUNT(...)*C12`; en JSON va como valor).
2. **El snapshot se sella al publicarse.** Después sólo se escribe `resultado`, y sólo con
   hechos observados. Jamás se recalculan probabilidades de una jornada ya jugada.
3. **`desempeno.json` es derivado**, se reconstruye desde los snapshots sellados. Si se
   borra, se regenera idéntico.
4. **`no_modelado` es explícito** en el JSON, y la web lo muestra. Si alguien pregunta por
   córners, la respuesta sale del archivo, no de una nota en el código.
5. **4 decimales en el JSON, 1 decimal porcentual en pantalla** (69.3%). Publicar `0.6926`
   sugiere una precisión que el modelo no tiene, aun con la malla exacta.

---

## 6. Frontend

HTML/CSS/JS vanilla. Cero dependencias, cero build, cero npm — no hace falta que averigües
si tienes Node.

- **Tarjeta por partido, no tabla.** Una tabla de 8 columnas es ilegible en un celular.
  Cada partido es una tarjeta con una barra 1X2 apilada de tres segmentos: el ancho *es* la
  probabilidad, se lee de un vistazo y es honesta.
- **Bitácora** en un `<details>` nativo (colapsable sin JS), mostrando la cascada de λ capa
  por capa.
- **Tipografía:** Calibri existe en Windows pero no en Android/iOS. Stack:
  `Calibri, Carlito, "Segoe UI", system-ui, -apple-system, sans-serif`. Carlito es
  métricamente compatible y libre. **Sin Google Fonts**: el proxy corporativo y la latencia
  móvil no lo justifican.
- **Paleta GPV** como variables CSS. Ojo de contraste: el dorado `#C9A961` sobre el verde
  `#00573F` no da contraste suficiente para prosa chica — dorado sólo para acentos, bordes y
  títulos grandes; texto corrido en blanco sobre verde.
- **Peso:** ~9 partidos con top-5 marcadores, ~22 mercados y bitácora ≈ 40–60 KB por jornada,
  unos 10 KB comprimidos. Se carga sólo la jornada pedida.
- **Sin tests con navegador.** Nada de Playwright ni Puppeteer, respetando tu restricción de
  Elastic. La validación automatizada es un validador de esquema JSON en Python que corre al
  final de cada exportación; el frontend se revisa a ojo en el celular.

---

## 7. Sobre el histórico de aciertos (y una advertencia)

Lo que quieres medir por jornada y acumulado: aciertos 1X2, marcadores exactos, Brier, y si
el parlay pegó.

Dos precisiones que te van a importar:

- **Documenta la convención de Brier en el propio JSON.** Tu 0.568 vs azar 0.667 es el Brier
  multicategoría (suma de errores cuadráticos sobre los 3 resultados, uniforme = 2/3). Hay al
  menos tres convenciones circulando y mezclarlas es el error clásico. Que el archivo diga
  `"brier": {"convencion": "multicategoria_0_2", "azar": 0.667}`.
- **Considera agregar RPS** (Ranked Probability Score). Para resultados ordenados
  (Local > Empate > Visita) es el estándar en pronóstico de fútbol y penaliza correctamente
  fallar por dos categorías en lugar de una. Brier trata los tres resultados como no
  ordenados. Es una línea de código y te da una métrica más defendible.
- **Cuidado con leer una jornada sola.** Tu 6/9 de la J1 tiene un error estándar de ±16
  puntos porcentuales: es compatible con un modelo del 45% y con uno del 90%. Con 9 partidos
  por jornada, la métrica interpretable es la acumulada. Voy a mostrar ambas, pero la web
  debe decir esto explícitamente o tus colegas van a declarar al modelo genial o inútil cada
  semana. Un torneo completo son ~153 partidos: apenas suficiente para distinguir señal de
  ruido.

---

## 8. Flujo semanal (a esto quiero llegar)

```powershell
# 1. Editas cerebro\config\jornada.json  (fixture + lesiones de la semana)
# 2. Generas:
& C:\Users\asunad\.venv\Scripts\python.exe cerebro\cerebro_ligamx_2026.py `
    --historico cerebro\datos\historico_ligamx.csv `
    --jornada cerebro\config\jornada.json `
    --exportar-json docs\datos\j03.json --excel
# 3. Ya que se jugó, capturas resultados y se recalcula el desempeño:
& C:\Users\asunad\.venv\Scripts\python.exe cerebro\sellar_resultados.py --jornada 3
# 4. Publicas:
git add . ; git commit -m "J3 Apertura 2026" ; git push
```

Sin editar Python nunca más para operar el modelo.

---

## 9. Plan por fases

**Fase 0 — Red de seguridad.** Golden file: corro el modelo hoy, guardo la salida, y exijo
que todo cambio posterior la reproduzca. Sin esto, "cambios quirúrgicos" es una intención,
no una garantía. *No toca lógica.*

**Fase 1 — Contrato.** `--exportar-json` + `config/jornada.json` + validador de esquema, en
**una sola pasada** al script (mejor abrir el archivo validado una vez que dos). Aquí entran
también los arreglos 3.1 y 3.4. El Excel debe seguir saliendo idéntico salvo los decimales
que cambian por pasar de MC a exacto. *La web todavía no existe.*

**Fase 2 — Web.** Sitio estático: jornada actual, parlays, bitácora colapsable. Publicable.

**Fase 3 — Desempeño.** Sellado de resultados, Brier/RPS/aciertos, navegación entre jornadas.

**Fase 4 — Opcional.** Separar `motor/` (Dixon-Coles, joint de mitades, parlays — agnóstico
de liga) de `ligas/ligamx/` (nombres, estadios, escudo, H2H) para que el Cerebro Mundial
reutilice el motor. **Te lo pongo al final a propósito:** refactorizar un modelo validado de
948 líneas es exactamente donde se rompen cosas, y sólo tiene sentido con el golden file de
la Fase 0 verde. No es cosmético, pero tampoco urge.

---

## 10. Lo que necesito de ti para arrancar

**Bloqueante:**

1. **`historico_ligamx.csv` no está en la carpeta.** Sin él no puedo correr el modelo ni
   generar el golden file de la Fase 0. Es el único archivo que me falta.

**Decisiones tuyas (no las tomo yo):**

2. **¿Atlante hereda el historial de Mazatlán?** (§3.3) Cambia sus λ materialmente.
3. **¿Filtro de implicación en los parlays?** (§3.2) Depende del reglamento de tu quiniela.
4. **¿Repo público o privado?** GitHub Pages gratis exige repo público. Eso pone el branding
   GPV y el nombre de la empresa en una URL pública indexable. Para una quiniela interna
   quizá no importa, pero prefiero que lo decidas tú y no enterarte después. Alternativa:
   Netlify con drag-and-drop, sin repo público.
5. **Saca el repo de OneDrive.** Git dentro de `OneDrive - GPV` funciona hasta que OneDrive
   se pelea con `.git` por archivos bloqueados durante la sincronización, y además duplicaría
   todo al OneDrive corporativo. Sugiero `C:\Users\asunad\proyectos\liga-mx`.
6. **¿Los resultados de cada jornada los capturas a mano** (9 marcadores, dos minutos) **o
   quieres que los parsee?** openfootball se actualiza con retraso de días; a mano es más
   confiable para sellar a tiempo.
7. **¿La web nace multi-torneo** (pensando en el Cerebro Mundial) **o Liga MX primero?** El
   contrato JSON ya lo contempla; es cuestión de cuánto invertir hoy en el frontend.

---

**Dime qué cambias de esto y arranco por la Fase 0.**
