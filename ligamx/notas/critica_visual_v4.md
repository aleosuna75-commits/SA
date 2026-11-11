# Crítica visual de la versión 4 (10-nov-2026)

Comparada contra el commit `5306055` (la que le encantó al usuario). Capturas del crítico en el scratchpad de la sesión (pueden ya no existir).

## Veredicto

Sí supera a la 5306055, pero todavía no está a punto: la gana por contenido (cuadro real con ida y vuelta, en vivo) y pierde en la primera impresión, que era justo lo que al usuario le encantaba. Todo lo demás que le gustaba sigue idéntico: próximos, combinada, camino, tabla, última jornada, estadios, dominios y modelo sólo cambian de numeración (comparación por píxeles). La versión intermedia que «bajó muchísimo» (c57aaa3, foto de día con cielo azul) queda claramente atrás.
Se perdió: el video de portada (ahora foto fija con movimiento lento), que la portada quepa completa en la primera pantalla del iPhone, y la composición limpia de escritorio (con América/Banorte el título choca con el estadio). Se ganó: portada que sigue al favorito, cuadro en espejo muy bueno a 1440 px, tarjeta y sección en vivo de buen nivel.
Lo que falta: el cuadro se rompe en laptops de 1160 a 1400 px y en celular no se lee como torneo de un vistazo; el trofeo y el confeti se sienten de plantilla.
Revisé en WebKit iPhone 13 y Chromium 1440x900, más 1024, 1180, 1280 y celulares de 360 a 430 px. Capturas en /tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/da/cap/ (carpetas actual-*, anterior-*, vivo-*, anchos/, portadas/, cabeza/).

## Defectos

### D1 · ALTA
**Dónde:** Liguilla, cuadro en espejo entre 1160 y ~1400 px (laptops 1280x720 y 1366x768). Bloque @media (min-width:1160px) de plantilla.html (~líneas 638-661), .cuadro{grid-template-columns:repeat(5,...)}. Capturas: anchos/cuadro-1180.png y anchos/cuadro-1280.png

**Qué:** Las 5 columnas quedan de 200-230 px y el contenido no cabe. A 1180: 8 líneas de sede y fecha cortadas con «…» (se pierde la fecha), los porcentajes 1X2 salen pegados («35%26%40%»), el escudo derecho de «Global probable» se sale del borde de la tarjeta y #cuadro desborda 4 px. A 1280: 4 fechas cortadas y escudos tocando el borde; el cuadro mide 705 px y no cabe en una pantalla de 720. A 1440 y 1920 queda una cortada («Estadio Nemesio Diez · 28 o 29 …» en C4).

**Cómo arreglar:** Separar el breakpoint: dejar .barra__nav en 1160 px y mover las reglas del espejo (.cuadro, .nodo[data-pos], .cuadro__rot, .ronda{display:contents}) a @media (min-width:1400px). Entre 900 y 1399 px usar el cuadro de 3 columnas que ya existe (a 1024 se ve impecable), sin desplazamiento: .cuadro{overflow:visible} .ronda{flex:1 1 0;min-width:0} y ocultar .desliza. En el espejo: quitar el prefijo «Estadio » del nombre en la tarjeta (sólo formato), permitir dos renglones en la línea sede·fecha (white-space:normal, sin ellipsis) y dar column-gap a los tres porcentajes. Añadir a prueba.js una revisión de «ningún texto con ellipsis recortado dentro de #cuadro» a 1180, 1280 y 1440.

### D2 · ALTA
**Dónde:** Liguilla en celular (<900 px): #cuadro, .ronda, .llave, .rondas-nav. Capturas: actual-iphone-webkit/20 a 31

**Qué:** No se entiende de un vistazo como torneo. Cada tarjeta mide ~290 px de alto, así que en 664 px sólo cabe 1.7 series; la columna de cuartos mide 1,250 px. Semis y final nunca se ven junto a los cuartos: sólo asoman 70 px con textos cortados («VUE», «GLO»). La columna de semifinales tiene ~300 px vacíos sobre S1 y ~500 px entre S1 y S2. Los botones de ronda desaparecen al bajar a C2/C3 y repiten lo mismo que la cabecera de columna 80 px más abajo.

