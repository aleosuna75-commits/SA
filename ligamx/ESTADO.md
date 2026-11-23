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

- **Límites de la sesión (11-nov-2026):** «cada que se lleguen a acabar los límites de la sesión, tienes que dejarlo
  programado para la siguiente». Regla: **antes** de lanzar cualquier trabajo largo (workflow o agentes) activar la
  tarea de continuidad cada hora (`trig_011daxVc81g1dWPVNtuVKMCi`, `update_trigger enabled=true`) y dejar en la
  sección «En curso» los pasos que faltan; desactivarla sólo cuando todo esté publicado, con commit y avisado.

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

## En curso
**Cierre de la fase regular y puesta a punto de la liguilla (23-nov-2026, desde 03:20 UTC).** Tarea de continuidad
`trig_011daxVc81g1dWPVNtuVKMCi` ACTIVADA mientras dura. Hecho: `pipeline.py auto` tras Chivas 1-0 Cruz Azul, `vivo/actual`
en versión 107 (terminado_hoy), página republicada (V26) con `liguilla.torneo` «definido» y `pipeline.py publicado`.
Falta, en este orden (si la sesión se corta, retomar aquí):
1. Página en el estado «sin partidos pendientes y cuadro definido»: la portada debe anunciar los cuartos, «Próximos
   partidos» debe mostrar las 8 piernas de cuartos tomadas de `liguilla.torneo` (hoy sale vacío), las series de cuartos
   deben decir «definida» y no «proyectada», y `web/pruebas/prueba.js` debe pasar con 0 pendientes (hoy fallan 3
   revisiones y truena la de pestañas de la combinada).
2. Ensayo de la liguilla con cortes retrospectivos del Clausura 2026 (antes de la ida, entre ida y vuelta, semifinal,
   final): exportar + página + motor en vivo con serie a dos partidos.
3. Regla de menores (confirmar que nadie perdió 3 puntos), horarios y sedes de cuartos (sede de Cruz Azul) y bajas de
   los 8 clasificados en `config/actualidad.json`.
Los pasos 1 a 3 corren en el workflow `notas/workflows/10_liguilla_puesta_a_punto.js`. La primera corrida
(`wf_7ca6f6c0-3d7`, 03:31 UTC) murió a los 18 min porque se agotó el límite del modelo Fable (vuelve el 26-nov 14:00
UTC); el usuario cambió la sesión a Opus y se relanzó como **`wf_c407c924-72c` (23-nov 03:55 UTC)**, con notas de
reanudación para A (página, que dejó cambios a medias, guardados en el commit 9882c91) y B (ensayo, que dejó los 7
cortes y capturas en el scratchpad). Estructura: agentes A página, B ensayo en worktree, C reglas y bajas, D motor en vivo; luego E arreglos,
V1-V3 verificación y F cierre; sus carpetas de trabajo están en el scratchpad `liguilla/`). Si se cortó: relanzar con
`Workflow({scriptPath: <ese guion>, resumeFromRunId: "wf_c407c924-72c"})`; si el contenedor se reinició (no hay
diario), revisar `git status`/`git diff` de `ligamx/`, correr pytest y `web/pruebas/prueba.js` y terminar a mano lo
que falte. Al terminar el workflow: `python3 -m produccion.exportar` (un millón) + `python3 web/construir.py`,
pruebas, republicar con `url` y capabilities, `pipeline.py publicado`. La corrida diaria del 23-nov 07:21 UTC se
pospuso para no pisar al agente F (sin partidos nuevos; `vivo-plan --horas 72` vacío): al terminar el workflow, correr
`pipeline.py auto` en lugar del exportar suelto (incluye exportar con el millón y construir).
4. Programar los despertares en vivo de cuartos cuando ESPN liste los partidos; republicar; bitácora; commit y push;
   desactivar la tarea de continuidad y dejar esta sección en «Nada pendiente».

