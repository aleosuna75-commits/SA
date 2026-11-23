export const meta = {
  name: 'liguilla-puesta-a-punto',
  description: 'Deja la pagina, los datos y el motor en vivo de Cerebro Liga MX listos para la liguilla (cuartos definidos)',
  phases: [
    { title: 'Trabajo', detail: 'pagina, ensayo retrospectivo, reglas y bajas, motor en vivo' },
    { title: 'Arreglos', detail: 'corrige lo que el ensayo y el motor en vivo encontraron' },
    { title: 'Verificacion', detail: 'pruebas completas, revision visual y auditoria de datos' },
    { title: 'Cierre', detail: 'corrige lo bloqueante que la verificacion encuentre' },
  ],
}

const S = '/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/liguilla'
const R = '/home/user/SA/ligamx'

const INFORME = {
  type: 'object',
  properties: {
    resumen: { type: 'string', description: 'Qué hiciste y qué quedó, en 5 a 12 líneas' },
    cambios: { type: 'array', items: { type: 'object', properties: { archivo: { type: 'string' }, que: { type: 'string' } }, required: ['archivo', 'que'] } },
    hallazgos: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          severidad: { type: 'string', enum: ['bloqueante', 'importante', 'menor'] },
          donde: { type: 'string', description: 'archivo:línea o sección de la página' },
          descripcion: { type: 'string' },
          evidencia: { type: 'string', description: 'comando, salida, ruta de captura o dato que lo demuestra' },
          arreglo_sugerido: { type: 'string' },
          arreglado: { type: 'boolean' },
        },
        required: ['id', 'severidad', 'donde', 'descripcion', 'evidencia', 'arreglado'],
      },
    },
    pruebas: { type: 'string', description: 'Qué pruebas corriste y su resultado exacto (números)' },
    pendientes: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'cambios', 'hallazgos', 'pruebas', 'pendientes'],
}

const COMUN = `
CONTEXTO (proyecto «Cerebro Liga MX», carpeta ${R}; lee primero ${R}/CLAUDE.md y la sección «En curso» de ${R}/ESTADO.md).
Hoy es 23-nov-2026 (noche del domingo 22 en México). La fase regular del Apertura 2026 TERMINÓ. Tabla final: 1 Chivas 33,
2 Cruz Azul 32, 3 América 30, 4 Atlas 28, 5 Toluca 27, 6 Monterrey 27, 7 León 26, 8 Pachuca 25. Cuartos de final (ida 25 y
26 de noviembre, vuelta 28 y 29): C1 Chivas-Pachuca, C2 Cruz Azul-León, C3 América-Monterrey, C4 Atlas-Toluca. La liga
todavía NO publica día, hora ni sede de cada partido y ESPN todavía NO lista esos partidos, así que
salidas/actual.json trae «pendientes» vacío y liguilla.torneo.estado = "definido" con las piernas (ida y vuelta) de cada
serie pronosticadas pero sin id ni fecha. Cuando ESPN los liste (se espera el lunes 23), «pendientes» traerá los
partidos de cuartos con su pronóstico completo y combinadas.

REGLAS DE TRABAJO (obligatorias):
- Responde y escribe todo texto visible en español de México, sin anglicismos innecesarios.
- NO hagas commit, push, stash, checkout, restore ni reset: otros agentes editan otros archivos del mismo árbol al mismo
  tiempo. Toca SÓLO los archivos que este encargo te asigna. Si necesitas un cambio en un archivo ajeno, repórtalo como
  hallazgo con arreglado=false y el arreglo sugerido.
- NO publiques nada (ni Artifact ni base de datos) y no programes tareas.
- Simulaciones: cualquier corrida tuya de produccion.exportar debe llevar «--n-sim 100000» y «--sin-sello» (la de un
  millón gasta 4.4 GB y hay varios agentes a la vez). No corras «python3 pipeline.py auto» ni «vivo.py observar» sobre
  los archivos reales.
- Archivos temporales, capturas y salidas de prueba: sólo en tu carpeta de trabajo dentro de ${S}/ (créala). Para
  capturas usa Playwright ya instalado (require('playwright'); chromium.launch() sin opciones; WebKit también está);
  deviceScaleFactor 1 para capturas que sólo tú miras. Mira tus capturas con la herramienta Read antes de opinar.
- Nada inventado: si un dato no está confirmado, dilo. Los nombres de archivo y los números de tu informe deben ser
  comprobables.
- Tu respuesta final es el informe estructurado; sé concreto (archivo:línea, comando, número).
`

