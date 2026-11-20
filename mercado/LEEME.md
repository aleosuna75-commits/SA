# Mercado · proyección del valor de futbolistas

- `pipeline.py` baja los datos abiertos (transfermarkt-datasets, CC0), ajusta el modelo, corre el
  backtest y escribe `web/datos/*.json`. Requiere `pandas` y `numpy`. Tarda ~1 minuto.
- `web/` es el sitio estático (mapa, buscador, filtros, ficha de jugador). Netlify lo copia a `/mercado/`.
- Para verlo en local: `cd mercado/web && python3 -m http.server` y abrir http://localhost:8000

Alcance real de la v0: primera división de 31 ligas, ~15.7 mil jugadores. El modelo sólo usa
posición, edad y valor actual; los límites y el backtest se publican en la propia página.
