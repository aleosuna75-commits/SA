# Estado: pronósticos automáticos para todos los GP (pedido 9/11/2026)

Pedido: hacer Brasil (ya corrido el 6-8/11: se hace en retrospectiva, cada paso sólo con datos previos a su sesión) y que todo se
actualice solo para los GP restantes: Las Vegas (1300), Qatar (1301), Abu Dhabi (1302). Una sola URL (Artifact
https://claude.ai/artifact/A5ptCSyCPL7Eb63tt5U6zJ) que muestre el GP en curso + archivo; temas por GP.

- [x] Workflow wngpp26f1 (hora límite 05:30 UTC): gp_pipeline.py (auto/retro/pasos, gps/<slug>/, meta.json, post_carrera nuevo)
      + web/plantilla.html + temas + construir_web.py + publicar_sitio.py multi-GP
- [x] Verificación adversarial (sin fugas en retro, evaluaciones correctas, página por tema)
- [x] Publicar: Artifact con reglas db para gp, live, postqualy, carrera, vueltas, postcarrera, meta; sembrar docs de mexico2026 y
      brasil2026 y meta/actual; sitio Netlify; commit
- [x] Tareas programadas por sesión para 1300/1301/1302 (tras FP2, tras FP3, qualy−12 min en vivo, post-qualy, post-carrera)

## RUNBOOK de las tareas programadas (cada una dispara un turno en esta sesión)
Artifact: https://claude.ai/artifact/A5ptCSyCPL7Eb63tt5U6zJ — publicar SIEMPRE con file_path `f1_austin/web/index.html` (misma URL).
Docs: archivo `gps/<slug>/X.json` → colección/doc_id: gp.json→gp, live_qualy.json→live, post_qualy.json→postqualy, carrera.json→carrera,
vueltas.json→vueltas, post_carrera.json→postcarrera; `gps/meta.json`→meta/actual. Antes de escribir un doc existente, leer su versión
(ArtifactData get) y pasar if_version; los nuevos van sin if_version. Agrupar en un batch.
Publicar = docs (batch) + `python3 construir_web.py` + Artifact publish de f1_austin/web/index.html + `python3 publicar_sitio.py` + commit/push.

- RB-1 post-FP2: `python3 gp_pipeline.py auto`; leer `gps/ultimo_auto.json`. Si trae `reintentar`, programar send_later en `reintentar_utc`
  con este mismo RB-1. Publicar los `docs_a_publicar`. Avisar al usuario el Top 10 de qualy pronosticado (corto).
- RB-2 FP3 −12 min: lanzar en segundo plano (run_in_background) el comando de FP3 de `python3 gp_pipeline.py comandos <mk>`
  (respaldo por si OpenF1 bloquea con 401). Nada visible.
- RB-3 post-FP3: `python3 gp_pipeline.py auto` (paso fp3; si OpenF1 da 401 reconstruye desde la grabación). Publicar. Avisar qué cambió.
- RB-4 qualy −12 min: lanzar en segundo plano el colector de qualy de `comandos <mk>` (si se cae, relanzar igual: tiene --precargar).
  Relevo hasta que el snapshot diga estado "terminada": esperar cambios (helper scratchpad/live/esperar_snapshot.sh adaptado a
  gps/<slug>/live_qualy.json, copiando a un archivo fijo antes de enviarlo), ArtifactData set de live/<slug> cada ~70 s y
  construir_web.py + publish cada ~4 min. Al terminar: buscar penalizaciones y sustituciones (WebSearch) → `gps/<slug>/ajustes.json`;
  `python3 gp_pipeline.py auto` (post_qualy: evaluación + carrera + vuelta a vuelta); publicar; avisar resultado vs pronóstico y Top 10 de carrera.
- RB-5 carrera −3 h: revisar parrilla oficial (OpenF1 starting_grid / prensa: pit lane, penalizaciones, lluvia). Si cambió, actualizar
  ajustes.json, `auto` (post_qualy se repite), publicar y avisar. Si no, nada visible.
- RB-6 carrera +2 h 15 min: `python3 gp_pipeline.py auto` (post_carrera; si no está el resultado oficial, programar reintento +1 h).
  Publicar (incluye meta). Avisar cómo le fue al modelo en la carrera.

02:45 UTC 9/11: Artifact v19 'Pole F1 2026' publicado (multi-GP, 7 reglas db); 13 docs sembrados (mexico2026, brasil2026, meta/actual).
02:37 UTC 9/11: 18 tareas programadas (send_later a esta sesión), UTC:
 Las Vegas: RB-1 20/11 05:40 · RB-2 21/11 00:18 · RB-3 21/11 01:50 · RB-4 21/11 03:48 · RB-5 22/11 01:00 · RB-6 22/11 06:15
 Qatar:     RB-1 27/11 18:40 · RB-2 28/11 14:18 · RB-3 28/11 15:50 · RB-4 28/11 17:48 · RB-5 29/11 13:00 · RB-6 29/11 18:15
 Abu Dabi:  RB-1 04/12 14:40 · RB-2 05/12 10:18 · RB-3 05/12 11:50 · RB-4 05/12 13:48 · RB-5 06/12 10:00 · RB-6 06/12 15:15
Resultados retro/evaluación: Brasil qualy 6/10 (pole NOR; modelo ANT), carrera 9/10 con ganador NOR ✓ y podio 2/3; México carrera 7/10
(ganó VER; modelo HAM), podio 1/3.
