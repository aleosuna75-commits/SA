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
- [ ] 1. Datos y reconocimiento — **en curso** (lanzados 2026-11-10 ~03:00 UTC)
  - `01_datos_espn.js` → `datos/espn_descarga.py`, `datos/partidos.csv`, `goles.csv`, `tarjetas.csv`,
    `alineaciones.csv`, `calendario_pendiente.json`, `tabla_apertura2026.csv`, `COBERTURA.md`,
    `notas/mapa_repo_previo.md`. Listo cuando exista `COBERTURA.md` con la sección "Verificación independiente".
  - `01_reglas_actualidad.js` → `config/torneo.json`, `config/actualidad.json`,
    `notas/como_actualizar_actualidad.md`.
  - `01_medios.js` → `web/medios.json`, `web/img/estadios`, `web/img/ambiente`, `web/img/escudos`, `web/video`.
- [ ] 2. Cimientos de modelado (arnés walk-forward sin fugas + variables a la fecha) → `modelo/`
- [ ] 3. Competencia de modelos + ensamble + revisión adversarial → `modelo/RESULTADOS.md`
- [ ] 4. Análisis especiales (liguilla, dominios, estadios, rachas, ausencias, córners/tarjetas)
- [ ] 5. Producción: pronósticos, combinada de 4 picks, simulación de liguilla y campeón → `salidas/*.json`
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
