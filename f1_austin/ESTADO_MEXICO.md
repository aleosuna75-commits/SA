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
- [ ] Después de la qualy (≈22:15 UTC): bajar `session_result?session_key=11400` a `cache/qualy_real_1298.json`,
      regenerar el HTML (sección resultado real vs pronóstico), republicar el sitio y reportar aciertos

## Fase 2 (pedido 14:00 UTC): página cinematográfica en vivo, compartible en Safari
Estilo AURA (foto cinematográfica, serif editorial, acento naranja) + Día de Muertos + carreras, con animaciones.
Se publica como Artifact de claude.ai (db: docs `gp/mexico2026` y `live/qualy`, contrato en el workflow wzw9vriwd)
y la misma carpeta `web_mexico/` va a Netlify (sin db → datos incrustados).
- [x] Workflow wzw9vriwd (relanzado 14:20 con menú hamburguesa y referencias AURA en scratchpad/live/referencias): `web_mexico/index.html` (página), `live_qualy.py` (colector F1 Live Timing), modelo con `--fp3` + `exportar_datos_web.py`
- [x] Publicar Artifact con capabilities `{db:{rules:[gp y live: read view, write owner]}, user:{}}`; sembrar docs con ArtifactData; dar link
- [ ] 18:40 UTC: bajar FP3 (`descarga_datos.py`, borrar cache de la sesión 11399), correr modelo con FP3, actualizar `gp/mexico2026` (campo cambio), republicar sitio
- [ ] 20:50 UTC: lanzar `live_qualy.py` en segundo plano y relevar `live/qualy_mexico.json` → doc `live/qualy` cada ~60-90 s hasta 22:05 UTC
- [ ] 22:20 UTC: resultado final (OpenF1 11400) → `live/qualy` estado terminada, sección real vs pronóstico, republicar, reportar aciertos

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
- [ ] Workflow w0qyrzm9d terminado e integrado (republicar Artifact con reglas db también para `post` y `carrera`)
- [ ] 22:05-22:20 UTC: qualy real → cache/qualy_real_1298.json; buscar penalizaciones de parrilla de México (prensa/FIA);
      escribir post/qualy; correr modelo de carrera; escribir carrera/mexico2026; incrustar y republicar Artifact; publicar_sitio.py; commit
