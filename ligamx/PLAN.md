# Cerebro Liga MX · plan de trabajo (iniciado 2026-11-10)

Pedido del usuario (10-nov-2026): proyecto similar al de F1 para la Liga MX: pronosticar cada partido (marcador,
resultado y **4 pronósticos del mismo partido tipo parlay**), **quién será campeón** y **cada serie de la liguilla**;
página con fotos de estadios, escudos y algún video; meter toda la estadística posible (rachas, casa/visita, dominios
entre equipos como América–Cruz Azul en finales, racha actual, lesionados, expulsados, peso de cada estadio) y
**encontrar el mejor modelo**.

**Precisión del usuario (10-nov, segundo mensaje):** no hay que construir sobre lo que existe: **encontrar lo mejor**;
y debe quedar **automatizado y mejorar sobre sí mismo partido a partido y jornada a jornada** (como el de F1:
tareas programadas + ciclo campeón/retador con regla anti-ruido).

## Punto de partida
- En la raíz del repo hay una versión previa (agosto 2026): `cerebro_ligamx_2026.py` (Dixon-Coles validado con
  `golden/`), `generar.py`, `proyeccion.py`, `config/jornadas.json`, `docs/` (sitio simple GPV) y `ARQUITECTURA.md`.
  No se toca: el motor original entra a la competencia como **línea base** ("Cerebro original").
- Estado del torneo (ESPN, 10-nov): Apertura 2026 con 143 de 153 partidos jugados; faltan Querétaro–Monterrey
  (14-nov) y la Jornada 17 (20–22 nov). Después, liguilla.
- Fuente de datos nueva: API pública de ESPN (resultados desde ~2002; por partido: tiros, córners, tarjetas,
  posesión, minuto de goles, alineaciones, momios). Esto abre mercados que antes no se podían modelar.

## Fases
1. **Datos y reconocimiento** (workflows `ligamx-datos-espn`, `ligamx-reglas-y-actualidad`, `ligamx-medios`, en
   paralelo porque cada workflow sólo corre 2 agentes a la vez en esta máquina de 4 CPU): `datos/` (ESPN + verificación),
   `config/torneo.json` (reglas de liguilla), `config/actualidad.json` (lesionados, suspendidos, DT),
   `web/medios.json` + `web/img` + `web/video` (estadios, ambiente, escudos), `notas/mapa_repo_previo.md`.
2. **Cimientos de modelado**: arnés de validación walk-forward sin fugas + variables "a la fecha"
   (`modelo/`): forma, rachas, casa/visita, descanso, viaje, altitud, H2H, tiros/córners, rojas previas, alineación.
3. **Competencia de modelos**: familias en paralelo (Dixon-Coles afinado, ratings dinámicos Elo/pi, fuerza por
   tiros, ML con variables, jerárquico) + ensamble; línea base = Cerebro original y **momios del mercado**.
   Protocolo: desarrollo hasta Clausura 2025; prueba única en Apertura 2025–Apertura 2026. Métricas: log-loss,
   RPS, Brier, verosimilitud del marcador exacto, calibración. Revisión adversarial de fugas.
4. **Análisis especiales**: efecto liguilla (goles, localía, sembrado), dominios H2H (América–Cruz Azul), peso de
   cada estadio, rachas, ausencias, córners y tarjetas, mitades; calibración histórica del simulador de series.
5. **Producción**: pronóstico de los partidos pendientes con todos los mercados y la combinada de 4 picks
   (probabilidad conjunta exacta), simulación de tabla → liguilla → campeón; JSON sellado por corrida.
6. **Página**: una sola página cinematográfica (como la de F1), móvil primero, menú de 3 barras, fotos, escudos,
   videos; Artifact + sitio estático.
7. **Revisión final** (Chromium y WebKit), publicación, commit.
8. **Automatización y mejora continua**: `pipeline.py auto` (actualiza datos de ESPN → recalibra → sella el
   pronóstico antes de cada partido → califica el anterior → vuelve a simular liguilla y campeón → reconstruye la
   página) + `mejora.py` (campeón/retador: tras cada jornada re-evalúa a los retadores en walk-forward y sólo adopta
   uno si mejora más que el ruido) + tareas programadas alrededor de cada partido pendiente y de cada fase de
   liguilla, con runbook en `ESTADO.md`.

## Reglas (heredadas y nuevas)
- Sin fugas: todo se calibra sólo con partidos anteriores a la fecha del pronóstico.
- JavaScript no calcula probabilidades: sólo formatea lo que exporta Python.
- Nada inventado: lo que no hay en los datos se dice.
- Elegir modelo mirando el mismo walk-forward sesga: se separa un periodo de prueba y se dice.
