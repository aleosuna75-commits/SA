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

- `--datos RUTA`: otro JSON con el mismo contrato (por ejemplo una corrida de `salidas/historial/`). Si no es
  `salidas/actual.json`, la corrida es de prueba (ver abajo): aunque se pida `--documento --salida DIR`, no
  reescribe `index.html`, `archivos_publicados.json` ni `capacidades.json`.
- `--documento`: además genera un documento completo (`<!doctype>`, `<head>`, `<body>`) en
  `web/sitio/` y copia ahí los `img/` y `video/` que la página usa.
- `--documento --salida DIR`: lo mismo en otro directorio. Si `DIR` es la propia carpeta `web/`, sólo
  escribe `web/documento.html` (es lo que usan las pruebas; sirve para abrirla con doble clic).
- `--vivo RUTA` (de prueba): incrusta ese documento en vivo como `datos.vivo`.
- `--portada EQUIPO` (de prueba): fuerza el equipo de la portada, para revisar las 16.
- `--datos OTRO.json --solo-documento web/_variante_x.html` (de prueba): escribe ÚNICAMENTE ese documento
  completo (dentro de `web/`, para que encuentre `img/` y `video/`); no toca `index.html`,
  `archivos_publicados.json` ni `capacidades.json` y se niega a escribir sobre `index.html` o
  `documento.html`. Es lo que usan las pruebas para armar la página con otro estado del torneo.

Las opciones de prueba (`--vivo`, `--portada`, `--solo-documento` y cualquier `--datos` distinto de
`salidas/actual.json`) NO tocan `index.html`, `archivos_publicados.json` ni `capacidades.json`: sólo escriben el
documento (`web/documento.html` si no se da `--salida`, el sitio de `--salida` o la ruta de `--solo-documento`).
Sin ellas, `index.html` incrusta `actual.json → vivo` cuando existe.

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
  clasificar y de campeón con su cambio. Desde el 23-nov-2026 (verificación del workflow 10):
  - el rótulo dice «Hoy» sólo si `dia` del documento es la fecha de hoy en el centro de México; si no, «Ayer» o la
    fecha, y ningún texto dice «de hoy». Si el documento es de otro día, nada está en juego y sus resultados ya
    están en `ultimos_resultados` (corrió `pipeline.py auto`), la sección y su botón del menú se retiran;
  - terminada la fase regular (`tabla_fija` o, con documentos viejos, `proyeccion.regular_completa`) la tabla es
    «Tabla final de la fase regular», sin flechas, y sólo sale mientras se juega algo (sin nada en juego repetiría
    «Tabla general · Así terminó»);
  - la proyección no sale si el motor no la recalculó (`proyeccion.previa`, o un documento viejo con todos los
    cambios en 0 y sin `partidos_considerados`) ni si, sin nada en juego, sus resultados ya están en la página: serían
    las cifras de la portada (o unas más viejas) presentadas como «=»;
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
  - Toda la tarjeta es el botón «Detalle» (`.llave .llave__ver::before` la cubre): en WebKit un toque fuera de un
    botón no sintetiza el clic. Con la serie en juego, el detalle muestra el marcador real de la pierna que se juega
    y rotula «antes del partido» el pronóstico de esa pierna y los globales.
  - Tocar una tarjeta abre su detalle debajo (al cargar, el detalle sólo invita a elegir serie): los 5
    marcadores de cada partido, el global más probable (en texto, con la frase que explica por qué no es
    la suma), los globales y los cruces alternativos («sale en 14.4% · CAZ avanza 79%»), y un botón
    «Volver al cuadro». Tablero dorado = pronóstico; tablero blanco = resultado real. Si falta
    `liguilla.torneo` sale un aviso.
- **Sin partidos con día y hora** (`pendientes` vacío; pasa entre el fin de la fase regular y el momento en que la
  liga programa la ronda, y entre rondas):
  - bajo la portada, la banda «Lo que sigue» anuncia la primera ronda con partidos por jugar entre equipos ya
    definidos («Liguilla definida · Cuartos de final · Del 25 al 29 de noviembre», ida y vuelta, «Día y hora de
    cada partido: por confirmar»), un botón por cruce que lleva a su serie y «Ver el cuadro» (en celular, al estado
    del cuadro con el mini-cuadro; en pantallas anchas, al cuadro). Con la liguilla terminada, el campeón. La
    portada sigue cabiendo en la primera pantalla;
  - «Próximos partidos» muestra esas piernas (`liguilla.torneo`, series `definida` sin decidir que no vienen en
    `pendientes`) como tarjetas compactas: primero las idas y luego las vueltas, con fase y pierna, llave, escudos,
    marcador más probable, barra 1X2 con %, el pronóstico de la pierna («Gana Pachuca · 40.7%», del `pick` que trae; su % va
    resaltado en la barra), sede (la de la prensa o la habitual del local: `estadio.origen`) y fecha o ventana («25 o 26 nov»;
    desde 600 px en su propio renglón), y un
    botón «Serie C1» que abre el detalle de la serie. Una nota dice que la combinada de cada partido se publica
    cuando la liga confirme día y hora. En celular van en una columna, desde 600 px de dos en dos y desde 1160 px de
    cuatro en cuatro (ningún nombre se parte a media palabra; sede y botón alineados abajo). Si ya hay partidos
    pendientes, las piernas que falten de programar salen después de sus tarjetas completas;
  - sin nada por jugar, «Próximos partidos» se retira; sin combinada de la jornada, la sección «Combinada de la
    jornada» también se retira (en vez de ocupar una pantalla con un aviso vacío) y «Próximos partidos» dice por
    qué. El menú, la barra de escritorio y el número de cada sección (`numerar()`) siguen a las secciones que sí se
    muestran.
