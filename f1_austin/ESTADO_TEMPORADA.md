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

## Mejora continua (pedido 9/11 ~02:45 UTC): "que mejore automáticamente tras cada sesión"
Workflow wf6fu1mrp (hora límite 06:30 + verificación 07:30 UTC): paso post_fp1 + pronóstico preliminar de carrera tras cada práctica
(historial.json por GP), ciclo campeón/retador `mejora_modelos.py ciclo` tras cada carrera (adopta sólo si mejora > z_crit EE [corregido: era 1 EE] y no
empeora en los últimos 8 GP; bitácora en modelos/bitacora.json → doc bitacora/actual), sección "Evolución del modelo" en la página.
- [x] Integrar: reglas db nuevas (historial, bitacora), publicar, runbook RB-0 (post-FP1) y RB-7 (mejora tras carrera),
      tareas nuevas: post-FP1 (LV 20/11 01:50, QAT 27/11 14:50, ABU 04/12 10:50 UTC) y RB-7 (LV 22/11 08:00, QAT 29/11
      20:00, ABU 06/12 17:00 UTC); RB-6 pasa a `F1_SIN_MEJORA=1 ... auto`

## Mejora continua tras cada sesión (pedido 9/11/2026: "que mejore automáticamente tras cada sesión")
- [x] Paso `post_fp1` (qualy sólo con FP1 + historial, `--fp1`) y carrera PRELIMINAR en post_fp1/pre_qualy/fp3 (parrilla =
      qualy pronosticada; `preliminar: true`); post_qualy la reemplaza. `historial.json` por GP (fases FP1/FP2/FP3/Q y cambios).
- [x] `mejora_modelos.py` (campeón/retador; modelos/registro.json, config_activa.json, bitacora.json, cache/) y paso `mejora`
      en `auto` tras post_carrera (una vez por GP).