**Cómo arreglar:** Añadir sobre .rondas-nav, sólo en <900 px, un mini-mapa del cuadro que quepa en 358 px: rejilla de 3 columnas (4 + 2 + 1 nodos), cada serie con dos renglones de ~22 px (escudo de 18 px, abreviatura y % de avanzar de p_avanza_mejor/peor), las mismas líneas de cal con ::after, y la final con el trofeo y campeon_ruta. Cada nodo es un botón data-serie que lleva a su tarjeta. Sólo da formato a datos que ya vienen. Además: .rondas-nav{position:sticky;top:60px} (106 px con .con-franja) y ocultar .ronda__cab en celular. Alternativa mínima si no hay mini-mapa: tarjeta compacta (IDA y VUELTA en un renglón cada una, «IDA 1-1 · Caliente · 25 o 26 nov», sin barra 1X2, que queda para el detalle) para que los 4 cuartos midan ≤150 px.

### D3 · ALTA
**Dónde:** Portada en celular: .portada{--foto:clamp(300px,98vw,560px)}, .palmares, .portada__pie. Capturas: actual-iphone-webkit/01-portada-0s.png contra anterior-iphone-webkit/01-portada-0s.png, y anchos/portada-m*.png

**Qué:** La portada ya no cabe en la primera pantalla. Mide 778 px en iPhone 13 Safari (664 útiles), 759 en 375x620 y 740 en 360x700. La segunda fila de probabilidades (Chivas y Toluca) queda partida a la mitad en el pliegue. La anterior cabía exacta (664 px, con las 4 probabilidades y la nota). Con la franja en vivo (+50 px) empeora.

**Cómo arreglar:** En <900 px: --foto:clamp(230px,40svh,560px) (hoy 98vw = 382 px de foto), h1{margin:8px 0 12px}, palmarés en un solo renglón («Último título: Apertura 2024, ante Monterrey, 3-2»; quitar flex-basis:100% de .palmares i), .favoritos li{padding:7px 12px}. Objetivo: que el borde inferior de .favoritos quede ≤ 100svh − 12 px en 390x664 y 360x700 (el crédito de la foto puede quedar bajo el pliegue). Añadir esa comprobación a prueba.js, también con .con-franja.

### D4 · MEDIA
**Dónde:** Portada en escritorio con América/Banorte (data-lado="der"): .portada[data-lado="der"] .fondo::after, .portada__caja, PORTADAS["banorte"] en construir.py. Captura: actual-desk-chromium/02-portada-5s.png contra anterior-desk-chromium/02-portada-5s.png

**Qué:** El título arranca en x≈550 y pisa la mitad derecha del estadio. El rótulo luminoso «BANORTE» termina en x≈515, a la misma altura que «CEREBRO», y se leen como una sola línea. «APERTURA 2026» en dorado cae sobre el anillo rojo y blanco del techo y casi no se lee. El velo lateral llega a 0 al 66% del ancho, antes de donde empieza el título. La anterior tenía el bloque sobre zona limpia. Además la foto es de 1600x900 con zoom 1.26 y se ve blanda. Las portadas con texto a la izquierda (Toluca, Tigres, Monterrey, Pachuca) sí funcionan.

**Cómo arreglar:** (1) Alargar el velo del lado derecho: linear-gradient(270deg,var(--velo-2) 0,var(--velo-2) 46%,var(--velo-1) 62%,var(--velo-0) 80%). (2) En ≥900 px limitar h1 a clamp(4rem,10.5vw,8.6rem) para que la caja mida ≤600 px y empiece en x≥690. (3) En PORTADAS["banorte"] bajar zoom a ~1.05 y mover pos_ancho para que el estadio termine antes del 40% del ancho. (4) Darle a .sello sombra más fuerte o una pastilla var(--velo-2). Verificar a 1440 y 1280.

### D5 · MEDIA
**Dónde:** Portada, trofeo: <symbol id="s-trofeo">, .emblema, .trofeo, .emblema__esc. Recorte: z-trofeo-movil.png

**Qué:** Se ve como un icono de línea pegado sobre una foto: contorno dorado de 3 px sin volumen, 105 px en celular, flotando junto al título. No transmite «levantar la copa» y es lo más genérico de la portada. En las portadas con texto a la izquierda cae en medio de la foto (Akron: sobre el techo y un poste; BBVA: sobre la cumbre).

**Cómo arreglar:** Darle materia sin copiar el trofeo oficial: relleno con degradado metálico (linearGradient de --oro-2 a --oro a sombra) y un brillo especular en el cáliz dentro del symbol; halo detrás con .emblema::before{background:radial-gradient(closest-side,var(--oro-brillo),var(--velo-0))}; dos haces de reflector tenues. Subir el tamaño a clamp(120px,34vw,220px). En ≥900 px sacarlo de la fila del título y anclarlo a la altura de .favoritos, del lado de la caja, con un velo local detrás para que no compita con el estadio.