### Último cierre (11 a 15-nov)
Nada pendiente (11-nov-2026, 04:15 UTC). Lo último cerrado: rediseño a punto (portada por favorito que cabe en la
primera pantalla del iPhone, mini-cuadro del torneo con ida y vuelta, cuadro por ancho, trofeo y confeti), liguilla con
estructura de torneo y pronóstico de ida y vuelta por partido (`liguilla.torneo`), y capa EN VIVO (motor `vivo.py` +
`produccion/en_juego.py`, documento `vivo/actual` en la base del Artifact, página con franja, tarjeta, «Al momento» y
avance de series). Publicado en https://claude.ai/artifact/K3fNKhot24LUcwn6PfXGF6 (V5; V6 con el millón de simulaciones) con
`capabilities` = `web/capacidades.json` (**al republicar pasar SIEMPRE `url` y esas capabilities**; sin `url` se crea
un duplicado, como pasó con https://claude.ai/artifact/9Pa1hLxwQxgokdJJUowHqF, que no se usa y sólo se borra si el
usuario lo pide). Workflows: `notas/workflows/05_vivo_y_rediseno.js` y `06_correcciones.js`; críticas en
`notas/critica_visual_v4.md` y en el diario de la corrida `wf_0172a560-1c9`.
Pruebas al cierre: 157 de pytest, 230 revisiones de página en Chromium y 230 en WebKit (desde el 16-nov: 110 de
producción y 254 revisiones de página por motor; desde el 23-nov, tras el encargo E del workflow 10, `pytest modelo/pruebas
produccion/pruebas` da 209 que pasan y 2 saltadas, y la página 625 revisiones por motor).
**Simulaciones (pedido del usuario, 11-nov):** el pronóstico usa **1,000,000 de torneos** en 50,000 muestras de
parámetros (`produccion/simulador.py`: `N_SIM`, `N_MUESTRAS`; ~55 s y ~4.4 GB; error de P(campeón) ±0.06 puntos, antes
±0.36). La proyección en vivo usa 100,000 en 10,000 muestras (`vivo.py`; ~7 s por actualización; con 1,000,000 cada gol
llegaría ~40 s tarde). Publicado como V6; `vivo/actual` en versión 3.
**Primera prueba real del vivo (14-nov, Querétaro 0-1 Monterrey): funcionó de punta a punta** (detalle en la bitácora).
Falta que el usuario confirme que la página se movió sola en su teléfono: desde aquí sólo se ve que las escrituras
en la base quedaron aceptadas.

## Pendientes de mejora
- [ ] Fotos de campeón (`web/medios_parts/campeon.json`, unido a `web/medios.json`): sólo hay festejos libres de Toluca (Cl. 2025) y Pumas (Cl. 2011). Si aparecen fotos libres de otros equipos con el trofeo, agregarlas; la portada las toma sola cuando ese equipo es el favorito. (avanzar uno por corrida diaria si alcanza el presupuesto; marcar al cerrar)
- [ ] Lesionados y técnicos (`config/actualidad.json`, formato en `produccion/MERCADOS.md` §7): antes de la Jornada
  17 (20-22 nov) y de cada ronda de liguilla. Guion: parte "Actualidad" de `notas/workflows/01_reglas_actualidad.js`.
  **Hecho el 12-nov sólo para Querétaro–Monterrey** (un agente de investigación, ~165 mil tokens): `equipos.<equipo>` con
  `tecnico`, `nota` y `lesionados` = [{jugador, motivo, tipo: lesion | seleccion | duda | suspension | otro, fuente,
  fecha_fuente}] más `fuentes`. La página lo muestra como «Bajas reportadas» con el motivo; el modelo no lo usa.
  **Hecho para los 18 equipos el 18-nov (Jornada 17)** con `notas/workflows/09_bajas_jornada17.js` (3 agentes, 0.54 M
  de tokens, 68 fuentes): el guion devuelve JSON y la sesión principal lo une en `config/actualidad.json` (también
  `cotejo_suspendidos` y `no_confirmado`). Repetir antes de cada ronda de liguilla (sólo los equipos vivos: mucho
  más barato). Casi todo sale de fichas de FotMob; no se encontró el boletín de la Disciplinaria.
