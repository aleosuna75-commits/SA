# Mercado · inteligencia de valor de futbolistas

## Qué hay aquí
- `pipeline.py` baja dos bases abiertas derivadas de Transfermarkt (dcaribou/transfermarkt-datasets y
  salimt/football-datasets), las une, entrena, corre la prueba retrospectiva y escribe `web/datos/`.
- `modelo.py` es el modelo de precisión: gradient boosting por cuantiles (LightGBM) sobre ~40
  variables por jugador-año, más la prueba retrospectiva de origen móvil y la calibración de bandas.
- `web/` es el sitio estático: mapa, radar, explorador, club, ficha de jugador, lista y metodología.
  Netlify lo copia a `/mercado/`.

## Cómo correrlo
    pip install pandas numpy lightgbm
    python3 mercado/pipeline.py                 # ~15 min: descarga, prueba retrospectiva, entrenamiento, exportación
    python3 mercado/pipeline.py --sin-descarga --sin-retro   # ~4 min: reutiliza datos crudos y la última prueba
    cd mercado/web && python3 -m http.server    # http://localhost:8000

## Decisiones de fondo (y por qué)
- **Valor real, no nominal.** Todo se entrena descontando un índice del mercado (500 jugadores más
  caros de cada año). La inflación futura es un supuesto aparte: la regla que menos falló al
  pronosticar el índice fue "la mitad del ritmo de los 10 años previos".
- **Modelos directos por horizonte y por cuantil** (1, 3, 5 y 8 años; p10, p50, p90), no una
  cadena año a año: los errores no se componen y cada banda se calibra contra el pasado.
- **Sesgo de selección.** La fuente A sólo incluye a un jugador si alguna vez llegó a una liga
  cubierta; sus fotos anteriores a esa entrada se excluyen de entrenamiento y evaluación.
- **Bandas calibradas fuera de muestra.** Se ensanchan con el error de la prueba retrospectiva; la
  cobertura que se publica deja fuera el año que evalúa.
- **Lo que se probó y no mejoró:** modelos más grandes o más chicos, identidad del club como
  variable, nacionalidad, fechas de debut en selección (la fuente no las trae). El techo lo ponen
  los datos públicos.

## Peso de los datos
`web/datos/det/` son 256 archivos con el detalle por jugador (historia, curvas, fichajes, lesiones,
precedentes); la página pide sólo el que necesita. Pesan ~40 MB y se regeneran completos en cada corrida.