### D6 · MEDIA
**Dónde:** Portada, función confeti() (~línea 1167) y .confeti

**Qué:** Son 22 a 64 rectángulos de 4-8 px cayendo sin fin. En escritorio se lee como polvo o ruido sobre la foto, no como festejo, y con .confeti{height:100%} cruza por detrás del título. En celular es discreto pero igual de tímido.

**Cómo arreglar:** Tres capas de profundidad: fondo de 3-5 px con alfa .35, medio de 6-10 px, y 8-10 piezas de frente de 14-26 px con alfa .5 y algo de desenfoque. Añadir unas serpentinas doradas (arcos). Ráfaga inicial de 1.5 s que salga de la copa y después densidad baja. En escritorio apagarlo sobre el rectángulo de .portada__caja, como ya se hace en celular con el factor f. Conservar la pausa fuera de pantalla y la imagen fija con movimiento reducido.

### D7 · MEDIA
**Dónde:** Sección «Al momento» en escritorio: .marc .llave__ver y la rejilla de #b-vivo-partidos. Captura: vivo-desk-chromium/02-vivo-seccion-t1.png

**Qué:** La regla .llave__ver{font-size:0} (línea 660, dentro de @media ≥1160, pensada para el cuadro) también borra el texto de «Ver el partido»: queda una flechita suelta de 6 px. La flecha no se ancla abajo: en las tarjetas cortas (Descanso, Por jugar) flota a media altura con ~70 px vacíos debajo. La cuarta tarjeta queda huérfana en una segunda fila (3 + 1).

**Cómo arreglar:** Limitar la regla a .cuadro .llave__ver. .marc{display:flex;flex-direction:column} y .marc .llave__ver{margin-top:auto;align-self:flex-end}. Rejilla repeat(auto-fit,minmax(250px,1fr)): 4 columnas en ≥1160 px y 2x2 entre 700 y 1159.

### D8 · MEDIA
**Dónde:** Tarjetas del cuadro, fila «Global probable»: globalLlave(s), y nota bajo el cuadro. Capturas: actual-iphone-webkit/20 y 21, actual-desk-chromium/20-cuadro-pantalla.png

**Qué:** A la vista contradice a la ida y la vuelta. C1: ida 1-1 y vuelta 2-0, pero global 3-2. C4: 1-1 y 2-0, global 4-2. S1: 1-1 y 1-1, global 3-3. El dato es fiel a global.probable (lo comprobé en actual.json: el global más probable no es la suma de los dos marcadores más probables), pero se percibe como error de suma. Además lleva tablero grande un resultado de 5%, y en escritorio la etiqueta se parte en dos renglones con el «5%» colgando.

**Cómo arreglar:** Sólo formato, sin calcular nada: etiqueta «Global más probable» en una línea (letter-spacing .08em en escritorio). Una frase junto a la nota del cuadro: «El global más probable no es la suma de los dos marcadores: cada marcador es el más probable de su partido». Bajar el peso de esa fila (cifra en texto de cartel, sin caja LED) y dejar que mande el % de avanzar, que es el dato fuerte.

### D9 · MEDIA
**Dónde:** En vivo: deltas en bloqueVivo (tarjeta), «Clasificar a la liguilla, al momento» y «Campeón, al momento» (.barras .val .dl)

**Qué:** Los cambios de probabilidad dicen «+8.0 pts», «−15.8 pts», «+1.0 pts». En una página de futbol, junto a la columna PTS de la tabla, se leen como puntos de la clasificación.

**Cómo arreglar:** Usar flecha y cifra («▲ 8.0», «▼ 15.8», «=») con los colores --gana/--pierde que ya existen, o «p. p.», y una nota única: «Cambio en puntos porcentuales frente al pronóstico de antes del partido».

### D10 · MEDIA
**Dónde:** Franja «EN VIVO»: .franja__in, .franja__lista, .fr. Capturas: z-barra-fantasma.png (celular) y vivo-desk-chromium/01-vivo-portada-con-franja.png

**Qué:** Celular: la lista se corta con borde duro unos 16 px antes del borde de la pantalla (la segunda pastilla queda partida a media cifra) mientras las líneas de la franja sí llegan al borde; hay un hueco entre el escudo visitante y el minuto. Escritorio: dos pastillas de ~170 px pegadas a la izquierda y más de 800 px de franja vacía.

