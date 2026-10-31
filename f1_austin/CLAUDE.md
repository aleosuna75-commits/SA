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

## Reglas aprendidas (no romper)
- El historial se corta por el INICIO del fin de semana (FP1), nunca por fecha de carrera entre fuentes (fuga en Las Vegas 2024).
- Variables por equipo que usan resultados (p. ej. `h_fp_to_q_team`) se calculan por GP, no por fila.
- Pilotos titulares del GP objetivo: lista de la qualy/FP3/FP2, no la de FP1 (en México y otros GPs la FP1 tiene novatos).
- Validación: walk-forward (cada GP sólo con GPs anteriores); comparar siempre contra baselines (orden de FP / qualy / parrilla).
- Elegir hiperparámetros o variantes mirando el mismo walk-forward sesga el resultado: decirlo cuando se haga.
- Carrera: el pronóstico oficial es el simulador Monte Carlo (`sim_carrera.py`), no el orden de qualy.
- Temas visuales: `reporte_html.py` (Texas), `reporte_carrera_html.py` (Texas carrera), `reporte_mexico_html.py` (Día de Muertos).
