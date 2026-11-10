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
- [x] 3. Competencia de modelos y selección: `modelo/informes/candidatos.md` (6 candidatos, 51 variantes),
  `modelo/RESULTADOS.md` (prueba pre-registrada, abierta una vez), `campeon.json` (**ajuste**: Dixon-Coles corregido
  con tiros, viaje y rotación), `registro.json` (retadores: ensamble, dc, dc2, elo, tiros), `pronostico.py`.
  Resultado franco: en la prueba (480 partidos) todos los modelos quedan dentro del ruido (1.022 a 1.028) y el
  mercado de cierre (1.003) les gana por ~0.02; el original limpio 1.0325 y subestima goles.
- [x] 5. Producción: `produccion/mercados.py` (56 mercados por mitades), `combinada.py` (4 picks, conjunta exacta
  calibrada), `contexto.py`, `simulador.py` (desempates oficiales, liguilla, campeón), `sellos.py`, `exportar.py`
  → `salidas/actual.json` (contrato en `salidas/CONTRATO.md`). Comando único: `python3 -m produccion.exportar`.
  Campeón al 10-nov: América 28%, Chivas 22%, Cruz Azul 21%, Toluca 20%.
- [x] 6. Página: `web/plantilla.html` + `web/construir.py` → `web/index.html` (51 revisiones en Chromium y WebKit).
- [x] 3b. Auditoría: `modelo/AUDITORIA.md` (sin fugas; réplica independiente coincide; la ventaja de `ajuste` estaba
  inflada por selección). Decisión: el modelo de producción es **`ensamble`** (`python3 -m modelo.mejora estado`).
- [x] 7. Publicada: **https://claude.ai/artifact/K3fNKhot24LUcwn6PfXGF6** (título "Cerebro Liga MX", icono soccer;
  `file_path` = `/home/user/SA/ligamx/web/index.html`; los 69 archivos de `web/archivos_publicados.json` ya están
  publicados y sólo se reenvían si cambian). Es privada: el usuario la comparte desde el menú Share.
- [x] 8. Automatización: `pipeline.py auto` + `modelo/mejora.py ciclo` + tarea programada diaria (runbook abajo).

## En curso (10-nov-2026, 22:00 UTC): en vivo y rediseño
Pedido del usuario: la versión visual que le encantó es la del commit `5306055`; volver a ponerla a punto, que la
liguilla tenga **estructura de torneo** con **pronóstico de ida y vuelta por partido**, y que la actualización **se vea
en vivo**. Workflow `notas/workflows/05_vivo_y_rediseno.js` (motor en vivo ∥ rediseño → crítica visual ∥ crítica
funcional → corrección). Ya hecho a mano: `liguilla.torneo` en `produccion/exportar.py` (siembra, rondas, series con
ida/vuelta) y `salidas/vivo_ejemplo.json` (contrato del documento en vivo).
Al terminar el workflow falta (lo hace la sesión principal):
1. Revisar capturas y pruebas; `python3 -m produccion.exportar`, `python3 web/construir.py`.
2. Republicar el Artifact con `capabilities: {db: {rules: [{path: "vivo", read: "view", write: "owner"}]}, user: {}}`
   y los archivos nuevos de `web/archivos_publicados.json`.
3. Sembrar `vivo/actual` con `ArtifactData set` (file_path = copia estable de `salidas/vivo.json`), verificar con
   `list` y con `as_level: "view"`; guardar la versión devuelta en `salidas/vivo_version.txt`.
4. Operación en día de partido (añadir al runbook): la corrida diaria programa con `send_later` un despertar 10 min
   antes de cada inicio; ahí se lanza `python3 vivo.py observar` en segundo plano y `python3 vivo.py esperar --desde N`
   (Bash en segundo plano, máx. 2 h); en cada evento: copiar `salidas/vivo.json` a `salidas/vivo_relevo.json`,
   `ArtifactData set vivo/actual` con `if_version`, guardar versión, volver a esperar; al final del día
   `pipeline.py auto`, republicar y commit.

## Pendientes de mejora
- [ ] Fotos de campeón (`web/medios_parts/campeon.json`, unido a `web/medios.json`): sólo hay festejos libres de Toluca (Cl. 2025) y Pumas (Cl. 2011). Si aparecen fotos libres de otros equipos con el trofeo, agregarlas; la portada las toma sola cuando ese equipo es el favorito. (avanzar uno por corrida diaria si alcanza el presupuesto; marcar al cerrar)
- [ ] Lesionados y técnicos (`config/actualidad.json`, formato en `produccion/MERCADOS.md` §7): antes de la Jornada
  17 (20-22 nov) y de cada ronda de liguilla. Guion: parte "Actualidad" de `notas/workflows/01_reglas_actualidad.js`.
