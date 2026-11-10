# Cerebro Liga MX · estado y cómo retomar

> Este archivo es la memoria del proyecto. Si la sesión se corta (límite de uso, reinicio del contenedor, contexto
> resumido), **se retoma desde aquí sin preguntarle al usuario**: leer este archivo y `PLAN.md`, revisar qué hay en
> disco y seguir con la primera fase que no esté marcada como hecha. Actualizarlo al cerrar cada fase.

## Instrucciones permanentes del usuario
- Proyecto similar al de F1: pronóstico por partido (marcador, resultado, **4 picks del mismo partido tipo parlay**),
  **campeón** y **cada serie de la liguilla**; página con fotos de estadios, escudos y algún video.
- Toda la estadística posible: rachas, casa/visita, dominios (América–Cruz Azul en finales), racha actual,
  lesionados, expulsados, peso de cada estadio. **Encontrar el mejor modelo** (no hay que construir sobre lo previo).
- **Automatizado y con mejora continua** partido a partido y jornada a jornada.
- **Si se acaba el límite de la sesión, continuar en automático en cuanto vuelva** (tarea programada cada hora que
  despierta esta sesión; ver abajo).
- Ultracode activo: usar workflows para todo trabajo sustantivo. No abrir PR. Commits con las líneas de atribución
  de la sesión. Rama `claude/new-session-i9lrt6`.

## Fases (marcar al cerrar)
- [~] 1. Datos y reconocimiento
  - [x] Base de ESPN: `datos/` (8,767 partidos 2001-2026, `COBERTURA.md`, `espn_descarga.py actualizar`). La
    verificación independiente no llegó a correr: la cubre la auditoría de la fase 3.
  - [x] Reglas: `config/torneo.json` (escrito a mano desde `notas/reglas_oficial.md`, fuente: reglamento 2026-27).
  - [x] Escudos: `web/img/escudos/*.png` + `web/medios_parts/escudos.json`.
  - [~] Estadios, videos y ambiente: workflow `02_medios_resto.js` (lanzado 04:00 UTC). Listo cuando existan
    `web/medios_parts/estadios_1.json`, `estadios_3.json` y `videos.json`. Después, unir todo en `web/medios.json`.
  - [ ] Actualidad (lesionados, suspendidos, DT): **pendiente**. Las suspensiones se deducen de `tarjetas.csv`
    (lo hace `modelo/variables.py`); las lesiones requieren búsqueda web antes de cada jornada (guion en
    `notas/workflows/01_reglas_actualidad.js`, parte "Actualidad").
- [~] 2 y 3. Cimientos + competencia de modelos + selección + auditoría: workflow `02_modelos.js` (lanzado 03:58
  UTC, args `{saltar: []}`). Etapas y su señal de "hecho" en disco: arnés (`modelo/ARNES.md`), variables
  (`modelo/VARIABLES.md`), familias (`modelo/informes/poisson.md`, `ratings.md`, `variables.md`), selección
  (`modelo/RESULTADOS.md`, `campeon.json`, `pronostico.py`), auditoría (`modelo/AUDITORIA.md`). Si se corta, relanzar
  con `args: {saltar: [...]}` listando las etapas ya hechas (`arnes`, `variables`, `poisson`, `ratings`,
  `variables_ml`, `seleccion`).
- [ ] 4. Análisis especiales (liguilla, dominios, estadios, rachas, ausencias, córners/tarjetas)
- [ ] 5. Producción: mercados, combinada de 4 picks, simulación de tabla → liguilla → campeón → `salidas/*.json`
- [ ] 6. Página (plantilla + constructor), probada en Chromium y WebKit
- [ ] 7. Publicación (Artifact + sitio estático) y commit
- [ ] 8. Automatización (`pipeline.py auto`, `mejora.py`, tareas programadas, runbook)

## Cómo retomar una fase cortada
- Los guiones de los workflows están copiados en `notas/workflows/` (los originales viven fuera del repo y se
  pierden si el contenedor se reinicia). Para relanzar uno: `Workflow({scriptPath: "<ruta>"})`. Antes de relanzar,
  revisar qué entregables ya existen en disco para no repetir trabajo (editar el guion y quitar lo ya hecho).
- La caché de ESPN (`datos/cache/`) no va al repositorio: si se perdió, `python3 datos/espn_descarga.py todo`
  la reconstruye (~45 min); las tablas CSV sí están versionadas.
- Esta máquina tiene 4 CPU: cada workflow corre 2 agentes a la vez; conviene lanzar 2–3 workflows en paralelo.
- Hacer commit y push al cerrar cada fase (el contenedor es efímero).

## Tarea programada de continuidad
- "Continuar Cerebro Liga MX" (`trig_011daxVc81g1dWPVNtuVKMCi`, minuto 13 de cada hora): despierta esta sesión. Si todo avanza, no hace nada; si el trabajo quedó
  detenido, lo retoma desde este archivo. **Desactivarla cuando el proyecto esté publicado y la automatización de
  jornadas quede montada** (fase 8).

## Bitácora
- 2026-11-10 02:50 UTC · Reconocimiento: ESPN da resultados y estadísticas por partido; 143/153 jugados.
- 2026-11-10 03:00 UTC · Fase 1 lanzada en tres workflows paralelos.
- 2026-11-10 03:30 UTC · Se agotó el límite de uso a media fase 1 (regresó 03:50). Quedaron hechos: datos ESPN,
  notas de reglas, mapa del código previo, fotos de 11 estadios. Lección: ~2.2 M de tokens de agentes agotan la
  ventana; lanzar menos agentes a la vez y por prioridad.
- 2026-11-10 04:00 UTC · Relanzado: modelos (`02_modelos.js`) y medios restantes (`02_medios_resto.js`).
