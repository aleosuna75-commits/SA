# Estado: GP de México 2026 (qualy sábado 31/10, 21:00 UTC)

Pedido: página como en el curso (sitio estático en Netlify + dominio propio), tema Día de Muertos + carreras,
y predicción del Top 10 de la qualy de México. Si la sesión se corta, retomar desde el primer paso sin marcar.

- [x] Datos de México (FP1/FP2) y temporada 2026 refrescados: `python3 descarga_datos.py gp 2026 1298 rodriguez`
- [x] Modelo de qualy parametrizado por GP (`GPS`, `main(meeting)`), titulares desde la lista de qualy (FP1 con 10 novatos)
- [x] Sitio para Netlify: `publicar_sitio.py`, `../netlify.toml`, `PUBLICAR_NETLIFY.md`, `CLAUDE.md`
- [x] Generador con tema Día de Muertos `reporte_mexico_html.py` (workflow de diseño + revisión visual)
- [x] Correr `python3 modelo_qualy_austin.py 1298` → `prediccion_qualy_mexico_2026.csv`, `resultado_qualy_mexico.pkl`
      (hecho 07:20 UTC; Random Forest 8.21/10 en validación. Falta el HTML: `python3 modelo_qualy_austin.py html mexico`)
- [x] `python3 publicar_sitio.py` → `../sitio_f1/` (index = México); revisar capturas 1280/390 px
- [x] Commit + push; entregar al usuario el HTML, la tabla del Top 10 y los pasos de Netlify/dominio
- [x] Después de la qualy (≈22:15 UTC): bajar `session_result?session_key=11400` a `cache/qualy_real_1298.json`,
      regenerar el HTML (sección resultado real vs pronóstico), republicar el sitio y reportar aciertos

## Fase 2 (pedido 14:00 UTC): página cinematográfica en vivo, compartible en Safari
Estilo AURA (foto cinematográfica, serif editorial, acento naranja) + Día de Muertos + carreras, con animaciones.
Se publica como Artifact de claude.ai (db: docs `gp/mexico2026` y `live/qualy`, contrato en el workflow wzw9vriwd)
y la misma carpeta `web_mexico/` va a Netlify (sin db → datos incrustados).
- [x] Workflow wzw9vriwd (relanzado 14:20 con menú hamburguesa y referencias AURA en scratchpad/live/referencias): `web_mexico/index.html` (página), `live_qualy.py` (colector F1 Live Timing), modelo con `--fp3` + `exportar_datos_web.py`
- [x] Publicar Artifact con capabilities `{db:{rules:[gp y live: read view, write owner]}, user:{}}`; sembrar docs con ArtifactData; dar link
- [x] 18:40 UTC: bajar FP3 (`descarga_datos.py`, borrar cache de la sesión 11399), correr modelo con FP3, actualizar `gp/mexico2026` (campo cambio), republicar sitio
- [x] 20:50 UTC: lanzar `live_qualy.py` en segundo plano y relevar `live/qualy_mexico.json` → doc `live/qualy` cada ~60-90 s hasta 22:05 UTC
- [x] 22:20 UTC: resultado final (OpenF1 11400) → `live/qualy` estado terminada, sección real vs pronóstico, republicar, reportar aciertos

Artifact publicado: https://claude.ai/artifact/A5ptCSyCPL7Eb63tt5U6zJ (file_path f1_austin/web_mexico/index.html; docs gp/mexico2026 v1 y live/qualy v1 sembrados).
Para viewers sin sesión de claude.ai la página usa los datos incrustados: además de actualizar la db, republicar el Artifact
con `python3 construir_web_mexico.py --gp web_mexico/datos_gp.json --live live/qualy_mexico.json` (sin --documento; reescribe web_mexico/index.html)
y luego Artifact publish del mismo file_path. Sitio Netlify: `python3 publicar_sitio.py`.
Comandos FP3 (del agente): `python3 descarga_datos.py 11399`; `python3 modelo_qualy_austin.py 1298 --fp3 --jobs 2`;
`python3 exportar_datos_web.py mexico_fp3 --previo resultado_qualy_mexico.pkl` (escribe web_mexico/datos_gp.json con fase FP3 y cambio).
Colector: `python3 live_qualy.py --salida live/qualy_mexico.json --minutos 80 --grabar live/crudo_qualy.jsonl` (prueba: `--cualquier-sesion --minutos 3`).

