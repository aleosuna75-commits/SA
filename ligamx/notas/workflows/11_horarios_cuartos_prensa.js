export const meta = {
  name: 'horarios-cuartos-prensa',
  description: 'Usa los horarios oficiales de cuartos (config) mientras ESPN no los lista: exportar, página, vivo-plan, contrato y pruebas',
  phases: [
    { title: 'Trabajo', detail: 'implementar el respaldo de horarios desde config/torneo.json' },
    { title: 'Verificacion', detail: 'revisión adversarial de datos/código y revisión visual' },
    { title: 'Arreglos', detail: 'corregir lo que encuentren los revisores' },
  ],
}

const INFORME = {
  type: 'object',
  properties: {
    resumen: { type: 'string' },
    cambios: { type: 'array', items: { type: 'object', properties: { archivo: { type: 'string' }, que: { type: 'string' } }, required: ['archivo', 'que'] } },
    hallazgos: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, severidad: { type: 'string', enum: ['bloqueante', 'importante', 'menor'] },
      donde: { type: 'string' }, descripcion: { type: 'string' }, evidencia: { type: 'string' },
      arreglo_sugerido: { type: 'string' }, arreglado: { type: 'boolean' } },
      required: ['id', 'severidad', 'donde', 'descripcion', 'arreglado'] } },
    pruebas: { type: 'string' },
    pendientes: { type: 'array', items: { type: 'string' } },
  },
  required: ['resumen', 'cambios', 'hallazgos', 'pruebas', 'pendientes'],
}

const S = '/tmp/claude-0/-home-user-SA/2bd39326-8617-5400-b04f-4c3059628357/scratchpad/horarios'
const COMUN = `Proyecto: /home/user/SA/ligamx (Cerebro Liga MX). Lee ESTADO.md (sección «Último cierre (23-nov)»), salidas/CONTRATO.md y web/LEEME.md antes de tocar nada.
Situación (24-nov-2026, 03:15 UTC): la fase regular terminó y los cuartos están definidos (C1 Chivas–Pachuca, C2 Cruz Azul–León, C3 América–Monterrey, C4 Atlas–Toluca). La Liga MX publicó el lunes 23 los días y horas de los 8 partidos, pero ESPN todavía NO los lista (su scoreboard del 25 al 29-nov sale vacío), así que salidas/actual.json trae «pendientes» vacío y las piernas de liguilla.torneo con id, fecha_local y hora_local en null; la página dice «Día y hora por confirmar … estos 8 partidos todavía no tienen día ni hora», lo cual ya es falso. Los horarios confirmados (Excélsior y Bolavip, hora del centro de México = UTC-6, sin horario de verano) ya están en config/torneo.json → liguilla.horarios_cuartos ({llave, pierna, local, visitante, fecha_local, hora_local, estadio, fuente}); la primera ida es Toluca–Atlas el miércoles 25 a las 19:00 (26-nov 01:00 UTC).
Reglas: JavaScript no calcula probabilidades; ESPN siempre manda sobre la configuración en cuanto liste un partido; no se inventa nada; los cortes retrospectivos de otro torneo no deben tomar estos horarios (igual que sede_prensa usa mismo_torneo). No publiques el Artifact, no hagas commit, no toques modelo/campeon.json ni registro.json. Para probar exporta con «python3 -m produccion.exportar --n-sim 100000 --sin-sello» (el orquestador hará la corrida final de un millón) y reconstruye con «python3 web/construir.py». Pruebas: «python3 -m pytest modelo/pruebas produccion/pruebas -q» y «cd web && node pruebas/prueba.js chromium» y «PLAYWRIGHT_BROWSERS_PATH=/opt/pw-webkit node pruebas/prueba.js webkit». Esta máquina tiene 4 CPU: no corras dos suites de página a la vez. Tu carpeta de trabajo para capturas y bitácoras: ${S}/<tu letra>/ (créala).`