const A_PAGINA = `${COMUN}
ENCARGO A · LA PÁGINA EN EL ESTADO «SIN PARTIDOS PENDIENTES Y CUADRO DEFINIDO».
Archivos tuyos: web/plantilla.html, web/pruebas/prueba.js, web/construir.py, web/LEEME.md, salidas/CONTRATO.md y, en
produccion/exportar.py, SÓLO la función torneo_liguilla y sus auxiliares directos. Carpeta de trabajo: ${S}/A.

Estado actual (compruébalo: «cd ${R}/web && node pruebas/prueba.js» falla en 3 revisiones y luego truena en la
revisión de pestañas de la combinada porque no hay ninguna tarjeta .partido; captura la página a 390 px de ancho y
mírala):
1. Portada: bajo las cuatro probabilidades dice «No hay partidos pendientes por ahora. La página se actualiza cuando se
   programe el siguiente.» (plantilla.html ~línea 1376). Con el cuadro definido debe ANUNCIAR la liguilla: algo como
   «Liguilla definida · Cuartos de final del 25 al 29 de noviembre» con un control que lleve al cuadro (sin
   location.hash). La portada debe seguir cabiendo en la primera pantalla del iPhone (390x664, 360x700, 375x620).
2. «Próximos partidos» sale vacío («Sin partidos por jugar», ~línea 1557) y «Combinada de la jornada» también
   («Todavía no hay combinada»): dos secciones vacías de 740 px cada una ANTES de la liguilla, en el momento más
   importante del torneo. Lo que se quiere: cuando no hay pendientes pero liguilla.torneo trae piernas sin jugar con
   los dos equipos ya definidos, «Próximos partidos» muestra esas piernas (las 4 idas y luego las 4 vueltas) como
   tarjetas compactas de pronóstico, con el mismo lenguaje visual de la página: fase y pierna («Cuartos · Ida»), llave,
   escudos y nombres, marcador más probable en el tablero, barra 1X2 con porcentajes, sede y ventana de fechas
   («25 o 26 nov» mientras no haya fecha exacta; fecha y hora cuando existan) y un control que abra el detalle de esa
   serie en el cuadro. Con una nota honesta: la combinada de cuatro pronósticos de cada partido se publica cuando la
   liga confirme día y hora. La sección «Combinada de la jornada», cuando no hay combinada ni pendientes, no debe ocupar
   una pantalla entera vacía: ocúltala (menú y numeración de secciones coherentes) o déjala en un aviso compacto; elige
   lo que se vea mejor y justifícalo.
3. Las series de cuartos llevan la etiqueta «Proyectada» (~línea 1648: s.real ? 'Definida' : 'Proyectada') aunque el
   cruce ya es definitivo. Agrega en torneo_liguilla un campo booleano por serie (por ejemplo «definida»: los dos
   equipos ya se conocen con certeza, haya o no partidos listados) y úsalo en la página: «Definida» para cuartos hoy;
   semifinales y final siguen «Proyectada» hasta que sus dos equipos se conozcan. Documenta el campo en
   salidas/CONTRATO.md y, si construir.py valida campos, que no truene con datos viejos que no lo traigan.
4. Textos que quedaron viejos con la fase regular terminada (proyeccion.regular_completa = true): por ejemplo «Top 4 =
   cerraría los cuartos de final en casa» (~línea 1918), «Probabilidad de clasificar a la liguilla (los primeros 8) y
   de llegar a cada ronda» con una columna «Liguilla» de puros 100% y 0%, «Sin título en ninguna simulación: …» (son
   los eliminados), la tabla «Tabla final proyectada» (ya es la tabla final), y cualquier «si la tabla termina como se
   espera». Recorre TODA la página a 390 px y a 1440 px buscando condicionales o futuros que ya no aplican y
   corrígelos de forma que dependan de los datos (regular_completa, torneo.estado), no de la fecha.
5. Pruebas (web/pruebas/prueba.js): hoy dependen de que haya partidos pendientes. Hazlas conscientes del estado:
   (a) con 0 pendientes y cuadro definido revisan lo nuevo (anuncio de portada, tarjetas de piernas, etiquetas
   «Definida», sin secciones vacías gigantes); (b) las revisiones de tarjetas de partido, pestañas de combinada, cuenta
   regresiva, etc. se siguen ejecutando SIEMPRE contra un documento construido con datos que sí traen pendientes: usa
   una copia fija de salidas/historial/actual_20261120T0722Z.json (9 pendientes; guárdala en web/pruebas/datos/ para que
   no dependa del historial) con «construir.py --datos … --documento --salida» a un directorio temporal o el mecanismo
   que ya usa la prueba para variantes; (c) investiga la revisión «sin window.claude: la página funciona y lo dice (hora
   con zona; con fecha si no es de hoy)», que hoy falla con «Sin conexión en vivo: datos de las 21:18 h (centro de
   México)»: decide si es defecto de la página o de la prueba y corrige el que sea.
   La prueba debe terminar en verde en Chromium y en WebKit con los datos reales de hoy.
Para ver tu nuevo campo en los datos durante el desarrollo regenera con
«cd ${R} && python3 -m produccion.exportar --n-sim 100000 --sin-sello» (escribe salidas/actual.json; al final el
orquestador lo rehace con el millón) y «python3 web/construir.py». No cambies probabilidades ni cálculos del simulador.
Reglas de la página (CLAUDE.md): fragmento sin doctype, un solo tema oscuro con tokens (ningún color literal fuera de
:root), cada bloque aislado con seguro(), sin location.hash, JavaScript no calcula probabilidades.
Entrega: capturas finales a 390 px de portada, «Próximos partidos» y liguilla en ${S}/A/final/, y el resultado
completo de prueba.js (número de revisiones por motor).`

