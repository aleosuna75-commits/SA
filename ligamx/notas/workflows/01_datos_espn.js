export const meta = {
  name: 'ligamx-datos-espn',
  description: 'Cerebro Liga MX: base historica desde ESPN (descarga reanudable e incremental) con verificacion independiente y mapa del codigo previo',
  phases: [
    { title: 'Datos ESPN', detail: 'descarga historica y tablas' },
    { title: 'Verificacion', detail: 'auditoria independiente de la base' },
    { title: 'Mapa', detail: 'lecciones del codigo previo del repo' },
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
- Objetivo final: pagina web con pronosticos por partido (marcador, resultado, 4 picks tipo parlay del mismo partido), probabilidad de campeon y pronostico de cada serie de la liguilla, usando el MEJOR modelo que salga de una validacion walk-forward. Todo debe quedar AUTOMATIZADO y mejorar solo partido a partido y jornada a jornada (despues de cada partido se actualizan datos, se recalibra y se reevalua).
- Apertura 2026: 18 equipos, 17 jornadas, 153 partidos; 143 jugados. Faltan: Queretaro-Monterrey (14-nov, pendiente) y la Jornada 17 (20-22 nov). Despues viene la liguilla.
- Nombres CANONICOS de los 18 equipos (en los archivos van CON acentos): América, Atlas, Atlante, Atlético San Luis, Cruz Azul, Chivas, Juárez, León, Monterrey, Necaxa, Pachuca, Puebla, Pumas, Querétaro, Santos, Tigres, Tijuana, Toluca. En ESPN: Guadalajara=Chivas, Pumas UNAM=Pumas, Tigres UANL=Tigres, FC Juarez=Juárez, Atletico de San Luis=Atlético San Luis. ESPN ids: América 227, Atlante 226, Atlas 216, Atlético San Luis 15720, Cruz Azul 218, Juárez 17851, Chivas 219, León 228, Monterrey 220, Necaxa 229, Pachuca 234, Puebla 231, Pumas 233, Querétaro 222, Santos 225, Tigres 232, Tijuana 10125, Toluca 223.
- RED (ya probado desde esta maquina): la API de ESPN funciona SIN autenticacion: https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=2026&limit=1000 devuelve un anio calendario completo (los rangos AAAAMMDD-AAAAMMDD fallan con 400; dates=AAAAMMDD de un solo dia si funciona); .../summary?event=<id> trae boxscore (tiros, tiros a puerta, corners, faltas, tarjetas, posesion, penales), keyEvents (goles y tarjetas con minuto y periodo, sustituciones), rosters (titulares, posicion, formacion), odds/pickcenter (momios), gameInfo (sede, asistencia); .../teams; y https://site.api.espn.com/apis/v2/sports/soccer/mex.1/standings. Cada evento del scoreboard trae season.slug con la fase (torneo-apertura, apertura---quarterfinals, ---semifinals, ---finals, ---reclassification, etc.). La respuesta viene en gzip: usa Accept-Encoding gzip (curl --compressed). Un User-Agent con la palabra "bot" recibe 403; usa uno de navegador. Se cortes: maximo ~5 peticiones por segundo, con reintentos y espera exponencial.
- REGLAS: no hagas git commit ni push. No toques archivos fuera de la carpeta que se te asigna (salvo leer). Nunca pongas datos personales del usuario en peticiones externas. NUNCA inventes datos: lo que no se pueda verificar va como vacio con una nota. Texto y comentarios en espanol. Crea las carpetas que falten.
`
const OUT = `Devuelve (salida estructurada): resumen (5-10 lineas con lo esencial y cifras), archivos (rutas absolutas creadas o modificadas), hallazgos (hechos verificados importantes para las siguientes fases, uno por elemento), pendientes (lo que no se pudo hacer o verificar y por que).`

const pDatos = `${CTX}
TAREA: construir la base historica de partidos de Liga MX desde la API de ESPN. Carpeta asignada: /home/user/SA/ligamx/datos/.
1) Escribe /home/user/SA/ligamx/datos/espn_descarga.py (libreria estandar + pandas/numpy; reanudable; cache en /home/user/SA/ligamx/datos/cache/espn/; concurrencia <= 6 hilos y <= 5 req/s; reintentos). CLI: "calendario", "resumenes [--desde AAAA]", "tablas", "todo" y "actualizar" (INCREMENTAL y rapido, para correr despues de cada partido: vuelve a bajar el scoreboard del anio en curso, baja los resumenes de partidos recien terminados o que aun no tenian estadisticas/eventos, regenera las tablas; idempotente; imprime un resumen JSON de que cambio: partidos nuevos jugados, partidos reprogramados). Pasos:
   a) calendario: por cada anio desde el mas antiguo con eventos (prueba desde 2002) hasta 2026, baja scoreboard?dates=AAAA&limit=1000 y guardalo comprimido.
   b) resumenes: para cada partido JUGADO baja summary?event=<id> y guarda un extracto COMPACTO comprimido por partido (no el JSON completo): estadisticas por equipo del boxscore, keyEvents (goles con minuto, minuto anadido, periodo, tipo gol/penal/autogol, anotador; tarjetas amarillas y rojas con minuto y jugador; sustituciones con minuto, quien entra y quien sale), rosters (jugador id y nombre, titular, posicion, formacion), odds/pickcenter (momios 1X2, linea de total y momios over/under, proveedor), sede, asistencia, arbitro si viene. Prioriza 2010-2026; despues los anios anteriores.
   c) tablas en /home/user/SA/ligamx/datos/:
      - partidos.csv (una fila por partido, tambien los PROGRAMADOS del Apertura 2026): id, fecha_utc (ISO), fecha_local (fecha en America/Mexico_City), anio, torneo ("Apertura 2026", "Clausura 2026"...), fase (regular | repechaje | cuartos | semifinal | final), pierna (1 o 2 en series de ida y vuelta, deducida por orden cronologico del cruce; vacio en regular), estado (jugado | programado | pospuesto | cancelado), local, visitante (nombres canonicos; los equipos historicos conservan un nombre unico y estable: Morelia, Veracruz, Chiapas, Mazatlán, Lobos BUAP, Tecos, San Luis, Dorados, Leones Negros, Atlante...), gl, gv (marcador al final del tiempo REGLAMENTARIO de 90 min), gl_et, gv_et (si hubo tiempos extra: marcador tras 120), pen_l, pen_v (tanda de penales, si hubo), gl_ht, gv_ht (medio tiempo, de los eventos de gol), estadio, ciudad, asistencia, arbitro, y por lado (_l y _v): tiros, tiros_puerta, corners, faltas, amarillas, rojas, posesion, fueras_lugar, atajadas, penales_tirados, penales_gol; momios en decimal: ml_l, ml_e, ml_v, total_linea, over, under, proveedor; banderas tiene_stats, tiene_eventos, tiene_alineaciones, tiene_momios.
      - goles.csv (partido_id, minuto, anadido, periodo, equipo, jugador, tipo), tarjetas.csv (partido_id, minuto, periodo, equipo, jugador, tipo amarilla|roja|segunda_amarilla), alineaciones.csv (partido_id, equipo, jugador_id, jugador, titular, posicion, minuto_entra, minuto_sale, formacion) y calendario_pendiente.json (partidos programados del Apertura 2026 con id, fecha_utc, fecha_local, local, visitante, estadio).
      - tabla_apertura2026.csv: tabla general calculada desde partidos.csv (PJ, G, E, P, GF, GC, DG, PTS, y lo mismo de local y de visita) comparada con el endpoint standings de ESPN.
   d) /home/user/SA/ligamx/datos/COBERTURA.md: por torneo, cuantos partidos hay y que porcentaje tiene cada bloque (stats, eventos, alineaciones, momios); desde que temporada es confiable cada bloque; diccionario de columnas; y la CONCILIACION contra /home/user/SA/historico_ligamx.csv (5,014 partidos 2010 a ago-2026: fecha,local,visitante,gl,gv,fase; ese archivo usa el marcador tras tiempos extra en finales) y contra /home/user/SA/historico_ht_ligamx.csv (medios tiempos 2018-2024): cuantos coinciden, lista de discrepancias y cual fuente crees correcta.
