# Mercado · inteligencia de valor de futbolistas

- `pipeline.py` baja dos bases abiertas derivadas de Transfermarkt (dcaribou/transfermarkt-datasets y
  salimt/football-datasets), las une, ajusta el modelo, corre la prueba retrospectiva y escribe
  `web/datos/`. Requiere `pandas`, `numpy` y `git`. Tarda ~2 minutos.
- `web/` es el sitio estático: mapa, radar, explorador, ficha de jugador, club, lista de seguimiento
  y metodología. Netlify lo copia a `/mercado/`.
- En local: `cd mercado/web && python3 -m http.server` y abrir http://localhost:8000

`web/datos/det/` son 256 archivos con el detalle por jugador (historia de valor, fichajes, lesiones,
precedentes); la página pide sólo el que necesita. Pesan ~30 MB en total y se regeneran completos en
cada corrida.

El modelo, su prueba retrospectiva y sus límites están en la pestaña Metodología del propio sitio.