- [ ] **Tarjetas de ESPN incompletas:** la prensa da a Óliver Torres (Monterrey) suspendido por quinta amarilla y
  `tarjetas.csv` le cuenta 4 en el Apertura 2026, así que la página lo marcaba sólo «a una amarilla». Se añadió a
  mano en `actualidad.json` (tipo `suspension`). Al investigar bajas, pedir también los suspendidos reportados para
  cotejarlos con `Contexto.suspendidos` y, si se repite, buscar la amarilla que falta (¿partido sin jugadas en ESPN?).
- [ ] Mostrar en la página el rango de la probabilidad de campeón entre modelos (hoy Cruz Azul va de 21% a 33% según
  el modelo; ver `modelo/pruebas/auditoria_resultados/campeon_por_modelo.json`): que `produccion/exportar.py` lo
  calcule (`proyeccion.campeon_por_modelo`) y `web/plantilla.html` lo dibuje.
- [x] Mercados y combinadas revalidados con `ensamble` (15-nov, workflow 07; informe `produccion/MERCADOS_ENSAMBLE.md`,
  guiones en `produccion/investigacion/mercados_2026_11/`). Resultado: 35 de 52 mercados le ganan a la constante (26
  con el provisional), los totales ya discriminan, las tres combinadas están calibradas (también en PRUEBA). **No se
  adoptó ninguna corrección:** las cuatro probadas reducen el sesgo pero mejoran 0.8 a 1.6 ee (se exigían 2).
- [ ] **«Ambos anotan» sigue corto**: 1.9 puntos en DESARROLLO y 5.8 en PRUEBA (z = 3.2; parte es forma, parte es que
  el nivel de goles de la liga subió). La corrección de forma de 1 parámetro (`forma_1`: marginales
  Conway-Maxwell-Poisson, 1X2 intacto) queda como candidata seria: z = −1.4 en DESARROLLO, −2.5 en PRUEBA (leída una
  vez, después de fallar la regla: no sirve para elegir). Decidirla por `modelo.mejora` (cambia el marcador sellado)
  o con los pronósticos sellados que se acumulen; no reintentar variantes sobre el mismo DESARROLLO.
- [ ] `python3 -m produccion.mercados validar ensamble` y `... combinada validar ensamble` corren con rho = 0
  (`modelo/pred/ensamble.parquet` no guarda `x_rho`): que el arnés lo guarde o que `validar` lo recupere de
  `modelo/cache/M_ensamble.npz`.
- [ ] Sesgo del simulador tras la ida (subestima ~10 puntos al que cierra en casa): reevaluar con la liguilla real.
- [ ] Retador "con mercado" (mezclar el modelo con los momios disponibles al pronosticar) evaluado sólo con
  pronósticos sellados. **Paso previo hecho el 16-nov (workflow 08):** cada sello guarda los momios del momento y su
  1X2 sin margen (Shin) en `mercado`; `desempeno.contra_mercado` califica al mercado en los mismos partidos (pareado,
  con error estandar y `lectura`), y la página lo muestra («Modelo contra mercado»). Los 9 partidos de la Jornada 17
  ya están sellados con momios. Falta: (a) decidir con el usuario si el pronóstico final (picks, marcador,
  combinadas) debe usar los momios; en la historia el mercado de cierre gana por 0.019 de log-loss; los de apertura
  sólo existen desde dic-2025; (b) si se hace, sellar también cerca del inicio (en «armar») para usar momios casi de
  cierre. La tarjeta de pendientes muestra el reparto proporcional y el sello guarda Shin: unificar.
- [ ] Sitio estático (Netlify): `netlify.toml` ya construye `sitio_f1/ligamx/` en cada despliegue.
- [ ] Revisar la página en el Artifact real desde un iPhone (el usuario) y atender lo que reporte.

- **Vivo, tras el primer partido real (14-nov):** revisar `salidas/vivo_observar.log` (nombres de estado y reloj de
  ESPN en descanso y agregado) y lo que quedó sin arreglar de la crítica funcional: H14 (el evento se anota antes de
  escribir `vivo.json`), H15 (vuelta sin `auto` tras la ida parte de 0-0 sin aviso), H16 (partido abandonado sale
  como final), H17 (pausa a media parte sale como «Descanso»), descanso del tiempo extra en una final, y la portada a
  320 px de ancho (se pasa 5 px). Costo estimado: 8 a 10 despertares por partido, 70 a 80 por jornada de 9.