## Fase 3 (pedido 15:30 UTC): al terminar la qualy, en la MISMA página (recargando)
(1) cómo le fue al modelo en la qualy (doc `post/qualy`) y (2) pronóstico de CARRERA = orden FINAL tras degradación, ritmo y
estrategia (doc `carrera/mexico2026`). Workflow w0qyrzm9d: secciones nuevas en la página + simulador con degradación/estrategia y
pipeline de carrera parametrizado (`python3 modelo_carrera_austin.py 1298 [--penalizaciones '{...}']` → web_mexico/datos_carrera.json).
- [x] Workflow w0qyrzm9d terminado e integrado (republicar Artifact con reglas db también para `post` y `carrera`)
- [x] 22:05-22:20 UTC: qualy real → cache/qualy_real_1298.json; buscar penalizaciones de parrilla de México (prensa/FIA);
      escribir post/qualy; correr modelo de carrera; escribir carrera/mexico2026; incrustar y republicar Artifact; publicar_sitio.py; commit

### Cambio de piloto (15:55 UTC): Hirakawa (HIR, #50) reemplaza a Ocon en Haas desde FP3 (qualy y carrera incluidas)
Fuentes: Haas vía The Race / Sky / RaceFans (31/10). OpenF1 aún lista a OCO (#31) en FP3/Q/carrera.
- [x] `GPS[1298]["sustituciones"] = {"OCO": "HIR"}` + `aplicar_sustituciones()` en modelo_qualy_austin.py (base de pilotos del GP)
- [x] Pronóstico de qualy recalculado con HIR (+ prior de debutantes: HIR P18; RF 8.26/10) (corrida en curso, log corrida_mexico_hir.log) → actualizar doc gp/mexico2026 en la db
      (la republicación con datos incrustados espera a que el agente de la página termine, ~18:30)
- [x] Carrera: verificar que la parrilla (qualy_real_1298.json, #50) y el dataset de carrera usen HIR y no OCO

16:35 UTC: Artifact v2 publicado (Hirakawa, secciones post-qualy/carrera, reglas db gp/live/post/carrera; compartido "cualquiera con el link").
Docs db: gp/mexico2026 v2, live/qualy v2. Carrera: `python3 modelo_carrera_austin.py 1298 [--penalizaciones '{...}' | --parrilla '{...}']`
→ web_mexico/datos_carrera.json (degradación/paradas sólo informativas: no mejoraron la validación). Republicar siempre con:
`python3 construir_web_mexico.py --gp web_mexico/datos_gp.json --live live/qualy_mexico.json [--post live/post_qualy.json --carrera web_mexico/datos_carrera.json]`

### 17:45 UTC: prueba del colector en FP3 → el feed público NO trae TimingData (posiciones) y SessionInfo dice "Race"
Sí trae TimingStats (mejores vueltas con hora), tiempos de sector, neumáticos, pits, reloj, estado y mensajes de carrera. Workflow wn21wo97b
(hora límite 19:45): modo público en live_qualy.py que reconstruye la clasificación con las mejores vueltas por segmento
(Q1 exacta; Q2/Q3 aproximadas). Si falla, plan B: monitoreo por segmentos con el feed público sólo para Q1 y resultado oficial al final.
18:37 UTC: colector v1.1 con modo público listo (probado 50 min con la FP3 real: 20/20 idéntico a TimingData; el feed se corrigió solo
a las 17:44). Comando de la qualy (20:50 UTC, desde f1_austin/; relanzar igual si se cae):
`python3 live_qualy.py --salida live/qualy_mexico.json --minutos 80 --grabar live/crudo_qualy.jsonl --precargar live/crudo_qualy.jsonl`
18:52 UTC: OpenF1 sigue en 401 tras la FP3. FP3 reconstruida desde la grabación del live timing con `fp3_desde_live.py`
(mejor vuelta 22/22 y vueltas 22/22 validadas; sin clima) → copiada a cache/*_11399.json; corrida del modelo con --fp3 en curso
(log corrida_mexico_fp3.log). Luego: `python3 exportar_datos_web.py mexico_fp3 --previo resultado_qualy_mexico.pkl`, db gp/mexico2026
(if_version 2), construir_web_mexico.py, republicar Artifact, publicar_sitio.py.
19:06 UTC: pronóstico con FP3 publicado (RF 8.27/10; gp/mexico2026 v3; Artifact v3). Cambios: NOR 5→3, RUS 3→5, PIA 7→6, HAM 6→7,
LAW 10→9, LIN entra (10), GAS sale (9→11). Docs db: gp v3, live v2.
21:31 UTC: comisarios investigan tras la sesión a BOR, BOT, HAM, PER (máximo tiempo delta en Q1) → revisar penalizaciones de parrilla antes del pronóstico de carrera
22:08 UTC: qualy terminada (provisional): HAM RUS LEC VER ANT NOR HAD LAW LIN GAS | HUL COL PIA BOR BEA SAI | ALB ALO HIR STR PER BOT. live/qualy v48. Grabación: live/crudo_qualy.jsonl
22:20 UTC: post/qualy v1 (9/10 en Top 10, pole fallada: HAM; Q1 5/6, Q2 4/6, MAE 2.0, Spearman 0.907) y carrera/mexico2026 v2 publicados
(Artifact v16). Parrilla usada (qualy live timing, OpenF1 aún 401): HAM RUS LEC ANT VER NOR HAD LIN LAW GAS HUL COL PIA BOR BEA SAI ALB ALO
HIR STR PER BOT (VER y LAW −1 por choque en FP2; BOT al fondo por motor). Pronóstico final: HAM RUS LEC ANT VER HAD NOR LAW LIN PIA.
PENDIENTE: decisión de comisarios sobre la Q1 (HAM, BOR, BOT, PER: tiempo delta máximo). Si cambia la parrilla: correr
`python3 modelo_carrera_austin.py 1298 --parrilla '{...}'`, ajustar parrilla_fuente, db carrera/mexico2026 (if_version 2), construir_web_mexico.py
con --post/--carrera, republicar Artifact y publicar_sitio.py.
23:31 UTC: qualy oficial de OpenF1 = la del live timing (22/22 idénticas). Parrilla de Crash.net = la usada. Sin decisión publicada sobre la Q1 (HAM/BOR/BOT/PER) ni sobre el MGU-K de Lawson (GPblog): sin cambios. Revisión final programada 2026-11-01 15:30 UTC (OpenF1 starting_grid 11404 + prensa).
02:59 UTC 1/11: Lawson descalificado de la qualy (MGU-K) → sale P22 (BOT P21). Parrilla: HAM RUS LEC ANT VER NOR HAD LIN GAS HUL COL PIA BOR BEA SAI ALB ALO HIR STR PER BOT LAW. post/qualy v2 (oficial 8/10; en pista 9/10), carrera v3, Artifact v17. Pronóstico: HAM RUS LEC ANT VER HAD NOR LIN PIA GAS (LAW ~P12).

## Fase 4 (pedido 03:00 UTC 1/11): resultado final de la carrera vuelta a vuelta (rebases, undercut/overcut, estrategias)
Workflow w6x89rhce: `sim_vueltas.py` (simulador vuelta a vuelta calibrado con 88 carreras; validación walk-forward vs simulador actual
0.8898) → web_mexico/datos_vueltas.json (doc "carrera/vueltas"); sección "La carrera, vuelta a vuelta" en la página
(construir_web_mexico.py --vueltas); verificación adversarial (hora límite 13:00 UTC).
- [x] Integrar: elegir orden final (sim vuelta a vuelta si valida ≥ actual; si no, el actual), db carrera/vueltas (+ carrera/mexico2026
      si cambia, if_version 3), construir_web_mexico.py con --post --carrera --vueltas, republicar Artifact, publicar_sitio.py, commit
- [ ] 15:30 UTC: revisión final de parrilla (programada)
05:10 UTC: simulador vuelta a vuelta integrado (Artifact v18; db carrera/vueltas v1). Orden final oficial = simulador actual
(vuelta a vuelta anclado 0.8866 vs 0.8898, Wilcoxon p=0.015 a favor del actual); vuelta a vuelta aporta estrategias (1 parada 58%, M-H
~v28, pit 22.9 s), duelos (undercut RUS→HAM v25 48%), rebases (~54), SC/VSC 71%, trazas. Regenerar: `python3 sim_vueltas.py mexico --sims 6000`
(si cambia la parrilla: primero modelo_carrera_austin.py --parrilla, luego sim_vueltas.py, luego construir_web_mexico.py con --vueltas).
15:31 UTC 1/11: revisión final sin cambios (parrilla igual: LAW P22; sin salidas desde pit lane reportadas; pronóstico seco ~26-27 °C, consistente con el modelo). OpenF1 starting_grid aún 404.