const B_ENSAYO = `${COMUN}
ENCARGO B · ENSAYO GENERAL DE LA LIGUILLA CON CORTES RETROSPECTIVOS (SÓLO INFORME, NO CORRIJAS NADA).
Trabajas en una copia aislada del repositorio (worktree de git): la carpeta del proyecto en tu copia es el
subdirectorio «ligamx» de tu directorio de trabajo actual (compruébalo con «git rev-parse --show-toplevel»); NO uses
${R} para correr nada. No modifiques archivos versionados: escribe todo en ${S}/B.

Objetivo: descubrir ANTES del miércoles cualquier defecto de datos o de página durante la liguilla, usando la liguilla
real del Clausura 2026, que está completa en datos/partidos.csv (cuartos 2 y 3 de mayo ida, 9 y 10 vuelta; semifinales
13-14 y 16-17 de mayo; final 21 y 24 de mayo de 2026; campeón Cruz Azul; América 3-3 Pumas y Pumas 3-3 América dio un
global 6-6 que avanzó al mejor sembrado).
Para cada corte (hora de la Ciudad de México) corre
  python3 -m produccion.exportar --corte <corte> --n-sim 100000 --sin-sello --salida ${S}/B/corte_<n>.json
  python3 web/construir.py --datos ${S}/B/corte_<n>.json --documento --salida ${S}/B/sitio_<n>
Cortes: (1) el último día de fase regular del Clausura 2026 ya con todo jugado y antes del primer partido de cuartos
(búscalo en datos/partidos.csv), (2) 2026-05-04T12:00 (cuatro idas jugadas), (3) 2026-05-11T12:00 (cuartos cerrados,
antes de semifinales), (4) 2026-05-15T12:00 (idas de semifinal jugadas), (5) 2026-05-18T12:00 (antes de la final),
(6) 2026-05-22T12:00 (entre la ida y la vuelta de la final), (7) 2026-05-25T12:00 (campeón decidido).
Comprueba que exportar con --salida y --sin-sello no escribe en ningún otro archivo (git status antes y después); si
escribe, es un hallazgo.
En cada corte revisa, contra los resultados reales:
- liguilla.torneo: estado, siembra, series «real», resultados de las piernas jugadas, global, quién avanza (regla:
  empate global en cuartos y semifinales avanza el mejor sembrado; en la final tiempos extra y penales), resiembra en
  semifinales (el mejor sembrado vivo contra el peor), quién cierra en casa, campeón decidido en el corte 7.
- proyeccion.campeon: equipos eliminados con probabilidad 0; después de una ida, que la probabilidad de avanzar refleje
  el marcador de la ida (compárala contra un cálculo independiente tuyo con Poisson a partir de lam_l y lam_v de la
  vuelta y la regla del empate; tolerancia 2 a 3 puntos).
- pendientes: ¿traen los partidos de liguilla que faltan?, ¿la tarjeta de cada partido dice que es de liguilla, de qué
  serie, qué pierna y cómo va el global (qué necesita cada equipo en la vuelta)?, ¿las combinadas y mercados de una
  vuelta tienen sentido?, ¿«combinada_jornada» agrupa bien los partidos de una ronda?
- desempeno, ultimos_resultados, avisos y notas: textos que hablen de «jornada» o de fase regular cuando ya es liguilla.
- La página de cada corte: captúrala a 390 px (página completa en tiras) y a 1440 px (portada y liguilla), MÍRALA y
  anota todo lo que se vea mal, vacío, contradictorio o confuso: portada (cuenta regresiva, favorito; en el corte 7 debe
  celebrar al campeón), «Próximos partidos», combinada, cuadro (mini-cuadro en celular y espejo ≥1400 px), detalle de
  serie con piernas jugadas, «Camino al título», tabla, «Última jornada», errores de consola.
Clasifica cada hallazgo (bloqueante = dato falso o página rota durante la liguilla; importante = confunde o se ve mal;
menor) con evidencia (ruta del JSON y clave, o ruta de la captura) y un arreglo sugerido con archivo y función. Di
también qué SÍ funciona bien, en el resumen. No propongas cambiar el modelo ni las probabilidades salvo que haya un
error demostrable.`