2) La descarga de resumenes son miles de peticiones: lanzala en segundo plano (nohup, log a archivo) y revisa el avance; no bloquees mas de 9 minutos por comando. No termines hasta tener AL MENOS 2012-2026 completo y las tablas generadas; si 2002-2011 no alcanza en ~45 min, dejalo anotado en pendientes con el comando para completarlo.
3) Verifica tu propio trabajo: sin duplicados, gl_ht<=gl, 153 partidos por torneo regular (171 en Apertura 2019; menos en el Clausura 2020 cancelado por pandemia), fases de liguilla con conteos correctos, fechas locales correctas (los partidos nocturnos caen en el dia UTC siguiente), y que la tabla del Apertura 2026 coincida con ESPN.
Agrega /home/user/SA/ligamx/.gitignore con datos/cache/ (los caches crudos no van al repositorio; las tablas CSV si).
${OUT}`

const pVerifDatos = (prev) => `${CTX}
TAREA: verificacion INDEPENDIENTE y esceptica de la base de datos que otro agente acaba de construir en /home/user/SA/ligamx/datos/ (script espn_descarga.py, partidos.csv, goles.csv, tarjetas.csv, alineaciones.csv, calendario_pendiente.json, tabla_apertura2026.csv, COBERTURA.md). Lo que reporto el otro agente:
${JSON.stringify(prev).slice(0, 6000)}
Tu trabajo es intentar ROMPERLA, no confiar en ella:
1) Muestra aleatoria de 40 partidos repartidos entre temporadas y fases (incluye finales con tiempos extra y penales): vuelve a pedir el summary crudo a ESPN y compara campo por campo contra las tablas (marcador 90', medio tiempo, corners, tarjetas, tiros, titulares, momios, fecha local, sede).
2) Integridad: duplicados, ids repetidos, gl_ht>gl, equipos con nombre no canonico o duplicado por acentos (lista TODOS los nombres distintos con su conteo y primer y ultimo anio), partidos sin fecha, conteo por torneo y fase (8 cuartos, 4 semis, 2 finales por torneo; repechajes y play-in donde existieron), piernas de liguilla bien asignadas y local/visitante correctos en cada pierna.
3) Marcador reglamentario vs tiempos extra/penales: revisa TODAS las finales y series desde 2010 que se definieron en tiempos extra o penales.
4) Conciliacion con /home/user/SA/historico_ligamx.csv y /home/user/SA/historico_ht_ligamx.csv: recalculala tu mismo; clasifica cada discrepancia (fecha corrida por zona horaria, marcador distinto, partido faltante, equipo mal mapeado).
5) Apertura 2026: reconstruye la tabla desde partidos.csv y comparala con el endpoint standings de ESPN equipo por equipo; verifica que los partidos pendientes y sus sedes sean correctos.
6) Sesgos de cobertura que importan para modelar: si los momios o las estadisticas faltan mas en ciertos equipos o temporadas; y si los momios parecen de APERTURA o de CIERRE, de que casa, y si para partidos FUTUROS (programados) ESPN ya publica momios.
7) Prueba el comando "actualizar": debe ser idempotente (dos corridas seguidas no cambian nada) y rapido.
Corrige lo que encuentres (edita el script y regenera las tablas con el cache) y agrega a COBERTURA.md una seccion "Verificacion independiente" que diga que se probo, que fallaba y que quedo corregido.
${OUT}`

const pMapa = `${CTX}
TAREA (solo lectura del codigo previo; escribe unicamente tu nota): en la RAIZ del repo /home/user/SA existe una version anterior del Cerebro Liga MX hecha en agosto: ARQUITECTURA.md, DOMINIO.md, cerebro_ligamx_2026.py (motor Dixon-Coles), generar.py, proyeccion.py, config/jornadas.json, analisis/ (credibilidad.md, backtest_k.py), desempeno/, golden/, docs/ (sitio estatico), historico_ligamx.csv, historico_ht_ligamx.csv, leagues_cup_2026.csv. El proyecto nuevo NO esta obligado a construir sobre ella (el usuario pidio "encuentra lo mejor"); el motor original solo entrara a la competencia de modelos como linea base. Lee todo y escribe /home/user/SA/ligamx/notas/mapa_repo_previo.md con:
1) como replicar EXACTAMENTE el modelo original como linea base (parametros, capas de lambdas_partido, credibilidad Z=w^p/(w^p+k^p) de generar.py, corte sin fuga) y una receta minima para llamarlo desde otro modulo;
2) la matematica reutilizable: joint de mitades por adelgazamiento de Poisson (_joint_mitades), catalogo de mercados (_catalogo_legs), probabilidad conjunta exacta (_prob_conjunta) y el hallazgo de legs que se implican logicamente;
3) proyeccion.py: supuestos de desempate y de liguilla, y que le falta (incertidumbre de parametros, tiempos extra, criterios oficiales);
4) el desempeno sellado de las jornadas ya publicadas (aciertos y Brier por jornada, convencion de Brier) para poder mostrar el historial;
5) decisiones tomadas con el usuario que conviene respetar (sellado de pronosticos, JS no calcula probabilidades, honestidad de datos, Atlante conserva su historia 2010-2014 pero no hereda de Mazatlan) y errores o limitaciones que veas (archivo:linea).
Se concreto y breve (maximo ~250 lineas).
${OUT}`

const [cadena, mapa] = await parallel([
  () => agent(pDatos, { label: 'datos-espn', phase: 'Datos ESPN', schema: R })
        .then(d => agent(pVerifDatos(d), { label: 'verifica-datos', phase: 'Verificacion', schema: R }).then(v => ({ datos: d, verificacion: v }))),
  () => agent(pMapa, { label: 'mapa-repo-previo', phase: 'Mapa', schema: R }),
])
return { datos: cadena, mapa }