- **Demo del vivo a pedido:** `python3 vivo.py repetir 401876913 --velocidad 60` y escribir `salidas/vivo_prueba.json`
  en `vivo/actual` (VIVO.md §6.6; nunca con partido real en las siguientes 3 h; al terminar volver a poner el real).

## Runbook de la tarea diaria ("Cerebro Liga MX diario", 01:20 hora de la Ciudad de México)
0. Si «En curso» tiene pasos pendientes y no hay nada corriendo, retomarlos primero.
1. `cd /home/user/SA/ligamx && python3 pipeline.py auto` (30 s a 2 min). Hace: datos de ESPN → variables → ciclo de
   mejora si hubo partidos nuevos (reevalúa producción y retadores; adopta sólo por regla) → pronósticos sellados,
   calificación de lo jugado, simulación de tabla/liguilla/campeón → estado en vivo del día → página.
   Si el paso `datos` falla por red, reintentar una vez 10 minutos después; si vuelve a fallar, anotarlo aquí.
2. Leer `salidas/ultimo_auto.json`. Si `publicar` es true: republicar el Artifact con
   `file_path=/home/user/SA/ligamx/web/index.html`, **siempre** con
   `url=https://claude.ai/artifact/K3fNKhot24LUcwn6PfXGF6` y `capabilities` = contenido de `web/capacidades.json`
   (`files` sólo si cambió `web/archivos_publicados.json`, con `root=/home/user/SA/ligamx/web`); después
   `python3 pipeline.py publicado`. Luego `cp salidas/vivo.json salidas/vivo_relevo.json` y escribir la copia en la
   base: `ArtifactData set`, `collection` `vivo`, `doc_id` `actual`, `file_path` = la copia, `if_version` =
   `salidas/vivo_version.txt`; guardar ahí la versión nueva.
3. **En vivo:** `python3 pipeline.py vivo-plan --horas 48`. Por cada bloque de partidos (inicios con menos de 2 h 30
   de diferencia) sin despertares ya programados (`list_triggers`): `send_later` «armar» 20 min antes del primer
   inicio, «vigilar» 60 min después de cada inicio y «cierre» 2 h 30 después del último. El día de partido se sigue
   **`produccion/VIVO.md` sección 6** (único procedimiento: `vivo.py observar` en segundo plano, `vivo.py esperar`
   despierta a la sesión en cada evento y cada despertar es una sola escritura en `vivo/actual`).
4. `git add ligamx && git commit && git push` (rama `claude/new-session-i9lrt6`).
5. Si faltan 3 días o menos para el siguiente partido y `config/actualidad.json` no existe o tiene más de 4 días:
   actualizar lesionados (pendiente de arriba), volver a correr `python3 -m produccion.exportar` y
   `python3 web/construir.py`, republicar.
6. Avisar al usuario SÓLO si: cambió el modelo de producción, se definieron los cruces de la liguilla, terminó una
   serie o hay campeón, o algo falló dos días seguidos. Si no, terminar el turno sin escribirle.
7. Cuando haya campeón: resumen final del desempeño sellado y desactivar la tarea.

## Cómo retomar una fase cortada
- Los guiones de los workflows están copiados en `notas/workflows/` (los originales viven fuera del repo y se
  pierden si el contenedor se reinicia). Para relanzar uno: `Workflow({scriptPath: "<ruta>"})`. Antes de relanzar,
  revisar qué entregables ya existen en disco para no repetir trabajo (editar el guion y quitar lo ya hecho).
- La caché de ESPN (`datos/cache/`) no va al repositorio: si se perdió, `python3 datos/espn_descarga.py todo`
  la reconstruye (~45 min); las tablas CSV sí están versionadas.
- Esta máquina tiene 4 CPU: cada workflow corre 2 agentes a la vez; conviene lanzar 2–3 workflows en paralelo.
- Hacer commit y push al cerrar cada fase (el contenedor es efímero).

## Tareas programadas
- "Cerebro Liga MX diario" (`trig_0195ELWvAUmne2MKmr1ih8zi`): todos los días a la 01:20 (Ciudad de México), en esta
  sesión. Sigue el runbook de arriba (prompt actualizado el 11-nov con el paso «en vivo»).
