# Página de Cerebro Liga MX

Página de una sola pieza («noche de partido») que muestra lo que escribe el modelo en
`salidas/actual.json` (contrato en `salidas/CONTRATO.md`) y, en vivo, el documento `vivo/actual` de
la base de datos del Artifact (forma en `salidas/vivo_ejemplo.json`). El JavaScript no calcula
probabilidades: sólo da formato a lo que viene en esos dos JSON.

## Reconstruir (después de cada partido)

    cd /home/user/SA/ligamx
    python3 -m produccion.exportar        # rehace salidas/actual.json
    python3 web/construir.py              # rehace web/index.html, archivos_publicados.json y capacidades.json

`construir.py` tarda menos de 1 s, sólo usa la biblioteca estándar y escribe a un temporal que luego
renombra. Si a `actual.json` le falta un campo obligatorio termina con código 1, lista lo que falta y
NO toca `index.html`. Los avisos no fatales (equipo sin escudo, sede sin fotos, `liguilla.torneo`
ausente) salen por stderr y la página los resuelve sola.

Opciones:

- `--datos RUTA`: otro JSON con el mismo contrato (por ejemplo una corrida de `salidas/historial/`).
- `--documento`: además genera un documento completo (`<!doctype>`, `<head>`, `<body>`) en
  `web/sitio/` y copia ahí los `img/` y `video/` que la página usa.
- `--documento --salida DIR`: lo mismo en otro directorio. Si `DIR` es la propia carpeta `web/`, sólo
  escribe `web/documento.html` (es lo que usan las pruebas; sirve para abrirla con doble clic).
- `--vivo RUTA` (de prueba): incrusta ese documento en vivo como `datos.vivo`.
- `--portada EQUIPO` (de prueba): fuerza el equipo de la portada, para revisar las 16.

Las dos opciones de prueba NO tocan `index.html` ni `archivos_publicados.json`: sólo escriben el
documento (`web/documento.html` si no se da `--salida`). Sin ellas, `index.html` incrusta
`actual.json → vivo` cuando existe.

## Qué se publica

- `web/index.html`: FRAGMENTO para el Artifact de claude.ai (sin `<!doctype>`, `<html>`, `<head>` ni
  `<body>`; la plataforma lo envuelve). Lleva incrustados `actual.json` y un `medios.json` recortado.
- Los archivos listados en `web/archivos_publicados.json`, con la MISMA ruta relativa (`img/...`,
  `video/...`). La portada ya no usa video: usa la foto del estadio del favorito.
- **Capacidad `db`**: al publicar hay que declarar `capabilities` con el contenido de
  `web/capacidades.json` (`{"db": {"rules": [{"path": "", "read": "view", "write": "admin"}]}}`:
  cualquiera con acceso lee, sólo el dueño y los editores escriben). Sin esa declaración
  `claude.use("db")` da `null` y la página se queda con el «vivo» incrustado.

No se publican: `plantilla.html`, `construir.py`, `medios.json`, `documento.html`, `capacidades.json`,
`pruebas/`.

## En vivo

El motor escribe el documento en la ruta **`vivo/actual`** de la base del Artifact cada vez que pasa
algo (inicio, gol, expulsión, descanso, final). La página:

- pide la base con `claude.use("db")` después del primer pintado (nunca lo bloquea) y abre UNA sola
  suscripción `db.doc("vivo/actual").onSnapshot(...)`; nunca recarga la página;
- «conectando» tiene límite de 10 s; después dice «Sin conexión en vivo por ahora: datos de las HH:MM»
  y sigue esperando en silencio;
- sin base (visitante sin sesión, vista previa, `use` → `null`) usa `datos.vivo` incrustado si tiene
  menos de 12 h, con el reloj detenido, y dice «Sin conexión en vivo: datos de las HH:MM»;
- con partidos en juego o en descanso muestra la franja fija «EN VIVO» bajo la barra (escudos,
  marcador en tablero y minuto que avanza solo a partir de `reloj_utc`, sin pasar del tope del
  periodo); al tocar un partido lleva a su tarjeta;
- en la tarjeta del partido: marcador, línea de eventos y probabilidad al momento contra el pronóstico
  previo; al terminar, resultado final y si el pronóstico acertó;
- sección «Al momento» (sólo aparece si el documento trae partidos de hoy): marcadores del día, tabla
  al momento con flechas y equipos en juego, probabilidad de clasificar y de campeón con su cambio;
- en liguilla, el cuadro muestra el global y la probabilidad de avanzar al momento de cada serie de
  `series` con `al_momento` distinto de `false`;
- un evento nuevo (`ultimo_evento` distinto al anterior) sale como aviso breve (visible y en
  `aria-live`) y el dígito del marcador que cambió destella;