**Cómo arreglar:** Celular: .franja__lista{margin-right:calc(-1*var(--canal-d));padding-right:var(--canal-d)} y un desvanecido con mask-image:linear-gradient(90deg,var(--tinta) calc(100% - 28px),var(--velo-0)) (con prefijo -webkit-); quitar el min-width del minuto. Escritorio: llenar la derecha con datos que ya llegan, ultimo_evento.texto en gris y «Sigue: Pumas–Monterrey 19:00» de siguiente.

### D11 · MEDIA
**Dónde:** Tarjetas del cuadro con liguilla en curso o en vivo: .llave. Capturas del constructor: web/pruebas/capturas/chromium-iphone-10-liguilla-en-curso.png y chromium-iphone-9e-vivo-cuadro.png

**Qué:** Todas las tarjetas miden lo mismo, y las series con menos renglones (terminada, sin global) dejan 100-150 px muertos al fondo. En vivo, la misma tarjeta muestra dos juegos de porcentajes de avanzar que compiten: 79%/21% grandes arriba (previo) y «Avanza: CAZ 87% · XOL 13%» chico en el bloque «Al momento», con el tablero flotando solo a la derecha. Con chip de estado largo («PROYECTADA») el subtítulo se corta a «4.º contra …».

**Cómo arreglar:** .llave{display:flex;flex-direction:column} y margin-top:auto en la fila del global para repartir el hueco. Cuando haya bloque al momento, atenuar los % previos (color --gris y rótulo «antes del partido») y poner el tablero junto a la pastilla. En escritorio bajar el chip de estado a su propio renglón.

### D12 · BAJA
**Dónde:** Cuadro en celular, última columna y aviso: .cuadro, .desliza. Captura: actual-iphone-webkit/29-cuadro-final.png

**Qué:** La tarjeta de la Final queda pegada al borde derecho de la pantalla, sin el canal de 16 px. «Desliza el cuadro →» sigue apuntando a la derecha cuando ya se está en la Final.

**Cómo arreglar:** .cuadro::after{content:"";flex:0 0 var(--canal-d)} y scroll-padding-inline:var(--canal-i). Ocultar o invertir .desliza cuando scrollLeft llegue al máximo, en el mismo manejador que marca aria-current en .rondas-nav.

### D13 · BAJA
**Dónde:** Detalle de la serie: #serie-det, .serie-sel, .lista de cruces alternativos. Capturas: z-det-C1.png y actual-desk-chromium/23-detalle-C1-t2.png

**Qué:** Siempre está abierto con C1 (2,160 px en celular que nadie pidió) y C1 aparece con borde dorado en el cuadro sin explicación. No hay forma de volver al cuadro al terminar de leer. Los chips C1…F no caben en 390 px (F queda cortado). En «Los cruces más probables» el «14.4%» suelto no dice qué es; en escritorio el nombre y la cifra quedan separados 900 px y desalineados en vertical.

**Cómo arreglar:** Chips con flex:1 y min-width:0 (o 40 px) para que quepan los 7. Botón «↑ Volver al cuadro» (data-ir="cuadro") al pie de #serie-det. Abrir por omisión la serie del favorito al título o dejar una invitación «Toca una serie». En la lista: max-width:640px, align-items:center y el texto «sale en 14.4% · CAZ avanza 79%».

### D14 · BAJA
**Dónde:** Barra fija y franja: .barra.solida, .con-franja .barra, .franja (fondo var(--velo-3) = .95). Captura: z-barra-fantasma.png. Heredado de 5306055

**Qué:** El contenido se transparenta detrás de la barra: títulos como «JORNADA 7 (REPROGRAMADO)» u «OTROS MERCADOS» pasan como texto fantasma detrás del logotipo y del menú. Es tenue, pero está en toda la página y se nota más en WebKit.

**Cómo arreglar:** Fondo opaco var(--noche) en .barra.solida, .con-franja .barra y .franja; o conservar el .95 con -webkit-backdrop-filter:blur(14px) y backdrop-filter:blur(14px) también en la barra.

### D15 · BAJA
**Dónde:** Barra de navegación en vivo entre 1160 y ~1215 px: .barra__nav, #hamb. Captura: anchos/vivo-top-1180.png

**Qué:** Al aparecer «Al momento» en la navegación, la hamburguesa queda fuera de la pantalla (x=1204 en un ancho de 1180), y con ella «Inicio» y «Créditos», que sólo están en el menú.

