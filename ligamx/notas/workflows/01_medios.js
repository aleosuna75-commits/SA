export const meta = {
  name: 'ligamx-medios',
  description: 'Cerebro Liga MX: datos y fotos libres de los 16 estadios, videos cortos, fotos de ambiente y escudos, con revision de licencias',
  phases: [
    { title: 'Medios', detail: 'estadios por grupo, videos y escudos' },
    { title: 'Revision', detail: 'licencias, calidad y manifiesto unico' },
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
- Proyecto nuevo "Cerebro Liga MX" en /home/user/SA/ligamx/ (repo git /home/user/SA). Hoy es 2026-11-10. Se construira una pagina web cinematografica (tipo editorial deportivo, movil primero) con pronosticos de la Liga MX; necesita fotos reales de estadios, escudos y algun video.
- Nombres CANONICOS de los 18 equipos y su slug: América=ame, Atlas=ats, Atlante=ate, Atlético San Luis=asl, Cruz Azul=caz, Chivas=chi, Juárez=jua, León=leo, Monterrey=mty, Necaxa=nec, Pachuca=pac, Puebla=pue, Pumas=pum, Querétaro=qro, Santos=san, Tigres=tig, Tijuana=tij, Toluca=tol. ESPN ids: ame 227, ate 226, ats 216, asl 15720, caz 218, jua 17851, chi 219, leo 228, mty 220, nec 229, pac 234, pue 231, pum 233, qro 222, san 225, tig 232, tij 10125, tol 223.
- RED: la API de Wikimedia (w/api.php, rest_v1) responde 429 desde esta IP: NO la uses. Las paginas HTML normales (commons.wikimedia.org/wiki/File:..., /wiki/Category:..., es.wikipedia.org/wiki/...) SI responden 200 con curl usando un User-Agent de navegador; tambien tienes WebSearch y WebFetch (cargalas con ToolSearch si no las ves). Las imagenes y videos originales se bajan de upload.wikimedia.org. Espacia las peticiones (1 cada 2 s) y no insistas ante un 429.
- LICENCIAS: solo material con licencia libre comprobada en su pagina File: de Commons (CC0, dominio publico, CC BY, CC BY-SA). Nada de "fair use", agencias, television, clubes ni YouTube.
- REGLAS: no hagas git commit ni push. No toques archivos fuera de /home/user/SA/ligamx/web/ (salvo leer). Nunca pongas datos personales del usuario en peticiones externas. NUNCA inventes datos ni atribuciones. Texto en espanol. Crea las carpetas que falten. Hay Pillow y ffmpeg (con libx264).
`
const OUT = `Devuelve (salida estructurada): resumen (5-10 lineas), archivos (rutas absolutas creadas), hallazgos (hechos utiles para quien disene la pagina, uno por elemento), pendientes (huecos y por que).`

const EST = [
  { g: 1, lista: 'Estadio Banorte (ex Azteca; slug banorte; lo usan America, Cruz Azul y Atlante), Olimpico Universitario (slug cu; Pumas), Nemesio Diez (slug nemesio; Toluca), Hidalgo (slug hidalgo; Pachuca), Cuauhtemoc (slug cuauhtemoc; Puebla), Corregidora (slug corregidora; Queretaro)' },
  { g: 2, lista: 'Akron (slug akron; Chivas), Jalisco (slug jalisco; Atlas), BBVA (slug bbva; Monterrey), Universitario de Nuevo Leon "El Volcan" (slug volcan; Tigres), Corona TSM (slug corona; Santos)' },
  { g: 3, lista: 'Caliente (slug caliente; Tijuana), Victoria (slug victoria; Necaxa), Estadio Leon / Nou Camp (slug leon; Leon), Alfonso Lastras / Libertad Financiera (slug lastras; Atletico San Luis), Olimpico Benito Juarez (slug benitojuarez; Juarez)' },
]
const pEstadios = (e) => `${CTX}
TAREA: datos y FOTOS de estos estadios: ${e.lista}.
A) Datos verificados por estadio (parte de /home/user/SA/docs/estadios.js, que ya se verifico en agosto, y vuelve a contrastar con una fuente): nombre oficial 2026 y nombre historico, ciudad, estado, altitud_m, capacidad, superficie (natural | hibrido | sintetico), lat, lon, inaugurado, techo, equipos que lo usan, y un dato curioso corto y verificable. Indica la fuente.
B) Fotos libres de Wikimedia Commons. Por estadio consigue 2 fotos horizontales de buena calidad (ideal: una panoramica interior con cancha y gradas, y una exterior o aerea; original de minimo 1600 px de ancho). Para cada una abre su pagina File: y registra: titulo del archivo, autor tal como pide la atribucion, licencia exacta, URL de la pagina File: y URL del original. Descarga el original y generala optimizada con Pillow: JPEG progresivo, 1600 px de ancho maximo, calidad ~78, peso <= 350 KB, sin metadatos EXIF, en /home/user/SA/ligamx/web/img/estadios/<slug>-1.jpg y <slug>-2.jpg. MIRA cada imagen resultante (herramienta Read) para confirmar que SI es ese estadio y que se ve bien; describe en una linea que muestra (texto alternativo) y sugiere el punto focal CSS (object-position) para recorte vertical en celular.
Escribe /home/user/SA/ligamx/web/medios_parts/estadios_${e.g}.json: { "estadios": [ { "slug": "", "nombre": "", "nombre_historico": "", "ciudad": "", "estado": "", "altitud_m": 0, "capacidad": 0, "superficie": "", "lat": 0, "lon": 0, "inaugurado": 0, "techo": "", "equipos": [], "dato": "", "fuente_datos": "", "fotos": [ { "archivo": "img/estadios/<slug>-1.jpg", "alt": "", "pos": "50% 50%", "autor": "", "licencia": "", "url_pagina": "", "url_original": "", "ancho": 0, "alto": 0, "kb": 0 } ] } ] }
Si de algun estadio no hay foto libre decente, dilo en pendientes y deja su lista con lo que haya: no uses fotos de otro estadio.
${OUT}`

const pVideos = `${CTX}
TAREA: VIDEOS cortos y fotos de AMBIENTE con licencia libre. Carpetas: /home/user/SA/ligamx/web/video/ y /home/user/SA/ligamx/web/img/ambiente/.
A) Videos: busca en Wikimedia Commons (categorias de estadios mexicanos, "Videos of association football", "Videos of Mexico City", Estadio Azteca, Estadio Akron, Estadio BBVA, aficion, tomas aereas o con dron, time-lapse de estadios) clips con licencia libre. Meta: 3 a 5 clips. Para cada uno registra pagina File:, autor, licencia y URL del original; descargalo y con ffmpeg produce un bucle para fondo: MP4 H.264 yuv420p, perfil main, SIN audio, 1280x720 o 960x540 recortado a 16:9, 8 a 14 segundos del mejor tramo, CRF 27-30, -movflags +faststart, peso <= 2.5 MB, mas un poster JPG del primer cuadro (<= 120 KB). Extrae cuadros y MIRALOS (Read) para comprobar que se ve bien y que el contenido es el descrito. Nombra <slug>.mp4 y <slug>.jpg.
   Si no hay suficientes clips libres de buena calidad, dilo con claridad y completa hasta 3 con bucles cinematograficos generados A PARTIR DE FOTOS libres de estadios mexicanos (paneo y acercamiento lento con ffmpeg zoompan, 10 s, 30 fps, 1280x720), marcandolos con "generado_de_foto": true y acreditando la foto.
