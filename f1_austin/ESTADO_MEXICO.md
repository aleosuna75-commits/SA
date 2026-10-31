# Estado: GP de México 2026 (qualy sábado 31/10, 21:00 UTC)

Pedido: página como en el curso (sitio estático en Netlify + dominio propio), tema Día de Muertos + carreras,
y predicción del Top 10 de la qualy de México. Si la sesión se corta, retomar desde el primer paso sin marcar.

- [x] Datos de México (FP1/FP2) y temporada 2026 refrescados: `python3 descarga_datos.py gp 2026 1298 rodriguez`
- [x] Modelo de qualy parametrizado por GP (`GPS`, `main(meeting)`), titulares desde la lista de qualy (FP1 con 10 novatos)
- [x] Sitio para Netlify: `publicar_sitio.py`, `../netlify.toml`, `PUBLICAR_NETLIFY.md`, `CLAUDE.md`
- [ ] Generador con tema Día de Muertos `reporte_mexico_html.py` (workflow de diseño + revisión visual)
- [x] Correr `python3 modelo_qualy_austin.py 1298` → `prediccion_qualy_mexico_2026.csv`, `resultado_qualy_mexico.pkl`
      (hecho 07:20 UTC; Random Forest 8.21/10 en validación. Falta el HTML: `python3 modelo_qualy_austin.py html mexico`)
- [ ] `python3 publicar_sitio.py` → `../sitio_f1/` (index = México); revisar capturas 1280/390 px
- [ ] Commit + push; entregar al usuario el HTML, la tabla del Top 10 y los pasos de Netlify/dominio
- [ ] Después de la qualy (≈22:15 UTC): bajar `session_result?session_key=11400` a `cache/qualy_real_1298.json`,
      regenerar el HTML (sección resultado real vs pronóstico), republicar el sitio y reportar aciertos