- [ ] Mostrar en la página el rango de la probabilidad de campeón entre modelos (hoy Cruz Azul va de 21% a 33% según
  el modelo; ver `modelo/pruebas/auditoria_resultados/campeon_por_modelo.json`): que `produccion/exportar.py` lo
  calcule (`proyeccion.campeon_por_modelo`) y `web/plantilla.html` lo dibuje.
- [ ] Repetir la validación de mercados y combinadas con el modelo de producción
  (`python3 -m produccion.mercados validar ensamble`, `python3 -m produccion.combinada validar ensamble`) y corregir
  el sesgo de "ambos anotan" (subestimado 3.4 puntos con poisson_simple).
- [ ] Sesgo del simulador tras la ida (subestima ~10 puntos al que cierra en casa): reevaluar con la liguilla real.
- [ ] Retador "con mercado" (mezclar el modelo con los momios disponibles al pronosticar) evaluado sólo con
  pronósticos sellados.
- [ ] Sitio estático (Netlify): `netlify.toml` ya construye `sitio_f1/ligamx/` en cada despliegue.
- [ ] Revisar la página en el Artifact real desde un iPhone (el usuario) y atender lo que reporte.

## Runbook de la tarea diaria ("Cerebro Liga MX diario", 01:20 hora de la Ciudad de México)
1. `cd /home/user/SA/ligamx && python3 pipeline.py auto` (30 s a 2 min). Hace: datos de ESPN → variables → ciclo de
   mejora si hubo partidos nuevos (reevalúa producción y retadores; adopta sólo por regla) → pronósticos sellados,
   calificación de lo jugado, simulación de tabla/liguilla/campeón → página.
   Si el paso `datos` falla por red, reintentar una vez 10 minutos después; si vuelve a fallar, anotarlo aquí.
2. Leer `salidas/ultimo_auto.json`. Si `publicar` es true: republicar el Artifact con
   `file_path=/home/user/SA/ligamx/web/index.html` (y `url=https://claude.ai/artifact/K3fNKhot24LUcwn6PfXGF6` si la
   conversación ya no recuerda la publicación; `files` sólo si cambió `web/archivos_publicados.json`, con
   `root=/home/user/SA/ligamx/web`) y después `python3 pipeline.py publicado`.
3. `git add ligamx && git commit && git push` (rama `claude/new-session-i9lrt6`).
4. Si faltan 3 días o menos para el siguiente partido y `config/actualidad.json` no existe o tiene más de 4 días:
   actualizar lesionados (pendiente de arriba), volver a correr `python3 -m produccion.exportar` y
   `python3 web/construir.py`, republicar.
5. Avisar al usuario SÓLO si: cambió el modelo de producción, se definieron los cruces de la liguilla, terminó una
   serie o hay campeón, o algo falló dos días seguidos. Si no, terminar el turno sin escribirle.
6. Cuando haya campeón: resumen final del desempeño sellado y desactivar la tarea.

## Cómo retomar una fase cortada
- Los guiones de los workflows están copiados en `notas/workflows/` (los originales viven fuera del repo y se
  pierden si el contenedor se reinicia). Para relanzar uno: `Workflow({scriptPath: "<ruta>"})`. Antes de relanzar,
  revisar qué entregables ya existen en disco para no repetir trabajo (editar el guion y quitar lo ya hecho).
- La caché de ESPN (`datos/cache/`) no va al repositorio: si se perdió, `python3 datos/espn_descarga.py todo`
  la reconstruye (~45 min); las tablas CSV sí están versionadas.
- Esta máquina tiene 4 CPU: cada workflow corre 2 agentes a la vez; conviene lanzar 2–3 workflows en paralelo.
- Hacer commit y push al cerrar cada fase (el contenedor es efímero).

## Tareas programadas
- "Cerebro Liga MX diario" (`trig_0195ELWvAUmne2MKmr1ih8zi`): todos los días a la 01:20 (Ciudad de México), en esta sesión. Sigue el runbook de arriba.
- "Continuar Cerebro Liga MX" (`trig_011daxVc81g1dWPVNtuVKMCi`, cada hora): **desactivada** el 10-nov-2026 al
  quedar publicada la página y montada la automatización.

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
- 2026-11-10 10:15 UTC · Terminó `03_campeon_y_produccion.js` completo (4 agentes, 1.15 M de tokens).
- 2026-11-10 10:20 UTC · Lanzado `04_pagina_y_auditoria.js`.
- 2026-11-10 10:45 UTC · Página publicada (Artifact), auditoría hecha, producción = ensamble.
- 2026-11-10 10:55 UTC · `pipeline.py auto` y `mejora ciclo` probados; tarea diaria programada.