B) Ambiente: 6 fotos libres de Commons, horizontales y de buena calidad, para fondo de secciones: balon sobre el pasto, reflectores de estadio de noche, aficion mexicana en la tribuna, red de porteria, cancha vista desde arriba o tunel, y confeti o celebracion de campeon (si existe libre). Optimiza a JPEG progresivo 1600 px, <= 320 KB, sin EXIF, en img/ambiente/<slug>.jpg; MIRA cada una para confirmar contenido y calidad.
Escribe /home/user/SA/ligamx/web/medios_parts/videos.json: { "videos": [ { "archivo": "video/<slug>.mp4", "poster": "video/<slug>.jpg", "descripcion": "", "segundos": 0, "kb": 0, "generado_de_foto": false, "autor": "", "licencia": "", "url_pagina": "", "url_original": "" } ], "ambiente": [ { "archivo": "img/ambiente/<slug>.jpg", "alt": "", "pos": "50% 50%", "autor": "", "licencia": "", "url_pagina": "", "url_original": "", "kb": 0 } ] }
${OUT}`

const pEscudos = `${CTX}
TAREA: escudos de los 18 equipos para identificarlos en la interfaz (uso nominativo, pagina independiente y sin fines de lucro). Carpeta: /home/user/SA/ligamx/web/img/escudos/.
1) Descarga cada escudo de la CDN de ESPN: https://a.espncdn.com/i/teamlogos/soccer/500/<id>.png (ids en el contexto; User-Agent de navegador). Con Pillow: recorta el margen transparente, centralo en un lienzo cuadrado transparente con un margen del 4% y guarda <slug>.png a 160x160 (PNG optimizado, ideal <= 30 KB). MIRA cada resultado (Read) para confirmar que es el escudo correcto y que no quedo cortado.
2) Colores de cada equipo: toma c1, c2 y fg de /home/user/SA/docs/equipos.js (ya revisados) y agrega el color dominante medido del escudo.
3) Escribe /home/user/SA/ligamx/web/medios_parts/escudos.json: { "nota_legal": "Los escudos y nombres son marcas de sus respectivos clubes; se muestran en baja resolucion solo para identificar a los equipos. Sitio independiente, sin afiliacion con la Liga MX ni con los clubes.", "fuente": "ESPN (a.espncdn.com)", "equipos": { "<nombre canonico>": { "slug": "", "abr": "", "espn_id": 0, "escudo": "img/escudos/<slug>.png", "c1": "", "c2": "", "fg": "", "dominante": "" } } }
${OUT}`

const pMediosJuez = (parts) => `${CTX}
TAREA: varios agentes juntaron fotos de estadios, videos, fotos de ambiente y escudos. Reportes: ${JSON.stringify(parts).slice(0, 8000)}
1) Lee /home/user/SA/ligamx/web/medios_parts/*.json y revisa CADA archivo declarado: que exista, dimensiones reales (Pillow / ffprobe), peso, JPEG progresivo y sin EXIF, y que los MP4 sean H.264 yuv420p sin pista de audio y con faststart (que reproduzcan en Safari de iPhone como fondo: muted, playsinline).
2) Licencias: abre la pagina File: de Commons de al menos la mitad de las fotos y de TODOS los videos y confirma autor y licencia; lo que no sea claramente libre se retira (borra el archivo y quitalo del manifiesto).
3) MIRA (Read) una foto por estadio y un cuadro por video: confirma que el contenido corresponde y descarta lo borroso, feo o equivocado.
4) Escribe el manifiesto unificado /home/user/SA/ligamx/web/medios.json: { "estadios": [], "videos": [], "ambiente": [], "escudos": {}, "nota_legal": "", "creditos": [ {"archivo": "", "autor": "", "licencia": "", "url": ""} ] } (creditos: una entrada por cada foto y video) y una lista clara de huecos.
${OUT}`

phase('Medios')
const parts = await parallel([
  ...EST.map(e => () => agent(pEstadios(e), { label: `estadios-g${e.g}`, phase: 'Medios', schema: R })),
  () => agent(pVideos, { label: 'videos-ambiente', phase: 'Medios', schema: R }),
  () => agent(pEscudos, { label: 'escudos', phase: 'Medios', schema: R, effort: 'low' }),
])
phase('Revision')
const juez = await agent(pMediosJuez(parts.filter(Boolean)), { label: 'medios-juez', phase: 'Revision', schema: R })
return { parts, juez }
