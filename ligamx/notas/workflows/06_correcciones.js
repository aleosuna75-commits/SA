export const meta = {
  name: 'ligamx-correcciones',
  description: 'Cerebro Liga MX: corrección visual del rediseño (17 defectos), crítica funcional de la capa en vivo y del motor, corrección funcional y verificación',
  phases: [
    { title: 'Corregir y criticar', detail: 'corrección visual de la página en paralelo con la crítica funcional (sobre una copia congelada)' },
    { title: 'Cerrar', detail: 'aplicar los hallazgos funcionales, volver a correr todas las pruebas y verificar' },
  ],
}

const RAIZ = '/home/user/SA/ligamx'
const SCR = '/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad'
const SNAP = SCR + '/func/snap'

const COMUN = `
Contexto: proyecto Cerebro Liga MX en ${RAIZ} (pronósticos de la Liga MX; página publicada como Artifact de claude.ai). Lee ${RAIZ}/web/LEEME.md y lo que necesites de ${RAIZ}/salidas/CONTRATO.md. El estado general está en ${RAIZ}/ESTADO.md (sección «En curso»).
Playwright ya está instalado: Chromium con PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers y WebKit con PLAYWRIGHT_BROWSERS_PATH=${SCR}/pw (no instales nada). ${RAIZ}/web/pruebas/prueba.js trae un window.claude simulado que puedes reutilizar.
Reglas del proyecto que no se rompen: el JavaScript no calcula probabilidades (sólo da formato a lo que exporta Python); la página es un fragmento sin doctype/html/head/body, un solo tema oscuro con todos los colores como tokens en :root, sin scripts externos, sin location.hash ni pushState, cada bloque de pintado aislado con seguro(); probar SIEMPRE en WebKit (iPhone 13) además de Chromium. No hagas commit ni push ni publiques nada: de eso se encarga la sesión principal.
Presupuesto: los tokens de esta ventana son limitados. Lee los archivos grandes por secciones (grep + rangos), mira sólo las capturas que necesites (deviceScaleFactor 1 y recortes, no páginas completas) y no repitas la batería completa de pruebas más veces de las necesarias (la batería tarda ~2 min por motor).
Puede que una corrida anterior de esta misma tarea haya quedado a medias (se acaba el límite de uso): antes de empezar revisa «git -C /home/user/SA status --short» y «git -C /home/user/SA diff --stat» y continúa desde lo que ya esté hecho en vez de rehacerlo.
`

const INFORME = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    archivos: { type: 'array', items: { type: 'string' } },
    hecho: { type: 'array', items: { type: 'string' }, description: 'una línea por defecto o hallazgo atendido, con su identificador' },
    no_hecho: { type: 'array', items: { type: 'string' }, description: 'lo que no se arregló y por qué' },
    pruebas: { type: 'string', description: 'qué baterías corriste y su resultado literal' },
    capturas: { type: 'array', items: { type: 'string' }, description: 'rutas absolutas de las capturas finales' },
  },
  required: ['resumen', 'archivos', 'hecho', 'no_hecho', 'pruebas', 'capturas'],
}

const HALLAZGOS = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    hallazgos: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          gravedad: { type: 'string', enum: ['alta', 'media', 'baja'] },
          area: { type: 'string', enum: ['pagina', 'motor', 'modelo_en_juego', 'operacion'] },
          donde: { type: 'string', description: 'archivo y línea o función' },
          que: { type: 'string' },
          reproducido: { type: 'boolean' },
          como_reproducir: { type: 'string' },
          como_arreglar: { type: 'string' },
        },
        required: ['id', 'gravedad', 'area', 'donde', 'que', 'reproducido', 'como_reproducir', 'como_arreglar'],
      },
    },
    lo_que_esta_bien: { type: 'array', items: { type: 'string' } },
    sin_revisar: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'hallazgos', 'lo_que_esta_bien', 'sin_revisar'],
}