**Cómo arreglar:** @media (min-width:1160px) and (max-width:1319px){.barra__nav button{padding:14px 6px;letter-spacing:.06em}} y .hamb{flex:none}. Comprobar a 1160 con .con-franja.

### D16 · BAJA
**Dónde:** Tabla al momento (#b-vivo-tabla) y tarjeta terminada. Captura: z-vivo-sec.png

**Qué:** Con cambio = 0 se pinta un guion junto a la posición en las 18 filas («3 –», «4 –»): ruido que parece signo de menos. En el partido terminado se repite «FINAL» y «RESULTADO FINAL» en la misma línea.

**Cómo arreglar:** No pintar nada cuando cambio es 0 y reservar el ancho para que no brinque; flecha sólo si hay cambio. Dejar una sola etiqueta en el partido terminado.

### D17 · BAJA
**Dónde:** Camino al título, tabla «Hasta dónde llega cada uno» (#b-embudo). Captura: z-act-camino-12.png. Heredado de 5306055

**Qué:** Las barras de celdas vecinas se funden: «Liguilla 100%» y «Semis 79%» parecen una sola barra larga, y el borde de la barra corta el número siguiente.

**Cómo arreglar:** Separador en las celdas (td+td{border-left:1px solid var(--linea)}) y barra como filete de 4 px al pie de la celda, o con inset de 6 px, para que el número quede sobre fondo liso.

## Aciertos (no tocar)

- La identidad que le encantó sigue intacta: Big Shoulders Display + Archivo, paleta noche/oro/cal, tableros tipo LED, barras 1X2 verde-gris-azul, cabeceras de banda con foto y crédito. Próximos partidos, combinada, camino, tabla, última jornada, estadios, dominios y modelo son idénticos a 5306055 salvo la numeración. No tocar.
- Portada en celular: foto nocturna aérea del Banorte arriba y texto limpio sobre el degradado, con crédito en texto corrido. Es más pertinente que el video del BBVA de la versión anterior (era otro estadio).
- Portadas de otros favoritos: Toluca (fuegos artificiales en el Nemesio Diez), Tigres (atardecer), Pachuca (reflectores) y Monterrey quedan cinematográficas, en celular y en escritorio con texto a la izquierda. No tocar esos encuadres.
- Cuadro en espejo a 1440 px: se lee como bracket al instante. Cuartos a los lados, semifinales, final al centro con «Campeón por esta ruta» encima, líneas de cal finas con esquinas redondeadas, simetría correcta. Conservarlo tal cual para ≥1400 px.
- Cuadro de 3 columnas a 1024 px: amplio, nada cortado, conectores claros. Es el diseño a extender hasta 1399 px.
- Tarjeta de serie: sembrado, escudo, % de avanzar grande con barra dorada, IDA y VUELTA con sede y fecha honesta («25 o 26 nov»), orden local–visita correcto, tablero dorado para pronóstico y blanco para resultado real, y chips de estado (en curso, terminada, definida, avanza).
- Navegación del cuadro en celular: los botones Cuartos/Semifinales/Final llevan a la serie tanto en horizontal como en vertical, con scroll-snap por ronda; tocar una tarjeta baja al detalle.
- Detalle de la serie: mismo lenguaje que las tarjetas de partido (duelo con tablero, «Quién avanza», 5 marcadores por partido, goles esperados, globales, regla de empate, cruces alternativos). En escritorio, ida y vuelta lado a lado.
- Bloque en vivo dentro de la tarjeta del partido: tinte granate, pastilla roja con punto, minuto grande, cronología con local a la izquierda, visita a la derecha y minuto al centro, tarjeta roja junto al equipo, destello del dígito que cambió, aviso de gol bajo la franja y «Probabilidad al momento» contra «Pronóstico antes del partido». Lo mejor de lo nuevo.
- Sección «Al momento» en celular: marcadores del día por estado (en vivo, descanso, por jugar, final), tabla con filas en juego resaltadas, punto rojo y línea de corte, barras de clasificar y campeón con su cambio, e indicador de conexión con «datos de ejemplo».
- Franja «EN VIVO»: compacta (50 px), con escudos, tablero y minuto; no tapa el título de la portada.
- Menú a pantalla completa con numeración coherente y «Liguilla» en su lugar; «Fechas de la liguilla» y «Cómo se juega» bien movidas a la sección Liguilla.