phase('Trabajo')
const a = await agent(`${COMUN}

Encargo A (implementar). Tu letra: A.
1. produccion/exportar.py, torneo_liguilla → piernas(): si una pierna no tiene fila en el calendario (id null o fuera de partidos.csv), toma día y hora de config/torneo.json → liguilla.horarios_<fase> (hoy sólo horarios_cuartos; generalízalo como sede_prensa con sedes_<fase>) emparejando local y visitante, sólo si mismo_torneo. Llena fecha_local ('AAAA-MM-DD'), hora_local ('HH:MM') y fecha_utc (ISO en UTC, convertida desde America/Mexico_City con zoneinfo, no sumando 6 a mano) y agrega un campo nuevo por pierna, horario_origen = "calendario" (ESPN) | "prensa" (config) | null. Si ESPN ya trae la pierna, su dato gana y horario_origen = "calendario". Revisa que rondas[].fechas, el aviso de la final y cualquier otro uso de fecha_local de las piernas sigan bien; si algún aviso o texto de exportar dice que faltan día y hora, que diga lo correcto cuando vengan de la prensa.
2. web/plantilla.html: con horario_origen "prensa" la página debe mostrar el día y la hora exactos (p. ej. «Mié 25 nov · 19:00 h») en las tarjetas compactas de «Próximos partidos», en el cuadro, en el mini-cuadro de celular y en el detalle de serie, ordenadas por fecha y hora. Cambia la nota «Día y hora por confirmar…» por una que diga que el día y la hora son los anunciados por la liga y que el pronóstico completo de cada partido (mercados y combinada) y el seguimiento en vivo llegan cuando ESPN publique el partido (redáctalo corto y en el tono del resto de la página). Revisa el anuncio de la portada (puede decir cuándo empieza: la primera ida) y si la cuenta regresiva / «Próximo partido» puede usar la primera pierna con fecha_utc cuando «pendientes» está vacío: hazlo si es limpio (sólo formato, sin cálculos de probabilidad). Ninguna sección debe contradecirse (nada de «por confirmar» o «sin día ni hora» cuando sí hay horario).
3. vivo.py plan(): si ESPN no lista los partidos, que el plan también dé las piernas de liguilla.torneo con fecha_utc (fuente «actual.json (prensa)», sin id) para poder programar los despertares; no cambies observar ni el resto del motor. Agrega su prueba en produccion/pruebas/test_vivo.py.
4. salidas/CONTRATO.md y web/LEEME.md: documenta horario_origen y el comportamiento nuevo.
5. Pruebas: en produccion/pruebas/test_liguilla_exportar.py agrega pruebas de (a) prensa llena día, hora y fecha_utc correctos (19:00 del 25-nov → 2026-11-26T01:00:00+00:00), (b) ESPN gana sobre la prensa, (c) un corte de otro torneo no toma los horarios. En web/pruebas/prueba.js agrega el estado «horarios de prensa» (una variante del documento fijo DOC_DEFINIDO con las piernas llenas como las dejaría exportar) y revisa que se vean día y hora en todos los lugares del punto 2 y que no quede ningún «por confirmar». El documento real de hoy (datos de hoy) ya traerá los horarios tras tu exportación: que sus revisiones pasen.
6. Corre todo: pytest completo, prueba.js en Chromium y en WebKit, y captura a 390 px y 1440 px (portada, Próximos partidos, cuadro, detalle de una serie) en ${S}/A/; míralas con Read.
Devuelve el informe con los archivos cambiados, lo que probaste y lo que no.`, { label: 'A · horarios de prensa', phase: 'Trabajo', schema: INFORME })