const C_REGLAS = `${COMUN}
ENCARGO C · REGLAS, HORARIOS, SEDES Y BAJAS PARA LOS CUARTOS DE FINAL (investigación en la web).
Archivos tuyos: config/torneo.json y config/actualidad.json (y nada más). Carpeta de trabajo: ${S}/C.
Privacidad: en ninguna búsqueda ni petición a sitios externos incluyas nombres de personas del proyecto, correos ni
rutas; usa sólo términos futbolísticos.
1. Regla de menores (config/torneo.json → ajustes_tabla): al 10-nov les faltaban minutos a Toluca, Puebla, Santos,
   Querétaro, León, Tigres y Monterrey; quien no cumpla 1,170 minutos pierde 3 puntos. Confirma con la tabla oficial de
   menores (ligamx.net) o con al menos dos medios serios si TODOS cumplieron y si la tabla final oficial quedó sin
   descuentos (León 26, Monterrey 27, Toluca 27 clasificados). Si alguno fue sancionado es un hallazgo BLOQUEANTE:
   repórtalo con fuentes, no cambies la tabla. Anota el resultado en ajustes_tabla (campo nuevo «verificado» con fecha
   y fuentes).
2. Horarios y sedes de los ocho partidos de cuartos: búscalos (ligamx.net, ESPN, Récord, Mediotiempo, TUDN, Fox). Si
   ya son oficiales, regístralos en config/torneo.json → liguilla, en un campo nuevo «horarios_cuartos» (lista de
   {llave, pierna, local, visitante, fecha_local, hora_local (centro de México), estadio, fuente}); si todavía no, deja
   escrito cuándo se anuncian. Confirma en particular la SEDE DE CRUZ AZUL como local (Estadio Banorte o Ciudad de los
   Deportes; ver «dudas» en torneo.json) y si algún estadio cambia. Verifica también las fechas de semifinales y final
   y la condición exacta para recorrer la final al 24 y 27 de diciembre por la Copa Intercontinental de Toluca;
   actualiza «dudas» (quita las resueltas, deja las abiertas con lo que se sabe).
3. Bajas de los 8 clasificados para la ida de cuartos (config/actualidad.json; respeta EXACTAMENTE el esquema que ya
   tiene: equipos.<equipo>.{tecnico, lesionados:[{jugador, motivo, tipo, fuente, fecha_fuente}], nota},
   cotejo_suspendidos, no_confirmado, fuentes; lee cómo lo usa produccion/exportar.py antes de editar): lesionados,
   suspendidos (expulsados en la Jornada 17 y suspensiones ya ganadas; las amarillas acumuladas se borran al empezar
   la liguilla), dudas y regresos. Cada dato con fuente y fecha; lo que venga de una sola fuente dudosa va como
   tipo «duda» o en no_confirmado. Para los 10 eliminados deja el equipo con una nota de «eliminado» (o como el esquema
   lo permita) sin borrar la estructura. Actualiza la fecha de corte del archivo.
Al terminar valida que nada truena: «cd ${R} && python3 -m produccion.exportar --n-sim 100000 --sin-sello --salida
${S}/C/prueba.json» y «python3 -m pytest produccion/pruebas -q -x» (di los números).
En el informe pon, además, una tabla breve por equipo con sus bajas confirmadas y los horarios encontrados (o que no
hay), con las URL de las fuentes en «evidencia» de cada hallazgo o en el resumen.`