- un documento raro (`{}`, `null`, campos en `null`) se ignora sin romper nada; un «en juego» con más
  de 3 h sin actualizar se marca como atrasado y se retira la franja; un documento con `ejemplo: true`
  se rotula «datos de ejemplo».

## Archivos

| archivo | qué es |
|---|---|
| `plantilla.html` | todo el HTML, CSS y JS. Marcas que llena `construir.py`: `{{DATOS}}`, `{{MEDIOS}}`, `{{PORTADA_FONDO}}`, `{{PORTADA_TONO}}`, `{{PORTADA_LADO}}`, `{{PORTADA_CREDITO}}` |
| `construir.py` | valida, recorta `medios.json`, arma `index.html`, `archivos_publicados.json` y `capacidades.json`. `ESCENAS` dice qué foto o video va en cada banda; `PORTADAS` y `PORTADAS_CAMPEON`, la foto de portada por estadio y su encuadre |
| `index.html` | resultado (no se edita a mano) |
| `archivos_publicados.json` | rutas relativas exactas de los medios que la página usa |
| `capacidades.json` | lo que hay que pasar como `capabilities` al publicar |
| `pruebas/prueba.js` | pruebas con Playwright |

## Cómo está hecha

- Un solo aspecto oscuro; todos los colores son tokens en `:root` (la prueba falla si aparece un color
  literal fuera de ahí). Tipografías de Google Fonts con pila de respaldo; ningún script externo.
- Cada bloque se dibuja aislado con `seguro(nombre, destino, fn)`: si un dato viene raro, ese bloque
  muestra un texto de respaldo, el error queda en la consola y el resto de la página sigue.
- **Portada**: cambia sola con el favorito al título (`proyeccion.campeon[0]`). Fondo = foto libre de
  su festejo de campeón si existe (`medios.json → campeon`; hoy Toluca y Pumas) o la foto elegida a mano
  de su estadio (`PORTADAS`: encuadre vertical y horizontal, lado del texto, acercamiento y tono; las de
  día se oscurecen y se enfrían). Movimiento lento tipo Ken Burns en CSS, trofeo dibujado en SVG (copa
  genérica, no el trofeo oficial) con el escudo del favorito, confeti en los colores del club en un
  `<canvas>` (en pausa fuera de pantalla; una imagen fija con movimiento reducido), su último título
  (`proyeccion.titulos`) y el crédito de la foto en texto corrido, sin encimar nada.
- **Liguilla** (`liguilla.torneo`): cuadro de eliminatoria con líneas de cal. En celular y tableta vive
  en un contenedor con desplazamiento horizontal y `scroll-snap` por ronda (botones de ronda e indicador
  «Desliza el cuadro»); desde 1160 px es un cuadro en espejo que cabe en una pantalla: cuartos a los
  lados, semifinales, y la final al centro con el campeón encima. Cada serie muestra sembrados, barra de
  avance, ida y vuelta (sede, fecha, marcador en tablero, 1X2 chico) y el global más probable. Tocar una
  serie abre su detalle debajo: los 5 marcadores de cada partido, los globales y los cruces alternativos.
  Tablero dorado = pronóstico; tablero blanco = resultado real. Si falta `liguilla.torneo` sale un aviso.
- Completa en reposo: las animaciones parten de un estado visible; con `prefers-reduced-motion` no hay
  animaciones ni autoplay.
- Navegación interna con `scrollIntoView` (no se usa `location.hash`, `history` ni `localStorage`).
- Los videos de las bandas no se descargan hasta que entran en pantalla (`preload="none"`).

## Probar

Chromium y WebKit, en iPhone 13 y en escritorio 1440x900 (abre `web/documento.html` con `file://`):

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium
    PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit
    # con --capturas guarda PNG en web/pruebas/capturas/ (ignoradas por git)

Revisa (157 comprobaciones por motor): fragmento válido y contrato de la plataforma, sin colores
literales, portada (foto, Ken Burns, trofeo, confeti, nada encimado), el cuadro (4 + 2 + 1 series con
ida y vuelta, el cuadro se desplaza de lado y el cuerpo no, botones de ronda, detalle), menú coherente
con las secciones, pestañas, imágenes, textos sin `undefined`/`NaN`/`null`, y el vivo con un
`window.claude` simulado (franja, minuto que avanza con el reloj de Playwright, gol nuevo con aviso,
tabla al momento, documentos corruptos, límite de 10 s, `use` → `null`, «vivo» incrustado), más las
variantes de liguilla en curso, sin `liguilla.torneo`, opcionales en `null` y movimiento reducido. Sale
con código 1 si algo falla. Tarda unos 2 minutos por motor. Si la máquina no tiene salida a internet las
fuentes de Google no cargan y se prueba con la pila de respaldo.