phase('Verificacion')
const resumenA = JSON.stringify(a || {}).slice(0, 12000)
const [v1, v2] = await parallel([
  () => agent(`${COMUN}

Encargo V1 (revisión adversarial de datos y código). Tu letra: V1. NO corrijas nada: sólo encuentra y documenta. El agente A dijo:
${resumenA}
Revisa con «git diff» (contra HEAD) todo lo que cambió en ligamx/. Busca defectos reales: conversión de hora a UTC (zona, formato ISO, 19:07 del domingo), emparejamiento por local/visitante (nombres con acento: León, América), que ESPN gane siempre (simula en una prueba aislada o en memoria que ESPN ya lista una pierna con otra hora), que un corte retrospectivo (p. ej. --corte 2026-05-01T00:00 del Clausura 2026, con --salida a tu carpeta y --sin-sello) no tome horarios del Apertura, que rondas[].fechas y el resto del documento sigan coherentes, que el simulador y las probabilidades no cambien por esto (compara campeón y P(avanza) antes/después con la misma semilla si existe), que vivo.py plan dé las piernas con su hora correcta y no rompa el caso con ESPN, que CONTRATO.md describa lo que el código hace. Corre pytest completo. Cada hallazgo con evidencia (comando y salida). Severidad: bloqueante si publicaría algo falso o rompe el día de partido; importante si la página o los datos quedan inconsistentes; menor lo demás.`, { label: 'V1 · datos y código', phase: 'Verificacion', schema: INFORME }),
  () => agent(`${COMUN}

Encargo V2 (revisión visual). Tu letra: V2. NO corrijas nada: sólo encuentra y documenta. El agente A dijo:
${resumenA}
Arma el documento completo de hoy con «python3 web/construir.py --solo-documento ${S}/V2/doc.html» (crea la carpeta y enlaza ${S}/V2/img → /home/user/SA/ligamx/web/img y ${S}/V2/video → /home/user/SA/ligamx/web/video para que carguen las fotos) y míralo con Playwright en Chromium y en WebKit (WebKit: launch con executablePath /opt/pw-webkit/webkit-2359/pw_run.sh o PLAYWRIGHT_BROWSERS_PATH=/opt/pw-webkit) a 390x844, 360x700 y 1440x900, con el reloj del navegador en 2026-11-24T04:00:00Z y también en 2026-11-26T00:30:00Z (media hora antes de la primera ida). Revisa portada (anuncio, cuenta regresiva si la hay), «Próximos partidos» (cada tarjeta con día y hora correctos y en orden, nota nueva, nada de «por confirmar»), cuadro y mini-cuadro (día y hora de cada pierna), detalle de cada serie, menú, y que ningún texto se contradiga ni se parta a media palabra ni desborde. Mira cada captura con Read. Cada hallazgo con la ruta de su captura. Severidad: bloqueante si muestra algo falso; importante si se ve roto o contradictorio; menor lo demás.`, { label: 'V2 · revisión visual', phase: 'Verificacion', schema: INFORME }),
])

const hallazgos = [v1, v2].filter(Boolean).flatMap(v => v.hallazgos || []).filter(h => !h.arreglado)
log(`Verificación: ${hallazgos.length} hallazgos (${hallazgos.filter(h => h.severidad !== 'menor').length} bloqueantes o importantes)`)

phase('Arreglos')
let e = null
if (hallazgos.length) {
  e = await agent(`${COMUN}

Encargo E (arreglos). Tu letra: E. El agente A implementó el respaldo de horarios; dos revisores encontraron esto:
${JSON.stringify(hallazgos).slice(0, 20000)}
Reproduce cada hallazgo bloqueante e importante y arréglalo en su causa, con su prueba (pytest o prueba.js). Los menores, arréglalos si son claros y baratos; si no, explica por qué no. Al final vuelve a exportar (100,000, --sin-sello), reconstruye, corre pytest completo y prueba.js en Chromium y en WebKit, y captura a 390 px portada, Próximos partidos y cuadro en ${S}/E/ (míralas con Read). Marca arreglado=true sólo en lo que comprobaste.`, { label: 'E · arreglos', phase: 'Arreglos', schema: INFORME })
}
return { a, v1, v2, e }
