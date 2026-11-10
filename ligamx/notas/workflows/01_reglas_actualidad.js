export const meta = {
  name: 'ligamx-reglas-y-actualidad',
  description: 'Cerebro Liga MX: formato oficial de la liguilla Apertura 2026 y actualidad de planteles (lesionados, suspendidos, tecnicos) con fuentes',
  phases: [
    { title: 'Reglas', detail: 'dos investigadores y un juez' },
    { title: 'Actualidad', detail: 'tres grupos de equipos y un editor' },
  ],
}

const R = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    archivos: { type: 'array', items: { type: 'string' } },
    hallazgos: { type: 'array', items: { type: 'string' } },
    pendientes: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'archivos', 'hallazgos', 'pendientes'],
}

const CTX = `
CONTEXTO COMUN (leelo completo)
- Proyecto nuevo "Cerebro Liga MX" en /home/user/SA/ligamx/ (repo git /home/user/SA). Hoy es 2026-11-10.
- Objetivo final: pagina con pronosticos por partido, probabilidad de campeon y pronostico de cada serie de la liguilla del Apertura 2026 de la Liga MX. Todo quedara automatizado y se actualizara jornada a jornada.
- Apertura 2026: 18 equipos, 17 jornadas; van 143 de 153 partidos. Faltan: Queretaro-Monterrey (14-nov, pendiente) y la Jornada 17 (20-22 nov). Despues viene la liguilla.
- Nombres CANONICOS de los 18 equipos (en los archivos van CON acentos): América, Atlas, Atlante, Atlético San Luis, Cruz Azul, Chivas, Juárez, León, Monterrey, Necaxa, Pachuca, Puebla, Pumas, Querétaro, Santos, Tigres, Tijuana, Toluca.
- RED: tienes WebSearch y WebFetch (cargalas con ToolSearch si no las ves). Con curl: ligamx.net responde 200; las paginas HTML de es.wikipedia.org responden 200 pero su API (w/api.php, rest_v1) responde 429 desde esta IP: no insistas. La API publica de ESPN funciona sin autenticacion y sin la palabra "bot" en el User-Agent: https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=2026&limit=1000 (anio completo, con --compressed) y .../summary?event=<id> (keyEvents con tarjetas y minuto; rosters con titulares).
- REGLAS: no hagas git commit ni push. No toques archivos fuera de la carpeta que se te asigna (salvo leer). Nunca pongas datos personales del usuario en peticiones externas. NUNCA inventes: lo que no se pueda verificar va vacio o como duda, con nota. Texto en espanol. Crea las carpetas que falten.
`
const OUT = `Devuelve (salida estructurada): resumen (5-10 lineas con lo esencial), archivos (rutas absolutas creadas o modificadas), hallazgos (hechos verificados importantes, uno por elemento, con su fuente), pendientes (lo que no se pudo verificar y por que).`

const pReglas = (angulo, archivo) => `${CTX}
TAREA: investigar el FORMATO OFICIAL de la fase final (liguilla) del torneo Apertura 2026 de la Liga MX y los criterios de desempate. Angulo de busqueda asignado: ${angulo}
Necesito, con fuente (URL, titulo, fecha) y cita corta para cada punto:
1) Cuantos equipos clasifican y como: clasificacion directa, y si existe o no Play-In/repechaje en el Apertura 2026 (hubo cambios para la temporada 2026-27) con su formato exacto si existe.
2) Criterios de desempate de la TABLA GENERAL en orden (puntos, diferencia de goles, goles a favor, goles de visitante, tabla de cocientes, fair play, sorteo... tal como los fija el reglamento de competencia vigente).
3) Liguilla: rondas, ida y vuelta, quien cierra en casa, criterio si el global queda empatado en cuartos y semifinales (posicion en la tabla o tiempos extra/penales), regla de gol de visitante (vigente o no), resiembra o cuadro fijo en semifinales, y como se define la final si queda empatada (tiempos extra y penales).
4) Calendario: fechas de cuartos (ida y vuelta), semifinales y final del Apertura 2026; y la fecha FIFA de noviembre de 2026.
5) Reglas nuevas 2026-27 que afecten pronosticos (extranjeros, menores, descenso/ascenso, sedes: que equipos comparten el Estadio Banorte).
Escribe tus hallazgos en ${archivo}, marcando lo CONFIRMADO (fuente oficial o dos medios) y lo NO CONFIRMADO.
${OUT}`

const pReglasJuez = (a, b) => `${CTX}
TAREA: dos investigadores independientes averiguaron el formato de la liguilla del Apertura 2026. Sus reportes:
A = ${JSON.stringify(a).slice(0, 5000)}
B = ${JSON.stringify(b).slice(0, 5000)}
Lee sus notas completas en /home/user/SA/ligamx/notas/reglas_oficial.md y /home/user/SA/ligamx/notas/reglas_medios.md. Donde coincidan y haya fuente, acepta. Donde discrepen o falte fuente, investiga tu mismo hasta resolverlo (o dejalo como duda). Escribe /home/user/SA/ligamx/config/torneo.json con esta forma (claves ASCII):
{ "torneo": "Apertura 2026", "equipos": 18, "jornadas": 17, "clasifican_directo": 0, "play_in": {"existe": false, "detalle": ""}, "desempate_tabla": ["puntos", "..."], "liguilla": {"rondas": ["cuartos","semifinal","final"], "ida_vuelta": true, "cierra_en_casa": "mejor posicion", "empate_global_cuartos_semis": "", "gol_visitante": false, "resiembra_semifinal": true, "final_empate": "", "fechas": {"cuartos_ida": [], "cuartos_vuelta": [], "semis_ida": [], "semis_vuelta": [], "final_ida": [], "final_vuelta": []}}, "fecha_fifa_noviembre": [], "reglas_nuevas": [], "fuentes": [{"url": "", "titulo": "", "fecha": "", "sustenta": ""}], "dudas": [] }
Cada regla debe estar sustentada por al menos una fuente listada; lo no confirmado va en "dudas" con el valor mas probable en el campo. Fechas no oficiales: lista vacia y explicalo en "dudas". Ademas revisa en los datos historicos como se resolvieron los empates globales en las ultimas liguillas (para confirmar el criterio vigente) y anotalo.
${OUT}`