- "Continuar Cerebro Liga MX" (`trig_011daxVc81g1dWPVNtuVKMCi`, cada hora): **ACTIVA desde el 23-nov-2026 03:26 UTC**
  (puesta a punto de la liguilla); se desactiva al dejar «En curso» en «Nada pendiente». **Activarla antes de cada
  trabajo largo** (regla del usuario sobre los límites).
- Los despertares en vivo de la Jornada 17 (viernes, sábado y domingo) ya se cumplieron; el «cierre» del domingo
  (`trig_01CGwZtpXxFi73qvKfSYhPMz`) se borró el 23-nov 03:31 UTC porque el cierre se hizo a mano al terminar el partido.
- «Liga MX: calendario de cuartos» (`trig_01TL9jTmiLVZi8GVJAQVWM9s`, una vez, lunes 23-nov 17:00 de México = 23:00 UTC):
  corre `pipeline.py auto`; si ESPN ya lista los cuartos, republica, programa los despertares en vivo de cada día de
  partido (VIVO.md §6.1) y avisa al usuario con horarios y pronósticos completos; si no, se reprograma 4 h después.

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
- 2026-11-11 04:15 UTC · Rediseño a punto y capa en vivo publicados (V5). Workflow 05 cortado por el límite (3 de 5
  agentes); al volver el límite se publicó una intermedia (V4) y se corrió el 06 (corrección visual de 17 defectos ∥
  crítica funcional con 23 hallazgos → cierre: 13 altos/medios atendidos). Base del Artifact: `vivo/actual` en
  versión 2. El usuario pidió dejar siempre programada la continuación cuando se acaben los límites.
- 2026-11-11 04:50 UTC · Simulaciones a 1,000,000 (50,000 muestras) en el pronóstico y 100,000 en vivo. Resultado:
  América 26.6%, Cruz Azul 26.3%, Toluca 20.0%, Chivas 19.3% (coherente con la corrida de 20,000: diferencias de menos
  de 1.7 errores estándar). `pipeline.py auto` tarda 68 s. Pruebas: 82 de producción, 230 + 230 de página. V6 publicada.
- 2026-11-11 07:30 UTC · Corrida diaria: sin partidos nuevos; momios actualizados; V7 publicada, `vivo/actual` en versión 4. Sin partidos en 48 h (despertares del 14-nov ya programados). No se avanzó un pendiente de mejora: la ventana de límite de hoy ya se usó en el rediseño.
- 2026-11-12 08:00 UTC · Corrida diaria: sin partidos nuevos; V8 publicada y `vivo/actual` en versión 5. Bajas de
  Querétaro–Monterrey en `config/actualidad.json` (1 y 6, con fuentes) y en la tarjeta del partido (V9). Una revisión
  de reconexión de `prueba.js` fallaba en WebKit por depender del reloj real: ahora avanza el reloj simulado.