const D_VIVO = `${COMUN}
ENCARGO D · EL MOTOR EN VIVO EN PARTIDOS DE LIGUILLA (series a dos partidos).
Archivos tuyos: vivo.py, produccion/en_juego.py, produccion/pruebas/test_vivo.py, produccion/VIVO.md y
salidas/vivo_ejemplo.json. Carpeta de trabajo: ${S}/D. NO edites web/plantilla.html ni produccion/simulador.py ni
produccion/exportar.py (si hace falta, repórtalo con el arreglo sugerido).
ANTES de empezar copia a ${S}/D/respaldo/ los archivos reales salidas/vivo.json, salidas/vivo_relevo.json,
salidas/vivo_ultimo_n.txt, salidas/vivo_eventos.jsonl y salidas/vivo_version.txt, y AL TERMINAR déjalos idénticos
(compruébalo con sha256sum). Prefiere siempre opciones que escriban en tu carpeta.
Lee produccion/VIVO.md completo (sobre todo §6, el procedimiento del día de partido) y el código. Desde el miércoles 25
el motor va a seguir partidos de cuartos de final en vivo y nunca se ha usado en liguilla con datos reales. Comprueba,
reproduciendo partidos reales del Clausura 2026 con «python3 vivo.py repetir …» (mira su ayuda; ids en
datos/partidos.csv: vuelta de cuartos Pumas 3-3 América 401870508 con ida 3-3 —global 6-6, avanzó Pumas por mejor
posición—, vuelta de cuartos Chivas 2-0 Tigres 401870507 tras perder 3-1 la ida, vuelta de semifinal Chivas 1-2 Cruz
Azul 401872571, y la vuelta de la final Pumas 1-2 Cruz Azul 401873246):
1. ¿El documento en vivo trae el estado de la SERIE (marcador de la ida, global al momento, quién avanza ahora mismo y
   con qué probabilidad, qué le falta a cada equipo) y la probabilidad de campeón recalculada con el marcador en curso
   (simular(en_juego=…)) durante la liguilla? ¿La «tabla al momento» se comporta bien cuando no hay fase regular?
2. Regla del empate global (mejor sembrado avanza en cuartos y semifinales; sin gol de visitante, sin tiempos extra) y
   la final (tiempos extra y penales): ¿el modelo en juego y los textos la aplican bien? ¿Qué pasa con los estados de
   ESPN de tiempos extra y penales (STATUS_EXTRA_TIME, STATUS_SHOOTOUT, STATUS_FINAL_AET, STATUS_FINAL_PEN,
   STATUS_END_OF_REGULATION, etc.) y con minutos > 90?
3. ¿«vivo.py plan», «una-vez» y «observar» reconocen partidos de liguilla del calendario (fase distinta de regular),
   dos partidos el mismo día en horarios separados, y el cambio de «día de partido» a las 04:00 de México?
4. La ida y la vuelta: durante la IDA, ¿la probabilidad de avanzar de la serie considera que falta la vuelta? Durante
   la VUELTA, ¿toma el marcador real de la ida?
5. Cierre: tras el final de una vuelta, ¿el documento dice quién avanzó y el estado pasa a terminado?
Corrige en TUS archivos lo que esté mal (con pruebas nuevas en produccion/pruebas/test_vivo.py) y corre
«python3 -m pytest produccion/pruebas/test_vivo.py -q» y luego «python3 -m pytest produccion/pruebas -q» (di los
números). Si la página (web/plantilla.html) necesita mostrar algo que el documento ya trae o debería traer, descríbelo
como hallazgo con la forma exacta del dato (clave y ejemplo). Deja en ${S}/D/ un documento en vivo de ejemplo de una
vuelta de cuartos a medio partido (vivo_vuelta_ejemplo.json) para que la página pueda probarse con él. Actualiza
produccion/VIVO.md con lo que cambie y con una sección corta «Liguilla» (qué cambia el día de partido).`

