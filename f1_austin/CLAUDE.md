# Pronósticos F1 (qualy y carrera)

Modelos de predicción por GP con datos de OpenF1 (2023+) y Jolpica (2018+), y reportes HTML temáticos publicados como sitio estático.

## Flujo para un GP nuevo
1. Agregar el GP a `GPS` en `modelo_qualy_austin.py` (meeting_key de OpenF1, slug, textos, `circuito_jolpica`, `tema`).
2. Datos: `python3 descarga_datos.py gp <año> <meeting_key> <circuito_jolpica>` (refresca la temporada en curso; borra la cache
   de las sesiones del GP para no quedarse con respuestas vacías de sesiones futuras).
3. Qualy: `python3 modelo_qualy_austin.py <meeting_key>` → `reporte_qualy_<slug>_2026.html`, `prediccion_qualy_<slug>_2026.csv`
   y `resultado_qualy_<slug>.pkl` (regenerar sólo el HTML: `python3 modelo_qualy_austin.py html <slug>`).
4. Sitio: añadir el GP a `PAGINAS` en `publicar_sitio.py` (el primero es la portada) y correr `python3 publicar_sitio.py`.
   Publicación y dominio propio: `PUBLICAR_NETLIFY.md`.

## Flujo automático multi-GP (desde Brasil 2026): `gp_pipeline.py`
- `python3 gp_pipeline.py auto` decide por hora UTC y `gps/<slug>/estado.json` qué paso toca (post_fp1 tras FP1, pre_qualy
  tras FP2, fp3 tras FP3, qualy_en_vivo = comando del colector, post_qualy, post_carrera, mejora), lo corre y escribe `gps/ultimo_auto.json` con los docs a publicar.
- `python3 gp_pipeline.py retro <meeting>` reproduce un GP ya corrido; `paso <paso> <meeting> [--forzar]` corre uno suelto.
- Config automática desde OpenF1/Jolpica en `gps/<slug>/config.json` (los GPs nuevos se agregan solos a `GPS`; 1297/1298 fijos).
  Sustituciones, parrilla o penalizaciones y fuentes: `gps/<slug>/ajustes.json` (a mano; post_qualy se repite si cambia).
- Sin fugas: los modelos reciben `F1_CORTE` (inicio de la sesión siguiente) y ocultan resultados/pilotos/vueltas posteriores.
- OpenF1 en 401 (sesión en vivo): `descarga_datos.py gp` no toca la cache (comprueba antes y aparta en vez de borrar;
  restaura si falla a medias) y `auto` devuelve `reintentar` (paso, error, `reintentar_utc` = +30 min hasta la sesión
  que corta el paso): reprogramar `auto` a esa hora. La FP3 sólo tiene respaldo si el colector se lanzó (corrida de
  `auto` en FP3−12 min). meta.json nunca se reescribe vacío. meta/página: sólo GPs desde México (1308 = GP de Baréin
  corrido en Sepang, antes de México: no va).
- Archivos → docs del Artifact: gp.json→gp/<slug>, live_qualy.json→live/<slug>, post_qualy.json→postqualy/<slug>,
  carrera.json→carrera/<slug>, vueltas.json→vueltas/<slug>, post_carrera.json→postcarrera/<slug>, gps/meta.json→meta/actual,
  historial.json→historial/<slug>, modelos/bitacora.json→bitacora/actual.
- Por fase: `post_fp1` (tras FP1, `modelo_qualy_austin.py <mk> --fp1`: sólo FP1 + historial; titulares = lista del GP
  anterior porque la FP1 trae novatos) y en post_fp1/pre_qualy/fp3 una carrera PRELIMINAR (`modelo_carrera_austin.py
  --parrilla <orden de qualy pronosticado> --sin-qualy`; carrera.json con `preliminar: true`, también carrera_<fase>.json);
  post_qualy la reemplaza con la parrilla real. Cada fase se agrega a `historial.json` con los cambios vs la anterior.
  `gp_pipeline.py historial <mk>` rellena un GP ya corrido (México y Brasil hechos).

## Mejora continua: `mejora_modelos.py` (campeón/retador)
- `gp_pipeline.py auto` corre el paso `mejora` tras post_carrera (una vez por GP): `mejora_modelos.py ciclo` re-evalúa con
  walk-forward (2024→hoy) al campeón y a los retadores de qualy_fp1/fp2/fp3 y carrera (cache por componente y GP en
  modelos/cache/: sólo recalcula lo que cambió) y adopta un retador SÓLO si mejora la métrica principal (qualy top10_hits,
  carrera NDCG@10) > z_crit EE en todos los GP (z_crit = max(2, Bonferroni unilateral 10 % sobre los k retadores: 2,33 con
  10), no empeora en los últimos 8 y lo confirma el promedio de 3 semillas (campeón prod+1,2; retador prod+3,4; en carrera
  el EE suma el ruido de semilla del Monte Carlo, que es común a todos los GP). Con "> 1 EE" se adoptaban retadores
  idénticos al campeón con otra semilla (verificación 9/11: 7/30 en qualy, 4/12 en carrera). Presupuesto: `--presupuesto-min`
  (en auto `F1_PRESUPUESTO_MEJORA`, default 40). En `auto` el paso mejora corre al FINAL (después de los pasos de
  cualquier GP en curso); `F1_SIN_MEJORA=1 python3 gp_pipeline.py auto` lo salta (RB-6 rápido; el ciclo va en RB-7).
- Los modelos NO se editan para cambiar de variante: leen `modelos/config_activa.json` (config_modelos.py) con historial
  `desde`; un GP en retro usa la variante vigente en su F1_CORTE (sin fugas). Sin archivo = comportamiento original.
- Proponer variantes: `python3 mejora_modelos.py agregar-candidato '<json>'` (claves en el docstring); quedan como
  retadores y nunca se adoptan sin pasar la regla. Estado: `mejora_modelos.py estado`; bitácora: modelos/bitacora.json.
- Elegir entre muchos retadores mirando el mismo walk-forward sesga a favor del elegido: la regla lo limita, no lo elimina.

## Reglas aprendidas (no romper)
- El historial se corta por el INICIO del fin de semana (FP1), nunca por fecha de carrera entre fuentes (fuga en Las Vegas 2024).
- Variables por equipo que usan resultados (p. ej. `h_fp_to_q_team`) se calculan por GP, no por fila.
- Pilotos titulares del GP objetivo: lista de la qualy/FP3/FP2, no la de FP1 (en México y otros GPs la FP1 tiene novatos).
- Validación: walk-forward (cada GP sólo con GPs anteriores); comparar siempre contra baselines (orden de FP / qualy / parrilla).
- Elegir hiperparámetros o variantes mirando el mismo walk-forward sesga el resultado: decirlo cuando se haga.
- Carrera: el pronóstico oficial es el simulador Monte Carlo (`sim_carrera.py`), no el orden de qualy.
- Página (web/plantilla.html): dentro del visor de Claude (iframe) no se toca `location.hash`; el telón de cambio de GP se quita
  siempre (finally + temporizador + animación CSS) y cada render va aislado con `seguro()` (en iPhone se quedaba trabado en Las Vegas).
  Probar cambios de GP también en WebKit, no sólo en Chromium.
- Temas visuales: `reporte_html.py` (Texas), `reporte_carrera_html.py` (Texas carrera), `reporte_mexico_html.py` (Día de Muertos).
