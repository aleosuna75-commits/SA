export const meta = {
  name: 'ligamx-momios-en-sellos',
  description: 'Cerebro Liga MX: guardar los momios en cada pronostico sellado y calificar al mercado junto al modelo, con revision independiente',
  phases: [
    { title: 'Implementar', detail: 'sellos con momios, desempeno con el mercado pareado, pagina y pruebas' },
    { title: 'Revisar', detail: 'revision independiente: fugas, compatibilidad con sellos viejos, pruebas en los dos navegadores' },
  ],
}

const RAIZ = '/home/user/SA/ligamx'
const SCR = '/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad'

const COMUN = `
Contexto: proyecto Cerebro Liga MX en ${RAIZ} (pronosticos de la Liga MX con pagina publicada). Antes de cada partido el sistema «sella» su pronostico (${RAIZ}/produccion/sellos.py → ${RAIZ}/salidas/sellos.jsonl; el sello oficial de un partido es el ultimo anterior a su inicio) y despues lo califica (${RAIZ}/salidas/desempeno.json, campo «desempeno» de ${RAIZ}/salidas/actual.json, que la pagina ${RAIZ}/web/plantilla.html muestra en su seccion de desempeño; contrato en ${RAIZ}/salidas/CONTRATO.md). Los momios de ESPN de cada partido pendiente ya llegan a los datos (columnas ml_l, ml_e, ml_v, total_linea, over, under de datos/partidos.csv y «momios» de cada partido pendiente en actual.json) y se actualizan en cada corrida de «python3 pipeline.py auto». En la validacion historica el mercado de cierre le gana a todos los modelos propios (log-loss 1.003 contra 1.022), y la pagina lo dice. Las probabilidades sin margen se calculan con el metodo de Shin que ya existe en ${RAIZ}/modelo/base.py (prob_shin).
Reglas que no se rompen: sin fugas (lo que se guarda en un sello es solo lo conocido al sellar); nada inventado; el JavaScript de la pagina no calcula probabilidades ni metricas (solo da formato a lo que exporta Python); la pagina es un fragmento con un solo tema oscuro de tokens, cada bloque aislado con seguro(), y se prueba SIEMPRE en Chromium y en WebKit: «PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node web/pruebas/prueba.js chromium» y «PLAYWRIGHT_BROWSERS_PATH=${SCR}/pw node web/pruebas/prueba.js webkit» (~2 min cada una; hoy pasan 230 revisiones por motor).
No hagas commit ni push ni publiques nada. Presupuesto de tokens limitado: lee los archivos grandes por secciones. Puede que una corrida anterior de esta tarea haya quedado a medias: revisa «git -C /home/user/SA status --short» antes de empezar y continua desde ahi.
`

const INFORME = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    cambios: { type: 'array', items: { type: 'string' } },
    archivos: { type: 'array', items: { type: 'string' } },
    pruebas: { type: 'string', description: 'baterias corridas y su resultado literal' },
    pendientes: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'cambios', 'archivos', 'pruebas', 'pendientes'],
}

const REVISION = {
  type: 'object',
  properties: {
    veredicto: { type: 'string', enum: ['listo', 'listo_con_arreglos', 'no_listo'] },
    resumen: { type: 'string' },
    hallazgos: { type: 'array', items: { type: 'object', properties: {
      gravedad: { type: 'string', enum: ['alta', 'media', 'baja'] }, que: { type: 'string' }, que_hice: { type: 'string' } },
      required: ['gravedad', 'que', 'que_hice'] } },
    pruebas: { type: 'string' },
    archivos: { type: 'array', items: { type: 'string' } },
  },
  required: ['veredicto', 'resumen', 'hallazgos', 'pruebas', 'archivos'],
}