phase('Trabajo')
const [a, b, c, d] = await parallel([
  () => agent(A_PAGINA, { label: 'A · página sin pendientes y cuadro definido', phase: 'Trabajo', schema: INFORME }),
  () => agent(B_ENSAYO, { label: 'B · ensayo retrospectivo de la liguilla', phase: 'Trabajo', schema: INFORME, isolation: 'worktree' }),
  () => agent(C_REGLAS, { label: 'C · menores, horarios, sedes y bajas', phase: 'Trabajo', schema: INFORME }),
  () => agent(D_VIVO, { label: 'D · motor en vivo con series', phase: 'Trabajo', schema: INFORME }),
])

const abiertos = [a, b, c, d].filter(Boolean).flatMap(r => r.hallazgos || []).filter(h => !h.arreglado)
log(`Trabajo: ${[a, b, c, d].filter(Boolean).length} de 4 informes; ${abiertos.length} hallazgos sin arreglar (${abiertos.filter(h => h.severidad === 'bloqueante').length} bloqueantes)`)

phase('Arreglos')
let arreglos = null
const porArreglar = abiertos.filter(h => h.severidad !== 'menor')
if (porArreglar.length) {
  arreglos = await agent(`${COMUN}
ENCARGO E · CORREGIR LO QUE ENCONTRARON EL ENSAYO DE LA LIGUILLA Y EL MOTOR EN VIVO.
Ya terminaron los otros agentes; ahora eres el ÚNICO que edita el árbol ${R} (puedes tocar cualquier archivo del
proyecto salvo config/actualidad.json; sigue sin hacer commit ni publicar). Carpeta de trabajo: ${S}/E.
Resúmenes de lo que hicieron:
A (página): ${a ? a.resumen : 'SIN INFORME (el agente no terminó: revisa git status y diff de web/ y termina su encargo si quedó a medias)'}
B (ensayo, sólo informe; sus salidas están en ${S}/B): ${b ? b.resumen : 'SIN INFORME'}
C (reglas y bajas): ${c ? c.resumen : 'SIN INFORME'}
D (motor en vivo; ejemplo en ${S}/D/vivo_vuelta_ejemplo.json): ${d ? d.resumen : 'SIN INFORME'}

Hallazgos abiertos que debes resolver (bloqueantes primero; si uno no procede, explica por qué con evidencia):
${JSON.stringify(porArreglar, null, 1)}

Hallazgos menores abiertos (arréglalos sólo si son de una línea y sin riesgo):
${JSON.stringify(abiertos.filter(h => h.severidad === 'menor'), null, 1)}

Forma de trabajar: reproduce cada hallazgo antes de tocar nada (los cortes retrospectivos se rehacen con
«python3 -m produccion.exportar --corte <corte> --n-sim 100000 --sin-sello --salida ${S}/E/corte_<n>.json» y la página con
«python3 web/construir.py --datos … --documento --salida ${S}/E/sitio_<n>»), corrige en la causa (exportador o
simulador si el dato es falso; plantilla si sólo es presentación; JavaScript no calcula probabilidades), agrega una
prueba por cada defecto de datos (produccion/pruebas) y una revisión en web/pruebas/prueba.js por cada defecto de
página cuando sea razonable, y vuelve a capturar para comprobar. No cambies el modelo campeón ni las reglas de
modelo.mejora. Si un arreglo exige cambiar el contrato, actualiza salidas/CONTRATO.md.
Al final corre TODO: «python3 -m pytest modelo/pruebas produccion/pruebas -q» y «cd web && node pruebas/prueba.js»
(Chromium y WebKit) y deja salidas/actual.json regenerado con
«python3 -m produccion.exportar --n-sim 100000 --sin-sello» + «python3 web/construir.py». Informa los números exactos.`,
    { label: 'E · arreglos del ensayo y del vivo', phase: 'Arreglos', schema: INFORME })
} else {
  log('Sin hallazgos importantes abiertos: se omite la etapa de arreglos')
}