const GRUPOS = [
  ['América', 'Cruz Azul', 'Atlante', 'Pumas', 'Toluca', 'Pachuca'],
  ['Chivas', 'Atlas', 'Monterrey', 'Tigres', 'Santos', 'Querétaro'],
  ['Tijuana', 'Necaxa', 'León', 'Atlético San Luis', 'Juárez', 'Puebla'],
]
const pActualidad = (g, i) => `${CTX}
TAREA: actualidad de planteles al 2026-11-10 para estos 6 equipos: ${g.join(', ')}.
Para CADA equipo investiga (WebSearch/WebFetch; ESPN, Mediotiempo, Record, TUDN, Milenio, El Universal, Claro Sports, sitios y redes oficiales de los clubes):
- director tecnico actual y desde cuando (si cambio durante el Apertura 2026: fecha y a quien sustituyo);
- lesionados vigentes: jugador, posicion, lesion, tiempo estimado de baja o fecha de regreso, si se pierde la Jornada 17 (20-22 nov) y/o la liguilla;
- suspendidos para su proximo partido (roja en su ultimo juego o acumulacion de amarillas) y sanciones largas;
- seleccionados en la fecha FIFA de noviembre que pudieran volver tocados; altas o bajas relevantes recientes;
- racha y contexto en una linea (p. ej. "5 sin perder", "ya eliminado", "pelea el liderato").
Cruza las suspensiones con ESPN: el ultimo partido de cada equipo esta en scoreboard?dates=2026&limit=1000 y sus tarjetas en summary?event=<id> (keyEvents).
Importancia de cada baja: indica si el jugador es titular habitual (cuenta en cuantos de los ultimos 8 partidos de su equipo fue titular segun rosters de ESPN summary) para poder ponderar su ausencia.
Cada dato lleva fuente_url, fuente_fecha (fecha de publicacion) y confianza (alta: fuente oficial o dos medios; media: un medio; baja: rumor o nota de mas de 3 semanas sin confirmacion). Si no encuentras nada verificable de un rubro, deja la lista vacia: NO inventes.
Escribe /home/user/SA/ligamx/config/actualidad_parts/grupo${i + 1}.json: { "fecha_corte": "2026-11-10", "equipos": { "<nombre canonico>": { "dt": {"nombre": "", "desde": "", "nota": ""}, "lesionados": [{"jugador": "", "posicion": "", "lesion": "", "regreso_estimado": "", "se_pierde_j17": null, "se_pierde_liguilla": null, "titular_ultimos8": null, "fuente_url": "", "fuente_fecha": "", "confianza": ""}], "suspendidos": [{"jugador": "", "posicion": "", "motivo": "", "partidos": 1, "titular_ultimos8": null, "fuente_url": "", "fuente_fecha": "", "confianza": ""}], "dudas": [], "contexto": "" } } }
${OUT}`

const pActualidadJuez = (parts) => `${CTX}
TAREA: tres agentes investigaron lesionados, suspendidos y tecnicos. Sus reportes: ${JSON.stringify(parts).slice(0, 7000)}
Lee /home/user/SA/ligamx/config/actualidad_parts/grupo1.json, grupo2.json y grupo3.json. Actua como editor esceptico:
1) Verifica por tu cuenta TODAS las suspensiones (cruzalas con las tarjetas rojas del ultimo partido de cada equipo en ESPN summary keyEvents) y al menos 2 lesiones por equipo que tengan impacto (abre la fuente citada; si no dice lo que se afirma, baja la confianza o elimina el dato).
2) Elimina duplicados, normaliza nombres de equipos a los canonicos y descarta lo que no tenga fuente.
3) Escribe /home/user/SA/ligamx/config/actualidad.json con la misma forma por equipo (los 18 equipos, aunque alguno quede con listas vacias), mas "fecha_corte", "metodo" (como se verifico) y "advertencias" (lista).
4) Escribe /home/user/SA/ligamx/notas/como_actualizar_actualidad.md: receta corta y repetible (que buscar, donde, como cruzar con ESPN) para que este paso se repita automaticamente antes de cada jornada y de cada partido de liguilla.
${OUT}`

const [reglas, actualidad] = await parallel([
  () => parallel([
          () => agent(pReglas('oficial: reglamento de competencia 2026-27 y comunicados de ligamx.net y la FMF', '/home/user/SA/ligamx/notas/reglas_oficial.md'), { label: 'reglas-oficial', phase: 'Reglas', schema: R }),
          () => agent(pReglas('medios: ESPN, Mediotiempo, Record, TUDN, Claro Sports y Wikipedia', '/home/user/SA/ligamx/notas/reglas_medios.md'), { label: 'reglas-medios', phase: 'Reglas', schema: R }),
        ]).then(([a, b]) => agent(pReglasJuez(a, b), { label: 'reglas-juez', phase: 'Reglas', schema: R })),
  () => parallel(GRUPOS.map((g, i) => () => agent(pActualidad(g, i), { label: `actualidad-g${i + 1}`, phase: 'Actualidad', schema: R })))
        .then(parts => agent(pActualidadJuez(parts.filter(Boolean)), { label: 'actualidad-editor', phase: 'Actualidad', schema: R })),
])
return { reglas, actualidad }