phase('Implementar')
const impl = await agent(`Eres quien implementa una mejora acotada en Cerebro Liga MX. ${COMUN}
Objetivo: que la comparacion «modelo contra mercado» se acumule con pronosticos sellados de verdad, partido a partido, empezando por la Jornada 17 (20 a 22 de noviembre de 2026).
1. SELLOS: cada sello nuevo guarda, cuando el partido tiene momios al momento de sellar, un campo «mercado» con los momios tal como estaban (ml_l, ml_e, ml_v, total_linea, over, under, proveedor si se conoce), las probabilidades 1X2 sin margen por Shin (p_l, p_e, p_v) y el margen. Sin momios, el campo es null. Los sellos ya escritos (sin el campo) deben seguir leyendose y calificandose igual. Cuida la regla que omite sellos identicos: un cambio de momios SI debe producir un sello nuevo (el oficial es el ultimo previo al partido), pero sin escribir uno por cada corrida cuando nada cambio.
2. DESEMPEÑO: al calificar, ademas de lo que ya se calcula para el modelo, calcula para el mercado sellado, SOLO en los partidos calificados que tienen mercado en su sello oficial: n, log-loss, Brier, RPS y acierto del favorito; y la diferencia pareada modelo menos mercado en log-loss con su error estandar (null si n < 2), mas el log-loss del modelo en ese mismo subconjunto. Que quede por partido en ultimos_resultados (probabilidades del mercado sellado y su log-loss) y acumulado en desempeno. No cambies nada de lo que ya existe en esos objetos (solo añade campos) y actualiza exportar.validar y salidas/CONTRATO.md.
3. PAGINA: en la seccion de desempeño (y en la tarjeta de cada resultado calificado, si ya muestra el pronostico sellado) muestra la comparacion con texto franco: cuantos partidos, log-loss del modelo y del mercado en los mismos partidos, la diferencia con su error estandar, y una frase que diga que con pocos partidos no se puede concluir nada (por ejemplo mientras n < 30). Si no hay ningun partido con mercado sellado, una linea que diga desde cuando se empezo a guardar. Mismo lenguaje visual que el resto; nada de colores sueltos.
4. PRUEBAS: añade pruebas en produccion/pruebas/ (sello con y sin momios, sello viejo sin el campo, calificacion pareada con un caso calculado a mano, momios invalidos o en vivo que deben descartarse igual que hace modelo/datos.py) y revisiones en web/pruebas/prueba.js. Cierra con «python3 -m pytest produccion/pruebas -q», «python3 -m produccion.exportar» (~75 s), «python3 web/construir.py» y las dos baterias de la pagina en verde.
Nota: hoy solo hay 1 partido calificado y su sello no tiene momios; los 9 partidos pendientes si tienen momios, asi que al exportar deben salir 9 sellos nuevos con «mercado». Eso es lo esperado: dilo en el informe.`,
  { label: 'implementar', phase: 'Implementar', schema: INFORME })

phase('Revisar')
const rev = await agent(`Eres un revisor independiente y esceptico de un cambio que otro agente acaba de hacer en Cerebro Liga MX; si encuentras defectos, los arreglas. ${COMUN}
El cambio: cada pronostico sellado guarda ahora los momios del momento y su probabilidad sin margen, y el desempeño califica al mercado junto al modelo en los mismos partidos. Informe de quien lo hizo:
${impl ? JSON.stringify(impl, null, 1) : '(el agente no termino: mira «git -C /home/user/SA diff --stat»; completa lo que falte de forma minima o revierte lo que este a medias, y dilo)'}

Revisa con «git -C /home/user/SA diff» y con tus propios guiones (en ${SCR}/rev_momios/):
1. Fugas y tiempos: ¿el mercado que queda en el sello oficial es de antes del inicio del partido? ¿Puede colarse un momio capturado con el partido en juego o ya terminado (ESPN a veces devuelve como «cierre» un momio en vivo; modelo/datos.py tiene una regla para detectarlos)? ¿Que pasa si un partido se sella despues de empezado?
2. Calculo: reproduce a mano, para 2 o 3 partidos pendientes, las probabilidades de Shin y el margen a partir de los momios guardados; y con resultados inventados (solo en tu guion, sin tocar datos) el log-loss, Brier y RPS del mercado y la diferencia pareada con su error estandar.
3. Compatibilidad: sellos viejos sin el campo, partidos sin momios, salidas/sellos.jsonl no reescrito ni duplicado sin motivo (cuenta cuantos sellos nuevos salen en dos exportaciones seguidas sin cambios: la segunda debe dar 0), exportar.validar y el contrato.
4. Pagina: que no calcule nada en JavaScript, que el texto sea franco y correcto (signo de la diferencia, error estandar, aviso de pocos partidos), que no rompa en celular (WebKit iPhone 13) ni con desempeno vacio o sin mercado, y que no haya cambiado nada mas de la pagina.
5. Que no se haya tocado el modelo, las probabilidades selladas del modelo ni la simulacion (compara salidas/actual.json antes y despues en proyeccion.campeon y en el 1X2 de los pendientes; el «antes» esta en git).
Cierra con «python3 -m pytest produccion/pruebas -q», «python3 -m produccion.exportar», «python3 web/construir.py» y las dos baterias de la pagina; reporta el resultado literal. Veredicto: «listo», «listo_con_arreglos» (di cuales hiciste) o «no_listo» (y en ese caso deja el repo en un estado coherente y explica que falta).`,
  { label: 'revisar', phase: 'Revisar', schema: REVISION })

return { impl, rev }