phase('Verificacion')
const estado = `
Estado: los agentes A (página), C (reglas y bajas), D (motor en vivo) y E (arreglos) ya terminaron y nadie más edita el
árbol. Resúmenes — A: ${a ? a.resumen : 'sin informe'} — C: ${c ? c.resumen : 'sin informe'} — D: ${d ? d.resumen : 'sin informe'} — E: ${arreglos ? arreglos.resumen : 'no hizo falta o sin informe'}.
NO corrijas nada en esta etapa: sólo verifica e informa (arreglado=false en todo). «git diff» y «git status» te dicen
qué cambió respecto al último commit.`
const verif = (await parallel([
  () => agent(`${COMUN}${estado}
ENCARGO V1 · PRUEBAS COMPLETAS Y REVISIÓN ADVERSARIAL DEL DIFF. Carpeta de trabajo: ${S}/V1.
1. Corre y reporta números exactos: «cd ${R} && python3 -m pytest modelo/pruebas produccion/pruebas -q» y
   «cd ${R}/web && node pruebas/prueba.js» (Chromium y WebKit). Si algo falla, di qué y por qué (bloqueante).
2. Lee TODO el diff («git diff» de ligamx/) buscando activamente errores: lógica de etiquetas definida/proyectada,
   casos límite (serie con ida jugada y vuelta pendiente, final decidida, pendientes vacíos, piernas sin fecha, datos
   viejos sin el campo nuevo), colores literales fuera de :root, uso de location.hash, bloques sin seguro(), JavaScript
   calculando probabilidades, pruebas que se saltan en silencio o que ya no revisan lo que revisaban, cambios al
   contrato sin documentar, y cualquier cambio en simulador/exportador que altere probabilidades (compara
   proyeccion.campeon del commit HEAD contra el actual: no deben moverse más que el ruido de Monte Carlo de 100,000
   simulaciones, ±0.3 puntos).
3. Verifica que config/actualidad.json y config/torneo.json siguen siendo JSON válido con el esquema que el exportador
   espera, y que salidas/vivo.json, vivo_relevo.json y vivo_version.txt (107) no quedaron alterados por las pruebas
   del motor en vivo (el respaldo está en ${S}/D/respaldo/).`,
    { label: 'V1 · pruebas y diff', phase: 'Verificacion', schema: INFORME }),
  () => agent(`${COMUN}${estado}
ENCARGO V2 · REVISIÓN VISUAL EXIGENTE EN CELULAR Y ESCRITORIO. Carpeta de trabajo: ${S}/V2.
Eres un director de arte y un aficionado que abre la página la noche en que se definió la liguilla. Construye la página
real («cd ${R} && python3 web/construir.py --documento --salida web/» ya lo hace la prueba; usa web/documento.html) y
captura con Playwright en Chromium y WebKit: iPhone 390x844 (página completa en tiras de 1500 px y la primera
pantalla sola), 360x700, y escritorio 1440x900 (portada, «Próximos partidos», liguilla con el cuadro espejo). Abre el
detalle de una serie tocando una llave y captúralo. Además construye dos estados de la liguilla con cortes
retrospectivos del Clausura 2026 («python3 -m produccion.exportar --corte 2026-05-04T12:00 --n-sim 100000 --sin-sello
--salida ${S}/V2/c2.json», otro con 2026-05-25T12:00, y «python3 web/construir.py --datos … --documento --salida
${S}/V2/sitio_x») y captúralos a 390 px; y un estado en vivo incrustando ${S}/D/vivo_vuelta_ejemplo.json si existe
(«construir.py --vivo … --documento --salida ${S}/V2/sitio_vivo» junto con --datos del corte que corresponda).
MIRA cada captura y reporta, con la ruta de la captura como evidencia: cosas encimadas o cortadas, secciones vacías o
demasiado altas, textos contradictorios con los datos (por ejemplo «proyectada» en algo definido, «si la tabla
termina…» con la tabla ya terminada, fechas ya pasadas), jerarquía débil en «Próximos partidos» (¿se entiende en 3
segundos quién juega, cuándo, dónde y qué pronostica el modelo?), contraste insuficiente, saltos de línea feos en
nombres largos (Atlético San Luis, Cruz Azul), tablero ilegible, errores de consola, y diferencias entre Chromium y
WebKit. Compara contra la calidad del resto de la página: lo nuevo no puede verse como un parche. Bloqueante = roto o
falso; importante = se ve mal o confunde; menor = pulido.`,
    { label: 'V2 · revisión visual', phase: 'Verificacion', schema: INFORME }),
  () => agent(`${COMUN}${estado}
ENCARGO V3 · AUDITORÍA INDEPENDIENTE DE LOS DATOS DE LA LIGUILLA. Carpeta de trabajo: ${S}/V3.
Sin fiarte del código del proyecto, comprueba salidas/actual.json (regenerado con 100,000 simulaciones; la versión de
un millón del commit HEAD se ve con «git show HEAD:ligamx/salidas/actual.json»):
1. Tabla final y siembra: recalcula la tabla desde datos/partidos.csv (Apertura 2026, fase regular: puntos, diferencia,
   goles a favor y los desempates de config/torneo.json → desempate_tabla) y compárala con «tabla» y con
   liguilla.torneo.siembra; presta atención al triple empate en 25 puntos (Pachuca, Tijuana, Santos) y al empate en 27
   (Toluca, Monterrey): ¿el orden sale del criterio correcto? Contrasta con la tabla que publica ESPN
   (https://site.api.espn.com/apis/v2/sports/soccer/mex.1/standings) si responde.
2. Cruces y localías: 1-8, 2-7, 3-6, 4-5; la IDA se juega en casa del peor sembrado y la VUELTA en casa del mejor;
   estadio correcto de cada local (config y «estadios»).
3. Probabilidad de avanzar de cada serie: recalcúlala tú con Poisson independiente (o con la matriz de marcadores si
   el JSON la trae) a partir de lam_l y lam_v de cada pierna y la regla «empate global avanza el mejor sembrado»;
   compárala con la publicada (tolerancia 2 a 3 puntos; si la diferencia es mayor explica la causa: correlación,
   incertidumbre de parámetros, etc.). Revisa que «global probable» y los marcadores más probables de cada pierna sean
   coherentes con sus lambdas, y que p_local+p_empate+p_visitante = 1.
4. Campeón: suma 1; p_semifinal de cada equipo = su probabilidad de avanzar en cuartos; p_final ≤ p_semifinal;
   coherencia de la ruta proyectada (resiembra en semifinales) con cuadro_mas_probable.
5. Textos de la página generados desde datos (notas honestas, avisos): ¿alguno afirma algo que ya no es cierto con la
   fase regular terminada?
Reporta cada discrepancia con los dos números y la clave del JSON.`,
    { label: 'V3 · auditoría de datos', phase: 'Verificacion', schema: INFORME }),
])).filter(Boolean)