- [x] México y Brasil: historial.json rellenado en retro sin fugas (`gp_pipeline.py historial <mk>`).
- [ ] Artifact: agregar reglas db para las colecciones nuevas `historial` y `bitacora` y sembrar historial/mexico2026,
      historial/brasil2026, bitacora/actual (+ republicar carrera/mexico2026, carrera/brasil2026 con `preliminar: false`,
      y meta/actual). La página ya los muestra (#trayecto "Cómo cambió el pronóstico" y #evolucion "Evolución del modelo").
- [x] Tareas programadas RB-0 (post-FP1) — sugeridas, UTC: Las Vegas 20/11 01:50 · Qatar 27/11 14:50 · Abu Dabi 04/12 10:50.
      Sin RB-0, la RB-1 corre post_fp1 + pre_qualy juntos (≈ +8 min; historial igual completo).

Verificación adversarial (9/11 04:30–05:15 UTC): sin fugas (filas de los 89 GP previos idénticas con y sin los datos de
Brasil; FP1/FP2/FP3 preliminares sólo con su corte), México FP2/FP3 y Brasil FP3/carrera se reproducen idénticos. La regla
"> 1 EE" adoptaba ruido (RF idéntico con otra semilla: 7/30 pasaban; Monte Carlo: 4/12) -> regla corregida (abajo); las
adopciones rf_fijo del primer ciclo (qualy FP1 y FP3, z 1,42 y 2,05: dentro del ruido de semilla) se revirtieron (ningún
pronóstico publicado las usó) y el ciclo se rehizo: 0 adopciones, racecraft_form3 descartado. auto: mejora va al final;
F1_SIN_MEJORA; post_fp1 tardío ya no pisa carrera.json de una fase posterior. Página: lista de candidatos rota a 390 px
(columna de nombre de 20 px) corregida.

Cambios al RUNBOOK (verificados 9/11 ~05 UTC; además de lo anterior):
- TODAS las corridas de `auto` con modelos (RB-0, RB-1, RB-3, fin de RB-4, RB-7) van con run_in_background y se espera a que
  termine (pre_qualy ≈ 8 min + carrera preliminar ≈ 2 min + descarga: pasa el tope de 10 min de una llamada en primer plano).
- RB-0 post-FP1 (nuevo; fin de FP1 + 20 min. UTC: Las Vegas 20/11 01:50 · Qatar 27/11 14:50 · Abu Dabi 04/12 10:50):
  `python3 gp_pipeline.py auto` en segundo plano (post_fp1: descarga + `modelo_qualy_austin.py <mk> --fp1` + carrera
  PRELIMINAR; ≈ 10–12 min con la selección automática; la FP2 empieza 2 h 30 después del fin de la FP1). Leer `gps/ultimo_auto.json`. Si trae
  `reintentar` con hora, send_later con este RB-0 a esa hora; si `reintentar_utc` es null lo recoge RB-1 (post_fp1 no
  bloquea a pre_qualy). Publicar `docs_a_publicar` (gp/<slug> fase FP1, carrera/<slug> con preliminar: true,
  historial/<slug>, meta/actual) igual que RB-1 (docs + construir_web + Artifact + publicar_sitio + commit). Avisar corto:
  Top 10 de qualy con sólo la FP1 y ganador PRELIMINAR (parrilla = qualy pronosticada).
- RB-1 / RB-3: además de gp publican carrera (preliminar) e historial. Avisar qué cambió (historial.fases[-1].cambios).
- RB-4: post_qualy publica también historial (fase Q: carrera con la parrilla real, preliminar: false). `auto` sólo corre
  post_qualy desde fin de qualy + 10 min (LV 05:10 UTC): si se llama antes y no aparece post_qualy, repetir a esa hora.
- RB-6 (carrera + 2 h 15): `F1_SIN_MEJORA=1 python3 gp_pipeline.py auto` (sólo post_carrera, ~1 min; el ciclo de mejora
  NO corre aquí). Publicar y avisar como antes. Si OpenF1 aún no tiene el resultado: reintento +1 h (igual).
- RB-7 mejora (nuevo; carrera + 4 h, para que Jolpica ya tenga la carrera. UTC: Las Vegas 22/11 08:00 · Qatar 29/11 20:00 ·
  Abu Dabi 06/12 17:00): `python3 gp_pipeline.py auto` en segundo plano (timeout 2 h): repite post_carrera ("sin
  cambios") y corre `mejora` (descarga, `mejora_modelos.py ciclo`, presupuesto F1_PRESUPUESTO_MEJORA = 40 min; normal
  5–10 min porque la cache sólo recalcula el GP nuevo). Leer `gps/ultimo_auto.json`: publicar bitacora/actual
  (modelos/bitacora.json; leer versión y pasar if_version) + meta si cambió; construir_web + Artifact + publicar_sitio +
  commit. Avisar: adopciones nuevas (bitacora.cambios con fecha de hoy: tarea, de → a, diferencia, EE, z) o "sin
  cambios: el modelo vigente sigue siendo el mejor" (+ 1 línea con aciertos del GP de bitacora.evolucion). Si la acción
  mejora falló o `ultimo_ciclo.sin_tiempo` no está vacío: un reintento con `python3 gp_pipeline.py paso mejora <mk>
  --forzar` en segundo plano 2 h después (antes de la FP1 del GP siguiente − 2 h); si no hubo carrera en Jolpica, la tarea
  carrera la toma el ciclo siguiente. `mejora` es una vez por GP y en `auto` corre siempre al final (después de los pasos
  de un GP en curso).
- Regla de adopción (corregida en la verificación): mejora > z_crit EE con z_crit = max(2, Bonferroni unilateral 10 % sobre
  los k retadores; 2,33 con 10, 2,47 con 15), sin empeorar en los últimos 8 GP, y confirmada con 3 semillas (campeón:
  producción + 1, 2; retador: producción + 3, 4; en carrera el EE suma el ruido de semilla del Monte Carlo).
- Un agente puede proponer variantes: `python3 mejora_modelos.py agregar-candidato '<json>'` (se evalúan en el próximo
  ciclo y sólo se adoptan si pasan esa regla).
05:15 UTC 9/11: Artifact v20 (9 reglas db), docs historial/{mexico2026,brasil2026}, bitacora/actual v1, carrera/mexico2026 v5,
carrera/brasil2026 v2, meta/actual v2. Tareas nuevas: RB-0 LV 20/11 01:50 · QAT 27/11 14:50 · ABU 04/12 10:50; RB-7 LV 22/11 08:00 ·
QAT 29/11 20:00 · ABU 06/12 17:00 (UTC). Total 24 tareas programadas. Primer ciclo de mejora (regla corregida): 0 adopciones.
