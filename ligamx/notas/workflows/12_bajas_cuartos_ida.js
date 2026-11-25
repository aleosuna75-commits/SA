export const meta = {
  name: 'ligamx-bajas-cuartos-ida',
  description: 'Cerebro Liga MX: bajas, dudas y suspendidos de los 8 equipos para las idas de cuartos, con verificación de cada fuente',
  phases: [
    { title: 'Investigar', detail: 'dos agentes: idas del miércoles y del jueves' },
    { title: 'Verificar', detail: 'un verificador por grupo relee cada fuente y descarta lo que no sostiene' },
  ],
}

const GRUPOS = [
  { clave: 'miercoles', partidos: [
    { local: 'Toluca', visitante: 'Atlas', cuando: 'miércoles 25-nov, 19:00' },
    { local: 'Monterrey', visitante: 'América', cuando: 'miércoles 25-nov, 21:10' },
  ] },
  { clave: 'jueves', partidos: [
    { local: 'Pachuca', visitante: 'Chivas', cuando: 'jueves 26-nov, 19:00' },
    { local: 'León', visitante: 'Cruz Azul', cuando: 'jueves 26-nov, 21:10' },
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
  return g.partidos.map(p => `- ${p.local} vs ${p.visitante} (${p.cuando}, hora del centro de México), ida de cuartos de final.`).join('\n')
}

function instruccion(g, actuales) {
  return `Tarea de investigación acotada para el proyecto Cerebro Liga MX. Hoy es miércoles 25 de noviembre de 2026 (mañana en México). Se juegan las idas de cuartos de final del Apertura 2026 de la Liga MX. Investiga las BAJAS de los cuatro equipos de estos partidos:
${previo(g)}

Lo que el proyecto tiene hoy (config/actualidad.json, investigado el 23-nov) para estos equipos:
${actuales}

Para cada equipo devuelve: director técnico; bajas vigentes para la ida (lesionados, dudas, suspendidos; tipo «suspension» para los suspendidos), con motivo corto, URL y fecha de la fuente; y en «ya_no_son_baja» a quienes figuraban como baja o duda y una fuente reciente dice que ya están disponibles, entrenaron con normalidad o fueron convocados. Busca en especial el reporte de la Comisión Disciplinaria de la Jornada 17 (fmf.mx / ligamx.net, publicado el martes 24) y cuántos partidos recibió cada expulsado de estos equipos (por ejemplo el portero Hugo González de Toluca y Salcedo de Monterrey, si aplica); ponlo en «disciplinaria».
Regla dura: nada inventado. Cada dato sale de una fuente publicada (club o Liga MX / FMF, ESPN, Récord, Mediotiempo, TUDN, Fox Sports, Excélsior, medios locales serios, FotMob o similares) con fecha del 22 de noviembre de 2026 en adelante (para lesiones largas vale una fuente reciente que confirme que sigue fuera). Si de un equipo no encuentras nada confiable y reciente, deja sus listas vacías y dilo en «nota». No rellenes con suposiciones.
Presupuesto: económico, unas 25 búsquedas o lecturas por partido como máximo; empieza por las previas de cada partido y las notas de convocados. Usa WebSearch y WebFetch (si un sitio bloquea, prueba otro). No incluyas datos personales de nadie en las búsquedas más allá de nombres de jugadores y clubes. No escribas ni modifiques ningún archivo: tu resultado es sólo el objeto estructurado. Los nombres de equipo deben ir EXACTAMENTE como en la lista de arriba.`
}

phase('Investigar')
const res = await pipeline(GRUPOS,
  g => agent(instruccion(g, args && args[g.clave] ? args[g.clave] : '(no disponible)'), { label: `bajas · ${g.clave}`, phase: 'Investigar', schema: ESQUEMA }),
  (r, g) => r ? agent(`Verificación adversarial para el proyecto Cerebro Liga MX (25-nov-2026). Otro agente investigó las bajas de estos partidos de ida de cuartos de la Liga MX:
${previo(g)}
Su resultado:
${JSON.stringify(r).slice(0, 30000)}

Tu trabajo: relee (WebFetch) la fuente citada de CADA baja, de cada «ya_no_son_baja» y del dato de la Disciplinaria. Conserva sólo lo que la fuente dice de verdad y con fecha del 22-nov en adelante; corrige el motivo, el tipo o la fecha si la fuente dice otra cosa; si una fuente no carga, busca otra que lo confirme y cámbiala, o descarta el dato. Si encuentras de paso una baja importante que faltó (titular lesionado o suspendido para la ida), agrégala con su fuente. Devuelve el mismo objeto ya depurado, y en «no_confirmado» explica qué descartaste y por qué. No escribas archivos.`, { label: `verificar · ${g.clave}`, phase: 'Verificar', schema: ESQUEMA }) : null,
)
return { miercoles: res[0], jueves: res[1] }
