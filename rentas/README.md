# Busca Nido

Mapa de rentas de la Ciudad de México, publicado como artefacto de Claude.

## Qué hay aquí

| Ruta | Para qué |
|---|---|
| `src/app.html` | La app (HTML, CSS y JS). |
| `src/plataformas.js` | Portales y cómo abrir su búsqueda con los filtros elegidos. |
| `src/iconos.json` | Íconos de OpenMoji (CC BY-SA 4.0) usados en la interfaz. |
| `src/maplibre-4.7.1.css` | Estilos de MapLibre GL (el JS se carga de cdnjs). |
| `construir.py` | Une todo en `publicar/index.html` y copia los datos. |
| `datos/mapa.py` | Descarga el mapa base de la CDMX de OpenFreeMap (datos de OpenStreetMap) y lo empaca en `t/*.json`. |
| `datos/alcaldias.py` | Límites de las 16 alcaldías (Nominatim). |
| `datos/ubicar.py` | Convierte los anuncios verificados en `datos/publicar/anuncios.json` y les pone ubicación. |
| `datos/publicar/` | Datos que se publican: `anuncios.json` y `lugares.json` (alcaldías, colonias y estaciones). |

## Cómo funciona el mapa sin servicios externos

El artefacto no puede pedir nada a otros sitios, así que el mapa viaja con él:
las teselas vectoriales de la CDMX (zoom 0 a 14) van en paquetes JSON (`t/`), las letras en `f/`,
los íconos del mapa en `s/` y el estilo en `map/style.json`. MapLibre los lee con protocolos propios
(`pack://` y `glyph://`). El estilo es *Liberty* de OpenFreeMap con etiquetas en español.

Para volver a generar el mapa: `python3 datos/mapa.py <carpeta>` (tarda un par de minutos).
Los paquetes no se guardan en git porque pesan unos 50 MB; el artefacto ya los tiene y al republicar
solo hace falta mandar lo que cambió.

## Datos de anuncios

Los anuncios se buscan con el buscador web y cada uno lo confirma un segundo agente. Los portales
y Facebook bloquean la lectura automática de sus páginas, así que no se copian fotos ni teléfonos:
cada anuncio lleva a su publicación original. Los pines están en el centro de la colonia
(o en la calle, si el anuncio la da).

Lo que la pareja agrega con **＋ Agregar** se guarda en la base del artefacto (colección `mios`),
con sus fotos en el almacén de archivos. Favoritos, avance y notas van en la colección `estado`.