const P_VISUAL = `Eres quien deja A PUNTO el diseño de la página de Cerebro Liga MX. ${COMUN}
Situación: al usuario le encantó la versión del commit 5306055 (git -C /home/user/SA show 5306055:ligamx/web/plantilla.html); una versión intermedia «bajó muchísimo» y pidió volver a ponerla a punto, con la liguilla en ESTRUCTURA DE TORNEO y pronóstico de IDA y VUELTA por partido, y que la actualización se vea EN VIVO. La versión actual (web/plantilla.html, ya publicada como intermedia) ya trae portada por favorito, cuadro y capa en vivo; un crítico independiente la comparó contra la 5306055 y dejó 17 defectos concretos, con dónde y cómo arreglar, en ${RAIZ}/notas/critica_visual_v4.md. Tu trabajo: arreglarlos TODOS (D1 a D17), sin tocar lo que el crítico lista como aciertos, y dejar las pruebas en verde en Chromium y WebKit. El usuario la mira sobre todo en su iPhone: ahí es donde tiene que impresionar.

Decisiones ya tomadas (mandan sobre las alternativas que ofrece la crítica):
1. PORTADA EN CELULAR (D3): tiene que caber completa en la primera pantalla: titular, «X es el favorito al título», último título y las 4 probabilidades, a 390x664 (iPhone 13 en Safari), 360x700 y 375x620, con y sin la franja en vivo. El crédito de la foto puede quedar bajo el pliegue. Añade esa revisión a prueba.js.
2. LIGUILLA EN CELULAR (D2): arriba un MINI-CUADRO del torneo completo que se entienda de un vistazo y quepa en el ancho de la pantalla (≤358 px) y en ~430 px de alto: 3 columnas (4 cuartos, 2 semifinales, final con el trofeo y el campeón de la ruta), líneas de cal que conectan las llaves, y en cada nodo los dos equipos (escudo de ~16-18 px, abreviatura y % de avanzar) más dos renglones chicos con el marcador más probable de la IDA y de la VUELTA en orden local–visitante con abreviaturas (p. ej. «IDA TIJ 1-1 CAZ», «VTA CAZ 2-0 TIJ»). Resultado real en blanco, pronóstico en dorado, punto rojo si la serie se está jugando. Cada nodo es un botón que lleva a la tarjeta de esa serie. Sólo formato de datos que ya vienen en liguilla.torneo (y en el vivo para lo real). Debajo, las tarjetas de las series en LISTA VERTICAL agrupada por ronda (Cuartos, Semifinales, Final), sin desplazamiento horizontal, sin huecos muertos y sin el aviso «Desliza el cuadro»; los botones de ronda quedan pegajosos bajo la barra (y bajo la franja en vivo si existe). Con esto D12 (canal de la Final y aviso de deslizar) deja de aplicar en celular.
3. FILA «GLOBAL PROBABLE» (D8): quítala de las tarjetas del cuadro en todos los anchos (confunde: no es la suma de los dos marcadores y vale ~5%). Se queda sólo en el detalle de la serie, con la frase «El global más probable no es la suma de los dos marcadores: cada marcador es el más probable de su partido». Cuando la serie ya tenga partidos jugados o esté en vivo, la tarjeta SÍ muestra el global real (es un hecho, no un pronóstico). Con la tarjeta más baja, el cuadro en espejo debe caber en una pantalla de 1440x900 y el de 3 columnas verse limpio.
4. ANCHOS (D1): cuadro en espejo sólo desde 1400 px; de 900 a 1399 px el cuadro de 3 columnas sin desplazamiento; nada cortado con puntos suspensivos en #cuadro a 1024, 1180, 1280, 1366, 1440 y 1920 (añade la revisión a prueba.js).
5. PORTADA EN ESCRITORIO (D4), TROFEO (D5) y CONFETI (D6): sigue la crítica. El trofeo debe verse como una copa con materia (degradado metálico, brillo, halo), genérica: NO copies el trofeo oficial de la Liga MX. Verifica la portada de América (texto a la derecha) a 1280 y 1440 y que las portadas con texto a la izquierda (Toluca, Tigres, Monterrey, Pachuca) no empeoren (construir.py --portada EQUIPO).
6. Lo demás (D7, D9, D10, D11, D13 a D17): como dice la crítica. En D9 usa flecha y cifra («▲ 8.0», «▼ 15.8») con una nota única de «puntos porcentuales».

Límites: trabaja sólo dentro de ${RAIZ}/web/ (plantilla.html, construir.py, pruebas/prueba.js, LEEME.md). No toques vivo.py, produccion/, modelo/ ni salidas/. No cambies CAPACIDADES en construir.py (ya está bien: ruta «vivo» y user). Mientras trabajas, otro agente revisa una COPIA congelada de la página; no edita web/. Las secciones que al usuario le encantaron (próximos partidos, combinada, camino al título, tabla, última jornada, estadios, dominios, modelo) deben quedar idénticas salvo D14 y D17.
Al terminar: «python3 web/construir.py» (sin argumentos) para dejar web/index.html al día, y «node web/pruebas/prueba.js chromium» y «... webkit» en verde. Deja capturas finales (deviceScaleFactor 2) en ${SCR}/final/: WebKit iPhone 13 → portada (primera pantalla), mini-cuadro, una tarjeta de serie, detalle de serie, portada con franja en vivo, tarjeta en vivo; Chromium 1440x900 y 1280x720 → portada y cuadro. Actualiza web/LEEME.md con lo que cambió. Devuelve el informe: por cada D1..D17 una línea con lo hecho, y lo que no se pudo y por qué.`

