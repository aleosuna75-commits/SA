# Estado: pronósticos automáticos para todos los GP (pedido 9/11/2026)

Pedido: hacer Brasil (ya corrido el 6-8/11: se hace en retrospectiva, cada paso sólo con datos previos a su sesión) y que todo se
actualice solo para los GP restantes: Las Vegas (1300), Qatar (1301), Abu Dhabi (1302). Una sola URL (Artifact
https://claude.ai/artifact/A5ptCSyCPL7Eb63tt5U6zJ) que muestre el GP en curso + archivo; temas por GP.

- [ ] Workflow wngpp26f1 (hora límite 05:30 UTC): gp_pipeline.py (auto/retro/pasos, gps/<slug>/, meta.json, post_carrera nuevo)
      + web/plantilla.html + temas + construir_web.py + publicar_sitio.py multi-GP
- [ ] Verificación adversarial (sin fugas en retro, evaluaciones correctas, página por tema)
- [ ] Publicar: Artifact con reglas db para gp, live, postqualy, carrera, vueltas, postcarrera, meta; sembrar docs de mexico2026 y
      brasil2026 y meta/actual; sitio Netlify; commit
- [ ] Tareas programadas por sesión para 1300/1301/1302 (tras FP2, tras FP3, qualy−12 min en vivo, post-qualy, post-carrera)
