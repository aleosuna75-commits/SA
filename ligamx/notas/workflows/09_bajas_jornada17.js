export const meta = {
  name: 'ligamx-bajas-jornada17',
  description: 'Cerebro Liga MX: bajas (lesionados, dudas y suspendidos reportados) de los 18 equipos para la Jornada 17, con fuente y fecha',
  phases: [
    { title: 'Investigar', detail: 'tres agentes, tres partidos cada uno; solo fuentes publicadas y recientes' },
  ],
}

const GRUPOS = [
  { clave: 'viernes', partidos: [
    { local: 'Puebla', visitante: 'Atlético San Luis', cuando: 'viernes 20-nov, 19:00', deducidos: 'ninguno' },
    { local: 'Juárez', visitante: 'Atlas', cuando: 'viernes 20-nov, 21:00', deducidos: 'Atlas: Adonis Frías' },
    { local: 'Tijuana', visitante: 'Atlante', cuando: 'viernes 20-nov, 21:10', deducidos: 'Atlante: Aarón Quirós y Walter Portales' },
  ] },
  { clave: 'sabado', partidos: [
    { local: 'Pachuca', visitante: 'Toluca', cuando: 'sábado 21-nov, 16:50', deducidos: 'Toluca: Helinho' },
    { local: 'Santos', visitante: 'León', cuando: 'sábado 21-nov, 17:00', deducidos: 'León: José Rodríguez y Juan Guevara' },
    { local: 'Pumas', visitante: 'Monterrey', cuando: 'sábado 21-nov, 19:00', deducidos: 'Pumas: Pedro Vite; Monterrey: Ricardo Chávez' },
  ] },
  { clave: 'cierre', partidos: [
    { local: 'Tigres', visitante: 'América', cuando: 'sábado 21-nov, 21:00', deducidos: 'América: Érick Sánchez' },
    { local: 'Chivas', visitante: 'Cruz Azul', cuando: 'domingo 22-nov, 17:07', deducidos: 'ninguno' },
    { local: 'Querétaro', visitante: 'Necaxa', cuando: 'domingo 22-nov, 19:10', deducidos: 'Querétaro: Guillermo Allison, Eduardo Pérez y Daniel Parra; Necaxa: Raúl Martínez' },
  ] },
]

const ESQUEMA = {
  type: 'object',
  properties: {
    equipos: { type: 'array', items: { type: 'object', properties: {
      equipo: { type: 'string', description: 'nombre EXACTO como aparece en la lista de partidos' },
      tecnico: { type: 'string', description: 'director técnico actual, o cadena vacía si no se confirmó' },
      bajas: { type: 'array', items: { type: 'object', properties: {
        jugador: { type: 'string' }, motivo: { type: 'string', description: 'texto corto' },
        tipo: { type: 'string', enum: ['lesion', 'duda', 'seleccion', 'otro'] },
        fuente: { type: 'string', description: 'URL' }, fecha_fuente: { type: 'string', description: 'AAAA-MM-DD' } },
        required: ['jugador', 'motivo', 'tipo', 'fuente', 'fecha_fuente'] } },
      suspendidos_prensa: { type: 'array', items: { type: 'object', properties: {
        jugador: { type: 'string' }, motivo: { type: 'string' }, fuente: { type: 'string' }, fecha_fuente: { type: 'string' } },
        required: ['jugador', 'motivo', 'fuente', 'fecha_fuente'] } },
      nota: { type: 'string', description: 'una línea: qué tan completa y reciente es la información de este equipo' } },
      required: ['equipo', 'tecnico', 'bajas', 'suspendidos_prensa', 'nota'] } },
    fuentes: { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, titulo: { type: 'string' }, fecha: { type: 'string' } }, required: ['url', 'titulo', 'fecha'] } },
    no_confirmado: { type: 'string' },
  },
  required: ['equipos', 'fuentes', 'no_confirmado'],
}

function instruccion(g) {
  const lista = g.partidos.map(p => `- ${p.local} vs ${p.visitante} (${p.cuando}, hora del centro de México). Suspendidos que el sistema ya deduce de las tarjetas: ${p.deducidos}.`).join('\n')
  return `Tarea de investigación acotada para el proyecto Cerebro Liga MX. Hoy es 18 de noviembre de 2026. Del 20 al 22 de noviembre se juega la Jornada 17 (última de la fase regular) del Apertura 2026 de la Liga MX. Investiga las BAJAS de los seis equipos de estos tres partidos:
${lista}

Para cada equipo devuelve: director técnico actual; lesionados y dudas (con motivo corto); y los SUSPENDIDOS que reporta la prensa o la Comisión Disciplinaria para ese partido (sirven para cotejar: los datos de tarjetas de ESPN a veces vienen incompletos; incluye también los que el sistema ya deduce si la fuente los confirma). La Fecha FIFA terminó el 17 de noviembre: los convocados a selección ya no son baja, salvo que una fuente diga que volvieron lesionados o que no llegan (eso va como «duda» u «otro»).
Regla dura: nada inventado. Cada dato sale de una fuente publicada (sitio oficial del club o de la Liga MX / Comisión Disciplinaria, ESPN, Récord, Mediotiempo, TUDN, Fox Sports, Telediario, medios locales serios, FotMob o similares) con fecha del 10 de noviembre de 2026 en adelante; para lesiones largas vale una fuente reciente que confirme que el jugador sigue fuera. Si de un equipo no encuentras nada confiable y reciente, deja sus listas vacías y dilo en su «nota». No rellenes con plantillas de otros años ni con suposiciones, y no des por lesionado a alguien que ya volvió a jugar.
Presupuesto: sé económico. Empieza por lo que cubre varios equipos a la vez (la lista de suspendidos de la Jornada 17, notas de «bajas» o «previa» de cada partido) y no pases de unas 25 búsquedas o lecturas por partido. Usa WebSearch y WebFetch; si un sitio bloquea, prueba otro. No incluyas datos personales de nadie en las búsquedas más allá de nombres de jugadores y clubes. No escribas ni modifiques ningún archivo del proyecto: tu resultado es sólo el objeto estructurado. Los nombres de equipo deben ir EXACTAMENTE como en la lista de arriba.`
}

phase('Investigar')
const res = await parallel(GRUPOS.map(g => () =>
  agent(instruccion(g), { label: 'bajas-' + g.clave, phase: 'Investigar', schema: ESQUEMA, agentType: 'general-purpose' })
    .then(r => ({ grupo: g.clave, r }))))
const ok = res.filter(Boolean).filter(x => x.r)
const faltan = GRUPOS.map(g => g.clave).filter(c => !ok.some(x => x.grupo === c))
if (faltan.length) log('grupos sin resultado: ' + faltan.join(', '))
return { grupos: ok, faltan }