- 2026-11-13 07:30 UTC · Corrida diaria: sin partidos nuevos; V10 publicada, `vivo/actual` en versión 6. Despertares del vivo de Querétaro–Monterrey (14-nov) confirmados. Bajas de Monterrey revisadas con una búsqueda: sin novedades desde el 11-nov (Orellano entrena al parejo y apunta a jugar, Durdevic sigue aparte; otro medio confirma a Óliver Torres suspendido), no se cambió `config/actualidad.json`.
- 2026-11-14 07:25 UTC · Corrida diaria (día de partido): sin partidos nuevos; V11 publicada, `vivo/actual` en versión 7. Hoy 23:00 UTC Querétaro–Monterrey: «armar» 22:40, «vigilar» 00:00 y «cierre» 01:30 UTC programados. Ojo: a esta hora `vivo.py estado` dice sin_partidos porque el día de partido cambia a las 04:00 de México.
- 2026-11-15 01:40 UTC · **Primera prueba real del vivo: Querétaro 0-1 Monterrey.** `observar` corrió de 22:40 a 01:14 UTC
  sin caídas ni respuestas raras de ESPN; 9 eventos: inicio (23:02:43), refresco 26', descanso (23:49:39), segundo tiempo
  (00:07:42), gol de Monterrey 48' (00:09:52; ESPN lo dio primero sin goleador y después «Diego Rossi»), roja 51' de
  Querétaro (ESPN la publicó hasta el 54'), refresco 79', roja 80' (al 82') y final (01:03:50). 11 despertares de la
  sesión (armar, vigilar y 9 eventos) y 11 escrituras en `vivo/actual` (versiones 8 a 18). De evento detectado a
  escritura: 15 a 20 s en goles y rojas, 50 a 80 s en lo que se agrupa (inicio, descanso, refresco). **Una falla:** en
  el descanso la herramienta rechazó la escritura porque `observar` reemplazó `vivo.json` en ese instante; se resolvió
  escribiendo desde una copia (`vivo_relevo.json`) y así quedó en VIVO.md §6.4. `vivo.json` dejó de versionarse.
  Modelo en juego: al descanso 0-0 daba 26.5 / 38.2 / 35.3. Cierre: `pipeline.py auto` (ciclo de mejora sin cambio de
  modelo), primer pronóstico sellado calificado: acertó el ganador (Monterrey, 42.9%), no el marcador (1-1), y la
  combinada «equilibrada» salió completa (4 de 4). V12 publicada. Siguiente partido: Puebla–San Luis, 21-nov 01:00 UTC.
- 2026-11-15 07:40 UTC · Corrida diaria: sin partidos nuevos; V13 publicada, `vivo/actual` en versión 19. Lanzado el workflow `07_mercados_ensamble.js` (tarea `wegjk24p6`, corrida `wf_0ce44788-b0f`): medición → corrección → auditoría de mercados y combinadas con `ensamble`. Para reanudarlo: `Workflow({scriptPath: "/home/user/SA/ligamx/notas/workflows/07_mercados_ensamble.js", resumeFromRunId: "wf_0ce44788-b0f"})`.
- 2026-11-15 08:45 UTC · Workflow 07 terminado (3 agentes, 0.75 M de tokens): medición, cuatro correcciones candidatas
  (ninguna pasa la regla escrita de antemano) y auditoría independiente (sin fugas, cifras reproducidas; lectura única
  de PRUEBA: combinadas confirmadas, «ambos anotan» 5.8 puntos corto). Producción sin cambios en los pronósticos. Se
  arregló `test_ultimos_resultados_usan_el_sello_oficial` (tenía un 9 escrito a mano), se actualizó la nota honesta de
  la página sobre esos mercados y se publicó V14 (`vivo/actual` en versión 20). 82 pruebas de producción en verde.
- 2026-11-16 07:35 UTC · Corrida diaria: sin partidos nuevos; V15 publicada, `vivo/actual` en versión 21. Se revisó el pendiente del sesgo del simulador tras la ida: ya se probó un factor de vuelta con las 119 series y no pasó (1.1 ee); sin datos nuevos no se reintenta hasta tener la liguilla real.
- 2026-11-16 07:42 UTC · Lanzado `08_momios_en_sellos.js` (tarea `w71jro89s`, corrida `wf_dcc3775a-252`). Para reanudarlo: `Workflow({scriptPath: "/home/user/SA/ligamx/notas/workflows/08_momios_en_sellos.js", resumeFromRunId: "wf_dcc3775a-252"})`.
- 2026-11-16 08:30 UTC · Workflow 08 terminado tras un corte del servicio (error 529; se relanzó con `resumeFromRunId`):
  sellos con momios y «Modelo contra mercado» en el desempeño y en la página; revisión independiente «listo con
  arreglos» (sin fugas, Shin y métricas reproducidos, 49 sellos viejos intactos). 9 sellos nuevos con mercado
  (Jornada 17). 110 pruebas de producción y 254 + 254 de página en verde. V16 publicada; `vivo/actual` en versión 22.
  Lección: los puntos de control automáticos a media revisión pueden llevarse archivos temporales (`web/.gitignore`
  ya ignora `_rev_*.html` y `_variante_*.html`).
