export const meta = {
  name: 'ligamx-bajas-cuartos-vuelta',
  description: 'Cerebro Liga MX: bajas, dudas y suspendidos de los 8 equipos para las vueltas de cuartos, con verificación de cada fuente',
  phases: [
    { title: 'Investigar', detail: 'dos agentes: vueltas del sábado y del domingo' },
    { title: 'Verificar', detail: 'un verificador por grupo relee cada fuente y descarta lo que no sostiene' },
  ],
}

const GRUPOS = [
  { clave: 'sabado', partidos: [
    { local: 'Atlas', visitante: 'Toluca', cuando: 'sábado 28-nov, 19:00; en la ida ganó Toluca 2-0' },
    { local: 'América', visitante: 'Monterrey', cuando: 'sábado 28-nov, 21:10; la ida fue Monterrey 0-0 América y Ricardo Chávez, de Monterrey, fue expulsado al minuto 11' },
  ] },
  { clave: 'domingo', partidos: [
    { local: 'Chivas', visitante: 'Pachuca', cuando: 'domingo 29-nov, 19:07; en la ida ganó Pachuca 2-1 y Oussama Idrissi, de Pachuca, fue expulsado al 90+3' },
    { local: 'Cruz Azul', visitante: 'León', cuando: 'domingo 29-nov, 21:00; en la ida ganó Cruz Azul 4-0 en León' },
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
        tipo: { type: 'string', enum: ['lesion', 'duda', 'seleccion', 'suspension', 'otro'] },
        fuente: { type: 'string', description: 'URL' }, fecha_fuente: { type: 'string', description: 'AAAA-MM-DD' } },
        required: ['jugador', 'motivo', 'tipo', 'fuente', 'fecha_fuente'] } },
      ya_no_son_baja: { type: 'array', description: 'jugadores que antes figuraban como baja o duda y una fuente reciente dice que ya están disponibles o fueron convocados', items: { type: 'object', properties: {
        jugador: { type: 'string' }, motivo: { type: 'string' }, fuente: { type: 'string' }, fecha_fuente: { type: 'string' } },
        required: ['jugador', 'motivo', 'fuente', 'fecha_fuente'] } },
      nota: { type: 'string', description: 'una línea: qué tan completa y reciente es la información de este equipo' } },
      required: ['equipo', 'tecnico', 'bajas', 'ya_no_son_baja', 'nota'] } },
    disciplinaria: { type: 'string', description: 'lo que dice el reporte de la Comisión Disciplinaria de la Jornada 17 sobre jugadores de estos equipos (partidos de suspensión), con URL; cadena vacía si no se encontró' },
    fuentes: { type: 'array', items: { type: 'object', properties: { url: { type: 'string' }, titulo: { type: 'string' }, fecha: { type: 'string' } }, required: ['url', 'titulo', 'fecha'] } },
    no_confirmado: { type: 'string' },
  },
  required: ['equipos', 'disciplinaria', 'fuentes', 'no_confirmado'],
}

function previo(g) {
  return g.partidos.map(p => `- ${p.local} vs ${p.visitante} (${p.cuando}, hora del centro de México), vuelta de cuartos de final.`).join('\n')
}

function instruccion(g, actuales) {
  return `Tarea de investigación acotada para el proyecto Cerebro Liga MX. Hoy es viernes 27 de noviembre de 2026 (madrugada en México). Ya se jugaron las idas de cuartos de final del Apertura 2026 de la Liga MX; el sábado 28 y el domingo 29 se juegan las vueltas. Investiga las BAJAS de los cuatro equipos de estos partidos:
${previo(g)}

Lo que el proyecto tiene hoy (config/actualidad.json, investigado el 25-nov para las idas) para estos equipos:
${actuales}

Para cada equipo devuelve: director técnico; bajas vigentes para la vuelta (lesionados, dudas, suspendidos; tipo «suspension» para los suspendidos), con motivo corto, URL y fecha de la fuente; y en «ya_no_son_baja» a quienes figuraban como baja o duda y una fuente reciente dice que ya están disponibles, entrenaron con normalidad o fueron convocados. Busca en especial los reportes de la Comisión Disciplinaria de la Jornada 17 y de las idas de cuartos (fmf.mx / ligamx.net) y cuántos partidos recibió cada expulsado: Hugo González (Toluca) y Carlos Salcedo (Monterrey), expulsados en la J17, que ya cumplieron un partido en la ida, y Ricardo Chávez (Monterrey) y Oussama Idrissi (Pachuca), expulsados en las idas; ponlo en «disciplinaria». Incluye también a los que salieron lesionados o con molestias en las idas.
Regla dura: nada inventado. Cada dato sale de una fuente publicada (club o Liga MX / FMF, ESPN, Récord, Mediotiempo, TUDN, Fox Sports, Excélsior, medios locales serios, FotMob o similares) con fecha del 25 de noviembre de 2026 en adelante (para lesiones largas vale una fuente reciente que confirme que sigue fuera). Si de un equipo no encuentras nada confiable y reciente, deja sus listas vacías y dilo en «nota». No rellenes con suposiciones.
Presupuesto: económico, unas 25 búsquedas o lecturas por partido como máximo; empieza por las previas de cada partido y las notas de convocados. Usa WebSearch y WebFetch (si un sitio bloquea, prueba otro). No incluyas datos personales de nadie en las búsquedas más allá de nombres de jugadores y clubes. No escribas ni modifiques ningún archivo: tu resultado es sólo el objeto estructurado. Los nombres de equipo deben ir EXACTAMENTE como en la lista de arriba.`
}

phase('Investigar')
const res = await pipeline(GRUPOS,
  g => agent(instruccion(g, args && args[g.clave] ? args[g.clave] : '(no disponible)'), { label: `bajas · ${g.clave}`, phase: 'Investigar', schema: ESQUEMA }),
  (r, g) => r ? agent(`Verificación adversarial para el proyecto Cerebro Liga MX (27-nov-2026). Otro agente investigó las bajas de estos partidos de vuelta de cuartos de la Liga MX:
${previo(g)}
Su resultado:
${JSON.stringify(r).slice(0, 30000)}

Tu trabajo: relee (WebFetch) la fuente citada de CADA baja, de cada «ya_no_son_baja» y del dato de la Disciplinaria. Conserva sólo lo que la fuente dice de verdad y con fecha del 25-nov en adelante; corrige el motivo, el tipo o la fecha si la fuente dice otra cosa; si una fuente no carga, busca otra que lo confirme y cámbiala, o descarta el dato. Si encuentras de paso una baja importante que faltó (titular lesionado o suspendido para la vuelta), agrégala con su fuente. Devuelve el mismo objeto ya depurado, y en «no_confirmado» explica qué descartaste y por qué. No escribas archivos.`, { label: `verificar · ${g.clave}`, phase: 'Verificar', schema: ESQUEMA }) : null,
)
return { sabado: res[0], domingo: res[1] }
