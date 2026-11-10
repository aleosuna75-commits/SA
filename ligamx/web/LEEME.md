# Página de Cerebro Liga MX

Página de una sola pieza («noche de partido») que muestra lo que escribe el modelo en
`salidas/actual.json` (contrato en `salidas/CONTRATO.md`). El JavaScript no calcula probabilidades:
sólo da formato a lo que viene en el JSON.

## Reconstruir (después de cada partido)

    cd /home/user/SA/ligamx
    python3 -m produccion.exportar        # rehace salidas/actual.json
    python3 web/construir.py              # rehace web/index.html y web/archivos_publicados.json

`construir.py` tarda menos de 1 s, sólo usa la biblioteca estándar y escribe a un temporal que luego
renombra. Si a `actual.json` le falta un campo obligatorio termina con código 1, lista lo que falta y
NO toca `index.html`. Los avisos no fatales (equipo sin escudo, sede sin fotos) salen por stderr y la
página los resuelve sola (iniciales en lugar de escudo, tarjeta sin foto).

Opciones:

- `--datos RUTA`: otro JSON con el mismo contrato (por ejemplo una corrida de `salidas/historial/`).
- `--documento`: además genera un documento completo (`<!doctype>`, `<head>`, `<body>`) en
  `web/sitio/` y copia ahí los `img/` y `video/` que la página usa: un sitio estático listo para
  cualquier servidor.
- `--documento --salida DIR`: lo mismo en otro directorio. Si `DIR` es la propia carpeta `web/`, sólo
  escribe `web/documento.html` junto a los medios, sin copiar nada (es lo que usan las pruebas y sirve
  para abrir la página en el navegador con doble clic).

## Qué se publica

- `web/index.html`: FRAGMENTO para el Artifact de claude.ai (sin `<!doctype>`, `<html>`, `<head>` ni
  `<body>`; la plataforma lo envuelve). Lleva incrustados `actual.json` y un `medios.json` recortado.
- Los archivos listados en `web/archivos_publicados.json` (hoy 69: fotos de estadios y de ambiente,
  escudos, 4 videos y sus pósters; 21 MB), con la MISMA ruta relativa (`img/...`, `video/...`).

No se publican: `plantilla.html`, `construir.py`, `medios.json`, `documento.html`, `pruebas/`.

## Archivos

| archivo | qué es |
|---|---|
| `plantilla.html` | todo el HTML, CSS y JS. Marcas que llena `construir.py`: `{{DATOS}}`, `{{MEDIOS}}`, `{{PORTADA_VIDEO}}`, `{{PORTADA_POSTER}}`, `{{PORTADA_CREDITO}}` |
| `construir.py` | valida, recorta `medios.json`, arma `index.html` y `archivos_publicados.json`. La tabla `ESCENAS` dice qué foto o video va de fondo en cada banda |
| `index.html` | resultado (no se edita a mano) |
| `archivos_publicados.json` | rutas relativas exactas de los medios que la página usa |
| `pruebas/prueba.js` | pruebas con Playwright |

## Cómo está hecha

- Un solo aspecto oscuro; todos los colores son tokens en `:root` (la prueba falla si aparece un color
  literal fuera de ahí). Tipografías de Google Fonts con pila de respaldo; ningún script externo.
- Cada bloque se dibuja aislado con `seguro(nombre, destino, fn)`: si un dato viene raro, ese bloque
  muestra un texto de respaldo, el error queda en la consola y el resto de la página sigue. No hay
  cortinas ni estados que dependan de que termine un script.
- Completa en reposo: las animaciones de entrada parten de un estado visible; con
  `prefers-reduced-motion` no hay animaciones ni autoplay (queda el póster).
- Navegación interna con `scrollIntoView` (no se usa `location.hash`, `history` ni `localStorage`).
- Cuando `liguilla.en_curso` sea `true`, «Camino al título» abre con el cuadro real (serie por serie)
  y los partidos de liguilla forman su propio grupo en «Próximos partidos»; no hay que tocar nada.
- Los videos fuera de la portada no se descargan hasta que entran en pantalla (`preload="none"`).

## Probar

Chromium y WebKit, en iPhone 13 y en escritorio 1440x900 (abre `web/documento.html` con `file://`):

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium
    PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit
    # con --capturas guarda PNG en web/pruebas/capturas/ (ignoradas por git)

Revisa: fragmento válido, sin colores literales, sin errores de consola, sin desplazamiento
horizontal, una tarjeta por partido pendiente, pestañas de la combinada, menú (abre, Escape, botón,
elegir sección), imágenes sin romper, texto sin `undefined`/`NaN`/`null`, video de portada, movimiento
reducido y una variante con la liguilla en curso y datos opcionales en `null`. Sale con código 1 si
algo falla. Si la máquina no tiene salida a internet las fuentes de Google no cargan y se prueba con
la pila de respaldo.
