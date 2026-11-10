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
- [x] 1. Datos y reconocimiento
  - [x] Base de ESPN: `datos/` (8,767 partidos 2001-2026, `COBERTURA.md`, `espn_descarga.py actualizar`, `verificar` en verde).
  - [x] Reglas: `config/torneo.json` (reglamento 2026-27).
  - [x] Medios: `web/medios.json` (36 fotos de los 16 estadios, 7 videos, 8 de ambiente, 18 escudos, créditos).
  - [ ] Actualidad (lesionados, DT): **pendiente**, se hace antes de la Jornada 17 (guion: parte "Actualidad" de
    `notas/workflows/01_reglas_actualidad.js`). Las suspensiones se deducen de `tarjetas.csv`.
- [x] 2. Cimientos de modelado: `modelo/arnes.py`, `base.py`, `metricas.py`, `datos.py`, `ARNES.md`;
  `modelo/variables.py`, `VARIABLES.md` (309 variables sin fuga, 20 pruebas en verde).
  Líneas base en desarrollo: frecuencias 1.0702, poisson_simple 1.0309, mercado (cierre, Shin) 1.0028.
- [~] 3 y 5. Workflow `03_campeon_y_produccion.js` (lanzado 09:25 UTC, args `{saltar: []}`), dos cadenas:
  - candidatos → selección. Señales de hecho: `modelo/informes/candidatos.md` (con sección "Estado"),
    `modelo/RESULTADOS.md` + `campeon.json` + `pronostico.py`.
  - mercados → simulador. Señales: `produccion/MERCADOS.md`, `produccion/SIMULADOR.md` + `salidas/actual.json` +
    `salidas/CONTRATO.md`.
  - Si se corta: relanzar con `args: {saltar: [...]}` (`candidatos`, `seleccion`, `mercados`, `simulador`).
- [ ] 3b. Auditoría adversarial de fugas y réplica independiente (prompt en `notas/workflows/02_modelos.js`,
  función `pAuditoria`) → `modelo/AUDITORIA.md`.
- [ ] 6. Página (plantilla + constructor) leyendo `salidas/actual.json` según `salidas/CONTRATO.md` y
  `web/medios.json`; referencia de estilo y de robustez: `f1_austin/web/plantilla.html` (probar en Chromium y WebKit;
  dentro de iframe no tocar `location.hash`).
- [ ] 7. Publicación (Artifact nuevo + sitio estático) y commit
- [ ] 8. Automatización (`pipeline.py auto`, `mejora.py` campeón/retador, tareas programadas, runbook)

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
- 2026-11-10 04:55 UTC · Segundo corte por límite (regresó 08:50). Quedaron hechos: medios completos, arnés,
  variables. Cada ventana de 5 h da para ~1.6-2 M de tokens de agentes: lanzar como mucho 2 cadenas a la vez.
- 2026-11-10 09:25 UTC · Lanzado `03_campeon_y_produccion.js` (candidatos → selección; mercados → simulador).