const hallV = verif.flatMap(r => r.hallazgos || [])
const graves = hallV.filter(h => h.severidad !== 'menor')
log(`Verificación: ${verif.length} de 3 informes; ${hallV.length} hallazgos (${hallV.filter(h => h.severidad === 'bloqueante').length} bloqueantes, ${hallV.filter(h => h.severidad === 'importante').length} importantes)`)

phase('Cierre')
let cierre = null
if (graves.length) {
  cierre = await agent(`${COMUN}
ENCARGO F · CIERRE: CORREGIR LO QUE ENCONTRÓ LA VERIFICACIÓN.
Eres el único que edita el árbol ${R} (cualquier archivo del proyecto; sin commit ni publicar). Carpeta: ${S}/F.
Hallazgos de la verificación (bloqueantes e importantes; reproduce cada uno antes de corregir y, si no procede, explica
por qué con evidencia):
${JSON.stringify(graves, null, 1)}
Menores (sólo si son de una línea y sin riesgo):
${JSON.stringify(hallV.filter(h => h.severidad === 'menor'), null, 1)}
Corrige en la causa, agrega la prueba o revisión que evite que vuelva a pasar, vuelve a capturar lo visual a 390 px en
Chromium y WebKit y MÍRALO. Al final corre TODO y da números exactos: «python3 -m pytest modelo/pruebas
produccion/pruebas -q» y «cd web && node pruebas/prueba.js». Deja salidas/actual.json regenerado con
«python3 -m produccion.exportar --n-sim 100000 --sin-sello» + «python3 web/construir.py».`,
    { label: 'F · cierre', phase: 'Cierre', schema: INFORME })
} else {
  log('La verificación no encontró nada bloqueante ni importante')
}

return { a, b, c, d, arreglos, verificacion: verif, cierre }
