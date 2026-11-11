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
  `web/capacidades.json` (`{"db": {"rules": [{"path": "vivo", "read": "view", "write": "admin"}]}, "user": {}}`:
  cualquiera con acceso lee, sólo el dueño y los editores escriben). Sin esa declaración
  `claude.use("db")` da `null` y la página se queda con el «vivo» incrustado.

No se publican: `plantilla.html`, `construir.py`, `medios.json`, `documento.html`, `capacidades.json`,
`pruebas/`.

## En vivo

El motor escribe el documento en la ruta **`vivo/actual`** de la base del Artifact cada vez que pasa
algo (inicio, gol, expulsión, descanso, final). La página:

- pide la base con `claude.use("db")` después del primer pintado (nunca lo bloquea) y mantiene UNA sola
  suscripción `db.doc("vivo/actual").onSnapshot(...)`; nunca recarga la página. Si el oyente muere con un
  error (`unavailable` o desconocido) abre otra a los 5, 15 y 60 s (siempre una sola viva); con un error
  definitivo (`revoked`, `not_granted`, `invalid_argument`, `permission_denied`) no reintenta;
- «conectando» tiene límite de 10 s; después dice «Sin conexión en vivo por ahora: datos de las HH:MM h
  (centro de México)» y sigue esperando en silencio. Las horas de la capa en vivo llevan la zona y, si el
  dato no es de hoy, la fecha («datos del 10 nov, 20:56 h»);
- sin base (visitante sin sesión, vista previa, `use` → `null`) usa `datos.vivo` incrustado si tiene
  menos de 12 h, con el reloj detenido, y dice «Sin conexión en vivo: datos de las HH:MM»;
- nunca va hacia atrás: un documento con `generado_utc` anterior al que ya se muestra se ignora (foto
  atrasada, o base más vieja que el «vivo» incrustado);
- **caducidad**: con algo en juego el documento vale hasta `vence_utc` (lo pone el motor; sin el campo,
  40 min). Si el flujo se corta, al pasar esa hora la página deja de decir «en vivo» sola: retira la
  franja, quita el pulso, detiene el reloj en el minuto recibido y pone «Sin actualizar desde las HH:MM h».
  Mientras el dato siga vigente el minuto corre aunque la conexión se caiga (no retrocede);
- al repintar no mueve lo que se está leyendo: toma de ancla el elemento a media pantalla y compensa el
  desplazamiento si lo de arriba creció («Al momento», el bloque en vivo de una tarjeta); un bloque cuyo
  contenido no cambió no se vuelve a pintar;
- un documento con `prueba: true` (de `vivo.py repetir`) se rotula «Prueba» en la franja, la sección, la
  tarjeta y la conexión;
- tiempos extra y penales (`periodo` ≥ 3): no muestra el 1X2 de los 90 minutos (ya cerrado), dice el
  marcador a 90' (`gl90`/`gv90`, con el que se califica el pronóstico) y el de la tanda (`penales`); en
  penales el reloj dice «Penales»; en la final la serie dice «Campeón» en lugar de «Avanza»;
- con partidos en juego o en descanso muestra la franja fija «EN VIVO» bajo la barra (escudos,
  marcador en tablero y minuto que avanza solo a partir de `reloj_utc`, sin pasar del tope del
  periodo); al tocar un partido lleva a su tarjeta. En escritorio la franja se completa con
  `ultimo_evento.texto` y «Sigue: …» (`siguiente`). La barra y la franja son opacas;
- en la tarjeta del partido: marcador, línea de eventos y probabilidad al momento contra el pronóstico
  previo; al terminar, resultado final y si el pronóstico acertó;
- sección «Al momento» (sólo aparece si el documento trae partidos de hoy): marcadores del día, tabla
  al momento con flechas (sólo si el equipo cambió de lugar) y equipos en juego, probabilidad de
  clasificar y de campeón con su cambio;
- los cambios de probabilidad van con flecha y cifra («▲ 8.0», «▼ 15.8», «=») y una sola nota de
  «puntos porcentuales» por bloque (nunca «pts», que se confunde con los puntos de la tabla);
- en liguilla, el cuadro, el mini-cuadro y el detalle de la serie muestran el global y la probabilidad
  de avanzar al momento de cada serie de `series` con `al_momento` distinto de `false`, sólo si sus
  equipos son los de la tarjeta (la llave «C1» se repite de un torneo a otro); la pierna que se juega
  muestra su marcador real («En juego») en lugar del pronóstico;
- un evento nuevo (`ultimo_evento` distinto al anterior) sale como aviso breve (visible y en
  `aria-live`; no intercepta toques y ocupa como mucho dos renglones) y el dígito del marcador que
  cambió destella;
- un documento raro (`{}`, `null`, campos en `null`) se ignora sin romper nada; un documento con
  `ejemplo: true` se rotula «Ejemplo» / «datos de ejemplo».

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
  de su estadio (`PORTADAS`: encuadre vertical y horizontal, lado del texto, acercamiento, tono y, si el
  estadio queda al centro, `dx_ancho` para correr la foto de lado en escritorio; las de día se oscurecen
  y se enfrían). Movimiento lento tipo Ken Burns en CSS; su último título (`proyeccion.titulos`) en un
  renglón y el crédito de la foto en texto corrido, sin encimar nada.
  - En celular la foto mide la mitad de la pantalla (`--foto: 52svh`) para que titular, favorito, último
    título y las 4 probabilidades quepan en la primera pantalla (la prueba lo revisa a 390x664, 360x700 y
    375x620, con y sin franja en vivo). Si se toca el tamaño del título (`--t-7`) o de la copa, «CEREBRO»
    debe seguir cabiendo junto a ella.
  - En escritorio el texto ocupa una columna de 600 px del lado que diga `lado`; la copa se para junto a
    las probabilidades, del lado de la foto, y todo cabe en una pantalla desde 1280x720.
  - Trofeo: copa genérica dibujada en SVG (NO es el trofeo oficial) con degradados metálicos
    (`#tf-metal`, `#tf-peana`…; los colores salen de los tokens `--oro-*` y `--brillo` con las clases
    `.tf-*`), brillo especular, halo y dos haces de reflector en CSS, y el escudo del favorito al frente.
  - Confeti en un `<canvas>` con los colores del club: tres capas de profundidad (fondo chico y tenue,
    medio, frente grande y suave) y serpentinas doradas; ráfaga inicial de 1.5 s que sale de la copa y
    después poca densidad; se apaga sobre el texto; en pausa fuera de pantalla; una imagen fija con
    movimiento reducido.