const P_CRITICA = `Eres un revisor adversarial: tu trabajo es ROMPER la capa en vivo de Cerebro Liga MX antes de que la vea el usuario en un partido real. No arreglas nada: reportas hallazgos verificados. ${COMUN}
Qué se construyó ayer: (a) un motor (${RAIZ}/vivo.py, ${RAIZ}/produccion/en_juego.py, simulador.simular(en_juego=...) en ${RAIZ}/produccion/simulador.py; documentación en ${RAIZ}/produccion/VIVO.md; pruebas en ${RAIZ}/produccion/pruebas/test_vivo.py) que consulta el marcador de ESPN, escribe ${RAIZ}/salidas/vivo.json y despierta a la sesión en cada evento; la sesión copia ese documento a la base del Artifact (documento «vivo/actual») y (b) la página, que lo recibe con claude.use("db") y onSnapshot y pinta franja EN VIVO, tarjeta en vivo, sección «Al momento» y el avance de las series sobre el cuadro de liguilla. Nada de esto se ha probado con un partido real en juego: el primero es Querétaro–Monterrey el 14-nov.

IMPORTANTE: otro agente está editando ${RAIZ}/web/ en este momento. Para la página trabaja SÓLO con la copia congelada: ${SNAP}/index.html (documento completo con sus img/ y video/; sírvelo con «python3 -m http.server» desde ${SNAP} o ábrelo con file://) y ${SNAP}/plantilla_congelada.html (el fuente para leer). No modifiques ningún archivo versionado del repo (ni salidas/vivo.json ni web/): tus guiones, documentos de prueba y capturas van en ${SCR}/func/. NO corras «vivo.py observar» ni «vivo.py una-vez» sin redirigir sus salidas fuera de salidas/ (mira en VIVO.md qué opciones de ruta existen; «repetir» escribe en salidas/vivo_prueba*, que está ignorado por git). Al terminar comprueba con git status que no dejaste cambios tuyos fuera de ${SCR}.

Revisa, en este orden de prioridad:
1. PÁGINA EN VIVO (WebKit iPhone 13 y Chromium, con window.claude simulado). Aliméntala con secuencias reales (documentos que genera «vivo.py repetir») y con documentos hostiles: instantáneas fuera de orden (una vieja después de una nueva), documento de ayer, gol anulado por VAR (el marcador BAJA), dos partidos a la vez, descanso, 90+N, tiempos extra y penales en una final, serie de liguilla en vivo (global y avance al momento sobre el cuadro y en el detalle), partido pospuesto o suspendido, ids como número y como texto, nombres de equipo que no coinciden con actual.json, eventos sin jugador, db null, use() que rechaza, onSnapshot que da error, base lenta (>10 s), pestaña oculta 30 min y de vuelta (¿el minuto se pone al día?), espectador fuera de México (¿las horas dicen de qué zona son?), prefers-reduced-motion, y texto de la base tratado como no confiable (¿algún innerHTML con nombres de jugador sin escapar?). Comprueba que la capa en vivo NO calcula probabilidades en JS. Busca también errores de consola, bloques de respaldo de seguro() a la vista, saltos de diseño, franja que tape contenido o controles, y trampas de scroll en iPhone.
2. MOTOR (vivo.py): detección de eventos (duplicados, dos goles entre dos consultas, gol anulado, reinicio a medio partido, roja y gol en la misma consulta), escritura atómica de vivo.json (¿un lector puede ver un archivo a medias?), candado y códigos de salida de «esperar» (condiciones de carrera, proceso muerto), qué pasa si ESPN da error o basura 5 minutos, el corte de día a las 04:00 de México y la partición de fechas de ESPN, el relevo por el tope de 2 h de los procesos en segundo plano, el partido reprogramado (Querétaro–Monterrey de la Jornada 7), la tabla al momento con los desempates oficiales (config/torneo.json), y la lógica de series de liguilla (empate global en cuartos y semis → avanza el mejor sembrado; final con tiempos extra y penales). Usa los fixtures de produccion/pruebas/fixtures y partidos reales rebobinados.
3. MODELO EN JUEGO (produccion/en_juego.py): audita la validación (¿hay fuga?: la curva de minutos y los ajustes ¿se estiman sólo con torneos anteriores al que se evalúa?; ¿las lambdas previas son de verdad fuera de muestra?), y la coherencia: al minuto 0 la probabilidad debe ser la del pronóstico previo, al final debe colapsar al resultado, debe ser monótona donde corresponde (un gol del local nunca baja su probabilidad de ganar), y con una roja el efecto debe ir en la dirección correcta para cada equipo.
4. OPERACIÓN (VIVO.md, sección 6): modos de falla del procedimiento del día de partido (la sesión dormida, el despertar que no llega, el tope de 2 h, conflicto de if_version al escribir en la base, dos partidos simultáneos) y costo: cuántos despertares de la sesión implica una jornada de 9 partidos y cuál sería el conjunto mínimo de eventos que justifican despertar; qué ve el usuario si el flujo se corta a medio partido.

Entrega como mucho 25 hallazgos, ordenados por gravedad, cada uno con archivo y línea, cómo reproducirlo (comando o guion en ${SCR}/func/) y cómo arreglarlo. Marca reproducido=true sólo si lo viste fallar; un hallazgo sólo razonado va con reproducido=false y dilo. No reportes gustos de estilo visual (eso lo cubre otra revisión). Di también qué quedó sin revisar.`