- 2026-11-17 15:00 UTC · Corrida diaria (la tarea llegó 7 h 38 min tarde: programada 07:20 UTC, entregada 14:58): sin partidos nuevos; Tijuana–Atlante y Querétaro–Necaxa se recorrieron 10 min; V17 publicada, `vivo/actual` en versión 23. Mañana (≤ 3 días para la Jornada 17) toca actualizar `config/actualidad.json` para los 18 equipos y programar los despertares del vivo del viernes.
- 2026-11-18 07:30 UTC · Corrida diaria: sin partidos nuevos; V18 publicada, `vivo/actual` en versión 24.
- 2026-11-18 07:35 UTC · Lanzado `09_bajas_jornada17.js` (tarea `w76vvdy83`, corrida `wf_454f2f0b-55a`); para reanudarlo: `Workflow({scriptPath: "/home/user/SA/ligamx/notas/workflows/09_bajas_jornada17.js", resumeFromRunId: "wf_454f2f0b-55a"})`. Programados los cuatro despertares del vivo del viernes.
- 2026-11-18 07:45 UTC · Bajas de la Jornada 17 integradas (18 equipos; 9 de 9 partidos con bajas en su tarjeta) y V19 publicada. Cotejo de suspendidos: los 13 que deduce el sistema aparecen en alguna fuente; un agregador da además a Gorriarán (Tigres) por quinta amarilla, el sistema cuenta 4 (la amarilla de una doble amonestación no acumula) y nadie más lo confirma: quedó como duda.
- 2026-11-19 07:25 UTC · Corrida diaria: sin partidos nuevos; V20 publicada, `vivo/actual` en versión 25. Programado el vivo del sábado (5 despertares). No se avanzó un pendiente de mejora: se guarda el presupuesto para el fin de semana de 9 partidos en vivo.
- 2026-11-20 07:25 UTC · Corrida diaria (hoy arranca la Jornada 17): sin partidos nuevos; V21 publicada, `vivo/actual` en versión 26; 83 sellos. Programado el vivo del domingo (4 despertares): los tres bloques del fin de semana ya tienen sus despertares. Esta sesión también atiende las tareas de F1 de Las Vegas (20 a 22-nov), que se intercalan con el vivo.
- 2026-11-21 07:05 UTC · **Viernes de la Jornada 17 en vivo** (Puebla 1-1 San Luis, Juárez 3-3 Atlas, Tijuana 1-0 Atlante):
  26 eventos (10 a 35), todos escritos en `vivo/actual` (versiones 27 a 52) sin rechazos gracias a la copia estable;
  primer **gol anulado** real (Juárez 2-1 → 1-1 al 45'+4') bien corregido; dos goles en la misma consulta (Atlas y
  Tijuana, 04:48) salieron en un solo despertar. A la vez corrió el vivo de la qualy de F1 (28 relevos). **La sesión se
  quedó sin límite de uso a las 05:07 UTC** (unas 80 respuestas en 4 h 50 min) y volvió a las 06:55: no se perdió nada
  visible de la Liga MX (el último final se escribió a las 05:07), pero el cierre y el aviso de F1 salieron 1 h 45 tarde.
  Para el sábado: `vivo_relevo.sh` (un despertar = una respuesta). Cierre: 4 sellos calificados; el modelo acertó 2 de 4
  ganadores y 1 marcador exacto; combinadas completas: segura 1 de 4, equilibrada 2 de 4, atrevida 1 de 4. Modelo contra
  mercado (3 partidos con momios sellados): log-loss 1.040 contra 1.075, diferencia −0.035 ± 0.008 a favor del modelo:
  demasiado pocos para concluir. V22 publicada. Campeón: América 26.4%, Cruz Azul 26.1%, Toluca 19.8%, Chivas 19.1%.