- **Liguilla** (`liguilla.torneo`): estructura de torneo con ida y vuelta por serie.
  - Celular y tableta (<900 px): arriba un **mini-cuadro** de tres columnas (4 cuartos, 2 semifinales y
    la final con el trofeo y el campeón de la ruta) con líneas de cal; cada nodo es un botón con los dos
    equipos (escudo, abreviatura y % de avanzar) y dos renglones «IDA XOL 1-1 CAZ» / «VTA CAZ 2-0 XOL»
    en orden local–visitante. Dorado = pronóstico, blanco = resultado real; con la serie en juego (según
    el documento en vivo) sale un punto rojo y los % pasan a ser los del momento; ya decidida, muestra el
    global real. Tocar un nodo lleva a la tarjeta de esa serie. Debajo, las tarjetas en lista vertical
    agrupada por ronda, con los botones de ronda pegajosos bajo la barra (y bajo la franja en vivo).
  - De 900 a 1399 px: cuadro de tres columnas con líneas de cal, sin desplazamiento.
  - Desde 1400 px: cuadro en espejo que cabe en una pantalla de 1440x900 (cuartos a los lados,
    semifinales, y la final al centro con el campeón encima).
  - Cada tarjeta muestra sembrados, % y barra de avance, e ida y vuelta (sede sin el prefijo «Estadio»,
    fecha, marcador en tablero y 1X2 chico). NO lleva «global probable» (no es la suma de los dos
    marcadores y confundía); sí lleva el global real cuando la serie ya tiene partidos jugados. En vivo,
    el tablero del global va junto a la pastilla «Al momento» y los % previos se atenúan con el rótulo
    «Antes del partido».
  - Tocar una tarjeta abre su detalle debajo (al cargar, el detalle sólo invita a elegir serie): los 5
    marcadores de cada partido, el global más probable (en texto, con la frase que explica por qué no es
    la suma), los globales y los cruces alternativos («sale en 14.4% · CAZ avanza 79%»), y un botón
    «Volver al cuadro». Tablero dorado = pronóstico; tablero blanco = resultado real. Si falta
    `liguilla.torneo` sale un aviso.
- Completa en reposo: las animaciones parten de un estado visible; con `prefers-reduced-motion` no hay
  animaciones ni autoplay.
- Navegación interna con `scrollIntoView` (no se usa `location.hash`, `history` ni `localStorage`).
- Los videos de las bandas no se descargan hasta que entran en pantalla (`preload="none"`).

## Probar

Chromium y WebKit, en iPhone 13 y en escritorio 1440x900 (abre `web/documento.html` con `file://`):

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium
    PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit
    # con --capturas guarda PNG en web/pruebas/capturas/ (ignoradas por git)

Revisa (230 comprobaciones por motor): fragmento válido y contrato de la plataforma, sin colores
literales, portada (foto, Ken Burns, trofeo, confeti, nada encimado; en celular, que quepa en la primera
pantalla a 390x664, 360x700 y 375x620, con y sin franja en vivo; en escritorio, que quepa y que la copa
no toque el título), el cuadro (4 + 2 + 1 series con ida y vuelta, sin «global probable»; en celular el
mini-cuadro de ≤358 px con sus marcadores en orden local–visitante, la lista vertical sin desplazamiento
de lado y los botones de ronda pegajosos; en escritorio, nada cortado con puntos suspensivos a 1024,
1180, 1280, 1366, 1440 y 1920 y el espejo en una pantalla de 1440x900), el detalle (invitación, frase del
global, «Volver al cuadro»), menú coherente con las secciones, pestañas, imágenes, textos sin
`undefined`/`NaN`/`null`, y el vivo con un `window.claude` simulado (franja opaca y completa, minuto que
avanza con el reloj de Playwright, gol nuevo con aviso, tabla al momento sin guiones, cambios con flecha
y «puntos porcentuales», tarjetas de «Al momento» en 4 o en 2 x 2, navegación a 1160 px, serie en juego
en el cuadro, en el mini-cuadro y en el detalle, documentos corruptos, límite de 10 s, `use` → `null`,
«vivo» incrustado; y la robustez: documento viejo que no reemplaza al vigente, lectura que no salta
cuando «Al momento» crece, error del oyente con nueva suscripción, flujo cortado que caduca en
`vence_utc`, documento de prueba, tiempos extra y penales, aviso que no estorba), más las variantes de liguilla en curso, sin `liguilla.torneo`, opcionales en `null` y
movimiento reducido. Sale con código 1 si algo falla. Tarda unos 2 minutos por motor. Si la máquina no
tiene salida a internet las fuentes de Google no cargan y se prueba con la pila de respaldo.

Para revisar la portada de otro favorito: `python3 web/construir.py --portada Toluca` (escribe sólo
`web/documento.html`) y abrirlo a 390x664, 1280x720 y 1440x900.