phase('Corregir y criticar')
const [visual, critica] = await parallel([
  () => agent(P_VISUAL, { label: 'correccion-visual', phase: 'Corregir y criticar', schema: INFORME }),
  () => agent(P_CRITICA, { label: 'critica-funcional', phase: 'Corregir y criticar', schema: HALLAZGOS }),
])
log('corrección visual: ' + (visual ? 'terminada' : 'SIN RESULTADO') + ' · crítica funcional: ' + (critica ? (critica.hallazgos.length + ' hallazgos') : 'SIN RESULTADO'))

phase('Cerrar')
const P_CIERRE = `Eres quien CIERRA la versión de Cerebro Liga MX que se va a publicar. ${COMUN}
Antes de ti trabajaron dos agentes: uno corrigió el diseño de la página (17 defectos de ${RAIZ}/notas/critica_visual_v4.md) y otro hizo una crítica funcional adversarial de la capa en vivo (página + ${RAIZ}/vivo.py + ${RAIZ}/produccion/en_juego.py + procedimiento de ${RAIZ}/produccion/VIVO.md) sobre una copia congelada ANTERIOR a las correcciones visuales (por eso, verifica cada hallazgo de página contra web/plantilla.html actual antes de tocar nada).

Informe de la corrección visual:
${visual ? JSON.stringify(visual, null, 1) : '(no terminó: revisa git diff de web/ y completa lo que falte de la crítica visual, empezando por los defectos de gravedad alta)'}

Hallazgos de la crítica funcional:
${critica ? JSON.stringify(critica, null, 1) : '(no terminó: haz tú una revisión funcional breve de la capa en vivo de la página y de vivo.py con documentos hostiles y arregla lo que encuentres de gravedad alta)'}

Tu trabajo:
1. Para cada hallazgo de gravedad alta o media: comprueba que es real (reprodúcelo o traza el camino desde una entrada realista). Si es real y el arreglo es proporcionado, arréglalo y añade una prueba que lo cubra (produccion/pruebas/ para el motor, web/pruebas/prueba.js para la página). Si es rebuscado o el arreglo cuesta más de lo que evita, no lo arregles y explica por qué. Los de gravedad baja: sólo los de arreglo trivial. Los de «operación»: corrige el procedimiento en produccion/VIVO.md (sección 6) para que sea a prueba de fallas y lo más barato posible en despertares, y si hace falta añade a vivo.py lo mínimo que lo sostenga (por ejemplo, despertar sólo con eventos que cambian el estado y un refresco espaciado).
2. Puedes editar web/ (plantilla.html, construir.py, pruebas/prueba.js, LEEME.md), vivo.py, produccion/ y salidas/CONTRATO.md. No cambies el contrato del documento en vivo de forma incompatible (la base del Artifact ya tiene un documento sembrado) ni CAPACIDADES en construir.py. No toques modelo/ salvo que un hallazgo real lo exija.
3. Verificación final de diseño: con la página ya corregida, toma capturas (WebKit iPhone 13; Chromium 1280x720 y 1440x900) de portada, mini-cuadro/cuadro, tarjeta de serie, detalle, franja y tarjeta en vivo, y repasa D1..D17 de la crítica visual: lo que siga mal y sea pequeño, arréglalo; lo que no, repórtalo. Comprueba en particular que la portada cabe en la primera pantalla del iPhone (390x664) y que el mini-cuadro del torneo se entiende de un vistazo.
4. Cierra con TODO en verde: «python3 -m pytest modelo/pruebas produccion/pruebas -q», «python3 pipeline.py auto» (una vez, al final; rehace salidas/actual.json y web/index.html), «node web/pruebas/prueba.js chromium» y «node web/pruebas/prueba.js webkit». Deja las capturas finales (deviceScaleFactor 2) en ${SCR}/final/ (sustituye las que haya).
Devuelve el informe: una línea por hallazgo (id, arreglado / no arreglado y por qué), el resultado literal de las cuatro baterías, y lo que quede pendiente.`
const cierre = await agent(P_CIERRE, { label: 'cierre-funcional-y-verificacion', phase: 'Cerrar', schema: INFORME })
return { visual, critica, cierre }