- 2026-11-21 07:25 UTC · Corrida diaria: sin partidos nuevos tras el cierre de las 07:00; momios actualizados; V23 publicada (`vivo/actual` sigue en versión 52: el documento no cambió de estado). Bloques del sábado y del domingo ya programados. Sin avanzar pendientes de mejora: el presupuesto de uso se guarda para el vivo del fin de semana.
- 2026-11-22 05:25 UTC · **Sábado de la Jornada 17 en vivo** (Pachuca 2-0 Toluca, Santos 1-2 León, Pumas 0-2 Monterrey, Tigres 1-0 América): 35 eventos (36 a 70) escritos en `vivo/actual` (versiones 53 a 88) con `vivo_relevo.sh`, una respuesta por despertar; esta vez NO se acabó el límite de uso (a la vez se atendió la parrilla de F1). Segundo gol anulado real (Tigres, 65') bien corregido. Cierre: 8 sellos calificados, 3 ganadores y 1 marcador exacto; combinadas completas: segura 2 de 8, equilibrada 4 de 8, atrevida 1 de 8. Modelo contra mercado (7 partidos): 1.051 contra 1.073, diferencia −0.022 ± 0.041: sin conclusión. Ciclo de mejora sin cambio de modelo. **Los ocho clasificados ya están definidos** (Cruz Azul, América, Chivas, Atlas, Toluca, Monterrey, León, Pachuca; Pachuca entra con 25 puntos por desempate sobre Tijuana y Santos); falta el orden de los tres primeros (Chivas–Cruz Azul del domingo). Favorito nuevo: Cruz Azul 26.4%, América 22.9%, Chivas 19.4%, Toluca 18.0%, Pachuca 5.6%. V24 publicada.
- 2026-11-22 07:25 UTC · Corrida diaria: sin partidos nuevos tras el cierre de las 05:25; V25 publicada (`vivo/actual` sigue en versión 88). Hoy se juega el bloque del domingo (Chivas–Cruz Azul 23:07 UTC, Querétaro–Necaxa 01:10 UTC), ya programado; su cierre avisa al usuario de los cruces. Mañana: bajas de los 8 clasificados para los cuartos (`config/actualidad.json` tiene 4 días).
- 2026-11-23 03:30 UTC · **Domingo de la Jornada 17 en vivo y FIN DE LA FASE REGULAR** (Chivas 1-0 Cruz Azul, Querétaro 2-2 Necaxa): 18 eventos (71 a 88) escritos en `vivo/actual` (versiones 89 a 106) con `vivo_relevo.sh`, sin rechazos ni cortes por límite; el bucle salió con código 3 (`terminado_hoy`) a las 03:17 UTC. Cierre a mano en cuanto acabó el partido (sin esperar el despertar de las 03:40, que se borró): `pipeline.py auto` (ciclo de mejora sin cambio de modelo), `vivo/actual` en versión 107, **V26 publicada** con `liguilla.torneo` «definido». Tabla final (coincide con ESPN): Chivas 33, Cruz Azul 32, América 30, Atlas 28, Toluca 27, Monterrey 27, León 26, Pachuca 25 (fuera Tijuana y Santos con 25). Cuartos: Chivas–Pachuca (avanza Chivas 64%), Cruz Azul–León (82%), América–Monterrey (71%), Atlas–Toluca (Toluca 72%). Campeón: Cruz Azul 26.4%, Chivas 20.8%, América 20.8%, Toluca 18.3%, Pachuca 5.8%, Monterrey 4.8%, Atlas 1.8%, León 1.3% (que Cruz Azul siga en 26.36% tras perder es coincidencia comprobada: su fuerza bajó de 0.761 a 0.707 pero cambia a Pachuca por León en cuartos; p_semifinal pasó de 73.7% a 81.1%). **Jornada 17 completa (9 partidos): 3 ganadores acertados y 1 marcador exacto; combinadas completas: segura 3 de 9, equilibrada 3 de 9, atrevida 1 de 9. Modelo contra mercado (9 partidos con momios sellados): log-loss 1.059 contra 1.080 (−0.021 ± 0.032, a favor del modelo pero sin poder concluir; el favorito del mercado ganó 2 de 9).** Acumulado de sellos calificados (10): 4 ganadores, log-loss 1.038. Los medios confirman los cruces (El Heraldo, Telediario, Diario Puntual); ESPN todavía no lista los cuartos (la liga publica horarios el lunes 23). Con 0 pendientes la página deja dos secciones vacías y `web/pruebas/prueba.js` falla (3 revisiones + la de pestañas): se lanzó el workflow `10_liguilla_puesta_a_punto.js` (`wf_7ca6f6c0-3d7`) y se activó la tarea de continuidad.