- **Estado de cada serie** en el cuadro: «Terminada», «En curso», «Definida» (campo `definida`: sus dos equipos ya
  son seguros; los cuartos desde el fin de la fase regular, las semifinales cuando están decididos los cuatro
  cuartos, la final cuando lo están las semifinales) o «Proyectada» (ruta de los favoritos). Con datos viejos sin el
  campo se deduce de `real` y del `estado` del torneo. Una serie definida ya no muestra cruces alternativos.
- **Fase regular terminada** (`proyeccion.regular_completa`): la tabla general se rotula «Así terminó» y desaparece
  la tabla final proyectada; «Hasta dónde llega cada uno» queda con los ocho clasificados y sin la columna
  «Liguilla»; «¿Quién será campeón?» nombra a los que no clasificaron (en el orden de la tabla) y a los eliminados
  en la liguilla; en «Camino al título» los cuartos más probables dejan su lugar a las semifinales y finales más
  probables. Todo depende de los datos, nunca de la fecha. En liguilla la combinada se llama «Combinada de la ronda»
  (sólo las pestañas de boletos distintos: `igual_a`) y «Última jornada» pasa a «Resultados recientes», agrupados por
  ronda para no mezclar fases en una cuenta.
- **Partidos de liguilla** (`pendientes[].serie`, desde el 23-nov-2026): la tarjeta y la franja «Próximo partido» dicen
  de qué serie es el partido, cómo va el global y qué necesita cada uno (texto armado en Python) con la probabilidad
  exacta de avanzar; el 1X2, los mercados y la combinada del partido se rotulan a 90 minutos. En «Al momento» cada
  partido trae su serie (texto, ida y quién avanza) y, con `vivo.tabla_fija`, la tabla es la final de la fase regular.
- **Final y campeón**: en la final la portada nombra a los dos finalistas y la ida, con sólo sus dos probabilidades;
  con el campeón decidido la portada, «Camino al título» y la llave F lo celebran (campeón y subcampeón, sin
  porcentajes). El trofeo del cuadro dice «Si gana cada favorito» (la ruta serie por serie) y, si ese no es el
  favorito al título de la simulación completa, también nombra a ese.
- Completa en reposo: las animaciones parten de un estado visible; con `prefers-reduced-motion` no hay
  animaciones ni autoplay.
- Navegación interna con `scrollIntoView` (no se usa `location.hash`, `history` ni `localStorage`).
- Los videos de las bandas no se descargan hasta que entran en pantalla (`preload="none"`).

## Probar

Chromium y WebKit, en iPhone 13 y en escritorio 1440x900. Arma y abre con `file://` tres documentos:
`web/documento.html` con los datos de hoy (se revisa lo que corresponda a SU estado: partidos pendientes o no,
piernas de liguilla sin día ni hora, cuadro proyectado / definido / en curso / terminado, fase regular terminada o
no, combinada o no), y dos copias fijas armadas con `--solo-documento`: `pruebas/datos/actual_20261120T0722Z.json`
(9 partidos pendientes, cuadro proyectado; reloj del navegador en el 20-nov) para tarjetas de partido, pestañas de
combinada, cuenta regresiva, cuadro, en vivo y variantes, y `pruebas/datos/actual_20261123T0353Z.json` (noche del
22-nov: 0 pendientes, cuadro definido, cuartos sin día ni hora; corrida de 100,000 simulaciones) con sus variantes
(datos viejos sin el campo `definida`, idas ya en el calendario, semifinales definidas, final a medio jugar, liguilla
terminada), más `pruebas/datos/vivo_vuelta_ejemplo.json` (documento en vivo de EJEMPLO de una vuelta de cuartos, idas
inventadas) para «Al momento» en liguilla:

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium
    PLAYWRIGHT_BROWSERS_PATH=<carpeta con webkit> node web/pruebas/prueba.js webkit
    # con --capturas guarda PNG en web/pruebas/capturas/ (ignoradas por git)

Revisa (625 comprobaciones por motor): fragmento válido y contrato de la plataforma, sin colores
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
movimiento reducido; y «Modelo contra mercado» en el desempeño sellado (lo que diga `desempeno.contra_mercado`
con los datos de hoy, y variantes con 3, 1 y 40 partidos comparados, sin ningún sello con momios, documento
viejo sin el campo y mercado con basura; en cada resultado, la barra del mercado sellado o la nota de que su
sello no guardó momios); y, según el estado de los datos, el anuncio bajo la portada con su botón al cuadro, las
tarjetas compactas de liguilla (contenido, orden, nombres sin partir, pie alineado, botón al detalle), que ninguna
sección visible quede vacía, la etiqueta de cada serie, el cuadro en espejo en una pantalla y los textos de la fase
regular terminada; y lo que encontró el ensayo de la liguilla (encargo E del workflow 10): títulos según la fase,
resultados por ronda, portada y «Camino al título» con la final o el campeón, «Si gana cada favorito», pronósticos
en cursiva en el mini-cuadro, pestañas sin boletos repetidos, la serie de cada partido de liguilla, la pastilla
«Resultado» legible y «Al momento» de una vuelta. Sale con código 1 si algo falla. Tarda de 2.5 a 3 minutos por motor. Si la máquina no
tiene salida a internet las fuentes de Google no cargan y se prueba con la pila de respaldo.

Para revisar la portada de otro favorito: `python3 web/construir.py --portada Toluca` (escribe sólo
`web/documento.html`) y abrirlo a 390x664, 1280x720 y 1440x900.
